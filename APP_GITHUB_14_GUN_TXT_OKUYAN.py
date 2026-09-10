from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO
from collections import defaultdict, Counter

st.set_page_config(page_title="Hızlı On – Ritim Uzmanı V2", layout="wide")
st.title("Hızlı On – Ritim Uzmanı V2 / Kilitli Olay Motoru")
st.caption("Tek amaç: ritim araştırmalarını aynı PRE-H tanımıyla tekrar üretmek. Her olay çekiliş+sayı kimliğiyle kayıt edilir.")

DATA_SHA256 = "94429a7cad2b38385133232008c51c63aff75a2dcb5a430a5ebc2d280a202c3b"

DATA_FILE = "HIZLI_ON_25_08_2026_07_09_2026_TAM_14_GUN.txt"


# -----------------------------
# 1) VERİ
# -----------------------------
@st.cache_data
def load_data():
    rows = []
    data_path = Path(DATA_FILE)
    if not data_path.exists():
        st.error(f"GitHub reposunda veri dosyası bulunamadı: {DATA_FILE}")
        st.stop()
    data_text = data_path.read_text(encoding="utf-8")
    for line in data_text.splitlines():
        line = line.strip()
        if not line:
            continue
        p = line.split(";")
        if len(p) != 3:
            continue
        draw = int(p[0])
        dt = pd.to_datetime(p[1], dayfirst=True, errors="coerce")
        nums = sorted({int(x) for x in p[2].split(",") if x.strip()})
        if pd.isna(dt) or len(nums) != 20 or min(nums) < 1 or max(nums) > 80:
            continue
        rows.append((draw, dt, nums))
    df = pd.DataFrame(rows, columns=["draw","dt","nums"]).sort_values(["dt","draw"]).reset_index(drop=True)
    df["date"] = df["dt"].dt.date
    df["day_idx"] = df.groupby("date").cumcount()
    return df

@st.cache_data
def build_matrix(df):
    X = np.zeros((len(df), 80), dtype=np.uint8)
    for i, nums in enumerate(df["nums"]):
        X[i, np.asarray(nums, dtype=int)-1] = 1
    return X

df = load_data()
X = build_matrix(df)
dates = df["date"].to_numpy()
day_idx = df["day_idx"].to_numpy()

# Same-day H lookup. If Hk crosses day boundary => unavailable.
def hbit(t, n0, k):
    j = t-k
    if j < 0 or dates[j] != dates[t]:
        return None
    return int(X[j, n0])

def hseq(t, n0, max_h=100):
    out = {}
    for k in range(1, max_h+1):
        v = hbit(t,n0,k)
        if v is None:
            break
        out[k] = v
    return out

def age_since_last(t, n0):
    """PRE-H age in draw-distance: H1 hit => age=1, H2 hit with H1=0 => age=2."""
    for k in range(1, int(day_idx[t])+1):
        if X[t-k,n0]:
            return k
    return None

def previous_hit_offsets(t, n0, max_hits=12):
    offs=[]
    for k in range(1, int(day_idx[t])+1):
        if X[t-k,n0]:
            offs.append(k)
            if len(offs) >= max_hits:
                break
    return offs

# -----------------------------
# 2) KANONİK RİTİM TANIMLARI
# -----------------------------
DEFS = {
    "R1": {
        "name":"Temiz 4'lük sabit ritim kapısı",
        "rule":"H12=1,H8=1,H4=1; H11-H9,H7-H5,H3-H1=0",
        "note":"H0 sadece etiket/sonuçtur; seçim PRE-H ile yapılır."
    },
    "R2_NEW": {
        "name":"Yeni doğmuş 2'lik ritim",
        "rule":"H6=1,H4=1,H2=1; H12-H7=0 ve H5,H3,H1=0",
        "note":"Eski 2'lik zinciri H8+ bölgesinden taşınmaz."
    },
    "R3_1414": {
        "name":"1→4→1 geçmişi, hedefte 4 dönüş kapısı",
        "rule":"Son üç gerçekleşmiş görünme aralığı 1,4,1 ve hedef PRE-H yaşı=4",
        "note":"Gerçek görünme aralıkları kullanılır; H0 sonucu kurala dahil edilmez."
    },
    "R4_121_SLEEP_7_9": {
        "name":"1→2→1 hızlı titreşim + 7–9 dönüş koridoru",
        "rule":"Son üç gerçekleşmiş görünme aralığı 1,2,1 ve hedef PRE-H yaşı 7..9",
        "note":"Uyku koridoru yalnız bu yaşam geçmişi içinde test edilir."
    }
}

