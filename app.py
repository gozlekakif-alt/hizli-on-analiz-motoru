
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import hashlib
import json
import base64

st.set_page_config(page_title="Sayı Laboratuvarı", layout="wide", page_icon="🎼")

DB_PATH = Path("predictions_v2.db")
SLOTS = ["23:02","23:07","23:12","23:17","23:22","23:27",
         "23:32","23:37","23:42","23:47","23:52","23:57"]

DEFAULT_DATA_FILE = Path("veri.txt")

def repo_data_text():
    """GitHub token varsa repodaki EN GUNCEL veri.txt'yi API'den oku; yoksa yerel checkout'u kullan."""
    try:
        token, repo, branch, path = github_config()
        if token:
            text, _sha = github_read_file(token, repo, branch, path)
            return text
    except Exception:
        pass
    if DEFAULT_DATA_FILE.exists():
        return DEFAULT_DATA_FILE.read_text(encoding="utf-8")
    return ""




def normalize_result_line(draw_no, date_s, time_s, nums):
    nums = sorted(set(map(int, nums)))
    if len(nums) != 20 or any(n < 1 or n > 80 for n in nums):
        raise ValueError("Sonuç 1-80 arasında tam 20 farklı sayı içermeli.")
    return f"{draw_no} | {date_s} {time_s} | {' '.join(map(str, nums))}"

def append_result_to_text(text, line):
    parts = [x.strip() for x in line.split('|')]
    dt_key = parts[1]
    existing = []
    for raw in text.splitlines():
        if raw.strip():
            existing.append(raw.rstrip())
            p = [x.strip() for x in raw.split('|')]
            if len(p) >= 2 and p[1] == dt_key:
                raise ValueError(f"{dt_key} zaten veri.txt içinde var.")
    existing.append(line)
    return "\n".join(existing).rstrip() + "\n"

def chain_status(df, target_date, target_time):
    data = df_to_map(df)
    ti = SLOTS.index(target_time)
    return [t for t in SLOTS[:ti] if (target_date, t) not in data]

def next_slot(time_s):
    i = SLOTS.index(time_s)
    return SLOTS[i+1] if i+1 < len(SLOTS) else None

# ----------------------------
# Data I/O
# ----------------------------

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS locked_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            target_date TEXT NOT NULL,
            target_time TEXT NOT NULL,
            model_version TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            coupon_name TEXT NOT NULL,
            numbers TEXT NOT NULL,
            metadata TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_date TEXT NOT NULL,
            target_time TEXT NOT NULL,
            numbers TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

def parse_pipe_text(text: str) -> pd.DataFrame:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 3:
            continue
        draw_no, dt, nums = parts[0], parts[1], parts[2]
        d, t = dt.split()
        ns = sorted({int(x) for x in nums.split() if x.strip().isdigit()})
        if len(ns) != 20:
            continue
        rows.append({
            "draw_no": int(draw_no) if str(draw_no).isdigit() else draw_no,
            "date": d,
            "time": t,
            "numbers": ns
        })
    return pd.DataFrame(rows)

def parse_csv(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower().strip(): c for c in df.columns}
    if {"date","time","numbers"}.issubset(cols):
        out = []
        for _, r in df.iterrows():
            ns = [int(x) for x in str(r[cols["numbers"]]).replace(",", " ").split()]
            if len(set(ns)) == 20:
                out.append({
                    "draw_no": r[cols.get("draw_no", cols.get("no", "date"))] if ("draw_no" in cols or "no" in cols) else "",
                    "date": str(r[cols["date"]]),
                    "time": str(r[cols["time"]]),
                    "numbers": sorted(set(ns))
                })
        return pd.DataFrame(out)
    raise ValueError("CSV için date, time, numbers sütunları gerekli.")

def df_to_map(df):
    m = {}
    for _, r in df.iterrows():
        m[(str(r["date"]), str(r["time"]))] = set(map(int, r["numbers"]))
    return m

def to_date(s):
    return datetime.strptime(s, "%d.%m.%Y").date()

def fmt(d):
    return d.strftime("%d.%m.%Y")

# ----------------------------
# Feature engine
# ----------------------------

def macro6_days_pattern(data, d, n, target_time, available_days):
    """
    Son 6 TAM GEÇMİŞ GÜNDE aynı hedef saatte sayının görülme deseni.
    En eski -> en yeni, örn. 010101.
    Hedef gün dahil değildir.
    """
    prev_days = [x for x in available_days if x < d]
    prev_days = prev_days[-6:]
    if not prev_days:
        return ""
    return "".join("1" if n in data.get((fmt(x), target_time), set()) else "0" for x in prev_days)

