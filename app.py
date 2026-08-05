import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On Analiz Motoru", layout="wide")

DATA_FILE = Path(__file__).parent / "veri.txt"
COLS = ["Cekilis_No", "Tarih", "Saat"] + [f"Sayi_{i}" for i in range(1, 21)]


def parse_line(line):
    """
    Desteklenen biçimler:
    46439;03.08.2026;00:02;7,9,15,...,78
    46439,03.08.2026,00:02,7,9,15,...,78
    Çekiliş no: 46439 (00:02) -> 7, 9, ... 78
    """
    raw = str(line).strip()
    if not raw:
        return None

    # Standart CSV/TXT biçimleri
    std = re.match(
        r"^\s*(\d+)\s*[;,]\s*(\d{2}[./]\d{2}[./]\d{4})\s*[;,]\s*(\d{2}:\d{2})\s*[;,]\s*(.*)$",
        raw,
    )
    if std:
        no = int(std.group(1))
        tarih = std.group(2).replace("/", ".")
        saat = std.group(3)
        number_text = std.group(4)
    else:
        # Ham çekiliş biçimi
        alt = re.match(
            r"^\s*Çekiliş\s*no\s*:\s*(\d+)\s*\((\d{2}:\d{2})\)\s*->\s*(.*)$",
            raw,
            re.I,
        )
        if not alt:
            return None
        no = int(alt.group(1))
        tarih = ""
        saat = alt.group(2)
        number_text = alt.group(3)

    # Sayı ayraçları: virgül, noktalı virgül, tire veya boşluk
    nums = [
        int(x)
        for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", number_text)
    ]

    if len(nums) != 20 or len(set(nums)) != 20:
        return None

    return [no, tarih, saat] + sorted(nums)


@st.cache_data(show_spinner=False)
def load_data():
    valid, invalid = [], []

    if not DATA_FILE.exists():
        return pd.DataFrame(columns=COLS), ["veri.txt bulunamadı"]

    for line_no, line in enumerate(
        DATA_FILE.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
    ):
        row = parse_line(line)
        if row:
            valid.append(row)
        elif line.strip():
            invalid.append(f"Satır {line_no}: {line[:160]}")

    df = pd.DataFrame(valid, columns=COLS)

    if not df.empty:
        df = (
            df.drop_duplicates("Cekilis_No", keep="last")
            .sort_values("Cekilis_No")
            .reset_index(drop=True)
        )

    return df, invalid


def num_cols(df):
    return [c for c in df.columns if c.startswith("Sayi_")]


def row_sets(df):
    return [set(map(int, row)) for row in df[num_cols(df)].to_numpy()]


def frequency(df):
    counter = Counter(map(int, df[num_cols(df)].to_numpy().ravel()))
    return pd.DataFrame(
        [{"Sayı": n, "Frekans": counter.get(n, 0)} for n in range(1, 81)]
    )


def gaps(df):
    sets = row_sets(df)
    output = []

    for n in range(1, 81):
        gap = len(sets)
        for index, draw_set in enumerate(reversed(sets)):
            if n in draw_set:
                gap = index
                break
        output.append({"Sayı": n, "Dinlenme": gap})

    return pd.DataFrame(output)


def combo_table(df, size, top_n):
    counter = Counter()

    for draw_set in row_sets(df):
        counter.update(combinations(sorted(draw_set), size))

    return pd.DataFrame(
        [
            {"Grup": " - ".join(map(str, group)), "Frekans": count}
            for group, count in counter.most_common(top_n)
        ]
    )


def consecutive_blocks(nums):
    nums = sorted(nums)

    if not nums:
        return []

    blocks, current = [], [nums[0]]

    for n in nums[1:]:
        if n == current[-1] + 1:
            current.append(n)
        else:
            if len(current) >= 2:
                blocks.append(current)
            current = [n]

    if len(current) >= 2:
        blocks.append(current)

    return blocks


def repeat_table(df):
    sets = row_sets(df)
    output = []

    for i in range(1, len(sets)):
        common = sorted(sets[i] & sets[i - 1])
        output.append(
            {
                "Çekiliş": int(df.iloc[i].Cekilis_No),
                "Tekrar sayısı": len(common),
                "Tekrar edenler": " - ".join(map(str, common)),
            }
        )

    return pd.DataFrame(output).sort_values("Çekiliş", ascending=False)


def block_table(df, last_n):
    previous_blocks, output = [], []

    for _, row in df.tail(last_n).iterrows():
        blocks = consecutive_blocks([int(row[c]) for c in num_cols(df)])
        shifts = []

        for block in blocks:
            for previous in previous_blocks:
                if len(block) == len(previous):
                    delta = block[0] - previous[0]
                    if delta in (-2, -1, 1, 2):
                        shifts.append(
                            f"{'-'.join(map(str, previous))} → "
                            f"{'-'.join(map(str, block))} ({delta:+d})"
                        )

        output.append(
            {
                "Çekiliş": int(row.Cekilis_No),
                "Bloklar": ", ".join(
                    "-".join(map(str, block)) for block in blocks
                )
                or "Yok",
                "Kayma": "; ".join(shifts) or "Yok",
            }
        )
        previous_blocks = blocks

    return pd.DataFrame(output).sort_values("Çekiliş", ascending=False)


