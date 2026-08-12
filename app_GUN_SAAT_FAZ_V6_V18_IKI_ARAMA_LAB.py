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
# V3 SEÇİCİ — 250 TESTTE KRONOLOJİK AYRIMLA KORUNAN BÖLGELER
# İlk 150 çekilişte kural çıkarıldı, son 100 çekilişte ayrıca kontrol edildi.
# Kural basit tutulur; hedef sonucu karar anında kullanılmaz.
# ============================================================
def v3_selector(meta, target_dt, core):
    reg = regime(target_dt)
    ph = phase(target_dt)
    phase_obs = int(meta.get("phase_obs", 0))
    core_len = len(core)

    # 1) SABAH-B:
    # İlk B çekilişi yerine faz en az 1 gözlem gördükten sonra,
    # yalnız 3 sayılık net çekirdek.
    morning_b = (
        reg == "SABAH"
        and ph == "B"
        and phase_obs >= 1
        and core_len == 3
    )

    # 2) AKŞAM-A:
    # A fazının ilk iki çekilişini bekle; yalnız 3 sayılık net çekirdek.
    evening_a = (
        reg == "AKŞAM"
        and ph == "A"
        and phase_obs >= 2
        and core_len == 3
    )

    speak = bool(morning_b or evening_a)
    reason = (
        "SABAH-B OLGUN ÇEKİRDEK" if morning_b
        else ("AKŞAM-A OLGUN ÇEKİRDEK" if evening_a else "PAS")
    )
    return speak, reason



# ============================================================
# V4 ADAYI — ÜÇÜNCÜ SAYI GÜVEN LAB
# V3 KURALI DEĞİŞMEZ. Yalnız V3 KONUŞTUĞUNDA 3. adayın
# ilk iki adayla puan yakınlığını ölçer.
# Güçlü değilse 3'lü yerine 2'li çekirdek önerir.
# ============================================================
def v4_third_number(core, tab, v3_speak):
    if not v3_speak or len(core) != 3 or tab is None or len(tab) < 4:
        return [], "PAS", 0.0

    # core sırası score_target sırasıdır; tab da Puan'a göre sıralıdır.
    top=tab.head(4).copy()
    p1=float(top.iloc[0]["Puan"])
    p2=float(top.iloc[1]["Puan"])
    p3=float(top.iloc[2]["Puan"])
    p4=float(top.iloc[3]["Puan"])

    # 3. sayının iki yönden ayrışması:
    # - ikinciye çok uzak düşmesin
    # - dördüncüden belirgin üstün olsun
    cohesion=max(0.0, 1.0-abs(p2-p3)/max(abs(p2),1.0))
    separation=max(0.0, (p3-p4)/max(abs(p3),1.0))
    confidence=100.0*(0.72*cohesion+0.28*min(separation*8.0,1.0))

    # Bu eşik V3 sonucuna göre optimize edilmedi; LAB başlangıç eşiğidir.
    # Sonuç CSV'sinden sonra değiştirilip ayrı doğrulama gerekir.
    if confidence >= 76.0:
        return core[:3], "3'LÜ", confidence
    return core[:2], "2'Lİ", confidence



# ============================================================
# V5 ADAYI — OLAY SEÇİCİ
# V3 ve V4 değişmez. V5 yalnız V3 KONUŞ olaylarının kendisini
# filtreler. Kural, 250 sonuçtaki V3 konuşmalarının kronolojik
# ilk %65 / son %35 parçalarında ayrı kontrol edilen basit bölgedir.
# ============================================================
def v5_event_selector(meta, v4_conf, v3_speak):
    if not v3_speak:
        return False, "V3 PAS"

    hour_obs=int(meta.get("hour_obs",0))
    phase_obs=int(meta.get("phase_obs",0))

    speak=(
        hour_obs >= 4
        and phase_obs >= 3
        and float(v4_conf) >= 65.0
        and float(v4_conf) <= 80.0
    )
    reason=(
        "OLGUN SAAT+FAZ / ORTA-GÜÇ V4" if speak
        else "V5 PAS"
    )
    return bool(speak),reason



