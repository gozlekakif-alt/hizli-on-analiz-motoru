# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile

from hizli_on_birlesme_kupon_motoru_v1 import (
    parse_analysis_report,
    training_rows,
    learn_branches,
    parse_day,
    produce_hour,
)

st.set_page_config(page_title="Hızlı On Birleşme Kupon Motoru", layout="wide")
st.title("🎯 Hızlı On — Geçiş Aileleri / Son-6 Birleşme Kupon Motoru")
st.caption("İlk 3 → İkinci 3 → Son 6 canlı kimlik. Hedef sonucu seçim sırasında kullanılmaz.")

DEFAULT_TRAIN = "HIZLI_ON_14_GUN_TUM_SAAT_SAAT_ANALIZLER-1.txt"
DEFAULT_DAY = "10_09_2026_GUNLUK_KUTUK.txt"

def save_upload(uploaded, suffix=".txt"):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded.getbuffer())
    tmp.close()
    return tmp.name

@st.cache_data(show_spinner=False)
def build_model(train_path):
    sessions = parse_analysis_report(train_path)
    df = training_rows(sessions)
    model = learn_branches(df)
    return sessions, df, model

st.sidebar.header("Dosyalar")

repo_train = Path(DEFAULT_TRAIN)
repo_day = Path(DEFAULT_DAY)

train_upload = st.sidebar.file_uploader(
    "14 günlük saat-saat analiz TXT",
    type=["txt"],
    help=f"Repo'da {DEFAULT_TRAIN} varsa otomatik kullanılır."
)
day_upload = st.sidebar.file_uploader(
    "Test günü TXT",
    type=["txt"],
    help=f"Repo'da {DEFAULT_DAY} varsa otomatik kullanılır."
)

if train_upload is not None:
    train_path = save_upload(train_upload)
elif repo_train.exists():
    train_path = str(repo_train)
else:
    train_path = None

if day_upload is not None:
    day_path = save_upload(day_upload)
elif repo_day.exists():
    day_path = str(repo_day)
else:
    day_path = None

if train_path is None:
    st.error(f"14 günlük kaynak bulunamadı. Repo'ya `{DEFAULT_TRAIN}` koy veya soldan yükle.")
    st.stop()

with st.spinner("14 günlük birleşme dalları öğreniliyor..."):
    sessions, train_df, model = build_model(train_path)

core = [b for b in model.values() if b.tier == "CORE"]
support = [b for b in model.values() if b.tier == "SUPPORT"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tam saat", len(sessions))
c2.metric("CORE dal", len(core))
c3.metric("SUPPORT dal", len(support))
c4.metric("Eğitim satırı", f"{len(train_df):,}".replace(",", "."))

tabs = st.tabs(["🎟️ Kupon Üret", "🧪 Gün Testi", "🧬 Güçlü Dallar", "📘 Motor Mantığı"])

with tabs[0]:
    st.subheader("Canlı saatten kupon üret")

    if day_path is None:
        st.info("Canlı/örnek saat için bir günlük TXT yükle.")
    else:
        hours = parse_day(day_path)
        if not hours:
            st.warning("Dosyada tam :02–:57 saat bloğu bulunamadı.")
        else:
            selected_hour = st.selectbox("Saat", sorted(hours.keys()))
            generated = produce_hour(hours[selected_hour], selected_hour, model, variants=5)

            if not generated:
                st.warning("Bu saatte motor sinyali yok: ABSTAIN.")
            else:
                rows = []
                for x in generated:
                    rows.append({
                        "Hedef": f"{selected_hour}:{x['minute']}",
                        "Varyant": x["variant"],
                        "Boyut": x["coupon_size"],
                        "Kolon": " - ".join(map(str, x["coupon"])),
                    })
                out = pd.DataFrame(rows)
                st.dataframe(out, use_container_width=True, hide_index=True)

                csv = out.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Kuponları CSV indir",
                    csv,
                    file_name=f"kuponlar_{selected_hour}.csv",
                    mime="text/csv"
                )

