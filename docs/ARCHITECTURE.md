# Architecture

The application uses Django's request/response stack and server-rendered templates.
The `accounts` app owns the custom authentication user model. The `core` app
contains shared views and access-control mixins. Domain apps call their own
services from thin views; persistence is through the Django ORM.

Settings are split into a shared `base.py` and explicit development and
production modules. SQLite is the default development database. Set
`DATABASE_URL` to a PostgreSQL URL to configure PostgreSQL.

## Foundation status

Phase 1 establishes the project, custom user, auth entry points, base template,
and shared permission mixin. Domain services, role seeding, and audit logging
are introduced in their corresponding implementation phases.
