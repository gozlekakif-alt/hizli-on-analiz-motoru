import streamlit as st
import pandas as pd
import numpy as np
import re
from pathlib import Path
from itertools import combinations

st.set_page_config(page_title="Hızlı On — Saatler Arası Dönüşüm Motoru", layout="wide")
st.title("🔄 Hızlı On — 14 Gün Saatler Arası Dönüşüm Motoru")
st.caption("GitHub'daki veri.txt ham verisini otomatik okur. Amaç: saatlik lider kadroların, uyku/dönüşlerin ve aile ağlarının bir sonraki saate nasıl dönüştüğünü ölçmek.")

DATA_FILE = Path(__file__).with_name("veri.txt")

if not DATA_FILE.exists():
    st.error("veri.txt bulunamadı. Bu app dosyası ile veri.txt GitHub deposunda aynı klasörde olmalı.")
    st.stop()

try:
    RAW = DATA_FILE.read_text(encoding="utf-8-sig")
except UnicodeDecodeError:
    RAW = DATA_FILE.read_text(encoding="cp1254")

def parse_data(raw):
    rows = []

    # Ana GitHub biçimi:
    # draw_id;dd.mm.yyyy HH:MM;n1,n2,...,n20
    for line in raw.splitlines():
        line = line.strip()
        if not line or ";" not in line:
            continue
        try:
            draw_id, dt, nums = line.split(";", 2)
            ts = pd.to_datetime(dt.strip(), dayfirst=True)
            ns = [int(x) for x in re.findall(r"\d+", nums)]
            if len(ns) == 20 and all(1 <= x <= 80 for x in ns):
                rows.append((int(draw_id.strip()), ts, ns))
        except Exception:
            pass

    # Alternatif Milli Piyango kopyalama biçimi
    if not rows:
        pat = re.compile(
            r"(?:Çekiliş\s*no\s*:?\s*)?(\d{4,})\s*\n?\s*"
            r"(\d{2}\.\d{2}\.\d{4})\s*[-–]?\s*(\d{2}:\d{2})"
            r"(.*?)(?=(?:Çekiliş\s*no\s*:?\s*)?\d{4,}\s*\n?\s*"
            r"\d{2}\.\d{2}\.\d{4}|$)",
            re.I | re.S
        )
        for m in pat.finditer(raw):
            try:
                draw_id = int(m.group(1))
                ts = pd.to_datetime(f"{m.group(2)} {m.group(3)}", dayfirst=True)
                ns = [int(x) for x in re.findall(
                    r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", m.group(4)
                )][:20]
                if len(ns) == 20:
                    rows.append((draw_id, ts, ns))
            except Exception:
                pass

    df = pd.DataFrame(rows, columns=["draw_id", "time", "numbers"])
    if df.empty:
        return df
    return (
        df.drop_duplicates("draw_id")
          .sort_values("time")
          .reset_index(drop=True)
    )

df = parse_data(RAW)
if df.empty:
    st.error("veri.txt okundu fakat geçerli çekiliş bulunamadı.")
    st.stop()

df["date"] = df["time"].dt.date
df["hour"] = df["time"].dt.hour

st.sidebar.success("Ham veri tanındı: veri.txt")
st.sidebar.write(f"Çekiliş: **{len(df):,}**")
st.sidebar.write(f"Gün: **{df['date'].nunique()}**")
st.sidebar.write(f"İlk: **{df['time'].min()}**")
st.sidebar.write(f"Son: **{df['time'].max()}**")

# 01:xx tek çekiliş olduğu için eşit 12 çekilişlik saat dönüşümlerine sokmuyoruz.
FULL_HOURS = [0] + list(range(7, 24))
TRANSITIONS = [(FULL_HOURS[i], FULL_HOURS[i+1]) for i in range(len(FULL_HOURS)-1)]
# 00 -> 07 gerçek oyun arasıdır; ayrı işaretlenecek.

def state_from_count(c):
    if c <= 1: return "0-1"
    if c == 2: return "2"
    if c <= 4: return "3-4"
    if c == 5: return "5"
    if c == 6: return "6"
    return "7+"

def leader_level(c):
    if c >= 8: return "8+"
    if c == 7: return "7"
    if c == 6: return "6"
    if c == 5: return "5"
    return "0-4"

def transition_type(a, b):
    if a >= 5 and b >= 5: return "LIDER_KORUDU"
    if a >= 5 and b < 5: return "LIDER_DUSTU"
    if a < 5 and b >= 5: return "YENI_LIDER"
    if a <= 1 and b >= 5: return "UYKUDAN_LIDER"
    if b > a: return "YUKSELIS"
    if b < a: return "DUSUS"
    return "SABIT"

