import streamlit as st
import pandas as pd
import numpy as np
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import math, sqlite3, json

st.set_page_config(page_title="Hızlı On — ANA BEYİN V4", page_icon="🧠", layout="wide")
st.title("🧠 Hızlı On — ANA BEYİN V4")
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
# UI
# ============================================================
if N<30:
    st.error("Motor için en az 30 geçmiş çekiliş gerekli.")
    st.stop()

t=N
tab,final10,final5,diag=run_brain(t)

c1,c2,c3,c4,c5=st.columns(5)
c1.metric("H1 arzı",diag["supply"]["H1"])
c2.metric("SHORT H2-H3",diag["supply"]["SHORT"])
c3.metric("MID H4-H6",diag["supply"]["MID"])
c4.metric("LONG H7-H12",diag["supply"]["LONG"])
c5.metric("DEEP H13+",diag["supply"]["DEEP"])

st.markdown("## 🧠 ANA BEYİN KARARI")
r1,r2,r3,r4=st.columns(4)
r1.write(f"**H1 modu:** {diag['h1_mode']}")
r2.write(f"**MID:** {'AKTİF' if diag['mid_gate'] else 'ABSTAIN'} · {', '.join(diag['mid_types']) or '-'}")
r3.write(f"**LONG:** {'AKTİF' if diag['long_gate'] else 'ABSTAIN'} · core={diag['long_core']}")
r4.write(f"**DEEP:** {'AKTİF' if diag['deep_exists'] else 'ABSTAIN'}")

st.write("**Hakemin kendi seçtiği kaynak koltukları:**",diag["seats"])
st.write("**Kaynaklardan gelen adaylar:**",diag["source_selected"])

c4a,c4b,c5=make_coupon_pack(t,tab,final10,final5,diag)

st.markdown("## 🎟️ 2 × 4'LÜ + 1 × 5'Lİ")
qa,qb,qc=st.columns(3)
with qa:
    st.info("4'LÜ A — ANA AİLE")
    st.markdown("## "+" — ".join(map(str,c4a)) if c4a else "ABSTAIN")
with qb:
    st.warning("4'LÜ B — ALTERNATİF AİLE")
    st.markdown("## "+" — ".join(map(str,c4b)) if c4b else "ABSTAIN")
with qc:
    st.success("5'Lİ ANA")
    st.markdown("## "+" — ".join(map(str,c5)) if c5 else "ABSTAIN")

target_pack=int(df.iloc[-1].draw)+1
if st.button(f"🔒 #{target_pack} İÇİN 2×4 + 1×5 KUPONLARI DONDUR",type="primary",disabled=not bool(c5)):
    save_coupon_pack(target_pack,c4a,c4b,c5,diag)
    st.success(f"#{target_pack} kuponları kalıcı kaydedildi. Sonuç eklenince otomatik değerlendirilecek.")

packs=check_coupon_packs()
if not packs.empty:
    st.markdown("### 📊 Kalıcı kolon değerlendirmesi")
    pp=packs.copy()
    pp["4A Sonuç"]=pp.apply(lambda r: "-" if not r.checked else f"{int(r.hit4_a)}/4",axis=1)
    pp["4B Sonuç"]=pp.apply(lambda r: "-" if not r.checked else f"{int(r.hit4_b)}/4",axis=1)
    pp["5'li Sonuç"]=pp.apply(lambda r: "-" if not r.checked else f"{int(r.hit5)}/5",axis=1)
    st.dataframe(pp[["target_draw","history_last_draw","coupon4_a","4A Sonuç",
                     "coupon4_b","4B Sonuç","coupon5","5'li Sonuç","checked"]],
                 use_container_width=True,hide_index=True)

    checked=pp[pp.checked==1].copy()
    if not checked.empty:
        k1,k2,k3,k4=st.columns(4)
        k1.metric("Değerlendirilen hedef",len(checked))
        k2.metric("4A ortalama",f"{checked.hit4_a.mean():.2f}/4")
        k3.metric("4B ortalama",f"{checked.hit4_b.mean():.2f}/4")
        k4.metric("5'li ortalama",f"{checked.hit5.mean():.2f}/5")
        best=max(checked.hit4_a.max()/4,checked.hit4_b.max()/4,checked.hit5.max()/5)
        st.caption("Sonuç geldiğinde kupon değiştirilmez; yalnız dondurulmuş kolon ölçülür.")

st.markdown("### 🎯 ANA 5")
if final5:
    st.markdown("# "+" — ".join(map(str,final5)))
else:
    st.warning("Güçlü sinyal yok: ANA 5 üretmedi.")

st.markdown("### 🔟 Güçlü aday havuzu")
if final10:
    st.markdown("### "+" — ".join(map(str,final10)))
    if len(final10)<10:
        st.caption(f"Filler yok. Motor yalnız {len(final10)} güçlü aday buldu.")
else:
    st.warning("ABSTAIN — güçlü aday yok.")

st.markdown("### 🧬 Bu elde bulunan aile yapıları")
if diag["families"]:
    famdf=pd.DataFrame(diag["families"])
    famdf["uyeler"]=famdf["uyeler"].apply(lambda x:"-".join(map(str,x)))
    st.dataframe(famdf,use_container_width=True,hide_index=True)
else:
    st.info("Aile sinyali yok.")

st.markdown("### 🔬 1–80 PRE-H karar tablosu")
show=tab.sort_values(["Final_skor","Aile_skor"],ascending=False)
st.dataframe(show,use_container_width=True,height=520,hide_index=True)

st.divider()
st.markdown("## 🔒 İleri test — sonucu görmeden dondur")
last_draw=int(df.iloc[-1].draw)
default_target=last_draw+1
x1,x2=st.columns(2)
target_draw=x1.number_input("Hedef çekiliş no",min_value=1,value=default_target,step=1)
target_time=x2.text_input("Hedef saat/tarih (isteğe bağlı)","")
if st.button("🔒 BU KARARI DONDUR",type="primary",disabled=not bool(final5)):
    freeze_prediction(target_draw,target_time,final5,final10,diag)
    st.success(f"#{target_draw} için donduruldu. Sonuç geldikten sonra bu kayıt değişmez.")

pred=check_frozen()
if not pred.empty:
    st.markdown("### 📒 Dondurulmuş test kayıtları")
    cols=["target_draw","target_time","history_last_draw","final5","final10","source_plan","checked","hit5","hit10"]
    st.dataframe(pred[cols],use_container_width=True,hide_index=True)

st.divider()
st.markdown("### Motor sözleşmesi")
st.write(
    "Motor H1/H2/H3/H4-H6/H7-H12/DEEP kaynaklarından sabit kota ile sayı çekmez. "
    "Önce PRE-H yaşam arzını ve uzman tetiklerini okur; H1, MID, LONG ve DEEP kapılarını açıp kapatır; "
    "kalan koltukları SHORT'a verir. Aile motoru sabit üyeyi ezberlemez, her hedefte üyeleri yeniden seçer. "
    "Güçlü aday yoksa filler üretmez. Sonuç yalnız dondurulmuş kaydı ölçmek için kullanılır."
)
st.caption("Bu tarihsel örüntü araştırmasıdır; rastgele çekilişlerde kesin kazanç garantisi vermez.")
