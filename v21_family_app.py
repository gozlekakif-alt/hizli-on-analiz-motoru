# -*- coding: utf-8 -*-
"""V21 Streamlit view — history-preserving selected-day family lifecycle."""
import io
import json
import zipfile
import streamlit as st
from v21_aile_yasam_dongusu import (
    group_full_days, daily_study, read_catalog, catalog_study,
    catalog_core_variants, forward_test, csv_bytes, zip_results
)


@st.cache_data(show_spinner=False, ttl=3600)
def _one_day(records, top):
    return daily_study(records[0]["day"], records, top_per_size=top, top_cores=top)


@st.cache_data(show_spinner=False, ttl=3600)
def _family_catalog(records, family_text):
    catalog = read_catalog(family_text)
    return catalog_study(records, catalog)


def render_v21(draws, family_text):
    st.subheader("🌳 V21 — 2–10'lu Ailelerin Gün İçi Yolculuğu")
    st.caption("217 çekilişte ailelerin tam görünüşü, saatleri, tekrar aralıkları, "
               "aynı çekirdeği koruyup çevresini değiştiren kadrolar. "
               "Geçmiş tek-kayıt kaynağı veri.txt; mevcut motorlara dokunulmaz.")
    st.info("Günlük aile keşfi tam tekrar eden aileleri eksiksiz bulur (en az 2 çıkış). "
            "Tek çıkışlı milyonlarca altkümeyi listelemez. "
            "Ailelerin sonuçtan sonra bulunması ileri tahmin kanıtı değildir.")
    normalized=[]
    for d in draws:
        x=dict(d)
        x["mask"]=sum(1 << (int(n)-1) for n in d["nums"])
        normalized.append(x)
    full,partial=group_full_days(normalized)
    if not full:
        st.warning("217 çekilişi tamamlanmış bir gün bulunamadı.")
        return
    st.caption(f"{len(full)} tam gün; eksik günler dışarıda: "+
               (", ".join(f"{day} ({n}/217)" for day,n in partial) or "yok"))
    options=[day for day,_ in full]
    day=st.selectbox("Aile hareketini görmek istediğin tam gün",
                     options=options,index=len(options)-1,key="v21_day")
    selected=next(ds for d,ds in full if d==day)
    cap=st.slider("Her aile boyutunda gösterilecek en güçlü aile",
                  min_value=3,max_value=30,value=10,key="v21_top")
    if st.button("🔬 Seçili günü derinlemesine tara",key="v21_run_day"):
        with st.spinner("Tekrarlanan aileler ve değişen çevreler hesaplanıyor"):
            sizes,tops,cores=_one_day(tuple(selected),cap)
        st.session_state["v21_latest_day"]=(day,sizes,tops,cores)
    stored=st.session_state.get("v21_latest_day")
    if stored is not None and stored[0]==day:
        _,sizes,tops,cores=stored
        st.markdown("#### 2'li–10'lu tekrar sayıları")
        st.dataframe(sizes,hide_index=True,use_container_width=True)
        st.markdown("#### Tam ailelerin çekiliş ve saat yolculuğu")
        st.dataframe(tops,hide_index=True,use_container_width=True)
        st.markdown("#### Aynı çekirdek, değişen çevre")
        st.dataframe(cores,hide_index=True,use_container_width=True)
        col=st.columns(3)
        for widget,txt,items,fn in [
            (col[0],"Günlük aile özeti",sizes,"V21_GUN_OZETI.csv"),
            (col[1],"Ailelerin tam saatleri",tops,"V21_AILE_SAATLERI.csv"),
            (col[2],"Değişen çevreler",cores,"V21_CEKIRDEK_CEVRE.csv")
        ]:
            widget.download_button("⬇️ "+txt,data=csv_bytes(items),
                                  file_name=fn,mime="text/csv",
                                  key="v21_dl_"+fn)
    st.divider()
    st.markdown("#### 72 günlük toplam rapor")
    st.caption("Tam gün taramasını GitHub Actions içindeki 'V21 Aile Yasam Dongusu' "
               "iş akışından çalıştırıp ZIP raporunu indirebilirsin. "
               "Streamlit sayfasında her açılışta 72 günlük ağır işlem yapılmaz.")
    st.markdown("#### İlk 6 → sonraki 6 çekiliş kör sınaması")
    if st.button("🎯 72 gün ileriye dönük aile kontrolü",key="v21_forward"):
        with st.spinner("Önceki 6'dan 2, 3, 4'lü çekirdek seçilip son 6'da değerlendiriliyor"):
            predictions,summary=forward_test(full)
        st.dataframe(summary,hide_index=True,use_container_width=True)
        st.download_button("⬇️ İleri testin tüm hedefleri",
                           data=csv_bytes(predictions),file_name="V21_ILK6_SON6.csv",
                           mime="text/csv",key="v21_dl_prediction")
    st.markdown("#### Kayıtlı aileler ve ortak merkezler")
    if family_text and st.button("🗂️ 1.131 kayıtlı ailenin 72 gününü tara",key="v21_catalog"):
        profiles=_family_catalog(tuple((d,tuple(rs)) for d,rs in full),family_text)
        variants=catalog_core_variants(read_catalog(family_text),profiles)
        st.dataframe(profiles,hide_index=True,use_container_width=True)
        st.dataframe(variants[:100],hide_index=True,use_container_width=True)
        st.download_button("⬇️ Kayıtlı aileler",csv_bytes(profiles),
                           "V21_KATALOG_TUM_GUNLER.csv","text/csv",key="v21_dl_catalog")
        st.download_button("⬇️ Çekirdek / çevre varyantları",
                           csv_bytes(variants),"V21_CEKIRDEK_VARYANTLARI.csv",
                           "text/csv",key="v21_dl_variants")
