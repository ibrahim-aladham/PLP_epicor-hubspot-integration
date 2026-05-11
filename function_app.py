"""
Azure Functions entry point for Epicor-HubSpot integration.

Provides two triggers:
- Timer trigger: Runs daily at 2 AM EST (7 AM UTC)
- HTTP trigger: For manual invocation
"""

import azure.functions as func
import logging
import json
from datetime import datetime

app = func.FunctionApp()

logger = logging.getLogger(__name__)


@app.timer_trigger(
    schedule="0 0 11-22 * * *",
    arg_name="timer",
    run_on_startup=False
)
def scheduled_sync(timer: func.TimerRequest) -> None:
    """
    Timer-triggered sync that runs hourly from 7 AM to 5 PM ET (11-22 UTC covers both EST and EDT).
    """
    from src.config import load_secrets_from_cloud, get_settings
    from src.main import main
    from src.utils.logger import setup_logging

    logger.info("Timer trigger fired for Epicor-HubSpot sync")

    if timer.past_due:
        logger.warning("Timer is past due — running sync anyway")

    try:
        load_secrets_from_cloud()
        settings = get_settings(force_reload=True)
        setup_logging(settings.log_level)

        result = main(delta_hours=16)
        logger.info(f"Scheduled sync completed: {json.dumps(result, default=str)}")

    except Exception as e:
        logger.error(f"Scheduled sync failed: {e}", exc_info=True)
        raise



