from pathlib import Path
from datetime import datetime
import re
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="BİRLİKTELİK TEK LAB 750",page_icon="🤝",layout="wide")
BASE=Path(__file__).with_name("veri.txt")

def parse_line(s):
    p=str(s).strip().split(";")
    if len(p)!=4:return None
    try:
        no=int(p[0]); dt=datetime.strptime(p[1]+" "+p[2],"%d.%m.%Y %H:%M")
        nums=[int(x) for x in re.findall(r"\d+",p[3])]
    except:return None
    if len(nums)!=20 or len(set(nums))!=20 or not all(1<=x<=80 for x in nums):return None
    return no,dt,sorted(nums)

@st.cache_data(show_spinner=False)
def load(txt):
    r=[]
    for x in txt.splitlines():
        z=parse_line(x)
        if z:r.append(z)
    d=pd.DataFrame(r,columns=["No","DT","Nums"]).drop_duplicates("No",keep="last").sort_values("No").reset_index(drop=True)
    return d

def matrix(df):
    A=np.zeros((len(df),80),dtype=np.int8)
    for i,a in enumerate(df.Nums):
        A[i,np.array(a)-1]=1
    return A

def pair_scores(A,t,window=160):
    H=A[max(0,t-window):t].astype(float); m=len(H)
    f=H.sum(0)
    co=H.T@H
    exp=np.outer(f,f)/max(m,1)
    lift=np.divide(co,exp,out=np.zeros_like(co),where=exp>0)
    np.fill_diagonal(lift,0)
    # Güvenilir eşleşme: en az 4 ortak olay; aşırı küçük örnek liftini bastır.
    support=(co>=4)
    adj=np.where(support,np.clip(lift,0,3),0)
    # Her sayının en güçlü 5 partneri.
    s=np.sort(adj,axis=1)[:,-5:].mean(1)
    return s,co,adj

def predict(A,t,k=10):
    s,co,adj=pair_scores(A,t)
    order=np.argsort(-s)[:k]
    rows=[]
    for i in order:
        partners=np.argsort(-adj[i])[:5]
        rows.append({"Sayı":int(i+1),"Birliktelik":float(s[i]),
                     "En güçlü eşler":"-".join(str(int(x+1)) for x in partners if adj[i,x]>0)})
    return [int(x+1) for x in order],pd.DataFrame(rows)

def backtest(df,A,n=750):
    valid=[t for t in range(160,len(df)) if int(df.No.iloc[t])==int(df.No.iloc[t-1])+1]
    valid=valid[-min(n,len(valid)):]
    rr=[]; dd=[]
    for pos,t in enumerate(valid):
        pred,tab=predict(A,t,10); actual=set(np.where(A[t]>0)[0]+1); hits=sorted(set(pred)&actual)
        third="İlk 250" if pos<250 else ("Orta 250" if pos<500 else "Son 250")
        rr.append({"Sıra":pos+1,"Bölüm":third,"Çekiliş":int(df.No.iloc[t]),
                   "Tarih/Saat":df.DT.iloc[t].strftime("%d.%m.%Y %H:%M"),
                   "Top10":len(hits),"Tahmin":"-".join(map(str,pred)),"Tutan":"-".join(map(str,hits)),
                   "Sızıntı":"TEMİZ" if int(df.No.iloc[t-1])<int(df.No.iloc[t]) else "HATALI"})
        tab.insert(0,"Çekiliş",int(df.No.iloc[t])); tab["Doğru"]=tab["Sayı"].isin(actual).astype(int)
        dd.append(tab)
    return pd.DataFrame(rr),pd.concat(dd,ignore_index=True)

st.title("🤝 BİRLİKTELİK TEK LAB — 750")
st.caption("Eski 8-uzman yapısındaki BİRLİKTELİK/pair mantığı bağımsız test edilir. Açılışta ağır test çalışmaz.")
if not BASE.exists():
    st.error("veri.txt bulunamadı; .py ile aynı klasörde olmalı."); st.stop()
df=load(BASE.read_text(encoding="utf-8",errors="ignore"))
st.success(f"Veri hazır: {len(df)} çekiliş")
st.info("Test sabit: 750 walk-forward. Top10 rastgele beklenti = 2.500.")

if "bir750" not in st.session_state:st.session_state.bir750=None
if "birdet" not in st.session_state:st.session_state.birdet=None

if st.button("🚀 750 TESTİ BAŞLAT",type="primary",use_container_width=True):
    with st.spinner("750 sızıntısız BİRLİKTELİK testi çalışıyor..."):
        A=matrix(df); r,d=backtest(df,A,750)
        st.session_state.bir750=r; st.session_state.birdet=d

r=st.session_state.bir750
if isinstance(r,pd.DataFrame) and len(r):
    st.subheader("📊 750 sonuç")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Top10 ort.",f"{r.Top10.mean():.3f}")
    c2.metric("Rastgele","2.500",delta=f"{r.Top10.mean()-2.5:+.3f}")
    c3.metric("5+",int((r.Top10>=5).sum()))
    c4.metric("Maksimum",int(r.Top10.max()))
    seg=r.groupby("Bölüm",sort=False).agg(Test=("Top10","size"),Top10_Ort=("Top10","mean"),Bes_Artı=("Top10",lambda x:int((x>=5).sum())),Maks=("Top10","max")).reset_index()
    seg["Net"]=seg.Top10_Ort-2.5
    st.subheader("İlk / Orta / Son 250")
    st.dataframe(seg,use_container_width=True,hide_index=True)
    st.dataframe(r.sort_values("Çekiliş",ascending=False),use_container_width=True,hide_index=True)
    st.download_button("⬇️ TEST SONUCUNU İNDİR",r.to_csv(index=False).encode("utf-8-sig"),
                       file_name="BIRLIKTELIK_750_WALKFORWARD.csv",mime="text/csv",use_container_width=True)
    d=st.session_state.birdet
    st.download_button("⬇️ ADAY DETAYINI İNDİR",d.to_csv(index=False).encode("utf-8-sig"),
                       file_name="BIRLIKTELIK_750_ADAY_DETAY.csv",mime="text/csv",use_container_width=True)

st.divider()
st.subheader("🎯 Güncel BİRLİKTELİK Top10")
try:
    A=matrix(df); p,t=predict(A,len(df),10)
    st.info(" - ".join(map(str,p)))
    st.dataframe(t,use_container_width=True,hide_index=True)
except Exception as e: st.warning(str(e))
