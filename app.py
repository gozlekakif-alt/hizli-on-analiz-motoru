# -*- coding: utf-8 -*-
"""
HIZLI ON — HEDEF ÇEKİLİŞ 10'LU AVCISI V1

Amaç
-----
Hedef çekilişten SONRAKİ hiçbir bilgiyi kullanmadan, hedef çekiliş için
10 sayılık aday aileleri üretir ve sıralar.

Motor iki aşamalıdır:
1) Ritim / kök avı:
   - hedef günden 4 gün ve 2 gün önceki çekilişlerin ortak kökleri
   - son çekilişlerin ortak kökleri
   - yeni 10'lular da üretilebilir; daha önce tam 10/10 gelmiş olma şartı yoktur
2) Aday 10'lu puanlama:
   - yakın dönem sayı gücü
   - ikili birliktelik gücü
   - D-4 / D-2 ortak-kök desteği
   - ara yankı (son çekilişlerde 6/10, 7/10, 8/10 yaklaşmaları)
   - hedef dakikasına yakın geçmiş destek
   - aşırı kullanılmış ailelere küçük "soğukluk" filtresi

Tarihsel hedef seçilirse gerçek hedef sonucu yalnız puanlama bittikten SONRA
kontrol edilir. Böylece walk-forward mantığı korunur.

Not: Bu geçmiş örüntü araştırmasıdır; gelecek çekiliş veya kazanç garantisi vermez.
"""

from __future__ import annotations

import io
import itertools
import math
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# SAYFA / SABİTLER
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Hızlı On — Hedef Çekiliş 10'lu Avcısı",
    page_icon="🎯",
    layout="wide",
)

APP_VERSION = "HEDEF_10LU_AVCISI_V2.0_CONSENSUS"
DEFAULT_DATA_FILE = Path("veri.txt")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"

K = 10
UNIVERSE = range(1, 81)


# -----------------------------------------------------------------------------
# VERİ OKUMA
# -----------------------------------------------------------------------------
def safe_secret(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, default)
        return str(v) if v is not None else default
    except Exception:
        return default


def github_read_text(repo: str, branch: str, path: str, token: str = "") -> str:
    if token:
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github.raw+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "hizli-on-hedef-10lu",
            },
        )
    else:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-hedef-10lu"})

    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def load_data_text(uploaded=None):
    """Öncelik: yüklenen TXT > repo/yerel veri.txt > GitHub."""
    if uploaded is not None:
        raw = uploaded.getvalue()
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                return raw.decode(enc), f"Yüklenen dosya: {uploaded.name}"
            except Exception:
                pass
        return raw.decode("utf-8", errors="replace"), f"Yüklenen dosya: {uploaded.name}"

    if DEFAULT_DATA_FILE.exists():
        return DEFAULT_DATA_FILE.read_text(encoding="utf-8", errors="replace"), "GitHub/yerel veri.txt"

    repo = safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO
    branch = safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH
    path = safe_secret("GITHUB_DATA_PATH", DEFAULT_PATH) or DEFAULT_PATH
    token = safe_secret("GITHUB_TOKEN", "")

    try:
        return github_read_text(repo, branch, path, token), f"GitHub: {repo}/{path}"
    except Exception as e:
        return "", f"GitHub veri.txt okunamadı: {e}"


def _parse_nums_field(s: str):
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s)]
    return sorted(set(n for n in nums if 1 <= n <= 80))


@st.cache_data(show_spinner=False)
def parse_draws(text: str) -> pd.DataFrame:
    rows = []

    # Kompakt:
    # 51213;25.08.2026 00:02;2,4,6,...
    line_re = re.compile(
        r"^\s*#?(\d{4,})\s*[;|]\s*(\d{2}\.\d{2}\.\d{4})\s+"
        r"(\d{2}:\d{2})\s*[;|]\s*(.*?)\s*$"
    )

    for line in text.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        nums = _parse_nums_field(m.group(4))
        if len(nums) != 20:
            continue
        try:
            dt = datetime.strptime(f"{m.group(2)} {m.group(3)}", "%d.%m.%Y %H:%M")
        except Exception:
            continue
        rows.append((int(m.group(1)), dt, nums))

    # Milli Piyango kopyala-yapıştır
    if not rows:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            if "çekiliş no" not in lines[i].lower():
                i += 1
                continue

            draw = None
            m = re.search(r"(\d{4,})", lines[i])
            if m:
                draw = int(m.group(1))

            j = i + 1
            if draw is None:
                while j < min(i + 6, len(lines)):
                    m = re.fullmatch(r"\s*#?\s*(\d{4,})\s*", lines[j])
                    if m:
                        draw = int(m.group(1))
                        j += 1
                        break
                    j += 1

            if draw is None:
                i += 1
                continue

            dt = None
            while j < min(i + 12, len(lines)):
                m = re.search(
                    r"(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})",
                    lines[j],
                )
                if m:
                    try:
                        dt = datetime.strptime(
                            f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M"
                        )
                    except Exception:
                        dt = None
                    j += 1
                    break
                j += 1

            if dt is None:
                i += 1
                continue

            nums = []
            while j < len(lines) and len(nums) < 20:
                if "çekiliş no" in lines[j].lower():
                    break
                m = re.fullmatch(r"\s*(\d{1,2})\s*", lines[j])
                if m:
                    n = int(m.group(1))
                    if 1 <= n <= 80:
                        nums.append(n)
                j += 1

            nums = sorted(set(nums))
            if len(nums) == 20:
                rows.append((draw, dt, nums))

            i = max(i + 1, j)

    if not rows:
        return pd.DataFrame(columns=["draw", "dt", "nums"])

    out = pd.DataFrame(rows, columns=["draw", "dt", "nums"])
    out = (
        out.sort_values(["draw", "dt"])
        .drop_duplicates(subset=["draw"], keep="last")
        .reset_index(drop=True)
    )
    out["dt"] = pd.to_datetime(out["dt"])
    out["day"] = out["dt"].dt.date
    return out


# -----------------------------------------------------------------------------
# ZAMAN
# -----------------------------------------------------------------------------
def next_draw_time(dt: pd.Timestamp) -> pd.Timestamp:
    """
    Kullanıcının veri akışındaki Hızlı On düzeni:
    00:02..01:02, sonra 07:02..23:57, 5 dakikada bir.
    """
    dt = pd.Timestamp(dt)

    if dt.hour == 1 and dt.minute == 2:
        return dt.normalize() + pd.Timedelta(hours=7, minutes=2)

    if dt.hour == 23 and dt.minute == 57:
        return dt.normalize() + pd.Timedelta(days=1, minutes=2)

    return dt + pd.Timedelta(minutes=5)


def infer_future_target_dt(df: pd.DataFrame, target_draw: int) -> pd.Timestamp:
    last_draw = int(df.iloc[-1]["draw"])
    dt = pd.Timestamp(df.iloc[-1]["dt"])

    steps = max(0, int(target_draw) - last_draw)
    for _ in range(steps):
        dt = next_draw_time(dt)
    return dt


