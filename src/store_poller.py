"""Direct store.ui.com poller for Ubiquiti stock alerts."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Base URL for Ubiquiti store
STORE_BASE_URL = "https://store.ui.com"


@dataclass
class ProductConfig:
    """Configuration for a product to monitor."""

    sku: str
    name: str
    url: str


@dataclass
class ProductStatus:
    """Current status of a monitored product."""

    sku: str
    name: str
    url: str
    in_stock: bool
    quantity: Optional[int] = None


class StorePoller:
    """
    Polls store.ui.com directly to check product availability.

    This serves as a backup to the Discord listener, checking product
    pages directly for stock status.
    """

    def __init__(
        self,
        products: List[ProductConfig],
        on_stock_alert: Callable[[str, str, str, Optional[int]], Awaitable[None]],
        interval_seconds: int = 60,
    ):
        """
        Initialize the store poller.

        Args:
            products: List of products to monitor
            on_stock_alert: Async callback when stock detected.
                           Called with (product_name, product_sku, url, quantity)
            interval_seconds: Polling interval (minimum 60 to avoid rate limiting)
        """
        self.products = products
        self.on_stock_alert = on_stock_alert
        self.interval_seconds = max(60, interval_seconds)  # Enforce minimum

        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Track previous states to detect changes
        self._previous_states: Dict[str, bool] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                }
            )
        return self._session

    async def check_product(self, product: ProductConfig) -> ProductStatus:
        """
        Check if a product is in stock.

        Args:
            product: Product configuration

        Returns:
            ProductStatus with current availability
        """
        session = await self._get_session()

        try:
            async with session.get(
                product.url, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status != 200:
                    logger.warning(
                        f"Failed to fetch {product.name}: HTTP {response.status}"
                    )
                    return ProductStatus(
                        sku=product.sku,
                        name=product.name,
                        url=product.url,
                        in_stock=False,
                    )

                html = await response.text()
                return self._parse_product_page(product, html)

        except aiohttp.ClientError as e:
            logger.error(f"Network error checking {product.name}: {e}")
            return ProductStatus(
                sku=product.sku,
                name=product.name,
                url=product.url,
                in_stock=False,
            )
        except Exception as e:
            logger.error(f"Unexpected error checking {product.name}: {e}")
            return ProductStatus(
                sku=product.sku,
                name=product.name,
                url=product.url,
                in_stock=False,
            )

    def _parse_product_page(self, product: ProductConfig, html: str) -> ProductStatus:
        """
        Parse product page HTML to determine stock status.

        Args:
            product: Product configuration
            html: Page HTML content

        Returns:
            ProductStatus with parsed availability
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.error(f"Error parsing HTML for {product.name}: {e}")
            return ProductStatus(
                sku=product.sku,
                name=product.name,
                url=product.url,
                in_stock=False,
            )

        # Common patterns for out-of-stock indicators
        out_of_stock_indicators = [
            "out of stock",
            "sold out",
            "currently unavailable",
            "notify me",
            "coming soon",
        ]

        # Check for add to cart button (indicates in stock)
        add_to_cart = soup.find("button", {"data-testid": "add-to-cart"})
        if add_to_cart is None:
            add_to_cart = soup.find("button", string=lambda x: x and "add to cart" in x.lower())

        # Check page text for out of stock indicators
        page_text = soup.get_text().lower()
        is_out_of_stock = any(indicator in page_text for indicator in out_of_stock_indicators)

        # Determine stock status
        in_stock = add_to_cart is not None and not is_out_of_stock

        # Try to extract quantity if available
        quantity = None
        quantity_elem = soup.find(attrs={"data-testid": "quantity-available"})
        if quantity_elem:
            try:
                quantity = int(quantity_elem.get_text(strip=True).split()[0])
            except (ValueError, IndexError):
                pass

        logger.debug(
            f"Product {product.name}: in_stock={in_stock}, "
            f"add_to_cart={'found' if add_to_cart else 'not found'}, "
            f"out_of_stock_text={is_out_of_stock}"
        )

        return ProductStatus(
            sku=product.sku,
            name=product.name,
            url=product.url,
            in_stock=in_stock,
            quantity=quantity,
        )

    async def _poll_once(self):
        """Perform one polling cycle for all products."""
        for product in self.products:
            status = await self.check_product(product)

            # Get previous state (default to False to trigger on first detection)
            was_in_stock = self._previous_states.get(product.sku, False)

            # Update state
            self._previous_states[product.sku] = status.in_stock

            # Alert on stock detection (transition from out-of-stock to in-stock)
            if status.in_stock and not was_in_stock:
                logger.info(
                    f"Stock detected for {product.name}! "
                    f"Quantity: {status.quantity or 'unknown'}"
                )
                try:
                    await self.on_stock_alert(
                        status.name, status.sku, status.url, status.quantity
                    )
                except Exception as e:
                    logger.error(f"Error in stock alert callback: {e}")

            # Small delay between products to avoid rate limiting
            await asyncio.sleep(2)

    async def _poll_loop(self):
        """Main polling loop."""
        logger.info(
            f"Store poller started. Monitoring {len(self.products)} products "
            f"every {self.interval_seconds}s"
        )

        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"Error in polling cycle: {e}")

            # Wait for next interval
            await asyncio.sleep(self.interval_seconds)

    async def start(self):
        """Start the polling loop."""
        if self._running:
            logger.warning("Store poller already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Store poller started")

    async def stop(self):
        """Stop the polling loop."""
        logger.info("Stopping store poller...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if self._session and not self._session.closed:
            await self._session.close()
            # Give session time to close gracefully
            await asyncio.sleep(0.25)

        logger.info("Store poller stopped")

    def get_status(self) -> Dict[str, bool]:
        """Get current stock status for all products."""
        return dict(self._previous_states)
