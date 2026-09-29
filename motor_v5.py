# -*- coding: utf-8 -*-
"""Hizli On Canli Motor V5

V4.1 model mantigini korur; canli ilk-yari -> ikinci-yari akisini,
erken/gec aktivasyon durumlarini ve dinamik kupon portfoyunu uygulama icin sunar.
Hedef cekilis sonucu tahmin aninda kullanilmaz.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from collections import Counter
from itertools import combinations
import io
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

EXPECTED_MINUTES = [2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57]
TARGET_INDEXES = range(6, 12)

STATE_TR = {
    "ERKEN_DEVAM": "Erken aktif + devam",
    "GEC_YUKSELIS": "Geç aktive / yükseliş",
    "ERKEN_SONEN": "Erken aktif + sönen",
    "SONRADAN_GIREN": "İlk 6'da yok, sonradan giren",
    "HALA_YOK": "Henüz hiç çıkmayan",
    "IKI_BLOKTA": "İki blokta görünen",
    "TEK_BLOK": "Tek blokta görünen",
}


def _parse_lines(lines):
    rows = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("="):
            continue
        p = line.split(";")
        if len(p) >= 3 and p[0].isdigit():
            dt = datetime.strptime(p[1].strip(), "%d.%m.%Y %H:%M")
            nums = tuple(int(x) for x in p[2].split(",") if x.strip())
            if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
                raise ValueError(f"Geçersiz çekiliş: {line}")
            rows.append((int(p[0]), dt, nums))
    df = pd.DataFrame(rows, columns=["draw_id", "dt", "nums"])
    if df.empty:
        return pd.DataFrame(columns=["draw_id", "dt", "nums", "date", "hour", "minute"])
    df = df.drop_duplicates(subset=["draw_id"], keep="last").sort_values("dt").reset_index(drop=True)
    df["date"] = df["dt"].dt.date
    df["hour"] = df["dt"].dt.hour
    df["minute"] = df["dt"].dt.minute
    return df


def load_txt(path: str | Path) -> pd.DataFrame:
    return _parse_lines(Path(path).read_text(encoding="utf-8").splitlines())


def load_txt_text(text: str) -> pd.DataFrame:
    return _parse_lines(text.splitlines())


def dataframe_to_txt(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    lines = []
    for d, gd in df.sort_values("dt").groupby("date"):
        lines.append(f"===== {d.strftime('%d.%m.%Y')} | {len(gd)} ÇEKİLİŞ =====")
        for _, r in gd.sort_values("dt").iterrows():
            nums = ",".join(map(str, r["nums"]))
            lines.append(f"{int(r['draw_id'])};{r['dt'].strftime('%d.%m.%Y %H:%M')};{nums}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def append_draw(df: pd.DataFrame, draw_id: int, dt: datetime, nums: list[int] | tuple[int, ...]) -> pd.DataFrame:
    nums = tuple(sorted(map(int, nums)))
    if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
        raise ValueError("Tam 20 farklı sayı gerekli; sayılar 1-80 arasında olmalı.")
    if int(draw_id) in set(df["draw_id"].astype(int).tolist()):
        raise ValueError("Bu çekiliş numarası zaten kayıtlı.")
    if not df.empty and dt in set(df["dt"].tolist()):
        raise ValueError("Bu tarih-saat zaten kayıtlı.")
    row = pd.DataFrame([{"draw_id": int(draw_id), "dt": pd.Timestamp(dt), "nums": nums}])
    row["date"] = row["dt"].dt.date
    row["hour"] = row["dt"].dt.hour
    row["minute"] = row["dt"].dt.minute
    return pd.concat([df, row], ignore_index=True).sort_values("dt").reset_index(drop=True)


def full_sessions(df: pd.DataFrame):
    out = {}
    if df.empty:
        return out
    for (d, h), g in df.groupby(["date", "hour"]):
        mins = sorted(g["minute"].astype(int).tolist())
        if mins == EXPECTED_MINUTES:
            g = g.sort_values("minute")
            out[(d, int(h))] = [set(x) for x in g["nums"]]
    return out


def ordered_prefix_hour(df: pd.DataFrame, d, hour: int):
    g = df[(df["date"] == d) & (df["hour"] == hour)].sort_values("minute")
    if g.empty:
        return [], g
    mins = g["minute"].astype(int).tolist()
    prefix = []
    for m in EXPECTED_MINUTES:
        if m in mins:
            prefix.append(m)
        else:
            break
    draws = [set(g.loc[g["minute"] == m, "nums"].iloc[0]) for m in prefix]
    return draws, g


def last_gap(obs, n):
    for gap, s in enumerate(reversed(obs)):
        if n in s:
            return min(gap, 6)
    return 7


class DynamicCouponEngine:
    def __init__(self, train_sessions):
        self.train_sessions = train_sessions
        self._build_history_stats()
        self._fit_models()

    def _build_history_stats(self):
        self.cnt_num = Counter(); self.cnt_num_min = Counter(); self.cnt_num_hour = Counter()
        self.den_min = Counter(); self.den_hour = Counter()
        self.state_min_den = Counter(); self.state_min_hit = Counter()
        for (d, hour), draws in self.train_sessions.items():
            for idx in TARGET_INDEXES:
                minute = EXPECTED_MINUTES[idx]
                target = draws[idx]
                self.den_min[minute] += 1
                self.den_hour[hour] += 1
                for n in target:
                    self.cnt_num[n] += 1
                    self.cnt_num_min[(n, minute)] += 1
                    self.cnt_num_hour[(n, hour)] += 1
                for n in range(1, 81):
                    st = self.state_name(draws, idx, n)
                    self.state_min_den[(st, minute)] += 1
                    self.state_min_hit[(st, minute)] += int(n in target)
        self.total_target_draws = max(1, len(self.train_sessions) * 6)

    def _smoothed_rate(self, n, minute, hour):
        base = (self.cnt_num[n] + 10 * 0.25) / (self.total_target_draws + 10)
        mr = (self.cnt_num_min[(n, minute)] + 20 * base) / (self.den_min[minute] + 20)
        hr = (self.cnt_num_hour[(n, hour)] + 40 * base) / (self.den_hour[hour] + 40)
        return base, mr, hr

    def state_name(self, draws, obs_count, n):
        e3 = sum(n in s for s in draws[:3])
        s3 = sum(n in s for s in draws[3:6])
        first6 = e3 + s3
        post6 = sum(n in s for s in draws[6:obs_count]) if obs_count > 6 else 0
        if first6 == 0 and post6 == 0: return "HALA_YOK"
        if first6 == 0 and post6 > 0: return "SONRADAN_GIREN"
        if e3 >= 2 and s3 == 0: return "ERKEN_SONEN"
        if e3 <= 1 and s3 >= 2: return "GEC_YUKSELIS"
        if e3 >= 2 and s3 >= 1: return "ERKEN_DEVAM"
        if e3 >= 1 and s3 >= 1: return "IKI_BLOKTA"
        return "TEK_BLOK"

    def features(self, draws, obs_count, n, hour, target_min):
        obs = draws[:obs_count]
        e3 = sum(n in s for s in draws[:3])
        s3 = sum(n in s for s in draws[3:6])
        first6 = e3 + s3
        obs_total = sum(n in s for s in obs)
        recent3 = sum(n in s for s in obs[-3:])
        prev3 = sum(n in s for s in obs[-6:-3]) if len(obs) >= 6 else 0
        last2 = sum(n in s for s in obs[-2:])
        last1 = int(n in obs[-1])
        gap = last_gap(obs, n)
        post6 = sum(n in s for s in obs[6:]) if obs_count > 6 else 0
        co = Counter()
        for s in obs:
            if n in s:
                for m in s:
                    if m != n: co[m] += 1
        pair_support = sum(1 for c in co.values() if c >= 2)
        pair_excess = sum(max(0, c - 1) for c in co.values())
        max_pair = max(co.values(), default=0)
        base, mf, hf = self._smoothed_rate(n, target_min, hour)
        return [
            hour, target_min, (n - 1) // 10, base, mf, hf,
            e3, s3, first6, obs_total, recent3, prev3, last2, last1, gap,
            int(e3 >= 2), int(s3 >= 2), int(e3 >= 1 and s3 >= 1),
            int(e3 >= 2 and s3 == 0), int(e3 <= 1 and s3 >= 2), int(first6 == 0),
            post6, int(first6 == 0 and post6 > 0), int(first6 == 0 and post6 == 0),
            recent3 - prev3, pair_support, pair_excess, max_pair
        ]

    def _fit_one(self, X, y):
        m = HistGradientBoostingClassifier(
            learning_rate=0.05, max_iter=160, max_leaf_nodes=31,
            min_samples_leaf=80, l2_regularization=8.0, random_state=42
        )
        m.fit(X, np.asarray(y, dtype=int))
        return m

    def _fit_models(self):
        X = []; yn = []; yany = []; y4 = []; y5 = []
        for (d, hour), draws in self.train_sessions.items():
            final_counts = {n: sum(n in s for s in draws) for n in range(1, 81)}
            for idx in TARGET_INDEXES:
                minute = EXPECTED_MINUTES[idx]
                for n in range(1, 81):
                    X.append(self.features(draws, idx, n, hour, minute))
                    yn.append(int(n in draws[idx]))
                    yany.append(int(any(n in s for s in draws[idx:])))
                    y4.append(int(final_counts[n] >= 4))
                    y5.append(int(final_counts[n] >= 5))
        if not X:
            raise ValueError("Motor eğitimi için geçmişte tam saat verisi yok.")
        X = np.asarray(X, dtype=float)
        self.m_next = self._fit_one(X, yn)
        self.m_any = self._fit_one(X, yany)
        self.m4 = self._fit_one(X, y4)
        self.m5 = self._fit_one(X, y5)

    def score_numbers(self, draws, obs_count, hour):
        target_min = EXPECTED_MINUTES[obs_count]
        F = np.asarray([self.features(draws, obs_count, n, hour, target_min) for n in range(1, 81)], dtype=float)
        pn = self.m_next.predict_proba(F)[:, 1]
        pa = self.m_any.predict_proba(F)[:, 1]
        p4 = self.m4.predict_proba(F)[:, 1]
        p5 = self.m5.predict_proba(F)[:, 1]
        base_score = .50 * pn + .20 * pa + .20 * p4 + .10 * p5
        rec = []
        for n in range(1, 81):
            st = self.state_name(draws, obs_count, n)
            den = self.state_min_den[(st, target_min)]
            state_rate = (self.state_min_hit[(st, target_min)] / den) if den else 0.25
            final_score = float(base_score[n - 1] + 0.50 * (state_rate - 0.25))
            e3 = sum(n in s for s in draws[:3])
            s3 = sum(n in s for s in draws[3:6])
            post6 = sum(n in s for s in draws[6:obs_count]) if obs_count > 6 else 0
            total = sum(n in s for s in draws[:obs_count])
            rec.append({
                "Sayi": n,
                "Skor": final_score,
                "HamSkor": float(base_score[n - 1]),
                "P_Next": float(pn[n - 1]),
                "P_KalanSaat": float(pa[n - 1]),
                "P_Final4": float(p4[n - 1]),
                "P_Final5": float(p5[n - 1]),
                "Durum": st,
                "DurumTR": STATE_TR.get(st, st),
                "DurumDakikaOrani": float(state_rate),
                "Ilk3": e3,
                "Ikinci3": s3,
                "Ilk6": e3 + s3,
                "Sonrasi": post6,
                "ToplamGorulme": total,
                "SonBosluk": last_gap(draws[:obs_count], n),
            })
        return pd.DataFrame(rec).sort_values(["Skor", "Sayi"], ascending=[False, True]).reset_index(drop=True)

    def coupons6(self, ranked):
        candidates = ranked.head(12)["Sayi"].astype(int).tolist()
        if len(candidates) < 12:
            raise ValueError("En az 12 aday gerekli.")
        power = ranked.sort_values(["HamSkor", "Sayi"], ascending=[False, True]).head(6)["Sayi"].astype(int).tolist()
        pattern = [
            [0, 1, 2, 6, 7, 8],
            [0, 3, 4, 6, 9, 10],
            [1, 3, 5, 7, 9, 11],
            [2, 4, 5, 8, 10, 11],
        ]
        return [tuple(power)] + [tuple(candidates[i] for i in idxs) for idxs in pattern]

    def diverse_coupons(self, ranked, k=6, nvar=5, topn=16):
        if k == 6 and nvar == 5:
            return self.coupons6(ranked)
        top = ranked.head(max(topn, k + 4)).copy()
        nums = top["Sayi"].astype(int).tolist()
        score = dict(zip(top["Sayi"].astype(int), top["Skor"].astype(float)))
        # exact combos are manageable for k <= 7 and topn <= 16
        combos = list(combinations(nums, k))
        base = {c: sum(score[n] for n in c) for c in combos}
        selected = []
        remaining = set(combos)
        while remaining and len(selected) < nvar:
            best = None; bestkey = None
            for c in remaining:
                overlap = sum(len(set(c) & set(s)) for s in selected)
                key = (base[c] - 0.12 * overlap, base[c], tuple(-x for x in c))
                if bestkey is None or key > bestkey:
                    bestkey = key; best = c
            selected.append(best); remaining.remove(best)
        return selected


def build_engine_for_live(df: pd.DataFrame, live_date):
    train = full_sessions(df[df["date"] < live_date])
    if not train:
        raise ValueError("Canlı günden önce yeterli tam saat verisi yok.")
    return DynamicCouponEngine(train)


def live_analysis(df: pd.DataFrame, live_date=None, hour=None, coupon_size=6, nvar=5):
    if df.empty:
        raise ValueError("Veri boş.")
    if live_date is None:
        live_date = df["date"].max()
    day = df[df["date"] == live_date]
    if day.empty:
        raise ValueError("Seçilen günde veri yok.")
    if hour is None:
        candidate_hours = []
        for h, g in day.groupby("hour"):
            draws, _ = ordered_prefix_hour(df, live_date, int(h))
            if 1 <= len(draws) < 12:
                candidate_hours.append(int(h))
        if candidate_hours:
            hour = max(candidate_hours)
        else:
            hour = int(day["hour"].max())
    draws, raw = ordered_prefix_hour(df, live_date, int(hour))
    obs_count = len(draws)
    result = {
        "date": live_date,
        "hour": int(hour),
        "draws": draws,
        "obs_count": obs_count,
        "raw": raw,
        "target_min": EXPECTED_MINUTES[obs_count] if obs_count < 12 else None,
        "ranked": None,
        "coupons": [],
    }
    if 6 <= obs_count < 12:
        eng = build_engine_for_live(df, live_date)
        ranked = eng.score_numbers(draws, obs_count, int(hour))
        result["ranked"] = ranked
        result["coupons"] = eng.diverse_coupons(ranked, k=coupon_size, nvar=nvar)
    return result


def historical_phase_table(df: pd.DataFrame, d, hour: int):
    draws, raw = ordered_prefix_hour(df, d, hour)
    rows = []
    for n in range(1, 81):
        e3 = sum(n in s for s in draws[:3])
        s3 = sum(n in s for s in draws[3:6])
        post = sum(n in s for s in draws[6:]) if len(draws) > 6 else 0
        rows.append({"Sayi": n, "Ilk3": e3, "Ikinci3": s3, "Ilk6": e3+s3, "IkinciYari": post, "SaatToplam": e3+s3+post})
    return pd.DataFrame(rows)
