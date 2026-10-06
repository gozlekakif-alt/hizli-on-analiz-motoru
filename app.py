# -*- coding: utf-8 -*-
"""
HIZLI ON — GERÇEK 20 OLUŞUM ANATOMİSİ V1.0

AMAÇ
-----
Bu uygulama TAHMİN veya KUPON üretmez.
Her hedef çekilişten hemen ÖNCE 1..80 arasındaki bütün sayıların durumunu dondurur,
5 katmana ayırır ve gerçek 20 sonuç geldikten sonra:

    80 SAYI -> 5 KATMAN -> GERÇEK 20 -> HANGİ KATMANDAN HANGİ SAYILAR ALINDI?

sorusunu çekiliş çekiliş kaydeder.

TASARIM KURALLARI
-----------------
- Ağır analiz uygulama açılışında başlamaz.
- veri.txt yalnız ham gerçek sonuç kaynağıdır.
- Hedef çekilişin kendisi, hedef-öncesi özelliklere ASLA girmez.
- 20 çıkan + 60 çıkmayan birlikte snapshot havuzunda saklanır.
- İşlem saatlik bloklar halinde checkpoint edilir.
- Kapanma / yeniden başlama sonrası tamamlanmış saatler tekrar hesaplanmaz.
- Geçmiş veri değişirse güvenli devam durdurulur.
- Katman sınırları motor sürümüne bağlı ve sabittir; geçmiş sonuç görülerek oynanmaz.

Not: Bu yazılım geçmiş çekiliş davranışını araştırmak içindir; gelecek sonuç garantisi vermez.
"""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# ======================================================================================
# SABİTLER
# ======================================================================================
st.set_page_config(
    page_title="Hızlı On — Gerçek 20 Anatomisi",
    page_icon="🔬",
    layout="wide",
)

APP_VERSION = "GERCEK20_ANATOMI_V1.0"
UI_BUILD = "V1.0.1_TEK_DOSYA_EXPORT"
DATA_FILE = Path("veri.txt")
DEFAULT_DATA_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_DATA_BRANCH = "main"
DEFAULT_DATA_PATH = "veri.txt"
DEFAULT_STATE_REPO = "gozlekakif-alt/hizli-on-analiz-state"
DEFAULT_STATE_BRANCH = "main"
DEFAULT_STATE_ROOT = ".gercek20_anatomi_v1"
LOCAL_STATE_ROOT = Path(DEFAULT_STATE_ROOT)

LAYERS = ["SOĞUK", "SERİN", "NÖTR", "ILIK", "SICAK"]
WINDOWS = [3, 6, 12, 24, 48, 72]
BASE_PROB = 0.25

# Isı endeksi, son pencerelerdeki gerçekleşme oranının doğal %25 tabanına oranıdır.
# Örn. 1.00 = doğal taban civarı, 1.50 = tabanın %50 üstü.
HEAT_WEIGHTS = {6: 0.34, 12: 0.26, 24: 0.18, 48: 0.12, 72: 0.10}
HEAT_THRESHOLDS = {
    "SOĞUK_MAX": 0.60,
    "SERİN_MAX": 0.85,
    "NÖTR_MAX": 1.15,
    "ILIK_MAX": 1.45,
}

# ======================================================================================
# YARDIMCILAR / SECRETS
# ======================================================================================
def safe_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


def clean_token(token: str) -> str:
    t = (token or "").strip().strip('"').strip("'")
    low = t.lower()
    if low.startswith("bearer "):
        t = t[7:].strip()
    elif low.startswith("token "):
        t = t[6:].strip()
    return t


@dataclass(frozen=True)
class Settings:
    data_repo: str
    data_branch: str
    data_path: str
    state_repo: str
    state_branch: str
    state_root: str
    token: str


def settings() -> Settings:
    return Settings(
        data_repo=(safe_secret("GITHUB_REPO", DEFAULT_DATA_REPO) or DEFAULT_DATA_REPO).strip(),
        data_branch=(safe_secret("GITHUB_BRANCH", DEFAULT_DATA_BRANCH) or DEFAULT_DATA_BRANCH).strip(),
        data_path=(safe_secret("GITHUB_DATA_PATH", DEFAULT_DATA_PATH) or DEFAULT_DATA_PATH).strip(),
        state_repo=(safe_secret("GITHUB_STATE_REPO", DEFAULT_STATE_REPO) or DEFAULT_STATE_REPO).strip(),
        state_branch=(safe_secret("GITHUB_STATE_BRANCH", DEFAULT_STATE_BRANCH) or DEFAULT_STATE_BRANCH).strip(),
        state_root=(safe_secret("ANATOMI_STATE_ROOT", DEFAULT_STATE_ROOT) or DEFAULT_STATE_ROOT).strip().strip("/"),
        token=clean_token(
            safe_secret("GITHUB_TOKEN", "")
            or safe_secret("GH_TOKEN", "")
            or safe_secret("GITHUB_PAT", "")
        ),
    )


# ======================================================================================
# GITHUB API — yalnız checkpoint/state için
# ======================================================================================
class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, detail: str):
        self.status = int(status)
        self.detail = detail
        super().__init__(f"GitHub HTTP {status}: {detail}")


