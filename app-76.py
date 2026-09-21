import streamlit as st
import pandas as pd
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Hızlı On — 14 Gün Yolculuk", layout="wide")
st.title("Hızlı On — 14 Gün Saatlik Frekans & Nöbet Yolculuğu")
st.caption("GitHub'daki veri.txt dosyasını doğrudan okur: draw_id;tarih saat;20 sayı")

DATA_FILE = Path(__file__).resolve().parent / "veri.txt"

def parse_veri(text):
    rows, errors = [], []
    for ln, raw in enumerate(text.splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            parts = raw.split(";")
            if len(parts) != 3:
                raise ValueError("3 noktalı-virgül alanı yok")
            draw_id = int(parts[0].strip())
            dt = datetime.strptime(parts[1].strip(), "%d.%m.%Y %H:%M")
            nums = [int(x.strip()) for x in parts[2].split(",") if x.strip()]
            if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
                raise ValueError("20 benzersiz 1–80 sayısı değil")
            rows.append((draw_id, dt, nums))
        except Exception as e:
            errors.append((ln, str(e), raw[:120]))
    return rows, errors

if not DATA_FILE.exists():
    st.error("veri.txt bulunamadı. app.py ile veri.txt GitHub'da aynı klasörde olmalı.")
    st.stop()

text = DATA_FILE.read_text(encoding="utf-8-sig", errors="ignore")
draws, errors = parse_veri(text)
if not draws:
    st.error("veri.txt bulundu fakat geçerli çekiliş okunamadı.")
    st.stop()

by_day = defaultdict(list)
for did, dt, nums in draws:
    by_day[dt.date()].append((did, dt, nums))
for d in by_day:
    by_day[d].sort(key=lambda x: x[1])

def cls(v):
    return f"+{v}" if v <= 9 else "+10+"

hour_rows, journey_rows, report = [], [], []
for day in sorted(by_day):
    ds = by_day[day]
    # Takvim saati bazında: o saate ait tüm çekilişler.
    hour_map = defaultdict(list)
    for did, dt, nums in ds:
        hour_map[dt.hour].append((did, dt, nums))
    hours = sorted(hour_map)

    report += ["="*95, f"GÜN {day.strftime('%d.%m.%Y')} | {len(ds)} çekiliş", "="*95]
    counts_by_hour = {}

    for h in hours:
        block = hour_map[h]
        c = Counter(n for _,_,nums in block for n in nums)
        counts_by_hour[h] = c
        report.append(f"\nSAAT {h:02d}:00–{h:02d}:59 | {len(block)} çekiliş")
        for level in range(0, 11):
            if level < 10:
                nums = [n for n in range(1,81) if c[n] == level]
                label = f"+{level}"
            else:
                nums = [n for n in range(1,81) if c[n] >= 10]
                label = "+10+"
            report.append(f"{label}: " + (", ".join(map(str,nums)) if nums else "–"))
            for n in nums:
                hour_rows.append([day.strftime("%d.%m.%Y"), f"{h:02d}:00", label, n, c[n]])

    report.append("\n--- NÖBET DEĞİŞİMİ / SAATTEN SAATE SAYI YOLCULUĞU ---")
    for h1,h2 in zip(hours,hours[1:]):
        c1,c2 = counts_by_hour[h1],counts_by_hour[h2]
        groups=defaultdict(list)
        for n in range(1,81):
            a,b=c1[n],c2[n]
            groups[(cls(a),cls(b))].append(n)
            journey_rows.append([day.strftime("%d.%m.%Y"),f"{h1:02d}:00",f"{h2:02d}:00",
                                 n,a,b,cls(a)+" → "+cls(b),b-a])
        report.append(f"\n{h1:02d}:00 → {h2:02d}:00")
        for (a,b), nums in sorted(groups.items()):
            if a=="+0" and b=="+0":
                continue
            report.append(f"{a} → {b}: "+", ".join(map(str,nums)))

hourly = pd.DataFrame(hour_rows, columns=["Gün","Saat","Sınıf","Sayı","Frekans"])
journey = pd.DataFrame(journey_rows, columns=["Gün","Önceki Saat","Sonraki Saat","Sayı",
                                              "Önceki Frekans","Sonraki Frekans","Geçiş","Fark"])
report_txt="\n".join(report)

a,b,c,d=st.columns(4)
a.metric("Gün",len(by_day))
b.metric("Çekiliş",len(draws))
c.metric("Hatalı satır",len(errors))
d.metric("Tarih",f"{min(by_day).strftime('%d.%m')}–{max(by_day).strftime('%d.%m')}")

if len(draws)==3038 and len(by_day)==14 and not errors:
    st.success("VERİ DOĞRULANDI: 14 gün × 217 = 3.038 çekiliş, tüm satırlar 20 sayı.")
else:
    st.warning(f"Dosya okundu: {len(by_day)} gün / {len(draws)} çekiliş / {len(errors)} hatalı satır.")

t1,t2,t3,t4=st.tabs(["Saatlik +0…+10+","Nöbet Yolculuğu","14 Gün Geçiş Özeti","Tek Çıktı"])

with t1:
    day=st.selectbox("Gün",sorted(hourly["Gün"].unique()),key="hday")
    hh=st.selectbox("Saat",sorted(hourly[hourly["Gün"]==day]["Saat"].unique()),key="hh")
    v=hourly[(hourly["Gün"]==day)&(hourly["Saat"]==hh)]
    for lab in [f"+{i}" for i in range(10)]+["+10+"]:
        nums=v[v["Sınıf"]==lab]["Sayı"].tolist()
        st.write(f"**{lab}:** "+(", ".join(map(str,nums)) if nums else "–"))

with t2:
    day=st.selectbox("Gün",sorted(journey["Gün"].unique()),key="jday")
    j=journey[journey["Gün"]==day]
    j=j[~((j["Önceki Frekans"]==0)&(j["Sonraki Frekans"]==0))]
    st.dataframe(j,use_container_width=True,height=650)

with t3:
    s=(journey.groupby("Geçiş")
       .agg(Adet=("Sayı","size"),Gün=("Gün","nunique"),Farklı_Sayı=("Sayı","nunique"))
       .reset_index().sort_values("Adet",ascending=False))
    st.dataframe(s,use_container_width=True,height=650)

with t4:
    st.download_button("14 GÜN TEK TXT",report_txt.encode("utf-8"),
                       "14_GUN_0_10_NOBET_YOLCULUK.txt","text/plain")
    st.download_button("YOLCULUK CSV",journey.to_csv(index=False).encode("utf-8-sig"),
                       "14_GUN_NOBET_YOLCULUK.csv","text/csv")
    st.text_area("Tek çıktı önizleme",report_txt,height=550)
