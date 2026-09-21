class SchedulingDomainError(Exception):
    """Base exception for scheduling domain errors."""

    pass


class InvalidTimestampError(SchedulingDomainError):
    """Raised when a naive or unparseable datetime is supplied."""

    pass


class RotationOverlapError(SchedulingDomainError):
    """Raised when base or override rotations conflict."""

    pass


class IneligibleUserError(SchedulingDomainError):
    """Raised when assigning a user who is inactive or not an active team member."""

    pass
