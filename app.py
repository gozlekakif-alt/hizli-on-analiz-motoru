# -*- coding: utf-8 -*-
"""
HIZLI ON V4 — KİLİTLİ ARAŞTIRMA MOTORU

Kilitli mimari:
- Ağır analiz uygulama açılışında ASLA otomatik başlamaz.
- veri.txt yalnız ham/gerçek çekiliş kaynağıdır.
- Her hedef çekilişten HEMEN ÖNCE 1..80 için snapshot üretilir.
- Hedef sonucu özellik/tahmin hesabına sızmaz.
- Tahmin dondurulduktan sonra gerçek 20 açılır ve 20/60 birlikte etiketlenir.
- Katman kotaları, o andaki katman kapasitesini (80 içindeki aday adedini) hesaba katar.
- İşleme kronolojiktir ve saatlik blok sonunda kalıcı checkpoint yazılır.
- Uygulama kapanırsa tamamlanmış saatler tekrar hesaplanmaz.
- Yeni çekiliş veri.txt'ye eklendiğinde yalnız yeni kısım işlenir.

Bu yazılım geçmiş örüntüleri araştırır; gelecek sonuç veya kazanç garantisi vermez.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# =============================================================================
# SABİTLER
# =============================================================================
APP_VERSION = "HIZLI_ON_V4_LOCKED_2026_10_06"
STATE_SCHEMA = 1
ENGINE_ID = "HIZLI_ON_V4_LOCKED"

DATA_FILE = Path("veri.txt")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_DATA_PATH = "veri.txt"

DEFAULT_STATE_REPO = "gozlekakif-alt/hizli-on-analiz-state"
DEFAULT_STATE_BRANCH = "main"
DEFAULT_STATE_ROOT = ".hizli_on_v4_locked"
LOCAL_STATE_ROOT = Path(".hizli_on_v4_locked_local")

LAYERS = ["SOĞUK", "SERİN", "NÖTR", "ILIK", "SICAK"]
LAYER_TO_CODE = {x: i for i, x in enumerate(LAYERS)}
P_BASE = 20.0 / 80.0
WARMUP_DRAWS = 72
AUTO_RUN_SECONDS = 45

# Candidate posterior priors. Güçlü geçmiş yoksa oranı doğal %25'e çeker.
PRIOR_1 = 120.0
PRIOR_2 = 140.0
PRIOR_3 = 160.0

# =============================================================================
# STREAMLIT / SECRETS
# =============================================================================
def safe_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


def clean_token(token: str) -> str:
    t = (token or "").strip().strip('"').strip("'")
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    elif t.lower().startswith("token "):
        t = t[6:].strip()
    return t


def settings() -> dict:
    return {
        "data_repo": (safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO).strip(),
        "data_branch": (safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH).strip(),
        "data_path": (safe_secret("GITHUB_DATA_PATH", DEFAULT_DATA_PATH) or DEFAULT_DATA_PATH).strip(),
        "state_repo": (safe_secret("GITHUB_STATE_REPO", DEFAULT_STATE_REPO) or DEFAULT_STATE_REPO).strip(),
        "state_branch": (safe_secret("GITHUB_STATE_BRANCH", DEFAULT_STATE_BRANCH) or DEFAULT_STATE_BRANCH).strip(),
        "state_root": (safe_secret("GITHUB_STATE_ROOT", DEFAULT_STATE_ROOT) or DEFAULT_STATE_ROOT).strip().strip("/"),
        "token": clean_token(
            safe_secret("GITHUB_TOKEN", "")
            or safe_secret("GH_TOKEN", "")
            or safe_secret("GITHUB_PAT", "")
        ),
    }

# =============================================================================
# GITHUB KALICI DEPOLAMA
# =============================================================================
class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, detail: str):
        self.status = int(status)
        self.detail = str(detail)
        super().__init__(f"GitHub HTTP {status}: {detail}")


def api_request(url: str, token: str, method: str = "GET", payload=None,
                accept: str = "application/vnd.github+json", timeout: int = 120,
                expect_json: bool = True):
    headers = {
        "Accept": accept,
        "User-Agent": "hizli-on-v4-locked",
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
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            if not expect_json:
                return data
            if not data:
                return {}
            return json.loads(data.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                obj = json.loads(raw)
                detail = obj.get("message", raw)
            except Exception:
                detail = raw
        except Exception:
            detail = str(e)
        raise GitHubAPIError(e.code, (detail or str(e))[:1000]) from e


def api_path(path: str) -> str:
    return urllib.parse.quote(path.strip("/"), safe="/")


def github_file_meta(repo: str, branch: str, path: str, token: str):
    url = f"https://api.github.com/repos/{repo}/contents/{api_path(path)}?ref={urllib.parse.quote(branch, safe='')}"
    try:
        return api_request(url, token)
    except GitHubAPIError as e:
        if e.status == 404:
            return None
        raise


def github_get_bytes(repo: str, branch: str, path: str, token: str) -> bytes:
    url = f"https://api.github.com/repos/{repo}/contents/{api_path(path)}?ref={urllib.parse.quote(branch, safe='')}"
    return api_request(url, token, accept="application/vnd.github.raw+json", expect_json=False)


def github_put_bytes(repo: str, branch: str, path: str, token: str, data: bytes, message: str):
    url = f"https://api.github.com/repos/{repo}/contents/{api_path(path)}"
    meta = github_file_meta(repo, branch, path, token)
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if meta and meta.get("sha"):
        payload["sha"] = meta["sha"]
    try:
        return api_request(url, token, method="PUT", payload=payload, timeout=180)
    except GitHubAPIError as e:
        # Olası SHA yarışı için bir kez tazele.
        if e.status not in (409, 422):
            raise
        meta = github_file_meta(repo, branch, path, token)
        payload.pop("sha", None)
        if meta and meta.get("sha"):
            payload["sha"] = meta["sha"]
        return api_request(url, token, method="PUT", payload=payload, timeout=180)


def github_repo_writable(repo: str, token: str) -> Tuple[bool, str]:
    if not token:
        return False, "GITHUB_TOKEN yok"
    try:
        obj = api_request(f"https://api.github.com/repos/{repo}", token)
        perms = obj.get("permissions") or {}
        writable = bool(perms.get("push") or perms.get("admin") or perms.get("maintain"))
        if writable:
            return True, f"{obj.get('full_name', repo)} yazılabilir"
        # Bazı fine-grained token yanıtlarında permissions olmayabilir; contents PUT sırasında gerçek doğrulama yapılır.
        return True, f"{obj.get('full_name', repo)} erişilebilir"
    except Exception as e:
        return False, str(e)


def storage_mode(cfg: dict) -> str:
    return "github" if cfg.get("token") and cfg.get("state_repo") else "local"


def storage_read(cfg: dict, relative_path: str) -> bytes | None:
    rel = relative_path.strip("/")
    if storage_mode(cfg) == "github":
        path = f"{cfg['state_root']}/{rel}"
        meta = github_file_meta(cfg["state_repo"], cfg["state_branch"], path, cfg["token"])
        if not meta:
            return None
        return github_get_bytes(cfg["state_repo"], cfg["state_branch"], path, cfg["token"])
    path = LOCAL_STATE_ROOT / rel
    if not path.exists():
        return None
    return path.read_bytes()


def storage_write(cfg: dict, relative_path: str, data: bytes, message: str):
    rel = relative_path.strip("/")
    if storage_mode(cfg) == "github":
        path = f"{cfg['state_root']}/{rel}"
        return github_put_bytes(
            cfg["state_repo"], cfg["state_branch"], path, cfg["token"], data, message
        )
    path = LOCAL_STATE_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"local": str(path)}

# =============================================================================
# VERİ OKUMA / DOĞRULAMA
# =============================================================================
def parse_nums_field(s: str) -> List[int]:
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s)]
    return [n for n in nums if 1 <= n <= 80]


def parse_draws(text: str) -> pd.DataFrame:
    rows = []

    # 1) Tek satır: draw ; date time ; numbers
    line_re = re.compile(
        r"^\s*#?(\d{4,})\s*[;|]\s*(\d{2}\.\d{2}\.\d{4})\s+([0-2]\d:[0-5]\d)\s*[;|]\s*(.*?)\s*$"
    )
    for line in text.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        nums = sorted(set(parse_nums_field(m.group(4))))
        if len(nums) != 20:
            continue
        try:
            dt = datetime.strptime(f"{m.group(2)} {m.group(3)}", "%d.%m.%Y %H:%M")
        except Exception:
            continue
        rows.append((int(m.group(1)), pd.Timestamp(dt), tuple(nums)))

    # 2) Blok formatı: Çekiliş no ... tarih ... 20 satır sayı
    if not rows:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            if "çekiliş no" not in lines[i].lower():
                i += 1
                continue

            draw = None
            m = re.search(r"(\d{4,})", lines[i])
            if m:
                draw = int(m.group(1))

            j = i + 1
            if draw is None:
                while j < min(i + 6, len(lines)):
                    mm = re.fullmatch(r"\s*#?\s*(\d{4,})\s*", lines[j])
                    if mm:
                        draw = int(mm.group(1))
                        j += 1
                        break
                    j += 1
            if draw is None:
                i += 1
                continue

            dt = None
            while j < min(i + 12, len(lines)):
                mm = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[-–— ]\s*([0-2]\d:[0-5]\d)", lines[j])
                if mm:
                    try:
                        dt = pd.Timestamp(datetime.strptime(f"{mm.group(1)} {mm.group(2)}", "%d.%m.%Y %H:%M"))
                    except Exception:
                        dt = None
                    j += 1
                    break
                j += 1
            if dt is None:
                i += 1
                continue

            nums = []
            while j < len(lines) and len(nums) < 20:
                if "çekiliş no" in lines[j].lower():
                    break
                mm = re.fullmatch(r"\s*(\d{1,2})\s*", lines[j])
                if mm:
                    n = int(mm.group(1))
                    if 1 <= n <= 80:
                        nums.append(n)
                j += 1

            nums = sorted(set(nums))
            if len(nums) == 20:
                rows.append((draw, dt, tuple(nums)))
            i = max(i + 1, j)

    if not rows:
        return pd.DataFrame(columns=["draw", "dt", "nums"])

    df = pd.DataFrame(rows, columns=["draw", "dt", "nums"])
    df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
    df = df.dropna(subset=["dt"])
    # Aynı draw tekrar etmişse son kayıt kalır; kalite raporu canonical veri üzerinden çalışır.
    df = df.sort_values(["dt", "draw"]).drop_duplicates("draw", keep="last").reset_index(drop=True)
    return df


def read_source(uploaded, cfg: dict) -> Tuple[str, str]:
    if uploaded is not None:
        raw = uploaded.getvalue()
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                return raw.decode(enc), f"Yüklenen dosya: {uploaded.name}"
            except Exception:
                pass
        return raw.decode("utf-8", errors="replace"), f"Yüklenen dosya: {uploaded.name}"

    if DATA_FILE.exists():
        return DATA_FILE.read_text(encoding="utf-8", errors="replace"), "repo / veri.txt"

    url = f"https://raw.githubusercontent.com/{cfg['data_repo']}/{cfg['data_branch']}/{cfg['data_path']}"
    req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-v4-locked"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace"), f"GitHub RAW: {cfg['data_repo']}/{cfg['data_path']}"


def validate_df(df: pd.DataFrame) -> dict:
    fatal = []
    warnings = []
    if df.empty:
        fatal.append("Geçerli çekiliş bulunamadı.")
        return {"fatal": fatal, "warnings": warnings}

    if df["draw"].duplicated().any():
        fatal.append("Tekrarlı çekiliş numarası var.")
    if df["dt"].duplicated().any():
        warnings.append(f"Aynı tarih-saatte {int(df['dt'].duplicated().sum())} tekrar var.")

    bad_nums = 0
    for nums in df["nums"]:
        if len(nums) != 20 or len(set(nums)) != 20 or min(nums) < 1 or max(nums) > 80:
            bad_nums += 1
    if bad_nums:
        fatal.append(f"{bad_nums} çekilişte 20 farklı 1–80 sayı kuralı bozuk.")

    draw_diffs = np.diff(df["draw"].to_numpy(dtype=int))
    if len(draw_diffs) and np.any(draw_diffs <= 0):
        warnings.append("Çekiliş numarası kronolojide monoton artmıyor.")

    dt_diffs = df["dt"].diff().dropna().dt.total_seconds() / 60.0
    unusual = int(((dt_diffs > 10) | (dt_diffs <= 0)).sum())
    if unusual:
        warnings.append(f"{unusual} noktada 10 dakikadan büyük/ters zaman boşluğu var; eksik gün veya gece arası olabilir.")

    return {"fatal": fatal, "warnings": warnings}


def canonical_prefix_hash(df: pd.DataFrame, count: int) -> str:
    h = hashlib.sha256()
    n = max(0, min(int(count), len(df)))
    for row in df.iloc[:n].itertuples(index=False):
        nums = ",".join(map(str, row.nums))
        line = f"{int(row.draw)}|{pd.Timestamp(row.dt).strftime('%Y-%m-%d %H:%M')}|{nums}\n"
        h.update(line.encode("utf-8"))
    return h.hexdigest()


def build_matrix(df: pd.DataFrame):
    m = np.zeros((len(df), 80), dtype=np.uint8)
    for i, nums in enumerate(df["nums"].tolist()):
        if nums:
            m[i, np.asarray(nums, dtype=int) - 1] = 1
    pref = np.vstack([np.zeros((1, 80), dtype=np.int32), np.cumsum(m, axis=0, dtype=np.int32)])
    return m, pref


def day_first_indices(df: pd.DataFrame) -> Dict[str, int]:
    out = {}
    for i, dt in enumerate(df["dt"]):
        key = pd.Timestamp(dt).strftime("%Y-%m-%d")
        out.setdefault(key, i)
    return out

# =============================================================================
# KATMAN / ÖZELLİK MOTORU
# =============================================================================
def zscore(counts, n: int):
    arr = np.asarray(counts, dtype=float)
    if n <= 0:
        return np.zeros_like(arr, dtype=float)
    den = math.sqrt(max(1e-12, n * P_BASE * (1.0 - P_BASE)))
    return (arr - n * P_BASE) / den


def temp_vec(score):
    s = np.asarray(score, dtype=float)
    out = np.full(s.shape, "NÖTR", dtype=object)
    out[s >= 1.00] = "SICAK"
    out[(s >= 0.35) & (s < 1.00)] = "ILIK"
    out[(s <= -0.35) & (s > -1.00)] = "SERİN"
    out[s <= -1.00] = "SOĞUK"
    return out


def window(pref: np.ndarray, idx: int, width: int, end_shift: int = 0):
    end = max(0, idx - end_shift)
    start = max(0, end - width)
    return pref[end] - pref[start], end - start


def direction_vec(cur_counts, cur_n: int, prev_counts, prev_n: int):
    if cur_n <= 0 or prev_n <= 0:
        return np.full(80, "YATAY", dtype=object), np.zeros(80, dtype=float)
    cur_rate = np.asarray(cur_counts, dtype=float) / float(cur_n)
    prev_rate = np.asarray(prev_counts, dtype=float) / float(prev_n)
    delta = cur_rate - prev_rate
    out = np.full(80, "YATAY", dtype=object)
    out[delta >= 0.08] = "YÜKSELİYOR"
    out[delta <= -0.08] = "DÜŞÜYOR"
    return out, delta


def gap_bucket(gap) -> str:
    if gap is None or (isinstance(gap, float) and np.isnan(gap)):
        return "İLK/ÇOK UZAK"
    g = int(gap)
    if g <= 1:
        return "0-1"
    if g <= 3:
        return "2-3"
    if g <= 6:
        return "4-6"
    if g <= 12:
        return "7-12"
    return "13+"


def state_count_vec(state: dict, field: str, key: str) -> np.ndarray:
    obj = state.get(field, {})
    arr = obj.get(str(key))
    if arr is None:
        return np.zeros(80, dtype=np.int32)
    return np.asarray(arr, dtype=np.int32)


def feature_vectors(df: pd.DataFrame, pref: np.ndarray, idx: int, day_start: int, state: dict) -> dict:
    c3, n3 = window(pref, idx, 3)
    c6, n6 = window(pref, idx, 6)
    c12, n12 = window(pref, idx, 12)
    c24, n24 = window(pref, idx, 24)
    c48, n48 = window(pref, idx, 48)
    c72, n72 = window(pref, idx, 72)

    p12, pn12 = window(pref, idx, 12, end_shift=12)
    p24, pn24 = window(pref, idx, 24, end_shift=12)
    p72, pn72 = window(pref, idx, 72, end_shift=12)

    z12 = zscore(c12, n12)
    z24 = zscore(c24, n24)
    z72 = zscore(c72, n72)
    heat_score = 0.50 * z12 + 0.30 * z24 + 0.20 * z72
    heat = temp_vec(heat_score)

    prev_score = 0.50 * zscore(p12, pn12) + 0.30 * zscore(p24, pn24) + 0.20 * zscore(p72, pn72)
    prev_heat = temp_vec(prev_score)
    direction, trend_delta = direction_vec(c12, n12, p12, pn12)
    transition = np.asarray([f"{a}→{b}" for a, b in zip(prev_heat, heat)], dtype=object)

    day_n = max(0, idx - day_start)
    day_counts = pref[idx] - pref[day_start]
    day_z = zscore(day_counts, day_n)
    day_heat = temp_vec(day_z)

    last_seen = np.asarray(state.get("last_seen", [-1] * 80), dtype=int)
    gaps = np.full(80, np.nan, dtype=float)
    seen = last_seen >= 0
    gaps[seen] = idx - last_seen[seen] - 1

    dt = pd.Timestamp(df.iloc[idx]["dt"])
    clock = dt.strftime("%H:%M")
    minute = f"{dt.minute:02d}"
    hour = f"{dt.hour:02d}"

    clock_counts = state_count_vec(state, "clock_counts", clock)
    clock_draws = int(state.get("clock_draws", {}).get(clock, 0))
    minute_counts = state_count_vec(state, "minute_counts", minute)
    minute_draws = int(state.get("minute_draws", {}).get(minute, 0))
    hour_counts = state_count_vec(state, "hour_counts", hour)
    hour_draws = int(state.get("hour_draws", {}).get(hour, 0))

    return {
        "c3": c3, "c6": c6, "c12": c12, "c24": c24, "c48": c48, "c72": c72,
        "heat_score": heat_score, "heat": heat, "prev_heat": prev_heat,
        "direction": direction, "trend_delta": trend_delta, "transition": transition,
        "day_counts": day_counts, "day_z": day_z, "day_heat": day_heat,
        "gaps": gaps,
        "clock_counts": clock_counts, "clock_draws": clock_draws, "clock_z": zscore(clock_counts, clock_draws),
        "minute_counts": minute_counts, "minute_draws": minute_draws, "minute_z": zscore(minute_counts, minute_draws),
        "hour_counts": hour_counts, "hour_draws": hour_draws, "hour_z": zscore(hour_counts, hour_draws),
        "clock": clock, "minute": minute, "hour": hour,
    }


def stats_key(*parts) -> str:
    return "¦".join(str(x) for x in parts)


def posterior(stats: dict, key: str, prior_exposure: float) -> float:
    exposure, hits = stats.get(key, [0, 0])
    return (float(hits) + prior_exposure * P_BASE) / (float(exposure) + prior_exposure)


def candidate_scores(f: dict, state: dict) -> np.ndarray:
    s1 = state.get("candidate_stats1", {})
    s2 = state.get("candidate_stats2", {})
    s3 = state.get("candidate_stats3", {})

    out = np.zeros(80, dtype=float)
    for n in range(80):
        gb = gap_bucket(f["gaps"][n])
        k1 = stats_key(f["heat"][n], f["direction"][n], gb)
        k2 = stats_key(f["transition"][n], gb)
        k3 = stats_key(f["day_heat"][n], f["direction"][n])
        p1 = posterior(s1, k1, PRIOR_1)
        p2 = posterior(s2, k2, PRIOR_2)
        p3 = posterior(s3, k3, PRIOR_3)
        p_model = 0.50 * p1 + 0.30 * p2 + 0.20 * p3

        # Küçük ve sınırlı ek hareket sinyalleri. Ana skor posterior başarı oranıdır.
        out[n] = (
            p_model
            + 0.010 * math.tanh(float(f["trend_delta"][n]) * 4.0)
            + 0.006 * math.tanh(float(f["day_z"][n]) / 2.0)
            + 0.004 * math.tanh(float(f["minute_z"][n]) / 2.0)
            + 0.003 * math.tanh(float(f["hour_z"][n]) / 2.0)
            + 0.003 * math.tanh(float(f["clock_z"][n]) / 2.0)
            + 0.002 * math.tanh(float(f["heat_score"][n]) / 2.0)
        )
    return out

# =============================================================================
# DİNAMİK KOTA MOTORU
# =============================================================================
def allocate_total(raw, capacities, total: int) -> np.ndarray:
    raw = np.asarray(raw, dtype=float)
    cap = np.asarray(capacities, dtype=int)
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    raw = np.clip(raw, 0.0, cap.astype(float))

    if raw.sum() <= 0:
        raw = cap.astype(float)
    if raw.sum() > 0:
        raw = raw * (float(total) / raw.sum())
    raw = np.minimum(raw, cap.astype(float))

    q = np.floor(raw).astype(int)
    q = np.minimum(q, cap)

    while int(q.sum()) < total:
        room = cap - q
        possible = np.where(room > 0)[0]
        if len(possible) == 0:
            break
        priority = raw - q
        j = int(possible[np.argmax(priority[possible])])
        q[j] += 1

    while int(q.sum()) > total:
        possible = np.where(q > 0)[0]
        if len(possible) == 0:
            break
        priority = raw - q
        j = int(possible[np.argmin(priority[possible])])
        q[j] -= 1

    return q


def residual_mean(group: dict | None, shrink_to: float) -> np.ndarray | None:
    if not group:
        return None
    n = int(group.get("n", 0))
    if n <= 0:
        return None
    s = np.asarray(group.get("sum", [0.0] * 5), dtype=float)
    mean = s / float(n)
    credibility = n / (n + float(shrink_to))
    return mean * credibility


def quota_prediction(state: dict, capacities: np.ndarray, dt: pd.Timestamp) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    capacities = np.asarray(capacities, dtype=int)
    baseline_raw = capacities.astype(float) * P_BASE
    baseline_quota = allocate_total(baseline_raw, capacities, 20)

    # Yeni günde yalnız gün-içi recent hafıza sıfırlanır; geçmiş saat/dakika/global hafıza kalır.
    day_key = dt.strftime("%Y-%m-%d")
    if state.get("current_day") != day_key:
        state["current_day"] = day_key
        state["quota_recent_day"] = []

    comps = []
    weights = []

    g = residual_mean(state.get("quota_global"), 80.0)
    if g is not None:
        comps.append(g); weights.append(0.15)

    recent_global = state.get("quota_recent_global", [])
    if recent_global:
        comps.append(np.mean(np.asarray(recent_global, dtype=float), axis=0)); weights.append(0.10)

    recent_day = state.get("quota_recent_day", [])
    if recent_day:
        comps.append(np.mean(np.asarray(recent_day, dtype=float), axis=0)); weights.append(0.30)

    hour_key = f"{dt.hour:02d}"
    minute_key = f"{dt.minute:02d}"
    clock_key = dt.strftime("%H:%M")

    h = residual_mean(state.get("quota_hour", {}).get(hour_key), 36.0)
    if h is not None:
        comps.append(h); weights.append(0.15)

    mi = residual_mean(state.get("quota_minute", {}).get(minute_key), 30.0)
    if mi is not None:
        comps.append(mi); weights.append(0.15)

    cl = residual_mean(state.get("quota_clock", {}).get(clock_key), 8.0)
    if cl is not None:
        comps.append(cl); weights.append(0.15)

    if comps:
        w = np.asarray(weights, dtype=float)
        w /= w.sum()
        residual = sum(float(ww) * cc for ww, cc in zip(w, comps))
    else:
        residual = np.zeros(5, dtype=float)

    # Her residual vektörünün toplamı teorik olarak 0'dır; sayısal sapmayı temizle.
    residual = residual - residual.mean()
    raw = baseline_raw + residual
    quota = allocate_total(raw, capacities, 20)
    return baseline_quota, raw, quota


def hist_quantile(hist: List[int], q: float = 0.80) -> int:
    arr = np.asarray(hist, dtype=int)
    total = int(arr.sum())
    if total < 24:
        return 2
    target = q * total
    c = 0
    for i, v in enumerate(arr):
        c += int(v)
        if c >= target:
            return max(1, min(4, int(i)))
    return 2


def quota_tolerances(state: dict) -> np.ndarray:
    hists = state.get("error_hist", [[0] * 21 for _ in range(5)])
    return np.asarray([hist_quantile(h, 0.80) for h in hists], dtype=int)


def select_by_quota(scores: np.ndarray, layer_codes: np.ndarray, quota: np.ndarray, total: int) -> List[int]:
    chosen: List[int] = []
    for code, take in enumerate(np.asarray(quota, dtype=int)):
        inds = np.where(layer_codes == code)[0]
        if len(inds) == 0 or take <= 0:
            continue
        order = inds[np.argsort(-scores[inds])]
        chosen.extend([int(x) for x in order[:int(take)]])

    if len(chosen) < total:
        for n in np.argsort(-scores):
            n = int(n)
            if n not in chosen:
                chosen.append(n)
            if len(chosen) >= total:
                break
    return chosen[:total]

# =============================================================================
# STATE / CHECKPOINT
# =============================================================================
def now_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def new_metric_bucket() -> dict:
    return {
        "draws": 0,
        "eval_draws": 0,
        "actual_sum": [0] * 5,
        "pred_sum": [0] * 5,
        "abs_err_sum": [0.0] * 5,
        "baseline_abs_err_sum": [0.0] * 5,
        "exact": [0] * 5,
        "within1": [0] * 5,
        "within2": [0] * 5,
        "pool_hits_sum": 0,
        "coupon_hits_sum": 0,
        "coupon_ge4": 0,
        "coupon_ge5": 0,
        "coupon_ge6": 0,
        "coupon_ge7": 0,
        "max_coupon": 0,
        "coupon_hit_dist": {},
        "last_draw": None,
        "last_dt": None,
    }


def new_state() -> dict:
    return {
        "schema": STATE_SCHEMA,
        "engine_id": ENGINE_ID,
        "engine_version": APP_VERSION,
        "run_id": now_id(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "processed_count": 0,
        "processed_prefix_hash": canonical_empty_hash(),
        "last_processed_draw": None,
        "last_processed_dt": None,
        "last_seen": [-1] * 80,
        "clock_counts": {}, "clock_draws": {},
        "minute_counts": {}, "minute_draws": {},
        "hour_counts": {}, "hour_draws": {},
        "candidate_stats1": {}, "candidate_stats2": {}, "candidate_stats3": {},
        "quota_global": {"sum": [0.0] * 5, "n": 0},
        "quota_hour": {}, "quota_minute": {}, "quota_clock": {},
        "quota_recent_global": [], "quota_recent_day": [], "current_day": None,
        "error_hist": [[0] * 21 for _ in range(5)],
        "metrics": new_metric_bucket(),
        "daily": {},
        "hourly": {},
    }


def canonical_empty_hash() -> str:
    return hashlib.sha256(b"").hexdigest()


def checkpoint_bytes(state: dict) -> bytes:
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, compresslevel=6)


def checkpoint_from_bytes(data: bytes) -> dict:
    raw = gzip.decompress(data)
    return json.loads(raw.decode("utf-8"))


def load_state(cfg: dict) -> Tuple[dict, str]:
    data = storage_read(cfg, "checkpoint.json.gz")
    if not data:
        return new_state(), "Yeni araştırma"
    state = checkpoint_from_bytes(data)
    return state, "Checkpoint"


def save_state(cfg: dict, state: dict):
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    storage_write(
        cfg, "checkpoint.json.gz", checkpoint_bytes(state),
        f"{ENGINE_ID}: checkpoint {state.get('last_processed_draw') or 'start'}"
    )


def state_compatible(state: dict, df: pd.DataFrame) -> Tuple[bool, str]:
    if int(state.get("schema", -1)) != STATE_SCHEMA:
        return False, "Checkpoint şeması bu V4 ile uyumlu değil."
    if state.get("engine_id") != ENGINE_ID:
        return False, "Checkpoint başka bir motor ailesine ait."
    count = int(state.get("processed_count", 0))
    if count < 0 or count > len(df):
        return False, "Checkpoint'teki işlenmiş çekiliş sayısı veri.txt ile uyumsuz."
    expected = state.get("processed_prefix_hash") or canonical_empty_hash()
    current = canonical_prefix_hash(df, count)
    if expected != current:
        return False, (
            "İşlenmiş geçmiş veri.txt içinde sonradan değişmiş. Güvenli devam engellendi. "
            "Geçmiş düzeltilmişse araştırmayı bilinçli olarak sıfırlayıp yeniden çalıştır."
        )
    return True, "Kaldığı yerden güvenli devam edebilir."

# =============================================================================
# STATE GÜNCELLEME YARDIMCILARI
# =============================================================================
def bump_stat(stats: dict, key: str, hit: int):
    cur = stats.get(key)
    if cur is None:
        stats[key] = [1, int(hit)]
    else:
        cur[0] = int(cur[0]) + 1
        cur[1] = int(cur[1]) + int(hit)


def bump_count_map(state: dict, counts_field: str, draws_field: str, key: str, actual_mask: np.ndarray):
    counts = state.setdefault(counts_field, {})
    draws = state.setdefault(draws_field, {})
    arr = np.asarray(counts.get(key, [0] * 80), dtype=np.int32)
    arr += actual_mask.astype(np.int32)
    counts[key] = arr.astype(int).tolist()
    draws[key] = int(draws.get(key, 0)) + 1


def bump_residual_group(group_map: dict, key: str, residual: np.ndarray):
    g = group_map.get(key)
    if g is None:
        group_map[key] = {"sum": np.asarray(residual, dtype=float).tolist(), "n": 1}
    else:
        s = np.asarray(g.get("sum", [0.0] * 5), dtype=float) + np.asarray(residual, dtype=float)
        g["sum"] = s.tolist()
        g["n"] = int(g.get("n", 0)) + 1


def bump_metric(bucket: dict, actual_comp: np.ndarray, pred_quota: np.ndarray,
                baseline_quota: np.ndarray, pool_hits: int, coupon_hits: int,
                evaluated: bool, draw: int, dt: pd.Timestamp):
    bucket["draws"] = int(bucket.get("draws", 0)) + 1
    bucket["actual_sum"] = (np.asarray(bucket.get("actual_sum", [0] * 5), dtype=int) + actual_comp).tolist()
    bucket["pred_sum"] = (np.asarray(bucket.get("pred_sum", [0] * 5), dtype=int) + pred_quota).tolist()
    bucket["last_draw"] = int(draw)
    bucket["last_dt"] = dt.isoformat()

    if not evaluated:
        return

    err = np.abs(actual_comp - pred_quota)
    berr = np.abs(actual_comp - baseline_quota)
    bucket["eval_draws"] = int(bucket.get("eval_draws", 0)) + 1
    bucket["abs_err_sum"] = (np.asarray(bucket.get("abs_err_sum", [0.0] * 5), dtype=float) + err).tolist()
    bucket["baseline_abs_err_sum"] = (
        np.asarray(bucket.get("baseline_abs_err_sum", [0.0] * 5), dtype=float) + berr
    ).tolist()
    bucket["exact"] = (np.asarray(bucket.get("exact", [0] * 5), dtype=int) + (err == 0).astype(int)).tolist()
    bucket["within1"] = (np.asarray(bucket.get("within1", [0] * 5), dtype=int) + (err <= 1).astype(int)).tolist()
    bucket["within2"] = (np.asarray(bucket.get("within2", [0] * 5), dtype=int) + (err <= 2).astype(int)).tolist()
    bucket["pool_hits_sum"] = int(bucket.get("pool_hits_sum", 0)) + int(pool_hits)
    bucket["coupon_hits_sum"] = int(bucket.get("coupon_hits_sum", 0)) + int(coupon_hits)
    bucket["coupon_ge4"] = int(bucket.get("coupon_ge4", 0)) + int(coupon_hits >= 4)
    bucket["coupon_ge5"] = int(bucket.get("coupon_ge5", 0)) + int(coupon_hits >= 5)
    bucket["coupon_ge6"] = int(bucket.get("coupon_ge6", 0)) + int(coupon_hits >= 6)
    bucket["coupon_ge7"] = int(bucket.get("coupon_ge7", 0)) + int(coupon_hits >= 7)
    bucket["max_coupon"] = max(int(bucket.get("max_coupon", 0)), int(coupon_hits))
    dist = bucket.setdefault("coupon_hit_dist", {})
    k = str(int(coupon_hits))
    dist[k] = int(dist.get(k, 0)) + 1


def update_after_result(state: dict, idx: int, dt: pd.Timestamp, f: dict, layer_codes: np.ndarray,
                        actual_mask: np.ndarray, actual_comp: np.ndarray, baseline_raw: np.ndarray,
                        pred_quota: np.ndarray, baseline_quota: np.ndarray, pool_hits: int,
                        coupon_hits: int, evaluated: bool, draw: int):
    # 20 ve 60 birlikte candidate learning'e girer.
    for n in range(80):
        hit = int(actual_mask[n])
        gb = gap_bucket(f["gaps"][n])
        bump_stat(state["candidate_stats1"], stats_key(f["heat"][n], f["direction"][n], gb), hit)
        bump_stat(state["candidate_stats2"], stats_key(f["transition"][n], gb), hit)
        bump_stat(state["candidate_stats3"], stats_key(f["day_heat"][n], f["direction"][n]), hit)

    # Zaman hafızaları yalnız sonuç açıldıktan sonra güncellenir.
    bump_count_map(state, "clock_counts", "clock_draws", f["clock"], actual_mask)
    bump_count_map(state, "minute_counts", "minute_draws", f["minute"], actual_mask)
    bump_count_map(state, "hour_counts", "hour_draws", f["hour"], actual_mask)

    last_seen = np.asarray(state.get("last_seen", [-1] * 80), dtype=int)
    last_seen[actual_mask.astype(bool)] = idx
    state["last_seen"] = last_seen.astype(int).tolist()

    # Kota residual: gerçek - katman kapasitesinin doğal %25 tabanı.
    residual = actual_comp.astype(float) - np.asarray(baseline_raw, dtype=float)
    g = state["quota_global"]
    g["sum"] = (np.asarray(g.get("sum", [0.0] * 5), dtype=float) + residual).tolist()
    g["n"] = int(g.get("n", 0)) + 1
    bump_residual_group(state["quota_hour"], f["hour"], residual)
    bump_residual_group(state["quota_minute"], f["minute"], residual)
    bump_residual_group(state["quota_clock"], f["clock"], residual)

    rg = state.setdefault("quota_recent_global", [])
    rg.append(residual.tolist())
    if len(rg) > 12:
        del rg[:-12]
    rd = state.setdefault("quota_recent_day", [])
    rd.append(residual.tolist())
    if len(rd) > 12:
        del rd[:-12]

    err = np.abs(actual_comp - pred_quota).astype(int)
    hists = state.setdefault("error_hist", [[0] * 21 for _ in range(5)])
    for j in range(5):
        e = max(0, min(20, int(err[j])))
        hists[j][e] = int(hists[j][e]) + 1

    day = dt.strftime("%Y-%m-%d")
    hour_key = f"{dt.hour:02d}"
    daily = state.setdefault("daily", {})
    if day not in daily:
        daily[day] = new_metric_bucket()
    hourly = state.setdefault("hourly", {})
    hourly.setdefault(day, {})
    if hour_key not in hourly[day]:
        hourly[day][hour_key] = new_metric_bucket()

    bump_metric(state["metrics"], actual_comp, pred_quota, baseline_quota, pool_hits, coupon_hits, evaluated, draw, dt)
    bump_metric(daily[day], actual_comp, pred_quota, baseline_quota, pool_hits, coupon_hits, evaluated, draw, dt)
    bump_metric(hourly[day][hour_key], actual_comp, pred_quota, baseline_quota, pool_hits, coupon_hits, evaluated, draw, dt)

# =============================================================================
# TEK ÇEKİLİŞİ İŞLE
# =============================================================================
def layer_rank(scores: np.ndarray, layer_codes: np.ndarray) -> np.ndarray:
    ranks = np.zeros(80, dtype=int)
    for code in range(5):
        inds = np.where(layer_codes == code)[0]
        if len(inds) == 0:
            continue
        order = inds[np.argsort(-scores[inds])]
        for r, n in enumerate(order, start=1):
            ranks[int(n)] = r
    return ranks


def process_one_draw(df: pd.DataFrame, matrix: np.ndarray, pref: np.ndarray,
                     day_starts: Dict[str, int], idx: int, state: dict):
    row = df.iloc[idx]
    dt = pd.Timestamp(row["dt"])
    draw = int(row["draw"])
    day = dt.strftime("%Y-%m-%d")
    day_start = int(day_starts[day])

    f = feature_vectors(df, pref, idx, day_start, state)
    layer_codes = np.asarray([LAYER_TO_CODE[str(x)] for x in f["heat"]], dtype=np.uint8)
    capacities = np.bincount(layer_codes, minlength=5).astype(int)

    # HEDEF AÇILMADAN ÖNCE dondurulan her şey burada hesaplanır.
    scores = candidate_scores(f, state)
    baseline_quota, raw_quota, pred_quota = quota_prediction(state, capacities, dt)
    tolerances = quota_tolerances(state)
    low = np.maximum(0, pred_quota - tolerances)
    high = np.minimum(capacities, pred_quota + tolerances)

    pool20 = select_by_quota(scores, layer_codes, pred_quota, 20)
    coupon_quota = allocate_total(pred_quota.astype(float) * 0.5, capacities, 10)
    coupon10 = select_by_quota(scores, layer_codes, coupon_quota, 10)
    ranks = layer_rank(scores, layer_codes)

    # Buradan sonra gerçek sonuç açılır.
    actual_mask = matrix[idx].astype(np.uint8)
    actual_idx = np.flatnonzero(actual_mask)
    actual_comp = np.bincount(layer_codes[actual_idx], minlength=5).astype(int)
    pool_hits = int(actual_mask[pool20].sum())
    coupon_hits = int(actual_mask[coupon10].sum())
    evaluated = bool(idx >= WARMUP_DRAWS)

    # 80-sayı snapshot: tahmin bilgileri target-before; actual yalnız sonradan etiket.
    snap_rows = []
    pool_set = set(pool20)
    coupon_set = set(coupon10)
    for n in range(80):
        last_seen_idx = int(state.get("last_seen", [-1] * 80)[n])
        last_seen_draw = None
        last_seen_dt = None
        if last_seen_idx >= 0 and last_seen_idx < len(df):
            last_seen_draw = int(df.iloc[last_seen_idx]["draw"])
            last_seen_dt = pd.Timestamp(df.iloc[last_seen_idx]["dt"]).isoformat()
        snap_rows.append({
            "engine_version": APP_VERSION,
            "draw": draw,
            "dt": dt.isoformat(),
            "day": day,
            "clock": f["clock"],
            "number": n + 1,
            "h3": int(f["c3"][n]), "h6": int(f["c6"][n]), "h12": int(f["c12"][n]),
            "h24": int(f["c24"][n]), "h48": int(f["c48"][n]), "h72": int(f["c72"][n]),
            "day_hits_before": int(f["day_counts"][n]),
            "gap_before": None if np.isnan(f["gaps"][n]) else int(f["gaps"][n]),
            "gap_bucket": gap_bucket(f["gaps"][n]),
            "last_seen_draw": last_seen_draw,
            "last_seen_dt": last_seen_dt,
            "heat_score_before": round(float(f["heat_score"][n]), 6),
            "layer_before": str(f["heat"][n]),
            "prev_layer": str(f["prev_heat"][n]),
            "transition": str(f["transition"][n]),
            "direction": str(f["direction"][n]),
            "trend_delta": round(float(f["trend_delta"][n]), 6),
            "day_heat_before": str(f["day_heat"][n]),
            "clock_hits_before": int(f["clock_counts"][n]),
            "clock_draws_before": int(f["clock_draws"]),
            "minute_hits_before": int(f["minute_counts"][n]),
            "minute_draws_before": int(f["minute_draws"]),
            "hour_hits_before": int(f["hour_counts"][n]),
            "hour_draws_before": int(f["hour_draws"]),
            "model_score_before": round(float(scores[n]), 8),
            "layer_rank_before": int(ranks[n]),
            "selected_pool20_before": int(n in pool_set),
            "selected_coupon10_before": int(n in coupon_set),
            "actual_after_open": int(actual_mask[n]),
            "evaluation_active": int(evaluated),
        })

    layer_row = {
        "engine_version": APP_VERSION,
        "draw": draw, "dt": dt.isoformat(), "day": day, "clock": f["clock"],
        "evaluation_active": int(evaluated),
    }
    for j, layer in enumerate(LAYERS):
        layer_row[f"capacity_{layer}"] = int(capacities[j])
        layer_row[f"baseline_{layer}"] = int(baseline_quota[j])
        layer_row[f"raw_pred_{layer}"] = round(float(raw_quota[j]), 5)
        layer_row[f"pred_{layer}"] = int(pred_quota[j])
        layer_row[f"tol_{layer}"] = int(tolerances[j])
        layer_row[f"low_{layer}"] = int(low[j])
        layer_row[f"high_{layer}"] = int(high[j])
        layer_row[f"actual_{layer}"] = int(actual_comp[j])
        layer_row[f"err_{layer}"] = int(actual_comp[j] - pred_quota[j])

    pred_row = {
        "engine_version": APP_VERSION,
        "draw": draw, "dt": dt.isoformat(), "day": day, "clock": f["clock"],
        "pool20": ",".join(str(x + 1) for x in pool20),
        "coupon10": ",".join(str(x + 1) for x in coupon10),
    }
    for j, layer in enumerate(LAYERS):
        pred_row[f"pool_quota_{layer}"] = int(pred_quota[j])
        pred_row[f"coupon_quota_{layer}"] = int(coupon_quota[j])

    perf_row = {
        "engine_version": APP_VERSION,
        "draw": draw, "dt": dt.isoformat(), "day": day, "clock": f["clock"],
        "evaluation_active": int(evaluated),
        "pool20_hits": pool_hits,
        "coupon10_hits": coupon_hits,
        "quota_mae": round(float(np.abs(actual_comp - pred_quota).mean()), 6),
        "baseline_quota_mae": round(float(np.abs(actual_comp - baseline_quota).mean()), 6),
        "all_layers_within1": int(np.all(np.abs(actual_comp - pred_quota) <= 1)),
        "actual20": ",".join(map(str, row["nums"])),
    }

    # Model ancak tahmin dondurulup gerçek sonuç açıldıktan sonra güncellenir.
    update_after_result(
        state, idx, dt, f, layer_codes, actual_mask, actual_comp,
        capacities.astype(float) * P_BASE,
        pred_quota, baseline_quota, pool_hits, coupon_hits, evaluated, draw,
    )

    return snap_rows, layer_row, pred_row, perf_row

# =============================================================================
# SAATLİK SHARD / CHECKPOINT
# =============================================================================
def df_gzip_bytes(df: pd.DataFrame) -> bytes:
    raw = df.to_csv(index=False).encode("utf-8-sig")
    return gzip.compress(raw, compresslevel=6)


def bytes_to_df(data: bytes) -> pd.DataFrame:
    raw = gzip.decompress(data)
    return pd.read_csv(io.BytesIO(raw))


def hour_relative_paths(state: dict, day: str, hour: int) -> dict:
    base = f"runs/{state['run_id']}"
    hh = f"{int(hour):02d}"
    return {
        "snapshot": f"{base}/snapshot_80/{day}/{hh}.csv.gz",
        "layers": f"{base}/layer_results/{day}/{hh}.csv.gz",
        "predictions": f"{base}/predictions/{day}/{hh}.csv.gz",
        "performance": f"{base}/performance/{day}/{hh}.csv.gz",
    }


def save_hour_shards(cfg: dict, state: dict, day: str, hour: int,
                     snap_df: pd.DataFrame, layer_df: pd.DataFrame,
                     pred_df: pd.DataFrame, perf_df: pd.DataFrame):
    paths = hour_relative_paths(state, day, hour)
    label = f"{day} {hour:02d}:xx"
    storage_write(cfg, paths["snapshot"], df_gzip_bytes(snap_df), f"V4 snapshot {label}")
    storage_write(cfg, paths["layers"], df_gzip_bytes(layer_df), f"V4 layers {label}")
    storage_write(cfg, paths["predictions"], df_gzip_bytes(pred_df), f"V4 predictions {label}")
    storage_write(cfg, paths["performance"], df_gzip_bytes(perf_df), f"V4 performance {label}")


def process_next_hour(df: pd.DataFrame, matrix: np.ndarray, pref: np.ndarray,
                      day_starts: Dict[str, int], state: dict, cfg: dict,
                      ui_status=None) -> Tuple[dict, dict | None]:
    start = int(state.get("processed_count", 0))
    if start >= len(df):
        return state, None

    dt0 = pd.Timestamp(df.iloc[start]["dt"])
    day = dt0.strftime("%Y-%m-%d")
    hour = int(dt0.hour)

    end = start
    while end < len(df):
        d = pd.Timestamp(df.iloc[end]["dt"])
        if d.strftime("%Y-%m-%d") != day or int(d.hour) != hour:
            break
        end += 1

    snap_rows = []
    layer_rows = []
    pred_rows = []
    perf_rows = []

    for idx in range(start, end):
        if ui_status is not None:
            row = df.iloc[idx]
            ui_status.write(f"#{int(row['draw'])} · {pd.Timestamp(row['dt']):%d.%m.%Y %H:%M} işleniyor")
        s, l, p, pe = process_one_draw(df, matrix, pref, day_starts, idx, state)
        snap_rows.extend(s)
        layer_rows.append(l)
        pred_rows.append(p)
        perf_rows.append(pe)

    snap_df = pd.DataFrame(snap_rows)
    layer_df = pd.DataFrame(layer_rows)
    pred_df = pd.DataFrame(pred_rows)
    perf_df = pd.DataFrame(perf_rows)

    # Önce saatlik veri parçaları; hepsi başarıyla yazılırsa checkpoint ilerletilir.
    save_hour_shards(cfg, state, day, hour, snap_df, layer_df, pred_df, perf_df)

    state["processed_count"] = end
    state["processed_prefix_hash"] = canonical_prefix_hash(df, end)
    state["last_processed_draw"] = int(df.iloc[end - 1]["draw"])
    state["last_processed_dt"] = pd.Timestamp(df.iloc[end - 1]["dt"]).isoformat()
    save_state(cfg, state)

    bundle = {
        "day": day, "hour": hour, "start": start, "end": end,
        "snapshot": snap_df, "layers": layer_df, "predictions": pred_df, "performance": perf_df,
    }
    return state, bundle

# =============================================================================
# RAPOR TABLOLARI
# =============================================================================
def metric_summary_df(bucket: dict) -> pd.DataFrame:
    n = int(bucket.get("eval_draws", 0))
    rows = []
    for j, layer in enumerate(LAYERS):
        if n <= 0:
            rows.append({"Katman": layer, "MAE": "—", "Doğal-kota MAE": "—", "Tam": "—", "±1": "—", "±2": "—"})
            continue
        mae = float(bucket.get("abs_err_sum", [0] * 5)[j]) / n
        bmae = float(bucket.get("baseline_abs_err_sum", [0] * 5)[j]) / n
        exact = 100.0 * int(bucket.get("exact", [0] * 5)[j]) / n
        w1 = 100.0 * int(bucket.get("within1", [0] * 5)[j]) / n
        w2 = 100.0 * int(bucket.get("within2", [0] * 5)[j]) / n
        rows.append({
            "Katman": layer, "MAE": round(mae, 3), "Doğal-kota MAE": round(bmae, 3),
            "Tam": f"{exact:.1f}%", "±1": f"{w1:.1f}%", "±2": f"{w2:.1f}%",
        })
    return pd.DataFrame(rows)


def daily_summary_df(state: dict) -> pd.DataFrame:
    rows = []
    for day in sorted(state.get("daily", {}).keys()):
        b = state["daily"][day]
        n = int(b.get("eval_draws", 0))
        rows.append({
            "Gün": day,
            "İşlenen": int(b.get("draws", 0)),
            "Test": n,
            "Kota MAE": round(sum(map(float, b.get("abs_err_sum", [0] * 5))) / (5 * n), 3) if n else np.nan,
            "Doğal kota MAE": round(sum(map(float, b.get("baseline_abs_err_sum", [0] * 5))) / (5 * n), 3) if n else np.nan,
            "20 havuz ort.": round(float(b.get("pool_hits_sum", 0)) / n, 3) if n else np.nan,
            "10'lu ort.": round(float(b.get("coupon_hits_sum", 0)) / n, 3) if n else np.nan,
            "4+": int(b.get("coupon_ge4", 0)), "5+": int(b.get("coupon_ge5", 0)),
            "6+": int(b.get("coupon_ge6", 0)), "7+": int(b.get("coupon_ge7", 0)),
            "Maks": int(b.get("max_coupon", 0)),
        })
    return pd.DataFrame(rows)


def hour_summary_df(state: dict, day: str) -> pd.DataFrame:
    rows = []
    for hh in sorted(state.get("hourly", {}).get(day, {}).keys()):
        b = state["hourly"][day][hh]
        n = int(b.get("eval_draws", 0))
        actual = np.asarray(b.get("actual_sum", [0] * 5), dtype=float)
        draws = max(1, int(b.get("draws", 0)))
        row = {"Saat": f"{hh}:xx", "Çekiliş": int(b.get("draws", 0)), "Test": n}
        for j, layer in enumerate(LAYERS):
            row[layer] = round(float(actual[j]) / draws, 2)
        row["10'lu ort."] = round(float(b.get("coupon_hits_sum", 0)) / n, 3) if n else np.nan
        row["Maks"] = int(b.get("max_coupon", 0))
        rows.append(row)
    return pd.DataFrame(rows)


def load_hour_bundle(cfg: dict, state: dict, day: str, hour: int):
    paths = hour_relative_paths(state, day, hour)
    out = {}
    for key, path in paths.items():
        data = storage_read(cfg, path)
        if data is None:
            raise FileNotFoundError(path)
        out[key] = bytes_to_df(data)
    out["day"] = day
    out["hour"] = hour
    return out

# =============================================================================
# UI
# =============================================================================
def main():
    st.set_page_config(page_title="Hızlı On V4 — Kilitli Araştırma", page_icon="🧬", layout="wide")
    st.title("🧬 Hızlı On V4 — Kilitli Araştırma Motoru")
    st.caption(
        "80 sayı → hedef-öncesi snapshot → dinamik 5 katman → kota → 20/60 ayrımı → walk-forward. "
        "Ağır analiz uygulama açılışında başlamaz."
    )

    cfg = settings()
    uploaded = st.sidebar.file_uploader("İstersen başka veri.txt yükle", type=["txt"])

    try:
        raw, source_name = read_source(uploaded, cfg)
        df = parse_draws(raw)
    except Exception as e:
        st.error(f"veri.txt okunamadı: {type(e).__name__}: {e}")
        st.stop()

    quality = validate_df(df)
    if quality["fatal"]:
        st.error("Veri doğrulaması başarısız: " + " | ".join(quality["fatal"]))
        st.stop()

    # Bu iki yapı hafiftir: ~binlerce x 80; ağır walk-forward değildir.
    matrix, pref = build_matrix(df)
    day_starts = day_first_indices(df)

    st.sidebar.success(f"Kaynak: {source_name}")
    st.sidebar.caption(
        f"{len(df):,} çekiliş · {df['dt'].dt.date.nunique()} gün · "
        f"{df.iloc[0]['dt']:%d.%m.%Y %H:%M} → {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}"
    )
    st.sidebar.caption(f"Motor: {APP_VERSION}")

    if quality["warnings"]:
        with st.sidebar.expander("Veri uyarıları"):
            for w in quality["warnings"]:
                st.write("• " + w)

    # Kalıcı checkpoint yalnız okunur; bu ağır analiz değildir.
    try:
        state, state_source = load_state(cfg)
    except Exception as e:
        st.error(f"Checkpoint okunamadı: {type(e).__name__}: {e}")
        st.stop()

    compatible, compat_message = state_compatible(state, df)

    # Üst durum
    total = len(df)
    done = int(state.get("processed_count", 0))
    remaining = max(0, total - done)
    pct = 0.0 if total == 0 else done / total

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Ham çekiliş", f"{total:,}".replace(",", "."))
    c2.metric("İşlenen", f"{done:,}".replace(",", "."))
    c3.metric("Kalan", f"{remaining:,}".replace(",", "."))
    c4.metric("İlerleme", f"{100*pct:.1f}%")
    c5.metric("Kalıcı mod", "GitHub" if storage_mode(cfg) == "github" else "Yerel")
    st.progress(min(1.0, max(0.0, pct)))

    if compatible:
        st.success(compat_message)
    else:
        st.error(compat_message)

    if storage_mode(cfg) == "local":
        st.warning(
            "GITHUB_TOKEN / state repo etkin değil. Analiz yerel diske yazılır; Streamlit Cloud yeniden başlarsa "
            "yerel checkpoint kaybolabilir. Kalıcı çalışma için GitHub state deposu kullanılmalı."
        )
    else:
        st.caption(f"Checkpoint: {state_source} · state repo: {cfg['state_repo']} / {cfg['state_branch']}")

    if state.get("last_processed_draw"):
        st.info(
            f"Son tamamlanan: #{state['last_processed_draw']} · "
            f"{pd.Timestamp(state['last_processed_dt']):%d.%m.%Y %H:%M}"
        )

    if done < total:
        nxt = df.iloc[done]
        st.markdown(
            f"**Sıradaki hedef:** #{int(nxt['draw'])} — {pd.Timestamp(nxt['dt']):%d.%m.%Y %H:%M}  "
            f"(hedef sonucu özellik hesabına girmeden önce tahmin dondurulacak)"
        )
    else:
        st.success("Mevcut veri.txt içindeki bütün çekilişler işlendi. Yeni çekiliş eklendiğinde yalnız yeni kısım işlenecek.")

    st.divider()
    st.subheader("Kontrollü analiz")
    st.caption(
        "Her işlem kronolojik gider. Saatlik blok tamamlanınca 80-sayı snapshot, katman sonucu, dondurulmuş tahmin, "
        "performans ve checkpoint kalıcı olarak yazılır."
    )

    b1, b2, b3 = st.columns(3)
    one_hour = b1.button("▶ 1 saatlik blok işle", use_container_width=True, disabled=(not compatible or done >= total))
    one_day = b2.button("▶ 1 gün işle", use_container_width=True, disabled=(not compatible or done >= total))
    auto = b3.button("▶ Güvenli otomatik · 45 sn", use_container_width=True, disabled=(not compatible or done >= total))

    if one_hour or one_day or auto:
        # GitHub moduysa işleme başlamadan yazma erişimini doğrula.
        if storage_mode(cfg) == "github":
            ok, msg = github_repo_writable(cfg["state_repo"], cfg["token"])
            if not ok:
                st.error("State deposuna yazılamıyor: " + msg)
                st.stop()

        status = st.status("Analiz başladı", expanded=True)
        try:
            if one_hour:
                state, bundle = process_next_hour(df, matrix, pref, day_starts, state, cfg, status)
                if bundle:
                    st.session_state["v4_last_bundle"] = bundle
                    status.update(label=f"{bundle['day']} {bundle['hour']:02d}:xx tamamlandı", state="complete")

            elif one_day:
                target_day = pd.Timestamp(df.iloc[int(state["processed_count"])]["dt"]).strftime("%Y-%m-%d")
                last_bundle = None
                while int(state["processed_count"]) < len(df):
                    cur_day = pd.Timestamp(df.iloc[int(state["processed_count"])]["dt"]).strftime("%Y-%m-%d")
                    if cur_day != target_day:
                        break
                    state, last_bundle = process_next_hour(df, matrix, pref, day_starts, state, cfg, status)
                if last_bundle:
                    st.session_state["v4_last_bundle"] = last_bundle
                status.update(label=f"{target_day} tamamlandı", state="complete")

            elif auto:
                deadline = time.monotonic() + AUTO_RUN_SECONDS
                blocks = 0
                last_bundle = None
                while int(state["processed_count"]) < len(df) and time.monotonic() < deadline:
                    state, last_bundle = process_next_hour(df, matrix, pref, day_starts, state, cfg, status)
                    blocks += 1
                if last_bundle:
                    st.session_state["v4_last_bundle"] = last_bundle
                status.update(label=f"Güvenli tur tamamlandı · {blocks} saatlik blok", state="complete")

            st.rerun()
        except Exception as e:
            status.update(label="İşlem durdu — tamamlanmış önceki saatler korunuyor", state="error")
            st.exception(e)
            st.stop()

    # -------------------------------------------------------------------------
    # Walk-forward performans — sadece checkpoint özetinden, hızlı.
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("Walk-forward sağlık ekranı")
    metrics = state.get("metrics", new_metric_bucket())
    ev = int(metrics.get("eval_draws", 0))
    if ev <= 0:
        st.info(f"İlk {WARMUP_DRAWS} çekiliş öğrenme ısınmasıdır. Yeterli test çekilişi oluşunca performans burada açılır.")
    else:
        qmae = sum(map(float, metrics.get("abs_err_sum", [0] * 5))) / (5 * ev)
        bmae = sum(map(float, metrics.get("baseline_abs_err_sum", [0] * 5))) / (5 * ev)
        pool_mean = float(metrics.get("pool_hits_sum", 0)) / ev
        coupon_mean = float(metrics.get("coupon_hits_sum", 0)) / ev

        p1, p2, p3, p4, p5, p6 = st.columns(6)
        p1.metric("Test çekilişi", ev)
        p2.metric("Dinamik kota MAE", f"{qmae:.3f}")
        p3.metric("Doğal kota MAE", f"{bmae:.3f}")
        p4.metric("20 havuz ort.", f"{pool_mean:.3f}", delta=f"{pool_mean-5.0:+.3f} vs 5.0")
        p5.metric("10'lu ort.", f"{coupon_mean:.3f}", delta=f"{coupon_mean-2.5:+.3f} vs 2.5")
        p6.metric("10'lu maksimum", int(metrics.get("max_coupon", 0)))

        st.dataframe(metric_summary_df(metrics), use_container_width=True, hide_index=True)

        g1, g2, g3, g4 = st.columns(4)
        g1.metric("4+", int(metrics.get("coupon_ge4", 0)))
        g2.metric("5+", int(metrics.get("coupon_ge5", 0)))
        g3.metric("6+", int(metrics.get("coupon_ge6", 0)))
        g4.metric("7+", int(metrics.get("coupon_ge7", 0)))

    # -------------------------------------------------------------------------
    # Gün / saat özetleri — checkpoint'ten hızlı.
    # -------------------------------------------------------------------------
    if state.get("daily"):
        st.divider()
        st.subheader("Gün gün / saat saat biriken veri havuzu")
        ddf = daily_summary_df(state)
        st.dataframe(ddf, use_container_width=True, hide_index=True, height=360)

        days = sorted(state.get("daily", {}).keys())
        sel_day = st.selectbox("İşlenmiş gün", days, index=len(days) - 1)
        hdf = hour_summary_df(state, sel_day)
        st.dataframe(hdf, use_container_width=True, hide_index=True, height=420)

        hours = sorted(int(h) for h in state.get("hourly", {}).get(sel_day, {}).keys())
        if hours:
            sel_hour = st.selectbox("Saatlik detay", hours, index=len(hours) - 1, format_func=lambda h: f"{h:02d}:xx")
            if st.button("Seçili saatin gerçek 80-sayı detayını yükle", use_container_width=True):
                try:
                    bundle = load_hour_bundle(cfg, state, sel_day, sel_hour)
                    st.session_state["v4_view_bundle"] = bundle
                except Exception as e:
                    st.error(f"Saatlik shard okunamadı: {type(e).__name__}: {e}")

    # Son işlenen / yüklenen saat detayını göster.
    bundle = st.session_state.get("v4_view_bundle") or st.session_state.get("v4_last_bundle")
    if bundle:
        st.divider()
        st.subheader(f"Saatlik laboratuvar — {bundle['day']} {int(bundle['hour']):02d}:xx")
        layer_df = bundle["layers"]
        perf_df = bundle["performance"]
        pred_df = bundle["predictions"]
        snap_df = bundle["snapshot"]

        # Çekiliş başına dinamik katman görünümü.
        cols = ["draw", "clock"]
        for layer in LAYERS:
            cols += [f"capacity_{layer}", f"pred_{layer}", f"low_{layer}", f"high_{layer}", f"actual_{layer}"]
        available = [c for c in cols if c in layer_df.columns]
        st.markdown("#### Her çekilişte katman: kapasite → beklenen ± tolerans → gerçek")
        st.dataframe(layer_df[available], use_container_width=True, hide_index=True, height=420)

        merged = perf_df.merge(pred_df[["draw", "pool20", "coupon10"]], on="draw", how="left")
        st.markdown("#### Dondurulmuş tahmin ve sonuç")
        st.dataframe(
            merged[["draw", "clock", "pool20", "pool20_hits", "coupon10", "coupon10_hits", "quota_mae", "baseline_quota_mae"]],
            use_container_width=True, hide_index=True, height=360,
        )

        draw_options = layer_df["draw"].astype(int).tolist()
        if draw_options:
            sd = st.selectbox("Bu saatte çekiliş seç", draw_options, index=len(draw_options)-1, key="v4_draw_detail")
            sub = snap_df[snap_df["draw"].astype(int) == int(sd)].copy()
            st.markdown("#### Hedef öncesi 80 sayının tamamı — sonuç etiketi sonradan eklenmiştir")
            st.dataframe(
                sub.sort_values(["layer_before", "model_score_before"], ascending=[True, False]),
                use_container_width=True, hide_index=True, height=620,
            )

    # -------------------------------------------------------------------------
    # Tehlikeli işlem: bilinçli reset.
    # -------------------------------------------------------------------------
    st.divider()
    with st.expander("Araştırmayı sıfırlama — yalnız geçmiş veri değiştiyse"):
        st.warning("Bu işlem yeni bir run_id açar. Eski shard'ları silmez ama aktif checkpoint sıfırdan başlar.")
        confirm = st.text_input("Sıfırlamak için SIFIRLA yaz", value="", key="v4_reset_text")
        if st.button("Yeni V4 araştırması başlat", disabled=(confirm.strip().upper() != "SIFIRLA")):
            fresh = new_state()
            save_state(cfg, fresh)
            st.session_state.pop("v4_view_bundle", None)
            st.session_state.pop("v4_last_bundle", None)
            st.success("Yeni araştırma checkpoint'i oluşturuldu.")
            st.rerun()


if __name__ == "__main__":
    main()