def rule_R1(t,n0):
    if day_idx[t] < 12: return False
    ones={12,8,4}
    for k in range(1,13):
        v=hbit(t,n0,k)
        if v is None: return False
        if (k in ones and v!=1) or (k not in ones and v!=0):
            return False
    return True

def rule_R2_NEW(t,n0):
    if day_idx[t] < 12: return False
    ones={6,4,2}
    for k in range(1,13):
        v=hbit(t,n0,k)
        if v is None: return False
        if (k in ones and v!=1) or (k not in ones and v!=0):
            return False
    return True

def actual_prev_gaps_and_age(t,n0):
    offs=previous_hit_offsets(t,n0,max_hits=5)
    if len(offs) < 4:
        return None, None
    age=offs[0]
    # chronological actual hits: oldest -> newest from offsets offs[3],offs[2],offs[1],offs[0]
    gaps=[offs[2]-offs[3], offs[1]-offs[2], offs[0]-offs[1]]
    # offsets decrease toward present, so differences are negative; absolute draw distances:
    gaps=[abs(x) for x in gaps]
    return gaps, age

def rule_R3(t,n0):
    gaps,age=actual_prev_gaps_and_age(t,n0)
    return gaps == [1,4,1] and age == 4

def rule_R4(t,n0):
    gaps,age=actual_prev_gaps_and_age(t,n0)
    return gaps == [1,2,1] and age in (7,8,9)

RULES={"R1":rule_R1,"R2_NEW":rule_R2_NEW,"R3_1414":rule_R3,"R4_121_SLEEP_7_9":rule_R4}

@st.cache_data
def build_event_ledger(df):
    rec=[]
    for t in range(len(df)):
        for n0 in range(80):
            matched=[]
            for rid,fn in RULES.items():
                if fn(t,n0):
                    matched.append(rid)
            if not matched:
                continue
            offs=previous_hit_offsets(t,n0,12)
            prev_gaps=[]
            if len(offs)>=2:
                prev_gaps=[offs[i]-offs[i+1] for i in range(len(offs)-1)]
            row={
                "event_id":f"{int(df.iloc[t].draw)}-{n0+1:02d}",
                "draw":int(df.iloc[t].draw),
                "dt":df.iloc[t]["dt"],
                "date":df.iloc[t]["date"],
                "day_idx":int(df.iloc[t]["day_idx"]),
                "number":n0+1,
                "REAL20":int(X[t,n0]),
                "NEGATIVE60":int(1-X[t,n0]),
                "age":age_since_last(t,n0),
                "rules":"|".join(matched),
                "prev_hit_offsets":",".join(map(str,offs)),
                "prev_gaps":",".join(map(str,prev_gaps)),
            }
            for k in range(1,101):
                v=hbit(t,n0,k)
                row[f"H{k}"] = np.nan if v is None else v
            rec.append(row)
    return pd.DataFrame(rec)

ledger = build_event_ledger(df)

# -----------------------------
# 3) ÖZEL SABİT RİTİM KAPILARI / GÖÇ ARAŞTIRMA ALTYAPISI
# -----------------------------
@st.cache_data
def fixed_rhythm_gates(df, min_gap=1, max_gap=12, min_repeats=3):
    """
    Canonical fixed-rhythm gate:
    PRE-H last min_repeats actual gaps are all g AND current age==g.
    Target result is REAL20 label only.
    """
    out=[]
    for t in range(len(df)):
        for n0 in range(80):
            offs=previous_hit_offsets(t,n0,max_hits=min_repeats+2)
            if len(offs) < min_repeats+1:
                continue
            age=offs[0]
            gaps=[offs[i]-offs[i+1] for i in range(len(offs)-1)]
            if len(gaps) < min_repeats:
                continue
            for g in range(min_gap,max_gap+1):
                if age == g and gaps[:min_repeats] == [g]*min_repeats:
                    out.append({
                        "event_id":f"{int(df.iloc[t].draw)}-{n0+1:02d}-G{g}",
                        "draw":int(df.iloc[t].draw),
                        "dt":df.iloc[t]["dt"],
                        "date":df.iloc[t]["date"],
                        "number":n0+1,
                        "gap":g,
                        "repeats":min_repeats,
                        "REAL20":int(X[t,n0]),
                        "age":age,
                        "prev_gaps":",".join(map(str,gaps[:8]))
                    })
    return pd.DataFrame(out)

