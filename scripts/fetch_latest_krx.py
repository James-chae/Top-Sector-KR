from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))


@dataclass
class OutputPaths:
    root: Path
    data_dir: Path
    latest_krx: Path


def now_kst() -> datetime:
    return datetime.now(KST)


def format_kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def format_date(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def detect_session_state(dt: datetime) -> str:
    hhmm = dt.hour * 100 + dt.minute

    if hhmm < 750:
        return "hold_previous_close"
    if 750 <= hhmm < 800:
        return "pre_open_reset"
    if 800 <= hhmm < 900:
        return "pre_open"
    if 900 <= hhmm <= 1530:
        return "kr_open"
    if 1531 <= hhmm < 2000:
        return "after_close"
    return "keep_after_close"


def build_paths() -> OutputPaths:
    script_path = Path(__file__).resolve()
    root = script_path.parent.parent
    data_dir = root / "data"
    return OutputPaths(
        root=root,
        data_dir=data_dir,
        latest_krx=data_dir / "latest_krx.json",
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_sample_rows() -> list[dict[str, Any]]:
    return [
        {
            "market": "KOSPI",
            "ticker": "005930",
            "name": "삼성전자",
            "price": 84500,
            "change_pct": 4.82,
            "volume": 12345678,
            "trading_value_eok": 3520,
        },
        {
            "market": "KOSPI",
            "ticker": "000660",
            "name": "SK하이닉스",
            "price": 245500,
            "change_pct": 5.31,
            "volume": 8352001,
            "trading_value_eok": 2870,
        },
        {
            "market": "KOSPI",
            "ticker": "010120",
            "name": "LS ELECTRIC",
            "price": 214000,
            "change_pct": 4.12,
            "volume": 1822330,
            "trading_value_eok": 1560,
        },
        {
            "market": "KOSPI",
            "ticker": "042700",
            "name": "한미반도체",
            "price": 117200,
            "change_pct": 6.15,
            "volume": 2512200,
            "trading_value_eok": 1410,
        },
        {
            "market": "KOSPI",
            "ticker": "329180",
            "name": "HD현대중공업",
            "price": 319500,
            "change_pct": 3.48,
            "volume": 620300,
            "trading_value_eok": 1180,
        },
        {
            "market": "KOSPI",
            "ticker": "012450",
            "name": "한화에어로스페이스",
            "price": 283000,
            "change_pct": 2.95,
            "volume": 511200,
            "trading_value_eok": 1020,
        },
        {
            "market": "KOSDAQ",
            "ticker": "357780",
            "name": "솔브레인",
            "price": 318000,
            "change_pct": 2.44,
            "volume": 144200,
            "trading_value_eok": 210,
        },
        {
            "market": "KOSDAQ",
            "ticker": "247540",
            "name": "에코프로비엠",
            "price": 251500,
            "change_pct": 1.97,
            "volume": 771000,
            "trading_value_eok": 640,
        },
    ]


def build_latest_krx_payload(dt: datetime) -> dict[str, Any]:
    rows = build_sample_rows()
    return {
        "meta": {
            "trade_date": format_date(dt),
            "generated_at_kst": format_kst(dt),
            "session_state": detect_session_state(dt),
            "source": "sample_fetch_latest_krx",
            "count": len(rows),
            "non_zero_trading": sum(
                1 for row in rows if float(row.get("trading_value_eok", 0) or 0) > 0
            ),
            "notes": "실데이터 수집기 연결 전 구조 검증용 샘플",
        },
        "rows": rows,
    }


def main() -> None:
    dt = now_kst()
    paths = build_paths()
    ensure_dir(paths.data_dir)

    payload = build_latest_krx_payload(dt)
    write_json(paths.latest_krx, payload)

    print("[OK] fetch_latest_krx.py completed")
    print(f" - root: {paths.root}")
    print(f" - latest_krx.json: {paths.latest_krx}")
    print(f" - generated_at_kst: {format_kst(dt)}")
    print(f" - row_count: {payload['meta']['count']}")


if __name__ == "__main__":
    main()
