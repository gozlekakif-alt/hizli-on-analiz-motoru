# -*- coding: utf-8 -*-
"""
HIZLI ON — KATMAN ARAŞTIRMA LABORATUVARI V3

Tek araştırma hedefi:
1) Her hedef çekilişten HEMEN ÖNCE 1-80 arasındaki 80 sayının durumunu çıkar.
2) Gerçek 20 sayının hangi ısı katmanlarından geldiğini ölç.
3) Katman başına beklenen sayı kotasını saat saat / gün gün öğren.
4) Katman içindeki adayları yalnız hedef öncesi bilgiyle sırala.
5) Walk-forward testte 20'lik hedef havuzu ve 10'lu kuponu sınar.

Önemli metodoloji:
- Tarihsel hedeflerde sonuç görülmeden sonraki bilgi kullanılmaz.
- Tahmin kotaları yalnız daha önce bitmiş çekilişlerin katman dağılımlarından öğrenilir.
- Aday skorları yalnız hedef çekilişten önceki verilerden hesaplanır.
- Geçmiş örüntü gelecekte kazanç garantisi değildir.
"""
from __future__ import annotations

import math
import re
import urllib.request
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On — Katman Araştırma V3", page_icon="🧬", layout="wide")

APP_VERSION = "KATMAN_ARASTIRMA_V3_2026_10_06"
DATA_FILE = Path("veri.txt")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"

P = 20 / 80
WARMUP = 72
LAYERS = ["SOĞUK", "SERİN", "NÖTR", "ILIK", "SICAK"]
LAYER_TO_CODE = {x: i for i, x in enumerate(LAYERS)}
CODE_TO_LAYER = {i: x for i, x in enumerate(LAYERS)}

PRIOR_EXPOSURE_1 = 90.0
PRIOR_EXPOSURE_2 = 110.0
PRIOR_EXPOSURE_3 = 130.0


# -----------------------------------------------------------------------------
# VERİ OKUMA
# -----------------------------------------------------------------------------
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
    df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
    df = df.dropna(subset=["dt"])
    return (
        df.sort_values(["dt", "draw"])
        .drop_duplicates("draw", keep="last")
        .reset_index(drop=True)
    )


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
        return DATA_FILE.read_text(encoding="utf-8", errors="replace"), "repo / veri.txt"

    repo = safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO
    branch = safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH
    path = safe_secret("GITHUB_DATA_PATH", DEFAULT_PATH) or DEFAULT_PATH
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-katman-v3"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace"), f"GitHub RAW: {repo}/{path}"


# -----------------------------------------------------------------------------
# MATEMATİK / ÖZELLİKLER
# -----------------------------------------------------------------------------
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
    c3, n3 = window_count(pref, idx, 3)
    c6, n6 = window_count(pref, idx, 6)
    c12, n12 = window_count(pref, idx, 12)
    c24, n24 = window_count(pref, idx, 24)
    c48, n48 = window_count(pref, idx, 48)
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

    prev_heat = temp_vec(zscore(prev12, prev12_n))
    direction, trend_delta = direction_vec(c12, n12, prev12, prev12_n)
    transition = np.asarray([f"{a}→{b}" for a, b in zip(prev_heat, heat)], dtype=object)

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
        "c3": c3, "c6": c6, "c12": c12, "prev12": prev12,
        "c24": c24, "c48": c48, "c72": c72,
        "heat_score": heat_score, "heat": heat,
        "direction": direction, "trend_delta": trend_delta,
        "transition": transition, "day_counts": day_counts,
        "day_z": day_z, "day_heat": day_heat,
        "gaps": gaps, "slot_counts": sc, "slot_draws": sd, "slot_z": slot_z,
    }


def posterior(stats, key, prior_exposure):
    exposure, hits = stats.get(key, (0, 0))
    return (hits + prior_exposure * P) / (exposure + prior_exposure)


def round_preserve_total(raw, total):
    raw = np.asarray(raw, dtype=float)
    raw = np.maximum(raw, 0.0)
    if raw.sum() <= 0:
        raw = np.ones(len(raw), dtype=float)
    raw = raw * (float(total) / raw.sum())
    base = np.floor(raw).astype(int)
    left = int(total - base.sum())
    if left > 0:
        order = np.argsort(-(raw - base))
        for j in order[:left]:
            base[j] += 1
    elif left < 0:
        order = np.argsort(raw - base)
        for j in order[:abs(left)]:
            if base[j] > 0:
                base[j] -= 1
    return base


def fit_quota_to_capacity(quota, capacities, total):
    q = np.asarray(quota, dtype=int).copy()
    cap = np.asarray(capacities, dtype=int)
    q = np.minimum(q, cap)
    while q.sum() < total:
        room = cap - q
        if room.max() <= 0:
            break
        j = int(np.argmax(room))
        q[j] += 1
    while q.sum() > total:
        j = int(np.argmax(q))
        if q[j] > 0:
            q[j] -= 1
        else:
            break
    return q


