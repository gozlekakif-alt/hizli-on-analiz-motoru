import io
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

st.set_page_config(page_title="META Tez–Antitez V1", page_icon="🧠", layout="wide")

NUMBERS = np.arange(1, 81)
FEATURE_NAMES = [
    "Frekans 5", "Frekans 10", "Frekans 20", "Frekans 50", "Frekans 100",
    "Dinlenme", "Son çekilişte", "Son 3 yoğunluğu", "Devam serisi",
    "Komşu ±1", "Komşu ±2", "Geçiş olasılığı", "Aynı saat", "Aynı saat dilimi",
    "10'luk bölge basıncı", "Kısa-uzun trend",
]
BASE_FILE = Path(__file__).with_name("veri.txt")


def parse_text(text: str) -> pd.DataFrame:
    rows = []
    for raw in str(text).splitlines():
        p = raw.strip().split(";")
        if len(p) != 4:
            continue
        try:
            no = int(p[0])
            dt = datetime.strptime(f"{p[1]} {p[2]}", "%d.%m.%Y %H:%M")
            nums = [int(x) for x in p[3].split(",")]
        except Exception:
            continue
        if len(nums) == 20 and len(set(nums)) == 20 and all(1 <= x <= 80 for x in nums):
            rows.append([no, dt, sorted(nums)])
    out = pd.DataFrame(rows, columns=["Cekilis_No", "DT", "Nums"])
    if out.empty:
        return out
    return out.drop_duplicates("Cekilis_No", keep="last").sort_values("Cekilis_No").reset_index(drop=True)


