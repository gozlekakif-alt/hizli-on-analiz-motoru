from pathlib import Path
from datetime import datetime
import re
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gün–Saat–Faz Aktif Çekirdek ULTRA HAFİF", page_icon="⚡", layout="wide")
DATA = Path(__file__).with_name("veri.txt")

# ============================================================
# VERİ
# ============================================================
def parse_line(line):
    p=str(line).strip().split(";")
    if len(p)!=4:
        return None
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
    rows=[]
    for x in text.splitlines():
        if not x.strip(): continue
        z=parse_line(x)
        if z is not None: rows.append(z)
    df=pd.DataFrame(rows,columns=["No","DT","Nums"])
    if len(df):
        df=(df.drop_duplicates("No",keep="last").sort_values("No").reset_index(drop=True))
    return df

def make_A(df):
    A=np.zeros((len(df),80),dtype=np.int8)
    for i,nums in enumerate(df.Nums):
        A[i,np.asarray(nums)-1]=1
    return A

# ============================================================
# GÜN / REJİM / FAZ
# ============================================================
def regime(dt):
    h=dt.hour+dt.minute/60
    if 7<=h<11: return "SABAH"
    if 11<=h<16: return "ÖĞLEN"
    if 16<=h<21: return "AKŞAM"
    return "KAPANIŞ"

def phase(dt):
    return "A" if dt.minute < 30 else "B"

def minute_slot(dt):
    return max(0,int(round((dt.minute-2)/5)))

# ============================================================
# HIZLI ÖN HESAPLAMA
# ============================================================
class FastEngine:
    def __init__(self,df):
        self.df=df
        self.A=make_A(df)
        self.N=len(df)
        self.dts=list(pd.to_datetime(df.DT))
        self.nos=df.No.astype(int).to_numpy()

        # Kümülatif frekans.
        self.cum=np.vstack([np.zeros((1,80),dtype=np.int32),np.cumsum(self.A,axis=0)])

        # Kişisel tekrar: geçmiş ardışık geçişlerde n -> n.
        self.rep_cases=np.zeros((self.N+1,80),dtype=np.int16)
        self.rep_hits=np.zeros((self.N+1,80),dtype=np.int16)
        for j in range(self.N-1):
            self.rep_cases[j+1]=self.rep_cases[j]
            self.rep_hits[j+1]=self.rep_hits[j]
            if self.nos[j+1]==self.nos[j]+1:
                self.rep_cases[j+1]+=self.A[j]
                self.rep_hits[j+1]+=self.A[j]*self.A[j+1]
        self.rep_cases[self.N]=self.rep_cases[self.N-1] if self.N else 0
        self.rep_hits[self.N]=self.rep_hits[self.N-1] if self.N else 0

    def win_rate(self,t,w):
        s=max(0,t-w)
        return (self.cum[t]-self.cum[s])/max(t-s,1)

    def subset_rate(self,t,mask_idx):
        ix=[j for j in mask_idx if j<t]
        if not ix: return np.full(80,.25)
        return self.A[ix].mean(0)

