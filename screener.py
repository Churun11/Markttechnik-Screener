#!/usr/bin/env python3
"""
Markttechnik Screener — Deutsche Märkte
Long und Short nach Voigt-Regelset

Korrekturen gegenüber v1:
  - P1/P2/P3 zeitliche Reihenfolge nach Voigt: P1(Tief) → P2(Hoch) → P3(Tief danach)
  - Kursziel-Formel: P3 + (P2 - P1), P1 ist ein TIEF, nicht ein Hoch
  - 1/3-Regel: bezogen auf Korrekturtiefe P2→P3, nicht auf gesamte Rally
  - PIVOT_LOOKBACK: 5 statt 3 (weniger Rauschen)
  - Stop-Buffer: dynamisch (min 20ct oder 2% der Korrektur)
"""

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
        close   = dax["Close"].squeeze()
        ma20    = close.rolling(20).mean()
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


def get_daily_volume(ticker):
    try:
        df = yf.download(ticker, period="30d", interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty:
            return 0
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df["Volume"].mean())
    except:
        return 0


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


def find_p1_p2_p3_long(highs, lows):
    if not highs or not lows:
        return None, None, None
    for p3 in reversed(lows):
        p2_cands = [h for h in highs if h[0] < p3[0] and h[1] > p3[1]]
        if not p2_cands:
            continue
        p2 = p2_cands[-1]
        p1_cands = [l for l in lows if l[0] < p2[0]]
        if not p1_cands:
            continue
        p1 = p1_cands[-1]
        if p3[1] > p1[1] and p2[1] > p1[1]:
            return p2, p3, p1
    return None, None, None


def find_p1_p2_p3_short(highs, lows):
    if not highs or not lows:
        return None, None, None
    for p3 in reversed(highs):
        p2_cands = [l for l in lows if l[0] < p3[0] and l[1] < p3[1]]
        if not p2_cands:
            continue
        p2 = p2_cands[-1]
        p1_cands = [h for h in highs if h[0] < p2[0]]
        if not p1_cands:
            continue
        p1 = p1_cands[-1]
        if p3[1] < p1[1] and p2[1] < p1[1]:
            return p2, p3, p1
    return None, None, None


def analyze_long(ticker, grosswetterlage):
    r = dict(
        ticker=ticker, name=ticker.replace(".DE", ""), signal=False,
        reason="", entry=None, stop=None, ziel=None, crv=None,
        stop_distanz=None, position_stueck=None, position_wert=None,
        p1=None, p2=None, p3=None, richtung="LONG", warnung=False
    )
    if grosswetterlage == "bearish":
        r["warnung"] = True
    vol = get_daily_volume(ticker)
    if vol < MIN_AVG_VOLUME:
        r["reason"] = f"Volumen zu gering ({int(vol / 1000)}k)"
        return r
    df = get_60min_data(ticker)
    if df is None:
        r["reason"] = "Keine Daten"
        return r
    highs, lows = find_pivots(df)
    p2, p3, p1 = find_p1_p2_p3_long(highs, lows)
    if p2 is None: r["reason"] = "Kein P2 erkennbar"; return r
    if p3 is None: r["reason"] = "Kein P3 erkennbar"; return r
    if p1 is None: r["reason"] = "Kein P1 erkennbar"; return r
    p2_hoch = p2[1]
    p3_tief = p3[1]
    p1_tief = p1[1]
    r["p1"] = round(p1_tief, 2)
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
    korrektur = p2_hoch - p3_tief
    max_entry = p2_hoch + korrektur / 3
    if entry > max_entry:
        r["reason"] = f"1/3-Regel verletzt — Kurs {entry:.2f} > Max {max_entry:.2f}"
        return r
    stop_buffer = max(0.20, korrektur * 0.02)
    stop = p3_tief - stop_buffer
    if stop <= 0 or stop >= entry:
        r["reason"] = "Stop ungültig"
        return r
    dist = (entry - stop) / entry
    r["stop_distanz"] = round(dist * 100, 1)
    if dist > MAX_STOP_DISTANCE:
        r["reason"] = f"Stop-Distanz {dist * 100:.1f}% > {MAX_STOP_DISTANCE * 100:.0f}%"
        return r
    impuls = p2_hoch - p1_tief
    ziel   = p3_tief + impuls
    risk   = entry - stop
    reward = ziel - entry
    if risk <= 0:
        r["reason"] = "Risk ungültig"
        return r
    crv = reward / risk
    if crv < MIN_CRV:
        r["reason"] = f"CRV 1:{crv:.1f} unter Minimum 1:{MIN_CRV:.0f}"
        return r
    euro_risiko = PORTFOLIO_VALUE * RISK_PER_TRADE
    stueck      = euro_risiko / risk
    wert        = stueck * entry
    r.update(
        signal=True, reason="✓ Alle Bedingungen erfüllt",
        entry=round(entry, 2), stop=round(stop, 2), ziel=round(ziel, 2),
        crv=round(crv, 1), position_stueck=round(stueck, 0),
        position_wert=round(wert, 0)
    )
    return r


