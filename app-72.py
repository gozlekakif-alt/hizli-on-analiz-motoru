# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile, hashlib, math, random
from collections import Counter, defaultdict
from dataclasses import dataclass

st.set_page_config(page_title="Hızlı On Birleşme Kupon Motoru", layout="wide")
st.title("🎯 Hızlı On — 0/3–3/3 Geçiş / Son-6 Birleşme Motoru")
st.caption("Kaynak: repo içindeki ham veri.txt • İlk3 → İkinci3 → Son6 canlı birleşme")

FIRST6 = ["02","07","12","17","22","27"]
TARGETS = ["32","37","42","47","52","57"]
ALL_MINS = FIRST6 + TARGETS
TRAIN_START = pd.Timestamp("2026-08-25")
TRAIN_END   = pd.Timestamp("2026-09-07 23:59:59")

def parse_draw_text(text_or_path):
    p = Path(str(text_or_path))
    if p.exists():
        txt = p.read_text(encoding="utf-8-sig", errors="replace")
    else:
        txt = str(text_or_path)

    rows = []
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) != 3:
            continue
        try:
            draw_id = int(parts[0].strip())
            dt = pd.to_datetime(parts[1].strip(), dayfirst=True)
            nums = sorted(set(int(x.strip()) for x in parts[2].split(",") if x.strip()))
        except Exception:
            continue
        if len(nums) == 20 and all(1 <= x <= 80 for x in nums):
            rows.append((draw_id, dt, nums))

    if not rows:
        raise ValueError("Geçerli çekiliş satırı bulunamadı.")

    df = pd.DataFrame(rows, columns=["draw_id","time","numbers"])
    return df.sort_values(["time","draw_id"]).drop_duplicates("draw_id").reset_index(drop=True)

def restrict_training(df):
    x = df[(df.time >= TRAIN_START) & (df.time <= TRAIN_END)].copy()
    if x.empty:
        raise ValueError("veri.txt içinde 25.08.2026–07.09.2026 eğitim aralığı bulunamadı.")
    return x.reset_index(drop=True)

def complete_hour_blocks(df):
    tmp = defaultdict(dict)
    for _, r in df.iterrows():
        date = r.time.strftime("%d.%m.%Y")
        hour = r.time.strftime("%H")
        minute = r.time.strftime("%M")
        if minute in ALL_MINS:
            tmp[(date,hour)][minute] = (int(r.draw_id), set(r.numbers))
    return {k:v for k,v in tmp.items() if all(m in v for m in ALL_MINS)}

def period_of(date_str):
    d = pd.to_datetime(date_str, dayfirst=True)
    if d <= pd.Timestamp("2026-08-28 23:59:59"):
        return "D"
    if d <= pd.Timestamp("2026-08-31 23:59:59"):
        return "V1"
    return "R"

def classify_families(hour_draws):
    first_sets = [hour_draws[m][1] for m in FIRST6]
    fam = {}
    for n in range(1,81):
        a = sum(n in first_sets[i] for i in range(3))
        b = sum(n in first_sets[i] for i in range(3,6))
        fam[n] = f"{a}/3→{b}/3"
    return fam

def build_training_rows(df):
    blocks = complete_hour_blocks(restrict_training(df))
    rows = []
    for (date,hour), hd in sorted(blocks.items()):
        fam = classify_families(hd)
        prior = {n:"" for n in range(1,81)}
        for minute in TARGETS:
            actual = hd[minute][1]
            for n in range(1,81):
                rows.append({
                    "date": date, "hour": hour, "num": n,
                    "family": fam[n], "minute": minute,
                    "prior": prior[n], "hit": int(n in actual),
                    "period": period_of(date),
                })
            for n in range(1,81):
                prior[n] += "1" if n in actual else "0"
    return pd.DataFrame(rows), blocks

def wilson_lower(h, n, z):
    if n <= 0:
        return 0.0
    p = h / n
    return (p + z*z/(2*n) - z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)

@dataclass
class Branch:
    minute: str
    family: str
    prior: str
    n: int
    hits: int
    rate: float
    d_rate: float
    v1_rate: float
    r_rate: float
    lb95: float
    lb80: float
    tier: str

def learn_branches(train_rows):
    model = {}
    for (minute,family,prior), g in train_rows.groupby(["minute","family","prior"]):
        n = len(g)
        hits = int(g.hit.sum())
        rate = hits/n
        prs = {}
        for per in ["D","V1","R"]:
            z = g[g.period == per]
            prs[per] = float(z.hit.mean()) if len(z) else 0.25
        lb95 = wilson_lower(hits,n,1.96)
        lb80 = wilson_lower(hits,n,1.282)
        min_period = min(prs.values())

        tier = "OFF"
        if n >= 30 and lb95 > 0.25 and min_period >= 0.25:
            tier = "CORE"
        elif n >= 40 and lb80 > 0.25 and min_period >= 0.24:
            tier = "SUPPORT"

        model[(minute,family,prior)] = Branch(
            minute,family,prior,n,hits,rate,
            prs["D"],prs["V1"],prs["R"],lb95,lb80,tier
        )
    return model

