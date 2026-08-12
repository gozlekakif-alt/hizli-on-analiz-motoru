
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import base64
import io
import re

import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Hızlı On Saat Bazlı Canlı Faz Motoru",
    page_icon="🧠",
    layout="wide",
)

BASE_FILE = Path(__file__).with_name("veri.txt")
COLS = ["Cekilis_No", "Tarih", "Saat"] + [f"Sayi_{i}" for i in range(1, 21)]
NUM_COLS = [f"Sayi_{i}" for i in range(1, 21)]

# ============================================================
# VERİ OKUMA / YAZMA
# ============================================================
def parse_standard_line(line: str):
    raw = str(line).strip()
    if not raw:
        return None

    parts = [p.strip() for p in raw.split(";")]
    if len(parts) == 4:
        try:
            no = int(parts[0])
            tarih = parts[1].replace("/", ".")
            saat = parts[2][:5]
            nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", parts[3])]
            if len(nums) == 20 and len(set(nums)) == 20 and all(1 <= n <= 80 for n in nums):
                return [no, tarih, saat] + sorted(nums)
        except Exception:
            pass

    if len(parts) >= 23:
        try:
            no = int(parts[0])
            tarih = parts[1].replace("/", ".")
            saat = parts[2][:5]
            nums = [int(x) for x in parts[3:23]]
            if len(nums) == 20 and len(set(nums)) == 20 and all(1 <= n <= 80 for n in nums):
                return [no, tarih, saat] + sorted(nums)
        except Exception:
            pass

    return None

def parse_draw_block(text: str):
    no = re.search(r"(?mi)^\s*Çekiliş\s*no\s*:\s*(\d+)\s*$", text)
    dt = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})", text)
    nums = [int(x) for x in re.findall(r"(?m)^\s*(\d{1,2})\s*$", text)]
    if not no or not dt or len(nums) != 20:
        return None
    if len(set(nums)) != 20 or any(n < 1 or n > 80 for n in nums):
        return None
    return [int(no.group(1)), dt.group(1), dt.group(2)] + sorted(nums)

def dataframe_from_text(text: str):
    rows = []
    for line in str(text).splitlines():
        r = parse_standard_line(line)
        if r:
            rows.append(r)

    if "Çekiliş no:" in str(text):
        blocks = re.split(r"(?=Çekiliş\s*no\s*:)", str(text), flags=re.I)
        for block in blocks:
            r = parse_draw_block(block)
            if r:
                rows.append(r)

    df = pd.DataFrame(rows, columns=COLS)
    return clean_df(df)

def clean_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    out = df.copy()
    for c in ["Cekilis_No"] + NUM_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["Cekilis_No"] + NUM_COLS)
    out["Cekilis_No"] = out["Cekilis_No"].astype(int)
    for c in NUM_COLS:
        out[c] = out[c].astype(int)

    valid = out[NUM_COLS].apply(
        lambda r: len(set(r.tolist())) == 20 and all(1 <= int(n) <= 80 for n in r),
        axis=1,
    )
    out = out[valid]
    out = out.drop_duplicates("Cekilis_No", keep="last").sort_values("Cekilis_No")
    return out[COLS].reset_index(drop=True)

def merge_data(*frames):
    good = [f for f in frames if f is not None and not f.empty]
    if not good:
        return pd.DataFrame(columns=COLS)
    return clean_df(pd.concat(good, ignore_index=True))

def to_text(df):
    lines = []
    for _, row in df.sort_values("Cekilis_No").iterrows():
        nums = ",".join(str(int(row[c])) for c in NUM_COLS)
        lines.append(f"{int(row.Cekilis_No)};{row.Tarih};{row.Saat};{nums}")
    return "\n".join(lines) + ("\n" if lines else "")

@st.cache_data(show_spinner=False)
def load_base_text():
    if not BASE_FILE.exists():
        return ""
    return BASE_FILE.read_text(encoding="utf-8", errors="ignore")

def load_base_df():
    return dataframe_from_text(load_base_text())

