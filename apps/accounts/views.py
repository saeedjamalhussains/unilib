from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView

from apps.audit.api import log


class AuditedPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    def form_valid(self, form):
        response = super().form_valid(form)
        log(self.request, "auth.password_changed", target=self.request.user)
        return response


class LoginRequiredPasswordChangeDoneView(LoginRequiredMixin, PasswordChangeDoneView):
    pass
