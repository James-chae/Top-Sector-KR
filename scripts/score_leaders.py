# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

INPUT_PATH = DATA_DIR / "market_raw.json"
OUTPUT_PATH = DATA_DIR / "leader_board.json"
HOLIDAYS_PATH = DATA_DIR / "krx_holidays.json"

LATEST_LEADERS_SNAPSHOT_PATH = DATA_DIR / "latest_leaders_snapshot.json"
PREVIOUS_LEADERS_SNAPSHOT_PATH = DATA_DIR / "previous_leaders_snapshot.json"

LATEST_D1_SNAPSHOT_PATH = DATA_DIR / "latest_d1_snapshot.json"
PREVIOUS_D1_SNAPSHOT_PATH = DATA_DIR / "previous_d1_snapshot.json"

KST = ZoneInfo("Asia/Seoul")
RESET_TIME = time(7, 50)

# ===== 설정 =====
MIN_BASE_TRADING = 500
MIN_LEADER_TRADING = 500
MIN_PULLBACK_TRADING = 500
MIN_NEXT_DAY_TRADING = 500

MIN_LEADER_CHANGE = 3.0
PULLBACK_MIN_CHANGE = 0.0
PULLBACK_MAX_CHANGE = 3.0
NEXT_DAY_MIN_CHANGE = 3.0
NEXT_DAY_MAX_CHANGE = 10.0

TOP_SECTOR_COUNT = 8
MAX_PER_SECTOR = 3
LEADER_COUNT = 20
PULLBACK_COUNT = 10
NEXT_DAY_COUNT = 10
D2_COUNT = 10
MIN_SECTOR_STOCK_COUNT = 2


# ===== 유틸 =====
def load_json(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def to_float(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "").replace("%", "").strip())
    except Exception:
        return default


def to_int(v, default=0):
    try:
        if v is None or v == "":
            return default
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return default


def clean_text(v):
    if v is None:
        return ""
    return str(v).strip()


def percentile(value, arr):
    if not arr:
        return 0.0
    return sum(x <= value for x in arr) / len(arr)


