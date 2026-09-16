import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path
import json, zipfile, io, pickle, gc, os

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

# Disk-backed persistence: completed days are NOT kept in session_state/RAM.
STORE=Path(__file__).with_name('gun_kutukleri'); STORE.mkdir(exist_ok=True)

def day_pkl(day): return STORE/f'{day}.pkl'
def done_days_disk(): return [d for d in DAYS if day_pkl(d).exists()]
def save_day(res):
    tmp=day_pkl(res['date']).with_suffix('.tmp')
    with open(tmp,'wb') as f: pickle.dump(res,f,pickle.HIGHEST_PROTOCOL)
    os.replace(tmp,day_pkl(res['date']))
def load_day_result(day):
    with open(day_pkl(day),'rb') as f: return pickle.load(f)


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

def recurring_family_summary(daydf,k):
    # Memory-safe: recurring k-families are generated from pairwise draw intersections.
    # A family seen only once has no 2nd-arrival/lifecycle, so it is counted only as singleton aggregate.
    sets=[set(x) for x in daydf.nums]
    cand=set()
    for i in range(len(sets)):
        for j in range(i+1,len(sets)):
            inter=sets[i] & sets[j]
            if len(inter)>=k:
                cand.update(combinations(sorted(inter),k))
    rows=[]
    for fam in cand:
        fs=set(fam); pos=[i+1 for i,S in enumerate(sets) if fs.issubset(S)]
        if len(pos)<2: continue
        gaps=[pos[i]-pos[i-1] for i in range(1,len(pos))]; gc=Counter(gap_class(g) for g in gaps)
        best=1; jj=0
        for ii,pp in enumerate(pos):
            while pp-pos[jj]>=12: jj+=1
            best=max(best,ii-jj+1)
        rows.append({'aile':'-'.join(map(str,fam)),'boyut':k,'toplam':len(pos),'ilk_el':pos[0],
          'ikinci_el':pos[1],'ilk_ikinci_gap':gaps[0],'medyan_gap':float(np.median(gaps)),
          'max12_burst':best,'art_arda':gc['art_arda'],'atlama1':gc['1_atlama'],'atlama2':gc['2_atlama'],
          'uyku3_5':gc['3_5_uyku'],'uyku6_11':gc['6_11_uyku'],'uyku12plus':gc['12plus_uyku'],
          'zincir':','.join(map(str,pos))})
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(['toplam','max12_burst'],ascending=False).reset_index(drop=True)

def analyze_day(day):
    d=df[df.date==day].copy().reset_index(drop=True); d['day_el']=np.arange(1,len(d)+1)
    result={'date':day,'draws':len(d),'first_draw':int(d.draw.iloc[0]),'last_draw':int(d.draw.iloc[-1])}
    fam={}
    # 2/3 are exhaustive. 4/5 lifecycle tables keep recurring families only, generated memory-safely.
    for k in (2,3): fam[k]=family_summary(d,k)
    fam[4]=recurring_family_summary(d,4)
    fam[5]=recurring_family_summary(d,5)
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

