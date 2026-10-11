# -*- coding: utf-8 -*-
import io
import math
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import combinations

import numpy as np
import pandas as pd
import requests
import streamlit as st

APP_TITLE = "🧠 Hızlı On — Kapsamlı Aile & Ritim Laboratuvarı V3"
DEFAULT_RAW_URL = "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"

st.set_page_config(page_title="Hızlı On Aile Ritim V3", page_icon="🧠", layout="wide")
st.title(APP_TITLE)
st.caption("1 Ağustos–9 Ekim veri.txt • normal 6’lı • 3+3 özel 6’lı • gün içi 2/3 vuruş • +77 küme-eko • 10’lu gün ritimleri")

# ============================================================
# Sabit kombinasyon tabloları — sadece 82.160 üçlü
# ============================================================
TRIPLES = np.array(list(combinations(range(1, 81), 3)), dtype=np.int16)
TCOUNT = len(TRIPLES)  # 82160
TRIPLE_KEYS = (
    TRIPLES[:, 0].astype(np.int32)
    | (TRIPLES[:, 1].astype(np.int32) << 7)
    | (TRIPLES[:, 2].astype(np.int32) << 14)
)
KEY_TO_RANK = np.full(1 << 21, -1, dtype=np.int32)
KEY_TO_RANK[TRIPLE_KEYS] = np.arange(TCOUNT, dtype=np.int32)
POS3 = np.array(list(combinations(range(20), 3)), dtype=np.int16)
P0, P1, P2 = POS3.T

# 80 bit = low64 + high16
TRI_LO = np.zeros(TCOUNT, dtype=np.uint64)
TRI_HI = np.zeros(TCOUNT, dtype=np.uint64)
for col in range(3):
    vals = TRIPLES[:, col]
    low = vals <= 64
    TRI_LO[low] |= np.left_shift(np.uint64(1), (vals[low] - 1).astype(np.uint64))
    TRI_HI[~low] |= np.left_shift(np.uint64(1), (vals[~low] - 65).astype(np.uint64))


def triple_name(rank: int) -> str:
    return "-".join(map(str, TRIPLES[int(rank)].tolist()))


def pair_code(a: int, b: int) -> int:
    if a > b:
        a, b = b, a
    return int(a) * TCOUNT + int(b)


def decode_pair(code: int):
    return divmod(int(code), TCOUNT)


def pair_coupon(code: int) -> str:
    a, b = decode_pair(code)
    nums = sorted(set(TRIPLES[a].tolist()) | set(TRIPLES[b].tolist()))
    return "-".join(map(str, nums))


def nums_to_split_mask(nums):
    lo = 0
    hi = 0
    for n in nums:
        if n <= 64:
            lo |= 1 << (int(n) - 1)
        else:
            hi |= 1 << (int(n) - 65)
    return np.uint64(lo), np.uint64(hi)


def split_mask_to_nums(lo: int, hi: int):
    out = []
    x = int(lo)
    while x:
        lsb = x & -x
        out.append(lsb.bit_length())
        x ^= lsb
    x = int(hi)
    while x:
        lsb = x & -x
        out.append(64 + lsb.bit_length())
        x ^= lsb
    return out


