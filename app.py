
from __future__ import annotations

import io
import re
import json
import math
import zipfile
from pathlib import Path
from collections import defaultdict, Counter

import pandas as pd
import streamlit as st

# ============================================================
# HIZLI ON ARAŞTIRMA LABORATUVARI V3
# AMAÇ: Kupon üretmek değil; GitHub reposundaki mevcut 14 günlük
# ham veriyi otomatik bulup araştırma kütüklerine dönüştürmek.
#
# TEMEL İŞ AKIŞI
# 1) Repo verisini otomatik tara
# 2) Günleri ayrı ayrı analiz et
# 3) 1-80 her sayının gün boyu yaşamını çıkar
# 4) Ritim / katlanma / kırılma / uyku-uyanış / kardeşlik /
#    ardışık / atlamalı / sosyal bağ / saat-faz / PRE-H izlerini çıkar
# 5) Sonra 14 günü toplu karşılaştır
# 6) CSV + TXT + ZIP araştırma çıktısı üret
# ============================================================

DRAW_HEADER_RE = re.compile(r"Çekiliş\s*no\s*:\s*(\d+)", re.I)
DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})")
INT_ONLY_RE = re.compile(r"^\s*(\d{1,2})\s*$")

SEARCH_DIRS = [
    ".", "data", "veri", "dataset", "datasets",
    "raw", "input", "inputs", "14gun", "14_gun", "hizli_on"
]

GAP_BANDS = [
    (1,3,"H1-H3"),
    (4,6,"H4-H6"),
    (7,14,"H7-H14"),
    (15,19,"H15-H19"),
    (20,29,"H20-H29"),
    (30,999,"H30+"),
]

EXACT_PATTERNS = {
    "1-2-1": (1,2,1),
    "1-1-2": (1,1,2),
    "2-1-1": (2,1,1),
    "1-2-1-2": (1,2,1,2),
    "2-1-2-1": (2,1,2,1),
    "1-2-4": (1,2,4),
    "1-2-4-8": (1,2,4,8),
    "2-4-8": (2,4,8),
    "2-4-8-16": (2,4,8,16),
    "1-3-6": (1,3,6),
    "1-3-6-12": (1,3,6,12),
}

def gap_band(age):
    if age is None:
        return "YENI"
    for lo,hi,name in GAP_BANDS:
        if lo <= age <= hi:
            return name
    return "H30+"

class Draw:
    def __init__(self, draw_no, dt, numbers, source=""):
        self.draw_no = int(draw_no)
        self.dt = pd.Timestamp(dt)
        self.numbers = tuple(sorted(map(int, numbers)))
        self.source = source
    @property
    def date(self):
        return self.dt.date()

def parse_txt(text: str, source=""):
    """
    Gerçek GitHub veri biçimi:
    51213;25.08.2026 00:02;2,4,6,9,13,18,19,20,21,24,32,34,40,48,51,55,61,62,63,80

    Ayrıca eski blok biçimini de geriye dönük destekler.
    """
    out = []

    # 1) Gerçek repo satır biçimi
    for raw in text.replace("\r\n","\n").replace("\r","\n").split("\n"):
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        parts = line.split(";", 2)
        if len(parts) == 3:
            try:
                draw_no = int(parts[0].strip())
                dt = pd.to_datetime(parts[1].strip(), format="%d.%m.%Y %H:%M", errors="coerce")
                nums = [int(x.strip()) for x in parts[2].split(",") if x.strip()]
                if (
                    not pd.isna(dt)
                    and len(nums) == 20
                    and len(set(nums)) == 20
                    and all(1 <= n <= 80 for n in nums)
                ):
                    out.append(Draw(draw_no, dt, nums, source))
            except Exception:
                pass

    if out:
        return out

    # 2) Eski blok biçimi fallback
    lines = text.replace("\r\n","\n").replace("\r","\n").split("\n")
    i = 0
    while i < len(lines):
        mh = DRAW_HEADER_RE.search(lines[i])
        if not mh:
            i += 1
            continue
        draw_no = int(mh.group(1))
        i += 1
        dt = None
        while i < len(lines) and not DRAW_HEADER_RE.search(lines[i]):
            md = DATE_RE.search(lines[i])
            if md:
                dt = pd.to_datetime(
                    f"{md.group(1)} {md.group(2)}",
                    format="%d.%m.%Y %H:%M", errors="coerce"
                )
                i += 1
                break
            i += 1
        nums = []
        while i < len(lines) and not DRAW_HEADER_RE.search(lines[i]):
            mi = INT_ONLY_RE.match(lines[i])
            if mi:
                n = int(mi.group(1))
                if 1 <= n <= 80:
                    nums.append(n)
            i += 1
        nums = list(dict.fromkeys(nums))[:20]
        if dt is not None and not pd.isna(dt) and len(nums) == 20:
            out.append(Draw(draw_no, dt, nums, source))
    return out

