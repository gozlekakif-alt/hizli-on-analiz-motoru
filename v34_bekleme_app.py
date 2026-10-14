# -*- coding: utf-8 -*-
"""V34 UI: compare 8-wait cold unseen vs other 8-wait, 6-11+ grid."""
from v32_35_draw_fingerprint import draw_fingerprint
import streamlit as st
from v34_bekleme_isi_v32_kesisim import run_cross


def render_v34(draws):
    st.subheader('🔬 V34 — 8 Bekleyen + Soğuk + V32 Döngü Kesişimi')
    st.info('Özel hedefimiz: **8 gerçek çekiliş çıkmayan**, V28 altı ısı sınıfından '
            '**SOGUK** olan ve V32 çıkan20 döngüsünde **henüz görülmeyen** sayılar. '
            'Bunları diğer 8 çekiliş bekleyenlerle gerçek bir sonraki çekilişte karşılaştırıyoruz.')
    st.caption('Ayrıca 6,7,8,9,10,11+ × altı sıcaklık × V32 görüldü/görülmedi × '
               'sekiz 10’luk bant ilişkilerini kayıt altına alır. '
               'İlk 36 gün keşif, son 36 gün test; 95% gün-blok tekrar örnekleme aralığı.')
    daycount={}
    for row in draws:daycount.setdefault(row['day'],set()).add(int(row['pos']))
    complete=sum(len(v)==217 and v==set(range(1,218)) for v in daycount.values())
    a,b,c=st.columns(3)
    a.metric('Tam gün',complete)
    b.metric('Eksik gün',len(daycount)-complete)
    c.metric('Kayıtlı çekiliş',len(draws))
    partial=st.checkbox('Eksik günleri de dahil et (sahte çekiliş yok)',
                        value=False,key='v34_partial')
    reps=st.select_slider('Gün temelli belirsizlik tekrarı',options=[400,1000,2000,4000],
                          value=2000,key='v34_reps')
    signature=draw_fingerprint(draws)
    if st.button('▶️ V34 SOĞUK–BEKLEME–DÖNGÜ DERİN ÇAPRAZ ANALİZİ',
                 type='primary',use_container_width=True,
                 disabled=not draws or (not partial and complete==0),key='v34_run'):
        bar=st.progress(0,text='80 sayı için geçmiş kayıtları inceliyorum')
        status=st.empty()
        def notify(n,total,stage,day):
            ratio=min(0.95,n/max(1,total))
            bar.progress(ratio,text=f'%{int(100*ratio)} — {stage}')
            status.caption(f'{day} • {n}/{total}')
        with st.spinner('V33 sınıfları, 8 bekleyen özel kesişim ve 36 günlük test hazırlanıyor...'):
            try:
                result=run_cross(draws,include_partial=partial,reps=reps,progress=notify)
                st.session_state['v34_ready']=(signature,partial,reps,*result)
                bar.progress(1.,text='100% — V34 tek ZIP hazır')
            except Exception as exc:st.error(f'V34 analiz hatası: {exc}')
    saved=st.session_state.get('v34_ready')
    if not saved:return
    oldsig,oldpartial,oldreps,blob,meta,comparisons,summary,ranking=saved
    if oldsig!=signature or oldpartial!=partial or oldreps!=reps:
        st.warning('Rapor önceki çekiliş veya seçeneklere ait. Güncel sonuç için tekrar başlat.')
    st.download_button('⬇️ V34 + V33 TÜM ÇAPRAZ HAVUZLAR — TEK ZIP',
            data=blob,file_name='V34_8_BEKLEME_SOGUK_V32_KESISIM_TEK_ZIP.zip',
            mime='application/zip',type='primary',use_container_width=True,key='v34_zip')
    primary=meta.get('test_birincil_karsilastirma')
    if primary:
        st.markdown('#### Ana karşılaştırma — SON 36 GÜN')
        a,b,c=st.columns(3)
        a.metric('Hedefin yeniden gelişi',f"{primary['hedef_yuzde']}%")
        b.metric('Diğer 8 bekleyenler',f"{primary['diger_yuzde']}%")
        c.metric('Fark (yüzde puanı)',str(primary['fark_yuzde_puan']))
        st.caption(f"Gün-blok yaklaşık 95% aralık: "
                   f"{primary['gun_blok_bootstrap_alt_95']} ila "
                   f"{primary['gun_blok_bootstrap_ust_95']} yüzde puanı. "
                   "Sıfırı içeren aralık belirgin üstünlük göstermez.")
    st.dataframe([r for r in comparisons if r['donem']=='TEST'],
                 hide_index=True,use_container_width=True)
    with st.expander('6–11+ tüm ısı × V32 havuz kesişimleri'):
        st.dataframe([r for r in summary if r['donem']=='TEST'],
                     hide_index=True,use_container_width=True)
    with st.expander('Yalnız eğitim günlerinden seçilen sekiz sinyalin test performansı'):
        st.dataframe(ranking,hide_index=True,use_container_width=True)
    st.caption('Test sonuçları giriş özelliklerine dahil edilmez. '
               'Normal 20/80 RNG altında bekleme süresinden bağımsız şans %25; '
               'çoklu tarama ve tekrar kullanılan geçmiş veriye karşı dikkatli olun.')
