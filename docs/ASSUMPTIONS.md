# Assumptions

- The empty `unilib` directory is the intended project root.
- Development uses SQLite unless `DATABASE_URL` is a PostgreSQL URL.
- The foundation pins Django 5.2.18, the latest Django 5.2 LTS patch available
  for this project's specified support line at implementation time.
- Authentication and account creation are staff-controlled; no public
  registration route is provided.
- Role-specific dashboard behavior and access policies will be added with the
  RBAC and domain phases.
