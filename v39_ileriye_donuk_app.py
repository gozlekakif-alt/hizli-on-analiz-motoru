# -*- coding: utf-8 -*-
"""V39: frozen pre-target number picks, multiple specialists and V38 audit."""
import hashlib
import streamlit as st
from v39_onceden_dondurulmus_uzman_paneli import study,ENSEMBLE,BASELINE,MODEL_NAMES


def render_v39(draws):
    st.subheader("🎯 V39 — Çekiliş Öncesi 20 Sayı / 207 Uzman Kalite Denetimi")
    st.info("V38 uzmanlarının tekrarlanan ve sabit ölçümlerini denetler. "
        "**Her gerçek çekilişin sonucuna bakmadan** 8 bağımsız sayı mekaniği, "
        "önceki performansla akort edilen bir 20'li ve rastgele 20'li hazırlar. "
        "Gerçek sonuç geldikten sonra 0–20 isabeti kaydeder ve SONRA öğrenir.")
    st.caption("Bu, 207 tanımlı uzmanın tamamının gerçek öngörü motoruna "
        "dönüştüğü anlamına gelmez. 207 sütunun bir bölümü yalnız geçmişi "
        "anlatır; bunları gelecek sonucu görmüş gibi kullanmıyoruz.")
    groups={}
    for d in draws:groups.setdefault(d["day"],set()).add(int(d["pos"]))
    full=sum(p==set(range(1,218)) for p in groups.values())
    a,b,c=st.columns(3)
    a.metric("Tam 217 çekilişlik gün",full)
    b.metric("Eksik gün",len(groups)-full)
    c.metric("Dondurulan 20'li yöntem",len(MODEL_NAMES))
    partial=st.checkbox("Eksik günleri de dahil et (bilinmeyen sonuçları tahmin diye sayma)",
                        key="v39_partial",value=False)
    quality_file=st.file_uploader("İsteğe bağlı: V38 207 Uzman ZIP raporunu yükle — aynı/sabit sütunları ayıkla",
           type=["zip"],key="v39_quality_zip",
           help="Yüklenmezse mevcut 207 raporunu tekrar üretmez; yalnız önceden dondurulan 20'li testini yapar.")
    rawzip=quality_file.getvalue() if quality_file else None
    sig=hashlib.sha256(str([(d["day"],int(d["pos"]),int(d["no"]),
        sorted(int(n) for n in d["nums"])) for d in draws]).encode()).hexdigest()
    quality_sha=hashlib.sha256(rawzip).hexdigest() if rawzip else ""
    if st.button("▶️ V39 — UZMANLARI KONTROL ET VE 20'LİLERİ GEÇMİŞTEN GELECEĞE SINAVA SOK",
         key="v39_start",type="primary",use_container_width=True,
         disabled=not draws or (full==0 and not partial)):
        bar=st.progress(0,text="Uzman kaynakları ve gerçek sıra doğrulanıyor")
        info=st.empty()
        def progress(i,total,stage,day):
            ratio=min(1.,i/max(1,total))
            bar.progress(ratio,text=f"%{int(ratio*100)} — {stage}")
            info.caption(f"{day}: {i}/{total} gerçek çekiliş")
        try:
            with st.spinner("20'li kuponlar hedef sonucunu görmeden üretiliyor ve test ediliyor..."):
                blob,meta,table,qc=study(draws,partial,rawzip,progress)
                st.session_state["v39_ready"]=(sig,quality_sha,partial,blob,meta,table,qc)
            bar.progress(1.,text="%100 — V39 analizi ve tek ZIP hazır")
        except Exception as exc:
            st.error("V39 analizi durdu: "+str(exc))
    saved=st.session_state.get("v39_ready")
    if not saved:
        st.caption("Tek düğmeyle ilerleyen tarihsel test. 207 uzman için tam "
            "kalite taraması istiyorsan önce V38 ZIP raporunu yukarı yükle.")
        return
    oldsig,oldzip,waspartial,blob,meta,table,qc=saved
    if (oldsig,oldzip,waspartial)!=(sig,quality_sha,partial):
        st.warning("Giriş verileri değişti; görünen ZIP eski koşuya ait olabilir.")
    st.download_button("⬇️ V39 — BÜTÜN DONDURULMUŞ 20'LİLER VE TEST RAPORU TEK ZIP",
        blob,file_name="V39_20_SAYI_GERCEK_ILERI_TEST_TEK_ZIP.zip",
        mime="application/zip",type="primary",use_container_width=True,
        key="v39_download")
    diff=meta["test_ensemble_vs_rng"]
    test={r["method"]:r for r in table if r["phase"]=="TEST"}
    if ENSEMBLE in test and BASELINE in test:
        first=test[ENSEMBLE];rng=test[BASELINE]
        st.markdown("#### Son yarı — gelecek sonucu görmeden hazırlanmış 20 sayılar")
        a,b,c=st.columns(3)
        a.metric("Uzman diyaloğu isabeti",f"{first['avg_hit']:.3f}/20")
        b.metric("Rastgele isabet",f"{rng['avg_hit']:.3f}/20")
        c.metric("16/20 ve üzeri",first["hits_16plus"])
        if diff["mean_hits_ensemble_minus_rng"] is not None:
            st.caption("Uzman – RNG farkı: "+
                str(diff["mean_hits_ensemble_minus_rng"])+" sayı. Gün blok %95 aralığı: "+
                str(diff["day_bootstrap_95"])+".")
    st.dataframe(table,hide_index=True,use_container_width=True)
    if qc:
        st.markdown("#### Gerçek V38 207 uzman kalite kontrolü")
        a,b,c=st.columns(3)
        a.metric("Sabit uzman sütunu",qc["constant"])
        b.metric("Tam tekrar sütunu",qc["duplicate_columns"])
        c.metric("Değişen benzersiz sütun",qc["variable_unique_streams"])
    else:
        st.caption("V38 ZIP verilmediği için bu çalışmada V38'den bağımsız "
                   "sütun tekrar sayısı yeniden hesaplanmadı.")
    st.warning("Bu tarihsel ileri yürütme testidir; tek başına gelecekte "
               "16/20 başarısı garantisi veya gerçek RNG durumuna erişim kanıtı değildir.")
