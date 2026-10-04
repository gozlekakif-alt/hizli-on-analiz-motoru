# -*- coding: utf-8 -*-
"""
HIZLI ON — GÜN GÜN AİLE & RİTİM LABORATUVARI V4.0

Mimari:
- SQLite YOK.
- 36 gün tek tek işlenir; bir gün 2'li→10'lu tamamen bitmeden sonraki güne geçilmez.
- Gün tamamlanınca tek gzip CSV GitHub app-state dalına yazılır ve progress.json güncellenir.
- Uygulama kapanırsa yalnız tamamlanmamış gün yeniden hesaplanır; bitmiş günlere dönmez.
- Günlük aşama bittikten sonra yalnız günlük ritim sonuçlarından gelen aileler için günler-arası taşıma analizi yapılır.

Kilitli aktivasyon tanımı:
- Bir aile yalnızca üyelerinin TAMAMI AYNI TEK ÇEKİLİŞTE bulunduğunda aktive olur.
- Saat içinde birikme aktivasyon değildir.
- Ana ritim mesafesi çekiliş numarası farkıdır.

Not: Bu yazılım geçmiş çekiliş örüntülerini araştırır; gelecek çekiliş veya kazanç garantisi vermez.
"""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import itertools
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On — Gün Gün Ritim", page_icon="🧬", layout="wide")

APP_VERSION = "AILE_RITIM_V4.1_SEPARATE_STATE_REPO"
DEFAULT_DATA_FILE = Path("veri.txt")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"
STATE_BRANCH_DEFAULT = "main"
STATE_ROOT_DEFAULT = ".aile_ritim_gun_gun_v41"
LEGACY_STATE_BRANCH = "app-state"
LEGACY_STATE_ROOT = ".aile_ritim_gun_gun_v4"
DEFAULT_STATE_REPO = "gozlekakif-alt/hizli-on-analiz-state"
SIZES = list(range(2, 11))
MIN_ACTIVATIONS = 3
RUN_LIMIT_SECONDS = 8 * 60

# --------------------------------------------------------------------------------------
# SECRETS / GITHUB
# --------------------------------------------------------------------------------------
def safe_secret(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, default)
        return str(v) if v is not None else default
    except Exception:
        return default


def _clean_token(token: str) -> str:
    t = (token or "").strip().strip('"').strip("'")
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    elif t.lower().startswith("token "):
        t = t[6:].strip()
    return t


def settings():
    code_repo = (safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO).strip()
    code_branch = (safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH).strip()
    state_repo = (safe_secret("GITHUB_STATE_REPO", DEFAULT_STATE_REPO) or DEFAULT_STATE_REPO).strip()
    state_branch = (safe_secret("GITHUB_STATE_BRANCH", STATE_BRANCH_DEFAULT) or STATE_BRANCH_DEFAULT).strip()
    root = (safe_secret("GITHUB_STATE_ROOT", STATE_ROOT_DEFAULT) or STATE_ROOT_DEFAULT).strip().strip("/")
    token = _clean_token(
        safe_secret("GITHUB_TOKEN", "") or safe_secret("GH_TOKEN", "") or safe_secret("GITHUB_PAT", "")
    )
    return code_repo, code_branch, state_repo, state_branch, root, token


class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, detail: str):
        self.status = int(status)
        self.detail = detail
        super().__init__(f"GitHub HTTP {status}: {detail}")


