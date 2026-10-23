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
