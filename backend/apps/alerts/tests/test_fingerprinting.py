from apps.alerts.triage import (
    build_alert_fingerprint,
    normalize_alert_message,
    normalize_alert_source,
)


def test_normalize_alert_source():
    """Verify source whitespace and casing normalization."""
    assert normalize_alert_source("  Prometheus  ") == "prometheus"
    assert normalize_alert_source("DATADOG") == "datadog"


def test_normalize_alert_message():
    """Verify whitespace trimming and whitespace collapsing in messages."""
    raw = "  HTTP  500   rate above   20% \n\t "
    normalized = normalize_alert_message(raw)
    assert normalized == "HTTP 500 rate above 20%"

    # Tokens, IDs, and numbers must remain intact
    token_msg = "Error 404 at /v1/checkout for order_id: 987654"
    assert normalize_alert_message(token_msg) == token_msg


def test_fingerprint_deterministic():
    """Verify SHA-256 fingerprint determinism across identical input."""
    fp1 = build_alert_fingerprint(1, "prometheus", "HTTP 500 rate above 20%")
    fp2 = build_alert_fingerprint(1, "prometheus", "HTTP 500 rate above 20%")
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex string


def test_fingerprint_normalizes_whitespace_and_case():
    """Verify equivalent messages with whitespace/casing differences yield identical fingerprints."""
    msg_a = "HTTP 500 rate above 20%"
    msg_b = "  HTTP   500 rate  above 20% \n"

    fp_a = build_alert_fingerprint(1, "prometheus", msg_a)
    fp_b = build_alert_fingerprint(1, "  PROMETHEUS  ", msg_b)

    assert fp_a == fp_b


def test_fingerprint_differs_by_service():
    """Verify different service IDs result in different fingerprints."""
    fp_srv1 = build_alert_fingerprint(1, "prometheus", "CPU high")
    fp_srv2 = build_alert_fingerprint(2, "prometheus", "CPU high")
    assert fp_srv1 != fp_srv2


def test_fingerprint_differs_by_source():
    """Verify different sources result in different fingerprints."""
    fp_src1 = build_alert_fingerprint(1, "prometheus", "CPU high")
    fp_src2 = build_alert_fingerprint(1, "datadog", "CPU high")
    assert fp_src1 != fp_src2


def test_fingerprint_differs_by_substantive_message():
    """Verify different messages result in different fingerprints."""
    fp_msg1 = build_alert_fingerprint(1, "prometheus", "Disk 80% full")
    fp_msg2 = build_alert_fingerprint(1, "prometheus", "Disk 95% full")
    assert fp_msg1 != fp_msg2
