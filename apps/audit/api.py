from django.contrib.contenttypes.models import ContentType

from apps.audit.context import current_request
from apps.audit.models import AuditLog


def log(request_or_none, action, target=None, outcome="success", **metadata):
    """Append one audit event using the active request, if available."""
    request = request_or_none or current_request.get()
    user = getattr(request, "user", None) if request is not None else None
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None

    target_type = ""
    target_id = ""
    target_repr = ""
    if target is not None:
        if isinstance(target, str):
            target_repr = target[:255]
        else:
            content_type = ContentType.objects.get_for_model(target)
            target_type = f"{content_type.app_label}.{content_type.model}"
            target_id = str(getattr(target, "pk", ""))[:100]
            target_repr = str(target)[:255]

    remote_addr = request.META.get("REMOTE_ADDR") if request is not None else None
    if remote_addr:
        from ipaddress import ip_address

        try:
            remote_addr = str(ip_address(remote_addr))
        except ValueError:
            remote_addr = None

    return AuditLog.objects.create(
        actor=user,
        actor_repr=str(user)[:255] if user is not None else "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_repr=target_repr,
        ip_address=remote_addr,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:512]
        if request is not None
        else "",
        metadata=_json_safe(metadata),
        outcome=outcome,
    )


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
