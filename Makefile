.PHONY: install migrate run test coverage lint

install:
	python -m pip install -r requirements/dev.txt

migrate:
	python manage.py migrate

run:
	python manage.py runserver

test:
	python manage.py test

coverage:
	coverage run manage.py test
	coverage report

lint:
	ruff check .