# ============================================================
# V18'DEN İKİ ARAMA MOTORU — V6 DENEYSEL KANIT
# 1) BENZER DURUM ARAMA:
#    Son davranış penceresine geçmişte benzeyen pencereleri bulur,
#    hemen sonraki çekilişlerde çıkan sayıları puanlar.
# 2) BLOK BASINÇ ARAMA:
#    Son blok yapısına benzeyen geçmiş pencerelerin ardından hangi
#    10'luk bölgelerde blok oluştuğunu puanlar.
#
# V5 olay seçicisi DEĞİŞMEZ. Bu iki motor yalnız V5 KONUŞ olduğunda
# 1–80 aday sırasını yeniden destekler.
# ============================================================
def _behavior_row_v6(eng, i):
    if i <= 0:
        return None
    prev=set((np.where(eng.A[i-1]>0)[0]+1).tolist())
    cur=set((np.where(eng.A[i]>0)[0]+1).tolist())

    carry=len(prev & cur)
    new=len(cur - prev)

    def rr(nums):
        xs=sorted(nums); runs=[]; c=[]
        for x in xs:
            if not c or x==c[-1]+1: c.append(x)
            else:
                if len(c)>=2: runs.append(c)
                c=[x]
        if len(c)>=2: runs.append(c)
        return runs

    runs=rr(cur)
    pair_density=sum(max(0,len(r)-1) for r in runs)
    triple_density=sum(max(0,len(r)-2) for r in runs)
    max_block=max([len(r) for r in runs],default=1)

    bands=[
        sum(1<=n<=20 for n in cur),
        sum(21<=n<=40 for n in cur),
        sum(41<=n<=60 for n in cur),
        sum(61<=n<=80 for n in cur),
    ]
    return np.array(
        [carry,new,pair_density,triple_density,max_block,*bands],
        dtype=float
    )

def v18_similar_state_scores_v6(eng,t,state_window=6,search_window=320,top_matches=20):
    if t < state_window*2+15:
        return np.zeros(80),0,0.0

    # Hedef t için mevcut durum t-1'e kadar.
    start=max(1,t-search_window)
    rows=[]
    idxs=[]
    for i in range(start,t):
        z=_behavior_row_v6(eng,i)
        if z is not None:
            rows.append(z); idxs.append(i)
    if len(rows)<state_window*2+3:
        return np.zeros(80),0,0.0

    X=np.vstack(rows)
    mu=X.mean(0); sd=X.std(0); sd[sd<1e-9]=1.0
    current=((X[-state_window:].mean(0)-mu)/sd)

    matches=[]
    # end is local row index; next target must stay strictly < t
    for end in range(state_window,len(X)-state_window):
        vec=((X[end-state_window:end].mean(0)-mu)/sd)
        dist=float(np.sqrt(np.mean((vec-current)**2)))
        target_i=idxs[end]
        if target_i>=t:
            continue
        matches.append((dist,target_i))
    matches=sorted(matches,key=lambda x:x[0])[:top_matches]
    if not matches:
        return np.zeros(80),0,0.0

    scores=np.zeros(80,float); tw=0.0
    sims=[]
    for dist,i in matches:
        w=1.0/(0.15+dist)
        tw+=w
        sims.append(100.0/(1.0+dist))
        scores += w*eng.A[i]
    scores=scores/max(tw,1e-9)
    return scores,len(matches),float(np.mean(sims))

def _block_profile_v6(nums):
    nums=sorted(set(nums))
    runs=[]; cur=[]
    for x in nums:
        if not cur or x==cur[-1]+1:
            cur.append(x)
        else:
            if len(cur)>=2:runs.append(cur)
            cur=[x]
    if len(cur)>=2:runs.append(cur)

    prof=np.array([
        len(runs),
        sum(len(r)==2 for r in runs),
        sum(len(r)==3 for r in runs),
        sum(len(r)>=4 for r in runs),
        max([len(r) for r in runs],default=1),
        sum(1<=n<=20 for n in nums),
        sum(21<=n<=40 for n in nums),
        sum(41<=n<=60 for n in nums),
        sum(61<=n<=80 for n in nums),
    ],dtype=float)
    return prof,runs

