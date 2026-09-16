import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path
import io, os, json, zipfile, hashlib, gc, pickle

st.set_page_config(page_title='Hızlı On — Aile Araştırma V4.2', layout='wide')
st.title('🧬 Hızlı On — Aile Araştırma Laboratuvarı V4.2')
st.caption('SADECE ARAŞTIRMA/ANALİZ. Tek tuş. Her gün 4 güvenli aşama: 2’li → 3’lü → 4’lü → 5’li. Her aşama diske yazılır.')

ROOT=Path(__file__).parent
DATA_DEFAULT=ROOT/'veri.txt'
STORE=ROOT/'aile_v42_kutuk'; STORE.mkdir(exist_ok=True)
RUN_FLAG=STORE/'RUNNING.flag'
PARTS=[[0,1,2,3],[4,5,6,7],[8,9,10],[11,12,13]]

# ---------- güvenlik ----------
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def zip_ok(b):
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z: return z.testzip() is None
    except Exception: return False

def atomic_pickle(path,obj):
    tmp=path.with_suffix(path.suffix+'.tmp')
    with open(tmp,'wb') as f: pickle.dump(obj,f,pickle.HIGHEST_PROTOCOL)
    os.replace(tmp,path)

def read_pickle(path):
    with open(path,'rb') as f: return pickle.load(f)

def band(n): return (n-1)//10+1
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
    ds=[fam[i+1]-fam[i] for i in range(len(fam)-1)]
    if len(set(ds))==1:
        if ds[0]==1:return 'ardisik'
        if ds[0]==2:return '1_atlamali'
        if ds[0]==3:return '2_atlamali'
        return f'esit_adim_{ds[0]}'
    return 'serbest'

# ---------- veri ----------
def parse_text(raw):
    text=raw.decode('utf-8-sig') if isinstance(raw,(bytes,bytearray)) else str(raw)
    rows=[]
    for line in text.splitlines():
        p=line.strip().split(';')
        if len(p)!=3: continue
        try:
            nums=tuple(sorted(map(int,p[2].split(','))))
            if len(nums)==20 and len(set(nums))==20 and min(nums)>=1 and max(nums)<=80:
                rows.append((int(p[0]),pd.to_datetime(p[1],dayfirst=True),nums))
        except Exception: pass
    d=pd.DataFrame(rows,columns=['draw','dt','nums']).sort_values('dt').reset_index(drop=True)
    if not d.empty: d['date']=d.dt.dt.strftime('%Y-%m-%d')
    return d

def load_input():
    if DATA_DEFAULT.exists(): return parse_text(DATA_DEFAULT.read_bytes()),'repo/veri.txt'
    up=st.file_uploader('veri.txt yükle',type=['txt'])
    if up: return parse_text(up.getvalue()),'yüklenen veri.txt'
    return pd.DataFrame(),None

# ---------- tek boyut araştırması ----------
def recurring_candidates(sets,k):
    cand=set()
    for i in range(len(sets)):
        Si=sets[i]
        for j in range(i+1,len(sets)):
            inter=Si & sets[j]
            if len(inter)>=k: cand.update(combinations(sorted(inter),k))
    return cand

def family_occurrences(daydf,k):
    sets=[set(x) for x in daydf.nums]
    if k in (2,3):
        occ=defaultdict(list)
        for i,S in enumerate(sets,1):
            for f in combinations(sorted(S),k): occ[f].append(i)
        return {f:p for f,p in occ.items() if len(p)>=2}
    # 4/5: yalnız >=2 kez görülen aileleri çift-kesişiminden üret.
    cand=recurring_candidates(sets,k)
    postings={n:set() for n in range(1,81)}
    for i,S in enumerate(sets,1):
        for n in S: postings[n].add(i)
    out={}
    for f in cand:
        ps=postings[f[0]].copy()
        for n in f[1:]:
            ps.intersection_update(postings[n])
            if len(ps)<2: break
        if len(ps)>=2: out[f]=sorted(ps)
    return out

