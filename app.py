# -*- coding: utf-8 -*-
"""
HIZLI ON — 20 SAYI AKIŞ LABORATUVARI V2

Amaç:
- GitHub/yerel veri.txt içindeki 36 günlük çekiliş havuzunu otomatik tanır.
- Her çekilişte çıkan GERÇEK 20 sayıyı, o sonuç görülmeden hemen ÖNCEKİ durumuyla izler.
- Gün içi durum, son durum, sıcak/soğuk, yön ve geçişleri raporlar.
- 00:02'den gün sonuna kadar her çekilişin 20 sayısını özetler.
- Walk-forward test ile modelin kupon sıralamasını geleceği görmeden sınar.
- Veri havuzunun sonuna göre bir sonraki çekiliş için 80 sayıyı sıralar ve farklı profilde 10'lu kolonlar üretir.

Önemli:
- Geçmiş örüntüler gelecek çekilişi garanti etmez.
- "Sıcak/soğuk" burada yalnızca geçmiş frekansın tanımıdır; "çıkması gerekir" anlamına gelmez.
"""
from __future__ import annotations

import math
import re
import urllib.request
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On — 20 Sayı Akış V2", page_icon="🧭", layout="wide")

APP_VERSION = "20_SAYI_AKIS_V2"
DATA_FILE = Path("veri.txt")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"

P = 20 / 80
WARMUP = 72
PRIOR_EXPOSURE = 100.0
PRIOR_HITS = PRIOR_EXPOSURE * P


# -----------------------------
# Veri okuma / ayrıştırma
# -----------------------------
def safe_secret(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, default)
        return str(v) if v is not None else default
    except Exception:
        return default


def parse_semicolon(text: str):
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("=", "#")):
            continue
        m = re.match(r"^\s*(\d+)\s*;\s*([^;]+?)\s*;\s*(.+?)\s*$", s)
        if not m:
            continue
        try:
            draw_id = int(m.group(1))
            dt = pd.to_datetime(m.group(2).strip(), dayfirst=True)
            nums = [int(x) for x in re.findall(r"\d+", m.group(3))]
            nums = list(dict.fromkeys(nums))
            if len(nums) == 20 and min(nums) >= 1 and max(nums) <= 80:
                rows.append((draw_id, dt, tuple(sorted(nums))))
        except Exception:
            pass
    return rows


def parse_blocks(text: str):
    pat = re.compile(
        r"Çekiliş\s*no\s*:\s*#?\s*(\d+)\s*\n"
        r"\s*(\d{2}\.\d{2}\.\d{4})\s*[-–—]?\s*(\d{2}:\d{2})",
        re.I,
    )
    ms = list(pat.finditer(text))
    rows = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        block = text[m.end():end]
        nums = []
        for ln in block.splitlines():
            s = ln.strip()
            if re.fullmatch(r"\d{1,2}", s):
                n = int(s)
                if 1 <= n <= 80:
                    nums.append(n)
                if len(nums) == 20:
                    break
        if len(nums) == 20:
            dt = pd.to_datetime(f"{m.group(2)} {m.group(3)}", dayfirst=True)
            rows.append((int(m.group(1)), dt, tuple(sorted(nums))))
    return rows


@st.cache_data(show_spinner=False)
def parse_text(text: str) -> pd.DataFrame:
    rows = parse_semicolon(text)
    if not rows:
        rows = parse_blocks(text)
    df = pd.DataFrame(rows, columns=["draw", "dt", "nums"])
    if df.empty:
        return df
    df = (
        df.sort_values(["dt", "draw"])
        .drop_duplicates("draw", keep="last")
        .reset_index(drop=True)
    )
    return df


def read_source(uploaded=None):
    if uploaded is not None:
        raw = uploaded.getvalue()
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                return raw.decode(enc), f"Yüklenen: {uploaded.name}"
            except Exception:
                pass
        return raw.decode("utf-8", errors="replace"), f"Yüklenen: {uploaded.name}"

    if DATA_FILE.exists():
        return DATA_FILE.read_text(encoding="utf-8", errors="replace"), "GitHub repo / yerel veri.txt"

    repo = safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO
    branch = safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH
    path = safe_secret("GITHUB_DATA_PATH", DEFAULT_PATH) or DEFAULT_PATH
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-20-sayi-akis-v2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace"), f"GitHub RAW: {repo}/{path}"


