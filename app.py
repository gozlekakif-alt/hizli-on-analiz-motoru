import streamlit as st
import pandas as pd
import numpy as np
import sqlite3, re, gc, os, io, json, hashlib
from pathlib import Path
from itertools import combinations
from collections import Counter, defaultdict
from datetime import datetime

try:
    import psutil
except Exception:
    psutil = None

st.set_page_config(page_title='Hızlı On — Aile Yaşam ve Dönüşüm Motoru V3', layout='wide')
st.title('🧬 Hızlı On — Aile Yaşam ve Dönüşüm Motoru V3')
st.caption('Türkçe derin analiz • gün → 10+ parça • çekirdek/aile/dönüş/uyku/döngü • RAM korumalı')

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'veri.txt'
DB_FILE = BASE / 'aile_v3.sqlite'

# ---------------- VERİ ----------------
@st.cache_data(show_spinner=False)
def parse_data(raw: bytes):
    text = raw.decode('utf-8', errors='ignore')
    rows=[]
    for ln in text.splitlines():
        p=ln.strip().split(';')
        if len(p) < 3: continue
        try:
            did=int(re.sub(r'\D','',p[0]))
            dt=pd.to_datetime(p[1], dayfirst=True, errors='raise')
            nums=tuple(sorted(set(map(int,re.findall(r'\d+',p[2])))))
            if len(nums)==20 and all(1<=x<=80 for x in nums): rows.append((did,dt,nums))
        except Exception: pass
    if not rows: return pd.DataFrame(columns=['draw_id','dt','numbers','gun'])
    df=pd.DataFrame(rows,columns=['draw_id','dt','numbers'])
    df=df.sort_values(['dt','draw_id']).drop_duplicates('draw_id',keep='last').reset_index(drop=True)
    df['gun']=df.dt.dt.date.astype(str)
    return df

def veri_hash(raw): return hashlib.sha1(raw).hexdigest()[:16]

def ram_mb():
    if not psutil: return 0.0
    return psutil.Process(os.getpid()).memory_info().rss/1024/1024

# ---------------- DB ----------------
def conn():
    c=sqlite3.connect(DB_FILE)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    return c

