
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
    page_title="Hızlı On — MASTER Tek Beyin",
    page_icon="🧠",
    layout="wide",
)

SLOTS = ["23:02","23:07","23:12","23:17","23:22","23:27",
         "23:32","23:37","23:42","23:47","23:52","23:57"]
BASE = 20/80
DATA_FILE = Path("veri.txt")
SAVE_FILE = Path("master_kupon_kayitlari.csv")

# ------------------------------------------------------------
# VERİ
# ------------------------------------------------------------
def parse_any(text):
    rows=[]
    for raw in str(text).splitlines():
        raw=raw.strip()
        if not raw:
            continue
        no=d=t=None
        nums=[]
        try:
            if "|" in raw:
                p=[x.strip() for x in raw.split("|")]
                no=int(re.findall(r"\d+",p[0])[0])
                m=re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[- ]?\s*(\d{2}:\d{2})",p[1])
                if not m: continue
                d,t=m.group(1),m.group(2)
                nums=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",p[2])]
            elif ";" in raw:
                p=[x.strip() for x in raw.split(";")]
                if len(p)<4: continue
                no=int(p[0]); d=p[1]; t=p[2]
                nums=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",p[3])]
            else:
                m=re.search(r"(\d{4,6}).*?(\d{1,2}\.\d{1,2}\.\d{4}).*?(\d{2}:\d{2})",raw)
                if not m: continue
                no=int(m.group(1)); d=m.group(2); t=m.group(3)
                tail=raw[m.end():]
                nums=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",tail)]
        except Exception:
            continue
        nums=sorted(set(nums))
        if t in SLOTS and len(nums)==20:
            rows.append({"draw_no":int(no),"date":d,"time":t,"numbers":nums})
    df=pd.DataFrame(rows)
    if df.empty: return df
    df["_dt"]=pd.to_datetime(df["date"]+" "+df["time"],format="%d.%m.%Y %H:%M",errors="coerce")
    df=(df.dropna(subset=["_dt"]).sort_values(["_dt","draw_no"])
          .drop_duplicates(["date","time"],keep="last").reset_index(drop=True))
    return df

def github_config():
    """
    GitHub ayarını V18 ile birebir uyumlu okur.
    Desteklenen biçimler:
      [github] token=...  (owner/repo verilmezse eski V18 varsayılanları kullanılır)
      GITHUB_TOKEN=... / GITHUB_REPO=owner/repo
    """
    DEFAULT_OWNER="gozlekakif-alt"
    DEFAULT_REPO="hizli-on-analiz-motoru"
    try:
        # 1) Eski V18 biçimi ÖNCELİKLİ. Eski uygulamada owner/repo opsiyoneldi.
        try:
            gh=st.secrets["github"]
        except Exception:
            gh=None
        if gh is not None:
            token=str(gh.get("token","")).strip()
            owner=str(gh.get("owner",DEFAULT_OWNER)).strip() or DEFAULT_OWNER
            rname=str(gh.get("repo",DEFAULT_REPO)).strip() or DEFAULT_REPO
            repo=(rname if "/" in rname else f"{owner}/{rname}")
            branch=str(gh.get("branch","main")).strip() or "main"
            path=str(gh.get("data_path",gh.get("path","veri.txt"))).strip() or "veri.txt"
            if token:
                return token,repo,branch,path

        # 2) Yeni düz biçim. Repo yazılmamışsa yine eski V18 reposuna düş.
        token=str(st.secrets.get("GITHUB_TOKEN","")).strip()
        repo=str(st.secrets.get("GITHUB_REPO",f"{DEFAULT_OWNER}/{DEFAULT_REPO}")).strip()
        branch=str(st.secrets.get("GITHUB_BRANCH","main")).strip() or "main"
        path=str(st.secrets.get("GITHUB_DATA_PATH","veri.txt")).strip() or "veri.txt"
        if token:
            if "/" not in repo:
                repo=f"{DEFAULT_OWNER}/{repo}"
            return token,repo,branch,path
    except Exception:
        pass
    return "",f"{DEFAULT_OWNER}/{DEFAULT_REPO}","main","veri.txt"

def github_read():
    token,repo,branch,path=github_config()
    if not token or not repo:
        raise RuntimeError("GitHub ayarı yok")
    url=f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    req=urllib.request.Request(url,headers={
        "Authorization":f"Bearer {token}",
        "Accept":"application/vnd.github+json",
        "User-Agent":"hizli-on-v24",
    })
    with urllib.request.urlopen(req,timeout=15) as r:
        obj=json.loads(r.read().decode())
    return base64.b64decode(obj["content"]).decode("utf-8")

def load_data():
    up=st.sidebar.file_uploader("Geçici veri.txt / csv",type=["txt","csv"])
    if up is not None:
        return parse_any(up.getvalue().decode("utf-8",errors="ignore")),f"Yüklenen: {up.name}"
    try:
        txt=github_read()
        df=parse_any(txt)
        if not df.empty: return df,"GitHub veri.txt"
    except Exception:
        pass
    if DATA_FILE.exists():
        return parse_any(DATA_FILE.read_text(encoding="utf-8",errors="ignore")),"Repo veri.txt"
    return pd.DataFrame(),"Veri bulunamadı"

# ------------------------------------------------------------
# YARDIMCI
# ------------------------------------------------------------
def sets_of(df):
    return [set(x) for x in df["numbers"]]

def pct(s):
    x=pd.Series(s,dtype=float)
    if x.nunique()<=1:
        return pd.Series([0.5]*len(x),index=x.index)
    return x.rank(pct=True,method="average")

def smooth(h,n,prior=BASE,k=18):
    return (h+prior*k)/(n+k) if n>=0 else prior

def number_gap(sets,n,cap=15):
    for g,s in enumerate(reversed(sets[-cap:])):
        if n in s: return g
    return cap

def life_bits(sets,n,w=11):
    return "".join("1" if n in s else "0" for s in sets[-w:])

def streak_now(sets,n,cap=8):
    c=0
    for s in reversed(sets[-cap:]):
        if n in s: c+=1
        else: break
    return c

def band(n):
    return (n-1)//10

def adj_support(s,n,dist=1):
    return int(n-dist in s)+int(n+dist in s)

def next_slot(last_time):
    i=SLOTS.index(last_time)
    return SLOTS[(i+1)%len(SLOTS)]

def next_target_label(df):
    last=df.iloc[-1]
    t=next_slot(last["time"])
    d=last["date"]
    if last["time"]=="23:57":
        d=(pd.to_datetime(d,format="%d.%m.%Y")+pd.Timedelta(days=1)).strftime("%d.%m.%Y")
    return d,t,int(last["draw_no"])+1

# ------------------------------------------------------------
# GECE KARAKTERİ
# ------------------------------------------------------------
def night_character(df):
    """
    GÜN BEYNİ V1
    Hedef sonucu görmeden, yalnız o gün hedefe KADAR gerçekleşmiş çekilişleri kullanır.

    0-2 gün içi gözlem: GÜN ÖĞRENİYOR -> uzmanlar nötr/karma davranır.
    3. gözlemden itibaren: KISA HAFIZA / TAŞIMA, UZUN HAFIZA / DÖNÜŞ
    veya KARMA / GEÇİŞ karakteri üretir.
    """
    sets=sets_of(df)
    if len(sets)<8:
        return {
            "label":"GÜN ÖĞRENİYOR / BELİRSİZ","short":0.5,"long":0.5,
            "carry":5.0,"gap2":0.0,"longret":0.0,
            "day_seen":0,"day_phase":"ÖĞRENİYOR","confidence":0.0
        }

    # Bir sonraki hedefin tarihi yalnız geçmişteki son satırdan türetilir.
    target_date,_,_=next_target_label(df)
    day_idx=[i for i in range(len(df)) if str(df.iloc[i]["date"])==str(target_date)]
    day_seen=len(day_idx)

    # Günün ilk çekilişi için de önceki gecenin son çekilişine geçiş ölçülebilir.
    trans=[]; gap2_vals=[]; long_vals=[]
    for i in day_idx:
        if i<=0:
            continue
        prior=sets[:i]
        cur=sets[i]
        trans.append(len(sets[i-1]&cur))
        gap2_vals.append(sum(
            1 for n in cur
            if n not in sets[i-1] and number_gap(prior,n,12)==2
        ))
        long_vals.append(sum(
            1 for n in cur
            if n not in sets[i-1] and number_gap(prior,n,15)>=5
        ))

    carry=float(np.mean(trans)) if trans else 5.0
    g2=float(np.mean(gap2_vals)) if gap2_vals else 0.0
    gl=float(np.mean(long_vals)) if long_vals else 0.0

    # İlk 3 çekiliş tanıma bölgesi: zorla rejim etiketi verme.
    if day_seen < 3:
        return {
            "label":"GÜN ÖĞRENİYOR / BELİRSİZ",
            "short":0.5,"long":0.5,
            "carry":carry,"gap2":g2,"longret":gl,
            "day_seen":day_seen,"day_phase":"ÖĞRENİYOR",
            "confidence":round(day_seen/3.0,3)
        }

    # Gün içi davranış: taşıma + kısa dönüş ile uzun dönüş birbirinden ayrılır.
    short=np.clip((carry+g2)/10.0,0,1)
    long=np.clip((gl+max(0,5-carry))/8.0,0,1)

    # 3. çekilişte karar var ama ihtiyatlı; 4+ çekilişte yetki tam açılır.
    margin=0.10 if day_seen==3 else 0.07
    if short>=0.60 and short>long+margin:
        label="KISA HAFIZA / TAŞIMA"
    elif long>=0.53 and long>short+margin:
        label="UZUN HAFIZA / DÖNÜŞ"
    else:
        label="KARMA / GEÇİŞ"

    confidence=float(np.clip(
        0.55 + 0.10*min(day_seen-3,3) + 0.35*abs(short-long),
        0,1
    ))
    return {
        "label":label,"short":float(short),"long":float(long),
        "carry":carry,"gap2":g2,"longret":gl,
        "day_seen":day_seen,
        "day_phase":"TANINDI" if day_seen>=4 else "İLK KARAR",
        "confidence":confidence
    }

# ------------------------------------------------------------
# GEÇMİŞ AYNI SAAT / MEKANİZMA BAŞARILARI
# ------------------------------------------------------------
def mechanism_history(df,target_time,lookback=240):
    sets=sets_of(df)
    rows=[]
    idxs=[i for i in range(1,len(df)) if df.iloc[i]["time"]==target_time]
    for i in idxs[-lookback:]:
        prior=sets[:i]; actual=sets[i]; src=sets[i-1]
        vals=Counter()
        for n in actual:
            g=number_gap(prior,n,15)
            if n in src: vals["TAŞIMA"]+=1
            if g==1 and n not in src: vals["GAP1"]+=1
            if g==2: vals["GAP2"]+=1
            if g==3: vals["GAP3"]+=1
            if g in (4,5): vals["GAP45"]+=1
            if g>=6: vals["GAP6+"]+=1
        rows.append(vals)
    if not rows:
        return {k:0.25 for k in ["TAŞIMA","GAP1","GAP2","GAP3","GAP45","GAP6+"]}
    avg={k:np.mean([r[k] for r in rows]) for k in ["TAŞIMA","GAP1","GAP2","GAP3","GAP45","GAP6+"]}
    mx=max(avg.values()) or 1
    return {k:0.15+0.85*avg[k]/mx for k in avg}

# ------------------------------------------------------------
# 16 UZMAN
# ------------------------------------------------------------
def expert_table(df,target_time):
    if len(df)<36:
        raise ValueError("En az 36 geçmiş çekiliş gerekir.")
    sets=sets_of(df)
    latest=sets[-1]
    recent2=sets[-2:]
    recent4=sets[-4:]
    recent8=sets[-8:]
    recent12=sets[-12:]
    char=night_character(df)
    mh=mechanism_history(df,target_time)

    # tarih içindeki önceki görünümler: yeni aktivasyon tespiti
    cur_date=df.iloc[-1]["date"]
    day_idx=df.index[df["date"]==cur_date].tolist()
    day_sets=[sets[i] for i in day_idx]
    before_latest_day=day_sets[:-1] if day_sets else []

    # same-slot history
    slot_df=df[df["time"]==target_time].tail(80)
    slot_sets=[set(x) for x in slot_df["numbers"]]
    slot_cnt=Counter()
    for s in slot_sets: slot_cnt.update(s)

    # pair/cluster memory from recent history
    pair_cnt=Counter()
    recent_hist=sets[-min(180,len(sets)):]
    for s in recent_hist:
        a=sorted(s)
        for x,y in combinations(a,2):
            if abs(x-y)<=3:
                pair_cnt[(x,y)]+=1

    # recurring rhythm: each number recent occurrence intervals
    intervals={}
    for n in range(1,81):
        pos=[i for i,s in enumerate(sets[-80:]) if n in s]
        gaps=[b-a for a,b in zip(pos,pos[1:])]
        intervals[n]=gaps[-8:]

    # candidate raw rows
    rows=[]
    for n in range(1,81):
        g=number_gap(sets,n,15)
        present=n in latest
        seen2=sum(n in s for s in recent2)
        seen4=sum(n in s for s in recent4)
        seen8=sum(n in s for s in recent8)
        seen12=sum(n in s for s in recent12)
        bits=life_bits(sets,n,11)
        st=streak_now(sets,n)

        # 1 TAŞIMA
        carry=float(present)*(0.55+0.45*mh["TAŞIMA"])
        # 2 YENİ AKTİVASYON -> TAŞIMA
        new_act=float(present and all(n not in s for s in before_latest_day))*(0.65+0.35*(1.0 if len(before_latest_day)>=2 else 0.5))
        # 3-7 gap motorları
        gap1=float(g==1)*mh["GAP1"]
        gap2=float(g==2)*mh["GAP2"]
        gap3=float(g==3)*mh["GAP3"]
        gap45=float(g in (4,5))*mh["GAP45"]
        gap6=float(g>=6)*mh["GAP6+"]
        # 8 seri -> uyku -> dönüş: geçmişte seri vardı, şimdi uyuyor
        had_streak=any(("11" in life_bits(sets[:j],n,8)) for j in range(max(2,len(sets)-10),len(sets))) if len(sets)>10 else False
        streak_sleep=float((not present) and g>=4 and had_streak)
        # 9 küme taşıma: latest yakın çift/komşu yoğunluğu
        cluster_carry=0.0
        if present:
            cluster_carry=min(1.0,(adj_support(latest,n,1)+0.7*adj_support(latest,n,2))/2.2)
        # 10 küme dönüş: son görüldüğü elde yanında olan güçlü eşlerin bugün aday olması
        cluster_return=0.0
        if not present and g>=1 and g<15:
            srcset=sets[-1-g]
            mates=[m for m in srcset if m!=n and abs(m-n)<=3]
            if mates:
                cluster_return=min(1.0,np.mean([pair_cnt[tuple(sorted((n,m)))] for m in mates])/8.0)
        # 11 aynı yaşam izi: aynı bit dizisine sahip diğer sayıların aktifliği
        same=[]
        for m in range(1,81):
            if m!=n and life_bits(sets,m,8)==life_bits(sets,n,8):
                same.append(m)
        same_life=0.0
        if same:
            same_life=min(1.0,(len(same)/5.0)+0.15*sum(m in latest for m in same))
        # 12 zaman ritmi: son aralığa yakın tekrar
        ig=intervals[n]
        rhythm=0.0
        if len(ig)>=2:
            med=float(np.median(ig))
            rhythm=max(0.0,1.0-abs((g+1)-med)/max(2.0,med))
        # 13 ardışık/+2/atlamalı dizi
        seq=min(1.0,(adj_support(latest,n,1)+0.75*adj_support(latest,n,2)+0.45*adj_support(latest,n,3))/2.2)
        # 14 bant / komşu akış
        b=band(n)
        band_recent=[sum(1 for x in s if band(x)==b) for s in recent4]
        bp=np.mean(band_recent)/2.5 if band_recent else 0
        band_neighbor=min(1.0,0.55*bp+0.45*seq)
        # 15 geçmiş aynı saat fazı
        slot_rate=slot_cnt[n]/max(1,len(slot_sets))
        same_slot=min(1.0,slot_rate/0.38)
        # 16 gece karakter motoru
        if char["label"].startswith("KISA"):
            night=0.55*carry+0.25*gap2+0.20*new_act
        elif char["label"].startswith("UZUN"):
            night=0.20*carry+0.25*gap2+0.25*gap45+0.30*gap6
        else:
            night=0.30*carry+0.25*gap2+0.15*gap3+0.15*gap45+0.15*same_slot

        rows.append({
            "Sayı":n,"Gap":g,"Yaşam İzi":bits,"Gece Görünüm":seen12,
            "TAŞIMA":carry,
            "YENİ AKTİVASYON→TAŞIMA":new_act,
            "GAP-1":gap1,"GAP-2":gap2,"GAP-3":gap3,"GAP-4/5":gap45,"GAP-6+":gap6,
            "SERİ→UYKU→DÖNÜŞ":streak_sleep,
            "KÜME TAŞIMA":cluster_carry,
            "KÜME DÖNÜŞ":cluster_return,
            "AYNI YAŞAM İZİ":same_life,
            "KÜME ZAMAN RİTMİ":rhythm,
            "ARDIŞIK/+2/+3":seq,
            "BANT/KOMŞU":band_neighbor,
            "AYNI SAAT FAZI":same_slot,
            "GECE KARAKTER":night,
        })

    tab=pd.DataFrame(rows)
    experts=[
        "TAŞIMA","YENİ AKTİVASYON→TAŞIMA","GAP-1","GAP-2","GAP-3","GAP-4/5","GAP-6+",
        "SERİ→UYKU→DÖNÜŞ","KÜME TAŞIMA","KÜME DÖNÜŞ","AYNI YAŞAM İZİ",
        "KÜME ZAMAN RİTMİ","ARDIŞIK/+2/+3","BANT/KOMŞU","AYNI SAAT FAZI","GECE KARAKTER"
    ]

    # her uzman kendi dağılımında konuşur; tek ham skor baskın olmaz
    for c in experts:
        tab[c+" R"]=pct(tab[c])

    # dinamik uzman ağırlığı: gece karakterine göre aileler
    w={c:1.0 for c in experts}
    if char["label"].startswith("KISA"):
        for c in ["TAŞIMA","YENİ AKTİVASYON→TAŞIMA","GAP-1","GAP-2","KÜME TAŞIMA"]:
            w[c]=1.35
        for c in ["GAP-6+","SERİ→UYKU→DÖNÜŞ"]:
            w[c]=0.72
    elif char["label"].startswith("UZUN"):
        for c in ["GAP-2","GAP-4/5","GAP-6+","SERİ→UYKU→DÖNÜŞ","KÜME DÖNÜŞ","KÜME ZAMAN RİTMİ"]:
            w[c]=1.35
        w["TAŞIMA"]=0.72
    else:
        for c in ["GAP-2","KÜME DÖNÜŞ","AYNI SAAT FAZI","BANT/KOMŞU"]:
            w[c]=1.18

    # aynı saat tarihsel mekanizma gücü
    w["TAŞIMA"]*=0.75+0.5*mh["TAŞIMA"]
    w["GAP-1"]*=0.75+0.5*mh["GAP1"]
    w["GAP-2"]*=0.75+0.5*mh["GAP2"]
    w["GAP-3"]*=0.75+0.5*mh["GAP3"]
    w["GAP-4/5"]*=0.75+0.5*mh["GAP45"]
    w["GAP-6+"]*=0.75+0.5*mh["GAP6+"]

    weighted=np.zeros(len(tab))
    votes=np.zeros(len(tab))
    strong=np.zeros(len(tab))
    for c in experts:
        r=tab[c+" R"].to_numpy(float)
        weighted += w[c]*r
        votes += (r>=0.68)
        strong += (r>=0.82)
    weighted/=sum(w.values())
    # konsensüs bonusu + tek sinyal cezası
    master=weighted + 0.055*np.clip((votes-3)/8,0,1) + 0.035*np.clip((strong-1)/5,0,1)
    master -= 0.045*(votes<=2)
    tab["Uzman Oy"]=votes.astype(int)
    tab["Güçlü Oy"]=strong.astype(int)
    tab["Ana Puan"]=master
    tab["Ana Yüzdelik"]=pct(tab["Ana Puan"])

    def reasons(r):
        top=sorted(experts,key=lambda c:float(r[c+" R"]),reverse=True)[:5]
        return " + ".join([c for c in top if r[c+" R"]>=0.62]) or top[0]

    tab["Kaynaklar"]=tab.apply(reasons,axis=1)
    tab=tab.sort_values(["Ana Puan","Uzman Oy","Güçlü Oy"],ascending=False).reset_index(drop=True)
    return tab,char,w,mh

# ------------------------------------------------------------
# KUPON SEÇİCİ
# ------------------------------------------------------------
def select_diverse(tab,size,offset=0):
    selected=[]
    band_count=Counter()
    source_count=Counter()
    z=tab.iloc[offset:].copy()
    for _,r in z.iterrows():
        n=int(r["Sayı"]); b=band(n)
        if band_count[b]>=2:
            continue
        # 4/5 kuponlarda aynı mini bölgeye aşırı yığılma olmasın
        if any(abs(n-x)<=1 for x in selected) and sum(abs(n-x)<=2 for x in selected)>=2:
            continue
        selected.append(n); band_count[b]+=1
        for s in str(r["Kaynaklar"]).split(" + "): source_count[s]+=1
        if len(selected)==size: break
    if len(selected)<size:
        for n in tab["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected)==size: break
    return selected

# ------------------------------------------------------------
# V21 CERRAHİ GÖZLEMCİ
# Kaynak dosyalarda V21.21 / V21.22 validation net -1 olduğu için
# varsayılan üretimde swap YAPMAZ; yalnız aday gösterir.
# ------------------------------------------------------------
def surgery_observer(tab,base5):
    z=tab.copy().set_index("Sayı")
    base_rows=z.loc[base5].copy()
    # temporal temizleyici benzeri risk: az bağımsız destek + komşu2 baskısı + orta gap
    risks={}
    protects={}
    for n,r in base_rows.iterrows():
        temporal=(1-float(r["Ana Yüzdelik"])) + 0.20*(int(r["Uzman Oy"])<=3) + 0.10*(int(r["Gap"])>=1)
        cleaner=(1-float(r["Ana Yüzdelik"])) + 0.10*(int(r["Güçlü Oy"])==0)
        protect=0.55*float(r["Ana Yüzdelik"])+0.06*int(r["Uzman Oy"])+0.05*int(r["Güçlü Oy"])
        risks[n]=(temporal+cleaner)/2
        protects[n]=protect
    exit_n=max(risks,key=risks.get)
    outside=[n for n in tab["Sayı"].astype(int).tolist() if n not in base5][:8]
    entry_n=outside[0] if outside else None
    agreement=True
    unprotected=protects[exit_n] < np.median(list(protects.values()))
    strong_entry=False
    if entry_n is not None:
        er=z.loc[entry_n]
        strong_entry=(float(er["Ana Yüzdelik"])>=0.82 and int(er["Uzman Oy"])>=4)
    triple=bool(agreement and unprotected and strong_entry)
    experimental=base5.copy()
    if triple and entry_n is not None:
        experimental[experimental.index(exit_n)]=entry_n
    return {
        "exit":int(exit_n),"entry":int(entry_n) if entry_n else None,
        "triple_lock":triple,
        "base5":base5,
        "experimental5":experimental,
        "note":"V21.21/V21.22 validation geçmişi negatif olduğu için canlı kuponda otomatik swap kapalıdır."
    }

# ------------------------------------------------------------
# TAHMİN
# ------------------------------------------------------------
def predict(df,target_time):
    tab,char,w,mh=expert_table(df,target_time)
    core4=select_diverse(tab,4,0)
    alt4=select_diverse(tab,4,1)
    core5=select_diverse(tab,5,0)
    alt5=select_diverse(tab,5,1)
    surg=surgery_observer(tab,core5)
    return {
        "tab":tab,"char":char,"weights":w,"mech_hist":mh,
        "core4":core4,"alt4":alt4,"core5":core5,"alt5":alt5,"surgery":surg
    }

# ------------------------------------------------------------
# GERÇEK KÖR WALK-FORWARD
# Her hedef için yalnız HEDEFTEN ÖNCEKİ satırlar kullanılır.
# ------------------------------------------------------------
def blind_test(df,ntest=40,min_train=120):
    rows=[]
    start=max(min_train,len(df)-ntest)
    for i in range(start,len(df)):
        train=df.iloc[:i].reset_index(drop=True)
        if len(train)<min_train: continue
        target=df.iloc[i]
        try:
            p=predict(train,target["time"])
        except Exception:
            continue
        actual=set(target["numbers"])
        row={
            "Çekiliş":int(target["draw_no"]),
            "Tarih":target["date"],
            "Saat":target["time"],
            "Gece":p["char"]["label"],
            "4 Çekirdek":len(set(p["core4"])&actual),
            "4 Alternatif":len(set(p["alt4"])&actual),
            "5 Çekirdek":len(set(p["core5"])&actual),
            "5 Alternatif":len(set(p["alt5"])&actual),
            "Havuz12":len(set(p["tab"].head(12)["Sayı"].astype(int))&actual),
            "Havuz16":len(set(p["tab"].head(16)["Sayı"].astype(int))&actual),
            "Cerrahi5":len(set(p["surgery"]["experimental5"])&actual),
            "CerrahiAçıldı":int(p["surgery"]["triple_lock"]),
        }
        rows.append(row)
    return pd.DataFrame(rows)

def mechanism_blind_audit(df,ntest=50,min_train=120):
    experts=[
        "TAŞIMA","YENİ AKTİVASYON→TAŞIMA","GAP-1","GAP-2","GAP-3","GAP-4/5","GAP-6+",
        "SERİ→UYKU→DÖNÜŞ","KÜME TAŞIMA","KÜME DÖNÜŞ","AYNI YAŞAM İZİ",
        "KÜME ZAMAN RİTMİ","ARDIŞIK/+2/+3","BANT/KOMŞU","AYNI SAAT FAZI","GECE KARAKTER"
    ]
    agg={e:{"n":0,"hits":0,"size":0} for e in experts}
    start=max(min_train,len(df)-ntest)
    for i in range(start,len(df)):
        train=df.iloc[:i].reset_index(drop=True); target=df.iloc[i]
        if len(train)<min_train: continue
        try:
            tab,_,_,_=expert_table(train,target["time"])
        except Exception:
            continue
        actual=set(target["numbers"])
        for e in experts:
            # her uzman kendi Top-5 adayını konuşur
            top=tab.sort_values(e+" R",ascending=False).head(5)["Sayı"].astype(int).tolist()
            agg[e]["n"]+=1; agg[e]["hits"]+=len(set(top)&actual); agg[e]["size"]+=5
    out=[]
    for e,a in agg.items():
        if not a["n"]: continue
        avg=a["hits"]/a["n"]
        out.append({
            "Uzman":e,"Test":a["n"],"Top5 Ort. İsabet":avg,
            "Rastgele Beklenti":1.25,
            "Lift":avg-1.25
        })
    return pd.DataFrame(out).sort_values("Lift",ascending=False).reset_index(drop=True)


# ------------------------------------------------------------
# V25 — MERKEZ BEYİN + KALICI ÖĞRENME + SONUÇ GERİ BESLEME
# ------------------------------------------------------------
EXPERTS=[
    "TAŞIMA","YENİ AKTİVASYON→TAŞIMA","GAP-1","GAP-2","GAP-3","GAP-4/5","GAP-6+",
    "SERİ→UYKU→DÖNÜŞ","KÜME TAŞIMA","KÜME DÖNÜŞ","AYNI YAŞAM İZİ",
    "KÜME ZAMAN RİTMİ","ARDIŞIK/+2/+3","BANT/KOMŞU","AYNI SAAT FAZI","GECE KARAKTER"
]
BRAIN_FILE=Path("v26_merkez_beyin.json")
EVAL_FILE=Path("v26_sonuc_karnesi.csv")


def _default_brain():
    return {
        "version":"V25",
        "experts":{e:{"tests":0,"hit_total":0.0,"last_hits":[],"positive":0,"zero":0} for e in EXPERTS},
        "surgery":{"tests":0,"triggered":0,"base_hit_total":0.0,"exp_hit_total":0.0,
                   "positive":0,"negative":0,"neutral":0,"approved":False},
        "evaluated_draws":[],
        "updated_at":""
    }


def _merge_brain(obj):
    base=_default_brain()
    if not isinstance(obj,dict): return base
    for e in EXPERTS:
        if isinstance(obj.get("experts",{}).get(e),dict):
            base["experts"][e].update(obj["experts"][e])
    if isinstance(obj.get("surgery"),dict): base["surgery"].update(obj["surgery"])
    if isinstance(obj.get("evaluated_draws"),list): base["evaluated_draws"]=obj["evaluated_draws"][-500:]
    base["updated_at"]=str(obj.get("updated_at",""))
    return base


def github_read_path(path):
    token,repo,branch,_=github_config()
    if not token or not repo: raise RuntimeError("GitHub ayarı yok")
    url=f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    req=urllib.request.Request(url,headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","User-Agent":"hizli-on-v25"})
    with urllib.request.urlopen(req,timeout=15) as r: obj=json.loads(r.read().decode())
    return base64.b64decode(obj["content"]).decode("utf-8"),obj.get("sha")


def github_write_path(path,text,message="V25 merkez beyin güncelle"):
    token,repo,branch,_=github_config()
    if not token or not repo: raise RuntimeError("GitHub ayarı yok")
    sha=None
    try: _,sha=github_read_path(path)
    except Exception: pass
    url=f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    payload={"message":message,"content":base64.b64encode(text.encode("utf-8")).decode(),"branch":branch}
    if sha: payload["sha"]=sha
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),method="PUT",headers={
        "Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","Content-Type":"application/json","User-Agent":"hizli-on-v25"})
    with urllib.request.urlopen(req,timeout=20) as r: return json.loads(r.read().decode())


