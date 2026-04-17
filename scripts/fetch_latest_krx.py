# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "latest_krx.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.naver.com/",
}

URLS = [
    ("KOSPI", "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0"),
    ("KOSDAQ", "https://finance.naver.com/sise/sise_market_sum.naver?sosok=1"),
]

REQUEST_SLEEP_SEC = 0.12
REQUEST_TIMEOUT = 15
KST = timezone(timedelta(hours=9))


def get_kst_now() -> datetime:
    return datetime.now(KST)


def infer_kr_session_state(now: datetime | None = None) -> str:
    now = now or get_kst_now()
    hhmm = now.hour * 100 + now.minute

    if hhmm < 750:
        return "previous_close"
    if hhmm < 800:
        return "reset"
    if hhmm < 2000:
        return "live_update_window"
    return "final_hold"


def clean(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def to_int(value) -> int:
    s = clean(value).replace(",", "").replace("+", "").replace("%", "")
    if s in {"", "-"}:
        return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def to_float(value) -> float:
    s = clean(value).replace(",", "").replace("+", "").replace("%", "")
    if s in {"", "-"}:
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def build_page_url(base_url: str, page: int) -> str:
    parsed = urlparse(base_url)
    q = parse_qs(parsed.query)
    q["page"] = [str(page)]
    new_query = urlencode(q, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = "euc-kr"
    return response.text


def apply_field_submit(session: requests.Session, page_url: str) -> None:
    return_url = urlparse(page_url).path + "?" + urlparse(page_url).query
    payload = [
        ("menu", "market_sum"),
        ("returnUrl", return_url),
        ("fieldIds", "quant"),
        ("fieldIds", "amount"),
        ("fieldIds", "market_sum"),
        ("fieldIds", "foreign_rate"),
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
    except Exception:
        pass


def extract_code_map(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    code_map: dict[str, str] = {}
    for a in soup.select("a.tltle"):
        name = a.get_text(strip=True)
        href = a.get("href", "")
        match = re.search(r"code=(\d{6})", href)
        if match and name:
            code_map[name] = match.group(1)
    return code_map


def extract_last_page(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    max_page = 1
    for a in soup.select("table.Nnavi a"):
        href = a.get("href", "")
        match = re.search(r"[?&]page=(\d+)", href)
        if match:
            max_page = max(max_page, int(match.group(1)))
    return max_page


def parse_table_from_html(html: str) -> pd.DataFrame:
    tables = pd.read_html(StringIO(html))
    if len(tables) < 2:
        return pd.DataFrame()

    df = tables[1].copy()
    if "종목명" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["종목명"]).copy()
    df["종목명"] = df["종목명"].astype(str).str.strip()
    df = df[df["종목명"] != "종목명"].copy()
    return df


def get_trading_value_okrw(row: pd.Series, df_columns) -> int:
    col = None
    for c in df_columns:
        if "거래대금" in str(c).strip():
            col = c
            break

    if col is not None:
        raw_value = to_int(row.get(col, 0))
        col_name = str(col).strip()

        if "백만" in col_name or "백만원" in col_name or col_name == "거래대금":
            value = int(raw_value / 100)
            if value > 0:
                return value

        if "원" in col_name:
            value = int(raw_value / 100000000)
            if value > 0:
                return value

        value = int(raw_value / 100)
        if value > 0:
            return value

    price = to_int(row.get("현재가", 0))
    volume = to_int(row.get("거래량", 0))
    return int((price * volume) / 100000000)


def fetch_page_rows(session: requests.Session, page_url: str, market: str, debug_first_page: bool = False):
    apply_field_submit(session, page_url)
    html = fetch_html(session, page_url)
    df = parse_table_from_html(html)

    if df.empty:
        return [], html

    code_map = extract_code_map(html)
    if debug_first_page:
        print(f"[DEBUG] {market} columns = {list(df.columns)}")

    rows = []
    for _, r in df.iterrows():
        name = clean(r.get("종목명", ""))
        code = code_map.get(name, "")
        if not name or not code:
            continue

        rows.append({
            "code": code,
            "name": name,
            "market": market,
            "price": to_int(r.get("현재가", 0)),
            "change_value": 0,
            "change_pct": to_float(r.get("등락률", 0)),
            "volume": to_int(r.get("거래량", 0)),
            "trading_value_okrw": get_trading_value_okrw(r, df.columns),
        })

    return rows, html


def dedupe_rows(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        code = row.get("code", "")
        if not code:
            continue
        prev = best.get(code)
        if prev is None or row.get("trading_value_okrw", 0) > prev.get("trading_value_okrw", 0):
            best[code] = row
    return list(best.values())


def fetch_market_data(session: requests.Session, base_url: str, market: str) -> list[dict]:
    first_url = build_page_url(base_url, 1)
    first_rows, first_html = fetch_page_rows(session, first_url, market, debug_first_page=True)

    last_page = extract_last_page(first_html)
    print(f"[INFO] {market} detected last_page={last_page}")

    all_rows: list[dict] = []
    all_rows.extend(first_rows)

    for page in range(2, last_page + 1):
        page_url = build_page_url(base_url, page)
        page_rows, _ = fetch_page_rows(session, page_url, market, debug_first_page=False)
        all_rows.extend(page_rows)

        if page == 2 or page % 10 == 0 or page == last_page:
            print(f"[DEBUG] {market} page={page}/{last_page}, accumulated_rows={len(all_rows)}")

        time.sleep(REQUEST_SLEEP_SEC)

    return dedupe_rows(all_rows)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    all_rows: list[dict] = []

    for market, url in URLS:
        rows = fetch_market_data(session, url, market)
        print(f"[INFO] {market} final rows={len(rows)}")
        all_rows.extend(rows)

    all_rows = dedupe_rows(all_rows)
    non_zero_trading = sum(1 for row in all_rows if row.get("trading_value_okrw", 0) > 0)

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
        },
        "count": len(all_rows),
        "rows": all_rows,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DEBUG] total rows={len(all_rows)}")
    print(f"[DEBUG] non_zero trading rows={non_zero_trading}")
    print(f"[OK] latest_krx.json 생성 완료 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