# ============================================================
# Veri
# ============================================================
@st.cache_data(ttl=90, show_spinner=False)
def fetch_text(url: str, cache_bust: int = 0) -> str:
    sep = "&" if "?" in url else "?"
    r = requests.get(
        f"{url}{sep}_cb={cache_bust}", timeout=30,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    r.raise_for_status()
    return r.text


@st.cache_data(show_spinner=False)
def parse_veri(text: str):
    rows = []
    seen = set()
    for raw in text.splitlines():
        p = raw.strip().split(";")
        if len(p) != 3:
            continue
        try:
            draw_id = int(p[0].strip())
            dt = datetime.strptime(p[1].strip(), "%d.%m.%Y %H:%M")
            nums = tuple(sorted(int(x.strip()) for x in p[2].split(",") if x.strip()))
        except Exception:
            continue
        if draw_id in seen or len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
            continue
        seen.add(draw_id)
        lo, hi = nums_to_split_mask(nums)
        rows.append((draw_id, dt, nums, lo, hi))
    rows.sort(key=lambda r: r[1])
    return rows


def draw_triple_ids(nums):
    n = np.asarray(nums, dtype=np.int32)
    keys = n[P0] | (n[P1] << 7) | (n[P2] << 14)
    return KEY_TO_RANK[keys]


def df_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def build_zip(files: dict):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8-sig")
            z.writestr(name, data)
    return bio.getvalue()


# ============================================================
# 3'lü aile — sabit bellekli hızlı tarama
# ============================================================
def mine_triples_dense(records, max_gap=60, progress=None):
    max_gap = int(max_gap)
    last = np.full(TCOUNT, -999999, dtype=np.int32)
    freq = np.zeros(TCOUNT, dtype=np.uint16)
    gaps = np.zeros((TCOUNT, max_gap + 1), dtype=np.uint16)
    nrec = len(records)

    for pos, r in enumerate(records):
        ids = draw_triple_ids(r[2])
        freq[ids] += 1
        g = pos - last[ids]
        v = (g >= 1) & (g <= max_gap)
        if np.any(v):
            np.add.at(gaps, (ids[v], g[v]), 1)
        last[ids] = pos
        if progress is not None and (pos % 400 == 0 or pos + 1 == nrec):
            progress.progress(min(0.45, 0.45 * (pos + 1) / nrec), text=f"3'lü aile ritimleri: {pos+1:,}/{nrec:,}")

    body = gaps[:, 1:]
    best_count = body.max(axis=1)
    best_gap = body.argmax(axis=1) + 1
    return freq, best_gap, best_count


def choose_families(freq, best_gap, best_count, requested_min=7, safe_limit=500, auto_safe=True):
    threshold = int(requested_min)
    if auto_safe:
        while threshold < 100 and int(np.sum(best_count >= threshold)) > int(safe_limit):
            threshold += 1
    qualified = np.where(best_count >= threshold)[0]
    # strongest first; safety hard-cap remains even if auto is off
    score_order = np.lexsort((qualified, -freq[qualified].astype(np.int32), -best_count[qualified].astype(np.int32)))
    ordered = qualified[score_order]
    selected = ordered[: int(safe_limit)]
    return threshold, qualified, selected


def mine_pairs_safe(records, selected_families, pair_min_repeat=3, progress=None):
    selected_flag = np.zeros(TCOUNT, dtype=bool)
    selected_flag[selected_families] = True
    active = []
    counts = Counter()
    nrec = len(records)

    for pos, r in enumerate(records):
        ids = draw_triple_ids(r[2])
        arr = ids[selected_flag[ids]]
        active.append(arr.astype(np.int32, copy=False))
        L = len(arr)
        for ii in range(L - 1):
            rest = arr[ii + 1 :]
            dis = ((TRI_LO[arr[ii]] & TRI_LO[rest]) == 0) & ((TRI_HI[arr[ii]] & TRI_HI[rest]) == 0)
            rr = rest[dis]
            if len(rr):
                codes = arr[ii].astype(np.int64) * TCOUNT + rr.astype(np.int64)
                counts.update(map(int, codes.tolist()))
        if progress is not None and (pos % 400 == 0 or pos + 1 == nrec):
            progress.progress(0.45 + 0.30 * (pos + 1) / nrec, text=f"3+3 çiftleri: {pos+1:,}/{nrec:,}")

    eligible = {c: n for c, n in counts.items() if n >= int(pair_min_repeat)}
    eligible_set = set(eligible)
    pairsets = []
    events = []
    day_hits = defaultdict(lambda: defaultdict(list))

    for idx, arr in enumerate(active):
        local = set()
        L = len(arr)
        for ii in range(L - 1):
            rest = arr[ii + 1 :]
            dis = ((TRI_LO[arr[ii]] & TRI_LO[rest]) == 0) & ((TRI_HI[arr[ii]] & TRI_HI[rest]) == 0)
            for b in rest[dis]:
                c = pair_code(int(arr[ii]), int(b))
                if c in eligible_set:
                    local.add(c)
        pairsets.append(local)
        if local:
            draw_id, dt = records[idx][0], records[idx][1]
            for c in local:
                a, b = decode_pair(c)
                day_hits[c][dt.date()].append(idx)
                events.append({
                    "_idx": idx, "_pair": c,
                    "Çekiliş": draw_id, "Tarih": dt.date(), "Saat": dt.strftime("%H:%M"),
                    "Aile A": triple_name(a), "Aile B": triple_name(b),
                    "6'lı Kupon": pair_coupon(c), "Pair Toplam 6/6": int(eligible[c]),
                })
        if progress is not None and (idx % 500 == 0 or idx + 1 == nrec):
            progress.progress(0.75 + 0.25 * (idx + 1) / nrec, text=f"Olay raporu: {idx+1:,}/{nrec:,}")

    pair_rows = []
    for c, total in sorted(eligible.items(), key=lambda kv: (-kv[1], kv[0])):
        a, b = decode_pair(c)
        perday = day_hits[c]
        same2 = sum(len(v) >= 2 for v in perday.values())
        same3 = sum(len(v) >= 3 for v in perday.values())
        hits = sorted(i for vv in perday.values() for i in vv)
        gc = Counter(y - x for x, y in zip(hits, hits[1:]))
        mg, mn = gc.most_common(1)[0] if gc else ("", 0)
        pair_rows.append({
            "_pair": c, "Aile A": triple_name(a), "Aile B": triple_name(b),
            "6'lı Kupon": pair_coupon(c), "Toplam 6/6": int(total), "Aktif Gün": len(perday),
            "Aynı Gün 2+ Gün": same2, "Aynı Gün 3+ Gün": same3,
            "En Sık Pair Gap": mg, "Gap Tekrar": mn,
        })
    return active, pairsets, pair_rows, events


def summarize_events(events):
    if not events:
        return pd.DataFrame(), pd.DataFrame()
    e = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in events])
    daily = e.groupby("Tarih", as_index=False).agg(**{
        "3+3 Olay": ("Çekiliş", "size"), "Farklı 6'lı": ("6'lı Kupon", "nunique"), "Aktif Çekiliş": ("Çekiliş", "nunique")
    }).sort_values("Tarih")
    t = e.copy(); t["SaatDilimi"] = t["Saat"].str[:2] + ":00"
    hourly = t.groupby(["Tarih", "SaatDilimi"], as_index=False).agg(**{
        "3+3 Olay": ("Çekiliş", "size"), "Farklı 6'lı": ("6'lı Kupon", "nunique"), "Aktif Çekiliş": ("Çekiliş", "nunique")
    }).sort_values(["Tarih", "SaatDilimi"])
    return daily, hourly


# ============================================================
# +77 küme-eko
# ============================================================
def cluster_echo(records, pairsets, gap=77, min_cluster=6, same_day_only=True):
    src_rows, rows = [], []
    n = len(records)
    for i, src in enumerate(pairsets):
        if len(src) < int(min_cluster):
            continue
        j = i + int(gap)
        if j >= n:
            continue
        if same_day_only and records[i][1].date() != records[j][1].date():
            continue
        inter = src & pairsets[j]
        src_rows.append({
            "Kaynak Çekiliş": records[i][0], "Kaynak": records[i][1].strftime("%d.%m.%Y %H:%M"),
            "Kaynak Küme": len(src), "Hedef Çekiliş": records[j][0], "Hedef": records[j][1].strftime("%d.%m.%Y %H:%M"),
            "Echo 6/6 Adet": len(inter),
        })
        for c in sorted(inter):
            a, b = decode_pair(c)
            rows.append({
                "Gap": int(gap), "Kaynak Çekiliş": records[i][0], "Kaynak": records[i][1].strftime("%d.%m.%Y %H:%M"),
                "Kaynak Küme": len(src), "Hedef Çekiliş": records[j][0], "Hedef": records[j][1].strftime("%d.%m.%Y %H:%M"),
                "Aile A": triple_name(a), "Aile B": triple_name(b), "6'lı Kupon": pair_coupon(c), "Sonuç": "6/6 EKO",
            })
    return src_rows, rows


