# -*- coding: utf-8 -*-
"""
build_market_raw_from_latest_krx.py

목적
- data/latest_krx.json + 섹터_마스터.xlsx 결합
- data/market_raw.json 생성
- run_scoring.py / app.js 가 기대하는 rows 구조 제공
- ETF / ETN 제거
- 미매칭 종목, ETF 제거 종목 디버그 출력

사용 위치
- scripts/build_market_raw_from_latest_krx.py 로 두는 것을 권장
- 루트에 두어도 동작하도록 프로젝트 루트 탐색 로직 포함
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


def find_project_root(start: Path) -> Path:
    """
    현재 파일 위치 기준으로 프로젝트 루트를 찾는다.
    기대 구조 예:
    - <root>/data
    - <root>/scripts/build_market_raw_from_latest_krx.py
    """
    candidates = [start, *start.parents]
    for p in candidates:
        if (p / "data").exists():
            return p
    return start.parent


HERE = Path(__file__).resolve()
PROJECT_ROOT = find_project_root(HERE.parent)
DATA_DIR = PROJECT_ROOT / "data"

LATEST_PATH = DATA_DIR / "latest_krx.json"
OUTPUT_PATH = DATA_DIR / "market_raw.json"
EXCEL_PATH = PROJECT_ROOT / "섹터_마스터.xlsx"

# 필요 시 특정 섹터만 추적 가능
TRACKED_SECTORS: Optional[set[str]] = None

ETF_KEYWORDS = [
    "KODEX", "TIGER", "KINDEX", "ARIRANG", "KOSEF", "HANARO", "SMART",
    "SOL", "ACE", "PLUS", "KBSTAR", "KB스타", "ETF", "ETN",
    "레버리지", "인버스", "선물", "채권", "국고채", "스팩", "SPAC",
    "TRUSTON", "RISE",
]


def clean_text(value) -> str:
    if pd.isna(value):
        return ""
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
    if s in {"", "-"}:
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
    if s in {"", "-"}:
        return default
    try:
        return float(s)
    except Exception:
        return default


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    normalized = []
    for col in out.columns:
        c = clean_text(col)
        c = re.sub(r"\s+", "", c)
        normalized.append(c)
    out.columns = normalized
    return out


def pick_column(df: pd.DataFrame, candidates: list[str], required: bool = True) -> Optional[str]:
    cols = list(df.columns)

    # exact 우선
    for cand in candidates:
        for col in cols:
            if cand == col:
                return col

    # 포함 검색 fallback
    for cand in candidates:
        for col in cols:
            if cand.lower() in str(col).lower():
                return col

    if required:
        raise RuntimeError(f"필수 컬럼 없음: candidates={candidates}, columns={cols}")
    return None


def is_etf_or_etn(name: str, sector1: str = "", sector2: str = "") -> bool:
    text = f"{clean_text(name)} {clean_text(sector1)} {clean_text(sector2)}".upper()
    return any(kw.upper() in text for kw in ETF_KEYWORDS)


def load_latest_payload() -> dict:
    if not LATEST_PATH.exists():
        raise FileNotFoundError(f"latest 파일 없음: {LATEST_PATH}")

    payload = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("latest_krx.json 의 rows 가 비어 있음")
    return payload


def load_latest_rows() -> list[dict]:
    payload = load_latest_payload()
    rows = payload["rows"]

    cleaned_rows: list[dict] = []

    for row in rows:
        code = normalize_code(row.get("code", ""))
        name = clean_text(row.get("name", ""))
        market = clean_text(row.get("market", ""))

        if not name:
            continue

        trading_value = row.get("trading_value_okrw", row.get("trading_value", 0))

        cleaned_rows.append(
            {
                "code": code,
                "name": name,
                "market": market,
                "price": to_int(row.get("price", 0)),
                "change_value": to_int(row.get("change_value", row.get("diff", 0))),
                "change_pct": to_float(row.get("change_pct", 0.0)),
                "volume": to_int(row.get("volume", 0)),
                "trading_value_okrw": to_int(trading_value, 0),
            }
        )

    dedup: dict[tuple[str, str, str], dict] = {}
    for row in cleaned_rows:
        key = (row["code"], row["name"], row["market"])
        if key not in dedup:
            dedup[key] = row
        else:
            if row["trading_value_okrw"] > dedup[key]["trading_value_okrw"]:
                dedup[key] = row

    final_rows = list(dedup.values())
    if not final_rows:
        raise RuntimeError("정리 후 latest rows 가 비어 있음")

    return final_rows


def load_sector_master() -> pd.DataFrame:
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"엑셀 파일 없음: {EXCEL_PATH}")

    xls = pd.ExcelFile(EXCEL_PATH)
    df = pd.read_excel(EXCEL_PATH, sheet_name=xls.sheet_names[0], dtype=str)
    df = normalize_columns(df)

    code_col = pick_column(df, ["종목코드", "코드", "ticker"])
    name_col = pick_column(df, ["종목명", "이름", "name"], required=False)
    sector1_col = pick_column(df, ["sector1", "섹터1", "대분류", "섹터"])
    sector2_col = pick_column(df, ["sector2", "섹터2", "중분류"], required=False)
    market_col = pick_column(df, ["market", "시장"], required=False)
    etf_col = pick_column(df, ["etf", "ETF"], required=False)

    out = pd.DataFrame(
        {
            "code": df[code_col].map(normalize_code),
            "name_master": df[name_col].map(clean_text) if name_col else "",
            "sector1": df[sector1_col].map(clean_text),
            "sector2": df[sector2_col].map(clean_text) if sector2_col else "",
            "market_master": df[market_col].map(clean_text) if market_col else "",
            "etf_flag_raw": df[etf_col].map(clean_text) if etf_col else "",
        }
    )

    out = out[out["code"] != ""].copy()

    def parse_etf_flag(v: str) -> bool:
        s = clean_text(v).lower()
        return s in {"1", "true", "y", "yes", "etf"}

    out["etf"] = out["etf_flag_raw"].map(parse_etf_flag)
    out = out.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)

    if out.empty:
        raise RuntimeError("섹터_마스터.xlsx 에서 유효한 종목코드를 읽지 못함")

    return out


def build_market_raw() -> dict:
    latest_payload = load_latest_payload()
    latest_rows = load_latest_rows()
    sector_df = load_sector_master()

    latest_df = pd.DataFrame(latest_rows)
    if latest_df.empty:
        raise RuntimeError("latest rows 없음")

    merged = latest_df.merge(
        sector_df[["code", "name_master", "sector1", "sector2", "market_master", "etf"]],
        on="code",
        how="left",
        validate="m:1",
    )

    merged["sector1"] = merged["sector1"].fillna("").map(clean_text)
    merged["sector2"] = merged["sector2"].fillna("").map(clean_text)
    merged["name_master"] = merged["name_master"].fillna("").map(clean_text)
    merged["market_master"] = merged["market_master"].fillna("").map(clean_text)
    merged["etf"] = merged["etf"].fillna(False).astype(bool)

    merged["is_matched"] = merged["sector1"].ne("")
    merged["is_etf_name"] = merged.apply(
        lambda r: is_etf_or_etn(r["name"], r["sector1"], r["sector2"]),
        axis=1,
    )
    merged["is_etf_filtered"] = merged["etf"] | merged["is_etf_name"]

    tracked_sectors = TRACKED_SECTORS or set(
        s for s in merged["sector1"].dropna().map(clean_text).tolist() if s
    )

    merged["is_other_sector"] = merged["sector1"].apply(
        lambda x: clean_text(x) != "" and clean_text(x) not in tracked_sectors
    )

    unmatched_df = merged[(~merged["is_matched"]) & (~merged["is_etf_filtered"])].copy()
    filtered_etf_df = merged[merged["is_etf_filtered"]].copy()
    ignored_other_df = merged[
        (merged["is_matched"]) &
        (merged["is_other_sector"]) &
        (~merged["is_etf_filtered"])
    ].copy()

    final_df = merged[
        (merged["is_matched"]) &
        (~merged["is_etf_filtered"]) &
        (~merged["is_other_sector"])
    ].copy()

    final_df = final_df.sort_values(
        by=["trading_value_okrw", "change_pct"],
        ascending=[False, False],
    ).reset_index(drop=True)

    rows: list[dict] = []
    for _, row in final_df.iterrows():
        rows.append(
            {
                "code": clean_text(row["code"]),
                "name": clean_text(row["name"]),
                "market": clean_text(row["market"]),
                "price": to_int(row["price"]),
                "change_value": to_int(row["change_value"]),
                "change_pct": to_float(row["change_pct"]),
                "volume": to_int(row["volume"]),
                "trading_value_okrw": to_int(row["trading_value_okrw"]),
                "sector1": clean_text(row["sector1"]),
                "sector2": clean_text(row["sector2"]),
            }
        )

    if not rows:
        raise RuntimeError("market_raw 최종 rows 가 비어 있음. 섹터 매핑 또는 latest 데이터 확인 필요")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_date = datetime.now().strftime("%Y-%m-%d")

    payload = {
        "meta": {
            "trade_date": trade_date,
            "generated_at": generated_at,
            "project_root": str(PROJECT_ROOT),
            "source_latest_file": str(LATEST_PATH),
            "source_sector_file": str(EXCEL_PATH),
            "latest_generated_at": clean_text(latest_payload.get("generated_at", "")),
            "latest_count": int(latest_payload.get("count", len(latest_rows))),
            "latest_session_state": clean_text(
                latest_payload.get("meta", {}).get("session_state", latest_payload.get("session_state", ""))
            ),
        },
        "summary": {
            "latest_row_count": int(len(latest_df)),
            "market_raw_count": int(len(rows)),
            "tracked_sector_count": int(len(tracked_sectors)),
            "unmatched_sector_stock_count": int(len(unmatched_df)),
            "filtered_etf_stock_count": int(len(filtered_etf_df)),
            "ignored_other_sector_stock_count": int(len(ignored_other_df)),
        },
        "rows": rows,
    }

    sector_rows_ex_etf = int(len(sector_df[~sector_df["etf"]]))
    latest_positive_value_rows = int((latest_df["trading_value_okrw"] > 0).sum())

    print(f"[INFO] project_root: {PROJECT_ROOT}")
    print(f"[INFO] sector rows from excel (ETF 제외): {sector_rows_ex_etf}")
    print(f"[INFO] latest stock rows: {len(latest_df)}")
    print(f"[INFO] latest rows with trading_value_okrw > 0: {latest_positive_value_rows}")
    print(f"[INFO] tracked_sector_count: {len(tracked_sectors)}")
    print(f"[INFO] unmatched_sector_stock_count: {len(unmatched_df)}")
    print(f"[INFO] filtered_etf_stock_count: {len(filtered_etf_df)}")
    print(f"[INFO] ignored_other_sector_stock_count: {len(ignored_other_df)}")
    print(f"[INFO] market_raw_count: {len(rows)}")

    def preview(df: pd.DataFrame, title: str, limit: int = 20) -> None:
        print(f"\n[DEBUG] {title}:")
        if df.empty:
            print("  (없음)")
            return
        cols = ["code", "name", "market", "sector1", "sector2", "trading_value_okrw", "change_pct"]
        existing_cols = [c for c in cols if c in df.columns]
        for _, r in df[existing_cols].head(limit).iterrows():
            line = " | ".join(f"{c}={clean_text(r[c])}" for c in existing_cols)
            print(f"  {line}")

    preview(unmatched_df, "unmatched sector stocks")
    preview(ignored_other_df, "ignored other sector stocks")
    preview(filtered_etf_df, "filtered ETF/ETN stocks")

    return payload


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_market_raw()
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[OK] Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
