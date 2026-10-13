# -*- coding: utf-8 -*-
"""V25 Streamlit: available 6-draw snapshot -> non-leaking family DNA + 10s."""
import streamlit as st
from collections import defaultdict
from v21_aile_yasam_dongusu import HOUR_STARTS, clock, csv_bytes, read_catalog
from v25_aile_dna_kupon import (
    new_state,update_history,choose_family_panel,coupon_sets,
    coupon_event,predict_satellites,catalog_events
)


def format_hour(start):
    return clock(start)[0] + "–" + clock(start+11)[0]


def render_v25(draws,family_text=""):
    st.subheader("🧬 V25 — Aile DNA / İlk → İkinci → Üçüncü / 10'lu Kupon")
    st.caption("Saatin ilk 6 çekilişiyle, günün daha önceki gerçek çekilişleri "
               "kullanılarak aileler ve 10'lu kuponlar üretilir. "
               "7–12. çekilişin sonuçları seçime sızmaz.")
    st.info("1. çıkış: doğum, 2. çıkış: tekrar, 3 ve sonrası: olgun evre. "
            "2,3,4'lü çekirdekler aile durumuna göre ayrılır. "
            "5–10'lu kayıtlı aileler tam görünüş kontrolünde izlenir. "
            "Üretilen kuponlar deneysel; kazanma garantisi yoktur.")
    byday=defaultdict(dict)
    for r in draws:
        if r.get("pos"):
            byday[r["day"]][int(r["pos"])]={
                **r,"mask":sum(1<<(int(n)-1) for n in r["nums"])
            }
    if not byday:
        st.warning("Çekiliş kaydı bulunamadı.")
        return
    dates=sorted(byday)
    selected=st.selectbox("İncelenecek gün",dates,index=len(dates)-1,key="v25_date")
    daily=byday[selected]
    eligible=[start for start in HOUR_STARTS if
              all(p in daily for p in range(1,start+6))]
    if not eligible:
        st.warning("Bu gün henüz ilk 6 çekiliş tamamlanmadı veya sıralamada boşluk var.")
        return
    start=st.selectbox("Saat / ilk 6 tamamlanmış an",eligible,index=len(eligible)-1,
                       format_func=format_hour,key="v25_hour")
    cutoff=start+5
    st.caption(f"Tahmin üretim zamanı: **{clock(cutoff)[0]}**. "
               f"Hedefler: {clock(cutoff+1)[0]}–{clock(start+11)[0]}.")
    if st.button("🧬 Aileleri ve 10'lu kuponları hesapla",key="v25_make"):
        history=[daily[p] for p in range(1,cutoff+1)]
        first6=history[-6:]
        state=new_state()
        catalog=read_catalog(family_text) if family_text else {}
        for d in history:update_history(state,d,catalog)
        panel,hot12,hot6=choose_family_panel(selected,cutoff,state,history,first6)
        coupons=coupon_sets(selected,start,panel,hot12,hot6,history)
        cores=[]
        for (k,stage),methods in sorted(panel.items()):
            for label,fam in methods.items():
                cores.append({
                    "Boyut":k,"Evre":stage,"Yöntem":label,
                    "Çekirdek":"-".join(str(n) for n in fam),
                    "Kesime dek birlikte":state["counts"][k][fam],
                    "Eşlikçiler":"-".join(str(n) for n in predict_satellites(fam,history))
                })
        cds=[{"Yöntem":name,"10 sayı":"-".join(str(n) for n in nums)}
             for name,nums in coupons.items()]
        cat=[]
        for label,(k,fam,mask) in catalog.items():
            if k<5:continue
            if not any((d["mask"]&mask)==mask for d in first6):continue
            ct=state["catalog"].get(label,0)
            cat.append({"Aile":label,"Boyut":k,"Kesime dek görünüş":ct,
                        "Evre":"İlk" if ct==1 else "İki" if ct==2 else "Üç+"})
        future=[daily[p] for p in range(cutoff+1,start+12) if p in daily]
        evaluated=None
        if len(future)==6:
            evaluated=[coupon_event(selected,start,name,nums,future)
                       for name,nums in coupons.items()]
        st.session_state["v25_snapshot"]=(selected,start,cores,cds,cat,evaluated)
    saved=st.session_state.get("v25_snapshot")
    if saved and saved[:2]==(selected,start):
        _,_,cores,coupons,cat,evaluated=saved
        st.markdown("#### Aileler: ilk / ikinci / üçüncü evre")
        st.dataframe(cores,hide_index=True,use_container_width=True)
        st.markdown("#### Deneysel 10'lu kuponlar")
        st.dataframe(coupons,hide_index=True,use_container_width=True)
        if cat:
            st.markdown("#### Kayıtlı 5–10'lu büyük aileler")
            st.dataframe(cat,hide_index=True,use_container_width=True)
        if evaluated:
            st.markdown("#### Sonraki 6 çekiliş gerçek sonuçları")
            st.dataframe(evaluated,hide_index=True,use_container_width=True)
        else:
            st.caption("Hedef 6 çekiliş henüz tamamlanmadıysa skor gösterilmez.")
        st.download_button("⬇️ V25 kuponları CSV",csv_bytes(coupons),
                           "V25_KUPONLAR.csv","text/csv",key="v25_dl_c")
        st.download_button("⬇️ Aile/çekirdek sinyalleri CSV",csv_bytes(cores),
                           "V25_AILE_SINYALLER.csv","text/csv",key="v25_dl_f")
    st.divider()
    st.caption("72 günün 36 öğrenme / 36 test raporu: "
               "GitHub Actions → V25 Aile DNA 72 Gun Kor Test. "
               "Bütün 0/10–10/10 kupon isabetleri ve rastgele kontroller aynı ZIP'tedir.")
