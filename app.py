import streamlit as st
import pandas as pd
import numpy as np
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import math, sqlite3, json

st.set_page_config(page_title="Hızlı On — REAL20 CANLI V6", page_icon="🧠", layout="wide")
st.title("🧠 Hızlı On — REAL20 CANLI V6")
st.caption("PRE-H karar motoru • H1/H2/H3/H4-H6/H7-H12/DEEP • aile nöbeti • kaynak hakemi • dondurulmuş ileri test")

ROOT = Path(__file__).parent
DB = ROOT / "ana_beyin_v2.sqlite"

# ============================================================
# VERİ
# ============================================================
def parse_text(text):
    rows=[]
    for line in text.splitlines():
        line=line.strip()
        if not line:
            continue
        p=[x.strip() for x in line.split(";")]
        if len(p) >= 3:
            try:
                draw=int("".join(ch for ch in p[0] if ch.isdigit()))
                dt=pd.to_datetime(p[1], dayfirst=True, errors="raise")
                nums=tuple(sorted({int(x) for x in p[2].replace(" ", "").split(",") if x.strip()}))
                if len(nums)==20 and min(nums)>=1 and max(nums)<=80:
                    rows.append((draw,dt,nums))
                    continue
            except Exception:
                pass
    if not rows:
        return pd.DataFrame(columns=["draw","dt","nums"])
    d=pd.DataFrame(rows,columns=["draw","dt","nums"])
    d=d.drop_duplicates("draw",keep="last").sort_values(["dt","draw"]).reset_index(drop=True)
    return d

def load_base():
    candidates=[
        ROOT/"veri.txt",
        ROOT/"veri (6).txt",
        ROOT/"HIZLI_ON_14_GUN.txt",
    ]
    for p in candidates:
        if p.exists():
            d=parse_text(p.read_text(encoding="utf-8-sig",errors="ignore"))
            if not d.empty:
                return d,p.name
    up=st.sidebar.file_uploader("14 günlük veri TXT",type=["txt"])
    if up is None:
        return pd.DataFrame(),None
    d=parse_text(up.getvalue().decode("utf-8-sig",errors="ignore"))
    return d,up.name

def init_db():
    con=sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS frozen_predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        target_draw INTEGER,
        target_time TEXT,
        history_last_draw INTEGER,
        final5 TEXT,
        final10 TEXT,
        source_plan TEXT,
        diagnostics TEXT,
        checked INTEGER DEFAULT 0,
        hit5 INTEGER,
        hit10 INTEGER,
        real_numbers TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS live_draws(
        draw INTEGER PRIMARY KEY,
        dt TEXT NOT NULL,
        nums TEXT NOT NULL,
        saved_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS coupon_sets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        target_draw INTEGER,
        history_last_draw INTEGER,
        coupon4_a TEXT,
        coupon4_b TEXT,
        coupon5 TEXT,
        diagnostics TEXT,
        checked INTEGER DEFAULT 0,
        hit4_a INTEGER,
        hit4_b INTEGER,
        hit5 INTEGER,
        real_numbers TEXT
    )""")
    con.commit()
    con.close()

init_db()
base,src=load_base()
if base.empty:
    st.info("14 günlük TXT dosyasını yükle. Beklenen satır: çekiliş_no;gg.aa.yyyy SS:DD;20 sayı virgülle")
    st.stop()

def load_saved_live():
    con=sqlite3.connect(DB)
    q=pd.read_sql_query("SELECT draw,dt,nums FROM live_draws ORDER BY dt,draw",con)
    con.close()
    if q.empty:
        return pd.DataFrame(columns=["draw","dt","nums"])
    q["dt"]=pd.to_datetime(q["dt"],errors="coerce")
    q["nums"]=q["nums"].apply(lambda s: tuple(sorted(int(x) for x in str(s).split(",") if x)))
    return q.dropna(subset=["dt"])

def save_live_draw(draw,dt,nums):
    con=sqlite3.connect(DB)
    con.execute("""INSERT OR REPLACE INTO live_draws(draw,dt,nums) VALUES(?,?,?)""",
                (int(draw),pd.Timestamp(dt).isoformat(),",".join(map(str,sorted(nums)))))
    con.commit(); con.close()

# Kalıcı canlı çekilişler
saved_live=load_saved_live()

st.sidebar.markdown("### 📋 YENİ ÇEKİLİŞ SONUCU")
st.sidebar.caption("Milli Piyango sonucunu başlık + tarih/saat + 20 sayı olarak TEK PARÇA yapıştır.")

with st.sidebar.form("paste_draw_form", clear_on_submit=True):
    pasted_result=st.text_area(
        "Sonucu buraya yapıştır",
        height=310,
        placeholder="""Çekiliş no: 54260
