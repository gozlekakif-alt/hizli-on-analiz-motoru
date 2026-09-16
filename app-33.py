import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path
import io, os, json, zipfile, hashlib, gc, pickle, tempfile

st.set_page_config(page_title='Hızlı On — Aile Araştırma Laboratuvarı V4', layout='wide')
st.title('🧬 Hızlı On — Aile Araştırma Laboratuvarı V4')
st.caption('SADECE ARAŞTIRMA/ANALİZ. Kupon ve sayı tahmini üretmez. Tek tuş → 14 gün → 4 doğrulanmış parça + Master.')

ROOT=Path(__file__).parent
DATA_DEFAULT=ROOT/'veri.txt'
STORE=ROOT/'aile_v4_kutuk'; STORE.mkdir(exist_ok=True)
PARTS=[[0,1,2,3],[4,5,6,7],[8,9,10],[11,12,13]]

# ---------- yardımcılar ----------
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def zip_ok(b):
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z: return z.testzip() is None
    except Exception: return False

def band(n): return (n-1)//10 + 1

def band_counts(nums):
    c=Counter(band(n) for n in nums)
    return '|'.join(f'B{i}:{c.get(i,0)}' for i in range(1,9))

def gap_class(g):
    if g==1:return 'H1_art_arda'
    if g==2:return 'H2_1_atlama'
    if g==3:return 'H3_2_atlama'
    if g<=6:return 'uyku_3_5'
    if g<=12:return 'uyku_6_11'
    return 'uyku_12plus'

def family_type(fam):
    if len(fam)<2:return 'tekil'
    d=[fam[i+1]-fam[i] for i in range(len(fam)-1)]
    if len(set(d))==1:
        if d[0]==1:return 'ardisik'
        if d[0]==2:return '1_atlamali'
        if d[0]==3:return '2_atlamali'
        return f'esit_adim_{d[0]}'
    return 'serbest'

@st.cache_data(show_spinner=False)
def parse_text(raw):
    rows=[]
    for line in raw.decode('utf-8-sig','ignore').splitlines():
        p=line.strip().split(';')
        if len(p)!=3: continue
        try:
            nums=tuple(sorted(map(int,p[2].split(','))))
            if len(nums)!=20 or len(set(nums))!=20 or min(nums)<1 or max(nums)>80: continue
            rows.append((int(p[0]),pd.to_datetime(p[1],dayfirst=True),nums))
        except Exception: pass
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows,columns=['draw','dt','nums']).sort_values('dt').reset_index(drop=True)
    d['date']=d.dt.dt.strftime('%Y-%m-%d'); d['day_el']=d.groupby('date').cumcount()+1
    return d

def load_input():
    if DATA_DEFAULT.exists(): return parse_text(DATA_DEFAULT.read_bytes()), 'repo/veri.txt'
    up=st.file_uploader('veri.txt yükle (draw;datetime;20 sayı)',type=['txt'])
    if up: return parse_text(up.getvalue()), 'yüklenen veri.txt'
    return pd.DataFrame(), None

# ---------- araştırma çekirdeği ----------
def recurring_candidates(sets,k):
    # 4/5 için yalnız yaşamı olan (>=2 kez görülen) aileleri bellek güvenli çıkarır.
    cand=set()
    for i in range(len(sets)):
        for j in range(i+1,len(sets)):
            inter=sets[i]&sets[j]
            if len(inter)>=k: cand.update(combinations(sorted(inter),k))
    return cand

def family_occurrences(daydf,k):
    sets=[set(x) for x in daydf.nums]
    if k in (2,3):
        occ=defaultdict(list)
        for i,S in enumerate(sets,1):
            for f in combinations(sorted(S),k): occ[f].append(i)
        return {f:p for f,p in occ.items() if len(p)>=2}
    cand=recurring_candidates(sets,k)
    out={}
    for f in cand:
        fs=set(f); p=[i for i,S in enumerate(sets,1) if fs.issubset(S)]
        if len(p)>=2: out[f]=p
    return out

