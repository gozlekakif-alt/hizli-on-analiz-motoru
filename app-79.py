import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import defaultdict
from pathlib import Path
import sqlite3, io, zipfile, hashlib, json, gc, os, shutil, tempfile

st.set_page_config(page_title='Hızlı On — Günlük Aile Araştırma V5.1', layout='wide')
st.title('🧬 Hızlı On — Günlük Aile Araştırma V5.1')
st.caption('SADECE ARAŞTIRMA • 1 gün = 1 tuş • 6 kanal • sonuçlar RAM yerine günlük SQLite veritabanına yazılır • 2 gün = 1 paket')
ROOT=Path(__file__).parent
DATA_DEFAULT=ROOT/'veri.txt'
STORE=ROOT/'aile_v51_gunluk'; STORE.mkdir(exist_ok=True)
PAIR_INDEX=[(0,1),(2,3),(4,5),(6,7),(8,9),(10,11),(12,13)]

def zip_ok_bytes(b):
    try:
        with zipfile.ZipFile(io.BytesIO(b),'r') as z: return z.testzip() is None
    except Exception: return False

def zip_ok_path(p):
    try:
        with zipfile.ZipFile(p,'r') as z: return z.testzip() is None
    except Exception: return False

def sha_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
    return h.hexdigest()

def atomic_replace(src,dst): os.replace(src,dst)

@st.cache_data(show_spinner=False)
def parse_data(raw):
    rows=[]
    for line in raw.decode('utf-8-sig').splitlines():
        p=[x.strip() for x in line.split(';')]
        if len(p)!=3: continue
        try:
            nums=tuple(sorted(map(int,p[2].split(',')))); dt=pd.to_datetime(p[1],dayfirst=True); draw=int(p[0])
        except Exception: continue
        if len(nums)==20 and len(set(nums))==20 and min(nums)>=1 and max(nums)<=80: rows.append((draw,dt,nums))
    d=pd.DataFrame(rows,columns=['draw','dt','nums']).sort_values('dt').reset_index(drop=True)
    d['date']=d.dt.dt.strftime('%Y-%m-%d'); d['day_el']=d.groupby('date').cumcount()+1
    return d

if DATA_DEFAULT.exists(): raw=DATA_DEFAULT.read_bytes(); source='repo/veri.txt'
else:
    up=st.file_uploader('veri.txt yükle',type=['txt'])
    if up is None: st.stop()
    raw=up.getvalue(); source='yüklenen veri.txt'
df=parse_data(raw); DAYS=sorted(df.date.unique())
if len(df)!=3038 or len(DAYS)!=14 or any(len(df[df.date==d])!=217 for d in DAYS):
    st.error(f'Veri kontrolü geçmedi: {len(df)} çekiliş / {len(DAYS)} gün. Beklenen 3038 / 14 ve her gün 217.'); st.stop()
st.success(f'Veri doğrulandı: {source} • 14 gün × 217 = 3038 çekiliş')

IDX={k:np.array(list(combinations(range(20),k)),dtype=np.int8) for k in (2,3,4,5)}
def dec(v,k):
    out=[0]*k; v=int(v)
    for i in range(k-1,-1,-1): out[i]=v&127; v>>=7
    return tuple(out)
def encoded_draw(nums,k):
    nums=tuple(sorted(int(x) for x in nums))
    if len(nums)!=20: raise ValueError('20 sayı bekleniyor')
    a=np.fromiter(nums,dtype=np.uint64,count=20); ix=IDX[k]
    vals=np.zeros(len(ix),dtype=np.uint64)
    for j in range(k): vals=(vals<<np.uint64(7))|a[ix[:,j]]
    return vals

