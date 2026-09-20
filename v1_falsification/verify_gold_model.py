# -*- coding: utf-8 -*-
"""
V1 — Falsification test of a folk gold-pricing model
=====================================================

The hypothesis under test (in Chinese media / retail-investor circles):

  1. Gold never trades below its extraction cost (floor = AISC).
  2. Gold never trades above  U.S. federal debt / total above-ground gold stock.
  3. Cyclical troughs sit at ~80% of that "ceiling".
  4. Interest rates (and rate expectations) compress the price-to-ceiling ratio.

Data sources
------------
- U.S. federal debt      : FRED series GFDEBTN (quarterly, millions of USD)
- Gold price             : World Bank "Pink Sheet" monthly averages, 1960–present
                           (bundled in ../data/CMO-Monthly.xlsx, re-downloaded if missing)
- Above-ground gold stock: anchored to the World Gold Council estimate of
                           ~222,600 t as of mid-2026, back-cast at ~1.7 %/yr,
                           consistent with GFMS/WGC anchors (2013: 171,300 t;
                           2023: 212,582 t; end-2024: 216,265 t).
- Real rates             : FRED series DFII10 (10-year TIPS yield, 2003–present)

Outputs
-------
- gold_model_verification.png : two-panel chart (prices vs bounds; ratio vs real rates)
- ../data/gold_model_data.csv : monthly series used in the tests

License: MIT (see ../LICENSE). Data attribution: see ../NOTICE.
"""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent          # v1_falsification/
ROOT = HERE.parent                               # repository root
DATA = ROOT / "data"

WB_XLSX = DATA / "CMO-Monthly.xlsx"
WB_URL = ("https://thedocs.worldbank.org/en/doc/"
          "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
          "CMO-Historical-Data-Monthly.xlsx")


