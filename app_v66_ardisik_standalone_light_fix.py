
from pathlib import Path
import io
import zipfile
import hashlib
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hızlı On V6.5 Ardışık Uzman", page_icon="🧬", layout="wide")
st.title("🧬 V6.6 — ARDIŞIK UZMAN KARAKTERİ / STANDALONE LIGHT FIX")
st.success("BUILD: V6.6-STANDALONE-FIX — eski V6.3/V6.4 zinciri bu dosyada YOK.")
st.caption(
    "Bu sürüm eski V5/V6 motorlarını hiç çalıştırmaz. "
    "Sadece daha önce üretilmiş V6.1 Ardışık Profesörü ZIP'ini okur ve "
    "uzman-karakter walk-forward testini hafif, parçalı ve kalıcı şekilde yapar."
)

ROOT = Path(".v65_ardisik_light")
ROOT.mkdir(exist_ok=True)

def fp_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]

def motion_family(r):
    dc=int(r["block_count_delta_21"])
    dl=int(r["max_len_delta_21"])
    if dl>=1 and dc<=0: return "COALESCE_EXPAND"
    if dl>=1 and dc>0: return "EXPAND_FRAGMENT"
    if dl<=-1 and dc>=0: return "CONTRACT_FRAGMENT"
    if dl<=-1 and dc<0: return "CONTRACT_MERGE"
    if dc>=1: return "FRAGMENT"
    if dc<=-1: return "MERGE"
    return "STABLE"

def density_family(r):
    bc=int(r["H1_block_count"])
    ml=int(r["H1_max_len"])
    if bc>=5 or ml>=4: return "HIGH"
    if bc>=3 or ml>=3: return "MID"
    return "LOW"

def delta_band(v):
    v=int(v)
    if v<=-2:return "DOWN2P"
    if v==-1:return "DOWN1"
    if v==0:return "FLAT"
    if v==1:return "UP1"
    return "UP2P"

def build_state(chain):
    s=chain.copy()
    s["motion_family"]=s.apply(motion_family,axis=1)
    s["density_family"]=s.apply(density_family,axis=1)
    s["count_delta_band"]=s.block_count_delta_21.map(delta_band)
    s["len_delta_band"]=s.max_len_delta_21.map(delta_band)
    s["expert_character"]=(
        s.motion_family.astype(str)+"|"+
        s.density_family.astype(str)+"|"+
        s.count_delta_band.astype(str)+"|"+
        s.len_delta_band.astype(str)
    )
    s["target_block_delta"]=s.H_block_count-s.H1_block_count
    s["target_maxlen_delta"]=s.H_max_len-s.H1_max_len
    s["target_motion"]=np.select(
        [
            s.target_maxlen_delta>=1,
            s.target_maxlen_delta<=-1,
            s.target_block_delta>=1,
            s.target_block_delta<=-1
        ],
        ["EXPAND","CONTRACT","FRAGMENT","MERGE"],
        default="STABLE_OR_MORPH"
    )
    return s

def build_q2(pair):
    q=pair[pair.Q2_GATE_FROZEN==1].copy()
    if q.empty:
        return q
    q["motion_family"]=q.apply(motion_family,axis=1)
    q["density_family"]=q.apply(density_family,axis=1)
    q["count_delta_band"]=q.block_count_delta_21.map(delta_band)
    q["len_delta_band"]=q.max_len_delta_21.map(delta_band)
    q["expert_character"]=(
        q.motion_family.astype(str)+"|"+
        q.density_family.astype(str)+"|"+
        q.count_delta_band.astype(str)+"|"+
        q.len_delta_band.astype(str)
    )
    return q

def hier_pool(train,row,min_events=18):
    levels=[
        ("EXACT",["motion_family","density_family","count_delta_band","len_delta_band"]),
        ("MOTION_DENSITY_DELTA",["motion_family","density_family","count_delta_band"]),
        ("MOTION_DENSITY",["motion_family","density_family"]),
        ("MOTION_ONLY",["motion_family"]),
    ]
    for name,fs in levels:
        g=train
        for f in fs:
            g=g[g[f].astype(str)==str(row[f])]
        if len(g)>=min_events:
            return g,name
    return train.iloc[0:0],"NO_HISTORY"

