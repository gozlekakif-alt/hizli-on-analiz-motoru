from pathlib import Path
import os
from urllib.request import Request, urlopen
import pandas as pd
import streamlit as st
from motor import parse_data, analyse, make_zip

st.set_page_config(page_title='Hızlı On | 14 Gün Yaşam Laboratuvarı', layout='wide')
st.title('Hızlı On — 14 Gün Yaşam Laboratuvarı')
st.caption('00:02’den hedef çekilişe 80 sayı; ilk 3 el kohortları; 4–8+ geçişleri; çekiliş öncesi kronolojik kıyas. Gelecek sonucu önceden kullanmaz.')
root=Path(__file__).resolve().parent
url=''
try: url=st.secrets.get('GITHUB_RAW_URL','')
except Exception: pass
url=url or os.getenv('GITHUB_RAW_URL','')
@st.cache_data(ttl=300,show_spinner=False)
def get_raw(link):
    if not (link.startswith('https://raw.githubusercontent.com/') or link.startswith('https://github.com/')):
        raise ValueError('Yalnız GitHub bağlantısı destekleniyor')
    if link.startswith('https://github.com/'):
        link=link.replace('https://github.com/','https://raw.githubusercontent.com/',1).replace('/blob/','/')
    with urlopen(Request(link,headers={'User-Agent':'HizliOn-Research'}),timeout=20) as r:
        data=r.read(25_000_001)
    if len(data)>25_000_000: raise ValueError('25 MB sınırı aşıldı')
    return data
if (root/'veri.txt').is_file():
    raw=(root/'veri.txt').read_bytes(); source='GitHub deposundaki veri.txt'
elif url:
    try: raw=get_raw(url); source='GitHub raw bağlantısı'
    except Exception as e: st.error(f'GitHub veri okuma hatası: {e}'); st.stop()
else:
    st.error('veri.txt bulunamadı. app.py, motor.py ve veri.txt aynı klasörde olmalı.'); st.stop()
try: df=parse_data(raw)
except Exception as e: st.error(f'Veri ayrıştırma hatası: {e}'); st.stop()
@st.cache_data(show_spinner=False)
def run(data): return analyse(parse_data(data))
with st.spinner('14 gün kronolojik işleniyor...'):
    try: result=run(raw)
    except Exception as e: st.error(f'Motor hatası: {e}'); st.stop()
st.info(f'Kaynak: {source} | {len(df):,} çekiliş | {df.draw_time.dt.date.nunique()} gün')
if result['uyarilar']: st.warning('Veri denetimi: '+'; '.join(result['uyarilar']))
else: st.success('Gün ve saat bütünlüğü kontrol edildi.')
a,b,c=st.columns(3)
a.metric('Gün',len(result['gun_ozeti']))
b.metric('Saat × 80 sayı',len(result['saat_80_yasam']))
c.metric('Çekiliş öncesi sayı kaydı',len(result['cekilis_80_oncesi']))

summary, daily, cohorts, paths, thresholds, forward, export=st.tabs([
    '14 gün özet','Gün ve hedef çekiliş','İlk 3 el → 4–8+','80 sayının yaşamı','Eşik geçişleri','Kronolojik kıyas','Tek ZIP indir'])
with summary:
    st.subheader('14 gün: ilk üç elden saat sonuna geçiş')
    st.dataframe(result['ilk3_esik_ozeti'],hide_index=True,use_container_width=True)
    st.subheader('Gün gün denetim ve kıyas')
    st.dataframe(result['gun_ozeti'],hide_index=True,use_container_width=True)
    st.caption('Saat sonu eşik sonuçları geriye dönük gözlemdir; öngörü başarısı değildir.')

all_pre=result['cekilis_80_oncesi']
all_hours=result['saat_80_yasam']
all_paths=result['gun_80_yasam_yolu']
all_thresholds=result['gun_esik_gecisleri']
dates=result['gun_ozeti']['tarih'].tolist()
with daily:
    st.subheader('00:02 → hedef çekiliş: 80 sayının geçmişi')
    day=st.selectbox('Gün',dates,key='daily_day')
    daydraws=df[df.draw_time.dt.strftime('%Y-%m-%d')==day].sort_values('draw_time')
    draw_options={f"{r.draw_time:%H:%M} — #{r.draw_id}":int(r.draw_id) for r in daydraws.itertuples()}
    target=st.selectbox('Hedef çekiliş (önceki durum gösterilir)',list(draw_options),key='target')
    target_id=draw_options[target]
    state=all_pre[(all_pre.tarih==day)&(all_pre.cekilis==target_id)].copy()
    if state.empty:
        st.warning('01:02 köprü çekilişi için saatlik 80 kayıt tutulmamış; günlük yaşam toplamında hesaba katılır.')
    else:
        view=['sayi','gun_oncesi','saat_oncesi','ilk3_grubu','onceki_saat_toplam','uyku_el','gun_kesintisiz_oncesi']
        st.caption('Aşağıdaki alanlar yalnız hedef çekiliş ÖNCESİNDE bilinir. İlk üç el grubu 4. elden önce gösterilmez.')
        st.dataframe(state[view].sort_values(['gun_oncesi','sayi'],ascending=[False,True]),hide_index=True,use_container_width=True)
        with st.expander('Sonuç sonrası doğrulama (ayrı açılır)'):
            st.dataframe(state[['sayi','gun_oncesi','cikti','gun_sonrasi','saat_sonrasi','gun_kesintisiz_sonrasi']],hide_index=True,use_container_width=True)

