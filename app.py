import io
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Hızlı On Ultimate Analiz Motoru V6 V6",
    page_icon="🎯",
    layout="wide",
)

BASE_FILE = Path(__file__).parent / "veri.txt"
COLS = ["Cekilis_No", "Tarih", "Saat"] + [f"Sayi_{i}" for i in range(1, 21)]
NUM_COLS = [f"Sayi_{i}" for i in range(1, 21)]
BANDS = [(1, 20), (21, 40), (41, 60), (61, 80)]
BAND_NAMES = ["1-20", "21-40", "41-60", "61-80"]


def parse_standard_line(line: str):
    raw = str(line).strip()
    if not raw:
        return None

    m = re.match(
        r"^\s*(\d+)\s*[;,]\s*(\d{2}[./]\d{2}[./]\d{4})\s*[;,]\s*(\d{2}:\d{2})\s*[;,]\s*(.*)$",
        raw,
    )
    if not m:
        return None

    nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", m.group(4))]
    if len(nums) != 20 or len(set(nums)) != 20:
        return None

    return [int(m.group(1)), m.group(2).replace("/", "."), m.group(3)] + sorted(nums)


def parse_draw_block(text: str):
    no = re.search(r"Çekiliş\s*no\s*:\s*(\d+)", text, re.I)
    dt = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})", text)
    nums = [int(x) for x in re.findall(r"(?m)^\s*(\d{1,2})\s*$", text)]

    if not no or not dt or len(nums) != 20:
        return None
    if len(set(nums)) != 20 or any(n < 1 or n > 80 for n in nums):
        return None

    return [int(no.group(1)), dt.group(1), dt.group(2)] + sorted(nums)


def dataframe_from_text(text: str):
    valid, invalid = [], []
    lines = text.splitlines()

    for idx, line in enumerate(lines, 1):
        row = parse_standard_line(line)
        if row:
            valid.append(row)
        elif line.strip():
            invalid.append(f"Satır {idx}: {line[:140]}")

    # Ham blok formatı varsa ayrıca dene.
    if not valid and "Çekiliş no:" in text:
        blocks = re.split(r"(?=Çekiliş\s*no\s*:)", text, flags=re.I)
        invalid = []
        for idx, block in enumerate(blocks, 1):
            if not block.strip():
                continue
            row = parse_draw_block(block)
            if row:
                valid.append(row)
            else:
                invalid.append(f"Blok {idx}: okunamadı")

    df = pd.DataFrame(valid, columns=COLS)
    return clean_df(df), invalid


def clean_df(df: pd.DataFrame):
    if df.empty:
        return pd.DataFrame(columns=COLS)

    out = df.copy()
    for c in ["Cekilis_No"] + NUM_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["Cekilis_No"] + NUM_COLS)
    out["Cekilis_No"] = out["Cekilis_No"].astype(int)
    for c in NUM_COLS:
        out[c] = out[c].astype(int)

    valid_mask = out[NUM_COLS].apply(
        lambda r: len(set(r.tolist())) == 20 and all(1 <= int(n) <= 80 for n in r),
        axis=1,
    )
    out = out[valid_mask]
    out = out.drop_duplicates("Cekilis_No", keep="last").sort_values("Cekilis_No")
    return out[COLS].reset_index(drop=True)


def read_uploaded_file(uploaded):
    name = uploaded.name.lower()
    raw = uploaded.getvalue()

    if name.endswith((".txt", ".csv")):
        text = raw.decode("utf-8", errors="ignore")
        # Önce standart metin okuyucu
        df, invalid = dataframe_from_text(text)
        if not df.empty:
            return df, invalid

        # Klasik CSV tablo biçimi
        for sep in [",", ";"]:
            try:
                tmp = pd.read_csv(io.BytesIO(raw), sep=sep)
                if set(COLS).issubset(tmp.columns):
                    return clean_df(tmp[COLS]), []
            except Exception:
                pass
        return pd.DataFrame(columns=COLS), ["Dosya biçimi okunamadı"]

    if name.endswith((".xlsx", ".xls")):
        try:
            tmp = pd.read_excel(io.BytesIO(raw))
            if set(COLS).issubset(tmp.columns):
                return clean_df(tmp[COLS]), []
            if len(tmp.columns) >= 23:
                tmp = tmp.iloc[:, :23].copy()
                tmp.columns = COLS
                return clean_df(tmp), []
            return pd.DataFrame(columns=COLS), ["Excel sütunları uygun değil"]
        except Exception as exc:
            return pd.DataFrame(columns=COLS), [f"Excel okunamadı: {exc}"]

    return pd.DataFrame(columns=COLS), ["Desteklenmeyen dosya türü"]


