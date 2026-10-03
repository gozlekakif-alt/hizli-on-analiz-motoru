# -*- coding: utf-8 -*-
"""
HIZLI ON — AİLE & RİTİM LABORATUVARI V1

Kilitli tanım:
- Bir aile yalnızca üyelerinin TAMAMI AYNI TEK ÇEKİLİŞTE bulunduğunda aktive olur.
- Saat içinde birikme / pencere birleşimi aktivasyon değildir.
- Aile boyutları 2,3,4,5,6,7,8,9,10 sırayla işlenir.
- Ana ritim mesafesi çekiliş numarası farkıdır.
- APP düşük RAM için boyut boyut çalışır, sonuçları SQLite'a yazar ve kaldığı yerden devam eder.

Not:
Bu yazılım geçmiş çekiliş örüntülerini araştırır; gelecek çekiliş veya kazanç garantisi vermez.
"""

from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import math
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------------------
# SAYFA / SABİTLER
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="Hızlı On — Aile & Ritim", page_icon="🧬", layout="wide")

APP_VERSION = "AILE_RITIM_V1.0"
DEFAULT_DATA_FILE = Path("veri.txt")
DB_PATH = Path("aile_ritim_checkpoint.sqlite3")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"
SIZES = list(range(2, 11))
LOW_MASK = (1 << 64) - 1

# RAM'i korumak için:
# 2..6: 1..80 evrenindeki aileleri boyut boyut, prefix-prefix tarar.
# 7..10: tekrar eden büyük aileler için çekiliş-kesişim aday taraması kullanır.
EXHAUSTIVE_MAX_K = 6
PAIR_SCAN_MIN_K = 7

# Ritim tanımının en küçük örnek sayısı. 3 aktivasyon düz ritmi (d,d) gösterebilir.
MIN_ACTIVATIONS = 3

# --------------------------------------------------------------------------------------
# YARDIMCILAR
# --------------------------------------------------------------------------------------
def safe_secret(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, default)
        return str(v) if v is not None else default
    except Exception:
        return default


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def github_read_text(repo: str, branch: str, path: str, token: str = "") -> str:
    """Public repo için RAW, token varsa GitHub API kullanır."""
    if token:
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github.raw+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "hizli-on-aile-ritim",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-aile-ritim"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def load_data_text(uploaded=None):
    """Öncelik: yüklenen dosya > repo içindeki veri.txt > GitHub raw/API."""
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


def _parse_nums_field(s: str) -> List[int]:
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s)]
    nums = [n for n in nums if 1 <= n <= 80]
    # sıra sonucu değiştirmez; tekrarlı sayıları ayıkla
    return sorted(set(nums))


def parse_draws(text: str) -> pd.DataFrame:
    rows = []

    # 1) Kompakt satırlar:
    # 51213;25.08.2026 00:02;2,4,...
    # 51213 | 25.08.2026 00:02 | 2 4 ...
    line_re = re.compile(
        r"^\s*#?(\d{4,})\s*[;|]\s*(\d{2}\.\d{2}\.\d{4})\s+" 
        r"(\d{2}:\d{2})\s*[;|]\s*(.*?)\s*$"
    )
    for line in text.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        draw = int(m.group(1))
        ds, ts = m.group(2), m.group(3)
        nums = _parse_nums_field(m.group(4))
        if len(nums) == 20:
            try:
                dt = datetime.strptime(f"{ds} {ts}", "%d.%m.%Y %H:%M")
            except Exception:
                continue
            rows.append((draw, dt, nums))

    # 2) Milli Piyango kopyala-yapıştır biçimi
    # Çekiliş no: 55118 / 11.09.2026-23:57 / 20 sayı ayrı satırlar
    if not rows:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if "Çekiliş no" not in s and "çekiliş no" not in s.lower():
                i += 1
                continue

            draw = None
            m = re.search(r"(\d{4,})", s)
            if m:
                draw = int(m.group(1))
            j = i + 1
            if draw is None:
                while j < min(i + 5, len(lines)):
                    m = re.fullmatch(r"\s*#?\s*(\d{4,})\s*", lines[j])
                    if m:
                        draw = int(m.group(1)); j += 1; break
                    j += 1
            if draw is None:
                i += 1; continue

            dt = None
            while j < min(i + 10, len(lines)):
                m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})", lines[j])
                if m:
                    try:
                        dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M")
                    except Exception:
                        dt = None
                    j += 1
                    break
                j += 1
            if dt is None:
                i += 1; continue

            nums = []
            while j < len(lines) and len(nums) < 20:
                if "Çekiliş no" in lines[j] or "çekiliş no" in lines[j].lower():
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

    # Aynı çekilişi tekilleştir, kronolojik sıraya koy
    best = {}
    for draw, dt, nums in rows:
        best[(draw, dt)] = nums
    out = pd.DataFrame([(d, dt, ns) for (d, dt), ns in best.items()], columns=["draw", "dt", "nums"])
    out = out.sort_values(["draw", "dt"]).drop_duplicates(subset=["draw"], keep="last").reset_index(drop=True)
    return out


