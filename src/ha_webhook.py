"""Home Assistant webhook client for sending stock alerts."""

import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)


class HAWebhookClient:
    """Sends stock alerts to Home Assistant via webhook."""

    def __init__(self, webhook_url: str, token: Optional[str] = None):
        self.webhook_url = webhook_url
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send_alert(
        self,
        product_name: str,
        product_sku: str,
        source: str,
        quantity: Optional[int] = None,
        url: Optional[str] = None,
        message: Optional[str] = None,
    ) -> bool:
        """
        Send a stock alert to Home Assistant.

        Args:
            product_name: Human-readable product name
            product_sku: Product SKU/ID
            source: Alert source ('discord' or 'store_poller')
            quantity: Available quantity (if known)
            url: Product URL
            message: Raw message from Discord (if applicable)

        Returns:
            True if webhook was sent successfully, False otherwise
        """
        payload = {
            "product_name": product_name,
            "product_sku": product_sku,
            "source": source,
            "quantity": quantity,
            "url": url or f"https://store.ui.com/us/en/search?q={product_sku}",
            "message": message,
        }

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            session = await self._get_session()
            async with session.post(
                self.webhook_url, json=payload, headers=headers, timeout=10
            ) as response:
                if response.status == 200:
                    logger.info(
                        f"Alert sent to HA: {product_name} ({product_sku}) from {source}"
                    )
                    return True
                else:
                    logger.error(
                        f"HA webhook failed: {response.status} - {await response.text()}"
                    )
                    return False
        except aiohttp.ClientError as e:
            logger.error(f"HA webhook connection error: {e}")
            return False
        except Exception as e:
            logger.error(f"HA webhook unexpected error: {e}")
            return False

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
