import streamlit as st
import pandas as pd
import numpy as np
import sqlite3, io, re
from itertools import combinations
from collections import Counter, defaultdict

st.set_page_config(page_title='Hızlı On — Aile Yaşam Laboratuvarı', layout='wide')
st.title('🧬 Hızlı On — Aile Yaşam Laboratuvarı V2')
st.caption('Sadece analiz: kupon üretmez. 2–10’lu ailelerin gün/saat/çok-gün yaşamını inceler.')

@st.cache_data(show_spinner=False)
def parse_data(raw: bytes):
    text=raw.decode('utf-8',errors='ignore')
    rows=[]
    for ln in text.splitlines():
        p=ln.strip().split(';')
        if len(p)>=3:
            try:
                did=int(re.sub(r'\D','',p[0])); dt=pd.to_datetime(p[1],dayfirst=True)
                nums=tuple(sorted(map(int,re.findall(r'\d+',p[2]))))
                if len(nums)==20 and len(set(nums))==20: rows.append((did,dt,nums))
            except: pass
    return pd.DataFrame(rows,columns=['draw_id','dt','numbers']).sort_values('dt').reset_index(drop=True)

def family_occurrences(df, family):
    fs=set(family)
    return df[df.numbers.map(lambda x: fs.issubset(x))][['draw_id','dt','numbers']].copy()

@st.cache_data(show_spinner=False)
def pair_matrix(df):
    c=Counter()
    for nums in df.numbers:
        for a,b in combinations(nums,2): c[(a,b)]+=1
    mat=np.zeros((80,80),dtype=int)
    for (a,b),v in c.items(): mat[a-1,b-1]=mat[b-1,a-1]=v
    return mat,c

@st.cache_data(show_spinner=False)
def hourly_partners(df, anchor, topn=8):
    rec=[]
    for h,g in df.groupby(df.dt.dt.floor('h')):
        cc=Counter()
        for nums in g.numbers:
            if anchor in nums:
                for n in nums:
                    if n!=anchor: cc[n]+=1
        for n,v in cc.most_common(topn): rec.append((h,anchor,n,v,len(g)))
    return pd.DataFrame(rec,columns=['hour','anchor','partner','together','draws_in_hour'])

@st.cache_data(show_spinner=False)
def daily_partners(df, anchor, topn=10):
    rec=[]
    for d,g in df.groupby(df.dt.dt.date):
        cc=Counter()
        for nums in g.numbers:
            if anchor in nums:
                for n in nums:
                    if n!=anchor: cc[n]+=1
        for n,v in cc.most_common(topn): rec.append((str(d),anchor,n,v,len(g)))
    return pd.DataFrame(rec,columns=['day','anchor','partner','together','draws_in_day'])

@st.cache_data(show_spinner=False)
def persistence(df, anchor):
    # pair life across days: active days, first/last, max daily, total
    tmp=defaultdict(lambda: defaultdict(int))
    for _,r in df.iterrows():
        nums=r["numbers"]
        if anchor in nums:
            draw_dt=pd.to_datetime(r["dt"], errors="coerce")
            if pd.isna(draw_dt):
                continue
            d=str(draw_dt.date())
            for n in nums:
                if n!=anchor: tmp[n][d]+=1
    out=[]
    for n,days in tmp.items():
        vals=list(days.values()); keys=sorted(days)
        out.append((n,sum(vals),len(days),keys[0],keys[-1],max(vals),np.mean(vals)))
    return pd.DataFrame(out,columns=['partner','total_together','active_days','first_day','last_day','max_in_day','avg_active_day']).sort_values(['active_days','total_together'],ascending=False)

@st.cache_data(show_spinner=False)
def family_table(df, k, min_occ=2, cap=None):
    # Exact exhaustive family counting. k>=8 can be very large; allow row cap by recent draws.
    work=df if cap is None else df.tail(cap)
    c=Counter()
    for nums in work.numbers:
        for fam in combinations(nums,k): c[fam]+=1
    rows=[(fam,v) for fam,v in c.items() if v>=min_occ]
    rows.sort(key=lambda x:(-x[1],x[0]))
    return pd.DataFrame(rows,columns=['family','occurrences'])

from pathlib import Path

DATA_FILE = Path(__file__).with_name("veri.txt")

# GitHub/Streamlit ana kaynak: repo içindeki veri.txt otomatik okunur.
# veri.txt yoksa yalnızca yedek olarak manuel yükleme açılır.
if DATA_FILE.exists():
    raw_data = DATA_FILE.read_bytes()
    data_source = f"GitHub MASTER: {DATA_FILE.name}"
else:
    st.warning("Repo içinde veri.txt bulunamadı. Yedek olarak TXT yükleyebilirsin.")
    up = st.file_uploader("TXT veri dosyası", type=["txt"])
    if not up:
        st.info("GitHub reposunda app.py ile veri.txt aynı klasörde olmalı. Format: çekiliş_no;tarih saat;1,2,...,20")
        st.stop()
    raw_data = up.getvalue()
    data_source = "Manuel TXT"

