
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
    page_title="Hızlı On — V24 Gece Mekanizma Laboratuvarı",
    page_icon="🧠",
    layout="wide",
)

SLOTS = ["23:02","23:07","23:12","23:17","23:22","23:27",
         "23:32","23:37","23:42","23:47","23:52","23:57"]
BASE = 20/80
DATA_FILE = Path("veri.txt")
SAVE_FILE = Path("v24_kupon_kayitlari.csv")

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
    try:
        token=str(st.secrets.get("GITHUB_TOKEN","")).strip()
        repo=str(st.secrets.get("GITHUB_REPO","")).strip()
        branch=str(st.secrets.get("GITHUB_BRANCH","main")).strip() or "main"
        path=str(st.secrets.get("GITHUB_DATA_PATH","veri.txt")).strip() or "veri.txt"
        return token,repo,branch,path
    except Exception:
        return "","","main","veri.txt"

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
    sets=sets_of(df)
    if len(sets)<8:
        return {"label":"BELİRSİZ","short":0.5,"long":0.5,"carry":5.0,"gap2":0.0,"longret":0.0}
    recent=min(10,len(sets)-1)
    trans=[]
    gap2_vals=[]
    long_vals=[]
    for i in range(len(sets)-recent,len(sets)):
        if i<=0: continue
        prev=sets[:i]
        cur=sets[i]
        trans.append(len(sets[i-1]&cur))
        g2=sum(1 for n in cur if n not in sets[i-1] and number_gap(prev,n,12)==2)
        gl=sum(1 for n in cur if n not in sets[i-1] and number_gap(prev,n,12)>=5)
        gap2_vals.append(g2); long_vals.append(gl)
    carry=float(np.mean(trans)) if trans else 5.0
    g2=float(np.mean(gap2_vals)) if gap2_vals else 0.0
    gl=float(np.mean(long_vals)) if long_vals else 0.0
    short=np.clip((carry+g2)/(10.0),0,1)
    long=np.clip((gl+max(0,5-carry))/(8.0),0,1)
    if short>=0.62 and short>long+0.08: label="KISA HAFIZA / TAŞIMA"
    elif long>=0.55 and long>short+0.05: label="UZUN HAFIZA / DÖNÜŞ"
    else: label="KARMA / GEÇİŞ"
    return {"label":label,"short":float(short),"long":float(long),
            "carry":carry,"gap2":g2,"longret":gl}

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
BRAIN_FILE=Path("v25_merkez_beyin.json")
EVAL_FILE=Path("v25_sonuc_karnesi.csv")


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
        txt,_=github_read_path(str(st.secrets.get("GITHUB_BRAIN_PATH","v25_merkez_beyin.json")))
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
        path=str(st.secrets.get("GITHUB_BRAIN_PATH","v25_merkez_beyin.json"))
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
    def chk(name):
        arr=list(map(int,snapshot.get(name,[]))); hit=sorted(set(arr)&actual); miss=sorted(set(arr)-actual)
        return {"Kol":name,"Seçim":"-".join(map(str,arr)),"Doğru":len(hit),"Tuttu":"-".join(map(str,hit)),"Kaçtı":"-".join(map(str,miss))}
    summary=pd.DataFrame([chk("core4"),chk("alt4"),chk("core5"),chk("alt5"),chk("live5"),chk("pool12"),chk("pool16")])
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
        rows.append({"draw_no":snapshot.get("target_draw"),"date":snapshot.get("target_date"),"time":snapshot.get("target_time"),
                     "night":snapshot.get("night_character"),"kol":r["Kol"],"dogru":int(r["Doğru"]),"tuttu":r["Tuttu"],
                     "secim":r["Seçim"],"saved_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    new=pd.DataFrame(rows)
    if EVAL_FILE.exists():
        try: old=pd.read_csv(EVAL_FILE)
        except Exception: old=pd.DataFrame()
        new=pd.concat([old,new],ignore_index=True).drop_duplicates(["draw_no","kol"],keep="last")
    new.to_csv(EVAL_FILE,index=False,encoding="utf-8-sig")
    try:
        path=str(st.secrets.get("GITHUB_EVAL_PATH","v25_sonuc_karnesi.csv"))
        github_write_path(path,new.to_csv(index=False),"V25 sonuç karnesi güncelle")
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


# ------------------------------------------------------------
# UI — V25
# ------------------------------------------------------------
st.title("🧠 Hızlı On — V25 Öğrenen Merkez Beyin")
st.caption(
    "16 uzman + gece mekanizması + kaynak havuzu + kontrollü V21 cerrahi + sonuç geri besleme + "
    "sıralı kör walk-forward. Sonuç görülmeden ağırlık güncellenmez."
)

df,source=load_data(); brain,brain_source=load_brain()
st.sidebar.caption(source); st.sidebar.caption("🧠 "+brain_source)
if df.empty:
    st.error("veri.txt bulunamadı. Repo köküne veri.txt koy veya soldan yükle."); st.stop()

target_date,target_time,target_draw=next_target_label(df)
target_time=st.sidebar.selectbox("Hedef saat",SLOTS,index=SLOTS.index(target_time))
pool_size=st.sidebar.slider("Kaynak havuzu",10,30,16)
p=predict(df,target_time,brain)
snapshot=make_snapshot(p,target_draw,target_date,target_time)
st.session_state["v25_current_snapshot"]=snapshot

tabs=st.tabs(["🎯 CANLI 4/5","🧠 MERKEZ BEYİN","🧬 16 UZMAN","🌙 GECE KARAKTERİ","🧪 KÖR TEST","🩺 V21 CERRAHİ","📥 SONUÇ & ÖĞREN","💾 KAYDET"])

with tabs[0]:
    st.subheader(f"🎯 Hedef: #{target_draw} · {target_date} {target_time}")
    st.info(f"Gece karakteri: **{p['char']['label']}** · son geçiş taşıma ort.: **{p['char']['carry']:.2f}**")
    a,b,c,d=st.columns(4)
    a.success("4'lü ÇEKİRDEK\n\n"+" - ".join(map(str,p["core4"])))
    b.info("4'lü ALTERNATİF\n\n"+" - ".join(map(str,p["alt4"])))
    c.success("5'li ÇEKİRDEK\n\n"+" - ".join(map(str,p["core5"])))
    d.info("5'li ALTERNATİF\n\n"+" - ".join(map(str,p["alt5"])))
    if p["surgery"]["brain_approved"] and p["surgery"]["triple_lock"]:
        st.success("🩺 Merkez beyin cerrahiyi ONAYLADI → Canlı 5: "+" - ".join(map(str,p["surgery"]["live5"])))
    else:
        st.caption("🩺 Cerrahi canlı kuponu değiştirmiyor; kanıt eşiği oluşana kadar gözlemci.")
    st.markdown("### 🔬 Kaynak Havuzu")
    show=p["tab"].head(pool_size).copy(); cols=["Sayı","Ana Puan","Uzman Oy","Güçlü Oy","Gap","Yaşam İzi","Kaynaklar"]
    st.dataframe(show[cols],use_container_width=True,hide_index=True)

with tabs[1]:
    st.subheader("🧠 Merkez Beyin — motor yetki tablosu")
    bw=brain_weights(brain); rows=[]
    for e in EXPERTS:
        x=brain["experts"][e]; n=int(x.get("tests",0)); avg=float(x.get("hit_total",0))/max(1,n)
        rows.append({"Uzman":e,"Öğrenme Testi":n,"Top5 Ort.":avg if n else np.nan,"Rastgele":1.25,"Merkez Katsayı":bw[e],"Son 10":str(x.get("last_hits",[])[-10:])})
    bdf=pd.DataFrame(rows).sort_values("Merkez Katsayı",ascending=False)
    st.dataframe(bdf.round(3),use_container_width=True,hide_index=True)
    st.caption("Katsayılar küçük örneklemde 1.00'a yakın tutulur; tek sonuçla motor şişirilmez veya silinmez.")
    sg=brain["surgery"]; approved,delta=surgery_gate(brain)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Cerrahi tetik",int(sg.get("triggered",0))); c2.metric("Pozitif",int(sg.get("positive",0)))
    c3.metric("Negatif",int(sg.get("negative",0))); c4.metric("Ort. cerrahi fark",f"{delta:+.3f}")
    st.write("Cerrahi canlı yetki:","✅ ONAYLI" if approved else "⛔ GÖZLEMCİ")

with tabs[2]:
    st.subheader("🧬 16 Alt Motor — ayrı ayrı konuşsun")
    selected=st.selectbox("Uzman",EXPERTS,index=3)
    t=p["tab"].sort_values(selected+" R",ascending=False).head(20)
    st.dataframe(t[["Sayı",selected,selected+" R","Gap","Yaşam İzi","Ana Puan","Kaynaklar"]],use_container_width=True,hide_index=True)

with tabs[3]:
    st.subheader("🌙 Gece Karakteri / aktif geliş yolları")
    c1,c2,c3=st.columns(3); c1.metric("Karakter",p["char"]["label"]); c2.metric("Kısa hafıza",f"{100*p['char']['short']:.1f}%"); c3.metric("Uzun hafıza",f"{100*p['char']['long']:.1f}%")
    mh=pd.DataFrame([{"Mekanizma":k,"Saat geçmiş gücü":v} for k,v in p["mech_hist"].items()])
    st.dataframe(mh.sort_values("Saat geçmiş gücü",ascending=False),use_container_width=True,hide_index=True)
    wt=pd.DataFrame([{"Uzman":k,"Nihai dinamik ağırlık":v,"Öğrenme katsayısı":p["brain_weights"].get(k,1.0)} for k,v in p["weights"].items()])
    st.dataframe(wt.sort_values("Nihai dinamik ağırlık",ascending=False).round(3),use_container_width=True,hide_index=True)

with tabs[4]:
    st.subheader("🧪 SIRALI ÖĞRENEN KÖR WALK-FORWARD")
    st.caption("Her hedefte: önce tahmin → sonra gerçek sonuç açılır → ancak ondan sonra simülasyon beyni öğrenir. Gelecek bilgi sızıntısı yoktur.")
    ntest=st.slider("Son kaç hedef?",20,240,60,10,key="blindn_v25")
    if st.button("▶️ Kör testi çalıştır",type="primary"):
        with st.spinner("Kör walk-forward + sıralı öğrenme çalışıyor..."):
            bt,simbrain=blind_test(df,ntest=ntest,min_train=min(120,max(50,len(df)//3)))
            ma=mechanism_blind_audit(df,ntest=min(ntest,100),min_train=min(120,max(50,len(df)//3)))
        st.session_state["v25_bt"]=bt; st.session_state["v25_ma"]=ma; st.session_state["v25_simbrain"]=simbrain
    bt=st.session_state.get("v25_bt")
    if isinstance(bt,pd.DataFrame) and not bt.empty:
        expected={"4 Çekirdek":1.0,"4 Alternatif":1.0,"5 Çekirdek":1.25,"5 Alternatif":1.25,"Canlı5":1.25,"Havuz12":3.0,"Havuz16":4.0,"Cerrahi5":1.25}
        metrics=list(expected)
        summary=pd.DataFrame({"Kol":metrics,"Ort. İsabet":[bt[c].mean() for c in metrics],"Rastgele Beklenti":[expected[c] for c in metrics],"Lift":[bt[c].mean()-expected[c] for c in metrics],"Maksimum":[bt[c].max() for c in metrics]})
        st.dataframe(summary.round(3),use_container_width=True,hide_index=True)
        x1,x2,x3,x4=st.columns(4); x1.metric("4'lü 4/4",int((bt["4 Çekirdek"]==4).sum())); x2.metric("5'li 5/5",int((bt["5 Çekirdek"]==5).sum())); x3.metric("5'li 4+",int((bt["5 Çekirdek"]>=4).sum())); x4.metric("Cerrahi tetik",int(bt["CerrahiAçıldı"].sum()))
        st.dataframe(bt.sort_values("Çekiliş",ascending=False),use_container_width=True,hide_index=True)
    ma=st.session_state.get("v25_ma")
    if isinstance(ma,pd.DataFrame) and not ma.empty:
        st.markdown("### 🧬 Uzmanların bağımsız kör Top-5 karnesi"); st.dataframe(ma.round(3),use_container_width=True,hide_index=True)

with tabs[5]:
    s=p["surgery"]; st.subheader("🩺 V21 Cerrahi — kanıta bağlı yetki")
    st.write("Base 5:"," - ".join(map(str,s["base5"]))); st.write("Çıkış itirazı:",s["exit"],"· Dış aday:",s["entry"])
    st.write("Üçlü kilit:","AÇILDI" if s["triple_lock"] else "KAPALI"); st.write("Deneysel 5:"," - ".join(map(str,s["experimental5"])))
    st.write("Merkez beyin canlı yetkisi:","ONAYLI" if s["brain_approved"] else "GÖZLEMCİ"); st.write("Canlı 5:"," - ".join(map(str,s["live5"])))
    st.caption("Cerrahi ancak geçmiş tetiklerde yeterli sayıda ve pozitif net katkı kanıtlanırsa canlı kupona dokunur.")

with tabs[6]:
    st.subheader("📥 Sonuç ekle → neden doğru/yanlış olduğunu öğren")
    st.caption("En sağlıklısı kuponu önce KAYDET, sonuç geldikten sonra bu bölüme yapıştırmaktır.")
    blob=st.text_area("Çekiliş no + tarih/saat + 20 sayı",height=260,placeholder="Çekiliş no: 49522\n17.08.2026 - 09:42\n1\n2\n...")
    parsed=parse_result_blob(blob) if blob.strip() else None
    if parsed:
        st.success(f"Okundu: #{parsed['draw_no']} · {parsed['date']} {parsed['time']} · 20 sayı")
        snap=None
        # önce oturumdaki hedefe bak
        cur=st.session_state.get("v25_current_snapshot")
        if cur and int(cur.get("target_draw",-1))==parsed["draw_no"]: snap=cur
        # sonra kayıt dosyasından snapshot ara
        if snap is None and SAVE_FILE.exists():
            try:
                saved=pd.read_csv(SAVE_FILE)
                hit=saved[saved["target_draw"].astype(int)==parsed["draw_no"]]
                if not hit.empty and "snapshot_json" in hit.columns:
                    snap=json.loads(hit.iloc[-1]["snapshot_json"])
            except Exception: pass
        if snap is None:
            st.warning("Bu çekiliş için önceden kaydedilmiş tahmin snapshot'ı bulunamadı. Sonucu geriye dönük tahmin üretmek için kullanmıyorum; bu leakage olur.")
        else:
            summ,edf,ddf=eval_snapshot(snap,parsed["numbers"])
            st.markdown("### 🎯 Kaçta kaç?"); st.dataframe(summ,use_container_width=True,hide_index=True)
            st.markdown("### 🧬 Hangi motor doğru/yanlış yönlendirdi?"); st.dataframe(edf,use_container_width=True,hide_index=True)
            st.markdown("### 🔬 Havuzdaki adayların açıklaması")
            st.dataframe(ddf,use_container_width=True,hide_index=True)
            if st.button("🧠 SONUCU MERKEZ BEYNE ÖĞRET",type="primary"):
                brain2,changed,msg=update_brain_from_result(brain,snap,parsed["numbers"])
                if changed:
                    where=save_brain(brain2); save_eval_log(snap,parsed["numbers"],summ)
                    st.success(msg+" · Kayıt: "+where); st.session_state["v25_current_snapshot"]=None; st.rerun()
                else: st.info(msg)
    elif blob.strip(): st.error("Çekiliş no, tarih/saat ve tam 20 benzersiz sayı okunamadı.")

with tabs[7]:
    st.subheader("💾 Tahmini sonuçtan ÖNCE dondur")
    row={"saved_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"target_draw":target_draw,"target_date":target_date,"target_time":target_time,"night_character":p["char"]["label"],"core4":"-".join(map(str,p["core4"])),"alt4":"-".join(map(str,p["alt4"])),"core5":"-".join(map(str,p["core5"])),"alt5":"-".join(map(str,p["alt5"])),"live5":"-".join(map(str,p["surgery"]["live5"])),"pool16":"-".join(map(str,p["tab"].head(16)["Sayı"].astype(int).tolist())),"snapshot_json":json.dumps(snapshot,ensure_ascii=False,separators=(",",":"))}
    if st.button("💾 HIZLI KAYDET",type="primary"):
        new=pd.DataFrame([row])
        if SAVE_FILE.exists():
            try: old=pd.read_csv(SAVE_FILE)
            except Exception: old=pd.DataFrame()
            new=pd.concat([old,new],ignore_index=True).drop_duplicates(["target_draw"],keep="last")
        new.to_csv(SAVE_FILE,index=False,encoding="utf-8-sig")
        try:
            path=str(st.secrets.get("GITHUB_COUPON_PATH","v24_kupon_kayitlari.csv")); github_write_path(path,new.to_csv(index=False),"V25 kupon snapshot kaydı"); st.success("Tahmin donduruldu: GitHub + yerel")
        except Exception: st.success("Tahmin donduruldu: yerel")
    if SAVE_FILE.exists():
        try:
            saved=pd.read_csv(SAVE_FILE); showcols=[c for c in ["saved_at","target_draw","target_date","target_time","night_character","core4","core5","live5","pool16"] if c in saved.columns]
            st.dataframe(saved[showcols].tail(30),use_container_width=True,hide_index=True)
            st.download_button("⬇️ Kupon kayıt CSV",saved.to_csv(index=False).encode("utf-8-sig"),file_name="v25_kupon_kayitlari.csv",mime="text/csv")
        except Exception: pass

st.divider()
st.caption("V25 araştırma aracıdır. Çekilişler rastlantısaldır; 4/4 veya 5/5 garanti etmez. Başarı yalnız kör/out-of-sample sonuçlarla değerlendirilmelidir.")
