from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.accounts.models import User as LibraryUser
from apps.accounts.role_matrix import ROLES
from apps.audit.api import log

MEMBER_ACCOUNT_ROLES = ("Faculty", "Student")


def is_administrator(user: LibraryUser) -> bool:
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.groups.filter(name="Administrator").exists()
    )


def is_librarian(user: LibraryUser) -> bool:
    return (
        user.is_authenticated
        and user.is_active
        and user.groups.filter(name="Librarian").exists()
    )


def account_role_names(user: LibraryUser) -> set[str]:
    return set(user.groups.filter(name__in=ROLES).values_list("name", flat=True))


def _can_manage_accounts(actor, target, *, initial_role=False):
    if is_administrator(actor) and (
        actor.is_superuser or actor.has_perm("accounts.manage_users")
    ):
        return True
    if not is_librarian(actor) or not actor.has_perm("membership.manage_members"):
        return False
    if target is None:
        return True
    roles = account_role_names(target)
    return roles in (
        {"Faculty"},
        {"Student"},
    ) or (initial_role and not roles)


def _require_account_management(actor, target=None, *, initial_role=False):
    if not actor.is_authenticated or not _can_manage_accounts(
        actor, target, initial_role=initial_role
    ):
        raise PermissionDenied("You are not allowed to manage this account.")


def _require_role_assignment(actor, target, role, *, initial_assignment=False):
    if role not in ROLES:
        raise ValidationError({"role": "Select a valid library role."})
    if not actor.is_authenticated:
        raise PermissionDenied("Authentication is required to assign a role.")
    if actor.pk == target.pk:
        raise PermissionDenied("You cannot change your own library role.")

    current_roles = account_role_names(target)
    is_initial_assignment = initial_assignment and not current_roles
    if is_administrator(actor):
        if not (actor.is_superuser or actor.has_perm("accounts.assign_roles")):
            raise PermissionDenied("You are not allowed to assign library roles.")
    elif (
        not is_initial_assignment
        or role not in MEMBER_ACCOUNT_ROLES
        or not is_librarian(actor)
        or not actor.has_perm("membership.manage_members")
    ):
        raise PermissionDenied("Only administrators may change library roles.")


def _has_another_active_administrator(target):
    User = get_user_model()
    administrator_ids = list(
        User.objects.select_for_update()
        .filter(is_active=True, groups__name="Administrator")
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    return any(user_id != target.pk for user_id in administrator_ids)


def _lock_account_rows(actor: LibraryUser, target: LibraryUser) -> tuple[LibraryUser, LibraryUser]:
    """Lock role-sensitive rows in one consistent order across lifecycle changes."""
    User = get_user_model()
    administrator_ids = set(
        User.objects.filter(is_active=True, groups__name="Administrator").values_list(
            "pk", flat=True
        )
    )
    administrator_ids.update((actor.pk, target.pk))
    users = {
        user.pk: user
        for user in User.objects.select_for_update()
        .filter(pk__in=administrator_ids)
        .order_by("pk")
    }
    if actor.pk not in users or target.pk not in users:
        raise User.DoesNotExist("The account no longer exists.")
    return users[actor.pk], users[target.pk]


@transaction.atomic
def assign_role(
    actor: LibraryUser,
    target: LibraryUser,
    role: str,
    *,
    initial_assignment: bool = False,
) -> LibraryUser:
    """Assign exactly one library role, subject to escalation safeguards."""
    _require_role_assignment(
        actor,
        target,
        role,
        initial_assignment=initial_assignment,
    )
    actor, target = _lock_account_rows(actor, target)
    _require_role_assignment(
        actor,
        target,
        role,
        initial_assignment=initial_assignment,
    )
    current_roles = account_role_names(target)
    if current_roles == {role}:
        return target
    if (
        "Administrator" in current_roles
        and role != "Administrator"
        and target.is_active
        and not _has_another_active_administrator(target)
    ):
        raise ValidationError("The last active administrator cannot be demoted.")

    role_groups = Group.objects.filter(name__in=ROLES)
    target.groups.remove(*role_groups.exclude(name=role))
    target.groups.add(Group.objects.get(name=role))
    log(
        actor,
        "accounts.role_assigned" if not current_roles else "accounts.role_changed",
        target=target,
        previous_roles=sorted(current_roles),
        role=role,
    )
    return target


@transaction.atomic
def create_account(
    actor: LibraryUser,
    *,
    username: str,
    email: str,
    password: str,
    role: str,
    first_name: str = "",
    last_name: str = "",
) -> LibraryUser:
    """Create an account and set its initial role in the same transaction."""
    _require_account_management(actor, initial_role=True)
    if role not in ROLES:
        raise ValidationError({"role": "Select a valid library role."})
    if not is_administrator(actor) and role not in MEMBER_ACCOUNT_ROLES:
        raise PermissionDenied("Librarians may create only student or faculty accounts.")

    User = get_user_model()
    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )
    user.full_clean(exclude=("password",))
    validate_password(password, user=user)
    user.set_password(password)
    user.save()
    assign_role(actor, user, role, initial_assignment=True)
    log(actor, "accounts.user_created", target=user, role=role)
    return user


