# Epicor-HubSpot Integration - Complete Implementation Instructions for Claude Code

## 📋 PROJECT OVERVIEW

**Project Name:** PLP Canada - Epicor to HubSpot Integration  
**Scope Authority:** Collins (190 hours estimated)  
**Sales Rep:** Sabrina  
**Objective:** One-way data synchronization from Epicor ERP to HubSpot CRM  
**Sync Frequency:** Daily at 2 AM EST  
**Deployment:** AWS Lambda (Serverless)

### Key Requirements (from Collins' Scope)
- **One-way sync**: Epicor → HubSpot only (Epicor remains the primary system)
- **Daily sync**: Automated batch processing once per day
- **Historical data**: Import historical quotes and orders
- **Data volumes**:
  - 64 active customer accounts
  - ~9,000 parts (many historical/inactive)
  - ~1,600 quotes per year (~7 per day)
  - Associated contacts, orders, and line items

---

## 🏗️ SYSTEM ARCHITECTURE

### Technology Stack
```yaml
Language: Python 3.11
Cloud: AWS (Lambda, S3, CloudWatch, Secrets Manager)
APIs: 
  - Epicor REST API v2 (OData v4)
  - HubSpot REST API v3/v4
Dependencies:
  - requests: 2.31.0
  - python-dotenv: 1.0.0
  - boto3: 1.34.0
  - pydantic: 2.5.0
Development:
  - Docker: Local testing
  - pytest: 8.0.0
  - black: 23.12.0
  - pylint: 3.0.0
```

### Architecture Diagram
```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Epicor ERP    │─────▶│  AWS Lambda     │─────▶│    HubSpot      │
│   (REST API)    │      │  (Python App)   │      │    (REST API)   │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                               │     │
                               ▼     ▼
                         ┌──────┐ ┌──────────┐
                         │  S3  │ │CloudWatch│
                         │ Logs │ │  Events  │
                         └──────┘ └──────────┘
```

---

## 📂 COMPLETE PROJECT STRUCTURE

Create the following directory structure exactly:

```
epicor-hubspot-integration/
│
├── src/                          # Source code
│   ├── __init__.py
│   ├── main.py                   # Lambda handler entry point
│   ├── config.py                 # Configuration management
│   │
│   ├── clients/                  # API clients
│   │   ├── __init__.py
│   │   ├── epicor_client.py     # Epicor API wrapper
│   │   └── hubspot_client.py    # HubSpot API wrapper
│   │
│   ├── models/                   # Data models
│   │   ├── __init__.py
│   │   ├── epicor_models.py     # Epicor data structures
│   │   └── hubspot_models.py    # HubSpot data structures
│   │
│   ├── transformers/             # Data transformation
│   │   ├── __init__.py
│   │   ├── base_transformer.py  # Base transformation class
│   │   ├── customer_transformer.py
│   │   ├── contact_transformer.py
│   │   ├── quote_transformer.py
│   │   ├── order_transformer.py
│   │   └── part_transformer.py
│   │
│   ├── sync/                     # Sync logic
│   │   ├── __init__.py
│   │   ├── sync_manager.py      # Main sync orchestrator
│   │   ├── sync_customers.py
│   │   ├── sync_contacts.py
│   │   ├── sync_quotes.py
│   │   ├── sync_orders.py
│   │   └── sync_parts.py
│   │
│   └── utils/                    # Utilities
│       ├── __init__.py
│       ├── logger.py             # Logging configuration
│       ├── error_handler.py     # Error handling
│       └── date_utils.py        # Date conversions
│
├── tests/                        # Test files
│   ├── __init__.py
│   ├── conftest.py              # Pytest configuration
│   ├── test_epicor_client.py
│   ├── test_hubspot_client.py
│   ├── test_transformers.py
│   └── test_sync_manager.py
│
├── config/                       # Configuration files
│   ├── dev.env                  # Development environment
│   ├── prod.env                 # Production environment
│   └── field_mappings.json      # Field mapping configuration
│
├── scripts/                      # Utility scripts
│   ├── setup_local.sh           # Local setup script
│   ├── deploy.sh                # Deployment script
│   ├── test_connection.py       # Test API connections
│   └── backfill_historical.py  # Historical data migration
│
├── docker/                       # Docker configuration
│   ├── Dockerfile               # Container definition
│   └── docker-compose.yml      # Local development setup
│
├── aws/                         # AWS configuration
│   ├── lambda_function.zip     # Deployment package (generated)
│   ├── cloudformation.yml      # Infrastructure as code
│   └── iam_policy.json         # Lambda IAM permissions
│
├── docs/                        # Documentation
│   ├── API_REFERENCE.md        # API documentation
│   ├── DEPLOYMENT.md           # Deployment guide
│   └── TROUBLESHOOTING.md      # Common issues
│
├── logs/                        # Local log files (git ignored)
│   └── .gitkeep
│
├── .env.example                 # Environment template
├── .gitignore                   # Git ignore rules
├── requirements.txt             # Python dependencies
├── requirements-dev.txt        # Development dependencies
├── pytest.ini                   # Pytest configuration
├── Makefile                     # Common commands
└── README.md                    # Project documentation
```

---

## 🔑 EPICOR REST API DETAILS

### Base Configuration
```yaml
Base URL: https://plpc-apperp.preformed.ca/ERP11PROD/api/v2/odata
Company: PLPC
API Version: v2 (OData v4)
Authentication: Basic Auth + API Key (BOTH required)
```

### Required Headers
```python
headers = {
    "Authorization": f"Basic {base64_encoded_credentials}",
    "x-api-key": "your_api_key",
    "Content-Type": "application/json"
}
```

