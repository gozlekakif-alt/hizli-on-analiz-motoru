from pathlib import Path
from datetime import datetime
import re

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="TEKRAR TEK LAB — Hafif V2",
    page_icon="🔁",
    layout="wide",
)

BASE_FILE = Path(__file__).with_name("veri.txt")

TEKRAR_V2_TRANS_MIN = 0.247
TEKRAR_V2_TRANS_MAX = 0.269
TEKRAR_V2_MIN_STREAK = 3


# ============================================================
# HAFİF VERİ OKUMA
# ============================================================
def parse_line(raw):
    parts = str(raw).strip().split(";")
    if len(parts) != 4:
        return None
    try:
        no = int(parts[0])
        dt = datetime.strptime(f"{parts[1]} {parts[2]}", "%d.%m.%Y %H:%M")
        nums = [int(x) for x in re.findall(r"\d+", parts[3])]
    except Exception:
        return None

    if len(nums) != 20 or len(set(nums)) != 20:
        return None
    if not all(1 <= n <= 80 for n in nums):
        return None

    return [no, dt, sorted(nums)]


@st.cache_data(show_spinner=False)
def parse_text_cached(text):
    rows, invalid = [], []
    for i, raw in enumerate(str(text).splitlines(), 1):
        if not raw.strip():
            continue
        row = parse_line(raw)
        if row is None:
            invalid.append(i)
        else:
            rows.append(row)

    df = pd.DataFrame(rows, columns=["Cekilis_No", "DT", "Nums"])
    if not df.empty:
        df = (
            df.drop_duplicates("Cekilis_No", keep="last")
              .sort_values("Cekilis_No")
              .reset_index(drop=True)
        )
    return df, invalid


class RepeatEngine:
    """Yalnız TEKRAR motorunun ihtiyaç duyduğu hafif veri motoru."""

    def __init__(self, df):
        self.df = df.reset_index(drop=True).copy()
        self.N = len(self.df)
        self.draw_nos = self.df["Cekilis_No"].astype(int).to_numpy()
        self.dts = list(pd.to_datetime(self.df["DT"]))

        self.A = np.zeros((self.N, 80), dtype=np.int8)
        for i, nums in enumerate(self.df["Nums"]):
            self.A[i, np.asarray(nums, dtype=int) - 1] = 1

        # Kaynak sayı -> sonraki sayı geçiş matrisi.
        self.cumT = np.zeros((self.N, 80, 80), dtype=np.uint16)
        self.cumS = np.zeros((self.N, 80), dtype=np.uint16)
        T = np.zeros((80, 80), dtype=np.uint16)
        S = np.zeros(80, dtype=np.uint16)

        for j in range(self.N - 1):
            if self.draw_nos[j + 1] == self.draw_nos[j] + 1:
                src = np.where(self.A[j] == 1)[0]
                dst = np.where(self.A[j + 1] == 1)[0]
                S[src] += 1
                T[np.ix_(src, dst)] += 1
            self.cumT[j + 1] = T
            self.cumS[j + 1] = S


# ============================================================
# TEKRAR ÖZELLİKLERİ
# ============================================================
def repeat_features(engine, t):
    if t < 40:
        return pd.DataFrame()

    A = engine.A
    prev_idx = np.where(A[t - 1] == 1)[0]
    rows = []

    overlaps = []
    for j in range(1, t):
        if engine.draw_nos[j] == engine.draw_nos[j - 1] + 1:
            overlaps.append(int(np.sum(A[j] * A[j - 1])))

    global_repeat = (
        float(np.mean(overlaps[-200:])) / 20.0 if overlaps else 0.25
    )

    TT = engine.cumT[t - 1].astype(float)
    SS = engine.cumS[t - 1].astype(float)

    target_hour = engine.dts[t - 1].hour
    H = A[max(0, t - 160):t].astype(float)
    freq = H.sum(axis=0)

    for idx in prev_idx:
        n = int(idx + 1)

        cases = hits = 0
        recent_cases = recent_hits = 0

        for j in range(max(0, t - 350), t - 1):
            if engine.draw_nos[j + 1] != engine.draw_nos[j] + 1:
                continue
            if A[j, idx]:
                cases += 1
                hits += int(A[j + 1, idx])
                if j >= t - 120:
                    recent_cases += 1
                    recent_hits += int(A[j + 1, idx])

        p_long = (hits + 5 * global_repeat) / max(cases + 5, 1)
        p_recent = (recent_hits + 4 * p_long) / max(recent_cases + 4, 1)

        streak = 0
        for j in range(t - 1, -1, -1):
            if A[j, idx]:
                streak += 1
            else:
                break

        f5 = float(A[max(0, t - 5):t, idx].mean())
        f20 = float(A[max(0, t - 20):t, idx].mean())

        lifts = []
        if len(H):
            for s in prev_idx:
                if s == idx:
                    continue
                both = float(np.sum(H[:, idx] * H[:, s]))
                expected = max((freq[idx] * freq[s]) / max(len(H), 1), 1e-6)
                lifts.append(min(both / expected, 3.0))
        pair_lift = float(np.mean(lifts)) if lifts else 1.0

        trans_same = float(TT[idx, idx] / SS[idx]) if SS[idx] > 0 else 0.0

        hour_cases = hour_hits = 0
        for j in range(1, t):
            if engine.draw_nos[j] != engine.draw_nos[j - 1] + 1:
                continue
            if engine.dts[j].hour != target_hour:
                continue
            if A[j - 1, idx]:
                hour_cases += 1
                hour_hits += int(A[j, idx])

        p_hour = (hour_hits + 3 * p_long) / max(hour_cases + 3, 1)

        rows.append({
            "Sayı": n,
            "streak": int(streak),
            "trans_same": float(trans_same),
            "p_recent": float(p_recent),
            "p_long": float(p_long),
            "p_hour": float(p_hour),
            "pair_lift": float(pair_lift),
            "f5": float(f5),
            "f20": float(f20),
            "cases": int(cases),
            "recent_cases": int(recent_cases),
            "hour_cases": int(hour_cases),
            "global_repeat": float(global_repeat),
        })

    return pd.DataFrame(rows)


