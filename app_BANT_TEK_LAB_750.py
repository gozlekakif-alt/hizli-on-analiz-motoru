from pathlib import Path
from datetime import datetime
import re
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="BANT TEK LAB 750", page_icon="📊", layout="wide")
BASE = Path(__file__).with_name("veri.txt")

def parse_line(s):
    p=str(s).strip().split(";")
    if len(p)!=4: return None
    try:
        no=int(p[0]); dt=datetime.strptime(p[1]+" "+p[2],"%d.%m.%Y %H:%M")
        nums=[int(x) for x in re.findall(r"\d+",p[3])]
    except: return None
    if len(nums)!=20 or len(set(nums))!=20 or not all(1<=x<=80 for x in nums): return None
    return no,dt,sorted(nums)

@st.cache_data(show_spinner=False)
def load(txt):
    rows=[z for x in txt.splitlines() if (z:=parse_line(x)) is not None]
    if not rows: return pd.DataFrame(columns=["No","DT","Nums"])
    return (pd.DataFrame(rows,columns=["No","DT","Nums"])
            .drop_duplicates("No",keep="last").sort_values("No").reset_index(drop=True))

def make_A(df):
    A=np.zeros((len(df),80),dtype=np.int8)
    for i,nums in enumerate(df.Nums):
        A[i,np.asarray(nums,dtype=int)-1]=1
    return A

def score_bands(A,t):
    # 8 adet 10'luk bant: 1-10 ... 71-80.
    # Yalnız t'den önceki geçmiş kullanılır.
    windows=(5,10,20,50,100)
    rates={}
    for w in windows:
        H=A[max(0,t-w):t]
        rates[w]=np.array([H[:,b*10:(b+1)*10].mean() if len(H) else 0 for b in range(8)])
    short=rates[5]
    medium=rates[20]
    long=rates[100]
    trend=short-long
    stability=1.0-np.clip(np.abs(rates[10]-rates[50])/0.25,0,1)
    # Ham BANT puanı: yakın dönem basıncı + orta dönem + trend + istikrar.
    raw=.40*short+.25*medium+.20*np.maximum(trend,0)+.15*stability
    return raw,rates,trend,stability

def predict(A,t,k_bands=2):
    raw,rates,trend,stability=score_bands(A,t)
    order=np.argsort(-raw)
    chosen=order[:k_bands]
    # Seçilen bantların kendi içindeki sayıları son20 frekansına göre sırala;
    # her banttan 5 sayı = Top10.
    H=A[max(0,t-20):t]
    f20=H.mean(0) if len(H) else np.zeros(80)
    picks=[]
    detail=[]
    for rank,b in enumerate(order,1):
        lo=b*10; hi=lo+10
        nums=np.arange(lo,hi)
        local=nums[np.argsort(-f20[nums],kind="mergesort")]
        detail.append({
            "Bant":f"{lo+1}-{hi}",
            "Bant sıra":rank,
            "Bant skor":float(raw[b]),
            "Son5 yoğunluk":float(rates[5][b]),
            "Son20 yoğunluk":float(rates[20][b]),
            "Son100 yoğunluk":float(rates[100][b]),
            "Trend":float(trend[b]),
            "İstikrar":float(stability[b]),
            "Bant Top5":"-".join(map(str,(local[:5]+1).tolist()))
        })
        if b in chosen:
            picks.extend((local[:5]+1).tolist())
    return sorted(set(map(int,picks))),pd.DataFrame(detail)

def backtest(df,A,n=750):
    valid=[t for t in range(120,len(df)) if int(df.No.iloc[t])==int(df.No.iloc[t-1])+1]
    valid=valid[-min(n,len(valid)):]
    rows=[]; details=[]
    for pos,t in enumerate(valid):
        picks,tab=predict(A,t)
        actual=set((np.where(A[t]>0)[0]+1).tolist())
        hits=sorted(set(picks)&actual)
        seg="İlk 250" if pos<250 else ("Orta 250" if pos<500 else "Son 250")
        rows.append({
            "Sıra":pos+1,"Bölüm":seg,"Çekiliş":int(df.No.iloc[t]),
            "Tarih/Saat":df.DT.iloc[t].strftime("%d.%m.%Y %H:%M"),
            "Top10":len(hits),"Tahmin":"-".join(map(str,picks)),
            "Tutan":"-".join(map(str,hits)),
            "Sızıntı":"TEMİZ" if int(df.No.iloc[t-1])<int(df.No.iloc[t]) else "HATALI"
        })
        tab.insert(0,"Çekiliş",int(df.No.iloc[t]))
        tab["Seçili"]=tab["Bant sıra"]<=2
        details.append(tab)
    return pd.DataFrame(rows),pd.concat(details,ignore_index=True)

st.title("📊 BANT TEK LAB — 750")
st.caption("BANT uzmanı bağımsız test edilir. 8 adet 10'luk bant. Test yalnız düğmeye basınca çalışır.")
if not BASE.exists():
    st.error("veri.txt bulunamadı. Bu .py ile veri.txt aynı klasörde olmalı."); st.stop()

df=load(BASE.read_text(encoding="utf-8",errors="ignore"))
if len(df)<180:
    st.error(f"Yeterli veri yok: {len(df)}"); st.stop()
st.success(f"Veri hazır: {len(df)} çekiliş")
st.info("Sabit test: son 750 geçerli walk-forward. Top10 rastgele beklenti = 2.500.")

if "bant_res" not in st.session_state: st.session_state.bant_res=None
if "bant_det" not in st.session_state: st.session_state.bant_det=None

if st.button("🚀 750 TESTİ BAŞLAT",type="primary",use_container_width=True):
    with st.spinner("BANT 750 walk-forward çalışıyor..."):
        A=make_A(df); r,d=backtest(df,A,750)
        st.session_state.bant_res=r; st.session_state.bant_det=d

r=st.session_state.bant_res
if isinstance(r,pd.DataFrame) and len(r):
    c1,c2,c3,c4=st.columns(4)
    avg=float(r.Top10.mean())
    c1.metric("Test",len(r)); c2.metric("Top10 ort.",f"{avg:.3f}")
    c3.metric("Rastgele","2.500",delta=f"{avg-2.5:+.3f}")
    c4.metric("Maksimum",int(r.Top10.max()))
    seg=(r.groupby("Bölüm",sort=False)
         .agg(Test=("Top10","size"),Top10_Ort=("Top10","mean"),
              Bes_Artı=("Top10",lambda x:int((x>=5).sum())),
              Alti_Artı=("Top10",lambda x:int((x>=6).sum())),
              Maks=("Top10","max")).reset_index())
    seg["Net"]=seg.Top10_Ort-2.5
    st.subheader("İlk / Orta / Son 250")
    st.dataframe(seg,use_container_width=True,hide_index=True)
    st.download_button("⬇️ TEST SONUCUNU İNDİR",
        r.to_csv(index=False).encode("utf-8-sig"),
        file_name="BANT_750_WALKFORWARD.csv",mime="text/csv",use_container_width=True)
    st.download_button("⬇️ BANT DETAYINI İNDİR",
        st.session_state.bant_det.to_csv(index=False).encode("utf-8-sig"),
        file_name="BANT_750_DETAY.csv",mime="text/csv",use_container_width=True)

st.divider()
st.subheader("🎯 Güncel BANT kararı")
try:
    A=make_A(df); p,t=predict(A,len(df))
    st.info("Top10: "+" - ".join(map(str,p)))
    st.dataframe(t,use_container_width=True,hide_index=True)
except Exception as e:
    st.warning(str(e))
