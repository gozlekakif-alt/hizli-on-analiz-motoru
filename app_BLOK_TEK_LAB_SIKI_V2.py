
import base64
import io
import math
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
    page_title="Ardışık Blok Motor Laboratuvarı",
    page_icon="🧠",
    layout="wide",
)

APP_VERSION = "META V6.3.1 — Kontrollü Faz + Saat + Benzer Durum"
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
        # Tarih/saat dizisini saat/faz ve benzer-durum motorları ortak kullanır.
        self.dts = list(pd.to_datetime(self.df["DT"]))
        self.times = [x.strftime("%H:%M") for x in self.dts]
        self.hours = [x.hour for x in self.dts]

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



def _safe_minmax_series(values):
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return a
    lo = float(np.nanmin(a))
    hi = float(np.nanmax(a))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.full(len(a), 0.5, dtype=float)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def _gap_before(engine, t, n_idx):
    """t hedefinden hemen önce sayının kaç el dinlendiği. Son elde varsa 0."""
    seen = np.where(engine.A[:t, n_idx] == 1)[0]
    if not len(seen):
        return min(t, 30)
    return int(t - 1 - seen[-1])




def time_regime_engine(engine, t, target_time):
    """
    Sızıntısız saat/faz motoru.
    Aynı dakika-slotu (örn. :17), yakın saat dilimi ve gün içi saat davranışının
    kısa dönem ile uzun dönem arasındaki değişimini ölçer.
    """
    if t < 60:
        return {
            "break_score": 0.0,
            "state": "Yetersiz geçmiş",
            "number_time_score": np.full(80, 0.5, dtype=float),
            "slot_samples": 0,
            "hour_samples": 0,
        }

    dt_hist = engine.dts[:t]
    target_hhmm = str(target_time)
    try:
        hh, mm = [int(x) for x in target_hhmm.split(":")[:2]]
    except Exception:
        hh, mm = 0, 0

    # Hızlı On 5 dakikalık yapıda dakika fazı önemli olabilir: :02, :07, :12...
    slot_idx = [i for i, d in enumerate(dt_hist) if int(d.minute) == mm]
    hour_idx = [i for i, d in enumerate(dt_hist) if int(d.hour) == hh]

    def rate(idxs, last_n=None):
        if last_n is not None:
            idxs = idxs[-last_n:]
        if not idxs:
            return np.zeros(80, dtype=float)
        return engine.A[idxs].mean(axis=0)

    slot_short = rate(slot_idx, 12)
    slot_long = rate(slot_idx, 60)
    hour_short = rate(hour_idx, 24)
    hour_long = rate(hour_idx, 100)

    slot_delta = slot_short - slot_long
    hour_delta = hour_short - hour_long

    # Saat rejim kırılması: son örneklerin uzun dönem saat/faz davranışından uzaklaşması.
    slot_break = float(np.mean(np.abs(slot_delta))) if len(slot_idx) >= 8 else 0.0
    hour_break = float(np.mean(np.abs(hour_delta))) if len(hour_idx) >= 12 else 0.0
    break_score = float(np.clip((0.62 * slot_break + 0.38 * hour_break) * 420.0, 0.0, 100.0))

    combined = (
        0.46 * slot_short
        + 0.18 * slot_long
        + 0.24 * hour_short
        + 0.12 * hour_long
    )
    # Değişim olduğunda yeni kısa dönem yönünü biraz daha öne çıkar.
    delta = 0.62 * slot_delta + 0.38 * hour_delta
    if break_score >= 35:
        combined = combined + (break_score / 100.0) * 0.45 * np.maximum(delta, 0.0)

    score = _safe_minmax_series(combined)

    if break_score >= 55:
        state = "SAAT REJİMİ KIRILIYOR"
    elif break_score >= 30:
        state = "SAAT REJİMİ GEÇİŞTE"
    else:
        state = "SAAT REJİMİ STABİL"

    return {
        "break_score": break_score,
        "state": state,
        "number_time_score": score,
        "slot_samples": len(slot_idx),
        "hour_samples": len(hour_idx),
        "slot_minute": mm,
        "hour": hh,
    }


def similar_state_next_engine(engine, t, target_time, top_matches=45):
    """
    Geçmişte bugünkü son çekilişe benzeyen durumları bulur ve onların GERÇEK
    bir sonraki çekilişlerinde hangi sayıların geldiğini ölçer.
    Hedef t ve sonrası hiçbir şekilde kullanılmaz.
    """
    if t < 100:
        return {
            "score": np.full(80, 0.5, dtype=float),
            "matches": 0,
            "avg_similarity": 0.0,
        }

    A = engine.A
    current = A[t - 1].astype(float)

    # Güncel durum özetleri: 10'luk bölgeler + son çekiliş + son 5 frekansı.
    cur_bands = np.array([current[b*10:(b+1)*10].sum() for b in range(8)], dtype=float) / 10.0
    cur_f5 = A[max(0, t-5):t].mean(axis=0)

    candidates = []
    # En az bir sonraki sonuç mevcut olan geçmiş durumlar.
    start = max(20, t - 700)
    for j in range(start, t - 1):
        hist = A[j].astype(float)
        overlap = float(np.sum(current * hist)) / 20.0
        hb = np.array([hist[b*10:(b+1)*10].sum() for b in range(8)], dtype=float) / 10.0
        band_sim = 1.0 - min(float(np.mean(np.abs(cur_bands - hb))) / 0.5, 1.0)

        hf5 = A[max(0, j-4):j+1].mean(axis=0)
        freq_sim = 1.0 - min(float(np.mean(np.abs(cur_f5 - hf5))) / 0.5, 1.0)

        # Saat fazı benzerliği bonusu.
        dj = engine.dts[j]
        try:
            th, tm = [int(x) for x in str(target_time).split(":")[:2]]
        except Exception:
            th, tm = 0, 0
        time_sim = 1.0 if int(dj.minute) == tm else (0.72 if int(dj.hour) == th else 0.45)

        sim = 0.48 * overlap + 0.24 * band_sim + 0.18 * freq_sim + 0.10 * time_sim
        candidates.append((sim, j))

    candidates.sort(reverse=True)
    chosen = candidates[:max(10, min(top_matches, len(candidates)))]
    if not chosen:
        return {"score": np.full(80, 0.5), "matches": 0, "avg_similarity": 0.0}

    weighted = np.zeros(80, dtype=float)
    total_w = 0.0
    for sim, j in chosen:
        # Benzer durumun kendisi değil, bir SONRAKİ çekilişi kullanılır.
        nxt = A[j + 1].astype(float)
        w = max(sim, 0.05) ** 2
        weighted += w * nxt
        total_w += w

    raw = weighted / max(total_w, 1e-9)
    score = _safe_minmax_series(raw)
    return {
        "score": score,
        "matches": len(chosen),
        "avg_similarity": float(np.mean([x[0] for x in chosen])),
    }


