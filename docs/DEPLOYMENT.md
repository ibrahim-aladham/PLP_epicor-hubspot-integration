# Deployment Guide - Epicor-HubSpot Integration

This guide covers deploying the integration to AWS Lambda and local development setup.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [AWS Lambda Deployment](#aws-lambda-deployment)
- [Configuration](#configuration)
- [Testing](#testing)
- [Monitoring](#monitoring)

---

## Prerequisites

### Required Accounts & Access

-  AWS Account with Lambda permissions
-  Epicor ERP access with API credentials
-  HubSpot account with Private App created
-  Python 3.9+ installed locally

### Required Tools

```bash
# Python 3.9 or higher
python --version

# pip (Python package manager)
pip --version

# AWS CLI (for Lambda deployment)
aws --version

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
1. Go to HubSpot ’ Settings ’ Users & Teams
2. Click on user ’ Copy Owner ID from URL

### 6. Run Locally

```bash
# Run sync
python -m src.main

# With debug logging
LOG_LEVEL=DEBUG python -m src.main
```

---

## AWS Lambda Deployment

### Method 1: Manual Deployment (via AWS Console)

#### Step 1: Create Deployment Package

```bash
# Create clean deployment directory
mkdir lambda-package
cd lambda-package

# Install dependencies
pip install -r ../requirements.txt -t .

# Copy source code
cp -r ../src .
cp -r ../config .

# Create ZIP file
zip -r ../deployment-package.zip .

# Go back to project root
cd ..
```

#### Step 2: Create Lambda Function

1. Go to **AWS Lambda Console**
2. Click **Create function**
3. Choose:
   - Function name: `epicor-hubspot-integration`
   - Runtime: **Python 3.9** (or 3.10/3.11)
   - Architecture: **x86_64**
   - Permissions: Create new role with basic Lambda permissions

4. Click **Create function**

#### Step 3: Upload Code

1. In Lambda function page, click **Upload from** ’ **.zip file**
2. Upload `deployment-package.zip`
3. Click **Save**

#### Step 4: Configure Environment Variables

1. Go to **Configuration** ’ **Environment variables**
2. Click **Edit** ’ **Add environment variable**
3. Add all variables from your `.env` file:

```
EPICOR_BASE_URL = https://...
EPICOR_COMPANY = ...
EPICOR_USERNAME = ...
EPICOR_PASSWORD = ...
EPICOR_API_KEY = ...
HUBSPOT_API_KEY = ...
HUBSPOT_QUOTES_PIPELINE_ID = ...
HUBSPOT_ORDERS_PIPELINE_ID = ...
SYNC_BATCH_SIZE = 100
SYNC_MAX_RETRIES = 3
LOG_LEVEL = INFO
ENVIRONMENT = production
SYNC_CUSTOMERS = true
SYNC_QUOTES = true
SYNC_ORDERS = true
```

4. Click **Save**

#### Step 5: Configure Function Settings

1. **General Configuration**:
   - Memory: **512 MB** (or more for large datasets)
   - Timeout: **5 minutes** (or 10 minutes for full sync)
   - Handler: `src.main.lambda_handler`

2. **VPC** (if Epicor is in VPC):
   - Select VPC
   - Select subnets
   - Select security groups

#### Step 6: Test Function

1. Click **Test** tab
2. Create new test event:
   ```json
   {
     "operation": "full_sync"
   }
   ```
3. Click **Test**
4. Check execution results and logs

### Method 2: AWS CLI Deployment

```bash
# Create deployment package
./deploy/create-package.sh

# Create Lambda function
aws lambda create-function \
  --function-name epicor-hubspot-integration \
  --runtime python3.9 \
  --handler src.main.lambda_handler \
  --zip-file fileb://deployment-package.zip \
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{EPICOR_BASE_URL=...,HUBSPOT_API_KEY=...}"

# Update function code (for updates)
aws lambda update-function-code \
  --function-name epicor-hubspot-integration \
  --zip-file fileb://deployment-package.zip
```

### Method 3: AWS SAM/Serverless Framework

Create `template.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  EpicorHubSpotSync:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: epicor-hubspot-integration
      Handler: src.main.lambda_handler
      Runtime: python3.9
      CodeUri: .
      Timeout: 300
      MemorySize: 512
      Environment:
        Variables:
          EPICOR_BASE_URL: !Ref EpicorBaseUrl
          HUBSPOT_API_KEY: !Ref HubSpotApiKey
          # ... other variables
      Events:
        ScheduledSync:
          Type: Schedule
          Properties:
            Schedule: rate(1 hour)  # Run every hour

Parameters:
  EpicorBaseUrl:
    Type: String
  HubSpotApiKey:
    Type: String
    NoEcho: true
```

Deploy:

```bash
sam build
sam deploy --guided
```

---

## Configuration

### Getting HubSpot Pipeline IDs

1. Go to HubSpot ’ **Settings** ’ **Objects** ’ **Deals** ’ **Pipelines**
2. Click on your **Quotes** pipeline
3. Copy the ID from the URL:
   ```
   https://app.hubspot.com/contacts/12345/objects/0-3/pipelines/6789012
                                                                 ^^^^^^^
                                                            This is the ID
   ```
4. Repeat for **Orders** pipeline
5. Update `.env` or Lambda environment variables

### Setting Up Scheduled Execution

#### Option 1: EventBridge (CloudWatch Events)

1. Go to **EventBridge** ’ **Rules** ’ **Create rule**
2. Define schedule:
   - **Rate expression**: `rate(1 hour)` (every hour)
   - **Cron expression**: `cron(0 */4 * * ? *)` (every 4 hours)
3. Select target: Your Lambda function
4. Create rule

#### Option 2: Lambda Trigger

1. In Lambda function, click **Add trigger**
2. Select **EventBridge (CloudWatch Events)**
3. Create new rule with schedule
4. Save

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

### Lambda Testing

#### Test Event (Manual Sync)

```json
{
  "operation": "full_sync"
}
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

### CloudWatch Logs

All logs are automatically sent to CloudWatch Logs:

1. Go to **CloudWatch** ’ **Log groups**
2. Find `/aws/lambda/epicor-hubspot-integration`
3. View log streams

### Key Log Messages

```
 Success indicators:
- "CUSTOMER SYNC COMPLETE"
- "QUOTE SYNC COMPLETE"
- "FULL SYNC COMPLETE"
- " Created company"
- " Updated quote"

   Warning indicators:
- "Rep 'XXX' not mapped"
- "Company not found"
- "Stage update blocked"

L Error indicators:
- "Failed to fetch"
- "Transformation error"
- "L Failed to create"
```

### CloudWatch Metrics (Custom)

Add custom metrics in code:

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='EpicorHubSpot',
    MetricData=[
        {
            'MetricName': 'CustomersSync',
            'Value': created_count,
            'Unit': 'Count'
        }
    ]
)
```

### Alerts

Create CloudWatch Alarms for:

- Lambda errors
- Execution duration > threshold
- Custom sync failure metrics

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

---

## Security Best Practices

### 1. Secrets Management

**Use AWS Secrets Manager (Recommended):**

```python
import boto3
import json

def get_secret(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# In Lambda function
epicor_creds = get_secret('epicor-credentials')
hubspot_key = get_secret('hubspot-api-key')
```

**Store secrets:**

```bash
aws secretsmanager create-secret \
  --name epicor-credentials \
  --secret-string '{"username":"...","password":"...","api_key":"..."}'

aws secretsmanager create-secret \
  --name hubspot-api-key \
  --secret-string '{"api_key":"..."}'
```

### 2. IAM Permissions

Minimum Lambda execution role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:epicor-*"
    }
  ]
}
```

### 3. Network Security

- Use VPC for Epicor access if required
- Configure security groups to allow only necessary outbound traffic
- Use PrivateLink for AWS services if needed

---

## Rollback Procedure

If deployment fails:

1. **Revert Lambda code:**
   ```bash
   aws lambda update-function-code \
     --function-name epicor-hubspot-integration \
     --zip-file fileb://previous-deployment-package.zip
   ```

2. **Restore environment variables** from previous version

3. **Check CloudWatch logs** for error details

4. **Test with small dataset** before full sync

---

## Production Checklist

Before going live:

- [ ] All environment variables configured
- [ ] Sales rep mapping file updated with real data
- [ ] HubSpot pipeline IDs verified
- [ ] Test sync with small dataset
- [ ] CloudWatch alarms configured
- [ ] Secrets stored in Secrets Manager (not environment variables)
- [ ] Lambda timeout appropriate for data volume
- [ ] Lambda memory appropriate for data volume
- [ ] Scheduled trigger configured
- [ ] Error notification setup (SNS/email)
- [ ] Documentation shared with team

---

*Last Updated: November 13, 2025*
