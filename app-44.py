import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path
import io, zipfile, hashlib, json, pickle, gc, os

st.set_page_config(page_title='Hızlı On — Günlük Aile Araştırma V5', layout='wide')
st.title('🧬 Hızlı On — Günlük Aile Araştırma Laboratuvarı V5')
st.caption('SADECE ARAŞTIRMA/ANALİZ • 1 gün = 1 tuş • 6 araştırma kanalı • 2 gün = 1 doğrulanmış ZIP • toplam 7 ZIP')

ROOT=Path(__file__).parent
DATA_DEFAULT=ROOT/'veri.txt'
STORE=ROOT/'aile_v5_gunluk'; STORE.mkdir(exist_ok=True)
PAIR_INDEX=[(0,1),(2,3),(4,5),(6,7),(8,9),(10,11),(12,13)]

# ---------- temel güvenlik ----------
def zip_ok(b):
    try:
        with zipfile.ZipFile(io.BytesIO(b),'r') as z: return z.testzip() is None
    except Exception: return False

def sha256(b): return hashlib.sha256(b).hexdigest()

def atomic_write(path,b):
    tmp=Path(str(path)+'.tmp')
    tmp.write_bytes(b); os.replace(tmp,path)

def atomic_pickle(path,obj):
    tmp=Path(str(path)+'.tmp')
    with open(tmp,'wb') as f: pickle.dump(obj,f,pickle.HIGHEST_PROTOCOL)
    os.replace(tmp,path)

# ---------- veri ----------
@st.cache_data(show_spinner=False)
def parse_data(raw):
    text=raw.decode('utf-8-sig')
    rows=[]
    for ln,line in enumerate(text.splitlines(),1):
        p=[x.strip() for x in line.split(';')]
        if len(p)!=3: continue
        try:
            nums=tuple(sorted(map(int,p[2].split(','))))
            dt=pd.to_datetime(p[1],dayfirst=True)
            draw=int(p[0])
        except Exception: continue
        if len(nums)==20 and len(set(nums))==20 and min(nums)>=1 and max(nums)<=80:
            rows.append((draw,dt,nums))
    d=pd.DataFrame(rows,columns=['draw','dt','nums']).sort_values('dt').reset_index(drop=True)
    d['date']=d.dt.dt.strftime('%Y-%m-%d')
    d['day_el']=d.groupby('date').cumcount()+1
    return d

if DATA_DEFAULT.exists(): raw=DATA_DEFAULT.read_bytes()
else:
    up=st.file_uploader('veri.txt yükle',type=['txt'])
    if up is None: st.stop()
    raw=up.getvalue()

df=parse_data(raw); DAYS=sorted(df.date.unique())
if len(df)!=3038 or len(DAYS)!=14 or any(len(df[df.date==d])!=217 for d in DAYS):
    st.error(f'Veri kontrolü geçmedi: {len(df)} çekiliş / {len(DAYS)} gün. Beklenen 3038 / 14 ve her gün 217 çekiliş.')
    st.stop()
st.success('Veri doğrulandı: 3.038 çekiliş • 14 gün • her gün 217 çekiliş')

# ---------- aile kodlama: düşük RAM ----------
# 1..80 sayıları 7 bitlik alanlara kodlanır; aile kimliği kayıpsız uint64 olur.
def enc(fam):
    v=0
    for n in fam: v=(v<<7)|int(n)
    return v

def dec(v,k):
    out=[0]*k; v=int(v)
    for i in range(k-1,-1,-1): out[i]=v&127; v>>=7
    return tuple(out)

IDX={k:np.array(list(combinations(range(20),k)),dtype=np.int8) for k in (2,3,4,5)}

def encoded_draw(nums,k):
    a=np.asarray(nums,dtype=np.uint64); ix=IDX[k]
    vals=np.zeros(len(ix),dtype=np.uint64)
    for j in range(k): vals=(vals<<np.uint64(7))|a[ix[:,j]]
    return vals

def family_lifecycle(day_nums,k,progress=None):
    # Tüm aileler sayılır; devasa Python set/DataFrame yok. uint64 diziler kullanılır.
    per=[]
    for i,nums in enumerate(day_nums):
        per.append(encoded_draw(nums,k))
        if progress and i%40==0: progress(min(.45,(i+1)/len(day_nums)*.45))
    allv=np.concatenate(per); uniq,cnt=np.unique(allv,return_counts=True)
    repeated=uniq[cnt>=2]
    rep_set=set(map(int,repeated.tolist()))  # yalnız tekrarlayan aileler
    pos=defaultdict(list)
    for el,arr in enumerate(per,1):
        for v in arr:
            iv=int(v)
            if iv in rep_set: pos[iv].append(el)
    rows=[]
    for v,ps in pos.items():
        gaps=np.diff(ps)
        rows.append({
            'aile':'-'.join(map(str,dec(v,k))),'boyut':k,'toplam':len(ps),'ilk_el':ps[0],'son_el':ps[-1],
            'ikinci_el':ps[1],'ilk_tekrar_gap':ps[1]-ps[0],
            'medyan_gap':float(np.median(gaps)),'min_gap':int(np.min(gaps)),'max_gap':int(np.max(gaps)),
            'art_arda':int(np.sum(gaps==1)),'1_atlama':int(np.sum(gaps==2)),'2_atlama':int(np.sum(gaps==3)),
            'uyku4_6':int(np.sum((gaps>=4)&(gaps<=6))),'uyku7_12':int(np.sum((gaps>=7)&(gaps<=12))),
            'uyku13plus':int(np.sum(gaps>=13)),'zincir':','.join(map(str,ps))})
    del allv,uniq,cnt,repeated,rep_set,pos,per; gc.collect()
    return pd.DataFrame(rows).sort_values(['toplam','medyan_gap'],ascending=[False,True]).reset_index(drop=True) if rows else pd.DataFrame()

