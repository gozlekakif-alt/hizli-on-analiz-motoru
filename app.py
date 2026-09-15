
import streamlit as st
import pandas as pd
import numpy as np
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path
import sqlite3, json, io, math

st.set_page_config(page_title="Hızlı On Tam Araştırma Laboratuvarı", layout="wide")
st.title("🧪 Hızlı On — Tam Araştırma Laboratuvarı")
st.caption("REAL20 / NEGATIVE60 • aileler • bloklar • ritim • H1–H8 • yaş/uyku • sıcaklık • ağ • faz • yakınsama • walk-forward • Top20 • kupon")

DATA_FILE = Path("veri.txt")
DB_FILE = "research.db"

@st.cache_data(show_spinner=False)
def load_data(path="veri.txt"):
    rows=[]
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        p=line.strip().split(";")
        if len(p)!=3: continue
        try:
            ns=tuple(sorted(map(int,p[2].split(","))))
            dt=pd.to_datetime(p[1],dayfirst=True)
            did=int(p[0])
        except: continue
        if len(ns)==20 and len(set(ns))==20 and min(ns)>=1 and max(ns)<=80:
            rows.append((did,dt,ns))
    d=pd.DataFrame(rows,columns=["draw_id","time","numbers"]).sort_values(["time","draw_id"]).reset_index(drop=True)
    d["date"]=d.time.dt.date
    d["clock"]=d.time.dt.strftime("%H:%M")
    d["day_index"]=d.groupby("date").cumcount()+1
    d["hour"]=d.time.dt.hour
    return d

def mask(df):
    A=np.zeros((len(df),80),dtype=np.uint8)
    for i,ns in enumerate(df.numbers):
        A[i,np.array(ns)-1]=1
    return A

def z(s):
    s=pd.Series(s,dtype=float)
    sd=s.std()
    return (s-s.mean())/(sd if sd and not np.isnan(sd) else 1)

def blocks(ns):
    if not ns: return []
    a=sorted(ns); out=[]; cur=[a[0]]
    for x in a[1:]:
        if x==cur[-1]+1: cur.append(x)
        else:
            if len(cur)>=2: out.append(tuple(cur))
            cur=[x]
    if len(cur)>=2: out.append(tuple(cur))
    return out

def gaps_of(idx):
    return np.diff(idx) if len(idx)>1 else np.array([],dtype=int)

def number_state(df):
    A=mask(df); n=len(df); rows=[]
    for num in range(1,81):
        idx=np.where(A[:,num-1]==1)[0]
        gaps=gaps_of(idx)
        age=n-1-idx[-1] if len(idx) else n
        row={"number":num,"freq":len(idx),"age":int(age),
             "mean_gap":float(gaps.mean()) if len(gaps) else np.nan,
             "max_gap":int(gaps.max()) if len(gaps) else np.nan,
             "min_gap":int(gaps.min()) if len(gaps) else np.nan}
        for w in (5,12,24,36,60):
            row[f"r{w}"]=int(A[max(0,n-w):,num-1].sum())
        for h in range(1,9):
            row[f"H{h}"]=int(A[-h,num-1]) if n>=h else 0
        rows.append(row)
    return pd.DataFrame(rows)

def family_events(df,k):
    c=Counter()
    first={}; last={}
    for i,r in df.iterrows():
        for fam in combinations(r.numbers,k):
            c[fam]+=1
            first.setdefault(fam,(int(r.draw_id),r.time))
            last[fam]=(int(r.draw_id),r.time)
    rows=[]
    for fam,n in c.items():
        if n>=2:
            rows.append({"family":"-".join(map(str,fam)),"size":k,"count":n,
                         "first_draw":first[fam][0],"last_draw":last[fam][0]})
    return pd.DataFrame(rows).sort_values(["count","family"],ascending=[False,True]) if rows else pd.DataFrame()

def family_transition_events(df,k,max_rows=200000):
    # occurrence gaps + persistence/fragmentation to next hand
    rows=[]; prev_occ=defaultdict(lambda:None)
    for i in range(len(df)):
        cur=set(df.iloc[i].numbers)
        nxt=set(df.iloc[i+1].numbers) if i+1<len(df) else set()
        for fam in combinations(sorted(cur),k):
            kept=len(set(fam)&nxt)
            po=prev_occ[fam]
            rows.append({"event_id":f"F{k}-{df.iloc[i].draw_id}-"+("-".join(map(str,fam))),
                         "draw_id":int(df.iloc[i].draw_id),"family":"-".join(map(str,fam)),
                         "next_kept":kept,"next_full":int(kept==k),
                         "gap_since_prev":(i-po if po is not None else np.nan)})
            prev_occ[fam]=i
            if len(rows)>=max_rows: return pd.DataFrame(rows)
    return pd.DataFrame(rows)