def dedupe_rows(rows):
    seen = set()
    out = []
    for r in rows:
        key = (clean_text(r.get("code")), clean_text(r.get("name")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def normalize_row(row):
    return {
        "code": clean_text(row.get("code")),
        "name": clean_text(row.get("name")),
        "market": clean_text(row.get("market")),
        "sector1": clean_text(row.get("sector1")),
        "sector2": clean_text(row.get("sector2")),
        "trading_value_okrw": to_float(row.get("trading_value_okrw"), 0.0),
        "change_pct": to_float(row.get("change_pct"), 0.0),
        "volume": to_int(row.get("volume"), 0),
        "price": to_float(row.get("price", 0), 0.0),
    }


def resolve_trade_date(raw):
    meta = raw.get("meta", {})
    trade_date = clean_text(meta.get("trade_date"))
    return trade_date or "-"


def resolve_generated_at(raw):
    meta = raw.get("meta", {})
    generated_at = clean_text(meta.get("generated_at"))
    return generated_at or ""


def parse_ymd(text: str) -> date | None:
    text = clean_text(text)
    if not text or text == "-":
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def format_dt_kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S %Z")


# ===== 거래일 유지 / reset =====
def load_krx_holidays() -> set[str]:
    payload = load_json(HOLIDAYS_PATH, default={})
    if isinstance(payload, list):
        return {clean_text(x) for x in payload if clean_text(x)}
    if isinstance(payload, dict):
        items = payload.get("holidays", [])
        return {clean_text(x) for x in items if clean_text(x)}
    return set()


def is_business_day(d: date, holidays: set[str]) -> bool:
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in holidays


def next_business_day(d: date, holidays: set[str]) -> date:
    cursor = d + timedelta(days=1)
    while not is_business_day(cursor, holidays):
        cursor += timedelta(days=1)
    return cursor


def compute_retention_context(raw_trade_date_text: str, now_kst: datetime, holidays: set[str]) -> dict:
    raw_trade_date = parse_ymd(raw_trade_date_text)
    today = now_kst.date()

    if raw_trade_date is None:
        return {
            "raw_trade_date": raw_trade_date_text,
            "display_trade_date": raw_trade_date_text,
            "hold_until_kst": "",
            "is_hold_active": False,
            "should_reset_for_new_day": False,
            "session_state": "unknown",
            "holiday_source": HOLIDAYS_PATH.name if HOLIDAYS_PATH.exists() else "weekend_only",
        }

    next_open_date = next_business_day(raw_trade_date, holidays)
    hold_until_dt = datetime.combine(next_open_date, RESET_TIME, tzinfo=KST)
    is_hold_active = now_kst < hold_until_dt

    current_business_date = today if is_business_day(today, holidays) else next_open_date
    should_reset_for_new_day = (not is_hold_active) and (current_business_date > raw_trade_date)

    if is_hold_active:
        session_state = "hold_previous_close"
        display_trade_date = raw_trade_date.isoformat()
    elif current_business_date > raw_trade_date:
        session_state = "waiting_new_trade_date_after_reset"
        display_trade_date = current_business_date.isoformat()
    else:
        session_state = "active_trade_date"
        display_trade_date = raw_trade_date.isoformat()

    return {
        "raw_trade_date": raw_trade_date.isoformat(),
        "display_trade_date": display_trade_date,
        "hold_until_kst": format_dt_kst(hold_until_dt),
        "is_hold_active": is_hold_active,
        "should_reset_for_new_day": should_reset_for_new_day,
        "session_state": session_state,
        "holiday_source": HOLIDAYS_PATH.name if HOLIDAYS_PATH.exists() else "weekend_only",
    }


# ===== 시장 판단 =====
def calc_market_bias(rows):
    if not rows:
        return "neutral"

    changes = [to_float(r.get("change_pct")) for r in rows]
    pos = sum(1 for x in changes if x > 0)
    ratio = pos / len(rows) if rows else 0.0
    avg = sum(changes) / len(rows) if rows else 0.0

    if ratio >= 0.68 and avg >= 2.0:
        return "strong_risk_on"
    if ratio >= 0.56 and avg >= 1.0:
        return "risk_on"
    if ratio <= 0.32 and avg <= -1.0:
        return "strong_risk_off"
    if ratio <= 0.42:
        return "risk_off"
    return "neutral"


# ===== 종목 점수 =====
def score_stocks(rows):
    values = [r["trading_value_okrw"] for r in rows] or [0]
    changes = [r["change_pct"] for r in rows] or [0]
    volumes = [r["volume"] for r in rows] or [0]

    out = []
    for r in rows:
        trading_score = percentile(r["trading_value_okrw"], values)
        change_score = percentile(r["change_pct"], changes)
        volume_score = percentile(r["volume"], volumes)

        score = (
            trading_score * 0.65
            + change_score * 0.30
            + volume_score * 0.05
        ) * 100.0

        r2 = r.copy()
        r2["score"] = round(score, 2)
        out.append(r2)

    return sorted(out, key=lambda x: x["score"], reverse=True)


# ===== 섹터 =====
def build_sectors(rows):
    grouped = defaultdict(list)

    for r in rows:
        sector_name = clean_text(r.get("sector1"))
        if not sector_name:
            continue
        grouped[sector_name].append(r)

    sector_total_list = [sum(y["trading_value_okrw"] for y in v) for v in grouped.values()] or [0]
    sector_avg_list = [sum(y["change_pct"] for y in v) / len(v) for v in grouped.values()] or [0]
    sector_count_list = [len(v) for v in grouped.values()] or [0]
    sector_top_stock_list = [max(y["score"] for y in v) for v in grouped.values()] or [0]

    sectors = []
    for sector_name, items in grouped.items():
        if len(items) < MIN_SECTOR_STOCK_COUNT:
            continue

        sorted_items = sorted(items, key=lambda x: x["score"], reverse=True)
        total_trading = sum(x["trading_value_okrw"] for x in items)
        avg_change = sum(x["change_pct"] for x in items) / len(items)
        top_stock_score = sorted_items[0]["score"] if sorted_items else 0.0

        sector_score = (
            percentile(total_trading, sector_total_list) * 0.45
            + percentile(avg_change, sector_avg_list) * 0.25
            + percentile(len(items), sector_count_list) * 0.15
            + percentile(top_stock_score, sector_top_stock_list) * 0.15
        ) * 100.0

        stocks_payload = []
        for x in sorted_items:
            stocks_payload.append({
                "code": x["code"],
                "name": x["name"],
                "market": x["market"],
                "sector1": x["sector1"],
                "sector2": x["sector2"],
                "change_pct": x["change_pct"],
                "trading_value_okrw": x["trading_value_okrw"],
                "volume": x["volume"],
                "price": x["price"],
                "score": x["score"],
                "stock_score": x["score"],
            })

        sectors.append({
            "sector1": sector_name,
            "sector": sector_name,
            "sector_score": round(sector_score, 2),
            "stock_count": len(items),
            "sector_total_trading_value": round(total_trading, 2),
            "sector_avg_change_pct": round(avg_change, 2),
            "top_stocks": stocks_payload[:3],
            "stocks": stocks_payload,
        })

    return sorted(
        sectors,
        key=lambda x: (x["sector_score"], x["sector_total_trading_value"]),
        reverse=True,
    )


# ===== 1타 =====
def pick_leaders(sectors):
    picked = []

    for sector in sectors[:TOP_SECTOR_COUNT]:
        added = 0
        for stock in sector["stocks"]:
            if stock["trading_value_okrw"] < MIN_LEADER_TRADING:
                continue
            if stock["change_pct"] < MIN_LEADER_CHANGE:
                continue

            stock2 = stock.copy()
            stock2["stock_score"] = stock2.get("stock_score", stock2.get("score", 0))
            stock2["sector_score"] = sector["sector_score"]
            picked.append(stock2)
            added += 1

            if added >= MAX_PER_SECTOR:
                break

    picked = dedupe_rows(picked)
    picked = sorted(
        picked,
        key=lambda x: (
            x.get("stock_score", x.get("score", 0)),
            x.get("trading_value_okrw", 0),
            x.get("change_pct", 0),
        ),
        reverse=True,
    )
    return picked[:LEADER_COUNT]


# ===== 2타 =====
def pick_pullback(all_rows, leaders, sectors):
    leader_codes = {x["code"] for x in leaders}
    top_sector_names = {x["sector1"] for x in sectors[:TOP_SECTOR_COUNT]}

    result = []
    all_values = [x["trading_value_okrw"] for x in all_rows] or [0]

    for r in all_rows:
        if r["code"] in leader_codes:
            continue
        if r["sector1"] not in top_sector_names:
            continue
        if r["trading_value_okrw"] < MIN_PULLBACK_TRADING:
            continue
        if not (PULLBACK_MIN_CHANGE <= r["change_pct"] <= PULLBACK_MAX_CHANGE):
            continue

        r2 = r.copy()
        r2["stock_score"] = round(
            r.get("score", 0) * 0.55
            + percentile(r["trading_value_okrw"], all_values) * 100 * 0.45,
            2,
        )
        result.append(r2)

    result = dedupe_rows(result)
    result = sorted(
        result,
        key=lambda x: (
            x["trading_value_okrw"],
            x.get("stock_score", x.get("score", 0)),
            x["change_pct"],
        ),
        reverse=True,
    )
    return result[:PULLBACK_COUNT]


# ===== 3타 =====
def pick_next_day(all_rows, leaders, pullback, sectors):
    leader_codes = {x["code"] for x in leaders}
    pullback_codes = {x["code"] for x in pullback}
    top_sector_names = {x["sector1"] for x in sectors[:TOP_SECTOR_COUNT]}

    result = []
    all_values = [x["trading_value_okrw"] for x in all_rows] or [0]

    for r in all_rows:
        if r["code"] in leader_codes:
            continue
        if r["code"] in pullback_codes:
            continue
        if r["sector1"] not in top_sector_names:
            continue
        if r["trading_value_okrw"] < MIN_NEXT_DAY_TRADING:
            continue
        if not (NEXT_DAY_MIN_CHANGE <= r["change_pct"] < NEXT_DAY_MAX_CHANGE):
            continue

        r2 = r.copy()
        r2["stock_score"] = round(
            r.get("score", 0) * 0.65
            + percentile(r["trading_value_okrw"], all_values) * 100 * 0.35,
            2,
        )
        result.append(r2)

    result = dedupe_rows(result)
    result = sorted(
        result,
        key=lambda x: (
            x.get("stock_score", x.get("score", 0)),
            x["trading_value_okrw"],
            x["change_pct"],
        ),
        reverse=True,
    )
    return result[:NEXT_DAY_COUNT]


# ===== 스냅샷 =====
def make_snapshot(trade_date, generated_at, rows, row_key="rows"):
    return {
        "trade_date": trade_date,
        "generated_at": generated_at,
        row_key: [
            {
                "code": x.get("code", ""),
                "name": x.get("name", ""),
                "market": x.get("market", ""),
                "sector1": x.get("sector1", ""),
                "change_pct": x.get("change_pct", 0),
                "trading_value_okrw": x.get("trading_value_okrw", 0),
                "stock_score": x.get("stock_score", x.get("score", 0)),
            }
            for x in rows
        ],
    }


def resolve_prev_snapshot(current_trade_date, latest_path: Path, previous_path: Path):
    latest_snapshot = load_json(latest_path, default={})
    previous_snapshot = load_json(previous_path, default={})

    latest_trade_date = clean_text(latest_snapshot.get("trade_date"))
    previous_trade_date = clean_text(previous_snapshot.get("trade_date"))

    if latest_trade_date and latest_trade_date != current_trade_date:
        return latest_snapshot

    if previous_trade_date and previous_trade_date != current_trade_date:
        return previous_snapshot

    return {}


def update_snapshot_chain(current_trade_date, generated_at, rows, latest_path: Path, previous_path: Path, row_key="rows"):
    latest_snapshot = load_json(latest_path, default={})
    latest_trade_date = clean_text(latest_snapshot.get("trade_date"))

    if latest_trade_date and latest_trade_date != current_trade_date:
        save_json(previous_path, latest_snapshot)

    current_snapshot = make_snapshot(current_trade_date, generated_at, rows, row_key=row_key)
    save_json(latest_path, current_snapshot)


# ===== 전일 1타 -> 오늘 눌림 =====
def make_leader_snapshot(trade_date, generated_at, leaders):
    return {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "leaders": [
            {
                "code": x.get("code", ""),
                "name": x.get("name", ""),
                "market": x.get("market", ""),
                "sector1": x.get("sector1", ""),
                "change_pct": x.get("change_pct", 0),
                "trading_value_okrw": x.get("trading_value_okrw", 0),
                "stock_score": x.get("stock_score", x.get("score", 0)),
            }
            for x in leaders
        ],
    }


def resolve_prev_leader_snapshot(current_trade_date):
    latest_snapshot = load_json(LATEST_LEADERS_SNAPSHOT_PATH, default={})
    previous_snapshot = load_json(PREVIOUS_LEADERS_SNAPSHOT_PATH, default={})

    latest_trade_date = clean_text(latest_snapshot.get("trade_date"))
    previous_trade_date = clean_text(previous_snapshot.get("trade_date"))

    if latest_trade_date and latest_trade_date != current_trade_date:
        return latest_snapshot

    if previous_trade_date and previous_trade_date != current_trade_date:
        return previous_snapshot

    return {}


def update_leader_snapshots(current_trade_date, generated_at, leaders):
    latest_snapshot = load_json(LATEST_LEADERS_SNAPSHOT_PATH, default={})
    latest_trade_date = clean_text(latest_snapshot.get("trade_date"))

    if latest_trade_date and latest_trade_date != current_trade_date:
        save_json(PREVIOUS_LEADERS_SNAPSHOT_PATH, latest_snapshot)

    current_snapshot = make_leader_snapshot(current_trade_date, generated_at, leaders)
    save_json(LATEST_LEADERS_SNAPSHOT_PATH, current_snapshot)


def apply_prev_leader_transition(prev_snapshot, pullback):
    prev_codes = {
        clean_text(x.get("code"))
        for x in prev_snapshot.get("leaders", [])
        if clean_text(x.get("code"))
    }

    transitioned = []
    updated_pullback = []

    for row in pullback:
        row2 = row.copy()
        row2["from_prev_leader"] = row2.get("code") in prev_codes
        updated_pullback.append(row2)

        if row2["from_prev_leader"]:
            transitioned.append({
                "code": row2.get("code", ""),
                "name": row2.get("name", ""),
                "market": row2.get("market", ""),
                "sector1": row2.get("sector1", ""),
                "sector2": row2.get("sector2", ""),
                "change_pct": row2.get("change_pct", 0),
                "trading_value_okrw": row2.get("trading_value_okrw", 0),
                "price": row2.get("price", 0),
                "stock_score": row2.get("stock_score", row2.get("score", 0)),
                "transition_label": "D-1 (오늘 눌림)",
            })

    return updated_pullback, transitioned


# ===== 전일 D-1 -> 오늘 D-2 =====
def apply_prev_d1_transition(prev_d1_snapshot, current_d1_rows):
    prev_d1_codes = {
        clean_text(x.get("code"))
        for x in prev_d1_snapshot.get("rows", [])
        if clean_text(x.get("code"))
    }

    d2_rows = []
    for row in current_d1_rows:
        code = clean_text(row.get("code"))
        if code in prev_d1_codes:
            row2 = row.copy()
            row2["from_prev_d1"] = True
            row2["transition_label"] = "D-2"
            d2_rows.append(row2)

    d2_rows = dedupe_rows(d2_rows)
    d2_rows = sorted(
        d2_rows,
        key=lambda x: (
            x.get("stock_score", x.get("score", 0)),
            x.get("trading_value_okrw", 0),
            x.get("change_pct", 0),
        ),
        reverse=True,
    )
    return d2_rows[:D2_COUNT]


def apply_reset_if_needed(retention: dict, leaders, pullback, next_day, transitioned, d2_rows):
    if not retention.get("should_reset_for_new_day"):
        return leaders, pullback, next_day, transitioned, d2_rows
    return [], [], [], [], []


# ===== 출력 =====
def build_output(
    raw,
    scored_rows,
    sectors,
    leaders,
    pullback,
    next_day,
    prev_snapshot,
    transitioned,
    prev_d1_snapshot,
    d2_rows,
    retention,
    now_kst,
):
    universe_rows = raw.get("rows", [])
    filtered_etf_stock_count = to_int(raw.get("summary", {}).get("filtered_etf_stock_count", 0))
    tracked_sector_count = len({clean_text(r.get("sector1")) for r in scored_rows if clean_text(r.get("sector1"))})

    market_bias = calc_market_bias(scored_rows)
    prev_trade_date = clean_text(prev_snapshot.get("trade_date"))
    prev_d1_trade_date = clean_text(prev_d1_snapshot.get("trade_date"))

    return {
        "meta": {
            "trade_date": retention.get("display_trade_date") or resolve_trade_date(raw),
            "raw_trade_date": retention.get("raw_trade_date") or resolve_trade_date(raw),
            "generated_at": resolve_generated_at(raw),
            "generated_at_kst": format_dt_kst(now_kst),
            "mode": "closing",
            "market": clean_text(raw.get("meta", {}).get("market", "KRX")),
            "currency": "KRW",
            "session_state": retention.get("session_state", "unknown"),
            "is_hold_active": bool(retention.get("is_hold_active", False)),
            "hold_until_kst": retention.get("hold_until_kst", ""),
            "holiday_source": retention.get("holiday_source", "weekend_only"),
        },
        "summary": {
            "input_rows": len(universe_rows),
            "after_filter_rows": len(scored_rows),
            "tracked_sector_count": tracked_sector_count,
            "filtered_etf_stock_count": filtered_etf_stock_count,
            "market_bias": market_bias,
            "reset_applied": bool(retention.get("should_reset_for_new_day", False)),
        },
        "transition_summary": {
            "prev_trade_date": prev_trade_date,
            "leader_to_pullback_count": len(transitioned),
            "prev_d1_trade_date": prev_d1_trade_date,
            "d2_count": len(d2_rows),
        },
        "market_bias": market_bias,
        "leaders": leaders,
        "pullback": pullback,
        "next_day": next_day,
        "leader_to_pullback": transitioned,
        "d2_pullback": d2_rows,
        "top_sectors": sectors[:TOP_SECTOR_COUNT],
    }


# ===== 메인 =====
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="closing")
    args = parser.parse_args()

    raw = load_json(INPUT_PATH)
    rows = raw.get("rows", [])

    normalized_rows = [normalize_row(r) for r in rows]
    normalized_rows = [
        r for r in normalized_rows
        if r["sector1"] and r["trading_value_okrw"] >= MIN_BASE_TRADING
    ]

    scored_rows = score_stocks(normalized_rows)
    sectors = build_sectors(scored_rows)

    leaders = pick_leaders(sectors)
    pullback = pick_pullback(scored_rows, leaders, sectors)
    next_day = pick_next_day(scored_rows, leaders, pullback, sectors)

    current_trade_date = resolve_trade_date(raw)
    generated_at = resolve_generated_at(raw)
    now_kst = datetime.now(KST)
    holidays = load_krx_holidays()
    retention = compute_retention_context(current_trade_date, now_kst, holidays)

    prev_snapshot = resolve_prev_leader_snapshot(current_trade_date)
    pullback, transitioned = apply_prev_leader_transition(prev_snapshot, pullback)

    prev_d1_snapshot = resolve_prev_snapshot(
        current_trade_date,
        LATEST_D1_SNAPSHOT_PATH,
        PREVIOUS_D1_SNAPSHOT_PATH,
    )
    d2_rows = apply_prev_d1_transition(prev_d1_snapshot, transitioned)

    leaders, pullback, next_day, transitioned, d2_rows = apply_reset_if_needed(
        retention,
        leaders,
        pullback,
        next_day,
        transitioned,
        d2_rows,
    )

    payload = build_output(
        raw,
        scored_rows,
        sectors,
        leaders,
        pullback,
        next_day,
        prev_snapshot,
        transitioned,
        prev_d1_snapshot,
        d2_rows,
        retention,
        now_kst,
    )
    save_json(OUTPUT_PATH, payload)

    if not retention.get("should_reset_for_new_day"):
        update_leader_snapshots(current_trade_date, generated_at, leaders)
        update_snapshot_chain(
            current_trade_date,
            generated_at,
            transitioned,
            LATEST_D1_SNAPSHOT_PATH,
            PREVIOUS_D1_SNAPSHOT_PATH,
            row_key="rows",
        )

    print(f"[INFO] scored_rows={len(scored_rows)}")
    print(f"[INFO] sectors={len(sectors)}")
    print(f"[INFO] leaders={len(leaders)}")
    print(f"[INFO] pullback={len(pullback)}")
    print(f"[INFO] next_day={len(next_day)}")
    print(f"[INFO] d1_transition={len(transitioned)}")
    print(f"[INFO] d2_pullback={len(d2_rows)}")
    print(f"[OK] leader_board.json 생성 완료 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
