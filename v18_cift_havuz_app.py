# -*- coding: utf-8 -*-
"""V18 Streamlit: two separate complete 20/60 pools per one of 217 slots.

Both views rebuild automatically from persistent GitHub veri.txt; there is no
third source of truth and no silent edit of previous draw or user coupons.
"""
from datetime import datetime
import streamlit as st
from v18_cift_havuz import (
    ACT,REST,build_day,state_history,csv_export,pool_txt
)

@st.cache_data(ttl=90,show_spinner=False)
def _v18_build(records):
    return build_day(records)


def render_v18(day_draws,daystr,is_today,now_tr):
    st.subheader("🌓 V18 — 217 çekilişte çıkan 20 / çıkmayan 60")
    st.caption(
        "Her çekilişte 1–80 havuzu ikiye ayrılır: "
        "**çıkan 20** ve **çıkmayan 60**. "
        "217 çekiliş boyunca her iki havuzun listeleri, "
        "her sayının giriş/çıkışları ve birikimleri ayrı tutulur."
    )
    st.info(
        "Kaynağımız GitHub'daki mevcut kalıcı veri.txt. "
        "Yeni çekiliş eklendiğinde iki havuz yeniden hesaplanır; "
        "geçmiş sonuç ve kuponlar değiştirilmez. "
        "Henüz kaydı olmayan çekilişler 'çıkmadı' sayılmaz."
    )
    known=[
        d for d in day_draws
        if not is_today or datetime.fromisoformat(d["dt"])<=now_tr()
    ]
    if not known:
        st.warning("Bu güne ait geçmiş çekiliş yok.")
        return
    try:
        result=_v18_build(known)
    except ValueError as ex:
        st.error(f"İki havuz kaydında tutarsızlık var: {ex}")
        return
    summary=result["meta"]
    cols=st.columns(4)
    cols[0].metric("İşlenen çekiliş",f'{summary["processed"]}/217')
    cols[1].metric("20 havuzu birikimi",summary["active_total"])
    cols[2].metric("60 havuzu birikimi",summary["rest_total"])
    cols[3].metric("Kayıtsız slot",len(summary["missing"]))
    st.caption(
        "Birikim, tekil rakam sayısı değil, çekiliş başına sayı görünüş "
        "kaydının toplamıdır. 217 tam çekilişte çıkan 20 havuzu 4.340 "
        "ve çıkmayan 60 havuzu 13.020 görünüş kaydı tutar. "
        "Aynı sayı farklı çekilişlerde tekrar sayılır."
    )
    selected=st.selectbox(
        "Hangi çekilişteki iki havuzu görelim?",
        options=list(range(len(result["draws"])-1,-1,-1)),
        format_func=lambda i:(
            f'#{result["draws"][i]["Çekiliş no"]} • '
            f'{result["draws"][i]["Saat"]} • '
            f'{result["draws"][i]["Günlük sıra"]}. çekiliş'
        ),
        key="v18_selected_pos"
    )
    draw=result["draws"][selected]
    a,b=st.columns(2)
    active_nums=draw["Çıkan 20"].split("-")
    rest_nums=draw["Çıkmayan 60"].split("-")
    with a:
        st.markdown("#### 🟢 Çıkan 20 havuzu")
        st.write(" · ".join(active_nums))
        st.caption(
            f'Bu çekilişe kadar {draw["20 havuz birikimi"]} '
            "çıkan-sayı kaydı"
        )
    with b:
        st.markdown("#### ⚪ Çıkmayan 60 havuzu")
        st.write(" · ".join(rest_nums))
        st.caption(
            f'Bu çekilişe kadar {draw["60 havuz birikimi"]} '
            "çıkmayan-sayı kaydı"
        )
    st.markdown("#### 🔄 Havuzlar arası geçiş")
    if draw["Kalan 20→20"] is None:
        st.caption(
            "Bu çekilişten hemen önce kayıtlı ardışık sonuç "
            "bulunamadığından geçiş uydurulmadı."
        )
    else:
        c=st.columns(4)
        c[0].metric("20→20 kaldı",draw["Kalan 20→20"])
        c[1].metric("20→60 ayrıldı",draw["Ayrılan 20→60"])
        c[2].metric("60→20 geldi",draw["Yeni gelen 60→20"])
        c[3].metric("60→60 bekledi",draw["Kalan 60→60"])
        st.caption(
            "20'li havuza giren sayı adediyle ayrılan sayı adedi "
            "her iki çekiliş arasında eşittir. 01:02→07:02 geçişi "
            "altı saat ara olarak ayrı işaretlenmiştir."
        )
    st.markdown("#### 📚 İki havuzun gün boyunca ayrı birikimi")
    choice=st.radio(
        "Kayıt görünümü",
        options=["Çıkan 20","Çıkmayan 60","217 çekiliş birlikte",
                 "80 sayının bireysel bilançosu","Havuz değişimleri"],
        horizontal=True,key="v18_view"
    )
    key={
        "Çıkan 20":"active20",
        "Çıkmayan 60":"rest60",
        "217 çekiliş birlikte":"draws",
        "80 sayının bireysel bilançosu":"numbers",
        "Havuz değişimleri":"transitions",
    }[choice]
    st.dataframe(result[key],hide_index=True,use_container_width=True)
    with st.expander("🔍 Tek bir sayının 217 çekilişlik havuz yolculuğu"):
        n=st.number_input("Hangi sayı?",min_value=1,max_value=80,
                          value=19,step=1,key="v18_specific_number")
        history=state_history(result,int(n))
        nrow=result["numbers"][int(n)-1]
        cols=st.columns(3)
        cols[0].metric("Çıkan 20'de",nrow["20 havuzunda toplam"])
        cols[1].metric("Çıkmayan 60'ta",nrow["60 havuzunda toplam"])
        cols[2].metric("60→20 dönüş",nrow["60→20 giriş"])
        st.dataframe(history,hide_index=True,use_container_width=True)
        st.download_button(
            "⬇️ Bu sayının havuz hareketi",
            csv_export(history),
            file_name=f"V18_SAYI_{int(n):02d}_{daystr}.csv",
            mime="text/csv",key="v18_single_download"
        )
    with st.expander("🧬 V17 karakter için 20/60 kaynakları"):
        st.caption(
            "V17'deki tekrar/taşıma karakteri '20→20 kalan' üzerinden; "
            "giriş-çıkış karakteri '60→20' ve '20→60' üzerinden "
            "ölçülebilir. Burada yalnız gerçekleşmiş sonuçların "
            "karakter kaynak verisini kaydediyoruz; gelecek sayı tahmini yok."
        )
        st.dataframe(result["transitions"][-25:],
                     hide_index=True,use_container_width=True)
    st.markdown("#### 📥 İki ayrı havuzu indir")
    col1,col2=st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Çıkan 20 — TXT",
            pool_txt(result["active20"]),
            file_name=f"V18_CIKAN_20_{daystr}.txt",
            mime="text/plain",key="v18_active_txt"
        )
        st.download_button(
            "⬇️ Çıkan 20 — CSV",
            csv_export(result["active20"]),
            file_name=f"V18_CIKAN_20_{daystr}.csv",
            mime="text/csv",key="v18_active_csv"
        )
    with col2:
        st.download_button(
            "⬇️ Çıkmayan 60 — TXT",
            pool_txt(result["rest60"]),
            file_name=f"V18_CIKMAYAN_60_{daystr}.txt",
            mime="text/plain",key="v18_rest_txt"
        )
        st.download_button(
            "⬇️ Çıkmayan 60 — CSV",
            csv_export(result["rest60"]),
            file_name=f"V18_CIKMAYAN_60_{daystr}.csv",
            mime="text/csv",key="v18_rest_csv"
        )
    st.download_button(
        "⬇️ 80 sayının birikmiş havuz kimliği",
        csv_export(result["numbers"]),
        file_name=f"V18_80_SAYI_HAVUZ_KIMLIGI_{daystr}.csv",
        mime="text/csv",key="v18_number_csv"
    )
    st.download_button(
        "⬇️ 217 satır × 80 sayı: Ç/B matrisi",
        csv_export(result["timeline"]),
        file_name=f"V18_217x80_HAVUZ_MATRISI_{daystr}.csv",
        mime="text/csv",key="v18_matrix_csv"
    )
    if summary["missing"]:
        st.caption(
            f'{len(summary["missing"])} gün içi pozisyon kayıtsız. '
            "Bu pozisyonlarda ne çıkan20 ne de çıkmayan60 hakkında "
            "varsayım yapılmıştır."
        )
    else:
        st.success(
            "217 çekilişin tamamı doğrulandı. "
            "İki havuz bütün günün 80 sayı ayrımını eksiksiz tutuyor."
        )