def _api_request(url: str, token: str, method: str = "GET", payload=None,
                 accept: str = "application/vnd.github+json", timeout: int = 120,
                 expect_json: bool = True):
    headers = {
        "Accept": accept,
        "User-Agent": "hizli-on-gun-gun-v4",
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


def _api_path(path: str) -> str:
    return urllib.parse.quote(path.strip("/"), safe="/")


def ensure_state_branch(repo: str, main_branch: str, state_branch: str, token: str):
    if not token:
        raise RuntimeError("GITHUB_TOKEN yok")
    ref_name = urllib.parse.quote(f"heads/{state_branch}", safe="/")
    ref_url = f"https://api.github.com/repos/{repo}/git/ref/{ref_name}"
    try:
        _api_request(ref_url, token)
        return
    except GitHubAPIError as e:
        if e.status != 404:
            raise
    main_ref = urllib.parse.quote(f"heads/{main_branch}", safe="/")
    base = _api_request(f"https://api.github.com/repos/{repo}/git/ref/{main_ref}", token)
    sha = base["object"]["sha"]
    try:
        _api_request(
            f"https://api.github.com/repos/{repo}/git/refs",
            token,
            method="POST",
            payload={"ref": f"refs/heads/{state_branch}", "sha": sha},
        )
    except GitHubAPIError as e:
        if e.status == 422:
            _api_request(ref_url, token)
            return
        raise


def file_meta(repo: str, branch: str, path: str, token: str):
    url = f"https://api.github.com/repos/{repo}/contents/{_api_path(path)}?ref={urllib.parse.quote(branch, safe='')}"
    try:
        return _api_request(url, token)
    except GitHubAPIError as e:
        if e.status == 404:
            return None
        raise


def get_bytes(repo: str, branch: str, path: str, token: str) -> bytes:
    url = f"https://api.github.com/repos/{repo}/contents/{_api_path(path)}?ref={urllib.parse.quote(branch, safe='')}"
    return _api_request(url, token, accept="application/vnd.github.raw+json", expect_json=False)


def put_bytes(repo: str, branch: str, path: str, token: str, data: bytes, message: str):
    url = f"https://api.github.com/repos/{repo}/contents/{_api_path(path)}"
    meta = file_meta(repo, branch, path, token)
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if meta and meta.get("sha"):
        payload["sha"] = meta["sha"]
    try:
        return _api_request(url, token, method="PUT", payload=payload, timeout=180)
    except GitHubAPIError as e:
        if e.status not in (409, 422):
            raise
        meta = file_meta(repo, branch, path, token)
        payload.pop("sha", None)
        if meta and meta.get("sha"):
            payload["sha"] = meta["sha"]
        return _api_request(url, token, method="PUT", payload=payload, timeout=180)


def github_auth_status(repo: str, token: str):
    if not token:
        return False, "GITHUB_TOKEN bulunamadı"
    try:
        obj = _api_request(f"https://api.github.com/repos/{repo}", token)
        return True, f"GitHub token kabul edildi · repo: {obj.get('full_name', repo)}"
    except Exception as e:
        return False, str(e)



def repo_exists_and_writable(repo: str, token: str):
    if not token:
        return False, "GITHUB_TOKEN bulunamadı"
    try:
        obj = _api_request(f"https://api.github.com/repos/{repo}", token)
        perms = obj.get("permissions") or {}
        writable = bool(perms.get("push") or perms.get("admin") or perms.get("maintain"))
        if writable:
            return True, f"Durum deposu hazır · {obj.get('full_name', repo)}"
        return False, f"Durum deposuna yazma izni yok: {repo}"
    except GitHubAPIError as e:
        if e.status == 404:
            return False, f"Durum deposu bulunamadı: {repo}"
        return False, str(e)
    except Exception as e:
        return False, str(e)


def migrate_legacy_state_if_needed(code_repo: str, state_repo: str, state_branch: str,
                                   state_root: str, token: str, data_hash: str, dates: List[str]):
    """V4 aynı-repo app-state kayıtlarını bir kez ayrı durum deposuna taşır."""
    new_base, new_progress = state_paths(state_root, data_hash)
    if file_meta(state_repo, state_branch, new_progress, token):
        return False, 0

    legacy_base, legacy_progress = state_paths(LEGACY_STATE_ROOT, data_hash)
    try:
        raw = get_bytes(code_repo, LEGACY_STATE_BRANCH, legacy_progress, token)
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return False, 0
    if obj.get("data_hash") != data_hash:
        return False, 0

    completed = [d for d in obj.get("completed_days", []) if d in dates]
    copied_days = []
    for day in completed:
        try:
            b = get_bytes(code_repo, LEGACY_STATE_BRANCH, day_path(legacy_base, day), token)
            put_bytes(state_repo, state_branch, day_path(new_base, day), token, b, f"V4.1 migration day {day}")
            copied_days.append(day)
        except Exception:
            # progress only marks days that were already persisted; if a single file is missing,
            # don't mark that day complete in the new state.
            pass

    safe_completed = copied_days
    obj["version"] = APP_VERSION
    obj["completed_days"] = safe_completed
    obj["daily_counts"] = {k:v for k,v in (obj.get("daily_counts") or {}).items() if k in safe_completed}
    obj["final_sizes"] = []
    obj["updated_at"] = datetime.now().isoformat(timespec="seconds")
    put_bytes(
        state_repo, state_branch, new_progress, token,
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        f"V4.1 migrate legacy progress {obj['updated_at']}"
    )
    return True, len(safe_completed)

# --------------------------------------------------------------------------------------
# VERİ
# --------------------------------------------------------------------------------------
def load_data_text(uploaded=None):
    if uploaded is not None:
        raw = uploaded.getvalue()
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                return raw.decode(enc), f"Yüklenen dosya: {uploaded.name}"
            except Exception:
                pass
        return raw.decode("utf-8", errors="replace"), f"Yüklenen dosya: {uploaded.name}"
    if DEFAULT_DATA_FILE.exists():
        return DEFAULT_DATA_FILE.read_text(encoding="utf-8", errors="replace"), "GitHub/yerel veri.txt"
    repo, branch, _, _, _, token = settings()
    path = safe_secret("GITHUB_DATA_PATH", DEFAULT_PATH) or DEFAULT_PATH
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-gun-gun-v4"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace"), f"GitHub RAW: {repo}/{path}"


def _parse_nums_field(s: str) -> List[int]:
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s)]
    return sorted(set(n for n in nums if 1 <= n <= 80))


