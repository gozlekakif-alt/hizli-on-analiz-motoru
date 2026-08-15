import base64
import json
import math
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Sayı Laboratuvarı V3 — Nota / Taşıma / Paket",
    page_icon="🎼",
    layout="wide",
)

# ============================================================
# V3 — NOTA / TAŞIMA / 2'Lİ-3'LÜ / 6 ÇEKİLİŞ / GİZLİ ADAY
# ============================================================

SLOTS = [
    "23:02","23:07","23:12","23:17","23:22","23:27",
    "23:32","23:37","23:42","23:47","23:52","23:57"
]
BASELINE = 20 / 80  # tek sayı için teorik taban = %25

DEFAULT_DATA_FILE = Path("veri.txt")
DEFAULT_GITHUB_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_GITHUB_BRANCH = "main"
DEFAULT_GITHUB_PATH = "veri.txt"


# ============================================================
# GitHub / kalıcı veri
# ============================================================

def github_config():
    token = ""
    repo = DEFAULT_GITHUB_REPO
    branch = DEFAULT_GITHUB_BRANCH
    path = DEFAULT_GITHUB_PATH
    try:
        token = str(st.secrets.get("GITHUB_TOKEN", "")).strip()
        repo = str(st.secrets.get("GITHUB_REPO", repo)).strip() or repo
        branch = str(st.secrets.get("GITHUB_BRANCH", branch)).strip() or branch
        path = str(st.secrets.get("GITHUB_DATA_PATH", path)).strip() or path
    except Exception:
        pass
    return token, repo, branch, path


