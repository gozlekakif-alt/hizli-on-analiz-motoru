import io
import os
import re
from pathlib import Path
from collections import Counter
from urllib.request import urlopen, Request

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On — +/− Damar Motoru V2", layout="wide")

ALL_NUMS = set(range(1, 81))
FULL_HOUR_MINUTES = [2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57]
MINUTE_LABELS = [f":{m:02d}" for m in FULL_HOUR_MINUTES]

# -----------------------------
# Veri okuma / ayrıştırma
# -----------------------------
def _safe_ints(s):
    vals = re.findall(r"(?<!\d)(?:0?[1-9]|[1-7]\d|80)(?!\d)", s)
    return [int(x) for x in vals if 1 <= int(x) <= 80]


def parse_draws(text: str) -> pd.DataFrame:
    """Hızlı On TXT formatlarını dayanıklı biçimde okur.

    Öncelik: kullanıcının standart tek satırlık formatı:
    58929;29.09.2026 16:02;2,4,...,77
    Ardından analiz TXT ve blok biçimleri denenir.
    """
    rows = []
    text = (text or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    def add_row(draw_id, dt, nums):
        try:
            draw_id = int(draw_id)
            dt = pd.to_datetime(dt, dayfirst=True, errors="coerce")
            nums = [int(x) for x in nums]
        except Exception:
            return
        if pd.isna(dt):
            return
        nums = list(dict.fromkeys(nums))
        if len(nums) == 20 and all(1 <= n <= 80 for n in nums):
            rows.append({"draw_id": draw_id, "dt": dt, "nums": frozenset(nums)})

    # 1) ANA FORMAT — draw;dd.mm.yyyy HH:MM;20 sayı
    # Bu parser eski çalışan uygulamalardaki güvenilir yöntemin aynısıdır.
    for line in lines:
        s = line.strip()
        if not s or ";" not in s:
            continue
        p = [x.strip() for x in s.split(";")]
        if len(p) < 3:
            continue
        try:
            draw = int("".join(ch for ch in p[0] if ch.isdigit()))
            dt = pd.to_datetime(p[1], dayfirst=True, errors="raise")
            nums = [int(x) for x in re.findall(r"(?<!\d)(?:0?[1-9]|[1-7]\d|80)(?!\d)", p[2])]
            add_row(draw, dt, nums)
        except Exception:
            pass

    # 2) Büyük analiz TXT: YYYY-MM-DD — HH:00 SAATİ + 'HH:MM #ID | çıkan=...'
    current_date = None
    for line in lines:
        s = line.strip()
        m_date = re.match(r"^(\d{4}-\d{2}-\d{2})\s+[—-]\s+\d{2}:00\s+SAATİ", s, re.I)
        if m_date:
            current_date = m_date.group(1)
            continue
        m = re.match(r"^(\d{1,2}:\d{2})\s+#(\d+)\s+\|\s+çıkan\s*=\s*(.*)$", s, re.I)
        if m and current_date:
            nums = _safe_ints(m.group(3))
            add_row(m.group(2), f"{current_date} {m.group(1)}", nums)

    # 3) Çekiliş no blok biçimi (tek veya iki satırlı ID)
    i = 0
    n = len(lines)
    while i < n:
        clean = lines[i].strip().replace("###", "").strip()
        if not re.match(r"^Çekiliş\s*no\s*:", clean, re.I):
            i += 1
            continue
        tail = re.sub(r"^Çekiliş\s*no\s*:\s*", "", clean, flags=re.I).strip()
        draw_id = int(tail) if re.fullmatch(r"\d{4,8}", tail or "") else None
        j = i + 1
        if draw_id is None:
            while j < min(i + 5, n):
                c = lines[j].strip().replace("###", "").strip()
                if re.fullmatch(r"\d{4,8}", c):
                    draw_id = int(c); j += 1; break
                j += 1
        if draw_id is None:
            i += 1; continue
        dt = None; nums = []
        scanned = 0
        while j < n and scanned < 90:
            t = lines[j].strip().replace("###", "").strip()
            if scanned > 0 and re.match(r"^Çekiliş\s*no\s*:", t, re.I):
                break
            md = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–— ]\s*(\d{1,2}:\d{2})", t)
            if md and dt is None:
                dt = f"{md.group(1)} {md.group(2)}"
            elif re.fullmatch(r"0?(?:[1-9])|[1-7]\d|80", t):
                nums.append(int(t))
                if len(nums) == 20:
                    break
            elif dt is not None:
                maybe = _safe_ints(t)
                if len(maybe) == 20 and len(set(maybe)) == 20:
                    nums = maybe; break
            j += 1; scanned += 1
        if dt is not None:
            add_row(draw_id, dt, nums)
        i = max(i + 1, j)

    if not rows:
        return pd.DataFrame(columns=["draw_id", "dt", "date", "hour", "minute", "nums"])

    df = pd.DataFrame(rows).drop_duplicates("draw_id", keep="last")
    df = df.sort_values(["dt", "draw_id"]).reset_index(drop=True)
    df["date"] = df["dt"].dt.date.astype(str)
    df["hour"] = df["dt"].dt.hour.astype(int)
    df["minute"] = df["dt"].dt.minute.astype(int)
    return df


