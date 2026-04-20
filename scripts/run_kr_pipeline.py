from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))


@dataclass
class Paths:
    root: Path
    data_dir: Path
    config_dir: Path
    leader_board: Path
    sector_calendar_history: Path
    dashboard_meta: Path
    latest_krx: Path
    market_raw: Path


def now_kst() -> datetime:
    return datetime.now(KST)


def format_kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def format_date(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def detect_session_state(dt: datetime) -> tuple[str, str]:
    hhmm = dt.hour * 100 + dt.minute

    if hhmm < 750:
        return "closing", "hold_previous_close"
    if 750 <= hhmm < 800:
        return "transition", "pre_open_reset"
    if 800 <= hhmm < 900:
        return "preopen_nxt", "pre_open"
    if 900 <= hhmm <= 1530:
        return "intraday", "kr_open"
    if 1531 <= hhmm < 2000:
        return "closing", "after_close"
    return "closing", "keep_after_close"


def default_leader_payload(dt: datetime) -> dict[str, Any]:
    mode, session_state = detect_session_state(dt)
    trade_date = format_date(dt)
    generated_at_kst = format_kst(dt)

    leaders = [
        {
            "rank": 1,
            "ticker": "005930",
            "name": "삼성전자",
            "sector": "반도체",
            "change_pct": 4.82,
            "trading_value_eok": 3520,
            "volume": 12345678,
            "score": 95,
        },
        {
            "rank": 2,
            "ticker": "000660",
            "name": "SK하이닉스",
            "sector": "반도체",
            "change_pct": 5.31,
            "trading_value_eok": 2870,
            "volume": 8352001,
            "score": 93,
        },
        {
            "rank": 3,
            "ticker": "010120",
            "name": "LS ELECTRIC",
            "sector": "전력설비",
            "change_pct": 4.12,
            "trading_value_eok": 1560,
            "volume": 1822330,
            "score": 89,
        },
        {
            "rank": 4,
            "ticker": "042700",
            "name": "한미반도체",
            "sector": "반도체",
            "change_pct": 6.15,
            "trading_value_eok": 1410,
            "volume": 2512200,
            "score": 88,
        },
        {
            "rank": 5,
            "ticker": "329180",
            "name": "HD현대중공업",
            "sector": "조선",
            "change_pct": 3.48,
            "trading_value_eok": 1180,
            "volume": 620300,
            "score": 81,
        },
        {
            "rank": 6,
            "ticker": "012450",
            "name": "한화에어로스페이스",
            "sector": "방산",
            "change_pct": 2.95,
            "trading_value_eok": 1020,
            "volume": 511200,
            "score": 77,
        },
    ]

    top_sectors = [
        {"sector": "반도체", "score": 92, "leaders": 3, "avg_change_pct": 5.2},
        {"sector": "전력설비", "score": 88, "leaders": 2, "avg_change_pct": 4.6},
        {"sector": "AI", "score": 84, "leaders": 2, "avg_change_pct": 3.9},
        {"sector": "조선", "score": 79, "leaders": 1, "avg_change_pct": 3.4},
        {"sector": "방산", "score": 74, "leaders": 1, "avg_change_pct": 2.8},
    ]

    return {
        "meta": {
            "trade_date": trade_date,
            "generated_at_kst": generated_at_kst,
            "mode": mode,
            "session_state": session_state,
            "leader_count": len(leaders),
            "sector_count": len(top_sectors),
            "market_bias": "샘플 파이프라인 데이터",
            "filtered_etf": "ETF 제외 기준 준비중",
            "source_status": "sample_pipeline",
        },
        "top_sectors": top_sectors,
        "leaders": leaders,
    }


def build_calendar_history(dt: datetime) -> dict[str, Any]:
    generated_at_kst = format_kst(dt)

    seeds = [
        [("반도체", 90), ("AI", 84), ("전선", 81)],
        [("반도체", 91), ("전력설비", 86), ("AI", 82)],
        [("전력설비", 88), ("반도체", 87), ("조선", 80)],
        [("반도체", 93), ("AI", 85), ("유리기판", 81)],
        [("방산", 82), ("조선", 81)],
        [("반도체", 89), ("전력설비", 84), ("방산", 80)],
        [("전력설비", 90), ("AI", 86), ("반도체", 84)],
        [("반도체", 94), ("조선", 82)],
        [("전력설비", 87), ("방산", 82), ("반도체", 81)],
        [("반도체", 92), ("전력설비", 88), ("AI", 84)],
    ]

    history: list[dict[str, Any]] = []
    cursor = dt.astimezone(KST).date() - timedelta(days=20)

    seed_index = 0
    while len(history) < 10:
        if cursor.weekday() < 5:
            sectors = [
                {"name": name, "score": score}
                for name, score in seeds[seed_index % len(seeds)]
            ]
            history.append(
                {
                    "date": cursor.strftime("%Y-%m-%d"),
                    "sectors": sectors,
                }
            )
            seed_index += 1
        cursor += timedelta(days=1)

    return {
        "meta": {
            "generated_at_kst": generated_at_kst,
            "days": len(history),
            "source_status": "sample_pipeline",
        },
        "history": history,
    }


def build_dashboard_meta(dt: datetime) -> dict[str, Any]:
    mode, session_state = detect_session_state(dt)
    return {
        "trade_date": format_date(dt),
        "generated_at_kst": format_kst(dt),
        "mode": mode,
        "session_state": session_state,
        "pipeline_ok": True,
        "source": "sample_pipeline",
        "notes": "실데이터 수집기 연결 전 구조 검증용",
    }


def merge_with_existing_calendar(
    existing_payload: dict[str, Any] | None,
    new_payload: dict[str, Any],
) -> dict[str, Any]:
    if not existing_payload or "history" not in existing_payload:
        return new_payload

    existing_history = existing_payload.get("history", [])
    incoming_history = new_payload.get("history", [])

    merged_by_date: dict[str, dict[str, Any]] = {}
    for item in existing_history:
        date_value = item.get("date")
        if date_value:
            merged_by_date[date_value] = item

    for item in incoming_history:
        date_value = item.get("date")
        if date_value:
            merged_by_date[date_value] = item

    merged_history = sorted(
        merged_by_date.values(),
        key=lambda x: x.get("date", ""),
    )[-120:]

    meta = new_payload.get("meta", {})
    meta["days"] = len(merged_history)

    return {
        "meta": meta,
        "history": merged_history,
    }


def build_paths() -> Paths:
    script_path = Path(__file__).resolve()
    root = script_path.parent.parent
    data_dir = root / "data"
    config_dir = root / "config"

    return Paths(
        root=root,
        data_dir=data_dir,
        config_dir=config_dir,
        leader_board=data_dir / "leader_board.json",
        sector_calendar_history=data_dir / "sector_calendar_history.json",
        dashboard_meta=data_dir / "dashboard_meta.json",
        latest_krx=data_dir / "latest_krx.json",
        market_raw=data_dir / "market_raw.json",
    )


def main() -> None:
    paths = build_paths()
    ensure_dir(paths.data_dir)
    ensure_dir(paths.config_dir)

    dt = now_kst()

    leader_payload = default_leader_payload(dt)
    calendar_payload = build_calendar_history(dt)
    dashboard_meta = build_dashboard_meta(dt)

    existing_calendar = read_json(paths.sector_calendar_history, default=None)
    merged_calendar = merge_with_existing_calendar(existing_calendar, calendar_payload)

    write_json(paths.leader_board, leader_payload)
    write_json(paths.sector_calendar_history, merged_calendar)
    write_json(paths.dashboard_meta, dashboard_meta)

    print("[OK] run_kr_pipeline.py completed")
    print(f" - root: {paths.root}")
    print(f" - leader_board.json: {paths.leader_board}")
    print(f" - sector_calendar_history.json: {paths.sector_calendar_history}")
    print(f" - dashboard_meta.json: {paths.dashboard_meta}")
    print(f" - generated_at_kst: {format_kst(dt)}")


if __name__ == "__main__":
    main()
