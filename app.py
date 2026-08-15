
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import base64, json, math, re, urllib.parse, urllib.request

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On V9 23:17 Ritm Motoru", page_icon="🎯", layout="wide")

st.title("🎯 Hızlı On V9 — 23:17 Ritm / Taşıma / Dönüş Motoru")
st.caption(
    "İlk 3 çekilişten oyunun karakterini okur; gün içi sıcaklaşma, taşıma, dinlenip dönüş, "
    "ardışık blok ve 6x6 yol ritmini birlikte değerlendirir. Hedef: yalnız 23:17."
)

DATA_FILE = Path("veri.txt")
SLOTS = ["23:02","23:07","23:12","23:17","23:22","23:27","23:32","23:37","23:42","23:47","23:52","23:57"]
INPUTS = ["23:02","23:07","23:12"]
TARGET = "23:17"
BASE = 0.25
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"

# ============================================================
# GITHUB / VERİ
# ============================================================
def github_config():
    token=""
    repo=DEFAULT_REPO
    branch=DEFAULT_BRANCH
    path=DEFAULT_PATH
    try:
        token=str(st.secrets.get("GITHUB_TOKEN","")).strip()
        repo=str(st.secrets.get("GITHUB_REPO",repo)).strip() or repo
        branch=str(st.secrets.get("GITHUB_BRANCH",branch)).strip() or branch
        path=str(st.secrets.get("GITHUB_DATA_PATH",path)).strip() or path
    except Exception:
        pass
    return token,repo,branch,path

def github_read(token,repo,branch,path):
    url=f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    req=urllib.request.Request(url,headers={
        "Authorization":f"Bearer {token}",
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"hizli-on-v9"
    })
    with urllib.request.urlopen(req,timeout=20) as r:
        obj=json.loads(r.read().decode("utf-8"))
    return base64.b64decode(obj["content"]).decode("utf-8"),obj["sha"]

def github_write(token,repo,branch,path,text,msg):
    _,sha=github_read(token,repo,branch,path)
    url=f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    body=json.dumps({
        "message":msg,
        "content":base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha":sha,
        "branch":branch
    }).encode("utf-8")
    req=urllib.request.Request(url,data=body,method="PUT",headers={
        "Authorization":f"Bearer {token}",
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "Content-Type":"application/json",
        "User-Agent":"hizli-on-v9"
    })
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def parse_pipe(text):
    rows=[]
    for raw in str(text).splitlines():
        p=[x.strip() for x in raw.split("|")]
        if len(p)<3: continue
        try:
            no=int(p[0]); d,t=p[1].split()
            nums=sorted(set(int(x) for x in re.findall(r"\d+",p[2])))
        except Exception:
            continue
        if t not in SLOTS or len(nums)!=20 or any(n<1 or n>80 for n in nums):
            continue
        rows.append({"draw_no":no,"date":d,"time":t,"numbers":nums})
    df=pd.DataFrame(rows)
    if df.empty: return df
    df["_dt"]=pd.to_datetime(df["date"]+" "+df["time"],format="%d.%m.%Y %H:%M",errors="coerce")
    df=df.dropna(subset=["_dt"])
    return (df.sort_values(["_dt","draw_no"])
              .drop_duplicates(["date","time"],keep="last")
              .reset_index(drop=True))

def parse_result_block(raw):
    raw=str(raw or "").replace("\u00a0"," ").replace("–","-").replace("—","-")
    m_no=re.search(r"(?:çekiliş|cekilis)\s*(?:no|numarası|numarasi)?\s*[:#-]?\s*(\d{4,})",raw,re.I)
    m_dt=re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}:\d{2})",raw)
    if not m_no: raise ValueError("Çekiliş no bulunamadı.")
    if not m_dt: raise ValueError("Tarih/saat bulunamadı.")
    no=int(m_no.group(1))
    d=datetime.strptime(m_dt.group(1),"%d.%m.%Y").strftime("%d.%m.%Y")
    t=m_dt.group(2)
    tail=raw[m_dt.end():]
    nums=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",tail)]
    if len(nums)!=20 or len(set(nums))!=20:
        raise ValueError(f"20 farklı sayı bekleniyor; {len(nums)} bulundu.")
    return {"draw_no":no,"date":d,"time":t,"numbers":sorted(nums)}

