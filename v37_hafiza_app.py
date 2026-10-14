# -*- coding: utf-8 -*-
"""V37 Stage A single-button shared memory, inspectable evidence ZIP."""
import os
import tempfile
import hashlib
from pathlib import Path
import streamlit as st
from v37_ortak_hafiza import replay,export


def render_v37(draws):
    st.subheader("🧠 V37 — 80 Sayının Ortak ve Silinmeyen Yaşam Hafızası")
    st.info("Burası V37'nin **ilk çalışan çekirdeği**: Tek resmi çekiliş defteri, "
            "80 sayının günlük ve ömürlük yaşamı, motor haznesine giriş/çıkış "
            "olayları, delilli motorlar arası bağlantı ve **SQLite kayıt dosyası**.")
    st.caption("207 uzman alt dalı mimaride tanımlıdır; **henüz 8 temel dal çalışıyor.** "
               "Ailelerin 2+1+1 gibi ayrıntılı yaşam motorları sonraki aşamada "
               "bu tek ortak hafızaya bağlanacak. Gizli RNG algoritmasını çözme "
               "ve gelecekteki sayıları bilme iddiası yok.")
    all_days={}
    for d in draws:all_days.setdefault(d["day"],set()).add(int(d["pos"]))
    full=sum(p==set(range(1,218)) for p in all_days.values())
    a,b,c=st.columns(3)
    a.metric("Tam 217 çekilişlik gün",full)
    b.metric("Eksik gün",len(all_days)-full)
    c.metric("Gerçek çekiliş",len(draws))
    partial=st.checkbox("Eksik günleri de işle (bilinmeyeni çıkmama sayma)",
                        key="v37_partial",value=False)
    statekey="v37_hafiza_state_"+str(partial)
    if statekey not in st.session_state:
        st.session_state[statekey]={"dir":tempfile.mkdtemp(prefix="hizli_v37_"),
                                     "summary":None,"zip":None}
    state=st.session_state[statekey]
    src=sorted(draws,key=lambda d:(d["day"],int(d["pos"])))
    digest=hashlib.sha256(str([(d["day"],int(d["pos"]),int(d["no"]),sorted(d["nums"]))
                               for d in src]).encode()).hexdigest()
    if st.button("▶️ V37 — 80 SAYININ BÜTÜN YAŞAM HAFIZASINI İŞLE",
                 type="primary",use_container_width=True,disabled=not draws or
                 (not partial and full==0),key="v37_go"):
        bar=st.progress(0,text="V37 ortak hafıza hazırlanıyor")
        status=st.empty()
        def update(done,total,stage,day):
            val=min(1.0,done/max(total,1))
            bar.progress(val,text=f"%{val*100:.0f} — {stage}")
            status.caption(f"{day} • yeni eklenen {done}/{total} çekiliş")
        db=Path(state["dir"])/"hafiza.sqlite3"
        zipfile=Path(state["dir"])/"V37_ORTAK_80_SAYI_YASAM_HAFIZASI_TEK_ZIP.zip"
        with st.spinner("Her çekilişte 80 sayı, sekiz motor haznesi ve olay bağlantıları işleniyor..."):
            try:
                result=replay(src,db,include_partial=partial,progress=update)
                export(db,zipfile,result)
                state.update({"summary":result,"zip":str(zipfile),"source":digest})
                bar.progress(1.0,text="Ortak yaşam hafızası ve tek ZIP hazır")
            except ValueError as ex:
                st.error("Veri güvenliği: "+str(ex))
                st.warning("Eski geçmiş değiştiyse güvenli kayıt için aşağıdaki "
                           "'Yeni boş hafıza' düğmesine bas; önceki ZIP'i sakla.")
            except Exception as ex:st.error("V37 hata: "+str(ex))
    result=state.get("summary")
    if result:
        if state.get("source")!=digest:
            st.warning("Yeni çekiliş var veya geçmiş değişmiş. Güncel ZIP için yeniden çalıştır.")
        x,y,z=st.columns(3)
        x.metric("Hafızadaki çekiliş",result["draw_count"])
        y.metric("Sayı-yaşam kartı",result["ball_step_rows"])
        z.metric("Motor olay bağlantısı",result["same_number_event_dialogues"])
        a,b=st.columns(2)
        a.metric("Son işlemde yeni çekiliş",result["new_draws_added"])
        b.metric("Çalışan temel uzman",result["engine_operational_count"])
        st.download_button("⬇️ V37 ORTAK HAFIZA SQLITE + RAPORLAR TEK ZIP",
          data=Path(state["zip"]).read_bytes(),
          file_name="V37_ORTAK_80_SAYI_YASAM_HAFIZASI_TEK_ZIP.zip",
          mime="application/zip",type="primary",use_container_width=True,
          key="v37_download")
        st.dataframe(result["daily"],hide_index=True,use_container_width=True)
        with st.expander("Çalışan ortak hafıza uzmanları"):
            st.write(", ".join(result["engine_operational"]))
        st.caption("Yalnız yeni çekiliş geldiyse mevcut SQLite geçmişi doğrulayıp "
                   "yalnız eklenen çizelgeyi işler. Verilen kaynak önceki "
                   "çekilişi değiştirirse eski veritabanının üstüne yazmaz.")
    if st.button("🗂️ Yeni boş hafıza oluştur (eskisine dokunma)",key="v37_new"):
        st.session_state[statekey]={"dir":tempfile.mkdtemp(prefix="hizli_v37_"),
                                     "summary":None,"zip":None}
        st.rerun()
    st.caption("Streamlit sunucusunun geçici SQLite yolu kalıcı GitHub kaydı "
        "değildir; ZIP'i indir. GitHub Actions veri.txt güncellemesinde yeni "
        "rapor üretir. Motorların kalıcı kütüğü yine veri.txt kaynağına dayanır.")
