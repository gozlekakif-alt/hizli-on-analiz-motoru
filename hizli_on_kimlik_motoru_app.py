import streamlit as st
import pandas as pd
import numpy as np
import requests
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title='Hızlı On — 80 Sayı Kimlik Motoru', layout='wide')
st.title('Hızlı On — 80 Sayı Dinamik Kimlik Motoru')
st.caption('25.08.2026’dan itibaren çekiliş çekiliş PRE-H kimlik güncellemesi • tek tuş analiz • tek TXT rapor')

DEFAULT_NAME = 'veri.txt'

def parse_text(txt):
    rows=[]
    for ln,line in enumerate(txt.splitlines(),1):
        line=line.strip()
        if not line: continue
        p=line.split(';')
        if len(p)!=3: continue
        try:
            did=int(p[0]); ts=pd.to_datetime(p[1], dayfirst=True)
            nums=sorted(set(int(x.strip()) for x in p[2].split(',') if x.strip()))
        except Exception:
            continue
        if len(nums)==20 and all(1<=x<=80 for x in nums): rows.append((did,ts,nums))
    if not rows: raise ValueError('Geçerli çekiliş satırı bulunamadı.')
    df=pd.DataFrame(rows,columns=['draw_id','time','numbers']).sort_values(['time','draw_id']).drop_duplicates('draw_id').reset_index(drop=True)
    return df

def load_source(upload, url):
    if upload is not None:
        return upload.getvalue().decode('utf-8-sig',errors='replace'), upload.name, 'yükleme'
    if url.strip():
        r=requests.get(url.strip(),timeout=20); r.raise_for_status()
        return r.text, DEFAULT_NAME, 'GitHub'
    p=Path(DEFAULT_NAME)
    if p.exists(): return p.read_text(encoding='utf-8-sig',errors='replace'), DEFAULT_NAME, 'yerel'
    raise FileNotFoundError('veri.txt bulunamadı. GitHub RAW adresini gir veya veri.txt yükle.')

def mat(df):
    X=np.zeros((len(df),80),dtype=np.int8)
    for i,nums in enumerate(df.numbers): X[i,np.array(nums)-1]=1
    return X

def cnt(X,i,w):
    a=max(0,i-w); return X[a:i].sum(axis=0).astype(int)

def age_vec(X,i):
    out=np.full(80,i+1,dtype=int)
    if i==0:return out
    for n in range(80):
        z=np.flatnonzero(X[:i,n])
        if len(z): out[n]=i-1-z[-1]
    return out

def ranks(longc,h48,h12,ages):
    # all PRE-H; deterministic tie break: long freq, H48, H12, shorter sleep, number
    nums=np.arange(1,81)
    order=np.lexsort((nums,ages,-h12,-h48,-longc))
    r=np.empty(80,dtype=int); r[order]=np.arange(1,81)
    return r

def band(rank):
    return 'HOT' if rank<=20 else ('MID' if rank<=60 else 'COLD')

def direction(h6,h24,prev_h6):
    # short momentum relative to own previous PRE-H H6; fallback short-vs-medium rate
    if prev_h6 is not None:
        d=h6-prev_h6
        return 'UP' if d>0 else ('DOWN' if d<0 else 'FLAT')
    expected=h24/4.0
    return 'UP' if h6>expected+.5 else ('DOWN' if h6<expected-.5 else 'FLAT')

def run_engine(df):
    X=mat(df); states=[]; transitions={}; prev=None
    real20_by_id={int(df.iloc[i].draw_id):set(df.iloc[i].numbers) for i in range(len(df))}
    for i,row in df.iterrows():
        h3=cnt(X,i,3); h6=cnt(X,i,6); h12=cnt(X,i,12); h24=cnt(X,i,24); h48=cnt(X,i,48)
        longc=X[:i].sum(axis=0).astype(int); ages=age_vec(X,i); rr=ranks(longc,h48,h12,ages)
        cur=[]
        for n in range(1,81):
            j=n-1; prevh6=None if prev is None else prev[j]['h6']
            b=band(int(rr[j])); d=direction(int(h6[j]),int(h24[j]),prevh6)
            ident=f'{b}_{d}|H3={h3[j]}|H6={h6[j]}|H12={h12[j]}|H24={h24[j]}|H48={h48[j]}|AGE={ages[j]}|R={rr[j]}'
            hit=int(X[i,j])
            rec={'draw_id':int(row.draw_id),'time':row.time,'number':n,'hit':hit,'band':b,'dir':d,'rank':int(rr[j]),'age':int(ages[j]),'h3':int(h3[j]),'h6':int(h6[j]),'h12':int(h12[j]),'h24':int(h24[j]),'h48':int(h48[j]),'cum':int(longc[j]),'identity':ident}
            states.append(rec); cur.append(rec)
            if prev is not None:
                key=(prev[j]['band']+'_'+prev[j]['dir'], b+'_'+d)
                if key not in transitions: transitions[key]=[0,0]
                transitions[key][0]+=1; transitions[key][1]+=hit
        prev=cur
    S=pd.DataFrame(states)
    return X,S,transitions

