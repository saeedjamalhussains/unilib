# Assumptions

- The existing `unilib` directory is the project root.
- Django 5.2.18 is the pinned Django 5.2 LTS patch used for this implementation.
- SQLite is the development default. A PostgreSQL `DATABASE_URL` enables
  production database behavior and meaningful row-level locks.
- Settings use `django-environ` to read environment variables and the optional
  project-root `.env` file. Secrets are never committed.
- Library roles are Django groups. A member profile's `member_type` must match
  the account's Faculty or Student role; staff cannot change a user's role via
  the member-profile form.
- Librarians may create Faculty and Student accounts but cannot create or edit
  privileged accounts or change an existing user's role. Administrator role
  changes remain subject to the final-active-administrator safeguard.
- Default policy values are: Students may hold 5 active loans for 14 days, may
  renew twice for 7 days each, and may have 5 active reservations. Faculty may
  hold 10 active loans for 30 days, may renew three times for 14 days each, and
  may have 10 active reservations. Both policies use a one-day grace period,
  0.25 currency units per overdue day, a 72-hour hold, and type-specific fine
  caps and blocking thresholds; administrators can edit these values.
- A membership expiring today remains eligible through that local calendar
  date. Overdue fines start only after the configured grace period and are
  capped per loan.
- A pending reservation protects the last available copy from a non-reserving
  member. Ready reservations are attached to a specific held copy and fulfilled
  when that copy is issued to the matching member.
- If a return lookup by university ID matches more than one active loan, staff
  must retry with the accession number to avoid selecting the wrong copy.
- Hold-ready notifications use the configured Django email backend and are
  queued with `transaction.on_commit`; the default backend prints mail to the
  console. Configure a real backend separately before production delivery.
  The `expire_reservations` command is scheduled externally rather than through
  an additional scheduler dependency.
- Login throttling permits five failed submissions per remote-address and
  normalized-username pair, then returns HTTP 429 for 15 minutes. The default
  development cache is process-local; deployments with multiple workers must
  use a shared cache.
- Reports aggregate circulation by book category, so a title assigned to
  multiple categories contributes to each category's count. CSV formula
  prefixes are neutralized before download.
- Copy loss/damage charging beyond overdue assessment and fine adjustment
  workflows beyond payment and administrator waiver remain future extensions;
  no payment gateway, external notification service, barcode scanner, or SSO
  integration is included.
- Students and faculty see title availability but not accession numbers or
  shelf locations; detailed physical-copy records are shown to inventory staff
  only.
