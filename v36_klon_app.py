# -*- coding: utf-8 -*-
"""V36: draw-by-draw autonomous clone and real-stream motor reservoirs UI."""
import hashlib
import streamlit as st
from v36_rng_davranis_klonu import run


def render_v36(draws):
    st.subheader("🧠 V36 — 80 Sayı / Her Çekilişte Kendini Akort Eden Davranış Klonu")
    st.info("İki ayrı kol birlikte ilerler: **GERÇEK** 20 sayı ile **KLON** kendi "
            "ürettiği 20 sayıyla bir sonraki adıma geçer. Her çekilişte her "
            "haznenin sayıları, **girenler ve çıkanlar** ayrıca kaydedilir.")
    st.caption("Bu laboratuvar bilinmeyen RNG algoritmasını veya tohumunu çözdüğünü "
        "iddia etmez. Hedefimiz gözlenebilir karakterleri adım adım yeniden üretmek, "
        "farkları ölçmek ve bir sonraki gerçek sonuçtan SONRA klonu akort etmektir.")
    byday={}
    for d in draws:byday.setdefault(d["day"],set()).add(int(d["pos"]))
    full=sum(1 for p in byday.values() if p==set(range(1,218)))
    a,b,c=st.columns(3)
    a.metric("217/217 tam gün",full)
    b.metric("Eksik gün",len(byday)-full)
    c.metric("Kayıtlı gerçek çekiliş",len(draws))
    partial=st.checkbox("Eksik günleri de incele (eksik yerde hafızayı kes)",
                        value=False,key="v36_partial")
    source_hash=hashlib.sha256(str([(d["no"],d["day"],d["pos"],sorted(d["nums"]))
                                    for d in draws]).encode()).hexdigest()
    if st.button("▶️ V36 — BÜTÜN UZMAN MOTORLARI VE KLONU TEK TUŞLA ÇALIŞTIR",
                 type="primary",use_container_width=True,
                 disabled=not draws or (full==0 and not partial),key="v36_start"):
        bar=st.progress(0,text="Hazneler hazırlanıyor")
        status=st.empty()
        def on_progress(i,total,stage,day):
            k=min(1.0,i/max(1,total))
            bar.progress(k,text=f"%{100*k:.0f} — {stage}")
            status.caption(f"{day}: tamamlanan gün {i}/{total}")
        with st.spinner("80 sayının bütün uzman dalları her çekilişte iki kolda oynatılıyor..."):
            try:
                result=run(draws,include_partial=partial,progress=on_progress)
                st.session_state["v36_lab"]=(source_hash,partial,*result)
                bar.progress(1.0,text="%100 — Klon raporları tamamlandı")
            except Exception as exc:
                st.error(f"V36 işlemi durdu: {exc}")
    saved=st.session_state.get("v36_lab")
    if not saved:
        st.caption("Başlat düğmesine basınca her adımın hazne geçmişi ve iki "
                   "kolun karşılaştırması tek ZIP olarak hazırlanır.")
        return
    oldhash,oldpartial,blob,meta,daily,calib,motor_counts=saved
    if oldhash!=source_hash or oldpartial!=partial:
        st.warning("Yeni veri veya seçenekler var. Güncel sonuç için tekrar başlat.")
    st.success(f"{meta['cekilis']} gerçek çekiliş ve {meta['80_sayi_kaydi']} "
               f"sayı-karakter kaydı işlendi.")
    st.download_button("⬇️ V36 BÜTÜN KLON VE MOTOR ANALİZLERİNİ TEK ZIP İNDİR",
        data=blob,file_name="V36_80_SAYI_HER_CEKILIS_KLON_TEK_ZIP.zip",
        mime="application/zip",type="primary",use_container_width=True,key="v36_zip")
    x,y,z=st.columns(3)
    x.metric("Ayrı uzman motor grubu",len(meta["motor_gruplari"]))
    y.metric("Öğrenen kalibrasyon dalı",len(meta["kalibrasyon_dallari"]))
    z.metric("Motor alt-haznesi",meta["motor_alt_hazne_sayisi"])
    test=meta["test"]
    st.markdown("#### Sonraki günlerdeki gerçek çekilişlere karşı")
    if test["gercek_cekilis"]:
        a,b,c=st.columns(3)
        a.metric("Özerk klon 20 ortak",test["ortalama_klon_ortak_sayi"])
        b.metric("Gerçek durumdan klon 20 ortak",test["ortalama_durum_ortak_sayi"])
        c.metric("Eşit şanslı RNG 20 ortak",test["ortalama_rastgele_ortak_sayi"])
    st.caption("20 sayıdan 20 sayı ile ortalama ortak sayı, bağımsız adil çekilişte "
               "5'tir. Gerçek modele üstünlük iddiası için sonraki bağımsız günlerde "
               "kalıcı avantaj gerekir. Test boyunca model yalnız çekiliş "
               "SONUCU görüldükten sonra öğrenmeye devam eder.")
    st.markdown("#### Gün gün klonun gerçek oyuna yakınlığı")
    st.dataframe(daily,hide_index=True,use_container_width=True)
    with st.expander("Ayrı uzman haznelerinin giriş/çıkış toplamları"):
        st.dataframe(motor_counts[:500],hide_index=True,use_container_width=True)
        st.caption("Haznelerin her gerçek çekilişteki tek tek sayı listeleri ZIP'in "
                   "02 dosyasındadır; bu tablo yalnız ilk 500 toplam satırı gösterir.")
    with st.expander("13 kalibrasyon dalının bütün ayarları"):
        st.dataframe(calib,hide_index=True,use_container_width=True)
    with st.expander("Motor sınırları, öğrenme kuralları ve veri güvenliği"):
        st.json({"versiyon":meta["versiyon"],"motorlar":meta["motor_gruplari"],
                 "kalibrasyon":meta["kalibrasyon_dallari"],
                 "test_ayrac":meta["egitim_test_siniri"],
                 "kaynak_uyarilari":meta["kaynak_uyarisi"]})
    st.caption("Eski V9–V35 dosyaları değiştirilmez. Kaynak veri.txt güncellendiğinde "
               "yeniden başlatma deterministik olarak eski adımları da oynatır. "
               "Kalıcı dışa aktarım tek ZIP'tir; oturum belleği kalıcı değildir.")
