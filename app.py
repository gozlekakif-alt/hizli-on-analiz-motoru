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
    page_title="Sayı Laboratuvarı V7 — Taşıma/Dönüş Uzman Motoru",
    page_icon="🧬",
    layout="wide",
)

SLOTS = [
    "23:02","23:07","23:12","23:17","23:22","23:27",
    "23:32","23:37","23:42","23:47","23:52","23:57"
]
BASE = 20/80
DATA_FILE = Path("veri.txt")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"


# ============================================================
# TEMEL YARDIMCILAR
# ============================================================

def to_date(s):
    return datetime.strptime(str(s), "%d.%m.%Y").date()

def fmt(d):
    return d.strftime("%d.%m.%Y")

def next_target(date_s, time_s):
    i = SLOTS.index(time_s)
    if i < len(SLOTS)-1:
        return date_s, SLOTS[i+1]
    return fmt(to_date(date_s)+timedelta(days=1)), "23:02"

def shrink(h, n, prior=BASE, strength=18.0):
    if n <= 0:
        return prior
    return (h + prior*strength)/(n+strength)

def wilson_lower(h, n, z=1.0):
    if n <= 0:
        return BASE
    p = h/n
    den = 1 + z*z/n
    return max(
        0.0,
        (p + z*z/(2*n) - z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / den
    )

def pct_rank(s):
    s = pd.Series(s, dtype=float)
    if s.nunique(dropna=False) <= 1:
        return pd.Series([0.5]*len(s), index=s.index)
    return s.rank(pct=True, method="average")

def path6(prev6, n):
    return "".join("1" if n in x else "0" for x in prev6)

def recent_count(prev6, n):
    return sum(n in x for x in prev6)

def streak(prev6, n):
    c = 0
    for x in reversed(prev6):
        if n in x:
            c += 1
        else:
            break
    return c

def gap(prev6, n):
    if n in prev6[-1]:
        return 0
    c = 0
    for x in reversed(prev6):
        if n in x:
            break
        c += 1
    return min(c, 6)


# ============================================================
# VERİ / GITHUB
# ============================================================

def github_config():
    token = ""
    repo = DEFAULT_REPO
    branch = DEFAULT_BRANCH
    path = DEFAULT_PATH
    try:
        token = str(st.secrets.get("GITHUB_TOKEN","")).strip()
        repo = str(st.secrets.get("GITHUB_REPO",repo)).strip() or repo
        branch = str(st.secrets.get("GITHUB_BRANCH",branch)).strip() or branch
        path = str(st.secrets.get("GITHUB_DATA_PATH",path)).strip() or path
    except Exception:
        pass
    return token, repo, branch, path

def github_read(token, repo, branch, path):
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization":f"Bearer {token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"sayi-lab-v34",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        obj = json.loads(r.read().decode("utf-8"))
    return base64.b64decode(obj["content"]).decode("utf-8"), obj["sha"]

def github_write(token, repo, branch, path, text, msg):
    _, sha = github_read(token, repo, branch, path)
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    body = json.dumps({
        "message":msg,
        "content":base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha":sha,
        "branch":branch,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="PUT",
        headers={
            "Authorization":f"Bearer {token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "Content-Type":"application/json",
            "User-Agent":"sayi-lab-v34",
        }
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def repo_text():
    token, repo, branch, path = github_config()
    if token:
        try:
            text, _ = github_read(token, repo, branch, path)
            return text
        except Exception:
            pass
    if DATA_FILE.exists():
        return DATA_FILE.read_text(encoding="utf-8")
    return ""


def persist_result_to_repo(r):
    """
    Tek sonucu GitHub veri.txt'ye idempotent biçimde yazar.
    Aynı tarih/saat tekrar girilirse yeni satır çoğaltmak yerine mevcut satırı değiştirir.
    Başarılı dönüşte güncellenmiş veri metnini ve DataFrame'i verir.
    """
    token, repo, branch, path = github_config()
    if not token:
        raise RuntimeError(
            "Kalıcı kayıt yapılamadı: GITHUB_TOKEN tanımlı değil. "
            "Analiz üretilmedi; önce Streamlit Secrets içindeki GITHUB_TOKEN'ı kontrol edin."
        )

    current_text, _ = github_read(token, repo, branch, path)
    line = line_for(r)
    updated = append_or_replace(current_text, line)

    # Aynı kayıt zaten birebir varsa gereksiz commit yapma.
    changed = updated != current_text
    if changed:
        github_write(
            token, repo, branch, path, updated,
            f"V7 auto add {r['draw_no']} {r['date']} {r['time']}"
        )

    fresh_df = parse_pipe(updated)
    if fresh_df.empty:
        raise RuntimeError("Kalıcı veri.txt yazıldı ancak yeniden okunamadı.")

    # Yazılan çekilişin gerçekten havuzda olduğunu doğrula.
    check = fresh_df[
        (fresh_df["date"].astype(str) == str(r["date"])) &
        (fresh_df["time"].astype(str) == str(r["time"]))
    ]
    if check.empty:
        raise RuntimeError("Kalıcı kayıt doğrulaması başarısız: çekiliş veri.txt içinde bulunamadı.")

    row = check.iloc[-1]
    if int(row["draw_no"]) != int(r["draw_no"]) or set(row["numbers"]) != set(r["numbers"]):
        raise RuntimeError("Kalıcı kayıt doğrulaması başarısız: veri.txt içindeki satır sonuçla uyuşmuyor.")

    return updated, fresh_df, changed

def parse_pipe(text):
    rows = []
    for raw in str(text).splitlines():
        p = [x.strip() for x in raw.split("|")]
        if len(p) < 3:
            continue
        try:
            no = int(p[0])
            d,t = p[1].split()
            nums = sorted(set(map(int,p[2].split())))
        except Exception:
            continue
        if t not in SLOTS or len(nums)!=20 or any(n<1 or n>80 for n in nums):
            continue
        rows.append({"draw_no":no,"date":d,"time":t,"numbers":nums})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["_dt"] = pd.to_datetime(df["date"]+" "+df["time"], format="%d.%m.%Y %H:%M")
    df = (
        df.sort_values(["_dt","draw_no"])
        .drop_duplicates(["date","time"], keep="last")
        .drop(columns="_dt")
        .reset_index(drop=True)
    )
    return df

def parse_block(text):
    # Telefon / web sayfasından kopyalanan metinlerde NBSP, farklı tireler,
    # Markdown başlıkları ve Türkçe karakter varyasyonları gelebilir.
    raw = str(text or "").strip()
    raw = raw.replace("\u00a0", " ").replace("\u202f", " ")
    raw = raw.replace("–", "-").replace("—", "-").replace("−", "-")

    m_dt = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}:\d{2})", raw)

    # Çekiliş no / Cekilis no / Çekiliş No : / ##### Çekiliş no vb.
    m_no = re.search(r"(?:çekiliş|cekilis)\s*(?:no|numarası|numarasi)?\s*[:#-]?\s*(\d{4,})", raw, re.IGNORECASE)

    # Son çare: tarih satırından ÖNCE bulunan son 4+ basamaklı sayı çekiliş no'dur.
    if not m_no and m_dt:
        before = raw[:m_dt.start()]
        candidates = re.findall(r"(?<!\d)(\d{4,})(?!\d)", before)
        if candidates:
            class _DrawMatch:
                def group(self, _): return candidates[-1]
            m_no = _DrawMatch()

    if not m_no:
        raise ValueError("Çekiliş no bulunamadı. İlk satırı örn. 'Çekiliş no: 48606' olarak yapıştırın.")
    if not m_dt:
        raise ValueError("Tarih/saat bulunamadı. Örn. '12.08.2026 - 23:47'.")
    no = int(m_no.group(1))
    d = datetime.strptime(m_dt.group(1),"%d.%m.%Y").strftime("%d.%m.%Y")
    t = m_dt.group(2)
    if t not in SLOTS:
        raise ValueError("Geçersiz çekiliş saati.")
    tail = raw[m_dt.end():]
    nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", tail)]
    if len(nums)!=20 or len(set(nums))!=20:
        raise ValueError(f"20 farklı sayı bekleniyor; {len(nums)} bulundu.")
    return {"draw_no":no,"date":d,"time":t,"numbers":sorted(nums)}

def line_for(r):
    return f"{r['draw_no']} | {r['date']} {r['time']} | {' '.join(map(str,r['numbers']))}"

def append_or_replace(text, line):
    key = [x.strip() for x in line.split("|")][1]
    out = []
    done = False
    for raw in text.splitlines():
        if not raw.strip():
            continue
        p = [x.strip() for x in raw.split("|")]
        if len(p)>=2 and p[1]==key:
            if not done:
                out.append(line)
                done=True
            continue
        out.append(raw.rstrip())
    if not done:
        out.append(line)
    return "\n".join(out).rstrip()+"\n"

def merge_session(base):
    extra = st.session_state.get("v33_rows",[])
    if not extra:
        return base.copy()
    x = pd.concat([base.copy(),pd.DataFrame(extra)],ignore_index=True)
    x["_dt"] = pd.to_datetime(x["date"]+" "+x["time"],format="%d.%m.%Y %H:%M")
    x["_ord"] = np.arange(len(x))
    x = (
        x.sort_values(["_dt","_ord"])
        .drop_duplicates(["date","time"],keep="last")
        .drop(columns=["_dt","_ord"])
        .reset_index(drop=True)
    )
    return x


# ============================================================
# TARİHSEL OLAYLAR
# ============================================================

def target_indices(df, slot):
    out=[]
    for i in range(6,len(df)):
        if str(df.iloc[i]["time"]) != slot:
            continue
        if slot!="23:02" and str(df.iloc[i]["date"]) != str(df.iloc[i-1]["date"]):
            continue
        out.append(i)
    return out

def note_character(df):
    sets=[set(x) for x in df["numbers"]]
    rows=[]
    for i in range(1,len(df)):
        slot=str(df.iloc[i]["time"])
        if slot!="23:02" and str(df.iloc[i]["date"]) != str(df.iloc[i-1]["date"]):
            continue
        y=sets[i]; src=sets[i-1]
        arr=sorted(y)
        adj2=sum(1 for a,b in zip(arr,arr[1:]) if b==a+1)
        adj3=sum(1 for a,b,c in zip(arr,arr[1:],arr[2:]) if b==a+1 and c==b+1)
        rows.append({"Nota":slot,"Taşıma":len(src&y),"Ard2":adj2,"Ard3":adj3})
    raw=pd.DataFrame(rows)
    out=[]
    for slot in SLOTS:
        x=raw[raw["Nota"]==slot]
        if x.empty: continue
        out.append({
            "Nota":slot,
            "Örnek":len(x),
            "Ort Taşıma":round(x["Taşıma"].mean(),2),
            "Medyan":round(x["Taşıma"].median(),1),
            "Min":int(x["Taşıma"].min()),
            "Max":int(x["Taşıma"].max()),
            "Ort Ard2":round(x["Ard2"].mean(),2),
            "Ard3 Var %":round(100*(x["Ard3"]>0).mean(),1),
        })
    return pd.DataFrame(out)


# ============================================================
# V4 — VERİDEN REJİM KEŞFİ / TAŞIMA İZİ / DİNLENİP DÖNÜŞ
# ============================================================

REGIMES = ["DÜŞÜK", "NORMAL", "YÜKSEK"]

def regime_of(carry_count):
    if carry_count <= 3:
        return "DÜŞÜK"
    if carry_count <= 6:
        return "NORMAL"
    return "YÜKSEK"


def _adj2_count(s):
    a = sorted(s)
    return sum(1 for x, y in zip(a, a[1:]) if y == x + 1)


def _adj3_count(s):
    a = sorted(s)
    return sum(1 for x, y, z in zip(a, a[1:], a[2:]) if y == x + 1 and z == y + 1)


def _same_note_prior_sets(sets, inds, i, k=6):
    return [sets[j] for j in inds if j < i][-k:]


def _same_note_prior_carry(sets, inds, i, k=6):
    vals = []
    for j in inds:
        if j >= i:
            break
        vals.append(len(sets[j-1] & sets[j]))
    return vals[-k:]


def _transition_context(sets, inds, i):
    """Hedef i'nin sonucu görülmeden, yalnız i öncesinden rejim bağlamı."""
    src = sets[i-1]
    prev6 = sets[max(0, i-6):i]
    prev_carries = []
    for j in range(max(1, i-3), i):
        prev_carries.append(len(sets[j-1] & sets[j]))
    prev_carries = ([5.0] * (3-len(prev_carries))) + [float(x) for x in prev_carries]

    same_c = _same_note_prior_carry(sets, inds, i, 6)
    same_mean = float(np.mean(same_c)) if same_c else 5.0
    same_std = float(np.std(same_c)) if len(same_c) >= 2 else 1.5

    source_recent = [recent_count(prev6, n) for n in src]
    absent = [n for n in range(1,81) if n not in src]
    absent_gap = [gap(prev6, n) for n in absent]

    return np.array([
        prev_carries[-1] / 10.0,
        prev_carries[-2] / 10.0,
        prev_carries[-3] / 10.0,
        same_mean / 10.0,
        min(same_std, 4.0) / 4.0,
        _adj2_count(src) / 10.0,
        _adj3_count(src) / 5.0,
        sum(n % 2 for n in src) / 20.0,
        sum(n <= 40 for n in src) / 20.0,
        np.mean(source_recent) / 6.0 if source_recent else 0.5,
        sum(x >= 2 for x in source_recent) / 20.0 if source_recent else 0.0,
        sum(g in (1,2) for g in absent_gap) / 60.0 if absent_gap else 0.0,
        sum(g in (3,4) for g in absent_gap) / 60.0 if absent_gap else 0.0,
        sum(g >= 5 for g in absent_gap) / 60.0 if absent_gap else 0.0,
    ], dtype=float)


def _current_context(train, target_slot):
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)
    # "i" yeni hedefin indeksidir; sets[i] henüz yok.
    i = len(sets)
    src = sets[-1]
    prev6 = sets[-6:]
    prev_carries = []
    for j in range(max(1, i-3), i):
        prev_carries.append(len(sets[j-1] & sets[j]))
    prev_carries = ([5.0] * (3-len(prev_carries))) + [float(x) for x in prev_carries]

    same_c = []
    for j in inds[-6:]:
        same_c.append(len(sets[j-1] & sets[j]))
    same_mean = float(np.mean(same_c)) if same_c else 5.0
    same_std = float(np.std(same_c)) if len(same_c) >= 2 else 1.5

    source_recent = [recent_count(prev6, n) for n in src]
    absent = [n for n in range(1,81) if n not in src]
    absent_gap = [gap(prev6, n) for n in absent]

    return np.array([
        prev_carries[-1] / 10.0,
        prev_carries[-2] / 10.0,
        prev_carries[-3] / 10.0,
        same_mean / 10.0,
        min(same_std, 4.0) / 4.0,
        _adj2_count(src) / 10.0,
        _adj3_count(src) / 5.0,
        sum(n % 2 for n in src) / 20.0,
        sum(n <= 40 for n in src) / 20.0,
        np.mean(source_recent) / 6.0 if source_recent else 0.5,
        sum(x >= 2 for x in source_recent) / 20.0 if source_recent else 0.0,
        sum(g in (1,2) for g in absent_gap) / 60.0 if absent_gap else 0.0,
        sum(g in (3,4) for g in absent_gap) / 60.0 if absent_gap else 0.0,
        sum(g >= 5 for g in absent_gap) / 60.0 if absent_gap else 0.0,
    ], dtype=float)


def learn_regime_model(train, target_slot):
    """
    Üç rejim baştan 'strateji' diye dayatılmaz.
    Aynı hedef notasının geçmiş geçişlerinden:
      DÜŞÜK  = 0-3 taşıma
      NORMAL = 4-6 taşıma
      YÜKSEK = 7+ taşıma
    bağlamları öğrenilir.
    """
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)
    if len(inds) < 12:
        raise ValueError(f"{target_slot} notası için rejim öğrenmeye yeterli geçmiş yok.")

    hist = []
    for i in inds:
        cc = len(sets[i-1] & sets[i])
        hist.append({
            "i": i,
            "x": _transition_context(sets, inds, i),
            "carry": cc,
            "regime": regime_of(cc),
        })

    x_now = _current_context(train, target_slot)
    # Aynı nota içinde yakın komşu bağlamlar. 12-18 komşu küçük örnek aşırılığını azaltır.
    distances = []
    for h in hist:
        d = float(np.sqrt(np.mean((h["x"] - x_now) ** 2)))
        distances.append((d, h))
    distances.sort(key=lambda z: z[0])
    k = min(max(12, int(round(math.sqrt(len(distances))*2.2))), 18, len(distances))
    nearest = distances[:k]

    raw = Counter()
    carry_num = 0.0
    carry_den = 0.0
    for d, h in nearest:
        w = 1.0 / (0.055 + d)
        raw[h["regime"]] += w
        carry_num += w * h["carry"]
        carry_den += w

    # Aynı-nota genel dağılımını küçük prior olarak ekle.
    global_counts = Counter(h["regime"] for h in hist)
    total_global = max(1, sum(global_counts.values()))
    for r in REGIMES:
        raw[r] += 2.5 * global_counts[r] / total_global

    total = sum(raw.values()) or 1.0
    probs = {r: raw[r] / total for r in REGIMES}
    expected = carry_num / carry_den if carry_den else np.mean([h["carry"] for h in hist])
    recommended = max(REGIMES, key=lambda r: probs[r])

    # Tarihsel rejim özeti
    carry_by_regime = {}
    for r in REGIMES:
        vals = [h["carry"] for h in hist if h["regime"] == r]
        carry_by_regime[r] = float(np.mean(vals)) if vals else {"DÜŞÜK":2.5,"NORMAL":5.0,"YÜKSEK":7.5}[r]

    return {
        "probs": probs,
        "expected_carry": float(expected),
        "recommended": recommended,
        "neighbors": k,
        "examples": len(hist),
        "carry_by_regime": carry_by_regime,
        "hist": hist,
    }