@transaction.atomic
def update_account(
    actor: LibraryUser,
    target: LibraryUser,
    *,
    username: str,
    email: str,
    first_name: str = "",
    last_name: str = "",
    role: str | None = None,
) -> LibraryUser:
    """Update non-role account details without permitting role or active changes."""
    _require_account_management(actor, target)
    if role:
        actor, target = _lock_account_rows(actor, target)
    else:
        target = get_user_model().objects.select_for_update().get(pk=target.pk)
    _require_account_management(actor, target)
    before = {
        "username": target.username,
        "email": target.email,
        "first_name": target.first_name,
        "last_name": target.last_name,
    }
    target.username = username
    target.email = email
    target.first_name = first_name
    target.last_name = last_name
    target.full_clean(exclude=("password", "last_login", "date_joined"))
    target.save(update_fields=("username", "email", "first_name", "last_name"))
    if role:
        assign_role(actor, target, role)
    after = {
        "username": target.username,
        "email": target.email,
        "first_name": target.first_name,
        "last_name": target.last_name,
    }
    if before != after:
        log(actor, "accounts.user_updated", target=target, before=before, after=after)
    return target


@transaction.atomic
def deactivate_user(actor: LibraryUser, target: LibraryUser) -> LibraryUser:
    """Deactivate an account without allowing self-lockout or loss of final admin."""
    if not actor.is_authenticated:
        raise PermissionDenied("Authentication is required to deactivate accounts.")
    if actor.pk == target.pk:
        raise PermissionDenied("You cannot deactivate your own account.")
    _require_account_management(actor, target)
    actor, target = _lock_account_rows(actor, target)
    if actor.pk == target.pk:
        raise PermissionDenied("You cannot deactivate your own account.")
    _require_account_management(actor, target)
    if not target.is_active:
        return target
    if "Administrator" in account_role_names(target) and not _has_another_active_administrator(
        target
    ):
        raise ValidationError("The last active administrator cannot be deactivated.")
    target.is_active = False
    target.save(update_fields=("is_active",))
    log(actor, "accounts.user_deactivated", target=target)
    return target


@transaction.atomic
def activate_user(actor: LibraryUser, target: LibraryUser) -> LibraryUser:
    """Activate an account within the actor's account-management scope."""
    if not actor.is_authenticated:
        raise PermissionDenied("Authentication is required to activate accounts.")
    _require_account_management(actor, target)
    actor, target = _lock_account_rows(actor, target)
    _require_account_management(actor, target)
    if target.is_active:
        return target
    target.is_active = True
    target.save(update_fields=("is_active",))
    log(actor, "accounts.user_activated", target=target)
    return target


@transaction.atomic
def delete_account(actor: LibraryUser, target: LibraryUser) -> None:
    """Delete an account only when actor and final-administrator rules allow it."""
    if not actor.is_authenticated:
        raise PermissionDenied("Authentication is required to delete accounts.")
    if actor.pk == target.pk:
        raise PermissionDenied("You cannot delete your own account.")
    if not is_administrator(actor) or not (
        actor.is_superuser or actor.has_perm("accounts.manage_users")
    ):
        raise PermissionDenied("Only administrators may delete accounts.")
    actor, target = _lock_account_rows(actor, target)
    if actor.pk == target.pk:
        raise PermissionDenied("You cannot delete your own account.")
    if not is_administrator(actor) or not (
        actor.is_superuser or actor.has_perm("accounts.manage_users")
    ):
        raise PermissionDenied("Only administrators may delete accounts.")
    if (
        target.is_active
        and "Administrator" in account_role_names(target)
        and not _has_another_active_administrator(target)
    ):
        raise ValidationError("The last active administrator cannot be deleted.")
    log(actor, "accounts.user_deleted", target=target)
    target.delete()


def account_list_for(
    actor: LibraryUser,
    queryset: QuerySet | None = None,
) -> QuerySet:
    """Return only accounts within the actor's account-management scope."""
    User = get_user_model()
    queryset = queryset if queryset is not None else User.objects.all()
    if is_administrator(actor):
        return queryset
    if is_librarian(actor) and actor.has_perm("membership.manage_members"):
        return queryset.filter(
            Q(groups__name="Faculty") | Q(groups__name="Student")
        ).distinct()
    raise PermissionDenied("You are not allowed to view managed accounts.")