def quota_prediction(global_sum, global_n, clock_sum, clock_n, hour_sum, hour_n, recent_comps):
    # Bütün bileşenler 20 sayıya toplamlandığı için ağırlıklı ortalama da 20'ye toplamlanır.
    means = []
    weights = []

    if global_n > 0:
        means.append(global_sum / global_n)
        weights.append(0.20)
    if len(recent_comps) > 0:
        means.append(np.mean(np.vstack(recent_comps), axis=0))
        weights.append(0.40)
    if clock_n >= 2:
        means.append(clock_sum / clock_n)
        weights.append(0.25)
    if hour_n >= 4:
        means.append(hour_sum / hour_n)
        weights.append(0.15)

    if not means:
        raw = np.asarray([4, 4, 4, 4, 4], dtype=float)
    else:
        w = np.asarray(weights, dtype=float)
        w = w / w.sum()
        raw = sum(a * b for a, b in zip(w, means))

    return raw, round_preserve_total(raw, 20)


def select_by_quota(scores, layer_codes, quota, total):
    chosen = []
    for layer_code, take in enumerate(quota):
        inds = np.where(layer_codes == layer_code)[0]
        if len(inds) == 0 or int(take) <= 0:
            continue
        order = inds[np.argsort(-scores[inds])]
        chosen.extend(order[:int(take)].tolist())

    # Kapasite / yuvarlama nedeniyle eksik kaldıysa en yüksek skorlardan tamamla.
    if len(chosen) < total:
        for n in np.argsort(-scores):
            if int(n) not in chosen:
                chosen.append(int(n))
            if len(chosen) >= total:
                break
    return chosen[:total]


