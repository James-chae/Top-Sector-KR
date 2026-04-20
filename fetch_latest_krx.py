
# -*- coding: utf-8 -*-
"""
fetch_latest_krx.py

목적
- 네이버 금융 시장합(sise_market_sum) 페이지에서 KOSPI/KOSDAQ 종목 데이터를 수집
- data/latest_krx.json 생성
- 이후 build_market_raw_from_latest_krx.py 가 기대하는 rows 구조 유지
- 구조가 깨졌을 때 빈 파일/샘플 파일로 덮어쓰지 않도록 안전장치 포함

출력 형식
{
  "generated_at": "...",
  "generated_at_kst": "... KST",
  "session_state": "previous_close|reset|preopen_nxt|intraday|closing|final_hold",
  "meta": {...},
  "count": 0000,
  "rows": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "price": 12345,
      "change_value": 120,
      "change_pct": 1.23,
      "volume": 1234567,
      "trading_value_okrw": 1234
    }
  ]
}

주의
- 네이버 HTML 구조가 바뀔 수 있으므로 파서는 복수 fallback 을 사용
- 수집량이 비정상적으로 적으면 파일 저장을 중단하여 기존 latest_krx.json 보호
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "latest_krx.json"
TMP_OUTPUT_PATH = DATA_DIR / "latest_krx.json.tmp"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

URLS = [
    ("KOSPI", "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0"),
    ("KOSDAQ", "https://finance.naver.com/sise/sise_market_sum.naver?sosok=1"),
]

REQUEST_TIMEOUT = 20
REQUEST_SLEEP_SEC = 0.12
MIN_EXPECTED_TOTAL_ROWS = 1200
MIN_EXPECTED_NONZERO_TRADING_ROWS = 300

KST = timezone(timedelta(hours=9))


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


def build_page_url(base_url: str, page: int) -> str:
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    query["page"] = [str(page)]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    # 네이버 금융은 euc-kr / cp949 계열인 경우가 많음
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "ascii"}:
        response.encoding = response.apparent_encoding or "euc-kr"

    text = response.text
    if not text or "finance.naver.com" not in response.url:
        raise RuntimeError(f"unexpected response url={response.url}")

    return text


def apply_field_submit(session: requests.Session, page_url: str) -> None:
    """
    시장합 페이지에 거래량/거래대금 등 컬럼을 노출시키기 위한 요청.
    실패해도 본 수집은 계속 진행.
    """
    parsed = urlparse(page_url)
    return_url = parsed.path + ("?" + parsed.query if parsed.query else "")

    payload = [
        ("menu", "market_sum"),
        ("returnUrl", return_url),
        ("fieldIds", "quant"),            # 거래량
        ("fieldIds", "amount"),           # 거래대금
        ("fieldIds", "market_sum"),       # 시가총액
        ("fieldIds", "foreign_rate"),     # 외국인비율
        ("fieldIds", "roe"),
        ("fieldIds", "per"),
        ("fieldIds", "pbr"),
        ("fieldIds", "listed_stock_cnt"),
    ]

    try:
        session.post(
            "https://finance.naver.com/sise/field_submit.naver",
            headers=HEADERS,
            data=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as exc:
        print(f"[WARN] field_submit failed: {exc}")


def extract_code_map(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    code_map: dict[str, str] = {}

    selectors = [
        "a.tltle",
        "table.type_2 a[href*='item/main.naver?code=']",
        "a[href*='item/main.naver?code=']",
    ]
    for selector in selectors:
        for a in soup.select(selector):
            name = a.get_text(strip=True)
            href = a.get("href", "")
            m = re.search(r"code=(\d{6})", href)
            if name and m:
                code_map[name] = m.group(1)

    return code_map


def extract_last_page(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    max_page = 1
    for a in soup.select("table.Nnavi a, td.pgRR a, .pgRR a, a[href*='page=']"):
        href = a.get("href", "")
        m = re.search(r"[?&]page=(\d+)", href)
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [re.sub(r"\s+", "", clean_text(c)) for c in out.columns]
    return out


def score_table_columns(columns: Iterable[str]) -> int:
    text = " ".join(clean_text(c) for c in columns)
    score = 0
    must_like = ["종목명", "현재가"]
    helpful = ["등락률", "거래량", "거래대금", "시가총액"]
    for x in must_like:
        if x in text:
            score += 5
    for x in helpful:
        if x in text:
            score += 2
    return score


def choose_best_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    best_score = -1
    best_df = pd.DataFrame()
    for raw in tables:
        df = normalize_columns(raw)
        score = score_table_columns(df.columns)
        if score > best_score:
            best_score = score
            best_df = df
    return best_df


def parse_table_from_html(html: str) -> pd.DataFrame:
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        return pd.DataFrame()
    if not tables:
        return pd.DataFrame()

    df = choose_best_table(tables)
    if df.empty:
        return df

    if "종목명" not in df.columns:
        # 그래도 혹시 비슷한 컬럼이 있는지 탐색
        for col in df.columns:
            if "종목명" in clean_text(col):
                df = df.rename(columns={col: "종목명"})
                break

    if "종목명" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["종목명"]).copy()
    df["종목명"] = df["종목명"].map(clean_text)
    df = df[df["종목명"] != ""].copy()
    df = df[df["종목명"] != "종목명"].copy()
    return df.reset_index(drop=True)


def find_column(df: pd.DataFrame, candidates: list[str], required: bool = False) -> Optional[str]:
    cols = list(df.columns)

    for cand in candidates:
        for col in cols:
            if clean_text(col) == cand:
                return col

    for cand in candidates:
        for col in cols:
            if cand in clean_text(col):
                return col

    if required:
        raise RuntimeError(f"required column not found: {candidates} / {cols}")
    return None


def parse_change_value(row: pd.Series, price: int) -> int:
    # 네이버 시장합 페이지는 전일비 컬럼이 따로 존재하는 경우가 많지만,
    # 구조 변경 가능성이 있어 없으면 0으로 둔다.
    diff_col = None
    for cand in ["전일비", "전일비(원)", "대비"]:
        diff_col = diff_col or next((c for c in row.index if cand in clean_text(c)), None)

    if diff_col:
        return to_int(row.get(diff_col, 0), 0)
    return 0


def get_trading_value_okrw(row: pd.Series, columns: Iterable[str]) -> int:
    """
    거래대금이 있으면 우선 사용.
    네이버 시장합 페이지는 흔히 '백만원' 성격이므로 억원 환산 시 /100.
    명확하지 않으면 보수적으로 백만원 기준 우선 처리 후 fallback.
    """
    col = None
    col_name = ""
    for c in columns:
        c_name = clean_text(c)
        if "거래대금" in c_name:
            col = c
            col_name = c_name
            break

    if col is not None:
        raw_value = to_int(row.get(col, 0), 0)

        # 원 단위 표기가 명시되면 1억원으로 환산
        if "원" in col_name and "백만" not in col_name:
            value = int(raw_value / 100000000)
            if value > 0:
                return value

        # 백만원 또는 일반 거래대금으로 보이면 /100
        value = int(raw_value / 100)
        if value > 0:
            return value

    # fallback = 현재가 * 거래량 / 1억
    price = to_int(row.get("현재가", 0), 0)
    volume_col = next((c for c in columns if "거래량" in clean_text(c)), None)
    volume = to_int(row.get(volume_col, 0), 0) if volume_col else 0
    return int((price * volume) / 100000000)


def row_to_payload(
    row: pd.Series,
    code_map: dict[str, str],
    market: str,
    columns: Iterable[str],
) -> Optional[dict]:
    name = clean_text(row.get("종목명", ""))
    if not name:
        return None

    code = normalize_code(code_map.get(name, ""))
    if not code:
        return None

    price_col = find_column(pd.DataFrame(columns=list(columns)), ["현재가"], required=False)  # dummy
    price = to_int(row.get("현재가", 0), 0)
    if price <= 0:
        # 컬럼명이 약간 달라진 경우 fallback
        maybe_price_col = next((c for c in columns if "현재가" in clean_text(c)), None)
        if maybe_price_col:
            price = to_int(row.get(maybe_price_col, 0), 0)

    change_pct_col = next((c for c in columns if "등락률" in clean_text(c)), None)
    volume_col = next((c for c in columns if "거래량" in clean_text(c)), None)

    change_pct = to_float(row.get(change_pct_col, 0.0), 0.0) if change_pct_col else 0.0
    volume = to_int(row.get(volume_col, 0), 0) if volume_col else 0
    trading_value_okrw = get_trading_value_okrw(row, columns)
    change_value = parse_change_value(row, price)

    return {
        "code": code,
        "name": name,
        "market": market,
        "price": price,
        "change_value": change_value,
        "change_pct": change_pct,
        "volume": volume,
        "trading_value_okrw": trading_value_okrw,
    }


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


def fetch_page_rows(
    session: requests.Session,
    page_url: str,
    market: str,
    debug_first_page: bool = False,
) -> tuple[list[dict], str]:
    apply_field_submit(session, page_url)
    html = fetch_html(session, page_url)

    df = parse_table_from_html(html)
    if df.empty:
        return [], html

    code_map = extract_code_map(html)

    if debug_first_page:
        print(f"[DEBUG] {market} columns={list(df.columns)}")

    rows: list[dict] = []
    for _, row in df.iterrows():
        item = row_to_payload(row, code_map, market, df.columns)
        if item is None:
            continue
        rows.append(item)

    return rows, html


def fetch_market_data(session: requests.Session, base_url: str, market: str) -> list[dict]:
    first_url = build_page_url(base_url, 1)
    first_rows, first_html = fetch_page_rows(session, first_url, market, debug_first_page=True)

    last_page = extract_last_page(first_html)
    print(f"[INFO] {market} detected last_page={last_page}")

    all_rows: list[dict] = []
    all_rows.extend(first_rows)

    for page in range(2, last_page + 1):
        page_url = build_page_url(base_url, page)
        try:
            page_rows, _ = fetch_page_rows(session, page_url, market, debug_first_page=False)
            all_rows.extend(page_rows)
        except Exception as exc:
            print(f"[WARN] {market} page={page} fetch failed: {exc}")

        if page == 2 or page % 10 == 0 or page == last_page:
            print(f"[DEBUG] {market} page={page}/{last_page}, accumulated_rows={len(all_rows)}")

        time.sleep(REQUEST_SLEEP_SEC)

    deduped = dedupe_rows(all_rows)
    return deduped


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
            f"row count too small: {total_rows} < {MIN_EXPECTED_TOTAL_ROWS} "
            "(html structure may have changed)"
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
            "source": "naver market sum",
            "min_expected_total_rows": MIN_EXPECTED_TOTAL_ROWS,
            "min_expected_nonzero_trading_rows": MIN_EXPECTED_NONZERO_TRADING_ROWS,
        },
        "count": len(rows),
        "rows": rows,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TMP_OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    TMP_OUTPUT_PATH.replace(OUTPUT_PATH)
    print(f"[OK] saved -> {OUTPUT_PATH}")


def main() -> None:
    session = requests.Session()
    all_rows: list[dict] = []

    for market, url in URLS:
        rows = fetch_market_data(session, url, market)
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
