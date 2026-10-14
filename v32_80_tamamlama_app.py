# -*- coding: utf-8 -*-
"""V32 UI: one-click complete 80/80 appearance and absence cycle export."""
import hashlib
import streamlit as st
from v32_80_tamamlama import analyze


def render_v32(draws):
    st.subheader('🔁 V32 — 80 Sayının Tamamlanma Döngüsü')
    st.info('İki bağımsız sayaç: **çıkan 20 içinde 80/80** ve **çıkmayan 60 içinde 80/80**. '
            '80 sayı tamamlandığı çekilişte döngü kapanır ve sonraki gerçek çekilişte sıfırdan başlar. '
            'Her gün 00:02 yeni başlangıçtır; 01:02 → 07:02 arasında çekiliş yoktur.')
    st.caption('Hangi döngü 7, 8, 20 veya daha fazla çekilişte tamamlandı? '
               '1, 2, 3, 4... çekilişte kaç yeni sayı geldi? '
               'İlk gelenler, geç gelenler, 8×10 bant, saat, tekrar ve RNG kontrolü tek raporda.')
    count={}
    for row in draws:
        count.setdefault(row['day'],set()).add(row['pos'])
    complete=sum(len(v)==217 and v==set(range(1,218)) for v in count.values())
    a,b,c=st.columns(3)
    a.metric('217/217 tam gün',complete)
    b.metric('Eksik gün',len(count)-complete)
    c.metric('Kayıtlı çekiliş',len(draws))
    partial=st.checkbox('Eksik günleri de dahil et (eksik aralıkta sayaç kesilir)',value=False,key='v32_partial')
    repeats=st.select_slider('Bağımsız RNG karşılaştırma tekrarı',options=[0,10,30,100],value=30,key='v32_rng')
    st.caption('Tam günler seçildiğinde eksik verili günler hesaplamaya girmez. '
               'Gün sonu açık döngüler tamamlanmış sayılmaz. RNG yalnızca kontrol grubudur; kupon vaadi değildir.')
    if st.button('▶️ V32 BÜTÜN DÖNGÜLERİ ANALİZ ET — TEK ZIP',type='primary',
                 use_container_width=True,disabled=not draws or (not partial and complete==0),key='v32_run'):
        progress=st.progress(0,text='80 sayı döngüleri hesaplanıyor')
        status=st.empty()
        def notify(done,all_steps,stage,day):
            if stage.startswith('Gerçek'):
                pct=min(.7,.7*done/max(1,all_steps))
            else:
                pct=.7+.3*done/max(1,all_steps)
            progress.progress(pct,text=f'{int(100*pct)}% — {stage}')
            status.caption(f'{stage} · {done}/{all_steps}' + (f' · {day}' if day else ''))
        with st.spinner('Bütün kayıtlı günleri sıra sıra tarıyorum...'):
            try:
                zipped,meta,cycles,hist,comparison=analyze(
                    draws,include_partial=partial,rng_reps=repeats,progress=notify)
                signature=hashlib.sha256(str([(r['no'],r['day'],r['pos']) for r in draws]).encode()).hexdigest()
                st.session_state['v32_ready']=(signature,partial,repeats,zipped,meta,cycles,hist,comparison)
                progress.progress(1.,text='100% — ZIP raporu hazır')
            except Exception as exc:
                st.error(f'V32 analiz hatası: {exc}')
    saved=st.session_state.get('v32_ready')
    if saved:
        signature,was_partial,was_repeats,zipped,meta,cycles,hist,comparison=saved
        if was_partial!=partial or was_repeats!=repeats:
            st.warning('İndirme dosyası önceki seçeneklerle hazırlanmıştır. Yeni seçenekleri kullanmak için yeniden çalıştır.')
        st.success('80 sayı döngüsü analizi tamamlandı. Bütün detaylar tek ZIP içinde.')
        st.download_button('⬇️ V32 — TAM ANALİZ TEK ZIP İNDİR',
            data=zipped,file_name='V32_80_SAYI_TAMAMLANMA_TEK_RAPOR.zip',
            mime='application/zip',type='primary',use_container_width=True,key='v32_zip')
        a,b,c=st.columns(3)
        a.metric('İncelenen çekiliş',meta['cekilis_sayisi'])
        b.metric('Çıkan 20 → 80/80',meta['tamamlanan_cikan20_dongusu'])
        c.metric('Çıkmayan 60 → 80/80',meta['tamamlanan_cikmayan60_dongusu'])
        st.write('**Tamamlanan döngülerin ortalama uzunluğu (çekiliş):**',
                 'Çıkan 20:',meta['cikan20_ortalama_adim'],
                 '| Çıkmayan 60:',meta['cikmayan60_ortalama_adim'])
        if comparison:
            st.caption('Bağımsız 20/80 RNG karşılaştırması (referans; istatistiksel üstünlük kanıtı değildir).')
            st.dataframe(comparison,hide_index=True,use_container_width=True)
        st.markdown('#### Döngü tamamlanma süreleri (ilk 40 çekiliş)')
        st.dataframe([r for r in hist if r['adim']<=40],hide_index=True,use_container_width=True)
        st.caption('ZIP içinde her çekilişin gerçek 20 sayısı, 80 sayının ilk görülme adımı, '
                   'açık/tamam döngüler, bantlar, saatler ve RNG kontrol tabloları var.')