def macro6_gap(p):
    g = 0
    for z in reversed(p):
        if z == "1":
            break
        g += 1
    return g

def micro_macro_code(micro6, macro6):
    """İki 6'lı söz dizimini tek imza anahtarına çevir."""
    return f"{micro6}|{macro6}"


def path_before(data, d, n, target_idx, length=6):
    ss = SLOTS[max(0, target_idx-length):target_idx]
    return "".join("1" if n in data.get((fmt(d), t), set()) else "0" for t in ss)

def gap_from_path(p):
    g = 0
    for z in reversed(p):
        if z == "1":
            break
        g += 1
    return g

def weekly_flag(data, d, n, target_time):
    pd0 = d - timedelta(days=7)
    return int(n in data.get((fmt(pd0), target_time), set()))

def shrink(hn, prior, strength):
    h, n = hn
    return (h + strength * prior) / (n + strength)

def complete_days(df):
    days = sorted({to_date(x) for x in df["date"].astype(str).unique()})
    data = df_to_map(df)
    return [d for d in days if all((fmt(d), t) in data for t in SLOTS)]

def learn_hour_model(df, source, target, train_days, calibration_days):
    data = df_to_map(df)
    ti = SLOTS.index(target)
    all_complete_days = complete_days(df)

    sig = defaultdict(lambda:[0,0])
    base = defaultdict(lambda:[0,0])
    num = defaultdict(lambda:[0,0])

    for d in train_days:
        A = data[(fmt(d), source)]
        Y = data[(fmt(d), target)]
        for n in range(1,81):
            pool = "C" if n in A else "E"
            hit = int(n in Y)
            p = path_before(data, d, n, ti)
            macro6 = macro6_days_pattern(data, d, n, target, all_complete_days)
            base[pool][0] += hit
            base[pool][1] += 1
            feats = [
                ("path", p),
                ("p4", p[-4:]),
                ("gap", gap_from_path(p)),
                ("seen", p.count("1")),
                ("week", weekly_flag(data, d, n, target)),
                ("macro6", macro6),
                ("macro6_gap", macro6_gap(macro6) if macro6 else 6),
                ("micro_macro", micro_macro_code(p, macro6)),
                ("odd", n % 2),
                ("low", int(n <= 40)),
            ]
            for k,v in feats:
                sig[(pool,k,v)][0] += hit
                sig[(pool,k,v)][1] += 1
            num[(pool,n)][0] += hit
            num[(pool,n)][1] += 1

    carry_med = round(np.median([
        len(data[(fmt(d),source)] & data[(fmt(d),target)])
        for d in train_days
    ]))
    odd_med = round(np.median([
        sum(n % 2 for n in data[(fmt(d),target)])
        for d in train_days
    ]))
    low_med = round(np.median([
        sum(n <= 40 for n in data[(fmt(d),target)])
        for d in train_days
    ]))

    def base_candidates(d):
        A = data[(fmt(d), source)]
        out = []
        for n in range(1,81):
            pool = "C" if n in A else "E"
            ph, pn = base[pool]
            pr = ph/pn if pn else 0.25
            p = path_before(data, d, n, ti)
            macro6 = macro6_days_pattern(data, d, n, target, all_complete_days)
            micro_macro = micro_macro_code(p, macro6)
            sc = (
                .23*shrink(sig[(pool,"path",p)], pr, 25)
                + .12*shrink(sig[(pool,"p4",p[-4:])], pr, 23)
                + .10*shrink(sig[(pool,"gap",gap_from_path(p))], pr, 25)
                + .08*shrink(sig[(pool,"seen",p.count("1"))], pr, 25)
                + .07*shrink(sig[(pool,"week",weekly_flag(data,d,n,target))], pr, 28)
                + .12*shrink(sig[(pool,"macro6",macro6)], pr, 24)
                + .08*shrink(sig[(pool,"macro6_gap",macro6_gap(macro6) if macro6 else 6)], pr, 24)
                + .10*shrink(sig[(pool,"micro_macro",micro_macro)], pr, 18)
                + .04*shrink(sig[(pool,"odd",n%2)], pr, 30)
                + .04*shrink(sig[(pool,"low",int(n<=40))], pr, 30)
                + .02*shrink(num[(pool,n)], pr, 22)
            )
            out.append({
                "n": n,
                "pool": pool,
                "path": p,
                "macro6": macro6,
                "micro_macro": micro_macro,
                "gap": gap_from_path(p),
                "macro6_gap": macro6_gap(macro6) if macro6 else 6,
                "seen": p.count("1"),
                "week": weekly_flag(data,d,n,target),
                "odd": n%2,
                "low": int(n<=40),
                "base_score": sc
            })
        ordered = sorted(out, key=lambda x:(x["base_score"], -x["n"]))
        for rank,c in enumerate(ordered,1):
            c["pct"] = 100*rank/80
            c["band"] = "L" if c["pct"] < 30 else "M" if c["pct"] < 60 else "W" if c["pct"] < 80 else "H"
        return out

    # Hedef saatin puan-band notası: gerçek 20 içinde L/M/W/H kompozisyonu.
    band_rows = []
    for d in train_days:
        Y = data[(fmt(d), target)]
        cs = base_candidates(d)
        pct = {c["n"]: c["pct"] for c in cs}
        br = {"L":0,"M":0,"W":0,"H":0}
        for n in Y:
            s = pct[n]
            b = "L" if s < 30 else "M" if s < 60 else "W" if s < 80 else "H"
            br[b] += 1
        band_rows.append(br)
    band_note = {b:int(round(np.median([r[b] for r in band_rows]))) for b in "LMWH"}
    while sum(band_note.values()) < 20:
        means = {b:np.mean([r[b] for r in band_rows]) for b in "LMWH"}
        b = max(means, key=lambda k: means[k]-band_note[k]); band_note[b] += 1
    while sum(band_note.values()) > 20:
        means = {b:np.mean([r[b] for r in band_rows]) for b in "LMWH"}
        b = max(means, key=lambda k: band_note[k]-means[k]); band_note[b] -= 1

    def note20(cands):
        sel = []
        for pool,q in [("C",carry_med),("E",20-carry_med)]:
            sel += sorted(
                [c for c in cands if c["pool"] == pool],
                key=lambda x:(-x["base_score"], x["n"])
            )[:q]

        # parity / low-high repair, preserving pool counts
        for key,targetq in [("odd", odd_med),("low", low_med)]:
            for _ in range(12):
                cur = sum(c[key] for c in sel)
                if cur == targetq:
                    break
                need = cur < targetq
                used = {c["n"] for c in sel}
                best = None
                for outc in sel:
                    if bool(outc[key]) == need:
                        continue
                    for inc in cands:
                        if inc["n"] in used or inc["pool"] != outc["pool"] or bool(inc[key]) != need:
                            continue
                        loss = outc["base_score"] - inc["base_score"]
                        if best is None or loss < best[0]:
                            best = (loss, outc, inc)
                if best is None:
                    break
                _, outc, inc = best
                sel[sel.index(outc)] = inc
        return sel

    # chord calibration
    chord = defaultdict(lambda:[0,0])
    role = defaultdict(lambda:[0,0])

    for d in calibration_days:
        Y = data[(fmt(d), target)]
        cands = base_candidates(d)
        note = note20(cands)
        all_cluster = Counter(c["path"] for c in cands)
        note_cluster = Counter(c["path"] for c in note)

        for pool in ["C","E"]:
            arr = sorted([c for c in note if c["pool"]==pool],
                         key=lambda x:(-x["base_score"],x["n"]))
            for rank,c in enumerate(arr,1):
                hit = int(c["n"] in Y)
                p = c["path"]
                role_name = f"{pool}{rank}"
                sz_all = min(all_cluster[p], 12)
                sz_note = min(note_cluster[p], 6)
                keys = [
                    ("exact", target, pool, p),
                    ("p4", target, pool, p[-4:]),
                    ("size", target, pool, sz_all),
                    ("pathsize", target, pool, p, sz_all),
                    ("notesize", target, pool, p, sz_note),
                    ("macro6", target, pool, c.get("macro6","")),
                    ("micro_macro", target, pool, c.get("micro_macro","")),
                ]
                for k in keys:
                    chord[k][0] += hit
                    chord[k][1] += 1
                role[(target, role_name, p[-4:])][0] += hit
                role[(target, role_name, p[-4:])][1] += 1

    model = {
        "data": data,
        "source": source,
        "target": target,
        "target_idx": ti,
        "carry_med": carry_med,
        "odd_med": odd_med,
        "low_med": low_med,
        "band_note": band_note,
        "base_candidates": base_candidates,
        "note20": note20,
        "chord": chord,
        "role": role
    }
    return model

