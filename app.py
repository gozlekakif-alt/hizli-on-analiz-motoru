
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
    c = con()
    c.execute("""CREATE TABLE IF NOT EXISTS draws(
        draw_id INTEGER PRIMARY KEY, draw_time TEXT NOT NULL, numbers TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS coupons(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_draw_id INTEGER NOT NULL,
        created_after_draw_id INTEGER NOT NULL,
        coupon_size INTEGER NOT NULL,
        coupon_no INTEGER NOT NULL,
        numbers TEXT NOT NULL,
        architecture TEXT NOT NULL,
        checked INTEGER DEFAULT 0,
        hit_count INTEGER DEFAULT 0,
        matched_numbers TEXT DEFAULT '',
        UNIQUE(target_draw_id,coupon_size,coupon_no)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pools(
        target_draw_id INTEGER PRIMARY KEY,
        created_after_draw_id INTEGER NOT NULL,
        pool20 TEXT NOT NULL,
        detail_csv TEXT NOT NULL
    )""")
    c.commit(); c.close()

def nums(s):
    return list(dict.fromkeys(int(x) for x in re.findall(r"\d+", str(s))))

def valid(ns):
    return len(ns)==20 and len(set(ns))==20 and all(1<=x<=80 for x in ns)

def parse_line(line):
    p=line.strip().replace("\ufeff","").split(";",2)
    if len(p)!=3: return None
    try:
        did=int(p[0].strip()); dt=p[1].strip(); ns=nums(p[2])
        if not valid(ns): return None
        return did,dt,ns
    except: return None

def add_draw(did, dt, ns):
    if not valid(ns): return False, "Tam 20 farklı sayı ve 1–80 aralığı gerekli."
    c=con()
    try:
        c.execute("INSERT INTO draws VALUES(?,?,?)",(int(did),str(dt),",".join(map(str,ns))))
        c.commit(); return True, "Eklendi"
    except sqlite3.IntegrityError:
        return False, "Bu çekiliş zaten kayıtlı."
    finally: c.close()

def bulk_import(text):
    ins=skip=0; bad=[]
    c=con()
    for no,line in enumerate(text.splitlines(),1):
        if not line.strip(): continue
        r=parse_line(line)
        if not r:
            skip+=1; bad.append(no); continue
        did,dt,ns=r
        cur=c.execute("INSERT OR IGNORE INTO draws VALUES(?,?,?)",(did,dt,",".join(map(str,ns))))
        if cur.rowcount: ins+=1
        else: skip+=1
    c.commit(); c.close()
    return ins,skip,bad

def seed():
    c=con(); n=c.execute("SELECT COUNT(*) FROM draws").fetchone()[0]; c.close()
    if n==0 and SEED_FILE.exists():
        return bulk_import(SEED_FILE.read_text(encoding="utf-8-sig"))
    return (0,0,[])

def load():
    c=con(); df=pd.read_sql_query("SELECT * FROM draws ORDER BY draw_id",c); c.close()
    if df.empty: return df
    df["Sayilar"]=df["numbers"].map(nums)
    df["dt"]=pd.to_datetime(df["draw_time"],dayfirst=True,errors="coerce")
    df=df.sort_values(["dt","draw_id"]).reset_index(drop=True)
    df["date"]=df["dt"].dt.date
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

def build_pool(df):
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
    # source-diverse 20: rank by evidence, while preserving source representation naturally
    d=d.sort_values(["Skor","H1_Takim"],ascending=False).reset_index(drop=True)
    pool=d.head(20).copy()
    pool["Havuz_Sirasi"]=range(1,21)
    return pool,d,sup,regimes

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

init_db()
seed()
check_and_roll()
df=load()

tab1,tab2,tab3,tab4,tab5=st.tabs(["🎯 Canlı Motor","➕ Tek Çekiliş","📥 Toplu Ekle","📊 Başarı Karnesi","🧬 20'lik Havuz Anatomisi"])

