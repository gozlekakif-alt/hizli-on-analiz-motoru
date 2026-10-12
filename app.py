# -*- coding: utf-8 -*-
"""Hızlı On Ritmik Aile / 3. Görünüş Ar-Ge V6 (Streamlit)."""
import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json

import pandas as pd
import requests
import streamlit as st

from motor import (DAY_GAPS, FAMILY_SIZES, read_draws, draw_text, quality_table,
                   discover_families, family_profiles, forecast_exact_third,
                   validate_exact_third, walk_forward, live_structural, report_zip, by_day)
from legacy_seeds import LEGACY_SEEDS

st.set_page_config(page_title='Hızlı On | 3. Görünüş Motoru V6', page_icon='🎯', layout='wide')
st.title('🎯 Hızlı On — Ritim, 3. Görünüş ve Kupon Laboratuvarı V6')
st.caption('5 / 6 / 7 / 8 / 9 / 10 sayılı aileler · 217 slot · 1→2→3 · rakam değişimli ritim · gün gün ileri-zaman testi')
st.info('Bu uygulama **tahmin hipotezlerini sınar**. Geçmişte ritim görülmesi, rastgele çekilişin üçüncü kez tekrarlanacağını göstermez. Doğrulanmış üstünlük yoksa **0 kupon** üretir.')
RAW = 'https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt'
TODAY = (datetime.now(timezone.utc)+timedelta(hours=3)).date()

@st.cache_data(ttl=90, show_spinner=False)
def github_data(raw_url, refresh_key):
    r=requests.get(raw_url,timeout=35,headers={'Cache-Control':'no-cache'})
    r.raise_for_status()
    return r.text

@st.cache_data(show_spinner=False)
def compute(text,target_date,holdout,max_gap,min_train,max_per_size,max_hour):
    records,warnings=read_draws(text)
    if not records:
        return {'records':[], 'warnings':warnings}
    historical=[r for r in records if r.day<target_date]
    available_dates=sorted(by_day(historical))
    enough=len(available_dates)>=12
    if enough:
        st_date=available_dates[-min(holdout,len(available_dates)-5)]
        # Previously selected seed families were mined from Aug 1–Oct 9.
        # They are excluded if the historical test period begins within that discovery window.
        allowed=LEGACY_SEEDS if st_date>datetime(2026,10,9).date() else []
        train_pre=[r for r in historical if r.day<st_date]
        fixed_candidates, discovery_fixed=discover_families(train_pre,allowed,max_per_size,max_gap)
        v,wf_tickets,size_summary,stats,wf_info=walk_forward(
            historical,holdout,max_gap,max_hour,min_train=min_train)
        test_dates=available_dates[-wf_info['test_gün']:]
        fixed_exact=validate_exact_third(historical,fixed_candidates,test_dates,2,max_gap)
    else:
        fixed_candidates={}
        discovery_fixed={}
        v,wf_tickets,size_summary,stats=pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{}
        wf_info={'uyarı':'En az 12 geçmiş gün olmadan ileri-zaman testi yapılamaz; kupon kararı 0.'}
        fixed_exact=pd.DataFrame()
    # For live use all earlier dates, never the target day's unknown future outcomes.
    # Candidates discovered on all pre-target data MUST NOT be used to retrospectively
    # claim wins in the chronological holdout report.
    seeds_live=LEGACY_SEEDS if target_date>datetime(2026,10,9).date() else []
    if historical:
        live_families,discover_info=discover_families(historical,seeds_live,max_per_size,max_gap)
        profiles,family_hits=family_profiles(historical,live_families,max_gap)
        exact_now=forecast_exact_third(records,live_families,target_date,2,12,max_gap)
    else:
        live_families,discover_info={},{}
        profiles,family_hits,exact_now=pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    verified=set()
    if not v.empty:
        verified=set((str(r['Mekanizma']),int(r['Gap']),int(r['Saat']),int(r['Boyut']))
                     for _,r in v[v['Testten geçti']].iterrows())
    live_all,live_accepted=live_structural(records,target_date,stats,max_gap,12,min_train,max_hour,verified)
    return {'records':records,'warnings':warnings,'quality':quality_table(records),
            'validations':v,'wf_tickets':wf_tickets,'size_summary':size_summary,
            'wf_info':wf_info,'fixed_exact':fixed_exact,'discover_info':discover_info,
            'fixed_discovery':discovery_fixed,'profiles':profiles,'family_hits':family_hits,
            'exact_now':exact_now,'live_all':live_all,'live_accepted':live_accepted,
            'family_count':sum(len(v) for v in live_families.values())}


