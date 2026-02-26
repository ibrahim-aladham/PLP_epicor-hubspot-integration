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

from src.config import load_secrets_from_cloud, get_settings
from src.main import main
from src.utils.logger import setup_logger

app = func.FunctionApp()

logger = logging.getLogger(__name__)


@app.timer_trigger(
    schedule="0 0 7 * * *",
    arg_name="timer",
    run_on_startup=False
)
def scheduled_sync(timer: func.TimerRequest) -> None:
    """
    Timer-triggered sync that runs daily at 2 AM EST (7 AM UTC).
    """
    logger.info("Timer trigger fired for Epicor-HubSpot sync")

    if timer.past_due:
        logger.warning("Timer is past due — running sync anyway")

    try:
        load_secrets_from_cloud()
        settings = get_settings(force_reload=True)
        setup_logger("epicor_hubspot_sync", settings.log_level)

        result = main()
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
    logger.info("HTTP trigger received for Epicor-HubSpot sync")

    try:
        load_secrets_from_cloud()
        settings = get_settings(force_reload=True)
        setup_logger("epicor_hubspot_sync", settings.log_level)

        result = main()

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