@st.cache_data(show_spinner=False)
def load_base():
    if not BASE_FILE.exists():
        return pd.DataFrame(columns=COLS), ["veri.txt bulunamadı"]
    return dataframe_from_text(BASE_FILE.read_text(encoding="utf-8", errors="ignore"))


def merge_data(*frames):
    valid = [f for f in frames if f is not None and not f.empty]
    if not valid:
        return pd.DataFrame(columns=COLS)
    return clean_df(pd.concat(valid, ignore_index=True))


def row_sets(df):
    return [set(map(int, r)) for r in df[NUM_COLS].to_numpy()]


def frequency(df):
    c = Counter(map(int, df[NUM_COLS].to_numpy().ravel()))
    return pd.DataFrame([{"Sayı": n, "Frekans": c.get(n, 0)} for n in range(1, 81)])


def gaps(df):
    sets = row_sets(df)
    out = []
    for n in range(1, 81):
        gap = len(sets)
        for i, s in enumerate(reversed(sets)):
            if n in s:
                gap = i
                break
        out.append({"Sayı": n, "Dinlenme": gap})
    return pd.DataFrame(out)


def consecutive_blocks(nums):
    nums = sorted(nums)
    if not nums:
        return []
    blocks, cur = [], [nums[0]]
    for n in nums[1:]:
        if n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2:
                blocks.append(cur)
            cur = [n]
    if len(cur) >= 2:
        blocks.append(cur)
    return blocks


def combo_table(df, size, top_n):
    c = Counter()
    for s in row_sets(df):
        c.update(combinations(sorted(s), size))
    return pd.DataFrame(
        [{"Grup": " - ".join(map(str, k)), "Frekans": v} for k, v in c.most_common(top_n)]
    )


def combo_dates(df, size, top_n):
    counts = Counter()
    occurrences = defaultdict(list)
    for _, row in df.iterrows():
        nums = sorted(int(row[c]) for c in NUM_COLS)
        for combo in combinations(nums, size):
            counts[combo] += 1
            occurrences[combo].append(f"{row.Tarih} {row.Saat} #{int(row.Cekilis_No)}")
    rows = []
    for combo, freq in counts.most_common(top_n):
        rows.append({
            "Grup": " - ".join(map(str, combo)),
            "Frekans": freq,
            "Son örnekler": " | ".join(occurrences[combo][-5:]),
        })
    return pd.DataFrame(rows)


def repeat_table(df):
    sets = row_sets(df)
    rows = []
    for i in range(1, len(sets)):
        common = sorted(sets[i] & sets[i - 1])
        rows.append({
            "Çekiliş": int(df.iloc[i].Cekilis_No),
            "Tekrar sayısı": len(common),
            "Tekrar edenler": " - ".join(map(str, common)),
        })
    return pd.DataFrame(rows).sort_values("Çekiliş", ascending=False) if rows else pd.DataFrame()


def block_table(df, last_n):
    prev, rows = [], []
    for _, row in df.tail(last_n).iterrows():
        blocks = consecutive_blocks([int(row[c]) for c in NUM_COLS])
        shifts = []
        for b in blocks:
            for p in prev:
                if len(b) == len(p):
                    d = b[0] - p[0]
                    if d in (-2, -1, 1, 2):
                        shifts.append(f"{'-'.join(map(str,p))} → {'-'.join(map(str,b))} ({d:+d})")
        rows.append({
            "Çekiliş": int(row.Cekilis_No),
            "Tarih": row.Tarih,
            "Saat": row.Saat,
            "Bloklar": ", ".join("-".join(map(str, b)) for b in blocks) or "Yok",
            "Kayma": "; ".join(shifts) or "Yok",
        })
        prev = blocks
    return pd.DataFrame(rows).sort_values("Çekiliş", ascending=False)