def repeat_v2_candidates(engine, t):
    tab = repeat_features(engine, t)
    if tab.empty:
        return [], tab

    tab = tab.copy()
    tab["V2_sinyal"] = (
        (tab["streak"] >= TEKRAR_V2_MIN_STREAK)
        & (tab["trans_same"] >= TEKRAR_V2_TRANS_MIN)
        & (tab["trans_same"] <= TEKRAR_V2_TRANS_MAX)
    )

    sel = sorted(
        tab.loc[tab["V2_sinyal"], "Sayı"].astype(int).unique().tolist()
    )
    return sel, tab.sort_values(
        ["V2_sinyal", "streak", "trans_same"],
        ascending=[False, False, False],
    )


def repeat_v2_walkforward(engine, test_count=250, min_history=140):
    # Yalnız son N hedefi test et; test başlamadan ağır hesap yok.
    all_t = [
        t for t in range(max(min_history, 1), len(engine.A))
        if engine.draw_nos[t] == engine.draw_nos[t - 1] + 1
    ]
    targets = all_t[-min(int(test_count), len(all_t)):]

    draw_rows = []
    candidate_rows = []

    for t in targets:
        picks, tab = repeat_v2_candidates(engine, t)
        actual = set((np.where(engine.A[t] == 1)[0] + 1).tolist())
        hits = sorted(set(picks) & actual)

        selected_tab = tab[tab["V2_sinyal"] == True].copy() if not tab.empty else pd.DataFrame()

        draw_rows.append({
            "Index": int(t),
            "Çekiliş": int(engine.draw_nos[t]),
            "Tarih/Saat": engine.dts[t].strftime("%d.%m.%Y %H:%M"),
            "Eğitim son çekiliş": int(engine.draw_nos[t - 1]),
            "Karar": "KONUŞ" if picks else "PAS",
            "Kupon boyu": len(picks),
            "İsabet": len(hits),
            "Tam isabet": bool(picks and len(hits) == len(picks)),
            "Tahmin": " - ".join(map(str, picks)) if picks else "",
            "Tutan": " - ".join(map(str, hits)) if hits else "",
            "Sızıntı kontrolü": (
                "TEMİZ"
                if int(engine.draw_nos[t - 1]) < int(engine.draw_nos[t])
                else "HATALI"
            ),
        })

        if not tab.empty:
            c = tab.copy()
            c.insert(0, "Index", int(t))
            c.insert(1, "Çekiliş", int(engine.draw_nos[t]))
            c.insert(2, "Tarih/Saat", engine.dts[t].strftime("%d.%m.%Y %H:%M"))
            c["Doğru"] = c["Sayı"].astype(int).isin(actual).astype(int)
            candidate_rows.append(c)

    draw_df = pd.DataFrame(draw_rows)
    cand_df = (
        pd.concat(candidate_rows, ignore_index=True)
        if candidate_rows else pd.DataFrame()
    )
    return draw_df, cand_df


# ============================================================
# ARAYÜZ — AÇILIŞTA TEST ÇALIŞMAZ
# ============================================================
st.title("🔁 TEKRAR TEK LAB — HAFİF V2")
st.caption(
    "Yalnız TEKRAR uzmanı. Uygulama açılırken ağır walk-forward çalışmaz. "
    "Test yalnız TESTİ BAŞLAT düğmesine basınca hesaplanır."
)

