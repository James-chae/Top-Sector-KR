from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Paths:
    root: Path
    data_dir: Path
    leader_board: Path
    sector_calendar_history: Path


def build_paths() -> Paths:
    script_path = Path(__file__).resolve()
    root = script_path.parent.parent
    data_dir = root / "data"
    return Paths(
        root=root,
        data_dir=data_dir,
        leader_board=data_dir / "leader_board.json",
        sector_calendar_history=data_dir / "sector_calendar_history.json",
    )


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8-sig"
            )
        )

    except Exception as exc:
        raise RuntimeError(
            f"JSON 읽기 실패 - 기존 기록 보호를 위해 중단: "
            f"{path} / {type(exc).__name__}: {exc}"
        ) from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8",
    )

    os.replace(
        temp_path,
        path
    )


def backup_history(
    root: Path,
    history_path: Path
) -> None:

    backup_dir = (
        root.parent
        / "Top-Sector-KR_History_Backups"
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    destination = (
        backup_dir
        / f"sector_calendar_history_{stamp}.json"
    )

    shutil.copy2(
        history_path,
        destination
    )

    backups = sorted(
        backup_dir.glob(
            "sector_calendar_history_*.json"
        ),
        key=lambda item: item.stat().st_mtime,
        reverse=True
    )

    # 최근 30개만 유지
    for old_backup in backups[30:]:
        try:
            old_backup.unlink()
        except OSError:
            pass


def normalize_sector_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("sector", item.get("name", "기타"))),
        "score": round(float(item.get("score", 0) or 0), 1),
    }


def build_today_entry(leader_board: dict[str, Any]) -> dict[str, Any]:
    meta = leader_board.get("meta", {})
    trade_date = str(meta.get("trade_date", "")).strip()
    if not trade_date:
        raise ValueError("leader_board.json meta.trade_date 값이 없습니다.")

    top_sectors = leader_board.get("top_sectors", []) or []
    sectors = [normalize_sector_item(item) for item in top_sectors[:3]]

    return {
        "date": trade_date,
        "sectors": sectors,
    }


def merge_history(existing_history: list[dict[str, Any]], today_entry: dict[str, Any]) -> list[dict[str, Any]]:
    merged_by_date: dict[str, dict[str, Any]] = {}

    for item in existing_history:
        date_value = str(item.get("date", "")).strip()
        if date_value:
            merged_by_date[date_value] = item

    merged_by_date[today_entry["date"]] = today_entry

    merged = sorted(
        merged_by_date.values(),
        key=lambda item: str(item.get("date", "")),
    )

    return merged[-120:]


def build_payload(
    leader_board: dict[str, Any],
    existing_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    meta = leader_board.get("meta", {})
    generated_at_kst = meta.get("generated_at_kst", "")
    today_entry = build_today_entry(leader_board)

    existing_history = []
    if isinstance(existing_payload, dict):
        existing_history = existing_payload.get("history", []) or []

    merged_history = merge_history(existing_history, today_entry)

    return {
        "meta": {
            "generated_at_kst": generated_at_kst,
            "days": len(merged_history),
            "source_status": "update_sector_calendar_from_leader_board",
        },
        "history": merged_history,
    }


def main() -> None:
    paths = build_paths()

    leader_board = read_json(paths.leader_board, default=None)
    if not leader_board or "top_sectors" not in leader_board:
        raise SystemExit(
            "[ERROR] data/leader_board.json 이 없습니다. 먼저 scripts/score_leaders.py 를 실행하세요."
        )

    existing_payload = read_json(
        paths.sector_calendar_history,
        default=None
    )

    if not isinstance(
        existing_payload,
        dict
    ):
        raise SystemExit(
            "[ERROR] 기존 sector_calendar_history.json이 "
            "없거나 구조가 비정상입니다. 자동 덮어쓰기를 차단합니다."
        )

    existing_history = existing_payload.get(
        "history"
    )

    if not isinstance(
        existing_history,
        list
    ):
        raise SystemExit(
            "[ERROR] 기존 history 구조가 비정상입니다."
        )

    # 이미 장기간 운영된 대시보드이므로
    # 갑자기 1~2일로 줄어든 정상 JSON도 차단
    if len(existing_history) < 30:
        raise SystemExit(
            f"[ERROR] 기존 기록이 {len(existing_history)}일뿐입니다. "
            "기록 유실 가능성이 있어 자동 덮어쓰기를 차단합니다."
        )

    backup_history(
        paths.root,
        paths.sector_calendar_history
    )

    payload = build_payload(
        leader_board,
        existing_payload
    )

    # 기존 기록보다 갑자기 줄어드는 결과 금지
    new_history = payload.get(
        "history",
        []
    )

    expected_min = min(
        len(existing_history),
        120
    )

    if len(new_history) < expected_min:
        raise SystemExit(
            f"[ERROR] 기록 감소 감지: "
            f"{len(existing_history)} -> {len(new_history)}. "
            "저장을 차단합니다."
        )

    write_json(
        paths.sector_calendar_history,
        payload
    )

    print("[OK] update_sector_calendar.py completed")
    print(f" - root: {paths.root}")
    print(f" - sector_calendar_history.json: {paths.sector_calendar_history}")
    print(f" - history_days: {payload['meta']['days']}")
    print(f" - latest_date: {payload['history'][-1]['date'] if payload['history'] else '-'}")


if __name__ == "__main__":
    main()
