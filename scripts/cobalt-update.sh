#!/usr/bin/env bash
# Pull latest Cobalt image and restart the container.
#
# Cobalt does not tag stable releases; deploys roll on `:latest` only.
# Without periodic pulls the image drifts months behind upstream and certain
# platforms start failing (X, Instagram are most volatile).
#
# Install:
#   1. chmod +x scripts/cobalt-update.sh
#   2. crontab -e (or `sudo crontab -u cust0dier -e`) and add:
#        0 4 * * 1 /home/cust0dier/video-bot/scripts/cobalt-update.sh
#      (Mondays 04:00 local time — keeps 06:00-23:00 high-traffic hours clean)
#
# Logs: ./data/logs/cobalt-update.log (rotates manually; usually <1 KB/run)

set -eu

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$REPO_DIR/data/logs/cobalt-update.log"
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo
  date '+=== %Y-%m-%d %H:%M:%S %z ==='
  cd "$REPO_DIR"
  docker compose pull cobalt
  docker compose up -d cobalt
  echo "Cobalt version after restart:"
  docker compose logs --tail 5 cobalt 2>&1 | grep -E 'version|commit' | head -2
} >> "$LOG_FILE" 2>&1