def branch_table(model):
    rows=[]
    for b in model.values():
        if b.tier == "OFF":
            continue
        rows.append({
            "target":f":{b.minute}",
            "family":b.family,
            "prior":b.prior if b.prior else "∅",
            "tier":b.tier,
            "n":b.n,
            "hits":b.hits,
            "rate":b.rate,
            "D":b.d_rate,
            "V1":b.v1_rate,
            "R":b.r_rate,
            "lb95":b.lb95,
            "lb80":b.lb80,
        })
    return pd.DataFrame(rows)

def _seed(*parts):
    raw="|".join(map(str,parts))
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],16)

def produce_hour(hour_draws, date_str, hour, model, variants=5):
    fam=classify_families(hour_draws)
    prior={n:"" for n in range(1,81)}
    out=[]

    for minute in TARGETS:
        groups=defaultdict(list)
        binfo={}
        for n in range(1,81):
            key=(minute,fam[n],prior[n])
            b=model.get(key)
            if b and b.tier!="OFF":
                gkey=(fam[n],prior[n])
                groups[gkey].append(n)
                binfo[gkey]=b

        def gsort(g):
            b=binfo[g]
            tier=2 if b.tier=="CORE" else 1
            conf=b.lb95 if b.tier=="CORE" else b.lb80
            return (tier,conf,b.rate,b.n)

        ordered=sorted(groups,key=gsort,reverse=True)
        candidate_count=sum(len(groups[g]) for g in ordered)

        if candidate_count>=4:
            for v in range(1,variants+1):
                rng=random.Random(_seed("BIRLESME-V2",date_str,hour,minute,v))
                bags={g:list(groups[g]) for g in ordered}
                for g in bags:
                    rng.shuffle(bags[g])

                chosen=[]
                group_count=Counter()
                fam_count=Counter()

                while len(chosen)<6:
                    added=False
                    for g in ordered:
                        family,_=g
                        if group_count[g]>=2 or fam_count[family]>=3 or not bags[g]:
                            continue
                        chosen.append(bags[g].pop())
                        group_count[g]+=1
                        fam_count[family]+=1
                        added=True
                        if len(chosen)==6:
                            break
                    if not added:
                        break

                if len(chosen)>=4:
                    out.append({
                        "date":date_str,
                        "hour":hour,
                        "minute":minute,
                        "variant":v,
                        "coupon":sorted(chosen),
                        "coupon_size":len(chosen),
                        "candidate_count":candidate_count
                    })

        actual=hour_draws[minute][1]
        for n in range(1,81):
            prior[n]+="1" if n in actual else "0"

    return out

def day_blocks(df):
    return complete_hour_blocks(df)

def backtest_day(train_df,test_df,variants=5):
    train_rows,train_blocks=build_training_rows(train_df)
    model=learn_branches(train_rows)
    test_blocks=day_blocks(test_df)

    rows=[]
    for (date,hour),hd in sorted(test_blocks.items()):
        generated=produce_hour(hd,date,hour,model,variants)
        for x in generated:
            actual=hd[x["minute"]][1]
            hitnums=sorted(set(x["coupon"]) & actual)
            rows.append({
                "date":date,
                "time":f"{hour}:{x['minute']}",
                "variant":x["variant"],
                "coupon_size":x["coupon_size"],
                "coupon":"-".join(map(str,x["coupon"])),
                "hits":len(hitnums),
                "hit_numbers":"-".join(map(str,hitnums)),
                "candidate_count":x["candidate_count"],
            })
    return pd.DataFrame(rows),model,train_blocks,test_blocks

def save_upload(upload):
    f=tempfile.NamedTemporaryFile(delete=False,suffix=".txt")
    f.write(upload.getbuffer())
    f.close()
    return f.name

# ---------------- UI ----------------

TRAIN_FILE="veri.txt"
DEFAULT_TEST_FILE="10_09_2026_GUNLUK_KUTUK.txt"

st.sidebar.header("Veri kaynağı")

repo_train=Path(TRAIN_FILE)
if repo_train.exists():
    st.sidebar.success("✅ veri.txt bulundu")
    train_path=str(repo_train)
else:
    train_upload=st.sidebar.file_uploader("14 günlük veri.txt yükle",type=["txt"],key="train")
    train_path=save_upload(train_upload) if train_upload else None

repo_test=Path(DEFAULT_TEST_FILE)
test_upload=st.sidebar.file_uploader("Test günü TXT",type=["txt"],key="test")
if test_upload is not None:
    test_path=save_upload(test_upload)
elif repo_test.exists():
    test_path=str(repo_test)
else:
    test_path=None

