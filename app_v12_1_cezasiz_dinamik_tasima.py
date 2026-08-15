
from pathlib import Path
from collections import Counter
from datetime import datetime
import base64, json, math, re, urllib.parse, urllib.request

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Hızlı On V12.1 Cezasız Dinamik Taşıma / Dönüş Uzmanları",
    page_icon="🌙",
    layout="wide",
)

st.title("🌙 Hızlı On V12.1 — Cezasız Dinamik Taşıma / Dönüş Uzmanları")
st.caption(
    "23:02 + 23:07 + 23:12 ilk üç çekiliş geceyi tanır. "
    "Sonra 23:17 → 23:22 → 23:27 → ... → 23:57 için sırayla 2 adet 7'li + 1 adet 10'lu kupon üretir. "
    "Her gerçek sonuç kaydedildikçe hedef otomatik bir sonraki çekilişe ilerler."
)

DATA_FILE = Path("veri.txt")
SLOTS = [
    "23:02","23:07","23:12","23:17","23:22","23:27",
    "23:32","23:37","23:42","23:47","23:52","23:57"
]
FIRST3 = ["23:02","23:07","23:12"]
TARGET_SLOTS = SLOTS[3:]
BASE = 20/80

DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"


# ============================================================
# GITHUB / KALICI VERİ
# ============================================================
def github_config():
    token = ""
    repo = DEFAULT_REPO
    branch = DEFAULT_BRANCH
    path = DEFAULT_PATH
    try:
        token = str(st.secrets.get("GITHUB_TOKEN","")).strip()
        repo = str(st.secrets.get("GITHUB_REPO",repo)).strip() or repo
        branch = str(st.secrets.get("GITHUB_BRANCH",branch)).strip() or branch
        path = str(st.secrets.get("GITHUB_DATA_PATH",path)).strip() or path
    except Exception:
        pass
    return token, repo, branch, path