def _bucket_same6(v):
    if v <= 1: return "0-1"
    if v <= 3: return "2-3"
    return "4-6"


def build_candidate_model(train, target_slot):
    """
    Skor = tek sıra değil; her rejim için ayrı koşullu kanallar öğrenilir.
    Koşullar: nota (fonksiyon zaten nota-özel), kaynakta var/yok,
    son-6 görünüm, path3/path4, streak/gap, aynı notanın son 6 günü,
    2'li taşıma paketi ve zayıf ardışık bağlam.
    """
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)
    if len(inds) < 12:
        raise ValueError(f"{target_slot} notası için yeterli geçmiş yok.")

    feat = defaultdict(lambda: [0,0])
    feat_global = defaultdict(lambda: [0,0])
    num = defaultdict(lambda: [0,0])
    pair_seen = Counter()
    pair_survive = Counter()
    adj = defaultdict(lambda: [0,0])

    for i in inds:
        y = sets[i]
        src = sets[i-1]
        prev6 = sets[i-6:i]
        same_prev = _same_note_prior_sets(sets, inds, i, 6)
        cc = len(src & y)
        rg = regime_of(cc)

        for n in range(1,81):
            present = n in src
            hit = int(n in y)
            c6 = recent_count(prev6, n)
            p6 = path6(prev6, n)
            s6 = sum(n in z for z in same_prev)
            sb = _bucket_same6(s6)

            basic = [
                ("side", present),
                ("count6", present, c6),
                ("path3", present, p6[-3:]),
                ("same6", present, sb),
            ]
            if present:
                basic += [
                    ("streak", streak(prev6,n)),
                    ("path4", True, p6[-4:]),
                ]
            else:
                g = gap(prev6,n)
                basic += [
                    ("gap", g),
                    ("gap_path3", g, p6[-3:]),
                    ("path4", False, p6[-4:]),
                ]

            for b in basic:
                feat[(rg,) + b][0] += hit
                feat[(rg,) + b][1] += 1
                feat_global[b][0] += hit
                feat_global[b][1] += 1

            nh = ((n-1) in src) + ((n+1) in src)
            trip = int(
                ((n-2) in src and (n-1) in src)
                or ((n-1) in src and (n+1) in src)
                or ((n+1) in src and (n+2) in src)
            )
            adj[(rg,present,int(nh),trip)][0] += hit
            adj[(rg,present,int(nh),trip)][1] += 1
            num[(rg,present,n)][0] += hit
            num[(rg,present,n)][1] += 1

        for a,b in combinations(sorted(src),2):
            pair_seen[(rg,a,b)] += 1
            if a in y and b in y:
                pair_survive[(rg,a,b)] += 1

    return {
        "feat": feat,
        "feat_global": feat_global,
        "num": num,
        "pair_seen": pair_seen,
        "pair_survive": pair_survive,
        "examples": len(inds),
    }


def _blend_feature_rate(model, regime, key, prior=BASE):
    hr,nr = model["feat"][(regime,) + key]
    hg,ng = model["feat_global"][key]
    # Rejim-hücresi küçükse global nota hücresine geri çekil.
    rr = shrink(hr,nr,prior,10)
    rg = shrink(hg,ng,prior,20)
    alpha = min(0.82, nr / (nr + 12.0))
    return alpha*rr + (1-alpha)*rg, nr


def score_v4_candidates(train, target_slot, regime_model, candidate_model):
    sets = [set(x) for x in train["numbers"]]
    src = sets[-1]
    prev6 = sets[-6:]
    inds = target_indices(train,target_slot)
    same_prev = [sets[j] for j in inds][-6:]

    rows = []
    for n in range(1,81):
        present = n in src
        c6 = recent_count(prev6,n)
        p6 = path6(prev6,n)
        s6 = sum(n in z for z in same_prev)
        sb = _bucket_same6(s6)
        g = gap(prev6,n)

        regime_scores = {}
        channel_by_regime = {}

        for rg in REGIMES:
            keys = [
                ("side",present),
                ("count6",present,c6),
                ("path3",present,p6[-3:]),
                ("same6",present,sb),
            ]
            if present:
                keys += [
                    ("streak",streak(prev6,n)),
                    ("path4",True,p6[-4:]),
                ]
            else:
                keys += [
                    ("gap",g),
                    ("gap_path3",g,p6[-3:]),
                    ("path4",False,p6[-4:]),
                ]

            vals = []
            supports = []
            for key in keys:
                r,sup = _blend_feature_rate(candidate_model,rg,key,BASE)
                vals.append(r); supports.append(sup)

            nh = int(((n-1) in src) + ((n+1) in src))
            tri = int(
                ((n-2) in src and (n-1) in src)
                or ((n-1) in src and (n+1) in src)
                or ((n+1) in src and (n+2) in src)
            )
            ah,an = candidate_model["adj"][(rg,present,nh,tri)] if "adj" in candidate_model else (0,0)
            # Eski dosyaya dönük güvenlik; aşağıda modelde adj var.
            adj_rate = shrink(ah,an,BASE,18) if an else BASE

            ih,it = candidate_model["num"][(rg,present,n)]
            id_rate = shrink(ih,it,BASE,45)

            # Paket yalnız kaynak sayı için ve ancak yeterli destekle.
            pair_rate = BASE*BASE
            pair_label = ""
            if present:
                prs = []
                for m in src:
                    if m == n: continue
                    a,b = sorted((n,m))
                    ps = candidate_model["pair_seen"][(rg,a,b)]
                    if ps >= 4:
                        ph = candidate_model["pair_survive"][(rg,a,b)]
                        pr = shrink(ph,ps,BASE*BASE,8)
                        prs.append((pr,m,ph,ps))
                if prs:
                    prs.sort(reverse=True)
                    top = prs[:3]
                    pair_rate = float(np.mean([x[0] for x in top]))
                    x = top[0]
                    pair_label = f"{n}-{x[1]} ({x[2]}/{x[3]})"

            # Kanal ortalaması; kimlik ve ardışıklık özellikle zayıf.
            core = float(np.mean(vals))
            package_lift = min(0.18, max(0.0, pair_rate - BASE*BASE) * 1.7)
            score = 0.86*core + 0.06*id_rate + 0.04*adj_rate + 0.04*(BASE + package_lift)
            regime_scores[rg] = score

            # "Karşı skor" için en güçlü bağımsız kanal; ortalamada gömülmesin.
            lifts = [max(0.0, v-BASE) for v in vals]
            strongest = sorted(lifts, reverse=True)[:3]
            counter = BASE + (0.45*strongest[0] + 0.30*strongest[1] + 0.15*strongest[2] if len(strongest)>=3 else sum(strongest))
            counter += 0.05*max(0.0, adj_rate-BASE)
            if present:
                counter += 0.05*max(0.0, pair_rate*3.0-BASE)
            channel_by_regime[rg] = {
                "counter": float(counter),
                "support": int(np.median(supports)) if supports else 0,
                "pair": float(pair_rate),
                "pair_label": pair_label,
            }

        weighted = sum(regime_model["probs"][rg] * regime_scores[rg] for rg in REGIMES)
        counter_weighted = sum(regime_model["probs"][rg] * channel_by_regime[rg]["counter"] for rg in REGIMES)
        confidence = 0.65*weighted + 0.35*counter_weighted

        rows.append({
            "Sayı": n,
            "Kaynakta": present,
            "Gap": g,
            "6 Yol": p6,
            "Son6 Görünüm": c6,
            "AynıNota6": s6,
            "DÜŞÜK": regime_scores["DÜŞÜK"],
            "NORMAL": regime_scores["NORMAL"],
            "YÜKSEK": regime_scores["YÜKSEK"],
            "DÜŞÜK Karşı": channel_by_regime["DÜŞÜK"]["counter"],
            "NORMAL Karşı": channel_by_regime["NORMAL"]["counter"],
            "YÜKSEK Karşı": channel_by_regime["YÜKSEK"]["counter"],
            "Beklenen Skor": weighted,
            "Karşı Skor": counter_weighted,
            "Kanıt": confidence,
            "Destek": int(round(sum(regime_model["probs"][rg]*channel_by_regime[rg]["support"] for rg in REGIMES))),
            "Paket": max(channel_by_regime[rg]["pair"] for rg in REGIMES),
            "En İyi Paket": next(
                (channel_by_regime[rg]["pair_label"] for rg in sorted(REGIMES,key=lambda x:regime_model["probs"][x],reverse=True)
                 if channel_by_regime[rg]["pair_label"]), ""
            ),
        })

    tab = pd.DataFrame(rows)

    # Her rejim ve birleşik skor için ayrı lig sıraları.
    for rg in REGIMES:
        tab[f"{rg} Lig Sıra"] = 0
    tab["Lig Sıra"] = 0
    for present in [True,False]:
        idx = tab.index[tab["Kaynakta"] == present]
        tab.loc[idx,"Lig Sıra"] = tab.loc[idx,"Kanıt"].rank(ascending=False,method="first").astype(int)
        for rg in REGIMES:
            tab.loc[idx,f"{rg} Lig Sıra"] = tab.loc[idx,rg].rank(ascending=False,method="first").astype(int)

    tab["Ham Sıra"] = tab["Beklenen Skor"].rank(ascending=False,method="first").astype(int)
    # Orta/düşük ham skor fakat bağımsız kanıtta yüksek.
    tab["Gizli Aday"] = (
        tab["Ham Sıra"].between(9,55)
        & (
            (tab["Karşı Skor"].rank(pct=True) >= .78)
            | (tab["Kanıt"].rank(pct=True) >= .78)
        )
    )
    return tab.sort_values(["Kanıt","Beklenen Skor"],ascending=False).reset_index(drop=True)