def counts_for(daydf, hour):
    sub = daydf[daydf["hour"] == hour]
    out = {n: 0 for n in range(1,81)}
    for nums in sub["numbers"]:
        for n in nums:
            out[n] += 1
    return out, len(sub)

def pair_counts(daydf, hour):
    sub = daydf[daydf["hour"] == hour]
    pc = {}
    for nums in sub["numbers"]:
        for a,b in combinations(sorted(nums),2):
            pc[(a,b)] = pc.get((a,b),0) + 1
    return pc

def recent_hour_history(daydf, target_hour, number):
    # Aynı gün target_hour öncesindeki tam saatlerde sayı kaç kez çıktı?
    vals = []
    for h in FULL_HOURS:
        if h >= target_hour:
            break
        c,_ = counts_for(daydf, h)
        vals.append((h, c[number]))
    return vals

def hours_since_leader(daydf, target_hour, number):
    hist = recent_hour_history(daydf, target_hour, number)
    dist = 0
    for h,c in reversed(hist):
        dist += 1
        if c >= 5:
            return dist
    return np.nan

def hours_since_active(daydf, target_hour, number):
    hist = recent_hour_history(daydf, target_hour, number)
    dist = 0
    for h,c in reversed(hist):
        dist += 1
        if c >= 2:
            return dist
    return np.nan

def build_master(df):
    rows = []
    dates = sorted(df["date"].unique())

    # Önce saat sayımları cache
    count_cache = {}
    pair_cache = {}
    draw_cache = {}
    for d in dates:
        daydf = df[df["date"] == d]
        for h in FULL_HOURS:
            c, nd = counts_for(daydf, h)
            count_cache[(d,h)] = c
            draw_cache[(d,h)] = nd
            pair_cache[(d,h)] = pair_counts(daydf,h)

    for d in dates:
        daydf = df[df["date"] == d]

        for h1,h2 in TRANSITIONS:
            # 00->07 gerçek oyun arası; ayrıca tutulur ama gap etiketi verilir.
            c1 = count_cache[(d,h1)]
            c2 = count_cache[(d,h2)]
            nd1 = draw_cache[(d,h1)]
            nd2 = draw_cache[(d,h2)]
            if nd1 == 0 or nd2 == 0:
                continue

            p1 = pair_cache[(d,h1)]
            p2 = pair_cache[(d,h2)]

            # Saat bazında lider kadrolar
            leaders1 = {n for n in range(1,81) if c1[n] >= 5}
            leaders2 = {n for n in range(1,81) if c2[n] >= 5}

            # Güçlü aileler: aynı saatte en az 2 kez birlikte görünen çiftler
            fam1 = {p for p,v in p1.items() if v >= 2}
            fam2 = {p for p,v in p2.items() if v >= 2}

            for n in range(1,81):
                prev1 = np.nan
                prev2 = np.nan
                prev3 = np.nan
                earlier = [h for h in FULL_HOURS if h < h1]
                if len(earlier) >= 1: prev1 = count_cache[(d,earlier[-1])][n]
                if len(earlier) >= 2: prev2 = count_cache[(d,earlier[-2])][n]
                if len(earlier) >= 3: prev3 = count_cache[(d,earlier[-3])][n]

                # Sayının güçlü çift partnerleri
                partners1 = sorted([
                    b if a == n else a
                    for (a,b) in fam1 if a == n or b == n
                ])
                partners2 = sorted([
                    b if a == n else a
                    for (a,b) in fam2 if a == n or b == n
                ])
                common_partners = sorted(set(partners1) & set(partners2))
                new_partners = sorted(set(partners2) - set(partners1))
                lost_partners = sorted(set(partners1) - set(partners2))

                rows.append({
                    "date": pd.Timestamp(d).strftime("%d.%m.%Y"),
                    "from_hour": f"{h1:02d}:xx",
                    "to_hour": f"{h2:02d}:xx",
                    "transition": f"{h1:02d}->{h2:02d}",
                    "game_pause_bridge": int(h1 == 0 and h2 == 7),
                    "from_draws": nd1,
                    "to_draws": nd2,
                    "number": n,

                    "from_count": c1[n],
                    "to_count": c2[n],
                    "delta": c2[n] - c1[n],
                    "from_state": state_from_count(c1[n]),
                    "to_state": state_from_count(c2[n]),
                    "from_leader_level": leader_level(c1[n]),
                    "to_leader_level": leader_level(c2[n]),
                    "transition_type": transition_type(c1[n], c2[n]),

                    "prev_hour_1_count": prev1,
                    "prev_hour_2_count": prev2,
                    "prev_hour_3_count": prev3,
                    "hours_since_5plus": hours_since_leader(daydf, h2, n),
                    "hours_since_2plus": hours_since_active(daydf, h2, n),

                    "from_is_5plus": int(c1[n] >= 5),
                    "to_is_5plus": int(c2[n] >= 5),
                    "to_is_6plus": int(c2[n] >= 6),
                    "to_is_7plus": int(c2[n] >= 7),
                    "to_is_8plus": int(c2[n] >= 8),

                    "from_leader_roster_size": len(leaders1),
                    "to_leader_roster_size": len(leaders2),
                    "leader_roster_overlap": len(leaders1 & leaders2),
                    "leader_new_entries": len(leaders2 - leaders1),
                    "leader_exits": len(leaders1 - leaders2),

                    "from_strong_partner_count": len(partners1),
                    "to_strong_partner_count": len(partners2),
                    "common_partner_count": len(common_partners),
                    "new_partner_count": len(new_partners),
                    "lost_partner_count": len(lost_partners),
                    "from_partners": ",".join(map(str,partners1)),
                    "to_partners": ",".join(map(str,partners2)),
                    "common_partners": ",".join(map(str,common_partners)),
                    "new_partners": ",".join(map(str,new_partners)),
                    "lost_partners": ",".join(map(str,lost_partners)),
                })

    return pd.DataFrame(rows)

