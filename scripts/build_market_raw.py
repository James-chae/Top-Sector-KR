from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SECTOR_MAP: dict[str, str] = {
    "005930": "반도체",
    "000660": "반도체",
    "010120": "전력설비",
    "042700": "반도체",
    "329180": "조선",
    "012450": "방산",
    "357780": "반도체 소재",
    "247540": "2차전지",
}


@dataclass
class Paths:
    root: Path
    data_dir: Path
    config_dir: Path
    latest_krx: Path
    market_raw: Path
    sector_map_json: Path


def build_paths() -> Paths:
    script_path = Path(__file__).resolve()
    root = script_path.parent.parent
    data_dir = root / "data"
    config_dir = root / "config"
    return Paths(
        root=root,
        data_dir=data_dir,
        config_dir=config_dir,
        latest_krx=data_dir / "latest_krx.json",
        market_raw=data_dir / "market_raw.json",
        sector_map_json=config_dir / "kr_sector_map.json",
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_sector_map(paths: Paths) -> dict[str, str]:
    custom_map = read_json(paths.sector_map_json, default=None)
    if isinstance(custom_map, dict) and custom_map:
        return {str(k): str(v) for k, v in custom_map.items()}
    return DEFAULT_SECTOR_MAP.copy()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def build_market_rows(rows: list[dict[str, Any]], sector_map: dict[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for row in rows:
        ticker = str(row.get("ticker", "")).strip()
        sector = sector_map.get(ticker, "기타")

        output.append(
            {
                "market": row.get("market", ""),
                "ticker": ticker,
                "name": row.get("name", ""),
                "sector": sector,
                "price": row.get("price", 0),
                "change_pct": to_float(row.get("change_pct", 0)),
                "volume": int(to_float(row.get("volume", 0))),
                "trading_value_eok": to_float(row.get("trading_value_eok", 0)),
            }
        )

    return output


def build_market_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kospi_count = sum(1 for row in rows if row.get("market") == "KOSPI")
    kosdaq_count = sum(1 for row in rows if row.get("market") == "KOSDAQ")
    positive_count = sum(1 for row in rows if to_float(row.get("change_pct", 0)) > 0)
    high_value_count = sum(1 for row in rows if to_float(row.get("trading_value_eok", 0)) >= 1000)

    return {
        "count": len(rows),
        "kospi_count": kospi_count,
        "kosdaq_count": kosdaq_count,
        "positive_count": positive_count,
        "high_value_count": high_value_count,
    }


def main() -> None:
    paths = build_paths()
    ensure_dir(paths.data_dir)
    ensure_dir(paths.config_dir)

    latest_payload = read_json(paths.latest_krx, default=None)
    if not latest_payload or "rows" not in latest_payload:
        raise SystemExit(
            "[ERROR] data/latest_krx.json 이 없습니다. 먼저 scripts/fetch_latest_krx.py 를 실행하세요."
        )

    sector_map = load_sector_map(paths)
    source_rows = latest_payload.get("rows", [])
    market_rows = build_market_rows(source_rows, sector_map)
    summary = build_market_summary(market_rows)

    payload = {
        "meta": {
            "trade_date": latest_payload.get("meta", {}).get("trade_date", ""),
            "generated_at_kst": latest_payload.get("meta", {}).get("generated_at_kst", ""),
            "session_state": latest_payload.get("meta", {}).get("session_state", ""),
            "source": "build_market_raw_from_latest_krx",
            "source_row_count": len(source_rows),
            "mapped_sector_count": len({row.get("sector", "") for row in market_rows}),
        },
        "summary": summary,
        "rows": market_rows,
    }

    write_json(paths.market_raw, payload)

    print("[OK] build_market_raw.py completed")
    print(f" - root: {paths.root}")
    print(f" - market_raw.json: {paths.market_raw}")
    print(f" - source_rows: {len(source_rows)}")
    print(f" - mapped_rows: {len(market_rows)}")


if __name__ == "__main__":
    main()
