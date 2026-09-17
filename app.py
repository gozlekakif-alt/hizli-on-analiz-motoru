import streamlit as st
import pandas as pd
import requests
from itertools import combinations
from collections import Counter
from datetime import datetime

st.set_page_config(page_title="Hızlı On Aile Tarayıcı",layout="wide")
st.title("🎯 Hızlı On — 10'lu / 9'lu / 8'li Aile Tarayıcı")

URL="https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"
DAYS={0:"Pazartesi",1:"Salı",2:"Çarşamba",3:"Perşembe",4:"Cuma",5:"Cumartesi",6:"Pazar"}

@st.cache_data
def load(url):
    x=requests.get(url,timeout=30); x.raise_for_status()
    rows=[]; bad=[]
    for ln,line in enumerate(x.text.splitlines(),1):
        try:
            a,b,c=line.strip().split(";",2)
            dt=datetime.strptime(b,"%d.%m.%Y %H:%M")
            nums=tuple(sorted(map(int,c.split(","))))
            if len(nums)!=20 or len(set(nums))!=20 or not all(1<=n<=80 for n in nums): raise ValueError("Geçersiz REAL20")
            rows.append((int(a),dt,nums,frozenset(nums)))
        except Exception as e: bad.append((ln,line,str(e)))
    return rows,bad

def scan(rows,k):
    # Tekrar eden bir k'li, en az iki REAL20'nin kesişiminde bulunmak zorundadır.
    # Bu yüzden yüz milyonlarca tekil kombinasyonu üretmeden eksiksiz tekrar taraması yapılır.
    d={}
    N=len(rows); bar=st.progress(0)
    for i in range(N-1):
        A=rows[i][3]
        for j in range(i+1,N):
            inter=A & rows[j][3]
            if len(inter)>=k:
                for fam in combinations(sorted(inter),k):
                    d.setdefault(fam,set()).update((i,j))
        if i%40==0: bar.progress((i+1)/(N-1))
    bar.empty()
    return d

url=st.text_input("GitHub RAW veri.txt",URL)
try: rows,bad=load(url)
except Exception as e: st.error(str(e)); st.stop()

a,b,c=st.columns(3)
a.metric("Geçerli çekiliş",len(rows)); b.metric("Hatalı satır",len(bad))
c.metric("Aralık",f"#{rows[0][0]}–#{rows[-1][0]}" if rows else "-")
if not rows: st.stop()

k=st.radio("Tarama",[10,9,8],horizontal=True)
minimum=st.number_input("Minimum tekrar",2,100,2)

if st.button(f"🔬 TÜM {k}'LİLERİ TARA",type="primary",use_container_width=True):
    st.session_state.result=scan(rows,k); st.session_state.k=k

if st.session_state.get("k")==k:
    d=st.session_state.result
    if not d: st.warning("Tekrar eden aile bulunamadı."); st.stop()
    dist=Counter(map(len,d.values()))
    m=max(dist)
    x,y=st.columns(2); x.metric("Tekrar eden farklı aile",len(d)); y.metric("Maksimum tekrar",m)
    st.subheader("Tekrar dağılımı")
    st.dataframe(pd.DataFrame([{"Tekrar":r,"Farklı aile":n} for r,n in sorted(dist.items())]),hide_index=True,use_container_width=True)

    data=[]
    for fam,idx in d.items():
        if len(idx)>=minimum:
            data.append({"Aile":"-".join(map(str,fam)),"Tekrar":len(idx),
                         "Çekilişler":", ".join("#"+str(rows[i][0]) for i in sorted(idx))})
    df=pd.DataFrame(data)
    if len(df): df=df.sort_values(["Tekrar","Aile"],ascending=[False,True])
    st.subheader(f"{k}'li aileler")
    st.dataframe(df,hide_index=True,use_container_width=True,height=450)
    st.download_button("⬇️ Özet CSV",df.to_csv(index=False).encode("utf-8-sig"),f"{k}li_aileler.csv","text/csv")

    if len(df):
        sel=st.selectbox("Aile detayını aç",df["Aile"])
        fam=tuple(map(int,sel.split("-"))); idx=d[fam]
        ev=[]
        for i in sorted(idx,key=lambda q:rows[q][1]):
            no,dt,nums,_=rows[i]
            ev.append({"Çekiliş No":no,"Gün":DAYS[dt.weekday()],"Tarih":dt.strftime("%d.%m.%Y"),
                       "Saat":dt.strftime("%H:%M"),"REAL20":"-".join(map(str,nums))})
        ed=pd.DataFrame(ev)
        st.subheader(f"📌 {sel} — {len(idx)} kez")
        st.dataframe(ed,hide_index=True,use_container_width=True)
        l,r=st.columns(2)
        with l:
            st.markdown("**Gün dağılımı**")
            st.dataframe(ed["Gün"].value_counts().rename_axis("Gün").reset_index(name="Tekrar"),hide_index=True)
        with r:
            st.markdown("**Saat bandı**")
            st.dataframe(ed["Saat"].str[:2].value_counts().sort_index().rename_axis("Saat").reset_index(name="Tekrar"),hide_index=True)
        st.download_button("⬇️ Detay CSV",ed.to_csv(index=False).encode("utf-8-sig"),f"{k}li_{sel}_detay.csv","text/csv")
        txt=f"{k}'Lİ: {sel}\nTOPLAM: {len(idx)}\n\n"+"\n".join(
            f"#{z['Çekiliş No']} | {z['Gün']} | {z['Tarih']} | {z['Saat']} | {z['REAL20']}" for z in ev)
        st.download_button("⬇️ Detay TXT",txt.encode("utf-8"),f"{k}li_{sel}_detay.txt","text/plain")

st.caption("8/9/10 tekrar taraması, REAL20 çiftlerinin kesişimleri üzerinden yapılır; yalnız gerçekten tekrar edebilecek alt kümeler üretilir.")
