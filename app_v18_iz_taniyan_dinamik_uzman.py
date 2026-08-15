
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
import base64, json, math, re, urllib.parse, urllib.request

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Hızlı On V17 — Bağımsız Taşıma / Dönüş Uzmanları",
    page_icon="🌙",
    layout="wide",
)

st.title("🌙 Hızlı On V17 — Bağımsız Taşıma / Dönüş Uzmanları")
st.caption(
    "İlk 3 çekiliş geceyi tanır. Sonra her yeni gerçek sonuç geldikçe gece karakterini, "
    "elden ele taşıma izlerini, dinlenip dönüşü, ortak sıcak havuzu, birlikte gelen kümeleri, "
    "birer atlamalı dizileri, ardışıkları, bant akışını ve 6-el yaşam yolunu yeniden hesaplar. "
    "Hedef otomatik olarak bir sonraki gece çekilişidir."
)

DATA_FILE = Path("veri.txt")
SLOTS = [
    "23:02","23:07","23:12","23:17","23:22","23:27",
    "23:32","23:37","23:42","23:47","23:52","23:57"
]
FIRST3 = ["23:02","23:07","23:12"]
TARGETS = SLOTS[3:]
BASE = 20/80

DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"

# ============================================================
# GITHUB / KALICI KAYIT
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
    return token,repo,branch,path

def github_read(token,repo,branch,path):
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization":f"Bearer {token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"hizli-on-v15",
        }
    )
    with urllib.request.urlopen(req,timeout=20) as r:
        obj=json.loads(r.read().decode("utf-8"))
    return base64.b64decode(obj["content"]).decode("utf-8"),obj["sha"]

def github_write(token,repo,branch,path,text,message):
    _,sha=github_read(token,repo,branch,path)
    url=f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    payload=json.dumps({
        "message":message,
        "content":base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha":sha,
        "branch":branch,
    }).encode("utf-8")
    req=urllib.request.Request(
        url,data=payload,method="PUT",
        headers={
            "Authorization":f"Bearer {token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "Content-Type":"application/json",
            "User-Agent":"hizli-on-v15",
        }
    )
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

# ============================================================
# VERİ PARSE / KAYIT
# ============================================================
def repair_draw_no(no,date_s):
    s=str(int(no))
    day=date_s.split(".")[0].zfill(2)
    if len(s)>=7 and s.endswith(day):
        cand=s[:-2]
        if 4<=len(cand)<=6:
            return int(cand)
    return int(no)

def parse_pipe(text):
    rows=[]
    for raw in str(text).splitlines():
        p=[x.strip() for x in raw.split("|")]
        if len(p)<3:
            continue
        try:
            no=int(re.findall(r"\d+",p[0])[0])
            d,t=p[1].split()
            no=repair_draw_no(no,d)
            nums=sorted(set(int(x) for x in re.findall(r"\d+",p[2])))
        except Exception:
            continue
        if t not in SLOTS or len(nums)!=20 or any(n<1 or n>80 for n in nums):
            continue
        rows.append({"draw_no":no,"date":d,"time":t,"numbers":nums})
    df=pd.DataFrame(rows)
    if df.empty:
        return df
    df["_dt"]=pd.to_datetime(df["date"]+" "+df["time"],format="%d.%m.%Y %H:%M",errors="coerce")
    df=df.dropna(subset=["_dt"])
    return (
        df.sort_values(["_dt","draw_no"])
        .drop_duplicates(["date","time"],keep="last")
        .reset_index(drop=True)
    )

def parse_result_block(raw):
    raw=str(raw or "").replace("\u00a0"," ").replace("–","-").replace("—","-").replace("−","-")
    m_no=re.search(r"(?:çekiliş|cekilis)\s*(?:no|numarası|numarasi)?\s*[:#-]?\s*(\d{4,8})",raw,re.I)
    m_dt=re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}:\d{2})",raw)
    if not m_no:
        raise ValueError("Çekiliş no bulunamadı.")
    if not m_dt:
        raise ValueError("Tarih/saat bulunamadı.")
    d=datetime.strptime(m_dt.group(1),"%d.%m.%Y").strftime("%d.%m.%Y")
    t=m_dt.group(2)
    if t not in SLOTS:
        raise ValueError("Bu uygulama 23:02–23:57 gece seansını kullanır.")
    no=repair_draw_no(int(m_no.group(1)),d)
    tail=raw[m_dt.end():]
    nums=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",tail)]
    if len(nums)!=20 or len(set(nums))!=20:
        raise ValueError(f"20 farklı sayı bekleniyor; {len(nums)} bulundu.")
    return {"draw_no":no,"date":d,"time":t,"numbers":sorted(nums)}