def streak_table(df):
    sets = row_sets(df)
    rows = []
    for n in range(1, 81):
        current = longest = breaks = 0
        for s in sets:
            if n in s:
                current += 1
                longest = max(longest, current)
            else:
                if current:
                    breaks += 1
                current = 0

        current_streak = 0
        for s in reversed(sets):
            if n in s:
                current_streak += 1
            else:
                break

        rows.append({
            "Sayı": n,
            "Mevcut seri": current_streak,
            "En uzun seri": longest,
            "Seri kırılma": breaks,
        })
    return pd.DataFrame(rows)


def band_table(df):
    rows = []
    for _, row in df.iterrows():
        nums = [int(row[c]) for c in NUM_COLS]
        vals = {name: sum(lo <= n <= hi for n in nums) for name, (lo, hi) in zip(BAND_NAMES, BANDS)}
        rows.append({"Çekiliş": int(row.Cekilis_No), "Tarih": row.Tarih, "Saat": row.Saat, **vals})
    return pd.DataFrame(rows)


def period_name(t):
    h = int(str(t).split(":")[0])
    if h < 7:
        return "Gece"
    if h < 12:
        return "Sabah"
    if h < 17:
        return "Öğle"
    if h < 21:
        return "Akşam"
    return "Kapanış"


def period_summary(df):
    rows = []
    for period, group in df.groupby(df["Saat"].map(period_name)):
        hot = frequency(group).sort_values(["Frekans", "Sayı"], ascending=[False, True]).head(10)
        bands = band_table(group)[BAND_NAMES].mean().round(2)
        rows.append({
            "Dönem": period,
            "Çekiliş": len(group),
            "En sıcak 10": " - ".join(map(str, hot["Sayı"])),
            **{f"Ort. {k}": bands[k] for k in BAND_NAMES},
        })
    order = {"Gece": 0, "Sabah": 1, "Öğle": 2, "Akşam": 3, "Kapanış": 4}
    return pd.DataFrame(rows).sort_values("Dönem", key=lambda s: s.map(order))


def similar_draws(df, target, top_n=30):
    target = set(target)
    rows = []
    for _, row in df.iterrows():
        nums = set(int(row[c]) for c in NUM_COLS)
        common = sorted(target & nums)
        union = target | nums
        rows.append({
            "Çekiliş": int(row.Cekilis_No),
            "Tarih": row.Tarih,
            "Saat": row.Saat,
            "Ortak sayı": len(common),
            "Jaccard": round(len(common) / len(union), 3),
            "Ortak sayılar": " - ".join(map(str, common)),
        })
    return pd.DataFrame(rows).sort_values(["Ortak sayı", "Jaccard"], ascending=False).head(top_n)


def score_numbers(df, window):
    sub = df.tail(window)
    f = frequency(sub).set_index("Sayı")["Frekans"]
    g = gaps(df).set_index("Sayı")["Dinlenme"]

    pair_c = Counter()
    for s in row_sets(sub):
        pair_c.update(combinations(sorted(s), 2))

    rows = []
    for n in range(1, 81):
        pair_strength = sum(v for (a, b), v in pair_c.items() if a == n or b == n)
        rows.append({
            "Sayı": n,
            "Frekans": int(f.get(n, 0)),
            "Dinlenme": int(g.get(n, 0)),
            "Bağ gücü": int(pair_strength),
        })

    out = pd.DataFrame(rows)
    for c in ["Frekans", "Dinlenme", "Bağ gücü"]:
        out[c + "_n"] = out[c] / max(out[c].max(), 1)
    out["Skor"] = 0.45 * out["Frekans_n"] + 0.25 * out["Dinlenme_n"] + 0.30 * out["Bağ gücü_n"]
    return out


def generate_coupon(df, size, strategy, window):
    scores = score_numbers(df, window).set_index("Sayı")
    nums = np.arange(1, 81)

    if strategy == "Sıcak":
        w = np.array([(scores.loc[n, "Frekans"] + 1) ** 2 for n in nums], float)
    elif strategy == "Dinlenmiş":
        w = np.array([(scores.loc[n, "Dinlenme"] + 1) ** 1.6 for n in nums], float)
    elif strategy == "Bağ gücü":
        w = np.array([(scores.loc[n, "Bağ gücü"] + 1) ** 1.3 for n in nums], float)
    else:
        w = np.array([scores.loc[n, "Skor"] + 0.05 for n in nums], float)

    w /= w.sum()
    return sorted(np.random.choice(nums, size=size, replace=False, p=w).tolist())


