# -*- coding: utf-8 -*-
"""V44: one-click research, no false betting edge, 19 candidates and 5 quotas."""
import hashlib
import streamlit as st
from v44_ana_beyin_uzman_elemesi import (study,MASTER,OLD,RNG,CONSENSUS,CANDIDATES)

def render_v44(draws):
    st.subheader("🧠 V44 — Ana Beyin / Ortak Hafıza / Uzman Eleme Merkezi")
    st.info("**Artık uzmanları çoğaltmak yerine eleyeceğiz.** "
       "V39'un 8 gerçek ileri tahmin motoru, V41'in 5 yön uzmanı "
       "ve V42/V43'ün 5 havuz/bant/20-60/oluşum uzmanı "
       "aynı hedefin ÖNCESİNDE 20 sayı seçiyor. "
       "Bir de sabit ve ayar yapılmamış 19. ortak-konsensüs adayı var.")
    st.caption("18 tam gün kurulum → 18 tam gün uzman seçimi → son 36 tam gün "
       "kilitli test. Uzman seçimi testte güncellenmez. "
       "19 aday için gün düzeyinde çoklu test düzeltmesi ve 7–12 kontrolü var. "
       "Hiç uzman geçemezse ana beyin sadece rastgele **araştırma referansı** üretir.")
    byday={}
    for r in draws:
        byday.setdefault(r["day"],set()).add(int(r["pos"]))
    complete=sum(x==set(range(1,218)) for x in byday.values())
    a,b,c=st.columns(3)
    a.metric("Tam gün 217/217",complete)
    b.metric("Gerçek çekiliş",len(draws))
    c.metric("Araştırma adayları",len(CANDIDATES))
    partial=st.checkbox("Eksik günleri de işle (ilk 36 günün sınırı sabit)",
                        key="v44_partial",value=False)
    ident=hashlib.sha256(str([(r["day"],int(r["pos"]),int(r["no"]),
         sorted(r["nums"])) for r in draws]).encode()).hexdigest()
    if st.button("▶️ V44 — BÜTÜN MOTORLARI TEK BEYİNDE SINAVDAN GEÇİR",
                 key="v44_go",type="primary",use_container_width=True,
                 disabled=(complete<8 and not partial) or not draws):
        meter=st.progress(0,text="Çekiliş öncesi uzman listeleri kuruluyor")
        line=st.empty()
        def progress(i,total,message,day):
            v=min(1.,i/max(1,total))
            meter.progress(v,text=f"%{v*100:.0f} {message}")
            line.caption(f"{day} — {i}/{total}")
        try:
            with st.spinner("72 gün, 19 uzman, 5 havuz kota ve 20'li gerçek test..."):
                content,meta,summ,qsum,gates=study(draws,
                           include_partial=partial,progress=progress)
            st.session_state["v44_result"]=dict(hash=ident,partial=partial,
                         content=content,meta=meta,summ=summ,qsum=qsum,gates=gates)
            meter.progress(1.,text="V44 ortak beyin testi tamamlandı")
        except Exception as exc:
            st.error("V44 analizi tamamlanamadı: "+str(exc))
    report=st.session_state.get("v44_result")
    if not report:
        st.caption("Tek ZIP içinde her hedef için uzmanların 20'li listeleri, "
           "eğitimden ayrılmış uzman elemesi, 36 gün kor test, 5 havuz "
           "kotaları, rastgele matematiksel referans ve gün-blok karşılaştırma.")
        return
    if report["hash"]!=ident or report["partial"]!=partial:
        st.warning("Veri kaynağı değişti. Güncel sonuç için V44'ü yeniden çalıştır.")
    info=report["meta"]
    st.download_button("⬇️ V44 ANA BEYİN — TÜM KARARLAR VE SONUÇLAR TEK ZIP",
       data=report["content"],file_name="V44_ANA_BEYIN_ELEME_72_GUN_TEK_ZIP.zip",
       mime="application/zip",key="v44_download",type="primary",
       use_container_width=True)
    approved=info["accepted"]
    if approved:
        st.success(f"Önceden kilitli eleme kuralını geçen {len(approved)} uzman: "
                   +", ".join(approved))
    else:
        st.warning("**Üstünlük kanıtlanmış uzman yok.** "
           "Ana beynin ürettiği 20'li bu durumda **rastgele kontrol listesidir**, "
           "kazanç veya kupon tavsiyesi değildir.")
    test=[r for r in report["summ"] if r["donem"]=="KOR_TEST"
          and r["pencere"]=="TUM" and r["motor"] in
          (MASTER,OLD,RNG,CONSENSUS)]
    st.markdown("#### Son 36 gün — gerçekten önceden hazırlanmış 20'li listeler")
    if test:
        st.dataframe(test,hide_index=True,use_container_width=True)
    st.markdown("#### Beş hareketli havuz: kota ayrı, sayı kimliği ayrı")
    qtest=[x for x in report["qsum"] if x["donem"]=="KOR_TEST"
           and x["pencere"]=="TUM"]
    st.dataframe(qtest,hide_index=True,use_container_width=True)
    with st.expander("19 araştırma uzmanının validasyon sınavı"):
        st.dataframe(report["gates"],hide_index=True,use_container_width=True)
    with st.expander("Günün 7.–12. çekilişleri ayrı test"):
        st.dataframe([x for x in report["summ"] if x["donem"]=="KOR_TEST"
            and x["pencere"]=="7_12" and x["motor"] in
            (MASTER,OLD,RNG,CONSENSUS)],hide_index=True,use_container_width=True)
    with st.expander("Eşlenik 36 günlük belirsizlik hesabı"):
        st.json(info["paired_36_day_comparisons"])
    with st.expander("Kaynak sonrası araştırma listesi"):
        snap=info["source_next_snapshot"]
        st.markdown(f"Kaynağın sonraki kayıt slotu: "
             f"**{snap['next_source_slot_date']} {snap['next_source_slot_time']}**")
        st.code(snap["research_20"])
        st.warning("Bu takvim saati bugün için gelecekte olmayabilir. "
                   "Gerçek zamanlı çekiliş bağlantısı veya kazanç kanıtı değildir.")
    st.caption("Yeni günleri eklemek, ilk 18/sonraki 18 uzman eleme "
               "penceresini kaydırmaz. 207 V38 analiz sütunu, "
               "207 bağımsız sayı tahmin modeli olarak etiketlenmez.")