def nums_to_mask(nums: Iterable[int]) -> int:
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m


def mask_to_nums(mask: int) -> Tuple[int, ...]:
    out = []
    m = int(mask)
    while m:
        lsb = m & -m
        out.append(lsb.bit_length())  # bit 0 -> sayı 1
        m ^= lsb
    return tuple(out)


def family_mask(nums: Iterable[int]) -> int:
    return nums_to_mask(nums)


def family_text(nums: Iterable[int]) -> str:
    return "-".join(f"{int(n):02d}" for n in nums)


def bits_to_indices(b: int) -> List[int]:
    out = []
    x = int(b)
    while x:
        lsb = x & -x
        out.append(lsb.bit_length() - 1)
        x ^= lsb
    return out


def build_vertical_bits(df: pd.DataFrame):
    num_bits = [0] * 81
    draw_masks = []
    for i, nums in enumerate(df["nums"]):
        bit = 1 << i
        m = nums_to_mask(nums)
        draw_masks.append(m)
        for n in nums:
            num_bits[int(n)] |= bit
    lows = np.array([m & LOW_MASK for m in draw_masks], dtype=np.uint64)
    highs = np.array([(m >> 64) & LOW_MASK for m in draw_masks], dtype=np.uint64)
    return num_bits, draw_masks, lows, highs


def occurrence_bits(nums: Tuple[int, ...], num_bits: List[int]) -> int:
    b = num_bits[nums[0]]
    for n in nums[1:]:
        b &= num_bits[n]
        if not b:
            break
    return b

# --------------------------------------------------------------------------------------
# RİTİM SINIFLANDIRMA
# --------------------------------------------------------------------------------------
def _best_equal_run(gaps: List[int]):
    best = None
    i = 0
    while i < len(gaps):
        j = i + 1
        while j < len(gaps) and gaps[j] == gaps[i]:
            j += 1
        run = j - i
        if run >= 2 and (best is None or run > best[0]):
            best = (run, i, j, gaps[i])
        i = j
    return best


