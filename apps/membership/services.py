from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.services import create_account
from apps.audit.api import log
from apps.membership.models import LibraryPolicy, MemberProfile


def _profile_snapshot(profile):
    return {
        "user_id": profile.user_id,
        "university_id": profile.university_id,
        "department": profile.department,
        "member_type": profile.member_type,
        "status": profile.status,
        "membership_expiry": profile.membership_expiry.isoformat(),
    }


@transaction.atomic
def save_member(actor: User, profile: MemberProfile) -> MemberProfile:
    if not actor.has_perm("membership.manage_members"):
        raise PermissionDenied("You are not allowed to manage member profiles.")
    created = profile.pk is None
    before = (
        None
        if created
        else _profile_snapshot(MemberProfile.objects.select_for_update().get(pk=profile.pk))
    )
    profile.full_clean()
    profile.save()
    after = _profile_snapshot(profile)
    if before != after:
        log(
            actor,
            "membership.member_created" if created else "membership.member_updated",
            target=profile,
            before=before,
            after=after,
        )
    return profile


@transaction.atomic
def register_member(
    actor: User,
    profile: MemberProfile,
    *,
    username: str,
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
) -> MemberProfile:
    """Create a user, assign its member role, and create its member profile atomically."""
    if profile.member_type not in MemberProfile.MemberType.values:
        raise ValidationError({"member_type": "Select a valid member type."})
    role = "Student" if profile.member_type == MemberProfile.MemberType.STUDENT else "Faculty"
    user = create_account(
        actor,
        username=username,
        email=email,
        password=password,
        role=role,
        first_name=first_name,
        last_name=last_name,
    )
    profile.user = user
    return save_member(actor, profile)


def _policy_snapshot(policy):
    return {
        field.name: str(getattr(policy, field.name))
        for field in policy._meta.fields
        if field.name not in ("id", "created_at", "updated_at")
    }


@transaction.atomic
def save_policy(actor: User, policy: LibraryPolicy) -> LibraryPolicy:
    if not actor.has_perm("membership.manage_policy"):
        raise PermissionDenied("Only administrators may manage library policies.")
    created = policy.pk is None
    before = (
        None
        if created
        else _policy_snapshot(LibraryPolicy.objects.select_for_update().get(pk=policy.pk))
    )
    policy.full_clean()
    policy.save()
    after = _policy_snapshot(policy)
    if before != after:
        log(
            actor,
            "membership.policy_created" if created else "membership.policy_updated",
            target=policy,
            before=before,
            after=after,
        )
    return policy


def get_policy(member_type: str) -> LibraryPolicy:
    try:
        return LibraryPolicy.objects.get(member_type=member_type)
    except LibraryPolicy.DoesNotExist as exc:
        raise ValidationError("No library policy is configured for this member type.") from exc
