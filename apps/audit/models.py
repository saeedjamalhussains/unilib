from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit log entries are append-only.")

    def delete(self):
        raise ValidationError("Audit log entries are append-only.")


class AuditLog(models.Model):
    OUTCOME_SUCCESS = "success"
    OUTCOME_DENIED = "denied"
    OUTCOME_FAILED = "failed"
    OUTCOME_CHOICES = (
        (OUTCOME_SUCCESS, "Success"),
        (OUTCOME_DENIED, "Denied"),
        (OUTCOME_FAILED, "Failed"),
    )

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    actor_repr = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ("-timestamp", "-pk")

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit log entries are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log entries are append-only.")

    def __str__(self):
        return f"{self.action} ({self.outcome}) at {self.timestamp}"
