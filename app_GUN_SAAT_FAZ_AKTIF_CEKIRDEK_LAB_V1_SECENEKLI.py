from pathlib import Path
from datetime import datetime
import re
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gün–Saat–Faz Aktif Çekirdek LAB V1", page_icon="🧠", layout="wide")
DATA = Path(__file__).with_name("veri.txt")

# ============================================================
# VERİ
# ============================================================
def parse_line(line):
    p=str(line).strip().split(";")
    if len(p)!=4: return None
    try:
        no=int(p[0])
        dt=datetime.strptime(p[1]+" "+p[2], "%d.%m.%Y %H:%M")
        nums=[int(x) for x in re.findall(r"\d+",p[3])]
    except Exception:
        return None
    if len(nums)!=20 or len(set(nums))!=20 or not all(1<=x<=80 for x in nums):
        return None
    return no,dt,sorted(nums)

@st.cache_data(show_spinner=False)
def load(text):
    rows=[]; bad=0
    for x in text.splitlines():
        if not x.strip(): continue
        z=parse_line(x)
        if z is None: bad+=1
        else: rows.append(z)
    df=pd.DataFrame(rows,columns=["No","DT","Nums"])
    if len(df):
        df=(df.drop_duplicates("No",keep="last")
              .sort_values("No").reset_index(drop=True))
    return df,bad

def matrix(df):
    A=np.zeros((len(df),80),dtype=np.int8)
    for i,nums in enumerate(df.Nums):
        A[i,np.asarray(nums)-1]=1
    return A

# ============================================================
# GÜN / REJİM / SAAT / FAZ
# ============================================================
def regime(dt):
    h=dt.hour+dt.minute/60
    if 7<=h<11: return "SABAH"
    if 11<=h<16: return "ÖĞLEN"
    if 16<=h<21: return "AKŞAM"
    return "KAPANIŞ"

def phase(dt):
    # Saatin kendi içindeki iki alt faz:
    # A: xx:02–xx:27, B: xx:32–xx:57.
    return "A" if dt.minute < 30 else "B"

def phase_key(dt):
    return f"{regime(dt)}_{dt.hour:02d}_{phase(dt)}"

def minute_slot(dt):
    # 5 dakikalık slotun saat içindeki sırası.
    return max(0, int(round((dt.minute-2)/5)))

def day_key(dt):
    return pd.Timestamp(dt).date()

# ============================================================
# CANLI GÜN KARAKTERİ
# ============================================================
def live_day_state(df,A,t):
    """Hedef t öncesinde, yalnız bugünün gerçekleşmiş çekilişlerinden durum."""
    target_dt=df.DT.iloc[t] if t < len(df) else df.DT.iloc[t-1]
    day=day_key(target_dt)
    hour=target_dt.hour
    reg=regime(target_dt)
    ph=phase(target_dt)

    idx_day=[j for j in range(t) if day_key(df.DT.iloc[j])==day]
    idx_hour=[j for j in idx_day if df.DT.iloc[j].hour==hour]
    idx_reg=[j for j in idx_day if regime(df.DT.iloc[j])==reg]
    idx_phase=[j for j in idx_hour if phase(df.DT.iloc[j])==ph]

    def freq(ix):
        return A[ix].mean(0) if ix else np.zeros(80)

    return {
        "day":day,
        "hour":hour,
        "regime":reg,
        "phase":ph,
        "day_freq":freq(idx_day),
        "reg_freq":freq(idx_reg),
        "hour_freq":freq(idx_hour),
        "phase_freq":freq(idx_phase),
        "n_day":len(idx_day),
        "n_reg":len(idx_reg),
        "n_hour":len(idx_hour),
        "n_phase":len(idx_phase),
    }

# ============================================================
# GEÇMİŞTEN DAVRANIŞ KURALI, BUGÜNDEN SAYI KİMLİĞİ
# ============================================================
FEATURES=[
    "today_hour","today_phase","today_regime","today_day",
    "carry_recent","return_1","return_2","return_3","return_4",
    "same_hour_hist","same_phase_hist","same_slot_hist",
    "band_live","band_trend","pair_support","streak"
]

