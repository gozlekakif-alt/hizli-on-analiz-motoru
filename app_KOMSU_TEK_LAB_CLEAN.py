from pathlib import Path
import re
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="KOMSU TEK LAB V1",
    page_icon="🧲",
    layout="wide",
)

APP_VERSION = "KOMSU TEK LAB V1 CLEAN"
BASE_FILE = Path(__file__).with_name("veri.txt")


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
    return no, dt, sorted(nums)


def load_data(path):
    if not path.exists():
        raise FileNotFoundError(f"veri.txt bulunamadı: {path}")

    rows = []
    invalid = []
    text = path.read_text(encoding="utf-8", errors="ignore")

    for line_no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        parsed = parse_line(raw)
        if parsed is None:
            invalid.append(line_no)
        else:
            rows.append(parsed)

    df = pd.DataFrame(rows, columns=["Cekilis_No", "DT", "Nums"])
    if df.empty:
        raise ValueError("Geçerli çekiliş bulunamadı.")

    df = (
        df.drop_duplicates("Cekilis_No", keep="last")
          .sort_values("Cekilis_No")
          .reset_index(drop=True)
    )
    return df, invalid


class Engine:
    def __init__(self, df):
        self.df = df.reset_index(drop=True).copy()
        self.N = len(df)
        self.draw_nos = df["Cekilis_No"].astype(int).to_numpy()
        self.dts = list(pd.to_datetime(df["DT"]))

        self.A = np.zeros((self.N, 80), dtype=np.int8)
        for i, nums in enumerate(df["Nums"]):
            self.A[i, np.asarray(nums, dtype=int) - 1] = 1


def komsu_features(engine, t):
    if t < 120:
        return pd.DataFrame()

    A = engine.A
    last = A[t - 1]
    h5 = A[max(0, t - 5):t]
    h20 = A[max(0, t - 20):t]
    rows = []

    for idx in range(80):
        n1 = [j for j in (idx - 1, idx + 1) if 0 <= j < 80]
        n2 = [j for j in (idx - 2, idx + 2) if 0 <= j < 80]

        last_n1 = int(sum(last[j] for j in n1))
        last_n2 = int(sum(last[j] for j in n2))

        near5 = 0.0
        near20 = 0.0
        neighbors = n1 + n2
        for j in neighbors:
            near5 += float(h5[:, j].mean()) if len(h5) else 0.0
            near20 += float(h20[:, j].mean()) if len(h20) else 0.0

        denom = max(len(neighbors), 1)
        near5 /= denom
        near20 /= denom

        cases = 0
        hits = 0
        recent_cases = 0
        recent_hits = 0

        for j in range(max(1, t - 350), t):
            if engine.draw_nos[j] != engine.draw_nos[j - 1] + 1:
                continue

            prev = A[j - 1]
            cond = sum(prev[k] for k in neighbors) > 0
            if not cond:
                continue

            cases += 1
            hits += int(A[j, idx])

            if j >= t - 140:
                recent_cases += 1
                recent_hits += int(A[j, idx])

        base = float(A[max(0, t - 250):t, idx].mean())
        p_hist = (hits + 6.0 * base) / max(cases + 6, 1)
        p_recent = (recent_hits + 5.0 * p_hist) / max(recent_cases + 5, 1)

        rows.append({
            "Sayi": idx + 1,
            "last_n1": last_n1,
            "last_n2": last_n2,
            "near5": near5,
            "near20": near20,
            "p_hist": p_hist,
            "p_recent": p_recent,
            "cases": cases,
            "recent_cases": recent_cases,
            "base": base,
        })

    d = pd.DataFrame(rows)

    def mm(values):
        a = np.asarray(values, dtype=float)
        lo = float(a.min())
        hi = float(a.max())
        if hi <= lo:
            return np.full(len(a), 0.5)
        return (a - lo) / (hi - lo)

    d["recent_n"] = mm(d["p_recent"])
    d["hist_n"] = mm(d["p_hist"])
    d["near5_n"] = mm(d["near5"])
    d["near20_n"] = mm(d["near20"])
    d["last_n"] = mm(d["last_n1"] + 0.6 * d["last_n2"])

    d["KOMSU_skor"] = np.clip(
        0.34 * d["recent_n"]
        + 0.22 * d["hist_n"]
        + 0.18 * d["near5_n"]
        + 0.12 * d["near20_n"]
        + 0.14 * d["last_n"],
        0.0,
        1.0,
    )

    d = d.sort_values(
        ["KOMSU_skor", "p_recent", "last_n1", "last_n2"],
        ascending=False,
    ).reset_index(drop=True)

    d["Sira"] = np.arange(1, len(d) + 1)
    return d


def komsu_walkforward(engine, start_t=140):
    rows = []

    for t in range(max(140, int(start_t)), len(engine.A)):
        if engine.draw_nos[t] != engine.draw_nos[t - 1] + 1:
            continue

        tab = komsu_features(engine, t)
        actual = set((np.where(engine.A[t] == 1)[0] + 1).tolist())

        for _, r in tab.iterrows():
            n = int(r["Sayi"])
            rows.append({
                "Index": int(t),
                "Cekilis": int(engine.draw_nos[t]),
                "Sayi": n,
                "Sira": int(r["Sira"]),
                "KOMSU_skor": float(r["KOMSU_skor"]),
                "last_n1": float(r["last_n1"]),
                "last_n2": float(r["last_n2"]),
                "near5": float(r["near5"]),
                "near20": float(r["near20"]),
                "p_hist": float(r["p_hist"]),
                "p_recent": float(r["p_recent"]),
                "cases": int(r["cases"]),
                "recent_cases": int(r["recent_cases"]),
                "base": float(r["base"]),
                "Dogru": int(n in actual),
            })

    return pd.DataFrame(rows)


