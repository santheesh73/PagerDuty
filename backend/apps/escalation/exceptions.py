class PolicyConfigurationError(Exception):
    """Raised when an escalation policy or level configuration is invalid or missing."""
    pass


class EscalationTargetUnavailable(Exception):
    """Raised when an escalation level's intended target cannot be resolved."""
    pass
