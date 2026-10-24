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

The suite covers the account-role boundaries, member-account scoping,
last-active-administrator safeguards, audited account lifecycle changes, and
role-forgery attempts through the staff interface. It also tests catalog search
and CRUD permissions, ISBN validation, inventory status auditing, and protected
deletes.
