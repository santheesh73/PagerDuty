from celery import shared_task
from django.conf import settings

from . import heartbeat, retention, selfcheck


@shared_task
def heartbeat_task() -> bool:
    """Stamp Beat's liveness, then ping the dead-man's switch iff the stack is healthy."""
    heartbeat.record()
    # Beat is plainly alive (we are running), so judge only the work it is supposed to drive.
    if all(c.ok for c in selfcheck.run(include_beat=False)):
        return heartbeat.ping_external()
    return False


@shared_task
def purge_old_data() -> dict[str, int]:
    """Daily housekeeping: retention (only if RETENTION_DAYS > 0) and expired sessions."""
    retention.clear_expired_sessions()
    return retention.purge(settings.RETENTION_DAYS)
