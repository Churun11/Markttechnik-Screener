#!/usr/bin/env python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import webbrowser, os, sys
from config import *

def get_grosswetterlage():
    try:
        dax = yf.download(MARKET_INDEX, period="60d", interval="1d",
                          progress=False, auto_adjust=True)
        if dax.empty:
            return "neutral", 0
        close = dax["Close"].squeeze()
        ma20  = close.rolling(20).mean()
        current = float(close.iloc[-1])
        ma      = float(ma20.iloc[-1])
        ma_prev = float(ma20.iloc[-5])
        if current > ma and ma > ma_prev:
            return "bullish", current
        elif current < ma and ma < ma_prev:
            return "bearish", current
        else:
            return "neutral", current
    except:
        return "neutral", 0

def get_60min_data(ticker):
    try:
        df = yf.download(ticker, period="30d", interval="60m",
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 20:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

def find_pivots(df, n=PIVOT_LOOKBACK):
    highs, lows = [], []
    hi = df["High"].values
    lo = df["Low"].values
    for i in range(n, len(df) - n):
        window_hi = list(hi[i-n:i]) + list(hi[i+1:i+n+1])
        window_lo = list(lo[i-n:i]) + list(lo[i+1:i+n+1])
        if hi[i] >= max(window_hi):
            highs.append((i, float(hi[i]), df.index[i]))
        if lo[i] <= min(window_lo):
            lows.append((i, float(lo[i]), df.index[i]))
    return highs, lows

def find_p2_p3(highs, lows):
    if not highs or not lows:
        return None, None
    p2 = highs[-1]
    candidates = [l for l in lows if l[0] < p2[0]]
    if not candidates:
        return p2, None
    p3 = candidates[-1]
    return p2, p3

def analyze(ticker, grosswetterlage):
    r = dict(ticker=ticker, name=ticker.replace(".DE",""), signal=False,
             reason="", entry=None, stop=None, ziel=None, crv=None,
             stop_distanz=None, position_stueck=None, position_wert=None,
             p2=None, p3=None)
    if grosswetterlage == "bearish":
        r["reason"] = "Großwetterlage bearish"
        return r
    df = get_60min_data(ticker)
    if df is None:
        r["reason"] = "Keine Daten"
        return r
    highs, lows = find_pivots(df)
    p2, p3 = find_p2_p3(highs, lows)
    if p2 is None:
        r["reason"] = "Kein P2 erkennbar"
        return r
    if p3 is None:
        r["reason"] = "Kein P3 erkennbar"
        return r
    p2_hoch = p2[1]
    p3_tief = p3[1]
    r["p2"] = round(p2_hoch, 2)
    r["p3"] = round(p3_tief, 2)
    try:
        current_close = float(df["Close"].iloc[-1])
    except:
        r["reason"] = "Kurs-Fehler"
        return r
    if current_close <= p2_hoch:
        r["reason"] = f"Kurs {current_close:.2f} nicht über P2 {p2_hoch:.2f}"
        return r
    entry = current_close
    stop  = p3_tief * 0.995
    if stop >= entry:
        r["reason"] = "Stop über Entry"
        return r
    dist = (entry - stop) / entry
    r["stop_distanz"] = round(dist * 100, 1)
    if dist > MAX_STOP_DISTANCE:
        r["reason"] = f"Stop-Distanz {dist*100:.1f}% > {MAX_STOP_DISTANCE*100:.0f}%"
        return r
    risk = entry - stop
    ziel = entry + MIN_CRV * risk
    crv  = (ziel - entry) / risk
    euro_risiko = PORTFOLIO_VALUE * RISK_PER_TRADE
    stueck      = euro_risiko / risk
    wert        = stueck * entry
    r.update(signal=True, reason="✓ Alle Bedingungen erfüllt",
             entry=round(entry,2), stop=round(stop,2), ziel=round(ziel,2),
             crv=round(crv,1), position_stueck=round(stueck,0),
             position_wert=round(wert,0))
    return r

def build_dashboard(results, gw, dax_kurs, scan_time):
    candidates = [r for r in results if r["signal"]]
    rejected   = [r for r in results if not r["signal"]]
    gw_color = {"bullish":"#00C853","bearish":"#D32F2F","neutral":"#FF8F00"}.get(gw,"#888")
    gw_icon  = {"bullish":"↑ BULLISH","bearish":"↓ BEARISH","neutral":"→ NEUTRAL"}.get(gw,"?")
    def crow(r):
        slug = r["name"].lower()
        link = f"https://www.finanzen.net/hebel-produkte/suche?underlying={slug}"
        return f"""<tr>
          <td><strong>{r["name"]}</strong><br><small style="color:#666">{r["ticker"]}</small></td>
          <td class="num">{r["entry"]:.2f}</td>
          <td class="num red">{r["stop"]:.2f}</td>
          <td class="num green">{r["ziel"]:.2f}</td>
          <td class="num">1:{r["crv"]}</td>
          <td class="num">{r["stop_distanz"]}%</td>
          <td class="num">{int(r["position_stueck"])} Stk<br><small style="color:#888">{int(r["position_wert"])} €</small></td>
          <td><a href="{link}" target="_blank">Schein&nbsp;→</a></td></tr>"""
    rows = "".join(crow(r) for r in candidates) if candidates else \
           '<tr><td colspan="8" class="empty">Heute keine Kandidaten.</td></tr>'
    rrows = "".join(
        f'<tr><td>{r["name"]}</td><td colspan="7" class="grey">{r["reason"]}</td></tr>'
        for r in rejected[:25])
    return f"""<!DOCTYPE html><html lang="de"><head>
<meta charset="UTF-8"><meta http-equiv="refresh" content="300">
<title>Markttechnik Screener</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#cdd9e5;padding:28px;min-width:900px}}
h1{{font-size:20px;font-weight:700;margin-bottom:4px}}
.meta{{font-size:12px;color:#6e7681;margin-bottom:20px}}
.badge{{display:inline-block;padding:5px 14px;border-radius:20px;font-size:13px;font-weight:600;border:1px solid {gw_color}55;background:{gw_color}18;color:{gw_color};margin-bottom:24px}}
.stats{{display:flex;gap:40px;margin-bottom:28px}}
.stat .n{{font-size:36px;font-weight:700;color:#58a6ff}}
.stat .l{{font-size:11px;color:#6e7681;margin-top:2px;text-transform:uppercase;letter-spacing:.5px}}
h2{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#6e7681;margin:28px 0 10px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 10px;border-bottom:2px solid #21262d;color:#6e7681;font-weight:500;font-size:11px;text-transform:uppercase}}
td{{padding:11px 10px;border-bottom:1px solid #161b22;vertical-align:middle}}
tr:hover td{{background:#161b22}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.red{{color:#f85149}}.green{{color:#3fb950}}.grey{{color:#6e7681;font-size:12px}}
.empty{{text-align:center;padding:24px;color:#6e7681}}
a{{color:#58a6ff;text-decoration:none}}a:hover{{text-decoration:underline}}
</style></head><body>
<h1>📊 Markttechnik Screener</h1>
<div class="meta">Scan: {scan_time} · {len(results)} Werte · Auto-Refresh 5 min</div>
<div class="badge">{gw_icon} &nbsp;·&nbsp; DAX {dax_kurs:,.0f}</div>
<div class="stats">
  <div class="stat"><div class="n">{len(candidates)}</div><div class="l">Kandidaten</div></div>
  <div class="stat"><div class="n" style="color:#6e7681">{len(rejected)}</div><div class="l">Gefiltert</div></div>
  <div class="stat"><div class="n" style="color:#6e7681">{PORTFOLIO_VALUE:,} €</div><div class="l">Portfolio</div></div>
</div>
<h2>🟢 Kandidaten</h2>
<table><thead><tr>
  <th>Wert</th><th style="text-align:right">Entry</th><th style="text-align:right">Stop</th>
  <th style="text-align:right">Ziel</th><th style="text-align:right">CRV</th>
  <th style="text-align:right">Dist.</th><th style="text-align:right">Position</th><th>Schein</th>
</tr></thead><tbody>{rows}</tbody></table>
<h2>⬜ Gefiltert</h2>
<table><thead><tr><th>Wert</th><th colspan="7">Grund</th></tr></thead>
<tbody>{rrows}</tbody></table>
</body></html>"""

def main():
    print("\n🔍  Markttechnik Screener")
    print(f"    Portfolio {PORTFOLIO_VALUE:,} € · Risiko {RISK_PER_TRADE*100:.0f}% · Max Stop {MAX_STOP_DISTANCE*100:.0f}% · CRV ≥ 1:{MIN_CRV:.0f}\n")
    print("📊  Großwetterlage …")
    gw, dax_kurs = get_grosswetterlage()
    print(f"    DAX {dax_kurs:,.0f}  →  {gw.upper()}\n")
    results = []
    total = len(ALL_TICKERS)
    for i, ticker in enumerate(ALL_TICKERS, 1):
        sys.stdout.write(f"    [{i:>3}/{total}] {ticker:<12}\r")
        sys.stdout.flush()
        results.append(analyze(ticker, gw))
    print()
    candidates = [r for r in results if r["signal"]]
    print(f"\n✅  {len(candidates)} Kandidat(en):\n")
    for c in candidates:
        print(f"    {c['name']:<8}  Entry {c['entry']:>8.2f}  Stop {c['stop']:>8.2f}  Ziel {c['ziel']:>8.2f}  CRV 1:{c['crv']}  Dist {c['stop_distanz']}%")
    scan_time = datetime.now().strftime("%d.%m.%Y  %H:%M")
    html = build_dashboard(results, gw, dax_kurs, scan_time)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n🌐  Dashboard: {path}\n")
    webbrowser.open(f"file://{path}")

if __name__ == "__main__":
    main()