### API Endpoints Structure
```
# Format
GET /api/v2/odata/{Company}/{Service}/{EntitySet}?$expand={ChildEntities}&api-key={key}

# Examples
GET /api/v2/odata/PLPC/Erp.BO.CustomerSvc/Customers
GET /api/v2/odata/PLPC/Erp.BO.PerConSvc/PerCons
GET /api/v2/odata/PLPC/Erp.BO.QuoteSvc/Quotes?$expand=QuoteDtls
GET /api/v2/odata/PLPC/Erp.BO.SalesOrderSvc/SalesOrders?$expand=OrderDtls
GET /api/v2/odata/PLPC/Erp.BO.PartSvc/Parts
```

### OData Query Parameters
```python
# Pagination
$top=100         # Limit results to 100 rows
$skip=100        # Skip first 100 rows

# Filtering
$filter=CustNum gt 100 and Country eq 'Canada'
$filter=EntryDate ge 2024-01-01T00:00:00Z

# Expanding child entities
$expand=QuoteDtls          # Include quote line items
$expand=OrderDtls          # Include order line items
$expand=PerConLnks         # Include contact links

# Selecting specific fields
$select=CustNum,Name,City

# Ordering
$orderby=EntryDate desc

# Counting
$count=true               # Include total count in response
```

### Error Handling
```python
# Common error codes
200: Success
400: Bad request (invalid OData query)
401: Unauthorized (invalid credentials)
403: Forbidden (no API key or invalid)
404: Not found
500: Internal server error
```

---

## 🔄 DATA MAPPING SPECIFICATIONS

### 1. CUSTOMER → COMPANY

**Epicor Source:** `Erp.BO.CustomerSvc/Customers`  
**HubSpot Target:** Companies Object

| Epicor Field | Type | HubSpot Property | Type | Transform | Notes |
|--------------|------|------------------|------|-----------|-------|
| CustNum | int | epicor_customer_number | number | Direct | PRIMARY ID |
| CustID | string(8) | epicor_customer_code | text | Direct | Business ID |
| Name | string(50) | name | text | Direct | Company name |
| Address1 | string(50) | address | text | Direct | Street 1 |
| Address2 | string(50) | address2 | text | Direct | Street 2 |
| City | string(50) | city | text | Direct | City |
| State | string(50) | state | text | Direct | Province |
| Zip | string(10) | zip | text | Direct | Postal code |
| Country | string(50) | country | text | Direct | Country |
| PhoneNum | string(20) | phone | text | E.164 format | Phone |
| FaxNum | string(20) | fax_number | text | Direct | Fax |
| EmailAddress | string(100) | epicor_email | text | Direct | Email |
| TermsCode | string(10) | payment_terms | text | Direct | Terms |
| CreditHold | boolean | credit_hold_status | boolean | Direct | Hold flag |
| TerritoryID | string(10) | territory | text | Direct | Territory |
| CurrencyCode | string(3) | currency_code | text | Direct | Currency |
| SysRowID | guid | epicor_sysrowid | text | To string | System ID |

**Matching Strategy:** Search by `epicor_customer_number`, create if not exists

---

### 2. CONTACT → CONTACT

**Epicor Source:** `Erp.BO.PerConSvc/PerCons`  
**HubSpot Target:** Contacts Object

| Epicor Field | Type | HubSpot Property | Type | Transform | Notes |
|--------------|------|------------------|------|-----------|-------|
| PerConID | int | epicor_contact_id | number | Direct | **PRIMARY ID** |
| Name | string(50) | full_name | text | Direct | Full name |
| FirstName | string(50) | firstname | text | Direct | First name |
| MiddleName | string(50) | middlename | text | Direct | Middle name |
| LastName | string(50) | lastname | text | Direct | Last name |
| EmailAddress | string(100) | email | text | Direct | Email |
| PhoneNum | string(20) | phone | text | Format | Phone |
| FaxNum | string(20) | fax_number | text | Format | Fax |
| Func | string(10) | job_function | text | Direct | Function code |
| SysRowID | guid | epicor_contact_sysrowid | text | To string | System ID |

**Association Rules:**
- Associate with Company via `PerConLnks` → `CustNum`
- Association Type: contact_to_company (type ID: 1)
- **Primary Matching Field:** `epicor_contact_id` (PerConID)

---

### 3. QUOTE → DEAL (Quotes Pipeline)

**Epicor Source:** `Erp.BO.QuoteSvc/Quotes?$expand=QuoteDtls`  
**HubSpot Target:** Deals Object

| Epicor Field | Type | HubSpot Property | Type | Transform | Notes |
|--------------|------|------------------|------|-----------|-------|
| QuoteNum | int | dealname | text | "Quote #" + num | Deal name |
| QuoteNum | int | epicor_quote_number | number | Direct | PRIMARY ID |
| CustNum | int | (association) | - | Via API | To company |
| EntryDate | datetime | createdate | datetime | Unix ms | Created |
| DueDate | datetime | closedate | datetime | Unix ms | Due date (STANDARD) |
| ExpirationDate | datetime | quote_expiration_date | datetime | Unix ms | Expires |
| DateQuoted | datetime | quote_sent_date | datetime | Unix ms | Sent date |
| QuoteAmt | decimal | amount | number | Direct | Total value |
| DocQuoteAmt | decimal | epicor_doc_amount | number | Direct | Doc amount |
| PONum | string(25) | customer_po_number | text | Direct | PO number |
| CurrentStage | string(10) | dealstage | text | Map stages | Stage |
| Quoted | boolean | epicor_quoted | boolean | Direct | Sent flag |
| QuoteClosed | boolean | epicor_closed | boolean | Direct | Closed |
| Ordered | boolean | epicor_converted_to_order | boolean | Direct | Won |
| Expired | boolean | epicor_expired | boolean | Direct | Expired |
| DiscountPercent | decimal | discount_percentage | number | Direct | Discount % |
| CurrencyCode | string(3) | deal_currency_code_ | text | Direct | Currency |
| SysRowID | guid | epicor_quote_sysrowid | text | To string | System ID |
| (hardcoded) | - | pipeline | text | Pipeline ID | Quotes pipe |

