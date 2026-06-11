# ─── MARKTTECHNIK SCREENER — Konfiguration ───────────────────────────────────

PORTFOLIO_VALUE   = 10_000
RISK_PER_TRADE    = 0.01
MAX_STOP_DISTANCE = 0.05
MIN_CRV           = 2.0
PIVOT_LOOKBACK    = 5
MIN_AVG_VOLUME    = 100_000
MARKET_INDEX      = "^GDAXI"

# ─── Universe ─────────────────────────────────────────────────────────────────

DAX = [
    "ADS.DE", "AIR.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BMW.DE", "BNR.DE",
    "CON.DE", "DB1.DE", "DBK.DE", "DHL.DE", "DTE.DE", "DTG.DE", "EOAN.DE",
    "FRE.DE", "HEI.DE", "HEN3.DE", "HNR1.DE", "IFX.DE", "MBG.DE",
    "MRK.DE", "MTX.DE", "MUV2.DE", "P911.DE", "PAH3.DE", "PUM.DE", "QIA.DE",
    "RHM.DE", "RWE.DE", "SAP.DE", "SHL.DE", "SIE.DE", "SRT3.DE", "SY1.DE",
    "VNA.DE", "VOW3.DE", "ZAL.DE",
]

MDAX = [
    "AFX.DE", "AIXA.DE", "BOSS.DE", "DUE.DE", "EVD.DE", "FME.DE", "GXI.DE",
    "HLAG.DE", "HOT.DE", "JEN.DE", "KGX.DE", "LEG.DE", "NDX1.DE",
    "RRTL.DE", "SDF.DE", "SGL.DE", "TKA.DE", "TUI1.DE", "VBK.DE", "WCH.DE",
    "BC8.DE", "ENR.DE", "GBF.DE", "NEM.DE",
    "8TRA.DE",   # Traton SE
    "RAA.DE",    # Rational AG
    "HAG.DE",    # Hensoldt AG
    "DHER.DE",   # Delivery Hero
]

TECDAX = [
    "AG1.DE", "FIE.DE", "GFT.DE", "IFX.DE", "JEN.DE",
    "KGX.DE", "NDX1.DE", "PSM.DE", "QIA.DE", "SAP.DE", "SHL.DE", "SIE.DE",
    "SRT3.DE", "SY1.DE", "VBK.DE", "WAF.DE", "AIXA.DE",
]

ALL_TICKERS = list(set(DAX + MDAX + TECDAX))
