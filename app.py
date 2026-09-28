
import re
import urllib.request
from collections import Counter
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Hızlı On — 14 Gün Saatlik Aktivasyon Analizi",
    page_icon="🎯",
    layout="wide",
)

EXPECTED_MINUTES = [2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57]
BLOCK_NAMES = {
    "A": "İlk 3 (02–12)",
    "B": "İkinci 3 (17–27)",
    "C": "Son 6 (32–57)",
}

def tr_num_list(nums):
    nums = list(nums)
    return ", ".join(str(int(x)) for x in nums) if nums else "—"

def read_text_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")

def clean_line(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^\s*#+\s*", "", s)
    s = s.replace("\u00a0", " ").strip()
    return s

def parse_number_line(line: str):
    """
    Sadece sayı/separatör içeren satırlardan 1–80 arası sayıları döndürür.
    'Detaylar' / URL / çekiliş no satırlarını yanlışlıkla sayı olarak almaz.
    """
    s = clean_line(line)
    if not s:
        return []
    if not re.fullmatch(r"[\d\s,;|/\-]+", s):
        return []
    vals = [int(x) for x in re.findall(r"\d+", s)]
    return [x for x in vals if 1 <= x <= 80]

@st.cache_data(show_spinner=False)
def parse_hizli_on_text(text: str):
    lines = [clean_line(x) for x in text.splitlines()]
    rows = []
    errors = []

    # ------------------------------------------------------------
    # FORMAT-1: GitHub veri.txt gerçek formatı
    # 51213;25.08.2026 00:02;2,4,6,...,80
    # ------------------------------------------------------------
    semicolon_rows = []
    row_pat = re.compile(
        r"^\\s*(\\d{4,6})\\s*;\\s*"
        r"(\\d{1,2}\\.\\d{1,2}\\.\\d{4})\\s+"
        r"(\\d{1,2}:\\d{2})\\s*;\\s*(.+?)\\s*$"
    )

    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s:
            continue
        m = row_pat.match(s)
        if not m:
            continue

        draw_id = int(m.group(1))
        try:
            draw_dt = datetime.strptime(
                m.group(2) + " " + m.group(3), "%d.%m.%Y %H:%M"
            )
        except ValueError:
            errors.append(f"#{draw_id}: tarih/saat okunamadı")
            continue

        nums = [int(x) for x in re.findall(r"\\d+", m.group(4))]
        nums = [x for x in nums if 1 <= x <= 80]

        if len(nums) != 20 or len(set(nums)) != 20:
            errors.append(
                f"#{draw_id} {draw_dt:%d.%m.%Y %H:%M}: "
                f"{len(nums)} sayı okundu / benzersiz={len(set(nums))}"
            )
            continue

        semicolon_rows.append({
            "draw_id": draw_id,
            "dt": draw_dt,
            "date": draw_dt.date(),
            "hour": draw_dt.hour,
            "minute": draw_dt.minute,
            "numbers": tuple(sorted(nums)),
        })

    if semicolon_rows:
        df = pd.DataFrame(semicolon_rows)
        df = (
            df.sort_values(["dt", "draw_id"])
              .drop_duplicates("draw_id", keep="last")
              .reset_index(drop=True)
        )
        return df, errors

    # ------------------------------------------------------------
    # FORMAT-2: Blok formatı
    # Çekiliş no: ...
    # 25.08.2026 - 00:02
    # 1
    # 2
    # ...
    # ------------------------------------------------------------
    i = 0

    draw_pat = re.compile(r"(?:Çekiliş|Cekilis)\s*no\s*:\s*(\d+)", re.I)
    dt_pat = re.compile(
        r"(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:-|–|—)?\s*(\d{1,2}:\d{2})"
    )

    while i < len(lines):
        m = draw_pat.search(lines[i])
        if not m:
            i += 1
            continue

        draw_id = int(m.group(1))
        i += 1

        draw_dt = None
        scan_limit = min(i + 6, len(lines))
        while i < scan_limit:
            dm = dt_pat.search(lines[i])
            if dm:
                try:
                    draw_dt = datetime.strptime(
                        dm.group(1) + " " + dm.group(2), "%d.%m.%Y %H:%M"
                    )
                except ValueError:
                    draw_dt = None
                i += 1
                break
            if draw_pat.search(lines[i]):
                break
            i += 1

        if draw_dt is None:
            errors.append(f"#{draw_id}: tarih/saat okunamadı")
            continue

        nums = []
        while i < len(lines) and len(nums) < 20:
            if draw_pat.search(lines[i]):
                break
            if "detay" in lines[i].lower() or "http://" in lines[i].lower() or "https://" in lines[i].lower():
                i += 1
                continue

            cand = parse_number_line(lines[i])
            for n in cand:
                if len(nums) < 20:
                    nums.append(n)
            i += 1

        if len(nums) != 20:
            errors.append(f"#{draw_id} {draw_dt:%d.%m.%Y %H:%M}: {len(nums)} sayı okundu")
            continue

        if len(set(nums)) != 20:
            errors.append(f"#{draw_id} {draw_dt:%d.%m.%Y %H:%M}: tekrar eden sayı var")
            continue

        rows.append({
            "draw_id": draw_id,
            "dt": draw_dt,
            "date": draw_dt.date(),
            "hour": draw_dt.hour,
            "minute": draw_dt.minute,
            "numbers": tuple(sorted(nums)),
        })

    if not rows:
        return pd.DataFrame(columns=["draw_id","dt","date","hour","minute","numbers"]), errors

    df = pd.DataFrame(rows).sort_values(["dt", "draw_id"]).drop_duplicates("draw_id", keep="last")
    return df.reset_index(drop=True), errors

def count_classes(draw_rows):
    c = Counter()
    for nums in draw_rows["numbers"]:
        c.update(nums)
    classes = {k: [] for k in range(4)}
    for n in range(1, 81):
        classes[min(c.get(n, 0), 3)].append(n)
    return c, classes

def make_sessions(df):
    sessions = []
    for (d, h), g in df.groupby(["date", "hour"], sort=True):
        g = g.sort_values(["minute", "draw_id"]).copy()
        minute_counts = g["minute"].value_counts()
        exact = all(minute_counts.get(m, 0) == 1 for m in EXPECTED_MINUTES)
        standard = g[g["minute"].isin(EXPECTED_MINUTES)].copy()
        complete = exact and len(standard) == 12
        sessions.append({
            "date": d,
            "hour": int(h),
            "complete": bool(complete),
            "n_draws": int(len(g)),
            "n_standard": int(len(standard)),
        })
    return pd.DataFrame(sessions)

def analyze_hour(g):
    g = g.sort_values(["minute", "draw_id"]).copy()
    standard = g[g["minute"].isin(EXPECTED_MINUTES)].copy()

    # Aynı standart dakikada birden fazla kayıt varsa son draw_id'yi tut.
    standard = standard.sort_values(["minute","draw_id"]).drop_duplicates("minute", keep="last")
    standard = standard.set_index("minute").reindex(EXPECTED_MINUTES).reset_index()

    if standard["draw_id"].isna().any():
        missing = standard.loc[standard["draw_id"].isna(), "minute"].tolist()
        raise ValueError("Eksik standart dakikalar: " + ", ".join(f"{m:02d}" for m in missing))

    standard["draw_id"] = standard["draw_id"].astype(int)
    A = standard.iloc[0:3].copy()
    B = standard.iloc[3:6].copy()
    C = standard.iloc[6:12].copy()

    cntA, clsA = count_classes(A)
    cntB, clsB = count_classes(B)

    cross = {}
    for a in range(4):
        for b in range(4):
            nums = [n for n in range(1,81) if cntA.get(n,0) == a and cntB.get(n,0) == b]
            cross[(a,b)] = nums

    zero6 = [n for n in range(1,81) if cntA.get(n,0) + cntB.get(n,0) == 0]
    zero6_events = []
    unopened = []
    for n in zero6:
        found = None
        for _, r in C.iterrows():
            if n in r["numbers"]:
                found = r
                break
        if found is None:
            unopened.append(n)
        else:
            zero6_events.append({
                "Sayı": n,
                "İlk aktivasyon": found["dt"].strftime("%H:%M"),
                "Çekiliş": int(found["draw_id"]),
            })

    family_rows = []
    for _, r in C.iterrows():
        for (a,b), fam in cross.items():
            if not fam:
                continue
            active = sorted(set(fam).intersection(r["numbers"]))
            family_rows.append({
                "Saat": r["dt"].strftime("%H:%M"),
                "Çekiliş": int(r["draw_id"]),
                "İlk 3": f"{a}/3",
                "İkinci 3": f"{b}/3",
                "Aile büyüklüğü": len(fam),
                "Bu çekilişte aktif": len(active),
                "Aktif sayılar": tr_num_list(active),
            })

    final_draw_rows = []
    for _, r in C.iterrows():
        present_pairs = []
        total_members = 0
        for (a,b), fam in cross.items():
            if not fam:
                continue
            active = sorted(set(fam).intersection(r["numbers"]))
            if active:
                present_pairs.append(f"{a}/3→{b}/3: {tr_num_list(active)}")
                total_members += len(active)
        final_draw_rows.append({
            "Saat": r["dt"].strftime("%H:%M"),
            "Çekiliş": int(r["draw_id"]),
            "Sınıf buluşmaları": " | ".join(present_pairs),
            "Toplam aile üyesi": total_members,
        })

    all_hour_counter = Counter()
    for nums in standard["numbers"]:
        all_hour_counter.update(nums)
    full_hour_unseen = [n for n in range(1,81) if all_hour_counter.get(n,0) == 0]

    active_both = [n for n in range(1,81) if cntA.get(n,0)>0 and cntB.get(n,0)>0]
    new_in_B = [n for n in range(1,81) if cntA.get(n,0)==0 and cntB.get(n,0)>0]
    dropped_in_B = [n for n in range(1,81) if cntA.get(n,0)>0 and cntB.get(n,0)==0]
    new_strong_B = cross[(0,2)] + cross[(0,3)]

    represented_final = {}
    for pair, fam in cross.items():
        represented_final[pair] = sum(
            1 for _, r in C.iterrows()
            if set(fam).intersection(r["numbers"])
        )

    closure_ratio = (len(zero6_events) / len(zero6)) if zero6 else 1.0
    carry_score = len(active_both)
    late_score = len(new_strong_B)

    # Betimleyici etiket; tahmin değil.
    if closure_ratio >= 0.95 and late_score >= 3:
        character = "DEVİR / GEÇ AKTİVASYON"
    elif carry_score >= 18 and closure_ratio < 0.95:
        character = "TAŞIMA / DEVAM"
    else:
        character = "KARMA"

    metrics = {
        "A_unique": 80 - len(clsA[0]),
        "A_0": len(clsA[0]),
        "A_1": len(clsA[1]),
        "A_2": len(clsA[2]),
        "A_3": len(clsA[3]),
        "B_unique": 80 - len(clsB[0]),
        "B_0": len(clsB[0]),
        "B_1": len(clsB[1]),
        "B_2": len(clsB[2]),
        "B_3": len(clsB[3]),
        "zero6": len(zero6),
        "zero6_opened": len(zero6_events),
        "zero6_unopened": len(unopened),
        "closure_ratio": closure_ratio,
        "full_hour_unseen": len(full_hour_unseen),
        "active_both": len(active_both),
        "new_in_B": len(new_in_B),
        "dropped_in_B": len(dropped_in_B),
        "A0_B2": len(cross[(0,2)]),
        "A0_B3": len(cross[(0,3)]),
        "A3_B0": len(cross[(3,0)]),
        "A3_B1": len(cross[(3,1)]),
        "A3_B2": len(cross[(3,2)]),
        "A3_B3": len(cross[(3,3)]),
        "character": character,
    }

    return {
        "draws": standard,
        "A": A, "B": B, "C": C,
        "cntA": cntA, "cntB": cntB,
        "clsA": clsA, "clsB": clsB,
        "cross": cross,
        "zero6": zero6,
        "zero6_events": pd.DataFrame(zero6_events),
        "unopened": unopened,
        "family_rows": pd.DataFrame(family_rows),
        "final_draw_rows": pd.DataFrame(final_draw_rows),
        "full_hour_unseen": full_hour_unseen,
        "represented_final": represented_final,
        "metrics": metrics,
    }

def draw_table(block):
    out = block[["dt","draw_id","numbers"]].copy()
    out["Saat"] = out["dt"].dt.strftime("%H:%M")
    out["Çekiliş"] = out["draw_id"].astype(int)
    out["20 sayı"] = out["numbers"].apply(tr_num_list)
    return out[["Saat","Çekiliş","20 sayı"]]

def classes_table(classes):
    return pd.DataFrame([
        {"Sınıf": f"{k}/3", "Adet": len(classes[k]), "Sayılar": tr_num_list(classes[k])}
        for k in (0,1,2,3)
    ])

def cross_table(cross):
    rows = []
    for a in range(4):
        for b in range(4):
            nums = cross[(a,b)]
            rows.append({
                "İlk 3": f"{a}/3",
                "İkinci 3": f"{b}/3",
                "Adet": len(nums),
                "Sayılar": tr_num_list(nums),
            })
    return pd.DataFrame(rows)

def session_summary(df, sessions, selected_dates=None):
    valid = sessions[sessions["complete"]].copy()
    if selected_dates is not None:
        valid = valid[valid["date"].isin(selected_dates)]

    rows = []
    transition_rows = []
    activation_rows = []

    for _, s in valid.iterrows():
        g = df[(df["date"] == s["date"]) & (df["hour"] == s["hour"])]
        try:
            a = analyze_hour(g)
        except Exception:
            continue
        m = a["metrics"]
        rows.append({
            "Tarih": s["date"],
            "Saat": int(s["hour"]),
            "İlk3 farklı": m["A_unique"],
            "İlk3 1/3": m["A_1"],
            "İlk3 2/3": m["A_2"],
            "İlk3 3/3": m["A_3"],
            "İlk6 sıfır": m["zero6"],
            "Son6 açılan": m["zero6_opened"],
            "Son6 açılmayan": m["zero6_unopened"],
            "Açılma oranı": m["closure_ratio"],
            "Saat sonu hiç gelmeyen": m["full_hour_unseen"],
            "İki blokta da aktif": m["active_both"],
            "İkinci 3 yeni": m["new_in_B"],
            "0/3→2/3": m["A0_B2"],
            "0/3→3/3": m["A0_B3"],
            "Karakter": m["character"],
        })
        for (aa,bb), nums in a["cross"].items():
            transition_rows.append({
                "Tarih": s["date"], "Saat": int(s["hour"]),
                "İlk 3 sınıfı": aa, "İkinci 3 sınıfı": bb,
                "Aile büyüklüğü": len(nums),
                "Son6 temsil": a["represented_final"].get((aa,bb),0),
            })
        if not a["zero6_events"].empty:
            for _, r in a["zero6_events"].iterrows():
                activation_rows.append({
                    "Tarih": s["date"], "Saat": int(s["hour"]),
                    "Sayı": int(r["Sayı"]),
                    "İlk aktivasyon": r["İlk aktivasyon"],
                    "Çekiliş": int(r["Çekiliş"]),
                })

    return pd.DataFrame(rows), pd.DataFrame(transition_rows), pd.DataFrame(activation_rows)


def build_full_text_report(df, sessions, selected_dates=None):
    valid = sessions[sessions["complete"]].copy()
    if selected_dates is not None:
        valid = valid[valid["date"].isin(selected_dates)]

    out = []
    out.append("HIZLI ON — 14 GÜN SAAT SAAT TAM ANALİZ RAPORU")
    out.append("=" * 72)
    out.append("Model: İlk 3 (02–12) / İkinci 3 (17–27) / Son 6 (32–57)")
    out.append("")

    analyzed = 0

    for _, s in valid.sort_values(["date","hour"]).iterrows():
        g = df[(df["date"] == s["date"]) & (df["hour"] == s["hour"])]
        try:
            a = analyze_hour(g)
        except Exception:
            continue

        analyzed += 1
        m = a["metrics"]
        out.append("")
        out.append("#" * 72)
        out.append(f"{s['date']:%d.%m.%Y} — {int(s['hour']):02d}:02–{int(s['hour']):02d}:57")
        out.append("#" * 72)

        out.append(
            f"İlk 3: farklı={m['A_unique']} | "
            f"0/3={m['A_0']} | 1/3={m['A_1']} | 2/3={m['A_2']} | 3/3={m['A_3']}"
        )
        out.append(
            f"İkinci 3: farklı={m['B_unique']} | "
            f"0/3={m['B_0']} | 1/3={m['B_1']} | 2/3={m['B_2']} | 3/3={m['B_3']}"
        )
        out.append(
            f"İlk 6 sıfır={m['zero6']} | Son 6'da açılan={m['zero6_opened']} | "
            f"Açılmayan={m['zero6_unopened']} | Saat sonu hiç gelmeyen={m['full_hour_unseen']}"
        )
        out.append(
            f"İki blokta da aktif={m['active_both']} | "
            f"İkinci 3'te yeni={m['new_in_B']} | "
            f"0/3→2/3={m['A0_B2']} | 0/3→3/3={m['A0_B3']} | "
            f"Karakter={m['character']}"
        )

        out.append("")
        out.append("İLK 3 SINIFLARI")
        for k in (0,1,2,3):
            out.append(f"{k}/3 ({len(a['clsA'][k])}): {tr_num_list(a['clsA'][k])}")

        out.append("")
        out.append("İKİNCİ 3 SINIFLARI")
        for k in (0,1,2,3):
            out.append(f"{k}/3 ({len(a['clsB'][k])}): {tr_num_list(a['clsB'][k])}")

        out.append("")
        out.append("İLK 3 → İKİNCİ 3 GEÇİŞ AİLELERİ")
        for aa in range(4):
            for bb in range(4):
                fam = a["cross"][(aa,bb)]
                if fam:
                    out.append(
                        f"{aa}/3→{bb}/3 ({len(fam)}): {tr_num_list(fam)}"
                    )

        out.append("")
        out.append("İLK 6'DA 0/6 KALANLAR")
        out.append(tr_num_list(a["zero6"]))

        out.append("")
        out.append("0/6 → SON 6 İLK AKTİVASYON")
        if a["zero6_events"].empty:
            out.append("—")
        else:
            for _, r in a["zero6_events"].sort_values(["İlk aktivasyon","Sayı"]).iterrows():
                out.append(
                    f"{int(r['Sayı'])} → {r['İlk aktivasyon']} "
                    f"(#{int(r['Çekiliş'])})"
                )

        out.append("")
        out.append("SAAT SONUNDA HÂLÂ HİÇ GELMEYEN")
        out.append(tr_num_list(a["full_hour_unseen"]))

        out.append("")
        out.append("SON 6 ÇEKİLİŞTE SINIF BULUŞMALARI")
        for _, r in a["final_draw_rows"].iterrows():
            out.append(
                f"{r['Saat']} #{int(r['Çekiliş'])} | "
                f"{r['Sınıf buluşmaları']}"
            )

    out.insert(3, f"Toplam analiz edilen tam saat: {analyzed}")
    return "\n".join(out)


st.title("🎯 Hızlı On — 14 Gün Saatlik Aktivasyon Analizi")
st.caption(
    "Her tam saat: İlk 3 çekiliş (02–12) + ikinci 3 (17–27) + son 6 (32–57). "
    "Analiz betimleyicidir; rastgele çekilişlerde geçmiş örüntüler gelecek sonucu garanti etmez."
)

GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/"
    "gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"
)