def classify_rhythms(draws: List[int], near_tol: int = 1):
    """Aktivasyon çekilişleri arasındaki ardışık farklardan ritimleri bulur."""
    if len(draws) < 3:
        return [], [], []
    gaps = [int(draws[i + 1] - draws[i]) for i in range(len(draws) - 1)]
    labels = []
    details = []

    # DÜZ: en az d,d (3 aktivasyon). Daha uzunu otomatik yakalanır.
    eq = _best_equal_run(gaps)
    if eq:
        run, i, j, d = eq
        labels.append("DUZ")
        details.append(f"DUZ:+{d} x{run}")

    # YAKIN DÜZ: en az 3 gap, yayılım tolerans içinde; tam eşit değil.
    if len(gaps) >= 3:
        best_near = None
        for w in range(min(6, len(gaps)), 2, -1):
            for i in range(0, len(gaps) - w + 1):
                seg = gaps[i:i + w]
                if max(seg) - min(seg) <= near_tol and len(set(seg)) > 1:
                    best_near = seg
                    break
            if best_near:
                break
        if best_near:
            labels.append("YAKIN")
            details.append("YAKIN:" + ",".join(f"+{x}" for x in best_near))

    # ZİKZAK / ABAB
    for i in range(len(gaps) - 3):
        a, b, c, d = gaps[i:i + 4]
        if a == c and b == d and a != b:
            labels.append("ZIKZAK")
            details.append(f"ZIKZAK:+{a},+{b},+{a},+{b}")
            break

    # ÇİFT RİTİM: A,A,B,A,A,B
    for i in range(len(gaps) - 5):
        s = gaps[i:i + 6]
        if s[0] == s[1] == s[3] == s[4] and s[2] == s[5] and s[0] != s[2]:
            labels.append("CIFT_RITIM")
            details.append("CIFT:" + ",".join(f"+{x}" for x in s))
            break

    # 3'lü tekrar: ABCABC
    for i in range(len(gaps) - 5):
        s = gaps[i:i + 6]
        if s[:3] == s[3:6] and len(set(s[:3])) > 1:
            labels.append("TEKRAR_3")
            details.append("TEKRAR3:" + ",".join(f"+{x}" for x in s))
            break

    # Katlanarak / azalarak: aynı tam sayı oranıyla en az 3 gap
    for i in range(len(gaps) - 2):
        a, b, c = gaps[i:i + 3]
        if a > 0 and b > a and b % a == 0:
            q = b // a
            if q >= 2 and c == b * q:
                labels.append("KATLANARAK")
                details.append(f"KATLANARAK:x{q} ({a},{b},{c})")
                break
    for i in range(len(gaps) - 2):
        a, b, c = gaps[i:i + 3]
        if c > 0 and a > b and a % b == 0 and b % c == 0:
            q1, q2 = a // b, b // c
            if q1 == q2 and q1 >= 2:
                labels.append("AZALARAK")
                details.append(f"AZALARAK:/{q1} ({a},{b},{c})")
                break

    # Basamaklı: gap farkları sabit ve sıfır değil; en az 4 gap tercih, 3 gap da kabul.
    for i in range(len(gaps) - 2):
        a, b, c = gaps[i:i + 3]
        step = b - a
        if step != 0 and c - b == step and min(a, b, c) > 0:
            # mümkünse 4. gap da aynı adımda mı?
            seg = [a, b, c]
            if i + 3 < len(gaps) and gaps[i + 3] - c == step and gaps[i + 3] > 0:
                seg.append(gaps[i + 3])
            labels.append("BASAMAKLI")
            details.append("BASAMAK:" + ",".join(f"+{x}" for x in seg))
            break

    # Tekilleştir
    labels = list(dict.fromkeys(labels))
    details = list(dict.fromkeys(details))
    return labels, details, gaps


def time_character(idxs: List[int], df: pd.DataFrame) -> str:
    if not idxs:
        return ""
    dts = [pd.Timestamp(df.iloc[i]["dt"]) for i in idxs]
    mins = [x.minute for x in dts]
    hrs = [x.hour for x in dts]
    parts = []
    if len(set(mins)) == 1:
        parts.append(f"dakika=:{mins[0]:02d}")
    else:
        mc = Counter(mins).most_common(1)[0]
        if mc[1] >= 3:
            parts.append(f"dakika_baskin=:{mc[0]:02d}({mc[1]}/{len(mins)})")
    if len(set(hrs)) == 1:
        parts.append(f"saat={hrs[0]:02d}:xx")
    else:
        hc = Counter(hrs).most_common(1)[0]
        if hc[1] >= 3:
            parts.append(f"saat_baskin={hc[0]:02d}:xx({hc[1]}/{len(hrs)})")
    return ";".join(parts)

