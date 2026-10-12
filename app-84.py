# -*- coding: utf-8 -*-
"""Hizli On V7 Streamlit: incremental resumable analysis for mobile."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
import io,zipfile,shutil,sqlite3,json
import pandas as pd
import requests
import streamlit as st
from motor import (SIZES,parse,serialize,data_quality,byday,pos_time,initialize,step_job,
                   hash_settings,status,to_frame,live_exact,performance,structure_statistics,
                   verify_structural,structural_live,bundle_reports,connect)

st.set_page_config(page_title='Hızlı On V7.1 | Mobil Ritim',page_icon='🎯',layout='wide',initial_sidebar_state='collapsed')
st.markdown("""<style>
@media (max-width: 700px) {
 .block-container {padding-top:0.9rem !important;padding-left:0.8rem !important;padding-right:0.8rem !important;}
 h1 {font-size:1.55rem !important;line-height:1.2 !important;}
 h2 {font-size:1.3rem !important;}
 [data-testid="stMetricValue"] {font-size:1.25rem !important;}
 [data-testid="stHorizontalBlock"] {gap:0.4rem !important;}
}
</style>""", unsafe_allow_html=True)
st.title('🎯 Hızlı On V7.1')
st.caption("5–10’lu aileler · gün ve saat ritimleri · 1→2→3 görünüş · kör isabet testi")
st.caption('Geçmiş ritim, gelecekte %100 isabet garantisi değildir. Onaylanmayan sinyaller kupon sayılmaz.')
RAW='https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt'
TR_NOW=(datetime.now(timezone.utc)+timedelta(hours=3)).date()
WORKDIR=Path('.hizli_on_v7_jobs')

@st.cache_data(ttl=90,show_spinner=False)
def fetch_url(url,nonce):
    r=requests.get(url,timeout=25,headers={'Cache-Control':'no-cache','Pragma':'no-cache'});r.raise_for_status();return r.text

@st.cache_data(show_spinner=False)
def parse_cached(txt): return parse(txt)

@st.cache_data(show_spinner=False)
def structure_cached(txt,cut,maxgap,target):
    draws,_=parse_cached(txt)
    # Do not use the target day's realized results when validating today's signals.
    past=[r for r in draws if r.day<target]
    result=structure_statistics(past,date.fromisoformat(cut),maxgap)
    return verify_structural(result)


def show(df,limit=200,height=450):
    if df is None or df.empty:
        st.caption('Bu koşullarda kayıt bulunamadı. 0 sonuç da geçerli sonuçtur.')
    else:
        st.dataframe(df.head(limit),use_container_width=True,hide_index=True,height=min(height,44+36*(min(limit,len(df))+1)))
        if len(df)>limit:st.caption(f'{limit}/{len(df)} satır gösteriliyor; tamamı indirilen raporda.')

# Telefon için yan menü yerine tek sayfalık, kolay anlaşılır kontrol alanı.
# Hazır modlar küçük işlem bloklarıyla çalışır. Değerler yalnızca "Özel" seçilirse değişir.
st.markdown('### 🧭 Analiz ayarları')
scan_mode=st.radio('Nasıl tarayalım?', ['Hızlı', 'Dengeli (önerilen)', 'Derin'],
                   index=1, horizontal=True, help='Dengeli: kapsamlı ve telefon için daha kontrollü işlem.')
presets={
    'Hızlı': (7,12,80,2),
    'Dengeli (önerilen)': (16,24,160,2),
    'Derin': (16,36,240,1),
}
holdout,maxgap,maxfam,batch=presets[scan_mode]
target=st.date_input('Hedef gün',TR_NOW)
with st.expander('⚙️ İleri ayarlar (istersen değiştir)', expanded=False):
    custom=st.checkbox('Hazır değerler yerine kendim ayarlayayım',value=False,key='v71_custom')
    if custom:
        holdout=st.slider('Kör test: son kaç gün?',5,16,holdout)
        maxgap=st.slider('Gün içi aralık (çekiliş)',6,36,maxgap,step=6)
        maxfam=st.slider('Boyut başına yeni aile',40,400,maxfam,step=40)
        batch=st.slider('Tek işlemde kaç gün?',1,4,batch)
    st.caption('Kör test: geçmişi öğrenmeden yapılan sınama. Aralık: 1. ve 2. görünüş arasında araştırılan en büyük çekiliş farkı.')
    st.caption('Aile limiti çok büyürse işlem uzar. Gün sayısını küçük tutmak daha güvenli ilerleme sağlar.')
with st.expander('📁 Veri ekle veya yedekten devam et (isteğe bağlı)', expanded=False):
    url=st.text_input('GitHub veri.txt bağlantısı',RAW)
    uploaded=st.file_uploader('Ek çekiliş TXT dosyaları',type=['txt'],accept_multiple_files=True)
    paste=st.text_area('Canlı çekilişleri buraya da yapıştırabilirsin',height=90,
                       placeholder='61674;12.10.2026 09:42;1,2,... (20 sayı)')
    old_backup=st.file_uploader('İlerleme yedeği (checkpoint ZIP)',type=['zip'],key='v7_restore')
    if st.button('🔄 GitHub önbelleğini temizle'):
        fetch_url.clear();st.rerun()
st.caption(f'**{scan_mode}:** {holdout} gün kör test · en fazla {maxgap} çekiliş aralığı · '
           f'{maxfam} yeni aile / boyut · {batch} gün / işlem')
start=st.button('🚀 VERİYİ AL VE ANALİZİ BAŞLAT',type='primary',use_container_width=True)

if start:
    try:base=fetch_url(url,str(TR_NOW))
    except Exception as e:
        base='';st.warning(f'GitHub okunamadı: {e}. Yüklenen/yapıştırılan veri kullanılacak.')
    parts=[base]
    for file in uploaded or []:
        data=file.getvalue()
        try:parts.append(data.decode('utf-8-sig'))
        except UnicodeDecodeError:parts.append(data.decode('cp1254',errors='replace'))
    if paste.strip():parts.append(paste)
    draws,issues=parse_cached('\n'.join(parts))
    if issues['celiski']:
        st.error('Veride çelişen çekilişler var, analiz durduruldu: '+'; '.join(issues['celiski'][:5]));st.stop()
    if draws and target<draws[-1].day:
        draws=[r for r in draws if r.day<=target]
        st.warning('Geçmiş hedef gün seçildi. Sonraki günlerin verisi analizden çıkarıldı; ileriye bakma hatası önlendi.')
    days=byday(draws)
    if len(days)<12:
        st.error(f'Yeterli gün yok: {len(days)}. Kör test için en az 12 gün ve geçerli 20 sayılı çekiliş gerekli.');st.stop()
    options={'holdout':holdout,'gap':maxgap,'per_size':maxfam}
    txt=serialize(draws);key=hash_settings(draws,options)
    path=WORKDIR/f'ritim_v7_{key}.sqlite'
    if old_backup is not None:
        raw=old_backup.getvalue()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if not {'checkpoint.sqlite','settings.json'}.issubset(z.namelist()):raise ValueError('V7 yedek biçimi değil')
                info=json.loads(z.read('settings.json'))
                if info.get('key')!=key:raise ValueError('Yedek, bu veri ve ayarlarla aynı değil')
                stat=z.getinfo('checkpoint.sqlite')
                if stat.file_size>250*1024*1024:raise ValueError('Yedek çok büyük')
                path.parent.mkdir(parents=True,exist_ok=True)
                for suffix in ('-wal','-shm'):
                    Path(str(path)+suffix).unlink(missing_ok=True)
                path.write_bytes(z.read('checkpoint.sqlite'))
                conn=sqlite3.connect(path)
                if conn.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Bozuk SQLite veritabanı')
                conn.close()
            st.success('İşlem yedeği aynı veriye geri yüklendi.')
        except Exception as e:
            st.error('Yedek yüklenemedi: '+str(e));st.stop()
    initialize(path,draws,holdout,maxfam,maxgap)
    st.session_state['v7_job']={'text':txt,'path':str(path),'key':key,'options':options,'target':target.isoformat(),'issues':issues}
    st.session_state['v7_auto']=False
    st.session_state.pop('v7_structure',None)
    st.session_state.pop('v7_backup',None)
    st.rerun()

job=st.session_state.get('v7_job')
if job:
    stored_target=date.fromisoformat(job['target'])
    changed=(target!=stored_target or {'holdout':holdout,'gap':maxgap,'per_size':maxfam}!=job['options'])
    if changed:
        st.warning('Hedef gün veya tarama ayarları değişti. Bunları kullanmak için “VERİYİ AL VE ANALİZİ BAŞLAT” düğmesine bas. Mevcut rapor eski sabit ayarlarla gösteriliyor.')
        target=stored_target

if not job:
    st.markdown('**Başlamak için** **“VERİYİ AL VE ANALİZİ BAŞLAT”** düğmesine dokun. `veri.txt` GitHub’dan okunur; burada yeni dosya yüklemek zorunlu değil.')
    st.markdown('Analiz, her işlem adımını kendi veritabanına kaydeder. Uygulama açıkken **otomatik devam** edebilir veya sen her adımı elle başlatabilirsin. Sunucu yeniden başlarsa indirilen yedeği yeniden yüklemek gerekebilir.')
    st.stop()

opts=job['options'];path=job['path'];txt=job['text']
draws,issues=parse_cached(txt)
q=data_quality(draws)
cut=initialize(path,draws,opts['holdout'],opts['per_size'],opts['gap'])
stg=status(path)
all_days=sorted(byday(draws))
train_days=sum(d<cut for d in all_days)
meta_stage=stg.get('stage','mine')
name_stage={'mine':'1/2 · Aile keşfi','profile':'2/2 · Aile ve üçlü doğrulama','ready':'TAMAMLANDI'}
c1,c2,c3,c4=st.columns(4)
c1.metric('Geçerli çekiliş',f'{len(draws):,}'.replace(',','.'))
c2.metric('Analiz günü',len(all_days))
c3.metric('Bulunan aday',int(stg.get('candidate_count',0)))
c4.metric('Aile profili',int(stg.get('profile_count',0)))
st.write(f"**Aşama:** {name_stage.get(meta_stage,meta_stage)} · **Eğitim/test sınırı:** {cut:%d.%m.%Y} · **Son kayıt:** {draws[-1].dt:%d.%m.%Y %H:%M}")
if issues.get('gecersiz'):st.caption(f"Atlanan geçersiz satır: {issues['gecersiz']}")
if meta_stage=='mine':
    st.progress(min(1,int(stg.get('mine_pos',0))/max(1,train_days)))
    st.caption(f"İşlenen eğitim günü: {stg.get('mine_pos',0)} / {train_days}")
elif_stage=meta_stage=='profile'
if elif_stage:
    st.progress(min(1,int(stg.get('profile_pos',0))/max(1,int(stg.get('selected_count',1)))))
    st.caption(f"İşlenen aile: {stg.get('profile_pos',0)} / {stg.get('selected_count',0)}")

if meta_stage!='ready':
    st.session_state.setdefault('v7_auto',False)
    st.toggle('▶ Otomatik devam et (ekran açıkken parça parça)',key='v7_auto')
    if st.button('⏩ Sonraki parçayı işle',type='primary'):
        try:
            with st.spinner('Küçük bölüm işleniyor; önceki ilerleme silinmez…'):
                step_job(path,draws,opts,batch=batch)
            st.rerun()
        except (sqlite3.Error,ValueError,RuntimeError) as e:
            st.error('İşlem kesildi; son başarılı bölüm saklandı. Tekrar deneyebilirsin: '+str(e))
    @st.fragment(run_every='3s')
    def advance():
        if st.session_state.get('v7_auto',False):
            try:
                with st.spinner('Otomatik küçük parça analiz ediliyor…'):
                    res=step_job(path,draws,opts,batch=min(batch,3))
                st.write(f"Kaydedildi · {name_stage.get(res['stage'],res['stage'])} · gün {res.get('mine_pos')} · aile {res.get('profile_pos')}")
                if res['stage']=='ready':
                    st.session_state['v7_completed']=True
                    st.rerun()
            except (sqlite3.Error,ValueError,RuntimeError) as e:
                st.error('Otomatik işlem bu adımda durdu. Son ilerleme saklı: '+str(e))
                st.caption('Otomatik devam düğmesini kapatıp elle devam etmeyi deneyebilirsin.')
        else:
            st.caption('Otomatik işlem kapalı; elle devam edebilirsin.')
    advance()
    with st.expander('Kaldığın yerden devam ve güvenlik'):
        if st.button('💾 Şu anki ilerleme yedeğini hazırla'):
            b=io.BytesIO()
            source=connect(path);tmp=sqlite3.connect(':memory:');source.backup(tmp)
            dst=WORKDIR/'backup_snapshot.sqlite';snapshot=sqlite3.connect(dst)
            tmp.backup(snapshot);snapshot.close();tmp.close();source.close()
            with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
                z.write(dst,'checkpoint.sqlite')
                z.writestr('settings.json',json.dumps({'key':job['key']},ensure_ascii=False))
            st.session_state['v7_backup']=b.getvalue()
        if st.session_state.get('v7_backup'):
            st.download_button('⬇️ İLERLEME YEDEĞİNİ İNDİR',st.session_state['v7_backup'],
                               'HIZLI_ON_V7_CHECKPOINT.zip',mime='application/zip')
        st.write('Aynı veri ve ayarlarla uygulamayı yeniden açtığında kaydedilmiş ilerlemeden devam eder. Streamlit Cloud yerel diski sunucu yeniden kurulunca silinebilir. ZIP raporunu ve varsa veritabanı yedeğini indir.')
    st.stop()

# Completed: all views read-only, no expensive mining on each page refresh.
profiles=to_frame(path,'profile')
selected=to_frame(path,'selected')
rhythms=to_frame(path,'rhythm')
triple=to_frame(path,'triples')
hits=to_frame(path,'hits')
exact=to_frame(path,'predictions')
hits=hits.sort_values(['k','fam','day','pos']).copy()
if not hits.empty:
    hits['Gün içi görünüş no']=hits.groupby(['k','fam','day']).cumcount()+1
    hits['Genel görünüş no']=hits.groupby(['k','fam']).cumcount()+1
    hits['Saat']=hits.pos.map(pos_time)
    hits['Saat bandı']=hits['Saat'].str[:2]
    hourly=hits.groupby(['day','Saat bandı','k']).agg(
        **{'Tam aile görünüşü':('fam','size'),'Farklı aile':('fam','nunique')}).reset_index()
else:
    hourly=pd.DataFrame(columns=['day','Saat bandı','k','Tam aile görünüşü','Farklı aile'])
timeline=pd.DataFrame([{'Tarih':str(r.day),'Saat':pos_time(r.pos),'Günlük sıra':r.pos,
                        'Çekiliş no':r.id,'20 sayı':','.join(map(str,r.nums))} for r in draws])
if not hits.empty:
    count_by=hits.groupby(['day','pos','k']).size().unstack(fill_value=0).reset_index()
    count_by.columns=['Tarih','Günlük sıra']+[f'{col}lı aile' for col in count_by.columns[2:]]
    timeline=timeline.merge(count_by,on=['Tarih','Günlük sıra'],how='left')
    for k in SIZES:
        c=f'{k}lı aile'
        if c not in timeline.columns:timeline[c]=0
    timeline[[f'{k}lı aile' for k in SIZES]]=timeline[[f'{k}lı aile' for k in SIZES]].fillna(0).astype(int)
limit_day=target if isinstance(target,date) else date.fromisoformat(str(target))
asof=max([r.pos for r in draws if r.day==limit_day],default=0)
if len([r for r in draws if r.day==limit_day])>=180:
    st.caption('Hedef günün çok sayıda çekilişi kaydedilmiş olabilir; gelecekteki hedef ancak en son veri sonrasına üretilebilir.')

st.success('Aile taraması tamamlandı; kayıtlar hazır. Alt sekmeleri açmak yeniden 70 günlük analizi çalıştırmaz.')
with st.expander('Hedef pencere ayarı',expanded=False):
    horizon=st.slider('Kaç sonraki çekiliş için aday gösterilsin?',1,36,12)
    manual_asof=st.slider('Gün içi bilinen son çekiliş sırası',0,217,asof)
    st.caption('Geriye dönük canlı simülasyonda 1. ve 2. gelişler yalnızca seçilen sıraya kadar okunur. Ancak bu ekrandaki tarihsel puanlar geriye dönük canlı doğrulaması yerine geçmez.')
else_horizon=locals().get('horizon',12)
else_asof=locals().get('manual_asof',asof)
live=live_exact(draws,path,limit_day,else_asof,else_horizon)
perf=performance(exact)

# Structural analysis is an optional single additional pass; cached for this exact data/time split.
if st.button('🧪 Rakam değişimli kör testini hesapla (bir defa)'):
    with st.spinner('Geçmiş 1→2→3 çiftleri eğitim ve test olarak ayrı sayılıyor…'):
        st.session_state['v7_structure']=structure_cached(txt,cut.isoformat(),opts['gap'],limit_day)
struc=st.session_state.get('v7_structure')
if struc is None:struct_live=pd.DataFrame()
else:struct_live=structural_live(draws,limit_day,else_asof,struc,opts['gap'],else_horizon)

c1,c2,c3,c4=st.columns(4)
c1.metric('Seçilen aile',len(profiles))
c2.metric('Gün içinde 3 görünüş',int(profiles['anyday3'].sum()) if not profiles.empty else 0)
c3.metric('Sabit aralıklı üçlü',int(profiles['sameday3'].sum()) if not profiles.empty else 0)
c4.metric('Önceden hedeflenip tam gelen',int((exact['hit']==exact['k']).sum()) if not exact.empty else 0)

T=st.tabs(['📊 Özet','5️⃣ Beşli','6️⃣ Altılı','7️⃣ Yedili','8️⃣ Sekizli','9️⃣ Dokuzlu','🔟 Onlu','🔗 Üçlü ritimler','🧪 Kör isabet','🎯 Hedef kupon','📦 Tek ZIP'])
with T[0]:
    st.subheader('Veri bütünlüğü ve motorların sonuçları')
    show(q.tail(80),80)
    st.markdown('**Çekiliş çekiliş: tam aile eşleşme sayıları**')
    show(timeline.tail(120).iloc[::-1],120)
    st.markdown('**Gün / saat / aile boyutu görünüş tablosu**')
    show(hourly.tail(150).iloc[::-1],150)
    summary=[]
    for k in SIZES:
        p=profiles[profiles.k==k]
        summary.append({'Boyut':k,'Bulunan aile':len(p),'Aynı gün 3 gelişi':int(p['anyday3'].sum()),
                        'Eşit gap üçlüsü':int(p['sameday3'].sum()),'Günler arası 3 gün ritmi':int(p['crossday3'].sum()),
                        'Kör hedef':int((exact.k==k).sum()),'Kör tam isabet':int(((exact.k==k)&(exact.hit==k)).sum())})
    overview=pd.DataFrame(summary)
    show(overview,10)
    st.caption('Bu sayılar birbirine eklenerek bağımsız olay sayısı kabul edilmez: tek aile birden çok örtüşen zincir oluşturabilir. Aile keşfi bütçeli olup tüm C(20,k) kombinasyonları eksiksiz saymaz.')

for index,k in enumerate(SIZES):
    with T[index+1]:
        p=profiles[profiles.k==k].copy()
        st.subheader(f'{k}’lı aileler — kendi başına analiz')
        if p.empty:
            st.warning(f'{k}’lı boyutta bu tarama bütçesiyle doğrulanmış aile kaydı bulunamadı. Bu, bütün olası {k}’lıların hiç tekrarlanmadığı anlamına gelmez.')
        else:
            pp=p.merge(selected[selected.k==k][['fam','src']],on='fam',how='left')
            show(pp.sort_values(['sameday3','crossday3','occ'],ascending=False),200)
            st.markdown('**En düzenli üçlü ritimler (aynı aile)**')
            rr=rhythms[(rhythms.k==k)&(rhythms.train3>0)].sort_values(['train3','all3'],ascending=False)
            show(rr,150)
            st.markdown('**Bugün için önceden hedef kaydı**')
            show(live[live.Boyut==k],50)

with T[7]:
    st.subheader('Gerçek 1. → 2. → 3. görünüş ayrıntıları')
    st.markdown('**Gün içinde üç geliş:** Tek bir ailenin 3 kere çıkması ile iki aralığın eşit olması ayrı sütunlardır.')
    tr=triple.sort_values(['equal','day','k'],ascending=[False,False,True]) if not triple.empty else triple
    show(tr,250)
    st.markdown('**Farklı günlerde aynı ritim:**')
    show(rhythms[(rhythms['mode']=='gün')&(rhythms['all3']>0)].sort_values(['train3','all3'],ascending=False),200)
    st.caption('Günler arası üçlü, o ailenin üç farklı aktif gününün eşit takvim aralığı oluşturmasıdır. Aynı saat/sırada tam tekrar ayrıca zorunlu değildir; zaman tutarlılığı ikinci bir test gerektirir.')

with T[8]:
    st.subheader('Aile bazında, tahmin yapıldıktan sonra ölçülen isabet')
    show(perf,10)
    st.markdown('**Gerçek kör hedefler (tahminin 1. ve 2. çekilişi hedeften öncedir):**')
    show(exact.sort_values(['day','pos'],ascending=[False,False]),220)
    if struc is not None:
        st.subheader('Rakam değişimli üçlü araştırması: eğitim / bağımsız test')
        show(struc,260)
        st.caption('3. devam ölçütü: ikinci ve üçüncü çekilişte >=k ortak sayı. Tam kupon ölçütü ayrı verilir. Eğitimde iyi görünen sonuç yalnız kör testten geçerse aday sayılır. İstatistiksel test sonuçları çakışan üçlüler nedeniyle kesin bağımsız kanıt değildir.')
    else:st.info('Rakam değişimli üçüncü geliş testini görmek için üstteki “Rakam değişimli kör testini hesapla” düğmesine bas.')

with T[9]:
    st.subheader('Yeni gün, yeni saat: 3. hedef çekilişi')
    st.markdown('**Gerçek tam aile adayları — eğitimde daha önce en az 2 eşit ritimli üçlü:**')
    show(live,160)
    st.markdown('**Rakam değişimli, bağımsız test filtresini geçen adaylar:**')
    show(struct_live,160)
    # Exact signals need independent out-of-sample performance; positive samples on other days not enough for 100% guarantee.
    st.warning('**Kesin (%100) kupon: 0.** Tekrarlayan ritim veya önceki tam isabet, gelecek çekilişte aynı aileyi garanti etmez. Yukarıdaki satırlar yalnız önceden planlanabilir araştırma hedefidir; kabul edilmiş kupon sayısı performans kanıtı gerektirir.')
    if live.empty and struct_live.empty:st.success('Bu hedef gün ve pencere için doğrulanabilir sinyal bulunmadı → 0 kupon.')

with T[10]:
    st.subheader('Tüm detayları tek ZIP indir')
    table={'01_VERI_KALITESI.csv':q,'02_BOYUT_OZETI.csv':overview,'03_TUM_AILELER.csv':profiles,
           '04_RITIM_GAP_GUN_CEKILIS.csv':rhythms,'05_3_KEZ_GELENLER.csv':triple,
           '06_AILE_VURUS_SAAT_SIRA.csv':hits,'07_KOR_HEDEF_ISABET.csv':exact,
           '08_BOYUT_ISABET_0_K.csv':perf,'09_CANLI_TAM_AILE_ADAY.csv':live,
           '10_RAKAM_DEGISIMLI_KOR_TEST.csv':struc if struc is not None else pd.DataFrame(),
           '11_RAKAM_DEGISIMLI_CANLI_ADAY.csv':struct_live,
           '15_HER_CEKILIS_AILE_GORUNUS.csv':timeline,'16_GUN_SAAT_BOYUT_OZET.csv':hourly}
    note=f'''HIZLI ON V7 — ARAŞTIRMA NOTLARI\nVeri: {len(draws)} çekiliş; aralık {draws[0].dt} – {draws[-1].dt}.\nEğitim/test ayrımı: {cut}. Yeni ailelerin otomatik keşfi yalnız eğitim döneminde.\nHer boyut 5/6/7/8/9/10 ayrı incelenir. 1→2→3 tam aile, aynı sayıların 3 ayrı çekilişte görünmesidir.\nGün içinde 3 kere çıkan aile, iki gap eşit olmasa da sayılır; eşit aralıklı ritim ayrıca sınıflandırılır.\nGünler-arası ardışık aktif günleri eşit gap olan üçlüler ayrı sınıftır.\nKör tahminde eğitim öncesi sonuçlar gelecek kuponu seçmek için kullanılmaz.\nCanlı sonuçlar gün içinde yalnız son bilinen sıradan sonraki pencerelere üretilir.\nHızlı On 1–80 arası 20 sayıdan oluşur: rastgele k sayılık kuponun ortalama tutanı k/4'tür.\nGeçmişte %100 sıklık ≠ gelecekte %100 isabet; geçmiş ritim gelecek olasılığını garanti etmez.\nSaat ile gün içi sıra bağımsız iki kanıt değildir.\nVeri eksik/hatalı olabilir; kalite tablosundaki eksik slotları incele.\nAday keşfi bütçelidir: 20 sayıdan C(20,k) tüm alt kümeler eksiksiz taranmamıştır. 9/10 bulamamak yokluk kanıtı değildir.\nRakam değişimli olay, tam aynı aile tekrarı değildir.\nÇoklu test düzeltmesi Bonferroni'dir; ilişkili çekilişler nedeniyle sonuçlar ihtiyatla yorumlanmalıdır.\nKullanıcı her yeni TXT güncellemesinde yeni veri hash’iyle ayrı tarama başlatabilir.\nBu ürün kumar sonucu garanti edemez.\n'''
    for k in SIZES:
        table[f'12_{k}LI_AYRI_AILE_ANALIZI.csv']=profiles[profiles.k==k]
        table[f'13_{k}LI_AYRI_GAP_RITIMLERI.csv']=rhythms[rhythms.k==k]
        table[f'14_{k}LI_AYRI_KOR_HEDEFLER.csv']=exact[exact.k==k]
    data=bundle_reports(table,note)
    st.download_button('⬇️ TÜM RAPORLAR · TEK ZIP',data=data,file_name='HIZLI_ON_V7_TUM_DETAYLI_RAPORLAR.zip',mime='application/zip',type='primary')
    st.download_button('⬇️ Temizlenmiş birleştirilmiş veri.txt',data=txt.encode('utf-8'),file_name='veri_V7_temiz.txt',mime='text/plain')
    st.caption('İlerleme, aynı veri hash’i için yerel SQLite veritabanına yazıldı. Streamlit Cloud yeniden kurulursa yerel veriler kaybolabileceğinden ZIP raporunu mutlaka indir.')

st.caption('V7 · Gözlemlenen örüntü ile ileriye dönük isabet kanıtı farklıdır. Araştırma aracı; kazanç veya kesin tahmin garantisi yoktur.')
