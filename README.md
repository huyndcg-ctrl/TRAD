# TRAD

Skill Claude Code + script trading của huyndcg.

| Thư mục | Nội dung | Nguồn trên máy |
|---|---|---|
| `skills/personal/` | `ve-du-doan`, `scan-channel`, `tradingview-connect`, `rose-signals-tracker` | `~/.claude/skills`, `Desktop\trad\.claude\skills` |
| `skills/third-party/` | `diagram-design`, các skill `mexc-*` (MEXC CLI cài) | `~/.claude/skills` |
| `trading/crypto-du-doan/` | Script quét kèo, đặt/huỷ lệnh MEXC, gắn SL (người dùng tự chạy & xác nhận) | `Desktop\trad\crypto-du-doan` |

Không chứa API key: `mexc_config.json`, log và dữ liệu theo ngày bị loại (xem `.gitignore`).

## Cập nhật lên repo
```bash
bash sync.sh
git add -A && git commit -m "Cập nhật skill" && git push
```

## Cài lại trên máy mới
Copy `skills/personal/*` và `skills/third-party/*` vào `~/.claude/skills/` (riêng `rose-signals-tracker` để trong `.claude/skills` của project trading).