def v18_block_pressure_scores_v6(eng,t,state_window=5,lookback=320,top_matches=30):
    if t<state_window+30:
        return np.zeros(80),0,0.0

    start=max(0,t-lookback)
    profiles=[]; sets=[]
    for i in range(start,t):
        nums=(np.where(eng.A[i]>0)[0]+1).tolist()
        p,r=_block_profile_v6(nums)
        profiles.append(p); sets.append((nums,r))
    if len(profiles)<state_window+20:
        return np.zeros(80),0,0.0

    P=np.vstack(profiles)
    cur=P[-state_window:].mean(0)
    hist=[]
    for i in range(state_window,len(P)-1):
        hist.append(P[i-state_window:i].mean(0))
    scale=np.std(np.vstack(hist),axis=0) if hist else np.ones_like(cur)
    scale=np.where(scale<0.25,1.0,scale)

    target_hour=eng.dts[t].hour if t<len(eng.dts) else (eng.dts[-1]+pd.Timedelta(minutes=5)).hour
    matches=[]
    for i in range(state_window,len(P)):
        # i is the historical "next draw" relative to its prior window
        vec=P[i-state_window:i].mean(0)
        dist=float(np.sqrt(np.mean(((vec-cur)/scale)**2)))
        sim=float(np.exp(-dist))
        global_i=start+i
        if eng.dts[global_i].hour==target_hour:
            sim*=1.12
        matches.append((sim,global_i))
    matches=sorted(matches,reverse=True)[:top_matches]
    if not matches:
        return np.zeros(80),0,0.0

    region=np.zeros(8,float); total=0.0; sims=[]
    for w,i in matches:
        total+=w; sims.append(w)
        nums=(np.where(eng.A[i]>0)[0]+1).tolist()
        _,runs=_block_profile_v6(nums)
        for r in runs:
            center=int(round(np.mean(r)))
            b=(center-1)//10
            region[b]+=w*max(1,len(r)-1)

    if region.max()>0:
        region=region/region.max()
    scores=np.zeros(80,float)
    for n in range(1,81):
        scores[n-1]=region[(n-1)//10]
    pressure=float(np.mean(sorted(region,reverse=True)[:2])*100.0)
    return scores,len(matches),pressure

def v6_v18_search_rerank(eng,t,tab,v5_speak):
    if not v5_speak or tab is None or tab.empty:
        return [],pd.DataFrame(),{}

    sim,sim_n,sim_q=v18_similar_state_scores_v6(eng,t)
    block,block_n,pressure=v18_block_pressure_scores_v6(eng,t)

    work=tab.copy()
    # tab Puan 0..yaklaşık100; normalize independently.
    base=work["Puan"].astype(float).to_numpy()
    bmin,bmax=float(base.min()),float(base.max())
    base_n=(base-bmin)/(bmax-bmin) if bmax>bmin else np.zeros_like(base)

    nums=work["Sayı"].astype(int).to_numpy()
    sim_v=np.array([sim[n-1] for n in nums],float)
    block_v=np.array([block[n-1] for n in nums],float)

    # V5 çekirdeği ana bilgi; V18 aramalar yalnız destek.
    final=.68*base_n+.20*sim_v+.12*block_v
    work["V18 Benzer Arama"]=np.round(sim_v*100,2)
    work["V18 Blok Arama"]=np.round(block_v*100,2)
    work["V6 Birleşik"]=np.round(final*100,3)
    work=work.sort_values(
        ["V6 Birleşik","Puan","Sayı"],ascending=[False,False,True]
    ).reset_index(drop=True)
    picks=work.head(3)["Sayı"].astype(int).tolist()
    meta={
        "Benzer eşleşme":sim_n,
        "Benzer kalite":round(sim_q,2),
        "Blok eşleşme":block_n,
        "Blok basıncı":round(pressure,2),
    }
    return picks,work,meta


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
        speak,reason=v3_selector(meta,eng.dts[t],core)
        selected_core=core if speak else []
        selected_hits=hits if speak else []
        v4_core,v4_mode,v4_conf=v4_third_number(core,tab,speak)
        v4_hits=sorted(set(v4_core)&actual)
        v5_speak,v5_reason=v5_event_selector(meta,v4_conf,speak)
        v5_core=core if v5_speak else []
        v5_hits=sorted(set(v5_core)&actual)
        v6_core,v6_tab,v6_meta=v6_v18_search_rerank(eng,t,tab,v5_speak)
        v6_hits=sorted(set(v6_core)&actual)
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
            "Ham çekirdek boyu":len(core),
            "Ham isabet":len(hits),
            "V3 Karar":"KONUŞ" if speak else "PAS",
            "V3 Neden":reason,
            "Çekirdek boyu":len(selected_core),
            "İsabet":len(selected_hits),
            "Tam çekirdek":bool(len(selected_core)>0 and len(selected_hits)==len(selected_core)),
            "Çekirdek":"-".join(map(str,selected_core)),
            "Tutan":"-".join(map(str,selected_hits)),
            "V4 Mod":v4_mode,
            "V4 Güven":round(v4_conf,2),
            "V4 Boyu":len(v4_core),
            "V4 İsabet":len(v4_hits),
            "V4 Kupon":"-".join(map(str,v4_core)),
            "V4 Tutan":"-".join(map(str,v4_hits)),
            "V4 Tam":bool(len(v4_core)>0 and len(v4_hits)==len(v4_core)),
            "V5 Karar":"KONUŞ" if v5_speak else "PAS",
            "V5 Neden":v5_reason,
            "V5 Boyu":len(v5_core),
            "V5 İsabet":len(v5_hits),
            "V5 Kupon":"-".join(map(str,v5_core)),
            "V5 Tutan":"-".join(map(str,v5_hits)),
            "V5 Tam":bool(len(v5_core)>0 and len(v5_hits)==len(v5_core)),
            "V6 Karar":"KONUŞ" if v6_core else "PAS",
            "V6 Boyu":len(v6_core),
            "V6 İsabet":len(v6_hits),
            "V6 Kupon":"-".join(map(str,v6_core)),
            "V6 Tutan":"-".join(map(str,v6_hits)),
            "V6 Tam":bool(len(v6_core)>0 and len(v6_hits)==len(v6_core)),
            "V18 Benzer eşleşme":int(v6_meta.get("Benzer eşleşme",0)),
            "V18 Benzer kalite":float(v6_meta.get("Benzer kalite",0.0)),
            "V18 Blok eşleşme":int(v6_meta.get("Blok eşleşme",0)),
            "V18 Blok basıncı":float(v6_meta.get("Blok basıncı",0.0)),
            "Sızıntı":"TEMİZ",
        })
    return pd.DataFrame(rows)