# -----------------------------
# Matematik yardımcıları
# -----------------------------
def build_matrix(df: pd.DataFrame):
    m = np.zeros((len(df), 80), dtype=np.uint8)
    for i, nums in enumerate(df["nums"].tolist()):
        if nums:
            m[i, np.asarray(nums, dtype=int) - 1] = 1
    pref = np.vstack([
        np.zeros((1, 80), dtype=np.int32),
        np.cumsum(m, axis=0, dtype=np.int32),
    ])
    return m, pref


def zscore(counts, n):
    arr = np.asarray(counts, dtype=float)
    if n <= 0:
        return np.zeros_like(arr, dtype=float)
    den = math.sqrt(max(1e-12, n * P * (1.0 - P)))
    return (arr - n * P) / den


def temp_vec(score):
    score = np.asarray(score, dtype=float)
    out = np.full(score.shape, "NÖTR", dtype=object)
    out[score >= 1.00] = "SICAK"
    out[(score >= 0.35) & (score < 1.00)] = "ILIK"
    out[(score <= -0.35) & (score > -1.00)] = "SERİN"
    out[score <= -1.00] = "SOĞUK"
    return out


def direction_vec(recent_counts, recent_n, prev_counts, prev_n):
    if recent_n <= 0 or prev_n <= 0:
        return np.full(80, "YATAY", dtype=object), np.zeros(80, dtype=float)
    recent_rate = np.asarray(recent_counts, dtype=float) / float(recent_n)
    prev_rate = np.asarray(prev_counts, dtype=float) / float(prev_n)
    delta = recent_rate - prev_rate
    out = np.full(80, "YATAY", dtype=object)
    out[delta >= 0.08] = "YÜKSELİYOR"
    out[delta <= -0.08] = "DÜŞÜYOR"
    return out, delta


def gap_bucket(gap):
    if gap is None or (isinstance(gap, float) and np.isnan(gap)):
        return "İLK/ÇOK UZAK"
    g = int(gap)
    if g <= 1:
        return "1"
    if g <= 3:
        return "2-3"
    if g <= 6:
        return "4-6"
    if g <= 12:
        return "7-12"
    return "13+"


def next_draw_dt(last_dt):
    dt = pd.Timestamp(last_dt).to_pydatetime()
    if dt.hour == 1 and dt.minute == 2:
        return dt.replace(hour=7, minute=2)
    if dt.hour == 23 and dt.minute == 57:
        return (dt + timedelta(days=1)).replace(hour=0, minute=2)
    return dt + timedelta(minutes=5)


def window_count(pref, idx, width):
    a = max(0, idx - width)
    return pref[idx] - pref[a], idx - a


def feature_vectors(df, m, pref, idx, day_start, last_seen, slot_counts, slot_draws):
    c6, n6 = window_count(pref, idx, 6)
    c12, n12 = window_count(pref, idx, 12)
    c24, n24 = window_count(pref, idx, 24)
    c72, n72 = window_count(pref, idx, 72)

    p12_a = max(0, idx - 24)
    p12_b = max(0, idx - 12)
    prev12 = pref[p12_b] - pref[p12_a]
    prev12_n = p12_b - p12_a

    z12 = zscore(c12, n12)
    z24 = zscore(c24, n24)
    z72 = zscore(c72, n72)
    heat_score = 0.50 * z12 + 0.30 * z24 + 0.20 * z72
    heat = temp_vec(heat_score)

    direction, trend_delta = direction_vec(c12, n12, prev12, prev12_n)
    transition = np.asarray([
        f"{a}→{b}" for a, b in zip(temp_vec(zscore(prev12, prev12_n)), temp_vec(z12))
    ], dtype=object)

    day_n = max(0, idx - day_start)
    day_counts = pref[idx] - pref[day_start]
    day_z = zscore(day_counts, day_n)
    day_heat = temp_vec(day_z)

    gaps = np.full(80, np.nan, dtype=float)
    seen = last_seen >= 0
    gaps[seen] = idx - last_seen[seen]

    dt = pd.Timestamp(df.iloc[idx]["dt"])
    clock = dt.strftime("%H:%M")
    sc = slot_counts.get(clock, np.zeros(80, dtype=np.int32))
    sd = int(slot_draws.get(clock, 0))
    slot_z = zscore(sc, sd)

    return {
        "c6": c6, "c12": c12, "prev12": prev12, "c24": c24, "c72": c72,
        "heat_score": heat_score, "heat": heat, "direction": direction,
        "trend_delta": trend_delta, "transition": transition,
        "day_counts": day_counts, "day_z": day_z, "day_heat": day_heat,
        "gaps": gaps, "slot_counts": sc, "slot_draws": sd, "slot_z": slot_z,
    }