def line_for(r):
    return f"{r['draw_no']} | {r['date']} {r['time']} | {' '.join(map(str,r['numbers']))}"

def append_or_replace(text,r):
    key=f"{r['date']} {r['time']}"
    nl=line_for(r); out=[]; done=False
    for raw in str(text).splitlines():
        if not raw.strip(): continue
        p=[x.strip() for x in raw.split("|")]
        if len(p)>=2 and p[1]==key:
            if not done:
                out.append(nl); done=True
            continue
        out.append(raw.rstrip())
    if not done: out.append(nl)
    return "\n".join(out).rstrip()+"\n"

def persist_result(r):
    token,repo,branch,path=github_config()
    if token:
        cur,_=github_read(token,repo,branch,path)
        upd=append_or_replace(cur,r)
        if upd!=cur:
            github_write(token,repo,branch,path,upd,f"V9 add {r['draw_no']} {r['date']} {r['time']}")
        return upd,True
    cur=DATA_FILE.read_text(encoding="utf-8") if DATA_FILE.exists() else ""
    upd=append_or_replace(cur,r)
    DATA_FILE.write_text(upd,encoding="utf-8")
    return upd,False

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
# OYUN KARAKTERİ / ÖZELLİKLER
# ============================================================
def day_map(df):
    out={}
    for _,r in df.iterrows():
        out.setdefault(str(r["date"]),{})[str(r["time"])]=set(r["numbers"])
    return out

def ordered_dates(df):
    return list(dict.fromkeys(df["date"].astype(str).tolist()))

def path3(n,a,b,c):
    return f"{int(n in a)}{int(n in b)}{int(n in c)}"

def path6(prev6,n):
    return "".join("1" if n in s else "0" for s in prev6)

def gap(prev_sets,n,maxgap=10):
    g=0
    for s in reversed(prev_sets[-maxgap:]):
        if n in s: return g
        g+=1
    return min(g,maxgap)

def consecutive_blocks(s):
    arr=sorted(s); blocks=[]; cur=[]
    for n in arr:
        if not cur or n==cur[-1]+1:
            cur.append(n)
        else:
            if len(cur)>=2: blocks.append(cur)
            cur=[n]
    if len(cur)>=2: blocks.append(cur)
    return blocks

def current_hotness(n,a,b,c):
    # Günün kendi içindeki sıcaklaşması
    return int(n in a)+int(n in b)+int(n in c)

def trend_label(n,a,b,c):
    p=path3(n,a,b,c)
    return {
        "001":"YENİ DOĞDU",
        "011":"ISINIYOR / DEVAM",
        "111":"SICAK / UZUYOR",
        "101":"GERİ DÖNDÜ",
        "110":"SÖNÜŞ ADAYI",
        "010":"ARA SICAK",
        "100":"SOĞUDU",
        "000":"UYKU"
    }[p]

def game_character(a,b,c):
    c1=len(a&b); c2=len(b&c); c3=len(a&c)
    blocks=sum(len(consecutive_blocks(x)) for x in [a,b,c])
    if c1>=6 and c2>=6:
        regime="TAŞIMA-AĞIR"
    elif c1<=3 and c2<=3:
        regime="DÖNÜŞ-AĞIR"
    else:
        regime="KARMA"
    return {
        "regime":regime,
        "carry_02_07":c1,
        "carry_07_12":c2,
        "cross_02_12":c3,
        "block_pressure":blocks
    }

def shrink(h,n,prior=BASE,strength=18):
    return (h+prior*strength)/(n+strength)

def build_event_bank(df):
    dm=day_map(df); dates=ordered_dates(df)
    events=[]
    for d in dates:
        if all(s in dm.get(d,{}) for s in INPUTS+[TARGET]):
            a,b,c,y=[dm[d][s] for s in INPUTS+[TARGET]]
            gc=game_character(a,b,c)
            events.append({"date":d,"a":a,"b":b,"c":c,"y":y,"gc":gc})
    return events