def show_table(df, n=200):
    if isinstance(df,pd.DataFrame) and not df.empty:
        st.dataframe(df.head(n),hide_index=True,use_container_width=True,height=min(570,75+34*min(n,len(df))))
        if len(df)>n:st.caption(f'Ekranda {n} / {len(df)} satır; tamamı ZIP raporunda.')
    else:
        st.caption('Bu koşullarda kayıt yok.')


def summary_note(res,target):
    n=len(res['records']); vals=res.get('validations',pd.DataFrame())
    picks=res.get('live_accepted',pd.DataFrame())
    tested=int(vals['Testten geçti'].sum()) if not vals.empty else 0
    txt=f'''HIZLI ON V6 — 3. GÖRÜNÜŞ VE RİTİM RAPORU
Hedef gün: {target:%d.%m.%Y}
Geçerli çekiliş: {n}
Geçmişte keşfedilmiş/yeniden keşfedilmiş aile: {res.get('family_count',0)}
İleri-zaman istatistik testi geçen koşul: {tested}
Canlı onaylı kupon: {len(picks)}

METODOLOJİ
1) Doğrulanan çekiliş saatleri: #1–13 (00:02–01:02) ve #14–217 (07:02–23:57).
2) Aynı aile, tek çekilişte sayıların tamamının bir arada çıkmasıdır. 1→2→3 zincirinde aynı rakamlar korunur.
3) Rakam değişimli analiz: İlk iki çekilişin ortak sayı adedi >= k ise, ikinci ve üçüncü çekilişin ortak sayı adedi >= k olur mu? Bu, aynı aile olmak ZORUNDA DEĞİLDİR.
4) Yakın çekiliş gap'i ve gün gap'i iki ayrı araştırmadır. Saat ile günlük sıra aynı zaman bilgisinin farklı gösterimidir.
5) Aile keşfi bütçelidir. 20 sayıdan oluşan her çekilişin C(20,k) tüm alt kümeleri eksiksiz taranmaz; ikili ve üçlü örtüşmelerden kontrollü aday çıkarılır.
6) Eğitim ve test kronolojik ayrılır. Başlangıç çekirdekleri oluşturulurken test verisine bakılmaz. Kütükteki önceki keşif aileleri, orijinal keşif dönemi içinde yapılan testlerde kullanılmaz.
7) Holdout testi her gün, yalnız o günden önceki bilgiyle tahmin üretir ve sonucu ancak ertesi gün eğitime katılır.
8) Doğal s23 >= k ihtimali hipergeometriktir. Toplam 80 sayı, 20 gelen sayı, 20 sonraki sayı. Normal 10'lu kupon için beklenen isabet sayısı 2.5'tir.
9) Test sinyalleri için çoklu karşılaştırma düzeltmeli p kullanılır. Aynı saat/gap etiketlerinde bağımlı örnekler olabileceğinden p-değerleri kesin kanıt değil, yalnız tarama filtresidir.
10) Canlı kupon: hem eğitim sinyali hem bağımsız geçmiş test koşulu geçmedikçe 0. 'Aday' ekranındaki kuponlar doğrulanmış bahis tavsiyesi değildir.
11) İleri-zaman testindeki günlük en fazla belirtilen kadar kupon, o günün sonucu görülmeden önceden seçilir.
12) Gün/slot bazında eksik çekilişler otomatik tahmini artırmaz; zincir için her üç geçerli olay gerekir.
13) Önceki geçmiş vuruşları inceleyerek başarılı seçim yapmak (post-hoc) ayrı; gerçek ileri-zaman isabeti ayrıdır.

Uyarı: Sayısal ritimler tesadüfen oluşabilir; gelecekte tahmin avantajı kanıtlanmamıştır.
'''
    return txt

with st.sidebar:
    st.header('⚙️ Veri ve motor ayarları')
    raw_url=st.text_input('GitHub veri.txt RAW',value=RAW)
    if st.button('🔄 GitHub verisini yeniden al'):
        github_data.clear();compute.clear();st.rerun()
    up=st.file_uploader('İsteğe bağlı ek TXT dosyaları',type=['txt'],accept_multiple_files=True)
    target=st.date_input('Hedef gün',value=TODAY)
    holdout=st.slider('İleri-zaman test günleri',5,15,7)
    maxgap=st.slider('Çekiliş gap üst sınırı',6,36,18,step=6)
    mintrain=st.slider('Ritim için minimum geçmiş olay',25,150,50,step=5)
    maxfamilies=st.slider('Yeni aile adayı / boyut',40,500,220,step=20)
    maxhour=st.slider('Saat başına en çok kupon',1,12,6)
    st.caption('Derin tarama genişleyince Streamlit Cloud belleği ve çalışma süresi artabilir.')
    st.markdown('**Canlı çekiliş ekleme**')
    pasted=st.text_area('Çekilişi yapıştır: tek satır TXT veya resmi sonuç bloğu',height=140,placeholder='61674;12.10.2026 09:42;1,2,... (20 farklı sayı)')
    run=st.button('🔬 TÜM ANALİZİ BAŞLAT / GÜNCELLE',type='primary',use_container_width=True)

