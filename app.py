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
    page_title="Sayı Laboratuvarı V3.3 — Nota / Taşıma / Dönüş / Paket",
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
            "User-Agent":"sayi-lab-v33",
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
            "User-Agent":"sayi-lab-v33",
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
# YENİ MOTOR: TAŞI / DÜŞ + DİNLEN / DÖN
# ============================================================

def build_model(train, target_slot):
    """
    Kritik fark:
    - Taşıma modeli sadece önceki 20 sayıyı kendi içinde sınıflandırır.
    - Dönüş modeli önceki elde olmayan 60 sayıyı kendi içinde sınıflandırır.
    - Sayı kimliğine aşırı bağlanmak yerine aday-olay özellikleri toplu öğrenilir.
    """
    sets=[set(x) for x in train["numbers"]]
    inds=target_indices(train,target_slot)
    if len(inds)<10:
        raise ValueError(f"{target_slot} için yeterli tarihsel örnek yok.")

    feat=defaultdict(lambda:[0,0])
    num=defaultdict(lambda:[0,0])
    pair_seen=Counter()
    pair_survive=Counter()
    actual_carry=[]

    for i in inds:
        y=sets[i]
        src=sets[i-1]
        prev6=sets[i-6:i]
        previous_same=[sets[j] for j in inds if j<i][-6:]

        actual_carry.append(len(src&y))

        for n in range(1,81):
            present=n in src
            hit=int(n in y)
            c6=recent_count(prev6,n)
            p6=path6(prev6,n)
            s6=sum(n in z for z in previous_same)

            keys=[
                ("side",present),
                ("count6",present,c6),
                ("path3",present,p6[-3:]),
                ("same6",present,s6),
            ]

            if present:
                st=streak(prev6,n)
                keys += [
                    ("streak",st),
                    ("carry_path4",p6[-4:]),
                ]
            else:
                g=gap(prev6,n)
                keys += [
                    ("gap",g),
                    ("gap_count",g,c6),
                    ("return_path4",p6[-4:]),
                ]

            for k in keys:
                feat[k][0]+=hit
                feat[k][1]+=1

            # sayı kimliği sadece zayıf yardımcı sinyal
            num[(present,n)][0]+=hit
            num[(present,n)][1]+=1

        for a,b in combinations(sorted(src),2):
            pair_seen[(a,b)]+=1
            if a in y and b in y:
                pair_survive[(a,b)]+=1

    return {
        "feat":feat,
        "num":num,
        "pair_seen":pair_seen,
        "pair_survive":pair_survive,
        "carry_mean":float(np.mean(actual_carry)),
        "carry_median":float(np.median(actual_carry)),
        "carry_std":float(np.std(actual_carry)),
        "n_examples":len(inds),
    }

