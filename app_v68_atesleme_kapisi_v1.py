
from pathlib import Path
import io
import zipfile
import hashlib
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On V6.8 Ateşleme Kapısı V1", page_icon="🔥", layout="wide")
st.title("🔥 V6.8 — ARDIŞIK PROFESÖRÜ ATEŞLEME KAPISI V1")
st.success("KURAL DONDURULDU — bu app test sonucuna bakarak eşiği veya karakter listesini değiştirmez.")
st.caption("Amaç: V6.7'de keşfedilen aday ateşleme kapısını, daha sonraki hiç görülmemiş veride aynen sınamak.")

ROOT=Path(".v68_atesleme_v1")
ROOT.mkdir(exist_ok=True)

STRONG_CHARS={
    "COALESCE_EXPAND|HIGH|DOWN2P|UP2P",
    "EXPAND_FRAGMENT|HIGH|UP1|UP2P",
    "COALESCE_EXPAND|HIGH|FLAT|UP2P",
    "COALESCE_EXPAND|HIGH|DOWN1|UP2P",
    "COALESCE_EXPAND|HIGH|DOWN1|UP1",
}
CONF_MIN=0.80
VETO_HOURS={7,11,23}

def fp(b):
    return hashlib.sha256(b).hexdigest()[:16]

def normalize_pred(df):
    x=df.copy()
    x["hour"]=x["time"].astype(str).str.slice(0,2).astype(int)
    return x

def frozen_gate(df):
    x=normalize_pred(df)
    return (
        (x.predicted_motion.astype(str)!="SUS") &
        (x.confidence.astype(float)>=CONF_MIN) &
        (x.expert_character.astype(str).isin(STRONG_CHARS)) &
        (~x.hour.isin(VETO_HOURS))
    )

def evaluate(df):
    x=normalize_pred(df)
    m=frozen_gate(x)
    g=x[m].copy()
    summary=pd.DataFrame([{
        "signals":len(g),
        "correct":int(g.correct.sum()) if len(g) else 0,
        "accuracy":float(g.correct.mean()) if len(g) else np.nan,
        "coverage":float(len(g)/len(x)) if len(x) else 0.0
    }])
    by_day=(g.groupby("date").correct.agg(["count","sum","mean"]).reset_index()
            .rename(columns={"count":"signals","sum":"correct","mean":"accuracy"})) if len(g) else pd.DataFrame()
    by_hour=(g.groupby("hour").correct.agg(["count","sum","mean"]).reset_index()
             .rename(columns={"count":"signals","sum":"correct","mean":"accuracy"})) if len(g) else pd.DataFrame()
    by_char=(g.groupby("expert_character").correct.agg(["count","sum","mean"]).reset_index()
             .rename(columns={"count":"signals","sum":"correct","mean":"accuracy"})) if len(g) else pd.DataFrame()
    return g,summary,by_day,by_hour,by_char

st.markdown("""
**Dondurulmuş kapı:**
- confidence ≥ 0.80
- yalnız 5 güçlü ardışık uzman karakteri
- 07:xx, 11:xx, 23:xx veto
- SUS tahminler yok
""")

up=st.file_uploader("Yeni / görülmemiş Ardışık Uzman walk-forward sonuç ZIP'ini yükle", type=["zip"])
if up is None:
    st.info("Bu sürüm keşif verisini yeniden kullanmak için değil, daha sonraki görülmemiş sonuçları test etmek için hazırlandı.")
    st.stop()

raw=up.getvalue()
fid=fp(raw)
WORK=ROOT/fid
WORK.mkdir(exist_ok=True)
FINAL=WORK/"ATEŞLEME_V1_TEST_RESULTS.zip"

with zipfile.ZipFile(io.BytesIO(raw),"r") as z:
    names=z.namelist()
    # Supports V6.7-style output.
    target=None
    for cand in ["02_STATE_TRUE_WALK_FORWARD.csv","03_STATE_TRUE_WALK_FORWARD.csv","04_OOS_NUMBER_ROLE_PREDICTIONS.csv"]:
        if cand in names:
            target=cand
            break
    if target is None:
        st.error("Uygun walk-forward sonuç tablosu bulunamadı.")
        st.stop()
    pred=pd.read_csv(z.open(target))

required={"draw_no","date","time","expert_character","predicted_motion","confidence","correct"}
missing=required-set(pred.columns)
if missing:
    st.error(f"Eksik sütunlar: {sorted(missing)}")
    st.stop()

g,summary,by_day,by_hour,by_char=evaluate(pred)
st.subheader("📌 Dondurulmuş kapı sonucu")
st.dataframe(summary,use_container_width=True)
if len(g):
    st.subheader("Gün gün")
    st.dataframe(by_day,use_container_width=True)
    st.subheader("Saat saat")
    st.dataframe(by_hour,use_container_width=True)
    st.subheader("Karakter bazında")
    st.dataframe(by_char,use_container_width=True)

if st.button("⬇️ TEST SONUÇ ZIP'İNİ HAZIRLA",use_container_width=True,type="primary"):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MANIFEST.txt",
            "V6.8 ATESLEME KAPISI V1\n"
            "Kural dondurulmustur; test sonucuna gore degistirilmez.\n"
            "confidence>=0.80\n"
            "5 guclu expert_character\n"
            "07,11,23 saat veto\n"
            "SUS yok\n")
        z.writestr("01_GATE_HITS.csv",g.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("02_SUMMARY.csv",summary.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("03_BY_DAY.csv",by_day.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("04_BY_HOUR.csv",by_hour.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("05_BY_CHARACTER.csv",by_char.to_csv(index=False).encode("utf-8-sig"))
    FINAL.write_bytes(bio.getvalue())
    st.rerun()

if FINAL.exists():
    st.download_button("⬇️ V6.8 ATEŞLEME KAPISI V1 — TEST ZIP",
        FINAL.read_bytes(),
        "HIZLI_ON_V6_8_ATESLEME_KAPISI_V1_TEST_RESULTS.zip",
        "application/zip",use_container_width=True)
