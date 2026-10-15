# -*- coding: utf-8 -*-
"""V52 interactive same-draw 80x80 partner counter: full/partial days."""
from __future__ import annotations

import hashlib

import streamlit as st

from v45_sinyal_kor_test import SLOTS
from v52_ayni_cekilis_eslikci_217 import (
    normalise_rows,compute,anchor_partners,pairs_sorted,make_zip,PAIR_P
)

@st.cache_data(ttl=600,show_spinner=False,max_entries=2)
def _report(hash_data, data, day):
    parsed,issues=normalise_rows(
        {"day":d,"id":drawno,"time":clock,"pos":slot,"nums":nums}
        for d,entries in data for slot,drawno,clock,nums in entries
    )
    return make_zip(day,parsed,issues)

def render_v52(draws):
    st.subheader("🔗 V52 — Aynı Çekilişte 80 Sayının Eşlikçileri")
    st.caption("Günün 1. çekilişinden 217. çekilişine kadar SADECE aynı "
               "20'li kadrodaki sayı çiftlerini sayar. Başka çekilişlerde "
               "ayrı ayrı çıkmaları birliktelik sayılmaz.")
    input_rows=[]
    for r in draws:
        try:
            slot=int(r["pos"])
            input_rows.append({
                "day":str(r["day"]),"id":int(r["no"]),"pos":slot,
                "time":SLOTS[slot-1] if 1<=slot<=217 else "",
                "nums":tuple(sorted(map(int,r["nums"])))
            })
        except (KeyError,TypeError,ValueError,IndexError):
            continue
    all_days,issues=normalise_rows(input_rows)
    if not all_days:
        st.warning("Geçerli çekiliş bulunmadı. Önce veri.txt veya canlı sonuçları ekle.")
        return
    opts=sorted(all_days,reverse=True)
    default_day=next((d for d in opts if len(all_days[d])==217),opts[0])
    chosen=st.selectbox("İncelenecek gün",opts,index=opts.index(default_day),key="v52_day")
    rows=all_days[chosen]
    a,b,c=st.columns(3)
    a.metric("Kaydedilen çekiliş",f"{len(rows)}/217")
    b.metric("Toplam ikili görünüm",f"{190*len(rows):,}".replace(",",".")) 
    c.metric("Olası farklı ikili","3.160")
    if issues:
        st.warning(f"{len(issues)} geçersiz/çakışan kayıt var. "
                   "Bu satırlar hesaplamaya katılmadı.")
    if len(rows)<217:
        st.info("Bu gün henüz 217/217 değil. Yalnız eldeki gerçek sonuçlar sayılıyor; "
                "eksik çekilişler sıfır gibi değerlendirilmez.")
    prefix=st.slider("Kaçıncı çekilişe kadarki birikim?",1,217,
                     value=max(r["pos"] for r in rows),step=1,
                     key="v52_progress")
    anchor=st.selectbox("Hangi sayının 79 eşlikçisini inceleyelim?",
                        list(range(1,81)),index=18,key="v52_number")
    n,counts,pair=compute(rows,upto=prefix)
    ranked=pairs_sorted(pair)
    ppartners=anchor_partners(anchor,counts,pair)
    st.markdown(f"**{chosen} • ilk {prefix} slot, {n} kayıtlı çekiliş**")
    a,b,c=st.columns(3)
    a.metric(f"{anchor} kaç kez çıktı?",counts[anchor])
    a2,b2,count2=ranked[0]
    b.metric("En çok ortak çıkan ikili",f"{a2}–{b2}")
    c.metric("Bu ikili kaç kez?",count2)
    st.caption(f"Bu tarihte {n} bağımsız 20/80 çekilişi için, belirli bir "
               f"ikilinin rastgele beklenen ortak sayısı {n*PAIR_P:.2f}'dir. "
               "En yüksek ikili geçmiş sonuçtan seçildiği için ayrıca "
               "istatistiksel doğrulama gerekir.")
    st.markdown(f"#### {anchor} sayısının 79 eşlikçisi — aynı çekilişte")
    st.dataframe([{
        "Sayı":anchor,"Eşlikçi":num,"Beraber kaç kez":joint,
        f"{anchor} çıktığında eşlikçi oranı":
            f"%{joint/counts[anchor]*100:.1f}" if counts[anchor] else "%0"}
        for num,joint in ppartners
    ],use_container_width=True,hide_index=True,height=330)
    st.markdown("#### Birikimde en çok çıkan 20 ikili")
    st.dataframe([{"İkili":f"{x}-{y}","Birlikte":v,
                   "Rastgele beklenti":round(n*PAIR_P,2)}
                  for x,y,v in ranked[:20]],
                  use_container_width=True,hide_index=True,height=300)
    st.markdown("#### Aynı günün her 20'li kadrosu")
    st.dataframe([{
        "Slot":r["pos"],"Çekiliş":r["id"],"Saat":r["time"],
        "20 sayı":"-".join(map(str,r["nums"]))
    } for r in rows if r["pos"]<=prefix],hide_index=True,
        use_container_width=True,height=250)
    st.markdown("#### Bütün günler + çekiliş çekiliş tek rapor")
    st.caption("ZIP içinde seçili günün 80×79 tam eşlikçi tablosu, 3.160 ikili, "
               "her çekilişte oluşan 190 çift, 1–217 birikimli matris ve "
               "veri.txt'deki tüm günlerin 3.160 ikili karşılaştırması bulunur.")
    frozen=tuple((d,tuple((r["pos"],r["id"],r["time"],r["nums"])
                            for r in rr)) for d,rr in sorted(all_days.items()))
    state_id=hashlib.sha256(repr((chosen,frozen)).encode()).hexdigest()
    if st.button("▶️ V52 — 217 ÇEKİLİŞİN TÜM EŞLİKÇİLERİNİ SAY",
                 type="primary",key="v52_run",use_container_width=True):
        try:
            with st.spinner("217 adım, 80×80 ikililer ve bütün günler hazırlanıyor..."):
                zbytes=_report(state_id,frozen,chosen)
            st.session_state["v52_download"]=(state_id,zbytes)
        except Exception as exc:
            st.error(f"V52 rapor hatası: {exc}")
    result=st.session_state.get("v52_download")
    if result and result[0]==state_id:
        st.download_button("⬇️ V52 TEK ZIP İNDİR — BANA GÖNDER",
            data=result[1],file_name=f"V52_ES_CEKILIS_80X80_{chosen}_TEK_RAPOR.zip",
            mime="application/zip",type="primary",use_container_width=True,key="v52_zip")
        st.caption("Dosya buradan telefonuna iner; GitHub'a göndermez.")
    elif result:
        st.info("Gün veya kayıtlar değişti. Güncel ZIP için yukarıdaki düğmeye yeniden bas.")
