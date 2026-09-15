import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations
from math import erfc, sqrt

st.set_page_config(page_title="H1-H8 Tetikleyici V3",layout="wide")
st.title("Hızlı On — 1–80 H Tetikleyici Laboratuvarı V3")
st.caption("14 gün TEK ZİNCİR • 1–80 × H-maskesi • REAL/NEGATIVE ayrımı • diğer 79 sayının pre-draw H geometrisi • ikinci tetikleyici • no-leakage")
BASE=.25

def ci95(k,n):
    if not n:return (np.nan,np.nan)
    p=k/n; z=1.95996398454; den=1+z*z/n
    c=(p+z*z/(2*n))/den; h=z*sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return max(0,c-h),min(1,c+h)
def pval(k,n,p0=BASE):
    if not n:return np.nan
    z=(k-n*p0)/sqrt(n*p0*(1-p0))
    return erfc(abs(z)/sqrt(2))
def add_stats(d,ncol='Aday',kcol='REAL'):
    d=d.copy(); d['Başarı']=d[kcol]/d[ncol]; d['Lift']=d['Başarı']/BASE
    cis=[ci95(int(k),int(n)) for n,k in zip(d[ncol],d[kcol])]
    d['CI95_alt']=[x[0] for x in cis]; d['CI95_üst']=[x[1] for x in cis]
    d['p']= [pval(int(k),int(n)) for n,k in zip(d[ncol],d[kcol])]
    # Benjamini-Hochberg q
    ok=d['p'].notna(); vals=d.loc[ok,'p'].to_numpy(); m=len(vals)
    q=np.full(m,np.nan)
    if m:
        order=np.argsort(vals); ranked=vals[order]; adj=ranked*m/np.arange(1,m+1); adj=np.minimum.accumulate(adj[::-1])[::-1]; adj=np.clip(adj,0,1); q[order]=adj
    d.loc[ok,'q_BH']=q
    return d

