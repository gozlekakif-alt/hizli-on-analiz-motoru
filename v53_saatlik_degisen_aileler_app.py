# -*- coding: utf-8 -*-
"""Interactive V53: hour-by-hour moving same-draw families (2..10)."""
from __future__ import annotations

import hashlib
import streamlit as st

from v45_sinyal_kor_test import SLOTS
from v52_ayni_cekilis_eslikci_217 import normalise_rows
from v53_saatlik_degisen_aileler import (
    BLOCKS,analyze_day,report_zip,K_SIZES,NAME_BY_HOUR
)

@st.cache_data(ttl=600,show_spinner=False,max_entries=5)
def _day_result(day,frozen):
    rows=[{"day":day,"pos":pos,"id":ident,"time":clock,"nums":nums}
          for pos,ident,clock,nums in frozen]
    return analyze_day(rows,day)

@st.cache_data(ttl=600,show_spinner=False,max_entries=2)
def _single_zip(statehash,selected,frozen):
    payload=[{"day":day,"pos":pos,"id":ident,"time":clock,"nums":nums}
             for day,rows in frozen
             for pos,ident,clock,nums in rows]
    days,issues=normalise_rows(payload)
    report,_=report_zip(selected,days,issues)
    return report

def render_v53(draws):
    st.subheader("🧬 V53 — Saat Saat Değişen Sayı Aileleri")
    st.caption("Aileleri yalnızca AYNI 20'li çekilişte birlikte çıkan sayılardan "
               "oluşturur. Bir saatte en az 2 çekilişte görünen aile aktiftir. "
               "Bir önceki saate göre yeni, devam eden, geri dönen ve sönen aileleri izler.")
    inputrows=[]
    for x in draws:
        try:
            pos=int(x["pos"])
            inputrows.append({
                "day":str(x["day"]),"pos":pos,"id":int(x["no"]),
                "time":SLOTS[pos-1] if 1<=pos<=217 else "",
                "nums":tuple(sorted(map(int,x["nums"])))
            })
        except (KeyError,ValueError,TypeError):
            continue
    days,issues=normalise_rows(inputrows)
    if not days:
        st.info("Henüz geçerli çekiliş bulunamadı. Önce veri.txt dosyasından ya da canlı sonuçlardan yükle.")
        return
    dates=sorted(days,reverse=True)
    selected=st.selectbox("İncelenecek gün",dates,index=0,key="v53_day")
    records=days[selected]
    encoded=tuple((x["pos"],x["id"],x["time"],x["nums"]) for x in records)
    with st.spinner("Bu günün 18 saatindeki aile kimlikleri eşleştiriliyor..."):
        result=_day_result(selected,encoded)
    m=result["meta"]
    x,y,z=st.columns(3)
    x.metric("Çekiliş",f"{m['recorded']}/217")
    y.metric("Tam saat",f"{m['hours_complete']}/18")
    z.metric("Birden çok saatte tekrar eden aile",m["cross_hour_repeated_family_count"])
    if issues:
        st.warning(f"{len(issues)} geçersiz veya çakışan kayıt atlandı.")
    if m["truncated_hours"]:
        st.error("Aday sınırına ulaşılan saatler var: "
                 +", ".join(m["truncated_hours"])+". Bu saatler eksik taranmıştır.")
    if not m["complete_day"]:
        st.info("Bu gün henüz tam değil. Yalnız mevcut çekilişlere göre güncellenen aileleri görüyoruz.")

    a,b=st.columns(2)
    with a:
        hour=st.selectbox("Saat", [i["code"] for i in BLOCKS],
           index=next((idx for idx,b in reversed(list(enumerate(BLOCKS)))
                       if any(x["pos"]>=b["start"] and x["pos"]<=b["end"] for x in records)),0),
           format_func=lambda code:f"{code} • {NAME_BY_HOUR[code]}",
           key="v53_hour")
    with b:
        size=st.selectbox("Aile büyüklüğü",list(K_SIZES),index=4,
                          format_func=lambda n:f"{n}'lı aile",
                          key="v53_size")
    hit=next(r for r in result["overview"] if r["hour"]==hour and r["size"]==size)
    st.markdown(f"#### {NAME_BY_HOUR[hour]} — {size}'lı ailelerin hareketi")
    q,r,s,t=st.columns(4)
    q.metric("Aktif",hit["active_families"])
    r.metric("Yeni",hit["new"])
    s.metric("Devam",hit["continuing"])
    t.metric("Geri gelen",hit["comeback"])
    st.caption(f"Önceki saate göre sönen: {hit['faded']}. "
               f"Saatte girilmiş sonuç {hit['draws']}/{hit['expected']}. "
               "Aktif=aynı saatte en az 2 farklı çekilişte tam aile birlikteliği.")
    st.dataframe([{
        "Aile":x["family"],"Birlikte":x["together"],"Hareket":x["status"]}
        for x in result["active"]
        if x["hour"]==hour and x["k"]==size],
        use_container_width=True,hide_index=True,height=300)
    st.markdown("#### Bu ailelerin 18 saatlik gelişimi")
    st.dataframe([{
        "Saat":x["hour"],"Çekiliş":x["draws"],
        "Aktif aile":x["active_families"],
        "Yeni":x["new"],"Devam":x["continuing"],
        "Geri":x["comeback"],"Sönen":x["faded"],
        "En güçlü aile":x["top_family"],"Kaç kere":x["top_support"]}
        for x in result["overview"] if x["size"]==size],
        use_container_width=True,hide_index=True,height=450)
    st.markdown("#### Birden fazla saatte güçlenen aileler")
    st.dataframe([{
        "Aile boyutu":x["size"],"Aile":x["family"],
        "Aktif saat":x["active_hours"],
        "Günlük tam görünüm":x["total_day_appearances"],
        "Saatlik yolculuk":x["hourly_path"]}
        for x in result["recurring"] if x["size"]==size][:60],
        use_container_width=True,hide_index=True,height=300)
    st.markdown("#### GitHub raporu — tek ZIP")
    st.caption("Tek dosyada 18 saat x 2–10 aile hareketi, tüm aktif aileler, "
               "yeni/devam/geri/sönenler, birden fazla saatte tekrarlayan "
               "ailelerin zaman yolu ve eski günlerin saatlik özetleri var.")
    frozen=tuple((day,tuple((x["pos"],x["id"],x["time"],x["nums"]) for x in rr))
                 for day,rr in sorted(days.items()))
    hid=hashlib.sha256(repr((selected,frozen)).encode()).hexdigest()
    if st.button("▶️ V53 — SAAT SAAT DEĞİŞEN AİLE RAPORUNU HAZIRLA",
                 key="v53_generate",type="primary",use_container_width=True):
        try:
            with st.spinner("72 günlük saatlik değişimler ve seçili günün aile yolculuğu hazırlanıyor..."):
                zipped=_single_zip(hid,selected,frozen)
            st.session_state["v53_package"]=(hid,zipped)
        except Exception as exc:
            st.error("V53 rapor hazırlanamadı: "+str(exc))
    package=st.session_state.get("v53_package")
    if package and package[0]==hid:
        st.download_button("⬇️ V53 SAATLIK AİLELER TEK ZIP İNDİR — BANA GÖNDER",
                           data=package[1],
                           file_name=f"V53_SAATLIK_2_10_AILELER_{selected}_TEK_RAPOR.zip",
                           mime="application/zip",type="primary",
                           key="v53_download",use_container_width=True)
    elif package:
        st.info("Veriler/gün değişmiş; yeni rapor oluşturmak için tekrar bas.")
    st.caption("Dönemsel tekrarlar açıklayıcı istatistiktir; gelecek çekilişi bildirmez.")