# -----------------------------------------------------------------------------
# TEMEL MATRİSLER
# -----------------------------------------------------------------------------
def nums_to_mask(nums):
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m


def mask_to_nums(mask: int):
    out = []
    x = int(mask)
    while x:
        lsb = x & -x
        out.append(lsb.bit_length())
        x ^= lsb
    return tuple(out)


def family_text(nums):
    return "-".join(f"{int(n):02d}" for n in nums)


def build_num_bits(pre: pd.DataFrame):
    bits = [0] * 81
    for i, nums in enumerate(pre["nums"]):
        b = 1 << i
        for n in nums:
            bits[int(n)] |= b
    return bits


def exact_support(nums, num_bits):
    b = num_bits[int(nums[0])]
    for n in nums[1:]:
        b &= num_bits[int(n)]
        if not b:
            return 0
    return int(b.bit_count())


def pair_matrix(pre: pd.DataFrame, window: int = 96):
    sub = pre.tail(max(1, int(window)))
    mat = np.zeros((81, 81), dtype=np.float32)

    if sub.empty:
        return mat

    for nums in sub["nums"]:
        ns = list(map(int, nums))
        for i in range(len(ns)):
            a = ns[i]
            for j in range(i + 1, len(ns)):
                b = ns[j]
                mat[a, b] += 1.0
                mat[b, a] += 1.0

    mat /= max(1, len(sub))
    return mat


# -----------------------------------------------------------------------------
# SAYI PUANLARI
# -----------------------------------------------------------------------------
def frequency_vector(pre: pd.DataFrame, window: int):
    sub = pre.tail(max(1, int(window)))
    v = np.zeros(81, dtype=np.float32)
    if sub.empty:
        return v

    for nums in sub["nums"]:
        for n in nums:
            v[int(n)] += 1.0
    v /= max(1, len(sub))
    return v


def day_frequency_vector(pre: pd.DataFrame, day):
    sub = pre[pre["day"] == day]
    v = np.zeros(81, dtype=np.float32)
    if sub.empty:
        return v

    for nums in sub["nums"]:
        for n in nums:
            v[int(n)] += 1.0
    v /= max(1, len(sub))
    return v


def same_minute_vector(pre: pd.DataFrame, target_dt: pd.Timestamp, days_back=14):
    lo = target_dt - pd.Timedelta(days=days_back)
    sub = pre[(pre["dt"] >= lo) & (pre["dt"].dt.minute == target_dt.minute)]

    v = np.zeros(81, dtype=np.float32)
    if sub.empty:
        return v

    for nums in sub["nums"]:
        for n in nums:
            v[int(n)] += 1.0
    v /= max(1, len(sub))
    return v


def recency_gap_vector(pre: pd.DataFrame):
    n = len(pre)
    last = np.full(81, -999999, dtype=np.int32)

    for i, nums in enumerate(pre["nums"]):
        for x in nums:
            last[int(x)] = i

    gap = np.full(81, 9999.0, dtype=np.float32)
    for x in UNIVERSE:
        if last[x] >= 0:
            gap[x] = float(n - 1 - last[x])

    # Orta gecikmeyi küçük bonusla ödüllendir:
    # 0/1 çekiliş çok sıcak, 2..8 arası "dinlenip gelme" bölgesi.
    score = np.zeros(81, dtype=np.float32)
    for x in UNIVERSE:
        g = float(gap[x])
        if g >= 9999:
            score[x] = 0.0
        else:
            score[x] = math.exp(-abs(g - 4.0) / 5.0)
    return score


def build_number_scores(pre: pd.DataFrame, target_dt: pd.Timestamp):
    f6 = frequency_vector(pre, 6)
    f12 = frequency_vector(pre, 12)
    f24 = frequency_vector(pre, 24)
    f48 = frequency_vector(pre, 48)
    f96 = frequency_vector(pre, 96)

    d2 = target_dt.date() - timedelta(days=2)
    d4 = target_dt.date() - timedelta(days=4)
    fd2 = day_frequency_vector(pre, d2)
    fd4 = day_frequency_vector(pre, d4)
    sm = same_minute_vector(pre, target_dt, days_back=14)
    gap = recency_gap_vector(pre)

    # Trend: kısa pencere uzun pencerenin üstündeyse bonus.
    trend = np.clip((f12 - f48) + 0.25, 0.0, 1.0)

    score = (
        0.16 * f6
        + 0.15 * f12
        + 0.13 * f24
        + 0.10 * f48
        + 0.06 * f96
        + 0.10 * fd2
        + 0.08 * fd4
        + 0.09 * sm
        + 0.07 * gap
        + 0.06 * trend
    )

    # 1..80 kısmını 0..1'e normalize et
    vals = score[1:81]
    lo, hi = float(vals.min()), float(vals.max())
    if hi > lo:
        score[1:81] = (vals - lo) / (hi - lo)
    else:
        score[1:81] = 0.0

    features = {
        "f6": f6,
        "f12": f12,
        "f24": f24,
        "f48": f48,
        "f96": f96,
        "fd2": fd2,
        "fd4": fd4,
        "same_minute": sm,
        "gap": gap,
        "trend": trend,
    }
    return score, features


# -----------------------------------------------------------------------------
# KÖK / ADAY ÜRETİMİ
# -----------------------------------------------------------------------------
def best_day_roots(
    pre: pd.DataFrame,
    target_dt: pd.Timestamp,
    min_root: int = 6,
    max_roots: int = 80,
):
    """
    D-4 ve D-2 günlerindeki çekiliş çiftlerinden en güçlü ortak kökleri çıkarır.
    Aynı 10'lunun geçmişte tam oluşması şart değildir.
    """
    d4 = target_dt.date() - timedelta(days=4)
    d2 = target_dt.date() - timedelta(days=2)

    a = pre[pre["day"] == d4]
    b = pre[pre["day"] == d2]

    roots = []
    if a.empty or b.empty:
        return roots

    tmin = target_dt.hour * 60 + target_dt.minute

    for _, ra in a.iterrows():
        sa = set(map(int, ra["nums"]))
        ma = pd.Timestamp(ra["dt"]).hour * 60 + pd.Timestamp(ra["dt"]).minute

        for _, rb in b.iterrows():
            inter = tuple(sorted(sa.intersection(map(int, rb["nums"]))))
            if len(inter) < min_root:
                continue

            mb = pd.Timestamp(rb["dt"]).hour * 60 + pd.Timestamp(rb["dt"]).minute

            # Büyük kök + hedef saate yakınlık
            clock_bonus = 1.0 / (1.0 + min(abs(ma - tmin), 1440 - abs(ma - tmin)) / 60.0)
            clock_bonus += 1.0 / (1.0 + min(abs(mb - tmin), 1440 - abs(mb - tmin)) / 60.0)

            root_score = float(len(inter)) + 0.35 * clock_bonus
            roots.append((root_score, inter, int(ra["draw"]), int(rb["draw"])))

    roots.sort(key=lambda x: (-x[0], -len(x[1]), x[2], x[3]))

    # Aynı kökü tekilleştir
    seen = set()
    out = []
    for item in roots:
        root = item[1]
        if root in seen:
            continue
        seen.add(root)
        out.append(item)
        if len(out) >= max_roots:
            break

    return out


