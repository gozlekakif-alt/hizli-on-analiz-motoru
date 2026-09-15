
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3, re, math
from itertools import combinations
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="Hızlı On – Tam İsabet Araştırma Motoru", layout="wide")
st.title("🎯 Hızlı On – Tam İsabet Araştırma Motoru")
st.caption("PRE-H yaşam geometrisi + R1–R4 ritim + H1 takım + kaynak bütçesi + birlikte yaşam + veto/protect + otomatik kupon takibi")

BASE = Path(__file__).resolve().parent
DB_FILE = BASE / "hizli_on_tam_isabet.db"
SEED_FILE = BASE / "14_GUN_3038_CEKILIS.txt"
N = 80

def con():
    return sqlite3.connect(DB_FILE)

def init_db():
    c=con()
    c.execute("""CREATE TABLE IF NOT EXISTS draws(
        draw_id INTEGER PRIMARY KEY, draw_time TEXT NOT NULL, numbers TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS coupons(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_draw_id INTEGER, engine TEXT, coupon_no INTEGER,
        numbers TEXT, reasons TEXT, checked INTEGER DEFAULT 0,
        hits INTEGER DEFAULT 0, hit_numbers TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS reason_ledger(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_draw_id INTEGER, engine TEXT, coupon_no INTEGER,
        number INTEGER, reasons TEXT, is_real INTEGER DEFAULT 0)""")

    # Safe additive migration from any older coupons table.
    cols={r[1] for r in c.execute("PRAGMA table_info(coupons)").fetchall()}
    additions={
        "engine":"TEXT","coupon_no":"INTEGER","reasons":"TEXT",
        "checked":"INTEGER DEFAULT 0","hits":"INTEGER DEFAULT 0",
        "hit_numbers":"TEXT DEFAULT ''"
    }
    for col,typ in additions.items():
        if col not in cols:
            c.execute(f"ALTER TABLE coupons ADD COLUMN {col} {typ}")
    cols={r[1] for r in c.execute("PRAGMA table_info(coupons)").fetchall()}
    if "kind" in cols:
        c.execute("UPDATE coupons SET engine=COALESCE(engine,kind) WHERE engine IS NULL")
    elif "coupon_type" in cols:
        c.execute("UPDATE coupons SET engine=COALESCE(engine,coupon_type) WHERE engine IS NULL")
    if "hit_count" in cols:
        c.execute("UPDATE coupons SET hits=hit_count WHERE COALESCE(hits,0)=0")
    c.commit(); c.close()

def seed(force=False):
    if not SEED_FILE.exists():
        return False,0,"14_GUN_3038_CEKILIS.txt bulunamadı"
    rows=[]; bad=[]
    for no,line in enumerate(SEED_FILE.read_text(encoding="utf-8-sig").splitlines(),1):
        if not line.strip(): continue
        try:
            parts=[x.strip() for x in line.split(";")]
            did=int(parts[0]); dt=parts[1]
            ns=[int(x.strip()) for x in parts[2].split(",") if x.strip()]
            if len(parts)!=3 or len(ns)!=20 or len(set(ns))!=20 or any(n<1 or n>80 for n in ns): raise ValueError()
            rows.append((did,dt,ns))
        except Exception: bad.append(no)
    if len(rows)!=3038: return False,len(rows),f"Ana dosya 3038 olmalı; okunan={len(rows)} bozuk={bad[:10]}"
    dates=pd.to_datetime([r[1] for r in rows],dayfirst=True,errors="coerce")
    counts=pd.Series([d.date() for d in dates if not pd.isna(d)]).value_counts()
    if dates.isna().any() or len(counts)!=14 or not (counts==217).all():
        return False,len(rows),"14 gün × 217 veri kilidi doğrulanamadı"
    c=con()
    if force:
        c.execute("DELETE FROM draws"); c.execute("DELETE FROM coupons"); c.execute("DELETE FROM pools")
    for did,dt,ns in rows:
        c.execute("INSERT OR IGNORE INTO draws(draw_id,draw_time,numbers) VALUES(?,?,?)",(did,dt,",".join(map(str,ns))))
    c.commit()
    present=sum(1 for did,_,_ in rows if c.execute("SELECT 1 FROM draws WHERE draw_id=?",(did,)).fetchone())
    c.close()
    if present!=3038: return False,present,f"Ana hafıza eksik: {present}/3038"
    return True,3038,"ANA HAFIZA: 3038/3038 ✓ | 14 gün × 217 ✓"