def scan_echo_gaps(records, pairsets, max_gap=200, min_cluster=6, same_day_only=True):
    cand = [i for i, s in enumerate(pairsets) if len(s) >= int(min_cluster)]
    out = []
    n = len(records)
    for gap in range(1, int(max_gap) + 1):
        srcn = ed = ep = 0
        for i in cand:
            j = i + gap
            if j >= n:
                continue
            if same_day_only and records[i][1].date() != records[j][1].date():
                continue
            srcn += 1
            k = len(pairsets[i] & pairsets[j])
            if k:
                ed += 1; ep += k
        if srcn:
            out.append({"Gap": gap, "Kaynak Küme": srcn, "Echo Olan Hedef": ed, "Echo 6/6 Adet": ep,
                        "Kaynak Başına Echo": round(ep/srcn, 4)})
    return sorted(out, key=lambda r: (-r["Echo 6/6 Adet"], -r["Kaynak Başına Echo"], r["Gap"]))




# ============================================================
# NORMAL 6'LI AİLE — 3+3 ŞARTI YOK
# ============================================================
def family6_mask(fam):
    return nums_to_split_mask(fam)


def mine_normal6_rhythm(records, day_gaps=(0,2,5), deep=False, max_expand_size=8,
                        candidate_cap=60000, verify_top=4000, progress=None):
    """
    Normal 6'lı aileleri 3+3 şartı olmadan bulur.

    Hızlı mod: iki çekilişin ortak bloğu TAM 6 sayıysa seed üretir.
    Derin mod: 7..max_expand_size ortak bloklarını da bütün 6'lı alt kümelere açar.
    Büyük ortak bloklar raporlanır ama belleği korumak için açılmaz.

    day_gaps içinde 0 = aynı gün. Diğerleri gün farkıdır.
    """
    bydate=date_map(records)
    dates=sorted(bydate)
    dset=set(dates)
    lo_all=np.array([r[3] for r in records],dtype=np.uint64)
    hi_all=np.array([r[4] for r in records],dtype=np.uint64)

    jobs=[]
    for gap in sorted(set(map(int,day_gaps))):
        if gap==0:
            jobs.extend((0,d,d) for d in dates)
        else:
            jobs.extend((gap,d,d+timedelta(days=gap)) for d in dates if d+timedelta(days=gap) in dset)

    famdata={}
    big=[]
    truncated=False
    done=0
    total=max(1,len(jobs))

    for gap,d1,d2 in jobs:
        I=bydate[d1]; J=bydate[d2]
        l1=lo_all[I][:,None]; h1=hi_all[I][:,None]
        l2=lo_all[J][None,:]; h2=hi_all[J][None,:]
        il=l1 & l2; ih=h1 & h2
        bc=np.bitwise_count(il)+np.bitwise_count(ih)
        if gap==0:
            tri=np.triu(np.ones(bc.shape,dtype=bool),1)
        else:
            tri=np.ones(bc.shape,dtype=bool)
        if deep:
            mask=tri & (bc>=6) & (bc<=int(max_expand_size))
        else:
            mask=tri & (bc==6)
        rr,cc=np.where(mask)

        # büyük blokları yalnız özetle
        br,bc2=np.where(tri & (bc>int(max_expand_size)))
        for a,b in zip(br[:200].tolist(),bc2[:200].tolist()):
            nums=split_mask_to_nums(il[a,b],ih[a,b])
            big.append({
                'Gün Gap':gap,'1. Gün':d1,'2. Gün':d2,
                '1. Saat':records[I[a]][1].strftime('%H:%M'),'2. Saat':records[J[b]][1].strftime('%H:%M'),
                'Ortak Blok Boyutu':len(nums),'Ortak Blok':'-'.join(map(str,nums)),
                'Not':'Bellek güvenliği için 6’lı alt kümelere açılmadı'
            })

        for a,b in zip(rr.tolist(),cc.tolist()):
            i=I[a]; j=J[b]
            nums=split_mask_to_nums(il[a,b],ih[a,b])
            fams=[tuple(nums)] if len(nums)==6 else combinations(nums,6)
            for fam in fams:
                fam=tuple(fam)
                info=famdata.get(fam)
                if info is None:
                    if len(famdata)>=int(candidate_cap):
                        truncated=True
                        continue
                    info={'draws':set(),'links':set(),'examples':[]}
                    famdata[fam]=info
                info['draws'].update((i,j))
                info['links'].add((gap,d1,d2))
                if len(info['examples'])<4:
                    info['examples'].append((records[i][1],records[j][1],gap))

        done+=1
        if progress is not None:
            progress.progress(min(0.72,0.72*done/total),text=f"Normal 6’lı tarama: {done}/{total} gün bağlantısı • aday {len(famdata):,}")

    # En güçlü adayların gerçek bütün veri desteğini doğrula.
    ranked=sorted(famdata.items(), key=lambda kv:(-len({records[i][1].date() for i in kv[1]['draws']}),-len(kv[1]['draws']),kv[0]))
    verify=set(f for f,_ in ranked[:int(verify_top)])
    rows=[]
    totalr=max(1,len(ranked))
    for z,(fam,info) in enumerate(ranked):
        if fam in verify:
            flo,fhi=family6_mask(fam)
            hit=np.where(((lo_all & flo)==flo) & ((hi_all & fhi)==fhi))[0].tolist()
            verified=True
        else:
            hit=sorted(info['draws'])
            verified=False
        dayc=Counter(records[i][1].date() for i in hit)
        links=info['links']
        gapc=Counter(g for g,a,b in links if g>0)
        bestgap,bestn=gapc.most_common(1)[0] if gapc else ('',0)
        ex=' | '.join(f"{a.strftime('%d.%m %H:%M')}→{b.strftime('%d.%m %H:%M')} (g{g})" for a,b,g in info['examples'])
        rows.append({
            "6'lı Aile":'-'.join(map(str,fam)),
            'Toplam Görünüş':len(hit),'Aktif Gün':len(dayc),
            'Aynı Gün Max':max(dayc.values()) if dayc else 0,
            'Aynı Gün 2+ Gün':sum(v>=2 for v in dayc.values()),
            'Aynı Gün 3+ Gün':sum(v>=3 for v in dayc.values()),
            'En Güçlü Gün Gap':bestgap,'Gap Tekrar Gün Bağı':bestn,
            'Seed Bağlantı':len(links),'Tam Doğrulama':'EVET' if verified else 'SEED',
            'Örnek':ex,
        })
        if progress is not None and z%500==0:
            progress.progress(0.72+0.28*(z+1)/totalr,text=f"Normal 6’lı doğrulama: {z+1:,}/{len(ranked):,}")
    rows.sort(key=lambda r:(-r['Aktif Gün'],-r['Toplam Görünüş'],-r['Aynı Gün Max'],r["6'lı Aile"]))
    return {'rows':rows,'big_blocks':big,'candidate_n':len(famdata),'truncated':truncated,'deep':deep}