@st.cache_data(ttl=300, show_spinner=False)
def load_github_veri():
    req = urllib.request.Request(
        GITHUB_RAW_URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()

with st.sidebar:
    st.header("Veri")
    default_path = Path(__file__).resolve().parent / "veri.txt"

    raw = None
    source_name = None
    load_error = None

    # Öncelik 1: Streamlit/GitHub repo içindeki veri.txt
    if default_path.exists():
        try:
            raw = default_path.read_bytes()
            source_name = "GitHub repo / veri.txt"
        except Exception as e:
            load_error = str(e)

    # Öncelik 2: RAW GitHub adresi
    if raw is None:
        try:
            raw = load_github_veri()
            source_name = "GitHub RAW / main/veri.txt"
        except Exception as e:
            load_error = str(e)

    st.write("Kaynak dosya: **veri.txt**")
    st.write("Repo: **gozlekakif-alt/hizli-on-analiz-motoru**")
    st.write("Branch: **main**")
    st.write("Standart dakika dizisi: **02, 07, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57**")

if raw is None:
    st.error("GitHub `veri.txt` okunamadı.")
    if load_error:
        st.code(load_error)
    st.stop()

text = read_text_bytes(raw)
df, parse_errors = parse_hizli_on_text(text)

if df.empty:
    st.error("Dosyadan geçerli çekiliş okunamadı.")
    if parse_errors:
        st.code("\n".join(parse_errors[:50]))
    st.stop()

sessions = make_sessions(df)
complete_sessions = sessions[sessions["complete"]]

top1, top2, top3, top4 = st.columns(4)
top1.metric("Okunan çekiliş", f"{len(df):,}".replace(",", "."))
top2.metric("Tarih aralığı", f"{df['date'].min():%d.%m.%Y} – {df['date'].max():%d.%m.%Y}")
top3.metric("Tam 12'li saat", len(complete_sessions))
top4.metric("Eksik/standart dışı saat", len(sessions) - len(complete_sessions))

st.caption(f"Kaynak: {source_name}")

if parse_errors:
    with st.expander(f"⚠️ Parser uyarıları ({len(parse_errors)})"):
        st.code("\n".join(parse_errors[:200]))

tabs = st.tabs(["🔬 Tek Saat Derin Analiz", "📊 14 Gün Saat Karşılaştırma", "🧭 Sınıf Geçiş Haritası", "🧾 Veri Kontrol"])

with tabs[0]:
    if complete_sessions.empty:
        st.warning("Standart 12 çekilişi tamamlanmış saat bulunamadı.")
    else:
        c1, c2 = st.columns([1,1])
        dates = sorted(complete_sessions["date"].unique())
        selected_date = c1.selectbox(
            "Tarih",
            dates,
            format_func=lambda d: d.strftime("%d.%m.%Y")
        )
        hours = sorted(complete_sessions.loc[complete_sessions["date"] == selected_date, "hour"].unique())
        selected_hour = c2.selectbox("Saat", hours, format_func=lambda h: f"{int(h):02d}:02–{int(h):02d}:57")

        g = df[(df["date"] == selected_date) & (df["hour"] == selected_hour)]
        a = analyze_hour(g)
        m = a["metrics"]

        st.subheader(f"{selected_date:%d.%m.%Y} — {selected_hour:02d}:02–{selected_hour:02d}:57")
        mc1,mc2,mc3,mc4,mc5,mc6 = st.columns(6)
        mc1.metric("İlk 3 farklı", m["A_unique"])
        mc2.metric("İlk 3: 2/3", m["A_2"])
        mc3.metric("İlk 3: 3/3", m["A_3"])
        mc4.metric("İlk 6 sıfır", m["zero6"])
        mc5.metric("Son 6'da açılan", f"{m['zero6_opened']}/{m['zero6']}")
        mc6.metric("Saat sonu 0", m["full_hour_unseen"])

        st.info(
            f"**Saat karakteri (betimleyici kural): {m['character']}**  |  "
            f"İki ilk blokta da aktif: **{m['active_both']}**  |  "
            f"İkinci 3'te yeni gelen: **{m['new_in_B']}**  |  "
            f"0/3→2/3: **{m['A0_B2']}**  |  0/3→3/3: **{m['A0_B3']}**"
        )

        st.markdown("### 12 çekiliş")
        d1,d2,d3 = st.columns(3)
        with d1:
            st.markdown("**İlk 3**")
            st.dataframe(draw_table(a["A"]), hide_index=True, use_container_width=True)
        with d2:
            st.markdown("**İkinci 3**")
            st.dataframe(draw_table(a["B"]), hide_index=True, use_container_width=True)
        with d3:
            st.markdown("**Son 6**")
            st.dataframe(draw_table(a["C"]), hide_index=True, use_container_width=True)

        s1,s2 = st.columns(2)
        with s1:
            st.markdown("### İlk 3 — 0/3, 1/3, 2/3, 3/3")
            st.dataframe(classes_table(a["clsA"]), hide_index=True, use_container_width=True)
        with s2:
            st.markdown("### İkinci 3 — 0/3, 1/3, 2/3, 3/3")
            st.dataframe(classes_table(a["clsB"]), hide_index=True, use_container_width=True)

        st.markdown("### İlk 3 → İkinci 3 geçiş aileleri")
        ct = cross_table(a["cross"])
        st.dataframe(ct, hide_index=True, use_container_width=True)

        st.markdown("### İlk 6'da hiç gelmeyenler → son 6'da ilk aktivasyon")
        st.write(f"İlk 6 sonunda **0/6 = {len(a['zero6'])} sayı:** {tr_num_list(a['zero6'])}")
        if not a["zero6_events"].empty:
            st.dataframe(a["zero6_events"], hide_index=True, use_container_width=True)
        else:
            st.write("Son 6'da açılan yok.")
        st.write(f"**Saat sonunda hâlâ hiç gelmeyen:** {tr_num_list(a['full_hour_unseen'])}")

        st.markdown("### Son 6 çekilişte sınıf ailelerinin buluşması")
        fam = a["family_rows"].copy()
        show_only_active = st.checkbox("Sadece aktif buluşmaları göster", value=True, key="active_only_single")
        if show_only_active:
            fam = fam[fam["Bu çekilişte aktif"] > 0]
        st.dataframe(fam, hide_index=True, use_container_width=True, height=480)

        st.markdown("### Çekiliş bazında toplu buluşma")
        st.dataframe(a["final_draw_rows"], hide_index=True, use_container_width=True)

with tabs[1]:
    if complete_sessions.empty:
        st.warning("Tam saat bulunamadı.")
    else:
        all_dates = sorted(complete_sessions["date"].unique())
        min_d, max_d = min(all_dates), max(all_dates)
        dr = st.date_input("Tarih aralığı", value=(min_d,max_d), min_value=min_d, max_value=max_d)
        if isinstance(dr, tuple) and len(dr) == 2:
            d0,d1 = dr
        else:
            d0,d1 = min_d,max_d
        date_set = [d for d in all_dates if d0 <= d <= d1]

        sumdf, transdf, actdf = session_summary(df, sessions, date_set)
        if sumdf.empty:
            st.warning("Seçilen aralıkta tam saat yok.")
        else:
            st.markdown("### Saat bazında 14 gün ortalaması")
            hour_agg = sumdf.groupby("Saat").agg(
                Gün=("Tarih","count"),
                İlk3_farklı=("İlk3 farklı","mean"),
                İlk3_1_3=("İlk3 1/3","mean"),
                İlk3_2_3=("İlk3 2/3","mean"),
                İlk3_3_3=("İlk3 3/3","mean"),
                İlk6_sıfır=("İlk6 sıfır","mean"),
                Son6_açılan=("Son6 açılan","mean"),
                Son6_açılmayan=("Son6 açılmayan","mean"),
                Açılma_oranı=("Açılma oranı","mean"),
                Saat_sonu_0=("Saat sonu hiç gelmeyen","mean"),
                İki_blokta_da_aktif=("İki blokta da aktif","mean"),
                Sıfırdan_2_3=("0/3→2/3","mean"),
                Sıfırdan_3_3=("0/3→3/3","mean"),
            ).reset_index()
            pct_cols = ["Açılma_oranı"]
            hour_agg["Açılma_oranı"] = (hour_agg["Açılma_oranı"]*100).round(1).astype(str) + "%"
            num_cols = [c for c in hour_agg.columns if c not in ("Saat","Gün","Açılma_oranı")]
            hour_agg[num_cols] = hour_agg[num_cols].round(2)
            hour_agg["Saat"] = hour_agg["Saat"].apply(lambda h: f"{int(h):02d}:00")
            st.dataframe(hour_agg, hide_index=True, use_container_width=True)

            st.download_button(
                "Saat özetini CSV indir",
                hour_agg.to_csv(index=False).encode("utf-8-sig"),
                "saat_14_gun_ozet.csv",
                "text/csv"
            )

            st.markdown("### Gün × saat detay tablosu")
            detail = sumdf.copy()
            detail["Tarih"] = detail["Tarih"].apply(lambda d: d.strftime("%d.%m.%Y"))
            detail["Saat"] = detail["Saat"].apply(lambda h: f"{int(h):02d}:00")
            detail["Açılma oranı"] = (detail["Açılma oranı"]*100).round(1).astype(str) + "%"
            st.dataframe(detail, hide_index=True, use_container_width=True, height=520)

            full_report_txt = build_full_text_report(df, sessions, date_set)
            st.download_button(
                "📥 14 günlük TAM saat-saat raporu tek TXT indir",
                full_report_txt.encode("utf-8-sig"),
                "HIZLI_ON_14_GUN_SAAT_SAAT_TAM_RAPOR.txt",
                "text/plain",
                use_container_width=True,
            )

            st.markdown("### 0/6 havuzunun son 6'da ilk açıldığı dakikalar")
            if actdf.empty:
                st.write("Aktivasyon kaydı yok.")
            else:
                minute_dist = (
                    actdf.groupby("İlk aktivasyon")
                    .size()
                    .rename("İlk aktivasyon adedi")
                    .reset_index()
                    .sort_values("İlk aktivasyon")
                )
                st.dataframe(minute_dist, hide_index=True, use_container_width=True)

with tabs[2]:
    if complete_sessions.empty:
        st.warning("Tam saat bulunamadı.")
    else:
        sumdf, transdf, actdf = session_summary(df, sessions)
        if transdf.empty:
            st.write("Geçiş verisi yok.")
        else:
            st.markdown("### Tüm tam saatlerde ortalama geçiş ailesi büyüklüğü")
            piv = transdf.pivot_table(
                index="İlk 3 sınıfı",
                columns="İkinci 3 sınıfı",
                values="Aile büyüklüğü",
                aggfunc="mean"
            ).reindex(index=[0,1,2,3], columns=[0,1,2,3]).round(2)
            piv.index = [f"{x}/3" for x in piv.index]
            piv.columns = [f"{x}/3" for x in piv.columns]
            st.dataframe(piv, use_container_width=True)

            st.markdown("### Geçiş ailesinin son 6 çekilişte temsil edildiği ortalama çekiliş sayısı")
            piv2 = transdf.pivot_table(
                index="İlk 3 sınıfı",
                columns="İkinci 3 sınıfı",
                values="Son6 temsil",
                aggfunc="mean"
            ).reindex(index=[0,1,2,3], columns=[0,1,2,3]).round(2)
            piv2.index = [f"{x}/3" for x in piv2.index]
            piv2.columns = [f"{x}/3" for x in piv2.columns]
            st.dataframe(piv2, use_container_width=True)

            st.markdown("### Belirli saati günler arasında karşılaştır")
            hour_options = sorted(complete_sessions["hour"].unique())
            hh = st.selectbox("Saat", hour_options, format_func=lambda x: f"{int(x):02d}:00", key="hour_compare")
            hsum = sumdf[sumdf["Saat"] == hh].copy()
            hsum["Tarih"] = hsum["Tarih"].apply(lambda d: d.strftime("%d.%m.%Y"))
            hsum["Açılma oranı"] = (hsum["Açılma oranı"]*100).round(1).astype(str) + "%"
            st.dataframe(hsum, hide_index=True, use_container_width=True)

with tabs[3]:
    st.markdown("### Okunan çekilişler")
    preview = df[["draw_id","dt","numbers"]].copy()
    preview["Tarih/Saat"] = preview["dt"].dt.strftime("%d.%m.%Y %H:%M")
    preview["20 sayı"] = preview["numbers"].apply(tr_num_list)
    preview = preview.rename(columns={"draw_id":"Çekiliş"})[["Çekiliş","Tarih/Saat","20 sayı"]]
    st.dataframe(preview, hide_index=True, use_container_width=True, height=500)

    st.markdown("### Saat bütünlüğü")
    sess = sessions.copy()
    sess["Tarih"] = sess["date"].apply(lambda d: d.strftime("%d.%m.%Y"))
    sess["Saat"] = sess["hour"].apply(lambda h: f"{int(h):02d}:00")
    sess["Durum"] = sess["complete"].map({True:"TAM 12", False:"EKSİK / STANDART DIŞI"})
    sess = sess.rename(columns={"n_draws":"Toplam kayıt","n_standard":"Standart dakika"})
    st.dataframe(sess[["Tarih","Saat","Durum","Toplam kayıt","Standart dakika"]], hide_index=True, use_container_width=True)

    st.markdown("### Kontrol kuralları")
    st.write(
        "App yalnızca 1–80 arası **20 benzersiz sayı** içeren çekilişleri kabul eder. "
        "Tam saat analizinde 02,07,12,17,22,27,32,37,42,47,52,57 dakikalarının hepsinin bulunmasını ister. "
        "Eksik saatler veri kontrolünde görünür ama derin analize karıştırılmaz."
    )