def build_v4_pools(tab, regime_model):
    """
    Önce geniş havuz, sonra dar boğaz.
    Havuz tek Top-N değildir: rejim skorları + karşı-skor + paket/kanıt kanallarından toplanır.
    """
    carry = tab[tab["Kaynakta"]].copy()
    ret = tab[~tab["Kaynakta"]].copy()
    rec = regime_model["recommended"]

    carry_pool = []
    def c_take(frame, limit):
        for n in frame["Sayı"].astype(int):
            if n not in carry_pool:
                carry_pool.append(n)
            if len(carry_pool) >= limit:
                break

    c_take(carry.sort_values([rec,"Kanıt"],ascending=False),5)
    c_take(carry.sort_values(["Karşı Skor","Kanıt"],ascending=False),8)
    c_take(carry.sort_values(["Paket","Kanıt"],ascending=False),10)
    c_take(carry.sort_values(["Kanıt","Beklenen Skor"],ascending=False),12)

    return_pool = []
    def r_take(frame, limit):
        for n in frame["Sayı"].astype(int):
            if n not in return_pool:
                return_pool.append(n)
            if len(return_pool) >= limit:
                break

    # Gap cepleri ayrı tutulur; tek gap bütün dönüş havuzunu ele geçirmez.
    r_take(ret[ret["Gap"].between(1,2)].sort_values([rec,"Karşı Skor"],ascending=False),6)
    r_take(ret[ret["Gap"].between(3,4)].sort_values([rec,"Karşı Skor"],ascending=False),12)
    r_take(ret[ret["Gap"]>=5].sort_values([rec,"Karşı Skor"],ascending=False),16)
    r_take(ret.sort_values(["Karşı Skor","Kanıt"],ascending=False),20)

    union = tab[tab["Sayı"].isin(set(carry_pool)|set(return_pool))].copy()
    # Dar boğaz 16: rejim-uyumlu kanıt + karşı-skor. Kaynak/dönüş dengesi rejim olasılığına göre.
    union["Dar Puan"] = (
        0.55*union[rec] +
        0.25*union["Karşı Skor"] +
        0.20*union["Kanıt"]
    )
    narrow = union.sort_values(["Dar Puan","Kanıt"],ascending=False).head(16)["Sayı"].astype(int).tolist()
    return carry_pool, return_pool, narrow


def _pick_unique(frame, selected, why, label, count):
    got = 0
    for _,r in frame.iterrows():
        n = int(r["Sayı"])
        if n in selected:
            continue
        selected.append(n)
        why[n] = label
        got += 1
        if got >= count:
            break
    return got


def regime_ticket(tab, regime, narrow_pool=None):
    """
    Üç kupon artık üç keyfi 'strateji' değil:
      DÜŞÜK  taşıma rejimi hipotezi
      NORMAL taşıma rejimi hipotezi
      YÜKSEK taşıma rejimi hipotezi
    """
    t = tab.copy()
    if narrow_pool:
        # Önce dar havuz, fakat gizli aday gerektiğinde dışarıdan kurtarma yapılabilir.
        main = t[t["Sayı"].isin(narrow_pool)].copy()
    else:
        main = t

    carry = main[main["Kaynakta"]].sort_values(
        [regime,"Kanıt","Karşı Skor"],ascending=False
    )
    ret = main[~main["Kaynakta"]].sort_values(
        [regime,"Karşı Skor","Kanıt"],ascending=False
    )

    if regime == "DÜŞÜK":
        carry_n, return_n = 2, 4
    elif regime == "NORMAL":
        carry_n, return_n = 3, 3
    else:
        carry_n, return_n = 4, 2

    selected, why = [], {}
    _pick_unique(carry,selected,why,f"{regime}/Taşıma",carry_n)
    _pick_unique(ret,selected,why,f"{regime}/Dönüş",return_n)

    # 7. koltuk: ham Top-8 dışında ama koşullu kanıdı güçlü orta/düşük aday.
    hidden = t[t["Gizli Aday"]].sort_values(
        [f"{regime} Karşı",regime,"Kanıt"],ascending=False
    )
    _pick_unique(hidden,selected,why,f"{regime}/Gizli-OrtaDüşük",1)

    fallback = main.sort_values([regime,"Karşı Skor","Kanıt"],ascending=False)
    _pick_unique(fallback,selected,why,f"{regime}/Tamamlama",7-len(selected))
    if len(selected)<7:
        fallback2=t.sort_values([regime,"Karşı Skor","Kanıt"],ascending=False)
        _pick_unique(fallback2,selected,why,f"{regime}/Tamamlama",7-len(selected))

    return selected[:7], why




# ============================================================
# V6 — SAYI YAŞAM DÖNGÜSÜ: DOĞUM → DEVAM → SÖNÜŞ → DÖNÜŞ
# ============================================================

def _life_run(bits):
    """Son durumun yaşı + ondan önceki karşı fazın uzunluğu."""
    b = [1 if x else 0 for x in bits]
    if not b:
        return 0, 0, 0
    cur = b[-1]
    age = 1
    k = len(b)-2
    while k >= 0 and b[k] == cur:
        age += 1
        k -= 1
    prev_age = 0
    while k >= 0 and b[k] != cur:
        prev_age += 1
        k -= 1
    return cur, age, prev_age


def _life_state(bits):
    """
    Salt 'kaç kere çıktı' demez; sayının bulunduğu FAZI tanımlar.
    Böylece yeni doğan sayı ile 3 eldir yanan sayı aynı puanı almaz.
    """
    cur, age, prev_age = _life_run(bits)
    last6 = [1 if x else 0 for x in bits[-6:]]
    last3 = sum(last6[-3:])
    prev3 = sum(last6[-6:-3]) if len(last6) >= 6 else 0
    delta = last3 - prev3
    if delta >= 2:
        momentum = "YÜKSELİYOR"
    elif delta <= -2:
        momentum = "SÖNÜYOR"
    else:
        momentum = "DENGELİ"

    if cur:
        if age == 1:
            state = "DOĞDU"
        elif age == 2:
            state = "DEVAM-2"
        elif age == 3:
            state = "DEVAM-3"
        else:
            state = "UZAMIŞ-ALEV"
    else:
        if age == 1:
            state = "YENİ-SÖNDÜ"
        elif age == 2:
            state = "DİNLENME-2"
        elif age <= 4:
            state = "DİNLENME-3/4"
        else:
            state = "UZUN-UYKU"

    return {
        "state": state,
        "present": bool(cur),
        "age": int(age),
        "prev_age": int(prev_age),
        "momentum": momentum,
        "last3": int(last3),
        "last6": int(sum(last6)),
    }


def _life_age_bucket(present, age):
    if present:
        if age <= 1: return "1"
        if age == 2: return "2"
        if age == 3: return "3"
        return "4+"
    if age <= 1: return "1"
    if age == 2: return "2"
    if age <= 4: return "3-4"
    return "5+"


def _same_note_life(sets, inds, i, n, k=6):
    prev = [j for j in inds if j < i][-k:]
    bits = [n in sets[j] for j in prev]
    if not bits:
        return 0, "YOK"
    cnt = sum(bits)
    if cnt <= 1: bucket = "0-1"
    elif cnt <= 3: bucket = "2-3"
    else: bucket = "4-6"
    # Aynı notada son iki görünüm ayrıca doğum/devam ayrımına yardımcı olur.
    tail = "".join("1" if x else "0" for x in bits[-3:])
    return cnt, f"{bucket}:{tail}"


def build_lifecycle_model(train, target_slot, max_events=140):
    """
    Hedef nota için tarihsel yaşam fazlarının GERÇEK bir sonraki çekilişte
    devam/sönüş/dönüş oranlarını öğrenir. Her olayda yalnız olay öncesi veri kullanılır.
    """
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)[-max_events:]

    state = defaultdict(lambda: [0,0])
    phase = defaultdict(lambda: [0,0])
    same = defaultdict(lambda: [0,0])
    identity = defaultdict(lambda: [0,0])

    for i in inds:
        if i < 12:
            continue
        y = sets[i]
        for n in range(1,81):
            bits = [n in sets[j] for j in range(max(0,i-12), i)]
            lf = _life_state(bits)
            ab = _life_age_bucket(lf["present"], lf["age"])
            _, sn = _same_note_life(sets, inds, i, n, 6)
            hit = int(n in y)

            keys = [
                ("state", lf["state"]),
                ("age", lf["present"], ab),
                ("momentum", lf["present"], lf["momentum"]),
                ("state_momentum", lf["state"], lf["momentum"]),
                ("prev_phase", lf["present"], min(lf["prev_age"], 5)),
            ]
            for key in keys:
                state[key][0] += hit
                state[key][1] += 1

            phase[(lf["state"], ab, lf["momentum"])][0] += hit
            phase[(lf["state"], ab, lf["momentum"])][1] += 1
            same[(lf["state"], sn)][0] += hit
            same[(lf["state"], sn)][1] += 1
            identity[(n, lf["state"])][0] += hit
            identity[(n, lf["state"])][1] += 1

    return {
        "state": state,
        "phase": phase,
        "same": same,
        "identity": identity,
        "examples": len(inds),
    }


def lifecycle_score_table(train, target_slot):
    """Güncel 80 sayının yaşam fazını ve tarihsel devam/dönüş olasılığını çıkarır."""
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)
    model = build_lifecycle_model(train, target_slot)
    rows = []

    for n in range(1,81):
        bits = [n in z for z in sets[-12:]]
        lf = _life_state(bits)
        ab = _life_age_bucket(lf["present"], lf["age"])
        same_cnt, sn = _same_note_life(sets, inds, len(sets), n, 6)

        # Dört ayrı tarihsel kanalı aşırı küçük örneğe karşı shrink ile birleştiriyoruz.
        h1,n1 = model["state"][("state", lf["state"])]
        h2,n2 = model["phase"][(lf["state"], ab, lf["momentum"])]
        h3,n3 = model["same"][(lf["state"], sn)]
        h4,n4 = model["identity"][(n, lf["state"])]

        r1 = shrink(h1,n1,BASE,18)
        r2 = shrink(h2,n2,r1,14)
        r3 = shrink(h3,n3,r1,18)
        r4 = shrink(h4,n4,r1,34)

        support = n1 + n2 + n3
        life_prob = 0.42*r1 + 0.28*r2 + 0.20*r3 + 0.10*r4

        # Faz yorumu: "yüksek puan" değil, neden canlı / neden sönüyor?
        if lf["present"]:
            if lf["state"] == "DOĞDU":
                phase_label = "DOĞUM sonrası devam"
            elif lf["state"] in ("DEVAM-2","DEVAM-3"):
                phase_label = "DEVAM penceresi"
            else:
                phase_label = "UZAMIŞ — sönme kontrolü"
            extinction = max(0.0, 1.0-life_prob)
        else:
            if lf["state"] == "YENİ-SÖNDÜ":
                phase_label = "YENİ SÖNÜŞ — erken dönüş"
            elif lf["state"] in ("DİNLENME-2","DİNLENME-3/4"):
                phase_label = "DÖNÜŞ penceresi"
            else:
                phase_label = "UZUN UYKU — seçici dönüş"
            extinction = 0.0

        rows.append({
            "Sayı": n,
            "Yaşam Durumu": lf["state"],
            "Faz": phase_label,
            "Yaş": lf["age"],
            "Önceki Faz": lf["prev_age"],
            "Momentum": lf["momentum"],
            "Son3": lf["last3"],
            "Son6": lf["last6"],
            "AynıNota6": same_cnt,
            "Yaşam Olasılığı": float(life_prob),
            "Sönme Riski": float(extinction),
            "Yaşam Destek": int(support),
        })

    out = pd.DataFrame(rows)
    out["YaşamRank"] = pct_rank(out["Yaşam Olasılığı"])
    out["SönmeRank"] = pct_rank(out["Sönme Riski"])
    return out.sort_values(["Yaşam Olasılığı","Yaşam Destek"], ascending=False).reset_index(drop=True)