# -----------------------------
# Ana tarihsel akış + walk-forward
# -----------------------------
@st.cache_data(show_spinner=False)
def build_history(df_in: pd.DataFrame):
    df = df_in[["draw", "dt", "nums"]].copy().reset_index(drop=True)
    df["dt"] = pd.to_datetime(df["dt"])
    m, pref = build_matrix(df)

    last_seen = np.full(80, -1, dtype=int)
    slot_counts = {}
    slot_draws = defaultdict(int)
    buckets = defaultdict(lambda: [0, 0])
    ledger_rows = []
    backtest_rows = []
    day_start = 0
    last_day = None

    for i in range(len(df)):
        dt = pd.Timestamp(df.iloc[i]["dt"])
        day = dt.date()
        if day != last_day:
            day_start = i
            last_day = day

        clock = dt.strftime("%H:%M")
        if clock not in slot_counts:
            slot_counts[clock] = np.zeros(80, dtype=np.int32)

        f = feature_vectors(df, m, pref, i, day_start, last_seen, slot_counts, slot_draws)

        keys = []
        model_p = np.full(80, P, dtype=float)
        for n in range(80):
            k = (str(f["heat"][n]), str(f["direction"][n]), gap_bucket(f["gaps"][n]))
            keys.append(k)
            exposure, hits = buckets[k]
            model_p[n] = (hits + PRIOR_HITS) / (exposure + PRIOR_EXPOSURE)

        model_score = (
            model_p
            + 0.010 * np.tanh(f["heat_score"] / 2.0)
            + 0.010 * np.tanh(f["trend_delta"] * 4.0)
            + 0.006 * np.tanh(f["day_z"] / 2.0)
            + 0.004 * np.tanh(f["slot_z"] / 2.0)
        )

        if i >= WARMUP:
            top10 = np.argsort(-model_score)[:10]
            backtest_rows.append({
                "draw": int(df.iloc[i]["draw"]),
                "dt": dt,
                "hits_top10": int(m[i, top10].sum()),
                "top10": ",".join(str(int(x) + 1) for x in top10),
            })

        actual = np.flatnonzero(m[i])
        for n in actual:
            last_seen_text = "—"
            if last_seen[n] >= 0:
                last_seen_text = pd.Timestamp(df.iloc[last_seen[n]]["dt"]).strftime("%d.%m %H:%M")

            # Sonuç çıktıktan sonraki ısı: yalnız raporlama için.
            a12 = max(0, i + 1 - 12)
            a24 = max(0, i + 1 - 24)
            a72 = max(0, i + 1 - 72)
            h12 = pref[i + 1, n] - pref[a12, n]
            h24 = pref[i + 1, n] - pref[a24, n]
            h72 = pref[i + 1, n] - pref[a72, n]
            z12_post = float(zscore([h12], i + 1 - a12)[0])
            z24_post = float(zscore([h24], i + 1 - a24)[0])
            z72_post = float(zscore([h72], i + 1 - a72)[0])
            post_score = 0.50 * z12_post + 0.30 * z24_post + 0.20 * z72_post
            post_heat = str(temp_vec([post_score])[0])

            ledger_rows.append({
                "draw": int(df.iloc[i]["draw"]),
                "dt": dt,
                "day": dt.strftime("%Y-%m-%d"),
                "number": int(n + 1),
                "day_hits_before": int(f["day_counts"][n]),
                "day_hits_after": int(f["day_counts"][n] + 1),
                "day_heat_before": str(f["day_heat"][n]),
                "day_z_before": round(float(f["day_z"][n]), 3),
                "hits_6": int(f["c6"][n]),
                "hits_12": int(f["c12"][n]),
                "prev_12": int(f["prev12"][n]),
                "hits_24": int(f["c24"][n]),
                "hits_72": int(f["c72"][n]),
                "gap_draws": None if np.isnan(f["gaps"][n]) else int(f["gaps"][n]),
                "gap_bucket": gap_bucket(f["gaps"][n]),
                "last_seen": last_seen_text,
                "heat_score_before": round(float(f["heat_score"][n]), 3),
                "heat_before": str(f["heat"][n]),
                "heat_after": post_heat,
                "direction": str(f["direction"][n]),
                "transition": str(f["transition"][n]),
                "slot_hits_before": int(f["slot_counts"][n]),
                "slot_draws_before": int(f["slot_draws"]),
                "slot_z": round(float(f["slot_z"][n]), 3),
                "repeat_prev": bool(i > 0 and m[i - 1, n] == 1),
                "model_p_before": round(float(model_p[n]), 5),
            })

        # Sonuç ancak çekiliş bittikten sonra öğrenme hafızasına girer.
        if i >= WARMUP:
            for n in range(80):
                k = keys[n]
                buckets[k][0] += 1
                buckets[k][1] += int(m[i, n])

        for n in actual:
            last_seen[n] = i
        slot_counts[clock] += m[i]
        slot_draws[clock] += 1

    bucket_rows = []
    for (heat, direction, gb), (exposure, hits) in buckets.items():
        raw = hits / exposure if exposure else 0.0
        shrunk = (hits + PRIOR_HITS) / (exposure + PRIOR_EXPOSURE)
        bucket_rows.append({
            "heat": heat,
            "direction": direction,
            "gap_bucket": gb,
            "exposure": int(exposure),
            "hits": int(hits),
            "raw_rate": raw,
            "shrunk_rate": shrunk,
            "lift_vs_25": shrunk / P,
        })

    ledger = pd.DataFrame(ledger_rows)
    bucket_df = pd.DataFrame(bucket_rows)
    if not bucket_df.empty:
        bucket_df = bucket_df.sort_values(["shrunk_rate", "exposure"], ascending=[False, False]).reset_index(drop=True)
    backtest = pd.DataFrame(backtest_rows)
    return ledger, bucket_df, backtest