def score_candidates(df):
    dm=day_map(df); dates=ordered_dates(df)
    if not dates: raise ValueError("Veri yok.")
    d=dates[-1]
    if not all(s in dm.get(d,{}) for s in INPUTS):
        miss=[s for s in INPUTS if s not in dm.get(d,{})]
        raise ValueError("23:17 için önce: "+", ".join(miss))
    a,b,c=[dm[d][s] for s in INPUTS]
    now_gc=game_character(a,b,c)
    events=build_event_bank(df)
    events=[e for e in events if e["date"]!=d]
    if len(events)<18:
        raise ValueError("En az 18 tamamlanmış 23:17 geçmiş günü gerekli.")

    # benzer günleri oyun karakterine göre ağırlıklandır
    scored_events=[]
    for e in events:
        dist=(
            abs(e["gc"]["carry_02_07"]-now_gc["carry_02_07"])/10 +
            abs(e["gc"]["carry_07_12"]-now_gc["carry_07_12"])/10 +
            abs(e["gc"]["cross_02_12"]-now_gc["cross_02_12"])/10 +
            abs(e["gc"]["block_pressure"]-now_gc["block_pressure"])/12
        )
        if e["gc"]["regime"]!=now_gc["regime"]:
            dist+=0.25
        w=1/(0.08+dist)
        scored_events.append((w,e))
    scored_events.sort(key=lambda z:z[0],reverse=True)
    near=scored_events[:min(24,len(scored_events))]

    # son 6 çekiliş, 6x6 yol ritmi
    sets=[set(x) for x in df["numbers"]]
    prev6=sets[-6:]

    rows=[]
    for n in range(1,81):
        p3=path3(n,a,b,c)
        p6=path6(prev6,n)
        in12=n in c
        hot=current_hotness(n,a,b,c)
        gp=gap(prev6,n)
        tr=trend_label(n,a,b,c)

        # Kanal 1: aynı 3-el yol
        h=nobs=0.0
        # Kanal 2: aynı oyun karakteri + aynı kaynak tarafı
        h2=n2=0.0
        # Kanal 3: aynı 6x6 ritim sonu
        h3=n3=0.0
        # Kanal 4: dinlenme/dönüş
        h4=n4=0.0
        # Kanal 5: gün-içi sıcaklaşma seviyesi
        h5=n5=0.0

        for w,e in near:
            ep3=path3(n,e["a"],e["b"],e["c"])
            hit=int(n in e["y"])
            if ep3==p3:
                h+=w*hit; nobs+=w
            if (n in e["c"])==in12:
                h2+=w*hit; n2+=w

            # tarihsel günün ilk 3 çekilişi ritimle karşılaştır
            ehist=[e["a"],e["b"],e["c"]]
            ep6=("000"+ep3)[-6:]
            if ep6[-3:]==p6[-3:]:
                h3+=w*hit; n3+=w

            # dönüş/dinlenme cepleri
            egap=0 if n in e["c"] else (1 if n in e["b"] else 2 if n in e["a"] else 3)
            ngap=0 if in12 else (1 if n in b else 2 if n in a else 3)
            if egap==ngap:
                h4+=w*hit; n4+=w

            ehot=int(n in e["a"])+int(n in e["b"])+int(n in e["c"])
            if ehot==hot:
                h5+=w*hit; n5+=w

        r1=shrink(h,nobs,BASE,10)
        r2=shrink(h2,n2,BASE,18)
        r3=shrink(h3,n3,BASE,16)
        r4=shrink(h4,n4,BASE,14)
        r5=shrink(h5,n5,BASE,12)

        # ardışık / komşuluk yalnız destek
        neighbor=int((n-1) in c)+int((n+1) in c)
        block_bonus=0.006*neighbor

        # Ana kanıt
        raw=0.34*r1+0.20*r2+0.18*r3+0.16*r4+0.12*r5+block_bonus
        support=nobs+0.6*n2+0.5*n3+0.5*n4+0.5*n5
        reliability=math.sqrt(support/(support+22)) if support>0 else 0
        evidence=BASE+(raw-BASE)*reliability

        # sahte sıcak cezaları / yaşam düzeltmeleri
        if tr=="SICAK / UZUYOR" and r1<0.27:
            evidence-=0.015
        if tr=="SÖNÜŞ ADAYI":
            evidence-=0.010
        if tr in ("YENİ DOĞDU","GERİ DÖNDÜ") and r4>0.27:
            evidence+=0.010

        rows.append({
            "Sayı":n,
            "Kaynakta12":in12,
            "3-El Yol":p3,
            "6x6 Yol":p6,
            "Trend":tr,
            "Gün Sıcaklığı":hot,
            "Gap":gp,
            "Komşu":neighbor,
            "YolKanıt":r1,
            "KarakterKanıt":r2,
            "RitimKanıt":r3,
            "DönüşKanıt":r4,
            "SıcaklıkKanıt":r5,
            "Destek":support,
            "Kanıt":evidence
        })

    tab=pd.DataFrame(rows)
    # ayrı ligler
    tab["TaşımaSıra"]=999; tab["DönüşSıra"]=999
    ci=tab.index[tab["Kaynakta12"]]; ri=tab.index[~tab["Kaynakta12"]]
    tab.loc[ci,"TaşımaSıra"]=tab.loc[ci,"Kanıt"].rank(ascending=False,method="first").astype(int)
    tab.loc[ri,"DönüşSıra"]=tab.loc[ri,"Kanıt"].rank(ascending=False,method="first").astype(int)
    return tab.sort_values(["Kanıt","Destek"],ascending=False).reset_index(drop=True),now_gc,d