def line_for(r):
    return f"{r['draw_no']} | {r['date']} {r['time']} | {' '.join(map(str,r['numbers']))}"

def append_or_replace(text,r):
    key=f"{r['date']} {r['time']}"
    newline=line_for(r)
    out=[]
    done=False
    for raw in str(text).splitlines():
        if not raw.strip():
            continue
        p=[x.strip() for x in raw.split("|")]
        if len(p)>=2 and p[1]==key:
            if not done:
                out.append(newline)
                done=True
            continue
        out.append(raw.rstrip())
    if not done:
        out.append(newline)
    return "\n".join(out).rstrip()+"\n"

def persist_result(r):
    token,repo,branch,path=github_config()
    if token:
        current,_=github_read(token,repo,branch,path)
        updated=append_or_replace(current,r)
        if updated!=current:
            github_write(token,repo,branch,path,updated,f"V15 add {r['draw_no']} {r['date']} {r['time']}")
        return updated,True
    current=DATA_FILE.read_text(encoding="utf-8") if DATA_FILE.exists() else ""
    updated=append_or_replace(current,r)
    DATA_FILE.write_text(updated,encoding="utf-8")
    return updated,False

def load_df():
    token,repo,branch,path=github_config()
    if token:
        try:
            txt,_=github_read(token,repo,branch,path)
            return parse_pipe(txt),"GitHub veri.txt"
        except Exception:
            pass
    if DATA_FILE.exists():
        return parse_pipe(DATA_FILE.read_text(encoding="utf-8")),"Repo veri.txt"
    return pd.DataFrame(),"Veri yok"

# ============================================================
# GECE HARİTASI / HEDEF
# ============================================================
def day_map(df):
    out={}
    for _,r in df.iterrows():
        out.setdefault(str(r["date"]),{})[str(r["time"])]=set(r["numbers"])
    return out

def ordered_dates(df):
    return list(dict.fromkeys(df["date"].astype(str).tolist()))

def next_live_target(df):
    dm=day_map(df)
    dates=ordered_dates(df)
    if not dates:
        return None,None,"Veri yok."
    d=dates[-1]
    day=dm.get(d,{})
    missing=[s for s in FIRST3 if s not in day]
    if missing:
        return d,None,"Geceyi tanımak için eksik: "+", ".join(missing)
    for target in TARGETS:
        if target not in day:
            ti=SLOTS.index(target)
            prior=SLOTS[:ti]
            miss=[s for s in prior if s not in day]
            if miss:
                return d,None,"Akışta eksik çekiliş: "+", ".join(miss)
            return d,target,None
    return d,None,"Bu gecenin 23:57 dahil tüm çekilişleri tamamlandı."

# ============================================================
# TEMEL ÖZELLİKLER
# ============================================================
def path_bits(draws,n,k=6):
    bits=["1" if n in s else "0" for s in draws[-k:]]
    return "".join(bits).rjust(k,"0")

def streak(draws,n):
    c=0
    for s in reversed(draws):
        if n in s:
            c+=1
        else:
            break
    return c

def gap(draws,n,maxgap=8):
    if n in draws[-1]:
        return 0
    g=0
    for s in reversed(draws):
        if n in s:
            break
        g+=1
    return min(g,maxgap)

def hot_count(draws,n):
    return sum(n in s for s in draws)

def weighted_hot(draws,n):
    w=[0.55,0.68,0.80,0.90,1.00,1.12]
    use=draws[-6:]
    ww=w[-len(use):]
    return sum((n in s)*a for s,a in zip(use,ww))

def consecutive_pairs(s):
    return {(n,n+1) for n in s if n+1 in s}

def step2_links(s):
    return {(n,n+2) for n in s if n+2 in s}

def band(n):
    return (n-1)//10

def band_counts(s):
    c=[0]*8
    for n in s:
        c[band(n)]+=1
    return c

def first3_character(a,b,c):
    carry1=len(a&b)
    carry2=len(b&c)
    core=len(a&b&c)
    bands=np.array([band_counts(x) for x in [a,b,c]],dtype=float)
    band_vol=float(np.std(bands,axis=0).mean())
    cons=sum(len(consecutive_pairs(x)) for x in [a,b,c])
    step2=sum(len(step2_links(x)) for x in [a,b,c])
    if carry1>=6 and carry2>=6:
        regime="TAŞIMA-AĞIR"
    elif carry1<=3 and carry2<=3:
        regime="DÖNÜŞ-AĞIR"
    else:
        regime="KARMA"
    return {
        "regime":regime,
        "carry1":carry1,
        "carry2":carry2,
        "core":core,
        "band_vol":band_vol,
        "cons":cons,
        "step2":step2,
    }