# -----------------------------------------------------------------------------
# WALK-FORWARD ANA MOTOR
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_research(df_in: pd.DataFrame):
    df = df_in[["draw", "dt", "nums"]].copy().reset_index(drop=True)
    df["dt"] = pd.to_datetime(df["dt"])
    m, pref = build_matrix(df)

    n_draws = len(df)
    score_matrix = np.zeros((n_draws, 80), dtype=np.float32)
    layer_matrix = np.zeros((n_draws, 80), dtype=np.uint8)

    last_seen = np.full(80, -1, dtype=int)
    slot_counts = {}
    slot_draws = defaultdict(int)

    stats1 = defaultdict(lambda: [0, 0])  # heat + direction + gap
    stats2 = defaultdict(lambda: [0, 0])  # transition + gap
    stats3 = defaultdict(lambda: [0, 0])  # day_heat + direction

    global_sum = np.zeros(5, dtype=float)
    global_n = 0
    clock_sum = defaultdict(lambda: np.zeros(5, dtype=float))
    clock_n = defaultdict(int)
    hour_sum = defaultdict(lambda: np.zeros(5, dtype=float))
    hour_n = defaultdict(int)
    recent_comps = deque(maxlen=12)

    ledger_rows = []
    quota_rows = []
    backtest_rows = []

    day_start = 0
    last_day = None

    for i in range(n_draws):
        dt = pd.Timestamp(df.iloc[i]["dt"])
        day = dt.date()
        if day != last_day:
            day_start = i
            last_day = day

        clock = dt.strftime("%H:%M")
        hour = int(dt.hour)
        if clock not in slot_counts:
            slot_counts[clock] = np.zeros(80, dtype=np.int32)

        f = feature_vectors(df, m, pref, i, day_start, last_seen, slot_counts, slot_draws)
        layer_codes = np.asarray([LAYER_TO_CODE[str(x)] for x in f["heat"]], dtype=np.uint8)
        layer_matrix[i] = layer_codes

        scores = np.zeros(80, dtype=float)
        keys1, keys2, keys3 = [], [], []
        for n in range(80):
            gb = gap_bucket(f["gaps"][n])
            k1 = (str(f["heat"][n]), str(f["direction"][n]), gb)
            k2 = (str(f["transition"][n]), gb)
            k3 = (str(f["day_heat"][n]), str(f["direction"][n]))
            keys1.append(k1); keys2.append(k2); keys3.append(k3)

            p1 = posterior(stats1, k1, PRIOR_EXPOSURE_1)
            p2 = posterior(stats2, k2, PRIOR_EXPOSURE_2)
            p3 = posterior(stats3, k3, PRIOR_EXPOSURE_3)
            p_model = 0.50 * p1 + 0.30 * p2 + 0.20 * p3

            scores[n] = (
                p_model
                + 0.009 * math.tanh(float(f["trend_delta"][n]) * 4.0)
                + 0.006 * math.tanh(float(f["day_z"][n]) / 2.0)
                + 0.004 * math.tanh(float(f["slot_z"][n]) / 2.0)
                + 0.003 * math.tanh(float(f["heat_score"][n]) / 2.0)
            )

        score_matrix[i] = scores.astype(np.float32)

        raw_quota, pred_quota = quota_prediction(
            global_sum, global_n,
            clock_sum[clock], clock_n[clock],
            hour_sum[hour], hour_n[hour],
            recent_comps,
        )

        capacities = np.bincount(layer_codes, minlength=5)
        pred_quota = fit_quota_to_capacity(pred_quota, capacities, 20)
        coupon_quota = round_preserve_total(pred_quota * 0.5, 10)
        coupon_quota = fit_quota_to_capacity(coupon_quota, capacities, 10)

        pool20 = select_by_quota(scores, layer_codes, pred_quota, 20)
        coupon10 = select_by_quota(scores, layer_codes, coupon_quota, 10)

        actual_mask = m[i].astype(bool)
        actual = np.flatnonzero(actual_mask)
        actual_comp = np.bincount(layer_codes[actual], minlength=5).astype(int)

        pool_hits = int(m[i, pool20].sum())
        coupon_hits = int(m[i, coupon10].sum())
        quota_abs_err = np.abs(actual_comp - pred_quota)

        quota_row = {
            "draw": int(df.iloc[i]["draw"]),
            "dt": dt,
            "day": dt.strftime("%Y-%m-%d"),
            "hour": hour,
            "clock": clock,
            "pool20_hits": pool_hits,
            "coupon10_hits": coupon_hits,
            "quota_mae": float(quota_abs_err.mean()),
            "quota_l1": int(quota_abs_err.sum()),
            "quota_all_within1": bool(np.all(quota_abs_err <= 1)),
            "pool20": ",".join(str(x + 1) for x in pool20),
            "coupon10": ",".join(str(x + 1) for x in coupon10),
        }
        for j, layer in enumerate(LAYERS):
            quota_row[f"actual_{layer}"] = int(actual_comp[j])
            quota_row[f"pred_{layer}"] = int(pred_quota[j])
            quota_row[f"rawpred_{layer}"] = round(float(raw_quota[j]), 3)
            quota_row[f"couponq_{layer}"] = int(coupon_quota[j])
            quota_row[f"candidates_{layer}"] = int(capacities[j])
        quota_rows.append(quota_row)

        if i >= WARMUP:
            backtest_rows.append(quota_row.copy())

        # Gerçek 20'nin hedef ÖNCESİ pasaportu
        for n in actual:
            last_seen_text = "—"
            if last_seen[n] >= 0:
                last_seen_text = pd.Timestamp(df.iloc[last_seen[n]]["dt"]).strftime("%d.%m %H:%M")
            ledger_rows.append({
                "draw": int(df.iloc[i]["draw"]),
                "dt": dt,
                "day": dt.strftime("%Y-%m-%d"),
                "hour": hour,
                "clock": clock,
                "number": int(n + 1),
                "layer": str(f["heat"][n]),
                "direction": str(f["direction"][n]),
                "transition": str(f["transition"][n]),
                "day_hits_before": int(f["day_counts"][n]),
                "day_heat_before": str(f["day_heat"][n]),
                "h3": int(f["c3"][n]),
                "h6": int(f["c6"][n]),
                "h12": int(f["c12"][n]),
                "prev12": int(f["prev12"][n]),
                "h24": int(f["c24"][n]),
                "h48": int(f["c48"][n]),
                "h72": int(f["c72"][n]),
                "gap": None if np.isnan(f["gaps"][n]) else int(f["gaps"][n]),
                "gap_bucket": gap_bucket(f["gaps"][n]),
                "last_seen": last_seen_text,
                "slot_hits_before": int(f["slot_counts"][n]),
                "slot_draws_before": int(f["slot_draws"]),
                "score_before": round(float(scores[n]), 6),
                "repeat_prev": bool(i > 0 and m[i - 1, n] == 1),
            })

        # SONUÇ AÇILDIKTAN SONRA öğrenme güncellenir.
        for n in range(80):
            hit = int(actual_mask[n])
            for stats, key in ((stats1, keys1[n]), (stats2, keys2[n]), (stats3, keys3[n])):
                stats[key][0] += 1
                stats[key][1] += hit

        global_sum += actual_comp
        global_n += 1
        clock_sum[clock] += actual_comp
        clock_n[clock] += 1
        hour_sum[hour] += actual_comp
        hour_n[hour] += 1
        recent_comps.append(actual_comp.astype(float))

        for n in actual:
            last_seen[n] = i
        slot_counts[clock] += m[i]
        slot_draws[clock] += 1

    def stats_to_df(stats, kind):
        rows = []
        for key, (exposure, hits) in stats.items():
            pe = PRIOR_EXPOSURE_1 if kind == 1 else PRIOR_EXPOSURE_2 if kind == 2 else PRIOR_EXPOSURE_3
            rows.append({
                "key": key,
                "exposure": int(exposure),
                "hits": int(hits),
                "rate": hits / exposure if exposure else 0.0,
                "posterior": (hits + pe * P) / (exposure + pe),
            })
        return pd.DataFrame(rows)

    return (
        pd.DataFrame(ledger_rows),
        pd.DataFrame(quota_rows),
        pd.DataFrame(backtest_rows),
        score_matrix,
        layer_matrix,
        stats_to_df(stats1, 1),
        stats_to_df(stats2, 2),
        stats_to_df(stats3, 3),
    )