def phase_regime_engine(engine, t):
    """
    Sızıntısız faz motoru.
    Fazı sayı bazında değil, 10'luk bölgelerin son dönem davranışında ölçer.
    Son 8 çekiliş ile önceki 24 çekilişin bölge paylarını karşılaştırır;
    kırılım kuvveti, yeni faz yönü ve 1-80 faz desteği üretir.
    """
    if t < 40:
        return {
            "break_score": 0.0,
            "state": "Yetersiz geçmiş",
            "band_momentum": np.zeros(8, dtype=float),
            "number_phase_score": np.full(80, 0.5, dtype=float),
            "hot_bands": [],
            "cooling_bands": [],
        }

    A = engine.A

    def band_vector(start, end):
        h = A[max(0, start):max(0, end)]
        out = np.zeros(8, dtype=float)
        if len(h) == 0:
            return out
        for b in range(8):
            lo, hi = b * 10, (b + 1) * 10
            out[b] = float(h[:, lo:hi].sum()) / len(h)
        # Her çekilişte toplam 20 sayı olduğundan bölgeleri paya dönüştür.
        total = max(float(out.sum()), 1e-9)
        return out / total

    recent = band_vector(t - 8, t)
    previous = band_vector(t - 32, t - 8)
    medium = band_vector(t - 20, t)

    # Mutlak rejim değişimi. 0 = aynı yapı, 100 = çok güçlü kırılma.
    l1 = float(np.sum(np.abs(recent - previous))) / 2.0
    break_score = float(np.clip(l1 * 180.0, 0.0, 100.0))

    momentum = recent - previous
    medium_shift = recent - medium
    combined = 0.72 * momentum + 0.28 * medium_shift

    # Band faz desteği 0-1.
    if np.max(np.abs(combined)) > 1e-12:
        band_norm = (combined - combined.min()) / max(combined.max() - combined.min(), 1e-9)
    else:
        band_norm = np.full(8, 0.5)

    number_phase = np.zeros(80, dtype=float)
    for n in range(80):
        number_phase[n] = band_norm[n // 10]

    ranked = np.argsort(-combined)
    hot_bands = [f"{int(i)*10+1}-{int(i)*10+10}" for i in ranked[:2] if combined[i] > 0]
    cool_ranked = np.argsort(combined)
    cooling_bands = [f"{int(i)*10+1}-{int(i)*10+10}" for i in cool_ranked[:2] if combined[i] < 0]

    if break_score >= 55:
        state = "KIRILIM / yeni faz oluşuyor"
    elif break_score >= 30:
        state = "GEÇİŞ / faz değişimi izleniyor"
    else:
        state = "STABİL faz"

    return {
        "break_score": break_score,
        "state": state,
        "band_momentum": combined,
        "number_phase_score": number_phase,
        "hot_bands": hot_bands,
        "cooling_bands": cooling_bands,
        "recent_band_share": recent,
        "previous_band_share": previous,
    }


def lifecycle_context(engine, t, target_time):
    """
    Yalnız A[:t] ile:
    - beklenen taşıma adedi
    - her son-çekiliş sayısının taşıma olasılığı
    - dinlenme sınıfı dönüş oranları
    - güncel birlikte-gelme / geçiş desteği
    üretir.
    """
    if t < 30:
        raise ValueError("Yaşam döngüsü için en az 30 geçmiş çekiliş gerekir.")

    A = engine.A
    phase_ctx = phase_regime_engine(engine, t)
    time_ctx = time_regime_engine(engine, t, target_time)
    similar_ctx = similar_state_next_engine(engine, t, target_time, top_matches=45)
    last_set_idx = set(np.where(A[t - 1] == 1)[0].tolist())

    # 1) Çekilişten çekilişe taşınan sayı adedi: kısa + orta + uzun hafıza.
    overlaps = []
    for j in range(1, t):
        if engine.draw_nos[j] == engine.draw_nos[j - 1] + 1:
            overlaps.append(int(np.sum(A[j] * A[j - 1])))
    if overlaps:
        arr = np.asarray(overlaps, dtype=float)
        m25 = float(np.mean(arr[-min(25, len(arr)):]))
        m75 = float(np.mean(arr[-min(75, len(arr)):]))
        m200 = float(np.mean(arr[-min(200, len(arr)):]))
        exp_carry = 0.50 * m25 + 0.30 * m75 + 0.20 * m200
    else:
        exp_carry = 5.0
    expected_carry = int(np.clip(round(exp_carry), 2, 8))

    # 2) Sayı-bazlı gerçek taşıma oranı (yalnız geçmiş ardışık geçişler).
    repeat_hits = np.zeros(80, dtype=float)
    repeat_cases = np.zeros(80, dtype=float)
    recent_hits = np.zeros(80, dtype=float)
    recent_cases = np.zeros(80, dtype=float)
    start_recent = max(0, t - 120)
    for j in range(0, t - 1):
        if engine.draw_nos[j + 1] != engine.draw_nos[j] + 1:
            continue
        cur = A[j]
        nxt = A[j + 1]
        repeat_cases += cur
        repeat_hits += cur * nxt
        if j >= start_recent:
            recent_cases += cur
            recent_hits += cur * nxt

    global_repeat = repeat_hits.sum() / max(repeat_cases.sum(), 1.0)
    num_repeat = repeat_hits / np.maximum(repeat_cases, 1.0)
    num_repeat_recent = recent_hits / np.maximum(recent_cases, 1.0)

    # 3) Kaynak -> sonraki sayı geçiş desteği, mevcut 20 sayının tamamından.
    TT = engine.cumT[t - 1].astype(float)
    SS = engine.cumS[t - 1].astype(float)
    src = np.array(sorted(last_set_idx), dtype=int)
    transition = np.zeros(80, dtype=float)
    coverage = np.zeros(80, dtype=float)
    base = engine.window_rate(t, min(200, t))
    for n in range(80):
        vals = []
        for ss in src:
            if SS[ss] >= 6:
                p = TT[ss, n] / max(SS[ss], 1.0)
                lift = p / max(base[n], 1e-6)
                # Aşırı küçük örnek / uç lift'i bastır.
                vals.append(0.68 * p + 0.32 * min(lift, 3.0) / 3.0)
                if TT[ss, n] > 0:
                    coverage[n] += 1
        transition[n] = float(np.mean(vals)) if vals else 0.0

    transition_n = _safe_minmax_series(transition)
    coverage_n = _safe_minmax_series(coverage)

    # 4) Son dönem birlikte-gelme gücü: mevcut son 20 ile aday arasındaki lift.
    start_pair = max(0, t - 160)
    H = A[start_pair:t].astype(float)
    freq = H.sum(axis=0)
    pair_support = np.zeros(80, dtype=float)
    if len(H):
        for n in range(80):
            vals = []
            for ss in src:
                if ss == n:
                    continue
                both = float(np.sum(H[:, n] * H[:, ss]))
                expected = max((freq[n] * freq[ss]) / max(len(H), 1), 1e-6)
                vals.append(min(both / expected, 3.0))
            pair_support[n] = float(np.mean(vals)) if vals else 0.0
    pair_n = _safe_minmax_series(pair_support)

    # 5) Dinlenme sınıfı -> gerçekten bir sonraki elde dönüş olasılığı.
    buckets = [(1, 2, "1-2"), (3, 5, "3-5"), (6, 10, "6-10"), (11, 999, "10+")]
    global_bucket_hits = {b: 0.0 for _, _, b in buckets}
    global_bucket_cases = {b: 0.0 for _, _, b in buckets}
    num_bucket_hits = {b: np.zeros(80, dtype=float) for _, _, b in buckets}
    num_bucket_cases = {b: np.zeros(80, dtype=float) for _, _, b in buckets}

    # Son 400 geçiş yeterli ve hesap maliyeti kontrollü.
    j0 = max(12, t - 400)
    last_seen = np.full(80, -9999, dtype=int)
    # warm-up last_seen
    for j in range(0, j0):
        last_seen[np.where(A[j] == 1)[0]] = j

    for j in range(j0, t - 1):
        gaps = j - last_seen
        nxt = A[j + 1]
        cur = A[j]
        for lo, hi, b in buckets:
            mask = (cur == 0) & (gaps >= lo) & (gaps <= hi)
            if np.any(mask):
                num_bucket_cases[b][mask] += 1
                num_bucket_hits[b][mask] += nxt[mask]
                global_bucket_cases[b] += float(np.sum(mask))
                global_bucket_hits[b] += float(np.sum(nxt[mask]))
        last_seen[np.where(cur == 1)[0]] = j

    rest_score = np.zeros(80, dtype=float)
    gap_class = ["TAŞIMA"] * 80
    for n in range(80):
        if n in last_set_idx:
            continue
        g = _gap_before(engine, t, n)
        bname = "10+"
        for lo, hi, b in buckets:
            if lo <= g <= hi:
                bname = b
                break
        gap_class[n] = bname
        gr = global_bucket_hits[bname] / max(global_bucket_cases[bname], 1.0)
        nr = num_bucket_hits[bname][n] / max(num_bucket_cases[bname][n], 1.0)
        rel = min(1.0, num_bucket_cases[bname][n] / 20.0)
        rest_score[n] = rel * nr + (1.0 - rel) * gr
    rest_n = _safe_minmax_series(rest_score)

    # 6) Taşıma skoru: kör "son elde çıktı" değil; kişisel tekrar + kısa form +
    # geçiş ağı + birlikte-gelme + seri davranışı.
    carry_score = np.zeros(80, dtype=float)
    for n in last_set_idx:
        # Az örnekli sayı kişisel oranını genele shrink et.
        rel_long = min(1.0, repeat_cases[n] / 35.0)
        rel_recent = min(1.0, recent_cases[n] / 14.0)
        p_long = rel_long * num_repeat[n] + (1.0 - rel_long) * global_repeat
        p_recent = rel_recent * num_repeat_recent[n] + (1.0 - rel_recent) * p_long

        # Kaç el üst üste devam etmiş? 1-2 el faydalı; çok uzun seride hafif fren.
        streak = 0
        for j in range(t - 1, -1, -1):
            if A[j, n] == 1:
                streak += 1
            else:
                break
        streak_factor = 1.0 if streak <= 2 else max(0.72, 1.0 - 0.08 * (streak - 2))

        raw = (
            0.42 * p_recent
            + 0.28 * p_long
            + 0.18 * transition_n[n]
            + 0.12 * pair_n[n]
        ) * streak_factor
        carry_score[n] = raw
    carry_n = _safe_minmax_series(carry_score)

    # 7) Geçmişte non-carry gerçeklerinin gap sınıf dağılımı -> koltuk oranları.
    bucket_counts = {"1-2": 0, "3-5": 0, "6-10": 0, "10+": 0}
    total_new = 0
    start_comp = max(20, t - 250)
    for j in range(start_comp, t):
        if j <= 0 or engine.draw_nos[j] != engine.draw_nos[j - 1] + 1:
            continue
        prev = set(np.where(A[j - 1] == 1)[0].tolist())
        actual = set(np.where(A[j] == 1)[0].tolist())
        for n in actual - prev:
            # gap before draw j
            seen = np.where(A[:j, n] == 1)[0]
            g = j - 1 - int(seen[-1]) if len(seen) else 30
            if g <= 2:
                bucket_counts["1-2"] += 1
            elif g <= 5:
                bucket_counts["3-5"] += 1
            elif g <= 10:
                bucket_counts["6-10"] += 1
            else:
                bucket_counts["10+"] += 1
            total_new += 1

    return {
        "expected_carry": expected_carry,
        "expected_carry_raw": float(exp_carry),
        "carry_score": carry_n,
        "rest_score": rest_n,
        "transition_score": transition_n,
        "coverage_score": coverage_n,
        "pair_score": pair_n,
        "gap_class": gap_class,
        "bucket_counts": bucket_counts,
        "total_new": total_new,
        "last_set_idx": last_set_idx,
        "global_repeat_rate": float(global_repeat),
        "phase_break_score": float(phase_ctx["break_score"]),
        "phase_state": phase_ctx["state"],
        "phase_score": phase_ctx["number_phase_score"],
        "phase_hot_bands": phase_ctx["hot_bands"],
        "phase_cooling_bands": phase_ctx["cooling_bands"],
        "time_break_score": float(time_ctx["break_score"]),
        "time_state": time_ctx["state"],
        "time_score": time_ctx["number_time_score"],
        "similar_score": similar_ctx["score"],
        "similar_matches": int(similar_ctx["matches"]),
        "similar_avg_similarity": float(similar_ctx["avg_similarity"]),
    }


def allocate_lifecycle_master20(engine, t, target_time, ranking, size=20):
    """
    META puanı + yaşam döngüsü.
    Önce çekiliş mimarisini tahmin eder, sonra 20 koltuğu:
      TAŞIMA / 1-2 / 3-5 / 6-10 / 10+
    sınıflarına ayırır. Geçiş ve birlikte-gelme tüm koltuklarda bonus olarak işler.
    """
    ctx = lifecycle_context(engine, t, target_time)
    base_map = ranking.set_index("Sayı")["META %"].astype(float).to_dict()
    base = np.array([base_map.get(n, 0.0) / 100.0 for n in range(1, 81)], dtype=float)
    base_n = _safe_minmax_series(base)

    # Taşıma dışındaki adaylarda dinlenme + geçiş + birliktelik; taşımalarda carry ana eksen.
    final = np.zeros(80, dtype=float)
    role = []
    phase_w = 0.03 + 0.09 * min(ctx["phase_break_score"] / 100.0, 1.0)
    time_w = 0.03 + 0.09 * min(ctx["time_break_score"] / 100.0, 1.0)
    # Benzer durum motoru yeterli eşleşmede anlamlı ağırlık alır.
    similar_w = 0.10 if ctx["similar_matches"] >= 25 else 0.05

    for i in range(80):
        structural_w = max(0.60, 1.0 - phase_w - time_w - similar_w)
        if i in ctx["last_set_idx"]:
            structural = (
                0.44 * base_n[i]
                + 0.38 * ctx["carry_score"][i]
                + 0.11 * ctx["transition_score"][i]
                + 0.07 * ctx["pair_score"][i]
            )
            final[i] = (
                structural_w * structural
                + phase_w * ctx["phase_score"][i]
                + time_w * ctx["time_score"][i]
                + similar_w * ctx["similar_score"][i]
            )
            role.append("TAŞIMA")
        else:
            structural = (
                0.43 * base_n[i]
                + 0.25 * ctx["rest_score"][i]
                + 0.20 * ctx["transition_score"][i]
                + 0.12 * ctx["pair_score"][i]
            )
            final[i] = (
                structural_w * structural
                + phase_w * ctx["phase_score"][i]
                + time_w * ctx["time_score"][i]
                + similar_w * ctx["similar_score"][i]
            )
            role.append(ctx["gap_class"][i])

    # Dinamik koltuk planı.
    carry_q = int(np.clip(ctx["expected_carry"], 2, min(8, size - 4)))
    remaining = size - carry_q
    bc = ctx["bucket_counts"]
    denom = max(sum(bc.values()), 1)
    raw_q = {b: remaining * bc[b] / denom for b in ["1-2", "3-5", "6-10", "10+"]}
    quotas = {b: int(math.floor(raw_q[b])) for b in raw_q}
    left = remaining - sum(quotas.values())
    for b in sorted(raw_q, key=lambda x: raw_q[x] - quotas[x], reverse=True)[:left]:
        quotas[b] += 1

    quota = {"TAŞIMA": carry_q, **quotas}

    # Her yaşam sınıfında kendi skoru yüksek olanı al.
    selected = []
    reasons = {}
    rows = []
    for rname in ["TAŞIMA", "1-2", "3-5", "6-10", "10+"]:
        candidates = [i for i in range(80) if role[i] == rname]
        candidates.sort(key=lambda i: (final[i], base_n[i]), reverse=True)
        for i in candidates[:quota.get(rname, 0)]:
            if i not in selected:
                selected.append(i)
                reasons[i] = rname

    # Sınıfta yeterli aday yoksa global puanla tamamla.
    if len(selected) < size:
        for i in np.argsort(-final):
            i = int(i)
            if i not in selected:
                selected.append(i)
                reasons[i] = role[i] + " / tamamlayıcı"
            if len(selected) >= size:
                break

    selected = selected[:size]

    for i in range(80):
        rows.append({
            "Sayı": i + 1,
            "Yaşam Rolü": role[i],
            "Yaşam Puanı": round(float(final[i]) * 100, 2),
            "META %": round(float(base[i]) * 100, 2),
            "Taşıma Kanıtı": round(float(ctx["carry_score"][i]) * 100, 2),
            "Dinlenmiş Dönüş": round(float(ctx["rest_score"][i]) * 100, 2),
            "Geçiş Desteği": round(float(ctx["transition_score"][i]) * 100, 2),
            "Birliktelik Desteği": round(float(ctx["pair_score"][i]) * 100, 2),
            "Faz Desteği": round(float(ctx["phase_score"][i]) * 100, 2),
            "Saat Rejimi": round(float(ctx["time_score"][i]) * 100, 2),
            "Benzer Durum→Sonraki": round(float(ctx["similar_score"][i]) * 100, 2),
            "MASTER-20": (i in selected),
            "Koltuk": reasons.get(i, ""),
        })

    table = pd.DataFrame(rows).sort_values(
        ["MASTER-20", "Yaşam Puanı", "META %"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    # Hedef 3-10: MASTER-20 içindeki nihai yaşam puanı sırası.
    selected_ordered = (
        table[table["MASTER-20"]]
        .sort_values(["Yaşam Puanı", "META %"], ascending=False)["Sayı"]
        .astype(int).tolist()
    )

    return selected_ordered, table, ctx, quota


def carryover_diagnostic(engine, t, target_time):
    """Son çekilişteki 20 sayıyı, bir sonraki ele devretme kanıtıyla sıralar."""
    ctx = lifecycle_context(engine, t, target_time)
    rows = []
    for i in sorted(ctx["last_set_idx"]):
        rows.append({
            "Sayı": i + 1,
            "Taşıma Puanı": round(float(ctx["carry_score"][i]) * 100, 2),
            "Geçiş": round(float(ctx["transition_score"][i]) * 100, 2),
            "Birliktelik": round(float(ctx["pair_score"][i]) * 100, 2),
        })
    return pd.DataFrame(rows).sort_values("Taşıma Puanı", ascending=False), ctx


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
        # Önce META olasılık tablosu, sonra yaşam-döngüsü koltuk tahsisi.
        rank_target = predict_table(model, X_target)
        structured20, lifecycle_table_bt, lifecycle_ctx_bt, quota_bt = allocate_lifecycle_master20(
            MetaFeatureEngine(df.iloc[:t].copy()),
            t,
            df.iloc[t]["DT"].strftime("%H:%M"),
            rank_target,
            size=20,
        )
        locked20 = structured20[:20]
        locked10 = structured20[:10]
        locked9 = structured20[:9]
        locked8 = structured20[:8]
        locked7 = structured20[:7]
        locked6 = structured20[:6]
        locked5 = structured20[:5]
        locked4 = structured20[:4]
        locked3 = structured20[:3]

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
            "Beklenen taşıma": int(lifecycle_ctx_bt["expected_carry"]),
            "Gerçek taşıma": int(len(set(df.iloc[t-1]["Nums"]) & actual_set)),
            "Taşıma koltuğu": int(quota_bt.get("TAŞIMA", 0)),
            "Koltuk planı": " | ".join(f"{k}:{v}" for k,v in quota_bt.items()),
            "Faz kırılım": round(float(lifecycle_ctx_bt["phase_break_score"]), 2),
            "Faz durumu": lifecycle_ctx_bt["phase_state"],
            "Saat kırılım": round(float(lifecycle_ctx_bt["time_break_score"]), 2),
            "Saat rejimi": lifecycle_ctx_bt["time_state"],
            "Benzer durum adedi": int(lifecycle_ctx_bt["similar_matches"]),
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
# ARDIŞIK + BLOK MOTOR LABORATUVARI V2
# -------------------------------------------------------------------
st.title("🧪 BLOK TEK LAB — Eski + Yeni + Dinamik Seçici")
st.caption(
    "META kapalı. Bu motor artık 'blok var/yok' diye tek puan vermez; "
    "DEVAM, KENAR BÜYÜME, KAYMA/KIRILMA ve YENİ BLOK DOĞUMU davranışlarını ayrı öğrenir."
)

def _runs(nums):
    xs = sorted(set(map(int, nums)))
    out, cur = [], []
    for x in xs:
        if not cur or x == cur[-1] + 1:
            cur.append(x)
        else:
            if len(cur) >= 2:
                out.append(cur)
            cur = [x]
    if len(cur) >= 2:
        out.append(cur)
    return out

def _bf(nums):
    ss = set(map(int, nums))
    rr = _runs(ss)
    rn = set(x for r in rr for x in r)
    edges = set()
    for r in rr:
        if r[0] > 1:
            edges.add(r[0] - 1)
        if r[-1] < 80:
            edges.add(r[-1] + 1)
    bands = [sum(10*b + 1 <= x <= 10*b + 10 for x in ss) for b in range(8)]
    return {
        "set": ss,
        "runs": rr,
        "run_nums": rn,
        "edges": edges,
        "pairs": sum(len(r) - 1 for r in rr),
        "triples": sum(max(0, len(r) - 2) for r in rr),
        "max_run": max([len(r) for r in rr], default=1),
        "bands": bands,
        "dense": sum(c >= 4 for c in bands),
        "run_count": len(rr),
    }

def _bsim(a, b):
    band_dist = sum(abs(x-y) for x,y in zip(a["bands"], b["bands"])) / 20.0
    z = (
        .18 * min(abs(a["pairs"] - b["pairs"]) / 5, 1)
        + .15 * min(abs(a["triples"] - b["triples"]) / 3, 1)
        + .15 * min(abs(a["max_run"] - b["max_run"]) / 3, 1)
        + .10 * min(abs(a["dense"] - b["dense"]) / 3, 1)
        + .10 * min(abs(a["run_count"] - b["run_count"]) / 5, 1)
        + .32 * min(band_dist, 1)
    )
    return max(0.0, 1.0 - z)

def _behavior_labels(prev_nums, next_nums):
    """Bir tarihsel blok durumunun bir sonraki elde ne yaptığını sınıflandır."""
    pf = _bf(prev_nums)
    nf = _bf(next_nums)
    prev = pf["set"]
    nxt = nf["set"]

    continuation = nxt & pf["run_nums"]
    growth = nxt & pf["edges"]

    # Mevcut blokların ±2 çevresine kayan/yeni yerleşen sayılar.
    near2 = set()
    for n in pf["run_nums"]:
        for d in (-2, -1, 1, 2):
            q = n + d
            if 1 <= q <= 80:
                near2.add(q)
    shift = (nxt & near2) - continuation - growth

    # Yeni çekilişte blok içinde olup mevcut blokların yakın çevresinde olmayanlar.
    birth = set(nf["run_nums"]) - continuation - growth - shift

    return {
        "DEVAM": continuation,
        "BÜYÜME": growth,
        "KAYMA": shift,
        "DOĞUM": birth,
        "next_block_nums": nf["run_nums"],
    }

def block_predict_v2(engine, t, k=7, neighbors=70):
    """
    STRICT:
    hedef = t.
    Görülebilen son çekiliş t-1.
    Benzer tarihsel durum j için yalnız j+1 sonucu kullanılır ve j+1 < t olmalıdır.
    """
    if t < 100:
        return list(range(1, k+1)), pd.DataFrame(), {
            "signal": 0, "confidence": 0.0, "neighbors": 0, "runs": [], "avg": 0.0
        }

    current_nums = (np.where(engine.A[t-1] == 1)[0] + 1).tolist()
    cf = _bf(current_nums)

    cand = []
    for j in range(max(20, t-900), t-1):  # j+1 < t
        prev_j = (np.where(engine.A[j] == 1)[0] + 1).tolist()
        jf = _bf(prev_j)
        sim = _bsim(cf, jf)

        # Aynı yapısal rejimlere küçük bonus; sayı kimliğine bonus yok.
        if cf["max_run"] == jf["max_run"]:
            sim += .05
        if cf["pairs"] == jf["pairs"]:
            sim += .04
        if cf["run_count"] == jf["run_count"]:
            sim += .03
        cand.append((sim, j))

    cand.sort(reverse=True)
    chosen = cand[:min(neighbors, len(cand))]

    channel = {name: np.zeros(80, dtype=float) for name in ["DEVAM","BÜYÜME","KAYMA","DOĞUM"]}
    opportunity = {name: 0.0 for name in channel}
    event_hits = {name: 0.0 for name in channel}
    total_w = 0.0

    for sim, j in chosen:
        prev_j = (np.where(engine.A[j] == 1)[0] + 1).tolist()
        next_j = (np.where(engine.A[j+1] == 1)[0] + 1).tolist()
        pf = _bf(prev_j)
        labels = _behavior_labels(prev_j, next_j)
        w = max(sim, .02) ** 3

        # Tarihsel olay gerçekleşme sıklığı -> güven.
        for name in channel:
            if labels[name]:
                event_hits[name] += w

        # Kanal puanlarını sayı pozisyonundan öğren.
        # DEVAM: tarihsel blok içindeki sayının göreli konumunu canlı bloklara taşımak.
        for r in pf["runs"]:
            for pos, n in enumerate(r):
                if n in labels["DEVAM"]:
                    # canlı bloklarda aynı göreli pozisyonlara oy ver
                    for cr in cf["runs"]:
                        if len(cr) == len(r) and pos < len(cr):
                            channel["DEVAM"][cr[pos]-1] += w
        opportunity["DEVAM"] += w

        # BÜYÜME: sol/sağ kenarın tarihsel başarı oranını canlı kenarlara taşı.
        hist_left = set(r[0]-1 for r in pf["runs"] if r[0] > 1)
        hist_right = set(r[-1]+1 for r in pf["runs"] if r[-1] < 80)
        left_hit = len(hist_left & labels["BÜYÜME"])
        right_hit = len(hist_right & labels["BÜYÜME"])
        for cr in cf["runs"]:
            if cr[0] > 1:
                channel["BÜYÜME"][cr[0]-2] += w * (0.35 + left_hit)
            if cr[-1] < 80:
                channel["BÜYÜME"][cr[-1]] += w * (0.35 + right_hit)
        opportunity["BÜYÜME"] += w * max(len(pf["edges"]), 1)

        # KAYMA: geçmişte blok çevresinde +2/-2 yönünde oluşan hareketleri canlı blok çevresine aktar.
        for hn in labels["KAYMA"]:
            nearest = min(pf["run_nums"], key=lambda x: abs(x-hn)) if pf["run_nums"] else None
            if nearest is None:
                continue
            delta = hn - nearest
            if delta not in (-2, -1, 1, 2):
                continue
            for cn in cf["run_nums"]:
                q = cn + delta
                if 1 <= q <= 80:
                    channel["KAYMA"][q-1] += w / max(len(cf["run_nums"]), 1)
        opportunity["KAYMA"] += w

        # DOĞUM: yeni blokların 10'luk bölgesini öğren; aynı bölge momentumunu canlıya uygula.
        for n in labels["DOĞUM"]:
            channel["DOĞUM"][n-1] += w
        opportunity["DOĞUM"] += w
        total_w += w

    def norm(a):
        a = np.asarray(a, dtype=float)
        lo, hi = float(a.min()), float(a.max())
        return (a-lo)/(hi-lo) if hi > lo else np.zeros_like(a)

    for name in channel:
        channel[name] = norm(channel[name])

    # Olay güvenleri: benzer geçmişlerde bu davranış gerçekten kaç kez görüldü?
    event_rate = {
        name: float(event_hits[name] / max(total_w, 1e-9))
        for name in channel
    }

    # Doğum kanalında ham sayı kimliği yerine kısa dönem blok-üyeliği ile shrink.
    recent = engine.A[max(0,t-120):t]
    recent_block = np.zeros(80, dtype=float)
    if len(recent):
        for row in recent:
            bf = _bf(np.where(row==1)[0]+1)
            for n in bf["run_nums"]:
                recent_block[n-1] += 1
        recent_block = norm(recent_block)
    channel["DOĞUM"] = .68*channel["DOĞUM"] + .32*recent_block

    # Kanal ağırlıkları sabit değil: tarihsel olay oranına göre.
    weights = {
        "DEVAM": .18 + .32*event_rate["DEVAM"],
        "BÜYÜME": .15 + .30*event_rate["BÜYÜME"],
        "KAYMA": .10 + .22*event_rate["KAYMA"],
        "DOĞUM": .16 + .30*event_rate["DOĞUM"],
    }
    sw = sum(weights.values())
    weights = {k0:v/sw for k0,v in weights.items()}

    score = sum(weights[name]*channel[name] for name in channel)

    # Tek bir kanala aşırı bağımlı adayı frenle, 2+ davranış desteğini ödüllendir.
    support_count = np.zeros(80, dtype=float)
    for name in channel:
        support_count += (channel[name] >= .55).astype(float)
    score = score + .06*np.minimum(support_count, 3)/3.0

    order = np.argsort(-score)
    pred = (order[:k] + 1).astype(int).tolist()

    # Güven artık sinyal büyüklüğü değil: benzerlik + olay kararlılığı + kanal ayrışması.
    avg_sim = float(np.mean([x[0] for x in chosen])) if chosen else 0.0
    event_stability = 1.0 - float(np.std(list(event_rate.values())))
    top_margin = float(score[order[0]] - score[order[min(k,79)]]) if len(order) > k else 0.0
    conf = np.clip(
        100*(.38*max(0,avg_sim-.35)/.65 + .32*event_stability + .30*min(top_margin/.35,1)),
        0, 100
    )

    signal = cf["pairs"] + 2*cf["triples"] + max(0,cf["max_run"]-2)
    rows=[]
    for i in range(80):
        rows.append({
            "Sayı": i+1,
            "Final Blok Puanı": round(float(score[i])*100,2),
            "DEVAM": round(float(channel["DEVAM"][i])*100,2),
            "BÜYÜME": round(float(channel["BÜYÜME"][i])*100,2),
            "KAYMA": round(float(channel["KAYMA"][i])*100,2),
            "DOĞUM": round(float(channel["DOĞUM"][i])*100,2),
            "Kanal Desteği": int(support_count[i]),
        })
    table = pd.DataFrame(rows).sort_values(
        ["Final Blok Puanı","Kanal Desteği"], ascending=[False,False]
    ).reset_index(drop=True)

    info = {
        "signal": int(signal),
        "confidence": round(float(conf),1),
        "neighbors": len(chosen),
        "runs": cf["runs"],
        "avg": round(avg_sim,3),
        "event_rate": {k0:round(v,3) for k0,v in event_rate.items()},
        "weights": {k0:round(v,3) for k0,v in weights.items()},
    }
    return pred, table, info

def backtest_v2(engine, tests=250, neighbors=70):
    """
    Aynı anda Top3..Top10 ölçer. Böylece bu uzman kaç koltuk istediğinde
    gerçekten avantaj sağlıyor, testten görülür.
    """
    rows=[]
    start=max(120, len(engine.A)-tests)
    for t in range(start, len(engine.A)):
        # Bir kez 10 aday üret, alt k'lar aynı sıralamanın üst kısmıdır.
        pred10, table, info = block_predict_v2(engine,t,k=10,neighbors=neighbors)
        actual=set((np.where(engine.A[t]==1)[0]+1).tolist())
        actual_bf=_bf(actual)
        rec={
            "Index":t,
            "Çekiliş":int(engine.draw_nos[t]),
            "Sinyal":info["signal"],
            "Güven":info["confidence"],
            "Ort benzerlik":info["avg"],
            "DEVAM olay":info["event_rate"]["DEVAM"],
            "BÜYÜME olay":info["event_rate"]["BÜYÜME"],
            "KAYMA olay":info["event_rate"]["KAYMA"],
            "DOĞUM olay":info["event_rate"]["DOĞUM"],
        }
        for k in range(3,11):
            picks=pred10[:k]
            rec[f"Top{k}"]=len(set(picks)&actual)
        rec["Top7 tahmin"]=" - ".join(map(str,pred10[:7]))
        rec["Top7 tutan"]=" - ".join(map(str,sorted(set(pred10[:7])&actual))) or "Yok"
        rec["Top7 gerçek blok içi"]=len(set(pred10[:7]) & actual_bf["run_nums"])
        rows.append(rec)
    return pd.DataFrame(rows)


def forensic_backtest_v2(engine, tests=250, neighbors=70):
    """
    PUANLAMAYA DOKUNMAZ.
    Mevcut block_predict_v2 sıralamasının ilk 15 adayını uzun formatta kaydeder.
    Her hedef çekilişte yalnız t öncesi geçmiş kullanılır.
    """
    draw_rows = []
    rank_rows = []
    start = max(120, len(engine.A) - tests)

    for t in range(start, len(engine.A)):
        pred15, table, info = block_predict_v2(
            engine, t, k=15, neighbors=neighbors
        )
        actual = set((np.where(engine.A[t] == 1)[0] + 1).tolist())

        # block_predict_v2'nin gerçek sıralama tablosu zaten final puana göre sıralı.
        top15_table = table.head(15).copy().reset_index(drop=True)
        top15 = top15_table["Sayı"].astype(int).tolist()
        top10 = top15[:10]

        draw_rows.append({
            "Index": t,
            "Çekiliş": int(engine.draw_nos[t]),
            "Top10": len(set(top10) & actual),
            "Top15": len(set(top15) & actual),
            "Top10 tahmin": " - ".join(map(str, top10)),
            "Top10 tutan": " - ".join(map(str, sorted(set(top10) & actual))) or "Yok",
            "11-15 adaylar": " - ".join(map(str, top15[10:15])),
            "11-15 gerçek": " - ".join(map(str, sorted(set(top15[10:15]) & actual))) or "Yok",
            "11-15 gerçek adet": len(set(top15[10:15]) & actual),
            "Sinyal": info["signal"],
            "Güven": info["confidence"],
            "Ort benzerlik": info["avg"],
            "DEVAM olay": info["event_rate"]["DEVAM"],
            "BÜYÜME olay": info["event_rate"]["BÜYÜME"],
            "KAYMA olay": info["event_rate"]["KAYMA"],
            "DOĞUM olay": info["event_rate"]["DOĞUM"],
        })

        for r, row in top15_table.iterrows():
            n = int(row["Sayı"])
            rank_rows.append({
                "Index": t,
                "Çekiliş": int(engine.draw_nos[t]),
                "Sıra": int(r + 1),
                "Sayı": n,
                "Gerçek çıktı": int(n in actual),
                "Final Blok Puanı": float(row["Final Blok Puanı"]),
                "DEVAM": float(row["DEVAM"]),
                "BÜYÜME": float(row["BÜYÜME"]),
                "KAYMA": float(row["KAYMA"]),
                "DOĞUM": float(row["DOĞUM"]),
                "Kanal Desteği": int(row["Kanal Desteği"]),
                "Sinyal": info["signal"],
                "Güven": info["confidence"],
                "Ort benzerlik": info["avg"],
            })

    return pd.DataFrame(draw_rows), pd.DataFrame(rank_rows)



def compare_old_new_block(engine, tests=250, neighbors=70, min_train_draws=60):
    """
    ESKİ BLOK vs YENİ yeniden-sıralama.
    block_predict_v2 değişmez.
    Yeni katman yalnız geçmiş hedeflerden öğrenir ve mevcut Top15'i yeniden sıralar.
    """
    feat_cols = ["DEVAM", "BÜYÜME", "KAYMA", "DOĞUM", "Kanal Desteği"]
    history = []
    rows = []
    start = max(120, len(engine.A) - tests)

    for t in range(start, len(engine.A)):
        _, table, info = block_predict_v2(engine, t, k=15, neighbors=neighbors)
        actual = set((np.where(engine.A[t] == 1)[0] + 1).tolist())
        cur = table.head(15).copy().reset_index(drop=True)
        cur["Gerçek"] = cur["Sayı"].astype(int).isin(actual).astype(int)

        old10 = cur.head(10)["Sayı"].astype(int).tolist()
        new10 = old10[:]
        trained = False

        if len(history) >= min_train_draws:
            hist = pd.concat(history[-250:], ignore_index=True)
            if hist["Gerçek"].nunique() == 2:
                Xtr = hist[feat_cols].astype(float).to_numpy()
                ytr = hist["Gerçek"].astype(int).to_numpy()
                reranker = make_pipeline(
                    StandardScaler(),
                    LogisticRegression(max_iter=500, C=0.20, class_weight=None)
                )
                reranker.fit(Xtr, ytr)
                p = reranker.predict_proba(cur[feat_cols].astype(float).to_numpy())[:, 1]
                cur2 = cur.copy()
                cur2["Yeni Olasılık"] = p
                cur2 = cur2.sort_values(
                    ["Yeni Olasılık", "Final Blok Puanı", "Sayı"],
                    ascending=[False, False, True]
                )
                new10 = cur2.head(10)["Sayı"].astype(int).tolist()
                trained = True

        old_hit = len(set(old10) & actual)
        new_hit = len(set(new10) & actual)
        rows.append({
            "Index": t,
            "Çekiliş": int(engine.draw_nos[t]),
            "Eğitim aktif": trained,
            "ESKİ Top10": old_hit,
            "YENİ Top10": new_hit,
            "Fark": new_hit - old_hit,
            "ESKİ sayılar": " - ".join(map(str, old10)),
            "YENİ sayılar": " - ".join(map(str, new10)),
            "Gerçek sonuç": " - ".join(map(str, sorted(actual))),
            "Sinyal": int(info["signal"]),
            "Güven": round(float(info["confidence"]), 3),
            "Ort benzerlik": round(float(info["avg"]), 6),
            "DEVAM olay": round(float(info["event_rate"]["DEVAM"]), 6),
            "BÜYÜME olay": round(float(info["event_rate"]["BÜYÜME"]), 6),
            "KAYMA olay": round(float(info["event_rate"]["KAYMA"]), 6),
            "DOĞUM olay": round(float(info["event_rate"]["DOĞUM"]), 6),
        })

        # Bu çekilişin gerçeği yalnız sonraki çekilişlerde eğitim geçmişine girer.
        history.append(cur[feat_cols + ["Gerçek"]].copy())

    return pd.DataFrame(rows)



def evaluate_dynamic_selector(cmp, min_history=60, window=120, min_bucket=12):
    """
    KONUŞ/PAS seçicisi.
    Her satırda yalnız daha önce sonucu görülmüş karşılaştırma satırlarını kullanır.
    Sabit eşik yok: geçmiş rejim komşularında YENİ-ESKİ farkının pozitif olup
    olmadığına göre karar verir.
    """
    feature_cols = [
        "Sinyal", "Güven", "Ort benzerlik",
        "DEVAM olay", "BÜYÜME olay", "KAYMA olay", "DOĞUM olay"
    ]
    out = cmp.copy()
    out["Seçici"] = "PAS"
    out["Geçmiş benzer olay"] = 0
    out["Beklenen avantaj"] = 0.0

    active_idx = out.index[out["Eğitim aktif"] == True].tolist()
    for pos, idx in enumerate(active_idx):
        past_idx = active_idx[max(0, pos-window):pos]
        if len(past_idx) < min_history:
            continue

        hist = out.loc[past_idx].copy()
        cur = out.loc[idx]

        X = hist[feature_cols].astype(float).to_numpy()
        x = cur[feature_cols].astype(float).to_numpy()
        mu = X.mean(axis=0)
        sd = X.std(axis=0)
        sd[sd < 1e-9] = 1.0
        dist = np.sqrt(np.mean(((X - x) / sd) ** 2, axis=1))

        k = min(max(min_bucket, int(round(len(hist) * 0.20))), len(hist))
        nearest = np.argsort(dist)[:k]
        local = hist.iloc[nearest]
        advantage = float(local["Fark"].mean())

        out.at[idx, "Geçmiş benzer olay"] = int(k)
        out.at[idx, "Beklenen avantaj"] = round(advantage, 4)
        # Pozitif avantaj + en az 12 geçmiş benzer olay. Gelecek bilgisi yok.
        if k >= min_bucket and advantage > 0:
            out.at[idx, "Seçici"] = "KONUŞ"

    out["SEÇİCİ Top10"] = np.where(
        out["Seçici"].eq("KONUŞ"), out["YENİ Top10"], np.nan
    )

    # SIKI V2 filtresi — 500 testin ilk/son yarısında ayrı ayrı doğrulanan
    # basit yapısal fren. Gelecek sonuç kullanmaz; sadece o andaki BLOK
    # özelliklerine bakar. Amaç: fazla KONUŞ'u azaltıp sinyal kalitesini artırmak.
    out["Sıkı Seçici"] = "PAS"
    strict_mask = (
        out["Seçici"].eq("KONUŞ")
        & (out["Sinyal"].astype(float) <= 9.0)
        & (out["KAYMA olay"].astype(float) <= 0.82)
    )
    out.loc[strict_mask, "Sıkı Seçici"] = "KONUŞ"
    out["SIKI Top10"] = np.where(
        out["Sıkı Seçici"].eq("KONUŞ"), out["YENİ Top10"], np.nan
    )
    return out


def summarize_v2(bt):
    rows=[]
    for k in range(3,11):
        avg=float(bt[f"Top{k}"].mean())
        rnd=k*20/80
        rows.append({
            "Koltuk":k,
            "Ort. İsabet":round(avg,3),
            "Rastgele":round(rnd,3),
            "Net Fark":round(avg-rnd,3),
            "Maksimum":int(bt[f"Top{k}"].max()),
            "2+ %":round(float((bt[f"Top{k}"]>=2).mean())*100,1),
        })
    return pd.DataFrame(rows).sort_values("Net Fark",ascending=False)

# -------------------------------------------------------------------
# HAFİF / TELEFON UYUMLU ÇALIŞTIRMA
# Ağır veri hazırlığı uygulama açılırken değil, yalnız TEST butonunda çalışır.
# Sonuçlar session_state içinde tutulur; indirme düğmesine basınca kaybolmaz.
# -------------------------------------------------------------------

st.title("🧪 BLOK TEK LAB — HAFİF + SIKI V2")
st.caption("Dinamik seçici korunur; SIKI V2 yalnız doğrulanmış yapısal bölgede ikinci kez filtreler.")
st.success("✅ Uygulama hazır. Ağır hesap henüz başlamadı.")
st.info("Telefon için hafif mod: Test yalnız aşağıdaki düğmeye bastığında çalışır. SIKI V2, dinamik seçicinin fazla konuşmasını ayrıca frenler.")

neighbors = st.slider("Benzer geçmiş blok durumu", 30, 120, 70, 5, key="lite_neighbors")
tests = st.select_slider(
    "Test adedi",
    options=[100, 250, 500, 750],
    value=250,
    key="lite_tests",
)

if "blok_lite_result" not in st.session_state:
    st.session_state["blok_lite_result"] = None
if "blok_lite_compare" not in st.session_state:
    st.session_state["blok_lite_compare"] = None
if "blok_lite_error" not in st.session_state:
    st.session_state["blok_lite_error"] = None

if st.button("🚀 TESTİ BAŞLAT — ESKİ + YENİ + DİNAMİK SEÇİCİ", type="primary", use_container_width=True):
    st.session_state["blok_lite_result"] = None
    st.session_state["blok_lite_compare"] = None
    st.session_state["blok_lite_error"] = None

    if not BASE_FILE.exists():
        st.session_state["blok_lite_error"] = "veri.txt bulunamadı. app.py ile veri.txt aynı klasörde olmalı."
    else:
        try:
            progress = st.progress(0, text="1/3 — veri.txt okunuyor...")
            raw_text = BASE_FILE.read_text(encoding="utf-8", errors="ignore")
            progress.progress(10, text="1/3 — veri hazırlanıyor...")

            # Ağır kısım: SADECE butona basılınca çalışır.
            df, eng, Xs, ys, ts, invalid_lines = prepare_cached(raw_text)
            progress.progress(45, text=f"2/3 — {len(df)} çekiliş hazır; walk-forward başlıyor...")

            test_n = min(int(tests), max(0, len(df) - 120))
            if test_n <= 0:
                raise ValueError("Test için yeterli geçmiş çekiliş yok.")

            cmp = compare_old_new_block(eng, tests=test_n, neighbors=int(neighbors))
            progress.progress(85, text="3/3 — dinamik seçici hesaplanıyor...")
            selected = evaluate_dynamic_selector(cmp)

            st.session_state["blok_lite_result"] = selected
            st.session_state["blok_lite_compare"] = cmp
            progress.progress(100, text="✅ Test tamamlandı.")
        except Exception as e:
            st.session_state["blok_lite_error"] = f"{type(e).__name__}: {e}"

err = st.session_state.get("blok_lite_error")
if err:
    st.error("Test çalışmadı: " + err)

selected = st.session_state.get("blok_lite_result")
cmp = st.session_state.get("blok_lite_compare")

if isinstance(selected, pd.DataFrame) and not selected.empty:
    valid = selected[selected.get("Eğitim aktif", True) == True].copy() if "Eğitim aktif" in selected.columns else selected.copy()
    spoken = selected[selected["Seçici"] == "KONUŞ"].copy() if "Seçici" in selected.columns else pd.DataFrame()
    strict_spoken = selected[selected["Sıkı Seçici"] == "KONUŞ"].copy() if "Sıkı Seçici" in selected.columns else pd.DataFrame()

    st.subheader("✅ TEST SONUCU")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Test", len(selected))
    if "ESKİ Top10" in valid.columns and len(valid):
        c2.metric("ESKİ Top10 ort.", f"{valid['ESKİ Top10'].mean():.3f}")
    else:
        c2.metric("ESKİ Top10 ort.", "—")
    if "YENİ Top10" in valid.columns and len(valid):
        c3.metric("YENİ Top10 ort.", f"{valid['YENİ Top10'].mean():.3f}")
    else:
        c3.metric("YENİ Top10 ort.", "—")
    c4.metric("KONUŞ", len(spoken))

    if len(spoken) and "YENİ Top10" in spoken.columns:
        st.success(
            f"Dinamik seçici {len(spoken)} kez KONUŞ dedi. "
            f"KONUŞ Top10 ortalaması: {spoken['YENİ Top10'].mean():.3f}"
        )
    else:
        st.warning("Bu testte dinamik seçici KONUŞ koşulu bulamadı veya seçici sütunu oluşmadı.")

    if len(strict_spoken) and "YENİ Top10" in strict_spoken.columns:
        s1,s2,s3,s4 = st.columns(4)
        s1.metric("SIKI KONUŞ", len(strict_spoken))
        s2.metric("SIKI Top10 ort.", f"{strict_spoken['YENİ Top10'].mean():.3f}")
        s3.metric("SIKI 5+", int((strict_spoken['YENİ Top10'] >= 5).sum()))
        s4.metric("SIKI 6+", int((strict_spoken['YENİ Top10'] >= 6).sum()))
        st.success(
            "🎯 SIKI V2 aktif: Dinamik KONUŞ + Sinyal ≤ 9 + KAYMA olay ≤ 0.82. "
            "Bu ikinci katman daha az ama daha seçici sinyal verir."
        )
    else:
        st.info("SIKI V2 bu testte KONUŞ koşulu bulamadı.")

    st.dataframe(selected.sort_values("Çekiliş", ascending=False) if "Çekiliş" in selected.columns else selected,
                 use_container_width=True, hide_index=True)

    # CSV baytları session_state kaynaklı olduğu için indirme tıklaması sonucu yok etmez.
    csv_selected = selected.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ TEST SONUCUNU İNDİR",
        data=csv_selected,
        file_name="BLOK_TEK_LAB_SIKI_V2_TEST.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_selected_lite",
    )

    if isinstance(cmp, pd.DataFrame) and not cmp.empty:
        st.download_button(
            "⬇️ HAM ESKİ-YENİ WALK-FORWARD İNDİR",
            data=cmp.to_csv(index=False).encode("utf-8-sig"),
            file_name="BLOK_ESKI_YENI_WALKFORWARD.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_compare_lite",
        )

    if st.button("🗑️ Test sonucunu temizle", use_container_width=True):
        st.session_state["blok_lite_result"] = None
        st.session_state["blok_lite_compare"] = None
        st.session_state["blok_lite_error"] = None
        st.rerun()
else:
    st.caption("Henüz test çalıştırılmadı. Yukarıdaki TESTİ BAŞLAT düğmesine bas.")