def parse_draws(text: str) -> pd.DataFrame:
    rows = []
    line_re = re.compile(
        r"^\s*#?(\d{4,})\s*[;|]\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s*[;|]\s*(.*?)\s*$"
    )
    for line in text.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        nums = _parse_nums_field(m.group(4))
        if len(nums) != 20:
            continue
        try:
            dt = datetime.strptime(f"{m.group(2)} {m.group(3)}", "%d.%m.%Y %H:%M")
        except Exception:
            continue
        rows.append((int(m.group(1)), dt, nums))

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
                while j < min(i + 5, len(lines)):
                    m = re.fullmatch(r"\s*#?\s*(\d{4,})\s*", lines[j])
                    if m:
                        draw = int(m.group(1)); j += 1; break
                    j += 1
            if draw is None:
                i += 1; continue
            dt = None
            while j < min(i + 10, len(lines)):
                m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})", lines[j])
                if m:
                    try:
                        dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M")
                    except Exception:
                        dt = None
                    j += 1
                    break
                j += 1
            if dt is None:
                i += 1; continue
            nums = []
            while j < len(lines) and len(nums) < 20:
                if "çekiliş no" in lines[j].lower():
                    break
                m = re.fullmatch(r"\s*(\d{1,2})\s*", lines[j])
                if m:
                    n = int(m.group(1))
                    if 1 <= n <= 80:
                        nums.append(n)
                j += 1
            nums = sorted(set(nums))
            if len(nums) == 20:
                rows.append((draw, dt, nums))
            i = max(i + 1, j)

    if not rows:
        return pd.DataFrame(columns=["draw", "dt", "nums"])
    df = pd.DataFrame(rows, columns=["draw", "dt", "nums"])
    df = df.sort_values(["draw", "dt"]).drop_duplicates("draw", keep="last").reset_index(drop=True)
    return df


