#!/bin/sh
set -eu

shard=${1:-}
repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-postgres-${shard:-unknown}.XXXXXX")
environment_file="$work_directory/postgres-shard.env"
project_name="tekdocs_postgres_${shard:-unknown}_$$"
coverage_directory="$repository_root/artifacts/postgres-coverage/$shard"
matrix_file="apps/core/tests/test_permission_idor_matrix.py"

shard_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "PostgreSQL test shard $shard failed; recent database and migration logs follow." >&2
    shard_compose logs --no-color --tail=120 db migrate >&2 || true
  fi
  shard_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

case "$shard" in
  route-access)
    set -- "$matrix_file::test_every_authenticated_route_denies_anonymous_and_non_member"
    ;;
  route-methods)
    set -- \
      "$matrix_file::test_every_cataloged_mutation_method_denies_read_only_members" \
      "$matrix_file::test_identifier_routes_reject_malformed_uuid_paths_without_entering_a_view"
    ;;
  route-session)
    set -- \
      "$matrix_file::test_every_unsafe_route_rejects_a_session_without_csrf" \
      "$matrix_file::test_every_cataloged_privileged_mutation_method_requires_mfa"
    ;;
  remaining)
    remaining_files=$(find "$repository_root/backend/apps" -path '*/tests/test_*.py' -type f \
      ! -name 'test_permission_idor_matrix.py' -print | sort | sed "s|$repository_root/backend/||")
    # The five large matrix functions run in the other shards. Selecting the
    # remainder by exclusion automatically includes any new matrix test.
    # shellcheck disable=SC2086
    set -- $remaining_files "$matrix_file" -k \
      "not test_every_authenticated_route_denies_anonymous_and_non_member and not test_every_cataloged_mutation_method_denies_read_only_members and not test_identifier_routes_reject_malformed_uuid_paths_without_entering_a_view and not test_every_unsafe_route_rejects_a_session_without_csrf and not test_every_cataloged_privileged_mutation_method_requires_mfa"
    ;;
  runtime)
    set -- \
      apps/core/tests/test_migration_stabilization.py::test_legacy_scope_helper_privileges_reverse_and_reapply \
      apps/core/tests/test_workspaces.py::test_runtime_role_workspace_routes_enforce_assigned_client_boundary \
      apps/accounts/tests/test_client_portal_boundary.py::test_runtime_role_client_portal_context_is_exactly_organization_scoped \
      apps/accounts/tests/test_client_portal_boundary.py::test_runtime_role_can_accept_client_invitation \
      apps/core/tests/test_scoping.py::test_runtime_role_scoped_queries_compose_with_database_workspace_isolation \
      apps/core/tests/test_runtime_rls.py::test_runtime_organization_scope_requires_system_principal_to_stage_tenant_person_identity \
      apps/core/tests/test_runtime_rls.py::test_runtime_role_administrator_can_create_and_reopen_fail_closed_organization \
      apps/core/tests/test_runtime_rls.py::test_runtime_role_request_enforces_assigned_only_entity_search_and_mentions \
      apps/core/tests/test_runtime_rls.py::test_runtime_role_preserves_request_actor_and_system_outbox_principal \
      apps/core/tests/test_runtime_rls.py::test_runtime_client_member_sees_only_its_organization_anchor_and_system_scope_restores_actor \
      apps/core/tests/test_runtime_rls.py::test_runtime_entity_anchors_require_entitled_user_or_explicit_system_principal \
      apps/core/tests/test_webhooks.py::test_inbound_signature_replay_tampering_and_expiration
    ;;
  *)
    echo "Usage: $0 {route-access|route-methods|route-session|remaining|runtime}" >&2
    exit 2
    ;;
esac

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

echo "Starting isolated PostgreSQL test shard: $shard"
shard_compose build --quiet migrate
shard_compose up -d db valkey mailpit --wait
shard_compose run --rm migrate

if [ "$shard" = "runtime" ]; then
  shard_compose run --rm migrate pytest "$@" --durations=25
else
  mkdir -p "$coverage_directory"
  chmod 0777 "$coverage_directory"
  coverage_file="$coverage_directory/coverage.$shard"
  rm -f "$coverage_file"
  shard_compose run --rm \
    -v "$coverage_directory:/coverage" \
    -e "COVERAGE_FILE=/coverage/coverage.$shard" \
    migrate pytest "$@" --cov --cov-report= --cov-fail-under=0 --durations=25
  test -s "$coverage_file"
  echo "PostgreSQL test shard $shard wrote $coverage_file"
fi

echo "PostgreSQL test shard $shard passed"