def score_candidates(train, target_slot, model):
    sets=[set(x) for x in train["numbers"]]
    src=sets[-1]
    prev6=sets[-6:]
    inds=target_indices(train,target_slot)
    previous_same=[sets[j] for j in inds][-6:]

    rows=[]
    for n in range(1,81):
        present=n in src
        c6=recent_count(prev6,n)
        p6=path6(prev6,n)
        s6=sum(n in z for z in previous_same)
        g=gap(prev6,n)

        keys=[
            ("side",present),
            ("count6",present,c6),
            ("path3",present,p6[-3:]),
            ("same6",present,s6),
        ]
        if present:
            keys += [
                ("streak",streak(prev6,n)),
                ("carry_path4",p6[-4:]),
            ]
        else:
            keys += [
                ("gap",g),
                ("gap_count",g,c6),
                ("return_path4",p6[-4:]),
            ]

        rates=[]
        lbs=[]
        for k in keys:
            h,t=model["feat"][k]
            rates.append(shrink(h,t,BASE,20))
            lbs.append(wilson_lower(h,t,1.0))

        nh,nt=model["num"][(present,n)]
        number_rate=shrink(nh,nt,BASE,35)

        # bağımsız özelliklerin ortalaması; kimlik sinyali yalnız %8
        raw=0.92*np.mean(rates)+0.08*number_rate
        conservative=np.mean(lbs)

        pair_score=BASE*BASE
        best_pair=""
        if present:
            prs=[]
            for m in src:
                if m==n: continue
                k=tuple(sorted((n,m)))
                total=model["pair_seen"][k]
                if total>=5:
                    h=model["pair_survive"][k]
                    r=shrink(h,total,BASE*BASE,8)
                    prs.append((r,m,h,total))
            if prs:
                prs.sort(reverse=True)
                top=prs[:3]
                pair_score=float(np.mean([x[0] for x in top]))
                x=top[0]
                best_pair=f"{n}-{x[1]} ({x[2]}/{x[3]})"
                # pair sinyali tek başına hakim olmasın
                raw=0.90*raw + 0.10*min(0.60, pair_score*3.5)

        rows.append({
            "Sayı":n,
            "Kaynakta":present,
            "Skor":raw,
            "GüvenAlt":conservative,
            "6 Yol":p6,
            "Son6 Görünüm":c6,
            "Gap":g,
            "AynıNota6":s6,
            "Paket":pair_score,
            "En İyi Paket":best_pair,
        })

    tab=pd.DataFrame(rows)

    # kaynakta ve kaynak dışı ayrı lig: biri diğerini kalabalıkla ezmesin
    tab["Lig Sıra"]=0
    for flag in [True,False]:
        idx=tab.index[tab["Kaynakta"]==flag]
        tab.loc[idx,"Lig Sıra"]=(
            tab.loc[idx,"Skor"].rank(ascending=False,method="first").astype(int)
        )

    return tab.sort_values(["Kaynakta","Skor"],ascending=[False,False]).reset_index(drop=True)

def _rank01(series):
    x=pd.Series(series,dtype=float)
    if x.nunique(dropna=False)<=1:
        return pd.Series([0.5]*len(x),index=x.index)
    return x.rank(pct=True,method="average")


def enrich_channels(tab):
    """Final kararı ham Skor değildir; bağımsız kanalları ayrı oy haline getirir."""
    t=tab.copy()
    for c in ["Skor","GüvenAlt","Paket","Son6 Görünüm","AynıNota6"]:
        t[c+" %"]=_rank01(t[c])
    # Yol karakteri: son 6 içindeki yapı; orta/düşük skor adayının güçlü yolu kaybolmasın.
    t["Ritim %"]=_rank01(t["Son6 Görünüm"] + 0.35*t["AynıNota6"])
    t["Paket %"]=_rank01(t["Paket"])
    t["Güven %"]=_rank01(t["GüvenAlt"])
    t["Ham Sıra"]=t["Skor"].rank(ascending=False,method="first").astype(int)
    t["Lig İçi Sıra"]=0
    for flag in [True,False]:
        idx=t.index[t["Kaynakta"]==flag]
        t.loc[idx,"Lig İçi Sıra"]=t.loc[idx,"Skor"].rank(ascending=False,method="first").astype(int)

    # Birbirinden bağımsız işaretler. Tek yüksek skor finali ele geçiremez.
    t["Skor Oy"]=(t["Skor %"]>=.72).astype(int)
    t["Güven Oy"]=(t["Güven %"]>=.68).astype(int)
    t["Ritim Oy"]=(t["Ritim %"]>=.72).astype(int)
    t["Nota Oy"]=(t["AynıNota6 %"]>=.70).astype(int)
    t["Paket Oy"]=(t["Paket %"]>=.72).astype(int)
    t["Yol Oy"]=t["6 Yol"].astype(str).isin(["000100","001000","010000","100000","001001","010010","100100","101000","010100"]).astype(int)
    t["Bağımsız Oy"]=t[["Skor Oy","Güven Oy","Ritim Oy","Nota Oy","Paket Oy","Yol Oy"]].sum(axis=1)

    # Gizli aday: özellikle ham top-8 dışında, fakat birden fazla mekanizma destekli.
    t["Gizli Aday"]=(
        (t["Ham Sıra"]>=9)&(t["Ham Sıra"]<=50)&(t["Bağımsız Oy"]>=3)&
        ((t["Ritim %"]>=.78)|(t["Paket %"]>=.78)|(t["AynıNota6 %"]>=.78)|(t["Güven %"]>=.78))
    )
    return t