def load_brain():
    try:
        txt,_=github_read_path(str(st.secrets.get("GITHUB_BRAIN_PATH","v26_merkez_beyin.json")))
        return _merge_brain(json.loads(txt)),"GitHub merkez beyin"
    except Exception:
        pass
    if BRAIN_FILE.exists():
        try: return _merge_brain(json.loads(BRAIN_FILE.read_text(encoding="utf-8"))),"Yerel merkez beyin"
        except Exception: pass
    return _default_brain(),"Yeni merkez beyin"


def save_brain(brain):
    brain=_merge_brain(brain); brain["updated_at"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txt=json.dumps(brain,ensure_ascii=False,indent=2)
    BRAIN_FILE.write_text(txt,encoding="utf-8")
    try:
        path=str(st.secrets.get("GITHUB_BRAIN_PATH","v26_merkez_beyin.json"))
        github_write_path(path,txt,"V25 merkez beyin öğrenme güncellemesi")
        return "GitHub + yerel"
    except Exception:
        return "Yerel oturum"


def brain_weights(brain):
    """Top-5 rastgele beklenti 1.25. Küçük örneklemde ağırlık agresif değişmez."""
    out={}
    prior_tests=16.0
    prior_avg=1.25
    for e in EXPERTS:
        x=brain.get("experts",{}).get(e,{})
        n=float(x.get("tests",0)); h=float(x.get("hit_total",0.0))
        avg=(h+prior_tests*prior_avg)/(n+prior_tests)
        factor=(avg/prior_avg)**0.70 if avg>0 else 0.72
        # veri azsa merkez beyin temkinli
        confidence=min(1.0,n/35.0)
        factor=1.0+confidence*(factor-1.0)
        out[e]=float(np.clip(factor,0.72,1.35))
    return out


def expert_table_brain(df,target_time,brain=None):
    tab,char,w,mh=expert_table(df,target_time)
    bw=brain_weights(brain or _default_brain())
    # Eski gece/rejim ağırlığını koru, öğrenilmiş merkez katsayısını üstüne bindir.
    w2={e:float(w.get(e,1.0))*float(bw.get(e,1.0)) for e in EXPERTS}
    weighted=np.zeros(len(tab)); votes=np.zeros(len(tab)); strong=np.zeros(len(tab))
    for e in EXPERTS:
        r=tab[e+" R"].to_numpy(float)
        weighted += w2[e]*r
        votes += (r>=0.68); strong += (r>=0.82)
    weighted/=max(1e-9,sum(w2.values()))
    master=weighted + 0.060*np.clip((votes-3)/8,0,1) + 0.040*np.clip((strong-1)/5,0,1)
    master -= 0.050*(votes<=2)
    tab=tab.copy()
    tab["Uzman Oy"]=votes.astype(int); tab["Güçlü Oy"]=strong.astype(int)
    tab["Ana Puan"]=master; tab["Ana Yüzdelik"]=pct(tab["Ana Puan"])
    def reasons(r):
        top=sorted(EXPERTS,key=lambda c:float(r[c+" R"])*w2[c],reverse=True)[:6]
        return " + ".join([c for c in top if r[c+" R"]>=0.62]) or top[0]
    tab["Kaynaklar"]=tab.apply(reasons,axis=1)
    tab=tab.sort_values(["Ana Puan","Uzman Oy","Güçlü Oy"],ascending=False).reset_index(drop=True)
    return tab,char,w2,mh,bw


def surgery_gate(brain):
    s=brain.get("surgery",{})
    trig=int(s.get("triggered",0)); pos=int(s.get("positive",0)); neg=int(s.get("negative",0))
    base=float(s.get("base_hit_total",0)); exp=float(s.get("exp_hit_total",0))
    delta=(exp-base)/max(1,trig)
    approved=bool(trig>=20 and delta>=0.08 and pos>=max(3,neg+1))
    return approved,delta


def predict(df,target_time,brain=None):
    brain=brain or _default_brain()
    tab,char,w,mh,bw=expert_table_brain(df,target_time,brain)
    core4=select_diverse(tab,4,0); alt4=select_diverse(tab,4,1)
    core5=select_diverse(tab,5,0); alt5=select_diverse(tab,5,1)
    surg=surgery_observer(tab,core5)
    approved,delta=surgery_gate(brain)
    surg["brain_approved"]=approved; surg["mean_delta"]=delta
    surg["live5"]=surg["experimental5"] if (approved and surg["triple_lock"]) else core5
    return {"tab":tab,"char":char,"weights":w,"brain_weights":bw,"mech_hist":mh,
            "core4":core4,"alt4":alt4,"core5":core5,"alt5":alt5,"surgery":surg}


def make_snapshot(p,target_draw,target_date,target_time):
    expert_top5={e:p["tab"].sort_values(e+" R",ascending=False).head(5)["Sayı"].astype(int).tolist() for e in EXPERTS}
    top_rows=[]
    for _,r in p["tab"].head(30).iterrows():
        top_rows.append({"Sayı":int(r["Sayı"]),"Ana Puan":float(r["Ana Puan"]),"Uzman Oy":int(r["Uzman Oy"]),
                         "Güçlü Oy":int(r["Güçlü Oy"]),"Gap":int(r["Gap"]),"Yaşam İzi":str(r["Yaşam İzi"]),
                         "Kaynaklar":str(r["Kaynaklar"])})
    return {
        "target_draw":int(target_draw),"target_date":str(target_date),"target_time":str(target_time),
        "night_character":p["char"]["label"],"core4":p["core4"],"alt4":p["alt4"],
        "core5":p["core5"],"alt5":p["alt5"],"live5":p["surgery"]["live5"],
        "pool12":p["tab"].head(12)["Sayı"].astype(int).tolist(),
        "pool16":p["tab"].head(16)["Sayı"].astype(int).tolist(),
        "pool30":p["tab"].head(30)["Sayı"].astype(int).tolist(),
        "expert_top5":expert_top5,"top_rows":top_rows,
        "surgery":{"base5":p["surgery"]["base5"],"experimental5":p["surgery"]["experimental5"],
                   "triple_lock":bool(p["surgery"]["triple_lock"]),"exit":p["surgery"]["exit"],"entry":p["surgery"]["entry"]}
    }


def eval_snapshot(snapshot,actual):
    actual=set(map(int,actual))
    labels=[
        ("core4","4 Çekirdek"),("alt4","4 Alternatif"),
        ("core5","5 Çekirdek"),("alt5","5 Alternatif"),("live5","Canlı5"),
        ("v5_dna4","V5 DNA4"),("v5_dna5","V5 DNA5"),
        ("v6_akor4","V6 Akor4"),("v6_akor5","V6 Akor5"),
        ("v7_final4","V7 Final4"),("v7_final5","V7 Final5"),
        ("v8_final4","V8 Final4"),("v8_final5","V8 Final5"),
        ("v9_final4","V9.5 Final4"),("v9_final5","V9.5 Final5"),
        ("v10_final4","V10 Yaşam Final4"),("v10_final5","V10 Yaşam Final5"),
        ("independent5","Bağımsız5 — V9.5"),
        ("pool12","Havuz12"),("pool16","MASTER Havuz16"),
        ("pool16_dna","DNA Havuz16"),("pool16_akor","Akor Havuz16"),
    ]
    rows=[]
    for key,label in labels:
        arr=list(map(int,snapshot.get(key,[]) or []))
        if not arr: continue
        hit=sorted(set(arr)&actual); miss=sorted(set(arr)-actual)
        rows.append({"Kupon/Havuz":label,"Boyut":len(arr),"Doğru":len(hit),
                     "Kaçta Kaç":f"{len(hit)}/{len(arr)}",
                     "Tuttu":"-".join(map(str,hit)),"Kaçtı":"-".join(map(str,miss)),
                     "Seçim":"-".join(map(str,arr))})
    summary=pd.DataFrame(rows)
    ex=[]
    for e,arr in snapshot.get("expert_top5",{}).items():
        hit=sorted(set(map(int,arr))&actual)
        ex.append({"Uzman":e,"Top5 Doğru":len(hit),"Doğrular":"-".join(map(str,hit))})
    expert_df=pd.DataFrame(ex).sort_values(["Top5 Doğru","Uzman"],ascending=[False,True]) if ex else pd.DataFrame()
    detail=[]
    for r in snapshot.get("top_rows",[]):
        d=dict(r); d["Gerçekte Çıktı"]="EVET" if int(r["Sayı"]) in actual else "HAYIR"; detail.append(d)
    detail_df=pd.DataFrame(detail)
    return summary,expert_df,detail_df


def update_brain_from_result(brain,snapshot,actual):
    brain=_merge_brain(brain); actual=set(map(int,actual)); draw=int(snapshot.get("target_draw",0))
    if draw in set(map(int,brain.get("evaluated_draws",[]))):
        return brain,False,"Bu çekiliş merkez beyne daha önce işlendi."
    for e,arr in snapshot.get("expert_top5",{}).items():
        if e not in brain["experts"]: continue
        h=len(set(map(int,arr))&actual); x=brain["experts"][e]
        x["tests"]=int(x.get("tests",0))+1; x["hit_total"]=float(x.get("hit_total",0))+h
        lh=list(x.get("last_hits",[])); lh.append(h); x["last_hits"]=lh[-40:]
        if h>1: x["positive"]=int(x.get("positive",0))+1
        if h==0: x["zero"]=int(x.get("zero",0))+1
    su=snapshot.get("surgery",{})
    if su:
        s=brain["surgery"]; s["tests"]=int(s.get("tests",0))+1
        if bool(su.get("triple_lock")):
            b=len(set(map(int,su.get("base5",[])))&actual); e=len(set(map(int,su.get("experimental5",[])))&actual)
            s["triggered"]=int(s.get("triggered",0))+1; s["base_hit_total"]=float(s.get("base_hit_total",0))+b; s["exp_hit_total"]=float(s.get("exp_hit_total",0))+e
            if e>b: s["positive"]=int(s.get("positive",0))+1
            elif e<b: s["negative"]=int(s.get("negative",0))+1
            else: s["neutral"]=int(s.get("neutral",0))+1
        s["approved"],_=surgery_gate(brain)
    brain["evaluated_draws"]=(list(brain.get("evaluated_draws",[]))+[draw])[-500:]
    brain["updated_at"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return brain,True,"Öğrenme merkez beyne işlendi."


def parse_result_blob(text):
    text=str(text)
    m_no=re.search(r"(?:Çekiliş\s*no\s*:?\s*)?(\d{4,6})",text,re.I)
    m_dt=re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})",text)
    nums=[]
    if m_dt:
        tail=text[m_dt.end():]
        nums=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",tail)]
    nums=sorted(set(nums))
    if not m_no or not m_dt or len(nums)!=20: return None
    return {"draw_no":int(m_no.group(1)),"date":m_dt.group(1),"time":m_dt.group(2),"numbers":nums}