fixed = fixed_rhythm_gates(df)

def rate_table(z, cols):
    if z.empty: return pd.DataFrame()
    g=z.groupby(cols, dropna=False)["REAL20"].agg(["size","sum","mean"]).reset_index()
    g=g.rename(columns={"size":"events","sum":"REAL20","mean":"rate"})
    g["rate_pct"]=(100*g["rate"]).round(2)
    return g

# -----------------------------
# UI
# -----------------------------
tabs = st.tabs([
    "Veri Kilidi",
    "Tanım Kütüğü",
    "R1–R4 Olay Defteri",
    "R1–R4 Performans",
    "Sabit Ritim Kapıları",
    "Özel PRE-H Sorgu",
    "Walk-Forward",
    "CSV Dışa Aktar"
])

with tabs[0]:
    st.subheader("GitHub veri kilidi")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Çekiliş", f"{len(df):,}")
    c2.metric("Gün", df["date"].nunique())
    c3.metric("Her çekiliş", "20 sayı")
    c4.metric("Aday evreni", f"{len(df)*80:,}")
    st.write(f"**Aralık:** {df['dt'].min()} → {df['dt'].max()}")
    st.code(f"SHA256: {DATA_SHA256}")
    day_counts=df.groupby("date").size().reset_index(name="draws")
    st.dataframe(day_counts, use_container_width=True)
    if len(df)==3038 and df["date"].nunique()==14 and day_counts["draws"].eq(217).all():
        st.success("KİLİT OK: 14 gün × 217 = 3.038 çekiliş.")
    else:
        st.error("GitHub veri kilidi beklenen 14×217 yapısıyla uyuşmuyor.")

with tabs[1]:
    st.subheader("Kanonik tanımlar")
    st.warning("Bu tanımlar değişirse araştırma versiyonu değişmiş sayılır. Eski oranlarla karıştırma.")
    for k,v in DEFS.items():
        st.markdown(f"### {k} — {v['name']}")
        st.code(v["rule"])
        st.caption(v["note"])
    st.markdown("**Temel H kuralı:** H1 hedef çekilişten hemen önceki çekiliştir. Gün sınırını aşan H bilgisi kullanılmaz. H0 hiçbir seçim kuralında kullanılmaz; sadece REAL20/NEGATIVE60 etiketi oluşturur.")

with tabs[2]:
    st.subheader("Olay defteri")
    rule=st.selectbox("Ritim", list(DEFS.keys()))
    z=ledger[ledger["rules"].str.contains(rule, regex=False)].copy()
    st.write(f"**{len(z)} olay | REAL20 {int(z.REAL20.sum())} | %{100*z.REAL20.mean():.2f}**" if len(z) else "Olay yok")
    showcols=["event_id","draw","dt","number","REAL20","age","rules","prev_hit_offsets","prev_gaps"]+[f"H{i}" for i in range(1,13)]
    st.dataframe(z[showcols], use_container_width=True, height=500)
    st.download_button("Bu olayları CSV indir", z.to_csv(index=False).encode("utf-8-sig"), f"{rule}_event_ledger.csv","text/csv")

with tabs[3]:
    st.subheader("R1–R4 REAL20 / NEGATIVE60")
    rows=[]
    for rid in DEFS:
        z=ledger[ledger["rules"].str.contains(rid, regex=False)]
        rows.append({
            "rule":rid,"events":len(z),"REAL20":int(z.REAL20.sum()) if len(z) else 0,
            "NEGATIVE60":int((1-z.REAL20).sum()) if len(z) else 0,
            "rate_pct":round(100*z.REAL20.mean(),2) if len(z) else np.nan
        })
    st.dataframe(pd.DataFrame(rows),use_container_width=True)
    rid=st.selectbox("Gün dayanıklılığı",list(DEFS.keys()),key="daily")
    z=ledger[ledger["rules"].str.contains(rid, regex=False)]
    daily=rate_table(z,["date"])
    st.dataframe(daily,use_container_width=True)
    if not daily.empty:
        st.line_chart(daily.set_index("date")["rate_pct"])

with tabs[4]:
    st.subheader("Sabit ritim kapıları")
    st.caption("Son 3 gerçek görünme aralığı g,g,g ve hedef PRE-H yaşı g ise aday kapısıdır. H0 sadece sonuç etiketi.")
    tbl=rate_table(fixed,["gap"])
    st.dataframe(tbl,use_container_width=True)
    if not fixed.empty:
        g=st.selectbox("Gap seç",sorted(fixed.gap.unique()))
        z=fixed[fixed.gap==g]
        st.dataframe(rate_table(z,["date"]),use_container_width=True)
        st.dataframe(z,use_container_width=True,height=400)

