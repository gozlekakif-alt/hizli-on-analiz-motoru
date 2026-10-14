# -*- coding: utf-8 -*-
"""V37C Streamlit: 80-ball shared memory; full 2/3-draw fragmented quartet
formation and pre-registered 2048-quartet long-life sample in one click."""
import hashlib
import tempfile
from pathlib import Path
import streamlit as st

from v37_ortak_hafiza import replay
from v37c_parcali_aile_hayati import run,export,SAMPLE,UNIVERSE


def render_v37c(draws):
    st.subheader("🧩 V37C — Sessiz ve Parçalı Dörtlü Ailelerin Yaşamı")
    st.info("Aynı çekilişte **4/4 hiç birleşmeyen**, fakat üyeleri farklı gerçek "
            "çekilişlerde ortaya çıkan aileleri inceler. 1+3, 2+2, 3+1 ve "
            "2+1+1 yollarını, uzun sessizlikleri, geri canlanmayı ve sayıların "
            "sıcaklık yönüyle bağlantılarını ortak V37 hafızasından okur.")
    st.caption("**Tam sayım:** 80 sayıdan bütün dört üyeli ailelerin iki ve üç "
       "ardışık çekilişlik parçalı oluşumları, kombinatorik hesapla. "
       "**Uzun aile yaşamı:** sonuçlardan bağımsız seçilmiş 2048 dörtlü üzerinden "
       "12 çekilişlik ayrıntılı hafıza. Bu iki veri türü birbirine karıştırılmaz.")
    byday={}
    for d in draws:byday.setdefault(d["day"],set()).add(int(d["pos"]))
    full=sum(v==set(range(1,218)) for v in byday.values())
    a,b,c=st.columns(3)
    a.metric("Tam gün",full)
    b.metric("Olası dörtlü",f"{UNIVERSE:,}")
    c.metric("Uzun yaşam örneklemi",SAMPLE)
    partial=st.checkbox("Eksik günleri dahil et; eksik yerde parçalı yolu kes",
                        key="v37c_partial",value=False)
    sorted_input=sorted(draws,key=lambda d:(d["day"],int(d["pos"])))
    source_sha=hashlib.sha256(str([(d["day"],int(d["pos"]),int(d["no"]),
                               sorted(d["nums"])) for d in sorted_input]).encode()).hexdigest()
    state_key=f"v37c_state_{partial}"
    if st.button("▶️ V37C — SESSİZ + PARÇALI AİLELERİ ORTAK HAFIZADA TARA",
                 key="v37c_run",type="primary",use_container_width=True,
                 disabled=not sorted_input or (full==0 and not partial)):
        bar=st.progress(0,text="Ortak hafızaya bağlanılıyor")
        progress_text=st.empty()
        def notify(i,total,stage,day):
            bar.progress(min(1.0,i/max(1,total)),text=stage)
            progress_text.caption(f"{day} • {i}/{total}")
        existing=st.session_state.get(f"v37_hafiza_state_{partial}")
        if existing and existing.get("dir"):
            folder=Path(existing["dir"])
        else:
            folder=Path(tempfile.mkdtemp(prefix="v37c_ortak_"))
            st.session_state[f"v37_hafiza_state_{partial}"]={
                "dir":str(folder),"summary":None,"zip":None}
        folder.mkdir(parents=True,exist_ok=True)
        db=folder/"hafiza.sqlite3"
        zipfile=folder/"V37C_PARCALI_DORTLU_AILE_YASAM_TEK_ZIP.zip"
        with st.spinner("72 günlük parçalı aile yolları ve 2048 aile yaşamı taranıyor..."):
            try:
                base=replay(sorted_input,db,include_partial=partial,progress=notify)
                stats=run(db,progress=notify)
                result=export(db,zipfile)
                st.session_state[state_key]={
                    "sha":source_sha,"core":base,"stats":stats,
                    "periods":result,"archive":str(zipfile)}
                bar.progress(1.0,text="V37C raporu tamamlandı")
            except Exception as exc:
                st.error(f"V37C analiz hatası: {exc}")
                st.caption("Kaynak geçmiş değiştiyse önce yeni boş V37 hafızası "
                           "başlat. Veritabanı eski geçmişi sessizce değiştirmez.")
    saved=st.session_state.get(state_key)
    if not saved:
        st.caption("Tek tuş hem ortak SQLite hafızasını doğrular hem yeni "
                   "dörtlü yaşam motorunu çalıştırır. Tam tarama uzun sürebilir; "
                   "GitHub Actions raporu alternatif olarak otomatik hazırlar.")
        return
    if saved["sha"]!=source_sha:
        st.warning("Veri değişti; güncel sonuç için yeniden çalıştır.")
    info=saved["stats"]
    x,y,z=st.columns(3)
    x.metric("İşlenen gerçek çekiliş",info["completed_draws"])
    y.metric("İncelenen sabit aile",info["catalogue_sample_size"])
    z.metric("Kaydedilen olay örnekleri",info["bounded_evidence_events"])
    st.download_button("⬇️ V37C — PARÇALI DÖRTLÜ AİLELER TEK ZIP",
        data=Path(saved["archive"]).read_bytes(),
        file_name="V37C_PARCALI_DORTLU_AILE_YASAM_TEK_ZIP.zip",
        mime="application/zip",type="primary",use_container_width=True,
        key="v37c_download")
    st.markdown("#### İlk yarı / ikinci yarı")
    for label,info in saved["periods"].items():
        with st.expander(label,expanded=True):
            st.json(info)
    st.caption("**Kesinlik:** 2 ve 3 çekilişlik parçalı oluşumların tamamı "
       "sayılır. 12 çekilişlik uzun ömür ve aile kimliği verileri ise 2048 "
       "ön kayıtlı aile örneklemine aittir. Bir sonraki çekilişi daha iyi "
       "bileceğimizi henüz göstermiyor.")