def block_events(df):
    rows=[]; prev={}
    for i,r in df.iterrows():
        nxt=set(df.iloc[i+1].numbers) if i+1<len(df) else set()
        for b in blocks(r.numbers):
            s=set(b); kept=len(s&nxt)
            key=b
            rows.append({"event_id":f"B-{r.draw_id}-"+("-".join(map(str,b))),
                         "draw_id":int(r.draw_id),"block":"-".join(map(str,b)),
                         "length":len(b),"next_kept":kept,"next_full":int(kept==len(b)),
                         "gap_since_prev":i-prev[key] if key in prev else np.nan})
            prev[key]=i
    return pd.DataFrame(rows)

def rhythm_table(df):
    A=mask(df); rows=[]
    for num in range(1,81):
        idx=np.where(A[:,num-1]==1)[0]
        gp=gaps_of(idx)
        cnt=Counter(map(int,gp))
        for gap,n in cnt.items():
            rows.append({"number":num,"gap":gap,"count":n})
    return pd.DataFrame(rows).sort_values(["count","number"],ascending=[False,True]) if rows else pd.DataFrame()

def suffix_table(df):
    rows=[]
    for _,r in df.iterrows():
        c=Counter(n%10 for n in r.numbers)
        for suf,n in c.items():
            rows.append({"draw_id":int(r.draw_id),"suffix":suf,"count":n})
    return pd.DataFrame(rows)