def backtest(df, size, strategy, window, test_count):
    start = max(window, len(df) - test_count)
    rows = []
    for i in range(start, len(df)):
        train = df.iloc[:i]
        coupon = generate_coupon(train, size, strategy, min(window, len(train)))
        actual = set(int(df.iloc[i][c]) for c in NUM_COLS)
        hits = sorted(set(coupon) & actual)
        rows.append({
            "Çekiliş": int(df.iloc[i].Cekilis_No),
            "Kolon": " - ".join(map(str, coupon)),
            "İsabet": len(hits),
            "Tutan": " - ".join(map(str, hits)),
        })
    return pd.DataFrame(rows)


def missing_draws(df):
    if df.empty:
        return []
    available = set(df.Cekilis_No.astype(int))
    return [n for n in range(int(df.Cekilis_No.min()), int(df.Cekilis_No.max()) + 1) if n not in available]


def to_text(df):
    lines = []
    for _, row in df.sort_values("Cekilis_No").iterrows():
        nums = ",".join(str(int(row[c])) for c in NUM_COLS)
        lines.append(f"{int(row.Cekilis_No)};{row.Tarih};{row.Saat};{nums}")
    return "\n".join(lines) + "\n"


def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Veri")
        frequency(df).to_excel(writer, index=False, sheet_name="Frekans")
        gaps(df).to_excel(writer, index=False, sheet_name="Dinlenme")
        band_table(df).to_excel(writer, index=False, sheet_name="Bantlar")
    return output.getvalue()



def recent_window_comparison(df):
    windows = [5, 10, 20, 50, 100]
    rows = []
    for w in windows:
        if len(df) < w:
            continue
        sub = df.tail(w)
        freq = frequency(sub).sort_values(["Frekans", "Sayı"], ascending=[False, True])
        rep = repeat_table(sub)
        bands = band_table(sub)[BAND_NAMES].mean()
        rows.append({
            "Pencere": f"Son {w}",
            "Sıcak 10": " - ".join(map(str, freq.head(10)["Sayı"])),
            "Ort. tekrar": round(rep["Tekrar sayısı"].mean(), 2) if not rep.empty else 0,
            "Baskın bant": bands.idxmax(),
            "Bant ortalaması": round(float(bands.max()), 2),
        })
    return pd.DataFrame(rows)


def block_length_summary(df):
    counter = Counter()
    examples = defaultdict(list)
    for _, row in df.iterrows():
        blocks = consecutive_blocks([int(row[c]) for c in NUM_COLS])
        for block in blocks:
            size = len(block)
            if 2 <= size <= 5:
                key = tuple(block)
                counter[key] += 1
                examples[key].append(f"{row.Tarih} {row.Saat} #{int(row.Cekilis_No)}")
    rows = []
    for block, count in counter.most_common(100):
        rows.append({
            "Blok": " - ".join(map(str, block)),
            "Uzunluk": len(block),
            "Frekans": count,
            "Son örnekler": " | ".join(examples[block][-5:]),
        })
    return pd.DataFrame(rows)


def drift_detector(df, short_window=20, long_window=100):
    if len(df) < max(short_window, long_window):
        return pd.DataFrame(), "Değişim analizi için yeterli çekiliş yok."

    short = frequency(df.tail(short_window)).set_index("Sayı")["Frekans"] / short_window
    long = frequency(df.tail(long_window)).set_index("Sayı")["Frekans"] / long_window
    out = pd.DataFrame({
        "Sayı": range(1, 81),
        "Kısa oran": [short.get(n, 0) for n in range(1, 81)],
        "Uzun oran": [long.get(n, 0) for n in range(1, 81)],
    })
    out["Değişim"] = out["Kısa oran"] - out["Uzun oran"]
    out["Mutlak değişim"] = out["Değişim"].abs()

    recent_bands = band_table(df.tail(short_window))[BAND_NAMES].mean()
    long_bands = band_table(df.tail(long_window))[BAND_NAMES].mean()
    dominant_recent = recent_bands.idxmax()
    dominant_long = long_bands.idxmax()
    message = (
        f"Son {short_window} çekilişte baskın bant {dominant_recent}; "
        f"son {long_window} çekilişte baskın bant {dominant_long}. "
        f"En güçlü kısa dönem sapmaları yukarıdaki tabloda gösterilir."
    )
    return out.sort_values("Mutlak değişim", ascending=False), message


