from apps.accounts.services import is_administrator, is_librarian
from apps.core.mixins import LibraryPermissionRequiredMixin


class AccountManagementRequiredMixin(LibraryPermissionRequiredMixin):
    permission_required = "accounts.manage_users"

    def has_permission(self):
        user = self.request.user
        if is_administrator(user):
            return user.is_superuser or user.has_perm("accounts.manage_users")
        return is_librarian(user) and user.has_perm("membership.manage_members")
