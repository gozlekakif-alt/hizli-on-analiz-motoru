# -*- coding: utf-8 -*-
"""
HIZLI ON — 10'LU AİLE TEKRAR AVCISI

Amaç:
- 20 sayılık her çekiliş içinde bulunan 10'lu aileleri inceler.
- Aynı 10 sayının farklı günlerde tekrar tam 10/10 birlikte bulunduğu aileleri bulur.
- Özellikle 3 gün boyunca +2 gün, +2 gün gibi sabit gün ritimlerini yakalar.
- Günlük "ritimli 10'lu" sonucu gerektirmez; ham veri.txt üzerinden doğrudan tarar.

Örnek hedef:
01.09 -> 03.09 -> 05.09
aynı 10'lu aile, üç ayrı günde en az bir çekilişte tam 10/10 bulunmuşsa yakalanır.
"""

from __future__ import annotations

import csv
import io
import itertools
import math
import re
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# -------------------------------------------------------------------
# SAYFA / AYARLAR
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Hızlı On — 10'lu Aile Tekrar Avcısı",
    page_icon="🔟",
    layout="wide",
)

APP_VERSION = "10LU_TEKRAR_V1.0"
DEFAULT_DATA_FILE = Path("veri.txt")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"
K = 10


# -------------------------------------------------------------------
# VERİ OKUMA
# -------------------------------------------------------------------
def safe_secret(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, default)
        return str(v) if v is not None else default
    except Exception:
        return default


def github_read_text(repo: str, branch: str, path: str, token: str = "") -> str:
    if token:
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github.raw+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "hizli-on-10lu-tekrar",
            },
        )
    else:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "hizli-on-10lu-tekrar"},
        )

    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def load_data_text(uploaded=None):
    """Öncelik: yüklenen TXT > yerel veri.txt > GitHub veri.txt."""
    if uploaded is not None:
        raw = uploaded.getvalue()
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                return raw.decode(enc), f"Yüklenen dosya: {uploaded.name}"
            except Exception:
                pass
        return raw.decode("utf-8", errors="replace"), f"Yüklenen dosya: {uploaded.name}"

    if DEFAULT_DATA_FILE.exists():
        return DEFAULT_DATA_FILE.read_text(encoding="utf-8", errors="replace"), "GitHub/yerel veri.txt"

    repo = safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO
    branch = safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH
    path = safe_secret("GITHUB_DATA_PATH", DEFAULT_PATH) or DEFAULT_PATH
    token = safe_secret("GITHUB_TOKEN", "")

    try:
        return github_read_text(repo, branch, path, token), f"GitHub: {repo}/{path}"
    except Exception as e:
        return "", f"GitHub veri.txt okunamadı: {e}"


def _parse_nums_field(s: str):
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s)]
    return sorted(set(n for n in nums if 1 <= n <= 80))