def parse_csv_bytes(data: bytes, source=""):
    for sep in [",",";","\t"]:
        try:
            df = pd.read_csv(io.BytesIO(data), sep=sep)
            if len(df.columns) >= 2:
                break
        except Exception:
            df = None
    if df is None:
        return []

    lc = {str(c).strip().lower(): c for c in df.columns}
    draw_col = next((lc[k] for k in lc if k in ["draw_no","çekiliş_no","cekilis_no","draw","no"]), None)
    date_col = next((lc[k] for k in lc if k in ["date","tarih","datetime","dt"]), None)
    time_col = next((lc[k] for k in lc if k in ["time","saat"]), None)
    nums_col = next((lc[k] for k in lc if k in ["numbers","sayılar","sayilar","nums"]), None)

    out = []
    if draw_col is None or date_col is None:
        return out

    num_cols = [c for c in df.columns if str(c).lower().startswith(("n","sayi","sayı"))]
    for _,r in df.iterrows():
        try:
            draw_no = int(r[draw_col])
            ds = str(r[date_col])
            ts = "" if time_col is None else str(r[time_col])
            dt = pd.to_datetime((ds+" "+ts).strip(), dayfirst=True, errors="coerce")
            if pd.isna(dt):
                continue
            nums = []
            if nums_col is not None:
                nums = [int(x) for x in re.findall(r"\d+", str(r[nums_col]))]
            elif len(num_cols) >= 20:
                nums = [int(r[c]) for c in num_cols[:20]]
            nums = [n for n in nums if 1 <= n <= 80]
            nums = list(dict.fromkeys(nums))
            if len(nums) == 20:
                out.append(Draw(draw_no, dt, nums, source))
        except Exception:
            pass
    return out

def discover_files(root: Path):
    seen, files = set(), []
    for rel in SEARCH_DIRS:
        p = (root/rel).resolve()
        if not p.exists() or not p.is_dir():
            continue
        for ext in ("*.txt","*.csv"):
            for f in p.rglob(ext):
                if any(part.startswith(".") for part in f.relative_to(root).parts):
                    continue
                rp = f.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                files.append(f)
    return sorted(files)

def load_repo(root: Path):
    all_draws, audit = [], []
    for f in discover_files(root):
        try:
            if f.suffix.lower() == ".txt":
                ds = parse_txt(f.read_text(encoding="utf-8", errors="ignore"), str(f))
            else:
                ds = parse_csv_bytes(f.read_bytes(), str(f))
            audit.append({"file": str(f.relative_to(root)), "draws_parsed": len(ds)})
            all_draws.extend(ds)
        except Exception as e:
            audit.append({"file": str(f), "draws_parsed": 0, "error": str(e)})
    dedup = {}
    for d in sorted(all_draws, key=lambda x:(x.dt,x.draw_no)):
        dedup.setdefault(d.draw_no, d)
    draws = sorted(dedup.values(), key=lambda x:(x.dt,x.draw_no))
    return draws, pd.DataFrame(audit)

def consecutive_blocks(nums, min_len=2):
    nums = sorted(nums)
    blocks, cur = [], []
    for n in nums:
        if not cur or n == cur[-1]+1:
            cur.append(n)
        else:
            if len(cur) >= min_len:
                blocks.append(tuple(cur))
            cur = [n]
    if len(cur) >= min_len:
        blocks.append(tuple(cur))
    return blocks