# -----------------------------------------------------------------------------
# SEÇİLİ HEDEF / SONRAKİ HEDEF İÇİN 80 SAYI PASAPORTU
# -----------------------------------------------------------------------------
def stats_maps(stats1_df, stats2_df, stats3_df):
    def mp(df):
        out = {}
        if df is None or df.empty:
            return out
        for r in df.itertuples(index=False):
            out[r.key] = float(r.posterior)
        return out
    return mp(stats1_df), mp(stats2_df), mp(stats3_df)


def snapshot_state(df, m, pref, idx, target_dt, score_override=None, final_stats=None):
    idx = int(max(0, min(idx, len(df))))
    target_dt = pd.Timestamp(target_dt)

    def wc(width):
        a = max(0, idx - width)
        return pref[idx] - pref[a], idx - a

    c3, n3 = wc(3); c6, n6 = wc(6); c12, n12 = wc(12)
    c24, n24 = wc(24); c48, n48 = wc(48); c72, n72 = wc(72)
    p12_a = max(0, idx - 24); p12_b = max(0, idx - 12)
    prev12 = pref[p12_b] - pref[p12_a]
    prev12_n = p12_b - p12_a

    z12 = zscore(c12, n12); z24 = zscore(c24, n24); z72 = zscore(c72, n72)
    heat_score = 0.50*z12 + 0.30*z24 + 0.20*z72
    heat = temp_vec(heat_score)
    prev_heat = temp_vec(zscore(prev12, prev12_n))
    direction, trend_delta = direction_vec(c12, n12, prev12, prev12_n)
    transition = np.asarray([f"{a}→{b}" for a,b in zip(prev_heat, heat)], dtype=object)

    prior_days = df.iloc[:idx]["dt"].dt.date if idx else pd.Series([], dtype=object)
    same = np.where(prior_days.to_numpy() == target_dt.date())[0] if idx else np.array([], dtype=int)
    day_start = int(same[0]) if len(same) else idx
    day_n = idx - day_start
    day_counts = pref[idx] - pref[day_start]
    day_z = zscore(day_counts, day_n)
    day_heat = temp_vec(day_z)

    gaps = np.full(80, np.nan, dtype=float)
    last_seen_txt = ["—"] * 80
    if idx:
        rev = m[:idx][::-1]
        has = rev.any(axis=0)
        dist = np.argmax(rev, axis=0) + 1
        for n in range(80):
            if has[n]:
                gaps[n] = int(dist[n])
                last_seen_txt[n] = pd.Timestamp(df.iloc[idx-int(dist[n])]["dt"]).strftime("%d.%m %H:%M")

    clock = target_dt.strftime("%H:%M")
    if idx:
        clocks = df.iloc[:idx]["dt"].dt.strftime("%H:%M").to_numpy()
        mask = clocks == clock
    else:
        mask = np.zeros(0, dtype=bool)
    if idx and mask.any():
        slot_counts = m[:idx][mask].sum(axis=0)
        slot_n = int(mask.sum())
    else:
        slot_counts = np.zeros(80, dtype=int); slot_n = 0
    slot_z = zscore(slot_counts, slot_n)

    if score_override is not None:
        scores = np.asarray(score_override, dtype=float)
    else:
        sm1, sm2, sm3 = stats_maps(*(final_stats or (None, None, None)))
        scores = np.zeros(80, dtype=float)
        for n in range(80):
            gb = gap_bucket(gaps[n])
            p1 = sm1.get((str(heat[n]), str(direction[n]), gb), P)
            p2 = sm2.get((str(transition[n]), gb), P)
            p3 = sm3.get((str(day_heat[n]), str(direction[n])), P)
            pm = 0.50*p1 + 0.30*p2 + 0.20*p3
            scores[n] = (
                pm
                + 0.009*math.tanh(float(trend_delta[n])*4.0)
                + 0.006*math.tanh(float(day_z[n])/2.0)
                + 0.004*math.tanh(float(slot_z[n])/2.0)
                + 0.003*math.tanh(float(heat_score[n])/2.0)
            )

    rows = []
    for n in range(80):
        rows.append({
            "Sayı": n+1,
            "Katman": str(heat[n]),
            "Yön": str(direction[n]),
            "Geçiş": str(transition[n]),
            "Gap": None if np.isnan(gaps[n]) else int(gaps[n]),
            "Gap sınıfı": gap_bucket(gaps[n]),
            "Son görülme": last_seen_txt[n],
            "Gün içi": int(day_counts[n]),
            "Gün katmanı": str(day_heat[n]),
            "H3": int(c3[n]), "H6": int(c6[n]), "H12": int(c12[n]),
            "Önceki12": int(prev12[n]), "H24": int(c24[n]), "H48": int(c48[n]), "H72": int(c72[n]),
            "Aynı dakika": f"{int(slot_counts[n])}/{slot_n}",
            "Slot z": round(float(slot_z[n]), 3),
            "Isı skor": round(float(heat_score[n]), 3),
            "Trend": round(float(trend_delta[n]), 4),
            "Model skor": round(float(scores[n]), 6),
        })
    return pd.DataFrame(rows), np.asarray([LAYER_TO_CODE[str(x)] for x in heat], dtype=np.uint8), scores