@st.cache_data(show_spinner=False)
def parse_draws(text: str) -> pd.DataFrame:
    rows = []

    # Kompakt biçim:
    # 51213;25.08.2026 00:02;2,4,6,...
    line_re = re.compile(
        r"^\s*#?(\d{4,})\s*[;|]\s*(\d{2}\.\d{2}\.\d{4})\s+"
        r"(\d{2}:\d{2})\s*[;|]\s*(.*?)\s*$"
    )

    for line in text.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        draw = int(m.group(1))
        nums = _parse_nums_field(m.group(4))
        if len(nums) != 20:
            continue
        try:
            dt = datetime.strptime(
                f"{m.group(2)} {m.group(3)}", "%d.%m.%Y %H:%M"
            )
        except Exception:
            continue
        rows.append((draw, dt, nums))

    # Milli Piyango kopyala-yapıştır biçimi
    if not rows:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if "çekiliş no" not in s.lower():
                i += 1
                continue

            draw = None
            m = re.search(r"(\d{4,})", s)
            if m:
                draw = int(m.group(1))

            j = i + 1
            if draw is None:
                while j < min(i + 6, len(lines)):
                    m = re.fullmatch(r"\s*#?\s*(\d{4,})\s*", lines[j])
                    if m:
                        draw = int(m.group(1))
                        j += 1
                        break
                    j += 1

            if draw is None:
                i += 1
                continue

            dt = None
            while j < min(i + 12, len(lines)):
                m = re.search(
                    r"(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})",
                    lines[j],
                )
                if m:
                    try:
                        dt = datetime.strptime(
                            f"{m.group(1)} {m.group(2)}",
                            "%d.%m.%Y %H:%M",
                        )
                    except Exception:
                        dt = None
                    j += 1
                    break
                j += 1

            if dt is None:
                i += 1
                continue

            nums = []
            while j < len(lines) and len(nums) < 20:
                if "çekiliş no" in lines[j].lower():
                    break
                m = re.fullmatch(r"\s*(\d{1,2})\s*", lines[j])
                if m:
                    n = int(m.group(1))
                    if 1 <= n <= 80:
                        nums.append(n)
                j += 1

            nums = sorted(set(nums))
            if len(nums) == 20:
                rows.append((draw, dt, nums))

            i = max(i + 1, j)

    if not rows:
        return pd.DataFrame(columns=["draw", "dt", "nums"])

    out = pd.DataFrame(rows, columns=["draw", "dt", "nums"])
    out = (
        out.sort_values(["draw", "dt"])
        .drop_duplicates(subset=["draw"], keep="last")
        .reset_index(drop=True)
    )
    out["dt"] = pd.to_datetime(out["dt"])
    out["day"] = out["dt"].dt.date
    return out


# -------------------------------------------------------------------
# BİT MASKELERİ
# -------------------------------------------------------------------
def nums_to_mask(nums):
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m


def mask_to_nums(mask: int):
    out = []
    x = int(mask)
    while x:
        lsb = x & -x
        out.append(lsb.bit_length())
        x ^= lsb
    return tuple(out)


def family_text(mask: int):
    return "-".join(f"{n:02d}" for n in mask_to_nums(mask))


def iter_10_submasks_from_intersection(inter_mask: int):
    nums = mask_to_nums(inter_mask)
    if len(nums) < 10:
        return
    if len(nums) == 10:
        yield inter_mask
        return

    for comb in itertools.combinations(nums, 10):
        yield nums_to_mask(comb)


def build_occurrence_bits(df: pd.DataFrame):
    """Her sayı için hangi çekilişlerde bulunduğunu Python-int bitset olarak tutar."""
    num_bits = [0] * 81
    draw_masks = []

    for i, nums in enumerate(df["nums"]):
        b = 1 << i
        m = nums_to_mask(nums)
        draw_masks.append(m)
        for n in nums:
            num_bits[int(n)] |= b

    return num_bits, draw_masks


def occurrence_bits_for_family(fam_mask: int, num_bits):
    nums = mask_to_nums(fam_mask)
    if not nums:
        return 0
    b = num_bits[nums[0]]
    for n in nums[1:]:
        b &= num_bits[n]
        if not b:
            break
    return b


def bits_to_indices(bits: int):
    out = []
    x = int(bits)
    while x:
        lsb = x & -x
        out.append(lsb.bit_length() - 1)
        x ^= lsb
    return out


# -------------------------------------------------------------------
# GÜN RİTMİ
# -------------------------------------------------------------------
def longest_fixed_gap_run(active_days, gap_days: int):
    """
    Aktif günler içinde d, d+gap, d+2gap... en uzun zinciri bulur.
    Dönüş: liste[date]
    """
    if not active_days:
        return []

    day_set = set(active_days)
    best = []

    for d in sorted(active_days):
        # zincirin daha eski elemanı varsa buradan başlatma
        prev = d - pd.Timedelta(days=gap_days)
        prev = prev.date() if hasattr(prev, "date") else prev
        if prev in day_set:
            continue

        run = [d]
        cur = d
        while True:
            nxt = cur + pd.Timedelta(days=gap_days)
            nxt = nxt.date() if hasattr(nxt, "date") else nxt
            if nxt not in day_set:
                break
            run.append(nxt)
            cur = nxt

        if len(run) > len(best):
            best = run

    return best


