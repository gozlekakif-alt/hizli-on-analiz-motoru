# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import re
from pathlib import Path

st.set_page_config(page_title="Hızlı On — 20 Sayının Geçmiş Mikroskobu", layout="wide")
st.title("🔬 Hızlı On — Her Çekilişin 20 Sayısının Geçmişi")
st.caption(
    "Kupon üretmez. Aday havuzu üretmez. Ortalama vermez. "
    "Her çekilişi kendi anında inceler ve sadece o çekilişten ÖNCE bilinen geçmişi kullanır."
)

DATA_FILE = Path("veri.txt")


def parse_semicolon(text):
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("=", "#")):
            continue
        m = re.match(r"^\s*(\d+)\s*;\s*([^;]+?)\s*;\s*(.+?)\s*$", s)
        if not m:
            continue
        try:
            draw_id = int(m.group(1))
            dt = pd.to_datetime(m.group(2).strip(), dayfirst=True)
            nums = [int(x) for x in re.findall(r"\d+", m.group(3))]
            nums = list(dict.fromkeys(nums))
            if len(nums) == 20 and min(nums) >= 1 and max(nums) <= 80:
                rows.append((draw_id, dt, tuple(sorted(nums))))
        except Exception:
            pass
    return rows


def parse_blocks(text):
    pat = re.compile(
        r"Çekiliş\s*no\s*:\s*#?\s*(\d+)\s*\n"
        r"\s*(\d{2}\.\d{2}\.\d{4})\s*[-–—]?\s*(\d{2}:\d{2})",
        re.I,
    )
    ms = list(pat.finditer(text))
    rows = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        block = text[m.end() : end]
        nums = []
        for ln in block.splitlines():
            s = ln.strip()
            if re.fullmatch(r"\d{1,2}", s):
                n = int(s)
                if 1 <= n <= 80:
                    nums.append(n)
                if len(nums) == 20:
                    break
        if len(nums) == 20:
            dt = pd.to_datetime(f"{m.group(2)} {m.group(3)}", dayfirst=True)
            rows.append((int(m.group(1)), dt, tuple(sorted(nums))))
    return rows


@st.cache_data(show_spinner=False)
def parse_text(text):
    rows = parse_semicolon(text)
    if not rows:
        rows = parse_blocks(text)
    df = pd.DataFrame(rows, columns=["draw_id", "dt", "numbers"])
    if df.empty:
        return df
    return (
        df.sort_values(["dt", "draw_id"])
        .drop_duplicates("draw_id", keep="last")
        .reset_index(drop=True)
    )


def read_source(uploaded):
    if uploaded is not None:
        return uploaded.getvalue().decode("utf-8-sig", errors="ignore"), uploaded.name
    if DATA_FILE.exists():
        return DATA_FILE.read_text(encoding="utf-8-sig", errors="ignore"), "repo/veri.txt"
    return None, None


def cmh(count6):
    if count6 == 0:
        return "C"
    if count6 <= 2:
        return "M"
    return "H"


def state_name(x):
    return {"C": "SOĞUK", "M": "ORTA", "H": "SICAK"}[x]


def count_in_slice(mat, idx, n0, width):
    if idx <= 0:
        return 0
    a = max(0, idx - width)
    return int(mat[a:idx, n0].sum())


def previous_hit_indices(mat, idx, n0, limit=8):
    if idx <= 0:
        return []
    inds = np.flatnonzero(mat[:idx, n0])
    if len(inds) == 0:
        return []
    return inds[-limit:][::-1].tolist()