08.09.2026 - 00:47
7
10
17
21
25
26
27
28
30
38
41
42
49
51
59
60
65
66
71
74"""
    )
    paste_save=st.form_submit_button("💾 KAYDET VE ANALİZ ET",type="primary",use_container_width=True)

    if paste_save:
        try:
            raw=pasted_result.strip()
            if not raw:
                raise ValueError("Sonuç metni boş.")

            m=re.search(r"Çekiliş\s*no\s*[:#]?\s*(\d+)",raw,flags=re.I)
            if not m:
                raise ValueError("Çekiliş no bulunamadı.")
            draw_no=int(m.group(1))

            dm=re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[-–]?\s*(\d{2}:\d{2})",raw)
            if not dm:
                raise ValueError("Tarih/saat bulunamadı.")
            draw_dt=pd.to_datetime(dm.group(1)+" "+dm.group(2),dayfirst=True,errors="raise")

            # Yalnız tarih/saatten SONRAKİ bağımsız satırlardaki 1–80 değerlerini al.
            tail=raw[dm.end():]
            nums=[]
            for line in tail.splitlines():
                line=line.strip()
                if re.fullmatch(r"\d{1,2}",line):
                    x=int(line)
                    if 1<=x<=80:
                        nums.append(x)

            # Bazı kopyalamalarda sayılar tek satıra dönüşürse güvenli yedek parser.
            if len(nums)!=20:
                nums=[int(x) for x in re.findall(r"(?<!\d)(?:80|[1-7]?\d)(?!\d)",tail)]
                nums=[x for x in nums if 1<=x<=80]

            # Sıra korunur; tekrar kabul edilmez.
            if len(nums)!=20 or len(set(nums))!=20:
                raise ValueError(f"Tam 20 farklı çekiliş sayısı bulunamadı. Algılanan: {len(nums)}")

            save_live_draw(draw_no,draw_dt,tuple(sorted(nums)))
            st.success(f"#{draw_no} · {draw_dt.strftime('%d.%m.%Y %H:%M')} · 20 sayı KALICI kaydedildi.")
            st.rerun()

        except Exception as e:
            st.error(f"Kayıt hatası: {e}")

# Tek giriş yolu: yukarıdaki tam sonuç yapıştırma alanı.
saved_live=load_saved_live()
live=pd.DataFrame(columns=["draw","dt","nums"])
df=pd.concat([base,saved_live],ignore_index=True)
df=df.drop_duplicates("draw",keep="last").sort_values(["dt","draw"]).reset_index(drop=True)
sets=[set(x) for x in df.nums]
N=len(df)

st.sidebar.success(f"{src} + canlı: {N} çekiliş")
if len(base)==3038:
    st.sidebar.success("14 gün / 3038 ana kütük algılandı")
else:
    st.sidebar.warning(f"Ana kütük {len(base)} çekiliş. 3038 bekleniyordu.")

# ============================================================
# PRE-H ÖZELLİKLER
# ============================================================
def age_at(t,n):
    """Hedef indeks t açılmadan önce n'nin son görülme yaşı."""
    for j in range(t-1,-1,-1):
        if n in sets[j]:
            return t-j
    return 999

def prev_gap_at(t,n):
    hits=[j for j in range(t-1,-1,-1) if n in sets[j]]
    if len(hits)<2:
        return 999
    return hits[0]-hits[1]

def count_last(t,n,w):
    lo=max(0,t-w)
    return sum(n in sets[j] for j in range(lo,t))

def delta12(t,n):
    # son 6 el ile önceki 6 el farkı
    a=sum(n in sets[j] for j in range(max(0,t-6),t))
    b=sum(n in sets[j] for j in range(max(0,t-12),max(0,t-6)))
    return a-b

def band(n):
    return (n-1)//10

def band_occ(t,b,w=1):
    lo=max(0,t-w)
    return sum(sum(1 for n in sets[j] if band(n)==b) for j in range(lo,t))

def direct_coocc(t,a,b,w=12):
    lo=max(0,t-w)
    return sum(a in sets[j] and b in sets[j] for j in range(lo,t))

def h1_set(t):
    return set() if t<1 else sets[t-1]

def h_age_groups(t):
    groups=defaultdict(list)
    for n in range(1,81):
        a=age_at(t,n)
        groups[a].append(n)
    return groups

def co_life_with_current_h1(t,n,w=12):
    h1=h1_set(t)
    if not h1:
        return 0
    return sum(direct_coocc(t,n,m,w) for m in h1 if m!=n)

def max_direct_with_h1(t,n,w=12):
    h1=h1_set(t)
    vals=[direct_coocc(t,n,m,w) for m in h1 if m!=n]
    return max(vals) if vals else 0

def older_h1_colife(t,n,w=24):
    # H2..H12 üyeleri ile son w elde ortak yaşam
    older=[m for m in range(1,81) if 2 <= age_at(t,m) <= 12 and m!=n]
    return sum(direct_coocc(t,n,m,w) for m in older)

