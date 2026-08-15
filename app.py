
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import hashlib
import json

st.set_page_config(page_title="Sayı Laboratuvarı", layout="wide", page_icon="🎼")

DB_PATH = Path("predictions_v2.db")
SLOTS = ["23:02","23:07","23:12","23:17","23:22","23:27",
         "23:32","23:37","23:42","23:47","23:52","23:57"]

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
            base[pool][0] += hit
            base[pool][1] += 1
            feats = [
                ("path", p),
                ("p4", p[-4:]),
                ("gap", gap_from_path(p)),
                ("seen", p.count("1")),
                ("week", weekly_flag(data, d, n, target)),
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
            sc = (
                .30*shrink(sig[(pool,"path",p)], pr, 25)
                + .18*shrink(sig[(pool,"p4",p[-4:])], pr, 23)
                + .12*shrink(sig[(pool,"gap",gap_from_path(p))], pr, 25)
                + .10*shrink(sig[(pool,"seen",p.count("1"))], pr, 25)
                + .10*shrink(sig[(pool,"week",weekly_flag(data,d,n,target))], pr, 28)
                + .05*shrink(sig[(pool,"odd",n%2)], pr, 30)
                + .05*shrink(sig[(pool,"low",int(n<=40))], pr, 30)
                + .10*shrink(num[(pool,n)], pr, 22)
            )
            out.append({
                "n": n,
                "pool": pool,
                "path": p,
                "gap": gap_from_path(p),
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

            # Dinlenme: destekleyici, baskın değil
            rest_bonus = 0.008 if c["gap"] in (3,4,6) else 0.0

            c["role"] = role_name
            c["cluster_size"] = all_cluster[p]
            c["chord_score"] = (
                .18*c["base_score"]
                + .20*exact
                + .12*p4
                + .14*size
                + .18*pathsize
                + .10*notesize
                + .08*rr
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
        target_date,target_time,"v2.0-orchestra",
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

st.title("🎼 Sayı Laboratuvarı v2 — Orkestra Motoru")
st.caption("Saat karakteri + 64 yol sözlüğü + 80 sayı profili + nota20 + akor + Live Blind.")

with st.sidebar:
    st.header("Veri")
    uploaded = st.file_uploader("TXT veya CSV yükle", type=["txt","csv"])
    st.markdown("Beklenen TXT biçimi: `çekiliş_no | GG.AA.YYYY SS:DD | 20 sayı`")

if uploaded is None:
    st.info("Başlamak için soldan veri dosyası yükleyin.")
    st.stop()

try:
    if uploaded.name.lower().endswith(".csv"):
        raw = pd.read_csv(uploaded)
        df = parse_csv(raw)
    else:
        text = uploaded.read().decode("utf-8")
        df = parse_pipe_text(text)
except Exception as e:
    st.error(f"Veri okunamadı: {e}")
    st.stop()

if df.empty:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

df["date_dt"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
df = df.sort_values(["date_dt","time"]).drop(columns=["date_dt"]).reset_index(drop=True)

days = complete_days(df)

tab_live, tab_hours, tab_numbers, tab_roads, tab_research, tab_history = st.tabs(["🔒 Live Blind","🎼 Saat Karakterleri","🧬 80 Sayı Profili","🛣️ 64 Yol Sözlüğü","🔬 Research","📚 Kilit Geçmişi"])

with tab_live:
    st.subheader("Live Blind Mode")
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

            st.markdown("### Sonuç doğrulama")
            result_text = st.text_input("Gerçek 20 sayı (boşlukla)")
            if result_text:
                try:
                    actual=set(map(int,result_text.replace(","," ").split()))
                    if len(actual)!=20:
                        st.warning("Tam 20 farklı sayı girin.")
                    else:
                        locked=get_locked(target_date,target_time)
                        if locked.empty:
                            st.warning("Önce kuponları kilitleyin.")
                        else:
                            for _,r in locked.sort_values("coupon_name").iterrows():
                                nums=set(map(int,r["numbers"].split()))
                                hits=sorted(nums&actual)
                                st.write(f"**{r['coupon_name']}: {len(hits)}/7** — {hits}")
                except Exception as e:
                    st.error(str(e))

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
            "6-adım yol":c["path"],"Son-4":c["path"][-4:],
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
    st.subheader("Research Mode")
    st.caption("Geçmiş veriyi incelemek içindir. Buradaki sonuçlar Live Blind tahmini geriye dönük değiştirmemeli.")

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