**Stage Mapping Logic:**
```python
def get_quote_stage(quote):
    if quote['Ordered']:
        return 'closedwon'          # Converted to order
    elif quote['Expired']:
        return 'quote_expired'
    elif quote['QuoteClosed']:
        return 'closedlost'         # Closed without order
    elif quote['Quoted']:
        return 'quote_sent'
    else:
        return 'quote_created'
```

---

### 4. ORDER → DEAL (Orders Pipeline)

**Epicor Source:** `Erp.BO.SalesOrderSvc/SalesOrders?$expand=OrderDtls`  
**HubSpot Target:** Deals Object

| Epicor Field | Type | HubSpot Property | Type | Transform | Notes |
|--------------|------|------------------|------|-----------|-------|
| OrderNum | int | dealname | text | "Order #" + num | Deal name |
| OrderNum | int | epicor_order_number | number | Direct | PRIMARY ID |
| CustNum | int | (association) | - | Via API | To company |
| OrderDate | datetime | createdate | datetime | Unix ms | Created |
| RequestDate | datetime | closedate | datetime | Unix ms | Delivery (STANDARD) |
| NeedByDate | datetime | need_by_date | datetime | Unix ms | Need by |
| OrderAmt | decimal | amount | number | Direct | Total value |
| TotalCharges | decimal | epicor_subtotal | number | Direct | Subtotal |
| DocOrderAmt | decimal | epicor_doc_amount | number | Direct | Doc amount |
| PONum | string(25) | customer_po_number | text | Direct | PO number |
| OpenOrder | boolean | epicor_open_order | boolean | Direct | Is open |
| OrderHeld | boolean | epicor_order_held | boolean | Direct | On hold |
| VoidOrder | boolean | epicor_void_order | boolean | Direct | Voided |
| OrderStatus | string(10) | epicor_order_status | text | Direct | Status |
| CurrencyCode | string(3) | deal_currency_code_ | text | Direct | Currency |
| SysRowID | guid | epicor_order_sysrowid | text | To string | System ID |
| (hardcoded) | - | pipeline | text | Pipeline ID | Orders pipe |

**Stage Mapping Logic:**
```python
def get_order_stage(order):
    if order['VoidOrder']:
        return 'closedlost'         # Cancelled
    elif not order['OpenOrder']:
        return 'closedwon'          # Completed
    elif order['OrderHeld']:
        return 'order_held'
    else:
        return 'order_received'     # Active
```

---

### 5. PART → PRODUCT

**Epicor Source:** `Erp.BO.PartSvc/Parts`  
**HubSpot Target:** Products Object

| Epicor Field | Type | HubSpot Property | Type | Transform | Notes |
|--------------|------|------------------|------|-----------|-------|
| PartNum | string(50) | hs_sku | text | Direct | Product SKU (PRIMARY) |
| PartDescription | string(100) | name | text | Direct | Product name |
| SearchWord | string(50) | epicor_search_word | text | Direct | Search keyword |
| ClassID | string(10) | category | text | Direct | Product class |
| TypeCode | string(10) | epicor_type_code | text | Direct | P=Purchased, M=Manufactured |
| IUM | string(10) | unit_of_measure | text | Direct | Inventory UOM |
| PUM | string(10) | purchase_uom | text | Direct | Purchase UOM |
| NonStock | boolean | non_stock_item | boolean | Direct | Non-stock flag |
| PurchasingFactor | decimal | epicor_purchase_factor | number | Direct | UOM conversion |
| InActive | boolean | product_status | text | Map active/inactive | Active status |
| SysRowID | guid | epicor_part_sysrowid | text | To string | System ID |

---

### 6. LINE ITEMS

**Quote Line Items:** `QuoteDtls` (expanded from Quotes)  
**Order Line Items:** `OrderDtls` (expanded from Orders)

| Epicor Field | Type | HubSpot Property | Type | Notes |
|--------------|------|------------------|------|-------|
| PartNum | string | sku | text | Links to Product |
| OrderQty / QuoteQty | decimal | quantity | number | Quantity |
| UnitPrice / DocUnitPrice | decimal | price | number | Unit price |
| LineDesc | string | name | text | Line description |
| DocExtPriceDtl | decimal | amount | number | Line total |
| LineNum | int | (internal) | - | Line sequence |

---

## 💻 IMPLEMENTATION INSTRUCTIONS

### Phase 1: Project Setup (2 hours)

1. **Create project structure** using the directory layout above
2. **Initialize git repository**
   ```bash
   git init
   git add .gitignore README.md
   git commit -m "Initial commit"
   ```

3. **Create requirements.txt**:
   ```
   requests==2.31.0
   python-dotenv==1.0.0
   boto3==1.34.0
   pydantic==2.5.0
   ```

4. **Create requirements-dev.txt**:
   ```
   pytest==8.0.0
   pytest-cov==4.1.0
   black==23.12.0
   pylint==3.0.0
   mypy==1.7.0
   pre-commit==3.5.0
   ```

5. **Create .env.example**:
   ```bash
   # Epicor Configuration
   EPICOR_BASE_URL=https://plpc-apperp.preformed.ca/ERP11PROD
   EPICOR_COMPANY=PLPC
   EPICOR_USERNAME=your_username
   EPICOR_PASSWORD=your_password
   EPICOR_API_KEY=your_api_key

   # HubSpot Configuration
   HUBSPOT_API_KEY=your_hubspot_api_key
   HUBSPOT_QUOTES_PIPELINE_ID=quotes_pipeline_id
   HUBSPOT_ORDERS_PIPELINE_ID=orders_pipeline_id

   # AWS Configuration
   AWS_REGION=us-east-1
   S3_BUCKET=epicor-hubspot-sync-logs

   # Sync Configuration
   BATCH_SIZE=100
   MAX_RETRIES=3
   RETRY_DELAY=5
   LOG_LEVEL=INFO

   # Feature Flags
   SYNC_CUSTOMERS=true
   SYNC_CONTACTS=true
   SYNC_QUOTES=true
   SYNC_ORDERS=true
   SYNC_PARTS=true
   ```