def make_tickets(tab,gc):
    carry=tab[tab["Kaynakta12"]].sort_values(["Kanıt","Destek"],ascending=False)
    ret=tab[~tab["Kaynakta12"]].sort_values(["Kanıt","Destek"],ascending=False)

    # karaktere göre taşıma koltuğu
    if gc["regime"]=="TAŞIMA-AĞIR":
        base_c=4
    elif gc["regime"]=="DÖNÜŞ-AĞIR":
        base_c=2
    else:
        base_c=3

    out={}
    for size in [6,7,8,9,10]:
        cseats=int(np.clip(round(base_c*size/10),1,min(4,size-2)))
        rseats=size-cseats
        cand=pd.concat([carry.head(cseats),ret.head(rseats)])
        cand=cand.sort_values(["Kanıt","Destek"],ascending=False)
        out[size]=cand["Sayı"].astype(int).tolist()
    return out

def evaluate_tickets(tickets,actual):
    rows=[]
    actual=set(actual)
    for size in [6,7,8,9,10]:
        t=tickets[size]
        hits=sorted(set(t)&actual)
        rows.append({
            "Kupon":f"{size}'li",
            "İsabet":f"{len(hits)}/{size}",
            "Tutanlar":" ".join(f"{n:02d}" for n in hits),
            "Kupon":" ".join(f"{n:02d}" for n in t)
        })
    return pd.DataFrame(rows)

# ============================================================
# UI
# ============================================================
df,source=load_df()
if df.empty:
    st.error("veri.txt yok.")
    st.stop()

