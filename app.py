# -*- coding: utf-8 -*-
import io
import math
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st

APP_TITLE = "🎯 Hızlı On — Canlı Ritim Saat & Çekiliş Merkezi V1"
DEFAULT_RAW_URL = "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"
SEED_COVERAGE_START = datetime(2026, 8, 1).date()
SEED_COVERAGE_END = datetime(2026, 10, 9).date()
SEEDS = [{'size': 6, 'family': '3-10-21-28-48-53', 'gaps': [7, 14], 'source_level': 'ULTRA6', 'seed_score': 86.4}, {'size': 6, 'family': '6-12-20-43-57-74', 'gaps': [7, 14], 'source_level': 'ULTRA6', 'seed_score': 81.0}, {'size': 6, 'family': '9-15-20-34-44-64', 'gaps': [5, 14], 'source_level': 'ULTRA6', 'seed_score': 72.6}, {'size': 6, 'family': '9-42-52-57-67-68', 'gaps': [2, 7, 14], 'source_level': 'ULTRA6', 'seed_score': 71.2}, {'size': 6, 'family': '6-12-23-50-70-80', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 89.8}, {'size': 6, 'family': '3-21-29-51-59-65', 'gaps': [2, 14], 'source_level': 'TOP50-6', 'seed_score': 87.5}, {'size': 6, 'family': '19-36-37-41-46-77', 'gaps': [2, 7, 14], 'source_level': 'TOP50-6', 'seed_score': 85.9}, {'size': 6, 'family': '3-21-24-25-32-78', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 94.8}, {'size': 6, 'family': '15-35-37-38-64-67', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 89.8}, {'size': 6, 'family': '5-34-48-56-63-67', 'gaps': [2, 5, 7], 'source_level': 'TOP50-6', 'seed_score': 89.8}, {'size': 6, 'family': '1-10-19-21-43-79', 'gaps': [2, 5, 7, 14], 'source_level': 'TOP50-6', 'seed_score': 87.5}, {'size': 6, 'family': '7-33-34-48-64-72', 'gaps': [2, 5, 7], 'source_level': 'TOP50-6', 'seed_score': 82.5}, {'size': 6, 'family': '14-35-36-54-64-66', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 87.2}, {'size': 6, 'family': '24-31-52-66-67-77', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 87.2}, {'size': 6, 'family': '20-27-30-45-51-52', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 86.5}, {'size': 6, 'family': '21-22-37-46-54-80', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 86.5}, {'size': 6, 'family': '2-17-42-43-62-66', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 86.5}, {'size': 6, 'family': '11-30-48-49-78-79', 'gaps': [2, 14], 'source_level': 'TOP50-6', 'seed_score': 86.4}, {'size': 6, 'family': '1-24-31-40-56-68', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 85.0}, {'size': 6, 'family': '5-20-43-53-61-69', 'gaps': [5, 7, 14], 'source_level': 'TOP50-6', 'seed_score': 85.0}, {'size': 6, 'family': '9-13-25-31-43-68', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 85.0}, {'size': 6, 'family': '1-11-18-26-39-52', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 84.4}, {'size': 6, 'family': '9-22-60-61-65-75', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 84.4}, {'size': 6, 'family': '21-28-37-62-64-71', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 84.4}, {'size': 6, 'family': '4-25-38-47-61-64', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 84.4}, {'size': 6, 'family': '16-26-43-52-58-69', 'gaps': [2, 5, 7, 14], 'source_level': 'TOP50-6', 'seed_score': 83.9}, {'size': 6, 'family': '18-22-28-38-39-73', 'gaps': [2, 14], 'source_level': 'TOP50-6', 'seed_score': 83.9}, {'size': 6, 'family': '6-21-35-46-53-63', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '8-12-27-63-74-77', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '1-26-32-37-50-77', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '12-23-66-70-72-75', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '7-17-22-28-44-53', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '20-32-53-57-71-74', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '18-35-48-53-66-71', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '5-7-31-40-77-79', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '4-6-27-31-32-36', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '6-21-26-37-40-67', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '22-26-44-58-66-71', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 82.2}, {'size': 6, 'family': '5-8-12-27-74-77', 'gaps': [5, 7, 14], 'source_level': 'TOP50-6', 'seed_score': 81.5}, {'size': 6, 'family': '11-20-28-47-79-80', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 81.5}, {'size': 6, 'family': '14-22-27-39-48-70', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 81.5}, {'size': 6, 'family': '3-22-26-27-35-48', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 81.5}, {'size': 6, 'family': '8-11-12-23-25-68', 'gaps': [2, 5, 7, 14], 'source_level': 'TOP50-6', 'seed_score': 81.4}, {'size': 6, 'family': '1-4-35-54-67-72', 'gaps': [2, 5], 'source_level': 'TOP50-6', 'seed_score': 81.4}, {'size': 6, 'family': '4-5-24-52-55-69', 'gaps': [2, 5, 7], 'source_level': 'TOP50-6', 'seed_score': 80.0}, {'size': 6, 'family': '5-7-14-22-25-70', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 80.0}, {'size': 6, 'family': '7-21-36-48-59-71', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 79.4}, {'size': 6, 'family': '2-59-62-68-73-78', 'gaps': [7, 14], 'source_level': 'TOP50-6', 'seed_score': 77.2}, {'size': 6, 'family': '5-21-41-57-69-77', 'gaps': [5, 7], 'source_level': 'TOP50-6', 'seed_score': 88.8}, {'size': 6, 'family': '2-3-14-29-34-70', 'gaps': [5, 14], 'source_level': 'TOP50-6', 'seed_score': 85.8}, {'size': 7, 'family': '17-27-32-35-42-70-72', 'gaps': [5], 'source_level': 'TOP50-7', 'seed_score': 133.0}, {'size': 7, 'family': '9-28-44-49-56-57-78', 'gaps': [7], 'source_level': 'TOP50-7', 'seed_score': 123.0}, {'size': 7, 'family': '23-37-43-48-61-71-72', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-6-17-37-63-71-75', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '19-24-51-67-71-72-78', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '21-36-48-52-56-61-73', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '3-27-55-59-66-76-79', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '23-39-43-48-61-71-72', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '17-19-29-48-49-55-60', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '1-3-7-28-32-55-65', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '29-43-50-65-69-73-79', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '23-43-46-51-56-74-75', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-27-36-45-53-76-77', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '4-15-18-43-52-63-78', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '5-15-16-36-48-50-61', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '3-9-13-25-36-46-62', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '3-10-16-22-36-60-70', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '33-36-55-66-68-71-80', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '24-28-45-68-70-72-80', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '12-15-29-38-44-72-74', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-3-16-34-58-59-61', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '9-18-30-41-57-59-63', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '5-8-9-51-57-59-66', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-3-16-34-58-59-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-3-16-34-58-61-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-3-16-34-59-61-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-3-16-58-59-61-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-3-34-58-59-61-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-16-34-58-59-61-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '3-16-34-58-59-61-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '13-27-30-34-59-60-69', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '6-17-25-27-50-65-69', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '21-22-28-38-39-70-71', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '5-8-9-51-57-66-74', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '21-24-37-46-60-66-77', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '13-14-16-38-41-56-60', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '21-22-49-55-62-63-80', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '3-7-11-29-38-71-79', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '5-8-9-22-54-55-80', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '6-16-34-52-57-71-73', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '13-16-20-22-39-49-53', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '8-12-14-45-60-62-67', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '7-31-34-35-44-66-72', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '34-41-44-49-59-78-79', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '15-17-41-46-47-53-74', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '8-10-22-26-52-57-79', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '2-29-41-54-55-61-76', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '29-50-63-71-74-78-79', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '5-23-28-46-53-54-75', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 7, 'family': '1-2-19-22-23-34-48', 'gaps': [2], 'source_level': 'TOP50-7', 'seed_score': 121.0}, {'size': 8, 'family': '2-3-16-34-58-59-61-67', 'gaps': [2], 'source_level': 'SERT8', 'seed_score': 121.0}, {'size': 8, 'family': '10-12-17-19-46-55-66-79', 'gaps': [2], 'source_level': 'SERT8', 'seed_score': 121.0}, {'size': 8, 'family': '1-17-27-32-35-42-70-72', 'gaps': [5], 'source_level': 'SERT8', 'seed_score': 121.0}, {'size': 8, 'family': '1-3-5-10-27-31-34-69', 'gaps': [7], 'source_level': 'SERT8', 'seed_score': 121.0}, {'size': 8, 'family': '22-28-32-55-56-67-74-80', 'gaps': [7], 'source_level': 'SERT8', 'seed_score': 121.0}, {'size': 10, 'family': '25-28-34-38-42-44-48-54-60-68', 'gaps': [2], 'source_level': 'ULTRA', 'seed_score': 100.0}, {'size': 10, 'family': '1-5-7-19-34-47-59-70-74-76', 'gaps': [2, 5], 'source_level': 'ADAY-ÇOKLU-GAP', 'seed_score': 50.0}, {'size': 10, 'family': '2-6-8-11-23-25-28-45-51-66', 'gaps': [2, 5], 'source_level': 'ADAY-ÇOKLU-GAP', 'seed_score': 50.0}]