def normal6_daily_hourly(records, rows, topn=1000):
    # Rapor amaçlı: en güçlü normal 6'lıların gün/saat görünüşleri
    if not rows:
        return pd.DataFrame(),pd.DataFrame()
    fams=[]
    for r in rows[:int(topn)]:
        fam=tuple(map(int,r["6'lı Aile"].split('-')))
        lo,hi=family6_mask(fam)
        fams.append((r["6'lı Aile"],lo,hi))
    lo_all=np.array([x[3] for x in records],dtype=np.uint64)
    hi_all=np.array([x[4] for x in records],dtype=np.uint64)
    daily=Counter(); hourly=Counter()
    for name,lo,hi in fams:
        ids=np.where(((lo_all&lo)==lo)&((hi_all&hi)==hi))[0]
        for i in ids:
            d=records[int(i)][1]
            daily[d.date()]+=1; hourly[(d.date(),d.strftime('%H:00'))]+=1
    ddf=pd.DataFrame([{'Tarih':d,'Normal 6 Görünüş':n} for d,n in sorted(daily.items())])
    hdf=pd.DataFrame([{'Tarih':d,'Saat':h,'Normal 6 Görünüş':n} for (d,h),n in sorted(hourly.items())])
    return ddf,hdf


# ============================================================
# 10'lu ritim — doğrudan gün çiftlerinden, tekrar tarama YOK
# ============================================================
def date_map(records):
    out = defaultdict(list)
    for i, r in enumerate(records):
        out[r[1].date()].append(i)
    return out


def expand_intersection_to_10(lo, hi, max_expand_size=14):
    nums = split_mask_to_nums(int(lo), int(hi))
    k = len(nums)
    if k < 10:
        return [], k
    if k > int(max_expand_size):
        return None, k
    return list(combinations(nums, 10)), k


