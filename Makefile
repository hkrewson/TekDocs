SHELL := /bin/sh

BACKEND_IMAGE_GATES := check security \
	test test-localization test-api-contracts test-api-tokens test-webhooks test-integrations \
	test-integration-stabilization test-integration-validation test-monitoring-stabilization \
	test-compliance-catalogs test-compliance-monitoring-validation test-auth-abuse \
	test-client-portal-boundary test-outbox test-notifications test-notification-email \
	test-portal-notification-stabilization test-portal-notification-validation test-policy \
	test-isolation test-rls test-organizations test-workspaces test-people \
	test-sites test-custom-fields test-relationships test-recovery test-stabilization \
	test-public-beta-performance test-entity-rbac-validation test-documentation-validation \
	test-file-export-stabilization test-diagram-exports \
	test-publication-control test-credential-references test-catalogs test-inventory \
	test-inventory-validation test-commercial test-billing-foundation test-invoice-drafts test-invoice-delivery test-networks test-network-stabilization \
	test-network-validation test-secret-files test-markdown test-compose test-e2e test-e2e-all \
	test-browser-artifact-hygiene test-e2e-live

.PHONY: test-notifications test-notification-email test-portal-notification-stabilization test-portal-notification-validation notification-upgrade-rehearsal notification-mail-outage-rehearsal portal-notification-upgrade-rehearsal portal-notification-backup-rehearsal placement-audience-upgrade-rehearsal
.PHONY: test-compliance-catalogs test-compliance-monitoring-validation compliance-monitoring-upgrade-rehearsal compliance-monitoring-backup-rehearsal supported-recovery-rehearsal supported-upgrade-matrix test-localization test-public-beta-performance test-browser-artifact-hygiene external-security-review-gate wiki-check test-diagram-exports diagram-export-release-gate
.PHONY: backend-test-images $(BACKEND_IMAGE_GATES)

.PHONY: bootstrap build up down logs check test test-api-contracts test-api-tokens test-webhooks test-integrations test-integration-stabilization test-integration-validation test-monitoring-stabilization test-auth-abuse test-client-portal-boundary test-outbox test-policy test-isolation test-rls test-runtime-authorization test-organizations test-workspaces test-people test-sites test-custom-fields test-relationships test-recovery test-stabilization test-entity-rbac-validation test-documentation-validation test-file-export-stabilization file-export-release-gate test-publication-control test-credential-references test-catalogs test-inventory test-inventory-validation test-commercial test-billing-foundation test-invoice-drafts test-invoice-delivery test-networks test-network-stabilization test-network-validation test-secret-files test-markdown test-compose test-e2e test-e2e-all test-e2e-live security dast release-gate schema migrations mail-test compose-doctor production-image-rehearsal clean-install-rehearsal upgrade-rehearsal client-portal-upgrade-rehearsal outbox-upgrade-rehearsal documentation-backup-rehearsal documentation-upgrade-rehearsal file-export-upgrade-rehearsal publication-control-upgrade-rehearsal key-publication-upgrade-rehearsal inventory-backup-rehearsal inventory-upgrade-rehearsal network-backup-rehearsal network-upgrade-rehearsal integration-upgrade-rehearsal integration-validation-upgrade-rehearsal integration-backup-rehearsal monitoring-upgrade-rehearsal monitoring-backup-rehearsal compliance-monitoring-upgrade-rehearsal compliance-monitoring-backup-rehearsal

bootstrap:
	./scripts/bootstrap-env.sh .env
	npm --prefix frontend install --no-audit --no-fund
	docker compose build

build:
	docker compose build

backend-test-images:
	docker compose build backend migrate

$(BACKEND_IMAGE_GATES): backend-test-images

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs --tail=150

check:
	./scripts/check-version.sh
	./scripts/check-supply-chain-pins.sh
	./scripts/check-wiki.py
	./scripts/check-product-boundary.py
	./scripts/check-compose-config.sh
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo rhysd/actionlint:1.7.7@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend ruff check .
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend mypy apps tekdocs
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations --check --dry-run
	./scripts/check-openapi.sh
	./scripts/frontend-gate.sh check

external-security-review-gate:
	python3 scripts/check-external-security-review.py

