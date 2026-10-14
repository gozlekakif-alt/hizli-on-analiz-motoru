# -*- coding: utf-8 -*-
"""Streamlit one button: V37 shared immutable memory -> V38 207 expert measures."""
import hashlib
import tempfile
from pathlib import Path
import streamlit as st
from v37_ortak_hafiza import replay as replay_core
from v38_207_uzman_yurutucu import replay as replay_experts,export


def render_v38(draws):
    st.subheader("🧠 V38 — 207 Uzman / 17 Ana Dal / Ortak Yaşam Hafızası")
    st.info("V37'nin aynı 80 sayılık gerçek yaşam hafızasını paylaşan "
        "**207 kimlikli uzman yürütücüsü**. Her gerçek çekilişte 207 ayrı "
        "sayısal ölçüm kaydeder. Bazı ayrıntılı yaşam uzmanları şimdilik "
        "yalnız tarama göstergesidir; kimlik kaydı tamamlanan epizod demek değildir.")
    daygroups={}
    for d in draws:daygroups.setdefault(d["day"],set()).add(int(d["pos"]))
    complete=sum(v==set(range(1,218)) for v in daygroups.values())
    partial=st.checkbox("Eksik günleri de dahil et (kayıt boşlukları korunur)",
                         value=False,key="v38_partial")
    a,b,c=st.columns(3)
    a.metric("Tam gün",complete)
    b.metric("Gerçek çekiliş",len(draws))
    c.metric("Kayıtlı uzman",207)
    ds=sorted(draws,key=lambda r:(r["day"],int(r["pos"])))
    sha=hashlib.sha256(str([(r["day"],int(r["pos"]),int(r["no"]),
                            sorted(r["nums"])) for r in ds]).encode()).hexdigest()
    statekey="v38_state_"+str(partial)
    state=st.session_state.get(statekey)
    if st.button("▶️ V38 — BÜTÜN 207 UZMANI TEK TUŞLA ÇALIŞTIR",
                 type="primary",use_container_width=True,key="v38_run",
                 disabled=(not ds or (complete==0 and not partial))):
        bar=st.progress(0,text="Ortak hafıza doğrulanıyor")
        infoline=st.empty()
        def update(i,total,stage,day):
            bar.progress(min(1.0,i/max(1,total)),text=stage)
            infoline.caption(f"{day}: çekiliş {i}/{total}")
        try:
            memory_state=st.session_state.get("v37_hafiza_state_"+str(partial))
            if memory_state and memory_state.get("dir"):
                root=Path(memory_state["dir"])
            else:
                root=Path(tempfile.mkdtemp(prefix="v38_207_"))
                st.session_state["v37_hafiza_state_"+str(partial)]={
                    "dir":str(root),"summary":None,"zip":None}
            root.mkdir(parents=True,exist_ok=True)
            database=root/"hafiza.sqlite3"
            archive=root/"V38_207_UZMAN_HER_CEKILIS_TEK_ZIP.zip"
            with st.spinner("207 uzmanın her çekiliş kaydı işleniyor..."):
                core=replay_core(ds,database,include_partial=partial,progress=update)
                result=replay_experts(database,progress=update)
                summary=export(database,archive)
            st.session_state[statekey]={
                "sha":sha,"archive":str(archive),"result":result,
                "summary":summary,"core":core}
            bar.progress(1.0,text="207 uzman raporu hazır")
        except Exception as e:
            st.error("V38 uzman analizi: "+str(e))
            st.caption("Geçmiş veri değiştiyse önce V37'de yeni boş ortak hafıza oluştur.")
    state=st.session_state.get(statekey)
    if not state:return
    if sha!=state["sha"]:st.warning("Yeni çekiliş var: tekrar başlatıp yalnız yeni adımı işle.")
    stats=state["result"]
    a,b,c=st.columns(3)
    a.metric("Uzman ölçümü",f"{stats['measurement_cells']:,}")
    b.metric("Doğrudan adım ölçümü",stats["per_step_measurement_experts"])
    c.metric("Tarama göstergesi",stats["proxy_screening_experts"])
    st.download_button("⬇️ V38 207 UZMAN — TEK ZIP RAPORU",
        data=Path(state["archive"]).read_bytes(),
        file_name="V38_207_UZMAN_HER_CEKILIS_TEK_ZIP.zip",
        mime="application/zip",use_container_width=True,type="primary",
        key="v38_download")
    st.caption("17 ana grup, tam 207 kimlik ve her gerçek çekiliş için "
      "ölçüm tablosu. Tarama göstergeleri henüz uzun yaşam epizodu "
      "olarak doğrulanmış değildir; ZIP'de tek tek işaretlenir.")
    st.dataframe(state["summary"],hide_index=True,use_container_width=True)
