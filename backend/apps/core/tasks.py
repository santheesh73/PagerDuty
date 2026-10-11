from celery import shared_task

from . import heartbeat, selfcheck


@shared_task
def heartbeat_task() -> bool:
    """Stamp Beat's liveness, then ping the dead-man's switch iff the stack is healthy."""
    heartbeat.record()
    # Beat is plainly alive (we are running), so judge only the work it is supposed to drive.
    if all(c.ok for c in selfcheck.run(include_beat=False)):
        return heartbeat.ping_external()
    return False