def init_db(path,day,draws):
    con=sqlite3.connect(path); cur=con.cursor()
    cur.execute('PRAGMA journal_mode=DELETE'); cur.execute('PRAGMA synchronous=NORMAL')
    cur.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
    cur.executemany('INSERT INTO meta VALUES(?,?)',[('gun',day),('cekilis',str(draws)),('surum','V5.1'),('amac','yalniz arastirma')])
    cur.execute('CREATE TABLE aile_yasam(boyut INTEGER,aile TEXT,toplam INTEGER,ilk_el INTEGER,son_el INTEGER,ikinci_el INTEGER,ilk_tekrar_gap INTEGER,medyan_gap REAL,min_gap INTEGER,max_gap INTEGER,art_arda INTEGER,atlama1 INTEGER,atlama2 INTEGER,uyku4_6 INTEGER,uyku7_12 INTEGER,uyku13plus INTEGER,zincir TEXT)')
    cur.execute('CREATE INDEX ix_aile ON aile_yasam(boyut,aile)')
    cur.execute('CREATE TABLE aile_ozet(boyut INTEGER PRIMARY KEY,benzersiz_toplam INTEGER,tek_gorulen INTEGER,tekrarlayan INTEGER,max_frekans INTEGER)')
    cur.execute('CREATE TABLE geometri(tip TEXT,adim INTEGER,boyut INTEGER,aile TEXT,toplam INTEGER,zincir TEXT)')
    cur.execute('CREATE TABLE baglam(boyut INTEGER,aile TEXT,olay_el INTEGER,aile_prevde_kac INTEGER,aile_sonrada_kac INTEGER,prevden_tasima INTEGER,sonraya_tasima INTEGER,prev_diger TEXT,olay_diger TEXT,sonra_diger TEXT)')
    cur.execute('CREATE TABLE bant(el INTEGER,prev_tasima INTEGER,sonraya_tasima INTEGER,b1 INTEGER,b2 INTEGER,b3 INTEGER,b4 INTEGER,b5 INTEGER,b6 INTEGER,b7 INTEGER,b8 INTEGER)')
    cur.execute('CREATE TABLE buyume(el INTEGER,sonraki_el INTEGER,boyut INTEGER,cekirdek TEXT,korunan_kesisim INTEGER,eklenen_sayi TEXT,ayrilan_sayi TEXT)')
    con.commit(); return con

