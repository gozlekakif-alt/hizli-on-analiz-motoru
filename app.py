import base64
from datetime import datetime, timedelta, timedelta
import io
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
    page_title="Hızlı On Ultimate Analiz Motoru V12.0",
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

def next_draw_defaults(df):
    """Son kayda göre bir sonraki çekiliş no ve +5 dakikalık tarih/saati üretir."""
    if df is None or df.empty:
        return 1, datetime.now().strftime("%d.%m.%Y"), datetime.now().strftime("%H:%M")

    latest = df.sort_values("Cekilis_No").iloc[-1]
    draw_no = int(latest.Cekilis_No) + 1
    try:
        last_dt = datetime.strptime(
            f"{latest.Tarih} {latest.Saat}",
            "%d.%m.%Y %H:%M",
        )
        next_dt = last_dt + timedelta(minutes=5)
        return draw_no, next_dt.strftime("%d.%m.%Y"), next_dt.strftime("%H:%M")
    except Exception:
        return draw_no, str(latest.Tarih), str(latest.Saat)

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
    settings, settings_error = github_settings()

    if settings_error:
        st.warning(settings_error)
        return

    st.success(
        "GitHub kalıcı kayıt bağlantısı hazır. "
        "Kaydet düğmesi ana veri.txt dosyasını günceller."
    )
    entered_pin = st.text_input(
        "Kalıcı kayıt PIN'i",
        type="password",
        key=f"{key_prefix}_pin",
    )

    if st.button(
        "💾 GitHub veri havuzuna kalıcı kaydet",
        type="primary",
        key=f"{key_prefix}_save",
    ):
        if not settings["admin_pin"]:
            st.error(
                "Secrets içinde admin_pin tanımlı değil. "
                "Güvenlik için kayıt durduruldu."
            )
        elif entered_pin != settings["admin_pin"]:
            st.error("PIN yanlış.")
        else:
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
                    "Kalıcı kayıt tamamlandı. GitHub veri.txt güncellendi. "
                    "Uygulama kısa süre içinde yeniden başlayabilir."
                )
                st.cache_data.clear()
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

st.title("🎯 Hızlı On Ultimate Analiz Motoru V12.0")
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


PAGES = [
    "✅ Kontrol",
    "🧠 Güç Puanı",
    "📈 Frekans",
    "🔗 Birlikte Çıkma",
    "🔥 Sıcak/Soğuk",
    "⏳ Dinlenme/Döngü",
    "🔄 Tekrar/Blok",
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
    st.success("Çalışan sürüm: V12.0 — Ana dosya: app.py")
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
    "V12.0 sağlam veri girişi, veri onarımı, öğrenen hibrit kuponlar ve 3 çekirdekli yoldaş kuponu içerir. "
    "Bu nedenle boş sekme ve sürekli yüklenme sorunu giderilmiştir. "
    "İstatistikler kesin sonuç veya kazanç garantisi vermez."
)