wiki-check:
	./scripts/check-wiki.py $(if $(WIKI_CHECKOUT),--checkout "$(WIKI_CHECKOUT)")

test:
	docker compose run --rm migrate pytest --cov
	./scripts/frontend-gate.sh test

test-localization:
	docker compose run --rm migrate pytest apps/core/tests/test_email_settings.py apps/core/tests/test_notification_delivery_scheduling.py -q
	./scripts/frontend-gate.sh test

test-api-contracts:
	docker compose run --rm migrate pytest apps/core/tests/test_api_contracts.py -q
	./scripts/frontend-gate.sh check

test-api-tokens:
	docker compose run --rm migrate pytest apps/accounts/tests/test_api_tokens.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py -q
	./scripts/frontend-gate.sh test

test-webhooks:
	docker compose run --rm migrate pytest apps/core/tests/test_webhooks.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-integrations:
	docker compose run --rm migrate pytest apps/core/tests/test_microsoft_graph_provider.py apps/core/tests/test_halopsa_provider.py apps/core/tests/test_halopsa_integration.py apps/core/tests/test_ninjaone_provider.py apps/core/tests/test_ninjaone_integration.py apps/core/tests/test_integrations.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-integration-stabilization:
	docker compose run --rm migrate pytest apps/core/tests/test_microsoft_graph_provider.py apps/core/tests/test_halopsa_provider.py apps/core/tests/test_halopsa_integration.py apps/core/tests/test_ninjaone_provider.py apps/core/tests/test_ninjaone_integration.py apps/core/tests/test_integration_stabilization.py apps/core/tests/test_integrations.py apps/core/tests/test_webhooks.py apps/accounts/tests/test_api_tokens.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh check

test-integration-validation:
	docker compose run --rm migrate pytest apps/core/tests/test_microsoft_graph_provider.py apps/core/tests/test_halopsa_provider.py apps/core/tests/test_halopsa_integration.py apps/core/tests/test_ninjaone_provider.py apps/core/tests/test_ninjaone_integration.py apps/core/tests/test_api_contracts.py apps/accounts/tests/test_api_tokens.py apps/core/tests/test_webhooks.py apps/core/tests/test_integrations.py apps/core/tests/test_integration_stabilization.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-monitoring-stabilization:
	docker compose run --rm migrate pytest apps/core/tests/test_domains.py apps/core/tests/test_domain_monitoring_egress.py apps/core/tests/test_certificate_monitoring.py apps/core/tests/test_certificate_monitoring_egress.py apps/core/tests/test_monitoring_stabilization.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-compliance-catalogs:
	docker compose run --rm migrate pytest apps/core/tests/test_compliance_catalogs.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_entity_rbac_validation.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-compliance-monitoring-validation:
	docker compose run --rm migrate pytest apps/core/tests/test_compliance_catalogs.py apps/core/tests/test_domains.py apps/core/tests/test_domain_monitoring_egress.py apps/core/tests/test_certificate_monitoring.py apps/core/tests/test_certificate_monitoring_egress.py apps/core/tests/test_monitoring_stabilization.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_entity_rbac_validation.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-auth-abuse:
	docker compose run --rm migrate pytest apps/accounts/tests -q

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

test-notification-email:
	docker compose run --rm migrate pytest apps/core/tests/test_email.py apps/core/tests/test_notification_email.py apps/core/tests/test_notification_delivery_scheduling.py apps/core/tests/test_notifications.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-portal-notification-stabilization:
	docker compose run --rm migrate pytest apps/accounts/tests/test_client_portal_boundary.py apps/core/tests/test_portal_documents.py apps/core/tests/test_outbox.py apps/core/tests/test_notifications.py apps/core/tests/test_notification_email.py apps/core/tests/test_notification_delivery_scheduling.py apps/core/tests/test_portal_notification_stabilization.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-portal-notification-validation:
	docker compose run --rm migrate pytest apps/accounts/tests/test_client_portal_boundary.py apps/accounts/tests/test_invitations.py apps/accounts/tests/test_invitation_acceptance.py apps/accounts/tests/test_auth_session.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_documents.py apps/core/tests/test_portal_documents.py apps/core/tests/test_outbox.py apps/core/tests/test_notifications.py apps/core/tests/test_email.py apps/core/tests/test_notification_email.py apps/core/tests/test_notification_delivery_scheduling.py apps/core/tests/test_portal_notification_stabilization.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-policy:
	docker compose run --rm migrate pytest apps/accounts/tests/test_access_control.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_scoping.py apps/core/tests/test_workspaces.py apps/core/tests/test_relationships.py apps/core/tests/test_permission_idor_matrix.py -q

