# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

FETCH_SCRIPT = ROOT / "scripts" / "fetch_latest_krx.py"
BUILD_SCRIPT = ROOT / "scripts" / "build_market_raw.py"
SCORE_SCRIPT = ROOT / "scripts" / "score_leaders.py"
CALENDAR_SCRIPT = ROOT / "scripts" / "update_sector_calendar.py"


def run_step(script_path: Path, label: str) -> None:
    if not script_path.exists():
        raise FileNotFoundError(f"{label} 파일 없음: {script_path}")

    print("=" * 72)
    print(f"[RUN] {label}")
    print(f"[FILE] {script_path}")

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=ROOT,
        text=True,
    )

    if result.returncode != 0:
        raise SystemExit(f"[FAIL] {label} 실행 실패 (exit={result.returncode})")

    print(f"[OK] {label} 완료")


def main() -> None:
    print("=" * 72)
    print("[PIPELINE] Top-Sector-KR 통합 실행 시작")

    run_step(FETCH_SCRIPT, "latest_krx 수집")
    run_step(BUILD_SCRIPT, "market_raw 생성")
    run_step(SCORE_SCRIPT, "leader_board 생성")
    run_step(CALENDAR_SCRIPT, "sector_calendar_history 생성")

    print("=" * 72)
    print("[PIPELINE] 전체 완료")
    print("[OUTPUT]")
    print(f" - {ROOT / 'data' / 'latest_krx.json'}")
    print(f" - {ROOT / 'data' / 'market_raw.json'}")
    print(f" - {ROOT / 'data' / 'leader_board.json'}")
    print(f" - {ROOT / 'data' / 'sector_calendar_history.json'}")


if __name__ == "__main__":
    main()