def analyze_short(ticker, grosswetterlage):
    r = dict(
        ticker=ticker, name=ticker.replace(".DE", ""), signal=False,
        reason="", entry=None, stop=None, ziel=None, crv=None,
        stop_distanz=None, position_stueck=None, position_wert=None,
        p1=None, p2=None, p3=None, richtung="SHORT", warnung=False
    )
    if grosswetterlage == "bullish":
        r["warnung"] = True
    vol = get_daily_volume(ticker)
    if vol < MIN_AVG_VOLUME:
        r["reason"] = f"Volumen zu gering ({int(vol / 1000)}k)"
        return r
    df = get_60min_data(ticker)
    if df is None:
        r["reason"] = "Keine Daten"
        return r
    highs, lows = find_pivots(df)
    p2, p3, p1 = find_p1_p2_p3_short(highs, lows)
    if p2 is None: r["reason"] = "Kein P2 erkennbar"; return r
    if p3 is None: r["reason"] = "Kein P3 erkennbar"; return r
    if p1 is None: r["reason"] = "Kein P1 erkennbar"; return r
    p2_tief = p2[1]
    p3_hoch = p3[1]
    p1_hoch = p1[1]
    r["p1"] = round(p1_hoch, 2)
    r["p2"] = round(p2_tief, 2)
    r["p3"] = round(p3_hoch, 2)
    try:
        current_close = float(df["Close"].iloc[-1])
    except:
        r["reason"] = "Kurs-Fehler"
        return r
    if current_close >= p2_tief:
        r["reason"] = f"Kurs {current_close:.2f} nicht unter P2 {p2_tief:.2f}"
        return r
    entry = current_close
    korrektur = p3_hoch - p2_tief
    min_entry = p2_tief - korrektur / 3
    if entry < min_entry:
        r["reason"] = f"1/3-Regel verletzt — Kurs {entry:.2f} < Min {min_entry:.2f}"
        return r
    stop_buffer = max(0.20, korrektur * 0.02)
    stop = p3_hoch + stop_buffer
    if stop <= entry:
        r["reason"] = "Stop ungültig"
        return r
    dist = (stop - entry) / entry
    r["stop_distanz"] = round(dist * 100, 1)
    if dist > MAX_STOP_DISTANCE:
        r["reason"] = f"Stop-Distanz {dist * 100:.1f}% > {MAX_STOP_DISTANCE * 100:.0f}%"
        return r
    impuls = p1_hoch - p2_tief
    ziel   = p3_hoch - impuls
    risk   = stop - entry
    reward = entry - ziel
    if risk <= 0:
        r["reason"] = "Risk ungültig"
        return r
    crv = reward / risk
    if crv < MIN_CRV:
        r["reason"] = f"CRV 1:{crv:.1f} unter Minimum 1:{MIN_CRV:.0f}"
        return r
    euro_risiko = PORTFOLIO_VALUE * RISK_PER_TRADE
    stueck      = euro_risiko / risk
    wert        = stueck * entry
    r.update(
        signal=True, reason="✓ Alle Bedingungen erfüllt",
        entry=round(entry, 2), stop=round(stop, 2), ziel=round(ziel, 2),
        crv=round(crv, 1), position_stueck=round(stueck, 0),
        position_wert=round(wert, 0)
    )
    return r