# ============================================================
# AİLE MOTORU — ÜYEYİ DEĞİL ROLÜ TAKİP ET
# ============================================================
def pair_history_score(t,a,b,w=48):
    lo=max(0,t-w)
    both=sum(a in sets[j] and b in sets[j] for j in range(lo,t))
    if t-lo==0:
        return 0.0
    fa=sum(a in sets[j] for j in range(lo,t))
    fb=sum(b in sets[j] for j in range(lo,t))
    p=both/(t-lo)
    exp=(fa/(t-lo))*(fb/(t-lo))
    lift=p/exp if exp>0 else 0
    return both + min(lift,3)

def family_role_score(t,n):
    """
    Aile skoru:
    - current H1 ile geçmiş ortak yaşam
    - aynı H yaş katmanındaki diğer adaylarla ortak yaşam
    - son 24/48 elde tekrarlanan 2'li bağlar
    Sabit aileyi zorlamaz; üyeler her hedefte yeniden seçilir.
    """
    a=age_at(t,n)
    peers=[m for m in range(1,81) if m!=n and abs(age_at(t,m)-a)<=1]
    h1=list(h1_set(t)-{n})
    best_h1=sorted((pair_history_score(t,n,m,36),m) for m in h1)[-3:]
    best_peer=sorted((pair_history_score(t,n,m,48),m) for m in peers)[-3:]
    score=sum(x[0] for x in best_h1)*0.18 + sum(x[0] for x in best_peer)*0.10
    partners=[m for _,m in sorted(best_h1+best_peer,reverse=True)[:3]]
    return score,partners

def build_families(t,candidates):
    # adaylar arasındaki en güçlü 2'li/3'lü bağları gösterir
    pairs=[]
    for a,b in combinations(sorted(set(candidates)),2):
        s=pair_history_score(t,a,b,48)
        pairs.append((s,(a,b)))
    pairs=sorted(pairs,reverse=True)
    used=set()
    fams=[]
    for s,p in pairs:
        if s<=0:
            continue
        if len(fams)>=5:
            break
        fams.append({"tip":"2'li","uyeler":p,"skor":round(float(s),3)})
        used.update(p)
    # en iyi üçlü: üç pair bağının toplamı
    triples=[]
    pool=sorted(set(candidates))[:20]
    for tri in combinations(pool,3):
        s=sum(pair_history_score(t,*p,48) for p in combinations(tri,2))
        triples.append((s,tri))
    if triples:
        s,tri=max(triples)
        fams.insert(0,{"tip":"3'lü","uyeler":tri,"skor":round(float(s),3)})
    return fams[:6]

# ============================================================
# UZMAN MOTORLAR
# Kütükteki kaynak sınıfları:
# H1 / SHORT(H2-H3) / MID(H4-H6) / LONG(H7-H12) / DEEP(H13+)
# ============================================================
def source_supply(t):
    ages={n:age_at(t,n) for n in range(1,81)}
    return {
        "H1":sum(a==1 for a in ages.values()),
        "SHORT":sum(2<=a<=3 for a in ages.values()),
        "MID":sum(4<=a<=6 for a in ages.values()),
        "LONG":sum(7<=a<=12 for a in ages.values()),
        "DEEP":sum(a>=13 for a in ages.values()),
    }

def source_regime(t):
    s=source_supply(t)
    # V30/V31 kaynak geometrisi
    reg={
        "SHORT":"HIGH" if s["SHORT"]>=28 else ("LOW" if s["SHORT"]<=25 else "MID"),
        "MID":"HIGH" if s["MID"]>=21 else ("LOW" if s["MID"]<=18 else "MID"),
        "LONG":"HIGH" if s["LONG"]>=13 else ("LOW" if s["LONG"]<=10 else "MID"),
        "DEEP":"HIGH" if s["DEEP"]>=3 else "LOW",
    }
    return s,reg