def context_distance(a,b):
    d=0.0
    d+=abs(a["carry1"]-b["carry1"])/8
    d+=abs(a["carry2"]-b["carry2"])/8
    d+=abs(a["core"]-b["core"])/6
    d+=abs(a["band_vol"]-b["band_vol"])/3
    d+=abs(a["cons"]-b["cons"])/12
    d+=abs(a["step2"]-b["step2"])/12
    if a["regime"]!=b["regime"]:
        d+=0.30
    return d

def shrink(h,n,prior=BASE,strength=16.0):
    if n<=0:
        return prior
    return (h+prior*strength)/(n+strength)

def gap_bucket(g):
    if g == 0:
        return "0"
    if g <= 2:
        return "1-2"
    if g <= 4:
        return "3-4"
    return "5+"

def streak_bucket(s):
    if s <= 1:
        return "1"
    if s == 2:
        return "2"
    if s == 3:
        return "3"
    return "4+"

def trace_label(draws,n):
    """
    Sayının güncel yaşam izini açık biçimde tanımlar.
    Kaynakta ise taşıma izi; kaynakta değilse dinlenip-dönüş izi.
    """
    src=draws[-1]
    p6=path_bits(draws,n,6)
    if n in src:
        return f"TAŞI:{p6[-4:]}|SERİ:{streak_bucket(streak(draws,n))}"
    return f"DÖNÜŞ:{p6[-4:]}|GAP:{gap_bucket(gap(draws,n,8))}"

# ============================================================
# OLAY BANKASI
# ============================================================
def historical_events(df,target_slot):
    dm=day_map(df)
    dates=ordered_dates(df)
    ti=SLOTS.index(target_slot)
    prior_slots=SLOTS[:ti]
    events=[]
    for d in dates:
        day=dm.get(d,{})
        if not all(s in day for s in FIRST3+[target_slot]):
            continue
        if not all(s in day for s in prior_slots):
            continue
        a,b,c=[day[s] for s in FIRST3]
        gc=first3_character(a,b,c)
        draws=[day[s] for s in prior_slots]
        events.append({
            "date":d,
            "gc":gc,
            "draws":draws,
            "source":draws[-1],
            "target":day[target_slot],
        })
    return events

