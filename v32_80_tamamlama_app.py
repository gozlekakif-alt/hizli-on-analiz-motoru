# -*- coding: utf-8 -*-
"""V32 Streamlit: exact 80/80 cycles plus 4/8/12 no-lookahead research."""
from v32_35_draw_fingerprint import draw_fingerprint
import streamlit as st
from v32_ileri_karakter import run_deep


def render_v32(draws):
    st.subheader('🔁 V32 — 80 Sayı Tamamlanma Döngüsü ve 4/8/12 Karakter')
    st.info('80 sayının tümü çıkan 20 havuzunda veya çıkmayan 60 havuzunda görülünce, '
            'ilgili sayaç **sonraki çekilişte sıfırlanır**. '
            'Her gün 00:02 yeni başlangıç; 01:02 → 07:02 arasında boşluk vardır.')
    st.caption('İlk dört çekilişten sonra, 8. ve 12. çekilişlerdeki 80/80 yolculuğunu '
        've sonraki 1/4/8/12 gerçek çekilişte tamamlanma durumunu karşılaştırır. '
        'Kesit sinyalleri geleceğe bakmadan hesaplanır.')
    count={}
    for row in draws:
        count.setdefault(row['day'],set()).add(row['pos'])
    complete=sum(len(v)==217 and v==set(range(1,218)) for v in count.values())
    a,b,c=st.columns(3)
    a.metric('217/217 tam gün',complete)
    b.metric('Eksik gün',len(count)-complete)
    c.metric('Kayıtlı çekiliş',len(draws))
    partial=st.checkbox('Eksik günleri de dahil et (aralarda döngüyü kes)',value=False,key='v32_partial')
    repeats=st.select_slider('Bağımsız RNG kontrol tekrarı',options=[0,10,30,100],value=30,key='v32_rng')
    st.caption('Tam günlerden önceki yarı EGITIM; sonraki yarı TEST olarak ayrı raporlanır. '
               'Eksik veri karşılaştırmalarda negatif sonuç sayılmaz. RNG üstünlüğü kanıtı değildir.')
    signature=draw_fingerprint(draws)
    saved=st.session_state.get('v32_ready')
    if saved and saved[0]!=signature:
        st.warning('Yeni çekiliş verisi gelmiş; ZIP önceki veriye ait. Yeniden analiz başlat.')
    if st.button('▶️ V32 80 SAYI + 4/8/12 DERİN ANALİZ — TEK ZIP',type='primary',
                 use_container_width=True,disabled=not draws or (not partial and complete==0),key='v32_run'):
        bar=st.progress(0,text='80 sayı döngüleri hesaplanıyor')
        status=st.empty()
        def notify(done,total,stage,day):
            if stage.startswith('Gerçek'):
                pct=.55*done/max(1,total)
            elif stage.startswith('Bağımsız'):
                pct=.55+.20*done/max(1,total)
            else:
                pct=.75+.25*done/max(1,total)
            bar.progress(min(1.,pct),text=f'%{int(100*pct)} — {stage}')
            status.caption(f'{stage}: {done}/{total}' + (f' · {day}' if day else ''))
        with st.spinner('Gerçek çekilişler, döngüler ve ileriye dönük test hazırlanıyor...'):
            try:
                result=run_deep(draws,include_partial=partial,rng_reps=repeats,progress=notify)
                st.session_state['v32_ready']=(signature,partial,repeats,*result)
                bar.progress(1.,text='%100 — 17 dosyalık tek ZIP hazır')
            except Exception as exc:
                st.error(f'V32 analizi tamamlanamadı: {exc}')
    saved=st.session_state.get('v32_ready')
    if not saved:
        return
    previous_signature,was_partial,was_repeats,zipped,meta,summary,variants,bands,snapshots=saved
    if (was_partial!=partial or was_repeats!=repeats or previous_signature!=signature):
        st.warning('ZIP önceki veriler veya seçeneklerle hazırlandı; güncellemek için yeniden başlat.')
    st.success('V32 derin döngü raporu hazır: ilk 11 orijinal dosya + 6 yeni analiz.')
    st.download_button('⬇️ V32 4–8–12 DERİN ANALİZİ TEK ZIP İNDİR',
        data=zipped,file_name='V32_4_8_12_TEK_ZIP.zip',
        mime='application/zip',type='primary',use_container_width=True,key='v32_zip')
    a,b,c=st.columns(3)
    a.metric('Gerçek çekiliş',meta['cekilis_sayisi'])
    b.metric('Çıkan 20 → 80/80',meta['tamamlanan_cikan20_dongusu'])
    c.metric('4/8/12 kesit',meta['4_8_12_kesit'])
    st.markdown('#### Zaman sıralı test dönemi — çıkan 20 havuzu')
    visible=[r for r in summary if r['donem']=='TEST' and r['havuz']=='CIKAN_20']
    st.dataframe(visible,hide_index=True,use_container_width=True)
    st.markdown('#### Yavaş / orta / hızlı ilk kesit karşılaştırması')
    st.dataframe([r for r in variants if r['donem']=='TEST' and r['havuz']=='CIKAN_20'],
                 hide_index=True,use_container_width=True)
    with st.expander('Eksik sayıların bantları — sonraki gerçek çekiliş isabeti'):
        st.dataframe([r for r in bands if r['donem']=='TEST'],
                     hide_index=True,use_container_width=True)
    with st.expander('4., 8. ve 12. çekiliş anlık kayıtları (ilk 200)'):
        st.dataframe(snapshots[:200],hide_index=True,use_container_width=True)
    st.caption('RNG karşılaştırması, henüz çıkmamış sayılar için teorik ihtimali kullanır. '
               'Bu tablolar RNG algoritmasının çözüldüğünü veya gelecek sayıları bildiğimizi göstermez.')
