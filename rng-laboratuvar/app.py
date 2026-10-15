# -*- coding: utf-8 -*-
"""Independent Streamlit Cloud entrypoint. Runs separately from v10_app.py."""
from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import duckdb
import pandas as pd
import requests
import streamlit as st

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0,str(HERE))

from core import read_txt,build_package,FORWARD_START,FORWARD_DAYS

# Read-only endpoint; cannot change old data or the live V10 application.
SOURCE="https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"
st.set_page_config(page_title="RNG Karakter Laboratuvarı",page_icon="🧠",layout="wide")
st.title("🧠 Hızlı On — RNG Karakter Laboratuvarı")
st.caption("Bağımsız araştırma uygulaması • salt okunur GitHub veri kaynağı • "
           "karakter tahmini önce, sayı seçimi sonra")

@st.cache_data(ttl=600,show_spinner=False)
def read_from_github():
    response=requests.get(SOURCE,timeout=45,headers={"Accept":"text/plain"})
    response.raise_for_status()
    return response.content.decode("utf-8-sig")

@st.cache_data(ttl=900,show_spinner=False,max_entries=3)
def calculate(digest,raw,day,simulations):
    full,partial,rejects=read_txt(raw)
    return build_package(full,partial,rejects,day=day,sims=simulations)

st.markdown("#### 1. Veriyi yükle")
a,b=st.columns([2,1])
with a:
    upload=st.file_uploader(
       "İstersen güncel veri.txt yükle (GitHub'a kayıt yapmaz)",
       type=["txt"],key="lab_user_file")
with b:
    st.write("")
    go=st.button("↻ GitHub'dan güncel veriyi oku",type="primary",
                 use_container_width=True)
if upload is not None:
    raw=upload.getvalue().decode("utf-8-sig")
    st.session_state["lab_current_raw"]=raw
    st.session_state["lab_source"]="Yüklenen TXT"
elif go:
    try:
        with st.spinner("Eski programın veri.txt dosyası salt okunur getiriliyor..."):
            st.session_state["lab_current_raw"]=read_from_github()
        st.session_state["lab_source"]="GitHub veri.txt"
    except Exception as exc:
        st.error(f"GitHub verisi alınamadı: {exc}. Dosyayı yukarıya yükleyebilirsin.")

raw=st.session_state.get("lab_current_raw")
if not raw:
    st.info("Başlamak için GitHub verisini oku veya TXT yükle. "
            "Eski motorlar ve veri.txt değiştirilmez.")
    st.stop()

full,partial,rejects=read_txt(raw)
if not full:
    st.warning("Veride 217 çekilişten oluşan tam gün bulunamadı.")
    st.stop()
dates=sorted(full,reverse=True)
new_days=[d for d in full if d>=str(FORWARD_START)]
k1,k2,k3,k4=st.columns(4)
k1.metric("Tam gün",len(full))
k2.metric("Toplam gerçek çekiliş",217*len(full))
k3.metric("Eksik gün",len(partial))
k4.metric("Yeni kör gün",f"{min(FORWARD_DAYS,len(new_days))}/{FORWARD_DAYS}")
if rejects:
    st.warning(f"{len(rejects)} hatalı/mükerrer ham veri satırı hesap dışı bırakıldı.")
st.caption(f"Kaynak: {st.session_state.get('lab_source','veri.txt')}. "
           "Kör test 16.10.2026'da başlar, ilk 14 tam günü kapsar.")

st.markdown("#### 2. Veri ambarı — DuckDB")
# SQL analysis of normalized records, without modifying GitHub or disk.
@st.cache_data(ttl=900,show_spinner=False,max_entries=2)
def sql_summary(fingerprint,data):
    df=pd.DataFrame([(day,row["slot"],row["id"],
                       "-".join(str(n) for n in sorted(row["nums"])))
                     for day,rows in data.items() for row in rows],
                    columns=["day","slot","draw_id","numbers"])
    con=duckdb.connect(database=":memory:")
    con.register("draws",df)
    daily=con.execute(
        "SELECT day, count(*)::INTEGER AS cekilis, min(draw_id) AS ilk, "
        "max(draw_id) AS son FROM draws GROUP BY day ORDER BY day DESC LIMIT 12"
    ).df()
    con.close()
    return daily
fingerprint=hashlib.sha256(raw.encode("utf-8")).hexdigest()
try:
    result=sql_summary(fingerprint,full)
    st.dataframe(result,hide_index=True,use_container_width=True,height=230)
except Exception as exc:
    st.caption(f"DuckDB gösterimi şu anda açılamadı: {exc}")

st.markdown("#### 3. Karakter / aile dönüşümü / RNG sınavı")
left,right=st.columns(2)
with left:
    chosen=st.selectbox("İncelenecek tam gün",dates,index=0)
with right:
    sims=st.select_slider(
        "Bağımsız rastgele 217 çekilişli sanal gün",
        options=[20,40,80,160],value=40)

st.caption("Model aynı saatin ilk 6 çekilişini görür; son 6'nın karakterini "
           "tahmin eder, ardından 10 sayı seçer. Gelecek sonuçların hiçbiri "
           "o saatin tahminini oluştururken kullanılmaz.")

marker=f"{fingerprint}|{chosen}|{sims}"
if st.button("▶️ LABORATUVARI ÇALIŞTIR — TEK RAPOR HAZIRLA",
             type="primary",use_container_width=True):
    try:
        with st.spinner("Kör test, karakter geçişleri ve sanal RNG hesaplanıyor..."):
            package,metadata=calculate(fingerprint,raw,chosen,sims)
        st.session_state["lab_package"]=(marker,package,metadata)
    except Exception as exc:
        st.error(f"Laboratuvar hesaplama hatası: {exc}")

saved=st.session_state.get("lab_package")
if not saved:
    st.info("Programı çalıştırdığında karakter hata karşılaştırması, "
            "aile değişimleri ve kupon isabetleri tek raporda oluşacak.")
    st.stop()
if saved[0]!=marker:
    st.info("Veri veya ayarlar değişti. Yeni rapor için programı tekrar çalıştır.")
    st.stop()

_,data,meta=saved
st.markdown("#### 4. Karakteri bilmek sayı seçimini iyileştirdi mi?")
st.dataframe(pd.DataFrame(meta["summary"]),hide_index=True,use_container_width=True)
st.markdown("#### Gerçek aile değişimi mi, rastgele beklenti mi?")
st.dataframe(pd.DataFrame(meta["sims"]),hide_index=True,use_container_width=True)
st.caption("Bu tablodaki olasılık değerleri keşif amaçlıdır. "
           "Birden çok desen tarandığı için gelecek öngörüsü kanıtı sayılmaz.")

st.download_button(
    "⬇️ TEK ZIP İNDİR — BANA GÖNDER",
    data=data,
    file_name=f"RNG_KARAKTER_LAB_{chosen}_TEK_RAPOR.zip",
    mime="application/zip",
    use_container_width=True,type="primary")

st.caption("Önemli: Adil 20/80 RNG'nin gelecekteki sonuçlarını geçmişten "
           "güvenilir biçimde tahmin edebildiğimiz gösterilmiş değildir. "
           "Sinyal yoksa yeni kupon önerilmez.")
