
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
# UI
# ------------------------------------------------------------
st.title("🧠 Hızlı On — V24 Gece Mekanizma Laboratuvarı")
st.caption(
    "Önce gecenin hangi geliş yollarıyla çalıştığını tanır; sonra 16 ayrı uzmanı birleştirir. "
    "4'lü/5'li seçimler ve gerçek kör walk-forward testi aynı motor üzerinden üretilir."
)

df,source=load_data()
st.sidebar.caption(source)
if df.empty:
    st.error("veri.txt bulunamadı. Repo köküne veri.txt koy veya soldan yükle.")
    st.stop()

target_date,target_time,target_draw=next_target_label(df)
target_time=st.sidebar.selectbox("Hedef saat",SLOTS,index=SLOTS.index(target_time))
pool_size=st.sidebar.slider("Kaynak havuzu",10,30,16)

tabs=st.tabs(["🎯 CANLI 4/5","🧬 16 UZMAN","🌙 GECE KARAKTERİ","🧪 KÖR TEST","🩺 V21 CERRAHİ","💾 KAYDET"])

with tabs[0]:
    p=predict(df,target_time)
    st.subheader(f"🎯 Hedef: #{target_draw} · {target_date} {target_time}")
    st.info(f"Gece karakteri: **{p['char']['label']}** · son geçiş taşıma ort.: **{p['char']['carry']:.2f}**")
    a,b,c,d=st.columns(4)
    a.success("4'lü ÇEKİRDEK\n\n"+" - ".join(map(str,p["core4"])))
    b.info("4'lü ALTERNATİF\n\n"+" - ".join(map(str,p["alt4"])))
    c.success("5'li ÇEKİRDEK\n\n"+" - ".join(map(str,p["core5"])))
    d.info("5'li ALTERNATİF\n\n"+" - ".join(map(str,p["alt5"])))

    st.markdown("### 🔬 Kaynak Havuzu")
    show=p["tab"].head(pool_size).copy()
    cols=["Sayı","Ana Puan","Uzman Oy","Güçlü Oy","Gap","Yaşam İzi","Kaynaklar"]
    st.dataframe(show[cols],use_container_width=True,hide_index=True)

    st.markdown("### 🧭 Havuz içindeki rol ayrışımı")
    detail_cols=["Sayı","TAŞIMA R","YENİ AKTİVASYON→TAŞIMA R","GAP-2 R","GAP-4/5 R","GAP-6+ R",
                 "KÜME DÖNÜŞ R","KÜME ZAMAN RİTMİ R","AYNI YAŞAM İZİ R","AYNI SAAT FAZI R"]
    st.dataframe(show[[c for c in detail_cols if c in show.columns]],use_container_width=True,hide_index=True)

with tabs[1]:
    st.subheader("🧬 16 Alt Motor — ayrı ayrı konuşsun")
    p=predict(df,target_time)
    experts=[
        "TAŞIMA","YENİ AKTİVASYON→TAŞIMA","GAP-1","GAP-2","GAP-3","GAP-4/5","GAP-6+",
        "SERİ→UYKU→DÖNÜŞ","KÜME TAŞIMA","KÜME DÖNÜŞ","AYNI YAŞAM İZİ",
        "KÜME ZAMAN RİTMİ","ARDIŞIK/+2/+3","BANT/KOMŞU","AYNI SAAT FAZI","GECE KARAKTER"
    ]
    selected=st.selectbox("Uzman",experts,index=3)
    t=p["tab"].sort_values(selected+" R",ascending=False).head(20)
    st.dataframe(t[["Sayı",selected,selected+" R","Gap","Yaşam İzi","Ana Puan","Kaynaklar"]],
                 use_container_width=True,hide_index=True)

with tabs[2]:
    p=predict(df,target_time)
    st.subheader("🌙 Gece Karakteri / aktif geliş yolları")
    c1,c2,c3=st.columns(3)
    c1.metric("Karakter",p["char"]["label"])
    c2.metric("Kısa hafıza",f"{100*p['char']['short']:.1f}%")
    c3.metric("Uzun hafıza",f"{100*p['char']['long']:.1f}%")
    mh=pd.DataFrame([{"Mekanizma":k,"Saat geçmiş gücü":v} for k,v in p["mech_hist"].items()])
    st.dataframe(mh.sort_values("Saat geçmiş gücü",ascending=False),use_container_width=True,hide_index=True)
    wt=pd.DataFrame([{"Uzman":k,"Dinamik ağırlık":v} for k,v in p["weights"].items()])
    st.dataframe(wt.sort_values("Dinamik ağırlık",ascending=False),use_container_width=True,hide_index=True)

