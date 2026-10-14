# -*- coding: utf-8 -*-
"""V28 Streamlit drilldown: every ball's H1..H12 hourly temperature journey.

Uses pre-draw temperature score, no lookahead at future unobserved draws.
Old S/OD/OY/YS 4x20 is a separate historical reference, never relabeled.
"""
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import streamlit as st
from v21_aile_yasam_dongusu import HOUR_STARTS,clock,csv_bytes
from v28_dijital_kaplan_dongu import (
    BALLS,HEAT_MACRO,HEAT_SIX,DECAY,state_before,hour_info,run
)


def inspect_hour(draws,day,start):
    ordered=sorted(draws,key=lambda x:(x["day"],x["pos"]))
    if not any(d["day"]==day and d["pos"]==start for d in ordered):
        raise ValueError("Selected hour start not in data")
    score=[0.]*81
    hourpath=defaultdict(list)
    previousmacro=None
    crossday=None
    for d in ordered:
        if (d["day"],d["pos"])>(day,start+11):
            break
        six,macro=state_before(score)
        if d["day"]==day and d["pos"] in range(start,start+12):
            slot=d["pos"]-start+1
            ns=set(d["nums"])
            for n in BALLS:
                hourpath[n].append({
                    "H":slot,"macro":macro[n],"six":six[n],
                    "hit":int(n in ns),"score":score[n]
                })
        ns=set(d["nums"])
        score=[0.]+[score[n]*DECAY+int(n in ns) for n in BALLS]
        previousmacro=macro
    rows=[]
    for n in BALLS:
        path=hourpath[n]
        if not path:continue
        row={"Sayı":n,
             "İlk sınıf":HEAT_MACRO[path[0]["macro"]],
             "Son bilinen sınıf":HEAT_MACRO[path[-1]["macro"]],
             "6 basamak son":HEAT_SIX[path[-1]["six"]],
             "H değişimi":sum(path[j]["macro"]!=path[j-1]["macro"] for j in range(1,len(path))),
             "Bu saatte çıktı":sum(x["hit"] for x in path)}
        for typ,i in zip(("Soğuk","Ilık","Sıcak"),range(3)):
            row[f"{typ} H sayısı"]=sum(x["macro"]==i for x in path)
            longest=run=0
            for x in path:
                run=run+1 if x["macro"]==i else 0
                longest=max(longest,run)
            row[f"{typ} en uzun H kalış"]=longest
        for h in range(1,13):
            val=next((x for x in path if x["H"]==h),None)
            row[f"H{h}"]=(("S" if val["macro"]==0 else "I" if val["macro"]==1 else "C")
                         +("●" if val["hit"] else "·")) if val else ""
        rows.append(row)
    return rows