# --------------------------------------------------------------------------------------
# SQLITE
# --------------------------------------------------------------------------------------
def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS progress(
            data_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            method TEXT NOT NULL,
            cursor INTEGER NOT NULL DEFAULT 0,
            done INTEGER NOT NULL DEFAULT 0,
            scanned INTEGER NOT NULL DEFAULT 0,
            rhythmic_found INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY(data_hash, size)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS results(
            data_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            family_mask TEXT NOT NULL,
            family TEXT NOT NULL,
            support INTEGER NOT NULL,
            draws TEXT NOT NULL,
            times TEXT NOT NULL,
            gaps TEXT NOT NULL,
            rhythm_types TEXT NOT NULL,
            rhythm_detail TEXT NOT NULL,
            time_character TEXT NOT NULL,
            PRIMARY KEY(data_hash, size, family_mask)
        )
        """
    )
    con.commit()
    return con


def ensure_progress(con, data_hash: str, k: int, method: str):
    con.execute(
        """INSERT OR IGNORE INTO progress(data_hash,size,method,cursor,done,scanned,rhythmic_found,updated_at)
           VALUES(?,?,?,?,0,0,0,?)""",
        (data_hash, k, method, 0, datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()


def get_progress(con, data_hash: str, k: int):
    r = con.execute(
        "SELECT method,cursor,done,scanned,rhythmic_found FROM progress WHERE data_hash=? AND size=?",
        (data_hash, k),
    ).fetchone()
    return r or ("", 0, 0, 0, 0)


def update_progress(con, data_hash: str, k: int, cursor: int, done: int, scanned: int, found: int):
    con.execute(
        """UPDATE progress SET cursor=?,done=?,scanned=?,rhythmic_found=?,updated_at=?
           WHERE data_hash=? AND size=?""",
        (cursor, done, scanned, found, datetime.now().isoformat(timespec="seconds"), data_hash, k),
    )
    con.commit()


def insert_result(con, data_hash: str, k: int, nums: Tuple[int, ...], occ_b: int,
                  df: pd.DataFrame, near_tol: int = 1) -> bool:
    support = int(occ_b.bit_count())
    if support < MIN_ACTIVATIONS:
        return False
    idxs = bits_to_indices(occ_b)
    draw_list = [int(df.iloc[i]["draw"]) for i in idxs]
    labels, details, gaps = classify_rhythms(draw_list, near_tol=near_tol)
    if not labels:
        return False

    times = [pd.Timestamp(df.iloc[i]["dt"]).strftime("%Y-%m-%d %H:%M") for i in idxs]
    fm = str(family_mask(nums))
    cur = con.execute(
        """INSERT OR IGNORE INTO results(
               data_hash,size,family_mask,family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data_hash, k, fm, family_text(nums), support,
            ",".join(map(str, draw_list)),
            " | ".join(times),
            ",".join(map(str, gaps)),
            ",".join(labels),
            " | ".join(details),
            time_character(idxs, df),
        ),
    )
    return cur.rowcount > 0

# --------------------------------------------------------------------------------------
# TARAMA — 2..6 TAM EVREN / 7..10 KESİŞİM ADAYI
# --------------------------------------------------------------------------------------
def scan_exhaustive_k(con, data_hash: str, k: int, num_bits: List[int], df: pd.DataFrame,
                      near_tol: int, progress_box, status_box, stop_after_seconds: int = 0):
    """1..80'den C(80,k) aileyi prefix-prefix tarar. RAM sabittir, prefix checkpointlidir."""
    method, cursor, done, scanned, found = get_progress(con, data_hash, k)
    if done:
        return scanned, found, True

    max_first = 80 - k + 1  # ilk sayı 1..max_first
    start_first = max(1, int(cursor) if int(cursor) > 0 else 1)
    started = time.time()
    pending_commit = 0

    # K için teorik toplam kombinasyon
    total = math.comb(80, k)

    for first in range(start_first, max_first + 1):
        tail_iter = itertools.combinations(range(first + 1, 81), k - 1)
        first_bits = num_bits[first]
        for tail in tail_iter:
            nums = (first,) + tail
            b = first_bits
            # tail AND; destek 3 altına indiğinde yine daha sonra yükselemez ama bu aile tamamlandı,
            # erken 0 kesmesi yeterli.
            for n in tail:
                b &= num_bits[n]
                if not b:
                    break
            scanned += 1
            if b and b.bit_count() >= MIN_ACTIVATIONS:
                if insert_result(con, data_hash, k, nums, b, df, near_tol):
                    found += 1
                    pending_commit += 1
                    if pending_commit >= 250:
                        con.commit(); pending_commit = 0

        # prefix tamamlanınca checkpoint
        next_first = first + 1
        update_progress(con, data_hash, k, next_first, 0, scanned, found)
        frac = min(1.0, scanned / max(1, total))
        progress_box.progress(frac, text=f"{k}'li: {scanned:,}/{total:,} aile tarandı · ritimli {found:,}".replace(",", "."))
        status_box.caption(f"Checkpoint: {k}'li ilk sayı {first} tamamlandı. APP kapanırsa buradan devam eder.")
        if stop_after_seconds and time.time() - started >= stop_after_seconds:
            con.commit()
            return scanned, found, False

    con.commit()
    update_progress(con, data_hash, k, max_first + 1, 1, scanned, found)
    progress_box.progress(1.0, text=f"{k}'li tamamlandı · ritimli {found:,}".replace(",", "."))
    return scanned, found, True


