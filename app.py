import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path
import json, zipfile, io

st.set_page_config(page_title='Hızlı On Otomatik Aile Kadavra V3', layout='wide')
st.title('🧬 Hızlı On — Otomatik Aile Kadavra Laboratuvarı V3')
st.caption('Tek tuş = tek gün. 14 gün sırayla tamamlanır; biten gün yeniden hesaplanmaz. Kupon üretmez.')

@st.cache_data(show_spinner=False)
def load_data(path):
    rows=[]
    with open(path,encoding='utf-8') as f:
        for line in f:
            p=line.strip().split(';')
            if len(p)!=3: continue
            nums=tuple(sorted(map(int,p[2].split(','))))
            if len(nums)==20: rows.append((int(p[0]),pd.to_datetime(p[1],dayfirst=True),nums))
    df=pd.DataFrame(rows,columns=['draw','dt','nums']).sort_values('dt').reset_index(drop=True)
    df['date']=df['dt'].dt.strftime('%Y-%m-%d'); df['hour']=df['dt'].dt.hour
    df['day_el']=df.groupby('date').cumcount()+1
    return df

DATA=Path(__file__).with_name('veri.txt')
df=load_data(str(DATA))
DAYS=sorted(df.date.unique())
if len(df)!=3038 or len(DAYS)!=14: st.error(f'Veri kontrolü başarısız: {len(df)} çekiliş / {len(DAYS)} gün'); st.stop()

# Session persistence: survives reruns while app instance/session is alive.
if 'done_days' not in st.session_state: st.session_state.done_days={}

def gap_class(g):
    if g==1:return 'art_arda'
    if g==2:return '1_atlama'
    if g==3:return '2_atlama'
    if g<=6:return '3_5_uyku'
    if g<=12:return '6_11_uyku'
    return '12plus_uyku'

def family_summary(daydf,k):
    occ=defaultdict(list)
    for r in daydf.itertuples():
        for fam in combinations(r.nums,k): occ[fam].append(int(r.day_el))
    rows=[]
    for fam,pos in occ.items():
        gaps=[pos[i]-pos[i-1] for i in range(1,len(pos))]
        gc=Counter(gap_class(g) for g in gaps)
        # max count in rolling 12 draws
        best=1; j=0
        for i,p in enumerate(pos):
            while p-pos[j]>=12: j+=1
            best=max(best,i-j+1)
        rows.append({'aile':'-'.join(map(str,fam)),'boyut':k,'toplam':len(pos),'ilk_el':pos[0],
                     'ikinci_el':pos[1] if len(pos)>1 else None,'ilk_ikinci_gap':gaps[0] if gaps else None,
                     'medyan_gap':float(np.median(gaps)) if gaps else None,'max12_burst':best,
                     'art_arda':gc['art_arda'],'atlama1':gc['1_atlama'],'atlama2':gc['2_atlama'],
                     'uyku3_5':gc['3_5_uyku'],'uyku6_11':gc['6_11_uyku'],'uyku12plus':gc['12plus_uyku'],
                     'zincir':','.join(map(str,pos))})
    return pd.DataFrame(rows).sort_values(['toplam','max12_burst'],ascending=False)

def geometry_summary(daydf,step,k):
    rows=[]
    maxstart=80-step*(k-1)
    for a in range(1,maxstart+1):
        fam=tuple(a+step*i for i in range(k)); fs=set(fam)
        pos=[int(r.day_el) for r in daydf.itertuples() if fs.issubset(r.nums)]
        if not pos: continue
        gaps=[pos[i]-pos[i-1] for i in range(1,len(pos))]
        rows.append({'aile':'-'.join(map(str,fam)),'tip':f'+{step}','boyut':k,'toplam':len(pos),
                     'ilk_el':pos[0],'ikinci_el':pos[1] if len(pos)>1 else None,
                     'ilk_ikinci_gap':gaps[0] if gaps else None,'zincir':','.join(map(str,pos))})
    return pd.DataFrame(rows).sort_values('toplam',ascending=False) if rows else pd.DataFrame()

def hourly_summary(daydf):
    out=[]
    for hour,g in daydf.groupby('hour'):
        # lightweight complete hourly family leaders 2/3/4; 5 via intersections omitted from exhaustive storage
        rec={'hour':int(hour),'cekilis':len(g)}
        for k in (2,3,4):
            c=Counter()
            for nums in g.nums: c.update(combinations(nums,k))
            fam,n=c.most_common(1)[0]
            rec[f'top{k}']='-'.join(map(str,fam)); rec[f'top{k}_n']=n
        rec['tasima_ort']=round(float(np.mean([len(set(g.iloc[i-1].nums)&set(g.iloc[i].nums)) for i in range(1,len(g))])),3) if len(g)>1 else None
        out.append(rec)
    return pd.DataFrame(out)