def data_quality(df, invalid):
    missing_draws = []

    if not df.empty:
        available = set(df.Cekilis_No.astype(int))
        missing_draws = [
            n
            for n in range(int(df.Cekilis_No.min()), int(df.Cekilis_No.max()) + 1)
            if n not in available
        ]

    return {
        "gecerli": len(df),
        "bozuk": len(invalid),
        "eksik_no": missing_draws,
        "mukerrer_sonrasi": int(df.Cekilis_No.duplicated().sum()) if not df.empty else 0,
    }


def generate_coupon(df, size, strategy, window):
    freq = frequency(df.tail(window)).set_index("Sayı").Frekans
    gap = gaps(df).set_index("Sayı").Dinlenme
    nums = np.arange(1, 81)

    if strategy == "Sıcak ağırlıklı":
        weights = np.array([(freq.get(n, 0) + 1) ** 2 for n in nums], float)
    elif strategy == "Dinlenmiş dönüş":
        weights = np.array([(gap.get(n, 0) + 1) ** 1.6 for n in nums], float)
    else:
        freq_values = np.array([freq.get(n, 0) for n in nums], float)
        gap_values = np.array([gap.get(n, 0) for n in nums], float)
        weights = (
            0.6 * freq_values / max(freq_values.max(), 1)
            + 0.4 * gap_values / max(gap_values.max(), 1)
            + 0.05
        )

    weights /= weights.sum()

    return sorted(
        np.random.choice(nums, size=size, replace=False, p=weights).tolist()
    )


def to_text(df):
    lines = []

    for _, row in df.sort_values("Cekilis_No").iterrows():
        values = [
            str(int(row.Cekilis_No)),
            str(row.Tarih),
            str(row.Saat),
        ] + [
            str(int(row[f"Sayi_{i}"])) for i in range(1, 21)
        ]
        lines.append(";".join(values[:3]) + ";" + ",".join(values[3:]))

    return "\n".join(lines) + "\n"


def parse_pasted_draw(text):
    draw_no = re.search(r"Çekiliş\s*no\s*:\s*(\d+)", text, re.I)
    date_time = re.search(
        r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})", text
    )
    nums = [
        int(x)
        for x in re.findall(r"(?m)^\s*(\d{1,2})\s*$", text)
    ]

    if not draw_no or not date_time:
        return None, "Çekiliş numarası, tarih veya saat bulunamadı."

    if len(nums) != 20:
        return None, f"20 sayı bekleniyordu, {len(nums)} sayı bulundu."

    if len(set(nums)) != 20 or any(n < 1 or n > 80 for n in nums):
        return None, "Sayılar 1-80 arasında ve birbirinden farklı olmalı."

    return (
        [
            int(draw_no.group(1)),
            date_time.group(1),
            date_time.group(2),
        ]
        + sorted(nums),
        None,
    )


st.title("🎯 Hızlı On Gelişmiş Analiz ve İstatistik Motoru")
st.caption(
    "Birlikte çıkma, sıcak/soğuk döngüsü, dinlenme, tekrar, "
    "blok kayması, veri kontrolü ve akıllı kupon"
)

df, invalid = load_data()

if df.empty:
    st.error("Geçerli çekiliş bulunamadı.")
    if invalid:
        st.code("\n".join(invalid[:50]), language="text")
    st.stop()

latest = df.iloc[-1]
quality = data_quality(df, invalid)

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Toplam çekiliş", f"{len(df):,}")
metric_2.metric("Son çekiliş", int(latest.Cekilis_No))
metric_3.metric("Son tarih / saat", f"{latest.Tarih} {latest.Saat}")
metric_4.metric("Eksik çekiliş no", len(quality["eksik_no"]))

with st.sidebar:
    st.header("⚙️ Ayarlar")
    window = st.slider(
        "Son kaç çekiliş?",
        50,
        max(50, len(df)),
        min(500, len(df)),
        50,
    )

    if invalid:
        st.warning(f"{len(invalid)} bozuk/eksik satır atlandı.")

analysis_df = df.tail(window)

tabs = st.tabs(
    [
        "✅ Veri Kontrol",
        "📈 Frekans",
        "🔗 2-3-4-5’li",
        "🔥 Sıcak/Soğuk",
        "⏳ Dinlenme",
        "🔄 Tekrar & Blok",
        "🎯 Akıllı Kupon",
        "➕ Yeni Çekiliş",
    ]
)

with tabs[0]:
    col_1, col_2, col_3 = st.columns(3)
    col_1.metric("Geçerli satır", quality["gecerli"])
    col_2.metric("Bozuk satır", quality["bozuk"])
    col_3.metric("Eksik çekiliş no", len(quality["eksik_no"]))

    if quality["eksik_no"]:
        st.warning(
            "Eksik çekiliş numaraları: "
            + ", ".join(map(str, quality["eksik_no"][:300]))
        )
    else:
        st.success("Çekiliş numaraları kesintisiz.")

    if invalid:
        with st.expander("Atlanan bozuk satırlar"):
            st.code("\n".join(invalid[:300]), language="text")

