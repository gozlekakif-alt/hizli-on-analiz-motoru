import base64
from datetime import datetime
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
    page_title="Hızlı On Ultimate Analiz Motoru V10.3",
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

st.title("🎯 Hızlı On Ultimate Analiz Motoru V10.3")
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
    st.success("Çalışan sürüm: V10.3 — Ana dosya: app.py")
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

        if st.button(
            "🎯 Geçiş kuponlarını üret",
            type="primary",
            key="v103_transition_generate",
        ):
            for shift in range(transition_count):
                coupon = transition_coupon(
                    transition_candidates,
                    pair_counts,
                    transition_size,
                    shift,
                )
                st.success(
                    f"Geçiş Kuponu {shift + 1}: "
                    + " - ".join(map(str, coupon))
                )
                st.dataframe(
                    explain_transition_coupon(
                        coupon,
                        transition_candidates,
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

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
        "Tek çekilişi aşağıdaki kutuya yapıştır. "
        "Toplu dosya yüklediysen Kontrol bölümünden kalıcı kaydet."
    )
    raw = st.text_area(
        "Yeni çekilişi yapıştır",
        height=280,
        placeholder="""Çekiliş no: 47054
05.08.2026 - 21:02
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
20""",
        key="v102_new_draw",
    )

    if raw.strip():
        row = parse_draw_block(raw)
        if not row:
            st.error(
                "Çekiliş okunamadı. Çekiliş no, tarih-saat "
                "ve 20 farklı sayı gerekli."
            )
        elif row[0] in set(df.Cekilis_No.astype(int)):
            st.warning("Bu çekiliş zaten mevcut.")
        else:
            candidate_df = merge_data(
                df, pd.DataFrame([row], columns=COLS)
            )
            st.success(
                f"Çekiliş #{row[0]} doğrulandı. "
                f"Havuz {len(df)} → {len(candidate_df)} olacak."
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
    "V10.3 telefonda yalnız seçilen bölümü hesaplar ve geçiş kuponu üretir. "
    "Bu nedenle boş sekme ve sürekli yüklenme sorunu giderilmiştir. "
    "İstatistikler kesin sonuç veya kazanç garantisi vermez."
)