st.set_page_config(page_title="Ritim Saat & Çekiliş Merkezi", page_icon="🎯", layout="wide")
st.title(APP_TITLE)
st.caption("6’lı + 7’li + 8’li + 10’lu dar çekirdek | aile+gap özel saat kimliği | gün içi çekiliş sırası | canlı hedef günü")
st.info(
    "Bu app yeni kombinasyon madenciliği yapmaz. Daha önce dar çekirdeğe giren ailelerin gerçek geçmiş vuruşlarını yeniden okuyup "
    "her aile + gün-gap için saat ve gün içi çekiliş kimliği çıkarır. Saat ve çekiliş iki ayrı bağımsız sinyal değildir; "
    "aynı zaman düzeninin iki görünümüdür. Sinyal yoksa kupon üretmez."
)

# ============================================================
# YARDIMCILAR
# ============================================================
def nums_to_split_mask(nums):
    lo = 0
    hi = 0
    for n in nums:
        n = int(n)
        if n <= 64:
            lo |= 1 << (n - 1)
        else:
            hi |= 1 << (n - 65)
    return np.uint64(lo), np.uint64(hi)


def family_nums(name):
    return tuple(sorted(int(x) for x in str(name).split("-") if str(x).strip()))


def safe_dataframe(data, max_rows=250):
    if not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data)
    if data.empty:
        st.info("Gösterilecek kayıt yok.")
        return
    df = data.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%d.%m.%Y %H:%M")
        elif pd.api.types.is_object_dtype(df[c]):
            df[c] = df[c].map(lambda x: "" if x is None else str(x))
    shown = df.head(max_rows)
    html = shown.to_html(index=False, escape=True, border=0)
    st.markdown(
        """
        <style>
        .ho-wrap{overflow-x:auto;max-width:100%;border:1px solid #ddd;border-radius:8px}
        .ho-wrap table{border-collapse:collapse;width:max-content;min-width:100%;font-size:.82rem}
        .ho-wrap th,.ho-wrap td{padding:6px 9px;border-bottom:1px solid #eee;white-space:nowrap;text-align:left}
        .ho-wrap th{position:sticky;top:0;background:#f6f7f9;z-index:1}
        </style>
        <div class="ho-wrap">""" + html + "</div>",
        unsafe_allow_html=True,
    )
    if len(df) > len(shown):
        st.caption(f"Ekranda ilk {len(shown)} / {len(df)} kayıt. Tam liste raporda.")