def api_request(
    url: str,
    token: str,
    method: str = "GET",
    payload=None,
    accept: str = "application/vnd.github+json",
    timeout: int = 90,
    expect_json: bool = True,
):
    headers = {
        "Accept": accept,
        "User-Agent": "hizli-on-gercek20-anatomi-v1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not expect_json:
                return raw
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("message", raw)
            except Exception:
                detail = raw
        except Exception:
            detail = str(exc)
        raise GitHubAPIError(exc.code, str(detail)[:1000]) from exc


def api_path(path: str) -> str:
    return urllib.parse.quote(path.strip("/"), safe="/")


def gh_file_meta(repo: str, branch: str, path: str, token: str):
    url = (
        f"https://api.github.com/repos/{repo}/contents/{api_path(path)}"
        f"?ref={urllib.parse.quote(branch, safe='')}"
    )
    try:
        return api_request(url, token)
    except GitHubAPIError as exc:
        if exc.status == 404:
            return None
        raise


def gh_get_bytes(repo: str, branch: str, path: str, token: str) -> Optional[bytes]:
    url = (
        f"https://api.github.com/repos/{repo}/contents/{api_path(path)}"
        f"?ref={urllib.parse.quote(branch, safe='')}"
    )
    try:
        return api_request(
            url,
            token,
            accept="application/vnd.github.raw+json",
            expect_json=False,
        )
    except GitHubAPIError as exc:
        if exc.status == 404:
            return None
        raise


def gh_put_bytes(repo: str, branch: str, path: str, token: str, data: bytes, message: str):
    url = f"https://api.github.com/repos/{repo}/contents/{api_path(path)}"
    meta = gh_file_meta(repo, branch, path, token)
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if meta and meta.get("sha"):
        payload["sha"] = meta["sha"]
    try:
        return api_request(url, token, method="PUT", payload=payload, timeout=150)
    except GitHubAPIError as exc:
        if exc.status not in (409, 422):
            raise
        # Çakışmada son SHA ile tek tekrar.
        meta = gh_file_meta(repo, branch, path, token)
        payload.pop("sha", None)
        if meta and meta.get("sha"):
            payload["sha"] = meta["sha"]
        return api_request(url, token, method="PUT", payload=payload, timeout=150)


# ======================================================================================
# HAM VERİ OKUMA / PARSE / DOĞRULAMA
# ======================================================================================
def decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def load_data_text(uploaded=None) -> Tuple[str, str]:
    if uploaded is not None:
        return decode_bytes(uploaded.getvalue()), f"Yüklenen: {uploaded.name}"

    if DATA_FILE.exists():
        return DATA_FILE.read_text(encoding="utf-8", errors="replace"), "repo/veri.txt"

    cfg = settings()
    url = (
        f"https://raw.githubusercontent.com/{cfg.data_repo}/"
        f"{cfg.data_branch}/{cfg.data_path}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-gercek20-anatomi-v1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return decode_bytes(resp.read()), f"GitHub RAW: {cfg.data_repo}/{cfg.data_path}"


def parse_numbers(text: str) -> List[int]:
    vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", text)]
    return vals


@st.cache_data(show_spinner=False)
def parse_draws(text: str) -> Tuple[pd.DataFrame, List[str]]:
    rows: List[Tuple[int, pd.Timestamp, Tuple[int, ...]]] = []
    issues: List[str] = []

    # 1) Sıkıştırılmış satır biçimi: draw ; date time ; numbers
    semicolon_hits = 0
    line_re = re.compile(
        r"^\s*#?(\d{4,})\s*[;|]\s*(\d{2}\.\d{2}\.\d{4})\s+"
        r"(\d{2}:\d{2})\s*[;|]\s*(.*?)\s*$"
    )
    for ln_no, line in enumerate(text.splitlines(), 1):
        m = line_re.match(line)
        if not m:
            continue
        semicolon_hits += 1
        draw_id = int(m.group(1))
        try:
            dt = pd.Timestamp(datetime.strptime(f"{m.group(2)} {m.group(3)}", "%d.%m.%Y %H:%M"))
        except Exception:
            issues.append(f"Satır {ln_no}: tarih/saat okunamadı — çekiliş #{draw_id}")
            continue
        nums = parse_numbers(m.group(4))
        if len(nums) != 20 or len(set(nums)) != 20 or any(n < 1 or n > 80 for n in nums):
            issues.append(f"Satır {ln_no}: #{draw_id} için 20 farklı 1–80 sayı doğrulanamadı")
            continue
        rows.append((draw_id, dt, tuple(sorted(nums))))

    # 2) Blok biçimi: Çekiliş no / tarih-saat / 20 sayı
    # Satır formatı yoksa veya bloklar da ayrıca mevcutsa blok parser da çalışır; duplicate sonra temizlenir.
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "çekiliş no" not in lines[i].lower():
            i += 1
            continue

        start_line = i + 1
        draw_id = None
        m = re.search(r"(\d{4,})", lines[i])
        if m:
            draw_id = int(m.group(1))
        j = i + 1
        if draw_id is None:
            while j < min(i + 6, len(lines)):
                m = re.fullmatch(r"\s*#?\s*(\d{4,})\s*", lines[j])
                if m:
                    draw_id = int(m.group(1))
                    j += 1
                    break
                j += 1
        if draw_id is None:
            issues.append(f"Satır {start_line}: çekiliş numarası okunamadı")
            i += 1
            continue

        dt = None
        while j < min(i + 12, len(lines)):
            m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[-–— ]\s*(\d{2}:\d{2})", lines[j])
            if not m:
                m = re.search(r"(\d{2}\.\d{2}\.\d{4}).*?(\d{2}:\d{2})", lines[j])
            if m:
                try:
                    dt = pd.Timestamp(datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M"))
                except Exception:
                    dt = None
                j += 1
                break
            j += 1

        if dt is None:
            issues.append(f"Satır {start_line}: #{draw_id} tarih/saat okunamadı")
            i += 1
            continue

        nums: List[int] = []
        k = j
        while k < len(lines) and len(nums) < 20:
            if k > j and "çekiliş no" in lines[k].lower():
                break
            mm = re.fullmatch(r"\s*(\d{1,2})\s*", lines[k])
            if mm:
                n = int(mm.group(1))
                if 1 <= n <= 80:
                    nums.append(n)
            k += 1

        if len(nums) != 20 or len(set(nums)) != 20:
            issues.append(f"Satır {start_line}: #{draw_id} blokta tam 20 farklı sayı bulunamadı")
        else:
            rows.append((draw_id, dt, tuple(sorted(nums))))
        i = max(i + 1, k)

    if not rows:
        return pd.DataFrame(columns=["draw_id", "dt", "numbers"]), issues

    df = pd.DataFrame(rows, columns=["draw_id", "dt", "numbers"])
    df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
    df = df.dropna(subset=["dt"]).copy()

    # Aynı çekiliş birden fazla formatla bulunduysa aynı sonucu tekleştir.
    # Farklı içerik varsa issue üret.
    conflict_draws = []
    for draw_id, g in df.groupby("draw_id"):
        signatures = {(pd.Timestamp(r.dt), tuple(r.numbers)) for r in g.itertuples()}
        if len(signatures) > 1:
            conflict_draws.append(int(draw_id))
    if conflict_draws:
        issues.append("Aynı çekiliş numarasında farklı içerik bulundu: " + ", ".join(map(str, conflict_draws[:20])))

    df = (
        df.sort_values(["dt", "draw_id"])
        .drop_duplicates("draw_id", keep="last")
        .reset_index(drop=True)
    )

    # Nihai doğrulama
    bad = []
    for r in df.itertuples():
        nums = list(r.numbers)
        if len(nums) != 20 or len(set(nums)) != 20 or min(nums) < 1 or max(nums) > 80:
            bad.append(int(r.draw_id))
    if bad:
        issues.append("Nihai kontrolde hatalı çekilişler: " + ", ".join(map(str, bad[:20])))
        df = df[~df["draw_id"].isin(bad)].reset_index(drop=True)

    dup_dt = df[df.duplicated("dt", keep=False)]
    if not dup_dt.empty:
        issues.append(f"Aynı tarih/saatte {dup_dt['draw_id'].nunique()} çekiliş bulundu; kontrol edilmeli.")

    if semicolon_hits == 0 and not any("çekiliş no" in x.lower() for x in lines):
        issues.append("Tanımlı veri formatı başlığı bulunamadı.")

    return df, issues


def normalized_rows(df: pd.DataFrame, n: Optional[int] = None) -> bytes:
    if n is None:
        n = len(df)
    out = io.StringIO()
    for r in df.iloc[:n].itertuples():
        nums = ",".join(map(str, r.numbers))
        out.write(f"{int(r.draw_id)}|{pd.Timestamp(r.dt).strftime('%Y-%m-%d %H:%M')}|{nums}\n")
    return out.getvalue().encode("utf-8")


def prefix_hash(df: pd.DataFrame, n: int) -> str:
    return hashlib.sha256(normalized_rows(df, n)).hexdigest()


def full_hash(df: pd.DataFrame) -> str:
    return hashlib.sha256(normalized_rows(df, len(df))).hexdigest()


# ======================================================================================
# HEDEF-ÖNCESİ BAĞLAM MATRİSLERİ
# ======================================================================================
@st.cache_resource(show_spinner=False)
def build_context(draw_ids: Tuple[int, ...], dts_iso: Tuple[str, ...], numbers_t: Tuple[Tuple[int, ...], ...]):
    """Tüm diziyi tek geçişte hazırlar.

    DİKKAT: Her i satırındaki before-matrisleri, i. çekiliş eklenmeden önce kopyalanır.
    Dolayısıyla hedef sonucundan bilgi sızıntısı yoktur.
    """
    n_draws = len(draw_ids)
    mat = np.zeros((n_draws, 80), dtype=np.uint8)
    for i, nums in enumerate(numbers_t):
        for n in nums:
            mat[i, n - 1] = 1

    cum = np.zeros((n_draws + 1, 80), dtype=np.int32)
    if n_draws:
        cum[1:] = np.cumsum(mat, axis=0, dtype=np.int32)

    dts = [pd.Timestamp(x) for x in dts_iso]

    prev_hit = np.full((n_draws, 80), -1, dtype=np.int32)
    day_before = np.zeros((n_draws, 80), dtype=np.uint16)
    same_minute_before = np.zeros((n_draws, 80), dtype=np.uint16)
    same_hour_before = np.zeros((n_draws, 80), dtype=np.uint16)

    last = np.full(80, -1, dtype=np.int32)
    day_counts = np.zeros(80, dtype=np.uint16)
    minute_counts = np.zeros((60, 80), dtype=np.uint16)
    hour_counts = np.zeros((24, 80), dtype=np.uint16)
    current_day = None

    day_start_idx = np.zeros(n_draws, dtype=np.int32)
    current_day_start = 0

    for i, dt in enumerate(dts):
        day = dt.date()
        if current_day != day:
            current_day = day
            day_counts[:] = 0
            current_day_start = i

        prev_hit[i] = last
        day_before[i] = day_counts
        same_minute_before[i] = minute_counts[dt.minute]
        same_hour_before[i] = hour_counts[dt.hour]
        day_start_idx[i] = current_day_start

        active = np.flatnonzero(mat[i])
        if len(active):
            last[active] = i
            day_counts[active] += 1
            minute_counts[dt.minute, active] += 1
            hour_counts[dt.hour, active] += 1

    return {
        "mat": mat,
        "cum": cum,
        "prev_hit": prev_hit,
        "day_before": day_before,
        "same_minute_before": same_minute_before,
        "same_hour_before": same_hour_before,
        "day_start_idx": day_start_idx,
    }


def get_context(df: pd.DataFrame):
    return build_context(
        tuple(int(x) for x in df["draw_id"].tolist()),
        tuple(pd.Timestamp(x).isoformat() for x in df["dt"].tolist()),
        tuple(tuple(int(n) for n in nums) for nums in df["numbers"].tolist()),
    )


def window_count(cum: np.ndarray, idx: int, n0: int, width: int) -> Tuple[int, int]:
    avail = min(idx, width)
    if avail <= 0:
        return 0, 0
    start = idx - avail
    return int(cum[idx, n0] - cum[start, n0]), avail


def window_ratio(cum: np.ndarray, idx: int, n0: int, width: int) -> float:
    count, avail = window_count(cum, idx, n0, width)
    if avail <= 0:
        return 1.0
    observed = count / avail
    return observed / BASE_PROB


def heat_index_for(cum: np.ndarray, idx: int, n0: int) -> float:
    if idx <= 0:
        return 1.0
    total = 0.0
    wsum = 0.0
    for width, weight in HEAT_WEIGHTS.items():
        _, avail = window_count(cum, idx, n0, width)
        if avail <= 0:
            continue
        total += weight * window_ratio(cum, idx, n0, width)
        wsum += weight
    return total / wsum if wsum else 1.0


def layer_for_heat(score: float) -> str:
    if score < HEAT_THRESHOLDS["SOĞUK_MAX"]:
        return "SOĞUK"
    if score < HEAT_THRESHOLDS["SERİN_MAX"]:
        return "SERİN"
    if score < HEAT_THRESHOLDS["NÖTR_MAX"]:
        return "NÖTR"
    if score < HEAT_THRESHOLDS["ILIK_MAX"]:
        return "ILIK"
    return "SICAK"


def direction_for(cum: np.ndarray, idx: int, n0: int) -> Tuple[str, float]:
    # Son 6 ile ondan önceki 6'nın oran farkı.
    if idx < 4:
        return "YENİ", 0.0
    recent_start = max(0, idx - 6)
    recent_len = idx - recent_start
    recent_hits = int(cum[idx, n0] - cum[recent_start, n0])
    recent_rate = recent_hits / recent_len if recent_len else 0.0

    prev_end = recent_start
    prev_start = max(0, prev_end - 6)
    prev_len = prev_end - prev_start
    if prev_len <= 0:
        return "YENİ", 0.0
    prev_hits = int(cum[prev_end, n0] - cum[prev_start, n0])
    prev_rate = prev_hits / prev_len
    delta = recent_rate - prev_rate
    if delta >= 0.10:
        return "YÜKSELİYOR", delta
    if delta <= -0.10:
        return "DÜŞÜYOR", delta
    return "YATAY", delta


def last12_pattern(mat: np.ndarray, idx: int, n0: int) -> str:
    start = max(0, idx - 12)
    vals = mat[start:idx, n0].tolist()
    bits = "".join("1" if int(v) else "0" for v in vals)
    return bits.rjust(12, "·")


def snapshot_for_draw(df: pd.DataFrame, ctx: dict, idx: int) -> pd.DataFrame:
    mat = ctx["mat"]
    cum = ctx["cum"]
    target = df.iloc[idx]
    selected = set(int(n) for n in target["numbers"])

    rows = []
    for n in range(1, 81):
        n0 = n - 1
        counts = {}
        for w in WINDOWS:
            counts[w] = window_count(cum, idx, n0, w)[0]

        heat = heat_index_for(cum, idx, n0)
        layer = layer_for_heat(heat)
        direction, direction_delta = direction_for(cum, idx, n0)

        prev_i = int(ctx["prev_hit"][idx, n0])
        if prev_i >= 0:
            gap = idx - prev_i - 1
            prev_row = df.iloc[prev_i]
            last_seen = pd.Timestamp(prev_row["dt"]).strftime("%d.%m.%Y %H:%M")
            last_draw = int(prev_row["draw_id"])
        else:
            gap = None
            last_seen = "-"
            last_draw = None

        rows.append({
            "draw_id": int(target["draw_id"]),
            "dt": pd.Timestamp(target["dt"]).strftime("%Y-%m-%d %H:%M"),
            "number": n,
            "selected": 1 if n in selected else 0,
            "layer": layer,
            "heat_index": round(float(heat), 4),
            "direction": direction,
            "direction_delta": round(float(direction_delta), 4),
            "H3": counts[3],
            "H6": counts[6],
            "H12": counts[12],
            "H24": counts[24],
            "H48": counts[48],
            "H72": counts[72],
            "day_before": int(ctx["day_before"][idx, n0]),
            "same_minute_before": int(ctx["same_minute_before"][idx, n0]),
            "same_hour_before": int(ctx["same_hour_before"][idx, n0]),
            "gap": "İLK" if gap is None else int(gap),
            "last_draw": "-" if last_draw is None else int(last_draw),
            "last_seen": last_seen,
            "last12": last12_pattern(mat, idx, n0),
            "history_draws_before": int(idx),
            "engine_version": APP_VERSION,
        })
    return pd.DataFrame(rows)


def anatomy_summary(snapshot: pd.DataFrame) -> dict:
    layer_candidates = {}
    layer_selected = {}
    counts = {}
    for layer in LAYERS:
        g = snapshot[snapshot["layer"] == layer]
        cand = g["number"].astype(int).tolist()
        sel = g.loc[g["selected"] == 1, "number"].astype(int).tolist()
        layer_candidates[layer] = cand
        layer_selected[layer] = sel
        counts[layer] = {"candidates": len(cand), "selected": len(sel)}
    return {
        "layer_candidates": layer_candidates,
        "layer_selected": layer_selected,
        "counts": counts,
    }


def draw_summary_row(df: pd.DataFrame, idx: int, snapshot: pd.DataFrame) -> dict:
    target = df.iloc[idx]
    anatomy = anatomy_summary(snapshot)
    row = {
        "draw_id": int(target["draw_id"]),
        "dt": pd.Timestamp(target["dt"]).strftime("%Y-%m-%d %H:%M"),
        "actual20": list(map(int, target["numbers"])),
        "history_draws_before": int(idx),
        "engine_version": APP_VERSION,
    }
    row.update(anatomy)
    return row


# ======================================================================================
# STATE / CHECKPOINT
# ======================================================================================
def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]


def default_progress() -> dict:
    return {
        "engine_version": APP_VERSION,
        "run_id": new_run_id(),
        "processed_count": 0,
        "processed_prefix_hash": hashlib.sha256(b"").hexdigest(),
        "last_draw_id": None,
        "last_dt": None,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


class StateStore:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.local_root = LOCAL_STATE_ROOT
        self.local_root.mkdir(parents=True, exist_ok=True)
        self.remote_enabled = bool(cfg.token and cfg.state_repo)
        self.remote_error = None

    def rel_progress(self) -> str:
        return "progress.json"

    def remote_path(self, rel: str) -> str:
        return f"{self.cfg.state_root}/{rel.strip('/')}"

    def local_path(self, rel: str) -> Path:
        p = self.local_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def read_bytes(self, rel: str) -> Optional[bytes]:
        if self.remote_enabled:
            try:
                raw = gh_get_bytes(
                    self.cfg.state_repo,
                    self.cfg.state_branch,
                    self.remote_path(rel),
                    self.cfg.token,
                )
                if raw is not None:
                    # Yerel aynayı tazele.
                    self.local_path(rel).write_bytes(raw)
                    return raw
            except Exception as exc:
                self.remote_error = str(exc)
        p = self.local_path(rel)
        if p.exists():
            return p.read_bytes()
        return None

    def write_bytes(self, rel: str, data: bytes, message: str) -> Tuple[bool, str]:
        self.local_path(rel).write_bytes(data)
        if self.remote_enabled:
            try:
                gh_put_bytes(
                    self.cfg.state_repo,
                    self.cfg.state_branch,
                    self.remote_path(rel),
                    self.cfg.token,
                    data,
                    message,
                )
                return True, "GitHub + yerel"
            except Exception as exc:
                self.remote_error = str(exc)
                return False, f"Yalnız yerel (GitHub hata: {exc})"
        return True, "Yerel"

    def load_progress(self) -> dict:
        raw = self.read_bytes(self.rel_progress())
        if not raw:
            return default_progress()
        try:
            obj = json.loads(raw.decode("utf-8"))
            return obj
        except Exception:
            return default_progress()

    def save_progress(self, progress: dict) -> Tuple[bool, str]:
        progress = dict(progress)
        progress["updated_at"] = datetime.now().isoformat(timespec="seconds")
        raw = json.dumps(progress, ensure_ascii=False, indent=2).encode("utf-8")
        return self.write_bytes(
            self.rel_progress(),
            raw,
            f"{APP_VERSION}: checkpoint #{progress.get('last_draw_id')}",
        )

    def save_block(self, run_id: str, block_key: str, payload: dict) -> Tuple[bool, str]:
        rel = f"runs/{run_id}/blocks/{block_key}.json.gz"
        raw = gzip.compress(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            compresslevel=6,
        )
        return self.write_bytes(rel, raw, f"{APP_VERSION}: block {block_key}")


# ======================================================================================
# BLOK İŞLEME
# ======================================================================================
def block_key_for_dt(dt: pd.Timestamp) -> str:
    return pd.Timestamp(dt).strftime("%Y-%m-%d_%H")


def next_hour_end(df: pd.DataFrame, start_idx: int) -> int:
    if start_idx >= len(df):
        return start_idx
    target = pd.Timestamp(df.iloc[start_idx]["dt"])
    key = (target.date(), target.hour)
    i = start_idx
    while i < len(df):
        dt = pd.Timestamp(df.iloc[i]["dt"])
        if (dt.date(), dt.hour) != key:
            break
        i += 1
    return i


def next_day_end(df: pd.DataFrame, start_idx: int) -> int:
    if start_idx >= len(df):
        return start_idx
    day = pd.Timestamp(df.iloc[start_idx]["dt"]).date()
    i = start_idx
    while i < len(df) and pd.Timestamp(df.iloc[i]["dt"]).date() == day:
        i += 1
    return i


def process_one_hour(
    df: pd.DataFrame,
    ctx: dict,
    store: StateStore,
    progress: dict,
) -> Tuple[dict, dict]:
    start = int(progress.get("processed_count", 0))
    if start >= len(df):
        return progress, {"done": True, "message": "Tüm çekilişler işlendi."}

    end = next_hour_end(df, start)
    block_dt = pd.Timestamp(df.iloc[start]["dt"])
    block_key = block_key_for_dt(block_dt)

    draw_summaries = []
    snapshots_records = []
    for idx in range(start, end):
        snap = snapshot_for_draw(df, ctx, idx)
        draw_summaries.append(draw_summary_row(df, idx, snap))
        snapshots_records.extend(snap.to_dict("records"))

    block_payload = {
        "engine_version": APP_VERSION,
        "run_id": progress["run_id"],
        "block_key": block_key,
        "start_index": start,
        "end_index_exclusive": end,
        "draw_count": end - start,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "draws": draw_summaries,
        "snapshots": snapshots_records,
    }

    ok_block, backend_block = store.save_block(progress["run_id"], block_key, block_payload)
    if store.remote_enabled and not ok_block:
        # Uzak blok güvenle yazılmadan checkpoint ilerletilmez.
        # Yerel blok kalabilir; sonraki denemede aynı saat güvenle yeniden üretilir.
        return progress, {
            "done": False,
            "error": True,
            "block_key": block_key,
            "draw_count": end - start,
            "backend": backend_block,
            "message": "GitHub blok kaydı başarısız; checkpoint ilerletilmedi.",
        }

    new_progress = dict(progress)
    new_progress["processed_count"] = end
    new_progress["processed_prefix_hash"] = prefix_hash(df, end)
    new_progress["last_draw_id"] = int(df.iloc[end - 1]["draw_id"])
    new_progress["last_dt"] = pd.Timestamp(df.iloc[end - 1]["dt"]).strftime("%Y-%m-%d %H:%M")
    ok_prog, backend_prog = store.save_progress(new_progress)
    if store.remote_enabled and not ok_prog:
        return new_progress, {
            "done": False,
            "error": True,
            "block_key": block_key,
            "draw_count": end - start,
            "start": start,
            "end": end,
            "backend": f"blok: {backend_block} · checkpoint: {backend_prog}",
            "message": "Blok yazıldı fakat uzak checkpoint yazılamadı; güvenli otomatik durduruldu.",
        }

    return new_progress, {
        "done": end >= len(df),
        "block_key": block_key,
        "draw_count": end - start,
        "start": start,
        "end": end,
        "backend": f"blok: {backend_block} · checkpoint: {backend_prog}",
        "persist_ok": bool(ok_block and ok_prog),
    }


def validate_resume(df: pd.DataFrame, progress: dict) -> Tuple[bool, str]:
    if progress.get("engine_version") != APP_VERSION:
        return False, (
            f"Checkpoint sürümü {progress.get('engine_version')} fakat uygulama {APP_VERSION}. "
            "Yeni çalışma başlatılmalı."
        )
    n = int(progress.get("processed_count", 0))
    if n < 0 or n > len(df):
        return False, "Checkpoint işlenen çekiliş sayısı mevcut veriyle uyumsuz."
    expected = progress.get("processed_prefix_hash", "")
    actual = prefix_hash(df, n)
    if expected and expected != actual:
        return False, (
            "İşlenmiş geçmiş veri değişmiş. Eski snapshot ile yeni veri karıştırılmadı. "
            "Yeni çalışma başlatın."
        )
    return True, "Güvenli devam uygun."


# ======================================================================================
# TÜM İŞLENMİŞ ANATOMİYİ TEK DOSYADA BİRLEŞTİRME
# ======================================================================================
def processed_block_keys(df: pd.DataFrame, processed_count: int) -> List[str]:
    """İşlenmiş ön ek için kronolojik benzersiz saat bloklarını döndürür."""
    keys: List[str] = []
    seen = set()
    for dt in df.iloc[:processed_count]["dt"].tolist():
        key = block_key_for_dt(pd.Timestamp(dt))
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def load_saved_block_local_first(store: StateStore, run_id: str, block_key: str) -> dict:
    """Export sırasında yüzlerce gereksiz GitHub isteğini önlemek için önce yerel aynayı okur."""
    rel = f"runs/{run_id}/blocks/{block_key}.json.gz"
    local = store.local_path(rel)
    if local.exists():
        raw = local.read_bytes()
    else:
        raw = store.read_bytes(rel)
    if not raw:
        raise FileNotFoundError(f"Kayıtlı saat bloğu bulunamadı: {block_key}")
    try:
        return json.loads(gzip.decompress(raw).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Saat bloğu açılamadı: {block_key} · {exc}") from exc


def build_full_anatomy_export(
    df: pd.DataFrame,
    store: StateStore,
    progress: dict,
    progress_callback=None,
) -> Tuple[bytes, dict]:
    """Checkpointlenmiş bütün snapshotları TEK gzip CSV'ye birleştirir.

    Yeniden anatomi hesaplamaz; saatlik bloklarda daha önce kaydedilmiş snapshotları okur.
    Çıkışın bütünlüğü 80 satır/çekiliş ve 20 selected/çekiliş ile doğrulanır.
    """
    processed_count = int(progress.get("processed_count", 0))
    if processed_count <= 0:
        raise RuntimeError("Henüz işlenmiş çekiliş yok.")

    run_id = str(progress.get("run_id") or "")
    if not run_id:
        raise RuntimeError("Checkpoint run_id bulunamadı.")

    block_keys = processed_block_keys(df, processed_count)
    if not block_keys:
        raise RuntimeError("Birleştirilecek saat bloğu bulunamadı.")

    base_fields = [
        "run_id", "block_key", "draw_id", "dt", "number", "selected", "layer",
        "heat_index", "direction", "direction_delta", "H3", "H6", "H12", "H24",
        "H48", "H72", "day_before", "same_minute_before", "same_hour_before",
        "gap", "last_draw", "last_seen", "last12", "history_draws_before",
        "engine_version", "actual20",
    ]
    layer_fields: List[str] = []
    for layer in LAYERS:
        layer_fields.extend([
            f"{layer}_aday",
            f"{layer}_alinan",
            f"{layer}_alinan_sayilar",
        ])
    fieldnames = base_fields + layer_fields

    buffer = io.BytesIO()
    row_count = 0
    selected_total = 0
    draw_ids_seen = set()

    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=6) as gz:
        with io.TextIOWrapper(gz, encoding="utf-8-sig", newline="") as txt:
            writer = csv.DictWriter(txt, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()

            total_blocks = len(block_keys)
            for bi, block_key in enumerate(block_keys, 1):
                payload = load_saved_block_local_first(store, run_id, block_key)
                if payload.get("run_id") != run_id:
                    raise RuntimeError(f"Run uyuşmazlığı: {block_key}")

                draw_map = {int(x["draw_id"]): x for x in payload.get("draws", [])}
                snapshots = payload.get("snapshots", [])
                for rec in snapshots:
                    draw_id = int(rec["draw_id"])
                    summary = draw_map.get(draw_id)
                    if summary is None:
                        raise RuntimeError(f"Çekiliş özeti bulunamadı: #{draw_id} · {block_key}")

                    anatomy_counts = summary.get("counts", {})
                    anatomy_selected = summary.get("layer_selected", {})
                    out = dict(rec)
                    out["run_id"] = run_id
                    out["block_key"] = block_key
                    out["actual20"] = ",".join(map(str, summary.get("actual20", [])))
                    for layer in LAYERS:
                        c = anatomy_counts.get(layer, {})
                        out[f"{layer}_aday"] = int(c.get("candidates", 0))
                        out[f"{layer}_alinan"] = int(c.get("selected", 0))
                        out[f"{layer}_alinan_sayilar"] = ",".join(
                            map(str, anatomy_selected.get(layer, []))
                        )

                    writer.writerow(out)
                    row_count += 1
                    selected_total += int(rec.get("selected", 0))
                    draw_ids_seen.add(draw_id)

                if progress_callback is not None:
                    progress_callback(bi, total_blocks, block_key)

    expected_rows = processed_count * 80
    expected_selected = processed_count * 20
    if row_count != expected_rows:
        raise RuntimeError(
            f"Bütünlük hatası: {expected_rows:,} snapshot satırı bekleniyordu, {row_count:,} bulundu."
        )
    if selected_total != expected_selected:
        raise RuntimeError(
            f"Bütünlük hatası: {expected_selected:,} gerçek-seçim etiketi bekleniyordu, "
            f"{selected_total:,} bulundu."
        )
    if len(draw_ids_seen) != processed_count:
        raise RuntimeError(
            f"Bütünlük hatası: {processed_count:,} çekiliş bekleniyordu, "
            f"{len(draw_ids_seen):,} farklı çekiliş bulundu."
        )

    meta = {
        "run_id": run_id,
        "draws": processed_count,
        "rows": row_count,
        "selected": selected_total,
        "blocks": len(block_keys),
    }
    return buffer.getvalue(), meta


# ======================================================================================
# GÖRSEL RAPORLAR
# ======================================================================================
def selected_draw_view(df: pd.DataFrame, ctx: dict, idx: int):
    snap = snapshot_for_draw(df, ctx, idx)
    target = df.iloc[idx]
    anatomy = anatomy_summary(snap)

    st.markdown(f"### #{int(target['draw_id'])} — {pd.Timestamp(target['dt']):%d.%m.%Y %H:%M}")
    st.write("**Gerçek 20:** " + " – ".join(map(str, target["numbers"])))

    cols = st.columns(5)
    for col, layer in zip(cols, LAYERS):
        with col:
            c = anatomy["counts"][layer]
            st.metric(layer, f"{c['selected']} / {c['candidates']}")
            st.caption("alınan / katmandaki")

    st.markdown("#### 80 → 5 katman → gerçek 20")
    for layer in LAYERS:
        candidates = anatomy["layer_candidates"][layer]
        selected = anatomy["layer_selected"][layer]
        with st.expander(
            f"{layer} · katmanda {len(candidates)} sayı · gerçek 20 buradan {len(selected)} sayı aldı",
            expanded=True,
        ):
            st.write("**Katmandaki tüm sayılar:** " + (", ".join(map(str, candidates)) if candidates else "-"))
            st.write("**Gerçek 20'ye alınanlar:** " + (", ".join(map(str, selected)) if selected else "-"))

    st.markdown("#### 80 sayının hedef-öncesi pasaportu")
    show_cols = [
        "number", "selected", "layer", "heat_index", "direction", "H3", "H6", "H12",
        "H24", "H48", "H72", "day_before", "same_minute_before", "same_hour_before",
        "gap", "last_draw", "last_seen", "last12",
    ]
    table = snap[show_cols].copy()
    table = table.rename(columns={
        "number": "Sayı",
        "selected": "Gerçek20",
        "layer": "Katman",
        "heat_index": "Isı endeksi",
        "direction": "Yön",
        "day_before": "Gün içi önce",
        "same_minute_before": "Aynı dakika geçmişi",
        "same_hour_before": "Aynı saat geçmişi",
        "gap": "Gap",
        "last_draw": "Son çekiliş",
        "last_seen": "Son görülme",
        "last12": "Son12 izi",
    })
    table["Gerçek20"] = table["Gerçek20"].map({1: "✓", 0: ""})
    st.dataframe(table, use_container_width=True, hide_index=True, height=760)

    st.download_button(
        "⬇️ Bu çekilişin 80 sayı snapshot CSV'sini indir",
        data=snap.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"GERCEK20_ANATOMI_{int(target['draw_id'])}_{pd.Timestamp(target['dt']):%Y%m%d_%H%M}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def range_anatomy_table(df: pd.DataFrame, ctx: dict, indices: List[int]) -> pd.DataFrame:
    rows = []
    for idx in indices:
        snap = snapshot_for_draw(df, ctx, idx)
        anatomy = anatomy_summary(snap)
        r = df.iloc[idx]
        row = {
            "Çekiliş": int(r["draw_id"]),
            "Tarih-saat": pd.Timestamp(r["dt"]).strftime("%d.%m.%Y %H:%M"),
        }
        total = 0
        for layer in LAYERS:
            cnt = anatomy["counts"][layer]
            row[f"{layer} aday"] = cnt["candidates"]
            row[f"{layer} alınan"] = cnt["selected"]
            row[f"{layer} sayılar"] = ",".join(map(str, anatomy["layer_selected"][layer]))
            total += cnt["selected"]
        row["Toplam"] = total
        rows.append(row)
    return pd.DataFrame(rows)


# ======================================================================================
# UYGULAMA
# ======================================================================================
st.title("🔬 Hızlı On — Gerçek 20 Oluşum Anatomisi")
st.caption(
    "Tahmin/kupon üretmez. Her çekilişte 80 sayının hedef-öncesi durumunu dondurur ve "
    "gerçek 20'nin hangi katmandan hangi sayıları aldığını kaydeder."
)

cfg = settings()
store = StateStore(cfg)

with st.sidebar:
    st.subheader("Veri")
    uploaded = st.file_uploader("İstersen geçici TXT yükle", type=["txt"])

try:
    raw_text, source_name = load_data_text(uploaded)
except Exception as exc:
    st.error(f"veri.txt okunamadı: {exc}")
    st.stop()

with st.spinner("Yalnız veri okunuyor ve doğrulanıyor…"):
    df, parse_issues = parse_draws(raw_text)

if df.empty:
    st.error("Geçerli çekiliş bulunamadı. veri.txt biçimini kontrol et.")
    st.stop()

# Ham veri kalite kontrolü
all_valid = df["numbers"].map(lambda x: len(x) == 20 and len(set(x)) == 20 and all(1 <= n <= 80 for n in x)).all()

progress = store.load_progress()
resume_ok, resume_msg = validate_resume(df, progress)
processed_count = int(progress.get("processed_count", 0)) if resume_ok else 0

with st.sidebar:
    st.success(f"Kaynak: {source_name}")
    st.caption(f"{len(df):,} çekiliş · {df.dt.min():%d.%m.%Y %H:%M} → {df.dt.max():%d.%m.%Y %H:%M}")
    if store.remote_enabled:
        st.caption(f"Checkpoint: GitHub state repo + yerel ayna")
    else:
        st.caption("Checkpoint: yalnız yerel · GITHUB_TOKEN yok")
    if store.remote_error:
        st.warning("GitHub state erişiminde sorun var; yerel ayna kullanılıyor.")

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Ham çekiliş", f"{len(df):,}")
with m2:
    st.metric("Doğrulanmış 20'li", f"{int(all_valid) * len(df):,}" if all_valid else "HATA")
with m3:
    st.metric("İşlenmiş", f"{processed_count:,}")
with m4:
    st.metric("Kalan", f"{max(0, len(df) - processed_count):,}")

if parse_issues:
    with st.expander(f"⚠️ Veri kontrol notları ({len(parse_issues)})", expanded=False):
        for x in parse_issues[:100]:
            st.write("• " + x)
        if len(parse_issues) > 100:
            st.caption(f"İlk 100 not gösterildi. Toplam {len(parse_issues)}.")
else:
    st.success("Ham veri kontrolü temiz: her kayıt 20 farklı 1–80 sayı içeriyor.")

if not resume_ok:
    st.error(resume_msg)
else:
    st.info(
        "Ağır analiz otomatik başlamaz. Aşağıdaki düğmelerden biriyle kontrollü başlatılır. "
        "Her tamamlanan saat ayrı checkpoint'tir."
    )

# İlerleme
pct = (processed_count / len(df)) if len(df) else 0.0
st.progress(min(1.0, max(0.0, pct)), text=f"İlerleme: {processed_count:,} / {len(df):,} çekiliş (%{pct*100:.1f})")
if processed_count:
    st.caption(
        f"Son tamamlanan: #{progress.get('last_draw_id')} · {progress.get('last_dt')} · "
        f"run={progress.get('run_id')}"
    )

# ------------------------ İşlem kontrolleri ------------------------
st.markdown("### Kontrollü analiz")
if resume_ok and processed_count < len(df):
    next_row = df.iloc[processed_count]
    st.write(
        f"**Sıradaki:** #{int(next_row['draw_id'])} — {pd.Timestamp(next_row['dt']):%d.%m.%Y %H:%M}"
    )

    c1, c2, c3 = st.columns(3)
    one_hour = c1.button("▶️ Sıradaki 1 saati işle", use_container_width=True, type="primary")
    one_day = c2.button("📅 Sıradaki 1 günü işle", use_container_width=True)
    auto_safe = c3.button("⚙️ Güvenli otomatik ~35 sn", use_container_width=True)

    if one_hour or one_day or auto_safe:
        # Ağır bağlam sadece burada hazırlanır; uygulama açılışında hazırlanmaz.
        with st.spinner("Hedef-öncesi 80 sayı bağlamı hazırlanıyor…"):
            ctx = get_context(df)

        work_progress = dict(progress)
        status_box = st.empty()
        bar = st.progress(processed_count / len(df), text="İşleniyor…")
        start_time = time.monotonic()
        start_day = pd.Timestamp(df.iloc[processed_count]["dt"]).date()
        blocks_done = 0
        last_info = None

        while int(work_progress.get("processed_count", 0)) < len(df):
            work_progress, info = process_one_hour(df, ctx, store, work_progress)
            last_info = info
            pc = int(work_progress["processed_count"])
            bar.progress(pc / len(df), text=f"{pc:,} / {len(df):,} çekiliş · {info.get('block_key', '')}")
            if info.get("error"):
                status_box.error(info.get("message", "Checkpoint yazılamadı."))
                break
            blocks_done += 1
            status_box.success(
                f"{info.get('block_key')} tamamlandı · {info.get('draw_count')} çekiliş · {info.get('backend')}"
            )

            if one_hour:
                break
            if one_day:
                if pc >= len(df):
                    break
                next_day = pd.Timestamp(df.iloc[pc]["dt"]).date()
                if next_day != start_day:
                    break
            if auto_safe and (time.monotonic() - start_time) >= 35:
                break

        st.session_state["last_run_message"] = (
            f"{blocks_done} saatlik blok tamamlandı. Son checkpoint: "
            f"#{work_progress.get('last_draw_id')} · {work_progress.get('last_dt')}"
        )
        st.rerun()

elif processed_count >= len(df):
    st.success("✅ Mevcut veri havuzundaki bütün çekilişler işlendi.")

if "last_run_message" in st.session_state:
    st.success(st.session_state.pop("last_run_message"))

# ------------------------ Yeni çalışma / güvenli reset ------------------------
with st.expander("Yeni çalışma başlat / checkpoint sıfırla", expanded=False):
    st.warning(
        "Bu işlem eski dosyaları silmez; yeni run_id açar ve analiz 0'dan başlar. "
        "Yalnız ham geçmiş veri gerçekten değiştiyse veya motor sürümü değiştiyse kullan."
    )
    confirm_reset = st.checkbox("Yeni çalışma açmayı onaylıyorum", key="confirm_reset")
    if st.button("Yeni run_id ile 0'dan başlat", disabled=not confirm_reset):
        p = default_progress()
        p["processed_prefix_hash"] = prefix_hash(df, 0)
        store.save_progress(p)
        st.session_state["last_run_message"] = f"Yeni çalışma açıldı: {p['run_id']}"
        st.rerun()

# ------------------------ TÜM ANALİZİ TEK DOSYADA İNDİR ------------------------
st.markdown("### 📦 Tüm analizi tek dosyada indir")
st.caption(
    "Saatlik checkpointlerde zaten hesaplanmış verileri birleştirir; 36 günü yeniden analiz etmez. "
    "Tek dosyada her çekiliş için 80 sayının pasaportu, katmanı, gerçek20 etiketi ve "
    "katmanların aldığı gerçek sayılar bulunur."
)

if processed_count <= 0:
    st.caption("Henüz birleştirilecek işlenmiş çekiliş yok.")
else:
    export_complete = processed_count >= len(df)
    if export_complete:
        st.success(
            f"Hazır kapsam: {processed_count:,}/{len(df):,} çekiliş · "
            f"{processed_count * 80:,} adet sayı-snapshot kaydı."
        )
    else:
        st.warning(
            f"Analiz henüz tamamlanmadı. İstersen şu ana kadarki {processed_count:,} çekilişi "
            "tek dosyada alabilirsin."
        )

    export_key = f"{progress.get('run_id')}::{processed_count}"
    cached_key = st.session_state.get("full_export_key")
    if cached_key != export_key:
        st.session_state.pop("full_export_bytes", None)
        st.session_state.pop("full_export_meta", None)
        st.session_state.pop("full_export_name", None)
        st.session_state["full_export_key"] = export_key

    make_all = st.button(
        "🧩 TÜM İŞLENMİŞ ANALİZİ TEK DOSYADA HAZIRLA",
        use_container_width=True,
        type="primary" if export_complete else "secondary",
    )

    if make_all:
        merge_bar = st.progress(0.0, text="Kayıtlı saat blokları birleştiriliyor…")
        merge_status = st.empty()

        def _merge_progress(done: int, total: int, block_key: str):
            frac = done / total if total else 1.0
            merge_bar.progress(
                min(1.0, frac),
                text=f"Birleştiriliyor: {done}/{total} saat bloğu · {block_key}",
            )
            if done == total or done % 25 == 0:
                merge_status.caption(f"Son okunan blok: {block_key}")

        try:
            with st.spinner("Daha önce hesaplanmış anatomi blokları tek dosyada toplanıyor…"):
                export_bytes, export_meta = build_full_anatomy_export(
                    df, store, progress, progress_callback=_merge_progress
                )
            suffix = "TUM_VERI" if export_complete else f"ILK_{processed_count}_CEKILIS"
            export_name = f"HIZLI_ON_GERCEK20_ANATOMI_{suffix}_{progress.get('run_id')}.csv.gz"
            st.session_state["full_export_bytes"] = export_bytes
            st.session_state["full_export_meta"] = export_meta
            st.session_state["full_export_name"] = export_name
            merge_bar.progress(1.0, text="Tek dosya hazır.")
            merge_status.success(
                f"Doğrulandı: {export_meta['draws']:,} çekiliş · "
                f"{export_meta['rows']:,} snapshot satırı · "
                f"{export_meta['selected']:,} gerçek20 etiketi."
            )
        except Exception as exc:
            st.error(f"Tek dosya hazırlanamadı: {exc}")

    if st.session_state.get("full_export_bytes"):
        meta = st.session_state.get("full_export_meta", {})
        st.download_button(
            "⬇️ TEK TÜM DOSYAYI İNDİR (.csv.gz)",
            data=st.session_state["full_export_bytes"],
            file_name=st.session_state.get("full_export_name", "HIZLI_ON_GERCEK20_ANATOMI_TUM.csv.gz"),
            mime="application/gzip",
            use_container_width=True,
            type="primary",
        )
        st.caption(
            f"İçerik: {meta.get('draws', 0):,} çekiliş × 80 sayı = "
            f"{meta.get('rows', 0):,} satır. Her satır hedef-öncesi durum + gerçek20 etiketi içerir."
        )

# ------------------------ İşlenmiş çekiliş anatomisini görüntüle ------------------------
st.markdown("### İşlenmiş çekilişleri incele")
if processed_count <= 0:
    st.caption("Henüz checkpointlenmiş çekiliş yok. Önce 1 saatlik blok işle.")
else:
    processed_df = df.iloc[:processed_count].copy()
    dates = sorted(processed_df["dt"].dt.date.unique())
    sel_date = st.selectbox(
        "Gün",
        dates,
        index=len(dates) - 1,
        format_func=lambda d: pd.Timestamp(d).strftime("%d.%m.%Y"),
    )
    day_idxs = processed_df.index[processed_df["dt"].dt.date == sel_date].tolist()

    hours = sorted({pd.Timestamp(processed_df.loc[i, "dt"]).hour for i in day_idxs})
    sel_hour = st.selectbox("Saat", hours, index=len(hours) - 1, format_func=lambda h: f"{h:02d}:xx")
    hour_idxs = [i for i in day_idxs if pd.Timestamp(processed_df.loc[i, "dt"]).hour == sel_hour]

    sel_idx = st.selectbox(
        "Çekiliş",
        hour_idxs,
        index=len(hour_idxs) - 1,
        format_func=lambda i: f"#{int(df.loc[i, 'draw_id'])} — {pd.Timestamp(df.loc[i, 'dt']):%H:%M}",
    )

    open_draw = st.button("🔍 Seçili çekilişin 80→20 anatomisini aç", use_container_width=True)
    if open_draw:
        with st.spinner("Seçili çekilişin hedef-öncesi snapshot'ı hazırlanıyor…"):
            ctx = get_context(df)
        selected_draw_view(df, ctx, int(sel_idx))

    with st.expander("Bu saatin çekiliş çekiliş katman akışı", expanded=False):
        if st.button("Saatlik tabloyu oluştur", key=f"hour_{sel_date}_{sel_hour}"):
            with st.spinner("Saatlik anatomi çıkarılıyor…"):
                ctx = get_context(df)
                htab = range_anatomy_table(df, ctx, hour_idxs)
            st.dataframe(htab, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Saatlik anatomi CSV",
                data=htab.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"GERCEK20_ANATOMI_{pd.Timestamp(sel_date):%Y%m%d}_{sel_hour:02d}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with st.expander("Bu günün 00:02 → gün sonu katman akışı", expanded=False):
        st.caption("Yalnız checkpointlenmiş çekilişler dahil edilir.")
        if st.button("Günlük tabloyu oluştur", key=f"day_{sel_date}"):
            with st.spinner("Günlük anatomi çıkarılıyor…"):
                ctx = get_context(df)
                dtab = range_anatomy_table(df, ctx, day_idxs)
            st.dataframe(dtab, use_container_width=True, hide_index=True, height=650)
            st.download_button(
                "⬇️ Günlük anatomi CSV",
                data=dtab.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"GERCEK20_ANATOMI_{pd.Timestamp(sel_date):%Y%m%d}_TUM_GUN.csv",
                mime="text/csv",
                use_container_width=True,
            )

# ------------------------ Metodoloji ------------------------
with st.expander("Katman tanımı ve veri sızıntısı kontrolü", expanded=False):
    st.markdown(
        f"""
**Katmanlar sabit motor tanımıyla oluşur; gerçek hedef sonucu katman hesabına girmez.**

Isı endeksi, hedef çekilişten **önceki** H6/H12/H24/H48/H72 görünme oranlarının,
doğal `%25` görünme tabanına göre ağırlıklı oranıdır.

- `SOĞUK`: ısı endeksi < {HEAT_THRESHOLDS['SOĞUK_MAX']:.2f}
- `SERİN`: {HEAT_THRESHOLDS['SOĞUK_MAX']:.2f} – {HEAT_THRESHOLDS['SERİN_MAX']:.2f}
- `NÖTR`: {HEAT_THRESHOLDS['SERİN_MAX']:.2f} – {HEAT_THRESHOLDS['NÖTR_MAX']:.2f}
- `ILIK`: {HEAT_THRESHOLDS['NÖTR_MAX']:.2f} – {HEAT_THRESHOLDS['ILIK_MAX']:.2f}
- `SICAK`: ≥ {HEAT_THRESHOLDS['ILIK_MAX']:.2f}

Her hedefte 80 sayının tamamı tam **bir** katmana girer. Sonra gerçek 20 sonuç yalnız `selected=1`
etiketi olarak eklenir. Bu yüzden “hangi katmandan hangi sayılar alındı?” bilgisi temiz biçimde ölçülür.

**Yön:** son 6 çekilişteki görünme oranı ile ondan önceki 6 çekilişin oranı karşılaştırılır.
Bu da hedef sonucu açılmadan hesaplanır.
        """
    )

st.caption(f"Motor: {APP_VERSION} · Arayüz: {UI_BUILD} · Ham veri hash: {full_hash(df)[:16]}…")
