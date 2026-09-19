import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import re

st.set_page_config(page_title="Hızlı On — 14 Gün Saatlik Yaşam Haritası", layout="wide")
st.title("Hızlı On — 14 Gün Saatlik Yaşam Haritası")
st.caption("Amaç: 1–80 sayıların saat saat çıkış sayılarını ölçmek; 23:02–23:57 davranışının kapanışa özgü mü, yoksa gün içindeki rutin saatlerin tekrarı mı olduğunu karşılaştırmak.")

DATA_FILE = Path(__file__).with_name("veri.txt")

if not DATA_FILE.exists():
    st.error("veri.txt bulunamadı. GitHub deposunda app dosyasıyla aynı klasöre veri.txt koy.")
    st.stop()

try:
    RAW_DATA = DATA_FILE.read_text(encoding="utf-8-sig")
except UnicodeDecodeError:
    RAW_DATA = DATA_FILE.read_text(encoding="cp1254")

st.sidebar.success(f"Veri kaynağı: {DATA_FILE.name}")

def parse_data(raw):
    rows=[]
    # 1) Ana biçim: draw_id;dd.mm.yyyy HH:MM;n1,n2,...,n20
    for line in raw.splitlines():
        line=line.strip()
        if not line or ';' not in line:
            continue
        try:
            draw_id, dt, nums = line.split(';',2)
            ts=pd.to_datetime(dt.strip(), dayfirst=True)
            ns=[int(x) for x in re.findall(r"\d+", nums)]
            if len(ns)==20 and all(1 <= x <= 80 for x in ns):
                rows.append((int(draw_id.strip()),ts,ns))
        except Exception:
            pass

    # 2) Alternatif Milli Piyango kopyalama biçimi
    if not rows:
        pat=re.compile(r"(?:Çekiliş\s*no\s*:?\s*)?(\d{4,})\s*\n?\s*(\d{2}\.\d{2}\.\d{4})\s*[-–]?\s*(\d{2}:\d{2})(.*?)(?=(?:Çekiliş\s*no\s*:?\s*)?\d{4,}\s*\n?\s*\d{2}\.\d{2}\.\d{4}|$)", re.I|re.S)
        for m in pat.finditer(raw):
            try:
                draw_id=int(m.group(1))
                ts=pd.to_datetime(f"{m.group(2)} {m.group(3)}", dayfirst=True)
                ns=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", m.group(4))]
                # URL/başka metin varsa ilk 20 geçerli sonucu al
                ns=ns[:20]
                if len(ns)==20:
                    rows.append((draw_id,ts,ns))
            except Exception:
                pass

    df=pd.DataFrame(rows, columns=['draw_id','time','numbers'])
    if df.empty:
        return df
    return df.drop_duplicates('draw_id').sort_values('time').reset_index(drop=True)

df=parse_data(RAW_DATA)
if df.empty:
    st.error("veri.txt okundu ama geçerli çekiliş bulunamadı. Beklenen ana biçim: çekiliş_no;tarih saat;20 virgüllü sayı")
    st.stop()

st.sidebar.caption(f"Okunan çekiliş: {len(df):,} | Gün: {df.time.dt.date.nunique()}")
df['date']=df.time.dt.date
df['hour']=df.time.dt.hour

dates=sorted(df.date.unique())
st.sidebar.header("Filtre")
selected_dates=st.sidebar.multiselect("Günler", dates, default=dates, format_func=lambda x: pd.Timestamp(x).strftime('%d.%m.%Y'))
sel=df[df.date.isin(selected_dates)].copy()

# Long form
long=sel[['draw_id','time','date','hour','numbers']].explode('numbers', ignore_index=True).rename(columns={'numbers':'number'})
long['number']=long.number.astype(int)

# Draw counts per hour/date and comparable hours
hour_draws=sel.groupby('hour').size().reindex(range(24), fill_value=0)
comparable_hours=[h for h in range(24) if hour_draws.get(h,0)>0 and h!=1]

c1,c2,c3,c4=st.columns(4)
c1.metric("Çekiliş", len(sel))
c2.metric("Gün", len(selected_dates))
c3.metric("Sayı görünümü", len(long))
c4.metric("23:xx çekilişi", int(hour_draws.get(23,0)))

st.info("Saat 01:00 bloğu yalnız 01:02 çekilişini içerdiği için 23:xx ile doğrudan karşılaştırmada dışarıda bırakılır. Diğer normal saatler çekiliş başına normalize edilir.")