def github_read(token, repo, branch, path):
    url = (
        f"https://api.github.com/repos/{repo}/contents/"
        f"{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hizli-on-v10",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        obj = json.loads(r.read().decode("utf-8"))
    return base64.b64decode(obj["content"]).decode("utf-8"), obj["sha"]


def github_write(token, repo, branch, path, text, message):
    _, sha = github_read(token, repo, branch, path)
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    body = json.dumps({
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": branch,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "Content-Type":"application/json",
            "User-Agent":"hizli-on-v10",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


# ============================================================
# PARSE / DOSYA
# ============================================================
def repair_draw_no(no, date_s):
    """Eski yanlış kayıtlarda çekiliş no sonuna gün (örn 4860112) yapıştıysa düzelt."""
    s = str(int(no))
    day = date_s.split(".")[0].zfill(2)
    if len(s) >= 7 and s.endswith(day):
        cand = s[:-2]
        if 4 <= len(cand) <= 6:
            return int(cand)
    return int(no)


def parse_pipe(text):
    rows = []
    for raw in str(text).splitlines():
        p = [x.strip() for x in raw.split("|")]
        if len(p) < 3:
            continue
        try:
            no = int(p[0])
            d, t = p[1].split()
            no = repair_draw_no(no, d)
            nums = sorted(set(int(x) for x in re.findall(r"\d+", p[2])))
        except Exception:
            continue
        if t not in SLOTS or len(nums) != 20 or any(n < 1 or n > 80 for n in nums):
            continue
        rows.append({"draw_no":no,"date":d,"time":t,"numbers":nums})

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["_dt"] = pd.to_datetime(
        df["date"]+" "+df["time"],
        format="%d.%m.%Y %H:%M",
        errors="coerce"
    )
    df = df.dropna(subset=["_dt"])
    return (
        df.sort_values(["_dt","draw_no"])
        .drop_duplicates(["date","time"],keep="last")
        .reset_index(drop=True)
    )


def parse_result_block(raw):
    raw = str(raw or "").strip()
    raw = raw.replace("\u00a0"," ").replace("–","-").replace("—","-").replace("−","-")

    m_no = re.search(
        r"(?:çekiliş|cekilis)\s*(?:no|numarası|numarasi)?\s*[:#-]?\s*(\d{4,7})",
        raw, re.I
    )
    m_dt = re.search(
        r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}:\d{2})",
        raw
    )
    if not m_no:
        raise ValueError("Çekiliş no bulunamadı.")
    if not m_dt:
        raise ValueError("Tarih/saat bulunamadı.")

    date_s = datetime.strptime(m_dt.group(1), "%d.%m.%Y").strftime("%d.%m.%Y")
    time_s = m_dt.group(2)
    if time_s not in SLOTS:
        raise ValueError("Geçersiz gece çekiliş saati.")

    draw_no = repair_draw_no(int(m_no.group(1)), date_s)

    tail = raw[m_dt.end():]
    nums = [
        int(x) for x in re.findall(
            r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", tail
        )
    ]
    if len(nums) != 20 or len(set(nums)) != 20:
        raise ValueError(f"20 farklı sayı bekleniyor; {len(nums)} bulundu.")

    return {
        "draw_no":draw_no,
        "date":date_s,
        "time":time_s,
        "numbers":sorted(nums),
    }


def line_for(r):
    return f"{r['draw_no']} | {r['date']} {r['time']} | {' '.join(map(str,r['numbers']))}"


def append_or_replace(text, r):
    key = f"{r['date']} {r['time']}"
    newline = line_for(r)
    out, done = [], False

    for raw in str(text).splitlines():
        if not raw.strip():
            continue
        p = [x.strip() for x in raw.split("|")]
        if len(p) >= 2 and p[1] == key:
            if not done:
                out.append(newline)
                done = True
            continue
        out.append(raw.rstrip())

    if not done:
        out.append(newline)

    return "\n".join(out).rstrip()+"\n"


def persist_result(r):
    token, repo, branch, path = github_config()
    if token:
        current, _ = github_read(token, repo, branch, path)
        updated = append_or_replace(current, r)
        if updated != current:
            github_write(
                token, repo, branch, path, updated,
                f"V10 add {r['draw_no']} {r['date']} {r['time']}"
            )
        return updated, True

    current = DATA_FILE.read_text(encoding="utf-8") if DATA_FILE.exists() else ""
    updated = append_or_replace(current, r)
    DATA_FILE.write_text(updated, encoding="utf-8")
    return updated, False


def load_df():
    token, repo, branch, path = github_config()
    if token:
        try:
            txt, _ = github_read(token, repo, branch, path)
            return parse_pipe(txt), "GitHub veri.txt"
        except Exception:
            pass
    if DATA_FILE.exists():
        return parse_pipe(DATA_FILE.read_text(encoding="utf-8")), "Repo veri.txt"
    return pd.DataFrame(), "Veri yok"


# ============================================================
# GECE / HEDEF SEÇİMİ
# ============================================================
def day_map(df):
    out = {}
    for _, r in df.iterrows():
        out.setdefault(str(r["date"]), {})[str(r["time"])] = set(r["numbers"])
    return out


def ordered_dates(df):
    return list(dict.fromkeys(df["date"].astype(str).tolist()))


def next_live_target(df):
    """
    İlk üç çekiliş geceyi tanır.
    Sonra mevcut gecede ilk eksik hedef saatini döndürür:
    23:17 -> 23:22 -> ... -> 23:57.
    """
    dm = day_map(df)
    dates = ordered_dates(df)
    if not dates:
        return None, None, "Veri yok."

    d = dates[-1]
    day = dm.get(d, {})

    # İlk üç tamamlanmadan kupon yok.
    missing_first = [s for s in FIRST3 if s not in day]
    if missing_first:
        return d, None, "Geceyi tanımak için eksik: " + ", ".join(missing_first)

    # İlk eksik hedefi bul.
    for target in TARGET_SLOTS:
        if target not in day:
            # hedefe kadar tüm önceki gece saatleri mevcut olmalı
            ti = SLOTS.index(target)
            prev_required = SLOTS[:ti]
            missing_prev = [s for s in prev_required if s not in day]
            if missing_prev:
                return d, None, "Akışta eksik çekiliş var: " + ", ".join(missing_prev)
            return d, target, None

    return d, None, "Bu gecenin 23:57 dahil tüm hedefleri tamamlandı. Yeni geceyi bekle."


# ============================================================
# OYUN KARAKTERİ
# ============================================================
def consecutive_blocks(s):
    arr = sorted(s)
    blocks, cur = [], []
    for n in arr:
        if not cur or n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2:
                blocks.append(cur)
            cur = [n]
    if len(cur) >= 2:
        blocks.append(cur)
    return blocks


def first3_character(a, b, c):
    c1 = len(a & b)
    c2 = len(b & c)
    c3 = len(a & c)
    tri = len(a & b & c)
    block_pressure = sum(len(consecutive_blocks(x)) for x in [a,b,c])

    if c1 >= 6 and c2 >= 6:
        regime = "TAŞIMA-AĞIR"
    elif c1 <= 3 and c2 <= 3:
        regime = "DÖNÜŞ-AĞIR"
    else:
        regime = "KARMA"

    return {
        "regime":regime,
        "carry_02_07":c1,
        "carry_07_12":c2,
        "cross_02_12":c3,
        "triple_core":tri,
        "block_pressure":block_pressure,
    }


def path_bits(draws, n, maxlen=6):
    bits = ["1" if n in s else "0" for s in draws[-maxlen:]]
    return "".join(bits).rjust(maxlen, "0")


def current_gap(draws, n, maxgap=8):
    g = 0
    for s in reversed(draws[-maxgap:]):
        if n in s:
            return g
        g += 1
    return min(g, maxgap)


def hot_count(draws, n):
    return sum(n in s for s in draws)


def hot_trend(draws, n):
    bits = [1 if n in s else 0 for s in draws]
    if len(bits) < 2:
        return "NÖTR"
    last3 = sum(bits[-3:])
    prev3 = sum(bits[-6:-3]) if len(bits) >= 6 else sum(bits[:-3])
    delta = last3 - prev3

    if bits[-1] and last3 >= 2 and delta > 0:
        return "SICAĞA YÜKSELİYOR"
    if bits[-1] and last3 >= 2:
        return "SICAK / DEVAM"
    if not bits[-1] and 1 <= current_gap(draws,n) <= 2:
        return "DİNLENİP DÖNÜŞ PENCERESİ"
    if not bits[-1] and current_gap(draws,n) >= 3:
        return "UZUN UYKU"
    if bits[-1] and last3 == 1:
        return "YENİ DOĞDU"
    return "NÖTR"


def context_distance(gc1, gc2):
    d = (
        abs(gc1["carry_02_07"] - gc2["carry_02_07"]) / 10.0
        + abs(gc1["carry_07_12"] - gc2["carry_07_12"]) / 10.0
        + abs(gc1["cross_02_12"] - gc2["cross_02_12"]) / 10.0
        + abs(gc1["triple_core"] - gc2["triple_core"]) / 8.0
        + abs(gc1["block_pressure"] - gc2["block_pressure"]) / 12.0
    )
    if gc1["regime"] != gc2["regime"]:
        d += 0.30
    return d


def shrink(h, n, prior=BASE, strength=16):
    return (h + prior*strength) / (n + strength)


# ============================================================
# HEDEF NOTA OLAY BANKASI
# ============================================================
def historical_target_events(df, target_slot):
    """
    Her geçmiş gecede hedef target_slot'tan ÖNCE bilinen çekilişleri kullanır.
    Hedef sonucu yalnız etiket olarak tutulur; özelliklere sızmaz.
    """
    dm = day_map(df)
    dates = ordered_dates(df)
    target_idx = SLOTS.index(target_slot)
    prior_slots = SLOTS[:target_idx]
    events = []

    for d in dates:
        day = dm.get(d,{})
        if not all(s in day for s in FIRST3 + [target_slot]):
            continue
        if not all(s in day for s in prior_slots):
            continue

        a,b,c = [day[s] for s in FIRST3]
        gc = first3_character(a,b,c)
        prior_draws = [day[s] for s in prior_slots]
        y = day[target_slot]

        events.append({
            "date":d,
            "gc":gc,
            "prior_draws":prior_draws,
            "target":y,
        })
    return events


# ============================================================
# ADAY SKORU
# ============================================================
def score_for_target(df, target_slot):
    dm = day_map(df)
    dates = ordered_dates(df)
    d = dates[-1]
    day = dm[d]

    # Canlı hedef sonucu veri.txt'de olmamalı.
    if target_slot in day:
        raise ValueError(f"{d} {target_slot} sonucu zaten kayıtlı.")

    target_idx = SLOTS.index(target_slot)
    prior_slots = SLOTS[:target_idx]
    if not all(s in day for s in prior_slots):
        missing = [s for s in prior_slots if s not in day]
        raise ValueError("Hedef öncesi eksik çekilişler: " + ", ".join(missing))

    a,b,c = [day[s] for s in FIRST3]
    gc_now = first3_character(a,b,c)
    draws_now = [day[s] for s in prior_slots]
    src = draws_now[-1]

    events = historical_target_events(df, target_slot)
    events = [e for e in events if e["date"] != d]
    if len(events) < 16:
        raise ValueError(f"{target_slot} için en az 16 geçmiş tam gece gerekli.")

    # Benzer oyun karakteri ağırlığı
    weighted_events = []
    for e in events:
        dist = context_distance(gc_now, e["gc"])
        w = 1.0 / (0.06 + dist)
        weighted_events.append((w,e))
    weighted_events.sort(key=lambda z:z[0], reverse=True)
    near = weighted_events[:min(24, len(weighted_events))]

    rows = []
    for n in range(1,81):
        pnow = path_bits(draws_now,n,6)
        gnow = current_gap(draws_now,n,8)
        hnow = hot_count(draws_now,n)
        trend = hot_trend(draws_now,n)
        in_src = n in src
        neigh = int((n-1) in src) + int((n+1) in src)

        # 1) Aynı 6x6 yol ritmi
        h1=n1=0.0
        # 2) Aynı taşıma/dönüş tarafı
        h2=n2=0.0
        # 3) Aynı dinlenme gap cebi
        h3=n3=0.0
        # 4) Aynı gece-içi sıcaklık seviyesi
        h4=n4=0.0
        # 5) Aynı trend yönü
        h5=n5=0.0
        # 6) sayı kimliği (çok zayıf)
        h6=n6=0.0

        for w,e in near:
            edraws = e["prior_draws"]
            esrc = edraws[-1]
            hit = int(n in e["target"])

            ep = path_bits(edraws,n,6)
            eg = current_gap(edraws,n,8)
            eh = hot_count(edraws,n)
            etrend = hot_trend(edraws,n)

            # tam yol ve son-4 yol yakınlığı
            if ep == pnow:
                h1 += w*hit; n1 += w
            elif ep[-4:] == pnow[-4:]:
                h1 += 0.55*w*hit; n1 += 0.55*w

            if (n in esrc) == in_src:
                h2 += w*hit; n2 += w

            # gap cepleri: 0 / 1-2 / 3-4 / 5+
            def gb(g):
                if g==0: return "0"
                if g<=2: return "1-2"
                if g<=4: return "3-4"
                return "5+"
            if gb(eg) == gb(gnow):
                h3 += w*hit; n3 += w

            # sıcaklık seviyeleri
            def hb(x):
                if x<=1: return "0-1"
                if x<=3: return "2-3"
                return "4+"
            if hb(eh) == hb(hnow):
                h4 += w*hit; n4 += w

            if etrend == trend:
                h5 += w*hit; n5 += w

            h6 += w*hit; n6 += w

        r1 = shrink(h1,n1,BASE,10)
        r2 = shrink(h2,n2,BASE,18)
        r3 = shrink(h3,n3,BASE,14)
        r4 = shrink(h4,n4,BASE,12)
        r5 = shrink(h5,n5,BASE,12)
        r6 = shrink(h6,n6,BASE,36)

        # Skor yerine kanıt: geçmiş gerçek isabet + destek öncelikli
        support = n1 + 0.65*n3 + 0.55*n4 + 0.50*n5
        reliability = math.sqrt(support/(support+20.0)) if support > 0 else 0.0

        raw = (
            0.36*r1 +    # 6x6 yol ritmi
            0.18*r2 +    # taşıma/dönüş tarafı
            0.18*r3 +    # dinlenme/gap
            0.14*r4 +    # gece içi sıcaklaşma
            0.10*r5 +    # trend yönü
            0.04*r6      # kimlik çok zayıf
        )

        # Ardışık sadece destek; asla ana karar değil
        raw += 0.004*neigh

        evidence = BASE + (raw-BASE)*reliability

        # Sahte sıcak frenleri
        if trend == "SICAK / DEVAM" and r1 < 0.265:
            evidence -= 0.012
        if trend == "UZUN UYKU" and r3 < 0.255:
            evidence -= 0.010
        if trend == "DİNLENİP DÖNÜŞ PENCERESİ" and r3 > 0.27 and r1 > 0.26:
            evidence += 0.010
        if trend == "SICAĞA YÜKSELİYOR" and r4 > 0.27 and r1 > 0.26:
            evidence += 0.010

        rows.append({
            "Sayı":n,
            "Kaynakta":in_src,
            "6x6 Yol":pnow,
            "Trend":trend,
            "Gece Görünüm":hnow,
            "Gap":gnow,
            "Komşu":neigh,
            "Yol Kanıt":r1,
            "Taşıma/Dönüş":r2,
            "Dinlenme Kanıt":r3,
            "Sıcaklık Kanıt":r4,
            "Trend Kanıt":r5,
            "Kimlik":r6,
            "Destek":support,
            "Kanıt":evidence,
        })

    tab = pd.DataFrame(rows)

    # Taşıma ve dönüş ayrı lig
    tab["Taşıma Sıra"] = 999
    tab["Dönüş Sıra"] = 999
    ci = tab.index[tab["Kaynakta"]]
    ri = tab.index[~tab["Kaynakta"]]
    tab.loc[ci,"Taşıma Sıra"] = tab.loc[ci,"Kanıt"].rank(
        ascending=False, method="first"
    ).astype(int)
    tab.loc[ri,"Dönüş Sıra"] = tab.loc[ri,"Kanıt"].rank(
        ascending=False, method="first"
    ).astype(int)

    return tab.sort_values(["Kanıt","Destek"],ascending=False).reset_index(drop=True), gc_now


# ============================================================
# KUPON ÜRETİMİ
# ============================================================
def _estimate_dynamic_carry_ratio(df, target_slot, gc_now):
    """
    Sabit kota/ceza yok.
    Benzer geçmiş gecelerde, hedef notada önceki çekilişten hedefe gerçek taşıma oranını öğrenir.
    Sonuç: 0.0-1.0 arası beklenen taşıma oranı.
    """
    dm = day_map(df)
    dates = ordered_dates(df)
    ti = SLOTS.index(target_slot)
    src_slot = SLOTS[ti-1]

    samples = []
    for d in dates:
        day = dm.get(d,{})
        if not all(s in day for s in FIRST3+[src_slot,target_slot]):
            continue

        a,b,c = [day[s] for s in FIRST3]
        gc_hist = first3_character(a,b,c)
        dist = context_distance(gc_now, gc_hist)
        w = 1.0/(0.08+dist)

        src = day[src_slot]
        tgt = day[target_slot]
        carry = len(src & tgt) / 20.0
        samples.append((w,carry))

    if not samples:
        return 0.25

    samples.sort(key=lambda z:z[0], reverse=True)
    near = samples[:min(24,len(samples))]
    num = sum(w*c for w,c in near)
    den = sum(w for w,_ in near)
    return float(np.clip(num/den if den else 0.25, 0.05, 0.75))


def _dynamic_side_target(size, carry_ratio):
    """
    Kupon boyutuna göre beklenen taşıma koltuğu.
    Zorunlu kota değil, yalnız yönlendirici hedef.
    Örn %50 taşıma -> 10'luda ~5 taşıma, 7'lide ~3-4 taşıma.
    """
    return int(np.clip(round(size*carry_ratio), 0, size))


def _stable_rank_frame(tab, gc):
    """
    V12 istikrar katmanı:
    - yüksek ham Kanıt tek başına yeterli değil
    - taşıma ve dönüş ayrı değerlendirilir
    - çoklu kanal desteği, destek miktarı ve sinyal tutarlılığı öne çıkar
    - tek kanalda parlayan adaylar cezalandırılır
    """
    x = tab.copy()

    cols = [
        "Yol Kanıt","Taşıma/Dönüş","Dinlenme Kanıt",
        "Sıcaklık Kanıt","Trend Kanıt","Destek","Kanıt"
    ]
    for c in cols:
        x[c] = pd.to_numeric(x[c], errors="coerce").fillna(0.0)

    # Yüzdelik sıralamalar: tek ölçeğe indirger.
    for c in ["Yol Kanıt","Taşıma/Dönüş","Dinlenme Kanıt",
              "Sıcaklık Kanıt","Trend Kanıt","Destek","Kanıt"]:
        x[c+"_P"] = x[c].rank(pct=True, method="average")

    x["CarryP"] = x["Kaynakta"].astype(float)
    x["ReturnP"] = 1.0 - x["CarryP"]

    # Çoklu kanalda üst bölgede olma sayısı.
    proof_cols = ["Yol Kanıt_P","Taşıma/Dönüş_P","Dinlenme Kanıt_P",
                  "Sıcaklık Kanıt_P","Trend Kanıt_P","Destek_P"]
    x["Kanal65"] = (x[proof_cols] >= 0.65).sum(axis=1)
    x["Kanal75"] = (x[proof_cols] >= 0.75).sum(axis=1)
    x["Kanal85"] = (x[proof_cols] >= 0.85).sum(axis=1)

    # Kanal tutarlılığı: kanallar birbirinden çok kopuksa ceza.
    x["KanalStd"] = x[proof_cols].std(axis=1).fillna(0.0)
    x["Tutarlılık"] = (1.0 - x["KanalStd"].clip(0,1)).clip(0,1)

    # Yaşam yönleri
    x["Rise"] = x["Trend"].isin(
        ["SICAĞA YÜKSELİYOR","DİNLENİP DÖNÜŞ PENCERESİ","YENİ DOĞDU"]
    ).astype(float)
    x["LongHot"] = x["Trend"].isin(["SICAK / DEVAM"]).astype(float)
    x["LongSleep"] = x["Trend"].isin(["UZUN UYKU"]).astype(float)

    # Rejim uyumu
    x["RejimUyum"] = 0.0
    if gc["regime"] == "TAŞIMA-AĞIR":
        x["RejimUyum"] = 0.7*x["CarryP"] + 0.3*x["ReturnP"]
    elif gc["regime"] == "DÖNÜŞ-AĞIR":
        x["RejimUyum"] = 0.7*x["ReturnP"] + 0.3*x["CarryP"]
    else:
        x["RejimUyum"] = 0.5

    # Ortak istikrar skoru.
    x["Stabil"] = (
        0.20*x["Yol Kanıt_P"] +
        0.16*x["Taşıma/Dönüş_P"] +
        0.18*x["Dinlenme Kanıt_P"] +
        0.13*x["Sıcaklık Kanıt_P"] +
        0.10*x["Trend Kanıt_P"] +
        0.13*x["Destek_P"] +
        0.10*x["Tutarlılık"]
    )

    # Çoklu kanıt bonusu
    x["Stabil"] += 0.018*x["Kanal65"] + 0.022*x["Kanal75"] + 0.028*x["Kanal85"]

    # Tek kanalda parlayan aday frenleri
    x.loc[x["Kanal65"] <= 1, "Stabil"] -= 0.11
    x.loc[x["Kanal75"] == 0, "Stabil"] -= 0.05
    x.loc[x["Tutarlılık"] < 0.72, "Stabil"] -= 0.05

    # Uzun sıcaklık / uzun uyku kör puan olmasın
    weak_path = x["Yol Kanıt_P"] < 0.58
    x.loc[(x["LongHot"]==1) & weak_path, "Stabil"] -= 0.04
    x.loc[(x["LongSleep"]==1) & (x["Dinlenme Kanıt_P"]<0.60), "Stabil"] -= 0.05

    # Rejim sadece yardımcı
    x["Stabil"] += 0.035*x["RejimUyum"]

    return x


def _pick_balanced(ranked, size, max_side_ratio=0.72, forbidden=None):
    forbidden = set(forbidden or [])
    chosen = []
    carry_n = return_n = 0
    max_side = max(4, int(round(size*max_side_ratio)))

    for _, row in ranked.iterrows():
        n = int(row["Sayı"])
        if n in forbidden:
            continue
        is_carry = bool(row["Kaynakta"])

        if is_carry and carry_n >= max_side:
            continue
        if (not is_carry) and return_n >= max_side:
            continue

        chosen.append(n)
        carry_n += int(is_carry)
        return_n += int(not is_carry)

        if len(chosen) == size:
            break

    if len(chosen) < size:
        for n in ranked["Sayı"].astype(int):
            if n not in chosen and n not in forbidden:
                chosen.append(n)
            if len(chosen) == size:
                break

    return chosen


def make_tickets(tab, gc, target_slot, df=None):
    """
    V12.1:
    - 2 bağımsız 7'li + 1 adet 10'lu
    - kuponlar birbirine benzemesin diye CEZA YOK
    - aynı sayı iki uzman tarafından da güçlü bulunuyorsa ikisinde de kalabilir
    - taşıma oranı sabit değil; benzer geçmiş gecelerden dinamik öğrenilir
    """
    x = _stable_rank_frame(tab, gc)

    carry_ratio = 0.25
    if df is not None:
        try:
            carry_ratio = _estimate_dynamic_carry_ratio(df, target_slot, gc)
        except Exception:
            carry_ratio = 0.25

    # 7A — TAŞIMA / DEVAM UZMANI
    a = x.copy()
    a["UzmanA"] = (
        0.28*a["Stabil"] +
        0.24*a["Yol Kanıt_P"] +
        0.20*a["Taşıma/Dönüş_P"] +
        0.12*a["Destek_P"] +
        0.08*a["Tutarlılık"] +
        0.08*a["CarryP"]
    )
    a.loc[(a["Kaynakta"]) & (a["Kanal65"]>=3), "UzmanA"] += 0.05
    a.loc[(a["Kaynakta"]) & (a["Kanal65"]<=1), "UzmanA"] -= 0.04

    # 7B — DİNLENİP DÖNÜŞ / RİTİM UZMANI
    b = x.copy()
    b["UzmanB"] = (
        0.28*b["Stabil"] +
        0.24*b["Dinlenme Kanıt_P"] +
        0.18*b["Yol Kanıt_P"] +
        0.12*b["Trend Kanıt_P"] +
        0.10*b["Sıcaklık Kanıt_P"] +
        0.08*b["ReturnP"]
    )
    b.loc[(~b["Kaynakta"]) & (b["Kanal65"]>=3), "UzmanB"] += 0.05
    b.loc[(~b["Kaynakta"]) & (b["Dinlenme Kanıt_P"]<0.55), "UzmanB"] -= 0.04

    # Rejim, taşıma beklentisini yönlendirir ama kilitlemez.
    if gc["regime"] == "TAŞIMA-AĞIR":
        a["UzmanA"] += 0.04*a["CarryP"]
    elif gc["regime"] == "DÖNÜŞ-AĞIR":
        b["UzmanB"] += 0.04*b["ReturnP"]

    a = a.sort_values(["UzmanA","Kanal75","Destek"],ascending=False)
    b = b.sort_values(["UzmanB","Kanal75","Destek"],ascending=False)

    def pick_free(ranked, size, target_carry):
        chosen=[]
        # Önce skor sırasından serbest seç; taşıma hedefi yalnız zayıf bir denge işareti.
        # Güçlü adaylar sırf oranı bozuyor diye atılmaz.
        for _,row in ranked.iterrows():
            chosen.append(int(row["Sayı"]))
            if len(chosen)==size:
                break

        # Eğer çok uç bir tek-taraf yığılması varsa ve sınırdaki adaylar yakınsa küçük dengeleme.
        if not chosen:
            return chosen

        chosen_df = ranked[ranked["Sayı"].isin(chosen)].copy()
        carry_now = int(chosen_df["Kaynakta"].sum())
        diff = carry_now - target_carry

        if abs(diff) >= 3:
            selected_scores = {
                int(r["Sayı"]): float(r[ranked.columns.intersection(["UzmanA","UzmanB"]).tolist()[0]])
                for _,r in chosen_df.iterrows()
            } if any(c in chosen_df.columns for c in ["UzmanA","UzmanB"]) else {}

            # Yalnız bariz uç durumda ve skor farkı küçükse değiştir.
            if diff > 0:
                outsiders = ranked[(~ranked["Kaynakta"]) & (~ranked["Sayı"].isin(chosen))]
                insiders = ranked[(ranked["Kaynakta"]) & (ranked["Sayı"].isin(chosen))].iloc[::-1]
            else:
                outsiders = ranked[(ranked["Kaynakta"]) & (~ranked["Sayı"].isin(chosen))]
                insiders = ranked[(~ranked["Kaynakta"]) & (ranked["Sayı"].isin(chosen))].iloc[::-1]

            if len(outsiders) and len(insiders):
                in_n = int(insiders.iloc[0]["Sayı"])
                out_n = int(outsiders.iloc[0]["Sayı"])
                score_col = "UzmanA" if "UzmanA" in ranked.columns else "UzmanB"
                in_score = float(insiders.iloc[0][score_col])
                out_score = float(outsiders.iloc[0][score_col])
                if in_score - out_score <= 0.035:
                    chosen[chosen.index(in_n)] = out_n

        return chosen

    carry7 = _dynamic_side_target(7, carry_ratio)
    carry10 = _dynamic_side_target(10, carry_ratio)

    t7a = pick_free(a,7,carry7)
    t7b = pick_free(b,7,carry7)

    # 10'lu konsensüs: A+B ortak güç; tekrar cezası yok.
    z = x.merge(a[["Sayı","UzmanA"]],on="Sayı",how="left").merge(
        b[["Sayı","UzmanB"]],on="Sayı",how="left"
    )
    z["A_P"] = z["UzmanA"].rank(pct=True)
    z["B_P"] = z["UzmanB"].rank(pct=True)
    z["OrtakGuç"] = np.minimum(z["A_P"],z["B_P"])

    z["Final10"] = (
        0.24*z["Stabil"] +
        0.22*z["A_P"] +
        0.22*z["B_P"] +
        0.14*z["OrtakGuç"] +
        0.08*z["Yol Kanıt_P"] +
        0.05*z["Dinlenme Kanıt_P"] +
        0.05*z["Destek_P"]
    )
    z.loc[z["Kanal65"]>=4,"Final10"] += 0.045
    z = z.sort_values(["Final10","Kanal75","Destek"],ascending=False)
    t10 = pick_free(z,10,carry10)

    return {
        "7A": t7a,
        "7B": t7b,
        "10": t10,
        "_carry_ratio": carry_ratio,
        "_carry7": carry7,
        "_carry10": carry10,
    }

def evaluate_tickets(tickets, actual):
    actual = set(actual)
    rows = []
    order = [("7A","7'li A"),("7B","7'li B"),("10","10'lu")]
    for key, label in order:
        t = tickets.get(key, [])
        hits = sorted(set(t) & actual)
        rows.append({
            "Kupon": label,
            "İsabet": f"{len(hits)}/{len(t)}",
            "Tutanlar": " ".join(f"{n:02d}" for n in hits),
            "Kupon Sayıları": " ".join(f"{n:02d}" for n in t),
        })
    return pd.DataFrame(rows)

# ============================================================
# UI
# ============================================================
df, source = load_df()
if df.empty:
    st.error("veri.txt bulunamadı.")
    st.stop()

st.caption(
    f"📂 {source} · {len(df)} çekiliş · {df['date'].nunique()} gece · "
    f"son: #{df.iloc[-1]['draw_no']} {df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

token,_,_,_ = github_config()
if token:
    st.caption("🔒 Kalıcı GitHub veri.txt kayıt: AÇIK")
else:
    st.warning("⚠️ GITHUB_TOKEN yok; GitHub kalıcı kayıt kapalı.")

# Önceki kayıt mesajı
if st.session_state.get("v10_msg"):
    st.success(st.session_state.pop("v10_msg"))

with st.expander("⚡ HIZLI SONUÇ EKLE", expanded=False):
    quick = st.text_area(
        "Çekiliş sonucunu aynen yapıştır",
        height=240,
        key="quick_result",
        placeholder="Çekiliş no: 48601\n12.08.2026 - 23:22\n..."
    )
    if st.button("💾 KAYDET + HEDEFİ İLERLET", use_container_width=True):
        try:
            r = parse_result_block(quick)

            # Kayıttan önce, bu sonuç mevcut canlı hedefse kupon karnesini çıkar.
            pred = st.session_state.get("v10_prediction")
            if pred and r["date"] == pred["date"] and r["time"] == pred["target"]:
                st.session_state["v10_eval"] = evaluate_tickets(
                    pred["tickets"], r["numbers"]
                )
                st.session_state["v10_eval_title"] = (
                    f"#{r['draw_no']} {r['date']} {r['time']}"
                )

            persist_result(r)
            st.session_state["v10_msg"] = (
                f"✅ #{r['draw_no']} {r['date']} {r['time']} kaydedildi. "
                "Hedef bir sonraki çekilişe ilerletildi."
            )
            st.rerun()
        except Exception as e:
            st.error(str(e))

target_date, target_slot, target_error = next_live_target(df)

tabs = st.tabs(["🏆 CANLI KUPONLAR","🧬 GECE KARAKTERİ","🔬 ADAY AYRIŞIMI"])

with tabs[0]:
    if target_slot is None:
        st.warning(target_error)
        st.session_state.pop("v10_prediction", None)
    else:
        try:
            tab, gc = score_for_target(df, target_slot)
            tickets = make_tickets(tab, gc, target_slot, df=df)

            st.session_state["v10_prediction"] = {
                "date":target_date,
                "target":target_slot,
                "tickets":tickets,
            }

            st.success(f"🎯 CANLI HEDEF: {target_date} {target_slot}")

            a,b,c,d = st.columns(4)
            a.metric("Gece karakteri", gc["regime"])
            b.metric("02→07 taşıma", gc["carry_02_07"])
            c.metric("07→12 taşıma", gc["carry_07_12"])
            d.metric("Beklenen taşıma", f"%{100*tickets.get('_carry_ratio',0.25):.1f}")

            st.caption(
                f"Dinamik taşıma yönü: 7'lide yaklaşık {tickets.get('_carry7','-')} taşıma · "
                f"10'luda yaklaşık {tickets.get('_carry10','-')} taşıma. "
                "Bu bir zorunlu kota değildir; güçlü aday sırf oranı bozuyor diye atılmaz."
            )

            st.info(
                "İlk üç çekiliş gece karakterini sabitler. "
                "Her yeni sonuç geldikçe aynı gece içinde sıcaklık, taşıma, dinlenme ve 6x6 yol ritmi yeniden hesaplanır."
            )

            st.markdown(f"### 🎯 {target_slot} — 7'Lİ A · TAŞIMA / İSTİKRAR")
            st.code("  ".join(f"{n:02d}" for n in tickets["7A"]))

            st.markdown(f"### 🎯 {target_slot} — 7'Lİ B · DİNLENİP DÖNÜŞ / RİTİM")
            st.code("  ".join(f"{n:02d}" for n in tickets["7B"]))

            st.markdown(f"### 🏆 {target_slot} — 10'LU KONSENSÜS")
            st.code("  ".join(f"{n:02d}" for n in tickets["10"]))

        except Exception as e:
            st.warning(str(e))
            st.session_state.pop("v10_prediction", None)

with tabs[1]:
    if target_slot is None:
        st.warning(target_error)
    else:
        dm = day_map(df)
        day = dm[target_date]
        a,b,c = [day[s] for s in FIRST3]
        gc = first3_character(a,b,c)

        st.subheader("🧬 İlk 3 çekilişten gece karakteri")
        st.write({
            "Hedef": target_slot,
            "Rejim": gc["regime"],
            "23:02→23:07 taşıma": gc["carry_02_07"],
            "23:07→23:12 taşıma": gc["carry_07_12"],
            "23:02↔23:12 çapraz": gc["cross_02_12"],
            "3 çekilişte ortak çekirdek": gc["triple_core"],
            "Ardışık blok baskısı": gc["block_pressure"],
        })

with tabs[2]:
    if target_slot is None:
        st.warning(target_error)
    else:
        try:
            tab, gc = score_for_target(df, target_slot)
            show = tab.copy()
            for col in [
                "Yol Kanıt","Taşıma/Dönüş","Dinlenme Kanıt",
                "Sıcaklık Kanıt","Trend Kanıt","Kimlik","Destek","Kanıt"
            ]:
                show[col] = show[col].map(lambda x: round(float(x),3))

            st.dataframe(
                show[[
                    "Sayı","Kaynakta","6x6 Yol","Trend","Gece Görünüm",
                    "Gap","Komşu","Yol Kanıt","Taşıma/Dönüş",
                    "Dinlenme Kanıt","Sıcaklık Kanıt","Trend Kanıt",
                    "Destek","Kanıt","Taşıma Sıra","Dönüş Sıra"
                ]],
                use_container_width=True,
                hide_index=True
            )
        except Exception as e:
            st.warning(str(e))

st.divider()
st.subheader("📊 SON KUPON KARNESİ")
if "v10_eval" in st.session_state:
    st.markdown(f"### {st.session_state.get('v10_eval_title','')}")
    st.dataframe(
        st.session_state["v10_eval"],
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Canlı hedef sonucu geldiğinde üstteki HIZLI SONUÇ EKLE bölümünden gir; kuponlar otomatik test edilir.")

st.caption(
    "V12.1'de 2 ayrı 7'li ve 1 adet 10'lu üretilir. Kupon benzerliğine ceza yoktur; taşıma oranı benzer geçmiş gecelerden dinamik öğrenilir. Yüksek ham skor tek başına seçim sebebi değildir. "
    "Öncelik: benzer geçmiş olaylarda gerçek isabet + 6x6 yol ritmi + dinlenme/dönüş + gece içi sıcaklaşma + destek."
)
