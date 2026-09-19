import streamlit as st
import pandas as pd
import re, os, glob
from collections import Counter

st.set_page_config(page_title="Hızlı On — Otomatik Nöbet Kadavrası", layout="wide")
st.title("🎯 Hızlı On — Otomatik Saatlik Nöbet Kadavrası")
st.caption("TXT kütüğünü uygulama kendisi okur. Günleri otomatik ayırır; 1–80'i saat saat inceler.")

DATA_DIR = "data"

def parse_text(text, source):
    rows=[]
    # format: id;DD.MM.YYYY HH:MM;n1,n2...
    for line in text.splitlines():
        m=re.match(r"\s*(\d+)\s*;\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s*;\s*([0-9,\s]+)\s*$",line)
        if m:
            ns=[int(x) for x in re.findall(r"\d+",m.group(4))]
            if len(ns)==20:
                rows.append((int(m.group(1)),pd.to_datetime(m.group(2)+" "+m.group(3),dayfirst=True),ns,source))
    if rows: return rows

    # copied Milli Piyango blocks
    blocks=re.split(r"(?=Çekiliş\s*no\s*:)",text,flags=re.I)
    for b in blocks:
        mi=re.search(r"Çekiliş\s*no\s*:\s*#?\s*(\d+)",b,re.I)
        md=re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}:\d{2})",b)
        if not(mi and md): continue
        body=re.split(r"Detaylar|https?://",b[md.end():],maxsplit=1)[0]
        ns=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",body)]
        if len(ns)>=20:
            rows.append((int(mi.group(1)),pd.to_datetime(md.group(1)+" "+md.group(2),dayfirst=True),ns[:20],source))
    return rows

@st.cache_data(show_spinner=False)
def load_all():
    files=sorted(glob.glob(os.path.join(DATA_DIR,"*.txt")))
    rows=[]
    for fp in files:
        try:
            text=Path(fp).read_text(encoding="utf-8-sig",errors="ignore")
            rows.extend(parse_text(text,os.path.basename(fp)))
        except Exception:
            pass
    if not rows: return pd.DataFrame(), files
    d=pd.DataFrame(rows,columns=["draw_id","dt","numbers","source"])
    d=d.drop_duplicates("draw_id").sort_values("dt")
    return d,files

def build_hourly(draws):
    out=[]
    for day,gday in draws.groupby(draws.dt.dt.date):
        for h,gh in gday.groupby(gday.dt.dt.hour):
            # Comparable hour: exactly 12 draws.
            if len(gh)!=12: continue
            c=Counter()
            for ns in gh.numbers: c.update(ns)
            for n in range(1,81):
                out.append((pd.Timestamp(day),int(h),n,c[n]))
    return pd.DataFrame(out,columns=["date","hour","number","count"])

def s(c):
    return "H" if c>=4 else ("M" if c>=2 else "L")

def hour_runs(hours):
    runs=[]; cur=[]
    for h in sorted(hours):
        if not cur or h==cur[-1]+1: cur.append(h)
        else:
            if cur:runs.append(cur)
            cur=[h]
    if cur:runs.append(cur)
    return runs

def transition_table(h,th=4):
    rows=[]
    for day,g in h.groupby("date"):
        p=g.pivot(index="number",columns="hour",values="count")
        for run in hour_runs(p.columns):
            for a,b in zip(run,run[1:]):
                A=set(p.index[p[a]>=th]); B=set(p.index[p[b]>=th])
                rows.append([day.date(),f"{a:02d}→{b:02d}",len(A),len(B),len(A&B),
                             len(A-B),len(B-A),100*len(A&B)/len(A) if A else 0])
    return pd.DataFrame(rows,columns=["Tarih","Geçiş","H kadro","H+1 kadro","Kalan","Çıkan","Yeni","Devam %"])

