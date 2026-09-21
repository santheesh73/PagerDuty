from django.core.exceptions import ValidationError


class SchedulingDomainError(Exception):
    """Base exception for scheduling domain errors."""

    pass


class InvalidTimestampError(SchedulingDomainError, ValueError):
    """Raised when a naive or unparseable datetime is supplied."""

    pass


class RotationOverlapError(SchedulingDomainError, ValidationError):
    """Raised when base or override rotations conflict."""

    pass


class IneligibleUserError(SchedulingDomainError, ValidationError):
    """Raised when assigning a user who is inactive or not an active team member."""

    pass

