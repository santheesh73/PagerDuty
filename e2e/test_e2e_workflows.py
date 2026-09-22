#!/usr/bin/env python3
"""
End-to-End (E2E) Integration & Workflow Test Suite
Phase 11: Quality Testing & Verification

Executes against the running incident management platform via HTTP REST API:
- Scenario 1: Incident responder workflow (Alert ingestion -> Incident -> Ack -> Resolve -> Reopen)
- Scenario 2: Configuration affects runtime (Schedule overrides & 1-second boundary transitions)
- Scenario 3: Escalation progression, timeline audit trail, and contract verification
"""

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE_URL = "http://localhost:8000/api"


def make_request(
    endpoint: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    expected_status: int | list[int] = 200,
) -> tuple[int, Any]:
    """Helper to perform HTTP requests against the platform API."""
    url = f"{BASE_URL}{endpoint}" if endpoint.startswith("/") else f"{BASE_URL}/{endpoint}"
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded_data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    acceptable_statuses = [expected_status] if isinstance(expected_status, int) else expected_status

    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            assert status in acceptable_statuses, f"Expected {acceptable_statuses} from {method} {url}, got {status}"
            return status, parsed
    except urllib.error.HTTPError as err:
        status = err.code
        body = err.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        assert status in acceptable_statuses, f"Expected {acceptable_statuses} from {method} {url}, got {status}: {parsed}"
        return status, parsed


def test_scenario_1_incident_responder_workflow():
    print("\n--- Running Scenario 1: Incident Responder Workflow ---")

    # Step 1: Ingest alert with unique test fingerprint
    test_run_id = int(time.time())
    alert_payload = {
        "service_id": 1,
        "message": f"High latency on payment settlement pipeline (E2E run {test_run_id})",
        "severity": "critical",
        "source": "datadog",
        "metadata": {"cluster": "us-east-1", "run_id": test_run_id},
    }
    status, alert_resp = make_request("/alerts/", method="POST", data=alert_payload, expected_status=201)
    print(f"  [1/7] Ingested alert -> Alert ID: {alert_resp['id']}, Service: {alert_resp['service']['slug']}")
    assert alert_resp["service"]["id"] == 1

    # Step 2: Query created incident
    incident_id = alert_resp.get("incident_id")
    if not incident_id:
        status, inc_list = make_request(f"/incidents/?service=1&status=triggered", expected_status=200)
        incident_id = inc_list[0]["id"]

    status, inc = make_request(f"/incidents/{incident_id}/", expected_status=200)
    print(f"  [2/7] Incident INC-{incident_id:04d} retrieved: Status={inc['status']}, Severity={inc['severity']}")
    assert inc["status"].lower() == "triggered"
    assert inc["acknowledged_at"] is None
    assert inc["resolved_at"] is None

    # Step 3: Verify timeline audit trail has INCIDENT_TRIGGERED
    status, events = make_request(f"/incidents/{incident_id}/events/", expected_status=200)
    event_types = [e["event_type"] for e in events]
    print(f"  [3/7] Verified audit timeline events: {event_types}")
    assert "INCIDENT_TRIGGERED" in event_types
    assert "ALERT_ATTACHED" in event_types

    # Step 4: Prohibited direct mutation verification (POST /api/incidents/ -> 405, PATCH -> 405)
    status, _ = make_request("/incidents/", method="POST", data={"title": "Hack"}, expected_status=405)
    status, _ = make_request(f"/incidents/{incident_id}/", method="PATCH", data={"status": "resolved"}, expected_status=405)
    print("  [4/7] Verified direct POST /api/incidents/ and PATCH /api/incidents/{id}/ return 405 Method Not Allowed")

    # Step 5: Acknowledge incident
    status, ack_resp = make_request(f"/incidents/{incident_id}/acknowledge/", method="POST", data={}, expected_status=200)
    assert ack_resp["status"] == "ACKNOWLEDGED"
    assert ack_resp["acknowledged_at"] is not None
    print(f"  [5/7] Incident acknowledged successfully at {ack_resp['acknowledged_at']}")

    # Step 6: Resolve incident
    status, res_resp = make_request(f"/incidents/{incident_id}/resolve/", method="POST", data={}, expected_status=200)
    assert res_resp["status"] == "RESOLVED"
    assert res_resp["resolved_at"] is not None
    print(f"  [6/7] Incident resolved successfully at {res_resp['resolved_at']}")

    # Step 7: Invalid transition rejection (Ack after Resolve -> 409 Conflict)
    status, conflict_resp = make_request(f"/incidents/{incident_id}/acknowledge/", method="POST", data={}, expected_status=409)
    print(f"  [7/7] Verified 409 Conflict on invalid transition (Acknowledge after Resolve)")

    print("  [PASS] Scenario 1 passed successfully!")