def scan_pair_candidates_k(con, data_hash: str, k: int, num_bits: List[int], df: pd.DataFrame,
                           lows: np.ndarray, highs: np.ndarray, near_tol: int,
                           progress_box, status_box, stop_after_seconds: int = 0):
    """
    Büyük ailelerde bütün C(80,k) evrenini üretmek yerine gerçek çekiliş çiftlerinin
    ortak kümelerinden k'li aday üretir. Bir aile en az 2 kez tam olduysa en az bir çiftin
    kesişiminde bulunmak zorundadır. Destek ve ritim daha sonra tam veri üzerinde doğrulanır.

    Bellek: yalnız mevcut çekilişin önceki çekilişlerle kesişim vektörü + bulunan ritimli sonuçlar.
    Non-rhythmic adaylar kalıcı tutulmaz.
    """
    method, cursor, done, scanned, found = get_progress(con, data_hash, k)
    if done:
        return scanned, found, True

    n = len(df)
    start_i = max(1, int(cursor) if int(cursor) > 0 else 1)
    started = time.time()
    # Aynı ritimli aile aynı taramada birçok çiftten gelebilir. Sadece bulunan sonuçları RAM'de tut.
    existing = {
        row[0] for row in con.execute(
            "SELECT family_mask FROM results WHERE data_hash=? AND size=?", (data_hash, k)
        ).fetchall()
    }
    pending_commit = 0

    for i in range(start_i, n):
        inter_lo = np.bitwise_and(lows[:i], lows[i])
        inter_hi = np.bitwise_and(highs[:i], highs[i])
        counts = np.bitwise_count(inter_lo).astype(np.uint16) + np.bitwise_count(inter_hi).astype(np.uint16)
        js = np.flatnonzero(counts >= k)

        for j in js.tolist():
            m = int(inter_lo[j]) | (int(inter_hi[j]) << 64)
            root_nums = mask_to_nums(m)
            # Ortak kök içinden gerçek k'li aile adayları
            for nums in itertools.combinations(root_nums, k):
                scanned += 1
                fm = str(family_mask(nums))
                if fm in existing:
                    continue
                b = occurrence_bits(nums, num_bits)
                if b.bit_count() < MIN_ACTIVATIONS:
                    continue
                before = found
                if insert_result(con, data_hash, k, nums, b, df, near_tol):
                    existing.add(fm)
                    found += 1
                    pending_commit += 1
                    if pending_commit >= 250:
                        con.commit(); pending_commit = 0

        update_progress(con, data_hash, k, i + 1, 0, scanned, found)
        if i % 10 == 0 or i == n - 1:
            frac = (i + 1) / max(1, n)
            progress_box.progress(frac, text=f"{k}'li: çekiliş {i+1:,}/{n:,} · aday {scanned:,} · ritimli {found:,}".replace(",", "."))
            status_box.caption(f"Checkpoint: {k}'li tarama çekiliş indeks {i+1} seviyesinde.")

        if stop_after_seconds and time.time() - started >= stop_after_seconds:
            con.commit()
            return scanned, found, False

    con.commit()
    update_progress(con, data_hash, k, n, 1, scanned, found)
    progress_box.progress(1.0, text=f"{k}'li tamamlandı · ritimli {found:,}".replace(",", "."))
    return scanned, found, True