# -----------------------------
# Belirli anda 80 sayının durumu
# -----------------------------
def state_at(df: pd.DataFrame, idx: int, target_dt, bucket_df: pd.DataFrame):
    df = df[["draw", "dt", "nums"]].copy().reset_index(drop=True)
    df["dt"] = pd.to_datetime(df["dt"])
    m, pref = build_matrix(df)
    idx = int(max(0, min(idx, len(df))))
    target_dt = pd.Timestamp(target_dt)

    def wc(width):
        a = max(0, idx - width)
        return pref[idx] - pref[a], idx - a

    c6, n6 = wc(6)
    c12, n12 = wc(12)
    c24, n24 = wc(24)
    c72, n72 = wc(72)
    p12_a = max(0, idx - 24)
    p12_b = max(0, idx - 12)
    prev12 = pref[p12_b] - pref[p12_a]
    prev12_n = p12_b - p12_a

    z12 = zscore(c12, n12)
    z24 = zscore(c24, n24)
    z72 = zscore(c72, n72)
    heat_score = 0.50 * z12 + 0.30 * z24 + 0.20 * z72
    heat = temp_vec(heat_score)
    direction, trend_delta = direction_vec(c12, n12, prev12, prev12_n)
    transition = np.asarray([
        f"{a}→{b}" for a, b in zip(temp_vec(zscore(prev12, prev12_n)), temp_vec(z12))
    ], dtype=object)

    same_day_indices = [j for j in range(idx) if pd.Timestamp(df.iloc[j]["dt"]).date() == target_dt.date()]
    day_start = same_day_indices[0] if same_day_indices else idx
    day_n = idx - day_start
    day_counts = pref[idx] - pref[day_start]
    day_z = zscore(day_counts, day_n)
    day_heat = temp_vec(day_z)

    gaps = np.full(80, np.nan, dtype=float)
    last_seen = ["—"] * 80
    if idx > 0:
        hist = m[:idx]
        rev = hist[::-1]
        has = rev.any(axis=0)
        dist = np.argmax(rev, axis=0) + 1
        for n in range(80):
            if has[n]:
                gaps[n] = int(dist[n])
                last_seen[n] = pd.Timestamp(df.iloc[idx - int(dist[n])]["dt"]).strftime("%d.%m %H:%M")

    clock = target_dt.strftime("%H:%M")
    if idx:
        clocks = df.iloc[:idx]["dt"].dt.strftime("%H:%M")
        mask = (clocks == clock).to_numpy()
    else:
        mask = np.zeros(0, dtype=bool)

    if idx and mask.any():
        slot_counts = m[:idx][mask].sum(axis=0)
        slot_n = int(mask.sum())
    else:
        slot_counts = np.zeros(80, dtype=int)
        slot_n = 0
    slot_z = zscore(slot_counts, slot_n)

    rate_map = {}
    if bucket_df is not None and not bucket_df.empty:
        for r in bucket_df.itertuples(index=False):
            rate_map[(str(r.heat), str(r.direction), str(r.gap_bucket))] = float(r.shrunk_rate)

    rows = []
    for n in range(80):
        gb = gap_bucket(gaps[n])
        mp = rate_map.get((str(heat[n]), str(direction[n]), gb), P)
        model_score = (
            mp
            + 0.010 * math.tanh(float(heat_score[n]) / 2.0)
            + 0.010 * math.tanh(float(trend_delta[n]) * 4.0)
            + 0.006 * math.tanh(float(day_z[n]) / 2.0)
            + 0.004 * math.tanh(float(slot_z[n]) / 2.0)
        )
        rows.append({
            "Sayı": n + 1,
            "Gün içi": int(day_counts[n]),
            "Gün durumu": str(day_heat[n]),
            "Gün z": round(float(day_z[n]), 2),
            "Son 6": int(c6[n]),
            "Son 12": int(c12[n]),
            "Önceki 12": int(prev12[n]),
            "Son 24": int(c24[n]),
            "Son 72": int(c72[n]),
            "Kaç çekiliş önce": None if np.isnan(gaps[n]) else int(gaps[n]),
            "Son görülme": last_seen[n],
            "Isı": str(heat[n]),
            "Yön": str(direction[n]),
            "Geçiş": str(transition[n]),
            "Aynı saat": f"{int(slot_counts[n])}/{slot_n}" if slot_n else "0/0",
            "Slot z": round(float(slot_z[n]), 2),
            "Model %": round(100 * mp, 2),
            "Model skor": round(float(model_score), 5),
            "Gap sınıfı": gb,
        })
    return pd.DataFrame(rows).sort_values(["Model skor", "Sayı"], ascending=[False, True]).reset_index(drop=True)


