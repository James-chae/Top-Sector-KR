from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def format_kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def format_date(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d")


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


def run_step(script_path: Path) -> None:
    print(f"[RUN] {script_path.name}")
    subprocess.run([sys.executable, str(script_path)], check=True)
    print(f"[OK]  {script_path.name}")


def build_dashboard_meta(root: Path, dt: datetime) -> dict[str, Any]:
    data_dir = root / "data"
    mode, session_state = detect_session_state(dt)

    latest_krx = read_json(data_dir / "latest_krx.json", default={})
    market_raw = read_json(data_dir / "market_raw.json", default={})
    leader_board = read_json(data_dir / "leader_board.json", default={})
    sector_calendar = read_json(data_dir / "sector_calendar_history.json", default={})

    return {
        "trade_date": leader_board.get("meta", {}).get("trade_date", format_date(dt)),
        "generated_at_kst": format_kst(dt),
        "mode": leader_board.get("meta", {}).get("mode", mode),
        "session_state": leader_board.get("meta", {}).get("session_state", session_state),
        "pipeline_ok": True,
        "source": "run_kr_pipeline_orchestrator",
        "counts": {
            "latest_krx_rows": int(latest_krx.get("meta", {}).get("count", 0) or 0),
            "market_raw_rows": int(market_raw.get("summary", {}).get("count", 0) or 0),
            "leader_count": int(leader_board.get("meta", {}).get("leader_count", 0) or 0),
            "sector_count": int(leader_board.get("meta", {}).get("sector_count", 0) or 0),
            "calendar_days": int(sector_calendar.get("meta", {}).get("days", 0) or 0),
        },
        "notes": "sample overwrite 제거. 개별 스크립트 실행 결과를 집계하는 오케스트레이터.",
    }


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    scripts_dir = root / "scripts"
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    ordered_scripts = [
        scripts_dir / "fetch_latest_krx.py",
        scripts_dir / "build_market_raw.py",
        scripts_dir / "score_leaders.py",
        scripts_dir / "update_sector_calendar.py",
    ]

    for script_path in ordered_scripts:
        if not script_path.exists():
            raise FileNotFoundError(f"필수 스크립트 없음: {script_path}")
        run_step(script_path)

    dt = now_kst()
    dashboard_meta = build_dashboard_meta(root, dt)
    write_json(data_dir / "dashboard_meta.json", dashboard_meta)

    print("[OK] run_kr_pipeline.py completed")
    print(f" - root: {root}")
    print(f" - dashboard_meta.json: {data_dir / 'dashboard_meta.json'}")
    print(f" - generated_at_kst: {format_kst(dt)}")


if __name__ == "__main__":
    main()
