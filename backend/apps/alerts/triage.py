import hashlib
import re


def normalize_alert_source(source: str) -> str:
    """
    Normalizes the alert source string.
    Trims surrounding whitespace and converts to lower case.
    """
    return source.strip().lower()


def normalize_alert_message(message: str) -> str:
    """
    Normalizes the alert message string.
    Trims leading/trailing whitespace and collapses internal multiple whitespace runs
    into a single space, without modifying error codes, IDs, or tokens.
    """
    trimmed = message.strip()
    return re.sub(r"\s+", " ", trimmed)


def build_alert_fingerprint(service_id: int | str, source: str, message: str) -> str:
    """
    Generates a deterministic SHA-256 fingerprint for alert grouping and deduplication.
    Formula: SHA-256(service_id:normalized_source:normalized_message).
    Omits received_at so identical events recurring across time share the same fingerprint.
    """
    norm_source = normalize_alert_source(source)
    norm_message = normalize_alert_message(message)
    payload = f"{service_id}:{norm_source}:{norm_message}".encode()
    return hashlib.sha256(payload).hexdigest()
