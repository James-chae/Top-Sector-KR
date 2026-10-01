# -*- coding: utf-8 -*-
"""
update_leader_stock_calendar.py

주도주달력 기록
- data/leader_board.json 의 1순위 섹터(top_sectors[0]) 주도주 종목명을
  화면 "오늘의 주도섹터 요약"과 같은 순서(score 내림차순, 최대 3개)로
  data/leader_stock_calendar_history.json 에 날짜별로 누적한다.
- 기존 데이터 파일은 읽기만 한다. 네트워크 호출 없음.
- 계산 결과가 기존 기록과 같으면 파일을 저장하지 않는다(변경 없음).

사용 예
  python scripts/update_leader_stock_calendar.py
  python scripts/update_leader_stock_calendar.py --dry-run --now "2026-09-30 20:05"
  python scripts/update_leader_stock_calendar.py --backfill-git   (수동 1회 전용)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = timezone(timedelta(hours=9))


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

LEADER_PATH = DATA_DIR / "leader_board.json"
HOLIDAY_PATH = DATA_DIR / "krx_holidays.json"
SECTOR_CALENDAR_PATH = DATA_DIR / "sector_calendar_history.json"
OUTPUT_PATH = DATA_DIR / "leader_stock_calendar_history.json"

RECORD_START_HHMM = 900   # 09:00 이전 데이터는 전일/프리마켓 값이라 기록하지 않음
FINAL_HHMM = 1530         # 15:30 이후 실행에서 확정
STOCK_LIMIT = 3           # app.js getSectorLeaderItems 와 동일
BACKFILL_MONTHS = 6


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def load_holidays() -> set[str]:
    try:
        return set(read_json(HOLIDAY_PATH, {}).get("holidays", []))
    except Exception:
        return set()


def parse_ymd(text: str) -> date | None:
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def is_trading_day(d: date, holidays: set[str]) -> bool:
    return d.weekday() < 5 and d.isoformat() not in holidays


def final_sector_name(item: dict[str, Any]) -> str:
    # app.js getFinalSectorName 과 동일
    return item.get("sector") or item.get("sector1") or item.get("sector2") or "-"


def pick_top_sector_stocks(board: dict[str, Any]) -> tuple[str, list[str]]:
    """화면 '오늘의 주도섹터 요약' 1순위 섹터와 그 종목명(표시 순서)."""
    sectors = board.get("top_sectors") or []
    if not sectors:
        return "", []
    sector = str(sectors[0].get("sector") or "").strip()
    if not sector:
        return "", []

    leaders = [x for x in (board.get("leaders") or []) if final_sector_name(x) == sector]

    def score_of(item: dict[str, Any]) -> float:
        try:
            return float(item.get("score") or 0)
        except (TypeError, ValueError):
            return 0.0

    # Python sorted 는 안정 정렬 -> JS Array.sort 와 같은 동점 순서
    leaders = sorted(leaders, key=score_of, reverse=True)[:STOCK_LIMIT]
    stocks = [str(x.get("name")) for x in leaders if x.get("name")]
    return sector, stocks


def empty_payload() -> dict[str, Any]:
    return {"version": 1, "days": {}}


def load_output(path: Path) -> dict[str, Any]:
    payload = read_json(path, default=None)  # 깨진 JSON 이면 예외 -> 덮어쓰지 않음
    if payload is None:
        return empty_payload()
    if not isinstance(payload, dict) or not isinstance(payload.get("days"), dict):
        raise RuntimeError(f"기존 파일 구조가 비정상이라 덮어쓰지 않음: {path}")
    return payload


def build_today_entry(
    board: dict[str, Any],
    existing_days: dict[str, Any],
    now: datetime,
    holidays: set[str],
) -> tuple[str | None, dict[str, Any] | None, str]:
    """(날짜, 새 항목, 메시지). 새 항목이 None 이면 기록하지 않는다."""
    trade_date = str((board.get("meta") or {}).get("trade_date") or "").strip()
    d = parse_ymd(trade_date)
    if d is None:
        return None, None, "기록 조건 아님: trade_date 없음"
    if not is_trading_day(d, holidays):
        return trade_date, None, f"기록 조건 아님: {trade_date} 주말/휴장일"

    hhmm = now.hour * 100 + now.minute
    if now.date() != d:
        return trade_date, None, f"기록 조건 아님: 현재 KST 날짜 {now.date()} != trade_date {trade_date}"
    if hhmm < RECORD_START_HHMM:
        return trade_date, None, f"기록 조건 아님: 09:00 이전 ({now:%H:%M})"

    sector, stocks = pick_top_sector_stocks(board)
    if not sector or not stocks:
        return trade_date, None, f"기록 유지: {trade_date} 1순위 섹터/종목 없음"

    old = existing_days.get(trade_date)
    if isinstance(old, dict) and old.get("final") is True:
        return trade_date, None, f"변경 없음: {trade_date} 이미 확정"

    final = hhmm >= FINAL_HHMM
    if (
        isinstance(old, dict)
        and old.get("sector") == sector
        and old.get("stocks") == stocks
        and old.get("final") == final
    ):
        return trade_date, None, f"변경 없음: {trade_date}"

    entry = {
        "sector": sector,
        "stocks": stocks,
        "final": final,
        "updated_at": now.isoformat(timespec="seconds"),
    }
    return trade_date, entry, f"기록: {trade_date} {sector} {stocks} final={final}"


def sorted_days(days: dict[str, Any]) -> dict[str, Any]:
    return {k: days[k] for k in sorted(days)}


# ---------------------------------------------------------------------------
# 백필 (수동 1회 전용: git 이력의 leader_board.json 사용)
# ---------------------------------------------------------------------------

def git_text(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {completed.stderr.strip()}")
    return completed.stdout


def calendar_top_sector(entry: dict[str, Any]) -> tuple[str, float | None]:
    """sector_calendar_history 항목의 1순위 (섹터명, 점수). 현재 형식(sectors)만 인정."""
    sectors = entry.get("sectors")
    if isinstance(sectors, list) and sectors:
        try:
            score = round(float(sectors[0].get("score")), 1)
        except (TypeError, ValueError):
            score = None
        return str(sectors[0].get("name") or ""), score
    return "", None


def board_top_score(board: dict[str, Any]) -> float | None:
    sectors = board.get("top_sectors") or []
    if not sectors or "score" not in sectors[0]:
        return None
    try:
        return round(float(sectors[0].get("score")), 1)
    except (TypeError, ValueError):
        return None


def months_back_start(d: date, months: int) -> date:
    index = d.year * 12 + (d.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def backfill_from_git(
    payload: dict[str, Any],
    reference: date,
    now: datetime,
    holidays: set[str],
) -> dict[str, int]:
    days = payload["days"]
    start = months_back_start(reference, BACKFILL_MONTHS)

    calendar = read_json(SECTOR_CALENDAR_PATH, {}) or {}
    calendar_top = {
        str(item.get("date")): calendar_top_sector(item)
        for item in calendar.get("history", [])
        if isinstance(item, dict)
    }

    # 커밋 시각(KST) 날짜별 그룹 (오래된 순)
    groups: dict[date, list[tuple[str, datetime]]] = {}
    for line in git_text(["log", "--reverse", "--format=%H %cI", "--", "data/leader_board.json"]).splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) != 2:
            continue
        committed = datetime.fromisoformat(parts[1]).astimezone(KST)
        groups.setdefault(committed.date(), []).append((parts[0], committed))

    candidates = set(groups) | {x for x in (parse_ymd(k) for k in calendar_top) if x}
    stats = {"filled": 0, "mismatch": 0, "no_candidate": 0, "already": 0}

    for d in sorted(candidates):
        if d < start or d >= now.date() or not is_trading_day(d, holidays):
            continue
        key = d.isoformat()
        if key in days:
            stats["already"] += 1
            continue

        found = None
        for commit, committed in reversed(groups.get(d, [])):
            if committed.hour * 100 + committed.minute < RECORD_START_HHMM:
                break
            try:
                board = json.loads(git_text(["show", f"{commit}:data/leader_board.json"]))
            except Exception:
                continue
            if str((board.get("meta") or {}).get("trade_date") or "") == key:
                found = (board, committed)
                break

        if found is None:
            stats["no_candidate"] += 1
            print(f"[BACKFILL] 후보 없음: {key}")
            continue

        board, committed = found
        sector, stocks = pick_top_sector_stocks(board)
        if not sector or not stocks:
            stats["no_candidate"] += 1
            print(f"[BACKFILL] 후보 없음(종목 없음): {key}")
            continue

        # 교차검증: 주도섹터달력에 저장된 1순위 섹터명과 점수가 모두 같아야
        # 그 날 화면에 최종 표시된 leader_board 와 같은 버전으로 인정한다.
        expected_name, expected_score = calendar_top.get(key, ("", None))
        git_score = board_top_score(board)
        if expected_name != sector or expected_score is None or git_score is None or abs(expected_score - git_score) > 0.05:
            stats["mismatch"] += 1
            print(
                f"[BACKFILL] 불일치 skip: {key} git={sector}({git_score}) "
                f"calendar={expected_name or '(없음)'}({expected_score})"
            )
            continue

        days[key] = {
            "sector": sector,
            "stocks": stocks,
            "final": True,
            "updated_at": committed.isoformat(timespec="seconds"),
            "source": "backfill",
        }
        stats["filled"] += 1

    return stats


# ---------------------------------------------------------------------------

def parse_now(text: str | None) -> datetime:
    if not text:
        return datetime.now(KST)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    raise SystemExit(f'[ERROR] --now 형식 오류: "{text}" (예: "2026-09-30 20:05")')


def main() -> None:
    parser = argparse.ArgumentParser(description="주도주달력 기록")
    parser.add_argument("--dry-run", action="store_true", help="파일 저장 없이 결과만 출력")
    parser.add_argument("--now", type=str, help='시각 가정 (KST), 예: "2026-09-30 20:05"')
    parser.add_argument("--out", type=str, help="출력 JSON 경로")
    parser.add_argument("--backfill-git", action="store_true", help="git 이력으로 과거 6개월 백필 (수동 1회 전용)")
    args = parser.parse_args()

    now = parse_now(args.now)
    out_path = Path(args.out).resolve() if args.out else OUTPUT_PATH
    holidays = load_holidays()
    board = read_json(LEADER_PATH, {}) or {}

    payload = load_output(out_path)
    file_exists = out_path.exists()
    changed = False
    trade_date = None

    print(f"[INFO] now={now.isoformat(timespec='seconds')} out={out_path}")

    if args.backfill_git:
        reference = parse_ymd((board.get("meta") or {}).get("trade_date", "")) or now.date()
        stats = backfill_from_git(payload, reference, now, holidays)
        print(
            f"[BACKFILL] 채움 {stats['filled']}일 / 불일치 skip {stats['mismatch']}일 / "
            f"후보 없음 {stats['no_candidate']}일 / 기존 기록 유지 {stats['already']}일"
        )
        changed = stats["filled"] > 0
    else:
        trade_date, entry, message = build_today_entry(board, payload["days"], now, holidays)
        print(f"[INFO] {message}")
        if entry is not None:
            payload["days"][trade_date] = entry
            changed = True

    if args.dry_run:
        if trade_date:
            print(json.dumps({trade_date: payload["days"].get(trade_date)}, ensure_ascii=False, indent=2))
        else:
            print(f"[DRY-RUN] days={len(payload['days'])}")
        print("[DRY-RUN] 저장하지 않음")
        return

    if not changed and file_exists:
        print("[OK] 변경 없음")
        return

    payload = {"version": 1, "days": sorted_days(payload["days"])}
    write_json_atomic(out_path, payload)
    print(f"[OK] saved -> {out_path} (days={len(payload['days'])})")


if __name__ == "__main__":
    main()
