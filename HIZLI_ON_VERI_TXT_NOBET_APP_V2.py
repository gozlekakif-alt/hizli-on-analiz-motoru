import streamlit as st
import pandas as pd
import re
from pathlib import Path
from collections import Counter

st.set_page_config(page_title="Hızlı On — Nöbet Zinciri", layout="wide")
st.title("🎯 Hızlı On — Saatlik Nöbet Zinciri")
st.caption("veri.txt otomatik okunur. Tarihler otomatik ayrılır. Upload yok.")

DATA_FILE = Path("veri.txt")

def parse_veri(text):
    rows=[]
    # id;DD.MM.YYYY HH:MM;n1,n2,...,n20
    for line in text.splitlines():
        m=re.match(r"\s*(\d+)\s*;\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s*;\s*([0-9,\s]+)\s*$", line)
        if m:
            nums=[int(x) for x in re.findall(r"\d+",m.group(4))]
            if len(nums)==20:
                rows.append((int(m.group(1)),pd.to_datetime(m.group(2)+" "+m.group(3),dayfirst=True),nums))
    if rows:
        return pd.DataFrame(rows,columns=["draw_id","dt","numbers"]).drop_duplicates("draw_id").sort_values("dt")

    # Çekiliş no: ... copied format
    blocks=re.split(r"(?=Çekiliş\s*no\s*:)",text,flags=re.I)
    for b in blocks:
        mi=re.search(r"Çekiliş\s*no\s*:\s*#?\s*(\d+)",b,re.I)
        md=re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}:\d{2})",b)
        if not(mi and md): continue
        body=re.split(r"Detaylar|https?://",b[md.end():],maxsplit=1)[0]
        nums=[int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)",body)]
        if len(nums)>=20:
            rows.append((int(mi.group(1)),pd.to_datetime(md.group(1)+" "+md.group(2),dayfirst=True),nums[:20]))
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows,columns=["draw_id","dt","numbers"]).drop_duplicates("draw_id").sort_values("dt")

def build_hourly(d):
    out=[]
    for day,gd in d.groupby(d.dt.dt.date):
        for h,gh in gd.groupby(gd.dt.dt.hour):
            # 12-draw comparable hours only
            if len(gh)!=12: continue
            c=Counter()
            for ns in gh.numbers: c.update(ns)
            for n in range(1,81):
                out.append([pd.Timestamp(day),int(h),n,c[n]])
    return pd.DataFrame(out,columns=["date","hour","number","count"])

def state(x):
    return "H" if x>=4 else ("M" if x>=2 else "L")

def runs(hours):
    z=[]; cur=[]
    for h in sorted(hours):
        if not cur or h==cur[-1]+1: cur.append(h)
        else:
            if cur:z.append(cur)
            cur=[h]
    if cur:z.append(cur)
    return z

def transitions(h,th):
    rr=[]
    for day,g in h.groupby("date"):
        p=g.pivot(index="number",columns="hour",values="count")
        for run in runs(p.columns):
            for a,b in zip(run,run[1:]):
                A=set(p.index[p[a]>=th]); B=set(p.index[p[b]>=th])
                rr.append([day.date(),f"{a:02d}→{b:02d}",len(A),len(B),len(A&B),len(A-B),len(B-A),
                           100*len(A&B)/len(A) if A else 0])
    return pd.DataFrame(rr,columns=["Tarih","Geçiş","İlk kadro","Sonraki kadro","Kalan","Çıkan","Yeni","Devam %"])

if not DATA_FILE.exists():
    st.error("veri.txt bulunamadı.")
    st.code("app.py\nveri.txt")
    st.stop()

draws=parse_veri(DATA_FILE.read_text(encoding="utf-8-sig",errors="ignore"))
if draws.empty:
    st.error("veri.txt bulundu ama çekiliş formatı okunamadı.")
    st.stop()

hourly=build_hourly(draws)
days=sorted(hourly.date.dt.date.unique())

a,b,c=st.columns(3)
a.metric("Gün",len(days))
b.metric("Çekiliş",len(draws))
c.metric("Saatlik kayıt",len(hourly))
st.success("veri.txt otomatik tanındı.")

day=st.selectbox("Gün",days,format_func=lambda x:pd.Timestamp(x).strftime("%d.%m.%Y"))
D=hourly[hourly.date.dt.date==day]

tabs=st.tabs(["Günlük Nöbet","4+/5+/6+/7+","Uzun Zincir","1–80 Yaşam","14 Gün Toplu"])

with tabs[0]:
    t=transitions(D,4)
    st.dataframe(t.round(2),use_container_width=True,hide_index=True)
    if len(t):
        x,y,z=st.columns(3)
        x.metric("Ort. kalan",f"{t.Kalan.mean():.2f}")
        y.metric("Ort. çıkan",f"{t.Çıkan.mean():.2f}")
        z.metric("Ort. yeni",f"{t.Yeni.mean():.2f}")

with tabs[1]:
    rows=[]
    for th in [4,5,6,7]:
        q=transitions(D,th)
        if len(q):
            rows.append([f"{th}+",q["İlk kadro"].mean(),q.Kalan.mean(),q.Çıkan.mean(),q.Yeni.mean(),q["Devam %"].mean()])
    st.dataframe(pd.DataFrame(rows,columns=["Seviye","Ort. kadro","Kalan","Çıkan","Yeni","Devam %"]).round(2),
                 use_container_width=True,hide_index=True)