6. **Create .gitignore**:
   ```
   # Python
   __pycache__/
   *.py[cod]
   *$py.class
   *.so
   .Python
   venv/
   env/
   ENV/

   # Environment
   .env
   config/*.env
   !config/dev.env.example

   # AWS
   aws/lambda_function.zip

   # Logs
   logs/
   *.log

   # IDE
   .vscode/
   .idea/
   *.swp
   *.swo

   # Testing
   .pytest_cache/
   .coverage
   htmlcov/

   # OS
   .DS_Store
   Thumbs.db
   ```

---

### Phase 2: Core Components (15 hours)

#### 2.1 Config Module (`src/config.py`)

```python
"""Configuration management for the integration."""
import os
from typing import Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings."""
    
    # Epicor Configuration
    epicor_base_url: str = Field(..., env="EPICOR_BASE_URL")
    epicor_company: str = Field(..., env="EPICOR_COMPANY")
    epicor_username: str = Field(..., env="EPICOR_USERNAME")
    epicor_password: str = Field(..., env="EPICOR_PASSWORD")
    epicor_api_key: str = Field(..., env="EPICOR_API_KEY")
    
    # HubSpot Configuration
    hubspot_api_key: str = Field(..., env="HUBSPOT_API_KEY")
    hubspot_quotes_pipeline_id: str = Field(..., env="HUBSPOT_QUOTES_PIPELINE_ID")
    hubspot_orders_pipeline_id: str = Field(..., env="HUBSPOT_ORDERS_PIPELINE_ID")
    
    # AWS Configuration
    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    s3_bucket: str = Field(..., env="S3_BUCKET")
    
    # Sync Configuration
    batch_size: int = Field(default=100, env="BATCH_SIZE")
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    retry_delay: int = Field(default=5, env="RETRY_DELAY")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Feature Flags
    sync_customers: bool = Field(default=True, env="SYNC_CUSTOMERS")
    sync_contacts: bool = Field(default=True, env="SYNC_CONTACTS")
    sync_quotes: bool = Field(default=True, env="SYNC_QUOTES")
    sync_orders: bool = Field(default=True, env="SYNC_ORDERS")
    sync_parts: bool = Field(default=True, env="SYNC_PARTS")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
```

#### 2.2 Epicor Client (`src/clients/epicor_client.py`)

```python
"""Epicor REST API client."""
import base64
import logging
from typing import Dict, List, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class EpicorClient:
    """Client for Epicor REST API v2."""
    
    def __init__(self, base_url: str, company: str, username: str, 
                 password: str, api_key: str):
        """Initialize Epicor client."""
        self.base_url = base_url.rstrip('/')
        self.company = company
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)
        
        # Create session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set authentication headers
        credentials = f"{username}:{password}"
        encoded_creds = base64.b64encode(credentials.encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {encoded_creds}",
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
    
    def _build_url(self, service: str, entity_set: str, 
                   params: Optional[Dict[str, str]] = None) -> str:
        """Build OData URL."""
        url = f"{self.base_url}/api/v2/odata/{self.company}/{service}/{entity_set}"
        
        if params:
            query_params = []
            for key, value in params.items():
                query_params.append(f"{key}={value}")
            url += "?" + "&".join(query_params)
        
        return url
    
    def _get_paged(self, url: str, batch_size: int = 100) -> List[Dict[str, Any]]:
        """Get all pages of data."""
        all_records = []
        skip = 0
        
        while True:
            paged_url = f"{url}{'&' if '?' in url else '?'}$top={batch_size}&$skip={skip}"
            
            self.logger.info(f"Fetching: {paged_url}")
            response = self.session.get(paged_url)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('value', [])
            
            if not records:
                break
            
            all_records.extend(records)
            skip += len(records)
            
            self.logger.info(f"Fetched {len(records)} records, total: {len(all_records)}")
            
            # Check if there's a next link
            if '@odata.nextLink' not in data:
                break
        
        return all_records
    
    def get_customers(self) -> List[Dict[str, Any]]:
        """Get all customers."""
        url = self._build_url("Erp.BO.CustomerSvc", "Customers")
        return self._get_paged(url)
    
    def get_contacts(self) -> List[Dict[str, Any]]:
        """Get all contacts with links."""
        url = self._build_url(
            "Erp.BO.PerConSvc", 
            "PerCons",
            {"$expand": "PerConLnks"}
        )
        return self._get_paged(url)
    
    def get_quotes(self, modified_after: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get quotes with line items."""
        params = {"$expand": "QuoteDtls"}
        
        if modified_after:
            params["$filter"] = f"SysRevID gt datetime'{modified_after}'"
        
        url = self._build_url("Erp.BO.QuoteSvc", "Quotes", params)
        return self._get_paged(url)
    
    def get_orders(self, modified_after: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get orders with line items."""
        params = {"$expand": "OrderDtls"}
        
        if modified_after:
            params["$filter"] = f"SysRevID gt datetime'{modified_after}'"
        
        url = self._build_url("Erp.BO.SalesOrderSvc", "SalesOrders", params)
        return self._get_paged(url)
    
    def get_parts(self) -> List[Dict[str, Any]]:
        """Get all parts."""
        url = self._build_url("Erp.BO.PartSvc", "Parts")
        return self._get_paged(url)
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            url = f"{self.base_url}/api/v2/environment"
            response = self.session.get(url)
            response.raise_for_status()
            self.logger.info("Epicor connection successful")
            return True
        except Exception as e:
            self.logger.error(f"Epicor connection failed: {e}")
            return False
```

#### 2.3 HubSpot Client (`src/clients/hubspot_client.py`)

