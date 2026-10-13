# -*- coding: utf-8 -*-
"""V17 Streamlit view: character, not ball identity or winning forecasts."""
import json
from datetime import datetime
from collections import Counter
import streamlit as st
from v17_karakter_motoru import (
    build_character_rows,fit,replay,latest_character,next_character,
    FIELDS,csv_export
)


@st.cache_data(ttl=2400,show_spinner=False)
def _full_test(all_draws):
    return replay(json.loads(all_draws),train_days=36)


@st.cache_data(ttl=2400,show_spinner=False)
def _train_36(initial):
    records=json.loads(initial)
    _,events=build_character_rows(records)
    return fit(events)


def render_v17(draws,day_draws,daystr,is_today,now_tr,moment):
    st.subheader("🧬 V17 — Çekiliş karakteri")
    st.caption(
        "Rakam kimliği yerine çekilişin davranışı: önceki 20'den tekrar, "
        "tek/çift ve alt/üst dengesi, 20'lik bantların koltukları, "
        "komşu kümelenmesi, soğuk/ılık/sıcak doluşu, 2–10 aile izleri."
    )
    st.warning(
        "Çekilişlerin 20 sayısı sırasız kümelerdir. Karakter, topların "
        "fiziksel çıkış sırası veya RNG algoritması değildir. "
        "Karakter tahmini de doğrudan kazanan rakam tahmini değildir."
    )
    known=sorted((d for d in day_draws
                  if not is_today or datetime.fromisoformat(d["dt"])<=now_tr()),
                 key=lambda d:d["pos"])
    chars,_=build_character_rows(known)
    st.markdown("#### 217 çekilişin karakter yolculuğu")
    if chars:
        rows=[]
        for r in chars:
            ch=r["Karakter"]
            rows.append({
                "Sıra":r["Pozisyon"],"Saat":r["Saat"],
                "Tekrar":ch["Tekrar sayısı"],
                "Yapısal karakter":ch["Bileşik karakter"],
                "Tek":ch["Tek sayı"],"Alt":ch["Alt sayı"],
                "Kümelenme":ch["Komşu bağlantı"],
                "Bant":ch["Bant"],"Isı":ch["Isı koltuğu"],
                "2'li iz":ch["Aile izi 2–10"][2],
                "6'lı iz":ch["Aile izi 2–10"][6],
                "10'lu iz":ch["Aile izi 2–10"][10],
            })
        a,b,c=st.columns(3)
        a.metric("Karakterlenen çekiliş",len(rows))
        b.metric("Ortalama tekrar",round(sum(r["Tekrar"] for r in rows)/len(rows),3))
        c.metric("Taşıma 7+",sum(r["Tekrar"]>=7 for r in rows))
        st.dataframe(rows,hide_index=True,use_container_width=True)
        st.download_button("⬇️ Günün 217 karakteri",csv_export(rows),
                           file_name=f"V17_GUNLUK_KARAKTER_{daystr}.csv",
                           mime="text/csv",key="v17_day_csv")
        st.caption(
            "Aile izi: son 12 çekilişte tam birlikte görünmüş alt-aile "
            "olaylarının sayısıdır; aynı aile birden fazla kez sayılabilir."
        )
    else:
        st.info("Karakter hesaplamak için birbirini izleyen iki çekiliş gerekli.")

    st.markdown("#### 36 gün öğrenim → 37 gün karakter tahmin testi")
    if st.button("🔬 V17 — Karakteri 73 günde test et",
                 type="primary",key="v17_run"):
        with st.spinner("217 günlük sıra ve 2–10 aile karakterleri inceleniyor..."):
            output=_full_test(json.dumps(draws,separators=(",",":")))
        st.session_state["v17_report"]={
            "last":max((r["no"] for r in draws),default=0),
            "output":output
        }
    saved=st.session_state.get("v17_report")
    if saved:
        result=saved["output"]
        meta=result["meta"]
        if saved["last"]!=max((r["no"] for r in draws),default=0):
            st.warning("Rapor eski veri sürümüne ait. Analizi yeniden çalıştır.")
        a,b,c=st.columns(3)
        a.metric("Eğitim günü",meta["train_days"])
        b.metric("Test günü",meta["test_days"])
        c.metric("Karakter hedefi",meta["test_targets"])
        st.markdown("##### Karakter geçişi sabit geçmişe karşı")
        st.dataframe(result["comparison"],hide_index=True,use_container_width=True)
        st.caption(
            "Geçiş − sabit log-kayıp küçükse daha iyi; "
            "sekiz karakter ölçüsünden seçilen çok küçük iyileşme "
            "doğrulanmış avantaj sayılmaz."
        )
        st.markdown("##### Günün 217 sırası, ilk altı / son altı")
        st.dataframe(result["phases"],hide_index=True,use_container_width=True)
        with st.expander("2–10 ailelerin geçmiş izleri"):
            st.dataframe(result["family_echo"],hide_index=True,
                         use_container_width=True)
        with st.expander("Karakterden karaktere geçiş çizelgesi"):
            st.dataframe(result["flow"],hide_index=True,use_container_width=True)
        for title,key,path in (
            ("Karakter testi","comparison","V17_KARAKTER_SONUCLARI.csv"),
            ("Tüm karakter geçişleri","flow","V17_KARAKTER_GECISLERI.csv"),
            ("217 sıra karakter koltukları","phases","V17_ZAMAN_KARAKTER.csv"),
            ("2–10 aile izleri","family_echo","V17_AILE_IZLERI.csv"),
            ("Her hedefin gerçek karakteri","ledger","V17_HEDEF_KARAKTER.csv")
        ):
            st.download_button("⬇️ "+title,csv_export(result[key]),
                               file_name=path,mime="text/csv",
                               key="v17_download_"+key)
    else:
        st.info("Kapsamlı test için yukarıdaki 🔬 düğmesine bas.")

    st.markdown("#### 🔭 Gelecek çekilişin karakteri")
    if not is_today or not known:
        st.caption("Bu önizleme yalnızca bugünün gelecekteki hedefleri içindir.")
        return
    pos=known[-1]["pos"]+1
    if pos>217 or pos in {d["pos"] for d in day_draws}:
        st.info("Henüz sonucu bilinmeyen yeni bir çekiliş yok.")
        return
    due=moment(daystr,pos)
    if due<=now_tr():
        st.info("Hedef zamanı geçmiş; sonradan tahmin üretmiyoruz.")
        return
    prior_char=latest_character(known,pos)
    if prior_char is None:
        st.info("Gelecek hedefin öncesinde kesintisiz iki çekiliş gereklidir.")
        return
    days=sorted({d["day"] for d in draws if d["day"]<daystr})[:36]
    if len(days)<36:
        st.info("36 tam eğitim günü henüz yok.")
        return
    training=[d for d in draws if d["day"] in set(days)]
    with st.spinner("İlk 36 günün karakter olasılıkları getiriliyor..."):
        fitted=_train_36(json.dumps(training,separators=(",",":")))
    estimated=next_character(prior_char,pos,fitted)
    rows=[]
    for key in FIELDS:
        best=sorted(estimated[key].items(),key=lambda item:(-item[1],item[0]))
        rows.append({
            "Karakter":key,"Önceki":prior_char[key],
            "Sıradaki en olası":best[0][0],
            "Olasılık %":round(best[0][1]*100,3),
            "İkinci olası":best[1][0],
            "İkinci olasılık %":round(best[1][1]*100,3)
        })
    st.write(f"**Hedef: {due:%H:%M} — {pos}. çekiliş.**")
    st.dataframe(rows,hide_index=True,use_container_width=True)
    st.download_button(
        "⬇️ Önceden belirlenen karakter beklentisi",
        csv_export(rows),
        file_name=f"V17_GELECEK_KARAKTER_{daystr}_{pos}.csv",
        mime="text/csv",key="v17_live_csv"
    )
    st.caption(
        "Bu olasılıklar sayı tahmini değildir. Gerçek tahmin üstünlüğü "
        "gösterilene dek V15 kupon motorunun kuralları değiştirilmez."
    )