def github_read_file(token, repo, branch, path):
    url = (
        f"https://api.github.com/repos/{repo}/contents/"
        f"{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sayi-laboratuvari-v3",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = base64.b64decode(payload["content"]).decode("utf-8")
    return content, payload["sha"]


def github_write_file(token, repo, branch, path, content, message):
    _, sha = github_read_file(token, repo, branch, path)
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    body = json.dumps({
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": branch,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "sayi-laboratuvari-v3",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def repo_data_text():
    try:
        token, repo, branch, path = github_config()
        if token:
            text, _ = github_read_file(token, repo, branch, path)
            return text
    except Exception:
        pass

    if DEFAULT_DATA_FILE.exists():
        return DEFAULT_DATA_FILE.read_text(encoding="utf-8")
    return ""


def normalize_result_line(draw_no, date_s, time_s, nums):
    nums = sorted(set(map(int, nums)))
    if len(nums) != 20 or any(n < 1 or n > 80 for n in nums):
        raise ValueError("Sonuç 1-80 arasında tam 20 farklı sayı içermeli.")
    return f"{int(draw_no)} | {date_s} {time_s} | {' '.join(map(str, nums))}"


def append_result_to_text(text, line):
    parts = [x.strip() for x in line.split("|")]
    if len(parts) < 3:
        raise ValueError("Geçersiz veri satırı.")
    dt_key = parts[1]
    existing = []
    replaced = False

    for raw in text.splitlines():
        if not raw.strip():
            continue
        p = [x.strip() for x in raw.split("|")]
        if len(p) >= 2 and p[1] == dt_key:
            # Aynı tarih/saat varsa güncel satırla değiştir.
            if not replaced:
                existing.append(line)
                replaced = True
            continue
        existing.append(raw.rstrip())

    if not replaced:
        existing.append(line)

    return "\n".join(existing).rstrip() + "\n"


# ============================================================
# Veri okuma / hızlı yapıştır
# ============================================================

def parse_pipe_text(text):
    rows = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line or "|" not in line:
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 3:
            continue
        try:
            draw_no = int(parts[0])
            d, t = parts[1].split()
            nums = sorted(set(int(x) for x in parts[2].split()))
        except Exception:
            continue
        if t not in SLOTS or len(nums) != 20 or any(n < 1 or n > 80 for n in nums):
            continue
        rows.append({
            "draw_no": draw_no,
            "date": d,
            "time": t,
            "numbers": nums,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["date_dt"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    df = (
        df.sort_values(["date_dt", "time", "draw_no"])
        .drop_duplicates(subset=["date", "time"], keep="last")
        .drop(columns=["date_dt"])
        .reset_index(drop=True)
    )
    return df


def parse_draw_block(text):
    """
    Kullanıcı şu biçimi aynen yapıştırabilir:

    Çekiliş no: 48597
    12.08.2026 - 23:02
    9
    ...
    80
    """
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Sonuç metni boş.")

    m_no = re.search(r"(?i)çekiliş\s*no\s*:\s*(\d+)", raw)
    m_dt = re.search(
        r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{2}:\d{2})",
        raw,
    )
    if not m_no:
        raise ValueError("Çekiliş no bulunamadı.")
    if not m_dt:
        raise ValueError("Tarih/saat bulunamadı.")

    draw_no = int(m_no.group(1))
    date_s = datetime.strptime(m_dt.group(1), "%d.%m.%Y").strftime("%d.%m.%Y")
    time_s = m_dt.group(2)

    if time_s not in SLOTS:
        raise ValueError(f"Geçersiz saat: {time_s}")

    tail = raw[m_dt.end():]
    nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", tail)]
    if len(nums) != 20 or len(set(nums)) != 20:
        raise ValueError(f"Tam 20 farklı sayı bekleniyor; {len(nums)} sayı bulundu.")

    return {
        "draw_no": draw_no,
        "date": date_s,
        "time": time_s,
        "numbers": sorted(nums),
    }


def to_date(s):
    return datetime.strptime(str(s), "%d.%m.%Y").date()


def fmt(d):
    return d.strftime("%d.%m.%Y")


def df_to_map(df):
    return {
        (str(r["date"]), str(r["time"])): set(map(int, r["numbers"]))
        for _, r in df.iterrows()
    }


def merge_session_rows(base_df):
    rows = st.session_state.get("v3_fast_rows", [])
    if not rows:
        return base_df.copy()

    add = pd.DataFrame(rows)
    out = pd.concat([base_df.copy(), add], ignore_index=True)
    out["_date"] = pd.to_datetime(out["date"], format="%d.%m.%Y")
    out["_ord"] = np.arange(len(out))
    out = (
        out.sort_values(["_date", "time", "_ord"])
        .drop_duplicates(subset=["date", "time"], keep="last")
        .drop(columns=["_date", "_ord"])
        .reset_index(drop=True)
    )
    return out


def next_target_after(date_s, time_s):
    idx = SLOTS.index(time_s)
    if idx < len(SLOTS) - 1:
        return date_s, SLOTS[idx + 1]
    return fmt(to_date(date_s) + timedelta(days=1)), "23:02"


def previous_source_key(df, target_date, target_time):
    """
    23:07..23:57 için aynı gün önceki slot.
    23:02 için bir önceki mevcut kayıt (genellikle önceki gün 23:57).
    """
    data = df_to_map(df)
    idx = SLOTS.index(target_time)

    if idx > 0:
        key = (target_date, SLOTS[idx - 1])
        return key if key in data else None

    # 23:02 -> önceki gün 23:57
    prev_day = fmt(to_date(target_date) - timedelta(days=1))
    key = (prev_day, "23:57")
    return key if key in data else None


# ============================================================
# İstatistik yardımcıları
# ============================================================

def wilson_lower(hits, n, z=1.28):
    """
    Yaklaşık %80 tek taraflı alt güven sınırı.
    Küçük örnekli 'mucize oranları' otomatik bastırır.
    """
    if n <= 0:
        return BASELINE
    p = hits / n
    den = 1 + z*z/n
    centre = p + z*z/(2*n)
    adj = z * math.sqrt((p*(1-p)/n) + z*z/(4*n*n))
    return max(0.0, (centre - adj) / den)


def shrink_rate(hits, n, prior=BASELINE, strength=8.0):
    return (hits + prior * strength) / (n + strength)


def binary_path(prev_sets, n, length=6):
    seq = list(prev_sets)[-length:]
    return "".join("1" if n in s else "0" for s in seq).rjust(length, "0")


def draw_gap(prev_sets, n, cap=6):
    g = 0
    for s in reversed(list(prev_sets)[-cap:]):
        if n in s:
            return g
        g += 1
    return cap


def adjacent_pair_count(nums):
    s = sorted(nums)
    return sum(1 for a, b in zip(s, s[1:]) if b == a + 1)


def adjacent_triple_count(nums):
    s = sorted(nums)
    return sum(
        1 for a, b, c in zip(s, s[1:], s[2:])
        if b == a + 1 and c == b + 1
    )


def rank01(series):
    x = pd.Series(series, dtype=float)
    if x.nunique(dropna=False) <= 1:
        return pd.Series([0.5] * len(x), index=x.index)
    return x.rank(method="average", pct=True)


# ============================================================
# NOTA KARAKTERİ
# ============================================================

def note_character_table(df):
    if df is None or df.empty or len(df) < 2:
        return pd.DataFrame()

    rows = []
    sets = [set(map(int, x)) for x in df["numbers"].tolist()]

    for i in range(1, len(df)):
        tgt = str(df.iloc[i]["time"])
        src = sets[i - 1]
        y = sets[i]

        # 23:02 için önceki gün 23:57 doğal kaynak olarak kabul edilir.
        if tgt != "23:02" and str(df.iloc[i]["date"]) != str(df.iloc[i-1]["date"]):
            continue

        rows.append({
            "Hedef": tgt,
            "Taşıma": len(src & y),
            "Ardışık 2li": adjacent_pair_count(y),
            "Ardışık 3lü": adjacent_triple_count(y),
            "Tek": sum(n % 2 for n in y),
            "Alt 1-40": sum(n <= 40 for n in y),
            "1-20": sum(1 <= n <= 20 for n in y),
            "21-40": sum(21 <= n <= 40 for n in y),
            "41-60": sum(41 <= n <= 60 for n in y),
            "61-80": sum(61 <= n <= 80 for n in y),
        })

    raw = pd.DataFrame(rows)
    if raw.empty:
        return raw

    out = []
    for slot in SLOTS:
        x = raw[raw["Hedef"] == slot]
        if x.empty:
            continue
        out.append({
            "Nota": slot,
            "Örnek": len(x),
            "Ort Taşıma": round(float(x["Taşıma"].mean()), 2),
            "Medyan Taşıma": round(float(x["Taşıma"].median()), 1),
            "Ort Ardışık 2li": round(float(x["Ardışık 2li"].mean()), 2),
            "3lü Görülen %": round(100 * float((x["Ardışık 3lü"] > 0).mean()), 1),
            "Ort Tek": round(float(x["Tek"].mean()), 2),
            "Ort Alt": round(float(x["Alt 1-40"].mean()), 2),
            "1-20": round(float(x["1-20"].mean()), 2),
            "21-40": round(float(x["21-40"].mean()), 2),
            "41-60": round(float(x["41-60"].mean()), 2),
            "61-80": round(float(x["61-80"].mean()), 2),
        })
    return pd.DataFrame(out)


# ============================================================
# V3 MOTOR HAZIRLAMA
# ============================================================

def historical_target_indices(df, target_time, stop_index=None):
    end = len(df) if stop_index is None else int(stop_index)
    inds = []
    for i in range(1, end):
        if str(df.iloc[i]["time"]) != str(target_time):
            continue

        # 23:02 çapraz gün olabilir; diğerleri aynı gün olmalı.
        if target_time != "23:02":
            if str(df.iloc[i]["date"]) != str(df.iloc[i-1]["date"]):
                continue
        inds.append(i)
    return inds


def build_v3_evidence(df, target_date, target_time):
    """
    Her sayı için bağımsız kanallar:
    1) Nota frekansı
    2) Elden-ele taşıma / yeni giriş
    3) 6 çekiliş yolu
    4) Dinlenme / gap
    5) 6 gün aynı nota
    6) Kaynak içindeki ikili paket taşıması
    7) Ardışık ikili/üçlü yapı desteği

    Sinyaller yalnız geçmiş hedeflerden öğrenilir.
    """
    if len(df) < 80:
        raise ValueError("V3 için daha fazla geçmiş veri gerekli.")

    data = df_to_map(df)
    source_key = previous_source_key(df, target_date, target_time)
    if source_key is None:
        raise ValueError(f"{target_date} {target_time} için kaynak çekiliş bulunamadı.")

    source_set = set(data[source_key])

    # Hedef tarihten sonraki hiçbir kayıt öğrenmeye girmesin.
    target_dt = datetime.strptime(f"{target_date} {target_time}", "%d.%m.%Y %H:%M")
    work = df.copy()
    work["_dt"] = pd.to_datetime(
        work["date"] + " " + work["time"],
        format="%d.%m.%Y %H:%M"
    )
    work = work[work["_dt"] < target_dt].drop(columns=["_dt"]).reset_index(drop=True)

    if len(work) < 60:
        raise ValueError("V3 için en az 60 geçmiş çekiliş önerilir.")

    sets = [set(map(int, x)) for x in work["numbers"].tolist()]
    inds = historical_target_indices(work, target_time)

    if len(inds) < 8:
        raise ValueError(f"{target_time} notası için yeterli geçmiş örnek yok.")

    # Son 6 gerçek çekiliş
    current_prev6 = sets[-6:]

    # Son 6 gün aynı nota
    current_date = to_date(target_date)
    prev_dates = sorted(
        {to_date(x) for x in work["date"].astype(str).unique() if to_date(x) < current_date}
    )[-6:]
    same_note_recent = []
    for d in prev_dates:
        key = (fmt(d), target_time)
        if key in df_to_map(work):
            same_note_recent.append(df_to_map(work)[key])

    # Sayaçlar
    note_hits = Counter()
    cond = defaultdict(lambda: [0, 0])
    path_counts = defaultdict(lambda: [0, 0])
    suffix_counts = defaultdict(lambda: [0, 0])
    gap_counts = defaultdict(lambda: [0, 0])
    pair_src = defaultdict(int)
    pair_survive = defaultdict(int)
    adj_pair_cond = defaultdict(lambda: [0, 0])
    adj_trip_cond = defaultdict(lambda: [0, 0])

    for i in inds:
        src = sets[i - 1]
        y = sets[i]
        prev6 = sets[max(0, i-6):i]

        for n in y:
            note_hits[n] += 1

        for n in range(1, 81):
            present = n in src
            cond[(n, present)][1] += 1
            cond[(n, present)][0] += int(n in y)

            p6 = binary_path(prev6, n, 6)
            path_counts[(n, p6)][1] += 1
            path_counts[(n, p6)][0] += int(n in y)

            p3 = p6[-3:]
            suffix_counts[(n, p3)][1] += 1
            suffix_counts[(n, p3)][0] += int(n in y)

            g = draw_gap(prev6, n, 6)
            gap_counts[(n, g)][1] += 1
            gap_counts[(n, g)][0] += int(n in y)

            near_pair = ((n-1) in src) or ((n+1) in src)
            adj_pair_cond[(n, near_pair)][1] += 1
            adj_pair_cond[(n, near_pair)][0] += int(n in y)

            in_triple = (
                ((n-2) in src and (n-1) in src)
                or ((n-1) in src and (n+1) in src)
                or ((n+1) in src and (n+2) in src)
            )
            adj_trip_cond[(n, in_triple)][1] += 1
            adj_trip_cond[(n, in_triple)][0] += int(n in y)

        ss = sorted(src)
        for a, b in combinations(ss, 2):
            pair_src[(a, b)] += 1
            if a in y and b in y:
                pair_survive[(a, b)] += 1

    n_note = len(inds)

    rows = []
    for n in range(1, 81):
        present = n in source_set
        p6 = binary_path(current_prev6, n, 6)
        p3 = p6[-3:]
        gap = draw_gap(current_prev6, n, 6)

        # 1) Nota karakteri
        note_h = note_hits[n]
        note_rate = shrink_rate(note_h, n_note, strength=10)
        note_lb = wilson_lower(note_h, n_note)

        # 2) Elden ele / yeni giriş
        h, c = cond[(n, present)]
        carry_rate = shrink_rate(h, c, strength=8)
        carry_lb = wilson_lower(h, c)

        # 3) 6 çekiliş yolu — exact + son3 fallback
        ph, pc = path_counts[(n, p6)]
        sh, sc = suffix_counts[(n, p3)]
        path_exact = shrink_rate(ph, pc, strength=7)
        path_suffix = shrink_rate(sh, sc, strength=9)
        # exact ancak yeterli destek varsa ağırlık alsın
        path_rate = (
            0.65 * path_exact + 0.35 * path_suffix
            if pc >= 3 else path_suffix
        )
        path_support = max(pc, sc)

        # 4) Dinlenme
        gh, gc = gap_counts[(n, gap)]
        gap_rate = shrink_rate(gh, gc, strength=8)
        gap_lb = wilson_lower(gh, gc)

        # 5) Son 6 gün aynı nota
        if same_note_recent:
            day_hits = sum(n in s for s in same_note_recent)
            day6_rate = (day_hits + 1.5) / (len(same_note_recent) + 6.0)
        else:
            day_hits = 0
            day6_rate = BASELINE

        # 6) ikili taşıma paketi
        pair_rates = []
        pair_details = []
        if present:
            for m in source_set:
                if m == n:
                    continue
                key = tuple(sorted((n, m)))
                ps = pair_src[key]
                if ps >= 5:
                    surv = pair_survive[key]
                    r = shrink_rate(surv, ps, prior=BASELINE*BASELINE, strength=5)
                    pair_rates.append(r)
                    pair_details.append((r, m, surv, ps))
        pair_details.sort(reverse=True)
        pair_rate = pair_details[0][0] if pair_details else 0.0
        best_pair = (
            f"{n}-{pair_details[0][1]} ({pair_details[0][2]}/{pair_details[0][3]})"
            if pair_details else ""
        )

        # 7) ardışık yapı bağlamı
        near_pair_now = ((n-1) in source_set) or ((n+1) in source_set)
        ah, ac = adj_pair_cond[(n, near_pair_now)]
        adj2_rate = shrink_rate(ah, ac, strength=8)

        in_trip_now = (
            ((n-2) in source_set and (n-1) in source_set)
            or ((n-1) in source_set and (n+1) in source_set)
            or ((n+1) in source_set and (n+2) in source_set)
        )
        th, tc = adj_trip_cond[(n, in_trip_now)]
        adj3_rate = shrink_rate(th, tc, strength=8)

        rows.append({
            "Sayı": n,
            "Kaynakta": present,
            "6 Yol": p6,
            "Gap": gap,
            "Nota": note_rate,
            "NotaLB": note_lb,
            "Taşıma": carry_rate,
            "TaşımaLB": carry_lb,
            "6Ç": path_rate,
            "6Ç Destek": path_support,
            "Dinlenme": gap_rate,
            "DinlenmeLB": gap_lb,
            "6 Gün": day6_rate,
            "6 Gün Hit": day_hits,
            "Paket": pair_rate,
            "En İyi Paket": best_pair,
            "Ard2": adj2_rate,
            "Ard3": adj3_rate,
        })

    tab = pd.DataFrame(rows)

    # Her kanal kendi içinde yüzdelik sıralamaya çevrilir.
    signal_cols = ["Nota", "Taşıma", "6Ç", "Dinlenme", "6 Gün", "Paket", "Ard2", "Ard3"]
    for c in signal_cols:
        tab[c + " %"] = rank01(tab[c])

    # Güvenli/aktif sinyal: oran tabanın üstünde ve destek varsa.
    tab["Nota Oy"] = (tab["NotaLB"] > BASELINE * 0.96).astype(int)
    tab["Taşıma Oy"] = (tab["TaşımaLB"] > BASELINE * 0.96).astype(int)
    tab["6Ç Oy"] = (
        (tab["6Ç"] > BASELINE * 1.05) & (tab["6Ç Destek"] >= 4)
    ).astype(int)
    tab["Dinlenme Oy"] = (tab["DinlenmeLB"] > BASELINE * 0.96).astype(int)
    tab["6G Oy"] = (
        (tab["6 Gün Hit"] >= 2) & (tab["6 Gün"] > BASELINE)
    ).astype(int)
    tab["Paket Oy"] = (
        tab["Paket"] > (BASELINE * BASELINE * 1.15)
    ).astype(int)
    tab["Ard Oy"] = (
        (tab["Ard2"] > BASELINE * 1.05) | (tab["Ard3"] > BASELINE * 1.05)
    ).astype(int)

    vote_cols = ["Nota Oy","Taşıma Oy","6Ç Oy","Dinlenme Oy","6G Oy","Paket Oy","Ard Oy"]
    tab["Bağımsız Oy"] = tab[vote_cols].sum(axis=1)

    # Ana skor yalnız pozitif liftlerin yumuşak birleşimi.
    # Tek yüksek puan bütün kuponu ele geçiremesin.
    weights = {
        "Nota %": 0.14,
        "Taşıma %": 0.20,
        "6Ç %": 0.18,
        "Dinlenme %": 0.14,
        "6 Gün %": 0.10,
        "Paket %": 0.10,
        "Ard2 %": 0.07,
        "Ard3 %": 0.07,
    }
    tab["V3 Puan"] = sum(tab[c] * w for c, w in weights.items())

    # Konsensüs bonusu; tek motor değil 3+ bağımsız kanala ödül.
    tab["V3 Puan"] += np.maximum(0, tab["Bağımsız Oy"] - 2) * 0.035

    # Orta/düşük skorlu ama çoklu kanalda güçlü "gizli" aday işareti.
    score_rank = tab["V3 Puan"].rank(method="first", ascending=False)
    tab["Ham Sıra"] = score_rank.astype(int)
    tab["Gizli Aday"] = (
        (tab["Ham Sıra"] >= 9)
        & (tab["Ham Sıra"] <= 50)
        & (tab["Bağımsız Oy"] >= 3)
        & (
            (tab["6Ç %"] >= 0.78)
            | (tab["Dinlenme %"] >= 0.78)
            | (tab["Paket %"] >= 0.78)
            | (tab["Ard3 %"] >= 0.78)
        )
    )

    tab = tab.sort_values(
        ["V3 Puan", "Bağımsız Oy", "Sayı"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    meta = {
        "source_key": source_key,
        "source_set": source_set,
        "target_date": target_date,
        "target_time": target_time,
        "note_examples": len(inds),
        "same_note_recent_days": len(same_note_recent),
    }
    return tab, meta


def select_v3_coupon(tab):
    """
    7 koltuğun tamamı Top-7 değildir.

    Koltuk 1-2: ana konsensüs
    Koltuk 3: elden-ele taşıma
    Koltuk 4: dinlenip dönüş
    Koltuk 5: 6 çekiliş ritmi
    Koltuk 6: ikili/3lü paket
    Koltuk 7: orta/düşük skordan Gizli Aday

    Bu yapı 'yüksek puana takılı kalma' sorununu kırar.
    """
    selected = []
    reason = {}

    def add_from(frame, label):
        for _, r in frame.iterrows():
            n = int(r["Sayı"])
            if n not in selected:
                selected.append(n)
                reason[n] = label
                return True
        return False

    # 1-2 konsensüs
    core = tab.sort_values(
        ["Bağımsız Oy", "V3 Puan", "Sayı"],
        ascending=[False, False, True]
    )
    add_from(core, "Konsensüs")
    add_from(core, "Konsensüs")

    # 3 taşıma koltuğu
    carry = tab[tab["Kaynakta"]].sort_values(
        ["Taşıma %", "Bağımsız Oy", "V3 Puan"],
        ascending=False
    )
    add_from(carry, "Elden Ele")

    # 4 dinlenme koltuğu
    rest = tab[~tab["Kaynakta"]].sort_values(
        ["Dinlenme %", "6Ç %", "Bağımsız Oy", "V3 Puan"],
        ascending=False
    )
    add_from(rest, "Dinlenip Dönüş")

    # 5 6-çekiliş ritmi
    rhythm = tab.sort_values(
        ["6Ç %", "6 Gün %", "Bağımsız Oy", "V3 Puan"],
        ascending=False
    )
    add_from(rhythm, "6 Çekiliş Ritmi")

    # 6 paket / ardışık
    package = tab.sort_values(
        ["Paket %", "Ard3 %", "Ard2 %", "Bağımsız Oy", "V3 Puan"],
        ascending=False
    )
    add_from(package, "2li/3lü Paket")

    # 7 gizli aday — özellikle Top-8 dışından
    hidden = tab[tab["Gizli Aday"]].sort_values(
        ["Bağımsız Oy", "6Ç %", "Dinlenme %", "Paket %", "V3 Puan"],
        ascending=False
    )
    if not add_from(hidden, "Gizli Aday"):
        mid = tab[(tab["Ham Sıra"] >= 9) & (tab["Ham Sıra"] <= 45)].sort_values(
            ["Bağımsız Oy", "6Ç %", "Dinlenme %", "Paket %", "V3 Puan"],
            ascending=False
        )
        add_from(mid, "Gizli Aday")

    # eksik kaldıysa genel konsensüsle tamamla
    while len(selected) < 7:
        if not add_from(core, "Tamamlama"):
            break

    selected = selected[:7]
    return selected, reason


# ============================================================
# Walk-forward test
# ============================================================

def walk_forward_v3(df, test_count=60):
    if len(df) < 180:
        return pd.DataFrame()

    start = max(160, len(df) - int(test_count))
    rows = []

    for i in range(start, len(df)):
        target = df.iloc[i]
        train = df.iloc[:i].copy()

        try:
            tab, meta = build_v3_evidence(
                train,
                str(target["date"]),
                str(target["time"]),
            )
            coupon, reason = select_v3_coupon(tab)
        except Exception:
            continue

        actual = set(map(int, target["numbers"]))
        hits = sorted(set(coupon) & actual)

        # hidden seat hit?
        hidden_num = next((n for n in coupon if reason.get(n) == "Gizli Aday"), None)

        rows.append({
            "Çekiliş": int(target["draw_no"]),
            "Tarih": str(target["date"]),
            "Saat": str(target["time"]),
            "Kupon": "-".join(map(str, coupon)),
            "İsabet": len(hits),
            "Tutan": "-".join(map(str, hits)),
            "Gizli": hidden_num if hidden_num is not None else "",
            "Gizli Tuttu": int(hidden_num in actual) if hidden_num is not None else 0,
        })

    return pd.DataFrame(rows)


# ============================================================
# 2'li / 3'lü analiz
# ============================================================

def package_analysis(df, target_time):
    sets = [set(map(int, x)) for x in df["numbers"].tolist()]
    inds = historical_target_indices(df, target_time)

    pair_src = defaultdict(int)
    pair_survive = defaultdict(int)
    adj2_target = Counter()
    adj3_target = Counter()

    for i in inds:
        src = sets[i - 1]
        y = sets[i]

        for a, b in combinations(sorted(src), 2):
            pair_src[(a, b)] += 1
            if a in y and b in y:
                pair_survive[(a, b)] += 1

        sy = sorted(y)
        for a, b in zip(sy, sy[1:]):
            if b == a + 1:
                adj2_target[(a, b)] += 1
        for a, b, c in zip(sy, sy[1:], sy[2:]):
            if b == a + 1 and c == b + 1:
                adj3_target[(a, b, c)] += 1

    rows = []
    for pair, n in pair_src.items():
        if n < 5:
            continue
        h = pair_survive[pair]
        rate = h / n if n else 0
        rows.append({
            "Paket": f"{pair[0]}-{pair[1]}",
            "Kaynak Görünüm": n,
            "Birlikte Taşındı": h,
            "Oran %": round(100*rate, 1),
            "Wilson Alt %": round(100*wilson_lower(h, n, z=1.0), 1),
        })
    pair_df = pd.DataFrame(rows)
    if not pair_df.empty:
        pair_df = pair_df.sort_values(
            ["Wilson Alt %", "Kaynak Görünüm"],
            ascending=False
        ).reset_index(drop=True)

    adj2_df = pd.DataFrame([
        {"Ardışık 2li": f"{a}-{b}", "Hedefte Görülme": c}
        for (a, b), c in adj2_target.most_common(30)
    ])
    adj3_df = pd.DataFrame([
        {"Ardışık 3lü": f"{a}-{b}-{c}", "Hedefte Görülme": n}
        for (a, b, c), n in adj3_target.most_common(30)
    ])
    return pair_df, adj2_df, adj3_df


# ============================================================
# UI / Veri yükleme
# ============================================================

st.title("🎼 Sayı Laboratuvarı V3 — Nota / Taşıma / Paket")
st.caption(
    "Nota karakteri + elden-ele taşıma + 6 çekiliş ritmi + dinlenip dönüş + "
    "2'li/3'lü paket + 6 gün + orta/düşük skordan Gizli Aday."
)

with st.sidebar:
    st.header("Veri")
    uploaded = st.file_uploader(
        "İstersen TXT ile geçici override et",
        type=["txt"],
    )
    st.caption("TXT: çekiliş_no | GG.AA.YYYY SS:DD | 20 sayı")

try:
    if uploaded is not None:
        base_df = parse_pipe_text(uploaded.read().decode("utf-8"))
        source_label = f"Geçici dosya: {uploaded.name}"
    else:
        text = repo_data_text()
        base_df = parse_pipe_text(text)
        source_label = "Repo veri.txt (token varsa GitHub canlı)"
except Exception as exc:
    st.error(f"Veri okunamadı: {exc}")
    st.stop()

if base_df.empty:
    st.error("Geçerli veri bulunamadı.")
    st.stop()

df = merge_session_rows(base_df)

st.caption(
    f"📂 {source_label} · {len(df)} çekiliş · "
    f"{df['date'].nunique()} gün · son: "
    f"{df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

tabs = st.tabs([
    "⚡ Hızlı 5dk",
    "🎯 V3 Canlı",
    "🎼 Nota Karakteri",
    "🧬 6 Çekiliş / Dinlenme",
    "🔗 2li-3lü Paket",
    "🧪 Walk-Forward",
    "💾 Veri / Kayıt",
])

# ============================================================
# HIZLI 5DK
# ============================================================

with tabs[0]:
    st.subheader("⚡ Tek Yapıştır → Sonraki V3 Kupon")
    st.caption(
        "Sonucu aynen yapıştır. RAM zinciri hemen güncellenir; "
        "GitHub kaydı kupon üretimini bekletmez."
    )

    pasted = st.text_area(
        "Gelen sonuç",
        height=310,
        placeholder=(
            "Çekiliş no: 48601\n"
            "12.08.2026 - 23:22\n"
            "4\n7\n12\n16\n18\n21\n23\n34\n42\n49\n"
            "50\n51\n52\n53\n55\n59\n65\n72\n74\n78"
        ),
        key="v3_paste",
    )

    if st.button(
        "⚡ SONUCU İŞLE + SONRAKİ V3 KUPONU",
        type="primary",
        use_container_width=True,
    ):
        try:
            r = parse_draw_block(pasted)

            rows = st.session_state.get("v3_fast_rows", [])
            rows = [
                x for x in rows
                if not (x["date"] == r["date"] and x["time"] == r["time"])
            ]
            rows.append(r)
            st.session_state["v3_fast_rows"] = rows

            work = merge_session_rows(base_df)
            next_date, next_time = next_target_after(r["date"], r["time"])

            tab, meta = build_v3_evidence(work, next_date, next_time)
            coupon, reasons = select_v3_coupon(tab)

            st.session_state["v3_last_result"] = r
            st.session_state["v3_last_coupon"] = {
                "date": next_date,
                "time": next_time,
                "coupon": coupon,
                "reasons": reasons,
                "table": tab,
            }

            st.success(
                f"✅ #{r['draw_no']} — {r['date']} {r['time']} işlendi. "
                f"Hedef: {next_date} {next_time}"
            )

        except Exception as exc:
            st.error(f"Hızlı işlem başarısız: {exc}")

    last = st.session_state.get("v3_last_coupon")
    if last:
        st.markdown(f"## 🎯 V3 — {last['date']} {last['time']}")
        st.code("  ".join(f"{n:02d}" for n in last["coupon"]))

        seat_rows = []
        t = last["table"].set_index("Sayı")
        for n in last["coupon"]:
            rr = t.loc[n]
            seat_rows.append({
                "Sayı": n,
                "Koltuk": last["reasons"].get(n, ""),
                "Ham Sıra": int(rr["Ham Sıra"]),
                "Bağımsız Oy": int(rr["Bağımsız Oy"]),
                "6 Yol": rr["6 Yol"],
                "Gap": int(rr["Gap"]),
                "Kaynakta": "Evet" if bool(rr["Kaynakta"]) else "Hayır",
                "En İyi Paket": rr["En İyi Paket"],
                "V3": round(float(rr["V3 Puan"]), 3),
            })
        st.dataframe(pd.DataFrame(seat_rows), use_container_width=True, hide_index=True)

        hidden = [
            n for n in last["coupon"]
            if last["reasons"].get(n) == "Gizli Aday"
        ]
        if hidden:
            st.info(
                "🕵️ Gizli aday koltuğu Top-7 ham skordan bağımsızdır: "
                + ", ".join(map(str, hidden))
            )

        with st.expander("İlk 25 aday — bütün sinyaller"):
            cols = [
                "Sayı","Ham Sıra","V3 Puan","Bağımsız Oy","Kaynakta",
                "6 Yol","Gap","Nota","Taşıma","6Ç","Dinlenme","6 Gün",
                "Paket","Ard2","Ard3","En İyi Paket","Gizli Aday"
            ]
            view = last["table"][cols].head(25).copy()
            for c in ["V3 Puan","Nota","Taşıma","6Ç","Dinlenme","6 Gün","Paket","Ard2","Ard3"]:
                view[c] = view[c].map(lambda x: round(float(x), 3))
            st.dataframe(view, use_container_width=True, hide_index=True)

# ============================================================
# V3 CANLI
# ============================================================

with tabs[1]:
    st.subheader("🎯 V3 Canlı / Manuel Hedef")

    max_date = max(df["date"], key=to_date)
    c1, c2 = st.columns(2)
    with c1:
        target_date = st.text_input("Hedef tarih", value=max_date, key="v3_target_date")
    with c2:
        target_time = st.selectbox("Hedef nota", SLOTS, index=1, key="v3_target_time")

    if st.button("🎯 V3 Kupon Üret", type="primary", use_container_width=True):
        try:
            tab, meta = build_v3_evidence(df, target_date, target_time)
            coupon, reasons = select_v3_coupon(tab)

            st.write(
                f"**Kaynak:** {meta['source_key'][0]} {meta['source_key'][1]} "
                f"→ **Hedef:** {target_date} {target_time}"
            )
            st.success("V3 7'Lİ: " + " - ".join(map(str, coupon)))

            rows = []
            tt = tab.set_index("Sayı")
            for n in coupon:
                r = tt.loc[n]
                rows.append({
                    "Sayı": n,
                    "Koltuk": reasons.get(n, ""),
                    "Ham Sıra": int(r["Ham Sıra"]),
                    "Oy": int(r["Bağımsız Oy"]),
                    "6 Yol": r["6 Yol"],
                    "Gap": int(r["Gap"]),
                    "Paket": r["En İyi Paket"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            with st.expander("80 sayı V3 taraması"):
                show = tab.copy()
                numeric = ["V3 Puan","Nota","Taşıma","6Ç","Dinlenme","6 Gün","Paket","Ard2","Ard3"]
                for c in numeric:
                    show[c] = show[c].map(lambda x: round(float(x), 4))
                st.dataframe(show, use_container_width=True, hide_index=True)

        except Exception as exc:
            st.error(str(exc))

# ============================================================
# NOTA KARAKTERİ
# ============================================================

with tabs[2]:
    st.subheader("🎼 Her çekiliş notasının ayrı karakteri")
    st.caption(
        "23:02 / 23:07 / 23:12 / 23:17 dahil bütün dakikalar "
        "taşıma, ardışık paket, tek/çift ve bant yapısıyla ayrı ölçülür."
    )

    note_tbl = note_character_table(df)
    st.dataframe(note_tbl, use_container_width=True, hide_index=True)

    wanted = st.multiselect(
        "Karşılaştırılacak notalar",
        SLOTS,
        default=["23:02","23:07","23:12","23:17"],
    )
    if wanted:
        st.dataframe(
            note_tbl[note_tbl["Nota"].isin(wanted)],
            use_container_width=True,
            hide_index=True,
        )

# ============================================================
# 6 ÇEKİLİŞ / DİNLENME
# ============================================================

with tabs[3]:
    st.subheader("🧬 6 Çekiliş Ritmi + Dinlenip Dönüş")
    slot = st.selectbox("Hedef nota", SLOTS, index=3, key="rhythm_slot")

    # Son mevcut tarihi hedef gibi kullan; kaynak yoksa bir sonraki gün/slot denenebilir.
    last_date = str(df.iloc[-1]["date"])
    try:
        # Hedef mevcutsa bir sonraki örnek için en son tarihin aynı notası kullanılmaz;
        # analiz görünümü geçmiş pattern dağılımlarını kullanır.
        temp_date = last_date
        if previous_source_key(df, temp_date, slot) is None:
            temp_date = fmt(to_date(last_date) + timedelta(days=1))

        tab, meta = build_v3_evidence(df, temp_date, slot)

        cols = [
            "Sayı","6 Yol","Gap","Kaynakta","6Ç","6Ç Destek",
            "Dinlenme","6 Gün","6 Gün Hit","Bağımsız Oy","Ham Sıra","Gizli Aday"
        ]
        view = tab[cols].copy()
        for c in ["6Ç","Dinlenme","6 Gün"]:
            view[c] = view[c].map(lambda x: round(float(x), 3))
        st.dataframe(view.head(40), use_container_width=True, hide_index=True)

        st.caption(
            "Gizli Aday = ham skorda Top-8 dışında olmasına rağmen "
            "6 çekiliş / dinlenme / paket gibi bağımsız kanallarda güçlü destek alan sayı."
        )
    except Exception as exc:
        st.info(str(exc))

# ============================================================
# 2Lİ / 3LÜ
# ============================================================

with tabs[4]:
    st.subheader("🔗 Elden Ele 2'li Paket + Ardışık 2'li/3'lü")
    pslot = st.selectbox("Paket hedef notası", SLOTS, index=4, key="package_slot")

    pair_df, adj2_df, adj3_df = package_analysis(df, pslot)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Birlikte taşınan ikililer**")
        st.dataframe(pair_df.head(30), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Hedefte sık ardışık 2'liler**")
        st.dataframe(adj2_df, use_container_width=True, hide_index=True)
    with c3:
        st.markdown("**Hedefte sık ardışık 3'lüler**")
        st.dataframe(adj3_df, use_container_width=True, hide_index=True)

# ============================================================
# WALK FORWARD
# ============================================================

with tabs[5]:
    st.subheader("🧪 Sızıntısız Walk-Forward Test")
    st.caption(
        "Her hedefte yalnız o hedeften önceki veri kullanılır. "
        "Tek çekiliş başarısı değil rolling istikrar ölçülür."
    )

    test_n = st.selectbox("Test çekilişi", [24, 48, 72, 120], index=1)

    if st.button("🚀 V3 WALK-FORWARD", type="primary", use_container_width=True):
        with st.spinner("V3 geçmiş hedeflerde kör test ediliyor..."):
            result = walk_forward_v3(df, test_n)
        st.session_state["v3_bt"] = result

    bt = st.session_state.get("v3_bt", pd.DataFrame())
    if isinstance(bt, pd.DataFrame) and not bt.empty:
        a,b,c,d,e = st.columns(5)
        a.metric("Test", len(bt))
        b.metric("Ort. isabet", f"{bt['İsabet'].mean():.2f}/7")
        c.metric("3+ oranı", f"%{100*(bt['İsabet']>=3).mean():.1f}")
        d.metric("4+ oranı", f"%{100*(bt['İsabet']>=4).mean():.1f}")
        e.metric("Maks.", int(bt["İsabet"].max()))

        st.caption(
            "Rastgele 7 sayı için teorik beklenen ortalama 1.75 isabettir. "
            "V3 ancak ileriye dönük walk-forward sonuçları bu tabanın üstünde "
            "istikrarlı kalırsa güçlü kabul edilmelidir."
        )

        by_slot = bt.groupby("Saat").agg(
            Test=("İsabet","size"),
            Ortalama=("İsabet","mean"),
            UcPlus=("İsabet", lambda x: float((x>=3).mean())),
            DortPlus=("İsabet", lambda x: float((x>=4).mean())),
            GizliHit=("Gizli Tuttu","mean"),
        ).reset_index()
        by_slot["Ortalama"] = by_slot["Ortalama"].round(3)
        by_slot["3+ %"] = (100*by_slot.pop("UcPlus")).round(1)
        by_slot["4+ %"] = (100*by_slot.pop("DortPlus")).round(1)
        by_slot["Gizli %"] = (100*by_slot.pop("GizliHit")).round(1)

        st.markdown("#### Nota bazında performans")
        st.dataframe(by_slot, use_container_width=True, hide_index=True)

        st.markdown("#### Son testler")
        st.dataframe(bt.sort_values("Çekiliş", ascending=False), use_container_width=True, hide_index=True)

# ============================================================
# VERİ / KAYIT
# ============================================================

with tabs[6]:
    st.subheader("💾 Veri ve Kalıcı Kayıt")
    st.write(
        f"Son kalıcı/okunan kayıt: **#{df.iloc[-1]['draw_no']} — "
        f"{df.iloc[-1]['date']} {df.iloc[-1]['time']}**"
    )

    fast_rows = st.session_state.get("v3_fast_rows", [])
    st.write(f"Bu oturumda RAM'e eklenen hızlı sonuç: **{len(fast_rows)}**")

    last_result = st.session_state.get("v3_last_result")
    if last_result:
        line = normalize_result_line(
            last_result["draw_no"],
            last_result["date"],
            last_result["time"],
            last_result["numbers"],
        )
        st.code(line)

        if st.button("💾 Son hızlı sonucu GitHub veri.txt'ye yaz", type="primary"):
            try:
                token, repo, branch, path = github_config()
                if not token:
                    st.error("Streamlit Secrets içinde GITHUB_TOKEN bulunamadı.")
                else:
                    current, _ = github_read_file(token, repo, branch, path)
                    updated = append_result_to_text(current, line)
                    github_write_file(
                        token, repo, branch, path, updated,
                        f"V3 add draw {last_result['draw_no']} {last_result['date']} {last_result['time']}"
                    )
                    st.success("GitHub veri.txt güncellendi.")
            except Exception as exc:
                st.error(f"Kalıcı kayıt başarısız: {exc}")

        try:
            updated_local = append_result_to_text(repo_data_text(), line)
            st.download_button(
                "⬇️ Güncel veri.txt indir",
                updated_local.encode("utf-8"),
                file_name="veri.txt",
                mime="text/plain",
            )
        except Exception:
            pass

st.divider()
st.caption(
    "V3 bir araştırma motorudur. Geçmiş örüntüler bağımsız gelecek çekilişlerini "
    "garanti etmez. Amaç; nota, taşıma, dinlenme ve paket sinyallerini "
    "sızıntısız walk-forward testle ölçmek ve yalnız kanıtlanan sinyalleri kullanmaktır."
)