def score_live(model, d):
    target = model["target"]
    cands = model["base_candidates"](d)
    note = model["note20"](cands)
    chord = model["chord"]
    role = model["role"]

    all_cluster = Counter(c["path"] for c in cands)
    note_cluster = Counter(c["path"] for c in note)
    enriched = []

    for pool in ["C","E"]:
        arr = sorted([c for c in note if c["pool"]==pool],
                     key=lambda x:(-x["base_score"],x["n"]))
        for rank,c0 in enumerate(arr,1):
            c = dict(c0)
            p = c["path"]
            role_name = f"{pool}{rank}"
            prior = .25
            sz_all = min(all_cluster[p],12)
            sz_note = min(note_cluster[p],6)

            exact = shrink(chord[("exact",target,pool,p)], prior, 10)
            p4 = shrink(chord[("p4",target,pool,p[-4:])], prior, 12)
            size = shrink(chord[("size",target,pool,sz_all)], prior, 14)
            pathsize = shrink(chord[("pathsize",target,pool,p,sz_all)], prior, 8)
            notesize = shrink(chord[("notesize",target,pool,p,sz_note)], prior, 8)
            rr = shrink(role[(target,role_name,p[-4:])], prior, 10)
            macro6_score = shrink(chord[("macro6",target,pool,c.get("macro6",""))], prior, 10)
            micro_macro_score = shrink(chord[("micro_macro",target,pool,c.get("micro_macro",""))], prior, 8)

            # Dinlenme destekleyici; 6×6 ayrı katmandır.
            rest_bonus = 0.006 if c["gap"] in (3,4,6) else 0.0

            c["role"] = role_name
            c["cluster_size"] = all_cluster[p]
            c["macro6_score"] = macro6_score
            c["micro_macro_score"] = micro_macro_score
            c["chord_score"] = (
                .15*c["base_score"]
                + .16*exact
                + .09*p4
                + .11*size
                + .14*pathsize
                + .08*notesize
                + .06*rr
                + .09*macro6_score
                + .12*micro_macro_score
                + rest_bonus
            )
            enriched.append(c)

    return sorted(enriched, key=lambda x:(-x["chord_score"], -x["base_score"], x["n"]))

