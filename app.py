
from __future__ import annotations

import io
import os
import re
import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict, Counter

import pandas as pd
import streamlit as st

# =========================================================
# HIZLI ON ARAŞTIRMA LABORATUVARI V1
# Amaç: kupon üretmek DEĞİL, ham veriyi ölçülebilir araştırma kütüklerine çevirmek.
# =========================================================

DRAW_HEADER_RE = re.compile(r"Çekiliş\s*no\s*:\s*(\d+)", re.I)
DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})")
INT_ONLY_RE = re.compile(r"^\s*(\d{1,2})\s*$")

DATA_DIR_CANDIDATES = [
    ".",
    "data",
    "veri",
    "dataset",
    "datasets",
    "raw",
    "input",
    "inputs",
]

SLEEP_BINS = [
    (1, 3, "H1-H3"),
    (4, 6, "H4-H6"),
    (7, 10, "H7-H10"),
    (11, 14, "H11-H14"),
    (15, 19, "H15-H19"),
    (20, 29, "H20-H29"),
    (30, 999, "H30+"),
]

PREDEFINED_PATTERNS = {
    "1-2-1": (1,2,1),
    "1-1-2": (1,1,2),
    "2-1-1": (2,1,1),
    "1-2-1-2": (1,2,1,2),
    "2-1-2-1": (2,1,2,1),
    "1-2-4": (1,2,4),
    "1-2-4-8": (1,2,4,8),
    "2-4-8": (2,4,8),
    "2-4-8-16": (2,4,8,16),
}

@dataclass
class Draw:
    draw_no: int
    dt: pd.Timestamp
    numbers: tuple[int, ...]

    @property
    def date(self):
        return self.dt.date()

def parse_txt(content: str, source: str = "") -> list[Draw]:
    """
    Beklenen yaygın biçim:
      Çekiliş no: 53793
      05.09.2026 - 22:02
      1
      3
      ...
      65
    Bir dosyada bloklar arka arkaya olabilir.
    """
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    draws = []
    i = 0
    while i < len(lines):
        m = DRAW_HEADER_RE.search(lines[i])
        if not m:
            i += 1
            continue
        draw_no = int(m.group(1))
        i += 1

        dt = None
        while i < len(lines) and not DRAW_HEADER_RE.search(lines[i]):
            md = DATE_RE.search(lines[i])
            if md:
                dt = pd.to_datetime(f"{md.group(1)} {md.group(2)}", format="%d.%m.%Y %H:%M", errors="coerce")
                i += 1
                break
            i += 1

        nums = []
        while i < len(lines) and not DRAW_HEADER_RE.search(lines[i]):
            mi = INT_ONLY_RE.match(lines[i])
            if mi:
                v = int(mi.group(1))
                if 1 <= v <= 80:
                    nums.append(v)
                    if len(nums) == 20:
                        # Consume until next header, but avoid pulling unrelated ints.
                        j = i + 1
                        while j < len(lines) and not DRAW_HEADER_RE.search(lines[j]):
                            j += 1
                        i = j
                        break
            i += 1

        if dt is not None and not pd.isna(dt) and len(nums) == 20 and len(set(nums)) == 20:
            draws.append(Draw(draw_no, dt, tuple(sorted(nums))))
    return draws

def parse_csv_bytes(data: bytes, source: str = "") -> list[Draw]:
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(data), sep=";")
        except Exception:
            return []

    cols = {str(c).strip().lower(): c for c in df.columns}
    draw_col = next((cols[k] for k in cols if k in {"draw_no","cekilis_no","çekiliş_no","draw","no"}), None)
    date_col = next((cols[k] for k in cols if k in {"date","tarih","datetime","dt"}), None)
    time_col = next((cols[k] for k in cols if k in {"time","saat"}), None)
    nums_col = next((cols[k] for k in cols if k in {"numbers","sayilar","sayılar","nums"}), None)

    draws = []
    if draw_col is not None and date_col is not None and nums_col is not None:
        for _, r in df.iterrows():
            try:
                draw_no = int(r[draw_col])
                ds = str(r[date_col])
                ts = str(r[time_col]) if time_col is not None else ""
                dt = pd.to_datetime((ds + " " + ts).strip(), dayfirst=True, errors="coerce")
                nums = [int(x) for x in re.findall(r"\d+", str(r[nums_col])) if 1 <= int(x) <= 80]
                nums = list(dict.fromkeys(nums))
                if not pd.isna(dt) and len(nums) == 20:
                    draws.append(Draw(draw_no, dt, tuple(sorted(nums))))
            except Exception:
                pass
    return draws

