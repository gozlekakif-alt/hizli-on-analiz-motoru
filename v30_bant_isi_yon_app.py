# -*- coding: utf-8 -*-
"""V30 Streamlit: ONE BUTTON, 72 days, one ZIP with human-readable report."""
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
import streamlit as st

from v30_bant_isi_yon import run_study


def source_text(draws):
    data=sorted(draws,key=lambda d:(d["day"],int(d["pos"])))
    return "\n".join(
        f"{int(x['no'])};{datetime.fromisoformat(str(x['dt'])).strftime('%d.%m.%Y %H:%M')};"+
        ",".join(str(int(n)) for n in x["nums"])
        for x in data
    )


@st.cache_data(show_spinner=False,max_entries=2)
def _v30_full_scan(text,_progress=None):
    reports,meta,validation,distribution,confidence,rates,perm=run_study(
        text,progress=_progress,band_null_reps=199)
    zipfile=BytesIO()
    with ZipFile(zipfile,"w",compression=ZIP_DEFLATED,compresslevel=6) as z:
        for name,payload in reports.items():
            z.writestr(name,payload)
    return zipfile.getvalue(),meta,validation,distribution,confidence,rates,perm


def render_v30(draws):
    st.subheader("🐅 V30 — 8 Bant × 6 Sıcaklık × Hareket Yönü")
    st.info(
        "Sabit bantlar: 1–10, 11–20, …, 71–80. "
        "Hareketli sıcaklık basamakları: soğuk, soğuğa yakın, orta, ılık, "
        "sıcağa yakın, sıcak. Her sayı H1–H6'daki **ısı puanı artışına "
        "veya düşüşüne** göre ısınan/soğuyan ayrılır; tam sabit kalanlar "
        "kendi grubunda tutulur."
    )
    st.caption(
        "Her sayının adil çekiliş olasılığı %25, her 10'luk bandın "
        "beklenen katkısı 2,5 sayıdır. Önceden bilinen ilk 6 çekilişten "
        "sonra 10'lu ve 20'li tahminler kilitlenir. "
        "24 gün öğrenme + 12 gün model seçimi + son36 gün bağımsız sınama."
    )
    days=defaultdict(set)
    for d in draws:
        days[d["day"]].add(int(d["pos"]))
    full=sum(1 for slots in days.values() if len(slots)==217
             and slots==set(range(1,218)))
    c1,c2,c3=st.columns(3)
    c1.metric("217 çekilişli gün",full)
    c2.metric("8 sayı bandı",8)
    c3.metric("6 × 2 hareket",12)
    st.caption("Tamamen hareketsiz kalan sayılar 12 gruba zorla sokulmaz; "
               "ayrı tutulur. Bant +/− dalgası ilk 6 çekilişte "
               "2,5 sayılık ortalamaya göre ölçülür.")
    if full<72:
        st.warning("Sabit ve dürüst 24+12+36 test için en az 72 TAM gün "
                   "gerekiyor. Mevcut günler tamamlanınca düğme açılır.")

    if st.button("▶️ V30 — TÜM GÜNLERİ VE BANTLARI OTOMATİK TARA",
                 key="v30_go",use_container_width=True,type="primary",
                 disabled=full<72):
        bar=st.progress(0,text="72 günlük tarama hazırlanıyor")
        caption=st.empty()
        def notify(done,total,stage,day):
            pc=max(0,min(100,round(100*done/max(1,total))))
            bar.progress(pc,text=f"%{pc} — {stage}")
            caption.caption(f"Gün: {day or 'Hazırlık'} · {done}/{total}")
        with st.spinner("80 sayı × 8 bant × sıcaklık ve yön analiz ediliyor. Sekmeyi açık tut."):
            try:
                zipped,meta,validation,distribution,ci,rates,perm=_v30_full_scan(
                    source_text(draws),_progress=notify)
                st.session_state["v30_result"]=(
                    zipped,meta,validation,distribution,ci,rates,perm)
                bar.progress(100,text="%100 — TEK ZIP RAPOR HAZIR")
                caption.success("72 günlük otomatik analiz tamamlandı.")
            except Exception as ex:
                st.error("V30 çalışması tamamlanamadı: "+str(ex))
    found=st.session_state.get("v30_result")
    if found:
        payload,meta,validation,dist,ci,rates,perm=found
        st.success(f"V30 araştırması hazır. Seçilen yöntem: {meta['Seçilen model']}")
        st.download_button(
            "⬇️ V30 TEK RAPOR — TÜM ANALİZLERİ ZIP İNDİR",
            data=payload,
            file_name="V30_BANT_ISI_YON_TEK_RAPOR.zip",
            mime="application/zip",
            key="v30_zip_download",
            use_container_width=True
        )
        st.caption("ZIP'in ilk dosyası 00_TEK_RAPOR_OZET.txt; "
                   "ayrıntılar numaralandırılmış CSV dosyalarında.")
        st.markdown("#### 10'lu ve 20'li gerçek isabetler — son 36 gün")
        st.dataframe(dist,hide_index=True,use_container_width=True)
        st.markdown("#### Güven aralığı — rastgele seçim kıyası")
        st.dataframe(ci,hide_index=True,use_container_width=True)
        with st.expander("8 bant × 6 sıcaklık × yön: hedefte görünme oranları"):
            st.dataframe(rates,hide_index=True,use_container_width=True)
        with st.expander("Bandlara yerleşim tesadüfi mi? Sayı-kimliği permütasyon testi"):
            st.dataframe(perm,hide_index=True,use_container_width=True)
        with st.expander("İlk 24 gün eğitim / 12 gün model seçme kararı"):
            st.dataframe(validation,hide_index=True,use_container_width=True)
    st.caption("Analiz tek düğmeyle başlar; veri.txt ve V9–V29 motorları "
               "değişmez. İşlem sırasında bu sekmeyi açık tut.")
