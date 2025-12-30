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

# Fix any old store.ui.com URLs in config.yaml
echo "Updating store URLs in config..."
if [ -f config.yaml ]; then
    sed -i 's|collections/cameras-background/products/uvc-g6-180|category/cameras-dome-turret/products/uvc-g6-180|g' config.yaml
    sed -i 's|collections/cameras-background/products/uvc-g6-pro-entry|category/door-access-readers/products/uvc-g6-pro-entry|g' config.yaml
    sed -i 's|collections/accessories-background/products/utr|category/wifi-special-devices/products/utr|g' config.yaml
fi

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