# --------------------------------------------------------------------------------------
# RAPOR
# --------------------------------------------------------------------------------------
def build_report(con, data_hash: str, df: pd.DataFrame, source: str) -> str:
    lines = []
    lines.append("=" * 130)
    lines.append("HIZLI ON — AİLE & RİTİM TEK RAPOR")
    lines.append("=" * 130)
    lines.append(f"APP: {APP_VERSION}")
    lines.append(f"Kaynak: {source}")
    lines.append(f"Veri SHA256: {data_hash}")
    lines.append(f"Çekiliş: {len(df)}")
    lines.append(f"Gün: {df['dt'].dt.date.nunique()}")
    if not df.empty:
        lines.append(f"Aralık: {df.iloc[0]['dt']:%d.%m.%Y %H:%M} -> {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}")
    lines.append("")
    lines.append("KİLİTLİ AKTİVASYON TANIMI: Ailenin bütün üyeleri AYNI TEK ÇEKİLİŞTE birlikte bulunmalıdır.")
    lines.append("Saat/pencere içinde birikme aktivasyon sayılmaz. Ana ritim mesafesi çekiliş numarası farkıdır.")
    lines.append("Ritimler: DUZ, YAKIN, ZIKZAK, CIFT_RITIM, TEKRAR_3, KATLANARAK, AZALARAK, BASAMAKLI.")
    lines.append("")

    for k in SIZES:
        p = con.execute(
            "SELECT method,cursor,done,scanned,rhythmic_found FROM progress WHERE data_hash=? AND size=?",
            (data_hash, k),
        ).fetchone()
        if p:
            lines.append(
                f"{k}'li durum | yöntem={p[0]} | tamam={p[2]} | taranan_aday={p[3]} | ritimli_aile={p[4]}"
            )
    lines.append("")

    for k in SIZES:
        rows = con.execute(
            """SELECT family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
               FROM results WHERE data_hash=? AND size=?
               ORDER BY support DESC, family ASC""",
            (data_hash, k),
        ).fetchall()
        lines.append("#" * 130)
        lines.append(f"{k}'Lİ AİLELER — RİTİMLİ TAM AKTİVASYONLAR | adet={len(rows)}")
        lines.append("#" * 130)
        if not rows:
            lines.append("Ritim kaydı yok / tarama henüz tamamlanmamış olabilir.")
            lines.append("")
            continue
        for family, support, draws, times, gaps, rtypes, rdetail, tchar in rows:
            lines.append(
                f"{family} | tam_aktivasyon={support} | ritim={rtypes} | {rdetail}"
            )
            lines.append(f"  çekilişler: {draws}")
            lines.append(f"  aralıklar: {gaps}")
            lines.append(f"  zamanlar: {times}")
            if tchar:
                lines.append(f"  zaman_karakteri: {tchar}")
        lines.append("")

    return "\n".join(lines)


def build_csv(con, data_hash: str) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["size", "family", "support", "draws", "times", "gaps", "rhythm_types", "rhythm_detail", "time_character"])
    for row in con.execute(
        """SELECT size,family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
           FROM results WHERE data_hash=? ORDER BY size,support DESC,family""",
        (data_hash,),
    ):
        w.writerow(row)
    return out.getvalue()

# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------
st.title("🧬 Hızlı On — Aile & Ritim Laboratuvarı")
st.caption(
    "Tek çekilişte tam aktivasyon • 2'li→10'lu sırayla • çekiliş mesafesi ritimleri • "
    "düşük RAM • SQLite checkpoint • GitHub veri.txt otomatik"
)

with st.expander("Kilitli kurallar", expanded=False):
    st.write(
        "Bir 6'lı aile ancak 6 sayının tamamı aynı çekilişin REAL20'sinde birlikteyse 6/6 aktive sayılır. "
        "Aynı kural 2'li–10'lu bütün aileler için geçerlidir. Saat içinde parça parça tamamlanma kabul edilmez."
    )
    st.write(
        "Ritim hesabı tam aktivasyon çekiliş numaralarının farklarından yapılır: düz, yakın, zikzak, "
        "katlanarak, azalarak, basamaklı, ABAB/çift ve ABCABC tekrar desenleri."
    )