def skip_one_blocks(nums, min_len=3):
    s = set(nums)
    blocks = []
    for start in sorted(s):
        if start-2 in s:
            continue
        cur = [start]
        x = start+2
        while x in s:
            cur.append(x)
            x += 2
        if len(cur) >= min_len:
            blocks.append(tuple(cur))
    return blocks

def rhythm_labels(gaps):
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
        if abs(d[1]-2*d[0]) <= 1 and abs(d[2]-2*d[1]) <= 1:
            labels.append("YAKLASIK_KATLANAN")
        if (d[1]-d[0]) == (d[2]-d[1]):
            labels.append("ARITMETIK")
    if len(g) >= 4:
        d = g[-4:]
        if d[0] == d[2] and d[1] == d[3]:
            labels.append("ABAB")
        if len(set(d)) == 1:
            labels.append("SABIT")
        if d[0] < d[1] < d[2] < d[3]:
            labels.append("ARTAN4")
        if d[0] > d[1] > d[2] > d[3]:
            labels.append("AZALAN4")
    return labels

def next_window(day_draws, idx, n, k):
    window = day_draws[idx+1:min(len(day_draws), idx+1+k)]
    return sum(n in d.numbers for d in window)

def analyze(draws):
    by_day = defaultdict(list)
    for d in draws:
        by_day[d.date].append(d)

    draw_trace = []
    life_events = []
    daily_life = []
    rhythm_events = []
    sleep_events = []
    sibling_trace = []
    sibling_follow = []
    consecutive = []
    skip_one = []
    pair_rows = []
    hour_rows = []
    phase_rows = []

    # day-by-day independent analysis
    for day, day_draws in sorted(by_day.items()):
        day_draws = sorted(day_draws, key=lambda x:(x.dt,x.draw_no))
        last_seen = {}
        appearances = defaultdict(list)
        gaps = defaultdict(list)
        pair_last_seen = {}

        # split day into 8 equal K phases
        nD = len(day_draws)
        def phase_of(idx):
            return min(8, int(idx * 8 / max(nD,1)) + 1)

        for idx,d in enumerate(day_draws):
            outcome = set(d.numbers)
            pre_age = {n: (None if n not in last_seen else idx-last_seen[n]) for n in range(1,81)}
            bc = Counter(gap_band(pre_age[n]) for n in outcome)

            draw_trace.append({
                "date":str(day),"draw_index_day":idx+1,"draw_no":d.draw_no,"datetime":d.dt,
                "numbers":" ".join(map(str,d.numbers)),
                "H1_H3":bc["H1-H3"],"H4_H6":bc["H4-H6"],"H7_H14":bc["H7-H14"],
                "H15_H19":bc["H15-H19"],"H20_H29":bc["H20-H29"],"H30plus":bc["H30+"],
                "YENI":bc["YENI"],"phase_K":phase_of(idx)
            })

            # hour normalized raw trace
            hour_rows.append({
                "date":str(day),"hour":d.dt.hour,"draw_no":d.draw_no,
                "draw_index_day":idx+1,"numbers":" ".join(map(str,d.numbers))
            })

            # consecutive / skip-one
            for b in consecutive_blocks(d.numbers):
                consecutive.append({
                    "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                    "block":"-".join(map(str,b)),"length":len(b)
                })
            for b in skip_one_blocks(d.numbers):
                skip_one.append({
                    "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                    "block":"-".join(map(str,b)),"length":len(b)
                })

            # last digit families
            for digit in range(10):
                fam = [n for n in range(1,81) if n % 10 == digit]
                hits = sorted(outcome.intersection(fam))
                active_pre = [n for n in fam if pre_age[n] is not None and pre_age[n] <= 3]
                sibling_trace.append({
                    "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                    "last_digit":digit,
                    "family":" ".join(map(str,fam)),
                    "pre_active_H1_H3":" ".join(map(str,active_pre)),
                    "pre_active_count":len(active_pre),
                    "real20_hits":" ".join(map(str,hits)),
                    "real20_hit_count":len(hits),
                    "phase_K":phase_of(idx)
                })

            # pair co-life and leader/follower raw events
            nums = sorted(d.numbers)
            for a_i in range(len(nums)):
                for b_i in range(a_i+1,len(nums)):
                    a,b = nums[a_i], nums[b_i]
                    pair_rows.append({
                        "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                        "a":a,"b":b,"same_last_digit":int(a%10==b%10),
                        "distance":abs(a-b),"phase_K":phase_of(idx)
                    })

            # each hit event
            for n in d.numbers:
                age = pre_age[n]
                prev6 = tuple(gaps[n][-6:])
                labs = rhythm_labels(prev6)
                life_events.append({
                    "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                    "datetime":d.dt,"number":n,
                    "pre_age_H":age if age is not None else "YENI",
                    "pre_band":gap_band(age),
                    "previous_gaps_last6":"-".join(map(str,prev6)),
                    "rhythm_labels":"|".join(labs),
                    "last_digit":n%10,"hour":d.dt.hour,"phase_K":phase_of(idx)
                })

                # exact rhythm patterns + generated labels
                for name,pat in EXACT_PATTERNS.items():
                    if len(gaps[n]) >= len(pat) and tuple(gaps[n][-len(pat):]) == pat:
                        rhythm_events.append({
                            "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                            "number":n,"pattern":name,
                            "pre_gaps":"-".join(map(str,pat)),
                            "next1_hit":next_window(day_draws,idx,n,1),
                            "next3_hit_count":next_window(day_draws,idx,n,3),
                            "next6_hit_count":next_window(day_draws,idx,n,6),
                            "hour":d.dt.hour,"phase_K":phase_of(idx)
                        })
                for lab in labs:
                    rhythm_events.append({
                        "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                        "number":n,"pattern":lab,
                        "pre_gaps":"-".join(map(str,prev6)),
                        "next1_hit":next_window(day_draws,idx,n,1),
                        "next3_hit_count":next_window(day_draws,idx,n,3),
                        "next6_hit_count":next_window(day_draws,idx,n,6),
                        "hour":d.dt.hour,"phase_K":phase_of(idx)
                    })

                # sleep -> wake
                if age is not None and age >= 7:
                    sleep_events.append({
                        "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                        "number":n,"wake_from_age":age,"wake_band":gap_band(age),
                        "next1_hit":next_window(day_draws,idx,n,1),
                        "next3_hit_count":next_window(day_draws,idx,n,3),
                        "next6_hit_count":next_window(day_draws,idx,n,6),
                        "hour":d.dt.hour,"phase_K":phase_of(idx)
                    })

                # sibling follow: which same-last-digit hit recently before this one?
                fam = [x for x in range(1,81) if x%10 == n%10 and x != n]
                prior = []
                for sib in fam:
                    if sib in last_seen:
                        prior.append((idx-last_seen[sib], sib))
                prior = sorted(prior)[:3]
                sibling_follow.append({
                    "date":str(day),"draw_no":d.draw_no,"draw_index_day":idx+1,
                    "number":n,"last_digit":n%10,
                    "closest_sibling_gap": prior[0][0] if prior else None,
                    "closest_sibling_number": prior[0][1] if prior else None,
                    "closest3": "|".join(f"{sib}:{gap}" for gap,sib in prior),
                    "phase_K":phase_of(idx)
                })

            # update AFTER outcome
            for n in d.numbers:
                if n in last_seen:
                    gaps[n].append(idx-last_seen[n])
                appearances[n].append(idx)
                last_seen[n] = idx

        # daily life cards for all 80
        for n in range(1,81):
            pos = appearances[n]
            gs = [b-a for a,b in zip(pos,pos[1:])]
            daily_life.append({
                "date":str(day),"number":n,
                "appearances":len(pos),
                "first_draw_no":day_draws[pos[0]].draw_no if pos else None,
                "last_draw_no":day_draws[pos[-1]].draw_no if pos else None,
                "gap_sequence":"-".join(map(str,gs)),
                "gap_count":len(gs),
                "mean_gap":(sum(gs)/len(gs)) if gs else None,
                "median_gap":float(pd.Series(gs).median()) if gs else None,
                "max_sleep":max(gs) if gs else None,
                "H1_H3_gaps":sum(1<=g<=3 for g in gs),
                "H4_H6_gaps":sum(4<=g<=6 for g in gs),
                "H7_H14_gaps":sum(7<=g<=14 for g in gs),
                "H15plus_gaps":sum(g>=15 for g in gs),
                "rhythm_signature_count":sum(bool(rhythm_labels(gs[:i])) for i in range(3,len(gs)+1)),
                "last_digit":n%10
            })

    dfs = {
        "draw_band_trace": pd.DataFrame(draw_trace),
        "life_events": pd.DataFrame(life_events),
        "daily_life_cards": pd.DataFrame(daily_life),
        "rhythm_events": pd.DataFrame(rhythm_events),
        "sleep_wake_events": pd.DataFrame(sleep_events),
        "last_digit_family_trace": pd.DataFrame(sibling_trace),
        "last_digit_follow_events": pd.DataFrame(sibling_follow),
        "consecutive_blocks": pd.DataFrame(consecutive),
        "skip_one_blocks": pd.DataFrame(skip_one),
        "pair_colife_events": pd.DataFrame(pair_rows),
        "hour_trace": pd.DataFrame(hour_rows),
    }

    # ---------- 14-day combined summaries ----------
    if not dfs["rhythm_events"].empty:
        dfs["rhythm_summary_14d"] = (
            dfs["rhythm_events"].groupby("pattern",as_index=False)
            .agg(
                events=("number","size"),
                days=("date","nunique"),
                numbers=("number","nunique"),
                next1_rate=("next1_hit","mean"),
                next3_mean_hits=("next3_hit_count","mean"),
                next6_mean_hits=("next6_hit_count","mean"),
            ).sort_values(["events","next1_rate"],ascending=[False,False])
        )
    else:
        dfs["rhythm_summary_14d"] = pd.DataFrame()

    if not dfs["sleep_wake_events"].empty:
        dfs["sleep_wake_summary_14d"] = (
            dfs["sleep_wake_events"].groupby("wake_band",as_index=False)
            .agg(
                events=("number","size"),days=("date","nunique"),numbers=("number","nunique"),
                next1_rate=("next1_hit","mean"),
                next3_mean_hits=("next3_hit_count","mean"),
                next6_mean_hits=("next6_hit_count","mean"),
            )
        )
    else:
        dfs["sleep_wake_summary_14d"] = pd.DataFrame()

    if not dfs["pair_colife_events"].empty:
        dfs["pair_summary_14d"] = (
            dfs["pair_colife_events"].groupby(["a","b","same_last_digit"],as_index=False)
            .agg(events=("draw_no","size"),days=("date","nunique"))
            .sort_values(["events","days"],ascending=[False,False])
        )
    else:
        dfs["pair_summary_14d"] = pd.DataFrame()

    if not dfs["last_digit_family_trace"].empty:
        dfs["last_digit_family_summary_14d"] = (
            dfs["last_digit_family_trace"].groupby("last_digit",as_index=False)
            .agg(
                rows=("draw_no","size"),
                mean_hits=("real20_hit_count","mean"),
                max_hits=("real20_hit_count","max"),
                mean_pre_active=("pre_active_count","mean"),
            )
        )
    else:
        dfs["last_digit_family_summary_14d"] = pd.DataFrame()

    # hourly normalized number frequencies
    if not dfs["hour_trace"].empty:
        h = dfs["hour_trace"].copy()
        # explode numbers
        rows = []
        for _,r in h.iterrows():
            nums = [int(x) for x in str(r["numbers"]).split()]
            for n in nums:
                rows.append({"date":r["date"],"hour":r["hour"],"number":n,"draw_no":r["draw_no"]})
        hx = pd.DataFrame(rows)
        draw_counts = h.groupby(["date","hour"]).size().rename("draws").reset_index()
        hf = hx.groupby(["date","hour","number"]).size().rename("hits").reset_index()
        hf = hf.merge(draw_counts,on=["date","hour"],how="left")
        hf["hit_rate_per_draw"] = hf["hits"]/hf["draws"]
        dfs["hour_number_frequency_normalized"] = hf
    else:
        dfs["hour_number_frequency_normalized"] = pd.DataFrame()

    # per-number 14-day identity summary
    if not dfs["daily_life_cards"].empty:
        dlf = dfs["daily_life_cards"].copy()
        dfs["number_identity_14d"] = (
            dlf.groupby("number",as_index=False)
            .agg(
                days=("date","nunique"),
                total_appearances=("appearances","sum"),
                mean_daily_appearances=("appearances","mean"),
                mean_gap=("mean_gap","mean"),
                mean_max_sleep=("max_sleep","mean"),
                max_sleep_seen=("max_sleep","max"),
                short_gaps=("H1_H3_gaps","sum"),
                mid_gaps=("H4_H6_gaps","sum"),
                long_gaps=("H7_H14_gaps","sum"),
                deep_gaps=("H15plus_gaps","sum"),
            )
        )
    else:
        dfs["number_identity_14d"] = pd.DataFrame()

    return dfs

