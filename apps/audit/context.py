from contextvars import ContextVar

current_request = ContextVar("audit_current_request", default=None)
