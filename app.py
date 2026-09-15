import streamlit as st
import pandas as pd
import sqlite3, re
from itertools import combinations
from pathlib import Path

st.set_page_config(page_title="Hızlı On Canlı Motor",layout="wide")
BASE=Path(__file__).resolve().parent
DB=BASE/"hizli_on_v2.db"
SEED=BASE/"14_GUN_3038_CEKILIS.txt"

def db():
    return sqlite3.connect(DB)

def init_db():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS draws(
      draw_id INTEGER PRIMARY KEY, draw_time TEXT NOT NULL, numbers TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tickets(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      target_draw_id INTEGER NOT NULL, engine TEXT NOT NULL, ticket_no INTEGER NOT NULL,
      numbers TEXT NOT NULL, checked INTEGER DEFAULT 0, hits INTEGER DEFAULT 0,
      matched TEXT DEFAULT '', UNIQUE(target_draw_id,engine,ticket_no))""")
    c.commit(); c.close()

def parse_seed_line(line):
    p=[x.strip() for x in line.split(";")]
    if len(p)!=3: raise ValueError("seed format")
    did=int(p[0]); dt=p[1]
    ns=[int(x) for x in p[2].split(",") if x.strip()]
    if len(ns)!=20 or len(set(ns))!=20 or any(n<1 or n>80 for n in ns): raise ValueError("20 sayı")
    return did,dt,ns

def seed_data():
    if not SEED.exists(): return False,"14 günlük TXT bulunamadı"
    rows=[]
    try:
        for line in SEED.read_text(encoding="utf-8-sig").splitlines():
            if line.strip(): rows.append(parse_seed_line(line))
    except Exception as e:
        return False,f"TXT okuma hatası: {e}"
    if len(rows)!=3038: return False,f"3038 yerine {len(rows)} çekiliş okundu"
    dates=pd.to_datetime([r[1] for r in rows],dayfirst=True,errors="coerce")
    cnt=pd.Series([d.date() for d in dates if not pd.isna(d)]).value_counts()
    if dates.isna().any() or len(cnt)!=14 or not (cnt==217).all():
        return False,"14 gün × 217 kilidi geçmedi"
    c=db()
    for did,dt,ns in rows:
        c.execute("INSERT OR IGNORE INTO draws VALUES(?,?,?)",(did,dt,",".join(map(str,ns))))
    c.commit()
    present=sum(bool(c.execute("SELECT 1 FROM draws WHERE draw_id=?",(r[0],)).fetchone()) for r in rows)
    c.close()
    return present==3038, f"ANA HAFIZA {present}/3038 | 14 gün × 217"

def nums(s):
    return [int(x) for x in str(s).split(",") if str(x).strip()]

def load_draws():
    c=db()
    d=pd.read_sql_query("SELECT draw_id,draw_time,numbers FROM draws ORDER BY draw_id",c)
    c.close()
    if d.empty:
        return pd.DataFrame(columns=["draw_id","draw_time","numbers","Sayilar","date"])
    d["Sayilar"]=d["numbers"].map(nums)
    d["draw_time"]=pd.to_datetime(d["draw_time"],dayfirst=True,errors="coerce")
    d=d.dropna(subset=["draw_time"]).sort_values(["draw_time","draw_id"]).reset_index(drop=True)
    d["date"]=d["draw_time"].dt.date
    return d

def parse_natural(text):
    blocks=re.split(r"(?=Çekiliş\s*no\s*:)",text.strip(),flags=re.I)
    out=[]; errors=[]
    for b in blocks:
        if not b.strip(): continue
        try:
            mid=re.search(r"Çekiliş\s*no\s*:\s*(\d+)",b,re.I)
            mdt=re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})",b)
            if not mid or not mdt: raise ValueError("No/tarih bulunamadı")
            did=int(mid.group(1)); dt=f"{mdt.group(1)} {mdt.group(2)}"
            tail=b[mdt.end():]
            ns=[int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)",tail)]
            if len(ns)!=20 or len(set(ns))!=20 or any(n<1 or n>80 for n in ns):
                raise ValueError(f"20 benzersiz sayı bekleniyor; {len(ns)} bulundu")
            out.append((did,dt,ns))
        except Exception as e: errors.append(str(e))
    return out,errors

def add_draws(text):
    rows,errs=parse_natural(text)
    if errs or not rows: return 0,errs or ["Çekiliş okunamadı"]
    c=db(); n=0
    for did,dt,ns in rows:
        cur=c.execute("INSERT OR IGNORE INTO draws VALUES(?,?,?)",(did,dt,",".join(map(str,ns))))
        n+=cur.rowcount
    c.commit(); c.close()
    return n,[]

def day_history(d):
    if d.empty:return d
    return d[d["date"]==d.iloc[-1]["date"]].reset_index(drop=True)

def age_map(day):
    out={}
    for n in range(1,81):
        age=None
        for j in range(len(day)-1,-1,-1):
            if n in day.iloc[j]["Sayilar"]:
                age=len(day)-j; break
        out[n]=age
    return out

def hbit(day,n,k):
    return int(len(day)>=k and n in day.iloc[-k]["Sayilar"])

def gaps(day,n):
    ix=[i for i,row in day.iterrows() if n in row["Sayilar"]]
    if len(ix)<4:return []
    return [ix[i]-ix[i-1] for i in range(len(ix)-3,len(ix))]

def rhythm(day,n,age):
    H=lambda k:hbit(day,n,k)
    r=[]
    if len(day)>=12 and H(12) and H(8) and H(4) and all(not H(k) for k in [11,10,9,7,6,5,3,2,1]): r.append("R1")
    if len(day)>=12 and H(6) and H(4) and H(2) and all(not H(k) for k in [12,11,10,9,8,7,5,3,1]): r.append("R2")
    g=gaps(day,n)
    if g==[1,4,1] and age==4:r.append("R3")
    if g==[1,2,1] and age in (7,8,9):r.append("R4")
    return r

def source(age):
    if age==1:return "H1"
    if age in (2,3):return "SHORT"
    if age in (4,5,6):return "MID"
    if age and 7<=age<=12:return "LONG"
    if age and age>=13:return "DEEP"
    return "DAY_UNSEEN"

def pair_carry(d,lookback=100):
    z=d.tail(lookback).reset_index(drop=True); pc={}
    for i in range(1,len(z)):
        common=sorted(set(z.iloc[i-1]["Sayilar"]) & set(z.iloc[i]["Sayilar"]))
        for a,b in combinations(common,2): pc[(a,b)]=pc.get((a,b),0)+1
    return pc

def main_pool(d):
    day=day_history(d); am=age_map(day); pc=pair_carry(d)
    last=set(d.iloc[-1]["Sayilar"]); rows=[]
    for n in range(1,81):
        a=am[n]; src=source(a); rr=rhythm(day,n,a)
        team=sum(pc.get(tuple(sorted((n,m))),0) for m in last if m!=n) if n in last else 0
        score={"H1":2.0,"SHORT":1.8,"MID":1.25,"LONG":.8,"DEEP":.35,"DAY_UNSEEN":.15}[src]
        why=[src]
        for x in rr: score+=2.1; why.append(x)
        if hbit(day,n,6):score+=.45; why.append("+6")
        if team: score+=min(1.5,team/30); why.append(f"H1_TEAM:{team}")
        rows.append((n,a,src,",".join(rr) or "-",team,round(score,3)," | ".join(why)))
    all80=pd.DataFrame(rows,columns=["Sayi","H_Yasi","Kaynak","Ritim","H1_Takim","Skor","Neden"])
    all80=all80.sort_values(["Skor","H1_Takim","Sayi"],ascending=[False,False,True]).reset_index(drop=True)
    return all80.head(20).copy(),all80

def make_main_tickets(pool):
    ns=pool["Sayi"].tolist(); sc=dict(zip(pool["Sayi"],pool["Skor"]))
    used={n:0 for n in ns}; out=[]
    for _ in range(3):
        cp=[]
        while len(cp)<4:
            cand=[n for n in ns if n not in cp]
            pick=max(cand,key=lambda n:(sc[n]-.30*used[n],-n))
            cp.append(pick); used[pick]+=1
        out.append(sorted(cp))
    return out

def user_code_engine(d,all80):
    if len(d)<6:return "YETERSIZ_VERI",[],[]
    last=set(d.iloc[-1]["Sayilar"]); pc=pair_carry(d)
    teams=[]
    for tri in combinations(sorted(last),3):
        s=sum(pc.get(tuple(sorted(x)),0) for x in combinations(tri,2))
        teams.append((s,tri))
    teams.sort(reverse=True)
    team=list(teams[0][1]) if teams and teams[0][0]>0 else []
    short=(set(d.iloc[-2]["Sayilar"])|set(d.iloc[-3]["Sayilar"]))-last
    mid=(set(d.iloc[-4]["Sayilar"])|set(d.iloc[-5]["Sayilar"])|set(d.iloc[-6]["Sayilar"]))-last-short
    if len(short)>=28 or len(mid)<=18: regime,cand="SHORT_HIGH",short
    elif len(mid)>=21 or len(short)<=25: regime,cand="MID_HIGH",mid
    else: regime,cand="NEUTRAL",short|mid
    score=dict(zip(all80["Sayi"],all80["Skor"]))
    cand=sorted(cand,key=lambda n:(score.get(n,0),-n),reverse=True)
    tickets=[]
    if len(team)==3:
        for n in cand:
            if n not in team:
                tickets.append(sorted(team+[n]))
            if len(tickets)==3:break
    return regime,team,tickets

def save_tickets(target,engine,tickets):
    c=db()
    for i,cp in enumerate(tickets,1):
        c.execute("""INSERT OR IGNORE INTO tickets(target_draw_id,engine,ticket_no,numbers)
                     VALUES(?,?,?,?)""",(target,engine,i,",".join(map(str,cp))))
    c.commit(); c.close()

def check_results():
    c=db()
    rows=c.execute("""SELECT t.id,t.numbers,d.numbers FROM tickets t
                      JOIN draws d ON d.draw_id=t.target_draw_id WHERE t.checked=0""").fetchall()
    for tid,cp,real in rows:
        hit=sorted(set(nums(cp))&set(nums(real)))
        c.execute("UPDATE tickets SET checked=1,hits=?,matched=? WHERE id=?",
                  (len(hit),",".join(map(str,hit)),tid))
    c.commit(); c.close()

def result_table():
    c=db()
    r=pd.read_sql_query("""SELECT target_draw_id Hedef,engine Motor,ticket_no Kolon,
                           numbers Sayilar,hits Isabet,matched Tutanlar
                           FROM tickets WHERE checked=1
                           ORDER BY target_draw_id DESC,engine,ticket_no LIMIT 24""",c)
    c.close()
    if not r.empty:r["Sonuc"]=r["Isabet"].astype(str)+"/4"
    return r

init_db()
memory_ok,memory_msg=seed_data()
check_results()
d=load_draws()

st.title("🎯 Hızlı On — Tek Ekran")
st.caption("3 ANA BEYİN + 3 GÖNDERDİĞİN KOD | yeni çekiliş ekle | kaç/4 sonucu gör")
if memory_ok: st.success(memory_msg+" ✓")
else:
    st.error(memory_msg); st.stop()

st.subheader("➕ Yeni çekiliş")
text=st.text_area("Çekilişi yapıştır",height=245,placeholder="""Çekiliş no: 54251
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
77""")
if st.button("EKLE → SONUCU KONTROL ET → YENİ 6 KUPONU ÜRET",type="primary",use_container_width=True):
    n,errs=add_draws(text)
    if errs: st.error(" | ".join(errs))
    else:
        check_results()
        st.success(f"{n} yeni çekiliş eklendi.")
        st.rerun()

d=load_draws()
if d.empty:st.stop()
target=int(d.iloc[-1]["draw_id"])+1
pool,all80=main_pool(d)
main3=make_main_tickets(pool)
regime,team,code3=user_code_engine(d,all80)
save_tickets(target,"ANA",main3)
save_tickets(target,"KOD",code3)

st.subheader(f"🎟️ Hedef #{target}")
c1,c2=st.columns(2)
with c1:
    st.markdown("### 🧠 ANA BEYİN — 3×4")
    for i,cp in enumerate(main3,1):
        st.success(f"ANA-{i}: "+" • ".join(f"{n:02d}" for n in cp))
with c2:
    st.markdown("### ⚙️ GÖNDERDİĞİN KOD — 3×4")
    if code3:
        for i,cp in enumerate(code3,1):
            st.info(f"KOD-{i}: "+" • ".join(f"{n:02d}" for n in cp))
    else: st.warning("Bu elde V33 takım sinyali yok; kod motoru kolon üretmedi.")
    st.caption(f"Rejim: {regime} | H1 takım: {team or '-'}")

st.subheader("✅ Sonuçlanan kolonlar")
r=result_table()
if r.empty: st.caption("Henüz sonuçlanan kolon yok.")
else: st.dataframe(r[["Hedef","Motor","Kolon","Sayilar","Sonuc","Tutanlar"]],hide_index=True,use_container_width=True)

with st.expander("🧬 20'lik havuz — sayı nereden geliyor?"):
    st.write(" • ".join(f"{n:02d}" for n in pool["Sayi"].tolist()))
    st.dataframe(pool,hide_index=True,use_container_width=True)
