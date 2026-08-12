SHELL := /bin/sh

.PHONY: test-notifications notification-upgrade-rehearsal

.PHONY: bootstrap build up down logs check test test-auth-abuse test-client-portal-boundary test-outbox test-policy test-isolation test-rls test-organizations test-workspaces test-people test-sites test-custom-fields test-relationships test-recovery test-stabilization test-certification test-documentation-certification test-publication-control test-credential-references test-catalogs test-inventory test-inventory-certification test-commercial test-networks test-network-stabilization test-network-certification test-secret-files test-markdown test-compose test-e2e test-e2e-all test-e2e-live security release-gate schema migrations mail-test compose-doctor production-image-rehearsal clean-install-rehearsal upgrade-rehearsal client-portal-upgrade-rehearsal outbox-upgrade-rehearsal documentation-backup-rehearsal documentation-upgrade-rehearsal publication-control-upgrade-rehearsal inventory-backup-rehearsal inventory-upgrade-rehearsal network-backup-rehearsal network-upgrade-rehearsal

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
	./scripts/check-supply-chain-pins.sh
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo rhysd/actionlint:1.7.7@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend ruff check .
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend mypy apps tekdocs
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations --check --dry-run
	./scripts/check-openapi.sh
	./scripts/frontend-gate.sh check

test:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend pytest --cov
	./scripts/frontend-gate.sh test

test-auth-abuse:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend pytest apps/accounts/tests -q

test-client-portal-boundary:
	docker compose run --rm migrate pytest apps/accounts/tests/test_client_portal_boundary.py apps/accounts/tests/test_invitations.py apps/accounts/tests/test_invitation_acceptance.py apps/accounts/tests/test_auth_session.py apps/core/tests/test_portal_documents.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-outbox:
	docker compose run --rm migrate pytest apps/core/tests/test_outbox.py -q
	docker compose run --rm migrate pytest apps/accounts/tests/test_invitations.py apps/accounts/tests/test_invitation_acceptance.py -q
	docker compose run --rm migrate pytest apps/core/tests/test_documents.py -q
	docker compose run --rm migrate pytest apps/core/tests/test_runtime_rls.py -q

test-notifications:
	docker compose run --rm migrate pytest apps/core/tests/test_notifications.py -q
	docker compose run --rm migrate pytest apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py -q
	./scripts/frontend-gate.sh test

test-policy:
	docker compose run --rm migrate pytest apps/accounts/tests/test_access_control.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_scoping.py apps/core/tests/test_workspaces.py apps/core/tests/test_relationships.py apps/core/tests/test_permission_idor_matrix.py -q

test-isolation:
	docker compose run --rm migrate pytest apps/core/tests/test_scoping.py apps/core/tests/test_permission_idor_matrix.py -q

test-rls:
	docker compose run --rm migrate pytest apps/core/tests/test_runtime_rls.py -q

test-organizations:
	docker compose run --rm migrate pytest apps/core/tests/test_organizations.py apps/core/tests/test_scoping.py -q

test-workspaces:
	docker compose run --rm migrate pytest apps/core/tests/test_workspaces.py apps/core/tests/test_scoping.py -q

test-people:
	docker compose run --rm migrate pytest apps/core/tests/test_people.py apps/core/tests/test_scoping.py -q

test-sites:
	docker compose run --rm migrate pytest apps/core/tests/test_sites.py apps/core/tests/test_people.py apps/core/tests/test_scoping.py -q

test-custom-fields:
	docker compose run --rm migrate pytest apps/core/tests/test_custom_fields.py apps/core/tests/test_scoping.py -q

test-relationships:
	docker compose run --rm migrate pytest apps/core/tests/test_relationships.py apps/core/tests/test_scoping.py -q

test-recovery:
	docker compose run --rm migrate pytest apps/core/tests/test_recycle_bin.py apps/core/tests/test_audit_immutability.py apps/core/tests/test_permission_idor_matrix.py -q

test-stabilization:
	docker compose run --rm migrate pytest apps/accounts/tests/test_access_control.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_scoping.py apps/core/tests/test_workspaces.py apps/core/tests/test_relationships.py apps/core/tests/test_recycle_bin.py apps/core/tests/test_audit_immutability.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py apps/core/tests/test_stabilization_performance.py -q

test-certification:
	docker compose run --rm migrate pytest apps/core/tests/test_entity_rbac_certification.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py -q

test-documentation-certification:
	docker compose run --rm migrate pytest apps/core/tests/test_documents.py apps/core/tests/test_attachment_security.py apps/core/tests/test_rendering.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_stabilization_performance.py -q

test-publication-control:
	docker compose run --rm migrate pytest apps/core/tests/test_documents.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-credential-references:
	docker compose run --rm migrate pytest apps/core/tests/test_credential_references.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py -q

