def log(request_or_none, action, target=None, outcome="success", **metadata):
    from apps.audit.api import log as write_audit_event

    return write_audit_event(
        request_or_none,
        action,
        target=target,
        outcome=outcome,
        **metadata,
    )