def growth_summary(f2,f3,f4,f5):
    # descriptive parent-child counts from families observed >=2, bounded output
    maps={2:f2,3:f3,4:f4,5:f5}; out=[]
    for k in (2,3,4):
        small=maps[k]; big=maps[k+1]
        if small.empty or big.empty: continue
        sc={tuple(map(int,a.split('-'))):int(n) for a,n in zip(small.aile,small.toplam)}
        for r in big.head(5000).itertuples():
            b=tuple(map(int,r.aile.split('-')))
            for parent in combinations(b,k):
                if parent in sc:
                    out.append({'gecis':f'{k}->{k+1}','cekirdek':'-'.join(map(str,parent)),
                                'cocuk':r.aile,'cekirdek_toplam':sc[parent],'cocuk_toplam':int(r.toplam)})
    return pd.DataFrame(out).sort_values(['cocuk_toplam','cekirdek_toplam'],ascending=False) if out else pd.DataFrame()

def analyze_day(day):
    d=df[df.date==day].copy().reset_index(drop=True); d['day_el']=np.arange(1,len(d)+1)
    result={'date':day,'draws':len(d),'first_draw':int(d.draw.iloc[0]),'last_draw':int(d.draw.iloc[-1])}
    fam={}
    # exhaustive 2/3/4; 5 only recurring candidates derived by intersections to keep RAM bounded
    for k in (2,3,4): fam[k]=family_summary(d,k)
    # recurring 5s: enumerate 5-combos only from each draw, Counter one day (~3.36m updates), discard singletons after count
    c5=Counter()
    for nums in d.nums: c5.update(combinations(nums,5))
    recurring={f:n for f,n in c5.items() if n>=2}; del c5
    rows=[]
    for f,n in recurring.items():
        fs=set(f); pos=[i+1 for i,nums in enumerate(d.nums) if fs.issubset(nums)]
        gaps=[pos[i]-pos[i-1] for i in range(1,len(pos))]
        rows.append({'aile':'-'.join(map(str,f)),'boyut':5,'toplam':n,'ilk_el':pos[0],'ikinci_el':pos[1],
                     'ilk_ikinci_gap':gaps[0],'medyan_gap':float(np.median(gaps)),'max12_burst':max(sum(1 for q in pos if p<=q<p+12) for p in pos),
                     'art_arda':sum(g==1 for g in gaps),'atlama1':sum(g==2 for g in gaps),'atlama2':sum(g==3 for g in gaps),
                     'uyku3_5':sum(4<=g<=6 for g in gaps),'uyku6_11':sum(7<=g<=12 for g in gaps),'uyku12plus':sum(g>=13 for g in gaps),'zincir':','.join(map(str,pos))})
    fam[5]=pd.DataFrame(rows).sort_values(['toplam','max12_burst'],ascending=False) if rows else pd.DataFrame(columns=fam[4].columns)
    result['families']=fam
    result['hours']=hourly_summary(d)
    result['consecutive']={k:geometry_summary(d,1,k) for k in (2,3,4,5)}
    result['step2']={k:geometry_summary(d,2,k) for k in (2,3,4,5)}
    result['step3']={k:geometry_summary(d,3,k) for k in (2,3,4,5)}
    result['growth']=growth_summary(fam[2],fam[3],fam[4],fam[5])
    # number life + carry
    numrows=[]
    for n in range(1,81):
        pos=[i+1 for i,nums in enumerate(d.nums) if n in nums]
        gaps=np.diff(pos) if len(pos)>1 else []
        numrows.append({'sayi':n,'toplam':len(pos),'ilk_el':pos[0] if pos else None,'son_el':pos[-1] if pos else None,'medyan_gap':float(np.median(gaps)) if len(gaps) else None})
    result['numbers']=pd.DataFrame(numrows)
    return result

def result_zip(res):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        day=res['date']
        z.writestr(f'{day}_SAAT.csv',res['hours'].to_csv(index=False))
        z.writestr(f'{day}_SAYI_1_80.csv',res['numbers'].to_csv(index=False))
        for k,x in res['families'].items(): z.writestr(f'{day}_SERBEST_{k}LU.csv',x.to_csv(index=False))
        for name in ('consecutive','step2','step3'):
            for k,x in res[name].items(): z.writestr(f'{day}_{name.upper()}_{k}LU.csv',x.to_csv(index=False))
        z.writestr(f'{day}_BUYUME.csv',res['growth'].to_csv(index=False))
        summary=f"GUN={day}\nCEKILIS={res['draws']}\nBAS={res['first_draw']}\nSON={res['last_draw']}\n"
        for k,x in res['families'].items(): summary+=f"SERBEST_{k}LU_AILE={len(x)}\n"
        z.writestr(f'{day}_OZET.txt',summary)
    return bio.getvalue()