def analyze_day(daydf):
    daydf=daydf.copy().reset_index(drop=True)
    day=str(daydf.date.iloc[0]); N=len(daydf); sets=[set(x) for x in daydf.nums]
    life_rows=[]; event_rows=[]; growth_rows=[]; type_rows=[]
    occ_by_k={}
    for k in (2,3,4,5):
        occ=family_occurrences(daydf,k); occ_by_k[k]=occ
        tc=Counter()
        for fam,pos in occ.items():
            typ=family_type(fam); tc[typ]+=1
            gaps=np.diff(pos).tolist(); gcc=Counter(gap_class(int(g)) for g in gaps)
            life_rows.append(dict(date=day,boyut=k,aile='-'.join(map(str,fam)),tip=typ,
                toplam=len(pos),ilk_el=pos[0],son_el=pos[-1],medyan_gap=float(np.median(gaps)) if gaps else None,
                max_gap=max(gaps) if gaps else None,H1=gcc['H1_art_arda'],H2=gcc['H2_1_atlama'],H3=gcc['H3_2_atlama'],
                uyku3_5=gcc['uyku_3_5'],uyku6_11=gcc['uyku_6_11'],uyku12plus=gcc['uyku_12plus'],zincir=','.join(map(str,pos))))
            for oi,el in enumerate(pos):
                cur=sets[el-1]; prev=sets[el-2] if el>1 else set(); nxt=sets[el] if el<N else set(); fs=set(fam)
                prev_fam=len(fs&prev); next_fam=len(fs&nxt)
                prev_other=len((cur-fs)&prev); next_other=len((cur-fs)&nxt)
                event_rows.append(dict(date=day,draw=int(daydf.iloc[el-1].draw),el=el,boyut=k,aile='-'.join(map(str,fam)),tip=typ,
                    gelis_no=oi+1,onceki_aile_uyesi=prev_fam,sonraki_aile_uyesi=next_fam,
                    oncekinden_tasinan_toplam=len(cur&prev),sonraki_ele_tasinan_toplam=len(cur&nxt),
                    aile_disi_oncekinden_tasinan=prev_other,aile_disi_sonraki_tasinan=next_other,
                    onceki_bant=band_counts(prev) if prev else '',olay_bant=band_counts(cur),sonraki_bant=band_counts(nxt) if nxt else '',
                    onceki_20='-'.join(map(str,sorted(prev))) if prev else '',sonraki_20='-'.join(map(str,sorted(nxt))) if nxt else ''))
        for typ,n in tc.items(): type_rows.append(dict(date=day,boyut=k,tip=typ,tekrarlayan_aile=n))

    # Gerçek kronolojik büyüme: aynı çekirdeğin sonraki görülüşünde daha büyük aileye katılması.
    for k in (2,3,4):
        bigger=occ_by_k[k+1]
        child_index=defaultdict(list)
        for child,cpos in bigger.items():
            for parent in combinations(child,k): child_index[parent].append((child,cpos))
        for parent,ppos in occ_by_k[k].items():
            for pel in ppos:
                candidates=[]
                for child,cpos in child_index.get(parent,[]):
                    later=[x for x in cpos if x>pel]
                    if later: candidates.append((min(later),child))
                if candidates:
                    cel,child=min(candidates,key=lambda x:x[0])
                    growth_rows.append(dict(date=day,gecis=f'{k}->{k+1}',cekirdek='-'.join(map(str,parent)),
                        cekirdek_el=pel,cocuk='-'.join(map(str,child)),cocuk_el=cel,bekleme=cel-pel))

    # tekil sayı bağlamı
    single=[]
    for el,S in enumerate(sets,1):
        prev=sets[el-2] if el>1 else set(); nxt=sets[el] if el<N else set()
        for n in sorted(S):
            single.append(dict(date=day,el=el,draw=int(daydf.iloc[el-1].draw),sayi=n,bant=band(n),
                               onceki_var=int(n in prev),sonraki_var=int(n in nxt)))
    return {k:pd.DataFrame(v) for k,v in dict(life=life_rows,events=event_rows,growth=growth_rows,types=type_rows,singles=single).items()}

def csvb(df): return df.to_csv(index=False).encode('utf-8-sig')

def make_day_zip(day,res):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name,dfx in res.items(): z.writestr(f'{day}_{name.upper()}.csv',csvb(dfx))
        z.writestr(f'{day}_README.txt',('AILE V4\nSadece araştırma/analiz.\n4/5 aile yaşam tabloları >=2 görülüşlü ailelerdir.\n'
            'EVENTS: aile oluştuğu anda önceki/sonraki el, bant ve taşıma bağlamı.\nGROWTH: kronolojik sonraki daha büyük aileye geçiş.\n').encode('utf-8'))
    out=b.getvalue()
    if not zip_ok(out): raise RuntimeError(f'{day} günlük ZIP doğrulaması başarısız')
    return out

def aggregate(daily):
    keys=['life','events','growth','types','singles']; agg={}
    for k in keys: agg[k]=pd.concat([daily[d][k] for d in daily],ignore_index=True) if daily else pd.DataFrame()
    # karakter özeti
    ev=agg['events']; gr=agg['growth']; life=agg['life']
    if not ev.empty:
        char=(ev.groupby(['boyut','tip']).agg(olay=('aile','size'),onceki_aile_ort=('onceki_aile_uyesi','mean'),
              sonraki_aile_ort=('sonraki_aile_uyesi','mean'),sonraki_tasima_ort=('sonraki_ele_tasinan_toplam','mean')).reset_index())
    else: char=pd.DataFrame()
    if not gr.empty:
        gg=gr.groupby('gecis').agg(buyume_olayi=('cekirdek','size'),medyan_bekleme=('bekleme','median'),ortalama_bekleme=('bekleme','mean')).reset_index()
    else: gg=pd.DataFrame()
    return agg,char,gg