st.caption(
    f"📂 {source} · {len(df)} çekiliş · {df['date'].nunique()} gece · "
    f"son: #{df.iloc[-1]['draw_no']} {df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

token,_,_,_=github_config()
if token:
    st.caption("🔒 Kalıcı GitHub veri.txt kayıt: AÇIK")
else:
    st.warning("GITHUB_TOKEN yok; kalıcı GitHub kaydı kapalı.")

with st.expander("⚡ HIZLI SONUÇ EKLE",expanded=False):
    txt=st.text_area("Sonucu aynen yapıştır",height=230,key="quick")
    if st.button("💾 KAYDET + YENİLE",use_container_width=True,key="quick_btn"):
        try:
            r=parse_result_block(txt)
            persist_result(r)
            st.success(f"#{r['draw_no']} kaydedildi.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

tabs=st.tabs(["🏆 KUPONLAR","🧬 OYUN KARAKTERİ","🔬 ADAY AYRIŞIMI"])

with tabs[0]:
    try:
        tab,gc,target_date=score_candidates(df)
        tickets=make_tickets(tab,gc)
        st.session_state["v9_pred"]={"date":target_date,"time":"23:17","tickets":tickets}

        a,b,c,d=st.columns(4)
        a.metric("Karakter",gc["regime"])
        b.metric("02→07 taşıma",gc["carry_02_07"])
        c.metric("07→12 taşıma",gc["carry_07_12"])
        d.metric("Ardışık baskı",gc["block_pressure"])

        for size in [6,7,8,9,10]:
            st.markdown(f"### 🎯 {size}'Lİ KUPON")
            st.code("  ".join(f"{n:02d}" for n in tickets[size]))
    except Exception as e:
        st.warning(str(e))

with tabs[1]:
    try:
        tab,gc,target_date=score_candidates(df)
        st.subheader("🧬 İlk 3 çekiliş oyunu nasıl oynuyor?")
        st.json(gc)
        st.info(
            "TAŞIMA-AĞIR: kaynak sayı koltuğu artar · DÖNÜŞ-AĞIR: dinlenip gelen koltuğu artar · "
            "KARMA: iki taraf dengelenir."
        )
    except Exception as e:
        st.warning(str(e))

with tabs[2]:
    try:
        tab,gc,target_date=score_candidates(df)
        show=tab.copy()
        for c in ["YolKanıt","KarakterKanıt","RitimKanıt","DönüşKanıt","SıcaklıkKanıt","Destek","Kanıt"]:
            show[c]=show[c].map(lambda x:round(float(x),3))
        st.dataframe(
            show[[
                "Sayı","Kaynakta12","3-El Yol","6x6 Yol","Trend","Gün Sıcaklığı","Gap","Komşu",
                "YolKanıt","KarakterKanıt","RitimKanıt","DönüşKanıt","SıcaklıkKanıt","Destek","Kanıt"
            ]],
            use_container_width=True,hide_index=True
        )
    except Exception as e:
        st.warning(str(e))

st.divider()
st.subheader("✅ SONUCU EKLE + KUPONLARI TEST ET + TXT'YE KAYDET")
real=st.text_area("Gerçek hedef sonucu",height=250,key="real_result")
if st.button("🏁 TEST ET + KALICI KAYDET",type="primary",use_container_width=True):
    try:
        r=parse_result_block(real)
        pred=st.session_state.get("v9_pred")
        if pred and r["date"]==pred["date"] and r["time"]==pred["time"]:
            st.session_state["v9_eval"]=evaluate_tickets(pred["tickets"],r["numbers"])
            st.session_state["v9_eval_title"]=f"#{r['draw_no']} {r['date']} {r['time']}"
        else:
            st.session_state["v9_eval"]=pd.DataFrame([{
                "Kupon":"-","İsabet":"-","Tutanlar":"Eşleşen hedef tahmini yok.","Kupon":"-"
            }])
        persist_result(r)
        st.session_state["saved_msg"]=f"✅ #{r['draw_no']} test edildi ve veri.txt'ye kaydedildi."
        st.rerun()
    except Exception as e:
        st.error(str(e))

if "saved_msg" in st.session_state:
    st.success(st.session_state.pop("saved_msg"))

if "v9_eval" in st.session_state:
    st.markdown(f"### 📊 Son kupon karnesi — {st.session_state.get('v9_eval_title','')}")
    st.dataframe(st.session_state["v9_eval"],use_container_width=True,hide_index=True)

st.caption(
    "Bu motor yüksek ham skor değil, benzer geçmiş olaylarda tekrarlanmış kanıt arar. "
    "Geçmiş performans gelecekteki bağımsız çekilişleri garanti etmez."
)
