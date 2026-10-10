from zoneinfo import ZoneInfo, available_timezones

from django.core.exceptions import ValidationError


def validate_timezone(value: str) -> None:
    # available_timezones() is cached by zoneinfo; ZoneInfo() alone accepts odd paths.
    if value not in available_timezones():
        raise ValidationError(f"{value!r} is not an IANA timezone name.")
    ZoneInfo(value)
