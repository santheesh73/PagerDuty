from django.core.management.base import BaseCommand
from django.db import transaction

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
            self.stdout.write(f"  - {action} service: {service.name} ({service.status})")

        self.stdout.write(self.style.SUCCESS("Successfully seeded demo data."))
