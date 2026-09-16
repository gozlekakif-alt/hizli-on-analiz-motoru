import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations
from math import sqrt,erfc
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

import json
from datetime import datetime

@st.cache_data(show_spinner=False)
def calculate_one(num):
    d=load();a=compact(d);days=d.date.drop_duplicates().tolist()
    ev=target_events(d,a,num)
    # Five stages: H/G1, events, family discovery, frozen 10+4, rolling.
    h=[]
    for lag in range(8):
        opportunities=int(a[8-lag-1:len(d)-lag-1,num-1].sum())
        hits=int(np.logical_and(a[8-lag-1:len(d)-lag-1,num-1],a[8:,num-1]).sum())
        h.append({'H':lag+1,'N':opportunities,'REAL':hits,'RATE':hits/opportunities if opportunities else None})
    train=ev[ev.date.isin(days[:10])];test=ev[ev.date.isin(days[10:])]
    discovered=family_discovery(train,num)
    frozen=[]
    if not discovered.empty:
        for _,r in discovered.head(20).iterrows():
            x=apply(train,r.AILE);y=apply(test,r.AILE)
            frozen.append({'family':r.AILE,'train_n':len(x),'train_real':int(x.REAL.sum()),'test_n':len(y),'test_real':int(y.REAL.sum()),'test_rate':float(y.REAL.mean()) if len(y) else None})
    rolling=[]
    for i in range(6,len(days)):
        tr=ev[ev.date.isin(days[:i])];te=ev[ev.date.eq(days[i])]
        fc=family_discovery(tr,num,min_n=8,pool_size=8,max_size=4)
        if fc.empty:
            rolling.append({'date':days[i],'family':None,'n':0,'real':0,'base_n':len(te),'base_real':int(te.REAL.sum())})
            continue
        family=str(fc.iloc[0].AILE);z=apply(te,family)
        rolling.append({'date':days[i],'family':family,'n':len(z),'real':int(z.REAL.sum()),'base_n':len(te),'base_real':int(te.REAL.sum())})
    # Store compact event log including HC and pre-draw ages for later reconstruction.
    event_cols=['Event_ID','draw_id','date','num','mask','return_gap','REAL','NEGATIVE']+[f'HC{k}' for k in range(9)]+[f'A{k}' for k in range(1,81) if k!=num]
    return {'num':num,'h':h,'g1':{'n':len(ev),'real':int(ev.REAL.sum()),'negative':int(ev.NEGATIVE.sum())},
            'events':ev[event_cols].replace({np.nan:None}).to_dict('records'),
            'family_discovery':discovered.head(30).replace({np.nan:None}).to_dict('records') if not discovered.empty else [],
            'frozen':frozen,'rolling':rolling}

def make_master(results):
    lines=['HIZLI ON TEK TUS 1-80 MASTER V4','YONTEM: Her sayi icin 5 asama; 10 gun kesif/4 gun frozen; gun6+ rolling; 14 gun tek zincir.',
           'UYARI: Kesif aileleri ayni veride secilir; ileri test disinda basari kaniti degildir.']
    for n in sorted(results,key=int):
        r=results[n];lines.append('\n'+'='*65+'\nSAYI '+str(n)+' | G1 '+str(r['g1']['real'])+'/'+str(r['g1']['n']))
        for title,key in [('H1-H8','h'),('AILE KESIF','family_discovery'),('10+4 DONDURULMUS','frozen'),('ROLLING','rolling')]:
            lines.append('--- '+title+' ---')
            for item in r[key]:lines.append(json.dumps(item,ensure_ascii=False,allow_nan=False))
        lines.append('--- EVENT_ID / PRE-DRAW / REAL-NEGATIVE ---')
        for item in r['events']:lines.append(json.dumps(item,ensure_ascii=False,allow_nan=False))
    return '\n'.join(lines)+'\n'

st.set_page_config(page_title='Hızlı On Tek Tuş Kadavra V4',layout='wide')
st.title('Hızlı On — 1’den 80’e Tek Tuş Kadavra V4')
st.caption('Bir sayıya bir kez bas: 5 aşama tamamlanır, kaydedilir ve sıradaki sayıya geçilir. Sonunda tek MASTER TXT.')
d=load();st.success(f'{len(d)} çekiliş • {d.date.nunique()} gün • tek zincir')
# A small local checkpoint survives Streamlit reruns, but Cloud may erase it on redeploy/reboot.
checkpoint=Path(__file__).with_name('kadavra_ilerleme.json')
if 'all_results' not in st.session_state:
    try:st.session_state.all_results=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {}
    except Exception:st.session_state.all_results={}
results=st.session_state.all_results
uploaded=st.file_uploader('Önceki ilerlemeyi geri yükle (isteğe bağlı JSON)',type=['json'])
if uploaded is not None:
    raw=uploaded.getvalue()
    digest=__import__('hashlib').sha256(raw).hexdigest()
    if st.session_state.get('restored_digest')!=digest:
        try:
            incoming=json.loads(raw.decode('utf-8'))
            if not isinstance(incoming,dict) or any(not str(k).isdigit() or not 1<=int(k)<=80 for k in incoming):raise ValueError('Geçersiz kayıt')
            results.update(incoming);checkpoint.write_text(json.dumps(results,ensure_ascii=False,allow_nan=False),encoding='utf-8')
            st.session_state.restored_digest=digest;st.rerun()
        except Exception as exc:st.error(f'İlerleme yüklenemedi: {exc}')
completed={int(k) for k in results}
next_num=next((n for n in range(1,81) if n not in completed),None)
st.progress(len(completed)/80,text=f'{len(completed)}/80 sayı tamamlandı')
if next_num is not None:
    st.subheader(f'Sıradaki sayı: {next_num}')
    if st.button(f'{next_num} için 5 analizi hesapla ve kaydet',type='primary',use_container_width=True):
        with st.spinner(f'{next_num}: H → olay → aile → 10+4 → rolling'):
            try:
                result=calculate_one(next_num)
                results[str(next_num)]=result
                checkpoint.write_text(json.dumps(results,ensure_ascii=False,allow_nan=False),encoding='utf-8')
                st.success(f'{next_num} tamamlandı. G→1: {result["g1"]["real"]}/{result["g1"]["n"]}. Sıradaki sayıya basabilirsin.')
                st.rerun()
            except Exception as exc:st.exception(exc)
else:st.success('80/80 tamamlandı. Tek MASTER dosyasını indir.')
if completed:
    last=max(completed);r=results[str(last)]
    st.write(f'Son kaydedilen sayı: **{last}** | G→1: **{r["g1"]["real"]}/{r["g1"]["n"]}** | aile adayı: {len(r["family_discovery"])} | frozen satırı: {len(r["frozen"])} | rolling günü: {len(r["rolling"])}')
    st.download_button('TEK MASTER TXT indir (şu ana kadarki tüm sayılar)',make_master(results).encode('utf-8'),'HIZLI_ON_1_80_TEK_MASTER_V4.txt','text/plain',use_container_width=True)
    st.download_button('İlerleme yedeği JSON indir',json.dumps(results,ensure_ascii=False,allow_nan=False).encode('utf-8'),'KADAVRA_ILerleme_YEDEK.json','application/json',use_container_width=True)
    st.caption('Cloud yeniden dağıtılırsa yerel kayıt silinebilir. Her birkaç sayıda bir ilerleme JSON yedeğini indir; üstte geri yükleyebilirsin.')