# ---------- TEK TUŞ OTOMATİK 14 GÜN ANALİZİ ----------
def auto_analyze(base_df):
    L=base_df[['draw_id','time','date','hour','numbers']].explode('numbers', ignore_index=True).rename(columns={'numbers':'number'})
    L['number']=L['number'].astype(int)
    out=[]
    day_summ=[]
    all_dates=sorted(base_df['date'].unique())
    for d in all_dates:
        day=base_df[base_df.date==d]
        dl=L[L.date==d]
        hd=day.groupby('hour').size()
        hc=pd.crosstab(dl['number'].to_numpy(), dl['hour'].to_numpy()).reindex(index=range(1,81),columns=range(24),fill_value=0)
        rates=hc.astype(float)
        for h in range(24):
            rates[h]=rates[h]/hd.get(h, np.nan) if hd.get(h,0)>0 else np.nan
        routine=[h for h in list(range(7,23))+[0] if hd.get(h,0)>0]
        zs=[]
        for n in range(1,81):
            vals=rates.loc[n,routine].dropna().to_numpy(dtype=float)
            r23=rates.loc[n,23] if hd.get(23,0)>0 else np.nan
            mu=float(np.mean(vals)) if len(vals) else np.nan
            sd=float(np.std(vals,ddof=1)) if len(vals)>1 else np.nan
            z=(r23-mu)/sd if pd.notna(sd) and sd>0 else np.nan
            zs.append((n,int(hc.loc[n,23]),r23,mu,z))
        zdf=pd.DataFrame(zs,columns=['Sayı','23 çıkış','23 oran','Rutin oran','Z'])
        high=zdf[zdf.Z>=1.5]
        leaders=zdf[zdf['23 çıkış']>=5]
        day_summ.append([pd.Timestamp(d).strftime('%d.%m.%Y'),len(day),len(high),len(leaders),', '.join(map(str,leaders['Sayı'].tolist()))])
        for row in zdf.itertuples(index=False):
            out.append([pd.Timestamp(d).strftime('%d.%m.%Y'),*row])
    detail=pd.DataFrame(out,columns=['Gün','Sayı','23 çıkış','23 oran','Rutin oran','Z'])
    summary=pd.DataFrame(day_summ,columns=['Gün','Çekiliş','23 özgü aday','5+ lider sayısı','5+ liderler'])
    return summary,detail

st.markdown("### Tek tuş — 14 günü otomatik analiz")
if st.button("🚀 14 GÜNÜN TAMAMINI ANALİZ ET", type="primary", use_container_width=True):
    summary,detail=auto_analyze(df)
    st.session_state['auto_summary']=summary
    st.session_state['auto_detail']=detail

if 'auto_summary' in st.session_state:
    summary=st.session_state['auto_summary']; detail=st.session_state['auto_detail']
    st.success("14 gün tek tek ve toplam analiz edildi.")
    st.dataframe(summary,use_container_width=True,hide_index=True)
    total=detail.groupby('Sayı').agg(**{'5+ gün':('23 çıkış',lambda x:int((x>=5).sum())), '23 toplam':('23 çıkış','sum'),'Ort. Z':('Z','mean')}).reset_index()
    total['Kapanış karakteri']=np.select([total['Ort. Z']>=1.5,total['Ort. Z']<=-1.5],['23:xx ÖZGÜ ADAY','23:xx DÜŞÜK'],default='RUTİN/KARIŞIK')
    st.markdown("#### 14 gün toplam 1–80 kapanış karakteri")
    st.dataframe(total.sort_values(['5+ gün','Ort. Z','23 toplam'],ascending=False),use_container_width=True,hide_index=True,height=500)
    st.download_button("Otomatik analiz CSV indir",detail.to_csv(index=False).encode('utf-8-sig'),"14_gun_otomatik_saatlik_analiz.csv","text/csv")

tab1,tab2,tab3,tab4,tab5=st.tabs(["Saatlik 1–80", "Gün × Saat", "23:xx karşılaştırma", "Tek sayı yaşamı", "Ham kalite"])

with tab1:
    st.subheader("Her saatte 1–80 kaç kez çıktı?")
    counts=pd.crosstab(long['number'].to_numpy(), long['hour'].to_numpy()).reindex(index=range(1,81),columns=range(24),fill_value=0)
    counts.columns=[f'{h:02d}:xx' for h in counts.columns]
    st.dataframe(counts, use_container_width=True, height=650)
    st.download_button("Saatlik tabloyu CSV indir", counts.to_csv(index=True).encode('utf-8-sig'), "saatlik_1_80.csv", "text/csv")

with tab2:
    st.subheader("Seçilen sayı için 14 gün × saat matrisi")
    n=st.number_input("Sayı",1,80,1,key='dayhour_num')
    x=long[long.number==n]
    mat=pd.crosstab(x.date,x.hour).reindex(index=dates,columns=range(24),fill_value=0)
    mat.index=[pd.Timestamp(d).strftime('%d.%m.%Y') for d in mat.index]
    mat.columns=[f'{h:02d}:xx' for h in mat.columns]
    st.dataframe(mat, use_container_width=True)
    st.bar_chart(x.groupby('hour').size().reindex(range(24),fill_value=0))

