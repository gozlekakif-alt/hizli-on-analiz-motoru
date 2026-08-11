
import base64
import io
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

st.set_page_config(
    page_title="Hızlı On META Tez–Antitez",
    page_icon="🧠",
    layout="wide",
)

APP_VERSION = "META Tez–Antitez V5 — 4 Geçiş Uzmanı Ayrı Kanallar"
BASE_FILE = Path(__file__).with_name("veri.txt")
NUMBERS = np.arange(1, 81)

FEATURE_NAMES = [
    "Frekans 5",
    "Frekans 10",
    "Frekans 20",
    "Frekans 50",
    "Frekans 100",
    "Dinlenme",
    "Son çekilişte",
    "Son 3 yoğunluğu",
    "Devam serisi",
    "Komşu ±1",
    "Komşu ±2",
    "Geçiş olasılığı",
    "Aynı saat",
    "Aynı saat dilimi",
    "10'luk bölge basıncı",
    "Kısa-uzun trend",
    "Son 2 ortaklığı",
    "Son 5 blok komşuluğu",
    "Son 10 bölge eğimi",
    "Tekrar karşı sinyali",
    "V18 Geçiş — Dengeli",
    "V18 Geçiş — Tekrar ağırlıklı",
    "V18 Geçiş — Yerine geçme ağırlıklı",
    "V18 Geçiş — Saat ve sıcaklık",
    "V18 Uzman — Dinlenmiş Dönüş",
    "V18 Uzman — Blok/Mikro-Konum",
    "V18 Uzman — Saat/Faz Genel Güç",
]

# -------------------------------------------------------------------
# Veri okuma / doğrulama
# -------------------------------------------------------------------

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
    if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
        return None
    return [no, dt, sorted(nums)]


def parse_text(text):
    rows = []
    invalid = []
    for i, raw in enumerate(str(text).splitlines(), 1):
        if not raw.strip():
            continue
        row = parse_line(raw)
        if row:
            rows.append(row)
        else:
            invalid.append(i)
    df = pd.DataFrame(rows, columns=["Cekilis_No", "DT", "Nums"])
    if df.empty:
        return df, invalid
    df = (
        df.drop_duplicates("Cekilis_No", keep="last")
          .sort_values("Cekilis_No")
          .reset_index(drop=True)
    )
    return df, invalid


def to_text(df):
    lines = []
    for _, row in df.sort_values("Cekilis_No").iterrows():
        nums = ",".join(str(int(x)) for x in row["Nums"])
        lines.append(
            f"{int(row['Cekilis_No'])};"
            f"{row['DT'].strftime('%d.%m.%Y')};"
            f"{row['DT'].strftime('%H:%M')};{nums}"
        )
    return "\n".join(lines) + "\n"


def extract_20_numbers(text):
    nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", str(text))]
    # Tarih/saat/çekiliş no girilmişse başlık satırlarını silip tekrar dene
    if len(nums) != 20:
        cleaned = re.sub(r"(?mi)^\s*Çekiliş\s*no\s*:\s*\d+\s*$", " ", str(text))
        cleaned = re.sub(r"(?mi)^\s*\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}:\d{2}\s*$", " ", cleaned)
        nums = [int(x) for x in re.findall(r"(?m)^\s*(\d{1,2})\s*$", cleaned)]
    nums = [x for x in nums if 1 <= x <= 80]
    if len(nums) == 20 and len(set(nums)) == 20:
        return sorted(nums)
    return None