# ----------------------------
# Coupon construction
# ----------------------------

def make_coupons(ranked):
    # A: Ana saat-akoru
    A = ranked[:7]

    # B: Dinlenip yeniden gelen; iki ana ankraj korunur.
    anchors = ranked[:2]
    rest = sorted(ranked[2:], key=lambda x:(
        -(x["pool"]=="E"),
        -(x["gap"] in (3,4,6)),
        -x["chord_score"],
        x["n"]
    ))
    B = anchors + rest[:5]

    # C: Puan-band notası + yol/küme. 1L + 2M + 2W + 2H.
    quota = {"L":1,"M":2,"W":2,"H":2}
    C = []
    for b,q in quota.items():
        arr = [x for x in ranked if x.get("band")==b and x["n"] not in {c["n"] for c in C}]
        C += sorted(arr, key=lambda x:(-x["chord_score"],x["n"]))[:q]
    if len(C) < 7:
        used={c["n"] for c in C}
        C += [x for x in ranked if x["n"] not in used][:7-len(C)]
    return {"A":A[:7], "B":B[:7], "C":C[:7]}

def input_hash(df, target_date, target_time):
    raw = df.sort_values(["date","time"]).to_json(orient="records") + target_date + target_time
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def lock_coupon(target_date, target_time, coupon_name, numbers, metadata, in_hash):
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO locked_predictions
        (created_at,target_date,target_time,model_version,input_hash,coupon_name,numbers,metadata)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        datetime.now().isoformat(timespec="seconds"),
        target_date,target_time,"v2.2-orchestra",
        in_hash,coupon_name,
        " ".join(map(str,sorted(numbers))),
        json.dumps(metadata, ensure_ascii=False)
    ))
    con.commit()
    con.close()

def get_locked(target_date=None, target_time=None):
    con = sqlite3.connect(DB_PATH)
    q = "SELECT * FROM locked_predictions"
    params=[]
    where=[]
    if target_date:
        where.append("target_date=?"); params.append(target_date)
    if target_time:
        where.append("target_time=?"); params.append(target_time)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC"
    df = pd.read_sql_query(q, con, params=params)
    con.close()
    return df



# ----------------------------
# UI
# ----------------------------

init_db()

st.title("🎼 Sayı Laboratuvarı v2.3 — 6×6 Mikro–Makro Orkestra")
st.caption("23:02 gün başlangıcı + kalıcı veri.txt + zincir bütünlüğü + saat karakteri + 64 yol + 80 sayı profili + Live Blind.")

