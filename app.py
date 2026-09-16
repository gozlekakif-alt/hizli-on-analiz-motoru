import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path

st.set_page_config(page_title="Hızlı On Aile Araştırma Laboratuvarı V2.1 FIX", layout="wide")
st.title("🧬 Hızlı On — Aile Araştırma Laboratuvarı V2.1 FIX")
st.caption("Amaç: 2/3/4/5'li aileleri önce kendi yaşam iziyle tanımak; kupon üretmek değil, kural kütüğü hazırlamak.")

@st.cache_data(show_spinner=False)
def load_data(path):
    rows=[]
    with open(path,encoding='utf-8') as f:
        for line in f:
            p=line.strip().split(';')
            if len(p)!=3: continue
            nums=tuple(sorted(map(int,p[2].split(','))))
            if len(nums)!=20: continue
            rows.append((int(p[0]),pd.to_datetime(p[1],dayfirst=True),nums))
    df=pd.DataFrame(rows,columns=['draw','dt','nums']).sort_values('dt').reset_index(drop=True)
    df['date']=df.dt.dt.date.astype(str); df['hour']=df.dt.dt.hour; df['minute']=df.dt.dt.minute
    df['day_el']=df.groupby('date').cumcount()+1
    return df

@st.cache_data(show_spinner=False)
def counts_for_size(nums_col, k):
    c=Counter()
    for nums in nums_col:
        c.update(combinations(nums,k))
    return c

def occurrences(df, fam):
    fs=set(fam); mask=df.nums.map(lambda x: fs.issubset(x))
    x=df.loc[mask,['draw','dt','date','hour','day_el']].copy()
    x['global_el']=x.index+1
    x=x.reset_index(drop=True)
    if len(x):
        x['prev_global_el']=x.global_el.shift(1)
        x['gap_el']=x.global_el.diff().astype('Int64')
        x['skipped_el']=(x.gap_el-1).astype('Int64')
        x['same_day_prev']=x.date.eq(x.date.shift(1))
        x.loc[~x.same_day_prev,['gap_el','skipped_el']]=pd.NA
    return x

def max_burst(pos, window=12):
    if not pos: return 0, None
    best=(1,(pos[0],pos[0])); j=0
    for i,p in enumerate(pos):
        while p-pos[j]>=window: j+=1
        n=i-j+1
        if n>best[0]: best=(n,(pos[j],p))
    return best

def classify_gap(g):
    if pd.isna(g): return 'başlangıç/gün değişimi'
    s=int(g)-1
    if s==0:return 'art arda'
    if s==1:return '1 el atlama'
    if s==2:return '2 el atlama'
    if s<=5:return '3–5 el uyku'
    if s<=11:return '6–11 el uyku'
    return '12+ el uzun uyku'

path=Path('veri.txt')
if not path.exists(): path=Path(__file__).with_name('veri.txt')
df=load_data(str(path))
if df.empty: st.error('veri.txt okunamadı'); st.stop()

c1,c2,c3,c4,c5=st.columns(5)
c1.metric('Çekiliş',len(df)); c2.metric('Gün',df.date.nunique()); c3.metric('Başlangıç',str(df.dt.min())); c4.metric('Bitiş',str(df.dt.max())); c5.metric('Sayı/çekiliş',20)

tabs=st.tabs(['🔎 Aile Kimliği','🏆 En Çok Oluşanlar','🕒 Saat/Gün','🌱 Büyüme Ağacı','🔁 Devir/Üye Değişimi','📚 Yan Kaynaklar','🧾 Kural Kütüğü'])

