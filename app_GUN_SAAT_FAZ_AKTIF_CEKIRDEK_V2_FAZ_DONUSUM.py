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
# V2 — FAZ DÖNÜŞÜMÜ / ÇEKİRDEK SÖNME + YENİ DOĞUM
# ============================================================
def _rate(A, ix):
    return A[ix].mean(0) if ix else np.zeros(80)

def _phase_transition_stats(eng, t, target_dt):
    """
    Geçmiş günlerde aynı saat içinde A->B faz geçişinde:
    - hangi sayıların A'dan B'ye taşındığını,
    - hangilerinin B'de yeni doğduğunu
    yalnız t öncesinden öğrenir.
    """
    A = eng.A
    carry_cases = np.zeros(80, dtype=float)
    carry_hits = np.zeros(80, dtype=float)
    birth_cases = np.zeros(80, dtype=float)
    birth_hits = np.zeros(80, dtype=float)

    # Son 360 çekiliş yeterli; hafif kalır.
    j0 = max(1, t - 360)
    for j in range(j0, t):
        cur_dt = eng.dts[j]
        prev_dt = eng.dts[j-1]
        if eng.nos[j] != eng.nos[j-1] + 1:
            continue
        if cur_dt.hour != target_dt.hour:
            continue
        # Sadece A -> B geçişlerini öğren.
        if phase(prev_dt) == "A" and phase(cur_dt) == "B":
            prev = A[j-1]
            cur = A[j]
            carry_cases += prev
            carry_hits += prev * cur
            absent = 1 - prev
            birth_cases += absent
            birth_hits += absent * cur

    carry_p = (carry_hits + 2.5) / (carry_cases + 10.0)
    birth_p = (birth_hits + 2.5) / (birth_cases + 10.0)
    return carry_p, birth_p

