# Testing

Install development dependencies and run the Django test suite:

```sh
python -m pip install -r requirements/dev.txt
python manage.py test
```

Run coverage reporting with:

```sh
coverage run manage.py test
coverage report
```

The suite covers role seeding and reconciliation, protected routes, audit
append-only behavior, account lifecycle and escalation safeguards, catalog and
inventory CRUD, member ownership, policy auditing, issue/return/renew rules,
reservation queue and expiry, fine payments and waivers, reporting and CSV
formula injection, login throttling, and demo workflows. Run the complete suite
after adding or changing a service; targeted service tests live in
`tests/test_membership_circulation.py`.

Coverage reporting includes each app's `services.py` plus the shared permission
helpers and mixins. The target is at least 85% across these files. Use
`coverage report -m` to inspect branches needing additional tests.
