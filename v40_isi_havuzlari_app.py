# -*- coding: utf-8 -*-
"""V40 six heat reservoirs / before-to-after direction Streamlit dashboard."""
import hashlib
import streamlit as st
from v40_alti_isi_yon_havuzlari import study,SIX,SIZES


def render_v40(draws):
    st.subheader("🌡️ V40 — 6 Isı Havuzu: 80 Sayının Yön ve Aile Yolculuğu")
    st.info("**Kupon üreticisi değil, araştırma motoru.** Her çekilişin sonucu "
        "bilinmeden önce 80 sayının soğuk / soğuğa yakın / orta / ılık / "
        "sıcağa yakın / sıcak hazneleri, hangi yöne ilerledikleri ve hangi "
        "aile ve bant karakterini taşıdıkları kaydedilir. Sonra gerçek çıkan "
        "20 içinden her havuzun kaç sayı verdiği ölçülür.")
    st.caption("Havuz kapasiteleri 13–13–14–14–13–13 = 80. "
        "Adil bağımsız çekilişte her havuzdaki tek sayının sonraki "
        "20'ye girme olasılığı %25'tir. Isı karakterinin üstünlüğü "
        "önceden değil, gerçek sonraki çekilişte sınanır.")
    byday={}
    for d in draws:byday.setdefault(d["day"],set()).add(int(d["pos"]))
    full=sum(s==set(range(1,218)) for s in byday.values())
    a,b,c=st.columns(3)
    a.metric("217/217 tam gün",full)
    b.metric("Gerçek çekiliş",len(draws))
    c.metric("Isı havuzu",len(SIX))
    partial=st.checkbox("Eksik günleri de işle; eksik sonuçlardan yokluk uydurma",
                        key="v40_partial",value=False)
    source_sha=hashlib.sha256(str([(d["day"],int(d["pos"]),int(d["no"]),
                                   sorted(d["nums"])) for d in draws]).encode()).hexdigest()
    if st.button("▶️ V40 — TÜM ISI/YÖN/AİLE/BANT HAZNELERİNİ TEK TUŞLA İNCELE",
                 key="v40_start",type="primary",use_container_width=True,
                 disabled=not draws or (full==0 and not partial)):
        bar=st.progress(0,text="V40 altı ısı haznesi hazırlanıyor")
        status=st.empty()
        def callback(i,total,stage,day):
            f=min(1.,i/max(total,1))
            bar.progress(f,text=f"%{round(f*100)} — {stage}")
            status.caption(f"{day} • {i}/{total} gerçek çekiliş")
        try:
            with st.spinner("80 sayının her hedef çekilişten önceki hafızası taranıyor..."):
                blob,meta,tests,rows=study(draws,include_partial=partial,
                                         progress=callback)
            st.session_state["v40_heat"]={
                "sha":source_sha,"partial":partial,"blob":blob,
                "meta":meta,"tests":tests,"rows":rows}
            bar.progress(1.,text="V40 gerçek sıralı test ve tek ZIP hazır")
        except Exception as exc:
            st.error(f"V40 hata: {exc}")
    saved=st.session_state.get("v40_heat")
    if not saved:
        st.caption("Tek tuşla 80 sayının her çekilişte önceki ısı hafızası, "
            "bant-aile-yön kesişimleri ve sonraki çıkan20 katkıları tek ZIP'te.")
        return
    if saved["sha"]!=source_sha or saved["partial"]!=partial:
        st.warning("Yeni veri var; güncel rapor için motoru yeniden başlat.")
    meta=saved["meta"]
    st.success(f"{meta['draws_read']} çekiliş tarandı; "
               f"{meta['number_steps']} sayı-karakter/test gözlemi oluştu.")
    st.download_button("⬇️ V40 — 6 HAVUZUN BÜTÜN ÇEKİLİŞ ANALİZLERİ TEK ZIP",
        data=saved["blob"],
        file_name="V40_ALTI_ISI_YON_AILE_BANT_TEK_ZIP.zip",
        mime="application/zip",type="primary",
        use_container_width=True,key="v40_download")
    st.markdown("#### Sonraki gerçek 20 sayıya katılım")
    stat=[r for r in saved["rows"] if r["boyut"]=="ISI" and r["test_donemi"]=="TEST"]
    st.dataframe([{ "Havuz":r["havuz"],"Sayı başına hedef20 %":r["cikis_orani_yuzde"],
        "Gerçekte gelen":r["gercek_sahneye_cikis"],
        "RNG beklenen":r["ortalama_rastgele_beklenen"],
        "İncelenen sayı/adım":r["sayi_firsati"]} for r in stat],
        hide_index=True,use_container_width=True)
    st.markdown("#### Isı–yön ve aile–bant hareketleri")
    seat=st.selectbox("Araştırılacak ısı haznesi",SIX,key="v40_seat")
    filtered=[r for r in saved["rows"] if r["test_donemi"]=="TEST" and
              r["havuz"]==seat and r["boyut"]=="ISI_YON"]
    st.dataframe(filtered,hide_index=True,use_container_width=True)
    with st.expander("Hedef çekilişten önce kalibre edilen oranların testi"):
        st.dataframe(saved["tests"],hide_index=True,use_container_width=True)
        st.caption("Brier daha küçükse olasılık tahmini daha isabetlidir. "
          "Gün bazlı belirsizlik aralığı sıfırı kapsıyorsa üstünlük "
          "gösterilmiş kabul edilmez.")
    with st.expander("Derin aile, bant ve havuzda kalış raporu"):
        dimension=st.selectbox("Çapraz analiz",
             ["ISI_YON_AILE","ISI_YON_BANT","ISI_YON_KALIS"],
             key="v40_cross")
        pairs=[r for r in saved["rows"] if r["boyut"]==dimension
               and r["test_donemi"]=="TEST" and r["havuz"]==seat]
        st.dataframe(pairs,hide_index=True,use_container_width=True)
    st.caption("Raporlar betimsel ve ileri yürüyen istatistiksel testtir. "
        "Gizli RNG durumuna erişim, 16/20 veya kesin kupon iddiası değildir.")