def number_features(df,A,t,n):
    idx=n-1
    target_dt=df.DT.iloc[t] if t<len(df) else (
        df.DT.iloc[t-1] + pd.Timedelta(minutes=5)
    )
    state=live_day_state(df,A,t)

    # Bugünün canlı kimliği.
    today_hour=float(state["hour_freq"][idx])
    today_phase=float(state["phase_freq"][idx])
    today_reg=float(state["reg_freq"][idx])
    today_day=float(state["day_freq"][idx])

    # Son çekilişten taşıma karakteri.
    carry_cases=carry_hits=0
    for j in range(max(0,t-180),t-1):
        if int(df.No.iloc[j+1])!=int(df.No.iloc[j])+1: continue
        if A[j,idx]:
            carry_cases+=1; carry_hits+=int(A[j+1,idx])
    carry=(carry_hits+2.5)/(carry_cases+10)

    # 1–4 el dinlenip dönüş: yalnız geçmişte gözlenen örüntü.
    ret=[]
    for gap in (1,2,3,4):
        cases=hits=0
        for j in range(max(gap,t-450),t):
            # j hedef, j-gap-1 son görülme varsayımı
            p=j-gap-1
            if p<0: continue
            if A[p,idx]!=1: continue
            if np.any(A[p+1:j,idx]): continue
            cases+=1
            hits+=int(A[j,idx])
        ret.append((hits+1.25)/(cases+5))

    # Aynı saat / aynı faz / aynı 5dk slot geçmiş davranışı.
    def hist_rate(match):
        vals=[]
        for j in range(max(0,t-700),t):
            if match(df.DT.iloc[j]):
                vals.append(A[j,idx])
        return (sum(vals)+2.5)/(len(vals)+10) if vals else .25

    same_hour=hist_rate(lambda d:d.hour==target_dt.hour)
    same_phase=hist_rate(lambda d:d.hour==target_dt.hour and phase(d)==phase(target_dt))
    slot=minute_slot(target_dt)
    same_slot=hist_rate(lambda d:minute_slot(d)==slot)

    # Canlı bant.
    b=idx//10
    hf=state["hour_freq"]
    pf=state["phase_freq"]
    band_live=float(hf[b*10:(b+1)*10].mean())
    band_phase=float(pf[b*10:(b+1)*10].mean())
    band_trend=band_phase-band_live

    # Bugünkü aynı saat içinde birlikte görünme desteği.
    day=state["day"]
    hour=state["hour"]
    ix=[j for j in range(t) if day_key(df.DT.iloc[j])==day and df.DT.iloc[j].hour==hour]
    pair=0.0
    if ix:
        H=A[ix]
        active=np.argsort(-H.mean(0))[:10]
        vals=[]
        for q in active:
            if q==idx: continue
            den=max(float(H[:,q].sum()),1.0)
            vals.append(float((H[:,q]*H[:,idx]).sum())/den)
        pair=float(np.mean(vals)) if vals else 0.0

    streak=0
    for j in range(t-1,-1,-1):
        if A[j,idx]: streak+=1
        else: break

    return {
        "Sayı":n,
        "today_hour":today_hour,
        "today_phase":today_phase,
        "today_regime":today_reg,
        "today_day":today_day,
        "carry_recent":carry,
        "return_1":ret[0],"return_2":ret[1],"return_3":ret[2],"return_4":ret[3],
        "same_hour_hist":same_hour,
        "same_phase_hist":same_phase,
        "same_slot_hist":same_slot,
        "band_live":band_live,
        "band_trend":band_trend,
        "pair_support":pair,
        "streak":streak,
    }

def candidate_table(df,A,t):
    return pd.DataFrame([number_features(df,A,t,n) for n in range(1,81)])

def train_model(df,A,t,lookback=500):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression

    xs=[]; ys=[]
    start=max(120,t-lookback)
    # Eğitim maliyetini kontrollü tut: son 500 hedef.
    for h in range(start,t):
        if h<=0 or int(df.No.iloc[h])!=int(df.No.iloc[h-1])+1: continue
        tab=candidate_table(df,A,h)
        y=A[h].astype(int)
        xs.append(tab[FEATURES].astype(float))
        ys.append(pd.Series(y))
    if not xs: return None
    X=pd.concat(xs,ignore_index=True); y=pd.concat(ys,ignore_index=True)
    if len(X)<400 or y.nunique()<2: return None
    model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=400,C=.12))
    model.fit(X,y)
    return model