def band_table(df):
    rows=[]
    for _,r in df.iterrows():
        c=Counter((n-1)//10+1 for n in r.numbers)
        row={"draw_id":int(r.draw_id)}
        for b in range(1,9): row[f"B{b}"]=c[b]
        rows.append(row)
    return pd.DataFrame(rows)

def geometry(df):
    rows=[]
    for _,r in df.iterrows():
        ns=sorted(r.numbers); bs=blocks(ns)
        rows.append({"draw_id":int(r.draw_id),"odd":sum(n%2 for n in ns),
                     "even":sum(n%2==0 for n in ns),"low_1_40":sum(n<=40 for n in ns),
                     "high_41_80":sum(n>40 for n in ns),
                     "block_count":len(bs),"block_numbers":sum(map(len,bs)),
                     "span":max(ns)-min(ns),"mean":round(float(np.mean(ns)),2),
                     "median":float(np.median(ns))})
    return pd.DataFrame(rows)

def real20_similarity(df):
    A=mask(df); hist=Counter(); best=(0,None,None)
    for i in range(len(A)):
        if i==0: continue
        sims=A[:i]@A[i]
        hist.update(map(int,sims))
        m=int(sims.max())
        if m>best[0]:
            j=int(np.argmax(sims)); best=(m,int(df.iloc[j].draw_id),int(df.iloc[i].draw_id))
    return best,pd.DataFrame(sorted(hist.items()),columns=["intersection","pair_count"])

def score_candidates(hist):
    f=number_state(hist).copy()
    for c in ["freq","r5","r12","r24","r36","r60"]:
        f[c+"z"]=z(f[c])
    # Independent signal columns are preserved; score is only the current ensemble.
    f["sig_recent"]=1.15*f.r5z+.85*f.r12z+.45*f.r24z
    f["sig_carry"]=.34*f.H1+.22*f.H2+.16*f.H3+.10*f.H4+.07*f.H5+.05*f.H6
    f["sig_age"]=-.018*(f.age-f.age.median()).abs()
    f["sig_long"]=.20*f.freqz+.18*f.r60z
    # neighbor/social support from last 12 draws
    recent=hist.tail(min(12,len(hist)))
    rc=Counter(n for ns in recent.numbers for n in ns)
    f["sig_social"]=f.number.map(lambda n: sum(rc.get(x,0) for x in (n-1,n+1) if 1<=x<=80)/12.0)
    f["score"]=f.sig_recent+f.sig_carry+f.sig_age+f.sig_long+.12*f.sig_social
    f["reasons"]=f.apply(lambda r:
        ", ".join([x for x,v in [
            ("H1 taşıma",r.H1),("H2 dönüş",r.H2),("H3 dönüş",r.H3),
            ("kısa pencere sıcak",r.r5>=2),("12-el güçlü",r.r12>=4),
            ("derin yaş",r.age>=8),("komşu/ağ desteği",r.sig_social>=.5)] if v]),axis=1)
    return f.sort_values(["score","number"],ascending=[False,True]).reset_index(drop=True)

def top20(hist): return tuple(sorted(score_candidates(hist).head(20).number.astype(int)))

def coupons_from_score(sc):
    r=sc.number.astype(int).tolist()[:20]
    sets=[r[:10],r[::2][:10],r[1::2][:10],r[5:15]]
    return [tuple(sorted(x)) for x in sets]

def walk_forward(df,warmup=50):
    rows=[]
    for i in range(max(1,warmup),len(df)):
        hist=df.iloc[:i]
        pred=set(top20(hist)); actual=set(df.iloc[i].numbers)
        inter=sorted(pred&actual)
        rows.append({"draw_id":int(df.iloc[i].draw_id),"time":df.iloc[i].time,
                     "hits":len(inter),"hit_numbers":"-".join(map(str,inter)),
                     "missed_real":"-".join(map(str,sorted(actual-pred))),
                     "false_positive":"-".join(map(str,sorted(pred-actual))),
                     "predicted":"-".join(map(str,sorted(pred)))})
    return pd.DataFrame(rows)

def daily_report(daydf, alldf):
    A=mask(daydf)
    ns=number_state(daydf)
    fams={k:family_events(daydf,k) for k in (2,3,4,5)}
    be=block_events(daydf)
    rt=rhythm_table(daydf)
    geo=geometry(daydf)
    bands=band_table(daydf)
    suffix=suffix_table(daydf)
    overlaps=np.sum(A[1:]*A[:-1],axis=1) if len(A)>1 else np.array([])
    lines=[]
    d=str(daydf.iloc[0].date)
    lines += [f"HIZLI ON GUNLUK KADAVRA RAPORU — {d}",
              f"Cekilis sayisi: {len(daydf)}",
              f"Ilk/Son: {daydf.iloc[0].draw_id} / {daydf.iloc[-1].draw_id}",
              f"Ardisik REAL20 ortalama tasima: {overlaps.mean():.3f}" if len(overlaps) else "",
              f"Ardisik REAL20 maksimum tasima: {overlaps.max()}" if len(overlaps) else "",
              ""]
    lines.append("=== SAYI YASAM YOLU / SICAKLIK / H1-H8 ===")
    for _,r in ns.sort_values(["freq","number"],ascending=[False,True]).iterrows():
        lines.append(f"{int(r.number):02d};freq={int(r.freq)};age={int(r.age)};r5={int(r.r5)};r12={int(r.r12)};"
                     +";".join(f"H{i}={int(r[f'H{i}'])}" for i in range(1,9)))
    for k in (2,3,4,5):
        lines += ["",f"=== {k}LI AILELER TOP 100 ==="]
        if len(fams[k]):
            for _,r in fams[k].head(100).iterrows():
                lines.append(f"{r.family};count={int(r['count'])};first={int(r.first_draw)};last={int(r.last_draw)}")
    lines += ["","=== ARDISIK BLOKLAR TOP 100 ==="]
    if len(be):
        q=be.groupby(["block","length"]).agg(events=("event_id","count"),next_full=("next_full","sum"),
                                                mean_next_kept=("next_kept","mean")).reset_index()
        for _,r in q.sort_values("events",ascending=False).head(100).iterrows():
            lines.append(f"{r.block};len={int(r.length)};events={int(r.events)};next_full={int(r.next_full)};next_kept={r.mean_next_kept:.2f}")
    lines += ["","=== RITIM/GAP TOP 100 ==="]
    if len(rt):
        for _,r in rt.head(100).iterrows(): lines.append(f"num={int(r.number)};gap={int(r.gap)};count={int(r['count'])}")
    lines += ["","=== GEOMETRI ORTALAMALARI ==="]
    for c in ["odd","even","low_1_40","high_41_80","block_count","block_numbers","span","mean"]:
        lines.append(f"{c}={geo[c].mean():.3f}")
    lines += ["","=== BANT ORTALAMALARI ==="]
    for b in range(1,9): lines.append(f"B{b}={bands[f'B{b}'].mean():.3f}")
    lines += ["","=== SON HANE ORTALAMALARI ==="]
    ss=suffix.groupby("suffix")["count"].mean()
    for s,v in ss.items(): lines.append(f"suffix{s}={v:.3f}")
    lines += ["","NOT: Bu rapor gun icindeki olaylari ozetler. Tahmin basarisi sadece kronolojik walk-forward ile olculur."]
    return "\n".join(lines)

def init_db():
    con=sqlite3.connect(DB_FILE)
    con.execute("""CREATE TABLE IF NOT EXISTS predictions(
    target_key TEXT PRIMARY KEY, created_at TEXT, history_last_id INTEGER,
    top20 TEXT, coupons TEXT, status TEXT, actual TEXT, hits INTEGER)""")
    con.commit(); con.close()

def append_draw(draw_id,dt,nums):
    line=f"{int(draw_id)};{pd.Timestamp(dt).strftime('%d.%m.%Y %H:%M')};"+",".join(map(str,sorted(nums)))
    old=DATA_FILE.read_text(encoding="utf-8").splitlines()
    if any(x.startswith(str(int(draw_id))+";") for x in old): raise ValueError("Çekiliş no zaten var.")
    with DATA_FILE.open("a",encoding="utf-8") as f: f.write("\n"+line)
    st.cache_data.clear()

init_db()
df=load_data()

if df.empty:
    st.error("veri.txt okunamadı."); st.stop()

st.sidebar.success(f"{len(df):,} çekiliş • {df.date.nunique()} gün")
section=st.sidebar.radio("Araştırma bölümü",[
    "1 Genel Kadavra","2 Sayı Yaşam Yolları","3 Aileler 2-5","4 Ardışık/Komşu/Geometri",
    "5 Ritimler","6 H1-H8 / Yaş-Uyku","7 Bant / Son Hane","8 Sosyal Ağ",
    "9 Aynı REAL20 / Yakınlık","10 Walk-forward","11 Günlük Rapor İndir",
    "12 Canlı Top20 + Kupon","13 Yeni Çekiliş / Doğrula"])

if section=="1 Genel Kadavra":
    A=mask(df); ov=np.sum(A[1:]*A[:-1],axis=1)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Çekiliş",len(df)); c2.metric("Gün",df.date.nunique())
    c3.metric("Ort. H1 taşıma",f"{ov.mean():.2f}"); c4.metric("Maks. H1 taşıma",int(ov.max()))
    st.dataframe(geometry(df),use_container_width=True)

elif section=="2 Sayı Yaşam Yolları":
    st.dataframe(number_state(df),use_container_width=True,height=650)

elif section=="3 Aileler 2-5":
    k=st.selectbox("Aile büyüklüğü",[2,3,4,5])
    tab=family_events(df,k)
    st.metric("En az 2 kez görülen aile",len(tab))
    st.dataframe(tab.head(3000),use_container_width=True,height=650)
    st.download_button(f"{k}'li aile CSV indir",tab.to_csv(index=False).encode(),"aileler.csv","text/csv")

elif section=="4 Ardışık/Komşu/Geometri":
    be=block_events(df)
    agg=be.groupby(["block","length"]).agg(events=("event_id","count"),next_full=("next_full","sum"),
        mean_next_kept=("next_kept","mean"),mean_gap=("gap_since_prev","mean")).reset_index().sort_values("events",ascending=False)
    st.dataframe(agg,use_container_width=True,height=500)
    st.subheader("REAL20 geometrisi")
    st.dataframe(geometry(df),use_container_width=True)

elif section=="5 Ritimler":
    rt=rhythm_table(df)
    st.dataframe(rt.head(5000),use_container_width=True,height=650)
    n=st.number_input("Sayı ritim kadavrası",1,80,1)
    st.dataframe(rt[rt.number==n],use_container_width=True)

elif section=="6 H1-H8 / Yaş-Uyku":
    ns=number_state(df)
    st.dataframe(ns,use_container_width=True,height=650)

elif section=="7 Bant / Son Hane":
    st.subheader("8 × 10'luk bant")
    st.dataframe(band_table(df),use_container_width=True,height=350)
    st.subheader("Aynı son hane aileleri")
    st.dataframe(suffix_table(df),use_container_width=True,height=350)

elif section=="8 Sosyal Ağ":
    pair=family_events(df,2).head(5000)
    st.caption("Kenar ağırlığı = ikilinin birlikte görülme sayısı.")
    st.dataframe(pair,use_container_width=True,height=650)

elif section=="9 Aynı REAL20 / Yakınlık":
    best,hist=real20_similarity(df)
    st.metric("Tarihsel maksimum REAL20 ↔ REAL20",best[0])
    st.write("İlk maksimum örnek:",best[1],"→",best[2])
    st.bar_chart(hist.set_index("intersection"))

elif section=="10 Walk-forward":
    warm=st.number_input("Warm-up",20,500,50)
    if st.button("Kronolojik walk-forward çalıştır",type="primary"):
        with st.spinner("Her çekiliş geçmişiyle ayrı ayrı hesaplanıyor..."):
            wf=walk_forward(df,int(warm))
        a,b,c=st.columns(3)
        a.metric("Ortalama Top20",f"{wf.hits.mean():.3f}")
        b.metric("Maksimum Top20",int(wf.hits.max()))
        c.metric("Test edilen",len(wf))
        st.bar_chart(wf.hits.value_counts().sort_index())
        st.dataframe(wf,use_container_width=True,height=500)
        st.download_button("Walk-forward CSV indir",wf.to_csv(index=False).encode(),"walk_forward.csv","text/csv")

elif section=="11 Günlük Rapor İndir":
    dates=sorted(df.date.unique())
    d=st.selectbox("Gün",dates)
    day=df[df.date==d].copy()
    st.write(f"{d} • {len(day)} çekiliş")
    rep=daily_report(day,df)
    st.text_area("Günlük araştırma çıktısı",rep,height=500)
    st.download_button("GÜNLÜK KADAVRA TXT İNDİR",rep.encode("utf-8"),f"KADAVRA_{d}.txt","text/plain")
    if st.button("14 günün tüm günlük raporlarını birleştir"):
        allrep="\n\n"+"="*80+"\n\n"
        allrep=allrep.join(daily_report(df[df.date==x].copy(),df) for x in dates)
        st.download_button("14 GÜN BİRLEŞİK RAPOR İNDİR",allrep.encode("utf-8"),"14_GUN_BIRLESIK_KADAVRA.txt","text/plain")

elif section=="12 Canlı Top20 + Kupon":
    sc=score_candidates(df)
    pool=tuple(sorted(sc.head(20).number.astype(int)))
    st.subheader("Araştırma havuzundan bir sonraki çekiliş Top20")
    st.write(pool)
    st.dataframe(sc.head(40)[["number","score","reasons","age","r5","r12","H1","H2","H3"]],use_container_width=True)
    cps=coupons_from_score(sc)
    for i,c in enumerate(cps,1): st.write(f"Kolon {i}:",c)
    key=st.text_input("Hedef çekiliş anahtarı","NEXT")
    if st.button("TOP20 + KUPONLARI DONDUR",type="primary"):
        con=sqlite3.connect(DB_FILE)
        exists=con.execute("SELECT 1 FROM predictions WHERE target_key=?",(key,)).fetchone()
        if exists: st.error("Bu hedef zaten dondurulmuş. Geçmiş tahmin değiştirilemez.")
        else:
            con.execute("INSERT INTO predictions VALUES(?,datetime('now'),?,?,?,'FROZEN',NULL,NULL)",
                (key,int(df.iloc[-1].draw_id),json.dumps(pool),json.dumps(cps)))
            con.commit(); st.success("Donduruldu.")
        con.close()

elif section=="13 Yeni Çekiliş / Doğrula":
    con=sqlite3.connect(DB_FILE)
    pred=pd.read_sql_query("SELECT * FROM predictions ORDER BY created_at DESC",con)
    con.close()
    st.subheader("Dondurulmuş tahminler")
    st.dataframe(pred,use_container_width=True)
    did=st.number_input("Yeni çekiliş no",1,step=1)
    dt=st.text_input("Tarih-saat","")
    txt=st.text_area("20 sayı, virgülle")
    target=st.text_input("Doğrulanacak hedef anahtarı","NEXT")
    if st.button("SONUCU DOĞRULA VE HAVUZA EKLE",type="primary"):
        try:
            nums=sorted({int(x.strip()) for x in txt.split(",") if x.strip()})
            if len(nums)!=20 or min(nums)<1 or max(nums)>80: raise ValueError("1–80 arasında tam 20 benzersiz sayı gir.")
            con=sqlite3.connect(DB_FILE)
            row=con.execute("SELECT top20,status FROM predictions WHERE target_key=?",(target,)).fetchone()
            if row and row[1]=="FROZEN":
                p=set(json.loads(row[0])); hits=len(p&set(nums))
                con.execute("UPDATE predictions SET status='CHECKED',actual=?,hits=? WHERE target_key=?",
                            (json.dumps(nums),hits,target))
                st.success(f"Dondurulmuş Top20 sonucu: {hits}/20")
            con.commit(); con.close()
            append_draw(did,pd.to_datetime(dt,dayfirst=True),nums)
            st.success("Yeni çekiliş araştırma havuzuna eklendi. Yeni tecrübe bir sonraki Top20'de kullanılacak.")
        except Exception as e: st.error(str(e))

st.divider()
st.caption("Araştırma kuralı: geçmiş tahminler sonuçtan sonra değiştirilmez. Walk-forward yalnız çekiliş öncesi bilgi kullanır.")
