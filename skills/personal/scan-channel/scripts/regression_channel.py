#!/usr/bin/env python
"""
Tinh kenh hoi quy tuyen tinh (linear regression channel) tu danh sach gia dong cua (close).

Dung khi: TradingView khong tra ve gia tri so cho indicator "Linear Regression Channel"
qua Data Window (no chi ve duong tren chart, khong co plot() output) - nen phai tu tinh
tu du lieu nen tho (OHLCV) lay qua data_get_ohlcv.

Input: JSON array cac gia close, moi nhat o CUOI mang, qua stdin.
  Vi du: echo "[100,101,99,102,105]" | python regression_channel.py

Output: JSON voi slope, basis (gia tri duong hoi quy tai nen cuoi), std (do lech chuan
phan du), upper/lower band o 1SD va 2SD, gia hien tai, va % vi tri gia trong kenh 2SD
(0% = cham day kenh, 100% = cham dinh kenh, co the <0% hoac >100% neu gia da pha kenh).

Khong can numpy - chi dung list/math thuan Python de chay duoc moi noi.
"""
import sys
import json


def compute_channel(closes):
    n = len(closes)
    if n < 5:
        raise ValueError("Can it nhat 5 nen de tinh kenh hoi quy co y nghia")

    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(closes) / n

    num = sum((xs[i] - mean_x) * (closes[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    intercept = mean_y - slope * mean_x

    fit = [slope * xi + intercept for xi in xs]
    resid = [closes[i] - fit[i] for i in range(n)]
    std = (sum(r * r for r in resid) / n) ** 0.5

    basis_now = fit[-1]
    price_now = closes[-1]

    upper1, lower1 = basis_now + std, basis_now - std
    upper2, lower2 = basis_now + 2 * std, basis_now - 2 * std

    channel_width = upper2 - lower2
    pct_position = (
        (price_now - lower2) / channel_width * 100 if channel_width else 50.0
    )

    return {
        "bar_count": n,
        "slope_per_bar": round(slope, 6),
        "trend": "tang" if slope > 0 else ("giam" if slope < 0 else "di ngang"),
        "basis_now": round(basis_now, 6),
        "std": round(std, 6),
        "upper_1sd": round(upper1, 6),
        "lower_1sd": round(lower1, 6),
        "upper_2sd": round(upper2, 6),
        "lower_2sd": round(lower2, 6),
        "price_now": price_now,
        "pct_position_in_channel": round(pct_position, 1),
        "note": (
            "vuot dinh kenh (qua mua trong kenh)" if pct_position > 100 else
            "vuot day kenh (qua ban trong kenh)" if pct_position < 0 else
            "quanh dinh kenh (>85%)" if pct_position > 85 else
            "quanh day kenh (<15%)" if pct_position < 15 else
            "giua kenh"
        ),
    }


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "Khong co input. Truyen JSON array gia close qua stdin."}))
        sys.exit(1)
    try:
        closes = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON khong hop le: {e}"}))
        sys.exit(1)

    try:
        result = compute_channel([float(c) for c in closes])
    except (ValueError, TypeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
