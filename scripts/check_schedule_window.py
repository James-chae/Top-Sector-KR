# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
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
            should_run_pipeline=True,
            note="07:50~07:59는 reset 구간",
        )

    if hhmm <= 2003:
        # 2026-09-17 버그 수정: 예전에는 "현재 분(minute)이 정확히
        # 5의 배수+3일 때만"(예: 08:03, 08:08...) 실행하도록
        # 했었는데, GitHub Actions의 cron 트리거는 실제로는 몇 분씩
        # 밀려서 실행되는 경우가 흔해서(예: :23분 예약이 :27분에
        # 실행), 그때마다 "분이 안 맞는다"며 파이프라인 실행 자체를
        # 건너뛰는 조용한 버그가 있었다.
        # -> 크론 스케줄 자체가 이미 5분 간격으로 트리거하므로,
        #    이 스크립트에서는 시간대 범위 안인지만 확인하고
        #    분 단위 정확도는 더 이상 요구하지 않는다.
        return SessionResult(
            input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            hhmm=hhmm,
            is_weekday=True,
            session_state="live_update_window",
            board_label="장중/주간 갱신",
            should_run_pipeline=True,
            note="08:00~20:03는 언제든 실행 가능 (분 단위 정확도 요구 제거, 2026-09-17)",
        )

    return SessionResult(
        input_time=dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        hhmm=hhmm,
        is_weekday=True,
        session_state="final_hold",
        board_label="최종 유지",
        should_run_pipeline=False,
        note="20:03 이후는 최종 데이터 유지",
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
        "2026-04-21 19:58",
        "2026-04-21 20:03",
        "2026-04-21 20:05",
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
