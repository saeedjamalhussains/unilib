from django.contrib import admin

from apps.audit.models import AuditLog
from apps.audit.site import admin_site


@admin.register(AuditLog, site=admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor_repr", "action", "target_repr", "outcome")
    list_filter = ("action", "outcome", "timestamp")
    search_fields = ("actor_repr", "target_repr", "action")
    readonly_fields = (
        "timestamp",
        "actor",
        "actor_repr",
        "action",
        "target_type",
        "target_id",
        "target_repr",
        "ip_address",
        "user_agent",
        "metadata",
        "outcome",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