def report(df,S,trans):
    lines=[]
    lines += ['HIZLI ON — 80 SAYI DINAMIK KIMLIK RAPORU',f'Uretim: {datetime.now():%d.%m.%Y %H:%M:%S}',f'Cekilis: {len(df)} | Durum: {len(S)} (= cekilis x 80)',f'Aralik: {df.time.min():%d.%m.%Y %H:%M} -> {df.time.max():%d.%m.%Y %H:%M}','']
    lines += ['KURAL','Her hedef cekilis icin yalnizca ONCEKI cekilisler kullanildi (PRE-H).','Kimlik: HOT/MID/COLD + UP/FLAT/DOWN + H3/H6/H12/H24/H48 + AGE + RANK.','Siralama esitlik kirma: kumulatif frekans > H48 > H12 > kisa uyku > sayi.','']
    # overall transition table
    lines.append('=== KIMLIK GECISLERI -> AYNI HEDEF REAL20 ===')
    tbl=[]
    for (a,b),(N,H) in trans.items():
        if N>=20: tbl.append((H/N,N,H,a,b))
    for rate,N,H,a,b in sorted(tbl,reverse=True)[:80]: lines.append(f'{a} -> {b} | N={N} | REAL20={H} | %{100*rate:.2f}')
    # number summaries
    lines += ['','=== 1-80 SAYI OZETI ===']
    for n in range(1,81):
        z=S[S.number==n]; last=z.iloc[-1]
        lines.append(f'{n:02d} | toplam={int(z.hit.sum())}/{len(z)} | son={last.identity}')
    # draw-by-draw identity ledger, compact but complete
    lines += ['','=== CEKILIS CEKILIS 80 KIMLIK DEFTERI ===']
    for did,g in S.groupby('draw_id',sort=False):
        t=g.time.iloc[0]
        real=','.join(map(str,df.loc[df.draw_id==did,'numbers'].iloc[0]))
        lines.append(f'\n#{did} {t:%d.%m.%Y %H:%M} | REAL20={real}')
        for _,r in g.iterrows():
            lines.append(f'{int(r.number):02d};hit={int(r.hit)};{r.identity};CUM={int(r.cum)}')
    return '\n'.join(lines)

with st.sidebar:
    st.subheader('Veri kaynağı')
    github=st.text_input('GitHub RAW veri.txt adresi', placeholder='https://raw.githubusercontent.com/.../veri.txt')
    upload=st.file_uploader('veya veri.txt yükle',type=['txt'])
    st.caption('GitHub kullanıyorsan dosya adı veri.txt olabilir; RAW adresini bir kez girmen yeterli.')

if st.button('TEK TUŞ — 14 GÜNÜ SIRA SIRA ANALİZ ET',type='primary',use_container_width=True):
    try:
        txt,name,src=load_source(upload,github)
        df=parse_text(txt)
        # requested research start
        df=df[df.time>=pd.Timestamp('2026-08-25 00:00')].reset_index(drop=True)
        if df.empty: raise ValueError('25.08.2026 ve sonrası veri yok.')
        with st.spinner('Çekiliş çekiliş 80 kimlik güncelleniyor...'):
            X,S,T=run_engine(df); out=report(df,S,T)
        st.success(f'Tamamlandı: {len(df)} çekiliş × 80 = {len(S):,} kimlik durumu. Kaynak: {src} / {name}')
        c1,c2,c3=st.columns(3)
        c1.metric('Çekiliş',len(df)); c2.metric('Kimlik durumu',f'{len(S):,}'); c3.metric('Gün',df.time.dt.date.nunique())
        last=S[S.draw_id==S.draw_id.iloc[-1]]
        st.dataframe(last[['number','band','dir','rank','h6','h12','h24','h48','age','hit']],use_container_width=True,height=430)
        st.download_button('TEK DOSYA İNDİR — KIMLIK_RAPORU.txt',data=out.encode('utf-8'),file_name='HIZLI_ON_14_GUN_80_KIMLIK_TAM_RAPOR.txt',mime='text/plain',use_container_width=True)
        st.caption('Bu tek TXT dosyasını bana gönderdiğinde kimlik yollarını, yükseliş/düşüş dönüşümlerini ve REAL20 öncesi tekrar eden yolları doğrudan tarayabiliriz.')
    except Exception as e:
        st.error(str(e))
