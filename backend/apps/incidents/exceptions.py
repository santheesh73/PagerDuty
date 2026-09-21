class IncidentDomainError(Exception):
    """Base domain exception for operational incident errors."""

    pass


class IncidentStateConflict(IncidentDomainError):
    """Raised when an action is incompatible with current incident status."""

    pass


class IncidentReopenConflict(IncidentDomainError):
    """Raised when reopening is prevented by an active incident for the same service and fingerprint."""

    pass