test-catalogs:
	docker compose run --rm migrate pytest apps/core/tests/test_catalogs.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-inventory:
	docker compose run --rm migrate pytest apps/core/tests/test_inventory.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-inventory-certification:
	docker compose run --rm migrate pytest apps/core/tests/test_catalogs.py apps/core/tests/test_inventory.py apps/core/tests/test_inventory_stabilization.py apps/core/tests/test_commercial.py apps/core/tests/test_credential_references.py apps/core/tests/test_attachment_security.py apps/core/tests/test_relationships.py apps/core/tests/test_recycle_bin.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-commercial:
	docker compose run --rm migrate pytest apps/core/tests/test_commercial.py apps/core/tests/test_recycle_bin.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-networks:
	docker compose run --rm migrate pytest apps/core/tests/test_network_inventory.py apps/core/tests/test_network_addressing.py apps/core/tests/test_network_endpoints.py apps/core/tests/test_network_services.py apps/core/tests/test_network_circuits.py apps/core/tests/test_netbox_reconciliation.py apps/core/tests/test_network_transfer.py apps/core/tests/test_relationships.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-network-stabilization:
	docker compose run --rm migrate pytest apps/core/tests/test_network_stabilization.py -q -s

test-network-certification: test-networks test-network-stabilization
	./scripts/frontend-gate.sh test

test-secret-files:
	docker compose run --rm migrate pytest apps/core/tests/test_secret_files.py apps/core/tests/test_health.py apps/core/tests/test_email_settings.py -q

test-markdown:
	docker compose run --rm migrate pytest apps/core/tests/test_rendering.py -q
	./scripts/frontend-gate.sh test

test-compose:
	docker compose -f compose.yml -f compose.test.yml up -d --build --wait
	curl --fail --silent http://localhost:$${TEKDOCS_PORT:-3200}/api/v1/health/ready
	curl --fail --silent http://127.0.0.1:$${MAILPIT_UI_PORT:-8025}/readyz
	docker compose exec -T backend python manage.py send_test_email operator-test@example.invalid
	docker compose exec -T backend python manage.py check --deploy
	docker compose run --rm migrate pytest --cov
	./scripts/check-compose-provenance.sh

test-e2e:
	./scripts/rehearse-browser-e2e.sh chromium

test-e2e-all:
	./scripts/rehearse-browser-e2e.sh all

test-e2e-live:
	./scripts/rehearse-live-workspace-e2e.sh

security:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false backend pip-audit
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false backend bandit -c pyproject.toml -r apps tekdocs
	./scripts/frontend-gate.sh audit
	docker run --rm -v "$(CURDIR):/src:ro" -v /dev/null:/src/.env:ro zricethezav/gitleaks:latest@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f detect --source=/src --no-git --no-banner --redact
	docker build --target production -t tekdocs-backend-security ./backend
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest@sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-backend-security
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest@sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-frontend
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest@sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 axllent/mailpit:edge@sha256:bccf2e68cfe67695cd6ed4d73e9def6100ea48a262901b1945befbed91cceec7

release-gate: check test test-auth-abuse test-client-portal-boundary test-outbox test-notifications test-compose test-policy test-isolation test-rls test-organizations test-workspaces test-people test-sites test-custom-fields test-relationships test-recovery test-stabilization test-certification test-documentation-certification test-publication-control test-credential-references test-catalogs test-inventory test-inventory-certification test-commercial test-network-certification test-secret-files test-markdown test-e2e-all test-e2e-live security production-image-rehearsal clean-install-rehearsal upgrade-rehearsal client-portal-upgrade-rehearsal outbox-upgrade-rehearsal notification-upgrade-rehearsal documentation-upgrade-rehearsal documentation-backup-rehearsal publication-control-upgrade-rehearsal inventory-upgrade-rehearsal inventory-backup-rehearsal network-upgrade-rehearsal network-backup-rehearsal

compose-doctor:
	./scripts/check-compose-provenance.sh

production-image-rehearsal:
	./scripts/rehearse-production-image.sh

clean-install-rehearsal:
	./scripts/rehearse-clean-install.sh

upgrade-rehearsal:
	./scripts/rehearse-upgrade.sh

client-portal-upgrade-rehearsal:
	./scripts/rehearse-client-portal-upgrade.sh

outbox-upgrade-rehearsal:
	./scripts/rehearse-outbox-upgrade.sh

notification-upgrade-rehearsal:
	./scripts/rehearse-notification-upgrade.sh

documentation-backup-rehearsal:
	./scripts/rehearse-documentation-backup.sh

documentation-upgrade-rehearsal:
	./scripts/rehearse-documentation-upgrade.sh

publication-control-upgrade-rehearsal:
	./scripts/rehearse-publication-control-upgrade.sh

inventory-backup-rehearsal:
	./scripts/rehearse-inventory-backup.sh

inventory-upgrade-rehearsal:
	./scripts/rehearse-inventory-upgrade.sh

network-backup-rehearsal:
	./scripts/rehearse-network-backup.sh

network-upgrade-rehearsal:
	./scripts/rehearse-network-upgrade.sh

schema:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py spectacular --validate > backend/openapi.yml

migrations:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations

mail-test:
	@test -n "$(EMAIL_TO)" || (echo "Usage: make mail-test EMAIL_TO=you@example.com" && exit 2)
	docker compose exec -T backend python manage.py send_test_email "$(EMAIL_TO)"