def load():
    c=con()
    df=pd.read_sql_query("SELECT draw_id,draw_time,numbers FROM draws ORDER BY draw_id",c)
    c.close()
    if df.empty:
        return pd.DataFrame(columns=["draw_id","draw_time","numbers","Sayilar"])
    def _numbers_to_list(x):
        if isinstance(x,list):
            return [int(v) for v in x]
        return [int(v.strip()) for v in str(x).split(",") if v.strip()]
    df["Sayilar"]=df["numbers"].map(_numbers_to_list)
    df["draw_time"]=pd.to_datetime(df["draw_time"],dayfirst=True,errors="coerce")
    df=df.dropna(subset=["draw_time"]).sort_values(["draw_time","draw_id"]).reset_index(drop=True)
    return df

def same_day_history(df):
    """Prediction state: only target day's prior draws for H-age, preserving same-day PRE-H."""
    if df.empty: return df
    d=df.iloc[-1]["date"]
    return df[df["date"]==d].reset_index(drop=True)

def age_map(daydf):
    if daydf.empty: return {n:None for n in range(1,N+1)}
    last_idx=len(daydf)-1
    out={}
    for n in range(1,N+1):
        found=None
        for j in range(last_idx,-1,-1):
            if n in daydf.iloc[j]["Sayilar"]:
                found=last_idx-j+1  # next target: last draw is H1
                break
        out[n]=found
    return out

def hbit(daydf,n,k):
    if len(daydf)<k: return 0
    return int(n in daydf.iloc[-k]["Sayilar"])

def gaps(daydf,n,need=3):
    idx=[i for i,row in daydf.iterrows() if n in row["Sayilar"]]
    if len(idx)<need+1: return []
    ds=[idx[i]-idx[i-1] for i in range(1,len(idx))]
    return ds[-need:]

def rhythm_flags(daydf,n,age):
    H=lambda k:hbit(daydf,n,k)
    r1 = H(12)==1 and H(8)==1 and H(4)==1 and all(H(k)==0 for k in [11,10,9,7,6,5,3,2,1])
    r2 = H(6)==1 and H(4)==1 and H(2)==1 and all(H(k)==0 for k in [12,11,10,9,8,7,5,3,1])
    g=gaps(daydf,n,3)
    r3 = (g==[1,4,1] and age==4)
    r4 = (g==[1,2,1] and age in (7,8,9))
    return [x for x,b in [("R1",r1),("R2_NEW",r2),("R3_1414",r3),("R4_121_SLEEP_7_9",r4)] if b]

def source(age):
    if age==1:return "H1_CARRY"
    if age in (2,3):return "SHORT"
    if age in (4,5,6):return "MID"
    if age is not None and 7<=age<=12:return "LONG"
    if age is not None and age>=13:return "DEEP"
    return "YENI"

def source_supply(am):
    keys=["H1_CARRY","SHORT","MID","LONG","DEEP","YENI"]
    return {k:sum(source(a)==k for a in am.values()) for k in keys}