```python
"""HubSpot REST API client."""
import logging
from typing import Dict, List, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class HubSpotClient:
    """Client for HubSpot REST API."""
    
    def __init__(self, api_key: str):
        """Initialize HubSpot client."""
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"
        self.logger = logging.getLogger(__name__)
        
        # Create session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set headers
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
    
    # COMPANIES
    def search_companies(self, filter_groups: List[Dict]) -> List[Dict]:
        """Search for companies."""
        url = f"{self.base_url}/crm/v3/objects/companies/search"
        payload = {
            "filterGroups": filter_groups,
            "properties": ["epicor_customer_number", "name"],
            "limit": 100
        }
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json().get('results', [])
    
    def create_company(self, properties: Dict[str, Any]) -> Dict:
        """Create a company."""
        url = f"{self.base_url}/crm/v3/objects/companies"
        payload = {"properties": properties}
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def update_company(self, company_id: str, properties: Dict[str, Any]) -> Dict:
        """Update a company."""
        url = f"{self.base_url}/crm/v3/objects/companies/{company_id}"
        payload = {"properties": properties}
        
        response = self.session.patch(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    # CONTACTS
    def search_contacts(self, filter_groups: List[Dict]) -> List[Dict]:
        """Search for contacts."""
        url = f"{self.base_url}/crm/v3/objects/contacts/search"
        payload = {
            "filterGroups": filter_groups,
            "properties": ["epicor_contact_id", "email"],
            "limit": 100
        }
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json().get('results', [])
    
    def create_contact(self, properties: Dict[str, Any]) -> Dict:
        """Create a contact."""
        url = f"{self.base_url}/crm/v3/objects/contacts"
        payload = {"properties": properties}
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def update_contact(self, contact_id: str, properties: Dict[str, Any]) -> Dict:
        """Update a contact."""
        url = f"{self.base_url}/crm/v3/objects/contacts/{contact_id}"
        payload = {"properties": properties}
        
        response = self.session.patch(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    # DEALS
    def search_deals(self, filter_groups: List[Dict]) -> List[Dict]:
        """Search for deals."""
        url = f"{self.base_url}/crm/v3/objects/deals/search"
        payload = {
            "filterGroups": filter_groups,
            "properties": ["epicor_quote_number", "epicor_order_number", "dealname"],
            "limit": 100
        }
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json().get('results', [])
    
    def create_deal(self, properties: Dict[str, Any]) -> Dict:
        """Create a deal."""
        url = f"{self.base_url}/crm/v3/objects/deals"
        payload = {"properties": properties}
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def update_deal(self, deal_id: str, properties: Dict[str, Any]) -> Dict:
        """Update a deal."""
        url = f"{self.base_url}/crm/v3/objects/deals/{deal_id}"
        payload = {"properties": properties}
        
        response = self.session.patch(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    # PRODUCTS
    def search_products(self, filter_groups: List[Dict]) -> List[Dict]:
        """Search for products."""
        url = f"{self.base_url}/crm/v3/objects/products/search"
        payload = {
            "filterGroups": filter_groups,
            "properties": ["hs_sku", "name"],
            "limit": 100
        }
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json().get('results', [])
    
    def create_product(self, properties: Dict[str, Any]) -> Dict:
        """Create a product."""
        url = f"{self.base_url}/crm/v3/objects/products"
        payload = {"properties": properties}
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def update_product(self, product_id: str, properties: Dict[str, Any]) -> Dict:
        """Update a product."""
        url = f"{self.base_url}/crm/v3/objects/products/{product_id}"
        payload = {"properties": properties}
        
        response = self.session.patch(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    # LINE ITEMS
    def create_line_item(self, properties: Dict[str, Any]) -> Dict:
        """Create a line item."""
        url = f"{self.base_url}/crm/v3/objects/line_items"
        payload = {"properties": properties}
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    # ASSOCIATIONS
    def create_association(self, from_object: str, from_id: str, 
                          to_object: str, to_id: str, 
                          association_type_id: int) -> bool:
        """Create association between objects."""
        url = (f"{self.base_url}/crm/v4/objects/{from_object}/{from_id}/"
               f"associations/{to_object}/{to_id}")
        
        payload = [{
            "associationCategory": "HUBSPOT_DEFINED",
            "associationTypeId": association_type_id
        }]
        
        response = self.session.put(url, json=payload)
        response.raise_for_status()
        
        return True
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            url = f"{self.base_url}/crm/v3/objects/companies?limit=1"
            response = self.session.get(url)
            response.raise_for_status()
            self.logger.info("HubSpot connection successful")
            return True
        except Exception as e:
            self.logger.error(f"HubSpot connection failed: {e}")
            return False
```

---

### Phase 3: Transformers (8 hours)

Create transformer classes for each entity type. Example for Customer:

#### `src/transformers/customer_transformer.py`

```python
"""Customer to Company transformer."""
from typing import Dict, Any, Optional
from datetime import datetime


class CustomerTransformer:
    """Transform Epicor Customer to HubSpot Company."""
    
    @staticmethod
    def transform(epicor_customer: Dict[str, Any]) -> Dict[str, Any]:
        """Transform customer data."""
        # Date conversion helper
        def to_unix_ms(date_str: Optional[str]) -> Optional[int]:
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            except:
                return None
        
        # Phone formatting helper (E.164)
        def format_phone(phone: Optional[str]) -> Optional[str]:
            if not phone:
                return None
            # Remove non-numeric characters
            digits = ''.join(c for c in phone if c.isdigit())
            if len(digits) == 10:
                return f"+1{digits}"  # Assume North America
            return phone
        
        # Build HubSpot properties
        properties = {
            # PRIMARY ID
            "epicor_customer_number": epicor_customer.get("CustNum"),
            "epicor_customer_code": epicor_customer.get("CustID"),
            
            # Standard properties
            "name": epicor_customer.get("Name"),
            "address": epicor_customer.get("Address1"),
            "address2": epicor_customer.get("Address2"),
            "city": epicor_customer.get("City"),
            "state": epicor_customer.get("State"),
            "zip": epicor_customer.get("Zip"),
            "country": epicor_customer.get("Country"),
            "phone": format_phone(epicor_customer.get("PhoneNum")),
            
            # Custom properties
            "fax_number": epicor_customer.get("FaxNum"),
            "epicor_email": epicor_customer.get("EmailAddress"),
            "payment_terms": epicor_customer.get("TermsCode"),
            "credit_hold_status": epicor_customer.get("CreditHold"),
            "territory": epicor_customer.get("TerritoryID"),
            "currency_code": epicor_customer.get("CurrencyCode"),
            "epicor_sysrowid": str(epicor_customer.get("SysRowID", ""))
        }
        
        # Remove None values
        return {k: v for k, v in properties.items() if v is not None}
```