with tabs[5]:
    st.subheader("Özel PRE-H sorgu")
    st.caption("Yeni hipotezleri tanımı bozmadan burada test et. Örn. H44=1, F24 vb.")
    rid=st.selectbox("Ana ritim",list(DEFS.keys()),key="custom_rule")
    z=ledger[ledger["rules"].str.contains(rid,regex=False)].copy()
    h=st.number_input("H basamağı",1,100,44,1)
    val=st.selectbox("H değeri",[1,0])
    if f"H{int(h)}" in z:
        q=z[z[f"H{int(h)}"]==val]
        a,b=st.columns(2)
        a.metric("Ana grup",f"{int(z.REAL20.sum())}/{len(z)} = %{100*z.REAL20.mean():.2f}" if len(z) else "-")
        b.metric("Filtreli",f"{int(q.REAL20.sum())}/{len(q)} = %{100*q.REAL20.mean():.2f}" if len(q) else "-")
        st.dataframe(rate_table(q,["date"]),use_container_width=True)
        st.dataframe(q[["event_id","draw","dt","number","REAL20",f"H{int(h)}","age"]],use_container_width=True)

with tabs[6]:
    st.subheader("Expanding walk-forward – sabit H kapısı seçimi")
    st.caption("Her test gününde yalnız önceki günler görünür. Ana ritim içinde H13–H100 basamaklarından geçmişte en iyi REAL20 oranına sahip H=1 koşulu seçilir.")
    rid=st.selectbox("Ana ritim",["R1","R2_NEW"],key="wf_rule")
    min_support=st.slider("Minimum geçmiş destek",5,50,20)
    z=ledger[ledger["rules"].str.contains(rid,regex=False)].copy()
    all_days=sorted(z["date"].unique())
    res=[]
    for di in range(1,len(all_days)):
        train_days=all_days[:di]
        test_day=all_days[di]
        tr=z[z.date.isin(train_days)]
        te=z[z.date==test_day]
        candidates=[]
        for h in range(13,101):
            col=f"H{h}"
            q=tr[tr[col]==1]
            if len(q)>=min_support:
                candidates.append((q.REAL20.mean(),len(q),h))
        if not candidates:
            continue
        candidates.sort(reverse=True)
        _,support,best_h=candidates[0]
        qtest=te[te[f"H{best_h}"]==1]
        res.append({
            "test_date":test_day,"selected_H":best_h,"train_support":support,
            "test_events":len(qtest),"test_REAL20":int(qtest.REAL20.sum()),
            "test_rate_pct":round(100*qtest.REAL20.mean(),2) if len(qtest) else np.nan
        })
    wf=pd.DataFrame(res)
    st.dataframe(wf,use_container_width=True)
    if not wf.empty:
        ev=wf.test_events.sum(); hit=wf.test_REAL20.sum()
        st.metric("Toplam kör sonuç",f"{hit}/{ev} = %{100*hit/ev:.2f}" if ev else "-")

with tabs[7]:
    st.subheader("Araştırma kütüğünü dışa aktar")
    st.download_button("R1–R4 tam olay defteri",ledger.to_csv(index=False).encode("utf-8-sig"),"RITIM_R1_R4_EVENT_LEDGER.csv","text/csv")
    st.download_button("Sabit ritim kapıları",fixed.to_csv(index=False).encode("utf-8-sig"),"SABIT_RITIM_GATE_LEDGER.csv","text/csv")
    defs_df=pd.DataFrame([{"id":k,**v} for k,v in DEFS.items()])
    st.download_button("Tanım kütüğü",defs_df.to_csv(index=False).encode("utf-8-sig"),"RITIM_TANIM_KUTUGU.csv","text/csv")

st.divider()
st.markdown("""
### Araştırma disiplini
- H0 sonuçtur; özellik değildir.
- Gün sınırını aşan PRE-H kullanılmaz.
- Her olay `çekiliş-sayı` kimliğiyle saklanır.
- Alt grupların toplamı ana grubu birebir geri vermelidir.
- Keşif sonucu tek başına kural değildir; gün bölme + expanding walk-forward gerekir.
- Uygulama kupon motoru değil, önce **ritim uzmanının ölçüm laboratuvarıdır**.
""")