def make_part_zip(part_no,days,daily):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for day in days: z.writestr(f'{day}_TAM_ARASTIRMA.zip',make_day_zip(day,daily[day]))
        sub={d:daily[d] for d in days}; agg,char,gg=aggregate(sub)
        z.writestr('PARCA_KARAKTER_OZET.csv',csvb(char)); z.writestr('PARCA_BUYUME_OZET.csv',csvb(gg))
        z.writestr('MANIFEST.json',json.dumps({'part':part_no,'days':days},ensure_ascii=False,indent=2))
    out=b.getvalue()
    if not zip_ok(out): raise RuntimeError(f'Parça {part_no} ZIP doğrulaması başarısız')
    return out

# ---------- UI ----------
df,src=load_input()
if df.empty:
    st.info('Başlamak için repo yanında veri.txt bulunsun veya yukarıdan yükle.')
    st.stop()

DAYS=sorted(df.date.unique())
st.write(f'**Kaynak:** {src}  •  **Çekiliş:** {len(df)}  •  **Gün:** {len(DAYS)}')
valid=(len(df)==3038 and len(DAYS)==14 and all(len(g)==217 for _,g in df.groupby('date')))
if not valid:
    st.error('Veri kapısı geçilmedi: beklenen 14 gün × 217 = 3038 çekiliş. Araştırma başlatılmadı.')
    st.stop()
st.success('Veri kapısı geçti: 14 gün × 217 = 3038 çekiliş.')

st.markdown('**Araştırılan yapı:** tekil sayı bağlamı + serbest/ardışık/atlamalı 2–5 aileler + tekrar/ritim/uyku + gerçek kronolojik büyüme + olaydan önceki ve sonraki el + bant/taşıma bağlamı.')

if st.button('▶️ TEK TUŞ — 14 GÜNLÜK AİLE ARAŞTIRMASINI BAŞLAT',type='primary',width='stretch'):
    daily={}; prog=st.progress(0,text='Başlıyor…')
    for i,day in enumerate(DAYS):
        pkl=STORE/f'{day}_v4.pkl'
        if pkl.exists():
            try:
                with open(pkl,'rb') as f: daily[day]=pickle.load(f)
            except Exception: pkl.unlink(missing_ok=True)
        if day not in daily:
            r=analyze_day(df[df.date==day].copy())
            tmp=pkl.with_suffix('.tmp')
            with open(tmp,'wb') as f: pickle.dump(r,f,pickle.HIGHEST_PROTOCOL)
            os.replace(tmp,pkl); daily[day]=r
        prog.progress((i+1)/14,text=f'{i+1}/14 — {day} tamamlandı')
        gc.collect()

    # 4 güvenli parça
    part_files=[]
    for pi,idxs in enumerate(PARTS,1):
        days=[DAYS[i] for i in idxs]
        pb=make_part_zip(pi,days,daily)
        path=STORE/f'AILE_V4_PARCA_{pi}.zip'; path.write_bytes(pb); part_files.append(path)

    agg,char,gg=aggregate(daily)
    master=io.BytesIO()
    with zipfile.ZipFile(master,'w',zipfile.ZIP_DEFLATED) as z:
        for p in part_files: z.writestr(p.name,p.read_bytes())
        z.writestr('14_GUN_KARAKTER_OZET.csv',csvb(char)); z.writestr('14_GUN_BUYUME_OZET.csv',csvb(gg))
        z.writestr('14_GUN_TIP_OZET.csv',csvb(agg['types']))
        manifest={'version':'V4','draws':len(df),'days':DAYS,'parts':[p.name for p in part_files],
                  'scope':'research_only','sha256_parts':{p.name:sha256_bytes(p.read_bytes()) for p in part_files}}
        z.writestr('MASTER_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    mb=master.getvalue()
    if not zip_ok(mb): raise RuntimeError('MASTER ZIP doğrulaması başarısız')
    mpath=STORE/'HIZLI_ON_14_GUN_AILE_ARASTIRMA_V4_MASTER.zip'; mpath.write_bytes(mb)
    st.session_state['v4_ready']=True
    st.success('14/14 tamamlandı. 4 parça ve Master bütünlük kontrolünden geçti.')

# kalıcı indirme alanı
st.divider(); st.subheader('📦 Doğrulanmış Çıktılar')
for pi in range(1,5):
    p=STORE/f'AILE_V4_PARCA_{pi}.zip'
    if p.exists() and zip_ok(p.read_bytes()): st.download_button(f'⬇️ PARÇA {pi}',p.read_bytes(),p.name,'application/zip',key=f'dl{pi}',width='stretch')
mp=STORE/'HIZLI_ON_14_GUN_AILE_ARASTIRMA_V4_MASTER.zip'
if mp.exists() and zip_ok(mp.read_bytes()): st.download_button('⬇️ 14 GÜNLÜK MASTER',mp.read_bytes(),mp.name,'application/zip',key='dlm',width='stretch')

st.caption('Güvenlik: günlük checkpoint + atomik yazma + her ZIP için CRC testi + 4 parça + SHA-256 manifest. Yarım kalırsa tamamlanan günleri yeniden hesaplamaz.')
