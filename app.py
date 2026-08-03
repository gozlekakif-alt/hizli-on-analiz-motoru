import io
import math
import re
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On Analiz Motoru", page_icon="🎯", layout="wide")
st.title("🎯 Hızlı On Analiz Motoru")
st.caption("TXT, CSV veya Excel veri havuzunu yükle; temizleme, doğrulama ve analizleri otomatik çalıştır.")
st.warning("Bu araç istatistiksel analiz içindir; kesin sonuç veya kazanç garantisi vermez.")

BANDS = [(1, 20), (21, 40), (41, 60), (61, 80)]
BAND_NAMES = ["1-20", "21-40", "41-60", "61-80"]

def parse_draw_line(line):
    line = str(line).strip()
    if not line or not re.match(r"^\d{5}", line):
        return None

    draw_no = int(re.match(r"^(\d{5})", line).group(1))
    rest = line[5:].lstrip(";, \t")

    date = None
    time = None
    md = re.search(r"(\d{2}\.\d{2}\.\d{4})", rest)
    if md:
        date = md.group(1)
    mt = re.search(r"(?<!\d)(\d{2}:\d{2})(?!\d)", rest)
    if mt:
        time = mt.group(1)

    cleaned = rest
    if date:
        cleaned = cleaned.replace(date, " ")
    if time:
        cleaned = cleaned.replace(time, " ")

    nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", cleaned)]
    unique_nums = []
    for n in nums:
        if 1 <= n <= 80 and n not in unique_nums:
            unique_nums.append(n)

    return {
        "CekilisNo": draw_no,
        "Tarih": date,
        "Saat": time,
        "Sayilar": sorted(unique_nums),
        "Gecerli": len(unique_nums) == 20,
        "HamSatir": line,
    }

def parse_txt(data):
    text = data.decode("utf-8", errors="ignore")
    records = []
    for line in text.splitlines():
        rec = parse_draw_line(line)
        if rec:
            records.append(rec)
    return records

def parse_excel(data):
    xls = pd.ExcelFile(io.BytesIO(data))
    preferred = None
    for name in xls.sheet_names:
        if name.strip().lower() in {"güncel veri", "guncel veri", "veri", "data"}:
            preferred = name
            break

    sheet_names = ([preferred] if preferred else []) + [s for s in xls.sheet_names if s != preferred]
    for sheet in sheet_names:
        df = pd.read_excel(io.BytesIO(data), sheet_name=sheet)
        cols = list(df.columns)
        number_cols = []
        for c in cols:
            nc = str(c).strip().lower().replace("ı", "i")
            if re.fullmatch(r"(sayi|numara|number)[ _-]?\d+", nc):
                number_cols.append(c)

        if len(number_cols) >= 20:
            def idx(c):
                m = re.search(r"(\d+)$", str(c))
                return int(m.group(1)) if m else 999

            number_cols = sorted(number_cols, key=idx)[:20]
            records = []
            for _, row in df.iterrows():
                nums = pd.to_numeric(row[number_cols], errors="coerce").dropna().astype(int).tolist()
                nums = sorted(set(n for n in nums if 1 <= n <= 80))
                if len(nums) == 20:
                    records.append({
                        "CekilisNo": int(row.get("CekilisNo", row.get("Çekiliş No", len(records)+1))),
                        "Tarih": row.get("Tarih", None),
                        "Saat": row.get("Saat", None),
                        "Sayilar": nums,
                        "Gecerli": True,
                        "HamSatir": "",
                    })
            if records:
                return records
    raise ValueError("Excel içinde 20 sayılık çekiliş tablosu bulunamadı.")

def band_counts(draw):
    return np.array([sum(a <= n <= b for n in draw) for a, b in BANDS], dtype=int)

def overlap(a, b):
    return len(set(a) & set(b))

def consecutive_blocks(draw):
    s = sorted(draw)
    if not s:
        return []
    blocks = []
    cur = [s[0]]
    for n in s[1:]:
        if n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2:
                blocks.append(cur)
            cur = [n]
    if len(cur) >= 2:
        blocks.append(cur)
    return blocks

uploaded = st.file_uploader("Veri havuzunu yükle", type=["txt", "csv", "xlsx", "xls"])

if uploaded is None:
    st.info("Başlamak için TXT, CSV veya Excel dosyasını yükle.")
    st.stop()

raw = uploaded.getvalue()
name = uploaded.name.lower()

try:
    if name.endswith(".txt") or name.endswith(".csv"):
        records = parse_txt(raw)
    else:
        records = parse_excel(raw)
except Exception as exc:
    st.error(f"Dosya okunamadı: {exc}")
    st.stop()

if not records:
    st.error("Dosyada çekiliş satırı bulunamadı.")
    st.stop()

df = pd.DataFrame(records)

# Mükerrer çekiliş numaralarında ilk geçerli kaydı koru
df["Oncelik"] = df["Gecerli"].astype(int)
df = df.sort_values(["CekilisNo", "Oncelik"], ascending=[True, False])
df = df.drop_duplicates(subset=["CekilisNo"], keep="first").drop(columns=["Oncelik"])
df = df.sort_values("CekilisNo").reset_index(drop=True)

