import streamlit as st
import pandas as pd
import re
from pathlib import Path
from itertools import combinations

st.set_page_config(page_title="Hızlı On — Saat Dönüşüm Kadavrası", layout="wide")
st.title("🔄 Hızlı On — 14 Gün Saatler Arası Dönüşüm Kadavrası")
st.caption("GitHub'daki veri.txt ham verisini tanır. Günleri tek tek işler; her gün tamamlanınca sonucu biriktirir. Sonunda tek MASTER CSV üretir.")

DATA_FILE = Path(__file__).with_name("veri.txt")
OUT_FILE = Path(__file__).with_name("HIZLI_ON_14_GUN_SAAT_DONUSUM_MASTER.csv")

# 12 çekilişlik tam saatler. 01:xx yalnız 01:02 olduğu için eşit saat analizine alınmaz.
FULL_HOURS = [0] + list(range(7, 24))
TRANSITIONS = [(FULL_HOURS[i], FULL_HOURS[i+1]) for i in range(len(FULL_HOURS)-1)]

@st.cache_data(show_spinner=False)
def load_raw(path_string):
    p = Path(path_string)
    if not p.exists():
        return pd.DataFrame()

    try:
        raw = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raw = p.read_text(encoding="cp1254")

    rows = []
    # Beklenen GitHub formatı:
    # draw_id;dd.mm.yyyy HH:MM;n1,n2,...,n20
    for line in raw.splitlines():
        line = line.strip()
        if not line or ";" not in line:
            continue
        try:
            draw_id, dt, nums = line.split(";", 2)
            ts = pd.to_datetime(dt.strip(), dayfirst=True)
            ns = [int(x) for x in re.findall(r"\d+", nums)]
            if len(ns) == 20 and len(set(ns)) == 20 and all(1 <= x <= 80 for x in ns):
                rows.append((int(draw_id.strip()), ts, ns))
        except Exception:
            pass

    # Alternatif kopyala-yapıştır blok biçimi
    if not rows:
        blocks = re.split(r"(?=Çekiliş\s*no\s*:)", raw, flags=re.I)
        for b in blocks:
            mid = re.search(r"Çekiliş\s*no\s*:?\s*(\d+)", b, flags=re.I)
            mdt = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[-–]?\s*(\d{2}:\d{2})", b)
            if not mid or not mdt:
                continue
            tail = b[mdt.end():]
            ns = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", tail)][:20]
            if len(ns) == 20 and len(set(ns)) == 20:
                try:
                    ts = pd.to_datetime(f"{mdt.group(1)} {mdt.group(2)}", dayfirst=True)
                    rows.append((int(mid.group(1)), ts, ns))
                except Exception:
                    pass

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["draw_id", "time", "numbers"])
    df = df.drop_duplicates("draw_id").sort_values("time").reset_index(drop=True)
    df["date"] = df["time"].dt.date
    df["hour"] = df["time"].dt.hour
    return df

def hour_tables(daydf):
    """Bir günü yalnız bir kez tarar; sayı ve çift tablolarını hazırlar."""
    counts = {h: [0]*81 for h in FULL_HOURS}
    pairs = {h: {} for h in FULL_HOURS}
    draws = {h: 0 for h in FULL_HOURS}

    for row in daydf.itertuples(index=False):
        h = int(row.hour)
        if h not in counts:
            continue
        draws[h] += 1
        nums = sorted(row.numbers)
        for n in nums:
            counts[h][n] += 1
        pc = pairs[h]
        for a,b in combinations(nums, 2):
            pc[(a,b)] = pc.get((a,b), 0) + 1

    return counts, pairs, draws

def state(c):
    if c <= 1: return "0-1"
    if c == 2: return "2"
    if c <= 4: return "3-4"
    if c == 5: return "5"
    if c == 6: return "6"
    return "7+"

def level(c):
    if c >= 8: return "8+"
    if c == 7: return "7"
    if c == 6: return "6"
    if c == 5: return "5"
    return "0-4"

def move_type(a, b):
    if a >= 5 and b >= 5: return "LIDER_KORUDU"
    if a >= 5 and b < 5: return "LIDER_DUSTU"
    if a < 5 and b >= 5:
        if a <= 1: return "UYKUDAN_LIDER"
        return "YENI_LIDER"
    if b > a: return "YUKSELIS"
    if b < a: return "DUSUS"
    return "SABIT"

