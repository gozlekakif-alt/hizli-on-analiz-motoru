
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
        for k in ["carry","return","hot","cluster","step2","cons","band","path","streak"]:
            probs[k]=shrink(sig_hits[k],sig_n[k],BASE,14 if k in ["path","carry","return"] else 18)
            supports[k]=sig_n[k]

        # destek güveni: az örnekli sinyal şişmesin
        def rel(s):
            return math.sqrt(s/(s+18.0)) if s>0 else 0.0

        # rol bazlı ana skorlar
        carry_score=(
            0.34*probs["carry"]*rel(supports["carry"]) +
            0.22*probs["path"]*rel(supports["path"]) +
            0.12*probs["streak"]*rel(supports["streak"]) +
            0.10*probs["hot"]*rel(supports["hot"]) +
            0.08*probs["cluster"]*rel(supports["cluster"]) +
            0.07*probs["cons"]*rel(supports["cons"]) +
            0.07*probs["band"]*rel(supports["band"])
        ) if in_src else 0.0

        return_score=(
            0.30*probs["return"]*rel(supports["return"]) +
            0.22*probs["path"]*rel(supports["path"]) +
            0.13*probs["hot"]*rel(supports["hot"]) +
            0.11*probs["cluster"]*rel(supports["cluster"]) +
            0.09*probs["step2"]*rel(supports["step2"]) +
            0.08*probs["cons"]*rel(supports["cons"]) +
            0.07*probs["band"]*rel(supports["band"])
        ) if not in_src else 0.0

        pattern_score=(
            0.20*probs["hot"]*rel(supports["hot"]) +
            0.18*probs["cluster"]*rel(supports["cluster"]) +
            0.14*probs["step2"]*rel(supports["step2"]) +
            0.14*probs["cons"]*rel(supports["cons"]) +
            0.16*probs["band"]*rel(supports["band"]) +
            0.18*probs["path"]*rel(supports["path"])
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
        strong=sum(probs[k] >= 0.285 for k in ["carry","return","hot","cluster","step2","cons","band","path"])
        if strong<=1:
            final-=0.018

        rows.append({
            "Sayı":n,
            "Rol":"TAŞIMA" if in_src else "DÖNÜŞ",
            "Kaynakta":in_src,
            "6-El Yol":p6,
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
            "GüçlüKanal":strong,
            "Final":final,
        })

    tab=pd.DataFrame(rows).sort_values(["Final","GüçlüKanal"],ascending=False).reset_index(drop=True)
    return tab,gc_now,expected_carry,hot_pool,common_cluster

# ============================================================
# KUPONLAR: 2 x 7 + 1 x 10
# ============================================================
def make_tickets(tab,expected_carry):
    """
    V17 — 3 bağımsız uzman.

    7A:
      Kaynak çekilişteki 20 sayıdan hangileri DEVAM eder?
      Taşıma + 6-el yol + streak + sıcaklık + ardışık/bant kanıtı.

    7B:
      Kaynakta olmayan 60 sayıdan hangileri DİNLENİP DÖNER?
      Dönüş + 6-el yol + sıcak/küme + step2 + ardışık/bant.

    10'lu:
      7A veya 7B'nin kopyası değildir.
      Benzer geçmiş gecelerden öğrenilen beklenen taşıma miktarını kullanarak
      iki bağımsız havuzdan seçim yapar.

    ÖNEMLİ:
      - Kuponları farklılaştırmak için ceza YOK.
      - Aynı sayı 7A ve 7B'ye zaten giremez; çünkü biri kaynak içi,
        diğeri kaynak dışı uzmanıdır.
      - Yüksek 'Final' tek başına seçim sebebi değildir.
    """
    z = tab.copy()

    channels = [
        "TaşımaKanıt","DönüşKanıt","SıcakKanıt","KümeKanıt",
        "Step2Kanıt","ArdışıkKanıt","BantKanıt","YolKanıt"
    ]

    # Her sinyal kendi dağılımında değerlendirilir.
    # Böylece 0.31 gibi "yüksek görünen" ham değer otomatik üstün olmaz.
    for c in channels:
        z[c+"_R"] = z[c].rank(pct=True, method="average")

    # Çoklu bağımsız kanıt kapısı.
    rcols = [c+"_R" for c in channels]
    z["Kanal70"] = z[rcols].ge(0.70).sum(axis=1)
    z["Kanal80"] = z[rcols].ge(0.80).sum(axis=1)
    z["Kanal90"] = z[rcols].ge(0.90).sum(axis=1)

    # En iyi 3 kanalın ortalaması: tek bir aşırı sinyalin aday taşımasını engeller.
    z["Top3Kanıt"] = z[rcols].apply(
        lambda r: float(np.mean(sorted([float(x) for x in r], reverse=True)[:3])),
        axis=1
    )

    # --------------------------------------------------------
    # UZMAN A — TAŞIYICI KİMLİĞİ
    # Yalnız son çekilişte bulunan 20 sayı yarışır.
    # --------------------------------------------------------
    carry = z[z["Kaynakta"]].copy()
    carry["UzmanA"] = (
        0.34*carry["TaşımaKanıt_R"] +
        0.25*carry["YolKanıt_R"] +
        0.11*carry["SıcakKanıt_R"] +
        0.09*carry["KümeKanıt_R"] +
        0.08*carry["ArdışıkKanıt_R"] +
        0.06*carry["BantKanıt_R"] +
        0.07*carry["Top3Kanıt"]
    )

    # En az 2 bağımsız iyi kanal yoksa "yüksek skor" adayını geriye at.
    carry["KapıA"] = (
        (carry["Kanal70"] >= 2) &
        (carry["TaşımaKanıt_R"] >= 0.55) &
        (carry["YolKanıt_R"] >= 0.45)
    ).astype(int)

    carry = carry.sort_values(
        ["KapıA","Kanal80","Kanal70","UzmanA","Final"],
        ascending=False
    )

    # 7A tamamen taşıma uzmanıdır. Burada 7 taşıyıcı aday gösterilir.
    # Bu, "7 sayı kesin taşınacak" demek değildir; kaynak 20 içindeki en iyi 7'yi verir.
    t7a = carry.head(7)["Sayı"].astype(int).tolist()

    # --------------------------------------------------------
    # UZMAN B — DİNLENİP DÖNÜŞ / YENİ DOĞUŞ
    # Yalnız son çekilişte OLMAYAN 60 sayı yarışır.
    # --------------------------------------------------------
    ret = z[~z["Kaynakta"]].copy()
    ret["UzmanB"] = (
        0.31*ret["DönüşKanıt_R"] +
        0.22*ret["YolKanıt_R"] +
        0.13*ret["SıcakKanıt_R"] +
        0.11*ret["KümeKanıt_R"] +
        0.09*ret["Step2Kanıt_R"] +
        0.06*ret["ArdışıkKanıt_R"] +
        0.04*ret["BantKanıt_R"] +
        0.04*ret["Top3Kanıt"]
    )

    ret["KapıB"] = (
        (ret["Kanal70"] >= 2) &
        (ret["DönüşKanıt_R"] >= 0.55) &
        (ret["YolKanıt_R"] >= 0.40)
    ).astype(int)

    ret = ret.sort_values(
        ["KapıB","Kanal80","Kanal70","UzmanB","Final"],
        ascending=False
    )
    t7b = ret.head(7)["Sayı"].astype(int).tolist()

    # --------------------------------------------------------
    # 10'LU — DİNAMİK KONSENSÜS
    # Beklenen gerçek taşıma 20 sayı içinden kaçının geçeceğini söylüyor.
    # 10'lu kupona ölçeklenir ama sert kota değildir.
    # --------------------------------------------------------
    carry_seats = int(np.clip(round(expected_carry * 10 / 20), 2, 7))
    return_seats = 10 - carry_seats

    c10 = carry.head(carry_seats)["Sayı"].astype(int).tolist()
    r10 = ret.head(return_seats)["Sayı"].astype(int).tolist()
    t10 = c10 + r10

    # 10'lu içinde sıralamayı ortak çoklu kanıta göre göster.
    multi_map = dict(zip(z["Sayı"].astype(int), z["Top3Kanıt"].astype(float)))
    t10 = sorted(
        dict.fromkeys(t10),
        key=lambda n: multi_map.get(n, 0.0),
        reverse=True
    )

    # Her ihtimale karşı 10 tamamlanmadıysa iki uzman havuzundan tamamla.
    if len(t10) < 10:
        fallback = (
            carry["Sayı"].astype(int).tolist() +
            ret["Sayı"].astype(int).tolist()
        )
        for n in fallback:
            if n not in t10:
                t10.append(n)
            if len(t10) == 10:
                break

    meta = {
        "expected_carry": float(expected_carry),
        "carry_seats_10": int(carry_seats),
        "return_seats_10": int(return_seats),
        "overlap_7a_7b": len(set(t7a) & set(t7b)),
    }

    return {
        "7A": t7a[:7],
        "7B": t7b[:7],
        "10": t10[:10],
        "_meta": meta,
    }

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
            tickets=make_tickets(tab,expected_carry)
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
                "Bu hedef son yüklenen gerçek sonuç dahil edilerek yeniden hesaplandı. "
                "7A yalnız kaynak 20 sayıdaki taşıyıcıları; 7B yalnız kaynak dışındaki dinlenip-dönenleri inceler. "
                f"10'lu: {meta.get('carry_seats_10','-')} taşıma + "
                f"{meta.get('return_seats_10','-')} dönüş koltuğu. "
                f"7A–7B zorunlu ortak sayı: {meta.get('overlap_7a_7b',0)}."
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
                "Step2Kanıt","ArdışıkKanıt","BantKanıt","YolKanıt","Final"
            ]:
                show[c]=show[c].map(lambda x:round(float(x),3))
            st.dataframe(
                show[[
                    "Sayı","Rol","Kaynakta","6-El Yol","Gap","Streak",
                    "GeceFrekans","SıcakHavuz","OrtakKüme","Step2Destek",
                    "ArdışıkDestek","Bant","TaşımaKanıt","DönüşKanıt",
                    "SıcakKanıt","KümeKanıt","Step2Kanıt","ArdışıkKanıt",
                    "BantKanıt","YolKanıt","GüçlüKanal","Final"
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
    "V16’nın ana ilkesi: ham yüksek skor seçim sebebi değildir; aday en az iki bağımsız kanıttan destek almalıdır. "
    "Bir adayın güçlü kalması için taşıma/dönüş + 6-el yol + gece sıcaklığı + küme/pattern + bant/komşuluk "
    "kanallarından birden fazlasının geçmişte gerçekten isabet üretmiş olması gerekir."
)