def discover_repo_files(root: Path) -> list[Path]:
    seen = set()
    files = []
    for rel in DATA_DIR_CANDIDATES:
        p = (root / rel).resolve()
        if not p.exists() or not p.is_dir():
            continue
        for ext in ("*.txt", "*.csv"):
            for f in p.rglob(ext):
                if any(part.startswith(".") for part in f.parts):
                    continue
                if f.resolve() in seen:
                    continue
                seen.add(f.resolve())
                files.append(f)
    return sorted(files)

def load_repo_draws(root: Path):
    all_draws = []
    audit = []
    for f in discover_repo_files(root):
        try:
            if f.suffix.lower() == ".txt":
                text = f.read_text(encoding="utf-8", errors="ignore")
                ds = parse_txt(text, str(f))
            elif f.suffix.lower() == ".csv":
                ds = parse_csv_bytes(f.read_bytes(), str(f))
            else:
                ds = []
            audit.append({"file": str(f.relative_to(root)), "draws_parsed": len(ds)})
            all_draws.extend(ds)
        except Exception as e:
            audit.append({"file": str(f), "draws_parsed": 0, "error": str(e)})

    # duplicate draw_no: keep earliest parsed instance
    dedup = {}
    for d in sorted(all_draws, key=lambda x: (x.dt, x.draw_no)):
        dedup.setdefault(d.draw_no, d)
    draws = sorted(dedup.values(), key=lambda x: (x.dt, x.draw_no))
    return draws, pd.DataFrame(audit)

def band_of_age(age):
    if age is None:
        return "YENI"
    for lo, hi, name in SLEEP_BINS:
        if lo <= age <= hi:
            return name
    return "H30+"

def longest_consecutive_block(nums):
    nums = sorted(nums)
    best = cur = []
    out = []
    for n in nums:
        if not cur or n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2: out.append(tuple(cur))
            cur = [n]
    if len(cur) >= 2: out.append(tuple(cur))
    return out

def classify_gap_pattern(gaps):
    g = list(gaps)
    labels = []
    if len(g) >= 3:
        d = g[-3:]
        if d[0] < d[1] < d[2]:
            labels.append("ARTAN")
        if d[0] > d[1] > d[2]:
            labels.append("AZALAN")
        if d[1] == 2*d[0] and d[2] == 2*d[1]:
            labels.append("KATLANAN_X2")
        if abs(d[1] - 2*d[0]) <= 1 and abs(d[2] - 2*d[1]) <= 1:
            labels.append("YAKLASIK_KATLANAN")
    if len(g) >= 4:
        d = g[-4:]
        if d[0] == d[2] and d[1] == d[3]:
            labels.append("ABAB")
        if len(set(d)) == 1:
            labels.append("SABIT")
    return labels