def txt_summary(dfs, meta):
    lines = [
        "HIZLI ON ARASTIRMA LABORATUVARI V3",
        f"Toplam cekilis: {meta['draw_count']}",
        f"Gun sayisi: {meta['day_count']}",
        f"Ilk: {meta['first_dt']}",
        f"Son: {meta['last_dt']}",
        "",
        "ANALIZLER:",
        "- Tek gun karakteri / K1-K8 fazlari",
        "- 1-80 gunluk yasam kartlari",
        "- H yas / tasima-donus bantlari",
        "- ritim: 1-2-1, 1-1-2, 2-1-1, ABAB, sabit, artan, azalan",
        "- katlanan ritimler: x2 ve yaklasik katlanma",
        "- ritim kirilmasi icin olay bazli sonraki 1/3/6 el",
        "- uyku-uyanis: H7+ ve derin uykular",
        "- son rakam kardesligi ve kardes takip mesafesi",
        "- ardisik bloklar",
        "- birer atlamali bloklar",
        "- ikili birlikte yasama / pair co-life",
        "- saat bazinda normalize frekans",
        "- 14 gunluk sayi kimligi",
        "",
        "DOSYALAR:"
    ]
    for k,v in dfs.items():
        lines.append(f"- {k}.csv : {len(v)} satir")
    return "\n".join(lines)