def write_family(con,day_nums,k):
    per=[encoded_draw(S,k) for S in day_nums]
    allv=np.concatenate(per); uniq,cnt=np.unique(allv,return_counts=True)
    repeated=uniq[cnt>=2]; rep_set=set(map(int,repeated.tolist()))
    con.execute('INSERT INTO aile_ozet VALUES(?,?,?,?,?)',(k,int(len(uniq)),int(np.sum(cnt==1)),int(len(repeated)),int(cnt.max())))
    pos=defaultdict(list)
    for el,arr in enumerate(per,1):
        for v in arr:
            iv=int(v)
            if iv in rep_set: pos[iv].append(el)
    batch=[]
    for v,ps in pos.items():
        gaps=np.diff(ps); fam='-'.join(map(str,dec(v,k)))
        batch.append((k,fam,len(ps),ps[0],ps[-1],ps[1],ps[1]-ps[0],float(np.median(gaps)),int(gaps.min()),int(gaps.max()),int(np.sum(gaps==1)),int(np.sum(gaps==2)),int(np.sum(gaps==3)),int(np.sum((gaps>=4)&(gaps<=6))),int(np.sum((gaps>=7)&(gaps<=12))),int(np.sum(gaps>=13)),','.join(map(str,ps))))
        if len(batch)>=5000:
            con.executemany('INSERT INTO aile_yasam VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch); con.commit(); batch=[]
    if batch: con.executemany('INSERT INTO aile_yasam VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch); con.commit()
    stats=(int(len(uniq)),int(np.sum(cnt==1)),int(len(repeated)),int(cnt.max()))
    del per,allv,uniq,cnt,repeated,rep_set,pos,batch; gc.collect(); return stats

def write_geometry(con,day_nums):
    rows=[]
    for step,name in ((1,'ardisik'),(2,'1_atlamali'),(3,'2_atlamali')):
        for k in (2,3,4,5):
            for a in range(1,82-step*(k-1)):
                fam=tuple(a+step*j for j in range(k))
                if fam[-1]>80: continue
                fs=set(fam); ps=[i+1 for i,S in enumerate(day_nums) if fs.issubset(S)]
                if ps: rows.append((name,step,k,'-'.join(map(str,fam)),len(ps),','.join(map(str,ps))))
    con.executemany('INSERT INTO geometri VALUES(?,?,?,?,?,?)',rows); con.commit(); return len(rows)

def write_context(con,day_nums):
    cur=con.execute('SELECT boyut,aile,ilk_el FROM aile_yasam')
    batch=[]; n=0
    for k,aile,ilk_el in cur:
        fam=set(map(int,aile.split('-'))); e=ilk_el-1
        curS=day_nums[e]; prev=day_nums[e-1] if e>0 else set(); nxt=day_nums[e+1] if e+1<len(day_nums) else set()
        batch.append((k,aile,e+1,len(fam&prev),len(fam&nxt),len(prev&curS),len(curS&nxt),','.join(map(str,sorted(prev-fam))),','.join(map(str,sorted(curS-fam))),','.join(map(str,sorted(nxt-fam)))))
        n+=1
        if len(batch)>=5000:
            con.executemany('INSERT INTO baglam VALUES(?,?,?,?,?,?,?,?,?,?)',batch); con.commit(); batch=[]
    if batch: con.executemany('INSERT INTO baglam VALUES(?,?,?,?,?,?,?,?,?,?)',batch); con.commit()
    return n

def write_bands(con,day_nums):
    rows=[]
    for i,S in enumerate(day_nums):
        prev=day_nums[i-1] if i else set(); nxt=day_nums[i+1] if i+1<len(day_nums) else set()
        bs=[sum(b*10+1<=n<=b*10+10 for n in S) for b in range(8)]
        rows.append((i+1,len(S&prev),len(S&nxt),*bs))
    con.executemany('INSERT INTO bant VALUES(?,?,?,?,?,?,?,?,?,?,?)',rows); con.commit(); return len(rows)

def write_growth(con,day_nums):
    batch=[]; n=0
    for i in range(len(day_nums)-1):
        A=day_nums[i]; B=day_nums[i+1]; inter=sorted(A&B); added=','.join(map(str,sorted(B-A))); removed=','.join(map(str,sorted(A-B)))
        for k in (2,3,4,5):
            if len(inter)<k: continue
            for fam in combinations(inter,k):
                batch.append((i+1,i+2,k,'-'.join(map(str,fam)),len(inter),added,removed)); n+=1
                if len(batch)>=5000:
                    con.executemany('INSERT INTO buyume VALUES(?,?,?,?,?,?,?)',batch); con.commit(); batch=[]
    if batch: con.executemany('INSERT INTO buyume VALUES(?,?,?,?,?,?,?)',batch); con.commit()
    return n

def make_day_zip(day,dbpath,summary):
    out=STORE/f'{day}_AILE_ARASTIRMA_V51.zip'; tmp=STORE/f'{day}.zip.tmp'
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.write(dbpath,arcname=f'{day}_AILE_ARASTIRMA.sqlite')
        z.writestr(f'{day}_OZET.json',json.dumps(summary,ensure_ascii=False,indent=2))
        z.writestr('ACIKLAMA.txt','Bu paket kupon/tahmin üretmez. aile_yasam: tekrarlayan ailelerin tam yaşam zinciri; aile_ozet: tek görülenler dahil tüm benzersiz aile sayıları; geometri: ardışık/+2/+3; baglam: ilk doğum öncesi-olay-sonrası; bant: 8 bant ve taşıma; buyume: komşu ellerde korunan çekirdeklerin eksiksiz kronolojik kayıtları.\n')
    if not zip_ok_path(tmp): tmp.unlink(missing_ok=True); raise RuntimeError('ZIP CRC testi geçmedi')
    atomic_replace(tmp,out); return out

def pair_zip(no,d1,d2):
    p1=STORE/f'{d1}_AILE_ARASTIRMA_V51.zip'; p2=STORE/f'{d2}_AILE_ARASTIRMA_V51.zip'
    if not zip_ok_path(p1) or not zip_ok_path(p2): return None
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(p1,p1.name); z.write(p2,p2.name)
        z.writestr('MANIFEST.json',json.dumps({'parca':no,'gunler':[d1,d2],'sha256':{d1:sha_file(p1),d2:sha_file(p2)}},indent=2))
    b=bio.getvalue(); return b if zip_ok_bytes(b) else None

st.divider(); st.subheader('📅 Günlük araştırma')
done=[d for d in DAYS if zip_ok_path(STORE/f'{d}_AILE_ARASTIRMA_V51.zip')]
cols=st.columns(7)
for i,d in enumerate(DAYS): cols[i%7].write(('✅' if d in done else '⬜')+f' {i+1}. gün\n{d}')
st.progress(len(done)/14,text=f'{len(done)}/14 gün tamamlandı')
next_day=next((d for d in DAYS if d not in done),None)
if next_day:
    st.info(f'Sıradaki: **{DAYS.index(next_day)+1}. gün — {next_day}**')
    if st.button('▶️ BU GÜNÜ TEK TUŞLA 6 KANAL ARAŞTIR',type='primary',width='stretch'):
        g=df[df.date==next_day].reset_index(drop=True); day_nums=[set(map(int,x)) for x in g.nums]
        dbtmp=STORE/f'{next_day}.sqlite.tmp'; dbtmp.unlink(missing_ok=True); con=init_db(dbtmp,next_day,len(g)); p=st.progress(0,text='1/6 Aile yaşamları...')
        try:
            famstats={}
            for j,k in enumerate((2,3,4,5)):
                famstats[k]=write_family(con,day_nums,k); p.progress(.10+.08*j,text=f'1/6 Aile yaşamları — {k}li tamamlandı')
            p.progress(.48,text='2/6 Ardışık/atlamalı...'); ngeo=write_geometry(con,day_nums)
            p.progress(.60,text='3/6 Önce–olay–sonra...'); nctx=write_context(con,day_nums)
            p.progress(.72,text='4/6 Bant/taşıma...'); nb=write_bands(con,day_nums)
            p.progress(.82,text='5/6 Kronolojik büyüme/küçülme...'); ng=write_growth(con,day_nums)
            con.execute('PRAGMA optimize'); con.commit(); con.close(); con=None
            summary={'gun':next_day,'cekilis':len(g),'ilk_cekilis':int(g.draw.iloc[0]),'son_cekilis':int(g.draw.iloc[-1]),'aile_ozet':{str(k):{'benzersiz':v[0],'tek_gorulen':v[1],'tekrarlayan':v[2],'max_frekans':v[3]} for k,v in famstats.items()},'geometri':ngeo,'baglam':nctx,'bant':nb,'buyume':ng}
            p.progress(.94,text='6/6 ZIP + CRC + SHA-256...'); out=make_day_zip(next_day,dbtmp,summary); dbtmp.unlink(missing_ok=True)
            p.progress(1.0,text='Tamamlandı ✅'); st.success(f'{next_day} sağlam tamamlandı • SHA-256 {sha_file(out)[:16]}…')
            st.download_button(f'⬇️ {next_day} GÜN YEDEĞİNİ İNDİR',out.read_bytes(),out.name,'application/zip',width='stretch')
            st.warning('Bu günlük ZIP’i indir. İndirdikten sonra sayfayı yenileyip sonraki güne geç.')
        except Exception as e:
            if con is not None: con.close()
            dbtmp.unlink(missing_ok=True); st.exception(e)
        finally:
            del day_nums,g; gc.collect()
else: st.success('14/14 tamamlandı.')

st.divider(); st.subheader('📦 İki günlük paketler')
for no,(a,b) in enumerate(PAIR_INDEX,1):
    d1,d2=DAYS[a],DAYS[b]; pb=pair_zip(no,d1,d2)
    if pb:
        st.download_button(f'⬇️ PARÇA {no} — {d1} + {d2}',pb,f'PARCA_{no}_{d1}_{d2}_AILE_V51.zip','application/zip',key=f'p{no}',width='stretch')
    else: st.caption(f'PARÇA {no}: {d1} + {d2} — iki gün tamamlanınca açılır.')
st.caption('V5.1: Her gün bağımsız. Ağır aile tabloları RAM’de birlikte tutulmaz; SQLite’a parça parça yazılır. Her günlük ZIP CRC ile doğrulanır. Kupon/tahmin yok.')
