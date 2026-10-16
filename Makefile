.PHONY: test deploy smoke smoke-dlq destroy fmt

test:
	.venv/bin/python -m pytest -q tests

deploy:
	./scripts/deploy.sh

smoke:
	python3 scripts/smoke_test.py

smoke-dlq:
	python3 scripts/smoke_test.py --with-dlq

destroy:
	./scripts/destroy.sh

fmt:
	terraform -chdir=terraform fmt