def make_zip(dfs,audit,meta):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        for name,df in dfs.items():
            z.writestr(f"{name}.csv", df.to_csv(index=False))
        z.writestr("file_audit.csv", audit.to_csv(index=False))
        z.writestr("RAPOR_INDEX.txt", txt_summary(dfs,meta))
        z.writestr("meta.json", json.dumps(meta,ensure_ascii=False,indent=2,default=str))
    return bio.getvalue()

# -------------------------- UI --------------------------
st.set_page_config(page_title="Hızlı On Araştırma Laboratuvarı V3", layout="wide")
st.title("Hızlı On — Araştırma Laboratuvarı V3")
st.caption("Repo verisini otomatik bulur. Dosya yükleme yok. Önce gün gün, sonra 14 gün bütün olarak analiz eder.")

ROOT = Path(".").resolve()

@st.cache_data(show_spinner=False)
def cached_load(root_str):
    return load_repo(Path(root_str))

@st.cache_data(show_spinner=False)
def cached_analyze(serialized):
    draws = [Draw(x["draw_no"],x["dt"],x["numbers"],x["source"]) for x in serialized]
    return analyze(draws)

draws, audit = cached_load(str(ROOT))

if not draws:
    st.error("Repo içinde okunabilir Hızlı On TXT/CSV verisi bulunamadı.")
    st.write("Taranan klasörler:", ", ".join(SEARCH_DIRS))
    st.dataframe(audit, use_container_width=True)
    st.stop()