def candidate_row(t,n):
    a=age_at(t,n)
    pg=prev_gap_at(t,n)
    d12=delta12(t,n)
    h6=count_last(t,n,6)
    h24=count_last(t,n,24)
    h1co=co_life_with_current_h1(t,n,12)
    h1max=max_direct_with_h1(t,n,12)
    oldco=older_h1_colife(t,n,24)
    fam,partners=family_role_score(t,n)

    src="OTHER"
    if a==1: src="H1"
    elif 2<=a<=3: src="SHORT"
    elif 4<=a<=6: src="MID"
    elif 7<=a<=12: src="LONG"
    elif a>=13: src="DEEP"

    signals=[]
    raw=0.0

    # H1: TEAM2 / TEAM3C / PAIR2C benzeri katman
    if src=="H1":
        if d12>=3 and oldco>=18:
            signals.append("H1_TEAM2"); raw+=4.0
        elif d12>=3 and oldco<=15:
            signals.append("H1_TEAM3C"); raw+=2.5
        if d12>=3 and h6>=4 and h24>=10:
            signals.append("H1_PAIR2C_ANCHOR"); raw+=5.0
        if oldco>=35:
            signals.append("H1_ABSENT_LONG35"); raw+=3.0

    # SHORT exact
    if a==2:
        # band değişimi H-2 -> H-1
        b=band(n)
        prev1=band_occ(t,b,1)
        prev2=band_occ(max(0,t-1),b,1) if t>=2 else prev1
        change=prev1-prev2
        if pg>=5 and change==-1:
            signals.append("H2_C1"); raw+=5.0
        if not (pg>=5 and change==-1) and 8<=pg<=10 and change==0:
            signals.append("H2_C2a"); raw+=2.5
    if a==3:
        if d12>=3 and h1max<=2:
            signals.append("H3_A"); raw+=4.5
        if d12>=3 and h1co>=27:
            signals.append("H3_B"); raw+=3.5

    # MID exact
    if a==4:
        b=band(n)
        now=band_occ(t,b,1)
        old=band_occ(max(0,t-3),b,1) if t>=3 else now
        if now-old>=1:
            signals.append("H4"); raw+=2.5
    if a==5 and count_last(t,n,6)>=3 and oldco>=19:
        signals.append("H5"); raw+=4.0
    if a==6 and d12>=1:
        signals.append("H6"); raw+=3.0

    # LONG exact
    if a==7 and pg>=15:
        signals.append("H7"); raw+=4.5
    if a==8 and pg>=11:
        signals.append("H8"); raw+=3.5
    if a==9 and oldco<=10:
        signals.append("H9"); raw+=3.0
    if 10<=a<=12:
        # gözlem: exact V1 LONG kapısı H7/H8/H9; H10-12 filler yapılmaz
        signals.append("LONG_OBS"); raw+=0.5

    # DEEP strict
    if 13<=a<=15 and d12<=-5 and h1max>=3:
        signals.append("DEEP_STRICT"); raw+=5.0

    raw += fam
    return {
        "Sayı":n,"H_yaşı":a,"Kaynak":src,"prior_gap":pg,"delta12":d12,
        "h6":h6,"h24":h24,"H1_co12":h1co,"H1_maxco12":h1max,
        "older_co24":oldco,"Aile_skor":round(fam,3),
        "Aile_partner":",".join(map(str,partners)),
        "Sinyal":" + ".join(signals) if signals else "ABSTAIN",
        "Ham_skor":round(raw,3)
    }

def run_brain(t):
    supply,reg=source_regime(t)
    rows=[candidate_row(t,n) for n in range(1,81)]
    tab=pd.DataFrame(rows)

    # Kaynak aktivasyonu: aday sinyali + PRE-H kaynak geometrisi.
    active={}
    for src in ["H1","SHORT","MID","LONG","DEEP"]:
        z=tab[(tab.Kaynak==src)&(tab.Sinyal!="ABSTAIN")]
        active[src]=len(z)

    # LONG gate: H7 sinyali veya H7/H8/H9 çekirdeklerinden en az 2 aktif
    long_core=tab[tab["Sinyal"].str.contains(r"\bH7\b|\bH8\b|\bH9\b",regex=True)]
    long_gate=(tab["Sinyal"].str.contains(r"\bH7\b",regex=True).any() or len(long_core)>=2)

    # MID: en az iki exact motor aktif
    mid_types=set()
    for sig in tab[tab.Kaynak=="MID"].Sinyal:
        for x in ("H4","H5","H6"):
            if x in sig: mid_types.add(x)
    mid_gate=len(mid_types)>=2

    # H1 modu
    h1_pair=tab["Sinyal"].str.contains("H1_PAIR2C_ANCHOR").any()
    h1_abs=tab["Sinyal"].str.contains("H1_ABSENT_LONG35").any()
    h1_mode="PAIR2C" if h1_pair else ("ABSENT_LONG35" if h1_abs else "ABSTAIN")

    # Hakem koltukları — V1 mantığı
    seats={"H1":0,"SHORT":0,"MID":0,"LONG":0,"DEEP":0}
    if h1_mode=="PAIR2C": seats["H1"]=3
    elif h1_mode=="ABSENT_LONG35": seats["H1"]=2

    if mid_gate:
        seats["MID"]=3 if len(mid_types)>=3 else 2

    deep_exists=tab["Sinyal"].str.contains("DEEP_STRICT").any()
    if deep_exists:
        seats["DEEP"]=1
    elif long_gate:
        seats["LONG"]=1

    # Kalan 10 koltuk SHORT; ama filler yok: yalnız sinyalli aday.
    seats["SHORT"]=max(0,10-sum(seats.values()))

    # Rejim, adayların sıralamasını etkiler; kaynak kotasını kör sabitlemez.
    regime_bonus={"HIGH":1.0,"MID":0.25,"LOW":-0.75}
    tab["Rejim"]=tab.Kaynak.map(lambda x: reg.get(x,"MID"))
    tab["Final_skor"]=tab.apply(
        lambda r: r.Ham_skor + regime_bonus.get(r.Rejim,0) +
                  (0.8 if r.Sinyal!="ABSTAIN" else -3.0),axis=1
    )

    selected=[]
    source_selected={}
    for src in ["H1","MID","DEEP","LONG","SHORT"]:
        k=seats[src]
        if k<=0: continue
        z=tab[(tab.Kaynak==src)&(tab.Sinyal!="ABSTAIN")].sort_values(
            ["Final_skor","Aile_skor","delta12"],ascending=False
        )
        picks=z.head(k).Sayı.astype(int).tolist()
        source_selected[src]=picks
        selected.extend(picks)

    # Aynı sayıyı tekleştir, filler YOK.
    selected=list(dict.fromkeys(selected))[:10]

    # 5'li: hakemin seçtiği güçlü havuz içinden aile uyumu + kaynak çeşitliliği.
    pool=tab[tab.Sayı.isin(selected)].copy()
    pool=pool.sort_values(["Final_skor","Aile_skor"],ascending=False)
    final5=[]
    # Önce en güçlü aile bağını koru.
    fams=build_families(t,selected)
    if fams:
        for n in fams[0]["uyeler"]:
            if n in selected and n not in final5 and len(final5)<3:
                final5.append(n)
    # Sonra kaynak hakemi skoruna göre tamamla.
    for n in pool.Sayı.astype(int):
        if n not in final5:
            final5.append(n)
        if len(final5)>=5:
            break

    diagnostics={
        "supply":supply,"regime":reg,"active":active,
        "h1_mode":h1_mode,"mid_types":sorted(mid_types),
        "mid_gate":mid_gate,"long_core":len(long_core),
        "long_gate":long_gate,"deep_exists":bool(deep_exists),
        "seats":seats,"source_selected":source_selected,
        "families":fams
    }
    return tab,selected,final5,diagnostics

