# -*- coding: utf-8 -*-
"""V41 Streamlit: directional movement learning with real 20/80 holdout."""
import hashlib
import streamlit as st

from v41_derin_yon_gecis_motoru import (study,SIX,ENSEMBLE,CONTROL_RNG,
   CONTROL_V39,FROZEN,ALL_METHODS)


def render_v41(draws):
    st.subheader("↗️↘️ V41 — Yön Hızı, Ters Dönüş ve Aile İvmesi")
    st.info("6 sıcaklık havuzunun içindeki sayıların **yön devamı, ters "
      "dönüşü, basamak sıçraması, ivmesi, kalış süresi ve aile eşliği** "
      "üzerinden her çekilişten ÖNCE 20'li listeler üretip gerçek çıkan "
      "20 ile karşılaştırır. Yalnız sonuç görülmeden bilinen geçmiş kullanılır.")
    st.caption("Ana test: Önceden belirlenmiş YÖN BİRLEŞİMİ ile rastgele 20 sayının "
       "son 36 tam gündeki isabet farkı. V39'un önceki 20'lisi ve "
       "ilk 36 gün eğitiminde dondurulmuş yön modeli de ayrı kontrol.")
    days={}
    for r in draws:days.setdefault(r["day"],set()).add(int(r["pos"]))
    full=sum(s==set(range(1,218)) for s in days.values())
    a,b,c=st.columns(3)
    a.metric("Tam 217/217 gün",full)
    b.metric("Yön uzmanı + kontroller",len(ALL_METHODS))
    c.metric("6 ısı havuzu",len(SIX))
    partial=st.checkbox("Eksik günleri de işle (eksik çekiliş uydurma)",
          key="v41_partial",value=False)
    sha=hashlib.sha256(str([(r["day"],int(r["pos"]),int(r["no"]),
         sorted(r["nums"])) for r in draws]).encode()).hexdigest()
    if st.button("▶️ V41 — YÖN HIZI, İVME, TERS DÖNÜŞ VE AİLELERİ TEST ET",
                 key="v41_go",type="primary",use_container_width=True,
                 disabled=not draws or (full==0 and not partial)):
        bar=st.progress(0,text="Çekiliş öncesi yön karakterleri hazırlanıyor")
        status=st.empty()
        def progress(i,total,stage,day):
            pct=min(1.,i/max(1,total))
            bar.progress(pct,text=f"%{pct*100:.0f} {stage}")
            status.caption(f"{day} • {i}/{total} gerçek çekiliş")
        with st.spinner("72 günlük bütün yön hareketleri ve 20'li ileri testleri işleniyor..."):
            try:
                output,meta,summaries,brier,comparison,groups=study(
                    draws,include_partial=partial,progress=progress)
                st.session_state["v41_result"]={
                   "sha":sha,"partial":partial,"output":output,
                   "meta":meta,"summaries":summaries,"brier":brier,
                   "comparison":comparison,"groups":groups}
                bar.progress(1.0,text="V41 analiz raporu hazır")
            except Exception as exc:st.error("V41 çalışamadı: "+str(exc))
    saved=st.session_state.get("v41_result")
    if not saved:
        st.caption("Tek tuşla 6 sıcaklık havuzu × yön hareketi × aile; "
                   "tüm 20'li listeler, yön yaşam kartları ve test sonuçları tek ZIP.")
        return
    if saved["sha"]!=sha or saved["partial"]!=partial:
        st.warning("Giriş geçmişi değişti; son sonuç için yeniden çalıştır.")
    meta=saved["meta"]
    st.success(f"{meta['predicted_draws']} geçmişten geleceğe hedef incelendi; "
               f"{meta['number_character_cards']} sayı-yön kartı işlendi.")
    st.download_button("⬇️ V41 YÖN HAREKETLERİ VE TÜM 20'Lİ TESTLER TEK ZIP",
           data=saved["output"],file_name="V41_DERIN_YON_HIZ_IVME_AILE_TEK_ZIP.zip",
           mime="application/zip",key="v41_dl",type="primary",
           use_container_width=True)
    test={r["motor"]:r for r in saved["summaries"] if r["donem"]=="TEST"}
    if ENSEMBLE in test:
        m=test[ENSEMBLE];rng=test[CONTROL_RNG]
        v39=test[CONTROL_V39]
        st.markdown("#### Son 36 gün — gerçek çıkan20 öncesinde hazırlanmış listeler")
        a,b,c=st.columns(3)
        a.metric("Yön birleşimi",f"{m['ortalama_isabet']:.3f}/20")
        b.metric("Rastgele 20",f"{rng['ortalama_isabet']:.3f}/20")
        c.metric("Önceki V39",f"{v39['ortalama_isabet']:.3f}/20")
        st.caption("Yön birleşiminin en iyi tek çekilişi: "+
           str(m["en_yuksek_isabet"])+"/20; 16/20 ve üzeri: "+
           str(m["isabet_16_ve_ustu"])+".")
    st.dataframe(saved["summaries"],hide_index=True,use_container_width=True)
    st.markdown("#### Paired day-block comparisons")
    st.json({k:v for k,v in saved["comparison"].items() if k.startswith("TEST__")})
    with st.expander("Yön, ivme, kalış ve aile alt dalları"):
        dimension=st.selectbox("Araştırma dalı",
            ["HAVUZ","YON","YON_DEVAM","YON_HIZ","YON_IVME",
              "YON_KALIS","YON_AILE","YON_BANT","AILE_ESYON"],key="v41_dimension")
        rows=[r for r in saved["groups"] if r["donem"]=="TEST"
              and r["boyut"]==dimension]
        st.dataframe(rows,hide_index=True,use_container_width=True)
    with st.expander("Olasılık kalibrasyonu"):
        st.dataframe(saved["brier"],hide_index=True,use_container_width=True)
    st.caption("Birden çok sinyali denemek tesadüfi yüksek isabetler "
      "üretebilir. Esas karar, son 36 günde RNG kontrolü ve yeni "
      "gelecek günler karşısında tutarlı üstünlük olup olmadığıdır.")
