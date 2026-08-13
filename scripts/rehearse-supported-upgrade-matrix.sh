#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
current_version=$(tr -d '[:space:]' < "$repository_root/VERSION")

run_case() {
  source_version=$1
  source_ref=$2
  shift 2
  resolved_version=$(git -C "$repository_root" show "$source_ref:VERSION" | tr -d '[:space:]')
  [ "$resolved_version" = "$source_version" ] || {
    echo "Supported-upgrade source $source_ref resolved to $resolved_version, expected $source_version." >&2
    exit 1
  }
  echo "Rehearsing supported TekDocs $source_version ($source_ref) -> $current_version"
  "$@"
}

run_case 0.1.3 147d00c env TEKDOCS_UPGRADE_FROM_REF=147d00c \
  "$repository_root/scripts/rehearse-upgrade.sh"
run_case 0.2.9 58520f1 env TEKDOCS_DOCUMENTATION_UPGRADE_FROM_REF=58520f1 \
  TEKDOCS_DOCUMENTATION_UPGRADE_FROM_VERSION=0.2.9 \
  "$repository_root/scripts/rehearse-documentation-upgrade.sh"
run_case 0.3.12 e11743f env TEKDOCS_INVENTORY_UPGRADE_FROM_REF=e11743f \
  TEKDOCS_INVENTORY_UPGRADE_FROM_VERSION=0.3.12 \
  "$repository_root/scripts/rehearse-inventory-upgrade.sh"
run_case 0.4.9 2f15710 env TEKDOCS_NETWORK_UPGRADE_FROM_REF=2f15710 \
  TEKDOCS_NETWORK_UPGRADE_FROM_VERSION=0.4.9 \
  "$repository_root/scripts/rehearse-network-upgrade.sh"
run_case 0.5.9 f15b6a7 env TEKDOCS_PORTAL_NOTIFICATION_UPGRADE_FROM_REF=f15b6a7 \
  TEKDOCS_PORTAL_NOTIFICATION_UPGRADE_FROM_VERSION=0.5.9 \
  "$repository_root/scripts/rehearse-portal-notification-upgrade.sh"
run_case 0.6.9 fc8aec7 env TEKDOCS_INTEGRATION_UPGRADE_FROM_REF=fc8aec7 \
  TEKDOCS_INTEGRATION_UPGRADE_FROM_VERSION=0.6.9 \
  TEKDOCS_INTEGRATION_UPGRADE_TO_VERSION="$current_version" \
  "$repository_root/scripts/rehearse-integration-upgrade.sh"
run_case 0.7.13 8fdde2d env TEKDOCS_CERTIFICATION_UPGRADE_FROM_REF=8fdde2d \
  TEKDOCS_CERTIFICATION_UPGRADE_FROM_VERSION=0.7.13 \
  "$repository_root/scripts/rehearse-compliance-monitoring-upgrade.sh"
run_case 0.8.0 557a976 env TEKDOCS_CERTIFICATION_UPGRADE_FROM_REF=557a976 \
  TEKDOCS_CERTIFICATION_UPGRADE_FROM_VERSION=0.8.0 \
  "$repository_root/scripts/rehearse-compliance-monitoring-upgrade.sh"

echo "Supported-minor upgrade matrix passed through TekDocs $current_version"