def next_draw_dt(dt):
    if dt.hour == 1 and dt.minute == 2:
        return (dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    cand = dt + timedelta(minutes=5)
    if (cand.hour == 1 and cand.minute > 2) or (2 <= cand.hour < 7):
        return (dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    return cand


def missing_draws(df):
    if df.empty:
        return []
    lo = int(df["Cekilis_No"].min())
    hi = int(df["Cekilis_No"].max())
    have = set(df["Cekilis_No"].astype(int))
    return [x for x in range(lo, hi + 1) if x not in have]


# -------------------------------------------------------------------
# GitHub kalıcı kayıt (Secrets varsa)
# -------------------------------------------------------------------

def github_settings():
    try:
        gh = st.secrets["github"]
        return {
            "token": gh["token"],
            "owner": gh.get("owner", "gozlekakif-alt"),
            "repo": gh.get("repo", "hizli-on-analiz-motoru"),
            "branch": gh.get("branch", "main"),
            "path": gh.get("data_path", "veri.txt"),
        }
    except Exception:
        return None


def github_headers(token):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_get(settings):
    url = f"https://api.github.com/repos/{settings['owner']}/{settings['repo']}/contents/{settings['path']}"
    r = requests.get(
        url,
        headers=github_headers(settings["token"]),
        params={"ref": settings["branch"]},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"GitHub veri.txt okunamadı: {r.status_code}")
    p = r.json()
    content = base64.b64decode(p["content"]).decode("utf-8", errors="ignore")
    return content, p["sha"]


def github_save(settings, text, message):
    current, sha = github_get(settings)
    url = f"https://api.github.com/repos/{settings['owner']}/{settings['repo']}/contents/{settings['path']}"
    payload = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": settings["branch"],
    }
    r = requests.put(
        url,
        headers=github_headers(settings["token"]),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub kayıt hatası: {r.status_code} {r.text[:250]}")
    return r.json()


# -------------------------------------------------------------------
# Merkezi özellik motoru
# -------------------------------------------------------------------

class MetaFeatureEngine:
    def __init__(self, df):
        self.df = df.reset_index(drop=True).copy()
        self.N = len(self.df)
        self.draw_nos = self.df["Cekilis_No"].astype(int).to_numpy()
        self.times = [x.strftime("%H:%M") for x in self.df["DT"]]
        self.hours = [x.hour for x in self.df["DT"]]

        self.A = np.zeros((self.N, 80), dtype=np.int8)
        for i, nums in enumerate(self.df["Nums"]):
            self.A[i, np.array(nums, dtype=int) - 1] = 1
        self.cum = np.vstack([
            np.zeros((1, 80), dtype=np.int32),
            np.cumsum(self.A, axis=0)
        ])

        # Gerçek ardışık çekilişlerden kaynak -> sonraki sayı matrisi.
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

    def window_rate(self, t, w):
        s = max(0, t - w)
        den = max(t - s, 1)
        return (self.cum[t] - self.cum[s]) / den

    @staticmethod
    def _minmax01(arr):
        arr = np.asarray(arr, dtype=float)
        lo = float(np.nanmin(arr)) if len(arr) else 0.0
        hi = float(np.nanmax(arr)) if len(arr) else 0.0
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            return np.full_like(arr, 0.5, dtype=float)
        return np.clip((arr - lo) / (hi - lo), 0.0, 1.0)

    def _v18_rest_return_expert(self, t, last):
        """
        V18.5.6.6'daki dinlenmiş-dönüş fikrinin sızıntısız META kanalı.
        Yalnız A[:t] kullanır. Mevcut dinlenmeyi sayının kendi geçmiş dönüş
        aralığıyla karşılaştırır; son çekilişte bulunan sayıları baskılar.
        """
        score = np.zeros(80, dtype=float)
        for n in range(80):
            seen = np.where(self.A[:t, n] == 1)[0]
            if len(seen):
                current_gap = t - 1 - int(seen[-1])
            else:
                current_gap = min(t, 30)

            if last[n] > 0:
                score[n] = 0.0
                continue

            if len(seen) >= 3:
                intervals = np.diff(seen)
                expected_rest = max(float(np.mean(intervals)) - 1.0, 0.0)
                cycle_fit = np.exp(
                    -abs(float(current_gap) - expected_rest) / (expected_rest + 2.0)
                )
            else:
                cycle_fit = 0.5

            if current_gap <= 2:
                gap_fit = 0.72
            elif current_gap <= 5:
                gap_fit = 1.00
            elif current_gap <= 10:
                gap_fit = 0.92
            else:
                gap_fit = 0.74

            score[n] = 0.82 * cycle_fit + 0.18 * gap_fit
        return np.clip(score, 0.0, 1.0)

    def _v18_block_expert(self, t, block_neighborhood, band5, region_trend):
        """
        V18'in blok/mikro-konum fikrini 1–80 uzman puanına çevirir.
        Son 100 geçmiş çekilişte gerçek komşu-blok üyeliği + yakın dönem
        blok çevresi + 10'luk bölge basıncı birlikte değerlendirilir.
        """
        h = self.A[max(0, t - 100):t]
        hist = np.zeros(80, dtype=float)
        if len(h):
            for n in range(80):
                left = h[:, n - 1] if n > 0 else 0
                right = h[:, n + 1] if n < 79 else 0
                own = h[:, n]
                hist[n] = float(np.sum(own * (left + right)))
        hist_n = self._minmax01(hist)
        near_n = self._minmax01(block_neighborhood)
        band_n = self._minmax01(band5)
        trend_n = self._minmax01(region_trend)
        return np.clip(
            0.42 * hist_n + 0.28 * near_n + 0.18 * band_n + 0.12 * trend_n,
            0.0, 1.0
        )

    def _v18_clock_general_expert(
        self, f10, f25, f50, f100, cycle_fit, repeat_rate,
        pair_strength, same_slot, same_hour, block_score
    ):
        """
        V18 intelligent_score_table mantığının META uzman kanalı.
        Saat/faz ana eksendir; kısa/uzun frekans, dönüş uyumu, tekrar,
        birlikte-gelme ve blok desteğiyle tek 0–1 skor üretir.
        """
        parts = {
            "f10": self._minmax01(f10),
            "f25": self._minmax01(f25),
            "f50": self._minmax01(f50),
            "f100": self._minmax01(f100),
            "cycle": self._minmax01(cycle_fit),
            "repeat": self._minmax01(repeat_rate),
            "pair": self._minmax01(pair_strength),
            "slot": self._minmax01(same_slot),
            "hour": self._minmax01(same_hour),
            "block": self._minmax01(block_score),
        }
        return np.clip(
            0.11 * parts["f10"]
            + 0.10 * parts["f25"]
            + 0.08 * parts["f50"]
            + 0.06 * parts["f100"]
            + 0.13 * parts["cycle"]
            + 0.09 * parts["repeat"]
            + 0.12 * parts["pair"]
            + 0.10 * parts["slot"]
            + 0.12 * parts["hour"]
            + 0.09 * parts["block"],
            0.0, 1.0
        )

    def build(self, t, target_time):
        if t < 10:
            raise ValueError("En az 10 geçmiş çekiliş gerekir.")

        f = {w: self.window_rate(t, w) for w in [5, 10, 20, 25, 50, 100]}
        last = self.A[t - 1]
        prev2 = (self.cum[t] - self.cum[max(0, t - 2)]) / min(2, t)
        prev3 = (self.cum[t] - self.cum[max(0, t - 3)]) / min(3, t)

        gap = np.zeros(80, dtype=float)
        streak = np.zeros(80, dtype=float)
        for n in range(80):
            seen = np.where(self.A[:t, n])[0]
            raw_gap = t - 1 - seen[-1] if len(seen) else min(t, 30)
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
            n1 = [x for x in (n - 1, n + 1) if 0 <= x < 80]
            n2 = [x for x in (n - 2, n + 2) if 0 <= x < 80]
            nbr1[n] = sum(last[x] for x in n1) / max(len(n1), 1)
            nbr2[n] = sum(last[x] for x in n2) / max(len(n2), 1)

        # Son 250 gerçek geçişten koşullu olasılık.
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
                    vals.append((int(TT[s, n]) + 4.0 * base[n]) / (ev + 4.0))
            trans[n] = float(np.mean(vals)) if vals else base[n]

        # V18.5.13 geçiş kuponundaki dört profil için ortak ham bileşenler.
        transition_coverage = np.zeros(80, dtype=float)
        for n in range(80):
            transition_coverage[n] = sum(1 for source_n in src if int(SS[source_n]) > 0 and int(TT[source_n, n]) > 0)
        trans_lift = trans / np.maximum(base, 1e-6)
        transition_score100 = 100.0 * (0.50*self._minmax01(trans) + 0.30*self._minmax01(trans_lift) + 0.20*self._minmax01(transition_coverage))

        inds = [i for i in self.slot_idxs[target_time] if i < t]
        same_slot = (self.A[inds].sum(0) + 8 * base) / (len(inds) + 8) if inds else base

        hour = int(target_time[:2])
        inds = [i for i in self.hour_idxs[hour] if i < t]
        same_hour = (self.A[inds].sum(0) + 12 * base) / (len(inds) + 12) if inds else base

        band5 = np.zeros(80)
        h5 = self.A[max(0, t - 5):t]
        for n in range(80):
            lo = (n // 10) * 10
            band5[n] = h5[:, lo:lo + 10].sum() / max(len(h5) * 10, 1)

        # Son 5 çekilişte komşu/blok çevresi.
        block_neighborhood = np.zeros(80)
        for row in h5:
            active = np.where(row)[0]
            for a in active:
                for d in (-2, -1, 1, 2):
                    b = a + d
                    if 0 <= b < 80:
                        block_neighborhood[b] += 1
        block_neighborhood /= max(len(h5) * 4, 1)

        # Son 10 bölgesel eğim: sayının kendi 10'luk bölgesinin son5-son10 değişimi.
        h10 = self.A[max(0, t - 10):t]
        region_trend = np.zeros(80)
        for n in range(80):
            lo = (n // 10) * 10
            recent = h5[:, lo:lo + 10].mean() if len(h5) else 0
            medium = h10[:, lo:lo + 10].mean() if len(h10) else 0
            region_trend[n] = recent - medium

        trend = f[5] - f[50]

        # Aşırı tekrarın antitez tarafını öğrenebilmesi için ayrı özellik.
        repeat_counter = last * np.clip(f[5] - f[20], 0, None)

        # V18 uzman 2: Dinlenmiş dönüş.
        v18_rest = self._v18_rest_return_expert(t, last)

        # V18 uzman 3: Blok / mikro-konum.
        v18_block = self._v18_block_expert(
            t, block_neighborhood, band5, region_trend
        )

        # V18 intelligent_score_table için gereken sızıntısız yardımcı kanallar.
        repeat_cases = np.zeros(80, dtype=float)
        repeat_hits = np.zeros(80, dtype=float)
        for j in range(max(0, t - 250), t - 1):
            cur = self.A[j]
            nxt = self.A[j + 1]
            repeat_cases += cur
            repeat_hits += cur * nxt
        repeat_rate = repeat_hits / np.maximum(repeat_cases, 1.0)

        # Birlikte-gelme gücü: son 100 çekilişte sayının diğer sayılarla eşleşme yoğunluğu.
        h100 = self.A[max(0, t - 100):t]
        if len(h100):
            pair_strength = np.zeros(80, dtype=float)
            row_sizes = h100.sum(axis=1)
            for n in range(80):
                pair_strength[n] = float(np.sum(h100[:, n] * np.maximum(row_sizes - 1, 0)))
        else:
            pair_strength = np.zeros(80, dtype=float)

        cycle_fit = np.zeros(80, dtype=float)
        for n in range(80):
            seen = np.where(self.A[:t, n] == 1)[0]
            current_gap = t - 1 - int(seen[-1]) if len(seen) else min(t, 30)
            if len(seen) >= 3:
                expected_rest = max(float(np.mean(np.diff(seen))) - 1.0, 0.0)
                cycle_fit[n] = np.exp(
                    -abs(float(current_gap) - expected_rest) / (expected_rest + 2.0)
                )
            else:
                cycle_fit[n] = 0.5

        # V18 uzman 4: Saat/Faz + Genel Güç.
        v18_clock_general = self._v18_clock_general_expert(
            f[10], f[25], f[50], f[100], cycle_fit, repeat_rate, pair_strength, same_slot, same_hour, v18_block
        )

        # V18.5.13 geçiş kuponundaki dört profil ayrı 1–80 kanalıdır; kupon üretmez.
        general100 = 100.0*self._minmax01(0.35*self._minmax01(f[10])+0.25*self._minmax01(f[50])+0.20*self._minmax01(cycle_fit)+0.20*self._minmax01(pair_strength))
        hybrid100 = np.clip(0.36*transition_score100+0.20*general100+0.12*(100*self._minmax01(repeat_rate))+0.12*(100*self._minmax01(same_hour))+0.10*(100*self._minmax01(pair_strength))+0.10*(100*self._minmax01(cycle_fit)),0,100)
        repeat_bonus = 12.0*(last>0).astype(float)
        replace_bonus = 10.0*(last<=0).astype(float)
        v18_gecis_dengeli = self._minmax01(hybrid100)
        v18_gecis_tekrar = self._minmax01(0.50*hybrid100+0.25*(100*self._minmax01(repeat_rate))+0.15*general100+0.10*transition_score100+repeat_bonus)
        v18_gecis_yerine = self._minmax01(0.50*hybrid100+0.25*transition_score100+0.15*np.clip(trans_lift,0,5)*20+0.10*transition_coverage+replace_bonus)
        v18_gecis_saat = self._minmax01(0.45*hybrid100+0.20*general100+0.18*(100*self._minmax01(same_hour))+0.12*(100*self._minmax01(f[10]))+0.05*(100*self._minmax01(cycle_fit)))

        return np.column_stack([
            f[5], f[10], f[20], f[50], f[100],
            gap, last, prev3, streak,
            nbr1, nbr2, trans, same_slot, same_hour,
            band5, trend, prev2, block_neighborhood,
            region_trend, repeat_counter,
            v18_gecis_dengeli, v18_gecis_tekrar, v18_gecis_yerine, v18_gecis_saat,
            v18_rest, v18_block, v18_clock_general,
        ]).astype(float)


@st.cache_data(show_spinner=False)
def prepare_cached(text, min_history=120):
    df, invalid = parse_text(text)
    if len(df) < min_history + 30:
        raise ValueError("Model için yeterli veri yok.")
    eng = MetaFeatureEngine(df)
    Xs, ys, ts = [], [], []
    for t in range(min_history, len(df)):
        # Eksik çekiliş sıçramalarında hedef eğitimini kullanma.
        if int(df.iloc[t]["Cekilis_No"]) != int(df.iloc[t - 1]["Cekilis_No"]) + 1:
            continue
        Xs.append(eng.build(t, df.iloc[t]["DT"].strftime("%H:%M")))
        ys.append(eng.A[t])
        ts.append(t)
    return df, eng, Xs, ys, ts, invalid


def fit_model(Xs, ys, ts, train_end_t, rolling=450):
    pairs = [
        (X, y, t)
        for X, y, t in zip(Xs, ys, ts)
        if t < train_end_t and t >= train_end_t - rolling
    ]
    if len(pairs) < 60:
        pairs = [(X, y, t) for X, y, t in zip(Xs, ys, ts) if t < train_end_t]
    if not pairs:
        raise ValueError("Model eğitimi için yeterli ardışık geçmiş yok.")
    X = np.vstack([p[0] for p in pairs])
    y = np.hstack([p[1] for p in pairs])
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=500,
            C=0.12,
            class_weight=None,
        ),
    )
    model.fit(X, y)
    return model


def predict_table(model, X):
    p = model.predict_proba(X)[:, 1]
    scaler = model.named_steps["standardscaler"]
    clf = model.named_steps["logisticregression"]
    Z = scaler.transform(X)
    contrib = Z * clf.coef_[0]

    rows = []
    for i, n in enumerate(NUMBERS):
        pos = [(FEATURE_NAMES[j], contrib[i, j]) for j in range(len(FEATURE_NAMES)) if contrib[i, j] > 0]
        neg = [(FEATURE_NAMES[j], contrib[i, j]) for j in range(len(FEATURE_NAMES)) if contrib[i, j] < 0]
        pos.sort(key=lambda x: x[1], reverse=True)
        neg.sort(key=lambda x: x[1])
        tez = sum(v for _, v in pos)
        antitez = sum(-v for _, v in neg)
        rows.append({
            "Sıra": 0,
            "Sayı": int(n),
            "META %": round(float(p[i]) * 100, 2),
            "TEZ": round(float(tez), 3),
            "ANTİTEZ": round(float(antitez), 3),
            "Net Kanıt": round(float(tez - antitez), 3),
            "En güçlü tez": " | ".join(f"{a} +{v:.2f}" for a, v in pos[:4]) or "—",
            "En güçlü antitez": " | ".join(f"{a} {v:.2f}" for a, v in neg[:4]) or "—",
        })
    out = pd.DataFrame(rows).sort_values(
        ["META %", "Net Kanıt", "Sayı"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    out["Sıra"] = np.arange(1, len(out) + 1)
    return out


def transition_expert_diagnostic(df, test_count=100, min_train=120):
    if len(df) <= min_train: return pd.DataFrame(), pd.DataFrame()
    engine=MetaFeatureEngine(df)
    cols={p:FEATURE_NAMES.index(n) for p,n in {
        "Dengeli":"V18 Geçiş — Dengeli", "Tekrar ağırlıklı":"V18 Geçiş — Tekrar ağırlıklı",
        "Yerine geçme ağırlıklı":"V18 Geçiş — Yerine geçme ağırlıklı", "Saat ve sıcaklık":"V18 Geçiş — Saat ve sıcaklık"}.items()}
    rows=[]; start=max(min_train,len(df)-int(test_count))
    for t in range(start,len(df)):
        X=engine.build(t,df.iloc[t]["DT"].strftime("%H:%M")); actual=set(df.iloc[t]["Nums"])
        for profile,c in cols.items():
            order=np.argsort(-X[:,c],kind="mergesort"); top20=[int(i+1) for i in order[:20]]; top10=[int(i+1) for i in order[:10]]
            rows.append({"Çekiliş":int(df.iloc[t]["Cekilis_No"]),"Eğitim son çekiliş":int(df.iloc[t-1]["Cekilis_No"]),"Profil":profile,"Top20":len(actual&set(top20)),"Top10":len(actual&set(top10)),"Top20 sayılar":" - ".join(map(str,top20)),"Top10 sayılar":" - ".join(map(str,top10))})
    d=pd.DataFrame(rows)
    if d.empty:return d,pd.DataFrame()
    sm=d.groupby("Profil",as_index=False).agg(Test=("Çekiliş","count"),Top20_Ort=("Top20","mean"),Top10_Ort=("Top10","mean"),Top20_Maks=("Top20","max"),Top10_Maks=("Top10","max"))
    sm["Top20_Net"]=(sm["Top20_Ort"]-5).round(3); sm["Top10_Net"]=(sm["Top10_Ort"]-2.5).round(3); sm["Top20_Ort"]=sm["Top20_Ort"].round(3); sm["Top10_Ort"]=sm["Top10_Ort"].round(3)
    return d,sm.sort_values(["Top20_Net","Top10_Net"],ascending=False)


def backtest(df, Xs, ys, ts, test_draws=250, refit_every=1):
    """
    SIKI WALK-FORWARD:
    Hedef t iken model yalnız t'den ÖNCEKİ hedef örnekleriyle eğitilir.
    Tahmin önce üretilir/kilitlenir; gerçek y yalnız puanlama aşamasında açılır.
    refit_every=1 varsayılanı denetimi en açık hale getirir.
    """
    valid_ts = [t for t in ts if t >= max(300, len(df) - test_draws)]
    lookup = {t: (X, y) for X, y, t in zip(Xs, ys, ts)}
    records = []
    model = None
    last_fit = None

    for t in valid_ts:
        target_no = int(df.iloc[t]["Cekilis_No"])
        train_last_no = int(df.iloc[t - 1]["Cekilis_No"])

        # Güvenlik freni: hedef çekiliş eğitim geçmişinin hemen sonrasında olmalı.
        if target_no != train_last_no + 1:
            continue

        if model is None or last_fit is None or (t - last_fit) >= refit_every:
            # fit_model içinde yalnız sample_t < t kullanılır.
            model = fit_model(Xs, ys, ts, train_end_t=t)
            last_fit = t

        X_target, y_hidden = lookup[t]

        # 1) GERÇEĞİ AÇMADAN tahmin üret ve dondur.
        p = model.predict_proba(X_target)[:, 1]
        order = np.argsort(-p)
        ranked_nums = (order + 1).astype(int)
        locked20 = ranked_nums[:20].tolist()
        locked10 = ranked_nums[:10].tolist()
        locked9 = ranked_nums[:9].tolist()
        locked8 = ranked_nums[:8].tolist()
        locked7 = ranked_nums[:7].tolist()
        locked6 = ranked_nums[:6].tolist()
        locked5 = ranked_nums[:5].tolist()
        locked4 = ranked_nums[:4].tolist()
        locked3 = ranked_nums[:3].tolist()

        # 2) Ancak şimdi gerçek sonucu puanlama için aç.
        actual = (np.where(y_hidden == 1)[0] + 1).astype(int).tolist()
        actual_set = set(actual)

        rec = {
            "Çekiliş": target_no,
            "Eğitim son çekiliş": train_last_no,
            "Tarih/Saat": df.iloc[t]["DT"].strftime("%d.%m.%Y %H:%M"),
            "MASTER-20 tahmin": " - ".join(map(str, locked20)),
            "Hedef-10 tahmin": " - ".join(map(str, locked10)),
            "Gerçek sonuç": " - ".join(map(str, actual)),
            "MASTER-20 tutan": " - ".join(map(str, sorted(actual_set & set(locked20)))),
            "Hedef-10 tutan": " - ".join(map(str, sorted(actual_set & set(locked10)))),
            "MASTER-20 kaçan gerçek": " - ".join(map(str, sorted(actual_set - set(locked20)))),
        }

        locked_by_k = {
            20: locked20, 10: locked10, 9: locked9, 8: locked8, 7: locked7,
            6: locked6, 5: locked5, 4: locked4, 3: locked3,
        }
        for k, picks in locked_by_k.items():
            rec[f"Top{k}"] = len(actual_set & set(picks))

        # Denetim damgası: eğitim son çekilişi hedefin altında değilse kayıt geçersizdir.
        rec["Sızıntı kontrolü"] = "TEMİZ" if train_last_no < target_no else "HATALI"
        records.append(rec)

    return pd.DataFrame(records)

def summarize_backtest(bt):
    rows = []
    for k in [20, 10, 9, 8, 7, 6, 5, 4, 3]:
        col = f"Top{k}"
        avg = float(bt[col].mean())
        random_exp = k * 20 / 80
        rows.append({
            "Hedef": k,
            "Ort. İsabet": round(avg, 3),
            "Rastgele Beklenti": round(random_exp, 3),
            "Net Fark": round(avg - random_exp, 3),
            "Maksimum": int(bt[col].max()),
            f"{max(1, k//2)}+ oranı %": round(float((bt[col] >= max(1, k//2)).mean()) * 100, 1),
        })
    return pd.DataFrame(rows)


# -------------------------------------------------------------------
# Uygulama
# -------------------------------------------------------------------

st.title("🧠 Hızlı On — META V5 + V18 Dört Geçiş Uzmanı")
st.caption(
    "Tek beyin mimarisi: ayrı arama motorları ayrı kupon üretmez. "
    "Bütün analizler 1–80 arasındaki sayıları aynı merkezde değerlendirir; "
    "önce MASTER-20, sonra istediğin 3–10 sayılık hedef kolon çıkar."
)

# Veri kaynağı
with st.expander("📥 Veri havuzu / hızlı çekiliş ekleme", expanded=False):
    uploaded = st.file_uploader("Yeni veri.txt yükle", type=["txt"])
    base_text = ""
    if BASE_FILE.exists():
        base_text = BASE_FILE.read_text(encoding="utf-8", errors="ignore")
    if uploaded is not None:
        incoming = uploaded.getvalue().decode("utf-8", errors="ignore")
        # yüklenen dosya ana kaynak olur
        base_text = incoming

    if not base_text:
        st.error("Repo içinde veri.txt bulunamadı. Önce veri.txt yükle.")
        st.stop()

    temp_df, _ = parse_text(base_text)
    if temp_df.empty:
        st.error("Veri havuzu okunamadı.")
        st.stop()

    last0 = temp_df.iloc[-1]
    suggested_no = int(last0["Cekilis_No"]) + 1
    suggested_dt = next_draw_dt(last0["DT"])

    st.markdown("#### ⚡ Hızlı yeni çekiliş")
    c1, c2, c3 = st.columns(3)
    draw_no = c1.number_input("Çekiliş no", min_value=1, value=suggested_no, step=1)
    draw_date = c2.text_input("Tarih", value=suggested_dt.strftime("%d.%m.%Y"))
    draw_time = c3.text_input("Saat", value=suggested_dt.strftime("%H:%M"))

    pasted = st.text_area(
        "20 sayıyı yapıştır",
        placeholder="Örn:\n2\n6\n13\n...\nveya virgülle 20 sayı",
        height=160,
    )

    if st.button("➕ Çekilişi geçici havuza ekle"):
        nums = extract_20_numbers(pasted)
        if nums is None:
            st.error("Tam olarak 20 benzersiz sayı okunamadı.")
        else:
            try:
                dt = datetime.strptime(f"{draw_date} {draw_time}", "%d.%m.%Y %H:%M")
                new_row = pd.DataFrame([[int(draw_no), dt, nums]], columns=["Cekilis_No", "DT", "Nums"])
                merged = pd.concat([temp_df, new_row], ignore_index=True)
                merged = (
                    merged.drop_duplicates("Cekilis_No", keep="last")
                          .sort_values("Cekilis_No")
                          .reset_index(drop=True)
                )
                st.session_state["meta_data_text"] = to_text(merged)
                st.success(f"#{int(draw_no)} geçici havuza eklendi.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    gh = github_settings()
    if gh:
        if st.button("💾 Mevcut havuzu GitHub veri.txt'ye kalıcı kaydet"):
            try:
                active_text = st.session_state.get("meta_data_text", base_text)
                active_df, _ = parse_text(active_text)
                github_save(
                    gh,
                    to_text(active_df),
                    f"META veri havuzu güncellendi #{int(active_df.iloc[-1]['Cekilis_No'])}",
                )
                st.success("GitHub veri.txt güncellendi.")
                st.cache_data.clear()
            except Exception as exc:
                st.error(str(exc))
    else:
        st.caption("GitHub Secrets tanımlı değilse kalıcı kayıt düğmesi çalışmaz; analiz yine çalışır.")

raw_text = st.session_state.get("meta_data_text", None)
if raw_text is None:
    if BASE_FILE.exists():
        raw_text = BASE_FILE.read_text(encoding="utf-8", errors="ignore")
    else:
        st.error("veri.txt bulunamadı.")
        st.stop()

try:
    with st.spinner("Merkezi tez–antitez matrisi hazırlanıyor..."):
        df, eng, Xs, ys, ts, invalid_lines = prepare_cached(raw_text)
except Exception as exc:
    st.error(str(exc))
    st.stop()

last = df.iloc[-1]
next_dt = next_draw_dt(last["DT"])
next_no = int(last["Cekilis_No"]) + 1
miss = missing_draws(df)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Toplam çekiliş", len(df))
m2.metric("Son çekiliş", int(last["Cekilis_No"]))
m3.metric("Son tarih/saat", last["DT"].strftime("%d.%m.%Y %H:%M"))
m4.metric("Eksik çekiliş", len(miss))

if invalid_lines:
    st.caption(f"Okunamayan satır: {len(invalid_lines)}")
if miss:
    with st.expander("Eksik çekiliş numaralarını göster"):
        st.write(", ".join(map(str, miss)))

st.info(
    f"🎯 Bir sonraki hedef: #{next_no} — "
    f"{next_dt.strftime('%d.%m.%Y %H:%M')}"
)

# Final model ve tahmin
with st.spinner("Son geçmişe kadar model eğitiliyor ve 1–80 puanlanıyor..."):
    final_model = fit_model(Xs, ys, ts, len(df))
    X_next = eng.build(len(df), next_dt.strftime("%H:%M"))
    ranking = predict_table(final_model, X_next)

master20 = ranking.head(20)["Sayı"].astype(int).tolist()

# Canlı ileri tahmini hedef çekiliş bazında kilitle.
lock_key = f"meta_locked_prediction_{next_no}"
if lock_key not in st.session_state:
    st.session_state[lock_key] = {
        "target_no": next_no,
        "train_last_no": int(last["Cekilis_No"]),
        "target_dt": next_dt.strftime("%d.%m.%Y %H:%M"),
        "master20": master20.copy(),
        "ranking": ranking.copy(),
    }

locked_live = st.session_state[lock_key]
master20 = list(locked_live["master20"])
ranking = locked_live["ranking"].copy()

st.info(
    "🧬 V18.5.13 Geçiş uzmanları ayrı kanallar: Dengeli + Tekrar + Yerine Geçme + Saat/Sıcaklık. Ayrıca Dinlenmiş Dönüş + "
    "Blok/Mikro-Konum + Saat/Faz Genel Güç. Uzmanlar kupon üretmez; "
    "META Tez–Antitez beynine 1–80 kanıtı verir."
)

st.subheader("1️⃣ META MASTER-20")
st.success("MASTER-20: " + " - ".join(map(str, master20)))
st.caption(
    f"🔒 Kilitli ileri tahmin: hedef #{locked_live['target_no']} | "
    f"eğitim sonu #{locked_live['train_last_no']} | {locked_live['target_dt']}"
)

c1, c2 = st.columns([1, 2])
target_k = c1.select_slider(
    "🎯 Hedef kolon büyüklüğü",
    options=list(range(3, 11)),
    value=10,
)
target_coupon = ranking.head(int(target_k))["Sayı"].astype(int).tolist()

c2.markdown(
    f"### 🎯 META Hedef {target_k}\n"
    + "**"
    + " - ".join(map(str, target_coupon))
    + "**"
)

st.caption(
    "Hedef kolon, ayrı bir motorun kuponu değildir. "
    "MASTER-20 sıralamasının üst kısmından seçilir."
)

st.subheader("2️⃣ Tez–Antitez ince eleme")
show_n = st.slider("Kaç sayıyı tabloda göster", 20, 80, 30, 10)
st.dataframe(
    ranking.head(show_n),
    use_container_width=True,
    hide_index=True,
)

with st.expander("🧬 META beyninde kullanılan analizler"):
    st.write(
        "META'nın kendi 20 temel sinyaline ek olarak V18.5.13'ten dört uzman kanalı bağlandı: "
        "Geçiş/Lift, Dinlenmiş Dönüş, Blok/Mikro-Konum ve Saat/Faz + Genel Güç. "
        "Bu uzmanların hiçbiri ayrı kupon üretmez. Her biri 1–80 için bir kanıt puanı verir; "
        "LogisticRegression bunları diğer TEZ/ANTİTEZ özellikleriyle birlikte öğrenir. "
        "Sonuç yine tek MASTER-20 ve onun üst sırasından seçilen tek 3–10 hedef kolondur."
    )

st.subheader("3️⃣-B V18 Geçiş Uzmanları — ayrı sızıntısız teşhis")
st.caption("Dengeli, Tekrar ağırlıklı, Yerine geçme ağırlıklı ve Saat/Sıcaklık ayrı ayrı 1–80 puanıyla ölçülür; ayrı kupon üretmez.")
_gn=st.selectbox("Geçiş uzmanı test adedi",[25,50,100,250],index=2,key="meta_v5_gecis_test_n")
if st.button("🧪 4 Geçiş Uzmanını Ayrı Test Et",key="meta_v5_gecis_test_run"):
    with st.spinner("Dört geçiş uzmanı sızıntısız test ediliyor..."):
        _gd,_gs=transition_expert_diagnostic(df,int(_gn),120)
    if _gs.empty: st.warning("Yeterli veri yok.")
    else: st.session_state["meta_v5_gecis_detail"]=_gd; st.session_state["meta_v5_gecis_summary"]=_gs
if "meta_v5_gecis_summary" in st.session_state:
    st.dataframe(st.session_state["meta_v5_gecis_summary"],use_container_width=True,hide_index=True)
    with st.expander("Geçiş uzmanı çekiliş çekiliş ayrıntısı"):
        st.dataframe(st.session_state["meta_v5_gecis_detail"].sort_values(["Çekiliş","Profil"],ascending=[False,True]),use_container_width=True,hide_index=True)

st.subheader("3️⃣ SIKI Walk-forward — gelecek veri sızıntısı kontrolü")
max_test = min(500, max(100, len(df) - 300))
test_draws = st.slider(
    "Kaç geçmiş çekilişi ileri-test et",
    min_value=100,
    max_value=max_test,
    value=min(250, max_test),
    step=25,
)
if st.button("🔬 Walk-forward testi çalıştır", type="primary"):
    with st.spinner("Her çekilişte yalnız o ana kadarki geçmiş kullanılıyor..."):
        bt = backtest(df, Xs, ys, ts, test_draws=test_draws, refit_every=1)
    if bt.empty:
        st.warning("Test üretilemedi.")
    else:
        summary = summarize_backtest(bt)
        st.dataframe(summary, use_container_width=True, hide_index=True)

        leak_bad = int((bt["Sızıntı kontrolü"] != "TEMİZ").sum())
        if leak_bad == 0:
            st.success("🔒 Denetim geçti: test edilen her çekilişte eğitim verisi hedef çekilişten önce kesildi.")
        else:
            st.error(f"🚨 {leak_bad} test satırında veri sızıntısı şüphesi var. Bu skorları kullanma.")

        top20_avg = float(bt["Top20"].mean())
        top10_avg = float(bt["Top10"].mean())
        st.write(
            f"**MASTER-20 ortalama:** {top20_avg:.3f}/20  |  "
            f"**Hedef-10 ortalama:** {top10_avg:.3f}/10"
        )
        st.caption(
            "Rastgele seçim beklentisi MASTER-20 için 5.0, Hedef-10 için 2.5'tir. "
            "Net fark kalıcı ve pozitif değilse modelin geleceğe dönük üstünlüğü henüz kanıtlanmış değildir."
        )

        st.dataframe(
            bt.tail(60).sort_values("Çekiliş", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        csv = bt.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Walk-forward CSV indir",
            csv,
            file_name="meta_walk_forward_DENETIMLI.csv",
            mime="text/csv",
        )

st.info(
    "🔐 Test protokolü: hedef çekilişin gerçek sonucu tahmin üretiminde kullanılmaz. "
    "Her CSV satırında 'Eğitim son çekiliş', kilitli MASTER-20/Hedef-10, gerçek sonuç, "
    "tutanlar ve kaçanlar birlikte yazılır. Böylece yüksek bir skor tek tek doğrulanabilir."
)

st.subheader("4️⃣ Sonuç geldiğinde kontrol")
result_text = st.text_area(
    "Gerçek 20 sayıyı buraya yapıştır",
    placeholder="20 sayıyı satır satır veya virgülle yapıştır",
    height=120,
    key="result_checker",
)
if st.button("✅ META sonucunu kontrol et"):
    actual = extract_20_numbers(result_text)
    if actual is None:
        st.error("20 benzersiz sayı okunamadı.")
    else:
        actual_set = set(actual)
        hit20 = sorted(actual_set & set(master20))
        hit_target = sorted(actual_set & set(target_coupon))

        r1, r2 = st.columns(2)
        r1.metric("MASTER-20 isabet", f"{len(hit20)}/20")
        r2.metric(f"Hedef-{target_k} isabet", f"{len(hit_target)}/{target_k}")

        st.write("**MASTER-20 tutturanlar:**", " - ".join(map(str, hit20)) or "Yok")
        st.write(f"**Hedef-{target_k} tutturanlar:**", " - ".join(map(str, hit_target)) or "Yok")

        missed = sorted(actual_set - set(master20))
        st.write("**MASTER-20 dışında kalan gerçek sayılar:**", " - ".join(map(str, missed)) or "Yok")

st.subheader("5️⃣ Dışa aktarma")
ranking_csv = ranking.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ 1–80 META sıralamasını CSV indir",
    ranking_csv,
    file_name=f"meta_siralama_{next_no}.csv",
    mime="text/csv",
)

st.download_button(
    "⬇️ Güncel veri.txt indir",
    to_text(df).encode("utf-8"),
    file_name="veri.txt",
    mime="text/plain",
)

st.warning(
    "Gerçeklik freni: çekilişler rastgele/bağımsızsa hiçbir istatistiksel model sürekli nokta atışı garanti edemez. "
    "Bu uygulamanın amacı sinyalleri mümkün olduğunca sıkı test etmek; başarı ölçütü tek iyi çekiliş değil, "
    "walk-forward ortalamasının rastgele beklentiyi kalıcı biçimde aşmasıdır."
)
