
from __future__ import annotations
import io, os, sys, zipfile, argparse
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd

CLASSES = ["SICAK","AZ_SICAK","ORTA","AZ_SOGUK","SOGUK"]
SCORE = {"SICAK":2, "AZ_SICAK":1, "ORTA":0, "AZ_SOGUK":-1, "SOGUK":-2}

def parse_txt(source):
    if hasattr(source, "read"):
        raw = source.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8-sig")
        lines = raw.splitlines()
    else:
        lines = Path(source).read_text(encoding="utf-8-sig").splitlines()
    rows=[]
    for ln in lines:
        ln=ln.strip()
        if not ln: continue
        p=ln.split(";")
        if len(p)!=3: continue
        no=int(p[0].strip())
        dt=pd.to_datetime(p[1].strip(), dayfirst=True)
        nums=[int(x) for x in p[2].split(",") if x.strip()]
        if len(nums)!=20 or len(set(nums))!=20 or min(nums)<1 or max(nums)>80:
            raise ValueError(f"Bozuk çekiliş: {no}")
        rows.append((no,dt,nums))
    df=pd.DataFrame(rows, columns=["draw_no","dt","nums"]).sort_values(["dt","draw_no"]).reset_index(drop=True)
    if df.empty: raise ValueError("Geçerli çekiliş bulunamadı.")
    df["date"]=df["dt"].dt.strftime("%d.%m.%Y")
    df["hour"]=df["dt"].dt.hour
    df["time"]=df["dt"].dt.strftime("%H:%M")
    df["sum20"]=df["nums"].map(sum)
    return df

