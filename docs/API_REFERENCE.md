# API Reference - Epicor-HubSpot Integration

This document provides detailed information about the modules, classes, and functions in the Epicor-HubSpot integration.

---

## Table of Contents

- [Configuration](#configuration)
- [Transformers](#transformers)
- [Sync Modules](#sync-modules)
- [Stage Logic](#stage-logic)
- [Utilities](#utilities)

---

## Configuration

### Settings Class (`src/config.py`)

Main configuration class using Pydantic for environment variable management.

#### Key Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `epicor_base_url` | str | Yes | Epicor API base URL |
| `epicor_company` | str | Yes | Epicor company ID |
| `epicor_username` | str | Yes | Epicor API username |
| `epicor_password` | str | Yes | Epicor API password |
| `epicor_api_key` | str | Yes | Epicor API key |
| `hubspot_api_key` | str | Yes | HubSpot private app token |
| `hubspot_quotes_pipeline_id` | str | Yes | HubSpot quotes pipeline ID |
| `hubspot_orders_pipeline_id` | str | Yes | HubSpot orders pipeline ID |
| `sync_batch_size` | int | No (default: 100) | Batch processing size |
| `sync_max_retries` | int | No (default: 3) | Max retry attempts |
| `sync_customers` | bool | No (default: True) | Enable customer sync |
| `sync_quotes` | bool | No (default: True) | Enable quote sync |
| `sync_orders` | bool | No (default: True) | Enable order sync |

#### Methods

**`get_hubspot_owner(sales_rep_code: str) -> Optional[str]`**

Maps Epicor sales rep code to HubSpot owner ID using `config/sales_rep_mapping.json`.

- **Parameters:**
  - `sales_rep_code`: Epicor sales rep code
- **Returns:** HubSpot owner ID or None
- **Fallback:** Uses `default_owner_id` from mapping file if rep not found

### Pipelines Class (`src/config.py`)

Helper class for accessing HubSpot pipeline IDs.

**`Pipelines.get_quotes_pipeline_id() -> str`**
- Returns the configured quotes pipeline ID

**`Pipelines.get_orders_pipeline_id() -> str`**
- Returns the configured orders pipeline ID

---

## Transformers

All transformers extend `BaseTransformer` and convert Epicor data to HubSpot format.

### CustomerTransformer (`src/transformers/customer_transformer.py`)

Transforms Epicor Customer � HubSpot Company

**Field Mapping (14 fields):**

| Epicor Field | HubSpot Property | Notes |
|--------------|------------------|-------|
| `CustNum` | `epicor_customer_number` | Primary matching key |
| `CustID` | `epicor_customer_code` | Business identifier |
| `Name` | `name` | Required |
| `Address1` | `address` | |
| `Address2` | `address2` | |
| `City` | `city` | |
| `State` | `state` | |
| `Zip` | `zip` | |
| `Country` | `country` | |
| `PhoneNum` | `phone` | E.164 formatted |
| `FaxNum` | `fax_number` | |
| `EmailAddress` | `epicor_email` | |
| `CurrencyCode` | `currency_code` | |
| `SysRowID` | `epicor_sysrowid` | GUID converted to string |

**Methods:**

- `transform(customer_data: Dict) -> Dict` - Transform customer data
- `get_customer_num(customer_data: Dict) -> int` - Extract customer number

### QuoteTransformer (`src/transformers/quote_transformer.py`)

Transforms Epicor Quote � HubSpot Deal (Quotes Pipeline)

**Field Mapping (21 fields):**

| Epicor Field | HubSpot Property | Notes |
|--------------|------------------|-------|
| `QuoteNum` | `dealname`, `epicor_quote_number` | Deal name and primary key |
| `CustNum` | (association) | Links to company |
| `EntryDate` | `createdate` | Unix ms timestamp |
| `DueDate` | `closedate` | Unix ms timestamp |
| `ExpirationDate` | `quote_expiration_date` | Unix ms timestamp |
| `DateQuoted` | `quote_sent_date` | Unix ms timestamp |
| `QuoteAmt` | `amount` | |
| `DocQuoteAmt` | `epicor_doc_amount` | |
| `PONum` | `customer_po_number` | |
| `Quoted`, `QuoteClosed`, `Ordered`, `Expired` | `dealstage` | Via stage logic |
| `Quoted` | `epicor_quoted` | Boolean flag |
| `QuoteClosed` | `epicor_closed` | Boolean flag |
| `Ordered` | `epicor_converted_to_order` | Boolean flag |
| `Expired` | `epicor_expired` | Boolean flag |
| `DiscountPercent` | `discount_percentage` | |
| `CurrencyCode` | `deal_currency_code_` | |
| `SysRowID` | `epicor_quote_sysrowid` | GUID string |
| `SalesRepCode` | `epicor_sales_rep_code` | |
| `SalesRepCode` | `hubspot_owner_id` | If mapped |
| (hardcoded) | `pipeline` | Quotes pipeline ID |

**Methods:**

- `transform(quote_data: Dict, current_hubspot_stage: Optional[str]) -> Dict`
  - Transforms quote with stage logic
  - Parameters:
    - `quote_data`: Epicor quote record
    - `current_hubspot_stage`: Current stage in HubSpot (None if new)
- `get_customer_num(quote_data: Dict) -> int` - Extract customer number for association

### OrderTransformer (`src/transformers/order_transformer.py`)

Transforms Epicor SalesOrder � HubSpot Deal (Orders Pipeline)

**Field Mapping (13 fields):**

| Epicor Field | HubSpot Property | Notes |
|--------------|------------------|-------|
| `OrderNum` | `dealname`, `epicor_order_number` | Deal name and primary key |
| `CustNum` | (association) | Links to company |
| `OrderDate` | `createdate` | Unix ms timestamp |
| `RequestDate` | `closedate` | Unix ms timestamp |
| `NeedByDate` | `need_by_date` | Unix ms timestamp |
| `OrderAmt` | `amount` | |
| `DocOrderAmt` | `epicor_doc_amount` | |
| `PONum` | `customer_po_number` | |
| `OpenOrder` | `epicor_open_order` | Boolean flag |
| `CurrencyCode` | `deal_currency_code_` | |
| `SysRowID` | `epicor_order_sysrowid` | GUID string |
| (hardcoded) | `pipeline` | Orders pipeline ID |
| `VoidOrder`, `OrderHeld`, `TotalShipped`, `OpenOrder` | `dealstage` | Via stage logic (NOT synced as properties) |

**Methods:**

- `transform(order_data: Dict) -> Dict` - Transform order data
- `get_customer_num(order_data: Dict) -> int` - Extract customer number

### LineItemTransformer (`src/transformers/line_item_transformer.py`)

Transforms Epicor QuoteDtl/OrderDtl � HubSpot Line Items

**Methods:**

- `transform_quote_line(line_data: Dict) -> Dict` - Transform QuoteDtl
- `transform_order_line(line_data: Dict) -> Dict` - Transform OrderDtl
- `get_minimal_product_properties(part_num: str, line_desc: Optional[str]) -> Dict`
  - Creates minimal product properties for auto-creation

---

## Sync Modules

### CustomerSync (`src/sync/customer_sync.py`)

**Methods:**

- `sync_all_customers() -> Dict` - Syncs all customers, returns summary
- `sync_customer(customer_data: Dict) -> str` - Returns: 'created', 'updated', or 'error'

### QuoteSync (`src/sync/quote_sync.py`)

**Methods:**

- `sync_all_quotes(filter_condition: Optional[str]) -> Dict` - Syncs quotes with optional OData filter
- `sync_quote(quote_data: Dict) -> str` - Syncs single quote with stage logic

### OrderSync (`src/sync/order_sync.py`)

**Methods:**

- `sync_all_orders(filter_condition: Optional[str]) -> Dict` - Syncs orders
- `sync_order(order_data: Dict) -> str` - Syncs single order

### LineItemSync (`src/sync/line_item_sync.py`)

**Methods:**

- `sync_quote_line_items(deal_id: str, line_items: List) -> Dict` - Auto-creates products
- `sync_order_line_items(deal_id: str, line_items: List) -> Dict` - Auto-creates products
- `ensure_product_exists(sku: str, name: Optional[str]) -> bool` - Returns True if created

### SyncManager (`src/sync/sync_manager.py`)

**Methods:**

- `run_full_sync() -> Dict` - Orchestrates all sync operations in order

---

## Stage Logic

### Quote Pipeline (7 Stages)

| Stage | Internal Name | Type |
|-------|---------------|------|
| Quote Created (20%) | `quote_created` | Open |
| Technical Review (30%) | `technical_review` | HubSpot-only |
| Quote Sent (40%) | `quote_sent` | Open |
| Follow Up (50%) | `follow_up` | HubSpot-only |
| Quote Expired (0%) | `quote_expired` | Reversible terminal |
| Closed Won (100%) | `closedwon` | Permanent terminal |
| Closed Lost (0%) | `closedlost` | Permanent terminal |

**Stage Derivation Priority:**
1. `Ordered=true` � `closedwon`
2. `Expired=true` � `quote_expired`
3. `QuoteClosed=true AND Ordered=false` � `closedlost`
4. `Quoted=true` � `quote_sent`
5. Default � `quote_created`

**Update Rules:**
- New deal � Always set
- Terminal from Epicor � Always update
- Permanent terminals � Cannot reopen
- Reversible terminal � Can reactivate
- Forward only � Never backward

### Order Pipeline (5 Stages)

| Stage | Internal Name | Condition |
|-------|---------------|-----------|
| Order Received | `order_received` | Default |
| Order Held | `order_held` | `OrderHeld=true` |
| Partially Shipped | `partially_shipped` | `TotalShipped>0` |
| Completed | `completed` | `OpenOrder=false` |
| Cancelled | `cancelled` | `VoidOrder=true` |

---

## Utilities

### Date Utilities (`src/utils/date_utils.py`)

- `epicor_datetime_to_unix_ms(date_str) -> int` - ISO to Unix ms
- `guid_to_string(guid) -> str` - GUID formatting
- `format_phone_e164(phone) -> str` - E.164 phone format

### Error Handler (`src/utils/error_handler.py`)

- `ErrorTracker` - Tracks errors during sync

### Logger (`src/utils/logger.py`)

- `setup_logger(name, level) -> Logger` - Creates logger

---

*Last Updated: November 13, 2025*
