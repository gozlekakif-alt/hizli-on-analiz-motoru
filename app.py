import streamlit as st
import pandas as pd, numpy as np
from pathlib import Path
from collections import Counter, defaultdict
from math import sqrt, erfc

st.set_page_config(page_title="Hızlı On Şematik Sıra-Ritim",layout="wide")
st.title("Hızlı On — Şematik Sıra / Ritim / Devir Motoru V1")
st.caption("14 gün • 3038 çekiliş • günler ayrı • 0/±1/±2 geometri • sıra imzası • bittiği yerden başlama • walk-forward")
BASE=.25

@st.cache_data
def load():
    rows=[]
    for line in Path('veri.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        a,b,c=line.split(';')
        rows.append((int(a),pd.to_datetime(b,dayfirst=True),tuple(sorted(map(int,c.split(','))))))
    d=pd.DataFrame(rows,columns=['draw_id','dt','nums']).sort_values('draw_id').reset_index(drop=True)
    d['date']=d.dt.dt.strftime('%d.%m.%Y')
    d['pos']=d.groupby('date').cumcount()+1
    return d

def nearest_delta(n, prev):
    # exact first; otherwise nearest prior member. Equal-distance tie is marked ambiguous,
    # but deterministic signed delta uses smaller absolute anchor then smaller anchor.
    if n in prev: return 0, n, False
    ds=[(abs(n-p), n-p, p) for p in prev]
    md=min(x[0] for x in ds); ties=[x for x in ds if x[0]==md]
    ties=sorted(ties,key=lambda x:(abs(x[1]),x[2]))
    x=ties[0]
    return int(x[1]),int(x[2]),len(ties)>1

def transition_rows(d):
    rows=[]
    for day,g in d.groupby('date',sort=False):
        g=g.sort_values('draw_id').reset_index(drop=True)
        for i in range(1,len(g)):
            prev=set(g.loc[i-1,'nums']); cur=set(g.loc[i,'nums'])
            deltas=[]
            for n in sorted(cur):
                de,a,amb=nearest_delta(n,prev); deltas.append(de)
                rows.append(dict(date=day,from_id=int(g.loc[i-1,'draw_id']),draw_id=int(g.loc[i,'draw_id']),pos=int(g.loc[i,'pos']),num=n,anchor=a,delta=de,abs_delta=abs(de),ambiguous=int(amb),real=1))
            c=Counter(deltas)
            yield dict(date=day,from_id=int(g.loc[i-1,'draw_id']),draw_id=int(g.loc[i,'draw_id']),pos=int(g.loc[i,'pos']),
                       same=c[0],m1=c[-1],p1=c[1],m2=c[-2],p2=c[2],near2=sum(v for k,v in c.items() if abs(k)<=2),
                       far=sum(v for k,v in c.items() if abs(k)>=3),mean_delta=np.mean(deltas),signed_seq=' '.join(f'{x:+d}' if x else '0' for x in deltas),
                       dir_seq=''.join('0' if x==0 else ('+' if x>0 else '-') for x in deltas))

@st.cache_data(show_spinner=True)
def build(d):
    t=pd.DataFrame(list(transition_rows(d)))
    # event table again, compact
    er=[]
    for day,g in d.groupby('date',sort=False):
        g=g.sort_values('draw_id').reset_index(drop=True)
        for i in range(1,len(g)):
            prev=set(g.loc[i-1,'nums']); cur=set(g.loc[i,'nums'])
            for n in sorted(cur):
                de,a,amb=nearest_delta(n,prev)
                er.append([day,int(g.loc[i-1,'draw_id']),int(g.loc[i,'draw_id']),int(g.loc[i,'pos']),n,a,de,abs(de),int(amb)])
    e=pd.DataFrame(er,columns=['date','from_id','draw_id','pos','num','anchor','delta','abs_delta','ambiguous'])
    return t,e

def day_summary(t):
    z=t.groupby('date',sort=False).agg(GECIS=('draw_id','size'),AYNI=('same','mean'),EKS1=('m1','mean'),ART1=('p1','mean'),EKS2=('m2','mean'),ART2=('p2','mean'),YAKIN2=('near2','mean'),UZAK=('far','mean'),NET_YON=('mean_delta','mean')).reset_index()
    z['YAKIN2_PAY']=z.YAKIN2/20
    return z

def delta_summary(e):
    x=e[e.abs_delta<=8].groupby('delta').size().rename('N').reset_index(); x['PAY']=x.N/len(e); return x

def ngram_table(e,k=3,min_n=20):
    # per number, within each day: signed nearest-delta history -> next signed delta
    rows=[]
    for (day,n),g in e.groupby(['date','num']):
        g=g.sort_values('draw_id'); a=g.delta.tolist()
        for i in range(k,len(a)):
            pat=tuple(a[i-k:i]); nxt=a[i]; rows.append((pat,nxt))
    if not rows:return pd.DataFrame()
    dd=defaultdict(Counter)
    for p,n in rows:dd[p][n]+=1
    out=[]
    for p,c in dd.items():
        N=sum(c.values())
        if N<min_n:continue
        top,nc=c.most_common(1)[0]
        out.append([str(p),N,top,nc,nc/N,len(c)])
    return pd.DataFrame(out,columns=['SEMA','N','SONRAKI_DELTA','DOGRU','ORAN','FARKLI_SONUC']).sort_values(['ORAN','N'],ascending=False)

def handoff(t):
    # transition-level ending signature -> next transition opening signature
    rows=[]
    for day,g in t.groupby('date',sort=False):
        g=g.sort_values('draw_id').reset_index(drop=True)
        for i in range(len(g)-1):
            a=g.iloc[i]; b=g.iloc[i+1]
            end=(int(np.sign(a.mean_delta)), int(a.near2>=15), int(a.same>=5))
            start=(int(np.sign(b.mean_delta)), int(b.near2>=15), int(b.same>=5))
            rows.append([day,a.draw_id,b.draw_id,str(end),str(start),int(end==start)])
    return pd.DataFrame(rows,columns=['date','draw_id','next_id','BITIS_IMZA','BASLANGIC_IMZA','DEVIR_ESLESME'])

def wf_predict(d, max_abs=2, lookback=30):
    # No-future benchmark: score 1..80 by learned signed-delta frequencies from previous transitions of SAME DAY.
    # First 12 draws warm-up; then predict top20. Compare rolling-frequency baseline.
    out=[]
    for day,g in d.groupby('date',sort=False):
        g=g.sort_values('draw_id').reset_index(drop=True)
        hist=[]
        for i in range(1,len(g)):
            prev=set(g.loc[i-1,'nums']); cur=set(g.loc[i,'nums'])
            if i>=12:
                recent=hist[-lookback:]
                dc=Counter(de for rr in recent for de in rr if abs(de)<=max_abs)
                scores={n:0.0 for n in range(1,81)}
                for n in range(1,81):
                    for p in prev:
                        de=n-p
                        if abs(de)<=max_abs:scores[n]+=dc.get(de,0)+0.1
                pred=sorted(scores,key=lambda n:(scores[n],-n),reverse=True)[:20]
                actual=cur; hit=len(set(pred)&actual)
                # rolling frequency comparator
                past_sets=[set(x) for x in g.loc[max(0,i-lookback):i-1,'nums'].tolist()]
                fc=Counter(n for s in past_sets for n in s); fp=[n for n,_ in sorted(fc.items(),key=lambda x:(-x[1],x[0]))[:20]]
                out.append([day,int(g.loc[i,'draw_id']),i+1,hit,len(set(fp)&actual)])
            hist.append([nearest_delta(n,prev)[0] for n in cur])
    return pd.DataFrame(out,columns=['date','draw_id','pos','SEMA_HIT','FREQ_HIT'])

d=load(); t,e=build(d); ds=day_summary(t); ho=handoff(t); wf=wf_predict(d)
st.success(f"{len(d)} çekiliş • {d.date.nunique()} gün • #{d.draw_id.min()}→#{d.draw_id.max()} • {len(t)} gün-içi geçiş")

tabs=st.tabs(['14 Gün Kontrol','Gün Kadavrası','± Yön Geometrisi','Sıra/Ritim N-Gram','Devir: Bittiği Yerden','Walk-Forward','Event Log','MASTER'])
with tabs[0]:
    st.subheader('14 gün tek tek')
    st.dataframe(ds,use_container_width=True,height=520)
    st.write('Genel ortalama yakınlık (0/±1/±2):',round(t.near2.mean(),3),'/20')
with tabs[1]:
    day=st.selectbox('Gün',d.date.drop_duplicates().tolist())
    z=t[t.date==day].copy(); st.dataframe(z[['pos','from_id','draw_id','same','m1','p1','m2','p2','near2','far','mean_delta']],use_container_width=True,height=560)
    st.caption('same=aynı; m1=-1; p1=+1; m2=-2; p2=+2. Her satır yalnız önceki çekilişi kullanır.')
with tabs[2]:
    st.dataframe(delta_summary(e),use_container_width=True,height=500)
    st.dataframe(e.groupby('date').agg(N=('num','size'),AMBIGUOUS=('ambiguous','sum'),ORT_ABS=('abs_delta','mean')).reset_index(),use_container_width=True)
with tabs[3]:
    k=st.slider('Şema uzunluğu',2,6,3); mn=st.slider('Minimum olay',10,200,30,10)
    ng=ngram_table(e,k,mn); st.dataframe(ng.head(500),use_container_width=True,height=600)
    st.caption('Bu tablo keşif tablosudur; yüksek oran tek başına ileri-tahmin kanıtı değildir.')
with tabs[4]:
    q=ho.groupby(['BITIS_IMZA','BASLANGIC_IMZA']).size().rename('N').reset_index().sort_values('N',ascending=False)
    st.metric('Aynı imzanın sonraki geçişte devam oranı',f"{ho.DEVIR_ESLESME.mean()*100:.2f}%")
    st.dataframe(q.head(300),use_container_width=True,height=550)
with tabs[5]:
    s=wf.groupby('date').agg(N=('draw_id','size'),SEMA_ORT=('SEMA_HIT','mean'),FREQ_ORT=('FREQ_HIT','mean'),SEMA_MAX=('SEMA_HIT','max'),FREQ_MAX=('FREQ_HIT','max')).reset_index()
    st.dataframe(s,use_container_width=True,height=500)
    st.metric('Şema motoru ortalama isabet',f"{wf.SEMA_HIT.mean():.3f}/20")
    st.metric('Rolling frekans ortalama isabet',f"{wf.FREQ_HIT.mean():.3f}/20")
    st.caption('Walk-forward: her gün ilk 12 çekiliş ısınma; sonraki elde yalnız geçmiş kullanılır. Rastgele teorik beklenti 5/20.')
with tabs[6]:
    st.dataframe(e,use_container_width=True,height=600)
    st.download_button('Event CSV',e.to_csv(index=False).encode('utf-8-sig'),'SEMA_SIRA_EVENT.csv','text/csv')
with tabs[7]:
    parts=['HIZLI ON SEMATIK SIRA RITIM MASTER V1',f'CEKILIS={len(d)}|GUN={d.date.nunique()}|BAS={d.draw_id.min()}|SON={d.draw_id.max()}',
           'KURAL=GUNLER_AYRI|NO_FUTURE=EVET|BASELINE_HIT=5/20','', '=== 14 GUN ===',ds.to_csv(index=False),
           '=== DELTA ===',delta_summary(e).to_csv(index=False),'=== DEVIR ===',ho.groupby(['BITIS_IMZA','BASLANGIC_IMZA']).size().rename('N').reset_index().to_csv(index=False),
           '=== WALK_FORWARD ===',wf.groupby('date').agg(N=('draw_id','size'),SEMA_ORT=('SEMA_HIT','mean'),FREQ_ORT=('FREQ_HIT','mean'),SEMA_MAX=('SEMA_HIT','max'),FREQ_MAX=('FREQ_HIT','max')).reset_index().to_csv(index=False)]
    master='\n'.join(parts)
    st.download_button('MASTER TXT',master.encode('utf-8'),'SEMA_SIRA_RITIM_MASTER_V1.txt','text/plain')
    st.text_area('MASTER önizleme',master[:30000],height=600)