# ============================================================
# HIZLI AKTİF ÇEKİRDEK
# ============================================================
def score_target(eng,t):
    df=eng.df; A=eng.A
    if t<=0: return [],pd.DataFrame()

    # Hedef zamanı: geçmiş testte gerçek hedef zamanı; canlıda son+5 dk.
    if t < eng.N:
        target_dt=eng.dts[t]
    else:
        target_dt=eng.dts[-1]+pd.Timedelta(minutes=5)

    target_day=target_dt.date()
    target_hour=target_dt.hour
    target_reg=regime(target_dt)
    target_phase=phase(target_dt)
    target_slot=minute_slot(target_dt)

    # BUGÜNÜN yalnız hedef öncesi gerçekleşmiş çekilişleri.
    today=[j for j in range(t) if eng.dts[j].date()==target_day]
    hour_ix=[j for j in today if eng.dts[j].hour==target_hour]
    phase_ix=[j for j in hour_ix if phase(eng.dts[j])==target_phase]
    reg_ix=[j for j in today if regime(eng.dts[j])==target_reg]

    def rate(ix):
        return A[ix].mean(0) if ix else np.zeros(80)

    today_hour=rate(hour_ix)
    today_phase=rate(phase_ix)
    today_reg=rate(reg_ix)

    # Geçmiş aynı saat / faz / slot. Son 300 satırla sınırlı.
    hist0=max(0,t-300)
    same_hour=[j for j in range(hist0,t) if eng.dts[j].hour==target_hour]
    same_phase=[j for j in same_hour if phase(eng.dts[j])==target_phase]
    same_slot=[j for j in range(hist0,t) if minute_slot(eng.dts[j])==target_slot]

    hour_hist=rate(same_hour)
    phase_hist=rate(same_phase)
    slot_hist=rate(same_slot)

    # Taşıma oranı hızlı kümülatiften.
    end=max(t-1,0)
    start=max(0,end-180)
    cases=(eng.rep_cases[end]-eng.rep_cases[start]).astype(float)
    hits=(eng.rep_hits[end]-eng.rep_hits[start]).astype(float)
    carry=(hits+2.5)/(cases+10.0)

    # 1/2/3/4 el dinlenip geri dönüş: yalnız mevcut durumun "gap" sınıfı.
    gaps=np.zeros(80,dtype=float)
    for n in range(80):
        seen=np.where(A[:t,n]>0)[0]
        gaps[n]=(t-1-seen[-1]) if len(seen) else 20

    # Gap dönüş uygunluğu: bugünün ve geçmişin hızlı proxy'si.
    ret1=np.exp(-np.abs(gaps-1)/1.2)
    ret2=np.exp(-np.abs(gaps-2)/1.2)
    ret3=np.exp(-np.abs(gaps-3)/1.3)
    ret4=np.exp(-np.abs(gaps-4)/1.4)
    return_fit=np.maximum.reduce([ret1,ret2,ret3,ret4])

    # Bant canlılığı.
    band_live=np.zeros(80)
    band_trend=np.zeros(80)
    h20=eng.win_rate(t,20)
    for n in range(80):
        lo=(n//10)*10
        bh=float(today_hour[lo:lo+10].mean()) if len(hour_ix) else 0.0
        bp=float(today_phase[lo:lo+10].mean()) if len(phase_ix) else 0.0
        band_live[n]=bh
        band_trend[n]=bp-bh

    # Son çekiliş / seri.
    last=A[t-1] if t>0 else np.zeros(80)
    streak=np.zeros(80)
    for n in range(80):
        st=0
        for j in range(t-1,max(-1,t-6),-1):
            if A[j,n]: st+=1
            else: break
        streak[n]=st/5.0

    # Geçmiş davranışı öğretir, bugünkü sayıları bugünün yoğunluğu seçer.
    score=(
        .24*today_hour
        + .16*today_phase
        + .07*today_reg
        + .12*carry
        + .10*phase_hist
        + .07*slot_hist
        + .06*hour_hist
        + .06*return_fit
        + .05*band_live
        + .03*np.clip(band_trend+.25,0,1)
        + .04*streak
    )

    # Saat başında bugünkü örnek yoksa geçmiş kanallar ağırlık taşır.
    maturity=min(len(hour_ix)/6.0,1.0)
    hist_score=.35*phase_hist+.25*slot_hist+.20*hour_hist+.20*eng.win_rate(t,60)
    score=maturity*score+(1-maturity)*hist_score

    order=np.argsort(-score,kind="mergesort")

    # 3–7 arası dinamik çekirdek; büyük skor boşluğunda kes.
    k=5
    if len(order)>=8:
        vals=score[order[:8]]
        gaps2=vals[:-1]-vals[1:]
        kk=int(np.argmax(gaps2[:6])+1)
        k=max(3,min(kk,7))
    core=(order[:k]+1).astype(int).tolist()

    tab=pd.DataFrame({
        "Sayı":np.arange(1,81),
        "Puan":np.round(score*100,3),
        "Bugün saat":np.round(today_hour*100,2),
        "Bugün faz":np.round(today_phase*100,2),
        "Taşıma":np.round(carry*100,2),
        "Faz geçmişi":np.round(phase_hist*100,2),
        "Slot geçmişi":np.round(slot_hist*100,2),
        "Dönüş uygunluğu":np.round(return_fit*100,2),
        "Bant canlı":np.round(band_live*100,2),
        "Gap":gaps.astype(int),
    }).sort_values(["Puan","Sayı"],ascending=[False,True]).reset_index(drop=True)

    meta={"hour_obs":len(hour_ix),"phase_obs":len(phase_ix),"maturity":maturity}
    return core,tab,meta

# ============================================================
# WALK-FORWARD — MODEL EĞİTİMİ YOK, BU YÜZDEN HIZLI
# ============================================================
def backtest(eng,n):
    valid=[t for t in range(80,eng.N) if eng.nos[t]==eng.nos[t-1]+1]
    valid=valid[-min(int(n),len(valid)):]
    rows=[]
    for pos,t in enumerate(valid):
        core,tab,meta=score_target(eng,t)
        actual=set((np.where(eng.A[t]>0)[0]+1).tolist())
        hits=sorted(set(core)&actual)
        seg="İlk" if pos<len(valid)/3 else ("Orta" if pos<2*len(valid)/3 else "Son")
        rows.append({
            "Sıra":pos+1,
            "Bölüm":seg,
            "Çekiliş":int(eng.nos[t]),
            "Tarih/Saat":eng.dts[t].strftime("%d.%m.%Y %H:%M"),
            "Rejim":regime(eng.dts[t]),
            "Faz":phase(eng.dts[t]),
            "Saat içi gözlem":meta["hour_obs"],
            "Faz içi gözlem":meta["phase_obs"],
            "Çekirdek boyu":len(core),
            "İsabet":len(hits),
            "Tam çekirdek":bool(len(core)>0 and len(hits)==len(core)),
            "Çekirdek":"-".join(map(str,core)),
            "Tutan":"-".join(map(str,hits)),
            "Sızıntı":"TEMİZ",
        })
    return pd.DataFrame(rows)

# ============================================================
# UI
# ============================================================
st.title("⚡ GÜN × SAAT × FAZ AKTİF ÇEKİRDEK — ULTRA HAFİF")
st.caption(
    "Ağır model eğitimi kaldırıldı. Geçmişten davranış oranlarını, bugünden canlı saat/faz karakterini kullanır."
)

if not DATA.exists():
    st.error("veri.txt bulunamadı.")
    st.stop()

df=load(DATA.read_text(encoding="utf-8",errors="ignore"))
if len(df)<120:
    st.error(f"Veri yetersiz: {len(df)}")
    st.stop()

eng=FastEngine(df)

c1,c2,c3=st.columns(3)
c1.metric("Havuz",len(df))
c2.metric("Son çekiliş",int(df.No.iloc[-1]))
c3.metric("Son faz",f"{regime(df.DT.iloc[-1])}_{df.DT.iloc[-1].hour:02d}_{phase(df.DT.iloc[-1])}")

tabs=st.tabs(["🧪 HIZLI KÖR TEST","🎯 BUGÜNÜN AKTİF ÇEKİRDEĞİ"])

with tabs[0]:
    test_n=st.select_slider("Test adedi",options=[10,25,50,100,250],value=25)
    st.info("Bu sürüm her hedefte yeniden LogisticRegression eğitmez; test çok daha hızlıdır.")
    if "fast_wf" not in st.session_state:
        st.session_state.fast_wf=None
    if st.button("⚡ TESTİ BAŞLAT",type="primary",use_container_width=True):
        with st.spinner(f"{test_n} çekiliş test ediliyor..."):
            st.session_state.fast_wf=backtest(eng,test_n)

    wf=st.session_state.fast_wf
    if isinstance(wf,pd.DataFrame) and len(wf):
        pred=int(wf["Çekirdek boyu"].sum())
        hit=int(wf["İsabet"].sum())
        a,b,c,d=st.columns(4)
        a.metric("Test",len(wf))
        b.metric("Sayı doğruluğu",f"%{100*hit/max(pred,1):.2f}")
        c.metric("Ort. çekirdek",f"{wf['Çekirdek boyu'].mean():.2f}")
        d.metric("Tam çekirdek",int(wf["Tam çekirdek"].sum()))
        st.dataframe(wf,use_container_width=True,hide_index=True)
        st.download_button(
            "⬇️ TEST CSV İNDİR",
            wf.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"GUN_SAAT_FAZ_ULTRA_HAFIF_{len(wf)}.csv",
            mime="text/csv",use_container_width=True
        )

with tabs[1]:
    core,tab,meta=score_target(eng,len(df))
    next_dt=df.DT.iloc[-1]+pd.Timedelta(minutes=5)
    st.write(f"**Hedef:** {next_dt.strftime('%d.%m.%Y %H:%M')} — {regime(next_dt)} / {phase(next_dt)}")
    st.write(f"Bugünkü saat içi gözlem: **{meta['hour_obs']}** • faz içi gözlem: **{meta['phase_obs']}**")
    st.success("AKTİF ÇEKİRDEK — "+" - ".join(map(str,core)))
    st.dataframe(tab.head(20),use_container_width=True,hide_index=True)