df = parse_data(raw_data)
if "dt" in df.columns:
    df["dt"] = pd.to_datetime(df["dt"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["dt"]).copy()
if df.empty:
    st.error("veri.txt bulundu fakat geçerli çekiliş okunamadı.")
    st.stop()

# Aynı çekiliş yanlışlıkla iki kez eklenmişse analizde tek kayıt kullan.
df = (df.sort_values(["dt","draw_id"])
        .drop_duplicates(subset=["draw_id"], keep="last")
        .reset_index(drop=True))

st.success(f"Veri otomatik tanındı — {data_source} — {len(df):,} çekiliş".replace(",", "."))

c1,c2,c3,c4=st.columns(4)
c1.metric('Çekiliş',f'{len(df):,}'.replace(',','.'))
c2.metric('İlk',str(df.dt.min()))
c3.metric('Son',str(df.dt.max()))
c4.metric('Gün',df.dt.dt.date.nunique())

tabs=st.tabs(['🤝 Çift aile / flört','🕐 Saatlik değişim','📅 Günlük kalıcılık','🧬 2–10 aile tarama','🔎 Aile kadavrası','📤 Rapor'])

with tabs[0]:
    st.subheader('Bir sayının kimlerle yaşadığını gör')
    anchor=st.number_input('Ana sayı',1,80,3,key='a1')
    mat,c=pair_matrix(df)
    vals=[(n,int(mat[anchor-1,n-1])) for n in range(1,81) if n!=anchor]
    vals.sort(key=lambda x:-x[1])
    st.dataframe(pd.DataFrame(vals[:30],columns=['partner','birlikte_çekiliş']),use_container_width=True,hide_index=True)

with tabs[1]:
    anchor=st.number_input('Saatlik ana sayı',1,80,3,key='a2')
    topn=st.slider('Saat başına gösterilecek partner',3,20,8)
    hp=hourly_partners(df,anchor,topn)
    st.dataframe(hp,use_container_width=True,hide_index=True)
    if not hp.empty:
        pivot=hp.pivot_table(index='hour',columns='partner',values='together',fill_value=0)
        st.line_chart(pivot)
    st.caption('Bu ekran 3–39 gün boyu sürüyor mu, yoksa 3 saat içinde başka partnerlere mi kayıyor sorusunu gösterir.')

with tabs[2]:
    anchor=st.number_input('Günlük ana sayı',1,80,3,key='a3')
    dp=daily_partners(df,anchor,10)
    ps=persistence(df,anchor)
    st.markdown('**Gün gün en güçlü partnerler**')
    st.dataframe(dp,use_container_width=True,hide_index=True)
    st.markdown('**Çok-gün kalıcılık / 6 gün sonra geri dönüş için temel tablo**')
    st.dataframe(ps.head(40),use_container_width=True,hide_index=True)

with tabs[3]:
    st.warning('2–7 tam ayda rahat çalışır. 8–10 kombinasyon sayısı çok büyüdüğü için önce filtreli/recent tarama önerilir.')
    k=st.slider('Aile büyüklüğü',2,10,3)
    minocc=st.number_input('En az tekrar',2,20,2)
    cap=None
    if k>=8:
        cap=st.number_input('Son kaç çekilişi tara? (performans koruması)',50,min(len(df),2000),min(len(df),500),50)
    if st.button('Aileleri tara',type='primary'):
        with st.spinner('Aileler sayılıyor...'):
            ft=family_table(df,k,int(minocc),cap)
        st.session_state['ft']=ft
    if 'ft' in st.session_state:
        st.metric('Bulunan aile',len(st.session_state.ft))
        st.dataframe(st.session_state.ft.head(500),use_container_width=True,hide_index=True)

with tabs[4]:
    raw=st.text_input('Aileyi yaz (örn. 3,39 veya 3,12,39,46,66,75)', '3,39')
    try: fam=tuple(sorted(set(map(int,re.findall(r'\d+',raw)))))
    except: fam=()
    if 2<=len(fam)<=10 and all(1<=x<=80 for x in fam):
        oc=family_occurrences(df,fam)
        st.write(f'**Aile:** {fam} — **toplam oluşum:** {len(oc)}')
        if len(oc):
            oc['gap']=oc.index.to_series().map(lambda _: np.nan).values
            idx=list(oc.index); gaps=[np.nan]+[idx[i]-idx[i-1] for i in range(1,len(idx))]
            oc['gap_draws']=gaps
            st.dataframe(oc[['draw_id','dt','gap_draws']],use_container_width=True,hide_index=True)
            st.bar_chart(oc.assign(day=oc.dt.dt.date.astype(str)).groupby('day').size())
    else: st.error('2–10 arasında geçerli sayı gir.')

with tabs[5]:
    st.subheader('Analiz dokümanı / CSV dışa aktar')
    anchor=st.number_input('Rapor ana sayısı',1,80,3,key='a4')
    ps=persistence(df,anchor)
    hp=hourly_partners(df,anchor,10)
    dp=daily_partners(df,anchor,10)
    summary=f'''HIZLI ON AILE YASAM LAB RAPORU\nÇekiliş: {len(df)}\nTarih: {df.dt.min()} -> {df.dt.max()}\nAna sayı: {anchor}\n\nAMAÇ\n2–10 ailelerin gün, saat ve çok-gün yaşamını keşfetmek. Kupon üretmez.\n\nKALICI PARTNERLER\n{ps.head(30).to_string(index=False)}\n\nSAATLIK PARTNERLER\n{hp.head(200).to_string(index=False)}\n\nGUNLUK PARTNERLER\n{dp.head(200).to_string(index=False)}\n'''
    st.download_button('TXT raporu indir',summary,file_name=f'aile_yasam_raporu_{anchor}.txt')
    st.download_button('Kalıcılık CSV indir',ps.to_csv(index=False).encode('utf-8-sig'),file_name=f'aile_kalicilik_{anchor}.csv')

st.divider()
st.caption('V2 analiz laboratuvarıdır. GitHub reposundaki veri.txt dosyasını otomatik tanır. Kupon üretmez.')