with tabs[0]:
    st.subheader('Bir aileyi kendi yaşam iziyle aç')
    size=st.radio('Aile boyutu',[2,3,4,5],horizontal=True)
    raw=st.text_input('Aile sayıları', value='21,57,65' if size==3 else '')
    try: fam=tuple(sorted({int(x.strip()) for x in raw.split(',') if x.strip()}))
    except: fam=()
    if len(fam)==size and all(1<=x<=80 for x in fam):
        o=occurrences(df,fam)
        st.write(f'**Aile:** {"-".join(map(str,fam))}  •  **14 gün toplam:** {len(o)}')
        if len(o):
            same=o[o.same_day_prev]
            med=float(same.gap_el.median()) if len(same) else np.nan
            a,b,c,d=st.columns(4)
            a.metric('İlk oluşum',o.iloc[0]['dt'].strftime('%d.%m %H:%M'))
            b.metric('2. oluşum',o.iloc[1]['dt'].strftime('%d.%m %H:%M') if len(o)>1 else '—')
            c.metric('Aynı gün medyan dönüş',f'{med:.1f} el' if not np.isnan(med) else '—')
            burst,span=max_burst(o.global_el.tolist(),12); d.metric('12 elde max buluşma',burst)
            show=o.copy(); show['ritim']=show.gap_el.map(classify_gap)
            st.dataframe(show[['draw','dt','day_el','gap_el','skipped_el','ritim']],use_container_width=True,hide_index=True)
            st.subheader('Geliş zinciri')
            chain=' → '.join('G'+str(i+1)+(f' (+{int(g)} el)' if not pd.isna(g) else '') for i,g in enumerate(o.gap_el))
            st.code(chain)
            h=o.groupby('hour').size().rename('olusum').reset_index(); st.bar_chart(h.set_index('hour'))
        else: st.info('Bu aile 14 günde oluşmamış.')
    else: st.info(f'{size} farklı sayı girin. Örn: 21,57,65')

with tabs[1]:
    st.subheader('En çok oluşan aileler')
    k=st.selectbox('Boyut',[2,3,4],key='topk')
    n=st.slider('Kaç aile gösterilsin?',10,200,50,10)
    with st.spinner(f'{k}li aileler sayılıyor...'):
        cc=counts_for_size(tuple(df.nums),k)
    top=pd.DataFrame([{'aile':'-'.join(map(str,f)),'toplam':v} for f,v in cc.most_common(n)])
    st.dataframe(top,use_container_width=True,hide_index=True)
    st.download_button('CSV indir',top.to_csv(index=False).encode('utf-8-sig'),f'top_{k}lu_aile.csv','text/csv')
    st.caption("5'li kombinasyonların tamamını bellekte saymak çok ağırdır. 5'li aileleri 'Aile Kimliği' ekranında tek tek veya Büyüme Ağacı üzerinden inceliyoruz; böylece uygulama çökmez.")

with tabs[2]:
    st.subheader('Saat ve gün karakteri')
    day=st.selectbox('Gün',['Tümü']+sorted(df.date.unique().tolist()))
    dd=df if day=='Tümü' else df[df.date==day]
    st.dataframe(dd.groupby(['date','hour']).size().rename('cekilis').reset_index(),use_container_width=True,hide_index=True)
    st.caption('Seçili ailenin saat dağılımı Aile Kimliği ekranında ayrıca gösterilir.')

with tabs[3]:
    st.subheader('2→3→4→5 büyüme ağacı')
    raw2=st.text_input('Çekirdek (2–4 sayı)',value='21,57',key='core')
    try: core=tuple(sorted({int(x.strip()) for x in raw2.split(',') if x.strip()}))
    except: core=()
    if 2<=len(core)<=4:
        base=occurrences(df,core)
        st.write(f'Çekirdek **{"-".join(map(str,core))}** toplam {len(base)} kez birlikte.')
        candidates=[]
        for x in range(1,81):
            if x in core: continue
            fam=tuple(sorted(core+(x,))); n=len(occurrences(df,fam))
            if n: candidates.append((x,n))
        cand=pd.DataFrame(candidates,columns=['eklenen_uye','birlikte_olusum']).sort_values('birlikte_olusum',ascending=False)
        st.dataframe(cand.head(40),use_container_width=True,hide_index=True)
        st.download_button('Büyüme adaylarını CSV indir',cand.to_csv(index=False).encode('utf-8-sig'),'buyume_agaci.csv','text/csv')