def exact_twenty(text):
    cleaned = str(text)
    cleaned = re.sub(r"(?mi)^\s*Çekiliş\s*no\s*:\s*\d+\s*$", " ", cleaned)
    cleaned = re.sub(r"(?mi)^\s*\d{2}[./]\d{2}[./]\d{4}\s*-\s*\d{2}:\d{2}\s*$", " ", cleaned)
    nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", cleaned)]
    if len(nums) != 20 or len(set(nums)) != 20:
        return None
    return sorted(nums)

# ============================================================
# GITHUB KALICI KAYIT
# ============================================================
def github_settings():
    try:
        g = st.secrets["github"]
        return {
            "token": g["token"],
            "owner": g.get("owner", "gozlekakif-alt"),
            "repo": g.get("repo", "hizli-on-analiz-motoru"),
            "branch": g.get("branch", "main"),
            "path": g.get("data_path", "veri.txt"),
        }, None
    except Exception:
        return None, "Streamlit Secrets içinde [github] ayarları yok."

def github_headers(token):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def get_github_text(settings):
    url = f"https://api.github.com/repos/{settings['owner']}/{settings['repo']}/contents/{settings['path']}"
    r = requests.get(
        url,
        headers=github_headers(settings["token"]),
        params={"ref": settings["branch"]},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"GitHub veri.txt okunamadı: {r.status_code} {r.text[:250]}")
    p = r.json()
    return base64.b64decode(p["content"]).decode("utf-8", errors="ignore"), p["sha"]