# progress — disk-backed, RAM-light\nst.subheader('📅 14 Günlük İşlem Sırası')\ndone=done_days_disk()\ncols=st.columns(7)\nfor i,day in enumerate(DAYS): cols[i%7].write(('✅ ' if day in done else '⬜ ')+f'{i+1}. gün\\n{day}')\nst.progress(len(done)/14, text=f'{len(done)}/14 gün tamamlandı')\nnext_day=next((d for d in DAYS if d not in done),None)\n\nif next_day:\n    st.info(f'Sıradaki: **{DAYS.index(next_day)+1}. gün — {next_day}**. Önceki günler RAM’e yüklenmez.')\n    if st.button(f'▶️ {DAYS.index(next_day)+1}. GÜNÜ TAM ANALİZ ET',type='primary',width='stretch'):\n        with st.spinner(f'{next_day}: günlük kadavra hesaplanıyor ve diske yazılıyor...'):\n            res=analyze_day(next_day)\n            save_day(res)\n            del res; gc.collect()\n        st.success(f'{next_day} tamamlandı ve diske kaydedildi ✅')\n        st.rerun()\nelse:\n    st.success('14/14 TAMAMLANDI ✅')\n\nst.divider(); st.subheader('📊 Tamamlanan Gün Sonuçları')\nif done:\n    sel=st.selectbox('Gün',done[::-1])\n    # Only the selected day is loaded into RAM.\n    r=load_day_result(sel)\n    a,b,c,d=st.columns(4); a.metric('Çekiliş',r['draws']); b.metric('2li aile',len(r['families'][2])); c.metric('3lü aile',len(r['families'][3])); d.metric('Tekrarlayan 5li',len(r['families'][5]))\n    tabs=st.tabs(['Saatlik','Serbest aile','Ardışık','Atlamalı','Büyüme','1–80'])\n    with tabs[0]: st.dataframe(r['hours'],width='stretch',hide_index=True)\n    with tabs[1]:\n        k=st.radio('Boyut',[2,3,4,5],horizontal=True,key='srk'); st.dataframe(r['families'][k].head(500),width='stretch',hide_index=True)\n        if k in (4,5): st.caption('4/5 yaşam tablosu: ikinci gelişi olan (tekrarlayan) aileler. Tek-seferlik aileler RAM koruması için tutulmaz.')\n    with tabs[2]:\n        k=st.radio('Boyut',[2,3,4,5],horizontal=True,key='ck'); st.dataframe(r['consecutive'][k],width='stretch',hide_index=True)\n    with tabs[3]:\n        step=st.radio('Adım',[2,3],horizontal=True); k=st.radio('Boyut',[2,3,4,5],horizontal=True,key='sk'); st.dataframe(r['step2' if step==2 else 'step3'][k],width='stretch',hide_index=True)\n    with tabs[4]: st.dataframe(r['growth'].head(1000),width='stretch',hide_index=True)\n    with tabs[5]: st.dataframe(r['numbers'],width='stretch',hide_index=True)\n    st.download_button(f'⬇️ {sel} TAM GÜN KÜTÜĞÜ ZIP',result_zip(r),f'{sel}_AILE_KADAVRA.zip','application/zip',width='stretch')\n    del r; gc.collect()\n\nst.divider(); st.subheader('🧬 14/14 Master')\nif len(done)==14:\n    if st.button('14/14 HAZIR GÜNLERDEN MASTER OLUŞTUR',width='stretch'):\n        out=STORE/'HIZLI_ON_14_GUN_AILE_KADAVRA_MASTER_V3_1.zip'\n        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:\n            for day in DAYS:\n                rr=load_day_result(day); z.writestr(f'{day}_GUN.zip',result_zip(rr)); del rr; gc.collect()\n            z.writestr('MASTER_OZET.txt','HIZLI ON AILE KADAVRA V3.1\\nCEKILIS=3038\\nGUN=14\\nMIMARI=DISK_BACKED_1_TUS_1_GUN\\n')\n        st.session_state['master_ready']=str(out)\n    mp=STORE/'HIZLI_ON_14_GUN_AILE_KADAVRA_MASTER_V3_1.zip'\n    if mp.exists():\n        st.download_button('⬇️ 14 GÜNLÜK MASTER ZIP',mp.read_bytes(),mp.name,'application/zip',width='stretch')\nelse: st.caption('Master 14 gün tamamlanınca açılır. Hazır günler yeniden hesaplanmaz.')\n\nst.caption('V3.1 bellek koruması: tamamlanan gün diske yazılır; session_state içinde ağır DataFrame tutulmaz. Uygulama yeniden başlatılırsa aynı çalışan instance içindeki gun_kutukleri klasörü taranır.')\n