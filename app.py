# -*- coding: utf-8 -*-
"""
HIZLI ON — YAŞAM HARİTASI / 5'Lİ KATMANLAR / SAATLİK AİLELER V5

Amaç:
- 1–80 her sayının günün ilk çekilişinden gün sonuna kadar yaşam izini tutmak
- NEW_HOT / HOT / RESTED_HOT / COOLING / NEUTRAL / WAKING_COLD / COLD / DEEP_COLD
  katmanlarını her çekiliş sonrası yeniden hesaplamak
- Her katmanı aktivasyon indeksine göre 5'erli havuzlara bölmek
- Havuzların sonraki 1–6 çekilişte ne yaptığını ölçmek
- İlk6 (:02..:27) karakterinden, hedef sonucu kullanmadan SAATLİK AİLELER keşfetmek
- Saatlik ailelerin son6 (:32..:57) davranışlarını H1'de öğrenilmiş kümelerle H2'de test etmek
- Dakika, katman, durum geçişi, bekleme, ısınma, soğuma ve aile zincirlerini otomatik taramak
- Kupon üretmemek. Önce oyunun yaşam haritasını çıkarmak.

Not:
Bu uygulama geçmiş frekans örüntülerini ölçer; "uzun süredir çıkmadı, artık çıkmalı"
varsayımı kullanmaz. Gap yalnız betimleyici bir özelliktir.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from itertools import combinations
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st


# ============================================================
# SAYFA
# ============================================================

st.set_page_config(
    page_title="Hızlı On — Yaşam Haritası V5",
    page_icon="🧬",
    layout="wide",
)

st.title("🧬 Hızlı On — 1–80 Yaşam Haritası / 5'li Katmanlar / Saatlik Aileler V5")
st.caption(
    "Kupon üretmez • 1–80 yaşam izi • 5'li sıcak/soğuk katmanlar • "
    "ilk6 saat karakteri • saatlik aile keşfi • H1→H2 kronolojik kontrol • kontrollü GitHub kayıt"
)

FIRST3 = ("02", "07", "12")
SECOND3 = ("17", "22", "27")
FIRST6 = FIRST3 + SECOND3
LAST6 = ("32", "37", "42", "47", "52", "57")
HOUR12 = FIRST6 + LAST6

STATUS_ORDER = (
    "NEW_HOT",
    "HOT",
    "RESTED_HOT",
    "COOLING",
    "NEUTRAL",
    "WAKING_COLD",
    "COLD",
    "DEEP_COLD",
)

# Sabit eşikler. Analiz sırasında gelecek sonuçlara göre yeniden ayarlanmaz.
HOT_THR = 0.85
COLD_THR = -0.65
DEEP_THR = -1.20

RANDOM_SINGLE = 0.25
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"


# ============================================================
# YARDIMCI
# ============================================================

def hypergeom_p_ge(pool_size: int, need: int) -> float:
    """80 sayıdan 20 çekilirken havuzdan >=need isabet olasılığı."""
    den = comb(80, pool_size)
    num = 0
    for j in range(need, min(pool_size, 20) + 1):
        num += comb(20, j) * comb(60, pool_size - j)
    return num / den


def safe_pct(x):
    if pd.isna(x):
        return np.nan
    return 100.0 * float(x)


def bucket_age(x: int) -> str:
    if x <= 1:
        return "1"
    if x == 2:
        return "2"
    if x == 3:
        return "3"
    if x <= 5:
        return "4-5"
    return "6+"


def bucket_gap(x: int) -> str:
    if x <= 0:
        return "0"
    if x == 1:
        return "1"
    if x == 2:
        return "2"
    if x <= 4:
        return "3-4"
    if x <= 7:
        return "5-7"
    return "8+"


def interval_sum(prefix: np.ndarray, end_idx: int, length: int):
    """0..end_idx dahil son length çekilişin 80 vektör toplamı."""
    if end_idx < 0:
        return np.zeros(80, dtype=float), 0
    start = max(0, end_idx - length + 1)
    v = prefix[end_idx].astype(float)
    if start > 0:
        v = v - prefix[start - 1]
    return v, end_idx - start + 1


def binom_z(h, n, p=0.25, prior_n=12):
    """Küçük örnekleri yumuşatan betimleyici binom z skoru."""
    if n <= 0:
        return 0.0
    mu = n * p
    sd = math.sqrt((n + prior_n) * p * (1 - p))
    return (h - mu) / sd if sd else 0.0


# ============================================================
# VERİ OKUMA
# ============================================================

def parse_line(line: str):
    s = line.strip()
    if not s or s.startswith(("=", "#")):
        return None

    m = re.match(r"^\s*(\d+)\s*;\s*([^;]+?)\s*;\s*(.+?)\s*$", s)
    if not m:
        m = re.match(r"^\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$", s)
    if not m:
        return None

    try:
        draw_id = int(m.group(1))
        dt = pd.to_datetime(m.group(2).strip(), dayfirst=True, errors="raise")
        nums = sorted(set(int(x) for x in re.findall(r"\d+", m.group(3))))
    except Exception:
        return None

    if len(nums) != 20 or not all(1 <= n <= 80 for n in nums):
        return None
    return draw_id, pd.Timestamp(dt), tuple(nums)


@st.cache_data(show_spinner=False)
def parse_text(raw: str, digest: str):
    rows = []
    rejected = 0

    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith(("=", "#")):
            continue
        x = parse_line(line)
        if x:
            rows.append(x)
        elif re.search(r"\d", line):
            rejected += 1

    if not rows:
        raise ValueError("Geçerli çekiliş bulunamadı.")

    df = pd.DataFrame(rows, columns=["draw_id", "time", "numbers"])
    before = len(df)

    # Aynı draw_id farklı satırlarda varsa sonuncu tutulur; ayrıca aynı timestamp çakışması raporlanır.
    df = (
        df.sort_values(["time", "draw_id"])
          .drop_duplicates("draw_id", keep="last")
          .reset_index(drop=True)
    )
    duplicates = before - len(df)
    return df, rejected, duplicates


# ============================================================
# GITHUB
# ============================================================

def _secret_value(*names):
    for name in names:
        try:
            if name in st.secrets and st.secrets[name] not in (None, ""):
                return str(st.secrets[name]).strip()
        except Exception:
            pass

    try:
        gh = st.secrets["github"]
        for name in names:
            short = name.lower().replace("github_", "").replace("gh_", "")
            for key in (name, name.lower(), short):
                try:
                    if key in gh and gh[key] not in (None, ""):
                        return str(gh[key]).strip()
                except Exception:
                    pass
    except Exception:
        pass
    return ""


def github_config():
    token = _secret_value("GITHUB_TOKEN", "GH_TOKEN", "token")
    repo = _secret_value("GITHUB_REPO", "GH_REPO", "repo") or DEFAULT_REPO
    branch = _secret_value("GITHUB_BRANCH", "GH_BRANCH", "branch") or DEFAULT_BRANCH
    path = _secret_value("GITHUB_DATA_PATH", "DATA_PATH", "data_path") or DEFAULT_PATH
    return token, repo, branch, path


def github_request(url, token="", method="GET", payload=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hizli-on-yasam-v5",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(msg).get("message", msg)
        except Exception:
            pass
        raise RuntimeError(f"GitHub HTTP {e.code}: {msg}")
    except Exception as e:
        raise RuntimeError(f"GitHub bağlantı hatası: {e}")


def github_fetch_veri():
    token, repo, branch, path = github_config()
    path_q = urllib.parse.quote(path, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{path_q}?ref={urllib.parse.quote(branch, safe='')}"
    obj = github_request(url, token=token, method="GET")
    if obj.get("type") != "file":
        raise RuntimeError(f"{path} GitHub'da dosya olarak bulunamadı.")
    raw = base64.b64decode(obj.get("content", "")).decode("utf-8-sig", errors="replace")
    return raw, obj.get("sha", ""), (token, repo, branch, path)


def read_source(uploaded):
    if uploaded is not None:
        raw = uploaded.getvalue().decode("utf-8-sig", errors="replace")
        return raw, uploaded.name

    try:
        raw, sha, cfg = github_fetch_veri()
        return raw, f"github/{cfg[1]}/{cfg[3]}@{sha[:10]}"
    except Exception:
        pass

    p = Path("veri.txt")
    if p.exists():
        return p.read_text(encoding="utf-8-sig", errors="replace"), "repo/veri.txt"

    return None, None


# ============================================================
# HAM YAPIŞTIRMA + KONTROLLÜ KAYIT
# ============================================================

def parse_pasted_draws(raw_text: str):
    txt = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not txt:
        return [], ["Giriş boş."]

    # Canonical satır formatı
    canonical = []
    meaningful = [x for x in txt.splitlines() if x.strip()]
    for line in meaningful:
        x = parse_line(line)
        if x:
            canonical.append(x)
    if canonical and len(canonical) == len(meaningful):
        records = canonical
    else:
        starts = list(re.finditer(r"(?im)^\s*(?:#+\s*)?Çekiliş\s*no\s*:", txt))
        if not starts:
            return [], ["'Çekiliş no:' başlığı bulunamadı."]

        records = []
        for j, m in enumerate(starts):
            end = starts[j + 1].start() if j + 1 < len(starts) else len(txt)
            block = txt[m.start():end]

            mid = re.search(
                r"(?is)Çekiliş\s*no\s*:\s*(?:\n\s*(?:#+\s*)?)?\s*(\d+)",
                block,
            )
            mdt = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})", block)
            if not mid or not mdt:
                return [], [f"{j+1}. blokta çekiliş no veya tarih-saat okunamadı."]

            draw_id = int(mid.group(1))
            try:
                dt = pd.to_datetime(
                    mdt.group(1) + " " + mdt.group(2),
                    format="%d.%m.%Y %H:%M",
                    errors="raise",
                )
            except Exception:
                return [], [f"#{draw_id}: tarih-saat geçersiz."]

            tail = block[mdt.end():]
            tail = re.split(r"(?i)\bDetaylar\b", tail, maxsplit=1)[0]
            nums = [int(x) for x in re.findall(r"(?<!\d)\d{1,2}(?!\d)", tail)]
            records.append((draw_id, pd.Timestamp(dt), tuple(nums)))

    errors = []
    clean = []
    seen_ids = set()
    seen_times = set()

    for draw_id, dt, nums0 in records:
        nums = list(nums0)

        if draw_id in seen_ids:
            errors.append(f"#{draw_id}: aynı yapıştırmada mükerrer çekiliş no.")
        if dt in seen_times:
            errors.append(f"{dt:%d.%m.%Y %H:%M}: aynı yapıştırmada mükerrer saat.")

        seen_ids.add(draw_id)
        seen_times.add(dt)

        if len(nums) != 20:
            errors.append(f"#{draw_id}: 20 sayı yerine {len(nums)} sayı bulundu.")
            continue
        if len(set(nums)) != 20:
            errors.append(f"#{draw_id}: tekrar eden sayı var.")
            continue
        if not all(1 <= n <= 80 for n in nums):
            errors.append(f"#{draw_id}: 1–80 dışında sayı var.")
            continue
        if dt.strftime("%M") not in HOUR12:
            errors.append(f"#{draw_id}: dakika :{dt:%M}; beklenen Hızlı On dakikalarından değil.")
            continue

        clean.append((int(draw_id), dt, tuple(sorted(nums))))

    clean = sorted(clean, key=lambda x: (x[1], x[0]))
    return clean, errors


def canonical_line(record):
    draw_id, dt, nums = record
    return f"{draw_id};{dt.strftime('%d.%m.%Y %H:%M')};" + ",".join(map(str, nums))


def validate_against_remote(records, remote_raw):
    digest = hashlib.sha256(remote_raw.encode("utf-8", errors="replace")).hexdigest()
    rdf, _, _ = parse_text(remote_raw, digest)

    by_id = {
        int(r.draw_id): (pd.Timestamp(r.time), tuple(r.numbers))
        for r in rdf.itertuples(index=False)
    }
    by_time = {
        pd.Timestamp(r.time): int(r.draw_id)
        for r in rdf.itertuples(index=False)
    }

    add, skipped, conflicts = [], [], []

    for rec in records:
        draw_id, dt, nums = rec

        if draw_id in by_id:
            old_dt, old_nums = by_id[draw_id]
            if old_dt == dt and tuple(old_nums) == tuple(nums):
                skipped.append(draw_id)
            else:
                conflicts.append(f"#{draw_id}: GitHub'da aynı çekiliş no farklı veriyle kayıtlı.")
            continue

        if dt in by_time:
            conflicts.append(
                f"{dt:%d.%m.%Y %H:%M}: GitHub'da #{by_time[dt]} var; yeni kayıt #{draw_id}."
            )
            continue

        add.append(rec)

    return add, skipped, conflicts


def github_commit_records(records):
    raw, sha, cfg = github_fetch_veri()
    token, repo, branch, path = cfg

    if not token:
        return {"ok": False, "errors": ["GitHub yazma için GITHUB_TOKEN gerekli."]}

    add, skipped, conflicts = validate_against_remote(records, raw)
    if conflicts:
        return {"ok": False, "errors": conflicts, "skipped": skipped}

    if not add:
        return {
            "ok": True,
            "message": "Yeni kayıt yok; gönderilen çekilişler zaten mevcut.",
            "added": [],
            "skipped": skipped,
        }

    new_text = raw.rstrip() + "\n" + "\n".join(canonical_line(x) for x in add) + "\n"

    if len(add) == 6:
        msg = f"{add[0][1]:%d.%m.%Y} {add[0][1]:%H:%M}–{add[-1][1]:%H:%M} ilk6 eklendi"
    elif len(add) == 1:
        msg = f"#{add[0][0]} {add[0][1]:%d.%m.%Y %H:%M} canlı çekiliş eklendi"
    else:
        msg = f"{len(add)} Hızlı On çekilişi kontrollü eklendi"

    path_q = urllib.parse.quote(path, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{path_q}"

    payload = {
        "message": msg,
        "content": base64.b64encode(new_text.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": branch,
    }

    try:
        result = github_request(url, token=token, method="PUT", payload=payload)
    except Exception as e:
        return {"ok": False, "errors": [str(e)]}

    # Son kontrol: tekrar GitHub'dan oku.
    verify_raw, _, _ = github_fetch_veri()
    vd, _, _ = parse_text(
        verify_raw,
        hashlib.sha256(verify_raw.encode("utf-8", errors="replace")).hexdigest(),
    )
    vmap = {
        int(r.draw_id): (pd.Timestamp(r.time), tuple(r.numbers))
        for r in vd.itertuples(index=False)
    }

    missing = []
    for rec in add:
        if rec[0] not in vmap or vmap[rec[0]] != (rec[1], tuple(rec[2])):
            missing.append(rec[0])

    if missing:
        return {
            "ok": False,
            "errors": [f"Commit sonrası doğrulanamayan kayıtlar: {missing}"],
        }

    return {
        "ok": True,
        "message": f"{len(add)} çekiliş GitHub'a kaydedildi ve tekrar okunarak doğrulandı.",
        "added": [x[0] for x in add],
        "skipped": skipped,
        "commit": result.get("commit", {}).get("sha", "")[:10],
    }


# ============================================================
# YAŞAM DURUMU
# ============================================================

def classify_state(score, prev_score, prev_state, current_hit, delta, gap):
    """
    Gelecek sonuç kullanılmaz.
    RESTED_HOT: sıcak skor korunurken sayı en az 2 çekiliştir görünmüyorsa.
    """
    if score >= HOT_THR:
        if prev_score < HOT_THR:
            return "NEW_HOT"
        if (not current_hit) and gap >= 2:
            return "RESTED_HOT"
        return "HOT"

    if prev_score >= HOT_THR and score < HOT_THR:
        return "COOLING"

    # Soğuktan yükseliş: eski soğuk kimlik + belirgin pozitif delta.
    if prev_state in ("COLD", "DEEP_COLD") and delta >= 0.18:
        return "WAKING_COLD"
    if prev_score <= COLD_THR and delta >= 0.24:
        return "WAKING_COLD"

    if score <= DEEP_THR and gap >= 8:
        return "DEEP_COLD"
    if score <= COLD_THR:
        return "COLD"

    return "NEUTRAL"


def activation_index(score, delta, current_hit, h3, h6, n6):
    short_rate = (h6 / n6) if n6 else 0.0
    return (
        score
        + 0.45 * delta
        + 0.20 * float(current_hit)
        + 0.14 * (short_rate - 0.25)
        + 0.06 * (h3 - 0.75)
    )


# ============================================================
# SAAT KARAKTERİ
# ============================================================

def build_hour_character_rows(df):
    rows = []

    dfx = df.copy()
    dfx["date"] = dfx.time.dt.strftime("%Y-%m-%d")
    dfx["hour"] = dfx.time.dt.strftime("%H")
    dfx["minute"] = dfx.time.dt.strftime("%M")

    for (date, hour), g in dfx.groupby(["date", "hour"], sort=True):
        by_min = {r.minute: set(r.numbers) for r in g.itertuples(index=False)}

        if any(m not in by_min for m in FIRST6):
            continue

        c1 = {n: sum(n in by_min[m] for m in FIRST3) for n in range(1, 81)}
        c2 = {n: sum(n in by_min[m] for m in SECOND3) for n in range(1, 81)}
        c6 = {n: c1[n] + c2[n] for n in range(1, 81)}

        q1 = [sum(c1[n] == k for n in range(1, 81)) for k in range(4)]
        q2 = [sum(c2[n] == k for n in range(1, 81)) for k in range(4)]
        q6 = [sum(c6[n] == k for n in range(1, 81)) for k in range(7)]

        transition_counts = {
            (a, b): sum(c1[n] == a and c2[n] == b for n in range(1, 81))
            for a in range(4)
            for b in range(4)
        }

        u1 = set().union(*(by_min[m] for m in FIRST3))
        u2 = set().union(*(by_min[m] for m in SECOND3))

        zero6 = {n for n in range(1, 81) if c6[n] == 0}
        hot6 = {n for n in range(1, 81) if c6[n] >= 2}
        very_hot6 = {n for n in range(1, 81) if c6[n] >= 3}

        if q6[0] <= 12:
            zero_band = "ZERO6_LOW"
        elif q6[0] <= 16:
            zero_band = "ZERO6_MID"
        else:
            zero_band = "ZERO6_HIGH"

        row = {
            "date": date,
            "hour": hour,
            "snapshot_time": pd.Timestamp(f"{date} {hour}:27"),
            "zero6_band": zero_band,
            "zero6": q6[0],
            "first6_distinct": 80 - q6[0],
            "first3_distinct": len(u1),
            "second3_distinct": len(u2),
            "overlap_12": len(u1 & u2),
            "new_second3": len(u2 - u1),
            "lost_second3": len(u1 - u2),
            "c6_ge2": len(hot6),
            "c6_ge3": len(very_hot6),
            "q1_0": q1[0],
            "q1_1": q1[1],
            "q1_2": q1[2],
            "q1_3": q1[3],
            "q2_0": q2[0],
            "q2_1": q2[1],
            "q2_2": q2[2],
            "q2_3": q2[3],
            "q6_vector": ",".join(map(str, q6)),
        }

        for a in range(4):
            for b in range(4):
                row[f"f_{a}_{b}"] = transition_counts[(a, b)]

        # Son6 sonuçları, sadece SAAT AİLELERİNİN SONUÇ PROFİLİNİ ölçmek için.
        # Kümeyi belirlerken kullanılmaz.
        last6_complete = all(m in by_min for m in LAST6)
        row["last6_complete"] = int(last6_complete)

        if last6_complete:
            last_sets = [by_min[m] for m in LAST6]
            union_last = set().union(*last_sets)
            zero_opened = zero6 & union_last
            hot6_seen = hot6 & union_last

            row["last6_distinct"] = len(union_last)
            row["zero6_opened"] = len(zero_opened)
            row["hot6_seen"] = len(hot6_seen)
            row["zero6_max_same"] = max(len(zero6 & s) for s in last_sets)
            row["hot6_max_same"] = max(len(hot6 & s) for s in last_sets)

            # Son6 içinde tekrar eden sayılar.
            lc = Counter()
            for s in last_sets:
                lc.update(s)
            row["last6_repeat2plus"] = sum(v >= 2 for v in lc.values())
            row["last6_repeat3plus"] = sum(v >= 3 for v in lc.values())

            for m in LAST6:
                row[f"zero6_hit_{m}"] = len(zero6 & by_min[m])
                row[f"hot6_hit_{m}"] = len(hot6 & by_min[m])
        else:
            for c in (
                "last6_distinct",
                "zero6_opened",
                "hot6_seen",
                "zero6_max_same",
                "hot6_max_same",
                "last6_repeat2plus",
                "last6_repeat3plus",
            ):
                row[c] = np.nan
            for m in LAST6:
                row[f"zero6_hit_{m}"] = np.nan
                row[f"hot6_hit_{m}"] = np.nan

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# K-MEANS — SADECE İLK6 ÖZELLİKLERİ
# ============================================================

HOUR_FEATURES = [
    "zero6",
    "first6_distinct",
    "first3_distinct",
    "second3_distinct",
    "overlap_12",
    "new_second3",
    "lost_second3",
    "c6_ge2",
    "c6_ge3",
    "q1_0",
    "q1_2",
    "q1_3",
    "q2_0",
    "q2_2",
    "q2_3",
    "f_0_0",
    "f_0_1",
    "f_1_0",
    "f_1_1",
    "f_1_2",
    "f_2_1",
    "f_2_2",
]


def _kmeans_fit(X, k=6, seed=42, iters=60):
    rng = np.random.default_rng(seed)
    n = len(X)

    if n < k:
        k = max(1, n)

    # Uzak nokta başlatması: ilk merkez rastgele, sonrakiler en uzaklardan.
    centers = [X[rng.integers(0, n)].copy()]
    for _ in range(1, k):
        d2 = np.min(
            np.stack([np.sum((X - c) ** 2, axis=1) for c in centers], axis=1),
            axis=1,
        )
        idx = int(np.argmax(d2))
        centers.append(X[idx].copy())

    centers = np.stack(centers, axis=0)

    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        dist = np.stack(
            [np.sum((X - c) ** 2, axis=1) for c in centers],
            axis=1,
        )
        new_labels = np.argmin(dist, axis=1)

        new_centers = centers.copy()
        for j in range(k):
            mask = new_labels == j
            if mask.any():
                new_centers[j] = X[mask].mean(axis=0)

        if np.array_equal(new_labels, labels) and np.allclose(new_centers, centers):
            labels = new_labels
            centers = new_centers
            break

        labels = new_labels
        centers = new_centers

    return labels, centers


def fit_hour_families(hours: pd.DataFrame, requested_k=6):
    if hours.empty:
        return hours.copy(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    x = hours.sort_values("snapshot_time").reset_index(drop=True).copy()

    # İlk yarıda aile yapısını öğren, ikinci yarıya aynı merkezlerle uygula.
    split_idx = max(1, len(x) // 2)
    train = x.iloc[:split_idx].copy()

    k = min(requested_k, max(2, len(train) // 25)) if len(train) >= 50 else min(3, len(train))
    k = max(1, k)

    mu = train[HOUR_FEATURES].astype(float).mean().values
    sd = train[HOUR_FEATURES].astype(float).std(ddof=0).replace(0, 1).fillna(1).values

    Xtrain = (train[HOUR_FEATURES].astype(float).values - mu) / sd
    tr_labels, centers = _kmeans_fit(Xtrain, k=k, seed=42)

    Xall = (x[HOUR_FEATURES].astype(float).values - mu) / sd
    dist = np.stack(
        [np.sum((Xall - c) ** 2, axis=1) for c in centers],
        axis=1,
    )
    all_labels = np.argmin(dist, axis=1)

    # Aile numaralarını H1 merkezindeki ZERO6 ortalamasına göre sırala:
    train_tmp = train.copy()
    train_tmp["_cluster"] = tr_labels
    order = (
        train_tmp.groupby("_cluster")["zero6"]
        .mean()
        .sort_values()
        .index
        .tolist()
    )
    mapping = {old: i + 1 for i, old in enumerate(order)}

    x["family_id"] = [mapping[int(z)] for z in all_labels]
    x["family"] = x.family_id.map(lambda z: f"F{z}")
    x["split"] = np.where(np.arange(len(x)) < split_idx, "H1", "H2")

    # H1 profiline göre açıklayıcı tag.
    tags = {}
    global_mean = train[HOUR_FEATURES].mean()
    global_sd = train[HOUR_FEATURES].std(ddof=0).replace(0, 1)

    for fam, g in x[x.split == "H1"].groupby("family"):
        z = (g[HOUR_FEATURES].mean() - global_mean) / global_sd

        if z["zero6"] >= 0.55:
            tag = "DAR / ZERO6_YUKSEK"
        elif z["overlap_12"] >= 0.55:
            tag = "TASIMA_DEVAM"
        elif z["new_second3"] >= 0.55:
            tag = "ROTASYON_YENI"
        elif z["c6_ge2"] >= 0.55:
            tag = "TEKRAR_YOGUN"
        elif (z["q1_3"] + z["q2_3"]) >= 0.8:
            tag = "TEPE_YOGUN"
        else:
            tag = "DENGELI_KARMA"

        tags[fam] = tag

    x["family_tag"] = x.family.map(tags).fillna("KARMA")

    # Aile özetleri
    family_summary = (
        x.groupby(["family", "family_tag", "split"], observed=True)
        .agg(
            n=("family", "size"),
            zero6_mean=("zero6", "mean"),
            overlap_mean=("overlap_12", "mean"),
            new2_mean=("new_second3", "mean"),
            c6ge2_mean=("c6_ge2", "mean"),
            zero6_opened_mean=("zero6_opened", "mean"),
            zero6_max_same_mean=("zero6_max_same", "mean"),
            hot6_seen_mean=("hot6_seen", "mean"),
            last6_distinct_mean=("last6_distinct", "mean"),
            last6_repeat2plus_mean=("last6_repeat2plus", "mean"),
        )
        .reset_index()
    )

    # Aynı saat-of-day'de aile tekrarı var mı?
    clock_counts = (
        x.groupby(["hour", "family"], observed=True)
        .size()
        .reset_index(name="n")
    )
    totals = clock_counts.groupby("hour").n.transform("sum")
    clock_counts["share_pct"] = 100 * clock_counts.n / totals
    clock_affinity = (
        clock_counts.sort_values(["hour", "share_pct"], ascending=[True, False])
        .groupby("hour", as_index=False)
        .first()
        .rename(columns={"family": "dominant_family", "n": "dominant_n", "share_pct": "dominant_share_pct"})
    )

    # Aile zinciri: aynı gün ardışık saatler.
    trans = Counter()
    trans_total = Counter()
    for date, g in x.groupby("date", sort=True):
        gg = g.sort_values("snapshot_time")
        prev = None
        for r in gg.itertuples(index=False):
            if prev is not None:
                key = (prev.family, r.family)
                trans[key] += 1
                trans_total[prev.family] += 1
            prev = r

    trans_rows = []
    for (a, b), n in trans.items():
        trans_rows.append({
            "from_family": a,
            "to_family": b,
            "n": n,
            "pct_from": 100 * n / max(1, trans_total[a]),
        })
    family_transitions = pd.DataFrame(trans_rows)
    if not family_transitions.empty:
        family_transitions = family_transitions.sort_values(
            ["from_family", "pct_from"],
            ascending=[True, False],
        )

    return x, family_summary, clock_affinity, family_transitions


# ============================================================
# ANA YAŞAM ANALİZİ
# ============================================================

@st.cache_data(show_spinner=False)
def analyze_all(serial_rows, digest, requested_k=6):
    """
    serial_rows: tuple[(draw_id, ISO-time, tuple(nums)), ...]
    Günler birbirine yaşam skoru taşımıyor. Her gün ilk çekilişte reset.
    """
    df = pd.DataFrame(serial_rows, columns=["draw_id", "time", "numbers"])
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values(["time", "draw_id"]).reset_index(drop=True)

    life_frames = []
    pool_rows = []
    transition_rows = []
    health_rows = []

    for date, day in df.groupby(df.time.dt.strftime("%Y-%m-%d"), sort=True):
        day = day.sort_values(["time", "draw_id"]).reset_index(drop=True)
        N = len(day)

        mat = np.zeros((N, 80), dtype=np.uint8)
        draw_sets = []

        for t, r in enumerate(day.itertuples(index=False)):
            s = set(r.numbers)
            draw_sets.append(s)
            for n in s:
                mat[t, n - 1] = 1

        prefix = np.cumsum(mat, axis=0)

        score_m = np.zeros((N, 80), dtype=np.float32)
        act_m = np.zeros((N, 80), dtype=np.float32)
        delta_m = np.zeros((N, 80), dtype=np.float32)
        gap_m = np.zeros((N, 80), dtype=np.int16)
        h3_m = np.zeros((N, 80), dtype=np.int8)
        h6_m = np.zeros((N, 80), dtype=np.int8)
        h12_m = np.zeros((N, 80), dtype=np.int8)
        h24_m = np.zeros((N, 80), dtype=np.int8)
        h48_m = np.zeros((N, 80), dtype=np.int8)
        dayhit_m = np.zeros((N, 80), dtype=np.int16)
        trend_m = np.zeros((N, 80), dtype=np.float32)
        age_m = np.ones((N, 80), dtype=np.int16)
        states_m = np.empty((N, 80), dtype=object)

        prev_score = np.zeros(80, dtype=float)
        prev_state = np.array(["NEUTRAL"] * 80, dtype=object)
        prev_age = np.zeros(80, dtype=int)
        last_seen = np.full(80, -1, dtype=int)

        # Saat karakteri, tüm gün verisinden sadece o saatin ilk6'sı ile hesaplanır.
        hour_chars = {}
        by_hour = defaultdict(dict)
        for r in day.itertuples(index=False):
            mm = r.time.strftime("%M")
            if mm in HOUR12:
                by_hour[r.time.strftime("%H")][mm] = set(r.numbers)

        for hh, d in by_hour.items():
            if any(m not in d for m in FIRST6):
                continue
            c1 = {n: sum(n in d[m] for m in FIRST3) for n in range(1, 81)}
            c2 = {n: sum(n in d[m] for m in SECOND3) for n in range(1, 81)}
            c6 = {n: c1[n] + c2[n] for n in range(1, 81)}
            q6 = [sum(c6[n] == k for n in range(1, 81)) for k in range(7)]
            if q6[0] <= 12:
                zb = "ZERO6_LOW"
            elif q6[0] <= 16:
                zb = "ZERO6_MID"
            else:
                zb = "ZERO6_HIGH"
            hour_chars[hh] = {"q6": q6, "zero6_band": zb}

        for t, r in enumerate(day.itertuples(index=False)):
            current = mat[t].astype(float)
            cum = prefix[t].astype(float)

            h3, n3 = interval_sum(prefix, t, 3)
            h6, n6 = interval_sum(prefix, t, 6)
            h12, n12 = interval_sum(prefix, t, 12)
            h24, n24 = interval_sum(prefix, t, 24)
            h48, n48 = interval_sum(prefix, t, 48)

            ph6, pn6 = interval_sum(prefix, t - 6, 6) if t - 6 >= 0 else (np.zeros(80), 0)

            z6 = np.array([binom_z(h6[i], n6) for i in range(80)])
            z12 = np.array([binom_z(h12[i], n12) for i in range(80)])
            z24 = np.array([binom_z(h24[i], n24) for i in range(80)])
            z48 = np.array([binom_z(h48[i], n48) for i in range(80)])
            zday = np.array([binom_z(cum[i], t + 1) for i in range(80)])

            rate6 = h6 / max(1, n6)
            prev_rate6 = ph6 / max(1, pn6) if pn6 else np.zeros(80)
            trend = rate6 - prev_rate6

            # Yakın dönem ağır, gün içi kimlik zemin.
            score = (
                0.34 * z6
                + 0.24 * z12
                + 0.16 * z24
                + 0.10 * z48
                + 0.16 * zday
                + 0.30 * trend
            )
            delta = score - prev_score

            gaps = np.zeros(80, dtype=int)
            for i in range(80):
                if current[i]:
                    gaps[i] = 0
                elif last_seen[i] >= 0:
                    gaps[i] = t - last_seen[i]
                else:
                    gaps[i] = t + 1

            states = []
            act_idx = np.zeros(80, dtype=float)

            for i in range(80):
                stt = classify_state(
                    float(score[i]),
                    float(prev_score[i]),
                    str(prev_state[i]),
                    bool(current[i]),
                    float(delta[i]),
                    int(gaps[i]),
                )
                states.append(stt)
                act_idx[i] = activation_index(
                    float(score[i]),
                    float(delta[i]),
                    bool(current[i]),
                    float(h3[i]),
                    float(h6[i]),
                    n6,
                )

                if stt == prev_state[i]:
                    age = prev_age[i] + 1
                else:
                    age = 1
                age_m[t, i] = age

            score_m[t] = score.astype(np.float32)
            act_m[t] = act_idx.astype(np.float32)
            delta_m[t] = delta.astype(np.float32)
            gap_m[t] = gaps.astype(np.int16)
            h3_m[t] = h3.astype(np.int8)
            h6_m[t] = h6.astype(np.int8)
            h12_m[t] = h12.astype(np.int8)
            h24_m[t] = h24.astype(np.int8)
            h48_m[t] = h48.astype(np.int8)
            dayhit_m[t] = cum.astype(np.int16)
            trend_m[t] = trend.astype(np.float32)
            states_m[t] = np.array(states, dtype=object)

            # Her yaşam durumu kendi içinde 5'li havuzlar.
            hh = r.time.strftime("%H")
            mm = r.time.strftime("%M")
            hc = hour_chars.get(hh)
            char_available = hc is not None and mm in ("27", "32", "37", "42", "47", "52", "57")

            for status in STATUS_ORDER:
                ids = [i for i, s in enumerate(states) if s == status]
                ids = sorted(ids, key=lambda i: (-act_idx[i], -score[i], i))

                for rank, start in enumerate(range(0, len(ids), 5), 1):
                    chunk = ids[start:start + 5]
                    if not chunk:
                        continue
                    members = [i + 1 for i in chunk]

                    exact_hits = []
                    masks = []
                    seen = set()

                    for h in range(1, 7):
                        if t + h < N:
                            hit_positions = [
                                p for p, n in enumerate(members, 1)
                                if n in draw_sets[t + h]
                            ]
                            exact_hits.append(len(hit_positions))
                            mask = 0
                            for p in hit_positions:
                                mask |= 1 << (p - 1)
                            masks.append(mask)
                            seen.update(n for n in members if n in draw_sets[t + h])
                        else:
                            exact_hits.append(np.nan)
                            masks.append(np.nan)

                    valid = [x for x in exact_hits if not pd.isna(x)]

                    row = {
                        "date": date,
                        "snapshot_time": pd.Timestamp(r.time),
                        "draw_id": int(r.draw_id),
                        "hour": hh,
                        "minute": mm,
                        "status": status,
                        "group_rank": rank,
                        "pool_size": len(members),
                        "members": "-".join(f"{n:02d}" for n in members),
                        "mean_score": float(np.mean([score[i] for i in chunk])),
                        "mean_activation": float(np.mean([act_idx[i] for i in chunk])),
                        "mean_gap": float(np.mean([gaps[i] for i in chunk])),
                        "current_hits": int(sum(current[i] for i in chunk)),
                        "unique_next6": len(seen) if valid else np.nan,
                        "max_same_next6": max(valid) if valid else np.nan,
                        "zero6_band": hc["zero6_band"] if char_available else "",
                        "q6_0": hc["q6"][0] if char_available else np.nan,
                    }

                    for p in range(1, 6):
                        row[f"p{p}"] = members[p - 1] if p <= len(members) else np.nan

                    for h in range(1, 7):
                        row[f"hit_h{h}"] = exact_hits[h - 1]
                        row[f"mask_h{h}"] = masks[h - 1]

                    pool_rows.append(row)

            # state update
            for i in range(80):
                if current[i]:
                    last_seen[i] = t
            prev_score = score.copy()
            prev_state = np.array(states, dtype=object)
            prev_age = age_m[t].astype(int)

        # Gün yaşam DataFrame — 80 sayı x N çekiliş
        draw_id_col = np.repeat(day.draw_id.values.astype(np.int64), 80)
        time_col = np.repeat(day.time.values, 80)
        num_col = np.tile(np.arange(1, 81, dtype=np.int16), N)

        next1 = np.full((N, 80), np.nan, dtype=np.float32)
        if N > 1:
            next1[:-1] = mat[1:].astype(np.float32)

        day_life = pd.DataFrame({
            "date": np.repeat(date, N * 80),
            "draw_id": draw_id_col,
            "time": time_col,
            "hour": np.repeat(day.time.dt.strftime("%H").values, 80),
            "minute": np.repeat(day.time.dt.strftime("%M").values, 80),
            "num": num_col,
            "hit": mat.reshape(-1).astype(np.int8),
            "status": states_m.reshape(-1),
            "state_age": age_m.reshape(-1).astype(np.int16),
            "score": score_m.reshape(-1),
            "activation": act_m.reshape(-1),
            "delta": delta_m.reshape(-1),
            "gap": gap_m.reshape(-1),
            "h3": h3_m.reshape(-1),
            "h6": h6_m.reshape(-1),
            "h12": h12_m.reshape(-1),
            "h24": h24_m.reshape(-1),
            "h48": h48_m.reshape(-1),
            "day_hits": dayhit_m.reshape(-1),
            "trend6": trend_m.reshape(-1),
            "next1_hit": next1.reshape(-1),
        })

        life_frames.append(day_life)

        # Durum geçişleri
        if N > 1:
            for t in range(N - 1):
                for i in range(80):
                    transition_rows.append({
                        "date": date,
                        "time": pd.Timestamp(day.time.iloc[t]),
                        "num": i + 1,
                        "from_status": states_m[t, i],
                        "to_status": states_m[t + 1, i],
                        "next_hit": int(mat[t + 1, i]),
                        "from_age": int(age_m[t, i]),
                        "from_gap": int(gap_m[t, i]),
                        "from_delta": float(delta_m[t, i]),
                    })

        expected_minutes = set(HOUR12)
        day_minutes = Counter(day.time.dt.strftime("%M"))
        full_hour = 0
        incomplete_hour = 0
        for hh, g in day.groupby(day.time.dt.strftime("%H")):
            mins = set(g.time.dt.strftime("%M"))
            if expected_minutes.issubset(mins):
                full_hour += 1
            elif mins & expected_minutes:
                incomplete_hour += 1

        health_rows.append({
            "date": date,
            "draws": N,
            "full_hours": full_hour,
            "incomplete_hours": incomplete_hour,
        })

    life = pd.concat(life_frames, ignore_index=True)
    life["status"] = pd.Categorical(life["status"], categories=STATUS_ORDER, ordered=True)

    pools = pd.DataFrame(pool_rows)
    transitions = pd.DataFrame(transition_rows)
    health = pd.DataFrame(health_rows)

    # --------------------------------------------------------
    # DURUM ÖZETİ
    # --------------------------------------------------------
    valid_life = life.dropna(subset=["next1_hit"]).copy()

    state_summary = (
        valid_life.groupby("status", observed=True)
        .agg(
            n=("next1_hit", "size"),
            next_hit_rate=("next1_hit", "mean"),
            current_hit_rate=("hit", "mean"),
            mean_score=("score", "mean"),
            mean_activation=("activation", "mean"),
            mean_gap=("gap", "mean"),
            mean_age=("state_age", "mean"),
        )
        .reset_index()
    )
    state_summary["next_hit_pct"] = 100 * state_summary.next_hit_rate
    state_summary["edge_pp_vs25"] = state_summary.next_hit_pct - 25.0

    # Durum yaşı / bekleme
    life_age = valid_life.copy()
    life_age["age_bucket"] = life_age.state_age.map(bucket_age)
    life_age["gap_bucket"] = life_age.gap.map(bucket_gap)

    age_summary = (
        life_age.groupby(["status", "age_bucket"], observed=True)
        .agg(n=("next1_hit", "size"), next_hit_pct=("next1_hit", lambda s: 100 * s.mean()))
        .reset_index()
    )

    gap_summary = (
        life_age.groupby(["status", "gap_bucket"], observed=True)
        .agg(n=("next1_hit", "size"), next_hit_pct=("next1_hit", lambda s: 100 * s.mean()))
        .reset_index()
    )

    # Durum geçiş matrisi
    transition_summary = (
        transitions.groupby(["from_status", "to_status"], observed=True)
        .agg(
            n=("next_hit", "size"),
            next_hit_pct=("next_hit", lambda s: 100 * s.mean()),
            mean_from_gap=("from_gap", "mean"),
            mean_from_delta=("from_delta", "mean"),
        )
        .reset_index()
    )

    # --------------------------------------------------------
    # 5'Lİ HAVUZ ÖZETİ
    # --------------------------------------------------------
    full5 = pools[(pools.pool_size == 5) & pools.hit_h1.notna()].copy()

    if not full5.empty:
        pool_summary = (
            full5.groupby(["status", "group_rank"], observed=True)
            .agg(
                n=("hit_h1", "size"),
                mean_h1=("hit_h1", "mean"),
                p2=("hit_h1", lambda s: 100 * (s >= 2).mean()),
                p3=("hit_h1", lambda s: 100 * (s >= 3).mean()),
                p4=("hit_h1", lambda s: 100 * (s >= 4).mean()),
                p5=("hit_h1", lambda s: 100 * (s >= 5).mean()),
                max6_mean=("max_same_next6", "mean"),
                unique6_mean=("unique_next6", "mean"),
                mean_activation=("mean_activation", "mean"),
                mean_gap=("mean_gap", "mean"),
            )
            .reset_index()
        )
        pool_summary["mean_edge"] = pool_summary.mean_h1 - 1.25
        pool_summary["p2_edge_pp"] = pool_summary.p2 - 100 * hypergeom_p_ge(5, 2)
        pool_summary["p3_edge_pp"] = pool_summary.p3 - 100 * hypergeom_p_ge(5, 3)
    else:
        pool_summary = pd.DataFrame()

    # Pozisyon çift/üçlü — tüm tam 5'liler, statü/rank bazında.
    pair_rows = []
    triple_rows = []
    if not full5.empty:
        for (status, rank), g in full5.groupby(["status", "group_rank"], observed=True):
            n = len(g)
            if n < 20:
                continue

            pc = Counter()
            tc = Counter()

            for mask in g.mask_h1.dropna().astype(int):
                for a, b in combinations(range(1, 6), 2):
                    if (mask & (1 << (a - 1))) and (mask & (1 << (b - 1))):
                        pc[(a, b)] += 1
                for a, b, c in combinations(range(1, 6), 3):
                    if all(mask & (1 << (p - 1)) for p in (a, b, c)):
                        tc[(a, b, c)] += 1

            for key, hits in pc.items():
                pair_rows.append({
                    "status": status,
                    "group_rank": rank,
                    "positions": "-".join(map(str, key)),
                    "n": n,
                    "both_hit_pct": 100 * hits / n,
                    "random_pct": 100 * ((20/80) * (19/79)),
                })

            for key, hits in tc.items():
                triple_rows.append({
                    "status": status,
                    "group_rank": rank,
                    "positions": "-".join(map(str, key)),
                    "n": n,
                    "all3_hit_pct": 100 * hits / n,
                    "random_pct": 100 * ((20/80) * (19/79) * (18/78)),
                })

    pair_summary = pd.DataFrame(pair_rows)
    triple_summary = pd.DataFrame(triple_rows)

    # --------------------------------------------------------
    # DAKİKA x DURUM / DAKİKA x HAVUZ
    # --------------------------------------------------------
    minute_state = (
        valid_life[valid_life.minute.isin(HOUR12)]
        .groupby(["minute", "status"], observed=True)
        .agg(
            n=("next1_hit", "size"),
            next_hit_pct=("next1_hit", lambda s: 100 * s.mean()),
            mean_activation=("activation", "mean"),
        )
        .reset_index()
    )
    minute_state["edge_pp_vs25"] = minute_state.next_hit_pct - 25.0

    minute_pool = pd.DataFrame()
    if not full5.empty:
        minute_pool = (
            full5[full5.minute.isin(HOUR12)]
            .groupby(["minute", "status", "group_rank"], observed=True)
            .agg(
                n=("hit_h1", "size"),
                mean_h1=("hit_h1", "mean"),
                p2=("hit_h1", lambda s: 100 * (s >= 2).mean()),
                p3=("hit_h1", lambda s: 100 * (s >= 3).mean()),
            )
            .reset_index()
        )

    # --------------------------------------------------------
    # H1 / H2 STABİLİTE — statü ve havuz
    # --------------------------------------------------------
    cutoff = valid_life.time.sort_values().iloc[len(valid_life) // 2]

    v = valid_life.copy()
    v["split"] = np.where(v.time <= cutoff, "H1", "H2")

    state_halves = (
        v.groupby(["status", "split"], observed=True)
        .agg(n=("next1_hit", "size"), next_hit_pct=("next1_hit", lambda s: 100 * s.mean()))
        .reset_index()
    )

    pool_halves = pd.DataFrame()
    stable_pool = pd.DataFrame()

    if not full5.empty:
        ph = full5.copy()
        ph["split"] = np.where(ph.snapshot_time <= cutoff, "H1", "H2")

        pool_halves = (
            ph.groupby(["status", "group_rank", "split"], observed=True)
            .agg(
                n=("hit_h1", "size"),
                mean_h1=("hit_h1", "mean"),
                p2=("hit_h1", lambda s: 100 * (s >= 2).mean()),
                p3=("hit_h1", lambda s: 100 * (s >= 3).mean()),
            )
            .reset_index()
        )

        h1 = pool_halves[pool_halves.split == "H1"].drop(columns="split")
        h2 = pool_halves[pool_halves.split == "H2"].drop(columns="split")
        stable_pool = h1.merge(
            h2,
            on=["status", "group_rank"],
            suffixes=("_H1", "_H2"),
        )
        stable_pool["stable_above_random"] = (
            (stable_pool.n_H1 >= 40)
            & (stable_pool.n_H2 >= 40)
            & (stable_pool.mean_h1_H1 > 1.25)
            & (stable_pool.mean_h1_H2 > 1.25)
            & (stable_pool.p2_H1 > 100 * hypergeom_p_ge(5, 2))
            & (stable_pool.p2_H2 > 100 * hypergeom_p_ge(5, 2))
        )

    # --------------------------------------------------------
    # SAATLİK AİLELER
    # --------------------------------------------------------
    hours_raw = build_hour_character_rows(df)

    # :27 yaşam katman kontenjanlarını saat özelliklerine ekle.
    if not life.empty and not hours_raw.empty:
        l27 = life[life.minute == "27"].copy()
        counts = (
            l27.groupby(["date", "hour", "status"], observed=True)
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        for s in STATUS_ORDER:
            if s not in counts.columns:
                counts[s] = 0
            counts = counts.rename(columns={s: f"state_{s}"})

        hours_raw = hours_raw.merge(counts, on=["date", "hour"], how="left")

    hours, family_summary, clock_affinity, family_transitions = fit_hour_families(
        hours_raw,
        requested_k=requested_k,
    )

    # Aile H2 sonuç farkı — sadece betimleyici.
    family_h2_edges = pd.DataFrame()
    if not hours.empty:
        h2 = hours[(hours.split == "H2") & (hours.last6_complete == 1)].copy()
        if not h2.empty:
            overall = {
                "zero6_opened": h2.zero6_opened.mean(),
                "zero6_max_same": h2.zero6_max_same.mean(),
                "hot6_seen": h2.hot6_seen.mean(),
            }
            family_h2_edges = (
                h2.groupby(["family", "family_tag"], observed=True)
                .agg(
                    n=("family", "size"),
                    zero6_opened=("zero6_opened", "mean"),
                    zero6_max_same=("zero6_max_same", "mean"),
                    hot6_seen=("hot6_seen", "mean"),
                )
                .reset_index()
            )
            family_h2_edges["zero6_opened_edge"] = family_h2_edges.zero6_opened - overall["zero6_opened"]
            family_h2_edges["zero6_max_same_edge"] = family_h2_edges.zero6_max_same - overall["zero6_max_same"]
            family_h2_edges["hot6_seen_edge"] = family_h2_edges.hot6_seen - overall["hot6_seen"]

    # --------------------------------------------------------
    # SAAT-OF-DAY x YAŞAM KATMANI
    # --------------------------------------------------------
    clock_state = (
        valid_life.groupby(["hour", "status"], observed=True)
        .agg(
            n=("next1_hit", "size"),
            next_hit_pct=("next1_hit", lambda s: 100 * s.mean()),
        )
        .reset_index()
    )
    clock_state["edge_pp_vs25"] = clock_state.next_hit_pct - 25.0

    # --------------------------------------------------------
    # RAPOR
    # --------------------------------------------------------
    report = build_master_report(
        df=df,
        digest=digest,
        health=health,
        state_summary=state_summary,
        age_summary=age_summary,
        gap_summary=gap_summary,
        transition_summary=transition_summary,
        pool_summary=pool_summary,
        stable_pool=stable_pool,
        family_summary=family_summary,
        family_h2_edges=family_h2_edges,
        clock_affinity=clock_affinity,
        family_transitions=family_transitions,
        minute_state=minute_state,
    )

    return {
        "life": life,
        "pools": pools,
        "full5": full5,
        "transitions": transitions,
        "state_summary": state_summary,
        "age_summary": age_summary,
        "gap_summary": gap_summary,
        "transition_summary": transition_summary,
        "pool_summary": pool_summary,
        "pair_summary": pair_summary,
        "triple_summary": triple_summary,
        "minute_state": minute_state,
        "minute_pool": minute_pool,
        "state_halves": state_halves,
        "pool_halves": pool_halves,
        "stable_pool": stable_pool,
        "hours": hours,
        "family_summary": family_summary,
        "family_h2_edges": family_h2_edges,
        "clock_affinity": clock_affinity,
        "family_transitions": family_transitions,
        "clock_state": clock_state,
        "health": health,
        "cutoff": cutoff,
        "report": report,
    }


# ============================================================
# RAPOR
# ============================================================

def build_master_report(
    df,
    digest,
    health,
    state_summary,
    age_summary,
    gap_summary,
    transition_summary,
    pool_summary,
    stable_pool,
    family_summary,
    family_h2_edges,
    clock_affinity,
    family_transitions,
    minute_state,
):
    L = []
    L.append("HIZLI ON — 1–80 YAŞAM HARİTASI / 5'Lİ KATMAN / SAATLİK AİLELER V5")
    L.append("=" * 118)
    L.append(
        f"Kapsam: {df.time.min():%d.%m.%Y %H:%M} – {df.time.max():%d.%m.%Y %H:%M} "
        f"| çekiliş={len(df)} | gün={df.time.dt.date.nunique()} | SHA={digest[:16]}"
    )
    L.append("")
    L.append("TEMEL İLKE")
    L.append(
        "Her gün yaşam izi ilk çekilişte sıfırlanır. Gelecek çekiliş yaşam puanında kullanılmaz. "
        "Gap yalnız betimleyicidir; 'artık çıkmalı' varsayımı yoktur."
    )
    L.append(
        "5'li rastgele referans: E=1.250 | "
        f"P2+={100*hypergeom_p_ge(5,2):.2f}% | "
        f"P3+={100*hypergeom_p_ge(5,3):.2f}% | "
        f"P4+={100*hypergeom_p_ge(5,4):.3f}%"
    )

    L.append("\n[A] DURUM KATMANLARI — SONRAKİ TEK ÇEKİLİŞ")
    L.append("-" * 118)
    if not state_summary.empty:
        for r in state_summary.sort_values("next_hit_pct", ascending=False).itertuples(index=False):
            L.append(
                f"{r.status:12s} | n={r.n:7d} | next={r.next_hit_pct:6.2f}% "
                f"| edge={r.edge_pp_vs25:+6.2f}pp | score={r.mean_score:+.3f} "
                f"| act={r.mean_activation:+.3f} | gap={r.mean_gap:.2f} | yaş={r.mean_age:.2f}"
            )

    L.append("\n[B] DURUM YAŞI — STABİL Mİ, YENİ Mİ?")
    L.append("-" * 118)
    if not age_summary.empty:
        tmp = age_summary[age_summary.n >= 100].sort_values("next_hit_pct", ascending=False).head(40)
        for r in tmp.itertuples(index=False):
            L.append(f"{r.status:12s} yaş={r.age_bucket:>3s} | n={r.n:7d} | next={r.next_hit_pct:6.2f}%")

    L.append("\n[C] GAP / BEKLEME — YALNIZ BETİMLEYİCİ")
    L.append("-" * 118)
    if not gap_summary.empty:
        tmp = gap_summary[gap_summary.n >= 100].sort_values("next_hit_pct", ascending=False).head(40)
        for r in tmp.itertuples(index=False):
            L.append(f"{r.status:12s} gap={r.gap_bucket:>3s} | n={r.n:7d} | next={r.next_hit_pct:6.2f}%")

    L.append("\n[D] DURUM GEÇİŞLERİ")
    L.append("-" * 118)
    if not transition_summary.empty:
        tmp = transition_summary[transition_summary.n >= 100].sort_values("next_hit_pct", ascending=False).head(60)
        for r in tmp.itertuples(index=False):
            L.append(
                f"{r.from_status:12s} → {r.to_status:12s} | n={r.n:7d} "
                f"| next-hit={r.next_hit_pct:6.2f}% | gap={r.mean_from_gap:.2f} | delta={r.mean_from_delta:+.3f}"
            )

    L.append("\n[E] 5'Lİ YAŞAM HAVUZLARI")
    L.append("-" * 118)
    if not pool_summary.empty:
        tmp = pool_summary[pool_summary.n >= 40].sort_values(["p3", "p2", "n"], ascending=False).head(60)
        for r in tmp.itertuples(index=False):
            L.append(
                f"{r.status:12s} G{int(r.group_rank):02d} | n={r.n:5d} | mean={r.mean_h1:.3f} "
                f"| P2+={r.p2:5.1f}% ({r.p2_edge_pp:+.1f}pp) "
                f"| P3+={r.p3:5.1f}% ({r.p3_edge_pp:+.1f}pp) "
                f"| unique6={r.unique6_mean:.2f}/5"
            )

    L.append("\n[F] KRONOLOJİK İKİ-YARI — 5'Lİ HAVUZ ADAYLARI")
    L.append("-" * 118)
    if not stable_pool.empty:
        cand = stable_pool[stable_pool.stable_above_random == True].sort_values(
            ["p2_H2", "mean_h1_H2"],
            ascending=False,
        )
        if cand.empty:
            L.append("İki yarıda birden rastgele referansı geçen n>=40 aday yok.")
        else:
            for r in cand.head(50).itertuples(index=False):
                L.append(
                    f"{r.status:12s} G{int(r.group_rank):02d} | "
                    f"H1 n={r.n_H1:4d} mean={r.mean_h1_H1:.3f} P2={r.p2_H1:5.1f}% | "
                    f"H2 n={r.n_H2:4d} mean={r.mean_h1_H2:.3f} P2={r.p2_H2:5.1f}%"
                )

    L.append("\n[G] SAATLİK AİLELER — İLK6 İLE ÖĞRENİLİR, SON6 SONUÇTUR")
    L.append("-" * 118)
    if not family_summary.empty:
        for r in family_summary.itertuples(index=False):
            L.append(
                f"{r.family} {r.family_tag:18s} {r.split} | n={r.n:4d} "
                f"| zero6={r.zero6_mean:.2f} overlap={r.overlap_mean:.2f} new2={r.new2_mean:.2f} "
                f"| zero6-open={r.zero6_opened_mean:.2f} | zero6-maxsame={r.zero6_max_same_mean:.2f} "
                f"| last6-distinct={r.last6_distinct_mean:.2f}"
            )

    L.append("\n[H] SAATLİK AİLE — H2 SONUÇ FARKLARI")
    L.append("-" * 118)
    if not family_h2_edges.empty:
        for r in family_h2_edges.sort_values("zero6_opened_edge", ascending=False).itertuples(index=False):
            L.append(
                f"{r.family} {r.family_tag:18s} | n={r.n:4d} "
                f"| zero6-open={r.zero6_opened:.2f} edge={r.zero6_opened_edge:+.2f} "
                f"| maxsame={r.zero6_max_same:.2f} edge={r.zero6_max_same_edge:+.2f} "
                f"| hot6-seen={r.hot6_seen:.2f} edge={r.hot6_seen_edge:+.2f}"
            )

    L.append("\n[I] SAAT-OF-DAY AİLE EĞİLİMİ")
    L.append("-" * 118)
    if not clock_affinity.empty:
        for r in clock_affinity.itertuples(index=False):
            L.append(
                f"{r.hour}:00 | baskın={r.dominant_family} | n={r.dominant_n} "
                f"| pay={r.dominant_share_pct:.1f}%"
            )

    L.append("\n[J] AİLE → SONRAKİ SAAT AİLESİ")
    L.append("-" * 118)
    if not family_transitions.empty:
        for r in family_transitions.head(80).itertuples(index=False):
            L.append(
                f"{r.from_family} → {r.to_family} | n={r.n} | from-pay={r.pct_from:.1f}%"
            )

    L.append("\n[K] DAKİKA x YAŞAM KATMANI — SONRAKİ ÇEKİLİŞ")
    L.append("-" * 118)
    if not minute_state.empty:
        tmp = minute_state[minute_state.n >= 100].sort_values(
            ["edge_pp_vs25", "n"],
            ascending=False,
        ).head(80)
        for r in tmp.itertuples(index=False):
            L.append(
                f":{r.minute} {r.status:12s} | n={r.n:7d} "
                f"| next={r.next_hit_pct:6.2f}% | edge={r.edge_pp_vs25:+6.2f}pp"
            )

    L.append("\n[L] VERİ SAĞLIĞI")
    L.append("-" * 118)
    if not health.empty:
        for r in health.itertuples(index=False):
            L.append(
                f"{r.date} | çekiliş={r.draws} | tam-saat={r.full_hours} | eksik-saat={r.incomplete_hours}"
            )

    return "\n".join(L)


# ============================================================
# DIŞA AKTARIM
# ============================================================

def make_zip(result, digest):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("ANA_RAPOR.txt", result["report"].encode("utf-8"))
        z.writestr("durum_ozeti.csv", result["state_summary"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("durum_yasi.csv", result["age_summary"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("gap_ozeti.csv", result["gap_summary"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("durum_gecisleri.csv", result["transition_summary"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("5li_havuz_ozeti.csv", result["pool_summary"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("5li_havuz_H1_H2.csv", result["pool_halves"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("saatlik_aileler.csv", result["hours"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("saatlik_aile_ozeti.csv", result["family_summary"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("saat_aile_baskinligi.csv", result["clock_affinity"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("aile_gecisleri.csv", result["family_transitions"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("dakika_durum.csv", result["minute_state"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("dakika_5li_havuz.csv", result["minute_pool"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("veri_sagligi.csv", result["health"].to_csv(index=False).encode("utf-8-sig"))

        # Büyük tablolar ayrıca sıkıştırılır.
        z.writestr("1_80_yasam_izi.csv", result["life"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("5li_havuz_olaylari.csv", result["pools"].to_csv(index=False).encode("utf-8-sig"))

        z.writestr("SHA256.txt", digest.encode("ascii"))
    return buf.getvalue()


# ============================================================
# SIDEBAR / VERİ
# ============================================================

with st.sidebar:
    st.header("⚙️ Veri ve analiz")
    uploaded = st.file_uploader("İstersen TXT yükle", type=["txt"])

    if st.button("🔄 VERİYİ YENİDEN OKU", width="stretch"):
        st.cache_data.clear()
        st.session_state.pop("analysis_v5", None)
        st.rerun()

    st.divider()
    st.write("**Saatlik aile küme sayısı**")
    requested_k = st.slider("K", min_value=3, max_value=9, value=6, step=1)
    st.caption("Kümeler sadece ilk6 özellikleriyle öğrenilir; son6 sonucu küme kurarken kullanılmaz.")

    token, repo, branch, path = github_config()
    st.divider()
    st.write(f"**Repo:** `{repo}`")
    st.write(f"**Branch:** `{branch}`")
    st.write(f"**Veri:** `{path}`")
    if token:
        st.success("GitHub yazma tokeni hazır.")
    else:
        st.info("GitHub okuma denenir; yazma için GITHUB_TOKEN gerekir.")


raw, source_name = read_source(uploaded)

if raw is None:
    st.error("veri.txt bulunamadı. GitHub ayarını kontrol et veya TXT yükle.")
    st.stop()

digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()

try:
    df, rejected, duplicates = parse_text(raw, digest)
except Exception as e:
    st.error(str(e))
    st.stop()

# Veri sağlık kartları
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
c2.metric("Gün", int(df.time.dt.date.nunique()))
c3.metric("İlk", df.time.min().strftime("%d.%m.%Y"))
c4.metric("Son", df.time.max().strftime("%d.%m.%Y %H:%M"))
c5.metric("SHA", digest[:10])

if rejected or duplicates:
    st.warning(f"Parse-red={rejected} | duplicate draw_id={duplicates}")

st.caption(f"Kaynak: {source_name}")


# ============================================================
# ANALİZ ÇALIŞTIR
# ============================================================

current_key = f"{digest}:{requested_k}"

if st.session_state.get("analysis_v5_key") != current_key:
    st.session_state.pop("analysis_v5", None)

if "analysis_v5" not in st.session_state:
    st.info(
        "Bu motor kupon üretmek yerine önce oyunun yaşam yapısını çıkarır. "
        "1–80 bütün sayıların gün içi izi, 5'li katmanları ve saatlik aileleri birlikte analiz eder."
    )

    if st.button("🧠 TAM YAŞAM ANALİZİNİ ÇALIŞTIR", type="primary", width="stretch"):
        with st.spinner("1–80 yaşam izi, 5'li havuzlar ve saatlik aileler hesaplanıyor..."):
            serial_rows = tuple(
                (int(r.draw_id), pd.Timestamp(r.time).isoformat(), tuple(r.numbers))
                for r in df.itertuples(index=False)
            )
            result = analyze_all(serial_rows, digest, requested_k=requested_k)
            st.session_state["analysis_v5"] = result
            st.session_state["analysis_v5_key"] = current_key
        st.rerun()
    st.stop()

result = st.session_state["analysis_v5"]

life = result["life"]
pools = result["pools"]
full5 = result["full5"]


# ============================================================
# TABS
# ============================================================

tabs = st.tabs([
    "🏠 Özet",
    "🧬 1–80 Yaşam İzi",
    "🧺 5'li Katmanlar",
    "🔁 Durum Geçişleri",
    "🕒 Saatlik Aileler",
    "⏱️ Dakika / Saat",
    "📥 Yeni Veri",
    "📦 Rapor",
])


# ------------------------------------------------------------
# ÖZET
# ------------------------------------------------------------
with tabs[0]:
    st.subheader("Yaşam katmanlarının sonraki çekiliş davranışı")

    ss = result["state_summary"].copy()
    if not ss.empty:
        show = ss[[
            "status", "n", "next_hit_pct", "edge_pp_vs25",
            "mean_score", "mean_activation", "mean_gap", "mean_age"
        ]].copy()
        show.columns = [
            "Katman", "Olay", "Sonraki çıkış %", "25%'e fark pp",
            "Yaşam skoru", "Aktivasyon", "Ort gap", "Ort durum yaşı"
        ]
        st.dataframe(show, width="stretch", hide_index=True)

    st.caption(
        "Tek sayı için rastgele referans %25'tir. Buradaki farklar keşif ölçüsüdür; "
        "ayrı H2 kontrolü olmadan 'gelecekte kesin yükselir' anlamına gelmez."
    )

    st.subheader("Kronolojik iki-yarıda kalan 5'li havuz adayları")
    sp = result["stable_pool"]
    if sp.empty:
        st.info("Yeterli 5'li havuz yok.")
    else:
        cand = sp[sp.stable_above_random == True].copy()
        if cand.empty:
            st.warning("İki yarıda birden rastgele 5'li referansı geçen n>=40 havuz bulunmadı.")
        else:
            st.dataframe(
                cand.sort_values(["p2_H2", "mean_h1_H2"], ascending=False),
                width="stretch",
                hide_index=True,
            )

    st.subheader("Saatlik aileler gerçekten ayrışıyor mu?")
    fe = result["family_h2_edges"]
    if fe.empty:
        st.info("H2 saatlik aile sonucu üretmek için yeterli tam saat yok.")
    else:
        st.dataframe(
            fe.sort_values("zero6_opened_edge", ascending=False),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Saat aileleri yalnız ilk6 yapısından öğrenildi. Tablodaki H2 sonuç farkları, "
            "ailelerin son6 davranışlarının birbirinden ayrışıp ayrışmadığını gösterir."
        )


# ------------------------------------------------------------
# 1–80 YAŞAM
# ------------------------------------------------------------
with tabs[1]:
    st.subheader("Bir sayının gün içi yaşam yolu")

    dates = sorted(life.date.unique().tolist())
    selected_date = st.selectbox("Gün", dates, index=len(dates)-1, key="life_date")
    selected_num = st.slider("Sayı", 1, 80, 1, key="life_num")

    g = life[(life.date == selected_date) & (life.num == selected_num)].copy()

    if not g.empty:
        view_cols = [
            "draw_id", "time", "hit", "status", "state_age",
            "score", "activation", "delta", "gap",
            "h3", "h6", "h12", "h24", "h48", "day_hits", "trend6", "next1_hit",
        ]
        st.dataframe(g[view_cols], width="stretch", hide_index=True)

        st.write("**Yaşam yolu:**")
        compact = (
            g.assign(label=g.time.dt.strftime("%H:%M") + " " + g.status.astype(str))
             .label.tolist()
        )
        st.code(" → ".join(compact), language=None)

    st.subheader("1–80 gün sonu kimliği")
    last_of_day = (
        life[life.date == selected_date]
        .sort_values("time")
        .groupby("num", as_index=False)
        .tail(1)
        .sort_values(["status", "activation"], ascending=[True, False])
    )
    st.dataframe(
        last_of_day[["num", "status", "score", "activation", "gap", "day_hits", "h6", "h12", "h24"]],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Durum yaşı")
    st.dataframe(
        result["age_summary"].sort_values(["status", "age_bucket"]),
        width="stretch",
        hide_index=True,
    )

    st.subheader("Bekleme / gap")
    st.dataframe(
        result["gap_summary"].sort_values(["status", "gap_bucket"]),
        width="stretch",
        hide_index=True,
    )


# ------------------------------------------------------------
# 5'Lİ HAVUZLAR
# ------------------------------------------------------------
with tabs[2]:
    st.subheader("5'li yaşam havuzları — genel performans")

    ps = result["pool_summary"]
    if ps.empty:
        st.info("Tam 5'li havuz yok.")
    else:
        st.dataframe(
            ps.sort_values(["p3", "p2", "n"], ascending=False),
            width="stretch",
            hide_index=True,
        )

    st.caption(
        f"Rastgele 5'li: E=1.250 | P2+={100*hypergeom_p_ge(5,2):.2f}% | "
        f"P3+={100*hypergeom_p_ge(5,3):.2f}% | P4+={100*hypergeom_p_ge(5,4):.3f}%"
    )

    st.subheader("Belirli çekilişte havuzları gör")
    pool_dates = sorted(pools.date.unique().tolist())
    pd_date = st.selectbox("Gün", pool_dates, index=len(pool_dates)-1, key="pool_date")

    times = sorted(pools[pools.date == pd_date].snapshot_time.dt.strftime("%H:%M").unique().tolist())
    if times:
        pd_time = st.selectbox("Snapshot", times, index=len(times)-1, key="pool_time")
        gg = pools[
            (pools.date == pd_date)
            & (pools.snapshot_time.dt.strftime("%H:%M") == pd_time)
        ].copy()

        st.dataframe(
            gg[[
                "status", "group_rank", "pool_size", "members",
                "mean_score", "mean_activation", "mean_gap",
                "current_hits", "hit_h1", "hit_h2", "hit_h3",
                "hit_h4", "hit_h5", "hit_h6",
            ]],
            width="stretch",
            hide_index=True,
        )

    st.subheader("Aynı 5'li içindeki pozisyon çiftleri")
    if not result["pair_summary"].empty:
        st.dataframe(
            result["pair_summary"].sort_values("both_hit_pct", ascending=False).head(150),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Aynı 5'li içindeki pozisyon üçlüleri")
    if not result["triple_summary"].empty:
        st.dataframe(
            result["triple_summary"].sort_values("all3_hit_pct", ascending=False).head(150),
            width="stretch",
            hide_index=True,
        )


# ------------------------------------------------------------
# DURUM GEÇİŞLERİ
# ------------------------------------------------------------
with tabs[3]:
    st.subheader("Katmandan katmana geçiş")

    ts = result["transition_summary"].copy()
    if not ts.empty:
        min_n = st.slider("Minimum olay", 20, 1000, 100, 20, key="trans_min_n")
        st.dataframe(
            ts[ts.n >= min_n].sort_values(["next_hit_pct", "n"], ascending=False),
            width="stretch",
            hide_index=True,
        )

    st.caption(
        "Örnek: COLD→WAKING_COLD veya RESTED_HOT→HOT gibi geçişlerin ne sıklıkta "
        "oluştuğunu ve o geçişte sayının bir sonraki çekiliş aktivasyonunu ölçer."
    )

    st.subheader("Özel katmanlar")
    special = ts[
        ts.from_status.isin(["COLD", "DEEP_COLD", "WAKING_COLD", "NEW_HOT", "HOT", "RESTED_HOT"])
        | ts.to_status.isin(["WAKING_COLD", "NEW_HOT", "HOT", "RESTED_HOT", "COOLING"])
    ].copy()
    st.dataframe(
        special.sort_values(["next_hit_pct", "n"], ascending=False).head(200),
        width="stretch",
        hide_index=True,
    )


# ------------------------------------------------------------
# SAATLİK AİLELER
# ------------------------------------------------------------
with tabs[4]:
    st.subheader("Saatlik aile keşfi — sadece ilk6 ile")

    st.info(
        "Aile kümesi oluşturulurken :32–:57 sonuçları kullanılmaz. "
        "İlk kronolojik yarıda ilk6 özellikleriyle aile merkezleri öğrenilir; "
        "ikinci yarı aynı merkezlere atanır."
    )

    fs = result["family_summary"]
    if not fs.empty:
        st.dataframe(fs, width="stretch", hide_index=True)

    st.subheader("H2 — ailelerin son6 davranışı")
    fe = result["family_h2_edges"]
    if not fe.empty:
        st.dataframe(
            fe.sort_values("zero6_opened_edge", ascending=False),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Saat-of-day: hangi saat hangi aileye daha çok düşüyor?")
    ca = result["clock_affinity"]
    if not ca.empty:
        st.dataframe(ca, width="stretch", hide_index=True)

    st.subheader("Aile → sonraki saat ailesi")
    ft = result["family_transitions"]
    if not ft.empty:
        st.dataframe(ft, width="stretch", hide_index=True)

    st.subheader("Tüm saat olayları")
    hrs = result["hours"].copy()
    if not hrs.empty:
        show_cols = [
            "date", "hour", "family", "family_tag", "split",
            "zero6_band", "zero6", "first6_distinct", "overlap_12",
            "new_second3", "c6_ge2", "c6_ge3",
            "zero6_opened", "zero6_max_same", "hot6_seen",
            "last6_distinct", "last6_repeat2plus",
        ]
        st.dataframe(hrs[show_cols], width="stretch", hide_index=True)


# ------------------------------------------------------------
# DAKİKA / SAAT
# ------------------------------------------------------------
with tabs[5]:
    st.subheader("Dakika x yaşam katmanı")

    ms = result["minute_state"]
    if not ms.empty:
        min_events = st.slider("Minimum olay", 50, 2000, 200, 50, key="minute_min_n")
        st.dataframe(
            ms[ms.n >= min_events].sort_values(["minute", "next_hit_pct"], ascending=[True, False]),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Dakika x tam 5'li havuz")
    mp = result["minute_pool"]
    if not mp.empty:
        st.dataframe(
            mp[mp.n >= 20].sort_values(["p3", "p2", "n"], ascending=False).head(300),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Saat-of-day x yaşam katmanı")
    cs = result["clock_state"]
    if not cs.empty:
        st.dataframe(
            cs[cs.n >= 100].sort_values(["hour", "next_hit_pct"], ascending=[True, False]),
            width="stretch",
            hide_index=True,
        )


# ------------------------------------------------------------
# YENİ VERİ
# ------------------------------------------------------------
with tabs[6]:
    st.subheader("Kontrollü yeni çekiliş girişi")

    st.caption(
        "İlk6'yı 6 çekiliş olarak veya sonraki çekilişleri tek tek yapıştırabilirsin. "
        "Önce kontrol edilir; sen onaylamadan GitHub'a yazılmaz."
    )

    paste = st.text_area(
        "Ham çekilişi buraya yapıştır",
        height=320,
        placeholder=(
            "Çekiliş no:59187\n"
            "30.09.2026-19:27\n"
            "1\n2\n...\n79\n"
            "Detaylar"
        ),
        key="paste_v5",
    )

    if st.button("🔍 KONTROL ET", type="primary", width="stretch", key="check_v5"):
        recs, errs = parse_pasted_draws(paste)
        st.session_state["pending_v5"] = recs
        st.session_state["pending_v5_errors"] = errs

    if "pending_v5" in st.session_state:
        recs = st.session_state.get("pending_v5", [])
        errs = st.session_state.get("pending_v5_errors", [])

        if errs:
            for e in errs:
                st.error(e)
        elif recs:
            preview = pd.DataFrame([
                {
                    "Çekiliş": r[0],
                    "Tarih-Saat": r[1].strftime("%d.%m.%Y %H:%M"),
                    "20 sayı": " ".join(map(str, r[2])),
                }
                for r in recs
            ])
            st.dataframe(preview, width="stretch", hide_index=True)

            try:
                remote_raw, remote_sha, _ = github_fetch_veri()
                add, skipped, conflicts = validate_against_remote(recs, remote_raw)

                if conflicts:
                    for e in conflicts:
                        st.error("⛔ " + e)
                else:
                    if skipped:
                        st.info("Zaten kayıtlı: " + ", ".join("#" + str(x) for x in skipped))

                    st.write(
                        f"Yeni eklenecek: **{len(add)}** | GitHub dosya SHA: **{remote_sha[:10]}**"
                    )

                    approve = st.checkbox(
                        "Gösterilen çekilişleri kontrol ettim.",
                        key="approve_v5",
                    )

                    if st.button(
                        "✅ ONAYLA VE GITHUB'A KAYDET",
                        disabled=not approve,
                        width="stretch",
                        key="save_v5",
                    ):
                        res = github_commit_records(recs)

                        if res.get("ok"):
                            st.success(
                                res.get("message", "Kayıt tamamlandı.")
                                + (f" | commit {res.get('commit')}" if res.get("commit") else "")
                            )
                            st.cache_data.clear()
                            st.session_state.pop("analysis_v5", None)
                            st.session_state.pop("analysis_v5_key", None)
                            st.session_state.pop("pending_v5", None)
                            st.session_state.pop("pending_v5_errors", None)
                            st.info("Yeni veri kaydedildi. 'VERİYİ YENİDEN OKU' ile analiz tabanını yenile.")
                        else:
                            for e in res.get("errors", ["Kayıt başarısız."]):
                                st.error(e)

            except Exception as e:
                st.error(f"GitHub kontrolü yapılamadı: {e}")


# ------------------------------------------------------------
# RAPOR
# ------------------------------------------------------------
with tabs[7]:
    st.subheader("Ana araştırma raporu")

    st.text_area(
        "Özet TXT",
        value=result["report"],
        height=520,
    )

    st.download_button(
        "⬇️ ANA RAPOR TXT",
        data=result["report"].encode("utf-8"),
        file_name="HIZLI_ON_YASAM_HARITASI_SAATLIK_AILELER_V5.txt",
        mime="text/plain; charset=utf-8",
        width="stretch",
    )

    if st.button("📦 TÜM CSV + YAŞAM İZİ ZIP HAZIRLA", width="stretch"):
        with st.spinner("ZIP hazırlanıyor..."):
            st.session_state["zip_v5"] = make_zip(result, digest)

    if "zip_v5" in st.session_state:
        st.download_button(
            "⬇️ TAM ARAŞTIRMA ZIP",
            data=st.session_state["zip_v5"],
            file_name="HIZLI_ON_YASAM_HARITASI_V5_TUM_TABLOLAR.zip",
            mime="application/zip",
            width="stretch",
        )

    st.subheader("Veri sağlığı")
    st.dataframe(result["health"], width="stretch", hide_index=True)

    st.caption(
        "Bu motorun amacı önce tekrar üretilebilir yaşam örüntülerini bulmaktır. "
        "Kupon motoru ancak ayrı kronolojik/kör doğrulamada kalıcı ayrışma görülürse daha sonra kurulmalıdır."
    )