def research_k(daydf,k):
    daydf=daydf.copy().reset_index(drop=True); day=str(daydf.date.iloc[0]); N=len(daydf)
    sets=[set(x) for x in daydf.nums]
    occ=family_occurrences(daydf,k)
    life=[]; events=[]; tc=Counter()
    for fam,pos in occ.items():
        typ=family_type(fam); tc[typ]+=1; gaps=np.diff(pos).tolist(); gcc=Counter(gap_class(int(g)) for g in gaps)
        life.append(dict(date=day,boyut=k,aile='-'.join(map(str,fam)),tip=typ,toplam=len(pos),ilk_el=pos[0],son_el=pos[-1],
            medyan_gap=float(np.median(gaps)) if gaps else None,max_gap=max(gaps) if gaps else None,
            H1=gcc['H1_art_arda'],H2=gcc['H2_1_atlama'],H3=gcc['H3_2_atlama'],uyku3_5=gcc['uyku_3_5'],
            uyku6_11=gcc['uyku_6_11'],uyku12plus=gcc['uyku_12plus'],zincir=','.join(map(str,pos))))
        fs=set(fam)
        for oi,el in enumerate(pos):
            cur=sets[el-1]; prev=sets[el-2] if el>1 else set(); nxt=sets[el] if el<N else set()
            events.append(dict(date=day,draw=int(daydf.iloc[el-1].draw),el=el,boyut=k,aile='-'.join(map(str,fam)),tip=typ,gelis_no=oi+1,
                onceki_aile_uyesi=len(fs&prev),sonraki_aile_uyesi=len(fs&nxt),oncekinden_tasinan_toplam=len(cur&prev),
                sonraki_ele_tasinan_toplam=len(cur&nxt),aile_disi_oncekinden_tasinan=len((cur-fs)&prev),
                aile_disi_sonraki_tasinan=len((cur-fs)&nxt),onceki_bant=band_counts(prev) if prev else '',olay_bant=band_counts(cur),
                sonraki_bant=band_counts(nxt) if nxt else '',onceki_20='-'.join(map(str,sorted(prev))) if prev else '',
                sonraki_20='-'.join(map(str,sorted(nxt))) if nxt else ''))
    types=[dict(date=day,boyut=k,tip=t,tekrarlayan_aile=n) for t,n in tc.items()]
    return {'occ':occ,'life':pd.DataFrame(life),'events':pd.DataFrame(events),'types':pd.DataFrame(types)}

def growth_between(day,small_occ,big_occ,k):
    rows=[]; child_index=defaultdict(list)
    for child,cpos in big_occ.items():
        for parent in combinations(child,k): child_index[parent].append((child,cpos))
    for parent,ppos in small_occ.items():
        for pel in ppos:
            best=None
            for child,cpos in child_index.get(parent,[]):
                later=[x for x in cpos if x>pel]
                if later:
                    v=(min(later),child)
                    if best is None or v[0]<best[0]: best=v
            if best:
                cel,child=best
                rows.append(dict(date=day,gecis=f'{k}->{k+1}',cekirdek='-'.join(map(str,parent)),cekirdek_el=pel,
                                 cocuk='-'.join(map(str,child)),cocuk_el=cel,bekleme=cel-pel))
    return pd.DataFrame(rows)

def singles_context(daydf):
    daydf=daydf.copy().reset_index(drop=True); day=str(daydf.date.iloc[0]); sets=[set(x) for x in daydf.nums]; N=len(sets); rows=[]
    for el,S in enumerate(sets,1):
        prev=sets[el-2] if el>1 else set(); nxt=sets[el] if el<N else set()
        for n in sorted(S): rows.append(dict(date=day,el=el,draw=int(daydf.iloc[el-1].draw),sayi=n,bant=band(n),onceki_var=int(n in prev),sonraki_var=int(n in nxt)))
    return pd.DataFrame(rows)

# ---------- checkpoint ----------
def stage_path(day,k): return STORE/f'{day}_K{k}.pkl'
def day_path(day): return STORE/f'{day}_FINAL.pkl'

def valid_stage(day,k):
    p=stage_path(day,k)
    if not p.exists(): return False
    try:
        r=read_pickle(p); return isinstance(r,dict) and all(x in r for x in ('occ','life','events','types'))
    except Exception:
        p.unlink(missing_ok=True); return False

def valid_day(day):
    p=day_path(day)
    if not p.exists(): return False
    try:
        r=read_pickle(p); return isinstance(r,dict) and all(x in r for x in ('life','events','growth','types','singles'))
    except Exception:
        p.unlink(missing_ok=True); return False

