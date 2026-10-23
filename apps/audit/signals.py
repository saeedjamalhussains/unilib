from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.audit.api import log


@receiver(user_logged_in, dispatch_uid="audit_user_logged_in")
def audit_login_success(sender, request, user, **kwargs):
    log(request, "auth.login", target=user)


@receiver(user_login_failed, dispatch_uid="audit_user_login_failed")
def audit_login_failure(sender, credentials, request, **kwargs):
    username_field = get_user_model().USERNAME_FIELD
    attempted_username = credentials.get(username_field, "")
    log(
        request,
        "auth.login_failed",
        outcome="failed",
        username=str(attempted_username)[:150],
    )


@receiver(user_logged_out, dispatch_uid="audit_user_logged_out")
def audit_logout(sender, request, user, **kwargs):
    log(request, "auth.logout", target=user)
