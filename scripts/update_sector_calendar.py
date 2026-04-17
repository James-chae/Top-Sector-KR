# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

LEADER_BOARD_PATH = DATA_DIR / "leader_board.json"
HISTORY_PATH = DATA_DIR / "sector_calendar_history.json"

RETENTION_DAYS = 183
MAX_SECTORS_PER_DAY = 8
MAX_STOCK_NAMES_PER_SECTOR = 3


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def to_float(v, default=0.0) -> float:
    if v is None:
        return default
    s = str(v).strip().replace(",", "").replace("+", "").replace("%", "")
    if not s:
        return default
    try:
        return float(s)
    except Exception:
        return default


def to_int(v, default=0) -> int:
    if v is None:
        return default
    s = str(v).strip().replace(",", "").replace("+", "").replace("%", "")
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def pick_trade_date(leader_board: dict) -> str:
    meta = leader_board.get("meta", {})
    trade_date = clean_text(meta.get("trade_date", ""))
    if trade_date:
        return trade_date
    return datetime.now().strftime("%Y-%m-%d")


def normalize_sector_item(item: dict) -> dict:
    stocks = item.get("top_stocks") or item.get("stocks") or []
    top_names = []

    for s in stocks[:MAX_STOCK_NAMES_PER_SECTOR]:
        name = clean_text(s.get("name", ""))
        if name:
            top_names.append(name)

    return {
        "sector1": clean_text(item.get("sector1", item.get("sector", "기타"))),
        "sector_score": round(to_float(item.get("sector_score", item.get("total", 0))), 4),
        "stock_count": to_int(item.get("stock_count", len(stocks))),
        "sector_total_trading_value": to_int(item.get("sector_total_trading_value", item.get("total", 0))),
        "sector_avg_change_pct": round(to_float(item.get("sector_avg_change_pct", item.get("avg_change", 0))), 4),
        "top_stock_names": top_names,
    }


def build_today_entry(leader_board: dict) -> dict:
    trade_date = pick_trade_date(leader_board)
    summary = leader_board.get("summary", {})
    market_bias = clean_text(summary.get("market_bias", leader_board.get("market_bias", "neutral")))

    raw_sectors = leader_board.get("top_sectors", [])[:MAX_SECTORS_PER_DAY]
    top_sectors = [
        normalize_sector_item(x)
        for x in raw_sectors
        if clean_text(x.get("sector1", x.get("sector", "")))
    ]

    return {
        "date": trade_date,
        "market_bias": market_bias,
        "top_sectors": top_sectors,
    }


def filter_retention(history_rows: list[dict], today_str: str) -> list[dict]:
    try:
        today_dt = datetime.strptime(today_str, "%Y-%m-%d")
    except Exception:
        today_dt = datetime.now()

    min_dt = today_dt - timedelta(days=RETENTION_DAYS)

    kept = []
    for row in history_rows:
        d = clean_text(row.get("date", ""))
        try:
            row_dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            continue
        if row_dt >= min_dt:
            kept.append(row)

    kept.sort(key=lambda x: x.get("date", ""))
    return kept


def upsert_history(existing_payload: dict | None, today_entry: dict) -> dict:
    if not existing_payload or not isinstance(existing_payload, dict):
        existing_payload = {"meta": {}, "history": []}

    history = existing_payload.get("history", [])
    if not isinstance(history, list):
        history = []

    target_date = today_entry["date"]
    replaced = False
    new_history = []

    for row in history:
        if clean_text(row.get("date", "")) == target_date:
            new_history.append(today_entry)
            replaced = True
        else:
            new_history.append(row)

    if not replaced:
        new_history.append(today_entry)

    new_history = filter_retention(new_history, target_date)

    payload = {
        "meta": {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "retention_days": RETENTION_DAYS,
            "history_count": len(new_history),
        },
        "history": new_history,
    }
    return payload


def main() -> None:
    if not LEADER_BOARD_PATH.exists():
        raise FileNotFoundError(f"leader_board.json 없음: {LEADER_BOARD_PATH}")

    leader_board = read_json(LEADER_BOARD_PATH, {})
    if not leader_board:
        raise RuntimeError("leader_board.json 이 비어 있음")

    today_entry = build_today_entry(leader_board)
    existing_payload = read_json(HISTORY_PATH, {"meta": {}, "history": []})
    new_payload = upsert_history(existing_payload, today_entry)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json(HISTORY_PATH, new_payload)

    print(f"[OK] sector_calendar_history.json 생성/업데이트 완료 -> {HISTORY_PATH}")
    print(f"[INFO] trade_date={today_entry['date']}")
    print(f"[INFO] market_bias={today_entry['market_bias']}")
    print(f"[INFO] top_sector_count={len(today_entry['top_sectors'])}")
    print(f"[INFO] history_count={new_payload['meta']['history_count']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