with tabs[4]:
    st.subheader('Üye değişimi / kardeş aile taraması')
    st.write('Bir çekirdek seçildiğinde Büyüme Ağacı tablosundaki farklı ek üyeler, aynı çekirdeğin kardeş ailelerini gösterir. Zaman sırası için aday üyeyi Aile Kimliği ekranında açıp geliş zincirlerini karşılaştırın.')
    st.info('V1 araştırma laboratuvarı burada önce gözlem üretir; otomatik “güçlü/zayıf” hükmü vermez. Bu sınıflandırma kural kütüğü dondurulurken eklenecek.')

with tabs[5]:
    st.subheader('Araştırmaya yardımcı yan kaynaklar')
    refs=pd.DataFrame([
      ['Aile yaşam master','HIZLI_ON_14_GUN_AILE_YASAM_MASTER_V1_3-1.txt','Burst/span ve kısa yaşam kayıtlarını karşılaştır.'],
      ['20 sayı aile kadavra','20_SAYI_AILE_ANATOMISI_ARDISIK_ATLAMALI_TEKIL_FREKANS_434.xlsx','Ardışık/atlamalı blok ve tekil geometri.'],
      ['H1–H8 kadavra','H1_H8_KADAVRA_MASTER_V2-1.txt','Aile üyelerinin H1–H8 yaş/taşıma durumunu bağlamak için.'],
      ['800 salınım','800_SALINIM_08_EYLUL_TEST.csv','Yalnız yardımcı bağlam; aile kararını tek başına vermesin.']
    ],columns=['kaynak','dosya','görev'])
    st.dataframe(refs,use_container_width=True,hide_index=True)
    st.caption('Bu ZIP yalnız ham 14 günlük veri.txt içerir. Yukarıdaki yan kaynaklar elinizdeyse sonraki sürümde yükleme panelinden birleştirilecek.')

with tabs[6]:
    st.subheader('45 maddelik araştırma → kural kütüğü')
    items=['Aile kimliği','Toplam yaşam','Doğum','İkinci geliş','Bütün geliş zinciri','Ritim karakteri','Ritim tekrarı','Burst/patlama','Aktif yaşam süresi','Uyku ve geri dönüş','Ölüm','Saat karakteri','Saat geçişi','Gün karakteri','2→3 büyüme','3→4 büyüme','4→5 büyüme','Ters küçülme','Ana çekirdek','Değişken üye','Üye değişimi','Devir/handoff','Aile ağacı','Kardeş aileler','Rakip aileler','Birlikte aktif aileler','Ardışık geometri','Atlamalı geometri','Ardışık uzunluk','Atlamalı uzunluk','1–80 tekil yaşamı','H1–H8 desteği','Taşıma','Aile yaşı','Saat içi faz','Günün fazı','Toplam/bant yardımcıları','NEGATIVE60 karşılığı','Aile öncesi 1–6 el','Aile sonrası 1–6 el','Özgün aile profili','Karakter sınıfları','Rastlantı kontrolü','Zaman-dağılım motoru','Dondurulmuş kural kütüğü']
    status=['AKTİF' if i in [0,1,2,3,4,5,7,11,14,15,16,18,19,20,22,23,41] else 'SONRAKİ KATMAN' for i in range(45)]
    plan=pd.DataFrame({'No':range(1,46),'Araştırma':items,'V1 Durum':status})
    st.dataframe(plan,use_container_width=True,hide_index=True)
    st.download_button('45 madde planını CSV indir',plan.to_csv(index=False).encode('utf-8-sig'),'45_madde_aile_arastirma_plani.csv','text/csv')
    st.warning('Kupon motoru bu laboratuvardan ayrı tutulur. Önce kurallar dondurulur; sonra ileri/kör doğrulama; yalnız doğrulanan kurallar kupon üreticiye geçer.')

# --- V2: Ardışık ve atlamalı aile yaşam motorları ---
def geom_family_occurrences(df, fam):
    return occurrences(df, tuple(fam))

def consecutive_families_in_draw(nums, k):
    s=set(nums); out=[]
    for a in range(1, 82-k):
        fam=tuple(range(a,a+k))
        if set(fam).issubset(s): out.append(fam)
    return out

