from django.db import models


class Service(models.Model):
    """
    Monitored application, component, or system owned by an operational Team.
    """

    class Status(models.TextChoices):
        HEALTHY = "HEALTHY", "Healthy"
        DEGRADED = "DEGRADED", "Degraded"
        DOWN = "DOWN", "Down"

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128, unique=True)
    description = models.TextField(blank=True, default="")
    team = models.ForeignKey(
        "users.Team",
        on_delete=models.CASCADE,
        related_name="services",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.HEALTHY,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self) -> str:
        return self.name