with st.sidebar:
    st.header("Veri")
    st.success("Varsayılan veri: repo içindeki veri.txt otomatik yüklenir.")
    uploaded = st.file_uploader("İstersen geçici TXT/CSV ile override et", type=["txt","csv"])
    st.markdown("Beklenen TXT biçimi: `çekiliş_no | GG.AA.YYYY SS:DD | 20 sayı`")

try:
    if uploaded is not None:
        if uploaded.name.lower().endswith(".csv"):
            df = parse_csv(pd.read_csv(uploaded))
        else:
            df = parse_pipe_text(uploaded.read().decode("utf-8"))
        data_source_label = f"Geçici yükleme: {uploaded.name}"
    else:
        text = repo_data_text()
        if not text.strip():
            st.error("Repo kökünde veri.txt bulunamadı.")
            st.stop()
        df = parse_pipe_text(text)
        data_source_label = "Kalıcı repo verisi: veri.txt (token varsa GitHub canlı)"
except Exception as e:
    st.error(f"Veri okunamadı: {e}")
    st.stop()

if df.empty:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

st.caption(f"📂 {data_source_label} · {len(df)} çekiliş · {df['date'].nunique()} gün")

df["date_dt"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
df = df.sort_values(["date_dt","time"]).drop(columns=["date_dt"]).reset_index(drop=True)

days = complete_days(df)

tab_live, tab_hours, tab_numbers, tab_roads, tab_research, tab_history = st.tabs(["🔒 Live Blind","🎼 Saat Karakterleri","🧬 80 Sayı Profili","🛣️ 64 Yol Sözlüğü","🔬 Research","📚 Kilit Geçmişi"])

with tab_live:
    st.subheader("Live Blind Mode")

    st.markdown("### 🌅 Gün başlangıcı — 23:02 sonucunu ekle")
    st.caption("23:02 bu özel zincirin ilk çekilişidir. Önce sonucu kalıcı veri.txt'ye ekle; ardından 23:07 hedefi için kupon üret.")
    ds1, ds2 = st.columns(2)
    with ds1:
        start_date = st.text_input("23:02 tarih", value=(max(df["date"], key=lambda x:to_date(x)) if not df.empty else ""), key="start_date_2302")
    with ds2:
        start_draw_no = st.text_input("23:02 çekiliş no", key="start_draw_no_2302")
    start_nums_text = st.text_input("23:02 gerçek 20 sayı", key="start_nums_2302")

    if start_nums_text:
        try:
            start_nums = set(map(int, start_nums_text.replace(","," ").split()))
            if len(start_nums) != 20 or any(n < 1 or n > 80 for n in start_nums):
                st.warning("23:02 için 1-80 arasında tam 20 farklı sayı gir.")
                start_nums = None
        except Exception:
            start_nums = None
            st.warning("23:02 sayılarını boşlukla gir.")

        if start_nums is not None and start_draw_no.strip():
            start_line = normalize_result_line(start_draw_no.strip(), start_date, "23:02", start_nums)
            st.code(start_line)

            csave, cdown = st.columns(2)
            with csave:
                if st.button("✅ 23:02 satırını hazırla", type="primary", key="save_2302"):
                    st.success("23:02 satırı hazır. Sağdaki düğmeden güncellenmiş veri.txt'yi indirip GitHub'daki veri.txt'nin üzerine yükle.")

            with cdown:
                try:
                    base_text = repo_data_text()
                    updated_local = append_result_to_text(base_text, start_line)
                    st.download_button(
                        "⬇️ 23:02 eklenmiş veri.txt indir",
                        data=updated_local.encode("utf-8"),
                        file_name="veri.txt",
                        mime="text/plain",
                        key="download_2302"
                    )
                except Exception:
                    pass
    st.divider()
    st.warning("Tahmin üretildikten sonra kuponu kilitle. Sonuç gelmeden model veya sayılar değiştirilmemeli.")

    c1,c2,c3 = st.columns(3)
    with c1:
        target_date = st.text_input("Hedef tarih", value=max(df["date"], key=lambda x:to_date(x)))
    with c2:
        target_time = st.selectbox("Hedef saat", SLOTS[1:], index=5 if "23:32" in SLOTS[1:] else 0)
    with c3:
        train_n = st.number_input("Development gün", min_value=10, max_value=max(10,len(days)-5), value=min(20,max(10,len(days)-10)))

    if target_time not in SLOTS or SLOTS.index(target_time)==0:
        st.error("Hedef saat için önceki saat gerekli.")
        st.stop()

    source_time = SLOTS[SLOTS.index(target_time)-1]
    target_d = to_date(target_date)

    missing_chain = chain_status(df, target_date, target_time)
    if missing_chain:
        st.error("⛔ Veri zinciri eksik. Bu hedef için kupon üretimi kapatıldı.")
        st.write("Eksik saatler:", ", ".join(missing_chain))
        st.info("Önce eksik çekilişleri kalıcı veri.txt'ye ekleyin; sonra model yeniden hesaplanır.")
        st.stop()

    if (target_date, source_time) not in df_to_map(df):
        st.error(f"{target_date} {source_time} sonucu veri içinde yok. Live tahmin üretilemez.")
    else:
        hist_days = [d for d in days if d < target_d]
        if len(hist_days) < 12:
            st.error("Yeterli geçmiş tam gün yok.")
        else:
            train_n_eff = min(int(train_n), max(10,len(hist_days)-5))
            train_days = hist_days[:train_n_eff]
            calibration_days = hist_days[train_n_eff:]
            if len(calibration_days) < 5:
                calibration_days = hist_days[-5:]
                train_days = hist_days[:-5]

            model = learn_hour_model(df, source_time, target_time, train_days, calibration_days)
            ranked = score_live(model, target_d)
            coupons = make_coupons(ranked)

            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("Saat geçişi", f"{source_time}→{target_time}")
            m2.metric("Taşıma notası", f"{model['carry_med']}/20")
            m3.metric("Tek notası", f"{model['odd_med']}/20")
            m4.metric("Alt 1–40 notası", f"{model['low_med']}/20")
            bn=model["band_note"]
            m5.metric("Puan notası", f"{bn['L']}/{bn['M']}/{bn['W']}/{bn['H']}")

            st.markdown("### 80 sayı tarayıcı — ilk 20")
            view = pd.DataFrame([{
                "Sıra":i+1,
                "Sayı":c["n"],
                "C/E":c["pool"],
                "Puan bandı":c.get("band",""),
                "Puan %":round(c.get("pct",0),1),
                "6-adım yol":c["path"],
                "6-gün yol":c.get("macro6",""),
                "6×6 imza":c.get("micro_macro",""),
                "Dinlenme":c["gap"],
                "Küme":c["cluster_size"],
                "Rol":c["role"],
                "Baz skor":round(c["base_score"],4),
                "Akor skor":round(c["chord_score"],4),
            } for i,c in enumerate(ranked[:20])])
            st.dataframe(view, use_container_width=True, hide_index=True)

            st.markdown("### Üç kupon")
            cols = st.columns(3)
            for j,(name, cs) in enumerate(coupons.items()):
                nums = [c["n"] for c in cs]
                with cols[j]:
                    label = {"A":"Ana saat-akoru","B":"Dinlenme / yeniden giriş","C":"Puan-bandı + yol/küme"}[name]
                    st.markdown(f"**{name} — {label}**")
                    st.code("  ".join(f"{n:02d}" for n in nums))
                    st.caption(
                        f"C={sum(c['pool']=='C' for c in cs)} / E={sum(c['pool']=='E' for c in cs)} · "
                        f"tek={sum(c['n']%2 for c in cs)} · alt={sum(c['n']<=40 for c in cs)}"
                    )

            ih = input_hash(df, target_date, target_time)
            if st.button("🔒 Üç kuponu kilitle", type="primary"):
                old = get_locked(target_date,target_time)
                if not old.empty:
                    st.error("Bu tarih/saat için daha önce kilitli tahmin var. Live Blind bütünlüğü için yeniden kilitleme kapalı.")
                else:
                    for name, cs in coupons.items():
                        nums=[c["n"] for c in cs]
                        lock_coupon(
                            target_date,target_time,name,nums,
                            {
                                "source_time":source_time,
                                "carry_note":model["carry_med"],
                                "odd_note":model["odd_med"],
                                "low_note":model["low_med"],
                                "band_note":model["band_note"],
                                "details":[{
                                    "n":c["n"],"pool":c["pool"],"path":c["path"],
                                    "gap":c["gap"],"cluster":c["cluster_size"],
                                    "band":c.get("band"),"pct":c.get("pct"),
                                    "role":c["role"],"score":c["chord_score"]
                                } for c in cs]
                            },
                            ih
                        )
                    st.success("Kuponlar kilitlendi. Sonuç gelene kadar değiştirilemez.")

            st.markdown("### Sonuç doğrulama + kalıcı veri güncelleme")
            st.caption("Kilitli kuponu doğrula; sonra gerçek sonucu kalıcı veri.txt'ye ekle. Sonraki kupon güncel zincirden üretilir.")
            draw_no_input = st.text_input("Çekiliş no", key=f"drawno_{target_date}_{target_time}")
            result_text = st.text_input("Gerçek 20 sayı (boşlukla)", key=f"result_{target_date}_{target_time}")
            actual = None
            if result_text:
                try:
                    actual = set(map(int, result_text.replace(","," ").split()))
                    if len(actual) != 20 or any(n < 1 or n > 80 for n in actual):
                        st.warning("1-80 arasında tam 20 farklı sayı girin.")
                        actual = None
                    else:
                        locked_df = get_locked(target_date,target_time)
                        if locked_df.empty:
                            st.warning("Önce kuponları kilitleyin.")
                        else:
                            for _,r in locked_df.sort_values("coupon_name").iterrows():
                                nums = set(map(int,r["numbers"].split()))
                                hits = sorted(nums & actual)
                                st.write(f"**{r['coupon_name']}: {len(hits)}/7** — {hits}")
                except Exception as e:
                    st.error(str(e))
                    actual = None

            if actual is not None and draw_no_input.strip():
                line = normalize_result_line(draw_no_input.strip(), target_date, target_time, actual)
                st.code(line)
                csave,cdown = st.columns(2)
                with csave:
                    if st.button("💾 Sonucu kalıcı veri.txt'ye ekle", type="primary"):
                        try:
                            token,repo,branch,gh_path = github_config()
                            if token:
                                current,_ = github_read_file(token,repo,branch,gh_path)
                                updated = append_result_to_text(current,line)
                                github_write_file(token,repo,branch,gh_path,updated,f"Add draw {draw_no_input.strip()} {target_date} {target_time}")
                                st.success("GitHub veri.txt güncellendi. Uygulama yeniden yükleniyor.")
                                st.rerun()
                            else:
                                st.error("Kalıcı otomatik yazma için Streamlit Secrets'ta GITHUB_TOKEN gerekli.")
                        except Exception as e:
                            st.error(f"Kalıcı kayıt başarısız: {e}")
                with cdown:
                    try:
                        updated_local = append_result_to_text(repo_data_text(), line)
                        st.download_button("⬇️ Güncel veri.txt indir", updated_local.encode("utf-8"), file_name="veri.txt", mime="text/plain")
                    except Exception:
                        pass
                ns = next_slot(target_time)
                if ns:
                    st.info(f"Kayıttan sonra hedef **{ns}** seçildiğinde kupon güncel, eksiksiz zincirden üretilecek.")
                else:
                    st.info("Günün son saati. Yeni gün 23:02 ile başlar.")

with tab_hours:
    st.subheader("Saat Karakterleri — her geçiş ayrı nota")
    if len(days) < 15:
        st.info("En az 15 tam gün önerilir.")
    else:
        trn = days[:-5]
        cal = days[-5:]
        rows_hour=[]
        for tgt in SLOTS[1:]:
            src0=SLOTS[SLOTS.index(tgt)-1]
            try:
                mm=learn_hour_model(df,src0,tgt,trn,cal)
                bn=mm["band_note"]
                rows_hour.append({
                    "Geçiş":f"{src0}→{tgt}",
                    "Taşıma":mm["carry_med"],"Yeni":20-mm["carry_med"],
                    "Tek":mm["odd_med"],"Çift":20-mm["odd_med"],
                    "Alt":mm["low_med"],"Üst":20-mm["low_med"],
                    "L":bn["L"],"M":bn["M"],"W":bn["W"],"H":bn["H"]
                })
            except Exception:
                pass
        st.dataframe(pd.DataFrame(rows_hour),use_container_width=True,hide_index=True)

with tab_numbers:
    st.subheader("80 Sayı Profili — tek tek")
    tgt=st.selectbox("Profil hedef saati",SLOTS[1:],key="profile_hour")
    src0=SLOTS[SLOTS.index(tgt)-1]
    if len(days)>=15:
        trn=days[:-5]; cal=days[-5:]
        mm=learn_hour_model(df,src0,tgt,trn,cal)
        d0=days[-1]
        rr=score_live(mm,d0)
        prof=pd.DataFrame([{
            "Sıra":i+1,"Sayı":c["n"],"C/E":c["pool"],
            "Puan bandı":c.get("band"),"Puan %":round(c.get("pct",0),1),
            "6-adım yol":c["path"],"6-gün yol":c.get("macro6",""),
            "6×6":c.get("micro_macro",""),"Son-4":c["path"][-4:],
            "Dinlenme":c["gap"],"Yolda görünme":c["seen"],
            "Küme":c["cluster_size"],"Rol":c["role"],
            "Baz":round(c["base_score"],4),"Akor":round(c["chord_score"],4)
        } for i,c in enumerate(rr)])
        st.dataframe(prof,use_container_width=True,hide_index=True)

with tab_roads:
    st.subheader("64 Yol Sözlüğü — hedef saate özel")
    tgt=st.selectbox("Yol hedef saati",SLOTS[1:],key="road_hour")
    src0=SLOTS[SLOTS.index(tgt)-1]
    data0=df_to_map(df)
    ti=SLOTS.index(tgt)
    cnt=defaultdict(lambda:[0,0])
    for d0 in days:
        if (fmt(d0),src0) not in data0 or (fmt(d0),tgt) not in data0:
            continue
        A=data0[(fmt(d0),src0)]; Y=data0[(fmt(d0),tgt)]
        for n in range(1,81):
            p=path_before(data0,d0,n,ti)
            pool="C" if n in A else "E"
            cnt[(pool,p)][0]+=int(n in Y); cnt[(pool,p)][1]+=1
    tbl=[]
    for (pool,p),(h,n) in cnt.items():
        tbl.append({"C/E":pool,"6-adım yol":p,"Gözlem":n,"İsabet":h,"Oran":h/n if n else 0,
                    "Dinlenme":gap_from_path(p),"Yolda görünme":p.count("1")})
    if tbl:
        st.dataframe(pd.DataFrame(tbl).sort_values(["Oran","Gözlem"],ascending=[False,False]),
                     use_container_width=True,hide_index=True)

with tab_research:
    st.subheader("Research Mode — 6×6 Mikro–Makro Test")
    st.caption("6 çekiliş mikro yolu, 6 gün makro yolu ve birleşik 6×6 imza geçmişte walk-forward olarak ölçülür; Live Blind sonucu görüldükten sonra geriye dönük değiştirilmez.")

    target = st.selectbox("Analiz hedef saati", SLOTS[1:], key="research_target")
    source = SLOTS[SLOTS.index(target)-1]

    if len(days) >= 16:
        split = st.slider("Development gün sayısı", 10, max(10,len(days)-5), min(20,max(10,len(days)-10)))
        train_days = days[:split]
        test_days = days[split:]
        calibration_days = train_days[-5:] if len(train_days)>=15 else train_days[-3:]
        model_train = train_days[:-len(calibration_days)]

        model=learn_hour_model(df,source,target,model_train,calibration_days)

        out=[]
        for d in test_days:
            if (fmt(d),target) not in df_to_map(df):
                continue
            actual=df_to_map(df)[(fmt(d),target)]
            ranked=score_live(model,d)
            cps=make_coupons(ranked)
            row={"date":fmt(d)}
            for k,cs in cps.items():
                row[k]=len(set(c["n"] for c in cs)&actual)
            out.append(row)

        if out:
            rdf=pd.DataFrame(out)
            c1,c2,c3=st.columns(3)
            for col,key in zip([c1,c2,c3],["A","B","C"]):
                with col:
                    st.metric(f"{key} ortalama", f"{rdf[key].mean():.3f}/7")
                    st.caption(f"3+ = {(rdf[key]>=3).sum()}/{len(rdf)} · max={rdf[key].max()}")
            st.dataframe(rdf, use_container_width=True, hide_index=True)

            st.markdown("#### Saat karakteri")
            note=pd.DataFrame({
                "Ölçü":["Taşıma","Tek","Alt 1–40","L/M/W/H"],
                "Nota":[model["carry_med"],model["odd_med"],model["low_med"],
                        f"{model['band_note']['L']}/{model['band_note']['M']}/{model['band_note']['W']}/{model['band_note']['H']}"]
            })
            st.dataframe(note, hide_index=True)
    else:
        st.info("Research Mode için daha fazla tam gün gerekli.")

with tab_history:
    st.subheader("Kilitli Tahminler")
    hist=get_locked()
    if hist.empty:
        st.info("Henüz kilitli tahmin yok.")
    else:
        show=hist[["created_at","target_date","target_time","model_version","coupon_name","numbers","input_hash"]]
        st.dataframe(show, use_container_width=True, hide_index=True)

st.divider()
st.caption("Not: Bu uygulama istatistiksel araştırma aracıdır. Geçmiş çekilişlerden gelecekteki bağımsız çekilişleri garanti ederek tahmin etmek mümkün değildir.")
