# Deployment Guide - Epicor-HubSpot Integration

This guide covers deploying the integration to Azure Functions and local development setup.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Azure Functions Deployment](#azure-functions-deployment)
- [Configuration](#configuration)
- [Testing](#testing)
- [Monitoring](#monitoring)

---

## Prerequisites

### Required Accounts & Access

-  Azure subscription with permissions to create Function Apps, Key Vault, and Storage
-  Epicor ERP access with API credentials
-  HubSpot account with Private App created
-  Python 3.9+ installed locally

### Required Tools

```bash
# Python 3.9 or higher
python --version

# pip (Python package manager)
pip --version

# Azure CLI (for Azure deployment)
az --version

# Azure Functions Core Tools (for local dev and deployment)
func --version

# Optional: virtualenv
pip install virtualenv
```

---

## Local Development

### 1. Clone Repository

```bash
git clone <repository-url>
cd epicor-hubspot-integration
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create `.env` file in project root:

```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required Variables:**

```ini
# Epicor Configuration
EPICOR_BASE_URL=https://your-epicor-instance.com/ERP11PROD
EPICOR_COMPANY=YOUR_COMPANY
EPICOR_USERNAME=your_username
EPICOR_PASSWORD=your_password
EPICOR_API_KEY=your_api_key

# HubSpot Configuration
HUBSPOT_API_KEY=your_private_app_token

# HubSpot Pipeline IDs (get from HubSpot UI)
HUBSPOT_QUOTES_PIPELINE_ID=your_quotes_pipeline_id
HUBSPOT_ORDERS_PIPELINE_ID=your_orders_pipeline_id

# Sync Configuration
SYNC_BATCH_SIZE=100
SYNC_MAX_RETRIES=3
LOG_LEVEL=INFO
ENVIRONMENT=development

# Feature Flags
SYNC_CUSTOMERS=true
SYNC_QUOTES=true
SYNC_ORDERS=true
```

### 5. Configure Sales Rep Mapping

Edit `config/sales_rep_mapping.json`:

```json
{
  "default_owner_id": null,
  "mappings": {
    "REP001": "hubspot_owner_id_1",
    "REP002": "hubspot_owner_id_2"
  }
}
```

**To get HubSpot Owner IDs:**
1. Go to HubSpot > Settings > Users & Teams
2. Click on user > Copy Owner ID from URL

### 6. Run Locally

```bash
# Run sync directly
python -m src.main

# With debug logging
LOG_LEVEL=DEBUG python -m src.main

# Run via Azure Functions Core Tools (uses local.settings.json)
func start
```

---

## Azure Functions Deployment

### Method 1: Deploy Script (Recommended)

```bash
# Deploy to Azure Functions
cd scripts && ./deploy.sh
```

The deploy script uses `func azure functionapp publish epicor-hubspot-sync-production` under the hood.

### Method 2: Azure Functions Core Tools (Manual)

#### Step 1: Create Azure Resources

Create the required Azure resources using the ARM template:

```bash
# Create resource group
az group create \
  --name epicor-hubspot-rg \
  --location canadacentral

# Deploy ARM template (creates Function App, Key Vault, Storage, App Insights)
az deployment group create \
  --resource-group epicor-hubspot-rg \
  --template-file azure/arm-template.json \
  --parameters environment=production
```

#### Step 2: Store Secrets in Azure Key Vault

**Important:** Do NOT store credentials as Function App application settings. Use Azure Key Vault instead.

Secrets are stored individually with hyphenated names:

```bash
# Set Key Vault name
KV_NAME="epicor-hs-kv-production"

# Store each secret individually
az keyvault secret set --vault-name $KV_NAME \
  --name "epicor-base-url" \
  --value "https://plpc-apperp.preformed.ca/ERP11PROD"

az keyvault secret set --vault-name $KV_NAME \
  --name "epicor-company" \
  --value "PLPC"

az keyvault secret set --vault-name $KV_NAME \
  --name "epicor-username" \
  --value "your_username"

az keyvault secret set --vault-name $KV_NAME \
  --name "epicor-password" \
  --value "your_password"

az keyvault secret set --vault-name $KV_NAME \
  --name "epicor-api-key" \
  --value "your_api_key"

az keyvault secret set --vault-name $KV_NAME \
  --name "hubspot-api-key" \
  --value "your_hubspot_token"

az keyvault secret set --vault-name $KV_NAME \
  --name "hubspot-quotes-pipeline-id" \
  --value "your_quotes_pipeline_id"

az keyvault secret set --vault-name $KV_NAME \
  --name "hubspot-orders-pipeline-id" \
  --value "your_orders_pipeline_id"
```

#### Step 3: Configure Function App Settings

1. Go to **Function App** in Azure Portal
2. Navigate to **Configuration** > **Application settings**
3. Add only these non-sensitive settings:

```
AZURE_KEYVAULT_URL = https://epicor-hs-kv-production.vault.azure.net/
LOG_LEVEL = INFO
ENVIRONMENT = production
SYNC_BATCH_SIZE = 100
SYNC_MAX_RETRIES = 3
SYNC_CUSTOMERS = true
SYNC_QUOTES = true
SYNC_ORDERS = true
```

4. Click **Save**

The Function App will automatically load credentials from Key Vault at runtime via Managed Identity.

#### Step 4: Deploy Function Code

```bash
# Publish to Azure Functions
func azure functionapp publish epicor-hubspot-sync-production
```

#### Step 5: Verify Deployment

1. Go to **Function App** in Azure Portal
2. Navigate to **Functions**
3. You should see two functions:
   - `scheduled_sync` - Timer Trigger (runs on cron schedule)
   - `manual_sync` - HTTP Trigger (for on-demand sync)
4. Click **manual_sync** > **Code + Test** > **Test/Run** to trigger a test

#### Test Event (Manual Sync via HTTP Trigger)

```json
{
  "operation": "full_sync"
}
```

### Project Files for Azure Functions

The following files support the Azure Functions v2 programming model:

- **`function_app.py`** - Main entry point with `scheduled_sync` (Timer Trigger) and `manual_sync` (HTTP Trigger)
- **`host.json`** - Azure Functions host configuration
- **`local.settings.json`** - Local development settings (gitignored)
- **`azure/arm-template.json`** - ARM template for provisioning Azure resources

---

## Configuration

### Getting HubSpot Pipeline IDs

1. Go to HubSpot > **Settings** > **Objects** > **Deals** > **Pipelines**
2. Click on your **Quotes** pipeline
3. Copy the ID from the URL:
   ```
   https://app.hubspot.com/contacts/12345/objects/0-3/pipelines/6789012
                                                                ^^^^^^^
                                                           This is the ID
   ```
4. Repeat for **Orders** pipeline
5. Update `.env` or Key Vault secrets

### Setting Up Scheduled Execution

The scheduled sync is built into the Azure Function as a Timer Trigger. It is defined in `function_app.py` and configured with a cron expression.

**Default schedule:** `0 0 7 * * *` (daily at 7:00 AM UTC)

To change the schedule:

1. Update the cron expression in `function_app.py` for the `scheduled_sync` function
2. Redeploy with `func azure functionapp publish epicor-hubspot-sync-production`

Alternatively, override via the `SYNC_SCHEDULE` application setting in the Function App configuration.

No external scheduling service (like EventBridge) is needed -- the Timer Trigger is built into Azure Functions.

---

## Testing

### Local Testing

```bash
# Run tests
pytest tests/ -v

# Run specific test
pytest tests/test_stage_logic.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Azure Functions Testing

#### Test via HTTP Trigger (Manual Sync)

```bash
# Full sync
curl -X POST "https://epicor-hubspot-sync-production.azurewebsites.net/api/manual_sync" \
  -H "Content-Type: application/json" \
  -d '{"operation": "full_sync"}'
```

#### Test Event (Customers Only)

```json
{
  "operation": "sync_customers"
}
```

#### Test Event (Quotes with Date Filter)

```json
{
  "operation": "sync_quotes",
  "filter": "EntryDate ge 2024-01-01"
}
```

---

## Monitoring

### Application Insights

All logs and telemetry are automatically sent to Application Insights:

1. Go to **Application Insights** in Azure Portal
2. Navigate to **Logs** (Log Analytics)
3. Query function execution traces:
   ```kusto
   traces
   | where operation_Name == "scheduled_sync" or operation_Name == "manual_sync"
   | order by timestamp desc
   | take 100
   ```

### Key Log Messages

```
 Success indicators:
- "CUSTOMER SYNC COMPLETE"
- "QUOTE SYNC COMPLETE"
- "FULL SYNC COMPLETE"
- " Created company"
- " Updated quote"

  Warning indicators:
- "Rep 'XXX' not mapped"
- "Company not found"
- "Stage update blocked"

 Error indicators:
- "Failed to fetch"
- "Transformation error"
- " Failed to create"
```

### Application Insights Metrics (Custom)

Add custom metrics in code:

```python
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import aggregation, measure, stats, view

# Define a measure
sync_count_measure = measure.MeasureInt("customers_synced", "Number of customers synced", "customers")

# Create and register a view
sync_count_view = view.View(
    "customers_synced_count",
    "Count of customers synced",
    [],
    sync_count_measure,
    aggregation.CountAggregation()
)

stats.stats.view_manager.register_view(sync_count_view)
```

### Alerts

Create Azure Monitor Alerts for:

- Function execution failures
- Execution duration > threshold
- Custom sync failure metrics

Configure alerts in **Azure Portal** > **Monitor** > **Alerts** > **New alert rule**, targeting the Function App resource.

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

---

## Security Best Practices

### 1. Secrets Management (REQUIRED for Azure Functions)

The integration automatically loads credentials from Azure Key Vault when running in Azure Functions.
This is the recommended and default approach - **do NOT store credentials in Function App application settings**.

#### Step 1: Create the Key Vault and Store Secrets

Secrets are stored individually with hyphenated names:

```bash
KV_NAME="epicor-hs-kv-production"

# Create Key Vault (if not already created by ARM template)
az keyvault create \
  --name $KV_NAME \
  --resource-group epicor-hubspot-rg \
  --location canadacentral

# Store each secret
az keyvault secret set --vault-name $KV_NAME --name "epicor-base-url" --value "https://plpc-apperp.preformed.ca/ERP11PROD"
az keyvault secret set --vault-name $KV_NAME --name "epicor-company" --value "PLPC"
az keyvault secret set --vault-name $KV_NAME --name "epicor-username" --value "your_epicor_username"
az keyvault secret set --vault-name $KV_NAME --name "epicor-password" --value "your_epicor_password"
az keyvault secret set --vault-name $KV_NAME --name "epicor-api-key" --value "your_epicor_api_key"
az keyvault secret set --vault-name $KV_NAME --name "hubspot-api-key" --value "your_hubspot_private_app_token"
az keyvault secret set --vault-name $KV_NAME --name "hubspot-quotes-pipeline-id" --value "your_quotes_pipeline_id"
az keyvault secret set --vault-name $KV_NAME --name "hubspot-orders-pipeline-id" --value "your_orders_pipeline_id"
```

#### Step 2: Verify Secrets

```bash
# List all secrets in the vault
az keyvault secret list --vault-name $KV_NAME --output table

# Retrieve a specific secret (be careful - outputs sensitive data)
az keyvault secret show --vault-name $KV_NAME --name "epicor-base-url" --query 'value' --output tsv
```

#### Step 3: Update Secrets (when credentials change)

```bash
az keyvault secret set --vault-name $KV_NAME \
  --name "epicor-password" \
  --value "new_password_value"
```

#### How It Works

1. Function App starts with only `AZURE_KEYVAULT_URL` application setting configured
2. `function_app.py` calls `load_secrets_from_cloud()` before loading settings
3. Secrets are fetched from Key Vault using Managed Identity and set as environment variables
4. `Settings()` loads from environment variables via Pydantic
5. Credentials are never stored in Function App configuration

#### Key Vault Name Convention

The ARM template uses environment-specific Key Vault names:
- Production: `epicor-hs-kv-production`
- Staging: `epicor-hs-kv-staging`
- Development: `epicor-hs-kv-development`

This is set automatically via the `AZURE_KEYVAULT_URL` application setting.

### 2. Managed Identity & RBAC

The Function App uses a system-assigned Managed Identity to authenticate with Key Vault. No client secrets or certificates are needed.

Required RBAC role assignments:

```bash
# Get the Function App's Managed Identity principal ID
PRINCIPAL_ID=$(az functionapp identity show \
  --name epicor-hubspot-sync-production \
  --resource-group epicor-hubspot-rg \
  --query principalId --output tsv)

# Grant Key Vault Secrets User role
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $PRINCIPAL_ID \
  --scope /subscriptions/<sub-id>/resourceGroups/epicor-hubspot-rg/providers/Microsoft.KeyVault/vaults/epicor-hs-kv-production

# Grant Storage Blob Data Contributor role (for Azure Blob Storage)
az role assignment create \
  --role "Storage Blob Data Contributor" \
  --assignee $PRINCIPAL_ID \
  --scope /subscriptions/<sub-id>/resourceGroups/epicor-hubspot-rg/providers/Microsoft.Storage/storageAccounts/<storage-account>
```

### 3. Network Security

- Use VNet Integration for Epicor access if required
- Configure Network Security Groups to allow only necessary outbound traffic
- Use Private Endpoints for Key Vault and Storage if needed

---

## Rollback Procedure

If deployment fails:

1. **Redeploy previous version:**
   ```bash
   # Roll back to a previous deployment using git
   git checkout <previous-commit-hash>
   func azure functionapp publish epicor-hubspot-sync-production
   ```

   Alternatively, if deployment slots are configured:
   ```bash
   # Swap staging slot back to production
   az functionapp deployment slot swap \
     --name epicor-hubspot-sync-production \
     --resource-group epicor-hubspot-rg \
     --slot staging
   ```

2. **Restore application settings** from previous version if changed

3. **Check Application Insights logs** for error details:
   ```kusto
   exceptions
   | where timestamp > ago(1h)
   | order by timestamp desc
   ```

4. **Test with small dataset** before full sync

---

## Production Checklist

Before going live:

- [ ] **Azure Key Vault secrets stored** with all credentials:
  - Key Vault `epicor-hs-kv-production` created
  - Contains: `epicor-base-url`, `epicor-company`, `epicor-username`, `epicor-password`, `epicor-api-key`
  - Contains: `hubspot-api-key`, `hubspot-quotes-pipeline-id`, `hubspot-orders-pipeline-id`
- [ ] Sales rep mapping file updated with real data (`config/sales_rep_mapping.json`)
- [ ] HubSpot pipeline IDs verified and added to Key Vault
- [ ] ARM template deployed (`az deployment group create --template-file azure/arm-template.json`)
- [ ] Function App Managed Identity granted Key Vault access
- [ ] Function code deployed (`func azure functionapp publish epicor-hubspot-sync-production`)
- [ ] Test sync with small dataset (trigger `manual_sync` HTTP endpoint)
- [ ] Application Insights alerts configured
- [ ] Function App timeout appropriate for data volume (default: 10 min)
- [ ] Function App plan appropriate for data volume (Consumption or Premium)
- [ ] Timer Trigger schedule configured (default: daily at 7:00 AM UTC -- cron `0 0 7 * * *`)
- [ ] Error notification setup (Azure Monitor action groups / email)
- [ ] Documentation shared with team

---

*Last Updated: February 26, 2026*