test-isolation:
	docker compose run --rm migrate pytest apps/core/tests/test_scoping.py apps/core/tests/test_permission_idor_matrix.py -q

test-rls:
	docker compose run --rm migrate pytest apps/core/tests/test_runtime_rls.py -q

test-runtime-authorization:
	./tests/rehearsals/rehearse-postgres-test-shard.sh runtime

test-organizations:
	docker compose run --rm migrate pytest apps/core/tests/test_organizations.py apps/core/tests/test_scoping.py -q

test-workspaces:
	docker compose run --rm migrate pytest apps/core/tests/test_capability_contract.py apps/core/tests/test_workspaces.py apps/core/tests/test_scoping.py -q

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

test-public-beta-performance:
	docker compose run --rm migrate pytest apps/core/tests/test_public_beta_capacity.py -m performance -q -s
	docker compose run --rm -e TEKDOCS_ENFORCE_LATENCY_BUDGETS=true migrate pytest apps/core/tests/test_stabilization_performance.py apps/core/tests/test_inventory_stabilization.py apps/core/tests/test_portal_notification_stabilization.py -q -s
	./scripts/frontend-gate.sh check
	./tests/rehearsals/rehearse-browser-performance.sh

test-entity-rbac-validation:
	docker compose run --rm migrate pytest apps/core/tests/test_entity_rbac_validation.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py -q

test-documentation-validation:
	docker compose run --rm migrate pytest apps/core/tests/test_documents.py apps/core/tests/test_attachment_security.py apps/core/tests/test_rendering.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_stabilization_performance.py -q

test-file-export-stabilization:
	docker compose run --rm migrate pytest apps/core/tests/test_documents.py apps/core/tests/test_attachment_security.py apps/accounts/tests/test_api_tokens.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py -q
	./scripts/frontend-gate.sh test

file-export-release-gate: check test-file-export-stabilization test-e2e-all test-e2e-live file-export-upgrade-rehearsal documentation-backup-rehearsal production-image-rehearsal security

test-diagram-exports:
	docker compose run --rm migrate pytest apps/core/tests/test_diagram_exports.py apps/core/tests/test_documents.py -q
	./tests/rehearsals/rehearse-diagram-exports.sh

diagram-export-release-gate: check test-diagram-exports test-e2e-all test-e2e-live file-export-upgrade-rehearsal documentation-backup-rehearsal production-image-rehearsal security

test-publication-control:
	docker compose run --rm migrate pytest apps/core/tests/test_documents.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-credential-references:
	docker compose run --rm migrate pytest apps/core/tests/test_credential_references.py apps/accounts/tests/test_custom_roles.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py -q

test-catalogs:
	docker compose run --rm migrate pytest apps/core/tests/test_catalogs.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-inventory:
	docker compose run --rm migrate pytest apps/core/tests/test_inventory.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-inventory-validation:
	docker compose run --rm migrate pytest apps/core/tests/test_catalogs.py apps/core/tests/test_inventory.py apps/core/tests/test_inventory_stabilization.py apps/core/tests/test_commercial.py apps/core/tests/test_credential_references.py apps/core/tests/test_attachment_security.py apps/core/tests/test_relationships.py apps/core/tests/test_recycle_bin.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-commercial:
	docker compose run --rm migrate pytest apps/core/tests/test_commercial.py apps/core/tests/test_recycle_bin.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-billing-foundation:
	docker compose run --rm migrate pytest apps/core/tests/test_money.py apps/core/tests/test_billing_foundation.py apps/core/tests/test_entity_rbac_validation.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-invoice-drafts:
	docker compose run --rm migrate pytest apps/core/tests/test_invoice_issue.py apps/core/tests/test_invoice_drafts.py apps/core/tests/test_money.py apps/core/tests/test_billing_foundation.py apps/core/tests/test_entity_rbac_validation.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-invoice-delivery:
	docker compose run --rm migrate pytest apps/core/tests/test_invoice_delivery.py apps/core/tests/test_invoice_issue.py apps/core/tests/test_invoice_drafts.py apps/core/tests/test_money.py apps/core/tests/test_billing_foundation.py apps/core/tests/test_entity_rbac_validation.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q
	./scripts/frontend-gate.sh test

