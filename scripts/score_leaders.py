from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "leader_count": 20,
    "min_trading_value_okrw": 1000,
    "min_change_pct": 1.0,
    "top_sector_count": 8,
    "per_sector_max": 3,
    "weights": {
        "trading_value": 65,
        "change_pct": 30,
        "volume": 5,
    },
}


@dataclass
class Paths:
    root: Path
    data_dir: Path
    config_dir: Path
    market_raw: Path
    leader_board: Path
    scoring_config: Path


def build_paths() -> Paths:
    script_path = Path(__file__).resolve()
    root = script_path.parent.parent
    data_dir = root / "data"
    config_dir = root / "config"
    return Paths(
        root=root,
        data_dir=data_dir,
        config_dir=config_dir,
        market_raw=data_dir / "market_raw.json",
        leader_board=data_dir / "leader_board.json",
        scoring_config=config_dir / "scoring_config.json",
    )


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


def ensure_default_config(path: Path) -> dict[str, Any]:
    if path.exists():
        loaded = read_json(path, default=None)
        if isinstance(loaded, dict) and loaded:
            return loaded

    write_json(path, DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return max(0.0, min(1.0, value / max_value))


def get_sector_name(row: dict[str, Any]) -> str:
    sector2 = str(row.get("sector2", "") or "").strip()
    sector1 = str(row.get("sector1", "") or "").strip()
    sector = str(row.get("sector", "") or "").strip()
    return sector2 or sector1 or sector or "기타"


def get_trading_value(row: dict[str, Any]) -> float:
    return to_float(
        row.get("trading_value_okrw", row.get("trading_value_eok", 0)),
        0.0,
    )


def build_scored_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    weights = config.get("weights", {})
    w_trading = to_float(weights.get("trading_value", 65))
    w_change = to_float(weights.get("change_pct", 30))
    w_volume = to_float(weights.get("volume", 5))

    max_trading = max((get_trading_value(row) for row in rows), default=0.0)
    max_change = max((max(0.0, to_float(row.get("change_pct", 0))) for row in rows), default=0.0)
    max_volume = max((to_float(row.get("volume", 0)) for row in rows), default=0.0)

    scored_rows: list[dict[str, Any]] = []
    for row in rows:
        trading_value = get_trading_value(row)
        change_pct = to_float(row.get("change_pct", 0))
        volume = to_float(row.get("volume", 0))

        score = (
            normalize(trading_value, max_trading) * w_trading
            + normalize(max(0.0, change_pct), max_change) * w_change
            + normalize(volume, max_volume) * w_volume
        )

        enriched = dict(row)
        enriched["sector"] = get_sector_name(row)
        enriched["trading_value_okrw"] = trading_value
        enriched["score"] = round(score, 2)
        scored_rows.append(enriched)

    return scored_rows


def filter_leader_candidates(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    min_trading = to_float(
        config.get("min_trading_value_okrw", config.get("min_trading_value_eok", 1000)),
        1000,
    )
    min_change = to_float(config.get("min_change_pct", 1.0), 1.0)

    filtered = [
        row for row in rows
        if get_trading_value(row) >= min_trading
        and to_float(row.get("change_pct", 0)) >= min_change
    ]
    if filtered:
        return filtered

    fallback = [
        row for row in rows
        if get_trading_value(row) >= min_trading * 0.7
        and to_float(row.get("change_pct", 0)) >= 0.5
    ]
    return fallback


def select_leaders(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    leader_count = int(config.get("leader_count", 20))
    per_sector_max = int(config.get("per_sector_max", 3))

    ranked = sorted(
        rows,
        key=lambda row: (
            to_float(row.get("score", 0)),
            get_trading_value(row),
            to_float(row.get("change_pct", 0)),
        ),
        reverse=True,
    )

    output: list[dict[str, Any]] = []
    sector_counts: dict[str, int] = {}

    for row in ranked:
        sector = get_sector_name(row)
        if sector_counts.get(sector, 0) >= per_sector_max:
            continue

        item = dict(row)
        item["sector"] = sector
        item["rank"] = len(output) + 1
        output.append(item)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

        if len(output) >= leader_count:
            break

    return output


def build_top_sectors(leaders: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    sector_stats: dict[str, dict[str, Any]] = {}

    for row in leaders:
        sector = get_sector_name(row)
        stat = sector_stats.setdefault(
            sector,
            {
                "sector": sector,
                "leaders": 0,
                "score_sum": 0.0,
                "change_sum": 0.0,
                "top_trading_value_okrw": 0.0,
            },
        )
        stat["leaders"] += 1
        stat["score_sum"] += to_float(row.get("score", 0))
        stat["change_sum"] += to_float(row.get("change_pct", 0))
        stat["top_trading_value_okrw"] = max(
            stat["top_trading_value_okrw"],
            get_trading_value(row),
        )

    sector_list: list[dict[str, Any]] = []
    for stat in sector_stats.values():
        leaders_count = max(1, int(stat["leaders"]))
        avg_score = stat["score_sum"] / leaders_count
        avg_change = stat["change_sum"] / leaders_count

        sector_score = min(
            99.0,
            avg_score + leaders_count * 6 + min(stat["top_trading_value_okrw"] / 400, 12),
        )

        sector_list.append(
            {
                "sector": stat["sector"],
                "score": round(sector_score, 1),
                "leaders": leaders_count,
                "avg_change_pct": round(avg_change, 2),
            }
        )

    top_sector_count = int(config.get("top_sector_count", 8))
    sector_list.sort(
        key=lambda item: (
            to_float(item.get("score", 0)),
            to_float(item.get("avg_change_pct", 0)),
            int(item.get("leaders", 0)),
        ),
        reverse=True,
    )
    return sector_list[:top_sector_count]


def detect_market_bias(top_sectors: list[dict[str, Any]]) -> str:
    if not top_sectors:
        return "주도섹터 데이터 부족"
    top_name = str(top_sectors[0].get("sector", ""))
    top_score = to_float(top_sectors[0].get("score", 0))
    return f"{top_name} 중심 강세 / 상위섹터 점수 {top_score:.1f}"


def infer_mode(session_state: str) -> str:
    if session_state == "intraday":
        return "intraday"
    if session_state == "preopen_nxt":
        return "preopen_nxt"
    return "closing"


def build_leader_board_payload(market_raw: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    source_rows = market_raw.get("rows", [])
    scored_rows = build_scored_rows(source_rows, config)
    candidates = filter_leader_candidates(scored_rows, config)
    leaders = select_leaders(candidates, config)
    top_sectors = build_top_sectors(leaders, config)

    for row in leaders:
        row["score"] = round(to_float(row.get("score", 0)), 1)

    meta = market_raw.get("meta", {})
    trade_date = meta.get("trade_date", "")
    generated_at_kst = meta.get("generated_at_kst", meta.get("generated_at", ""))
    session_state = meta.get("session_state", "")

    return {
        "meta": {
            "trade_date": trade_date,
            "generated_at_kst": generated_at_kst,
            "mode": infer_mode(session_state),
            "session_state": session_state,
            "leader_count": len(leaders),
            "sector_count": len(top_sectors),
            "market_bias": detect_market_bias(top_sectors),
            "filtered_etf": "ETF 제외 적용",
            "source_status": "score_leaders_from_market_raw_real",
            "config": {
                "leader_count": int(config.get("leader_count", 20)),
                "min_trading_value_okrw": to_float(
                    config.get("min_trading_value_okrw", config.get("min_trading_value_eok", 1000))
                ),
                "min_change_pct": to_float(config.get("min_change_pct", 1.0)),
                "top_sector_count": int(config.get("top_sector_count", 8)),
                "per_sector_max": int(config.get("per_sector_max", 3)),
                "weights": config.get("weights", {}),
            },
        },
        "top_sectors": top_sectors,
        "leaders": leaders,
    }


def main() -> None:
    paths = build_paths()
    market_raw = read_json(paths.market_raw, default=None)
    if not market_raw or "rows" not in market_raw:
        raise SystemExit("[ERROR] data/market_raw.json 이 없습니다. 먼저 scripts/build_market_raw_from_latest_krx.py 를 실행하세요.")

    config = ensure_default_config(paths.scoring_config)
    payload = build_leader_board_payload(market_raw, config)
    write_json(paths.leader_board, payload)

    print("[OK] score_leaders.py completed")
    print(f" - root: {paths.root}")
    print(f" - leader_board.json: {paths.leader_board}")
    print(f" - leader_count: {payload['meta']['leader_count']}")
    print(f" - sector_count: {payload['meta']['sector_count']}")
    print(f" - scoring_config.json: {paths.scoring_config}")


if __name__ == "__main__":
    main()