# ---------- 6 araştırma kanalı ----------
def geometry(day_nums):
    out=[]
    for step,name in [(1,'ardisik'),(2,'1_atlamali'),(3,'2_atlamali')]:
        for k in (2,3,4,5):
            for a in range(1,81-step*(k-1)):
                fam=tuple(a+step*j for j in range(k)); fs=set(fam)
                ps=[i+1 for i,S in enumerate(day_nums) if fs.issubset(S)]
                if ps: out.append({'tip':name,'adim':step,'boyut':k,'aile':'-'.join(map(str,fam)),'toplam':len(ps),'zincir':','.join(map(str,ps))})
    return pd.DataFrame(out)

def context_table(day_nums, fam_tables):
    # Her tekrarlayan aile için doğumdan önce / doğum / sonra bağlamı. Çıktı bounded: aile başına ilk olay.
    rows=[]
    for k,t in fam_tables.items():
        if t.empty: continue
        for r in t.itertuples():
            fam=tuple(map(int,r.aile.split('-'))); e=int(r.ilk_el)-1
            cur=set(day_nums[e]); prev=set(day_nums[e-1]) if e>0 else set(); nxt=set(day_nums[e+1]) if e+1<len(day_nums) else set()
            rows.append({'boyut':k,'aile':r.aile,'olay_el':e+1,
              'aile_prevde_kac':len(set(fam)&prev),'aile_sonrada_kac':len(set(fam)&nxt),
              'prevden_tasima':len(prev&cur),'sonraya_tasima':len(cur&nxt),
              'prev_diger':','.join(map(str,sorted(prev-set(fam)))),'olay_diger':','.join(map(str,sorted(cur-set(fam)))),
              'sonra_diger':','.join(map(str,sorted(nxt-set(fam))))})
    return pd.DataFrame(rows)

def band_context(day_nums):
    rows=[]
    for i,S in enumerate(day_nums):
        prev=day_nums[i-1] if i else set(); nxt=day_nums[i+1] if i+1<len(day_nums) else set()
        rec={'el':i+1,'prev_tasima':len(S&prev),'sonraya_tasima':len(S&nxt)}
        for b in range(8): rec[f'bant_{b*10+1}_{b*10+10}']=sum(b*10+1<=n<=b*10+10 for n in S)
        rows.append(rec)
    return pd.DataFrame(rows)

def growth_events(day_nums):
    # Gerçek kronolojik komşu-el büyüme/küçülme: t -> t+1 kesişiminden 2..5 çekirdekler.
    rows=[]
    for i in range(len(day_nums)-1):
        A=day_nums[i]; B=day_nums[i+1]; inter=sorted(A&B)
        added=sorted(B-A); removed=sorted(A-B)
        for k in (2,3,4,5):
            if len(inter)<k: continue
            # kayıt şişmesini engelle: çekirdeğin kendisi yerine olayın yapısal özeti + örnek ilk 100 aile
            combs=list(combinations(inter,k))
            for fam in combs[:100]:
                rows.append({'el':i+1,'sonraki_el':i+2,'boyut':k,'cekirdek':'-'.join(map(str,fam)),
                             'korunan_kesisim':len(inter),'eklenen_sayi':','.join(map(str,added)),
                             'ayrilan_sayi':','.join(map(str,removed))})
    return pd.DataFrame(rows)

def day_zip(day, fam, geo, ctx, bands, growth, meta):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for k,t in fam.items(): z.writestr(f'{day}_01_AILE_YASAM_{k}LU.csv',t.to_csv(index=False))
        z.writestr(f'{day}_02_ARDISIK_ATLAMALI.csv',geo.to_csv(index=False))
        z.writestr(f'{day}_03_ONCE_OLAY_SONRA.csv',ctx.to_csv(index=False))
        z.writestr(f'{day}_04_BANT_CEVRE.csv',bands.to_csv(index=False))
        z.writestr(f'{day}_05_BUYUME_KUCULME.csv',growth.to_csv(index=False))
        z.writestr(f'{day}_06_OZET.json',json.dumps(meta,ensure_ascii=False,indent=2))
        z.writestr('ACIKLAMA.txt','Kupon üretmez. AILE_YASAM tabloları gün içindeki TÜM aileleri sayar; yaşam tablosunda ritim için en az 2 kez görülen aileler listelenir. BUYUME_KUCULME komşu eller arasındaki kronolojik korunma/eklenme/ayrılma olaylarını araştırır; olay başına ilk 100 çekirdek örneği saklanır.\n')
    b=bio.getvalue()
    if not zip_ok(b): raise RuntimeError('Gün ZIP CRC doğrulaması başarısız')
    return b