def build_transition_summary(master):
    g = master.groupby("transition", sort=False)
    out = g.agg(
        number_cases=("number","size"),
        leader_kept=("transition_type", lambda s: (s=="LIDER_KORUDU").sum()),
        leader_dropped=("transition_type", lambda s: (s=="LIDER_DUSTU").sum()),
        new_leaders=("transition_type", lambda s: (s=="YENI_LIDER").sum()),
        sleep_to_leader=("transition_type", lambda s: (s=="UYKUDAN_LIDER").sum()),
        to_5plus=("to_is_5plus","sum"),
        to_6plus=("to_is_6plus","sum"),
        to_7plus=("to_is_7plus","sum"),
        to_8plus=("to_is_8plus","sum"),
        mean_delta=("delta","mean"),
        mean_roster_overlap=("leader_roster_overlap","mean"),
        mean_new_entries=("leader_new_entries","mean"),
        mean_exits=("leader_exits","mean"),
        mean_new_partners=("new_partner_count","mean"),
        mean_lost_partners=("lost_partner_count","mean"),
    ).reset_index()
    return out

st.subheader("Veri kontrolü")
c1,c2,c3,c4 = st.columns(4)
c1.metric("Çekiliş", f"{len(df):,}")
c2.metric("Gün", df["date"].nunique())
c3.metric("Sayı görünümü", f"{len(df)*20:,}")
c4.metric("Saat dönüşümü/gün", len(TRANSITIONS))

if st.button("🧬 14 GÜN SAAT DÖNÜŞÜM MASTER OLUŞTUR", type="primary", use_container_width=True):
    with st.spinner("14 gün × saat geçişleri × 80 sayı ve aile ağları işleniyor..."):
        master = build_master(df)
        summary = build_transition_summary(master)

    st.session_state["master"] = master
    st.session_state["summary"] = summary

if "master" in st.session_state:
    master = st.session_state["master"]
    summary = st.session_state["summary"]

    st.success(f"MASTER hazır: {len(master):,} sayı-geçiş vakası.")

    st.subheader("Saatler arası lider dönüşüm özeti")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.subheader("22→23 özel kontrol")
    close = summary[summary["transition"]=="22->23"]
    if not close.empty:
        st.dataframe(close, use_container_width=True, hide_index=True)

    st.subheader("MASTER önizleme")
    st.dataframe(master.head(500), use_container_width=True, hide_index=True)

    csv = master.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ HIZLI_ON_14_GUN_SAAT_DONUSUM_MASTER.csv",
        data=csv,
        file_name="HIZLI_ON_14_GUN_SAAT_DONUSUM_MASTER.csv",
        mime="text/csv",
        use_container_width=True
    )

    summary_csv = summary.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Saat dönüşüm özet CSV",
        data=summary_csv,
        file_name="HIZLI_ON_14_GUN_SAAT_DONUSUM_OZET.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.info(
        "Ana araştırma dosyası MASTER CSV'dir. Bana yalnız MASTER dosyasını atman yeterli. "
        "01:07–06:57 gerçek oyun arasıdır; 00→07 geçişi game_pause_bridge=1 olarak ayrıca işaretlenmiştir."
    )
else:
    st.info("Yukarıdaki tek tuşa bas. App GitHub'daki veri.txt dosyasını doğrudan okuyup dönüşüm MASTER'ını hazırlayacak.")
