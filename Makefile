.PHONY: install generate seed test

install:
	pip install -r requirements.txt

generate:
	python -m src.generate

seed:
	python -m src.seed

test:
	pytest -q
