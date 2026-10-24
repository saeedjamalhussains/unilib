# University Library Management System

A secure, server-rendered university library built with Django 5.2 LTS. Django
groups and permissions enforce the Administrator, Librarian, Faculty, and
Student roles. Sensitive domain operations are handled by transactional
services and written to an append-only audit log.

## Features

- Catalog search, book details, and physical-copy inventory.
- Staff-maintained member profiles and administrator-managed library policies.
- Issue, return, and renewal workflows with loan limits, due dates, grace periods,
  and fine blocking.
- FIFO reservations, expiring holds, overdue fines, partial payments, and
  administrator waivers.
- Role-specific dashboards, operational reports, formula-safe CSV exports, and
  a searchable administrator audit log.
- Django admin is restricted to superusers and Administrators. State-changing
  browser actions use POST and CSRF protection.

## Quick start

Requires Python 3.12 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env
```

Edit `.env` and set a private `DJANGO_SECRET_KEY`. Then initialize the database
and role groups:

```sh
python manage.py migrate
python manage.py seed_roles
```

Start the development server:

```sh
python manage.py runserver
```

The app is available at `http://127.0.0.1:8000/`. On first login, users can
change their password at `/accounts/password_change/`.

## Configuration

`django-environ` reads environment variables and the optional project-root
`.env` file. Important settings:

| Variable | Purpose |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` for development; use `config.settings.prod` for production |
| `DJANGO_SECRET_KEY` | Required for production; replace the development default |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames in production |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted HTTPS origins |
| `DATABASE_URL` | PostgreSQL connection URL; unset uses SQLite |
| `SQLITE_PATH` | Optional SQLite database path |
| `TIME_ZONE` | Django timezone, default `UTC` |
| `DJANGO_EMAIL_BACKEND` | Email backend for queued notices; defaults to the console backend |

Production uses PostgreSQL when `DATABASE_URL` is set and enables HTTPS redirects,
secure cookies, HSTS, content-type protection, and clickjacking protection.
Install `requirements/prod.txt`, configure a production-grade shared cache for
multi-worker deployments, and run `python manage.py check --deploy` before
release.

## Roles

The canonical role-to-permission mapping is maintained in
[`apps/accounts/role_matrix.py`](./apps/accounts/role_matrix.py). It generates
[`docs/RBAC_MATRIX.md`](./docs/RBAC_MATRIX.md) and is reconciled by
`python manage.py seed_roles`.

| Role | Typical capabilities |
|---|---|
| Administrator | All library operations, user/role administration, policies, waivers, reports, and audit |
| Librarian | Catalog/inventory/member maintenance, circulation, reservations, payments, reports |
| Faculty | Catalog search, own loans and renewals, own reservations and fines |
| Student | Catalog search, own loans and renewals, own reservations and fines |

See the generated matrix for the authoritative per-permission list.

## Development commands

```sh
make install
make migrate
make run
make test
make coverage
make lint
python manage.py seed_roles
python manage.py render_rbac_matrix
python manage.py expire_reservations
```

For additional design decisions and verification details, see
[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md),
[`docs/ASSUMPTIONS.md`](./docs/ASSUMPTIONS.md), and
[`docs/TESTING.md`](./docs/TESTING.md).
