from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone


@login_required
def home(request):
    user = request.user
    context = {"role_names": set(user.groups.values_list("name", flat=True))}
    if user.has_perm("circulation.view_own_loans"):
        from apps.circulation.models import Loan
        from apps.fines.models import Fine
        from apps.membership.models import MemberProfile
        from apps.reservations.models import Reservation

        profile = MemberProfile.objects.filter(user=user).first()
        context["profile"] = profile
        if profile:
            context["current_loans"] = (
                Loan.objects.owned_by(user)
                .filter(returned_at__isnull=True)
                .select_related("copy__book")
                .order_by("due_date")[:10]
            )
            context["ready_reservations"] = (
                Reservation.objects.owned_by(user)
                .filter(status=Reservation.Status.READY)
                .select_related("book")
            )
            context["outstanding_fines"] = (
                Fine.objects.owned_by(user)
                .filter(status=Fine.Status.OUTSTANDING)
                .select_related("loan__copy__book")
                .prefetch_related("payments")
            )
    if user.has_perm("circulation.view_all_loans"):
        from apps.circulation.models import Loan
        from apps.reservations.models import Reservation

        today = timezone.localdate()
        context["due_today"] = Loan.objects.filter(
            returned_at__isnull=True, due_date=today
        ).select_related("copy__book", "member")[:10]
        context["overdue_loans"] = (
            Loan.objects.filter(returned_at__isnull=True, due_date__lt=today)
            .select_related("copy__book", "member")
            .order_by("due_date")[:10]
        )
        context["pending_reservations"] = Reservation.objects.filter(
            status=Reservation.Status.PENDING
        ).select_related("book", "member")[:10]
    if user.has_perm("audit.view_auditlog"):
        from apps.accounts.models import User
        from apps.audit.models import AuditLog
        from apps.catalog.models import Book
        from apps.circulation.models import Loan
        from apps.inventory.models import BookCopy
        from apps.membership.models import MemberProfile

        context["system_counts"] = {
            "users": User.objects.count(),
            "members": MemberProfile.objects.count(),
            "books": Book.objects.count(),
            "copies": BookCopy.objects.count(),
            "active_loans": Loan.objects.filter(returned_at__isnull=True).count(),
        }
        context["recent_audit_events"] = AuditLog.objects.select_related("actor")[:10]
    return render(request, "core/home.html", context)
