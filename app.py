import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations
from math import sqrt,erfc
st.set_page_config(page_title='Hızlı On Kademeli Laboratuvar',layout='wide')
st.title('Hızlı On — Kademeli H / Ritim / Aile Laboratuvarı V3')
st.caption('Ağır analizler yalnız ilgili düğmeye basılınca çalışır. 14 gün tek zincir; hedef çekilişin sonucu hiçbir özellikte kullanılmaz.')
@st.cache_data(show_spinner=False)
def load():
    rows=[]
    for line in Path(__file__).with_name('veri.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        a,b,c=line.split(';');nums=frozenset(map(int,c.split(',')))
        if len(nums)!=20 or min(nums)<1 or max(nums)>80:raise ValueError('Geçersiz çekiliş: '+a)
        rows.append((int(a),pd.to_datetime(b,dayfirst=True),nums))
    d=pd.DataFrame(rows,columns=['draw_id','dt','nums']).sort_values('draw_id').reset_index(drop=True)
    if d.draw_id.duplicated().any():raise ValueError('Tekrarlı çekiliş no')
    d['date']=d.dt.dt.strftime('%Y-%m-%d');return d
@st.cache_data(show_spinner=False)
def compact(d):
    # Tek seferde yalnız 80 x 3038 boolean: 79 sosyal sütunu YOK.
    a=np.zeros((len(d),80),dtype=np.uint8)
    for t,ns in enumerate(d.nums):a[t,np.fromiter((n-1 for n in ns),dtype=int)]=1
    return a
@st.cache_data(show_spinner=False)
def basic(d,a):
    # H/mask ve G1 taraması: sosyal aile kombinasyonu hesaplanmaz.
    out=[]
    for t in range(8,len(d)):
        h=a[t-8:t][::-1];bits=[''.join(map(str,h[:,n].tolist())) for n in range(80)]
        for n,m in enumerate(bits):out.append((int(d.draw_id.iat[t]),d.date.iat[t],n+1,m,int(a[t,n]),int(m=='10000000')))
    return pd.DataFrame(out,columns=['draw_id','date','num','mask','REAL','G1'])
@st.cache_data(show_spinner=False)
def target_events(d,a,num):
    # Sosyal özellikleri SADECE seçilen tek hedef için hesapla: ~3030 x 79.
    n=num-1;out=[]
    for t in range(8,len(d)):
        h=a[t-8:t][::-1];mask=''.join(map(str,h[:,n].tolist()))
        if mask!='10000000':continue
        counts=h.sum(axis=0);hc=np.bincount(counts,minlength=9);hc[counts[n]]-=1
        ages=np.full(80,9,dtype=np.uint8)
        for lag in range(8,0,-1):ages[a[t-lag].astype(bool)]=lag
        gap=next((lag-1 for lag in range(2,min(t,101)) if a[t-lag,n]),np.nan)
        r={'Event_ID':f'{int(d.draw_id.iat[t])}-{num:02d}','draw_id':int(d.draw_id.iat[t]),'date':d.date.iat[t], 'num':num,'mask':mask,'return_gap':gap,'REAL':int(a[t,n]),'NEGATIVE':int(1-a[t,n])}
        for k in range(9):r[f'HC{k}']=int(hc[k])
        for other in range(1,81):
            if other!=num:r[f'A{other}']=int(ages[other-1])
        out.append(r)
    return pd.DataFrame(out)
def family_discovery(g,num,min_n=10,pool_size=10,max_size=5):
    if len(g)<min_n or g.REAL.nunique()<2:return pd.DataFrame()
    rank=[]
    for other in range(1,81):
        if other==num:continue
        live=g[f'A{other}'].le(8)
        diff=live[g.REAL.eq(1)].mean()-live[g.REAL.eq(0)].mean()
        rank.append((diff,other))
    pool=[n for _,n in sorted(rank,reverse=True)[:pool_size]]
    live={n:g[f'A{n}'].le(8).to_numpy() for n in pool};res=[]
    for size in range(2,max_size+1):
        for fam in combinations(pool,size):
            yes=np.logical_and.reduce([live[n] for n in fam]);z=g.loc[yes]
            if len(z)<min_n:continue
            res.append({'AILE':'-'.join(map(str,fam)),'BOYUT':size,'N':len(z),'REAL':int(z.REAL.sum()),'ORAN':z.REAL.mean(),'ANA_ORAN':g.REAL.mean(),'EK_KAZANC':z.REAL.mean()-g.REAL.mean()})
    return pd.DataFrame(res).sort_values(['EK_KAZANC','N'],ascending=[False,False]) if res else pd.DataFrame()
def apply(g,fam):
    members=[int(x) for x in fam.split('-')];z=g.copy()
    for n in members:z=z[z[f'A{n}'].le(8)]
    if len(z):
        ages=z[[f'A{n}' for n in members]]
        z['CAPA_YAS']=ages.max(axis=1);z['TAZE_1_3']=ages.le(3).sum(axis=1)
    return z

d=load();st.success(f'{len(d)} çekiliş • #{d.draw_id.iat[0]} → #{d.draw_id.iat[-1]} • {d.date.nunique()} gün')
a=compact(d)
st.info('Aşama seç: Genel H/G→1 → Tek sayı kadavra → Aile keşfi → 10+4 test → Rolling. Her aşama ayrı düğmeyle başlar.')
mode=st.radio('Çalıştırılacak aşama',['1 · Genel H / G→1 (hafif)','2 · Tek sayı / çevre (hafif)','3 · Aile keşfi (tek sayı)','4 · Dondurulmuş 10+4 (tek sayı)','5 · Rolling (tek sayı)'],horizontal=False)
num=st.number_input('Hedef sayı',1,80,74,1)
if mode.startswith('1'):
    if st.button('Genel taramayı çalıştır',type='primary'):
        with st.spinner('Kompakt 1–80 olay kütüğü hesaplanıyor'):
            ev=basic(d,a);g=ev[ev.G1.eq(1)];summary=g.groupby('num').REAL.agg(N='size',REAL='sum').reset_index();summary['ORAN']=summary.REAL/summary.N;summary['LIFT25']=summary.ORAN/.25
            st.session_state['general']=summary
    if 'general' in st.session_state:
        st.dataframe(st.session_state.general,hide_index=True);st.download_button('G1 özeti CSV',st.session_state.general.to_csv(index=False).encode('utf-8-sig'),'G1_1_80.csv')
else:
    if st.button('Seçilen aşamayı çalıştır',type='primary'):
        with st.spinner(f'{num} için olaylar hazırlanıyor'):
            ev=target_events(d,a,num);days=d.date.drop_duplicates().tolist();tr=ev[ev.date.isin(days[:10])];te=ev[ev.date.isin(days[10:])]
            st.session_state['result']=None
            if mode.startswith('2'):
                st.session_state['result']=('events',ev)
            elif mode.startswith('3'):
                st.session_state['result']=('family',family_discovery(tr,num))
            elif mode.startswith('4'):
                fc=family_discovery(tr,num);rows=[]
                if len(fc):
                    for _,r in fc.head(20).iterrows():
                        x=apply(tr,r.AILE);y=apply(te,r.AILE)
                        rows.append({'AILE':r.AILE,'TRAIN_N':len(x),'TRAIN_REAL':int(x.REAL.sum()),'TEST_N':len(y),'TEST_REAL':int(y.REAL.sum()),'TEST_ORAN':y.REAL.mean() if len(y) else np.nan,'TEST_BASE_N':len(te),'TEST_BASE_REAL':int(te.REAL.sum())})
                st.session_state['result']=('frozen',pd.DataFrame(rows))
            else:
                rows=[]
                for i in range(6,len(days)):
                    tr_i=ev[ev.date.isin(days[:i])];te_i=ev[ev.date.eq(days[i])];fc=family_discovery(tr_i,num,min_n=8,pool_size=8,max_size=4)
                    if len(fc):
                        fam=fc.iloc[0].AILE;z=apply(te_i,fam)
                        rows.append({'TEST_GUN':days[i],'DONDURULAN_AILE':fam,'N':len(z),'REAL':int(z.REAL.sum()),'BASE_N':len(te_i),'BASE_REAL':int(te_i.REAL.sum())})
                st.session_state['result']=('rolling',pd.DataFrame(rows))
            st.session_state['selection']=(mode,num)
    if st.session_state.get('selection')==(mode,num) and st.session_state.get('result') is not None:
        kind,res=st.session_state.result
        if res.empty:st.warning('Bu koşullarda yeterli olay/kural yok.')
        else:
            if kind=='events':
                st.metric('G→1 fırsat',len(res));st.metric('REAL',int(res.REAL.sum()));st.metric('REAL oranı',f'{res.REAL.mean():.2%}')
                st.dataframe(res[['Event_ID','date','mask','return_gap','REAL','NEGATIVE']+[f'HC{k}' for k in range(9)]],hide_index=True)
            elif kind=='rolling':
                st.metric('İleri test toplamı',f'{int(res.REAL.sum())}/{int(res.N.sum())}' if res.N.sum() else '0/0')
                st.caption('Her günün aile kuralı yalnız önceki günlerden seçilir. Bu tabloda keşif yüzdeleri başarı olarak gösterilmez.')
                st.dataframe(res,hide_index=True)
            else:
                st.caption('Aile seçimi keşif verisindendir; çoklu denemeler nedeniyle keşif oranı doğrulanmış başarı değildir.')
                st.dataframe(res,hide_index=True)
            st.download_button('Bu aşamanın CSV dosyasını indir',res.to_csv(index=False).encode('utf-8-sig'),f'KADAVRA_{num}_{kind}.csv','text/csv')