@app.route(route="sync", auth_level=func.AuthLevel.FUNCTION)
def manual_sync(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP-triggered sync for manual invocation.

    GET or POST /api/sync
    """
    from src.config import load_secrets_from_cloud, get_settings
    from src.main import main
    from src.utils.logger import setup_logging

    logger.info("HTTP trigger received for Epicor-HubSpot sync")

    try:
        load_secrets_from_cloud()
        settings = get_settings(force_reload=True)
        setup_logging(settings.log_level)

        # Support query params: ?full_sync=true&delta_hours=16&skip_customers=true
        # Year range: ?start_year=2023&end_year=2024 (uses EntryDate filter)
        full_sync = req.params.get('full_sync', '').lower() == 'true'
        delta_hours = int(req.params.get('delta_hours', '16'))
        start_year = req.params.get('start_year')
        end_year = req.params.get('end_year')

        # Allow skipping phases to stay within 30-min timeout
        if req.params.get('skip_customers', '').lower() == 'true':
            settings.sync_customers = False
        if req.params.get('skip_quotes', '').lower() == 'true':
            settings.sync_quotes = False
        if req.params.get('skip_orders', '').lower() == 'true':
            settings.sync_orders = False

        # Build year range filter if specified
        year_filter = None
        if start_year:
            sy = int(start_year)
            ey = int(end_year) if end_year else sy
            start_date = f"{sy}-01-01T00:00:00Z"
            end_date = f"{ey + 1}-01-01T00:00:00Z"
            year_filter = f"EntryDate ge {start_date} and EntryDate lt {end_date}"
            full_sync = True  # year range implies full sync mode
            logger.info(f"Year range filter: {year_filter}")

        result = main(full_sync=full_sync, delta_hours=delta_hours, filter_condition=year_filter)

        return func.HttpResponse(
            body=json.dumps({
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "result": result
            }, default=str),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logger.error(f"Manual sync failed: {e}", exc_info=True)
        return func.HttpResponse(
            body=json.dumps({
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="fix-associations", auth_level=func.AuthLevel.FUNCTION)
def fix_associations(req: func.HttpRequest) -> func.HttpResponse:
    """
    Temporary endpoint to fix deals missing company associations.
    Scans HubSpot for deals without company links, looks up customer
    from Epicor, and creates the association using v3 API.

    GET /api/fix-associations?type=quotes  (or type=orders, default=both)
    Optional: &min=309500&max=310100 to limit to a number range.

    Remove after all associations are fixed.
    """
    from src.config import load_secrets_from_cloud, get_settings
    from src.clients.epicor_client import EpicorClient
    from src.clients.hubspot_client import HubSpotClient
    from src.utils.logger import setup_logging
    import requests as req_lib

    logger.info("Fix-associations endpoint triggered")

    try:
        load_secrets_from_cloud()
        settings = get_settings(force_reload=True)
        setup_logging(settings.log_level)

        epicor = EpicorClient(
            base_url=settings.epicor_base_url,
            company=settings.epicor_company,
            username=settings.epicor_username,
            password=settings.epicor_password,
            api_key=settings.epicor_api_key,
        )
        hubspot = HubSpotClient(api_key=settings.hubspot_api_key)

        fix_type = req.params.get('type', 'both')
        hs_headers = {
            "Authorization": f"Bearer {settings.hubspot_api_key}",
            "Content-Type": "application/json"
        }
        hs_base = "https://api.hubapi.com"
        results = {"quotes_fixed": 0, "orders_fixed": 0, "skipped": 0, "errors": []}

        range_min = req.params.get('min')
        range_max = req.params.get('max')

        def fix_deals(property_name, label):
            fixed = 0
            skipped = 0
            after = None

            while True:
                # Build filters — optionally restrict to a number range
                filters = [{"propertyName": property_name, "operator": "HAS_PROPERTY"}]
                if range_min:
                    filters.append({"propertyName": property_name, "operator": "GTE", "value": range_min})
                if range_max:
                    filters.append({"propertyName": property_name, "operator": "LTE", "value": range_max})

                body = {
                    "filterGroups": [{"filters": filters}],
                    "properties": [property_name, "dealname"],
                    "limit": 100,
                }
                if after:
                    body["after"] = after

                resp = req_lib.post(f"{hs_base}/crm/v3/objects/deals/search",
                    headers=hs_headers, json=body, timeout=30).json()
                deals = resp.get('results', [])
                if not deals:
                    break

                for deal in deals:
                    deal_id = deal['id']
                    deal_name = deal.get('properties', {}).get('dealname', '')
                    entity_num = deal.get('properties', {}).get(property_name)

                    # Check if association exists
                    try:
                        assoc = req_lib.get(
                            f"{hs_base}/crm/v3/objects/deals/{deal_id}/associations/companies",
                            headers=hs_headers, timeout=10
                        ).json()
                        if assoc.get('results'):
                            skipped += 1
                            continue
                    except Exception:
                        continue

                    # Look up customer from Epicor
                    try:
                        if label == 'quote':
                            records = epicor.get_quotes(
                                filter_condition=f"QuoteNum eq {entity_num}",
                                expand_line_items=False
                            )
                        else:
                            records = epicor.get_orders(
                                filter_condition=f"OrderNum eq {entity_num}",
                                expand_line_items=False
                            )

                        if not records:
                            results["errors"].append(f"{deal_name}: not found in Epicor")
                            continue

                        cust_num = records[0].get('CustNum')
                        if not cust_num and cust_num != 0:
                            results["errors"].append(f"{deal_name}: no CustNum")
                            continue

                        company = hubspot.get_company_by_property('epicor_customer_number', cust_num)
                        if not company:
                            results["errors"].append(f"{deal_name}: company {cust_num} not in HubSpot")
                            continue

                        hubspot.associate_deal_to_company(deal_id, company['id'])
                        fixed += 1
                        logger.info(f"Fixed: {deal_name} -> company {cust_num}")

                    except Exception as e:
                        results["errors"].append(f"{deal_name}: {str(e)[:100]}")

                after = resp.get('paging', {}).get('next', {}).get('after')
                if not after:
                    break
                logger.info(f"[{label}] Fixed {fixed}, skipped {skipped}, page after={after}")

            results["skipped"] += skipped
            return fixed

        if fix_type in ('quotes', 'both'):
            logger.info("Fixing quote associations...")
            results["quotes_fixed"] = fix_deals('epicor_quote_number', 'quote')

        if fix_type in ('orders', 'both'):
            logger.info("Fixing order associations...")
            results["orders_fixed"] = fix_deals('epicor_order_number', 'order')

        logger.info(f"Fix-associations complete: {json.dumps(results, default=str)}")
        return func.HttpResponse(
            body=json.dumps(results, default=str, indent=2),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logger.error(f"Fix-associations failed: {e}", exc_info=True)
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )


def _get_blob_service():
    """Return BlobServiceClient using storage connection string (managed identity-aware)."""
    from azure.storage.blob import BlobServiceClient
    from azure.identity import DefaultAzureCredential
    import os
    # Try connection string first (works with AzureWebJobsStorage)
    conn_str = os.environ.get('AzureWebJobsStorage')
    if conn_str and 'AccountKey=' in conn_str:
        return BlobServiceClient.from_connection_string(conn_str)
    # Fall back to managed identity
    storage_account = os.environ.get('AzureWebJobsStorage__accountName') or 'epicorhssynceaststore'
    return BlobServiceClient(
        account_url=f"https://{storage_account}.blob.core.windows.net",
        credential=DefaultAzureCredential()
    )


def _read_checkpoint_blob(blob_name: str):
    """Read JSON blob from diff-results container. Returns None if missing."""
    try:
        client = _get_blob_service().get_container_client("diff-results")
        try:
            client.create_container()
        except Exception:
            pass
        blob = client.get_blob_client(blob_name)
        if not blob.exists():
            return None
        return json.loads(blob.download_blob().readall())
    except Exception as e:
        logger.warning(f"Could not read blob {blob_name}: {e}")
        return None


def _write_checkpoint_blob(blob_name: str, data: dict):
    """Write JSON blob to diff-results container."""
    client = _get_blob_service().get_container_client("diff-results")
    try:
        client.create_container()
    except Exception:
        pass
    client.upload_blob(
        blob_name,
        json.dumps(data, default=str),
        overwrite=True
    )


@app.route(route="diff-expired-quotes", auth_level=func.AuthLevel.FUNCTION)
def diff_expired_quotes(req: func.HttpRequest) -> func.HttpResponse:
    """
    Phased diff with checkpointing — survives function timeouts.

    GET /api/diff-expired-quotes?phase=epicor   # fetch Epicor list (resumable)
    GET /api/diff-expired-quotes?phase=hubspot  # fetch HubSpot list (resumable)
    GET /api/diff-expired-quotes?phase=compute  # compute diff from saved blobs

    Each phase saves progress incrementally to blob storage so a partial
    run can resume on the next call.
    """
    from src.config import load_secrets_from_cloud, get_settings
    from src.clients.epicor_client import EpicorClient
    from src.utils.logger import setup_logging
    import requests as req_lib

    phase = req.params.get('phase', 'compute')
    logger.info(f"Diff-expired-quotes triggered (phase={phase})")

    try:
        load_secrets_from_cloud()
        settings = get_settings(force_reload=True)
        setup_logging(settings.log_level)

        EPICOR_BLOB = "epicor-expired.json"
        HUBSPOT_BLOB = "hubspot-expired.json"
        DIFF_BLOB = "diff-result.json"

        if phase == 'epicor':
            return _fetch_epicor_phase(settings, EPICOR_BLOB)

        if phase == 'hubspot':
            return _fetch_hubspot_phase(settings, HUBSPOT_BLOB)

        if phase == 'compute':
            return _compute_diff_phase(EPICOR_BLOB, HUBSPOT_BLOB, DIFF_BLOB, req)

        return func.HttpResponse(
            body=json.dumps({"error": f"unknown phase: {phase}"}),
            mimetype="application/json",
            status_code=400
        )

    except Exception as e:
        logger.error(f"Diff-expired-quotes failed: {e}", exc_info=True)
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )


def _fetch_epicor_phase(settings, blob_name: str) -> func.HttpResponse:
    """Fetch Epicor quotes where Expired=true, using QuoteNum-based pagination.

    Uses `QuoteNum gt <last_seen>` ordered by QuoteNum instead of $skip,
    which avoids slow high-offset queries in Epicor OData.
    """
    import requests as req_lib

    # Resume if checkpoint exists. Backwards-compat: if old checkpoint has
    # 'skip' but no 'last_quote_num', derive last_quote_num from data.
    checkpoint = _read_checkpoint_blob(blob_name) or {
        "quote_nums": [], "last_quote_num": 0, "complete": False
    }
    quote_nums = set(checkpoint["quote_nums"])
    last_quote_num = checkpoint.get("last_quote_num")
    if last_quote_num is None:
        last_quote_num = max(quote_nums) if quote_nums else 0

    if checkpoint.get("complete"):
        logger.info(f"Epicor phase already complete: {len(quote_nums)} quotes")
        return func.HttpResponse(
            body=json.dumps({"status": "already_complete", "count": len(quote_nums)}),
            mimetype="application/json", status_code=200
        )

    logger.info(f"Resuming Epicor fetch from QuoteNum > {last_quote_num}, have {len(quote_nums)} so far")

    base_url = f"{settings.epicor_base_url}/api/v2/odata/{settings.epicor_company}/Erp.BO.QuoteSvc/Quotes"
    auth = (settings.epicor_username, settings.epicor_password)
    headers = {"x-api-key": settings.epicor_api_key}
    page_size = 1000
    pages_this_call = 0
    max_pages = 30

    while pages_this_call < max_pages:
        filter_expr = f"Expired eq true and QuoteNum gt {last_quote_num}"
        params = {
            "$filter": filter_expr,
            "$select": "QuoteNum",
            "$orderby": "QuoteNum",
            "$top": page_size,
        }
        try:
            resp = req_lib.get(base_url, params=params, auth=auth, headers=headers, verify=False, timeout=120)
            resp.raise_for_status()
            records = resp.json().get("value", [])
        except Exception as e:
            logger.warning(f"Epicor fetch failed at QuoteNum>{last_quote_num}: {e}. Saving checkpoint.")
            _write_checkpoint_blob(blob_name, {
                "quote_nums": sorted(quote_nums),
                "last_quote_num": last_quote_num,
                "complete": False
            })
            return func.HttpResponse(
                body=json.dumps({
                    "status": "error", "last_quote_num": last_quote_num,
                    "count": len(quote_nums), "error": str(e)[:200]
                }),
                mimetype="application/json", status_code=200
            )

        if not records:
            _write_checkpoint_blob(blob_name, {
                "quote_nums": sorted(quote_nums),
                "last_quote_num": last_quote_num,
                "complete": True
            })
            logger.warning(f"Epicor fetch COMPLETE: {len(quote_nums)} quotes")
            return func.HttpResponse(
                body=json.dumps({"status": "complete", "count": len(quote_nums)}),
                mimetype="application/json", status_code=200
            )

        page_max = last_quote_num
        for r in records:
            qn = r.get("QuoteNum")
            if qn is not None:
                qn_int = int(qn)
                quote_nums.add(qn_int)
                if qn_int > page_max:
                    page_max = qn_int
        last_quote_num = page_max
        pages_this_call += 1
        logger.info(f"Epicor page {pages_this_call}, last_quote_num={last_quote_num}, total={len(quote_nums)}")

        if pages_this_call % 2 == 0:
            _write_checkpoint_blob(blob_name, {
                "quote_nums": sorted(quote_nums),
                "last_quote_num": last_quote_num,
                "complete": False
            })

        if len(records) < page_size:
            _write_checkpoint_blob(blob_name, {
                "quote_nums": sorted(quote_nums),
                "last_quote_num": last_quote_num,
                "complete": True
            })
            logger.warning(f"Epicor fetch COMPLETE: {len(quote_nums)} quotes")
            return func.HttpResponse(
                body=json.dumps({"status": "complete", "count": len(quote_nums)}),
                mimetype="application/json", status_code=200
            )

    _write_checkpoint_blob(blob_name, {
        "quote_nums": sorted(quote_nums),
        "last_quote_num": last_quote_num,
        "complete": False
    })
    return func.HttpResponse(
        body=json.dumps({
            "status": "partial",
            "last_quote_num": last_quote_num,
            "count": len(quote_nums),
            "message": "Re-invoke to continue"
        }),
        mimetype="application/json", status_code=200
    )


def _fetch_hubspot_phase(settings, blob_name: str) -> func.HttpResponse:
    """Fetch HubSpot deals where epicor_expired=true, saving every 5 pages."""
    import requests as req_lib

    checkpoint = _read_checkpoint_blob(blob_name) or {"quote_nums": [], "after": None, "complete": False}
    quote_nums = set(checkpoint["quote_nums"])
    after = checkpoint["after"]

    if checkpoint.get("complete"):
        logger.info(f"HubSpot phase already complete: {len(quote_nums)} deals")
        return func.HttpResponse(
            body=json.dumps({"status": "already_complete", "count": len(quote_nums)}),
            mimetype="application/json", status_code=200
        )

    logger.info(f"Resuming HubSpot fetch from after={after}, have {len(quote_nums)} so far")

    hs_headers = {
        "Authorization": f"Bearer {settings.hubspot_api_key}",
        "Content-Type": "application/json"
    }
    hs_base = "https://api.hubapi.com"
    pages_this_call = 0
    max_pages = 200

    while pages_this_call < max_pages:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "epicor_quote_number", "operator": "HAS_PROPERTY"},
                {"propertyName": "epicor_expired", "operator": "EQ", "value": "true"}
            ]}],
            "properties": ["epicor_quote_number"],
            "limit": 100,
        }
        if after:
            body["after"] = after

        try:
            resp = req_lib.post(
                f"{hs_base}/crm/v3/objects/deals/search",
                headers=hs_headers, json=body, timeout=30
            ).json()
        except Exception as e:
            logger.warning(f"HubSpot fetch failed at after={after}: {e}. Saving checkpoint.")
            _write_checkpoint_blob(blob_name, {
                "quote_nums": sorted(quote_nums), "after": after, "complete": False
            })
            return func.HttpResponse(
                body=json.dumps({"status": "error", "count": len(quote_nums), "error": str(e)[:200]}),
                mimetype="application/json", status_code=200
            )

        deals = resp.get('results', [])
        for d in deals:
            qn = d.get('properties', {}).get('epicor_quote_number')
            if qn is not None:
                try:
                    quote_nums.add(int(qn))
                except (ValueError, TypeError):
                    pass

        new_after = resp.get('paging', {}).get('next', {}).get('after')
        pages_this_call += 1
        if pages_this_call % 5 == 0:
            logger.info(f"HubSpot page {pages_this_call}, total={len(quote_nums)}")
            _write_checkpoint_blob(blob_name, {
                "quote_nums": sorted(quote_nums), "after": new_after, "complete": False
            })

        if not new_after:
            _write_checkpoint_blob(blob_name, {
                "quote_nums": sorted(quote_nums), "after": None, "complete": True
            })
            logger.warning(f"HubSpot fetch COMPLETE: {len(quote_nums)} deals")
            return func.HttpResponse(
                body=json.dumps({"status": "complete", "count": len(quote_nums)}),
                mimetype="application/json", status_code=200
            )

        after = new_after

    _write_checkpoint_blob(blob_name, {
        "quote_nums": sorted(quote_nums), "after": after, "complete": False
    })
    return func.HttpResponse(
        body=json.dumps({
            "status": "partial", "count": len(quote_nums),
            "message": "Re-invoke to continue"
        }),
        mimetype="application/json", status_code=200
    )


@app.route(route="fix-expired-quotes", auth_level=func.AuthLevel.FUNCTION)
def fix_expired_quotes(req: func.HttpRequest) -> func.HttpResponse:
    """
    Part 2: Apply the fix from diff-result.json.

    Reads the list of QuoteNums needing update, looks up HubSpot deal IDs
    via batch-read, then batch-updates them to set epicor_expired=true and
    move stage to Quote Expired (when safe).

    GET /api/fix-expired-quotes
    Optional: &dry_run=true (no writes; report what would change)

    Checkpoint blob: fix-expired-checkpoint.json
    Tracks: index into diff list, processed counts, errors.
    Safe to re-invoke to resume after timeouts.
    """
    from src.config import load_secrets_from_cloud, get_settings
    from src.utils.logger import setup_logging
    import requests as req_lib

    DIFF_BLOB = "diff-result.json"
    CHECKPOINT_BLOB = "fix-expired-checkpoint.json"
    QUOTE_EXPIRED_STAGE_ID = "2008968145"
    OPEN_STAGES = {"2008968141", "2008968143"}  # Quote Created, Quote Sent — safe to move

    logger.info("Fix-expired-quotes triggered")
    dry_run = req.params.get('dry_run', '').lower() == 'true'

    try:
        load_secrets_from_cloud()
        settings = get_settings(force_reload=True)
        setup_logging(settings.log_level)

        # Load diff result
        diff_data = _read_checkpoint_blob(DIFF_BLOB)
        if not diff_data or 'needs_update' not in diff_data:
            return func.HttpResponse(
                body=json.dumps({"error": "diff-result.json not found or invalid. Run diff first."}),
                mimetype="application/json", status_code=400
            )
        quote_nums_to_fix = diff_data['needs_update']
        total_to_fix = len(quote_nums_to_fix)

        # Load or initialize checkpoint
        cp = _read_checkpoint_blob(CHECKPOINT_BLOB) or {
            "index": 0,
            "stage_updated": 0,
            "flag_only_updated": 0,
            "not_found": 0,
            "errors": [],
            "complete": False,
        }

        if cp.get("complete"):
            return func.HttpResponse(
                body=json.dumps({"status": "already_complete", **cp}),
                mimetype="application/json", status_code=200
            )

        start_index = cp["index"]
        logger.info(f"Starting fix from index {start_index}/{total_to_fix} (dry_run={dry_run})")

        hs_headers = {
            "Authorization": f"Bearer {settings.hubspot_api_key}",
            "Content-Type": "application/json"
        }
        hs_base = "https://api.hubapi.com"
        BATCH = 100
        max_batches_this_call = 50  # process up to 5000 per invocation
        batches_done = 0

        index = start_index
        while index < total_to_fix and batches_done < max_batches_this_call:
            batch = quote_nums_to_fix[index:index + BATCH]

            try:
                # Step 1: Search deals by epicor_quote_number IN <batch> to get IDs + stages.
                # HubSpot's batch/read with idProperty=epicor_quote_number returns OBJECT_NOT_FOUND
                # because that property isn't marked as a unique identifier.
                search_body = {
                    "filterGroups": [{"filters": [
                        {"propertyName": "epicor_quote_number",
                         "operator": "IN",
                         "values": [str(qn) for qn in batch]}
                    ]}],
                    "properties": ["epicor_quote_number", "dealstage", "epicor_expired"],
                    "limit": 100,
                }
                read_resp = req_lib.post(
                    f"{hs_base}/crm/v3/objects/deals/search",
                    headers=hs_headers, json=search_body, timeout=30
                )
                read_data = read_resp.json()
                found_deals = read_data.get('results', [])

                found_qns = {int(d['properties']['epicor_quote_number']) for d in found_deals if d.get('properties', {}).get('epicor_quote_number')}
                batch_set = set(batch)
                missing_qns = batch_set - found_qns
                cp["not_found"] += len(missing_qns)

                # Step 2: Build the batch update
                stage_update_inputs = []
                flag_only_inputs = []
                for d in found_deals:
                    deal_id = d['id']
                    current_stage = d.get('properties', {}).get('dealstage')
                    if current_stage in OPEN_STAGES:
                        stage_update_inputs.append({
                            "id": deal_id,
                            "properties": {
                                "epicor_expired": "true",
                                "dealstage": QUOTE_EXPIRED_STAGE_ID,
                            }
                        })
                    else:
                        flag_only_inputs.append({
                            "id": deal_id,
                            "properties": {"epicor_expired": "true"}
                        })

                # Step 3: Send batch updates
                if not dry_run:
                    all_inputs = stage_update_inputs + flag_only_inputs
                    if all_inputs:
                        upd_resp = req_lib.post(
                            f"{hs_base}/crm/v3/objects/deals/batch/update",
                            headers=hs_headers,
                            json={"inputs": all_inputs},
                            timeout=60
                        )
                        if not upd_resp.ok:
                            err = f"batch update at index={index} failed: {upd_resp.status_code} {upd_resp.text[:200]}"
                            logger.warning(err)
                            cp["errors"].append(err[:300])
                            # Save checkpoint and return — caller can retry
                            _write_checkpoint_blob(CHECKPOINT_BLOB, cp)
                            return func.HttpResponse(
                                body=json.dumps({
                                    "status": "error_partial", "index": cp["index"],
                                    "total": total_to_fix, **{k: v for k, v in cp.items() if k != "errors"},
                                    "last_error": err[:200]
                                }),
                                mimetype="application/json", status_code=200
                            )

                cp["stage_updated"] += len(stage_update_inputs)
                cp["flag_only_updated"] += len(flag_only_inputs)

            except Exception as e:
                err = f"batch at index={index}: {str(e)[:200]}"
                logger.warning(err)
                cp["errors"].append(err[:300])
                _write_checkpoint_blob(CHECKPOINT_BLOB, cp)
                return func.HttpResponse(
                    body=json.dumps({
                        "status": "error", "index": cp["index"],
                        "total": total_to_fix,
                        "stage_updated": cp["stage_updated"],
                        "flag_only_updated": cp["flag_only_updated"],
                        "not_found": cp["not_found"],
                        "error": err[:200]
                    }),
                    mimetype="application/json", status_code=200
                )

            index += len(batch)
            cp["index"] = index
            batches_done += 1

            # Checkpoint every 5 batches
            if batches_done % 5 == 0:
                _write_checkpoint_blob(CHECKPOINT_BLOB, cp)
                logger.info(
                    f"Progress: {index}/{total_to_fix} | "
                    f"stage_updated={cp['stage_updated']} flag_only={cp['flag_only_updated']} "
                    f"not_found={cp['not_found']}"
                )

        # End of loop — either complete or hit max_batches
        if index >= total_to_fix:
            cp["complete"] = True
            _write_checkpoint_blob(CHECKPOINT_BLOB, cp)
            logger.warning(
                f"FIX_COMPLETE: stage_updated={cp['stage_updated']} "
                f"flag_only_updated={cp['flag_only_updated']} not_found={cp['not_found']}"
            )
            return func.HttpResponse(
                body=json.dumps({
                    "status": "complete",
                    "total": total_to_fix,
                    "stage_updated": cp["stage_updated"],
                    "flag_only_updated": cp["flag_only_updated"],
                    "not_found": cp["not_found"],
                    "error_count": len(cp["errors"]),
                }, indent=2),
                mimetype="application/json", status_code=200
            )

        _write_checkpoint_blob(CHECKPOINT_BLOB, cp)
        return func.HttpResponse(
            body=json.dumps({
                "status": "partial",
                "index": index,
                "total": total_to_fix,
                "stage_updated": cp["stage_updated"],
                "flag_only_updated": cp["flag_only_updated"],
                "not_found": cp["not_found"],
                "message": "Re-invoke to continue",
            }, indent=2),
            mimetype="application/json", status_code=200
        )

    except Exception as e:
        logger.error(f"Fix-expired-quotes failed: {e}", exc_info=True)
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            mimetype="application/json", status_code=500
        )


def _compute_diff_phase(epicor_blob: str, hubspot_blob: str, diff_blob: str, req) -> func.HttpResponse:
    """Read Epicor and HubSpot blobs, compute diff, save result."""
    epicor_data = _read_checkpoint_blob(epicor_blob)
    hubspot_data = _read_checkpoint_blob(hubspot_blob)

    if not epicor_data or not epicor_data.get("complete"):
        return func.HttpResponse(
            body=json.dumps({"error": "Epicor phase not complete. Run ?phase=epicor first."}),
            mimetype="application/json", status_code=400
        )
    if not hubspot_data or not hubspot_data.get("complete"):
        return func.HttpResponse(
            body=json.dumps({"error": "HubSpot phase not complete. Run ?phase=hubspot first."}),
            mimetype="application/json", status_code=400
        )

    epicor_set = set(epicor_data["quote_nums"])
    hubspot_set = set(hubspot_data["quote_nums"])

    needs_update = sorted(epicor_set - hubspot_set)
    hubspot_only = sorted(hubspot_set - epicor_set)

    result = {
        "epicor_expired_count": len(epicor_set),
        "hubspot_expired_count": len(hubspot_set),
        "needs_update_count": len(needs_update),
        "hubspot_only_count": len(hubspot_only),
        "needs_update": needs_update,
        "hubspot_only": hubspot_only,
        "timestamp": datetime.now().isoformat(),
    }

    _write_checkpoint_blob(diff_blob, result)
    logger.warning(
        f"DIFF_COMPLETE: needs_update={len(needs_update)} "
        f"epicor={len(epicor_set)} hubspot={len(hubspot_set)}"
    )

    sample_limit = int(req.params.get('limit', '50'))
    summary = {
        **{k: v for k, v in result.items() if k not in ('needs_update', 'hubspot_only')},
        "needs_update_sample": needs_update[:sample_limit],
        "hubspot_only_sample": hubspot_only[:sample_limit],
        "result_blob": diff_blob,
    }
    return func.HttpResponse(
        body=json.dumps(summary, default=str, indent=2),
        mimetype="application/json", status_code=200
    )


