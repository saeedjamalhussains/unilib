# Architecture

The application uses Django's request/response stack and server-rendered templates.
The `accounts` app owns the custom authentication user model. The `core` app
contains shared views and access-control mixins. Domain apps call their own
services from thin views; persistence is through the Django ORM.

Settings are split into a shared `base.py` and explicit development and
production modules. SQLite is the default development database. Set
`DATABASE_URL` to a PostgreSQL URL to configure PostgreSQL.

## Foundation status

Phase 1 establishes the project, custom user, auth entry points, and base
template. Phase 2 adds role seeding and audit logging. Phase 3 adds secure
account and role administration. Phase 4 adds catalog and physical inventory
services and server-rendered management views. Membership and circulation
services are added in later phases.

## RBAC and audit core

The canonical role/capability mapping is
[`apps/accounts/role_matrix.py`](../apps/accounts/role_matrix.py); use
`python manage.py render_rbac_matrix` to regenerate its documentation and
`python manage.py seed_roles` to reconcile the Django groups. Permissions for
domain apps that have not been introduced yet are registered under a temporary
`rolecapability` content type for that app label and are reused by the seeder.

`LibraryPermissionRequiredMixin` and `library_permission_required` return a
login redirect for anonymous requests and a 403 for authenticated users without
permission; authenticated denials are audited. The audit API writes append-only
events, captures request IP/user-agent metadata through middleware, and records
authentication signals. The Django admin site separately limits entry to
superusers and members of the `Administrator` group.

## Role administration

The `/manage/users/` interface uses Django's `accounts.manage_users` permission
for administrators. Librarians use `membership.manage_members` only to create,
edit, list, and deactivate Faculty and Student accounts; they cannot edit
privileged accounts or assign roles to existing accounts. `accounts.services`
is the enforcement boundary for initial role assignment, account changes,
activation, deactivation, and deletion. Role updates replace any other library
role group, and final-active-administrator operations are rejected
transactionally.

## Catalog and inventory

`catalog` owns bibliographic titles and their authors, publishers, and
categories. Search and detail views require `catalog.view_book`; catalog
maintenance requires `catalog.manage_catalog`, while title deletion requires
`catalog.delete_book`. `inventory` owns `BookCopy` records; changes go through
its service layer and require `inventory.manage_copies`. Catalog and copy
mutations write audit events from their services. A title with copies cannot
be deleted, and copy-to-book references use `PROTECT`.