with tab3:
    st.subheader("23:xx gerçekten farklı mı?")
    # per-number rate per draw for each hour
    hc=pd.crosstab(long['number'].to_numpy(), long['hour'].to_numpy()).reindex(index=range(1,81),columns=range(24),fill_value=0)
    rates=hc.copy().astype(float)
    for h in range(24):
        d=hour_draws.get(h,0)
        rates[h]=rates[h]/d if d else np.nan
    routine=[h for h in comparable_hours if h!=23 and h>=7] + ([0] if 0 in comparable_hours else [])
    routine=list(dict.fromkeys(routine))
    rows=[]
    for n in range(1,81):
        r23=rates.loc[n,23] if 23 in rates.columns else np.nan
        vals=rates.loc[n,routine].dropna().values if routine else np.array([])
        mu=float(np.mean(vals)) if len(vals) else np.nan
        sd=float(np.std(vals,ddof=1)) if len(vals)>1 else np.nan
        z=(r23-mu)/sd if sd and sd>0 else np.nan
        rank_hours=[]
        valid=rates.loc[n,comparable_hours].dropna()
        if len(valid):
            rank=int(valid.rank(method='min',ascending=False).loc[23]) if 23 in valid.index else np.nan
        else: rank=np.nan
        rows.append([n,hc.loc[n,23] if 23 in hc.columns else 0,r23,mu,r23-mu,z,rank])
    cmp=pd.DataFrame(rows,columns=['Sayı','23 toplam','23 oran/çekiliş','Rutin ort. oran','Fark','Z','23 saat sırası'])
    cmp['23 lider?']=cmp['Z'].apply(lambda z: 'EVET' if pd.notna(z) and z>=1.5 else ('TERS' if pd.notna(z) and z<=-1.5 else 'RUTİN'))
    st.dataframe(cmp.sort_values(['Z','Fark'],ascending=False),use_container_width=True,height=600)
    st.caption("Z ≥ 1,5: 23:xx o sayının rutin saatlerine göre belirgin yüksek; Z ≤ -1,5: belirgin düşük. Bu keşif ölçüsüdür, tek başına tahmin kuralı değildir.")
    a,b,c=st.columns(3)
    a.metric("23'e özgü yüksek aday", int((cmp['23 lider?']=='EVET').sum()))
    b.metric("Rutin bant", int((cmp['23 lider?']=='RUTİN').sum()))
    c.metric("23'te düşük", int((cmp['23 lider?']=='TERS').sum()))
    st.download_button("23 karşılaştırmasını CSV indir", cmp.to_csv(index=False).encode('utf-8-sig'), "23_vs_rutin.csv", "text/csv")

with tab4:
    st.subheader("Tek sayının saatlik yaşam profili")
    n2=st.selectbox("Sayı seç",range(1,81),key='profile_num')
    prof=[]
    for h in range(24):
        d=int(hour_draws.get(h,0)); c=int(((long.number==n2)&(long.hour==h)).sum())
        prof.append([h,d,c,c/d if d else np.nan])
    prof=pd.DataFrame(prof,columns=['Saat','Çekiliş','Çıkış','Oran/çekiliş'])
    st.dataframe(prof,use_container_width=True)
    st.line_chart(prof.set_index('Saat')['Oran/çekiliş'])
    # day by day final vs daytime
    dd=[]
    for d in selected_dates:
        day=sel[sel.date==d]
        ld=day[['draw_id','time','date','hour','numbers']].explode('numbers', ignore_index=True).rename(columns={'numbers':'number'})
        ld['number']=ld.number.astype(int)
        final=int(((ld.number==n2)&(ld.hour==23)).sum())
        pre=int(((ld.number==n2)&(ld.hour!=23)).sum())
        dd.append([pd.Timestamp(d).strftime('%d.%m.%Y'),pre,final])
    st.dataframe(pd.DataFrame(dd,columns=['Gün','23 öncesi toplam','23:xx toplam']),use_container_width=True)

with tab5:
    st.subheader("Veri kapsamı")
    q=sel.groupby('date').agg(çekiliş=('draw_id','size'),ilk=('time','min'),son=('time','max')).reset_index()
    q['date']=q['date'].astype(str)
    st.dataframe(q,use_container_width=True)
    st.subheader("Saat başına çekiliş sayısı")
    hd=hour_draws.rename('çekiliş').reset_index().rename(columns={'hour':'saat'})
    st.dataframe(hd,use_container_width=True)

st.divider()
st.markdown("**Araştırma disiplini:** Önce 14 günün saatlik rutinini ölç. Sonra 23:xx profilini aynı sayının diğer saatleriyle ve günler arası tekrar oranıyla karşılaştır. 23:xx farkı yalnız tek günde değil, birden çok günde tekrarlanıyorsa kapanış karakteri adayı olarak işaretle.")
