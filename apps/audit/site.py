from django.contrib.admin import AdminSite


class LibraryAdminSite(AdminSite):
    site_header = "University Library administration"
    site_title = "Library administration"
    index_title = "Administration"

    def has_permission(self, request):
        user = request.user
        return bool(
            user.is_active
            and (
                user.is_superuser
                or user.groups.filter(name="Administrator").exists()
            )
        )


admin_site = LibraryAdminSite()