def most_common_day_gap(active_days):
    if len(active_days) < 2:
        return None, 0

    counts = defaultdict(int)
    ds = sorted(active_days)
    for a, b in zip(ds[:-1], ds[1:]):
        g = (b - a).days
        counts[g] += 1

    if not counts:
        return None, 0
    gap, cnt = max(counts.items(), key=lambda x: (x[1], -x[0]))
    return gap, cnt


# -------------------------------------------------------------------
# ANA TARAMA
# -------------------------------------------------------------------
def discover_candidates(
    df: pd.DataFrame,
    draw_masks,
    gap_mode: str,
    fixed_gap: int,
    progress,
    status,
):
    """
    Aynı 10'lu aile iki farklı günde tekrar ettiyse,
    o iki güne ait en az bir çekiliş çiftinin kesişiminde 10 sayı bulunmak zorunda.
    Bu nedenle bütün C(80,10) evrenini üretmek yerine yalnız gerçek çekiliş
    çiftlerinin >=10 kesişimlerinden aday çıkarıyoruz.
    """
    day_to_indices = defaultdict(list)
    for i, day in enumerate(df["day"]):
        day_to_indices[day].append(i)

    days = sorted(day_to_indices)
    day_pairs = []

    for i, d1 in enumerate(days):
        for j in range(i + 1, len(days)):
            d2 = days[j]
            gap = (d2 - d1).days
            if gap_mode == "Sabit gün aralığı":
                if gap == fixed_gap:
                    day_pairs.append((d1, d2))
            else:
                day_pairs.append((d1, d2))

    candidates = set()
    pair_hits = 0
    generated = 0

    total_pairs = max(1, len(day_pairs))

    for pno, (d1, d2) in enumerate(day_pairs, start=1):
        idx1 = day_to_indices[d1]
        idx2 = day_to_indices[d2]

        pair_candidates = set()

        for i in idx1:
            m1 = draw_masks[i]
            for j in idx2:
                inter = m1 & draw_masks[j]
                bc = inter.bit_count()
                if bc < 10:
                    continue

                pair_hits += 1

                for fam in iter_10_submasks_from_intersection(inter):
                    pair_candidates.add(fam)
                    generated += 1

        candidates.update(pair_candidates)

        progress.progress(
            pno / total_pairs,
            text=(
                f"Aday keşfi: {pno}/{total_pairs} gün çifti · "
                f">=10 kesişim {pair_hits:,} · benzersiz 10'lu {len(candidates):,}"
            ).replace(",", "."),
        )
        status.caption(
            f"İşlenen gün çifti: {d1.strftime('%d.%m.%Y')} ↔ {d2.strftime('%d.%m.%Y')}"
        )

    return candidates, len(day_pairs), pair_hits, generated