def fred_csv(series_id: str) -> pd.Series:
    """Download a FRED series as a pandas Series (public CSV endpoint, no API key)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna().set_index("date")[series_id]


# ---------------------------------------------------------------- data loading
# 1. U.S. federal debt (quarterly, millions of USD -> USD)
debt = fred_csv("GFDEBTN") * 1e6
print(f"U.S. debt: {debt.index[0].date()} ~ {debt.index[-1].date()}, "
      f"latest = ${debt.iloc[-1] / 1e12:.2f}T")

# 2. Gold price, monthly averages (World Bank Pink Sheet)
if not WB_XLSX.exists():
    print("World Bank Pink Sheet not found in data/, downloading ...")
    r = requests.get(WB_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    WB_XLSX.write_bytes(r.content)

wb = pd.read_excel(WB_XLSX, sheet_name="Monthly Prices", header=4)
wb = wb.rename(columns={wb.columns[0]: "period"})
wb = wb[wb["period"].astype(str).str.match(r"^\d{4}M\d{2}$")]
wb["date"] = pd.PeriodIndex(
    wb["period"].astype(str).str.replace("M", "-"), freq="M").to_timestamp()
gold = pd.to_numeric(wb["Gold"], errors="coerce")
gold.index = wb["date"].values
gold = gold.dropna().sort_index()
print(f"Gold price (WB): {gold.index[0].date()} ~ {gold.index[-1].date()}, "
      f"latest monthly avg = ${gold.iloc[-1]:,.0f}")

# 3. Above-ground gold stock model (tonnes -> troy ounces)
ANCHOR_TONNES = 222_600.0                 # WGC estimate, mid-2026
ANCHOR_DATE = pd.Timestamp("2026-06-30")
GROWTH = 0.017                             # ~1.7 %/yr long-run stock growth

years_back = (ANCHOR_DATE - gold.index).days / 365.25
stock_t = ANCHOR_TONNES / (1 + GROWTH) ** years_back
stock_oz = stock_t * 32_150.7466

# 4. Ceiling price and ratio
debt_m = debt.reindex(gold.index, method="ffill")
ceiling = debt_m / stock_oz                # USD/oz
ratio = gold / ceiling                     # price as fraction of the "ceiling"

df = pd.DataFrame({"gold": gold, "debt": debt_m, "stock_t": stock_t,
                   "ceiling": ceiling, "ratio": ratio}).dropna()

# ------------------------------------------------------------------- snapshot
AISC_NOW = 1709  # WGC / Metals Focus global median AISC, 2025 (USD/oz)
now = df.iloc[-1]
print("\n===== Current snapshot =====")
print(f"Gold (latest monthly avg): ${now['gold']:,.0f}")
print(f"U.S. debt: ${now['debt'] / 1e12:.2f}T,  stock: {now['stock_t']:,.0f} t "
      f"= {now['stock_t'] * 32150.7466 / 1e9:.2f} bn oz")
print(f"Ceiling = ${now['ceiling']:,.0f}/oz,  80% of ceiling = ${0.8 * now['ceiling']:,.0f}/oz")
print(f"Price / ceiling = {now['ratio'] * 100:.1f}%")
print(f"Price / AISC    = {now['gold'] / AISC_NOW:.2f}x")

# ---------------------------------------------------- Test 1: is the ceiling hard?
print("\n===== Test 1: ceiling violations (price > debt/stock) =====")
viol = df[df["ratio"] > 1]
print(f"Months above ceiling: {len(viol)} / {len(df)}")
if len(viol):
    print(f"  Period: {viol.index[0].date()} ~ {viol.index[-1].date()}")
    print(f"  Peak: {viol['ratio'].max() * 100:.0f}% of ceiling "
          f"at {viol['ratio'].idxmax().date()}")

# ------------------------------------------- Test 2: do troughs sit at ~80%?
print("\n===== Test 2: troughs vs the claimed 80%-of-ceiling =====")
dec = df.groupby(df.index.year // 10 * 10)["ratio"].agg(["min", "median", "max"])
dec.columns = ["min", "median", "max"]
print((dec * 100).round(1).to_string())
print(f"\nFull sample  price/ceiling: min={df['ratio'].min() * 100:.1f}% "
      f"({df['ratio'].idxmin().date()}), median={df['ratio'].median() * 100:.1f}%, "
      f"max={df['ratio'].max() * 100:.1f}%")
for d in ["1976-08", "1985-02", "1999-08", "2015-12"]:
    sel = df.loc[d]
    if len(sel):
        row = sel.iloc[0] if isinstance(sel, pd.DataFrame) else sel
        print(f"  Trough {d}: gold=${row['gold']:,.0f}, ceiling=${row['ceiling']:,.0f}, "
              f"ratio={row['ratio'] * 100:.1f}%  (claim: ~80%)")

# ------------------------------------------------- Test 3: the cost floor
print("\n===== Test 3: extraction-cost floor =====")
low_2000 = df.loc["1999":"2001", "gold"].min()
print(f"1999-2001 lowest monthly avg: ${low_2000:,.0f}/oz vs industry cash cost "
      f"~$200-250 -> price hugged, but did not durably break, the cash floor")
print(f"2026: AISC ~$1,709, gold ~${now['gold']:,.0f} -> {now['gold'] / AISC_NOW:.1f}x, "
      f"floor is not binding today")

# --------------------------------- Test 4: do real rates compress the ratio?
print("\n===== Test 4: real rates vs the ratio =====")
try:
    tips = fred_csv("DFII10").resample("MS").mean()
    sub = df.join(tips.rename("real10"), how="inner").dropna()
    c1 = sub["ratio"].corr(sub["real10"])
    c2 = sub["ratio"].pct_change(12).corr(sub["real10"].diff(12))
    print(f"2003-present: corr(ratio level, 10Y real yield) = {c1:.2f}")
    print(f"              corr(YoY changes)                 = {c2:.2f}")
except Exception as e:
    print("TIPS download failed:", e)
    sub = None

# --------------------------------------------------------------------- chart
try:
    from daimon_runtime import setup_plot
    setup_plot()
except Exception:  # portable fallback with CJK fonts
    import matplotlib
    matplotlib.rcParams["font.sans-serif"] = [
        "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
        "Arial Unicode MS", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False

import matplotlib.pyplot as plt

fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True,
                         gridspec_kw={"height_ratios": [1.15, 1]})

ax = axes[0]
ax.plot(df.index, df["gold"], color="#C8963E", lw=1.6, label="金价 (月均价, $/oz)")
ax.plot(df.index, df["ceiling"], color="#B03A2E", lw=1.2, ls="--",
        label="理论上限 = 美债总额 ÷ 已开采存量")
ax.plot(df.index, df["ceiling"] * 0.8, color="#E59866", lw=1.0, ls=":",
        label="上限的 80% (理论典型低点)")
ax.axhline(AISC_NOW, color="#5D6D7E", lw=1.0, ls="-.",
           label=f"开采成本 AISC ≈ ${AISC_NOW:,} (2025全球中位数)")
ax.set_yscale("log")
ax.set_ylabel("美元/盎司 (对数轴)")
ax.set_title("金价 vs 理论上下限 (1968–2026)", fontsize=13)
ax.legend(loc="upper left", fontsize=9)
ax.grid(alpha=0.3, which="both")

ax2 = axes[1]
ax2.plot(df.index, df["ratio"] * 100, color="#2E4053", lw=1.4,
         label="金价 ÷ 理论上限 (%)")
ax2.axhline(100, color="#B03A2E", lw=1, ls="--")
ax2.axhline(80, color="#E59866", lw=1, ls=":", label="理论声称的典型低点 = 80%")
ax2.axhline(df["ratio"].median() * 100, color="#7D3C98", lw=1, ls="-.",
            label=f"历史中位数 = {df['ratio'].median() * 100:.0f}%")
if sub is not None:
    ax2b = ax2.twinx()
    ax2b.plot(sub.index, sub["real10"], color="#48C9B0", lw=1.0, alpha=0.7,
              label="10Y TIPS 实际利率 (右轴)")
    ax2b.set_ylabel("实际利率 %", color="#48C9B0")
    ax2b.tick_params(axis="y", labelcolor="#48C9B0")
    lines2, labels2 = ax2b.get_legend_handles_labels()
    ax2.legend(lines2 + [plt.Line2D([], [], color="#2E4053"),
                         plt.Line2D([], [], color="#E59866", ls=":"),
                         plt.Line2D([], [], color="#7D3C98", ls="-.")],
               labels2 + ["金价/上限", "80%线", "中位数"],
               fontsize=8, loc="upper right")
else:
    ax2.legend(fontsize=9, loc="upper right")
ax2.set_ylabel("金价占上限 %")
ax2.set_title("比率检验: 理论上界曾被突破 (1980前后), 低点远低于80%", fontsize=12)
ax2.grid(alpha=0.3)

plt.tight_layout()
fig.savefig(HERE / "gold_model_verification.png", bbox_inches="tight", dpi=150)
df.to_csv(DATA / "gold_model_data.csv")
print(f"\nChart : {HERE / 'gold_model_verification.png'}")
print(f"Data  : {DATA / 'gold_model_data.csv'}")