def save_eval_log(snapshot,actual,summary):
    rows=[]
    for _,r in summary.iterrows():
        kol=r.get("Kol",r.get("Kupon/Havuz",""))
        dogru=int(r.get("Doğru",0))
        tuttu=r.get("Tuttu","")
        secim=r.get("Seçim","")
        rows.append({"draw_no":snapshot.get("target_draw"),"date":snapshot.get("target_date"),"time":snapshot.get("target_time"),
                     "night":snapshot.get("night_character"),"kol":kol,"dogru":dogru,"tuttu":tuttu,
                     "secim":secim,"saved_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    new=pd.DataFrame(rows)
    if EVAL_FILE.exists():
        try: old=pd.read_csv(EVAL_FILE)
        except Exception: old=pd.DataFrame()
        new=pd.concat([old,new],ignore_index=True).drop_duplicates(["draw_no","kol"],keep="last")
    new.to_csv(EVAL_FILE,index=False,encoding="utf-8-sig")
    try:
        path=str(st.secrets.get("GITHUB_EVAL_PATH","v26_sonuc_karnesi.csv"))
        github_write_path(path,new.to_csv(index=False),"V26 sonuç karnesi güncelle")
    except Exception: pass


def blind_test(df,ntest=40,min_train=120):
    """Sıralı öğrenen kör test: her hedefte önce tahmin, sonra sonuç görülür ve beyin sadece SONRA güncellenir."""
    rows=[]; simbrain=_default_brain(); start=max(min_train,len(df)-ntest)
    for i in range(start,len(df)):
        train=df.iloc[:i].reset_index(drop=True)
        if len(train)<min_train: continue
        target=df.iloc[i]
        try: p=predict(train,target["time"],simbrain)
        except Exception: continue
        actual=set(target["numbers"]); snap=make_snapshot(p,int(target["draw_no"]),target["date"],target["time"])
        rows.append({
            "Çekiliş":int(target["draw_no"]),"Tarih":target["date"],"Saat":target["time"],"Gece":p["char"]["label"],
            "4 Çekirdek":len(set(p["core4"])&actual),"4 Alternatif":len(set(p["alt4"])&actual),
            "5 Çekirdek":len(set(p["core5"])&actual),"5 Alternatif":len(set(p["alt5"])&actual),
            "Canlı5":len(set(p["surgery"]["live5"])&actual),"Havuz12":len(set(p["tab"].head(12)["Sayı"].astype(int))&actual),
            "Havuz16":len(set(p["tab"].head(16)["Sayı"].astype(int))&actual),
            "Cerrahi5":len(set(p["surgery"]["experimental5"])&actual),"CerrahiAçıldı":int(p["surgery"]["triple_lock"]),
            "CerrahiOnaylı":int(p["surgery"]["brain_approved"])
        })
        simbrain,_,_=update_brain_from_result(simbrain,snap,actual)
    return pd.DataFrame(rows),simbrain


def mechanism_blind_audit(df,ntest=50,min_train=120):
    agg={e:{"n":0,"hits":0} for e in EXPERTS}; start=max(min_train,len(df)-ntest)
    for i in range(start,len(df)):
        train=df.iloc[:i].reset_index(drop=True); target=df.iloc[i]
        if len(train)<min_train: continue
        try: tab,_,_,_,_=expert_table_brain(train,target["time"],_default_brain())
        except Exception: continue
        actual=set(target["numbers"])
        for e in EXPERTS:
            top=tab.sort_values(e+" R",ascending=False).head(5)["Sayı"].astype(int).tolist()
            agg[e]["n"]+=1; agg[e]["hits"]+=len(set(top)&actual)
    out=[]
    for e,a in agg.items():
        if not a["n"]: continue
        avg=a["hits"]/a["n"]
        out.append({"Uzman":e,"Test":a["n"],"Top5 Ort. İsabet":avg,"Rastgele Beklenti":1.25,"Lift":avg-1.25})
    return pd.DataFrame(out).sort_values("Lift",ascending=False).reset_index(drop=True)



# ============================================================
# V26 — MİKRO UZMAN + İKİ AŞAMALI ORTAK BEYİN
# ============================================================
# V26'nın ana farkı:
# 1) Uzman kendi alanı dışında oy vermez.
# 2) Aynı ham fikrin farklı isimlerle çoğalması "bağımsız kanıt" sayılmaz.
# 3) 80 -> Havuz16 ve Havuz16 -> 4/5 iki ayrı karar problemidir.
# 4) Skor yalnız sıralama yardımcısıdır; aday olmak için rol içi mikro koşul gerekir.
# 5) Cerrahi son katmandır; havuz üretmez ve kanıtlanmadan canlı kuponu değiştirmez.

FAMILIES = {
    "TAŞIMA":"CARRY",
    "YENİ AKTİVASYON→TAŞIMA":"CARRY",
    "GAP-1":"RETURN",
    "GAP-2":"RETURN",
    "GAP-3":"RETURN",
    "GAP-4/5":"RETURN",
    "GAP-6+":"RETURN",
    "SERİ→UYKU→DÖNÜŞ":"RETURN",
    "KÜME TAŞIMA":"CLUSTER",
    "KÜME DÖNÜŞ":"CLUSTER",
    "AYNI YAŞAM İZİ":"TRACE",
    "KÜME ZAMAN RİTMİ":"TRACE",
    "ARDIŞIK/+2/+3":"STRUCTURE",
    "BANT/KOMŞU":"STRUCTURE",
    "AYNI SAAT FAZI":"TIME",
    "GECE KARAKTER":"REGIME",
}

def _life_state(bits, gap, present):
    bits=str(bits)
    tail=bits[-4:]
    if present:
        if tail.endswith("11"):
            return "DEVAM/SERİ"
        if tail.endswith("01"):
            return "YENİ/GERİ AKTİF"
        return "AKTİF"
    if gap == 1:
        return "1 EL DİNLENME"
    if gap == 2:
        return "2 EL DİNLENME"
    if gap in (3,4):
        return "3-4 EL DİNLENME"
    if gap in (5,6,7):
        return "5-7 EL UYKU"
    if gap >= 8:
        return "UZUN UYKU"
    return "PASİF"

def _role_gate(row, expert):
    g=int(row["Gap"])
    # Uzman kendi alanı dışında kesinlikle oy vermez.
    if expert=="TAŞIMA":
        return g==0
    if expert=="YENİ AKTİVASYON→TAŞIMA":
        return float(row[expert])>0
    if expert=="GAP-1":
        return g==1
    if expert=="GAP-2":
        return g==2
    if expert=="GAP-3":
        return g==3
    if expert=="GAP-4/5":
        return g in (4,5)
    if expert=="GAP-6+":
        return g>=6
    if expert=="SERİ→UYKU→DÖNÜŞ":
        return float(row[expert])>0
    if expert in ("KÜME TAŞIMA","KÜME DÖNÜŞ","AYNI YAŞAM İZİ",
                  "KÜME ZAMAN RİTMİ","ARDIŞIK/+2/+3","BANT/KOMŞU",
                  "AYNI SAAT FAZI","GECE KARAKTER"):
        return float(row[expert])>0.05
    return False

def _micro_score(row, expert):
    """Rol içi mikro inceleme. Skor adaylık vermez; gate açıldıktan sonra ayrıştırır."""
    base=float(row.get(expert+" R",0.0))
    g=int(row["Gap"])
    life=str(row["Yaşam İzi"])
    seen=int(row.get("Gece Görünüm",0))
    rhythm=float(row.get("KÜME ZAMAN RİTMİ R",0.0))
    same=float(row.get("AYNI YAŞAM İZİ R",0.0))
    slot=float(row.get("AYNI SAAT FAZI R",0.0))
    cluster=max(float(row.get("KÜME TAŞIMA R",0.0)),float(row.get("KÜME DÖNÜŞ R",0.0)))
    seq=float(row.get("ARDIŞIK/+2/+3 R",0.0))
    bandr=float(row.get("BANT/KOMŞU R",0.0))
    night=float(row.get("GECE KARAKTER R",0.0))

    s=0.50*base
    if expert=="TAŞIMA":
        s += 0.13*cluster + 0.11*seq + 0.10*slot + 0.08*night + 0.04*min(seen/5,1)
        if life.endswith("11"): s += 0.06
    elif expert=="YENİ AKTİVASYON→TAŞIMA":
        s += 0.16*slot + 0.14*cluster + 0.12*night + 0.08*seq
        if seen<=1: s += 0.06
    elif expert=="GAP-1":
        s += 0.12*rhythm + 0.10*same + 0.10*cluster + 0.09*slot + 0.09*night
    elif expert=="GAP-2":
        s += 0.15*rhythm + 0.12*same + 0.11*cluster + 0.08*slot + 0.04*seq
    elif expert=="GAP-3":
        s += 0.15*rhythm + 0.12*same + 0.10*slot + 0.08*cluster + 0.05*bandr
    elif expert=="GAP-4/5":
        s += 0.15*same + 0.14*rhythm + 0.10*slot + 0.07*cluster + 0.04*bandr
    elif expert=="GAP-6+":
        s += 0.17*same + 0.16*rhythm + 0.10*slot + 0.05*cluster + 0.02*night
        if g>=8: s += 0.03
    elif expert=="SERİ→UYKU→DÖNÜŞ":
        s += 0.16*rhythm + 0.13*same + 0.10*slot + 0.07*cluster + 0.04*night
    elif expert in ("KÜME TAŞIMA","KÜME DÖNÜŞ"):
        s += 0.16*seq + 0.13*rhythm + 0.11*same + 0.07*bandr + 0.03*slot
    elif expert=="AYNI YAŞAM İZİ":
        s += 0.18*rhythm + 0.12*cluster + 0.10*slot + 0.06*night + 0.04*seq
    elif expert=="KÜME ZAMAN RİTMİ":
        s += 0.16*same + 0.13*cluster + 0.10*slot + 0.07*night + 0.04*seq
    elif expert=="ARDIŞIK/+2/+3":
        s += 0.16*cluster + 0.13*bandr + 0.09*slot + 0.07*rhythm + 0.05*night
    elif expert=="BANT/KOMŞU":
        s += 0.16*seq + 0.12*cluster + 0.09*slot + 0.07*rhythm + 0.06*night
    elif expert=="AYNI SAAT FAZI":
        s += 0.14*rhythm + 0.12*same + 0.09*cluster + 0.08*night + 0.07*bandr
    else:  # GECE KARAKTER
        s += 0.13*slot + 0.11*rhythm + 0.10*cluster + 0.08*same + 0.08*seq
    return float(s)

def _rank_within_gate(tab, expert):
    eligible=tab.apply(lambda r:_role_gate(r,expert),axis=1)
    score=tab.apply(lambda r:_micro_score(r,expert) if _role_gate(r,expert) else 0.0,axis=1)
    out=pd.Series(0.0,index=tab.index)
    idx=score[eligible].index
    if len(idx):
        vals=score.loc[idx]
        if vals.nunique()<=1:
            out.loc[idx]=0.70
        else:
            out.loc[idx]=vals.rank(pct=True,method="average")
    return eligible.astype(int),score,out

def expert_table_brain(df,target_time,brain=None):
    # V25 ham uzman tablosunu kullan, fakat V26'da her uzman kendi rol kapısından geçer.
    tab,char,w,mh=expert_table(df,target_time)
    brain=brain or _default_brain()
    bw=brain_weights(brain)

    micro_weights={}
    for e in EXPERTS:
        gate,ms,mr=_rank_within_gate(tab,e)
        tab[e+" Yetkili"]=gate
        tab[e+" Mikro"]=ms
        # V26'da e+" R" artık rol-içi mikro yüzdeliktir.
        tab[e+" R"]=mr
        micro_weights[e]=float(w.get(e,1.0))*float(bw.get(e,1.0))

    # Aile bazlı bağımsız kanıt: aynı ailede 4 motor oy verse bile 4 bağımsız kanıt sayılmaz.
    fams=sorted(set(FAMILIES.values()))
    for fam in fams:
        es=[e for e in EXPERTS if FAMILIES[e]==fam]
        arr=np.vstack([tab[e+" R"].to_numpy(float) for e in es])
        tab["Aile "+fam]=arr.max(axis=0)

    family_cols=["Aile "+f for f in fams]
    tab["Bağımsız Aile"]=sum((tab[c]>=0.68).astype(int) for c in family_cols)
    tab["Güçlü Aile"]=sum((tab[c]>=0.82).astype(int) for c in family_cols)
    tab["Uzman Oy"]=sum((tab[e+" R"]>=0.68).astype(int) for e in EXPERTS)
    tab["Güçlü Oy"]=sum((tab[e+" R"]>=0.82).astype(int) for e in EXPERTS)

    # Merkez beyin: ağırlıklı ortalamadan ziyade bağımsız aile konsensüsü.
    # Her ailenin yalnız en güçlü kanıtı kullanılır.
    fam_matrix=np.vstack([tab[c].to_numpy(float) for c in family_cols]).T
    fam_sorted=np.sort(fam_matrix,axis=1)[:,::-1]
    primary=(0.34*fam_sorted[:,0] + 0.24*fam_sorted[:,1] +
             0.17*fam_sorted[:,2] + 0.11*fam_sorted[:,3] +
             0.08*fam_sorted[:,4] + 0.04*fam_sorted[:,5] +
             0.02*fam_sorted[:,6])
    # 3+ bağımsız aileyi ödüllendir, tek aile parlamasını frenle.
    master=primary + 0.055*np.clip((tab["Bağımsız Aile"].to_numpy()-2)/4,0,1)
    master += 0.035*np.clip((tab["Güçlü Aile"].to_numpy()-1)/3,0,1)
    master -= 0.070*(tab["Bağımsız Aile"].to_numpy()<=1)

    tab["Ana Puan"]=master
    tab["Ana Yüzdelik"]=pct(tab["Ana Puan"])
    tab["Yaşam Durumu"]=tab.apply(lambda r:_life_state(r["Yaşam İzi"],int(r["Gap"]),int(r["Gap"])==0),axis=1)

    def reasons(r):
        candidates=[]
        for e in EXPERTS:
            if int(r[e+" Yetkili"]) and float(r[e+" R"])>=0.62:
                candidates.append((float(r[e+" R"]),e))
        candidates=sorted(candidates,reverse=True)
        # Aynı aileden en fazla 1 açıklama; gerçekten farklı kanıtlar görünür.
        used=set(); out=[]
        for _,e in candidates:
            fam=FAMILIES[e]
            if fam in used: continue
            used.add(fam); out.append(e)
            if len(out)>=6: break
        return " + ".join(out) if out else "ROL İÇİ KANIT ZAYIF"

    tab["Kaynaklar"]=tab.apply(reasons,axis=1)
    tab=tab.sort_values(["Bağımsız Aile","Güçlü Aile","Ana Puan"],ascending=False).reset_index(drop=True)
    return tab,char,micro_weights,mh,bw


# ============================================================
# MASTER — DERİN MİKRO MOTOR KATMANI
# 1 Mayıs kadavra çalışmasında sabitlenen sözleşmeler:
# rejim -> bant yaşam/göç -> yaşam yolu -> carry/return survival
# -> küme ağı -> ikiz ayırıcı -> negatif kanıt -> Tek Beyin.
# ============================================================

def band_label(n):
    lo=((int(n)-1)//10)*10+1
    return f"{lo}-{lo+9}"

def _band_counts(sets, last=6):
    use=sets[-last:]
    out=[]
    for s in use:
        out.append([sum(1 for n in s if band(n)==b) for b in range(8)])
    return out

def _recent_pair_counter(sets, lookback=80):
    pc=Counter()
    for s in sets[-lookback:]:
        a=sorted(s)
        for x,y in combinations(a,2):
            pc[(x,y)] += 1
    return pc

def _number_positions(sets,n,lookback=80):
    start=max(0,len(sets)-lookback)
    return [i for i,s in enumerate(sets[start:],start=start) if n in s]

def _life_event_path(sets,n,w=10):
    seq=sets[-w:]
    events=[]
    prev=False
    gap=0
    for s in seq:
        now=n in s
        if now:
            if prev: events.append("TAŞI")
            elif gap==0: events.append("AKTİF")
            elif gap==1: events.append("DÖN1")
            elif gap==2: events.append("DÖN2")
            elif gap<=4: events.append("DÖN3/4")
            else: events.append("UZUN_DÖN")
            gap=0
        else:
            gap+=1
            if prev: events.append("SÖN")
            else: events.append("UYKU")
        prev=now
    return ">".join(events[-6:])

def advanced_micro_overlay(df,target_time,tab,char):
    sets=sets_of(df)
    latest=sets[-1]
    prev=sets[-2] if len(sets)>=2 else set()
    prev2=sets[-3] if len(sets)>=3 else set()
    bc=_band_counts(sets,6)
    pc=_recent_pair_counter(sets,80)

    # band phase from only information available before target
    current_counts=bc[-1] if bc else [0]*8
    prev_counts=bc[-2] if len(bc)>=2 else [0]*8
    prev2_counts=bc[-3] if len(bc)>=3 else [0]*8

    rows=[]
    for _,r in tab.iterrows():
        n=int(r["Sayı"]); b=band(n); g=int(r["Gap"])
        c=current_counts[b]; p1=prev_counts[b]; p2=prev2_counts[b]

        # BAND LIFE / MIGRATION
        band_reactivation = 1.0 if p1==0 and c>0 else (0.65 if p2==0 and p1>0 and c>0 else 0.0)
        band_burst = min(1.0, c/5.0)
        band_narrow = 1.0 if p1>=4 and 0<c<=3 else 0.0
        band_alive = min(1.0,(c + 0.65*p1 + 0.35*p2)/7.0)

        # Core membership: survives while band membership rotates.
        in_now=n in latest
        in_prev=n in prev
        in_prev2=n in prev2
        recent_presence=int(in_now)+int(in_prev)+int(in_prev2)
        band_core = min(1.0, 0.34*recent_presence + 0.30*band_narrow*(in_now and (in_prev or in_prev2)))

        # Cluster network: pair strength + living companions.
        mates=[m for m in latest if m!=n]
        pair_strength=0.0
        living_mates=0
        if mates:
            vals=[]
            for m in mates:
                vals.append(pc[tuple(sorted((n,m)))])
                if m in prev or m in prev2: living_mates+=1
            pair_strength=min(1.0, (sum(sorted(vals,reverse=True)[:3])/3)/8.0)
        cluster_alive=min(1.0,0.70*pair_strength+0.30*min(living_mates/4,1))

        # Carry survival: not "present => carry"; needs independent support.
        streak=streak_now(sets,n,8)
        carry_survival=0.0
        if g==0:
            carry_survival=min(1.0,
                0.34*min(streak/3,1)+
                0.28*cluster_alive+
                0.23*band_core+
                0.15*float(r.get("AYNI SAAT FAZI R",0))
            )

        # Return survival: returned candidate's chance to live one more hand.
        return_survival=0.0
        if g>=1:
            gap_fit=1.0 if g in (1,2) else (0.80 if g in (3,4) else 0.72)
            return_survival=min(1.0,
                0.26*gap_fit+
                0.22*cluster_alive+
                0.20*band_reactivation+
                0.17*float(r.get("KÜME ZAMAN RİTMİ R",0))+
                0.15*float(r.get("AYNI YAŞAM İZİ R",0))
            )

        # Pioneer: can be a band regime signal without being a carry signal.
        pioneer = 1.0 if (g==0 and p1==0 and c>0 and not in_prev) else 0.0

        # Early-series -> long sleep -> return family.
        pos=_number_positions(sets,n,40)
        old_series=0.0
        if len(pos)>=2 and any((bb-aa)==1 for aa,bb in zip(pos,pos[1:])):
            old_series=1.0
        series_sleep_return = old_series * (1.0 if g>=5 else 0.0)

        # Negative evidence: reduce confidence, do not delete number.
        neg=0.0
        neg += 0.25*pioneer
        if g==0 and streak<=1 and cluster_alive<0.30 and band_core<0.35:
            neg += 0.30  # unsupported carry
        if g>=1 and return_survival<0.40:
            neg += 0.18
        if band_narrow and in_now and band_core<0.35:
            neg += 0.12  # temporary band passenger
        neg=min(1.0,neg)

        rows.append({
            "Sayı":n,
            "Bant":band_label(n),
            "Bant Yoğunluk":c,
            "Bant Reaktivasyon":band_reactivation,
            "Bant Patlama":band_burst,
            "Bant Daralma":band_narrow,
            "Bant Yaşam":band_alive,
            "Bant Çekirdek":band_core,
            "Küme Yaşam":cluster_alive,
            "Carry Survival":carry_survival,
            "Return Survival":return_survival,
            "Öncü/Kıvılcım":pioneer,
            "Seri→Uzun Uyku":series_sleep_return,
            "Negatif Kanıt":neg,
            "Yaşam Olay Yolu":_life_event_path(sets,n,10),
        })
    adv=pd.DataFrame(rows).set_index("Sayı")
    out=tab.copy().set_index("Sayı").join(adv,how="left").reset_index()

    # Twin separator: same GAP + same life trace => don't invent fake certainty.
    twin_sizes=out.groupby(["Gap","Yaşam İzi"])["Sayı"].transform("count")
    out["İkiz Grup"]=twin_sizes
    out["İkiz Belirsizlik"]=np.where(twin_sizes>=2,1.0,0.0)

    # Independent micro-evidence families. A role must have genuine extra support.
    out["Mikro Bağımsız Kanıt"]=(
        (out["Bant Çekirdek"]>=0.55).astype(int)+
        (out["Bant Reaktivasyon"]>=0.65).astype(int)+
        (out["Küme Yaşam"]>=0.55).astype(int)+
        (out["Carry Survival"]>=0.58).astype(int)+
        (out["Return Survival"]>=0.58).astype(int)+
        (out["Seri→Uzun Uyku"]>=1).astype(int)
    )

    # Decision class: description first, score second.
    def cls(r):
        if r["Öncü/Kıvılcım"]>=1:
            return "ÖNCÜ — bant sinyali, taşıma garanti değil"
        if r["Gap"]==0 and r["Carry Survival"]>=0.62 and r["Mikro Bağımsız Kanıt"]>=2:
            return "YAŞAYAN TAŞIYICI"
        if r["Gap"]>=1 and r["Return Survival"]>=0.62 and r["Mikro Bağımsız Kanıt"]>=2:
            return "DÖNÜŞ→DEVAM ADAYI"
        if r["Seri→Uzun Uyku"]>=1 and r["Gap"]>=5:
            return "SERİ→UYKU→DÖNÜŞ"
        if r["İkiz Belirsizlik"]>=1 and r["Mikro Bağımsız Kanıt"]<=1:
            return "İKİZ / KANIT YETERSİZ"
        if r["Negatif Kanıt"]>=0.35:
            return "GEÇİCİ / NEGATİF KANITLI"
        return "İZLEME"

    out["Karar Sınıfı"]=out.apply(cls,axis=1)

    # Overlay is deliberately modest; it cannot erase the underlying V26 families.
    bonus=(
        0.026*out["Bant Çekirdek"]+
        0.024*out["Bant Reaktivasyon"]+
        0.028*out["Küme Yaşam"]+
        0.032*np.maximum(out["Carry Survival"],out["Return Survival"])+
        0.018*out["Seri→Uzun Uyku"]+
        0.010*np.minimum(out["Mikro Bağımsız Kanıt"],3)
        -0.030*out["Negatif Kanıt"]
    )
    # Twin candidates get only a small penalty when there is no independent separator.
    bonus -= 0.018*((out["İkiz Belirsizlik"]>=1)&(out["Mikro Bağımsız Kanıt"]<=1)).astype(float)
    out["Ana Puan"]=out["Ana Puan"].astype(float)+bonus
    out["Ana Yüzdelik"]=pct(out["Ana Puan"])

    out=out.sort_values(
        ["Bağımsız Aile","Mikro Bağımsız Kanıt","Güçlü Aile","Ana Puan"],
        ascending=False
    ).reset_index(drop=True)
    return out

# Preserve V26 role-gated brain, then add the MASTER micro overlay.
_expert_table_brain_v26 = expert_table_brain
def expert_table_brain(df,target_time,brain=None):
    tab,char,w,mh,bw=_expert_table_brain_v26(df,target_time,brain)
    tab=advanced_micro_overlay(df,target_time,tab,char)
    return tab,char,w,mh,bw


def _active_experts(tab,char):
    """Motorun gerçekten konuşacak adayı yoksa merkez beyin o motora koltuk vermez."""
    rows=[]
    for e in EXPERTS:
        elig=int(tab[e+" Yetkili"].sum())
        strong=int((tab[e+" R"]>=0.82).sum())
        top=float(tab[e+" R"].max())
        active=elig>0 and (strong>0 or top>=0.72)
        rows.append((e,active,elig,strong,top))
    return rows

def _pool16_two_stage(tab,char,size=16):
    # 80 -> 16: rol şampiyonları + bağımsız aile konsensüsü.
    if char["label"].startswith("KISA"):
        seats={"CARRY":4,"RETURN":4,"CLUSTER":2,"TRACE":2,"STRUCTURE":2,"TIME":1,"REGIME":1}
    elif char["label"].startswith("UZUN"):
        seats={"CARRY":2,"RETURN":6,"CLUSTER":2,"TRACE":3,"STRUCTURE":1,"TIME":1,"REGIME":1}
    else:
        seats={"CARRY":3,"RETURN":5,"CLUSTER":2,"TRACE":2,"STRUCTURE":2,"TIME":1,"REGIME":1}

    chosen=[]
    reason={}
    # Aile içindeki aday: o ailedeki en güçlü uzman mikro kanıtı.
    for fam,nseat in seats.items():
        es=[e for e in EXPERTS if FAMILIES[e]==fam]
        z=tab.copy()
        z["_fam"]=z[["Aile "+fam]].iloc[:,0]
        z=z[z["_fam"]>0].sort_values(
            ["_fam","Bağımsız Aile","Güçlü Aile","Ana Puan"],
            ascending=False
        )
        for _,r in z.iterrows():
            n=int(r["Sayı"])
            if n in chosen: continue
            chosen.append(n); reason[n]=fam
            if sum(reason.get(x)==fam for x in chosen)>=nseat: break

    # Açık koltukları 3+ bağımsız aile destekli adaylarla tamamla.
    for _,r in tab.sort_values(["Bağımsız Aile","Güçlü Aile","Ana Puan"],ascending=False).iterrows():
        n=int(r["Sayı"])
        if n not in chosen:
            chosen.append(n); reason[n]="CONSENSUS"
        if len(chosen)>=size: break
    chosen=chosen[:size]

    # chosen ilk 16 olacak şekilde tabloyu yeniden sırala.
    order={n:i for i,n in enumerate(chosen)}
    out=tab.copy()
    out["V26 Havuz"]=out["Sayı"].map(lambda n:"EVET" if int(n) in order else "HAYIR")
    out["_pool_order"]=out["Sayı"].map(lambda n:order.get(int(n),999))
    out=out.sort_values(
        ["_pool_order","Bağımsız Aile","Güçlü Aile","Ana Puan"],
        ascending=[True,False,False,False]
    ).drop(columns=["_pool_order"]).reset_index(drop=True)
    return chosen,out,reason


def _pool16_v2_observer(tab,char,size=16):
    """
    V2 HAVUZ16 — yalnız GÖZLEMCİ/deney kolu.
    Ana Puanı ana seçici yapmaz. Sabit mekanizma koridorları kullanır.
    Sonuç bilgisi kullanmaz; yalnız hedef öncesi tablosundan seçim yapar.
    """
    z=tab.copy()

    def col(name,default=0.0):
        if name in z.columns:
            return pd.to_numeric(z[name],errors="coerce").fillna(default)
        return pd.Series(default,index=z.index,dtype=float)

    gap=col("Gap")
    reactivation=col("Bant Reaktivasyon")
    long_sleep=col("Seri→Uzun Uyku")
    neg=col("Negatif Kanıt")
    twin=col("İkiz Belirsizlik")
    micro=col("Mikro Bağımsız Kanıt")
    cluster=col("Küme Yaşam")
    carry=col("Carry Survival")
    ret=col("Return Survival")

    # Kör otopsiden çıkan yönler; Ana Puan burada yalnız en son eşitlik bozucudur.
    z["V2 Rescue"] = (
        1.15*long_sleep +
        0.70*((gap>=6).astype(float)*reactivation) +
        0.45*(gap>=10).astype(float) +
        0.30*ret +
        0.18*cluster -
        0.55*neg -
        0.20*((twin>=1)&(micro<=1)).astype(float)
    )

    # GAP-2/3 ve zaman ritmi: bağımsız dönüş koridoru.
    g23=((gap>=2)&(gap<=3)).astype(float)
    time_r=col("KÜME ZAMAN RİTMİ R")
    gap2r=col("GAP-2 R"); gap3r=col("GAP-3 R")
    z["V2 Rhythm"] = 0.70*g23 + 0.55*np.maximum(gap2r,gap3r) + 0.55*time_r + 0.20*cluster - 0.45*neg

    # Küme/yaşam koridoru.
    cl_r=np.maximum(col("KÜME TAŞIMA R"),col("KÜME DÖNÜŞ R"))
    z["V2 Cluster"] = 0.75*cluster + 0.55*cl_r + 0.20*reactivation - 0.45*neg

    # Taşıma sıcaklığı sınırlı ve ikinci kanıt şartlı.
    carry_support=((cluster>=0.35)|(micro>=2)|(col("Bant Çekirdek")>=0.5)).astype(float)
    z["V2 Carry"] = 0.75*carry*carry_support + 0.30*col("TAŞIMA R") - 0.55*neg

    # Genel çeşitlilik puanı: aile sayısını sınırsız ödüllendirme.
    fam=np.minimum(col("Bağımsız Aile"),3)/3.0
    strong=np.minimum(col("Güçlü Aile"),2)/2.0
    z["V2 Diversity"] = (
        0.34*fam + 0.24*strong + 0.18*micro.clip(0,3)/3.0 +
        0.12*cluster + 0.12*reactivation - 0.38*neg
    )

    chosen=[]; reason={}; band_count=Counter()

    def take(score_col,nseat,label,eligible=None,max_per_band=3):
        nonlocal chosen
        q=z.copy()
        if eligible is not None:
            q=q[eligible.loc[q.index]]
        # Ana Puan yalnız son eşitlik bozucu.
        q=q.sort_values([score_col,"Ana Puan"],ascending=False)
        used=0
        for _,r in q.iterrows():
            if used>=nseat or len(chosen)>=size: break
            n=int(r["Sayı"]); b=band(n)
            if n in chosen or band_count[b]>=max_per_band: continue
            if float(r[score_col])<=0: continue
            chosen.append(n); reason[n]=label; band_count[b]+=1; used+=1

    # Sabit 16 koltuk: sıcaklık/konsensüs tek başına havuzu ele geçiremez.
    take("V2 Rescue",4,"V2_RESCUE",
         eligible=((gap>=6)&((long_sleep>0)|(reactivation>0)|(ret>0.15))))
    take("V2 Rhythm",4,"V2_GAP23_TIME",
         eligible=((gap>=2)&(gap<=3)))
    take("V2 Cluster",3,"V2_CLUSTER",
         eligible=(cluster>0))
    take("V2 Carry",2,"V2_CARRY_GATED",
         eligible=(carry_support>0))
    take("V2 Diversity",3,"V2_DIVERSITY")

    # Açık koltuk kalırsa en güçlü farklı mekanizma kanıtıyla tamamla.
    z["V2 Final"] = z[["V2 Rescue","V2 Rhythm","V2 Cluster","V2 Carry","V2 Diversity"]].max(axis=1)
    q=z.sort_values(["V2 Final","Ana Puan"],ascending=False)
    for _,r in q.iterrows():
        if len(chosen)>=size: break
        n=int(r["Sayı"]); b=band(n)
        if n in chosen: continue
        if band_count[b]>=3: continue
        chosen.append(n); reason[n]="V2_FILL"; band_count[b]+=1

    # Çok sıkışık durumda 16'yı tamamla; yine Ana Puan ana karar değil, sadece fallback.
    if len(chosen)<size:
        for _,r in q.iterrows():
            n=int(r["Sayı"])
            if n not in chosen:
                chosen.append(n); reason[n]="V2_FALLBACK"
            if len(chosen)>=size: break

    return chosen[:size],reason



def _day_league_history_score(df, target_time, brain=None, min_day_obs=3):
    """
    GÜN İÇİ UZMAN LİGİ — GÖZLEMCİ
    Aynı günün önceki çekilişlerinde hangi uzmanların gerçekten isabet ürettiğini ölçer.
    Hedef sonucu kesinlikle kullanılmaz.
    """
    if df.empty:
        return {}, []
    target_date,_,_=next_target_label(df)
    day=df[df["date"]==target_date].sort_values("_dt").reset_index(drop=True)
    if len(day)<min_day_obs:
        return {}, []

    # Her önceki gün içi çekilişi, kendisinden önceki veriyle kör şekilde değerlendir.
    all_df=df.sort_values("_dt").reset_index(drop=True)
    scores={e:[] for e in EXPERTS}
    for _,row in day.iterrows():
        idx=all_df.index[all_df["draw_no"]==row["draw_no"]].tolist()
        if not idx: continue
        i=idx[0]
        train=all_df.iloc[:i].reset_index(drop=True)
        if len(train)<36: continue
        try:
            tab,_,_,_,_=expert_table_brain(train,row["time"],brain or _default_brain())
        except Exception:
            continue
        actual=set(map(int,row["numbers"]))
        for e in EXPERTS:
            top=tab.sort_values(e+" R",ascending=False).head(5)["Sayı"].astype(int).tolist()
            scores[e].append(len(set(top)&actual))

    # Küçük örneklem shrinkage: rastgele Top5 beklentisi 1.25'e çek.
    perf={}
    for e,hs in scores.items():
        if not hs: continue
        avg=(sum(hs)+2*1.25)/(len(hs)+2)
        perf[e]=float(avg)
    ranked=sorted(perf,key=lambda e:perf[e],reverse=True)
    return perf, ranked[:3]


def _pool16_day_league_observer(tab, df, target_time, brain=None, size=16):
    """
    Günün ilk 3+ çekilişinden sonra o gün çalışan TOP-3 uzmanı dinleyen deney havuzu.
    Canlı MASTER havuzunu değiştirmez; yalnız kör test/gözlem için.
    """
    perf,top3=_day_league_history_score(df,target_time,brain,min_day_obs=3)
    if len(top3)<3:
        return [],{"mode":"LEARNING","top3":top3,"perf":perf}

    z=tab.copy()
    rcols=[e+" R" for e in top3]
    z["Lig Ort"]=z[rcols].mean(axis=1)
    z["Lig Max"]=z[rcols].max(axis=1)
    z["Lig Oy"]=(z[rcols]>=0.68).sum(axis=1)
    z["Lig Skor"]=0.50*z["Lig Ort"]+0.30*z["Lig Max"]+0.20*(z["Lig Oy"]/3.0)

    # Ana Puan sadece eşitlik bozucu.
    z=z.sort_values(["Lig Skor","Ana Puan"],ascending=False).reset_index(drop=True)

    chosen=[]; bands=Counter()
    for _,r in z.iterrows():
        n=int(r["Sayı"]); b=band(n)
        if bands[b]>=3: continue
        chosen.append(n); bands[b]+=1
        if len(chosen)>=size: break
    if len(chosen)<size:
        for n in z["Sayı"].astype(int):
            if n not in chosen:
                chosen.append(n)
            if len(chosen)>=size: break
    return chosen[:size],{"mode":"ACTIVE","top3":top3,"perf":perf}


def _twin_second_trace_overlay(df, tab):
    """
    İKİZ İKİNCİ İZ SENSÖRÜ
    Aynı GAP + aynı yaşam izindeki adayları, kadavrada gördüğümüz ikinci izlerle ayırır:
    partner yaşamı, +2 ardışık yeniden bağlanma, gün içi partner canlılığı,
    mevcut ritim/return ve mikro konsensüsün ters-yük riskleri.

    Not: Bu katman SONUÇ görmez. Yalnız hedef öncesi geçmişi kullanır.
    """
    sets=sets_of(df)
    if not sets:
        return tab.copy()

    latest=sets[-1]
    prev=sets[-2] if len(sets)>=2 else set()
    target_date,target_time,_=next_target_label(df)
    day_sets=[set(x) for x in df[df["date"]==target_date]["numbers"].tolist()]
    day_union=set().union(*day_sets) if day_sets else set()

    # son 60 elde partner hafızası
    recent=sets[-60:]
    partner_counters={}
    occ_counts={}
    for n in range(1,81):
        pc=Counter(); occ=0
        for s in recent:
            if n in s:
                occ+=1
                for m in s:
                    if m!=n:
                        pc[m]+=1
        partner_counters[n]=pc
        occ_counts[n]=occ

    z=tab.copy()
    pa2=[]; tda=[]; s2r=[]
    for _,r in z.iterrows():
        n=int(r["Sayı"])
        pc=partner_counters[n]
        top=[m for m,_ in pc.most_common(3)]
        denom=max(1,len(top))
        pa2.append(sum((m in latest or m in prev) for m in top)/denom if top else 0.0)
        tda.append(sum(m in day_union for m in top)/denom if top else 0.0)

        # +2 yeniden bağlanma: sayı son elde yok, +2 komşularından biri canlı
        neigh={x for x in (n-2,n+2) if 1<=x<=80}
        s2r.append(float((n not in latest) and bool(neigh & latest)))

    z["İkiz PartnerCanlı2"]=pa2
    z["İkiz GünPartner"]=tda
    z["İkiz +2 YenidenBağ"]=s2r

    # İlk geliştirme setinde öğrenilen, son holdoutta sınır swapında pozitif kalan
    # ikinci-iz bileşimi. Normalize sabitleri sadece ölçek içindir.
    z["İkiz İkinciİz Skoru"]=(
        -1.0*z["İkiz +2 YenidenBağ"]/0.4674363667
        +1.0*z["İkiz PartnerCanlı2"]/0.2933282253
        -1.0*pd.to_numeric(z.get("KÜME ZAMAN RİTMİ R",0),errors="coerce").fillna(0)/0.3347529991
        -1.0*pd.to_numeric(z.get("Mikro Bağımsız Kanıt",0),errors="coerce").fillna(0)/0.7802587709
        -1.0*pd.to_numeric(z.get("Return Survival",0),errors="coerce").fillna(0)/0.2580534365
        +1.0*z["İkiz GünPartner"]/0.3596746567
    )
    return z


def _twin_boundary_surgeon_observer(df, tab, pool16, max_swaps=2, margin=0.5):
    """
    GÖZLEMCİ CERRAH:
    - İlk 12 koltuğa dokunmaz.
    - Sadece Havuz16 sınırındaki 13-16 ile dışarıdaki 17-30 arasında çalışır.
    - Yalnız AYNI GAP + AYNI YAŞAM İZİ ikiz çatışmasında swap önerir.
    - Canlı MASTER Havuz16'yı değiştirmez; kör testte ayrı ölçülür.
    """
    z=_twin_second_trace_overlay(df,tab).copy()
    pos={int(n):i+1 for i,n in enumerate(z["Sayı"].astype(int).tolist())}
    base=list(map(int,pool16))
    protected=set(base[:12])
    current=set(base)
    swaps=[]

    # Sadece 13-30 sınır bölgesi.
    boundary=z[z["Sayı"].astype(int).map(lambda n:13<=pos.get(int(n),999)<=30)].copy()

    candidates=[]
    for (g,life),grp in boundary.groupby(["Gap","Yaşam İzi"],dropna=False):
        inside=grp[grp["Sayı"].astype(int).isin(current-protected)]
        outside=grp[~grp["Sayı"].astype(int).isin(current)]
        if inside.empty or outside.empty:
            continue
        outrow=outside.sort_values("İkiz İkinciİz Skoru",ascending=False).iloc[0]
        inrow=inside.sort_values("İkiz İkinciİz Skoru",ascending=True).iloc[0]
        delta=float(outrow["İkiz İkinciİz Skoru"]-inrow["İkiz İkinciİz Skoru"])
        if delta>=margin:
            candidates.append((delta,int(outrow["Sayı"]),int(inrow["Sayı"]),int(g),str(life)))

    for delta,entry,exitn,g,life in sorted(candidates,reverse=True):
        if len(swaps)>=max_swaps:
            break
        if exitn not in current or exitn in protected or entry in current:
            continue
        current.remove(exitn); current.add(entry)
        swaps.append({
            "Çıkış":exitn,"Giriş":entry,"Delta":delta,
            "Gap":g,"Yaşam İzi":life
        })

    # Orijinal sıra korunarak çıkışlar düşürülür, girişler kendi tablo sırasına göre eklenir.
    result=[n for n in base if n in current]
    for n in z["Sayı"].astype(int).tolist():
        if n in current and n not in result:
            result.append(n)
    return result[:16],swaps,z




def _three_draw_block_sensor(df, tab):
    """
    23:02 + 23:07 + 23:12 öğrenme penceresindeki tekrar eden 2/3/4'lü blokları
    hedef sonucuna bakmadan çıkarır. 23:17 ve sonrasında sabit saat-başı blok kanıtı üretir.
    """
    z=tab.copy()
    z["3El Blok"]=0.0
    z["3El Blok Derece"]=0.0
    z["3El Blok Partner"]=0.0

    target_date,target_time,_=next_target_label(df)
    day=df[df["date"]==target_date].sort_values("_dt").reset_index(drop=True)
    if len(day)<3:
        return z, {"mode":"LEARNING","families":[]}

    first3=[set(map(int,x)) for x in day.iloc[:3]["numbers"].tolist()]
    # Bir çift ilk 3 elde en az iki kez beraber görünmüşse gerçek blok bağı say.
    pair_hits=Counter()
    for s in first3:
        for a,b in combinations(sorted(s),2):
            pair_hits[(a,b)] += 1
    edges={p:c for p,c in pair_hits.items() if c>=2}

    # Ağ bileşenleri = aynı tekrar ailesi. Büyük aile aynı kanıtı 10 kere saymasın.
    adj={n:set() for n in range(1,81)}
    for (a,b),c in edges.items():
        adj[a].add(b); adj[b].add(a)

    comps=[]; seen=set()
    for n in range(1,81):
        if n in seen or not adj[n]: continue
        stack=[n]; comp=set()
        while stack:
            x=stack.pop()
            if x in comp: continue
            comp.add(x); seen.add(x); stack.extend(adj[x]-comp)
        if len(comp)>=2: comps.append(comp)

    # Üye puanı: tekrar bağ yoğunluğu + üç elde görünme + üçlü/dörtlü alt-blok desteği.
    score={n:0.0 for n in range(1,81)}
    degree={n:0.0 for n in range(1,81)}
    partner={n:0.0 for n in range(1,81)}
    for n in range(1,81):
        nbr=adj[n]
        degree[n]=min(len(nbr)/5.0,1.0)
        appear=sum(n in s for s in first3)/3.0
        if nbr:
            strength=sum(edges.get(tuple(sorted((n,m))),0) for m in nbr)/(2.0*len(nbr))
            partner[n]=min(strength,1.0)
            score[n]=0.45*degree[n]+0.35*appear+0.20*partner[n]

    z["3El Blok"]=z["Sayı"].astype(int).map(score).fillna(0.0)
    z["3El Blok Derece"]=z["Sayı"].astype(int).map(degree).fillna(0.0)
    z["3El Blok Partner"]=z["Sayı"].astype(int).map(partner).fillna(0.0)

    fams=[sorted(c) for c in sorted(comps,key=lambda c:(-len(c),min(c)))]
    return z, {"mode":"ACTIVE","families":fams[:12],"edge_count":len(edges)}



def _master_phase_policy(df):
    """
    23:02–23:22 = ÖĞRENME
    23:27 = İLK KUPON / kontrollü geçiş
    23:32–23:52 = RESCUE
    23:57 = NÖTR kapanış

    Hedef zamanı next_target_label() ile, hedef sonucu görülmeden belirlenir.
    """
    _, target_time, _ = next_target_label(df)
    try:
        hh, mm = [int(x) for x in str(target_time).split(":")[:2]]
    except Exception:
        return {"mode":"NEUTRAL","time":str(target_time),"max_swaps":16}

    if hh == 23 and mm <= 22:
        return {"mode":"LEARNING","time":str(target_time),"max_swaps":0}
    if hh == 23 and mm == 27:
        return {"mode":"FIRST_TICKET","time":str(target_time),"max_swaps":2}
    if hh == 23 and 32 <= mm <= 52:
        return {"mode":"RESCUE","time":str(target_time),"max_swaps":16}
    if hh == 23 and mm == 57:
        return {"mode":"NEUTRAL","time":str(target_time),"max_swaps":16}
    return {"mode":"NEUTRAL","time":str(target_time),"max_swaps":16}


def _unified_brain_observer(df, tab, char, size=16):
    """
    TEK BEYİN BAĞLANTI KATMANI V2 — KADAVRA REVİZYONU / GÖZLEMCİ

    40 kör hedef kadavrasından çıkan yönler:
    - GAP-6+ rescue alanı
    - GAP-3 koruma alanı
    - GAP-1 güçlü fren/eleme alanı
    - GAP-0 / carry tek başına terfi edemez
    - 3-el blok sadece CONFIRM rolünde
    - aynı yaşam izi + küme dönüş + seri→uzun uyku birlikteyse return yolu güçlenir
    - canlı MASTER havuzuna dokunmaz; ayrı Havuz16 üretir
    """
    z, block_meta = _three_draw_block_sensor(df, tab)
    phase_policy = _master_phase_policy(df)
    phase_mode = phase_policy["mode"]

    def C(name, default=0.0):
        if name in z.columns:
            return pd.to_numeric(z[name], errors="coerce").fillna(default)
        return pd.Series(default, index=z.index, dtype=float)

    gap = C("Gap")
    neg = C("Negatif Kanıt")
    fam = np.minimum(C("Bağımsız Aile"), 4) / 4.0
    strong = np.minimum(C("Güçlü Aile"), 3) / 3.0
    micro = np.minimum(C("Mikro Bağımsız Kanıt"), 4) / 4.0

    cluster = C("Küme Yaşam")
    carry = C("Carry Survival")
    ret = C("Return Survival")
    react = C("Bant Reaktivasyon")
    core = C("Bant Çekirdek")
    block = C("3El Blok")
    seq = C("ARDIŞIK/+2/+3 R")
    rhythm = C("KÜME ZAMAN RİTMİ R")
    same = C("AYNI YAŞAM İZİ R")
    slot = C("AYNI SAAT FAZI R")
    longsleep = C("Seri→Uzun Uyku")
    kret = C("KÜME DÖNÜŞ R")
    kcarry = C("KÜME TAŞIMA R")
    tasima_r = C("TAŞIMA R")

    gap_signal = pd.Series(0.0, index=z.index, dtype=float)
    for gcol, mask in [
        ("GAP-1 R", gap == 1),
        ("GAP-2 R", gap == 2),
        ("GAP-3 R", gap == 3),
        ("GAP-4/5 R", (gap >= 4) & (gap <= 5)),
        ("GAP-6+ R", gap >= 6),
    ]:
        gap_signal = np.maximum(gap_signal, C(gcol) * mask.astype(float))

    return_path = (
        0.26 * gap_signal
        + 0.18 * ret
        + 0.16 * kret
        + 0.14 * same
        + 0.10 * rhythm
        + 0.08 * react
        + 0.08 * longsleep
    )

    rescue_support = np.maximum.reduce([
        ret.to_numpy(),
        kret.to_numpy(),
        same.to_numpy(),
        rhythm.to_numpy(),
        longsleep.to_numpy(),
    ])
    gap6_rescue = ((gap >= 6).astype(float) *
                   np.clip((rescue_support - 0.35) / 0.45, 0, 1))

    gap3_protect = ((gap == 3).astype(float) *
                    np.clip((np.maximum(kret, same) + ret - 0.55) / 0.65, 0, 1))

    carry_second = np.maximum.reduce([
        cluster.to_numpy(),
        core.to_numpy(),
        micro.to_numpy(),
        kcarry.to_numpy(),
        seq.to_numpy(),
    ])
    carry_gate = np.clip((carry_second - 0.40) / 0.45, 0, 1)
    carry_path = (
        (0.34 * carry + 0.18 * tasima_r + 0.16 * cluster +
         0.10 * seq + 0.10 * core + 0.06 * slot + 0.06 * micro)
        * carry_gate
    )

    cluster_path = (
        0.30 * cluster
        + 0.20 * kret
        + 0.12 * kcarry
        + 0.14 * rhythm
        + 0.10 * same
        + 0.08 * react
        + 0.06 * seq
    )

    trace_path = (
        0.30 * same
        + 0.20 * rhythm
        + 0.14 * slot
        + 0.12 * react
        + 0.10 * longsleep
        + 0.08 * seq
        + 0.06 * cluster
    )

    other = np.maximum.reduce([
        return_path.to_numpy(),
        carry_path.to_numpy(),
        cluster_path.to_numpy(),
        trace_path.to_numpy(),
    ])
    block_confirm = block.to_numpy() * np.clip((other - 0.48) / 0.32, 0, 1)

    path_count = (
        (return_path >= 0.46).astype(int)
        + (carry_path >= 0.46).astype(int)
        + (cluster_path >= 0.46).astype(int)
        + (trace_path >= 0.46).astype(int)
    )
    independent = (
        0.30 * fam
        + 0.22 * strong
        + 0.22 * micro
        + 0.26 * np.minimum(path_count / 3.0, 1.0)
    )

    gap1_brake = (
        (gap == 1).astype(float)
        * np.clip((0.55 - np.maximum(return_path, cluster_path)) / 0.35, 0, 1)
    )
    gap0_carry_brake = (
        (gap == 0).astype(float)
        * np.clip((0.50 - carry_second) / 0.40, 0, 1)
    )
    contradiction = (
        0.46 * neg
        + 0.18 * gap1_brake
        + 0.16 * gap0_carry_brake
        + 0.08 * ((fam <= 0.25) & (micro <= 0.25)).astype(float)
    )

    paths = np.vstack([
        return_path.to_numpy(),
        carry_path.to_numpy(),
        cluster_path.to_numpy(),
        trace_path.to_numpy()
    ]).T
    ps = np.sort(paths, axis=1)[:, ::-1]

    z["Tek Beyin V2 Rescue"] = gap6_rescue
    z["Tek Beyin V2 GAP3 Koruma"] = gap3_protect
    z["Tek Beyin V2 Carry Gate"] = carry_gate

    z["Tek Beyin Skor"] = (
        0.31 * ps[:, 0]
        + 0.21 * ps[:, 1]
        + 0.22 * independent
        + 0.10 * gap6_rescue
        + 0.08 * gap3_protect
        + 0.05 * block_confirm
        + 0.03 * C("Ana Yüzdelik")
        - contradiction
    )

    z["Tek Beyin Yol"] = np.select(
        [
            (return_path >= carry_path) & (return_path >= cluster_path) & (return_path >= trace_path),
            (carry_path >= cluster_path) & (carry_path >= trace_path),
            (cluster_path >= trace_path),
        ],
        ["RETURN", "CARRY", "CLUSTER"],
        default="TRACE",
    )

    # FAZ POLİTİKASI:
    # Öğrenme fazında canlı alternatif üretme; MASTER referans kalır.
    # 23:27 ilk kupon: yalnız güçlü rescue + yaşam izi ile kontrollü itiraz.
    # 23:32–23:52: kör kadavrada çalışan rescue ağına daha fazla yetki.
    phase_bonus = np.zeros(len(z), dtype=float)
    phase_brake = np.zeros(len(z), dtype=float)

    if phase_mode == "FIRST_TICKET":
        strong_first = (
            (gap >= 6).astype(float)
            * np.clip((same + ret + kret + longsleep - 1.35) / 1.20, 0, 1)
        )
        phase_bonus += 0.10 * strong_first.to_numpy()
        phase_brake += (
            0.12 * (gap <= 1).astype(float).to_numpy()
            + 0.08 * ((block > 0.45) & (other < 0.55)).astype(float).to_numpy()
        )
    elif phase_mode == "RESCUE":
        mature_rescue = (
            (gap >= 4).astype(float)
            * np.clip((same + kret + ret + longsleep + micro/1.0 - 1.55) / 1.55, 0, 1)
        )
        phase_bonus += 0.12 * mature_rescue.to_numpy() + 0.05 * gap6_rescue
    elif phase_mode == "LEARNING":
        phase_brake += 1.0

    z["Tek Beyin Faz"] = phase_mode
    z["Tek Beyin Faz Bonus"] = phase_bonus
    z["Tek Beyin Faz Fren"] = phase_brake
    z["Tek Beyin Skor"] = z["Tek Beyin Skor"] + phase_bonus - phase_brake

    q = z.sort_values(
        ["Tek Beyin Skor", "Bağımsız Aile", "Mikro Bağımsız Kanıt", "Ana Puan"],
        ascending=False
    )

    # Önce serbest Birleşik V2 adayı.
    free_chosen = []
    bc = Counter()
    for _, r in q.iterrows():
        n = int(r["Sayı"])
        b = band(n)
        if bc[b] >= 3:
            continue
        free_chosen.append(n)
        bc[b] += 1
        if len(free_chosen) >= size:
            break
    if len(free_chosen) < size:
        for n in q["Sayı"].astype(int):
            if n not in free_chosen:
                free_chosen.append(n)
            if len(free_chosen) >= size:
                break

    # MASTER referansı: mevcut iki-aşamalı Havuz16. Bu fonksiyon yalnız gözlemci.
    master_ref, _, _ = _pool16_two_stage(tab.copy(), char, size)

    if phase_mode == "LEARNING":
        chosen = list(map(int, master_ref))
    elif phase_mode == "FIRST_TICKET":
        # 23:27: MASTER'ı koru, yalnız en fazla 2 çok güçlü itiraz.
        chosen = list(map(int, master_ref))
        rank = {int(n): i for i, n in enumerate(q["Sayı"].astype(int).tolist())}
        outsiders = [n for n in free_chosen if n not in chosen]
        insiders = [n for n in chosen]
        swaps = 0
        for entry in outsiders:
            er = z[z["Sayı"].astype(int) == int(entry)].iloc[0]
            if not (float(er["Gap"]) >= 6 and
                    float(er.get("AYNI YAŞAM İZİ R",0)) >= 0.45 and
                    (float(er.get("Return Survival",0)) >= 0.35 or
                     float(er.get("KÜME DÖNÜŞ R",0)) >= 0.45 or
                     float(er.get("Seri→Uzun Uyku",0)) >= 0.45)):
                continue

            # Çıkışta GAP-3 ve güçlü yaşam izi korunur.
            exits = []
            for x in insiders:
                xr = z[z["Sayı"].astype(int) == int(x)].iloc[0]
                protected = (
                    (int(xr["Gap"]) == 3 and
                     (float(xr.get("AYNI YAŞAM İZİ R",0)) >= 0.40 or
                      float(xr.get("KÜME DÖNÜŞ R",0)) >= 0.40))
                    or float(xr.get("AYNI YAŞAM İZİ R",0)) >= 0.60
                )
                if not protected:
                    exits.append(x)
            if not exits:
                break
            exitn = min(exits, key=lambda x: float(z.loc[z["Sayı"].astype(int)==int(x),"Tek Beyin Skor"].iloc[0]))
            entry_score = float(er["Tek Beyin Skor"])
            exit_score = float(z.loc[z["Sayı"].astype(int)==int(exitn),"Tek Beyin Skor"].iloc[0])
            if entry_score <= exit_score + 0.04:
                continue
            chosen.remove(exitn); chosen.append(int(entry))
            insiders.remove(exitn); insiders.append(int(entry))
            swaps += 1
            if swaps >= 2:
                break
    else:
        # RESCUE ve NÖTR fazlarda serbest gözlemci havuzu.
        chosen = free_chosen[:size]

    meta = {
        "block": block_meta,
        "phase_policy": phase_policy,
        "top_paths": z.sort_values("Tek Beyin Skor", ascending=False).head(16)[
            ["Sayı","Tek Beyin Skor","Tek Beyin Yol","3El Blok",
             "Tek Beyin V2 Rescue","Tek Beyin V2 GAP3 Koruma","Tek Beyin V2 Carry Gate"]
        ].to_dict("records")
    }
    return chosen[:size], meta, z








def _dynamic_motor_coefficients(df):
    """Her 5 dakikalık geçişte motor güvenini RELATİF değişimle ölçer.
    Hedef sonucu kullanılmaz. Son geçiş, önceki 2-4 geçişlik kendi baz çizgisine kıyaslanır.
    Böylece Return/Reaktivasyon sürekli tavana vurmaz.
    """
    target_date,target_time,_=next_target_label(df)
    day=df[df["date"]==target_date].sort_values("_dt").reset_index(drop=True)
    if len(day)<3:
        return {"carry":1.0,"return":1.0,"react":1.0,"rhythm":1.0,"sample":0,"target_time":str(target_time)}

    sets=[set(map(int,x)) for x in day["numbers"].tolist()]
    feats=[]

    def band_count(s,b):
        lo=(b-1)*10+1; hi=b*10
        return sum(lo<=n<=hi for n in s)

    for i in range(1,len(sets)):
        prev=sets[i-1]; cur=sets[i]
        carry=len(prev&cur)/20.0

        hist=set().union(*sets[max(0,i-4):i-1]) if i-1>max(0,i-4) else set()
        returned=len((cur-prev)&hist)/20.0 if hist else 0.0

        react_hits=0; eligible=0
        for b in range(1,9):
            p=band_count(prev,b); c=band_count(cur,b)
            if p<=1:
                eligible+=1
                if c>=2: react_hits+=1
        react=react_hits/max(eligible,1)

        rhythm=carry
        if i>=2:
            prevprev=sets[i-2]
            triple=len(prevprev&prev&cur)/20.0
            rhythm=(carry+triple)/2.0

        feats.append(np.array([carry,returned,react,rhythm],dtype=float))

    # Need a current transition plus prior baseline.
    if len(feats)<2:
        return {"carry":1.0,"return":1.0,"react":1.0,"rhythm":1.0,"sample":len(feats),"target_time":str(target_time)}

    cur=feats[-1]
    hist=np.vstack(feats[max(0,len(feats)-5):-1])
    base=hist.mean(axis=0)
    spread=hist.std(axis=0)

    # Stabilize tiny variance; coefficient based on relative surprise.
    floor=np.array([0.06,0.05,0.08,0.05])
    z=(cur-base)/np.maximum(spread,floor)
    z=np.clip(z,-1.5,1.5)

    # Narrow band 0.88–1.12, less prone to saturation than old 0.85–1.15.
    coeff=1.0 + 0.08*z
    return {
        "carry":float(coeff[0]),
        "return":float(coeff[1]),
        "react":float(coeff[2]),
        "rhythm":float(coeff[3]),
        "sample":int(len(hist)),
        "raw_carry":float(cur[0]),
        "raw_return":float(cur[1]),
        "raw_react":float(cur[2]),
        "raw_rhythm":float(cur[3]),
        "base_carry":float(base[0]),
        "base_return":float(base[1]),
        "base_react":float(base[2]),
        "base_rhythm":float(base[3]),
        "target_time":str(target_time),
    }


def _v9_dynamic_conductor(df, tab, pool, v7_base, target_time, size=5):
    """V9: V7 taban + faza duyarlı, en fazla tek kontrollü swap."""
    z=tab[tab["Sayı"].astype(int).isin(set(map(int,pool)))].copy()
    def C(n,d=0.0):
        return pd.to_numeric(z[n],errors="coerce").fillna(d) if n in z.columns else pd.Series(d,index=z.index,dtype=float)

    sleep=C("SERİ→UYKU→DÖNÜŞ R"); gap6=C("GAP-6+ R"); gap45=C("GAP-4/5 R")
    g1=C("GAP-1 R"); g2=C("GAP-2 R"); g3=C("GAP-3 R"); carry=C("TAŞIMA R")
    react=C("Bant Reaktivasyon"); rhythm=C("KÜME ZAMAN RİTMİ R"); hour=C("AYNI SAAT FAZI R")
    same=C("AYNI YAŞAM İZİ R"); kret=C("KÜME DÖNÜŞ R"); bscore=C("BANT/KOMŞU R")
    ret=C("Return Survival"); micro=np.minimum(C("Mikro Bağımsız Kanıt"),4)/4.0
    main=C("Ana Yüzdelik"); neg=C("Negatif Kanıt")
    strong=np.minimum(C("Güçlü Oy"),6)/6.0; expert=np.minimum(C("Uzman Oy"),8)/8.0

    t=str(target_time)
    dyn=_dynamic_motor_coefficients(df)
    rg=sg=cg=xg=1.0
    if t=="23:52": rg,sg,cg,xg=1.12,.94,.96,1.05
    elif t=="23:57": rg,sg,cg,xg=.88,1.12,1.08,1.00
    elif t=="23:27": rg,sg,cg,xg=1.04,.92,.94,1.02

    # Dinamik katsayılar: günün son geçişlerinden öğrenilir, hedefe bakmaz.
    rg *= dyn["return"]
    sg *= dyn["rhythm"]
    cg *= dyn["carry"]
    xg *= dyn["react"]

    z["V9_RETURN_FAMILY"]=rg*(.42*sleep+.25*gap6+.15*gap45+.10*ret+.08*micro)
    short=np.maximum.reduce([g1.to_numpy(),g2.to_numpy(),g3.to_numpy()])
    z["V9_SHORT_FAMILY"]=sg*(.30*short+.25*rhythm+.17*hour+.12*ret+.08*micro+.08*main)
    z["V9_REACT_FAMILY"]=xg*(.34*react+.22*micro+.16*kret+.10*same+.10*ret+.08*main)
    conf=np.maximum.reduce([rhythm.to_numpy(),same.to_numpy(),hour.to_numpy()])
    z["V9_CARRY_FAMILY"]=cg*(.38*carry+.22*conf+.14*micro+.10*main+.08*kret+.08*bscore)

    fam=z[["V9_RETURN_FAMILY","V9_SHORT_FAMILY","V9_REACT_FAMILY","V9_CARRY_FAMILY"]].to_numpy()
    fs=np.sort(fam,axis=1)[:,::-1]
    independence=.62*fs[:,0]+.28*fs[:,1]+.10*fs[:,2]
    consensus=np.clip((.55*strong+.45*expert-.70)/.30,0,1)
    same_story=np.clip((fs[:,0]-fs[:,1]-.18)/.45,0,1)
    z["V9_SCORE"]=independence+.10*micro+.07*ret+.05*main-.09*consensus-.10*same_story-.14*neg

    selected=[int(n) for n in v7_base][:size]
    v9_swap_meta={
        "phase": t,
        "swap_opened": False,
        "swap_applied": False,
        "weak_n": None,
        "challenger_n": None,
        "reason": "V7_KORUNDU",
    }
    q=z.sort_values(["V9_SCORE","Ana Puan"],ascending=False)
    for n in q["Sayı"].astype(int):
        if len(selected)>=size: break
        if n not in selected: selected.append(n)

    # ------------------------------------------------------------
    # V9.5 REAKTİVASYON MAHKEMESİ
    # ------------------------------------------------------------
    # ÖNEMLİ: Challenger artık "en yüksek V9_SCORE" ile seçilmez.
    # V7'nin içerideki her adayı ile Akor Havuz16'daki her dış aday,
    # doğrudan mekanizma farkları üzerinden karşılaştırılır.
    zin=z[z["Sayı"].astype(int).isin(selected)].copy()
    zout=z[~z["Sayı"].astype(int).isin(selected)].copy()

    qualified=[]
    if len(zin) and len(zout):
        bc=Counter(band(int(n)) for n in selected)

        for _,weak in zin.iterrows():
            wn=int(weak["Sayı"])
            for _,chal in zout.iterrows():
                cn=int(chal["Sayı"])

                # Aynı bantta üçüncü sayı oluşturma.
                band_ok = bc[band(cn)] < 2 or band(cn)==band(wn)
                if not band_ok:
                    continue

                # Sadece sayı-sayı mekanizma farkları.
                d_react=float(react.loc[chal.name]-react.loc[weak.name])
                d_micro=float(micro.loc[chal.name]-micro.loc[weak.name])
                d_sleep=float(sleep.loc[chal.name]-sleep.loc[weak.name])
                d_gap6=float(gap6.loc[chal.name]-gap6.loc[weak.name])
                d_expert=float(expert.loc[chal.name]-expert.loc[weak.name])

                # Simülasyonda temiz kalan C mekanizması:
                # 31 itirazda 7 vaka -> 3 kazanç / 0 kayıp / 4 eşit.
                react_jump = d_react >= 0.50
                micro_not_worse = d_micro >= 0.00
                return_preserved = d_sleep >= -0.40 and d_gap6 >= -0.40
                consensus_not_inflated = d_expert <= (3.0/8.0)  # normalize +3 uzman oyu

                # Negatif kanıt sadece güvenlik vetosu; skor/terfi kaynağı değildir.
                chal_neg=float(neg.loc[chal.name]) if chal.name in neg.index else 0.0
                clean_challenger = chal_neg < 0.18

                if not (react_jump and micro_not_worse and return_preserved and
                        consensus_not_inflated and clean_challenger):
                    continue

                # Faz artık aday üretmez; yalnız dar bir güvenlik filtresi.
                phase_ok=True
                if t=="23:52":
                    # Return'ın güçlü olduğu fazda dönüş mekanizması daha fazla korunmalı.
                    phase_ok = d_sleep >= -0.20 and d_gap6 >= -0.20
                elif t=="23:57":
                    # Kapanışta reaktivasyon sinyali daha net olmalı.
                    phase_ok = d_react >= 0.65
                if not phase_ok:
                    continue

                # Mahkeme sıralaması TOPLAM SKOR DEĞİL:
                # 1) reaktivasyon sıçraması, 2) mikro kanıt farkı,
                # 3) return mekanizmasının ne kadar korunduğu.
                preservation=min(d_sleep,d_gap6)
                qualified.append({
                    "weak_n":wn,
                    "challenger_n":cn,
                    "d_react":d_react,
                    "d_micro":d_micro,
                    "d_sleep":d_sleep,
                    "d_gap6":d_gap6,
                    "d_expert_norm":d_expert,
                    "preservation":preservation,
                })

    v9_swap_meta["swap_opened"]=bool(qualified)

    if qualified:
        # Mekanizma delili en güçlü tek dosya seçilir.
        qualified.sort(
            key=lambda q:(q["d_react"],q["d_micro"],q["preservation"]),
            reverse=True
        )
        case=qualified[0]
        wn=int(case["weak_n"]); cn=int(case["challenger_n"])

        selected=[cn if n==wn else n for n in selected]
        v9_swap_meta.update({
            "swap_applied":True,
            "weak_n":wn,
            "challenger_n":cn,
            "reason":"V9.5_REAKTIVASYON_MAHKEMESI_KABUL",
            "d_react":case["d_react"],
            "d_micro":case["d_micro"],
            "d_sleep":case["d_sleep"],
            "d_gap6":case["d_gap6"],
            "d_expert_norm":case["d_expert_norm"],
            "qualified_case_count":len(qualified),
        })
    else:
        v9_swap_meta.update({
            "swap_applied":False,
            "reason":"V9.5_RED:REAKTIVASYON+MIKRO+RETURN_KORUNUMU_BIRLIKTE_YOK",
            "qualified_case_count":0,
        })

    v9_swap_meta["dynamic_coeffs"]=dyn
    z.attrs["v9_swap_meta"]=v9_swap_meta
    return selected[:size],z

def _v8_role_final(tab, pool, size=5):
    """V8 ROL TABANLI FİNAL — 16→5 GÖZLEMCİ.
    Beş koltuğu aynı skordan doldurmaz; farklı doğru mekanizmalarını temsil eder.
    Roller: Long Return, Reaktivasyon/Küme, Kısa-Orta GAP/Ritim,
    Kanıtlı Carry/Devam, Çatışma Cerrahı.
    """
    z = tab[tab["Sayı"].astype(int).isin(set(map(int, pool)))].copy()

    def C(name, default=0.0):
        if name in z.columns:
            return pd.to_numeric(z[name], errors="coerce").fillna(default)
        return pd.Series(default, index=z.index, dtype=float)

    gap=C("Gap")
    sleep=C("SERİ→UYKU→DÖNÜŞ R")
    gap6=C("GAP-6+ R")
    react=C("Bant Reaktivasyon")
    micro=np.minimum(C("Mikro Bağımsız Kanıt"),4)/4.0
    kret=C("KÜME DÖNÜŞ R")
    same=C("AYNI YAŞAM İZİ R")
    band_score=C("BANT/KOMŞU R")
    rhythm=C("KÜME ZAMAN RİTMİ R")
    hour=C("AYNI SAAT FAZI R")
    ret=C("Return Survival")
    carry=C("TAŞIMA R")
    gap1=C("GAP-1 R"); gap2=C("GAP-2 R"); gap3=C("GAP-3 R")
    main=C("Ana Yüzdelik")
    neg=C("Negatif Kanıt")
    strong=np.minimum(C("Güçlü Oy"),6)/6.0
    expert=np.minimum(C("Uzman Oy"),8)/8.0

    # Rol 1: gerçek uzun dönüş. Salt uzun GAP yeterli değil; uyku-dönüş onayı aranır.
    z["V8_LONG"] = (
        0.36*sleep + 0.22*gap6 + 0.14*ret + 0.10*micro +
        0.10*np.clip((gap-5)/7.0,0,1) + 0.08*hour
    )

    # Tek-hikâye aşırı güven freni: 57 tipi "her return sinyali aynı anda tavan".
    return_stack=((sleep>=0.75)&(gap6>=0.80)&(react>=0.60)&(micro>=0.75)).astype(float)
    z["V8_LONG"] -= 0.12*return_stack

    # Rol 2: reaktivasyon + küme. Küme tek başına seçici değildir.
    z["V8_REACT"] = (
        0.30*react + 0.24*micro + 0.16*kret + 0.12*ret +
        0.10*band_score + 0.08*main
    )
    z["V8_REACT"] -= 0.08*((react<0.30)&(kret>0.80)).astype(float)

    # Rol 3: GAP1-3 + ritim/saat fazı.
    shortmid=np.maximum.reduce([gap1.to_numpy(),gap2.to_numpy(),gap3.to_numpy()])
    z["V8_RHYTHM"] = (
        0.30*shortmid + 0.24*rhythm + 0.18*hour +
        0.12*ret + 0.08*micro + 0.08*main
    )

    # Rol 4: kanıtlı carry/devam. Carry tek başına değil; ritim/yaşam/saat onayı gerekir.
    carry_confirm=np.maximum.reduce([rhythm.to_numpy(),same.to_numpy(),hour.to_numpy()])
    z["V8_CARRY"] = (
        0.32*carry + 0.22*carry_confirm + 0.16*micro +
        0.12*main + 0.10*band_score + 0.08*kret
    )
    z["V8_CARRY"] -= 0.10*((carry>0.65)&(carry_confirm<0.55)).astype(float)

    # Dekoratif konsensüs: çok oy var ama bağımsız mekanizma yoksa ceza.
    consensus=np.clip((0.55*strong+0.45*expert-0.68)/0.32,0,1)
    mechanism=np.maximum.reduce([
        z["V8_LONG"].to_numpy(), z["V8_REACT"].to_numpy(),
        z["V8_RHYTHM"].to_numpy(), z["V8_CARRY"].to_numpy()
    ])
    z["V8_CONFLICT"] = (
        0.42*mechanism + 0.16*micro + 0.12*ret + 0.10*hour +
        0.08*main + 0.06*same + 0.06*kret -
        0.10*consensus - 0.14*neg
    )

    # Her sayı hangi hikâyeye ait? Aynı hikâyeden finali doldurmayı engelle.
    role_cols=["V8_LONG","V8_REACT","V8_RHYTHM","V8_CARRY"]
    arr=z[role_cols].to_numpy()
    z["V8_BEST_ROLE_IDX"]=arr.argmax(axis=1)
    z["V8_BEST_ROLE_SCORE"]=arr.max(axis=1)

    selected=[]
    used_bands=Counter()
    role_taken=Counter()

    def take(role, threshold):
        q=z.sort_values([role,"V8_CONFLICT","Ana Puan"],ascending=False)
        for _,r in q.iterrows():
            n=int(r["Sayı"]); b=band(n)
            if n in selected or used_bands[b]>=2: continue
            if float(r[role])<threshold: continue
            selected.append(n); used_bands[b]+=1; role_taken[role]+=1
            return True
        return False

    # İlk dört koltuk dört farklı mekanizma.
    take("V8_LONG",0.28)
    take("V8_REACT",0.28)
    take("V8_RHYTHM",0.28)
    take("V8_CARRY",0.26)

    # Eksik rol varsa mekanizma skoru ile doldur, fakat aynı dominant rolden en fazla 2 sayı.
    q=z.sort_values(["V8_CONFLICT","V8_BEST_ROLE_SCORE","Ana Puan"],ascending=False)
    for _,r in q.iterrows():
        if len(selected)>=size: break
        n=int(r["Sayı"]); b=band(n)
        role=role_cols[int(r["V8_BEST_ROLE_IDX"])]
        if n in selected or used_bands[b]>=2: continue
        if role_taken[role]>=2: continue
        selected.append(n); used_bands[b]+=1; role_taken[role]+=1

    if len(selected)<size:
        for _,r in q.iterrows():
            n=int(r["Sayı"])
            if n not in selected:
                selected.append(n)
            if len(selected)>=size: break

    return selected[:size]

def _v10_life_final_observer(tab, pool, size=5):
    """V10 YAŞAM FINAL — 16→5 GÖZLEMCİ.

    V8'i değiştirmez. Kısa/orta GAP (1/2/3) yaşam yollarını ayrı ayrı
    değerlendirir; uzun GAP ancak gerçek return kanıtıyla, carry ise bağımsız
    yaşam/ritim desteğiyle final koltuğu alabilir. Bu motor yalnız gözlemci ve
    kör test karşılaştırması içindir.
    """
    z=tab[tab["Sayı"].astype(int).isin(set(map(int,pool)))].copy()
    if z.empty:
        return []

    def C(name, default=0.0):
        if name in z.columns:
            return pd.to_numeric(z[name],errors="coerce").fillna(default)
        return pd.Series(default,index=z.index,dtype=float)

    gap=C("Gap")
    g1=C("GAP-1 R"); g2=C("GAP-2 R"); g3=C("GAP-3 R")
    rhythm=C("KÜME ZAMAN RİTMİ R")
    same=C("AYNI YAŞAM İZİ R")
    kret=C("KÜME DÖNÜŞ R")
    ret=C("Return Survival")
    sleep=C("SERİ→UYKU→DÖNÜŞ R")
    carry=C("Carry Survival")
    cluster=C("Küme Yaşam")
    micro=np.minimum(C("Mikro Bağımsız Kanıt"),4)/4.0
    main=C("Ana Yüzdelik")
    neg=C("Negatif Kanıt")
    dna=C("DNA Return")
    hour=C("AYNI SAAT FAZI R")
    state=(z["Yaşam Durumu"].astype(str) if "Yaşam Durumu" in z.columns
           else pd.Series("",index=z.index))

    # Kısa/orta yaşam: GAP 1/2/3 birbirinin yerine geçmez; her biri kendi rolü.
    z["V10_GAP1"]=(gap==1).astype(float)*(
        0.26*g1+0.20*rhythm+0.16*same+0.12*kret+0.10*ret+0.08*micro+0.08*main
    )
    z["V10_GAP2"]=(gap==2).astype(float)*(
        0.24*g2+0.22*rhythm+0.14*same+0.12*kret+0.12*ret+0.08*micro+0.08*main
    )
    z["V10_GAP3"]=(gap==3).astype(float)*(
        0.24*g3+0.22*rhythm+0.14*same+0.12*kret+0.10*ret+0.10*micro+0.08*main
    )

    # Uzun yaşam: salt GAP uzunluğu seçilme sebebi değildir.
    longproof=np.maximum.reduce([
        ret.to_numpy(),kret.to_numpy(),same.to_numpy(),sleep.to_numpy(),dna.to_numpy()
    ])
    z["V10_LONG"]=(gap>=4).astype(float)*(
        0.22*dna+0.18*ret+0.16*kret+0.14*same+0.12*sleep+0.10*rhythm+0.08*main
    )*np.clip((longproof-0.30)/0.45,0,1)

    # Carry: yaşam/ritim/küme/saat/mikro desteği yoksa koltuk alamaz.
    carryproof=np.maximum.reduce([
        cluster.to_numpy(),same.to_numpy(),rhythm.to_numpy(),micro.to_numpy(),hour.to_numpy()
    ])
    z["V10_CARRY"]=(gap==0).astype(float)*(
        0.30*carry+0.18*cluster+0.14*same+0.12*rhythm+0.10*micro+0.08*hour+0.08*main
    )*np.clip((carryproof-0.38)/0.42,0,1)

    mech=z[["V10_GAP1","V10_GAP2","V10_GAP3","V10_LONG","V10_CARRY"]].to_numpy()
    sm=np.sort(mech,axis=1)[:,::-1]
    z["V10_FINAL"]=(
        0.52*sm[:,0]+0.18*sm[:,1]+0.12*micro+0.08*main+
        0.06*ret+0.04*rhythm-0.18*neg
    )
    z.loc[state.eq("YENİ/GERİ AKTİF"),"V10_FINAL"]-=0.10
    z.loc[state.eq("DEVAM/SERİ") & (carryproof<0.62),"V10_FINAL"]-=0.08

    selected=[]; bc=Counter()
    # İlk dört koltuk: üç kısa/orta yaşam + bir kanıtlı uzun dönüş.
    roles=["V10_GAP1","V10_GAP2","V10_GAP3","V10_LONG"]
    thresholds={"V10_GAP1":0.20,"V10_GAP2":0.20,"V10_GAP3":0.20,"V10_LONG":0.18}
    for role in roles:
        q=z.sort_values([role,"V10_FINAL","Ana Puan"],ascending=False)
        for _,r in q.iterrows():
            n=int(r["Sayı"]); b=band(n)
            if n in selected or bc[b]>=2 or float(r[role])<thresholds[role]:
                continue
            selected.append(n); bc[b]+=1; break

    # Beşinci koltuk: tüm yaşam mekanizmaları arasında en güçlü çatışma kazananı.
    q=z.sort_values(["V10_FINAL","V10_GAP2","V10_GAP1","V10_GAP3","V10_LONG","Ana Puan"],ascending=False)
    for _,r in q.iterrows():
        if len(selected)>=size: break
        n=int(r["Sayı"]); b=band(n)
        if n in selected or bc[b]>=2: continue
        selected.append(n); bc[b]+=1

    if len(selected)<size:
        for n in q["Sayı"].astype(int):
            if n not in selected: selected.append(n)
            if len(selected)>=size: break
    return selected[:size]

def _v7_final_surgeon(tab, pool, size=5):
    """V7 FİNAL CERRAHI — 16→5/4 GÖZLEMCİ

    Son kör kadavra:
    - Pozitif ana yol: SERİ→UYKU→DÖNÜŞ + GAP6+
    - İkinci pozitif yol: Bant Reaktivasyon + Mikro Bağımsız Kanıt
    - Küme Dönüş / Aynı Yaşam / Bant-Komşu / yüksek oy tek başına final koltuğu vermez
    - Kaçan doğru kurtarma: GAP1–5 + Küme Zaman Ritmi + bağımsız kanıt
    """
    z = tab[tab["Sayı"].astype(int).isin(set(map(int, pool)))].copy()

    def C(name, default=0.0):
        if name in z.columns:
            return pd.to_numeric(z[name], errors="coerce").fillna(default)
        return pd.Series(default, index=z.index, dtype=float)

    gap = C("Gap")
    sleepret = C("SERİ→UYKU→DÖNÜŞ R")
    gap6 = C("GAP-6+ R")
    react = C("Bant Reaktivasyon")
    micro = np.minimum(C("Mikro Bağımsız Kanıt"), 4) / 4.0
    rhythm = C("KÜME ZAMAN RİTMİ R")
    ret = C("Return Survival")
    same = C("AYNI YAŞAM İZİ R")
    kret = C("KÜME DÖNÜŞ R")
    bandkom = C("BANT/KOMŞU R")
    strong_votes = np.minimum(C("Güçlü Oy"), 6) / 6.0
    expert_votes = np.minimum(C("Uzman Oy"), 8) / 8.0
    neg = C("Negatif Kanıt")
    main = C("Ana Yüzdelik")

    # 1) Uzun GAP + uyku-dönüş gerçek final yolu.
    z["V7_LONG_RETURN"] = (
        0.32 * sleepret +
        0.22 * gap6 +
        0.18 * np.clip((gap - 4) / 5.0, 0, 1) +
        0.12 * ret +
        0.08 * micro +
        0.08 * main
    )

    # 2) Bant reaktivasyon + mikro bağımsız kanıt.
    z["V7_REACT_MICRO"] = (
        0.34 * react +
        0.30 * micro +
        0.14 * ret +
        0.10 * main +
        0.12 * np.clip((gap - 2) / 5.0, 0, 1)
    )

    # 3) Kaçan doğru kurtarma yolu:
    # orta GAP + küme zaman ritmi + bağımsız kanıt.
    mid_gap = ((gap >= 1) & (gap <= 5)).astype(float)
    z["V7_RESCUE_MID"] = (
        mid_gap * (
            0.34 * rhythm +
            0.26 * micro +
            0.16 * ret +
            0.12 * main +
            0.12 * np.maximum(same, kret)
        )
    )

    # 4) Yaşam/küme yalnız destekleyici; tek başına final terfisi yok.
    z["V7_TRACE_SUPPORT"] = (
        0.24 * same +
        0.22 * kret +
        0.16 * rhythm +
        0.14 * ret +
        0.12 * micro +
        0.12 * react
    )

    # Aşırı konsensüs / "çok motor seviyor" freni.
    consensus_over = np.clip((0.55 * strong_votes + 0.45 * expert_votes - 0.65) / 0.35, 0, 1)

    # KümeDönüş / AynıYaşam / Bant-Komşu yüksek ama gerçek bağımsız yol zayıfsa fren.
    decorative = np.maximum.reduce([kret.to_numpy(), same.to_numpy(), bandkom.to_numpy()])
    real_path = np.maximum.reduce([
        z["V7_LONG_RETURN"].to_numpy(),
        z["V7_REACT_MICRO"].to_numpy(),
        z["V7_RESCUE_MID"].to_numpy()
    ])
    decorative_brake = np.clip((decorative - 0.65) / 0.35, 0, 1) * np.clip((0.48 - real_path) / 0.48, 0, 1)

    paths = np.vstack([
        z["V7_LONG_RETURN"].to_numpy(),
        z["V7_REACT_MICRO"].to_numpy(),
        z["V7_RESCUE_MID"].to_numpy(),
        z["V7_TRACE_SUPPORT"].to_numpy()
    ]).T
    ps = np.sort(paths, axis=1)[:, ::-1]

    z["V7_FINAL_SCORE"] = (
        0.38 * ps[:, 0] +
        0.24 * ps[:, 1] +
        0.14 * micro +
        0.08 * main +
        0.08 * z["V7_RESCUE_MID"] +
        0.08 * z["V7_REACT_MICRO"] -
        0.12 * consensus_over -
        0.10 * decorative_brake -
        0.16 * neg
    )

    roles = ["V7_LONG_RETURN", "V7_REACT_MICRO", "V7_RESCUE_MID"]
    selected = []
    used_bands = Counter()

    def pick(role, min_score):
        q = z.sort_values([role, "V7_FINAL_SCORE", "Ana Puan"], ascending=False)
        for _, r in q.iterrows():
            n = int(r["Sayı"])
            b = band(n)
            if n in selected or used_bands[b] >= 2:
                continue
            if float(r[role]) < min_score:
                continue
            selected.append(n)
            used_bands[b] += 1
            return True
        return False

    pick("V7_LONG_RETURN", 0.30)
    pick("V7_REACT_MICRO", 0.28)
    pick("V7_RESCUE_MID", 0.28)

    # 4. koltuk ve 5. koltuk: çatışma cerrahı.
    q = z.sort_values(
        ["V7_FINAL_SCORE", "V7_LONG_RETURN", "V7_RESCUE_MID", "Ana Puan"],
        ascending=False
    )
    for _, r in q.iterrows():
        n = int(r["Sayı"])
        b = band(n)
        if n in selected or used_bands[b] >= 2:
            continue
        selected.append(n)
        used_bands[b] += 1
        if len(selected) >= size:
            break

    if len(selected) < size:
        for n in q["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected) >= size:
                break

    return selected[:size]

def _motor_harmony_observer(tab, dna_pool, size=16):
    """V6 MOTOR AKOR BEYNİ — bounded observer.
    Motor sayısını değil, motorların birlikte anlattığı mekanizmayı ölçer.
    Mayıs kalibrasyonunda iki ayrı günde aynı yönde kalan çiftler kullanılır.
    Kör holdoutta üstünlük kanıtlanmadığı için DNA Havuzun yerine geçmez;
    yalnız ayrı gözlemci havuz üretir.
    """
    z=tab.copy()

    POS={
        ("KÜME DÖNÜŞ","KÜME ZAMAN RİTMİ"):0.037,
        ("GAP-1","KÜME DÖNÜŞ"):0.037,
        ("KÜME DÖNÜŞ","BANT/KOMŞU"):0.027,
        ("AYNI YAŞAM İZİ","GECE KARAKTER"):0.016,
    }
    NEG={
        ("TAŞIMA","GECE KARAKTER"):-0.057,
        ("KÜME TAŞIMA","ARDIŞIK/+2/+3"):-0.047,
        ("KÜME TAŞIMA","BANT/KOMŞU"):-0.047,
        ("TAŞIMA","BANT/KOMŞU"):-0.046,
        ("TAŞIMA","AYNI SAAT FAZI"):-0.043,
        ("KÜME TAŞIMA","GECE KARAKTER"):-0.040,
        ("KÜME ZAMAN RİTMİ","AYNI SAAT FAZI"):-0.039,
    }

    def strong(name):
        rc=name+" R"; ac=name+" Yetkili"
        if rc not in z.columns or ac not in z.columns:
            return pd.Series(False,index=z.index)
        r=pd.to_numeric(z[rc],errors="coerce").fillna(0)
        a=pd.to_numeric(z[ac],errors="coerce").fillna(0)>0
        return a & (r>=0.68)

    harmony=pd.Series(0.0,index=z.index)
    reasons=[[] for _ in range(len(z))]
    for (a,b),w in {**POS,**NEG}.items():
        mask=strong(a)&strong(b)
        harmony += mask.astype(float)*w
        tag=("+" if w>0 else "")+f"{a}×{b}"
        for j,flag in enumerate(mask.to_numpy()):
            if flag: reasons[j].append(tag)

    # Aşırı konsensüs otomatik üstünlük değildir.
    names=["TAŞIMA","YENİ AKTİVASYON→TAŞIMA","GAP-1","GAP-2","GAP-3","GAP-4/5","GAP-6+",
           "SERİ→UYKU→DÖNÜŞ","KÜME TAŞIMA","KÜME DÖNÜŞ","AYNI YAŞAM İZİ","KÜME ZAMAN RİTMİ",
           "ARDIŞIK/+2/+3","BANT/KOMŞU","AYNI SAAT FAZI","GECE KARAKTER"]
    cnt=pd.Series(0,index=z.index,dtype=int)
    for n in names: cnt += strong(n).astype(int)
    harmony -= (cnt>=7).astype(float)*0.025

    # Akor katmanı küçük tutulur: temel DNA skorunu ezemez.
    harmony=harmony.clip(-0.10,0.10)
    z["Motor Akor"]=harmony
    z["Motor Akor Sayısı"]=cnt
    z["Motor Akor Yol"]=[" | ".join(x) if x else "NÖTR" for x in reasons]
    z["Akor Havuz Skor"]=pd.to_numeric(z["DNA Havuz Skor"],errors="coerce").fillna(0)+harmony

    base_set=set(map(int,dna_pool))
    # DNA havuz üyelerine çok küçük süreklilik koruması.
    z["Akor Havuz Skor"] += z["Sayı"].astype(int).isin(base_set).astype(float)*0.010

    q=z.sort_values(["Akor Havuz Skor","DNA Return","Ana Puan"],ascending=False)
    chosen=[]; bc=Counter()
    for _,r in q.iterrows():
        n=int(r["Sayı"]); b=band(n)
        if bc[b]>=3: continue
        chosen.append(n); bc[b]+=1
        if len(chosen)>=size: break
    if len(chosen)<size:
        for n in q["Sayı"].astype(int):
            if n not in chosen: chosen.append(n)
            if len(chosen)>=size: break
    return chosen[:size],z

def _dna_pool16_observer(tab, unified_pool, size=16):
    """DNA Havuz Beyni — yalnız gözlemci.
    V3 birleşik havuzu temel alır; doğrulanmış return yaşam yollarını korur,
    carry/sıcaklığı tek başına terfi sebebi yapmaz.
    """
    z=tab.copy()
    def C(n,d=0.0):
        if n in z.columns:
            return pd.to_numeric(z[n],errors="coerce").fillna(d)
        return pd.Series(d,index=z.index,dtype=float)

    gap=C("Gap"); same=C("AYNI YAŞAM İZİ R"); kret=C("KÜME DÖNÜŞ R")
    ret=C("Return Survival"); sleep=C("Seri→Uzun Uyku")
    micro=np.minimum(C("Mikro Bağımsız Kanıt"),4)/4.0
    neg=C("Negatif Kanıt"); carry=C("Carry Survival"); cluster=C("Küme Yaşam")

    dna1=((gap>=6).astype(float))*np.minimum(kret/0.45,1.0)
    dna2=np.minimum(sleep,1.0)*np.minimum(same/0.45,1.0)
    dna3=((gap>=6).astype(float))*np.minimum(same/0.45,1.0)
    dna4=np.minimum(kret/0.65,1.0)*np.minimum(same/0.65,1.0)
    dna5=np.minimum(sleep,1.0)*np.minimum(kret/0.45,1.0)
    return_votes=((ret>=0.35).astype(int)+(kret>=0.45).astype(int)+
                  (same>=0.45).astype(int)+(sleep>=1).astype(int))
    dna6=((gap>=6).astype(float))*np.minimum(return_votes/2.0,1.0)

    z["DNA Return"]=(0.24*dna1+0.20*dna2+0.18*dna3+0.16*dna4+0.12*dna5+0.10*dna6)
    # GAP0/carry ancak bağımsız destek varsa nötrleşebilir; avantaj sayılmaz.
    carry_gate=np.maximum(cluster,micro)
    carry_pen=((gap==0).astype(float))*np.clip((0.55-carry_gate)/0.45,0,1)
    gap1_pen=((gap==1).astype(float))*np.clip((0.50-np.maximum(kret,same))/0.40,0,1)
    base=C("Tek Beyin Skor")
    z["DNA Havuz Skor"]=base+0.18*z["DNA Return"]-0.10*carry_pen-0.07*gap1_pen-0.12*neg

    # V3 havuz üyelerine küçük koruma; DNA yalnız sınır cerrahisi yapar.
    base_set=set(map(int,unified_pool))
    z["DNA Havuz Skor"] += z["Sayı"].astype(int).isin(base_set).astype(float)*0.025

    q=z.sort_values(["DNA Havuz Skor","DNA Return","Bağımsız Aile","Ana Puan"],ascending=False)
    chosen=[]; bc=Counter()
    for _,r in q.iterrows():
        n=int(r["Sayı"]); b=band(n)
        if bc[b]>=3: continue
        chosen.append(n); bc[b]+=1
        if len(chosen)>=size: break
    if len(chosen)<size:
        for n in q["Sayı"].astype(int):
            if n not in chosen: chosen.append(n)
            if len(chosen)>=size: break
    return chosen[:size],z


def _dna_ticket_brain(tab,pool,size=5):
    """V5 KOLON CERRAHI — 16→4/5 GÖZLEMCİ

    Kadavra prensibi:
    - ham Uzman/Güçlü Oy çoğunluğu koltuk garantisi değildir
    - uzun GAP + return / uyku→dönüş için ayrı koltuk
    - yaşam izi + küme dönüş için ayrı koltuk
    - carry ancak ikinci bağımsız kanıtla girebilir
    - son koltuk çatışma cerrahıdır
    """
    z=tab[tab["Sayı"].astype(int).isin(set(map(int,pool)))].copy()

    def C(n,d=0.0):
        if n in z.columns:
            return pd.to_numeric(z[n],errors="coerce").fillna(d)
        return pd.Series(d,index=z.index,dtype=float)

    gap=C("Gap")
    same=C("AYNI YAŞAM İZİ R")
    kret=C("KÜME DÖNÜŞ R")
    ret=C("Return Survival")
    sleep=C("Seri→Uzun Uyku")
    sleepret=C("SERİ→UYKU→DÖNÜŞ R")
    carry=C("Carry Survival")
    cluster=C("Küme Yaşam")
    kcarry=C("KÜME TAŞIMA R")
    seq=C("ARDIŞIK/+2/+3 R")
    rhythm=C("KÜME ZAMAN RİTMİ R")
    micro=np.minimum(C("Mikro Bağımsız Kanıt"),4)/4.0
    fam=np.minimum(C("Bağımsız Aile"),4)/4.0
    strong=np.minimum(C("Güçlü Aile"),3)/3.0
    neg=C("Negatif Kanıt")
    dna=C("DNA Return")
    main=C("Ana Yüzdelik")

    # 1) Uzun GAP / gerçek return koltuğu.
    long_gap=np.clip((gap-3)/5.0,0,1)
    z["V5_RETURN"]=(
        0.24*long_gap + 0.20*dna + 0.16*ret + 0.14*kret +
        0.12*same + 0.08*sleepret + 0.06*np.minimum(sleep,1)
    )

    # 2) Uyku → dönüş koltuğu. Ham oy sayısından bağımsız.
    z["V5_SLEEP_RETURN"]=(
        0.28*np.minimum(sleep,1)+0.22*sleepret+0.18*long_gap+
        0.14*same+0.10*kret+0.08*ret
    )

    # 3) Yaşam izi / küme koltuğu.
    z["V5_TRACE_CLUSTER"]=(
        0.30*same+0.24*kret+0.16*rhythm+0.12*cluster+
        0.10*seq+0.08*ret
    )

    # 4) Carry: mutlaka ikinci bağımsız kanıt.
    carry_second=np.maximum.reduce([
        cluster.to_numpy(), kcarry.to_numpy(), micro.to_numpy(),
        seq.to_numpy(), same.to_numpy()
    ])
    carry_gate=np.clip((carry_second-0.38)/0.42,0,1)
    z["V5_CARRY"]=(
        0.34*carry+0.20*cluster+0.14*kcarry+0.12*micro+
        0.10*seq+0.10*same
    )*carry_gate

    # Konsensüs sadece yardımcı kanıt; artık ana seçim motoru değil.
    consensus=0.55*micro+0.30*fam+0.15*strong

    # Cerrah: iki farklı mekanizmanın beraber desteklediği adayları sever.
    mech=np.vstack([
        z["V5_RETURN"].to_numpy(),
        z["V5_SLEEP_RETURN"].to_numpy(),
        z["V5_TRACE_CLUSTER"].to_numpy(),
        z["V5_CARRY"].to_numpy()
    ]).T
    sm=np.sort(mech,axis=1)[:,::-1]
    z["V5_SURGEON"]=(
        0.42*sm[:,0]+0.28*sm[:,1]+0.12*consensus+
        0.08*dna+0.05*main-0.20*neg
    )

    # Kadavrada kaçan doğruların uzun-GAP/return izini koru.
    z["V5_RESCUE"]=(
        (gap>=4).astype(float) *
        np.clip((z["V5_RETURN"]+z["V5_SLEEP_RETURN"]+z["V5_TRACE_CLUSTER"]-0.95)/1.10,0,1)
    )
    z["V5_SURGEON"] += 0.12*z["V5_RESCUE"]

    # GAP0/GAP1 aday sırf konsensüs yüksek diye uzun-GAP dönüş adayını ezmesin.
    shallow=((gap<=1).astype(float) *
             np.clip((0.48-np.maximum(z["V5_CARRY"],z["V5_TRACE_CLUSTER"]))/0.38,0,1))
    z["V5_SURGEON"] -= 0.10*shallow

    # Rol koltukları. 4'lü: return, sleep-return, trace-cluster, cerrah.
    # 5'li: bunlara doğrulanmış carry koltuğu eklenir; carry yoksa cerrah doldurur.
    roles=["V5_RETURN","V5_SLEEP_RETURN","V5_TRACE_CLUSTER"]
    if size>=5:
        roles.append("V5_CARRY")

    selected=[]
    used_bands=Counter()

    def pick_role(role):
        q=z.sort_values([role,"V5_SURGEON","V5_RESCUE","Ana Puan"],ascending=False)
        for _,r in q.iterrows():
            n=int(r["Sayı"]); b=band(n)
            if n in selected or used_bands[b]>=2:
                continue
            if role=="V5_CARRY" and float(r[role])<0.36:
                continue
            # Bir rol gerçekten konuşmuyorsa zorla koltuk doldurma.
            if role!="V5_CARRY" and float(r[role])<0.28:
                continue
            selected.append(n); used_bands[b]+=1
            return True
        return False

    for role in roles:
        pick_role(role)
        if len(selected)>=size:
            break

    # Eksik ve son koltuklar çatışma cerrahı.
    q=z.sort_values(["V5_SURGEON","V5_RESCUE","DNA Return","Ana Puan"],ascending=False)
    for _,r in q.iterrows():
        n=int(r["Sayı"]); b=band(n)
        if n in selected or used_bands[b]>=2:
            continue
        selected.append(n); used_bands[b]+=1
        if len(selected)>=size:
            break

    if len(selected)<size:
        for n in q["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected)>=size:
                break

    return selected[:size]


def _ticket_from_pool(tab,pool,size,variant=0):
    # 16 -> 4/5 ikinci beyin.
    z=tab[tab["Sayı"].isin(pool)].copy()
    # Terfi için aile genişliği, iki güçlü aile, rol içi şampiyonluk ve yaşam çeşitliliği.
    z["Terfi Kanıtı"] = (
        0.42*z["Bağımsız Aile"] +
        0.28*z["Güçlü Aile"] +
        0.20*z["Ana Yüzdelik"] +
        0.10*np.minimum(z["Uzman Oy"],5)/5
    )
    z=z.sort_values(["Terfi Kanıtı","Bağımsız Aile","Güçlü Aile","Ana Puan"],ascending=False)
    if variant:
        z=pd.concat([z.iloc[variant:],z.iloc[:variant]],ignore_index=True)

    selected=[]; bands=Counter(); states=Counter()
    for _,r in z.iterrows():
        n=int(r["Sayı"]); b=band(n); state=str(r["Yaşam Durumu"])
        # küçük kuponu tek banda/tek yaşam tipine kilitleme
        if bands[b]>=2: continue
        if states[state]>=2: continue
        # tek aileli aday kupona ancak son çare olarak girer
        if int(r["Bağımsız Aile"])<=1 and len(selected)<size-1: continue
        selected.append(n); bands[b]+=1; states[state]+=1
        if len(selected)>=size: break
    if len(selected)<size:
        for n in z["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected)>=size: break
    return selected

def surgery_observer_v26(tab,base5):
    z=tab.set_index("Sayı")
    # Cerrahi: düşük aile genişliği + dışarıda daha güçlü bağımsız kanıt.
    weakest=min(base5,key=lambda n:(int(z.loc[n,"Bağımsız Aile"]),
                                   int(z.loc[n,"Güçlü Aile"]),
                                   float(z.loc[n,"Ana Puan"])))
    outs=[int(n) for n in tab.head(16)["Sayı"] if int(n) not in base5]
    entry=None
    for n in outs:
        if int(z.loc[n,"Bağımsız Aile"]) >= int(z.loc[weakest,"Bağımsız Aile"])+1 and \
           int(z.loc[n,"Güçlü Aile"]) >= int(z.loc[weakest,"Güçlü Aile"]):
            entry=n; break
    triple=entry is not None and int(z.loc[weakest,"Bağımsız Aile"])<=2
    exp=base5.copy()
    if triple:
        exp[exp.index(weakest)]=entry
    return {
        "exit":int(weakest),"entry":int(entry) if entry is not None else None,
        "triple_lock":bool(triple),"base5":base5,"experimental5":exp,
        "note":"V26 cerrahi yalnız Havuz16 içindeki bağımsız kanıt farkına itiraz eder; yeni aday üretmez."
    }

def predict(df,target_time,brain=None):
    brain=brain or _default_brain()
    tab,char,w,mh,bw=expert_table_brain(df,target_time,brain)
    pool16,tab,seat_reason=_pool16_two_stage(tab,char,16)
    pool16_v2,pool16_v2_reason=_pool16_v2_observer(tab,char,16)
    pool16_day_league,day_league_meta=_pool16_day_league_observer(tab,df,target_time,brain,16)
    pool16_twin,twin_swaps,tab=_twin_boundary_surgeon_observer(df,tab,pool16,2,0.5)
    pool16_unified,unified_meta,tab=_unified_brain_observer(df,tab,char,16)
    pool16_dna,tab=_dna_pool16_observer(tab,pool16_unified,16)
    pool16_akor,tab=_motor_harmony_observer(tab,pool16_dna,16)
    dna4=_dna_ticket_brain(tab,pool16_dna,4)
    dna5=_dna_ticket_brain(tab,pool16_dna,5)
    akor4=_dna_ticket_brain(tab,pool16_akor,4)
    akor5=_dna_ticket_brain(tab,pool16_akor,5)
    v7final4=_v7_final_surgeon(tab,pool16_akor,4)
    v7final5=_v7_final_surgeon(tab,pool16_akor,5)
    v8final4=_v8_role_final(tab,pool16_akor,4)
    v8final5=_v8_role_final(tab,pool16_akor,5)
    # V10 yaşam final yalnız gözlemci; V8/V9 veya canlı kuponu değiştirmez.
    v10final4=_v10_life_final_observer(tab,pool16_akor,4)
    v10final5=_v10_life_final_observer(tab,pool16_akor,5)
    # V9 yalnız Akor Havuz16 alt-kümesinde çalışır.
    # KRİTİK: V9'un 16 satırlık alt tablosu ana 80-satırlık `tab` değişkeninin üstüne YAZILMAZ.
    # Aksi halde aşağıdaki canlı kuponlar ve kör otopsi yalnız 16 satır görür ve z.loc[n] KeyError üretir.
    v9final4,_v9tab4=_v9_dynamic_conductor(df,tab,pool16_akor,v7final4,target_time,4)
    v9final5,_v9tab5=_v9_dynamic_conductor(df,tab,pool16_akor,v7final5,target_time,5)
    # BAĞIMSIZ5: V10 dışında son kör pakette en yüksek toplamı veren V9.5 motorunun
    # ayrı 5'li kuponudur. V10 ana kuponuna dokunmaz.
    independent5=list(map(int,v9final5))
    v9meta=dict(_v9tab5.attrs.get("v9_swap_meta",{}))

    # V9 tanı sütunlarını ana 80'lik tabloya yalnız sayı anahtarıyla geri taşı.
    # Havuz dışındaki sayılar NaN/0 kalır; ana tablo boyutu ve eski motorlar korunur.
    _v9diag_cols=[
        "V9_RETURN_FAMILY","V9_SHORT_FAMILY","V9_REACT_FAMILY",
        "V9_CARRY_FAMILY","V9_SCORE"
    ]
    _v9idx=_v9tab5.set_index("Sayı")
    for _c in _v9diag_cols:
        if _c in _v9idx.columns:
            tab[_c]=tab["Sayı"].map(_v9idx[_c]).fillna(0.0)

    core4=_ticket_from_pool(tab,pool16,4,0)
    alt4=_ticket_from_pool(tab,pool16,4,1)
    core5=_ticket_from_pool(tab,pool16,5,0)
    alt5=_ticket_from_pool(tab,pool16,5,1)

    surg=surgery_observer_v26(tab,core5)
    approved,delta=surgery_gate(brain)
    surg["brain_approved"]=approved
    surg["mean_delta"]=delta
    surg["live5"]=surg["experimental5"] if (approved and surg["triple_lock"]) else core5

    return {
        "tab":tab,"char":char,"weights":w,"brain_weights":bw,"mech_hist":mh,
        "core4":core4,"alt4":alt4,"core5":core5,"alt5":alt5,
        "pool16":pool16,"pool_reason":seat_reason,
        "pool16_v2":pool16_v2,"pool16_v2_reason":pool16_v2_reason,
        "pool16_day_league":pool16_day_league,"day_league_meta":day_league_meta,
        "pool16_twin":pool16_twin,"twin_swaps":twin_swaps,
        "pool16_unified":pool16_unified,"unified_meta":unified_meta,
        "pool16_dna":pool16_dna,"dna4":dna4,"dna5":dna5,
        "pool16_akor":pool16_akor,"akor4":akor4,"akor5":akor5,
        "v7final4":v7final4,"v7final5":v7final5,
        "v8final4":v8final4,"v8final5":v8final5,
        "v10final4":v10final4,"v10final5":v10final5,
        "v9final4":v9final4,"v9final5":v9final5,"independent5":independent5,"v9meta":v9meta,
        "active_experts":_active_experts(tab,char),
        "surgery":surg
    }

# make_snapshot override: Havuz16 artık V26'nın iki aşamalı havuzudur.
def make_snapshot(p,target_draw,target_date,target_time):
    expert_top5={}
    for e in EXPERTS:
        q=p["tab"][p["tab"][e+" Yetkili"]==1].sort_values(e+" R",ascending=False).head(5)
        expert_top5[e]=q["Sayı"].astype(int).tolist()
    top_rows=[]
    for _,r in p["tab"].head(30).iterrows():
        top_rows.append({
            "Sayı":int(r["Sayı"]),"Ana Puan":float(r["Ana Puan"]),
            "Uzman Oy":int(r["Uzman Oy"]),"Güçlü Oy":int(r["Güçlü Oy"]),
            "Bağımsız Aile":int(r["Bağımsız Aile"]),"Güçlü Aile":int(r["Güçlü Aile"]),
            "Gap":int(r["Gap"]),"Yaşam İzi":str(r["Yaşam İzi"]),
            "Yaşam Durumu":str(r["Yaşam Durumu"]),"Kaynaklar":str(r["Kaynaklar"])
        })
    return {
        "target_draw":int(target_draw),"target_date":str(target_date),"target_time":str(target_time),
        "night_character":p["char"]["label"],"core4":p["core4"],"alt4":p["alt4"],
        "core5":p["core5"],"alt5":p["alt5"],"live5":p["surgery"]["live5"],
        "v5_dna4":p.get("dna4",[]),"v5_dna5":p.get("dna5",[]),
        "v6_akor4":p.get("akor4",[]),"v6_akor5":p.get("akor5",[]),
        "v7_final4":p.get("v7final4",[]),"v7_final5":p.get("v7final5",[]),
        "v8_final4":p.get("v8final4",[]),"v8_final5":p.get("v8final5",[]),
        "v9_final4":p.get("v9final4",[]),"v9_final5":p.get("v9final5",[]),
        "v10_final4":p.get("v10final4",[]),"v10_final5":p.get("v10final5",[]),
        "independent5":p.get("independent5",p.get("v9final5",[])),
        "pool12":p["pool16"][:12],"pool16":p["pool16"],
        "pool16_dna":p.get("pool16_dna",[]),"pool16_akor":p.get("pool16_akor",[]),
        "pool30":p["tab"].head(30)["Sayı"].astype(int).tolist(),
        "expert_top5":expert_top5,"top_rows":top_rows,
        "surgery":{"base5":p["surgery"]["base5"],"experimental5":p["surgery"]["experimental5"],
                   "triple_lock":bool(p["surgery"]["triple_lock"]),
                   "exit":p["surgery"]["exit"],"entry":p["surgery"]["entry"]}
    }

# Blind test override: V26 havuzunu ayrıca detaylı kaydeder.
def blind_test(df,ntest=40,min_train=120):
    rows=[]; simbrain=_default_brain(); start=max(min_train,len(df)-ntest)
    for i in range(start,len(df)):
        train=df.iloc[:i].reset_index(drop=True)
        if len(train)<min_train: continue
        target=df.iloc[i]
        try:
            p=predict(train,target["time"],simbrain)
        except Exception:
            continue
        actual=set(target["numbers"])
        snap=make_snapshot(p,int(target["draw_no"]),target["date"],target["time"])
        pool16=list(map(int,p["pool16"]))
        h16=sorted(set(pool16)&actual)
        pool16_v2=list(map(int,p.get("pool16_v2",[])))
        h16_v2=sorted(set(pool16_v2)&actual)
        pool16_league=list(map(int,p.get("pool16_day_league",[])))
        h16_league=sorted(set(pool16_league)&actual)
        pool16_twin=list(map(int,p.get("pool16_twin",[])))
        h16_twin=sorted(set(pool16_twin)&actual)
        pool16_unified=list(map(int,p.get("pool16_unified",[])))
        h16_unified=sorted(set(pool16_unified)&actual)
        pool16_dna=list(map(int,p.get("pool16_dna",[])))
        h16_dna=sorted(set(pool16_dna)&actual)
        dna4=list(map(int,p.get("dna4",[]))); hdna4=sorted(set(dna4)&actual)
        dna5=list(map(int,p.get("dna5",[]))); hdna5=sorted(set(dna5)&actual)
        pool16_akor=list(map(int,p.get("pool16_akor",[])))
        h16_akor=sorted(set(pool16_akor)&actual)
        akor4=list(map(int,p.get("akor4",[]))); hakor4=sorted(set(akor4)&actual)
        akor5=list(map(int,p.get("akor5",[]))); hakor5=sorted(set(akor5)&actual)
        v7f4=list(map(int,p.get("v7final4",[]))); hv7f4=sorted(set(v7f4)&actual)
        v7f5=list(map(int,p.get("v7final5",[]))); hv7f5=sorted(set(v7f5)&actual)
        v8f4=list(map(int,p.get("v8final4",[]))); hv8f4=sorted(set(v8f4)&actual)
        v8f5=list(map(int,p.get("v8final5",[]))); hv8f5=sorted(set(v8f5)&actual)
        v10f4=list(map(int,p.get("v10final4",[]))); hv10f4=sorted(set(v10f4)&actual)
        v10f5=list(map(int,p.get("v10final5",[]))); hv10f5=sorted(set(v10f5)&actual)
        v9f4=list(map(int,p.get("v9final4",[]))); hv9f4=sorted(set(v9f4)&actual)
        v9f5=list(map(int,p.get("v9final5",[]))); hv9f5=sorted(set(v9f5)&actual)
        _v9m=p.get("v9meta",{}) or {}
        _v9swap=bool(_v9m.get("swap_applied",False))
        _v9delta=len(hv9f5)-len(hv7f5)
        _v9verdict=("KAZANDI" if _v9swap and _v9delta>0 else
                    "KAYBETTI" if _v9swap and _v9delta<0 else
                    "ESIT" if _v9swap else "SWAP_YOK")
        base5=list(map(int,p["core5"]))
        b5=sorted(set(base5)&actual)
        exp5=list(map(int,p["surgery"]["experimental5"]))
        e5=sorted(set(exp5)&actual)
        live5=list(map(int,p["surgery"]["live5"]))
        l5=sorted(set(live5)&actual)
        missed=[n for n in h16 if n not in base5]
        reasons=[]
        z=p["tab"].set_index("Sayı")
        for n in missed:
            if n not in z.index:
                reasons.append(f"{n}: havuzda doğru; otopsi tablosunda satır bulunamadı")
                continue
            rr=z.loc[n]
            reasons.append(
                f"{n}: havuzda doğru; aile={int(rr['Bağımsız Aile'])}, güçlü={int(rr['Güçlü Aile'])}, "
                f"yaşam={rr['Yaşam Durumu']}; 5 koltuk terfisinde geride kaldı"
            )
        rows.append({
            "Çekiliş":int(target["draw_no"]),"Tarih":target["date"],"Saat":target["time"],
            "Gece":p["char"]["label"],
            "Gün Gözlem":int(p["char"].get("day_seen",0)),
            "Gün Fazı":str(p["char"].get("day_phase","-")),
            "Gün Güven":float(p["char"].get("confidence",0.0)),
            "Gerçek20":"-".join(map(str,sorted(actual))),
            "4 Çekirdek":len(set(p["core4"])&actual),"4 Alternatif":len(set(p["alt4"])&actual),
            "5 Çekirdek":len(b5),"5 Alternatif":len(set(p["alt5"])&actual),
            "Canlı5":len(l5),"Havuz12":len(set(pool16[:12])&actual),"Havuz16":len(h16),
            "V2 Havuz16":len(h16_v2),"V2 Fark":len(h16_v2)-len(h16),
            "Gün Ligi Havuz16":len(h16_league) if pool16_league else np.nan,
            "Gün Ligi Fark":(len(h16_league)-len(h16)) if pool16_league else np.nan,
            "Gün Ligi Top3":" + ".join(p.get("day_league_meta",{}).get("top3",[])),
            "İkiz Cerrah Havuz16":len(h16_twin),
            "İkiz Cerrah Fark":len(h16_twin)-len(h16),
            "İkiz Swap":len(p.get("twin_swaps",[])),
            "Birleşik Beyin Havuz16":len(h16_unified),
            "Birleşik Beyin Fark":len(h16_unified)-len(h16),
            "DNA Havuz16":len(h16_dna),"DNA Havuz16 Fark":len(h16_dna)-len(h16),
            "V5 Kolon 4":len(hdna4),"V5 Kolon 5":len(hdna5),
            "V6 Akor Havuz16":len(h16_akor),"V6 Akor Fark":len(h16_akor)-len(h16_dna),
            "V6 Akor Kolon4":len(hakor4),"V6 Akor Kolon5":len(hakor5),
            "V7 Final4":len(hv7f4),"V7 Final5":len(hv7f5),
            "V8 Rol Final4":len(hv8f4),"V8 Rol Final5":len(hv8f5),
            "V10 Yaşam Final4":len(hv10f4),"V10 Yaşam Final5":len(hv10f5),
            "V10-V8 Final5 Fark":len(hv10f5)-len(hv8f5),
            "V9.5 Reaktivasyon Şefi4":len(hv9f4),"V9.5 Reaktivasyon Şefi5":len(hv9f5),
            "V9.1 Swap Açıldı":int(bool(_v9m.get("swap_opened",False))),
            "V9.1 Swap Uygulandı":int(_v9swap),
            "V9.1 Swap Delta":_v9delta,
            "V9.1 Swap Hüküm":_v9verdict,
            "V9.1 Faz":_v9m.get("phase",""),
            "V9.1 Swap Red/Neden":_v9m.get("reason",""),
            "V9.5 Uygun Dosya Sayısı":_v9m.get("qualified_case_count",0),
            "V9.5 ΔReaktivasyon":_v9m.get("d_react",""),
            "V9.5 ΔMikro":_v9m.get("d_micro",""),
            "V9.5 ΔUykuDönüş":_v9m.get("d_sleep",""),
            "V9.5 ΔGAP6":_v9m.get("d_gap6",""),
            "V9.5 ΔUzmanNorm":_v9m.get("d_expert_norm",""),
            "V9.4 Carry Katsayı":(_v9m.get("dynamic_coeffs",{}) or {}).get("carry",1.0),
            "V9.4 Return Katsayı":(_v9m.get("dynamic_coeffs",{}) or {}).get("return",1.0),
            "V9.4 React Katsayı":(_v9m.get("dynamic_coeffs",{}) or {}).get("react",1.0),
            "V9.4 Ritim Katsayı":(_v9m.get("dynamic_coeffs",{}) or {}).get("rhythm",1.0),
            "V9.4 Geçiş Örnek":(_v9m.get("dynamic_coeffs",{}) or {}).get("sample",0),
            "V9.4 Carry Baz":(_v9m.get("dynamic_coeffs",{}) or {}).get("base_carry",""),
            "V9.4 Return Baz":(_v9m.get("dynamic_coeffs",{}) or {}).get("base_return",""),
            "V9.4 React Baz":(_v9m.get("dynamic_coeffs",{}) or {}).get("base_react",""),
            "V9.4 Ritim Baz":(_v9m.get("dynamic_coeffs",{}) or {}).get("base_rhythm",""),
            "3El Blok Mod":p.get("unified_meta",{}).get("block",{}).get("mode",""),
            "Tek Beyin Faz":p.get("unified_meta",{}).get("phase_policy",{}).get("mode",""),
            "Cerrahi5":len(e5),"CerrahiAçıldı":int(p["surgery"]["triple_lock"]),
            "CerrahiOnaylı":int(p["surgery"]["brain_approved"]),
            "Havuz16 Sayıları":"-".join(map(str,pool16)),
            "Havuz16 Doğruları":"-".join(map(str,h16)),
            "V2 Havuz16 Sayıları":"-".join(map(str,pool16_v2)),
            "V2 Havuz16 Doğruları":"-".join(map(str,h16_v2)),
            "Gün Ligi Havuz16 Sayıları":"-".join(map(str,pool16_league)),
            "Gün Ligi Havuz16 Doğruları":"-".join(map(str,h16_league)),
            "İkiz Cerrah Havuz16 Sayıları":"-".join(map(str,pool16_twin)),
            "İkiz Cerrah Havuz16 Doğruları":"-".join(map(str,h16_twin)),
            "İkiz Cerrah Swap Detay":json.dumps(p.get("twin_swaps",[]),ensure_ascii=False),
            "Birleşik Beyin Havuz16 Sayıları":"-".join(map(str,pool16_unified)),
            "Birleşik Beyin Havuz16 Doğruları":"-".join(map(str,h16_unified)),
            "DNA Havuz16 Sayıları":"-".join(map(str,pool16_dna)),
            "DNA Havuz16 Doğruları":"-".join(map(str,h16_dna)),
            "V6 Akor Havuz16 Sayıları":"-".join(map(str,pool16_akor)),
            "V6 Akor Havuz16 Doğruları":"-".join(map(str,h16_akor)),
            "V6 Akor4 Sayıları":"-".join(map(str,akor4)),"V6 Akor4 Doğruları":"-".join(map(str,hakor4)),
            "V6 Akor5 Sayıları":"-".join(map(str,akor5)),"V6 Akor5 Doğruları":"-".join(map(str,hakor5)),
            "V7 Final4 Sayıları":"-".join(map(str,v7f4)),"V7 Final4 Doğruları":"-".join(map(str,hv7f4)),
            "V7 Final5 Sayıları":"-".join(map(str,v7f5)),"V7 Final5 Doğruları":"-".join(map(str,hv7f5)),
            "V8 Rol Final4 Sayıları":"-".join(map(str,v8f4)),"V8 Rol Final4 Doğruları":"-".join(map(str,hv8f4)),
            "V8 Rol Final5 Sayıları":"-".join(map(str,v8f5)),"V8 Rol Final5 Doğruları":"-".join(map(str,hv8f5)),
            "V10 Yaşam Final4 Sayıları":"-".join(map(str,v10f4)),"V10 Yaşam Final4 Doğruları":"-".join(map(str,hv10f4)),
            "V10 Yaşam Final5 Sayıları":"-".join(map(str,v10f5)),"V10 Yaşam Final5 Doğruları":"-".join(map(str,hv10f5)),
            "V9.5 Reaktivasyon Şefi4 Sayıları":"-".join(map(str,v9f4)),"V9.5 Reaktivasyon Şefi4 Doğruları":"-".join(map(str,hv9f4)),
            "V9.5 Reaktivasyon Şefi5 Sayıları":"-".join(map(str,v9f5)),"V9.5 Reaktivasyon Şefi5 Doğruları":"-".join(map(str,hv9f5)),
            "V9.1 Çıkan Aday":_v9m.get("weak_n",""),
            "V9.1 İtiraz Adayı":_v9m.get("challenger_n",""),
            "V5 Kolon4 Sayıları":"-".join(map(str,dna4)),"V5 Kolon4 Doğruları":"-".join(map(str,hdna4)),
            "V5 Kolon5 Sayıları":"-".join(map(str,dna5)),"V5 Kolon5 Doğruları":"-".join(map(str,hdna5)),
            "3El Blok Aileleri":json.dumps(p.get("unified_meta",{}).get("block",{}).get("families",[]),ensure_ascii=False),
            "Base5 Sayıları":"-".join(map(str,base5)),
            "Base5 Doğruları":"-".join(map(str,b5)),
            "Cerrahi5 Sayıları":"-".join(map(str,exp5)),
            "Cerrahi5 Doğruları":"-".join(map(str,e5)),
            "Canlı5 Sayıları":"-".join(map(str,live5)),
            "Canlı5 Doğruları":"-".join(map(str,l5)),
            "Cerrahi Çıkış":p["surgery"]["exit"],
            "Cerrahi Giriş":p["surgery"]["entry"],
            "Havuz Doğru Ama Base5 Dışı":"-".join(map(str,missed)),
            "Mikro Otopsi":" | ".join(reasons),
        })
        simbrain,_,_=update_brain_from_result(simbrain,snap,actual)

    return pd.DataFrame(rows),simbrain


def blind_micro_autopsy(df, ntest=40, min_train=120):
    """
    GERÇEK KÖR 80-SAYI OTOPSİSİ.
    Her hedefte özellikler yalnız hedeften ÖNCE hesaplanır.
    Gerçek sonuç daha sonra yalnız sınıf etiketi vermek için açılır.
    """
    rows=[]
    simbrain=_default_brain()
    start=max(min_train,len(df)-ntest)

    keep_cols=[
        "Sayı","Ana Puan","Ana Yüzdelik","Bağımsız Aile","Güçlü Aile",
        "Uzman Oy","Güçlü Oy","Gap","Yaşam İzi","Yaşam Durumu",
        "Karar Sınıfı","Mikro Bağımsız Kanıt",
        "Bant","Bant Yoğunluk","Bant Reaktivasyon","Bant Patlama",
        "Bant Daralma","Bant Yaşam","Bant Çekirdek",
        "Küme Yaşam","Carry Survival","Return Survival",
        "Öncü/Kıvılcım","Seri→Uzun Uyku","Negatif Kanıt",
        "İkiz Grup","İkiz Belirsizlik","Yaşam Olay Yolu","Kaynaklar"
    ]

    # Aile skorlarını ve 16 uzman rol içi yüzdeliklerini de sakla.
    family_cols=[c for c in ["Aile CARRY","Aile RETURN","Aile CLUSTER","Aile TRACE",
                             "Aile STRUCTURE","Aile TIME","Aile REGIME"]]
    expert_cols=[]
    for e in EXPERTS:
        expert_cols += [e+" Yetkili", e+" R"]

    for i in range(start,len(df)):
        train=df.iloc[:i].reset_index(drop=True)
        if len(train)<min_train:
            continue
        target=df.iloc[i]

        # KRİTİK: tahmin burada, hedef sonucu açılmadan önce oluşur.
        try:
            p=predict(train,target["time"],simbrain)
        except Exception:
            continue

        tab=p["tab"].copy().reset_index(drop=True)
        tab["Ön Sıra"]=range(1,len(tab)+1)

        pool16=set(map(int,p["pool16"]))
        actual=set(map(int,target["numbers"]))

        for _,r in tab.iterrows():
            n=int(r["Sayı"])
            is_actual=n in actual
            is_pool=n in pool16

            if is_actual and is_pool:
                cls="DOĞRU — HAVUZDA"
            elif is_actual and not is_pool:
                cls="KAÇAN DOĞRU"
            elif (not is_actual) and is_pool:
                cls="YANLIŞ — HAVUZDA"
            else:
                cls="DIŞARIDA — ÇIKMADI"

            rec={
                "Çekiliş":int(target["draw_no"]),
                "Tarih":str(target["date"]),
                "Saat":str(target["time"]),
                "Gece/Rejim":str(p["char"]["label"]),
                "Gün Gözlem":int(p["char"].get("day_seen",0)),
                "Gün Fazı":str(p["char"].get("day_phase","-")),
                "Gün Güven":float(p["char"].get("confidence",0.0)),
                "Sayı":n,
                "Ön Sıra":int(r["Ön Sıra"]),
                "Havuz16":int(is_pool),
                "Gerçekte Çıktı":int(is_actual),
                "Otopsi Sınıfı":cls,
            }

            for c in keep_cols+family_cols+expert_cols:
                if c in r.index:
                    v=r[c]
                    # numpy değerlerini CSV için sade Python tipine dönüştür.
                    if hasattr(v,"item"):
                        try: v=v.item()
                        except Exception: pass
                    rec[c]=v
            rows.append(rec)

        # Hedef sonucu ANCAK snapshot oluşturulduktan sonra beyne öğretilir.
        snap=make_snapshot(p,int(target["draw_no"]),target["date"],target["time"])
        simbrain,_,_=update_brain_from_result(simbrain,snap,actual)

    out=pd.DataFrame(rows)
    if not out.empty:
        first=[
            "Çekiliş","Tarih","Saat","Gece/Rejim","Sayı","Ön Sıra",
            "Havuz16","Gerçekte Çıktı","Otopsi Sınıfı"
        ]
        rest=[c for c in out.columns if c not in first]
        out=out[first+rest]
    return out


# ============================================================
# MASTER — GÜNLÜK KADAVRA / MOTOR LABORATUVARI / DIŞA AKTAR
# ============================================================
def merge_dataframes(a,b):
    if a is None or a.empty: return b.copy()
    if b is None or b.empty: return a.copy()
    z=pd.concat([a,b],ignore_index=True)
    z["_dt"]=pd.to_datetime(z["date"]+" "+z["time"],format="%d.%m.%Y %H:%M",errors="coerce")
    return (z.dropna(subset=["_dt"]).sort_values(["_dt","draw_no"])
             .drop_duplicates(["date","time"],keep="last").reset_index(drop=True))

def canonical_draw_line(draw_no,date,time,numbers):
    return f"{int(draw_no)} | {date} - {time} | " + " ".join(map(str,sorted(map(int,numbers))))

def add_draw_to_github(draw_no,date,time,numbers):
    token,repo,branch,path=github_config()
    if not token or not repo:
        raise RuntimeError("GitHub secrets yok")
    try:
        old=github_read_path(path)
    except Exception:
        old=""
    new_line=canonical_draw_line(draw_no,date,time,numbers)
    lines=[x.strip() for x in old.splitlines() if x.strip()]
    # replace same draw/date/time if present via parsed data is too expensive; append and parser keeps latest
    lines.append(new_line)
    github_write_path(path,"\n".join(lines)+"\n",message=f"MASTER çekiliş ekle #{draw_no}")
    return f"GitHub {path}"

def add_many_draws_to_github(rows):
    token,repo,branch,path=github_config()
    if not token or not repo:
        raise RuntimeError("GitHub secrets yok")
    try:
        old,_sha=github_read_path(path)
    except Exception:
        old=""
    lines=[x.strip() for x in old.splitlines() if x.strip()]
    for r in rows:
        lines.append(canonical_draw_line(r["draw_no"],r["date"],r["time"],r["numbers"]))
    github_write_path(path,"\n".join(lines)+"\n",message=f"MASTER toplu çekiliş ekle ({len(rows)})")
    return f"GitHub {path} · {len(rows)} çekiliş"

def _saved_snapshots_df():
    frames=[]
    if SAVE_FILE.exists():
        try: frames.append(pd.read_csv(SAVE_FILE))
        except Exception: pass
    try:
        path=str(st.secrets.get("GITHUB_COUPON_PATH","master_kupon_kayitlari.csv"))
        txt,_=github_read_path(path)
        import io
        frames.append(pd.read_csv(io.StringIO(txt)))
    except Exception:
        pass
    if not frames: return pd.DataFrame()
    z=pd.concat(frames,ignore_index=True)
    if "target_draw" in z.columns:
        z=z.drop_duplicates(["target_draw"],keep="last")
    return z

def find_snapshot_for_draw(draw_no):
    cur=st.session_state.get("v26_current_snapshot")
    if cur and int(cur.get("target_draw",-1))==int(draw_no):
        return cur
    saved=_saved_snapshots_df()
    if not saved.empty and "target_draw" in saved.columns and "snapshot_json" in saved.columns:
        try:
            hit=saved[pd.to_numeric(saved["target_draw"],errors="coerce")==int(draw_no)]
            if not hit.empty:
                return json.loads(hit.iloc[-1]["snapshot_json"])
        except Exception:
            pass
    return None

def parse_multi_results(text):
    """Birden çok sonucu parse_any formatlarıyla okur."""
    return parse_any(text)

def bulk_hit_report(result_df):
    rows=[]
    for _,r in result_df.iterrows():
        snap=find_snapshot_for_draw(int(r["draw_no"]))
        if snap is None:
            rows.append({"Çekiliş":int(r["draw_no"]),"Tarih":r["date"],"Saat":r["time"],
                         "Kupon/Havuz":"SNAPSHOT YOK","Kaçta Kaç":"-","Doğru":None,"Tuttu":""})
            continue
        summ,_,_=eval_snapshot(snap,r["numbers"])
        for _,x in summ.iterrows():
            rows.append({"Çekiliş":int(r["draw_no"]),"Tarih":r["date"],"Saat":r["time"],
                         "Kupon/Havuz":x["Kupon/Havuz"],"Kaçta Kaç":x["Kaçta Kaç"],
                         "Doğru":int(x["Doğru"]),"Tuttu":x["Tuttu"]})
    return pd.DataFrame(rows)

def _gap_before(sets_before,n,cap=30):
    if not sets_before: return cap
    for g,s in enumerate(reversed(sets_before)):
        if n in s: return g
    return cap

def daily_cadaver(df,date):
    day=df[df["date"]==date].sort_values("_dt").reset_index(drop=True)
    if day.empty:
        return {},{}
    sets=[set(x) for x in day["numbers"]]

    transitions=[]
    band_rows=[]
    for i,row in day.iterrows():
        s=sets[i]
        band_counts=[sum(1 for n in s if band(n)==b) for b in range(8)]
        band_rows.append({"Saat":row["time"],**{f"{b*10+1}-{b*10+10}":band_counts[b] for b in range(8)}})
        if i==0: continue
        prev=sets[i-1]
        prior=sets[:i]
        actual=s
        gap_counts=Counter()
        for n in actual:
            if n in prev:
                gap_counts["GAP-0 / TAŞIMA"]+=1
            else:
                g=_gap_before(prior,n,30)
                if g==1: gap_counts["GAP-1"]+=1
                elif g==2: gap_counts["GAP-2"]+=1
                elif g==3: gap_counts["GAP-3"]+=1
                elif g in (4,5): gap_counts["GAP-4/5"]+=1
                elif g>=6 and g<30: gap_counts["GAP-6+"]+=1
                else: gap_counts["İLK AKTİVASYON"]+=1
        transitions.append({
            "Hedef":int(row["draw_no"]),"Saat":row["time"],
            "Taşıma":len(prev&actual),
            "GAP-1":gap_counts["GAP-1"],"GAP-2":gap_counts["GAP-2"],
            "GAP-3":gap_counts["GAP-3"],"GAP-4/5":gap_counts["GAP-4/5"],
            "GAP-6+":gap_counts["GAP-6+"],"İlk Aktivasyon":gap_counts["İLK AKTİVASYON"],
        })

    # band transitions: burst/zero/reactivation/member migration
    band_trans=[]
    for i in range(1,len(sets)):
        prev=sets[i-1]; cur=sets[i]
        for b in range(8):
            p={n for n in prev if band(n)==b}; c={n for n in cur if band(n)==b}
            band_trans.append({
                "Saat":day.iloc[i]["time"],"Bant":f"{b*10+1}-{b*10+10}",
                "Önce":len(p),"Şimdi":len(c),"Taşınan":"-".join(map(str,sorted(p&c))),
                "Düşen":"-".join(map(str,sorted(p-c))),"Yeni/Göç":"-".join(map(str,sorted(c-p))),
                "Reaktivasyon":int(len(p)==0 and len(c)>0),
                "Patlama":int(len(c)>=4),"Daralma":int(len(p)>=4 and 0<len(c)<=3),
            })

    # cluster network for pairs/triples
    pair=Counter(); triple=Counter()
    for s in sets:
        a=sorted(s)
        pair.update(combinations(a,2))
        triple.update(combinations(a,3))
    pair_df=pd.DataFrame(
        [{"Küme":f"{a}-{b}","Tekrar":cnt} for (a,b),cnt in pair.items() if cnt>=3]
    ).sort_values("Tekrar",ascending=False) if pair else pd.DataFrame()
    tri_df=pd.DataFrame(
        [{"Küme":"-".join(map(str,t)),"Tekrar":cnt} for t,cnt in triple.items() if cnt>=3]
    ).sort_values("Tekrar",ascending=False) if triple else pd.DataFrame()

    # number life trace
    life=[]
    for n in range(1,81):
        bits="".join("1" if n in s else "0" for s in sets)
        positions=[i for i,s in enumerate(sets) if n in s]
        intervals=[b-a for a,b in zip(positions,positions[1:])]
        life.append({
            "Sayı":n,"Yaşam İzi":bits,"Görünüm":sum(n in s for s in sets),
            "Son Gap":_gap_before(sets,n,30),
            "Aralıklar":"-".join(map(str,intervals)),
            "Bant":band_label(n),
        })
    life_df=pd.DataFrame(life)

    return {
        "day":day.drop(columns=["_dt"],errors="ignore"),
        "transitions":pd.DataFrame(transitions),
        "bands":pd.DataFrame(band_rows),
        "band_transitions":pd.DataFrame(band_trans),
        "pairs":pair_df,
        "triples":tri_df,
        "life":life_df,
    }, {
        "draws":len(day),
        "avg_carry":float(pd.DataFrame(transitions)["Taşıma"].mean()) if transitions else 0.0,
        "max_carry":int(pd.DataFrame(transitions)["Taşıma"].max()) if transitions else 0,
    }

def manifest_df():
    rows=[
        ("REGIME_BRAIN","AKTİF","Gün/saat karakteri + rejim değişimi","Motorlara yetki verir; sayı seçmez"),
        ("EARLY_WARNING","AKTİF","Uzun hafıza/yeni aktivasyon/bant reaktivasyon öncüsü","Tek el ile rejim değiştirmez"),
        ("LIFE_PATH_MEMORY","AKTİF","VAR/YOK değil olay yolu hafızası","Tek örnek kural olmaz"),
        ("RETURN_SURVIVAL","AKTİF","DÖN→TAŞI / DÖN→SÖN","GAP tek başına yeterli değil"),
        ("CARRY_SURVIVAL","AKTİF","TAŞI→TAŞI / çekirdek / geçici yolcu","Sıcak+son elde var yeterli değil"),
        ("BAND_LIFE_MIGRATION","AKTİF","8 bant: patlama/sönme/reaktivasyon/göç","Bant aktif = sayı aktif değildir"),
        ("CLUSTER_NETWORK","AKTİF","İkili/üçlü/dörtlü yaşayan kümeler","Frekans tek başına kanıt değil"),
        ("CLUSTER_BAND_SYNC","AKTİF","Küme zamanı + bant zamanı","Tekrarlanan koşul aranır"),
        ("TWIN_SEPARATOR","AKTİF","Aynı GAP+yaşam izi ikizleri","Fark yoksa BELİRSİZ"),
        ("NEGATIVE_EVIDENCE","AKTİF","Öncü, geçici yolcu, çözülmüş küme, sahte sıcak","Sayıyı silmez; kanıtı frenler"),
        ("EVIDENCE_FUSION","AKTİF","Bağımsız kanıt ailelerini birleştirir","Aynı kanıt iki kez sayılmaz"),
        ("POOL_SURGERY","AKTİF","80→uzman havuzu→Havuz16","Top-16 skor değil"),
        ("DAY_BRAIN_V1","AKTİF","İlk 3 çekiliş günü tanır; 3. elde ilk karar, 4+ elde tam gün karakteri","Hedef sonucu görülmez; 0-2 elde GÜN ÖĞRENİYOR"),
        ("DAY_EXPERT_LEAGUE","GÖZLEMCİ","Aynı günün önceki 3+ çekilişinde çalışan TOP-3 uzmanı seçer","Canlı havuza dokunmaz; kör testte ayrı ölçülür"),
        ("TWIN_BOUNDARY_SURGEON","GÖZLEMCİ","Aynı GAP+yaşam izindeki sınır ikizlerini partner/+2/gün iziyle ayırır","İlk 12 korunur; en fazla 2 swap; canlı havuza dokunmaz"),
        ("UNIFIED_BRAIN_LINK","GÖZLEMCİ","GAP+yaşam+kümeler+survival+ardışık+3-el blok+negatif kanıtı tek karar ağında bağlar","23:02-23:12 blok öğrenir; 23:17+ destek kanıtı; canlı MASTER'a dokunmaz"),
        ("POOL16_V2_OBSERVER","GÖZLEMCİ","Rescue + GAP2/3-zaman + küme + kapılı taşıma + çeşitlilik","Canlı havuza dokunmaz; kör testte MASTER ile yan yana ölçülür"),
        ("PROMOTION_BRAIN","AKTİF","Havuz16→4/5 terfi","Havuza giriş skoru = terfi skoru değil"),
        ("V21_SURGERY","GÖZLEMCİ","Son itiraz / tek swap","Kör kanıt olmadan canlı yetki yok"),
        ("AUTOPSY_LEARNING","AKTİF","Sonuç sonrası nerede doğru kaybedildi?","Sonuç öncesi snapshot şart"),
    ]
    return pd.DataFrame(rows,columns=["Motor","Durum","Görev","Fren/Kural"])

def zip_report_bytes(files_map):
    import io, zipfile
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        for name,obj in files_map.items():
            if isinstance(obj,pd.DataFrame):
                z.writestr(name,obj.to_csv(index=False).encode("utf-8-sig"))
            elif isinstance(obj,(dict,list)):
                z.writestr(name,json.dumps(obj,ensure_ascii=False,indent=2).encode("utf-8"))
            else:
                z.writestr(name,str(obj).encode("utf-8"))
    return bio.getvalue()


# ------------------------------------------------------------
# UI — MASTER
# ------------------------------------------------------------

# ------------------------------------------------------------
# UI — V10 TEK EKRAN / 3 KUPON
# ------------------------------------------------------------

def _simple_parse_result(text, fallback_draw, fallback_date, fallback_time):
    """Başlıklı veya yalnız 20 sayılık sonucu tek ekranda güvenli okur."""
    parsed=parse_result_blob(text) if str(text).strip() else None
    if parsed:
        return parsed
    raw=str(text)
    # Satır satır yalnız 1..80 sayılarını tercih et; tarih/saat/çekiliş no karışmaz.
    line_nums=[]
    for line in raw.splitlines():
        s=line.strip()
        if re.fullmatch(r"(?:[1-9]|[1-7]\\d|80)",s):
            line_nums.append(int(s))
    if len(line_nums)==20 and len(set(line_nums))==20:
        return {"draw_no":int(fallback_draw),"date":str(fallback_date),"time":str(fallback_time),"numbers":sorted(line_nums)}
    # Tek satırda 20 sayı verilmişse, başlık olmadığı durumda kabul et.
    if not re.search(r"\\d{1,2}\\.\\d{1,2}\\.\\d{4}|Çekiliş",raw,re.I):
        nums=[int(x) for x in re.findall(r"(?<!\\d)(?:[1-9]|[1-7]\\d|80)(?!\\d)",raw)]
        if len(nums)==20 and len(set(nums))==20:
            return {"draw_no":int(fallback_draw),"date":str(fallback_date),"time":str(fallback_time),"numbers":sorted(nums)}
    return None


def _snapshot_row(snapshot,p):
    return {
        "saved_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_draw":int(snapshot["target_draw"]),
        "target_date":snapshot["target_date"],
        "target_time":snapshot["target_time"],
        "night_character":snapshot.get("night_character",""),
        "v10_ana5":"-".join(map(str,snapshot.get("v10_final5",[]))),
        "bagimsiz5":"-".join(map(str,snapshot.get("independent5",[]))),
        "ucuncu5":"-".join(map(str,snapshot.get("v7_final5",[]))),
        "snapshot_json":json.dumps(snapshot,ensure_ascii=False,separators=(",",":"))
    }


def _freeze_snapshot_once(snapshot,p):
    """Hedef kuponlarını sonuçtan önce bir kez yerel + mümkünse GitHub'a dondur."""
    row=_snapshot_row(snapshot,p)
    draw=int(row["target_draw"])
    local=pd.DataFrame()
    if SAVE_FILE.exists():
        try: local=pd.read_csv(SAVE_FILE)
        except Exception: local=pd.DataFrame()
    exists=False
    if not local.empty and "target_draw" in local.columns:
        exists=bool((pd.to_numeric(local["target_draw"],errors="coerce")==draw).any())
    if not exists:
        new=pd.concat([local,pd.DataFrame([row])],ignore_index=True) if not local.empty else pd.DataFrame([row])
        new=new.drop_duplicates(["target_draw"],keep="last")
        try: new.to_csv(SAVE_FILE,index=False,encoding="utf-8-sig")
        except Exception: pass
        try:
            path=str(st.secrets.get("GITHUB_COUPON_PATH","master_kupon_kayitlari.csv"))
            remote=pd.DataFrame()
            try:
                txt,_=github_read_path(path)
                import io
                remote=pd.read_csv(io.StringIO(txt))
            except Exception:
                remote=pd.DataFrame()
            merged=pd.concat([remote,pd.DataFrame([row])],ignore_index=True) if not remote.empty else pd.DataFrame([row])
            merged=merged.drop_duplicates(["target_draw"],keep="last")
            github_write_path(path,merged.to_csv(index=False),f"V10 kupon dondur #{draw}")
        except Exception:
            pass


def _persist_draw_simple(parsed):
    """Sonucu oturuma ve mümkünse GitHub veri.txt'ye kalıcı ekler."""
    row=pd.DataFrame([{
        "draw_no":int(parsed["draw_no"]),"date":str(parsed["date"]),
        "time":str(parsed["time"]),"numbers":list(map(int,parsed["numbers"]))
    }])
    row["_dt"]=pd.to_datetime(row["date"]+" "+row["time"],format="%d.%m.%Y %H:%M",errors="coerce")
    old=st.session_state.get("master_extra_df",pd.DataFrame())
    st.session_state["master_extra_df"]=merge_dataframes(old,row)
    gh_msg="Yerel/oturum"
    try:
        token,repo,branch,path=github_config()
        if token and repo:
            try: oldtxt,_=github_read_path(path)
            except Exception: oldtxt=""
            lines=[x.strip() for x in str(oldtxt).splitlines() if x.strip()]
            newline=canonical_draw_line(parsed["draw_no"],parsed["date"],parsed["time"],parsed["numbers"])
            # Aynı çekilişi tekrar tekrar çoğaltma.
            prefix=f"{int(parsed['draw_no'])} |"
            lines=[x for x in lines if not x.startswith(prefix)]
            lines.append(newline)
            github_write_path(path,"\n".join(lines)+"\n",message=f"V10 çekiliş ekle #{parsed['draw_no']}")
            try:
                verify_txt,_=github_read_path(path)
                verify_df=parse_any(verify_txt)
                ok=(not verify_df.empty and int(parsed["draw_no"]) in set(verify_df["draw_no"].astype(int)))
                gh_msg=(f"GitHub {path} ✅" if ok else f"GitHub {path} yazıldı ama veri doğrulanamadı")
            except Exception:
                gh_msg=f"GitHub {path} ✅"
    except Exception as e:
        gh_msg=f"GitHub yazılamadı: {e}"
    return gh_msg




# ============================================================
# V10.1 — UZMAN KURULU / MOTORLAR ARASI DIYALOG + UYUM HAFIZASI
# ============================================================
def _pair_key(a,b):
    return "||".join(sorted((str(a),str(b))))

def _triple_key(a,b,c):
    return "||".join(sorted((str(a),str(b),str(c))))

def _default_council_memory():
    return {"pairs":{},"triples":{},"last_dialogue":{},"version":"V10.1_COUNCIL"}

# Eski beyin dosyalarıyla geriye uyumlu; yeni kurul hafızasını kaybetmez.
_merge_brain_pre_council = _merge_brain
def _merge_brain(obj):
    base=_merge_brain_pre_council(obj)
    cm=_default_council_memory()
    if isinstance(obj,dict) and isinstance(obj.get("council"),dict):
        old=obj.get("council",{})
        if isinstance(old.get("pairs"),dict): cm["pairs"].update(old["pairs"])
        if isinstance(old.get("triples"),dict): cm["triples"].update(old["triples"])
        if isinstance(old.get("last_dialogue"),dict): cm["last_dialogue"].update(old["last_dialogue"])
    base["council"]=cm
    base["version"]="V10.1"
    return base

def _pair_factor(brain,a,b):
    x=(brain or {}).get("council",{}).get("pairs",{}).get(_pair_key(a,b),{})
    n=float(x.get("tests",0)); succ=float(x.get("both_positive",0)); fail=float(x.get("both_zero",0))
    if n<=0: return 0.0
    # Beta-benzeri temkinli merkezleme; küçük örneklemde etkisi çok az.
    quality=(succ+2.0)/(n+4.0) - 0.5
    zero_drag=(fail+1.0)/(n+4.0) - 0.25
    conf=min(1.0,n/30.0)
    return float(np.clip(conf*(0.75*quality-0.35*zero_drag),-0.18,0.18))

def _triple_factor(brain,a,b,c):
    x=(brain or {}).get("council",{}).get("triples",{}).get(_triple_key(a,b,c),{})
    n=float(x.get("tests",0)); succ=float(x.get("all_positive",0))
    if n<=0: return 0.0
    q=(succ+2.0)/(n+4.0)-0.5
    return float(np.clip(min(1.0,n/35.0)*q,-0.10,0.10))

def _council_dialogue_layer(tab,brain):
    """16 uzmanın aday bazında destek/itiraz/çekimser konuşmasını kurar.
    Öğrenilmiş çift/üçlü uyum yalnız küçük bir üst-katman etkisidir; ana motorları ezmez.
    """
    z=tab.copy(); brain=_merge_brain(brain or {})
    supports=[]; opposes=[]; nets=[]; verdicts=[]; dialogues=[]; pairbon=[]; triplebon=[]
    neg=pd.to_numeric(z.get("Negatif Kanıt",0.0),errors="coerce").fillna(0.0)
    for idx,r in z.iterrows():
        pro=[]; con=[]; abst=[]
        for e in EXPERTS:
            auth=int(r.get(e+" Yetkili",0))>0
            rv=float(r.get(e+" R",0.0) or 0.0)
            if auth and rv>=0.82: pro.append((e,rv,"GÜÇLÜ"))
            elif auth and rv>=0.68: pro.append((e,rv,"DESTEK"))
            elif auth and rv<=0.22: con.append((e,1.0-rv,"İTİRAZ"))
            else: abst.append(e)
        # Negatif kanıt gerçek veto kapısıdır; tek başına mutlak yasak değildir.
        nv=float(neg.loc[idx]) if idx in neg.index else 0.0
        veto = nv>=0.72
        pscore=sum(x[1] for x in pro)/max(1,len(pro)) if pro else 0.0
        cscore=sum(x[1] for x in con)/max(1,len(con)) if con else 0.0
        pb=0.0
        pnames=[x[0] for x in pro[:6]]
        for i in range(len(pnames)):
            for j in range(i+1,len(pnames)):
                pb += _pair_factor(brain,pnames[i],pnames[j])
        pb=float(np.clip(pb,-0.22,0.22))
        tb=0.0
        # En güçlü ilk 4 destekçinin üçlü hafızası.
        for i in range(min(4,len(pnames))):
            for j in range(i+1,min(4,len(pnames))):
                for k in range(j+1,min(4,len(pnames))):
                    tb += _triple_factor(brain,pnames[i],pnames[j],pnames[k])
        tb=float(np.clip(tb,-0.12,0.12))
        net=0.62*pscore - 0.28*cscore + pb + tb - 0.45*nv
        if veto: verdict="VETO / NEGATİF KANIT"
        elif net>=0.42 and len(pro)>=2: verdict="KABUL"
        elif net<=0.05: verdict="RED / ZAYIF DOSYA"
        else: verdict="ÇEKİMSER / İZLE"
        protxt=", ".join(f"{e}:{tag}" for e,_,tag in pro[:5]) or "yok"
        contxt=", ".join(e for e,_,_ in con[:3]) or "yok"
        dialogues.append(f"Destek[{protxt}] · İtiraz[{contxt}] · Karar[{verdict}]")
        supports.append(len(pro)); opposes.append(len(con)); nets.append(net); verdicts.append(verdict); pairbon.append(pb); triplebon.append(tb)
    z["Kurul Destek"]=supports; z["Kurul İtiraz"]=opposes
    z["Çift Uyum Hafıza"]=pairbon; z["Üçlü Uyum Hafıza"]=triplebon
    z["Kurul Net"]=nets; z["Kurul Kararı"]=verdicts; z["Kurul Diyalog"]=dialogues
    # Sınırlı etki: kurul ana puanı en fazla yaklaşık +/-0.045 oynatır.
    adj=np.clip(np.asarray(nets,dtype=float),-0.45,0.45)*0.10
    veto_mask=np.array([v.startswith("VETO") for v in verdicts],dtype=float)
    z["Ana Puan"]=pd.to_numeric(z["Ana Puan"],errors="coerce").fillna(0.0)+adj-0.025*veto_mask
    z["Ana Yüzdelik"]=pct(z["Ana Puan"])
    z=z.sort_values(["Bağımsız Aile","Kurul Net","Güçlü Aile","Ana Puan"],ascending=False).reset_index(drop=True)
    return z

# Son canlı predict'in kurul katmanlı sürümü.
_predict_pre_council = predict
def predict(df,target_time,brain=None):
    brain=_merge_brain(brain or _default_brain())
    # Mevcut zincirin tamamını çalıştır; sonra kurul kararıyla tabloyu ve seçim zincirini yeniden üret.
    base=_predict_pre_council(df,target_time,brain)
    tab=_council_dialogue_layer(base["tab"],brain)
    char=base["char"]
    pool16,tab,seat_reason=_pool16_two_stage(tab,char,16)
    pool16_v2,pool16_v2_reason=_pool16_v2_observer(tab,char,16)
    pool16_day_league,day_league_meta=_pool16_day_league_observer(tab,df,target_time,brain,16)
    pool16_twin,twin_swaps,tab=_twin_boundary_surgeon_observer(df,tab,pool16,2,0.5)
    pool16_unified,unified_meta,tab=_unified_brain_observer(df,tab,char,16)
    pool16_dna,tab=_dna_pool16_observer(tab,pool16_unified,16)
    pool16_akor,tab=_motor_harmony_observer(tab,pool16_dna,16)
    dna4=_dna_ticket_brain(tab,pool16_dna,4); dna5=_dna_ticket_brain(tab,pool16_dna,5)
    akor4=_dna_ticket_brain(tab,pool16_akor,4); akor5=_dna_ticket_brain(tab,pool16_akor,5)
    v7final4=_v7_final_surgeon(tab,pool16_akor,4); v7final5=_v7_final_surgeon(tab,pool16_akor,5)
    v8final4=_v8_role_final(tab,pool16_akor,4); v8final5=_v8_role_final(tab,pool16_akor,5)
    v10final4=_v10_life_final_observer(tab,pool16_akor,4); v10final5=_v10_life_final_observer(tab,pool16_akor,5)
    v9final4,_v9tab4=_v9_dynamic_conductor(df,tab,pool16_akor,v7final4,target_time,4)
    v9final5,_v9tab5=_v9_dynamic_conductor(df,tab,pool16_akor,v7final5,target_time,5)
    independent5=list(map(int,v9final5)); v9meta=dict(_v9tab5.attrs.get("v9_swap_meta",{}))
    core4=_ticket_from_pool(tab,pool16,4,0); alt4=_ticket_from_pool(tab,pool16,4,1)
    core5=_ticket_from_pool(tab,pool16,5,0); alt5=_ticket_from_pool(tab,pool16,5,1)
    surg=surgery_observer_v26(tab,core5); approved,delta=surgery_gate(brain)
    surg["brain_approved"]=approved; surg["mean_delta"]=delta
    surg["live5"]=surg["experimental5"] if (approved and surg["triple_lock"]) else core5
    out=dict(base)
    out.update({"tab":tab,"core4":core4,"alt4":alt4,"core5":core5,"alt5":alt5,
        "pool16":pool16,"pool_reason":seat_reason,"pool16_v2":pool16_v2,"pool16_v2_reason":pool16_v2_reason,
        "pool16_day_league":pool16_day_league,"day_league_meta":day_league_meta,"pool16_twin":pool16_twin,"twin_swaps":twin_swaps,
        "pool16_unified":pool16_unified,"unified_meta":unified_meta,"pool16_dna":pool16_dna,"dna4":dna4,"dna5":dna5,
        "pool16_akor":pool16_akor,"akor4":akor4,"akor5":akor5,"v7final4":v7final4,"v7final5":v7final5,
        "v8final4":v8final4,"v8final5":v8final5,"v10final4":v10final4,"v10final5":v10final5,
        "v9final4":v9final4,"v9final5":v9final5,"independent5":independent5,"v9meta":v9meta,"surgery":surg,
        "active_experts":_active_experts(tab,char),"council_enabled":True})
    return out

_make_snapshot_pre_council = make_snapshot
def make_snapshot(p,target_draw,target_date,target_time):
    s=_make_snapshot_pre_council(p,target_draw,target_date,target_time)
    cols=["Sayı","Kurul Destek","Kurul İtiraz","Kurul Net","Kurul Kararı","Kurul Diyalog"]
    if all(c in p["tab"].columns for c in cols):
        s["council_rows"]=p["tab"][cols].head(30).to_dict("records")
    return s

_update_brain_pre_council = update_brain_from_result
def update_brain_from_result(brain,snapshot,actual):
    brain=_merge_brain(brain); actual=set(map(int,actual)); draw=int(snapshot.get("target_draw",0))
    if draw in set(map(int,brain.get("evaluated_draws",[]))):
        return brain,False,"Bu çekiliş merkez beyne daha önce işlendi."
    # Önce mevcut uzman + cerrahi öğrenmesini uygula.
    brain,changed,msg=_update_brain_pre_council(brain,snapshot,actual)
    if not changed: return brain,changed,msg
    hits={}
    for e,arr in snapshot.get("expert_top5",{}).items():
        hits[e]=len(set(map(int,arr or []))&actual)
    cm=brain.setdefault("council",_default_council_memory())
    pairs=cm.setdefault("pairs",{}); triples=cm.setdefault("triples",{})
    names=[e for e in EXPERTS if e in hits]
    for i,a in enumerate(names):
        for b in names[i+1:]:
            k=_pair_key(a,b); x=pairs.setdefault(k,{"tests":0,"both_positive":0,"both_zero":0,"joint_hit_total":0.0})
            x["tests"]+=1; x["joint_hit_total"]+=float(min(hits[a],hits[b]))
            if hits[a]>0 and hits[b]>0: x["both_positive"]+=1
            if hits[a]==0 and hits[b]==0: x["both_zero"]+=1
    # Üçlü hafıza: bütün üçlüleri sabit boyutlu istatistik olarak tut.
    for i,a in enumerate(names):
        for j in range(i+1,len(names)):
            b=names[j]
            for c in names[j+1:]:
                k=_triple_key(a,b,c); x=triples.setdefault(k,{"tests":0,"all_positive":0,"joint_hit_total":0.0})
                x["tests"]+=1; x["joint_hit_total"]+=float(min(hits[a],hits[b],hits[c]))
                if hits[a]>0 and hits[b]>0 and hits[c]>0: x["all_positive"]+=1
    cm["last_dialogue"]={"draw":draw,"updated_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    brain["version"]="V10.1"
    return brain,True,msg+" · Uzman Kurulu çift/üçlü uyum hafızası güncellendi."

st.set_page_config(page_title="V10 — 3 Kupon",page_icon="🎯",layout="wide")
st.title("🎯 V10 — Tek Ekran / 3 Kupon")
st.caption("Sonucu yapıştır → kaçta kaç gördüğünü gör → sonuç kaydolur → bir sonraki çekilişin 3 kuponu hemen hazır olur.")

df,source=load_data(); brain,brain_source=load_brain()
extra=st.session_state.get("master_extra_df",pd.DataFrame())
if isinstance(extra,pd.DataFrame) and not extra.empty:
    df=merge_dataframes(df,extra)
if df.empty:
    st.error("veri.txt bulunamadı."); st.stop()

target_date,target_time,target_draw=next_target_label(df)
p=predict(df,target_time,brain)
snapshot=make_snapshot(p,target_draw,target_date,target_time)
st.session_state["v26_current_snapshot"]=snapshot
_freeze_snapshot_once(snapshot,p)

st.markdown("### ➕ Yeni çekiliş sonucunu buraya yapıştır")
result_blob=st.text_area(
    "Tek kutu",
    height=210,
    placeholder="Çekiliş no: 49476\\n16.08.2026 - 23:57\\n7\\n12\\n... (20 sayı)",
    label_visibility="collapsed",
    key=f"v10_simple_result_blob_{target_draw}"
)
parsed=_simple_parse_result(result_blob,target_draw,target_date,target_time) if result_blob.strip() else None
if result_blob.strip() and parsed is None:
    st.warning("Henüz tam 20 benzersiz sayı okuyamadım. Başlıkla birlikte komple yapıştırabilirsin.")
elif parsed is not None:
    st.caption(f"Okundu: #{parsed['draw_no']} · {parsed['date']} {parsed['time']} · 20 sayı")

if st.button("✅ SONUCU EKLE · KAÇTA KAÇI GÖSTER · SONRAKİ 3 KUPONU HAZIRLA",type="primary",use_container_width=True,disabled=(parsed is None)):
    # Sonuç görülmeden önce dondurulmuş snapshot'ı kullan.
    snap=find_snapshot_for_draw(parsed["draw_no"]) or st.session_state.get("v26_current_snapshot")
    cards=[]
    if snap and int(snap.get("target_draw",-1))==int(parsed["draw_no"]):
        actual=set(map(int,parsed["numbers"]))
        wanted=[
            ("V10 ANA 5",snap.get("v10_final5",[])),
            ("BAĞIMSIZ 5 — V9.5",snap.get("independent5",snap.get("v9_final5",[]))),
            ("3. KUPON — V7",snap.get("v7_final5",[])),
        ]
        for name,arr in wanted:
            arr=list(map(int,arr or [])); hits=sorted(set(arr)&actual)
            cards.append({"name":name,"score":f"{len(hits)}/{len(arr) if arr else 5}","hits":"-".join(map(str,hits))})
        try:
            summ,_,_=eval_snapshot(snap,parsed["numbers"])
            save_eval_log(snap,parsed["numbers"],summ)
        except Exception:
            pass
        learn_msg=""
        try:
            brain2,changed,msg=update_brain_from_result(brain,snap,parsed["numbers"])
            if changed:
                where=save_brain(brain2); learn_msg=msg+" · "+where
            else: learn_msg=msg
        except Exception as e:
            learn_msg=f"Öğrenme kaydı atlandı: {e}"
    else:
        cards=[
            {"name":"V10 ANA 5","score":"—","hits":"snapshot yok"},
            {"name":"BAĞIMSIZ 5 — V9.5","score":"—","hits":"snapshot yok"},
            {"name":"3. KUPON — V7","score":"—","hits":"snapshot yok"},
        ]
        learn_msg="Bu çekiliş için sonuçtan önce dondurulmuş kupon bulunamadı; geriye dönük kupon üretmedim."
    persist=_persist_draw_simple(parsed)
    st.session_state["v10_simple_last_eval"]={
        "draw":int(parsed["draw_no"]),"date":parsed["date"],"time":parsed["time"],
        "cards":cards,"persist":persist,"learn_msg":learn_msg
    }
    st.rerun()

# Son eklenen çekilişin KAÇTA KAÇ sonucunu giriş alanının HEMEN altında göster.
last_eval=st.session_state.get("v10_simple_last_eval")
if isinstance(last_eval,dict):
    st.markdown("### 🎯 SON EKLENEN ÇEKİLİŞ — KAÇTA KAÇ?")
    st.success(f"#{last_eval['draw']} · {last_eval['date']} {last_eval['time']} · {last_eval.get('persist','')}")
    cards=st.columns(3)
    for i,item in enumerate(last_eval.get("cards",[])[:3]):
        score=str(item.get("score","—"))
        hits=str(item.get("hits","") or "—")
        with cards[i]:
            st.metric(item.get("name",f"Kupon {i+1}"),score)
            st.caption("Tutan sayılar: "+hits)
    if last_eval.get("learn_msg"):
        st.caption(last_eval["learn_msg"])

st.divider()
st.markdown(f"### 🎟️ Sıradaki çekiliş: #{target_draw} · {target_date} {target_time}")
q1,q2,q3=st.columns(3)
with q1:
    st.success("V10 ANA 5")
    st.markdown("### "+" - ".join(map(str,p.get("v10final5",[]))))
with q2:
    st.info("BAĞIMSIZ 5 — V9.5")
    st.markdown("### "+" - ".join(map(str,p.get("independent5",p.get("v9final5",[])))))
with q3:
    st.warning("3. KUPON — V7")
    st.markdown("### "+" - ".join(map(str,p.get("v7final5",[]))))
st.caption("Üç kupon dışında canlı ekranda başka kupon üretmiyorum. V10 ana kupondur; diğer ikisi ayrı kapsama içindir.")

st.markdown("### 🕘 Son 10 çekiliş")
recent=df.sort_values("_dt",ascending=False).head(10).copy()
if not recent.empty:
    recent_show=recent[["draw_no","date","time","numbers"]].copy()
    recent_show["numbers"]=recent_show["numbers"].apply(lambda x:" - ".join(map(str,x)))
    recent_show.columns=["Çekiliş","Tarih","Saat","20 sayı"]
    st.dataframe(recent_show,use_container_width=True,hide_index=True)

with st.expander("⚙️ Teknik durum",expanded=False):
    st.write("Veri:",source)
    st.write("Beyin:",brain_source)
    _ght,_ghr,_ghb,_ghp=github_config()
    if _ght and _ghr:
        st.write("GitHub kalıcı kayıt:", "✅ bağlı")
    else:
        st.write("GitHub kalıcı kayıt:", "⛔ token okunamadı")
        st.caption("Eski V18 ayarı destekleniyor: [github] altında yalnız token olması bile yeterli; owner/repo eski varsayılanlardan tamamlanır.")
    st.caption(f"Repo: {_ghr} · branch: {_ghb} · veri yolu: {_ghp}")
    st.write("Aktif kuponlar: V10 Ana · V9.5 Bağımsız · V7 üçüncü kupon")
