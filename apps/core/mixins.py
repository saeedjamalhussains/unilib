from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from apps.audit.api import log


class LibraryPermissionRequiredMixin(PermissionRequiredMixin):
    raise_exception = True

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        log(
            self.request,
            "access.denied",
            target=self.request.path,
            outcome="denied",
            permission=self.get_permission_required(),
        )
        self.request._audit_access_denied = True
        raise PermissionDenied


class OwnedByMemberMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.owned_by(self.request.user)
