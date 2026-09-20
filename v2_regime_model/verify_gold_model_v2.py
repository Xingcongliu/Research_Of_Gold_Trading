# -*- coding: utf-8 -*-
"""
V2 — From hard bounds to a regime-aware valuation gauge
========================================================

V1 (../v1_falsification) showed the folk model's hard ceiling and the fixed
"80% trough" rule are falsified by history. V2 rebuilds the idea into something
usable:

  1. The ratio  price / (U.S. debt / above-ground stock)  is kept — but as a
     *valuation gauge*, not a bound. Extremes are read off a rolling 20-year
     quantile band (P10 / P50 / P90) that drifts with the regime.
  2. The "fair" level of the ratio is modelled with mechanisms instead of a
     fixed percentage:

         log(ratio) = b0 + b1 * (10Y TIPS real yield)
                          + b2 * (post-2022 central-bank-buying regime dummy)

     Estimated on monthly data, 2003–present.
  3. Regime segmentation shows how much the ratio's centre of gravity moves
     across monetary eras (1971-80, 1981-99, 2000-11, 2012-21, 2022-26).

Inputs
------
- ../data/gold_model_data.csv  (produced by v1; a copy is bundled)
- FRED series DFII10 (10-year TIPS yield)

Outputs
-------
- gold_model_v2.png           : ratio with rolling band + model fair value
- ../data/gold_model_data_v2.csv

License: MIT (see ../LICENSE). Data attribution: see ../NOTICE.
"""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent          # v2_regime_model/
ROOT = HERE.parent
DATA = ROOT / "data"

df = pd.read_csv(DATA / "gold_model_data.csv", index_col=0, parse_dates=True)


def fred_csv(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text))
    d.columns = ["date", series_id]
    d["date"] = pd.to_datetime(d["date"])
    d[series_id] = pd.to_numeric(d[series_id], errors="coerce")
    return d.dropna().set_index("date")[series_id]


tips = fred_csv("DFII10").resample("MS").mean()
df = df.join(tips.rename("real10"), how="left")

# ------------------------- 1. rolling 20-year quantile band (regime-adaptive)
lr = np.log(df["ratio"])
roll = lr.rolling(240, min_periods=120)
df["band_p10"] = np.exp(roll.quantile(0.10))
df["band_p50"] = np.exp(roll.quantile(0.50))
df["band_p90"] = np.exp(roll.quantile(0.90))
df["pctile_20y"] = lr.rolling(240, min_periods=120).apply(
    lambda w: (w.iloc[-1] > w).mean(), raw=False)

now = df.dropna(subset=["pctile_20y"]).iloc[-1]
print(f"Current ratio          = {now['ratio'] * 100:.1f}%")
print(f"Percentile in 20Y window = {now['pctile_20y'] * 100:.0f}%")
print(f"20Y band: P10={now['band_p10'] * 100:.0f}%, "
      f"P50={now['band_p50'] * 100:.0f}%, P90={now['band_p90'] * 100:.0f}%")

# --- 2. two-factor fair-value model: real yield + post-2022 CB-buying regime
sub = df.loc["2003":].dropna(subset=["real10"]).copy()
sub["post2022"] = (sub.index >= "2022-03-01").astype(float)
y = np.log(sub["ratio"].values)
X = np.column_stack([np.ones(len(sub)), sub["real10"].values,
                     sub["post2022"].values])
beta, *_ = np.linalg.lstsq(X, y, rcond=None)
pred = X @ beta
resid = y - pred
r2 = 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()
print(f"\nlog(ratio) = {beta[0]:.3f} + ({beta[1]:.3f})*real10 "
      f"+ ({beta[2]:.3f})*post2022")
print(f"R^2 = {r2:.2f}  (real-yield-only R^2 = "
      f"{np.corrcoef(y, sub['real10'])[0, 1] ** 2:.2f})")
print(f"Read: +1pt real yield -> ratio {np.exp(beta[1]) - 1:+.1%}; "
      f"post-2022 regime shift {np.exp(beta[2]) - 1:+.1%}")

cur = sub.iloc[-1]
fair = np.exp(beta[0] + beta[1] * cur["real10"] + beta[2] * cur["post2022"])
print(f"\nNow: real yield = {cur['real10']:.2f}%, model fair ratio = {fair * 100:.0f}%, "
      f"actual = {cur['ratio'] * 100:.1f}%")
print(f"Deviation = {(cur['ratio'] / fair - 1):+.1%}, "
      f"residual percentile = {(resid < resid[-1]).mean():.0%}")
print(f"Implied model price ~ ${fair * cur['ceiling']:,.0f}/oz "
      f"(actual ${cur['gold']:,.0f})")
df.loc[sub.index, "model_ratio"] = np.exp(pred)

# ------------------------------------------------ 3. regime segmentation
print("\n===== Ratio median by monetary regime =====")
for name, (a, b) in [("1971-80 depegging + stagflation", ("1971", "1980")),
                     ("1981-99 Volcker strong dollar", ("1981", "1999")),
                     ("2000-11 weak dollar + QE", ("2000", "2011")),
                     ("2012-21 new normal", ("2012", "2021")),
                     ("2022-26 CB buying wave", ("2022", "2026"))]:
    s = df.loc[a:b, "ratio"]
    if len(s):
        print(f"  {name}: median {s.median() * 100:.0f}%, "
              f"range {s.min() * 100:.0f}%-{s.max() * 100:.0f}%")

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

fig, ax = plt.subplots(figsize=(12, 6.5))
ax.plot(df.index, df["ratio"] * 100, color="#2E4053", lw=1.3,
        label="金价 ÷ (美债/存量) 比率")
ax.plot(df.index, df["band_p10"] * 100, color="#5D6D7E", lw=1, ls="--",
        alpha=0.8, label="滚动20年 P10 / P90 带")
ax.plot(df.index, df["band_p90"] * 100, color="#5D6D7E", lw=1, ls="--",
        alpha=0.8)
ax.plot(df.index, df["band_p50"] * 100, color="#7D3C98", lw=1.2, ls="-.",
        label="滚动20年中位数 (动态锚)")
ax.plot(df.index, df["model_ratio"] * 100, color="#C0392B", lw=1.4,
        label="两因子模型公允比率 (实际利率+regime)")
ax.fill_between(df.index, df["band_p10"] * 100, df["band_p90"] * 100,
                color="#5D6D7E", alpha=0.08)
for d in ["1980-01-21", "1999-08-01", "2011-09-01", "2022-03-01"]:
    ax.axvline(pd.Timestamp(d), color="#B03A2E", lw=0.7, alpha=0.4)
ax.set_yscale("log")
ax.set_yticks([20, 30, 50, 80, 120, 200])
ax.set_yticklabels(["20%", "30%", "50%", "80%", "120%", "200%"])
ax.set_ylabel("比率 (对数轴)")
ax.set_title("改进版: 比率作为估值指标 — 滚动分位带 + 机制模型, 替代固定上下限",
             fontsize=13)
ax.legend(fontsize=9, loc="lower left")
ax.grid(alpha=0.3, which="both")

plt.tight_layout()
fig.savefig(HERE / "gold_model_v2.png", bbox_inches="tight", dpi=150)
df.to_csv(DATA / "gold_model_data_v2.csv")
print(f"\nChart : {HERE / 'gold_model_v2.png'}")
print(f"Data  : {DATA / 'gold_model_data_v2.csv'}")