def identity_for_number(df, mat, idx, n):
    n0 = n - 1
    h1 = count_in_slice(mat, idx, n0, 1)
    h3 = count_in_slice(mat, idx, n0, 3)
    h6 = count_in_slice(mat, idx, n0, 6)
    h12 = count_in_slice(mat, idx, n0, 12)
    h24 = count_in_slice(mat, idx, n0, 24)
    h48 = count_in_slice(mat, idx, n0, 48)

    a = max(0, idx - 12)
    b = max(0, idx - 6)
    prev6 = int(mat[a:b, n0].sum()) if b > a else 0

    cur_state = cmh(h6)
    prev_state = cmh(prev6)
    transition = f"{prev_state}→{cur_state}"

    hit_idx = previous_hit_indices(mat, idx, n0, limit=8)
    if hit_idx:
        last_i = hit_idx[0]
        gap = idx - last_i - 1
        last_seen = pd.Timestamp(df.iloc[last_i]["dt"])
        last_draw = int(df.iloc[last_i]["draw_id"])
    else:
        gap = None
        last_seen = pd.NaT
        last_draw = None

    target_day = df.iloc[idx]["dt"].date()
    day_start = idx
    while day_start > 0 and df.iloc[day_start - 1]["dt"].date() == target_day:
        day_start -= 1
    day_count = int(mat[day_start:idx, n0].sum())

    a12 = max(0, idx - 12)
    bits = "".join("1" if x else "0" for x in mat[a12:idx, n0].tolist())
    bits = bits.rjust(12, "·")

    prev_hits = []
    for j in hit_idx[:5]:
        r = df.iloc[j]
        prev_hits.append(f"#{int(r.draw_id)} {pd.Timestamp(r.dt).strftime('%H:%M')}")
    prev_hits_txt = " | ".join(prev_hits) if prev_hits else "-"

    return {
        "Sayı": n,
        "Kimlik": state_name(cur_state),
        "Geçiş": transition,
        "Son el": "ÇIKTI" if h1 else "YOK",
        "Gap": "İLK" if gap is None else gap,
        "H3": h3,
        "H6": h6,
        "Önceki6": prev6,
        "H12": h12,
        "H24": h24,
        "H48": h48,
        "Gün içi önce": day_count,
        "Son görülme": "-" if pd.isna(last_seen) else last_seen.strftime("%d.%m %H:%M"),
        "Son çekiliş": "-" if last_draw is None else f"#{last_draw}",
        "Son12 izi": bits,
        "Önceki 5 çıkışı": prev_hits_txt,
    }


@st.cache_data(show_spinner=False)
def build_matrix(records):
    mat = np.zeros((len(records), 80), dtype=np.uint8)
    for i, rec in enumerate(records):
        for n in rec["numbers"]:
            mat[i, n - 1] = 1
    return mat


def draw_report(df, mat, idx):
    row = df.iloc[idx]
    actual = list(row["numbers"])
    detail = pd.DataFrame([identity_for_number(df, mat, idx, n) for n in actual])
    kimlik = detail["Kimlik"].value_counts().reindex(["SOĞUK", "ORTA", "SICAK"], fill_value=0)
    trans = detail["Geçiş"].value_counts()
    h6_dist = detail["H6"].value_counts().sort_index()
    return detail, kimlik, trans, h6_dist


def day_text_report(df, mat, date_value):
    idxs = df.index[df["dt"].dt.date == date_value].tolist()
    out = []
    for idx in idxs:
        r = df.iloc[idx]
        detail, kimlik, trans, _ = draw_report(df, mat, idx)
        out.append("=" * 118)
        out.append(f"#{int(r.draw_id)} | {pd.Timestamp(r.dt).strftime('%d.%m.%Y %H:%M')}")
        out.append("GERÇEK20: " + ",".join(map(str, r.numbers)))
        out.append("BU ÇEKİLİŞİN KİMLİĞİ: " + " | ".join(f"{k}={int(v)}" for k, v in kimlik.items()))
        out.append("GEÇİŞLER: " + " | ".join(f"{k}={int(v)}" for k, v in trans.items()))
        out.append("-" * 118)
        out.append(detail.to_csv(index=False))
    return "\n".join(out)


uploaded = st.sidebar.file_uploader("İstersen veri TXT yükle", type=["txt"])
raw, source_name = read_source(uploaded)

if raw is None:
    st.error("veri.txt bulunamadı. GitHub deposunda app dosyasıyla aynı klasöre veri.txt koy veya soldan TXT yükle.")
    st.stop()

df = parse_text(raw)
if df.empty:
    st.error("Veriden geçerli çekiliş okunamadı.")
    st.stop()

mat = build_matrix(df.to_dict("records"))