**Create similar transformers for:**
- `contact_transformer.py`
- `quote_transformer.py`
- `order_transformer.py`
- `part_transformer.py`

---

### Phase 4: Sync Modules (20 hours)

Create sync modules for each entity type. Example for Customers:

#### `src/sync/sync_customers.py`

```python
"""Customer synchronization module."""
import logging
from typing import List, Dict, Any
from ..clients.epicor_client import EpicorClient
from ..clients.hubspot_client import HubSpotClient
from ..transformers.customer_transformer import CustomerTransformer


class CustomerSync:
    """Synchronize customers from Epicor to HubSpot."""
    
    def __init__(self, epicor_client: EpicorClient, hubspot_client: HubSpotClient):
        """Initialize customer sync."""
        self.epicor = epicor_client
        self.hubspot = hubspot_client
        self.transformer = CustomerTransformer()
        self.logger = logging.getLogger(__name__)
    
    def sync(self) -> Dict[str, int]:
        """Sync all customers."""
        stats = {
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "errors": 0
        }
        
        try:
            # 1. Fetch from Epicor
            self.logger.info("Fetching customers from Epicor...")
            customers = self.epicor.get_customers()
            stats["fetched"] = len(customers)
            self.logger.info(f"Fetched {stats['fetched']} customers")
            
            # 2. Process each customer
            for customer in customers:
                try:
                    self._sync_customer(customer, stats)
                except Exception as e:
                    self.logger.error(f"Error syncing customer {customer.get('CustNum')}: {e}")
                    stats["errors"] += 1
            
            self.logger.info(f"Customer sync complete: {stats}")
            return stats
            
        except Exception as e:
            self.logger.error(f"Customer sync failed: {e}")
            raise
    
    def _sync_customer(self, customer: Dict[str, Any], stats: Dict[str, int]):
        """Sync a single customer."""
        # Transform data
        hs_properties = self.transformer.transform(customer)
        
        # Search for existing company by epicor_customer_number
        epicor_num = customer.get("CustNum")
        filter_groups = [{
            "filters": [{
                "propertyName": "epicor_customer_number",
                "operator": "EQ",
                "value": str(epicor_num)
            }]
        }]
        
        existing = self.hubspot.search_companies(filter_groups)
        
        if existing:
            # Update existing company
            company_id = existing[0]['id']
            self.hubspot.update_company(company_id, hs_properties)
            stats["updated"] += 1
            self.logger.debug(f"Updated company {company_id}")
        else:
            # Create new company
            result = self.hubspot.create_company(hs_properties)
            stats["created"] += 1
            self.logger.debug(f"Created company {result['id']}")
```

**Create similar sync modules for:**
- `sync_contacts.py` (with association to companies)
- `sync_quotes.py` (with line items and associations)
- `sync_orders.py` (with line items and associations)
- `sync_parts.py`

---

### Phase 5: Sync Manager (8 hours)

#### `src/sync/sync_manager.py`

```python
"""Main synchronization manager."""
import logging
from typing import Dict
from ..config import Settings
from ..clients.epicor_client import EpicorClient
from ..clients.hubspot_client import HubSpotClient
from .sync_customers import CustomerSync
from .sync_contacts import ContactSync
from .sync_quotes import QuoteSync
from .sync_orders import OrderSync
from .sync_parts import PartSync


class SyncManager:
    """Orchestrate all sync operations."""
    
    def __init__(self, settings: Settings):
        """Initialize sync manager."""
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        
        # Initialize clients
        self.epicor = EpicorClient(
            base_url=settings.epicor_base_url,
            company=settings.epicor_company,
            username=settings.epicor_username,
            password=settings.epicor_password,
            api_key=settings.epicor_api_key
        )
        
        self.hubspot = HubSpotClient(api_key=settings.hubspot_api_key)
        
        # Initialize sync modules
        self.customer_sync = CustomerSync(self.epicor, self.hubspot)
        self.contact_sync = ContactSync(self.epicor, self.hubspot)
        self.quote_sync = QuoteSync(self.epicor, self.hubspot, 
                                    settings.hubspot_quotes_pipeline_id)
        self.order_sync = OrderSync(self.epicor, self.hubspot,
                                    settings.hubspot_orders_pipeline_id)
        self.part_sync = PartSync(self.epicor, self.hubspot)
    
    def run_daily_sync(self) -> Dict[str, Any]:
        """Run complete daily synchronization."""
        self.logger.info("=" * 80)
        self.logger.info("STARTING DAILY SYNC")
        self.logger.info("=" * 80)
        
        results = {}
        
        try:
            # Test connections first
            if not self.epicor.test_connection():
                raise Exception("Epicor connection failed")
            if not self.hubspot.test_connection():
                raise Exception("HubSpot connection failed")
            
            # Sync in order (respecting dependencies)
            
            # 1. Parts (independent)
            if self.settings.sync_parts:
                self.logger.info("\n--- Syncing Parts ---")
                results["parts"] = self.part_sync.sync()
            
            # 2. Customers (independent)
            if self.settings.sync_customers:
                self.logger.info("\n--- Syncing Customers ---")
                results["customers"] = self.customer_sync.sync()
            
            # 3. Contacts (depends on customers)
            if self.settings.sync_contacts:
                self.logger.info("\n--- Syncing Contacts ---")
                results["contacts"] = self.contact_sync.sync()
            
            # 4. Quotes (depends on customers and parts)
            if self.settings.sync_quotes:
                self.logger.info("\n--- Syncing Quotes ---")
                results["quotes"] = self.quote_sync.sync()
            
            # 5. Orders (depends on customers and parts)
            if self.settings.sync_orders:
                self.logger.info("\n--- Syncing Orders ---")
                results["orders"] = self.order_sync.sync()
            
            self.logger.info("\n" + "=" * 80)
            self.logger.info("SYNC COMPLETED SUCCESSFULLY")
            self.logger.info("=" * 80)
            self.logger.info(f"Results: {results}")
            
            return {
                "status": "success",
                "results": results
            }
            
        except Exception as e:
            self.logger.error(f"Sync failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "results": results
            }
```

