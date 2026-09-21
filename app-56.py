import streamlit as st
import re
from collections import Counter, defaultdict
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="Hızlı On — Saatlik Yolculuk Motoru", layout="wide")
st.title("Hızlı On — 14 Gün Saatlik Frekans & Nöbet Değişimi")
st.caption("veri.txt ham çekiliş havuzunu okur. Her günü bağımsız işler; her saat için +0…+10+ sınıflarını ve saatler arası sayı yolculuğunu çıkarır.")

DEFAULT_FILE = "veri.txt"

def read_text(uploaded):
    if uploaded is not None:
        return uploaded.getvalue().decode("utf-8", errors="ignore")
    try:
        return Path(DEFAULT_FILE).read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        st.error("veri.txt bulunamadı. GitHub deposunda app.py ile aynı klasöre veri.txt koy veya soldan TXT yükle.")
        st.stop()

def parse_draws(text):
    # Ham biçim örneği:
    # Çekiliş no: 51449
    # 26.08.2026-07:32
    # 1
    # 9 ...
    # Ayrıca tarih ile saat arasında boşluk / tire varyasyonlarını kabul eder.
    draw_pat = re.compile(
        r"Çekiliş\s*no\s*:\s*#?\s*(\d+)\s*"
        r"(\d{2}\.\d{2}\.\d{4})\s*[-–—]?\s*(\d{2}:\d{2})",
        re.I
    )
    matches = list(draw_pat.finditer(text))
    rows = []
    for i, m in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[m.end():end]
        nums = []
        for line in block.splitlines():
            s = line.strip()
            if re.fullmatch(r"\d{1,2}", s):
                n = int(s)
                if 1 <= n <= 80:
                    nums.append(n)
            if len(nums) == 20:
                break
        if len(nums) == 20:
            dt = datetime.strptime(m.group(2) + " " + m.group(3), "%d.%m.%Y %H:%M")
            rows.append({"draw_id": int(m.group(1)), "dt": dt, "numbers": nums})
    return rows

def band(c):
    # İstenen 0,+1,...,+9,+10+ sınıfları.
    return str(c) if c <= 9 else "10+"

def analyse(draws):
    by_day = defaultdict(list)
    for r in draws:
        by_day[r["dt"].date()].append(r)
    for d in by_day:
        by_day[d].sort(key=lambda x: x["dt"])

    hourly_rows = []
    journey_rows = []
    txt = []

    for day in sorted(by_day):
        day_draws = by_day[day]
        hours = sorted(set(r["dt"].hour for r in day_draws))
        hour_counts = {}

        txt.append("=" * 88)
        txt.append(f"GÜN: {day.strftime('%d.%m.%Y')} | ÇEKİLİŞ: {len(day_draws)}")
        txt.append("=" * 88)

        for h in hours:
            hd = [r for r in day_draws if r["dt"].hour == h]
            c = Counter(n for r in hd for n in r["numbers"])
            hour_counts[h] = c
            txt.append(f"\nSAAT {h:02d}:00–{h:02d}:59 | {len(hd)} çekiliş")
            for k in range(0, 11):
                label = f"+{k}" if k < 10 else "+10+"
                nums = sorted(n for n in range(1,81) if (c[n] == k if k < 10 else c[n] >= 10))
                txt.append(f"{label}: " + (", ".join(map(str, nums)) if nums else "–"))
                for n in nums:
                    hourly_rows.append({
                        "Gün": day.strftime("%d.%m.%Y"),
                        "Saat": f"{h:02d}:00",
                        "Sınıf": label,
                        "Sayı": n,
                        "Saatte_Gelme": c[n]
                    })

        # Saatler arası nöbet değişimi: aynı sayının bir saatten sonraki saate sınıf geçişi.
        txt.append("\n--- SAATLER ARASI NÖBET DEĞİŞİMİ / YOLCULUK ---")
        for h1, h2 in zip(hours, hours[1:]):
            c1, c2 = hour_counts[h1], hour_counts[h2]
            transition_groups = defaultdict(list)
            for n in range(1,81):
                a, b = c1[n], c2[n]
                transition_groups[(band(a), band(b))].append(n)
                journey_rows.append({
                    "Gün": day.strftime("%d.%m.%Y"),
                    "Önceki_Saat": f"{h1:02d}:00",
                    "Sonraki_Saat": f"{h2:02d}:00",
                    "Sayı": n,
                    "Önceki_Frekans": a,
                    "Sonraki_Frekans": b,
                    "Geçiş": f"+{band(a)} → +{band(b)}",
                    "Fark": b-a
                })
            txt.append(f"\n{h1:02d}:00 → {h2:02d}:00")
            # Sadece hareket edenleri yaz; 0→0 gürültüsünü rapordan çıkar.
            for (a,b), nums in sorted(transition_groups.items(), key=lambda z: (int(z[0][0].replace("+","").replace("10+","10")) if z[0][0]!="10+" else 10,
                                                                                int(z[0][1].replace("+","").replace("10+","10")) if z[0][1]!="10+" else 10)):
                if a == "0" and b == "0":
                    continue
                txt.append(f"+{a} → +{b}: " + ", ".join(map(str, nums)))

    return pd.DataFrame(hourly_rows), pd.DataFrame(journey_rows), "\n".join(txt), by_day