with tab1:
    if df.empty:
        st.warning("Veri yok.")
    else:
        last=df.iloc[-1]
        st.metric("Toplam çekiliş",len(df))
        st.write(f"Son çekiliş: **#{int(last.draw_id)} — {last.draw_time}**")
        target=int(last.draw_id)+1
        save_prediction(df)
        c=con()
        q=pd.read_sql_query("SELECT coupon_size,coupon_no,numbers,checked,hit_count,matched_numbers FROM coupons WHERE target_draw_id=? ORDER BY coupon_size,coupon_no",c,params=(target,))
        c.close()
        st.subheader(f"Hedef çekiliş #{target}")
        for size in (4,5):
            z=q[q.coupon_size==size]
            cols=st.columns(3)
            for j,(_,r) in enumerate(z.iterrows()):
                cols[j%3].info(f"{size}'lü {int(r.coupon_no)}: {r.numbers}")
        pool,_,sup,reg=build_pool(df)
        st.subheader("REAL20 aday havuzu")
        st.write(" • ".join(f"{int(x):02d}" for x in pool.Sayi))
        st.caption("Genel sıcaklık/frekans ana seçim puanı olarak kullanılmaz.")
        st.write("Kaynak arzı:",sup," | Rejim:",", ".join(reg) if reg else "NEUTRAL")

with tab2:
    st.subheader("Tek çekiliş ekle → eski kuponları kontrol et → yeni kuponları üret")
    did=st.number_input("Çekiliş no",min_value=1,step=1,value=int(df.iloc[-1].draw_id+1) if not df.empty else 1)
    dt=st.text_input("Tarih-saat","15.09.2026 10:02")
    tx=st.text_area("20 sayı","")
    if st.button("Çekilişi ekle ve motoru ilerlet",type="primary"):
        ns=nums(tx); ok,msg=add_draw(did,dt,ns)
        if ok:
            checked=check_and_roll()
            st.success("Çekiliş eklendi. Önceki hedef kuponları kontrol edildi ve sıradaki hedef üretildi.")
            if checked:
                st.dataframe(pd.DataFrame(checked,columns=["Hedef","Boyut","Kupon","İsabet","Tutanlar"]),use_container_width=True)
            st.rerun()
        else: st.error(msg)

with tab3:
    st.subheader("Toplu çekiliş ekle")
    raw=st.text_area("Format: çekiliş_no;tarih saat;20 sayı",height=260)
    up=st.file_uploader("Veya TXT/CSV yükle",type=["txt","csv"])
    if st.button("Toplu ekle ve tüm bekleyen kuponları kontrol et"):
        text=up.getvalue().decode("utf-8-sig") if up else raw
        ins,sk,bad=bulk_import(text)
        checked=check_and_roll()
        st.success(f"{ins} çekiliş eklendi, {sk} satır atlandı. {len(checked)} kupon sonucu kontrol edildi.")
        if bad: st.warning(f"Biçimi bozuk satırlar: {bad[:20]}")
        st.rerun()

with tab4:
    c=con()
    hist=pd.read_sql_query("""SELECT target_draw_id,coupon_size,coupon_no,numbers,hit_count,matched_numbers
                              FROM coupons WHERE checked=1 ORDER BY target_draw_id DESC,coupon_size,coupon_no""",c)
    c.close()
    if hist.empty: st.info("Henüz sonuçlanmış kupon yok.")
    else:
        hist["Sonuc"]=hist.apply(lambda r:f"{int(r.hit_count)}/{int(r.coupon_size)}",axis=1)
        a,b,c1,d=st.columns(4)
        a.metric("Kontrol edilen kolon",len(hist))
        b.metric("4/4",int(((hist.coupon_size==4)&(hist.hit_count==4)).sum()))
        c1.metric("5/5",int(((hist.coupon_size==5)&(hist.hit_count==5)).sum()))
        d.metric("Maksimum isabet",f"{int(hist.hit_count.max())}/{int(hist.loc[hist.hit_count.idxmax(),'coupon_size'])}")
        st.dataframe(hist,use_container_width=True,hide_index=True)

with tab5:
    if not df.empty:
        pool,all80,sup,reg=build_pool(df)
        st.subheader("20 sayının tamamı ve nereden geldiği")
        st.dataframe(pool[["Havuz_Sirasi","Sayi","H_Yasi","Kaynak","Ritim","H1_Takim","NEG_Oyu","Protect","Skor","Neden"]],
                     use_container_width=True,hide_index=True)
        st.subheader("1–80 aday inceleme")
        st.dataframe(all80,use_container_width=True,hide_index=True)
        st.caption("Skor açıklanabilir PRE-H kanıtlardan oluşur. Genel 14 günlük sıcak sayı frekansı seçim puanına eklenmez.")
