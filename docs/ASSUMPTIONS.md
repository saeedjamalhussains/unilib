# Assumptions

- The empty `unilib` directory is the intended project root.
- Development uses SQLite unless `DATABASE_URL` is a PostgreSQL URL.
- The foundation pins Django 5.2.18, the latest Django 5.2 LTS patch available
  for this project's specified support line at implementation time.
- Authentication and account creation are staff-controlled; no public
  registration route is provided.
- Role-specific dashboard behavior and access policies will be added with the
  RBAC and domain phases.
- Until each domain app/model exists, `seed_roles` registers its matrix
  permissions against that app's `rolecapability` content type. This lets
  permissions and groups be seeded from the canonical matrix in Phase 2; later
  domain model permissions can use the same app label/codenames.
- The role matrix keeps `accounts.manage_users` and `accounts.assign_roles`
  administrator-only. Librarians' narrower student/faculty account-management
  access is authorized through `membership.manage_members`; their first role
  assignment is limited to those member roles during account creation.
- ISBN input accepts ISBN-10 and ISBN-13 with optional hyphens or spaces and
  validates the standard check digit. The catalog form stores a normalized,
  separator-free value.
- Catalog records referenced by titles and titles referenced by physical
  copies cannot be deleted; users must retain referenced records.
- Students and faculty see title availability but not accession numbers or
  shelf locations; detailed copy records are shown to inventory staff only.