def verify_candidates(
    df: pd.DataFrame,
    candidates,
    num_bits,
    target_days: int,
    gap_mode: str,
    fixed_gap: int,
    progress,
):
    rows = []
    total = max(1, len(candidates))

    for no, fam in enumerate(candidates, start=1):
        occ = occurrence_bits_for_family(fam, num_bits)
        idxs = bits_to_indices(occ)

        if len(idxs) < target_days:
            continue

        active_days = sorted({df.iloc[i]["day"] for i in idxs})
        if len(active_days) < target_days:
            continue

        if gap_mode == "Sabit gün aralığı":
            run = longest_fixed_gap_run(active_days, fixed_gap)
            if len(run) < target_days:
                continue
            rhythm_gap = fixed_gap
            rhythm_run = run
        else:
            rhythm_gap, _ = most_common_day_gap(active_days)
            rhythm_run = active_days

        draws = [int(df.iloc[i]["draw"]) for i in idxs]
        times = [
            pd.Timestamp(df.iloc[i]["dt"]).strftime("%d.%m.%Y %H:%M")
            for i in idxs
        ]

        # Her aktif günde kaç çekilişte 10/10 geldi?
        by_day = defaultdict(list)
        for i in idxs:
            d = df.iloc[i]["day"]
            by_day[d].append(int(df.iloc[i]["draw"]))

        rows.append(
            {
                "Aile": family_text(fam),
                "Ritim": (
                    f"+{fixed_gap} gün"
                    if gap_mode == "Sabit gün aralığı"
                    else (f"baskın +{rhythm_gap} gün" if rhythm_gap else "")
                ),
                "En_Uzun_Zincir": len(rhythm_run),
                "Zincir_Günleri": " → ".join(
                    d.strftime("%d.%m.%Y") for d in rhythm_run
                ),
                "Toplam_Aktif_Gün": len(active_days),
                "Toplam_10da10_Aktivasyon": len(idxs),
                "Tüm_Aktif_Günler": " | ".join(
                    d.strftime("%d.%m.%Y") for d in active_days
                ),
                "Çekilişler": ",".join(map(str, draws)),
                "Saatler": " | ".join(times),
                "Gün_Bazlı_Çekilişler": " || ".join(
                    f"{d.strftime('%d.%m.%Y')}:" + ",".join(map(str, by_day[d]))
                    for d in sorted(by_day)
                ),
            }
        )

        if no % 250 == 0 or no == len(candidates):
            progress.progress(
                no / total,
                text=f"Doğrulama: {no:,}/{len(candidates):,} aday · bulunan {len(rows):,}".replace(",", "."),
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Aile",
                "Ritim",
                "En_Uzun_Zincir",
                "Zincir_Günleri",
                "Toplam_Aktif_Gün",
                "Toplam_10da10_Aktivasyon",
                "Tüm_Aktif_Günler",
                "Çekilişler",
                "Saatler",
                "Gün_Bazlı_Çekilişler",
            ]
        )

    out = pd.DataFrame(rows)
    out = out.sort_values(
        ["En_Uzun_Zincir", "Toplam_Aktif_Gün", "Toplam_10da10_Aktivasyon", "Aile"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    return out


def build_txt_report(
    result: pd.DataFrame,
    source: str,
    df: pd.DataFrame,
    gap_mode: str,
    fixed_gap: int,
    target_days: int,
    stats: dict,
):
    lines = []
    lines.append("=" * 110)
    lines.append("HIZLI ON — 10'LU AİLE TEKRAR AVCISI")
    lines.append("=" * 110)
    lines.append(f"APP: {APP_VERSION}")
    lines.append(f"Kaynak: {source}")
    lines.append(f"Çekiliş: {len(df)}")
    lines.append(f"Gün: {df['day'].nunique()}")
    lines.append(
        f"Aralık: {df.iloc[0]['dt']:%d.%m.%Y %H:%M} -> {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}"
    )
    lines.append(f"Mod: {gap_mode}")
    if gap_mode == "Sabit gün aralığı":
        lines.append(f"Hedef ritim: +{fixed_gap} gün")
    lines.append(f"En az zincir uzunluğu: {target_days} gün")
    lines.append("")
    lines.append("TANIM:")
    lines.append(
        "Bir 10'lu aile aktive sayılırsa, aynı 10 sayının tamamı AYNI TEK ÇEKİLİŞİN 20 sayısı içinde bulunmuştur."
    )
    lines.append(
        "Farklı çekilişlerden sayı biriktirme yoktur. Aynı aile farklı günlerde yeniden 10/10 bulunursa tekrar sayılır."
    )
    lines.append("")
    lines.append(
        f"Taranan gün çifti: {stats.get('day_pairs', 0):,} | "
        f">=10 ortak sayılı çekiliş çifti: {stats.get('pair_hits', 0):,} | "
        f"Benzersiz aday 10'lu: {stats.get('candidate_count', 0):,}"
    )
    lines.append(f"HEDEFİ SAĞLAYAN 10'LU AİLE: {len(result):,}")
    lines.append("")

    if result.empty:
        lines.append("Hedef koşulda tekrar eden 10'lu aile bulunamadı.")
        return "\n".join(lines)

    for i, r in result.iterrows():
        lines.append("-" * 110)
        lines.append(
            f"{i+1:05d}. {r['Aile']} | {r['Ritim']} | "
            f"zincir={r['En_Uzun_Zincir']} | aktif_gün={r['Toplam_Aktif_Gün']} | "
            f"10/10_aktivasyon={r['Toplam_10da10_Aktivasyon']}"
        )
        lines.append(f"  zincir günleri: {r['Zincir_Günleri']}")
        lines.append(f"  tüm aktif günler: {r['Tüm_Aktif_Günler']}")
        lines.append(f"  çekilişler: {r['Çekilişler']}")
        lines.append(f"  saatler: {r['Saatler']}")

    return "\n".join(lines)


# -------------------------------------------------------------------
# ARAYÜZ
# -------------------------------------------------------------------
st.title("🔟 Hızlı On — 10'lu Aile Tekrar Avcısı")
st.caption(
    "Aynı 10 sayının farklı günlerde aynı çekilişte 10/10 tekrarını bulur. "
    "Varsayılan hedef: 3 gün boyunca +2 gün, +2 gün."
)

with st.expander("🔒 Kilitli tanım", expanded=False):
    st.write(
        "Bir 10'lu aile yalnızca 10 sayının tamamı aynı tek çekilişin 20 sayısı içinde bulunduğunda aktive olur."
    )
    st.write(
        "Örnek: 01.09 → 03.09 → 05.09 aynı 10'lu aile en az birer çekilişte tam bulunursa, +2 gün x2 ritim yakalanır."
    )
    st.write(
        "Bu APP günlük ritim sonuçlarına bağlı değildir; ham veri.txt içinden doğrudan tekrar eden 10'luları arar."
    )

uploaded = st.file_uploader(
    "İstersen veri.txt yükle (boş bırakırsan GitHub/yerel veri.txt otomatik okunur)",
    type=["txt"],
)

text, source = load_data_text(uploaded)

if not text:
    st.error(source)
    st.stop()

df = parse_draws(text)

if df.empty:
    st.error("veri.txt bulundu ama geçerli 20 sayılık çekiliş okunamadı.")
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
b.metric("Gün", int(df["day"].nunique()))
c.metric("İlk gün", df.iloc[0]["dt"].strftime("%d.%m.%Y"))
d.metric("Son gün", df.iloc[-1]["dt"].strftime("%d.%m.%Y"))
st.success(f"Veri hazır — {source}")

st.divider()

c1, c2, c3 = st.columns(3)

gap_mode = c1.selectbox(
    "Gün ritmi",
    ["Sabit gün aralığı", "Herhangi günlerde tekrar"],
    index=0,
)

fixed_gap = c2.number_input(
    "Gün aralığı (+kaç gün)",
    min_value=1,
    max_value=30,
    value=2,
    step=1,
    disabled=(gap_mode != "Sabit gün aralığı"),
)

target_days = c3.number_input(
    "En az kaç gün zincir",
    min_value=2,
    max_value=10,
    value=3,
    step=1,
)

if gap_mode == "Sabit gün aralığı":
    st.info(
        f"Hedef: aynı 10'lu aile en az {int(target_days)} gün boyunca "
        f"+{int(fixed_gap)} gün aralıkla tekrar etsin."
    )
else:
    st.info(
        f"Hedef: aynı 10'lu aile en az {int(target_days)} farklı günde tekrar 10/10 bulunsun."
    )

start = st.button(
    "🔎 10'LU TEKRARLARI TARA",
    type="primary",
    use_container_width=True,
)

if "ten_result" not in st.session_state:
    st.session_state.ten_result = None
    st.session_state.ten_report = None
    st.session_state.ten_stats = None

if start:
    num_bits, draw_masks = build_occurrence_bits(df)

    st.subheader("1️⃣ Aday 10'lular keşfediliyor")
    p1 = st.progress(0.0)
    s1 = st.empty()

    candidates, day_pairs, pair_hits, generated = discover_candidates(
        df=df,
        draw_masks=draw_masks,
        gap_mode=gap_mode,
        fixed_gap=int(fixed_gap),
        progress=p1,
        status=s1,
    )

    stats = {
        "day_pairs": day_pairs,
        "pair_hits": pair_hits,
        "generated_before_dedup": generated,
        "candidate_count": len(candidates),
    }

    st.write(
        f"**{len(candidates):,}** benzersiz aday 10'lu bulundu.".replace(",", ".")
    )

    st.subheader("2️⃣ Adaylar bütün veri üzerinde doğrulanıyor")
    p2 = st.progress(0.0)

    result = verify_candidates(
        df=df,
        candidates=candidates,
        num_bits=num_bits,
        target_days=int(target_days),
        gap_mode=gap_mode,
        fixed_gap=int(fixed_gap),
        progress=p2,
    )

    report = build_txt_report(
        result=result,
        source=source,
        df=df,
        gap_mode=gap_mode,
        fixed_gap=int(fixed_gap),
        target_days=int(target_days),
        stats=stats,
    )

    st.session_state.ten_result = result
    st.session_state.ten_report = report
    st.session_state.ten_stats = stats

    if result.empty:
        st.warning("Bu koşullarda tekrar eden 10'lu aile bulunamadı.")
    else:
        st.success(
            f"Bulundu: {len(result):,} adet hedefi sağlayan 10'lu aile.".replace(",", ".")
        )

result = st.session_state.ten_result

if result is not None:
    st.divider()
    st.subheader("🎯 Sonuç")

    if not result.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Tekrar eden 10'lu", f"{len(result):,}".replace(",", "."))
        m2.metric("En uzun zincir", int(result["En_Uzun_Zincir"].max()))
        m3.metric("En çok aktif gün", int(result["Toplam_Aktif_Gün"].max()))

        st.dataframe(
            result[
                [
                    "Aile",
                    "Ritim",
                    "En_Uzun_Zincir",
                    "Zincir_Günleri",
                    "Toplam_Aktif_Gün",
                    "Toplam_10da10_Aktivasyon",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=520,
        )

        csv_data = result.to_csv(index=False).encode("utf-8-sig")
        txt_data = st.session_state.ten_report.encode("utf-8")

        d1, d2 = st.columns(2)
        d1.download_button(
            "⬇️ TÜM SONUÇLARI CSV İNDİR",
            data=csv_data,
            file_name="HIZLI_ON_10LU_TEKRAR_EDEN_AILELER.csv",
            mime="text/csv",
            use_container_width=True,
        )
        d2.download_button(
            "⬇️ TEK TXT RAPORU İNDİR",
            data=txt_data,
            file_name="HIZLI_ON_10LU_TEKRAR_EDEN_AILELER.txt",
            mime="text/plain",
            use_container_width=True,
        )

        st.subheader("İlk 20 ailenin ayrıntısı")
        for _, r in result.head(20).iterrows():
            with st.expander(
                f"{r['Aile']} · {r['Ritim']} · zincir {int(r['En_Uzun_Zincir'])}"
            ):
                st.write("**Zincir günleri:**", r["Zincir_Günleri"])
                st.write("**Tüm aktif günler:**", r["Tüm_Aktif_Günler"])
                st.write("**Çekilişler:**", r["Çekilişler"])
                st.write("**Saatler:**", r["Saatler"])
                st.write("**Gün bazlı:**", r["Gün_Bazlı_Çekilişler"])
    else:
        st.info("Son taramada hedef koşulda aile çıkmadı.")

st.caption(
    "Teknik yöntem: C(80,10) evreni körlemesine üretilmez. "
    "Farklı günlerdeki gerçek çekiliş çiftlerinin ortak sayıları >=10 olduğunda "
    "yalnız mümkün 10'lu adaylar çıkarılır; sonra her aday bütün veri üzerinde tam 10/10 doğrulanır."
)
