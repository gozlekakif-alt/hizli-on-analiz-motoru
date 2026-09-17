import streamlit as st
import pandas as pd
import requests
from itertools import combinations
from collections import Counter
from datetime import datetime

st.set_page_config(page_title="Hızlı On Aile Tarayıcı V2",layout="wide")
st.title("🎯 Hızlı On — Aile / Çekirdek Tarayıcı V2")
st.caption("GitHub veri.txt → 10'lu / 9'lu / 8'li tekrarlar → gün, tarih, saat, çekiliş")

URL="https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"
DAYS={0:"Pazartesi",1:"Salı",2:"Çarşamba",3:"Perşembe",4:"Cuma",5:"Cumartesi",6:"Pazar"}

@st.cache_data(show_spinner=False)
def load(url):
    r=requests.get(url,timeout=30); r.raise_for_status()
    rows=[]; bad=[]
    for ln,line in enumerate(r.text.splitlines(),1):
        if not line.strip(): continue
        try:
            a,b,c=line.strip().split(";",2)
            dt=datetime.strptime(b.strip(),"%d.%m.%Y %H:%M")
            nums=tuple(sorted(map(int,c.split(","))))
            if len(nums)!=20 or len(set(nums))!=20 or not all(1<=n<=80 for n in nums):
                raise ValueError("Geçersiz REAL20")
            rows.append((int(a),dt,nums,frozenset(nums)))
        except Exception as e:
            bad.append((ln,line,str(e)))
    return rows,bad

@st.cache_data(show_spinner=False)
def scan(serialized,k):
    rows=[(no,datetime.fromisoformat(dt),tuple(nums),frozenset(nums))
          for no,dt,nums in serialized]
    d={}
    N=len(rows)
    for i in range(N-1):
        A=rows[i][3]
        for j in range(i+1,N):
            inter=A & rows[j][3]
            if len(inter)>=k:
                for fam in combinations(sorted(inter),k):
                    d.setdefault(fam,set()).update((i,j))
    # cache-friendly: set -> sorted tuple
    return {fam:tuple(sorted(v)) for fam,v in d.items()}

def family_df(d,rows,minrep):
    rec=[]
    for fam,idx in d.items():
        if len(idx)>=minrep:
            rec.append({
                "Aile / Çekirdek":"-".join(map(str,fam)),
                "Tekrar":len(idx),
                "Çekilişler":", ".join(f"#{rows[i][0]}" for i in idx)
            })
    if not rec:
        return pd.DataFrame(columns=["Aile / Çekirdek","Tekrar","Çekilişler"])
    return pd.DataFrame(rec).sort_values(
        ["Tekrar","Aile / Çekirdek"],ascending=[False,True]
    ).reset_index(drop=True)

url=st.text_input("GitHub RAW veri.txt",URL)
try:
    rows,bad=load(url)
except Exception as e:
    st.error(f"Veri alınamadı: {e}"); st.stop()

c1,c2,c3,c4=st.columns(4)
c1.metric("Geçerli çekiliş",len(rows))
c2.metric("Hatalı satır",len(bad))
c3.metric("İlk",f"#{rows[0][0]}" if rows else "-")
c4.metric("Son",f"#{rows[-1][0]}" if rows else "-")
if not rows: st.stop()

serialized=tuple((no,dt.isoformat(),nums) for no,dt,nums,_ in rows)

st.divider()
k=st.radio("Tarama türü",[10,9,8],horizontal=True,index=2)

# IMPORTANT FIX: min repeat does NOT trigger a rescan and cannot erase the cached result.
if "results" not in st.session_state:
    st.session_state.results={}

if st.button(f"🔬 TÜM {k}'LİLERİ TARA",type="primary",use_container_width=True):
    with st.spinner(f"{k}'li tekrarlar hesaplanıyor. Bitene kadar sayfayı kapatma..."):
        st.session_state.results[k]=scan(serialized,k)
    st.success(f"{k}'li tarama tamamlandı.")

if k not in st.session_state.results:
    st.info(f"Önce TÜM {k}'LİLERİ TARA butonuna bas.")
    st.stop()

d=st.session_state.results[k]
dist=Counter(len(v) for v in d.values())
maxrep=max(dist) if dist else 0

a,b=st.columns(2)
a.metric(f"Tekrar eden farklı {k}'li",f"{len(d):,}".replace(",","."))
b.metric("Maksimum tekrar",maxrep)

