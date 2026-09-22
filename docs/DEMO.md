# 5-Minute Demonstration Runbook

This guide walks reviewers through a complete, deterministic walkthrough of the platform from a clean start.

---

## 1. Prerequisites & Startup

```bash
# 1. Clone repository and copy environment template
cp .env.example .env

# 2. Start the full application stack in background
docker compose up -d --build

# 3. Seed deterministic demonstration data
docker compose exec backend python manage.py seed_demo
```

Verify health check:
```bash
curl -s http://localhost:8000/api/health/
# Expected: {"status":"ok","dependencies":{"database":"ok","redis":"ok"}}
```

Open the web interface: **[http://localhost:5173](http://localhost:5173)**

---

## 2. Step-by-Step Operational Walkthrough

### Step 1: Inspect the On-Call Schedule
- Navigate to **On-Call Schedule** (`/schedules`).
- Observe that **alice** is the base on-call responder for the `Backend Primary` schedule.
- Notice the active override: **bob** is scheduled for an override window.
- The UI highlights the active responder with an `[OVERRIDE]` badge.

### Step 2: Trigger a Production Incident
Simulate an alert from a monitoring system (e.g. Datadog or Prometheus):
```bash
curl -X POST http://localhost:8000/api/alerts/ \
  -H "Content-Type: application/json" \
  -d '{
    "service": 1,
    "severity": "CRITICAL",
    "message": "Payment Gateway 504 Gateway Timeout",
    "source": "PaymentGatewayMonitor",
    "metadata": {"endpoint": "/v1/charge", "latency_ms": 15200}
  }'
```
- The API returns HTTP `201 Created` with a deterministic SHA-256 fingerprint.

### Step 3: Inspect the Incident Workbench
- Navigate to **Incidents** (`/incidents`).
- Notice the newly created incident:
  - **Status**: `TRIGGERED` (red badge)
  - **Severity**: `CRITICAL`
  - **Service**: `Payment API`
  - **Assignee**: **bob** (assigned automatically based on the active override)
- Click on the incident to open the **Incident Detail** view.

### Step 4: Review the Immutable Audit Timeline
- In the **Incident Detail** view, inspect the chronological event timeline:
  - `INCIDENT_TRIGGERED`: Incident created and assigned to responder.
  - `ALERT_ATTACHED`: Alert signal linked.
  - `ESCALATION_STARTED`: Level 1 of `Backend Critical Policy` initiated.

### Step 5: Test Active Incident Deduplication
Submit the exact same alert payload again:
```bash
curl -X POST http://localhost:8000/api/alerts/ \
  -H "Content-Type: application/json" \
  -d '{
    "service": 1,
    "severity": "CRITICAL",
    "message": "Payment Gateway 504 Gateway Timeout",
    "source": "PaymentGatewayMonitor"
  }'
```
- Return to the Incidents list. Notice **no second incident** was created.
- Check the Incident Detail view: a new `ALERT_ATTACHED` event appears on the timeline, indicating deduplication into the existing active incident.

### Step 6: Acknowledge the Incident
- In the Incident Detail view, click the **Acknowledge** button.
- Status changes to `ACKNOWLEDGED` (amber badge).
- The timeline records `INCIDENT_ACKNOWLEDGED`.
- Any pending escalation timers are automatically halted.

### Step 7: Resolve the Incident
- In the Incident Detail view, click the **Resolve** button.
- Status transitions to `RESOLVED` (green badge).
- `resolved_at` timestamp is set, and `INCIDENT_RESOLVED` is appended to the timeline.

### Step 8: Inspect Operational Analytics
- Navigate to **Analytics** (`/analytics`).
- Observe the updated metrics:
  - **Total Incidents** and **Active Incidents** counts.
  - **Mean Time to Acknowledge (MTTA)** computed dynamically.
  - **Mean Time to Resolve (MTTR)** computed dynamically.
  - **Severity Distribution** chart updated.