def next_draw_dt(dt: datetime) -> datetime:
    if dt.hour == 1 and dt.minute == 2:
        return (dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    cand = dt + timedelta(minutes=5)
    if (cand.hour == 1 and cand.minute > 2) or (2 <= cand.hour < 7):
        return (dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    return cand


class FeatureEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df.reset_index(drop=True).copy()
        self.N = len(df)
        self.draw_nos = self.df["Cekilis_No"].astype(int).to_numpy()
        self.times = [x.strftime("%H:%M") for x in self.df["DT"]]
        self.hours = [x.hour for x in self.df["DT"]]
        self.A = np.zeros((self.N, 80), dtype=np.int8)
        for i, nums in enumerate(self.df["Nums"]):
            self.A[i, np.array(nums, dtype=int) - 1] = 1
        self.cum = np.vstack([np.zeros((1, 80), dtype=np.int32), np.cumsum(self.A, axis=0)])

        # Kümülatif kaynak -> sonraki sayı geçiş matrisi. Sadece gerçekten ardışık çekilişler kullanılır.
        self.cumT = np.zeros((self.N, 80, 80), dtype=np.uint16)
        self.cumS = np.zeros((self.N, 80), dtype=np.uint16)
        T = np.zeros((80, 80), dtype=np.uint16)
        S = np.zeros(80, dtype=np.uint16)
        for j in range(self.N - 1):
            if self.draw_nos[j + 1] == self.draw_nos[j] + 1:
                src = np.where(self.A[j])[0]
                dst = np.where(self.A[j + 1])[0]
                S[src] += 1
                T[np.ix_(src, dst)] += 1
            self.cumT[j + 1] = T
            self.cumS[j + 1] = S

        self.slot_idxs = defaultdict(list)
        self.hour_idxs = defaultdict(list)
        for i, (slot, hour) in enumerate(zip(self.times, self.hours)):
            self.slot_idxs[slot].append(i)
            self.hour_idxs[hour].append(i)

    def window_rate(self, t: int, w: int):
        s = max(0, t - w)
        den = max(t - s, 1)
        return (self.cum[t] - self.cum[s]) / den

    def build(self, t: int, target_time: str):
        """t = hedef satır indeksi. t == N ise gerçek gelecek çekiliş."""
        if t < 5:
            raise ValueError("En az 5 geçmiş çekiliş gerekli.")
        f = {w: self.window_rate(t, w) for w in [5, 10, 20, 50, 100]}
        last = self.A[t - 1]
        prev3 = (self.cum[t] - self.cum[max(0, t - 3)]) / min(3, t)

        gap = np.empty(80, dtype=float)
        streak = np.empty(80, dtype=float)
        for n in range(80):
            prev = np.where(self.A[:t, n])[0]
            raw_gap = t - 1 - prev[-1] if len(prev) else min(t, 30)
            gap[n] = min(raw_gap, 30) / 30.0
            st = 0
            for j in range(t - 1, -1, -1):
                if self.A[j, n]:
                    st += 1
                else:
                    break
            streak[n] = min(st, 5) / 5.0

        nbr1 = np.zeros(80)
        nbr2 = np.zeros(80)
        for n in range(80):
            nbr1[n] = sum(last[x] for x in (n - 1, n + 1) if 0 <= x < 80) / 2.0
            nbr2[n] = sum(last[x] for x in (n - 2, n + 2) if 0 <= x < 80) / 2.0

        # Son 250 gerçek geçişten koşullu olasılık; az örnekte uzun dönem frekansına shrink edilir.
        look = max(0, t - 250)
        end_transition = max(t - 1, 0)
        TT = self.cumT[end_transition] - self.cumT[look]
        SS = self.cumS[end_transition] - self.cumS[look]
        src = np.where(last)[0]
        base = f[100]
        trans = np.zeros(80)
        for n in range(80):
            vals = []
            for s in src:
                ev = int(SS[s])
                if ev > 0:
                    vals.append((int(TT[s, n]) + 3.0 * base[n]) / (ev + 3.0))
            trans[n] = float(np.mean(vals)) if vals else base[n]

        inds = [i for i in self.slot_idxs[target_time] if i < t]
        slot = (self.A[inds].sum(0) + 5 * base) / (len(inds) + 5) if inds else base
        hour = int(target_time[:2])
        inds = [i for i in self.hour_idxs[hour] if i < t]
        hour_rate = (self.A[inds].sum(0) + 10 * base) / (len(inds) + 10) if inds else base

        band5 = np.zeros(80)
        h = self.A[max(0, t - 5):t]
        for n in range(80):
            lo = (n // 10) * 10
            band5[n] = h[:, lo:lo + 10].sum() / max(len(h) * 10, 1)

        trend = f[5] - f[50]
        return np.column_stack([
            f[5], f[10], f[20], f[50], f[100], gap, last, prev3, streak,
            nbr1, nbr2, trans, slot, hour_rate, band5, trend,
        ]).astype(float)


@st.cache_data(show_spinner=False)
def prepare_cached(text: str, min_history: int = 120):
    df = parse_text(text)
    if len(df) < min_history + 20:
        raise ValueError("Model için veri yetersiz.")
    eng = FeatureEngine(df)
    Xs, ys, ts = [], [], []
    for t in range(min_history, len(df)):
        # Ardışık olmayan iki özel boşluğun hedefini eğitimde kullanma.
        if df.iloc[t]["Cekilis_No"] != df.iloc[t - 1]["Cekilis_No"] + 1:
            continue
        Xs.append(eng.build(t, df.iloc[t]["DT"].strftime("%H:%M")))
        ys.append(eng.A[t])
        ts.append(t)
    return df, eng, Xs, ys, ts


def fit_model(Xs, ys, ts, train_end_t, rolling=400):
    pairs = [(X, y, t) for X, y, t in zip(Xs, ys, ts) if t < train_end_t and t >= train_end_t - rolling]
    if len(pairs) < 50:
        pairs = [(X, y, t) for X, y, t in zip(Xs, ys, ts) if t < train_end_t]
    X = np.vstack([p[0] for p in pairs])
    y = np.hstack([p[1] for p in pairs])
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=400, C=0.15))
    model.fit(X, y)
    return model


def backtest(df, eng, Xs, ys, ts, test_draws=200, refit_every=25):
    valid_ts = [t for t in ts if t >= max(300, len(df) - test_draws)]
    records = []
    model = None
    last_fit = None
    lookup = {t: (X, y) for X, y, t in zip(Xs, ys, ts)}
    for t in valid_ts:
        if model is None or last_fit is None or t - last_fit >= refit_every:
            model = fit_model(Xs, ys, ts, t)
            last_fit = t
        X, y = lookup[t]
        p = model.predict_proba(X)[:, 1]
        order = np.argsort(-p)
        rec = {
            "Çekiliş": int(df.iloc[t]["Cekilis_No"]),
            "Tarih/Saat": df.iloc[t]["DT"].strftime("%d.%m.%Y %H:%M"),
        }
        for k in [20, 10, 9, 8, 7, 6, 5, 4, 3]:
            rec[f"Top{k}"] = int(y[order[:k]].sum())
        records.append(rec)
    return pd.DataFrame(records)


def evidence_table(model, X, probs):
    scaler = model.named_steps["standardscaler"]
    clf = model.named_steps["logisticregression"]
    Z = scaler.transform(X)
    contrib = Z * clf.coef_[0]
    rows = []
    for i, n in enumerate(NUMBERS):
        pos = [(FEATURE_NAMES[j], contrib[i, j]) for j in range(len(FEATURE_NAMES)) if contrib[i, j] > 0]
        neg = [(FEATURE_NAMES[j], contrib[i, j]) for j in range(len(FEATURE_NAMES)) if contrib[i, j] < 0]
        pos = sorted(pos, key=lambda x: x[1], reverse=True)
        neg = sorted(neg, key=lambda x: x[1])
        rows.append({
            "Sayı": int(n),
            "META olasılık": round(float(probs[i]) * 100, 2),
            "TEZ": round(sum(v for _, v in pos), 3),
            "ANTİTEZ": round(sum(-v for _, v in neg), 3),
            "En güçlü tez": " | ".join(f"{a} +{v:.2f}" for a, v in pos[:3]) or "—",
            "En güçlü antitez": " | ".join(f"{a} {v:.2f}" for a, v in neg[:3]) or "—",
        })
    return pd.DataFrame(rows).sort_values(["META olasılık", "Sayı"], ascending=[False, True]).reset_index(drop=True)


st.title("🧠 META Tez–Antitez V1 — Tek Merkez / 80 → 20 → Hedef Kolon")
st.caption(
    "Ayrı arama motorları kupon üretmez. Bütün istatistiksel özellikler tek merkezde 1–80'i puanlar; "
    "önce MASTER-20, sonra aynı sıralamadan 3–10 sayılık hedef kolon çıkar."
)

uploaded = st.file_uploader("Veri havuzu (.txt)", type=["txt"])
if uploaded is not None:
    raw_text = uploaded.getvalue().decode("utf-8", errors="ignore")
elif BASE_FILE.exists():
    raw_text = BASE_FILE.read_text(encoding="utf-8", errors="ignore")
else:
    st.error("veri.txt bulunamadı. Veri havuzunu yükle.")
    st.stop()

try:
    with st.spinner("Veri hazırlanıyor ve merkez özellik matrisi kuruluyor..."):
        df, eng, Xs, ys, ts = prepare_cached(raw_text)
except Exception as exc:
    st.error(str(exc))
    st.stop()

last = df.iloc[-1]
next_dt = next_draw_dt(last["DT"])
next_no = int(last["Cekilis_No"]) + 1

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam çekiliş", len(df))
c2.metric("Son çekiliş", int(last["Cekilis_No"]))
c3.metric("Son saat", last["DT"].strftime("%d.%m.%Y %H:%M"))
c4.metric("Hedef", f"#{next_no} — {next_dt.strftime('%H:%M')}")

st.subheader("1️⃣ Walk-forward gerçeklik kontrolü")
test_draws = st.slider("Test çekilişi", 100, min(500, max(100, len(df) - 300)), min(250, max(100, len(df) - 300)), 25)
if st.button("🔬 Walk-forward testi çalıştır", type="primary"):
    with st.spinner("Her hedefte sadece geçmiş bilgi kullanılarak test ediliyor..."):
        bt = backtest(df, eng, Xs, ys, ts, test_draws=test_draws)
    if bt.empty:
        st.warning("Test üretilemedi.")
    else:
        summary = []
        for k in [20, 10, 9, 8, 7, 6, 5, 4, 3]:
            avg = float(bt[f"Top{k}"].mean())
            random_exp = k * 20 / 80
            summary.append({
                "Hedef": k,
                "Ort. isabet": round(avg, 3),
                "Rastgele beklenti": round(random_exp, 3),
                "Net fark": round(avg - random_exp, 3),
                "Maksimum": int(bt[f"Top{k}"].max()),
            })
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
        st.caption(
            "Net fark sıfıra yakınsa modelin geçmişte rastgele seçimden istikrarlı üstünlüğü kanıtlanmamıştır. "
            "Bu tablo programın kendini kandırmasını engelleyen ana frenidir."
        )
        st.dataframe(bt.tail(50).sort_values("Çekiliş", ascending=False), use_container_width=True, hide_index=True)

st.subheader("2️⃣ META MASTER-20")
with st.spinner("Son bilinen çekilişe kadar eğitim + gelecek hedef için tez/antitez puanlama..."):
    final_model = fit_model(Xs, ys, ts, len(df))
    X_next = eng.build(len(df), next_dt.strftime("%H:%M"))
    probs = final_model.predict_proba(X_next)[:, 1]
    evidence = evidence_table(final_model, X_next, probs)

master20 = evidence.head(20)["Sayı"].astype(int).tolist()
st.success("MASTER-20: " + " - ".join(map(str, master20)))

k = st.select_slider("🎯 Hedef kolon büyüklüğü", options=list(range(3, 11)), value=10)
final_coupon = evidence.head(k)["Sayı"].astype(int).tolist()
st.markdown(f"### 🎯 META Hedef {k}: " + " - ".join(map(str, final_coupon)))

st.subheader("3️⃣ İnce eleme — tez / antitez kanıt tablosu")
st.dataframe(evidence.head(30), use_container_width=True, hide_index=True)

with st.expander("📐 Merkezde kullanılan analizler"):
    st.write(
        "Kısa/orta/uzun dönem frekansları (5/10/20/50/100), dinlenme, son çekiliş taşıması, "
        "son 3 yoğunluğu, devam serisi, ±1/±2 komşuluk-blok sinyali, kaynak→sonraki sayı geçiş olasılığı, "
        "aynı saat davranışı, aynı saat dilimi davranışı, 10'luk bölge basıncı ve kısa-uzun trend. "
        "Hepsi ayrı kupon üretmek yerine tek olasılık modelinde birleşir."
    )

st.warning(
    "Bu sistem geçmiş ilişkileri test eder; çekilişler bağımsız/rastgele ise kalıcı tahmin üstünlüğü oluşmayabilir. "
    "Bu yüzden nihai ölçüt tek bir iyi çekiliş değil, walk-forward ortalamasının rastgele beklentiyi aşmasıdır."
)
