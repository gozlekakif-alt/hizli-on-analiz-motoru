# -*- coding: utf-8 -*-
"""V37 B: one-click experts fed from the SINGLE real 80-ball shared ledger."""
import hashlib
import json
import tempfile
from pathlib import Path
import streamlit as st
from v37_ortak_hafiza import replay
from v37_aile_yon_uzmanlari import build, export


def render_v37b(draws):
    st.subheader("🧩 V37B — Aileler ve Yön Uzmanları / Ortak Hafızaya Bağlı")
    st.info("Gerçek çekilişleri **ortak V37 SQLite yaşam hafızasından** okur. "
        "2'li, 3'lü, 4'lü ailelerin önceki 11 çekilişle tekrarlarını; "
        "dörtlülerin 3+1, 2+2, 2+1+1 gibi tamamlanma yollarını; "
        "altı sıcaklık sınıfı arasında her sayı hareketini ve "
        "aile–yön bağlantılarının delillerini kaydeder.")
    st.caption("Bu aşamada 4'lü parçalı yol raporu, **o çekilişte 4/4 birlikte "
        "gelen dörtlülerin** önceki 11 çekilişte üyelerinin ilk görünme "
        "sırasını ölçer. 4/4 tek çekilişte hiç gelmemiş ailelerin bütün "
        "parçalı yaşamı sonraki motor aşamasıdır. Her çekilişin tekrarlayan "
        "aile sayıları tam; ayrıntılı örnekler en fazla sekizdir.")
    byday={}
    for r in draws:byday.setdefault(r["day"],set()).add(int(r["pos"]))
    full=sum(set(x)==set(range(1,218)) for x in byday.values())
    a,b,c=st.columns(3)
    a.metric("217/217 tamam gün",full)
    b.metric("Gerçek çekiliş",len(draws))
    c.metric("Aile büyüklüğü","2 / 3 / 4")
    partial=st.checkbox("Eksik günler de dahil (kesintilerde önceki aile unutulur)",
                        value=False,key="v37b_partial")
    sorted_input=sorted(draws,key=lambda d:(d["day"],int(d["pos"])))
    fingerprint=hashlib.sha256(str([
      (d["day"],int(d["pos"]),int(d["no"]),sorted(d["nums"]))
      for d in sorted_input]).encode()).hexdigest()
    statekey=f"v37b_result_{partial}"
    saved=st.session_state.get(statekey)
    if st.button("▶️ V37B TEK TUŞ — ORTAK HAFIZA + AİLE + YÖN MOTORLARINI ÇALIŞTIR",
                 type="primary",use_container_width=True,
                 disabled=not sorted_input or (full==0 and not partial),
                 key="v37b_go"):
        bar=st.progress(0,text="Ortak hafıza doğrulanıyor")
        status=st.empty()
        def on_progress(i,total,stage,day):
            ratio=min(1.0,i/max(total,1))
            bar.progress(ratio,text=f"%{100*ratio:.0f}: {stage}")
            status.caption(f"{day}: {i}/{total}")
        try:
            # Reuse the SAME SQLite DB created by V37A when available;
            # otherwise create it once, with no copy of raw draws inside B.
            original_key=f"v37_hafiza_state_{partial}"
            original=st.session_state.get(original_key)
            if original and original.get("dir"):
                root=Path(original["dir"])
            else:
                root=Path(tempfile.mkdtemp(prefix="v37_ortak_yasam_b_"))
                st.session_state[original_key]={"dir":str(root),"summary":None,"zip":None}
            root.mkdir(parents=True,exist_ok=True)
            db=root/"hafiza.sqlite3"
            target=root/"V37B_AILE_ISI_YON_ORTAK_HAFIZA_TEK_ZIP.zip"
            with st.spinner("72 günlük 80 sayı hafızası kontrol ediliyor ve bağımsız aile/yön uzmanları bağlanıyor..."):
                base=replay(sorted_input,db,include_partial=partial,progress=on_progress)
                bar.progress(0.0,text="Ailelerin geçmiş tekrarları ve ısı yönü hesaplanıyor")
                attached=build(db,progress=on_progress)
                panels=export(db,target)
            st.session_state[statekey]={"root":str(root),"db":str(db),
                    "archive":str(target),"source":fingerprint,
                    "base":base,"attached":attached,"panels":panels}
            bar.progress(1.0,text="V37B uzman kayıtları ve tek ZIP hazır")
        except Exception as exc:
            st.error(f"V37B durdu: {exc}")
            st.caption("Eski geçmiş değiştiyse V37 ortak hafızasında yeni boş "
                       "kayıt başlat; mevcut veritabanına zarar verilmez.")
    saved=st.session_state.get(statekey)
    if not saved:
        st.caption("Tek tuş önce ortak hafızayı oluşturur/doğrular, sonra aile "
                   "ve yön uzmanlarını aynı veritabanında çalıştırır. "
                   "Ayrı sonuç ZIP'i ortak SQLite'ın dev boyutunu yeniden çoğaltmaz.")
        return
    if saved["source"]!=fingerprint:
        st.warning("Yeni veri veya geçmiş düzeltmesi tespit edildi. Güncel rapor için tekrar başlat.")
    info=saved["attached"];panels=saved["panels"]
    x,y,z=st.columns(3)
    x.metric("İncelenen çekiliş",info["completed_draws"])
    y.metric("Dörtlü aile olay örneği",info["repeated_quartet_evidence_rows"])
    z.metric("Aile–yön bağlantısı",info["linked_direction_events"])
    st.download_button("⬇️ V37B AİLE + YÖN + DİYALOG — TEK ZIP",
        data=Path(saved["archive"]).read_bytes(),
        file_name="V37B_AILE_ISI_YON_ORTAK_HAFIZA_TEK_ZIP.zip",
        mime="application/zip",type="primary",
        use_container_width=True,key="v37b_zip")
    st.markdown("#### Ailelerin günlük değil, adım adım tekrar ve yön davranışı")
    for period,values in panels.items():
        with st.expander(period+" — bütün çekilişlerin araştırma özeti",expanded=True):
            st.json(values)
    st.caption("ZIP: her çekilişin 2/3/4 aile tekrarı, 36 sıcaklık geçişi, "
       "sınırlı somut aile örnekleri, aile–ısı delil bağlantıları, "
       "ilk 36/sonraki 36 günün tarihsel karşılaştırması ve kapsam notları.")
    st.caption("Bu, RNG'nin gizli algoritmasını çözdüğü veya gelecek 20 sayıyı "
               "bildiği anlamına gelmez. Büyük çapta gerçek veri işlemi "
               "Streamlit Cloud üzerinde zaman alabilir.")