uploaded = st.file_uploader("İstersen veri.txt yükle (boş bırakırsan GitHub/yerel veri.txt otomatik okunur)", type=["txt"])
text, source = load_data_text(uploaded)

if not text:
    st.error(source)
    st.stop()

df = parse_draws(text)
if df.empty:
    st.error("veri.txt bulundu ama geçerli 20 sayılık çekiliş satırı okunamadı.")
    st.stop()

df["dt"] = pd.to_datetime(df["dt"])
data_hash = sha256_text(text)

# Veri kalite özeti
by_day = df.groupby(df["dt"].dt.date).size()
full217 = int((by_day == 217).sum())
partial = int((by_day != 217).sum())

a,b,c,d = st.columns(4)
a.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
b.metric("Gün", int(df["dt"].dt.date.nunique()))
c.metric("217 tam gün", full217)
d.metric("Eksik/farklı gün", partial)
st.success(f"Veri tanındı — {source}")
st.caption(f"İlk: #{int(df.iloc[0]['draw'])} {df.iloc[0]['dt']:%d.%m.%Y %H:%M} · Son: #{int(df.iloc[-1]['draw'])} {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}")

# Aynı draw no sırasındaki boşluk bilgisi
if len(df) > 1:
    draw_diffs = np.diff(df["draw"].to_numpy(dtype=np.int64))
    missing_steps = int(np.sum(np.maximum(draw_diffs - 1, 0)))
else:
    missing_steps = 0
if missing_steps:
    st.warning(f"Çekiliş numarası sırasındaki toplam boşluk: {missing_steps}. Ritim hesabında gerçek çekiliş numarası farkı kullanılacak.")

near_tol = st.number_input("Yakın ritim toleransı (çekiliş farkı)", min_value=0, max_value=10, value=1, step=1)
run_slice = st.selectbox(
    "Tek basışta çalışma süresi",
    ["Tamamlanana kadar", "5 dakika", "10 dakika", "20 dakika"],
    index=0,
    help="Uzun taramada süre sınırı seçersen checkpoint kaydedilir; aynı düğmeye tekrar basınca devam eder.",
)
limit_map = {"Tamamlanana kadar": 0, "5 dakika": 300, "10 dakika": 600, "20 dakika": 1200}
stop_after = limit_map[run_slice]

con = db_connect()
# Farklı veri hashlerinde eski sonuçlar kalabilir ama karışmaz.
for k in SIZES:
    method = "EXHAUSTIVE_80" if k <= EXHAUSTIVE_MAX_K else "PAIR_INTERSECTION"
    ensure_progress(con, data_hash, k, method)

# Durum tablosu
prog_rows = []
for k in SIZES:
    method, cursor, done, scanned, found = get_progress(con, data_hash, k)
    prog_rows.append({
        "Aile": f"{k}'li",
        "Yöntem": method,
        "Durum": "TAMAM" if done else ("DEVAM" if scanned else "BEKLİYOR"),
        "Taranan": int(scanned),
        "Ritimli": int(found),
    })
st.dataframe(pd.DataFrame(prog_rows), use_container_width=True, hide_index=True)

col1, col2 = st.columns([2,1])
start = col1.button("▶️ ANALİZİ BAŞLAT / KALDIĞI YERDEN DEVAM ET", type="primary", use_container_width=True)
reset = col2.button("🧹 Bu veri için sonucu sıfırla", use_container_width=True)

if reset:
    con.execute("DELETE FROM results WHERE data_hash=?", (data_hash,))
    con.execute("DELETE FROM progress WHERE data_hash=?", (data_hash,))
    con.commit()
    for k in SIZES:
        method = "EXHAUSTIVE_80" if k <= EXHAUSTIVE_MAX_K else "PAIR_INTERSECTION"
        ensure_progress(con, data_hash, k, method)
    st.success("Bu veri için checkpoint ve sonuçlar sıfırlandı.")
    st.rerun()

