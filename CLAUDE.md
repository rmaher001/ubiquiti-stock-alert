# Ubiquiti Stock Alert Monitor

## Project Overview

A self-hosted stock monitoring system for Ubiquiti products that:
1. Listens to UbiquitiStockAlerts Discord server via self-bot (instant alerts)
2. Polls store.ui.com directly as backup (60s interval)
3. Sends alerts to Home Assistant via webhook
4. HA triggers persistent notifications until acknowledged

## Architecture

```
┌─────────────────────────────────────────┐
│  Docker Container (Proxmox LXC)         │
│                                         │
│  Discord Listener ──┐                   │
│  (discord.py-self)  ├──▶ Deduplication ──▶ HA Webhook
│                     │                   │
│  Store Poller ──────┘                   │
│  (60s backup)                           │
└─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  Home Assistant                         │
│  - Alert loops every 30s until ack     │
│  - TTS to home_group speakers          │
│  - Pushover with ack callback          │
│  - SMS via Twilio                      │
└─────────────────────────────────────────┘
```

## File Structure

```
ubiquiti-stock-alert/
├── CLAUDE.md           # This file
├── docker-compose.yml  # Docker deployment
├── Dockerfile          # Container build
├── config.yaml         # Configuration (contains secrets - DO NOT COMMIT)
├── config.example.yaml # Example config (safe to commit)
├── requirements.txt    # Python dependencies
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── discord_listener.py  # Self-bot WebSocket listener
│   ├── store_poller.py      # Direct store.ui.com poller
│   ├── deduplication.py     # Duplicate alert prevention
│   └── ha_webhook.py        # Home Assistant webhook client
└── .gitignore
```

## Configuration

**IMPORTANT:** `config.yaml` contains secrets (Discord token, HA webhook URL).
- Never commit `config.yaml`
- Use `config.example.yaml` as template
- Config is mounted as volume in Docker

## Development

### Local Testing
```bash
cd ~/dev/ubiquiti-stock-alert
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# Edit config.yaml with real values
python src/main.py
```

### Docker Build & Run
```bash
docker-compose up --build
```

## Deployment

Target: Proxmox LXC with Docker

1. Create LXC container or use existing Docker host
2. Clone repo
3. Copy config.example.yaml to config.yaml and fill in values
4. Run `docker-compose up -d`

## Key Dependencies

- `discord.py-self` - Discord user account API (self-bot)
- `aiohttp` - Async HTTP client for webhooks and store polling
- `pyyaml` - Configuration parsing

## Watched Products

| Product | SKU | Role in Discord |
|---------|-----|-----------------|
| G6 180 | UVC-G6-180 | @UVC-G6-180 |
| G6 Pro Entry | UVC-G6-Pro-Entry | @UVC-G6-Pro-Entry |
| UniFi Travel Router | UTR | @UTR |

## Discord Self-Bot Notes

- Uses secondary throwaway Discord account
- Token stored in config.yaml (never commit)
- Violates Discord TOS - account may be banned
- If banned: create new account, rejoin server, update token
- The bot is READ-ONLY (only listens, never sends messages)

## Home Assistant Integration

### Webhook Endpoint
HA receives alerts at: `POST /api/webhook/ubiquiti_stock_alert`

### Alert Flow
1. Webhook received → Create `input_boolean.ubiquiti_alert_active`
2. Automation loops every 30s while alert active:
   - TTS announcement to `media_player.home_group`
   - Pushover notification with ACK action
   - SMS via Twilio (if configured)
3. Acknowledgment methods:
   - Pushover action button callback
   - Voice command: "Hey Google, acknowledge alert"
   - HA Dashboard button
   - Push notification action

## Troubleshooting

### Discord connection issues
- Check token is valid (not expired/banned)
- Verify secondary account still in UbiquitiStockAlerts server
- Check container logs: `docker-compose logs -f`

### No alerts received
- Verify roles are subscribed in Discord (checkmarks)
- Check deduplication window hasn't suppressed it
- Test HA webhook manually: `curl -X POST http://HA_IP:8123/api/webhook/ubiquiti_stock_alert -H "Content-Type: application/json" -d '{"product":"test"}'`

### Store poller not working
- Check store.ui.com isn't rate-limiting (60s minimum interval)
- Verify product SKUs are correct
