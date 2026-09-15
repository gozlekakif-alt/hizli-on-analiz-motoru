import streamlit as st
import pandas as pd
import numpy as np
from collections import Counter
from itertools import combinations
from pathlib import Path
import sqlite3, json

st.set_page_config(page_title="Hızlı On Araştırma Laboratuvarı", layout="wide")
st.title("Hızlı On — Araştırma Laboratuvarı")
st.caption("Araştır → Walk-forward doğrula → Yeni çekiliş ekle → Top20 → Kupon → Sonuçla doğrula")

DATA_FILE = Path("veri.txt")
DB_FILE = "research.db"

def load_data(path=DATA_FILE):
    rows=[]
    if not path.exists(): return pd.DataFrame()
    for line in path.read_text(encoding="utf-8").splitlines():
        p=line.strip().split(";")
        if len(p)!=3: continue
        nums=tuple(sorted(map(int,p[2].split(","))))
        if len(nums)!=20 or len(set(nums))!=20: continue
        rows.append({"draw_id":int(p[0]),"time":pd.to_datetime(p[1],dayfirst=True),"numbers":nums})
    return pd.DataFrame(rows).sort_values(["time","draw_id"]).reset_index(drop=True)

def init_db():
    con=sqlite3.connect(DB_FILE)
    con.execute("""CREATE TABLE IF NOT EXISTS predictions(
      target_key TEXT PRIMARY KEY, created_at TEXT, history_last_id INTEGER,
      top20 TEXT, coupons TEXT, status TEXT DEFAULT 'FROZEN', actual TEXT, hits INTEGER)""")
    con.commit(); con.close()

def masks(df):
    a=np.zeros((len(df),80),dtype=np.uint8)
    for i,ns in enumerate(df.numbers):
        a[i,np.array(ns)-1]=1
    return a

def overlap_series(a):
    return np.sum(a[1:]*a[:-1],axis=1) if len(a)>1 else np.array([])

def family_table(df, k, min_count=2):
    c=Counter()
    for ns in df.numbers:
        c.update(combinations(ns,k))
    z=pd.DataFrame([(x,n) for x,n in c.items() if n>=min_count],columns=["family","count"])
    return z.sort_values("count",ascending=False) if len(z) else z

def consecutive_blocks(ns):
    ns=sorted(ns); blocks=[]; cur=[ns[0]]
    for x,y in zip(ns,ns[1:]):
        if y==x+1: cur.append(y)
        else:
            if len(cur)>=2: blocks.append(tuple(cur))
            cur=[y]
    if len(cur)>=2: blocks.append(tuple(cur))
    return blocks

def number_features(df):
    A=masks(df); n=len(df); rows=[]
    for num in range(1,81):
        idx=np.where(A[:,num-1]==1)[0]
        freq=len(idx)
        age=(n-1-idx[-1]) if freq else n
        gaps=np.diff(idx) if freq>1 else np.array([])
        h=[int(A[-j,num-1]) if n>=j else 0 for j in range(1,9)]
        recent5=int(A[max(0,n-5):,num-1].sum())
        recent12=int(A[max(0,n-12):,num-1].sum())
        recent36=int(A[max(0,n-36):,num-1].sum())
        rows.append([num,freq,age,recent5,recent12,recent36,*h,
                     float(gaps.mean()) if len(gaps) else np.nan])
    cols=["number","freq","age","r5","r12","r36"]+[f"H{i}" for i in range(1,9)]+["mean_gap"]
    return pd.DataFrame(rows,columns=cols)

def research_score(df):
    f=number_features(df).copy()
    # Başlangıç birleşik araştırma skoru. Sonraki sürümlerde her uzman motor ayrı walk-forward kalibre edilir.
    for c in ["freq","r5","r12","r36"]:
        sd=f[c].std()
        f[c+"_z"]=(f[c]-f[c].mean())/(sd if sd else 1)
    age_center=(f.age-f.age.median()).abs()
    f["score"]=1.20*f.r5_z + .90*f.r12_z + .45*f.r36_z + .20*f.freq_z
    f["score"] += .30*f.H1 + .18*f.H2 + .12*f.H3
    f["score"] -= .015*age_center
    return f.sort_values(["score","number"],ascending=[False,True])

