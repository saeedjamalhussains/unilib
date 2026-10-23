from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from apps.audit.api import log


def library_permission_required(perm):
    """Enforce a permission and audit authenticated denials."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            required_permissions = [perm] if isinstance(perm, str) else perm
            if not request.user.has_perms(required_permissions):
                log(
                    request,
                    "access.denied",
                    target=request.path,
                    outcome="denied",
                    permission=perm,
                )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