@st.cache_data
def load():
    rows=[]
    for line in Path('veri.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        a,b,c=line.split(';'); rows.append((int(a),pd.to_datetime(b,dayfirst=True),set(map(int,c.split(',')))))
    d=pd.DataFrame(rows,columns=['draw_id','dt','nums']).sort_values('draw_id').reset_index(drop=True)
    d['date']=d.dt.dt.date.astype(str); d['hour']=d.dt.dt.hour
    return d

@st.cache_data(show_spinner=True)
def analyze(df):
    sets=df.nums.tolist(); rows=[]
    # Common warm-up t=8 gives every event a full H1..H8 pre-state.
    for t in range(8,len(df)):
        actual=sets[t]
        for num in range(1,81):
            bits=[int(num in sets[t-h]) for h in range(1,9)]
            mask=''.join(map(str,bits)); real=int(num in actual)
            post=str(real)+mask[:7] # state immediately AFTER target is revealed
            sleep=0
            for h in range(1,t+1):
                if num in sets[t-h]: break
                sleep+=1
            rows.append({'Event_ID':f"{int(df.draw_id.iloc[t])}-{num:02d}",'target_draw_id':int(df.draw_id.iloc[t]),
              'target_dt':df.dt.iloc[t],'date':df.date.iloc[t],'hour':int(df.hour.iloc[t]),'num':num,
              **{f'H{h}':bits[h-1] for h in range(1,9)},'pre_mask':mask,'H_count':sum(bits),
              'pre_sleep':sleep,'REAL':real,'NEGATIVE':1-real,'post_mask':post})
    ev=pd.DataFrame(rows)
    # singles
    s=[]
    for h in range(1,9):
        x=ev[ev[f'H{h}']==1]; s.append([f'H{h}',len(x),int(x.REAL.sum())])
    single=add_stats(pd.DataFrame(s,columns=['Test','Aday','REAL']))
    # all intersections 2..4
    cr=[]
    for r in (2,3,4):
      for hs in combinations(range(1,9),r):
        x=ev
        for h in hs:x=x[x[f'H{h}']==1]
        cr.append(['+'.join(f'H{h}' for h in hs),r,len(x),int(x.REAL.sum())])
    combo=add_stats(pd.DataFrame(cr,columns=['Test','Boyut','Aday','REAL']))
    # exact masks
    p=ev.groupby('pre_mask').REAL.agg(Aday='size',REAL='sum').reset_index(); paths=add_stats(p); paths['H_count']=paths.pre_mask.str.count('1')
    # pre_mask -> post_mask transitions (post is descriptive after reveal)
    mt=ev.groupby(['pre_mask','post_mask']).REAL.agg(Aday='size',REAL='sum').reset_index(); mt=add_stats(mt)
    # Number x H fingerprint
    nr=[]
    for num,g in ev.groupby('num'):
      for h in range(1,9):
        x=g[g[f'H{h}']==1]; nr.append([num,f'H{h}',len(x),int(x.REAL.sum())])
    nh=add_stats(pd.DataFrame(nr,columns=['Sayı','H','Aday','REAL']))
    # number x exact mask; require filtering in UI, stats retained for all observed
    nm=ev.groupby(['num','pre_mask']).REAL.agg(Aday='size',REAL='sum').reset_index(); nm=add_stats(nm)
    # predictive sleep hazard: BEFORE target, absent exactly g draws; does it return now?
    hz=ev.groupby(['pre_sleep']).REAL.agg(Aday='size',REAL='sum').reset_index(); hz=add_stats(hz); hz=hz.rename(columns={'pre_sleep':'Uyku'})
    nhz=ev.groupby(['num','pre_sleep']).REAL.agg(Aday='size',REAL='sum').reset_index(); nhz=add_stats(nhz); nhz=nhz.rename(columns={'num':'Sayı','pre_sleep':'Uyku'})
    # binary prior paths length 2..8 are identical to suffixes of H state, but explicitly report them.
    pr=[]
    for L in range(2,9):
      col='path'+str(L); tmp=ev[['num','REAL','pre_mask','date']].copy(); tmp[col]=tmp.pre_mask.str[:L]
      a=tmp.groupby(col).REAL.agg(Aday='size',REAL='sum').reset_index().rename(columns={col:'Geçmiş_Yol'}); a['Yol_Uzunluğu']=L; pr.append(a)
    rhythm=add_stats(pd.concat(pr,ignore_index=True))
    # number-specific prior paths
    npr=[]
    for L in range(2,9):
      tmp=ev[['num','REAL','pre_mask']].copy(); tmp['Geçmiş_Yol']=tmp.pre_mask.str[:L]
      a=tmp.groupby(['num','Geçmiş_Yol']).REAL.agg(Aday='size',REAL='sum').reset_index(); a['Yol_Uzunluğu']=L; npr.append(a)
    nrhythm=add_stats(pd.concat(npr,ignore_index=True)).rename(columns={'num':'Sayı'})
    # day consistency for singles, exact masks, and number-H fingerprints
    day=[]
    for h in range(1,9):
      for d,g in ev[ev[f'H{h}']==1].groupby('date'): day.append([f'H{h}',d,len(g),int(g.REAL.sum())])
    daily=add_stats(pd.DataFrame(day,columns=['Test','Tarih','Aday','REAL']))
    # fingerprint summary per number: best/worst H using large n automatically
    fp=[]
    for num,g in nh.groupby('Sayı'):
      b=g.sort_values('Başarı',ascending=False).iloc[0]; w=g.sort_values('Başarı').iloc[0]
      fp.append([num,b.H,b.Başarı,b.Lift,b.q_BH,w.H,w.Başarı,w.Lift,w.q_BH,float(b.Başarı-w.Başarı)])
    fingerprint=pd.DataFrame(fp,columns=['Sayı','En_güçlü_H','Güçlü_oran','Güçlü_lift','Güçlü_q','En_zayıf_H','Zayıf_oran','Zayıf_lift','Zayıf_q','H_farkı'])
    # PRE-DRAW environment for every target draw: other-79 comparisons can be built by subtraction.
    env=[]
    for did,g in ev.groupby('target_draw_id',sort=False):
      row={'target_draw_id':did}
      for h in range(1,9): row[f'ALL_H{h}']=int(g[f'H{h}'].sum())
      hc=g['H_count'].value_counts()
      for k in range(0,9): row[f'ALL_HC{k}']=int(hc.get(k,0))
      mc=g['pre_mask'].value_counts()
      row['MASK_COUNTS']=mc.to_dict()
      env.append(row)
    env=pd.DataFrame(env)
    return ev,single,combo,paths,mt,nh,nm,hz,nhz,rhythm,nrhythm,daily,fingerprint,env

df=load(); st.success(f"{len(df)} çekiliş • #{df.draw_id.iloc[0]}→#{df.draw_id.iloc[-1]} • {df.date.nunique()} gün • TEK ZİNCİR")
st.info("No-leakage: pre_mask, H1–H8 ve pre_sleep yalnız hedef çekilişten ÖNCE bilinen sonuçlardan hesaplanır. REAL/NEGATIVE daha sonra doğrulama için eklenir.")
if st.button('H1→H8 KADAVRA V2 ANALİZİNİ ÇALIŞTIR',type='primary'):
  st.session_state['R']=analyze(df)
if 'R' in st.session_state:
 ev,single,combo,paths,mt,nh,nm,hz,nhz,rhythm,nrhythm,daily,fingerprint,env=st.session_state['R']
 tabs=st.tabs(['H1-H8','H Kombinasyon','Tam 256 Maske','Maske→Maske','1–80 Parmak İzi','Sayı Kadavrası','1–80 İkinci Tetikleyici','Uyku Hazard','Dönüş Yolları','Gün Tutarlılığı','Event Kütüğü','MASTER'])
 with tabs[0]: st.dataframe(single,use_container_width=True)
 with tabs[1]:
  n=st.slider('Minimum aday',20,3000,200,20,key='cmin'); st.dataframe(combo[combo.Aday>=n].sort_values(['q_BH','Lift'],ascending=[True,False]),use_container_width=True,height=650)
 with tabs[2]:
  n=st.slider('Minimum maske olayı',10,3000,100,10); st.dataframe(paths[paths.Aday>=n].sort_values(['q_BH','Lift'],ascending=[True,False]),use_container_width=True,height=650)
 with tabs[3]: st.dataframe(mt[mt.Aday>=20].sort_values(['pre_mask','Aday'],ascending=[True,False]),use_container_width=True,height=650)
 with tabs[4]: st.dataframe(fingerprint.sort_values('H_farkı',ascending=False),use_container_width=True,height=650)
 with tabs[5]:
  num=st.selectbox('Sayı',range(1,81)); st.subheader(f'{num} — H1→H8'); st.dataframe(nh[nh.Sayı==num].sort_values('H'),use_container_width=True)
  st.subheader('Tam H maskeleri'); st.dataframe(nm[(nm.num==num)&(nm.Aday>=5)].sort_values(['q_BH','Lift'],ascending=[True,False]),use_container_width=True,height=420)
  st.subheader('2–8 basamak dönüş yolları'); st.dataframe(nrhythm[(nrhythm.Sayı==num)&(nrhythm.Aday>=20)].sort_values(['q_BH','Lift'],ascending=[True,False]),use_container_width=True,height=420)
 with tabs[6]:
  st.subheader('1–80 × H-maskesi → ikinci tetikleyici')
  st.caption('Seçilen sayı/maskenin bütün fırsatlarında, hedef sonucu açılmadan ÖNCE diğer 79 sayının H geometrisini hesaplar; sonra REAL ve NEGATIVE olaylarını karşılaştırır.')
  tn=st.selectbox('Sayı',range(1,81),index=73,key='tr_num')
  masks=nm[nm.num==tn].sort_values('Aday',ascending=False).pre_mask.tolist()
  default_idx=masks.index('10000000') if tn==74 and '10000000' in masks else 0
  tm=st.selectbox('Ana H maskesi',masks,index=default_idx,key='tr_mask')
  base=ev[(ev.num==tn)&(ev.pre_mask==tm)].merge(env,on='target_draw_id',how='left')
  # subtract selected number from all-80 pre-state -> exact OTHER 79 pre-draw geometry
  for h in range(1,9): base[f'Diger79_H{h}']=base[f'ALL_H{h}']-base[f'H{h}']
  for k in range(0,9): base[f'Diger79_HC{k}']=base[f'ALL_HC{k}']-(base.H_count==k).astype(int)
  base['Diger79_AyniMaske']=base.apply(lambda r:int(r['MASK_COUNTS'].get(tm,0))-1,axis=1)
  st.metric('Toplam fırsat',len(base)); c1,c2,c3=st.columns(3)
  c1.metric('REAL',int(base.REAL.sum())); c2.metric('NEGATIVE',int(base.NEGATIVE.sum())); c3.metric('Temel başarı',f"{base.REAL.mean():.2%}" if len(base) else '-')
  feats=[f'Diger79_H{h}' for h in range(1,9)]+[f'Diger79_HC{k}' for k in range(0,9)]+['Diger79_AyniMaske']
  comp=[]
  for f in feats:
    a=base[base.REAL==1][f]; b=base[base.REAL==0][f]
    comp.append([f,a.mean() if len(a) else np.nan,b.mean() if len(b) else np.nan,(a.mean()-b.mean()) if len(a) and len(b) else np.nan])
  st.subheader('42/67 gibi REAL–NEGATIVE geometri karşılaştırması')
  st.dataframe(pd.DataFrame(comp,columns=['Pre-draw özellik','REAL_ortalama','NEGATIVE_ortalama','Fark']).sort_values('Fark',key=lambda x:x.abs(),ascending=False),use_container_width=True)
  # threshold discovery within this selected condition; clearly exploratory
  rules=[]
  for f in feats:
    vals=sorted(base[f].dropna().unique())
    for cut in vals:
      for op in ('>=','<='):
        x=base[base[f]>=cut] if op=='>=' else base[base[f]<=cut]
        if len(x)>=max(15,int(len(base)*.15)):
          rules.append([f,op,cut,len(x),int(x.REAL.sum())])
  rr=add_stats(pd.DataFrame(rules,columns=['Özellik','Koşul','Eşik','Aday','REAL'])) if rules else pd.DataFrame()
  if len(rr):
    st.subheader('Keşif amaçlı ikinci tetikleyiciler')
    st.warning('Bu eşikler aynı veri üzerinde keşfedildi. q_BH gösterilir; kesin kural sayılmaz. Sonraki sürümde holdout/walk-forward ile dondurulup doğrulanmalıdır.')
    st.dataframe(rr.sort_values(['q_BH','Lift'],ascending=[True,False]).head(100),use_container_width=True,height=500)
  outcols=['Event_ID','target_draw_id','target_dt','num','pre_mask','REAL','NEGATIVE']+feats
  st.download_button('SEÇİLİ SAYI-MASKE OLAYLARI CSV',base[outcols].to_csv(index=False).encode('utf-8-sig'),f'H_TETIK_{tn}_{tm}.csv','text/csv')
 with tabs[7]:
  st.subheader('PREDİKTİF uyku→bu elde dönüş hazardı'); st.dataframe(hz[hz.Uyku<=30],use_container_width=True)
  num2=st.selectbox('Sayı',range(1,81),key='hz'); st.dataframe(nhz[(nhz.Sayı==num2)&(nhz.Uyku<=30)&(nhz.Aday>=5)],use_container_width=True,height=420)
 with tabs[8]:
  n=st.slider('Minimum yol olayı',50,20000,300,50); st.dataframe(rhythm[rhythm.Aday>=n].sort_values(['q_BH','Lift'],ascending=[True,False]),use_container_width=True,height=650)
 with tabs[9]:
  test=st.selectbox('H testi',daily.Test.unique()); st.dataframe(daily[daily.Test==test],use_container_width=True)
 with tabs[10]:
  st.caption('Her satır gerçek bir target_draw_id × sayı Event_ID kaydıdır. pre_* alanları sonuçtan önce dondurulmuştur.')
  st.dataframe(ev.head(5000),use_container_width=True,height=650)
  st.download_button('EVENT KÜTÜĞÜ CSV',ev.to_csv(index=False).encode('utf-8-sig'),'H1_H8_EVENT_KUTUGU_V3.csv','text/csv')
 with tabs[11]:
  lines=['HIZLI ON 1-80 H TETIKLEYICI MASTER V3',f'CEKILIS={len(df)}|BAS={df.draw_id.iloc[0]}|SON={df.draw_id.iloc[-1]}|GUN={df.date.nunique()}','NO_LEAKAGE=EVET|BASELINE=0.25|EVENT_ID=EVET|CI95=EVET|BH_FDR=EVET','']
  sections=[('H1-H8',single),('H KOMBINASYON',combo),('TAM MASKELER',paths),('MASKE GECIS',mt),('1-80 H PARMAK IZI',fingerprint),('SAYI x H',nh),('SAYI x MASKE',nm),('UYKU HAZARD',hz),('SAYI UYKU HAZARD',nhz),('DONUS YOLLARI',rhythm),('SAYI DONUS YOLLARI',nrhythm),('GUN TUTARLILIK',daily)]
  for title,d in sections: lines += [f'=== {title} ===',d.to_csv(index=False),'']
  master='\n'.join(lines)
  st.download_button('H1-H8 TETIKLEYICI MASTER V3 TXT',master.encode('utf-8'),'H1_H8_TETIKLEYICI_MASTER_V3.txt','text/plain')
  st.download_button('1-80 PARMAK İZİ CSV',fingerprint.to_csv(index=False).encode('utf-8-sig'),'H1_H8_PARMAK_IZI_V2.csv','text/csv')
st.caption('Not: BH-FDR çoklu testlerde yalancı keşif riskini azaltır. Küçük örnekli yüksek liftler otomatik olarak gerçek sinyal kabul edilmemelidir.')