# ============================================================
# SON 10 EL SICAK HAFIZA
# ============================================================
def hot_memory_table(t, window=10):
    lo=max(0,t-window)
    recent=sets[lo:t]
    rows=[]
    for n in range(1,81):
        pos=[i for i,x in enumerate(recent) if n in x]
        freq=len(pos)
        last_age=(len(recent)-pos[-1]) if pos else 99
        streak=sum(n in x for x in recent[-3:])
        # sıcak hafıza: frekans + son 3 el canlılığı + yakın zamanda görülme
        score=freq*2.0 + streak*1.25 + (1.5 if last_age<=2 else (0.5 if last_age<=4 else 0))
        rows.append({"Sayı":n,"Son10":freq,"Son3":streak,"Son_görülme_H":last_age,"Sıcak_skor":round(score,2)})
    return pd.DataFrame(rows).sort_values(["Sıcak_skor","Son10","Son3"],ascending=False)

def hot_coupon_pack(t):
    ht=hot_memory_table(t,10)
    ranked=ht.Sayı.astype(int).tolist()

    # Son 10 elde birlikte yaşayan aile bağıyla 4A
    top24=ranked[:24]
    pair_scores=[]
    for a,b in combinations(top24,2):
        co=sum(a in sets[j] and b in sets[j] for j in range(max(0,t-10),t))
        pair_scores.append((co,a,b))
    pair_scores.sort(reverse=True)

    c4a=[]
    for co,a,b in pair_scores:
        if co<2: break
        for n in (a,b):
            if n not in c4a:
                c4a.append(n)
            if len(c4a)>=4: break
        if len(c4a)>=4: break
    for n in ranked:
        if n not in c4a: c4a.append(n)
        if len(c4a)>=4: break

    # 4B: sıcak ama A'dan mümkün olduğunca farklı
    c4b=[]
    for n in ranked:
        if n not in c4a:
            c4b.append(n)
        if len(c4b)>=4: break
    if len(c4b)<4:
        for n in ranked:
            if n not in c4b:
                c4b.append(n)
            if len(c4b)>=4: break

    # 5'li ana: sıcaklık + mevcut ana beynin H/aile skoru birleşimi
    brain=tab[["Sayı","Final_skor","Aile_skor"]].copy()
    z=ht.merge(brain,on="Sayı",how="left").fillna(0)
    # ölçekleri normalize et ki tek bir motor ezmesin
    for c in ["Sıcak_skor","Final_skor","Aile_skor"]:
        mn,mx=z[c].min(),z[c].max()
        z[c+"_N"]=(z[c]-mn)/(mx-mn) if mx>mn else 0.0
    z["Birleşik"]=0.55*z["Sıcak_skor_N"]+0.30*z["Final_skor_N"]+0.15*z["Aile_skor_N"]
    c5=z.sort_values(["Birleşik","Son10","Son3"],ascending=False).head(5).Sayı.astype(int).tolist()
    return ht,c4a[:4],c4b[:4],c5,z.sort_values("Birleşik",ascending=False)

