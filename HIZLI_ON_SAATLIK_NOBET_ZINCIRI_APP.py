import streamlit as st
import pandas as pd
import re
from collections import Counter

st.set_page_config(page_title="Hızlı On - Saatlik Nöbet Zinciri", layout="wide")
st.title("🎯 Hızlı On — Saatlik 4+ Nöbet Zinciri")
st.caption("TXT yükle → gün gün otomatik analiz. 4+/5+/6+/7+ kadroları, saatten saate devir ve uzun nöbet zincirleri.")

# ---------------- PARSER ----------------
def parse_txt(text):
    rows = []
    # Format A: draw_id;DD.MM.YYYY HH:MM;n1,n2,...,n20
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s*;\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s*;\s*([0-9,\s]+)\s*$", line)
        if m:
            nums = [int(x) for x in re.findall(r"\d+", m.group(4))]
            if len(nums) == 20:
                rows.append((int(m.group(1)), pd.to_datetime(m.group(2)+" "+m.group(3), dayfirst=True), nums))
    if rows:
        return pd.DataFrame(rows, columns=["draw_id","dt","numbers"]).sort_values("dt")

    # Format B: Milli Piyango copied blocks
    blocks = re.split(r"(?=Çekiliş\s*no\s*:)", text, flags=re.I)
    for b in blocks:
        mid = re.search(r"Çekiliş\s*no\s*:\s*#?\s*(\d+)", b, re.I)
        mdt = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}:\d{2})", b)
        if not (mid and mdt):
            continue
        after = b[mdt.end():]
        after = re.split(r"Detaylar|https?://", after, maxsplit=1)[0]
        nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", after)]
        if len(nums) >= 20:
            nums = nums[:20]
            rows.append((int(mid.group(1)), pd.to_datetime(mdt.group(1)+" "+mdt.group(2), dayfirst=True), nums))
    return pd.DataFrame(rows, columns=["draw_id","dt","numbers"]).sort_values("dt") if rows else pd.DataFrame()

def hour_label(dt):
    return int(dt.hour)

def build_hourly(draws):
    rec=[]
    for day, gd in draws.groupby(draws["dt"].dt.date):
        for h, gh in gd.groupby(gd["dt"].dt.hour):
            # Analyze only complete 12-draw hours. 00 may be special; 01 is not comparable.
            if len(gh) != 12:
                continue
            c=Counter()
            for ns in gh["numbers"]:
                c.update(ns)
            for n in range(1,81):
                rec.append({"date":pd.Timestamp(day), "hour":int(h), "number":n, "count":c[n]})
    return pd.DataFrame(rec)

def state(c):
    if c <= 1: return "L"
    if c <= 3: return "M"
    return "H"

def consecutive_pairs(hours):
    hs=sorted(hours)
    return [(a,b) for a,b in zip(hs,hs[1:]) if b==a+1]

def transition_summary(hourly, threshold):
    out=[]
    for day, g in hourly.groupby("date"):
        piv=g.pivot(index="number",columns="hour",values="count")
        for a,b in consecutive_pairs(piv.columns):
            A=set(piv.index[piv[a]>=threshold])
            B=set(piv.index[piv[b]>=threshold])
            out.append({
                "Tarih":day.date(), "Geçiş":f"{a:02d}→{b:02d}",
                "H kadro":len(A), "H+1 kadro":len(B),
                "Kalan":len(A&B), "Çıkan":len(A-B), "Yeni":len(B-A),
                "Devam %":round(100*len(A&B)/len(A),1) if A else 0
            })
    return pd.DataFrame(out)

def long_chains(hourly, min_len=4, max_len=12):
    rows=[]
    for day,g in hourly.groupby("date"):
        piv=g.pivot(index="number",columns="hour",values="count")
        hs=sorted(piv.columns)
        # split into genuinely consecutive-hour runs
        runs=[]
        cur=[]
        for h in hs:
            if not cur or h==cur[-1]+1: cur.append(h)
            else:
                if cur: runs.append(cur)
                cur=[h]
        if cur: runs.append(cur)
        for n in piv.index:
            for run in runs:
                vals=[int(piv.loc[n,h]) for h in run]
                sts=[state(v) for v in vals]
                for L in range(min_len, min(max_len,len(run))+1):
                    for i in range(0,len(run)-L+1):
                        rows.append({
                            "Tarih":day.date(),"Sayı":n,
                            "Başlangıç":run[i],"Bitiş":run[i+L-1],"Uzunluk":L,
                            "Ham zincir":"→".join(map(str,vals[i:i+L])),
                            "Durum zinciri":"→".join(sts[i:i+L])
                        })
    return pd.DataFrame(rows)

def rotation_age_table(hourly, threshold=4):
    rows=[]
    for day,g in hourly.groupby("date"):
        piv=g.pivot(index="number",columns="hour",values="count")
        hs=sorted(piv.columns)
        for n in piv.index:
            last_h=None
            for h in hs:
                active = piv.loc[n,h] >= threshold
                if active:
                    age = None if last_h is None else h-last_h-1
                    rows.append({"Tarih":day.date(),"Saat":h,"Sayı":n,"Seviye":threshold,
                                 "Önceki nöbetten bekleme":age,"Count":int(piv.loc[n,h])})
                    last_h=h
    return pd.DataFrame(rows)

