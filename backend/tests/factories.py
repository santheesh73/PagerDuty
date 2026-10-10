"""factory_boy factories for every model.

`ServiceFactory()` alone builds a complete, pageable graph: team → members → schedule with a
rotating layer → two-level escalation policy (schedule, then a user) → service.
"""

from datetime import UTC, datetime, time, timedelta

import factory
from django.utils import timezone

from apps.accounts.models import Membership, Team, User
from apps.alerting.models import Alert, Severity
from apps.catalog.models import Service
from apps.escalations.models import EscalationPolicy, EscalationRule, EscalationTarget
from apps.incidents.models import EventType, Incident, IncidentEvent
from apps.notifications.models import Notification
from apps.schedules.models import LayerMember, Rotation, Schedule, ScheduleLayer, ScheduleOverride

DEFAULT_PASSWORD = "demo1234"
LAYER_START = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)  # a Monday, 09:00 UTC


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.test")
    name = factory.Faker("name")
    timezone = "UTC"
    password = factory.django.Password(DEFAULT_PASSWORD)


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    name = factory.Sequence(lambda n: f"Team {n}")
    slug = factory.Sequence(lambda n: f"team-{n}")


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    team = factory.SubFactory(TeamFactory)
    role = Membership.Role.RESPONDER


class ScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Schedule

    team = factory.SubFactory(TeamFactory)
    name = factory.Sequence(lambda n: f"Schedule {n}")
    timezone = "UTC"


class ScheduleLayerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScheduleLayer
        skip_postgeneration_save = True

    schedule = factory.SubFactory(ScheduleFactory)
    name = factory.Sequence(lambda n: f"Layer {n}")
    priority = factory.Sequence(lambda n: n)
    rotation_type = Rotation.DAILY
    turn_count = 1
    turn_length = None
    start = LAYER_START
    handoff_time = time(9, 0)

    @factory.post_generation
    def users(self, create: bool, extracted: list[User] | None, **kwargs: object) -> None:
        """`ScheduleLayerFactory(users=[a, b])` adds members in rotation order."""
        if create and extracted:
            for position, user in enumerate(extracted):
                LayerMember.objects.create(layer=self, user=user, position=position)


class LayerMemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LayerMember

    layer = factory.SubFactory(ScheduleLayerFactory)
    user = factory.SubFactory(UserFactory)
    position = factory.Sequence(lambda n: n)


class ScheduleOverrideFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScheduleOverride

    schedule = factory.SubFactory(ScheduleFactory)
    user = factory.SubFactory(UserFactory)
    start = factory.LazyFunction(timezone.now)
    end = factory.LazyAttribute(lambda o: o.start + timedelta(hours=4))


class EscalationPolicyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EscalationPolicy
        skip_postgeneration_save = True

    team = factory.SubFactory(TeamFactory)
    name = factory.Sequence(lambda n: f"Policy {n}")
    num_loops = 0

    @factory.post_generation
    def rules(self, create: bool, extracted: object, **kwargs: object) -> None:
        """Default: L0 → an on-call schedule of two responders, L1 → a team admin.

        Pass `rules=False` for an empty policy.
        """
        if not create or extracted is False:
            return
        responders = [
            MembershipFactory(team=self.team, role=Membership.Role.RESPONDER).user for _ in range(2)
        ]
        admin = MembershipFactory(team=self.team, role=Membership.Role.ADMIN).user
        schedule = ScheduleFactory(team=self.team)
        ScheduleLayerFactory(schedule=schedule, users=responders)
        l0 = EscalationRuleFactory(policy=self, level=0, delay_minutes=5)
        EscalationTargetFactory(rule=l0, target_user=None, target_schedule=schedule)
        l1 = EscalationRuleFactory(policy=self, level=1, delay_minutes=10)
        EscalationTargetFactory(rule=l1, target_user=admin)


class EscalationRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EscalationRule

    policy = factory.SubFactory(EscalationPolicyFactory, rules=False)
    level = factory.Sequence(lambda n: n)
    delay_minutes = 5


class EscalationTargetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EscalationTarget

    rule = factory.SubFactory(EscalationRuleFactory)
    position = factory.Sequence(lambda n: n)
    target_user = factory.SubFactory(UserFactory)
    target_schedule = None


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    team = factory.SubFactory(TeamFactory)
    name = factory.Sequence(lambda n: f"service-{n}")
    description = "Synthetic test service"
    escalation_policy = factory.SubFactory(
        EscalationPolicyFactory, team=factory.SelfAttribute("..team")
    )
    mode = Service.Mode.ACTIVE


class IncidentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Incident

    service = factory.SubFactory(ServiceFactory)
    title = factory.Faker("sentence", nb_words=6)
    dedup_key = factory.Sequence(lambda n: f"dedup-{n}")
    triggered_at = factory.LazyFunction(timezone.now)
    escalation_snapshot = factory.LazyFunction(dict)


class AlertFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Alert

    service = factory.SubFactory(ServiceFactory)
    incident = None
    dedup_key = factory.Sequence(lambda n: f"dedup-{n}")
    severity = Severity.CRITICAL
    summary = factory.Faker("sentence", nb_words=5)
    source = "factory"
    payload = factory.LazyFunction(dict)


class IncidentEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IncidentEvent

    incident = factory.SubFactory(IncidentFactory)
    type = EventType.NOTE_ADDED
    message = "note"


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    incident = factory.SubFactory(IncidentFactory)
    user = factory.SubFactory(UserFactory)
    channel = Notification.Channel.IN_APP
    idempotency_key = factory.Sequence(lambda n: f"test-notification-{n}")