with tabs[1]:
    st.subheader("Test günü — tüm hedefler")

    if day_path is None:
        st.info("Test günü TXT yükle.")
    else:
        hours = parse_day(day_path)
        all_rows = []

        for hour in sorted(hours):
            generated = produce_hour(hours[hour], hour, model, variants=5)
            for x in generated:
                actual = set(hours[hour][x["minute"]][1])
                coupon = set(x["coupon"])
                hitnums = sorted(actual & coupon)
                all_rows.append({
                    "Saat": f"{hour}:{x['minute']}",
                    "Varyant": x["variant"],
                    "Boyut": x["coupon_size"],
                    "Kolon": " - ".join(map(str, x["coupon"])),
                    "İsabet": len(hitnums),
                    "Vuranlar": " - ".join(map(str, hitnums))
                })

        report = pd.DataFrame(all_rows)

        if report.empty:
            st.warning("Bu test gününde motor kupon üretmedi.")
        else:
            total = len(report)
            dist = report["İsabet"].value_counts().sort_index()

            a, b, c, d = st.columns(4)
            a.metric("Toplam kolon", total)
            b.metric("3+ kolon", int((report["İsabet"] >= 3).sum()))
            c.metric("4+ kolon", int((report["İsabet"] >= 4).sum()))
            d.metric("5+ kolon", int((report["İsabet"] >= 5).sum()))

            st.markdown("#### İsabet dağılımı")
            dist_df = pd.DataFrame({
                "İsabet": [f"{i}/6" for i in range(7)],
                "Kolon": [int(dist.get(i, 0)) for i in range(7)]
            })
            st.dataframe(dist_df, use_container_width=True, hide_index=True)

            st.markdown("#### 4+ kolonlar")
            hi = report[report["İsabet"] >= 4].sort_values(["İsabet", "Saat"], ascending=[False, True])
            st.dataframe(hi, use_container_width=True, hide_index=True)

            st.markdown("#### Tüm kolonlar")
            st.dataframe(report, use_container_width=True, hide_index=True)

            csv = report.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Tam test raporunu indir",
                csv,
                file_name="BIRLESME_MOTORU_GUN_TEST_RAPORU.csv",
                mime="text/csv"
            )

with tabs[2]:
    st.subheader("CORE / SUPPORT birleşme dalları")

    rows = []
    for b in model.values():
        if b.tier == "OFF":
            continue
        rows.append({
            "Hedef": f":{b.minute}",
            "Geçiş ailesi": b.family,
            "Önceki son-6 yolu": b.prior if b.prior else "∅",
            "Tier": b.tier,
            "n": b.n,
            "Hit": b.hits,
            "Oran %": round(100*b.rate, 2),
            "D %": round(100*b.d_rate, 2),
            "V1 %": round(100*b.v1_rate, 2),
            "R %": round(100*b.r_rate, 2),
        })

    branches = pd.DataFrame(rows)
    if not branches.empty:
        branches = branches.sort_values(["Tier", "Oran %", "n"], ascending=[True, False, False])
        st.dataframe(branches, use_container_width=True, hide_index=True)

        csv = branches.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Dal tablosunu indir",
            csv,
            file_name="BIRLESME_MOTORU_DALLAR.csv",
            mime="text/csv"
        )

with tabs[3]:
    st.subheader("Motor mantığı")
    st.markdown(
        """
- **İlk 3:** `:02, :07, :12` → 0/3, 1/3, 2/3, 3/3.
- **İkinci 3:** `:17, :22, :27` → 0/3, 1/3, 2/3, 3/3.
- Bunlar birleşerek `0/3→0/3`, `1/3→2/3` gibi **geçiş ailelerini** oluşturur.
- Son 6 hedefte sayıların canlı izi ayrıca tutulur. Örneğin :47 öncesi `010`,
  `:32 yok → :37 var → :42 yok` demektir.
- Motor, 14 günlük geçmişte **aynı geçiş ailesi + aynı canlı iz + aynı hedef dakika**
  hücrelerini öğrenir.
- Güven filtresinden geçen dallar **CORE / SUPPORT** olur.
- Aynı daldan en fazla 2, aynı geçiş ailesinden en fazla 3 sayı alınır.
- Yeterli sinyal yoksa **ABSTAIN**.
- Hedef çekiliş sonucu, o hedef için seçim özelliği olarak kullanılmaz.
        """
    )