def pair_zip(pair_no,d1,d2):
    b1=(STORE/f'{d1}.zip').read_bytes(); b2=(STORE/f'{d2}.zip').read_bytes()
    if not zip_ok(b1) or not zip_ok(b2): raise RuntimeError('Gün ZIP doğrulaması başarısız')
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{d1}_ARASTIRMA.zip',b1); z.writestr(f'{d2}_ARASTIRMA.zip',b2)
        z.writestr('MANIFEST.json',json.dumps({'parca':pair_no,'gunler':[d1,d2],'sha256':{d1:sha256(b1),d2:sha256(b2)}},indent=2))
    out=bio.getvalue()
    if not zip_ok(out): raise RuntimeError('2 günlük ZIP CRC doğrulaması başarısız')
    return out

# ---------- arayüz ----------
st.divider(); st.subheader('📅 Günlük araştırma')
done=[d for d in DAYS if (STORE/f'{d}.zip').exists() and zip_ok((STORE/f'{d}.zip').read_bytes())]
cols=st.columns(7)
for i,d in enumerate(DAYS): cols[i%7].write(('✅' if d in done else '⬜')+f' {i+1}. gün\n{d}')
next_day=next((d for d in DAYS if d not in done),None)
st.progress(len(done)/14,text=f'{len(done)}/14 gün tamamlandı')

if next_day:
    st.info(f'Sıradaki: **{DAYS.index(next_day)+1}. gün — {next_day}**')
    if st.button('▶️ BU GÜNÜ TEK TUŞLA 6 KANAL ARAŞTIR',type='primary',width='stretch'):
        g=df[df.date==next_day].copy().reset_index(drop=True)
        day_nums=[set(x) for x in g.nums]
        p=st.progress(0,text='1/6 Aile yaşamları...')
        fam={}
        for j,k in enumerate((2,3,4,5)):
            fam[k]=family_lifecycle(day_nums,k)
            p.progress(.08+.10*j,text=f'1/6 Aile yaşamları: {k}li tamamlandı')
        p.progress(.50,text='2/6 Ardışık ve atlamalı aileler...'); geo=geometry(day_nums)
        p.progress(.62,text='3/6 Önce–olay–sonra bağlamı...'); ctx=context_table(day_nums,fam)
        p.progress(.74,text='4/6 Bant ve çevre karakteri...'); bands=band_context(day_nums)
        p.progress(.84,text='5/6 Kronolojik büyüme/küçülme...'); growth=growth_events(day_nums)
        meta={'gun':next_day,'cekilis':len(g),'ilk_cekilis':int(g.draw.iloc[0]),'son_cekilis':int(g.draw.iloc[-1]),
              'tekrarlayan_aile':{str(k):len(fam[k]) for k in fam},'geometri_olay':len(geo),'baglam_olay':len(ctx),'buyume_kuculme_kaydi':len(growth)}
        p.progress(.94,text='6/6 ZIP + CRC + SHA-256 doğrulanıyor...')
        b=day_zip(next_day,fam,geo,ctx,bands,growth,meta); atomic_write(STORE/f'{next_day}.zip',b)
        p.progress(1.0,text='Gün tamamlandı ve doğrulandı ✅')
        st.success(f'{next_day} tamamlandı. ZIP sağlam. SHA-256: {sha256(b)[:16]}…')
        st.download_button(f'⬇️ {next_day} GÜN YEDEĞİ',b,f'{next_day}_AILE_ARASTIRMA_V5.zip','application/zip',width='stretch')
        st.info('Gün yedeğini indirmen güvenlik içindir. Sonraki güne geçmek için sayfayı bir kez yenile.')
        del fam,geo,ctx,bands,growth,g,day_nums,b; gc.collect()
else: st.success('14/14 günlük araştırma tamamlandı.')

st.divider(); st.subheader('📦 7 adet iki günlük paket')
for no,(a,b) in enumerate(PAIR_INDEX,1):
    d1,d2=DAYS[a],DAYS[b]
    if d1 in done and d2 in done:
        try:
            pb=pair_zip(no,d1,d2)
            st.download_button(f'⬇️ PARÇA {no} — {d1} + {d2}',pb,f'PARCA_{no}_{d1}_{d2}_AILE_ARASTIRMA.zip','application/zip',key=f'p{no}',width='stretch')
        except Exception as e: st.error(f'Parça {no}: {e}')
    else: st.caption(f'PARÇA {no}: {d1} + {d2} — iki gün tamamlanınca açılır.')

st.caption('V5 güvenlik: 14 günlük tek koşu yok. Her gün bağımsızdır. Her gün ZIP/CRC doğrulanır. İki gün tamamlanınca o çift için ayrı ZIP açılır. Kupon/tahmin üretmez.')