def analyze_10_rhythm_fast(records, day_gaps=(2,5), max_expand_size=14, progress=None):
    bydate = date_map(records)
    dates = sorted(bydate)
    dset = set(dates)
    # family -> gap -> date-pair -> occurrence info
    fam_events = defaultdict(lambda: defaultdict(dict))
    big_blocks = []
    work = [(g,d) for g in day_gaps for d in dates if d + timedelta(days=int(g)) in dset]
    total_work = max(1, len(work)); done = 0

    for gap in day_gaps:
        gap = int(gap)
        for d in dates:
            d2 = d + timedelta(days=gap)
            if d2 not in dset:
                continue
            I, J = bydate[d], bydate[d2]
            lo1 = np.array([records[i][3] for i in I], dtype=np.uint64)[:,None]
            hi1 = np.array([records[i][4] for i in I], dtype=np.uint64)[:,None]
            lo2 = np.array([records[j][3] for j in J], dtype=np.uint64)[None,:]
            hi2 = np.array([records[j][4] for j in J], dtype=np.uint64)[None,:]
            il = lo1 & lo2; ih = hi1 & hi2
            bc = np.bitwise_count(il) + np.bitwise_count(ih)
            rr, cc = np.where(bc >= 10)

            for a, b in zip(rr.tolist(), cc.tolist()):
                inter_lo, inter_hi = il[a,b], ih[a,b]
                fams, size = expand_intersection_to_10(inter_lo, inter_hi, max_expand_size)
                if fams is None:
                    big_blocks.append({
                        "Gün Aralığı": gap, "1. Gün": d, "2. Gün": d2,
                        "Ortak Blok Boyutu": int(size), "Ortak Blok": "-".join(map(str, split_mask_to_nums(inter_lo, inter_hi))),
                        "1. Saat": records[I[a]][1].strftime("%H:%M"), "2. Saat": records[J[b]][1].strftime("%H:%M"),
                        "Not": f"Güvenlik için {max_expand_size}'ten büyük blok 10'lulara açılmadı",
                    })
                    continue
                for fam in fams:
                    key = (d, d2)
                    e = fam_events[fam][gap].get(key)
                    if e is None:
                        fam_events[fam][gap][key] = {
                            "count": 1,
                            "t1": records[I[a]][1].strftime("%H:%M"),
                            "t2": records[J[b]][1].strftime("%H:%M"),
                        }
                    else:
                        e["count"] += 1
            done += 1
            if progress is not None:
                progress.progress(min(1.0, done/total_work), text=f"10'lu ritim: {done}/{total_work} gün çifti")

    repeat_rows = []
    progression_rows = []
    special_812 = []
    special_sep812 = []

    for fam, gapmap in fam_events.items():
        famtxt = "-".join(map(str, fam))
        for gap, pairs in gapmap.items():
            if not pairs:
                continue
            sorted_pairs = sorted(pairs)
            dates_used = sorted(set(x for ab in sorted_pairs for x in ab))
            repeat_rows.append({
                "Gün Aralığı": gap, "10'lu Aile": famtxt,
                "Gün Çifti Adet": len(sorted_pairs), "Tekrar Eden Gün Sayısı": len(dates_used),
                "İlk Gün": dates_used[0], "Son Gün": dates_used[-1],
                "Örnek": " | ".join(f"{a.strftime('%d.%m')} {pairs[(a,b)]['t1']} → {b.strftime('%d.%m')} {pairs[(a,b)]['t2']}" for a,b in sorted_pairs[:6]),
            })
            pairset = set(sorted_pairs)
            for d, d2 in sorted_pairs:
                d3 = d2 + timedelta(days=gap)
                if (d2, d3) in pairset:
                    row = {
                        "Ritim": f"+{gap} gün, +{gap} gün", "10'lu Aile": famtxt,
                        "1. Gün": d, "2. Gün": d2, "3. Gün": d3,
                        "1→2 Saat": f"{pairs[(d,d2)]['t1']}→{pairs[(d,d2)]['t2']}",
                        "2→3 Saat": f"{pairs[(d2,d3)]['t1']}→{pairs[(d2,d3)]['t2']}",
                    }
                    progression_rows.append(row)
                    if gap == 2 and d.strftime("%d.%m.%Y") == "08.08.2026":
                        special_812.append(row.copy())
                    if gap == 2 and d.strftime("%d.%m.%Y") == "08.09.2026":
                        special_sep812.append(row.copy())

    # dedupe progressions
    seen=set(); pp=[]
    for r in progression_rows:
        k=(r["Ritim"],r["10'lu Aile"],r["1. Gün"],r["2. Gün"],r["3. Gün"])
        if k not in seen:
            seen.add(k); pp.append(r)
    progression_rows=pp
    repeat_rows.sort(key=lambda r:(r["Gün Aralığı"], -r["Gün Çifti Adet"], r["10'lu Aile"]))
    progression_rows.sort(key=lambda r:(r["Ritim"], r["1. Gün"], r["10'lu Aile"]))
    special_812.sort(key=lambda r:r["10'lu Aile"])
    special_sep812.sort(key=lambda r:r["10'lu Aile"])
    return {"repeats":repeat_rows, "progressions":progression_rows, "special_812":special_812, "special_sep812":special_sep812, "big_blocks":big_blocks}


# ============================================================
# UI / veri
# ============================================================
with st.sidebar:
    st.header("Veri Kaynağı")
    raw_url = st.text_input("GitHub raw veri.txt", value=DEFAULT_RAW_URL)
    if "cache_bust" not in st.session_state:
        st.session_state.cache_bust = 0
    if st.button("🔄 GitHub verisini yenile", use_container_width=True):
        st.session_state.cache_bust = int(time.time())
        st.cache_data.clear()
        for k in ["a33v2","normal6v3","echo_scan_v2","tenv2"]:
            st.session_state.pop(k, None)
        st.rerun()

try:
    text = fetch_text(raw_url, int(st.session_state.cache_bust))
    all_records = parse_veri(text)
except Exception as e:
    st.error(f"veri.txt okunamadı: {e}")
    st.stop()

if not all_records:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

all_dates=[r[1].date() for r in all_records]
min_date,max_date=min(all_dates),max(all_dates)
with st.sidebar:
    st.success(f"{len(all_records):,} çekiliş • {min_date.strftime('%d.%m.%Y')} → {max_date.strftime('%d.%m.%Y')}")
    start_date=st.date_input("Başlangıç", value=min_date, min_value=min_date, max_value=max_date)
    end_date=st.date_input("Bitiş", value=max_date, min_value=min_date, max_value=max_date)
    if start_date>end_date:
        st.error("Başlangıç bitişten büyük olamaz."); st.stop()

records=[r for r in all_records if start_date <= r[1].date() <= end_date]
if not records:
    st.stop()

if min_date <= datetime(2026,8,1).date() and max_date >= datetime(2026,10,9).date():
    st.success("✅ 1 Ağustos–9 Ekim kapsaması veri.txt içinde görünüyor.")
else:
    st.warning(f"Görünen kapsam: {min_date.strftime('%d.%m.%Y')}–{max_date.strftime('%d.%m.%Y')}")

sig=(str(start_date),str(end_date),len(records),records[0][0],records[-1][0])
if st.session_state.get("data_sig") != sig:
    st.session_state.data_sig=sig
    for k in ["a33v2","normal6v3","echo_scan_v2","tenv2"]:
        st.session_state.pop(k,None)


tab0,tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs([
    "🧭 Laboratuvar","🧩 Normal 6'lı","🧬 3+3 Özel 6'lı","🎯 +77 / Eko",
    "🔟 10'lu Ritim","🕐 Gün/Saat","📚 Rehber","📦 Rapor"
])

