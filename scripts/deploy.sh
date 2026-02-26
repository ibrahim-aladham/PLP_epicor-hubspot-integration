#!/bin/bash
# Azure Functions deployment script for Epicor-HubSpot Integration

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="${AZURE_FUNCTION_APP_NAME:-epicor-hubspot-sync-production}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-epicor-hubspot-rg}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Epicor-HubSpot Integration Deployment${NC}"
echo -e "${GREEN}(Azure Functions)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Step 1: Check prerequisites
echo -e "${YELLOW}[1/4]${NC} Checking prerequisites..."

if ! command -v func &> /dev/null; then
    echo -e "${RED}Error: Azure Functions Core Tools (func) not found.${NC}"
    echo "Install: npm install -g azure-functions-core-tools@4 --unsafe-perm true"
    exit 1
fi

if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI (az) not found.${NC}"
    echo "Install: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Verify logged in
if ! az account show &> /dev/null; then
    echo -e "${RED}Error: Not logged into Azure CLI. Run 'az login' first.${NC}"
    exit 1
fi

echo -e "${GREEN}Prerequisites OK${NC}"
echo ""

# Step 2: Deploy ARM template (if requested)
if [[ "$1" == "--deploy-infra" ]]; then
    echo -e "${YELLOW}[2/4]${NC} Deploying ARM template..."
    echo "Resource Group: ${RESOURCE_GROUP}"

    # Create resource group if it doesn't exist
    az group create \
        --name "${RESOURCE_GROUP}" \
        --location "eastus" \
        --output none 2>/dev/null || true

    az deployment group create \
        --resource-group "${RESOURCE_GROUP}" \
        --template-file azure/arm-template.json \
        --parameters environmentName=production \
        --output table

    echo -e "${GREEN}ARM template deployed${NC}"
    echo ""
else
    echo -e "${YELLOW}[2/4]${NC} Skipping infrastructure deployment (use --deploy-infra to deploy ARM template)"
    echo ""
fi

# Step 3: Publish function app
echo -e "${YELLOW}[3/4]${NC} Publishing to Azure Functions..."
echo "Function App: ${APP_NAME}"

func azure functionapp publish "${APP_NAME}" --python

echo -e "${GREEN}Function app published${NC}"
echo ""

# Step 4: Verify deployment
echo -e "${YELLOW}[4/4]${NC} Verifying deployment..."

az functionapp show \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query "{Name:name, State:state, DefaultHostName:defaultHostName}" \
    --output table

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Test the function: curl https://${APP_NAME}.azurewebsites.net/api/sync?code=<function-key>"
echo "  2. View logs: az monitor app-insights query --app ${APP_NAME}-insights-production --analytics-query 'traces | order by timestamp desc | take 50'"
echo "  3. Check timer trigger: az functionapp function show --name ${APP_NAME} --resource-group ${RESOURCE_GROUP} --function-name scheduled_sync"
echo ""
