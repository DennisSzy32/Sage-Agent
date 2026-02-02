#!/bin/bash
# Sage Agent Deployment Script
# Run on Sage-LiveKit Pi after pushing changes to GitHub

set -e

echo "========================================"
echo "  Sage Agent Deployment"
echo "========================================"

cd /home/dennis-admin/sage-agent

echo ""
echo "[1/4] Pulling latest from GitHub..."
git pull origin main

echo ""
echo "[2/4] Checking dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet

echo ""
echo "[3/4] Restarting services..."
sudo systemctl restart sage-agent

echo ""
echo "[4/4] Verifying..."
sleep 2
if systemctl is-active --quiet sage-agent; then
    echo "✓ sage-agent is running"
else
    echo "✗ sage-agent failed!"
    sudo journalctl -u sage-agent -n 20
    exit 1
fi

echo ""
echo "========================================"
echo "  Deployment complete!"
echo "========================================"
echo ""
echo "View logs: sudo journalctl -u sage-agent -f"
