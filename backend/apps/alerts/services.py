from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.services.models import Service

from .models import Alert
from .triage import (
    build_alert_fingerprint,
    normalize_alert_message,
    normalize_alert_source,
    triage_alert,
)


def ingest_alert(
    *,
    service: Service,
    severity: str,
    message: str,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> Alert:
    """
    Core domain service to validate, normalize, fingerprint, and persist an incoming Alert.
    Phase 2 persists alerts without deduplication into incidents (prepared for Phase 3).
    """
    if not service.is_active:
        raise ValidationError(
            {"service_id": f"Cannot ingest alert for inactive service '{service.name}'."}
        )

    clean_source = normalize_alert_source(source)
    if not clean_source:
        raise ValidationError({"source": "Source cannot be blank."})

    clean_message = normalize_alert_message(message)
    if not clean_message:
        raise ValidationError({"message": "Message cannot be blank."})

    canonical_severity = severity.strip().upper()
    if canonical_severity not in Alert.Severity.values:
        valid_choices = ", ".join(Alert.Severity.values)
        raise ValidationError(
            {"severity": f"Invalid severity '{severity}'. Must be one of: {valid_choices}."}
        )

    fingerprint = build_alert_fingerprint(
        service_id=service.id,
        source=clean_source,
        message=clean_message,
    )

    with transaction.atomic():
        alert = Alert.objects.create(
            service=service,
            severity=canonical_severity,
            message=clean_message,
            source=clean_source,
            fingerprint=fingerprint,
            metadata=metadata or {},
        )
        triage_alert(alert)
        alert.refresh_from_db()
        return alert