def top20(df):
    return tuple(sorted(research_score(df).head(20).number.astype(int)))

def make_coupons(score):
    ranked=score.number.astype(int).tolist()
    top=ranked[:20]
    # 4 farklı görevli 10'lu kolon
    c1=top[:10]
    c2=top[0:20:2][:10]
    c3=top[1:20:2][:10]
    c4=(top[5:15] if len(top)>=15 else top[:10])
    return [tuple(sorted(x)) for x in [c1,c2,c3,c4]]

def walk_forward(df, warmup=50):
    rows=[]
    for i in range(max(warmup,1),len(df)):
        pred=set(top20(df.iloc[:i]))
        actual=set(df.iloc[i].numbers)
        rows.append({"draw_id":int(df.iloc[i].draw_id),"time":df.iloc[i].time,
                     "hits":len(pred&actual),"predicted":tuple(sorted(pred)),
                     "actual":tuple(sorted(actual))})
    return pd.DataFrame(rows)

def add_draw(draw_id, dt, nums):
    line=f"{int(draw_id)};{pd.Timestamp(dt).strftime('%d.%m.%Y %H:%M')};"+",".join(map(str,sorted(nums)))
    existing=DATA_FILE.read_text(encoding="utf-8").splitlines() if DATA_FILE.exists() else []
    if any(x.startswith(str(draw_id)+";") for x in existing): raise ValueError("Bu çekiliş numarası zaten kayıtlı.")
    with DATA_FILE.open("a",encoding="utf-8") as f: f.write(("\n" if existing else "")+line)

init_db()
df=load_data()
if df.empty:
    st.error("veri.txt bulunamadı veya okunamadı."); st.stop()
A=masks(df)

tabs=st.tabs(["Genel","Aileler 2–5","Ardışık/Geometri","H1–H8 & Yaş","Ritim","Aynı 20 / Yakınlık","Walk-forward","Canlı Top20 & Kupon","Yeni Çekiliş"])

with tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Çekiliş",len(df)); c2.metric("Gün",df.time.dt.date.nunique())
    c3.metric("İlk",str(df.iloc[0].draw_id)); c4.metric("Son",str(df.iloc[-1].draw_id))
    ov=overlap_series(A)
    if len(ov):
        st.write("Ardışık iki REAL20 kesişimi — ortalama:",round(float(ov.mean()),3),"maksimum:",int(ov.max()))
        st.bar_chart(pd.Series(ov).value_counts().sort_index())
    st.dataframe(number_features(df),use_container_width=True)

with tabs[1]:
    k=st.selectbox("Aile büyüklüğü",[2,3,4,5])
    minimum=st.number_input("Minimum tekrar",2,100,2)
    st.dataframe(family_table(df,k,minimum).head(500),use_container_width=True)

with tabs[2]:
    bc=Counter()
    for ns in df.numbers:
        for b in consecutive_blocks(ns): bc[b]+=1
    bt=pd.DataFrame(bc.items(),columns=["block","count"]).sort_values("count",ascending=False)
    st.dataframe(bt.head(500),use_container_width=True)
    st.caption("Sonraki sürüm: blok doğum/parçalanma/sağa-sola kayma/genişleme/daralma Event_ID zincirleri.")

with tabs[3]:
    st.dataframe(number_features(df),use_container_width=True)
    st.caption("H1–H8, yaş, uyku ve gap tabanı hazır. Koşullu dönüş tabloları uzman motor olarak ayrıştırılacak.")