def predict(df,A,t,model=None):
    tab=candidate_table(df,A,t)
    if model is None:
        model=train_model(df,A,t)
    tab=tab.copy()
    if model is None:
        tab["P"]=(
            .25*tab.today_hour+.18*tab.today_phase+.10*tab.today_regime+
            .10*tab.carry_recent+.12*tab.same_phase_hist+.08*tab.same_slot_hist+
            .07*tab.pair_support+.10*tab.band_live
        )
        trained=False
    else:
        tab["P"]=model.predict_proba(tab[FEATURES].astype(float))[:,1]
        trained=True

    tab=tab.sort_values(["P","today_hour","today_phase"],ascending=[False,False,False]).reset_index(drop=True)

    # Çekirdek boyunu zorla sabitleme: puan dağılımına göre 3–7.
    top=tab.P.to_numpy()
    if len(top)>=8:
        gaps=top[:7]-top[1:8]
        k=int(np.argmax(gaps)+1)
        k=max(3,min(k,7))
    else:
        k=5
    core=tab.head(k).Sayı.astype(int).tolist()
    return core,tab,trained

# ============================================================
# GÜN-İÇİ KÖR WALK-FORWARD
# ============================================================
def walkforward(df,A,n=750):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression

    valid=[t for t in range(140,len(df)) if int(df.No.iloc[t])==int(df.No.iloc[t-1])+1]
    valid=valid[-min(n,len(valid)):]

    rows=[]
    # Her hedefte sadece geçmiş; performans için model 60 hedefte bir yeniden eğitilir,
    # ama eğitim kesimi hiçbir zaman hedefi veya geleceği içermez.
    model=None; trained_at=None
    for pos,t in enumerate(valid):
        if model is None or trained_at is None or t-trained_at>=60:
            model=train_model(df,A,t,lookback=420)
            trained_at=t

        core,tab,trained=predict(df,A,t,model)
        actual=set((np.where(A[t]>0)[0]+1).tolist())
        hits=sorted(set(core)&actual)

        state=live_day_state(df,A,t)
        rows.append({
            "Sıra":pos+1,
            "Çekiliş":int(df.No.iloc[t]),
            "Tarih/Saat":df.DT.iloc[t].strftime("%d.%m.%Y %H:%M"),
            "Rejim":regime(df.DT.iloc[t]),
            "Saat":df.DT.iloc[t].hour,
            "Faz":phase(df.DT.iloc[t]),
            "Bugün saat içi gözlem":state["n_hour"],
            "Bugün faz içi gözlem":state["n_phase"],
            "Çekirdek boyu":len(core),
            "İsabet":len(hits),
            "Tam çekirdek":len(hits)==len(core),
            "Çekirdek":"-".join(map(str,core)),
            "Tutan":"-".join(map(str,hits)),
            "Öğrenme":trained,
            "Sızıntı":"TEMİZ",
        })
    return pd.DataFrame(rows)

# ============================================================
# UI
# ============================================================
st.title("🧠 GÜN × SAAT × FAZ AKTİF ÇEKİRDEK — LAB V1 SEÇENEKLİ")
st.info(
    "Geçmiş günlerin SAYILARINI ezberlemez; geçmişten davranış kuralını öğrenir. "
    "Bugünün gerçekleşmiş çekilişlerinden bugünkü aktif çekirdeği oluşturur."
)

if not DATA.exists():
    st.error("veri.txt bu .py ile aynı klasörde olmalı.")
    st.stop()

df,bad=load(DATA.read_text(encoding="utf-8",errors="ignore"))
if len(df)<250:
    st.error(f"Veri yetersiz: {len(df)}")
    st.stop()
A=matrix(df)

c1,c2,c3,c4=st.columns(4)
c1.metric("Havuz",len(df))
c2.metric("Son çekiliş",int(df.No.iloc[-1]))
c3.metric("Son rejim",regime(df.DT.iloc[-1]))
c4.metric("Son faz",phase_key(df.DT.iloc[-1]))

tabs=st.tabs(["🧪 GÜN-İÇİ KÖR TEST","🎯 BUGÜNÜN AKTİF ÇEKİRDEĞİ","📊 SAAT/FAZ KARAKTERİ"])