# ============================================================
# 7 SİNYAL MOTORU
# ============================================================
def score_candidates(df,target_slot):
    dm=day_map(df)
    dates=ordered_dates(df)
    d=dates[-1]
    day=dm[d]
    if target_slot in day:
        raise ValueError(f"{d} {target_slot} sonucu zaten kayıtlı.")
    ti=SLOTS.index(target_slot)
    prior_slots=SLOTS[:ti]
    if not all(s in day for s in prior_slots):
        miss=[s for s in prior_slots if s not in day]
        raise ValueError("Hedef öncesi eksik: "+", ".join(miss))

    draws=[day[s] for s in prior_slots]
    source=draws[-1]
    a,b,c=[day[s] for s in FIRST3]
    gc_now=first3_character(a,b,c)

    events=[e for e in historical_events(df,target_slot) if e["date"]!=d]
    if len(events)<16:
        raise ValueError(f"{target_slot} için geçmiş tam gece sayısı yetersiz: {len(events)}")

    weighted=[]
    for e in events:
        w=1.0/(0.08+context_distance(gc_now,e["gc"]))
        weighted.append((w,e))
    weighted.sort(key=lambda z:z[0],reverse=True)
    near=weighted[:min(28,len(weighted))]

    # Benzer gecelerde gerçek taşıma miktarı
    num=den=0.0
    for w,e in near:
        num+=w*len(e["source"]&e["target"])
        den+=w
    expected_carry=float(np.clip(num/den if den else 5.0,1.0,12.0))

    # Gece ortak sıcak havuzu
    cur_freq=Counter()
    for s in draws:
        cur_freq.update(s)
    hot_pool={n for n,cnt in cur_freq.items() if cnt>=max(2,int(math.ceil(len(draws)*0.35)))}

    # Son 3 çekilişte tekrar eden küme
    last3=draws[-3:]
    common_cluster=set()
    if last3:
        cc=Counter()
        for s in last3:
            cc.update(s)
        common_cluster={n for n,c in cc.items() if c>=2}

    rows=[]
    for n in range(1,81):
        in_src=n in source
        p6=path_bits(draws,n,6)
        g=gap(draws,n,8)
        st=streak(draws,n)
        iz=trace_label(draws,n)
        hot=hot_count(draws,n)
        wh=weighted_hot(draws,n)
        in_hot=int(n in hot_pool)
        in_cluster=int(n in common_cluster)

        # güncel aritmetik sinyaller
        cons_support=int((n-1) in source)+int((n+1) in source)
        step2_support=int((n-2) in source)+int((n+2) in source)
        b=band(n)
        bc=band_counts(source)
        band_density=bc[b]
        edge_neighbor=0
        if b==7:  # 71-80 bandında özel komşuluk
            edge_neighbor=sum(abs(n-x)<=3 for x in source if 71<=x<=80)

        # Geçmişte aynı durumda gerçek isabet
        sig_hits=defaultdict(float)
        sig_n=defaultdict(float)

        for w,e in near:
            ed=e["draws"]
            es=e["source"]
            y=int(n in e["target"])
            ep6=path_bits(ed,n,6)
            eg=gap(ed,n,8)
            est=streak(ed,n)
            ehot=hot_count(ed,n)
            ef=Counter()
            for s in ed:
                ef.update(s)
            ehotpool={x for x,cnt in ef.items() if cnt>=max(2,int(math.ceil(len(ed)*0.35)))}
            el3=ed[-3:]
            ecc=Counter()
            for s in el3:
                ecc.update(s)
            ecluster={x for x,cnt in ecc.items() if cnt>=2}
            eiz=trace_label(ed,n)

            # ÖZEL YAŞAM İZİ:
            # Aynı rol + aynı son-4 yaşam yolu + aynı seri/gap cebinde
            # geçmişte gerçekten hedefe gelmiş mi?
            if eiz == iz:
                sig_hits["trace"] += 1.20*w*y
                sig_n["trace"] += 1.20*w
            elif ep6[-4:] == p6[-4:] and ((n in es) == in_src):
                sig_hits["trace"] += 0.55*w*y
                sig_n["trace"] += 0.55*w

            # 1 taşıma
            if (n in es)==in_src:
                sig_hits["carry"]+=w*y
                sig_n["carry"]+=w

            # 2 dinlenip dönüş
            if (not in_src) and (not n in es):
                same_gap=(eg==g) or (1<=eg<=2 and 1<=g<=2) or (3<=eg<=4 and 3<=g<=4) or (eg>=5 and g>=5)
                if same_gap:
                    sig_hits["return"]+=w*y
                    sig_n["return"]+=w
            elif in_src:
                sig_hits["return"]+=0.25*w*y
                sig_n["return"]+=0.25*w

            # 3 gece sıcak havuzu
            if (n in ehotpool)==bool(in_hot):
                sig_hits["hot"]+=w*y
                sig_n["hot"]+=w

            # 4 birlikte gelen küme
            if (n in ecluster)==bool(in_cluster):
                sig_hits["cluster"]+=w*y
                sig_n["cluster"]+=w

            # 5 birer atlamalı dizi
            estep=int((n-2) in es)+int((n+2) in es)
            if estep==step2_support:
                sig_hits["step2"]+=w*y
                sig_n["step2"]+=w

            # 6 ardışık
            econs=int((n-1) in es)+int((n+1) in es)
            if econs==cons_support:
                sig_hits["cons"]+=w*y
                sig_n["cons"]+=w

            # 7 bant akışı
            ebc=band_counts(es)
            if abs(ebc[b]-band_density)<=1:
                sig_hits["band"]+=w*y
                sig_n["band"]+=w

            # 6-el yol
            if ep6==p6:
                sig_hits["path"]+=1.15*w*y
                sig_n["path"]+=1.15*w
            elif ep6[-4:]==p6[-4:]:
                sig_hits["path"]+=0.60*w*y
                sig_n["path"]+=0.60*w

            # streak
            if est==st or (est>=3 and st>=3):
                sig_hits["streak"]+=w*y
                sig_n["streak"]+=w

        probs={}
        supports={}
        for k in ["carry","return","hot","cluster","step2","cons","band","path","streak","trace"]:
            probs[k]=shrink(sig_hits[k],sig_n[k],BASE,13 if k in ["path","carry","return","trace"] else 18)
            supports[k]=sig_n[k]

        # destek güveni: az örnekli sinyal şişmesin
        def rel(s):
            return math.sqrt(s/(s+18.0)) if s>0 else 0.0

        # rol bazlı ana skorlar
        carry_score=(
            0.27*probs["carry"]*rel(supports["carry"]) +
            0.24*probs["trace"]*rel(supports["trace"]) +
            0.18*probs["path"]*rel(supports["path"]) +
            0.10*probs["streak"]*rel(supports["streak"]) +
            0.08*probs["hot"]*rel(supports["hot"]) +
            0.05*probs["cluster"]*rel(supports["cluster"]) +
            0.04*probs["cons"]*rel(supports["cons"]) +
            0.04*probs["band"]*rel(supports["band"])
        ) if in_src else 0.0

        return_score=(
            0.25*probs["return"]*rel(supports["return"]) +
            0.25*probs["trace"]*rel(supports["trace"]) +
            0.17*probs["path"]*rel(supports["path"]) +
            0.10*probs["hot"]*rel(supports["hot"]) +
            0.08*probs["cluster"]*rel(supports["cluster"]) +
            0.06*probs["step2"]*rel(supports["step2"]) +
            0.05*probs["cons"]*rel(supports["cons"]) +
            0.04*probs["band"]*rel(supports["band"])
        ) if not in_src else 0.0

        pattern_score=(
            0.20*probs["hot"]*rel(supports["hot"]) +
            0.18*probs["cluster"]*rel(supports["cluster"]) +
            0.14*probs["step2"]*rel(supports["step2"]) +
            0.14*probs["cons"]*rel(supports["cons"]) +
            0.16*probs["band"]*rel(supports["band"]) +
            0.13*probs["path"]*rel(supports["path"]) +
            0.05*probs["trace"]*rel(supports["trace"])
        )

        # geçmiş kanıt + güncel mikro-sinyal, ama mikro-sinyal küçük etki
        micro=0.0
        micro += 0.008*min(cons_support,2)
        micro += 0.007*min(step2_support,2)
        micro += 0.006*in_hot
        micro += 0.006*in_cluster
        if b==7 and edge_neighbor>=2:
            micro += 0.006

        final=max(carry_score,return_score)+0.35*pattern_score+micro

        # tek sinyalde parlayan ama diğerleri zayıf adayı frenle
        strong=sum(probs[k] >= 0.285 for k in ["carry","return","hot","cluster","step2","cons","band","path","trace"])
        if strong<=1:
            final-=0.018

        rows.append({
            "Sayı":n,
            "Rol":"TAŞIMA" if in_src else "DÖNÜŞ",
            "Kaynakta":in_src,
            "6-El Yol":p6,
            "Yaşamİzi":iz,
            "Gap":g,
            "Streak":st,
            "GeceFrekans":hot,
            "SıcakHavuz":bool(in_hot),
            "OrtakKüme":bool(in_cluster),
            "Step2Destek":step2_support,
            "ArdışıkDestek":cons_support,
            "Bant":f"{b*10+1}-{b*10+10}",
            "TaşımaKanıt":probs["carry"],
            "DönüşKanıt":probs["return"],
            "SıcakKanıt":probs["hot"],
            "KümeKanıt":probs["cluster"],
            "Step2Kanıt":probs["step2"],
            "ArdışıkKanıt":probs["cons"],
            "BantKanıt":probs["band"],
            "YolKanıt":probs["path"],
            "İzKanıt":probs["trace"],
            "GüçlüKanal":strong,
            "Final":final,
        })

    tab=pd.DataFrame(rows).sort_values(["Final","GüçlüKanal"],ascending=False).reset_index(drop=True)
    return tab,gc_now,expected_carry,hot_pool,common_cluster