def make_plan(state,warmup=900,block=120):
    draws=sorted(state.draw_no.unique())
    plan=[]
    k=1
    for pos in range(warmup,len(draws),block):
        td=draws[pos:min(pos+block,len(draws))]
        if td:
            plan.append({"block":k,"from":int(td[0]),"to":int(td[-1]),"n":len(td)})
            k+=1
    return plan

def run_one_block(state,info):
    train=state[state.draw_no<info["from"]]
    test=state[(state.draw_no>=info["from"])&(state.draw_no<=info["to"])]
    rows=[]
    for _,r in test.iterrows():
        pool,level=hier_pool(train,r,min_events=18)
        if pool.empty:
            pred="SUS"
            conf=0.0
        else:
            vc=pool.target_motion.value_counts()
            pred=str(vc.index[0])
            conf=float(vc.iloc[0]/vc.sum())
            if conf<0.42:
                pred="SUS"
        rows.append({
            "wf_block":info["block"],
            "draw_no":r.draw_no,
            "date":r.date,
            "time":r.time,
            "expert_character":r.expert_character,
            "match_level":level,
            "history_events":len(pool),
            "predicted_motion":pred,
            "confidence":conf,
            "actual_motion":r.target_motion,
            "correct":int(pred!="SUS" and pred==str(r.target_motion))
        })
    return pd.DataFrame(rows)

