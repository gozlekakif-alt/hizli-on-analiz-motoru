# -*- coding: utf-8 -*-
"""V23 Streamlit: exact first/second sighting over a WHOLE 217-slot day.

Lightweight interactive family lookup supports no appearance / once / twice /
third; deep day scan runs ONLY when explicitly clicked.
"""
import re
import streamlit as st
from v21_aile_yasam_dongusu import group_full_days,csv_bytes
from v23_aile_ilk_iki_tamgun import (
    query_family_day,scan_day,first_two_positions
)


def render_v23(all_draws):
    st.subheader("🔎 V23 — Ailelerin İlk 2 Tam Çıkışı (217 çekiliş)")
    st.caption("2–10'lu aile; 00:02–23:57 tam gün. "
               "İlk iki çekiliş no/saat, çekiliş ve gerçek dakika aralığı, "
               "ilk/ikinci çevre kadro farkı, üçüncü gerçekleşmişse zamanı.")
    st.info("Gün içi ilk iki görünüş, saatin ilk altısıyla sınırlı değildir. "
            "İlk görünüş varsa fakat ikinci henüz yoksa **ilk 1** olarak gösterilir. "
            "Gelecekteki sonuçlar tahmine eklenmez.")
    normalized=[
        {**r,"mask":sum(1<<(int(n)-1) for n in r["nums"])}
        for r in all_draws
    ]
    full,partial=group_full_days(normalized)
    if not full:
        st.warning("İnceleme için 217 çekilişlik tam gün yok.")
        return
    days=[d for d,_ in full]
    today=st.selectbox("Hangi tam gün?",days,index=len(days)-1,key="v23_day")
    day=next(d for dt,d in full if dt==today)
    st.caption(f"{len(full)} tam gün; eksik olanlar analize dahil edilmez. "
               "01:02–07:02 çekiliş yapılmayan zaman aralığıdır.")
    st.markdown("#### Belirli ailenin gün içindeki ilk iki çıkışı")
    entry=st.text_input("Aile sayılarını gir (2–10 sayı)",
                        value="19-20-23",key="v23_custom_family")
    try:
        family=tuple(int(x) for x in re.findall(r"\d+",entry))
        result=query_family_day(day,family)
    except ValueError as exc:
        st.error("Geçersiz aile: "+str(exc))
        result=None
    if result:
        c1,c2,c3=st.columns(3)
        c1.metric("Tam görünüş",result["Gözlenen çıkış"])
        c2.metric("İlk saat",str(result["İlk saat"] or "Henüz yok"))
        c3.metric("İkinci saat",str(result["İkinci saat"] or "Henüz yok"))
        st.dataframe([result],hide_index=True,use_container_width=True)
        st.download_button("⬇️ Bu ailenin zaman/çevre kaydı",
                           data=csv_bytes([result]),
                           file_name="V23_SECILI_AILE_ILK_IKI.csv",
                           mime="text/csv",key="v23_single_download")
    st.markdown("#### Günün 2'li–10'lu tüm tekrar eden ailelerini tara")
    st.caption("Her gün yüz binlerce veya milyonlarca alt aile olabilir. "
               "Tam tarama tüm ailelerin ilk ve ikinci çıkışlarını istatistikte sayar; "
               "ekranda ailelerin sınırlı sayıda güçlü/erken/geç örneğini gösterir.")
    top=st.slider("Her boyut için örnek aile sayısı",3,20,8,key="v23_top")
    if st.button("🔬 Günlük bütün ilk iki görünüşleri analiz et",key="v23_analyze"):
        with st.spinner("217 gerçek çekilişin tekrarlanan aileleri bulunuyor"):
            summary,gaps,hours,transitions,examples=scan_day(today,day,top)
        st.session_state["v23_result"]=(today,summary,gaps,hours,transitions,examples)
    saved=st.session_state.get("v23_result")
    if saved and saved[0]==today:
        _,summary,gaps,hours,transitions,examples=saved
        st.markdown("#### İlk iki görülüş — aile boyutu özetleri")
        st.dataframe(summary,hide_index=True,use_container_width=True)
        size=st.select_slider("Hangi aile boyutu?",list(range(2,11)),
                              value=4,key="v23_size")
        st.markdown("#### Gerçek ilk ve ikinci saatleri")
        st.dataframe([r for r in examples if r["Boyut"]==size],
                     hide_index=True,use_container_width=True)
        st.markdown("#### İlk ve ikinci arasındaki çekiliş farkları")
        st.dataframe([r for r in gaps if r["Boyut"]==size],
                     hide_index=True,use_container_width=True)
        for title,rows,name in [
            ("Günlük özet",summary,"V23_GUN_OZET.csv"),
            ("İlk/ikinci tüm aralık dağılımı",gaps,"V23_GUN_GAP.csv"),
            ("Gün içindeki saatler",hours,"V23_GUN_SAAT.csv"),
            ("Saatten saate aileler",transitions,"V23_GUN_GECIS.csv"),
            ("İlk/ikinci gerçek aile örnekleri",examples,"V23_GUN_AILELER.csv"),
        ]:
            st.download_button("⬇️ "+title,csv_bytes(rows),name,"text/csv",
                               key="v23_dl_"+name)
    st.markdown("#### 72 günlük büyük rapor")
    st.caption("GitHub Actions içindeki **V23 Aile Ilk Iki Cikis 72 Gun** çalışması "
               "72 tam gün, 1.131 katalog ailesi, ilk/ikinci dakika ve çekiliş farkı, "
               "çekirdek ve çevre değişimlerini tek ZIP içinde verir. "
               "Günlük tam tekrar profilleri toplu hesaplanır; milyonlarca "
               "satırlık tekli aile arşivi oluşturulmaz.")