uploaded = st.file_uploader("TXT dosyası yükle", type=["txt"], accept_multiple_files=True)

if uploaded:
    parts=[]
    for f in uploaded:
        text=f.read().decode("utf-8-sig", errors="ignore")
        d=parse_txt(text)
        if not d.empty:
            d["source"]=f.name
            parts.append(d)
    if not parts:
        st.error("TXT içinden çekiliş okunamadı.")
        st.stop()

    draws=pd.concat(parts,ignore_index=True).drop_duplicates(subset=["draw_id"]).sort_values("dt")
    st.success(f"{draws['dt'].dt.date.nunique()} gün, {len(draws)} çekiliş okundu.")

    hourly=build_hourly(draws)
    dates=sorted(hourly["date"].dt.date.unique())
    chosen=st.multiselect("Analiz günleri", dates, default=dates)
    H=hourly[hourly["date"].dt.date.isin(chosen)].copy()

    tabs=st.tabs(["4+ Nöbet", "5+/6+/7+", "Uzun Zincir", "Nöbet Yaşı", "Sayı Yaşamı"])

    with tabs[0]:
        t=transition_summary(H,4)
        if len(t):
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Ort. 4+ kadro", f"{t['H kadro'].mean():.2f}")
            c2.metric("Ort. kalan", f"{t['Kalan'].mean():.2f}")
            c3.metric("Ort. çıkan", f"{t['Çıkan'].mean():.2f}")
            c4.metric("Ort. yeni", f"{t['Yeni'].mean():.2f}")
            st.dataframe(t, use_container_width=True, hide_index=True)
            st.subheader("Saat geçişi özeti")
            st.dataframe(t.groupby("Geçiş").agg(
                Geçiş_sayısı=("Kalan","size"),
                Ort_kalan=("Kalan","mean"),
                Ort_çıkan=("Çıkan","mean"),
                Ort_yeni=("Yeni","mean"),
                Devam_yüzde=("Devam %","mean")
            ).round(2), use_container_width=True)

    with tabs[1]:
        allsum=[]
        for th in [4,5,6,7]:
            q=transition_summary(H,th)
            if len(q):
                allsum.append({
                    "Seviye":f"{th}+","Ort. kadro":q["H kadro"].mean(),
                    "Ort. kalan":q["Kalan"].mean(),"Ort. çıkan":q["Çıkan"].mean(),
                    "Ort. yeni":q["Yeni"].mean(),"Devam %":q["Devam %"].mean()
                })
        st.dataframe(pd.DataFrame(allsum).round(2),use_container_width=True,hide_index=True)

    with tabs[2]:
        maxlen=st.slider("Zincir uzunluğu",4,12,8)
        chains=long_chains(H,4,maxlen)
        if len(chains):
            exact=chains[chains["Uzunluk"]==maxlen]
            freq=exact.groupby("Durum zinciri").size().reset_index(name="Vaka").sort_values("Vaka",ascending=False)
            st.caption("L=0–1, M=2–3, H=4+. Tam ham sayı dizisini ezberlemek yerine nöbet fazını görür.")
            st.dataframe(freq.head(100),use_container_width=True,hide_index=True)
            st.subheader("Özel merdiven arama")
            pattern=st.text_input("Durum veya ham zincir (örn. H→M→M veya 4→3→2→1→0)", "H→M→M")
            hit=chains[(chains["Durum zinciri"].str.contains(pattern,regex=False)) |
                       (chains["Ham zincir"].str.contains(pattern,regex=False))]
            st.write(f"{len(hit)} eşleşme")
            st.dataframe(hit.head(500),use_container_width=True,hide_index=True)

    with tabs[3]:
        age=rotation_age_table(H,4)
        aa=age.dropna(subset=["Önceki nöbetten bekleme"])
        if len(aa):
            z=aa.groupby("Önceki nöbetten bekleme").size().reset_index(name="Nöbete dönüş")
            z["Pay %"]=100*z["Nöbete dönüş"]/z["Nöbete dönüş"].sum()
            st.dataframe(z.round(2),use_container_width=True,hide_index=True)
        st.caption("0 = ardışık saatte yeniden 4+; 1 = bir saat dışarıda kalıp dönüş; 2 = iki saat dinlenip dönüş.")

    with tabs[4]:
        n=st.number_input("Sayı",1,80,35)
        one=H[H["number"]==n].sort_values(["date","hour"]).copy()
        one["Durum"]=one["count"].map(state)
        st.dataframe(one[["date","hour","count","Durum"]],use_container_width=True,hide_index=True)
        for day,g in one.groupby("date"):
            st.write(str(day.date()), "  ", " → ".join(f"{int(r.hour):02d}:{int(r['count'])}" for _,r in g.iterrows()))

    # exports
    st.divider()
    st.subheader("Çıktı")
    t4=transition_summary(H,4)
    csv=t4.to_csv(index=False).encode("utf-8-sig")
    st.download_button("4+ saatlik nöbet raporunu CSV indir",csv,"4plus_saatlik_nobet.csv","text/csv")
else:
    st.info("Bir veya birden fazla günlük TXT yükle. App günleri otomatik tanır ve ayrı ayrı analiz eder.")
