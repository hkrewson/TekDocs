SHELL := /bin/sh

.PHONY: bootstrap build up down logs check test test-compose test-e2e security release-gate schema migrations

bootstrap:
	./scripts/bootstrap-env.sh .env
	npm --prefix frontend install --no-audit --no-fund
	docker compose build

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs --tail=150

check:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend ruff check .
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend mypy apps tekdocs
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations --check --dry-run
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend run test
	npm --prefix frontend run build

test:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend pytest --cov
	npm --prefix frontend run test

test-compose:
	docker compose -f compose.yml -f compose.test.yml up -d --build --wait
	curl --fail --silent http://localhost:$${TEKDOCS_PORT:-3200}/api/v1/health/ready
	docker compose exec -T backend python manage.py check --deploy
	docker compose exec -T backend pytest --cov

test-e2e:
	npm --prefix frontend run test:e2e

security:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false backend pip-audit
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false backend bandit -c pyproject.toml -r apps tekdocs
	npm --prefix frontend audit --omit=dev --audit-level=high
	docker run --rm -v "$(CURDIR):/src:ro" -v /dev/null:/src/.env:ro zricethezav/gitleaks:latest detect --source=/src --no-git --no-banner --redact
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-backend
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-frontend

release-gate: check test test-compose test-e2e security

schema:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py spectacular --file openapi.yml --validate

migrations:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations
