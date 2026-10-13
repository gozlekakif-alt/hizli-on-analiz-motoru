# -*- coding: utf-8 -*-
"""V22 Streamlit — first two witnessed core events and next third time."""
import streamlit as st
from v21_aile_yasam_dongusu import group_full_days, csv_bytes, clock, HOUR_STARTS
from v22_ucuncu_aile_zaman import evaluate_hour, summarise_rows


@st.cache_data(show_spinner=False,ttl=3600)
def _daily(records):
    date=records[0]["day"]
    day={int(r["pos"]):r for r in records}
    rows=[]
    for start in HOUR_STARTS:
        for k in range(2,11):
            x,_=evaluate_hour(date,day,start,k)
            if x:
                x["Dönem"]="Gün incelemesi"
                rows.append(x)
    return rows


def render_v22(draws):
    st.subheader("🌱 V22 — İki Kez Görülen Ailenin Üçüncü Gelişi")
    st.caption("2–10'lu aileleri gün boyunca takip eder. Bir saatin ilk 6 çekilişinde "
               "tam iki kez görülen aile, ilk 6 bitince sabitlenir. "
               "Son 6 çekiliş ve günün kalanı önceden seçilmiş aile ile test edilir.")
    st.info("Burada **çekirdek** aynı kalır, **eşlikçiler** değişebilir. "
            "İlk iki çıkışın saatleri, aralıkları, yeniden dönüş ve üç eşlikçinin "
            "sonraki tam çıkışlarda ne yaptığı ölçülür. "
            "Sonuçlar bir RNG tahmin avantajı kanıtı değildir.")
    full,missing=group_full_days([
        {**d,"mask":sum(1<<(int(n)-1) for n in d["nums"])} for d in draws
    ])
    if not full:
        st.warning("Tam gün yok.")
        return
    st.caption(f"{len(full)} tam gün; {len(missing)} eksik gün atlandı. "
               "01:02–07:02 arasına çekiliş eklenmez.")
    dates=[d for d,_ in full]
    chosen=st.selectbox("Hangi günün üçüncü aile yolculuğu?",dates,
                        index=len(dates)-1,key="v22_date")
    day=next(rs for date,rs in full if date==chosen)
    if st.button("🔎 Seçilen günü tüm aile boyutlarında tara",key="v22_compute"):
        with st.spinner("İlk iki ve üçüncü tam görünüşler karşılaştırılıyor"):
            rows=_daily(tuple(day))
        st.session_state["v22_day_store"]=(chosen,rows)
    saved=st.session_state.get("v22_day_store")
    if saved is not None and saved[0]==chosen:
        _,rows=saved
        if not rows:
            st.caption("Bu günde ilk altı çekilişte iki tam çıkışı olan aile yok.")
            return
        st.markdown("#### İlk iki → üçüncü çıkış özeti")
        st.dataframe(summarise_rows(rows),hide_index=True,use_container_width=True)
        k=st.select_slider("Aile boyutu",options=list(range(2,11)),value=3,key="v22_family_size")
        subset=[r for r in rows if r["Boyut"]==k]
        st.dataframe(subset,hide_index=True,use_container_width=True)
        st.download_button("⬇️ Bu günün bütün üçüncü aile olaylarını indir",
                           csv_bytes(rows),file_name="V22_UCUNCU_AILE_GUNLUK.csv",
                           mime="text/csv",key="v22_download")
    st.divider()
    st.markdown("#### 72 günlük tam araştırma")
    st.caption("Github Actions: **V22 Aile Ucuncu Gelis Testi**. "
               "72 günün bütün ilk6/son6 ve gün sonuna kadar tekrarları, "
               "eşit zaman aralığı sınaması, çekirdek ve çevre değişimleri "
               "tek ZIP dosyasında sunulur.")