def source_regime(sup):
    tags=[]
    if sup["SHORT"]>=28: tags.append("SHORT_HIGH")
    if sup["SHORT"]<=25: tags.append("SHORT_LOW")
    if sup["MID"]>=21: tags.append("MID_HIGH")
    if sup["MID"]<=18: tags.append("MID_LOW")
    if sup["LONG"]>=13: tags.append("LONG_HIGH")
    if sup["LONG"]<=10: tags.append("LONG_LOW")
    if sup["DEEP"]>=3: tags.append("DEEP_HIGH")
    if sup["DEEP"]<=2: tags.append("DEEP_LOW")
    return tags

def pair_stats(df, lookback=100):
    z=df.tail(lookback).reset_index(drop=True)
    carry={}
    co={}
    for i in range(len(z)):
        cur=set(z.iloc[i]["Sayilar"])
        for a,b in combinations(sorted(cur),2):
            co[(a,b)]=co.get((a,b),0)+1
        if i:
            prev=set(z.iloc[i-1]["Sayilar"])
            common=sorted(prev & cur)
            for a,b in combinations(common,2):
                carry[(a,b)]=carry.get((a,b),0)+1
    return carry,co

def negative_votes(daydf,n,age):
    """Conservative transparent veto proxies only; no fabricated V-rule labels."""
    votes=[]; protect=[]
    # Long absence alone is NOT a veto.
    last6=sum(hbit(daydf,n,k) for k in range(1,min(6,len(daydf))+1))
    last12=sum(hbit(daydf,n,k) for k in range(1,min(12,len(daydf))+1))
    if len(daydf)>=12 and last12==0 and age is not None and age>=13:
        votes.append("DERIN_UYKU_ZAYIF_YAKIN_KANIT")
    if last6>=4:
        protect.append("YAKIN_YOGUN_YASAM")
    return votes,protect


def v33_h1_ek_uzman(df):
    """Ek uzman: ana sayı seçimini engellemez, hiçbir sayıyı veto etmez."""
    if df.empty: return {}, []
    last=set(df.iloc[-1]["Sayilar"])
    carry,_=pair_stats(df,100)
    support={}
    for n in last:
        vals=[carry.get(tuple(sorted((n,m))),0) for m in last if m!=n]
        support[n]=sum(sorted(vals,reverse=True)[:4])
    mx=max(support.values()) if support else 0
    bonus={n:(min(0.75,0.75*v/mx) if mx else 0.0) for n,v in support.items()}
    teams=[]
    for tri in combinations(sorted(last),3):
        sc=sum(carry.get(tuple(sorted(x)),0) for x in combinations(tri,2))
        teams.append((sc,tri))
    teams.sort(reverse=True)
    best=list(teams[0][1]) if teams else []
    return bonus,best


def kullanici_numara_ureticisi(df):
    """
    Kullanıcının gönderdiği üretici:
    V33 H1 takım + SHORT/MID rejimi + 3->4->4->4 cooling filtresi.
    ANA MOTOR'dan bağımsız sonuç üretir; ana motorun sayılarını engellemez.
    """
    if len(df)<6:
        return {"Rejim":"YETERSIZ_VERI","Takim":[],"Adaylar":[],"Kolonlar":[]}

    last=set(df.iloc[-1]["Sayilar"])
    z=df.tail(100).reset_index(drop=True)
    team_hist={}
    for i in range(1,len(z)):
        common=sorted(set(z.iloc[i-1]["Sayilar"]) & set(z.iloc[i]["Sayilar"]))
        if len(common)>=3:
            for tri in combinations(common,3):
                team_hist[tri]=team_hist.get(tri,0)+1
    valid_teams={k:v for k,v in team_hist.items() if set(k).issubset(last)}
    team=list(max(valid_teams.items(),key=lambda x:x[1])[0]) if valid_teams else []

    short=(set(df.iloc[-2]["Sayilar"])|set(df.iloc[-3]["Sayilar"]))-last
    mid=(set(df.iloc[-4]["Sayilar"])|set(df.iloc[-5]["Sayilar"])|set(df.iloc[-6]["Sayilar"]))-last-short
    if len(short)>=28 or len(mid)<=18:
        regime="SHORT_HIGH"; candidates=sorted(short)
    elif len(mid)>=21 or len(short)<=25:
        regime="MID_HIGH"; candidates=sorted(mid)
    else:
        regime="NEUTRAL"; candidates=sorted(short|mid)

    def h_history(n,limit=4):
        hits=[i for i,row in df.iterrows() if n in row["Sayilar"]]
        if len(hits)<2:return []
        gaps=[hits[i]-hits[i-1] for i in range(1,len(hits))]
        return list(reversed(gaps[-limit:]))

    approved=[]
    for n in candidates:
        hg=h_history(n,4)
        # Preserve the user's supplied cooling veto exactly as a local specialist rule.
        cooling=(len(hg)>=4 and hg[:3]==[4,4,4] and hg[3]==3)
        if not cooling: approved.append(n)

    # Rank complements by the MAIN app evidence when available, not by hot frequency.
    main_pool,all80,_,_=build_pool_base(df)
    main_score=dict(zip(all80["Sayi"],all80["Skor"]))
    approved=sorted(approved,key=lambda n:(main_score.get(n,0),-n),reverse=True)

    cols=[]
    if len(team)>=3 and approved:
        for n in approved:
            if n not in team:
                cols.append(sorted(team[:3]+[n]))
            if len(cols)==3: break
    return {"Rejim":regime,"Takim":team,"Adaylar":approved,"Kolonlar":cols}

