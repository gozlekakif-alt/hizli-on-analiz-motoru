from pathlib import Path
import os
from urllib.request import Request,urlopen
import streamlit as st
from motor import parse_data,analyse,make_zip

st.set_page_config(page_title='Hızlı On | 14 Gün Sıralı Motor',layout='wide')
st.title('Hızlı On — 14 Günlük Otomatik Sıralı Motor')
st.caption('İlk 3 el 0/1/2/3 grupları, 4–8+ eşikleri, çekiliş bazlı yaşam ve geçmişe dayalı kronolojik kıyas. Tahmin garantisi yok.')
root=Path(__file__).parent
url=''
try:url=st.secrets.get('GITHUB_RAW_URL','')
except Exception:pass
url=url or os.getenv('GITHUB_RAW_URL','')
@st.cache_data(ttl=300,show_spinner=False)
def get_raw(url):
    if not (url.startswith('https://raw.githubusercontent.com/') or url.startswith('https://github.com/')):raise ValueError('GitHub raw URL geçersiz')
    if url.startswith('https://github.com/'):url=url.replace('https://github.com/','https://raw.githubusercontent.com/',1).replace('/blob/','/')
    with urlopen(Request(url,headers={'User-Agent':'HizliOn-Research'}),timeout=20) as response:
        data=response.read(25_000_001)
    if len(data)>25_000_000:raise ValueError('25 MB sınırı aşıldı')
    return data
if (root/'veri.txt').exists():raw=(root/'veri.txt').read_bytes();source='GitHub deposundaki veri.txt (app.py yanında)'
elif url:
    try:raw=get_raw(url);source='GitHub otomatik raw URL'
    except Exception as e:st.error(f'GitHub okunamadı: {e}');st.stop()
else:
    st.error('GitHub veri.txt bulunamadı. veri.txt dosyasını app.py yanına koy veya GITHUB_RAW_URL secret tanımla. Eski veriye sessiz geçiş yapılmaz.')
    st.stop()
try:df=parse_data(raw)
except Exception as e:st.error(f'Veri biçimi hatası: {e}');st.stop()
st.info(f'Kaynak: {source} · Toplam {len(df)} çekiliş · {df.draw_time.dt.date.nunique()} gün')
@st.cache_data(show_spinner=False)
def run(raw):return analyse(parse_data(raw))
with st.spinner('14 gün sırayla işleniyor; çekilişlerin geleceği kullanılmıyor...'):
    try:result=run(raw)
    except Exception as e:st.error(f'Analiz durdu: {e}');st.stop()
if result['uyarilar']:st.warning('Eksik/uyumsuz kayıt: '+'; '.join(result['uyarilar']))
else:st.success('Gün ve saat bütünlük kontrolü geçti.')
a,b,c=st.columns(3)
a.metric('Araştırma günü',len(result['gun_ozeti']))
b.metric('Tam saat × 80 sayı',len(result['saat_80_yasam']))
c.metric('Çekiliş öncesi 80 kayıt',len(result['cekilis_80_oncesi']))
st.download_button('📦 14 GÜNLÜK TEK ÇIKTI ZIP İNDİR',make_zip(result),'HIZLI_ON_14_GUN_TEK_CIKTI.zip','application/zip',type='primary')
st.subheader('14 gün birleşik: ilk üç elden 4–8+ dönüşümü')
st.dataframe(result['ilk3_esik_ozeti'],hide_index=True,use_container_width=True)
st.subheader('Gün gün kronolojik kıyas ve veri denetimi')
st.dataframe(result['gun_ozeti'],hide_index=True,use_container_width=True)
dates=result['gun_ozeti']['tarih'].tolist();chosen=st.selectbox('Detay günü',dates)
subset=result['saat_80_yasam'];subset=subset[subset.tarih==chosen]
hour=st.selectbox('Saat',sorted(subset.saat.unique().tolist()))
st.dataframe(subset[subset.saat==hour],hide_index=True,use_container_width=True)
st.subheader('00:02 → hedef çekiliş: 80 sayının günlük +1,+2,+3,... yaşamı')
number=st.selectbox('Günlük yaşamı izlenecek sayı',list(range(1,81)),index=19)
paths=result['gun_80_yasam_yolu'];st.dataframe(paths[(paths.tarih==chosen)&(paths.sayi==number)],hide_index=True,use_container_width=True)
all_pre=result['cekilis_80_oncesi'];number_pre=all_pre[(all_pre.tarih==chosen)&(all_pre.sayi==number)].copy()
if not number_pre.empty:
    st.dataframe(number_pre[['cekilis','el','saat','gun_oncesi','cikti','gun_sonrasi','gun_kesintisiz_oncesi','gun_kesintisiz_sonrasi','uyku_el']],hide_index=True,use_container_width=True)
    st.caption('gun_oncesi: çekiliş sonucu bilinmeden önceki günlük toplam; gun_sonrasi: sonuç geldikten sonraki toplam. 01:02 günlük toplamı etkiler ancak 12 ellik saat sınıflamasına girmez.')
st.subheader('Günlük eşiklerin gerçekleştiği çekilişler')
th=result['gun_esik_gecisleri'];st.dataframe(th[(th.tarih==chosen)&(th.sayi==number)],hide_index=True,use_container_width=True)
st.caption('01:02 köprü çekilişi 12 ellik saat analizine dahil edilmez. İlk üç el grubu yalnız 4. el öncesinde kullanılabilir. 4+ eşik tabloları gerçekleşmiş sonuçların açıklamasıdır; kıyas tahminleri yalnız geçmiş son 12 elden oluşturulur.')