# ============================================================
# 2 x 4'LÜ + 1 x 5'Lİ KUPON MOTORU
# ============================================================
def make_coupon_pack(t,tab,final10,final5,diag):
    ranked=tab[tab["Sayı"].isin(final10)].sort_values(
        ["Final_skor","Aile_skor"],ascending=False
    ).Sayı.astype(int).tolist()

    fams=diag.get("families",[])
    c4a=[]
    c4b=[]

    # 4'lü A: en güçlü aileyi mümkün olduğunca bozmadan kur.
    if fams:
        for n in fams[0]["uyeler"]:
            if n in ranked and n not in c4a:
                c4a.append(int(n))
    for n in ranked:
        if n not in c4a:
            c4a.append(n)
        if len(c4a)>=4: break

    # 4'lü B: A'nın kopyası değil; ikinci aile + farklı kaynakları kullan.
    if len(fams)>1:
        for n in fams[1]["uyeler"]:
            if n in ranked and n not in c4b:
                c4b.append(int(n))
    # A dışındaki güçlüleri öne al.
    for n in ranked:
        if n not in c4b and (n not in c4a or len(c4b)>=2):
            c4b.append(n)
        if len(c4b)>=4: break
    for n in ranked:
        if n not in c4b:
            c4b.append(n)
        if len(c4b)>=4: break

    c5=list(map(int,final5[:5]))
    return c4a[:4],c4b[:4],c5

def save_coupon_pack(target_draw,c4a,c4b,c5,diag):
    con=sqlite3.connect(DB)
    # Aynı hedef için tekrar basılırsa eskiyi ezmek yerine yeni dondurulmuş kayıt açar.
    con.execute("""INSERT INTO coupon_sets(
        target_draw,history_last_draw,coupon4_a,coupon4_b,coupon5,diagnostics
    ) VALUES(?,?,?,?,?,?)""",
    (int(target_draw),int(df.iloc[-1].draw),
     ",".join(map(str,c4a)),",".join(map(str,c4b)),",".join(map(str,c5)),
     json.dumps(diag,ensure_ascii=False)))
    con.commit(); con.close()

def check_coupon_packs():
    con=sqlite3.connect(DB)
    q=pd.read_sql_query("SELECT * FROM coupon_sets ORDER BY id DESC",con)
    if q.empty:
        con.close(); return q
    drawmap={int(r.draw):set(r.nums) for r in df.itertuples()}
    for _,r in q.iterrows():
        d=int(r.target_draw)
        if d not in drawmap or int(r.checked)==1:
            continue
        real=drawmap[d]
        a={int(x) for x in str(r.coupon4_a).split(",") if x}
        b={int(x) for x in str(r.coupon4_b).split(",") if x}
        c={int(x) for x in str(r.coupon5).split(",") if x}
        con.execute("""UPDATE coupon_sets
            SET checked=1,hit4_a=?,hit4_b=?,hit5=?,real_numbers=? WHERE id=?""",
            (len(a&real),len(b&real),len(c&real),
             ",".join(map(str,sorted(real))),int(r.id)))
    con.commit()
    q=pd.read_sql_query("SELECT * FROM coupon_sets ORDER BY id DESC",con)
    con.close()
    return q

# ============================================================
# DONDURMA / KONTROL
# ============================================================
def freeze_prediction(target_draw,target_time,final5,final10,diag):
    con=sqlite3.connect(DB)
    con.execute("""INSERT INTO frozen_predictions
        (target_draw,target_time,history_last_draw,final5,final10,source_plan,diagnostics)
        VALUES(?,?,?,?,?,?,?)""",
        (int(target_draw),str(target_time),int(df.iloc[-1].draw),
         ",".join(map(str,final5)),",".join(map(str,final10)),
         json.dumps(diag.get("seats",{}),ensure_ascii=False),
         json.dumps(diag,ensure_ascii=False)))
    con.commit(); con.close()

def check_frozen():
    con=sqlite3.connect(DB)
    pred=pd.read_sql_query("SELECT * FROM frozen_predictions ORDER BY id DESC",con)
    if pred.empty:
        con.close(); return pred
    drawmap={int(r.draw):set(r.nums) for r in df.itertuples()}
    for _,r in pred.iterrows():
        d=int(r.target_draw)
        if d not in drawmap or int(r.checked)==1:
            continue
        real=drawmap[d]
        f5={int(x) for x in str(r.final5).split(",") if x}
        f10={int(x) for x in str(r.final10).split(",") if x}
        con.execute("""UPDATE frozen_predictions SET checked=1,hit5=?,hit10=?,real_numbers=? WHERE id=?""",
                    (len(f5&real),len(f10&real),",".join(map(str,sorted(real))),int(r.id)))
    con.commit()
    pred=pd.read_sql_query("SELECT * FROM frozen_predictions ORDER BY id DESC",con)
    con.close()
    return pred