def stepped_families_in_draw(nums, k, step=2):
    s=set(nums); out=[]
    max_start=80-step*(k-1)
    for a in range(1,max_start+1):
        fam=tuple(a+step*i for i in range(k))
        if set(fam).issubset(s): out.append(fam)
    return out

st.divider()
st.header('🧬 V2 — Geometrik Aile Uzmanları')
st.caption('Serbest aileden ayrı çalışır: ardışık aile ve atlamalı aile kendi yaşam zinciriyle incelenir.')
gtabs=st.tabs(['🔗 Ardışık Aile','⏭️ Atlamalı Aile','🌱 Geometrik Büyüme'])

with gtabs[0]:
    k=st.radio('Ardışık aile boyutu',[2,3,4,5],horizontal=True,key='con_k')
    start=st.number_input('Başlangıç sayısı',min_value=1,max_value=81-k,value=min(18,81-k),step=1,key='con_start')
    fam=tuple(range(int(start),int(start)+k))
    o=geom_family_occurrences(df,fam)
    st.write(f'**Ardışık aile:** {"-".join(map(str,fam))} • **14 gün toplam:** {len(o)}')
    if len(o):
        show=o.copy(); show['ritim']=show.gap_el.map(classify_gap)
        st.dataframe(show[['draw','dt','day_el','gap_el','skipped_el','ritim']],use_container_width=True,hide_index=True)
        st.code(' → '.join('G'+str(i+1)+(f' (+{int(g)} el)' if not pd.isna(g) else '') for i,g in enumerate(o.gap_el)))
        hh=o.groupby('hour').size().rename('olusum').reset_index(); st.bar_chart(hh.set_index('hour'))
    st.caption('Örnek: 18-19, 18-19-20, 18-19-20-21 gibi aynı geometrik soy ayrı aile kimliği taşır.')

with gtabs[1]:
    k=st.radio('Atlamalı aile boyutu',[2,3,4,5],horizontal=True,key='step_k')
    step=st.selectbox('Adım',[2,3],index=0,key='step_n')
    max_start=80-step*(k-1)
    start=st.number_input('Başlangıç sayısı',min_value=1,max_value=max_start,value=min(10,max_start),step=1,key='step_start')
    fam=tuple(int(start)+step*i for i in range(k))
    o=geom_family_occurrences(df,fam)
    st.write(f'**Atlamalı aile:** {"-".join(map(str,fam))} • **14 gün toplam:** {len(o)}')
    if len(o):
        show=o.copy(); show['ritim']=show.gap_el.map(classify_gap)
        st.dataframe(show[['draw','dt','day_el','gap_el','skipped_el','ritim']],use_container_width=True,hide_index=True)
        st.code(' → '.join('G'+str(i+1)+(f' (+{int(g)} el)' if not pd.isna(g) else '') for i,g in enumerate(o.gap_el)))
        hh=o.groupby('hour').size().rename('olusum').reset_index(); st.bar_chart(hh.set_index('hour'))

with gtabs[2]:
    st.write('Ardışık ve atlamalı ailelerde büyüme/küçülmeyi aynı soy üzerinden karşılaştırır.')
    typ=st.selectbox('Soy',['Ardışık (+1)','Atlamalı (+2)'],key='grow_geom')
    step=1 if typ.startswith('Ardışık') else 2
    start=st.number_input('Soy başlangıcı',1,70,18,key='grow_start')
    rows=[]
    for k in range(2,6):
        fam=tuple(int(start)+step*i for i in range(k))
        if fam[-1] > 80: continue
        o=occurrences(df,fam)
        burst,_=max_burst(o.global_el.tolist(),12) if len(o) else (0,None)
        rows.append({'boyut':k,'aile':'-'.join(map(str,fam)),'14_gun_toplam':len(o),'12_el_max_burst':burst,
                     'ilk':o.iloc[0]['dt'] if len(o) else pd.NaT,'son':o.iloc[-1]['dt'] if len(o) else pd.NaT})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