def analyze(draws: list[Draw]):
    if not draws:
        return {}

    draw_rows = []
    life_event_rows = []
    daily_life_rows = []
    pattern_event_rows = []
    sleep_wake_rows = []
    family_rows = []
    consecutive_rows = []

    by_day = defaultdict(list)
    for d in draws:
        by_day[d.date].append(d)

    for day, day_draws in sorted(by_day.items()):
        day_draws = sorted(day_draws, key=lambda x: (x.dt, x.draw_no))
        last_seen = {}
        appearances = defaultdict(list)
        gaps = defaultdict(list)

        # PRE-H chronology within the day only.
        for idx, d in enumerate(day_draws):
            pre_ages = {}
            for n in range(1, 81):
                pre_ages[n] = None if n not in last_seen else idx - last_seen[n]

            outcome = set(d.numbers)
            band_counts = Counter(band_of_age(pre_ages[n]) for n in outcome)

            draw_rows.append({
                "date": str(day),
                "draw_index_day": idx + 1,
                "draw_no": d.draw_no,
                "datetime": d.dt,
                "numbers": " ".join(map(str, d.numbers)),
                "H1_H3": sum(band_counts[x] for x in ["H1-H3"]),
                "H4_H6": band_counts["H4-H6"],
                "H7_H10": band_counts["H7-H10"],
                "H11_H14": band_counts["H11-H14"],
                "H15_H19": band_counts["H15-H19"],
                "H20_H29": band_counts["H20-H29"],
                "H30plus": band_counts["H30+"],
                "YENI": band_counts["YENI"],
            })

            # Last digit family state and outcome
            for digit in range(10):
                fam = [n for n in range(1,81) if n % 10 == digit]
                active = sorted(outcome.intersection(fam))
                pre_h1h3 = [n for n in fam if pre_ages[n] is not None and 1 <= pre_ages[n] <= 3]
                family_rows.append({
                    "date": str(day),
                    "draw_no": d.draw_no,
                    "draw_index_day": idx+1,
                    "last_digit": digit,
                    "family_members": " ".join(map(str,fam)),
                    "pre_H1_H3_members": " ".join(map(str,pre_h1h3)),
                    "pre_H1_H3_count": len(pre_h1h3),
                    "real20_family_hits": " ".join(map(str,active)),
                    "real20_family_hit_count": len(active),
                })

            # Consecutive blocks
            blocks = longest_consecutive_block(d.numbers)
            for b in blocks:
                consecutive_rows.append({
                    "date": str(day),
                    "draw_no": d.draw_no,
                    "draw_index_day": idx+1,
                    "block": "-".join(map(str,b)),
                    "block_len": len(b)
                })

            # Per-number event
            for n in d.numbers:
                age = pre_ages[n]
                prev_gaps = tuple(gaps[n][-6:])
                labels = classify_gap_pattern(prev_gaps)

                life_event_rows.append({
                    "date": str(day),
                    "draw_no": d.draw_no,
                    "draw_index_day": idx + 1,
                    "datetime": d.dt,
                    "number": n,
                    "pre_age_H": age if age is not None else "YENI",
                    "pre_band": band_of_age(age),
                    "previous_gaps_last6": "-".join(map(str, prev_gaps)),
                    "rhythm_labels": "|".join(labels),
                    "last_digit_family": n % 10,
                })

                # exact PRE-H rhythm patterns. Outcome = same number in next 1/3/6 draws.
                for name, pat in PREDEFINED_PATTERNS.items():
                    if len(gaps[n]) >= len(pat) and tuple(gaps[n][-len(pat):]) == pat:
                        next1 = int(idx+1 < len(day_draws) and n in day_draws[idx+1].numbers)
                        next3 = int(any(n in x.numbers for x in day_draws[idx+1:min(len(day_draws), idx+4)]))
                        next6 = int(any(n in x.numbers for x in day_draws[idx+1:min(len(day_draws), idx+7)]))
                        pattern_event_rows.append({
                            "date": str(day), "draw_no": d.draw_no, "draw_index_day": idx+1,
                            "number": n, "pattern": name,
                            "pre_gaps": "-".join(map(str,gaps[n][-len(pat):])),
                            "next1_hit": next1, "next3_any_hit": next3, "next6_any_hit": next6,
                        })

                # Long sleep wake event: current hit woke from H11+ etc.
                if age is not None and age >= 11:
                    next1 = int(idx+1 < len(day_draws) and n in day_draws[idx+1].numbers)
                    next3_count = sum(n in x.numbers for x in day_draws[idx+1:min(len(day_draws), idx+4)])
                    next6_count = sum(n in x.numbers for x in day_draws[idx+1:min(len(day_draws), idx+7)])
                    sleep_wake_rows.append({
                        "date": str(day), "draw_no": d.draw_no, "draw_index_day": idx+1,
                        "number": n, "wake_from_age": age, "wake_band": band_of_age(age),
                        "next1_hit": next1,
                        "next3_hit_count": next3_count,
                        "next6_hit_count": next6_count,
                    })

            # Update state AFTER outcome
            for n in d.numbers:
                if n in last_seen:
                    gap = idx - last_seen[n]
                    gaps[n].append(gap)
                appearances[n].append(idx)
                last_seen[n] = idx

        # End-of-day 1..80 life cards
        for n in range(1,81):
            pos = appearances[n]
            gs = [b-a for a,b in zip(pos,pos[1:])]
            max_sleep = max(gs) if gs else None
            first_draw = day_draws[pos[0]].draw_no if pos else None
            last_draw = day_draws[pos[-1]].draw_no if pos else None
            daily_life_rows.append({
                "date": str(day),
                "number": n,
                "appearances": len(pos),
                "first_draw_no": first_draw,
                "last_draw_no": last_draw,
                "gap_sequence": "-".join(map(str,gs)),
                "min_gap": min(gs) if gs else None,
                "median_gap": float(pd.Series(gs).median()) if gs else None,
                "mean_gap": (sum(gs)/len(gs)) if gs else None,
                "max_sleep": max_sleep,
                "short_gap_1_3_count": sum(1 <= g <= 3 for g in gs),
                "mid_gap_4_6_count": sum(4 <= g <= 6 for g in gs),
                "long_gap_7_14_count": sum(7 <= g <= 14 for g in gs),
                "deep_gap_15plus_count": sum(g >= 15 for g in gs),
                "last_digit_family": n % 10,
            })

    dfs = {
        "draw_band_trace": pd.DataFrame(draw_rows),
        "life_events": pd.DataFrame(life_event_rows),
        "daily_life_cards": pd.DataFrame(daily_life_rows),
        "pattern_events": pd.DataFrame(pattern_event_rows),
        "sleep_wake_events": pd.DataFrame(sleep_wake_rows),
        "last_digit_family_trace": pd.DataFrame(family_rows),
        "consecutive_blocks": pd.DataFrame(consecutive_rows),
    }

    # Aggregates
    if not dfs["pattern_events"].empty:
        dfs["pattern_summary"] = (
            dfs["pattern_events"]
            .groupby("pattern", as_index=False)
            .agg(
                events=("number","size"),
                days=("date","nunique"),
                next1_rate=("next1_hit","mean"),
                next3_any_rate=("next3_any_hit","mean"),
                next6_any_rate=("next6_any_hit","mean"),
            )
            .sort_values(["events","next1_rate"], ascending=[False,False])
        )
    else:
        dfs["pattern_summary"] = pd.DataFrame()

    if not dfs["sleep_wake_events"].empty:
        dfs["sleep_wake_summary"] = (
            dfs["sleep_wake_events"]
            .groupby("wake_band", as_index=False)
            .agg(
                events=("number","size"),
                days=("date","nunique"),
                next1_rate=("next1_hit","mean"),
                next3_mean_hits=("next3_hit_count","mean"),
                next6_mean_hits=("next6_hit_count","mean"),
            )
        )
    else:
        dfs["sleep_wake_summary"] = pd.DataFrame()

    if not dfs["last_digit_family_trace"].empty:
        dfs["last_digit_family_summary"] = (
            dfs["last_digit_family_trace"]
            .groupby("last_digit", as_index=False)
            .agg(
                rows=("draw_no","size"),
                mean_real20_family_hits=("real20_family_hit_count","mean"),
                max_real20_family_hits=("real20_family_hit_count","max"),
                mean_pre_H1_H3=("pre_H1_H3_count","mean"),
            )
        )
    else:
        dfs["last_digit_family_summary"] = pd.DataFrame()

    return dfs

