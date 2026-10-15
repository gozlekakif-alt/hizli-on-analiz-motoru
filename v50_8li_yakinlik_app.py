# -*- coding: utf-8 -*-
"""Read-only V50 Streamlit page. Computes a single ZIP locally; never writes GitHub."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import streamlit as st

from v45_sinyal_kor_test import SLOTS
from v50_8li_yakinlik_kor import START, N_DAYS, run, build_zip

@st.cache_data(ttl=600, show_spinner=False)
def _analyze(key, data):
    full={}
    for day,entries in data:
        full[date.fromisoformat(day)]=[
           {"id":no,"day":day,"time":clock,"nums":frozenset(nums)}
           for no,clock,nums in entries
        ]
    result=run(full,{},[],[])
    return {
        "historic":result[3],
        "new":result[4],
        "content":build_zip(*result),
    }

def render_v50(draws):
    st.subheader("🧬 V50 — 8’li Aile / 7–12. Çekiliş Testi")
    st.caption("5–30 dakikada ikinci kez birlikte görülen 8 sayıyı dondurur; "
               "sonraki 7, 8, 9, 10, 11 ve 12. hedefte 8/8 ve 7/8 sonucunu "
               "aynı hedefteki rastgele kontrolle kıyaslar.")
    byday=defaultdict(dict)
    errors=[]
    for r in draws:
        try:
            day=str(r["day"])
            slot=int(r["pos"])
            nums=tuple(sorted(map(int,r["nums"])))
            if not (1<=slot<=217 and len(nums)==20 and
                    len(set(nums))==20 and 1<=nums[0]<=nums[-1]<=80):
                continue
            item=(int(r["no"]),SLOTS[slot-1],nums)
            if slot in byday[day] and byday[day][slot]!=item:
                errors.append(f"{day} #{slot}")
                continue
            byday[day][slot]=item
        except (KeyError,ValueError,TypeError):
            continue
    complete=[(day,tuple(positions[i] for i in range(1,218)))
              for day,positions in sorted(byday.items())
              if len(positions)==217 and set(positions)==set(range(1,218))]
    new_days=[day for day,entries in complete if day>=START.isoformat()]
    eligible=new_days[:N_DAYS]
    a,b,c=st.columns(3)
    a.metric("Yeni tam gün",f"{len(eligible)}/{N_DAYS}")
    b.metric("Seçilen 8’li aile", "1 / yakın olay")
    c.metric("Hedef pencere", "7–12. el")
    if errors:
        st.warning(f"{len(errors)} çakışan kayıt var; kaynak dosyayı doğrula.")
    if len(eligible)<N_DAYS:
        st.warning("14 yeni tam gün henüz tamamlanmadı. "
                   "Geçmişin yüksek görünen 8/8 sonucu ileri tahmin kanıtı değildir.")
    else:
        st.info("14 tam gün birikti. Sonuç yalnız bir araştırma karşılaştırmasıdır; "
                "çoklu hipotez düzeltmesi ve bağımsız tekrar gerekir.")
    st.markdown("#### Dondurulmuş kural")
    st.write("Aynı gün 5–30 dakika arayla iki çekilişte **en az 8 ortak sayı** "
             "varsa, ortak sayıların **küçükten büyüğe ilk sekizini** al. "
             "İkinci görülmeden sonraki **7–12. çekilişlerde** sınav yap.")
    st.caption("Kontrol için aynı tetik anında 8 rastgele sayı da dondurulur. "
               "Hedef çekilişi görülmeden seçim tamamlanır.")
    st.markdown("#### Tek dosya raporu")
    ident=hashlib.sha256(repr(complete).encode()).hexdigest()
    if st.button("▶️ V50 — TÜM SİNYALLERİ TEST ET",
                 key="v50_run",type="primary",use_container_width=True):
        try:
            with st.spinner("72 günlük geçmiş ve yeni tam günler değerlendiriliyor..."):
                result=_analyze(ident,tuple(complete))
            st.session_state["v50_report"]={"hash":ident,"result":result}
        except Exception as exc:
            st.error("V50 hata: "+str(exc))
    report=st.session_state.get("v50_report")
    if not report:
        st.info("Geçmiş araştırma sonuçları ve yeni gün durumunu "
                "tek ZIP indirmek için önce yukarıdaki test düğmesine bas.")
        return
    if report["hash"]!=ident:
        st.warning("veri.txt değişti. Güncel rapor için testi yeniden çalıştır.")
        return
    info=report["result"]
    old=info["historic"]
    future=info["new"]
    st.markdown("#### Eski 72 gün — keşif, bağımsız test değil")
    a,b,c=st.columns(3)
    a.metric("8/8 gerçekleşen",old["observed_8of8"])
    b.metric("RNG teorik",f'{old["expected_8of8"]:.2f}')
    c.metric("Rastgele 8’li kontrol",old["random_8of8"])
    st.markdown("#### Yeni günler — ileri kontrol")
    a,b,c=st.columns(3)
    a.metric("Test fırsatı",future["opportunities"])
    b.metric("8/8",future["observed_8of8"])
    c.metric("Rastgele 8/8",future["random_8of8"])
    st.dataframe([{
        "Tarih":r["day"],"Test":r["targets"],"8/8":r["win8"],
        "Kontrol 8/8":r["random8"],"7/8+":r["win7"],
        "Kontrol 7/8+":r["random7"]}
        for r in future["per_day"]
    ],hide_index=True,use_container_width=True)
    st.download_button(
        "⬇️ V50 TEK ZIP İNDİR — BANA GÖNDER",
        data=info["content"],
        file_name="V50_8LI_7_12_YAKINLIK_TEK_RAPOR.zip",
        mime="application/zip",
        key="v50_download",type="primary",use_container_width=True)
    st.caption("ZIP içinde geçmiş her hedef, yeni hedefler, her tetikleyici "
               "aile, gün gün isabet ve yöntem/uyarılar var. GitHub’a yönlendirme yok.")