# -----------------------------
# Raporlar / kuponlar
# -----------------------------
def day_summary(ledger_day: pd.DataFrame):
    rows = []
    for (draw, dt), g in ledger_day.groupby(["draw", "dt"], sort=True):
        vc = g["heat_before"].value_counts()
        rows.append({
            "Çekiliş": int(draw),
            "Saat": pd.Timestamp(dt).strftime("%H:%M"),
            "SICAK": int(vc.get("SICAK", 0)),
            "ILIK": int(vc.get("ILIK", 0)),
            "NÖTR": int(vc.get("NÖTR", 0)),
            "SERİN": int(vc.get("SERİN", 0)),
            "SOĞUK": int(vc.get("SOĞUK", 0)),
            "Yükselen": int((g["direction"] == "YÜKSELİYOR").sum()),
            "Yatay": int((g["direction"] == "YATAY").sum()),
            "Düşen": int((g["direction"] == "DÜŞÜYOR").sum()),
            "Tekrar": int(g["repeat_prev"].sum()),
            "Ort. gap": round(float(pd.to_numeric(g["gap_draws"], errors="coerce").mean()), 2),
        })
    return pd.DataFrame(rows)


def make_coupons(state: pd.DataFrame):
    s = state.copy()
    out = []

    model = s.sort_values("Model skor", ascending=False).head(10)["Sayı"].astype(int).tolist()
    out.append(("MODEL", model))

    rising = s.copy()
    rising["_score"] = rising["Model skor"] + np.where(rising["Yön"].eq("YÜKSELİYOR"), 0.025, 0.0)
    out.append(("YÜKSELEN", rising.sort_values("_score", ascending=False).head(10)["Sayı"].astype(int).tolist()))

    slot = s.copy()
    slot["_score"] = slot["Model skor"] + 0.010 * np.tanh(pd.to_numeric(slot["Slot z"], errors="coerce").fillna(0))
    out.append(("SAAT İZİ", slot.sort_values("_score", ascending=False).head(10)["Sayı"].astype(int).tolist()))

    chosen = []
    groups = [
        (s[s["Isı"].isin(["SICAK", "ILIK"])], 3),
        (s[(s["Isı"] == "NÖTR") & (s["Yön"].isin(["YÜKSELİYOR", "YATAY"]))], 3),
        (s[(s["Isı"].isin(["SERİN", "SOĞUK"])) & (s["Yön"] == "YÜKSELİYOR")], 2),
    ]
    for g, take in groups:
        c = 0
        for n in g.sort_values("Model skor", ascending=False)["Sayı"].astype(int):
            if n not in chosen:
                chosen.append(n)
                c += 1
            if c >= take:
                break
    for n in s.sort_values("Model skor", ascending=False)["Sayı"].astype(int):
        if n not in chosen:
            chosen.append(n)
        if len(chosen) >= 10:
            break
    out.append(("DENGELİ", chosen[:10]))
    return out