if train_path is None:
    st.error("Repo kökünde `veri.txt` bulunamadı. Dosyayı repo'ya koy veya soldan yükle.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_train(path):
    raw=parse_draw_text(path)
    train=restrict_training(raw)
    rows,blocks=build_training_rows(train)
    model=learn_branches(rows)
    return raw,train,rows,blocks,model

try:
    with st.spinner("veri.txt okunuyor ve 14 günlük birleşme motoru kuruluyor..."):
        raw,train,train_rows,train_blocks,model=load_train(train_path)
except Exception as e:
    st.exception(e)
    st.stop()

bt=branch_table(model)
core_n=int((bt.tier=="CORE").sum()) if not bt.empty else 0
support_n=int((bt.tier=="SUPPORT").sum()) if not bt.empty else 0

c1,c2,c3,c4,c5=st.columns(5)
c1.metric("veri.txt çekiliş",len(raw))
c2.metric("Eğitim çekiliş",len(train))
c3.metric("Tam saat",len(train_blocks))
c4.metric("CORE",core_n)
c5.metric("SUPPORT",support_n)

if len(train)!=3038:
    st.warning(f"Eğitim aralığında {len(train)} çekiliş bulundu. Beklenen 3038; veri.txt biçimini kontrol et.")

tabs=st.tabs(["🧬 Dallar","🎟️ Kupon Üret","🧪 Gün Testi","📘 Mantık"])

with tabs[0]:
    st.subheader("14 günden öğrenilen birleşme dalları")
    if bt.empty:
        st.warning("CORE/SUPPORT dal bulunamadı.")
    else:
        show=bt.copy()
        for c in ["rate","D","V1","R","lb95","lb80"]:
            show[c]=(100*show[c]).round(2)
        st.dataframe(show.sort_values(["tier","rate","n"],ascending=[True,False,False]),
                     use_container_width=True,hide_index=True)

with tabs[1]:
    st.subheader("Test günündeki saatten kupon üret")
    if test_path is None:
        st.info("Test günü TXT yükle veya repo'ya `10_09_2026_GUNLUK_KUTUK.txt` koy.")
    else:
        test_df=parse_draw_text(test_path)
        blocks=day_blocks(test_df)
        if not blocks:
            st.warning("Tam :02–:57 saat bloğu bulunamadı.")
        else:
            opts=[f"{d} {h}:00" for d,h in sorted(blocks)]
            sel=st.selectbox("Saat",opts)
            date,h00=sel.split()
            hour=h00[:2]
            generated=produce_hour(blocks[(date,hour)],date,hour,model,variants=5)
            if not generated:
                st.warning("Sinyal yok → ABSTAIN")
            else:
                q=pd.DataFrame([{
                    "Hedef":f"{hour}:{x['minute']}",
                    "Varyant":x["variant"],
                    "Boyut":x["coupon_size"],
                    "Aday":x["candidate_count"],
                    "Kolon":" - ".join(map(str,x["coupon"]))
                } for x in generated])
                st.dataframe(q,use_container_width=True,hide_index=True)
                st.download_button("Kuponları CSV indir",
                                   q.to_csv(index=False).encode("utf-8-sig"),
                                   "BIRLESME_KUPONLARI.csv","text/csv")

with tabs[2]:
    st.subheader("Tam gün kör test raporu")
    if test_path is None:
        st.info("Test günü TXT yükle.")
    else:
        test_df=parse_draw_text(test_path)
        report,_,_,test_blocks=backtest_day(train,test_df,variants=5)
        if report.empty:
            st.warning("Motor bu günde kupon üretmedi.")
        else:
            a,b,c,d,e=st.columns(5)
            a.metric("Tam test saati",len(test_blocks))
            b.metric("Toplam kolon",len(report))
            c.metric("3+",int((report.hits>=3).sum()))
            d.metric("4+",int((report.hits>=4).sum()))
            e.metric("5+",int((report.hits>=5).sum()))

            dist=report.hits.value_counts().sort_index()
            dd=pd.DataFrame({
                "İsabet":[f"{i}/6" for i in range(7)],
                "Kolon":[int(dist.get(i,0)) for i in range(7)]
            })
            st.markdown("#### İsabet dağılımı")
            st.dataframe(dd,use_container_width=True,hide_index=True)

            st.markdown("#### 4+ kolonlar")
            st.dataframe(report[report.hits>=4].sort_values(["hits","time"],ascending=[False,True]),
                         use_container_width=True,hide_index=True)

            st.markdown("#### Tüm kolonlar")
            st.dataframe(report,use_container_width=True,hide_index=True)

            st.download_button("Tam raporu CSV indir",
                               report.to_csv(index=False).encode("utf-8-sig"),
                               "BIRLESME_MOTORU_GUN_TEST_RAPORU.csv","text/csv")

with tabs[3]:
    st.markdown("""
### Motor mantığı

- `veri.txt` içindeki 25.08.2026–07.09.2026 aralığı eğitimdir.
- İlk 3: `:02,:07,:12`
- İkinci 3: `:17,:22,:27`
- Geçiş ailesi: `0/3→0/3 ... 3/3→3/3`
- Son 6 hedef: `:32,:37,:42,:47,:52,:57`
- Canlı yol her hedef sonrası güncellenir.
- Aynı geçiş ailesi + canlı yol + hedef dakika hücreleri CORE/SUPPORT olarak öğrenilir.
- Hedef sonucu o hedefi seçmek için kullanılmaz.
- Sinyal yetersizse ABSTAIN.
""")
