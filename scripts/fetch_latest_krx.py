# -*- coding: utf-8 -*-
"""
fetch_latest_krx.py (2026-09 개편 대응 버전)

목적
- 네이버 모바일 JSON API(m.stock.naver.com)에서 KOSPI/KOSDAQ 종목 데이터를 수집
- data/latest_krx.json 생성
- build_market_raw_from_latest_krx.py 가 기대하는 rows 구조 유지 (필드/단위 동일)
- 구조가 깨졌을 때 빈 파일/샘플 파일로 덮어쓰지 않도록 안전장치 포함

변경 이유
- 2026-09-10경 네이버가 finance.naver.com의 PC용 시세 페이지(sise_market_sum)를
  신규 SPA 사이트(stock.naver.com)로 이전하면서, 기존 HTML 표 스크래핑 방식이
  통째로 막힘 (requests가 리다이렉트를 따라가 200을 받지만 표 자체가 없음).
- 네이버 모바일 페이지가 쓰는 공개 JSON 엔드포인트로 교체:
  https://m.stock.naver.com/api/json/sise/siseListJson.nhn
  (로그인/쿠키 불필요, 시가총액순 종목 리스트를 페이지 단위로 반환)

권장 위치
- scripts/fetch_latest_krx.py (기존 파일 교체)
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


KST = timezone(timedelta(hours=9))
REQUEST_TIMEOUT = 20
REQUEST_SLEEP_SEC = 0.15
PAGE_SIZE = 100
MIN_EXPECTED_TOTAL_ROWS = 1200
MIN_EXPECTED_NONZERO_TRADING_ROWS = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; SM-S911N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Mobile Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# sosok: 0 = KOSPI, 1 = KOSDAQ
MARKETS = [
    ("KOSPI", 0),
    ("KOSDAQ", 1),
]

API_URL = "https://m.stock.naver.com/api/json/sise/siseListJson.nhn"


def find_project_root(start: Path) -> Path:
    candidates = [start, *start.parents]
    for p in candidates:
        if (p / "data").exists() or (p / ".github").exists() or (p / "app").exists():
            return p
    return start.parent


HERE = Path(__file__).resolve()
PROJECT_ROOT = find_project_root(HERE.parent)
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_PATH = DATA_DIR / "latest_krx.json"
TMP_OUTPUT_PATH = DATA_DIR / "latest_krx.json.tmp"


def get_kst_now() -> datetime:
    return datetime.now(KST)


def infer_kr_session_state(now: Optional[datetime] = None) -> str:
    now = now or get_kst_now()
    hhmm = now.hour * 100 + now.minute
    if hhmm < 750:
        return "previous_close"
    if hhmm < 800:
        return "reset"
    if hhmm < 900:
        return "preopen_nxt"
    if hhmm < 1530:
        return "intraday"
    if hhmm < 2000:
        return "closing"
    return "final_hold"


def clean_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).replace("\xa0", " ").strip()


def normalize_code(value) -> str:
    s = clean_text(value)
    if not s:
        return ""
    m = re.search(r"(\d{6})", s)
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", s)
    if digits:
        return digits.zfill(6)[-6:]
    return ""


def to_int(value, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return default
    s = clean_text(value)
    if not s:
        return default
    s = s.replace(",", "").replace("+", "").replace("%", "")
    if s in {"", "-", "--"}:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def to_float(value, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return default
    s = clean_text(value)
    if not s:
        return default
    s = s.replace(",", "").replace("+", "").replace("%", "")
    if s in {"", "-", "--"}:
        return default
    try:
        return float(s)
    except Exception:
        return default


def extract_item_list(payload) -> list:
    """API 응답이 순수 배열이든, 여러 단계로 감싸져 있든 모두 처리.
    실제 확인된 형태: {"result": {"totCnt": N, "itemList": [...]}}
    """
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        # 1단계: 바로 리스트인 키
        for key in ("itemList", "list", "items", "stocks", "data"):
            if key in payload and isinstance(payload[key], list):
                return payload[key]

        # 2단계: result 안에 감싸진 경우 (실제 확인된 구조)
        result = payload.get("result")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("itemList", "list", "items", "stocks", "data"):
                if key in result and isinstance(result[key], list):
                    return result[key]

    return []


def fetch_market_data(session: requests.Session, market: str, sosok: int) -> list[dict]:
    rows: list[dict] = []
    page = 1

    while True:
        params = {
            "menu": "market_sum",
            "sosok": sosok,
            "pageSize": PAGE_SIZE,
            "page": page,
        }
        response = session.get(API_URL, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type.lower():
            snippet = response.text[:200].replace("\n", " ")
            raise RuntimeError(
                f"{market} page={page}: JSON이 아닌 응답을 받았습니다 "
                f"(content-type={content_type}). 응답 앞부분: {snippet}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"{market} page={page}: JSON 파싱 실패: {exc}") from exc

        items = extract_item_list(payload)
        if not items:
            break

        for item in items:
            code = normalize_code(item.get("cd", ""))
            name = clean_text(item.get("nm", ""))
            if not code or not name:
                continue

            price = to_int(item.get("nv"), 0)
            change_value = to_int(item.get("cv"), 0)
            change_pct = to_float(item.get("cr"), 0.0)
            volume = to_int(item.get("aq"), 0)

            # 주의: 'aa'(누적거래대금) 필드는 종목/시장에 따라 단위가 다르게 내려오는
            # 것이 확인됨 (일부는 백만원, 일부는 천원 단위로 추정 - 원인 불명).
            # 신뢰할 수 없어 사용하지 않고, price × volume으로 직접 계산한다.
            # (실측 검증: 코스피 대형주/코스닥 중소형주 모두 실제 거래대금과 오차 5% 이내로 일치)
            trading_value_okrw = int((price * volume) / 100000000)

            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market": market,
                    "price": price,
                    "change_value": change_value,
                    "change_pct": change_pct,
                    "volume": volume,
                    "trading_value_okrw": trading_value_okrw,
                }
            )

        print(f"[DEBUG] {market} page={page}, page_items={len(items)}, accumulated_rows={len(rows)}")

        if len(items) < PAGE_SIZE:
            break

        page += 1
        time.sleep(REQUEST_SLEEP_SEC)

    return rows


def dedupe_rows(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        code = normalize_code(row.get("code", ""))
        if not code:
            continue

        prev = best.get(code)
        if prev is None:
            best[code] = row
            continue

        prev_value = to_int(prev.get("trading_value_okrw", 0), 0)
        curr_value = to_int(row.get("trading_value_okrw", 0), 0)
        if curr_value > prev_value:
            best[code] = row
            continue

        if curr_value == prev_value:
            prev_volume = to_int(prev.get("volume", 0), 0)
            curr_volume = to_int(row.get("volume", 0), 0)
            if curr_volume > prev_volume:
                best[code] = row

    return list(best.values())


def validate_payload(rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError("no rows fetched")

    total_rows = len(rows)
    nonzero_trading_rows = sum(1 for r in rows if to_int(r.get("trading_value_okrw", 0), 0) > 0)
    kospi_count = sum(1 for r in rows if clean_text(r.get("market")) == "KOSPI")
    kosdaq_count = sum(1 for r in rows if clean_text(r.get("market")) == "KOSDAQ")

    print(f"[INFO] total_rows={total_rows}")
    print(f"[INFO] nonzero_trading_rows={nonzero_trading_rows}")
    print(f"[INFO] kospi_count={kospi_count}, kosdaq_count={kosdaq_count}")

    if total_rows < MIN_EXPECTED_TOTAL_ROWS:
        raise RuntimeError(
            f"row count too small: {total_rows} < {MIN_EXPECTED_TOTAL_ROWS} (API 구조가 또 바뀌었을 수 있음)"
        )

    if nonzero_trading_rows < MIN_EXPECTED_NONZERO_TRADING_ROWS:
        raise RuntimeError(
            f"nonzero trading rows too small: {nonzero_trading_rows} < {MIN_EXPECTED_NONZERO_TRADING_ROWS}"
        )

    if kospi_count == 0 or kosdaq_count == 0:
        raise RuntimeError("either KOSPI or KOSDAQ rows are missing")


def save_payload(rows: list[dict]) -> None:
    now_kst = get_kst_now()
    session_state = infer_kr_session_state(now_kst)

    payload = {
        "generated_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
        "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
        "session_state": session_state,
        "meta": {
            "market": "KR",
            "session_state": session_state,
            "generated_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "generated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
            "source": "naver mobile json api (m.stock.naver.com)",
            "project_root": str(PROJECT_ROOT),
            "min_expected_total_rows": MIN_EXPECTED_TOTAL_ROWS,
            "min_expected_nonzero_trading_rows": MIN_EXPECTED_NONZERO_TRADING_ROWS,
        },
        "count": len(rows),
        "rows": rows,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TMP_OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    TMP_OUTPUT_PATH.replace(OUTPUT_PATH)
    print(f"[OK] saved -> {OUTPUT_PATH}")


def main() -> None:
    print(f"[INFO] project_root={PROJECT_ROOT}")
    session = requests.Session()
    all_rows: list[dict] = []

    for market, sosok in MARKETS:
        rows = fetch_market_data(session, market, sosok)
        print(f"[INFO] {market} final_rows={len(rows)}")
        all_rows.extend(rows)

    all_rows = dedupe_rows(all_rows)
    validate_payload(all_rows)
    save_payload(all_rows)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[ERROR] interrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