def build_pool_base(df):
    day=same_day_history(df); am=age_map(day); sup=source_supply(am); regimes=source_regime(sup)
    carry,co=pair_stats(df,100)
    last=set(df.iloc[-1]["Sayilar"]) if len(df) else set()
    rows=[]
    for n in range(1,N+1):
        a=am[n]; src=source(a); rhy=rhythm_flags(day,n,a)
        neg,prot=negative_votes(day,n,a)
        team=sum(carry.get(tuple(sorted((n,m))),0) for m in last if m!=n) if n in last else 0
        social=sum(co.get(tuple(sorted((n,m))),0) for m in range(1,N+1) if m!=n)
        score=0.0; why=[]
        # No global hot-frequency score.
        if src=="H1_CARRY": score+=2.0; why.append("H1")
        elif src=="SHORT": score+=1.8; why.append(src)
        elif src=="MID": score+=1.25; why.append(src)
        elif src=="LONG": score+=0.8; why.append(src)
        elif src=="DEEP": score+=0.35; why.append(src)
        for r in rhy:
            score += {"R1":2.0,"R2_NEW":2.2,"R3_1414":2.0,"R4_121_SLEEP_7_9":2.3}[r]
            why.append(r)
        if src=="SHORT" and ("SHORT_HIGH" in regimes or "MID_LOW" in regimes): score+=1.0; why.append("SHORT_REJIM")
        if src=="MID" and ("MID_HIGH" in regimes or "SHORT_LOW" in regimes): score+=0.9; why.append("MID_REJIM")
        if src=="LONG" and "LONG_HIGH" in regimes: score+=0.7; why.append("LONG_REJIM")
        if src=="DEEP" and "DEEP_HIGH" in regimes: score+=0.5; why.append("DEEP_REJIM")
        if n in last and team:
            score += min(2.0, team/25.0); why.append(f"H1_TAKIM:{team}")
        # +6 as supporting evidence, not standalone.
        if hbit(day,n,6):
            score+=0.45; why.append("+6")
        # social is tie-breaker only
        score += min(0.35, social/2000.0)
        if prot: score+=0.45; why += ["PROTECT:"+x for x in prot]
        if len(neg)>=2: score-=2.0
        elif len(neg)==1: score-=0.35
        rows.append(dict(Sayi=n,H_Yasi=a if a is not None else "Yeni",Kaynak=src,
                         Ritim=",".join(rhy) if rhy else "-",H1_Takim=team,
                         NEG_Oyu=len(neg),Protect=len(prot),Skor=round(score,4),
                         Neden=" | ".join(why) if why else "ABSTAIN"))
    d=pd.DataFrame(rows)
    # V33 yalnız EK DESTEK verir; ana motorun adaylarını engellemez/veto etmez.
    v33_bonus,v33_team=v33_h1_ek_uzman(df)
    d["V33_Destek"]=d["Sayi"].map(v33_bonus).fillna(0.0)
    d["V33_Takim"]=d["Sayi"].isin(v33_team)
    d["Skor"]=(d["Skor"]+d["V33_Destek"]).round(4)
    d.loc[d["V33_Destek"]>0,"Neden"]=d.loc[d["V33_Destek"]>0].apply(
        lambda r:(("" if r["Neden"]=="ABSTAIN" else r["Neden"]+" | ")+f"V33_EK:{r['V33_Destek']:.2f}"),axis=1)
    d=d.sort_values(["Skor","H1_Takim"],ascending=False).reset_index(drop=True)
    pool=d.head(20).copy()
    pool["Havuz_Sirasi"]=range(1,21)
    return pool,d,sup,regimes


