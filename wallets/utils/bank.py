import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Configurable via Django settings with sensible defaults
THIRD_PARTY_BASE_URL = getattr(
    settings, "THIRD_PARTY_BASE_URL", "http://localhost:8010"
)
THIRD_PARTY_TIMEOUT = getattr(settings, "THIRD_PARTY_TIMEOUT", 10)


def request_third_party_deposit(wallet_uuid: str, amount: int) -> dict:
    """
    Send a deposit request to the third-party bank service.

    Handles both HTTP errors (non-200 responses from the bank) and network
    failures (connection errors, timeouts). Returns a structured result dict
    for consistent downstream handling.

    Args:
        wallet_uuid: UUID of the wallet owner.
        amount: Amount to deposit to the owner's bank account.

    Returns:
        dict with keys:
            - success (bool): Whether the third-party accepted the deposit.
            - response (dict): The raw response data or error details.
    """
    try:
        response = requests.post(
            f"{THIRD_PARTY_BASE_URL}/",
            json={"wallet_uuid": wallet_uuid, "amount": amount},
            timeout=THIRD_PARTY_TIMEOUT,
        )

        response_data = response.json()

        # The third-party returns status in the JSON body
        if response_data.get("status") == 200:
            logger.info(
                "Third-party deposit succeeded: wallet=%s amount=%d",
                wallet_uuid,
                amount,
            )
            return {"success": True, "response": response_data}

        logger.warning(
            "Third-party deposit failed: wallet=%s amount=%d response=%s",
            wallet_uuid,
            amount,
            response_data,
        )
        return {"success": False, "response": response_data}

    except requests.exceptions.ConnectionError as exc:
        logger.error(
            "Third-party connection error: wallet=%s amount=%d error=%s",
            wallet_uuid,
            amount,
            str(exc),
        )
        return {
            "success": False,
            "response": {"error": "connection_error", "detail": str(exc)},
        }

    except requests.exceptions.Timeout as exc:
        logger.error(
            "Third-party timeout: wallet=%s amount=%d error=%s",
            wallet_uuid,
            amount,
            str(exc),
        )
        return {
            "success": False,
            "response": {"error": "timeout", "detail": str(exc)},
        }

    except requests.exceptions.RequestException as exc:
        logger.error(
            "Third-party request error: wallet=%s amount=%d error=%s",
            wallet_uuid,
            amount,
            str(exc),
        )
        return {
            "success": False,
            "response": {"error": "request_error", "detail": str(exc)},
        }