def make_zip(dfs, audit, meta):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, df in dfs.items():
            z.writestr(f"{name}.csv", df.to_csv(index=False))
        z.writestr("file_audit.csv", audit.to_csv(index=False))
        z.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        # Human-readable TXT index
        summary = [
            "HIZLI ON ARASTIRMA LABORATUVARI V1",
            f"Toplam çekiliş: {meta.get('draw_count')}",
            f"Gün sayısı: {meta.get('day_count')}",
            f"İlk tarih: {meta.get('first_dt')}",
            f"Son tarih: {meta.get('last_dt')}",
            "",
            "ÇIKTILAR:",
        ]
        summary += [f"- {k}.csv : {len(v)} satır" for k,v in dfs.items()]
        z.writestr("RAPOR_INDEX.txt", "\n".join(summary))
    return bio.getvalue()

st.set_page_config(page_title="Hızlı On Araştırma Laboratuvarı V1", layout="wide")
st.title("Hızlı On — Araştırma Laboratuvarı V1")
st.caption("Kupon motoru değildir. Ham veriyi gün gün yaşam izi, ritim, uyku/uyanış ve son-rakam kardeşliği araştırma kütüklerine dönüştürür.")

with st.sidebar:
    st.header("Veri Kaynağı")
    mode = st.radio("Kaynak", ["GitHub repo / yerel klasör", "Dosya yükle"])
    st.info("GitHub/Streamlit Cloud'da app.py ile aynı repodaki .txt/.csv dosyaları otomatik taranır.")

draws = []
audit = pd.DataFrame()