def finalize_day(day,daydf):
    ks={k:read_pickle(stage_path(day,k)) for k in (2,3,4,5)}
    life=pd.concat([ks[k]['life'] for k in (2,3,4,5)],ignore_index=True)
    events=pd.concat([ks[k]['events'] for k in (2,3,4,5)],ignore_index=True)
    types=pd.concat([ks[k]['types'] for k in (2,3,4,5)],ignore_index=True)
    growth=pd.concat([growth_between(day,ks[k]['occ'],ks[k+1]['occ'],k) for k in (2,3,4)],ignore_index=True)
    return {'life':life,'events':events,'growth':growth,'types':types,'singles':singles_context(daydf)}

def csvb(d): return d.to_csv(index=False).encode('utf-8-sig')
def make_day_zip(day,res):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name,d in res.items(): z.writestr(f'{day}_{name.upper()}.csv',csvb(d))
        z.writestr(f'{day}_README.txt',('AILE V4.2\nAraştırma/analiz.\n2/3/4/5 yaşam tabloları >=2 görülüşlü ailelerdir.\n'
          'Her gün 4 checkpoint: K2,K3,K4,K5. EVENTS önceki/olay/sonraki el bağlamıdır. GROWTH kronolojiktir.\n').encode())
    out=b.getvalue()
    if not zip_ok(out): raise RuntimeError(f'{day} ZIP CRC başarısız')
    return out

def aggregate(daily):
    keys=['life','events','growth','types','singles']; agg={}
    for k in keys: agg[k]=pd.concat([daily[d][k] for d in daily],ignore_index=True)
    ev=agg['events']; gr=agg['growth']
    char=ev.groupby(['boyut','tip']).agg(olay=('aile','size'),onceki_aile_ort=('onceki_aile_uyesi','mean'),sonraki_aile_ort=('sonraki_aile_uyesi','mean'),sonraki_tasima_ort=('sonraki_ele_tasinan_toplam','mean')).reset_index() if not ev.empty else pd.DataFrame()
    gg=gr.groupby('gecis').agg(buyume_olayi=('cekirdek','size'),medyan_bekleme=('bekleme','median'),ortalama_bekleme=('bekleme','mean')).reset_index() if not gr.empty else pd.DataFrame()
    return agg,char,gg

def make_part_zip(no,days,daily):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for day in days: z.writestr(f'{day}_TAM_ARASTIRMA.zip',make_day_zip(day,daily[day]))
        sub={d:daily[d] for d in days}; agg,char,gg=aggregate(sub)
        z.writestr('PARCA_KARAKTER_OZET.csv',csvb(char)); z.writestr('PARCA_BUYUME_OZET.csv',csvb(gg))
        z.writestr('MANIFEST.json',json.dumps({'version':'V4.2','part':no,'days':days},ensure_ascii=False,indent=2))
    out=b.getvalue()
    if not zip_ok(out): raise RuntimeError(f'Parça {no} CRC başarısız')
    return out

# ---------- UI ----------
df,src=load_input()
if df.empty: st.info('Repo yanında veri.txt bulunsun veya yükle.'); st.stop()
DAYS=sorted(df.date.unique())
valid=(len(df)==3038 and len(DAYS)==14 and all(len(g)==217 for _,g in df.groupby('date')))
st.write(f'**Kaynak:** {src} • **Çekiliş:** {len(df)} • **Gün:** {len(DAYS)}')
if not valid: st.error('Veri kapısı geçmedi: 14 × 217 = 3038 gerekli.'); st.stop()
st.success('Veri kapısı geçti: 14 gün × 217 = 3038 çekiliş.')
st.markdown('**Araştırma:** tekil bağlam + serbest/ardışık/atlamalı 2–5 aile + tekrar/ritim/uyku + kronolojik 2→3→4→5 büyüme + önceki/sonraki el + bant/taşıma.')

c1,c2=st.columns([3,1])
with c1:
    if st.button('▶️ TEK TUŞ — ARAŞTIRMAYI BAŞLAT / DEVAM ET',type='primary',width='stretch'):
        RUN_FLAG.write_text('1'); st.rerun()
with c2:
    if st.button('⏹️ DURDUR',width='stretch'):
        RUN_FLAG.unlink(missing_ok=True); st.rerun()

# 56 aşamalı ilerleme
completed_stages=sum(valid_stage(d,k) for d in DAYS for k in (2,3,4,5))
completed_days=sum(valid_day(d) for d in DAYS)
st.progress(completed_stages/56,text=f'{completed_stages}/56 alt aşama • {completed_days}/14 gün tamamlandı')