def _final_feature_row(tab, regime_model, carry_pool, return_pool, narrow_pool):
    """Her sayıyı tek FINAL motoru için açıklanabilir özelliklere dönüştürür."""
    rec = regime_model["recommended"]
    probs = regime_model["probs"]
    cp, rp, npool = set(carry_pool), set(return_pool), set(narrow_pool)

    t = tab.copy()
    t["RejimUyum"] = sum(float(probs[rg]) * t[rg] for rg in REGIMES)
    t["RejimYayilim"] = t[REGIMES].max(axis=1) - t[REGIMES].min(axis=1)
    t["RejimUzlasi"] = 1.0 - pct_rank(t["RejimYayilim"])
    t["KanıtRank"] = pct_rank(t["Kanıt"])
    t["KarsiRank"] = pct_rank(t["Karşı Skor"])
    t["UyumRank"] = pct_rank(t["RejimUyum"])
    t["RecRank"] = pct_rank(t[rec])
    t["PaketRank"] = pct_rank(t["Paket"])
    t["LigRank"] = 1.0 - (t["Lig Sıra"].astype(float)-1.0) / 59.0
    t["HavuzOy"] = (
        t["Sayı"].isin(cp).astype(float)
        + t["Sayı"].isin(rp).astype(float)
        + t["Sayı"].isin(npool).astype(float)
    ) / 3.0
    t["DarOy"] = t["Sayı"].isin(npool).astype(float)
    t["TasimaOy"] = t["Sayı"].isin(cp).astype(float)
    t["DonusOy"] = t["Sayı"].isin(rp).astype(float)

    # Tek bir kanala körü körüne yaslanmak yerine bağımsız kanıtların uzlaşması.
    t["FinalHam"] = (
        0.22*t["KanıtRank"] +
        0.18*t["KarsiRank"] +
        0.18*t["UyumRank"] +
        0.10*t["RecRank"] +
        0.08*t["PaketRank"] +
        0.08*t["LigRank"] +
        0.10*t["HavuzOy"] +
        0.06*t["RejimUzlasi"]
    )
    return t


def _learn_final_reliability(train, target_slot, max_events=120):
    """
    Sızıntısız geçmiş olaylarda, FINAL özelliklerinin hangi dilimlerinin
    gerçekten isabet ürettiğini öğrenir. Sonuç görülmeden kurulmuş her
    tarihsel tahmin bir eğitim örneğidir.
    """
    inds = target_indices(train, target_slot)
    inds = inds[-max_events:]
    samples = []
    min_train = 180

    for i in inds:
        if i < min_train:
            continue
        hist = train.iloc[:i].reset_index(drop=True)
        try:
            rm = learn_regime_model(hist, target_slot)
            cm = build_candidate_model(hist, target_slot)
            tab = score_v4_candidates(hist, target_slot, rm, cm)
            cp, rp, narrow = build_v4_pools(tab, rm)
            ft = _final_feature_row(tab, rm, cp, rp, narrow)
        except Exception:
            continue

        actual = set(train.iloc[i]["numbers"])
        for _, r in ft.iterrows():
            samples.append({
                "hit": int(int(r["Sayı"]) in actual),
                "KanıtRank": float(r["KanıtRank"]),
                "KarsiRank": float(r["KarsiRank"]),
                "UyumRank": float(r["UyumRank"]),
                "RecRank": float(r["RecRank"]),
                "PaketRank": float(r["PaketRank"]),
                "LigRank": float(r["LigRank"]),
                "HavuzOy": float(r["HavuzOy"]),
                "DarOy": float(r["DarOy"]),
                "TasimaOy": float(r["TasimaOy"]),
                "DonusOy": float(r["DonusOy"]),
                "RejimUzlasi": float(r["RejimUzlasi"]),
            })

    if not samples:
        return None

    s = pd.DataFrame(samples)
    features = [
        "KanıtRank","KarsiRank","UyumRank","RecRank","PaketRank",
        "LigRank","HavuzOy","DarOy","TasimaOy","DonusOy","RejimUzlasi"
    ]
    weights = {}
    diagnostics = []

    for f in features:
        # Sürekli özelliklerde üst yarı / alt yarı ayrımı; havuz bayraklarında var/yok.
        if s[f].nunique() <= 3:
            hi = s[s[f] > 0]
            lo = s[s[f] == 0]
        else:
            hi = s[s[f] >= s[f].median()]
            lo = s[s[f] < s[f].median()]
        ph = shrink(int(hi["hit"].sum()), len(hi), BASE, 40) if len(hi) else BASE
        pl = shrink(int(lo["hit"].sum()), len(lo), BASE, 40) if len(lo) else BASE
        lift = ph - pl
        weights[f] = float(np.clip(lift / 0.12, -1.0, 1.0))
        diagnostics.append((f, len(hi), ph, pl, lift))

    return {"weights": weights, "diagnostics": diagnostics, "events": len(s)//80}



# ============================================================
# V7 — AYRI UZMANLAR: TAŞIMA / DÖNÜŞ + SİNYAL AYRIŞTIRMA
# ============================================================

def _bucket(v, cuts):
    for label, hi in cuts:
        if v <= hi:
            return label
    return cuts[-1][0]


def _carry_context_bucket(prev_sets):
    vals = []
    for a,b in zip(prev_sets[:-1], prev_sets[1:]):
        vals.append(len(a & b))
    m = float(np.mean(vals[-3:])) if vals else 5.0
    if m < 4.0: return "AZ"
    if m > 6.0: return "ÇOK"
    return "ORTA"


def _candidate_snapshot(sets, inds, i, n):
    """Hedef i görülmeden sayı n için taşımaya/dönüşe özel durum fotoğrafı."""
    src = sets[i-1]
    hist12 = sets[max(0,i-12):i]
    bits = [n in z for z in hist12]
    lf = _life_state(bits)
    p6 = path6(sets[max(0,i-6):i], n)
    same_prev = [sets[j] for j in inds if j < i][-6:]
    same6 = sum(n in z for z in same_prev)
    sb = _bucket_same6(same6)
    nh = int(((n-1) in src) + ((n+1) in src))
    band = (n-1)//10 + 1
    carry_ctx = _carry_context_bucket(sets[max(0,i-4):i])

    return {
        "present": n in src,
        "state": lf["state"],
        "age": lf["age"],
        "prev_age": min(lf["prev_age"], 6),
        "momentum": lf["momentum"],
        "path4": p6[-4:],
        "path3": p6[-3:],
        "same6": same6,
        "same_bucket": sb,
        "neighbor": nh,
        "band": band,
        "carry_ctx": carry_ctx,
        "recent6": sum(bits[-6:]),
    }


def _rate_from(counter, key, prior=BASE, strength=18):
    h,n = counter[key]
    return shrink(h,n,prior,strength), n


def build_transition_experts(train, target_slot, max_events=160):
    """
    TAŞIMA ve DÖNÜŞ ayrı öğrenilir.
    Aynı 'iki kere çıktı' durumu bile doğum yaşı, momentum, path, aynı nota,
    komşu yapısı ve son geçiş karakterine göre farklı hücrelere ayrılır.
    """
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)[-max_events:]

    carry = defaultdict(lambda:[0,0])
    ret = defaultdict(lambda:[0,0])
    carry_num = defaultdict(lambda:[0,0])
    return_num = defaultdict(lambda:[0,0])

    for i in inds:
        if i < 12:
            continue
        y = sets[i]
        src = sets[i-1]
        for n in range(1,81):
            s = _candidate_snapshot(sets, inds, i, n)
            hit = int(n in y)
            store = carry if s["present"] else ret

            if s["present"]:
                keys = [
                    ("state", s["state"]),
                    ("state_mom", s["state"], s["momentum"]),
                    ("age_mom", _life_age_bucket(True,s["age"]), s["momentum"]),
                    ("path4", s["path4"]),
                    ("same", s["same_bucket"]),
                    ("neighbor", s["neighbor"]),
                    ("ctx", s["carry_ctx"]),
                    ("state_ctx", s["state"], s["carry_ctx"]),
                    ("band_state", s["band"], s["state"]),
                ]
                carry_num[(n,s["state"])][0] += hit
                carry_num[(n,s["state"])][1] += 1
            else:
                rest_bucket = _life_age_bucket(False,s["age"])
                keys = [
                    ("state", s["state"]),
                    ("state_mom", s["state"], s["momentum"]),
                    ("rest", rest_bucket),
                    ("rest_path", rest_bucket, s["path3"]),
                    ("same", s["same_bucket"]),
                    ("neighbor", s["neighbor"]),
                    ("ctx", s["carry_ctx"]),
                    ("rest_ctx", rest_bucket, s["carry_ctx"]),
                    ("band_rest", s["band"], rest_bucket),
                ]
                return_num[(n,s["state"])][0] += hit
                return_num[(n,s["state"])][1] += 1

            for key in keys:
                store[key][0] += hit
                store[key][1] += 1

    return {
        "carry": carry,
        "return": ret,
        "carry_num": carry_num,
        "return_num": return_num,
        "examples": len(inds),
    }


def transition_expert_table(train, target_slot):
    """
    Her sayı için 'neden taşır / neden söner' veya 'neden döner / neden bekler'
    olasılığını ayrı hesaplar. Tekrar sayısı tek başına karar veremez.
    """
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)
    i = len(sets)
    model = build_transition_experts(train, target_slot)
    rows=[]

    for n in range(1,81):
        s = _candidate_snapshot(sets, inds, i, n)

        if s["present"]:
            keys = [
                ("state", s["state"]),
                ("state_mom", s["state"], s["momentum"]),
                ("age_mom", _life_age_bucket(True,s["age"]), s["momentum"]),
                ("path4", s["path4"]),
                ("same", s["same_bucket"]),
                ("neighbor", s["neighbor"]),
                ("ctx", s["carry_ctx"]),
                ("state_ctx", s["state"], s["carry_ctx"]),
                ("band_state", s["band"], s["state"]),
            ]
            store = model["carry"]
            vals=[]; supports=[]
            prior=BASE
            for j,key in enumerate(keys):
                r,sup=_rate_from(store,key,prior,18 + j*2)
                vals.append(r); supports.append(sup)
            ih,it=model["carry_num"][(n,s["state"])]
            ident=shrink(ih,it,float(np.mean(vals)),42)
            # Medyan + üst kanallar: tek uç sinyal ortalamayı ele geçirmesin.
            sv=sorted(vals, reverse=True)
            core=0.50*float(np.median(vals))+0.30*float(np.mean(sv[:3]))+0.20*ident
            decision="TAŞI"
            risk=max(0.0,1.0-core)
            why=f"{s['state']} | {s['momentum']} | ctx:{s['carry_ctx']}"
            score_type="Taşıma Olasılığı"
        else:
            rest_bucket=_life_age_bucket(False,s["age"])
            keys = [
                ("state", s["state"]),
                ("state_mom", s["state"], s["momentum"]),
                ("rest", rest_bucket),
                ("rest_path", rest_bucket, s["path3"]),
                ("same", s["same_bucket"]),
                ("neighbor", s["neighbor"]),
                ("ctx", s["carry_ctx"]),
                ("rest_ctx", rest_bucket, s["carry_ctx"]),
                ("band_rest", s["band"], rest_bucket),
            ]
            store=model["return"]
            vals=[]; supports=[]
            prior=BASE
            for j,key in enumerate(keys):
                r,sup=_rate_from(store,key,prior,18 + j*2)
                vals.append(r); supports.append(sup)
            ih,it=model["return_num"][(n,s["state"])]
            ident=shrink(ih,it,float(np.mean(vals)),48)
            sv=sorted(vals, reverse=True)
            core=0.50*float(np.median(vals))+0.30*float(np.mean(sv[:3]))+0.20*ident
            decision="DÖN"
            risk=0.0
            why=f"{s['state']} | dinlenme:{s['age']} | ctx:{s['carry_ctx']}"
            score_type="Dönüş Olasılığı"

        rows.append({
            "Sayı":n,
            "Kaynakta":s["present"],
            "Uzman Tür":decision,
            "Durum":s["state"],
            "Yaş":s["age"],
            "Momentum":s["momentum"],
            "AynıNota6":s["same6"],
            "Komşu":s["neighbor"],
            "Geçiş Karakteri":s["carry_ctx"],
            score_type:float(core),
            "Uzman Olasılığı":float(core),
            "Sönme Riski Uzman":float(risk),
            "Uzman Destek":int(np.median(supports)) if supports else 0,
            "Uzman Gerekçe":why,
        })

    out=pd.DataFrame(rows)
    out["UzmanRank"]=0.0
    for present in [True,False]:
        idx=out.index[out["Kaynakta"]==present]
        out.loc[idx,"UzmanRank"]=pct_rank(out.loc[idx,"Uzman Olasılığı"]).values
    return out