st.sidebar.success(f"Kaynak: {source_name}")
st.sidebar.caption(f"Çekiliş: {len(df):,} | {df.dt.min():%d.%m.%Y %H:%M} → {df.dt.max():%d.%m.%Y %H:%M}")

dates = sorted(df["dt"].dt.date.unique())
sel_date = st.sidebar.selectbox(
    "Gün",
    dates,
    index=len(dates) - 1,
    format_func=lambda d: pd.Timestamp(d).strftime("%d.%m.%Y"),
)

day_df = df[df["dt"].dt.date == sel_date].sort_values("dt")
draw_options = day_df.index.tolist()
sel_idx = st.sidebar.selectbox(
    "Çekiliş",
    draw_options,
    index=0,
    format_func=lambda i: f"#{int(df.loc[i, 'draw_id'])} — {df.loc[i, 'dt']:%H:%M}",
)

detail, kimlik_counts, transition_counts, h6dist = draw_report(df, mat, sel_idx)
target = df.iloc[sel_idx]

st.subheader(f"#{int(target.draw_id)} — {target.dt:%d.%m.%Y %H:%M}")
st.write("**Gerçek 20:** " + " – ".join(map(str, target.numbers)))

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Soğuk", int(kimlik_counts["SOĞUK"]))
with c2:
    st.metric("Orta", int(kimlik_counts["ORTA"]))
with c3:
    st.metric("Sıcak", int(kimlik_counts["SICAK"]))

st.markdown("#### Bu çekilişin 20 sayısının geçmiş pasaportu")
st.dataframe(detail, use_container_width=True, hide_index=True, height=720)

st.markdown("#### Bu çekilişe özel kimlik geçişleri")
tr_df = pd.DataFrame({
    "Geçiş": transition_counts.index,
    "Bu çekilişte çıkan sayı adedi": transition_counts.values,
})
st.dataframe(tr_df, use_container_width=True, hide_index=True)

st.markdown("#### Bu çekilişe özel H6 derecesi")
h6_df = pd.DataFrame({
    "H6'da kaç kez görünmüştü": h6dist.index,
    "Bu çekilişte çıkan sayı adedi": h6dist.values,
})
st.dataframe(h6_df, use_container_width=True, hide_index=True)

st.info(
    "Bu ekranda hiçbir günlük/saatlik ortalama yoktur. "
    "Her satır yalnız seçili çekilişin 20 gerçek sayısının, hedef açılmadan önceki geçmişidir."
)

with st.expander("Sütunların anlamı"):
    st.markdown(
        """
- **Kimlik:** Hedef çekilişten önceki son 6 çekilişte sayı 0 kez görünmüşse SOĞUK, 1–2 kez ORTA, 3+ kez SICAK.
- **Geçiş:** Bir önceki 6'lı pencerenin kimliğinden son 6'lı pencerenin kimliğine geçiş. Örn. `C→M`.
- **Gap:** Sayının son görülmesinden sonra kaç çekiliş geçti.
- **H3/H6/H12/H24/H48:** Hedef açılmadan önceki ilgili pencere içindeki görünme sayısı.
- **Gün içi önce:** O gün 00:02'den hedef çekilişten hemen öncesine kadar kaç kez göründü.
- **Son12 izi:** Son 12 çekilişteki 0/1 görünme izi. Sağ taraf hedefe en yakın geçmiş.
- **Önceki 5 çıkışı:** Sayının hedef öncesindeki en son beş görülme yeri.
        """
    )

st.markdown("### Günün tamamını dışa aktar")
st.caption(
    "Seçili günün 00:02'den son çekilişe kadar HER çekilişi ayrı ayrı yazar. "
    "Gün/saat ortalaması eklemez."
)
if st.button("Bu günün ayrıntılı raporunu hazırla", use_container_width=True):
    txt = day_text_report(df, mat, sel_date)
    st.download_button(
        "⬇️ Günün tüm çekiliş geçmiş raporunu indir",
        data=txt.encode("utf-8-sig"),
        file_name=f"HIZLI_ON_{pd.Timestamp(sel_date):%d_%m_%Y}_20_GECMIS_MIKROSKOBU.txt",
        mime="text/plain",
        use_container_width=True,
    )