---

### Phase 6: Lambda Handler (4 hours)

#### `src/main.py`

```python
"""AWS Lambda handler for Epicor-HubSpot sync."""
import logging
import json
from typing import Dict, Any
from .config import get_settings
from .sync.sync_manager import SyncManager
from .utils.logger import setup_logging


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function handler."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Lambda function invoked")
    logger.info(f"Event: {json.dumps(event)}")
    
    try:
        # Load settings
        settings = get_settings()
        
        # Run sync
        manager = SyncManager(settings)
        results = manager.run_daily_sync()
        
        return {
            "statusCode": 200,
            "body": json.dumps(results)
        }
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e)
            })
        }


# For local testing
if __name__ == "__main__":
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))
```

---

### Phase 7: Utilities (3 hours)

#### `src/utils/logger.py`

```python
"""Logging configuration."""
import logging
import sys


def setup_logging(level: str = "INFO"):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
```

#### `src/utils/date_utils.py`

```python
"""Date utility functions."""
from datetime import datetime
from typing import Optional


def epicor_to_unix_ms(date_str: Optional[str]) -> Optional[int]:
    """Convert Epicor datetime string to Unix milliseconds."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return int(dt.timestamp() * 1000)
    except:
        return None


def format_epicor_date(date_str: Optional[str]) -> Optional[str]:
    """Format Epicor date for display."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except:
        return date_str
```

---

### Phase 8: Testing (15 hours)

#### `tests/conftest.py`

```python
"""Pytest configuration and fixtures."""
import pytest
from unittest.mock import Mock
from src.config import Settings


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.epicor_base_url = "https://test.epicor.com"
    settings.epicor_company = "TEST"
    settings.epicor_username = "test_user"
    settings.epicor_password = "test_pass"
    settings.epicor_api_key = "test_key"
    settings.hubspot_api_key = "test_hubspot_key"
    settings.batch_size = 100
    return settings


@pytest.fixture
def sample_customer():
    """Sample Epicor customer data."""
    return {
        "CustNum": 123,
        "CustID": "ABC123",
        "Name": "Test Company",
        "Address1": "123 Main St",
        "City": "Toronto",
        "State": "ON",
        "Zip": "M1M 1M1",
        "Country": "Canada",
        "PhoneNum": "416-555-0123",
        "EmailAddress": "test@company.com",
        "SysRowID": "abc-123-def"
    }
```

#### `tests/test_customer_transformer.py`

```python
"""Test customer transformer."""
import pytest
from src.transformers.customer_transformer import CustomerTransformer


def test_customer_transform(sample_customer):
    """Test customer transformation."""
    transformer = CustomerTransformer()
    result = transformer.transform(sample_customer)
    
    assert result["epicor_customer_number"] == 123
    assert result["epicor_customer_code"] == "ABC123"
    assert result["name"] == "Test Company"
    assert result["city"] == "Toronto"
```

Create comprehensive test suites for all modules.

---

### Phase 9: Deployment (10 hours)

#### `scripts/deploy.sh`

```bash
#!/bin/bash
# AWS Lambda deployment script

echo "Building deployment package..."

# Create clean directory
rm -rf build/
mkdir -p build/

# Copy source code
cp -r src/ build/

# Install dependencies
pip install -r requirements.txt -t build/

# Create ZIP
cd build/
zip -r ../aws/lambda_function.zip .
cd ..

echo "Deploying to AWS Lambda..."

# Deploy (update with your function name)
aws lambda update-function-code \
    --function-name epicor-hubspot-sync \
    --zip-file fileb://aws/lambda_function.zip

echo "Deployment complete!"
```

#### `aws/cloudformation.yml`

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Epicor-HubSpot Integration Infrastructure'

Resources:
  SyncFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: epicor-hubspot-sync
      Runtime: python3.11
      Handler: src.main.lambda_handler
      Role: !GetAtt LambdaExecutionRole.Arn
      Timeout: 900  # 15 minutes
      MemorySize: 512
      Environment:
        Variables:
          LOG_LEVEL: INFO
  
  DailySchedule:
    Type: AWS::Events::Rule
    Properties:
      Description: 'Trigger sync daily at 2 AM EST'
      ScheduleExpression: 'cron(0 7 * * ? *)'  # 2 AM EST = 7 AM UTC
      State: ENABLED
      Targets:
        - Arn: !GetAtt SyncFunction.Arn
          Id: SyncFunctionTarget
  
  LambdaInvokePermission:
    Type: AWS::Lambda::Permission
    Properties:
      FunctionName: !Ref SyncFunction
      Action: 'lambda:InvokeFunction'
      Principal: events.amazonaws.com
      SourceArn: !GetAtt DailySchedule.Arn
  
  LambdaExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: 'sts:AssumeRole'
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
      Policies:
        - PolicyName: S3Access
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 's3:PutObject'
                  - 's3:GetObject'
                Resource: 'arn:aws:s3:::epicor-hubspot-sync-logs/*'
  
  LogBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: epicor-hubspot-sync-logs
      VersioningConfiguration:
        Status: Enabled
```

---

## 📊 TESTING STRATEGY

### Unit Tests
```bash
# Run all tests
pytest tests/ -v --cov=src

# Run specific test file
pytest tests/test_customer_transformer.py -v