def _expert_final(train, target_slot, tab, regime_model, carry_pool, return_pool, narrow_pool, size=10):
    """
    V7 Final: önce TAŞIMA ve DÖNÜŞ uzmanları adayları ayrı doğrular,
    sonra yalnız bu iki uzmanın güçlü adayları finalde buluşturulur.
    """
    base=_final_feature_row(tab,regime_model,carry_pool,return_pool,narrow_pool)
    life=lifecycle_score_table(train,target_slot)
    exp=transition_expert_table(train,target_slot)

    t=base.merge(
        life[["Sayı","Yaşam Durumu","Faz","Yaş","Momentum","Yaşam Olasılığı","Sönme Riski","Yaşam Destek"]],
        on="Sayı",how="left"
    ).merge(
        exp[["Sayı","Uzman Tür","Uzman Olasılığı","UzmanRank","Sönme Riski Uzman",
             "Uzman Destek","Uzman Gerekçe","Geçiş Karakteri"]],
        on="Sayı",how="left"
    )

    t["YaşamRank"]=pct_rank(t["Yaşam Olasılığı"].fillna(BASE))
    t["UzmanDestekRank"]=pct_rank(t["Uzman Destek"].fillna(0))

    # Ana karar artık expert + yaşam. Eski skorlar teyit görevi görüyor.
    t["FinalPuanV7"] = (
        0.42*t["UzmanRank"] +
        0.18*t["YaşamRank"] +
        0.12*t["KanıtRank"] +
        0.09*t["KarsiRank"] +
        0.06*t["UyumRank"] +
        0.05*t["HavuzOy"] +
        0.04*t["RejimUzlasi"] +
        0.04*t["UzmanDestekRank"]
    )

    # Taşıma sayısını yalnız rejim ortalamasından değil, 20 kaynak sayının
    # uzman olasılık toplamından da tahmin et.
    carry_side=t[t["Kaynakta"]].copy()
    exp_carry=float(carry_side["Uzman Olasılığı"].sum())
    model_carry=float(regime_model["expected_carry"])
    predicted_carry=0.60*exp_carry+0.40*model_carry

    # 10'lu kupondaki carry koltuklarını, iki tarafın TOP aday olasılıklarının
    # marjinal değerine göre seç. Sabit 3/7 veya 5/5 dayatma yok.
    carry_ranked=t[t["Kaynakta"]].sort_values(
        ["Uzman Olasılığı","FinalPuanV7","Kanıt"],ascending=False
    )
    return_ranked=t[~t["Kaynakta"]].sort_values(
        ["Uzman Olasılığı","FinalPuanV7","Kanıt"],ascending=False
    )

    options=[]
    for cn in range(2,8):
        rn=size-cn
        c=carry_ranked.head(cn)
        r=return_ranked.head(rn)
        # Uzman olasılık toplamı + beklenen carry sayısına makul yakınlık.
        utility=float(c["Uzman Olasılığı"].sum()+r["Uzman Olasılığı"].sum())
        utility-=0.035*abs(cn - size*predicted_carry/20.0)
        options.append((utility,cn,rn))
    _,carry_n,return_n=max(options,key=lambda z:z[0])

    selected=pd.concat([carry_ranked.head(carry_n),return_ranked.head(return_n)])
    final=selected.sort_values(
        ["FinalPuanV7","Uzman Olasılığı","Kanıt"],ascending=False
    )["Sayı"].astype(int).tolist()

    reasons={}
    for n in final:
        r=t[t["Sayı"]==n].iloc[0]
        side="TAŞIMA" if bool(r["Kaynakta"]) else "DÖNÜŞ"
        reasons[n]=(
            f"{side}/{r['Yaşam Durumu']}/{r['Momentum']}"
            f"/Uzman:{r['Uzman Olasılığı']:.3f}"
        )

    meta={
        "predicted_carry":float(predicted_carry),
        "carry_seats":int(carry_n),
        "return_seats":int(return_n),
        "carry_expert_sum":float(exp_carry),
    }
    return final,reasons,t.sort_values(
        ["FinalPuanV7","Uzman Olasılığı"],ascending=False
    ),meta


def build_elimination_audit(pred, actual, source_numbers):
    """Doğru adayın hangi aşamada kaybolduğunu ve yanlış finalin neden girdiğini gösterir."""
    actual=set(actual)
    src=set(source_numbers)
    cp=set(pred["carry_pool"]); rp=set(pred["return_pool"])
    npool=set(pred["narrow_pool"]); final=set(pred["final"])
    ft=pred.get("final_table")
    rows=[]

    for n in sorted(actual):
        side="TAŞIMA" if n in src else "DÖNÜŞ"
        if n in final:
            stage="FINAL DOĞRU"
        elif n in npool:
            stage="DAR16'DA KALDI → FINAL ATTI"
        elif n in cp or n in rp:
            stage="GENİŞ HAVUZDA KALDI → DAR/FINAL ATTI"
        else:
            stage="ADAY MOTORU KAÇIRDI"
        row={"Sayı":n,"Gerçek Tip":side,"Kayıp Aşaması":stage}
        if ft is not None and n in set(ft["Sayı"]):
            x=ft[ft["Sayı"]==n].iloc[0]
            row["Uzman Olasılığı"]=round(float(x.get("Uzman Olasılığı",0)),3)
            row["Yaşam"]=str(x.get("Yaşam Durumu",""))
            row["Momentum"]=str(x.get("Momentum",""))
        rows.append(row)

    false=[]
    if ft is not None:
        for n in pred["final"]:
            if n in actual: continue
            x=ft[ft["Sayı"]==n].iloc[0]
            false.append({
                "Sayı":int(n),
                "Tip":"TAŞIMA" if bool(x["Kaynakta"]) else "DÖNÜŞ",
                "Uzman Olasılığı":round(float(x.get("Uzman Olasılığı",0)),3),
                "Yaşam":str(x.get("Yaşam Durumu","")),
                "Momentum":str(x.get("Momentum","")),
                "Neden Girdi":str(pred["reasons"].get(int(n),"")),
            })
    return pd.DataFrame(rows),pd.DataFrame(false)


def final_ticket_v5(train, target_slot, tab, regime_model, carry_pool, return_pool, narrow_pool, size=10):
    """Uyumluluk adı korunur; gerçek final V7 ayrı TAŞIMA/DÖNÜŞ uzmanlarıdır."""
    final,reasons,table,meta=_expert_final(
        train,target_slot,tab,regime_model,carry_pool,return_pool,narrow_pool,size
    )
    return final,reasons,table,meta

def prediction_bundle(train, target_date, target_slot):
    regime_model = learn_regime_model(train,target_slot)
    candidate_model = build_candidate_model(train,target_slot)

    # score fonksiyonunun zayıf ardışık bağlam sayaçlarına erişmesi için.
    # Python dict'e sonradan eklemek, kodu açık tutuyor.
    # build_candidate_model içindeki adj değişkeni burada yeniden üretilemez; modelin parçası olmalı.
    # Eski kayıtlarda yoksa score tarafı BASE'e düşer.
    if "adj" not in candidate_model:
        # build_candidate_model fonksiyonunun lokal adj'sini modele eklemek için emniyet:
        # Bu blok normalde çalışmaz; aşağıdaki reconstruct yalnız uyumluluk amaçlıdır.
        candidate_model["adj"] = defaultdict(lambda:[0,0])

    tab = score_v4_candidates(train,target_slot,regime_model,candidate_model)
    carry_pool, return_pool, narrow = build_v4_pools(tab,regime_model)

    tickets, reasons = {}, {}
    for rg in REGIMES:
        tickets[rg], reasons[rg] = regime_ticket(tab,rg,narrow)

    # V5: üç rejim kuponunu teşhis için koru; kullanıcıya tek FINAL üret.
    final10, final_reasons, final_table, final_rel = final_ticket_v5(
        train, target_slot, tab, regime_model, carry_pool, return_pool, narrow, size=10
    )

    rec = regime_model["recommended"]
    return {
        "regime": regime_model,
        "table": tab,
        "carry_pool": carry_pool,
        "return_pool": return_pool,
        "narrow_pool": narrow,
        "tickets": tickets,
        "ticket_reasons": reasons,
        "recommended": rec,
        "final": final10,
        "reasons": final_reasons,
        "final_table": final_table,
        "final_reliability": final_rel,
        "final_meta": final_rel,
        "target_date": target_date,
        "target_time": target_slot,
    }


# build_candidate_model'e adj sayaçlarını modele dahil eden küçük sarmalayıcı.
_build_candidate_model_original = build_candidate_model
def build_candidate_model(train, target_slot):
    sets = [set(x) for x in train["numbers"]]
    inds = target_indices(train, target_slot)
    if len(inds) < 12:
        raise ValueError(f"{target_slot} notası için yeterli geçmiş yok.")

    feat = defaultdict(lambda:[0,0])
    feat_global = defaultdict(lambda:[0,0])
    num = defaultdict(lambda:[0,0])
    pair_seen = Counter()
    pair_survive = Counter()
    adj = defaultdict(lambda:[0,0])

    for i in inds:
        y=sets[i]; src=sets[i-1]; prev6=sets[i-6:i]
        same_prev=_same_note_prior_sets(sets,inds,i,6)
        rg=regime_of(len(src&y))
        for n in range(1,81):
            present=n in src; hit=int(n in y); c6=recent_count(prev6,n)
            p6=path6(prev6,n); s6=sum(n in z for z in same_prev); sb=_bucket_same6(s6)
            basic=[("side",present),("count6",present,c6),("path3",present,p6[-3:]),("same6",present,sb)]
            if present:
                basic += [("streak",streak(prev6,n)),("path4",True,p6[-4:])]
            else:
                g=gap(prev6,n)
                basic += [("gap",g),("gap_path3",g,p6[-3:]),("path4",False,p6[-4:])]
            for b in basic:
                feat[(rg,)+b][0]+=hit; feat[(rg,)+b][1]+=1
                feat_global[b][0]+=hit; feat_global[b][1]+=1
            nh=int(((n-1) in src)+((n+1) in src))
            tri=int(((n-2) in src and (n-1) in src) or ((n-1) in src and (n+1) in src) or ((n+1) in src and (n+2) in src))
            adj[(rg,present,nh,tri)][0]+=hit; adj[(rg,present,nh,tri)][1]+=1
            num[(rg,present,n)][0]+=hit; num[(rg,present,n)][1]+=1

        for a,b in combinations(sorted(src),2):
            pair_seen[(rg,a,b)]+=1
            if a in y and b in y:
                pair_survive[(rg,a,b)]+=1

    return {
        "feat":feat,"feat_global":feat_global,"num":num,
        "pair_seen":pair_seen,"pair_survive":pair_survive,"adj":adj,
        "examples":len(inds),
    }



# ============================================================
# V8.1 — 23:17 HEDEF MOTORU
# Önceki gece çapraz karakter + 23:02 / 23:07 / 23:12 oyun tanıma
# ============================================================

SNIPER_INPUT = ["23:02","23:07","23:12"]
SNIPER_TARGET = "23:17"
PREV_NIGHT = ["23:42","23:47","23:52","23:57"]

def _day_map(df):
    out={}
    for _,r in df.iterrows():
        out.setdefault(str(r["date"]),{})[str(r["time"])]=set(r["numbers"])
    return out

def _date_order(df):
    return list(dict.fromkeys(df["date"].astype(str).tolist()))

def _adj_features(s):
    a=sorted(s)
    adj2=sum(1 for x,y in zip(a,a[1:]) if y==x+1)
    adj3=sum(1 for x,y,z in zip(a,a[1:],a[2:]) if y==x+1 and z==y+1)
    return adj2,adj3

def _band_counts(s):
    return [sum(10*k < n <= 10*(k+1) for n in s)/20.0 for k in range(8)]

def _sniper_day_context(day_sets, prev_sets):
    s02=day_sets["23:02"]; s07=day_sets["23:07"]; s12=day_sets["23:12"]
    p42,p47,p52,p57=[prev_sets[x] for x in PREV_NIGHT]
    a02=_adj_features(s02); a07=_adj_features(s07); a12=_adj_features(s12)
    # Oyun karakteri: ilk 3 elin birbirine taşıması, çapraz gece izi ve bant/ardışık yapı.
    vec=[
        len(s02&s07)/20.0,
        len(s07&s12)/20.0,
        len(s02&s12)/20.0,
        len(p57&s02)/20.0,
        len(p52&s02)/20.0,
        len(p47&s07)/20.0,
        len(p42&s12)/20.0,
        len((p52|p57)&s02)/20.0,
        len((p47|p52|p57)&(s07|s12))/40.0,
        a02[0]/10.0,a07[0]/10.0,a12[0]/10.0,
        a02[1]/5.0,a07[1]/5.0,a12[1]/5.0,
        sum(n%2 for n in s12)/20.0,
        sum(n<=40 for n in s12)/20.0,
    ]
    vec.extend(_band_counts(s12))
    return np.array(vec,dtype=float)