with tab0:
    st.subheader("Kapsamlı Aile & Ritim Laboratuvarı")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Çekiliş",f"{len(records):,}")
    c2.metric("Gün",len(set(r[1].date() for r in records)))
    c3.metric("İlk",records[0][1].strftime("%d.%m.%Y %H:%M"))
    c4.metric("Son",records[-1][1].strftime("%d.%m.%Y %H:%M"))
    st.markdown("""
### Bu app'te neye bakıyoruz?
- **Normal 6'lı aile:** 3+3 şartı yok. Aynı 6 sayı farklı çekiliş/günlerde yeniden yaşıyor mu? Aynı gün 2–3 kez vuruyor mu? +2 / +5 gün ritmi var mı?
- **3+3 özel 6'lı:** iki ayrık 3'lü ailenin aynı çekilişte 3/3 + 3/3 = 6/6 birleşmesi.
- **Gün içi tekrar:** aynı 6'lı ailenin bir günde 2 veya 3 kez görünmesi; 1→2 ve 2→3 çekiliş gapleri.
- **Küme‑Eko:** özellikle **+77**, ayrıca +1…+300 bütün çekiliş gapleri.
- **10'lu aile:** aynı 10 sayının +2 / +5 gün ve üç tarih zincirleri. **08→10→12 Eylül** ayrıca kontrol edilir.
- **Gün / saat:** hangi gün ve saat dilimlerinde aile yoğunluğu artıyor?
- **Rapor:** bütün sonuçları tek ZIP.
""")
    st.info("Normal 6'lı ile 3+3 aynı şey değildir. 3+3, normal 6'lıların yalnız özel bir alt türüdür.")

with tab1:
    st.subheader("🧩 Normal 6'lı aileler — 3+3 şartı YOK")
    st.caption("İki çekilişte ortak yaşayan altı sayıyı aile olarak izler. Hızlı mod exact 6 ortak çekirdeği tarar; derin mod 7–8 sayılık ortak blokların içindeki 6'lıları da açar.")
    a,b,c,d=st.columns(4)
    with a:
        ngaps=st.multiselect("Gün ritimleri (0=aynı gün)",[0,1,2,3,4,5,6,7,10,14],default=[0,2,5])
    with b:
        deep6=st.checkbox("Derin mod: 7/8 ortak blokları da 6'lıya aç",value=False)
    with c:
        maxexp6=st.slider("Derin ortak blok üstü",6,10,8,1,disabled=not deep6)
    with d:
        cap6=st.number_input("Aday güvenlik limiti",10000,120000,60000,5000)
    verify6=st.slider("Tam doğrulanacak en güçlü aile",500,10000,4000,500)
    if st.button("🚀 NORMAL 6'LI ANALİZİNİ BAŞLAT",type="primary",use_container_width=True):
        if not ngaps:
            st.warning("En az bir gün ritmi seç.")
        else:
            prog=st.progress(0,text="Normal 6'lı taraması başlıyor...")
            st.session_state.normal6v3=mine_normal6_rhythm(records,tuple(ngaps),bool(deep6),int(maxexp6),int(cap6),int(verify6),prog)
            prog.progress(1.0,text="Normal 6'lı tamamlandı ✅")
    if "normal6v3" in st.session_state:
        nr=st.session_state.normal6v3
        ndf=pd.DataFrame(nr["rows"])
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Normal 6'lı aday",nr["candidate_n"])
        c2.metric("Farklı gün 2+ yaşayan",int((ndf["Aktif Gün"]>=2).sum()) if not ndf.empty else 0)
        c3.metric("Aynı gün 2+",int((ndf["Aynı Gün Max"]>=2).sum()) if not ndf.empty else 0)
        c4.metric("Aynı gün 3+",int((ndf["Aynı Gün Max"]>=3).sum()) if not ndf.empty else 0)
        if nr["truncated"]:
            st.warning("Aday güvenlik limitine ulaşıldı. Sonuç çökmemesi için yeni aday üretimi sınırlandı; limiti yükseltip yeniden tarayabilirsin.")
        st.markdown("**En çok farklı günde yaşayan normal 6'lılar**")
        if not ndf.empty:
            st.dataframe(ndf.head(3000),use_container_width=True,height=500)
            st.download_button("Normal 6'lı CSV",df_bytes(ndf),"normal_6li_aileler.csv","text/csv")
            f2=ndf[ndf["Aktif Gün"]>=2]
            f3=ndf[ndf["Aynı Gün Max"]>=3]
            with st.expander("Farklı günlerde yaşayanlar"):
                st.dataframe(f2.head(5000),use_container_width=True,height=450)
            with st.expander("Aynı gün 3 kez yaşayanlar"):
                st.dataframe(f3,use_container_width=True,height=380)
        bdf=pd.DataFrame(nr["big_blocks"])
        if not bdf.empty:
            with st.expander("Açılmayan büyük ortak bloklar"):
                st.dataframe(bdf.head(2000),use_container_width=True,height=350)
    else:
        st.info("Normal 6'lı analizi ayrı çalışır; 3+3 analizine bağlı değildir.")

