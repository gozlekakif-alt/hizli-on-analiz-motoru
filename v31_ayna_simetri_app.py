# -*- coding: utf-8 -*-
"""V31 Streamlit on-demand 72 day 40.5 symmetry / mirror band / mirrored-number research."""
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import streamlit as st

from v31_ayna_simetri import run_study


def encode_draws(draws):
    ordered=sorted(draws,key=lambda r:(r["day"],int(r["pos"])))
    return "\n".join(
        f"{int(r['no'])};{datetime.fromisoformat(str(r['dt'])).strftime('%d.%m.%Y %H:%M')};"+
        ",".join(str(int(n)) for n in r["nums"])
        for r in ordered
    )


@st.cache_data(show_spinner=False,max_entries=2)
def _v31_run(text,_progress=None):
    reports,meta,dist,confidence,null,pairs=run_study(text,progress=_progress)
    output=BytesIO()
    with ZipFile(output,"w",compression=ZIP_DEFLATED,compresslevel=6) as z:
        for name,blob in reports.items():
            z.writestr(name,blob)
    return output.getvalue(),meta,dist,confidence,null,pairs


def render_v31(draws):
    st.subheader("🪞 V31 — Ayna Bant Kardeşliği, 40'ın Altı ve Üstü")
    st.info(
        "Sekiz bant arasında 4 ayna kardeşlik: **1–10 ↔ 71–80, "
        "11–20 ↔ 61–70, 21–30 ↔ 51–60, 31–40 ↔ 41–50**. "
        "Ayrıca 40 sayı aynası: 1↔80, 2↔79, … 40↔41."
    )
    st.caption(
        "1–40 ve 41–80 aynı çekilişte zorunlu olarak birbirini tamamlar: "
        "toplamda 20 sayı. Bu mekanik ters hareket ile sonraki çekilişleri "
        "haber veren gerçek bir ilişkiyi ayrı ayrı sınayacağız. "
        "Bantların sıcaklık, ısınma/soğuma, +/− salınımları ve 0–6 çekiliş "
        "gecikmeleri de raporlanır."
    )
    dates=defaultdict(set)
    for d in draws:dates[d["day"]].add(int(d["pos"]))
    full=sum(len(s)==217 and s==set(range(1,218)) for s in dates.values())
    a,b,c=st.columns(3)
    a.metric("Tam gün",full)
    b.metric("Ayna bant",4)
    c.metric("Tek sayı aynası",40)
    st.caption(
        "24 gün öğrenme + 12 gün model seçimi + son36 gün geriye dönük "
        "zaman sıralı sınama. **Bu son 36 gün V30'da önceden görüldü; "
        "yeni ve bağımsız doğrulama yerine geçmez.**"
    )
    if full<72:
        st.warning("Bunun için en az 72 tam gün (217 çekiliş) gerekiyor.")
    if st.button("▶️ 72 GÜN AYNA / SİMETRİ ANALİZİNİ OTOMATİK BAŞLAT",
                 disabled=full<72,key="v31_run",use_container_width=True,
                 type="primary"):
        progress=st.progress(0,text="40.5 eksenindeki ayna analizine başlanıyor")
        status=st.empty()
        def notify(done,total,stage,day):
            pct=min(100,int(100*done/max(1,total)))
            progress.progress(pct,text=f"%{pct} — {stage}")
            status.caption(f"Adım {done}/{total} · Gün: {day or 'Hazırlık'}")
        with st.spinner("Bütün günler ve bant kardeşleri sırayla işleniyor..."):
            try:
                output=_v31_run(encode_draws(draws),_progress=notify)
                st.session_state["v31_ready"]=output
                progress.progress(100,text="%100 — AYNA RAPORU HAZIR")
            except Exception as exc:
                st.error(f"V31 çalışması tamamlanamadı: {exc}")
    saved=st.session_state.get("v31_ready")
    if saved:
        zipped,meta,dist,confidence,null,pairs=saved
        st.success("V31: 72 günlük ayna raporu tek dosya olarak hazır.")
        st.download_button(
            "⬇️ V31 AYNA / SİMETRİ TAM ANALİZİ TEK ZIP İNDİR",
            data=zipped,
            file_name="V31_AYNA_SIMETRI_BANT_KARDESLIK_TEK_RAPOR.zip",
            mime="application/zip",
            key="v31_download",
            use_container_width=True
        )
        st.caption(
            f"Seçilen keşifsel model: {meta['Seçilen']} · "
            f"Son 36 gün hedef çekiliş: {meta['Hedef çekiliş']}. "
            "ZIP'te 00_TEK_RAPOR_AYNA_SIMETRI.txt öncelikli özet."
        )
        st.markdown("#### Rastgele kontrole göre 40 aynalı sayı ilişkisi")
        st.dataframe(null,hide_index=True,use_container_width=True)
        st.markdown("#### 10'lu ve 20'li kupon gerçek isabetleri")
        st.dataframe(dist,hide_index=True,use_container_width=True)
        st.markdown("#### Bağımsız seçime karşı belirsizlik")
        st.dataframe(confidence,hide_index=True,use_container_width=True)
        with st.expander("Ayna bant kardeşlikleri: tüm saatler"):
            st.dataframe(pairs,hide_index=True,use_container_width=True)
    st.caption("Analiz sadece düğmeye basınca çalışır. "
               "veri.txt, diğer motorlar ve eski raporlar değişmez.")
