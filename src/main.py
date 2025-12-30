"""Main entry point for Ubiquiti Stock Alert Monitor."""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import yaml

from .deduplication import DeduplicationEngine
from .discord_listener import create_discord_listener, DiscordListener
from .ha_webhook import HAWebhookClient
from .store_poller import ProductConfig, StorePoller

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)

    if not path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)

    if path.is_dir():
        logger.error(f"Configuration path is a directory, not a file: {config_path}")
        sys.exit(1)

    try:
        with open(path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in configuration file: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Validate required fields
    required = ["discord", "home_assistant"]
    for field in required:
        if field not in config:
            logger.error(f"Missing required configuration: {field}")
            sys.exit(1)

    return config


class StockAlertMonitor:
    """Main application orchestrator."""

    def __init__(self, config: dict):
        """
        Initialize the stock alert monitor.

        Args:
            config: Configuration dictionary from YAML
        """
        self.config = config
        self._shutdown_event = asyncio.Event()

        # Initialize components
        self.dedup = DeduplicationEngine(
            window_minutes=config.get("deduplication", {}).get("window_minutes", 30)
        )

        self.ha_client = HAWebhookClient(
            webhook_url=config["home_assistant"]["webhook_url"],
            token=config["home_assistant"].get("token"),
        )

        self.discord_listener: Optional[DiscordListener] = None
        self.store_poller: Optional[StorePoller] = None

        # Configure logging level
        log_level = config.get("logging", {}).get("level", "INFO").upper()
        logging.getLogger().setLevel(getattr(logging, log_level))

    async def _on_discord_alert(
        self, product_name: str, product_sku: str, message: str
    ):
        """Handle stock alert from Discord listener."""
        logger.info(f"Discord alert: {product_name} ({product_sku})")

        if not self.dedup.should_alert(product_sku):
            logger.info(f"Duplicate alert suppressed for {product_sku}")
            return

        await self.ha_client.send_alert(
            product_name=product_name,
            product_sku=product_sku,
            source="discord",
            message=message,
        )

    async def _on_store_alert(
        self,
        product_name: str,
        product_sku: str,
        url: str,
        quantity: Optional[int],
    ):
        """Handle stock alert from store poller."""
        logger.info(f"Store poller alert: {product_name} ({product_sku})")

        if not self.dedup.should_alert(product_sku):
            logger.info(f"Duplicate alert suppressed for {product_sku}")
            return

        await self.ha_client.send_alert(
            product_name=product_name,
            product_sku=product_sku,
            source="store_poller",
            quantity=quantity,
            url=url,
        )

    async def start(self):
        """Start all monitoring components."""
        logger.info("Starting Ubiquiti Stock Alert Monitor...")

        # Start Discord listener
        discord_config = self.config.get("discord", {})
        if discord_config.get("token"):
            try:
                self.discord_listener = await create_discord_listener(
                    token=discord_config["token"],
                    watched_roles=discord_config.get("watched_roles", []),
                    on_stock_alert=self._on_discord_alert,
                )
                logger.info("Discord listener started")
            except Exception as e:
                logger.error(f"Failed to start Discord listener: {e}")
                # Continue without Discord if it fails
        else:
            logger.warning("Discord token not configured, skipping Discord listener")

        # Start store poller
        poller_config = self.config.get("store_poller", {})
        if poller_config.get("enabled", True):
            products = [
                ProductConfig(
                    sku=p["sku"],
                    name=p["name"],
                    url=p["url"],
                )
                for p in poller_config.get("products", [])
            ]

            if products:
                self.store_poller = StorePoller(
                    products=products,
                    on_stock_alert=self._on_store_alert,
                    interval_seconds=poller_config.get("interval_seconds", 60),
                )
                await self.store_poller.start()
                logger.info(f"Store poller started, monitoring {len(products)} products")
            else:
                logger.warning("No products configured for store poller")
        else:
            logger.info("Store poller disabled in configuration")

        logger.info("Ubiquiti Stock Alert Monitor is running")

    async def stop(self):
        """Stop all monitoring components."""
        logger.info("Shutting down Ubiquiti Stock Alert Monitor...")

        if self.discord_listener:
            await self.discord_listener.shutdown()

        if self.store_poller:
            await self.store_poller.stop()

        await self.ha_client.close()

        logger.info("Shutdown complete")

    async def run(self):
        """Run the monitor until shutdown signal."""
        await self.start()

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        await self.stop()

    def request_shutdown(self):
        """Request graceful shutdown."""
        self._shutdown_event.set()


def setup_signal_handlers(monitor: StockAlertMonitor):
    """Set up signal handlers for graceful shutdown."""
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, monitor.request_shutdown)


async def main():
    """Main entry point."""
    # Load configuration
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config = load_config(config_path)

    # Create monitor
    monitor = StockAlertMonitor(config)

    # Set up signal handlers
    try:
        setup_signal_handlers(monitor)
    except NotImplementedError:
        # Signal handlers not supported on Windows
        logger.warning("Signal handlers not supported on this platform")

    # Run
    try:
        await monitor.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
