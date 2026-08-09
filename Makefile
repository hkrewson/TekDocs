SHELL := /bin/sh

.PHONY: bootstrap build up down logs check test test-auth-abuse test-policy test-isolation test-organizations test-workspaces test-people test-sites test-custom-fields test-relationships test-compose test-e2e test-e2e-all test-e2e-live security release-gate schema migrations mail-test compose-doctor production-image-rehearsal clean-install-rehearsal upgrade-rehearsal

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
	./scripts/check-version.sh
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend ruff check .
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend mypy apps tekdocs
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations --check --dry-run
	./scripts/check-openapi.sh
	./scripts/frontend-gate.sh check

test:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend pytest --cov
	./scripts/frontend-gate.sh test

test-auth-abuse:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend pytest apps/accounts/tests -q

test-policy:
	docker compose exec -T backend pytest apps/accounts/tests/test_access_control.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_scoping.py -q

test-isolation:
	docker compose exec -T backend pytest apps/core/tests/test_scoping.py -q

test-organizations:
	docker compose exec -T backend pytest apps/core/tests/test_organizations.py apps/core/tests/test_scoping.py -q

test-workspaces:
	docker compose exec -T backend pytest apps/core/tests/test_workspaces.py apps/core/tests/test_scoping.py -q

test-people:
	docker compose exec -T backend pytest apps/core/tests/test_people.py apps/core/tests/test_scoping.py -q

test-sites:
	docker compose exec -T backend pytest apps/core/tests/test_sites.py apps/core/tests/test_people.py apps/core/tests/test_scoping.py -q

test-custom-fields:
	docker compose exec -T backend pytest apps/core/tests/test_custom_fields.py apps/core/tests/test_scoping.py -q

test-relationships:
	docker compose exec -T backend pytest apps/core/tests/test_relationships.py apps/core/tests/test_scoping.py -q

test-compose:
	docker compose -f compose.yml -f compose.test.yml up -d --build --wait
	curl --fail --silent http://localhost:$${TEKDOCS_PORT:-3200}/api/v1/health/ready
	curl --fail --silent http://127.0.0.1:$${MAILPIT_UI_PORT:-8025}/readyz
	docker compose exec -T backend python manage.py send_test_email operator-test@example.invalid
	docker compose exec -T backend python manage.py check --deploy
	docker compose exec -T backend pytest --cov
	./scripts/check-compose-provenance.sh

test-e2e:
	./scripts/rehearse-browser-e2e.sh chromium

test-e2e-all:
	./scripts/rehearse-browser-e2e.sh all

test-e2e-live:
	./scripts/rehearse-live-workspace-e2e.sh

security:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false backend pip-audit
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false backend bandit -c pyproject.toml -r apps tekdocs
	./scripts/frontend-gate.sh audit
	docker run --rm -v "$(CURDIR):/src:ro" -v /dev/null:/src/.env:ro zricethezav/gitleaks:latest detect --source=/src --no-git --no-banner --redact
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-backend
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-frontend
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 axllent/mailpit:edge@sha256:bccf2e68cfe67695cd6ed4d73e9def6100ea48a262901b1945befbed91cceec7

release-gate: check test test-auth-abuse test-compose test-policy test-isolation test-organizations test-workspaces test-people test-sites test-custom-fields test-relationships test-e2e-all test-e2e-live security production-image-rehearsal clean-install-rehearsal upgrade-rehearsal

compose-doctor:
	./scripts/check-compose-provenance.sh

production-image-rehearsal:
	./scripts/rehearse-production-image.sh

clean-install-rehearsal:
	./scripts/rehearse-clean-install.sh

upgrade-rehearsal:
	./scripts/rehearse-upgrade.sh

schema:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py spectacular --validate > backend/openapi.yml

migrations:
	docker compose run --rm --no-deps -e TEKDOCS_RUN_MIGRATIONS=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations

mail-test:
	@test -n "$(EMAIL_TO)" || (echo "Usage: make mail-test EMAIL_TO=you@example.com" && exit 2)
	docker compose exec -T backend python manage.py send_test_email "$(EMAIL_TO)"
