
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import base64
import json
import math
import re
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# HIZLI ON V19
# Gece Karakteri + Sayı Yolculuğu Uzmanları
# ============================================================

st.set_page_config(
    page_title="Hızlı On V19 — Gece Karakteri + Yolculuk Uzmanları",
    page_icon="🌙",
    layout="wide",
)

st.title("🌙 Hızlı On V19 — Gece Karakteri + Yolculuk Uzmanları")
st.caption(
    "İlk 3 çekiliş geceyi tanır. Sonraki her hedefte aday sayının yaşam yolculuğu, "
    "aynı hedef saatindeki benzer geçmiş gecelerle karşılaştırılır. "
    "Yüksek ham skor tek başına seçim sebebi değildir."
)

DATA_FILE = Path("veri.txt")
SLOTS = [
    "23:02","23:07","23:12","23:17","23:22","23:27",
    "23:32","23:37","23:42","23:47","23:52","23:57"
]
FIRST3 = SLOTS[:3]
TARGETS = SLOTS[3:]
SLOT_INDEX = {s:i for i,s in enumerate(SLOTS)}

DEFAULT_REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "veri.txt"
BASE = 0.25

# Araştırmada en iyi genel yolculuk ayarı
NEIGHBOR_NIGHTS = 12
PRIOR_STRENGTH = 10.0

# ============================================================
# GITHUB / KALICI KAYIT
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
            "User-Agent": "hizli-on-v19",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        obj = json.loads(r.read().decode("utf-8"))
    return base64.b64decode(obj["content"]).decode("utf-8"), obj["sha"]