with tab2:
    st.subheader("🧬 3+3 — özel 6'lı aile")
    st.caption("Bütün 82.160 üçlü taranır. Sonra iki ayrık 3'lü aynı çekilişte birleştiğinde 3+3=6/6 olarak raporlanır.")
    a,b,c,d=st.columns(4)
    with a: max_gap=st.number_input("Exact gap üst sınırı",10,217,60,1,key="a33_gap")
    with b: minrep=st.number_input("Başlangıç gap tekrar eşiği",2,50,7,1,key="a33_rep")
    with c: famcap=st.number_input("Güvenli aile havuzu limiti",100,1500,500,50,key="a33_cap")
    with d: pairmin=st.number_input("3+3 çift min 6/6",1,30,3,1,key="a33_pair")
    autosafe=st.checkbox("Aile sayısı fazlaysa eşiği otomatik yükselt (önerilen)",value=True,key="a33_auto")
    if st.button("🚀 3+3 ANALİZİNİ BAŞLAT",type="primary",use_container_width=True):
        prog=st.progress(0,text="Başlıyor...")
        freq,bgap,bcount=mine_triples_dense(records,int(max_gap),prog)
        eff,qualified,selected=choose_families(freq,bgap,bcount,int(minrep),int(famcap),bool(autosafe))
        prog.progress(0.45,text=f"Ritimli aile: {len(qualified):,} • 3+3 havuzu: {len(selected):,}")
        active,pairsets,pair_rows,events=mine_pairs_safe(records,selected,int(pairmin),prog)
        daily,hourly=summarize_events(events)
        selected_set=set(map(int,selected))
        fam_rows=[{"3'lü Aile":triple_name(int(k)),"3/3 Görünüş":int(freq[k]),"En Güçlü Exact Gap":int(bgap[k]),"Gap Tekrar":int(bcount[k]),"3+3 Havuzunda":"EVET" if int(k) in selected_set else "HAYIR"} for k in qualified]
        fam_rows.sort(key=lambda r:(-r["Gap Tekrar"],-r["3/3 Görünüş"],r["3'lü Aile"]))
        st.session_state.a33v2={"family_rows":fam_rows,"pair_rows":pair_rows,"events":events,"pairsets":pairsets,"daily":daily,"hourly":hourly,"effective":eff,"qualified_n":len(qualified),"selected_n":len(selected)}
        prog.progress(1.0,text="Tamamlandı ✅")
    if "a33v2" in st.session_state:
        r=st.session_state.a33v2
        pdf=pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["pair_rows"]])
        edf=pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["events"]])
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Ritimli 3'lü",r["qualified_n"]); c2.metric("3+3 havuz",r["selected_n"])
        c3.metric("3+3 çift",len(pdf)); c4.metric("6/6 olay",len(edf))
        st.dataframe(pdf.head(3000),use_container_width=True,height=420)
        if not pdf.empty:
            with st.expander("Aynı gün 3 kez yaşayan 3+3 aileler"):
                st.dataframe(pdf[pdf["Aynı Gün 3+ Gün"]>0],use_container_width=True,height=350)
        st.download_button("3+3 çiftler CSV",df_bytes(pdf),"3arti3_ciftler.csv","text/csv")
        with st.expander("Bütün 3+3=6/6 olayları"):
            st.dataframe(edf.head(5000),use_container_width=True,height=500)
            st.download_button("3+3 olaylar CSV",df_bytes(edf),"3arti3_tum_olaylar.csv","text/csv")
    else:
        st.info("3+3 analizini başlat.")

with tab3:
    st.subheader("🎯 +77 Küme‑Eko ve tüm gap taraması")
    if "a33v2" not in st.session_state:
        st.info("Önce 3+3 analizini çalıştır; küme‑eko 3+3 olay kümelerini izler.")
    else:
        r=st.session_state.a33v2
        a,b,c=st.columns(3)
        with a: egap=st.number_input("Eko gap",1,400,77,1,key="echo_gap")
        with b: mincluster=st.number_input("Kaynak küme min 6/6",1,200,6,1,key="echo_cluster")
        with c: sameday=st.checkbox("Aynı gün içinde",value=True,key="echo_same")
        src,echo=cluster_echo(records,r["pairsets"],int(egap),int(mincluster),bool(sameday))
        c1,c2,c3=st.columns(3)
        c1.metric("Kaynak küme",len(src)); c2.metric(f"+{egap} eko 6/6",len(echo)); c3.metric("Eko hedef çekiliş",len(set(x["Hedef Çekiliş"] for x in echo)) if echo else 0)
        if echo: st.dataframe(pd.DataFrame(echo),use_container_width=True,height=420)
        maxscan=st.slider("Tüm eko gap tarama üst sınırı",20,300,200,key="echo_scanmax")
        if st.button("🔎 1→üst gap tara",use_container_width=True):
            st.session_state.echo_scan_v2=scan_echo_gaps(records,r["pairsets"],int(maxscan),int(mincluster),bool(sameday))
        if "echo_scan_v2" in st.session_state:
            st.dataframe(pd.DataFrame(st.session_state.echo_scan_v2).head(300),use_container_width=True,height=450)

with tab4:
    st.subheader("🔟 10'lu aile ritimleri")
    st.caption("+2 / +5 gün ve seçilen diğer gün aralıkları. Üç tarih zincirleri ayrıca çıkarılır.")
    gaps=st.multiselect("Gün aralıkları",[1,2,3,4,5,6,7,10],default=[2,5],key="ten_gaps")
    maxexpand=st.slider("Ortak blok en fazla kaç sayıya kadar 10'lulara açılsın?",10,15,14,key="ten_expand")
    if st.button("🔟 10'LU RİTİM ANALİZİNİ BAŞLAT",type="primary",use_container_width=True):
        if not gaps:
            st.warning("En az bir gün aralığı seç.")
        else:
            prog=st.progress(0,text="10'lu ritimler hazırlanıyor...")
            st.session_state.tenv2=analyze_10_rhythm_fast(records,tuple(sorted(set(map(int,gaps)))),int(maxexpand),prog)
            prog.progress(1.0,text="Tamamlandı ✅")
    if "tenv2" in st.session_state:
        t=st.session_state.tenv2
        rdf=pd.DataFrame(t["repeats"]); pdf=pd.DataFrame(t["progressions"])
        aug=pd.DataFrame(t.get("special_812",[])); sep=pd.DataFrame(t.get("special_sep812",[]))
        c1,c2,c3=st.columns(3)
        c1.metric("Tekrar eden 10'lu",len(rdf)); c2.metric("3 tarihli ritim",len(pdf)); c3.metric("08→10→12 Eylül",len(sep))
        st.markdown("### 08 → 10 → 12 Eylül özel kontrol")
        if not sep.empty:
            st.success("✅ Aynı 10'lu aile 08.09 → 10.09 → 12.09 zincirinde bulundu.")
            st.dataframe(sep,use_container_width=True,height=260)
        else:
            st.info("Seçili ayarlarda 08→10→12 Eylül exact 10'lu zinciri bulunmadı.")
        if not aug.empty:
            with st.expander("08→10→12 Ağustos ayrıca"):
                st.dataframe(aug,use_container_width=True,height=250)
        st.markdown("**Bütün 3 tarihli 10'lu ritimler**")
        if not pdf.empty: st.dataframe(pdf,use_container_width=True,height=430)
        st.markdown("**Tekrar eden 10'lular**")
        if not rdf.empty: st.dataframe(rdf.head(5000),use_container_width=True,height=500)

