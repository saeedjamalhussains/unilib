from apps.audit.context import current_request


class AuditRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_request.set(request)
        try:
            response = self.get_response(request)
            if response.status_code == 403 and not getattr(
                request, "_audit_access_denied", False
            ):
                from apps.audit.api import log

                log(
                    request,
                    "access.denied",
                    target=request.path,
                    outcome="denied",
                )
            return response
        finally:
            current_request.reset(token)
