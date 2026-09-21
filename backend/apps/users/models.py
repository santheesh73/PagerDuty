from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """
    Custom User model representing individuals in the platform.
    Extends AbstractUser to provide a deterministic foundation for future
    incident assignment, schedule rotations, and notification routing.
    """

    class Meta:
        ordering = ["username"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        return self.get_full_name().strip() or self.username


class Team(models.Model):
    """
    Operational ownership group responsible for services, escalation policies,
    and on-call schedules.
    """

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Team"
        verbose_name_plural = "Teams"

    def __str__(self) -> str:
        return self.name


class TeamMembership(models.Model):
    """
    Explicit join model linking a User to a Team with a defined operational role.
    """

    class Role(models.TextChoices):
        ENGINEER = "ENGINEER", "Engineer"
        LEAD = "LEAD", "Lead"
        RESPONDER = "RESPONDER", "Responder"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.ENGINEER,
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-joined_at"]
        verbose_name = "Team Membership"
        verbose_name_plural = "Team Memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "team"],
                name="unique_user_team_membership",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.username} -> {self.team.name} ({self.role})"