test-networks:
	docker compose run --rm migrate pytest apps/core/tests/test_network_inventory.py apps/core/tests/test_network_addressing.py apps/core/tests/test_network_endpoints.py apps/core/tests/test_network_services.py apps/core/tests/test_network_circuits.py apps/core/tests/test_netbox_reconciliation.py apps/core/tests/test_network_transfer.py apps/core/tests/test_relationships.py apps/core/tests/test_permission_idor_matrix.py apps/core/tests/test_runtime_rls.py apps/core/tests/test_migration_stabilization.py -q

test-network-stabilization:
	docker compose run --rm migrate pytest apps/core/tests/test_network_stabilization.py -q -s

test-network-validation: test-networks test-network-stabilization
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
	./tests/rehearsals/rehearse-browser-e2e.sh chromium

test-e2e-all:
	./tests/rehearsals/rehearse-browser-e2e.sh all

test-browser-artifact-hygiene:
	./tests/rehearsals/test-browser-artifact-hygiene.sh

test-production-setup:
	./tests/rehearsals/test-production-setup.sh

test-e2e-live:
	./tests/rehearsals/rehearse-live-workspace-e2e.sh

security:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false backend pip-audit
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false backend bandit -c pyproject.toml -r apps tekdocs
	./scripts/frontend-gate.sh audit
	docker compose run --rm --no-deps --entrypoint node diagram-renderer check-licenses.mjs
	docker run --rm -v "$(CURDIR):/src:ro" -v /dev/null:/src/.env:ro zricethezav/gitleaks:latest@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f detect --source=/src --no-git --no-banner --redact
	docker build --target production -t tekdocs-backend-security ./backend
	docker run --rm -v "$(CURDIR)/scripts/check-python-licenses.py:/check-python-licenses.py:ro" tekdocs-backend-security python /check-python-licenses.py
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest@sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-backend-security
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest@sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-frontend
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest@sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 tekdocs-diagram-renderer
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$(CURDIR)/.trivyignore.yaml:/.trivyignore.yaml:ro" aquasec/trivy:latest@sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c image --scanners vuln --ignorefile /.trivyignore.yaml --severity HIGH,CRITICAL --exit-code 1 axllent/mailpit:edge@sha256:8ff5eae4b0873bbfe047f408e681a4e59885f819dcb891e5f424b46135191e1b

dast:
	TEKDOCS_RUN_DAST=true ./tests/rehearsals/rehearse-production-image.sh

release-gate: check test test-public-beta-performance test-api-tokens test-webhooks test-integrations test-integration-stabilization test-integration-validation test-monitoring-stabilization test-compliance-monitoring-validation test-auth-abuse test-client-portal-boundary test-outbox test-notifications test-notification-email test-portal-notification-validation test-compose test-policy test-isolation test-rls test-organizations test-workspaces test-people test-sites test-custom-fields test-relationships test-recovery test-stabilization test-entity-rbac-validation test-documentation-validation test-file-export-stabilization test-publication-control test-credential-references test-catalogs test-inventory test-inventory-validation test-commercial test-network-validation test-secret-files test-markdown test-e2e-all test-e2e-live security production-image-rehearsal clean-install-rehearsal upgrade-rehearsal client-portal-upgrade-rehearsal outbox-upgrade-rehearsal notification-upgrade-rehearsal notification-mail-outage-rehearsal portal-notification-upgrade-rehearsal portal-notification-backup-rehearsal documentation-upgrade-rehearsal documentation-backup-rehearsal file-export-upgrade-rehearsal publication-control-upgrade-rehearsal key-publication-upgrade-rehearsal placement-audience-upgrade-rehearsal inventory-upgrade-rehearsal inventory-backup-rehearsal network-upgrade-rehearsal network-backup-rehearsal integration-validation-upgrade-rehearsal integration-backup-rehearsal monitoring-upgrade-rehearsal monitoring-backup-rehearsal compliance-monitoring-upgrade-rehearsal compliance-monitoring-backup-rehearsal supported-recovery-rehearsal supported-upgrade-matrix
release-gate: test-compliance-catalogs

