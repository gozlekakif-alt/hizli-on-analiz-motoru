# -*- coding: utf-8 -*-
"""
HIZLI ON — AİLE & RİTİM LABORATUVARI V1

Kilitli tanım:
- Bir aile yalnızca üyelerinin TAMAMI AYNI TEK ÇEKİLİŞTE bulunduğunda aktive olur.
- Saat içinde birikme / pencere birleşimi aktivasyon değildir.
- Aile boyutları 2,3,4,5,6,7,8,9,10 sırayla işlenir.
- Ana ritim mesafesi çekiliş numarası farkıdır.
- APP düşük RAM için boyut boyut çalışır, sonuçları SQLite'a yazar ve kaldığı yerden devam eder.

Not:
Bu yazılım geçmiş çekiliş örüntülerini araştırır; gelecek çekiliş veya kazanç garantisi vermez.
"""

from __future__ import annotations

import base64
import csv
import gzip
import gc
import hashlib
import io
import itertools
import json
import math
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------------------
# SAYFA / SABİTLER
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="Hızlı On — Aile & Ritim", page_icon="🧬", layout="wide")

APP_VERSION = "AILE_RITIM_V1.7_SQLITE_SAFE_LOWRAM"
DEFAULT_DATA_FILE = Path("veri.txt")
DB_PATH = Path("/tmp/aile_ritim_checkpoint_v17.sqlite3")
DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"
CHECKPOINT_BRANCH_DEFAULT = "app-state"
CHECKPOINT_ROOT_DEFAULT = ".aile_ritim_state_v17"
CHECKPOINT_CHUNK_BYTES = 8 * 1024 * 1024  # düşük RAM için 8 MB parçalar
REMOTE_AUTOSAVE_SECONDS = 600  # yaklaşık 10 dakikada bir kalıcı checkpoint
SIZES = list(range(2, 11))
LOW_MASK = (1 << 64) - 1

# RAM'i korumak için:
# 2..6: 1..80 evrenindeki aileleri boyut boyut, prefix-prefix tarar.
# 7..10: tekrar eden büyük aileler için çekiliş-kesişim aday taraması kullanır.
EXHAUSTIVE_MAX_K = 6
PAIR_SCAN_MIN_K = 7

# Ritim tanımının en küçük örnek sayısı. 3 aktivasyon düz ritmi (d,d) gösterebilir.
MIN_ACTIVATIONS = 3

# --------------------------------------------------------------------------------------
# YARDIMCILAR
# --------------------------------------------------------------------------------------
def safe_secret(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, default)
        return str(v) if v is not None else default
    except Exception:
        return default


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def github_read_text(repo: str, branch: str, path: str, token: str = "") -> str:
    """Public repo için RAW, token varsa GitHub API kullanır."""
    if token:
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github.raw+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "hizli-on-aile-ritim",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "hizli-on-aile-ritim"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def load_data_text(uploaded=None):
    """Öncelik: yüklenen dosya > repo içindeki veri.txt > GitHub raw/API."""
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

    repo = safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO
    branch = safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH
    path = safe_secret("GITHUB_DATA_PATH", DEFAULT_PATH) or DEFAULT_PATH
    token = safe_secret("GITHUB_TOKEN", "")
    try:
        return github_read_text(repo, branch, path, token), f"GitHub: {repo}/{path}"
    except Exception as e:
        return "", f"GitHub veri.txt okunamadı: {e}"


class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, detail: str, url: str):
        self.status = int(status)
        self.detail = detail
        self.url = url
        super().__init__(f"GitHub HTTP {status}: {detail}")


def _clean_github_token(token: str) -> str:
    t = (token or "").strip().strip('"').strip("'")
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    elif t.lower().startswith("token "):
        t = t[6:].strip()
    return t


def checkpoint_settings():
    repo = (safe_secret("GITHUB_REPO", DEFAULT_REPO) or DEFAULT_REPO).strip()
    base_branch = (safe_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH).strip()
    state_branch = (
        safe_secret("GITHUB_CHECKPOINT_BRANCH", CHECKPOINT_BRANCH_DEFAULT)
        or CHECKPOINT_BRANCH_DEFAULT
    ).strip()
    root = (
        safe_secret("GITHUB_CHECKPOINT_ROOT", CHECKPOINT_ROOT_DEFAULT)
        or CHECKPOINT_ROOT_DEFAULT
    ).strip().strip("/")
    token = (
        safe_secret("GITHUB_TOKEN", "")
        or safe_secret("GH_TOKEN", "")
        or safe_secret("GITHUB_PAT", "")
    )
    return repo, base_branch, state_branch, root, _clean_github_token(token)