def run_q2_wf(q):
    if q.empty:
        return pd.DataFrame()
    draws=sorted(q.draw_no.unique())
    start=max(1,len(draws)//3)
    rows=[]
    for pos in range(start,len(draws),120):
        td=draws[pos:min(pos+120,len(draws))]
        train=q[q.draw_no<td[0]]
        test=q[q.draw_no.isin(td)]
        for _,r in test.iterrows():
            levels=[
                ("EXACT",["motion_family","density_family","count_delta_band","len_delta_band"]),
                ("MOTION_DENSITY",["motion_family","density_family"]),
                ("MOTION_ONLY",["motion_family"]),
            ]
            pool=None
            level="NO_HISTORY"
            for nm,fs in levels:
                g=train
                for f in fs:
                    g=g[g[f].astype(str)==str(r[f])]
                if len(g)>=5:
                    pool=g
                    level=nm
                    break
            rows.append({
                "draw_no":r.draw_no,
                "date":r.date,
                "time":r.time,
                "expert_character":r.expert_character,
                "match_level":level,
                "history_signals":0 if pool is None else len(pool),
                "history_hits":0 if pool is None else int(pool.Q2_HIT.sum()),
                "history_rate":np.nan if pool is None else float(pool.Q2_HIT.mean()),
                "actual_hit":int(r.Q2_HIT)
            })
    return pd.DataFrame(rows)

def reports(pred,q2pred):
    out={}
    active=pred[pred.predicted_motion!="SUS"].copy()
    by_level=(pred.groupby("match_level")
              .agg(tests=("draw_no","count"),
                   active=("predicted_motion",lambda z:int((z!="SUS").sum())),
                   correct=("correct","sum"))
              .reset_index())
    by_level["accuracy_active"]=by_level.correct/by_level.active.replace(0,np.nan)
    out["01_MATCH_LEVEL_REPORT.csv"]=by_level

    if not active.empty:
        def _confidence_band_v66(x):
            x=float(x)
            if x < 0.50: return "42-50"
            if x < 0.60: return "50-60"
            if x < 0.70: return "60-70"
            if x < 0.80: return "70-80"
            return "80-100"
        active["confidence_band"]=active.confidence.map(_confidence_band_v66)
        conf=(active.groupby("confidence_band",observed=True)
              .agg(tests=("draw_no","count"),correct=("correct","sum"))
              .reset_index())
        conf["accuracy"]=conf.correct/conf.tests
        out["02_CONFIDENCE_REPORT.csv"]=conf

    if not q2pred.empty:
        q2s=(q2pred.groupby("match_level")
             .agg(signals=("draw_no","count"),
                  actual_hits=("actual_hit","sum"),
                  avg_history_rate=("history_rate","mean"))
             .reset_index())
        q2s["actual_rate"]=q2s.actual_hits/q2s.signals
        out["03_Q2_REPORT.csv"]=q2s
    return out

def make_final(state,pred,q2,q2pred):
    bio=io.BytesIO()
    reps=reports(pred,q2pred)
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "00_MANIFEST.txt",
            "V6.6 STANDALONE LIGHT FIX ARDISIK UZMAN KARAKTERI\n"
            "Eski uygulama zinciri calismaz.\n"
            "Kaynak: V6.1 Ardışık Profesörü sonuç ZIP'i.\n"
            "PRE-H uzman karakter -> dondurulmus blok walk-forward -> POST-H dogrulama.\n"
            "Q2 tanimi degistirilmez.\n"
        )
        z.writestr("01_EXPERT_STATE_TIMELINE.csv",state.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("02_STATE_TRUE_WALK_FORWARD.csv",pred.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("03_Q2_EVENTS.csv",q2.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("04_Q2_TRUE_WALK_FORWARD.csv",q2pred.to_csv(index=False).encode("utf-8-sig"))
        for fn,t in reps.items():
            z.writestr("05_REPORTS/"+fn,t.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

up=st.file_uploader("V6.1 sonuç ZIP'ini yükle",type=["zip"])
if up is None:
    st.info("Yüklemen gereken dosya: HIZLI_ON_V6_1_UZMAN01_ARDISIK_PROFESORU_RESULTS.zip")
    st.stop()

raw=up.getvalue()
fid=fp_bytes(raw)
WORK=ROOT/fid
WORK.mkdir(exist_ok=True)
WF=WORK/"wf"
WF.mkdir(exist_ok=True)
SOURCE=WORK/"source.zip"
if not SOURCE.exists():
    SOURCE.write_bytes(raw)

BASE=WORK/"state.pkl"
Q2=WORK/"q2.pkl"
Q2WF=WORK/"q2wf.pkl"
FINAL=WORK/"RESULTS.zip"

st.write(f"Kaynak fingerprint: `{fid}`")

if not BASE.exists():
    if st.button("1️⃣ UZMAN KARAKTER TABANINI HAZIRLA",use_container_width=True,type="primary"):
        ss=st.status("Sadece V6.1 şekil-zinciri okunuyor…",expanded=True)
        try:
            with zipfile.ZipFile(io.BytesIO(raw),"r") as z:
                chain=pd.read_csv(z.open("04_SHAPE_CHAIN_H3_H2_H1.csv"))
            state=build_state(chain)
            pd.to_pickle(state,BASE)
            ss.write(f"Durum satırı: {len(state):,}")
            ss.update(label="✅ Hafif uzman karakter tabanı hazır",state="complete",expanded=False)
            st.rerun()
        except Exception as e:
            ss.update(label="❌ Taban hazırlanamadı",state="error",expanded=True)
            st.exception(e)
    st.stop()

state=pd.read_pickle(BASE)
plan=make_plan(state,warmup=900,block=120)
done={i["block"]:WF/f"wf_{i['block']:02d}.pkl" for i in plan if (WF/f"wf_{i['block']:02d}.pkl").exists()}

st.success(f"✅ Uzman karakter tabanı hazır: {len(state):,} satır")
st.progress(len(done)/len(plan) if plan else 1.0,text=f"Walk-forward: {len(done)}/{len(plan)} blok")

if len(done)<len(plan):
    if st.button("2️⃣ SONRAKİ WALK-FORWARD BLOĞUNU TEST ET",use_container_width=True,type="primary"):
        info=next(i for i in plan if i["block"] not in done)
        ss=st.status(f"WF blok {info['block']}/{len(plan)} çalışıyor…",expanded=True)
        try:
            r=run_one_block(state,info)
            pd.to_pickle(r,WF/f"wf_{info['block']:02d}.pkl")
            active=r[r.predicted_motion!="SUS"]
            ss.write(f"Aktif tahmin: {len(active)}")
            ss.write(f"Doğru: {int(active.correct.sum()) if len(active) else 0}")
            ss.write(f"Accuracy: {float(active.correct.mean()):.3f}" if len(active) else "Accuracy: —")
            ss.update(label=f"✅ WF blok {info['block']} kalıcı kaydedildi",state="complete",expanded=False)
            st.rerun()
        except Exception as e:
            ss.update(label=f"❌ WF blok {info['block']} hata verdi",state="error",expanded=True)
            st.exception(e)

done={i["block"]:WF/f"wf_{i['block']:02d}.pkl" for i in plan if (WF/f"wf_{i['block']:02d}.pkl").exists()}

if len(done)==len(plan):
    st.success("✅ Tüm walk-forward blokları hazır.")
    if not Q2.exists():
        if st.button("3️⃣ Q2 VERİSİNİ HAZIRLA",use_container_width=True,type="primary"):
            ss=st.status("Sadece V6.1 pair tablosu okunup Q2 sinyalleri süzülüyor…",expanded=True)
            try:
                with zipfile.ZipFile(SOURCE,"r") as z:
                    pair=pd.read_csv(z.open("02_PAIR_STATE_TRANSITIONS.csv"))
                q2=build_q2(pair)
                pd.to_pickle(q2,Q2)
                ss.write(f"Q2 sinyali: {len(q2):,}")
                ss.update(label="✅ Q2 veri tabanı hazır",state="complete",expanded=False)
                st.rerun()
            except Exception as e:
                ss.update(label="❌ Q2 hazırlanamadı",state="error",expanded=True)
                st.exception(e)

if Q2.exists() and len(done)==len(plan):
    q2=pd.read_pickle(Q2)
    if not Q2WF.exists():
        if st.button("4️⃣ Q2 WALK-FORWARD TESTİNİ ÇALIŞTIR",use_container_width=True,type="primary"):
            ss=st.status("Q2 walk-forward çalışıyor…",expanded=True)
            try:
                q2pred=run_q2_wf(q2)
                pd.to_pickle(q2pred,Q2WF)
                ss.write(f"Q2 WF satırı: {len(q2pred):,}")
                ss.update(label="✅ Q2 walk-forward hazır",state="complete",expanded=False)
                st.rerun()
            except Exception as e:
                ss.update(label="❌ Q2 walk-forward hata verdi",state="error",expanded=True)
                st.exception(e)

if Q2WF.exists() and len(done)==len(plan):
    if not FINAL.exists():
        if st.button("5️⃣ TEK SONUÇ ZIP'İNİ OLUŞTUR",use_container_width=True,type="primary"):
            ss=st.status("Sonuçlar birleştiriliyor…",expanded=True)
            try:
                preds=[pd.read_pickle(WF/f"wf_{i['block']:02d}.pkl") for i in plan]
                pred=pd.concat(preds,ignore_index=True) if preds else pd.DataFrame()
                q2=pd.read_pickle(Q2)
                q2pred=pd.read_pickle(Q2WF)
                FINAL.write_bytes(make_final(state,pred,q2,q2pred))
                ss.update(label="✅ V6.5 final ZIP hazır",state="complete",expanded=False)
                st.rerun()
            except Exception as e:
                ss.update(label="❌ Final ZIP oluşturulamadı",state="error",expanded=True)
                st.exception(e)

if FINAL.exists():
    st.download_button(
        "⬇️ V6.6 ARDIŞIK UZMAN KARAKTERİ — TEK ZIP",
        FINAL.read_bytes(),
        "HIZLI_ON_V6_6_ARDISIK_UZMAN_KARAKTERI_RESULTS.zip",
        "application/zip",
        use_container_width=True
    )
