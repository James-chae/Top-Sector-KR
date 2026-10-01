# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")

# 2026-09-30 버그 수정: 추석(9/24~25) 등 "평일이지만 KRX 휴장일"에도
# 이 스크립트가 평일 여부만 보고 실행을 허용해서, 네이버가 내려주는
# 마지막 거래일(직전 영업일) 데이터를 그날 데이터인 것처럼 착각해
# 주도섹터 달력에 중복 기록하는 사고가 있었다.
# -> data/krx_holidays.json에 등록된 날짜는 평일이어도 주말과 똑같이
#    취급해서 실행하지 않는다. 파일이 없으면 기존처럼 주말 기준으로만
#    동작한다(README에 명시된 원래 설계 의도).
HOLIDAY_FILE = Path(__file__).resolve().parent.parent / "data" / "krx_holidays.json"


def load_holidays() -> set[str]:
    try:
        with open(HOLIDAY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("holidays", []))
    except FileNotFoundError:
        return set()
    except Exception:
        return set()


def is_market_holiday(dt: datetime) -> bool:
    return dt.strftime("%Y-%m-%d") in load_holidays()


@dataclass
class SessionResult:
    input_time: str
    hhmm: int
    is_weekday: bool
    session_state: str
    board_label: str
    should_run_pipeline: bool
    note: str


def to_hhmm(dt: datetime) -> int:
    return dt.hour * 100 + dt.minute


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def classify_session(dt: datetime) -> SessionResult:
    hhmm = to_hhmm(dt)
    weekday = is_weekday(dt)

    if not weekday:
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=False,
            session_state="weekend_hold",
            board_label="주말 유지",
            should_run_pipeline=False,
            note="주말은 자동 갱신 없이 마지막 정상 데이터 유지",
        )

    if is_market_holiday(dt):
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="holiday_hold",
            board_label="휴장일 유지",
            should_run_pipeline=False,
            note="data/krx_holidays.json에 등록된 KRX 휴장일 - 마지막 정상 데이터 유지",
        )

    if hhmm < 750:
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="previous_close",
            board_label="전일 유지",
            should_run_pipeline=False,
            note="07:50 전까지는 전일 종가 기준 유지",
        )

    if hhmm < 800:
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="reset",
            board_label="reset",
            should_run_pipeline=False,
            note="07:50~07:59는 reset 구간 - 네이버가 전일 애프터마켓 포함 값을 내려주므로 실행 안 함",
        )

    if hhmm < 900:
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="preopen_hold",
            board_label="전일 유지",
            should_run_pipeline=False,
            note="09:00 전까지는 전일 15:35 기준 데이터 유지",
        )

    if hhmm <= 1535:
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="live_update_window",
            board_label="장중 갱신",
            should_run_pipeline=True,
            note="09:00~15:35는 언제든 실행 가능 (15:30 이후 애프터마켓 합산 방지)",
        )

    return SessionResult(
        input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        hhmm=hhmm,
        is_weekday=True,
        session_state="final_hold",
        board_label="최종 유지",
        should_run_pipeline=False,
        note="15:35 이후는 최종 데이터 유지",
    )


def parse_input_time(text: str) -> datetime:
    text = text.strip()
    fmts = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=KST)
        except ValueError:
            pass
    raise ValueError(f"지원하지 않는 날짜 형식: {text}")


def print_result(result: SessionResult) -> None:
    print("=" * 72)
    print(f"입력시각            : {result.input_time}")
    print(f"HHMM               : {result.hhmm}")
    print(f"평일여부           : {result.is_weekday}")
    print(f"session_state      : {result.session_state}")
    print(f"board_label        : {result.board_label}")
    print(f"파이프라인 실행여부 : {result.should_run_pipeline}")
    print(f"설명               : {result.note}")


def print_machine_result(result: SessionResult) -> None:
    print(f"should_run_pipeline={'true' if result.should_run_pipeline else 'false'}")
    print(f"session_state={result.session_state}")
    print(f"board_label={result.board_label}")


def run_default_samples() -> None:
    samples = [
        "2026-04-21 07:49",
        "2026-04-21 07:50",
        "2026-04-21 07:55",
        "2026-04-21 08:03",
        "2026-04-21 08:08",
        "2026-04-21 13:27",
        "2026-09-24 10:00",  # 추석 연휴 - 평일이지만 휴장일이어야 함
        "2026-04-21 15:33",
        "2026-04-21 15:35",
        "2026-04-21 15:36",
    ]

    print("[기본 샘플 테스트 시작]")
    for item in samples:
        dt = parse_input_time(item)
        result = classify_session(dt)
        print_result(result)
        print_machine_result(result)
        print("-" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Top-Sector-KR 시간대 판정 검증")
    parser.add_argument("--time", type=str, help='예: "2026-04-21 07:55"')
    parser.add_argument("--now", action="store_true", help="현재 KST 시각으로 판정")
    parser.add_argument("--machine", action="store_true", help="기계용 출력만 표시")
    args = parser.parse_args()

    if args.now:
        dt = datetime.now(KST)
    elif args.time:
        dt = parse_input_time(args.time)
    else:
        run_default_samples()
        return

    result = classify_session(dt)

    if args.machine:
        print_machine_result(result)
        sys.exit(0)

    print_result(result)
    print_machine_result(result)


if __name__ == "__main__":
    main()
