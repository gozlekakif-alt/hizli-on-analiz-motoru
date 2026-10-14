# -*- coding: utf-8 -*-
"""V29 Streamlit: one-click automatic 72-day temperature dwell -> target20.

No rerun of heavy calculations on day/hour widgets. Cached by uploaded
valid data and model parameters, all results bundled in one ZIP.
"""
from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from collections import defaultdict
import streamlit as st

from v21_aile_yasam_dongusu import group_full_days
from v29_sicaklik_kalis_hedef import run_study


def _encode(draws):
    ordered=sorted(draws,key=lambda r:(r["day"],int(r["pos"])))
    return "\n".join(
        f"{int(r['no'])};{datetime.fromisoformat(str(r['dt'])).strftime('%d.%m.%Y %H:%M')};"+
        ",".join(str(int(n)) for n in r["nums"])
        for r in ordered
    )


@st.cache_data(show_spinner=False,max_entries=2)
def _automatic_v29(text,_callback=None):
    reports,meta,validation,distribution,confidence=run_study(
        text,progress=_callback)
    buf=BytesIO()
    with ZipFile(buf,"w",compression=ZIP_DEFLATED,compresslevel=6) as zip:
        for name,payload in reports.items():
            zip.writestr(name,payload)
    return buf.getvalue(),meta,validation,distribution,confidence


def render_v29(draws):
    st.subheader("🐅 V29 — Sıcaklıkta Kalış → Hedef 20 Sayı")
    st.caption("72 tam günün bütün saatleri otomatik analiz edilir. "
               "80 sayının H6 sonundaki sıcaklıkta kalış süresi, "
               "ısınma/soğuma yönü, geçmiş çıkışları ve "
               "H7–H12'de gerçekten bulunma oranı incelenir.")
    st.info("İlk 24 gün öğrenme, sonraki 12 gün yöntem seçimi, "
            "son 36 gün dondurulmuş kuralın bağımsız testidir. "
            "Her sayının çekilişteki temel olasılığı %25'tir. "
            "Sıcaklık grupları V28'in deneysel altılı gruplarıdır; "
            "eski sistemin bilinmeyen eşikleri olarak sunulmaz.")
    byday=defaultdict(set)
    for d in draws:
        byday[d["day"]].add(int(d["pos"]))
    full=sum(1 for a in byday.values() if len(a)==217 and a==set(range(1,218)))
    ca,cb,cc=st.columns(3)
    ca.metric("Tam gün",full)
    cb.metric("Hedef saat",min(full,72)*18)
    cc.metric("Sayı/saat test",min(max(full-36,0),36)*18*80)
    st.caption("**Her gün ve saat otomatik ilerler; elle gün/saat seçimi yoktur.** "
               "Sonuçlarda 0/10–10/10, 0/20–20/20, 5+, 6+, 7+, 8+, 9+, 10+ "
               "isabetler ve şans karşılaştırması bulunur.")
    if full<72:
        st.warning("Sabit 24+12+36 karşılaştırma için en az 72 tam gün gerekir.")
    if st.button("▶️ V29 OTOMATİK 72 GÜN ARAŞTIRMASINI BAŞLAT",
                 type="primary",use_container_width=True,
                 key="v29_start",disabled=full<72):
        line=st.progress(0,text="80 sayının sıcaklık kimlikleri hazırlanıyor")
        status=st.empty()
        def progress(done,total,stage,day):
            percent=min(100,int(done/max(total,1)*100))
            line.progress(percent,text=f"%{percent} — {stage}")
            status.caption(f"Adım {done}/{total} · Gün: {day or 'Hazırlık'}")
        try:
            raw=_encode(draws)
            with st.spinner("Program tüm günleri ve saatleri otomatik tarıyor..."):
                zipbytes,meta,validation,distribution,ci=_automatic_v29(
                    raw,_callback=progress)
            line.progress(100,text="%100 — Tüm sonuçlar hazır")
            st.session_state["v29_ready"]=(
                zipbytes,meta,validation,distribution,ci)
        except Exception as exc:
            st.error("V29 tamamlanamadı: "+str(exc))
    cached=st.session_state.get("v29_ready")
    if cached:
        archive,meta,validation,dist,ci=cached
        st.success("V29 araştırması tamamlandı; tek ZIP indirilebilir.")
        st.download_button("⬇️ BÜTÜN V29 ANALİZLERİNİ TEK ZIP İNDİR",
                           data=archive,
                           file_name="V29_SICAKLIK_KALIS_HEDEF_72_GUN.zip",
                           mime="application/zip",key="v29_zip")
        st.caption(f"Seçilen yöntem: {meta.get('Dondurulmuş yöntem')} · "
                   f"Son 36 gün {meta.get('Son 36 gün hedef çekilişi')} çekiliş · "
                   f"{meta.get('Test sayı-saat kayıt')} sayı-saat kaydı")
        st.markdown("#### Son 36 gün: gerçek kupon isabetleri")
        st.dataframe(dist,hide_index=True,use_container_width=True)
        st.markdown("#### Rastgele sisteme karşı güven aralıkları")
        st.dataframe(ci,hide_index=True,use_container_width=True)
        with st.expander("Hangi sıcaklık-kalış modeli doğrulamada seçildi?"):
            st.dataframe(validation,hide_index=True,use_container_width=True)
        st.caption("Tek ZIP içinde her sayının kesintisiz sıcak/ılık/soğukta "
                   "kalışı, geçiş yönü, H7–H12'deki gerçek sayısı ve "
                   "10/20'li kupon karşılaştırmaları CSV olarak yer alır.")
    st.caption("Sekmeyi işlem bitene kadar açık tut. "
               "Program veri.txt veya V9–V28 motorlarını değiştirmez.")
