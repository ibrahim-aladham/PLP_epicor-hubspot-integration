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
        full_sync = req.params.get('full_sync', '').lower() == 'true'
        delta_hours = int(req.params.get('delta_hours', '16'))

        # Allow skipping phases to stay within 30-min timeout
        if req.params.get('skip_customers', '').lower() == 'true':
            settings.sync_customers = False
        if req.params.get('skip_quotes', '').lower() == 'true':
            settings.sync_quotes = False
        if req.params.get('skip_orders', '').lower() == 'true':
            settings.sync_orders = False

        result = main(full_sync=full_sync, delta_hours=delta_hours)

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