# -----------------------------------------------------------------------------
# PROFİL / TOLERANS TABLOLARI
# -----------------------------------------------------------------------------
def layer_profile(g: pd.DataFrame, prefix="actual_"):
    rows = []
    for layer in LAYERS:
        s = pd.to_numeric(g[f"{prefix}{layer}"], errors="coerce").dropna()
        if s.empty:
            rows.append({"Katman": layer, "Ortalama": np.nan, "Medyan": np.nan, "±1σ": "—", "P10–P90": "—", "Min–Maks": "—"})
            continue
        mu = float(s.mean()); sd = float(s.std(ddof=0))
        p10, p90 = np.quantile(s, [0.10, 0.90])
        rows.append({
            "Katman": layer,
            "Ortalama": round(mu, 2),
            "Medyan": round(float(s.median()), 2),
            "±1σ": f"{max(0, mu-sd):.1f}–{mu+sd:.1f}",
            "P10–P90": f"{p10:.0f}–{p90:.0f}",
            "Min–Maks": f"{int(s.min())}–{int(s.max())}",
        })
    return pd.DataFrame(rows)


def hour_profile_table(qday: pd.DataFrame):
    rows = []
    for hour, g in qday.groupby("hour"):
        row = {"Saat": f"{int(hour):02d}:xx", "Çekiliş": len(g)}
        for layer in LAYERS:
            s = g[f"actual_{layer}"].astype(float)
            mu = s.mean(); sd = s.std(ddof=0)
            row[layer] = f"{mu:.1f} ± {sd:.1f}"
        rows.append(row)
    return pd.DataFrame(rows)


def layer_numbers_for_draw(ledger, draw):
    g = ledger[ledger["draw"] == int(draw)]
    out = {}
    for layer in LAYERS:
        out[layer] = sorted(g.loc[g["layer"] == layer, "number"].astype(int).tolist())
    return out


def quota_dict_from_row(row, prefix="pred_"):
    return {layer: int(row[f"{prefix}{layer}"]) for layer in LAYERS}