if run or 'analysis_v6' not in st.session_state:
    try:
        base=github_data(raw_url,0)
    except Exception as ex:
        base=''
        st.warning(f'GitHub verisi şu anda alınamadı: {ex}. Yüklenen TXT / yapıştırılan veriler kullanılıyor.')
    parts=[base]
    for x in up or []:
        try:parts.append(x.getvalue().decode('utf-8-sig'))
        except UnicodeError:parts.append(x.getvalue().decode('cp1254',errors='replace'))
    if pasted.strip():parts.append(pasted)
    combined='\n'.join(parts)
    valid,parse_warn=read_draws(combined)
    if parse_warn['çakışmalar']:
        st.error('Veride çelişen çekiliş kayıtları var. Güvenli analiz için önce düzelt: '+ '; '.join(parse_warn['çakışmalar'][:10]))
        st.stop()
    if not valid:
        st.error('Hiç geçerli çekiliş okunamadı. Dosya biçimi: NO;GG.AA.YYYY SS:DD;20 sayı')
        st.stop()
    st.session_state['data_v6']=draw_text(valid)
    st.session_state['target_v6']=target
    st.session_state['params_v6']=(holdout,maxgap,mintrain,maxfamilies,maxhour)
    st.session_state['analysis_v6']=None

if st.session_state.get('analysis_v6') is None:
    with st.spinner('Saat ve çekiliş ritimleri taranıyor; üçüncü görünüşler ile ileri-zaman testleri hesaplanıyor…'):
        res=compute(st.session_state['data_v6'],st.session_state['target_v6'],*st.session_state['params_v6'])
        st.session_state['analysis_v6']=res
else:
    res=st.session_state['analysis_v6']
    if (target!=st.session_state['target_v6'] or
        (holdout,maxgap,mintrain,maxfamilies,maxhour)!=st.session_state['params_v6'] or
        bool(pasted.strip()) or bool(up)):
        st.warning('Yan tarafta veri veya ayar değişti. Yeni değerlerin işlenmesi için TÜM ANALİZİ BAŞLAT / GÜNCELLE düğmesini kullan.')

records=res['records']
old=[r for r in records if r.day < st.session_state['target_v6']]
current=[r for r in records if r.day == st.session_state['target_v6']]
val=res['validations']
accepted=res['live_accepted']
q=res['quality']

c1,c2,c3,c4,c5=st.columns(5)
c1.metric('Çekiliş',f'{len(records):,}'.replace(',','.'))
c2.metric('Takip edilen 5–10 aile',res['family_count'])
c3.metric('Hedef gün çekiliş',len(current))
c4.metric('Holdout geçen koşul',int(val['Testten geçti'].sum()) if not val.empty else 0)
c5.metric('Onaylı canlı kupon',len(accepted))

if not old:
    st.warning('Hedef günden önce analiz yapacak geçmiş çekiliş bulunmuyor.');st.stop()
if not val.empty and len(val[val['Testten geçti']])==0:
    st.warning('İleri-zaman döneminde çoklu-test filtresini geçen ritim yok: **onaylı kupon 0**. Adaylar araştırma amaçlıdır.')
if not res['warnings'].get('çakışmalar') and res['warnings'].get('geçersiz_satır'):
    st.caption('Biçimi bozuk satır sayısı: '+str(res['warnings']['geçersiz_satır']))

T=st.tabs(['📊 Genel bakış','🧬 5–10 aileler','🔗 1→2→3 aynı rakam','🔄 Rakam değişen ritim',
           '🧪 İleri-zaman isabet','🎯 Canlı kupon','📦 ZIP / GitHub'])