def recent_roots(pre: pd.DataFrame, min_root=6, lookback=30, max_roots=60):
    """
    Son çekilişler arasındaki güçlü kesişimleri ek aday kökü olarak kullanır.
    """
    sub = pre.tail(max(2, int(lookback))).reset_index(drop=True)
    roots = []

    for i in range(len(sub)):
        si = set(map(int, sub.iloc[i]["nums"]))
        for j in range(i + 1, len(sub)):
            inter = tuple(sorted(si.intersection(map(int, sub.iloc[j]["nums"]))))
            if len(inter) >= min_root:
                # Yakın iki çekiliş biraz daha fazla puan
                dist = j - i
                score = float(len(inter)) + 0.30 / max(1, dist)
                roots.append(
                    (
                        score,
                        inter,
                        int(sub.iloc[i]["draw"]),
                        int(sub.iloc[j]["draw"]),
                    )
                )

    roots.sort(key=lambda x: (-x[0], -len(x[1])))

    seen = set()
    out = []
    for item in roots:
        if item[1] in seen:
            continue
        seen.add(item[1])
        out.append(item)
        if len(out) >= max_roots:
            break

    return out


def partial_score(nums, num_score, pmat):
    if not nums:
        return 0.0

    s = float(np.mean([num_score[n] for n in nums]))
    if len(nums) >= 2:
        ps = []
        for a, b in itertools.combinations(nums, 2):
            ps.append(float(pmat[a, b]))
        pair = float(np.mean(ps)) if ps else 0.0
    else:
        pair = 0.0

    return s + 0.45 * pair


def complete_root_to_10(root, pool, num_score, pmat, beam_width=30):
    """
    Kök 10'dan küçükse güçlü sayılarla deterministik beam-search ile tamamlar.
    Kök 10'dan büyükse kökün içindeki en güçlü 10'lu alt aileleri seçer.
    """
    root = tuple(sorted(set(map(int, root))))

    if len(root) == 10:
        return [root]

    if len(root) > 10:
        # Büyük kökte bütün C(n,10) yerine en iyi beam
        source = list(root)
        states = [((), 0.0)]
        for _ in range(10):
            nxt = {}
            for part, _ in states:
                last = part[-1] if part else 0
                for n in source:
                    if n <= last:
                        continue
                    cand = part + (n,)
                    sc = partial_score(cand, num_score, pmat)
                    if cand not in nxt or sc > nxt[cand]:
                        nxt[cand] = sc
            states = sorted(nxt.items(), key=lambda x: -x[1])[:beam_width]
        return [x[0] for x in states]

    missing = 10 - len(root)
    available = [n for n in pool if n not in root]

    states = [(root, partial_score(root, num_score, pmat))]
    for _ in range(missing):
        nxt = {}
        for part, _ in states:
            for n in available:
                if n in part:
                    continue
                cand = tuple(sorted(part + (n,)))
                if len(cand) != len(part) + 1:
                    continue
                sc = partial_score(cand, num_score, pmat)
                if cand not in nxt or sc > nxt[cand]:
                    nxt[cand] = sc
        states = sorted(nxt.items(), key=lambda x: -x[1])[:beam_width]
        if not states:
            break

    return [x[0] for x in states if len(x[0]) == 10]


def global_beam_candidates(num_score, pmat, pool_size=24, beam_width=350):
    pool = sorted(
        range(1, 81),
        key=lambda n: (-float(num_score[n]), n),
    )[: int(pool_size)]

    states = [((), 0.0)]

    for _ in range(10):
        nxt = {}
        for part, _ in states:
            last = part[-1] if part else 0
            for n in pool:
                if n <= last:
                    continue
                cand = part + (n,)
                sc = partial_score(cand, num_score, pmat)
                if cand not in nxt or sc > nxt[cand]:
                    nxt[cand] = sc

        states = sorted(nxt.items(), key=lambda x: -x[1])[: int(beam_width)]
        if not states:
            break

    return [x[0] for x in states if len(x[0]) == 10]