def build_dashboard(results, gw, dax_kurs, scan_time, modus):
    candidates = [r for r in results if r["signal"]]
    rejected   = [r for r in results if not r["signal"]]
    is_long  = modus == "long"
    farbe    = "#00C853" if is_long else "#f85149"
    icon     = "↑ LONG" if is_long else "↓ SHORT"
    titel    = "📈 Long-Kandidaten" if is_long else "📉 Short-Kandidaten"
    gw_color = {"bullish": "#00C853", "bearish": "#D32F2F", "neutral": "#FF8F00"}.get(gw, "#888")
    gw_icon  = {"bullish": "↑ BULLISH", "bearish": "↓ BEARISH", "neutral": "→ NEUTRAL"}.get(gw, "?")

    def crow(r):
        slug    = r["name"].lower()
        link    = f"https://www.finanzen.net/hebel-produkte/suche?underlying={slug}"
        sc      = "red" if is_long else "green"
        zc      = "green" if is_long else "red"
        warnung = ('<span style="color:#FF8F00;margin-right:6px" '
                   'title="Gegen Großwetterlage">⚠️</span>') if r.get("warnung") else ""
        return f"""<tr>
          <td>{warnung}<strong>{r["name"]}</strong><br>
              <small style="color:#666">{r["ticker"]}</small></td>
          <td class="num">{r["p1"]}</td>
          <td class="num">{r["p2"]}</td>
          <td class="num">{r["p3"]}</td>
          <td class="num">{r["entry"]:.2f}</td>
          <td class="num {sc}">{r["stop"]:.2f}</td>
          <td class="num {zc}">{r["ziel"]:.2f}</td>
          <td class="num">1:{r["crv"]}</td>
          <td class="num">{r["stop_distanz"]}%</td>
          <td class="num">{int(r["position_stueck"])} Stk<br>
              <small style="color:#888">{int(r["position_wert"])} €</small></td>
          <td><a href="{link}" target="_blank">Schein&nbsp;→</a></td>
        </tr>"""

    rows = ("".join(crow(r) for r in candidates) if candidates else
            f'<tr><td colspan="11" class="empty">Heute keine {modus.upper()}-Kandidaten.</td></tr>')
    rrows = "".join(
        f'<tr><td>{r["name"]}</td>'
        f'<td colspan="10" class="grey">{r["reason"]}</td></tr>'
        for r in rejected[:50]
    )
    warnung_hinweis = ""
    if any(r.get("warnung") for r in candidates):
        warnung_hinweis = (
            '<div style="background:#FF8F0018;border:1px solid #FF8F0055;'
            'border-radius:8px;padding:12px 16px;margin-bottom:20px;'
            'font-size:13px;color:#FF8F00">⚠️ &nbsp;Einige Kandidaten laufen '
            '<strong>gegen die Großwetterlage</strong> — '
            'erhöhte Anforderung an die Struktur.</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="300">
<title>Markttechnik Screener — {modus.upper()}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#0d1117; color:#cdd9e5; padding:28px; min-width:1100px }}
h1   {{ font-size:20px; font-weight:700; margin-bottom:4px }}
.meta {{ font-size:12px; color:#6e7681; margin-bottom:20px }}
.badge {{ display:inline-block; padding:5px 14px; border-radius:20px;
          font-size:13px; font-weight:600;
          border:1px solid {gw_color}55; background:{gw_color}18;
          color:{gw_color}; margin-bottom:12px }}
.modus {{ display:inline-block; margin-left:10px; padding:5px 14px;
          border-radius:20px; font-size:13px; font-weight:600;
          border:1px solid {farbe}55; background:{farbe}18;
          color:{farbe}; margin-bottom:12px }}
.stats {{ display:flex; gap:40px; margin:16px 0 28px }}
.stat .n {{ font-size:36px; font-weight:700; color:#58a6ff }}
.stat .l {{ font-size:11px; color:#6e7681; margin-top:2px;
             text-transform:uppercase; letter-spacing:.5px }}
h2   {{ font-size:11px; text-transform:uppercase; letter-spacing:1px;
         color:#6e7681; margin:28px 0 10px }}
table {{ width:100%; border-collapse:collapse; font-size:13px }}
th   {{ text-align:left; padding:8px 10px; border-bottom:2px solid #21262d;
         color:#6e7681; font-weight:500; font-size:11px; text-transform:uppercase }}
td   {{ padding:11px 10px; border-bottom:1px solid #161b22; vertical-align:middle }}
tr:hover td {{ background:#161b22 }}
.num   {{ text-align:right; font-variant-numeric:tabular-nums }}
.red   {{ color:#f85149 }}
.green {{ color:#3fb950 }}
.grey  {{ color:#6e7681; font-size:12px }}
.empty {{ text-align:center; padding:24px; color:#6e7681 }}
a      {{ color:#58a6ff; text-decoration:none }}
a:hover {{ text-decoration:underline }}
</style>
</head>
<body>
<h1>📊 Markttechnik Screener</h1>
<div class="meta">Scan: {scan_time} · {len(results)} Werte · Auto-Refresh 5 min</div>
<div class="badge">{gw_icon} &nbsp;·&nbsp; DAX {dax_kurs:,.0f}</div>
<div class="modus">{icon}</div>
<div class="stats">
  <div class="stat">
    <div class="n" style="color:{farbe}">{len(candidates)}</div>
    <div class="l">Kandidaten</div>
  </div>
  <div class="stat">
    <div class="n" style="color:#6e7681">{len(rejected)}</div>
    <div class="l">Gefiltert</div>
  </div>
  <div class="stat">
    <div class="n" style="color:#6e7681">{PORTFOLIO_VALUE:,} €</div>
    <div class="l">Portfolio</div>
  </div>
</div>
{warnung_hinweis}
<h2>{titel}</h2>
<table>
  <thead><tr>
    <th>Wert</th>
    <th style="text-align:right">P1</th>
    <th style="text-align:right">P2</th>
    <th style="text-align:right">P3</th>
    <th style="text-align:right">Entry</th>
    <th style="text-align:right">Stop</th>
    <th style="text-align:right">Ziel</th>
    <th style="text-align:right">CRV</th>
    <th style="text-align:right">Dist.</th>
    <th style="text-align:right">Position</th>
    <th>Schein</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
<h2>⬜ Gefiltert</h2>
<table>
  <thead><tr><th>Wert</th><th colspan="10">Grund</th></tr></thead>
  <tbody>{rrows}</tbody>
</table>
</body>
</html>"""


def main():
    modus = "long"
    if len(sys.argv) > 1 and sys.argv[1].lower() in ["--short", "short"]:
        modus = "short"
    print(f"\n🔍  Markttechnik Screener — {modus.upper()}")
    print(f"    Portfolio {PORTFOLIO_VALUE:,} € · Risiko {RISK_PER_TRADE * 100:.0f}% · "
          f"Max Stop {MAX_STOP_DISTANCE * 100:.0f}% · CRV ≥ 1:{MIN_CRV:.0f}\n")
    print("📊  Großwetterlage …")
    gw, dax_kurs = get_grosswetterlage()
    print(f"    DAX {dax_kurs:,.0f}  →  {gw.upper()}\n")
    results    = []
    total      = len(ALL_TICKERS)
    analyze_fn = analyze_long if modus == "long" else analyze_short
    for i, ticker in enumerate(ALL_TICKERS, 1):
        sys.stdout.write(f"    [{i:>3}/{total}] {ticker:<12}\r")
        sys.stdout.flush()
        results.append(analyze_fn(ticker, gw))
    print()
    candidates = [r for r in results if r["signal"]]
    print(f"\n✅  {len(candidates)} {modus.upper()}-Kandidat(en):\n")
    for c in candidates:
        warn = " ⚠️ " if c.get("warnung") else "    "
        print(f"  {warn}{c['name']:<8}  "
              f"P1 {c['p1']:>8}  P2 {c['p2']:>8}  P3 {c['p3']:>8}  "
              f"Entry {c['entry']:>8.2f}  Stop {c['stop']:>8.2f}  "
              f"Ziel {c['ziel']:>8.2f}  CRV 1:{c['crv']}  Dist {c['stop_distanz']}%")
    scan_time = datetime.now().strftime("%d.%m.%Y  %H:%M")
    html      = build_dashboard(results, gw, dax_kurs, scan_time, modus)
    filename  = f"dashboard_{modus}.html"
    path      = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n🌐  Dashboard: {path}\n")
    webbrowser.open(f"file://{path}")


if __name__ == "__main__":
    main()