def selected_draw_detail(ledger: pd.DataFrame, draw: int):
    g = ledger[ledger["draw"] == int(draw)].copy().sort_values("number")
    if g.empty:
        return g
    return g[[
        "number", "day_hits_before", "day_hits_after", "day_heat_before",
        "hits_6", "hits_12", "prev_12", "hits_24", "hits_72",
        "gap_draws", "last_seen", "heat_before", "direction", "transition",
        "heat_after", "slot_hits_before", "slot_draws_before", "repeat_prev",
    ]].rename(columns={
        "number": "Sayı",
        "day_hits_before": "Gün içi önce",
        "day_hits_after": "Gün içi sonra",
        "day_heat_before": "Gün durumu",
        "hits_6": "Son 6",
        "hits_12": "Son 12",
        "prev_12": "Önceki 12",
        "hits_24": "Son 24",
        "hits_72": "Son 72",
        "gap_draws": "Kaç çekiliş önce",
        "last_seen": "Son görülme",
        "heat_before": "Isı (önce)",
        "direction": "Yön",
        "transition": "Geçiş",
        "heat_after": "Isı (sonra)",
        "slot_hits_before": "Aynı saat çıkış",
        "slot_draws_before": "Aynı saat örnek",
        "repeat_prev": "Bir önceki çekilişte",
    })


# -----------------------------
# UI
# -----------------------------
st.title("🧭 Hızlı On — 20 Sayı Akış Laboratuvarı V2")
st.caption(
    "Her gerçek 20 sayıyı çekilişten ÖNCEKİ haliyle inceler. "
    "Gün içi durum + son durum + sıcak/soğuk + yön + geçiş + walk-forward kupon testi."
)

uploaded = st.sidebar.file_uploader("İstersen başka veri.txt yükle", type=["txt"])
try:
    raw, source = read_source(uploaded)
    df = parse_text(raw)
except Exception as e:
    st.error(f"Veri okunamadı: {type(e).__name__}: {e}")
    st.stop()

if df.empty:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

st.sidebar.success(f"Kaynak: {source}")
st.sidebar.caption(
    f"Çekiliş: {len(df):,} · Gün: {df['dt'].dt.date.nunique()} · "
    f"{df.iloc[0]['dt']:%d.%m.%Y %H:%M} → {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}"
)

with st.spinner("36 günlük havuzdan sayı akış defteri ve walk-forward test hazırlanıyor..."):
    ledger, bucket_df, backtest = build_history(df)

# Veri özeti
c1, c2, c3, c4 = st.columns(4)
c1.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
c2.metric("Gün", int(df["dt"].dt.date.nunique()))
c3.metric("İlk", df.iloc[0]["dt"].strftime("%d.%m.%Y"))
c4.metric("Son", df.iloc[-1]["dt"].strftime("%d.%m.%Y"))
st.caption(f"#{int(df.iloc[0]['draw'])} → #{int(df.iloc[-1]['draw'])} · {source}")