with tab5:
    st.subheader("🕐 Gün / saat yoğunluğu")
    if "a33v2" in st.session_state:
        st.markdown("**3+3 günlük**"); st.dataframe(st.session_state.a33v2["daily"],use_container_width=True,height=300)
        st.markdown("**3+3 saatlik**"); st.dataframe(st.session_state.a33v2["hourly"],use_container_width=True,height=380)
    else:
        st.info("3+3 günlük/saatlik tablo için 3+3 analizini çalıştır.")
    if "normal6v3" in st.session_state:
        d6,h6=normal6_daily_hourly(records,st.session_state.normal6v3["rows"],topn=1000)
        st.markdown("**Normal 6'lı — en güçlü 1000 aile günlük**")
        st.dataframe(d6,use_container_width=True,height=300)
        st.markdown("**Normal 6'lı — en güçlü 1000 aile saatlik**")
        st.dataframe(h6,use_container_width=True,height=380)

with tab6:
    st.subheader("📚 Nasıl okuyacağız?")
    st.markdown("""
**Normal 6'lı:** Herhangi bir altı sayının tekrar davranışı. 3+3 olma şartı yok.  
**3+3 özel 6'lı:** İki ayrı 3'lü ailenin aynı çekilişte tam birleşmesi.  
**Aynı gün 2+/3+:** Bir ailenin aynı gün kaç kez yeniden 6/6 olduğu.  
**Gün gap:** +2, +5 gibi farklı tarihler arasındaki ritim.  
**Çekiliş gap:** +39→+44 veya +79→+82 gibi çekiliş sayısı ritimleri.  
**+77 Küme‑Eko:** Bir çekilişte çok sayıda 3+3 oluştuğunda +77 çekiliş sonra aynı çiftlerden kaçı tekrar 6/6 oluyor.  
**10'lu üç tarih zinciri:** aynı 10 sayının örn. 08→10→12 Eylül gibi iki eşit gün aralığıyla tekrar etmesi.

Önce **normal 6'lı** ve **10'lu ritim** ile geniş yapıyı çıkar; sonra 3+3 ve +77 özel motorlarıyla derine in.
""")

with tab7:
    st.subheader("📦 Tek ZIP rapor")
    files={"00_BILGI.txt":f"Veri: {records[0][1]} -> {records[-1][1]}\nÇekiliş: {len(records)}\nKapsamlı V3 aile-ritim motoru\n"}
    if "normal6v3" in st.session_state:
        nr=st.session_state.normal6v3
        files["01_NORMAL_6LU_AILELER.csv"]=df_bytes(pd.DataFrame(nr["rows"]))
        files["02_NORMAL_6_BUYUK_BLOKLAR.csv"]=df_bytes(pd.DataFrame(nr["big_blocks"]))
    if "a33v2" in st.session_state:
        r=st.session_state.a33v2
        files["03_3LU_AILELER.csv"]=df_bytes(pd.DataFrame(r["family_rows"]))
        files["04_3ARTI3_CIFTLER.csv"]=df_bytes(pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["pair_rows"]]))
        files["05_3ARTI3_OLAYLAR.csv"]=df_bytes(pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["events"]]))
        files["06_3ARTI3_GUNLUK.csv"]=df_bytes(r["daily"]); files["07_3ARTI3_SAATLIK.csv"]=df_bytes(r["hourly"])
        s,e=cluster_echo(records,r["pairsets"],77,6,True)
        files["08_PLUS77_KAYNAK.csv"]=df_bytes(pd.DataFrame(s)); files["09_PLUS77_EKO.csv"]=df_bytes(pd.DataFrame(e))
    if "echo_scan_v2" in st.session_state:
        files["10_EKO_GAP_TARAMA.csv"]=df_bytes(pd.DataFrame(st.session_state.echo_scan_v2))
    if "tenv2" in st.session_state:
        t=st.session_state.tenv2
        files["11_10LU_TEKRAR.csv"]=df_bytes(pd.DataFrame(t["repeats"]))
        files["12_10LU_3TARIH.csv"]=df_bytes(pd.DataFrame(t["progressions"]))
        files["13_08_10_12_EYLUL.csv"]=df_bytes(pd.DataFrame(t.get("special_sep812",[])))
        files["14_08_10_12_AGUSTOS.csv"]=df_bytes(pd.DataFrame(t.get("special_812",[])))
        files["15_10LU_BUYUK_BLOKLAR.csv"]=df_bytes(pd.DataFrame(t["big_blocks"]))
    st.download_button("⬇️ TÜM RAPORLARI ZIP İNDİR",build_zip(files),"HIZLI_ON_KAPSAMLI_V3_TUM_RAPORLAR.zip","application/zip",use_container_width=True)

st.caption("V3 Streamlit Cloud için bellek kontrollü tasarlanmıştır. Normal 6’lı, 3+3 ve 10’lu ayrı motorlardır. Geçmiş ritimler gelecekte sonucu garanti etmez.")