with tabs[3]:
    st.subheader("🧪 GERÇEK KÖR WALK-FORWARD")
    st.caption("Her hedef satırında motor yalnız o çekilişten ÖNCEKİ veriyi görür. Hedef sonucu skor/eşik seçiminde kullanılmaz.")
    ntest=st.slider("Son kaç hedef?",20,120,40,10,key="blindn")
    if st.button("▶️ Kör testi çalıştır",type="primary"):
        with st.spinner("Walk-forward çalışıyor..."):
            bt=blind_test(df,ntest=ntest,min_train=min(120,max(50,len(df)//3)))
            ma=mechanism_blind_audit(df,ntest=min(ntest,70),min_train=min(120,max(50,len(df)//3)))
        st.session_state["v24_bt"]=bt
        st.session_state["v24_ma"]=ma
    bt=st.session_state.get("v24_bt")
    if isinstance(bt,pd.DataFrame) and not bt.empty:
        metrics=["4 Çekirdek","4 Alternatif","5 Çekirdek","5 Alternatif","Havuz12","Havuz16","Cerrahi5"]
        summary=pd.DataFrame({
            "Kol":metrics,
            "Ort. İsabet":[bt[c].mean() for c in metrics],
            "Maksimum":[bt[c].max() for c in metrics],
            "Tam İsabet":[
                int((bt[c]==(4 if c.startswith("4 ") else 5 if c.startswith("5 ") or c=="Cerrahi5" else 12 if c=="Havuz12" else 16)).sum())
                for c in metrics
            ],
        })
        st.dataframe(summary.round(3),use_container_width=True,hide_index=True)
        x1,x2,x3,x4=st.columns(4)
        x1.metric("4'lü 4/4",int((bt["4 Çekirdek"]==4).sum()))
        x2.metric("5'li 5/5",int((bt["5 Çekirdek"]==5).sum()))
        x3.metric("5'li 4+",int((bt["5 Çekirdek"]>=4).sum()))
        x4.metric("Cerrahi açılma",int(bt["CerrahiAçıldı"].sum()))
        st.dataframe(bt.sort_values("Çekiliş",ascending=False),use_container_width=True,hide_index=True)
    ma=st.session_state.get("v24_ma")
    if isinstance(ma,pd.DataFrame) and not ma.empty:
        st.markdown("### 🧬 Uzmanların kör Top-5 performansı")
        st.dataframe(ma.round(3),use_container_width=True,hide_index=True)

with tabs[4]:
    p=predict(df,target_time)
    s=p["surgery"]
    st.subheader("🩺 V21 Cerrahi — GÖZLEMCİ MOD")
    st.warning(
        "V21.21 ve V21.22 validation kayıtlarında cerrahi net -1 verdiği için bu sürümde otomatik canlı swap KAPALIDIR. "
        "Kör testte deneysel karşılaştırılır."
    )
    st.write("Base 5:", " - ".join(map(str,s["base5"])))
    st.write("Çıkış itirazı:",s["exit"]," · Dış aday:",s["entry"])
    st.write("Üçlü kilit:", "AÇILDI" if s["triple_lock"] else "KAPALI")
    st.write("Deneysel 5:", " - ".join(map(str,s["experimental5"])))
    st.caption(s["note"])

with tabs[5]:
    p=predict(df,target_time)
    row={
        "saved_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_draw":target_draw,"target_date":target_date,"target_time":target_time,
        "night_character":p["char"]["label"],
        "core4":"-".join(map(str,p["core4"])),
        "alt4":"-".join(map(str,p["alt4"])),
        "core5":"-".join(map(str,p["core5"])),
        "alt5":"-".join(map(str,p["alt5"])),
        "pool16":"-".join(map(str,p["tab"].head(16)["Sayı"].astype(int).tolist())),
    }
    if st.button("💾 HIZLI KAYDET",type="primary"):
        new=pd.DataFrame([row])
        if SAVE_FILE.exists():
            try: old=pd.read_csv(SAVE_FILE)
            except Exception: old=pd.DataFrame()
            new=pd.concat([old,new],ignore_index=True)
        new.to_csv(SAVE_FILE,index=False,encoding="utf-8-sig")
        st.success("Kaydedildi.")
    if SAVE_FILE.exists():
        try:
            saved=pd.read_csv(SAVE_FILE)
            st.dataframe(saved.tail(30),use_container_width=True,hide_index=True)
            st.download_button("⬇️ Kayıt CSV indir",saved.to_csv(index=False).encode("utf-8-sig"),
                               file_name="v24_kupon_kayitlari.csv",mime="text/csv")
        except Exception:
            pass

st.divider()
st.caption(
    "Araştırma aracı: çekilişler bağımsız/rastlantısaldır; 4/4 veya 5/5 garanti etmez. "
    "V24'ün amacı sabit Top-N yerine gece mekanizmasını tanıyıp bağımsız uzmanları kör testle ölçmektir."
)