def closing_summary(df):
    close_df = df[df["Saat"].map(period_name) == "Kapanış"]
    if close_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    freq = frequency(close_df).sort_values(["Frekans", "Sayı"], ascending=[False, True])
    combos = combo_dates(close_df, 2, 30)
    return freq, combos


def coupon_check(coupon_text, result_text):
    coupon = sorted(set(int(x) for x in re.findall(r"\d+", coupon_text) if 1 <= int(x) <= 80))
    result = sorted(set(int(x) for x in re.findall(r"\d+", result_text) if 1 <= int(x) <= 80))
    hits = sorted(set(coupon) & set(result))
    return coupon, result, hits

def rule_based_interpretation(df, window):
    sub = df.tail(window)
    f = frequency(sub).sort_values("Frekans", ascending=False)
    rep = repeat_table(sub)
    bands = band_table(sub)
    hot = " - ".join(map(str, f.head(10)["Sayı"]))
    cold = " - ".join(map(str, f.tail(10)["Sayı"]))
    avg_repeat = rep["Tekrar sayısı"].mean() if not rep.empty else 0
    dominant_band = bands[BAND_NAMES].mean().idxmax()

    return (
        f"Son {len(sub)} çekilişte en sıcak 10 sayı: {hot}. "
        f"En düşük frekanslı 10 sayı: {cold}. "
        f"Ardışık çekilişlerde ortalama tekrar {avg_repeat:.2f} sayı. "
        f"Ortalama yoğunluğu en yüksek bant {dominant_band}. "
        "Bu yorum kural tabanlı istatistik özetidir; gerçek yapay zekâ tahmini veya garanti değildir."
    )


base_df, base_invalid = load_base()

if "extra_df" not in st.session_state:
    st.session_state.extra_df = pd.DataFrame(columns=COLS)

st.title("🎯 Hızlı On Ultimate Analiz Motoru V6 V6")
st.caption("Ana veri havuzu + sonradan dosya yükleme + tek çekiliş ekleme + analiz + dışa aktarma")