def rank_classes(counts):
    # Deterministic: frequency desc, number asc. 16 numbers per class.
    ranked=sorted(range(1,81), key=lambda n:(-counts.get(n,0), n))
    out={}
    for i,n in enumerate(ranked):
        out[n]=CLASSES[min(i//16,4)]
    return out, ranked

def long_counts(df, group_cols):
    rows=[]
    for key,g in df.groupby(group_cols, sort=False):
        if not isinstance(key, tuple): key=(key,)
        c=Counter(n for arr in g["nums"] for n in arr)
        cls, ranked=rank_classes(c)
        total=len(g)
        for rank,n in enumerate(ranked,1):
            rec={col:val for col,val in zip(group_cols,key)}
            rec.update(number=n, frequency=c[n], draws=total,
                       pct_draws=100*c[n]/total, rank=rank, temp_class=cls[n])
            rows.append(rec)
    return pd.DataFrame(rows)

def class_lists(table, group_cols):
    rows=[]
    for key,g in table.groupby(group_cols, sort=False):
        if not isinstance(key,tuple): key=(key,)
        rec={col:val for col,val in zip(group_cols,key)}
        for cl in CLASSES:
            z=g[g.temp_class==cl].sort_values(["rank","number"])
            rec[cl]=",".join(map(str,z.number.tolist()))
        rows.append(rec)
    return pd.DataFrame(rows)

def preh_temperature(df, window=24, min_history=8):
    hist=[]
    rows=[]
    for i,r in df.iterrows():
        prior=df.iloc[max(0,i-window):i]
        if len(prior)<min_history:
            rows.append((r.draw_no, len(prior), None, None, None, None, None, None, None))
            continue
        c=Counter(n for arr in prior.nums for n in arr)
        cls,_=rank_classes(c)
        comp=Counter(cls[n] for n in r.nums)
        temp_score=sum(SCORE[cls[n]] for n in r.nums)/20.0
        hot=comp["SICAK"]+comp["AZ_SICAK"]
        cold=comp["SOGUK"]+comp["AZ_SOGUK"]
        rows.append((r.draw_no,len(prior),comp["SICAK"],comp["AZ_SICAK"],comp["ORTA"],
                     comp["AZ_SOGUK"],comp["SOGUK"],temp_score, hot-cold))
    out=pd.DataFrame(rows,columns=["draw_no","history_n","SICAK_n","AZ_SICAK_n","ORTA_n",
                                   "AZ_SOGUK_n","SOGUK_n","temp_pressure","hot_minus_cold"])
    return df.merge(out,on="draw_no",how="left")

def zone800(x):
    if x<760:return "<760"
    if x<790:return "760-789"
    if x<810:return "790-809"
    if x<830:return "810-829"
    if x<860:return "830-859"
    return "860+"

def direction(v, eps=0.05):
    if pd.isna(v): return "NA"
    if v>eps:return "UP"
    if v<-eps:return "DOWN"
    return "FLAT"

def enrich_osc(df):
    x=df.copy()
    x["pressure800"]=x["sum20"]-800
    x["zone800"]=x["sum20"].map(zone800)
    x["d800"]=x["sum20"].diff()
    x["dtemp"]=x["temp_pressure"].diff()
    x["dir800"]=x["d800"].map(lambda v: direction(v,0))
    x["dirtemp"]=x["dtemp"].map(direction)
    x["same_direction"]=np.where((x.dir800=="NA")|(x.dirtemp=="NA"),np.nan,(x.dir800==x.dirtemp).astype(int))
    x["hot_share_pct"]=100*(x["SICAK_n"]+x["AZ_SICAK_n"])/20
    x["cold_share_pct"]=100*(x["SOGUK_n"]+x["AZ_SOGUK_n"])/20
    x["temp_balance_pct"]=x["hot_share_pct"]-x["cold_share_pct"]
    return x

def transition_table(series, name):
    s=pd.Series(series).dropna().astype(str)
    prev=s.shift(1)
    z=pd.DataFrame({"from":prev,"to":s}).dropna()
    t=z.groupby(["from","to"]).size().reset_index(name="n")
    den=t.groupby("from")["n"].transform("sum")
    t["pct_from"]=100*t["n"]/den
    t.insert(0,"variable",name)
    return t.sort_values(["from","pct_from"],ascending=[True,False])

def daily_number_transitions(daily):
    p=daily.pivot(index="date",columns="number",values="temp_class")
    dates=list(p.index)
    rows=[]
    for a,b in zip(dates[:-1],dates[1:]):
        for n in range(1,81):
            ca,cb=p.loc[a,n],p.loc[b,n]
            rows.append((a,b,n,ca,cb,SCORE[cb]-SCORE[ca]))
    return pd.DataFrame(rows,columns=["date_from","date_to","number","class_from","class_to","score_delta"])

def hour_number_transitions(hourly):
    # within each day, consecutive observed hour buckets
    rows=[]
    for date,g in hourly.groupby("date",sort=False):
        p=g.pivot(index="hour",columns="number",values="temp_class").sort_index()
        hs=list(p.index)
        for a,b in zip(hs[:-1],hs[1:]):
            for n in range(1,81):
                ca,cb=p.loc[a,n],p.loc[b,n]
                rows.append((date,a,b,n,ca,cb,SCORE[cb]-SCORE[ca]))
    return pd.DataFrame(rows,columns=["date","hour_from","hour_to","number","class_from","class_to","score_delta"])

def relation_summary(x):
    z=x.dropna(subset=["temp_pressure"]).copy()
    corr=z[["sum20","pressure800","temp_pressure","hot_share_pct","cold_share_pct"]].corr()
    # temp pressure bins and next draw response
    z["temp_bin"]=pd.cut(z["temp_pressure"],[-9,-.6,-.2,.2,.6,9],
                         labels=["COK_SOGUK_BASKI","SOGUK_BASKI","DENGE","SICAK_BASKI","COK_SICAK_BASKI"])
    z["next_temp_pressure"]=z["temp_pressure"].shift(-1)
    z["next_sum20"]=z["sum20"].shift(-1)
    z["next_hot_share_pct"]=z["hot_share_pct"].shift(-1)
    z["next_cold_share_pct"]=z["cold_share_pct"].shift(-1)
    bytemp=z.groupby("temp_bin",observed=True).agg(
        n=("draw_no","size"),
        temp_pressure_mean=("temp_pressure","mean"),
        next_temp_pressure_mean=("next_temp_pressure","mean"),
        next_hot_share_pct=("next_hot_share_pct","mean"),
        next_cold_share_pct=("next_cold_share_pct","mean"),
        sum20_mean=("sum20","mean"),
        next_sum20_mean=("next_sum20","mean")
    ).reset_index()
    joint=z.groupby(["zone800","temp_bin"],observed=True).agg(
        n=("draw_no","size"), hot_share_pct=("hot_share_pct","mean"),
        cold_share_pct=("cold_share_pct","mean"), temp_pressure=("temp_pressure","mean"),
        sum20=("sum20","mean")
    ).reset_index()
    return corr,bytemp,joint

def lag_analysis(x,max_lag=12):
    z=x.dropna(subset=["temp_pressure"]).copy()
    rows=[]
    for lag in range(1,max_lag+1):
        a=z["temp_pressure"]
        b=z["temp_pressure"].shift(-lag)
        c=z["pressure800"]
        d=z["pressure800"].shift(-lag)
        e=z["temp_pressure"].shift(-lag)
        rows.append((lag,a.corr(b),c.corr(d),c.corr(e)))
    return pd.DataFrame(rows,columns=["lag_draws","temp_autocorr","pressure800_autocorr","pressure800_to_future_temp_corr"])

def build_outputs(df, window=24, min_history=8):
    daily=long_counts(df,["date"])
    hourly=long_counts(df,["date","hour"])
    overall=long_counts(df.assign(scope="14_GUN"),["scope"])
    daily_lists=class_lists(daily,["date"])
    hourly_lists=class_lists(hourly,["date","hour"])
    overall_lists=class_lists(overall,["scope"])

    pre=enrich_osc(preh_temperature(df,window,min_history))
    dtrans=daily_number_transitions(daily)
    htrans=hour_number_transitions(hourly)
    corr,bytemp,joint=relation_summary(pre)
    lags=lag_analysis(pre,12)

    temp_trans=transition_table(
        pd.cut(pre["temp_pressure"],[-9,-.6,-.2,.2,.6,9],
               labels=["COK_SOGUK_BASKI","SOGUK_BASKI","DENGE","SICAK_BASKI","COK_SICAK_BASKI"]),
        "TEMP_PRESSURE_BIN")
    z800_trans=transition_table(pre["zone800"],"ZONE800")

    # day/hour aggregate of actual PRE-H composition
    daycomp=pre.dropna(subset=["temp_pressure"]).groupby("date").agg(
        draws=("draw_no","size"),sum20_mean=("sum20","mean"),temp_pressure_mean=("temp_pressure","mean"),
        hot_share_pct_mean=("hot_share_pct","mean"),cold_share_pct_mean=("cold_share_pct","mean"),
        same_direction_pct=("same_direction","mean")
    ).reset_index()
    daycomp["same_direction_pct"]*=100
    hourcomp=pre.dropna(subset=["temp_pressure"]).groupby(["date","hour"]).agg(
        draws=("draw_no","size"),sum20_mean=("sum20","mean"),temp_pressure_mean=("temp_pressure","mean"),
        hot_share_pct_mean=("hot_share_pct","mean"),cold_share_pct_mean=("cold_share_pct","mean"),
        same_direction_pct=("same_direction","mean")
    ).reset_index()
    hourcomp["same_direction_pct"]*=100

    # strongest changers
    dchg=dtrans.assign(abs_delta=lambda q:q.score_delta.abs()).groupby("number").agg(
        transitions=("score_delta","size"),mean_abs_change=("abs_delta","mean"),
        big_jumps=("abs_delta",lambda s:int((s>=3).sum())),
        hot_to_cold=("score_delta",lambda s:int((s<=-3).sum())),
        cold_to_hot=("score_delta",lambda s:int((s>=3).sum()))
    ).reset_index().sort_values(["big_jumps","mean_abs_change"],ascending=False)

    meta=pd.DataFrame([
        ["draws",len(df)],["days",df.date.nunique()],["numbers_per_draw",20],
        ["preh_window_draws",window],["preh_min_history",min_history],
        ["temperature_classes","16 sayı x 5 sınıf; frekans sırası, eşitlikte sayı küçük olan önde"],
        ["important","Gün/saat tabloları betimleyici TAM periyot; salınım tabloları strict PRE-H rolling sınıflama kullanır."]
    ],columns=["field","value"])

    return {
        "00_META.csv":meta,
        "01_14_GUN_GENEL_SICAKLIK_1_80.csv":overall,
        "02_14_GUN_GENEL_SINIF_LISTESI.csv":overall_lists,
        "03_GUNLUK_SICAKLIK_1_80.csv":daily,
        "04_GUNLUK_SINIF_LISTELERI.csv":daily_lists,
        "05_GUN_SAAT_SICAKLIK_1_80.csv":hourly,
        "06_GUN_SAAT_SINIF_LISTELERI.csv":hourly_lists,
        "07_GUNLER_ARASI_SAYI_SICAKLIK_GECISLERI.csv":dtrans,
        "08_SAATLER_ARASI_SAYI_SICAKLIK_GECISLERI.csv":htrans,
        "09_EN_COK_KARAKTER_DEGISTIREN_SAYILAR.csv":dchg,
        "10_PREH_CEKILIS_SICAK_SOGUK_800_BASINC.csv":pre.drop(columns=["nums","dt"]),
        "11_SICAKLIK_BASINC_GECIS_YUZDELERI.csv":temp_trans,
        "12_800_ZONE_GECIS_YUZDELERI.csv":z800_trans,
        "13_800_SICAKLIK_KORELASYON.csv":corr.reset_index().rename(columns={"index":"variable"}),
        "14_SICAKLIK_BASINCI_SONRAKI_EL_ANALIZI.csv":bytemp,
        "15_800_ZONE_X_SICAKLIK_BASINCI.csv":joint,
        "16_LAG_SALINIM_ANALIZI_H1_H12.csv":lags,
        "17_GUN_BAZI_BASINC_OZETI.csv":daycomp,
        "18_GUN_SAAT_BAZI_BASINC_OZETI.csv":hourcomp,
    }

def make_summary(outputs):
    meta=outputs["00_META.csv"]
    corr=outputs["13_800_SICAKLIK_KORELASYON.csv"]
    lag=outputs["16_LAG_SALINIM_ANALIZI_H1_H12.csv"]
    chg=outputs["09_EN_COK_KARAKTER_DEGISTIREN_SAYILAR.csv"].head(20)
    lines=[
        "HIZLI ON - SICAK/SOGUK + 800 SALINIM PROFESORU",
        "",
        "KURAL:",
        "- Gün ve gün+saat sıcaklık listeleri retrospektif betimleyicidir.",
        "- Çekiliş bazlı sıcak/soğuk basınç ve 800 ilişkisi STRICT PRE-H rolling geçmişten hesaplanır.",
        "- Hedef çekiliş sonucu sıcaklık sınıfını oluşturmak için kullanılmaz.",
        "",
        "DOSYALAR:",
        "- Günlük 1-80 sıcaklık ve 5 sınıf listeleri",
        "- Gün+saat 1-80 sıcaklık ve 5 sınıf listeleri",
        "- Gün/saat sıcaklık karakter geçişleri",
        "- PRE-H sıcak-soğuk basınç, 800 basıncı ve yön salınımı",
        "- Geçiş yüzdeleri, çapraz durumlar ve H1-H12 lag analizi",
        "",
        "EN COK GUNLUK KARAKTER DEGISTIREN SAYILAR:",
        chg.to_string(index=False),
        "",
        "KORELASYON MATRISI:",
        corr.to_string(index=False),
        "",
        "LAG ANALIZI:",
        lag.to_string(index=False),
    ]
    return "\n".join(lines)

def run(input_path, out_zip, window=24, min_history=8):
    df=parse_txt(input_path)
    outputs=build_outputs(df,window,min_history)
    summary=make_summary(outputs)
    with zipfile.ZipFile(out_zip,"w",zipfile.ZIP_DEFLATED) as z:
        for name,tab in outputs.items():
            z.writestr(name,tab.to_csv(index=False,encoding="utf-8-sig"))
        z.writestr("19_OKU_BENI_OZET.txt",summary.encode("utf-8"))
    return df, outputs

def streamlit_main():
    import streamlit as st
    st.set_page_config(page_title="Hızlı On Sıcak/Soğuk + 800 Salınım Profesörü",layout="wide")
    st.title("Hızlı On — Sıcak/Soğuk + 800 Salınım Profesörü")
    st.caption("Gün + saat sıcaklık haritası, sıcak↔soğuk bağları, yüzde geçişleri ve 800 basıncı çapraz analizi.")
    # Repo içindeki ana TXT'yi otomatik bul ve doğrula.
    # Dosya adı değişse bile 3038 çekiliş / 14 gün yapısını arar.
    def discover_master():
        preferred = [
            Path("HIZLI_ON_25_08_2026_07_09_2026_TAM_14_GUN.txt"),
            Path("data/HIZLI_ON_25_08_2026_07_09_2026_TAM_14_GUN.txt"),
        ]
        candidates = preferred + sorted(Path(".").glob("*.txt")) + sorted(Path("data").glob("*.txt")) if Path("data").exists() else preferred + sorted(Path(".").glob("*.txt"))
        seen=set()
        for p in candidates:
            try:
                rp=str(p.resolve())
                if rp in seen or not p.is_file(): continue
                seen.add(rp)
                d=parse_txt(p)
                if len(d)==3038 and d["date"].nunique()==14:
                    return p, d
            except Exception:
                pass
        return None, None

    master_path, master_df = discover_master()
    if master_path is not None:
        st.success(f"Ana veri otomatik bulundu: {master_path} — {len(master_df)} çekiliş / {master_df.date.nunique()} gün")
    else:
        st.error("Repo içinde doğrulanmış 14 günlük ana TXT bulunamadı (beklenen: 3038 çekiliş / 14 gün).")

    with st.expander("İsteğe bağlı: farklı TXT ile test et"):
        f=st.file_uploader("Farklı TXT",type=["txt"])

    c1,c2=st.columns(2)
    window=c1.number_input("STRICT PRE-H rolling pencere (çekiliş)",8,120,24,1)
    min_history=c2.number_input("Minimum PRE-H geçmiş",4,60,8,1)

    source = master_path
    if f is not None:
        tmp=Path("uploaded_override.txt")
        tmp.write_bytes(f.getvalue())
        source=tmp

    if source is not None and st.button("TAM ANALİZİ ÇALIŞTIR",type="primary"):
        out=Path("HIZLI_ON_SICAK_SOGUK_800_SALINIM_TAM_CIKTI.zip")
        try:
            df,outputs=run(source,out,int(window),int(min_history))
            st.success(f"{len(df)} çekiliş / {df.date.nunique()} gün analiz edildi.")
            st.dataframe(outputs["04_GUNLUK_SINIF_LISTELERI.csv"],use_container_width=True)
            st.dataframe(outputs["17_GUN_BAZI_BASINC_OZETI.csv"],use_container_width=True)
            st.download_button("TAM ZIP ÇIKTIYI İNDİR",out.read_bytes(),out.name,"application/zip")
        except Exception as e:
            st.exception(e)

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]!="streamlit":
        ap=argparse.ArgumentParser()
        ap.add_argument("--input",required=True)
        ap.add_argument("--out",required=True)
        ap.add_argument("--window",type=int,default=24)
        ap.add_argument("--min-history",type=int,default=8)
        a=ap.parse_args()
        df,_=run(a.input,a.out,a.window,a.min_history)
        print(f"OK draws={len(df)} days={df.date.nunique()} out={a.out}")
    else:
        streamlit_main()