# Bir rerun = yalnız bir K aşaması. K5 bittikten sonra gün finalize edilir.
if RUN_FLAG.exists():
    target=None
    for d in DAYS:
        if valid_day(d): continue
        for k in (2,3,4,5):
            if not valid_stage(d,k): target=(d,k); break
        if target: break
        # dört stage var ama final yoksa sadece finalleştir
        target=(d,'FINAL'); break
    if target:
        d,k=target; box=st.status(f'🔬 {d} — {"gün birleştiriliyor" if k=="FINAL" else str(k)+"’li aile aşaması"}…',expanded=True)
        try:
            daydf=df[df.date==d].copy()
            if k=='FINAL':
                res=finalize_day(d,daydf); dz=make_day_zip(d,res)
                if not zip_ok(dz): raise RuntimeError('Günlük CRC geçmedi')
                atomic_pickle(day_path(d),res); del res,dz
                box.update(label=f'✅ {d} — 4/4 aşama birleştirildi',state='complete',expanded=False)
            else:
                res=research_k(daydf,k); atomic_pickle(stage_path(d,k),res); del res
                box.update(label=f'✅ {d} — K{k} checkpoint tamamlandı',state='complete',expanded=False)
            gc.collect(); st.rerun()
        except Exception as e:
            RUN_FLAG.unlink(missing_ok=True); box.update(label='❌ Araştırma durduruldu',state='error',expanded=True); st.error(f'{d} / {k}: {type(e).__name__}: {e}')
    else:
        # 14 gün hazır: paketle
        try:
            daily={d:read_pickle(day_path(d)) for d in DAYS}; part_files=[]
            for pi,idxs in enumerate(PARTS,1):
                days=[DAYS[i] for i in idxs]; pb=make_part_zip(pi,days,daily); p=STORE/f'AILE_V42_PARCA_{pi}.zip'; tmp=p.with_suffix('.tmp'); tmp.write_bytes(pb); os.replace(tmp,p); part_files.append(p)
            agg,char,gg=aggregate(daily); master=io.BytesIO()
            with zipfile.ZipFile(master,'w',zipfile.ZIP_DEFLATED) as z:
                for p in part_files: z.writestr(p.name,p.read_bytes())
                z.writestr('14_GUN_KARAKTER_OZET.csv',csvb(char)); z.writestr('14_GUN_BUYUME_OZET.csv',csvb(gg)); z.writestr('14_GUN_TIP_OZET.csv',csvb(agg['types']))
                z.writestr('MASTER_MANIFEST.json',json.dumps({'version':'V4.2','draws':len(df),'days':DAYS,'sha256_parts':{p.name:sha256_bytes(p.read_bytes()) for p in part_files}},ensure_ascii=False,indent=2))
            mb=master.getvalue()
            if not zip_ok(mb): raise RuntimeError('MASTER CRC başarısız')
            mp=STORE/'HIZLI_ON_14_GUN_AILE_ARASTIRMA_V4_2_MASTER.zip'; tmp=mp.with_suffix('.tmp'); tmp.write_bytes(mb); os.replace(tmp,mp)
            RUN_FLAG.unlink(missing_ok=True); st.success('✅ 14/14 tamamlandı; 4 parça + Master doğrulandı.'); st.rerun()
        except Exception as e:
            RUN_FLAG.unlink(missing_ok=True); st.error(f'Paketleme: {type(e).__name__}: {e}')

st.divider(); st.subheader('📦 Doğrulanmış Çıktılar')
for pi in range(1,5):
    p=STORE/f'AILE_V42_PARCA_{pi}.zip'
    if p.exists():
        b=p.read_bytes()
        if zip_ok(b): st.download_button(f'⬇️ PARÇA {pi}',b,p.name,'application/zip',key=f'p{pi}',width='stretch')
mp=STORE/'HIZLI_ON_14_GUN_AILE_ARASTIRMA_V4_2_MASTER.zip'
if mp.exists():
    b=mp.read_bytes()
    if zip_ok(b): st.download_button('⬇️ 14 GÜNLÜK MASTER',b,mp.name,'application/zip',key='master',width='stretch')
st.caption('V4.2 güvenlik: 56 alt checkpoint + günlük atomik kayıt + 4 parça + CRC + SHA-256. Bağlantı koparsa Başlat/Devam Et ile kaldığı aşamadan sürer.')