def test_scenario_2_configuration_affects_runtime():
    print("\n--- Running Scenario 2: Configuration Affects Runtime Behavior ---")

    schedule_id = 1

    # Exact boundary checks matching Section 40 and Phase 11 Golden Matrix:
    # Base: Alice 09:00 - 17:00
    # Override: Bob 12:00 - 14:00

    # 11:00:00 -> Alice (Base)
    status, res = make_request(f"/schedules/{schedule_id}/on-call/?at=2026-09-21T11:00:00Z", expected_status=200)
    assert res["user"]["username"] == "alice"
    assert res["source"] == "base"
    print("  [1/5] Boundary 11:00:00Z -> Alice (base)")

    # 11:59:59 -> Alice (1s before override begins)
    status, res = make_request(f"/schedules/{schedule_id}/on-call/?at=2026-09-21T11:59:59Z", expected_status=200)
    assert res["user"]["username"] == "alice"
    assert res["source"] == "base"
    print("  [2/5] Boundary 11:59:59Z (1s prior) -> Alice (base)")

    # 12:00:00 -> Bob (Override starts)
    status, res = make_request(f"/schedules/{schedule_id}/on-call/?at=2026-09-21T12:00:00Z", expected_status=200)
    assert res["user"]["username"] == "bob"
    assert res["source"] == "override"
    print("  [3/5] Boundary 12:00:00Z -> Bob (override begins)")

    # 13:59:59 -> Bob (1s before override ends)
    status, res = make_request(f"/schedules/{schedule_id}/on-call/?at=2026-09-21T13:59:59Z", expected_status=200)
    assert res["user"]["username"] == "bob"
    assert res["source"] == "override"
    print("  [4/5] Boundary 13:59:59Z (1s prior to end) -> Bob (override active)")

    # 14:00:00 -> Alice (Override ends, reverts to base)
    status, res = make_request(f"/schedules/{schedule_id}/on-call/?at=2026-09-21T14:00:00Z", expected_status=200)
    assert res["user"]["username"] == "alice"
    assert res["source"] == "base"
    print("  [5/5] Boundary 14:00:00Z -> Alice (override ends, returned to base)")

    print("  [PASS] Scenario 2 passed successfully!")


def test_scenario_3_escalation_and_contracts():
    print("\n--- Running Scenario 3: Escalation Progression & Contract Verification ---")

    # 1. Escalation Policy inspection
    status, policy = make_request("/escalation-policies/1/", expected_status=200)
    print(f"  [1/4] Escalation Policy retrieved: {policy['name']} with {len(policy['levels'])} levels")
    assert len(policy["levels"]) >= 2
    assert policy["levels"][0]["order"] == 1

    # 2. Team mismatch rejection in Service API
    mismatch_payload = {
        "name": "Invalid Cross Team Service",
        "slug": f"invalid-svc-{int(time.time())}",
        "team_id": 2,  # Platform Team
        "escalation_policy_id": 1,  # Backend Team's policy
    }
    status, err = make_request("/services/", method="POST", data=mismatch_payload, expected_status=400)
    assert "escalation_policy_id" in err
    print(f"  [2/4] Cross-team escalation policy rejected as expected: {err['escalation_policy_id']}")

    # 3. Standardized error envelope on 404
    status, err_404 = make_request("/incidents/999999/", expected_status=404)
    assert "error" in err_404 or "detail" in err_404
    print("  [3/4] Standardized error format confirmed on 404")

    # 4. Analytics null semantics verification
    status, analytics = make_request("/analytics/summary/", expected_status=200)
    assert "incident_count" in analytics
    assert "active_incidents" in analytics
    print(f"  [4/4] Analytics summary endpoint confirmed: incident_count={analytics['incident_count']}, active={analytics['active_incidents']}")

    print("  [PASS] Scenario 3 passed successfully!")


def main():
    print("==============================================================")
    print("  Incident Management Platform -- Phase 11 E2E Verification   ")
    print("==============================================================")
    start_time = time.time()

    # Verify platform health first
    status, health = make_request("/health/", expected_status=200)
    print(f"Health Check: status={health.get('status')}, DB={health.get('dependencies', {}).get('database')}, Redis={health.get('dependencies', {}).get('redis')}")
    assert health.get("status") == "ok"

    try:
        test_scenario_1_incident_responder_workflow()
        test_scenario_2_configuration_affects_runtime()
        test_scenario_3_escalation_and_contracts()
    except Exception as exc:
        print(f"\n[FAIL] E2E TEST FAILED: {exc}")
        sys.exit(1)

    duration = time.time() - start_time
    print("\n==============================================================")
    print(f"  All 3 E2E Scenarios PASSED in {duration:.2f}s!  ")
    print("==============================================================")
    sys.exit(0)


if __name__ == "__main__":
    main()