def _github_api_request(url: str, token: str, method: str = "GET", payload=None,
                        accept: str = "application/vnd.github+json", timeout: int = 90,
                        expect_json: bool = True):
    headers = {
        "Accept": accept,
        "User-Agent": "hizli-on-aile-ritim",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if not expect_json:
                return body
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "json" in ctype:
                return json.loads(body.decode("utf-8", errors="replace"))
            return body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            try:
                obj = json.loads(body)
                detail = obj.get("message", body)
                errors = obj.get("errors")
                if errors:
                    detail += f" | {errors}"
            except Exception:
                detail = body
        except Exception:
            detail = str(e)
        detail = (detail or str(e)).replace("\n", " ")[:900]
        raise GitHubAPIError(e.code, detail, url) from e


def _api_path(path: str) -> str:
    return urllib.parse.quote(path.strip("/"), safe="/")


def _git_blob_sha(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(f"blob {len(data)}\0".encode("ascii"))
    h.update(data)
    return h.hexdigest()


def ensure_checkpoint_branch(repo: str, base_branch: str, state_branch: str, token: str):
    """app-state dalını güvenli biçimde oluşturur; 422'yi körlemesine yutmaz."""
    ref = urllib.parse.quote(f"heads/{state_branch}", safe="/")
    ref_url = f"https://api.github.com/repos/{repo}/git/ref/{ref}"
    try:
        _github_api_request(ref_url, token)
        return
    except GitHubAPIError as e:
        if e.status != 404:
            raise

    base_ref = urllib.parse.quote(f"heads/{base_branch}", safe="/")
    base = _github_api_request(
        f"https://api.github.com/repos/{repo}/git/ref/{base_ref}", token
    )
    sha = base["object"]["sha"]

    try:
        _github_api_request(
            f"https://api.github.com/repos/{repo}/git/refs",
            token,
            method="POST",
            payload={"ref": f"refs/heads/{state_branch}", "sha": sha},
        )
    except GitHubAPIError as create_err:
        # Aynı anda başka oturum dalı oluşturmuşsa 422 gelebilir. Gerçekten oluştu mu kontrol et.
        if create_err.status == 422:
            try:
                _github_api_request(ref_url, token)
                return
            except Exception:
                pass
        raise


def github_file_meta(repo: str, branch: str, path: str, token: str):
    url = (
        f"https://api.github.com/repos/{repo}/contents/{_api_path(path)}"
        f"?ref={urllib.parse.quote(branch, safe='')}"
    )
    try:
        return _github_api_request(url, token)
    except GitHubAPIError as e:
        if e.status == 404:
            return None
        raise


def github_get_bytes(repo: str, branch: str, path: str, token: str) -> bytes:
    url = (
        f"https://api.github.com/repos/{repo}/contents/{_api_path(path)}"
        f"?ref={urllib.parse.quote(branch, safe='')}"
    )
    return _github_api_request(
        url, token, accept="application/vnd.github.raw+json", timeout=120, expect_json=False
    )


def github_put_bytes(repo: str, branch: str, path: str, token: str,
                     data: bytes, message: str):
    """Küçük parça dosyasını yaz. Aynı içerik varsa commit üretmez."""
    url = f"https://api.github.com/repos/{repo}/contents/{_api_path(path)}"
    meta = github_file_meta(repo, branch, path, token)
    local_blob_sha = _git_blob_sha(data)
    if meta and meta.get("sha") == local_blob_sha:
        return "unchanged"

    body = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if meta and meta.get("sha"):
        body["sha"] = meta["sha"]

    try:
        _github_api_request(url, token, method="PUT", payload=body, timeout=180)
        return "written"
    except GitHubAPIError as first_err:
        # Paralel/önceki commit yüzünden SHA eskidiyse bir kez tazele ve yeniden dene.
        if first_err.status not in (409, 422):
            raise
        meta2 = github_file_meta(repo, branch, path, token)
        body2 = {
            "message": message,
            "content": base64.b64encode(data).decode("ascii"),
            "branch": branch,
        }
        if meta2 and meta2.get("sha"):
            if meta2.get("sha") == local_blob_sha:
                return "unchanged"
            body2["sha"] = meta2["sha"]
        _github_api_request(url, token, method="PUT", payload=body2, timeout=180)
        return "written"


def _db_progress_score(path: Path, data_hash: str):
    """Aynı veri için hangi DB daha ileride onu belirler. Bağlantıyı HER durumda kapatır."""
    if not path.exists() or path.stat().st_size == 0:
        return (-1, -1, "")
    con = None
    try:
        con = sqlite3.connect(path, timeout=10)
        con.execute("PRAGMA busy_timeout=10000")
        info = con.execute("PRAGMA table_info(progress)").fetchall()
        if not info:
            return (-1, -1, "")
        cols = {str(r[1]) for r in info}
        if not {"data_hash", "size"}.issubset(cols):
            return (-1, -1, "")

        done_expr = "done" if "done" in cols else "0"
        scanned_expr = "scanned" if "scanned" in cols else "0"
        updated_expr = "COALESCE(updated_at,'')" if "updated_at" in cols else "''"
        rows = con.execute(
            f"SELECT {done_expr},{scanned_expr},{updated_expr} FROM progress WHERE data_hash=?",
            (data_hash,),
        ).fetchall()
        if not rows:
            return (0, 0, "")
        return (
            sum(int(r[0] or 0) for r in rows),
            sum(int(r[1] or 0) for r in rows),
            max(str(r[2] or "") for r in rows),
        )
    except Exception:
        return (-1, -1, "")
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass


def _checkpoint_paths(root: str, data_hash: str):
    base = f"{root}/{data_hash}"
    return base, f"{base}/manifest.json"


def save_checkpoint_to_github(con, data_hash: str, reason: str = "checkpoint"):
    """
    SQLite dosyasını tek dev dosya olarak değil 16 MB ham parçalara ayırır.
    Her parça ayrı gziplenir; manifest EN SON yazılır. Böylece 100 MB/422 sorunu aşılır.
    """
    repo, base_branch, state_branch, root, token = checkpoint_settings()
    if not token:
        return False, "GITHUB_TOKEN yok; checkpoint yalnız bu Streamlit oturumunda kalır."

    try:
        # Yalnız aktif veri setini taşı; checkpoint gereksiz büyümesin.
        con.execute("DELETE FROM results WHERE data_hash<>?", (data_hash,))
        con.execute("DELETE FROM progress WHERE data_hash<>?", (data_hash,))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.commit()

        ensure_checkpoint_branch(repo, base_branch, state_branch, token)

        raw_size = DB_PATH.stat().st_size
        base_path, manifest_path = _checkpoint_paths(root, data_hash)
        parts = []
        written = 0
        unchanged = 0

        with DB_PATH.open("rb") as f:
            idx = 0
            while True:
                raw = f.read(CHECKPOINT_CHUNK_BYTES)
                if not raw:
                    break
                packed = gzip.compress(raw, compresslevel=6)
                part_name = f"part-{idx:05d}.bin.gz"
                remote_part = f"{base_path}/{part_name}"
                action = github_put_bytes(
                    repo, state_branch, remote_part, token, packed,
                    f"Aile ritim checkpoint parça {idx:05d} · {reason}",
                )
                if action == "written":
                    written += 1
                else:
                    unchanged += 1
                parts.append({
                    "name": part_name,
                    "raw_size": len(raw),
                    "packed_size": len(packed),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "packed_sha256": hashlib.sha256(packed).hexdigest(),
                })
                idx += 1

        score = _db_progress_score(DB_PATH, data_hash)
        manifest = {
            "format": "sqlite-chunks-v1",
            "app_version": APP_VERSION,
            "data_hash": data_hash,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
            "raw_size": raw_size,
            "chunk_bytes": CHECKPOINT_CHUNK_BYTES,
            "score": [score[0], score[1], score[2]],
            "parts": parts,
        }
        manifest_bytes = json.dumps(
            manifest, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

        # Manifest en son: yarım yükleme restore sırasında "tam checkpoint" sanılmasın.
        github_put_bytes(
            repo, state_branch, manifest_path, token, manifest_bytes,
            f"Aile ritim checkpoint manifest · {reason}",
        )
        total_packed = sum(int(p["packed_size"]) for p in parts)
        return True, (
            f"GitHub kalıcı checkpoint OK · {len(parts)} parça · "
            f"{total_packed/1024/1024:.1f} MB · yeni {written}, değişmeyen {unchanged}"
        )
    except GitHubAPIError as e:
        return False, f"GitHub checkpoint yazılamadı: HTTP {e.status} · {e.detail}"
    except Exception as e:
        return False, f"GitHub checkpoint yazılamadı: {e}"


def restore_checkpoint_from_github(data_hash: str):
    """Manifest + parçaları indirip, uzaktaki DB daha ilerideyse yerel DB'yi geri kurar."""
    repo, _, state_branch, root, token = checkpoint_settings()
    if not token:
        return False, "GITHUB_TOKEN bulunamadı; kalıcı checkpoint okunamadı."

    base_path, manifest_path = _checkpoint_paths(root, data_hash)
    try:
        manifest_raw = github_get_bytes(repo, state_branch, manifest_path, token)
        manifest = json.loads(manifest_raw.decode("utf-8"))
        if manifest.get("format") != "sqlite-chunks-v1":
            return False, "GitHub checkpoint biçimi tanınmadı."
        if manifest.get("data_hash") != data_hash:
            return False, "GitHub checkpoint başka veri.txt için."

        remote_score = tuple(manifest.get("score") or (-1, -1, ""))
        local_score = _db_progress_score(DB_PATH, data_hash)
        if len(remote_score) == 3 and local_score >= remote_score:
            return False, "Yerel checkpoint GitHub kaydından geri değil."

        tmp = DB_PATH.with_suffix(".remote.tmp.sqlite3")
        with tmp.open("wb") as out:
            for p in manifest.get("parts", []):
                remote_part = f"{base_path}/{p['name']}"
                packed = github_get_bytes(repo, state_branch, remote_part, token)
                if hashlib.sha256(packed).hexdigest() != p["packed_sha256"]:
                    raise RuntimeError(f"Parça doğrulaması başarısız: {p['name']}")
                raw = gzip.decompress(packed)
                if hashlib.sha256(raw).hexdigest() != p["raw_sha256"]:
                    raise RuntimeError(f"Ham parça doğrulaması başarısız: {p['name']}")
                out.write(raw)

        if tmp.stat().st_size != int(manifest.get("raw_size", -1)):
            raise RuntimeError("Checkpoint boyutu uyuşmuyor.")

        tmp_score = _db_progress_score(tmp, data_hash)
        if tmp_score < local_score:
            tmp.unlink(missing_ok=True)
            return False, "İndirilen checkpoint yerelden geri; kullanılmadı."

        for extra in (Path(str(DB_PATH) + "-wal"), Path(str(DB_PATH) + "-shm")):
            try:
                extra.unlink()
            except FileNotFoundError:
                pass
        tmp.replace(DB_PATH)
        return True, (
            f"GitHub checkpoint geri yüklendi · tamamlanan boyut={tmp_score[0]} · "
            f"taranan={tmp_score[1]:,}".replace(",", ".")
        )
    except GitHubAPIError as e:
        if e.status == 404:
            return False, "Henüz GitHub kalıcı checkpoint kaydı yok."
        return False, f"GitHub checkpoint okunamadı: HTTP {e.status} · {e.detail}"
    except Exception as e:
        return False, f"GitHub checkpoint okunamadı: {e}"


def github_auth_status():
    repo, _, _, _, token = checkpoint_settings()
    if not token:
        return False, "GITHUB_TOKEN bulunamadı — kalıcı GitHub kaydı yapılamaz."
    try:
        _github_api_request(f"https://api.github.com/repos/{repo}", token)
        return True, f"GitHub token kabul edildi · repo: {repo}"
    except GitHubAPIError as e:
        return False, f"GitHub token/repo kontrolü başarısız: HTTP {e.status} · {e.detail}"
    except Exception as e:
        return False, f"GitHub kontrolü başarısız: {e}"


def import_result_backup(uploaded, con, data_hash: str):
    """
    Eski CSV veya CSV.GZ çıktısını yeni SQLite'a taşır.
    2'li ve 3'lü boyutlar bu projede tamamlanmış eski çıktı olarak işaretlenebilir.
    4+ satırlar korunur fakat ilerleme baştan doğrulanır; INSERT OR IGNORE tekrarları engeller.
    """
    if uploaded is None:
        return False, "Yedek dosya seçilmedi."

    name = (uploaded.name or "").lower()
    uploaded.seek(0)
    if name.endswith(".gz"):
        raw_stream = gzip.GzipFile(fileobj=uploaded, mode="rb")
        text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8-sig", errors="replace", newline="")
    else:
        text_stream = io.TextIOWrapper(uploaded, encoding="utf-8-sig", errors="replace", newline="")

    counts = Counter()
    inserted = 0
    try:
        reader = csv.DictReader(text_stream)
        required = {"size", "family", "support", "draws", "times", "gaps",
                    "rhythm_types", "rhythm_detail", "time_character"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            return False, "CSV sütunları bu uygulamanın yedeğiyle uyumlu değil."

        for row in reader:
            try:
                k = int(row["size"])
                nums = tuple(int(x) for x in row["family"].split("-"))
                if k not in SIZES or len(nums) != k:
                    continue
                counts[k] += 1
                cur = con.execute(
                    """INSERT OR IGNORE INTO results(
                           data_hash,size,family_mask,family,support,draws,times,gaps,
                           rhythm_types,rhythm_detail,time_character
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        data_hash, k, str(family_mask(nums)), row["family"],
                        int(row["support"]), row["draws"], row["times"], row["gaps"],
                        row["rhythm_types"], row["rhythm_detail"], row["time_character"],
                    ),
                )
                inserted += int(cur.rowcount > 0)
                if inserted and inserted % 500 == 0:
                    con.commit()
            except Exception:
                continue
        con.commit()

        # Bu kullanıcının eski çıktısında 2'li ve 3'lü tamamlanmıştı.
        for k in (2, 3):
            if counts.get(k, 0):
                total = math.comb(80, k)
                max_first = 80 - k + 1
                con.execute(
                    """UPDATE progress
                       SET cursor=?,done=1,scanned=?,rhythmic_found=?,updated_at=?
                       WHERE data_hash=? AND size=?""",
                    (
                        max_first + 1, total, counts[k],
                        datetime.now().isoformat(timespec="seconds"), data_hash, k,
                    ),
                )
        # 4+ sonuçları korunur ama cursor ilerletilmez; eksik prefix varsa güvenli biçimde yeniden taranır.
        for k in range(4, 11):
            if counts.get(k, 0):
                con.execute(
                    """UPDATE progress
                       SET rhythmic_found=(SELECT COUNT(*) FROM results WHERE data_hash=? AND size=?),
                           updated_at=?
                       WHERE data_hash=? AND size=?""",
                    (
                        data_hash, k, datetime.now().isoformat(timespec="seconds"),
                        data_hash, k,
                    ),
                )
        con.commit()
        return True, (
            f"Yedek içe aktarıldı · yeni kayıt {inserted:,} · "
            f"2'li={counts.get(2,0):,} · 3'lü={counts.get(3,0):,} · "
            f"4+'lı={sum(v for kk,v in counts.items() if kk>=4):,}"
        ).replace(",", ".")
    finally:
        try:
            text_stream.detach()
        except Exception:
            pass


def _parse_nums_field(s: str) -> List[int]:
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", s)]
    nums = [n for n in nums if 1 <= n <= 80]
    # sıra sonucu değiştirmez; tekrarlı sayıları ayıkla
    return sorted(set(nums))


def parse_draws(text: str) -> pd.DataFrame:
    rows = []

    # 1) Kompakt satırlar:
    # 51213;25.08.2026 00:02;2,4,...
    # 51213 | 25.08.2026 00:02 | 2 4 ...
    line_re = re.compile(
        r"^\s*#?(\d{4,})\s*[;|]\s*(\d{2}\.\d{2}\.\d{4})\s+" 
        r"(\d{2}:\d{2})\s*[;|]\s*(.*?)\s*$"
    )
    for line in text.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        draw = int(m.group(1))
        ds, ts = m.group(2), m.group(3)
        nums = _parse_nums_field(m.group(4))
        if len(nums) == 20:
            try:
                dt = datetime.strptime(f"{ds} {ts}", "%d.%m.%Y %H:%M")
            except Exception:
                continue
            rows.append((draw, dt, nums))

    # 2) Milli Piyango kopyala-yapıştır biçimi
    # Çekiliş no: 55118 / 11.09.2026-23:57 / 20 sayı ayrı satırlar
    if not rows:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if "Çekiliş no" not in s and "çekiliş no" not in s.lower():
                i += 1
                continue

            draw = None
            m = re.search(r"(\d{4,})", s)
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
                if "Çekiliş no" in lines[j] or "çekiliş no" in lines[j].lower():
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

    # Aynı çekilişi tekilleştir, kronolojik sıraya koy
    best = {}
    for draw, dt, nums in rows:
        best[(draw, dt)] = nums
    out = pd.DataFrame([(d, dt, ns) for (d, dt), ns in best.items()], columns=["draw", "dt", "nums"])
    out = out.sort_values(["draw", "dt"]).drop_duplicates(subset=["draw"], keep="last").reset_index(drop=True)
    return out


def nums_to_mask(nums: Iterable[int]) -> int:
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m


def mask_to_nums(mask: int) -> Tuple[int, ...]:
    out = []
    m = int(mask)
    while m:
        lsb = m & -m
        out.append(lsb.bit_length())  # bit 0 -> sayı 1
        m ^= lsb
    return tuple(out)


def family_mask(nums: Iterable[int]) -> int:
    return nums_to_mask(nums)


def family_text(nums: Iterable[int]) -> str:
    return "-".join(f"{int(n):02d}" for n in nums)


def bits_to_indices(b: int) -> List[int]:
    out = []
    x = int(b)
    while x:
        lsb = x & -x
        out.append(lsb.bit_length() - 1)
        x ^= lsb
    return out


def build_vertical_bits(df: pd.DataFrame):
    """Yalnız gerekli bit yapılarını üret; tüm draw mask listesini RAM'de tutma."""
    num_bits = [0] * 81
    n = len(df)
    lows = np.empty(n, dtype=np.uint64)
    highs = np.empty(n, dtype=np.uint64)
    for i, nums in enumerate(df["nums"]):
        bit = 1 << i
        m = nums_to_mask(nums)
        lows[i] = np.uint64(m & LOW_MASK)
        highs[i] = np.uint64((m >> 64) & LOW_MASK)
        for num in nums:
            num_bits[int(num)] |= bit
    return num_bits, lows, highs


def occurrence_bits(nums: Tuple[int, ...], num_bits: List[int]) -> int:
    b = num_bits[nums[0]]
    for n in nums[1:]:
        b &= num_bits[n]
        if not b:
            break
    return b

# --------------------------------------------------------------------------------------
# RİTİM SINIFLANDIRMA
# --------------------------------------------------------------------------------------
def _best_equal_run(gaps: List[int]):
    best = None
    i = 0
    while i < len(gaps):
        j = i + 1
        while j < len(gaps) and gaps[j] == gaps[i]:
            j += 1
        run = j - i
        if run >= 2 and (best is None or run > best[0]):
            best = (run, i, j, gaps[i])
        i = j
    return best


def classify_rhythms(draws: List[int], near_tol: int = 1):
    """Aktivasyon çekilişleri arasındaki ardışık farklardan ritimleri bulur."""
    if len(draws) < 3:
        return [], [], []
    gaps = [int(draws[i + 1] - draws[i]) for i in range(len(draws) - 1)]
    labels = []
    details = []

    # DÜZ: en az d,d (3 aktivasyon). Daha uzunu otomatik yakalanır.
    eq = _best_equal_run(gaps)
    if eq:
        run, i, j, d = eq
        labels.append("DUZ")
        details.append(f"DUZ:+{d} x{run}")

    # YAKIN DÜZ: en az 3 gap, yayılım tolerans içinde; tam eşit değil.
    if len(gaps) >= 3:
        best_near = None
        for w in range(min(6, len(gaps)), 2, -1):
            for i in range(0, len(gaps) - w + 1):
                seg = gaps[i:i + w]
                if max(seg) - min(seg) <= near_tol and len(set(seg)) > 1:
                    best_near = seg
                    break
            if best_near:
                break
        if best_near:
            labels.append("YAKIN")
            details.append("YAKIN:" + ",".join(f"+{x}" for x in best_near))

    # ZİKZAK / ABAB
    for i in range(len(gaps) - 3):
        a, b, c, d = gaps[i:i + 4]
        if a == c and b == d and a != b:
            labels.append("ZIKZAK")
            details.append(f"ZIKZAK:+{a},+{b},+{a},+{b}")
            break

    # ÇİFT RİTİM: A,A,B,A,A,B
    for i in range(len(gaps) - 5):
        s = gaps[i:i + 6]
        if s[0] == s[1] == s[3] == s[4] and s[2] == s[5] and s[0] != s[2]:
            labels.append("CIFT_RITIM")
            details.append("CIFT:" + ",".join(f"+{x}" for x in s))
            break

    # 3'lü tekrar: ABCABC
    for i in range(len(gaps) - 5):
        s = gaps[i:i + 6]
        if s[:3] == s[3:6] and len(set(s[:3])) > 1:
            labels.append("TEKRAR_3")
            details.append("TEKRAR3:" + ",".join(f"+{x}" for x in s))
            break

    # Katlanarak / azalarak: aynı tam sayı oranıyla en az 3 gap
    for i in range(len(gaps) - 2):
        a, b, c = gaps[i:i + 3]
        if a > 0 and b > a and b % a == 0:
            q = b // a
            if q >= 2 and c == b * q:
                labels.append("KATLANARAK")
                details.append(f"KATLANARAK:x{q} ({a},{b},{c})")
                break
    for i in range(len(gaps) - 2):
        a, b, c = gaps[i:i + 3]
        if c > 0 and a > b and a % b == 0 and b % c == 0:
            q1, q2 = a // b, b // c
            if q1 == q2 and q1 >= 2:
                labels.append("AZALARAK")
                details.append(f"AZALARAK:/{q1} ({a},{b},{c})")
                break

    # Basamaklı: gap farkları sabit ve sıfır değil; en az 4 gap tercih, 3 gap da kabul.
    for i in range(len(gaps) - 2):
        a, b, c = gaps[i:i + 3]
        step = b - a
        if step != 0 and c - b == step and min(a, b, c) > 0:
            # mümkünse 4. gap da aynı adımda mı?
            seg = [a, b, c]
            if i + 3 < len(gaps) and gaps[i + 3] - c == step and gaps[i + 3] > 0:
                seg.append(gaps[i + 3])
            labels.append("BASAMAKLI")
            details.append("BASAMAK:" + ",".join(f"+{x}" for x in seg))
            break

    # Tekilleştir
    labels = list(dict.fromkeys(labels))
    details = list(dict.fromkeys(details))
    return labels, details, gaps


def time_character(idxs: List[int], df: pd.DataFrame) -> str:
    if not idxs:
        return ""
    dts = [pd.Timestamp(df.iloc[i]["dt"]) for i in idxs]
    mins = [x.minute for x in dts]
    hrs = [x.hour for x in dts]
    parts = []
    if len(set(mins)) == 1:
        parts.append(f"dakika=:{mins[0]:02d}")
    else:
        mc = Counter(mins).most_common(1)[0]
        if mc[1] >= 3:
            parts.append(f"dakika_baskin=:{mc[0]:02d}({mc[1]}/{len(mins)})")
    if len(set(hrs)) == 1:
        parts.append(f"saat={hrs[0]:02d}:xx")
    else:
        hc = Counter(hrs).most_common(1)[0]
        if hc[1] >= 3:
            parts.append(f"saat_baskin={hc[0]:02d}:xx({hc[1]}/{len(hrs)})")
    return ";".join(parts)

# --------------------------------------------------------------------------------------
# SQLITE
# --------------------------------------------------------------------------------------
def _table_info(con, table: str):
    try:
        return con.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return []


def _table_columns(con, table: str):
    return {str(r[1]) for r in _table_info(con, table)}


def _pk_columns(con, table: str):
    info = _table_info(con, table)
    return [str(r[1]) for r in sorted((r for r in info if int(r[5]) > 0), key=lambda r: int(r[5]))]


def _rebuild_progress_table(con):
    """progress tablosunu kesin V1.5 şemasına taşır; eski/ek NOT NULL kolonlarını temizler."""
    old_exists = bool(_table_info(con, "progress"))
    old_name = "progress_legacy_v15"
    con.execute(f"DROP TABLE IF EXISTS {old_name}")
    if old_exists:
        con.execute(f"ALTER TABLE progress RENAME TO {old_name}")

    con.execute(
        """
        CREATE TABLE progress(
            data_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            method TEXT NOT NULL,
            cursor INTEGER NOT NULL DEFAULT 0,
            done INTEGER NOT NULL DEFAULT 0,
            scanned INTEGER NOT NULL DEFAULT 0,
            rhythmic_found INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY(data_hash, size)
        )
        """
    )

    if old_exists:
        cols = _table_columns(con, old_name)
        if {"data_hash", "size"}.issubset(cols):
            def expr(name, default_sql):
                return name if name in cols else default_sql
            con.execute(
                f"""
                INSERT OR REPLACE INTO progress(
                    data_hash,size,method,cursor,done,scanned,rhythmic_found,updated_at
                )
                SELECT
                    data_hash,
                    size,
                    {expr('method', "''")},
                    {expr('cursor', '0')},
                    {expr('done', '0')},
                    {expr('scanned', '0')},
                    {expr('rhythmic_found', '0')},
                    {expr('updated_at', 'NULL')}
                FROM {old_name}
                WHERE data_hash IS NOT NULL AND size IS NOT NULL
                """
            )
        con.execute(f"DROP TABLE IF EXISTS {old_name}")


def _rebuild_results_table(con):
    """results tablosunu kesin V1.5 şemasına taşır."""
    old_exists = bool(_table_info(con, "results"))
    old_name = "results_legacy_v15"
    con.execute(f"DROP TABLE IF EXISTS {old_name}")
    if old_exists:
        con.execute(f"ALTER TABLE results RENAME TO {old_name}")

    con.execute(
        """
        CREATE TABLE results(
            data_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            family_mask TEXT NOT NULL,
            family TEXT NOT NULL,
            support INTEGER NOT NULL,
            draws TEXT NOT NULL,
            times TEXT NOT NULL,
            gaps TEXT NOT NULL,
            rhythm_types TEXT NOT NULL,
            rhythm_detail TEXT NOT NULL,
            time_character TEXT NOT NULL,
            PRIMARY KEY(data_hash, size, family_mask)
        )
        """
    )

    if old_exists:
        cols = _table_columns(con, old_name)
        required = {"data_hash", "size", "family_mask", "family"}
        if required.issubset(cols):
            def expr(name, default_sql):
                return name if name in cols else default_sql
            con.execute(
                f"""
                INSERT OR IGNORE INTO results(
                    data_hash,size,family_mask,family,support,draws,times,gaps,
                    rhythm_types,rhythm_detail,time_character
                )
                SELECT
                    data_hash,
                    size,
                    family_mask,
                    family,
                    {expr('support', '0')},
                    {expr('draws', "''")},
                    {expr('times', "''")},
                    {expr('gaps', "''")},
                    {expr('rhythm_types', "''")},
                    {expr('rhythm_detail', "''")},
                    {expr('time_character', "''")}
                FROM {old_name}
                WHERE data_hash IS NOT NULL
                  AND size IS NOT NULL
                  AND family_mask IS NOT NULL
                  AND family IS NOT NULL
                """
            )
        con.execute(f"DROP TABLE IF EXISTS {old_name}")


def _repair_schema(con):
    """Eski checkpoint şemalarını V1.5'in kesin şemasına güvenli biçimde taşır."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    expected_progress = {
        "data_hash", "size", "method", "cursor", "done", "scanned", "rhythmic_found", "updated_at"
    }
    expected_results = {
        "data_hash", "size", "family_mask", "family", "support", "draws", "times", "gaps",
        "rhythm_types", "rhythm_detail", "time_character"
    }

    pcols = _table_columns(con, "progress")
    ppk = _pk_columns(con, "progress")
    if pcols != expected_progress or ppk != ["data_hash", "size"]:
        _rebuild_progress_table(con)

    rcols = _table_columns(con, "results")
    rpk = _pk_columns(con, "results")
    if rcols != expected_results or rpk != ["data_hash", "size", "family_mask"]:
        _rebuild_results_table(con)

    # Tablo hiç yoksa rebuild fonksiyonları zaten oluşturur; yine de garanti et.
    if not _table_info(con, "progress"):
        _rebuild_progress_table(con)
    if not _table_info(con, "results"):
        _rebuild_results_table(con)

    con.commit()

def _quarantine_sqlite_files(path: Path, tag: str = "uyumsuz"):
    """Sorunlu SQLite dosyasını kenara alır; WAL/SHM kalıntılarını temizler."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if path.exists():
        bad = path.with_name(f"{path.stem}.{tag}_{stamp}{path.suffix}")
        try:
            path.replace(bad)
        except Exception:
            try:
                path.unlink()
            except Exception:
                pass
    for extra in (Path(str(path) + "-wal"), Path(str(path) + "-shm"), Path(str(path) + "-journal")):
        try:
            extra.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _open_sqlite_connection(path: Path):
    con = sqlite3.connect(path, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    # WAL yerine DELETE: Streamlit yeniden başlatmalarında tek dosyalı ve daha az kilit riski.
    try:
        con.execute("PRAGMA journal_mode=DELETE")
    except sqlite3.Error:
        pass
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=-8192")
    con.execute("PRAGMA temp_store=FILE")
    con.execute("PRAGMA mmap_size=0")
    return con


def _schema_write_probe(con):
    """progress tablosuna gerçek yazma yapılabildiğini yan etkisiz doğrular."""
    probe_hash = "__schema_probe_v17__"
    con.execute("SAVEPOINT v17_probe")
    try:
        con.execute(
            """INSERT OR REPLACE INTO progress(
                   data_hash,size,method,cursor,done,scanned,rhythmic_found,updated_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (probe_hash, 2, "PROBE", 0, 0, 0, 0, datetime.now().isoformat(timespec="seconds")),
        )
        con.execute("DELETE FROM progress WHERE data_hash=?", (probe_hash,))
        con.execute("ROLLBACK TO v17_probe")
        con.execute("RELEASE v17_probe")
    except Exception:
        try:
            con.execute("ROLLBACK TO v17_probe")
            con.execute("RELEASE v17_probe")
        except Exception:
            pass
        raise


def db_connect():
    """V1.7: eski/bozuk/kitli checkpoint uygulamayı düşürmesin; gerekirse temiz DB'ye geçer."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Ön kontrol: fiziksel DB bozuksa taşı.
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        probe = None
        try:
            probe = sqlite3.connect(DB_PATH, timeout=10)
            probe.execute("PRAGMA busy_timeout=10000")
            ok = probe.execute("PRAGMA quick_check").fetchone()
            if not ok or str(ok[0]).lower() != "ok":
                raise sqlite3.DatabaseError("quick_check başarısız")
        except sqlite3.Error:
            if probe is not None:
                try: probe.close()
                except Exception: pass
            _quarantine_sqlite_files(DB_PATH, "bozuk")
        finally:
            if probe is not None:
                try: probe.close()
                except Exception: pass

    # Birinci deneme: mevcut V1.7 DB'yi şema onarımı + gerçek yazma probundan geçir.
    con = None
    try:
        con = _open_sqlite_connection(DB_PATH)
        _repair_schema(con)
        con.commit()
        _schema_write_probe(con)
        con.commit()
        return con
    except sqlite3.Error:
        if con is not None:
            try:
                con.rollback()
            except Exception:
                pass
            try:
                con.close()
            except Exception:
                pass

    # Herhangi bir SQLite hatasında eski dosyaya tutunma: temiz V1.7 DB oluştur.
    _quarantine_sqlite_files(DB_PATH, "sqlite_hata")
    con = _open_sqlite_connection(DB_PATH)
    _repair_schema(con)
    con.commit()
    _schema_write_probe(con)
    con.commit()
    return con


def ensure_progress(con, data_hash: str, k: int, method: str):
    sql = """INSERT OR IGNORE INTO progress(data_hash,size,method,cursor,done,scanned,rhythmic_found,updated_at)
             VALUES(?,?,?,?,0,0,0,?)"""
    args = (data_hash, k, method, 0, datetime.now().isoformat(timespec="seconds"))
    try:
        con.execute(sql, args)
        con.commit()
        return
    except sqlite3.Error:
        # Hata metnine güvenme: Streamlit mesajı redakte edebilir. Tabloyu kesin şemayla yeniden kur ve tekrar dene.
        try:
            con.rollback()
        except Exception:
            pass
        _rebuild_progress_table(con)
        con.commit()
        con.execute(sql, args)
        con.commit()


def get_progress(con, data_hash: str, k: int):
    r = con.execute(
        "SELECT method,cursor,done,scanned,rhythmic_found FROM progress WHERE data_hash=? AND size=?",
        (data_hash, k),
    ).fetchone()
    return r or ("", 0, 0, 0, 0)


def update_progress(con, data_hash: str, k: int, cursor: int, done: int, scanned: int, found: int):
    con.execute(
        """UPDATE progress SET cursor=?,done=?,scanned=?,rhythmic_found=?,updated_at=?
           WHERE data_hash=? AND size=?""",
        (cursor, done, scanned, found, datetime.now().isoformat(timespec="seconds"), data_hash, k),
    )
    con.commit()


def insert_result(con, data_hash: str, k: int, nums: Tuple[int, ...], occ_b: int,
                  df: pd.DataFrame, near_tol: int = 1) -> bool:
    support = int(occ_b.bit_count())
    if support < MIN_ACTIVATIONS:
        return False
    idxs = bits_to_indices(occ_b)
    draw_list = [int(df.iloc[i]["draw"]) for i in idxs]
    labels, details, gaps = classify_rhythms(draw_list, near_tol=near_tol)
    if not labels:
        return False

    times = [pd.Timestamp(df.iloc[i]["dt"]).strftime("%Y-%m-%d %H:%M") for i in idxs]
    fm = str(family_mask(nums))
    cur = con.execute(
        """INSERT OR IGNORE INTO results(
               data_hash,size,family_mask,family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data_hash, k, fm, family_text(nums), support,
            ",".join(map(str, draw_list)),
            " | ".join(times),
            ",".join(map(str, gaps)),
            ",".join(labels),
            " | ".join(details),
            time_character(idxs, df),
        ),
    )
    return cur.rowcount > 0

# --------------------------------------------------------------------------------------
# TARAMA — 2..6 TAM EVREN / 7..10 KESİŞİM ADAYI
# --------------------------------------------------------------------------------------
def scan_exhaustive_k(con, data_hash: str, k: int, num_bits: List[int], df: pd.DataFrame,
                      near_tol: int, progress_box, status_box, stop_after_seconds: int = 0):
    """1..80'den C(80,k) aileyi prefix-prefix tarar. RAM sabittir, prefix checkpointlidir."""
    method, cursor, done, scanned, found = get_progress(con, data_hash, k)
    if done:
        return scanned, found, True

    max_first = 80 - k + 1  # ilk sayı 1..max_first
    start_first = max(1, int(cursor) if int(cursor) > 0 else 1)
    started = time.time()
    last_remote_save = time.time()
    pending_commit = 0

    # K için teorik toplam kombinasyon
    total = math.comb(80, k)

    for first in range(start_first, max_first + 1):
        tail_iter = itertools.combinations(range(first + 1, 81), k - 1)
        first_bits = num_bits[first]
        for tail in tail_iter:
            nums = (first,) + tail
            b = first_bits
            for n in tail:
                b &= num_bits[n]
                if not b:
                    break
            scanned += 1
            if b and b.bit_count() >= MIN_ACTIVATIONS:
                if insert_result(con, data_hash, k, nums, b, df, near_tol):
                    found += 1
                    pending_commit += 1
                    if pending_commit >= 250:
                        con.commit()
                        pending_commit = 0

        # Prefix bitince yerel checkpoint kesinleşir.
        next_first = first + 1
        update_progress(con, data_hash, k, next_first, 0, scanned, found)
        frac = min(1.0, scanned / max(1, total))
        progress_box.progress(
            frac,
            text=f"{k}'li: {scanned:,}/{total:,} aile tarandı · ritimli {found:,}".replace(",", ".")
        )
        status_box.caption(
            f"Yerel checkpoint: {k}'li ilk sayı {first} tamamlandı."
        )

        # Uzun taramada yaklaşık 10 dakikada bir kalıcı GitHub checkpoint.
        now = time.time()
        if now - last_remote_save >= REMOTE_AUTOSAVE_SECONDS:
            ok_remote, remote_msg = save_checkpoint_to_github(
                con, data_hash, f"{k}li_ilk_{first}"
            )
            if ok_remote:
                status_box.success(remote_msg)
            else:
                status_box.warning(remote_msg)
            last_remote_save = time.time()

        if stop_after_seconds and time.time() - started >= stop_after_seconds:
            con.commit()
            ok_remote, remote_msg = save_checkpoint_to_github(
                con, data_hash, f"{k}li_sure_dilimi"
            )
            if ok_remote:
                status_box.success(remote_msg)
            else:
                status_box.warning(remote_msg)
            return scanned, found, False

    con.commit()
    update_progress(con, data_hash, k, max_first + 1, 1, scanned, found)
    progress_box.progress(
        1.0, text=f"{k}'li tamamlandı · ritimli {found:,}".replace(",", ".")
    )
    ok_remote, remote_msg = save_checkpoint_to_github(
        con, data_hash, f"{k}li_tamam"
    )
    if ok_remote:
        status_box.success(remote_msg)
    else:
        status_box.warning(remote_msg)
    return scanned, found, True


def scan_pair_candidates_k(con, data_hash: str, k: int, num_bits: List[int], df: pd.DataFrame,
                           lows: np.ndarray, highs: np.ndarray, near_tol: int,
                           progress_box, status_box, stop_after_seconds: int = 0):
    """
    Büyük ailelerde bütün C(80,k) evrenini üretmek yerine gerçek çekiliş çiftlerinin
    ortak kümelerinden k'li aday üretir. Destek ve ritim daha sonra tam veri üzerinde doğrulanır.
    """
    method, cursor, done, scanned, found = get_progress(con, data_hash, k)
    if done:
        return scanned, found, True

    n = len(df)
    start_i = max(1, int(cursor) if int(cursor) > 0 else 1)
    started = time.time()
    last_remote_save = time.time()

    existing = {
        str(row[0]) for row in con.execute(
            "SELECT family_mask FROM results WHERE data_hash=? AND size=?", (data_hash, k)
        )
    }
    pending_commit = 0

    for i in range(start_i, n):
        inter_lo = np.bitwise_and(lows[:i], lows[i])
        inter_hi = np.bitwise_and(highs[:i], highs[i])
        counts = (
            np.bitwise_count(inter_lo).astype(np.uint16)
            + np.bitwise_count(inter_hi).astype(np.uint16)
        )
        js = np.flatnonzero(counts >= k)

        for j in js.tolist():
            m = int(inter_lo[j]) | (int(inter_hi[j]) << 64)
            root_nums = mask_to_nums(m)
            for nums in itertools.combinations(root_nums, k):
                scanned += 1
                fm = str(family_mask(nums))
                if fm in existing:
                    continue
                b = occurrence_bits(nums, num_bits)
                if b.bit_count() < MIN_ACTIVATIONS:
                    continue
                if insert_result(con, data_hash, k, nums, b, df, near_tol):
                    existing.add(fm)
                    found += 1
                    pending_commit += 1
                    if pending_commit >= 250:
                        con.commit()
                        pending_commit = 0

        update_progress(con, data_hash, k, i + 1, 0, scanned, found)
        if i % 10 == 0 or i == n - 1:
            frac = (i + 1) / max(1, n)
            progress_box.progress(
                frac,
                text=f"{k}'li: çekiliş {i+1:,}/{n:,} · aday {scanned:,} · ritimli {found:,}".replace(",", ".")
            )
            status_box.caption(
                f"Yerel checkpoint: {k}'li çekiliş indeks {i+1} seviyesinde."
            )

        now = time.time()
        if now - last_remote_save >= REMOTE_AUTOSAVE_SECONDS:
            ok_remote, remote_msg = save_checkpoint_to_github(
                con, data_hash, f"{k}li_index_{i+1}"
            )
            if ok_remote:
                status_box.success(remote_msg)
            else:
                status_box.warning(remote_msg)
            last_remote_save = time.time()

        if stop_after_seconds and time.time() - started >= stop_after_seconds:
            con.commit()
            ok_remote, remote_msg = save_checkpoint_to_github(
                con, data_hash, f"{k}li_sure_dilimi"
            )
            if ok_remote:
                status_box.success(remote_msg)
            else:
                status_box.warning(remote_msg)
            return scanned, found, False

    con.commit()
    update_progress(con, data_hash, k, n, 1, scanned, found)
    progress_box.progress(
        1.0, text=f"{k}'li tamamlandı · ritimli {found:,}".replace(",", ".")
    )
    ok_remote, remote_msg = save_checkpoint_to_github(
        con, data_hash, f"{k}li_tamam"
    )
    if ok_remote:
        status_box.success(remote_msg)
    else:
        status_box.warning(remote_msg)
    return scanned, found, True


# --------------------------------------------------------------------------------------
# RAPOR
# --------------------------------------------------------------------------------------
def build_report(con, data_hash: str, df: pd.DataFrame, source: str) -> str:
    lines = []
    lines.append("=" * 130)
    lines.append("HIZLI ON — AİLE & RİTİM TEK RAPOR")
    lines.append("=" * 130)
    lines.append(f"APP: {APP_VERSION}")
    lines.append(f"Kaynak: {source}")
    lines.append(f"Veri SHA256: {data_hash}")
    lines.append(f"Çekiliş: {len(df)}")
    lines.append(f"Gün: {df['dt'].dt.date.nunique()}")
    if not df.empty:
        lines.append(f"Aralık: {df.iloc[0]['dt']:%d.%m.%Y %H:%M} -> {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}")
    lines.append("")
    lines.append("KİLİTLİ AKTİVASYON TANIMI: Ailenin bütün üyeleri AYNI TEK ÇEKİLİŞTE birlikte bulunmalıdır.")
    lines.append("Saat/pencere içinde birikme aktivasyon sayılmaz. Ana ritim mesafesi çekiliş numarası farkıdır.")
    lines.append("Ritimler: DUZ, YAKIN, ZIKZAK, CIFT_RITIM, TEKRAR_3, KATLANARAK, AZALARAK, BASAMAKLI.")
    lines.append("")

    for k in SIZES:
        p = con.execute(
            "SELECT method,cursor,done,scanned,rhythmic_found FROM progress WHERE data_hash=? AND size=?",
            (data_hash, k),
        ).fetchone()
        if p:
            lines.append(
                f"{k}'li durum | yöntem={p[0]} | tamam={p[2]} | taranan_aday={p[3]} | ritimli_aile={p[4]}"
            )
    lines.append("")

    for k in SIZES:
        rows = con.execute(
            """SELECT family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
               FROM results WHERE data_hash=? AND size=?
               ORDER BY support DESC, family ASC""",
            (data_hash, k),
        ).fetchall()
        lines.append("#" * 130)
        lines.append(f"{k}'Lİ AİLELER — RİTİMLİ TAM AKTİVASYONLAR | adet={len(rows)}")
        lines.append("#" * 130)
        if not rows:
            lines.append("Ritim kaydı yok / tarama henüz tamamlanmamış olabilir.")
            lines.append("")
            continue
        for family, support, draws, times, gaps, rtypes, rdetail, tchar in rows:
            lines.append(
                f"{family} | tam_aktivasyon={support} | ritim={rtypes} | {rdetail}"
            )
            lines.append(f"  çekilişler: {draws}")
            lines.append(f"  aralıklar: {gaps}")
            lines.append(f"  zamanlar: {times}")
            if tchar:
                lines.append(f"  zaman_karakteri: {tchar}")
        lines.append("")

    return "\n".join(lines)


def build_csv(con, data_hash: str) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["size", "family", "support", "draws", "times", "gaps", "rhythm_types", "rhythm_detail", "time_character"])
    for row in con.execute(
        """SELECT size,family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
           FROM results WHERE data_hash=? ORDER BY size,support DESC,family""",
        (data_hash,),
    ):
        w.writerow(row)
    return out.getvalue()

def _export_paths(data_hash: str):
    short = data_hash[:12]
    return (
        Path(f"/tmp/HIZLI_ON_AILE_RITIM_TEK_RAPOR_{short}.txt.gz"),
        Path(f"/tmp/HIZLI_ON_AILE_RITIM_SONUCLAR_{short}.csv.gz"),
    )


def write_report_txt_gz(con, data_hash: str, df: pd.DataFrame, source: str, path: Path):
    """Raporu RAM'de dev string oluşturmadan doğrudan gzip dosyasına akıtır."""
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write("=" * 130 + "\nHIZLI ON — AİLE & RİTİM TEK RAPOR\n" + "=" * 130 + "\n")
        f.write(f"APP: {APP_VERSION}\nKaynak: {source}\nVeri SHA256: {data_hash}\n")
        f.write(f"Çekiliş: {len(df)}\nGün: {df['dt'].dt.date.nunique()}\n")
        if not df.empty:
            f.write(f"Aralık: {df.iloc[0]['dt']:%d.%m.%Y %H:%M} -> {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}\n")
        f.write("\nKİLİTLİ AKTİVASYON TANIMI: Ailenin bütün üyeleri AYNI TEK ÇEKİLİŞTE birlikte bulunmalıdır.\n")
        f.write("Saat/pencere içinde birikme aktivasyon sayılmaz. Ana ritim mesafesi çekiliş numarası farkıdır.\n")
        f.write("Ritimler: DUZ, YAKIN, ZIKZAK, CIFT_RITIM, TEKRAR_3, KATLANARAK, AZALARAK, BASAMAKLI.\n\n")
        for k in SIZES:
            p = con.execute(
                "SELECT method,cursor,done,scanned,rhythmic_found FROM progress WHERE data_hash=? AND size=?",
                (data_hash, k),
            ).fetchone()
            if p:
                f.write(f"{k}'li durum | yöntem={p[0]} | tamam={p[2]} | taranan_aday={p[3]} | ritimli_aile={p[4]}\n")
        f.write("\n")
        for k in SIZES:
            f.write("#" * 130 + "\n")
            count = con.execute(
                "SELECT COUNT(*) FROM results WHERE data_hash=? AND size=?", (data_hash, k)
            ).fetchone()[0]
            f.write(f"{k}'Lİ AİLELER — RİTİMLİ TAM AKTİVASYONLAR | adet={count}\n")
            f.write("#" * 130 + "\n")
            cur = con.execute(
                """SELECT family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
                   FROM results WHERE data_hash=? AND size=? ORDER BY support DESC, family ASC""",
                (data_hash, k),
            )
            any_row = False
            for family, support, draws, times, gaps, rtypes, rdetail, tchar in cur:
                any_row = True
                f.write(f"{family} | tam_aktivasyon={support} | ritim={rtypes} | {rdetail}\n")
                f.write(f"  çekilişler: {draws}\n  aralıklar: {gaps}\n  zamanlar: {times}\n")
                if tchar:
                    f.write(f"  zaman_karakteri: {tchar}\n")
            if not any_row:
                f.write("Ritim kaydı yok / tarama henüz tamamlanmamış olabilir.\n")
            f.write("\n")


def write_results_csv_gz(con, data_hash: str, path: Path):
    """CSV'yi RAM'e almadan satır satır gzip dosyasına yazar."""
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["size", "family", "support", "draws", "times", "gaps", "rhythm_types", "rhythm_detail", "time_character"])
        cur = con.execute(
            """SELECT size,family,support,draws,times,gaps,rhythm_types,rhythm_detail,time_character
               FROM results WHERE data_hash=? ORDER BY size,support DESC,family""",
            (data_hash,),
        )
        for row in cur:
            w.writerow(row)

# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------
st.title("🧬 Hızlı On — Aile & Ritim Laboratuvarı")
st.caption(
    "Tek çekilişte tam aktivasyon • 2'li→10'lu sırayla • çekiliş mesafesi ritimleri • "
    "düşük RAM V1.7 • SQLite V1.7 güvenli + parçalı GitHub checkpoint • büyük raporlar RAM'e alınmaz"
)

with st.expander("Kilitli kurallar", expanded=False):
    st.write(
        "Bir 6'lı aile ancak 6 sayının tamamı aynı çekilişin REAL20'sinde birlikteyse 6/6 aktive sayılır. "
        "Aynı kural 2'li–10'lu bütün aileler için geçerlidir. Saat içinde parça parça tamamlanma kabul edilmez."
    )
    st.write(
        "Ritim hesabı tam aktivasyon çekiliş numaralarının farklarından yapılır: düz, yakın, zikzak, "
        "katlanarak, azalarak, basamaklı, ABAB/çift ve ABCABC tekrar desenleri."
    )

uploaded = st.file_uploader("İstersen veri.txt yükle (boş bırakırsan GitHub/yerel veri.txt otomatik okunur)", type=["txt"])
text, source = load_data_text(uploaded)

if not text:
    st.error(source)
    st.stop()

df = parse_draws(text)
if df.empty:
    st.error("veri.txt bulundu ama geçerli 20 sayılık çekiliş satırı okunamadı.")
    st.stop()

df["dt"] = pd.to_datetime(df["dt"])
data_hash = sha256_text(text)

# Veri kalite özeti
by_day = df.groupby(df["dt"].dt.date).size()
full217 = int((by_day == 217).sum())
partial = int((by_day != 217).sum())

a,b,c,d = st.columns(4)
a.metric("Çekiliş", f"{len(df):,}".replace(",", "."))
b.metric("Gün", int(df["dt"].dt.date.nunique()))
c.metric("217 tam gün", full217)
d.metric("Eksik/farklı gün", partial)
st.success(f"Veri tanındı — {source}")
st.caption(f"İlk: #{int(df.iloc[0]['draw'])} {df.iloc[0]['dt']:%d.%m.%Y %H:%M} · Son: #{int(df.iloc[-1]['draw'])} {df.iloc[-1]['dt']:%d.%m.%Y %H:%M}")

# Aynı draw no sırasındaki boşluk bilgisi
if len(df) > 1:
    draw_diffs = np.diff(df["draw"].to_numpy(dtype=np.int64))
    missing_steps = int(np.sum(np.maximum(draw_diffs - 1, 0)))
else:
    missing_steps = 0
if missing_steps:
    st.warning(f"Çekiliş numarası sırasındaki toplam boşluk: {missing_steps}. Ritim hesabında gerçek çekiliş numarası farkı kullanılacak.")

near_tol = st.number_input("Yakın ritim toleransı (çekiliş farkı)", min_value=0, max_value=10, value=1, step=1)
run_slice = st.selectbox(
    "Tek basışta çalışma süresi",
    ["Tamamlanana kadar", "5 dakika", "10 dakika", "20 dakika"],
    index=2,
    help="Uzun taramada süre sınırı seçersen checkpoint kaydedilir; aynı düğmeye tekrar basınca devam eder.",
)
limit_map = {"Tamamlanana kadar": 0, "5 dakika": 300, "10 dakika": 600, "20 dakika": 1200}
stop_after = limit_map[run_slice]

# GitHub bağlantısını ve varsa kalıcı checkpoint'i önce kontrol et.
auth_ok, auth_msg = github_auth_status()
if auth_ok:
    st.success(f"🔐 {auth_msg}")
else:
    st.warning(f"⚠️ {auth_msg}")

restored, restore_msg = restore_checkpoint_from_github(data_hash)
if restored:
    st.success(f"♻️ {restore_msg}")
elif "Henüz GitHub" not in restore_msg and "Yerel checkpoint GitHub kaydından geri değil" not in restore_msg:
    st.caption(f"Checkpoint: {restore_msg}")
else:
    st.caption(f"Checkpoint: {restore_msg}")

con = db_connect()
# Farklı veri hashlerinde eski sonuçlar kalabilir ama karışmaz.
for k in SIZES:
    method = "EXHAUSTIVE_80" if k <= EXHAUSTIVE_MAX_K else "PAIR_INTERSECTION"
    ensure_progress(con, data_hash, k, method)

with st.expander("♻️ Eski CSV sonucunu geri yükle", expanded=False):
    st.caption(
        "Eski uygulamadan indirdiğin HIZLI_ON_AILE_RITIM_SONUCLAR.csv veya .csv.gz dosyasını "
        "buradan içe aktarabilirsin. 2'li ve 3'lü sonuçlar tamamlandı olarak geri kurulur."
    )
    backup_upload = st.file_uploader(
        "CSV / CSV.GZ yedeği",
        type=["csv", "gz"],
        key="result_backup_upload",
    )
    if st.button("📥 YEDEĞİ İÇE AKTAR VE GITHUB'A KAYDET", use_container_width=True):
        ok_import, import_msg = import_result_backup(backup_upload, con, data_hash)
        if ok_import:
            ok_remote, remote_msg = save_checkpoint_to_github(con, data_hash, "csv_yedek_aktarimi")
            st.success(import_msg)
            if ok_remote:
                st.success(remote_msg)
            else:
                st.warning(remote_msg)
            st.rerun()
        else:
            st.warning(import_msg)

# Durum tablosu
prog_rows = []
for k in SIZES:
    method, cursor, done, scanned, found = get_progress(con, data_hash, k)
    prog_rows.append({
        "Aile": f"{k}'li",
        "Yöntem": method,
        "Durum": "TAMAM" if done else ("DEVAM" if scanned else "BEKLİYOR"),
        "Taranan": int(scanned),
        "Ritimli": int(found),
    })
st.dataframe(pd.DataFrame(prog_rows), use_container_width=True, hide_index=True)

col1, col2 = st.columns([2,1])
start = col1.button("▶️ ANALİZİ BAŞLAT / KALDIĞI YERDEN DEVAM ET", type="primary", use_container_width=True)
reset = col2.button("🧹 Bu veri için sonucu sıfırla", use_container_width=True)

if reset:
    con.execute("DELETE FROM results WHERE data_hash=?", (data_hash,))
    con.execute("DELETE FROM progress WHERE data_hash=?", (data_hash,))
    con.commit()
    for k in SIZES:
        method = "EXHAUSTIVE_80" if k <= EXHAUSTIVE_MAX_K else "PAIR_INTERSECTION"
        ensure_progress(con, data_hash, k, method)
    ok_remote, remote_msg = save_checkpoint_to_github(con, data_hash, "sifirlama")
    st.success("Bu veri için yerel checkpoint ve sonuçlar sıfırlandı.")
    if ok_remote:
        st.success("GitHub kalıcı checkpoint de sıfırlandı.")
    else:
        st.warning(remote_msg)
    st.rerun()

if start:
    num_bits, lows, highs = build_vertical_bits(df)
    global_started = time.time()
    overall = st.progress(0.0, text="Hazırlanıyor...")
    status = st.empty()
    size_box = st.empty()

    completed_before = sum(int(get_progress(con, data_hash, k)[2]) for k in SIZES)

    for pos, k in enumerate(SIZES):
        method, cursor, done, scanned, found = get_progress(con, data_hash, k)
        if done:
            overall.progress((pos + 1) / len(SIZES), text=f"{k}'li zaten tamam — sonraki boyuta geçiliyor")
            continue

        size_box.markdown(f"### Şimdi {k}'li aileler işleniyor")
        pbox = st.progress(0.0)

        # toplam çalışma süresi seçilmişse kalan süreyi aktar
        remaining = 0
        if stop_after:
            elapsed = time.time() - global_started
            remaining = max(1, int(stop_after - elapsed))
            if remaining <= 1:
                status.info("Süre dilimi tamamlandı. Checkpoint kaydedildi; tekrar DEVAM ET'e bas.")
                break

        if k <= EXHAUSTIVE_MAX_K:
            scanned, found, done_now = scan_exhaustive_k(
                con, data_hash, k, num_bits, df, int(near_tol), pbox, status, remaining
            )
        else:
            scanned, found, done_now = scan_pair_candidates_k(
                con, data_hash, k, num_bits, df, lows, highs, int(near_tol), pbox, status, remaining
            )

        # Boyut değişiminde geçici NumPy/Python nesnelerini mümkün olduğunca bırak.
        gc.collect()
        overall.progress((pos + (1 if done_now else 0)) / len(SIZES), text=f"{k}'li {'tamam' if done_now else 'checkpoint'}")
        if not done_now:
            status.info("Bu çalışma dilimi bitti. Sonuç kaydedildi; aynı düğmeye tekrar basınca kaldığı yerden devam eder.")
            break

    all_done = all(int(get_progress(con, data_hash, k)[2]) == 1 for k in SIZES)
    if all_done:
        overall.progress(1.0, text="2'liden 10'luya bütün taramalar tamamlandı.")
        status.success("Analiz tamamlandı. Tek rapor aşağıda hazır.")
    else:
        status.warning("Tarama henüz tamamlanmadı; checkpoint kaydedildi.")

# Büyük TXT/CSV'yi her Streamlit rerun'ında RAM'e alma. Yalnız kullanıcı isterse diske akıt.
st.divider()
st.subheader("📦 Tek çıktı — düşük RAM")
st.caption("Büyük raporlar otomatik hazırlanmaz. 'Hazırla' dediğinde SQLite'dan satır satır .gz dosyasına yazılır; RAM şişmez.")
export_txt_path, export_csv_path = _export_paths(data_hash)
prepare_exports = st.button("📦 SIKIŞTIRILMIŞ TXT + CSV HAZIRLA", use_container_width=True)
if prepare_exports:
    with st.spinner("Çıktılar diske yazılıyor..."):
        write_report_txt_gz(con, data_hash, df, source, export_txt_path)
        write_results_csv_gz(con, data_hash, export_csv_path)
        gc.collect()
    st.session_state["exports_ready_hash"] = data_hash
    st.success("Çıktılar hazır. Aşağıdaki düğmelerden indirebilirsin.")

if st.session_state.get("exports_ready_hash") == data_hash and export_txt_path.exists() and export_csv_path.exists():
    rc1, rc2 = st.columns(2)
    with export_txt_path.open("rb") as f_txt:
        rc1.download_button(
            "⬇️ TXT.GZ İNDİR",
            data=f_txt,
            file_name="HIZLI_ON_AILE_RITIM_TEK_RAPOR.txt.gz",
            mime="application/gzip",
            use_container_width=True,
        )
    with export_csv_path.open("rb") as f_csv:
        rc2.download_button(
            "⬇️ CSV.GZ İNDİR",
            data=f_csv,
            file_name="HIZLI_ON_AILE_RITIM_SONUCLAR.csv.gz",
            mime="application/gzip",
            use_container_width=True,
        )

# Ekranı şişirmeden yalnız örnek sonuç göster.
st.subheader("Sonuç önizleme")
preview = pd.read_sql_query(
    """SELECT size AS Boyut, family AS Aile, support AS Aktivasyon,
              rhythm_types AS Ritim, rhythm_detail AS Detay, time_character AS Zaman
       FROM results WHERE data_hash=? ORDER BY size, support DESC, family LIMIT 200""",
    con,
    params=(data_hash,),
)
if preview.empty:
    st.info("Henüz ritimli aile kaydı yok. Analizi başlat.")
else:
    st.dataframe(preview, use_container_width=True, hide_index=True, height=520)
    st.caption("Ekranda ilk 200 kayıt gösterilir; tam sonuç tek TXT/CSV dosyasındadır.")

st.caption(
    "Teknik not: 2–6 boyutlarında 1–80 aile evreni prefix-checkpoint ile düşük RAM taranır. "
    "7–10 boyutlarında gerçek çekiliş çiftlerinin ortak kümelerinden aday çıkarılır. "
    "Kalıcı checkpoint tek büyük dosya yerine 8 MB SQLite parçaları halinde app-state dalına yazılır. "
    "Büyük TXT/CSV yalnız istek üzerine diske akıtılır; her ekran yenilemede RAM'e yüklenmez."
)