def data_hash_for_df(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for r in df.itertuples(index=False):
        h.update(f"{int(r.draw)}|{pd.Timestamp(r.dt).isoformat()}|{','.join(map(str,r.nums))}\n".encode("utf-8"))
    return h.hexdigest()


def nums_to_mask(nums: Iterable[int]) -> int:
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m


def mask_to_nums(mask: int) -> Tuple[int, ...]:
    out = []
    x = int(mask)
    while x:
        b = x & -x
        out.append(b.bit_length())
        x ^= b
    return tuple(out)


def family_text(nums: Iterable[int]) -> str:
    return "-".join(f"{int(n):02d}" for n in nums)


def bit_indices(bits: int):
    x = int(bits)
    out = []
    while x:
        b = x & -x
        out.append(b.bit_length() - 1)
        x ^= b
    return out


def build_day_bits(df_day: pd.DataFrame):
    num_bits = [0] * 81
    draw_masks = []
    for i, nums in enumerate(df_day["nums"]):
        bit = 1 << i
        m = nums_to_mask(nums)
        draw_masks.append(m)
        for n in nums:
            num_bits[int(n)] |= bit
    return num_bits, draw_masks


def occurrence_bits(nums: Tuple[int, ...], num_bits: List[int]) -> int:
    b = num_bits[nums[0]]
    for n in nums[1:]:
        b &= num_bits[n]
        if not b:
            break
    return b


# --------------------------------------------------------------------------------------
# RİTİM
# --------------------------------------------------------------------------------------
def _best_equal_run(vals: List[int]):
    best = None
    i = 0
    while i < len(vals):
        j = i + 1
        while j < len(vals) and vals[j] == vals[i]:
            j += 1
        run = j - i
        if run >= 2 and (best is None or run > best[0]):
            best = (run, i, j, vals[i])
        i = j
    return best


def classify_draw_gaps(draws: List[int], near_tol: int = 1):
    if len(draws) < 3:
        return [], [], []
    gaps = [int(draws[i+1] - draws[i]) for i in range(len(draws)-1)]
    labels, details = [], []
    eq = _best_equal_run(gaps)
    if eq:
        run, _, _, d = eq
        labels.append("DUZ")
        details.append(f"DUZ:+{d} x{run}")
    if len(gaps) >= 3:
        found = None
        for w in range(min(6, len(gaps)), 2, -1):
            for i in range(len(gaps)-w+1):
                s = gaps[i:i+w]
                if max(s)-min(s) <= near_tol and len(set(s)) > 1:
                    found = s; break
            if found: break
        if found:
            labels.append("YAKIN")
            details.append("YAKIN:" + ",".join(f"+{x}" for x in found))
    for i in range(len(gaps)-3):
        a,b,c,d = gaps[i:i+4]
        if a == c and b == d and a != b:
            labels.append("ZIKZAK")
            details.append(f"ZIKZAK:+{a},+{b},+{a},+{b}")
            break
    for i in range(len(gaps)-5):
        s = gaps[i:i+6]
        if s[:3] == s[3:6] and len(set(s[:3])) > 1:
            labels.append("TEKRAR_3")
            details.append("TEKRAR3:" + ",".join(f"+{x}" for x in s))
            break
    for i in range(len(gaps)-2):
        a,b,c = gaps[i:i+3]
        step = b-a
        if step != 0 and c-b == step and min(a,b,c) > 0:
            labels.append("BASAMAKLI")
            details.append(f"BASAMAK:+{a},+{b},+{c}")
            break
    return list(dict.fromkeys(labels)), list(dict.fromkeys(details)), gaps


def classify_times(dts: List[pd.Timestamp]):
    labels, details = [], []
    if len(dts) < 3:
        return labels, details
    mins = [x.minute for x in dts]
    if len(set(mins)) == 1:
        labels.append("SABIT_DAKIKA")
        details.append(f"SABIT_DAKIKA=:{mins[0]:02d}")
    else:
        mc = Counter(mins).most_common(1)[0]
        if mc[1] >= 3 and mc[1] / len(mins) >= 0.6:
            labels.append("DAKIKA_BASKIN")
            details.append(f"DAKIKA_BASKIN=:{mc[0]:02d}({mc[1]}/{len(mins)})")
    minute_stamps = [int(x.timestamp() // 60) for x in dts]
    tgaps = [minute_stamps[i+1]-minute_stamps[i] for i in range(len(minute_stamps)-1)]
    eq = _best_equal_run(tgaps)
    if eq:
        run, _, _, gap = eq
        if gap > 0:
            labels.append("SABIT_ZAMAN_ARALIGI")
            details.append(f"SABIT_ZAMAN:+{gap}dk x{run}")
    return list(dict.fromkeys(labels)), list(dict.fromkeys(details))


def analyze_occurrence(nums: Tuple[int, ...], bits: int, df_scope: pd.DataFrame, near_tol: int = 1):
    if bits.bit_count() < MIN_ACTIVATIONS:
        return None
    idxs = bit_indices(bits)
    draws = [int(df_scope.iloc[i]["draw"]) for i in idxs]
    dts = [pd.Timestamp(df_scope.iloc[i]["dt"]) for i in idxs]
    labels1, details1, gaps = classify_draw_gaps(draws, near_tol)
    labels2, details2 = classify_times(dts)
    labels = list(dict.fromkeys(labels1 + labels2))
    if not labels:
        return None
    return {
        "family_mask": str(nums_to_mask(nums)),
        "family": family_text(nums),
        "support": len(idxs),
        "draws": ",".join(map(str, draws)),
        "times": "|".join(x.strftime("%Y-%m-%d %H:%M") for x in dts),
        "gaps": ",".join(map(str, gaps)),
        "rhythm_types": ",".join(labels),
        "rhythm_detail": " | ".join(details1 + details2),
    }


# --------------------------------------------------------------------------------------
# GÜNLÜK TARAMA
# --------------------------------------------------------------------------------------
def scan_small_size(df_day: pd.DataFrame, k: int, near_tol: int = 1):
    num_bits, _ = build_day_bits(df_day)
    out = []
    for nums in itertools.combinations(range(1, 81), k):
        b = occurrence_bits(nums, num_bits)
        if b.bit_count() < MIN_ACTIVATIONS:
            continue
        r = analyze_occurrence(nums, b, df_day, near_tol)
        if r:
            r["size"] = k
            r["method"] = "EXHAUSTIVE_DAY"
            out.append(r)
    return out


def generate_large_candidates(df_day: pd.DataFrame):
    """5..10 için eksiksiz aday üretimi: >=3 aktivasyon varsa aile en az bir 3-çekiliş kesişiminin altkümesidir."""
    _, masks = build_day_bits(df_day)
    cands = {k: set() for k in range(5, 11)}
    n = len(masks)
    for i in range(n-2):
        a = masks[i]
        for j in range(i+1, n-1):
            ab = a & masks[j]
            if ab.bit_count() < 5:
                continue
            for q in range(j+1, n):
                inter = ab & masks[q]
                s = inter.bit_count()
                if s < 5:
                    continue
                vals = mask_to_nums(inter)
                for k in range(5, min(10, s)+1):
                    for nums in itertools.combinations(vals, k):
                        cands[k].add(nums_to_mask(nums))
    return cands


def scan_large_sizes(df_day: pd.DataFrame, near_tol: int = 1, progress_cb=None):
    num_bits, _ = build_day_bits(df_day)
    cands = generate_large_candidates(df_day)
    results = {}
    for k in range(5, 11):
        out = []
        masks = cands[k]
        if progress_cb:
            progress_cb(k, len(masks))
        for m in masks:
            nums = mask_to_nums(m)
            b = occurrence_bits(nums, num_bits)
            if b.bit_count() < MIN_ACTIVATIONS:
                continue
            r = analyze_occurrence(nums, b, df_day, near_tol)
            if r:
                r["size"] = k
                r["method"] = "TRIPLE_INTERSECTION_DAY"
                out.append(r)
        results[k] = out
    return results


def analyze_one_day(df_day: pd.DataFrame, near_tol: int = 1, status_cb=None):
    all_rows = []
    for k in (2,3,4):
        if status_cb: status_cb(f"{k}'li tam tarama")
        all_rows.extend(scan_small_size(df_day, k, near_tol))
    if status_cb: status_cb("5–10 üçlü-çekiliş kesişim adayları")
    large = scan_large_sizes(
        df_day, near_tol,
        progress_cb=(lambda k,n: status_cb(f"{k}'li aday doğrulama · aday={n:,}")) if status_cb else None
    )
    for k in range(5,11):
        all_rows.extend(large[k])
    cols = ["size","method","family_mask","family","support","draws","times","gaps","rhythm_types","rhythm_detail"]
    return pd.DataFrame(all_rows, columns=cols)


def df_to_gzip_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
        txt = io.TextIOWrapper(gz, encoding="utf-8-sig", newline="", write_through=True)
        df.to_csv(txt, index=False)
        txt.flush(); txt.detach()
    return buf.getvalue()


def gzip_csv_bytes_to_df(data: bytes) -> pd.DataFrame:
    with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
        return pd.read_csv(gz, dtype={"family_mask": str, "family": str})


# --------------------------------------------------------------------------------------
# KALICI DURUM
# --------------------------------------------------------------------------------------
def state_paths(root: str, data_hash: str):
    base = f"{root}/{data_hash}"
    return base, f"{base}/progress.json"


def default_state(data_hash: str, dates: List[str]):
    return {
        "version": APP_VERSION,
        "data_hash": data_hash,
        "dates": dates,
        "completed_days": [],
        "daily_counts": {},
        "final_sizes": [],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_state(repo: str, branch: str, progress_path: str, token: str, data_hash: str, dates: List[str]):
    try:
        raw = get_bytes(repo, branch, progress_path, token)
        obj = json.loads(raw.decode("utf-8"))
        if obj.get("data_hash") == data_hash:
            obj.setdefault("completed_days", [])
            obj.setdefault("daily_counts", {})
            obj.setdefault("final_sizes", [])
            return obj
    except GitHubAPIError as e:
        if e.status != 404:
            raise
    except Exception:
        pass
    return default_state(data_hash, dates)


def save_state(repo: str, branch: str, progress_path: str, token: str, state: dict):
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    data = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    put_bytes(repo, branch, progress_path, token, data, f"V4 progress {state['updated_at']}")


def day_path(base: str, day: str):
    return f"{base}/days/day-{day}.csv.gz"


def final_path(base: str, k: int):
    return f"{base}/final/final-size-{k:02d}.csv.gz"


def save_day(repo, branch, base, token, day: str, df_day_result: pd.DataFrame):
    data = df_to_gzip_csv_bytes(df_day_result)
    put_bytes(repo, branch, day_path(base, day), token, data, f"V4 günlük sonuç {day}")


def build_combined_daily_csv_gz(repo, branch, base, token, completed_days: List[str], out_path: Path):
    """
    Daha önce GitHub durum deposuna yazılmış günlük sonuç dosyalarını TEKRAR ANALİZ ETMEDEN
    tek bir gzip CSV dosyasında birleştirir. Belleği korumak için günleri sırayla işler.
    """
    total_rows = 0
    writer = None
    expected_fields = None

    with gzip.open(out_path, "wt", encoding="utf-8-sig", newline="") as fout:
        for day in completed_days:
            data = get_bytes(repo, branch, day_path(base, day), token)
            with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
                txt = io.TextIOWrapper(gz, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(txt)
                fields = list(reader.fieldnames or [])
                if not fields:
                    continue
                if expected_fields is None:
                    expected_fields = fields
                    writer = csv.DictWriter(fout, fieldnames=["day"] + expected_fields)
                    writer.writeheader()
                elif fields != expected_fields:
                    raise ValueError(f"{day} günlük sonuç sütunları diğer günlerle uyuşmuyor.")

                for row in reader:
                    writer.writerow({"day": day, **row})
                    total_rows += 1

    return total_rows


# --------------------------------------------------------------------------------------
# GÜNLER ARASI ANALİZ
# --------------------------------------------------------------------------------------
def build_full_bits(df: pd.DataFrame):
    bits = [0] * 81
    for i, nums in enumerate(df["nums"]):
        b = 1 << i
        for n in nums:
            bits[int(n)] |= b
    return bits


def consecutive_pairs(days: List[str]) -> int:
    ds = sorted(datetime.strptime(x, "%Y-%m-%d").date() for x in set(days))
    s = set(ds)
    return sum(1 for d in ds if d + timedelta(days=1) in s)


def cross_day_time_features(dts: List[pd.Timestamp]):
    by_clock = defaultdict(set)
    by_minute = defaultdict(set)
    for x in dts:
        day = x.strftime("%Y-%m-%d")
        by_clock[x.strftime("%H:%M")].add(day)
        by_minute[x.strftime("%M")].add(day)
    clock_best = max(((len(v), k) for k,v in by_clock.items()), default=(0,""))
    minute_best = max(((len(v), k) for k,v in by_minute.items()), default=(0,""))
    return clock_best, minute_best


def collect_daily_family_stats(repo, branch, base, token, completed_days: List[str]):
    stats = {}
    for day in completed_days:
        data = get_bytes(repo, branch, day_path(base, day), token)
        ddf = gzip_csv_bytes_to_df(data)
        if ddf.empty:
            continue
        for r in ddf.itertuples(index=False):
            key = (int(r.size), str(r.family_mask))
            ent = stats.setdefault(key, {
                "family": str(r.family), "rhythmic_days": set(), "day_details": []
            })
            ent["rhythmic_days"].add(day)
            ent["day_details"].append(f"{day}:{r.rhythm_types}")
    return stats


def analyze_cross_day_size(df_all: pd.DataFrame, full_bits, stats: dict, k: int, near_tol: int = 1):
    rows = []
    for (size, mask_text), ent in stats.items():
        if size != k:
            continue
        nums = mask_to_nums(int(mask_text))
        bits = occurrence_bits(nums, full_bits)
        if bits.bit_count() < MIN_ACTIVATIONS:
            continue
        idxs = bit_indices(bits)
        draws = [int(df_all.iloc[i]["draw"]) for i in idxs]
        dts = [pd.Timestamp(df_all.iloc[i]["dt"]) for i in idxs]
        active_days = sorted(set(x.strftime("%Y-%m-%d") for x in dts))
        rhythmic_days = sorted(ent["rhythmic_days"])
        if len(active_days) < 2:
            continue
        cpairs = consecutive_pairs(active_days)
        glabels, gdetails, _ = classify_draw_gaps(draws, near_tol)
        clock_best, minute_best = cross_day_time_features(dts)
        same_clock_days, same_clock = clock_best
        same_minute_days, same_minute = minute_best

        # Taşınma ölçütü: günlük ritim göstermiş aile en az iki güne taşınmalı ve
        # ya ardışık günlerde aktif olmalı, ya günler-arası ritim/saat izi göstermeli,
        # ya da en az iki ayrı günde yeniden günlük ritim üretmiş olmalı.
        carries = (
            cpairs >= 1 or
            bool(glabels) or
            same_clock_days >= 2 or
            same_minute_days >= 3 or
            len(rhythmic_days) >= 2
        )
        if not carries:
            continue
        rows.append({
            "size": k,
            "family_mask": mask_text,
            "family": ent["family"],
            "rhythmic_days": len(rhythmic_days),
            "active_days": len(active_days),
            "consecutive_day_pairs": cpairs,
            "total_activations": len(idxs),
            "global_rhythm_types": ",".join(glabels),
            "global_rhythm_detail": " | ".join(gdetails),
            "same_clock": same_clock if same_clock_days >= 2 else "",
            "same_clock_days": same_clock_days,
            "same_minute": same_minute if same_minute_days >= 3 else "",
            "same_minute_days": same_minute_days,
            "first_activation": dts[0].strftime("%Y-%m-%d %H:%M"),
            "last_activation": dts[-1].strftime("%Y-%m-%d %H:%M"),
            "rhythmic_day_list": "|".join(rhythmic_days),
            "daily_rhythm_trace": " || ".join(ent["day_details"]),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(
            ["rhythmic_days","consecutive_day_pairs","active_days","total_activations"],
            ascending=[False,False,False,False]
        ).reset_index(drop=True)
    return out


# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------
st.title("🧬 Hızlı On — Gün Gün Aile & Ritim Laboratuvarı V4")
st.caption(
    "SQLite yok • Her gün 2'li→10'lu tamamen biter • Gün tamamlanınca GitHub'a tek dosya • "
    "Bitmiş gün bir daha başa dönmez • En sonda yalnız günler-arası taşınan ritimli aileler"
)

with st.expander("🔒 Kilitli analiz kuralları", expanded=False):
    st.write("• Aktivasyon: ailenin bütün üyeleri aynı tek çekilişte birlikte bulunur.")
    st.write("• 2–4: günlük 1–80 evreninde tam tarama.")
    st.write("• 5–10: en az 3 tam aktivasyonu eksiksiz yakalayan üçlü-çekiliş kesişim taraması.")
    st.write("• Bir günün 2–10 analizi bitmeden sonraki güne geçilmez.")
    st.write("• Final: yalnız günlük ritim listelerine girmiş ve günler arasında taşınmış aileler.")

uploaded = st.file_uploader("İstersen veri.txt yükle (boş bırakırsan repo/yerel veri.txt okunur)", type=["txt"])
try:
    raw_text, source = load_data_text(uploaded)
    df = parse_draws(raw_text)
except Exception as e:
    st.error(f"Veri okunamadı: {e}")
    st.stop()

if df.empty:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

df["day"] = df["dt"].dt.strftime("%Y-%m-%d")
dates = sorted(df["day"].unique().tolist())
data_hash = data_hash_for_df(df)

c1,c2,c3,c4 = st.columns(4)
c1.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
c2.metric("Gün", len(dates))
c3.metric("İlk", df.iloc[0]["dt"].strftime("%d.%m.%Y"))
c4.metric("Son", df.iloc[-1]["dt"].strftime("%d.%m.%Y"))
st.caption(f"Veri: {source} · #{int(df.iloc[0]['draw'])} → #{int(df.iloc[-1]['draw'])}")

near_tol = st.number_input("Yakın ritim toleransı (çekiliş farkı)", min_value=0, max_value=5, value=1, step=1)

code_repo, main_branch, state_repo, state_branch, root, token = settings()
auth_ok, auth_msg = github_auth_status(code_repo, token)
if not auth_ok:
    st.error(f"GitHub kod deposu okunamadı: {auth_msg}")
    st.stop()

state_ok, state_msg = repo_exists_and_writable(state_repo, token)
if not state_ok:
    st.error(state_msg)
    st.info(
        "Bu sürüm analiz sonucunu UYGULAMANIN KENDİ REPOSUNA yazmaz. "
        "GitHub'da ayrı bir `hizli-on-analiz-state` deposu oluştur ve Streamlit Secrets'e "
        "`GITHUB_STATE_REPO = \"gozlekakif-alt/hizli-on-analiz-state\"` ekle. "
        "Tokenın bu ikinci depoda Contents: Read and write izni olmalı."
    )
    st.stop()

st.success(f"🔐 Kod: {code_repo} · Kalıcı durum: {state_repo}/{state_branch}")

base, progress_path = state_paths(root, data_hash)
try:
    migrated, migrated_days = migrate_legacy_state_if_needed(
        code_repo, state_repo, state_branch, root, token, data_hash, dates
    )
    if migrated:
        st.success(f"Eski V4 kaydı ayrı durum deposuna taşındı · korunan gün: {migrated_days}")
    state = load_state(state_repo, state_branch, progress_path, token, data_hash, dates)
except Exception as e:
    st.error(f"progress.json okunamadı/taşınamadı: {e}")
    st.stop()

completed = [d for d in state.get("completed_days", []) if d in dates]
remaining = [d for d in dates if d not in completed]

m1,m2,m3 = st.columns(3)
m1.metric("Tamamlanan gün", f"{len(completed)}/{len(dates)}")
m2.metric("Sıradaki gün", remaining[0] if remaining else "TÜMÜ TAMAM")
m3.metric("Final boyut", f"{len(state.get('final_sizes', []))}/9")
st.progress(len(completed)/max(1,len(dates)), text=f"Günlük analiz: {len(completed)}/{len(dates)}")

if state.get("daily_counts"):
    latest_days = completed[-8:]
    rows=[]
    for d in latest_days:
        counts = state["daily_counts"].get(d, {})
        rows.append({"Gün": d, **{f"{k}'li": int(counts.get(str(k),0)) for k in SIZES}})
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

status_box = st.empty()
day_prog = st.empty()

run = st.button("▶ GÜNLÜK ANALİZİ BAŞLAT / KALDIĞI YERDEN DEVAM ET", width="stretch", disabled=not remaining)
if run:
    start = time.time()
    processed_now = 0
    try:
        while True:
            completed = [d for d in state.get("completed_days", []) if d in dates]
            remaining = [d for d in dates if d not in completed]
            if not remaining:
                break
            day = remaining[0]
            ddf = df[df["day"] == day].reset_index(drop=True)
            status_box.info(f"📅 {day} işleniyor · çekiliş={len(ddf)}")

            def _status(msg):
                day_prog.info(f"{day} → {msg}")

            result = analyze_one_day(ddf, int(near_tol), _status)
            counts = {str(k): int((result["size"] == k).sum()) if not result.empty else 0 for k in SIZES}

            # Önce gün dosyası; başarıyla yazıldıktan sonra progress TAMAM olarak işaretlenir.
            save_day(state_repo, state_branch, base, token, day, result)
            state.setdefault("completed_days", []).append(day)
            state["completed_days"] = sorted(set(state["completed_days"]), key=dates.index)
            state.setdefault("daily_counts", {})[day] = counts
            save_state(state_repo, state_branch, progress_path, token, state)
            processed_now += 1
            status_box.success(f"✅ {day} TAMAM · 2'li→10'lu kaydedildi")

            if time.time() - start >= RUN_LIMIT_SECONDS:
                break
        st.success(f"Bu çalıştırmada {processed_now} gün tamamlandı. Kalıcı kayıt ayrı GitHub durum deposunda.")
        st.rerun()
    except Exception as e:
        st.error(f"Günlük analiz durdu. Tamamlanmış günler korunuyor. Hata: {type(e).__name__}: {e}")

# Final günler-arası analiz
completed = [d for d in state.get("completed_days", []) if d in dates]
all_days_done = len(completed) == len(dates)
if all_days_done:
    st.divider()
    st.subheader(f"📦 {len(completed)} günlük tamamlanmış sonuç — tek çıktı")
    st.caption(
        "Bu bölüm 36 günü yeniden analiz etmez. GitHub durum deposunda zaten tamamlanmış günlük "
        "sonuç dosyalarını okuyup tek CSV.GZ dosyasında birleştirir."
    )

    make_daily_all = st.button(
        f"📦 {len(completed)} GÜNLÜK TEK ÇIKTI HAZIRLA — YENİDEN ANALİZ YOK",
        width="stretch",
        key="make_all_daily_output",
    )
    if make_daily_all:
        try:
            status_box.info(f"{len(completed)} tamamlanmış günlük sonuç dosyası birleştiriliyor; analiz yapılmıyor...")
            out_path = Path(f"/tmp/HIZLI_ON_V4_{len(completed)}_GUN_TUM_GUNLUK_SONUCLAR.csv.gz")
            row_count = build_combined_daily_csv_gz(
                state_repo, state_branch, base, token, completed, out_path
            )
            st.session_state["v4_all_daily_output"] = str(out_path)
            st.session_state["v4_all_daily_output_rows"] = int(row_count)
            status_box.success(
                f"✅ {len(completed)} günün kayıtlı sonuçları tek dosyada hazır · satır={row_count:,}".replace(",", ".")
            )
        except Exception as e:
            st.error(f"Tek günlükler-birleşik çıktı hazırlanamadı: {type(e).__name__}: {e}")

    daily_all_path = st.session_state.get("v4_all_daily_output")
    if daily_all_path and Path(daily_all_path).exists():
        rows_ready = int(st.session_state.get("v4_all_daily_output_rows", 0))
        st.success(
            f"✅ {len(completed)} günlük bütün çıktı hazır"
            + (f" · {rows_ready:,} kayıt".replace(",", ".") if rows_ready else "")
        )
        with open(daily_all_path, "rb") as f:
            st.download_button(
                f"⬇️ {len(completed)} GÜNLÜK TEK BÜTÜN ÇIKTIYI İNDİR",
                data=f,
                file_name=f"HIZLI_ON_V4_{len(completed)}_GUN_TUM_GUNLUK_SONUCLAR.csv.gz",
                mime="application/gzip",
                width="stretch",
                key="download_all_daily_output",
            )

    st.divider()
    st.subheader("🌉 Günler arası taşınan ritimli aileler")
    st.caption("Yalnız günlük ritim dosyalarına girmiş aileler değerlendirilir; bütün 1–80 kombinasyonları yeniden taranmaz.")
    final_done = set(int(x) for x in state.get("final_sizes", []))
    st.write("Tamamlanan final boyutları:", ", ".join(map(str, sorted(final_done))) if final_done else "henüz yok")

    do_final = st.button("🌉 GÜNLER ARASI FİNAL ANALİZİNİ BAŞLAT / DEVAM ET", width="stretch", disabled=len(final_done)==9)
    if do_final:
        try:
            status_box.info("Günlük sonuç dosyaları okunuyor...")
            stats = collect_daily_family_stats(state_repo, state_branch, base, token, completed)
            full_bits = build_full_bits(df)
            for k in SIZES:
                if k in final_done:
                    continue
                status_box.info(f"🌉 Final {k}'li aileler analiz ediliyor...")
                out = analyze_cross_day_size(df, full_bits, stats, k, int(near_tol))
                put_bytes(
                    state_repo, state_branch, final_path(base, k), token,
                    df_to_gzip_csv_bytes(out),
                    f"V4 final {k}'li günler-arası ritim"
                )
                state.setdefault("final_sizes", []).append(k)
                state["final_sizes"] = sorted(set(int(x) for x in state["final_sizes"]))
                save_state(state_repo, state_branch, progress_path, token, state)
            st.success("✅ 2'li→10'lu günler-arası final analiz tamamlandı.")
            st.rerun()
        except Exception as e:
            st.error(f"Final analiz durdu; tamamlanan final boyutları korunuyor. Hata: {type(e).__name__}: {e}")

    # Final özet ve ZIP
    final_done = set(int(x) for x in state.get("final_sizes", []))
    if final_done:
        summary=[]
        for k in sorted(final_done):
            try:
                xdf = gzip_csv_bytes_to_df(get_bytes(state_repo, state_branch, final_path(base,k), token))
                summary.append({"Boyut": f"{k}'li", "Taşınan ritimli aile": len(xdf)})
            except Exception:
                pass
        if summary:
            st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)

    if len(final_done) == 9:
        if st.button("📦 FİNAL 2–10 ZIP HAZIRLA", width="stretch"):
            try:
                zp = Path("/tmp/HIZLI_ON_V4_GUNLER_ARASI_FINAL.zip")
                with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                    for k in SIZES:
                        b = get_bytes(state_repo, state_branch, final_path(base,k), token)
                        z.writestr(f"final_{k:02d}li.csv.gz", b)
                    z.writestr("progress.json", json.dumps(state, ensure_ascii=False, indent=2))
                st.session_state["v4_final_zip"] = str(zp)
            except Exception as e:
                st.error(f"ZIP hazırlanamadı: {e}")
        zpath = st.session_state.get("v4_final_zip")
        if zpath and Path(zpath).exists():
            with open(zpath, "rb") as f:
                st.download_button(
                    "⬇️ HIZLI_ON_V4_GUNLER_ARASI_FINAL.zip",
                    data=f,
                    file_name="HIZLI_ON_V4_GUNLER_ARASI_FINAL.zip",
                    mime="application/zip",
                    width="stretch",
                )

st.divider()
st.caption(
    "V4.1 güvenlik ilkesi: SQLite yok ve analiz sonuçları Streamlit'in çalıştığı kod reposuna YAZILMAZ. "
    "Kalıcı sonuçlar ayrı GitHub durum deposunda tutulur. Böylece her gün kaydı Streamlit'i yeniden deploy etmez. "
    "Bir gün sonuç dosyası yazılmadan progress.json içinde TAMAM sayılmaz."
)