if mode == "GitHub repo / yerel klasör":
    root_text = st.text_input("Repo kökü", value=".")
    root = Path(root_text).resolve()
    if st.button("Repodaki veriyi tara ve analiz et", type="primary"):
        draws, audit = load_repo_draws(root)
        st.session_state["draws"] = draws
        st.session_state["audit"] = audit
else:
    ups = st.file_uploader("TXT veya CSV dosyaları", type=["txt","csv"], accept_multiple_files=True)
    if st.button("Yüklenen veriyi analiz et", type="primary"):
        all_d = []
        audit_rows = []
        for u in ups or []:
            data = u.getvalue()
            if u.name.lower().endswith(".txt"):
                ds = parse_txt(data.decode("utf-8", errors="ignore"), u.name)
            else:
                ds = parse_csv_bytes(data, u.name)
            all_d.extend(ds)
            audit_rows.append({"file":u.name,"draws_parsed":len(ds)})
        ded = {}
        for d in sorted(all_d, key=lambda x:(x.dt,x.draw_no)):
            ded.setdefault(d.draw_no,d)
        st.session_state["draws"] = sorted(ded.values(), key=lambda x:(x.dt,x.draw_no))
        st.session_state["audit"] = pd.DataFrame(audit_rows)

draws = st.session_state.get("draws", [])
audit = st.session_state.get("audit", pd.DataFrame())

if draws:
    day_count = len(set(d.date for d in draws))
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Çekiliş", len(draws))
    c2.metric("Gün", day_count)
    c3.metric("İlk", draws[0].dt.strftime("%d.%m.%Y %H:%M"))
    c4.metric("Son", draws[-1].dt.strftime("%d.%m.%Y %H:%M"))

    if day_count != 14:
        st.warning(f"App {day_count} gün algıladı. Beklenen veri 14 gün ise 'Dosya denetimi' tablosundan eksik/okunmayan dosyayı kontrol et.")
    else:
        st.success("14 günlük veri algılandı.")

    with st.spinner("Araştırma kütükleri hazırlanıyor..."):
        dfs = analyze(draws)

    tabs = st.tabs([
        "Dosya denetimi","Günlük yaşam kartları","Ritim",
        "Uyku/Uyanış","Son rakam kardeşliği","Ardışık blok","H-bant izi","Dışa aktar"
    ])

    with tabs[0]:
        st.dataframe(audit, use_container_width=True)
    with tabs[1]:
        st.dataframe(dfs["daily_life_cards"], use_container_width=True, height=600)
    with tabs[2]:
        st.subheader("Ritim özeti")
        st.dataframe(dfs["pattern_summary"], use_container_width=True)
        st.subheader("Tüm PRE-H ritim olayları")
        st.dataframe(dfs["pattern_events"], use_container_width=True, height=500)
    with tabs[3]:
        st.subheader("Uyku → uyanış sonrası")
        st.dataframe(dfs["sleep_wake_summary"], use_container_width=True)
        st.dataframe(dfs["sleep_wake_events"], use_container_width=True, height=500)
    with tabs[4]:
        st.dataframe(dfs["last_digit_family_summary"], use_container_width=True)
        st.dataframe(dfs["last_digit_family_trace"], use_container_width=True, height=500)
    with tabs[5]:
        st.dataframe(dfs["consecutive_blocks"], use_container_width=True, height=600)
    with tabs[6]:
        st.dataframe(dfs["draw_band_trace"], use_container_width=True, height=600)
    with tabs[7]:
        meta = {
            "draw_count": len(draws),
            "day_count": day_count,
            "first_dt": draws[0].dt,
            "last_dt": draws[-1].dt,
            "note": "Her gün bağımsız yaşam olarak analiz edilir; H yaşı gün başında sıfırlanır. PRE-H geleceği görmez."
        }
        z = make_zip(dfs, audit, meta)
        st.download_button(
            "Tüm araştırma kütüklerini ZIP indir",
            data=z,
            file_name="HIZLI_ON_ARASTIRMA_KUTUKLERI_V1.zip",
            mime="application/zip",
            type="primary"
        )
        st.write("Bana özellikle `pattern_events.csv`, `sleep_wake_events.csv`, `daily_life_cards.csv`, `last_digit_family_trace.csv` dosyalarını verirsen derin yorumlayabilirim.")
else:
    st.info("Veriyi tara/yükle. App çekiliş bloklarını algıladığında analiz ekranı açılır.")
