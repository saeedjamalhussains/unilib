from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import ListView

from apps.audit.models import AuditLog
from apps.core.mixins import LibraryPermissionRequiredMixin


class AuditLogListView(LoginRequiredMixin, LibraryPermissionRequiredMixin, ListView):
    permission_required = "audit.view_auditlog"
    model = AuditLog
    template_name = "audit/audit_list.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        events = AuditLog.objects.select_related("actor")
        action = self.request.GET.get("action", "").strip()
        outcome = self.request.GET.get("outcome", "").strip()
        query = self.request.GET.get("q", "").strip()
        if action:
            events = events.filter(action__icontains=action)
        if outcome in {choice[0] for choice in AuditLog.OUTCOME_CHOICES}:
            events = events.filter(outcome=outcome)
        if query:
            events = events.filter(
                Q(actor_repr__icontains=query)
                | Q(target_repr__icontains=query)
                | Q(target_id__icontains=query)
            )
        return events