compose-doctor:
	./scripts/check-compose-provenance.sh

production-image-rehearsal:
	./tests/rehearsals/rehearse-production-image.sh

clean-install-rehearsal:
	./tests/rehearsals/rehearse-clean-install.sh

upgrade-rehearsal:
	./tests/rehearsals/rehearse-upgrade.sh

client-portal-upgrade-rehearsal:
	./tests/rehearsals/rehearse-client-portal-upgrade.sh

outbox-upgrade-rehearsal:
	./tests/rehearsals/rehearse-outbox-upgrade.sh

notification-upgrade-rehearsal:
	./tests/rehearsals/rehearse-notification-upgrade.sh

notification-mail-outage-rehearsal:
	./tests/rehearsals/rehearse-notification-mail-outage.sh

portal-notification-upgrade-rehearsal:
	./tests/rehearsals/rehearse-portal-notification-upgrade.sh

portal-notification-backup-rehearsal:
	./tests/rehearsals/rehearse-portal-notification-backup.sh

documentation-backup-rehearsal:
	./tests/rehearsals/rehearse-documentation-backup.sh

documentation-upgrade-rehearsal:
	./tests/rehearsals/rehearse-documentation-upgrade.sh

file-export-upgrade-rehearsal:
	./tests/rehearsals/rehearse-file-export-upgrade.sh

publication-control-upgrade-rehearsal:
	./tests/rehearsals/rehearse-publication-control-upgrade.sh

key-publication-upgrade-rehearsal:
	./tests/rehearsals/rehearse-key-publication-upgrade.sh

placement-audience-upgrade-rehearsal:
	./tests/rehearsals/rehearse-placement-audience-upgrade.sh

inventory-backup-rehearsal:
	./tests/rehearsals/rehearse-inventory-backup.sh

inventory-upgrade-rehearsal:
	./tests/rehearsals/rehearse-inventory-upgrade.sh

network-backup-rehearsal:
	./tests/rehearsals/rehearse-network-backup.sh

network-upgrade-rehearsal:
	./tests/rehearsals/rehearse-network-upgrade.sh

integration-upgrade-rehearsal:
	./tests/rehearsals/rehearse-integration-upgrade.sh

integration-validation-upgrade-rehearsal:
	TEKDOCS_INTEGRATION_UPGRADE_FROM_REF=fc8aec7 TEKDOCS_INTEGRATION_UPGRADE_FROM_VERSION=0.6.9 TEKDOCS_INTEGRATION_UPGRADE_TO_VERSION=$$(tr -d '[:space:]' < VERSION) ./tests/rehearsals/rehearse-integration-upgrade.sh

integration-backup-rehearsal:
	./tests/rehearsals/rehearse-integration-backup.sh

monitoring-upgrade-rehearsal:
	./tests/rehearsals/rehearse-monitoring-upgrade.sh

monitoring-backup-rehearsal:
	./tests/rehearsals/rehearse-monitoring-backup.sh

compliance-monitoring-upgrade-rehearsal:
	./tests/rehearsals/rehearse-compliance-monitoring-upgrade.sh

compliance-monitoring-backup-rehearsal:
	./tests/rehearsals/rehearse-compliance-monitoring-backup.sh

supported-recovery-rehearsal:
	./tests/rehearsals/rehearse-supported-recovery.sh

supported-upgrade-matrix:
	./tests/rehearsals/rehearse-supported-upgrade-matrix.sh

schema:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py spectacular --validate > backend/openapi.yml

migrations:
	docker compose run --rm --no-deps -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test backend python manage.py makemigrations

mail-test:
	@test -n "$(EMAIL_TO)" || (echo "Usage: make mail-test EMAIL_TO=you@example.com" && exit 2)
	docker compose exec -T backend python manage.py send_test_email "$(EMAIL_TO)"
