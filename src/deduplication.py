"""Deduplication engine to prevent duplicate alerts."""

import logging
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)


class DeduplicationEngine:
    """
    Prevents duplicate alerts for the same product within a time window.

    This ensures that if both Discord and store poller detect the same
    restock event, only one alert is sent.
    """

    def __init__(self, window_minutes: int = 30):
        """
        Initialize deduplication engine.

        Args:
            window_minutes: Time window in minutes. Same product won't alert
                          twice within this window. Set to 0 to disable.
        """
        self.window_minutes = window_minutes
        self._last_alerts: Dict[str, datetime] = {}

    def should_alert(self, product_sku: str) -> bool:
        """
        Check if an alert should be sent for this product.

        Args:
            product_sku: The product SKU to check

        Returns:
            True if alert should be sent, False if duplicate
        """
        if self.window_minutes <= 0:
            # Deduplication disabled
            return True

        now = datetime.now()
        sku_lower = product_sku.lower()

        if sku_lower in self._last_alerts:
            last_alert = self._last_alerts[sku_lower]
            window = timedelta(minutes=self.window_minutes)

            if now - last_alert < window:
                remaining = window - (now - last_alert)
                logger.debug(
                    f"Duplicate alert suppressed for {product_sku}. "
                    f"Window expires in {remaining.seconds}s"
                )
                return False

        # Record this alert
        self._last_alerts[sku_lower] = now
        logger.debug(f"Alert allowed for {product_sku}")
        return True

    def clear(self, product_sku: str = None):
        """
        Clear alert history.

        Args:
            product_sku: Specific SKU to clear, or None to clear all
        """
        if product_sku:
            self._last_alerts.pop(product_sku.lower(), None)
            logger.debug(f"Cleared dedup history for {product_sku}")
        else:
            self._last_alerts.clear()
            logger.debug("Cleared all dedup history")

    def get_status(self) -> Dict[str, str]:
        """Get current deduplication status for debugging."""
        now = datetime.now()
        status = {}
        for sku, last_alert in self._last_alerts.items():
            elapsed = now - last_alert
            remaining = timedelta(minutes=self.window_minutes) - elapsed
            if remaining.total_seconds() > 0:
                status[sku] = f"blocked for {int(remaining.total_seconds())}s"
            else:
                status[sku] = "expired"
        return status
