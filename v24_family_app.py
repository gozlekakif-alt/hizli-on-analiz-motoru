# -*- coding: utf-8 -*-
"""V24 Streamlit view: frozen first family -> second occurrence prediction."""
import streamlit as st
from v21_aile_yasam_dongusu import group_full_days,csv_bytes,HOUR_STARTS,clock
from v24_aile_ikinci_ongoru import per_day_forecasts,STRATEGIES,CONTROL


def render_v24(draws):
    st.subheader("🌾 V24 — İlk Çıkıştan İkinciyi Önceden Seç")
    st.caption("2'li–10'lu ailelerde ikinci çıkış, ilk tam birlikte görünüşten "
               "SONRA seçilir. Son 11 çekiliş ve gün sonu doğruluk, "
               "rastgele aileyle karşılaştırılır.")
    st.info("Önceki 217-gün analizlerinden farklı olarak bu ekranda "
            "ilk çıkışa kadar hiç görünmeyen aileler seçilir; ikinci çıkış "
            "sırasındaki sayıların hiçbirinden faydalanılmaz.")
    full,incomplete=group_full_days([
        {**r,"mask":sum(1<<(int(n)-1) for n in r["nums"])} for r in draws
    ])
    if not full:
        st.warning("Tam günlük veri yok")
        return
    names=[d for d,_ in full]
    chosen=st.selectbox("Gün",names,index=len(names)-1,key="v24_date")
    day=next(rs for day,rs in full if day==chosen)
    hour=st.selectbox("İlk çıkışın alındığı gerçek saat",
                      HOUR_STARTS,index=min(9,len(HOUR_STARTS)-1),
                      format_func=lambda n:clock(n)[0],key="v24_hour")
    if st.button("🔍 Seçili günün ikinci çıkışlarını incele",key="v24_start"):
        with st.spinner("Yeni aileler geçmişe bakılarak sabitleniyor"):
            output=per_day_forecasts(chosen,day)
        st.session_state["v24_day_results"]=(chosen,output)
    save=st.session_state.get("v24_day_results")
    if save and save[0]==chosen:
        _,rows=save
        k=st.select_slider("Aile boyutu",options=list(range(2,11)),
                           value=3,key="v24_size")
        select=[r for r in rows if r["Boyut"]==k and r["İlk sıra"]==hour]
        if not select:
            st.warning("Bu saatte ilk kez çıkan yeni aile kalmamış.")
            return
        st.dataframe(select,hide_index=True,use_container_width=True)
        st.caption("Görülmeyen ikinci çıkışlar boş kalır; gün sonu itibarıyla "
                   "ikinci çıkış olmamış demektir. Önceden seçilen aile "
                   "geleceği görerek değiştirilmez.")
        st.download_button("⬇️ Günlük V24 tahmin/isabet raporu",
                           csv_bytes(rows),"V24_ILK_IKINCI_GUNLUK.csv",
                           "text/csv",key="v24_dl")
    st.divider()
    st.caption("72 günlük V24 ana raporu GitHub Actions'ta hesaplanır: "
               "ilk 36 günden yöntem seçilir, sonraki 36 günde frozen "
               "kural sınanır. Tam CSV ve özet ZIP dosyası oluşturulur.")