def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def build_zip(files):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8-sig")
            z.writestr(name, data)
    return bio.getvalue()


def hm(minute):
    minute = int(minute) % 1440
    return f"{minute//60:02d}:{minute%60:02d}"


def parse_gap_list(x):
    if isinstance(x, list):
        return [int(v) for v in x]
    out = []
    cur = ""
    for ch in str(x):
        if ch.isdigit():
            cur += ch
        elif cur:
            out.append(int(cur))
            cur = ""
    if cur:
        out.append(int(cur))
    return sorted(set(out))


def best_minute_window(minutes, width=60):
    vals = sorted(int(x) % 1440 for x in minutes)
    n = len(vals)
    if n == 0:
        return "", 0, 0.0
    ext = vals + [x + 1440 for x in vals]
    best_n, best_i, j = 1, 0, 0
    for i in range(n):
        if j < i:
            j = i
        while j < i + n and ext[j] - ext[i] <= int(width):
            j += 1
        cnt = j - i
        if cnt > best_n:
            best_n, best_i = cnt, i
    start = ext[best_i] % 1440
    end = (ext[best_i] + int(width)) % 1440
    return f"{hm(start)}–{hm(end)}", int(best_n), float(best_n / n)


def best_pos_band(positions, width=7):
    vals = sorted(int(x) for x in positions)
    if not vals:
        return None, None, 0, 0.0
    best_n, best_start = 1, vals[0]
    j = 0
    for i, start in enumerate(vals):
        if j < i:
            j = i
        while j < len(vals) and vals[j] <= start + int(width) - 1:
            j += 1
        cnt = j - i
        if cnt > best_n:
            best_n, best_start = cnt, start
    return int(best_start), int(best_start + int(width) - 1), int(best_n), float(best_n / len(vals))


def chain_ending_at(active_set, end_day, gap):
    if end_day is None:
        return 0
    n = 1
    d = end_day
    while d - timedelta(days=int(gap)) in active_set:
        n += 1
        d -= timedelta(days=int(gap))
    return n


def expected_time_segments(schedule_map, a, b):
    pts = []
    for p in range(int(a), int(b) + 1):
        t = schedule_map.get(p)
        if t:
            h, m = map(int, t.split(":"))
            pts.append((p, h * 60 + m, t))
    if not pts:
        return ""
    segs = []
    start = prev = pts[0]
    for cur in pts[1:]:
        if cur[1] - prev[1] > 65:
            segs.append((start[2], prev[2]))
            start = cur
        prev = cur
    segs.append((start[2], prev[2]))
    return " / ".join(a if a == b else f"{a}–{b}" for a, b in segs)


