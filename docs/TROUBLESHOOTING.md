# Troubleshooting Guide - Epicor-HubSpot Integration

Common issues and solutions for the Epicor-HubSpot integration.

---

## Table of Contents

- [Connection Issues](#connection-issues)
- [Configuration Issues](#configuration-issues)
- [Sync Issues](#sync-issues)
- [Stage Logic Issues](#stage-logic-issues)
- [Data Mapping Issues](#data-mapping-issues)
- [Performance Issues](#performance-issues)
- [AWS Lambda Issues](#aws-lambda-issues)

---

## Connection Issues

### Issue: "Epicor connection test failed"

**Symptoms:**
```
ERROR: Epicor connection test failed
```

**Possible Causes & Solutions:**

1. **Incorrect Base URL**
   ```bash
   # Check EPICOR_BASE_URL in .env
   # Should be: https://your-domain.com/ERP11PROD
   # NOT: https://your-domain.com/ERP11PROD/  (no trailing slash)
   ```

2. **Invalid Credentials**
   ```bash
   # Verify credentials in Epicor
   # Test with: curl or Postman
   curl -u username:password https://your-domain.com/ERP11PROD/api/v1/
   ```

3. **Network/Firewall**
   - Check if server can reach Epicor API
   - Verify firewall rules allow outbound HTTPS
   - Check if VPN required

4. **SSL Certificate Issues**
   ```python
   # Temporary workaround (NOT for production)
   import urllib3
   urllib3.disable_warnings()
   ```

---

### Issue: "HubSpot connection test failed"

**Symptoms:**
```
ERROR: HubSpot connection test failed
```

**Solutions:**

1. **Invalid API Key**
   - Go to HubSpot ’ Settings ’ Integrations ’ Private Apps
   - Generate new access token
   - Update `HUBSPOT_API_KEY` in .env

2. **Insufficient Permissions**
   - Private app needs scopes:
     - `crm.objects.companies.read` + `write`
     - `crm.objects.deals.read` + `write`
     - `crm.objects.line_items.read` + `write`
     - `crm.schemas.companies.read` + `write`
     - `crm.schemas.deals.read` + `write`

3. **Rate Limiting**
   ```
   ERROR: 429 Too Many Requests
   ```
   - HubSpot has API rate limits
   - Reduce `SYNC_BATCH_SIZE`
   - Add delays between requests
   - Upgrade HubSpot plan if needed

---

## Configuration Issues

### Issue: "Missing required fields"

**Symptoms:**
```
ERROR: Missing required fields in customer 12345
```

**Solution:**

Check which fields are missing:
```python
# Enable debug logging
LOG_LEVEL=DEBUG python -m src.main
```

Required fields by entity:
- **Customer**: `CustNum`, `Name`
- **Quote**: `QuoteNum`, `CustNum`
- **Order**: `OrderNum`, `CustNum`, `OpenOrder`

---

### Issue: "Pipeline ID not found"

**Symptoms:**
```
ERROR: Invalid pipeline ID
```

**Solution:**

1. Get correct pipeline IDs from HubSpot:
   - Settings ’ Objects ’ Deals ’ Pipelines
   - Click pipeline ’ Copy ID from URL

2. Update `.env`:
   ```ini
   HUBSPOT_QUOTES_PIPELINE_ID=actual_id_here
   HUBSPOT_ORDERS_PIPELINE_ID=actual_id_here
   ```

---

### Issue: "Sales rep mapping file not found"

**Symptoms:**
```
WARNING: Sales rep mapping file not found: config/sales_rep_mapping.json
```

**Solution:**

Create the file:
```bash
cat > config/sales_rep_mapping.json << 'EOF'
{
  "default_owner_id": null,
  "mappings": {
    "REP001": "hubspot_owner_id_1"
  }
}
EOF
```

---

## Sync Issues

### Issue: "Company not found in HubSpot for quote/order"

**Symptoms:**
```
WARNING: Company 12345 not found in HubSpot for quote 1001. Skipping quote.
```

**Cause:**
Customer sync must run BEFORE quote/order sync.

**Solution:**

1. Ensure `SYNC_CUSTOMERS=true` in .env
2. Run customer sync first:
   ```bash
   # Full sync (customers ’ quotes ’ orders)
   python -m src.main
   ```

3. Check if customer was created:
   - Go to HubSpot ’ Contacts ’ Companies
   - Search for `epicor_customer_number = 12345`

---

### Issue: "Transformation error for customer/quote/order"

**Symptoms:**
```
ERROR: Transformation error for quote 1001: KeyError: 'QuoteNum'
```

**Cause:**
Missing required field from Epicor API response.

**Solutions:**

1. **Check Epicor API Response:**
   ```bash
   # Enable debug logging to see raw data
   LOG_LEVEL=DEBUG python -m src.main
   ```

2. **Verify Epicor API Permissions:**
   - User must have read access to entities
   - Check BAQ security settings

3. **Check Field Names:**
   - Epicor field names are case-sensitive
   - Some fields may be in child tables

---

### Issue: "Failed to create/update in HubSpot"

**Symptoms:**
```
ERROR: L Failed to create company 12345
```

**Possible Causes:**

1. **Property Doesn't Exist:**
   ```
   ERROR: Property 'epicor_customer_number' does not exist
   ```
   - Create custom properties in HubSpot first
   - See field mapping documentation

2. **Invalid Property Value:**
   ```
   ERROR: Property 'amount' value must be a number
   ```
   - Check data types in transformation
   - Ensure numeric fields aren't strings

3. **Property Length Limit:**
   ```
   ERROR: Property value exceeds maximum length
   ```
   - HubSpot has field length limits
   - Truncate long text fields if needed

---

## Stage Logic Issues

### Issue: "Quote stage not updating"

**Symptoms:**
```
INFO: Quote 1001: Stage update blocked (keeping 'quote_sent')
```

**This is EXPECTED BEHAVIOR when:**

1. **Backward Movement Blocked:**
   - Current: `quote_sent` (position 3)
   - New: `quote_created` (position 1)
   - L Blocked: Cannot move backward

2. **Permanent Terminal Protected:**
   - Current: `closedwon` or `closedlost`
   - New: Any other stage
   - L Blocked: Cannot reopen closed deals

3. **HubSpot-Only Stage Protected:**
   - Current: `technical_review` or `follow_up`
   - New: Earlier stage
   - L Blocked: Cannot move backward from HubSpot stages

**Valid Stage Updates:**

```
 quote_created ’ quote_sent (forward)
 quote_sent ’ closedwon (terminal override)
 quote_expired ’ quote_created (reversible terminal)
L quote_sent ’ quote_created (backward)
L closedwon ’ quote_sent (permanent terminal)
```

---

### Issue: "Order stage incorrect"

**Symptoms:**
Order shows wrong stage in HubSpot.

**Solution:**

Check Epicor field values:
```python
# Enable debug logging
LOG_LEVEL=DEBUG python -m src.main

# Check logs for stage derivation:
# "Order stage: order_held (OrderHeld=true)"
```

**Stage Derivation Priority:**
1. `VoidOrder=true` ’ `cancelled`
2. `OpenOrder=false` ’ `completed`
3. `OrderHeld=true` ’ `order_held`
4. `OpenOrder=true AND TotalShipped>0` ’ `partially_shipped`
5. Default ’ `order_received`

---

## Data Mapping Issues

### Issue: "Phone number format invalid"

**Symptoms:**
```
WARNING: Failed to format phone '123-456'
```

**Solution:**

E.164 formatting expects valid phone numbers:
```
 Valid: (416) 555-1234 ’ +14165551234
 Valid: 416-555-1234 ’ +14165551234
L Invalid: 123-456 ’ None
L Invalid: abc-defg ’ None
```

Function automatically adds +1 for North American numbers.

---

### Issue: "GUID conversion error"

**Symptoms:**
```
WARNING: Failed to convert GUID 'invalid-guid'
```

**Solution:**

- GUIDs should be in format: `123e4567-e89b-12d3-a456-426614174000`
- Function removes hyphens: `123e4567e89b12d3a456426614174000`
- Invalid GUIDs are passed through as-is

---

### Issue: "Date conversion returns None"

**Symptoms:**
Date fields are empty in HubSpot.

**Cause:**
Invalid date format from Epicor.

**Solution:**

Expected format: ISO 8601
```
 Valid: 2024-01-15T14:30:00Z
 Valid: 2024-01-15T14:30:00
L Invalid: 2024/01/15
L Invalid: 01-15-2024
```

---

## Performance Issues

### Issue: "Sync taking too long"

**Symptoms:**
Sync exceeds Lambda timeout or takes hours locally.

**Solutions:**

1. **Reduce Batch Size:**
   ```ini
   SYNC_BATCH_SIZE=50  # Down from 100
   ```

2. **Use Date Filters:**
   ```python
   # Only sync recent quotes
   filter_condition = "EntryDate ge 2024-01-01"
   ```

3. **Increase Lambda Timeout:**
   - Go to Lambda ’ Configuration ’ General configuration
   - Set timeout to 10 minutes (max: 15 min)

4. **Increase Lambda Memory:**
   - More memory = more CPU
   - Try 1024 MB instead of 512 MB

5. **Split into Separate Functions:**
   - One Lambda for customers
   - One Lambda for quotes
   - One Lambda for orders

---

### Issue: "Memory errors in Lambda"

**Symptoms:**
```
ERROR: MemoryError: Out of memory
```

**Solutions:**

1. **Increase Lambda Memory:**
   - Current: 512 MB
   - Try: 1024 MB or 2048 MB

2. **Process in Smaller Batches:**
   ```python
   SYNC_BATCH_SIZE=25  # Smaller batches
   ```

3. **Use Generators:**
   - Process records one at a time
   - Don't load all records into memory

---

## AWS Lambda Issues

### Issue: "Lambda timeout"

**Symptoms:**
```
Task timed out after 300.00 seconds
```

**Solutions:**

1. **Increase Timeout:**
   - Configuration ’ General configuration ’ Timeout
   - Set to 10 minutes (600 seconds)

2. **Optimize Sync:**
   - Add date filters
   - Reduce batch size
   - Skip unchanged records

3. **Split into Multiple Invocations:**
   - Sync customers in one invocation
   - Sync quotes in another
   - Use Step Functions for orchestration

---

### Issue: "Import errors in Lambda"

**Symptoms:**
```
ERROR: No module named 'pydantic'
```

**Cause:**
Dependencies not included in deployment package.

**Solution:**

Rebuild deployment package:
```bash
# Create fresh package
rm -rf lambda-package
mkdir lambda-package
cd lambda-package

# Install all dependencies
pip install -r ../requirements.txt -t .

# Copy source
cp -r ../src .
cp -r ../config .

# Create ZIP
zip -r ../deployment-package.zip .
```

---

### Issue: "Environment variables not loading"

**Symptoms:**
```
ERROR: epicor_base_url: field required
```

**Solution:**

1. **Check Lambda Configuration:**
   - Configuration ’ Environment variables
   - Verify all required variables are set

2. **Check Variable Names:**
   - Must match config.py field names
   - Case-insensitive (Pydantic handles)

3. **Restart Function:**
   - Save a configuration change to force restart

---

## Debugging Tips

### Enable Debug Logging

```bash
# Local
LOG_LEVEL=DEBUG python -m src.main

# Lambda
# Set environment variable: LOG_LEVEL=DEBUG
```

### Check Raw API Responses

Add logging in clients:
```python
# In epicor_client.py or hubspot_client.py
logger.debug(f"API Response: {response.json()}")
```

### Test Individual Components

```python
# Test transformer only
from src.transformers.customer_transformer import CustomerTransformer

transformer = CustomerTransformer()
result = transformer.transform({
    'CustNum': 12345,
    'Name': 'Test Company'
})
print(result)
```

### Check HubSpot Properties

Use HubSpot API to verify:
```bash
curl "https://api.hubapi.com/crm/v3/objects/companies?limit=1" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Getting Help

### Log Analysis

When reporting issues, include:

1. **Error message** (full stack trace)
2. **Log context** (10 lines before/after error)
3. **Configuration** (sanitized, no credentials)
4. **Steps to reproduce**
5. **Expected vs actual behavior**

### Useful Log Filters

CloudWatch Logs Insights queries:

```sql
# Find all errors
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 100

# Find sync summaries
fields @timestamp, @message
| filter @message like /SYNC COMPLETE/
| sort @timestamp desc

# Find stage update blocks
fields @timestamp, @message
| filter @message like /Stage update blocked/
| sort @timestamp desc
```

---

## Common Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 400 | Bad Request | Check payload format |
| 401 | Unauthorized | Verify API credentials |
| 403 | Forbidden | Check API permissions |
| 404 | Not Found | Verify resource exists |
| 429 | Rate Limited | Reduce request frequency |
| 500 | Server Error | Retry, contact API support |

---

*Last Updated: November 13, 2025*
