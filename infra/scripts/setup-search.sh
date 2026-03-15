#!/usr/bin/env bash
#
# Post-provisioning script: deploys Azure AI Search index, datasource, skillset, and indexer.
#
# Called automatically by `azd provision` via the postprovision hook,
# or can be run manually:
#   ./infra/scripts/setup-search.sh
#
# Expects the following environment variables (set by azd):
#   AZURE_SEARCH_SERVICE_NAME
#   AZURE_STORAGE_ACCOUNT_NAME
#   AZURE_STORAGE_CONTAINER_NAME
#   AZURE_AI_SERVICES_ENDPOINT
#   AZURE_RESOURCE_GROUP
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/../search-config"

# ── Resolve variables ─────────────────────────────────────────────
SEARCH_SERVICE="${AZURE_SEARCH_SERVICE_NAME:?Set AZURE_SEARCH_SERVICE_NAME}"
STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT_NAME:?Set AZURE_STORAGE_ACCOUNT_NAME}"
CONTAINER_NAME="${AZURE_STORAGE_CONTAINER_NAME:-wh-kb-docs}"
AI_ENDPOINT="${AZURE_AI_SERVICES_ENDPOINT:?Set AZURE_AI_SERVICES_ENDPOINT}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"

SEARCH_ENDPOINT="https://${SEARCH_SERVICE}.search.windows.net"
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Get an admin API key for the search service
API_KEY=$(az search admin-key show \
  --service-name "${SEARCH_SERVICE}" \
  --resource-group "${RESOURCE_GROUP}" \
  --query primaryKey -o tsv)

API_VERSION="2024-07-01"

echo "============================================"
echo "Setting up Azure AI Search"
echo "  Search:    ${SEARCH_ENDPOINT}"
echo "  Storage:   ${STORAGE_ACCOUNT}/${CONTAINER_NAME}"
echo "  AI:        ${AI_ENDPOINT}"
echo "============================================"
echo ""

# ── Helper: substitute placeholders and PUT a JSON config ──────────
deploy_config() {
  local config_file="$1"
  local resource_type="$2"
  local resource_name="$3"

  echo "→ Deploying ${resource_type}: ${resource_name}"

  # Substitute placeholders
  local body
  body=$(cat "${config_file}" \
    | sed "s|{{SUBSCRIPTION_ID}}|${SUBSCRIPTION_ID}|g" \
    | sed "s|{{RESOURCE_GROUP}}|${RESOURCE_GROUP}|g" \
    | sed "s|{{STORAGE_ACCOUNT_NAME}}|${STORAGE_ACCOUNT}|g" \
    | sed "s|{{STORAGE_CONTAINER_NAME}}|${CONTAINER_NAME}|g" \
    | sed "s|{{AI_SERVICES_ENDPOINT}}|${AI_ENDPOINT}|g" \
  )

  local url="${SEARCH_ENDPOINT}/${resource_type}/${resource_name}?api-version=${API_VERSION}"

  local http_code
  http_code=$(curl -s -o /tmp/search-deploy-response.json -w "%{http_code}" \
    -X PUT "${url}" \
    -H "Content-Type: application/json" \
    -H "api-key: ${API_KEY}" \
    -d "${body}")

  if [[ "${http_code}" =~ ^2 ]]; then
    echo "  ✓ ${resource_type}/${resource_name} deployed (HTTP ${http_code})"
  else
    echo "  ✗ Failed to deploy ${resource_type}/${resource_name} (HTTP ${http_code})"
    cat /tmp/search-deploy-response.json
    echo ""
    return 1
  fi
}

# ── Deploy in order: index → datasource → skillset → indexer ──────
deploy_config "${CONFIG_DIR}/index.json"      "indexes"     "wh-kb-docs-index"
deploy_config "${CONFIG_DIR}/datasource.json"  "datasources" "wh-kb-docs-datasource"
deploy_config "${CONFIG_DIR}/skillset.json"    "skillsets"   "wh-kb-docs-skillset"
deploy_config "${CONFIG_DIR}/indexer.json"     "indexers"    "wh-kb-docs-indexer"

echo ""
echo "✓ Search configuration deployed successfully."
echo ""
echo "Next steps:"
echo "  1. Upload documents:  python upload_docs.py --clean"
echo "  2. Run the indexer:   az search indexer run --name wh-kb-docs-indexer --service-name ${SEARCH_SERVICE} --resource-group ${RESOURCE_GROUP}"
