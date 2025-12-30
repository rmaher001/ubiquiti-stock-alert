"""Discord self-bot listener for Ubiquiti stock alerts."""

import asyncio
import logging
import re
from typing import Awaitable, Callable, List, Optional, Set

import discord

logger = logging.getLogger(__name__)

# UbiquitiStockAlerts server ID
UBIQUITI_STOCK_ALERTS_GUILD_ID = 1200139856194584797


class DiscordListener(discord.Client):
    """
    Discord self-bot that listens for role mentions in UbiquitiStockAlerts.

    Uses discord.py-self to connect as a user account (not a bot).
    Watches for role mentions matching configured product roles.
    """

    def __init__(
        self,
        watched_roles: List[str],
        on_stock_alert: Callable[[str, str, str], Awaitable[None]],
        **kwargs,
    ):
        """
        Initialize the Discord listener.

        Args:
            watched_roles: List of role names to watch for (e.g., ["UVC-G6-180", "UTR"])
            on_stock_alert: Async callback when stock alert detected.
                           Called with (product_name, product_sku, message_content)
        """
        # discord.py-self doesn't use Intents like regular discord.py
        super().__init__(**kwargs)

        self.watched_roles: Set[str] = {role.lower() for role in watched_roles}
        self.on_stock_alert = on_stock_alert
        self._start_task: Optional[asyncio.Task] = None

    async def on_ready(self):
        """Called when the client is ready."""
        logger.info(f"Discord listener connected as {self.user}")

        # Find the UbiquitiStockAlerts guild
        guild = self.get_guild(UBIQUITI_STOCK_ALERTS_GUILD_ID)
        if guild:
            logger.info(f"Found UbiquitiStockAlerts server: {guild.name}")
        else:
            logger.warning(
                "UbiquitiStockAlerts server not found. "
                "Make sure the account has joined the server."
            )

    async def shutdown(self):
        """Gracefully shutdown the client."""
        logger.info("Shutting down Discord listener...")
        await self.close()
        if self._start_task and not self._start_task.done():
            self._start_task.cancel()
            try:
                await self._start_task
            except asyncio.CancelledError:
                pass
        logger.info("Discord listener shutdown complete")

    async def on_message(self, message: discord.Message):
        """Process incoming messages for stock alerts."""
        # Only process messages from UbiquitiStockAlerts
        if not message.guild or message.guild.id != UBIQUITI_STOCK_ALERTS_GUILD_ID:
            return

        # Ignore our own messages
        if message.author == self.user:
            return

        # Log all messages from UbiquitiStockAlerts for debugging
        logger.info(
            f"Message received - Channel: {message.channel.name}, "
            f"Author: {message.author}, Roles mentioned: {[r.name for r in message.role_mentions]}"
        )

        # Check for role mentions
        for role in message.role_mentions:
            role_name_lower = role.name.lower()

            if role_name_lower in self.watched_roles:
                logger.info(
                    f"Stock alert detected! Role: {role.name}, "
                    f"Channel: {message.channel.name}"
                )

                # Extract product info
                product_name = self._extract_product_name(role.name, message.content)
                product_sku = role.name  # Role name is typically the SKU

                # Trigger callback
                try:
                    await self.on_stock_alert(
                        product_name, product_sku, message.content
                    )
                except Exception as e:
                    logger.error(f"Error in stock alert callback: {e}")

    def _extract_product_name(self, role_name: str, message_content: str) -> str:
        """
        Extract a human-readable product name from the message or role.

        Args:
            role_name: The Discord role name (usually SKU)
            message_content: The full message content

        Returns:
            Human-readable product name
        """
        # Map of known SKUs to product names
        sku_to_name = {
            "uvc-g6-180": "G6 180",
            "uvc-g6-pro-entry": "G6 Pro Entry",
            "utr": "UniFi Travel Router",
        }

        role_lower = role_name.lower()
        if role_lower in sku_to_name:
            return sku_to_name[role_lower]

        # Try to extract from message using common patterns
        # Pattern: "Product Name (SKU)" or "Product Name - SKU"
        patterns = [
            rf"([^(@\n]+?)\s*\({re.escape(role_name)}\)",
            rf"([^-\n]+?)\s*-\s*{re.escape(role_name)}",
        ]

        for pattern in patterns:
            match = re.search(pattern, message_content, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback to role name
        return role_name

    async def on_error(self, event: str, *args, **kwargs):
        """Handle errors in event handlers."""
        logger.exception(f"Error in Discord event {event}")


async def create_discord_listener(
    token: str,
    watched_roles: List[str],
    on_stock_alert: Callable[[str, str, str], Awaitable[None]],
) -> DiscordListener:
    """
    Create and start a Discord listener.

    Args:
        token: Discord user token
        watched_roles: List of role names to watch
        on_stock_alert: Async callback for stock alerts

    Returns:
        Running DiscordListener instance
    """
    client = DiscordListener(watched_roles=watched_roles, on_stock_alert=on_stock_alert)

    # Start client in background and store task reference
    client._start_task = asyncio.create_task(client.start(token))

    # Wait for ready using discord.py's built-in method with timeout
    try:
        await asyncio.wait_for(client.wait_until_ready(), timeout=30.0)
        logger.info("Discord client is ready")
    except asyncio.TimeoutError:
        logger.error("Discord client failed to become ready within 30s")
        raise TimeoutError("Discord client failed to connect within 30.0s")
    except discord.LoginFailure:
        logger.error("Discord authentication failed - check token")
        raise ValueError("Invalid Discord token") from None
    except Exception as e:
        logger.error(f"Failed to connect to Discord: {type(e).__name__}")
        raise

    return client