st.divider()
st.subheader("1) Günün 00:02'den son çekilişe kadar gerçek 20 sayı akışı")
dates = sorted(ledger["day"].unique().tolist())
sel_day = st.selectbox("Gün", dates, index=len(dates)-1)
ld = ledger[ledger["day"] == sel_day].copy()
ds = day_summary(ld)
st.dataframe(ds, use_container_width=True, hide_index=True, height=430)

# Tek çekiliş
draws = ds["Çekiliş"].astype(int).tolist()
if draws:
    def fmt_draw(x):
        r = ds[ds["Çekiliş"] == x].iloc[0]
        return f"#{x} — {r['Saat']}"

    sel_draw = st.selectbox("Tek çekilişi aç", draws, index=0, format_func=fmt_draw)
    actual_nums = list(df[df["draw"] == sel_draw].iloc[0]["nums"])
    st.write("**Gerçek 20:** " + " – ".join(map(str, actual_nums)))

    detail = selected_draw_detail(ledger, sel_draw)
    st.subheader(f"2) #{sel_draw} — çıkan 20 sayı çekilişten ÖNCE ne durumdaydı?")
    st.dataframe(detail, use_container_width=True, hide_index=True, height=620)

    g = ledger[ledger["draw"] == sel_draw]
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("Sıcak", int((g["heat_before"] == "SICAK").sum()))
    a2.metric("Ilık", int((g["heat_before"] == "ILIK").sum()))
    a3.metric("Nötr", int((g["heat_before"] == "NÖTR").sum()))
    a4.metric("Serin", int((g["heat_before"] == "SERİN").sum()))
    a5.metric("Soğuk", int((g["heat_before"] == "SOĞUK").sum()))

    # O çekilişten önceki 80 sayının tamamı
    idx = int(df.index[df["draw"] == sel_draw][0])
    target_dt = pd.Timestamp(df.iloc[idx]["dt"])
    state_before_draw = state_at(df.iloc[:idx].copy().reset_index(drop=True), idx, target_dt, bucket_df)
    with st.expander("Bu çekilişten hemen önceki 80 sayının tamamını göster", expanded=False):
        st.dataframe(state_before_draw, use_container_width=True, hide_index=True, height=560)

st.divider()
st.subheader("3) Walk-forward test — kupon motoru geleceği görmeden ne yaptı?")
if not backtest.empty:
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Test çekilişi", f"{len(backtest):,}".replace(",", "."))
    b2.metric("10'luda ort. isabet", f"{backtest['hits_top10'].mean():.3f}")
    b3.metric("4+ oranı", f"{100*backtest['hits_top10'].ge(4).mean():.2f}%")
    b4.metric("5+ oranı", f"{100*backtest['hits_top10'].ge(5).mean():.2f}%")
    b5.metric("Maksimum", int(backtest["hits_top10"].max()))

    dist = (
        backtest["hits_top10"].value_counts().sort_index()
        .rename_axis("İsabet").reset_index(name="Çekiliş sayısı")
    )
    st.dataframe(dist, use_container_width=True, hide_index=True)
    st.caption(
        "Karşılaştırma eşiği: rastgele seçilmiş 10 sayının teorik ortalama isabeti 2,50'dir. "
        "Bir sinyali güçlü kabul etmek için yalnız yüksek maksimum değil, ortalama ve farklı günlerde süreklilik aranmalıdır."
    )
else:
    st.info("Walk-forward test için yeterli çekiliş yok.")

st.subheader("4) Hangi sıcaklık + yön + gap durumları daha çok gelmiş?")
if not bucket_df.empty:
    show_b = bucket_df[bucket_df["exposure"] >= 200].copy()
    show_b["Gerçek %"] = (100 * show_b["raw_rate"]).round(2)
    show_b["Düzeltilmiş %"] = (100 * show_b["shrunk_rate"]).round(2)
    show_b["Lift"] = show_b["lift_vs_25"].round(3)
    st.dataframe(
        show_b[["heat", "direction", "gap_bucket", "exposure", "hits", "Gerçek %", "Düzeltilmiş %", "Lift"]]
        .rename(columns={
            "heat": "Isı", "direction": "Yön", "gap_bucket": "Gap",
            "exposure": "Örnek", "hits": "Gelen",
        }),
        use_container_width=True,
        hide_index=True,
        height=460,
    )