with T[0]:
    st.subheader('Gün/gap ve çekiliş/slot kalitesi')
    st.caption('00:02 #1, 01:02 #13, 07:02 #14, 09:37 #45 ve 23:57 #217. Eksik günler saklanmaz.')
    show_table(q.tail(35),35)
    inf=res['wf_info']
    st.markdown(f"**İleri-zaman dönemi:** {inf.get('test_başlangıç','—')} – {inf.get('test_bitiş','—')} | Gün: {inf.get('test_gün','—')}")
    if inf.get('uyarı'): st.warning(inf['uyarı'])
    st.write('Ritim motorlarının iş akışı: gün/saat/çekiliş → 1. vuruş → 2. vuruş (gap) → 3. vuruş testi → geçmişe bakmadan kupon testi → yalnız doğrulanan sinyal.')
    h=res['family_hits']
    if not h.empty:
        daily=h.groupby(['Tarih','Boyut']).size().rename('Aile tam vuruş').reset_index()
        st.subheader('Günlük aile tam-vuruş kayıtları')
        show_table(daily.tail(70),70)
        st.subheader('Saat ve çekiliş sırası — vuruş detay')
        show_table(h.sort_values(['Tarih','Saat'],ascending=[False,False]),120)

with T[1]:
    st.subheader('5’li, 6’lı, 7’li, 8’li, 9’lu, 10’lu aile madenciliği')
    st.caption('Aday aileler tarihsel ikili ve üçlü kesişmelerden çıkarılır. Tüm olası kombinasyonlar hesaplanmaz; gerçek tüm-vuruşlar ayrıca veride doğrulanır.')
    st.write('Keşif özeti:',res['discover_info'])
    kset=st.multiselect('Aile boyutu seç',FAMILY_SIZES,default=list(FAMILY_SIZES),key='kset')
    profiles=res['profiles']
    if not profiles.empty:
        chosen=profiles[profiles['Boyut'].isin(kset)]
        show_table(chosen,250)
        st.caption('“Üçlü tekrar” sayısı aynı ailede tam isabetin üç çekiliş/günde olmasıdır; seçilmiş sonuçların geleceğe taşınması doğrulanmış değildir.')

with T[2]:
    st.subheader('Gerçek aynı aile: 1. → 2. → 3. kez')
    st.markdown('Rakamlar **aynı ailede değişmez**. Çekiliş farkı +g veya gün farkı +g, en az iki geçmiş üçlü zincir varsa aday penceresi açılır.')
    st.write('Bugünkü gelecekteki adaylar (geçmişte en az iki tam üçlü zincir koşullu):')
    show_table(res['exact_now'],150)
    st.write('Gerçek ileri-zaman 3. olay testi — aile ve 3. hedef test öncesinde bellidir:')
    show_table(res['fixed_exact'],200)
    e=res['fixed_exact']
    if not e.empty:
        st.write(f"Önceden üretilen hedef: **{len(e)}** · 3. tam eşleşme: **{int(e['3. isabet'].sum())}** · başarı: **{e['3. isabet'].mean():.2%}**")
    else:
        st.info('Bu geçmiş veri ve katı zincir koşuluyla 3. tam görünüşe ilişkin ileri-zaman tahmini oluşmadı.')

with T[3]:
    st.subheader('Rakamlar değişse de üçüncü çekiliş ritmi var mı?')
    st.caption('Birinci–ikinci çekilişte en az k ortak sayı, ikinci–üçüncü çekilişte en az k ortak sayı: bunlar birbirinden farklı rakamlardan oluşabilir.')
    if not val.empty:
        m=st.selectbox('Yol', ['çekiliş','gün'], key='route')
        dk=st.multiselect('Boyut',FAMILY_SIZES,default=list(FAMILY_SIZES),key='val_k')
        vf=val[(val['Mekanizma']==m)&val['Boyut'].isin(dk)]
        show_table(vf,250)
        st.caption('Çekiliş gap = ardışık 5 dakikalık kayıt farkı. Gün gap = üç farklı günde aynı gerçek 217’lik sıra. “3 çizimde aynı aile” ayrıca belirtilir.')
    else:
        st.warning('Bu veri aralığında yeterli geçmiş/test günü yok.')

with T[4]:
    st.subheader('Kör ileri-zaman kupon isabet raporu')
    st.caption('Her test günü hesaplanan kuponlar yalnız önceki günlerin verisiyle seçildi; seçildikten sonra sonraki çekiliş sonucuyla karşılaştırıldı.')
    show_table(res['size_summary'],10)
    b=res['wf_tickets']
    if not b.empty:
        st.markdown(f"**Deneme kuponları: {len(b)}** — 10’lu kupon için matematiksel ortalama {10/4:.1f} sayı/kupon. Bu bir kazanma vaadi değildir.")
        show_table(b.sort_values(['Tarih','Saat'],ascending=False),200)
    else:
        st.info('Kör testte geçmiş sinyal filtresini geçen kupon çıkmadı. Başarı varmış gibi rastgele kupon üretilmedi.')