with tabs[4]:
    num=st.number_input("Sayı",1,80,1)
    idx=np.where(A[:,int(num)-1]==1)[0]
    gaps=np.diff(idx)
    st.write("Çıkış:",len(idx),"Son yaş:",len(df)-1-idx[-1] if len(idx) else len(df))
    st.write("Ritim/gap dağılımı")
    if len(gaps): st.bar_chart(pd.Series(gaps).value_counts().sort_index())
    st.caption("R1–R4, yön asimetrisi, Event_ID ve ritim+H+yaş birleşimleri ayrı doğrulama katmanına genişletilecek.")

with tabs[5]:
    # Gerçek çekilişlerin birbirine benzerliği: 20/20, 19/20 ... maksimum
    best=(0,None,None)
    hist=Counter()
    for i in range(len(A)):
        sims=A[:i]@A[i] if i else np.array([])
        if len(sims):
            m=int(sims.max()); hist.update(map(int,sims))
            if m>best[0]:
                j=int(np.argmax(sims)); best=(m,int(df.iloc[j].draw_id),int(df.iloc[i].draw_id))
    st.metric("Tarihsel maksimum REAL20 ↔ REAL20 kesişimi",best[0])
    st.write("İlk maksimum örnek:",best[1],"→",best[2])
    st.bar_chart(pd.Series(hist).sort_index())
    st.caption("Walk-forward aday20 → REAL20 yakınsama basamakları Walk-forward sekmesindeki dondurulmuş tahminlerden ölçülür.")

with tabs[6]:
    warm=st.number_input("İlk eğitim çekilişi",20,500,50)
    if st.button("Walk-forward testi çalıştır"):
        with st.spinner("Kronolojik test çalışıyor..."):
            wf=walk_forward(df,int(warm))
        st.metric("Ortalama Top20 isabet",round(float(wf.hits.mean()),3))
        st.metric("Maksimum Top20 isabet",int(wf.hits.max()))
        st.bar_chart(wf.hits.value_counts().sort_index())
        st.dataframe(wf,use_container_width=True)

with tabs[7]:
    score=research_score(df); pool=tuple(sorted(score.head(20).number.astype(int)))
    st.subheader("Bir sonraki çekiliş için araştırma Top20")
    st.write(pool)
    st.dataframe(score.head(30),use_container_width=True)
    coupons=make_coupons(score)
    for i,c in enumerate(coupons,1): st.write(f"Kolon {i}:",c)
    target=st.text_input("Tahmin anahtarı / hedef çekiliş","NEXT")
    if st.button("Top20 ve kuponları DONDUR"):
        con=sqlite3.connect(DB_FILE)
        con.execute("INSERT OR REPLACE INTO predictions(target_key,created_at,history_last_id,top20,coupons,status) VALUES(?,datetime('now'),?,?,?,'FROZEN')",
                    (target,int(df.iloc[-1].draw_id),json.dumps(pool),json.dumps(coupons)))
        con.commit(); con.close()
        st.success("Tahmin donduruldu. Sonuç geldikten sonra geçmiş tahmin değiştirilemez kayıt olarak saklanır.")

with tabs[8]:
    st.write("Yeni sonuç önce mevcut dondurulmuş tahminin doğrulanmasında kullanılmalı, ardından araştırma havuzuna eklenir.")
    did=st.number_input("Çekiliş no",min_value=1,step=1)
    dt=st.text_input("Tarih saat (örn. 08.09.2026 00:02)")
    txt=st.text_area("20 sayı (virgülle)")
    if st.button("Yeni çekilişi ekle"):
        try:
            ns=[int(x.strip()) for x in txt.split(",") if x.strip()]
            if len(ns)!=20 or len(set(ns))!=20 or min(ns)<1 or max(ns)>80:
                raise ValueError("Tam 20 benzersiz sayı, 1–80 arasında olmalı.")
            add_draw(did,pd.to_datetime(dt,dayfirst=True),ns)
            st.success("Çekiliş havuza eklendi. Sayfayı yenileyince tüm araştırma durumları yeni veriyle hesaplanır.")
        except Exception as e: st.error(str(e))