with st.sidebar:
    st.header("📥 Veri yükleme")
    uploads = st.file_uploader(
        "Yeni TXT, CSV veya Excel dosyalarını yükle",
        type=["txt", "csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    upload_messages = []
    if uploads:
        loaded_frames = []
        for uploaded in uploads:
            fdf, errs = read_uploaded_file(uploaded)
            if not fdf.empty:
                loaded_frames.append(fdf)
                upload_messages.append(f"{uploaded.name}: {len(fdf)} çekiliş okundu")
            else:
                upload_messages.append(f"{uploaded.name}: okunamadı")
            if errs:
                upload_messages.append(f"{uploaded.name}: {len(errs)} bozuk satır/blok")

        if loaded_frames:
            st.session_state.extra_df = merge_data(st.session_state.extra_df, *loaded_frames)

    for msg in upload_messages:
        st.write(msg)

    if st.button("Yüklenen geçici verileri temizle"):
        st.session_state.extra_df = pd.DataFrame(columns=COLS)
        st.rerun()

df = merge_data(base_df, st.session_state.extra_df)

if df.empty:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

latest = df.iloc[-1]
missing = missing_draws(df)

a, b, c, d = st.columns(4)
a.metric("Toplam çekiliş", len(df))
b.metric("Son çekiliş", int(latest.Cekilis_No))
c.metric("Son tarih/saat", f"{latest.Tarih} {latest.Saat}")
d.metric("Eksik çekiliş no", len(missing))

with st.sidebar:
    window = st.slider("Analiz penceresi", 50, max(50, len(df)), min(500, len(df)), 50)

adf = df.tail(window)

tabs = st.tabs([
    "✅ Kontrol",
    "📈 Frekans",
    "🔗 Birlikte Çıkma",
    "🔥 Sıcak/Soğuk",
    "⏳ Dinlenme/Döngü",
    "🔄 Tekrar/Blok",
    "📊 Bant/Saat",
    "🧭 Benzerlik",
    "🧠 Gün Yorumu",
    "🧬 Değişim Dedektörü",
    "🌙 Kapanış",
    "🎯 Kupon/Backtest",
    "✅ Kupon Kontrol",
    "➕ Yeni Çekiliş",
    "⬇️ Dışa Aktar",
])

with tabs[0]:
    st.write(f"Ana havuz: **{len(base_df)}** çekiliş")
    st.write(f"Bu oturumda yüklenen ek veri: **{len(st.session_state.extra_df)}** çekiliş")
    if missing:
        st.warning("Eksik çekiliş numaraları: " + ", ".join(map(str, missing[:500])))
    else:
        st.success("Çekiliş numaraları kesintisiz.")
    if base_invalid:
        with st.expander("Ana dosyada atlanan satırlar"):
            st.code("\n".join(base_invalid[:300]))

with tabs[1]:
    f = frequency(adf).sort_values(["Frekans", "Sayı"], ascending=[False, True])
    st.dataframe(f, use_container_width=True, hide_index=True)
    st.bar_chart(f.sort_values("Sayı").set_index("Sayı")["Frekans"])

with tabs[2]:
    subtabs = st.tabs(["2’li", "3’lü", "4’lü", "5’li"])
    for tab, size in zip(subtabs, [2, 3, 4, 5]):
        with tab:
            top_n = st.slider(f"İlk kaç {size}’li?", 10, 100, 30, key=f"combo_{size}")
            st.dataframe(combo_dates(adf, size, top_n), use_container_width=True, hide_index=True)

with tabs[3]:
    merged = frequency(adf).merge(gaps(df), on="Sayı")
    l, r = st.columns(2)
    with l:
        st.subheader("Sıcak")
        st.dataframe(merged.sort_values(["Frekans", "Dinlenme"], ascending=[False, True]).head(20),
                     use_container_width=True, hide_index=True)
    with r:
        st.subheader("Soğuk / dinlenmiş")
        st.dataframe(merged.sort_values(["Dinlenme", "Frekans"], ascending=[False, True]).head(20),
                     use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader("Dinlenme")
    st.dataframe(gaps(df).sort_values(["Dinlenme", "Sayı"], ascending=[False, True]),
                 use_container_width=True, hide_index=True)
    st.subheader("Seri ve kırılma")
    st.dataframe(streak_table(df).sort_values(["Mevcut seri", "En uzun seri"], ascending=False),
                 use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("Çekilişler arası tekrar")
    st.dataframe(repeat_table(adf).head(200), use_container_width=True, hide_index=True)
    st.subheader("Ardışık blok ve kayma")
    st.dataframe(block_table(df, min(window, 300)), use_container_width=True, hide_index=True)

with tabs[6]:
    bands = band_table(adf)
    st.subheader("Bant yoğunluğu")
    st.dataframe(bands.sort_values("Çekiliş", ascending=False), use_container_width=True, hide_index=True)
    st.bar_chart(bands[BAND_NAMES].mean())
    st.subheader("Saat dilimi davranışı")
    st.dataframe(period_summary(adf), use_container_width=True, hide_index=True)

with tabs[7]:
    default_target = " ".join(str(int(latest[c])) for c in NUM_COLS)
    target_text = st.text_area("20 hedef sayı", value=default_target, height=100)
    target = sorted(set(int(x) for x in re.findall(r"\d+", target_text) if 1 <= int(x) <= 80))
    if len(target) == 20:
        st.dataframe(similar_draws(df.iloc[:-1], target), use_container_width=True, hide_index=True)
    else:
        st.info(f"20 farklı sayı gerekli. Şu an {len(target)} sayı var.")

with tabs[8]:
    st.info(rule_based_interpretation(df, window))
    st.caption("Bu bölüm dış API kullanmadan kural tabanlı istatistik yorumu üretir.")

with tabs[9]:
    st.subheader("Kısa ve uzun dönem karşılaştırması")
    st.dataframe(recent_window_comparison(df), use_container_width=True, hide_index=True)
    drift, drift_msg = drift_detector(df)
    st.info(drift_msg)
    if not drift.empty:
        st.dataframe(drift.head(30), use_container_width=True, hide_index=True)
    st.subheader("2–5’li ardışık blok özeti")
    st.dataframe(block_length_summary(adf), use_container_width=True, hide_index=True)

with tabs[10]:
    close_freq, close_combos = closing_summary(df)
    if close_freq.empty:
        st.info("Kapanış döneminde kayıt bulunamadı.")
    else:
        st.subheader("Kapanış sıcak sayıları")
        st.dataframe(close_freq.head(30), use_container_width=True, hide_index=True)
        st.subheader("Kapanışta en sık birlikte çıkan ikililer")
        st.dataframe(close_combos, use_container_width=True, hide_index=True)

with tabs[11]:
    c1, c2, c3 = st.columns(3)
    with c1:
        size = st.selectbox("Kolon büyüklüğü", [3, 4, 5, 6, 7, 8, 10], index=4)
    with c2:
        count = st.slider("Kolon sayısı", 1, 10, 4)
    with c3:
        strategy = st.selectbox("Strateji", ["Dengeli", "Sıcak", "Dinlenmiş", "Bağ gücü"])

    if st.button("Kolon üret", type="primary"):
        made = set()
        tries = 0
        while len(made) < count and tries < 1000:
            made.add(tuple(generate_coupon(df, size, strategy, window)))
            tries += 1
        for i, coupon in enumerate(sorted(made), 1):
            st.success(f"Kolon {i}: " + " - ".join(map(str, coupon)))

    test_count = st.slider("Backtest çekiliş sayısı", 10, min(300, max(10, len(df) - 50)), min(100, max(10, len(df) - 50)))
    if st.button("Backtest çalıştır"):
        result = backtest(df, size, strategy, window, test_count)
        if not result.empty:
            x, y = st.columns(2)
            x.metric("Ortalama isabet", f"{result['İsabet'].mean():.2f}")
            y.metric("En yüksek isabet", int(result["İsabet"].max()))
            st.dataframe(result.sort_values("Çekiliş", ascending=False), use_container_width=True, hide_index=True)

with tabs[12]:
    st.subheader("Kupon ile sonuç karşılaştır")
    coupon_text = st.text_area("Kupon sayıları", placeholder="7 11 18 24 39 52 71", key="coupon_check_coupon")
    result_text = st.text_area("Çekiliş sonucu (20 sayı)", placeholder="1 7 11 14 18 ...", key="coupon_check_result")
    if coupon_text.strip() and result_text.strip():
        coupon_vals, result_vals, hits = coupon_check(coupon_text, result_text)
        st.write("Kupon:", " - ".join(map(str, coupon_vals)))
        st.write("Tutan sayılar:", " - ".join(map(str, hits)) or "Yok")
        st.metric("İsabet", f"{len(hits)} / {len(coupon_vals)}")

with tabs[13]:
    raw = st.text_area("Yeni çekilişi yapıştır", height=280, placeholder="""Çekiliş no: 47042
05.08.2026 - 20:02
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20""")
    if raw.strip():
        row = parse_draw_block(raw)
        if not row:
            st.error("Çekiliş okunamadı. 20 farklı sayı, çekiliş no, tarih ve saat gerekli.")
        elif row[0] in set(df.Cekilis_No.astype(int)):
            st.warning("Bu çekiliş zaten mevcut.")
        else:
            new_row_df = pd.DataFrame([row], columns=COLS)
            st.session_state.extra_df = merge_data(st.session_state.extra_df, new_row_df)
            st.success("Çekiliş bu oturuma eklendi. Kalıcılaştırmak için Dışa Aktar sekmesinden veri.txt indir.")
            st.rerun()

with tabs[14]:
    st.download_button(
        "Güncel veri.txt indir",
        data=to_text(df).encode("utf-8"),
        file_name="veri.txt",
        mime="text/plain",
        type="primary",
    )
    st.download_button(
        "Güncel CSV indir",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="hizli_on_guncel.csv",
        mime="text/csv",
    )
    st.download_button(
        "Güncel Excel indir",
        data=to_excel_bytes(df),
        file_name="hizli_on_guncel.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.caption(
    "Analizler istatistikseldir; kesin sonuç veya kazanç garantisi vermez. "
    "Yeni dosyalar uygulamaya yüklenebilir ve mevcut havuzla birleştirilir. "
    "Streamlit Community Cloud dosya sistemine kalıcı yazma yapmadığı için, "
    "güncellenmiş veri.txt dosyasını indirip GitHub'daki veri.txt üzerine yüklemek gerekir."
)
