# -*- coding: utf-8 -*-
"""
run_kr_pipeline.py

목적
- Top-Sector-KR 한국 전용 파이프라인 오케스트레이터
- fetch_latest_krx.py 실행
- scripts/build_market_raw_from_latest_krx.py 실행
- 중간 실패 시 즉시 중단
- 샘플 데이터 덮어쓰기 금지
- 최종 산출물 존재 여부 확인

권장 실행 위치
- 프로젝트 루트
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"

FETCH_SCRIPT = PROJECT_ROOT / "fetch_latest_krx.py"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_market_raw_from_latest_krx.py"

LATEST_PATH = DATA_DIR / "latest_krx.json"
MARKET_RAW_PATH = DATA_DIR / "market_raw.json"
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

    if count != len(rows):
        print(f"[WARN] latest count({count}) != rows length({len(rows)})")

    print(f"[INFO] latest count={count}")
    print(f"[INFO] latest session_state={meta.get('session_state', '')}")
    print(f"[INFO] latest generated_at_kst={meta.get('generated_at_kst', payload.get('generated_at_kst', ''))}")

    return payload


def validate_market_raw() -> dict:
    payload = load_json(MARKET_RAW_PATH)
    rows = payload.get("rows", [])
    summary = payload.get("summary", {})

    if not isinstance(rows, list) or not rows:
        raise RuntimeError("market_raw.json rows 가 비어 있음")

    market_raw_count = int(summary.get("market_raw_count", 0))
    if market_raw_count <= 0:
        raise RuntimeError("market_raw.json market_raw_count 가 비정상")

    print(f"[INFO] market_raw_count={market_raw_count}")
    print(f"[INFO] filtered_etf_stock_count={summary.get('filtered_etf_stock_count', 0)}")
    print(f"[INFO] unmatched_sector_stock_count={summary.get('unmatched_sector_stock_count', 0)}")

    return payload


def write_dashboard_meta(latest_payload: dict, market_raw_payload: dict) -> None:
    latest_meta = latest_payload.get("meta", {})
    latest_summary_count = int(latest_payload.get("count", 0))
    raw_summary = market_raw_payload.get("summary", {})

    meta_payload = {
        "generated_at": now_text(),
        "pipeline": "kr_only",
        "status": "ok",
        "latest": {
            "count": latest_summary_count,
            "session_state": latest_meta.get("session_state", ""),
            "generated_at": latest_meta.get("generated_at", latest_payload.get("generated_at", "")),
            "generated_at_kst": latest_meta.get("generated_at_kst", latest_payload.get("generated_at_kst", "")),
        },
        "market_raw": {
            "market_raw_count": int(raw_summary.get("market_raw_count", 0)),
            "tracked_sector_count": int(raw_summary.get("tracked_sector_count", 0)),
            "unmatched_sector_stock_count": int(raw_summary.get("unmatched_sector_stock_count", 0)),
            "filtered_etf_stock_count": int(raw_summary.get("filtered_etf_stock_count", 0)),
            "ignored_other_sector_stock_count": int(raw_summary.get("ignored_other_sector_stock_count", 0)),
        },
    }

    META_PATH.write_text(
        json.dumps(meta_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] dashboard_meta saved -> {META_PATH}")


def ensure_required_files() -> None:
    missing = [str(p) for p in [FETCH_SCRIPT, BUILD_SCRIPT] if not p.exists()]
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

    write_dashboard_meta(latest_payload, market_raw_payload)

    print("\n[OK] KR pipeline completed successfully")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
