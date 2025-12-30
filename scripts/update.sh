#!/bin/bash
# Update script for Ubiquiti Stock Alert Monitor
# Run this from inside the LXC to update the application

set -e

APP_DIR="/opt/ubiquiti-stock-alert"
cd "$APP_DIR"

echo "Updating Ubiquiti Stock Alert Monitor..."

# Pull latest changes
echo "Pulling latest changes from git..."
git pull

# Rebuild and restart container
echo "Rebuilding and restarting container..."
docker compose down
docker compose up -d --build

# Show container status
echo ""
echo "Container status:"
docker compose ps

echo ""
echo "Update complete!"
echo "View logs with: docker compose logs -f"
