import base64
from datetime import datetime, timedelta, timedelta
import io
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import requests
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import streamlit as st

st.set_page_config(
    page_title="Hızlı On Ultimate AI Studio V18.5.8",
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
    no = re.search(r"(?mi)^\s*Çekiliş\s*no\s*:\s*(\d+)\s*$", text)
    dt = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})", text)
    nums = [int(x) for x in re.findall(r"(?m)^\s*(\d{1,2})\s*$", text)]

    if not no or not dt or len(nums) != 20:
        return None
    if len(set(nums)) != 20 or any(n < 1 or n > 80 for n in nums):
        return None

    return [int(no.group(1)), dt.group(1), dt.group(2)] + sorted(nums)



def extract_exact_twenty_numbers(text: str):
    """
    Satır, boşluk, virgül veya tire ile girilmiş 20 oyun sayısını okur.
    Çekiliş no, tarih ve saat parçalarını oyun sayısı olarak saymaz.
    """
    raw = str(text).strip()
    if not raw:
        return None

    cleaned = raw

    # Tam başlık satırlarını kaldır.
    cleaned = re.sub(
        r"(?mi)^\s*(?:#+\s*)?Çekiliş\s*no\s*:\s*\d+\s*$",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^\s*\d{2}[./]\d{2}[./]\d{4}\s*-\s*\d{2}:\d{2}\s*$",
        " ",
        cleaned,
    )

    # Başlık tek satır içindeyse metadata parçalarını kaldır.
    cleaned = re.sub(
        r"(?i)\bÇekiliş\s*no\s*:\s*\d+\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"\b\d{2}[./]\d{2}[./]\d{4}\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"\b\d{2}:\d{2}\b",
        " ",
        cleaned,
    )

    numbers = [
        int(value)
        for value in re.findall(
            r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",
            cleaned,
        )
    ]

    if len(numbers) != 20:
        return None
    if len(set(numbers)) != 20:
        return None
    return sorted(numbers)

def next_draw_datetime_v18(last_dt):
    """
    Merkezi Hızlı On takvimi.
    Normal akış 5 dakikadır.
    01:02'den sonraki gerçek çekiliş ertesi gün 07:02'dir.
    """
    if last_dt.hour == 1 and last_dt.minute == 2:
        return (last_dt + timedelta(days=1)).replace(
            hour=7, minute=2, second=0, microsecond=0
        )

    candidate = last_dt + timedelta(minutes=5)

    if (
        (candidate.hour == 1 and candidate.minute > 2)
        or (2 <= candidate.hour < 7)
    ):
        return (last_dt + timedelta(days=1)).replace(
            hour=7, minute=2, second=0, microsecond=0
        )

    return candidate


def next_draw_defaults(df):
    """
    Uygulamanın tamamında kullanılacak tek sonraki çekiliş hesaplayıcısı.
    """
    if df is None or df.empty:
        return 1, datetime.now().strftime("%d.%m.%Y"), "07:02"

    latest = df.sort_values("Cekilis_No").iloc[-1]
    draw_no = int(latest.Cekilis_No) + 1

    try:
        last_dt = datetime.strptime(
            f"{latest.Tarih} {latest.Saat}",
            "%d.%m.%Y %H:%M",
        )
        next_dt = next_draw_datetime_v18(last_dt)
        return (
            draw_no,
            next_dt.strftime("%d.%m.%Y"),
            next_dt.strftime("%H:%M"),
        )
    except Exception:
        return draw_no, str(latest.Tarih), str(latest.Saat)


def repair_calendar_sequence_v18(df):
    """
    Yalnızca çekiliş numaraları ardışıkken ve kayıt kapalı saat aralığına
    düşmüşse takvim hatasını onarır.
    Örnek: 01:02 sonrası yanlış 01:07 -> ertesi gün 07:02.
    """
    if df is None or df.empty:
        return df

    work = df.sort_values("Cekilis_No").reset_index(drop=True).copy()

    for i in range(1, len(work)):
        prev_no = int(work.iloc[i - 1]["Cekilis_No"])
        cur_no = int(work.iloc[i]["Cekilis_No"])
        if cur_no != prev_no + 1:
            continue

        try:
            prev_dt = datetime.strptime(
                f"{work.iloc[i - 1]['Tarih']} {work.iloc[i - 1]['Saat']}",
                "%d.%m.%Y %H:%M",
            )
            cur_dt = datetime.strptime(
                f"{work.iloc[i]['Tarih']} {work.iloc[i]['Saat']}",
                "%d.%m.%Y %H:%M",
            )
        except Exception:
            continue

        invalid_closed_time = (
            (cur_dt.hour == 1 and cur_dt.minute > 2)
            or (2 <= cur_dt.hour < 7)
        )

        if invalid_closed_time:
            expected = next_draw_datetime_v18(prev_dt)
            work.at[i, "Tarih"] = expected.strftime("%d.%m.%Y")
            work.at[i, "Saat"] = expected.strftime("%H:%M")

    return work


def draw_calendar_status_v18(df):
    if df is None or df.empty:
        return {}

    latest = df.sort_values("Cekilis_No").iloc[-1]
    next_no, next_date, next_time = next_draw_defaults(df)

    return {
        "Son Çekiliş": int(latest.Cekilis_No),
        "Son Tarih": str(latest.Tarih),
        "Son Saat": str(latest.Saat),
        "Sonraki Çekiliş": int(next_no),
        "Sonraki Tarih": str(next_date),
        "Sonraki Saat": str(next_time),
    }



def canonical_draw_no_v1852(date_text: str, time_text: str):
    """07.08.2026 10:02 = #47356 resmî ankrajına göre 07.08.2026 ve sonrası için çekiliş no üretir."""
    try:
        d = datetime.strptime(str(date_text), "%d.%m.%Y").date()
        hh, mm = map(int, str(time_text)[:5].split(":"))
    except Exception:
        return None

    anchor_date = datetime.strptime("07.08.2026", "%d.%m.%Y").date()
    if d < anchor_date:
        return None

    minutes = hh * 60 + mm
    if 2 <= minutes <= 62 and (minutes - 2) % 5 == 0:
        day_index = (minutes - 2) // 5
    elif 7 * 60 + 2 <= minutes <= 23 * 60 + 57 and (minutes - (7 * 60 + 2)) % 5 == 0:
        day_index = 13 + (minutes - (7 * 60 + 2)) // 5
    else:
        return None

    anchor_day_index = 13 + ((10 * 60 + 2) - (7 * 60 + 2)) // 5
    first_draw_anchor_day = 47356 - anchor_day_index
    days = (d - anchor_date).days
    return int(first_draw_anchor_day + days * 217 + day_index)


def apply_verified_draw_numbers_v1852(df: pd.DataFrame):
    """Yalnızca çekiliş numarasını düzeltir; tarih, saat ve 20 sayıya dokunmaz."""
    if df is None or df.empty:
        return df, 0

    out = df.copy()
    changed = 0
    for idx, row in out.iterrows():
        expected = canonical_draw_no_v1852(row["Tarih"], row["Saat"])
        if expected is None:
            continue
        current = int(row["Cekilis_No"])
        if current != expected:
            out.at[idx, "Cekilis_No"] = expected
            changed += 1

    return clean_df(out), changed


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



def normalize_draw_number(draw_no, date_value):
    """
    Tarihin gün hanesinin yanlışlıkla çekiliş numarasının sonuna
    eklenmesi gibi kayıtları onarır.
    Örnek: 4706205 + 05.08.2026 -> 47062
    """
    try:
        draw_no = int(draw_no)
    except (TypeError, ValueError):
        return draw_no

    date_text = str(date_value or "").strip()
    day_match = re.match(r"^(\d{2})[./-]\d{2}[./-]\d{4}$", date_text)
    day = day_match.group(1) if day_match else None
    draw_text = str(abs(draw_no))

    # Normal Hızlı On çekiliş numaraları bu veri setinde 5 hanedir.
    # 7 haneli ve tarih günüyle biten kayıtları güvenli biçimde düzelt.
    if day and len(draw_text) >= 7 and draw_text.endswith(day):
        candidate = draw_text[:-2]
        if candidate.isdigit() and 10000 <= int(candidate) <= 999999:
            return int(candidate)

    return draw_no


def repair_draw_numbers(df: pd.DataFrame):
    """Bozuk çekiliş numaralarını onarır ve kaç satırın düzeldiğini döndürür."""
    if df is None or df.empty or "Cekilis_No" not in df.columns:
        return df, 0

    out = df.copy()
    repaired = 0
    fixed_values = []

    for _, row in out.iterrows():
        old_value = row.get("Cekilis_No")
        new_value = normalize_draw_number(old_value, row.get("Tarih"))
        fixed_values.append(new_value)
        try:
            if int(new_value) != int(old_value):
                repaired += 1
        except (TypeError, ValueError):
            pass

    out["Cekilis_No"] = fixed_values
    return out, repaired

def clean_df(df: pd.DataFrame):
    if df.empty:
        return pd.DataFrame(columns=COLS)

    out = df.copy()
    out, _ = repair_draw_numbers(out)

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



def github_settings():
    try:
        token = st.secrets["github"]["token"]
        owner = st.secrets["github"].get("owner", "gozlekakif-alt")
        repo = st.secrets["github"].get("repo", "hizli-on-analiz-motoru")
        branch = st.secrets["github"].get("branch", "main")
        path = st.secrets["github"].get("data_path", "veri.txt")
        admin_pin = str(st.secrets["github"].get("admin_pin", ""))
        return {
            "token": token,
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "path": path,
            "admin_pin": admin_pin,
        }, None
    except Exception:
        return None, (
            "GitHub kalıcı kayıt ayarları yapılmamış. "
            "Streamlit Secrets bölümüne github bilgileri eklenmeli."
        )


def github_headers(token):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_github_file(settings):
    url = (
        f"https://api.github.com/repos/{settings['owner']}/"
        f"{settings['repo']}/contents/{settings['path']}"
    )
    response = requests.get(
        url,
        headers=github_headers(settings["token"]),
        params={"ref": settings["branch"]},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub veri dosyası okunamadı: "
            f"{response.status_code} {response.text[:300]}"
        )
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode(
        "utf-8", errors="ignore"
    )
    return content, payload["sha"]


def update_github_file(settings, new_text, commit_message):
    _, sha = get_github_file(settings)
    url = (
        f"https://api.github.com/repos/{settings['owner']}/"
        f"{settings['repo']}/contents/{settings['path']}"
    )
    payload = {
        "message": commit_message,
        "content": base64.b64encode(
            new_text.encode("utf-8")
        ).decode("ascii"),
        "sha": sha,
        "branch": settings["branch"],
    }
    response = requests.put(
        url,
        headers=github_headers(settings["token"]),
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"GitHub kaydı başarısız: "
            f"{response.status_code} {response.text[:500]}"
        )
    return response.json()


def persistent_save_panel(df_to_save, key_prefix):
    """V18.5.8 — çekiliş/veri havuzu kalıcı kaydı PIN istemeden tek dokunuşla yapılır."""
    settings, settings_error = github_settings()

    if settings_error:
        st.warning(settings_error)
        return

    st.success(
        "GitHub kalıcı kayıt bağlantısı hazır. "
        "Tek dokunuşla ana veri.txt dosyası güncellenir."
    )

    if st.button(
        "✅ Çekilişi kalıcı kaydet ve güncelle",
        type="primary",
        key=f"{key_prefix}_save",
    ):
        try:
            with st.spinner("GitHub veri.txt güncelleniyor..."):
                update_github_file(
                    settings,
                    to_text(df_to_save),
                    (
                        f"Veri havuzu güncellendi: "
                        f"{int(df_to_save.iloc[-1].Cekilis_No)}"
                    ),
                )
            st.success(
                "Kalıcı kayıt tamamlandı. GitHub veri.txt güncellendi."
            )
            st.cache_data.clear()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def github_text_file(settings, path):
    url = (
        f"https://api.github.com/repos/{settings['owner']}/"
        f"{settings['repo']}/contents/{path}"
    )
    response = requests.get(
        url,
        headers=github_headers(settings["token"]),
        params={"ref": settings["branch"]},
        timeout=30,
    )
    if response.status_code == 404:
        return "", None
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub dosyası okunamadı ({path}): "
            f"{response.status_code} {response.text[:300]}"
        )
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode(
        "utf-8", errors="ignore"
    )
    return content, payload["sha"]


def save_github_text_file(settings, path, text, message):
    current_text, sha = github_text_file(settings, path)
    url = (
        f"https://api.github.com/repos/{settings['owner']}/"
        f"{settings['repo']}/contents/{path}"
    )
    payload = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": settings["branch"],
    }
    if sha:
        payload["sha"] = sha

    response = requests.put(
        url,
        headers=github_headers(settings["token"]),
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"GitHub kaydı başarısız ({path}): "
            f"{response.status_code} {response.text[:500]}"
        )
    return response.json()


def parse_coupon_lines(text):
    coupons = []
    for line in str(text).splitlines():
        nums = sorted(
            set(
                int(x)
                for x in re.findall(r"\d+", line)
                if 1 <= int(x) <= 80
            )
        )
        if len(nums) >= 2:
            coupons.append(nums)
    if not coupons:
        nums = sorted(
            set(
                int(x)
                for x in re.findall(r"\d+", str(text))
                if 1 <= int(x) <= 80
            )
        )
        if len(nums) >= 2:
            coupons = [nums]
    return coupons


def empty_coupon_archive():
    return pd.DataFrame(
        columns=[
            "Kupon_ID",
            "Etiket",
            "Kayit_Tarihi",
            "Kayit_Saati",
            "Baslangic_Cekilis",
            "Kolon",
            "Boyut",
        ]
    )


def load_coupon_archive(settings):
    text, _ = github_text_file(settings, "kuponlar.csv")
    if not text.strip():
        return empty_coupon_archive()
    try:
        archive = pd.read_csv(io.StringIO(text), dtype=str)
    except Exception:
        return empty_coupon_archive()

    for col in empty_coupon_archive().columns:
        if col not in archive.columns:
            archive[col] = ""
    archive["Baslangic_Cekilis"] = pd.to_numeric(
        archive["Baslangic_Cekilis"], errors="coerce"
    ).fillna(0).astype(int)
    archive["Boyut"] = pd.to_numeric(
        archive["Boyut"], errors="coerce"
    ).fillna(0).astype(int)
    return archive[list(empty_coupon_archive().columns)]


def save_coupon_archive(settings, archive):
    csv_text = archive.to_csv(index=False)
    save_github_text_file(
        settings,
        "kuponlar.csv",
        csv_text,
        "Kupon arşivi güncellendi",
    )


def append_coupons_to_archive(
    settings,
    coupons,
    label,
    start_draw,
):
    archive = load_coupon_archive(settings)
    now = datetime.now()
    new_rows = []
    base_id = int(now.strftime("%Y%m%d%H%M%S"))
    for i, coupon in enumerate(coupons, start=1):
        new_rows.append(
            {
                "Kupon_ID": str(base_id + i),
                "Etiket": label or f"Kupon {i}",
                "Kayit_Tarihi": now.strftime("%d.%m.%Y"),
                "Kayit_Saati": now.strftime("%H:%M:%S"),
                "Baslangic_Cekilis": int(start_draw),
                "Kolon": "-".join(map(str, coupon)),
                "Boyut": len(coupon),
            }
        )
    archive = pd.concat(
        [archive, pd.DataFrame(new_rows)],
        ignore_index=True,
    )
    save_coupon_archive(settings, archive)
    return archive, pd.DataFrame(new_rows)


def coupon_numbers_from_archive_row(row):
    return sorted(
        set(
            int(x)
            for x in re.findall(r"\d+", str(row["Kolon"]))
            if 1 <= int(x) <= 80
        )
    )


def coupon_performance_summary(df, archive):
    rows = []
    details = {}
    for _, row in archive.iterrows():
        coupon = coupon_numbers_from_archive_row(row)
        start_draw = int(row["Baslangic_Cekilis"])
        tested = df[df["Cekilis_No"].astype(int) >= start_draw].copy()

        detail_rows = []
        for _, draw in tested.iterrows():
            actual = set(int(draw[c]) for c in NUM_COLS)
            hits = sorted(set(coupon) & actual)
            detail_rows.append(
                {
                    "Çekiliş": int(draw.Cekilis_No),
                    "Tarih": draw.Tarih,
                    "Saat": draw.Saat,
                    "İsabet": len(hits),
                    "Tutan Sayılar": " - ".join(map(str, hits)),
                }
            )
        detail_df = pd.DataFrame(detail_rows)
        details[str(row["Kupon_ID"])] = detail_df

        if detail_df.empty:
            avg_hit = 0.0
            max_hit = 0
            best_count = 0
            hit_rate = 0.0
        else:
            avg_hit = float(detail_df["İsabet"].mean())
            max_hit = int(detail_df["İsabet"].max())
            best_count = int(
                (detail_df["İsabet"] == max_hit).sum()
            )
            hit_rate = (
                avg_hit / max(len(coupon), 1) * 100
            )

        rows.append(
            {
                "Kupon_ID": row["Kupon_ID"],
                "Etiket": row["Etiket"],
                "Kolon": row["Kolon"],
                "Boyut": len(coupon),
                "Başlangıç Çekilişi": start_draw,
                "Test Edilen Çekiliş": len(detail_df),
                "Ortalama İsabet": round(avg_hit, 2),
                "Ortalama İsabet %": round(hit_rate, 2),
                "En Yüksek İsabet": max_hit,
                "En İyi Sonuç Adedi": best_count,
            }
        )
    return pd.DataFrame(rows), details


def delete_coupon_from_archive(settings, coupon_id):
    archive = load_coupon_archive(settings)
    new_archive = archive[
        archive["Kupon_ID"].astype(str) != str(coupon_id)
    ].copy()
    save_coupon_archive(settings, new_archive)
    return new_archive


def create_pdf_report(df, score_df=None):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 45

    def line(text, size=10, gap=15):
        nonlocal y
        if y < 55:
            pdf.showPage()
            y = height - 45
        pdf.setFont("Helvetica", size)
        pdf.drawString(40, y, str(text)[:110])
        y -= gap

    pdf.setTitle("Hizli On V10 Analiz Raporu")
    line("HIZLI ON ULTIMATE V10 ANALIZ RAPORU", 15, 24)
    line(f"Toplam cekilis: {len(df)}", 11)
    latest = df.iloc[-1]
    line(
        f"Son cekilis: {int(latest.Cekilis_No)} | "
        f"{latest.Tarih} {latest.Saat}",
        11,
    )
    line("")

    freq_df = frequency(df).sort_values(
        ["Frekans", "Sayı"], ascending=[False, True]
    ).head(20)
    line("En sik 20 sayi", 12, 20)
    for _, row in freq_df.iterrows():
        line(f"Sayi {int(row['Sayı'])}: {int(row['Frekans'])} kez")

    line("")
    gap_df = gaps(df).sort_values(
        ["Dinlenme", "Sayı"], ascending=[False, True]
    ).head(20)
    line("En uzun dinlenen 20 sayi", 12, 20)
    for _, row in gap_df.iterrows():
        line(f"Sayi {int(row['Sayı'])}: {int(row['Dinlenme'])} cekilis")

    if score_df is not None and not score_df.empty:
        line("")
        line("En yuksek guc puanli 20 sayi", 12, 20)
        for _, row in score_df.head(20).iterrows():
            line(
                f"Sayi {int(row['Sayı'])}: "
                f"{float(row['Toplam Puan']):.2f} puan"
            )

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def transition_statistics(df, source_numbers, lookback=None):
    """Kaynak sayılar görüldükten hemen sonraki çekilişleri inceler."""
    if lookback:
        work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    else:
        work = df.reset_index(drop=True)

    sets = row_sets(work)
    baseline = frequency(work).set_index("Sayı")["Frekans"] / max(len(work), 1)
    source_numbers = sorted(set(int(n) for n in source_numbers if 1 <= int(n) <= 80))

    per_source = []
    aggregate_counts = Counter()
    aggregate_events = 0
    source_coverage = Counter()
    next_draw_sets = []

    for source in source_numbers:
        events = []
        next_counts = Counter()

        for i in range(len(sets) - 1):
            if source in sets[i]:
                events.append(i)
                next_counts.update(sets[i + 1])
                next_draw_sets.append(sets[i + 1])

        event_count = len(events)
        aggregate_events += event_count
        aggregate_counts.update(next_counts)

        if event_count:
            for candidate in next_counts:
                if next_counts[candidate] > 0:
                    source_coverage[candidate] += 1

        repeat_count = next_counts.get(source, 0)
        repeat_rate = repeat_count / event_count if event_count else 0.0

        strongest = [
            (n, c, c / event_count if event_count else 0.0)
            for n, c in next_counts.most_common(12)
        ]
        per_source.append({
            "Kaynak sayı": source,
            "Geçmiş olay": event_count,
            "Tekrar adedi": repeat_count,
            "Tekrar oranı %": round(repeat_rate * 100, 2),
            "Sonraki güçlü sayılar": " | ".join(
                f"{n} ({rate*100:.1f}%)" for n, _, rate in strongest
            ),
        })

    candidate_rows = []
    denom = max(aggregate_events, 1)
    for n in range(1, 81):
        count = aggregate_counts.get(n, 0)
        transition_rate = count / denom
        base_rate = float(baseline.get(n, 0))
        lift = transition_rate / base_rate if base_rate > 0 else 0.0
        coverage = source_coverage.get(n, 0)
        is_repeat = n in source_numbers

        candidate_rows.append({
            "Sayı": n,
            "Geçiş adedi": count,
            "Geçiş oranı %": round(transition_rate * 100, 2),
            "Genel oran %": round(base_rate * 100, 2),
            "Lift": round(lift, 3),
            "Kaynak desteği": coverage,
            "Tür": "Tekrar adayı" if is_repeat else "Yerine geçme adayı",
        })

    candidates = pd.DataFrame(candidate_rows)
    if not candidates.empty:
        for col in ["Geçiş oranı %", "Lift", "Kaynak desteği"]:
            candidates[col + "_n"] = normalized_series(candidates[col])
        candidates["Geçiş Puanı"] = (
            0.50 * candidates["Geçiş oranı %_n"]
            + 0.30 * candidates["Lift_n"]
            + 0.20 * candidates["Kaynak desteği_n"]
        ) * 100
        candidates["Geçiş Puanı"] = candidates["Geçiş Puanı"].round(2)
        candidates = candidates.sort_values(
            ["Geçiş Puanı", "Geçiş adedi", "Sayı"],
            ascending=[False, False, True],
        )

    pair_counts = Counter()
    for next_set in next_draw_sets:
        pair_counts.update(combinations(sorted(next_set), 2))

    return pd.DataFrame(per_source), candidates, pair_counts


def transition_chain_table(df, source_numbers, lookback=None):
    """Kaynak → bir sonraki → iki sonraki çekiliş zincirini özetler."""
    if lookback:
        work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    else:
        work = df.reset_index(drop=True)

    sets = row_sets(work)
    rows = []
    for source in sorted(set(source_numbers)):
        first_counts = Counter()
        second_counts = Counter()
        event_count = 0

        for i in range(len(sets) - 2):
            if source in sets[i]:
                event_count += 1
                first_counts.update(sets[i + 1])
                second_counts.update(sets[i + 2])

        rows.append({
            "Kaynak": source,
            "Olay": event_count,
            "1 el sonra": " - ".join(str(n) for n, _ in first_counts.most_common(8)),
            "2 el sonra": " - ".join(str(n) for n, _ in second_counts.most_common(8)),
        })
    return pd.DataFrame(rows)


def transition_coupon(candidates, pair_counts, size, seed_shift=0):
    """Geçiş puanı, bant dengesi ve sonraki çekiliş uyumuyla kupon kurar."""
    if candidates.empty:
        return []

    work = candidates.copy()
    work["Seçim Puanı"] = work["Geçiş Puanı"] + (
        ((work["Sayı"] * 11 + seed_shift * 7) % 17) / 100
    )

    selected = []
    band_counts = [0, 0, 0, 0]
    max_per_band = max(2, int(np.ceil(size / 3)))

    while len(selected) < size:
        best_number = None
        best_score = -1.0

        for _, row in work.iterrows():
            n = int(row["Sayı"])
            if n in selected:
                continue

            band_idx = next(
                i for i, (lo, hi) in enumerate(BANDS) if lo <= n <= hi
            )
            if band_counts[band_idx] >= max_per_band:
                continue

            compatibility = sum(
                pair_counts.get(tuple(sorted((n, chosen))), 0)
                for chosen in selected
            )
            score = float(row["Seçim Puanı"]) + 0.08 * compatibility

            # En fazla üçlü ardışık zincir oluşmasını engelle.
            trial = set(selected + [n])
            long_run = (
                {n - 2, n - 1, n}.issubset(trial)
                or {n - 1, n, n + 1}.issubset(trial)
                or {n, n + 1, n + 2}.issubset(trial)
            )
            if long_run:
                score -= 8

            if score > best_score:
                best_score = score
                best_number = n

        if best_number is None:
            for n in work["Sayı"].astype(int):
                if n not in selected:
                    best_number = n
                    break

        if best_number is None:
            break

        selected.append(best_number)
        band_idx = next(
            i for i, (lo, hi) in enumerate(BANDS)
            if lo <= best_number <= hi
        )
        band_counts[band_idx] += 1

    return sorted(selected)


def explain_transition_coupon(coupon, candidates):
    indexed = candidates.set_index("Sayı")
    rows = []
    for n in coupon:
        row = indexed.loc[n]
        rows.append({
            "Sayı": n,
            "Geçiş puanı": row["Geçiş Puanı"],
            "Tür": row["Tür"],
            "Geçiş oranı %": row["Geçiş oranı %"],
            "Lift": row["Lift"],
            "Kaynak desteği": row["Kaynak desteği"],
        })
    return pd.DataFrame(rows)


def hybrid_transition_table(df, transition_candidates, target_time=None):
    """Geçiş verisini bütün ana analiz puanlarıyla birleştirir."""
    if transition_candidates.empty:
        return transition_candidates.copy()

    smart = intelligent_score_table(df, target_time).copy()
    smart = smart.rename(columns={"Toplam Puan": "Genel Güç Puanı"})

    merged = transition_candidates.merge(
        smart[
            [
                "Sayı",
                "Genel Güç Puanı",
                "Son 10",
                "Son 25",
                "Dinlenme",
                "Dönüş uyumu",
                "Tekrar oranı",
                "Saat oranı",
                "Birlikte gelme",
                "Blok puanı",
            ]
        ],
        on="Sayı",
        how="left",
    ).fillna(0)

    # Her bileşeni aynı ölçeğe getir.
    merged["Geçiş_n"] = normalized_series(merged["Geçiş Puanı"])
    merged["Genel_n"] = normalized_series(merged["Genel Güç Puanı"])
    merged["Tekrar_n"] = normalized_series(merged["Tekrar oranı"])
    merged["Saat_n"] = normalized_series(merged["Saat oranı"])
    merged["Bağ_n"] = normalized_series(merged["Birlikte gelme"])
    merged["Dönüş_n"] = normalized_series(merged["Dönüş uyumu"])
    merged["Blok_n"] = normalized_series(merged["Blok puanı"])

    # Geçiş motoru ana ağırlık; diğer istatistikler filtre görevi görür.
    merged["Hibrit Puan"] = (
        0.40 * merged["Geçiş_n"]
        + 0.18 * merged["Genel_n"]
        + 0.13 * merged["Tekrar_n"]
        + 0.09 * merged["Saat_n"]
        + 0.09 * merged["Bağ_n"]
        + 0.07 * merged["Dönüş_n"]
        + 0.04 * merged["Blok_n"]
    ) * 100

    # Bir sayı hem tekrar adayı hem de yüksek geçiş desteğine sahipse küçük destek.
    repeat_bonus = (
        (merged["Tür"] == "Tekrar adayı")
        & (merged["Geçiş oranı %"] >= merged["Geçiş oranı %"].quantile(0.60))
    )
    merged.loc[repeat_bonus, "Hibrit Puan"] += 3.0

    merged["Hibrit Puan"] = merged["Hibrit Puan"].clip(0, 100).round(2)
    return merged.sort_values(
        ["Hibrit Puan", "Geçiş Puanı", "Sayı"],
        ascending=[False, False, True],
    )


def transition_profile_score(row, profile):
    """Farklı kupon stratejileri için aday puanını hesaplar."""
    if profile == "Tekrar ağırlıklı":
        type_bonus = 12 if row["Tür"] == "Tekrar adayı" else 0
        return (
            0.50 * float(row["Hibrit Puan"])
            + 0.25 * float(row["Tekrar oranı"]) * 100
            + 0.15 * float(row["Genel Güç Puanı"])
            + 0.10 * float(row["Geçiş Puanı"])
            + type_bonus
        )
    if profile == "Yerine geçme ağırlıklı":
        type_bonus = 10 if row["Tür"] == "Yerine geçme adayı" else 0
        return (
            0.50 * float(row["Hibrit Puan"])
            + 0.25 * float(row["Geçiş Puanı"])
            + 0.15 * float(row["Lift"]) * 20
            + 0.10 * float(row["Kaynak desteği"])
            + type_bonus
        )
    if profile == "Saat ve sıcaklık":
        return (
            0.45 * float(row["Hibrit Puan"])
            + 0.20 * float(row["Genel Güç Puanı"])
            + 0.18 * float(row["Saat oranı"]) * 100
            + 0.12 * float(row["Son 10"]) * 100
            + 0.05 * float(row["Dönüş uyumu"]) * 100
        )
    # Dengeli
    return float(row["Hibrit Puan"])


def build_profile_coupon(
    hybrid_candidates,
    pair_counts,
    size,
    profile,
    excluded_coupons=None,
    diversity_seed=0,
):
    """Profil bazlı, bant dengeli ve önceki kuponlardan farklı kupon üretir."""
    if hybrid_candidates.empty:
        return []

    excluded_coupons = excluded_coupons or []
    work = hybrid_candidates.copy()
    work["Profil Puanı"] = work.apply(
        lambda row: transition_profile_score(row, profile),
        axis=1,
    )
    work["Profil Puanı"] += (
        (work["Sayı"] * (13 + diversity_seed) + diversity_seed * 17) % 23
    ) / 100

    selected = []
    band_counts = [0, 0, 0, 0]
    max_per_band = max(2, int(np.ceil(size / 3)))

    while len(selected) < size:
        best_n = None
        best_score = -10**9

        for _, row in work.iterrows():
            n = int(row["Sayı"])
            if n in selected:
                continue

            band_idx = next(
                i for i, (lo, hi) in enumerate(BANDS) if lo <= n <= hi
            )
            if band_counts[band_idx] >= max_per_band:
                continue

            compatibility = sum(
                pair_counts.get(tuple(sorted((n, chosen))), 0)
                for chosen in selected
            )
            score = float(row["Profil Puanı"]) + 0.07 * compatibility

            # Önceki kuponlarla aşırı benzerliği azalt.
            for old in excluded_coupons:
                if n in old:
                    overlap = len(set(selected) & set(old))
                    score -= 1.8 + 0.8 * overlap

            trial = set(selected + [n])
            if (
                {n - 2, n - 1, n}.issubset(trial)
                or {n - 1, n, n + 1}.issubset(trial)
                or {n, n + 1, n + 2}.issubset(trial)
            ):
                score -= 7

            if score > best_score:
                best_score = score
                best_n = n

        if best_n is None:
            for n in work.sort_values("Profil Puanı", ascending=False)["Sayı"].astype(int):
                if n not in selected:
                    best_n = n
                    break

        if best_n is None:
            break

        selected.append(best_n)
        band_idx = next(
            i for i, (lo, hi) in enumerate(BANDS)
            if lo <= best_n <= hi
        )
        band_counts[band_idx] += 1

    return sorted(selected)


def generate_unique_profile_coupons(
    hybrid_candidates,
    pair_counts,
    size,
    count,
):
    profiles = [
        "Dengeli",
        "Tekrar ağırlıklı",
        "Yerine geçme ağırlıklı",
        "Saat ve sıcaklık",
    ]
    coupons = []
    attempts = 0

    while len(coupons) < count and attempts < count * 12:
        profile = profiles[attempts % len(profiles)]
        coupon = build_profile_coupon(
            hybrid_candidates,
            pair_counts,
            size,
            profile,
            excluded_coupons=coupons,
            diversity_seed=attempts,
        )
        if coupon and coupon not in coupons:
            coupons.append(coupon)
        attempts += 1

    return [
        {
            "Kupon": coupon,
            "Profil": profiles[i % len(profiles)],
        }
        for i, coupon in enumerate(coupons)
    ]


def explain_hybrid_coupon(coupon, hybrid_candidates):
    indexed = hybrid_candidates.set_index("Sayı")
    rows = []
    for n in coupon:
        row = indexed.loc[n]
        reasons = []
        if row["Tür"] == "Tekrar adayı":
            reasons.append("son çekilişten tekrar adayı")
        else:
            reasons.append("yerine geçme adayı")
        if row["Tekrar oranı"] >= hybrid_candidates["Tekrar oranı"].quantile(0.70):
            reasons.append("tekrar eğilimi")
        if row["Saat oranı"] >= hybrid_candidates["Saat oranı"].quantile(0.70):
            reasons.append("saat desteği")
        if row["Birlikte gelme"] >= hybrid_candidates["Birlikte gelme"].quantile(0.70):
            reasons.append("birlikte gelme")
        if row["Dönüş uyumu"] >= hybrid_candidates["Dönüş uyumu"].quantile(0.70):
            reasons.append("dönüş zamanı yakın")

        rows.append(
            {
                "Sayı": n,
                "Hibrit Puan": row["Hibrit Puan"],
                "Geçiş Puanı": row["Geçiş Puanı"],
                "Genel Güç": row["Genel Güç Puanı"],
                "Tür": row["Tür"],
                "Neden seçildi?": ", ".join(reasons),
            }
        )
    return pd.DataFrame(rows)


def coupon_recent_performance(df, coupons, last_n=100):
    rows = []
    test_df = df.tail(min(last_n, len(df)))
    for idx, item in enumerate(coupons, start=1):
        coupon = item["Kupon"]
        detail = historical_coupon_test(test_df, coupon)
        rows.append(
            {
                "Kupon": idx,
                "Profil": item["Profil"],
                "Kolon": " - ".join(map(str, coupon)),
                "Test çekilişi": len(detail),
                "Ortalama isabet": round(float(detail["İsabet"].mean()), 2),
                "En yüksek isabet": int(detail["İsabet"].max()),
                "3+ isabet adedi": int((detail["İsabet"] >= 3).sum()),
                "4+ isabet adedi": int((detail["İsabet"] >= 4).sum()),
            }
        )
    return pd.DataFrame(rows)


def generated_coupon_result_table(df, generated_items, start_draw):
    """Üretilen kuponların, üretimden sonraki çekilişlerdeki sonucunu gösterir."""
    rows = []
    tested = df[df["Cekilis_No"].astype(int) >= int(start_draw)].copy()
    for idx, item in enumerate(generated_items, start=1):
        coupon = sorted(set(item["Kupon"]))
        for _, draw in tested.iterrows():
            actual = set(int(draw[c]) for c in NUM_COLS)
            hits = sorted(set(coupon) & actual)
            rows.append({
                "Kupon": idx,
                "Profil": item["Profil"],
                "Çekiliş": int(draw.Cekilis_No),
                "Tarih/Saat": f"{draw.Tarih} {draw.Saat}",
                "İsabet": len(hits),
                "Tutan sayılar": " - ".join(map(str, hits)),
            })
    return pd.DataFrame(rows)


def profile_learning_summary(result_df):
    """Gerçek sonraki sonuçlara göre profil başarılarını özetler."""
    if result_df.empty:
        return pd.DataFrame()
    summary = (
        result_df.groupby("Profil", as_index=False)
        .agg(
            Test=("Çekiliş", "count"),
            Ortalama_İsabet=("İsabet", "mean"),
            En_Yüksek_İsabet=("İsabet", "max"),
            Üç_Artı=("İsabet", lambda s: int((s >= 3).sum())),
            Dört_Artı=("İsabet", lambda s: int((s >= 4).sum())),
        )
    )
    summary["Öğrenme Ağırlığı"] = (
        0.55 * normalized_series(summary["Ortalama_İsabet"])
        + 0.25 * normalized_series(summary["Üç_Artı"])
        + 0.20 * normalized_series(summary["Dört_Artı"])
    )
    summary["Öğrenme Ağırlığı"] = (
        summary["Öğrenme Ağırlığı"] / max(summary["Öğrenme Ağırlığı"].sum(), 1)
    ).round(3)
    return summary.sort_values(
        ["Öğrenme Ağırlığı", "Ortalama_İsabet"],
        ascending=False,
    )


def archive_profile_learning(df, archive):
    """Kupon arşivindeki profil etiketlerinden kalıcı öğrenme özeti çıkarır."""
    if archive is None or archive.empty:
        return pd.DataFrame()

    rows = []
    for _, rec in archive.iterrows():
        label = str(rec.get("Etiket", ""))
        profile = "Bilinmeyen"
        for candidate in [
            "Dengeli",
            "Tekrar ağırlıklı",
            "Yerine geçme ağırlıklı",
            "Saat ve sıcaklık",
        ]:
            if candidate.lower() in label.lower():
                profile = candidate
                break

        coupon = coupon_numbers_from_archive_row(rec)
        start_draw = int(rec["Baslangic_Cekilis"])
        tested = df[df["Cekilis_No"].astype(int) >= start_draw]
        for _, draw in tested.iterrows():
            actual = set(int(draw[c]) for c in NUM_COLS)
            hits = len(set(coupon) & actual)
            rows.append({
                "Profil": profile,
                "Çekiliş": int(draw.Cekilis_No),
                "İsabet": hits,
            })

    return profile_learning_summary(pd.DataFrame(rows))


def next_draw_number(df):
    return int(df.iloc[-1].Cekilis_No) + 1


def core_three_analysis(df, target_time=None, window=100):
    """
    Son çekilişteki 20 sayı arasından en güçlü üç çekirdeği seçer.
    Tekrar, birlikte gelme, dönüş zamanı, saat ve genel güç kullanılır.
    """
    if df.empty:
        return [], pd.DataFrame()

    latest_row = df.sort_values("Cekilis_No").iloc[-1]
    latest_numbers = sorted(int(latest_row[c]) for c in NUM_COLS)
    subset = df.tail(min(int(window), len(df))).copy()

    repeat_rates = repeat_probability(subset)
    gap_df = gaps(df).set_index("Sayı")
    cycle_df = return_cycle_table(df).set_index("Sayı")
    smart = intelligent_score_table(
        df,
        target_time or str(latest_row.Saat),
    ).set_index("Sayı")

    pair_counts = Counter()
    for draw_set in row_sets(subset):
        pair_counts.update(combinations(sorted(draw_set), 2))

    rows = []
    for number in latest_numbers:
        relationship = sum(
            pair_counts.get(tuple(sorted((number, other))), 0)
            for other in latest_numbers
            if other != number
        )

        current_gap = float(gap_df.loc[number, "Dinlenme"])
        expected_rest = max(
            float(cycle_df.loc[number, "Ort. dönüş aralığı"]) - 1.0,
            0.0,
        )
        comeback_fit = float(
            np.exp(
                -abs(current_gap - expected_rest)
                / (expected_rest + 2.0)
            )
        )

        rows.append(
            {
                "Sayı": number,
                "Tekrar oranı": float(repeat_rates.get(number, 0.0)),
                "Son çekiliş bağı": float(relationship),
                "Dönüş uyumu": comeback_fit,
                "Genel güç": float(smart.loc[number, "Toplam Puan"]),
                "Saat oranı": float(smart.loc[number, "Saat oranı"]),
            }
        )

    table = pd.DataFrame(rows)
    components = [
        "Tekrar oranı",
        "Son çekiliş bağı",
        "Dönüş uyumu",
        "Genel güç",
        "Saat oranı",
    ]
    for column in components:
        table[column + "_n"] = normalized_series(table[column])

    table["Çekirdek Puan"] = (
        0.30 * table["Tekrar oranı_n"]
        + 0.25 * table["Son çekiliş bağı_n"]
        + 0.20 * table["Dönüş uyumu_n"]
        + 0.15 * table["Genel güç_n"]
        + 0.10 * table["Saat oranı_n"]
    ) * 100
    table["Çekirdek Puan"] = table["Çekirdek Puan"].round(2)
    table = table.sort_values(
        ["Çekirdek Puan", "Sayı"],
        ascending=[False, True],
    )

    core = table.head(3)["Sayı"].astype(int).tolist()
    return core, table


def companion_candidates_for_core(
    df,
    core,
    target_time=None,
    window=150,
):
    """
    Çekirdek üçlüyle birlikte gelen ve dinlenip dönüş zamanı yaklaşan
    sayıları ortak puanla sıralar.
    """
    if not core:
        return pd.DataFrame()

    subset = df.tail(min(int(window), len(df))).copy()
    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)

    together_counts = Counter()
    for draw_set in row_sets(subset):
        overlap = len(set(core) & draw_set)
        if overlap:
            for candidate in draw_set:
                if candidate not in core:
                    together_counts[candidate] += overlap

    smart = intelligent_score_table(
        df,
        target_time or str(df.iloc[-1].Saat),
    ).set_index("Sayı")
    gap_df = gaps(df).set_index("Sayı")
    cycle_df = return_cycle_table(df).set_index("Sayı")

    rows = []
    for number in range(1, 81):
        if number in core:
            continue

        current_gap = float(gap_df.loc[number, "Dinlenme"])
        expected_rest = max(
            float(cycle_df.loc[number, "Ort. dönüş aralığı"]) - 1.0,
            0.0,
        )
        comeback_fit = float(
            np.exp(
                -abs(current_gap - expected_rest)
                / (expected_rest + 2.0)
            )
        )

        rows.append(
            {
                "Sayı": number,
                "Çekirdekle birlikte": int(together_counts.get(number, 0)),
                "Dönüş uyumu": comeback_fit,
                "Dinlenme": int(current_gap),
                "Genel güç": float(smart.loc[number, "Toplam Puan"]),
                "Saat oranı": float(smart.loc[number, "Saat oranı"]),
                "Son çekilişte vardı": number in latest_set,
            }
        )

    output = pd.DataFrame(rows)
    components = [
        "Çekirdekle birlikte",
        "Dönüş uyumu",
        "Genel güç",
        "Saat oranı",
    ]
    for column in components:
        output[column + "_n"] = normalized_series(output[column])

    output["Yoldaş Puan"] = (
        0.42 * output["Çekirdekle birlikte_n"]
        + 0.23 * output["Dönüş uyumu_n"]
        + 0.20 * output["Genel güç_n"]
        + 0.15 * output["Saat oranı_n"]
    ) * 100

    comeback_bonus = (
        (~output["Son çekilişte vardı"])
        & (
            output["Dönüş uyumu"]
            >= output["Dönüş uyumu"].quantile(0.70)
        )
    )
    output.loc[comeback_bonus, "Yoldaş Puan"] += 4.0
    output["Yoldaş Puan"] = output["Yoldaş Puan"].clip(0, 100).round(2)

    return output.sort_values(
        ["Yoldaş Puan", "Çekirdekle birlikte", "Sayı"],
        ascending=[False, False, True],
    )


def build_core_companion_coupon(
    core,
    companions,
    size=7,
    diversity_shift=0,
):
    """Üç çekirdek ve güçlü yoldaş/dönüş adaylarıyla dengeli kupon kurar."""
    selected = list(dict.fromkeys(int(number) for number in core))
    if companions.empty:
        return sorted(selected[:size])

    work = companions.copy()
    work["Seçim Puanı"] = work["Yoldaş Puan"] + (
        (
            work["Sayı"] * 19
            + diversity_shift * 11
        ) % 29
    ) / 100

    band_counts = [
        sum(low <= number <= high for number in selected)
        for low, high in BANDS
    ]
    max_per_band = max(2, int(np.ceil(size / 3)))

    while len(selected) < size:
        best_number = None
        best_score = -10**9

        for _, row in work.iterrows():
            number = int(row["Sayı"])
            if number in selected:
                continue

            band_index = next(
                index
                for index, (low, high) in enumerate(BANDS)
                if low <= number <= high
            )
            if band_counts[band_index] >= max_per_band:
                continue

            score = float(row["Seçim Puanı"])
            if not bool(row["Son çekilişte vardı"]):
                score += 1.5

            trial = set(selected + [number])
            long_run = (
                {number - 2, number - 1, number}.issubset(trial)
                or {number - 1, number, number + 1}.issubset(trial)
                or {number, number + 1, number + 2}.issubset(trial)
            )
            if long_run:
                score -= 6.0

            if score > best_score:
                best_score = score
                best_number = number

        if best_number is None:
            break

        selected.append(best_number)
        band_index = next(
            index
            for index, (low, high) in enumerate(BANDS)
            if low <= best_number <= high
        )
        band_counts[band_index] += 1

    return sorted(selected[:size])


def explain_core_coupon(coupon, core, companions):
    indexed = companions.set_index("Sayı")
    rows = []

    for number in coupon:
        if number in core:
            rows.append(
                {
                    "Sayı": number,
                    "Rol": "Çekirdek",
                    "Puan": "-",
                    "Neden seçildi?": (
                        "Son çekilişte bulunan güçlü tekrar/bağ çekirdeği"
                    ),
                }
            )
            continue

        row = indexed.loc[number]
        reasons = ["çekirdekle birlikte gelme"]
        if (
            row["Dönüş uyumu"]
            >= companions["Dönüş uyumu"].quantile(0.70)
        ):
            reasons.append("dinlenip dönüş zamanı yakın")
        if (
            row["Saat oranı"]
            >= companions["Saat oranı"].quantile(0.70)
        ):
            reasons.append("saat desteği")

        rows.append(
            {
                "Sayı": number,
                "Rol": "Yoldaş/Dönüş",
                "Puan": row["Yoldaş Puan"],
                "Neden seçildi?": ", ".join(reasons),
            }
        )

    return pd.DataFrame(rows)



def consecutive_pairs(draw_set):
    """Bir çekilişte bulunan ardışık 2'li blokları döndürür."""
    values = sorted(set(int(n) for n in draw_set))
    return [(n, n + 1) for n in values if n + 1 in values]


def carryover_distribution(df, window=None):
    """Ardışık çekilişler arasında kaç sayının taşındığını özetler."""
    work = df.tail(min(int(window), len(df))) if window else df
    work = work.reset_index(drop=True)
    sets = row_sets(work)

    rows = []
    for i in range(1, len(sets)):
        carried = sorted(sets[i - 1] & sets[i])
        rows.append(
            {
                "Çekiliş": int(work.iloc[i].Cekilis_No),
                "Önceki çekiliş": int(work.iloc[i - 1].Cekilis_No),
                "Taşınan sayı": len(carried),
                "Taşınanlar": " - ".join(map(str, carried)),
            }
        )

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()

    counts = (
        detail["Taşınan sayı"]
        .value_counts()
        .sort_index()
        .rename_axis("Taşınan sayı")
        .reset_index(name="Adet")
    )
    counts["Oran %"] = (
        counts["Adet"] / max(len(detail), 1) * 100
    ).round(2)
    return detail.sort_values("Çekiliş", ascending=False), counts


def carryover_number_scores(df, target_time=None, window=300):
    """
    Son çekilişteki 20 sayı için bir sonraki ele taşınma puanı üretir.
    Geçmiş tekrar oranı, kısa dönem devam, seri, saat ve bağ gücü kullanılır.
    """
    work = df.tail(min(int(window), len(df))).reset_index(drop=True)
    sets = row_sets(work)
    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)

    cases = Counter()
    hits = Counter()
    recent_cases = Counter()
    recent_hits = Counter()

    recent_start = max(0, len(sets) - 25)
    for i in range(len(sets) - 1):
        for n in sets[i]:
            cases[n] += 1
            if n in sets[i + 1]:
                hits[n] += 1
            if i >= recent_start:
                recent_cases[n] += 1
                if n in sets[i + 1]:
                    recent_hits[n] += 1

    streaks = streak_table(df).set_index("Sayı")
    smart = intelligent_score_table(
        df,
        target_time or str(df.iloc[-1].Saat),
    ).set_index("Sayı")

    # Son çekiliş içindeki bağ gücü
    pair_counts = Counter()
    for draw_set in sets:
        pair_counts.update(combinations(sorted(draw_set), 2))

    rows = []
    for n in sorted(latest_set):
        overall_rate = hits[n] / cases[n] if cases[n] else 0.0
        recent_rate = (
            recent_hits[n] / recent_cases[n]
            if recent_cases[n]
            else overall_rate
        )
        latest_link = sum(
            pair_counts.get(tuple(sorted((n, other))), 0)
            for other in latest_set
            if other != n
        )
        current_streak = float(streaks.loc[n, "Mevcut seri"])
        longest_streak = max(float(streaks.loc[n, "En uzun seri"]), 1.0)
        fatigue = min(current_streak / longest_streak, 1.0)

        rows.append(
            {
                "Sayı": n,
                "Genel tekrar oranı": overall_rate,
                "Son 25 tekrar oranı": recent_rate,
                "Mevcut seri": int(current_streak),
                "Yorgunluk": fatigue,
                "Son çekiliş bağı": float(latest_link),
                "Saat oranı": float(smart.loc[n, "Saat oranı"]),
                "Genel güç": float(smart.loc[n, "Toplam Puan"]),
            }
        )

    out = pd.DataFrame(rows)
    for col in [
        "Genel tekrar oranı",
        "Son 25 tekrar oranı",
        "Son çekiliş bağı",
        "Saat oranı",
        "Genel güç",
    ]:
        out[col + "_n"] = normalized_series(out[col])

    out["Taşıma Puanı"] = (
        0.28 * out["Genel tekrar oranı_n"]
        + 0.26 * out["Son 25 tekrar oranı_n"]
        + 0.18 * out["Son çekiliş bağı_n"]
        + 0.14 * out["Saat oranı_n"]
        + 0.14 * out["Genel güç_n"]
        - 0.10 * out["Yorgunluk"]
    ) * 100
    out["Taşıma Puanı"] = out["Taşıma Puanı"].clip(0, 100).round(2)

    q70 = out["Taşıma Puanı"].quantile(0.70)
    q35 = out["Taşıma Puanı"].quantile(0.35)
    out["Sınıf"] = np.where(
        out["Taşıma Puanı"] >= q70,
        "Güçlü taşıma",
        np.where(
            out["Taşıma Puanı"] >= q35,
            "Sınırda",
            "Yerini bırakma",
        ),
    )
    return out.sort_values(
        ["Taşıma Puanı", "Sayı"],
        ascending=[False, True],
    )


def new_arrival_scores(df, carry_scores, target_time=None, window=300):
    """
    Son çekilişte olmayan sayılar arasından, güçlü taşıma adaylarıyla
    bir sonraki elde birlikte gelme eğilimi yüksek yeni adayları puanlar.
    """
    work = df.tail(min(int(window), len(df))).reset_index(drop=True)
    sets = row_sets(work)
    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
    strong_carriers = set(
        carry_scores.head(max(3, min(7, len(carry_scores))))["Sayı"].astype(int)
    )

    next_counts = Counter()
    source_support = Counter()
    events = 0

    for i in range(len(sets) - 1):
        source_overlap = strong_carriers & sets[i]
        if not source_overlap:
            continue
        events += len(source_overlap)
        for candidate in sets[i + 1]:
            if candidate not in sets[i]:
                next_counts[candidate] += len(source_overlap)
                source_support[candidate] += 1

    smart = intelligent_score_table(
        df,
        target_time or str(df.iloc[-1].Saat),
    ).set_index("Sayı")
    gap_df = gaps(df).set_index("Sayı")
    cycle_df = return_cycle_table(df).set_index("Sayı")

    rows = []
    for n in range(1, 81):
        if n in latest_set:
            continue

        current_gap = float(gap_df.loc[n, "Dinlenme"])
        typical_rest = max(
            float(cycle_df.loc[n, "Ort. dönüş aralığı"]) - 1.0,
            0.0,
        )
        return_fit = float(
            np.exp(
                -abs(current_gap - typical_rest)
                / (typical_rest + 2.0)
            )
        )

        rows.append(
            {
                "Sayı": n,
                "Taşıyanlarla sonraki geliş": int(next_counts.get(n, 0)),
                "Kaynak desteği": int(source_support.get(n, 0)),
                "Dönüş uyumu": return_fit,
                "Dinlenme": int(current_gap),
                "Saat oranı": float(smart.loc[n, "Saat oranı"]),
                "Genel güç": float(smart.loc[n, "Toplam Puan"]),
            }
        )

    out = pd.DataFrame(rows)
    for col in [
        "Taşıyanlarla sonraki geliş",
        "Kaynak desteği",
        "Dönüş uyumu",
        "Saat oranı",
        "Genel güç",
    ]:
        out[col + "_n"] = normalized_series(out[col])

    out["Yeni Aday Puanı"] = (
        0.34 * out["Taşıyanlarla sonraki geliş_n"]
        + 0.16 * out["Kaynak desteği_n"]
        + 0.22 * out["Dönüş uyumu_n"]
        + 0.13 * out["Saat oranı_n"]
        + 0.15 * out["Genel güç_n"]
    ) * 100
    out["Yeni Aday Puanı"] = out["Yeni Aday Puanı"].round(2)

    return out.sort_values(
        ["Yeni Aday Puanı", "Sayı"],
        ascending=[False, True],
    )


def block_network_tables(df, window=300):
    """
    Ardışık blokların aynı çekilişte birlikte çıkma ve bir sonraki
    çekilişe geçiş eğilimlerini hesaplar.
    """
    work = df.tail(min(int(window), len(df))).reset_index(drop=True)
    sets = row_sets(work)

    block_frequency = Counter()
    co_network = Counter()
    transition_network = Counter()

    blocks_by_draw = []
    for draw_set in sets:
        blocks = consecutive_pairs(draw_set)
        blocks_by_draw.append(blocks)
        block_frequency.update(blocks)
        for pair_of_blocks in combinations(sorted(blocks), 2):
            co_network[pair_of_blocks] += 1

    for i in range(len(blocks_by_draw) - 1):
        for source in blocks_by_draw[i]:
            for target in blocks_by_draw[i + 1]:
                transition_network[(source, target)] += 1

    freq_rows = [
        {
            "Blok": f"{a}-{b}",
            "Frekans": count,
        }
        for (a, b), count in block_frequency.most_common(100)
    ]

    co_rows = [
        {
            "Blok 1": f"{first[0]}-{first[1]}",
            "Blok 2": f"{second[0]}-{second[1]}",
            "Birlikte çıkma": count,
        }
        for (first, second), count in co_network.most_common(100)
    ]

    transition_rows = [
        {
            "Kaynak blok": f"{source[0]}-{source[1]}",
            "Sonraki blok": f"{target[0]}-{target[1]}",
            "Geçiş adedi": count,
        }
        for (source, target), count in transition_network.most_common(100)
    ]

    return (
        pd.DataFrame(freq_rows),
        pd.DataFrame(co_rows),
        pd.DataFrame(transition_rows),
    )


def build_carryover_coupon(
    carry_scores,
    new_scores,
    size=7,
    carry_count=None,
    seed=0,
    previous_coupons=None,
):
    """
    Güçlü taşıma adayları + yeni gelen/dinlenip dönen adaylarla
    birbirinden farklı kupon üretir.
    """
    previous_coupons = previous_coupons or []
    if carry_count is None:
        carry_count = max(2, min(4, size // 2))

    carry_work = carry_scores.copy()
    new_work = new_scores.copy()

    carry_work["Seçim"] = carry_work["Taşıma Puanı"] + (
        (carry_work["Sayı"] * 17 + seed * 13) % 31
    ) / 100
    new_work["Seçim"] = new_work["Yeni Aday Puanı"] + (
        (new_work["Sayı"] * 19 + seed * 11) % 37
    ) / 100

    selected = []
    for n in carry_work.sort_values("Seçim", ascending=False)["Sayı"].astype(int):
        if any(n in old for old in previous_coupons):
            overlap_penalty = sum(n in old for old in previous_coupons)
            if overlap_penalty >= len(previous_coupons) and seed > 0:
                continue
        selected.append(n)
        if len(selected) >= carry_count:
            break

    for n in new_work.sort_values("Seçim", ascending=False)["Sayı"].astype(int):
        if n in selected:
            continue
        trial = set(selected + [n])
        if (
            {n - 2, n - 1, n}.issubset(trial)
            or {n - 1, n, n + 1}.issubset(trial)
            or {n, n + 1, n + 2}.issubset(trial)
        ):
            continue

        selected.append(n)
        if len(selected) >= size:
            break

    return sorted(selected[:size])


def generate_unique_carryover_coupons(
    carry_scores,
    new_scores,
    size,
    count,
):
    coupons = []
    attempts = 0

    while len(coupons) < count and attempts < count * 20:
        carry_count = 2 + (attempts % max(1, min(3, size - 2)))
        coupon = build_carryover_coupon(
            carry_scores,
            new_scores,
            size=size,
            carry_count=min(carry_count, size - 1),
            seed=attempts,
            previous_coupons=coupons,
        )

        if coupon and coupon not in coupons:
            # Önceki kuponlardan en az iki sayı farklı olsun.
            if all(
                len(set(coupon) ^ set(old)) >= 4
                for old in coupons
            ):
                coupons.append(coupon)
        attempts += 1

    return coupons


def explain_carryover_coupon(coupon, carry_scores, new_scores):
    carry_index = carry_scores.set_index("Sayı")
    new_index = new_scores.set_index("Sayı")
    rows = []

    for n in coupon:
        if n in carry_index.index:
            row = carry_index.loc[n]
            rows.append(
                {
                    "Sayı": n,
                    "Rol": "Elden ele taşıma",
                    "Puan": row["Taşıma Puanı"],
                    "Açıklama": (
                        f"{row['Sınıf']}; son 25 tekrar "
                        f"%{row['Son 25 tekrar oranı'] * 100:.1f}"
                    ),
                }
            )
        else:
            row = new_index.loc[n]
            rows.append(
                {
                    "Sayı": n,
                    "Rol": "Yeni/Dönüş",
                    "Puan": row["Yeni Aday Puanı"],
                    "Açıklama": (
                        f"Taşıyanlarla geliş {int(row['Taşıyanlarla sonraki geliş'])}; "
                        f"dinlenme {int(row['Dinlenme'])}"
                    ),
                }
            )
    return pd.DataFrame(rows)



def draw_transition_report(df, source_index=-2, target_index=-1):
    """İki çekiliş arasındaki taşıma, yeni geliş, düşen sayı ve bant değişimini raporlar."""
    if len(df) < 2:
        return {}, pd.DataFrame()

    source = df.iloc[source_index]
    target = df.iloc[target_index]

    source_set = set(int(source[c]) for c in NUM_COLS)
    target_set = set(int(target[c]) for c in NUM_COLS)

    carried = sorted(source_set & target_set)
    arrived = sorted(target_set - source_set)
    dropped = sorted(source_set - target_set)

    source_bands = {
        name: sum(lo <= n <= hi for n in source_set)
        for name, (lo, hi) in zip(BAND_NAMES, BANDS)
    }
    target_bands = {
        name: sum(lo <= n <= hi for n in target_set)
        for name, (lo, hi) in zip(BAND_NAMES, BANDS)
    }

    band_rows = []
    for name in BAND_NAMES:
        band_rows.append(
            {
                "Bant": name,
                "Önceki": source_bands[name],
                "Sonraki": target_bands[name],
                "Değişim": target_bands[name] - source_bands[name],
            }
        )

    summary = {
        "Önceki çekiliş": int(source.Cekilis_No),
        "Sonraki çekiliş": int(target.Cekilis_No),
        "Taşınan sayı adedi": len(carried),
        "Taşınanlar": carried,
        "Yeni gelenler": arrived,
        "Yerini bırakanlar": dropped,
        "Önceki bloklar": consecutive_pairs(source_set),
        "Sonraki bloklar": consecutive_pairs(target_set),
    }

    return summary, pd.DataFrame(band_rows)


def replacement_map_table(df, lookback=500, top_n=5):
    """
    Bir sayı çekilişten çıkıp sonraki elde görünmediğinde,
    onun yerine en sık hangi yeni sayıların geldiğini hesaplar.
    """
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    sets = row_sets(work)
    maps = defaultdict(Counter)
    cases = Counter()

    for i in range(len(sets) - 1):
        current_set = sets[i]
        next_set = sets[i + 1]
        dropped = current_set - next_set
        arrived = next_set - current_set

        for source in dropped:
            cases[source] += 1
            maps[source].update(arrived)

    rows = []
    for source in range(1, 81):
        total = cases[source]
        strongest = maps[source].most_common(top_n)
        rows.append(
            {
                "Kaynak sayı": source,
                "Yerini bırakma olayı": total,
                "En sık yerine gelenler": " | ".join(
                    f"{n} ({count}, %{(count / total * 100 if total else 0):.1f})"
                    for n, count in strongest
                ),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["Yerini bırakma olayı", "Kaynak sayı"],
        ascending=[False, True],
    )


def latest_replacement_candidates(df, lookback=500):
    """Son çekilişteki her sayı için, yerini bırakırsa öne çıkan yeni adayları birleştirir."""
    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    sets = row_sets(work)

    maps = defaultdict(Counter)
    source_cases = Counter()

    for i in range(len(sets) - 1):
        current_set = sets[i]
        next_set = sets[i + 1]
        dropped = current_set - next_set
        arrived = next_set - current_set

        for source in dropped:
            source_cases[source] += 1
            maps[source].update(arrived)

    aggregate = Counter()
    support = Counter()

    for source in latest_set:
        total = max(source_cases[source], 1)
        for candidate, count in maps[source].items():
            if candidate in latest_set:
                continue
            rate = count / total
            aggregate[candidate] += rate
            support[candidate] += 1

    rows = []
    for candidate in range(1, 81):
        if candidate in latest_set:
            continue
        rows.append(
            {
                "Sayı": candidate,
                "Yerine gelme gücü": float(aggregate.get(candidate, 0.0)),
                "Kaynak desteği": int(support.get(candidate, 0)),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["Yerine gelme_n"] = normalized_series(out["Yerine gelme gücü"])
    out["Kaynak desteği_n"] = normalized_series(out["Kaynak desteği"])
    out["Yerine Gelme Puanı"] = (
        0.70 * out["Yerine gelme_n"]
        + 0.30 * out["Kaynak desteği_n"]
    ) * 100

    return out.sort_values(
        ["Yerine Gelme Puanı", "Sayı"],
        ascending=[False, True],
    )


def block_replacement_network(df, lookback=500):
    """
    Bir çekilişte bulunan ardışık blokların, sonraki çekilişte hangi bloklara
    dönüştüğünü hesaplar.
    """
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    sets = row_sets(work)
    transition_counts = Counter()
    source_counts = Counter()

    blocks_by_draw = [consecutive_pairs(s) for s in sets]

    for i in range(len(blocks_by_draw) - 1):
        current_blocks = blocks_by_draw[i]
        next_blocks = blocks_by_draw[i + 1]

        for source in current_blocks:
            source_counts[source] += 1
            for target in next_blocks:
                transition_counts[(source, target)] += 1

    rows = []
    for (source, target), count in transition_counts.most_common(300):
        total = max(source_counts[source], 1)
        rows.append(
            {
                "Kaynak blok": f"{source[0]}-{source[1]}",
                "Sonraki blok": f"{target[0]}-{target[1]}",
                "Geçiş adedi": count,
                "Koşullu oran %": round(count / total * 100, 2),
            }
        )

    return pd.DataFrame(rows)


def fatigue_table(df, recommendation_window=5):
    """
    Son çekilişlerde sık görünmüş ve uzun seri yapmış sayılara yorgunluk puanı verir.
    """
    recent = df.tail(min(int(recommendation_window), len(df)))
    recent_freq = frequency(recent).set_index("Sayı")["Frekans"]
    streaks = streak_table(df).set_index("Sayı")
    gaps_df = gaps(df).set_index("Sayı")

    rows = []
    for n in range(1, 81):
        recent_count = int(recent_freq.get(n, 0))
        current_streak = int(streaks.loc[n, "Mevcut seri"])
        longest = max(int(streaks.loc[n, "En uzun seri"]), 1)
        gap = int(gaps_df.loc[n, "Dinlenme"])

        fatigue_score = (
            0.55 * (recent_count / max(len(recent), 1))
            + 0.35 * (current_streak / longest)
            + 0.10 * (1.0 if gap == 0 else 0.0)
        ) * 100

        rows.append(
            {
                "Sayı": n,
                "Son pencere görülme": recent_count,
                "Mevcut seri": current_streak,
                "Dinlenme": gap,
                "Yorgunluk Puanı": round(fatigue_score, 2),
            }
        )

    out = pd.DataFrame(rows)
    q75 = out["Yorgunluk Puanı"].quantile(0.75)
    out["Durum"] = np.where(
        out["Yorgunluk Puanı"] >= q75,
        "Yorgun / azalt",
        "Normal",
    )
    return out.sort_values(
        ["Yorgunluk Puanı", "Sayı"],
        ascending=[False, True],
    )


def role_assignment_table(
    df,
    carry_scores,
    replacement_scores,
    target_time=None,
    lookback=300,
):
    """
    Her sayıya Taşıyıcı, Yerine Gelen, Blok Oyuncusu,
    Dinlenip Dönen veya Yorgun rolü verir.
    """
    smart = intelligent_score_table(
        df,
        target_time or str(df.iloc[-1].Saat),
    ).set_index("Sayı")
    gap_df = gaps(df).set_index("Sayı")
    cycle_df = return_cycle_table(df).set_index("Sayı")
    fatigue = fatigue_table(df).set_index("Sayı")

    # Blok üyeliği gücü
    subset = df.tail(min(int(lookback), len(df)))
    block_counts = Counter()
    for draw_set in row_sets(subset):
        for block in consecutive_pairs(draw_set):
            block_counts.update(block)

    carry_map = (
        carry_scores.set_index("Sayı")["Taşıma Puanı"].to_dict()
        if not carry_scores.empty
        else {}
    )
    replacement_map = (
        replacement_scores.set_index("Sayı")["Yerine Gelme Puanı"].to_dict()
        if not replacement_scores.empty
        else {}
    )

    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
    rows = []

    for n in range(1, 81):
        gap = float(gap_df.loc[n, "Dinlenme"])
        typical_rest = max(
            float(cycle_df.loc[n, "Ort. dönüş aralığı"]) - 1.0,
            0.0,
        )
        return_fit = float(
            np.exp(
                -abs(gap - typical_rest)
                / (typical_rest + 2.0)
            )
        )

        carry = float(carry_map.get(n, 0.0))
        replacement = float(replacement_map.get(n, 0.0))
        block_strength = float(block_counts.get(n, 0))
        tired = float(fatigue.loc[n, "Yorgunluk Puanı"])

        role_scores = {
            "Taşıyıcı": carry if n in latest_set else 0.0,
            "Yerine gelen": replacement if n not in latest_set else 0.0,
            "Blok oyuncusu": block_strength,
            "Dinlenip dönen": return_fit * 100 if n not in latest_set else 0.0,
            "Yorgun": tired,
        }

        role = max(role_scores, key=role_scores.get)
        rows.append(
            {
                "Sayı": n,
                "Rol": role,
                "Rol puanı": round(float(role_scores[role]), 2),
                "Taşıma": round(carry, 2),
                "Yerine gelme": round(replacement, 2),
                "Blok gücü": round(block_strength, 2),
                "Dönüş uyumu": round(return_fit * 100, 2),
                "Yorgunluk": round(tired, 2),
                "Genel güç": float(smart.loc[n, "Toplam Puan"]),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["Rol", "Rol puanı", "Sayı"],
        ascending=[True, False, True],
    )


def build_role_balanced_coupon(
    role_table,
    size=10,
    seed=0,
    previous_coupons=None,
):
    """
    Taşıyıcı, yerine gelen, blok oyuncusu ve dinlenip dönen rolleri
    dengeli biçimde karıştırarak kupon oluşturur.
    """
    previous_coupons = previous_coupons or []
    role_targets = {
        "Taşıyıcı": max(2, round(size * 0.30)),
        "Yerine gelen": max(2, round(size * 0.30)),
        "Blok oyuncusu": max(1, round(size * 0.20)),
        "Dinlenip dönen": max(1, size - (
            max(2, round(size * 0.30))
            + max(2, round(size * 0.30))
            + max(1, round(size * 0.20))
        )),
    }

    selected = []

    for role, target_count in role_targets.items():
        candidates = role_table[
            (role_table["Rol"] == role)
            & (role_table["Yorgunluk"] < 75)
        ].copy()

        if candidates.empty:
            continue

        candidates["Seçim"] = (
            candidates["Rol puanı"]
            + 0.20 * candidates["Genel güç"]
            + ((candidates["Sayı"] * 13 + seed * 17) % 41) / 100
        )

        for n in candidates.sort_values(
            "Seçim",
            ascending=False,
        )["Sayı"].astype(int):
            if n in selected:
                continue

            if previous_coupons and all(n in old for old in previous_coupons):
                continue

            selected.append(n)
            if sum(
                int(role_table.set_index("Sayı").loc[x, "Rol"] == role)
                for x in selected
                if x in set(role_table["Sayı"])
            ) >= target_count:
                break

    # Eksik kalırsa tüm güçlü, yorgun olmayan adaylardan tamamla.
    fallback = role_table[role_table["Yorgunluk"] < 80].copy()
    fallback["Seçim"] = (
        fallback["Rol puanı"]
        + 0.25 * fallback["Genel güç"]
        + ((fallback["Sayı"] * 17 + seed * 19) % 43) / 100
    )

    for n in fallback.sort_values("Seçim", ascending=False)["Sayı"].astype(int):
        if n not in selected:
            selected.append(n)
        if len(selected) >= size:
            break

    return sorted(selected[:size])


def generate_role_balanced_coupons(
    role_table,
    size,
    count,
):
    coupons = []
    attempts = 0

    while len(coupons) < count and attempts < count * 30:
        coupon = build_role_balanced_coupon(
            role_table,
            size=size,
            seed=attempts,
            previous_coupons=coupons,
        )
        if coupon and coupon not in coupons:
            if all(
                len(set(coupon) ^ set(old)) >= 4
                for old in coupons
            ):
                coupons.append(coupon)
        attempts += 1

    return coupons


def explain_role_coupon(coupon, role_table):
    indexed = role_table.set_index("Sayı")
    rows = []

    for n in coupon:
        row = indexed.loc[n]
        rows.append(
            {
                "Sayı": n,
                "Rol": row["Rol"],
                "Rol puanı": row["Rol puanı"],
                "Genel güç": row["Genel güç"],
                "Yorgunluk": row["Yorgunluk"],
            }
        )

    return pd.DataFrame(rows)



def behavior_feature_table(df):
    """
    Her çekiliş geçişini bir 'davranış parmak izi'ne çevirir.
    Tek tek sayılardan çok oyunun yapısını ölçer.
    """
    if len(df) < 2:
        return pd.DataFrame()

    sets = row_sets(df.reset_index(drop=True))
    rows = []

    for i in range(1, len(sets)):
        prev_set = sets[i - 1]
        cur_set = sets[i]

        carried = prev_set & cur_set
        blocks = consecutive_blocks(cur_set)
        pair_blocks = sum(len(block) - 1 for block in blocks)
        block3 = sum(max(0, len(block) - 2) for block in blocks)
        max_block = max([len(block) for block in blocks], default=1)

        band_counts = {
            name: sum(lo <= n <= hi for n in cur_set)
            for name, (lo, hi) in zip(BAND_NAMES, BANDS)
        }

        rows.append(
            {
                "Index": i,
                "Çekiliş": int(df.iloc[i].Cekilis_No),
                "Tarih": str(df.iloc[i].Tarih),
                "Saat": str(df.iloc[i].Saat),
                "SaatNo": int(str(df.iloc[i].Saat).split(":")[0]),
                "Taşıma": len(carried),
                "Yeni": 20 - len(carried),
                "2liBlokYoğunluğu": pair_blocks,
                "3lüBlokYoğunluğu": block3,
                "MaksBlok": max_block,
                **{f"Bant_{name}": value for name, value in band_counts.items()},
            }
        )

    return pd.DataFrame(rows)


def rolling_behavior_state(feature_df, end_pos=None, short_window=6, long_window=24):
    """
    Bir noktadaki kısa ve uzun dönem davranışı karşılaştırıp faz adı ve güven üretir.
    """
    if feature_df.empty:
        return {}, pd.DataFrame()

    if end_pos is None:
        end_pos = len(feature_df)

    end_pos = max(1, min(int(end_pos), len(feature_df)))
    short = feature_df.iloc[max(0, end_pos - short_window):end_pos]
    long = feature_df.iloc[max(0, end_pos - long_window):end_pos]

    cols = [
        "Taşıma",
        "Yeni",
        "2liBlokYoğunluğu",
        "3lüBlokYoğunluğu",
        "MaksBlok",
        "Bant_1-20",
        "Bant_21-40",
        "Bant_41-60",
        "Bant_61-80",
    ]

    short_mean = short[cols].mean()
    long_mean = long[cols].mean()
    hist = feature_df.iloc[:end_pos][cols]
    hist_std = hist.std(ddof=0).replace(0, 1.0)

    z = ((short_mean - long_mean) / hist_std).fillna(0.0)

    phase_scores = {
        "Taşıma Fazı": (
            1.20 * z["Taşıma"]
            - 0.70 * z["Yeni"]
            - 0.20 * z["2liBlokYoğunluğu"]
        ),
        "Yenilenme Fazı": (
            1.20 * z["Yeni"]
            - 0.75 * z["Taşıma"]
        ),
        "Blok Fazı": (
            0.80 * z["2liBlokYoğunluğu"]
            + 0.75 * z["3lüBlokYoğunluğu"]
            + 0.45 * z["MaksBlok"]
        ),
        "Üst Bant Fazı": (
            0.90 * z["Bant_61-80"]
            - 0.20 * z["Bant_1-20"]
        ),
        "Alt/Orta Bant Fazı": (
            0.55 * z["Bant_1-20"]
            + 0.55 * z["Bant_21-40"]
            - 0.40 * z["Bant_61-80"]
        ),
    }

    ordered = sorted(
        phase_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    phase, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0

    # Sinyal zayıfsa karışık faz.
    if top_score < 0.35:
        phase = "Karışık / Geçiş Fazı"

    separation = max(0.0, top_score - second_score)
    strength = max(0.0, top_score)
    confidence = min(
        100.0,
        38.0 + 24.0 * separation + 18.0 * strength
    )
    if phase == "Karışık / Geçiş Fazı":
        confidence = min(confidence, 58.0)

    metrics = pd.DataFrame(
        [
            {
                "Ölçüt": col,
                "Kısa dönem": round(float(short_mean[col]), 3),
                "Uzun dönem": round(float(long_mean[col]), 3),
                "Sapma": round(float(z[col]), 3),
            }
            for col in cols
        ]
    )

    return {
        "Faz": phase,
        "Güven": round(confidence, 1),
        "Kısa pencere": len(short),
        "Uzun pencere": len(long),
        "Skorlar": phase_scores,
    }, metrics


def hour_character_table(df):
    """
    Saat başına davranış karakterini çıkarır.
    Her saat yaklaşık 12 adet 5-dakikalık çekiliş içerir.
    """
    features = behavior_feature_table(df)
    if features.empty:
        return pd.DataFrame()

    rows = []
    for hour, group in features.groupby("SaatNo"):
        if len(group) < 3:
            continue

        rows.append(
            {
                "Saat": f"{int(hour):02d}:00-{int(hour):02d}:59",
                "Çekiliş": len(group),
                "Ort. taşıma": round(float(group["Taşıma"].mean()), 2),
                "Ort. yeni": round(float(group["Yeni"].mean()), 2),
                "2'li blok": round(float(group["2liBlokYoğunluğu"].mean()), 2),
                "3'lü blok": round(float(group["3lüBlokYoğunluğu"].mean()), 2),
                "1-20": round(float(group["Bant_1-20"].mean()), 2),
                "21-40": round(float(group["Bant_21-40"].mean()), 2),
                "41-60": round(float(group["Bant_41-60"].mean()), 2),
                "61-80": round(float(group["Bant_61-80"].mean()), 2),
            }
        )

    return pd.DataFrame(rows).sort_values("Saat")


def recent_phase_timeline(df, short_window=6, long_window=24, last_n=36):
    """Son çekilişlerde fazın ne zaman değiştiğini gösterir."""
    features = behavior_feature_table(df)
    if len(features) < 4:
        return pd.DataFrame()

    start = max(short_window, len(features) - int(last_n))
    rows = []

    for end_pos in range(start, len(features) + 1):
        state, _ = rolling_behavior_state(
            features,
            end_pos=end_pos,
            short_window=min(short_window, end_pos),
            long_window=min(long_window, end_pos),
        )
        last_row = features.iloc[end_pos - 1]
        rows.append(
            {
                "Çekiliş": int(last_row["Çekiliş"]),
                "Tarih": last_row["Tarih"],
                "Saat": last_row["Saat"],
                "Faz": state.get("Faz", ""),
                "Güven": state.get("Güven", 0),
            }
        )

    timeline = pd.DataFrame(rows)
    if timeline.empty:
        return timeline

    timeline["Faz değişti"] = (
        timeline["Faz"] != timeline["Faz"].shift(1)
    )
    return timeline.sort_values("Çekiliş", ascending=False)


def similar_state_next_scores(
    df,
    state_window=6,
    search_window=500,
    top_matches=25,
):
    """
    Bugünkü son davranış penceresine geçmişte en çok benzeyen pencereleri bulur
    ve o pencerelerden sonra gelen sayıları puanlar.
    """
    features = behavior_feature_table(df)
    if len(features) < state_window * 2 + 3:
        return pd.DataFrame(), pd.DataFrame()

    features = features.tail(min(int(search_window), len(features))).reset_index(drop=True)

    cols = [
        "Taşıma",
        "Yeni",
        "2liBlokYoğunluğu",
        "3lüBlokYoğunluğu",
        "MaksBlok",
        "Bant_1-20",
        "Bant_21-40",
        "Bant_41-60",
        "Bant_61-80",
    ]

    means = features[cols].mean()
    stds = features[cols].std(ddof=0).replace(0, 1.0)

    current_slice = features.iloc[-state_window:]
    current_vec = ((current_slice[cols].mean() - means) / stds).to_numpy(float)

    matches = []
    # Son pencere ve hemen komşularını dışarıda bırak.
    max_end = len(features) - state_window - 1

    for end_pos in range(state_window, max_end + 1):
        window_slice = features.iloc[end_pos - state_window:end_pos]
        vec = ((window_slice[cols].mean() - means) / stds).to_numpy(float)
        distance = float(np.sqrt(np.mean((vec - current_vec) ** 2)))

        target_feature_row = features.iloc[end_pos]
        draw_index = int(target_feature_row["Index"])
        if draw_index >= len(df):
            continue

        matches.append(
            {
                "Mesafe": distance,
                "Benzerlik %": round(100.0 / (1.0 + distance), 2),
                "Sonraki Çekiliş": int(df.iloc[draw_index].Cekilis_No),
                "Tarih": str(df.iloc[draw_index].Tarih),
                "Saat": str(df.iloc[draw_index].Saat),
                "_draw_index": draw_index,
            }
        )

    match_df = pd.DataFrame(matches)
    if match_df.empty:
        return match_df, pd.DataFrame()

    match_df = match_df.sort_values(
        ["Mesafe", "Sonraki Çekiliş"],
        ascending=[True, True],
    ).head(int(top_matches))

    weighted_counts = Counter()
    total_weight = 0.0

    for _, match in match_df.iterrows():
        draw_index = int(match["_draw_index"])
        weight = 1.0 / (0.15 + float(match["Mesafe"]))
        total_weight += weight
        draw_nums = [int(df.iloc[draw_index][c]) for c in NUM_COLS]
        for n in draw_nums:
            weighted_counts[n] += weight

    score_rows = []
    for n in range(1, 81):
        raw = float(weighted_counts.get(n, 0.0))
        score_rows.append(
            {
                "Sayı": n,
                "Benzer Durum Puanı": round(
                    raw / max(total_weight, 1e-9) * 100,
                    2,
                ),
            }
        )

    score_df = pd.DataFrame(score_rows).sort_values(
        ["Benzer Durum Puanı", "Sayı"],
        ascending=[False, True],
    )

    return (
        match_df.drop(columns=["_draw_index"]),
        score_df,
    )


def predicted_block_number_scores(df, lookback=400):
    """
    Son çekilişteki bloklardan sonra geçmişte hangi blokların geldiğini kullanarak
    sayı bazında blok-geçiş puanı üretir.
    """
    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
    current_blocks = consecutive_pairs(latest_set)

    rows = [{"Sayı": n, "Blok Geçiş Puanı": 0.0} for n in range(1, 81)]
    if not current_blocks:
        return pd.DataFrame(rows)

    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    sets = row_sets(work)
    blocks_by_draw = [consecutive_pairs(s) for s in sets]

    target_counts = Counter()
    source_cases = Counter()

    for i in range(len(blocks_by_draw) - 1):
        current = set(blocks_by_draw[i])
        nxt = blocks_by_draw[i + 1]
        for source in current_blocks:
            if source in current:
                source_cases[source] += 1
                target_counts.update(nxt)

    number_score = Counter()
    for block, count in target_counts.items():
        a, b = block
        number_score[a] += count
        number_score[b] += count

    max_score = max(number_score.values(), default=1)
    return pd.DataFrame(
        [
            {
                "Sayı": n,
                "Blok Geçiş Puanı": round(
                    number_score.get(n, 0) / max_score * 100,
                    2,
                ),
            }
            for n in range(1, 81)
        ]
    )


def live_dynamic_weights(phase):
    """Faza göre motor ağırlıklarını otomatik değiştirir."""
    base = {
        "Taşıma": 0.15,
        "Yerine": 0.15,
        "Blok": 0.12,
        "Dönüş": 0.12,
        "Saat": 0.10,
        "Genel": 0.12,
        "Benzer": 0.16,
        "Kısaİvme": 0.08,
    }

    if "Taşıma" in phase:
        base.update({
            "Taşıma": 0.25,
            "Yerine": 0.08,
            "Benzer": 0.15,
        })
    elif "Yenilenme" in phase:
        base.update({
            "Taşıma": 0.08,
            "Yerine": 0.25,
            "Dönüş": 0.15,
        })
    elif "Blok" in phase:
        base.update({
            "Blok": 0.24,
            "Taşıma": 0.12,
            "Benzer": 0.15,
        })
    elif "Üst Bant" in phase or "Alt/Orta" in phase:
        base.update({
            "Saat": 0.16,
            "Benzer": 0.18,
        })

    total = sum(base.values())
    return {key: value / total for key, value in base.items()}


def live_number_score_table(
    df,
    target_time=None,
    analysis_window=500,
    state_window=6,
):
    """
    Bütün motorları tek canlı kararda birleştirir.
    Ağırlıklar mevcut faza göre değişir.
    """
    features = behavior_feature_table(df)
    state, _ = rolling_behavior_state(
        features,
        short_window=min(6, max(2, len(features))),
        long_window=min(24, max(4, len(features))),
    )
    phase = state.get("Faz", "Karışık / Geçiş Fazı")
    weights = live_dynamic_weights(phase)

    carry = carryover_number_scores(
        df,
        target_time or str(df.iloc[-1].Saat),
        analysis_window,
    )
    replacement = latest_replacement_candidates(
        df,
        analysis_window,
    )
    block = predicted_block_number_scores(
        df,
        analysis_window,
    )
    _, similar = similar_state_next_scores(
        df,
        state_window=state_window,
        search_window=analysis_window,
        top_matches=25,
    )
    smart = intelligent_score_table(
        df,
        target_time or str(df.iloc[-1].Saat),
    )
    gaps_df = gaps(df).set_index("Sayı")
    cycles = return_cycle_table(df).set_index("Sayı")
    fatigue = fatigue_table(df, recommendation_window=5).set_index("Sayı")
    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)

    # Kısa dönem ivmesi: son 5'e karşı son 25.
    f5 = frequency(df.tail(min(5, len(df)))).set_index("Sayı")["Frekans"] / max(min(5, len(df)), 1)
    f25 = frequency(df.tail(min(25, len(df)))).set_index("Sayı")["Frekans"] / max(min(25, len(df)), 1)

    carry_map = carry.set_index("Sayı")["Taşıma Puanı"].to_dict() if not carry.empty else {}
    replacement_map = (
        replacement.set_index("Sayı")["Yerine Gelme Puanı"].to_dict()
        if not replacement.empty else {}
    )
    block_map = block.set_index("Sayı")["Blok Geçiş Puanı"].to_dict() if not block.empty else {}
    similar_map = (
        similar.set_index("Sayı")["Benzer Durum Puanı"].to_dict()
        if not similar.empty else {}
    )
    smart_idx = smart.set_index("Sayı")

    rows = []
    for n in range(1, 81):
        gap = float(gaps_df.loc[n, "Dinlenme"])
        expected_rest = max(
            float(cycles.loc[n, "Ort. dönüş aralığı"]) - 1.0,
            0.0,
        )
        return_fit = float(
            np.exp(
                -abs(gap - expected_rest)
                / (expected_rest + 2.0)
            )
        ) * 100.0

        rows.append(
            {
                "Sayı": n,
                "Taşıma": float(carry_map.get(n, 0.0)) if n in latest_set else 0.0,
                "Yerine": float(replacement_map.get(n, 0.0)) if n not in latest_set else 0.0,
                "Blok": float(block_map.get(n, 0.0)),
                "Dönüş": return_fit if n not in latest_set else max(0.0, return_fit * 0.35),
                "Saat": float(smart_idx.loc[n, "Saat oranı"]) * 100.0,
                "Genel": float(smart_idx.loc[n, "Toplam Puan"]),
                "Benzer": float(similar_map.get(n, 0.0)),
                "Kısaİvme": max(
                    0.0,
                    float(f5.get(n, 0.0) - f25.get(n, 0.0))
                ) * 100.0,
                "Yorgunluk": float(fatigue.loc[n, "Yorgunluk Puanı"]),
                "Son elde": n in latest_set,
            }
        )

    out = pd.DataFrame(rows)

    # Her pozitif bileşeni normalize et.
    for col in [
        "Taşıma",
        "Yerine",
        "Blok",
        "Dönüş",
        "Saat",
        "Genel",
        "Benzer",
        "Kısaİvme",
    ]:
        out[col + "_n"] = normalized_series(out[col])

    out["Canlı Puan"] = 0.0
    for component, weight in weights.items():
        out["Canlı Puan"] += out[component + "_n"] * weight

    # Yorgunluğu doğrudan ceza olarak uygula.
    fatigue_norm = normalized_series(out["Yorgunluk"])
    out["Canlı Puan"] = (
        out["Canlı Puan"] * 100.0
        - 10.0 * fatigue_norm
    ).clip(0, 100).round(2)

    # Rol
    def role_of(row):
        components = {
            "Taşıyıcı": row["Taşıma"],
            "Yerine gelen": row["Yerine"],
            "Blok": row["Blok"],
            "Dinlenip dönen": row["Dönüş"],
            "Benzer durum": row["Benzer"],
        }
        role = max(components, key=components.get)
        if row["Yorgunluk"] >= out["Yorgunluk"].quantile(0.85):
            return "Yorgun"
        return role

    out["Canlı Rol"] = out.apply(role_of, axis=1)

    return (
        out.sort_values(
            ["Canlı Puan", "Sayı"],
            ascending=[False, True],
        ),
        state,
        weights,
    )


def generate_live_coupons(score_table, size=7, count=4):
    """Canlı puanlardan birbirinden ayrışan, bant dengeli kuponlar üretir."""
    coupons = []
    attempts = 0

    while len(coupons) < count and attempts < count * 40:
        work = score_table.copy()
        work["Seçim"] = (
            work["Canlı Puan"]
            + ((work["Sayı"] * (17 + attempts) + attempts * 13) % 47) / 100
        )

        # Önceki kuponlarda aşırı kullanılan sayıları bastır.
        usage = Counter(n for coupon in coupons for n in coupon)
        work["Seçim"] -= work["Sayı"].map(lambda n: usage.get(int(n), 0) * 3.0)

        selected = []
        band_counts = [0, 0, 0, 0]
        max_per_band = max(2, int(np.ceil(size / 3)))

        for _, row in work.sort_values("Seçim", ascending=False).iterrows():
            n = int(row["Sayı"])
            band_idx = next(
                i for i, (lo, hi) in enumerate(BANDS)
                if lo <= n <= hi
            )
            if band_counts[band_idx] >= max_per_band:
                continue

            trial = set(selected + [n])
            if (
                {n - 2, n - 1, n}.issubset(trial)
                or {n - 1, n, n + 1}.issubset(trial)
                or {n, n + 1, n + 2}.issubset(trial)
            ):
                # Blok puanı çok yüksekse üçlü blok yine kabul edilebilir.
                if float(row["Blok"]) < score_table["Blok"].quantile(0.85):
                    continue

            selected.append(n)
            band_counts[band_idx] += 1
            if len(selected) >= size:
                break

        coupon = sorted(selected[:size])
        if len(coupon) == size and coupon not in coupons:
            if all(len(set(coupon) ^ set(old)) >= 4 for old in coupons):
                coupons.append(coupon)

        attempts += 1

    return coupons


def explain_live_coupon(coupon, score_table):
    indexed = score_table.set_index("Sayı")
    rows = []
    for n in coupon:
        row = indexed.loc[n]
        strongest = sorted(
            [
                ("taşıma", row["Taşıma"]),
                ("yerine", row["Yerine"]),
                ("blok", row["Blok"]),
                ("dönüş", row["Dönüş"]),
                ("saat", row["Saat"]),
                ("benzer durum", row["Benzer"]),
            ],
            key=lambda item: item[1],
            reverse=True,
        )[:3]

        rows.append(
            {
                "Sayı": n,
                "Canlı Puan": row["Canlı Puan"],
                "Rol": row["Canlı Rol"],
                "En güçlü nedenler": ", ".join(
                    f"{name}:{value:.1f}"
                    for name, value in strongest
                ),
                "Yorgunluk": round(float(row["Yorgunluk"]), 1),
            }
        )
    return pd.DataFrame(rows)


def live_backtest(df, coupon_size=7, test_count=20, analysis_window=300):
    """
    Walk-forward test: her noktada yalnız o ana kadarki veriyi kullanır.
    Mobil performans için test sayısı sınırlıdır.
    """
    if len(df) < 80:
        return pd.DataFrame()

    test_count = int(min(test_count, max(1, len(df) - 60)))
    start = len(df) - test_count
    rows = []

    for i in range(start, len(df)):
        train = df.iloc[:i].copy()
        if len(train) < 60:
            continue

        try:
            score_table, state, _ = live_number_score_table(
                train,
                target_time=str(train.iloc[-1].Saat),
                analysis_window=min(analysis_window, len(train)),
                state_window=6,
            )
            coupons = generate_live_coupons(
                score_table,
                size=coupon_size,
                count=1,
            )
            if not coupons:
                continue

            coupon = coupons[0]
            actual = set(int(df.iloc[i][c]) for c in NUM_COLS)
            hits = sorted(set(coupon) & actual)

            rows.append(
                {
                    "Çekiliş": int(df.iloc[i].Cekilis_No),
                    "Faz": state.get("Faz", ""),
                    "Kupon": " - ".join(map(str, coupon)),
                    "İsabet": len(hits),
                    "Tutan": " - ".join(map(str, hits)),
                }
            )
        except Exception:
            continue

    return pd.DataFrame(rows)


def normalized_series(values):
    series = pd.Series(values, dtype=float)
    lo, hi = float(series.min()), float(series.max())
    if hi <= lo:
        return pd.Series(np.full(len(series), 0.5), index=series.index)
    return (series - lo) / (hi - lo)


def repeat_probability(df):
    sets = row_sets(df)
    cases = Counter()
    hits = Counter()

    for i in range(len(sets) - 1):
        for n in sets[i]:
            cases[n] += 1
            if n in sets[i + 1]:
                hits[n] += 1

    return {
        n: hits[n] / cases[n] if cases[n] else 0.0
        for n in range(1, 81)
    }


def return_cycle_table(df):
    positions = defaultdict(list)
    for i, draw_set in enumerate(row_sets(df)):
        for n in draw_set:
            positions[n].append(i)

    rows = []
    for n in range(1, 81):
        pos = positions[n]
        intervals = [pos[i] - pos[i - 1] for i in range(1, len(pos))]
        rests = [max(0, x - 1) for x in intervals]
        current_gap = len(df) - 1 - pos[-1] if pos else len(df)
        rows.append({
            "Sayı": n,
            "Görülme": len(pos),
            "Mevcut dinlenme": current_gap,
            "Ort. dönüş aralığı": round(float(np.mean(intervals)), 2) if intervals else 0,
            "Medyan dönüş": round(float(np.median(intervals)), 2) if intervals else 0,
            "En uzun dinlenme": max(rests) if rests else 0,
            "Son 10 dönüş": " - ".join(map(str, intervals[-10:])),
        })
    return pd.DataFrame(rows)


def hour_number_rates(df, target_time):
    if df.empty:
        return {n: 0.0 for n in range(1, 81)}

    target_minutes = int(target_time.split(":")[0]) * 60 + int(target_time.split(":")[1])
    minutes = df["Saat"].map(
        lambda x: int(str(x).split(":")[0]) * 60 + int(str(x).split(":")[1])
    )
    # Aynı saat çevresindeki ±30 dakikalık çekilişler.
    mask = (minutes - target_minutes).abs() <= 30
    subset = df[mask]
    if len(subset) < 5:
        subset = df[df["Saat"].map(period_name) == period_name(target_time)]

    freq = frequency(subset).set_index("Sayı")["Frekans"] if not subset.empty else pd.Series(dtype=float)
    denominator = max(len(subset), 1)
    return {n: float(freq.get(n, 0)) / denominator for n in range(1, 81)}


def neighbor_block_strength(df, window):
    subset = df.tail(window)
    neighbor = Counter()
    block_member = Counter()

    for draw_set in row_sets(subset):
        for n in draw_set:
            if n - 1 in draw_set:
                neighbor[n] += 1
            if n + 1 in draw_set:
                neighbor[n] += 1
        for block in consecutive_blocks(draw_set):
            for n in block:
                block_member[n] += len(block) - 1

    return {
        n: neighbor[n] + block_member[n]
        for n in range(1, 81)
    }


def intelligent_score_table(df, target_time=None):
    windows = [10, 25, 50, 100]
    rows = pd.DataFrame({"Sayı": range(1, 81)})

    for w in windows:
        subset = df.tail(min(w, len(df)))
        freq = frequency(subset).set_index("Sayı")["Frekans"] / max(len(subset), 1)
        rows[f"Son {w}"] = [float(freq.get(n, 0)) for n in range(1, 81)]

    gap_df = gaps(df).set_index("Sayı")
    cycle_df = return_cycle_table(df).set_index("Sayı")
    repeat = repeat_probability(df)
    pair = score_numbers(df, min(100, len(df))).set_index("Sayı")["Bağ gücü"]
    block_strength = neighbor_block_strength(df, min(100, len(df)))

    if target_time is None:
        target_time = str(df.iloc[-1].Saat)
    hour_rates = hour_number_rates(df, target_time)

    rows["Dinlenme"] = [int(gap_df.loc[n, "Dinlenme"]) for n in range(1, 81)]
    rows["Ort. dönüş"] = [float(cycle_df.loc[n, "Ort. dönüş aralığı"]) for n in range(1, 81)]
    rows["Tekrar oranı"] = [float(repeat[n]) for n in range(1, 81)]
    rows["Birlikte gelme"] = [float(pair.get(n, 0)) for n in range(1, 81)]
    rows["Saat oranı"] = [float(hour_rates[n]) for n in range(1, 81)]
    rows["Blok puanı"] = [float(block_strength[n]) for n in range(1, 81)]

    # Dinlenme/dönüş uyumu: mevcut dinlenme, o sayının tipik dönüş aralığına yaklaştıkça artar.
    expected_rest = (rows["Ort. dönüş"] - 1).clip(lower=0)
    rows["Dönüş uyumu"] = np.exp(
        -np.abs(rows["Dinlenme"] - expected_rest) / (expected_rest + 2)
    )

    component_weights = {
        "Son 10": 0.13,
        "Son 25": 0.12,
        "Son 50": 0.10,
        "Son 100": 0.08,
        "Dönüş uyumu": 0.14,
        "Tekrar oranı": 0.10,
        "Birlikte gelme": 0.13,
        "Saat oranı": 0.10,
        "Blok puanı": 0.10,
    }

    normalized = {}
    for col in component_weights:
        normalized[col] = normalized_series(rows[col])

    rows["Toplam Puan"] = 0.0
    for col, weight in component_weights.items():
        rows["Toplam Puan"] += normalized[col] * weight

    rows["Toplam Puan"] = (rows["Toplam Puan"] * 100).round(2)
    rows["Durum"] = pd.cut(
        rows["Toplam Puan"],
        bins=[-1, 45, 60, 75, 101],
        labels=["Zayıf", "Orta", "Güçlü", "Çok güçlü"],
    ).astype(str)

    display_cols = [
        "Sayı", "Toplam Puan", "Durum", "Son 10", "Son 25", "Son 50",
        "Son 100", "Dinlenme", "Ort. dönüş", "Dönüş uyumu",
        "Tekrar oranı", "Saat oranı", "Birlikte gelme", "Blok puanı"
    ]
    return rows[display_cols].sort_values(
        ["Toplam Puan", "Sayı"], ascending=[False, True]
    )


def balanced_smart_coupon(score_df, size, seed_shift=0):
    work = score_df.copy()
    # Küçük çeşitlilik için deterministik, kontrollü bir kaydırma.
    work["Seçim Puanı"] = work["Toplam Puan"] + (
        ((work["Sayı"] * 17 + seed_shift * 13) % 19) / 100
    )
    work = work.sort_values("Seçim Puanı", ascending=False)

    selected = []
    band_counts = [0, 0, 0, 0]
    max_per_band = max(2, int(np.ceil(size / 3)))

    for n in work["Sayı"].astype(int):
        band_idx = next(i for i, (lo, hi) in enumerate(BANDS) if lo <= n <= hi)
        # Aynı banttan aşırı yığılmayı ve uzun ardışık zinciri sınırla.
        creates_long_run = any(
            {n - 2, n - 1}.issubset(selected)
            or {n - 1, n + 1}.issubset(selected)
            or {n + 1, n + 2}.issubset(selected)
            for _ in [0]
        )
        if band_counts[band_idx] >= max_per_band or creates_long_run:
            continue
        selected.append(n)
        band_counts[band_idx] += 1
        if len(selected) == size:
            break

    # Kısıtlar yüzünden eksik kalırsa puan sırasından tamamla.
    if len(selected) < size:
        for n in work["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected) == size:
                break

    return sorted(selected)


def explain_coupon(coupon, score_df):
    indexed = score_df.set_index("Sayı")
    rows = []
    for n in coupon:
        row = indexed.loc[n]
        reasons = []
        if row["Son 10"] >= score_df["Son 10"].quantile(0.70):
            reasons.append("son 10 güçlü")
        if row["Dönüş uyumu"] >= score_df["Dönüş uyumu"].quantile(0.70):
            reasons.append("dönüş zamanı yakın")
        if row["Tekrar oranı"] >= score_df["Tekrar oranı"].quantile(0.70):
            reasons.append("tekrar oranı güçlü")
        if row["Saat oranı"] >= score_df["Saat oranı"].quantile(0.70):
            reasons.append("saat uyumu")
        if row["Birlikte gelme"] >= score_df["Birlikte gelme"].quantile(0.70):
            reasons.append("bağ gücü")
        if row["Blok puanı"] >= score_df["Blok puanı"].quantile(0.70):
            reasons.append("blok desteği")
        rows.append({
            "Sayı": n,
            "Puan": row["Toplam Puan"],
            "Seçilme nedeni": ", ".join(reasons) or "dengeli toplam puan",
        })
    return pd.DataFrame(rows)


def historical_coupon_test(df, coupon):
    coupon_set = set(coupon)
    rows = []
    for _, row in df.iterrows():
        actual = set(int(row[c]) for c in NUM_COLS)
        hits = sorted(coupon_set & actual)
        rows.append({
            "Çekiliş": int(row.Cekilis_No),
            "Tarih": row.Tarih,
            "Saat": row.Saat,
            "İsabet": len(hits),
            "Tutan sayılar": " - ".join(map(str, hits)),
        })
    return pd.DataFrame(rows)


def hit_distribution(test_df, coupon_size):
    counts = test_df["İsabet"].value_counts().reindex(
        range(coupon_size + 1), fill_value=0
    ).sort_index()
    return pd.DataFrame({
        "İsabet": counts.index,
        "Adet": counts.values,
        "Oran %": (counts.values / max(len(test_df), 1) * 100).round(2),
    })


def weakest_coupon_replacement(coupon, score_df):
    indexed = score_df.set_index("Sayı")
    weakest = min(coupon, key=lambda n: indexed.loc[n, "Toplam Puan"])
    alternatives = [
        int(n) for n in score_df["Sayı"]
        if int(n) not in coupon
    ][:5]
    return weakest, alternatives

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

st.title("🎯 Hızlı On Ultimate AI Studio V18.5.8")
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

df = repair_calendar_sequence_v18(merge_data(base_df, st.session_state.extra_df))
df, corrected_draw_count_v1852 = apply_verified_draw_numbers_v1852(df)
if corrected_draw_count_v1852:
    st.info(
        f"🔧 Resmî takvime göre {corrected_draw_count_v1852} çekiliş numarası düzeltildi. "
        "Diğer veriler değiştirilmedi."
    )

if df.empty:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

latest = df.iloc[-1]
missing = missing_draws(df)

top_left, top_right = st.columns(2)
top_left.metric("Toplam çekiliş", f"{len(df)}")
top_right.metric("Son çekiliş", f"{int(latest.Cekilis_No)}")

bottom_left, bottom_right = st.columns(2)
bottom_left.metric("Son tarih/saat", f"{latest.Tarih} {latest.Saat}")
bottom_right.metric("Eksik çekiliş adedi", f"{len(missing)}")

if missing:
    with st.expander("Eksik çekiliş numaralarını göster"):
        st.write(", ".join(map(str, missing[:200])))
        if len(missing) > 200:
            st.caption(f"İlk 200 numara gösteriliyor. Toplam eksik: {len(missing)}")
else:
    st.success("Çekiliş numaraları kesintisiz.")

with st.sidebar:
    window = st.slider("Analiz penceresi", 50, max(50, len(df)), min(500, len(df)), 50)

adf = df.tail(window)



def ten_band_name(number):
    """1-80 aralığını 8 adet 10'luk bölgeye ayırır."""
    number = int(number)
    low = ((number - 1) // 10) * 10 + 1
    high = min(low + 9, 80)
    return f"{low}-{high}"


def draw_shape_metrics(prev_set, cur_set):
    """İki ardışık çekilişten çekiliş iskeleti özellikleri çıkarır."""
    prev_set = set(int(x) for x in prev_set)
    cur_set = set(int(x) for x in cur_set)
    carried = prev_set & cur_set
    blocks = consecutive_blocks(cur_set)

    region_counts = Counter(ten_band_name(n) for n in cur_set)
    return {
        "Taşıma": len(carried),
        "Yeni": 20 - len(carried),
        "2liBlok": sum(max(0, len(block) - 1) for block in blocks),
        "3luBlok": sum(max(0, len(block) - 2) for block in blocks),
        "MaksBlok": max([len(block) for block in blocks], default=1),
        **{f"Bölge_{name}": region_counts.get(name, 0)
           for name in [f"{i}-{i+9}" for i in range(1, 80, 10)]},
    }


def skeleton_forecast(df, state_window=6, search_window=500, top_matches=25):
    """
    Bugünkü son davranış penceresine benzeyen tarihsel durumların
    hemen sonraki çekilişlerinden beklenen 'çekiliş iskeleti'ni üretir.
    """
    matches, _ = similar_state_next_scores(
        df,
        state_window=state_window,
        search_window=search_window,
        top_matches=top_matches,
    )

    if matches.empty:
        return {}, pd.DataFrame(), pd.DataFrame()

    draw_to_index = {
        int(row.Cekilis_No): idx
        for idx, row in df.reset_index(drop=True).iterrows()
    }

    weighted = Counter()
    total_weight = 0.0
    samples = []

    for _, match in matches.iterrows():
        draw_no = int(match["Sonraki Çekiliş"])
        idx = draw_to_index.get(draw_no)
        if idx is None or idx <= 0:
            continue

        prev_set = set(int(df.reset_index(drop=True).iloc[idx - 1][c]) for c in NUM_COLS)
        cur_set = set(int(df.reset_index(drop=True).iloc[idx][c]) for c in NUM_COLS)
        metrics = draw_shape_metrics(prev_set, cur_set)

        sim = float(match["Benzerlik %"])
        weight = max(sim, 1.0) / 100.0
        total_weight += weight

        for key, value in metrics.items():
            weighted[key] += float(value) * weight

        sample_row = {
            "Çekiliş": draw_no,
            "Benzerlik %": sim,
            **metrics,
        }
        samples.append(sample_row)

    if total_weight <= 0:
        return {}, pd.DataFrame(), pd.DataFrame()

    forecast = {
        key: round(value / total_weight, 2)
        for key, value in weighted.items()
    }

    # En aktif iki bölge
    region_pairs = [
        (name.replace("Bölge_", ""), value)
        for name, value in forecast.items()
        if name.startswith("Bölge_")
    ]
    region_pairs.sort(key=lambda x: x[1], reverse=True)
    forecast["Aktif Bölge 1"] = region_pairs[0][0] if region_pairs else "-"
    forecast["Aktif Bölge 2"] = region_pairs[1][0] if len(region_pairs) > 1 else "-"

    region_table = pd.DataFrame(
        [
            {
                "Bölge": name,
                "Beklenen sayı": round(value, 2),
            }
            for name, value in region_pairs
        ]
    )

    return forecast, pd.DataFrame(samples).sort_values(
        "Benzerlik %",
        ascending=False,
    ), region_table


def region_probability_scores(df, state_window=6, search_window=500, top_matches=25):
    """
    Benzer tarihsel durumların sonraki çekilişlerinden sayı ve bölge puanı üretir.
    """
    matches, _ = similar_state_next_scores(
        df,
        state_window=state_window,
        search_window=search_window,
        top_matches=top_matches,
    )

    if matches.empty:
        return pd.DataFrame(
            {"Sayı": range(1, 81), "Bölge Puanı": [0.0] * 80}
        )

    draw_to_index = {
        int(row.Cekilis_No): idx
        for idx, row in df.reset_index(drop=True).iterrows()
    }

    region_weight = Counter()
    number_weight = Counter()
    total_weight = 0.0

    for _, match in matches.iterrows():
        draw_no = int(match["Sonraki Çekiliş"])
        idx = draw_to_index.get(draw_no)
        if idx is None:
            continue

        weight = max(float(match["Benzerlik %"]), 1.0) / 100.0
        total_weight += weight
        nums = [int(df.reset_index(drop=True).iloc[idx][c]) for c in NUM_COLS]

        for n in nums:
            number_weight[n] += weight
            region_weight[ten_band_name(n)] += weight

    max_region = max(region_weight.values(), default=1.0)
    max_num = max(number_weight.values(), default=1.0)

    rows = []
    for n in range(1, 81):
        region = ten_band_name(n)
        score = (
            0.65 * region_weight.get(region, 0.0) / max_region
            + 0.35 * number_weight.get(n, 0.0) / max_num
        ) * 100.0
        rows.append(
            {
                "Sayı": n,
                "Bölge": region,
                "Bölge Puanı": round(score, 2),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["Bölge Puanı", "Sayı"],
        ascending=[False, True],
    )


def elimination_table_v16(df, live_scores, region_scores):
    """
    'Neyi seçelim?' kadar 'neyi elemeliyiz?' sorusunu puanlar.
    Yorgunluk + zayıf canlı sinyal + zayıf bölge + aşırı kısa dönem kullanım.
    """
    recent5 = frequency(df.tail(min(5, len(df)))).set_index("Sayı")["Frekans"]
    recent20 = frequency(df.tail(min(20, len(df)))).set_index("Sayı")["Frekans"]

    live_idx = live_scores.set_index("Sayı")
    region_idx = region_scores.set_index("Sayı")

    rows = []
    for n in range(1, 81):
        short_rate = float(recent5.get(n, 0)) / max(min(5, len(df)), 1)
        long_rate = float(recent20.get(n, 0)) / max(min(20, len(df)), 1)
        overuse = max(0.0, short_rate - long_rate) * 100.0

        live = float(live_idx.loc[n, "Canlı Puan"])
        fatigue = float(live_idx.loc[n, "Yorgunluk"])
        region = float(region_idx.loc[n, "Bölge Puanı"])

        elimination = (
            0.38 * fatigue
            + 0.27 * (100.0 - live)
            + 0.20 * (100.0 - region)
            + 0.15 * overuse
        )
        rows.append(
            {
                "Sayı": n,
                "Eleme Puanı": round(min(max(elimination, 0.0), 100.0), 2),
                "Canlı Puan": live,
                "Yorgunluk": fatigue,
                "Bölge Puanı": region,
                "Aşırı Kullanım": round(overuse, 2),
            }
        )

    out = pd.DataFrame(rows)
    q80 = out["Eleme Puanı"].quantile(0.80)
    q55 = out["Eleme Puanı"].quantile(0.55)
    out["Eleme Durumu"] = np.where(
        out["Eleme Puanı"] >= q80,
        "Güçlü ele",
        np.where(
            out["Eleme Puanı"] >= q55,
            "Dikkat",
            "Tutulabilir",
        ),
    )
    return out.sort_values(
        ["Eleme Puanı", "Sayı"],
        ascending=[False, True],
    )


def role_table_v16(live_scores, region_scores, elimination_scores):
    """
    Her sayıya mevcut durumda tek baskın rol verir.
    """
    live = live_scores.set_index("Sayı")
    region = region_scores.set_index("Sayı")
    elimination = elimination_scores.set_index("Sayı")

    rows = []
    for n in range(1, 81):
        row = live.loc[n]

        role_scores = {
            "Taşıyıcı": float(row["Taşıma"]),
            "Yerine Gelen": float(row["Yerine"]),
            "Blok Tamamlayıcı": float(row["Blok"]),
            "Dinlenip Dönen": float(row["Dönüş"]),
            "Benzer Durum": float(row["Benzer"]),
            "Aktif Bölge": float(region.loc[n, "Bölge Puanı"]),
        }
        role = max(role_scores, key=role_scores.get)
        role_score = float(role_scores[role])

        if float(elimination.loc[n, "Eleme Puanı"]) >= 78:
            role = "Yorgun / Ele"
            role_score = float(elimination.loc[n, "Eleme Puanı"])

        rows.append(
            {
                "Sayı": n,
                "Rol": role,
                "Rol Puanı": round(role_score, 2),
                "Canlı Puan": float(row["Canlı Puan"]),
                "Eleme Puanı": float(elimination.loc[n, "Eleme Puanı"]),
                "Bölge Puanı": float(region.loc[n, "Bölge Puanı"]),
                "Son Elde": bool(row["Son elde"]),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["Rol", "Rol Puanı", "Canlı Puan"],
        ascending=[True, False, False],
    )


def component_reliability_backtest_v16(
    df,
    coupon_size=7,
    test_count=10,
    analysis_window=250,
):
    """
    Alt motorların son gerçek sonuçlarda top-N isabetini ölçer.
    Her testte yalnızca o ana kadar bilinen veri kullanılır.
    """
    if len(df) < 80:
        return pd.DataFrame(), {}

    components = [
        "Taşıma",
        "Yerine",
        "Blok",
        "Dönüş",
        "Saat",
        "Benzer",
        "Kısaİvme",
    ]
    hit_sums = Counter()
    tests = 0

    start = max(60, len(df) - int(test_count))

    for i in range(start, len(df)):
        train = df.iloc[:i].copy()
        if len(train) < 60:
            continue

        try:
            scores, _, _ = live_number_score_table(
                train,
                target_time=str(train.iloc[-1].Saat),
                analysis_window=min(int(analysis_window), len(train)),
                state_window=6,
            )
        except Exception:
            continue

        actual = set(int(df.iloc[i][c]) for c in NUM_COLS)
        for component in components:
            picks = set(
                scores.sort_values(
                    [component, "Sayı"],
                    ascending=[False, True],
                ).head(int(coupon_size))["Sayı"].astype(int)
            )
            hit_sums[component] += len(picks & actual)

        tests += 1

    if tests == 0:
        return pd.DataFrame(), {}

    avg_hits = {
        comp: hit_sums[comp] / tests
        for comp in components
    }
    baseline = sum(avg_hits.values()) / max(len(avg_hits), 1)

    raw_weights = {
        comp: max(avg / max(baseline, 1e-9), 0.35)
        for comp, avg in avg_hits.items()
    }
    total = sum(raw_weights.values())
    reliability = {
        comp: value / total
        for comp, value in raw_weights.items()
    }

    table = pd.DataFrame(
        [
            {
                "Motor": comp,
                "Test": tests,
                "Ort. top-N isabet": round(avg_hits[comp], 3),
                "Güven ağırlığı %": round(reliability[comp] * 100, 2),
            }
            for comp in components
        ]
    ).sort_values(
        "Güven ağırlığı %",
        ascending=False,
    )

    return table, reliability


def v16_master_score_table(
    df,
    target_time=None,
    analysis_window=500,
    state_window=6,
    reliability=None,
):
    """
    V16 ana karar tablosu:
    Canlı skor + çekiliş iskeleti + aktif bölge + eleme + meta güven.
    """
    live_scores, state, phase_weights = live_number_score_table(
        df,
        target_time=target_time or str(df.iloc[-1].Saat),
        analysis_window=analysis_window,
        state_window=state_window,
    )
    region_scores = region_probability_scores(
        df,
        state_window=state_window,
        search_window=analysis_window,
        top_matches=25,
    )
    elimination = elimination_table_v16(
        df,
        live_scores,
        region_scores,
    )

    master = (
        live_scores
        .merge(
            region_scores[["Sayı", "Bölge", "Bölge Puanı"]],
            on="Sayı",
            how="left",
        )
        .merge(
            elimination[["Sayı", "Eleme Puanı", "Eleme Durumu"]],
            on="Sayı",
            how="left",
        )
    ).fillna(0)

    reliability = reliability or {}
    component_map = {
        "Taşıma": "Taşıma",
        "Yerine": "Yerine",
        "Blok": "Blok",
        "Dönüş": "Dönüş",
        "Saat": "Saat",
        "Benzer": "Benzer",
        "Kısaİvme": "Kısaİvme",
    }

    # Meta-skor: alt motorların backtest güvenini kullan.
    meta_raw = np.zeros(len(master), dtype=float)
    used_weight = 0.0
    for component, col in component_map.items():
        rel = float(reliability.get(component, 0.0))
        if rel > 0:
            meta_raw += rel * normalized_series(master[col]).to_numpy(float)
            used_weight += rel

    if used_weight <= 0:
        meta_raw = normalized_series(master["Canlı Puan"]).to_numpy(float)

    master["Meta Motor"] = meta_raw * 100.0

    master["V16 Ana Puan"] = (
        0.52 * normalized_series(master["Canlı Puan"])
        + 0.22 * normalized_series(master["Bölge Puanı"])
        + 0.26 * normalized_series(master["Meta Motor"])
    ) * 100.0

    # Eleme cezası
    master["V16 Ana Puan"] -= (
        0.18 * master["Eleme Puanı"]
    )
    master["V16 Ana Puan"] = master["V16 Ana Puan"].clip(0, 100).round(2)

    roles = role_table_v16(
        live_scores,
        region_scores,
        elimination,
    )[["Sayı", "Rol", "Rol Puanı"]]

    master = master.merge(roles, on="Sayı", how="left")

    return (
        master.sort_values(
            ["V16 Ana Puan", "Sayı"],
            ascending=[False, True],
        ),
        state,
        phase_weights,
        region_scores,
        elimination,
    )


def scenario_score_v16(master, scenario):
    """
    Beş farklı senaryo için aynı aday tablosunu farklı biçimde yorumlar.
    """
    out = master.copy()

    if scenario == "İskelet Dengeli":
        out["Senaryo Puanı"] = (
            0.55 * out["V16 Ana Puan"]
            + 0.20 * out["Bölge Puanı"]
            + 0.10 * out["Blok"]
            + 0.15 * out["Dönüş"]
        )
    elif scenario == "Taşıma":
        out["Senaryo Puanı"] = (
            0.45 * out["V16 Ana Puan"]
            + 0.35 * out["Taşıma"]
            + 0.10 * out["Saat"]
            + 0.10 * out["Benzer"]
        )
    elif scenario == "Yenilenme":
        out["Senaryo Puanı"] = (
            0.40 * out["V16 Ana Puan"]
            + 0.30 * out["Yerine"]
            + 0.20 * out["Dönüş"]
            + 0.10 * out["Bölge Puanı"]
        )
    elif scenario == "Blok/Küme":
        out["Senaryo Puanı"] = (
            0.40 * out["V16 Ana Puan"]
            + 0.30 * out["Blok"]
            + 0.20 * out["Bölge Puanı"]
            + 0.10 * out["Benzer"]
        )
    else:  # Sürpriz / Benzer Durum
        out["Senaryo Puanı"] = (
            0.35 * out["V16 Ana Puan"]
            + 0.30 * out["Benzer"]
            + 0.20 * out["Kısaİvme"]
            + 0.15 * out["Dönüş"]
        )

    out["Senaryo Puanı"] -= 0.12 * out["Eleme Puanı"]
    return out


def build_scenario_coupon_v16(
    master,
    latest_set,
    size,
    scenario,
    expected_carry,
    expected_regions,
    previous_coupons=None,
    seed=0,
):
    """
    Önce çekiliş iskeletine, sonra sayılara karar verir.
    """
    previous_coupons = previous_coupons or []
    work = scenario_score_v16(master, scenario)

    usage = Counter(n for coupon in previous_coupons for n in coupon)
    work["Final Seçim"] = (
        work["Senaryo Puanı"]
        - work["Sayı"].map(lambda n: usage.get(int(n), 0) * 3.0)
        + ((work["Sayı"] * (17 + seed) + seed * 29) % 53) / 100.0
    )

    # Güçlü ele adaylarını büyük ölçüde dışarıda bırak.
    q_elim = work["Eleme Puanı"].quantile(0.86)
    pool = work[work["Eleme Puanı"] < q_elim].copy()
    if len(pool) < size * 2:
        pool = work.copy()

    selected = []

    # İskeletin beklediği taşıma sayısına yaklaş.
    carry_target = int(round(expected_carry))
    carry_target = max(1, min(carry_target, size - 1))

    if scenario == "Yenilenme":
        carry_target = max(1, carry_target - 1)
    elif scenario == "Taşıma":
        carry_target = min(size - 1, carry_target + 1)

    carry_pool = pool[pool["Sayı"].isin(latest_set)].sort_values(
        "Final Seçim",
        ascending=False,
    )
    new_pool = pool[~pool["Sayı"].isin(latest_set)].sort_values(
        "Final Seçim",
        ascending=False,
    )

    for n in carry_pool["Sayı"].astype(int):
        selected.append(n)
        if len(selected) >= carry_target:
            break

    # Aktif iki bölgeyi öncele.
    region_target_counts = Counter()
    for region in expected_regions[:2]:
        if region and region != "-":
            region_target_counts[region] = max(1, round((size - len(selected)) / 2))

    def can_add(n):
        if n in selected:
            return False

        # Üçlü blok sadece blok senaryosunda veya blok puanı çok güçlüyse.
        trial = set(selected + [n])
        creates_three = (
            {n - 2, n - 1, n}.issubset(trial)
            or {n - 1, n, n + 1}.issubset(trial)
            or {n, n + 1, n + 2}.issubset(trial)
        )
        if creates_three and scenario != "Blok/Küme":
            block_score = float(
                pool.set_index("Sayı").loc[n, "Blok"]
            )
            if block_score < pool["Blok"].quantile(0.88):
                return False
        return True

    # Önce aktif bölgelerdeki yeni sayılar.
    for region, needed in region_target_counts.items():
        added = 0
        region_rows = new_pool[new_pool["Bölge"] == region]
        for n in region_rows["Sayı"].astype(int):
            if can_add(n):
                selected.append(n)
                added += 1
            if added >= needed or len(selected) >= size:
                break

    # Sonra genel en güçlü adaylar.
    combined = pd.concat([new_pool, carry_pool]).drop_duplicates("Sayı")
    for n in combined["Sayı"].astype(int):
        if len(selected) >= size:
            break
        if can_add(n):
            selected.append(n)

    return sorted(selected[:size])


def generate_v16_scenario_coupons(
    master,
    latest_set,
    skeleton,
    size=7,
    count=5,
):
    scenarios = [
        "İskelet Dengeli",
        "Taşıma",
        "Yenilenme",
        "Blok/Küme",
        "Sürpriz/Benzer",
    ]

    expected_carry = float(skeleton.get("Taşıma", max(2, size // 2)))
    expected_regions = [
        skeleton.get("Aktif Bölge 1", "-"),
        skeleton.get("Aktif Bölge 2", "-"),
    ]

    coupons = []
    results = []
    attempts = 0

    while len(results) < count and attempts < count * 10:
        scenario = scenarios[attempts % len(scenarios)]
        coupon = build_scenario_coupon_v16(
            master,
            latest_set,
            size=size,
            scenario=scenario,
            expected_carry=expected_carry,
            expected_regions=expected_regions,
            previous_coupons=coupons,
            seed=attempts,
        )

        if len(coupon) == size and coupon not in coupons:
            if all(
                len(set(coupon) ^ set(old)) >= 4
                for old in coupons
            ):
                coupons.append(coupon)
                results.append(
                    {
                        "Senaryo": scenario,
                        "Kupon": coupon,
                    }
                )
        attempts += 1

    return results


def explain_v16_coupon(coupon, master):
    idx = master.set_index("Sayı")
    rows = []
    for n in coupon:
        row = idx.loc[n]
        strongest = sorted(
            [
                ("taşıma", row["Taşıma"]),
                ("yerine", row["Yerine"]),
                ("blok", row["Blok"]),
                ("dönüş", row["Dönüş"]),
                ("bölge", row["Bölge Puanı"]),
                ("benzer", row["Benzer"]),
            ],
            key=lambda x: x[1],
            reverse=True,
        )[:3]

        rows.append(
            {
                "Sayı": n,
                "V16 Ana Puan": row["V16 Ana Puan"],
                "Rol": row["Rol"],
                "Eleme": row["Eleme Puanı"],
                "Bölge": row["Bölge"],
                "En güçlü neden": ", ".join(
                    f"{name}:{value:.1f}"
                    for name, value in strongest
                ),
            }
        )
    return pd.DataFrame(rows)



def all_consecutive_blocks_from_set(draw_set, min_len=2, max_len=5):
    """Bir çekilişte bulunan tüm 2/3/4/5'li ardışık alt blokları çıkarır."""
    values = sorted(set(int(n) for n in draw_set))
    present = set(values)
    blocks = []
    for length in range(int(min_len), int(max_len) + 1):
        for start in range(1, 82 - length):
            block = tuple(range(start, start + length))
            if set(block).issubset(present):
                blocks.append(block)
    return blocks


def block_birth_engine_v17(df, lookback=500, target_time=None):
    """
    Bir sonraki çekilişte doğabilecek 2/3/4'lü ardışık blokları puanlar.
    Sadece frekans değil; mevcut bloktan geçiş, sağ/sol kayma, saat ve
    benzer tarihsel durum desteğini birlikte kullanır.
    """
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    if len(work) < 3:
        return pd.DataFrame()

    sets = row_sets(work)
    current_set = sets[-1]
    current_blocks = all_consecutive_blocks_from_set(current_set, 2, 5)

    birth_counts = Counter()
    transition_counts = Counter()
    shift_counts = Counter()
    hour_counts = Counter()
    source_cases = Counter()

    target_hour = str(target_time or work.iloc[-1].Saat)[:2]

    blocks_by_draw = [
        all_consecutive_blocks_from_set(s, 2, 5)
        for s in sets
    ]

    for i in range(len(blocks_by_draw) - 1):
        cur_blocks = blocks_by_draw[i]
        nxt_blocks = blocks_by_draw[i + 1]
        next_hour = str(work.iloc[i + 1].Saat)[:2]

        for target in nxt_blocks:
            birth_counts[target] += 1
            if next_hour == target_hour:
                hour_counts[target] += 1

        for source in cur_blocks:
            source_cases[source] += 1
            for target in nxt_blocks:
                transition_counts[(source, target)] += 1

                if len(source) == len(target):
                    delta = target[0] - source[0]
                    if delta in (-2, -1, 1, 2):
                        shift_counts[(source, target)] += 1

    # Benzer durumların sonrasındaki bloklar
    match_df, _ = similar_state_next_scores(
        df,
        state_window=6,
        search_window=lookback,
        top_matches=25,
    )
    similar_block_weight = Counter()
    if not match_df.empty:
        draw_to_index = {
            int(row.Cekilis_No): idx
            for idx, row in df.reset_index(drop=True).iterrows()
        }
        for _, match in match_df.iterrows():
            idx = draw_to_index.get(int(match["Sonraki Çekiliş"]))
            if idx is None:
                continue
            draw_set = set(
                int(df.reset_index(drop=True).iloc[idx][c])
                for c in NUM_COLS
            )
            weight = max(float(match["Benzerlik %"]), 1.0) / 100.0
            for block in all_consecutive_blocks_from_set(draw_set, 2, 5):
                similar_block_weight[block] += weight

    candidates = []
    for length in (2, 3, 4, 5):
        for start in range(1, 82 - length):
            block = tuple(range(start, start + length))
            base = float(birth_counts.get(block, 0))
            hour = float(hour_counts.get(block, 0))
            similar = float(similar_block_weight.get(block, 0.0))

            trans = 0.0
            shift = 0.0
            source_support = 0
            for source in current_blocks:
                count = float(transition_counts.get((source, block), 0))
                trans += count
                if count > 0:
                    source_support += 1
                shift += float(shift_counts.get((source, block), 0))

            candidates.append(
                {
                    "Blok": "-".join(map(str, block)),
                    "Uzunluk": length,
                    "Temel doğum": base,
                    "Mevcut bloktan geçiş": trans,
                    "Sağ/Sol kayma": shift,
                    "Saat desteği": hour,
                    "Benzer durum": similar,
                    "Kaynak desteği": source_support,
                }
            )

    out = pd.DataFrame(candidates)
    if out.empty:
        return out

    for col in [
        "Temel doğum",
        "Mevcut bloktan geçiş",
        "Sağ/Sol kayma",
        "Saat desteği",
        "Benzer durum",
        "Kaynak desteği",
    ]:
        out[col + "_n"] = normalized_series(out[col])

    # Uzun bloklar nadir olduğu için küçücük uzunluk primi
    length_bonus = out["Uzunluk"].map({2: 0.00, 3: 0.04, 4: 0.06, 5: 0.08}).fillna(0.0)

    out["Blok Doğum Puanı"] = (
        0.24 * out["Temel doğum_n"]
        + 0.26 * out["Mevcut bloktan geçiş_n"]
        + 0.13 * out["Sağ/Sol kayma_n"]
        + 0.11 * out["Saat desteği_n"]
        + 0.20 * out["Benzer durum_n"]
        + 0.06 * out["Kaynak desteği_n"]
        + length_bonus
    ) * 100.0

    out["Blok Doğum Puanı"] = out["Blok Doğum Puanı"].clip(0, 100).round(2)
    return out.sort_values(
        ["Blok Doğum Puanı", "Uzunluk", "Blok"],
        ascending=[False, False, True],
    )


def block_shift_table_v17(df, lookback=500):
    """Blokların sağa/sola kaç sayı kayarak devam ettiğini özetler."""
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    sets = row_sets(work)
    blocks_by_draw = [
        all_consecutive_blocks_from_set(s, 2, 5)
        for s in sets
    ]

    rows = Counter()
    for i in range(len(blocks_by_draw) - 1):
        for source in blocks_by_draw[i]:
            for target in blocks_by_draw[i + 1]:
                if len(source) != len(target):
                    continue
                delta = target[0] - source[0]
                if delta in (-3, -2, -1, 0, 1, 2, 3):
                    rows[(source, target, delta)] += 1

    return pd.DataFrame(
        [
            {
                "Kaynak": "-".join(map(str, source)),
                "Sonraki": "-".join(map(str, target)),
                "Kayma": delta,
                "Adet": count,
            }
            for (source, target, delta), count in rows.most_common(250)
        ]
    )


def neighborhood_completion_v17(df, base_scores, lookback=500):
    """
    Güçlü sayıların ±1/±2 komşularının gerçekten birlikte gelme ve
    küme tamamlama eğilimini puanlar.
    """
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    sets = row_sets(work)
    base_top = base_scores.head(20)["Sayı"].astype(int).tolist()

    pair_counts = Counter()
    base_occurrence = Counter()
    for draw_set in sets:
        for base in base_top:
            if base in draw_set:
                base_occurrence[base] += 1
                for delta in (-2, -1, 1, 2):
                    neigh = base + delta
                    if 1 <= neigh <= 80 and neigh in draw_set:
                        pair_counts[(base, neigh)] += 1

    rows = []
    for base in base_top:
        base_score = float(
            base_scores.set_index("Sayı").loc[base, "V16 Ana Puan"]
            if "V16 Ana Puan" in base_scores.columns
            else base_scores.set_index("Sayı").loc[base, "Canlı Puan"]
        )
        denom = max(base_occurrence.get(base, 0), 1)

        for delta in (-2, -1, 1, 2):
            neigh = base + delta
            if not (1 <= neigh <= 80):
                continue
            co = pair_counts.get((base, neigh), 0)
            cond = co / denom

            rows.append(
                {
                    "Çekirdek": base,
                    "Komşu": neigh,
                    "Mesafe": delta,
                    "Birlikte gelme": co,
                    "Koşullu oran %": round(cond * 100, 2),
                    "Çekirdek güç": base_score,
                    "Komşuluk Puanı": round(
                        min(100.0, 0.55 * base_score + 45.0 * cond),
                        2,
                    ),
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["Komşuluk Puanı", "Koşullu oran %", "Komşu"],
        ascending=[False, False, True],
    )


def cluster_completion_scores_v17(df, base_scores, lookback=500):
    """
    Güçlü çekirdeklerin yanında tarihsel olarak tekrar eden yakın kümeleri
    sayı bazında destek puanına dönüştürür.
    """
    neigh = neighborhood_completion_v17(
        df,
        base_scores,
        lookback=lookback,
    )
    score = Counter()

    if not neigh.empty:
        for _, row in neigh.head(80).iterrows():
            score[int(row["Komşu"])] += float(row["Komşuluk Puanı"])

    max_score = max(score.values(), default=1.0)
    return pd.DataFrame(
        [
            {
                "Sayı": n,
                "Küme Tamamlama": round(
                    score.get(n, 0.0) / max_score * 100.0,
                    2,
                ),
            }
            for n in range(1, 81)
        ]
    )


def v17_master_table(df, target_time, window, state_window, reliability=None):
    """
    V16 ana puanını Blok Doğum + Komşuluk/Küme Tamamlama ile genişletir.
    """
    master, state, phase_weights, region_scores, elimination = v16_master_score_table(
        df,
        target_time=target_time,
        analysis_window=window,
        state_window=state_window,
        reliability=reliability or {},
    )

    block_birth = block_birth_engine_v17(
        df,
        lookback=window,
        target_time=target_time,
    )

    # Blok puanını sayı bazına çevir
    block_number_score = Counter()
    if not block_birth.empty:
        for _, row in block_birth.head(80).iterrows():
            nums = [int(x) for x in str(row["Blok"]).split("-")]
            for n in nums:
                block_number_score[n] += float(row["Blok Doğum Puanı"])

    max_block = max(block_number_score.values(), default=1.0)
    block_number_df = pd.DataFrame(
        [
            {
                "Sayı": n,
                "Blok Doğum": round(
                    block_number_score.get(n, 0.0) / max_block * 100.0,
                    2,
                ),
            }
            for n in range(1, 81)
        ]
    )

    cluster_df = cluster_completion_scores_v17(
        df,
        master,
        lookback=window,
    )

    out = (
        master
        .merge(block_number_df, on="Sayı", how="left")
        .merge(cluster_df, on="Sayı", how="left")
        .fillna(0)
    )

    out["V17 Yaşayan Puan"] = (
        0.72 * normalized_series(out["V16 Ana Puan"])
        + 0.16 * normalized_series(out["Blok Doğum"])
        + 0.12 * normalized_series(out["Küme Tamamlama"])
    ) * 100.0

    out["V17 Yaşayan Puan"] -= 0.12 * out["Eleme Puanı"]
    out["V17 Yaşayan Puan"] = out["V17 Yaşayan Puan"].clip(0, 100).round(2)

    return (
        out.sort_values(
            ["V17 Yaşayan Puan", "Sayı"],
            ascending=[False, True],
        ),
        state,
        phase_weights,
        region_scores,
        elimination,
        block_birth,
    )


def v17_scenario_table(master, scenario):
    """V17 senaryolarına blok-doğum ve küme-tamamlama etkisi ekler."""
    out = master.copy()

    if scenario == "İskelet":
        out["Senaryo"] = (
            0.52 * out["V17 Yaşayan Puan"]
            + 0.18 * out["Bölge Puanı"]
            + 0.15 * out["Blok Doğum"]
            + 0.15 * out["Küme Tamamlama"]
        )
    elif scenario == "Blok Doğum":
        out["Senaryo"] = (
            0.36 * out["V17 Yaşayan Puan"]
            + 0.34 * out["Blok Doğum"]
            + 0.20 * out["Küme Tamamlama"]
            + 0.10 * out["Bölge Puanı"]
        )
    elif scenario == "Taşıma/Küme":
        out["Senaryo"] = (
            0.38 * out["V17 Yaşayan Puan"]
            + 0.25 * out["Taşıma"]
            + 0.22 * out["Küme Tamamlama"]
            + 0.15 * out["Benzer"]
        )
    elif scenario == "Yenilenme":
        out["Senaryo"] = (
            0.38 * out["V17 Yaşayan Puan"]
            + 0.28 * out["Yerine"]
            + 0.20 * out["Dönüş"]
            + 0.14 * out["Bölge Puanı"]
        )
    else:  # Benzer/Sürpriz
        out["Senaryo"] = (
            0.35 * out["V17 Yaşayan Puan"]
            + 0.28 * out["Benzer"]
            + 0.17 * out["Kısaİvme"]
            + 0.10 * out["Blok Doğum"]
            + 0.10 * out["Küme Tamamlama"]
        )

    out["Senaryo"] -= 0.10 * out["Eleme Puanı"]
    return out


def build_v17_coupon(master, latest_set, skeleton, scenario, size=7, previous=None, seed=0):
    previous = previous or []
    work = v17_scenario_table(master, scenario)

    usage = Counter(n for c in previous for n in c)
    work["Final"] = (
        work["Senaryo"]
        - work["Sayı"].map(lambda n: usage.get(int(n), 0) * 3.2)
        + ((work["Sayı"] * (19 + seed) + seed * 31) % 59) / 100.0
    )

    expected_carry = int(round(float(skeleton.get("Taşıma", 3))))
    expected_carry = max(1, min(expected_carry, size - 1))
    if scenario == "Yenilenme":
        expected_carry = max(1, expected_carry - 1)
    if scenario == "Taşıma/Küme":
        expected_carry = min(size - 1, expected_carry + 1)

    active_regions = [
        skeleton.get("Aktif Bölge 1", "-"),
        skeleton.get("Aktif Bölge 2", "-"),
    ]

    q_elim = work["Eleme Puanı"].quantile(0.88)
    pool = work[work["Eleme Puanı"] < q_elim].copy()
    if len(pool) < size * 2:
        pool = work.copy()

    selected = []

    carry_pool = pool[pool["Sayı"].isin(latest_set)].sort_values(
        "Final",
        ascending=False,
    )
    for n in carry_pool["Sayı"].astype(int):
        selected.append(n)
        if len(selected) >= expected_carry:
            break

    # Aktif bölgeden destek
    for region in active_regions:
        if region == "-":
            continue
        region_pool = pool[
            (~pool["Sayı"].isin(selected))
            & (pool["Bölge"] == region)
        ].sort_values("Final", ascending=False)
        if not region_pool.empty and len(selected) < size:
            selected.append(int(region_pool.iloc[0]["Sayı"]))

    # Blok senaryosunda en güçlü doğacak bloktan 2-3 sayı almaya çalış
    if scenario == "Blok Doğum":
        block_birth = block_birth_engine_v17(df, lookback=min(500, len(df)))
        if not block_birth.empty:
            for _, brow in block_birth.head(10).iterrows():
                nums = [int(x) for x in str(brow["Blok"]).split("-")]
                trial_add = [n for n in nums if n not in selected]
                if trial_add and len(selected) + len(trial_add) <= size:
                    selected.extend(trial_add)
                    break

    for n in pool.sort_values("Final", ascending=False)["Sayı"].astype(int):
        if len(selected) >= size:
            break
        if n in selected:
            continue

        trial = set(selected + [n])
        creates_four = any(
            set(range(start, start + 4)).issubset(trial)
            for start in range(max(1, n - 3), min(78, n) + 1)
        )
        if creates_four and scenario != "Blok Doğum":
            continue

        selected.append(n)

    return sorted(selected[:size])


def generate_v17_coupons(master, latest_set, skeleton, size=7, count=5):
    scenarios = [
        "İskelet",
        "Blok Doğum",
        "Taşıma/Küme",
        "Yenilenme",
        "Benzer/Sürpriz",
    ]

    coupons = []
    items = []
    attempts = 0

    while len(items) < count and attempts < count * 12:
        scenario = scenarios[attempts % len(scenarios)]
        coupon = build_v17_coupon(
            master,
            latest_set,
            skeleton,
            scenario,
            size=size,
            previous=coupons,
            seed=attempts,
        )

        if len(coupon) == size and coupon not in coupons:
            if all(len(set(coupon) ^ set(old)) >= 4 for old in coupons):
                coupons.append(coupon)
                items.append(
                    {
                        "Senaryo": scenario,
                        "Kupon": coupon,
                    }
                )
        attempts += 1

    return items


def load_motor_memory_v17(settings):
    """Kalıcı motor hafızasını GitHub'dan okur."""
    text, _ = github_text_file(settings, "motor_hafiza.csv")
    if not text.strip():
        return pd.DataFrame(
            columns=[
                "Tarih",
                "Cekilis",
                "Senaryo",
                "Kupon",
                "Isabet",
                "Tutan",
            ]
        )
    try:
        return pd.read_csv(io.StringIO(text), dtype=str)
    except Exception:
        return pd.DataFrame(
            columns=[
                "Tarih",
                "Cekilis",
                "Senaryo",
                "Kupon",
                "Isabet",
                "Tutan",
            ]
        )


def save_motor_memory_v17(settings, memory_df):
    save_github_text_file(
        settings,
        "motor_hafiza.csv",
        memory_df.to_csv(index=False),
        "V17 motor hafızası güncellendi",
    )


def evaluate_v17_saved_coupons(df, items, start_draw):
    """Üretilen V17 kuponlarını sonraki gerçek çekilişlerle değerlendirir."""
    rows = []
    tested = df[df["Cekilis_No"].astype(int) >= int(start_draw)]

    for _, draw in tested.iterrows():
        actual = set(int(draw[c]) for c in NUM_COLS)
        for item in items:
            coupon = sorted(set(int(n) for n in item["Kupon"]))
            hits = sorted(set(coupon) & actual)
            rows.append(
                {
                    "Tarih": f"{draw.Tarih} {draw.Saat}",
                    "Cekilis": int(draw.Cekilis_No),
                    "Senaryo": item["Senaryo"],
                    "Kupon": "-".join(map(str, coupon)),
                    "Isabet": len(hits),
                    "Tutan": "-".join(map(str, hits)),
                }
            )

    return pd.DataFrame(rows)



def save_v18_pending_v1853(settings, items, target_date, target_time, target_draw=None):
    """V18 kuponlarını sonuç gelmeden GitHub'a küçük bir bekleyen dosya olarak kaydeder."""
    payload = {
        "target_date": str(target_date),
        "target_time": str(target_time),
        "target_draw": target_draw,
        "items": [
            {
                "Senaryo": str(item.get("Senaryo", "")),
                "Kupon": [int(x) for x in item.get("Kupon", [])],
            }
            for item in items
        ],
    }
    save_github_text_file(
        settings,
        "v18_bekleyen.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "V18 bekleyen kuponlar güncellendi",
    )


def load_v18_pending_v1853(settings):
    """Streamlit yeniden başlasa bile sonuç bekleyen V18 kuponlarını geri yükler."""
    text, _ = github_text_file(settings, "v18_bekleyen.json")
    if not text.strip():
        return {}
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            return {}
        return payload
    except Exception:
        return {}


def clear_v18_pending_v1853(settings):
    try:
        save_github_text_file(
            settings,
            "v18_bekleyen.json",
            "{}",
            "V18 bekleyen kupon temizlendi",
        )
    except Exception:
        pass


def v17_memory_scorecard(memory_df):
    if memory_df is None or memory_df.empty:
        return pd.DataFrame()

    work = memory_df.copy()
    work["Isabet"] = pd.to_numeric(work["Isabet"], errors="coerce").fillna(0)

    return (
        work.groupby("Senaryo", as_index=False)
        .agg(
            Test=("Isabet", "count"),
            Ortalama=("Isabet", "mean"),
            En_Iyi=("Isabet", "max"),
            Uc_Artı=("Isabet", lambda s: int((s >= 3).sum())),
            Dort_Artı=("Isabet", lambda s: int((s >= 4).sum())),
            Bes_Artı=("Isabet", lambda s: int((s >= 5).sum())),
        )
        .sort_values(["Ortalama", "Dort_Artı"], ascending=False)
    )



def adaptive_weights_from_memory_v18(memory_df):
    """
    Kalıcı motor hafızasından gerçek sonuç performansına göre öğrenen katsayılar üretir.
    V18.5.3:
    - 5 gerçek test satırından sonra çalışmaya başlar.
    - 'Blok Doğum 3lü' gibi senaryo adlarını da tanır.
    - Son 250 hafıza satırına daha fazla önem verir.
    - Aşırı sıçramayı engellemek için 1.00'a doğru yumuşatma uygular.
    """
    default = {
        "Taşıma": 1.0,
        "Yerine": 1.0,
        "Blok": 1.0,
        "Dönüş": 1.0,
        "Saat": 1.0,
        "Benzer": 1.0,
        "Kısaİvme": 1.0,
        "Bölge": 1.0,
        "Küme": 1.0,
    }

    if memory_df is None or memory_df.empty or "Isabet" not in memory_df.columns:
        return default

    work = memory_df.copy()
    work["Isabet"] = pd.to_numeric(work["Isabet"], errors="coerce")
    work = work.dropna(subset=["Isabet"]).tail(250)

    if len(work) < 5:
        return default

    overall = float(work["Isabet"].mean())
    if overall <= 0:
        return default

    scenario_map = {
        "Taşıma": ["Taşıma", "Taşıma/Küme"],
        "Yerine": ["Yenilenme"],
        "Blok": ["Blok Doğum", "Blok/Küme"],
        "Dönüş": ["Yenilenme", "Benzer/Sürpriz"],
        "Saat": ["İskelet"],
        "Benzer": ["Benzer/Sürpriz", "Sürpriz/Benzer"],
        "Kısaİvme": ["Benzer/Sürpriz", "Sürpriz/Benzer"],
        "Bölge": ["İskelet"],
        "Küme": ["Taşıma/Küme", "Blok Doğum"],
    }

    scenario_text = work["Senaryo"].fillna("").astype(str)

    weights = {}
    for motor, patterns in scenario_map.items():
        mask = pd.Series(False, index=work.index)
        for pattern in patterns:
            mask = mask | scenario_text.str.contains(
                re.escape(pattern),
                case=False,
                regex=True,
                na=False,
            )

        subset = work[mask]
        if subset.empty:
            weights[motor] = 1.0
            continue

        n = len(subset)
        raw_mean = float(subset["Isabet"].mean())

        # Küçük örneklerde aşırı tepki vermesin.
        shrink_strength = 12.0
        shrunk_mean = (
            raw_mean * n + overall * shrink_strength
        ) / (n + shrink_strength)

        ratio = shrunk_mean / overall if overall > 0 else 1.0

        # 1.00 nötr; sınırlar güvenli tutuldu.
        weights[motor] = round(
            min(max(ratio, 0.75), 1.30),
            3,
        )

    return weights


def v18_living_score_table(master_v17, adaptive_weights):
    """
    V17 Yaşayan Puan + kalıcı öğrenme katsayıları = V18 Nefes Puanı.
    """
    out = master_v17.copy()

    def nrm(col):
        return normalized_series(out[col])

    score = (
        0.28 * nrm("V17 Yaşayan Puan")
        + 0.10 * nrm("Taşıma") * adaptive_weights.get("Taşıma", 1.0)
        + 0.08 * nrm("Yerine") * adaptive_weights.get("Yerine", 1.0)
        + 0.10 * nrm("Blok Doğum") * adaptive_weights.get("Blok", 1.0)
        + 0.08 * nrm("Dönüş") * adaptive_weights.get("Dönüş", 1.0)
        + 0.06 * nrm("Saat") * adaptive_weights.get("Saat", 1.0)
        + 0.10 * nrm("Benzer") * adaptive_weights.get("Benzer", 1.0)
        + 0.05 * nrm("Kısaİvme") * adaptive_weights.get("Kısaİvme", 1.0)
        + 0.08 * nrm("Bölge Puanı") * adaptive_weights.get("Bölge", 1.0)
        + 0.07 * nrm("Küme Tamamlama") * adaptive_weights.get("Küme", 1.0)
    )

    out["V18 Nefes Puanı"] = score * 100.0
    out["V18 Nefes Puanı"] -= 0.14 * out["Eleme Puanı"]
    out["V18 Nefes Puanı"] = out["V18 Nefes Puanı"].clip(0, 100).round(2)

    return out.sort_values(
        ["V18 Nefes Puanı", "Sayı"],
        ascending=[False, True],
    )


def v18_confidence_panel(state, skeleton, block_birth_df, memory_df):
    phase_conf = float(state.get("Güven", 0.0))

    skeleton_conf = 0.0
    if skeleton:
        skeleton_conf = min(
            95.0,
            42.0
            + 4.0 * float(skeleton.get("Taşıma", 0.0))
            + 6.0 * float(skeleton.get("MaksBlok", 0.0)),
        )

    block_conf = 0.0
    if block_birth_df is not None and not block_birth_df.empty:
        block_conf = float(
            block_birth_df.head(5)["Blok Doğum Puanı"].mean()
        )

    learning_conf = 30.0
    if memory_df is not None and not memory_df.empty and "Isabet" in memory_df.columns:
        tests = pd.to_numeric(
            memory_df["Isabet"],
            errors="coerce",
        ).notna().sum()
        learning_conf = min(95.0, 30.0 + tests * 2.5)

    number_conf = (
        0.30 * phase_conf
        + 0.25 * skeleton_conf
        + 0.25 * block_conf
        + 0.20 * learning_conf
    )

    return {
        "Durum Güveni": round(phase_conf, 1),
        "İskelet Güveni": round(skeleton_conf, 1),
        "Blok Güveni": round(block_conf, 1),
        "Öğrenme Güveni": round(learning_conf, 1),
        "Sayı Seçimi Güveni": round(number_conf, 1),
    }


def latest_draw_structure_v18(df):
    if df is None or len(df) < 2:
        return {}
    work = df.sort_values("Cekilis_No").reset_index(drop=True)
    prev_set = set(int(work.iloc[-2][c]) for c in NUM_COLS)
    cur_set = set(int(work.iloc[-1][c]) for c in NUM_COLS)
    return draw_shape_metrics(prev_set, cur_set)


def forecast_error_report_v18(df, skeleton, block_birth_df, region_forecast_df):
    actual = latest_draw_structure_v18(df)
    if not actual:
        return {}

    result = {}
    for key in ["Taşıma", "Yeni", "2liBlok", "3luBlok", "MaksBlok"]:
        pred = float(skeleton.get(key, 0.0))
        act = float(actual.get(key, 0.0))
        result[f"{key}_Tahmin"] = round(pred, 2)
        result[f"{key}_Gercek"] = round(act, 2)
        result[f"{key}_Hata"] = round(abs(pred - act), 2)

    predicted_regions = []
    if region_forecast_df is not None and not region_forecast_df.empty:
        predicted_regions = (
            region_forecast_df.head(2)["Bölge"].astype(str).tolist()
        )

    actual_regions = sorted(
        [
            (key.replace("Bölge_", ""), value)
            for key, value in actual.items()
            if key.startswith("Bölge_")
        ],
        key=lambda x: x[1],
        reverse=True,
    )[:2]
    result["Bolge_Eslesti"] = len(
        set(predicted_regions)
        & set(name for name, _ in actual_regions)
    )

    actual_set = set(int(df.sort_values("Cekilis_No").iloc[-1][c]) for c in NUM_COLS)
    actual_blocks = {
        "-".join(map(str, b))
        for b in all_consecutive_blocks_from_set(actual_set, 2, 4)
    }

    predicted_blocks = []
    if block_birth_df is not None and not block_birth_df.empty:
        predicted_blocks = block_birth_df.head(10)["Blok"].astype(str).tolist()

    result["Blok_Top10_Isabet"] = len(
        set(predicted_blocks) & actual_blocks
    )

    return result


def v18_postmortem_text(error_report, scorecard):
    if not error_report:
        return "Henüz değerlendirilecek yeni gerçek sonuç yok."

    messages = []

    if error_report.get("Taşıma_Hata", 0) >= 2:
        messages.append("Taşıma iskeleti belirgin sapmış.")
    if (
        error_report.get("2liBlok_Hata", 0) >= 2
        or error_report.get("3luBlok_Hata", 0) >= 1
    ):
        messages.append("Blok yoğunluğu doğru okunamamış.")
    if error_report.get("Bolge_Eslesti", 0) == 0:
        messages.append("Aktif bölge tahmini kaçmış.")
    if error_report.get("Blok_Top10_Isabet", 0) == 0:
        messages.append("Blok doğum motoru top-10 içinde gerçek bloğu yakalayamamış.")

    if scorecard is not None and not scorecard.empty:
        best = scorecard.iloc[0]
        messages.append(
            f"Şu anda en verimli senaryo {best['Senaryo']} "
            f"(ortalama {float(best['Ortalama']):.2f})."
        )

    if not messages:
        messages.append(
            "İskelet ve yapı genel olarak uyumlu; hata sayı seçimi katmanında kalmış olabilir."
        )

    return " ".join(messages)


def generate_v18_coupons(master_v18, latest_set, skeleton, size=7, count=5):
    scenarios = [
        "İskelet",
        "Blok Doğum",
        "Taşıma/Küme",
        "Yenilenme",
        "Benzer/Sürpriz",
    ]

    items = []
    coupons = []

    for attempt in range(count * 12):
        if len(items) >= count:
            break

        scenario = scenarios[attempt % len(scenarios)]
        work = v17_scenario_table(master_v18, scenario).copy()
        work["SenaryoV18"] = (
            0.58 * work["Senaryo"]
            + 0.42 * work["V18 Nefes Puanı"]
        )

        usage = Counter(n for coupon in coupons for n in coupon)
        work["FinalV18"] = (
            work["SenaryoV18"]
            - work["Sayı"].map(
                lambda n: usage.get(int(n), 0) * 3.4
            )
            + (
                (
                    work["Sayı"] * (23 + attempt)
                    + attempt * 37
                ) % 61
            ) / 100.0
        )

        expected_carry = int(
            round(float(skeleton.get("Taşıma", 3)))
        )
        expected_carry = max(
            1,
            min(expected_carry, size - 1),
        )

        if scenario == "Yenilenme":
            expected_carry = max(1, expected_carry - 1)
        elif scenario == "Taşıma/Küme":
            expected_carry = min(size - 1, expected_carry + 1)

        selected = []

        carry_pool = work[
            work["Sayı"].isin(latest_set)
        ].sort_values(
            "FinalV18",
            ascending=False,
        )

        for n in carry_pool["Sayı"].astype(int):
            selected.append(n)
            if len(selected) >= expected_carry:
                break

        for region in [
            skeleton.get("Aktif Bölge 1", "-"),
            skeleton.get("Aktif Bölge 2", "-"),
        ]:
            if len(selected) >= size or region == "-":
                continue

            region_pool = work[
                (~work["Sayı"].isin(selected))
                & (work["Bölge"] == region)
            ].sort_values(
                "FinalV18",
                ascending=False,
            )

            if not region_pool.empty:
                selected.append(
                    int(region_pool.iloc[0]["Sayı"])
                )

        if scenario == "Blok Doğum":
            pool = work.sort_values(
                [
                    "Blok Doğum",
                    "Küme Tamamlama",
                    "FinalV18",
                ],
                ascending=False,
            )
        else:
            pool = work.sort_values(
                "FinalV18",
                ascending=False,
            )

        for n in pool["Sayı"].astype(int):
            if len(selected) >= size:
                break
            if n not in selected:
                selected.append(n)

        coupon = sorted(selected[:size])

        if (
            len(coupon) == size
            and coupon not in coupons
            and all(
                len(set(coupon) ^ set(old)) >= 4
                for old in coupons
            )
        ):
            coupons.append(coupon)
            items.append(
                {
                    "Senaryo": scenario,
                    "Kupon": coupon,
                }
            )

    return items



def evaluate_exact_target_draw_v181(df, items, target_draw_no=None, target_date=None, target_time=None):
    """
    V18.3: Kuponu çekiliş numarası tahminiyle değil, hedef tarih+saat ile
    eşleştirir. Gerçek sonuç bulunduğunda gerçek Cekilis_No kullanılır.
    Eski target_draw_no parametresi geriye uyumluluk için tutulur.
    """
    if not items or target_date is None or target_time is None:
        return pd.DataFrame()

    target = df[
        (df["Tarih"].astype(str) == str(target_date))
        & (df["Saat"].astype(str).str[:5] == str(target_time)[:5])
    ]
    if target.empty:
        return pd.DataFrame()

    draw = target.iloc[-1]
    actual = set(int(draw[c]) for c in NUM_COLS)

    rows = []
    for item in items:
        coupon = sorted(set(int(n) for n in item["Kupon"]))
        hits = sorted(set(coupon) & actual)
        rows.append(
            {
                "Tarih": f"{draw.Tarih} {draw.Saat}",
                "Cekilis": int(draw.Cekilis_No),
                "Senaryo": item["Senaryo"],
                "Kupon": "-".join(map(str, coupon)),
                "Isabet": len(hits),
                "Tutan": "-".join(map(str, hits)),
            }
        )
    return pd.DataFrame(rows)


def target_badge_v181(target_draw, target_date, target_time):
    return f"{target_date} {target_time} — çekiliş no sonuç gelince kesinleşecek"


def maximal_blocks_v184(draw_set):
    """Çekilişteki maksimal ardışık blokları döndürür (2+)."""
    nums = sorted(set(int(n) for n in draw_set))
    if not nums:
        return []
    blocks, cur = [], [nums[0]]
    for n in nums[1:]:
        if n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2:
                blocks.append(tuple(cur))
            cur = [n]
    if len(cur) >= 2:
        blocks.append(tuple(cur))
    return blocks


def block_profile_v184(draw_set):
    """Tek çekilişin blok karakterini sayısal profile çevirir."""
    blocks = maximal_blocks_v184(draw_set)
    lengths = [len(b) for b in blocks]
    return {
        "Blok Adedi": len(blocks),
        "Komşu Çifti": sum(max(0, len(b) - 1) for b in blocks),
        "Maks Blok": max(lengths, default=1),
        "2+": sum(len(b) >= 2 for b in blocks),
        "3+": sum(len(b) >= 3 for b in blocks),
        "4+": sum(len(b) >= 4 for b in blocks),
        "5+": sum(len(b) >= 5 for b in blocks),
        "Blok Üyesi": sum(lengths),
    }


def block_state_vector_v184(profiles):
    """Son birkaç çekilişin blok hareketini tek durum vektöründe özetler."""
    if not profiles:
        return np.zeros(10, dtype=float)
    frame = pd.DataFrame(profiles)
    cols = ["Blok Adedi", "Komşu Çifti", "Maks Blok", "3+", "4+", "5+", "Blok Üyesi"]
    means = frame[cols].mean().to_numpy(float)
    last = frame.iloc[-1]
    trend = np.array([
        float(frame["Komşu Çifti"].iloc[-1] - frame["Komşu Çifti"].iloc[0]) if len(frame) > 1 else 0.0,
        float(frame["Maks Blok"].iloc[-1] - frame["Maks Blok"].iloc[0]) if len(frame) > 1 else 0.0,
        float(frame["Blok Adedi"].iloc[-1] - frame["Blok Adedi"].iloc[0]) if len(frame) > 1 else 0.0,
    ])
    return np.concatenate([means, trend])


def block_pressure_engine_v184(df, lookback=600, state_window=5, target_time=None, top_matches=45):
    """
    Geçmişte son blok durumuna benzeyen pencereleri bulur ve onların hemen
    sonraki çekilişlerinden 2/3/4/5'li blok basıncı tahmini çıkarır.
    Tahmin yalnızca geçmiş satırlara dayanır; gelecek satır kullanılmaz.
    """
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    if len(work) < state_window + 25:
        return {}, pd.DataFrame(), pd.DataFrame()

    sets = row_sets(work)
    profiles = [block_profile_v184(s) for s in sets]
    current_vec = block_state_vector_v184(profiles[-state_window:])

    # ölçek: geçmiş durum vektörlerinin standart sapması
    hist_vectors = []
    for i in range(state_window, len(work) - 1):
        hist_vectors.append(block_state_vector_v184(profiles[i-state_window:i]))
    scale = np.std(np.vstack(hist_vectors), axis=0) if hist_vectors else np.ones_like(current_vec)
    scale = np.where(scale < 0.25, 1.0, scale)

    target_hour = str(target_time or work.iloc[-1].Saat)[:2]
    matches = []
    for i in range(state_window, len(work)):
        # i = hedeflenen sonraki çekiliş; durum sadece i öncesini kullanır
        if i >= len(profiles):
            break
        vec = block_state_vector_v184(profiles[i-state_window:i])
        dist = float(np.sqrt(np.mean(((vec - current_vec) / scale) ** 2)))
        sim = float(np.exp(-dist))
        if str(work.iloc[i].Saat)[:2] == target_hour:
            sim *= 1.12
        matches.append((sim, i))

    matches = sorted(matches, reverse=True)[:int(top_matches)]
    if not matches:
        return {}, pd.DataFrame(), pd.DataFrame()

    total_w = sum(w for w, _ in matches) or 1.0
    expected = Counter()
    prob = Counter()
    region = Counter()
    match_rows = []

    for weight, i in matches:
        prof = profiles[i]
        for k, v in prof.items():
            expected[k] += weight * float(v)
        for length in (2, 3, 4, 5):
            if int(prof["Maks Blok"]) >= length:
                prob[length] += weight

        # Blok merkezlerini 10'luk bölgelere ağırlıkla
        for block in maximal_blocks_v184(sets[i]):
            center = int(round(float(np.mean(block))))
            region[ten_band_name(center)] += weight * max(1, len(block) - 1)

        match_rows.append({
            "Benzerlik %": round(weight / 1.12 * 100 if str(work.iloc[i].Saat)[:2] == target_hour else weight * 100, 2),
            "Çekiliş": int(work.iloc[i].Cekilis_No),
            "Tarih": str(work.iloc[i].Tarih),
            "Saat": str(work.iloc[i].Saat),
            **prof,
        })

    forecast = {k: round(v / total_w, 2) for k, v in expected.items()}
    for length in (2, 3, 4, 5):
        forecast[f"{length}lü Olasılık %"] = round(prob[length] / total_w * 100, 1)

    # Basınç: geçmiş benzer pencerelerin sonraki çekilişlerinde uzun blokların ağırlıklı birleşimi
    pressure = (
        0.22 * forecast.get("2lü Olasılık %", 0)
        + 0.28 * forecast.get("3lü Olasılık %", 0)
        + 0.28 * forecast.get("4lü Olasılık %", 0)
        + 0.22 * forecast.get("5lü Olasılık %", 0)
    )
    forecast["Blok Basıncı"] = round(min(max(pressure, 0.0), 100.0), 1)
    p = forecast["Blok Basıncı"]
    forecast["Basınç Seviyesi"] = "Çok yüksek" if p >= 75 else "Yüksek" if p >= 60 else "Orta" if p >= 40 else "Düşük"

    region_rows = []
    max_region = max(region.values(), default=1.0)
    for name in [f"{i}-{i+9}" for i in range(1, 80, 10)]:
        region_rows.append({
            "Bölge": name,
            "Blok Bölge Puanı": round(region.get(name, 0.0) / max_region * 100.0, 2),
        })
    region_df = pd.DataFrame(region_rows).sort_values("Blok Bölge Puanı", ascending=False)
    match_df = pd.DataFrame(match_rows).sort_values("Benzerlik %", ascending=False)
    return forecast, region_df, match_df


def block_growth_break_table_v184(df, lookback=600):
    """Son çekilişteki blokların geçmişte sonraki elde nasıl evrildiğini ölçer."""
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    if len(work) < 3:
        return pd.DataFrame()
    sets = row_sets(work)
    current_blocks = maximal_blocks_v184(sets[-1])
    rows = []

    for current in current_blocks:
        exact = grow = shrink = shift = broken = cases = 0
        curset = set(current)
        for i in range(len(sets) - 1):
            # tarihsel çekilişte mevcut bloğun tamamı varsa olay say
            if not curset.issubset(sets[i]):
                continue
            cases += 1
            nxt_blocks = maximal_blocks_v184(sets[i + 1])
            found = False
            for nb in nxt_blocks:
                nbset = set(nb)
                overlap = len(curset & nbset)
                if tuple(nb) == tuple(current):
                    exact += 1; found = True; break
                if curset.issubset(nbset) and len(nb) > len(current):
                    grow += 1; found = True; break
                if nbset.issubset(curset) and overlap >= 2 and len(nb) < len(current):
                    shrink += 1; found = True; break
                if len(nb) == len(current) and abs(nb[0] - current[0]) <= 2 and overlap >= max(1, len(current)-1):
                    shift += 1; found = True; break
            if not found:
                broken += 1

        denom = max(cases, 1)
        rows.append({
            "Mevcut Blok": "-".join(map(str, current)),
            "Uzunluk": len(current),
            "Geçmiş Olay": cases,
            "Aynen %": round(exact/denom*100, 1),
            "Büyüme %": round(grow/denom*100, 1),
            "Küçülme %": round(shrink/denom*100, 1),
            "Kayma %": round(shift/denom*100, 1),
            "Kırılma %": round(broken/denom*100, 1),
        })
    return pd.DataFrame(rows)


def block_overfollow_penalty_v184(df, lookback=600):
    """Önceki blokları kör taşıma riskini sayı bazında cezaya çevirir."""
    growth = block_growth_break_table_v184(df, lookback=lookback)
    penalty = Counter()
    if growth.empty:
        return pd.DataFrame({"Sayı": range(1,81), "Blok Takip Cezası": [0.0]*80})
    for _, row in growth.iterrows():
        nums = [int(x) for x in str(row["Mevcut Blok"]).split("-")]
        break_rate = float(row["Kırılma %"])
        cases = int(row["Geçmiş Olay"])
        confidence = min(1.0, cases / 15.0)
        p = break_rate * confidence
        for n in nums:
            penalty[n] = max(penalty[n], p)
    return pd.DataFrame([
        {"Sayı": n, "Blok Takip Cezası": round(penalty.get(n,0.0),2)}
        for n in range(1,81)
    ])


def block_intelligence_number_scores_v184(block_birth, region_df):
    """Blok adaylarını ve blok-bölge basıncını sayı puanına dönüştürür."""
    score = Counter()
    if block_birth is not None and not block_birth.empty:
        for _, row in block_birth.head(120).iterrows():
            nums = [int(x) for x in str(row["Blok"]).split("-")]
            base = float(row["Blok Doğum Puanı"])
            length = int(row["Uzunluk"])
            bonus = {2:1.0, 3:1.08, 4:1.14, 5:1.20}.get(length,1.0)
            for n in nums:
                score[n] += base * bonus
    region_idx = region_df.set_index("Bölge")["Blok Bölge Puanı"].to_dict() if region_df is not None and not region_df.empty else {}
    maxscore = max(score.values(), default=1.0)
    rows = []
    for n in range(1,81):
        candidate = score.get(n,0.0)/maxscore*100.0
        region = float(region_idx.get(ten_band_name(n),0.0))
        rows.append({"Sayı":n, "Blok Zekâsı":round(0.72*candidate+0.28*region,2)})
    return pd.DataFrame(rows)


def decorate_master_v184(df, master18, block_birth, region_df, lookback=600):
    intel = block_intelligence_number_scores_v184(block_birth, region_df)
    penalty = block_overfollow_penalty_v184(df, lookback=lookback)
    out = master18.merge(intel,on="Sayı",how="left").merge(penalty,on="Sayı",how="left").fillna(0)
    out["V18.4 Nefes Puanı"] = (
        0.82 * normalized_series(out["V18 Nefes Puanı"])
        + 0.18 * normalized_series(out["Blok Zekâsı"])
    ) * 100.0
    out["V18.4 Nefes Puanı"] -= 0.10 * out["Blok Takip Cezası"]
    out["V18.4 Nefes Puanı"] = out["V18.4 Nefes Puanı"].clip(0,100).round(2)
    return out.sort_values(["V18.4 Nefes Puanı","Sayı"], ascending=[False,True])


def generate_v184_coupons(master184, latest_set, skeleton, block_forecast, block_birth, size=7, count=5):
    """V18 kupon çeşitliliğini korur; Blok Doğum kuponunu basınca göre yapılandırır."""
    temp = master184.copy()
    temp["V18 Nefes Puanı"] = temp["V18.4 Nefes Puanı"]
    items = generate_v18_coupons(temp, latest_set, skeleton, size=size, count=count)
    if not items or block_birth is None or block_birth.empty:
        return items

    # Basınca göre bilinçli blok uzunluğu seçimi
    desired = 2
    if size >= 5 and float(block_forecast.get("5lü Olasılık %",0)) >= 55:
        desired = 5
    elif size >= 4 and float(block_forecast.get("4lü Olasılık %",0)) >= 52:
        desired = 4
    elif size >= 3 and float(block_forecast.get("3lü Olasılık %",0)) >= 48:
        desired = 3

    cand = block_birth[block_birth["Uzunluk"] == desired]
    if cand.empty:
        cand = block_birth[block_birth["Uzunluk"] <= min(desired,size)]
    if cand.empty:
        return items

    chosen_block = [int(x) for x in str(cand.iloc[0]["Blok"]).split("-")]
    score_idx = temp.set_index("Sayı")["V18.5 Nefes Puanı"].to_dict()

    for item in items:
        if item["Senaryo"] == "Blok Doğum":
            base = list(item["Kupon"])
            merged = list(dict.fromkeys(chosen_block + sorted(base, key=lambda n: score_idx.get(n,0), reverse=True)))
            item["Kupon"] = sorted(merged[:size])
            item["Senaryo"] = f"Blok Doğum {desired}lü"
            break
    return items


def block_pressure_backtest_v184(df, test_count=80, lookback=350, state_window=5):
    """Blok basıncı skorunun geçmişte 3+/4+/5+ blokları ayırma gücünü walk-forward test eder."""
    if len(df) < 100:
        return pd.DataFrame(), pd.DataFrame()
    start = max(60, len(df)-int(test_count))
    rows = []
    for i in range(start, len(df)):
        train = df.iloc[:i].copy()
        actual_set = set(int(df.iloc[i][c]) for c in NUM_COLS)
        actual = block_profile_v184(actual_set)
        forecast, _, _ = block_pressure_engine_v184(
            train, lookback=min(lookback,len(train)), state_window=state_window,
            target_time=str(df.iloc[i].Saat), top_matches=30
        )
        if not forecast:
            continue
        rows.append({
            "Çekiliş": int(df.iloc[i].Cekilis_No),
            "Basınç": forecast.get("Blok Basıncı",0),
            "Gerçek Maks": actual["Maks Blok"],
            "Gerçek Blok Adedi": actual["Blok Adedi"],
            "3+ Gerçek": int(actual["Maks Blok"]>=3),
            "4+ Gerçek": int(actual["Maks Blok"]>=4),
            "5+ Gerçek": int(actual["Maks Blok"]>=5),
        })
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()
    detail["Basınç Dilimi"] = pd.cut(detail["Basınç"], bins=[-1,40,60,75,101], labels=["Düşük","Orta","Yüksek","Çok yüksek"])
    summary = detail.groupby("Basınç Dilimi", observed=False).agg(
        Test=("Çekiliş","count"),
        Ort_Maks=("Gerçek Maks","mean"),
        Ort_Blok=("Gerçek Blok Adedi","mean"),
        Uc_Artı=("3+ Gerçek","mean"),
        Dort_Artı=("4+ Gerçek","mean"),
        Bes_Artı=("5+ Gerçek","mean"),
    ).reset_index()
    for c in ["Uc_Artı","Dort_Artı","Bes_Artı"]:
        summary[c+" %"] = (summary[c]*100).round(1)
    return detail, summary.drop(columns=["Uc_Artı","Dort_Artı","Bes_Artı"])


def block_location_engine_v185(df, block_birth, base_region_df, lookback=600):
    """
    Blok doğumunun yalnızca var/yok değil, NEREDE olacağına ayrı puan verir.
    10'luk bölgeler için:
      - son dönem blok yoğunluğu,
      - geçmiş blok doğumları,
      - komşu yoğunluğu,
      - bölge göçü,
      - aynı bölgeyi kör takip cezası
    birlikte değerlendirilir.
    """
    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    if len(work) < 20:
        return pd.DataFrame(), {}

    sets = row_sets(work)
    bands = [f"{i}-{i+9}" for i in range(1, 80, 10)]

    recent_windows = [5, 10, 20, 50]
    recent_scores = {b: 0.0 for b in bands}
    weights = {5: 0.34, 10: 0.27, 20: 0.22, 50: 0.17}

    for w in recent_windows:
        sub = sets[-min(w, len(sets)):]
        counts = Counter()
        for s in sub:
            for block in maximal_blocks_v184(s):
                center = int(round(float(np.mean(block))))
                counts[ten_band_name(center)] += max(1, len(block)-1)
        mx = max(counts.values(), default=1.0)
        for b in bands:
            recent_scores[b] += weights[w] * (counts.get(b, 0.0) / mx * 100.0)

    # Aday bloklardan gelen konum puanı
    birth_scores = {b: 0.0 for b in bands}
    if block_birth is not None and not block_birth.empty:
        for _, row in block_birth.head(160).iterrows():
            nums = [int(x) for x in str(row["Blok"]).split("-")]
            if not nums:
                continue
            center = int(round(float(np.mean(nums))))
            band = ten_band_name(center)
            length = int(row["Uzunluk"])
            val = float(row["Blok Doğum Puanı"]) * {2:1.0,3:1.10,4:1.18,5:1.26}.get(length,1.0)
            birth_scores[band] += val
    mx_birth = max(birth_scores.values(), default=1.0)
    birth_scores = {b: birth_scores[b]/mx_birth*100.0 for b in bands}

    # V18.4 benzer-durum bölge tablosu
    base_region = {}
    if base_region_df is not None and not base_region_df.empty:
        base_region = base_region_df.set_index("Bölge")["Blok Bölge Puanı"].to_dict()

    # Son 2 çekilişteki baskın blok bölgelerini kör takip etme cezası
    last_region_counts = Counter()
    for s in sets[-2:]:
        for block in maximal_blocks_v184(s):
            center = int(round(float(np.mean(block))))
            last_region_counts[ten_band_name(center)] += max(1, len(block)-1)

    # Blok göçü: geçmişte bir çekilişte baskın bölgeden sonraki çekilişte hangi bölgeye geçilmiş?
    migration = defaultdict(Counter)
    for i in range(len(sets)-1):
        cur_blocks = maximal_blocks_v184(sets[i])
        nxt_blocks = maximal_blocks_v184(sets[i+1])
        if not cur_blocks or not nxt_blocks:
            continue
        cur_counts = Counter()
        nxt_counts = Counter()
        for b in cur_blocks:
            cur_counts[ten_band_name(int(round(float(np.mean(b)))))] += max(1, len(b)-1)
        for b in nxt_blocks:
            nxt_counts[ten_band_name(int(round(float(np.mean(b)))))] += max(1, len(b)-1)
        if cur_counts and nxt_counts:
            cur_band = cur_counts.most_common(1)[0][0]
            for nb, val in nxt_counts.items():
                migration[cur_band][nb] += val

    current_band = None
    if last_region_counts:
        current_band = last_region_counts.most_common(1)[0][0]

    migration_scores = {b: 0.0 for b in bands}
    if current_band and migration[current_band]:
        mx_m = max(migration[current_band].values(), default=1.0)
        for b in bands:
            migration_scores[b] = migration[current_band].get(b,0.0)/mx_m*100.0

    rows = []
    for b in bands:
        follow_penalty = 0.0
        if current_band == b and last_region_counts.get(b,0) > 0:
            # aynı bölgeyi kör takip etme cezası; tamamen yasaklama değil
            follow_penalty = min(28.0, 8.0 + 4.0*last_region_counts[b])

        raw = (
            0.27 * float(base_region.get(b,0.0))
            + 0.24 * recent_scores[b]
            + 0.29 * birth_scores[b]
            + 0.20 * migration_scores[b]
            - follow_penalty
        )
        rows.append({
            "Bölge": b,
            "Konum Puanı": round(max(0.0, min(100.0, raw)), 2),
            "Benzer Durum": round(float(base_region.get(b,0.0)),2),
            "Son Dönem": round(recent_scores[b],2),
            "Aday Blok": round(birth_scores[b],2),
            "Göç Desteği": round(migration_scores[b],2),
            "Takip Cezası": round(follow_penalty,2),
        })

    out = pd.DataFrame(rows).sort_values("Konum Puanı", ascending=False).reset_index(drop=True)
    info = {
        "Ana Bölge": str(out.iloc[0]["Bölge"]) if len(out) else "-",
        "Ana Puan": float(out.iloc[0]["Konum Puanı"]) if len(out) else 0.0,
        "Alternatif Bölge": str(out.iloc[1]["Bölge"]) if len(out) > 1 else "-",
        "Alternatif Puan": float(out.iloc[1]["Konum Puanı"]) if len(out) > 1 else 0.0,
        "Önceki Baskın Bölge": current_band or "-",
    }
    return out, info


def common_core_brake_v185(items, master185, max_share=0.80):
    """
    Aynı sayının tüm kuponlara kör biçimde yayılmasını sınırlar.
    Çok yüksek puanlı sayılar bile en fazla yaklaşık %80 kuponda tutulur.
    Yerine benzer puanlı ama kullanılma oranı düşük adaylar seçilir.
    """
    if not items or len(items) < 3:
        return items

    n_items = len(items)
    max_count = max(2, int(np.ceil(n_items * float(max_share))))
    score_col = "V18.5 Nefes Puanı" if "V18.5 Nefes Puanı" in master185.columns else "V18.4 Nefes Puanı"
    score_idx = master185.set_index("Sayı")[score_col].to_dict()
    usage = Counter(n for item in items for n in item["Kupon"])

    # Önce en aşırı ortak sayıları ele al.
    offenders = [n for n,c in usage.items() if c > max_count]
    offenders.sort(key=lambda n: usage[n], reverse=True)

    ranked = [int(n) for n in master185.sort_values(score_col, ascending=False)["Sayı"]]

    for n in offenders:
        while usage[n] > max_count:
            # Bu sayıyı en düşük katkı yapan / en fazla ortaklı kupondan çıkar.
            candidate_items = [
                (idx, item) for idx,item in enumerate(items) if n in item["Kupon"]
            ]
            if not candidate_items:
                break

            # Blok doğum kuponunda, n gerçek blok yapısının parçasıysa mümkün olduğunca koru.
            def removable_priority(pair):
                idx, item = pair
                scenario = str(item.get("Senaryo",""))
                keep_bonus = 1 if "Blok Doğum" in scenario else 0
                return (keep_bonus, score_idx.get(n,0), -idx)

            idx, item = sorted(candidate_items, key=removable_priority)[0]
            current = list(item["Kupon"])

            replacement = None
            for alt in ranked:
                if alt in current:
                    continue
                if usage[alt] >= max_count:
                    continue
                # aşırı uzun ardışık zincir yaratma
                trial = set(current)
                trial.discard(n)
                trial.add(alt)
                creates_four = any(
                    {k,k+1,k+2,k+3}.issubset(trial)
                    for k in range(1,78)
                )
                if creates_four and "Blok Doğum" not in str(item.get("Senaryo","")):
                    continue
                replacement = alt
                break

            if replacement is None:
                break

            current.remove(n)
            current.append(replacement)
            item["Kupon"] = sorted(current)
            usage[n] -= 1
            usage[replacement] += 1

    return items


def block_candidate_location_filter_v185(block_birth, location_df):
    """Blok adaylarını konum motoru puanıyla yeniden sıralar."""
    if block_birth is None or block_birth.empty:
        return block_birth
    if location_df is None or location_df.empty:
        return block_birth

    loc = location_df.set_index("Bölge")["Konum Puanı"].to_dict()
    out = block_birth.copy()
    region_score = []
    for _, row in out.iterrows():
        nums = [int(x) for x in str(row["Blok"]).split("-")]
        center = int(round(float(np.mean(nums)))) if nums else 1
        region_score.append(float(loc.get(ten_band_name(center),0.0)))
    out["Konum Puanı"] = region_score
    out["V18.5 Blok Puanı"] = (
        0.62 * normalized_series(out["Blok Doğum Puanı"])
        + 0.38 * normalized_series(out["Konum Puanı"])
    ) * 100.0
    return out.sort_values(
        ["V18.5 Blok Puanı","Uzunluk","Blok"],
        ascending=[False,False,True]
    ).reset_index(drop=True)


def block_lifecycle_number_scores_v1854(df, lookback=600):
    """
    V18.5.4 Blok Yaşam Döngüsü Motoru.
    Son çekilişteki blokları kör taşımak yerine geçmişte aynı blokların
    devam / büyüme / küçülme / kayma / kırılma davranışını sayı puanına çevirir.
    """
    growth = block_growth_break_table_v184(df, lookback=lookback)
    support = Counter()
    risk = Counter()
    if growth is None or growth.empty:
        return pd.DataFrame({
            "Sayı": range(1, 81),
            "Blok Yaşam": [0.0] * 80,
            "Blok Kırılma Riski": [0.0] * 80,
        })

    for _, row in growth.iterrows():
        nums = [int(x) for x in str(row["Mevcut Blok"]).split("-") if str(x).strip()]
        cases = max(int(row.get("Geçmiş Olay", 0)), 0)
        confidence = min(1.0, cases / 18.0)
        exact = float(row.get("Aynen %", 0.0))
        grow = float(row.get("Büyüme %", 0.0))
        shrink = float(row.get("Küçülme %", 0.0))
        shift = float(row.get("Kayma %", 0.0))
        broken = float(row.get("Kırılma %", 0.0))

        keep = confidence * (0.42 * exact + 0.32 * grow + 0.16 * shift + 0.10 * shrink)
        break_risk = confidence * broken
        for n in nums:
            support[n] = max(support[n], keep)
            risk[n] = max(risk[n], break_risk)
        # Büyüme/kayma ihtimali varsa bloğun iki yan komşusuna kontrollü destek ver.
        if nums:
            edge_support = confidence * (0.55 * grow + 0.45 * shift)
            for n in (min(nums)-1, max(nums)+1):
                if 1 <= n <= 80:
                    support[n] = max(support[n], edge_support)

    rows = []
    for n in range(1, 81):
        life = max(0.0, min(100.0, support.get(n, 0.0) - 0.55 * risk.get(n, 0.0)))
        rows.append({
            "Sayı": n,
            "Blok Yaşam": round(life, 2),
            "Blok Kırılma Riski": round(risk.get(n, 0.0), 2),
        })
    return pd.DataFrame(rows)



def region_fatigue_scores_v1855(df, window=12):
    """
    Bölge Yaşam/Yorgunluk Motoru.
    Son birkaç elde aşırı yoğunlaşan 10'luk bandı kör takip etmeyi frenler;
    uzun dönem ortalamasına göre beklenenden az kullanılan banda küçük geri dönüş desteği verir.
    """
    regions = [f"{a}-{a+9}" for a in range(1, 81, 10)]
    if df is None or df.empty:
        return pd.DataFrame({"Bölge": regions, "Bölge Yorgunluğu": 0.0, "Bölge Geri Dönüş": 0.0})

    recent = df.tail(max(4, min(int(window), len(df))))
    base = df.tail(min(300, len(df)))

    def counts(frame):
        c = Counter()
        for _, row in frame.iterrows():
            for col in NUM_COLS:
                c[ten_band_name(int(row[col]))] += 1
        return c

    rc = counts(recent)
    bc = counts(base)
    recent_den = max(len(recent) * 20, 1)
    base_den = max(len(base) * 20, 1)

    rows = []
    for region in regions:
        rshare = rc.get(region, 0) / recent_den
        bshare = bc.get(region, 0) / base_den
        # 10'luk bant için nötr pay yaklaşık %12.5; karşılaştırmayı kendi geçmişine göre yapıyoruz.
        excess = max(0.0, rshare - bshare)
        deficit = max(0.0, bshare - rshare)
        rows.append({
            "Bölge": region,
            "Bölge Yorgunluğu": round(min(100.0, excess * 900.0), 2),
            "Bölge Geri Dönüş": round(min(100.0, deficit * 700.0), 2),
        })
    return pd.DataFrame(rows)


def block_shift_variant_scores_v1855(df):
    """
    Son gerçek blokların ±1/±2 komşu varyantlarını ayrı puanlar.
    37-38-39 tahmini / 36-37-38 gerçek gibi yön hatalarını azaltmayı amaçlar.
    """
    if df is None or df.empty:
        return pd.DataFrame({"Sayı": range(1,81), "Blok Kayma Varyantı": [0.0]*80})

    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
    blocks = [b for b in consecutive_blocks(latest_set) if len(b) >= 2]
    score = Counter()

    for block in blocks:
        L = len(block)
        # Aynı blok küçük destek; ±1 en güçlü alternatif, ±2 daha temkinli.
        for shift, weight in [(0, 0.35), (-1, 1.00), (1, 1.00), (-2, 0.55), (2, 0.55)]:
            shifted = [n + shift for n in block if 1 <= n + shift <= 80]
            if len(shifted) != L:
                continue
            for n in shifted:
                score[n] = max(score[n], 100.0 * weight)

    return pd.DataFrame({
        "Sayı": range(1,81),
        "Blok Kayma Varyantı": [round(score.get(n,0.0),2) for n in range(1,81)],
    })


def core_confidence_scores_v1855(master):
    """
    Ortak çekirdek için tek sinyale değil çoklu bağımsız sinyal uzlaşmasına bakar.
    """
    out = master[["Sayı"]].copy()

    def s(name):
        if name in master.columns:
            return normalized_series(pd.to_numeric(master[name], errors="coerce").fillna(0.0))
        return pd.Series(0.0, index=master.index)

    consensus = (
        0.20*s("Taşıma")
        + 0.16*s("Dönüş")
        + 0.16*s("Benzer")
        + 0.16*s("Bölge Puanı")
        + 0.16*s("Blok Zekâsı")
        + 0.16*s("Küme Tamamlama")
    )
    out["Ortak Çekirdek Güveni"] = (consensus * 100.0).round(2)
    return out


def decorate_master_v1855(df, master185):
    """
    V18.5.5 katmanı:
    - bölge yorgunluğu / geri dönüş
    - ±1/±2 blok kayma varyantı
    - ortak çekirdek güveni
    Mevcut V18.5.4 puanını ana omurga olarak korur.
    """
    out = master185.copy()

    fatigue = region_fatigue_scores_v1855(df, window=12)
    fmap = fatigue.set_index("Bölge").to_dict("index") if not fatigue.empty else {}
    out["Bölge Yorgunluğu 55"] = [
        float(fmap.get(ten_band_name(int(n)), {}).get("Bölge Yorgunluğu", 0.0))
        for n in out["Sayı"]
    ]
    out["Bölge Geri Dönüş 55"] = [
        float(fmap.get(ten_band_name(int(n)), {}).get("Bölge Geri Dönüş", 0.0))
        for n in out["Sayı"]
    ]

    shift = block_shift_variant_scores_v1855(df)
    out = out.merge(shift, on="Sayı", how="left")
    core = core_confidence_scores_v1855(out)
    out = out.merge(core, on="Sayı", how="left")

    for c in ["Blok Kayma Varyantı","Ortak Çekirdek Güveni","Bölge Yorgunluğu 55","Bölge Geri Dönüş 55"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    out["V18.5.5 Nefes Puanı"] = (
        0.82 * normalized_series(out["V18.5 Nefes Puanı"])
        + 0.07 * normalized_series(out["Ortak Çekirdek Güveni"])
        + 0.05 * normalized_series(out["Blok Kayma Varyantı"])
        + 0.06 * normalized_series(out["Bölge Geri Dönüş 55"])
    ) * 100.0

    # Bölgeyi ve son bloğu kör takip etmesin.
    out["V18.5.5 Nefes Puanı"] -= 0.10 * out["Bölge Yorgunluğu 55"]
    if "Blok Kırılma Riski" in out.columns:
        out["V18.5.5 Nefes Puanı"] -= 0.04 * pd.to_numeric(
            out["Blok Kırılma Riski"], errors="coerce"
        ).fillna(0.0)

    out["V18.5.5 Nefes Puanı"] = out["V18.5.5 Nefes Puanı"].clip(0,100).round(2)
    # Eski üreticiyi bozmadan yeni puanı kullandır.
    out["V18.5 Nefes Puanı"] = out["V18.5.5 Nefes Puanı"]
    return out.sort_values(["V18.5.5 Nefes Puanı","Sayı"], ascending=[False,True])


def diversify_coupons_v1855(items, master, max_common=4):
    """
    Beş kuponun aynı hataya yığılmasını azaltır.
    Bir sayı kuponların %80'inden fazlasına yayılıyorsa ve ortak çekirdek güveni
    çok yüksek değilse düşük puanlı kullanımlardan kontrollü çıkarılır.
    """
    if not items:
        return items

    score_col = "V18.5.5 Nefes Puanı" if "V18.5.5 Nefes Puanı" in master.columns else "V18.5 Nefes Puanı"
    idx = master.set_index("Sayı")
    usage = Counter(n for item in items for n in item.get("Kupon", []))
    limit = min(max_common, max(2, int(round(len(items)*0.80))))

    for n, used in list(usage.items()):
        if used <= limit:
            continue
        confidence = float(idx.loc[n, "Ortak Çekirdek Güveni"]) if n in idx.index and "Ortak Çekirdek Güveni" in idx.columns else 0.0
        if confidence >= 82.0:
            continue

        candidate_items = sorted(
            [item for item in items if n in item.get("Kupon", [])],
            key=lambda item: 0 if "İskelet" not in str(item.get("Senaryo","")) else 1
        )

        for item in candidate_items:
            if usage[n] <= limit:
                break
            coupon = list(item["Kupon"])
            alternatives = [
                int(x) for x in master["Sayı"]
                if int(x) not in coupon and usage[int(x)] < limit
            ]
            replacement = None
            for alt in alternatives:
                # Aynı kuponda aşırı 4'lü blok yaratma.
                trial = set(coupon)
                trial.discard(n)
                trial.add(alt)
                creates_four = any({k,k+1,k+2,k+3}.issubset(trial) for k in range(1,78))
                if creates_four and "Blok Doğum" not in str(item.get("Senaryo","")):
                    continue
                replacement = alt
                break
            if replacement is not None:
                coupon.remove(n)
                coupon.append(replacement)
                item["Kupon"] = sorted(coupon)
                usage[n] -= 1
                usage[replacement] += 1
    return items



def carry_identity_scores_v1856(df, target_time=None, window=500):
    """
    V18.5.6 Seri Devam/Kırılma + Taşıma Kimliği Motoru.

    Mevcut 'kaç sayı taşınır?' iskelet tahminini DEĞİŞTİRMEZ.
    Yalnızca son çekilişteki 20 sayı arasından hangilerinin taşınmaya daha
    uygun olduğunu geçmişte aynı seri uzunluğu, kısa dönem devam ve mevcut
    taşıma puanıyla ayırt etmeye çalışır.
    """
    if df is None or len(df) < 3:
        return pd.DataFrame({
            "Sayı": range(1, 81),
            "Taşıma Kimlik": [0.0] * 80,
            "Seri Devam %": [0.0] * 80,
            "Seri Örnek": [0] * 80,
            "Mevcut Seri 56": [0] * 80,
        })

    base = carryover_number_scores(
        df,
        target_time or str(df.iloc[-1].Saat),
        window=min(int(window), len(df)),
    )
    base_map = base.set_index("Sayı")["Taşıma Puanı"].to_dict() if not base.empty else {}
    latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
    sets = row_sets(df.tail(min(int(window), len(df))).reset_index(drop=True))
    streaks_now = streak_table(df).set_index("Sayı")

    rows = []
    for n in range(1, 81):
        current_streak = int(streaks_now.loc[n, "Mevcut seri"]) if n in streaks_now.index else 0
        cases = 0
        cont = 0

        if n in latest_set and current_streak > 0:
            # Geçmişte, n sayısının çekiliş i itibarıyla aynı seri uzunluğuna
            # eriştiği anları bul ve sonraki elde devam edip etmediğini ölç.
            run = 0
            for i in range(len(sets) - 1):
                if n in sets[i]:
                    run += 1
                else:
                    run = 0
                if run == current_streak:
                    cases += 1
                    if n in sets[i + 1]:
                        cont += 1

        conditional = (cont / cases) if cases else 0.0
        base_score = float(base_map.get(n, 0.0)) if n in latest_set else 0.0

        # Küçük örneklerde koşullu oran aşırı hükmetmesin.
        reliability = min(1.0, cases / 14.0)
        conditional_score = conditional * 100.0
        identity = (
            (0.68 * base_score)
            + (0.32 * (reliability * conditional_score + (1.0 - reliability) * base_score))
        )

        # 4+ el seri varsa kör devamı önlemek için hafif fren.
        if current_streak >= 4:
            identity *= 0.93

        rows.append({
            "Sayı": n,
            "Taşıma Kimlik": round(max(0.0, min(100.0, identity)), 2),
            "Seri Devam %": round(conditional_score, 2),
            "Seri Örnek": int(cases),
            "Mevcut Seri 56": int(current_streak),
        })

    return pd.DataFrame(rows)


def block_regime_micro_v1856(df, lookback=500):
    """
    V18.5.6 Blok Rejim + Mikro-Konum Motoru.

    Son çekilişin blok karakterine benzeyen geçmiş çekilişleri bulur ve onların
    bir sonraki sonuçlarında:
      - tek uzun blok (4+)
      - çoklu küçük blok (en az iki ayrı 2/3'lü)
      - seyrek/karışık
    rejimlerini ölçer.

    Aynı zamanda benzer geçmişlerin bir sonraki çekilişindeki blok sayılarına
    mikro-konum puanı verir. Bu sayede doğru 10'luk bölge içinde yanlış
    34-35-36 yerine örn. 39-40 veya ±1/±2 komşu varyantlar daha iyi ayrıştırılır.
    """
    empty_summary = {
        "Uzun Blok %": 0.0,
        "Çoklu Küçük %": 0.0,
        "Seyrek/Karışık %": 0.0,
        "Benzer Olay": 0,
        "Önerilen Rejim": "Karışık",
    }
    empty_micro = pd.DataFrame({
        "Sayı": range(1,81),
        "Blok Mikro 56": [0.0]*80,
        "Blok Sonraki Görülme 56": [0.0]*80,
    })
    if df is None or len(df) < 30:
        return empty_summary, empty_micro

    work = df.tail(min(int(lookback), len(df))).reset_index(drop=True)
    sets = row_sets(work)

    def signature(s):
        blocks = consecutive_blocks(s)
        pair_count = sum(max(len(b)-1, 0) for b in blocks)
        max_len = max([len(b) for b in blocks], default=1)
        block_count = len(blocks)
        small_count = sum(1 for b in blocks if 2 <= len(b) <= 3)
        return pair_count, max_len, block_count, small_count

    cur_sig = signature(sets[-1])
    matches = []
    for i in range(len(sets) - 1):
        sig = signature(sets[i])
        # Yakın komşuluk karakterleri; birebir eşleşmeye zorlamıyoruz.
        dist = (
            1.2 * abs(sig[0] - cur_sig[0])
            + 1.8 * abs(sig[1] - cur_sig[1])
            + 1.0 * abs(sig[2] - cur_sig[2])
            + 0.8 * abs(sig[3] - cur_sig[3])
        )
        matches.append((dist, i))

    matches = sorted(matches, key=lambda x: x[0])[:min(45, max(15, len(matches)//5))]
    long_count = 0
    multi_small_count = 0
    sparse_count = 0
    micro = Counter()
    appear = Counter()
    total = 0

    for _, i in matches:
        nxt = sets[i+1]
        blocks = consecutive_blocks(nxt)
        total += 1
        has_long = any(len(b) >= 4 for b in blocks)
        small_blocks = [b for b in blocks if 2 <= len(b) <= 3]

        if has_long:
            long_count += 1
        elif len(small_blocks) >= 2:
            multi_small_count += 1
        else:
            sparse_count += 1

        for b in blocks:
            # Küçük blok rejiminde 2/3'lüleri, uzun rejimde 4+'ları ayrı
            # ağırlıkla ama tamamını mikro konum öğrenmesine dahil et.
            weight = 1.0 + 0.18 * max(0, len(b)-2)
            for n in b:
                micro[n] += weight
                appear[n] += 1

    denom = max(total, 1)
    probs = {
        "Uzun Blok %": 100.0 * long_count / denom,
        "Çoklu Küçük %": 100.0 * multi_small_count / denom,
        "Seyrek/Karışık %": 100.0 * sparse_count / denom,
    }
    regime = max(probs, key=probs.get).replace(" %","")
    summary = {
        **{k: round(v,2) for k,v in probs.items()},
        "Benzer Olay": int(total),
        "Önerilen Rejim": regime,
    }

    max_micro = max(micro.values()) if micro else 1.0
    rows = []
    for n in range(1,81):
        rows.append({
            "Sayı": n,
            "Blok Mikro 56": round(100.0 * micro.get(n,0.0) / max_micro, 2),
            "Blok Sonraki Görülme 56": round(100.0 * appear.get(n,0) / denom, 2),
        })
    return summary, pd.DataFrame(rows)


def candidate_quality_v1856(df, master1855, target_time=None):
    """
    Aday havuzu kalitesini yükselten son katman.
    V18.5.5 puanı ana omurgadır; taşıma kimliği ve blok mikro-konumu yalnızca
    kontrollü ek bilgi olarak kullanılır.
    """
    out = master1855.copy()
    carry = carry_identity_scores_v1856(df, target_time=target_time, window=500)
    regime, micro = block_regime_micro_v1856(df, lookback=500)

    out = out.merge(carry, on="Sayı", how="left").merge(micro, on="Sayı", how="left")
    for c in ["Taşıma Kimlik","Seri Devam %","Seri Örnek","Mevcut Seri 56",
              "Blok Mikro 56","Blok Sonraki Görülme 56"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    def nrm(name):
        return normalized_series(out[name]) if name in out.columns else pd.Series(0.0, index=out.index)

    out["Aday Kalitesi 56"] = (
        0.68 * nrm("V18.5.5 Nefes Puanı")
        + 0.13 * nrm("Taşıma Kimlik")
        + 0.10 * nrm("Blok Mikro 56")
        + 0.05 * nrm("Ortak Çekirdek Güveni")
        + 0.04 * nrm("Benzer")
    ) * 100.0

    # Eski yanlış blokların peşinden kör gitmeyi azalt.
    if "Blok Kırılma Riski" in out.columns:
        out["Aday Kalitesi 56"] -= 0.035 * pd.to_numeric(
            out["Blok Kırılma Riski"], errors="coerce"
        ).fillna(0.0)

    out["Aday Kalitesi 56"] = out["Aday Kalitesi 56"].clip(0,100).round(2)
    out["V18.5.6 Nefes Puanı"] = (
        0.84 * nrm("V18.5.5 Nefes Puanı")
        + 0.16 * normalized_series(out["Aday Kalitesi 56"])
    ) * 100.0
    out["V18.5.6 Nefes Puanı"] = out["V18.5.6 Nefes Puanı"].clip(0,100).round(2)

    # Eski kupon üreticilerinin beklediği alanı koru.
    out["V18.5 Nefes Puanı"] = out["V18.5.6 Nefes Puanı"]
    return out.sort_values(["V18.5.6 Nefes Puanı","Sayı"], ascending=[False,True]), regime


def _best_block_candidate_v1856(block_birth185, desired_len):
    if block_birth185 is None or block_birth185.empty:
        return []
    cand = block_birth185.copy()
    if "Uzunluk" in cand.columns:
        exact = cand[pd.to_numeric(cand["Uzunluk"], errors="coerce") == int(desired_len)]
        if not exact.empty:
            cand = exact
        else:
            cand = cand[
                pd.to_numeric(cand["Uzunluk"], errors="coerce") <= int(desired_len)
            ]
    if cand.empty:
        return []
    sort_cols = [c for c in ["V18.5 Blok Puanı","Blok Doğum Puanı","Konum Puanı"] if c in cand.columns]
    if sort_cols:
        cand = cand.sort_values(sort_cols, ascending=[False]*len(sort_cols))
    try:
        return [int(x) for x in str(cand.iloc[0]["Blok"]).split("-")]
    except Exception:
        return []


def apply_block_regime_to_items_v1856(items, master, block_birth185, regime_summary, size):
    """
    Blok kuponunu rejime göre düzeltir:
      - Çoklu küçük baskınsa 4/5'li tek bloğa zorlamaz, 2/3'lü mikro blok kullanır.
      - Uzun blok baskınsa 3/4'lü adayın büyümesine izin verir.
    """
    if not items:
        return items

    multi = float(regime_summary.get("Çoklu Küçük %",0.0))
    longp = float(regime_summary.get("Uzun Blok %",0.0))
    if multi >= longp + 8:
        desired = 2 if multi >= 48 else 3
        regime_label = "Çoklu Küçük"
    elif longp >= multi + 8:
        desired = min(4, max(3, int(size)-3))
        regime_label = "Uzun Blok"
    else:
        desired = 3
        regime_label = "Dengeli Blok"

    chosen = _best_block_candidate_v1856(block_birth185, desired)
    if not chosen:
        return items

    score_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in master.columns else "V18.5 Nefes Puanı"
    score_map = master.set_index("Sayı")[score_col].to_dict()

    for item in items:
        if "Blok" in str(item.get("Senaryo","")):
            rest = [
                int(n) for n in master.sort_values(score_col, ascending=False)["Sayı"]
                if int(n) not in chosen
            ]
            coupon = list(chosen)
            for n in rest:
                if len(coupon) >= int(size):
                    break
                coupon.append(n)
            item["Kupon"] = sorted(set(coupon))[:int(size)]
            item["Senaryo"] = f"Blok Rejim {desired}lü/{regime_label}"
            break
    return items



def carry_continue_break_v18562(master, latest_set):
    """
    Son çekilişteki sayıları DEVAM / BELİRSİZ / KIRILMA olarak ayırır.
    Var olan Taşıma Kimlik puanını bozmaz; seri devam oranı, örnek güveni ve
    yaşayan kupon puanıyla ikinci bir kimlik katmanı üretir.
    """
    out = master.copy()
    latest_set = set(int(x) for x in latest_set)
    for c in ["Taşıma Kimlik","Seri Devam %","Seri Örnek","Mevcut Seri 56"]:
        if c not in out.columns:
            out[c] = 0.0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    base_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in out.columns else "V18.5 Nefes Puanı"
    base = normalized_series(out[base_col])
    ident = normalized_series(out["Taşıma Kimlik"])
    cont = (out["Seri Devam %"] / 100.0).clip(0,1)
    rel = (out["Seri Örnek"] / 18.0).clip(0,1)

    # Küçük örnekte seri yüzdesi tek başına hükmetmesin.
    out["Devam Puanı 562"] = (
        0.52 * ident
        + 0.24 * base
        + 0.24 * (rel * cont + (1.0-rel) * ident)
    ) * 100.0

    # Uzun seride kör devamı hafifçe frenle.
    out.loc[out["Mevcut Seri 56"] >= 4, "Devam Puanı 562"] *= 0.94
    out.loc[~out["Sayı"].astype(int).isin(latest_set), "Devam Puanı 562"] = 0.0
    out["Devam Puanı 562"] = out["Devam Puanı 562"].clip(0,100).round(2)

    out["Taşıma Kararı 562"] = "YENİ ADAY"
    mask = out["Sayı"].astype(int).isin(latest_set)
    out.loc[mask & (out["Devam Puanı 562"] >= 62), "Taşıma Kararı 562"] = "DEVAM"
    out.loc[mask & (out["Devam Puanı 562"] >= 45) & (out["Devam Puanı 562"] < 62), "Taşıma Kararı 562"] = "BELİRSİZ"
    out.loc[mask & (out["Devam Puanı 562"] < 45), "Taşıma Kararı 562"] = "KIRILMA"
    return out


def _micro_band_maps_v18562(master):
    """10'luk bölgelerin mikro gücünü ve sıralamasını üretir."""
    work = master.copy()
    if "Blok Mikro 56" not in work.columns:
        work["Blok Mikro 56"] = 0.0
    if "Blok Sonraki Görülme 56" not in work.columns:
        work["Blok Sonraki Görülme 56"] = 0.0
    work["Bölge562"] = work["Sayı"].astype(int).map(ten_band_name)
    grp = work.groupby("Bölge562", as_index=False).agg(
        Mikro=("Blok Mikro 56","mean"),
        Görülme=("Blok Sonraki Görülme 56","mean"),
    )
    grp["Bölge Puanı 562"] = 0.68*grp["Mikro"] + 0.32*grp["Görülme"]
    return grp.sort_values("Bölge Puanı 562", ascending=False)


def regime_distribution_coupon_v18562(coupon, master, regime_summary, size=7):
    """
    Çoklu Küçük rejimde tek 10'luk bölgeye yığılmayı kırar.
    En güçlü 2-3 mikro bölgenin temsil edilmesini sağlar.
    Uzun blok rejiminde müdahale etmez.
    """
    coupon = [int(x) for x in coupon]
    size = int(size)
    multi = float(regime_summary.get("Çoklu Küçük %",0.0))
    longp = float(regime_summary.get("Uzun Blok %",0.0))
    if multi < longp + 8 or not coupon:
        return sorted(coupon[:size])

    score_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in master.columns else "V18.5 Nefes Puanı"
    work = master.copy()
    work["Bölge562"] = work["Sayı"].astype(int).map(ten_band_name)
    bands = _micro_band_maps_v18562(work)
    target_bands = bands.head(3 if multi >= 70 else 2)["Bölge562"].tolist()

    # Çoklu küçük rejimde 7'li kolonda aynı 10'luk bölgeden en fazla 3 sayı.
    cap = 3
    selected = []
    counts = Counter()

    # Önce 2-3 güçlü mikro bölgeye birer temsilci.
    for band in target_bands:
        cand = work[work["Bölge562"] == band].copy()
        cand["R562"] = (
            0.46*normalized_series(cand[score_col])
            + 0.34*normalized_series(cand["Blok Mikro 56"])
            + 0.20*normalized_series(cand["Blok Sonraki Görülme 56"])
        )
        for n in cand.sort_values("R562", ascending=False)["Sayı"].astype(int):
            if n not in selected:
                selected.append(n); counts[band] += 1
                break

    # Mevcut kuponun güçlü adaylarını koru ama yığılma tavanına uy.
    score_map = work.set_index("Sayı")[score_col].to_dict()
    for n in sorted(coupon, key=lambda x: score_map.get(int(x),0), reverse=True):
        band = ten_band_name(int(n))
        if n not in selected and counts[band] < cap:
            selected.append(n); counts[band] += 1
        if len(selected) >= size:
            break

    # Eksik yerleri mikro+temel puanla, yine bölge tavanıyla doldur.
    work["R562"] = (
        0.52*normalized_series(work[score_col])
        + 0.30*normalized_series(work["Blok Mikro 56"])
        + 0.18*normalized_series(work["Blok Sonraki Görülme 56"])
    )
    for n in work.sort_values("R562", ascending=False)["Sayı"].astype(int):
        band = ten_band_name(int(n))
        if n not in selected and counts[band] < cap:
            selected.append(n); counts[band] += 1
        if len(selected) >= size:
            break
    return sorted(selected[:size])


def apply_regime_distribution_v18562(items, master, regime_summary, size=7):
    """Tüm yaşayan kuponlara rejim-kupon uyum katmanı uygular."""
    out = []
    for item in (items or []):
        ni = dict(item)
        ni["Kupon"] = regime_distribution_coupon_v18562(
            ni.get("Kupon", []), master, regime_summary, size=size
        )
        out.append(ni)
    return out



def carry_identity_v18563(df, master, latest_set, expected_carry, lookback=500, k=55):
    """Taşıma adedini değiştirmeden, taşıma kimliğini benzer geçmiş geçişlerden puanlar."""
    out = master.copy()
    latest_set = set(int(x) for x in latest_set)
    oldcol = "Devam Puanı 562" if "Devam Puanı 562" in out.columns else "Taşıma Kimlik"
    if df is None or len(df) < 3 or not latest_set:
        out["Taşıma Kimlik 563"] = pd.to_numeric(out.get(oldcol, 0.0), errors="coerce").fillna(0.0)
        return out
    rows=[]
    for _,r in df.tail(int(lookback)+2).iterrows():
        s=set()
        for c in NUM_COLS:
            if c in df.columns and pd.notna(r[c]):
                s.add(int(r[c]))
        rows.append(s)
    events=[]
    for i in range(len(rows)-1):
        a,b=rows[i],rows[i+1]
        if not a or not b: continue
        carry=len(a&b)
        jac=len(a&latest_set)/max(1,len(a|latest_set))
        ba=Counter(ten_band_name(n) for n in a); bl=Counter(ten_band_name(n) for n in latest_set)
        dist=sum(abs(ba.get(x,0)-bl.get(x,0)) for x in set(ba)|set(bl))
        bsim=max(0.0,1.0-dist/40.0)
        csim=max(0.0,1.0-abs(float(carry)-float(expected_carry))/8.0)
        events.append((0.46*csim+0.34*jac+0.20*bsim,a,b))
    events=sorted(events,key=lambda x:x[0],reverse=True)[:max(12,int(k))]
    base=out.set_index("Sayı")
    scores={}; supports={}
    for n in latest_set:
        num=den=0.0
        for sim,a,b in events:
            if n in a:
                den+=sim
                if n in b: num+=sim
        hist=100.0*num/den if den else 0.0
        old=float(base.loc[n].get(oldcol,0.0)) if n in base.index else 0.0
        scores[n]=0.64*hist+0.36*old; supports[n]=den
    out["Taşıma Kimlik 563"]=out["Sayı"].astype(int).map(scores).fillna(0.0).clip(0,100).round(2)
    out["Taşıma Benzer Destek 563"]=out["Sayı"].astype(int).map(supports).fillna(0.0).round(2)
    return out

def shared_core_brake_v18563(items, master, max_share_ratio=0.67, protected=1):
    """Aşırı ortak çekirdeği döndürür; en güçlü 1 ortak aday korunabilir."""
    items=[dict(x) for x in (items or [])]
    if len(items)<3: return items
    usage=Counter(int(n) for it in items for n in it.get("Kupon",[]))
    limit=max(2,int(round(len(items)*float(max_share_ratio))))
    sc="V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in master.columns else "V18.5 Nefes Puanı"
    w=master.copy()
    bm=w["Blok Mikro 56"] if "Blok Mikro 56" in w.columns else pd.Series(0.0,index=w.index)
    bg=w["Blok Sonraki Görülme 56"] if "Blok Sonraki Görülme 56" in w.columns else pd.Series(0.0,index=w.index)
    w["S563"]=0.50*normalized_series(w[sc])+0.28*normalized_series(bm)+0.22*normalized_series(bg)
    ranked=w.sort_values("S563",ascending=False)["Sayı"].astype(int).tolist()
    protected_nums=[n for n,_ in usage.most_common(protected)]
    for n,cnt in list(usage.most_common()):
        if n in protected_nums or cnt<=limit: continue
        need=cnt-limit
        for idx in range(len(items)-1,-1,-1):
            if need<=0: break
            q=list(map(int,items[idx].get("Kupon",[])))
            if n not in q: continue
            for alt in ranked:
                if alt not in q and usage.get(alt,0)<limit:
                    q[q.index(n)]=alt; items[idx]["Kupon"]=sorted(q)
                    usage[n]-=1; usage[alt]+=1; need-=1; break
    return items

def block_region_transfer_v18563(coupon, master, block_loc, size=7):
    """Yüksek güvenli ana blok bölgesinden güçlü mikro-adayı kupona taşır."""
    q=list(map(int,coupon))
    if not block_loc or not block_loc.get("Ana Bölge") or float(block_loc.get("Ana Puan",0.0))<82:
        return sorted(q[:size])
    band=block_loc["Ana Bölge"]; w=master.copy(); w["B563"]=w["Sayı"].astype(int).map(ten_band_name)
    cand=w[w["B563"]==band].copy()
    if cand.empty: return sorted(q[:size])
    sc="V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in cand.columns else "V18.5 Nefes Puanı"
    bm=cand["Blok Mikro 56"] if "Blok Mikro 56" in cand.columns else pd.Series(0.0,index=cand.index)
    bg=cand["Blok Sonraki Görülme 56"] if "Blok Sonraki Görülme 56" in cand.columns else pd.Series(0.0,index=cand.index)
    cand["BR563"]=0.38*normalized_series(cand[sc])+0.40*normalized_series(bm)+0.22*normalized_series(bg)
    top=cand.sort_values("BR563",ascending=False)["Sayı"].astype(int).head(3).tolist()
    if any(n in q for n in top): return sorted(q[:size])
    base=master.set_index("Sayı")[sc].to_dict()
    rem=[n for n in q if ten_band_name(n)!=band]
    if rem and top:
        drop=min(rem,key=lambda n:base.get(n,0)); q[q.index(drop)]=top[0]
    return sorted(dict.fromkeys(q))[:size]

def consensus_coupon_v1856(items, master, latest_set, skeleton, size=7):
    """
    V18.5.6.1 Birleşik Güç / Konsensüs.

    İki cerrahi düzeltme:
    1) Diğer yaşayan kuponlarda birden fazla bağımsız senaryoda desteklenen
       güçlü adayları gerçekten tek kolonda toplar.
    2) Taşıma kotası sabit değildir. Beklenen taşıma yükselirse ve taşıma
       kimliği yeterince güçlüyse 7'li kuponun 6-7 hanesi de taşıma olabilir.

    Mevcut V18.5.6 blok/aday/öğrenme motorlarına dokunmaz.
    """
    if master is None or master.empty or int(size) <= 0:
        return []

    size = int(size)
    usage = Counter()
    scenario_support = {}
    for item in (items or []):
        scenario = str(item.get("Senaryo", ""))
        for n in set(int(x) for x in item.get("Kupon", [])):
            usage[n] += 1
            scenario_support.setdefault(n, set()).add(scenario)

    max_usage = max(usage.values()) if usage else 1
    max_scen = max((len(v) for v in scenario_support.values()), default=1)

    work = master.copy()
    score_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in work.columns else "V18.5 Nefes Puanı"
    work["Kupon Desteği 56"] = work["Sayı"].map(lambda n: usage.get(int(n), 0) / max_usage)
    work["Bağımsız Senaryo 561"] = work["Sayı"].map(
        lambda n: len(scenario_support.get(int(n), set())) / max_scen
    )

    def nrm(name):
        return normalized_series(work[name]) if name in work.columns else pd.Series(0.0, index=work.index)

    # İlk V18.5.6 testinde normal kupon havuzu 5 doğru aday bulurken Konsensüs
    # bunları kaçırdı. Bu nedenle kupon/senaryo desteğinin ağırlığı artırıldı;
    # fakat kör çoğunluk olmaması için temel puan + taşıma + çekirdek + mikro
    # sinyalleri korunuyor.
    work["Konsensüs 56"] = (
        0.31 * nrm(score_col)
        + 0.23 * nrm("Kupon Desteği 56")
        + 0.15 * nrm("Bağımsız Senaryo 561")
        + 0.14 * nrm("Taşıma Kimlik")
        + 0.09 * nrm("Ortak Çekirdek Güveni")
        + 0.08 * nrm("Blok Mikro 56")
    ) * 100.0

    latest_set = set(int(n) for n in latest_set)

    # --- Adaptif taşıma kotası: 0..7 ---
    expected_carry = float(skeleton.get("Taşıma", 0.0))
    carriers = work[work["Sayı"].astype(int).isin(latest_set)].copy()
    if "Devam Puanı 562" not in carriers.columns:
        carriers["Devam Puanı 562"] = carriers.get("Taşıma Kimlik", 0.0)
    if "Taşıma Kimlik 563" not in carriers.columns:
        carriers["Taşıma Kimlik 563"] = carriers["Devam Puanı 562"]
    if "Taşıma Kimlik 565" not in carriers.columns:
        carriers["Taşıma Kimlik 565"] = carriers["Taşıma Kimlik 563"]
    carriers = carriers.sort_values(
        ["Taşıma Kimlik 565", "Taşıma Kimlik 563", "Devam Puanı 562", "Taşıma Kimlik", "Konsensüs 56"],
        ascending=[False, False, False, False, False]
    )

    carry_vals = pd.to_numeric(carriers.get("Taşıma Kimlik", 0.0), errors="coerce").fillna(0.0)
    strong_70 = int((carry_vals >= 70).sum())
    strong_60 = int((carry_vals >= 60).sum())
    strong_50 = int((carry_vals >= 50).sum())

    # Beklenen taşıma 20'lik gerçek çekiliş içindir; 7'li kupon kotasına
    # doğrusal zorlamıyoruz. Rejim yükseldikçe tavan açılıyor.
    if expected_carry >= 8.5:
        carry_cap = 7
    elif expected_carry >= 7.0:
        carry_cap = 6
    elif expected_carry >= 5.5:
        carry_cap = 5
    elif expected_carry >= 4.0:
        carry_cap = 4
    elif expected_carry >= 2.5:
        carry_cap = 3
    elif expected_carry > 0:
        carry_cap = 2
    else:
        carry_cap = 0

    # Kimlik motoru çok güçlü ortak sinyal veriyorsa rejim kotasını bir kademe aç.
    if strong_70 >= 6:
        carry_cap = max(carry_cap, min(7, strong_70))
    elif strong_60 >= 5:
        carry_cap = max(carry_cap, min(6, strong_60))
    elif strong_50 >= 4:
        carry_cap = max(carry_cap, min(5, strong_50))
    carry_cap = min(size, carry_cap)

    selected = []

    # Önce gerçekten güçlü ve yaşayan kuponlarca da desteklenen taşıyıcılar.
    for _, row in carriers.iterrows():
        n = int(row["Sayı"])
        identity = float(row.get("Taşıma Kimlik", 0.0))
        continue_score = float(row.get("Devam Puanı 562", identity))
        support = usage.get(n, 0)
        scen = len(scenario_support.get(n, set()))
        if continue_score >= 55 or identity >= 58 or support >= 2 or scen >= 2:
            selected.append(n)
        if len(selected) >= carry_cap:
            break

    # Kota dolmadıysa en iyi taşıma kimlikleriyle tamamla.
    if len(selected) < carry_cap:
        for n in carriers["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected) >= carry_cap:
                break

    # Sonra normal 5 kuponun ortak bulduğu güçlü yeni adayları biriktir.
    newcomers = work[~work["Sayı"].astype(int).isin(latest_set)].copy()
    newcomers["Toplama Önceliği 561"] = (
        0.40 * nrm("Konsensüs 56").reindex(newcomers.index).fillna(0.0)
        + 0.32 * nrm("Kupon Desteği 56").reindex(newcomers.index).fillna(0.0)
        + 0.18 * nrm("Bağımsız Senaryo 561").reindex(newcomers.index).fillna(0.0)
        + 0.10 * nrm(score_col).reindex(newcomers.index).fillna(0.0)
    )
    newcomers = newcomers.sort_values(
        ["Toplama Önceliği 561", "Konsensüs 56", score_col],
        ascending=[False, False, False],
    )

    for n in newcomers["Sayı"].astype(int):
        if len(selected) >= size:
            break
        if n not in selected:
            selected.append(n)

    # Güvenli son tamamlama.
    if len(selected) < size:
        for n in work.sort_values("Konsensüs 56", ascending=False)["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected) >= size:
                break

    return sorted(selected[:size])


def core_companion_engine_v18564(df, master, core_numbers, latest_set, lookback=500, short_window=100):
    """
    V18.5.6.4 Çekirdek -> Eşlikçi Motoru.
    Bir çekirdek sayı için:
      - uzun dönem P(X|core)
      - kısa dönem P(X|core)
      - lift = P(X|core) / P(X)
      - son çekilişten taşınma durumunda birlikte devam etme
      - +/-1 ve +/-2 blok/komşuluk bağı
    puanlarını birleştirir.
    """
    core_numbers = [int(x) for x in core_numbers]
    latest_set = set(int(x) for x in latest_set)
    out = {}
    if df is None or len(df) < 10:
        return out

    def sets_from(frame):
        rows=[]
        for _, r in frame.iterrows():
            s=set()
            for c in NUM_COLS:
                if c in frame.columns and pd.notna(r[c]):
                    s.add(int(r[c]))
            if s:
                rows.append(s)
        return rows

    rows_long = sets_from(df.tail(int(lookback)))
    rows_short = rows_long[-int(short_window):]
    if not rows_long:
        return out

    universe = range(1,81)
    base_freq = Counter(n for s in rows_long for n in s)
    total_long = max(1, len(rows_long))

    # Transition pairs for carry-together behavior.
    transitions = list(zip(rows_long[:-1], rows_long[1:]))

    for core in core_numbers:
        core_rows = [s for s in rows_long if core in s]
        short_core_rows = [s for s in rows_short if core in s]
        denom_long = max(1, len(core_rows))
        denom_short = max(1, len(short_core_rows))
        scored=[]

        for x in universe:
            if x == core:
                continue
            together_long = sum(1 for s in core_rows if x in s)
            together_short = sum(1 for s in short_core_rows if x in s)
            p_cond = together_long / denom_long
            p_short = together_short / denom_short
            p_base = base_freq[x] / total_long
            lift = p_cond / max(0.01, p_base)

            # If core is in previous draw, how often did x travel with it into next draw?
            carry_den = carry_num = 0
            for a,b in transitions:
                if core in a:
                    carry_den += 1
                    if core in b and x in b:
                        carry_num += 1
            carry_pair = carry_num / max(1, carry_den)

            dist = abs(x-core)
            neighbor = 1.0 if dist == 1 else (0.55 if dist == 2 else 0.0)

            # Reward specific association, not merely globally-hot numbers.
            score = (
                0.30 * min(1.0, p_cond / 0.50) +
                0.22 * min(1.0, p_short / 0.55) +
                0.24 * min(1.0, lift / 1.65) +
                0.14 * min(1.0, carry_pair / 0.25) +
                0.10 * neighbor
            ) * 100.0

            scored.append({
                "Sayı": int(x),
                "P_Beraber": round(100*p_cond,2),
                "Kısa_Beraber": round(100*p_short,2),
                "Lift": round(lift,3),
                "Taşıma_Beraber": round(100*carry_pair,2),
                "Komşu": neighbor,
                "Eşlikçi Puanı": round(score,2),
            })
        out[core] = pd.DataFrame(scored).sort_values(
            ["Eşlikçi Puanı","Lift","P_Beraber"], ascending=False
        ).reset_index(drop=True)
    return out


def inject_companions_v18564(items, companion_map, protected_cores, max_companions_per_coupon=1):
    """
    Çekirdeğin doğru eşlikçisini aynı kolona toplamak için senaryolara
    farklı güçlü eşlikçiler dağıtır. Aynı eşlikçiyi bütün kuponlara basmaz.
    """
    items=[dict(x) for x in (items or [])]
    if not items or not companion_map:
        return items

    used=Counter()
    for idx,it in enumerate(items):
        q=list(map(int,it.get("Kupon",[])))
        cores=[c for c in protected_cores if c in q and c in companion_map]
        if not cores:
            continue

        inserted=0
        for core in cores:
            tab=companion_map.get(core)
            if tab is None or tab.empty:
                continue
            # Rotate through top companions; require positive lift.
            for _,r in tab.head(10).iterrows():
                x=int(r["Sayı"])
                if x in q or float(r["Lift"]) < 1.03:
                    continue
                if used[x] >= 2:
                    continue

                # Replace a non-core, avoiding removal of an existing +/-1 block mate.
                removable=[]
                for n in q:
                    if n in protected_cores:
                        continue
                    if any(abs(n-z)==1 for z in q if z!=n):
                        continue
                    removable.append(n)
                if not removable:
                    removable=[n for n in q if n not in protected_cores]
                if not removable:
                    break

                # Deterministic rotation prevents duplicate coupons.
                drop=removable[(idx + inserted) % len(removable)]
                q[q.index(drop)] = x
                used[x]+=1
                inserted+=1
                break
            if inserted >= max_companions_per_coupon:
                break
        it["Kupon"]=sorted(dict.fromkeys(q))
    return items


def deduplicate_coupons_v18564(items, master, min_difference=2):
    """Birebir aynı / aşırı benzer kuponları ayırır; en az min_difference sayı farkı hedefler."""
    items=[dict(x) for x in (items or [])]
    if len(items)<2:
        return items
    score_col="V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in master.columns else "V18.5 Nefes Puanı"
    ranked=master.sort_values(score_col,ascending=False)["Sayı"].astype(int).tolist()
    previous=[]
    for i,it in enumerate(items):
        q=list(map(int,it.get("Kupon",[])))
        tries=0
        while any(len(set(q)-set(p)) < min_difference for p in previous) and tries < 20:
            changed=False
            for alt in ranked:
                if alt in q:
                    continue
                # change one of the most over-shared non-adjacent positions
                for pos in range(len(q)-1,-1,-1):
                    candidate=q[pos]
                    nq=q.copy(); nq[pos]=alt; nq=sorted(dict.fromkeys(nq))
                    if len(nq)!=len(q):
                        continue
                    if all(len(set(nq)-set(p)) >= min_difference for p in previous):
                        q=nq; changed=True; break
                if changed: break
            tries+=1
            if not changed: break
        it["Kupon"]=sorted(q)
        previous.append(list(q))
    return items


def carry_identity_v18565(df, master, latest_set, expected_carry, lookback=500):
    """
    V18.5.6.5 Taşıma Kimliği Kalibrasyonu.
    Taşıma ADEDİNİ değiştirmez. Kimlik için:
      - düzeltilmiş V18.5.6.3 benzer-geçiş kimliği
      - son 4 çekilişteki var/yok deseni
      - aynı desenin geçmişte bir sonraki elde devam oranı
      - son iki gerçek geçişte düşük/yüksek taşıma rejimi
    birlikte kullanılır.
    """
    out = master.copy()
    latest_set = set(int(x) for x in latest_set)

    if df is None or len(df) < 8 or not latest_set:
        base = out["Taşıma Kimlik 563"] if "Taşıma Kimlik 563" in out.columns else (
            out["Devam Puanı 562"] if "Devam Puanı 562" in out.columns else out.get("Taşıma Kimlik", 0.0)
        )
        out["Taşıma Kimlik 565"] = pd.to_numeric(base, errors="coerce").fillna(0.0)
        out["Taşıma Desen % 565"] = 0.0
        return out

    frame = df.tail(min(int(lookback)+8, len(df))).reset_index(drop=True)

    def rset(i):
        r = frame.iloc[i]
        return set(int(r[c]) for c in NUM_COLS if c in frame.columns and pd.notna(r[c]))

    sets = [rset(i) for i in range(len(frame))]
    recent_carries = [len(sets[i] & sets[i+1]) for i in range(max(0, len(sets)-4), len(sets)-1)]
    recent_mean = sum(recent_carries)/max(1, len(recent_carries))
    regime_delta = float(expected_carry) - recent_mean

    # Number-specific binary pattern in the last 4 draws, including latest draw.
    scores = {}
    pattern_rates = {}
    samples = {}
    for n in latest_set:
        current_pattern = tuple(1 if n in s else 0 for s in sets[-4:])
        hit = total = 0
        # Historical same-pattern next-draw continuation.
        for j in range(3, len(sets)-1):
            pat = tuple(1 if n in sets[k] else 0 for k in range(j-3, j+1))
            if pat == current_pattern:
                total += 1
                if n in sets[j+1]:
                    hit += 1
        pattern_rate = 100.0 * hit / total if total else 0.0

        row = out[out["Sayı"].astype(int) == int(n)]
        if row.empty:
            old = 0.0
        elif "Taşıma Kimlik 563" in row.columns:
            old = float(row.iloc[0]["Taşıma Kimlik 563"])
        elif "Devam Puanı 562" in row.columns:
            old = float(row.iloc[0]["Devam Puanı 562"])
        else:
            old = float(row.iloc[0].get("Taşıma Kimlik", 0.0))

        # Small samples are shrunk strongly toward old identity.
        reliability = min(1.0, total/14.0)
        pattern_component = reliability*pattern_rate + (1.0-reliability)*old

        # If recent real carry regime fell well below long estimate, identity
        # confidence is compressed; if rising, a mild boost only.
        if regime_delta >= 2.0:
            regime_factor = 0.92
        elif regime_delta <= -2.0:
            regime_factor = 0.97
        else:
            regime_factor = 1.0

        score = (0.62*old + 0.38*pattern_component) * regime_factor
        scores[n] = max(0.0, min(100.0, score))
        pattern_rates[n] = pattern_rate
        samples[n] = total

    out["Taşıma Kimlik 565"] = out["Sayı"].astype(int).map(scores).fillna(0.0).round(2)
    out["Taşıma Desen % 565"] = out["Sayı"].astype(int).map(pattern_rates).fillna(0.0).round(2)
    out["Taşıma Desen Örnek 565"] = out["Sayı"].astype(int).map(samples).fillna(0).astype(int)
    return out


def dynamic_core_brake_v18565(items, master, hard_max_share=0.83):
    """
    6/6 ortak sayıyı sadece olağanüstü güven varsa bırakır.
    Olağanüstü değilse en fazla ~5/6; orta güvenli ortaklarda ~4/6.
    """
    items = [dict(x) for x in (items or [])]
    if len(items) < 3:
        return items

    score_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in master.columns else "V18.5 Nefes Puanı"
    w = master.copy()

    def col(name):
        return normalized_series(w[name]) if name in w.columns else pd.Series(0.0, index=w.index)

    w["Core Güven 565"] = (
        0.40*col(score_col)
        + 0.20*col("Ortak Çekirdek Güveni")
        + 0.18*col("Blok Mikro 56")
        + 0.12*col("Taşıma Kimlik 565")
        + 0.10*col("Benzer")
    ) * 100.0
    trust = w.set_index("Sayı")["Core Güven 565"].to_dict()
    ranked = w.sort_values("Core Güven 565", ascending=False)["Sayı"].astype(int).tolist()
    usage = Counter(int(n) for it in items for n in it.get("Kupon", []))

    for n, cnt in list(usage.most_common()):
        t = float(trust.get(n, 0.0))
        if t >= 88:
            limit = len(items)                       # 6/6 allowed only here
        elif t >= 78:
            limit = max(3, int(round(len(items)*hard_max_share)))  # ~5/6
        else:
            limit = max(3, int(round(len(items)*0.67)))            # ~4/6

        if cnt <= limit:
            continue

        need = cnt - limit
        for idx in range(len(items)-1, -1, -1):
            if need <= 0:
                break
            q = list(map(int, items[idx].get("Kupon", [])))
            if n not in q:
                continue
            for alt in ranked:
                if alt in q or usage.get(alt,0) >= limit:
                    continue
                q[q.index(n)] = int(alt)
                items[idx]["Kupon"] = sorted(q)
                usage[n] -= 1
                usage[alt] += 1
                need -= 1
                break
    return items


def block_package_engine_v18565(df, latest_set, lookback=500):
    """
    Blok -> Eşlikçi / Blok Taşıma Motoru.
    Son gerçek çekilişteki 2+ ardışık blokların geçmişte sonraki elde:
      - aynen sürmesi
      - bir komşuyla büyümesi
      - sağa/sola kayması
    davranışlarını puanlar.
    """
    latest_set = set(int(x) for x in latest_set)
    latest_blocks = consecutive_blocks(latest_set)
    latest_blocks = [tuple(map(int,b)) for b in latest_blocks if len(b) >= 2]
    if df is None or len(df) < 20 or not latest_blocks:
        return []

    frame = df.tail(min(int(lookback)+2, len(df))).reset_index(drop=True)
    sets=[]
    for _,r in frame.iterrows():
        sets.append(set(int(r[c]) for c in NUM_COLS if c in frame.columns and pd.notna(r[c])))

    packages=[]
    for block in latest_blocks:
        blen=len(block)
        starts=[]
        for i in range(len(sets)-1):
            for b in consecutive_blocks(sets[i]):
                if len(b)==blen:
                    starts.append((tuple(map(int,b)), sets[i+1]))

        candidates=Counter()
        total=max(1,len(starts))
        # Current block itself and +/-1 growth/shift packages.
        cur=set(block)
        poss=[]
        poss.append(tuple(sorted(cur)))
        if min(cur)>1: poss.append(tuple(sorted(cur|{min(cur)-1})))
        if max(cur)<80: poss.append(tuple(sorted(cur|{max(cur)+1})))
        if min(cur)>1 and max(cur)<80:
            poss.append(tuple(sorted({x-1 for x in cur})))
            poss.append(tuple(sorted({x+1 for x in cur})))

        for pkg in poss:
            hit=0
            for _,nxt in starts:
                if set(pkg).issubset(nxt):
                    hit+=1
            rate=100.0*hit/total
            if rate>0:
                candidates[pkg]=rate

        for pkg,rate in candidates.items():
            packages.append({
                "Kaynak Blok": "-".join(map(str,block)),
                "Paket": tuple(pkg),
                "Paket Puanı 565": round(rate,2),
                "Uzunluk": len(pkg),
            })

    return sorted(packages, key=lambda x:(x["Paket Puanı 565"], x["Uzunluk"]), reverse=True)


def inject_block_package_v18565(items, packages, master, size=7):
    """En güçlü blok paketini Blok Rejim kuponuna, ikinci paketi başka bir senaryoya kontrollü taşır."""
    items=[dict(x) for x in (items or [])]
    if not items or not packages:
        return items
    score_col="V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in master.columns else "V18.5 Nefes Puanı"
    rank=master.set_index("Sayı")[score_col].to_dict()

    targets=[]
    for i,it in enumerate(items):
        if "Blok" in str(it.get("Senaryo","")):
            targets.append(i)
            break
    if len(items)>1:
        targets += [i for i in range(len(items)) if i not in targets][:1]

    for pidx,idx in enumerate(targets):
        if pidx >= len(packages):
            break
        pkg=list(map(int,packages[pidx]["Paket"]))
        q=list(map(int,items[idx].get("Kupon",[])))
        for n in pkg:
            if n in q:
                continue
            removable=[x for x in q if x not in pkg]
            if not removable:
                break
            drop=min(removable,key=lambda x:rank.get(x,0))
            q[q.index(drop)]=n
        items[idx]["Kupon"]=sorted(dict.fromkeys(q))[:int(size)]
    return items


def micro_location_calibration_v18565(items, master, block_loc_info, regime_summary, size=7):
    """
    Ana bölgeye kör yığılma yerine ana+alternatif bölge ve sınır komşuluğunu birlikte kullanır.
    Çoklu Küçük rejimde tek bölgede en fazla 3 sayı kuralını korur.
    """
    items=[dict(x) for x in (items or [])]
    if not items or not block_loc_info:
        return items

    main=block_loc_info.get("Ana Bölge")
    alt=block_loc_info.get("Alternatif Bölge")
    main_conf=float(block_loc_info.get("Ana Puan",0.0))
    alt_conf=float(block_loc_info.get("Alternatif Puan",0.0))
    if main_conf < 72 and alt_conf < 72:
        return items

    w=master.copy()
    score_col="V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in w.columns else "V18.5 Nefes Puanı"
    w["Band565"]=w["Sayı"].astype(int).map(ten_band_name)

    def nrm(name):
        return normalized_series(w[name]) if name in w.columns else pd.Series(0.0,index=w.index)

    # Boundary bonus: numbers next to a 10-band edge can complete a block across regions.
    boundary=[]
    for n in w["Sayı"].astype(int):
        boundary.append(1.0 if n in {9,10,11,19,20,21,29,30,31,39,40,41,49,50,51,59,60,61,69,70,71} else 0.0)
    w["Sınır 565"]=boundary
    w["Mikro Kalibre 565"]=(
        0.42*nrm(score_col)
        +0.31*nrm("Blok Mikro 56")
        +0.17*nrm("Blok Sonraki Görülme 56")
        +0.10*nrm("Sınır 565")
    )

    main_pool=w[w["Band565"]==main].sort_values("Mikro Kalibre 565",ascending=False)["Sayı"].astype(int).head(4).tolist() if main else []
    alt_pool=w[w["Band565"]==alt].sort_values("Mikro Kalibre 565",ascending=False)["Sayı"].astype(int).head(4).tolist() if alt else []

    for idx,it in enumerate(items):
        q=list(map(int,it.get("Kupon",[])))
        # Alternate main/alt representation between coupons.
        pool = main_pool if idx%2==0 else (alt_pool or main_pool)
        if pool and not any(x in q for x in pool[:2]):
            cand=pool[0]
            counts=Counter(ten_band_name(x) for x in q)
            removable=[x for x in q if counts[ten_band_name(x)]>=2 and x!=cand]
            if not removable:
                removable=[x for x in q if x!=cand]
            if removable:
                base=w.set_index("Sayı")[score_col].to_dict()
                drop=min(removable,key=lambda x:base.get(x,0))
                q[q.index(drop)]=cand
        items[idx]["Kupon"]=sorted(dict.fromkeys(q))[:int(size)]
    return items


def rest_return_scores_v18566(df, master, latest_set, lookback=500):
    """
    V18.5.6.6 Dinlenmiş Dönüş Kalibrasyonu.
    1–2 / 3–5 / 6–10 / 10+ el dinlenme sınıflarının geçmişte bir sonraki
    çekilişte dönüş oranını ölçer. Sayı-özel oranı küçük örnekte genel sınıf
    oranına doğru küçültülür. Son çekilişte bulunan sayılara dönüş puanı verilmez.
    """
    out = master.copy()
    latest_set = set(int(x) for x in latest_set)

    if df is None or len(df) < 20:
        out["Dinlenme 566"] = 0
        out["Dinlenme Sınıfı 566"] = "0"
        out["Dönüş % 566"] = 0.0
        out["Dönüş Puanı 566"] = 0.0
        return out

    frame = df.tail(min(int(lookback)+20, len(df))).reset_index(drop=True)
    sets = []
    for _, r in frame.iterrows():
        sets.append(set(
            int(r[c]) for c in NUM_COLS
            if c in frame.columns and pd.notna(r[c])
        ))

    def bucket(g):
        g = int(g)
        if g <= 0:
            return "0"
        if g <= 2:
            return "1-2"
        if g <= 5:
            return "3-5"
        if g <= 10:
            return "6-10"
        return "10+"

    # Historical state: after draw t, current gap class -> hit in draw t+1?
    gap_state = {n: 99 for n in range(1,81)}
    global_stats = {b:[0,0] for b in ["1-2","3-5","6-10","10+"]}
    num_stats = {n:{b:[0,0] for b in ["1-2","3-5","6-10","10+"]} for n in range(1,81)}

    # Initialize/update gaps draw by draw.
    for t in range(len(sets)-1):
        cur = sets[t]
        nxt = sets[t+1]
        for n in range(1,81):
            if n in cur:
                gap_state[n] = 0
            else:
                gap_state[n] = min(99, gap_state[n] + 1)

            b = bucket(gap_state[n])
            if b == "0":
                continue
            global_stats[b][1] += 1
            num_stats[n][b][1] += 1
            if n in nxt:
                global_stats[b][0] += 1
                num_stats[n][b][0] += 1

    # Current gaps from newest draw backwards.
    current_gap = {}
    for n in range(1,81):
        g = 0
        found = False
        for s in reversed(sets):
            if n in s:
                found = True
                break
            g += 1
        current_gap[n] = 0 if n in latest_set else (g if found else len(sets))

    score_map = {}
    rate_map = {}
    class_map = {}
    for n in range(1,81):
        g = current_gap[n]
        b = bucket(g)
        class_map[n] = b
        if b == "0":
            score_map[n] = 0.0
            rate_map[n] = 0.0
            continue

        gh, gt = global_stats[b]
        nh, nt = num_stats[n][b]
        global_rate = gh / max(1, gt)
        num_rate = nh / max(1, nt)

        # Shrink number-specific estimate toward bucket baseline.
        rel = min(1.0, nt / 18.0)
        blended = rel*num_rate + (1.0-rel)*global_rate

        # Moderate preference to historically productive rest zones, never raw gap alone.
        gap_fit = {"1-2":0.72, "3-5":1.00, "6-10":0.92, "10+":0.74}.get(b, 0.0)
        score = 100.0 * (0.82*min(1.0, blended/0.34) + 0.18*gap_fit)
        score_map[n] = max(0.0, min(100.0, score))
        rate_map[n] = 100.0*blended

    out["Dinlenme 566"] = out["Sayı"].astype(int).map(current_gap).fillna(0).astype(int)
    out["Dinlenme Sınıfı 566"] = out["Sayı"].astype(int).map(class_map).fillna("0")
    out["Dönüş % 566"] = out["Sayı"].astype(int).map(rate_map).fillna(0.0).round(2)
    out["Dönüş Puanı 566"] = out["Sayı"].astype(int).map(score_map).fillna(0.0).round(2)
    return out


def meta_master_coupon_v18566(df, master, items, latest_set, skeleton, regime_summary,
                              block_loc_info=None, companion_map=None, packages=None, size=7):
    """
    V18.5.6.6 ANA ORTAK / MASTER kolon.
    Sonuç bilgisi kullanmaz. Aynı anda şu bağımsız kanıtları birleştirir:
      - yaşayan/nefesten gelen temel puan
      - senaryo desteği + senaryo çeşitliliği
      - taşıma kimliği
      - dinlenmiş dönüş
      - blok mikro-konum
      - ana/alternatif bölge
      - Çekirdek→Eşlikçi
      - Blok→Eşlikçi / blok paket desteği
    Rejim tutarlılığıyla tek bölgede/tek uzun blokta aşırı yığılmayı sınırlar.
    """
    size = int(size)
    latest_set = set(int(x) for x in latest_set)
    work = rest_return_scores_v18566(df, master, latest_set, lookback=500)

    if work is None or work.empty or size <= 0:
        return [], pd.DataFrame()

    score_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in work.columns else (
        "V18.5 Nefes Puanı" if "V18.5 Nefes Puanı" in work.columns else "V18 Nefes Puanı"
    )

    usage = Counter()
    scenario_support = {}
    for it in (items or []):
        scenario = str(it.get("Senaryo",""))
        for n in set(int(x) for x in it.get("Kupon", [])):
            usage[n] += 1
            scenario_support.setdefault(n,set()).add(scenario)

    max_usage = max(usage.values()) if usage else 1
    max_scen = max((len(v) for v in scenario_support.values()), default=1)

    work["Senaryo Oy 566"] = work["Sayı"].astype(int).map(
        lambda n: usage.get(int(n),0)/max_usage
    )
    work["Senaryo Çeşit 566"] = work["Sayı"].astype(int).map(
        lambda n: len(scenario_support.get(int(n),set()))/max_scen
    )
    work["Havuzda 566"] = work["Sayı"].astype(int).map(
        lambda n: 1.0 if usage.get(int(n),0)>0 else 0.0
    )

    def nrm(name):
        if name in work.columns:
            return normalized_series(pd.to_numeric(work[name], errors="coerce").fillna(0.0))
        return pd.Series(0.0, index=work.index)

    carry_col = "Taşıma Kimlik 565" if "Taşıma Kimlik 565" in work.columns else (
        "Taşıma Kimlik 563" if "Taşıma Kimlik 563" in work.columns else (
            "Devam Puanı 562" if "Devam Puanı 562" in work.columns else "Taşıma Kimlik"
        )
    )

    # Companion support: max support supplied by any strong core.
    comp_map = {}
    if companion_map:
        for _, tab in companion_map.items():
            if tab is None or tab.empty:
                continue
            for _, r in tab.head(12).iterrows():
                n = int(r["Sayı"])
                comp_map[n] = max(comp_map.get(n,0.0), float(r.get("Eşlikçi Puanı",0.0)))
    work["Eşlikçi Destek 566"] = work["Sayı"].astype(int).map(comp_map).fillna(0.0)

    # Block-package support.
    pkg_map = {}
    for p in (packages or []):
        pscore = float(p.get("Paket Puanı 565",0.0))
        for n in p.get("Paket",()):
            pkg_map[int(n)] = max(pkg_map.get(int(n),0.0), pscore)
    work["Blok Paket 566"] = work["Sayı"].astype(int).map(pkg_map).fillna(0.0)

    # Region support: main + alternative, with confidence, but never dominant alone.
    reg_map = {}
    if block_loc_info:
        main = block_loc_info.get("Ana Bölge")
        alt = block_loc_info.get("Alternatif Bölge")
        mp = float(block_loc_info.get("Ana Puan",0.0))
        ap = float(block_loc_info.get("Alternatif Puan",0.0))
        for n in range(1,81):
            band = ten_band_name(n)
            if band == main:
                reg_map[n] = mp
            elif band == alt:
                reg_map[n] = 0.88*ap
            else:
                reg_map[n] = 0.0
    work["Bölge Destek 566"] = work["Sayı"].astype(int).map(reg_map).fillna(0.0)

    # Dynamic carry/rest balance. Carry quantity may be right while identity weak,
    # so carry never dominates Master by itself.
    expected_carry = float(skeleton.get("Taşıma", 5.0))
    carry_weight = 0.07 + min(0.05, max(0.0, expected_carry-4.0)*0.012)
    rest_weight = 0.12 if expected_carry <= 5.5 else 0.09

    work["Meta Master Puan 566"] = (
        0.18*nrm(score_col)
        +0.20*nrm("Senaryo Oy 566")
        +0.10*nrm("Senaryo Çeşit 566")
        +carry_weight*nrm(carry_col)
        +rest_weight*nrm("Dönüş Puanı 566")
        +0.10*nrm("Blok Mikro 56")
        +0.07*nrm("Bölge Destek 566")
        +0.06*nrm("Eşlikçi Destek 566")
        +0.05*nrm("Blok Paket 566")
        +0.04*nrm("Havuzda 566")
    ) * 100.0

    # Independent evidence count: favor numbers supported by multiple engines.
    evidence = pd.Series(0, index=work.index, dtype=float)
    for name,thr in [
        ("Senaryo Oy 566",0.45),
        (carry_col,55),
        ("Dönüş Puanı 566",58),
        ("Blok Mikro 56",55),
        ("Bölge Destek 566",70),
        ("Eşlikçi Destek 566",55),
        ("Blok Paket 566",45),
    ]:
        if name in work.columns:
            vals = pd.to_numeric(work[name], errors="coerce").fillna(0.0)
            evidence += (vals >= thr).astype(float)
    work["Bağımsız Kanıt 566"] = evidence
    work["Meta Master Puan 566"] += 2.2*work["Bağımsız Kanıt 566"]

    # Candidate ordering.
    ranked = work.sort_values(
        ["Meta Master Puan 566","Bağımsız Kanıt 566",score_col],
        ascending=[False,False,False]
    )

    multi = float(regime_summary.get("Çoklu Küçük %",0.0)) if regime_summary else 0.0
    longp = float(regime_summary.get("Uzun Blok %",0.0)) if regime_summary else 0.0
    max_run = 3 if multi >= longp + 15 else (4 if longp < 45 else 5)
    max_band = 3 if multi >= 60 else 4

    # Adaptive carry cap, but no forced carries.
    if expected_carry >= 8.5:
        carry_cap = size
    elif expected_carry >= 7.0:
        carry_cap = min(size,6)
    elif expected_carry >= 5.5:
        carry_cap = min(size,4)
    elif expected_carry >= 4.0:
        carry_cap = min(size,3)
    else:
        carry_cap = min(size,2)

    def max_consecutive_run(nums):
        if not nums:
            return 0
        s = sorted(set(nums))
        best = cur = 1
        for a,b in zip(s,s[1:]):
            if b == a+1:
                cur += 1
                best = max(best,cur)
            else:
                cur = 1
        return best

    selected=[]
    band_counts=Counter()
    carry_count=0

    def allowed(n):
        nonlocal carry_count
        n=int(n)
        if n in selected:
            return False
        b=ten_band_name(n)
        if band_counts[b] >= max_band:
            return False
        if n in latest_set and carry_count >= carry_cap:
            return False
        if max_consecutive_run(selected+[n]) > max_run:
            return False
        return True

    # Phase A: strong multi-engine evidence from scenario pool.
    for _,r in ranked.iterrows():
        n=int(r["Sayı"])
        if float(r["Havuzda 566"]) < 1:
            continue
        if float(r["Bağımsız Kanıt 566"]) < 2:
            continue
        if allowed(n):
            selected.append(n)
            band_counts[ten_band_name(n)] += 1
            if n in latest_set:
                carry_count += 1
        if len(selected) >= size:
            break

    # Phase B: ensure up to two strong rested-return candidates can enter
    # when they are not already represented and evidence is adequate.
    rest_added=0
    rest_rank=ranked[
        (~ranked["Sayı"].astype(int).isin(latest_set))
        & (ranked["Dönüş Puanı 566"] >= 62)
    ]
    for _,r in rest_rank.iterrows():
        if rest_added >= 2 or len(selected) >= size:
            break
        n=int(r["Sayı"])
        if allowed(n):
            selected.append(n)
            band_counts[ten_band_name(n)] += 1
            rest_added += 1

    # Phase C: fill by global meta score under regime constraints.
    for _,r in ranked.iterrows():
        if len(selected) >= size:
            break
        n=int(r["Sayı"])
        if allowed(n):
            selected.append(n)
            band_counts[ten_band_name(n)] += 1
            if n in latest_set:
                carry_count += 1

    # Last safe fill if constraints are too strict.
    if len(selected) < size:
        for n in ranked["Sayı"].astype(int):
            if n not in selected:
                selected.append(n)
            if len(selected) >= size:
                break

    return sorted(selected[:size]), work.sort_values(
        ["Meta Master Puan 566","Bağımsız Kanıt 566"],
        ascending=[False,False]
    )


def master_item_v18566(df, master, items, latest_set, skeleton, regime_summary,
                      block_loc_info=None, companion_map=None, packages=None, size=7):
    coupon, table = meta_master_coupon_v18566(
        df, master, items, latest_set, skeleton, regime_summary,
        block_loc_info=block_loc_info,
        companion_map=companion_map,
        packages=packages,
        size=size,
    )
    return {
        "Senaryo": "🏆 ANA ORTAK / MASTER",
        "Kupon": coupon,
        "Master Tablo 566": table,
    }


def recent_engine_form_v18567(df, lookback=12):
    """
    V18.5.6.7 Motor Form Hafızası.
    Son gerçek çekilişlerde motor ailesi benzeri sinyallerin ne kadar işe yaradığını
    yaklaşık olarak ölçer. Amaç motorları kapatmak değil, MASTER içindeki söz hakkını
    dinamikleştirmektir.
    """
    base = {
        "Taşıma": 1.00,
        "Dinlenmiş": 1.00,
        "Blok": 1.00,
        "Bölge": 1.00,
        "Eşlikçi": 1.00,
        "Senaryo": 1.00,
        "KarşıRejim": 1.00,
    }
    if df is None or len(df) < 10:
        return base

    work = df.tail(min(len(df), int(lookback)+2)).reset_index(drop=True)
    sets = [set(int(r[c]) for c in NUM_COLS) for _,r in work.iterrows()]
    if len(sets) < 3:
        return base

    # Carry form: actual carry count stability around rolling expectation.
    carries = [len(sets[i-1] & sets[i]) for i in range(1,len(sets))]
    if carries:
        mean_c = sum(carries)/len(carries)
        dev = sum(abs(x-mean_c) for x in carries)/len(carries)
        base["Taşıma"] = max(0.72, min(1.28, 1.16 - 0.05*dev))

    # Block form: how consistently small consecutive structures appear.
    block_counts=[]
    long_counts=[]
    for s in sets[1:]:
        bs = consecutive_blocks(s)
        block_counts.append(sum(1 for b in bs if len(b) >= 2))
        long_counts.append(sum(1 for b in bs if len(b) >= 4))
    if block_counts:
        avg_b = sum(block_counts)/len(block_counts)
        base["Blok"] = max(0.78, min(1.30, 0.88 + 0.06*avg_b))
        # Counter-regime should never be zeroed, especially if long blocks recently appeared.
        avg_long = sum(long_counts)/len(long_counts)
        base["KarşıRejim"] = max(0.80, min(1.22, 0.90 + 0.12*avg_long))

    # Region form: measure concentration tendency rather than one exact region.
    region_concs=[]
    for s in sets[1:]:
        cc=Counter(ten_band_name(n) for n in s)
        region_concs.append(max(cc.values())/20.0 if cc else 0.0)
    if region_concs:
        rc=sum(region_concs)/len(region_concs)
        base["Bölge"]=max(0.78,min(1.22,0.88+0.70*rc))

    # Rested returns: how many numbers return after being absent 2+ draws.
    rest_hits=[]
    for i in range(3,len(sets)):
        prev=sets[i-1]
        before=sets[i-2] | sets[i-3]
        rested=(sets[i]-prev) & before
        rest_hits.append(len(rested)/20.0)
    if rest_hits:
        rr=sum(rest_hits)/len(rest_hits)
        base["Dinlenmiş"]=max(0.78,min(1.22,0.92+0.90*rr))

    return base


def regime_break_guard_v18567(regime_summary, df):
    """
    Çoklu Küçük baskın olsa bile karşı rejimi tamamen öldürmez.
    Yakın geçmişte 4+ bloklar görülüyorsa MASTER'a küçük karşı-senaryo payı açar.
    """
    multi = float(regime_summary.get("Çoklu Küçük %",0.0)) if regime_summary else 0.0
    longp = float(regime_summary.get("Uzun Blok %",0.0)) if regime_summary else 0.0
    recent_long = 0
    if df is not None and len(df):
        for _,r in df.tail(min(8,len(df))).iterrows():
            nums=[int(r[c]) for c in NUM_COLS]
            if any(len(b)>=4 for b in consecutive_blocks(nums)):
                recent_long += 1
    # 0..1 insurance factor
    return min(1.0, 0.20 + 0.08*recent_long + 0.004*longp + max(0.0,(65.0-multi))*0.003)


def scenario_family_v1858(name):
    """Uzman kuponları gerçek karar ailesine indirger; aynı motorun kopya oylarını tek kanıt saymaz."""
    text=str(name or "").lower()
    if "taşıma" in text or "küme" in text:
        return "Taşıma/Küme"
    if "yenilen" in text:
        return "Yenilenme"
    if "blok" in text:
        return "Blok"
    if "iskelet" in text:
        return "İskelet"
    if "benzer" in text or "sürpriz" in text:
        return "Benzer/Sürpriz"
    if "konsens" in text or "birleşik" in text:
        return "Konsensüs"
    return str(name or "Diğer")


def expert_vote_structure_v1858(items):
    """Kupon benzerliğini, uzman aile desteğini ve her kuponun bağımsızlık ağırlığını hesaplar."""
    rows=[]
    for it in (items or []):
        if str(it.get("Senaryo","")).startswith("🏆 OYNA"):
            continue
        nums=set(int(x) for x in it.get("Kupon",[]) if 1 <= int(x) <= 80)
        if nums:
            rows.append((scenario_family_v1858(it.get("Senaryo","")), nums))
    if not rows:
        return {}, {}, {}, 0.0

    weights=[]
    for i,(_,a) in enumerate(rows):
        sims=[]
        for j,(_,b) in enumerate(rows):
            if i==j:
                continue
            union=a|b
            sims.append(len(a&b)/len(union) if union else 0.0)
        avg_sim=sum(sims)/len(sims) if sims else 0.0
        # Yüksek örtüşen kuponun sözü azalır ama sıfırlanmaz.
        weights.append(1.0/(1.0+1.8*avg_sim))

    weighted=defaultdict(float)
    families=defaultdict(set)
    raw=Counter()
    for (fam,nums),wt in zip(rows,weights):
        for n in nums:
            weighted[n]+=wt
            families[n].add(fam)
            raw[n]+=1

    family_count={n:len(v) for n,v in families.items()}
    max_weight=max(weighted.values()) if weighted else 1.0
    weighted_norm={n:(v/max_weight if max_weight else 0.0) for n,v in weighted.items()}
    # 0..1: kuponlar birbirinin ne kadar kopyası?
    herd=1.0-(sum(weights)/len(weights)) if weights else 0.0
    return weighted_norm, family_count, raw, float(np.clip(herd,0.0,1.0))


def engine_votes_v18567(master, items, latest_set, skeleton, block_loc_info=None,
                        companion_map=None, packages=None, df=None):
    """
    Her sayı için motor bazlı ham oyları üretir.
    """
    w = rest_return_scores_v18566(df, master, latest_set, lookback=500).copy()
    score_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in w.columns else (
        "V18.5 Nefes Puanı" if "V18.5 Nefes Puanı" in w.columns else "V18 Nefes Puanı"
    )

    usage=Counter()
    scen={}
    for it in (items or []):
        sname=str(it.get("Senaryo",""))
        for n in set(int(x) for x in it.get("Kupon",[])):
            usage[n]+=1
            scen.setdefault(n,set()).add(sname)

    maxu=max(usage.values()) if usage else 1
    maxs=max((len(v) for v in scen.values()), default=1)
    w["Oy_Senaryo"]=w["Sayı"].astype(int).map(lambda n: usage.get(int(n),0)/maxu)
    w["Oy_SenaryoÇeşit"]=w["Sayı"].astype(int).map(lambda n: len(scen.get(int(n),set()))/maxs)

    # V18.5.8 — uzman oylarının gerçekten bağımsız olup olmadığını ayır.
    _wexpert, _families, _rawexpert, _herd = expert_vote_structure_v1858(items)
    _max_family=max(_families.values()) if _families else 1
    w["Oy_UzmanAğırlık 58"] = w["Sayı"].astype(int).map(lambda n: _wexpert.get(int(n),0.0)).fillna(0.0)
    w["Uzman Aile Desteği 58"] = w["Sayı"].astype(int).map(lambda n: _families.get(int(n),0)).fillna(0).astype(int)
    w["Oy_UzmanAileÇeşit 58"] = w["Sayı"].astype(int).map(
        lambda n: _families.get(int(n),0)/max(_max_family,1)
    ).fillna(0.0)
    # Çok kuponda görünmek ama az uzman ailesinden gelmek = korelasyon/sürü riski.
    w["Uzman Korelasyon 58"] = (
        100.0 * (w["Oy_Senaryo"] - 0.72*w["Oy_UzmanAileÇeşit 58"]).clip(lower=0.0)
    )
    w["Uzman Sürü Basıncı 58"] = float(_herd*100.0)

    carry_col = "Taşıma Kimlik 565" if "Taşıma Kimlik 565" in w.columns else (
        "Taşıma Kimlik 563" if "Taşıma Kimlik 563" in w.columns else (
            "Devam Puanı 562" if "Devam Puanı 562" in w.columns else "Taşıma Kimlik"
        )
    )

    comp={}
    if companion_map:
        for _,tab in companion_map.items():
            if tab is None or tab.empty:
                continue
            for _,r in tab.head(15).iterrows():
                n=int(r["Sayı"])
                comp[n]=max(comp.get(n,0.0), float(r.get("Eşlikçi Puanı",0.0)))
    w["Oy_Eşlikçi"]=w["Sayı"].astype(int).map(comp).fillna(0.0)

    pkg={}
    for p in (packages or []):
        ps=float(p.get("Paket Puanı 565",0.0))
        for n in p.get("Paket",()):
            pkg[int(n)]=max(pkg.get(int(n),0.0), ps)
    w["Oy_BlokPaket"]=w["Sayı"].astype(int).map(pkg).fillna(0.0)

    reg={}
    if block_loc_info:
        main=block_loc_info.get("Ana Bölge")
        alt=block_loc_info.get("Alternatif Bölge")
        mp=float(block_loc_info.get("Ana Puan",0.0))
        ap=float(block_loc_info.get("Alternatif Puan",0.0))
        for n in range(1,81):
            band=ten_band_name(n)
            if band==main:
                reg[n]=mp
            elif band==alt:
                reg[n]=0.88*ap
            else:
                reg[n]=0.0
    w["Oy_Bölge"]=w["Sayı"].astype(int).map(reg).fillna(0.0)

    w["Oy_Taşıma"]=pd.to_numeric(w.get(carry_col,0.0),errors="coerce").fillna(0.0)
    w["Oy_Dinlenmiş"]=pd.to_numeric(w.get("Dönüş Puanı 566",0.0),errors="coerce").fillna(0.0)
    w["Oy_Blok"]=(
        0.55*normalized_series(pd.to_numeric(w.get("Blok Mikro 56",0.0),errors="coerce").fillna(0.0))
        +0.45*normalized_series(pd.to_numeric(w.get("Blok Sonraki Görülme 56",0.0),errors="coerce").fillna(0.0))
    )*100.0
    w["Oy_Temel"]=pd.to_numeric(w[score_col],errors="coerce").fillna(0.0)

    # independent evidence count
    ev = pd.Series(0.0,index=w.index)
    for col,thr in [
        ("Oy_UzmanAğırlık 58",0.45),("Oy_Taşıma",55),("Oy_Dinlenmiş",58),("Oy_Blok",55),
        ("Oy_Bölge",70),("Oy_Eşlikçi",55),("Oy_BlokPaket",45)
    ]:
        vals=pd.to_numeric(w[col],errors="coerce").fillna(0.0)
        ev += (vals>=thr).astype(float)
    w["Bağımsız Motor 567"]=ev
    return w


def expert_context_calibration_v1857(df, target_time=None, character_window=12):
    """V18.5.8: saat + gün fazı + yakın karaktere göre uzman motor katsayılarını kalibre eder."""
    out = {"Taşıma":1.0,"Dinlenmiş":1.0,"Blok":1.0,"Bölge":1.0,"Eşlikçi":1.0,"Senaryo":1.0,"KarşıRejim":1.0}
    if df is None or len(df) < 30:
        return out, {"Faz":"Yetersiz veri","Benzer":0,"Saat":str(target_time or "")}
    work=df.sort_values("Cekilis_No").reset_index(drop=True)
    if target_time is None:
        _,_,target_time=next_draw_defaults(work)
    try:
        th,tm=map(int,str(target_time)[:5].split(":")); target_min=th*60+tm
    except Exception:
        target_min=0
    phase=period_name(f"{target_min//60:02d}:{target_min%60:02d}")
    sets=row_sets(work)
    events=[]
    for i in range(3,len(work)):
        t=str(work.iloc[i]["Saat"])
        try:
            hh,mm=map(int,t[:5].split(":")); mins=hh*60+mm
        except Exception:
            continue
        same_phase=period_name(t)==phase
        clock_dist=abs(mins-target_min); clock_dist=min(clock_dist,1440-clock_dist)
        if not same_phase and clock_dist>60: continue
        prev=sets[i-1]; cur=sets[i]
        carry=len(prev&cur)/20.0
        blocks=consecutive_blocks(cur)
        block_strength=min(1.0,(sum(max(0,len(b)-1) for b in blocks))/5.0)
        prev_bands=Counter(ten_band_name(n) for n in prev)
        cur_bands=Counter(ten_band_name(n) for n in cur)
        dominant=prev_bands.most_common(1)[0][0] if prev_bands else None
        region=(cur_bands.get(dominant,0)/20.0) if dominant else 0.0
        rested=((cur-prev)&(sets[i-2]|sets[i-3]))
        rest=len(rested)/20.0
        pair_follow=0.0
        if prev:
            pair_follow=len(cur & set(n for n in range(1,81) if any(abs(n-x)<=2 for x in prev)))/20.0
        age=max(0,(len(work)-1)-i)
        recency=np.exp(-age/max(12.0,float(character_window)*7.0))
        weight=(1.0/(1.0+clock_dist/30.0))*(0.45+0.55*recency)
        events.append((weight,carry,block_strength,region,rest,pair_follow))
    if not events:
        return out,{"Faz":phase,"Benzer":0,"Saat":str(target_time)}
    def wav(idx):
        den=sum(e[0] for e in events) or 1.0
        return sum(e[0]*e[idx] for e in events)/den
    # 0.25 rastgele tabanına göre yumuşak, sınırlı katsayılar; aşırı öğrenmeyi önler.
    out["Taşıma"]=float(np.clip(0.82+1.05*wav(1),0.78,1.28))
    out["Blok"]=float(np.clip(0.84+0.75*wav(2),0.78,1.28))
    out["Bölge"]=float(np.clip(0.86+1.10*wav(3),0.78,1.24))
    out["Dinlenmiş"]=float(np.clip(0.84+1.10*wav(4),0.78,1.26))
    out["Eşlikçi"]=float(np.clip(0.84+0.70*wav(5),0.80,1.22))
    return out,{"Faz":phase,"Benzer":len(events),"Saat":str(target_time)}


def apply_herd_brake_v1857(votes):
    """Aynı senaryo ailesinin toplu oyunu bağımsız kanıt sanma hatasını azaltır."""
    v=votes.copy()
    scen=normalized_series(pd.to_numeric(v["Oy_Senaryo"],errors="coerce").fillna(0.0))
    diversity=normalized_series(pd.to_numeric(v["Oy_SenaryoÇeşit"],errors="coerce").fillna(0.0))
    independent=normalized_series(pd.to_numeric(v["Bağımsız Motor 567"],errors="coerce").fillna(0.0))
    v["Sürü Freni 57"]=(scen*(1.0-diversity)*(1.0-independent))*12.0
    return v


def seven_seat_master_v18567(df, master, items, latest_set, skeleton, regime_summary,
                             block_loc_info=None, companion_map=None, packages=None, size=7,
                             character_window=6, target_time=None):
    """
    V18.5.6.7 TEK KUPON MASTER.
    MASTER'ı kuponların ortalaması olmaktan çıkarır:
    - motor formu
    - çapraz onay
    - taşıma adedi ile kimliği ayırma
    - dinlenmiş dönüş
    - bölge/mikro ayrımı
    - rejim kırılma sigortası
    - 7 koltuklu temsil
    """
    size=int(size)
    latest_set=set(int(x) for x in latest_set)
    votes=engine_votes_v18567(
        master,items,latest_set,skeleton,
        block_loc_info=block_loc_info,
        companion_map=companion_map,
        packages=packages,
        df=df
    )
    character_window=max(4,int(character_window or 6))
    form=recent_engine_form_v18567(df,lookback=character_window)
    break_guard=regime_break_guard_v18567(regime_summary,df)
    if not target_time:
        _, _, target_time = next_draw_defaults(df)
    context_form, context_info = expert_context_calibration_v1857(
        df, target_time=target_time, character_window=character_window
    )
    # Canlı form ile saat/faz formunu geometrik ortalama ile birleştir.
    # Böylece tek bir kısa pencere uzmanı aşırı şişiremez.
    for _k in form:
        form[_k] = float(np.sqrt(max(0.01, form[_k]) * max(0.01, context_form.get(_k, 1.0))))
    votes = apply_herd_brake_v1857(votes)

    def nrm(col):
        return normalized_series(pd.to_numeric(votes[col],errors="coerce").fillna(0.0))

    expected=float(skeleton.get("Taşıma",5.0))
    carry_cap = 2 if expected<4 else (3 if expected<5.5 else (4 if expected<7 else 5))

    # V18.5.8 — ham çoğunluk yerine korelasyondan arındırılmış uzman desteği.
    votes["Master567"] = (
        0.12*nrm("Oy_Temel")
        +0.10*form["Senaryo"]*nrm("Oy_Senaryo")
        +0.10*form["Senaryo"]*nrm("Oy_UzmanAğırlık 58")
        +0.07*form["Senaryo"]*nrm("Oy_UzmanAileÇeşit 58")
        +0.10*form["Taşıma"]*nrm("Oy_Taşıma")
        +0.10*form["Dinlenmiş"]*nrm("Oy_Dinlenmiş")
        +0.14*form["Blok"]*nrm("Oy_Blok")
        +0.08*form["Bölge"]*nrm("Oy_Bölge")
        +0.07*form["Eşlikçi"]*nrm("Oy_Eşlikçi")
        +0.07*form["Blok"]*nrm("Oy_BlokPaket")
        +0.05*break_guard*nrm("Oy_Blok")
    )*100.0
    votes["Master567"] += 2.5*votes["Bağımsız Motor 567"]

    _ind = normalized_series(votes["Bağımsız Motor 567"])
    _fam = normalized_series(votes["Oy_UzmanAileÇeşit 58"])
    _corr = normalized_series(votes["Uzman Korelasyon 58"])
    votes["Uzman Bağımsızlık Bonusu 58"] = 7.5*_fam*(0.55+0.45*_ind)
    votes["Uzman Korelasyon Cezası 58"] = 10.0*_corr*(1.0-0.55*_ind)
    votes["Master567"] += votes["Uzman Bağımsızlık Bonusu 58"]
    votes["Master567"] -= votes["Uzman Korelasyon Cezası 58"]

    # Bağımsız keşif: uzman çoğunluğundan uzak ama temel/özel motorları güçlü adaya kapı bırak.
    votes["Keşif Puanı 58"] = (
        0.40*nrm("Oy_Temel") + 0.22*_ind + 0.14*nrm("Oy_Dinlenmiş")
        +0.12*nrm("Oy_Bölge") + 0.12*nrm("Oy_Eşlikçi")
        -0.22*nrm("Oy_Senaryo")
    )*100.0

    # Gerçek uzman çeşitliliği yüksekse sıralama bu sayıyı kolayca gömmesin.
    votes.loc[votes["Uzman Aile Desteği 58"]>=3,"Master567"] += 7.0
    votes.loc[(votes["Uzman Aile Desteği 58"]>=4) & (votes["Bağımsız Motor 567"]>=4),"Master567"] += 6.0

    ranked=votes.sort_values(
        ["Master567","Bağımsız Motor 567","Oy_Temel"],
        ascending=[False,False,False]
    ).reset_index(drop=True)

    multi=float(regime_summary.get("Çoklu Küçük %",0.0)) if regime_summary else 0.0
    longp=float(regime_summary.get("Uzun Blok %",0.0)) if regime_summary else 0.0
    herd_pressure=float(pd.to_numeric(votes["Uzman Sürü Basıncı 58"],errors="coerce").fillna(0.0).max())
    max_run=2 if (multi>=65 and herd_pressure>=28) else (3 if multi>=65 and longp<35 else 4)
    max_band=2 if herd_pressure>=35 else 3

    selected=[]
    seat_reason={}
    band_counts=Counter()
    carry_used=0

    def runlen(nums):
        s=sorted(set(nums))
        if not s: return 0
        best=cur=1
        for a,b in zip(s,s[1:]):
            if b==a+1:
                cur+=1; best=max(best,cur)
            else:
                cur=1
        return best

    def can_add(n, allow_counter=False):
        nonlocal carry_used
        n=int(n)
        if n in selected:
            return False
        if band_counts[ten_band_name(n)]>=max_band:
            return False
        if n in latest_set and carry_used>=carry_cap:
            return False
        if runlen(selected+[n])>max_run and not allow_counter:
            return False
        return True

    # Seat 1-2: strongest cross-engine approved numbers.
    for _,r in ranked.iterrows():
        if len(selected)>=2: break
        if int(r.get("Uzman Aile Desteği 58",0)) < 2: continue
        if float(r["Bağımsız Motor 567"])<3: continue
        n=int(r["Sayı"])
        if can_add(n):
            selected.append(n); seat_reason[n]="Çapraz Motor"
            band_counts[ten_band_name(n)]+=1
            if n in latest_set: carry_used+=1

    # Seat 3: strongest carry identity, but not forced if weak.
    carr=ranked[ranked["Sayı"].astype(int).isin(latest_set)].sort_values(
        ["Oy_Taşıma","Master567"],ascending=False
    )
    for _,r in carr.iterrows():
        if float(r["Oy_Taşıma"])<55: break
        n=int(r["Sayı"])
        if can_add(n):
            selected.append(n); seat_reason[n]="Taşıma"
            band_counts[ten_band_name(n)]+=1; carry_used+=1
            break

    # Seat 4: strongest rested return, only if genuinely strong.
    rest=ranked[~ranked["Sayı"].astype(int).isin(latest_set)].sort_values(
        ["Oy_Dinlenmiş","Master567"],ascending=False
    )
    for _,r in rest.iterrows():
        if float(r["Oy_Dinlenmiş"])<62: break
        n=int(r["Sayı"])
        if can_add(n):
            selected.append(n); seat_reason[n]="Dinlenmiş Dönüş"
            band_counts[ten_band_name(n)]+=1
            break

    # Seat 5: block specialist.
    blk=ranked.sort_values(["Oy_Blok","Oy_BlokPaket","Master567"],ascending=False)
    for _,r in blk.iterrows():
        n=int(r["Sayı"])
        if float(r["Oy_Blok"])<52 and float(r["Oy_BlokPaket"])<45:
            break
        if can_add(n):
            selected.append(n); seat_reason[n]="Blok"
            band_counts[ten_band_name(n)]+=1
            if n in latest_set: carry_used+=1
            break

    # Seat 6: region/micro specialist.
    reg=ranked.sort_values(["Oy_Bölge","Master567"],ascending=False)
    for _,r in reg.iterrows():
        n=int(r["Sayı"])
        if float(r["Oy_Bölge"])<70: break
        if can_add(n):
            selected.append(n); seat_reason[n]="Bölge/Mikro"
            band_counts[ten_band_name(n)]+=1
            if n in latest_set: carry_used+=1
            break

    # Son koltuklardan birini bağımsız keşfe ayır; kalanları toplam güçle tamamla.
    reserve_discovery = 1 if size >= 7 else 0
    general_target=max(0,size-reserve_discovery)
    for _,r in ranked.iterrows():
        if len(selected)>=general_target: break
        n=int(r["Sayı"])
        if can_add(n):
            selected.append(n); seat_reason[n]="Toplam Güç"
            band_counts[ten_band_name(n)]+=1
            if n in latest_set: carry_used+=1

    if len(selected) < size:
        discovery=votes.sort_values(
            ["Keşif Puanı 58","Master567","Oy_Temel"], ascending=False
        )
        for _,r in discovery.iterrows():
            n=int(r["Sayı"])
            # Keşif koltuğu uzman sürüsünün kopyası olmasın.
            if float(r["Oy_Senaryo"])>0.72 and int(r.get("Uzman Aile Desteği 58",0))>=3:
                continue
            if can_add(n, allow_counter=(break_guard>=0.50)):
                selected.append(n); seat_reason[n]="Bağımsız Keşif"
                band_counts[ten_band_name(n)]+=1
                if n in latest_set: carry_used+=1
                break

    # Keşif adayı bulunamazsa normal sıralamayla tamamla.
    for _,r in ranked.iterrows():
        if len(selected)>=size: break
        n=int(r["Sayı"])
        if can_add(n):
            selected.append(n); seat_reason[n]="Toplam Güç"
            band_counts[ten_band_name(n)]+=1
            if n in latest_set: carry_used+=1

    # Counter-regime insurance: if no long-block-ish adjacency represented and
    # recent long blocks exist, allow one controlled swap from top block candidate.
    if break_guard>=0.45 and runlen(selected)<2:
        for _,r in blk.iterrows():
            n=int(r["Sayı"])
            if n in selected: continue
            if any(abs(n-x)==1 for x in selected):
                # replace weakest total-gain seat
                _swappable=[x for x in selected if seat_reason.get(x) not in ("Çapraz Motor","Bağımsız Keşif")]
                if not _swappable:
                    _swappable=list(selected)
                weak=min(_swappable,key=lambda x: float(votes.loc[votes["Sayı"].astype(int)==x,"Master567"].iloc[0]))
                trial=[x for x in selected if x!=weak]+[n]
                if runlen(trial)<=4:
                    selected=trial
                    seat_reason.pop(weak,None)
                    seat_reason[n]="Karşı Rejim"
                    break

    selected=sorted(selected[:size])

    # Explanation table only for chosen numbers.
    expl=votes[votes["Sayı"].astype(int).isin(selected)].copy()
    expl["Seçim Nedeni 567"]=expl["Sayı"].astype(int).map(seat_reason).fillna("Toplam Güç")
    expl["Hedef Faz 57"] = context_info.get("Faz", "")
    expl["Benzer Saat/Faz Olayı 57"] = int(context_info.get("Benzer", 0))
    expl["Karakter Penceresi 58"] = int(character_window)
    expl["Sürü Basıncı 58"] = float(herd_pressure)
    expl=expl.sort_values("Master567",ascending=False)
    form["Hedef Faz"] = context_info.get("Faz", "")
    form["Benzer Saat/Faz Olayı"] = int(context_info.get("Benzer", 0))
    form["Karakter Penceresi"] = int(character_window)
    form["Sürü Basıncı"] = round(float(herd_pressure),2)
    return selected, expl, form, break_guard


def master_item_v18567(df, master, items, latest_set, skeleton, regime_summary,
                      block_loc_info=None, companion_map=None, packages=None, size=7,
                      character_window=6, target_time=None):
    coupon, expl, form, break_guard = seven_seat_master_v18567(
        df,master,items,latest_set,skeleton,regime_summary,
        block_loc_info=block_loc_info,
        companion_map=companion_map,
        packages=packages,
        size=size,
        character_window=character_window,
        target_time=target_time,
    )
    return {
        "Senaryo":"🏆 OYNA — MASTER 7",
        "Kupon":coupon,
        "Master Açıklama 567":expl,
        "Motor Form 567":form,
        "Rejim Sigorta 567":break_guard,
    }

def generate_v1856_coupons(master1856, latest_set, skeleton, block_forecast, block_birth185,
                           regime_summary, size=7, count=5, df_hist=None, block_loc_info=None,
                           character_window=6, target_time=None):
    """
    V18.5.5'in 5 yaşayan kuponunu korur.
    Üstüne:
      1) blok rejim düzeltmesi
      2) akıllı ortak çekirdek/çeşitlilik
      3) V18 Kupon 6 — Birleşik Güç
    ekler.
    """
    items = generate_v1855_coupons(
        master1856, latest_set, skeleton, block_forecast, block_birth185,
        size=size, count=count
    )
    items = apply_block_regime_to_items_v1856(
        items, master1856, block_birth185, regime_summary, size
    )

    # V18.5.6.2: rejim motorunun kararını kuponlara gerçekten uygula.
    # Çoklu Küçük rejimde tek 10'luk bölgeye aşırı yığılmayı kır ve
    # en güçlü 2-3 mikro-bölgeye temsil ver.
    master1856 = carry_continue_break_v18562(master1856, latest_set)
    items = apply_regime_distribution_v18562(
        items, master1856, regime_summary, size=size
    )

    master1856 = carry_identity_v18563(
        df_hist, master1856, latest_set, skeleton.get("Taşıma", 5.0)
    )
    items = shared_core_brake_v18563(items, master1856, max_share_ratio=0.67, protected=1)
    for _it in items:
        _it["Kupon"] = block_region_transfer_v18563(
            _it.get("Kupon", []), master1856, block_loc_info, size=size
        )

    # V18.5.6.4 — Çekirdek -> Eşlikçi:
    # En güçlü taşıma/nefes çekirdeklerini al, beraber çıkma + lift + kısa dönem +
    # taşıma beraberliği + komşuluk ile eşlikçi üret ve senaryolara dağıt.
    _carry_col = "Taşıma Kimlik 563" if "Taşıma Kimlik 563" in master1856.columns else (
        "Devam Puanı 562" if "Devam Puanı 562" in master1856.columns else "Taşıma Kimlik"
    )
    _score_col = "V18.5.6 Nefes Puanı" if "V18.5.6 Nefes Puanı" in master1856.columns else "V18.5 Nefes Puanı"
    _tmp = master1856.copy()
    _tmp["Core5634"] = 0.58*normalized_series(_tmp[_score_col]) + 0.42*normalized_series(_tmp[_carry_col])
    _core_numbers = _tmp.sort_values("Core5634", ascending=False)["Sayı"].astype(int).head(4).tolist()
    _companions = core_companion_engine_v18564(df_hist, master1856, _core_numbers, latest_set)
    items = inject_companions_v18564(items, _companions, _core_numbers, max_companions_per_coupon=1)
    items = deduplicate_coupons_v18564(items, master1856, min_difference=2)

    # V18.5.6.5 — testlerden çıkan üç tekrarlayan sorun:
    # taşıma kimliği, mikro-konum ve blok paket devamı.
    master1856 = carry_identity_v18565(
        df_hist, master1856, latest_set, skeleton.get("Taşıma", 5.0)
    )
    _packages565 = block_package_engine_v18565(df_hist, latest_set, lookback=500)
    items = inject_block_package_v18565(items, _packages565, master1856, size=size)
    items = micro_location_calibration_v18565(
        items, master1856, block_loc_info, regime_summary, size=size
    )
    items = dynamic_core_brake_v18565(items, master1856, hard_max_share=0.83)
    items = deduplicate_coupons_v18564(items, master1856, min_difference=2)

    consensus = consensus_coupon_v1856(
        items, master1856, latest_set, skeleton, size=size
    )
    consensus = regime_distribution_coupon_v18562(
        consensus, master1856, regime_summary, size=size
    )
    _cons_item565 = [{"Senaryo":"Birleşik Güç/Konsensüs","Kupon":consensus}]
    _cons_item565 = micro_location_calibration_v18565(
        _cons_item565, master1856, block_loc_info, regime_summary, size=size
    )
    consensus = _cons_item565[0]["Kupon"] if _cons_item565 else consensus
    if consensus and all(set(consensus) != set(item.get("Kupon",[])) for item in items):
        items.append({
            "Senaryo": "Birleşik Güç/Konsensüs",
            "Kupon": consensus,
        })
    items = deduplicate_coupons_v18564(items, master1856, min_difference=2)

    # V18.5.6.7 — Tek kupon odaklı yeni MASTER karar merkezi.
    # Eski kuponlar laboratuvar/test olarak korunur; esas oynanacak kolon budur.
    _master567 = master_item_v18567(
        df_hist,
        master1856,
        items,
        latest_set,
        skeleton,
        regime_summary,
        block_loc_info=block_loc_info,
        companion_map=_companions,
        packages=_packages565,
        size=size,
        character_window=character_window,
        target_time=target_time,
    )
    if _master567.get("Kupon"):
        items.append(_master567)

    return items


def generate_v1855_coupons(master1855, latest_set, skeleton, block_forecast, block_birth185, size=7, count=5):
    """
    Mevcut V18.5 kupon üretimini korur; V18.5.5 yalnızca son puanı ve
    kupon çeşitlilik frenini ekler.
    """
    items = generate_v185_coupons(
        master1855, latest_set, skeleton, block_forecast, block_birth185,
        size=size, count=count
    )
    return diversify_coupons_v1855(items, master1855, max_common=4)


def decorate_master_v185(master184, location_df, lifecycle_df=None):
    out = master184.copy()
    loc = location_df.set_index("Bölge")["Konum Puanı"].to_dict() if location_df is not None and not location_df.empty else {}
    out["Blok Konum"] = [float(loc.get(ten_band_name(int(n)),0.0)) for n in out["Sayı"]]
    if lifecycle_df is not None and not lifecycle_df.empty:
        out = out.merge(lifecycle_df, on="Sayı", how="left")
    if "Blok Yaşam" not in out.columns:
        out["Blok Yaşam"] = 0.0
    if "Blok Kırılma Riski" not in out.columns:
        out["Blok Kırılma Riski"] = 0.0
    out[["Blok Yaşam", "Blok Kırılma Riski"]] = out[["Blok Yaşam", "Blok Kırılma Riski"]].fillna(0.0)
    out["V18.5 Nefes Puanı"] = (
        0.80 * normalized_series(out["V18.4 Nefes Puanı"])
        + 0.12 * normalized_series(out["Blok Konum"])
        + 0.08 * normalized_series(out["Blok Yaşam"])
    ) * 100.0
    out["V18.5 Nefes Puanı"] -= 0.06 * out["Blok Kırılma Riski"]
    out["V18.5 Nefes Puanı"] = out["V18.5 Nefes Puanı"].clip(0,100).round(2)
    return out.sort_values(["V18.5 Nefes Puanı","Sayı"], ascending=[False,True])


def generate_v185_coupons(master185, latest_set, skeleton, block_forecast, block_birth185, size=7, count=5):
    """
    V18.5:
      1) V18.4 kupon üretimini korur.
      2) Blok Doğum kuponunda konum-sıralı blok adayını kullanır.
      3) Ortak çekirdek frenini uygular.
    """
    temp = master185.copy()
    # V18.4 üreticisi "V18.4 Nefes Puanı" okur; V18.5'te seçim için
    # son puanı kullanmasını istiyoruz.
    temp["V18.4 Nefes Puanı"] = temp["V18.5 Nefes Puanı"]

    items = generate_v184_coupons(
        temp, latest_set, skeleton, block_forecast, block_birth185,
        size=size, count=count
    )

    items = common_core_brake_v185(items, master185, max_share=0.80)
    return items


PAGES = [
    "✅ Kontrol",
    "🧠 Güç Puanı",
    "📈 Frekans",
    "🔗 Birlikte Çıkma",
    "🔥 Sıcak/Soğuk",
    "⏳ Dinlenme/Döngü",
    "🔄 Tekrar/Blok",
    "🔁 Elden Ele / Blok Ağı",
    "🧭 Çekiliş Evrimi V14",
    "🧠 Canlı Motor V15",
    "🧬 Canlı Karar V16",
    "🧠 Yaşayan Motor V17",
    "🫁 Living Engine V18",
    "📊 Bant/Saat",
    "🧭 Benzerlik",
    "🧬 Değişim",
    "🌙 Kapanış",
    "🎯 Süper Kupon",
    "🔀 Geçiş Kuponu",
    "🧪 Kupon Laboratuvarı",
    "💾 Kupon Arşivi",
    "✅ Sonuç Kontrol",
    "➕ Yeni Çekiliş",
    "⬇️ Dışa Aktar",
]

with st.sidebar:
    st.divider()
    page = st.radio("📌 Bölüm seç", PAGES, index=0)

if page == "✅ Kontrol":
    st.success("Çalışan sürüm: V18.5.6 — Ana dosya: app.py")
    st.write(f"Ana havuz: **{len(base_df)}** çekiliş")
    gh_settings, gh_error = github_settings()
    if gh_error:
        st.warning("Kalıcı GitHub kayıt: Kapalı")
    else:
        st.success(
            f"Kalıcı GitHub kayıt: Hazır — "
            f"{gh_settings['owner']}/{gh_settings['repo']}/"
            f"{gh_settings['path']}"
        )

    st.write(
        f"Bu oturumda yüklenen ek veri: "
        f"**{len(st.session_state.extra_df)}** çekiliş"
    )

    if missing:
        st.warning(
            "Eksik çekiliş numaraları: "
            + ", ".join(map(str, missing[:500]))
        )
    else:
        st.success("Çekiliş numaraları kesintisiz.")

    if base_invalid:
        with st.expander("Ana dosyada atlanan satırlar"):
            st.code("\n".join(base_invalid[:300]))

    # Ana veri havuzundaki bozuk çekiliş numaralarını tespit et.
    raw_base = base_df.copy()
    repaired_base, repaired_count = repair_draw_numbers(raw_base)
    repaired_base = clean_df(repaired_base)

    if repaired_count > 0:
        st.error(
            f"Ana veri havuzunda {repaired_count} bozuk çekiliş numarası bulundu. "
            "Örnek: 4706205 → 47062."
        )
        st.download_button(
            "Önce düzeltilmiş veri.txt yedeğini indir",
            data=to_text(repaired_base).encode("utf-8"),
            file_name="veri_duzeltilmis.txt",
            mime="text/plain",
            key="v111_repaired_backup",
        )
        persistent_save_panel(repaired_base, "v111_repair_base")
    else:
        st.success("Çekiliş numarası biçimleri temiz.")

    if not st.session_state.extra_df.empty:
        st.divider()
        st.subheader("💾 Yüklenen çekilişleri kalıcılaştır")
        st.write(
            f"Birleşik havuz: **{len(df)} çekiliş** — "
            f"son çekiliş **{int(df.iloc[-1].Cekilis_No)}**"
        )
        st.download_button(
            "Önce yedek veri.txt indir",
            data=to_text(df).encode("utf-8"),
            file_name="veri.txt",
            mime="text/plain",
            key="control_backup",
        )
        persistent_save_panel(df, "control_bulk_save")

elif page == "🧠 Güç Puanı":
    st.subheader("0–100 Akıllı Güç Puanı")
    target_time = st.text_input(
        "Hedef saat", value=str(latest.Saat), key="score_target_time_v102"
    )
    try:
        score_df = intelligent_score_table(df, target_time)
        st.dataframe(score_df, use_container_width=True, hide_index=True)
        st.bar_chart(score_df.head(25).set_index("Sayı")["Toplam Puan"])
    except Exception as exc:
        st.error(f"Puan hesaplanamadı: {exc}")

elif page == "📈 Frekans":
    f = frequency(adf).sort_values(
        ["Frekans", "Sayı"], ascending=[False, True]
    )
    st.dataframe(f, use_container_width=True, hide_index=True)
    st.bar_chart(f.sort_values("Sayı").set_index("Sayı")["Frekans"])

elif page == "🔗 Birlikte Çıkma":
    combo_size = st.selectbox("Grup büyüklüğü", [2, 3, 4, 5], index=0)
    top_n = st.slider(
        f"İlk kaç {combo_size}’li?", 10, 100, 30,
        key=f"combo_v102_{combo_size}"
    )
    with st.spinner(f"{combo_size}’li gruplar hesaplanıyor..."):
        st.dataframe(
            combo_dates(adf, combo_size, top_n),
            use_container_width=True,
            hide_index=True,
        )

elif page == "🔥 Sıcak/Soğuk":
    merged = frequency(adf).merge(gaps(df), on="Sayı")
    left, right = st.columns(2)
    with left:
        st.subheader("Sıcak")
        st.dataframe(
            merged.sort_values(
                ["Frekans", "Dinlenme"], ascending=[False, True]
            ).head(20),
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.subheader("Soğuk / dinlenmiş")
        st.dataframe(
            merged.sort_values(
                ["Dinlenme", "Frekans"], ascending=[False, True]
            ).head(20),
            use_container_width=True,
            hide_index=True,
        )

elif page == "⏳ Dinlenme/Döngü":
    st.subheader("Dönüş döngüleri")
    cycle_df = return_cycle_table(df)
    st.dataframe(
        cycle_df.sort_values(
            ["Mevcut dinlenme", "Ort. dönüş aralığı"],
            ascending=False,
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Tekrar serileri ve kırılmalar")
    st.dataframe(
        streak_table(df).sort_values(
            ["Mevcut seri", "En uzun seri"], ascending=False
        ),
        use_container_width=True,
        hide_index=True,
    )

elif page == "🔄 Tekrar/Blok":
    st.subheader("Çekilişler arası tekrar")
    st.dataframe(
        repeat_table(adf).head(200),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Ardışık blok ve sağa/sola kayma")
    st.dataframe(
        block_table(df, min(window, 300)),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("2–5’li blok laboratuvarı")
    st.dataframe(
        block_length_summary(adf),
        use_container_width=True,
        hide_index=True,
    )


elif page == "🔁 Elden Ele / Blok Ağı":
    st.header("🔁 Elden Ele Geçiş ve Blok Ağı")

    target_time = st.text_input(
        "Hedef saat",
        value=str(latest.Saat),
        key="v130_carry_target_time",
    )
    analysis_window = st.selectbox(
        "Geçmiş pencere",
        [50, 100, 200, 300, 500, len(df)],
        index=min(4, 5),
        key="v130_carry_window",
    )

    detail, distribution = carryover_distribution(
        df,
        analysis_window,
    )

    if not detail.empty:
        mean_carry = float(detail["Taşınan sayı"].mean())
        median_carry = float(detail["Taşınan sayı"].median())
        last_carry = int(detail.iloc[0]["Taşınan sayı"])

        m1, m2, m3 = st.columns(3)
        m1.metric("Ortalama taşınan", f"{mean_carry:.2f}")
        m2.metric("Medyan taşınan", f"{median_carry:.0f}")
        m3.metric("Son elde taşınan", last_carry)

        st.subheader("Taşınan sayı adedi dağılımı")
        st.dataframe(
            distribution,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Son elden güçlü taşıma adayları")
        carry_scores = carryover_number_scores(
            df,
            target_time,
            analysis_window,
        )
        st.dataframe(
            carry_scores[
                [
                    "Sayı",
                    "Taşıma Puanı",
                    "Sınıf",
                    "Genel tekrar oranı",
                    "Son 25 tekrar oranı",
                    "Mevcut seri",
                    "Son çekiliş bağı",
                    "Saat oranı",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Taşıyan sayılarla uyumlu yeni/dönüş adayları")
        new_scores = new_arrival_scores(
            df,
            carry_scores,
            target_time,
            analysis_window,
        )
        st.dataframe(
            new_scores[
                [
                    "Sayı",
                    "Yeni Aday Puanı",
                    "Taşıyanlarla sonraki geliş",
                    "Kaynak desteği",
                    "Dönüş uyumu",
                    "Dinlenme",
                    "Saat oranı",
                ]
            ].head(30),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("🎯 Elden ele kupon üretici")
        c1, c2 = st.columns(2)
        with c1:
            carry_coupon_size = st.selectbox(
                "Kupon büyüklüğü",
                [3, 4, 5, 6, 7, 8, 10],
                index=4,
                key="v130_carry_coupon_size",
            )
        with c2:
            carry_coupon_count = st.slider(
                "Farklı kupon sayısı",
                1,
                10,
                4,
                key="v130_carry_coupon_count",
            )

        if st.button(
            "🔁 Farklı elden-ele kuponları üret",
            type="primary",
            key="v130_generate_carry_coupons",
        ):
            coupons = generate_unique_carryover_coupons(
                carry_scores,
                new_scores,
                carry_coupon_size,
                carry_coupon_count,
            )

            if not coupons:
                st.error("Farklı kupon üretilemedi.")
            else:
                for idx, coupon in enumerate(coupons, start=1):
                    st.success(
                        f"Elden Ele Kupon {idx}: "
                        + " - ".join(map(str, coupon))
                    )
                    st.dataframe(
                        explain_carryover_coupon(
                            coupon,
                            carry_scores,
                            new_scores,
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        st.divider()
        st.subheader("🧱 Blokların birbirleriyle çıkma eğilimi")
        block_freq, block_co, block_transition = block_network_tables(
            df,
            analysis_window,
        )

        b1, b2, b3 = st.tabs(
            [
                "Blok frekansı",
                "Aynı elde blok ağı",
                "Bir sonraki ele blok geçişi",
            ]
        )
        with b1:
            st.dataframe(
                block_freq,
                use_container_width=True,
                hide_index=True,
            )
        with b2:
            st.dataframe(
                block_co,
                use_container_width=True,
                hide_index=True,
            )
        with b3:
            st.dataframe(
                block_transition,
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("Son elden ele ayrıntı")
        st.dataframe(
            detail.head(100),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Elden ele analiz için yeterli çekiliş yok.")


elif page == "🧭 Çekiliş Evrimi V14":
    st.header("🧭 Çekiliş Evrimi ve Rol Tabanlı Kupon")

    if len(df) < 2:
        st.info("Bu analiz için en az iki çekiliş gerekli.")
    else:
        transition_window = st.selectbox(
            "Geçiş geçmişi",
            [50, 100, 200, 300, 500, len(df)],
            index=min(4, 5),
            key="v140_transition_window",
        )
        target_time = st.text_input(
            "Hedef saat",
            value=str(latest.Saat),
            key="v140_target_time",
        )

        summary, band_change = draw_transition_report(df)

        st.subheader(
            f"Son geçiş: #{summary['Önceki çekiliş']} → "
            f"#{summary['Sonraki çekiliş']}"
        )
        m1, m2, m3 = st.columns(3)
        m1.metric("Taşınan sayı", summary["Taşınan sayı adedi"])
        m2.metric("Yeni gelen", len(summary["Yeni gelenler"]))
        m3.metric("Yerini bırakan", len(summary["Yerini bırakanlar"]))

        st.write(
            "**Taşınanlar:** "
            + (" - ".join(map(str, summary["Taşınanlar"])) or "Yok")
        )
        st.write(
            "**Yeni gelenler:** "
            + (" - ".join(map(str, summary["Yeni gelenler"])) or "Yok")
        )
        st.write(
            "**Yerini bırakanlar:** "
            + (" - ".join(map(str, summary["Yerini bırakanlar"])) or "Yok")
        )

        st.subheader("Bant geçişi")
        st.dataframe(
            band_change,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Sayıların yerini hangi sayılar alıyor?")
        replacement_map = replacement_map_table(
            df,
            transition_window,
            top_n=5,
        )
        st.dataframe(
            replacement_map.head(80),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Son çekilişe göre güçlü yerine-gelme adayları")
        replacement_scores = latest_replacement_candidates(
            df,
            transition_window,
        )
        st.dataframe(
            replacement_scores.head(30),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Blokların bloklara dönüşümü")
        block_replacements = block_replacement_network(
            df,
            transition_window,
        )
        st.dataframe(
            block_replacements.head(100),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Sıcak sayı yorulması")
        fatigue = fatigue_table(df, recommendation_window=5)
        st.dataframe(
            fatigue.head(30),
            use_container_width=True,
            hide_index=True,
        )

        carry_scores = carryover_number_scores(
            df,
            target_time,
            transition_window,
        )

        st.subheader("Rol tablosu")
        role_table = role_assignment_table(
            df,
            carry_scores,
            replacement_scores,
            target_time,
            transition_window,
        )
        st.dataframe(
            role_table,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("🎯 Rol tabanlı gelişmiş kupon üretici")
        c1, c2 = st.columns(2)
        with c1:
            role_coupon_size = st.selectbox(
                "Kupon büyüklüğü",
                [4, 5, 6, 7, 8, 10],
                index=5,
                key="v140_role_coupon_size",
            )
        with c2:
            role_coupon_count = st.slider(
                "Farklı kupon sayısı",
                1,
                10,
                4,
                key="v140_role_coupon_count",
            )

        if st.button(
            "🧭 Rol dengeli kuponları üret",
            type="primary",
            key="v140_generate_role_coupons",
        ):
            role_coupons = generate_role_balanced_coupons(
                role_table,
                role_coupon_size,
                role_coupon_count,
            )

            if not role_coupons:
                st.error("Rol dengeli kupon üretilemedi.")
            else:
                for idx, coupon in enumerate(role_coupons, start=1):
                    st.success(
                        f"V14 Rol Kuponu {idx}: "
                        + " - ".join(map(str, coupon))
                    )
                    st.dataframe(
                        explain_role_coupon(
                            coupon,
                            role_table,
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                st.info(
                    "Kuponlar taşıyıcı, yerine gelen, blok oyuncusu ve "
                    "dinlenip dönen rolleri birlikte kullanır. "
                    "Yorgun sayılar otomatik azaltılır."
                )


elif page == "🧠 Canlı Motor V15":
    st.header("🧠 Canlı Durum Motoru V15")
    st.caption(
        "Bu bölüm tek bir sabit puan formülü kullanmaz. "
        "Oyunun mevcut fazını tanır, motor ağırlıklarını değiştirir, "
        "geçmişte benzer durumları bulur ve bütün sinyalleri tek kararda birleştirir."
    )

    if len(df) < 40:
        st.info("Canlı motor için en az 40 çekiliş önerilir.")
    else:
        _, next_date, next_time = next_draw_defaults(df)

        top1, top2, top3 = st.columns(3)
        with top1:
            live_window = st.selectbox(
                "Canlı analiz geçmişi",
                [100, 200, 300, 500, len(df)],
                index=min(3, 4),
                key="v150_live_window",
            )
        with top2:
            live_target_time = st.text_input(
                "Hedef saat",
                value=next_time,
                key="v150_target_time",
            )
        with top3:
            state_window = st.selectbox(
                "Durum penceresi",
                [4, 6, 8, 12],
                index=1,
                key="v150_state_window",
            )

        features = behavior_feature_table(df)
        current_state, state_metrics = rolling_behavior_state(
            features,
            short_window=min(state_window, len(features)),
            long_window=min(24, len(features)),
        )

        st.subheader("1️⃣ Oyunun şu anki karakteri")
        p1, p2, p3 = st.columns(3)
        p1.metric("Canlı Faz", current_state.get("Faz", "-"))
        p2.metric("Faz güveni", f"%{current_state.get('Güven', 0):.1f}")
        p3.metric("Hedef", f"{next_date} {live_target_time}")

        st.dataframe(
            state_metrics,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("2️⃣ Saat karakteri")
        hours = hour_character_table(df.tail(min(live_window, len(df))))
        st.dataframe(
            hours,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("3️⃣ Son faz değişimleri")
        timeline = recent_phase_timeline(
            df,
            short_window=state_window,
            long_window=24,
            last_n=36,
        )
        if not timeline.empty:
            st.dataframe(
                timeline.head(36),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("4️⃣ Geçmişte bugüne benzeyen durumlar")
        with st.spinner("Benzer tarihsel durumlar aranıyor..."):
            similar_matches, similar_scores = similar_state_next_scores(
                df,
                state_window=state_window,
                search_window=live_window,
                top_matches=20,
            )
        left, right = st.columns(2)
        with left:
            st.dataframe(
                similar_matches.head(20),
                use_container_width=True,
                hide_index=True,
            )
        with right:
            st.dataframe(
                similar_scores.head(25),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("5️⃣ Tüm motorların ortak canlı puanı")
        with st.spinner("Taşıma, yerine geçme, blok, dönüş, saat ve benzer durum motorları birleştiriliyor..."):
            live_scores, live_state, live_weights = live_number_score_table(
                df,
                target_time=live_target_time,
                analysis_window=live_window,
                state_window=state_window,
            )

        weight_df = pd.DataFrame(
            [
                {
                    "Motor": name,
                    "Canlı ağırlık %": round(weight * 100, 2),
                }
                for name, weight in live_weights.items()
            ]
        ).sort_values("Canlı ağırlık %", ascending=False)

        st.write(
            f"**Motorun seçtiği aktif faz:** {live_state.get('Faz', '-')} "
            f"— güven %{live_state.get('Güven', 0):.1f}"
        )
        st.dataframe(
            weight_df,
            use_container_width=True,
            hide_index=True,
        )

        st.dataframe(
            live_scores[
                [
                    "Sayı",
                    "Canlı Puan",
                    "Canlı Rol",
                    "Taşıma",
                    "Yerine",
                    "Blok",
                    "Dönüş",
                    "Saat",
                    "Benzer",
                    "Kısaİvme",
                    "Yorgunluk",
                    "Son elde",
                ]
            ].head(40),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("6️⃣ Tek motor — farklı canlı kuponlar")
        q1, q2 = st.columns(2)
        with q1:
            live_coupon_size = st.selectbox(
                "Kupon büyüklüğü",
                [4, 5, 6, 7, 8, 10],
                index=3,
                key="v150_coupon_size",
            )
        with q2:
            live_coupon_count = st.slider(
                "Farklı kupon sayısı",
                1,
                10,
                4,
                key="v150_coupon_count",
            )

        if st.button(
            "🧠 CANLI KUPONLARI ÜRET",
            type="primary",
            key="v150_generate_live",
        ):
            live_coupons = generate_live_coupons(
                live_scores,
                size=live_coupon_size,
                count=live_coupon_count,
            )

            if not live_coupons:
                st.error("Canlı kupon üretilemedi.")
            else:
                st.session_state["v150_live_coupons"] = live_coupons
                st.session_state["v150_live_start_draw"] = int(df.iloc[-1].Cekilis_No) + 1

                for idx, coupon in enumerate(live_coupons, start=1):
                    st.success(
                        f"Canlı Kupon {idx}: "
                        + " - ".join(map(str, coupon))
                    )
                    st.dataframe(
                        explain_live_coupon(
                            coupon,
                            live_scores,
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        st.subheader("7️⃣ Walk-forward geçmiş testi")
        st.caption(
            "Her test noktasında yalnız o ana kadar bilinen veriyi kullanır; "
            "gelecek çekilişi modele göstermez."
        )
        bt1, bt2 = st.columns(2)
        with bt1:
            bt_count = st.slider(
                "Test edilecek son çekiliş",
                5,
                30,
                15,
                key="v150_backtest_count",
            )
        with bt2:
            bt_size = st.selectbox(
                "Backtest kupon büyüklüğü",
                [4, 5, 6, 7, 8, 10],
                index=3,
                key="v150_backtest_size",
            )

        if st.button(
            "🧪 CANLI MOTORU GERİYE DÖNÜK TEST ET",
            key="v150_run_backtest",
        ):
            with st.spinner("Walk-forward test çalışıyor; mobilde biraz sürebilir..."):
                bt = live_backtest(
                    df,
                    coupon_size=bt_size,
                    test_count=bt_count,
                    analysis_window=min(live_window, 300),
                )
            if bt.empty:
                st.warning("Backtest sonucu üretilemedi.")
            else:
                b1, b2, b3 = st.columns(3)
                b1.metric("Ortalama isabet", f"{bt['İsabet'].mean():.2f}")
                b2.metric("En yüksek", int(bt["İsabet"].max()))
                b3.metric("3+ sonuç", int((bt["İsabet"] >= 3).sum()))
                st.dataframe(
                    bt.sort_values("Çekiliş", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )


elif page == "🧬 Canlı Karar V16":
    st.header("🧬 Canlı Karar Motoru V16")
    st.caption(
        "Önce çekilişin iskeletini ve rejimini tahmin eder; "
        "sonra taşıma, yenilenme, blok, bölge, dönüş, eleme ve "
        "meta-öğrenme sinyallerini kullanarak farklı senaryolar üretir."
    )

    if len(df) < 80:
        st.info("V16 için en az 80 çekiliş önerilir.")
    else:
        _, next_date, next_time = next_draw_defaults(df)

        vcol1, vcol2, vcol3 = st.columns(3)
        with vcol1:
            v16_window = st.selectbox(
                "Geçmiş analiz penceresi",
                [150, 250, 300, 500, len(df)],
                index=min(3, 4),
                key="v160_window",
            )
        with vcol2:
            v16_state_window = st.selectbox(
                "Karakter penceresi",
                [4, 6, 8, 12],
                index=1,
                key="v160_state_window",
            )
        with vcol3:
            v16_target_time = st.text_input(
                "Hedef saat",
                value=next_time,
                key="v160_target_time",
            )

        st.subheader("1️⃣ Önce çekiliş iskeleti")
        with st.spinner("Geçmişteki benzer durumların sonraki çekilişleri inceleniyor..."):
            skeleton, skeleton_samples, region_forecast = skeleton_forecast(
                df,
                state_window=v16_state_window,
                search_window=v16_window,
                top_matches=25,
            )

        if skeleton:
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Beklenen taşıma", f"{skeleton.get('Taşıma', 0):.2f}")
            s2.metric("Beklenen yeni", f"{skeleton.get('Yeni', 0):.2f}")
            s3.metric("2'li blok yoğunluğu", f"{skeleton.get('2liBlok', 0):.2f}")
            s4.metric("Beklenen maks. blok", f"{skeleton.get('MaksBlok', 0):.2f}")

            st.write(
                f"**En aktif iki bölge:** "
                f"{skeleton.get('Aktif Bölge 1', '-')} ve "
                f"{skeleton.get('Aktif Bölge 2', '-')}"
            )
            st.dataframe(
                region_forecast,
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("2️⃣ Meta öğrenme — hangi motor son testlerde daha iyi?")
        st.caption(
            "İstersen çalıştır. Son gerçek çekilişlerde alt motorların top-N "
            "isabetini walk-forward biçimde ölçer."
        )

        meta_tests = st.slider(
            "Meta test sayısı",
            5,
            15,
            8,
            key="v160_meta_tests",
        )

        if st.button(
            "🧪 MOTOR GÜVENLERİNİ ÖLÇ",
            key="v160_measure_reliability",
        ):
            with st.spinner("Alt motorlar geriye dönük ölçülüyor..."):
                reliability_table, reliability = component_reliability_backtest_v16(
                    df,
                    coupon_size=7,
                    test_count=meta_tests,
                    analysis_window=min(v16_window, 250),
                )
            st.session_state["v160_reliability"] = reliability
            st.session_state["v160_reliability_table"] = reliability_table

        reliability = st.session_state.get("v160_reliability", {})
        reliability_table = st.session_state.get(
            "v160_reliability_table",
            pd.DataFrame(),
        )

        if not reliability_table.empty:
            st.dataframe(
                reliability_table,
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("3️⃣ Ana karar + eleme + roller")
        with st.spinner("V16 bütün sinyalleri tek karar tablosunda birleştiriyor..."):
            master, state, phase_weights, region_scores, elimination = v16_master_score_table(
                df,
                target_time=v16_target_time,
                analysis_window=v16_window,
                state_window=v16_state_window,
                reliability=reliability,
            )

        m1, m2, m3 = st.columns(3)
        m1.metric("Aktif rejim", state.get("Faz", "-"))
        m2.metric("Rejim güveni", f"%{state.get('Güven', 0):.1f}")
        m3.metric("Hedef çekiliş", f"#{int(df.iloc[-1].Cekilis_No)+1}")

        st.dataframe(
            master[
                [
                    "Sayı",
                    "V16 Ana Puan",
                    "Rol",
                    "Eleme Durumu",
                    "Eleme Puanı",
                    "Bölge",
                    "Bölge Puanı",
                    "Taşıma",
                    "Yerine",
                    "Blok",
                    "Dönüş",
                    "Benzer",
                    "Yorgunluk",
                    "Son elde",
                ]
            ].head(45),
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("En güçlü eleme adayları"):
            st.dataframe(
                elimination.head(25),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("4️⃣ Beş farklı olası gelecek senaryosu")
        qc1, qc2 = st.columns(2)
        with qc1:
            v16_size = st.selectbox(
                "Kupon büyüklüğü",
                [4, 5, 6, 7, 8, 10],
                index=3,
                key="v160_coupon_size",
            )
        with qc2:
            v16_count = st.slider(
                "Senaryo kuponu sayısı",
                1,
                5,
                5,
                key="v160_coupon_count",
            )

        if st.button(
            "🧬 V16 SENARYO KUPONLARINI ÜRET",
            type="primary",
            key="v160_generate",
        ):
            latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
            result_items = generate_v16_scenario_coupons(
                master,
                latest_set,
                skeleton,
                size=v16_size,
                count=v16_count,
            )

            if not result_items:
                st.error("V16 senaryo kuponları üretilemedi.")
            else:
                st.session_state["v160_coupons"] = result_items
                st.session_state["v160_start_draw"] = int(df.iloc[-1].Cekilis_No) + 1

                for idx, item in enumerate(result_items, start=1):
                    st.success(
                        f"V16 Kupon {idx} — {item['Senaryo']}: "
                        + " - ".join(map(str, item["Kupon"]))
                    )
                    st.dataframe(
                        explain_v16_coupon(
                            item["Kupon"],
                            master,
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        st.info(
            "V16'nın ana farkı: önce sayıları seçmez. Önce beklenen taşıma, "
            "yeni sayı, blok ve aktif bölgelerden çekiliş iskeletini kurar; "
            "sonra senaryoya uygun sayıları seçer. Yorgun/eleme puanı yüksek "
            "adayları da baskılar."
        )


elif page == "🧠 Yaşayan Motor V17":
    st.header("🧠 Yaşayan Motor V17")
    st.caption(
        "V16'nın iskelet + rejim + meta öğrenme mimarisine; "
        "blok doğumu, blok kayması, komşuluk/küme tamamlama ve kalıcı "
        "motor hafızası eklenmiştir."
    )

    if len(df) < 100:
        st.info("V17 için 100+ çekiliş önerilir.")
    else:
        _, next_date, next_time = next_draw_defaults(df)

        c1, c2, c3 = st.columns(3)
        with c1:
            v17_window = st.selectbox(
                "Analiz geçmişi",
                [200, 300, 500, len(df)],
                index=min(2, 3),
                key="v170_window",
            )
        with c2:
            v17_state_window = st.selectbox(
                "Karakter penceresi",
                [4, 6, 8, 12],
                index=1,
                key="v170_state_window",
            )
        with c3:
            v17_target_time = st.text_input(
                "Hedef saat",
                value=next_time,
                key="v170_target_time",
            )

        st.subheader("1️⃣ Çekiliş iskeleti")
        skeleton, skeleton_samples, region_forecast = skeleton_forecast(
            df,
            state_window=v17_state_window,
            search_window=v17_window,
            top_matches=25,
        )

        if skeleton:
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Beklenen taşıma", f"{skeleton.get('Taşıma', 0):.2f}")
            s2.metric("Beklenen yeni", f"{skeleton.get('Yeni', 0):.2f}")
            s3.metric("2'li blok", f"{skeleton.get('2liBlok', 0):.2f}")
            s4.metric("Maks blok", f"{skeleton.get('MaksBlok', 0):.2f}")

            st.write(
                f"**Aktif bölgeler:** "
                f"{skeleton.get('Aktif Bölge 1', '-')} / "
                f"{skeleton.get('Aktif Bölge 2', '-')}"
            )

        st.subheader("2️⃣ Blok doğum motoru")
        block_birth = block_birth_engine_v17(
            df,
            lookback=v17_window,
            target_time=v17_target_time,
        )

        if not block_birth.empty:
            st.dataframe(
                block_birth[
                    [
                        "Blok",
                        "Uzunluk",
                        "Blok Doğum Puanı",
                        "Mevcut bloktan geçiş",
                        "Sağ/Sol kayma",
                        "Saat desteği",
                        "Benzer durum",
                        "Kaynak desteği",
                    ]
                ].head(40),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("3️⃣ Blok sağa/sola kayma")
        shifts = block_shift_table_v17(df, lookback=v17_window)
        if not shifts.empty:
            st.dataframe(
                shifts.head(80),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("4️⃣ Meta güven + V17 ana karar")
        reliability = st.session_state.get("v160_reliability", {})
        with st.spinner("V17 yaşayan puanı hesaplanıyor..."):
            master, state, phase_weights, region_scores, elimination, block_birth2 = v17_master_table(
                df,
                target_time=v17_target_time,
                window=v17_window,
                state_window=v17_state_window,
                reliability=reliability,
            )

        m1, m2, m3 = st.columns(3)
        m1.metric("Aktif rejim", state.get("Faz", "-"))
        m2.metric("Rejim güveni", f"%{state.get('Güven', 0):.1f}")
        m3.metric("Hedef", f"#{int(df.iloc[-1].Cekilis_No)+1}")

        st.dataframe(
            master[
                [
                    "Sayı",
                    "V17 Yaşayan Puan",
                    "Rol",
                    "Eleme Durumu",
                    "Bölge",
                    "Bölge Puanı",
                    "Blok Doğum",
                    "Küme Tamamlama",
                    "Taşıma",
                    "Yerine",
                    "Dönüş",
                    "Benzer",
                    "Yorgunluk",
                ]
            ].head(45),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("5️⃣ Komşuluk / küme tamamlama")
        neighbors = neighborhood_completion_v17(
            df,
            master,
            lookback=v17_window,
        )
        if not neighbors.empty:
            st.dataframe(
                neighbors.head(50),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("6️⃣ Beş yaşayan senaryo kuponu")
        q1, q2 = st.columns(2)
        with q1:
            v17_size = st.selectbox(
                "Kupon büyüklüğü",
                [4, 5, 6, 7, 8, 10],
                index=3,
                key="v170_coupon_size",
            )
        with q2:
            v17_count = st.slider(
                "Kupon sayısı",
                1,
                5,
                5,
                key="v170_coupon_count",
            )

        if st.button(
            "🧠 V17 YAŞAYAN KUPONLARI ÜRET",
            type="primary",
            key="v170_generate",
        ):
            latest_set = set(int(df.iloc[-1][c]) for c in NUM_COLS)
            items = generate_v17_coupons(
                master,
                latest_set,
                skeleton,
                size=v17_size,
                count=v17_count,
            )
            st.session_state["v170_items"] = items
            st.session_state["v170_start_draw"] = int(df.iloc[-1].Cekilis_No) + 1

            for idx, item in enumerate(items, start=1):
                st.success(
                    f"V17 Kupon {idx} — {item['Senaryo']}: "
                    + " - ".join(map(str, item["Kupon"]))
                )

                expl = explain_v16_coupon(item["Kupon"], master.rename(
                    columns={"V17 Yaşayan Puan": "V16 Ana Puan"}
                ))
                st.dataframe(
                    expl,
                    use_container_width=True,
                    hide_index=True,
                )

            settings, settings_error = github_settings()
            if not settings_error and items:
                if st.button(
                    "💾 V17 kuponlarını kalıcı arşive kaydet",
                    key="v170_save_archive",
                ):
                    for idx, item in enumerate(items, start=1):
                        append_coupons_to_archive(
                            settings,
                            [item["Kupon"]],
                            f"V17 {item['Senaryo']}",
                            st.session_state["v170_start_draw"],
                        )
                    st.success("V17 kuponları kuponlar.csv arşivine kaydedildi.")

        st.subheader("7️⃣ Sonuç geldikçe otomatik değerlendirme")
        saved_items = st.session_state.get("v170_items", [])
        saved_start = st.session_state.get("v170_start_draw")

        if saved_items and saved_start:
            evaluated = evaluate_v17_saved_coupons(
                df,
                saved_items,
                saved_start,
            )
            if evaluated.empty:
                st.info(
                    f"#{saved_start} ve sonrası ilk sonuç bekleniyor."
                )
            else:
                st.dataframe(
                    evaluated.sort_values(
                        ["Cekilis", "Senaryo"],
                        ascending=[False, True],
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                settings, settings_error = github_settings()
                if not settings_error:
                    if st.button(
                        "🧠 Bu sonuçları kalıcı motor hafızasına yaz",
                        key="v170_save_memory",
                    ):
                        old_memory = load_motor_memory_v17(settings)
                        combined = pd.concat(
                            [old_memory, evaluated.astype(str)],
                            ignore_index=True,
                        ).drop_duplicates(
                            subset=["Cekilis", "Senaryo", "Kupon"],
                            keep="last",
                        )
                        save_motor_memory_v17(settings, combined)
                        st.success("motor_hafiza.csv güncellendi.")

        st.subheader("8️⃣ Kalıcı motor karnesi")
        settings, settings_error = github_settings()
        if not settings_error:
            try:
                memory = load_motor_memory_v17(settings)
                scorecard = v17_memory_scorecard(memory)
                if scorecard.empty:
                    st.info("Henüz kalıcı V17 test hafızası yok.")
                else:
                    st.dataframe(
                        scorecard,
                        use_container_width=True,
                        hide_index=True,
                    )
            except Exception as exc:
                st.caption(f"Motor hafızası okunamadı: {exc}")

        st.info(
            "V17'nin amacı tek bir 'sıcak sayı' formülüne güvenmek değil; "
            "çekiliş iskeleti, rejim, blok doğumu, blok kayması, komşuluk, "
            "küme tamamlama, taşıma/yenilenme ve gerçek sonuç hafızasını "
            "tek yaşayan karar sisteminde birleştirmektir."
        )


elif page == "🫁 Living Engine V18":
    st.header("🫁 Living Engine V18 — Nefes Alan Motor")
    st.caption(
        "V17/V18/V18.4 özellikleri korunur. V18.5; blok konumu, alternatif blok bölgesi, ortak çekirdek freni ve "
        "büyüme-kırılma, çoklu blok rejimi, bölge tahmini ve blok takip cezasını "
        "yaşayan öğrenme döngüsüne ekler."
    )

    if len(df) < 100:
        st.info("V18 için 100+ çekiliş önerilir.")
    else:
        calendar = draw_calendar_status_v18(df)

        st.subheader("0️⃣ Merkezi takvim")
        a, b = st.columns(2)
        with a:
            st.write("**Son gerçek çekiliş**")
            st.write(
                f"#{calendar.get('Son Çekiliş')} — "
                f"{calendar.get('Son Tarih')} "
                f"{calendar.get('Son Saat')}"
            )
        with b:
            st.write("**Beklenen sonraki çekiliş**")
            st.write(
                f"#{calendar.get('Sonraki Çekiliş')} — "
                f"{calendar.get('Sonraki Tarih')} "
                f"{calendar.get('Sonraki Saat')}"
            )

        c1, c2, c3 = st.columns(3)
        with c1:
            v18_window = st.selectbox(
                "Analiz geçmişi",
                [200, 300, 500, len(df)],
                index=min(2, 3),
                key="v180_window",
            )
        with c2:
            v18_state_window = st.selectbox(
                "Karakter penceresi",
                [4, 6, 8, 12],
                index=1,
                key="v180_state_window",
            )
        with c3:
            v18_target_time = st.text_input(
                "Hedef saat",
                value=calendar.get("Sonraki Saat", "07:02"),
                key="v180_target_time",
            )

        st.subheader("1️⃣ Çekiliş iskeleti")
        skeleton, skeleton_samples, region_forecast = skeleton_forecast(
            df,
            state_window=v18_state_window,
            search_window=v18_window,
            top_matches=25,
        )

        if skeleton:
            s1, s2, s3, s4 = st.columns(4)
            s1.metric(
                "Beklenen taşıma",
                f"{skeleton.get('Taşıma', 0):.2f}",
            )
            s2.metric(
                "Beklenen yeni",
                f"{skeleton.get('Yeni', 0):.2f}",
            )
            s3.metric(
                "2'li blok",
                f"{skeleton.get('2liBlok', 0):.2f}",
            )
            s4.metric(
                "Maks blok",
                f"{skeleton.get('MaksBlok', 0):.2f}",
            )

            st.write(
                f"**Aktif bölgeler:** "
                f"{skeleton.get('Aktif Bölge 1', '-')} / "
                f"{skeleton.get('Aktif Bölge 2', '-')}"
            )

        st.subheader("2️⃣ Yaşayan temel")
        settings, settings_error = github_settings()
        memory = pd.DataFrame()

        if not settings_error:
            try:
                memory = load_motor_memory_v17(settings)
            except Exception:
                memory = pd.DataFrame()

        adaptive = adaptive_weights_from_memory_v18(memory)

        master17, state, phase_weights, region_scores, elimination, block_birth = v17_master_table(
            df,
            target_time=v18_target_time,
            window=v18_window,
            state_window=v18_state_window,
            reliability=st.session_state.get(
                "v160_reliability",
                {},
            ),
        )

        master18 = v18_living_score_table(
            master17,
            adaptive,
        )

        confidence = v18_confidence_panel(
            state,
            skeleton,
            block_birth,
            memory,
        )

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Güven": name,
                        "Değer %": value,
                    }
                    for name, value in confidence.items()
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("3️⃣ Blok doğumu")
        if not block_birth.empty:
            st.dataframe(
                block_birth[
                    [
                        "Blok",
                        "Uzunluk",
                        "Blok Doğum Puanı",
                        "Mevcut bloktan geçiş",
                        "Sağ/Sol kayma",
                        "Saat desteği",
                        "Benzer durum",
                    ]
                ].head(30),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("3️⃣-B Blok Sinyal + Konum Motoru V18.5.1")
        block_forecast184, block_region184, block_matches184 = block_pressure_engine_v184(
            df,
            lookback=v18_window,
            state_window=min(6, v18_state_window),
            target_time=v18_target_time,
            top_matches=45,
        )

        if block_forecast184:
            bp1, bp2, bp3, bp4, bp5 = st.columns(5)
            bp1.metric("🔥 Blok Basıncı", f"{block_forecast184.get('Blok Basıncı',0):.1f}/100")
            bp2.metric("3'lü+", f"%{block_forecast184.get('3lü Olasılık %',0):.1f}")
            bp3.metric("4'lü+", f"%{block_forecast184.get('4lü Olasılık %',0):.1f}")
            bp4.metric("5'li+", f"%{block_forecast184.get('5lü Olasılık %',0):.1f}")
            bp5.metric("Beklenen blok", f"{block_forecast184.get('Blok Adedi',0):.2f}")
            st.write(
                f"**Basınç seviyesi:** {block_forecast184.get('Basınç Seviyesi','-')}  |  "
                f"**Beklenen maksimum blok:** {block_forecast184.get('Maks Blok',0):.2f}  |  "
                f"**Beklenen komşu çifti:** {block_forecast184.get('Komşu Çifti',0):.2f}"
            )

        if not block_region184.empty:
            st.write("**V18.4 temel blok bölge tahmini**")
            st.dataframe(block_region184, use_container_width=True, hide_index=True)

        block_location185, block_location_info185 = block_location_engine_v185(
            df,
            block_birth,
            block_region184,
            lookback=v18_window,
        )
        block_birth185 = block_candidate_location_filter_v185(
            block_birth,
            block_location185,
        )

        if not block_location185.empty:
            st.write("**📍 V18.5 Blok Konum Motoru**")
            bl1, bl2, bl3 = st.columns(3)
            bl1.metric(
                "Ana blok bölgesi",
                block_location_info185.get("Ana Bölge","-"),
                f"{block_location_info185.get('Ana Puan',0):.1f}/100",
            )
            bl2.metric(
                "Alternatif bölge",
                block_location_info185.get("Alternatif Bölge","-"),
                f"{block_location_info185.get('Alternatif Puan',0):.1f}/100",
            )
            bl3.metric(
                "Önceki baskın bölge",
                block_location_info185.get("Önceki Baskın Bölge","-"),
            )
            st.dataframe(
                block_location185,
                use_container_width=True,
                hide_index=True,
            )
            with st.expander("Konuma göre yeniden sıralanan blok adayları"):
                show_cols = [
                    c for c in [
                        "Blok","Uzunluk","Blok Doğum Puanı","Konum Puanı",
                        "V18.5 Blok Puanı","Mevcut bloktan geçiş","Sağ/Sol kayma",
                        "Saat desteği","Benzer durum"
                    ] if c in block_birth185.columns
                ]
                st.dataframe(
                    block_birth185[show_cols].head(40),
                    use_container_width=True,
                    hide_index=True,
                )

        growth184 = block_growth_break_table_v184(df, lookback=v18_window)
        lifecycle1854 = block_lifecycle_number_scores_v1854(df, lookback=v18_window)
        if not growth184.empty:
            st.write("**Mevcut blokların büyüme / kırılma / kayma davranışı**")
            st.dataframe(growth184, use_container_width=True, hide_index=True)

        with st.expander("Benzer geçmiş blok durumları"):
            if not block_matches184.empty:
                st.dataframe(block_matches184.head(30), use_container_width=True, hide_index=True)

        if st.button("🧪 BLOK BASINCI BACKTEST", key="v184_block_backtest"):
            with st.spinner("Blok basıncı geleceği görmeden test ediliyor..."):
                bt_detail184, bt_summary184 = block_pressure_backtest_v184(
                    df,
                    test_count=min(100, max(30, len(df)//10)),
                    lookback=min(v18_window, 350),
                    state_window=min(6, v18_state_window),
                )
            if bt_summary184.empty:
                st.info("Backtest için yeterli veri yok.")
            else:
                st.dataframe(bt_summary184, use_container_width=True, hide_index=True)
                with st.expander("Backtest ayrıntısı"):
                    st.dataframe(bt_detail184, use_container_width=True, hide_index=True)

        master18 = decorate_master_v184(
            df,
            master18,
            block_birth,
            block_region184,
            lookback=v18_window,
        )
        master18 = decorate_master_v185(
            master18,
            block_location185 if 'block_location185' in locals() else pd.DataFrame(),
            lifecycle1854 if 'lifecycle1854' in locals() else pd.DataFrame(),
        )
        master18 = decorate_master_v1855(df, master18)
        master18, regime1856 = candidate_quality_v1856(
            df,
            master18,
            target_time=str(calendar.get("Sonraki Saat")),
        )

        st.subheader("4️⃣ V18.5.8 Nefes Puanı")
        st.dataframe(
            master18[
                [
                    "Sayı",
                    "V18.5.6 Nefes Puanı",
                    "Aday Kalitesi 56",
                    "Taşıma Kimlik",
                    "Seri Devam %",
                    "Blok Mikro 56",
                    "V18.5.5 Nefes Puanı",
                    "V18.5 Nefes Puanı",
                    "V18.4 Nefes Puanı",
                    "V18 Nefes Puanı",
                    "Blok Zekâsı",
                    "Blok Konum",
                    "Blok Yaşam",
                    "Blok Kırılma Riski",
                    "Blok Kayma Varyantı",
                    "Ortak Çekirdek Güveni",
                    "Bölge Yorgunluğu 55",
                    "Bölge Geri Dönüş 55",
                    "Blok Takip Cezası",
                    "Rol",
                    "Eleme Durumu",
                    "Bölge",
                    "Bölge Puanı",
                    "Blok Doğum",
                    "Küme Tamamlama",
                    "Taşıma",
                    "Yerine",
                    "Dönüş",
                    "Benzer",
                    "Yorgunluk",
                ]
            ].head(45),
            use_container_width=True,
            hide_index=True,
        )

        st.write("**🧩 V18.5.8 Blok Rejim / Mikro-Konum Kararı**")
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("Uzun blok", f"{float(regime1856.get('Uzun Blok %',0)):.1f}%")
        rc2.metric("Çoklu küçük", f"{float(regime1856.get('Çoklu Küçük %',0)):.1f}%")
        rc3.metric("Seyrek/karışık", f"{float(regime1856.get('Seyrek/Karışık %',0)):.1f}%")
        rc4.metric("Benzer olay", int(regime1856.get("Benzer Olay",0)))
        st.caption(
            "Önerilen blok rejimi: "
            + str(regime1856.get("Önerilen Rejim","Karışık"))
            + " — blok oluşumu, uzunluk ve mikro-konum artık ayrı değerlendiriliyor."
        )

        st.write("**🔁 V18.5.8 Elden Ele Taşıma Kimliği**")
        # HF3: Panel artık yardımcı isimlere bağımlı değil.
        # Uygulamanın global NUM_COLS sabiti + mevcut df/master18 kullanılır.
        # Ayrıca panelde beklenmeyen bir görüntüleme hatası olursa ana motor çökmez.
        try:
            _latest_set562 = set()
            if df is not None and not df.empty:
                _last_row562 = df.iloc[-1]
                _latest_set562 = {
                    int(_last_row562[c])
                    for c in NUM_COLS
                    if c in df.columns and pd.notna(_last_row562[c])
                }

            _carry562 = carry_continue_break_v18562(master18, _latest_set562)
            _carry562 = _carry562[
                _carry562["Sayı"].astype(int).isin(_latest_set562)
            ].sort_values(
                ["Devam Puanı 562", "Taşıma Kimlik"],
                ascending=[False, False],
            )

            _dev = _carry562[
                _carry562["Taşıma Kararı 562"] == "DEVAM"
            ]["Sayı"].astype(int).tolist()
            _bel = _carry562[
                _carry562["Taşıma Kararı 562"] == "BELİRSİZ"
            ]["Sayı"].astype(int).tolist()
            _kir = _carry562[
                _carry562["Taşıma Kararı 562"] == "KIRILMA"
            ]["Sayı"].astype(int).tolist()

            c1, c2, c3 = st.columns(3)
            c1.metric("DEVAM adayı", len(_dev))
            c2.metric("BELİRSİZ", len(_bel))
            c3.metric("KIRILMA adayı", len(_kir))
            st.caption(
                "DEVAM: "
                + (" - ".join(map(str, _dev[:10])) if _dev else "yok")
            )
        except Exception:
            st.warning(
                "Taşıma Kimliği paneli geçici olarak gösterilemedi; "
                "V18.5.6.2 taşıma ve kupon motorları çalışmaya devam ediyor."
            )

        st.caption(
            "Çoklu Küçük rejimde kuponlar tek 10'luk bölgeye en fazla 3 sayı "
            "yığabilir; güçlü 2–3 mikro-bölge temsil edilir."
        )

        st.write("**🌙 V18.5.8 Dinlenmiş Dönüş Motoru**")
        st.caption("Dinlenme sınıfları: 1–2 / 3–5 / 6–10 / 10+ el. MASTER kolon, geçmişte aynı dinlenme sınıfından gerçekten dönüş yapan sayıları ayrı puanlar.")
        st.subheader("5️⃣ Öğrenen motor katsayıları — CANLI")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Motor": key,
                        "Öğrenen Katsayı": value,
                    }
                    for key, value in adaptive.items()
                ]
            ).sort_values(
                "Öğrenen Katsayı",
                ascending=False,
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("6️⃣ V18 yaşayan kuponlar")
        st.caption("🏆 V18.5.8 OYNA — MASTER 7: uzman aile bağımsızlığı + korelasyon/sürü freni + bağımsız keşif koltuğu + saat/faz/karakter kalibrasyonu + taşıma + dinlenmiş dönüş + blok + bölge/mikro + eşlikçi sinyallerini tek nihai kolonda birleştirir.")
        st.caption("V18.5.6.5: taşıma kimliği gerçek 'Taşıma' beklentisiyle çalışır; son çekiliş blokları paket halinde devam/kayma/büyüme için test edilir; 6/6 ortak sayı yalnız olağanüstü güvenle korunur.")
        st.caption("V18.5.6.4: Güçlü çekirdek sayı tek bırakılmaz; geçmişte onunla özel bağ gösteren eşlikçiler senaryolara dağıtılır. Genel sıcaklık yerine koşullu olasılık + lift kullanılır; aynı kuponların tekrarı frenlenir.")
        st.caption("V18.5.6.5: önceki motorlar korunur + düzeltilmiş taşıma kimliği/desen kalibrasyonu + dinamik ortak çekirdek + blok→eşlikçi/taşıma paketi + ana/alternatif bölge mikro-konum kalibrasyonu.")
        q1, q2 = st.columns(2)
        with q1:
            v18_size = st.selectbox(
                "Kupon büyüklüğü",
                [4, 5, 6, 7, 8, 10],
                index=3,
                key="v180_coupon_size",
            )
        with q2:
            v18_count = st.slider(
                "Kupon sayısı",
                1,
                5,
                5,
                key="v180_coupon_count",
            )

        if st.button(
            "🫁 V18 YAŞAYAN KUPONLARI ÜRET",
            type="primary",
            key="v180_generate",
        ):
            latest_set = set(
                int(df.iloc[-1][c])
                for c in NUM_COLS
            )

            items = generate_v1856_coupons(
                master18,
                latest_set,
                skeleton,
                block_forecast184,
                block_birth185 if 'block_birth185' in locals() else block_birth,
                regime1856,
                size=v18_size,
                count=v18_count,
                df_hist=df,
                block_loc_info=block_location_info185 if 'block_location_info185' in locals() else None,
                character_window=v18_state_window,
                target_time=v18_target_time,
            )

            st.session_state["v180_items"] = items
            st.session_state["v180_start_draw"] = int(calendar.get("Sonraki Çekiliş"))
            st.session_state["v180_locked_target_draw"] = None
            st.session_state["v180_locked_target_date"] = str(calendar.get("Sonraki Tarih"))
            st.session_state["v180_locked_target_time"] = str(calendar.get("Sonraki Saat"))
            st.session_state["v180_skeleton"] = skeleton
            st.session_state["v180_region_forecast"] = region_forecast
            st.session_state["v180_block_birth"] = block_birth
            st.session_state["v184_block_forecast"] = block_forecast184
            st.session_state["v184_block_region"] = block_region184
            st.session_state["v180_state"] = state

            # V18.5.3: Kuponları sonuç gelmeden kalıcı olarak sakla.
            if not settings_error:
                try:
                    save_v18_pending_v1853(
                        settings,
                        items,
                        st.session_state["v180_locked_target_date"],
                        st.session_state["v180_locked_target_time"],
                        st.session_state.get("v180_start_draw"),
                    )
                except Exception as exc:
                    st.caption(f"Bekleyen kupon hafızası yazılamadı: {exc}")

            st.warning(
                "🎯 BU KUPONLAR SADECE ŞU TARİH/SAAT İÇİNDİR: "
                + target_badge_v181(
                    st.session_state["v180_locked_target_draw"],
                    st.session_state["v180_locked_target_date"],
                    st.session_state["v180_locked_target_time"],
                )
            )

            for idx, item in enumerate(
                items,
                start=1,
            ):
                st.success(
                    f"V18 Kupon {idx} — "
                    f"{item['Senaryo']}: "
                    + " - ".join(
                        map(str, item["Kupon"])
                    )
                )

            _master_item = next((x for x in items if str(x.get("Senaryo","")).startswith("🏆 OYNA")), None)
            if _master_item:
                st.markdown("### 🏆 OYNA — MASTER 7 Açıklama")
                _exp = _master_item.get("Master Açıklama 567")
                if isinstance(_exp, pd.DataFrame) and not _exp.empty:
                    _cols = [c for c in [
                        "Sayı","Master567","Bağımsız Motor 567","Seçim Nedeni 567",
                        "Uzman Aile Desteği 58","Oy_UzmanAğırlık 58","Uzman Korelasyon 58",
                        "Keşif Puanı 58","Oy_Taşıma","Oy_Dinlenmiş","Oy_Blok","Oy_Bölge","Oy_Eşlikçi","Oy_BlokPaket"
                    ] if c in _exp.columns]
                    st.dataframe(_exp[_cols], use_container_width=True, hide_index=True)
                _form = _master_item.get("Motor Form 567",{})
                if _form:
                    st.caption("Motor formu: " + " | ".join(f"{k} {v:.2f}" for k,v in _form.items()))
                st.caption(f"Rejim kırılma sigortası: {_master_item.get('Rejim Sigorta 567',0.0):.2f}")

        st.subheader("7️⃣ Sonuç geldikçe öğren")
        items = st.session_state.get(
            "v180_items",
            [],
        )
        start_draw = st.session_state.get(
            "v180_start_draw",
        )

        # Streamlit/GitHub yeniden başlatmasında session_state silinse bile
        # sonuç bekleyen kuponları geri getir.
        if (not items or not start_draw) and not settings_error:
            try:
                pending_v1853 = load_v18_pending_v1853(settings)
                pending_items = pending_v1853.get("items", [])
                if pending_items:
                    items = pending_items
                    start_draw = pending_v1853.get("target_draw")
                    st.session_state["v180_items"] = items
                    st.session_state["v180_start_draw"] = start_draw
                    st.session_state["v180_locked_target_date"] = pending_v1853.get("target_date", "")
                    st.session_state["v180_locked_target_time"] = pending_v1853.get("target_time", "")
            except Exception:
                pass

        if items and start_draw:
            target_draw = st.session_state.get(
                "v180_target_draw",
                start_draw,
            )
            target_date = st.session_state.get(
                "v180_locked_target_date",
                str(calendar.get("Sonraki Tarih")),
            )
            target_time = st.session_state.get(
                "v180_locked_target_time",
                str(calendar.get("Sonraki Saat")),
            )
            evaluated = evaluate_exact_target_draw_v181(
                df,
                items,
                target_draw_no=None,
                target_date=target_date,
                target_time=target_time,
            )

            if evaluated.empty:
                target_draw = st.session_state.get("v180_locked_target_draw", start_draw)
                target_date = st.session_state.get("v180_locked_target_date", "")
                target_time = st.session_state.get("v180_locked_target_time", "")
                st.info(
                    "Bu kuponlar yalnızca hedef tarih/saat olan "
                    + target_badge_v181(target_draw, target_date, target_time)
                    + " sonucu için bekliyor."
                )
            else:
                st.dataframe(
                    evaluated.sort_values(
                        ["Cekilis", "Senaryo"],
                        ascending=[False, True],
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                if not settings_error:
                    try:
                        old_memory = load_motor_memory_v17(settings)
                        enrich = evaluated.copy()

                        error_report = forecast_error_report_v18(
                            df,
                            st.session_state.get("v180_skeleton", {}),
                            st.session_state.get("v180_block_birth", pd.DataFrame()),
                            st.session_state.get("v180_region_forecast", pd.DataFrame()),
                        )

                        enrich["Faz"] = st.session_state.get("v180_state", {}).get("Faz", "")
                        enrich["Iskelet_Hata"] = error_report.get("Taşıma_Hata", "")
                        enrich["Blok_Hata"] = error_report.get("Blok_Top10_Isabet", "")
                        enrich["Bolge_Hata"] = error_report.get("Bolge_Eslesti", "")

                        before_count = len(old_memory)
                        combined = pd.concat(
                            [old_memory, enrich.astype(str)],
                            ignore_index=True,
                        ).drop_duplicates(
                            subset=["Cekilis", "Senaryo", "Kupon"],
                            keep="last",
                        )

                        if len(combined) > before_count:
                            save_motor_memory_v17(settings, combined)
                            clear_v18_pending_v1853(settings)
                            st.success(
                                "🧠 V18.5.6.2 sonucu otomatik öğrendi ve GitHub motor hafızasına yazdı."
                            )
                            st.info(
                                "Öğrenen katsayılar bir sonraki yenilemede yeni hafızaya göre değişecektir."
                            )
                        else:
                            st.caption("Bu sonuç daha önce öğrenilmiş; tekrar yazılmadı.")
                    except Exception as exc:
                        st.warning(f"Otomatik öğrenme hafızası yazılamadı: {exc}")

        st.subheader("8️⃣ Neden yanıldım?")
        scorecard = (
            v17_memory_scorecard(memory)
            if memory is not None
            else pd.DataFrame()
        )

        error_report = forecast_error_report_v18(
            df,
            st.session_state.get(
                "v180_skeleton",
                {},
            ),
            st.session_state.get(
                "v180_block_birth",
                pd.DataFrame(),
            ),
            st.session_state.get(
                "v180_region_forecast",
                pd.DataFrame(),
            ),
        )

        st.write(
            v18_postmortem_text(
                error_report,
                scorecard,
            )
        )

        if not scorecard.empty:
            st.subheader("9️⃣ Motor karnesi")
            st.dataframe(
                scorecard,
                use_container_width=True,
                hide_index=True,
            )

        st.info(
            "V18 döngüsü: Algıla → Fazı tanı → İskeleti tahmin et → "
            "Blok/bölge/kümeyi hesapla → Kupon üret → Gerçek sonucu gör → "
            "Hatasını ölç → Hafızaya yaz → Motor ağırlıklarını değiştir. "
            "V18.5.6, V18.5.5 ve önceki öğrenme/hafıza yapısını korur; taşıma miktarı tahmini değiştirilmeden taşıma kimliği, seri devam/kırılma, aday kalitesi, blok rejimi/mikro-konumu ve Birleşik Güç kuponu kontrollü son katman olarak eklenmiştir."
        )

elif page == "📊 Bant/Saat":
    bands = band_table(adf)
    st.subheader("Bant yoğunluğu")
    st.dataframe(
        bands.sort_values("Çekiliş", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
    st.bar_chart(bands[BAND_NAMES].mean())
    st.subheader("Saat dilimi davranışı")
    st.dataframe(
        period_summary(adf),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Son 5/10/20/50/100 karşılaştırması")
    st.dataframe(
        recent_window_comparison(df),
        use_container_width=True,
        hide_index=True,
    )

elif page == "🧭 Benzerlik":
    default_target = " ".join(str(int(latest[c])) for c in NUM_COLS)
    target_text = st.text_area(
        "20 hedef sayı",
        value=default_target,
        height=100,
        key="v102_similarity",
    )
    target = sorted(
        set(
            int(x)
            for x in re.findall(r"\d+", target_text)
            if 1 <= int(x) <= 80
        )
    )
    if len(target) == 20:
        st.dataframe(
            similar_draws(df.iloc[:-1], target),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(f"20 farklı sayı gerekli. Şu an {len(target)} sayı var.")

elif page == "🧬 Değişim":
    drift, drift_msg = drift_detector(df)
    st.info(drift_msg)
    if not drift.empty:
        st.dataframe(
            drift.head(40),
            use_container_width=True,
            hide_index=True,
        )
    st.info(rule_based_interpretation(df, window))

elif page == "🌙 Kapanış":
    close_freq, close_combos = closing_summary(df)
    if close_freq.empty:
        st.info("Kapanış döneminde kayıt bulunamadı.")
    else:
        st.subheader("Kapanış sıcak sayıları")
        st.dataframe(
            close_freq.head(30),
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Kapanışta en sık birlikte çıkan ikililer")
        st.dataframe(
            close_combos,
            use_container_width=True,
            hide_index=True,
        )

elif page == "🎯 Süper Kupon":
    st.subheader("Bütün analizleri birleştiren Süper Akıllı Kupon")
    q1, q2, q3 = st.columns(3)
    with q1:
        smart_size = st.selectbox(
            "Kolon büyüklüğü",
            [3, 4, 5, 6, 7, 8, 10],
            index=4,
            key="v102_smart_size",
        )
    with q2:
        smart_count = st.slider(
            "Kolon sayısı", 1, 10, 4, key="v102_smart_count"
        )
    with q3:
        smart_time = st.text_input(
            "Hedef çekiliş saati",
            value=str(latest.Saat),
            key="v102_smart_time",
        )

    if st.button(
        "Süper kolonları üret",
        type="primary",
        key="v102_super_generate",
    ):
        score_df = intelligent_score_table(df, smart_time)
        for shift in range(smart_count):
            coupon = balanced_smart_coupon(
                score_df, smart_size, shift
            )
            st.success(
                f"Kolon {shift + 1}: "
                + " - ".join(map(str, coupon))
            )
            st.dataframe(
                explain_coupon(coupon, score_df),
                use_container_width=True,
                hide_index=True,
            )


elif page == "🔀 Geçiş Kuponu":
    st.header("🔀 Geçiş ve Yer Değiştirme Kuponu")
    st.info(
        "Son çekilişteki seçtiğin sayıların geçmişte bir sonraki elde "
        "hangi sayılara geçtiğini, hangilerinin tekrar ettiğini ve "
        "hangi adayların birlikte daha uyumlu olduğunu hesaplar."
    )

    last_numbers = sorted(int(latest[c]) for c in NUM_COLS)
    default_sources = " ".join(map(str, last_numbers))
    source_text = st.text_area(
        "Son çekilişten incelenecek sayılar",
        value=default_sources,
        height=90,
        help="Örnek: 54 63 80. Boş bırakma; 1–80 arasında sayılar yaz.",
        key="v103_transition_sources",
    )
    source_numbers = sorted(
        set(
            int(x)
            for x in re.findall(r"\d+", source_text)
            if 1 <= int(x) <= 80
        )
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        transition_window = st.selectbox(
            "Geçmiş pencere",
            [100, 200, 300, 500, len(df)],
            index=min(3, 4),
            key="v103_transition_window",
        )
    with c2:
        transition_size = st.selectbox(
            "Kupon büyüklüğü",
            [3, 4, 5, 6, 7, 8, 10],
            index=4,
            key="v103_transition_size",
        )
    with c3:
        transition_count = st.slider(
            "Kupon sayısı",
            1, 10, 4,
            key="v103_transition_count",
        )

    if not source_numbers:
        st.warning("En az bir kaynak sayı yaz.")
    else:
        with st.spinner("Geçiş davranışları hesaplanıyor..."):
            source_table, transition_candidates, pair_counts = (
                transition_statistics(
                    df,
                    source_numbers,
                    transition_window,
                )
            )

        st.subheader("Kaynak sayıların tekrar ve geçiş özeti")
        st.dataframe(
            source_table,
            use_container_width=True,
            hide_index=True,
        )

        repeat_candidates = transition_candidates[
            transition_candidates["Tür"] == "Tekrar adayı"
        ].head(20)
        replacement_candidates = transition_candidates[
            transition_candidates["Tür"] == "Yerine geçme adayı"
        ].head(30)

        left, right = st.columns(2)
        with left:
            st.subheader("🔁 Tekrar adayları")
            st.dataframe(
                repeat_candidates[
                    [
                        "Sayı",
                        "Geçiş Puanı",
                        "Geçiş oranı %",
                        "Lift",
                        "Kaynak desteği",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
        with right:
            st.subheader("🔄 Yerine geçme adayları")
            st.dataframe(
                replacement_candidates[
                    [
                        "Sayı",
                        "Geçiş Puanı",
                        "Geçiş oranı %",
                        "Lift",
                        "Kaynak desteği",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("İki çekilişlik geçiş zinciri")
        st.dataframe(
            transition_chain_table(
                df,
                source_numbers,
                transition_window,
            ),
            use_container_width=True,
            hide_index=True,
        )

        target_time = st.text_input(
            "Hedef çekiliş saati",
            value=str(latest.Saat),
            key="v104_transition_target_time",
        )

        st.divider()
        st.subheader("🧩 Son çekilişten 3 çekirdek + yoldaş kuponu")
        st.caption(
            "Son çekilişteki 20 sayıdan en güçlü 3 çekirdeği seçer; "
            "geçmişte bu çekirdeklerle birlikte gelen ve dinlenip "
            "dönüş zamanı yaklaşan sayıları yanlarına ekler."
        )

        core_window = st.selectbox(
            "Çekirdek analiz penceresi",
            [50, 100, 150, 300, 500],
            index=1,
            key="v120_core_window",
        )

        core, core_table = core_three_analysis(
            df,
            target_time,
            core_window,
        )
        companion_table = companion_candidates_for_core(
            df,
            core,
            target_time,
            max(100, core_window),
        )

        st.success(
            "Seçilen 3 çekirdek: "
            + " - ".join(map(str, core))
        )

        core_left, core_right = st.columns(2)
        with core_left:
            st.dataframe(
                core_table[
                    [
                        "Sayı",
                        "Çekirdek Puan",
                        "Tekrar oranı",
                        "Son çekiliş bağı",
                        "Dönüş uyumu",
                        "Genel güç",
                    ]
                ].head(12),
                use_container_width=True,
                hide_index=True,
            )

        with core_right:
            st.dataframe(
                companion_table[
                    [
                        "Sayı",
                        "Yoldaş Puan",
                        "Çekirdekle birlikte",
                        "Dönüş uyumu",
                        "Dinlenme",
                        "Son çekilişte vardı",
                    ]
                ].head(20),
                use_container_width=True,
                hide_index=True,
            )

        if st.button(
            "🧩 Çekirdek kuponunu üret",
            type="primary",
            key="v120_core_coupon_generate",
        ):
            core_coupon = build_core_companion_coupon(
                core,
                companion_table,
                transition_size,
            )
            st.session_state["v120_core_coupon"] = core_coupon
            st.success(
                "Çekirdek Kuponu: "
                + " - ".join(map(str, core_coupon))
            )
            st.dataframe(
                explain_core_coupon(
                    core_coupon,
                    core,
                    companion_table,
                ),
                use_container_width=True,
                hide_index=True,
            )

        with st.spinner("Bütün analizler ortak puanda birleştiriliyor..."):
            hybrid_candidates = hybrid_transition_table(
                df,
                transition_candidates,
                target_time,
            )

        st.subheader("🧠 Ortak Hibrit Puan")
        st.caption(
            "Geçiş, tekrar, genel güç, saat, birlikte gelme, dönüş ve "
            "blok analizleri tek puanda birleştirilmiştir."
        )
        st.dataframe(
            hybrid_candidates[
                [
                    "Sayı",
                    "Hibrit Puan",
                    "Tür",
                    "Geçiş Puanı",
                    "Genel Güç Puanı",
                    "Tekrar oranı",
                    "Saat oranı",
                    "Birlikte gelme",
                    "Dönüş uyumu",
                ]
            ].head(40),
            use_container_width=True,
            hide_index=True,
        )

        if st.button(
            "🎯 Tam donanımlı kuponları üret",
            type="primary",
            key="v104_transition_generate",
        ):
            generated_items = generate_unique_profile_coupons(
                hybrid_candidates,
                pair_counts,
                transition_size,
                transition_count,
            )

            if not generated_items:
                st.error("Kupon üretilemedi.")
            else:
                st.session_state["v104_generated_transition_coupons"] = generated_items

                for idx, item in enumerate(generated_items, start=1):
                    coupon = item["Kupon"]
                    st.success(
                        f"Kupon {idx} — {item['Profil']}: "
                        + " - ".join(map(str, coupon))
                    )
                    st.dataframe(
                        explain_hybrid_coupon(
                            coupon,
                            hybrid_candidates,
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                st.subheader("📊 Son 100 çekilişte sabit kupon performansı")
                st.dataframe(
                    coupon_recent_performance(
                        df,
                        generated_items,
                        last_n=100,
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                st.info(
                    "Kuponlar birbirinin aynısı olmayacak şekilde; dengeli, "
                    "tekrar ağırlıklı, yerine geçme ağırlıklı ve saat/sıcaklık "
                    "profilleriyle oluşturuldu."
                )

                st.session_state["v11_generated_start_draw"] = next_draw_number(df)

                settings, settings_error = github_settings()
                if settings_error:
                    st.warning(
                        "Kalıcı kupon takibi için GitHub Secrets bağlantısı gerekli."
                    )
                else:
                    if st.button(
                        "💾 Bu 4 kuponu arşive kaydet ve sonraki çekilişlerde izle",
                        key="v11_save_generated_coupons",
                    ):
                        saved_rows = []
                        start_draw = st.session_state["v11_generated_start_draw"]
                        for idx, item in enumerate(generated_items, start=1):
                            _, new_row = append_coupons_to_archive(
                                settings,
                                [item["Kupon"]],
                                f"V11 Geçiş {idx} - {item['Profil']}",
                                start_draw,
                            )
                            saved_rows.append(new_row)
                        st.success(
                            f"Kuponlar kaydedildi. Kontrol başlangıcı: {start_draw}"
                        )

        saved_generated = st.session_state.get(
            "v104_generated_transition_coupons", []
        )
        saved_start = st.session_state.get("v11_generated_start_draw")

        if saved_generated and saved_start:
            st.subheader("✅ Yeni çekiliş geldikçe otomatik sonuç kontrolü")
            live_result = generated_coupon_result_table(
                df,
                saved_generated,
                saved_start,
            )
            if live_result.empty:
                st.info(
                    f"Kuponlar {saved_start} numaralı çekilişten itibaren "
                    "kontrol edilecek. Henüz yeni sonuç yok."
                )
            else:
                st.dataframe(
                    live_result.sort_values(
                        ["Çekiliş", "Kupon"],
                        ascending=[False, True],
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                learned = profile_learning_summary(live_result)
                if not learned.empty:
                    st.subheader("🧠 Profil öğrenme tablosu")
                    st.dataframe(
                        learned,
                        use_container_width=True,
                        hide_index=True,
                    )
                    best_profile = learned.iloc[0]["Profil"]
                    st.success(
                        f"Şu ana kadarki gerçek sonuçlarda öne çıkan profil: "
                        f"{best_profile}"
                    )

        settings, settings_error = github_settings()
        if not settings_error:
            try:
                archive = load_coupon_archive(settings)
                archive_learning = archive_profile_learning(df, archive)
                if not archive_learning.empty:
                    st.subheader("📚 Kalıcı arşivden öğrenilen profil ağırlıkları")
                    st.dataframe(
                        archive_learning,
                        use_container_width=True,
                        hide_index=True,
                    )
            except Exception as exc:
                st.caption(f"Arşiv öğrenme özeti okunamadı: {exc}")

elif page == "🧪 Kupon Laboratuvarı":
    st.subheader("Kupon Laboratuvarı")
    lab_coupon_text = st.text_area(
        "Test edilecek kupon",
        placeholder="7 11 18 24 39 52 71",
        key="v102_lab_coupon",
    )
    if lab_coupon_text.strip():
        lab_coupon = sorted(
            set(
                int(x)
                for x in re.findall(r"\d+", lab_coupon_text)
                if 1 <= int(x) <= 80
            )
        )
        if not lab_coupon:
            st.error("Geçerli sayı bulunamadı.")
        else:
            test_df = historical_coupon_test(df, lab_coupon)
            distribution = hit_distribution(
                test_df, len(lab_coupon)
            )
            m1, m2, m3 = st.columns(3)
            m1.metric(
                "Ortalama isabet",
                f"{test_df['İsabet'].mean():.2f}",
            )
            m2.metric(
                "En yüksek isabet",
                int(test_df["İsabet"].max()),
            )
            m3.metric(
                "En iyi sonuç sayısı",
                int(
                    (
                        test_df["İsabet"]
                        == test_df["İsabet"].max()
                    ).sum()
                ),
            )
            st.dataframe(
                distribution,
                use_container_width=True,
                hide_index=True,
            )
            st.dataframe(
                test_df.sort_values(
                    ["İsabet", "Çekiliş"],
                    ascending=[False, False],
                ).head(100),
                use_container_width=True,
                hide_index=True,
            )
            score_df = intelligent_score_table(
                df, str(latest.Saat)
            )
            weakest, alternatives = weakest_coupon_replacement(
                lab_coupon, score_df
            )
            st.warning(
                f"En zayıf puanlı kupon sayısı: {weakest}. "
                f"Alternatif güçlü sayılar: "
                f"{' - '.join(map(str, alternatives))}"
            )

elif page == "💾 Kupon Arşivi":
    st.subheader("Kupon yapıştır, kalıcı kaydet ve isabetlerini izle")
    settings, settings_error = github_settings()

    if settings_error:
        st.warning(settings_error)
    else:
        coupon_text = st.text_area(
            "Kuponları yapıştır",
            height=180,
            placeholder="""7 11 18 24 39 52 71
3 9 22 31 44 58 69""",
            key="v102_coupon_archive_text",
        )
        c1, c2 = st.columns(2)
        with c1:
            label = st.text_input(
                "Etiket",
                value="Güncel kupon",
                key="v102_coupon_label",
            )
        with c2:
            start_draw = st.number_input(
                "Hangi çekilişten itibaren kontrol edilsin?",
                min_value=1,
                value=int(df["Cekilis_No"].max()) + 1,
                step=1,
                key="v102_coupon_start_draw",
            )
        pin = st.text_input(
            "Kalıcı kayıt PIN'i",
            type="password",
            key="v102_coupon_pin",
        )

        if st.button(
            "💾 Kuponları kalıcı kaydet",
            type="primary",
            key="v102_save_coupons",
        ):
            coupons = parse_coupon_lines(coupon_text)
            if not coupons:
                st.error("Geçerli kupon bulunamadı.")
            elif not settings["admin_pin"]:
                st.error("Secrets içinde admin_pin tanımlı değil.")
            elif pin != settings["admin_pin"]:
                st.error("PIN yanlış.")
            else:
                try:
                    _, added = append_coupons_to_archive(
                        settings,
                        coupons,
                        label,
                        int(start_draw),
                    )
                    st.success(
                        f"{len(added)} kupon kalıcı kaydedildi."
                    )
                    st.dataframe(
                        added,
                        use_container_width=True,
                        hide_index=True,
                    )
                except Exception as exc:
                    st.error(str(exc))

        st.divider()
        st.subheader("Kayıtlı kuponların isabet raporu")
        try:
            archive = load_coupon_archive(settings)
            if archive.empty:
                st.info("Henüz kayıtlı kupon yok.")
            else:
                summary_df, detail_map = coupon_performance_summary(
                    df, archive
                )
                st.dataframe(
                    summary_df,
                    use_container_width=True,
                    hide_index=True,
                )
                selected_id = st.selectbox(
                    "Detayını görmek istediğin kupon",
                    options=summary_df["Kupon_ID"].astype(str).tolist(),
                    key="v102_coupon_detail_id",
                )
                detail_df = detail_map.get(
                    str(selected_id), pd.DataFrame()
                )
                if detail_df.empty:
                    st.info(
                        "Bu kupondan sonra henüz test edilecek "
                        "çekiliş yok."
                    )
                else:
                    st.dataframe(
                        detail_df.sort_values(
                            ["İsabet", "Çekiliş"],
                            ascending=[False, False],
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
        except Exception as exc:
            st.error(str(exc))

elif page == "✅ Sonuç Kontrol":
    st.subheader("Kupon ile yeni çekiliş sonucunu karşılaştır")
    coupon_text = st.text_area(
        "Kupon sayıları",
        placeholder="7 11 18 24 39 52 71",
        key="v102_result_coupon",
    )
    result_text = st.text_area(
        "Çekiliş sonucu (20 sayı)",
        placeholder="1 7 11 14 18 ...",
        key="v102_result_draw",
    )
    if coupon_text.strip() and result_text.strip():
        coupon_vals, _, hits = coupon_check(
            coupon_text, result_text
        )
        st.write("Kupon:", " - ".join(map(str, coupon_vals)))
        st.write(
            "Tutan sayılar:",
            " - ".join(map(str, hits)) or "Yok",
        )
        st.metric(
            "İsabet", f"{len(hits)} / {len(coupon_vals)}"
        )

elif page == "➕ Yeni Çekiliş":
    st.header("➕ Yeni Çekiliş Ekle")
    st.info(
        "Tam çekiliş metnini veya yalnızca 20 sayıyı yapıştırabilirsin. "
        "Yalnızca sayıları yapıştırırsan çekiliş no, tarih ve saat "
        "aşağıdaki alanlardan alınır."
    )

    default_no, default_date, default_time = next_draw_defaults(df)
    field_col1, field_col2, field_col3 = st.columns(3)
    manual_no = field_col1.number_input(
        "Çekiliş no",
        min_value=1,
        value=int(default_no),
        step=1,
        key="v112_manual_draw_no",
    )
    manual_date = field_col2.text_input(
        "Tarih",
        value=default_date,
        placeholder="05.08.2026",
        key="v112_manual_date",
    )
    manual_time = field_col3.text_input(
        "Saat",
        value=default_time,
        placeholder="21:52",
        key="v112_manual_time",
    )

    raw = st.text_area(
        "Çekilişi veya yalnızca 20 sayıyı yapıştır",
        height=280,
        placeholder="""Tam format:
Çekiliş no: 47064
05.08.2026 - 21:52
3
6
7
9
13
20
25
30
34
41
46
47
59
62
64
65
68
69
72
76

VEYA yalnızca:
3 6 7 9 13 20 25 30 34 41 46 47 59 62 64 65 68 69 72 76""",
        key="v102_new_draw",
    )

    if raw.strip():
        # Önce tam WhatsApp/site blok biçimini dene.
        row = parse_draw_block(raw)

        # Tek satırlık standart biçimi de kabul et.
        if not row:
            possible_lines = [line.strip() for line in raw.splitlines() if line.strip()]
            if len(possible_lines) == 1:
                row = parse_standard_line(possible_lines[0])

        # Metadata yoksa yalnızca 20 sayıyı manuel alanlarla tamamla.
        if not row:
            only_numbers = extract_exact_twenty_numbers(raw)
            date_ok = bool(re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", manual_date.strip()))
            time_ok = bool(re.fullmatch(r"\d{2}:\d{2}", manual_time.strip()))

            if only_numbers and date_ok and time_ok:
                row = [
                    int(manual_no),
                    manual_date.strip(),
                    manual_time.strip(),
                    *only_numbers,
                ]
                st.info(
                    "Yalnızca 20 sayı algılandı; çekiliş no, tarih ve saat "
                    "üstteki alanlardan tamamlandı."
                )

        if not row:
            found_nums = [
                int(x) for x in re.findall(
                    r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",
                    raw,
                )
            ]
            st.error(
                "Çekiliş okunamadı. Tam metni veya 20 farklı sayıyı gir. "
                f"Algılanan uygun sayı adedi: {len(found_nums)}."
            )
        elif row[0] in set(df.Cekilis_No.astype(int)):
            st.warning(f"Çekiliş #{row[0]} zaten veri havuzunda mevcut.")
        else:
            raw_draw_no = row[0]
            row[0] = normalize_draw_number(row[0], row[1])
            if row[0] != raw_draw_no:
                st.warning(
                    f"Çekiliş numarası otomatik düzeltildi: "
                    f"{raw_draw_no} → {row[0]}"
                )

            # Tarih/saatin gerçekten geçerli olduğunu kontrol et.
            try:
                datetime.strptime(
                    f"{row[1]} {row[2]}",
                    "%d.%m.%Y %H:%M",
                )
            except ValueError:
                st.error("Tarih veya saat geçersiz. Örnek: 05.08.2026 ve 21:52")
                row = None

            if row:
                candidate_df = merge_data(
                    df, pd.DataFrame([row], columns=COLS)
                )
                if len(candidate_df) != len(df) + 1:
                    st.error(
                        "Kayıt havuza eklenemedi. Çekiliş numarası veya sayılar "
                        "başka bir kayıtla çakışıyor olabilir."
                    )
                else:
                    st.success(
                        f"Çekiliş #{row[0]} doğrulandı. "
                        f"{row[1]} {row[2]} | Havuz {len(df)} → {len(candidate_df)}"
                    )
                    st.write(
                        "Okunan sayılar: "
                        + " - ".join(map(str, row[3:]))
                    )
                    st.download_button(
                        "Yedek veri.txt indir",
                        data=to_text(candidate_df).encode("utf-8"),
                        file_name="veri.txt",
                        mime="text/plain",
                        key="v102_new_draw_backup",
                    )
                    persistent_save_panel(
                        candidate_df, "v102_single_draw"
                    )

elif page == "⬇️ Dışa Aktar":
    try:
        pdf_score_df = intelligent_score_table(
            df, str(df.iloc[-1].Saat)
        )
    except Exception:
        pdf_score_df = pd.DataFrame()

    st.download_button(
        "PDF analiz raporu indir",
        data=create_pdf_report(df, pdf_score_df),
        file_name="hizli_on_v102_analiz_raporu.pdf",
        mime="application/pdf",
        type="primary",
    )
    st.download_button(
        "Güncel veri.txt indir",
        data=to_text(df).encode("utf-8"),
        file_name="veri.txt",
        mime="text/plain",
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
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

st.caption(
    "V18.3 V18.2 özelliklerini korur; hedefi tarih+saat ile kilitler, çekiliş numarasını tahmin etmez ve gerçek sonuç geldiğinde gerçek çekiliş numarasını kullanır. "
    "Bu nedenle boş sekme ve sürekli yüklenme sorunu giderilmiştir. "
    "İstatistikler kesin sonuç veya kazanç garantisi vermez."
)
