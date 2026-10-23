from django.contrib.auth.mixins import PermissionRequiredMixin


class LibraryPermissionRequiredMixin(PermissionRequiredMixin):
    raise_exception = True


class OwnedByMemberMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.owned_by(self.request.user)