def build_pool(df):
    """Ana beyin havuzu. Kullanıcı üreticisi bunu değiştirmez."""
    return build_pool_base(df)

def make_coupons(pool,size,count=6):
    p=pool.copy()
    numbers=p["Sayi"].tolist()
    score=dict(zip(p["Sayi"],p["Skor"]))
    src=dict(zip(p["Sayi"],p["Kaynak"]))
    # deterministic greedy: maximize score + source diversity + pair separation across coupons
    used={n:0 for n in numbers}; out=[]
    for cno in range(count):
        chosen=[]
        for _ in range(size):
            cand=[n for n in numbers if n not in chosen]
            def val(n):
                diversity=0.35 if src[n] not in [src[x] for x in chosen] else 0
                rotation=-0.22*used[n]
                return score[n]+diversity+rotation
            pick=max(cand,key=lambda n:(val(n),-n))
            chosen.append(pick); used[pick]+=1
        out.append(sorted(chosen))
    return out

def save_prediction(df):
    if df.empty:return
    last_id=int(df.iloc[-1]["draw_id"]); target=last_id+1
    pool,all80,sup,reg=build_pool(df)
    detail=pool.to_csv(index=False)
    c=con()
    c.execute("""INSERT OR REPLACE INTO pools(target_draw_id,created_after_draw_id,pool20,detail_csv)
                 VALUES(?,?,?,?)""",(target,last_id,",".join(map(str,pool["Sayi"])),detail))
    arch="PRE-H+RITIM+H1_TEAM+SOURCE_BUDGET+PAIR+NEG/PROTECT (GLOBAL HOT FREKANS YOK)"
    for size in (4,5):
        for i,cp in enumerate(make_coupons(pool,size,6),1):
            c.execute("""INSERT OR IGNORE INTO coupons(target_draw_id,created_after_draw_id,coupon_size,coupon_no,numbers,architecture)
                         VALUES(?,?,?,?,?,?)""",(target,last_id,size,i,",".join(map(str,cp)),arch))
    c.commit(); c.close()

def check_and_roll():
    c=con()
    rows=c.execute("""SELECT c.id,c.target_draw_id,c.numbers,c.coupon_size,d.numbers
                      FROM coupons c JOIN draws d ON d.draw_id=c.target_draw_id
                      WHERE c.checked=0""").fetchall()
    checked=[]
    for cid,target,cp,size,real in rows:
        a=set(nums(cp)); b=set(nums(real)); hit=sorted(a&b)
        c.execute("UPDATE coupons SET checked=1,hit_count=?,matched_numbers=? WHERE id=?",
                  (len(hit),",".join(map(str,hit)),cid))
        checked.append((target,size,sorted(a),len(hit),hit))
    c.commit(); c.close()
    df=load()
    if not df.empty: save_prediction(df)
    return checked