with tabs[0]:
    st.subheader("Gün-içi kör walk-forward")
    test_n = st.select_slider("Test adedi", options=[250,500,750], value=250)
    st.caption(
        "Örnek: hedef 08:32 ise model o gün yalnız 08:27'ye kadar olan sonuçları görür. "
        "08:32 ve sonrası bugünkü karaktere sızamaz."
    )
    if "core_wf" not in st.session_state: st.session_state.core_wf=None
    if st.button("🚀 TESTİ BAŞLAT",type="primary",use_container_width=True):
        with st.spinner(f"{test_n} çekilişlik Gün–Saat–Faz kör testi çalışıyor..."):
            st.session_state.core_wf=walkforward(df,A,test_n)

    wf=st.session_state.core_wf
    if isinstance(wf,pd.DataFrame) and len(wf):
        pred=int(wf["Çekirdek boyu"].sum()); hit=int(wf["İsabet"].sum())
        a,b,c,d=st.columns(4)
        a.metric("Test",len(wf))
        b.metric("Çekirdek sayı doğruluğu",f"%{100*hit/max(pred,1):.2f}")
        c.metric("Ort. çekirdek",f"{wf['Çekirdek boyu'].mean():.2f}")
        d.metric("Tam çekirdek",int(wf["Tam çekirdek"].sum()))

        by=wf.groupby(["Rejim","Faz"]).agg(
            Test=("İsabet","size"),Tahmin=("Çekirdek boyu","sum"),
            Doğru=("İsabet","sum"),Tam=("Tam çekirdek","sum")
        ).reset_index()
        by["Doğruluk %"]=100*by.Doğru/by.Tahmin.clip(lower=1)
        st.dataframe(by,use_container_width=True,hide_index=True)

        # Canlı karakterin oluşması için saat içinde kaç gözlem gerektiğini göster.
        maturity=pd.cut(wf["Bugün saat içi gözlem"],[-1,1,3,6,99],
                        labels=["0–1","2–3","4–6","7+"])
        mm=wf.assign(Olgunluk=maturity).groupby("Olgunluk",observed=True).agg(
            Test=("İsabet","size"),Tahmin=("Çekirdek boyu","sum"),Doğru=("İsabet","sum")
        ).reset_index()
        mm["Doğruluk %"]=100*mm.Doğru/mm.Tahmin.clip(lower=1)
        st.subheader("Bugünkü saat karakteri olgunlaştıkça")
        st.dataframe(mm,use_container_width=True,hide_index=True)

        st.download_button(
            "⬇️ 750 TEST CSV",
            wf.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"GUN_SAAT_FAZ_AKTIF_CEKIRDEK_{len(wf)}.csv",
            mime="text/csv",use_container_width=True
        )

with tabs[1]:
    st.subheader("Bir sonraki çekiliş için bugünkü aktif çekirdek")
    # Bir sonraki hedef zamanı yaklaşık +5 dk; özellik fonksiyonunun t=len(df)
    # halinde son DT+5 kullanması sağlanmıştır.
    with st.spinner("Bugünün canlı karakteri öğreniliyor..."):
        core,tab,trained=predict(df,A,len(df))
    next_dt=df.DT.iloc[-1]+pd.Timedelta(minutes=5)
    st.write(
        f"**Hedef yaklaşık:** {next_dt.strftime('%d.%m.%Y %H:%M')} — "
        f"{regime(next_dt)} / {phase_key(next_dt)}"
    )
    st.success("AKTİF ÇEKİRDEK — "+" - ".join(map(str,core)))
    st.caption(
        "Bu çekirdek dünkü aynı saatin sayılarını kopyalamaz. "
        "Bugünün o ana kadarki saat/faz davranışını geçmişte öğrenilen kurallarla puanlar."
    )
    show=tab[["Sayı","P","today_hour","today_phase","carry_recent",
              "return_1","return_2","return_3","return_4",
              "same_phase_hist","same_slot_hist","band_live","band_trend",
              "pair_support","streak"]].head(20).copy()
    st.dataframe(show,use_container_width=True,hide_index=True)

with tabs[2]:
    st.subheader("Bugünkü saat/faz karakteri")
    last_day=day_key(df.DT.iloc[-1])
    today=df[df.DT.apply(day_key)==last_day].copy()
    rows=[]
    for h,g in today.groupby(today.DT.dt.hour):
        counts=np.zeros(80,dtype=int)
        for nums in g.Nums:
            counts[np.asarray(nums)-1]+=1
        top=np.argsort(-counts)[:10]+1
        rows.append({
            "Saat":f"{int(h):02d}:xx",
            "Çekiliş":len(g),
            "Aktif 10":" - ".join(map(str,top.tolist())),
            "En yüksek tekrar":int(counts.max())
        })
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

if bad:
    st.warning(f"Atlanan bozuk veri satırı: {bad}")