valid_df = df[df["Gecerli"]].copy()
invalid_df = df[~df["Gecerli"]].copy()
draws = valid_df["Sayilar"].tolist()

st.success(f"{len(df):,} benzersiz çekiliş bulundu; {len(valid_df):,} geçerli, {len(invalid_df):,} hatalı/eksik satır.")

a, b, c, d = st.columns(4)
a.metric("Benzersiz çekiliş", f"{len(df):,}")
b.metric("Geçerli çekiliş", f"{len(valid_df):,}")
c.metric("Hatalı satır", f"{len(invalid_df):,}")
d.metric("Eksik çekiliş no", max(0, int(df["CekilisNo"].max() - df["CekilisNo"].min() + 1 - len(df))))

tabs = st.tabs(["🧹 Veri Kontrolü", "📊 Temel Analiz", "🔗 İkili / Üçlü", "🧭 Faz", "📥 İndir"])

with tabs[0]:
    if len(invalid_df):
        st.subheader("Hatalı veya eksik satırlar")
        show = invalid_df[["CekilisNo", "Tarih", "Saat", "Sayilar", "HamSatir"]].copy()
        show["Sayı adedi"] = show["Sayilar"].apply(len)
        st.dataframe(show, use_container_width=True)
    else:
        st.success("Tüm satırlar geçerli.")

with tabs[1]:
    if not draws:
        st.stop()

    freq = Counter(n for d in draws for n in d)
    last_seen = {}
    for i, d in enumerate(draws):
        for n in d:
            last_seen[n] = i

    stats = pd.DataFrame({
        "Sayı": range(1, 81),
        "Frekans": [freq[n] for n in range(1, 81)],
        "Oran %": [round(100 * freq[n] / len(draws), 2) for n in range(1, 81)],
        "Dinlenme eli": [(len(draws)-1) - last_seen.get(n, -1) for n in range(1, 81)],
    })

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("En sık gelenler")
        st.dataframe(stats.sort_values("Frekans", ascending=False).head(20), use_container_width=True)
    with col2:
        st.subheader("En uzun dinlenenler")
        st.dataframe(stats.sort_values("Dinlenme eli", ascending=False).head(20), use_container_width=True)

    if len(draws) > 1:
        avg_repeat = np.mean([overlap(draws[i-1], draws[i]) for i in range(1, len(draws))])
        st.metric("Ortalama ardışık çekiliş tekrar sayısı", f"{avg_repeat:.3f}")

with tabs[2]:
    pair_counts = Counter()
    triple_counts = Counter()
    for d in draws:
        pair_counts.update(combinations(d, 2))
        triple_counts.update(combinations(d, 3))

    pairs = pd.DataFrame(
        [(a, b, c) for (a, b), c in pair_counts.most_common(50)],
        columns=["Sayı 1", "Sayı 2", "Birlikte geliş"],
    )
    triples = pd.DataFrame(
        [(a, b, c, cnt) for (a, b, c), cnt in triple_counts.most_common(50)],
        columns=["Sayı 1", "Sayı 2", "Sayı 3", "Birlikte geliş"],
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("En güçlü ikililer")
        st.dataframe(pairs, use_container_width=True)
    with c2:
        st.subheader("En güçlü üçlüler")
        st.dataframe(triples, use_container_width=True)

with tabs[3]:
    latest = draws[-1]
    bands = band_counts(latest)
    blocks = consecutive_blocks(latest)
    st.write("Son çekiliş:", latest)
    st.write("Bant dağılımı:", dict(zip(BAND_NAMES, bands.tolist())))
    st.write("Ardışık bloklar:", ["-".join(map(str, b)) for b in blocks] or "Yok")
    band_df = pd.DataFrame({"Bant": BAND_NAMES, "Adet": bands}).set_index("Bant")
    st.bar_chart(band_df)

with tabs[4]:
    clean_rows = []
    for _, row in valid_df.iterrows():
        clean_rows.append([
            row["CekilisNo"],
            row["Tarih"],
            row["Saat"],
            *row["Sayilar"],
        ])

    cols = ["CekilisNo", "Tarih", "Saat"] + [f"Sayi_{i}" for i in range(1, 21)]
    clean_df = pd.DataFrame(clean_rows, columns=cols)

    csv_bytes = clean_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Temiz CSV indir",
        data=csv_bytes,
        file_name="Hizli_On_Temiz_Verihavuzu.csv",
        mime="text/csv",
    )

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        clean_df.to_excel(writer, sheet_name="Guncel Veri", index=False)
        if len(invalid_df):
            invalid_df.to_excel(writer, sheet_name="Hatalı Satırlar", index=False)

    st.download_button(
        "Temiz Excel indir",
        data=out.getvalue(),
        file_name="Hizli_On_Temiz_Verihavuzu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
