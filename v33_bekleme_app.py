# -*- coding: utf-8 -*-
"""V33 waiting 6..10+ classes: daily counts, live pools and one ZIP."""
import hashlib
import streamlit as st
from v33_bekleme_havuzlari import run_study


def render_v33(draws):
    st.subheader('⏳ V33 — 6 / 7 / 8 / 9 / 10 Çekiliş Bekleyen 80 Sayı')
    st.info('Her sayının gün içinde son görülmesinden beri **kaç gerçek çekilişte çıkmadığını** sayarız. '
            '6, 7, 8, 9, 10 ve 11+ ayrı sınıflardır. Sayı çıkınca bekleme sıfırlanır; '
            'V32 80/80 döngüsü ayrıca takip edilir.')
    st.caption('Günün 00:02 başlangıcında bekleme sıfır; 01:02 → 07:02 arasında sahte çekiliş yok. '
               'Her çekilişten sonra sınıfa giren sayı çıkmayan 60 havuzundadır. '
               '6 sıcaklık koltuğu, 8 onluk bant ve V32 80/80 görülme havuzu ayrı gösterilir.')
    groups={}
    for d in draws:groups.setdefault(d['day'],set()).add(int(d['pos']))
    complete=sum(len(p)==217 and p==set(range(1,218)) for p in groups.values())
    a,b,c=st.columns(3)
    a.metric('Tam 217 çekilişlik gün',complete)
    b.metric('Eksik gün',len(groups)-complete)
    c.metric('Kayıtlı çekiliş',len(draws))
    partial=st.checkbox('Eksik günleri de incele (aralarda bekleme sıfırlanır)',
                        value=False,key='v33_partial')
    if st.button('▶️ V33 — TÜM 80 SAYI BEKLEME HAVUZLARINI TARA',
                 type='primary',use_container_width=True,
                 disabled=not draws or (not partial and complete==0),key='v33_run'):
        bar=st.progress(0,text='Sayılar ve alt havuzlar taranıyor')
        status=st.empty()
        def progress(done,total,stage,day):
            ratio=min(1.,done/max(1,total))
            bar.progress(ratio,text=f'%{int(100*ratio)} — {stage}')
            status.caption(f'{done}/{total} · {day}')
        with st.spinner('72 günlük veri dahil tüm seçilen çekilişler inceleniyor...'):
            try:
                result=run_study(draws,include_partial=partial,progress=progress)
                digest=hashlib.sha256(str([(r['no'],r['day'],r['pos'],r['mask']) for r in draws]).encode()).hexdigest()
                st.session_state['v33_ready']=(digest,partial,*result)
                bar.progress(1.,text='V33 tek ZIP hazır')
            except Exception as exc:st.error(f'V33 hatası: {exc}')
    saved=st.session_state.get('v33_ready')
    if not saved:return
    digest,was_partial,zipped,summary,matrix,placements,daily=saved
    now=hashlib.sha256(str([(r['no'],r['day'],r['pos'],r['mask']) for r in draws]).encode()).hexdigest()
    if was_partial!=partial or now!=digest:
        st.warning('ZIP önceki veri veya seçeneklerle hazırlanmıştır; yeniden analiz başlat.')
    st.download_button('⬇️ V33 6–10 BEKLEYEN TÜM HAVUZLAR TEK ZIP',
        data=zipped,file_name='V33_6_7_8_9_10_BEKLEYEN_HAVUZLAR_TEK_ZIP.zip',
        mime='application/zip',type='primary',use_container_width=True,key='v33_zip')
    st.success(f"{summary['tam_gun']} tam gün · {summary['cekilis']} çekiliş · "
               f"Çekiliş başına ortalama {summary['her_cekiliste_ortalama_6_uzeri']} sayı, 6+ beklemede.")
    st.markdown('#### Her gün sınıfa giren farklı sayı / bir çekilişte mevcut')
    st.dataframe(summary['siniflar'],hide_index=True,use_container_width=True)
    st.markdown('#### Hangi alt havuzlarda duruyorlar?')
    st.dataframe(placements,hide_index=True,use_container_width=True)
    st.markdown('#### Sonraki çekilişte geri dönüş (test dönemi)')
    test=[r for r in matrix if r['donem']=='TEST' and r['grup']=='TUMU']
    st.dataframe(test,hide_index=True,use_container_width=True)
    with st.expander('Test dönemi ısı sınıfı ve bant detayları'):
        st.dataframe([r for r in matrix if r['donem']=='TEST' and r['grup']!='TUMU'],
                     hide_index=True,use_container_width=True)
    with st.expander('80 sayının günlük 6+ sınıfına girişi'):
        st.dataframe(daily,hide_index=True,use_container_width=True)
    st.caption('Sonraki çekiliş sonuçları sadece değerlendirmede kullanılır. '
               '20/80 oyunda tek sayının normal çıkma şansı %25; '
               'bekleme uzunluğu bunu kendiliğinden yükseltmez.')
