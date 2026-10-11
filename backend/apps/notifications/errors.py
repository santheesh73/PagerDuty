class ChannelError(Exception):
    """A transient delivery failure; the task retries with backoff."""


class PermanentChannelError(Exception):
    """A delivery that can never succeed (bad number, channel not configured): fail it now,
    visibly, instead of retrying while a human waits for a page that will not come."""