# ============================================================
# KUPONLAR: 2 x 7 + 1 x 10
# ============================================================
def rank_experts(tab):
    """
    Sadece aday tablosundan iki bağımsız uzman sıralaması üretir.
    Bu yardımcı fonksiyon geçmiş hedefleri replay ederken de kullanılır.
    """
    z=tab.copy()
    channels=[
        "TaşımaKanıt","DönüşKanıt","SıcakKanıt","KümeKanıt",
        "Step2Kanıt","ArdışıkKanıt","BantKanıt","YolKanıt","İzKanıt"
    ]
    for c in channels:
        z[c+"_R"]=z[c].rank(pct=True,method="average")

    rcols=[c+"_R" for c in channels]
    z["Kanal70"]=z[rcols].ge(0.70).sum(axis=1)
    z["Kanal80"]=z[rcols].ge(0.80).sum(axis=1)
    z["Kanal90"]=z[rcols].ge(0.90).sum(axis=1)
    z["Top3Kanıt"]=z[rcols].apply(
        lambda r:float(np.mean(sorted([float(x) for x in r],reverse=True)[:3])),
        axis=1
    )

    carry=z[z["Kaynakta"]].copy()
    carry["UzmanA"]=(
        0.29*carry["İzKanıt_R"] +
        0.25*carry["TaşımaKanıt_R"] +
        0.19*carry["YolKanıt_R"] +
        0.08*carry["SıcakKanıt_R"] +
        0.06*carry["KümeKanıt_R"] +
        0.05*carry["ArdışıkKanıt_R"] +
        0.03*carry["BantKanıt_R"] +
        0.05*carry["Top3Kanıt"]
    )
    carry["KapıA"]=(
        (carry["Kanal70"]>=2) &
        (carry["İzKanıt_R"]>=0.55) &
        (carry["TaşımaKanıt_R"]>=0.50)
    ).astype(int)
    carry=carry.sort_values(
        ["KapıA","Kanal80","Kanal70","UzmanA","Final"],ascending=False
    )

    ret=z[~z["Kaynakta"]].copy()
    ret["UzmanB"]=(
        0.30*ret["İzKanıt_R"] +
        0.23*ret["DönüşKanıt_R"] +
        0.17*ret["YolKanıt_R"] +
        0.09*ret["SıcakKanıt_R"] +
        0.07*ret["KümeKanıt_R"] +
        0.05*ret["Step2Kanıt_R"] +
        0.04*ret["ArdışıkKanıt_R"] +
        0.02*ret["BantKanıt_R"] +
        0.03*ret["Top3Kanıt"]
    )
    ret["KapıB"]=(
        (ret["Kanal70"]>=2) &
        (ret["İzKanıt_R"]>=0.55) &
        (ret["DönüşKanıt_R"]>=0.50)
    ).astype(int)
    ret=ret.sort_values(
        ["KapıB","Kanal80","Kanal70","UzmanB","Final"],ascending=False
    )
    return z,carry,ret