def github_write(token, repo, branch, path, text, message):
    _, sha = github_read(token, repo, branch, path)
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    payload = json.dumps({
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": branch,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "hizli-on-v19",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


# ============================================================
# VERİ OKUMA / SONUÇ KAYDETME
# ============================================================

def repair_draw_no(no, date_s):
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
            no = int(re.findall(r"\d+", p[0])[0])
            date_s, time_s = p[1].split()
            nums = sorted(set(int(x) for x in re.findall(r"\d+", p[2])))
            no = repair_draw_no(no, date_s)
        except Exception:
            continue
        if time_s not in SLOTS or len(nums) != 20 or any(n < 1 or n > 80 for n in nums):
            continue
        rows.append({
            "draw_no": no,
            "date": date_s,
            "time": time_s,
            "numbers": nums,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["_dt"] = pd.to_datetime(
        df["date"] + " " + df["time"],
        format="%d.%m.%Y %H:%M",
        errors="coerce",
    )
    df = df.dropna(subset=["_dt"])
    return (
        df.sort_values(["_dt","draw_no"])
        .drop_duplicates(["date","time"], keep="last")
        .reset_index(drop=True)
    )


def parse_result_block(raw):
    raw = (
        str(raw or "")
        .replace("\u00a0"," ")
        .replace("–","-")
        .replace("—","-")
        .replace("−","-")
    )
    m_no = re.search(
        r"(?:çekiliş|cekilis)\s*(?:no|numarası|numarasi)?\s*[:#-]?\s*(\d{4,8})",
        raw, re.I
    )
    m_dt = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}:\d{2})", raw)
    if not m_no:
        raise ValueError("Çekiliş no bulunamadı.")
    if not m_dt:
        raise ValueError("Tarih/saat bulunamadı.")
    date_s = datetime.strptime(m_dt.group(1), "%d.%m.%Y").strftime("%d.%m.%Y")
    time_s = m_dt.group(2)
    if time_s not in SLOTS:
        raise ValueError("Bu uygulama 23:02–23:57 gece seansını kullanır.")
    no = repair_draw_no(int(m_no.group(1)), date_s)
    tail = raw[m_dt.end():]
    nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", tail)]
    if len(nums) != 20 or len(set(nums)) != 20:
        raise ValueError(f"20 farklı sayı bekleniyor; {len(nums)} bulundu.")
    return {
        "draw_no": no,
        "date": date_s,
        "time": time_s,
        "numbers": sorted(nums),
    }


def line_for(r):
    return f"{r['draw_no']} | {r['date']} {r['time']} | {' '.join(map(str,r['numbers']))}"


def append_or_replace(text, r):
    key = f"{r['date']} {r['time']}"
    newline = line_for(r)
    out = []
    done = False
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
    return "\n".join(out).rstrip() + "\n"


def persist_result(r):
    token, repo, branch, path = github_config()
    if token:
        current, _ = github_read(token, repo, branch, path)
        updated = append_or_replace(current, r)
        if updated != current:
            github_write(
                token, repo, branch, path, updated,
                f"V19 add {r['draw_no']} {r['date']} {r['time']}"
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
# GECE HARİTASI
# ============================================================

def day_map(df):
    out = {}
    for _, r in df.iterrows():
        out.setdefault(str(r["date"]), {})[str(r["time"])] = set(r["numbers"])
    return out


def ordered_dates(df):
    return list(dict.fromkeys(df["date"].astype(str).tolist()))


def complete_night_dates(df):
    dm = day_map(df)
    return [d for d in ordered_dates(df) if all(s in dm.get(d,{}) for s in SLOTS)]


def next_live_target(df):
    dm = day_map(df)
    dates = ordered_dates(df)
    if not dates:
        return None, None, "Veri yok."
    d = dates[-1]
    day = dm.get(d,{})
    missing = [s for s in FIRST3 if s not in day]
    if missing:
        return d, None, "Geceyi tanımak için eksik: " + ", ".join(missing)
    for target in TARGETS:
        if target not in day:
            ti = SLOT_INDEX[target]
            prior = SLOTS[:ti]
            miss = [s for s in prior if s not in day]
            if miss:
                return d, None, "Akışta eksik çekiliş: " + ", ".join(miss)
            return d, target, None
    return d, None, "Bu gecenin 23:57 dahil tüm çekilişleri tamamlandı."


# ============================================================
# İLK 3 ÇEKİLİŞ — GECE KARAKTERİ
# ============================================================

def band(n):
    return (n-1)//10


def band_vec(s):
    a = [0]*8
    for n in s:
        a[band(n)] += 1
    return a


def consecutive_pairs_count(s):
    return sum(1 for n in s if n+1 in s)


def step2_pairs_count(s):
    return sum(1 for n in s if n+2 in s)


def first3_character_from_sets(draws3):
    a,b,c = draws3
    cnt = Counter()
    for s in draws3:
        cnt.update(s)
    vec = np.array([
        len(a&b)/8,
        len(b&c)/8,
        len(a&c)/8,
        len(a&b&c)/5,
        sum(consecutive_pairs_count(x) for x in draws3)/15,
        sum(step2_pairs_count(x) for x in draws3)/15,
        *[x/6 for x in band_vec(c)],
        *[sum(1 for n in range(1,81) if cnt[n]==k)/80 for k in (1,2,3)]
    ], dtype=float)

    avgcarry = (len(a&b) + len(b&c))/2
    if avgcarry >= 6:
        carry_regime = "TAŞIMA-AĞIR"
    elif avgcarry <= 4:
        carry_regime = "DÖNÜŞ-AĞIR"
    else:
        carry_regime = "KARMA"

    cons = sum(consecutive_pairs_count(x) for x in draws3)
    step2 = sum(step2_pairs_count(x) for x in draws3)
    if cons >= step2 + 3:
        pattern_regime = "ARDIŞIK"
    elif step2 >= cons + 3:
        pattern_regime = "STEP2"
    else:
        pattern_regime = "DENGELİ"

    return {
        "vector": vec,
        "carry_regime": carry_regime,
        "pattern_regime": pattern_regime,
        "carry12": len(a&b),
        "carry23": len(b&c),
        "carry13": len(a&c),
        "core3": len(a&b&c),
        "cons": cons,
        "step2": step2,
    }


def character_distance(c1, c2):
    return float(np.abs(c1["vector"] - c2["vector"]).sum())


# ============================================================
# SAYI YOLCULUĞU
# ============================================================

def current_gap(draws, n):
    if n in draws[-1]:
        return 0
    for g, s in enumerate(reversed(draws)):
        if n in s:
            return g
    return 99


def path_bits(draws, n, k=4):
    return "".join("1" if n in s else "0" for s in draws[-k:]).rjust(k, "0")


def current_streak(draws, n):
    c = 0
    for s in reversed(draws):
        if n in s:
            c += 1
        else:
            break
    return c


def gap_bucket(g):
    if g <= 3:
        return str(g)
    if g in (4,5):
        return "4-5"
    if 6 <= g < 99:
        return "6+"
    return "NEW"


def streak_bucket(s):
    if s <= 2:
        return str(s)
    return "3+"


def journey_signature(draws, n):
    src = draws[-1]
    return (
        gap_bucket(current_gap(draws,n)),
        path_bits(draws,n,4),
        min(sum(n in s for s in draws[-3:]),3),
        streak_bucket(current_streak(draws,n)),
        min(int(n-1 in src) + int(n+1 in src), 2),
        min(int(n-2 in src) + int(n+2 in src), 2),
    )


def journey_label(draws, n):
    sig = journey_signature(draws,n)
    return (
        f"{sig[0]} | P4:{sig[1]} | R3:{sig[2]} | "
        f"SERİ:{sig[3]} | ±1:{sig[4]} | ±2:{sig[5]}"
    )


# ============================================================
# V19 ANA UZMAN
# ============================================================

def score_live_target(df, target_date, target_slot):
    dm = day_map(df)
    day = dm[target_date]
    ti = SLOT_INDEX[target_slot]
    prior_slots = SLOTS[:ti]
    draws = [day[s] for s in prior_slots]

    first3_now = [day[s] for s in FIRST3]
    char_now = first3_character_from_sets(first3_now)

    # Yalnız tamamen bitmiş geçmiş geceler
    past_dates = [
        d for d in complete_night_dates(df)
        if pd.to_datetime(d,format="%d.%m.%Y") < pd.to_datetime(target_date,format="%d.%m.%Y")
    ]
    if len(past_dates) < 8:
        raise ValueError("Gece karakteri uzmanı için en az 8 geçmiş tam gece gerekli.")

    # İlk üç karaktere en çok benzeyen K gece
    historical_chars = {}
    for d in past_dates:
        historical_chars[d] = first3_character_from_sets([dm[d][s] for s in FIRST3])

    ranked_dates = sorted(
        past_dates,
        key=lambda d: character_distance(char_now, historical_chars[d])
    )
    neighbors = ranked_dates[:min(NEIGHBOR_NIGHTS,len(ranked_dates))]

    # Yakınlık sadece örnek ağırlığı; seçim birebir yolculuk izinden gelir.
    weights = {
        d: 1.0/(0.08 + character_distance(char_now,historical_chars[d]))
        for d in neighbors
    }

    # Geçmiş aynı hedef saatinde imza -> aday/hit bankası
    sig_bank = defaultdict(lambda:[0.0,0.0])  # weighted count, weighted hit
    first3_bank = defaultdict(lambda:[0.0,0.0])

    for d in neighbors:
        hday = dm[d]
        hdraws = [hday[s] for s in prior_slots]
        htgt = hday[target_slot]
        w = weights[d]

        hf3 = [hday[s] for s in FIRST3]
        for n in range(1,81):
            sig = journey_signature(hdraws,n)
            sig_bank[sig][0] += w
            sig_bank[sig][1] += w*int(n in htgt)

            cls = sum(n in s for s in hf3)
            first3_bank[cls][0] += w
            first3_bank[cls][1] += w*int(n in htgt)

    rows = []
    for n in range(1,81):
        sig = journey_signature(draws,n)
        den, hit = sig_bank[sig]
        exact_rate = (hit + BASE*PRIOR_STRENGTH)/(den + PRIOR_STRENGTH)

        f3cls = sum(n in s for s in first3_now)
        cden, chit = first3_bank[f3cls]
        f3_rate = (chit + BASE*8)/(cden + 8)

        # Araştırmada exact journey + küçük first3 katılım desteği en iyi yönü verdi.
        score = 0.85*exact_rate + 0.15*f3_rate

        # Güven: birebir iz desteği azsa yüksek oran şişmesin.
        reliability = math.sqrt(den/(den+12.0)) if den > 0 else 0.0
        calibrated = BASE + (score-BASE)*reliability

        rows.append({
            "Sayı": n,
            "Rol": "TAŞIMA" if n in draws[-1] else "DÖNÜŞ",
            "Gap": current_gap(draws,n),
            "P4": path_bits(draws,n,4),
            "P6": path_bits(draws,n,6),
            "Seri": current_streak(draws,n),
            "İlk3Görünüm": f3cls,
            "Yolculuk": journey_label(draws,n),
            "BirebirİzDestek": den,
            "BirebirİzOranı": exact_rate,
            "İlk3SınıfOranı": f3_rate,
            "Güven": reliability,
            "V19Skor": calibrated,
        })

    tab = pd.DataFrame(rows).sort_values(
        ["V19Skor","Güven","BirebirİzDestek"],
        ascending=False
    ).reset_index(drop=True)

    # Gece karakterine göre uzman güveni.
    regime_key = f"{char_now['carry_regime']} + {char_now['pattern_regime']}"
    # 44-gece araştırmasında özellikle bu rejim dikkat çekti.
    if regime_key == "TAŞIMA-AĞIR + ARDIŞIK":
        regime_conf = "YÜKSEK"
    elif char_now["carry_regime"] == "KARMA" and char_now["pattern_regime"] == "ARDIŞIK":
        regime_conf = "DÜŞÜK"
    else:
        regime_conf = "NORMAL"

    return tab, char_now, neighbors, regime_conf


# ============================================================
# İKİ 7'Lİ + BİR 10'LU
# ============================================================

def build_tickets(tab, regime_conf):
    """
    7A: en güçlü birebir yolculuk izleri.
    7B: aynı skoru kopyalamaz; yeterli destek + farklı rol dağılımı arar.
    10'lu: ana konsensüs.
    Hiçbir sayı yalnız ham skor yüksek diye seçilmez.
    """
    z = tab.copy()

    # Güven kapısı
    z["Kanıtlı"] = (
        (z["BirebirİzDestek"] >= z["BirebirİzDestek"].median()) &
        (z["Güven"] >= z["Güven"].median())
    )

    primary = z.sort_values(
        ["Kanıtlı","V19Skor","Güven","BirebirİzDestek"],
        ascending=False
    )

    t7a = primary.head(7)["Sayı"].astype(int).tolist()

    # 7B: rol uzmanı. Aynı sayıları zorla yasaklamıyoruz;
    # fakat taşıma/dönüş tarafında ayrı güçlü adayları öne çıkarıyoruz.
    carry = primary[primary["Rol"]=="TAŞIMA"].copy()
    ret = primary[primary["Rol"]=="DÖNÜŞ"].copy()

    # Gece karakteri yüksek taşıma güvenindeyse A'da taşıma biraz daha fazla,
    # aksi durumda dengeli.
    if regime_conf == "YÜKSEK":
        c_seat = 4
    elif regime_conf == "DÜŞÜK":
        c_seat = 2
    else:
        c_seat = 3

    t7b = (
        carry.head(c_seat)["Sayı"].astype(int).tolist() +
        ret.head(7-c_seat)["Sayı"].astype(int).tolist()
    )
    # Kendi içinde skora göre
    score_map = dict(zip(z["Sayı"].astype(int), z["V19Skor"].astype(float)))
    t7b = sorted(dict.fromkeys(t7b), key=lambda n:score_map.get(n,0), reverse=True)
    if len(t7b) < 7:
        for n in primary["Sayı"].astype(int):
            if n not in t7b:
                t7b.append(n)
            if len(t7b)==7:
                break

    t10 = primary.head(10)["Sayı"].astype(int).tolist()

    # Pas sinyali: top10 ortalaması tabandan çok az yukarıdaysa uyar.
    top10_edge = float(primary.head(10)["V19Skor"].mean() - BASE)
    if top10_edge >= 0.025 and regime_conf != "DÜŞÜK":
        signal = "GÜÇLÜ"
    elif top10_edge >= 0.010:
        signal = "NORMAL"
    else:
        signal = "ZAYIF / PAS DÜŞÜN"

    return {
        "7A": t7a[:7],
        "7B": t7b[:7],
        "10": t10[:10],
        "_signal": signal,
        "_edge": top10_edge,
    }


def evaluate_tickets(tickets, actual):
    actual = set(actual)
    rows = []
    for key,label in [("7A","7'li A"),("7B","7'li B"),("10","10'lu")]:
        t = tickets[key]
        hits = sorted(set(t)&actual)
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
    f"📂 {source} · {len(df)} çekiliş · "
    f"{len(complete_night_dates(df))} tam gece · "
    f"son: #{df.iloc[-1]['draw_no']} {df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

token,_,_,_ = github_config()
if token:
    st.caption("🔒 Kalıcı GitHub veri.txt kayıt: AÇIK")
else:
    st.warning("⚠️ GitHub token yok; yerel veri.txt kullanılıyor.")

if st.session_state.get("msg"):
    st.success(st.session_state.pop("msg"))

with st.expander("⚡ HIZLI SONUÇ EKLE", expanded=False):
    raw = st.text_area(
        "Sonucu aynen yapıştır",
        height=220,
        placeholder="Çekiliş no: 49258\n15.08.2026 - 23:52\n..."
    )
    if st.button("💾 KAYDET + SONRAKİ KUPONU GELİŞTİR", use_container_width=True):
        try:
            r = parse_result_block(raw)
            pred = st.session_state.get("pred")
            if pred and r["date"]==pred["date"] and r["time"]==pred["target"]:
                st.session_state["eval"] = evaluate_tickets(pred["tickets"], r["numbers"])
                st.session_state["eval_title"] = (
                    f"#{r['draw_no']} {r['date']} {r['time']}"
                )

            persist_result(r)
            st.session_state["msg"] = (
                f"✅ #{r['draw_no']} {r['date']} {r['time']} kaydedildi. "
                "Gece karakteri ve sayı yolculukları yeniden hesaplandı."
            )
            st.rerun()
        except Exception as e:
            st.error(str(e))

target_date, target_slot, target_error = next_live_target(df)
tabs = st.tabs([
    "🏆 CANLI KUPONLAR",
    "🧬 GECE KARAKTERİ",
    "🛤️ SAYI YOLCULUKLARI",
    "📊 SON KUPON KARNESİ",
])

with tabs[0]:
    if target_slot is None:
        st.warning(target_error)
        st.info(
            "Yeni gecede 23:02 + 23:07 + 23:12 tamamlanınca "
            "Gece Karakteri Uzmanı açılır."
        )
        st.session_state.pop("pred",None)
    else:
        try:
            tab, gc, neighbors, regime_conf = score_live_target(
                df, target_date, target_slot
            )
            tickets = build_tickets(tab, regime_conf)

            st.session_state["pred"] = {
                "date": target_date,
                "target": target_slot,
                "tickets": tickets,
            }

            st.success(f"🎯 CANLI HEDEF: {target_date} {target_slot}")

            a,b,c,d = st.columns(4)
            a.metric("Gece karakteri", gc["carry_regime"])
            b.metric("Pattern", gc["pattern_regime"])
            c.metric("Uzman güveni", regime_conf)
            d.metric("Canlı sinyal", tickets["_signal"])

            st.caption(
                f"İlk 3 taşıma: {gc['carry12']} → {gc['carry23']} · "
                f"3'lü ortak çekirdek: {gc['core3']} · "
                f"Karşılaştırılan en benzer geçmiş gece: {len(neighbors)}."
            )

            st.markdown(f"### 🎯 {target_slot} — 7'Lİ A · BİREBİR YOLCULUK")
            st.code("  ".join(f"{n:02d}" for n in tickets["7A"]))

            st.markdown(f"### 🎯 {target_slot} — 7'Lİ B · ROL UZMANI")
            st.code("  ".join(f"{n:02d}" for n in tickets["7B"]))

            st.markdown(f"### 🏆 {target_slot} — 10'LU ANA KONSENSÜS")
            st.code("  ".join(f"{n:02d}" for n in tickets["10"]))

            if tickets["_signal"] == "ZAYIF / PAS DÜŞÜN":
                st.warning(
                    "Bu hedefte geçmiş benzer gecelerin yolculuk kanıtı zayıf. "
                    "Program zorla güçlü sinyal varmış gibi davranmıyor."
                )

        except Exception as e:
            st.error(f"Kupon üretilemedi: {e}")
            st.session_state.pop("pred",None)

with tabs[1]:
    if target_slot is None:
        st.warning(target_error)
    else:
        try:
            tab, gc, neighbors, regime_conf = score_live_target(
                df, target_date, target_slot
            )
            st.subheader("🧬 İlk 3 çekilişten gece karakteri")
            st.write({
                "Taşıma rejimi": gc["carry_regime"],
                "Pattern rejimi": gc["pattern_regime"],
                "23:02→23:07 taşıma": gc["carry12"],
                "23:07→23:12 taşıma": gc["carry23"],
                "23:02↔23:12 ortak": gc["carry13"],
                "İlk 3 ortak çekirdek": gc["core3"],
                "Ardışık baskı": gc["cons"],
                "+2 baskı": gc["step2"],
                "Uzman güveni": regime_conf,
            })
            st.markdown(
                "**En benzer geçmiş geceler:** " +
                ", ".join(neighbors)
            )
        except Exception as e:
            st.error(str(e))

with tabs[2]:
    if target_slot is None:
        st.warning(target_error)
    else:
        try:
            tab, gc, neighbors, regime_conf = score_live_target(
                df, target_date, target_slot
            )
            show = tab.copy()
            for col in [
                "BirebirİzDestek","BirebirİzOranı",
                "İlk3SınıfOranı","Güven","V19Skor"
            ]:
                show[col] = show[col].map(lambda x: round(float(x),3))
            st.dataframe(
                show[[
                    "Sayı","Rol","Gap","P4","P6","Seri","İlk3Görünüm",
                    "Yolculuk","BirebirİzDestek","BirebirİzOranı",
                    "İlk3SınıfOranı","Güven","V19Skor"
                ]],
                use_container_width=True,
                hide_index=True,
            )
        except Exception as e:
            st.error(str(e))

with tabs[3]:
    if "eval" in st.session_state:
        st.markdown(f"### {st.session_state.get('eval_title','')}")
        st.dataframe(
            st.session_state["eval"],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Canlı hedef sonucu geldiğinde HIZLI SONUÇ EKLE bölümünden kaydet; "
            "7A, 7B ve 10'lu otomatik test edilir."
        )

st.divider()
st.caption(
    "Araştırma notu: 44 gece üzerinde yapılan walk-forward çalışmada "
    "ilk 3 karakter + birebir yolculuk yaklaşımı Top-10 için 2.537 ortalama "
    "isabet verdi; rastgele beklenti 2.500'dür. Bu küçük bir üstünlüktür, "
    "yüksek isabet garantisi değildir. V19 bu nedenle kanıt zayıfsa PAS uyarısı verir."
)