st.subheader("Tekrar dağılımı")
distdf=pd.DataFrame([{"Tekrar":r,"Farklı aile":n} for r,n in sorted(dist.items())])
st.dataframe(distdf,hide_index=True,use_container_width=True)

# FIX: slider bounded by ACTUAL maximum; default = maximum so strongest families show immediately.
st.subheader("Aile listesini aç")
minrep=st.slider(
    "Minimum tekrar",
    min_value=2,
    max_value=max(2,maxrep),
    value=max(2,maxrep),
    step=1,
    key=f"minrep_{k}"
)

df=family_df(d,rows,minrep)
st.write(f"**Gösterilen aile sayısı: {len(df)}**")
if df.empty:
    st.warning("Bu eşikte aile yok. Minimum tekrarı düşür.")
    st.stop()

# FIX: full family table is always shown and its own CSV is directly underneath.
st.dataframe(df,hide_index=True,use_container_width=True,height=520)
st.download_button(
    f"⬇️ BU {len(df)} AİLEYİ CSV İNDİR",
    df.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"{k}li_aileler_min_{minrep}.csv",
    mime="text/csv",
    type="primary",
    use_container_width=True
)

# Full detailed export: one row per family occurrence, with day/date/time/REAL20.
all_events=[]
for fam,idxs in d.items():
    if len(idxs)<minrep: continue
    famtxt="-".join(map(str,fam))
    for i in idxs:
        no,dt,nums,_=rows[i]
        all_events.append({
            "Aile / Çekirdek":famtxt,
            "Aile Tekrarı":len(idxs),
            "Çekiliş No":no,
            "Gün":DAYS[dt.weekday()],
            "Tarih":dt.strftime("%d.%m.%Y"),
            "Saat":dt.strftime("%H:%M"),
            "REAL20":"-".join(map(str,nums))
        })
detail_all=pd.DataFrame(all_events).sort_values(
    ["Aile Tekrarı","Aile / Çekirdek","Tarih","Saat"],
    ascending=[False,True,True,True]
)
st.download_button(
    f"⬇️ TÜM {len(df)} AİLENİN GÜN-SAAT DETAYINI CSV İNDİR",
    detail_all.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"{k}li_aileler_min_{minrep}_GUN_SAAT_DETAY.csv",
    mime="text/csv",
    use_container_width=True
)

st.divider()
st.subheader("Tek aile kadavrası")
sel=st.selectbox("Aile seç",df["Aile / Çekirdek"].tolist())
fam=tuple(map(int,sel.split("-")))
idxs=d[fam]
events=[]
for i in sorted(idxs,key=lambda q:rows[q][1]):
    no,dt,nums,_=rows[i]
    events.append({
        "Çekiliş No":no,
        "Gün":DAYS[dt.weekday()],
        "Tarih":dt.strftime("%d.%m.%Y"),
        "Saat":dt.strftime("%H:%M"),
        "REAL20":"-".join(map(str,nums))
    })
ed=pd.DataFrame(events)
st.markdown(f"### 📌 {sel} — {len(idxs)} kez")
st.dataframe(ed,hide_index=True,use_container_width=True)

x,y=st.columns(2)
with x:
    st.markdown("**Gün dağılımı**")
    st.dataframe(ed["Gün"].value_counts().rename_axis("Gün").reset_index(name="Tekrar"),
                 hide_index=True,use_container_width=True)
with y:
    st.markdown("**Saat dağılımı**")
    st.dataframe(ed["Saat"].str[:2].value_counts().sort_index().rename_axis("Saat bandı").reset_index(name="Tekrar"),
                 hide_index=True,use_container_width=True)

txt=[f"{k}'Lİ AİLE: {sel}",f"TOPLAM TEKRAR: {len(idxs)}",""]
for z in events:
    txt.append(f"#{z['Çekiliş No']} | {z['Gün']} | {z['Tarih']} | {z['Saat']} | {z['REAL20']}")
st.download_button(
    "⬇️ SEÇİLİ AİLE TXT",
    "\n".join(txt).encode("utf-8"),
    file_name=f"{k}li_{sel}_detay.txt",
    mime="text/plain",
    use_container_width=True
)

st.caption("V2 düzeltmesi: Minimum tekrar artık taramadan bağımsız filtre. Maksimum 4 ise 24 gibi geçersiz eşik seçilemez. Güçlü aile tablosu ve tüm gün/saat detay CSV'si doğrudan indirilebilir.")