def load_default_text():
    candidates = [
        Path("veri.txt"),
        Path("HIZLI_ON_TUM_GUNLER_TUM_SAATLER_TUM_ANALIZLER_TEK_DOSYA-1.txt"),
        Path("/mnt/data/veri.txt"),
        Path("/mnt/data/HIZLI_ON_TUM_GUNLER_TUM_SAATLER_TUM_ANALIZLER_TEK_DOSYA-1.txt"),
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore"), str(p)
    return None, None


def load_url_text(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


# -----------------------------
# Saat / ritim yardımcıları
# -----------------------------
def complete_hours(df):
    out = []
    for (date, hour), g in df.groupby(["date", "hour"], sort=True):
        gg = g[g["minute"].isin(FULL_HOUR_MINUTES)].sort_values("minute")
        if list(gg["minute"]) == FULL_HOUR_MINUTES:
            out.append((date, int(hour), gg.copy()))
    return out


def signature(nums_by_pos, num):
    return "".join("+" if num in s else "−" for s in nums_by_pos)


def hour_number_table(g):
    g = g.sort_values("minute")
    sets = g["nums"].tolist()
    rows = []
    for num in range(1, 81):
        sig = signature(sets, num)
        first3 = sig[:3]
        second3 = sig[3:6]
        last6 = sig[6:]
        rows.append({
            "Sayı": num,
            "12'li ritim": sig,
            "İlk3 desen": first3,
            "İlk3 +": first3.count("+"),
            "İkinci3 desen": second3,
            "İkinci3 +": second3.count("+"),
            "Son6 desen": last6,
            "Son6 +": last6.count("+"),
            "Saat toplam +": sig.count("+"),
            **{MINUTE_LABELS[i]: 1 if sig[i] == "+" else 0 for i in range(12)},
        })
    return pd.DataFrame(rows)


def transition_rows(hours):
    rows = []
    for date, hour, g in hours:
        g = g.sort_values("minute").reset_index(drop=True)
        for i in range(11):
            a = set(g.loc[i, "nums"])
            b = set(g.loc[i + 1, "nums"])
            pp = a & b
            pn = a - b
            np_ = b - a
            nn = ALL_NUMS - (a | b)
            rows.append({
                "date": date, "hour": hour,
                "from_min": int(g.loc[i, "minute"]), "to_min": int(g.loc[i+1, "minute"]),
                "from_draw": int(g.loc[i, "draw_id"]), "to_draw": int(g.loc[i+1, "draw_id"]),
                "++": len(pp), "+−": len(pn), "−+": len(np_), "−−": len(nn),
                "carry_nums": sorted(pp), "drop_nums": sorted(pn), "enter_nums": sorted(np_),
            })
    return pd.DataFrame(rows)


def pattern_stats(hours):
    # Her saat/sayı bir olay. İlk3 exact desen -> sonraki her dakikada + oranı ve son6 dağılımı.
    rows = []
    for date, hour, g in hours:
        t = hour_number_table(g)
        family = ""
        for _, r in t.iterrows():
            sig = r["12'li ritim"]
            rows.append({
                "date": date, "hour": hour, "num": int(r["Sayı"]),
                "first3": sig[:3], "first3_hits": sig[:3].count("+"),
                "second3": sig[3:6], "second3_hits": sig[3:6].count("+"),
                "last6": sig[6:], "last6_hits": sig[6:].count("+"),
                **{f"m{FULL_HOUR_MINUTES[i]:02d}": 1 if sig[i] == "+" else 0 for i in range(12)},
            })
    ev = pd.DataFrame(rows)
    if ev.empty:
        return ev, pd.DataFrame()
    grp = []
    for pat, x in ev.groupby("first3"):
        d = {
            "İlk3 desen": pat,
            "İlk3 +": pat.count("+"),
            "n": len(x),
            "Son6 ort +": x["last6_hits"].mean(),
            "Son6 1+ %": 100*(x["last6_hits"] >= 1).mean(),
            "Son6 2+ %": 100*(x["last6_hits"] >= 2).mean(),
            "Son6 3+ %": 100*(x["last6_hits"] >= 3).mean(),
            "Son6 4+ %": 100*(x["last6_hits"] >= 4).mean(),
        }
        for m in FULL_HOUR_MINUTES[3:]:
            d[f":{m:02d} + %"] = 100*x[f"m{m:02d}"].mean()
        grp.append(d)
    return ev, pd.DataFrame(grp).sort_values(["İlk3 +", "İlk3 desen"], ascending=[False, True])


def first3_count_stats(events):
    out = []
    for k, x in events.groupby("first3_hits"):
        d = {
            "İlk3 sınıf": f"{k}/3",
            "n": len(x),
            "Son6 ort +": x["last6_hits"].mean(),
            "Son6 1+ %": 100*(x["last6_hits"] >= 1).mean(),
            "Son6 2+ %": 100*(x["last6_hits"] >= 2).mean(),
            "Son6 3+ %": 100*(x["last6_hits"] >= 3).mean(),
            "Son6 4+ %": 100*(x["last6_hits"] >= 4).mean(),
            "Son6 5+ %": 100*(x["last6_hits"] >= 5).mean(),
            "Son6 6/6 %": 100*(x["last6_hits"] == 6).mean(),
        }
        for m in FULL_HOUR_MINUTES[6:]:
            d[f":{m:02d} + %"] = 100*x[f"m{m:02d}"].mean()
        out.append(d)
    return pd.DataFrame(out).sort_values("İlk3 sınıf")


def root_damar_tracking(g, start_idx):
    """Seçilen çekilişin gerçek 20 pozitifi kök damar; sonraki çekilişlerde yolu."""
    g = g.sort_values("minute").reset_index(drop=True)
    root = set(g.loc[start_idx, "nums"])
    later_sets = g.loc[start_idx:, "nums"].tolist()
    rows = []
    for num in sorted(root):
        sig = signature(later_sets, num)
        rows.append({
            "Sayı": num,
            "Damar yolu": sig,
            "Başlangıç sonrası +": sig[1:].count("+"),
            "Kesintisiz + serisi": next((i for i,c in enumerate(sig) if c == "−"), len(sig)),
            "Son çekilişte +": 1 if sig[-1] == "+" else 0,
        })
    return pd.DataFrame(rows)


def historical_root_decay(hours):
    # Her pozisyonun gerçek 20 pozitifi için +1... kalan pozisyonlarda retention
    records = []
    for date, hour, g in hours:
        g = g.sort_values("minute").reset_index(drop=True)
        sets = [set(x) for x in g["nums"]]
        for start in range(11):
            root = sets[start]
            for step in range(1, 12-start):
                retained = len(root & sets[start+step])
                records.append({
                    "Başlangıç": f":{FULL_HOUR_MINUTES[start]:02d}",
                    "Adım": step,
                    "Hedef": f":{FULL_HOUR_MINUTES[start+step]:02d}",
                    "Kalan +": retained,
                    "Oran %": 100*retained/20,
                })
    return pd.DataFrame(records)



def build_single_txt_report(df, hours, trans, events, exact_stats, count_stats, decay):
    """Tüm gün/saat +/− damar analizini tek TXT içinde birleştirir."""
    out = []
    W = 132
    out.append('=' * W)
    out.append('HIZLI ON — POZİTİF / NEGATİF DAMAR — TÜM GÜNLER / TÜM SAATLER / TEK ÇIKTI')
    out.append('=' * W)
    out.append(f'Çekiliş={len(df)} | Gün={df["date"].nunique()} | Tam 12’li saat={len(hours)} | Saat başı=240 pozitif / 720 negatif')
    out.append('Damar tanımı: Her çekilişin gerçekleşmiş 20 sayısı +, kalan 60 sayı −. Geçişler: ++ / +− / −+ / −−.')
    out.append('')

    if not trans.empty:
        out.append('[A] GENEL GEÇİŞ ÖZETİ')
        out.append('-' * W)
        sm = trans[["++", "+−", "−+", "−−"]].agg(["mean", "std", "min", "max"]).T
        for k, r in sm.iterrows():
            out.append(f'{k:>3} | ort={r["mean"]:.3f} | std={r["std"]:.3f} | min={r["min"]:.0f} | max={r["max"]:.0f}')
        out.append('')

        out.append('[B] DAKİKA GEÇİŞ ORTALAMALARI')
        out.append('-' * W)
        pos = trans.groupby(["from_min", "to_min"])[["++", "+−", "−+", "−−"]].mean().reset_index()
        for _, r in pos.iterrows():
            out.append(f':{int(r.from_min):02d}→:{int(r.to_min):02d} | ++={r["++"]:.3f} | +−={r["+−"]:.3f} | −+={r["−+"]:.3f} | −−={r["−−"]:.3f}')
        out.append('')

    out.append('[C] EXACT İLK3 YÖNLÜ RİTİMLER')
    out.append('-' * W)
    if exact_stats is not None and not exact_stats.empty:
        out.append(exact_stats.round(3).to_csv(index=False).strip())
    out.append('')

    out.append('[D] İLK3 0/3–3/3 ÖZETİ')
    out.append('-' * W)
    if count_stats is not None and not count_stats.empty:
        out.append(count_stats.round(3).to_csv(index=False).strip())
    out.append('')

    if decay is not None and not decay.empty:
        out.append('[E] GERÇEK 20’LİK KÖK DAMAR — İLERİ TAŞINMA ÖZETİ')
        out.append('-' * W)
        agg = decay.groupby(["Başlangıç", "Adım", "Hedef"])["Kalan +"].agg(["count", "mean", "std"]).reset_index()
        for _, r in agg.iterrows():
            out.append(f'{r["Başlangıç"]} +{int(r["Adım"])} → {r["Hedef"]} | n={int(r["count"])} | ort_kalan+={r["mean"]:.3f} | std={r["std"]:.3f}')
        out.append('')

    out.append('[F] GÜN GÜN / SAAT SAAT TAM DAMAR HARİTASI')
    out.append('=' * W)
    by_date = {}
    for date, hour, g in hours:
        by_date.setdefault(date, []).append((hour, g))

    for date in sorted(by_date):
        out.append('')
        out.append('#' * W)
        out.append(f'GÜN {date}')
        out.append('#' * W)
        for hour, g in sorted(by_date[date], key=lambda x: x[0]):
            g = g.sort_values('minute').reset_index(drop=True)
            out.append('')
            out.append(f'--- {date} {hour:02d}:00 | 12 ÇEKİLİŞ ---')
            for _, r in g.iterrows():
                nums = '-'.join(f'{n:02d}' for n in sorted(r['nums']))
                out.append(f':{int(r["minute"]):02d} #{int(r["draw_id"])} | +20={nums}')

            out.append('GEÇİŞLER:')
            tx = trans[(trans['date'] == date) & (trans['hour'] == hour)] if not trans.empty else pd.DataFrame()
            for _, r in tx.iterrows():
                carry = '-'.join(f'{n:02d}' for n in r['carry_nums'])
                drop = '-'.join(f'{n:02d}' for n in r['drop_nums'])
                enter = '-'.join(f'{n:02d}' for n in r['enter_nums'])
                out.append(
                    f':{int(r["from_min"]):02d}→:{int(r["to_min"]):02d} | ++={int(r["++"])} [{carry}] | +−={int(r["+−"])} [{drop}] | −+={int(r["−+"])} [{enter}] | −−={int(r["−−"])}'
                )

            out.append('80 SAYI × 12 ÇEKİLİŞ RİTİMLERİ:')
            ht = hour_number_table(g)
            for _, r in ht.iterrows():
                out.append(
                    f'{int(r["Sayı"]):02d} | {r["12\'li ritim"]} | ilk3={r["İlk3 desen"]} ({int(r["İlk3 +"])}/3)'
                    f' | ikinci3={r["İkinci3 desen"]} ({int(r["İkinci3 +"])}/3) | son6={r["Son6 desen"]} ({int(r["Son6 +"])}/6)'
                    f' | saat+={int(r["Saat toplam +"])}'
                )

    out.append('')
    out.append('=' * W)
    out.append('TEK ÇIKTI SONU')
    out.append('=' * W)
    return '\n'.join(out)

# -----------------------------
# Arayüz
# -----------------------------
st.title("Hızlı On — Pozitif / Negatif Damar Motoru V2")
st.caption("Damar = gerçekleşmiş çekilişteki gerçek 20 pozitif. Motor, bu 20'nin taşınmasını ve 60 negatiften yeni girişleri inceler. Kupon üretmez; mekanik araştırır.")

with st.sidebar:
    st.header("Veri")
    uploaded = st.file_uploader("TXT yükle", type=["txt"])
    url = st.text_input("İstersen GitHub RAW veri.txt adresi", value="")
    st.caption("Öncelik: yüklenen TXT → URL → klasördeki veri.txt / ana analiz TXT")

text = None
source = None
if uploaded is not None:
    text = uploaded.getvalue().decode("utf-8", errors="ignore")
    source = uploaded.name
elif url.strip():
    try:
        text = load_url_text(url.strip())
        source = url.strip()
    except Exception as e:
        st.error(f"URL okunamadı: {e}")
        st.stop()
else:
    text, source = load_default_text()

if not text:
    st.warning("Veri bulunamadı. veri.txt yükle veya GitHub RAW bağlantısını gir.")
    st.stop()

@st.cache_data(show_spinner=False)
def cached_parse(txt):
    return parse_draws(txt)

@st.cache_data(show_spinner=False)
def cached_hours(df_serialized):
    # Streamlit cache için doğrudan dataframe kullanmak yerine yeniden oluşturma yok; bu fonksiyon kullanılmıyor.
    return None

df = cached_parse(text)
semicolon_lines = sum(1 for ln in text.splitlines() if ln.count(";") >= 2)
if df.empty:

    st.error(f"PARSER V2: 0 çekiliş okundu. Metinde {semicolon_lines} adet noktalı-virgüllü aday satır bulundu.")
    with st.expander("Tanılama — ilk 25 satırı göster"):
        st.code("\n".join(text.splitlines()[:25]))
    st.info("PARSER V2 — desteklenen ana biçim: 58929;29.09.2026 16:02;2,4,... (20 sayı). Ayrıca Çekiliş no blokları ve analiz TXT biçimi desteklenir.")
    st.stop()

st.success(f"PARSER V2 OK — {len(df)} çekiliş okundu | noktalı-virgüllü aday satır: {semicolon_lines}")
hours = complete_hours(df)
trans = transition_rows(hours)
events, exact_stats = pattern_stats(hours)
count_stats = first3_count_stats(events) if not events.empty else pd.DataFrame()
decay = historical_root_decay(hours)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
c2.metric("Gün", df["date"].nunique())
c3.metric("Tam 12'li saat", len(hours))
c4.metric("Saat başı durum", "240 + / 720 −")
st.caption(f"Kaynak: {source}")

# Veri doğrulama
bad = df[df["nums"].map(len) != 20]
if len(bad):
    st.warning(f"20 sayı olmayan {len(bad)} çekiliş var.")

TABS = st.tabs([
    "1. Damar Omurgası",
    "2. Saatin 80×12 Haritası",
    "3. İlk3 Yönlü Ritimler",
    "4. Gerçek 20'lik Damar Takibi",
    "5. Geçişler ++ / +− / −+ / −−",
    "6. Dışa Aktar",
])

with TABS[0]:
    st.subheader("Gerçek damar mantığı")
    st.write("Her çekilişte 20 sayı **+**, kalan 60 sayı **−**. Sonraki çekilişte dört gerçek hareket vardır: **++ taşıyan**, **+− sönen**, **−+ yeni giren**, **−− dışarıda kalan**.")
    if not trans.empty:
        summary = trans[["++", "+−", "−+", "−−"]].agg(["mean", "std", "min", "max"]).T
        summary.columns = ["Ortalama", "Std", "Min", "Max"]
        st.dataframe(summary.round(2), use_container_width=True)

        pos = trans.groupby(["from_min", "to_min"])[["++", "+−", "−+", "−−"]].mean().reset_index()
        pos["Geçiş"] = pos.apply(lambda r: f":{int(r.from_min):02d}→:{int(r.to_min):02d}", axis=1)
        st.markdown("**Dakika geçiş ortalamaları**")
        st.dataframe(pos[["Geçiş", "++", "+−", "−+", "−−"]].round(2), use_container_width=True, hide_index=True)

        st.markdown("**Gerçek 20'lik kök damarın ileride ne kadarı tekrar + oluyor?**")
        agg = decay.groupby(["Başlangıç", "Adım", "Hedef"])["Kalan +"].agg(["count", "mean", "std"]).reset_index()
        agg.columns = ["Başlangıç", "Adım", "Hedef", "n", "Ort. kalan +", "Std"]
        st.dataframe(agg.round(2), use_container_width=True, hide_index=True)

with TABS[1]:
    st.subheader("Bir saatin 80 sayı × 12 çekiliş +/− haritası")
    keys = [(d,h) for d,h,_ in hours]
    dates = sorted(set(d for d,_ in keys))
    sel_date = st.selectbox("Gün", dates, index=len(dates)-1, key="map_date")
    hours_for_date = sorted(h for d,h in keys if d == sel_date)
    sel_hour = st.selectbox("Saat", hours_for_date, index=len(hours_for_date)-1, key="map_hour")
    g = next(g for d,h,g in hours if d == sel_date and h == sel_hour)
    tab = hour_number_table(g)

    view = tab[["Sayı"] + MINUTE_LABELS + ["12'li ritim", "İlk3 desen", "İkinci3 desen", "Son6 +", "Saat toplam +"]].copy()
    for m in MINUTE_LABELS:
        view[m] = view[m].map({1:"+", 0:"−"})
    st.dataframe(view, use_container_width=True, height=720, hide_index=True)

    st.markdown("**Bu saatte ilk3 sınıfları**")
    cls = tab.groupby(["İlk3 +", "İlk3 desen"]).agg(n=("Sayı","count"), son6_ort=("Son6 +","mean")).reset_index()
    st.dataframe(cls.round(3), use_container_width=True, hide_index=True)

with TABS[2]:
    st.subheader("İlk3'ü yalnız 1/3–2/3 diye ezme: yönü koru")
    st.write("Örn. **++−**, **+−+**, **−++** üçü de 2/3'tür ama farklı damardır. Bu tabloda ayrı tutulur.")
    st.markdown("**Exact ilk3 desenleri → devam davranışı**")
    st.dataframe(exact_stats.round(2), use_container_width=True, hide_index=True)
    st.markdown("**Sadece 0/3, 1/3, 2/3, 3/3 toplu görünüm**")
    st.dataframe(count_stats.round(2), use_container_width=True, hide_index=True)

    if not events.empty:
        pat = st.selectbox("Bir ilk3 deseni seç", sorted(events["first3"].unique()), index=0)
        x = events[events["first3"] == pat]
        next_cols = [f"m{m:02d}" for m in FULL_HOUR_MINUTES[3:]]
        probs = pd.DataFrame({
            "Dakika": [f":{m:02d}" for m in FULL_HOUR_MINUTES[3:]],
            "+ oranı %": [100*x[c].mean() for c in next_cols],
        })
        st.dataframe(probs.round(2), use_container_width=True, hide_index=True)

with TABS[3]:
    st.subheader("Seçilen geçmiş çekilişin gerçek 20 pozitifi = kök damar")
    keys = [(d,h) for d,h,_ in hours]
    dates = sorted(set(d for d,_ in keys))
    sel_date2 = st.selectbox("Gün", dates, index=len(dates)-1, key="root_date")
    hours_for_date = sorted(h for d,h in keys if d == sel_date2)
    sel_hour2 = st.selectbox("Saat", hours_for_date, index=len(hours_for_date)-1, key="root_hour")
    g2 = next(g for d,h,g in hours if d == sel_date2 and h == sel_hour2).sort_values("minute").reset_index(drop=True)
    start_min = st.selectbox("Kök damar çekilişi", [f":{m:02d}" for m in FULL_HOUR_MINUTES[:-1]], index=0)
    start_idx = FULL_HOUR_MINUTES.index(int(start_min[1:]))
    root = root_damar_tracking(g2, start_idx)

    st.write(f"**{sel_date2} {sel_hour2:02d}{start_min}** çekilişinde + olan gerçek 20 sayının sonraki yolu:")
    st.dataframe(root, use_container_width=True, hide_index=True)

    # Her sonraki adımda kök 20'den kaç kişi kalıyor ve kaç yeni giriş var
    sets = [set(x) for x in g2["nums"]]
    root_set = sets[start_idx]
    flow = []
    for j in range(start_idx, 12):
        curr = sets[j]
        flow.append({
            "Dakika": f":{FULL_HOUR_MINUTES[j]:02d}",
            "Kök 20'den + kalan": len(root_set & curr),
            "Kök dışından +": len(curr - root_set),
        })
    st.dataframe(pd.DataFrame(flow), use_container_width=True, hide_index=True)

with TABS[4]:
    st.subheader("Her ardışık çekilişte dört gerçek hareket")
    if trans.empty:
        st.info("Geçiş bulunamadı.")
    else:
        date_opts = sorted(trans["date"].unique())
        td = st.selectbox("Gün", date_opts, index=len(date_opts)-1, key="tr_date")
        h_opts = sorted(trans[trans["date"] == td]["hour"].unique())
        th = st.selectbox("Saat", h_opts, index=len(h_opts)-1, key="tr_hour")
        x = trans[(trans["date"] == td) & (trans["hour"] == th)].copy()
        x["Geçiş"] = x.apply(lambda r: f":{int(r.from_min):02d}→:{int(r.to_min):02d}", axis=1)
        show = x[["Geçiş", "++", "+−", "−+", "−−", "carry_nums", "drop_nums", "enter_nums"]]
        st.dataframe(show, use_container_width=True, hide_index=True)

with TABS[5]:
    st.subheader("Tek çıktı")
    single_txt = build_single_txt_report(df, hours, trans, events, exact_stats, count_stats, decay)
    st.download_button(
        "TÜM GÜNLER + TÜM SAATLER + TÜM DAMAR ANALİZLERİ — TEK TXT",
        single_txt.encode("utf-8-sig"),
        "HIZLI_ON_POZITIF_NEGATIF_DAMAR_TUM_ANALIZLER_TEK_DOSYA.txt",
        "text/plain",
        use_container_width=True,
    )
    st.caption("Bu tek TXT: genel özet + dakika geçişleri + ilk3 ritimleri + kök damar taşınması + her gün/her saat 12 çekiliş + 80 sayının 12’li +/− ritmini içerir.")

    with st.expander("İstersen ayrı CSV tablolarını da indir"):
        st.download_button("Exact ilk3 ritimleri CSV", exact_stats.to_csv(index=False).encode("utf-8-sig"), "ilk3_exact_ritimler.csv", "text/csv")
        st.download_button("0/3–3/3 özet CSV", count_stats.to_csv(index=False).encode("utf-8-sig"), "ilk3_sinif_ozet.csv", "text/csv")
        st.download_button("Tüm sayı-saat ritimleri CSV", events.to_csv(index=False).encode("utf-8-sig"), "tum_sayi_saat_ritimleri.csv", "text/csv")
        trans_export = trans.copy()
        for c in ["carry_nums", "drop_nums", "enter_nums"]:
            if c in trans_export:
                trans_export[c] = trans_export[c].map(lambda x: "-".join(f"{n:02d}" for n in x))
        st.download_button("Tüm geçişler CSV", trans_export.to_csv(index=False).encode("utf-8-sig"), "tum_gecisler.csv", "text/csv")

st.divider()
st.caption("Araştırma modu: gerçekleşmiş +/− akışını ölçer. Gelecek sonucu veri özelliklerine sızdırmaz; kupon/garanti üretmez.")
