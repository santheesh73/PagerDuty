from datetime import UTC, datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.incidents.models import Incident, IncidentEvent
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.services.models import Service
from apps.users.models import Team, TeamMembership, User


class Command(BaseCommand):
    help = "Seed deterministic demo users, teams, memberships, and services (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding demo identity and services data...")

        # 1. Users
        users_data = [
            {"username": "alice", "first_name": "Alice", "last_name": "Smith", "email": "alice@example.com"},
            {"username": "bob", "first_name": "Bob", "last_name": "Jones", "email": "bob@example.com"},
            {"username": "charlie", "first_name": "Charlie", "last_name": "Brown", "email": "charlie@example.com"},
        ]
        users = {}
        for u_data in users_data:
            user, created = User.objects.get_or_create(
                username=u_data["username"],
                defaults={
                    "first_name": u_data["first_name"],
                    "last_name": u_data["last_name"],
                    "email": u_data["email"],
                    "is_active": True,
                },
            )
            users[u_data["username"]] = user
            action = "Created" if created else "Found existing"
            self.stdout.write(f"  - {action} user: {user.username}")

        # 2. Teams
        teams_data = [
            {"name": "Backend Team", "slug": "backend", "description": "Core backend APIs and domain logic"},
            {"name": "Platform Team", "slug": "platform", "description": "Infrastructure and developer platforms"},
            {"name": "SRE Team", "slug": "sre", "description": "Site reliability and incident response"},
        ]
        teams = {}
        for t_data in teams_data:
            team, created = Team.objects.get_or_create(
                slug=t_data["slug"],
                defaults={
                    "name": t_data["name"],
                    "description": t_data["description"],
                    "is_active": True,
                },
            )
            teams[t_data["slug"]] = team
            action = "Created" if created else "Found existing"
            self.stdout.write(f"  - {action} team: {team.name}")

        # 3. Memberships
        memberships_data = [
            {"user": users["alice"], "team": teams["backend"], "role": TeamMembership.Role.ENGINEER},
            {"user": users["bob"], "team": teams["backend"], "role": TeamMembership.Role.LEAD},
            {"user": users["charlie"], "team": teams["backend"], "role": TeamMembership.Role.RESPONDER},
            {"user": users["charlie"], "team": teams["sre"], "role": TeamMembership.Role.RESPONDER},
        ]
        for m_data in memberships_data:
            membership, created = TeamMembership.objects.get_or_create(
                user=m_data["user"],
                team=m_data["team"],
                defaults={
                    "role": m_data["role"],
                    "is_active": True,
                },
            )
            if not created:
                membership.role = m_data["role"]
                membership.is_active = True
                membership.save()
            action = "Created" if created else "Ensured"
            self.stdout.write(f"  - {action} membership: {membership}")

        # 4. Services
        services_data = [
            {
                "name": "Payment API",
                "slug": "payment-api",
                "team": teams["backend"],
                "description": "Payment processing and settlement service",
                "status": Service.Status.HEALTHY,
            },
            {
                "name": "Authentication API",
                "slug": "auth-api",
                "team": teams["backend"],
                "description": "User authentication and token service",
                "status": Service.Status.HEALTHY,
            },
            {
                "name": "Notification API",
                "slug": "notification-api",
                "team": teams["platform"],
                "description": "Multi-channel notification dispatch service",
                "status": Service.Status.HEALTHY,
            },
        ]
        for s_data in services_data:
            service, created = Service.objects.get_or_create(
                slug=s_data["slug"],
                defaults={
                    "name": s_data["name"],
                    "team": s_data["team"],
                    "description": s_data["description"],
                    "status": s_data["status"],
                    "is_active": True,
                },
            )
            if not created:
                service.name = s_data["name"]
                service.team = s_data["team"]
                service.status = s_data["status"]
                service.is_active = True
                service.save()
            action = "Created" if created else "Ensured"
        # 5. Schedules & Rotations (Phase 4)
        backend_schedule, created = Schedule.objects.get_or_create(
            slug="backend-primary",
            defaults={
                "name": "Backend Primary",
                "team": teams["backend"],
                "timezone": "UTC",
                "is_primary": True,
                "is_active": True,
            },
        )
        if not created:
            backend_schedule.name = "Backend Primary"
            backend_schedule.team = teams["backend"]
            backend_schedule.timezone = "UTC"
            backend_schedule.is_primary = True
            backend_schedule.is_active = True
            backend_schedule.save()
        action = "Created" if created else "Ensured"
        self.stdout.write(f"  - {action} schedule: {backend_schedule.name}")

        # Seed rotations for deterministic reference date 2026-09-21
        rotations_data = [
            {
                "user": users["alice"],
                "start_time": datetime(2026, 9, 21, 9, 0, 0, tzinfo=UTC),
                "end_time": datetime(2026, 9, 21, 17, 0, 0, tzinfo=UTC),
                "is_override": False,
            },
            {
                "user": users["bob"],
                "start_time": datetime(2026, 9, 21, 17, 0, 0, tzinfo=UTC),
                "end_time": datetime(2026, 9, 22, 1, 0, 0, tzinfo=UTC),
                "is_override": False,
            },
            {
                "user": users["bob"],
                "start_time": datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC),
                "end_time": datetime(2026, 9, 21, 14, 0, 0, tzinfo=UTC),
                "is_override": True,
            },
        ]
        for r_data in rotations_data:
            rot, created = ScheduleRotation.objects.get_or_create(
                schedule=backend_schedule,
                start_time=r_data["start_time"],
                end_time=r_data["end_time"],
                is_override=r_data["is_override"],
                defaults={"user": r_data["user"]},
            )
            action = "Created" if created else "Ensured"
            self.stdout.write(f"  - {action} rotation: {rot}")

        # 6. Escalation Policies & Levels (Phase 5)
        backend_policy, created = EscalationPolicy.objects.get_or_create(
            slug="backend-critical-policy",
            defaults={
                "name": "Backend Critical Policy",
                "team": teams["backend"],
                "is_active": True,
            },
        )
        if not created:
            backend_policy.name = "Backend Critical Policy"
            backend_policy.team = teams["backend"]
            backend_policy.is_active = True
            backend_policy.save()
        action = "Created" if created else "Ensured"
        self.stdout.write(f"  - {action} escalation policy: {backend_policy.name}")

        # Level 1: Current On-Call (wait 5 mins)
        level_1, created = EscalationLevel.objects.get_or_create(
            policy=backend_policy,
            order=1,
            defaults={
                "target_type": EscalationLevel.TargetType.CURRENT_ON_CALL,
                "target_user": None,
                "wait_minutes": 5,
            },
        )
        if not created:
            level_1.target_type = EscalationLevel.TargetType.CURRENT_ON_CALL
            level_1.target_user = None
            level_1.wait_minutes = 5
            level_1.save()
        action = "Created" if created else "Ensured"
        self.stdout.write(f"  - {action} level 1: {level_1}")

        # Level 2: Bob (User target, wait 10 mins)
        level_2, created = EscalationLevel.objects.get_or_create(
            policy=backend_policy,
            order=2,
            defaults={
                "target_type": EscalationLevel.TargetType.USER,
                "target_user": users["bob"],
                "wait_minutes": 10,
            },
        )
        if not created:
            level_2.target_type = EscalationLevel.TargetType.USER
            level_2.target_user = users["bob"]
            level_2.wait_minutes = 10
            level_2.save()
        action = "Created" if created else "Ensured"
        self.stdout.write(f"  - {action} level 2: {level_2}")

        # Level 3: Charlie (User target, wait 15 mins)
        level_3, created = EscalationLevel.objects.get_or_create(
            policy=backend_policy,
            order=3,
            defaults={
                "target_type": EscalationLevel.TargetType.USER,
                "target_user": users["charlie"],
                "wait_minutes": 15,
            },
        )
        if not created:
            level_3.target_type = EscalationLevel.TargetType.USER
            level_3.target_user = users["charlie"]
            level_3.wait_minutes = 15
            level_3.save()
        action = "Created" if created else "Ensured"
        self.stdout.write(f"  - {action} level 3: {level_3}")

        # Link Payment API service to backend critical policy
        payment_service = Service.objects.filter(slug="payment-api").first()
        if payment_service:
            payment_service.escalation_policy = backend_policy
            payment_service.save(update_fields=["escalation_policy"])
            self.stdout.write(f"  - Linked Payment API to {backend_policy.name}")

        # 7. Deterministic Sample Incidents (Phase 10 Product Experience)
        auth_service = Service.objects.filter(slug="auth-api").first()
        notification_service = Service.objects.filter(slug="notification-api").first()

        now = timezone.now()

        # INC-1: Payment API, Critical, Triggered, Assigned to Alice, Level 1
        if payment_service:
            inc1_fp = "payment-api-gateway-504-outage"
            inc1_triggered = now - timedelta(minutes=15)
            inc1, inc1_created = Incident.objects.get_or_create(
                service=payment_service,
                fingerprint=inc1_fp,
                defaults={
                    "title": "Payment Gateway 504 Gateway Timeout",
                    "severity": Incident.Severity.CRITICAL,
                    "status": Incident.Status.TRIGGERED,
                    "assigned_user": users["alice"],
                    "current_escalation_level": level_1,
                    "triggered_at": inc1_triggered,
                },
            )
            if inc1_created:
                IncidentEvent.objects.create(
                    incident=inc1,
                    event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED,
                    actor=None,
                    metadata={"service": "payment-api", "severity": "CRITICAL"},
                    created_at=inc1_triggered,
                )
                IncidentEvent.objects.create(
                    incident=inc1,
                    event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED,
                    actor=users["alice"],
                    metadata={"user_id": users["alice"].id, "username": "alice", "source": "schedule"},
                    created_at=inc1_triggered + timedelta(seconds=2),
                )
                IncidentEvent.objects.create(
                    incident=inc1,
                    event_type=IncidentEvent.EventType.ESCALATION_STARTED,
                    actor=None,
                    metadata={"policy": backend_policy.name, "level": 1},
                    created_at=inc1_triggered + timedelta(seconds=5),
                )
            action = "Created" if inc1_created else "Ensured"
            self.stdout.write(f"  - {action} sample incident 1: {inc1}")

        # INC-2: Auth API, High, Acknowledged, Assigned to Bob, Level 2
        if auth_service:
            inc2_fp = "auth-api-token-validation-errors"
            inc2_triggered = now - timedelta(hours=1, minutes=20)
            inc2_ack = now - timedelta(minutes=45)
            inc2, inc2_created = Incident.objects.get_or_create(
                service=auth_service,
                fingerprint=inc2_fp,
                defaults={
                    "title": "High Token Validation Latency & Failure Rate",
                    "severity": Incident.Severity.HIGH,
                    "status": Incident.Status.ACKNOWLEDGED,
                    "assigned_user": users["bob"],
                    "current_escalation_level": level_2,
                    "triggered_at": inc2_triggered,
                    "acknowledged_at": inc2_ack,
                },
            )
            if inc2_created:
                IncidentEvent.objects.create(
                    incident=inc2,
                    event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED,
                    actor=None,
                    metadata={"service": "auth-api", "severity": "HIGH"},
                    created_at=inc2_triggered,
                )
                IncidentEvent.objects.create(
                    incident=inc2,
                    event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED,
                    actor=users["alice"],
                    metadata={"user_id": users["alice"].id, "username": "alice", "source": "schedule"},
                    created_at=inc2_triggered + timedelta(seconds=2),
                )
                IncidentEvent.objects.create(
                    incident=inc2,
                    event_type=IncidentEvent.EventType.ESCALATION_STARTED,
                    actor=None,
                    metadata={"policy": backend_policy.name, "level": 1},
                    created_at=inc2_triggered + timedelta(seconds=5),
                )
                IncidentEvent.objects.create(
                    incident=inc2,
                    event_type=IncidentEvent.EventType.INCIDENT_ESCALATED,
                    actor=None,
                    metadata={"from_level": 1, "to_level": 2},
                    created_at=inc2_triggered + timedelta(minutes=5),
                )
                IncidentEvent.objects.create(
                    incident=inc2,
                    event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED,
                    actor=users["bob"],
                    metadata={"user_id": users["bob"].id, "username": "bob", "target_type": "USER"},
                    created_at=inc2_triggered + timedelta(minutes=5, seconds=2),
                )
                IncidentEvent.objects.create(
                    incident=inc2,
                    event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED,
                    actor=users["bob"],
                    metadata={"acknowledged_by": users["bob"].username},
                    created_at=inc2_ack,
                )
            action = "Created" if inc2_created else "Ensured"
            self.stdout.write(f"  - {action} sample incident 2: {inc2}")

        # INC-3: Notification API, Medium, Resolved, Resolved by Charlie
        if notification_service:
            inc3_fp = "notification-queue-backlog"
            inc3_triggered = now - timedelta(hours=3)
            inc3_ack = now - timedelta(hours=2, minutes=30)
            inc3_resolved = now - timedelta(hours=1, minutes=15)
            inc3, inc3_created = Incident.objects.get_or_create(
                service=notification_service,
                fingerprint=inc3_fp,
                defaults={
                    "title": "Notification Delivery Queue Congestion",
                    "severity": Incident.Severity.MEDIUM,
                    "status": Incident.Status.RESOLVED,
                    "assigned_user": users["charlie"],
                    "current_escalation_level": None,
                    "triggered_at": inc3_triggered,
                    "acknowledged_at": inc3_ack,
                    "resolved_at": inc3_resolved,
                },
            )
            if inc3_created:
                IncidentEvent.objects.create(
                    incident=inc3,
                    event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED,
                    actor=None,
                    metadata={"service": "notification-api", "severity": "MEDIUM"},
                    created_at=inc3_triggered,
                )
                IncidentEvent.objects.create(
                    incident=inc3,
                    event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED,
                    actor=users["charlie"],
                    metadata={"user_id": users["charlie"].id, "username": "charlie"},
                    created_at=inc3_triggered + timedelta(seconds=2),
                )
                IncidentEvent.objects.create(
                    incident=inc3,
                    event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED,
                    actor=users["charlie"],
                    metadata={"acknowledged_by": users["charlie"].username},
                    created_at=inc3_ack,
                )
                IncidentEvent.objects.create(
                    incident=inc3,
                    event_type=IncidentEvent.EventType.INCIDENT_RESOLVED,
                    actor=users["charlie"],
                    metadata={"resolved_by": users["charlie"].username},
                    created_at=inc3_resolved,
                )
            action = "Created" if inc3_created else "Ensured"
            self.stdout.write(f"  - {action} sample incident 3: {inc3}")

        self.stdout.write(self.style.SUCCESS("Successfully seeded demo data."))

