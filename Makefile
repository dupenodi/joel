.PHONY: setup hydra check-0

PYTHON ?= python3.12

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r api/requirements.txt

hydra:
	./scripts/run_hydra.sh

check-0:
	.venv/bin/python scripts/check_0_env.py
