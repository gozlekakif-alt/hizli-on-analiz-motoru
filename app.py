import streamlit as st
import pandas as pd, numpy as np
from pathlib import Path
from math import sqrt, erfc
from itertools import combinations
from collections import Counter

st.set_page_config(page_title='Hızlı On H/Ritim/Aile Kadavra V2',layout='wide')
st.title('Hızlı On — H / Ritim / Aile Kadavra Motoru V2')
st.caption('3038 çekiliş tek zincir • 1–80 • Event_ID • no-leakage • aile/çapa/tazelik • frozen validation • rolling walk-forward')
BASE=.25

def wilson(k,n):
    if not n:return np.nan,np.nan
    z=1.95996398454;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*sqrt((p*(1-p)+z*z/(4*n))/n)/d
    return max(0,c-h),min(1,c+h)
def pval(k,n):
    if not n:return np.nan
    z=(k-n*BASE)/sqrt(n*BASE*(1-BASE));return erfc(abs(z)/sqrt(2))
def bh(p):
    p=np.nan_to_num(np.asarray(p,float),nan=1.);m=len(p)
    if not m:return p
    o=np.argsort(p);a=p[o]*m/np.arange(1,m+1);a=np.minimum.accumulate(a[::-1])[::-1];q=np.empty(m);q[o]=np.minimum(a,1);return q
def addstats(x,n='N',k='REAL'):
    x=x.copy();x['ORAN']=x[k]/x[n];x['LIFT25']=x.ORAN/BASE
    ci=[wilson(int(a),int(b)) for b,a in zip(x[n],x[k])];x['CI_ALT']=[a for a,b in ci];x['CI_UST']=[b for a,b in ci];x['p']= [pval(int(a),int(b)) for b,a in zip(x[n],x[k])];x['q_BH']=bh(x.p);return x
