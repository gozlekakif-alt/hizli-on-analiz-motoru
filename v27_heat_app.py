# -*- coding: utf-8 -*-
"""V27 Streamlit view: six experimental tiers vs exact old four 20s.

Only uses completed pretarget draws. Uses the already connected V10
'veri.txt' history; no changes to GitHub data or existing motors.
"""
from collections import Counter, defaultdict
import streamlit as st
from v21_aile_yasam_dongusu import clock, csv_bytes
from v27_alti_isi_koltuk import (
    GROUPS,COUNTS,LOOKBACKS,METHODS,DECAY,make_index,classify_before,
    bins_for_state,largest_remainder,fitted_rate,evaluate_target
)


def _row_for_before(history, window,method):
    ordered=[{**r,"mask":sum(1<<(n-1) for n in r["nums"])}
             for r in history]
    records,p,e=make_index(ordered)
    t=len(records)
    if t<max(window,12):
        return None
    grp,direct,score=classify_before(t,window,method,p,e)
    counts,members=bins_for_state(grp,direct)
    # If no trained historical rates available, use unconditional .25 as
    # an honest baseline; don't mislabel it as fitted or predictive.
    seats=largest_remainder([counts[i]*.25 for i in range(18)],members)
    raw_scores=sorted(range(1,81),key=lambda n:(e[n][t],n))
    old={name:raw_scores[q*20:(q+1)*20]
         for q,name in enumerate(("S","OD","OY","YS"))}
    return grp,direct,score,seats,members,old


def render_v27(draws):
    st.subheader("🌡️ V27 — Altı Isı Basamağı / 20 Koltuk / Geçmiş Penceresi")
    st.info("Önemli köken bilgisi: Eski çalışmamızın doğrulanmış 12 çekiliş "
            "yarı ömürlü modeli **S / OD / OY / YS** olarak dört adet 20'lik "
            "havuzdur; gün başında sıfırlanmaz. Buradaki altı sıcaklık basamağı "
            "eski kaydın aynısı değil, YENİ DENEYSEL 13/13/14/14/13/13 "
            "yüzdelik sınıflandırmasıdır.")
    st.caption("Hedefteki 20 sayının hangi sıcaklık havuzlarından geldiğini "
               "istatistiksel koltuk olarak inceleriz. Fiziksel çekme sırası değil.")
    ordered=sorted(draws,key=lambda d:(d["day"],int(d["pos"])))
    if not ordered:
        st.warning("Kayıt yok.")
        return
    dates=sorted({d["day"] for d in ordered})
    selected=st.selectbox("İncelenecek gün",dates,index=len(dates)-1,key="v27_day")
    day=[d for d in ordered if d["day"]==selected]
    available=sorted({int(d["pos"]) for d in day})
    if not available:
        return
    pos=st.selectbox("Hedef çekiliş sıra",available,
                     index=len(available)-1,
                     format_func=lambda p:f"{p}. çekiliş ({clock(p)[0]})",
                     key="v27_pos")
    window=st.select_slider("Kaç geçmiş GERÇEK çekilişe bakılsın?",
                            options=list(LOOKBACKS),value=144,key="v27_window")
    method=st.radio("Sıcaklık hesabı",
                    list(METHODS),horizontal=True,key="v27_method")
    if st.button("🌡️ Koltuk ve sıcaklık sıralamasını hesapla",key="v27_calc"):
        history=[d for d in ordered if
                 (d["day"],int(d["pos"]))<(selected,pos)]
        with st.spinner("Önceki gerçek çekilişlerden 80 kimlik hesaplanıyor"):
            result=_row_for_before(history,window,method)
        if result is None:
            st.warning("Bu pencere için yeterli geçmiş gerçek çekiliş yok.")
            return
        grp,direction,score,seats,members,old=result
        st.session_state["v27_snapshot"]=(selected,pos,window,method,result)
    saved=st.session_state.get("v27_snapshot")
    if saved and saved[:4]==(selected,pos,window,method):
        _,_,_,_,result=saved
        grp,direction,score,seats,members,old=result
        target=next((d for d in day if d["pos"]==pos),None)
        observed=set(target["nums"]) if target else set()
        rows=[]
        for j,name in enumerate(GROUPS):
            found=sum(n in observed for n in members[j])
            rows.append({
                "Sıcaklık":name,"80'de üyeler":COUNTS[j],
                "Adil RNG 20 koltuk beklentisi":round(COUNTS[j]/4,2),
                "RNG ile koltuk tahmini":seats[j],
                "Gerçek hedefte gelen":found,
                "Sayılar":"-".join(f"{n:02d}" for n in members[j])
            })
        st.markdown("#### Deneysel altı basamak: 20 gerçek koltuğun kaynağı")
        st.dataframe(rows,hide_index=True,use_container_width=True)
        oldrows=[{
           "Eski 4'lü havuz":name,"Üye":20,
           "Hedefte gelen":sum(n in observed for n in numbers),
           "RNG beklenti":5,
           "Sayılar":"-".join(f"{n:02d}" for n in numbers)
        } for name,numbers in old.items()]
        st.markdown("#### Eski gerçek referans: S / OD / OY / YS dört 20'lik")
        st.dataframe(oldrows,hide_index=True,use_container_width=True)
        st.caption("Bu sayfada gösterilen koltuk tahmini henüz geçmişte "
                   "öğrenilmiş bir öngörü modeli değil, %25 RNG tabanıdır. "
                   "Öğrenme ve bağımsız test sonuçları GitHub V27 raporundadır.")
        st.download_button("⬇️ Altı basamaklı koltuklar",csv_bytes(rows),
                           "V27_6_ISI_KOLTUK.csv","text/csv",key="v27_dl6")
        st.download_button("⬇️ Eski 4x20 koltuklar",csv_bytes(oldrows),
                           "V27_ESKI_4x20_KOLTUK.csv","text/csv",key="v27_dl4")
    st.divider()
    st.caption("GitHub Actions / V27 6 Isi 20 Koltuk Gecmis Testi: "
               "6–1519 geçmiş çekiliş penceresi, 18 gün kalibrasyon, "
               "18 gün model seçimi ve 36 gün sabit bağımsız test.")