# progress
st.subheader('📅 14 Günlük İşlem Sırası')
done=st.session_state.done_days
cols=st.columns(7)
for i,day in enumerate(DAYS): cols[i%7].write(('✅ ' if day in done else '⬜ ')+f'{i+1}. gün\n{day}')
st.progress(len(done)/14, text=f'{len(done)}/14 gün tamamlandı')
next_day=next((d for d in DAYS if d not in done),None)

if next_day:
    st.info(f'Sıradaki: **{DAYS.index(next_day)+1}. gün — {next_day}**. Bu basışta yalnız bu gün hesaplanır.')
    if st.button(f'▶️ {DAYS.index(next_day)+1}. GÜNÜ TAM ANALİZ ET',type='primary',use_container_width=True):
        with st.spinner(f'{next_day}: serbest 2/3/4/5 + saat + ardışık + atlamalı + büyüme hesaplanıyor...'):
            res=analyze_day(next_day); done[next_day]=res; st.session_state.done_days=done
        st.success(f'{next_day} tamamlandı ✅ — {res["draws"]} çekiliş')
        st.rerun()
else:
    st.success('14/14 TAMAMLANDI ✅')

st.divider()
st.subheader('📊 Tamamlanan Gün Sonuçları')
if done:
    sel=st.selectbox('Gün',list(done.keys())[::-1]); r=done[sel]
    a,b,c,d=st.columns(4); a.metric('Çekiliş',r['draws']); b.metric('2li aile',len(r['families'][2])); c.metric('3lü aile',len(r['families'][3])); d.metric('Tekrarlayan 5li',len(r['families'][5]))
    tabs=st.tabs(['Saatlik','Serbest aile','Ardışık','Atlamalı','Büyüme','1–80'])
    with tabs[0]: st.dataframe(r['hours'],use_container_width=True,hide_index=True)
    with tabs[1]:
        k=st.radio('Boyut',[2,3,4,5],horizontal=True,key='srk'); st.dataframe(r['families'][k].head(500),use_container_width=True,hide_index=True)
    with tabs[2]:
        k=st.radio('Boyut',[2,3,4,5],horizontal=True,key='ck'); st.dataframe(r['consecutive'][k],use_container_width=True,hide_index=True)
    with tabs[3]:
        step=st.radio('Adım',[2,3],horizontal=True); k=st.radio('Boyut',[2,3,4,5],horizontal=True,key='sk'); st.dataframe(r['step2' if step==2 else 'step3'][k],use_container_width=True,hide_index=True)
    with tabs[4]: st.dataframe(r['growth'].head(1000),use_container_width=True,hide_index=True)
    with tabs[5]: st.dataframe(r['numbers'],use_container_width=True,hide_index=True)
    st.download_button(f'⬇️ {sel} TAM GÜN KÜTÜĞÜ ZIP',result_zip(r),f'{sel}_AILE_KADAVRA.zip','application/zip',use_container_width=True)

st.divider()
st.subheader('🧬 14/14 Master')
if len(done)==14:
    if st.button('14/14 HAZIR SONUÇLARI BİRLEŞTİR (yeniden hesaplama yok)',use_container_width=True):
        bio=io.BytesIO()
        with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
            for day,r in done.items(): z.writestr(f'{day}_GUN.zip',result_zip(r))
            z.writestr('MASTER_OZET.txt','HIZLI ON AILE KADAVRA V3\nCEKILIS=3038\nGUN=14\nMIMARI=1_TUS_1_GUN\n')
        st.session_state.master_zip=bio.getvalue()
    if 'master_zip' in st.session_state: st.download_button('⬇️ 14 GÜNLÜK MASTER ZIP',st.session_state.master_zip,'HIZLI_ON_14_GUN_AILE_KADAVRA_MASTER_V3.zip','application/zip',use_container_width=True)
else: st.caption('Master yalnız 14 gün tamamlandıktan sonra açılır; hazır günleri yeniden hesaplamaz.')

st.caption('Not: Streamlit oturumu/uygulama yeniden başlatılırsa session_state sıfırlanabilir. Her tamamlanan günü ZIP olarak indirerek kalıcı yedek tutun.')