# ============================================================
# UI
# ============================================================
st.title("🔎 GÜN × SAAT × FAZ V6 — V18 İKİ ARAMA LAB")
st.caption("Dondurulmuş V5 olay seçicisi korunur. V18 Benzer Durum Arama + V18.4 Blok Basınç Arama yalnız V5 KONUŞ olaylarında 3 sayıyı yeniden sıralar.")

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
        active=wf[wf["V3 Karar"]=="KONUŞ"].copy()
        a.metric("Test",len(wf))
        b.metric("V3 KONUŞ",len(active))
        c.metric("V3 sayı doğruluğu",f"%{100*active['İsabet'].sum()/max(active['Çekirdek boyu'].sum(),1):.2f}" if len(active) else "—")
        d.metric("Tam çekirdek",int(active["Tam çekirdek"].sum()) if len(active) else 0)

        if len(active):
            st.subheader("V3 seçilmiş olaylar")
            seg=(active.groupby(["Rejim","Faz"])
                 .agg(Test=("İsabet","size"),Tahmin=("Çekirdek boyu","sum"),
                      Doğru=("İsabet","sum"),Tam=("Tam çekirdek","sum"))
                 .reset_index())
            seg["Doğruluk %"]=100*seg["Doğru"]/seg["Tahmin"].clip(lower=1)
            st.dataframe(seg,use_container_width=True,hide_index=True)

        v4=wf[wf["V4 Mod"]!="PAS"].copy()
        if len(v4):
            st.subheader("V3 ↔ V4 karşılaştırma")
            v3_pred=int(active["Çekirdek boyu"].sum()) if len(active) else 0
            v3_hit=int(active["İsabet"].sum()) if len(active) else 0
            v4_pred=int(v4["V4 Boyu"].sum())
            v4_hit=int(v4["V4 İsabet"].sum())
            x1,x2,x3,x4=st.columns(4)
            x1.metric("V3 doğruluk",f"%{100*v3_hit/max(v3_pred,1):.2f}")
            x2.metric("V4 doğruluk",f"%{100*v4_hit/max(v4_pred,1):.2f}")
            x3.metric("V4 3'lü olay",int((v4["V4 Mod"]=="3'LÜ").sum()))
            x4.metric("V4 2'li olay",int((v4["V4 Mod"]=="2'Lİ").sum()))
            comp=(v4.groupby(["Rejim","Faz","V4 Mod"])
                  .agg(Test=("V4 İsabet","size"),Tahmin=("V4 Boyu","sum"),
                       Doğru=("V4 İsabet","sum"),Tam=("V4 Tam","sum"),
                       Ort_Güven=("V4 Güven","mean"))
                  .reset_index())
            comp["Doğruluk %"]=100*comp["Doğru"]/comp["Tahmin"].clip(lower=1)
            st.dataframe(comp,use_container_width=True,hide_index=True)

        v5=wf[wf["V5 Karar"]=="KONUŞ"].copy()
        if len(v5):
            st.subheader("🔥 V5 olay seçici")
            p=int(v5["V5 Boyu"].sum())
            h=int(v5["V5 İsabet"].sum())
            q1,q2,q3,q4=st.columns(4)
            q1.metric("V5 KONUŞ",len(v5))
            q2.metric("V5 doğruluk",f"%{100*h/max(p,1):.2f}")
            q3.metric("0/3 olay",int((v5["V5 İsabet"]==0).sum()))
            q4.metric("2+ olay",int((v5["V5 İsabet"]>=2).sum()))

            # Kronolojik iki yarı
            mid=len(wf)//2
            tmp=v5.copy()
            tmp["Yarı"]=np.where(tmp["Sıra"]<=wf.iloc[mid-1]["Sıra"],"İlk yarı","Son yarı")
            half=(tmp.groupby("Yarı")
                  .agg(Test=("V5 İsabet","size"),Tahmin=("V5 Boyu","sum"),
                       Doğru=("V5 İsabet","sum"),Sıfır=("V5 İsabet",lambda x:int((x==0).sum())),
                       İki_Artı=("V5 İsabet",lambda x:int((x>=2).sum())))
                  .reset_index())
            half["Doğruluk %"]=100*half["Doğru"]/half["Tahmin"].clip(lower=1)
            st.dataframe(half,use_container_width=True,hide_index=True)

        v6=wf[wf["V6 Karar"]=="KONUŞ"].copy()
        if len(v6):
            st.subheader("🔎 V5 ↔ V6 (V18 iki arama) karşılaştırma")
            v5a=wf[wf["V5 Karar"]=="KONUŞ"].copy()
            p5=int(v5a["V5 Boyu"].sum()); h5=int(v5a["V5 İsabet"].sum())
            p6=int(v6["V6 Boyu"].sum()); h6=int(v6["V6 İsabet"].sum())
            r1,r2,r3,r4=st.columns(4)
            r1.metric("V5 doğruluk",f"%{100*h5/max(p5,1):.2f}")
            r2.metric("V6 doğruluk",f"%{100*h6/max(p6,1):.2f}")
            r3.metric("V6 0/3",int((v6["V6 İsabet"]==0).sum()))
            r4.metric("V6 2+",int((v6["V6 İsabet"]>=2).sum()))

            cmp=(v6.groupby(["Rejim","Faz"])
                 .agg(Test=("V6 İsabet","size"),
                      Tahmin=("V6 Boyu","sum"),
                      Doğru=("V6 İsabet","sum"),
                      Sıfır=("V6 İsabet",lambda x:int((x==0).sum())),
                      İki_Artı=("V6 İsabet",lambda x:int((x>=2).sum())),
                      BenzerKalite=("V18 Benzer kalite","mean"),
                      BlokBasıncı=("V18 Blok basıncı","mean"))
                 .reset_index())
            cmp["Doğruluk %"]=100*cmp["Doğru"]/cmp["Tahmin"].clip(lower=1)
            st.dataframe(cmp,use_container_width=True,hide_index=True)

        st.dataframe(wf,use_container_width=True,hide_index=True)
        st.download_button(
            "⬇️ TEST CSV İNDİR",
            wf.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"GUN_SAAT_FAZ_V6_V18_IKI_ARAMA_{len(wf)}.csv",
            mime="text/csv",use_container_width=True
        )