uploaded = st.sidebar.file_uploader("İstersen veri.txt yükle", type=["txt"])
text = read_text(uploaded)
draws = parse_draws(text)

if not draws:
    st.error("Ham çekilişler okunamadı. Beklenen yapı: 'Çekiliş no:', tarih-saat ve altında 20 sayı.")
    st.stop()

hourly_df, journey_df, report_txt, by_day = analyse(draws)

c1, c2, c3 = st.columns(3)
c1.metric("Okunan gün", len(by_day))
c2.metric("Okunan çekiliş", len(draws))
c3.metric("İlk–son", f"{min(by_day).strftime('%d.%m')} – {max(by_day).strftime('%d.%m')}")

if len(by_day) != 14:
    st.warning(f"14 gün bekleniyordu; dosyada {len(by_day)} ayrı gün okundu. Analiz yine mevcut günlerin tamamı için üretildi.")

tab1, tab2, tab3 = st.tabs(["Saatlik +0…+10+", "Nöbet / Yolculuk", "Tek Çıktı"])

with tab1:
    day = st.selectbox("Gün", sorted(hourly_df["Gün"].unique()), key="day1")
    h = st.selectbox("Saat", sorted(hourly_df.loc[hourly_df["Gün"]==day, "Saat"].unique()), key="hour1")
    view = hourly_df[(hourly_df["Gün"]==day) & (hourly_df["Saat"]==h)]
    for k in [f"+{i}" for i in range(10)] + ["+10+"]:
        nums = view.loc[view["Sınıf"]==k, "Sayı"].tolist()
        st.write(f"**{k}:** " + (", ".join(map(str, nums)) if nums else "–"))

with tab2:
    day2 = st.selectbox("Gün", sorted(journey_df["Gün"].unique()), key="day2")
    j = journey_df[journey_df["Gün"]==day2].copy()
    only_active = st.checkbox("0 → 0 satırlarını gizle", value=True)
    if only_active:
        j = j[~((j["Önceki_Frekans"]==0) & (j["Sonraki_Frekans"]==0))]
    st.dataframe(j, use_container_width=True, height=600)

    st.subheader("14 günlük geçiş özeti")
    summary = (journey_df.groupby(["Geçiş"])
               .agg(Geçiş_Sayısı=("Sayı","size"),
                    Farklı_Gün=("Gün","nunique"),
                    Farklı_Sayı=("Sayı","nunique"))
               .reset_index()
               .sort_values("Geçiş_Sayısı", ascending=False))
    st.dataframe(summary, use_container_width=True)

with tab3:
    st.text_area("14 gün — tek rapor", report_txt, height=650)
    st.download_button("TEK TXT ÇIKTISINI İNDİR",
                       data=report_txt.encode("utf-8"),
                       file_name="14_GUN_SAATLIK_0_10_YOLCULUK_RAPORU.txt",
                       mime="text/plain")
    st.download_button("YOLCULUK CSV İNDİR",
                       data=journey_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="14_GUN_NOBET_YOLCULUK.csv",
                       mime="text/csv")

st.info("Bu sürüm geleceği kullanmaz; yalnız gerçekleşmiş saat frekanslarını ve saat→saat geçişlerini gösterir. Sonraki aşamada aynı yapı üzerinden 'saat tamamlanmadan önce hangi +4/+5/+6… adayları bulunabiliyordu?' walk-forward testi eklenebilir.")