if start:
    num_bits, draw_masks, lows, highs = build_vertical_bits(df)
    global_started = time.time()
    overall = st.progress(0.0, text="Hazırlanıyor...")
    status = st.empty()
    size_box = st.empty()

    completed_before = sum(int(get_progress(con, data_hash, k)[2]) for k in SIZES)

    for pos, k in enumerate(SIZES):
        method, cursor, done, scanned, found = get_progress(con, data_hash, k)
        if done:
            overall.progress((pos + 1) / len(SIZES), text=f"{k}'li zaten tamam — sonraki boyuta geçiliyor")
            continue

        size_box.markdown(f"### Şimdi {k}'li aileler işleniyor")
        pbox = st.progress(0.0)

        # toplam çalışma süresi seçilmişse kalan süreyi aktar
        remaining = 0
        if stop_after:
            elapsed = time.time() - global_started
            remaining = max(1, int(stop_after - elapsed))
            if remaining <= 1:
                status.info("Süre dilimi tamamlandı. Checkpoint kaydedildi; tekrar DEVAM ET'e bas.")
                break

        if k <= EXHAUSTIVE_MAX_K:
            scanned, found, done_now = scan_exhaustive_k(
                con, data_hash, k, num_bits, df, int(near_tol), pbox, status, remaining
            )
        else:
            scanned, found, done_now = scan_pair_candidates_k(
                con, data_hash, k, num_bits, df, lows, highs, int(near_tol), pbox, status, remaining
            )

        overall.progress((pos + (1 if done_now else 0)) / len(SIZES), text=f"{k}'li {'tamam' if done_now else 'checkpoint'}")
        if not done_now:
            status.info("Bu çalışma dilimi bitti. Sonuç kaydedildi; aynı düğmeye tekrar basınca kaldığı yerden devam eder.")
            break

    all_done = all(int(get_progress(con, data_hash, k)[2]) == 1 for k in SIZES)
    if all_done:
        overall.progress(1.0, text="2'liden 10'luya bütün taramalar tamamlandı.")
        status.success("Analiz tamamlandı. Tek rapor aşağıda hazır.")
    else:
        status.warning("Tarama henüz tamamlanmadı; checkpoint kaydedildi.")

# Rapor her an indirilebilir; tamamlanmamış boyutlar başlıkta görünür.
report_txt = build_report(con, data_hash, df, source)
report_csv = build_csv(con, data_hash)

st.divider()
st.subheader("📦 Tek çıktı")
rc1, rc2 = st.columns(2)
rc1.download_button(
    "⬇️ TEK TXT RAPORU İNDİR",
    data=report_txt.encode("utf-8"),
    file_name="HIZLI_ON_AILE_RITIM_TEK_RAPOR.txt",
    mime="text/plain",
    use_container_width=True,
)
rc2.download_button(
    "⬇️ CSV SONUÇLARI İNDİR",
    data=report_csv.encode("utf-8-sig"),
    file_name="HIZLI_ON_AILE_RITIM_SONUCLAR.csv",
    mime="text/csv",
    use_container_width=True,
)

# Ekranı şişirmeden yalnız örnek sonuç göster.
st.subheader("Sonuç önizleme")
preview = pd.read_sql_query(
    """SELECT size AS Boyut, family AS Aile, support AS Aktivasyon,
              rhythm_types AS Ritim, rhythm_detail AS Detay, time_character AS Zaman
       FROM results WHERE data_hash=? ORDER BY size, support DESC, family LIMIT 200""",
    con,
    params=(data_hash,),
)
if preview.empty:
    st.info("Henüz ritimli aile kaydı yok. Analizi başlat.")
else:
    st.dataframe(preview, use_container_width=True, hide_index=True, height=520)
    st.caption("Ekranda ilk 200 kayıt gösterilir; tam sonuç tek TXT/CSV dosyasındadır.")

st.caption(
    "Teknik not: 2–6 boyutlarında 1–80 aile evreni prefix-checkpoint ile düşük RAM taranır. "
    "7–10 boyutlarında büyük kombinasyon patlamasını önlemek için gerçek çekiliş çiftlerinin ortak kümelerinden aday çıkarılır; "
    "adayın tam aktivasyon sayısı ve ritmi bütün veri üzerinde tekrar doğrulanır."
)