day_count = len(set(d.date for d in draws))
c1,c2,c3,c4 = st.columns(4)
c1.metric("Çekiliş",len(draws))
c2.metric("Gün",day_count)
c3.metric("İlk",draws[0].dt.strftime("%d.%m.%Y %H:%M"))
c4.metric("Son",draws[-1].dt.strftime("%d.%m.%Y %H:%M"))

if day_count == 14 and len(draws) == 3038:
    st.success("14 günlük veri doğru algılandı: 14 gün / 3038 çekiliş.")
elif day_count == 14:
    st.warning(f"14 gün bulundu fakat çekiliş sayısı {len(draws)}. Beklenen 3038.")
else:
    st.warning(f"Repo verisinde {day_count} gün / {len(draws)} çekiliş algılandı. Beklenen 14 gün / 3038 çekiliş.")

serialized = [
    {"draw_no":d.draw_no,"dt":str(d.dt),"numbers":list(d.numbers),"source":d.source}
    for d in draws
]

with st.spinner("Gün gün ve 14 günlük araştırma kütükleri hazırlanıyor..."):
    dfs = cached_analyze(serialized)

tabs = st.tabs([
    "Özet","Dosya Denetimi","1-80 Günlük Yaşam","Ritim","Uyku/Uyanış",
    "Son Rakam Kardeşliği","Ardışık","Birer Atlamalı","İkili Sosyal Bağ",
    "Saat/Faz","H-Bant","14 Gün Kimlik","Dışa Aktar"
])

