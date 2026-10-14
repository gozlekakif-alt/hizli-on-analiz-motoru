# -*- coding: utf-8 -*-
"""V42 Streamlit five legacy dynamic H72 pools: quota first, identities second."""
import hashlib
import streamlit as st

from v42_bes_hareketli_havuz_kota import study,POOL_NAMES


def render_v42(draws):
    st.subheader("🎯 V42 — Beş Hareketli Isı Havuzu / Çıkan20 Kota Motoru")
    st.info("Bu kez eski %60 çalışmasındaki **5 hareketli havuza** dönüyoruz: "
        "Soğuk (72'de 0–14 kez), Serin (15–16), Nötr (17–19), "
        "Ilık (20–21), Sıcak (22+). "
        "**Her çekilişten önce** havuz büyüklükleri değişir. "
        "İlk hedef, çıkan 20'nin bu beş havuzdan kaçar sayı ile dolacağını tahmin etmektir. "
        "20 sayının kimliği ayrıca ölçülür.")
    st.caption("Tek havuzda ±1 başarılı olmak, tüm 5 havuzun birden ±1 "
      "olması veya 20 sayının kimliğini doğru bulmak DEMEK DEĞİLDİR. "
      "RNG'nin gerçek matematiksel referansı her adımda karşılaştırılır.")
    days={}
    for row in draws:
        days.setdefault(row["day"],set()).add(int(row["pos"]))
    complete=sum(set(range(1,218))==s for s in days.values())
    a,b,c=st.columns(3)
    a.metric("217/217 tam gün",complete)
    b.metric("Gerçek çekiliş",len(draws))
    c.metric("Hareketli ısı havuzu",len(POOL_NAMES))
    partial=st.checkbox("Eksik günleri dahil et (eksik çekiliş üretme)",
                key="v42_partial",value=False)
    data_hash=hashlib.sha256(str([
        (d["day"],int(d["pos"]),int(d["no"]),sorted(d["nums"]))
        for d in draws]).encode()).hexdigest()
    if st.button("▶️ V42 — BEŞ HAVUZUN 20'Lİ KOTALARINI VE OLUŞUM TEKRARLARINI TEST ET",
                 type="primary",use_container_width=True,key="v42_go",
                 disabled=not draws or (complete==0 and not partial)):
        bar=st.progress(0,text="72 gerçek çekilişlik sıcaklık hafızası kuruluyor")
        line=st.empty()
        def progress(i,total,stage,day):
            f=min(1.,i/max(1,total))
            bar.progress(f,text=f"%{100*f:.0f} — {stage}")
            line.caption(f"{day}: {i}/{total}")
        try:
            with st.spinner("20'nin havuzlardan oluşumu, ±1 kota ve gerçek matematiksel ihtimal hesaplanıyor..."):
                blob,meta,summary,ident,formation=study(draws,include_partial=partial,
                                                       progress=progress)
            st.session_state["v42_saved"]={"sha":data_hash,"partial":partial,
                "blob":blob,"meta":meta,"summary":summary,"ident":ident,
                "formation":formation}
            bar.progress(1.,text="V42 tüm raporlar hazır")
        except Exception as exc:st.error("V42 araştırma hatası: "+str(exc))
    saved=st.session_state.get("v42_saved")
    if not saved:
        st.caption("Eski 6→7 %60–70 raporuyla karşılaştırmak için "
           "7.–12. çekilişlerin havuz başına ±1 doğruluğu ve bütün "
           "5 havuzun aynı anda ±1 doğruluğu ayrı ayrı raporlanır.")
        return
    if saved["sha"]!=data_hash or saved["partial"]!=partial:
        st.warning("Yeni çekilişler eklendi: güncel analiz için yeniden çalıştır.")
    meta=saved["meta"]
    a,b,c=st.columns(3)
    a.metric("Önceden kota tahmin edilen",meta["evaluated_targets"])
    a,b,c=st.columns(3)
    a.metric("Tam 20'li kimlik tekrar çifti",
        meta["full20_identity_duplicate_audit"]["exact_20_sets_repeated_pairs"])
    b.metric("Tekrarlayan 5 havuz imzası",
        meta["full20_identity_duplicate_audit"]["five_pool_formation_repeated_patterns"])
    c.metric("Tekrarlayan 8 bant imzası",
        meta["full20_identity_duplicate_audit"]["eight_band_formation_repeated_patterns"])
    st.download_button("⬇️ V42 — BEŞ HAVUZ KOTALARI + 20'Lİ KİMLİKLER + TEKRARLAR TEK ZIP",
        data=saved["blob"],file_name="V42_BES_HAVUZ_KOTA_OLUSUM_TEK_ZIP.zip",
        key="v42_download",type="primary",mime="application/zip",
        use_container_width=True)
    st.markdown("#### Son 36 gün: 20'yi beş havuzda doldurma başarısı")
    test=[r for r in saved["summary"] if r["donem"]=="TEST"]
    st.dataframe(test,hide_index=True,use_container_width=True)
    st.markdown("#### Son 36 gün: kotalarla seçilen 20 sayının kimliği")
    identity=[r for r in saved["ident"] if r["donem"]=="TEST"]
    st.dataframe(identity,hide_index=True,use_container_width=True)
    with st.expander("Tekrarlayan 20'li oluşum karakterleri"):
        st.dataframe(saved["formation"][:150],hide_index=True,use_container_width=True)
    with st.expander("Hata payını nasıl okuyalım?"):
        st.markdown("**Tek havuz ±1:** Bir sıcaklık sınıfının tahmini sayısı "
             "gerçekten en çok 1 eksik/fazla.\n\n"
             "**Beş havuz aynı anda ±1:** Hepsi aynı çekilişte en çok 1 hata.\n\n"
             "**Kimlik isabeti:** Önceden seçilen gerçek 20 sayı adedinden "
             "kaçı çıktı? Bu oran için rastgele ortalama **5/20**.\n\n"
             "Adil RNG'nin ±1 beklenen başarısı, o anki havuzların "
             "gerçek aday sayılarına koşullu hiper-geometrik hesapla bulunur.")
    st.caption("Geçmişte oluşum imzalarının tekrar etmesi bir sonraki 20 sayıyı "
      "tahmin ettiğinin kanıtı değildir. Sonuç açılmadan dondurulan "
      "tahmin ve rastgele referansı daima birlikte kontrol edilir.")
