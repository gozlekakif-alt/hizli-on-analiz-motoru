
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
        draw_id INTEGER PRIMARY KEY,
        draw_time TEXT NOT NULL,
        numbers TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS app_coupons_v2(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_draw_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        numbers TEXT NOT NULL,
        checked INTEGER NOT NULL DEFAULT 0,
        hits INTEGER NOT NULL DEFAULT 0,
        matched_numbers TEXT NOT NULL DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS pools(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_draw_id INTEGER,
        numbers TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_app_coupon_v2
                 ON app_coupons_v2(target_draw_id,kind,numbers)""")
    c.commit()
    c.close()
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
        c.execute("DELETE FROM draws"); c.execute("DELETE FROM app_coupons_v2"); c.execute("DELETE FROM pools")
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
    if df.empty: return pd.DataFrame(columns=["draw_id","draw_time","numbers","Sayilar","date"])
    df["Sayilar"]=df["numbers"].map(lambda x:[int(v.strip()) for v in str(x).split(",") if v.strip()])
    df["draw_time"]=pd.to_datetime(df["draw_time"],dayfirst=True,errors="coerce")
    df=df.dropna(subset=["draw_time"]).sort_values(["draw_time","draw_id"]).reset_index(drop=True)
    df["date"]=df["draw_time"].dt.date
    return df

def parse_user_blocks(text):
    text=str(text or "").replace("\r","")
    starts=list(re.finditer(r"(?im)^\s*Çekiliş\s*no\s*:\s*(\d+)\s*$",text))
    if not starts: return [],["'Çekiliş no:' satırı bulunamadı."]
    out=[]; errors=[]
    for i,m in enumerate(starts):
        block=text[m.start():starts[i+1].start() if i+1<len(starts) else len(text)]
        did=int(m.group(1)); lines=[x.strip() for x in block.splitlines() if x.strip()]
        dt=None; vals=[]; after=False
        for line in lines[1:]:
            mm=re.match(r"^(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})$",line)
            if mm: dt=f"{mm.group(1)} {mm.group(2)}"; after=True; continue
            if after and re.fullmatch(r"\d{1,2}",line): vals.append(int(line))
        if dt is None: errors.append(f"#{did}: tarih/saat okunamadı")
        elif len(vals)!=20 or len(set(vals))!=20 or any(n<1 or n>80 for n in vals):
            errors.append(f"#{did}: 20 benzersiz 1–80 sayı gerekli; okunan={len(vals)}")
        else: out.append((did,dt,vals))
    return out,errors

def import_user_blocks(text):
    rows,errors=parse_user_blocks(text)
    if errors: return 0,0,errors
    c=con(); ins=dup=0
    for did,dt,vals in rows:
        if c.execute("SELECT 1 FROM draws WHERE draw_id=?",(did,)).fetchone(): dup+=1
        else:
            c.execute("INSERT INTO draws(draw_id,draw_time,numbers) VALUES(?,?,?)",(did,dt,",".join(map(str,vals)))); ins+=1
    c.commit(); c.close()
    return ins,dup,[]

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
    # deterministic greedy: maximize score + source diversity + pair separation across app_coupons_v2
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

def check_and_roll():
    c=con()
    rows=c.execute("""SELECT c.id,c.target_draw_id,c.numbers,d.numbers FROM app_coupons_v2 c JOIN draws d ON d.draw_id=c.target_draw_id WHERE COALESCE(c.checked,0)=0""").fetchall()
    checked=[]
    for cid,target,cp,real in rows:
        a={int(x) for x in str(cp).split(",") if x.strip()}
        b={int(x) for x in str(real).split(",") if x.strip()}
        hit=sorted(a&b)
        c.execute("UPDATE app_coupons_v2 SET checked=1,hits=?,matched_numbers=? WHERE id=?",(len(hit),",".join(map(str,hit)),cid))
        checked.append((target,len(hit),hit))
    c.commit(); c.close()
    return checked

init_db()
memory_ok,memory_n,memory_msg=seed()
df=load()
if memory_ok:
    check_and_roll()
    df=load()


# =========================
# TEK EKRAN CANLI KULLANIM
# =========================
st.title("🎯 Hızlı On — Canlı Tek Ekran")
if memory_ok:
    st.success(memory_msg)
else:
    st.error("⛔ "+memory_msg)
    st.stop()

df=load()
check_and_roll()
df=load()

st.subheader("➕ Yeni çekilişi ekle")
st.caption("Tek çekilişi aşağıdaki doğal biçimde yapıştır. Ekleyince önceki 6 kolon otomatik kontrol edilir ve yeni hedef için 6 kolon yenilenir.")
example="""Çekiliş no: 54251
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
77"""
tx=st.text_area("Çekiliş",height=230,placeholder=example,label_visibility="collapsed")
if st.button("EKLE → KONTROL ET → YENİ KUPONLARI ÜRET",type="primary",use_container_width=True):
    ins,dup,errs=import_user_blocks(tx)
    if errs:
        st.error(" | ".join(errs[:5]))
    elif ins or dup:
        check_and_roll()
        st.success(f"{ins} yeni çekiliş eklendi. Önceki kolonlar kontrol edildi.")
        st.rerun()

df=load()
if df.empty:
    st.warning("Veri yok.")
    st.stop()

last=int(df.iloc[-1]["draw_id"])
target=last+1
pool,all80,sup,reg=build_pool(df)
ana4=make_coupons(pool,4,3)
km=kullanici_numara_ureticisi(df)
user4=km["Kolonlar"][:3]

# Save current six 4-number app_coupons_v2 for exact target, without duplicates.
c=con()
for i,cp in enumerate(ana4,1):
    c.execute("""INSERT INTO app_coupons_v2(target_draw_id,kind,numbers,checked,hits)
                 SELECT ?,?,?,0,0 WHERE NOT EXISTS(
                 SELECT 1 FROM app_coupons_v2 WHERE target_draw_id=? AND kind=? AND numbers=?)""",
              (target,f"ANA-{i}",",".join(map(str,cp)),target,f"ANA-{i}",",".join(map(str,cp))))
for i,cp in enumerate(user4,1):
    c.execute("""INSERT INTO app_coupons_v2(target_draw_id,kind,numbers,checked,hits)
                 SELECT ?,?,?,0,0 WHERE NOT EXISTS(
                 SELECT 1 FROM app_coupons_v2 WHERE target_draw_id=? AND kind=? AND numbers=?)""",
              (target,f"KOD-{i}",",".join(map(str,cp)),target,f"KOD-{i}",",".join(map(str,cp))))
c.commit(); c.close()

st.divider()
st.subheader(f"🎟️ Hedef çekiliş #{target}")
a,b=st.columns(2)
with a:
    st.markdown("### 🧠 ANA BEYİN — 3 KUPON")
    for i,cp in enumerate(ana4,1):
        st.success(f"ANA-{i}  |  "+" • ".join(f"{n:02d}" for n in cp))
with b:
    st.markdown("### ⚙️ GÖNDERDİĞİN KOD — 3 KUPON")
    if user4:
        for i,cp in enumerate(user4,1):
            st.info(f"KOD-{i}  |  "+" • ".join(f"{n:02d}" for n in cp))
    else:
        st.warning("Bu elde kod motorunda yeterli H1 takım sinyali yok.")
    st.caption(f"Rejim: {km['Rejim']}")

st.divider()
st.subheader("✅ Son kontrol edilen kolonlar — kaçta kaç?")
c=con()
res=pd.read_sql_query("""SELECT target_draw_id AS Hedef, kind AS Kolon, numbers AS Sayilar,
                                hits AS Isabet
                         FROM app_coupons_v2 WHERE checked=1
                         ORDER BY target_draw_id DESC, kind LIMIT 18""",c)
c.close()
if res.empty:
    st.caption("Henüz sonuçlanmış kolon yok.")
else:
    res["Sonuc"]=res["Isabet"].astype(str)+"/4"
    st.dataframe(res[["Hedef","Kolon","Sayilar","Sonuc"]],use_container_width=True,hide_index=True)

st.divider()
with st.expander("🧬 20'lik aday havuzu ve nereden geliyor?"):
    st.write(" • ".join(f"{int(n):02d}" for n in pool["Sayi"].tolist()))
    show=[x for x in ["Sayi","H_Yasi","Kaynak","Ritim","H1_Takim","V33_Destek","V33_Takim","NEG_Oyu","Protect","Skor","Neden"] if x in pool.columns]
    st.dataframe(pool[show],use_container_width=True,hide_index=True)
    st.caption("Ana beyin ve gönderdiğin kod ayrı üreticidir; kod motoru ana beynin sayı seçimini engellemez.")
