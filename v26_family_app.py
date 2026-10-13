# -*- coding: utf-8 -*-
"""V26 live-safe mixed coupon snapshot: 6 seen, next 6 unseen."""
from collections import defaultdict
import streamlit as st
from v21_aile_yasam_dongusu import clock, HOUR_STARTS, csv_bytes
from v26_karma_kupon import snapshot, coupon_event, MIX_CONFIG, BASELINES


def render_v26(draws):
    st.subheader("🔀 V26 — Sıcak + Soğuk + Yeni Aktif Karma Kupon")
    st.caption("İlk 6 gerçek çekiliş: sıcak >=3/6; soğuk = 0/6; "
               "yeni aktif = ilk 3'te 0, sonraki 3'te en az 1. "
               "Sıcak-yeni çakışırsa sıcak önceliklidir.")
    st.info("4 sıcak + 3 soğuk + 3 yeni; 3+3+4; 3+4+3; "
            "ve aile çekirdeği/önceki eşlikçilere ağırlık veren 4+3+3 üretilir. "
            "Karşılarında V25'in sıcak, soğuk, AileDNA ve rastgele kuponları vardır. "
            "Bunlar kesin tahmin değil, test edilen kurallardır.")
    days=defaultdict(dict)
    for d in draws:
        pos=d.get("pos")
        if pos:
            days[d["day"]][int(pos)]={
                **d,"mask":sum(1<<(int(n)-1) for n in d["nums"])
            }
    dates=sorted(days)
    if not dates:
        st.warning("Geçerli çekiliş verisi bulunamadı.")
        return
    date=st.selectbox("İncelenecek gün",dates,index=len(dates)-1,key="v26_date")
    chosen=days[date]
    starts=[s for s in HOUR_STARTS if all(i in chosen for i in range(1,s+6))]
    if not starts:
        st.warning("Bu günün ilk altı çekilişi veya önceki kayıtları eksik.")
        return
    start=st.selectbox("İlk 6 çekilişi tamamlanmış saat",starts,
                       index=len(starts)-1,
                       format_func=lambda s:clock(s)[0]+"–"+clock(s+11)[0],
                       key="v26_hour")
    cutoff=start+5
    st.caption(f"Kupon sabitleme: **{clock(cutoff)[0]}**. "
               f"Test hedefleri: {clock(start+6)[0]}–{clock(start+11)[0]}.")
    if st.button("🔀 Karma 10'lu kuponları hesapla",key="v26_make"):
        history=[chosen[i] for i in range(1,cutoff+1)]
        coupons,signals=snapshot(date,start,history)
        display=[]
        for name,nums in coupons.items():
            c=signals["category_counts"].get(name)
            display.append({
                "Yöntem":name,"10 sayı":"-".join(f"{n:02d}" for n in nums),
                "Gerçek sıcak":c["hot"] if c else "",
                "Gerçek soğuk":c["cold"] if c else "",
                "Gerçek yeni":c["new"] if c else "",
                "Diğer":c["mid"] if c else "",
            })
        targets=[chosen[i] for i in range(cutoff+1,start+12)
                 if i in chosen]
        evaluated=None
        if len(targets)==6:
            evaluated=[coupon_event(date,start,m,ns,targets)
                       for m,ns in coupons.items()]
        st.session_state["v26_snapshot"]=(date,start,display,signals,evaluated)
    saved=st.session_state.get("v26_snapshot")
    if saved and saved[:2]==(date,start):
        _,_,rows,signals,outcomes=saved
        a,b,c=st.columns(3)
        a.metric("Sıcak havuz",signals["hot"])
        b.metric("Soğuk havuz",signals["cold"])
        c.metric("Yeni aktif",signals["new"])
        st.markdown("#### Karma ve kontrol kuponları")
        st.dataframe(rows,hide_index=True,use_container_width=True)
        st.markdown("#### İlk 6'da görülen hareketler")
        st.write({
            "Sıcak":signals["hot_nums"],
            "Soğuk":signals["cold_nums"],
            "Yeni aktive olan":signals["new_nums"]
        })
        if outcomes:
            st.markdown("#### Sonraki 6 gerçek çekilişin kupon isabetleri")
            st.dataframe(outcomes,hide_index=True,use_container_width=True)
            st.download_button("⬇️ 0–10 isabet sonuçları",
                               csv_bytes(outcomes),
                               "V26_KARMA_KUPON_ISABET.csv","text/csv",
                               key="v26_dl_score")
        else:
            st.caption("7–12. çekilişler tamamlanmadığı için kuponlar henüz sınanmadı.")
        st.download_button("⬇️ Karma 10'lu kuponları indir",
                           csv_bytes(rows),"V26_KARMA_10LU_KUPONLAR.csv",
                           "text/csv",key="v26_dl_coupon")
    st.divider()
    st.caption("72 tam gün / 36 öğrenme + 36 test araştırması GitHub Actions "
               "'V26 Karma Kupon 72 Gun Kor Test' adımında tek ZIP'te saklanır.")