def _sniper_num_signature(n, day_sets, prev_sets):
    s02=day_sets["23:02"]; s07=day_sets["23:07"]; s12=day_sets["23:12"]
    p=[prev_sets[x] for x in PREV_NIGHT]
    cur=[int(n in s02),int(n in s07),int(n in s12)]
    prv=[int(n in z) for z in p]
    # doğum/devam/sönüş ayrı imza
    cur_path="".join(map(str,cur))
    prev_path="".join(map(str,prv))
    if cur==[0,0,1]: state="12-DE-DOĞDU"
    elif cur==[0,1,1]: state="07→12 DEVAM"
    elif cur==[1,1,1]: state="3-EL DEVAM"
    elif cur==[1,0,1]: state="GERİ-DÖNDÜ"
    elif cur==[1,1,0]: state="12-DE-SÖNDÜ"
    elif cur==[0,1,0]: state="07-TEK"
    elif cur==[1,0,0]: state="02-SONRA-UYKU"
    else: state="3-EL-YOK"
    return {
        "cur_path":cur_path,"prev_path":prev_path,"state":state,
        "in12":bool(cur[-1]),"cur_count":sum(cur),"prev_count":sum(prv),
        "night_tail":sum(prv[-2:]),
        "neighbor12":int(((n-1) in s12)+((n+1) in s12)),
        "band":(n-1)//10+1
    }

def _sniper_histories(df):
    dm=_day_map(df); dates=_date_order(df)
    events=[]
    for di in range(1,len(dates)):
        d=dates[di]; pd=dates[di-1]
        if not all(x in dm.get(d,{}) for x in SNIPER_INPUT+[SNIPER_TARGET]):
            continue
        if not all(x in dm.get(pd,{}) for x in PREV_NIGHT):
            continue
        day=dm[d]; prev=dm[pd]
        events.append({
            "date":d,"prev_date":pd,
            "context":_sniper_day_context(day,prev),
            "day":day,"prev":prev,
            "target":day[SNIPER_TARGET],
            "carry17":len(day["23:12"]&day[SNIPER_TARGET])
        })
    return events

def sniper_2317_prediction(df, topn=10):
    """
    Hedef 23:17. Program ancak aynı gün 23:02, 23:07, 23:12 mevcutsa çalışır.
    Önceki gecenin 23:42/47/52/57 bloğunu da çapraz karakter olarak kullanır.
    """
    dm=_day_map(df); dates=_date_order(df)
    if not dates:
        raise ValueError("Veri yok.")
    d=dates[-1]
    if not all(x in dm.get(d,{}) for x in SNIPER_INPUT):
        missing=[x for x in SNIPER_INPUT if x not in dm.get(d,{})]
        raise ValueError("23:17 hedefi için önce şu çekilişler gerekli: "+", ".join(missing))
    if SNIPER_TARGET in dm[d]:
        # 23:17 zaten girilmişse yeni hedef üretmek yerine laboratuvar kullanılabilir.
        raise ValueError("Bu günün 23:17 sonucu zaten veri havuzunda. Yeni günün ilk üç çekilişini girin.")
    if len(dates)<2:
        raise ValueError("Önceki gece yok.")
    pd=dates[-2]
    if not all(x in dm.get(pd,{}) for x in PREV_NIGHT):
        raise ValueError("Önceki gecenin 23:42/23:47/23:52/23:57 bloğu eksik.")

    day=dm[d]; prev=dm[pd]
    ctx=_sniper_day_context(day,prev)
    hist=_sniper_histories(df)
    if len(hist)<18:
        raise ValueError("23:17 motoru için en az 18 tam geçmiş gece gerekli.")

    # Benzer oyun günleri: ilk üç çekiliş + önceki gece çapraz karakteri.
    dist=[]
    for e in hist:
        ds=float(np.sqrt(np.mean((e["context"]-ctx)**2)))
        dist.append((ds,e))
    dist.sort(key=lambda x:x[0])
    k=min(max(14,int(round(math.sqrt(len(dist))*2.5))),26,len(dist))
    near=dist[:k]

    # O günkü gerçek 23:17 taşıma sayısını benzer günlerden öğren.
    num=sum((1/(0.04+d0))*e["carry17"] for d0,e in near)
    den=sum(1/(0.04+d0) for d0,e in near)
    expected_carry=num/den if den else 5.0

    rows=[]
    for n in range(1,81):
        sig=_sniper_num_signature(n,day,prev)
        hit_num=0.0; total=0.0
        exact_num=0.0; exact_den=0.0
        state_num=0.0; state_den=0.0

        for d0,e in near:
            w=1/(0.04+d0)
            hs=_sniper_num_signature(n,e["day"],e["prev"])
            hit=int(n in e["target"])
            total+=w; hit_num+=w*hit

            # Aynı 3-el yol + önceki gece izi en güçlü kanal.
            if hs["cur_path"]==sig["cur_path"] and hs["prev_path"]==sig["prev_path"]:
                exact_den+=w; exact_num+=w*hit
            if hs["state"]==sig["state"]:
                state_den+=w; state_num+=w*hit

        near_rate=(hit_num+0.25*10)/(total+10)
        exact_rate=(exact_num+near_rate*10)/(exact_den+10)
        state_rate=(state_num+near_rate*16)/(state_den+16)

        # Aynı sayı kimliği değil, olay karakteri ana ağırlık.
        score=0.40*near_rate+0.35*exact_rate+0.25*state_rate

        # 23:12 kaynakta olanlar ve olmayanlar ayrı ligde güvenilirlik.
        support=exact_den+state_den
        reliability=math.sqrt(support/(support+20.0)) if support>0 else 0.0
        evidence=(score-0.25)*reliability

        rows.append({
            "Sayı":n,"Kaynakta12":sig["in12"],"3-El Yol":sig["cur_path"],
            "Önceki Gece Yol":sig["prev_path"],"Durum":sig["state"],
            "İlk3 Görünüm":sig["cur_count"],"Gece Görünüm":sig["prev_count"],
            "Komşu12":sig["neighbor12"],"Skor":float(score),
            "Kanıt Gücü":float(evidence),"Destek":float(support)
        })

    tab=pd.DataFrame(rows)

    # 10'lu finalde taşıma koltuğu, 23:17 gerçek taşımasının yaklaşık yarısı.
    carry_n=int(np.clip(round(expected_carry/2.0),2,4))
    return_n=topn-carry_n

    carry=tab[tab["Kaynakta12"]].sort_values(
        ["Kanıt Gücü","Skor","Destek"],ascending=False
    )
    ret=tab[~tab["Kaynakta12"]].sort_values(
        ["Kanıt Gücü","Skor","Destek"],ascending=False
    )
    selected=pd.concat([carry.head(carry_n),ret.head(return_n)])
    final=selected.sort_values(["Kanıt Gücü","Skor"],ascending=False)["Sayı"].astype(int).tolist()

    # oyun karakteri etiketi
    c1=len(day["23:02"]&day["23:07"]); c2=len(day["23:07"]&day["23:12"])
    if c1>=7 and c2>=7: game="YAPIŞKAN / YÜKSEK TAŞIMA"
    elif c1<=3 and c2<=3: game="DAĞILAN / YÜKSEK DÖNÜŞ"
    else: game="KARMA / NORMAL"

    return {
        "target_date":d,"target_time":"23:17","previous_date":pd,
        "game_character":game,"carry02_07":c1,"carry07_12":c2,
        "expected_carry17":float(expected_carry),"carry_seats":carry_n,
        "return_seats":return_n,"neighbors":k,"final":final,
        "table":tab.sort_values(["Kanıt Gücü","Skor"],ascending=False)
    }

def sniper_walk_forward(df, ntest=60):
    """
    Gün bazında gerçek walk-forward: hedef günün 23:17 sonucu eğitimde yokken tahmin edilir.
    """
    dm=_day_map(df); dates=_date_order(df)
    candidates=[]
    for di in range(1,len(dates)):
        d=dates[di]; pd=dates[di-1]
        if all(x in dm.get(d,{}) for x in SNIPER_INPUT+[SNIPER_TARGET]) and \
           all(x in dm.get(pd,{}) for x in PREV_NIGHT):
            candidates.append(d)
    candidates=candidates[-int(ntest):]
    rows=[]
    for d in candidates:
        # Hedef günün 23:17 ve sonrasını kes; sadece ilk 3 el biliniyor.
        target_dt=pd.to_datetime(d+" 23:17",format="%d.%m.%Y %H:%M")
        tmp=df.copy()
        dts=pd.to_datetime(tmp["date"]+" "+tmp["time"],format="%d.%m.%Y %H:%M")
        train=tmp[dts<target_dt].reset_index(drop=True)
        try:
            pred=sniper_2317_prediction(train)
        except Exception:
            continue
        actual=dm[d]["23:17"]
        prev12=dm[d]["23:12"]
        final=set(pred["final"])
        rows.append({
            "Tarih":d,"Karakter":pred["game_character"],
            "Final10":len(final&actual),
            "Final Taşıma":len(final&actual&prev12),
            "Final Dönüş":len(final&actual-prev12),
            "Gerçek Taşıma":len(prev12&actual),
            "Beklenen Taşıma":round(pred["expected_carry17"],2),
            "Kupon":"-".join(map(str,pred["final"]))
        })
    return pd.DataFrame(rows)


# ============================================================
# WALK-FORWARD
# ============================================================

def walk_forward(df, ntest=72):
    start=max(180,len(df)-int(ntest))
    rows=[]
    for i in range(start,len(df)):
        train=df.iloc[:i].reset_index(drop=True)
        tgt=df.iloc[i]
        try:
            pred=prediction_bundle(train,str(tgt["date"]),str(tgt["time"]))
        except Exception:
            continue

        actual=set(tgt["numbers"])
        prev=set(train.iloc[-1]["numbers"])
        actual_carry=prev&actual
        actual_return=actual-prev
        actual_regime=regime_of(len(actual_carry))

        rec=pred["recommended"]
        rows.append({
            "Çekiliş":int(tgt["draw_no"]),
            "Tarih":str(tgt["date"]),
            "Saat":str(tgt["time"]),
            "Gerçek Rejim":actual_regime,
            "Önerilen Rejim":rec,
            "Rejim Doğru":int(rec==actual_regime),
            "Gerçek Taşıma":len(actual_carry),
            "Beklenen Taşıma":round(pred["regime"]["expected_carry"],2),
            "Taşıma Havuzu":len(set(pred["carry_pool"])&actual_carry),
            "Dönüş Havuzu":len(set(pred["return_pool"])&actual_return),
            "Dar16":len(set(pred["narrow_pool"])&actual),
            "DÜŞÜK İsabet":len(set(pred["tickets"]["DÜŞÜK"])&actual),
            "NORMAL İsabet":len(set(pred["tickets"]["NORMAL"])&actual),
            "YÜKSEK İsabet":len(set(pred["tickets"]["YÜKSEK"])&actual),
            "Önerilen İsabet":len(set(pred["final"])&actual),
            "FINAL10 İsabet":len(set(pred["final"])&actual),
            "FINAL Taşıma İsabet":len(set(pred["final"])&actual_carry),
            "FINAL Dönüş İsabet":len(set(pred["final"])&actual_return),
            "Final Taşıma Koltuğu":pred.get("final_meta",{}).get("carry_seats",0),
            "Final Dönüş Koltuğu":pred.get("final_meta",{}).get("return_seats",0),
            "Önerilen Kupon":"-".join(map(str,pred["final"])),
        })
    return pd.DataFrame(rows)

# ============================================================
# UYGULAMA
# ============================================================

st.title("🎯 Sayı Laboratuvarı V8.1 — 23:17 Hedef Motoru")
st.caption(
    "Önceki gecenin çapraz karakterini ve aynı gün 23:02 / 23:07 / 23:12 ilk üç elini okuyup "
    "asıl hedef 23:17 için tek FINAL-10 üretir. Taşıma ve dönüş ayrı liglerde seçilir."
)

with st.sidebar:
    st.header("Veri")
    upload=st.file_uploader("Geçici veri.txt",type=["txt"])
    st.caption("Kalıcı kullanımda repo veri.txt okunur.")

if upload:
    base_df=parse_pipe(upload.read().decode("utf-8"))
    source=f"Geçici: {upload.name}"
else:
    base_df=parse_pipe(repo_text())
    source="Repo veri.txt"

if base_df.empty:
    st.error("Veri bulunamadı.")
    st.stop()

# V4 kendi session anahtarını kullanır; eski sürüm kalıntıları karışmaz.
def merge_v4_session(base):
    extra=st.session_state.get("v4_rows",[])
    if not extra:
        return base.copy()
    x=pd.concat([base.copy(),pd.DataFrame(extra)],ignore_index=True)
    x["_dt"]=pd.to_datetime(x["date"]+" "+x["time"],format="%d.%m.%Y %H:%M")
    x["_ord"]=np.arange(len(x))
    x=(x.sort_values(["_dt","_ord"])
       .drop_duplicates(["date","time"],keep="last")
       .drop(columns=["_dt","_ord"])
       .reset_index(drop=True))
    return x

df=merge_v4_session(base_df)

