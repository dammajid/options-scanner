#!/usr/bin/env python3
import os
import sys
import time
import requests
import datetime as dt
from typing import List, Dict, Any, Optional

# 🔑 API Key Polygon.io
API_KEY = "4iAMfpPiaKbINLZkKFc1xTkzGFLP2QoH"
POLYGON_BASE = "https://api.polygon.io"

HEADERS = {
    "Accept": "application/json"
}

# Filter constants
PRICE_MIN = 5.0
PRICE_MAX = 175.0
OI_MIN = 175
DTE_MIN = 1
DTE_MAX = 60


# === API Helpers ===
def _get(url, params=None):
    if params is None:
        params = {}
    params["apiKey"] = API_KEY
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()

def get_underlying_quote(symbol: str):
    try:
        # previous close (OHLC + volume) → ini yang tersedia di free plan
        url_prev = f"{POLYGON_BASE}/v2/aggs/ticker/{symbol}/prev?apiKey={API_KEY}"
        prev_data = _get(url_prev)
        day_data = prev_data.get("results", [{}])[0] if prev_data.get("results") else {}

        return {
            "price":  day_data.get("c"),  # pakai close harga terakhir hari itu
            "open":   day_data.get("o"),
            "high":   day_data.get("h"),
            "low":    day_data.get("l"),
            "close":  day_data.get("c"),
            "volume": day_data.get("v"),
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return {}
        
def get_expirations(symbol: str) -> List[str]:
    """Ambil semua tanggal kedaluwarsa option untuk suatu symbol"""
    url = f"{POLYGON_BASE}/v3/reference/options/contracts"
    data = _get(url, params={"underlying_ticker": symbol, "limit": 1000})
    
    expirations = []
    for result in data.get("results", []):
        if "expiration_date" in result:
            expirations.append(result["expiration_date"])
    
    # Hapus duplikat & urutkan
    expirations = sorted(list(set(expirations)))
    return expirations


def get_chain(symbol: str, expiration: str, opt_type: str) -> List[Dict[str, Any]]:
    """
    Ambil option chain (CALL / PUT) dari Polygon.io
    opt_type: "call" atau "put"
    """
    url = f"{POLYGON_BASE}/v3/snapshot/options/{symbol}"
    data = _get(url, params={"expiration_date": expiration})

    results = []
    for opt in data.get("results", []):
        details = opt.get("details", {})
        last_quote = opt.get("last_quote", {})
        day_info = opt.get("day", {})

        contract_type = details.get("contract_type", "").lower()
        if contract_type == opt_type.lower():
            results.append({
                "symbol": details.get("ticker", ""),
                "strike": details.get("strike_price", 0),
                "expiration": details.get("expiration_date", ""),
                "option_type": contract_type,  # lebih konsisten lowercase
                "bid": last_quote.get("bid", 0),
                "ask": last_quote.get("ask", 0),
                "last": last_quote.get("last", last_quote.get("midpoint", 0)),  # fallback
                "open_interest": opt.get("open_interest", 0),
                "volume": day_info.get("volume", 0)
            })

    return results

# === Utilities ===
def dte_from_str(expiration: str, today: dt.date) -> int:
    y, m, d = map(int, expiration.split("-"))
    return (dt.date(y, m, d) - today).days


def mark_price(opt: Dict[str, Any]) -> Optional[float]:
    try:
        bid = float(opt.get("bid", 0) or 0)
        ask = float(opt.get("ask", 0) or 0)
        if bid == 0 and ask == 0:
            return None
        return (bid + ask) / 2.0
    except:
        return None


def pick_atm_for_expiry(options: List[Dict[str, Any]], underlying_last: float):
    calls = [o for o in options if o.get("type") == "call"]
    puts = [o for o in options if o.get("type") == "put"]

    def nearest(cands):
        if not cands:
            return None
        return min(cands, key=lambda o: abs(float(o.get("strike", 0)) - underlying_last))

    return nearest(calls), nearest(puts)


def passes_filters(opt: Dict[str, Any], dte: int) -> bool:
    try:
        oi = int(opt.get("open_interest", 0))
    except:
        return False
    if oi < OI_MIN or not (DTE_MIN <= dte <= DTE_MAX):
        return False
    return mark_price(opt) not in (None, 0.0)

# === Scanner ===
def scan_symbol(symbol: str, side: str = "both") -> List[Dict[str, Any]]:
    out = []
    today = dt.date.today()

    q = get_underlying_quote(symbol)
    if not q:
        return out

    underlying_last = float(q.get("last", q.get("close", 0)) or 0)
    if not (PRICE_MIN <= underlying_last <= PRICE_MAX):
        return out

    for exp in get_expirations(symbol):
        try:
            dte = dte_from_str(exp, today)
        except:
            continue
        if not (DTE_MIN <= dte <= DTE_MAX):
            continue

        chain = get_chain(symbol, exp)
        call_opt, put_opt = pick_atm_for_expiry(chain, underlying_last)

        for opt in (call_opt, put_opt):
            if not opt:
                continue
            if side == "call" and opt.get("option_type") != "call":
                continue
            if side == "put" and opt.get("option_type") != "put":
                continue
            if not passes_filters(opt, dte):
                continue

            out.append({
                "symbol": symbol,
                "underlying_last": round(underlying_last, 2),
                "expiration": exp,
                "dte": dte,
                "type": opt.get("option_type"),
                "strike": float(opt.get("strike")),
                "oi": int(opt.get("open_interest", 0)),
                "bid": float(opt.get("bid", 0) or 0),
                "ask": float(opt.get("ask", 0) or 0),
                "mark": round(mark_price(opt), 3),
                "option_symbol": opt.get("symbol"),
            })
    return out

# ===  Run Example ===
if __name__ == "__main__":
    symbols = ["AAPL", "MSFT", "SPY"]  # ganti sesuai kebutuhan
    results = []
    for s in symbols:
        rows = scan_symbol(s, side="both")
        results.extend(rows)

    # Sort debit (termurah dulu)
    results = sorted(results, key=lambda r: r["mark"])

    # Print table
    if not results:
        print("No matches found.")
    else:
        for r in results[:20]:  # tampilkan max 20 hasil
            print(r)