@st.cache_data
def load():
    rows=[]
    for line in Path('veri.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        a,b,c=line.split(';'); rows.append((int(a),pd.to_datetime(b,dayfirst=True),frozenset(map(int,c.split(',')))))
    d=pd.DataFrame(rows,columns=['draw_id','dt','nums']).sort_values('draw_id').reset_index(drop=True)
    d['date']=d.dt.dt.date.astype(str);d['hour']=d.dt.dt.hour;d['phase']=pd.cut(d.hour,[-1,5,11,16,20,23],labels=['00-05','06-11','12-16','17-20','21-23']).astype(str)
    return d
@st.cache_data(show_spinner=True)
def build_events(d):
    sets=d.nums.tolist(); rows=[]
    for t in range(8,len(d)):
        # target-level pre-draw features
        masks={}; hcnt={}; ages={}
        for n in range(1,81):
            bits=tuple(int(n in sets[t-h]) for h in range(1,9));m=''.join(map(str,bits));masks[n]=m;hcnt[n]=sum(bits)
            ages[n]=next((h for h in range(1,min(t,80)+1) if n in sets[t-h]),81)
        hc=Counter(hcnt.values())
        prev=sets[t-1]
        # geometry of previous draw only (prior)
        consec=sum(1 for n in prev if n+1 in prev)
        bands=Counter((n-1)//10 for n in prev);suffix=Counter(n%10 for n in prev)
        for n in range(1,81):
            m=masks[n]; real=int(n in sets[t]);
            # return gap before H1 hit; meaningful for G1
            gap=next((h-1 for h in range(2,min(t,100)+1) if n in sets[t-h]),np.nan) if m[0]=='1' else np.nan
            r={'Event_ID':f'{int(d.draw_id.iloc[t])}-{n:02d}','t':t,'draw_id':int(d.draw_id.iloc[t]),'dt':d.dt.iloc[t],'date':d.date.iloc[t],'hour':int(d.hour.iloc[t]),'phase':d.phase.iloc[t],'num':n,'mask':m,'H_count':hcnt[n],'REAL':real,'NEGATIVE':1-real,'G1':int(m=='10000000'),'return_gap':gap,'prev_consec':consec,'prev_band_max':max(bands.values()),'prev_suffix_max':max(suffix.values())}
            for k in range(9):r[f'HC{k}']=hc[k]-(1 if hcnt[n]==k else 0)
            # compact social representation: last age 1..8, 9 absent
            for o in range(1,81):
                if o!=n:r[f'A{o}']=ages[o] if ages[o]<=8 else 9
            rows.append(r)
    return pd.DataFrame(rows)

def family_candidates(train,target,min_base=25,min_family=12,max_members=5,top_social=12):
    g=train[(train.num==target)&(train.G1==1)]
    if len(g)<min_base:return pd.DataFrame()
    # rank social members by REAL-vs-NEG live difference, discovery only
    rank=[]
    for o in range(1,81):
        if o==target:continue
        live=(g[f'A{o}']<=8)
        a=live[g.REAL==1].mean() if (g.REAL==1).any() else 0;b=live[g.REAL==0].mean() if (g.REAL==0).any() else 0
        rank.append((abs(a-b),a-b,o))
    pool=[o for _,_,o in sorted(rank,reverse=True)[:top_social]]
    out=[]
    for size in range(2,max_members+1):
        for fam in combinations(pool,size):
            z=g[np.logical_and.reduce([(g[f'A{o}']<=8).to_numpy() for o in fam])]
            if len(z)<min_family:continue
            rate=z.REAL.mean();out.append([target,'-'.join(map(str,fam)),size,len(g),int(g.REAL.sum()),len(z),int(z.REAL.sum()),rate,rate-g.REAL.mean()])
    if not out:return pd.DataFrame()
    x=pd.DataFrame(out,columns=['SAYI','AILE','BOYUT','BASE_N','BASE_REAL','N','REAL','ORAN','EK_KAZANC']);x['p']= [pval(k,n) for n,k in zip(x.N,x.REAL)];x['q_BH']=bh(x.p);return x.sort_values(['EK_KAZANC','N'],ascending=[False,False])

def apply_family(df,target,fam):
    z=df[(df.num==target)&(df.G1==1)].copy(); members=list(map(int,fam.split('-')))
    if z.empty:return z
    live=np.logical_and.reduce([(z[f'A{o}']<=8).to_numpy() for o in members]);z=z[live].copy()
    ages=np.column_stack([z[f'A{o}'].to_numpy() for o in members]);z['AILE_CANLI']=len(members);z['CAPA_YAS']=ages.max(axis=1);z['TAZE_1_3']=np.sum(ages<=3,axis=1);z['TAMAMLANMA_YASI']=ages.max(axis=1);return z

def frozen_10_4(ev,d):
    days=list(d.date.drop_duplicates());train_days=set(days[:10]);test_days=set(days[10:]);rows=[]
    for n in range(1,81):
        tr=ev[ev.date.isin(train_days)];te=ev[ev.date.isin(test_days)]
        fc=family_candidates(tr,n)
        if fc.empty:continue
        best=fc.iloc[0];fam=best.AILE
        a=apply_family(tr,n,fam);b=apply_family(te,n,fam)
        rows.append([n,fam,int(best.BOYUT),len(a),int(a.REAL.sum()),len(b),int(b.REAL.sum()),len(te[(te.num==n)&(te.G1==1)]),int(te[(te.num==n)&(te.G1==1)].REAL.sum())])
    x=pd.DataFrame(rows,columns=['SAYI','DONDURULAN_AILE','BOYUT','TRAIN_N','TRAIN_REAL','TEST_N','TEST_REAL','TEST_BASE_N','TEST_BASE_REAL'])
    if len(x):x['TRAIN_ORAN']=x.TRAIN_REAL/x.TRAIN_N;x['TEST_ORAN']=x.TEST_REAL/x.TEST_N.replace(0,np.nan);x['TEST_BASE_ORAN']=x.TEST_BASE_REAL/x.TEST_BASE_N.replace(0,np.nan);x['TEST_EK_KAZANC']=x.TEST_ORAN-x.TEST_BASE_ORAN
    return x

def rolling(ev,d):
    days=list(d.date.drop_duplicates());rows=[]
    for i in range(6,len(days)):
        tr=ev[ev.date.isin(days[:i])];te=ev[ev.date==days[i]]
        for n in range(1,81):
            fc=family_candidates(tr,n,min_base=18,min_family=8,max_members=4,top_social=10)
            if fc.empty:continue
            best=fc.iloc[0];fam=best.AILE;z=apply_family(te,n,fam);base=te[(te.num==n)&(te.G1==1)]
            rows.append([days[i],n,fam,int(best.BOYUT),len(z),int(z.REAL.sum()),len(base),int(base.REAL.sum())])
    x=pd.DataFrame(rows,columns=['TEST_GUN','SAYI','AILE','BOYUT','N','REAL','BASE_N','BASE_REAL'])
    if len(x):
        s=x.groupby('SAYI').agg(TEST_N=('N','sum'),TEST_REAL=('REAL','sum'),BASE_N=('BASE_N','sum'),BASE_REAL=('BASE_REAL','sum')).reset_index();s['TEST_ORAN']=s.TEST_REAL/s.TEST_N.replace(0,np.nan);s['BASE_ORAN']=s.BASE_REAL/s.BASE_N.replace(0,np.nan);s['EK_KAZANC']=s.TEST_ORAN-s.BASE_ORAN
    else:s=pd.DataFrame()
    return x,s

d=load();st.success(f'{len(d)} çekiliş • #{d.draw_id.iloc[0]}→#{d.draw_id.iloc[-1]} • {d.date.nunique()} gün • tek zincir')
ev=build_events(d)
g1=ev[ev.G1==1];g1sum=addstats(g1.groupby('num').REAL.agg(N='size',REAL='sum').reset_index().rename(columns={'num':'SAYI'}))
mask=addstats(ev.groupby(['num','mask']).REAL.agg(N='size',REAL='sum').reset_index().rename(columns={'num':'SAYI','mask':'MASKE'}))
hs=[]
for h in range(1,9):
    z=ev[ev['mask'].str[h-1]=='1'];q=z.groupby('num').REAL.agg(N='size',REAL='sum').reset_index();q['H']=f'H{h}';hs.append(q)
hsum=addstats(pd.concat(hs).rename(columns={'num':'SAYI'}))
frozen=frozen_10_4(ev,d);roll,rollsum=rolling(ev,d)

tabs=st.tabs(['G→1 1–80','H1–H8 / Mask','Aile Kadavrası','10G→4G Frozen','Rolling Aile','Çapa/Tazelik','Geometri','Event Log','MASTER'])
with tabs[0]:st.dataframe(g1sum.sort_values(['q_BH','ORAN'],ascending=[True,False]),use_container_width=True,height=650)
with tabs[1]:
    n=st.selectbox('Sayı',range(1,81),index=73);st.dataframe(hsum[hsum.SAYI==n].sort_values('H'),use_container_width=True);st.dataframe(mask[(mask.SAYI==n)&(mask.N>=20)].sort_values('ORAN',ascending=False),use_container_width=True,height=420)
with tabs[2]:
    n=st.selectbox('Sayı ',range(1,81),index=73,key='fam');fc=family_candidates(ev[ev.date.isin(list(d.date.drop_duplicates())[:10])],n)
    st.caption('Aileler yalnız ilk 10 günde keşfedilir; burada gösterilen oran keşiftir, doğrulama değildir.')
    st.dataframe(fc.head(200),use_container_width=True,height=600)
with tabs[3]:st.dataframe(frozen.sort_values(['TEST_ORAN','TEST_N'],ascending=[False,False]),use_container_width=True,height=650)
with tabs[4]:
    st.dataframe(rollsum[rollsum.TEST_N>=5].sort_values(['TEST_ORAN','TEST_N'],ascending=[False,False]),use_container_width=True,height=420);st.dataframe(roll,use_container_width=True,height=350)
with tabs[5]:
    n=st.selectbox('Sayı  ',range(1,81),index=73,key='anchor');row=frozen[frozen.SAYI==n]
    if len(row):
        fam=row.iloc[0].DONDURULAN_AILE;z=apply_family(ev[ev.date.isin(list(d.date.drop_duplicates())[10:])],n,fam);st.write('Dondurulmuş aile:',fam)
        if len(z):st.dataframe(z.groupby(['CAPA_YAS','TAZE_1_3']).REAL.agg(N='size',REAL='sum').reset_index().assign(ORAN=lambda x:x.REAL/x.N),use_container_width=True)
with tabs[6]:
    n=st.selectbox('Sayı   ',range(1,81),index=73,key='geo');z=g1[g1.num==n];cols=['HC0','HC1','HC2','HC3','HC4','HC5','HC6','HC7','HC8','prev_consec','prev_band_max','prev_suffix_max'];out=[]
    for c in cols:out.append([c,z[z.REAL==1][c].mean(),z[z.REAL==0][c].mean()]);o=pd.DataFrame(out,columns=['OZELLIK','REAL_ORT','NEG_ORT']);o['FARK']=o.REAL_ORT-o.NEG_ORT;st.dataframe(o.sort_values('FARK',key=lambda s:s.abs(),ascending=False),use_container_width=True)
with tabs[7]:
    keep=['Event_ID','draw_id','dt','date','hour','phase','num','mask','H_count','G1','return_gap','REAL','NEGATIVE']+[f'HC{k}' for k in range(9)];st.dataframe(ev[keep],use_container_width=True,height=600);st.download_button('EVENT CSV',ev[keep].to_csv(index=False).encode('utf-8-sig'),'H_RITIM_AILE_EVENT_V2.csv','text/csv')
with tabs[8]:
    parts=['HIZLI ON H/RITIM/AILE KADAVRA MASTER V2',f'CEKILIS={len(d)}|BAS={d.draw_id.iloc[0]}|SON={d.draw_id.iloc[-1]}|GUN={d.date.nunique()}','TEK_ZINCIR=EVET|NO_LEAKAGE=EVET|BASELINE=0.25','', '=== G1 1-80 ===',g1sum.to_csv(index=False),'=== H1-H8 ===',hsum.to_csv(index=False),'=== EXACT MASK ===',mask.to_csv(index=False),'=== 10G-4G FROZEN AILE ===',frozen.to_csv(index=False),'=== ROLLING AILE OZET ===',rollsum.to_csv(index=False) if len(rollsum) else '','=== ROLLING GUNLUK ===',roll.to_csv(index=False) if len(roll) else '']
    master='\n'.join(parts);st.download_button('MASTER TXT',master.encode('utf-8'),'H_RITIM_AILE_MASTER_V2.txt','text/plain');st.text_area('MASTER önizleme',master[:25000],height=600)