with tabs[2]:
    L=st.slider("Zincir uzunluğu",4,12,8)
    p=D.pivot(index="number",columns="hour",values="count")
    out=[]
    for n in p.index:
        for run in runs(p.columns):
            vals=[int(p.loc[n,h]) for h in run]
            for i in range(max(0,len(vals)-L+1)):
                v=vals[i:i+L]
                if len(v)==L:
                    out.append([n,run[i],run[i+L-1],"→".join(map(str,v)),"→".join(state(x) for x in v)])
    zz=pd.DataFrame(out,columns=["Sayı","Başlangıç","Bitiş","Ham zincir","L/M/H"])
    st.dataframe(zz,use_container_width=True,hide_index=True)

with tabs[3]:
    n=st.number_input("Sayı",1,80,35)
    q=D[D.number==n].sort_values("hour").copy()
    q["Durum"]=q["count"].map(state)
    st.dataframe(q[["hour","count","Durum"]],use_container_width=True,hide_index=True)
    if len(q):
        st.code(" → ".join(f"{int(r.hour):02d}:{int(r['count'])}" for _,r in q.iterrows()))

with tabs[4]:
    rows=[]
    for th in [4,5,6,7]:
        q=transitions(hourly,th)
        if len(q):
            rows.append([f"{th}+",len(q),q["İlk kadro"].mean(),q.Kalan.mean(),q.Çıkan.mean(),q.Yeni.mean(),q["Devam %"].mean()])
    st.dataframe(pd.DataFrame(rows,columns=["Seviye","Geçiş","Ort. kadro","Kalan","Çıkan","Yeni","Devam %"]).round(2),
                 use_container_width=True,hide_index=True)

st.divider()
st.subheader("📦 Tüm Günler — Tek MASTER TXT")

def master_report(hourly):
    out=["HIZLI ON — SAATLİK NÖBET / UZUN ZİNCİR MASTER","Kaynak: veri.txt","L=0–1 | M=2–3 | H=4+",""]
    for day in sorted(hourly.date.dt.date.unique()):
        D=hourly[hourly.date.dt.date==day]
        out += ["","="*80,f"GÜN {pd.Timestamp(day).strftime('%d.%m.%Y')}","="*80]
        out.append("[4+/5+/6+/7+ ÖZET]")
        for th in [4,5,6,7]:
            q=transitions(D,th)
            if len(q):
                out.append(f"{th}+ | ort.kadro={q['İlk kadro'].mean():.2f} | kalan={q.Kalan.mean():.2f} | çıkan={q.Çıkan.mean():.2f} | yeni={q.Yeni.mean():.2f} | devam={q['Devam %'].mean():.2f}%")
        q=transitions(D,4)
        out.append("[4+ SAATTEN SAATE]")
        for _,r in q.iterrows():
            out.append(f"{r['Geçiş']} | {int(r['İlk kadro'])}->{int(r['Sonraki kadro'])} | kalan={int(r.Kalan)} çıkan={int(r.Çıkan)} yeni={int(r.Yeni)} devam={r['Devam %']:.1f}%")
        p=D.pivot(index="number",columns="hour",values="count")
        out.append("[1–80 TAM YAŞAM]")
        for n in range(1,81):
            if n not in p.index: continue
            hs=sorted(p.columns); vals=[int(p.loc[n,h]) for h in hs]
            active=[h for h,v in zip(hs,vals) if v>=4]
            gaps=[active[i]-active[i-1]-1 for i in range(1,len(active))]
            out.append(f"SAYI {n:02d} | "+" -> ".join(f"{h:02d}:{v}" for h,v in zip(hs,vals)))
            out.append("DURUM    | "+"->".join(state(v) for v in vals)+f" | 4+={len(active)} direkt={sum(x==0 for x in gaps)} 1s={sum(x==1 for x in gaps)} 2s={sum(x==2 for x in gaps)} 3+s={sum(x>=3 for x in gaps)}")
        out.append("[12 SAATLİK UZUN İZLER]")
        for n in p.index:
            for run in runs(p.columns):
                vals=[int(p.loc[n,h]) for h in run]
                for i in range(max(0,len(vals)-11)):
                    v=vals[i:i+12]
                    if len(v)==12:
                        out.append(f"{int(n):02d} | {run[i]:02d}->{run[i+11]:02d} | "+"->".join(map(str,v))+" | "+"->".join(state(x) for x in v))
    out += ["","="*80,"TÜM GÜNLER TOPLU","="*80]
    for th in [4,5,6,7]:
        q=transitions(hourly,th)
        if len(q):
            out.append(f"{th}+ | geçiş={len(q)} ort.kadro={q['İlk kadro'].mean():.2f} kalan={q.Kalan.mean():.2f} çıkan={q.Çıkan.mean():.2f} yeni={q.Yeni.mean():.2f} devam={q['Devam %'].mean():.2f}%")
    return "\n".join(out)

MASTER=master_report(hourly)
st.write(f"{len(days)} gün tek dosyada hazır — {MASTER.count(chr(10))+1:,} satır")
st.download_button("⬇️ TEK MASTER TXT İNDİR",MASTER.encode("utf-8-sig"),"HIZLI_ON_14_GUN_NOBET_ZINCIRI_MASTER.txt","text/plain",use_container_width=True)