with cohorts:
    st.subheader('İlk 3 elin 0/3, 1/3, 2/3, 3/3 grupları')
    day=st.selectbox('Gün',dates,key='cohort_day')
    hours=all_hours[all_hours.tarih==day]
    hour=st.selectbox('Saat',sorted(hours.saat.unique().tolist()),key='cohort_hour')
    hourdata=hours[hours.saat==hour]
    group=st.selectbox('İlk 3 el grubu',[0,1,2,3],key='cohort_group')
    cohort=hourdata[hourdata.ilk3==group]
    st.metric('Bu gruptaki sayı',len(cohort))
    st.dataframe(cohort[['sayi','ilk3','son9','saat_toplam','ciktigi_eller','ciktigi_cekilisler','ilk_4_el','ilk_5_el','ilk_6_el','ilk_7_el','ilk_8_el']],hide_index=True,use_container_width=True)
    st.subheader('Bu grubun 4.–12. eldeki gerçek aktivasyonu')
    group_ids=set(cohort.sayi)
    trans=result['esik_gecisleri']
    trans=trans[(trans.tarih==day)&(trans.saat==hour)&(trans.sayi.isin(group_ids))]
    if not trans.empty:
        st.dataframe(trans.groupby('el').agg(aktif_sayi=('sayi','nunique'),cikis=('sayi','size')).reindex(range(4,13),fill_value=0).reset_index(),hide_index=True,use_container_width=True)
        st.dataframe(trans[['el','cekilis','sayi','oncesi','sonrasi','uyku_el']],hide_index=True,use_container_width=True)
    else: st.info('Bu grupta son 9 elde aktivasyon yok.')

with paths:
    st.subheader('Bir sayının 00:02’den gün sonuna yaşamı')
    day=st.selectbox('Gün',dates,key='path_day')
    number=st.selectbox('Sayı',list(range(1,81)),key='path_number')
    path=all_paths[(all_paths.tarih==day)&(all_paths.sayi==number)]
    st.dataframe(path,hide_index=True,use_container_width=True)
    one=all_pre[(all_pre.tarih==day)&(all_pre.sayi==number)]
    st.dataframe(one[['cekilis','el','saat','gun_oncesi','cikti','gun_sonrasi','saat_oncesi','saat_sonrasi','uyku_el','gun_kesintisiz_oncesi','gun_kesintisiz_sonrasi']],hide_index=True,use_container_width=True)
    st.caption('01:02 günlük toplama dahildir; saatlik 12-el tablosunda ayrı köprü olarak tutulur.')

with thresholds:
    st.subheader('Günlük +1,+2,+3,+4... eşiklerin gerçek çekilişleri')
    day=st.selectbox('Gün',dates,key='threshold_day')
    number=st.selectbox('Sayı (tümü için boş bırak)', ['Tümü']+list(range(1,81)),key='threshold_number')
    th=all_thresholds[all_thresholds.tarih==day]
    if number!='Tümü': th=th[th.sayi==number]
    st.dataframe(th,hide_index=True,use_container_width=True)
    st.caption('Bu tablo gerçekleşmiş eşik zamanlarını açıklar; hedef çekiliş öncesi tahmin olarak kullanılamaz.')

with forward:
    st.subheader('Kronolojik sabit kıyas: son 12 çekiliş frekansı')
    st.caption('Her hedef için yalnız önceki çekilişler kullanılır; günün ilk çekilişinde tahmin yok. Bu gelişmiş öğrenen motor değil, referans ölçümdür.')
    day=st.selectbox('Gün',dates,key='forward_day')
    p=result['kronolojik_kiyas'];p=p[p.tarih==day]
    st.dataframe(p,hide_index=True,use_container_width=True)
    st.metric('Tahmin yapılan çekiliş',int(p.isabet.notna().sum()))
    if p.isabet.notna().any(): st.metric('Ortalama isabet',round(float(p.isabet.mean()),3))

with export:
    st.subheader('14 günün bütün tabloları — tek ZIP')
    st.download_button('📦 14 GÜNLÜK TEK ÇIKTI ZIP İNDİR',make_zip(result),'HIZLI_ON_14_GUN_TEK_CIKTI.zip','application/zip',type='primary')
    st.caption('CSV dosyaları: günlük özet, ilk3 eşikleri, saatlik 80 sayı, çekiliş öncesi 80 sayı, eşik geçişleri, günlük yaşam yolu ve kronolojik kıyas.')