def select_seated_final(tab, carry_pool, return_pool, carry_mean):
    """V3.3: 7 ayrı görev koltuğu. Ham Top-7 kullanmak yasak."""
    t=enrich_channels(tab)
    selected=[]; reason={}
    def add(frame,label):
        for _,r in frame.iterrows():
            n=int(r["Sayı"])
            if n not in selected:
                selected.append(n); reason[n]=label; return True
        return False

    # Beklenen taşıma ~5 olsa da 7'liyi yalnız taşıma ile doldurma: 3 taşıma + 3 dönüş + 1 serbest/gizli.
    carry=t[t["Kaynakta"]].sort_values(["Bağımsız Oy","Güven %","Ritim %","Paket %","Skor"],ascending=False)
    rest=t[~t["Kaynakta"]].sort_values(["Bağımsız Oy","Ritim %","AynıNota6 %","Güven %","Skor"],ascending=False)

    add(carry,"Taşıma-1")
    add(carry,"Taşıma-2")
    # üçüncü taşıma özellikle paket/6-yol: aynı elden diğer ele geçen kümeyi koru
    carry_pack=carry.sort_values(["Paket %","Ritim %","Bağımsız Oy","Skor"],ascending=False)
    add(carry_pack,"Taşıma Paket")

    # Dinlenip dönüş iki farklı karakter: kısa/orta gap ve uzun/gizli dönüş.
    short=rest[rest["Gap"].between(1,3)].sort_values(["Ritim %","Güven %","Bağımsız Oy","Skor"],ascending=False)
    longr=rest[rest["Gap"].between(4,6)].sort_values(["AynıNota6 %","Ritim %","Bağımsız Oy","Skor"],ascending=False)
    if not add(short,"Dinlenip Dönüş-Kısa"): add(rest,"Dinlenip Dönüş-Kısa")
    if not add(longr,"Dinlenip Dönüş-Uzun"): add(rest,"Dinlenip Dönüş-Uzun")

    # 6 çekiliş + nota koltuğu; 02/07/12/17 dahil hedef nota kendi geçmişiyle öğrenilir.
    rhythm=t.sort_values(["Ritim %","AynıNota6 %","Bağımsız Oy","Güven %","Skor"],ascending=False)
    add(rhythm,"6 Çekiliş + Nota")

    # Son koltuk kesinlikle ham Top-8 dışını arar: orta/düşük skorun kaçmasını engeller.
    hidden=t[t["Gizli Aday"]].sort_values(["Bağımsız Oy","Ritim %","Paket %","AynıNota6 %","Güven %"],ascending=False)
    if not add(hidden,"Gizli Orta/Düşük"):
        mid=t[(t["Ham Sıra"]>=9)&(t["Ham Sıra"]<=45)].sort_values(["Bağımsız Oy","Ritim %","Paket %","Güven %","Skor"],ascending=False)
        add(mid,"Gizli Orta/Düşük")

    consensus=t.sort_values(["Bağımsız Oy","Güven %","Skor"],ascending=False)
    while len(selected)<7:
        if not add(consensus,"Tamamlama"): break
    return selected[:7],reason,t


def prediction_bundle(train, target_date, target_slot):
    model=build_model(train,target_slot)
    tab=score_candidates(train,target_slot,model)
    carry=tab[tab["Kaynakta"]].sort_values("Skor",ascending=False).reset_index(drop=True)
    ret=tab[~tab["Kaynakta"]].sort_values("Skor",ascending=False).reset_index(drop=True)
    carry_pool=carry.head(10)["Sayı"].astype(int).tolist()
    return_pool=ret.head(18)["Sayı"].astype(int).tolist()
    final,reasons,enriched=select_seated_final(tab,carry_pool,return_pool,model["carry_mean"])
    return {
        "model":model,"table":enriched,"carry_pool":carry_pool,"return_pool":return_pool,
        "final":final,"reasons":reasons,"target_date":target_date,"target_time":target_slot,
    }


