# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


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
            note="07:50~07:59는 reset 구간, 화면/자동화 분리 확인용",
        )

    if hhmm < 2000:
        minute = dt.minute
        should_run = (minute % 5 == 0)
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="live_update_window",
            board_label="장중/주간 갱신",
            should_run_pipeline=should_run,
            note="08:00~19:55는 5분 단위 갱신 구간",
        )

    if hhmm == 2000:
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="final_update",
            board_label="최종 반영",
            should_run_pipeline=True,
            note="20:00는 당일 최종 반영 시점",
        )

    return SessionResult(
        input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        hhmm=hhmm,
        is_weekday=True,
        session_state="final_hold",
        board_label="최종 유지",
        should_run_pipeline=False,
        note="20:00 이후는 최종 데이터 유지",
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


def run_default_samples() -> None:
    samples = [
        "2026-04-17 07:49",
        "2026-04-17 07:50",
        "2026-04-17 07:55",
        "2026-04-17 08:00",
        "2026-04-17 08:05",
        "2026-04-17 19:55",
        "2026-04-17 20:00",
        "2026-04-17 20:05",
    ]

    print("[기본 샘플 테스트 시작]")
    for item in samples:
        dt = parse_input_time(item)
        result = classify_session(dt)
        print_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Top-Sector-KR 시간대 판정 검증")
    parser.add_argument(
        "--time",
        type=str,
        help='예: "2026-04-17 07:55" 또는 "2026-04-17 20:00:00"',
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="현재 KST 시각으로 판정",
    )
    args = parser.parse_args()

    if args.now:
        now_kst = datetime.now(KST)
        result = classify_session(now_kst)
        print_result(result)
        return

    if args.time:
        dt = parse_input_time(args.time)
        result = classify_session(dt)
        print_result(result)
        return

    run_default_samples()


if __name__ == "__main__":
    main()