if not BASE_FILE.exists():
    st.error("veri.txt bulunamadı. Bu .py ile veri.txt aynı GitHub klasöründe olmalı.")
    st.stop()

raw_text = BASE_FILE.read_text(encoding="utf-8", errors="ignore")
df, invalid_lines = parse_text_cached(raw_text)

if len(df) < 180:
    st.error(f"Yeterli veri yok: {len(df)} çekiliş.")
    st.stop()

st.success(f"Veri hazır: {len(df)} çekiliş")
if invalid_lines:
    st.warning(f"Atlanan bozuk satır: {len(invalid_lines)}")

tests = st.select_slider(
    "Test adedi",
    options=[100, 250, 500, 750],
    value=250,
)

st.info(
    "Dondurulmuş V2 kuralı: son çekilişte bulunan sayı + "
    "streak ≥ 3 + trans_same 0.247–0.269. "
    "Bu testte eşikler değiştirilmez."
)

if "tekrar_v2_draw" not in st.session_state:
    st.session_state["tekrar_v2_draw"] = None
if "tekrar_v2_cand" not in st.session_state:
    st.session_state["tekrar_v2_cand"] = None
if "tekrar_v2_n" not in st.session_state:
    st.session_state["tekrar_v2_n"] = None

if st.button("🚀 TESTİ BAŞLAT", type="primary", use_container_width=True):
    with st.spinner(f"{tests} çekilişlik TEKRAR V2 walk-forward çalışıyor..."):
        eng = RepeatEngine(df)
        draw_df, cand_df = repeat_v2_walkforward(eng, test_count=tests)

    st.session_state["tekrar_v2_draw"] = draw_df
    st.session_state["tekrar_v2_cand"] = cand_df
    st.session_state["tekrar_v2_n"] = tests

draw_df = st.session_state.get("tekrar_v2_draw")
cand_df = st.session_state.get("tekrar_v2_cand")

if isinstance(draw_df, pd.DataFrame) and not draw_df.empty:
    active = draw_df[draw_df["Kupon boyu"] > 0].copy()
    full = active[active["Tam isabet"] == True].copy()

    total_n = int(active["Kupon boyu"].sum()) if len(active) else 0
    total_hit = int(active["İsabet"].sum()) if len(active) else 0
    accuracy = 100.0 * total_hit / max(total_n, 1)

    st.subheader(f"📊 Sonuç — {st.session_state.get('tekrar_v2_n')} test")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("KONUŞ çekilişi", len(active))
    c2.metric("Verilen sayı", total_n)
    c3.metric("Sayı doğruluğu", f"%{accuracy:.2f}")
    c4.metric("Tam kolon", len(full))

    if len(active):
        z0 = int((active["İsabet"] == 0).sum())
        z1 = int((active["İsabet"] == 1).sum())
        st.write(
            f"**KONUŞ oranı:** %{100*len(active)/max(len(draw_df),1):.1f}  •  "
            f"**0 isabet:** {z0}  •  **1 isabet:** {z1}  •  "
            f"**Tam isabet:** {len(full)}"
        )

    st.subheader("KONUŞ olayları")
    st.dataframe(
        active.sort_values("Çekiliş", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ TEST SONUCUNU İNDİR",
        draw_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="TEKRAR_V2_HAFIF_WALKFORWARD.csv",
        mime="text/csv",
        use_container_width=True,
    )

    if isinstance(cand_df, pd.DataFrame) and not cand_df.empty:
        st.download_button(
            "⬇️ ADAY DETAYINI İNDİR",
            cand_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="TEKRAR_V2_ADAY_DETAY.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if st.button("🧹 Test sonucunu temizle", use_container_width=True):
        st.session_state["tekrar_v2_draw"] = None
        st.session_state["tekrar_v2_cand"] = None
        st.session_state["tekrar_v2_n"] = None
        st.rerun()

st.divider()
st.subheader("🎯 Güncel TEKRAR V2 kararı")
try:
    eng_live = RepeatEngine(df)
    picks_now, detail_now = repeat_v2_candidates(eng_live, len(df))
    if picks_now:
        st.success("KONUŞ — " + " - ".join(map(str, picks_now)))
    else:
        st.warning("PAS — V2 koşulunu geçen sayı yok.")

    if not detail_now.empty:
        st.dataframe(
            detail_now.head(20),
            use_container_width=True,
            hide_index=True,
        )
except Exception as e:
    st.info(f"Güncel karar üretilemedi: {e}")