def render_v28(draws):
    st.subheader("🐅 V28 Dijital Kaplan — 80 Sayının H1–H12 Isı Yolculuğu")
    st.info("H1–H12, aynı gerçek saatin **birinci–on ikinci çekilişleridir**. "
            "01:02 tek çekiliştir; 01:02 ile 07:02 arası 6 saat boşluktur. "
            "Her sayının sıcaklık hafızası sonraki güne devreder.")
    st.caption("Altı deneysel ısı basamağı, eski doğrulanmış 4×20 S/OD/OY/YS "
               "sistemi ile aynı şey değildir. Buradaki S = soğuk, "
               "I = ılık, C = sıcak; ● sayı çıktı, · çıkmadı.")
    if not draws:
        st.warning("Henüz çekiliş yüklenmedi.")
        return
    days=defaultdict(dict)
    for d in draws:
        day=d["day"]
        pos=int(d["pos"])
        if pos:
            days[day][pos]=d
    dates=sorted(days)
    day=st.selectbox("Gün",dates,index=len(dates)-1,key="v28_date")
    positions=days[day]
    starts=[p for p in HOUR_STARTS if p in positions]
    if not starts:
        st.warning("Günün ilk saat çekilişi henüz yok.")
        return
    start=st.selectbox("Hangi 12 çekilişlik saat?",starts,index=len(starts)-1,
                       format_func=lambda p:clock(p)[0]+"–"+clock(p+11)[0],
                       key="v28_start")
    if st.button("🐅 80 sayının saatlik yolculuğunu göster",key="v28_go"):
        with st.spinner("Geçmişi günler arasında kesmeden 12 yarı ömürle işliyorum"):
            rows=inspect_hour(draws,day,start)
        st.session_state["v28_hour"]=(day,start,rows)
    saved=st.session_state.get("v28_hour")
    if saved and saved[:2]==(day,start):
        rows=saved[2]
        selected=st.select_slider("İlgilendiğin H pozisyonu",
                                   options=list(range(1,13)),value=6,
                                   key="v28_h")
        known=sum(bool(r[f"H{selected}"]) for r in rows)
        st.caption(f"H{selected}: {known} sayı için o anın durumu gözlenmiştir.")
        st.markdown("#### Her sayının H1–H12 sıcaklık yolu")
        st.dataframe(rows,hide_index=True,use_container_width=True)
        num=st.number_input("Tek sayının yolculuğu",min_value=1,max_value=80,
                            value=19,step=1,key="v28_one")
        match=next((r for r in rows if r["Sayı"]==num),None)
        if match:
            st.write(match)
        st.download_button("⬇️ 80 sayı, H1–H12 tam saatlik TXT/CSV",
                           csv_bytes(rows),file_name="V28_80_SAYI_H1_H12.csv",
                           mime="text/csv",key="v28_download")
    st.divider()
    st.markdown("### 🔬 72 günlük tüm analizi Streamlit'te çalıştır")
    st.caption(
        "İki ayrı zaman ölçeği: bir saatin 12 çekilişi ve 12 ardışık "
        "GERÇEK saat. Her sayı için kalışlar, 6 sıcaklık sınıfı geçişleri, "
        "günler arası döngüler, RNG karşılaştırması ve 20 sayı sınaması."
    )
    complete=[x for x,pos in days.items()
              if len(pos)==217 and set(pos)==set(range(1,218))]
    col1,col2,col3=st.columns(3)
    col1.metric("Tam gün",len(complete))
    col2.metric("Çekiliş",len(complete)*217)
    col3.metric("80 sayı × saat",min(72,len(complete))*18*80)
    nulls=st.select_slider(
        "Rastgele RNG denetimi kaç tekrar?",
        options=[3,6,12,24],value=6,key="v28_null_repetitions")
    if len(complete)<72:
        st.warning("Bu analizin sabit 36+36 karşılaştırması için en az 72 tam gün gerekir.")
    if st.button("🐅 TÜM 72 GÜNÜ ANALİZ ET",
                 disabled=len(complete)<72,key="v28_run_all"):
        with st.spinner("Gerçek çekilişler ve aynı saatlerde rastgele kontrol akışları hesaplanıyor..."):
            try:
                raw=_v28_source_as_txt(draws)
                digest=sha256(raw.encode("utf-8")).hexdigest()
                payload,meta,macro,forecast,ci=_v28_cached_full_run(raw,int(nulls))
                st.session_state["v28_completed"]=(digest,int(nulls),payload,meta,macro,forecast,ci)
            except Exception as exc:
                st.error("V28 analiz hatası: "+str(exc))
    saved=st.session_state.get("v28_completed")
    if saved:
        digest,reps,payload,meta,macro,forecast,ci=saved
        st.success("V28 tam rapor hazır.")
        if reps!=int(nulls):
            st.warning("Bu sonuç önceki RNG tekrar sayısına aittir.")
        st.download_button(
            "⬇️ TÜM V28 ANALİZİNİ TEK ZIP İNDİR",
            data=payload,
            file_name="V28_DIJITAL_KAPLAN_72_GUN_TAM_ANALIZ.zip",
            mime="application/zip",
            key="v28_all_zip")
        st.caption(f"{meta.get('Tam gün','?')} tam gün · "
                   f"{meta.get('Saat','?')} gerçek saat · "
                   f"{meta.get('Saat içi 80 sayı profili','?')} sayı-saat kaydı · "
                   f"{reps} RNG benzetimi")
        with st.expander("🎯 36 günlük 20 sayı tahmin ve rastgele kontrol",expanded=True):
            st.dataframe(forecast,hide_index=True,use_container_width=True)
            st.dataframe(ci,hide_index=True,use_container_width=True)
        with st.expander("🔄 Soğuk–ılık–sıcak 3×3 bütün geçişler"):
            st.dataframe(macro,hide_index=True,use_container_width=True)
        with st.expander("📅 Günler arasında süren döngüler"):
            st.json(meta.get("Ardışık gün benzerliği",{}))
        st.caption("ZIP içinde sayıların bir saatteki 12 çekilişi, "
                   "ayrıca 12 GERÇEK SAAT boyunca H1-H12 yolculuğu, "
                   "tüm kalışlar ve RNG denetimleri ayrı CSV dosyalarındadır.")
    st.caption("Büyük analiz yalnız düğmeye bastığında çalışır; "
               "GitHub veri.txt ve eski motorları değiştirmez.")


def _v28_source_as_txt(draws):
    """Export valid fetched draws to the original milli piyango raw format
    without writing to the repository."""
    ordered=sorted(draws,key=lambda d:(d["day"],int(d["pos"])))
    return "\n".join(
        f"{int(d['no'])};{datetime.fromisoformat(str(d['dt'])).strftime('%d.%m.%Y %H:%M')};"
        +",".join(str(int(n)) for n in d["nums"])
        for d in ordered
    )


@st.cache_data(show_spinner=False,max_entries=2)
def _v28_cached_full_run(data_text,null_reps):
    """Only explicit user button triggers heavy 72-day execution."""
    reports,meta,macro,_durations,forecast,ci=run(
        data_text,rng_reps=int(null_reps),detailed=True)
    buffer=BytesIO()
    with ZipFile(buffer,"w",compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for filename,blob in reports.items():
            archive.writestr(filename,blob)
    return buffer.getvalue(),meta,macro,forecast,ci