# ============================================================
# VERİ
# ============================================================
@st.cache_data(ttl=90, show_spinner=False)
def fetch_text(url, cache_bust=0):
    sep = "&" if "?" in url else "?"
    r = requests.get(
        f"{url}{sep}_cb={cache_bust}",
        timeout=35,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    r.raise_for_status()
    return r.text


@st.cache_data(show_spinner=False)
def parse_veri(text):
    base = []
    seen = set()
    for raw in text.splitlines():
        p = raw.strip().split(";")
        if len(p) != 3:
            continue
        try:
            draw_id = int(p[0].strip())
            dt = datetime.strptime(p[1].strip(), "%d.%m.%Y %H:%M")
            nums = tuple(sorted(int(x.strip()) for x in p[2].split(",") if x.strip()))
        except Exception:
            continue
        if draw_id in seen or len(nums) != 20 or len(set(nums)) != 20:
            continue
        if not all(1 <= n <= 80 for n in nums):
            continue
        seen.add(draw_id)
        lo, hi = nums_to_split_mask(nums)
        base.append((draw_id, dt, nums, int(lo), int(hi)))
    base.sort(key=lambda x: x[1])
    rows = []
    daily_counter = defaultdict(int)
    hour_counter = defaultdict(int)
    for draw_id, dt, nums, lo, hi in base:
        d = dt.date()
        hk = (d, dt.hour)
        daily_counter[d] += 1
        hour_counter[hk] += 1
        rows.append({
            "draw_id": int(draw_id), "dt": dt, "date": d, "nums": nums,
            "lo": int(lo), "hi": int(hi), "day_pos": int(daily_counter[d]),
            "hour_pos": int(hour_counter[hk]), "minute_day": int(dt.hour * 60 + dt.minute),
        })
    return rows


def build_schedule_map(records):
    c = defaultdict(Counter)
    for r in records:
        c[int(r["day_pos"])][r["dt"].strftime("%H:%M")] += 1
    return {p: cnt.most_common(1)[0][0] for p, cnt in c.items() if cnt}


def family_hit_indices(records, fam):
    nums = family_nums(fam)
    flo, fhi = nums_to_split_mask(nums)
    lo = np.fromiter((r["lo"] for r in records), dtype=np.uint64, count=len(records))
    hi = np.fromiter((r["hi"] for r in records), dtype=np.uint64, count=len(records))
    mask = ((lo & flo) == flo) & ((hi & fhi) == fhi)
    return np.flatnonzero(mask).tolist()


def choose_closest_pair(day1_hits, day2_hits):
    if not day1_hits or not day2_hits:
        return None
    best = None
    for a in day1_hits:
        for b in day2_hits:
            key = (
                abs(int(b["day_pos"]) - int(a["day_pos"])),
                abs(int(b["minute_day"]) - int(a["minute_day"])),
            )
            if best is None or key < best[0]:
                best = (key, a, b)
    return best[1], best[2]


@st.cache_data(show_spinner=False)
def analyze_identity(text, draw_band_width=7, minute_window=60):
    records = parse_veri(text)
    if not records:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}, records
    schedule = build_schedule_map(records)
    max_pos = max(schedule) if schedule else 217

    lo_arr = np.fromiter((r["lo"] for r in records), dtype=np.uint64, count=len(records))
    hi_arr = np.fromiter((r["hi"] for r in records), dtype=np.uint64, count=len(records))

    all_profile_rows = []
    all_link_rows = []
    event_rows = []

    for seed in SEEDS:
        fam = seed["family"]
        k = int(seed["size"])
        nums = family_nums(fam)
        flo, fhi = nums_to_split_mask(nums)
        mask = ((lo_arr & flo) == flo) & ((hi_arr & fhi) == fhi)
        hit_idx = np.flatnonzero(mask).tolist()
        hits = [records[i] for i in hit_idx]
        bydate = defaultdict(list)
        for h in hits:
            bydate[h["date"]].append(h)
        active_dates = sorted(bydate)
        active_set = set(active_dates)

        for gap in parse_gap_list(seed.get("gaps", [])):
            links = []
            rhythm_days = set()
            for d1 in active_dates:
                d2 = d1 + timedelta(days=int(gap))
                if d2 not in active_set:
                    continue
                pair = choose_closest_pair(bydate[d1], bydate[d2])
                if pair is None:
                    continue
                a, b = pair
                rhythm_days.update([d1, d2])
                links.append({
                    "Aile Boyutu": k, "Aile": fam, "Kaynak Seviye": seed["source_level"],
                    "Gün Gap": int(gap), "1. Gün": d1.isoformat(), "2. Gün": d2.isoformat(),
                    "1. Saat": a["dt"].strftime("%H:%M"), "2. Saat": b["dt"].strftime("%H:%M"),
                    "1. Günlük Sıra": int(a["day_pos"]), "2. Günlük Sıra": int(b["day_pos"]),
                    "Sıra Kayması": int(b["day_pos"] - a["day_pos"]),
                    "1. Çekiliş No": int(a["draw_id"]), "2. Çekiliş No": int(b["draw_id"]),
                })

            rhythm_hits = [h for h in hits if h["date"] in rhythm_days]
            identity_hits = rhythm_hits if rhythm_hits else hits
            for h in identity_hits:
                event_rows.append({
                    "Aile Boyutu": k, "Aile": fam, "Gün Gap": int(gap), "Tarih": h["date"].isoformat(),
                    "Saat": h["dt"].strftime("%H:%M"), "Günlük Sıra": int(h["day_pos"]),
                    "Saat İçi Sıra": int(h["hour_pos"]), "Çekiliş No": int(h["draw_id"]),
                })

            shifts = [int(x["Sıra Kayması"]) for x in links]
            link_n = len(links)
            latest = max(links, key=lambda x: x["2. Gün"]) if links else None
            latest_end = datetime.strptime(latest["2. Gün"], "%Y-%m-%d").date() if latest else None
            next_expected = latest_end + timedelta(days=int(gap)) if latest_end else None
            chain_len = chain_ending_at(active_set, latest_end, int(gap)) if latest_end else 0

            mins = [h["minute_day"] for h in identity_hits]
            positions = [h["day_pos"] for h in identity_hits]
            minute_label, minute_n, minute_ratio = best_minute_window(mins, int(minute_window))
            pos_a, pos_b, pos_n, pos_ratio = best_pos_band(positions, int(draw_band_width))

            shift_med = float(np.median(shifts)) if shifts else np.nan
            shift_mad = float(np.median(np.abs(np.array(shifts) - shift_med))) if shifts else np.nan
            pred_pos = None
            pred_a = pred_b = None
            pred_time = pred_time_band = ""
            if latest and shifts:
                pred_pos = int(round(int(latest["2. Günlük Sıra"]) + shift_med))
                pred_pos = max(1, min(int(max_pos), pred_pos))
                radius = int(max(2, min(8, math.ceil((shift_mad if not np.isnan(shift_mad) else 4) * 1.5) + 2)))
                pred_a = max(1, pred_pos - radius)
                pred_b = min(int(max_pos), pred_pos + radius)
                pred_time = schedule.get(pred_pos, "")
                pred_time_band = expected_time_segments(schedule, pred_a, pred_b)

            sample_factor = min(1.0, link_n / 4.0)
            shift_consistency = 0.0 if not shifts else max(0.0, 1.0 - (shift_mad / 12.0))
            cluster = float(minute_ratio)
            timing_score = round(100 * (0.45 * sample_factor + 0.35 * shift_consistency + 0.20 * cluster))
            if link_n >= 3 and timing_score >= 70:
                timing_level = "GÜÇLÜ"
            elif link_n >= 2 and timing_score >= 50:
                timing_level = "ORTA"
            else:
                timing_level = "ZAYIF"

            dominant_hour = ""
            dominant_hour_n = 0
            if identity_hits:
                hc = Counter(h["dt"].hour for h in identity_hits)
                hh, nn = hc.most_common(1)[0]
                dominant_hour = f"{int(hh):02d}:00–{int(hh):02d}:59"
                dominant_hour_n = int(nn)

            all_profile_rows.append({
                "Aile Boyutu": k,
                "Aile": fam,
                "Kaynak Seviye": seed["source_level"],
                "Kaynak Puan": seed.get("seed_score", 0),
                "Gün Gap": int(gap),
                "Toplam Görünüş": len(hits),
                "Aktif Gün": len(active_dates),
                "Gap Bağı": int(link_n),
                "Son Bağ Sonu": latest_end.isoformat() if latest_end else "",
                "Son Zincir Tarih": int(chain_len),
                "Sıradaki Ritim Tarihi": next_expected.isoformat() if next_expected else "",
                "Ritim Olayı": len(identity_hits),
                "Baskın Saat": dominant_hour,
                "Baskın Saat Tekrar": dominant_hour_n,
                f"{minute_window}dk Saat Penceresi": minute_label,
                "Saat Pencere Tekrar": int(minute_n),
                "Saat Pencere Oranı": round(float(minute_ratio), 3),
                "Tarihsel Günlük Sıra Bandı": "" if pos_a is None else f"#{pos_a}–#{pos_b}",
                "Sıra Bandı Tekrar": int(pos_n),
                "Sıra Bandı Oranı": round(float(pos_ratio), 3),
                "Bağlarda Medyan Sıra Kayması": "" if np.isnan(shift_med) else round(float(shift_med), 1),
                "Sıra Kayması MAD": "" if np.isnan(shift_mad) else round(float(shift_mad), 1),
                "Sonraki Tahmin Günlük Sıra": "" if pred_pos is None else f"#{pred_pos}",
                "Sonraki Tahmin Sıra Bandı": "" if pred_a is None else f"#{pred_a}–#{pred_b}",
                "Sonraki Tahmin Saat": pred_time,
                "Sonraki Tahmin Saat Bandı": pred_time_band,
                "Zaman Kimliği Puanı": int(timing_score),
                "Zaman Kimliği": timing_level,
            })
            all_link_rows.extend(links)

    profiles = pd.DataFrame(all_profile_rows)
    links_df = pd.DataFrame(all_link_rows)
    events_df = pd.DataFrame(event_rows)
    if not profiles.empty:
        profiles = profiles.sort_values(
            ["Zaman Kimliği Puanı", "Gap Bağı", "Kaynak Puan"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
    return profiles, links_df, events_df, schedule, records


# ============================================================
# KONTROLLER
# ============================================================
with st.sidebar:
    st.header("⚙️ Canlı ayarlar")
    raw_url = st.text_input("GitHub veri.txt RAW", value=DEFAULT_RAW_URL)
    sizes = st.multiselect("Takip edilecek aileler", [6, 7, 8, 10], default=[6, 7, 8, 10])
    draw_band_width = st.slider("Çekiliş sıra bandı genişliği", 3, 15, 7, step=2)
    minute_window = st.slider("Saat penceresi (dakika)", 30, 120, 60, step=15)
    max_coupon_per_size = st.slider("Hedef günde boyut başına max kupon", 1, 5, 2)
    include_10_candidates = st.checkbox("10’lu çoklu-gap ADAYlarını kupona dahil et", value=False)
    turkey_today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    target_date = st.date_input("Hedef tarih", value=turkey_today)
    st.caption("Varsayılan kupon kuralı: tam ritim günü + Zaman Kimliği GÜÇLÜ/ORTA. ZAYIF sinyal kupona girmez.")

if st.button("🔄 GitHub verisini yenile", type="secondary"):
    fetch_text.clear()
    parse_veri.clear()
    analyze_identity.clear()
    st.rerun()

try:
    text = fetch_text(raw_url)
    profiles, links_df, events_df, schedule_map, records = analyze_identity(text, draw_band_width, minute_window)
except Exception as e:
    st.error(f"veri.txt okunamadı veya analiz edilemedi: {e}")
    st.stop()

if not records:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

min_date = records[0]["date"]
max_date = records[-1]["date"]
max_draw = records[-1]["draw_id"]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Çekiliş", f"{len(records):,}".replace(",", "."))
c2.metric("Başlangıç", min_date.strftime("%d.%m.%Y"))
c3.metric("Veri sonu", max_date.strftime("%d.%m.%Y"))
c4.metric("Son çekiliş no", max_draw)
c5.metric("Takip aile", len({s['family'] for s in SEEDS}))

if min_date > SEED_COVERAGE_START:
    st.warning(
        f"Dar çekirdekler 01.08.2026–09.10.2026 çalışmasından geldi; bu veri.txt {min_date.strftime('%d.%m.%Y')} tarihinde başlıyor. "
        "Erken dönem eksikse saat/çekiliş kimliği zayıflayabilir. Mümkünse 01.08’den başlayan tam veri.txt kullan."
    )
if max_date < target_date:
    st.warning(
        f"Hedef tarih {target_date.strftime('%d.%m.%Y')}, veri.txt ise {max_date.strftime('%d.%m.%Y')} tarihinde bitiyor. "
        "Ritim tarihi hesaplanır ama canlı aktivasyon için veri.txt hedef güne kadar güncel olmalı."
    )

view = profiles[profiles["Aile Boyutu"].isin(sizes)].copy() if not profiles.empty else profiles

if not view.empty:
    def target_state(x):
        if not x:
            return ""
        d = datetime.strptime(str(x), "%Y-%m-%d").date()
        delta = (d - target_date).days
        if delta == 0:
            return "🎯 HEDEF GÜN"
        if delta > 0:
            return f"⏳ +{delta} gün"
        return f"GEÇTİ {delta} gün"

    view["Hedef Durum"] = view["Sıradaki Ritim Tarihi"].map(target_state)
    view["Hedefe Gün"] = view["Sıradaki Ritim Tarihi"].map(
        lambda x: (datetime.strptime(str(x), "%Y-%m-%d").date() - target_date).days if x else 9999
    )

records_by_date = defaultdict(list)
for r in records:
    records_by_date[r["date"]].append(r)
target_records = records_by_date.get(target_date, [])
last_target_pos = max([r["day_pos"] for r in target_records], default=0)

if not view.empty:
    live_cols = []
    for _, row in view.iterrows():
        fam = row["Aile"]
        nums = set(family_nums(fam))
        recent = target_records[-6:] if target_records else []
        overlaps = [len(nums.intersection(r["nums"])) for r in recent]
        max_overlap = max(overlaps) if overlaps else ""
        latest_overlap = overlaps[-1] if overlaps else ""
        band = str(row["Sonraki Tahmin Sıra Bandı"])
        state = ""
        if band.startswith("#"):
            try:
                a, b = [int(x.replace("#", "")) for x in band.split("–")]
                if not target_records:
                    state = "TARİH BEKLENİYOR" if target_date > max_date else "VERİ YOK"
                elif last_target_pos < a:
                    state = "BEKLE"
                elif a <= last_target_pos <= b:
                    state = "🟢 PENCERE AÇIK"
                else:
                    state = "PENCERE GEÇTİ"
            except Exception:
                state = ""
        live_cols.append((max_overlap, latest_overlap, state))
    view["Son 6’da Maks Örtüşme"] = [x[0] for x in live_cols]
    view["Son Çekiliş Örtüşme"] = [x[1] for x in live_cols]
    view["Canlı Pencere"] = [x[2] for x in live_cols]

st.divider()
tabs = st.tabs(["🔥 Hedef Gün Kupon", "🕒 Saat & Çekiliş Kimliği", "📆 Yaklaşan Ritimler", "🔗 Gap Bağları", "📦 Rapor"])

with tabs[0]:
    st.subheader(f"🔥 {target_date.strftime('%d.%m.%Y')} hedef günü")
    if view.empty:
        st.info("Takip ailesi yok.")
    else:
        live = view[
            (view["Hedefe Gün"] == 0) &
            (view["Zaman Kimliği"].isin(["GÜÇLÜ", "ORTA"]))
        ].copy()
        if not include_10_candidates:
            live = live[~((live["Aile Boyutu"] == 10) & (live["Kaynak Seviye"] == "ADAY-ÇOKLU-GAP"))]
        live = live.sort_values(["Aile Boyutu", "Zaman Kimliği Puanı", "Kaynak Puan"], ascending=[True, False, False])
        chosen = []
        for k in sorted(live["Aile Boyutu"].unique().tolist()):
            chosen.append(live[live["Aile Boyutu"] == k].head(int(max_coupon_per_size)))
        live2 = pd.concat(chosen, ignore_index=True) if chosen else pd.DataFrame()

        if live2.empty:
            st.success("Bu hedef tarihte GÜÇLÜ/ORTA zaman kimliğiyle tam ritim günü çakışan kupon yok → 0 kupon.")
            weak = view[view["Hedefe Gün"] == 0].copy()
            if not weak.empty:
                st.caption("Ritim günü var ama zaman kimliği yeterince güçlü olmayan izleme adayları:")
                safe_dataframe(weak[["Aile Boyutu","Aile","Gün Gap","Zaman Kimliği","Zaman Kimliği Puanı","Sonraki Tahmin Sıra Bandı","Sonraki Tahmin Saat Bandı"]], 50)
        else:
            st.success(f"{len(live2)} kupon adayı. Bunlar tarihsel ritim filtresidir; garanti değildir.")
            cols = [
                "Aile Boyutu","Aile","Kaynak Seviye","Gün Gap","Gap Bağı","Son Zincir Tarih",
                "Zaman Kimliği","Zaman Kimliği Puanı","Sonraki Tahmin Günlük Sıra",
                "Sonraki Tahmin Sıra Bandı","Sonraki Tahmin Saat","Sonraki Tahmin Saat Bandı",
                "Son 6’da Maks Örtüşme","Son Çekiliş Örtüşme","Canlı Pencere"
            ]
            safe_dataframe(live2[cols], 50)

    with st.expander("Bu hedef saat/çekiliş nasıl bulunuyor?", expanded=False):
        st.markdown(
            """
1. Önce aile + gap’in gerçekten bağ kurduğu gün çiftleri bulunur.  
2. Her bağda iki günde gerçekleşen aile vuruşları arasından **günlük çekiliş sırası birbirine en yakın** eşleştirme alınır.  
3. Bu bağların sıra kaymalarının medyanı çıkarılır. Son ritim vuruşunun günlük sırasına bu medyan kayma eklenerek sonraki merkez sıra hesaplanır.  
4. Dağılım genişse bant genişler; saat, günlük sıra takviminden çevrilir.  
5. **Saat ve çekiliş sırası aynı zaman davranışının iki görünümüdür; iki bağımsız doğrulama gibi sayılmaz.**
            """
        )

with tabs[1]:
    st.subheader("🕒 Aile + gap özel zaman kimliği")
    levels = st.multiselect("Zaman kimliği", ["GÜÇLÜ","ORTA","ZAYIF"], default=["GÜÇLÜ","ORTA"], key="levels")
    kim = view[view["Zaman Kimliği"].isin(levels)].copy() if not view.empty else view
    cols = [
        "Aile Boyutu","Aile","Kaynak Seviye","Gün Gap","Gap Bağı","Son Zincir Tarih","Toplam Görünüş","Aktif Gün",
        "Baskın Saat", f"{minute_window}dk Saat Penceresi", "Saat Pencere Oranı",
        "Tarihsel Günlük Sıra Bandı","Sıra Bandı Oranı","Bağlarda Medyan Sıra Kayması","Sıra Kayması MAD",
        "Sıradaki Ritim Tarihi","Sonraki Tahmin Günlük Sıra","Sonraki Tahmin Sıra Bandı",
        "Sonraki Tahmin Saat","Sonraki Tahmin Saat Bandı","Zaman Kimliği Puanı","Zaman Kimliği"
    ]
    safe_dataframe(kim[cols] if not kim.empty else kim, 300)

with tabs[2]:
    st.subheader("📆 Önümüzdeki 14 gün")
    if view.empty:
        st.info("Kayıt yok.")
    else:
        upcoming = view[(view["Hedefe Gün"] >= 0) & (view["Hedefe Gün"] <= 14)].copy()
        upcoming = upcoming.sort_values(["Hedefe Gün","Zaman Kimliği Puanı","Kaynak Puan"], ascending=[True,False,False])
        safe_dataframe(upcoming[[
            "Hedefe Gün","Sıradaki Ritim Tarihi","Aile Boyutu","Aile","Gün Gap","Gap Bağı","Son Zincir Tarih",
            "Zaman Kimliği","Zaman Kimliği Puanı","Sonraki Tahmin Sıra Bandı","Sonraki Tahmin Saat Bandı"
        ]], 300)

with tabs[3]:
    st.subheader("🔗 Gerçek gap bağlarının saat/sıra geçişleri")
    ldf = links_df[links_df["Aile Boyutu"].isin(sizes)].copy() if not links_df.empty else links_df
    safe_dataframe(ldf.sort_values(["Aile Boyutu","Aile","Gün Gap","2. Gün"], ascending=[True,True,True,False]) if not ldf.empty else ldf, 300)

with tabs[4]:
    st.subheader("📦 Tüm raporu indir")
    report_view = view.drop(columns=["Hedefe Gün"], errors="ignore").copy() if not view.empty else view
    upcoming_report = view[(view["Hedefe Gün"] >= 0) & (view["Hedefe Gün"] <= 14)].copy() if not view.empty else pd.DataFrame()
    live_report = view[(view["Hedefe Gün"] == 0) & (view["Zaman Kimliği"].isin(["GÜÇLÜ","ORTA"]))].copy() if not view.empty else pd.DataFrame()
    method = """CANLI RİTİM SAAT & ÇEKİLİŞ MERKEZİ V1

Takip havuzu:
- 6'lı: dar çekirdek Top50 (4 ULTRA dahil)
- 7'li: 450 çekirdek içinden skor sırasına göre Top50
- 8'li: 3 bağ / 4 tarih sert kriterini geçen 5 aile
- 10'lu: 1 ULTRA + 2 çoklu-gap aday

Zaman kimliği aile + gap bazında hesaplanır.
Saat ve günlük çekiliş sırası bağımsız iki sinyal değildir.
Tahmin bandı, geçmiş gerçek gap bağlarında günlük sıra kaymasının medyanı ve sapmasına göre kurulur.
Zaman Kimliği Puanı olasılık değildir; örnek sayısı + sıra kayması tutarlılığı + saat kümelenmesi sıralama puanıdır.
Canlı kupon: tam hedef gün + GÜÇLÜ/ORTA zaman kimliği. ZAYIF => 0 kupon.
Geçmiş ritim gelecekte tekrar garantisi vermez.
"""
    files = {
        "01_AILE_GAP_SAAT_CEKILIS_KIMLIGI.csv": csv_bytes(report_view),
        "02_HEDEF_GUN_ADAYLARI.csv": csv_bytes(live_report),
        "03_ONUMUZDEKI_14_GUN.csv": csv_bytes(upcoming_report),
        "04_GAP_BAG_DETAY.csv": csv_bytes(links_df),
        "05_RITIM_OLAYLARI.csv": csv_bytes(events_df),
        "99_METODOLOJI.txt": method,
    }
    st.download_button(
        "⬇️ TÜM RAPORLARI ZIP İNDİR",
        data=build_zip(files),
        file_name="HIZLI_ON_CANLI_RITIM_SAAT_CEKILIS_V1_TUM_RAPORLAR.zip",
        mime="application/zip",
        type="primary",
    )
    st.download_button(
        "⬇️ Saat & çekiliş kimliği CSV",
        data=csv_bytes(report_view),
        file_name="HIZLI_ON_AILE_GAP_SAAT_CEKILIS_KIMLIGI.csv",
        mime="text/csv",
    )

st.caption(
    "Not: Bu uygulama geçmiş exact aile tekrarlarından ritim ve zaman yoğunluğu çıkarır. "
    "İstatistiksel düzen gözlenmesi, sonraki çekilişin kesin tahmini anlamına gelmez."
)
