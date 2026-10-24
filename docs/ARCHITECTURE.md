# Architecture

The system is a server-rendered Django application. Requests pass through
authentication, server-side permission checks, ownership-scoped querysets, and
audit middleware before domain services use the Django ORM. Django templates,
vendored Bootstrap, and small progressive-enhancement assets form the browser
layer. SQLite is used by default; `DATABASE_URL` configures PostgreSQL.

## Application boundaries

- `accounts`: custom user, login/password workflows, role administration, and
  account lifecycle services.
- `core`: shared permission mixins/decorators, dashboards, and common UI.
- `audit`: request context, append-only audit records, authentication signals,
  restricted admin registration, and audit viewer.
- `catalog` and `inventory`: bibliographic records and physical copies.
- `membership`: member profiles, ownership-scoped access, library policies,
  staff membership workflows, and eligibility settings.
- `circulation`: loan model and atomic issue, return, and renewal services.
- `reservations`: FIFO reservations, timed holds, notifications, and the
  idempotent `expire_reservations` command.
- `fines`: overdue fine records, partial payments, outstanding balances, and
  administrator waivers.
- `reports`: ORM-based inventory, circulation, loan, title popularity, and
  fine reports with formula-neutralized CSV export.

## Request security and RBAC

`apps/accounts/role_matrix.py` is the canonical matrix used by the role seeder,
generated permission documentation, and matrix tests. The seeder reconciles
each Django group exactly. Permissions for a domain without a concrete
permission-bearing model (currently reports) use an app-labelled `rolecapability`
content type; model-backed capabilities use their actual model content types.

`LibraryPermissionRequiredMixin` and `library_permission_required` redirect
anonymous requests to login and return an audited 403 to authenticated users
without permission. Mixed staff/member endpoints perform explicit permission
checks and identify their required permissions for the deny-by-default URL
test. Ownership-sensitive `Loan`, `Reservation`, `Fine`, and `MemberProfile`
querysets expose `owned_by(user)`; member-facing object access is always scoped
before lookup.

Account role assignment is centralized in `accounts.services.assign_role`.
Domain services own validation, atomic persistence, row locking where
concurrency matters, and audit events. State-changing views accept POST only
and rely on Django CSRF middleware. User-controlled output uses Django's
autoescaping.

## Audit and operational behavior

`audit.log()` is the common append-only audit API. Auth signals capture login,
failed login, and logout; services audit lifecycle and domain changes within
their database transaction. Middleware captures request IP and user agent and
records protected-endpoint 403s. The audit model refuses updates/deletes and is
read-only in the restricted Django admin.

The login throttle tracks failures by normalized username and remote address in
Django's configured cache. The default development cache is local memory;
production deployments with multiple workers should configure a shared cache.
The inactivity session timeout is 30 minutes.

Reservation-ready email is routed through Django's configured email backend
(console backend in development) and dispatched after the hold transaction
commits. Schedule `python manage.py expire_reservations` periodically in
production; repeated runs are safe.

## Configuration and data

`django-environ` loads environment variables and an optional project-root
`.env`. `config.settings.dev` selects local development behavior; production
requires a secret, host allow-list, and configured database. Migrations seed
default student and faculty policies. Run `seed_roles` after migrations; the
development-only `seed_demo_data` command is repeatable and never resets
existing demo-account passwords.

All domain data is accessed via the Django ORM. PostgreSQL row locks protect
checkout/payment/hold mutations; SQLite remains suitable for development and
automated functional tests.