def strict_selector(history, target_index, current_tab):
    hist = history[history["Index"] < target_index].copy()

    if len(hist) < 1400:
        return [], pd.DataFrame()

    selected = []
    detail = []

    for _, r in current_tab.iterrows():
        rank = int(r["Sira"])
        score = float(r["KOMSU_skor"])
        n1 = float(r["last_n1"])
        n2 = float(r["last_n2"])
        pr = float(r["p_recent"])

        h = hist[
            (hist["Sira"] == rank)
            & (np.abs(hist["KOMSU_skor"] - score) <= 0.07)
            & (hist["last_n1"] == n1)
            & (np.abs(hist["last_n2"] - n2) <= 1)
            & (np.abs(hist["p_recent"] - pr) <= 0.06)
        ].copy()

        if len(h) < 70:
            h = hist[
                (hist["Sira"] == rank)
                & (np.abs(hist["KOMSU_skor"] - score) <= 0.11)
                & (np.abs(hist["last_n1"] - n1) <= 1)
                & (np.abs(hist["last_n2"] - n2) <= 1)
                & (np.abs(hist["p_recent"] - pr) <= 0.09)
            ].copy()

        ok = False
        acc = np.nan
        first = np.nan
        second = np.nan

        if len(h) >= 70:
            h = h.sort_values("Index")
            mid = len(h) // 2
            first = float(h.iloc[:mid]["Dogru"].mean())
            second = float(h.iloc[mid:]["Dogru"].mean())
            acc = float(h["Dogru"].mean())
            ok = bool(acc >= 0.36 and first >= 0.32 and second >= 0.32)

        if ok:
            selected.append(int(r["Sayi"]))

        detail.append({
            "Sayi": int(r["Sayi"]),
            "Sira": rank,
            "KOMSU_skor": round(score, 4),
            "last_n1": n1,
            "last_n2": n2,
            "p_recent": round(pr, 4),
            "Benzer_gecmis": int(len(h)),
            "Gecmis_dogruluk": round(acc, 4) if np.isfinite(acc) else np.nan,
            "Ilk_yari": round(first, 4) if np.isfinite(first) else np.nan,
            "Son_yari": round(second, 4) if np.isfinite(second) else np.nan,
            "KONUS": bool(ok),
        })

    return sorted(set(selected)), pd.DataFrame(detail)


def strict_walkforward(engine, start_t=140):
    raw = komsu_walkforward(engine, start_t=start_t)
    if raw.empty:
        return pd.DataFrame(), raw

    rows = []

    for t in sorted(raw["Index"].unique()):
        current = komsu_features(engine, int(t))
        picks, _ = strict_selector(raw, int(t), current)
        actual = set((np.where(engine.A[int(t)] == 1)[0] + 1).tolist())
        hits = sorted(set(picks) & actual)

        rows.append({
            "Index": int(t),
            "Cekilis": int(engine.draw_nos[int(t)]),
            "Kupon_boyu": len(picks),
            "Isabet": len(hits),
            "Tam_isabet": bool(picks and len(hits) == len(picks)),
            "Karar": "KONUS" if picks else "PAS",
            "Tahmin": " - ".join(map(str, picks)) if picks else "",
            "Tutan": " - ".join(map(str, hits)) if hits else "",
        })

    return pd.DataFrame(rows), raw


st.title("🧲 KOMSU TEK LAB V1")
st.caption(APP_VERSION)

try:
    df, invalid = load_data(BASE_FILE)
    eng = Engine(df)

    c1, c2, c3 = st.columns(3)
    c1.metric("Gecerli cekilis", len(df))
    c2.metric("Ilk cekilis", int(df["Cekilis_No"].min()))
    c3.metric("Son cekilis", int(df["Cekilis_No"].max()))

    if invalid:
        st.warning(f"Atlanan bozuk satir: {len(invalid)}")

    st.info(
        "KOMSU motoru yuksek skor diye otomatik sayi vermez. "
        "Benzer komsuluk kosulunun gecmiste gercekten calisip calismadigini test eder."
    )

    if st.button("🧲 KOMSU motorunu tek basina test et", type="primary"):
        with st.spinner("Walk-forward testi calisiyor..."):
            strict_df, raw_df = strict_walkforward(eng, start_t=140)

        active = strict_df[strict_df["Kupon_boyu"] > 0].copy()
        full = active[active["Tam_isabet"] == True].copy()

        a, b, c, d = st.columns(4)
        a.metric("KONUS", len(active))
        b.metric("Verilen sayi", int(active["Kupon_boyu"].sum()) if len(active) else 0)
        c.metric(
            "Sayi dogrulugu",
            f"%{100 * active['Isabet'].sum() / max(active['Kupon_boyu'].sum(), 1):.1f}",
        )
        d.metric("Tam kolon", len(full))

        st.subheader("Son 250 karar")
        st.dataframe(
            strict_df.tail(250).sort_values("Cekilis", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "KOMSU TEK LAB CSV indir",
            strict_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="KOMSU_TEK_LAB_WALKFORWARD.csv",
            mime="text/csv",
        )

        st.download_button(
            "KOMSU aday kalibrasyon CSV indir",
            raw_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="KOMSU_ADAY_KALIBRASYON.csv",
            mime="text/csv",
        )

except Exception as exc:
    st.error(f"Hata: {exc}")
