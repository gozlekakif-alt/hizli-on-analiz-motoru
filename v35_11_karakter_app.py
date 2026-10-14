# -*- coding: utf-8 -*-
"""V35 Streamlit tab: 11 real-draw binary signatures for 80 numbers."""
import hashlib
import streamlit as st
from v35_11_cekim_cift_karakter import study


def render_v35(draws):
    st.subheader('🧬 V35 — 11 Çekilişlik Çift Karakter / 80 Sayının İmzası')
    st.info('Her sayı için son **11 gerçek çekilişin 1/0 dizisi** kaydedilir: '
            '1 = çıkan 20, 0 = çıkmayan 60. '
            '11’de en az 6 kez görünenler **YOĞUN 6+**, '
            'üst üste 6+ çekiliş hiç görünmeyenler **BEKLEYEN 6+**.')
    st.caption('Bir sayı, aynı 11 çekilişte hem 6+ kez çıkmış hem 6+ kez '
               'üst üste kaybolmuş olamaz. Farklı sayılar bu iki sınıfta '
               'aynı anda bulunabilir. Eşleşmelerinin sonraki çekilişte '
               'birlikte çıkışı ve 6 sıcaklık, 8 bant, V32 döngü kimliği incelenir.')
    day_positions={}
    for d in draws:
        day_positions.setdefault(d['day'],set()).add(int(d['pos']))
    full=sum(v==set(range(1,218)) for v in day_positions.values())
    a,b,c=st.columns(3)
    a.metric('Tam gün',full)
    b.metric('Eksik gün',len(day_positions)-full)
    c.metric('Gerçek çekiliş',len(draws))
    partial=st.checkbox('Eksik günleri dahil et; 11 penceresini eksik yerde sıfırla',
        value=False,key='v35_partial')
    signature=hashlib.sha256(str([(d['no'],d['day'],d['pos'],d['mask']) for d in draws]).encode()).hexdigest()
    if st.button('▶️ V35 — 80 SAYI × 11 ÇEKİLİŞ TÜM KARAKTERLERİ TARA',
                 type='primary',use_container_width=True,
                 disabled=not draws or (full==0 and not partial),key='v35_run'):
        progress=st.progress(0,text='11 bitlik 80 sayı geçmişi hazırlanıyor')
        label=st.empty()
        def notify(x,n,stage,day):
            progress.progress(min(1.0,x/max(1,n)),text=f'{int(100*x/max(1,n))}% — {stage}')
            label.caption(f'{day} • {x}/{n}')
        with st.spinner('72 gün için 80 sayı 1/0 imzaları ve birlikte dönüşler inceleniyor...'):
            try:
                result=study(draws,include_partial=partial,progress=notify)
                st.session_state['v35_ready']=(signature,partial,*result)
                progress.progress(1.0,text='100% — V35 ZIP raporu hazır')
            except Exception as exc:
                st.error('V35 analizi: '+str(exc))
    result=st.session_state.get('v35_ready')
    if not result:return
    oldhash,oldpartial,blob,meta,classes,freq,selected=result
    if oldhash!=signature or oldpartial!=partial:
        st.warning('Yeni veri veya seçenekler mevcut. Güncel sonuç için tekrar çalıştır.')
    st.download_button('⬇️ V35 11 ÇEKİLİŞ 80 SAYI ÇİFT KARAKTER TEK ZIP',
        data=blob,file_name='V35_11_CEKILIS_80_SAYI_CIFT_KARAKTER_TEK_ZIP.zip',
        mime='application/zip',type='primary',use_container_width=True,key='v35_zip')
    x,y,z=st.columns(3)
    x.metric('11’li gerçek kesit',meta['11li_kesit'])
    y.metric('Kesit başına 11’de 6+',meta['yogun_ortalama_kesit'])
    z.metric('Kesit başına 6+ bekleyen',meta['bekleyen_ortalama_kesit'])
    st.caption('RNG kontrol: 11’de 6+ görünme Binom(11, %25), '
               '6+ art arda yokluk yaklaşık (%75)^6. '
               'İki farklı sayının aynı anda gelme şansı ~%6,01.')
    st.markdown('#### Son 36 gün: beş karakterin bir sonraki çekilişe dönüşü')
    st.dataframe([r for r in classes if r['donem']=='TEST'],
                 hide_index=True,use_container_width=True)
    with st.expander('11’de 0–11 görünme sayısına göre gerçek/test sonuçları'):
        st.dataframe([r for r in freq if r['donem']=='TEST'],
                     hide_index=True,use_container_width=True)
    with st.expander('İlk 36 günde seçilen 11 haneli imzalar, sonraki 36 gündeki sınama'):
        st.dataframe(selected,hide_index=True,use_container_width=True)
    st.caption('18 dosyalı ZIP içinde **her sayı / her 11’li pencere** 1/0 imzası, '
               'durum geçişleri, yüksek + bekleyen sayı çiftleri, bant/ısı eşleşmeleri, '
               'günlük aile büyüklükleri ve gerçekleşmiş hedeflerin test kayıtları var. '
               'Geçmişte iyi görünen imza, gelecekte avantaj sağlar diye varsayılmıyor.')