def day_report(h,day):
    g=h[h.date.dt.date==day]
    p=g.pivot(index="number",columns="hour",values="count")
    rows=[]
    for n in range(1,81):
        if n not in p.index: continue
        hs=sorted(p.columns)
        vals=[int(p.loc[n,x]) for x in hs]
        states=[s(x) for x in vals]
        active=[hs[i] for i,v in enumerate(vals) if v>=4]
        gaps=[active[i]-active[i-1]-1 for i in range(1,len(active))]
        rows.append({
            "Sayı":n,
            "Saatlik ham yaşam":" → ".join(f"{hh:02d}:{v}" for hh,v in zip(hs,vals)),
            "L/M/H":"→".join(states),
            "4+ nöbet sayısı":len(active),
            "Doğrudan 4+→4+":sum(1 for a,b in zip(active,active[1:]) if b-a==1),
            "1 saat dinlenip dönüş":sum(1 for x in gaps if x==1),
            "2 saat dinlenip dönüş":sum(1 for x in gaps if x==2),
            "3+ saat dinlenip dönüş":sum(1 for x in gaps if x>=3),
        })
    return pd.DataFrame(rows)

draws,files=load_all()
if draws.empty:
    st.error("Veri bulunamadı.")
    st.code("Repo içinde 'data' klasörü oluştur ve günlük TXT dosyalarını oraya koy.\nÖrnek: data/25_08_2026.txt")
    st.info("TXT'leri bir kez GitHub/Streamlit uygulamasının data klasörüne koyduktan sonra ekranda Upload yapmayacaksın.")
    st.stop()

hourly=build_hourly(draws)
days=sorted(hourly.date.dt.date.unique())

c1,c2,c3=st.columns(3)
c1.metric("Tanındı",f"{len(days)} gün")
c2.metric("Çekiliş",f"{len(draws)}")
c3.metric("TXT",f"{len(files)}")

st.caption("Okunan günler: "+", ".join(pd.Timestamp(x).strftime("%d.%m.%Y") for x in days))

day=st.selectbox("Gün",days,format_func=lambda x:pd.Timestamp(x).strftime("%d.%m.%Y"))
D=hourly[hourly.date.dt.date==day]

tabs=st.tabs(["Gün Kadavrası","Saatten Saate Nöbet","4+/5+/6+/7+","Uzun İzler","80 Sayı"])

with tabs[0]:
    rep=day_report(hourly,day)
    st.dataframe(rep,use_container_width=True,hide_index=True)

with tabs[1]:
    t=transition_table(D,4)
    st.dataframe(t.round(2),use_container_width=True,hide_index=True)
    if len(t):
        a,b,c=st.columns(3)
        a.metric("Ort. kalan",f"{t.Kalan.mean():.2f}")
        b.metric("Ort. çıkan",f"{t.Çıkan.mean():.2f}")
        c.metric("Ort. yeni",f"{t.Yeni.mean():.2f}")

with tabs[2]:
    rr=[]
    for th in [4,5,6,7]:
        q=transition_table(D,th)
        if len(q):
            rr.append([f"{th}+",q["H kadro"].mean(),q.Kalan.mean(),q.Çıkan.mean(),q.Yeni.mean(),q["Devam %"].mean()])
    st.dataframe(pd.DataFrame(rr,columns=["Seviye","Ort kadro","Kalan","Çıkan","Yeni","Devam %"]).round(2),
                 use_container_width=True,hide_index=True)

with tabs[3]:
    g=D.pivot(index="number",columns="hour",values="count")
    L=st.slider("İz uzunluğu (saat)",4,12,8)
    patterns=[]
    for n in g.index:
        for run in hour_runs(g.columns):
            vals=[int(g.loc[n,h]) for h in run]
            if len(vals)<L: continue
            for i in range(len(vals)-L+1):
                v=vals[i:i+L]
                patterns.append([n,run[i],run[i+L-1],"→".join(map(str,v)),"→".join(s(x) for x in v)])
    z=pd.DataFrame(patterns,columns=["Sayı","Başlangıç","Bitiş","Ham zincir","L/M/H"])
    st.dataframe(z,use_container_width=True,hide_index=True)

with tabs[4]:
    n=st.number_input("Sayı",1,80,35)
    one=D[D.number==n].sort_values("hour").copy()
    one["Durum"]=one["count"].map(s)
    st.dataframe(one[["hour","count","Durum"]],use_container_width=True,hide_index=True)
    if len(one):
        st.code(" → ".join(f"{int(r.hour):02d}:{int(r['count'])}" for _,r in one.iterrows()))

st.divider()
st.caption("Yeni TXT eklediğinde data klasörüne koyup uygulamayı yeniden başlat/yayınla; tarih otomatik eklenir.")
