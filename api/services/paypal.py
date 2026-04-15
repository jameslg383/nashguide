"""PayPal REST API integration (orders v2)."""
import httpx
from api.config import settings


async def _access_token() -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.paypal_base}/v1/oauth2/token",
            auth=(settings.paypal_client_id, settings.paypal_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def create_order(amount: float, description: str, return_url: str, cancel_url: str) -> dict:
    token = await _access_token()
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "description": description,
                "amount": {"currency_code": "USD", "value": f"{amount:.2f}"},
            }
        ],
        "application_context": {
            "brand_name": "NashGuide AI",
            "landing_page": "NO_PREFERENCE",
            "user_action": "PAY_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.paypal_base}/v2/checkout/orders",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()


async def capture_order(paypal_order_id: str) -> dict:
    token = await _access_token()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.paypal_base}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
