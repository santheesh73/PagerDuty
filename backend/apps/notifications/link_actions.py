"""Acting on an acknowledge/resolve link or a voice-call keypress, as the person who was paged."""

from django.db import transaction

from apps.core.permissions import Role, has_role
from apps.incidents import actions as incident_actions

from . import links
from .models import ActionLink


def check_actor(link: ActionLink) -> None:
    """The link works only while its owner could do the same thing in the app.

    A deactivated person, or one removed from the team since the page went out, gets nothing
    from a link that was valid when it was sent. Raised as InvalidLink so a prober learns nothing.
    """
    user = link.notification.user
    incident = link.notification.incident
    if not user.is_active or not has_role(user, incident.service.team_id, Role.RESPONDER):
        raise links.InvalidLink


def act(token: str, *, via: str) -> ActionLink:
    """Spend the link and perform its action in one transaction.

    If the action itself is refused (already acknowledged, already resolved) the transaction
    rolls back and the link is not consumed.
    """
    with transaction.atomic():
        link = links.spend(token)
        check_actor(link)
        user = link.notification.user
        incident_id = link.notification.incident_id
        if link.action == ActionLink.Action.ACK:
            incident_actions.acknowledge(incident_id, actor=user, via=via)
        else:
            incident_actions.resolve(incident_id, actor=user, via=via)
        return link