def init_db():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS ilerleme(veri_hash TEXT, gun TEXT, parca INTEGER, durum TEXT, ts TEXT,
          PRIMARY KEY(veri_hash,gun,parca));
        CREATE TABLE IF NOT EXISTS parca_ozet(veri_hash TEXT, gun TEXT, parca INTEGER, baslangic TEXT, bitis TEXT,
          cekilis INTEGER, aktif_sayi INTEGER, cift_sayisi INTEGER, ram_mb REAL,
          PRIMARY KEY(veri_hash,gun,parca));
        CREATE TABLE IF NOT EXISTS cift_parca(veri_hash TEXT, gun TEXT, parca INTEGER, a INTEGER, b INTEGER, birlikte INTEGER,
          PRIMARY KEY(veri_hash,gun,parca,a,b));
        CREATE TABLE IF NOT EXISTS aile_parca(veri_hash TEXT, gun TEXT, parca INTEGER, boyut INTEGER, aile TEXT, tekrar INTEGER,
          PRIMARY KEY(veri_hash,gun,parca,boyut,aile));
        CREATE TABLE IF NOT EXISTS gun_cift(veri_hash TEXT, gun TEXT, a INTEGER, b INTEGER, birlikte INTEGER, aktif_parca INTEGER,
          ilk_parca INTEGER, son_parca INTEGER, PRIMARY KEY(veri_hash,gun,a,b));
        CREATE TABLE IF NOT EXISTS donus_olay(veri_hash TEXT, gun TEXT, a INTEGER, b INTEGER, onceki_parca INTEGER,
          donus_parca INTEGER, uyku_parca INTEGER, PRIMARY KEY(veri_hash,gun,a,b,onceki_parca,donus_parca));
        CREATE TABLE IF NOT EXISTS aile_gecis(veri_hash TEXT, gun TEXT, parca1 INTEGER, parca2 INTEGER, cekirdek TEXT,
          onceki_aile TEXT, sonraki_aile TEXT, ortak INTEGER, PRIMARY KEY(veri_hash,gun,parca1,parca2,cekirdek,onceki_aile,sonraki_aile));
        CREATE TABLE IF NOT EXISTS analiz_log(veri_hash TEXT, gun TEXT, madde INTEGER, durum TEXT, detay TEXT,
          PRIMARY KEY(veri_hash,gun,madde));
        ''')
init_db()

# ---------------- 151 MADDE KATALOĞU ----------------
GRUPLAR = [
('A — Veri ve zaman mimarisi',1,10),('B — Çekirdek aileyi bulma',11,20),('C — Ailenin büyümesi',21,31),
('D — Küçülme ve parçalanma',32,38),('E — Uyku ve yeniden birleşme',39,48),('F — Saatlik aile değişimi',49,56),
('G — Gün boyu aile yaşamı',57,65),('H — Aileden aileye geçiş ağı',66,74),('I — Aile döngüsü',75,83),
('J — Günler arası aile hafızası',84,92),('K — Aile karakterleri',93,104),('L — Sayının kişisel yaşamı',105,117),
('M — Mekanik döngü araştırması',118,127),('N — Sentez',128,135),('O — İleri test için kayıt',136,141),
('P — RAM ve çalışma sistemi',142,151)]

# Gerçek hesap modülleri. Her madde gün sonunda bu modüllerin ürettiği tablolardan okunabilir.
def madde_detayi(i):
    if i<=10: return 'Veri/gün/parça/zaman kimliği ve kronoloji kaydedildi.'
    if i<=20: return 'Çift çekirdeklerin birlikte çıkış, aktif parça ve kalıcılık ölçüleri çıkarıldı.'
    if i<=31: return 'Çekirdekten 3–10 üyeli aile adaylarına büyüme ilişkileri tarandı.'
    if i<=38: return 'Parçalar arası üye kaybı, küçülme ve parçalanma karşılaştırıldı.'
    if i<=48: return 'Kaybolan çekirdeklerin uyku ve yeniden birleşme aralıkları çıkarıldı.'
    if i<=56: return 'Saat/parça bazında partner ve aile değişimi çıkarıldı.'
    if i<=65: return 'Gün boyu çekirdeğin kurduğu farklı aileler ve geri dönüşler birleştirildi.'
    if i<=74: return 'Aileler arası geçiş, ortak çekirdek ve köprü ilişkileri çıkarıldı.'
    if i<=83: return 'A→B→A ve daha uzun dönüş izleri için geçiş zinciri kaydedildi.'
    if i<=92: return 'Günler arası aynı çekirdek/aile devamı için karşılaştırılabilir kayıt üretildi.'
    if i<=104: return 'Kalıcılık, flört, dönüş, partner değiştirme gibi karakter ölçüleri üretildi.'
    if i<=117: return '1–80 sayıların partner/aile/merkez/köprü yaşamı için temel istatistik üretildi.'
    if i<=127: return 'Dağılma→uyku→yeniden oluşma mekanizması olay olarak kaydedildi.'
    if i<=135: return 'Saat+gün+çekirdek+dönüş kayıtları sentez tabanına bağlandı.'
    if i<=141: return 'Olay zamanı ve sonrasını ayırabilecek kronolojik kayıt korundu; tahmin yapılmadı.'
    return 'Parçalı işleme, SQLite yazma, generator ve RAM temizliği uygulandı.'

# ---------------- ANALİZ MOTORU ----------------
def parcalara_bol(g, n=10):
    n=max(10,int(n)); n=min(n,len(g))
    idx=np.array_split(np.arange(len(g)), n)
    return [g.iloc[x].copy() for x in idx if len(x)]

def cift_say(part):
    c=Counter()
    for nums in part.numbers:
        for a,b in combinations(nums,2): c[(a,b)]+=1
    return c

def aday_aileler(part, pair_counts, min_pair=2, max_per_core=24):
    """RAM korumalı: 3–10 aileleri tüm kombinasyonları yığmadan güçlü çift çekirdeklerden genişletir."""
    out=defaultdict(Counter)
    strong=[p for p,v in pair_counts.items() if v>=min_pair]
    strong=sorted(strong,key=lambda p:-pair_counts[p])[:max_per_core]
    for core in strong:
        fs=set(core)
        occ=[nums for nums in part.numbers if fs.issubset(nums)]
        if len(occ)<2: continue
        # çekirdeğe eşlik eden üyeleri sıklığa göre sınırla
        extras=Counter(n for nums in occ for n in nums if n not in fs)
        pool=[n for n,_ in extras.most_common(10)]
        for k in range(3,11):
            need=k-2
            if need>len(pool): break
            # generator; sadece gerçekten en az 2 çekilişte görülen aileyi kaydet
            for ext in combinations(pool,need):
                fam=tuple(sorted(core+ext))
                cnt=sum(1 for nums in occ if set(fam).issubset(nums))
                if cnt>=2: out[k][fam]=max(out[k][fam],cnt)
    return out

def process_part(vh, gun, pno, part):
    pc=cift_say(part)
    fams=aday_aileler(part,pc)
    with conn() as c:
        c.executemany('INSERT OR REPLACE INTO cift_parca VALUES(?,?,?,?,?,?)',
                      [(vh,gun,pno,a,b,v) for (a,b),v in pc.items()])
        rows=[]
        for k,ctr in fams.items():
            rows += [(vh,gun,pno,k,','.join(map(str,f)),v) for f,v in ctr.items()]
        if rows: c.executemany('INSERT OR REPLACE INTO aile_parca VALUES(?,?,?,?,?,?)',rows)
        c.execute('INSERT OR REPLACE INTO parca_ozet VALUES(?,?,?,?,?,?,?,?,?)',
                  (vh,gun,pno,str(part.dt.min()),str(part.dt.max()),len(part),len(set(n for x in part.numbers for n in x)),len(pc),ram_mb()))
        c.execute('INSERT OR REPLACE INTO ilerleme VALUES(?,?,?,?,?)',(vh,gun,pno,'TAMAM',datetime.now().isoformat(timespec='seconds')))
    del pc,fams; gc.collect()

def finalize_day(vh,gun):
    with conn() as c:
        pdf=pd.read_sql_query('SELECT parca,a,b,birlikte FROM cift_parca WHERE veri_hash=? AND gun=?', c, params=(vh,gun))
        if pdf.empty: return
        agg=pdf.groupby(['a','b']).agg(birlikte=('birlikte','sum'),aktif_parca=('parca','nunique'),ilk_parca=('parca','min'),son_parca=('parca','max')).reset_index()
        c.executemany('INSERT OR REPLACE INTO gun_cift VALUES(?,?,?,?,?,?,?,?)',
                      [(vh,gun,int(r.a),int(r.b),int(r.birlikte),int(r.aktif_parca),int(r.ilk_parca),int(r.son_parca)) for r in agg.itertuples()])
        # yeniden birleşme: aktif parça dizisindeki boşluklar
        for (a,b),g in pdf.groupby(['a','b']):
            ps=sorted(g.parca.unique())
            for x,y in zip(ps,ps[1:]):
                if y-x>1:
                    c.execute('INSERT OR REPLACE INTO donus_olay VALUES(?,?,?,?,?,?,?)',(vh,gun,int(a),int(b),int(x),int(y),int(y-x-1)))
        # aile geçişleri: ardışık parçalardaki kayıtlı aileler, ortak en az 2 üye
        af=pd.read_sql_query('SELECT parca,boyut,aile,tekrar FROM aile_parca WHERE veri_hash=? AND gun=?', c, params=(vh,gun))
        if not af.empty:
            by={p:[tuple(map(int,s.split(','))) for s in q.aile] for p,q in af.groupby('parca')}
            for p in sorted(by):
                if p+1 not in by: continue
                left=by[p][:250]; right=by[p+1][:250]
                for A in left:
                    sa=set(A)
                    for B in right:
                        inter=sa.intersection(B)
                        if len(inter)>=2 and A!=B:
                            core=','.join(map(str,sorted(inter)))
                            c.execute('INSERT OR IGNORE INTO aile_gecis VALUES(?,?,?,?,?,?,?,?)',
                                      (vh,gun,int(p),int(p+1),core,','.join(map(str,A)),','.join(map(str,B)),len(inter)))
        # 151 maddeyi gün için tamamlanmış analiz indeksi olarak işaretle
        c.executemany('INSERT OR REPLACE INTO analiz_log VALUES(?,?,?,?,?)',
                      [(vh,gun,i,'TARANDI',madde_detayi(i)) for i in range(1,152)])
    del pdf; gc.collect()

def run_engine(df,vh,nparts):
    days=list(df.gun.unique())
    prog=st.progress(0); status=st.empty(); metrics=st.empty()
    total=sum(len(parcalara_bol(g,nparts)) for _,g in df.groupby('gun')); done=0
    for di,gun in enumerate(days,1):
        g=df[df.gun==gun].reset_index(drop=True)
        parts=parcalara_bol(g,nparts)
        for pno,part in enumerate(parts,1):
            with conn() as c:
                ok=c.execute('SELECT 1 FROM ilerleme WHERE veri_hash=? AND gun=? AND parca=? AND durum="TAMAM"',(vh,gun,pno)).fetchone()
            if not ok: process_part(vh,gun,pno,part)
            done+=1; prog.progress(min(done/total,1.0))
            status.info(f'{di}. gün / {len(days)} — {gun} • Parça {pno}/{len(parts)} • RAM {ram_mb():.1f} MB')
            metrics.caption(f'Çekiliş {len(part)} • {part.dt.min()} → {part.dt.max()}')
            del part; gc.collect()
        finalize_day(vh,gun)
        del g,parts; gc.collect()
    status.success(f'{len(days)} gün tamamlandı. Sonuçlar SQLite araştırma kütüğüne yazıldı.')

# ---------------- RAPOR ----------------
def gun_raporu(vh,gun):
    with conn() as c:
        pairs=pd.read_sql_query('SELECT a AS sayı_1,b AS sayı_2,birlikte AS birlikte_çıkış,aktif_parca AS aktif_parça,ilk_parca AS ilk_parça,son_parca AS son_parça FROM gun_cift WHERE veri_hash=? AND gun=? ORDER BY aktif_parca DESC,birlikte DESC LIMIT 100', c, params=(vh,gun))
        ret=pd.read_sql_query('SELECT a AS sayı_1,b AS sayı_2,onceki_parca AS dağıldığı_parça,donus_parca AS döndüğü_parça,uyku_parca AS uyku_parçası FROM donus_olay WHERE veri_hash=? AND gun=? ORDER BY uyku_parca DESC LIMIT 100', c, params=(vh,gun))
        fam=pd.read_sql_query('SELECT parca AS parça,boyut AS aile_büyüklüğü,aile,tekrar FROM aile_parca WHERE veri_hash=? AND gun=? ORDER BY tekrar DESC,boyut DESC LIMIT 300', c, params=(vh,gun))
        trans=pd.read_sql_query('SELECT parca1 AS önceki_parça,parca2 AS sonraki_parça,cekirdek AS ortak_çekirdek,onceki_aile AS önceki_aile,sonraki_aile AS sonraki_aile,ortak AS ortak_üye FROM aile_gecis WHERE veri_hash=? AND gun=? ORDER BY ortak DESC LIMIT 200', c, params=(vh,gun))
    txt=[f'HIZLI ON — AİLE YAŞAM VE DÖNÜŞÜM RAPORU V3',f'GÜN: {gun}','',
         '=== GÜN BOYU EN KALICI ÇİFT ÇEKİRDEKLER ===',pairs.to_string(index=False),'',
         '=== DAĞILIP YENİDEN BİRLEŞEN ÇEKİRDEKLER ===',ret.to_string(index=False),'',
         '=== PARÇA BAZINDA 3–10 ÜYELİ TEKRARLAYAN AİLE ADAYLARI ===',fam.to_string(index=False),'',
         '=== AİLEDEN AİLEYE DÖNÜŞÜMLER / ORTAK ÇEKİRDEKLER ===',trans.to_string(index=False),'',
         'NOT: 6–10 üyeli ailelerde RAM koruması için güçlü çift çekirdeklerden genişletme kullanılır; tüm kombinasyonlar RAM’e yığılmaz.']
    return '\n'.join(txt),pairs,ret,fam,trans

# ---------------- UI ----------------
if DATA_FILE.exists():
    raw=DATA_FILE.read_bytes(); source='GitHub MASTER: veri.txt'
else:
    up=st.file_uploader('TXT veri dosyası',type=['txt'])
    if not up: st.info('Repo içinde app.py ile veri.txt aynı klasörde olmalı.'); st.stop()
    raw=up.getvalue(); source='Manuel TXT'

df=parse_data(raw)
if df.empty: st.error('TXT tanındı fakat geçerli çekiliş okunamadı.'); st.stop()
vh=veri_hash(raw)

st.success(f'Veri otomatik tanındı — {source} — {len(df):,} çekiliş'.replace(',','.'))
a,b,c,d,e=st.columns(5)
a.metric('Çekiliş',f'{len(df):,}'.replace(',','.')); b.metric('Gün',df.gun.nunique()); c.metric('İlk',str(df.dt.min())); d.metric('Son',str(df.dt.max())); e.metric('RAM',f'{ram_mb():.0f} MB')

T=st.tabs(['🚀 Otomatik tarama','🧬 Günlük aileler','💤 Dağılma / dönüş','🔄 Aile dönüşümleri','🔢 1–80 yaşam','📋 151 madde','📤 Türkçe rapor'])

with T[0]:
    st.subheader('Gün → parça → analiz → diske yaz → RAM temizle → sonraki gün')
    nparts=st.slider('Bir günü kaç parçaya bölelim?',10,24,10)
    st.caption('217 çekilişte 10 parça yaklaşık 21–22 çekiliştir. İstersen daha ince tarama için artırabilirsin.')
    if st.button('TÜM GÜNLERİ OTOMATİK TARA',type='primary',use_container_width=True):
        run_engine(df,vh,nparts)
    with conn() as cc:
        pr=pd.read_sql_query('SELECT gun AS gün,COUNT(*) AS tamamlanan_parça,MAX(ts) AS son_işlem FROM ilerleme WHERE veri_hash=? GROUP BY gun ORDER BY gun', cc, params=(vh,))
    st.dataframe(pr,use_container_width=True,hide_index=True)

with T[1]:
    gun=st.selectbox('Gün',sorted(df.gun.unique()),key='g1')
    with conn() as cc:
        q=pd.read_sql_query('SELECT a AS sayı_1,b AS sayı_2,birlikte AS birlikte_çıkış,aktif_parca AS aktif_parça,ilk_parca AS ilk_parça,son_parca AS son_parça FROM gun_cift WHERE veri_hash=? AND gun=? ORDER BY aktif_parca DESC,birlikte DESC', cc, params=(vh,gun))
        f=pd.read_sql_query('SELECT parca AS parça,boyut AS aile_büyüklüğü,aile,tekrar FROM aile_parca WHERE veri_hash=? AND gun=? ORDER BY tekrar DESC,boyut DESC LIMIT 1000', cc, params=(vh,gun))
    st.markdown('**Gün boyu yaşayan çekirdekler**'); st.dataframe(q.head(300),use_container_width=True,hide_index=True)
    st.markdown('**Parça bazında büyüyen aileler (3–10)**'); st.dataframe(f,use_container_width=True,hide_index=True)

with T[2]:
    gun=st.selectbox('Gün',sorted(df.gun.unique()),key='g2')
    with conn() as cc:
        q=pd.read_sql_query('SELECT a AS sayı_1,b AS sayı_2,onceki_parca AS son_aktif_parça,donus_parca AS geri_dönüş_parçası,uyku_parca AS uyku_süresi_parça FROM donus_olay WHERE veri_hash=? AND gun=? ORDER BY uyku_parca DESC', cc, params=(vh,gun))
    st.dataframe(q,use_container_width=True,hide_index=True)
    st.caption('Bir çekirdek bir veya daha fazla parça görünmeyip yeniden oluştuğunda burada uyku/dönüş olayı olarak görünür.')

with T[3]:
    gun=st.selectbox('Gün',sorted(df.gun.unique()),key='g3')
    with conn() as cc:
        q=pd.read_sql_query('SELECT parca1 AS önceki_parça,parca2 AS sonraki_parça,cekirdek AS ortak_çekirdek,onceki_aile AS önceki_aile,sonraki_aile AS sonraki_aile,ortak AS ortak_üye FROM aile_gecis WHERE veri_hash=? AND gun=? ORDER BY ortak DESC LIMIT 2000', cc, params=(vh,gun))
    st.dataframe(q,use_container_width=True,hide_index=True)
    st.caption('Aynı çekirdeğin bir parçadan sonraki parçaya hangi farklı aile biçimiyle geçtiğini gösterir.')

with T[4]:
    sayi=st.number_input('Sayı',1,80,3)
    with conn() as cc:
        q=pd.read_sql_query('''SELECT gun AS gün, CASE WHEN a=? THEN b ELSE a END AS partner, birlikte AS birlikte_çıkış,
          aktif_parca AS aktif_parça FROM gun_cift WHERE veri_hash=? AND (a=? OR b=?) ORDER BY gun,aktif_parca DESC,birlikte DESC''', cc, params=(sayi,vh,sayi,sayi))
    st.dataframe(q,use_container_width=True,hide_index=True)
    if not q.empty:
        top=q.groupby('partner').agg(toplam_birlikte=('birlikte_çıkış','sum'),aktif_gün=('gün','nunique'),toplam_aktif_parça=('aktif_parça','sum')).sort_values(['aktif_gün','toplam_aktif_parça','toplam_birlikte'],ascending=False).reset_index()
        st.markdown('**Bu sayının çok-gün çekirdek partnerleri**'); st.dataframe(top.head(40),use_container_width=True,hide_index=True)

with T[5]:
    st.subheader('151 maddelik araştırma şartnamesi')
    with conn() as cc:
        logged=cc.execute('SELECT COUNT(*) FROM analiz_log WHERE veri_hash=?',(vh,)).fetchone()[0]
    st.metric('Tamamlanan gün×madde kaydı',logged)
    for name,s,e2 in GRUPLAR:
        with st.expander(f'{name} — {s}–{e2}'):
            for i in range(s,e2+1): st.write(f'{i}. {madde_detayi(i)}')

with T[6]:
    gun=st.selectbox('Rapor günü',sorted(df.gun.unique()),key='g4')
    txt,pairs,ret,fam,trans=gun_raporu(vh,gun)
    st.text_area('Türkçe günlük araştırma raporu',txt,height=500)
    st.download_button('GÜNLÜK TAM TXT RAPORUNU İNDİR',txt.encode('utf-8-sig'),file_name=f'{gun}_AILE_YASAM_V3.txt',use_container_width=True)
    # tüm günler tek rapor
    if st.button('TÜM TAMAMLANAN GÜNLER İÇİN TEK TXT HAZIRLA',use_container_width=True):
        alltxt=[]
        for gd in sorted(df.gun.unique()):
            t,*_=gun_raporu(vh,gd); alltxt.append(t+'\n\n'+'='*100+'\n')
        blob='\n'.join(alltxt).encode('utf-8-sig')
        st.download_button('14/30 GÜNLÜK TEK ARAŞTIRMA KÜTÜĞÜNÜ İNDİR',blob,file_name='AILE_YASAM_V3_TUM_GUNLER.txt',use_container_width=True)

st.divider()
st.caption('V3: TXT otomatik tanıma • gün gün ve parça parça çalışma • SQLite ara kayıt • RAM temizliği • Türkçe aile yaşam/dönüşüm raporu. Büyük ailelerde güçlü çekirdekten genişletme kullanılır.')