def expert_night_performance(df,current_date,current_target):
    """
    Aynı gecede current_target'tan ÖNCE tamamlanmış hedefleri sızıntısız replay eder.
    Böylece hangi uzman bu gece gerçekten çalışıyor öğrenilir.
    """
    dm=day_map(df)
    day=dm.get(current_date,{})
    if current_target not in TARGETS:
        return {"n":0,"A_rate":0.5,"B_rate":0.5,"A_hits":0.0,"B_hits":0.0}

    cur_i=TARGETS.index(current_target)
    previous=[s for s in TARGETS[:cur_i] if s in day]
    previous=previous[-4:]  # en son 4 hedef, gece karakterine daha yakın

    if not previous:
        return {"n":0,"A_rate":0.5,"B_rate":0.5,"A_hits":0.0,"B_hits":0.0}

    dts=pd.to_datetime(
        df["date"]+" "+df["time"],
        format="%d.%m.%Y %H:%M",
        errors="coerce"
    )

    A_num=A_den=B_num=B_den=0.0
    details=[]

    for j,slot in enumerate(previous):
        cutoff=pd.to_datetime(
            current_date+" "+slot,
            format="%d.%m.%Y %H:%M",
            errors="coerce"
        )
        train=df[dts < cutoff].reset_index(drop=True)
        if train.empty:
            continue
        try:
            tab,gc,exp,hot,cluster=score_candidates(train,slot)
            _,carry,ret=rank_experts(tab)
            ta=carry.head(7)["Sayı"].astype(int).tolist()
            tb=ret.head(7)["Sayı"].astype(int).tolist()
            actual=day[slot]
            ha=len(set(ta)&set(actual))
            hb=len(set(tb)&set(actual))
            # yeni hedefe yakın sonuç daha ağır
            w=1.0 + 0.35*j
            A_num+=w*(ha/7.0); A_den+=w
            B_num+=w*(hb/7.0); B_den+=w
            details.append((slot,ha,hb))
        except Exception:
            continue

    if A_den==0 or B_den==0:
        return {"n":0,"A_rate":0.5,"B_rate":0.5,"A_hits":0.0,"B_hits":0.0}

    return {
        "n":len(details),
        "A_rate":A_num/A_den,
        "B_rate":B_num/B_den,
        "A_hits":float(np.mean([x[1] for x in details])) if details else 0.0,
        "B_hits":float(np.mean([x[2] for x in details])) if details else 0.0,
        "details":details,
    }