# Generate coverage report
pytest --cov=src --cov-report=html
```

### Integration Tests
Create `scripts/test_connection.py`:
```python
"""Test API connections."""
from src.config import get_settings
from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient

settings = get_settings()

# Test Epicor
epicor = EpicorClient(
    settings.epicor_base_url,
    settings.epicor_company,
    settings.epicor_username,
    settings.epicor_password,
    settings.epicor_api_key
)
print("Testing Epicor connection...")
assert epicor.test_connection()
print("✓ Epicor connected")

# Test HubSpot
hubspot = HubSpotClient(settings.hubspot_api_key)
print("Testing HubSpot connection...")
assert hubspot.test_connection()
print("✓ HubSpot connected")

print("\n✓ All connections successful!")
```

---

## 🚀 DEPLOYMENT STEPS

1. **Set up AWS environment**
   ```bash
   # Configure AWS CLI
   aws configure
   
   # Create S3 bucket for logs
   aws s3 mb s3://epicor-hubspot-sync-logs
   ```

2. **Store secrets in AWS Secrets Manager**
   ```bash
   aws secretsmanager create-secret \
       --name epicor-hubspot-integration \
       --secret-string file://secrets.json
   ```

3. **Deploy infrastructure**
   ```bash
   aws cloudformation deploy \
       --template-file aws/cloudformation.yml \
       --stack-name epicor-hubspot-stack \
       --capabilities CAPABILITY_IAM
   ```

4. **Deploy Lambda function**
   ```bash
   ./scripts/deploy.sh
   ```

5. **Test Lambda function**
   ```bash
   aws lambda invoke \
       --function-name epicor-hubspot-sync \
       --payload '{}' \
       response.json
   
   cat response.json
   ```

---

## 📋 MILESTONE CHECKLIST

Following Collins' 190-hour scope:

- [ ] **Milestone 1: Discovery & Requirements** (20 hours) - COMPLETE
- [ ] **Milestone 2: System Design & Architecture** (25 hours) - COMPLETE
- [ ] **Milestone 3: Historical Data Migration Plan** (30 hours)
  - [ ] Design migration strategy
  - [ ] Data cleansing scripts
  - [ ] Historical import scripts
- [ ] **Milestone 4: One-Way Sync Development** (40 hours)
  - [ ] Build integration
  - [ ] Job scheduler
  - [ ] Error logging
- [ ] **Milestone 5: Testing & Validation** (35 hours)
  - [ ] Unit tests
  - [ ] Integration tests
  - [ ] Performance tests
  - [ ] Stakeholder review
- [ ] **Milestone 6: Deployment & Training** (20 hours)
  - [ ] Production deployment
  - [ ] Team training
  - [ ] Documentation
- [ ] **Milestone 7: Post-Deployment Support** (20 hours)
  - [ ] Monitor syncs
  - [ ] Optimize performance
  - [ ] User feedback

---

## 🔧 MAKEFILE

Create `Makefile` for common commands:

```makefile
.PHONY: help setup test run deploy clean

help:
	@echo "Available commands:"
	@echo "  make setup    - Set up development environment"
	@echo "  make test     - Run all tests"
	@echo "  make run      - Run sync locally"
	@echo "  make deploy   - Deploy to AWS"
	@echo "  make clean    - Clean up generated files"

setup:
	python3.11 -m venv venv
	./venv/bin/pip install -r requirements.txt
	./venv/bin/pip install -r requirements-dev.txt
	cp .env.example .env

test:
	pytest tests/ -v --cov=src

run:
	python -m src.main

format:
	black src/ tests/
	isort src/ tests/

lint:
	pylint src/
	mypy src/

deploy:
	./scripts/deploy.sh

clean:
	rm -rf build/
	rm -rf aws/lambda_function.zip
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
```

---

## 📝 README.md TEMPLATE

```markdown
# Epicor-HubSpot Integration

One-way data synchronization from Epicor ERP to HubSpot CRM for PLP Canada.

## Quick Start

1. Clone repository
2. Run `make setup`
3. Configure `.env` file
4. Run `make test`
5. Run `make run` (local test)
6. Run `make deploy` (AWS deployment)

## Architecture

- **Source:** Epicor REST API v2 (OData v4)
- **Target:** HubSpot REST API v3/v4
- **Runtime:** AWS Lambda (Python 3.11)
- **Schedule:** Daily at 2 AM EST

## Data Flow

Customers → Contacts → Parts → Quotes → Orders

## Development

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
make test

# Format code
make format

# Run locally
python -m src.main
```

## Deployment

```bash
# Deploy to AWS Lambda
make deploy

# View logs
aws logs tail /aws/lambda/epicor-hubspot-sync --follow
```

## Support

Contact: [Your contact info]
```

---

## 🎯 CRITICAL SUCCESS FACTORS

1. **HubSpot Custom Properties**: ALL custom properties MUST be created in HubSpot before sync
2. **Pipeline IDs**: Both Quotes and Orders pipeline IDs must be configured
3. **API Keys**: Both Epicor API key and HubSpot API key required
4. **Sync Order**: Must sync in order: Parts → Customers → Contacts → Quotes/Orders
5. **Error Handling**: Robust error logging to S3 for debugging
6. **Rate Limiting**: Respect HubSpot rate limits (100 req/10 sec)
7. **Pagination**: Handle Epicor pagination with $top and $skip
8. **Associations**: Create associations AFTER creating objects

---

## 📞 NEXT STEPS

1. Create HubSpot account and generate API key
2. Create all custom properties in HubSpot (see mapping document)
3. Create two pipelines: "Quotes" and "Orders"
4. Generate Epicor API key
5. Test API connections using `scripts/test_connection.py`
6. Run initial sync in development environment
7. Validate data in HubSpot
8. Deploy to production
9. Monitor daily syncs

---

**END OF INSTRUCTIONS**

This document provides complete implementation instructions following Collins' 190-hour scope. All technical specifications are based on the official Epicor REST API documentation and HubSpot API requirements.