def save_six_coupons(target, ana_cols, kod_cols, pool):
    reason_map={int(r["Sayi"]):str(r.get("Neden","")) for _,r in pool.iterrows()}
    c=con()
    for engine,cols in [("ANA",ana_cols),("KOD",kod_cols)]:
        for idx,cp in enumerate(cols,1):
            nums=",".join(map(str,cp))
            reasons=" | ".join(f"{n}:{reason_map.get(n,'KOD_V33/V30/V11-V17' if engine=='KOD' else 'ANA')}" for n in cp)
            exists=c.execute("""SELECT 1 FROM coupons WHERE target_draw_id=? AND engine=? AND coupon_no=?""",
                             (target,engine,idx)).fetchone()
            if not exists:
                c.execute("""INSERT INTO coupons(target_draw_id,engine,coupon_no,numbers,reasons,checked,hits,hit_numbers)
                             VALUES(?,?,?,?,?,0,0,'')""",(target,engine,idx,nums,reasons))
                for n in cp:
                    c.execute("""INSERT INTO reason_ledger(target_draw_id,engine,coupon_no,number,reasons,is_real)
                                 VALUES(?,?,?,?,?,0)""",
                              (target,engine,idx,int(n),reason_map.get(int(n),"KOD_V33/V30/V11-V17" if engine=="KOD" else "ANA")))
    c.commit(); c.close()

def settle_target(draw_id, real_numbers):
    real=set(map(int,real_numbers)); c=con()
    rows=c.execute("""SELECT id,engine,coupon_no,numbers FROM coupons
                      WHERE target_draw_id=? AND COALESCE(checked,0)=0""",(draw_id,)).fetchall()
    for rid,engine,cno,nums in rows:
        cp=[int(x) for x in str(nums).split(",") if x]
        hit=sorted(real & set(cp))
        c.execute("UPDATE coupons SET checked=1,hits=?,hit_numbers=? WHERE id=?",
                  (len(hit),",".join(map(str,hit)),rid))
    c.execute("""UPDATE reason_ledger SET is_real=CASE WHEN number IN (%s) THEN 1 ELSE 0 END
                 WHERE target_draw_id=?""" % ",".join("?"*len(real)),
              tuple(sorted(real))+(draw_id,))
    c.commit(); c.close()

def success_tables():
    c=con()
    detail=pd.read_sql_query("""SELECT target_draw_id AS Hedef,engine AS Motor,coupon_no AS Kolon,
                                numbers AS Sayilar,hits AS Isabet,hit_numbers AS Tutanlar
                                FROM coupons WHERE checked=1
                                ORDER BY target_draw_id DESC,engine,coupon_no""",c)
    summary=pd.read_sql_query("""SELECT engine AS Motor,COUNT(*) AS Kolon,
        SUM(CASE WHEN hits=0 THEN 1 ELSE 0 END) AS "0/4",
        SUM(CASE WHEN hits=1 THEN 1 ELSE 0 END) AS "1/4",
        SUM(CASE WHEN hits=2 THEN 1 ELSE 0 END) AS "2/4",
        SUM(CASE WHEN hits=3 THEN 1 ELSE 0 END) AS "3/4",
        SUM(CASE WHEN hits=4 THEN 1 ELSE 0 END) AS "4/4",
        SUM(hits) AS Toplam_Isabet
        FROM coupons WHERE checked=1 GROUP BY engine""",c)
    veins=pd.read_sql_query("""SELECT reasons AS Damar,COUNT(*) AS Secim,
        SUM(is_real) AS Dogru,
        ROUND(100.0*SUM(is_real)/COUNT(*),2) AS Dogru_Yuzde
        FROM reason_ledger GROUP BY reasons HAVING COUNT(*)>0
        ORDER BY Dogru_Yuzde DESC,Secim DESC""",c)
    c.close()
    return detail,summary,veins