st.divider()
next_dt = next_draw_dt(df.iloc[-1]["dt"])
st.subheader(f"5) Veri havuzuna göre sıradaki çekiliş: {next_dt:%d.%m.%Y %H:%M}")
current_state = state_at(df, len(df), next_dt, bucket_df)
st.dataframe(current_state.head(30), use_container_width=True, hide_index=True, height=520)

st.subheader("6) Kupon reçetesi")
coupons = make_coupons(current_state)
cp = pd.DataFrame([
    {"Profil": name, "10 sayı": " - ".join(map(str, nums))}
    for name, nums in coupons
])
st.dataframe(cp, use_container_width=True, hide_index=True)
st.caption(
    "MODEL = geçmişteki durum sınıflarının düzeltilmiş oranı; YÜKSELEN = ivme ağırlıklı; "
    "SAAT İZİ = aynı saat geçmişi; DENGELİ = sıcak/ılık + nötr + soğuktan yükselen karışımı. "
    "Kuponlar garanti değildir; hangi profil daha sağlıklıysa walk-forward testten anlaşılır."
)

st.divider()
st.subheader("7) Günlük teknik çıktı")
# Seçili günün 20 x çekiliş ayrıntısını indir.
export_cols = [
    "draw", "dt", "number", "day_hits_before", "day_hits_after", "day_heat_before",
    "hits_6", "hits_12", "prev_12", "hits_24", "hits_72", "gap_draws", "last_seen",
    "heat_before", "direction", "transition", "heat_after", "slot_hits_before", "slot_draws_before",
    "repeat_prev", "model_p_before",
]
export_day = ld[export_cols].copy()
export_day["dt"] = pd.to_datetime(export_day["dt"]).dt.strftime("%d.%m.%Y %H:%M")
st.download_button(
    "⬇️ Seçili günün bütün çekiliş / gerçek20 teknik CSV'sini indir",
    data=export_day.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"HIZLI_ON_{sel_day}_GERCEK20_AKIS.csv",
    mime="text/csv",
    use_container_width=True,
)

with st.expander("Isı ve yön nasıl hesaplanıyor?", expanded=False):
    st.markdown(
        """
- **Gün içi:** O gün hedef çekilişten önce sayı kaç kez çıktı. Ayrıca teorik %25 oranına göre gün z-skoru hesaplanır.
- **Isı:** Son 12, 24 ve 72 çekilişin z-skorları sırasıyla %50, %30, %20 ağırlıkla birleşir.
- **SICAK / ILIK / NÖTR / SERİN / SOĞUK:** Birleşik ısı skorunun bantlarıdır.
- **Yön:** Son 12 çekilişteki görülme oranı ile ondan önceki 12 çekiliş karşılaştırılır. Fark en az 0,08 ise yükseliyor/düşüyor kabul edilir.
- **Geçiş:** Önceki 12'lik pencerenin ısı sınıfından son 12'lik pencerenin ısı sınıfına hareket. Örn. `SOĞUK→NÖTR`.
- **Gap:** Sayının hedef çekilişten kaç çekiliş önce görüldüğü.
- **Aynı saat:** Örneğin hedef 10:42 ise önceki günlerdeki 10:42 çekilişlerinde kaç kez görüldüğü.
- **Model %:** Isı + yön + gap sınıfının geçmişteki isabet oranı; aşırı uyumu azaltmak için %25 tabanına doğru Bayes tipi yumuşatma uygulanır.
- **Walk-forward:** Her hedef çekilişte model yalnız o ana kadar oluşmuş geçmişi kullanır; hedef sonucu daha sonra öğrenme hafızasına eklenir.
        """
    )

st.warning(
    "Bu uygulama geçmiş çekilişleri teknik olarak inceler. Sıcak/soğuk veya geçmiş ritim, bağımsız bir çekilişte gelecekteki sonucu garanti etmez."
)
