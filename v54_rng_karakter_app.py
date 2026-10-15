# -*- coding: utf-8 -*-
"""V54 Streamlit: 80-state character movement, family migration, RNG fairness check."""
from __future__ import annotations
import hashlib
import streamlit as st
from datetime import date

from v45_sinyal_kor_test import SLOTS
from v52_ayni_cekilis_eslikci_217 import normalise_rows
from v54_rng_karakter_gecis import (
    START_FUTURE,N_FUTURE_DAYS,COLDS,
    analyze,build_zip
)

@st.cache_data(ttl=900,max_entries=2,show_spinner=False)
def _cached_run(content_hash, frozen, chosen, n_sims):
    full={}
    for day,items in frozen:
        if len(items)!=217 or {slot for slot,_,_,_ in items}!=set(range(1,218)):
            continue
        full[date.fromisoformat(day)]=[
            {"day":day,"time":clock,"id":ident,"nums":frozenset(nums)}
            for slot,ident,clock,nums in items
        ]
    result=analyze(full,date.fromisoformat(chosen),n_sims)
    return result,build_zip(result)

def render_v54(draws):
    st.subheader("🧠 V54 — RNG Karakteri ve Aile Dönüşümü")
    st.caption("80 sayının hareketli sıcaklık/yön yolculuğunu, saatten saate 3'lü–5'li "
        "ailelerin tam devam veya bir sayı değiştirerek dönüşmesini izler. "
        "Bağımsız 20/80 sanal çekiliş günleriyle kıyaslar.")
    incoming=[]
    for row in draws:
        try:
            pos=int(row["pos"])
            if not 1<=pos<=217: continue
            incoming.append({"day":str(row["day"]),"pos":pos,"id":int(row["no"]),
                "time":SLOTS[pos-1],"nums":tuple(sorted(map(int,row["nums"])))})
        except (KeyError,ValueError,TypeError):continue
    days,issues=normalise_rows(incoming)
    full_dates=sorted(d for d,rows in days.items()
                      if len(rows)==217 and {x["pos"] for x in rows}==set(range(1,218)))
    if not full_dates:
        st.warning("Henüz 217 çekilişli tam gün yok. veri.txt içindeki saatleri tamamla.")
        return
    new=[d for d in full_dates if d>=START_FUTURE.isoformat()][:N_FUTURE_DAYS]
    a,b,c=st.columns(3)
    a.metric("Tam günlük veri",len(full_dates))
    b.metric("Yeni kör test günü",f"{len(new)}/{N_FUTURE_DAYS}")
    c.metric("Bağımsız RNG", "20 / 80")
    if issues: st.warning(f"{len(issues)} hatalı/çakışan veri rapora katılmadı.")
    selected=st.selectbox("İncelenecek gün",list(reversed(full_dates)),
        key="v54_day")
    size=st.selectbox("Aile büyüklüğü",[3,4,5],
        format_func=lambda k:f"{k}'lü aile",key="v54_k")
    simulations=st.selectbox("Sanal RNG gün sayısı",[20,40,80],index=1,
        key="v54_sim_count")
    st.markdown("#### İncelediğimiz gerçek davranış")
    st.write("Bir aile önceki saatin güçlü ilk 12 ailesindeyse, "
        "sonraki saatte **aynen mi kaldı, bir sayısı değişerek mi geri geldi, "
        "yoksa lider listesinden mi çıktı** diye bakıyoruz. "
        "Her aile aynı saat içinde en az iki kez birlikte görünmüş olmalı.")
    st.caption("Ailelerin bir sayıyla 'dönüşmesi' nedensel bağ anlamına gelmez; "
        "benzer aileleri yalnızca sayısal olarak eşleştiriyoruz.")
    st.markdown("#### İlk 6 → Sonraki 6 kör deneme")
    st.write("Saatin ilk 6 çekilişi geldikten sonra sıcak72, soğuk72, "
        "yükselen12, ilk6 sıcak ve eşlikçi-geçiş kurallarıyla 10'lu listeleri "
        "sabitliyoruz. Sonraki 6 hedef sonucunu ancak daha sonra puanlıyoruz.")
    st.caption(f"Yeni bağımsız ileri değerlendirme {START_FUTURE:%d.%m.%Y} "
       f"ve sonrasındaki ilk {N_FUTURE_DAYS} tam güne uygulanıyor.")
    frozen=tuple((day,tuple((r["pos"],r["id"],r["time"],r["nums"])
         for r in items)) for day,items in sorted(days.items()) if day in full_dates)
    key=hashlib.sha256(repr((frozen,selected,simulations)).encode()).hexdigest()
    if st.button("▶️ V54 KARAKTER + AİLE + RNG KARŞILAŞTIRMASINI ÇALIŞTIR",
        key="v54_start",type="primary",use_container_width=True):
        try:
            with st.spinner("RNG sanal günleri ve aile geçişleri karşılaştırılıyor..."):
                info,zipped=_cached_run(key,frozen,selected,simulations)
            st.session_state["v54_latest"]=(key,info,zipped)
        except Exception as exc:
            st.error(f"V54 hesaplama hatası: {exc}")
    current=st.session_state.get("v54_latest")
    if not current:
        st.info("Raporu hazırlamak ve indirmek için yukarıdaki düğmeye bas.")
        return
    if current[0]!=key:
        st.warning("Veri veya filtre değişti. Güncel sonuç için testi yeniden başlat.")
        return
    info,zipped=current[1:]
    m=info["meta"]
    st.success(f"{m['selected']} günü: 217 çekiliş, {m['simulation_days']} "
               "bağımsız sanal gün karşılaştırıldı.")
    st.markdown("#### Gerçek ve rastgele aile dönüşümü")
    comparison=[x for x in info["null"] if x["size"]==size]
    st.dataframe([{
         "Durum":x["kind"],"Gerçek":x["observed"],"RNG ortalama":x["rng_average"],
         "RNG %5":x["rng_q05"],"RNG %95":x["rng_q95"]
    } for x in comparison],hide_index=True,use_container_width=True)
    st.markdown("#### Saatten saate değişen aile örnekleri")
    examples=[x for x in info["change_details"] if x["family_size"]==size
              and x["status"] in ("AYNI_AILE_DEVAM","BIR_SAYI_DEGISTI")][:40]
    st.dataframe([{"Saat":x["from"]+" → "+x["to"],"Eski aile":x["old_family"],
                  "Yeni aile":x["new_family"],"Durum":x["status"]} for x in examples],
                  hide_index=True,use_container_width=True,height=270)
    st.markdown("#### İlk 6 → Sonraki 6 test ortalamaları")
    st.dataframe([{"Dönem":x["period"],"Motor":x["model"],
      "Hedef":x["targets"],"Ortalama / 10":x["mean"],"Rastgele beklenti":2.5,
      "7 veya üzeri":x["hits_7plus"]}
      for x in info["audit_summary"]],hide_index=True,use_container_width=True)
    st.markdown("#### 80 sayının sıcaklık geçişleri")
    chosen_number=st.selectbox("Sayı seç",list(range(1,81)),index=18,key="v54_number")
    character=[r for r in info["trajectory"] if r["number"]==chosen_number]
    st.dataframe([{"Çekiliş":x["slot"],"Saat":x["time"],"Çıktı":x["drawn"],
       "Önceki havuz":x["before_state"],"Sonraki havuz":x["after_state"],
       "Yön":x["before_direction"],"72'de görülme":x["before72"],
       "Bekleme":x["gap_before"]} for x in character],
       hide_index=True,use_container_width=True,height=250)
    st.download_button("⬇️ V54 KARAKTER + AİLE + RNG TEK ZIP İNDİR",
        data=zipped, file_name=f"V54_RNG_KARAKTER_AILE_DONUSUMU_{selected}_TEK_ZIP.zip",
        mime="application/zip",type="primary",key="v54_download",use_container_width=True)
    st.caption("ZIP: 80×217 sayı kimliği, saatlik aile dönüşümü, sanal RNG karşılaştırması, "
         "ilk6/son6 ileri görmeden test ve günlük aile bağlantısı. "
         "Betimleyici benzerlikten otomatik tahmin başarısı çıkarılmaz.")