def make_tickets(tab,expected_carry,expert_perf=None):
    """
    V18:
      7A = gerçek taşıma izi uzmanı
      7B = gerçek dinlenip-dönüş izi uzmanı
      10'lu = bu gece hangi uzman daha iyi çalışıyorsa ona dinamik ağırlık verir
    """
    z,carry,ret=rank_experts(tab)
    t7a=carry.head(7)["Sayı"].astype(int).tolist()
    t7b=ret.head(7)["Sayı"].astype(int).tolist()

    perf=expert_perf or {"n":0,"A_rate":0.5,"B_rate":0.5}
    ar=float(perf.get("A_rate",0.5))
    br=float(perf.get("B_rate",0.5))

    # Beklenen taşıma oranı temel yön; gecedeki uzman başarısı ince ayar.
    base_share=float(np.clip(expected_carry/20.0,0.10,0.60))
    perf_delta=float(np.clip(ar-br,-0.35,0.35))
    carry_share=float(np.clip(base_share + 0.45*perf_delta,0.20,0.75))

    carry_seats=int(np.clip(round(10*carry_share),2,7))
    return_seats=10-carry_seats

    c10=carry.head(carry_seats)["Sayı"].astype(int).tolist()
    r10=ret.head(return_seats)["Sayı"].astype(int).tolist()
    t10=c10+r10

    # 10'lu sıralaması uzman güveni + çoklu kanıt ile.
    a_map=dict(zip(carry["Sayı"].astype(int),carry["UzmanA"].astype(float)))
    b_map=dict(zip(ret["Sayı"].astype(int),ret["UzmanB"].astype(float)))
    top_map=dict(zip(z["Sayı"].astype(int),z["Top3Kanıt"].astype(float)))

    def final_key(n):
        if n in a_map:
            return (0.72+0.50*ar)*a_map[n] + 0.20*top_map.get(n,0)
        return (0.72+0.50*br)*b_map.get(n,0) + 0.20*top_map.get(n,0)

    t10=sorted(dict.fromkeys(t10),key=final_key,reverse=True)

    meta={
        "expected_carry":float(expected_carry),
        "carry_seats_10":carry_seats,
        "return_seats_10":return_seats,
        "A_rate":ar,
        "B_rate":br,
        "perf_n":int(perf.get("n",0)),
        "A_hits":float(perf.get("A_hits",0.0)),
        "B_hits":float(perf.get("B_hits",0.0)),
    }
    return {"7A":t7a[:7],"7B":t7b[:7],"10":t10[:10],"_meta":meta}

def evaluate_tickets(tickets,actual):
    actual=set(actual)
    rows=[]
    for key,label in [("7A","7'li A"),("7B","7'li B"),("10","10'lu")]:
        t=tickets[key]
        h=sorted(set(t)&actual)
        rows.append({
            "Kupon":label,
            "İsabet":f"{len(h)}/{len(t)}",
            "Tutanlar":" ".join(f"{n:02d}" for n in h),
            "Kupon Sayıları":" ".join(f"{n:02d}" for n in t),
        })
    return pd.DataFrame(rows)

# ============================================================
# UI
# ============================================================
df,source=load_df()
if df.empty:
    st.error("veri.txt bulunamadı.")
    st.stop()