def generate_candidates(pre, target_dt, num_score, pmat, settings):
    pool = sorted(
        range(1, 81),
        key=lambda n: (-float(num_score[n]), n),
    )[: settings["pool_size"]]

    candidates = set()
    provenance = defaultdict(set)

    # D-4 / D-2 kökleri
    day_roots = best_day_roots(
        pre,
        target_dt,
        min_root=settings["min_root"],
        max_roots=settings["max_day_roots"],
    )

    for root_score, root, d4draw, d2draw in day_roots:
        completed = complete_root_to_10(
            root,
            pool,
            num_score,
            pmat,
            beam_width=settings["root_beam"],
        )
        for fam in completed:
            candidates.add(fam)
            provenance[fam].add(f"D4-D2 kök({len(root)}) #{d4draw}/#{d2draw}")

    # Son çekiliş kökleri
    rec_roots = recent_roots(
        pre,
        min_root=settings["min_root"],
        lookback=settings["recent_root_lookback"],
        max_roots=settings["max_recent_roots"],
    )

    for root_score, root, d1, d2 in rec_roots:
        completed = complete_root_to_10(
            root,
            pool,
            num_score,
            pmat,
            beam_width=max(10, settings["root_beam"] // 2),
        )
        for fam in completed:
            candidates.add(fam)
            provenance[fam].add(f"yakın kök({len(root)}) #{d1}/#{d2}")

    # Kökten bağımsız yeni aileler
    for fam in global_beam_candidates(
        num_score,
        pmat,
        pool_size=settings["pool_size"],
        beam_width=settings["global_beam"],
    ):
        candidates.add(fam)
        provenance[fam].add("genel beam")

    return sorted(candidates), provenance, day_roots, rec_roots


# -----------------------------------------------------------------------------
# AİLE PUANLAMA
# -----------------------------------------------------------------------------
def overlaps_for_draws(fam_set, sub: pd.DataFrame):
    if sub.empty:
        return []
    return [len(fam_set.intersection(map(int, nums))) for nums in sub["nums"]]


def family_pair_score(fam, pmat):
    vals = [float(pmat[a, b]) for a, b in itertools.combinations(fam, 2)]
    return float(np.mean(vals)) if vals else 0.0


def normalize_series(s: pd.Series):
    s = pd.to_numeric(s, errors="coerce").fillna(0.0)
    lo, hi = float(s.min()), float(s.max())
    if hi <= lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def score_candidates(
    pre: pd.DataFrame,
    target_dt: pd.Timestamp,
    candidates,
    provenance,
    num_score,
    pmat,
    num_bits,
):
    d2 = target_dt.date() - timedelta(days=2)
    d4 = target_dt.date() - timedelta(days=4)

    day2 = pre[pre["day"] == d2]
    day4 = pre[pre["day"] == d4]

    last12 = pre.tail(12)
    last24 = pre.tail(24)
    last48 = pre.tail(48)

    same_min = pre[
        (pre["dt"] >= target_dt - pd.Timedelta(days=14))
        & (pre["dt"].dt.minute == target_dt.minute)
    ]

    rows = []

    for fam in candidates:
        fs = set(fam)

        base = float(np.mean([num_score[n] for n in fam]))
        pair = family_pair_score(fam, pmat)

        o12 = overlaps_for_draws(fs, last12)
        o24 = overlaps_for_draws(fs, last24)
        o48 = overlaps_for_draws(fs, last48)

        max12 = max(o12) if o12 else 0
        max24 = max(o24) if o24 else 0

        c6 = sum(x >= 6 for x in o48)
        c7 = sum(x >= 7 for x in o48)
        c8 = sum(x >= 8 for x in o48)

        od2 = overlaps_for_draws(fs, day2)
        od4 = overlaps_for_draws(fs, day4)
        d2max = max(od2) if od2 else 0
        d4max = max(od4) if od4 else 0

        bridge = min(d2max, d4max) / 10.0 if od2 and od4 else 0.0
        day_avg = ((d2max + d4max) / 20.0) if (od2 or od4) else 0.0

        osm = overlaps_for_draws(fs, same_min)
        minute_max = max(osm) if osm else 0

        support = exact_support(fam, num_bits)
        # "Soğuk" bonus: hiç/az tam oluşmuş aileyi hafifçe destekle.
        cold = 1.0 / (1.0 + support)

        # Aynı aile D-4 ve D-2'de tam 10/10 olduysa ayrıca görünür olsun.
        exact_d2 = int(d2max == 10)
        exact_d4 = int(d4max == 10)
        repeat_watch = int(exact_d2 and exact_d4)

        # Ara yankı: 6/7/8 kümelenmesi.
        echo_raw = 0.10 * c6 + 0.28 * c7 + 0.65 * c8 + 0.15 * max12 + 0.08 * max24

        rows.append(
            {
                "Aile": family_text(fam),
                "_fam": fam,
                "Kaynak": " | ".join(sorted(provenance.get(fam, {"-"}))),
                "Sayi_Gucu": base,
                "Ikili_Guc": pair,
                "Echo_Raw": echo_raw,
                "Son12_Max": max12,
                "Son24_Max": max24,
                "Son48_6plus": c6,
                "Son48_7plus": c7,
                "Son48_8plus": c8,
                "D4_Max": d4max,
                "D2_Max": d2max,
                "D4_D2_Kopru": bridge,
                "Gun_Ort": day_avg,
                "Ayni_Dakika_Max": minute_max,
                "Gecmis_Tam10": support,
                "Sogukluk": cold,
                "D4_Tam10": exact_d4,
                "D2_Tam10": exact_d2,
                "Tekrar_Alarmi": repeat_watch,
            }
        )

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)

    # Normalize
    for col in [
        "Sayi_Gucu",
        "Ikili_Guc",
        "Echo_Raw",
        "D4_D2_Kopru",
        "Gun_Ort",
        "Ayni_Dakika_Max",
        "Sogukluk",
    ]:
        out[f"N_{col}"] = normalize_series(out[col])

    # Şeffaf puan:
    out["Skor"] = (
        0.24 * out["N_Sayi_Gucu"]
        + 0.19 * out["N_Ikili_Guc"]
        + 0.20 * out["N_Echo_Raw"]
        + 0.17 * out["N_D4_D2_Kopru"]
        + 0.08 * out["N_Gun_Ort"]
        + 0.07 * out["N_Ayni_Dakika_Max"]
        + 0.05 * out["N_Sogukluk"]
        + 0.06 * out["Tekrar_Alarmi"]
    )

    out["Skor"] = 100.0 * out["Skor"]
    out = out.sort_values(
        ["Skor", "D4_D2_Kopru", "Son48_8plus", "Ikili_Guc"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    out.insert(0, "Sira", np.arange(1, len(out) + 1))
    return out


# -----------------------------------------------------------------------------
# TEK HEDEF MOTORU
# -----------------------------------------------------------------------------
def predict_for_target(
    df: pd.DataFrame,
    target_draw: int,
    settings: dict,
):
    actual_row = df[df["draw"] == int(target_draw)]

    if not actual_row.empty:
        target_dt = pd.Timestamp(actual_row.iloc[0]["dt"])
        pre = df[df["draw"] < int(target_draw)].copy()
        actual_nums = set(map(int, actual_row.iloc[0]["nums"]))
        historical = True
    else:
        if int(target_draw) <= int(df.iloc[0]["draw"]):
            raise ValueError("Hedef çekiliş veri aralığının öncesinde.")
        if int(target_draw) <= int(df.iloc[-1]["draw"]):
            raise ValueError("Hedef çekiliş numarası veri içinde bulunamadı.")

        target_dt = infer_future_target_dt(df, int(target_draw))
        pre = df.copy()
        actual_nums = None
        historical = False

    if len(pre) < 100:
        raise ValueError("Sağlıklı aday üretimi için hedef öncesinde en az 100 çekiliş gerekli.")

    num_score, num_features = build_number_scores(pre, target_dt)
    pmat = pair_matrix(pre, window=settings["pair_window"])
    num_bits = build_num_bits(pre)

    candidates, provenance, day_roots, rec_roots = generate_candidates(
        pre,
        target_dt,
        num_score,
        pmat,
        settings,
    )

    scored = score_candidates(
        pre,
        target_dt,
        candidates,
        provenance,
        num_score,
        pmat,
        num_bits,
    )

    if historical and not scored.empty:
        scored["Gercek_Isabet"] = scored["_fam"].apply(
            lambda fam: len(set(fam).intersection(actual_nums))
        )
    else:
        scored["Gercek_Isabet"] = np.nan

    return {
        "target_draw": int(target_draw),
        "target_dt": target_dt,
        "pre": pre,
        "historical": historical,
        "actual_nums": actual_nums,
        "scored": scored,
        "day_roots": day_roots,
        "recent_roots": rec_roots,
    }


# -----------------------------------------------------------------------------
# HIZLI WALK-FORWARD
# -----------------------------------------------------------------------------
def quick_backtest(df, settings, n_targets=12, stride=12, top_n=5):
    """
    Son bölgeden her 'stride' çekilişte bir hedef seçer.
    Her hedefte sadece öncesi kullanılır.
    """
    eligible = df.iloc[500:].copy()
    idxs = list(range(len(eligible) - 1, -1, -max(1, int(stride))))
    idxs = idxs[: int(n_targets)]
    idxs = sorted(idxs)

    rows = []
    progress = st.progress(0.0, text="Walk-forward hazırlanıyor...")

    for pos, idx in enumerate(idxs, start=1):
        row = eligible.iloc[idx]
        target_draw = int(row["draw"])

        try:
            res = predict_for_target(df, target_draw, settings)
            scored = res["scored"].head(int(top_n))
            if scored.empty:
                continue

            hits = scored["Gercek_Isabet"].astype(int).tolist()
            rows.append(
                {
                    "Hedef": target_draw,
                    "Tarih": pd.Timestamp(row["dt"]).strftime("%d.%m.%Y %H:%M"),
                    "Aday_Sayisi": len(scored),
                    "TopN_EnIyi_Isabet": max(hits),
                    "TopN_Ortalama_Isabet": float(np.mean(hits)),
                    "7plus_Adet": sum(h >= 7 for h in hits),
                    "8plus_Adet": sum(h >= 8 for h in hits),
                    "9plus_Adet": sum(h >= 9 for h in hits),
                    "10da10_Adet": sum(h == 10 for h in hits),
                }
            )
        except Exception:
            pass

        progress.progress(
            pos / max(1, len(idxs)),
            text=f"Walk-forward: {pos}/{len(idxs)} hedef",
        )

    return pd.DataFrame(rows)



# -----------------------------------------------------------------------------
# FİKİR BİRLİĞİ / FİNAL SIKIŞTIRMA
# -----------------------------------------------------------------------------
def build_consensus_final(
    res,
    settings,
    consensus_top_n=20,
    lock_ratio=0.80,
):
    """
    Ham aday listesini 5-10 final 10'luya sıkıştırır.

    1) İlk N adayda her sayının görünme oranını hesaplar.
    2) Eşik üstündeki sayıları çekirdek yapar.
    3) Çekirdeği en az 2, en fazla 6 sayıda tutar.
    4) Toplam 11 sayılık fikir-birliği havuzu kurar.
    5) Final kolonları orijinal motorla tekrar puanlar.
    6) Motor skoru + fikir-birliği skorunu birleştirir.
    """
    scored = res["scored"]
    if scored is None or scored.empty:
        return {
            "final": pd.DataFrame(),
            "core": [],
            "pool": [],
            "freq_df": pd.DataFrame(),
            "used_top_n": 0,
        }

    top_n = min(int(consensus_top_n), len(scored))
    top = scored.head(top_n).copy()

    counts = defaultdict(int)
    score_sum = defaultdict(float)

    for _, row in top.iterrows():
        fam = tuple(row["_fam"])
        s = float(row["Skor"])
        for n in fam:
            counts[int(n)] += 1
            score_sum[int(n)] += s

    rank_rows = []
    for n in range(1, 81):
        c = int(counts.get(n, 0))
        if c <= 0:
            continue
        rank_rows.append(
            {
                "Sayi": n,
                "Adet": c,
                "Oran": c / max(1, top_n),
                "Aday_Skor_Ort": score_sum[n] / c,
            }
        )

    freq_df = pd.DataFrame(rank_rows)
    if freq_df.empty:
        return {
            "final": pd.DataFrame(),
            "core": [],
            "pool": [],
            "freq_df": pd.DataFrame(),
            "used_top_n": top_n,
        }

    freq_df = freq_df.sort_values(
        ["Adet", "Aday_Skor_Ort", "Sayi"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    core = freq_df[freq_df["Oran"] >= float(lock_ratio)]["Sayi"].astype(int).tolist()
    core = core[:6]

    if len(core) < 2:
        core = freq_df.head(2)["Sayi"].astype(int).tolist()

    core = sorted(set(core))

    total_pool_size = 11
    ranked_nums = freq_df["Sayi"].astype(int).tolist()

    pool = list(core)
    for n in ranked_nums:
        if n not in pool:
            pool.append(n)
        if len(pool) >= total_pool_size:
            break

    pool = pool[:total_pool_size]

    need = 10 - len(core)
    extras = [n for n in pool if n not in core]

    final_fams = []
    if need < 0:
        for comb in itertools.combinations(core, 10):
            final_fams.append(tuple(sorted(comb)))
    elif need == 0:
        final_fams = [tuple(sorted(core))]
    elif len(extras) >= need:
        for comb in itertools.combinations(extras, need):
            final_fams.append(tuple(sorted(tuple(core) + tuple(comb))))

    if len(final_fams) < 5:
        expanded_pool = list(pool)
        for n in ranked_nums:
            if n not in expanded_pool:
                expanded_pool.append(n)

            extras2 = [x for x in expanded_pool if x not in core]
            if len(extras2) >= need:
                final_fams = [
                    tuple(sorted(tuple(core) + tuple(c)))
                    for c in itertools.combinations(extras2, need)
                ]

            if len(final_fams) >= 5 or len(expanded_pool) >= 13:
                pool = expanded_pool
                break

    def consensus_raw(fam):
        vals = [counts.get(int(n), 0) / max(1, top_n) for n in fam]
        return float(sum(vals) / len(vals))

    final_fams = sorted(
        set(final_fams),
        key=lambda fam: (-consensus_raw(fam), fam),
    )[:40]

    if not final_fams:
        return {
            "final": pd.DataFrame(),
            "core": core,
            "pool": pool,
            "freq_df": freq_df,
            "used_top_n": top_n,
        }

    pre = res["pre"]
    target_dt = res["target_dt"]

    num_score, _ = build_number_scores(pre, target_dt)
    pmat = pair_matrix(pre, window=settings["pair_window"])
    num_bits = build_num_bits(pre)

    prov = defaultdict(set)
    for fam in final_fams:
        prov[fam].add("ilk adaylar fikir-birliği")

    final = score_candidates(
        pre=pre,
        target_dt=target_dt,
        candidates=final_fams,
        provenance=prov,
        num_score=num_score,
        pmat=pmat,
        num_bits=num_bits,
    )

    if final.empty:
        return {
            "final": final,
            "core": core,
            "pool": pool,
            "freq_df": freq_df,
            "used_top_n": top_n,
        }

    final["Fikir_Birligi"] = final["_fam"].apply(consensus_raw)
    final["Cekirdek_Tam"] = final["_fam"].apply(
        lambda fam: int(set(core).issubset(set(fam)))
    )

    final["Final_Skor"] = (
        0.65 * final["Skor"]
        + 35.0 * final["Fikir_Birligi"]
    )

    final = final.sort_values(
        ["Final_Skor", "Fikir_Birligi", "Skor"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    desired = min(10, max(5, 11 - len(core)))
    final = final.head(desired).copy()
    final["Final_Sira"] = range(1, len(final) + 1)

    if res["historical"] and res["actual_nums"] is not None:
        actual = set(map(int, res["actual_nums"]))
        final["Gercek_Isabet"] = final["_fam"].apply(
            lambda fam: len(set(fam).intersection(actual))
        )
    else:
        final["Gercek_Isabet"] = np.nan

    return {
        "final": final,
        "core": core,
        "pool": pool,
        "freq_df": freq_df,
        "used_top_n": top_n,
    }


def build_consensus_txt(res, consensus):
    final = consensus["final"]
    core = consensus["core"]
    pool = consensus["pool"]

    lines = []
    lines.append("=" * 118)
    lines.append("HIZLI ON — FİKİR BİRLİĞİ FİNAL 10'LULAR")
    lines.append("=" * 118)
    lines.append(f"APP: {APP_VERSION}")
    lines.append(f"Hedef: #{res['target_draw']} | {res['target_dt']:%d.%m.%Y %H:%M}")
    lines.append(f"Fikir birliği ilk aday sayısı: {consensus['used_top_n']}")
    lines.append("Kilit çekirdek: " + "-".join(f"{n:02d}" for n in core))
    lines.append("Final sayı havuzu: " + "-".join(f"{n:02d}" for n in pool))
    lines.append(f"Final kolon sayısı: {len(final)}")
    lines.append("")
    lines.append(
        "KURAL: Final kolonlar hedef sonucu görülmeden oluşturulur. "
        "Tarihsel hedefte gerçek isabet sıralamadan sonra eklenir."
    )
    lines.append("")

    if final.empty:
        lines.append("Final kolon üretilemedi.")
        return "\n".join(lines)

    for _, r in final.iterrows():
        hit = ""
        if pd.notna(r.get("Gercek_Isabet", np.nan)):
            hit = f" | gerçek={int(r['Gercek_Isabet'])}/10"

        lines.append(
            f"{int(r['Final_Sira']):02d}. {r['Aile']} "
            f"| final_skor={r['Final_Skor']:.2f} "
            f"| fikir_birliği=%{100*r['Fikir_Birligi']:.1f} "
            f"| motor={r['Skor']:.2f}{hit}"
        )

    lines.append("")
    lines.append("UYARI: Geçmiş örüntü araştırmasıdır; gelecek çekiliş veya kazanç garantisi vermez.")
    return "\n".join(lines)


def quick_backtest_consensus(df, settings, n_targets=12, stride=12, consensus_top_n=20):
    """
    Tarihsel hedeflerde ham adayları üretir, sonra fikir-birliği motoruyla
    5-10 final kolona sıkıştırır.
    """
    eligible = df.iloc[500:].copy()
    idxs = list(range(len(eligible) - 1, -1, -max(1, int(stride))))
    idxs = idxs[: int(n_targets)]
    idxs = sorted(idxs)

    rows = []
    progress = st.progress(0.0, text="V2 consensus walk-forward hazırlanıyor...")

    for pos, idx in enumerate(idxs, start=1):
        row = eligible.iloc[idx]
        target_draw = int(row["draw"])

        try:
            res = predict_for_target(df, target_draw, settings)
            con = build_consensus_final(
                res,
                settings,
                consensus_top_n=int(consensus_top_n),
                lock_ratio=0.80,
            )
            final = con["final"]
            if final.empty:
                continue

            hits = final["Gercek_Isabet"].astype(int).tolist()
            rows.append(
                {
                    "Hedef": target_draw,
                    "Tarih": pd.Timestamp(row["dt"]).strftime("%d.%m.%Y %H:%M"),
                    "Cekirdek": "-".join(f"{n:02d}" for n in con["core"]),
                    "Final_Kolon": len(final),
                    "EnIyi_Isabet": max(hits),
                    "Ort_Isabet": float(np.mean(hits)),
                    "6plus": sum(h >= 6 for h in hits),
                    "7plus": sum(h >= 7 for h in hits),
                    "8plus": sum(h >= 8 for h in hits),
                    "9plus": sum(h >= 9 for h in hits),
                    "10da10": sum(h == 10 for h in hits),
                }
            )
        except Exception:
            pass

        progress.progress(
            pos / max(1, len(idxs)),
            text=f"V2 consensus walk-forward: {pos}/{len(idxs)} hedef",
        )

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# RAPOR
# -----------------------------------------------------------------------------
def build_txt_report(res, top_n=20):
    scored = res["scored"].head(int(top_n))
    lines = []
    lines.append("=" * 118)
    lines.append("HIZLI ON — HEDEF ÇEKİLİŞ 10'LU AVCISI")
    lines.append("=" * 118)
    lines.append(f"APP: {APP_VERSION}")
    lines.append(f"Hedef çekiliş: #{res['target_draw']}")
    lines.append(f"Hedef zaman: {res['target_dt']:%d.%m.%Y %H:%M}")
    lines.append(f"Hedef öncesi kullanılan çekiliş: {len(res['pre'])}")
    lines.append(f"Tarihsel kontrol: {'EVET' if res['historical'] else 'HAYIR / CANLI HEDEF'}")
    lines.append("")
    lines.append(
        "KURAL: Hedef çekiliş sonucu aday üretimi ve puanlama sırasında kullanılmaz. "
        "Tarihsel hedefte gerçek isabet en son kontrol edilir."
    )
    lines.append("")
    lines.append(f"Üretilen aday aile: {len(res['scored'])}")
    lines.append(f"Gösterilen ilk: {len(scored)}")
    lines.append("")

    for _, r in scored.iterrows():
        hit = ""
        if pd.notna(r["Gercek_Isabet"]):
            hit = f" | gerçek_isabet={int(r['Gercek_Isabet'])}/10"

        lines.append(
            f"{int(r['Sira']):03d}. {r['Aile']} | skor={r['Skor']:.2f}"
            f" | D4={int(r['D4_Max'])}/10 | D2={int(r['D2_Max'])}/10"
            f" | son12_max={int(r['Son12_Max'])}/10"
            f" | 7+ yankı={int(r['Son48_7plus'])}"
            f" | geçmiş_tam10={int(r['Gecmis_Tam10'])}"
            f"{hit}"
        )
        lines.append(f"     kaynak: {r['Kaynak']}")

    if res["historical"] and res["actual_nums"] is not None:
        lines.append("")
        lines.append("GERÇEK HEDEF 20:")
        lines.append("-".join(f"{x:02d}" for x in sorted(res["actual_nums"])))

    lines.append("")
    lines.append("UYARI: Bu geçmiş örüntü araştırmasıdır; gelecek çekiliş veya kazanç garantisi vermez.")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🎯 Hızlı On — Hedef Çekiliş 10'lu Avcısı")
st.caption(
    "Hedef çekilişten önce hangi YENİ 10'lu aileler yükseliyor? "
    "D-4/D-2 kökleri + ara yankı + ikili birliktelik + son dönem hareketi."
)

with st.expander("🔒 Motorun kilitli kuralları", expanded=False):
    st.write(
        "• Hedef çekiliş sonucu aday üretirken kullanılmaz. Tarihsel hedefte sonuç en son kontrol edilir."
    )
    st.write(
        "• Aday 10'lunun daha önce tam 10/10 gelmiş olması şart değildir; motor yeni 10'lular üretebilir."
    )
    st.write(
        "• D-4 ve D-2 günlerindeki ortak kökler, son çekiliş kökleri, ara 6/10–8/10 yankıları ve ikili birliktelikler birlikte puanlanır."
    )
    st.write(
        "• Bu bir olasılık/örüntü araştırmasıdır; çekilişin rastgele doğası nedeniyle garanti üretmez."
    )

uploaded = st.file_uploader(
    "İstersen veri.txt yükle (boş bırakırsan GitHub/yerel veri.txt otomatik okunur)",
    type=["txt"],
)

text, source = load_data_text(uploaded)

if not text:
    st.error(source)
    st.stop()

df = parse_draws(text)
if df.empty:
    st.error("veri.txt bulundu ama geçerli 20 sayılık çekiliş okunamadı.")
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
b.metric("Gün", int(df["day"].nunique()))
c.metric("İlk", f"#{int(df.iloc[0]['draw'])}")
d.metric("Son", f"#{int(df.iloc[-1]['draw'])}")
st.success(f"Veri hazır — {source}")
st.caption(
    f"{df.iloc[0]['dt']:%d.%m.%Y %H:%M} → {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}"
)

st.divider()

left, right = st.columns([2, 1])

default_target = int(df.iloc[-1]["draw"]) + 1
target_draw = left.number_input(
    "🎯 Hedef çekiliş numarası",
    min_value=int(df.iloc[0]["draw"]) + 100,
    value=default_target,
    step=1,
    help=(
        "Veri içindeki eski bir çekiliş numarası girersen walk-forward kontrolü yapılır. "
        "Son çekilişten büyük bir numara girersen canlı hedef olur."
    ),
)

top_show = right.selectbox("Gösterilecek 10'lu", [5, 10, 20, 50], index=1)

g1, g2 = st.columns(2)
consensus_top_n = g1.selectbox(
    "🧠 Fikir birliği için ilk kaç aday",
    [10, 20, 30, 50],
    index=1,
    help="Varsayılan 20. İlk adaylarda en sık tekrar eden sayılar çekirdek olur.",
)
lock_ratio_pct = g2.slider(
    "🔒 Kilit çekirdek eşiği",
    min_value=60,
    max_value=100,
    value=80,
    step=5,
    help="Bir sayı ilk adayların bu yüzdesinde veya daha fazlasında varsa çekirdeğe kilitlenir.",
)

with st.expander("⚙️ Motor ayarları", expanded=False):
    e1, e2, e3, e4 = st.columns(4)
    pool_size = e1.slider("Ana sayı havuzu", 18, 32, 24, 1)
    min_root = e2.slider("Minimum ortak kök", 5, 10, 6, 1)
    root_beam = e3.slider("Kök başına aday", 10, 80, 30, 5)
    global_beam = e4.slider("Genel beam adayı", 100, 800, 350, 50)

    f1, f2, f3, f4 = st.columns(4)
    max_day_roots = f1.slider("D-4/D-2 kök sayısı", 20, 150, 80, 10)
    recent_root_lookback = f2.slider("Yakın kök geri bakış", 12, 60, 30, 6)
    max_recent_roots = f3.slider("Yakın kök sayısı", 20, 120, 60, 10)
    pair_window = f4.slider("İkili güç penceresi", 24, 192, 96, 12)

settings = {
    "pool_size": int(pool_size),
    "min_root": int(min_root),
    "root_beam": int(root_beam),
    "global_beam": int(global_beam),
    "max_day_roots": int(max_day_roots),
    "recent_root_lookback": int(recent_root_lookback),
    "max_recent_roots": int(max_recent_roots),
    "pair_window": int(pair_window),
}

run = st.button("🚀 HEDEF 10'LULARI ÜRET", type="primary", use_container_width=True)

if "hedef10_result" not in st.session_state:
    st.session_state.hedef10_result = None

if run:
    with st.spinner("Hedef öncesi veri taranıyor; 10'lu adaylar kuruluyor..."):
        try:
            st.session_state.hedef10_result = predict_for_target(
                df,
                int(target_draw),
                settings,
            )
        except Exception as e:
            st.error(str(e))
            st.session_state.hedef10_result = None

res = st.session_state.hedef10_result

if res is not None:
    st.divider()
    st.subheader(f"🎯 Hedef #{res['target_draw']} — {res['target_dt']:%d.%m.%Y %H:%M}")

    scored = res["scored"]
    if scored.empty:
        st.warning("Aday üretilemedi. Motor ayarlarında minimum kökü düşür.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Üretilen aday", f"{len(scored):,}".replace(",", "."))
        m2.metric("D-4/D-2 kökü", len(res["day_roots"]))
        m3.metric("Yakın dönem kökü", len(res["recent_roots"]))

        if res["historical"]:
            best_hit = int(scored.head(int(top_show))["Gercek_Isabet"].max())
            m4.metric(f"İlk {top_show} en iyi isabet", f"{best_hit}/10")
        else:
            m4.metric("Mod", "CANLI HEDEF")

        show_cols = [
            "Sira",
            "Aile",
            "Skor",
            "D4_Max",
            "D2_Max",
            "Son12_Max",
            "Son48_7plus",
            "Son48_8plus",
            "Gecmis_Tam10",
            "Tekrar_Alarmi",
            "Kaynak",
        ]

        if res["historical"]:
            show_cols.insert(3, "Gercek_Isabet")

        view = scored.head(int(top_show))[show_cols].copy()
        view["Skor"] = view["Skor"].round(2)

        st.dataframe(view, use_container_width=True, hide_index=True, height=520)

        if res["historical"]:
            actual_txt = " - ".join(f"{x:02d}" for x in sorted(res["actual_nums"]))
            st.info(f"Gerçek hedef 20: **{actual_txt}**")

            top = scored.head(int(top_show))
            dist = top["Gercek_Isabet"].value_counts().sort_index(ascending=False)
            dist_txt = " · ".join(f"{int(k)}/10: {int(v)} aday" for k, v in dist.items())
            st.caption(f"İlk {top_show} isabet dağılımı: {dist_txt}")

        report = build_txt_report(res, top_n=max(20, int(top_show)))
        csv_out = scored.drop(columns=["_fam"], errors="ignore").to_csv(index=False)

        dl1, dl2 = st.columns(2)
        dl1.download_button(
            "⬇️ HEDEF 10'LULAR CSV",
            data=csv_out.encode("utf-8-sig"),
            file_name=f"HEDEF_{res['target_draw']}_10LU_ADAYLAR.csv",
            mime="text/csv",
            use_container_width=True,
        )
        dl2.download_button(
            "⬇️ HEDEF 10'LULAR TXT",
            data=report.encode("utf-8"),
            file_name=f"HEDEF_{res['target_draw']}_10LU_RAPOR.txt",
            mime="text/plain",
            use_container_width=True,
        )

        # V2: Ham adayları fikir birliğiyle 5-10 finale sıkıştır
        consensus = build_consensus_final(
            res,
            settings,
            consensus_top_n=int(consensus_top_n),
            lock_ratio=float(lock_ratio_pct) / 100.0,
        )
        final10 = consensus["final"]

        st.divider()
        st.subheader("🧠 V2 — Fikir Birliğiyle Final 10'lular")

        core_txt = " - ".join(f"{n:02d}" for n in consensus["core"]) or "-"
        pool_txt = " - ".join(f"{n:02d}" for n in consensus["pool"]) or "-"

        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Kilit çekirdek", len(consensus["core"]))
        cc2.metric("Final sayı havuzu", len(consensus["pool"]))
        cc3.metric("Final 10'lu", len(final10))

        st.write(f"**Kilit çekirdek:** {core_txt}")
        st.caption(f"Final havuzu: {pool_txt}")

        if not consensus["freq_df"].empty:
            freq_view = consensus["freq_df"].head(15).copy()
            freq_view["Oran"] = (100 * freq_view["Oran"]).round(1)
            freq_view["Aday_Skor_Ort"] = freq_view["Aday_Skor_Ort"].round(2)
            freq_view = freq_view.rename(columns={"Oran": "İlk adaylarda %"})
            st.dataframe(
                freq_view[["Sayi", "Adet", "İlk adaylarda %", "Aday_Skor_Ort"]],
                use_container_width=True,
                hide_index=True,
                height=320,
            )

        if final10.empty:
            st.warning("Fikir-birliği finali üretilemedi.")
        else:
            final_cols = [
                "Final_Sira",
                "Aile",
                "Final_Skor",
                "Fikir_Birligi",
                "Skor",
                "D4_Max",
                "D2_Max",
                "Son12_Max",
                "Son48_7plus",
                "Son48_8plus",
                "Gecmis_Tam10",
            ]

            if res["historical"]:
                final_cols.insert(3, "Gercek_Isabet")

            fv = final10[final_cols].copy()
            fv["Final_Skor"] = fv["Final_Skor"].round(2)
            fv["Skor"] = fv["Skor"].round(2)
            fv["Fikir_Birligi"] = (100 * fv["Fikir_Birligi"]).round(1)

            st.dataframe(fv, use_container_width=True, hide_index=True, height=360)

            if res["historical"]:
                best_final = int(final10["Gercek_Isabet"].max())
                avg_final = float(final10["Gercek_Isabet"].mean())
                f1, f2, f3 = st.columns(3)
                f1.metric("Final en iyi isabet", f"{best_final}/10")
                f2.metric("Final ortalama", f"{avg_final:.2f}/10")
                f3.metric("7+ final kolon", int((final10["Gercek_Isabet"] >= 7).sum()))

            consensus_txt = build_consensus_txt(res, consensus)
            consensus_csv = final10.drop(columns=["_fam"], errors="ignore").to_csv(index=False)

            fd1, fd2 = st.columns(2)
            fd1.download_button(
                "⬇️ V2 FİNAL 10'LULAR CSV",
                data=consensus_csv.encode("utf-8-sig"),
                file_name=f"HEDEF_{res['target_draw']}_V2_FINAL_10LULAR.csv",
                mime="text/csv",
                use_container_width=True,
            )
            fd2.download_button(
                "⬇️ V2 FİNAL 10'LULAR TXT",
                data=consensus_txt.encode("utf-8"),
                file_name=f"HEDEF_{res['target_draw']}_V2_FINAL_10LULAR.txt",
                mime="text/plain",
                use_container_width=True,
            )

        st.subheader("🔎 İlk 5 adayın ayrıntısı")
        for _, r in scored.head(5).iterrows():
            hit = ""
            if res["historical"]:
                hit = f" · gerçek {int(r['Gercek_Isabet'])}/10"

            with st.expander(f"#{int(r['Sira'])} {r['Aile']} · skor {r['Skor']:.2f}{hit}"):
                st.write(f"**D-4 maksimum:** {int(r['D4_Max'])}/10")
                st.write(f"**D-2 maksimum:** {int(r['D2_Max'])}/10")
                st.write(f"**Son 12 çekiliş maksimum:** {int(r['Son12_Max'])}/10")
                st.write(
                    f"**Son 48 yankı:** 6+ = {int(r['Son48_6plus'])}, "
                    f"7+ = {int(r['Son48_7plus'])}, 8+ = {int(r['Son48_8plus'])}"
                )
                st.write(f"**Geçmiş tam 10/10 sayısı:** {int(r['Gecmis_Tam10'])}")
                st.write(f"**Kaynak:** {r['Kaynak']}")

st.divider()
st.subheader("🧪 Hızlı walk-forward kontrol")

bt1, bt2, bt3 = st.columns(3)
bt_targets = bt1.selectbox("Kaç tarihsel hedef", [6, 12, 18, 24], index=1)
bt_stride = bt2.selectbox("Hedef aralığı (çekiliş)", [6, 12, 24], index=1)
bt_topn = bt3.selectbox("Her hedefte ilk kaç 10'lu", [3, 5, 10], index=1)

bt_run = st.button(
    "🧪 WALK-FORWARD TESTİ ÇALIŞTIR",
    use_container_width=True,
)

if bt_run:
    bt = quick_backtest(
        df,
        settings,
        n_targets=int(bt_targets),
        stride=int(bt_stride),
        top_n=int(bt_topn),
    )

    if bt.empty:
        st.warning("Backtest sonucu üretilemedi.")
    else:
        st.dataframe(bt, use_container_width=True, hide_index=True)

        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Test hedefi", len(bt))
        q2.metric("Ort. en iyi isabet", f"{bt['TopN_EnIyi_Isabet'].mean():.2f}/10")
        q3.metric("En yüksek", f"{int(bt['TopN_EnIyi_Isabet'].max())}/10")
        q4.metric("7+ görülen hedef", int((bt["TopN_EnIyi_Isabet"] >= 7).sum()))

        st.download_button(
            "⬇️ WALK-FORWARD CSV",
            data=bt.to_csv(index=False).encode("utf-8-sig"),
            file_name="HEDEF_10LU_WALK_FORWARD.csv",
            mime="text/csv",
            use_container_width=True,
        )

st.divider()
st.subheader("🧪 V2 — Fikir Birliği Final Walk-Forward")

cw1, cw2, cw3 = st.columns(3)
cw_targets = cw1.selectbox(
    "V2 test hedefi",
    [6, 12, 18, 24],
    index=1,
    key="consensus_bt_targets",
)
cw_stride = cw2.selectbox(
    "V2 hedef aralığı",
    [6, 12, 24],
    index=1,
    key="consensus_bt_stride",
)
cw_top = cw3.selectbox(
    "V2 fikir birliği ilk N",
    [10, 20, 30],
    index=1,
    key="consensus_bt_top",
)

cw_run = st.button(
    "🧪 V2 FİNAL WALK-FORWARD ÇALIŞTIR",
    use_container_width=True,
)

if cw_run:
    cbt = quick_backtest_consensus(
        df,
        settings,
        n_targets=int(cw_targets),
        stride=int(cw_stride),
        consensus_top_n=int(cw_top),
    )

    if cbt.empty:
        st.warning("V2 walk-forward sonucu üretilemedi.")
    else:
        st.dataframe(cbt, use_container_width=True, hide_index=True)

        z1, z2, z3, z4 = st.columns(4)
        z1.metric("Test hedefi", len(cbt))
        z2.metric("Ort. en iyi", f"{cbt['EnIyi_Isabet'].mean():.2f}/10")
        z3.metric("En yüksek", f"{int(cbt['EnIyi_Isabet'].max())}/10")
        z4.metric("7+ hedef", int((cbt["EnIyi_Isabet"] >= 7).sum()))

        st.download_button(
            "⬇️ V2 WALK-FORWARD CSV",
            data=cbt.to_csv(index=False).encode("utf-8-sig"),
            file_name="HEDEF_10LU_V2_CONSENSUS_WALK_FORWARD.csv",
            mime="text/csv",
            use_container_width=True,
        )


st.caption(
    "Önemli: Hedef çekiliş sonucu puanlama sırasında kullanılmaz. "
    "Tarihsel hedeflerde Gerçek_Isabet sütunu yalnız tahminler üretildikten sonra eklenir."
)
