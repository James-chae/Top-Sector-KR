# -*- coding: utf-8 -*-
"""
run_kr_pipeline.py

Top-Sector-KR 실전 파이프라인
- scripts/fetch_latest_krx.py
- scripts/build_market_raw_from_latest_krx.py
- scripts/score_leaders.py
- scripts/update_sector_calendar.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"

FETCH_SCRIPT = SCRIPTS_DIR / "fetch_latest_krx.py"
BUILD_SCRIPT = SCRIPTS_DIR / "build_market_raw_from_latest_krx.py"
SCORE_SCRIPT = SCRIPTS_DIR / "score_leaders.py"
CALENDAR_SCRIPT = SCRIPTS_DIR / "update_sector_calendar.py"

LATEST_PATH = DATA_DIR / "latest_krx.json"
MARKET_RAW_PATH = DATA_DIR / "market_raw.json"
LEADER_PATH = DATA_DIR / "leader_board.json"
CALENDAR_PATH = DATA_DIR / "sector_calendar_history.json"
META_PATH = DATA_DIR / "dashboard_meta.json"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_step(title: str, cmd: list[str]) -> None:
    print(f"\n{'=' * 72}")
    print(f"[STEP] {title}")
    print(f"[CMD ] {' '.join(cmd)}")
    print(f"{'=' * 72}")

    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{title} 실패 (exit code={completed.returncode})")


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"필수 파일 없음: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_latest() -> dict:
    payload = load_json(LATEST_PATH)
    rows = payload.get("rows", [])
    count = int(payload.get("count", 0))
    meta = payload.get("meta", {})

    if not isinstance(rows, list) or not rows:
        raise RuntimeError("latest_krx.json rows 가 비어 있음")
    if count <= 0:
        raise RuntimeError("latest_krx.json count 가 비정상")

    print(f"[INFO] latest count={count}")
    print(f"[INFO] latest session_state={meta.get('session_state', payload.get('session_state', ''))}")
    print(f"[INFO] latest generated_at_kst={meta.get('generated_at_kst', payload.get('generated_at_kst', ''))}")
    return payload


def validate_market_raw() -> dict:
    payload = load_json(MARKET_RAW_PATH)
    rows = payload.get("rows", [])
    summary = payload.get("summary", {})

    if not isinstance(rows, list) or not rows:
        raise RuntimeError("market_raw.json rows 가 비어 있음")

    market_raw_count = int(summary.get("market_raw_count", summary.get("count", 0)))
    if market_raw_count <= 0:
        raise RuntimeError("market_raw.json row count 가 비정상")

    print(f"[INFO] market_raw_count={market_raw_count}")
    print(f"[INFO] filtered_etf_stock_count={summary.get('filtered_etf_stock_count', 0)}")
    print(f"[INFO] unmatched_sector_stock_count={summary.get('unmatched_sector_stock_count', 0)}")
    return payload


def validate_leader_board() -> dict:
    payload = load_json(LEADER_PATH)
    meta = payload.get("meta", {})
    leaders = payload.get("leaders", [])
    sectors = payload.get("top_sectors", [])

    print(f"[INFO] leader_count={len(leaders)}")
    print(f"[INFO] sector_count={len(sectors)}")

    if not isinstance(leaders, list):
        raise RuntimeError("leader_board.json leaders 구조가 비정상")
    if not isinstance(sectors, list):
        raise RuntimeError("leader_board.json top_sectors 구조가 비정상")
    if len(leaders) <= 0:
        raise RuntimeError("leader_board.json leaders 가 비어 있음")
    if len(sectors) <= 0:
        raise RuntimeError("leader_board.json top_sectors 가 비어 있음")

    return payload


def validate_calendar() -> dict:
    payload = load_json(CALENDAR_PATH)
    history = payload.get("history", [])

    if not isinstance(history, list):
        raise RuntimeError("sector_calendar_history.json history 구조가 비정상")

    print(f"[INFO] history_days={payload.get('meta', {}).get('days', len(history))}")
    if history:
        print(f"[INFO] latest_date={history[-1].get('date', '')}")
    return payload


def write_dashboard_meta(
    latest_payload: dict,
    market_raw_payload: dict,
    leader_payload: dict,
    calendar_payload: dict,
) -> None:
    latest_meta = latest_payload.get("meta", {})
    raw_summary = market_raw_payload.get("summary", {})
    leader_meta = leader_payload.get("meta", {})
    calendar_meta = calendar_payload.get("meta", {})

    meta_payload = {
        "trade_date": leader_meta.get("trade_date", latest_meta.get("trade_date", "")),
        "generated_at_kst": latest_meta.get("generated_at_kst", latest_payload.get("generated_at_kst", "")),
        "mode": leader_meta.get("mode", ""),
        "session_state": leader_meta.get("session_state", latest_meta.get("session_state", "")),
        "pipeline_ok": True,
        "source": "run_kr_pipeline_real",
        "counts": {
            "latest_krx_rows": int(latest_payload.get("count", 0)),
            "market_raw_rows": int(raw_summary.get("market_raw_count", raw_summary.get("count", 0))),
            "leader_count": int(leader_meta.get("leader_count", 0)),
            "sector_count": int(leader_meta.get("sector_count", 0)),
            "calendar_days": int(calendar_meta.get("days", len(calendar_payload.get("history", [])))),
        },
        "notes": "real pipeline: fetch -> market_raw -> score -> calendar",
    }

    META_PATH.write_text(
        json.dumps(meta_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] dashboard_meta saved -> {META_PATH}")


def ensure_required_files() -> None:
    missing = [str(p) for p in [FETCH_SCRIPT, BUILD_SCRIPT, SCORE_SCRIPT, CALENDAR_SCRIPT] if not p.exists()]
    if missing:
        raise FileNotFoundError("필수 스크립트 없음:\n- " + "\n- ".join(missing))


def main() -> None:
    print(f"[INFO] run_kr_pipeline start: {now_text()}")
    print(f"[INFO] project_root={PROJECT_ROOT}")

    ensure_required_files()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    run_step("Fetch latest KRX", [sys.executable, str(FETCH_SCRIPT)])
    latest_payload = validate_latest()

    run_step("Build market_raw", [sys.executable, str(BUILD_SCRIPT)])
    market_raw_payload = validate_market_raw()

    run_step("Score leaders", [sys.executable, str(SCORE_SCRIPT)])
    leader_payload = validate_leader_board()

    run_step("Update sector calendar", [sys.executable, str(CALENDAR_SCRIPT)])
    calendar_payload = validate_calendar()

    write_dashboard_meta(latest_payload, market_raw_payload, leader_payload, calendar_payload)

    print("\n[OK] KR pipeline completed successfully")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)