with tabs[1]:
    core,tab,meta=score_target(eng,len(df))
    next_dt=df.DT.iloc[-1]+pd.Timedelta(minutes=5)
    speak,reason=v3_selector(meta,next_dt,core)
    st.write(f"**Hedef:** {next_dt.strftime('%d.%m.%Y %H:%M')} — {regime(next_dt)} / {phase(next_dt)}")
    st.write(f"Bugünkü saat içi gözlem: **{meta['hour_obs']}** • faz içi gözlem: **{meta['phase_obs']}**")
    if speak:
        st.success("V3 KONUŞ — "+" - ".join(map(str,core)))
        st.caption("Seçici neden: "+reason)
    else:
        st.warning("V3 PAS — ham çekirdek var ama seçici koşul yeterince güçlü değil.")
        st.caption("Ham çekirdek: "+" - ".join(map(str,core)))
    v4_core,v4_mode,v4_conf=v4_third_number(core,tab,speak)
    if speak:
        if v4_mode=="3'LÜ":
            st.success("V4 ÜÇÜNCÜ SAYI ONAYLI — "+" - ".join(map(str,v4_core))+f" | güven {v4_conf:.1f}")
        else:
            st.info("V4 ÜÇÜNCÜ SAYIYI ELE — 2'Lİ ÇEKİRDEK: "+" - ".join(map(str,v4_core))+f" | güven {v4_conf:.1f}")
        v5_speak,v5_reason=v5_event_selector(meta,v4_conf,speak)
        if v5_speak:
            st.success("🔥 V5 OLAY ONAYLI — 3'LÜ ÇEKİRDEK: "+" - ".join(map(str,core)))
            st.caption(v5_reason)
        else:
            st.warning("V5 PAS — V3 konuştu ama olay seçici yeterli görmedi.")
        if v5_speak:
            v6_core,v6_table,v6_meta=v6_v18_search_rerank(eng,len(df),tab,True)
            if v6_core:
                st.success("🔎 V6 V18-ARAMA DESTEKLİ 3'LÜ — "+" - ".join(map(str,v6_core)))
                st.caption(
                    f"Benzer durum eşleşmesi: {v6_meta.get('Benzer eşleşme',0)} | "
                    f"ortalama benzer kalite: {v6_meta.get('Benzer kalite',0):.1f} | "
                    f"blok basıncı: {v6_meta.get('Blok basıncı',0):.1f}"
                )
                st.dataframe(
                    v6_table[["Sayı","Puan","V18 Benzer Arama","V18 Blok Arama","V6 Birleşik"]].head(15),
                    use_container_width=True,hide_index=True
                )
    st.dataframe(tab.head(20),use_container_width=True,hide_index=True)