init_db()
memory_ok,memory_n,memory_msg=seed()
if not memory_ok:
    st.error("⛔ "+memory_msg)
    st.stop()

df=load()

st.title("🎯 Hızlı On — Canlı Motor")
st.success(memory_msg)

st.subheader("1) Yeni çekiliş ekle")
st.caption("Çekiliş no + tarih/saat + 20 sayıyı doğal biçimde yapıştır.")
tx=st.text_area("Yeni çekiliş",height=230,placeholder="""Çekiliş no: 54251
08.09.2026 - 00:02
3
7
10
13
18
27
32
34
35
36
41
42
44
47
57
59
65
67
74
77""",label_visibility="collapsed")

if st.button("EKLE → ÖNCEKİ KOLONLARI KONTROL ET → YENİLERİ ÜRET",type="primary",use_container_width=True):
    before=set(load()["draw_id"].tolist())
    ins,dup,errs=import_user_blocks(tx)
    if errs:
        st.error(" | ".join(errs[:5]))
    else:
        now=load()
        added=now[~now["draw_id"].isin(before)]
        for _,r in added.iterrows():
            settle_target(int(r["draw_id"]),r["Sayilar"])
        st.success(f"{ins} yeni çekiliş eklendi; ilgili kolonlar kontrol edildi.")
        st.rerun()

df=load()
if df.empty: st.stop()
last=int(df.iloc[-1]["draw_id"]); target=last+1
pool,all80,sup,reg=build_pool(df)
ana=make_coupons(pool,4,3)
km=kullanici_numara_ureticisi(df)
kod=km["Kolonlar"][:3]
save_six_coupons(target,ana,kod,pool)

st.divider()
st.subheader(f"2) Yeni hedef #{target} — verilen kolonlar")
c1,c2=st.columns(2)
with c1:
    st.markdown("#### 🧠 ANA BEYİN — 3×4")
    for i,cp in enumerate(ana,1):
        st.success(f"ANA-{i}: "+" • ".join(f"{n:02d}" for n in cp))
with c2:
    st.markdown("#### ⚙️ SENİN KODUN — 3×4")
    if kod:
        for i,cp in enumerate(kod,1):
            st.info(f"KOD-{i}: "+" • ".join(f"{n:02d}" for n in cp))
    else:
        st.warning("Bu elde V33 takım sinyali yeterli değil; kod motoru susuyor.")
    st.caption(f"V30 rejimi: {km['Rejim']}")

detail,summary,veins=success_tables()

st.divider()
st.subheader("3) Sonuçlanan kolonlar — kaçta kaç?")
if detail.empty:
    st.caption("Henüz sonuçlanan kolon yok.")
else:
    d=detail.head(18).copy()
    d["Sonuc"]=d["Isabet"].astype(int).astype(str)+"/4"
    st.dataframe(d[["Hedef","Motor","Kolon","Sayilar","Sonuc","Tutanlar"]],
                 use_container_width=True,hide_index=True)

st.divider()
st.subheader("4) Genel başarı tablosu")
if summary.empty: st.caption("Henüz yeterli sonuç yok.")
else: st.dataframe(summary,use_container_width=True,hide_index=True)

st.divider()
st.subheader("5) Doğru sayı hangi damardan geldi?")
if veins.empty:
    st.caption("Henüz damar sonucu birikmedi.")
else:
    st.dataframe(veins.head(40),use_container_width=True,hide_index=True)

with st.expander("🧬 20'lik havuz ve seçim nedenleri"):
    st.write(" • ".join(f"{int(n):02d}" for n in pool["Sayi"]))
    cols=[x for x in ["Sayi","H_Yasi","Kaynak","Ritim","H1_Takim","V33_Destek","V33_Takim","NEG_Oyu","Protect","Skor","Neden"] if x in pool.columns]
    st.dataframe(pool[cols],use_container_width=True,hide_index=True)
