# University Library Management System

A secure, server-rendered university library application built with Django.
Role-based access control and audit logging are the central design goals.

## Setup

Requires Python 3.12 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

The current foundation has login, logout, password reset/change pages, and the
custom `accounts.User` model. There are no demo credentials yet because account
creation is intentionally staff-controlled.

Seed the four role groups and their permissions, then regenerate the matrix
documentation when changing the canonical role data:

```sh
python manage.py seed_roles
python manage.py render_rbac_matrix
```

## Configuration

Settings default to `config.settings.dev`. Set `DJANGO_SETTINGS_MODULE` to
`config.settings.prod` for deployment. `DATABASE_URL` accepts a PostgreSQL URL;
otherwise SQLite is used. Copy `.env.example` and replace the development
secret before deployment. Do not commit `.env`.

## Development commands

```sh
make migrate
make run
make test
make coverage
make lint
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/TESTING.md](docs/TESTING.md), and [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).