# ============================================================
# REAL20 ADAY HAVUZU + KAYNAK İZİ
# Geçmiş tecrübe ana katman, son10 canlı doğrulayıcı.
# ============================================================
def real20_pool(t, tab, diag):
    hot=hot_memory_table(t,10)
    z=tab.merge(hot,on="Sayı",how="left").fillna(0)

    def reasons(r):
        sig=[] if r["Sinyal"]=="ABSTAIN" else [x.strip() for x in str(r["Sinyal"]).split("+")]
        a=int(r["H_yaşı"])
        exact=f"H{a}" if a<=15 else "H13+"
        out=[exact]
        out += sig
        if float(r["Aile_skor"])>0: out.append("AİLE")
        if int(r["Son10"])>=3: out.append("SON10_SICAK")
        return list(dict.fromkeys(out))

    # Tecrübe/karakter ana ağırlık; son10 yalnız doğrulayıcı.
    # Kaynak rejimi ve exact motor sinyali önde.
    regime_bonus={"HIGH":2.0,"MID":0.5,"LOW":-1.0}
    z["Tecrübe_skor"]=z.apply(
        lambda r: float(r["Final_skor"])*1.00
                  + regime_bonus.get(str(r["Rejim"]),0)
                  + min(float(r["Aile_skor"]),12.0)*0.18,axis=1)
    # Son10 katkısı sınırlı; geçmiş motoru ezemez.
    z["Canlı_skor"]=z["Sıcak_skor"]*0.22
    z["REAL20_skor"]=z["Tecrübe_skor"]+z["Canlı_skor"]
    z["Nedenler"]=z.apply(reasons,axis=1)
    z["Ana_neden"]=z.apply(
        lambda r: (str(r["Sinyal"]).split("+")[0].strip()
                   if r["Sinyal"]!="ABSTAIN" else
                   (f"H{int(r['H_yaşı'])}" if int(r["H_yaşı"])<=15 else "H13+")),axis=1)

    # Kaynak koltuk hedefleri: geçmiş ortalama karakter + mevcut rejim.
    # 20 koltuk tamamlanır ama önce kaynak karakteri korunur.
    seats={"H1":5,"SHORT":6,"MID":5,"LONG":3,"DEEP":1}
    if diag["regime"]["SHORT"]=="HIGH": seats["SHORT"]+=1; seats["MID"]=max(0,seats["MID"]-1)
    if diag["regime"]["MID"]=="HIGH": seats["MID"]+=1; seats["SHORT"]=max(0,seats["SHORT"]-1)
    if diag["regime"]["LONG"]=="HIGH": seats["LONG"]+=1; seats["H1"]=max(0,seats["H1"]-1)
    if diag["regime"]["DEEP"]=="HIGH": seats["DEEP"]+=1; seats["SHORT"]=max(0,seats["SHORT"]-1)

    chosen=[]
    for src in ["H1","SHORT","MID","LONG","DEEP"]:
        q=z[z["Kaynak"]==src].sort_values(["REAL20_skor","Aile_skor","Son10"],ascending=False)
        for n in q.head(seats[src])["Sayı"].astype(int):
            if n not in chosen: chosen.append(n)

    # Eksik koltuk varsa kalan 80 içinden birleşik karakter skoruyla tamamla.
    if len(chosen)<20:
        q=z[~z["Sayı"].isin(chosen)].sort_values(["REAL20_skor","Aile_skor","Son10"],ascending=False)
        chosen += q.head(20-len(chosen))["Sayı"].astype(int).tolist()
    chosen=chosen[:20]

    pool=z[z["Sayı"].isin(chosen)].copy().sort_values("REAL20_skor",ascending=False)
    return chosen,pool,seats

def traced_coupon_pack(pool):
    # 20'lik havuzdan üç kolon. 4B mümkün olduğunca 4A'dan farklı.
    ranked=pool["Sayı"].astype(int).tolist()
    a=ranked[:4]
    b=[n for n in ranked if n not in a][:4]
    # 5'li: ilk 5 ama kaynak çeşitliliğini koru
    five=[]
    used_src=set()
    for r in pool.itertuples():
        if r.Kaynak not in used_src:
            five.append(int(r.Sayı)); used_src.add(r.Kaynak)
        if len(five)>=5: break
    for n in ranked:
        if n not in five: five.append(n)
        if len(five)>=5: break
    return a,b,five[:5]

# ============================================================
# UI — PRATİK CANLI AKIŞ
# ============================================================
if N<30:
    st.error("Motor için en az 30 geçmiş çekiliş gerekli.")
    st.stop()