# ============================================================
# WALK FORWARD
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
        cp=set(pred["carry_pool"])
        rp=set(pred["return_pool"])
        final=set(pred["final"])

        rows.append({
            "Çekiliş":int(tgt["draw_no"]),
            "Tarih":str(tgt["date"]),
            "Saat":str(tgt["time"]),
            "Gerçek Taşıma":len(actual_carry),
            "Taşıma Havuzu İsabet":len(cp&actual_carry),
            "Dönüş Havuzu İsabet":len(rp&actual_return),
            "Final İsabet":len(final&actual),
            "Final": "-".join(map(str,pred["final"])),
        })
    return pd.DataFrame(rows)


# ============================================================
# UYGULAMA VERİSİ
# ============================================================

st.title("🧬 Sayı Laboratuvarı V3.3 — Nota / Taşıma / Dönüş / Paket")
st.caption(
    "Önceki 20 sayıyı 'kalır mı düşer mi?', diğer 60 sayıyı 'dinlenip döner mi?' "
    "diye iki ayrı ligde analiz eder. Tek ham puana saplanmaz."
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

df=merge_session(base_df)

st.caption(
    f"📂 {source} · {len(df)} çekiliş · {df['date'].nunique()} gün · "
    f"son: #{df.iloc[-1]['draw_no']} {df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

tabs=st.tabs([
    "⚡ Hızlı",
    "🫱 Elden Ele",
    "😴 Dinlenip Dönüş",
    "🎼 Nota",
    "🧪 Kör Test",
    "💾 Kayıt",
])

# ============================================================
# HIZLI
# ============================================================

with tabs[0]:
    st.subheader("⚡ Sonucu yapıştır → sonraki hedefi çıkar")
    paste=st.text_area(
        "Gelen sonucu aynen yapıştır",
        height=300,
        placeholder=(
            "Çekiliş no: 48604\n"
            "12.08.2026 - 23:37\n"
            "1\n8\n10\n14\n15\n22\n27\n29\n31\n36\n"
            "37\n39\n41\n46\n51\n52\n56\n58\n69\n72"
        ),
        key="paste33",
    )

    if st.button("⚡ İŞLE + SONRAKİ ANALİZİ ÜRET",type="primary",use_container_width=True):
        try:
            r=parse_block(paste)

            # Önceki tahmini gelen gerçek sonuçla otomatik denetle
            old=st.session_state.get("v33_last_prediction")
            if old and old["target_date"]==r["date"] and old["target_time"]==r["time"]:
                actual=set(r["numbers"])
                src=set(old["source_numbers"])
                carry_actual=src&actual
                return_actual=actual-src
                report={
                    "target":f"{r['date']} {r['time']}",
                    "final_hits":sorted(set(old["final"])&actual),
                    "carry_actual":sorted(carry_actual),
                    "carry_pool_hits":sorted(set(old["carry_pool"])&carry_actual),
                    "return_actual":sorted(return_actual),
                    "return_pool_hits":sorted(set(old["return_pool"])&return_actual),
                }
                st.session_state["v33_last_report"]=report

            rows=st.session_state.get("v33_rows",[])
            rows=[x for x in rows if not (x["date"]==r["date"] and x["time"]==r["time"])]
            rows.append(r)
            st.session_state["v33_rows"]=rows

            work=merge_session(base_df)
            nd,nt=next_target(r["date"],r["time"])
            pred=prediction_bundle(work,nd,nt)
            pred["source_numbers"]=r["numbers"]
            st.session_state["v33_last_prediction"]=pred
            st.session_state["v33_last_result"]=r

            st.success(f"✅ #{r['draw_no']} işlendi. Hedef: {nd} {nt}")
        except Exception as e:
            st.error(f"İşlem başarısız: {e}")

    report=st.session_state.get("v33_last_report")
    if report:
        with st.expander("🔎 Bir önceki tahminin gerçek sonuç kontrolü",expanded=True):
            st.write(f"**Hedef:** {report['target']}")
            st.write(
                f"Final kupon isabeti: **{len(report['final_hits'])}/7** — "
                + (" ".join(map(str,report["final_hits"])) or "yok")
            )
            st.write(
                f"Gerçek taşınanlar ({len(report['carry_actual'])}): "
                + " ".join(map(str,report["carry_actual"]))
            )
            st.write(
                f"Taşıma havuzu yakaladı ({len(report['carry_pool_hits'])}): "
                + (" ".join(map(str,report["carry_pool_hits"])) or "yok")
            )
            st.write(
                f"Dönüş havuzu yakaladı ({len(report['return_pool_hits'])}): "
                + (" ".join(map(str,report["return_pool_hits"])) or "yok")
            )

    pred=st.session_state.get("v33_last_prediction")
    if pred:
        st.markdown(f"## 🎯 V3.3 — {pred['target_date']} {pred['target_time']}")
        st.code("  ".join(f"{n:02d}" for n in pred["final"]))
        st.caption(" · ".join(f"{n:02d}: {pred['reasons'].get(n,'')}" for n in pred["final"]))

        c1,c2=st.columns(2)
        with c1:
            st.markdown("### 🫱 Taşıma Havuzu")
            st.code(" ".join(f"{n:02d}" for n in pred["carry_pool"]))
            st.caption(
                f"Geçmiş {pred['model']['n_examples']} aynı-nota örneğinde "
                f"ortalama gerçek taşıma: {pred['model']['carry_mean']:.2f}"
            )
        with c2:
            st.markdown("### 😴 Dinlenip Dönüş Havuzu")
            st.code(" ".join(f"{n:02d}" for n in pred["return_pool"]))
            st.caption("Önceki elde olmayan 60 sayı ayrı ligde puanlanır.")

        t=pred["table"].copy()
        final_rows=t[t["Sayı"].isin(pred["final"])][
            ["Sayı","Kaynakta","Lig İçi Sıra","Ham Sıra","Bağımsız Oy","Skor","GüvenAlt","6 Yol","Son6 Görünüm","Gap","AynıNota6","En İyi Paket","Gizli Aday"]
        ].copy()
        final_rows["Skor"]=final_rows["Skor"].round(3)
        final_rows["GüvenAlt"]=final_rows["GüvenAlt"].round(3)
        st.dataframe(final_rows,use_container_width=True,hide_index=True)

# ============================================================
# TAŞIMA
# ============================================================

with tabs[1]:
    st.subheader("🫱 Önceki 20 sayı: KALIR mı DÜŞER mi?")
    st.caption(
        "Bu sekme yalnız kaynak 20 sayıyı yarıştırır. Diğer 60 sayı bu sıralamaya karışmaz."
    )
    slot=st.selectbox("Hedef nota",SLOTS,index=7,key="carry_slot")
    try:
        pred=prediction_bundle(df,str(df.iloc[-1]["date"]),slot)
        carry=pred["table"][pred["table"]["Kaynakta"]].sort_values("Skor",ascending=False).copy()
        carry["Skor"]=carry["Skor"].round(3)
        carry["GüvenAlt"]=carry["GüvenAlt"].round(3)
        st.metric("Bu nota tarihsel ort. taşıma",f"{pred['model']['carry_mean']:.2f}/20")
        st.dataframe(
            carry[["Sayı","Lig Sıra","Skor","GüvenAlt","6 Yol","Son6 Görünüm","AynıNota6","En İyi Paket"]],
            use_container_width=True,hide_index=True
        )
    except Exception as e:
        st.info(str(e))

# ============================================================
# DİNLENME
# ============================================================

with tabs[2]:
    st.subheader("😴 Önceki elde olmayan 60 sayı: DÖNER mi?")
    st.caption(
        "Gap 1/2/3/4/5/6, son-6 yolu ve aynı notanın son 6 günü birlikte değerlendirilir."
    )
    slot2=st.selectbox("Hedef nota",SLOTS,index=7,key="return_slot")
    try:
        pred=prediction_bundle(df,str(df.iloc[-1]["date"]),slot2)
        ret=pred["table"][~pred["table"]["Kaynakta"]].sort_values("Skor",ascending=False).copy()
        ret["Skor"]=ret["Skor"].round(3)
        ret["GüvenAlt"]=ret["GüvenAlt"].round(3)
        st.dataframe(
            ret[["Sayı","Lig Sıra","Skor","GüvenAlt","Gap","6 Yol","Son6 Görünüm","AynıNota6"]].head(30),
            use_container_width=True,hide_index=True
        )
    except Exception as e:
        st.info(str(e))

# ============================================================
# NOTA
# ============================================================

with tabs[3]:
    st.subheader("🎼 Çekiliş karakterleri")
    chars=note_character(df)
    st.dataframe(chars,use_container_width=True,hide_index=True)
    st.info(
        "Taşıma miktarı nota bazında ayrı öğrenilir; 23:02 önceki gün 23:57 ile çapraz-gün geçişidir."
    )

# ============================================================
# KÖR TEST
# ============================================================

with tabs[4]:
    st.subheader("🧪 Walk-forward: taşıma havuzu / dönüş havuzu / final")
    ntest=st.selectbox("Test adedi",[24,48,72,120],index=2)
    if st.button("🚀 TEST ET",type="primary",use_container_width=True):
        with st.spinner("Geçmiş hedeflerde yalnız geçmiş veriyle test ediliyor..."):
            bt=walk_forward(df,ntest)
        st.session_state["v33_bt"]=bt

    bt=st.session_state.get("v33_bt",pd.DataFrame())
    if isinstance(bt,pd.DataFrame) and not bt.empty:
        a,b,c,d=st.columns(4)
        a.metric("Test",len(bt))
        b.metric("Final ort.",f"{bt['Final İsabet'].mean():.2f}/7")
        c.metric("3+ oranı",f"%{100*(bt['Final İsabet']>=3).mean():.1f}")
        d.metric("4+ oranı",f"%{100*(bt['Final İsabet']>=4).mean():.1f}")

        st.caption(
            "Rastgele 7 sayının teorik beklenen ortalaması 1.75/7'dir. "
            "Bu sürüm özellikle taşıma/dönüş havuzunun ne kadar doğru aday kapsadığını ayrıca gösterir."
        )

        by=bt.groupby("Saat").agg(
            Test=("Final İsabet","size"),
            FinalOrt=("Final İsabet","mean"),
            TasimaPool=("Taşıma Havuzu İsabet","mean"),
            DonusPool=("Dönüş Havuzu İsabet","mean"),
            GercekTasima=("Gerçek Taşıma","mean"),
        ).reset_index()
        for c in ["FinalOrt","TasimaPool","DonusPool","GercekTasima"]:
            by[c]=by[c].round(2)
        st.dataframe(by,use_container_width=True,hide_index=True)
        st.dataframe(bt.sort_values("Çekiliş",ascending=False),use_container_width=True,hide_index=True)

# ============================================================
# KAYIT
# ============================================================

with tabs[5]:
    st.subheader("💾 Kalıcı veri.txt")
    r=st.session_state.get("v33_last_result")
    if r:
        line=line_for(r)
        st.code(line)
        if st.button("💾 Son sonucu GitHub veri.txt'ye yaz",type="primary"):
            try:
                token,repo,branch,path=github_config()
                if not token:
                    st.error("GITHUB_TOKEN tanımlı değil.")
                else:
                    text,_=github_read(token,repo,branch,path)
                    updated=append_or_replace(text,line)
                    github_write(
                        token,repo,branch,path,updated,
                        f"V3.3 add {r['draw_no']} {r['date']} {r['time']}"
                    )
                    st.success("Kalıcı veri.txt güncellendi.")
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
    "V3.3 araştırma aracıdır; bağımsız çekilişleri garanti ederek öngörmez. "
    "Ana değişiklik: taşıma ve dinlenip-dönüş artık tek kupon koltuğu değil, ayrı aday ligleridir."
)