with T[5]:
    st.subheader(f"{st.session_state['target_v6']:%d.%m.%Y} — canlı 3. çekiliş penceresi")
    if current:
        last=max(current,key=lambda r:r.dt)
        st.write(f"Son kaydedilen çekiliş: **#{last.id}** — **{last.dt:%H:%M}**, günlük sıra **#{last.pos}**")
    st.markdown('**Bağımsız geçmiş testini geçen canlı kuponlar**')
    if accepted.empty:
        st.warning('Şu an için **0 onaylı kupon**. Sadece geçmişe uygun görünen ritimleri oynamak için doğrulama eksik.')
    else:
        show_table(accepted,60)
    st.markdown('**Keşif amaçlı olası 3. çekiliş adayları — bunlar kupon tavsiyesi değildir**')
    candidate=res['live_all']
    if not candidate.empty:
        show_table(candidate.sort_values(['Train lift','Train örnek'],ascending=False),200)
    else:
        st.caption('Gelecek 12 çekilişte geçmiş örnek eşiğini geçen 1→2 tetikleyicisi görülmedi.')

with T[6]:
    st.subheader('Bütün sonuçları tek dosya halinde indir')
    tables={'01_VERI_KALITESI.csv':q, '02_AILELER_5_10.csv':res['profiles'],
            '03_AILE_GORUNUS_CEKILIS_SAAT.csv':res['family_hits'],
            '04_KOR_TEST_GAP_RITIM.csv':val,'05_KOR_TEST_KUPON_ISABET.csv':res['wf_tickets'],
            '06_KOR_TEST_BOYUT_0_10_DAGILIM.csv':res['size_summary'],
            '07_TAM_3LU_KOR_TEST.csv':res['fixed_exact'],
            '08_CANLI_3LU_TAM_AILE_ADAY.csv':res['exact_now'],
            '09_CANLI_YAPISAL_ADAY.csv':res['live_all'],
            '10_ONAYLI_CANLI_KUPON.csv':accepted}
    st.download_button('⬇️ TÜM ANALİZLER — TEK ZIP',data=report_zip(tables,summary_note(res,st.session_state['target_v6'])),
        file_name='HIZLI_ON_3_GORUNUS_V6_TUM_RAPORLAR.zip',mime='application/zip',type='primary')
    st.download_button('⬇️ Güncel birleştirilmiş veri.txt',data=draw_text(records).encode('utf-8'),
        file_name='veri_birlesik.txt',mime='text/plain')
    with st.expander('🔒 GitHub veri.txt’ye kalıcı kaydet (isteğe bağlı)'):
        st.caption('Yalnız GitHub deposunun yöneticisi iseniz ve Streamlit Secrets içinde GITHUB_TOKEN varsa çalışır. Token ekranda gösterilmez. Kaydet düğmesine basmadıkça dış veri değiştirilmez.')
        if st.button('Github veri.txt dosyasını birleştirip KAYDET',type='secondary'):
            try:
                tok=st.secrets.get('GITHUB_TOKEN','')
                if not tok:raise ValueError('Streamlit Secrets içine GITHUB_TOKEN ekleyin.')
                endpoint='https://api.github.com/repos/gozlekakif-alt/hizli-on-analiz-motoru/contents/veri.txt'
                hdr={'Authorization':f'Bearer {tok}', 'Accept':'application/vnd.github+json'}
                check=requests.get(endpoint,headers=hdr,timeout=25)
                check.raise_for_status()
                blob=check.json()
                content=base64.b64decode(blob['content']).decode('utf-8-sig')
                remote,_=read_draws(content)
                merged,conf=read_draws(draw_text(remote)+'\n'+draw_text(records))
                if conf['çakışmalar']:
                    raise ValueError('Mevcut repo verisinde çakışma: '+str(conf['çakışmalar'][:3]))
                if draw_text(remote)==draw_text(merged):
                    st.info('GitHub zaten güncel.')
                else:
                    payload={'message':'Hizli On veri.txt checked merge V6',
                             'content':base64.b64encode(draw_text(merged).encode('utf-8')).decode('ascii'),
                             'sha':blob['sha'],'branch':'main'}
                    sent=requests.put(endpoint,headers=hdr,json=payload,timeout=35)
                    sent.raise_for_status()
                    github_data.clear();compute.clear()
                    st.success(f'GitHub main/veri.txt güncellendi: {len(merged)} çekiliş.')
            except Exception as exc:
                st.error(f'GitHub kaydı yapılmadı: {str(exc)[:260]}')

st.caption('Araştırma uygulaması V6 · 5–10’lu ailelerin geçmiş başarıları, ileri-zaman koşullu tahmin başarısıyla aynı şey değildir.')
