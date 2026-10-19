#!/usr/bin/env bash
# Đồng bộ skill + script trading từ nơi đang dùng vào repo này. Chạy: bash sync.sh
set -euo pipefail
cd "$(dirname "$0")"
SK="$HOME/.claude/skills"; TR="/c/Users/dell/Desktop/trad"
rm -rf skills trading && mkdir -p skills/personal skills/third-party trading/crypto-du-doan
for s in ve-du-doan scan-channel tradingview-connect; do cp -r "$SK/$s" skills/personal/; done
cp -r "$TR/.claude/skills/rose-signals-tracker" skills/personal/
cp -r "$SK/diagram-design" skills/third-party/
for d in "$SK"/mexc-*; do cp -r "$d" skills/third-party/; done
# script trading: chỉ file code/hướng dẫn — KHÔNG lấy mexc_config.json, log, dữ liệu theo ngày
for f in "$TR"/crypto-du-doan/*.py "$TR"/crypto-du-doan/*.bat "$TR"/crypto-du-doan/README.md "$TR"/crypto-du-doan/mexc_config.example.json "$TR"/crypto-du-doan/ve_plan.json; do
  [ -f "$f" ] && cp "$f" trading/crypto-du-doan/
done
find . -name __pycache__ -type d -prune -exec rm -rf {} +
echo "Đã đồng bộ. Xem thay đổi: git status"