with tabs[1]:
    freq = frequency(analysis_df).sort_values(
        ["Frekans", "Sayı"], ascending=[False, True]
    )
    st.dataframe(freq, use_container_width=True, hide_index=True)
    st.bar_chart(freq.sort_values("Sayı").set_index("Sayı").Frekans)

with tabs[2]:
    sub_tabs = st.tabs(["2’li", "3’lü", "4’lü", "5’li"])

    for tab, size in zip(sub_tabs, [2, 3, 4, 5]):
        with tab:
            top_n = st.slider(
                f"İlk kaç {size}’li grup?",
                10,
                100,
                30,
                key=f"top{size}",
            )
            st.dataframe(
                combo_table(analysis_df, size, top_n),
                use_container_width=True,
                hide_index=True,
            )

with tabs[3]:
    freq = frequency(analysis_df)
    gap = gaps(df)
    merged = freq.merge(gap, on="Sayı")

    left, right = st.columns(2)

    with left:
        st.markdown("### 🔥 Sıcak sayılar")
        st.dataframe(
            merged.sort_values(
                ["Frekans", "Dinlenme"], ascending=[False, True]
            ).head(20),
            use_container_width=True,
            hide_index=True,
        )

    with right:
        st.markdown("### ❄️ Soğuk / dinlenmiş")
        st.dataframe(
            merged.sort_values(
                ["Dinlenme", "Frekans"], ascending=[False, True]
            ).head(20),
            use_container_width=True,
            hide_index=True,
        )

with tabs[4]:
    st.dataframe(
        gaps(df).sort_values(
            ["Dinlenme", "Sayı"], ascending=[False, True]
        ),
        use_container_width=True,
        hide_index=True,
    )

with tabs[5]:
    st.subheader("Çekilişler arası tekrar")
    st.dataframe(
        repeat_table(analysis_df).head(100),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Ardışık bloklar ve sağa/sola kayma")
    st.dataframe(
        block_table(df, min(window, 300)),
        use_container_width=True,
        hide_index=True,
    )

with tabs[6]:
    col_1, col_2, col_3 = st.columns(3)

    with col_1:
        size = st.selectbox(
            "Kolon büyüklüğü", [3, 4, 5, 6, 7, 8, 10], index=4
        )

    with col_2:
        count = st.slider("Kolon sayısı", 1, 10, 4)

    with col_3:
        strategy = st.selectbox(
            "Strateji",
            ["Dengeli", "Sıcak ağırlıklı", "Dinlenmiş dönüş"],
        )

    if st.button("🎯 Kolonları üret", type="primary"):
        made = set()
        safety = 0

        while len(made) < count and safety < 500:
            made.add(
                tuple(generate_coupon(df, size, strategy, window))
            )
            safety += 1

        for index, coupon in enumerate(made, 1):
            st.success(
                f"Kolon {index}: " + " - ".join(map(str, coupon))
            )

        st.caption(
            "İstatistiksel örneklemedir; kesin sonuç garantisi vermez."
        )

with tabs[7]:
    st.subheader("Yeni çekilişi olduğu gibi yapıştır")

    raw = st.text_area(
        "Çekiliş metni",
        height=260,
        placeholder="""Çekiliş no: 46729
04.08.2026 - 12:02
2
15
18
20
38
40
44
49
51
52
54
57
58
59
63
64
65
76
78
80""",
    )

    if raw.strip():
        row, error = parse_pasted_draw(raw)

        if error:
            st.error(error)
        else:
            st.code(
                ";".join(map(str, row[:3]))
                + ";"
                + ",".join(map(str, row[3:])),
                language="text",
            )

            if row[0] in set(df.Cekilis_No.astype(int)):
                st.warning("Bu çekiliş zaten kayıtlı.")
            else:
                new_df = pd.concat(
                    [df, pd.DataFrame([row], columns=COLS)],
                    ignore_index=True,
                ).sort_values("Cekilis_No")

                st.success(
                    "Yeni çekiliş eklendi. Güncel veri.txt hazır."
                )

                st.download_button(
                    "⬇️ Güncellenmiş veri.txt indir",
                    to_text(new_df).encode("utf-8"),
                    file_name="veri.txt",
                    mime="text/plain",
                    type="primary",
                )

                previous = set(
                    map(int, df.iloc[-1][num_cols(df)].tolist())
                )
                current = set(row[3:])
                common = sorted(previous & current)
                blocks = consecutive_blocks(row[3:])

                st.write(
                    f"Önceki çekilişten tekrar: **{len(common)} sayı**"
                )
                st.write(
                    "Tekrar edenler:",
                    " - ".join(map(str, common)) or "Yok",
                )
                st.write(
                    "Ardışık bloklar:",
                    ", ".join(
                        "-".join(map(str, block))
                        for block in blocks
                    )
                    or "Yok",
                )
                st.info(
                    "İndirdiğin veri.txt dosyasını GitHub’daki veri.txt "
                    "üzerine yüklediğinde kayıt kalıcı olur."
                )
