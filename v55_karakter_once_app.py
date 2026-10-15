# -*- coding: utf-8 -*-
"""V55 Streamlit: character-first prospective selection, no-leakage audit."""
from __future__ import annotations
import hashlib
from datetime import date

import streamlit as st

from v45_sinyal_kor_test import SLOTS
from v52_ayni_cekilis_eslikci_217 import normalise_rows
from v55_karakter_once_kor_motor import (
    START_FORWARD,N_FORWARD_DAYS,CONTROLS,MIN_TRAIN_HOURS,
    audit,metrics,build_zip,day_comparison
)

@st.cache_data(ttl=900,max_entries=1,show_spinner=False)
def _compute(checksum,packed):
    full={}
    for day,rows in packed:
        if len(rows)!=217 or {p for p,ident,t,n in rows}!=set(range(1,218)):
            continue
        full[date.fromisoformat(day)]=[
             {"day":day,"id":ident,"time":clock,"nums":frozenset(nums)}
             for pos,ident,clock,nums in rows]
    characters,records=audit(full)
    stats=metrics(characters,records)
    return characters,records,stats,build_zip(full,characters,records,stats)

def render_v55(draws):
    st.subheader("🧠 V55 — Önce Karakter, Sonra Sayı Seçimi")
    st.caption("Önce saatlik oyun karakterini tahmin eder; ancak daha önceki saatlerde "
      "tahmin hatası rastgele beklentiden daha iyi çıkarsa sinyal üretir. "
      "Karakter seçimi ile kupon seçim başarısını AYRI sınar.")
    inputrows=[]
    for r in draws:
        try:
            pos=int(r["pos"])
            if not (1<=pos<=217):continue
            inputrows.append({"day":str(r["day"]),"id":int(r["no"]),
                 "pos":pos,"time":SLOTS[pos-1],"nums":tuple(sorted(map(int,r["nums"])))})
        except (TypeError,KeyError,ValueError):continue
    days,issues=normalise_rows(inputrows)
    full=tuple((d,tuple((x["pos"],x["id"],x["time"],x["nums"]) for x in rows))
               for d,rows in sorted(days.items())
               if len(rows)==217 and {x["pos"] for x in rows}==set(range(1,218)))
    nfuture=len([x for x,y in full if x>=str(START_FORWARD)][:N_FORWARD_DAYS])
    a,b,c=st.columns(3)
    a.metric("Tam gün",len(full))
    b.metric("Yeni kör gün",f"{nfuture}/{N_FORWARD_DAYS}")
    c.metric("Her saat", "İlk 6 → Son 6")
    if issues:st.warning(f"{len(issues)} geçersiz/çakışan kayıt değerlendirme dışı.")
    if not full:
        st.info("217/217 çekiliş içeren bir gün bulunamadı. veri.txt içinde tam gün gerekli.")
        return
    st.markdown("#### 1. Karakter sınavı")
    st.write("Bir sonraki altı çekilişin **8 sayı bandına, 5 sıcaklık havuzuna dağılımını**, "
       "önceki 20 sayıyla ortaklık miktarını ve seçili 2’li/3’lü aile tekrarını "
       "önceden tahmin ediyoruz. Bunlar rastgele beklentiye göre puanlanıyor.")
    st.markdown("#### 2. Kupon sınavı")
    st.write("Karakter tahmini anlamlı geçmiş başarı gösterirse, bu tahmine göre "
       "10 sayı seçiliyor. **Karakter kullanmayan ve rastgele 10’lu** kontrol "
       "aynı çekilişte eşit şartlarda sınanıyor.")
    st.caption("Tahmin modeli geçmiş saatlerle öğrenir. Her saatin altı hedef sonucu "
       "gelmeden karakter ve tüm kuponlar dondurulur. Uygun sinyal yoksa kupon önerilmez; "
       "gölge test sonuçları ayrı tutulur.")
    checksum=hashlib.sha256(repr(full).encode()).hexdigest()
    if st.button("▶️ V55 KARAKTER ÖĞREN + KÖR TESTİ ÇALIŞTIR",
                 key="v55_execute",type="primary",use_container_width=True):
        try:
            with st.spinner("Geçmiş saatleri sırayla öğrenip geleceği görmeden test ediyor..."):
                res=_compute(checksum,full)
            st.session_state["v55_report"]=(checksum,res)
        except Exception as err:
            st.error("V55 test hatası: "+str(err))
    result=st.session_state.get("v55_report")
    if not result:
        st.info("İlk test için yukarıdaki düğmeye bas. Rapor hazır olunca tek ZIP indirebilirsin.")
        return
    if result[0]!=checksum:
        st.warning("veri.txt güncellendi. Güncel rapor için testi yeniden çalıştır.")
        return
    characters,records,stats,zipped=result[1]
    selected=st.selectbox("Sonucu incelenecek dönem",
        ["GERIYE_DONUK","ILERI_14"],
        format_func=lambda s:"Geçmiş kontrol" if s=="GERIYE_DONUK"
                  else "16 Ekim sonrası yeni 14 gün",
        key="v55_phase")
    chars=[r for r in characters if r["phase"]==selected]
    if selected=="ILERI_14" and not chars:
        st.info("Henüz ileri testte tam gün yok. Bugünkü tarihli sonuçlardan "
                "geleceği bildiğimizi iddia etmiyoruz.")
    qualified=[r for r in chars if r["trained"]>=MIN_TRAIN_HOURS]
    x,y,z=st.columns(3)
    x.metric("Değerlendirilen saat",len(qualified))
    y.metric("Karakteri uygun sinyal",sum(c["signal"] for c in qualified))
    z.metric("Kontrol sayısı",2)
    st.markdown("#### Önce karakteri doğru bildik mi?")
    cc=[x for x in stats if x["phase"]==selected and x["metric"].startswith("KARAKTER_")]
    st.dataframe([{"Karakter":r["metric"].removeprefix("KARAKTER_"),
        "Model hatası":r["model"],"Rastgele model hatası":r["baseline"],
        "Fark (eksi daha iyi)":r["delta_model_minus_baseline"]} for r in cc],
        hide_index=True,use_container_width=True)
    st.markdown("#### Karakter doğruysa sayı seçiminde fark var mı?")
    comparison=[x for x in stats if x["phase"]==selected and
                x["metric"].startswith("KUPON_")]
    st.dataframe([{"Ölçüm":r["metric"],"Hedef":r["samples"],
                  "Ortalama 10’lu isabet":r["model"],
                  "2,5’a göre fark":r["delta_model_minus_baseline"],
                  "Ayrıntı":r["note"]} for r in comparison],
                  hide_index=True,use_container_width=True,height=300)
    st.markdown("#### Saat saat tahmin ve gerçek karakter")
    shown=[r for r in chars if r["trained"]>=MIN_TRAIN_HOURS][-40:]
    st.dataframe([{"Gün":r["day"],"Saat":r["hour"],
        "Sinyal":("VAR" if r["signal"] else "YOK"),
        "Bant tahmini":r["pred_band"],"Gerçek bant":r["actual_band"],
        "Örtüşme tahmini":r["pred_overlap"],
        "Gerçek örtüşme":r["actual_overlap"]} for r in shown],
        hide_index=True,use_container_width=True,height=330)
    st.download_button("⬇️ V55 KARAKTER + KUPON KÖR TEST TEK ZIP",
        data=zipped,mime="application/zip",key="v55_download",
        file_name="V55_ONCE_KARAKTER_SONRA_KUPON_KOR_TEK_RAPOR.zip",
        type="primary",use_container_width=True)
    st.caption("Bant/sıcaklık/örtüşme hatası rastgele dağılımdan tutarlı biçimde "
       "düşmedikçe karakter öğrenildi veya isabet artırıldı denemez.")