with tabs[0]:
    st.write("**Analiz mantığı:** Her gün bağımsız yaşam olarak okunur; sonra 14 gün üst üste karşılaştırılır.")
    st.dataframe(dfs["rhythm_summary_14d"],use_container_width=True)
with tabs[1]:
    st.dataframe(audit,use_container_width=True,height=600)
with tabs[2]:
    st.dataframe(dfs["daily_life_cards"],use_container_width=True,height=650)
with tabs[3]:
    st.subheader("14 Gün Ritim Özeti")
    st.dataframe(dfs["rhythm_summary_14d"],use_container_width=True)
    st.subheader("Tüm PRE-H Ritim Olayları")
    st.dataframe(dfs["rhythm_events"],use_container_width=True,height=500)
with tabs[4]:
    st.dataframe(dfs["sleep_wake_summary_14d"],use_container_width=True)
    st.dataframe(dfs["sleep_wake_events"],use_container_width=True,height=500)
with tabs[5]:
    st.dataframe(dfs["last_digit_family_summary_14d"],use_container_width=True)
    st.dataframe(dfs["last_digit_follow_events"],use_container_width=True,height=500)
with tabs[6]:
    st.dataframe(dfs["consecutive_blocks"],use_container_width=True,height=600)
with tabs[7]:
    st.dataframe(dfs["skip_one_blocks"],use_container_width=True,height=600)
with tabs[8]:
    st.dataframe(dfs["pair_summary_14d"],use_container_width=True,height=600)
with tabs[9]:
    st.subheader("Normalize Saat Frekansı")
    st.dataframe(dfs["hour_number_frequency_normalized"],use_container_width=True,height=600)
with tabs[10]:
    st.dataframe(dfs["draw_band_trace"],use_container_width=True,height=600)
with tabs[11]:
    st.dataframe(dfs["number_identity_14d"],use_container_width=True,height=600)
with tabs[12]:
    meta = {
        "draw_count":len(draws),
        "day_count":day_count,
        "first_dt":draws[0].dt,
        "last_dt":draws[-1].dt,
        "method":"Her gun bagimsiz; PRE-H yalniz onceki cekilislerden; sonra 14 gun toplu."
    }
    z = make_zip(dfs,audit,meta)
    st.download_button(
        "ARAŞTIRMA KÜTÜKLERİNİ ZIP İNDİR",
        data=z,
        file_name="HIZLI_ON_ARASTIRMA_KUTUKLERI_V3.zip",
        mime="application/zip",
        type="primary"
    )
    st.write("İndirdiğin ZIP'i bana ver; çıkan davranışları birlikte derinlemesine inceleyelim.")
