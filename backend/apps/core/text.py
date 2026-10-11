"""Small text helpers shared by ingest and the notification channels."""


def one_line(text: str) -> str:
    """Collapse every run of whitespace (newlines, tabs, repeats) into a single space.

    Alert summaries come from monitoring templates and routinely contain newlines; a title
    or an email header may not.
    """
    return " ".join(text.split())