def quota_array_from_row(row, prefix="pred_"):
    return np.asarray([int(row[f"{prefix}{layer}"]) for layer in LAYERS], dtype=int)


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🧬 Hızlı On — Katman Araştırma Laboratuvarı V3")
st.caption(
    "Tek konu: her çekilişte çıkan 20 sayının hangi katmanlardan geldiğini ve "
    "o katmanların içindeki hangi sayıların hedefe dönüştüğünü saat saat / gün gün ölçmek."
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

m, pref = build_matrix(df)
st.sidebar.success(f"Kaynak: {source}")
st.sidebar.caption(
    f"Çekiliş: {len(df):,} · Gün: {df['dt'].dt.date.nunique()} · "
    f"{df.iloc[0]['dt']:%d.%m.%Y %H:%M} → {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}"
)
st.sidebar.caption(f"Motor: {APP_VERSION}")

with st.spinner("Bütün havuz walk-forward işleniyor: katman → kota → katman içi aday → 20'lik havuz → 10'lu kupon..."):
    ledger, quota_log, backtest, score_matrix, layer_matrix, stats1_df, stats2_df, stats3_df = build_research(df)

# Üst özet
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
c2.metric("Gün", int(df["dt"].dt.date.nunique()))
c3.metric("Gerçek20 satırı", f"{len(ledger):,}".replace(",", "."))
c4.metric("Katman", "5")
c5.metric("Taban oran", "25%")

st.divider()
st.subheader("1) 36 günlük genel katman reçetesi")
st.caption("Bu bölüm betimleyicidir: gerçek 20 sayının katman dağılımını bütün havuzda özetler.")
st.dataframe(layer_profile(quota_log), use_container_width=True, hide_index=True)

mean_comp = [quota_log[f"actual_{x}"].mean() for x in LAYERS]
recipe = " + ".join(f"{x} {m:.2f}" for x, m in zip(LAYERS, mean_comp))
st.info(f"Ortalama 20'lik yapı: {recipe} = 20")

st.divider()
st.subheader("2) Gün gün → saat saat otomatik katman analizi")
dates = sorted(quota_log["day"].unique().tolist())
sel_day = st.selectbox("Gün", dates, index=len(dates)-1)
qday = quota_log[quota_log["day"] == sel_day].copy()
lday = ledger[ledger["day"] == sel_day].copy()

st.markdown("#### Günün saat profili")
st.dataframe(hour_profile_table(qday), use_container_width=True, hide_index=True, height=460)

st.markdown("#### Günün tamamı — her çekilişte 20 hangi katmandan geldi?")
show_cols = ["draw", "clock"]
for layer in LAYERS:
    show_cols += [f"actual_{layer}", f"pred_{layer}"]
show_cols += ["quota_mae", "pool20_hits", "coupon10_hits"]
show = qday[show_cols].copy()
rename = {"draw":"Çekiliş", "clock":"Saat", "quota_mae":"Kota MAE", "pool20_hits":"20 havuz isabet", "coupon10_hits":"10'lu isabet"}
for layer in LAYERS:
    rename[f"actual_{layer}"] = f"{layer} gerçek"
    rename[f"pred_{layer}"] = f"{layer} beklenen"
st.dataframe(show.rename(columns=rename), use_container_width=True, hide_index=True, height=520)

st.markdown("#### Seçili günün kendi toleransları")
st.dataframe(layer_profile(qday), use_container_width=True, hide_index=True)

st.divider()
st.subheader("3) Hedef çekiliş laboratuvarı — katmanda hangi sayı gerçekten oldu?")
draws = qday["draw"].astype(int).tolist()
if not draws:
    st.info("Bu günde çekiliş yok.")
    st.stop()

def fmt_draw(x):
    r = qday[qday["draw"] == x].iloc[0]
    return f"#{x} — {r['clock']}"

sel_draw = st.selectbox("Hedef çekiliş", draws, index=0, format_func=fmt_draw)
idx = int(df.index[df["draw"] == sel_draw][0])
qr = quota_log[quota_log["draw"] == sel_draw].iloc[0]
target_dt = pd.Timestamp(df.iloc[idx]["dt"])
actual_set = set(map(int, df.iloc[idx]["nums"]))

state80, layer_codes, scores = snapshot_state(
    df, m, pref, idx, target_dt,
    score_override=score_matrix[idx],
)
state80["Gerçekte çıktı"] = state80["Sayı"].isin(actual_set)
state80["Katman içi sıra"] = state80.groupby("Katman")["Model skor"].rank(method="first", ascending=False).astype(int)

actual_nums = layer_numbers_for_draw(ledger, sel_draw)
pred_q = quota_array_from_row(qr, "pred_")
actual_q = quota_array_from_row(qr, "actual_")
coupon_q = quota_array_from_row(qr, "couponq_")
capacities = np.asarray([int(qr[f"candidates_{x}"]) for x in LAYERS], dtype=int)
pool20 = select_by_quota(scores, layer_codes, pred_q, 20)
coupon10 = select_by_quota(scores, layer_codes, coupon_q, 10)
pool20_set = {x+1 for x in pool20}
coupon10_set = {x+1 for x in coupon10}

lab_rows = []
for j, layer in enumerate(LAYERS):
    candidates = state80[state80["Katman"] == layer].sort_values("Model skor", ascending=False)
    target_pool_nums = candidates.head(int(pred_q[j]))["Sayı"].astype(int).tolist()
    coupon_nums = candidates.head(int(coupon_q[j]))["Sayı"].astype(int).tolist()
    winners = actual_nums[layer]
    lab_rows.append({
        "Katman": layer,
        "80 içindeki aday": int(capacities[j]),
        "Beklenen 20 kotası": int(pred_q[j]),
        "Gerçek 20 kotası": int(actual_q[j]),
        "Fark": int(actual_q[j] - pred_q[j]),
        "10'lu kota": int(coupon_q[j]),
        "Katman 20 adayları": " - ".join(map(str, target_pool_nums)) or "—",
        "Gerçekte çıkan": " - ".join(map(str, winners)) or "—",
        "Katman havuz isabet": len(set(target_pool_nums) & set(winners)),
        "10'lu sayıları": " - ".join(map(str, coupon_nums)) or "—",
    })
lab_df = pd.DataFrame(lab_rows)
st.dataframe(lab_df, use_container_width=True, hide_index=True)

k1,k2,k3,k4 = st.columns(4)
k1.metric("Gerçek20 havuz isabet", int(qr["pool20_hits"]))
k2.metric("10'lu kupon isabet", int(qr["coupon10_hits"]))
k3.metric("Katman kota MAE", f"{float(qr['quota_mae']):.2f}")
k4.metric("Tüm katmanlar ±1", "EVET" if bool(qr["quota_all_within1"]) else "HAYIR")

st.write("**Gerçek 20:** " + " - ".join(map(str, sorted(actual_set))))
st.write("**Hedef-öncesi 20'lik katman havuzu:** " + " - ".join(map(str, sorted(pool20_set))))
st.write("**Hedef-öncesi 10'lu kupon:** " + " - ".join(map(str, sorted(coupon10_set))))

with st.expander("Hedef çekilişten hemen önceki 80 sayının tamamı", expanded=False):
    st.dataframe(
        state80.sort_values(["Katman", "Model skor"], ascending=[True, False]),
        use_container_width=True, hide_index=True, height=620,
    )

st.markdown("#### Aynı dakika (ör. 10:42) 36 gün boyunca hangi katmanlardan sayı almış?")
same_clock = quota_log[quota_log["clock"] == qr["clock"]]
st.caption(f"{qr['clock']} için {len(same_clock)} tarihsel çekiliş bulundu.")
st.dataframe(layer_profile(same_clock), use_container_width=True, hide_index=True)

st.divider()
st.subheader("4) Walk-forward — kota gerçekten önceden tahmin edilebiliyor mu?")
if backtest.empty:
    st.info("Walk-forward için yeterli geçmiş yok.")
else:
    b1,b2,b3,b4,b5,b6 = st.columns(6)
    b1.metric("Test çekilişi", f"{len(backtest):,}".replace(",", "."))
    b2.metric("Ort. kota MAE", f"{backtest['quota_mae'].mean():.3f}")
    b3.metric("Tümü ±1", f"{100*backtest['quota_all_within1'].mean():.1f}%")
    b4.metric("20 havuz ort.", f"{backtest['pool20_hits'].mean():.3f}")
    b5.metric("10'lu ort.", f"{backtest['coupon10_hits'].mean():.3f}")
    b6.metric("10'lu max", int(backtest["coupon10_hits"].max()))

    layer_bt = []
    for layer in LAYERS:
        err = (backtest[f"actual_{layer}"] - backtest[f"pred_{layer}"]).abs()
        layer_bt.append({
            "Katman": layer,
            "Gerçek ort.": round(float(backtest[f"actual_{layer}"].mean()), 3),
            "Tahmin ort.": round(float(backtest[f"pred_{layer}"].mean()), 3),
            "MAE": round(float(err.mean()), 3),
            "±1 doğruluk": f"{100*err.le(1).mean():.1f}%",
            "Tam isabet": f"{100*err.eq(0).mean():.1f}%",
        })
    st.dataframe(pd.DataFrame(layer_bt), use_container_width=True, hide_index=True)

    dist = backtest["coupon10_hits"].value_counts().sort_index().rename_axis("İsabet").reset_index(name="Çekiliş")
    st.markdown("#### 10'lu kupon isabet dağılımı")
    st.dataframe(dist, use_container_width=True, hide_index=True)
    st.caption("Rastgele 10 sayının teorik ortalama isabeti 2,50'dir. Asıl kıyas walk-forward sonuçlarıdır.")

st.divider()
st.subheader("5) Sonraki çekiliş — katman kotası → 20'lik hedef havuzu → 10'lu kupon")
next_dt = next_draw_dt(df.iloc[-1]["dt"])

# Sonraki kota için bütün geçmişi betimleyici hafıza olarak kullan.
last12 = quota_log.tail(12)
global_sum = np.asarray([quota_log[f"actual_{x}"].sum() for x in LAYERS], dtype=float)
global_n = len(quota_log)
clock_hist = quota_log[quota_log["clock"] == next_dt.strftime("%H:%M")]
clock_sum_v = np.asarray([clock_hist[f"actual_{x}"].sum() for x in LAYERS], dtype=float)
clock_n_v = len(clock_hist)
hour_hist = quota_log[quota_log["hour"] == next_dt.hour]
hour_sum_v = np.asarray([hour_hist[f"actual_{x}"].sum() for x in LAYERS], dtype=float)
hour_n_v = len(hour_hist)
recent_v = [r for r in last12[[f"actual_{x}" for x in LAYERS]].to_numpy(dtype=float)]
raw_next, next_q = quota_prediction(global_sum, global_n, clock_sum_v, clock_n_v, hour_sum_v, hour_n_v, recent_v)

next_state, next_layers, next_scores = snapshot_state(
    df, m, pref, len(df), next_dt,
    score_override=None,
    final_stats=(stats1_df, stats2_df, stats3_df),
)
next_cap = np.bincount(next_layers, minlength=5)
next_q = fit_quota_to_capacity(next_q, next_cap, 20)
next_coupon_q = fit_quota_to_capacity(round_preserve_total(next_q*0.5, 10), next_cap, 10)
next_pool = select_by_quota(next_scores, next_layers, next_q, 20)
next_coupon = select_by_quota(next_scores, next_layers, next_coupon_q, 10)

st.write(f"**Hedef zaman:** {next_dt:%d.%m.%Y %H:%M}")
next_rows = []
for j, layer in enumerate(LAYERS):
    g = next_state[next_state["Katman"] == layer].sort_values("Model skor", ascending=False)
    next_rows.append({
        "Katman": layer,
        "80 aday": int(next_cap[j]),
        "20'lik beklenen kota": int(next_q[j]),
        "10'lu kota": int(next_coupon_q[j]),
        "Katmanın önde gelen adayları": " - ".join(map(str, g.head(max(int(next_q[j]), 5))["Sayı"].astype(int).tolist())),
    })
st.dataframe(pd.DataFrame(next_rows), use_container_width=True, hide_index=True)
st.write("**20'lik hedef havuzu:** " + " - ".join(map(str, sorted(x+1 for x in next_pool))))
st.write("**10'lu katman kuponu:** " + " - ".join(map(str, sorted(x+1 for x in next_coupon))))

with st.expander("Sonraki hedef için 80 sayının tamamı", expanded=False):
    st.dataframe(next_state.sort_values(["Katman", "Model skor"], ascending=[True, False]), use_container_width=True, hide_index=True, height=620)

st.divider()
st.subheader("6) Otomatik dışa aktarma")
export_day = lday.copy()
export_day["dt"] = pd.to_datetime(export_day["dt"]).dt.strftime("%d.%m.%Y %H:%M")
st.download_button(
    "⬇️ Seçili gün — gerçek20 katman pasaportları CSV",
    data=export_day.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"HIZLI_ON_{sel_day}_GERCEK20_KATMAN_PASAPORT.csv",
    mime="text/csv",
    use_container_width=True,
)

qexp = qday.copy()
qexp["dt"] = pd.to_datetime(qexp["dt"]).dt.strftime("%d.%m.%Y %H:%M")
st.download_button(
    "⬇️ Seçili gün — çekiliş çekiliş kota / havuz / kupon CSV",
    data=qexp.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"HIZLI_ON_{sel_day}_KATMAN_KOTA_WALKFORWARD.csv",
    mime="text/csv",
    use_container_width=True,
)

st.download_button(
    "⬇️ 36 gün — bütün katman kota sonuçları CSV",
    data=quota_log.assign(dt=pd.to_datetime(quota_log["dt"]).dt.strftime("%d.%m.%Y %H:%M")).to_csv(index=False).encode("utf-8-sig"),
    file_name="HIZLI_ON_36_GUN_KATMAN_KOTA_TUM_SONUCLAR.csv",
    mime="text/csv",
    use_container_width=True,
)

with st.expander("Motor neyi nasıl yapıyor?", expanded=False):
    st.markdown(
        """
**Katman:** Hedef çekilişten önceki son 12/24/72 çekilişin z-skorlarının birleşimidir. Beş sınıf: SOĞUK, SERİN, NÖTR, ILIK, SICAK.

**Kota tahmini:** Hedef açılmadan önce tamamlanmış çekilişlerden; genel geçmiş + son 12 çekiliş + aynı dakika geçmişi + aynı saat geçmişi ağırlıklı birleştirilir. Toplam her zaman 20'dir.

**Katman içi sayı seçimi:** Isı + yön + gap, geçiş + gap ve gün katmanı + yön sınıflarının yalnız geçmişte oluşmuş isabet oranları Bayes tipi yumuşatma ile birleştirilir. Sonuç açıldıktan sonra öğrenme hafızası güncellenir.

**20'lik hedef havuzu:** Tahmin edilen beş katman kotası kadar, her katmanın kendi içindeki en yüksek skorlu aday alınır.

**10'lu kupon:** 20'lik katman kotası yarıya ölçeklenir ve toplam 10 olacak şekilde dağıtılır; yine her katmandan kendi en yüksek skorlu sayılar alınır.

**Walk-forward:** Geçmiş bir çekilişi test ederken o çekilişin sonucu ve ondan sonraki hiçbir çekiliş model tarafından görülmez.
        """
    )

st.warning(
    "Bu çalışma istatistiksel örüntü araştırmasıdır. Çekiliş sonuçları garanti edilemez; sıcak/soğuk veya geçmiş ritim gelecekte çıkma zorunluluğu yaratmaz."
)