t=N
tab,legacy10,legacy5,diag=run_brain(t)
hot10=hot_memory_table(t,10)
real20,real20_df,seat20=real20_pool(t,tab,diag)
coupon4a,coupon4b,coupon5=traced_coupon_pack(real20_df)

st.markdown("## ⚡ CANLI KULLANIM")
st.caption(f"Son kayıt: #{int(df.iloc[-1].draw)} · {df.iloc[-1].dt.strftime('%d.%m.%Y %H:%M')} · Toplam {N} çekiliş")

st.markdown(f"## 🎯 Sıradaki çekiliş #{int(df.iloc[-1].draw)+1}")

st.markdown("### 🧠 REAL20 aday havuzu")
st.markdown("## "+" · ".join(map(str,real20)))
st.caption("Geçmiş tecrübe/karakter ana karar verici; son 10 el sıcak hafıza canlı doğrulayıcıdır.")

# Her aday nereden geldi?
trace=real20_df[["Sayı","Ana_neden","Nedenler","Kaynak","H_yaşı","Son10","REAL20_skor"]].copy()
trace["Nereden geldi"]=trace["Nedenler"].apply(lambda x:" + ".join(x))
trace=trace[["Sayı","Ana_neden","Nereden geldi","Kaynak","H_yaşı","Son10","REAL20_skor"]]
st.dataframe(trace,use_container_width=True,hide_index=True)

st.markdown("### 🎟️ Kuponlar")
a,b,c=st.columns(3)
with a:
    st.info("4'LÜ A")
    st.markdown("## "+" — ".join(map(str,coupon4a)))
with b:
    st.warning("4'LÜ B")
    st.markdown("## "+" — ".join(map(str,coupon4b)))
with c:
    st.success("5'Lİ ANA")
    st.markdown("## "+" — ".join(map(str,coupon5)))

# Kupon sayı kaynaklarını kısa göster.
reason_map={int(r["Sayı"]):str(r["Ana_neden"]) for _,r in real20_df.iterrows()}
st.caption("4A: "+" | ".join(f"{n}({reason_map.get(n,'?')})" for n in coupon4a))
st.caption("4B: "+" | ".join(f"{n}({reason_map.get(n,'?')})" for n in coupon4b))
st.caption("5'li: "+" | ".join(f"{n}({reason_map.get(n,'?')})" for n in coupon5))

target=int(df.iloc[-1].draw)+1
if st.button(f"🔒 #{target} KUPONLARINI DONDUR",type="primary",use_container_width=True):
    save_coupon_pack(target,coupon4a,coupon4b,coupon5,diag)
    st.success(f"#{target} için 4A + 4B + 5'li kalıcı donduruldu.")

packs=check_coupon_packs()
if not packs.empty:
    st.markdown("### 📊 Kolon değerlendirmesi")
    q=packs.copy()
    q["4A"]=q.apply(lambda r:"-" if not r.checked else f"{int(r.hit4_a)}/4",axis=1)
    q["4B"]=q.apply(lambda r:"-" if not r.checked else f"{int(r.hit4_b)}/4",axis=1)
    q["5L"]=q.apply(lambda r:"-" if not r.checked else f"{int(r.hit5)}/5",axis=1)
    st.dataframe(q[["target_draw","coupon4_a","4A","coupon4_b","4B","coupon5","5L"]],
                 use_container_width=True,hide_index=True)

st.markdown("### 🔥 Son 10 el sıcak hafıza")
hot20=hot10.head(20)
st.markdown("**Sıcak 20:** "+" · ".join(map(str,hot20["Sayı"].astype(int).tolist())))
with st.expander("Son 10 çekiliş + sıcaklık detayını aç"):
    last10=df.tail(10)[["draw","dt","nums"]].copy()
    last10["dt"]=last10["dt"].dt.strftime("%d.%m.%Y %H:%M")
    last10["nums"]=last10["nums"].apply(lambda x:" - ".join(map(str,x)))
    st.dataframe(last10,use_container_width=True,hide_index=True)
    st.dataframe(hot10.head(30),use_container_width=True,hide_index=True)

with st.expander("🔬 Teknik motor detayları"):
    st.write("20 koltuk kaynak bütçesi:",seat20)
    st.write("PRE-H kaynak arzı:",diag["supply"])
    st.write("Karakter/rejim:",diag["regime"])
    st.write("H1 modu:",diag["h1_mode"])
    st.write("MID:",diag["mid_types"],"LONG gate:",diag["long_gate"],"DEEP:",diag["deep_exists"])
    st.dataframe(tab.sort_values("Final_skor",ascending=False),use_container_width=True,hide_index=True)

st.caption("Tarihsel örüntü araştırmasıdır; rastgele çekilişlerde kesin kazanç garantisi vermez.")
