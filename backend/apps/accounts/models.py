from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_timezone


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name or self.email


class Team(TimeStampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=64, unique=True)
    members = models.ManyToManyField(User, through="Membership", related_name="teams")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Membership(TimeStampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Team admin"
        RESPONDER = "responder", "Responder"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.RESPONDER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "team"], name="uniq_membership_user_team"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.team} ({self.role})"