st.caption(
    f"📂 {source} · {len(df)} çekiliş · {df['date'].nunique()} gün · "
    f"son: #{df.iloc[-1]['draw_no']} {df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

if not upload:
    token, _, _, _ = github_config()
    if token:
        st.caption("🔒 Otomatik kalıcı kayıt: AÇIK — her V7 işleminden önce GitHub veri.txt güncellenir.")
    else:
        st.error("🔴 Otomatik kalıcı kayıt KAPALI: GITHUB_TOKEN bulunamadı. Yeni analiz üretmeden önce bunu düzeltin.")

tabs=st.tabs([
    "🎯 23:17 Hedef",
    "⚡ Hızlı",
    "🌗 Rejim",
    "🫱 Taşıma İzleri",
    "😴 Dinlenip Dönüş",
    "🎯 Dar Boğaz",
    "🫀 Yaşam Döngüsü",
    "🧵 Uzman Ayrışım",
    "🎼 Nota",
    "🧪 Kör Test",
    "💾 Kayıt",
])

with tabs[0]:
    st.subheader("🎯 23:17 Hedef — Önce oyunu tanı, sonra kupon üret")
    st.caption(
        "Bu motor 23:02, 23:07 ve 23:12 sonuçları girilmeden kupon vermez. "
        "Önceki gecenin 23:42/23:47/23:52/23:57 çapraz karakterini de kullanır."
    )
    try:
        pred2317=sniper_2317_prediction(df)
        a,b,c,d=st.columns(4)
        a.metric("02→07 taşıma",pred2317["carry02_07"])
        b.metric("07→12 taşıma",pred2317["carry07_12"])
        c.metric("23:17 beklenen taşıma",f"{pred2317['expected_carry17']:.2f}/20")
        d.metric("Benzer geçmiş gün",pred2317["neighbors"])
        st.info(
            f"Oyun karakteri: **{pred2317['game_character']}** · "
            f"Final yapısı: **{pred2317['carry_seats']} TAŞIMA + {pred2317['return_seats']} DÖNÜŞ**"
        )
        st.markdown("## 🏆 23:17 TEK FINAL-10")
        st.code("  ".join(f"{n:02d}" for n in pred2317["final"]))
        ft=pred2317["table"]
        show=ft[ft["Sayı"].isin(pred2317["final"])].copy()
        for cc in ["Skor","Kanıt Gücü","Destek"]:
            show[cc]=show[cc].map(lambda x:round(float(x),3))
        st.dataframe(
            show[["Sayı","Kaynakta12","Durum","3-El Yol","Önceki Gece Yol",
                  "İlk3 Görünüm","Gece Görünüm","Skor","Kanıt Gücü","Destek"]],
            use_container_width=True,hide_index=True
        )
    except Exception as e:
        st.warning(str(e))
        st.info("Sıra: 23:02 sonucunu gir → 23:07 → 23:12. Sonra bu sekme 23:17 kuponunu açar.")

    st.markdown("### 🧪 23:17 Walk-Forward")
    ntest2317=st.slider("Son kaç hedef günü test et?",20,100,60,10,key="sniper_ntest")
    if st.button("🧪 23:17 MOTORUNU TEST ET",use_container_width=True,key="sniper_test"):
        bt=sniper_walk_forward(df,ntest2317)
        if bt.empty:
            st.warning("Test üretilemedi.")
        else:
            x1,x2,x3,x4=st.columns(4)
            x1.metric("Final10 ort.",f"{bt['Final10'].mean():.2f}/10")
            x2.metric("4+ oranı",f"%{100*(bt['Final10']>=4).mean():.1f}")
            x3.metric("5+ oranı",f"%{100*(bt['Final10']>=5).mean():.1f}")
            x4.metric("En iyi",f"{bt['Final10'].max()}/10")
            st.dataframe(bt.sort_values(["Final10","Tarih"],ascending=[False,False]),
                         use_container_width=True,hide_index=True)

with tabs[1]:
    st.subheader("⚡ Sonucu yapıştır → KALICI KAYDET → sonraki V8.1 analizi")
    paste=st.text_area(
        "Gelen sonuç",
        height=300,
        placeholder=(
            "Çekiliş no: 48814\n"
            "13.08.2026 - 23:02\n"
            "2\n5\n7\n8\n11\n17\n20\n22\n24\n33\n"
            "42\n46\n50\n52\n65\n68\n70\n71\n74\n78"
        ),
        key="v4_paste",
    )

    if st.button("⚡ KALICI KAYDET + V8.1 ÜRET",type="primary",use_container_width=True):
        try:
            r=parse_block(paste)

            old=st.session_state.get("v4_last_prediction")
            if old and old["target_date"]==r["date"] and old["target_time"]==r["time"]:
                actual=set(r["numbers"]); src=set(old["source_numbers"])
                actual_carry=src&actual; actual_return=actual-src
                report={
                    "target":f"{r['date']} {r['time']}",
                    "actual_regime":regime_of(len(actual_carry)),
                    "recommended":old["recommended"],
                    "tickets":{rg:sorted(set(old["tickets"][rg])&actual) for rg in REGIMES},
                    "carry_actual":sorted(actual_carry),
                    "carry_hits":sorted(set(old["carry_pool"])&actual_carry),
                    "return_hits":sorted(set(old["return_pool"])&actual_return),
                    "narrow_hits":sorted(set(old["narrow_pool"])&actual),
                }
                audit_true,audit_false=build_elimination_audit(old,actual,old["source_numbers"])
                report["audit_true"]=audit_true
                report["audit_false"]=audit_false
                report["final_hits"]=sorted(set(old["final"])&actual)
                report["final_meta"]=old.get("final_meta",{})
                st.session_state["v4_last_report"]=report

            # ------------------------------------------------------------
            # ÖNCE KALICI KAYIT: analiz bundan sonra güncel veri.txt üzerinden yapılır.
            # ------------------------------------------------------------
            if upload:
                raise RuntimeError(
                    "Geçici dosya yükleme modu açıkken otomatik kalıcı kayıt yapılmaz. "
                    "Kalıcı çalışma için yüklenen dosyayı kaldırıp Repo veri.txt moduna dönün."
                )

            _, persisted_df, changed = persist_result_to_repo(r)

            # Session kopyasını da güncel tut; repo satırıyla mükerrerleşse bile
            # merge_v4_session tarih/saat bazında tek satır bırakır.
            rows=st.session_state.get("v4_rows",[])
            rows=[x for x in rows if not (x["date"]==r["date"] and x["time"]==r["time"])]
            rows.append(r)
            st.session_state["v4_rows"]=rows

            # Kritik fark: tahmin artık eski base_df'den değil,
            # kalıcı veri.txt'nin YENİDEN OKUNMUŞ halinden üretilir.
            work=merge_v4_session(persisted_df)
            nd,nt=next_target(r["date"],r["time"])
            pred=prediction_bundle(work,nd,nt)
            pred["source_numbers"]=r["numbers"]
            st.session_state["v4_last_prediction"]=pred
            st.session_state["v4_last_result"]=r
            st.session_state["v7_last_persisted_count"]=len(persisted_df)
            st.session_state["v7_last_persisted_draw"]=int(r["draw_no"])

            action = "kalıcı veri.txt'ye eklendi" if changed else "kalıcı veri.txt'de zaten vardı"
            st.success(
                f"✅ #{r['draw_no']} {action}. "
                f"Kalıcı havuz: {len(persisted_df)} çekiliş. Hedef: {nd} {nt}"
            )
        except Exception as e:
            st.error(f"V8.1 işlem durduruldu: {e}")

    report=st.session_state.get("v4_last_report")
    if report:
        with st.expander("🔎 Önceki V4 tahmininin gerçek sonuç karnesi",expanded=True):
            st.write(
                f"Gerçek rejim: **{report['actual_regime']}** · "
                f"önerilen: **{report['recommended']}**"
            )
            for rg in REGIMES:
                hits=report["tickets"][rg]
                st.write(f"**{rg}: {len(hits)}/7** — " + (" ".join(map(str,hits)) or "yok"))
            st.write(
                f"Gerçek taşınanlar ({len(report['carry_actual'])}): "
                + " ".join(map(str,report["carry_actual"]))
            )
            st.write(
                f"Taşıma havuzu yakaladı **{len(report['carry_hits'])}**: "
                + (" ".join(map(str,report["carry_hits"])) or "yok")
            )
            st.write(
                f"Dönüş havuzu yakaladı **{len(report['return_hits'])}**: "
                + (" ".join(map(str,report["return_hits"])) or "yok")
            )
            st.write(
                f"Dar-16 gerçek sayı yakaladı **{len(report['narrow_hits'])}/16**: "
                + (" ".join(map(str,report["narrow_hits"])) or "yok")
            )

            st.write(
                f"V7 FINAL gerçek sayı yakaladı **{len(report.get('final_hits',[]))}/10**: "
                + (" ".join(map(str,report.get("final_hits",[]))) or "yok")
            )
            fm=report.get("final_meta",{})
            if fm:
                st.caption(
                    f"Final koltukları: {fm.get('carry_seats','?')} TAŞIMA + "
                    f"{fm.get('return_seats','?')} DÖNÜŞ · "
                    f"uzman beklenen taşıma {fm.get('predicted_carry',0):.2f}"
                )
            if isinstance(report.get("audit_true"),pd.DataFrame):
                st.markdown("#### 🧵 Doğru sayı nerede kayboldu?")
                st.dataframe(report["audit_true"],use_container_width=True,hide_index=True)
            if isinstance(report.get("audit_false"),pd.DataFrame) and not report["audit_false"].empty:
                st.markdown("#### ❌ Yanlış Final adayları neden girdi?")
                st.dataframe(report["audit_false"],use_container_width=True,hide_index=True)

    pred=st.session_state.get("v4_last_prediction")
    if pred:
        rm=pred["regime"]
        st.markdown(f"## 🎯 V4 — {pred['target_date']} {pred['target_time']}")
        p1,p2,p3=st.columns(3)
        p1.metric("Düşük rejim",f"%{100*rm['probs']['DÜŞÜK']:.1f}")
        p2.metric("Normal rejim",f"%{100*rm['probs']['NORMAL']:.1f}")
        p3.metric("Yüksek rejim",f"%{100*rm['probs']['YÜKSEK']:.1f}")
        st.info(
            f"Önerilen rejim: **{pred['recommended']}** · "
            f"beklenen taşıma: **{rm['expected_carry']:.2f}/20** · "
            f"{rm['neighbors']} benzer geçmiş bağlam kullanıldı."
        )

        cols=st.columns(3)
        emoji={"DÜŞÜK":"🌘","NORMAL":"🌗","YÜKSEK":"🌕"}
        for j,rg in enumerate(REGIMES):
            with cols[j]:
                st.markdown(f"### {emoji[rg]} {rg} Kuponu")
                st.code("  ".join(f"{n:02d}" for n in pred["tickets"][rg]))
                st.caption(
                    " · ".join(
                        f"{n:02d}:{pred['ticket_reasons'][rg].get(n,'')}"
                        for n in pred["tickets"][rg]
                    )
                )

        c1,c2=st.columns(2)
        with c1:
            st.markdown("### 🫱 Taşıma Havuzu — 12")
            st.code(" ".join(f"{n:02d}" for n in pred["carry_pool"]))
        with c2:
            st.markdown("### 😴 Dönüş Havuzu — 20")
            st.code(" ".join(f"{n:02d}" for n in pred["return_pool"]))

        st.markdown("### 🔬 Dar Boğaz — 16")
        st.code(" ".join(f"{n:02d}" for n in pred["narrow_pool"]))
        st.caption(
            "Bu 16 sayı tek yüksek skor sırasından değil; önerilen rejim + karşı-skor + kanıt birleşiminden gelir."
        )

        st.markdown("## 🏆 TEK FINAL KUPONU — 10")
        st.code("  ".join(f"{n:02d}" for n in pred["final"]))
        st.caption(" · ".join(
            f"{n:02d}:{pred['reasons'].get(n,'')}" for n in pred["final"]
        ))
        meta=pred.get("final_meta",{})
        if meta:
            st.info(
                f"V7 Final koltukları: **{meta['carry_seats']} TAŞIMA + {meta['return_seats']} DÖNÜŞ** · "
                f"uzman beklenen gerçek taşıma: **{meta['predicted_carry']:.2f}/20**"
            )

        st.markdown("### 🧵 FINAL Sinyal Ayrışımı — neden seçildi?")
        ft = pred.get("final_table")
        if ft is not None:
            show = ft[ft["Sayı"].isin(pred["final"])].copy()

            # V7 final tablosunda ana sütun FinalPuanV7'dir.
            # Eski V5/V6 oturumlarından gelen tahminlerde FinalPuan olabilir;
            # ikisi de yoksa mevcut güvenli sütunlarla devam et.
            sort_cols = []
            if "FinalPuanV7" in show.columns:
                sort_cols.append("FinalPuanV7")
            elif "FinalPuan" in show.columns:
                sort_cols.append("FinalPuan")
            if "Uzman Olasılığı" in show.columns:
                sort_cols.append("Uzman Olasılığı")
            if "Yaşam Olasılığı" in show.columns:
                sort_cols.append("Yaşam Olasılığı")
            if sort_cols:
                show = show.sort_values(sort_cols, ascending=[False]*len(sort_cols))

            for c in ["Uzman Olasılığı","Yaşam Olasılığı","Sönme Riski","FinalPuanV7","FinalPuan"]:
                if c in show.columns:
                    show[c] = show[c].map(lambda x: round(float(x),3))

            life_cols = [
                "Sayı","Kaynakta","Uzman Tür","Yaşam Durumu","Faz","Yaş","Momentum",
                "Uzman Olasılığı","Uzman Destek","Uzman Gerekçe",
                "Yaşam Olasılığı","Sönme Riski","FinalPuanV7","FinalPuan"
            ]
            visible_cols = [c for c in life_cols if c in show.columns]
            if visible_cols and not show.empty:
                st.dataframe(show[visible_cols], use_container_width=True, hide_index=True)
            else:
                st.info("FINAL ayrışım tablosu için gösterilebilir sütun bulunamadı.")
            st.caption(
                "V7'de DEVAM-2/DEVAM-3 otomatik artı değildir. Taşıma ve dönüş ayrı uzmanlarca, "
                "aynı fazın geçmişte gerçekten sürme/dönme başarısına göre değerlendirilir."
            )

with tabs[2]:
    st.subheader("🌗 Rejim Algılayıcı")
    slot=st.selectbox("Hedef nota",SLOTS,index=1,key="v4_regime_slot")
    try:
        rm=learn_regime_model(df,slot)
        a,b,c,d=st.columns(4)
        a.metric("DÜŞÜK",f"%{100*rm['probs']['DÜŞÜK']:.1f}")
        b.metric("NORMAL",f"%{100*rm['probs']['NORMAL']:.1f}")
        c.metric("YÜKSEK",f"%{100*rm['probs']['YÜKSEK']:.1f}")
        d.metric("Beklenen taşıma",f"{rm['expected_carry']:.2f}")
        st.write(
            f"Öneri: **{rm['recommended']}**. Bu seçim sadece nota ortalamasına değil; "
            "son üç taşıma, aynı-nota son altı, kaynak çekiliş yapısı ve son-6 görünüm yoğunluğuna bakar."
        )
        reg_rows=[]
        for rg in REGIMES:
            reg_rows.append({
                "Rejim":rg,
                "Olasılık %":round(100*rm["probs"][rg],1),
                "Tarihsel rejim ort. taşıma":round(rm["carry_by_regime"][rg],2),
            })
        st.dataframe(pd.DataFrame(reg_rows),use_container_width=True,hide_index=True)
    except Exception as e:
        st.info(str(e))

with tabs[3]:
    st.subheader("🫱 Taşıma İzleri — önceki 20 kendi liginde")
    slot=st.selectbox("Taşıma hedef notası",SLOTS,index=1,key="v4_carry_slot")
    try:
        rm=learn_regime_model(df,slot)
        cm=build_candidate_model(df,slot)
        t=score_v4_candidates(df,slot,rm,cm)
        carry=t[t["Kaynakta"]].sort_values(
            [rm["recommended"],"Karşı Skor","Kanıt"],ascending=False
        ).copy()
        cols=["Sayı","Lig Sıra","DÜŞÜK","NORMAL","YÜKSEK","Karşı Skor","Kanıt",
              "6 Yol","Son6 Görünüm","AynıNota6","Paket","En İyi Paket","Gizli Aday"]
        for c in ["DÜŞÜK","NORMAL","YÜKSEK","Karşı Skor","Kanıt","Paket"]:
            carry[c]=carry[c].map(lambda x:round(float(x),3))
        st.dataframe(carry[cols],use_container_width=True,hide_index=True)
    except Exception as e:
        st.info(str(e))

with tabs[4]:
    st.subheader("😴 Dinlenip Dönüş — kaynakta olmayan 60 kendi liginde")
    slot=st.selectbox("Dönüş hedef notası",SLOTS,index=1,key="v4_return_slot")
    try:
        rm=learn_regime_model(df,slot)
        cm=build_candidate_model(df,slot)
        t=score_v4_candidates(df,slot,rm,cm)
        ret=t[~t["Kaynakta"]].sort_values(
            [rm["recommended"],"Karşı Skor","Kanıt"],ascending=False
        ).copy()
        cols=["Sayı","Lig Sıra","Gap","6 Yol","Son6 Görünüm","AynıNota6",
              "DÜŞÜK","NORMAL","YÜKSEK","Karşı Skor","Kanıt","Gizli Aday"]
        for c in ["DÜŞÜK","NORMAL","YÜKSEK","Karşı Skor","Kanıt"]:
            ret[c]=ret[c].map(lambda x:round(float(x),3))
        st.dataframe(ret[cols].head(35),use_container_width=True,hide_index=True)
    except Exception as e:
        st.info(str(e))

with tabs[5]:
    st.subheader("🎯 Havuz → Dar Boğaz → 3 Rejim Kuponu")
    slot=st.selectbox("Dar boğaz hedef notası",SLOTS,index=1,key="v4_narrow_slot")
    try:
        pred=prediction_bundle(df,str(df.iloc[-1]["date"]),slot)
        st.write(
            f"Rejim önerisi: **{pred['recommended']}** · "
            f"Beklenen taşıma {pred['regime']['expected_carry']:.2f}"
        )
        st.code("Dar16: " + " ".join(f"{n:02d}" for n in pred["narrow_pool"]))
        narrow=pred["table"][pred["table"]["Sayı"].isin(pred["narrow_pool"])].copy()
        narrow["Dar Sıra"]=narrow["Kanıt"].rank(ascending=False,method="first").astype(int)
        narrow=narrow.sort_values(["Kanıt","Karşı Skor"],ascending=False)
        for c in ["DÜŞÜK","NORMAL","YÜKSEK","Beklenen Skor","Karşı Skor","Kanıt"]:
            narrow[c]=narrow[c].map(lambda x:round(float(x),3))
        st.dataframe(
            narrow[["Sayı","Kaynakta","Gap","Ham Sıra","Lig Sıra","DÜŞÜK","NORMAL","YÜKSEK",
                    "Beklenen Skor","Karşı Skor","Kanıt","6 Yol","Gizli Aday"]],
            use_container_width=True,hide_index=True
        )
    except Exception as e:
        st.info(str(e))

with tabs[6]:
    st.subheader("🫀 Sayı Yaşam Döngüsü — Doğum / Devam / Sönüş / Dönüş")
    slot=st.selectbox("Yaşam hedef notası",SLOTS,index=1,key="v6_life_slot")
    try:
        lt=lifecycle_score_table(df,slot).copy()
        for c in ["Yaşam Olasılığı","Sönme Riski"]:
            lt[c]=lt[c].map(lambda x:round(float(x),3))
        st.dataframe(
            lt[["Sayı","Yaşam Durumu","Faz","Yaş","Önceki Faz","Momentum",
                "Son3","Son6","AynıNota6","Yaşam Olasılığı","Sönme Riski","Yaşam Destek"]].head(40),
            use_container_width=True,hide_index=True
        )
        st.info(
            "Bu tablo '2 kere çıktı = puan artır' mantığı kullanmaz. "
            "Örneğin 2. devam fazı geçmişte çoğunlukla sönüyorsa puanı düşer; "
            "1-4 el dinlenen bir sayı aynı fazda geçmişte dönüyorsa yükselir."
        )
    except Exception as e:
        st.info(str(e))

with tabs[7]:
    st.subheader("🧵 Taşıma / Dönüş Uzman Ayrışımı")
    slot=st.selectbox("Uzman hedef notası",SLOTS,index=1,key="v7_expert_slot")
    try:
        et=transition_expert_table(df,slot).copy()
        for c in ["Uzman Olasılığı","Sönme Riski Uzman"]:
            et[c]=et[c].map(lambda x:round(float(x),3))
        c1,c2=st.columns(2)
        with c1:
            st.markdown("#### 🫱 TAŞIMA — önceki 20")
            st.dataframe(
                et[et["Kaynakta"]].sort_values("Uzman Olasılığı",ascending=False)
                [["Sayı","Durum","Yaş","Momentum","AynıNota6","Komşu","Geçiş Karakteri",
                  "Uzman Olasılığı","Sönme Riski Uzman","Uzman Destek"]].head(20),
                use_container_width=True,hide_index=True
            )
        with c2:
            st.markdown("#### 😴 DÖNÜŞ — kaynakta olmayan 60")
            st.dataframe(
                et[~et["Kaynakta"]].sort_values("Uzman Olasılığı",ascending=False)
                [["Sayı","Durum","Yaş","Momentum","AynıNota6","Komşu","Geçiş Karakteri",
                  "Uzman Olasılığı","Uzman Destek"]].head(25),
                use_container_width=True,hide_index=True
            )
        st.info(
            "Bu tabloda 'kaç kere çıktı' tek başına puan değildir. Aynı yaşam fazının, aynı nota ve "
            "benzer geçiş karakterinde gerçekten sürüp sürmediği veya geri dönüp dönmediği ölçülür."
        )
    except Exception as e:
        st.info(str(e))

with tabs[8]:
    st.subheader("🎼 Nota Karakteri")
    st.dataframe(note_character(df),use_container_width=True,hide_index=True)
    st.info(
        "V4 nota farkını sert kural yapmaz. Nota, rejim ve sayı yollarını koşullandıran bağlamdır."
    )

with tabs[9]:
    st.subheader("🧪 Sızıntısız Walk-Forward")
    ntest=st.selectbox("Test adedi",[24,48,72,120,180],index=2,key="v4_test_n")
    if st.button("🚀 V4 TEST ET",type="primary",use_container_width=True):
        with st.spinner("Her hedef yalnız geçmiş veriyle yeniden kuruluyor..."):
            bt=walk_forward(df,ntest)
        st.session_state["v4_bt"]=bt

    bt=st.session_state.get("v4_bt",pd.DataFrame())
    if isinstance(bt,pd.DataFrame) and not bt.empty:
        a,b,c,d,e=st.columns(5)
        a.metric("Test",len(bt))
        b.metric("Rejim doğruluğu",f"%{100*bt['Rejim Doğru'].mean():.1f}")
        c.metric("FINAL10 ort.",f"{bt['FINAL10 İsabet'].mean():.2f}/10")
        d.metric("4+ oranı",f"%{100*(bt['FINAL10 İsabet']>=4).mean():.1f}")
        e.metric("Dar16 ort.",f"{bt['Dar16'].mean():.2f}/16")

        st.caption(
            "Rastgele 7 sayının teorik beklenen isabeti 1.75'tir. "
            "V4'ün amacı tek geçmiş örneği parlatmak değil; rejim ve dar-boğazın ileri testte değer katıp katmadığını ölçmektir."
        )

        by=bt.groupby("Saat").agg(
            Test=("Önerilen İsabet","size"),
            Rejim=("Rejim Doğru","mean"),
            Onerilen=("Önerilen İsabet","mean"),
            Dusuk=("DÜŞÜK İsabet","mean"),
            Normal=("NORMAL İsabet","mean"),
            Yuksek=("YÜKSEK İsabet","mean"),
            TasimaPool=("Taşıma Havuzu","mean"),
            DonusPool=("Dönüş Havuzu","mean"),
            Dar16=("Dar16","mean"),
        ).reset_index()
        by["Rejim %"]=(100*by.pop("Rejim")).round(1)
        for c in ["Onerilen","Dusuk","Normal","Yuksek","TasimaPool","DonusPool","Dar16"]:
            by[c]=by[c].round(2)
        st.dataframe(by,use_container_width=True,hide_index=True)
        st.dataframe(bt.sort_values("Çekiliş",ascending=False),use_container_width=True,hide_index=True)

with tabs[10]:
    st.subheader("💾 Kalıcı veri.txt — Otomatik kayıt")
    r=st.session_state.get("v4_last_result")
    if r:
        line=line_for(r)
        st.code(line)
        st.info(
            "Hızlı sekmede 'KALICI KAYDET + V7 ÜRET' düğmesine bastığınızda bu sonuç "
            "önce GitHub veri.txt'ye yazılır, kayıt doğrulanır ve analiz ancak bundan sonra üretilir."
        )
        if st.button("🔁 Bu sonucu kalıcı kayıtta tekrar doğrula",type="secondary"):
            try:
                _, fresh_df, changed = persist_result_to_repo(r)
                st.success(
                    f"Kalıcı kayıt doğrulandı. Havuz: {len(fresh_df)} çekiliş. "
                    + ("Satır güncellendi." if changed else "Satır zaten günceldi.")
                )
            except Exception as e:
                st.error(str(e))
        try:
            updated=append_or_replace(repo_text(),line)
            st.download_button(
                "⬇️ Güncel veri.txt indir",
                updated.encode("utf-8"),
                file_name="veri.txt",
                mime="text/plain",
            )
        except Exception:
            pass
    else:
        st.caption("Önce hızlı sekmede bir sonuç işle.")

st.divider()
st.caption(
    "V7 araştırma aracıdır. Geçmiş örüntüler bağımsız gelecek çekilişlerini garanti etmez. "
    "Programın ana ilkesi: önce rejimi ve aday havuzunu ölç, sonra daralt; ham Top-7'yi final sanma."
)