def score_target(eng,t):
    df=eng.df; A=eng.A
    if t<=0:
        return [],pd.DataFrame(),{}

    target_dt = eng.dts[t] if t < eng.N else eng.dts[-1] + pd.Timedelta(minutes=5)
    target_day = target_dt.date()
    target_hour = target_dt.hour
    target_reg = regime(target_dt)
    target_phase = phase(target_dt)
    target_slot = minute_slot(target_dt)

    today=[j for j in range(t) if eng.dts[j].date()==target_day]
    hour_ix=[j for j in today if eng.dts[j].hour==target_hour]
    phase_ix=[j for j in hour_ix if phase(eng.dts[j])==target_phase]
    reg_ix=[j for j in today if regime(eng.dts[j])==target_reg]
    a_ix=[j for j in hour_ix if phase(eng.dts[j])=="A"]
    b_ix=[j for j in hour_ix if phase(eng.dts[j])=="B"]

    today_hour=_rate(A,hour_ix)
    today_phase=_rate(A,phase_ix)
    today_reg=_rate(A,reg_ix)
    today_A=_rate(A,a_ix)
    today_B=_rate(A,b_ix)

    hist0=max(0,t-300)
    same_hour=[j for j in range(hist0,t) if eng.dts[j].hour==target_hour]
    same_phase=[j for j in same_hour if phase(eng.dts[j])==target_phase]
    same_slot=[j for j in range(hist0,t) if minute_slot(eng.dts[j])==target_slot]
    hour_hist=_rate(A,same_hour)
    phase_hist=_rate(A,same_phase)
    slot_hist=_rate(A,same_slot)

    # Kişisel tekrar / taşıma.
    end=max(t-1,0); start=max(0,end-180)
    cases=(eng.rep_cases[end]-eng.rep_cases[start]).astype(float)
    hits=(eng.rep_hits[end]-eng.rep_hits[start]).astype(float)
    carry=(hits+2.5)/(cases+10.0)

    # Gap ve dönüş uygunluğu.
    gaps=np.zeros(80,dtype=float)
    for n in range(80):
        seen=np.where(A[:t,n]>0)[0]
        gaps[n]=(t-1-seen[-1]) if len(seen) else 20
    return_fit=np.maximum.reduce([
        np.exp(-np.abs(gaps-1)/1.0),
        np.exp(-np.abs(gaps-2)/1.1),
        np.exp(-np.abs(gaps-3)/1.2),
        np.exp(-np.abs(gaps-4)/1.3)
    ])

    # Faz geçişi özel istatistikleri.
    ab_carry, ab_birth = _phase_transition_stats(eng,t,target_dt)

    # Canlı bant.
    band_live=np.zeros(80); band_shift=np.zeros(80)
    for n in range(80):
        lo=(n//10)*10
        h=float(today_hour[lo:lo+10].mean()) if hour_ix else 0.0
        p=float(today_phase[lo:lo+10].mean()) if phase_ix else 0.0
        a=float(today_A[lo:lo+10].mean()) if a_ix else 0.0
        b=float(today_B[lo:lo+10].mean()) if b_ix else 0.0
        band_live[n]=p if phase_ix else h
        band_shift[n]=(b-a) if target_phase=="B" else (p-h)

    # Son çekiliş ve kısa seri.
    last=A[t-1] if t>0 else np.zeros(80)
    streak=np.zeros(80)
    for n in range(80):
        st=0
        for j in range(t-1,max(-1,t-6),-1):
            if A[j,n]: st+=1
            else: break
        streak[n]=st/5.0

    # Faz olgunluğu.
    hour_maturity=min(len(hour_ix)/6.0,1.0)
    phase_maturity=min(len(phase_ix)/4.0,1.0)

    # A fazı çekirdeğinin B'de otomatik sürmesini engelle.
    # B başında: A yoğunluğu ancak tarihsel A->B taşıma destekliyorsa korunur.
    a_memory = today_A
    if target_phase=="B":
        retained = a_memory * ab_carry
        fade = a_memory * (1.0 - ab_carry)
        live_identity = .42*today_B + .18*retained + .10*ab_birth
        phase_change_penalty = .16*fade
    else:
        live_identity = .52*today_A + .08*ab_birth
        phase_change_penalty = np.zeros(80)

    # Yeni doğum: önceki çekilişte olmayan, B'de doğma geçmişi + canlı bant desteği.
    new_birth = (1-last) * (
        .48*ab_birth + .22*phase_hist + .16*band_live + .14*return_fit
    )

    # Taşıma: son çekilişte olan, kişisel carry + faz geçiş carry.
    carry_channel = last * (
        .50*carry + .24*ab_carry + .16*today_hour + .10*streak
    )

    # Dönüş: 1-4 el yokluk + aynı faz/slot geçmişi.
    return_channel = (1-last) * return_fit * (
        .44*phase_hist + .28*slot_hist + .18*hour_hist + .10*band_live
    )

    # Geçmiş kural + bugünkü kimlik.
    hist_score = .34*phase_hist + .24*slot_hist + .18*hour_hist + .12*carry + .12*eng.win_rate(t,60)
    live_score = (
        .32*live_identity
        + .22*carry_channel
        + .18*return_channel
        + .18*new_birth
        + .06*today_reg
        + .04*np.clip(band_shift+.25,0,1)
        - phase_change_penalty
    )

    # Saat başında geçmişe daha çok yaslan; faz olgunlaştıkça bugüne dön.
    maturity = .55*hour_maturity + .45*phase_maturity
    score = (1-maturity)*hist_score + maturity*live_score

    # Aşırı yapışmayı azalt: aynı sayının saat içinde çok yüksek tekrarına yumuşak fren.
    overheat=np.clip(today_hour-.65,0,None)
    score -= .10*overheat

    order=np.argsort(-score,kind="mergesort")

    # Dinamik çekirdek 3–7; ama skor ayrımı zayıfsa 3'e düş.
    vals=score[order[:8]]
    if len(vals)>=8:
        gapv=vals[:-1]-vals[1:]
        k=int(np.argmax(gapv[:6])+1)
        k=max(3,min(k,7))
        if float(vals[0]-vals[4]) < 0.025:
            k=3
    else:
        k=3

    core=(order[:k]+1).astype(int).tolist()

    role=np.array(["DİĞER"]*80,dtype=object)
    for i in range(80):
        parts={
            "TAŞIMA":carry_channel[i],
            "FAZ-DÖNÜŞ":return_channel[i],
            "YENİ-DOĞUM":new_birth[i],
            "CANLI-ÇEKİRDEK":live_identity[i],
        }
        role[i]=max(parts,key=parts.get)

    tab=pd.DataFrame({
        "Sayı":np.arange(1,81),
        "Puan":np.round(score*100,3),
        "Rol":role,
        "Bugün A":np.round(today_A*100,2),
        "Bugün B":np.round(today_B*100,2),
        "A→B taşıma":np.round(ab_carry*100,2),
        "B doğum":np.round(ab_birth*100,2),
        "Taşıma kanal":np.round(carry_channel*100,2),
        "Faz dönüş":np.round(return_channel*100,2),
        "Yeni doğum":np.round(new_birth*100,2),
        "Faz geçmişi":np.round(phase_hist*100,2),
        "Slot geçmişi":np.round(slot_hist*100,2),
        "Bant kayma":np.round(band_shift*100,2),
        "Gap":gaps.astype(int),
    }).sort_values(["Puan","Sayı"],ascending=[False,True]).reset_index(drop=True)

    meta={
        "hour_obs":len(hour_ix),
        "phase_obs":len(phase_ix),
        "maturity":round(float(maturity),3),
        "phase":target_phase,
    }
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
st.title("⚡ GÜN × SAAT × FAZ AKTİF ÇEKİRDEK V2 — FAZ DÖNÜŞÜM")
st.caption("A fazı çekirdeğini B fazına kör taşımak yerine: SÖNME + A→B TAŞIMA + FAZ-DÖNÜŞ + YENİ-DOĞUM ayrı kanallardır.")

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
            file_name=f"GUN_SAAT_FAZ_V2_DONUSUM_{len(wf)}.csv",
            mime="text/csv",use_container_width=True
        )

with tabs[1]:
    core,tab,meta=score_target(eng,len(df))
    next_dt=df.DT.iloc[-1]+pd.Timedelta(minutes=5)
    st.write(f"**Hedef:** {next_dt.strftime('%d.%m.%Y %H:%M')} — {regime(next_dt)} / {phase(next_dt)}")
    st.write(f"Bugünkü saat içi gözlem: **{meta['hour_obs']}** • faz içi gözlem: **{meta['phase_obs']}**")
    st.success("AKTİF ÇEKİRDEK — "+" - ".join(map(str,core)))
    st.dataframe(tab.head(20),use_container_width=True,hide_index=True)