def save_github_df(df, message):
    settings, err = github_settings()
    if err:
        raise RuntimeError(err)
    _, sha = get_github_text(settings)
    url = f"https://api.github.com/repos/{settings['owner']}/{settings['repo']}/contents/{settings['path']}"
    payload = {
        "message": message,
        "content": base64.b64encode(to_text(df).encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": settings["branch"],
    }
    r = requests.put(
        url,
        headers=github_headers(settings["token"]),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub kayıt başarısız: {r.status_code} {r.text[:350]}")
    st.cache_data.clear()

# ============================================================
# TAKVİM / SAAT
# ============================================================
def row_dt(row):
    return datetime.strptime(f"{row.Tarih} {row.Saat}", "%d.%m.%Y %H:%M")

def next_draw_dt(last_dt):
    if last_dt.hour == 1 and last_dt.minute == 2:
        return (last_dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    x = last_dt + timedelta(minutes=5)
    if (x.hour == 1 and x.minute > 2) or (2 <= x.hour < 7):
        return (last_dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    return x

def next_defaults(df):
    if df.empty:
        return 1, datetime.now().strftime("%d.%m.%Y"), "07:02"
    last = df.iloc[-1]
    ndt = next_draw_dt(row_dt(last))
    return int(last.Cekilis_No)+1, ndt.strftime("%d.%m.%Y"), ndt.strftime("%H:%M")

def minute_of_day(t):
    h,m = map(int, str(t)[:5].split(":"))
    return h*60+m

def same_hour_indices(df, target_time, lookback=None):
    h = int(str(target_time)[:2])
    work = df if lookback is None else df.tail(min(lookback, len(df)))
    return [i for i,r in work.iterrows() if int(str(r.Saat)[:2]) == h]

def same_slot_indices(df, target_time, tolerance=7, lookback=None):
    tm = minute_of_day(target_time)
    work = df if lookback is None else df.tail(min(lookback, len(df)))
    out = []
    for i,r in work.iterrows():
        d = abs(minute_of_day(r.Saat)-tm)
        d = min(d, 1440-d)
        if d <= tolerance:
            out.append(i)
    return out

# ============================================================
# OYUN KARAKTERİ / FAZ
# ============================================================
def row_sets(df):
    return [set(map(int, r)) for r in df[NUM_COLS].to_numpy()]

def consecutive_blocks(nums):
    nums = sorted(nums)
    if not nums:
        return []
    blocks, cur = [], [nums[0]]
    for n in nums[1:]:
        if n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2:
                blocks.append(cur)
            cur = [n]
    if len(cur) >= 2:
        blocks.append(cur)
    return blocks

def behavior_profile(prev, cur):
    blocks = consecutive_blocks(cur)
    band20 = [
        sum(1 <= n <= 20 for n in cur),
        sum(21 <= n <= 40 for n in cur),
        sum(41 <= n <= 60 for n in cur),
        sum(61 <= n <= 80 for n in cur),
    ]
    return np.array([
        len(prev & cur),
        len(cur - prev),
        len(blocks),
        sum(len(b)==2 for b in blocks),
        sum(len(b)>=3 for b in blocks),
        max([len(b) for b in blocks], default=1),
        *band20
    ], dtype=float)

def detect_active_phase(df, lookback=48):
    sets = row_sets(df)
    if len(sets) < 8:
        return max(0, len(sets)-4), min(len(sets), 4)

    start = max(1, len(sets)-lookback)
    prof = []
    idxs = []
    for i in range(start, len(sets)):
        prof.append(behavior_profile(sets[i-1], sets[i]))
        idxs.append(i)

    P = np.vstack(prof)
    scale = P.std(axis=0)
    scale[scale < 0.75] = 0.75
    breaks = [max(0, start-6)]

    # Fazı tek bir sıçramayla değil, kalıcı karakter değişimiyle kır.
    for j in range(6, len(P)):
        before = P[j-6:j-2].mean(axis=0)
        after = P[j-2:j+1].mean(axis=0)
        d = float(np.sqrt(np.mean(((after-before)/scale)**2)))
        if d >= 1.45:
            candidate = idxs[j-2]
            # Ardışık iki aday birbirine çok yakınsa sonuncuyu alma.
            if candidate - breaks[-1] >= 4:
                breaks.append(candidate)

    phase_start = max(breaks[-1], len(sets)-18) if len(sets)-breaks[-1] > 18 else breaks[-1]
    phase_age = len(sets)-phase_start
    return phase_start, phase_age

def phase_state(df, phase_start):
    sets = row_sets(df)
    phase_sets = sets[phase_start:]
    if len(phase_sets) < 2:
        return "Yeni Faz"

    carries = []
    blocks = []
    for i in range(1, len(phase_sets)):
        carries.append(len(phase_sets[i-1] & phase_sets[i]))
        blocks.append(sum(max(0,len(b)-1) for b in consecutive_blocks(phase_sets[i])))

    avg_c = np.mean(carries) if carries else 0
    avg_b = np.mean(blocks) if blocks else 0

    if avg_c >= 6.2:
        return "Taşıma Fazı"
    if avg_b >= 3.0:
        return "Blok/Ardışık Fazı"
    if avg_c <= 3.8:
        return "Yenilenme Fazı"
    return "Karışık Faz"

# ============================================================
# SAAT BAZLI MOTOR
# ============================================================
def freq_rate_from_indices(df, idxs):
    c = Counter()
    for i in idxs:
        c.update(int(df.loc[i,cname]) for cname in NUM_COLS)
    denom = max(len(idxs),1)
    return np.array([c.get(n,0)/denom for n in range(1,81)], float)

def transition_rate(df, n, lookback=260):
    sets = row_sets(df.tail(min(lookback,len(df))).reset_index(drop=True))
    cases=hits=0
    for i in range(len(sets)-1):
        if n in sets[i]:
            cases += 1
            hits += int(n in sets[i+1])
    return (hits+1.5)/(cases+6.0)

def return_rate(df, n, gap_target, lookback=260):
    sets = row_sets(df.tail(min(lookback,len(df))).reset_index(drop=True))
    cases=hits=0
    for i in range(gap_target, len(sets)-1):
        if n in sets[i-gap_target] and all(n not in sets[k] for k in range(i-gap_target+1, i+1)):
            cases += 1
            hits += int(n in sets[i+1])
    return (hits+1.0)/(cases+5.0)

def block_support_scores(df, window=6):
    scores = np.zeros(80,float)
    sets = row_sets(df.tail(min(window,len(df))).reset_index(drop=True))
    for s in sets:
        for b in consecutive_blocks(s):
            w = max(1, len(b)-1)
            for n in b:
                scores[n-1] += w
            for n in range(max(1,b[0]-1), min(80,b[-1]+1)+1):
                scores[n-1] += 0.30
    if scores.max() > 0:
        scores /= scores.max()
    return scores

def similar_hour_character_scores(df, target_time, state_window=4, search_window=320):
    if len(df) < state_window + 30:
        return np.zeros(80,float)

    work = df.tail(min(search_window,len(df))).reset_index(drop=True)
    sets = row_sets(work)

    feats = []
    for i in range(1,len(sets)):
        feats.append(behavior_profile(sets[i-1], sets[i]))
    F = np.vstack(feats)

    cur = F[-state_window:].mean(axis=0)
    mu = F.mean(axis=0)
    sd = F.std(axis=0)
    sd[sd < 0.5] = 1.0
    curz = (cur-mu)/sd

    target_hour = int(str(target_time)[:2])
    matches=[]
    for end in range(state_window, len(F)-1):
        hist = F[end-state_window:end].mean(axis=0)
        dist=float(np.sqrt(np.mean((((hist-mu)/sd)-curz)**2)))
        next_idx=end+1
        hour = int(str(work.iloc[next_idx].Saat)[:2])
        hour_bonus = 1.25 if hour == target_hour else 0.70
        sim = hour_bonus/(0.20+dist)
        matches.append((sim,next_idx))

    matches=sorted(matches, reverse=True)[:20]
    score=np.zeros(80,float)
    tw=0
    for w,i in matches:
        tw+=w
        score += w*np.array([1.0 if n in sets[i] else 0.0 for n in range(1,81)])
    if tw>0:
        score/=tw
    return score

def live_hour_character_score(df, target_time):
    phase_start, phase_age = detect_active_phase(df)
    state = phase_state(df, phase_start)

    sets = row_sets(df)
    phase_sets = sets[phase_start:]
    last = sets[-1]

    # SAAT ANA EKSEN
    hour_idx = same_hour_indices(df, target_time, lookback=420)
    slot_idx = same_slot_indices(df, target_time, tolerance=7, lookback=420)
    hour_rate = freq_rate_from_indices(df, hour_idx)
    slot_rate = freq_rate_from_indices(df, slot_idx)

    # AKTİF FAZ SICAK ÇEKİRDEĞİ
    phase_counter=Counter()
    for s in phase_sets:
        phase_counter.update(s)
    phase_hot=np.array([phase_counter.get(n,0)/max(len(phase_sets),1) for n in range(1,81)],float)

    # SICAK ÇEKİRDEK = son 8 + aktif faz birlikte.
    last8 = sets[-8:] if len(sets)>=8 else sets
    core_counter=Counter()
    for s in last8:
        core_counter.update(s)
    core_hot=np.array([core_counter.get(n,0)/max(len(last8),1) for n in range(1,81)],float)

    # Çekirdek sürekliliği: son 3 elde görünme / son 8 içindeki pay.
    last3 = sets[-3:] if len(sets)>=3 else sets
    persist=np.array([
        (sum(n in s for s in last3)/max(len(last3),1))*0.65 +
        core_hot[n-1]*0.35
        for n in range(1,81)
    ],float)

    # KISA CANLI AKIŞ
    short_counter=Counter()
    for s in last8[-5:]:
        short_counter.update(s)
    short_hot=np.array([short_counter.get(n,0)/max(min(5,len(last8)),1) for n in range(1,81)],float)

    # TAŞIMA / DÖNÜŞ / BLOK / BENZER SAAT KARAKTERİ
    carry=np.array([transition_rate(df,n) for n in range(1,81)],float)

    gaps={}
    for n in range(1,81):
        g=len(sets)
        for i,s in enumerate(reversed(sets)):
            if n in s:
                g=i
                break
        gaps[n]=g

    ret=np.array([
        return_rate(df,n,gaps[n]) if 1 <= gaps[n] <= 4 else 0.0
        for n in range(1,81)
    ],float)

    block=block_support_scores(df,6)
    similar=similar_hour_character_scores(df,target_time)

    last_bonus=np.array([1.0 if n in last else 0.0 for n in range(1,81)])

    # TÜM GEÇMİŞ SADECE DESTEK
    all_recent_idx=list(range(max(0,len(df)-120),len(df)))
    history=freq_rate_from_indices(df, all_recent_idx)

    # FAZA GÖRE AĞIRLIK: saat her zaman en önemli
    weights = {
        "hour":0.30,
        "slot":0.14,
        "phase":0.16,
        "core":0.12,
        "persist":0.07,
        "short":0.05,
        "carry":0.05,
        "return":0.04,
        "block":0.03,
        "similar":0.03,
        "history":0.01,
    }

    if state == "Taşıma Fazı":
        weights["carry"] += 0.05
        weights["persist"] += 0.03
        weights["phase"] += 0.02
        weights["slot"] -= 0.03
        weights["short"] -= 0.01
        weights["return"] -= 0.01
        weights["similar"] -= 0.01
        weights["history"] -= 0.01
        weights["block"] -= 0.01
        weights["core"] -= 0.02
    elif state == "Blok/Ardışık Fazı":
        weights["block"] += 0.06
        weights["core"] += 0.03
        weights["phase"] += 0.02
        weights["hour"] -= 0.02
        weights["slot"] -= 0.02
        weights["carry"] -= 0.01
        weights["return"] -= 0.01
        weights["short"] -= 0.01
        weights["similar"] -= 0.01
        weights["history"] -= 0.01
        weights["persist"] -= 0.02
    elif state == "Yenilenme Fazı":
        weights["return"] += 0.05
        weights["core"] += 0.03
        weights["similar"] += 0.02
        weights["phase"] += 0.02
        weights["carry"] -= 0.03
        weights["persist"] -= 0.02
        weights["slot"] -= 0.02
        weights["short"] -= 0.01
        weights["history"] -= 0.01
        weights["block"] -= 0.01
        weights["hour"] -= 0.01

    total=sum(weights.values())
    weights={k:v/total for k,v in weights.items()}

    score=(
        weights["hour"]*hour_rate +
        weights["slot"]*slot_rate +
        weights["phase"]*phase_hot +
        weights["core"]*core_hot +
        weights["persist"]*persist +
        weights["short"]*short_hot +
        weights["carry"]*(carry*last_bonus + 0.35*carry*(1-last_bonus)) +
        weights["return"]*ret +
        weights["block"]*block +
        weights["similar"]*similar +
        weights["history"]*history
    )

    rows=[]
    for n in range(1,81):
        reason=[]
        if hour_rate[n-1] >= np.quantile(hour_rate,0.70): reason.append("saat güçlü")
        if phase_hot[n-1] >= 0.42: reason.append("faz sıcak")
        if core_hot[n-1] >= 0.50: reason.append("sıcak çekirdek")
        if persist[n-1] >= 0.60: reason.append("çekirdek sürekliliği")
        if n in last and carry[n-1] >= np.quantile(carry,0.65): reason.append("taşıma")
        if 1 <= gaps[n] <= 4 and ret[n-1] >= 0.24: reason.append(f"{gaps[n]} el dönüş")
        if block[n-1] >= 0.35: reason.append("blok/ardışık")
        if similar[n-1] >= np.quantile(similar,0.70): reason.append("benzer saat karakteri")

        rows.append({
            "Sayı":n,
            "Puan":round(score[n-1]*100,3),
            "Saat %":round(hour_rate[n-1]*100,2),
            "Slot %":round(slot_rate[n-1]*100,2),
            "Faz sıcak %":round(phase_hot[n-1]*100,2),
            "Çekirdek %":round(core_hot[n-1]*100,2),
            "Süreklilik %":round(persist[n-1]*100,2),
            "Taşıma %":round(carry[n-1]*100,2),
            "Dinlenme":gaps[n],
            "Dönüş %":round(ret[n-1]*100,2),
            "Blok %":round(block[n-1]*100,2),
            "Benzer %":round(similar[n-1]*100,2),
            "Neden":", ".join(reason) if reason else "destek",
        })

    tab=pd.DataFrame(rows).sort_values(["Puan","Sayı"],ascending=[False,True]).reset_index(drop=True)

    top=tab["Puan"].head(10).to_numpy()
    spread=float(top[0]-top[6]) if len(top)>=7 else 0.0

    # Kullanıcının hedefi 7'li kupon performansı. Çok düşük güven dışında 7'li üret.
    # 3/4/5'e düşürmek önceki testte toplam isabeti gereksiz biçimde kesti.
    if phase_age <= 1 and spread >= 18:
        size=5
    else:
        size=7

    coupon=sorted(tab.head(size)["Sayı"].astype(int).tolist())
    meta={
        "phase_start":phase_start,
        "phase_age":phase_age,
        "state":state,
        "hour_samples":len(hour_idx),
        "slot_samples":len(slot_idx),
        "weights":weights,
    }
    return coupon,tab,meta

# ============================================================
# KÖR TEST
# ============================================================
def blind_test_chunk(df,start_i,end_i):
    rows=[]
    for i in range(start_i,end_i):
        train=df.iloc[:i].copy()
        if len(train)<100:
            continue
        target_time=str(df.iloc[i].Saat)
        coupon,_,meta=live_hour_character_score(train,target_time)
        actual=set(int(df.iloc[i][c]) for c in NUM_COLS)
        hits=sorted(set(coupon)&actual)

        # Aynı büyüklükte basit saat-frekans baz çizgisi:
        hour_idx = same_hour_indices(train, target_time, lookback=420)
        base_rate = freq_rate_from_indices(train, hour_idx)
        baseline = sorted((np.argsort(base_rate)[::-1][:len(coupon)] + 1).tolist())
        base_hits = sorted(set(baseline) & actual)

        rows.append({
            "Çekiliş":int(df.iloc[i].Cekilis_No),
            "Tarih":df.iloc[i].Tarih,
            "Saat":df.iloc[i].Saat,
            "Faz":meta["state"],
            "Faz yaşı":meta["phase_age"],
            "Kupon boyu":len(coupon),
            "Kupon":"-".join(map(str,coupon)),
            "İsabet":len(hits),
            "Tutan":"-".join(map(str,hits)),
            "Baz Kupon":"-".join(map(str,baseline)),
            "Baz İsabet":len(base_hits),
            "Avantaj":len(hits)-len(base_hits),
            "Sızıntı":"TEMİZ",
        })
    return pd.DataFrame(rows)

# ============================================================
# SESSION
# ============================================================
base_df=load_base_df()
if "pool_df" not in st.session_state:
    st.session_state.pool_df=base_df.copy()
df=clean_df(st.session_state.pool_df)

# ============================================================
# UI
# ============================================================
st.title("🧠 SAAT BAZLI CANLI KARAKTER / OTOMATİK FAZ — TAM SÜRÜM")
st.caption(
    "Saat ana eksendir. Tüm geçmiş yalnız destek olur. "
    "Aktif faz sıcak çekirdeği + taşıma + 1–4 el dönüş + blok/ardışık + benzer saat karakteri tek kuponda birleşir."
)

settings,settings_err=github_settings()
m1,m2,m3,m4=st.columns(4)
m1.metric("Ana havuz",len(df))
m2.metric("Son çekiliş",int(df.iloc[-1].Cekilis_No) if len(df) else "—")
m3.metric("GitHub kayıt","AKTİF" if not settings_err else "KAPALI")
m4.metric("Son saat",f"{df.iloc[-1].Tarih} {df.iloc[-1].Saat}" if len(df) else "—")

if settings_err:
    st.warning("Kalıcı GitHub kayıt kapalı. Test ve canlı havuz çalışır; kalıcı kayıt için Streamlit Secrets gerekir.")

tab_live,tab_test,tab_add,tab_result=st.tabs([
    "🎯 TEK KUPON",
    "🧪 PARÇALI KÖR TEST",
    "➕ TEKLİ / ÇOKLU EKLE",
    "✅ SONUÇ KONTROLÜ → HAVUZA KAYDET",
])

with tab_live:
    if len(df)<100:
        st.error("Motor için en az 100 çekiliş gerekir.")
    else:
        next_no,next_date,next_time=next_defaults(df)
        coupon,scoretab,meta=live_hour_character_score(df,next_time)
        ps=meta["phase_start"]

        st.subheader(f"Hedef: #{next_no} — {next_date} {next_time}")
        a,b,c,d=st.columns(4)
        a.metric("Aktif faz",meta["state"])
        b.metric("Faz yaşı",f"{meta['phase_age']} el")
        c.metric("Aynı saat örnek",meta["hour_samples"])
        d.metric("Kupon boyu",len(coupon))

        st.write(f"**Faz başlangıcı:** #{int(df.iloc[ps].Cekilis_No)} — {df.iloc[ps].Tarih} {df.iloc[ps].Saat}")
        st.success("TEK KUPON: "+" - ".join(map(str,coupon)))
        st.dataframe(scoretab.head(20),use_container_width=True,hide_index=True)

        if st.button("💾 BU KUPONU SONUÇ KONTROLÜ İÇİN AÇ",type="primary",use_container_width=True):
            st.session_state.open_coupon=coupon
            st.session_state.open_draw_no=next_no
            st.session_state.open_date=next_date
            st.session_state.open_time=next_time
            st.success(f"#{next_no} kuponu sonuç kontrolüne kaydedildi.")

with tab_test:
    total=st.selectbox("Toplam test",[10,25,50,100],index=1)
    st.caption("Her basışta yalnız sonraki 10 çekiliş hesaplanır.")

    if "bt_total" not in st.session_state: st.session_state.bt_total=None
    if "bt_done" not in st.session_state: st.session_state.bt_done=0
    if "bt_result" not in st.session_state: st.session_state.bt_result=pd.DataFrame()

    if st.button("🔄 TESTİ BAŞLAT / SIFIRLA",use_container_width=True):
        st.session_state.bt_total=int(total)
        st.session_state.bt_done=0
        st.session_state.bt_result=pd.DataFrame()
        st.rerun()

    if st.session_state.bt_total:
        start0=max(100,len(df)-st.session_state.bt_total)
        done=st.session_state.bt_done
        remain=st.session_state.bt_total-done
        st.progress(min(done/max(st.session_state.bt_total,1),1.0))
        st.write(f"İlerleme: **{done}/{st.session_state.bt_total}**")

        if remain>0 and st.button("▶️ SONRAKİ 10 TESTİ ÇALIŞTIR",type="primary",use_container_width=True):
            chunk=min(10,remain)
            part=blind_test_chunk(df,start0+done,start0+done+chunk)
            st.session_state.bt_result=part if st.session_state.bt_result.empty else pd.concat([st.session_state.bt_result,part],ignore_index=True)
            st.session_state.bt_done+=chunk
            st.rerun()

        res=st.session_state.bt_result
        if isinstance(res,pd.DataFrame) and not res.empty:
            pred=int(res["Kupon boyu"].sum())
            hit=int(res["İsabet"].sum())
            x1,x2,x3,x4=st.columns(4)
            x1.metric("Tamamlanan",len(res))
            x2.metric("Ort. isabet",f"{res['İsabet'].mean():.2f}")
            x3.metric("Baz ortalama",f"{res['Baz İsabet'].mean():.2f}" if "Baz İsabet" in res.columns else "—")
            x4.metric("Net avantaj",f"{res['Avantaj'].mean():+.2f}" if "Avantaj" in res.columns else "—")
            st.caption(f"Seçilen toplam sayı: {pred} | Toplam tutan: {hit} | Sayı doğruluğu: %{100*hit/max(pred,1):.2f}")
            st.dataframe(res,use_container_width=True,hide_index=True)
            st.download_button(
                "⬇️ TEST CSV İNDİR",
                res.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"SAAT_BAZLI_KOR_TEST_{len(res)}.csv",
                mime="text/csv",
                use_container_width=True,
            )

with tab_add:
    st.subheader("Tek çekiliş ekle")
    nno,ndate,ntime=next_defaults(df)
    c1,c2,c3=st.columns(3)
    draw_no=c1.number_input("Çekiliş no",min_value=1,value=int(nno),step=1)
    draw_date=c2.text_input("Tarih",value=ndate)
    draw_time=c3.text_input("Saat",value=ntime)
    nums_text=st.text_area("20 sayı",placeholder="1 5 7 12 ...")

    if st.button("➕ TEK ÇEKİLİŞİ HAVUZA EKLE",use_container_width=True):
        nums=exact_twenty(nums_text)
        if nums is None:
            st.error("Tam 20 benzersiz sayı gir.")
        else:
            row=pd.DataFrame([[int(draw_no),draw_date,draw_time]+nums],columns=COLS)
            st.session_state.pool_df=merge_data(df,row)
            st.success(f"#{int(draw_no)} canlı havuza eklendi.")
            st.rerun()

    st.divider()
    st.subheader("Çoklu çekiliş ekle")
    multi_text=st.text_area(
        "Birden fazla çekilişi yapıştır",
        height=260,
        placeholder=(
            "47776;09.08.2026;08:52;1,2,...,20\n"
            "47777;09.08.2026;08:57;...\n\n"
            "veya Çekiliş no: bloklarını art arda yapıştır."
        ),
    )

    if st.button("📚 ÇOKLU VERİYİ OKU VE HAVUZA EKLE",use_container_width=True):
        add_df=dataframe_from_text(multi_text)
        if add_df.empty:
            st.error("Okunabilir çekiliş bulunamadı.")
        else:
            merged=merge_data(df,add_df)
            added=len(merged)-len(df)
            st.session_state.pool_df=merged
            st.success(f"{len(add_df)} satır okundu; havuz net +{added} çekiliş büyüdü.")
            st.rerun()

    st.divider()
    if len(df):
        st.download_button(
            "⬇️ GÜNCEL HAVUZU veri.txt OLARAK İNDİR",
            to_text(df).encode("utf-8"),
            file_name="veri.txt",
            mime="text/plain",
            use_container_width=True,
        )

    if st.button("☁️ GÜNCEL HAVUZU GITHUB veri.txt'YE KALICI KAYDET",type="primary",use_container_width=True):
        try:
            save_github_df(df,f"Hızlı On havuz güncellendi #{int(df.iloc[-1].Cekilis_No)}")
            st.success("GitHub veri.txt kalıcı olarak güncellendi.")
        except Exception as exc:
            st.error(str(exc))

with tab_result:
    open_coupon=st.session_state.get("open_coupon",[])
    open_no=st.session_state.get("open_draw_no")
    open_date=st.session_state.get("open_date","")
    open_time=st.session_state.get("open_time","")

    if open_coupon and open_no:
        st.info(f"Açık tahmin #{open_no} — {open_date} {open_time}\n\nKupon: {' - '.join(map(str,open_coupon))}")
    else:
        st.warning("Önce TEK KUPON sekmesinden kuponu sonuç kontrolü için aç.")

    result_no=st.number_input("Sonuç çekiliş no",min_value=1,value=int(open_no or next_defaults(df)[0]),step=1)
    r1,r2=st.columns(2)
    result_date=r1.text_input("Sonuç tarihi",value=open_date or next_defaults(df)[1])
    result_time=r2.text_input("Sonuç saati",value=open_time or next_defaults(df)[2])
    result_text=st.text_area("Gerçek 20 sayı",height=220)

    if st.button("🔍 SONUCU KONTROL ET",type="primary",use_container_width=True):
        nums=exact_twenty(result_text)
        if nums is None:
            st.error("Sonuçta tam 20 benzersiz sayı olmalı.")
        else:
            hits=sorted(set(open_coupon)&set(nums)) if open_coupon else []
            st.session_state.checked_draw={
                "no":int(result_no),"date":result_date,"time":result_time,"nums":nums,"hits":hits
            }
            if open_coupon:
                st.success(f"İsabet: {len(hits)}/{len(open_coupon)} — "+("Tutan: "+" - ".join(map(str,hits)) if hits else "Tutan sayı yok"))
            else:
                st.success("Sonuç geçerli: 20/20 benzersiz sayı.")

    checked=st.session_state.get("checked_draw")
    if checked:
        st.write(f"Kontrol edilen çekiliş: **#{checked['no']} — {checked['date']} {checked['time']}**")

        if st.button("✅ KONTROL EDİLEN ÇEKİLİŞİ CANLI HAVUZA EKLE",use_container_width=True):
            row=pd.DataFrame([[checked["no"],checked["date"],checked["time"]]+checked["nums"]],columns=COLS)
            st.session_state.pool_df=merge_data(df,row)
            st.success("Canlı havuza eklendi.")
            st.rerun()

        if st.button("☁️ KONTROL EDİLEN ÇEKİLİŞİ ANA HAVUZA KALICI KAYDET",type="primary",use_container_width=True):
            try:
                row=pd.DataFrame([[checked["no"],checked["date"],checked["time"]]+checked["nums"]],columns=COLS)
                merged=merge_data(df,row)
                save_github_df(merged,f"Sonuç kaydı #{checked['no']} {checked['date']} {checked['time']}")
                st.session_state.pool_df=merged
                st.success("Çekiliş GitHub veri.txt ana havuzuna kalıcı kaydedildi.")
                st.session_state.pop("checked_draw",None)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