def process_one_day(daydf):
    counts, pairs, draws = hour_tables(daydf)
    rows = []

    # Her saat/sayı için geçmiş durumları bir defa ön-hesapla.
    history = {}
    for hi, h in enumerate(FULL_HOURS):
        for n in range(1,81):
            prev = [counts[ph][n] for ph in FULL_HOURS[:hi]]
            last5 = None
            last2 = None
            for dist, val in enumerate(reversed(prev), start=1):
                if last5 is None and val >= 5:
                    last5 = dist
                if last2 is None and val >= 2:
                    last2 = dist
                if last5 is not None and last2 is not None:
                    break
            history[(h,n)] = {
                "p1": prev[-1] if len(prev)>=1 else None,
                "p2": prev[-2] if len(prev)>=2 else None,
                "p3": prev[-3] if len(prev)>=3 else None,
                "since5": last5,
                "since2": last2,
            }

    for h1,h2 in TRANSITIONS:
        if draws[h1] == 0 or draws[h2] == 0:
            continue

        c1, c2 = counts[h1], counts[h2]
        leaders1 = {n for n in range(1,81) if c1[n] >= 5}
        leaders2 = {n for n in range(1,81) if c2[n] >= 5}

        # Güçlü aile = saatte en az iki ortak çekiliş.
        fam1 = {p for p,v in pairs[h1].items() if v >= 2}
        fam2 = {p for p,v in pairs[h2].items() if v >= 2}

        partner1 = {n:set() for n in range(1,81)}
        partner2 = {n:set() for n in range(1,81)}
        for a,b in fam1:
            partner1[a].add(b); partner1[b].add(a)
        for a,b in fam2:
            partner2[a].add(b); partner2[b].add(a)

        for n in range(1,81):
            p1 = partner1[n]
            p2 = partner2[n]
            common = p1 & p2
            new = p2 - p1
            lost = p1 - p2
            hist = history[(h1,n)]

            rows.append({
                "date": daydf["time"].iloc[0].strftime("%d.%m.%Y"),
                "transition": f"{h1:02d}->{h2:02d}",
                "from_hour": h1,
                "to_hour": h2,
                "game_pause_bridge": int(h1 == 0 and h2 == 7),
                "from_draws": draws[h1],
                "to_draws": draws[h2],
                "number": n,
                "from_count": c1[n],
                "to_count": c2[n],
                "delta": c2[n]-c1[n],
                "from_state": state(c1[n]),
                "to_state": state(c2[n]),
                "from_leader_level": level(c1[n]),
                "to_leader_level": level(c2[n]),
                "transition_type": move_type(c1[n],c2[n]),
                "prev_hour_1_count": hist["p1"],
                "prev_hour_2_count": hist["p2"],
                "prev_hour_3_count": hist["p3"],
                "hours_since_5plus": hist["since5"],
                "hours_since_2plus": hist["since2"],
                "from_is_5plus": int(c1[n]>=5),
                "to_is_5plus": int(c2[n]>=5),
                "to_is_6plus": int(c2[n]>=6),
                "to_is_7plus": int(c2[n]>=7),
                "to_is_8plus": int(c2[n]>=8),
                "from_leader_roster_size": len(leaders1),
                "to_leader_roster_size": len(leaders2),
                "leader_roster_overlap": len(leaders1 & leaders2),
                "leader_new_entries": len(leaders2 - leaders1),
                "leader_exits": len(leaders1 - leaders2),
                "from_strong_partner_count": len(p1),
                "to_strong_partner_count": len(p2),
                "common_partner_count": len(common),
                "new_partner_count": len(new),
                "lost_partner_count": len(lost),
                "from_partners": ",".join(map(str,sorted(p1))),
                "to_partners": ",".join(map(str,sorted(p2))),
                "common_partners": ",".join(map(str,sorted(common))),
                "new_partners": ",".join(map(str,sorted(new))),
                "lost_partners": ",".join(map(str,sorted(lost))),
            })

    return pd.DataFrame(rows)

df = load_raw(str(DATA_FILE))
if df.empty:
    st.error("veri.txt bulunamadı veya ham veri tanınamadı. GitHub'da app.py ile veri.txt aynı klasörde olmalı.")
    st.stop()

dates = sorted(df["date"].unique())

c1,c2,c3,c4 = st.columns(4)
c1.metric("Çekiliş", f"{len(df):,}")
c2.metric("Gün", len(dates))
c3.metric("Sayı görünümü", f"{len(df)*20:,}")
c4.metric("Geçiş/gün", len(TRANSITIONS))

st.info("Bu hafif sürüm 14 günü aynı anda yüklenmez. Gün gün hesaplar, her günün sonucunu biriktirir ve sonunda tek MASTER oluşturur.")

if st.button("🧬 GÜN GÜN 14 GÜNÜ İŞLE", type="primary", use_container_width=True):
    progress = st.progress(0)
    status = st.empty()
    daily_box = st.empty()
    parts = []

    for i,d in enumerate(dates, start=1):
        label = pd.Timestamp(d).strftime("%d.%m.%Y")
        status.write(f"**{label} işleniyor...** ({i}/{len(dates)})")
        daydf = df[df["date"] == d].copy()
        part = process_one_day(daydf)
        parts.append(part)

        progress.progress(i/len(dates))
        daily_box.success(f"✓ {label} tamamlandı — {len(part):,} sayı-geçiş vakası")

    master = pd.concat(parts, ignore_index=True)
    st.session_state["master_csv"] = master.to_csv(index=False).encode("utf-8-sig")
    st.session_state["master_rows"] = len(master)
    st.session_state["master_preview"] = master.head(300)
    status.success("14 günün tamamı işlendi. Tek MASTER hazır.")

if "master_csv" in st.session_state:
    st.success(f"MASTER: {st.session_state['master_rows']:,} sayı-geçiş vakası")
    st.dataframe(st.session_state["master_preview"], use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ TEK MASTER DOSYAYI İNDİR",
        data=st.session_state["master_csv"],
        file_name="HIZLI_ON_14_GUN_SAAT_DONUSUM_MASTER.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.caption("Bana yalnız bu MASTER CSV'yi atman yeterli.")