st.caption(
    f"📂 {source} · {len(df)} çekiliş · {df['date'].nunique()} gece · "
    f"son: #{df.iloc[-1]['draw_no']} {df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

token,_,_,_=github_config()
if token:
    st.caption("🔒 Kalıcı GitHub veri.txt kayıt: AÇIK")
else:
    st.warning("⚠️ GitHub token yok; yerel veri.txt kullanılıyor.")

if st.session_state.get("msg"):
    st.success(st.session_state.pop("msg"))

with st.expander("⚡ HIZLI SONUÇ EKLE",expanded=False):
    raw=st.text_area(
        "Sonucu aynen yapıştır",
        height=220,
        placeholder="Çekiliş no: 48821\n13.08.2026 - 23:37\n..."
    )
    if st.button("💾 KAYDET + SONRAKİ KUPONU GELİŞTİR",use_container_width=True):
        try:
            r=parse_result_block(raw)
            pred=st.session_state.get("pred")
            if pred and r["date"]==pred["date"] and r["time"]==pred["target"]:
                st.session_state["eval"]=evaluate_tickets(pred["tickets"],r["numbers"])
                st.session_state["eval_title"]=f"#{r['draw_no']} {r['date']} {r['time']}"
            persist_result(r)
            st.session_state["msg"]=(
                f"✅ #{r['draw_no']} {r['date']} {r['time']} kaydedildi. "
                "Gece karakteri güncellendi ve hedef bir sonraki çekilişe ilerletildi."
            )
            st.rerun()
        except Exception as e:
            st.error(str(e))

target_date,target_slot,target_error=next_live_target(df)
tabs=st.tabs(["🏆 CANLI KUPONLAR","🧬 GECE KARAKTERİ","🔬 7 SİNYAL AYRIŞIMI"])

with tabs[0]:
    if target_slot is None:
        st.warning(target_error)
        st.info("Yeni gece başladığında 23:02 + 23:07 + 23:12 tamamlanınca canlı kupon açılır.")
        st.session_state.pop("pred",None)
    else:
        try:
            tab,gc,expected_carry,hot_pool,cluster=score_candidates(df,target_slot)
            perf=expert_night_performance(df,target_date,target_slot)
            tickets=make_tickets(tab,expected_carry,expert_perf=perf)
            st.session_state["pred"]={
                "date":target_date,
                "target":target_slot,
                "tickets":tickets,
            }

            st.success(f"🎯 CANLI HEDEF: {target_date} {target_slot}")
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Gece karakteri",gc["regime"])
            c2.metric("02→07 taşıma",gc["carry1"])
            c3.metric("07→12 taşıma",gc["carry2"])
            c4.metric("Beklenen taşıma",f"{expected_carry:.1f}/20")

            meta=tickets.get("_meta",{})
            st.caption(
                "Bu hedef son gerçek sonuç dahil edilerek yeniden hesaplandı. "
                f"Bu gecede replay edilen {meta.get('perf_n',0)} hedefte "
                f"Taşıma Uzmanı ort. {meta.get('A_hits',0):.1f}/7, "
                f"Dönüş Uzmanı ort. {meta.get('B_hits',0):.1f}/7. "
                f"10'lu bu nedenle {meta.get('carry_seats_10','-')} taşıma + "
                f"{meta.get('return_seats_10','-')} dönüş koltuğuyla kuruldu."
            )

            st.markdown(f"### 🎯 {target_slot} — 7'Lİ A · TAŞIMA / 6-EL YOL")
            st.code("  ".join(f"{n:02d}" for n in tickets["7A"]))
            st.markdown(f"### 🎯 {target_slot} — 7'Lİ B · DÖNÜŞ / SICAK-KÜME-PATTERN")
            st.code("  ".join(f"{n:02d}" for n in tickets["7B"]))
            st.markdown(f"### 🏆 {target_slot} — 10'LU KONSENSÜS")
            st.code("  ".join(f"{n:02d}" for n in tickets["10"]))

        except Exception as e:
            st.error(f"Kupon üretilemedi: {e}")
            st.session_state.pop("pred",None)

with tabs[1]:
    if target_slot is None:
        st.warning(target_error)
    else:
        try:
            tab,gc,expected_carry,hot_pool,cluster=score_candidates(df,target_slot)
            st.subheader("🧬 Gece karakteri")
            st.write({
                "Rejim":gc["regime"],
                "23:02→23:07 taşıma":gc["carry1"],
                "23:07→23:12 taşıma":gc["carry2"],
                "İlk 3 ortak çekirdek":gc["core"],
                "Ardışık baskı":gc["cons"],
                "Birer atlamalı baskı":gc["step2"],
                "Beklenen hedef taşıması":round(expected_carry,2),
            })
            st.markdown("**Gece ortak sıcak havuzu:** "+(" ".join(f"{n:02d}" for n in sorted(hot_pool)) or "-"))
            st.markdown("**Son 3 çekiliş ortak kümesi:** "+(" ".join(f"{n:02d}" for n in sorted(cluster)) or "-"))
        except Exception as e:
            st.error(str(e))

with tabs[2]:
    if target_slot is None:
        st.warning(target_error)
    else:
        try:
            tab,gc,expected_carry,hot_pool,cluster=score_candidates(df,target_slot)
            show=tab.copy()
            for c in [
                "TaşımaKanıt","DönüşKanıt","SıcakKanıt","KümeKanıt",
                "Step2Kanıt","ArdışıkKanıt","BantKanıt","YolKanıt","İzKanıt","Final"
            ]:
                show[c]=show[c].map(lambda x:round(float(x),3))
            st.dataframe(
                show[[
                    "Sayı","Rol","Kaynakta","6-El Yol","Yaşamİzi","Gap","Streak",
                    "GeceFrekans","SıcakHavuz","OrtakKüme","Step2Destek",
                    "ArdışıkDestek","Bant","TaşımaKanıt","DönüşKanıt",
                    "SıcakKanıt","KümeKanıt","Step2Kanıt","ArdışıkKanıt",
                    "BantKanıt","YolKanıt","İzKanıt","GüçlüKanal","Final"
                ]],
                use_container_width=True,
                hide_index=True
            )
        except Exception as e:
            st.error(str(e))

st.divider()
st.subheader("📊 SON KUPON KARNESİ")
if "eval" in st.session_state:
    st.markdown(f"### {st.session_state.get('eval_title','')}")
    st.dataframe(st.session_state["eval"],use_container_width=True,hide_index=True)
else:
    st.info("Canlı hedef sonucu geldiğinde HIZLI SONUÇ EKLE bölümünden gir; kuponlar otomatik test edilir.")

st.caption(
    "V18’in ana ilkesi: taşıma/dönüş yaşam izi ve bu gecede gerçekten çalışan uzman önceliklidir; ham yüksek skor seçim sebebi değildir; aday en az iki bağımsız kanıttan destek almalıdır. "
    "Bir adayın güçlü kalması için taşıma/dönüş + 6-el yol + gece sıcaklığı + küme/pattern + bant/komşuluk "
    "kanallarından birden fazlasının geçmişte gerçekten isabet üretmiş olması gerekir."
)
