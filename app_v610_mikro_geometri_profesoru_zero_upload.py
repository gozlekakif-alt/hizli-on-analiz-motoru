from pathlib import Path
import io,zipfile,gzip,base64
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="V6.10 Mikro-Geometri Profesörü",page_icon="🔬",layout="wide")
st.title("🔬 V6.10 — ARDIŞIK MİKRO-GEOMETRİ PROFESÖRÜ")
st.success("ZERO-UPLOAD — V6.9 kapı olayları + gerekli V6.1 PRE-H blokları app içine gömülü.")
st.caption("161/152/9 kapısı SABİT. Yalnız H-3→H-2→H-1 ön-geometrisi incelenir. H hedef bloğu özellik üretiminde kullanılmaz; yeni veto otomatik yazılmaz.")

GATE_B64="""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"""
PRE_B64="""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"""

@st.cache_data
def load():
    g=pd.read_csv(io.BytesIO(gzip.decompress(base64.b64decode(GATE_B64))))
    p=pd.read_csv(io.BytesIO(gzip.decompress(base64.b64decode(PRE_B64))))
    return g,p

def parse_block(x):
    if pd.isna(x): return None
    try:return tuple(int(v) for v in str(x).split("-"))
    except:return None

def blocks_for(pre,draw):
    q=pre[(pre.draw_no.astype(int)==int(draw)) & pre.pre_block.notna()]
    out=[]
    for x in q.pre_block:
        b=parse_block(x)
        if b:out.append(b)
    return out

def center(b): return sum(b)/len(b)

def transition(a,b):
    # PRE-only transition A -> B. Greedy maximum-overlap matching.
    pairs=[]
    candidates=[]
    for i,x in enumerate(a):
        sx=set(x)
        for j,y in enumerate(b):
            sy=set(y); inter=len(sx&sy); union=len(sx|sy)
            jac=inter/union if union else 0
            if inter:candidates.append((jac,inter,-abs(center(y)-center(x)),i,j))
    useda=set();usedb=set()
    for jac,inter,negdr,i,j in sorted(candidates,reverse=True):
        if i in useda or j in usedb:continue
        useda.add(i);usedb.add(j);pairs.append((a[i],b[j],jac))
    exact=shiftL=shiftR=grow=shrink=morph=0; drifts=[]
    for x,y,jac in pairs:
        dx=center(y)-center(x); drifts.append(dx)
        if x==y:exact+=1
        elif len(x)==len(y) and all(y[k]==x[k]-1 for k in range(len(x))):shiftL+=1
        elif len(x)==len(y) and all(y[k]==x[k]+1 for k in range(len(x))):shiftR+=1
        elif set(x).issubset(set(y)) and len(y)>len(x):grow+=1
        elif set(y).issubset(set(x)) and len(y)<len(x):shrink+=1
        else:morph+=1
    return {
      "birth":len(b)-len(usedb),"death":len(a)-len(useda),"matched":len(pairs),
      "exact":exact,"shift_left":shiftL,"shift_right":shiftR,"grow":grow,"shrink":shrink,"morph":morph,
      "mean_abs_drift":float(np.mean(np.abs(drifts))) if drifts else np.nan,
      "net_drift":float(np.mean(drifts)) if drifts else np.nan
    }

def snapshot(bs,prefix):
    lens=[len(x) for x in bs]
    members=set(v for b in bs for v in b)
    return {
      f"{prefix}_blocks":len(bs),
      f"{prefix}_members":len(members),
      f"{prefix}_maxlen":max(lens) if lens else 0,
      f"{prefix}_meanlen":float(np.mean(lens)) if lens else 0,
      f"{prefix}_long3p":sum(v>=3 for v in lens),
      f"{prefix}_long4p":sum(v>=4 for v in lens)
    }

def build(g,pre):
    rows=[]
    for _,r in g.iterrows():
        d=int(r.draw_no)
        h3=blocks_for(pre,d-2); h2=blocks_for(pre,d-1); h1=blocks_for(pre,d)
        t32=transition(h3,h2);t21=transition(h2,h1)
        z=r.to_dict()
        z.update(snapshot(h3,"H3"));z.update(snapshot(h2,"H2"));z.update(snapshot(h1,"H1"))
        z.update({"T32_"+k:v for k,v in t32.items()})
        z.update({"T21_"+k:v for k,v in t21.items()})
        z["pre_birth_accel"]=t21["birth"]-t32["birth"]
        z["pre_death_accel"]=t21["death"]-t32["death"]
        z["pre_shift_balance"]=(t21["shift_right"]-t21["shift_left"])
        z["pre_longblock_delta"]=z["H1_long3p"]-z["H2_long3p"]
        z["pre_member_delta"]=z["H1_members"]-z["H2_members"]
        rows.append(z)
    return pd.DataFrame(rows)

def compare(x):
    numeric=[
      "H3_blocks","H2_blocks","H1_blocks","H3_members","H2_members","H1_members",
      "H3_maxlen","H2_maxlen","H1_maxlen","H1_long3p","H1_long4p",
      "T32_birth","T32_death","T32_exact","T32_shift_left","T32_shift_right","T32_grow","T32_shrink","T32_morph","T32_mean_abs_drift",
      "T21_birth","T21_death","T21_exact","T21_shift_left","T21_shift_right","T21_grow","T21_shrink","T21_morph","T21_mean_abs_drift",
      "pre_birth_accel","pre_death_accel","pre_shift_balance","pre_longblock_delta","pre_member_delta"]
    rows=[]
    for c in numeric:
        a=x[x.correct==1][c].dropna();b=x[x.correct==0][c].dropna()
        rows.append({"feature":c,"correct_mean":a.mean(),"wrong_mean":b.mean(),
                     "difference_wrong_minus_correct":b.mean()-a.mean(),
                     "correct_median":a.median(),"wrong_median":b.median()})
    return pd.DataFrame(rows).sort_values("difference_wrong_minus_correct",key=lambda s:s.abs(),ascending=False)

g,pre=load()
x=build(g,pre)
cmp=compare(x)
good=x[x.correct==1];bad=x[x.correct==0]

c1,c2,c3=st.columns(3)
c1.metric("Kapı olayı",len(x));c2.metric("Doğru",len(good));c3.metric("Yanlış",len(bad))

st.subheader("1 — 9 YANLIŞIN PRE-H MİKRO-GEOMETRİSİ")
show=["draw_no","date","time","expert_character","actual_motion",
"H3_blocks","H2_blocks","H1_blocks","H3_maxlen","H2_maxlen","H1_maxlen",
"T32_birth","T32_death","T32_exact","T32_shift_left","T32_shift_right","T32_grow","T32_shrink","T32_morph",
"T21_birth","T21_death","T21_exact","T21_shift_left","T21_shift_right","T21_grow","T21_shrink","T21_morph",
"pre_birth_accel","pre_death_accel","pre_shift_balance","pre_member_delta"]
st.dataframe(bad[show],use_container_width=True,hide_index=True)

st.subheader("2 — 152 DOĞRU vs 9 YANLIŞ / PRE-H FARKLARI")
st.dataframe(cmp,use_container_width=True,hide_index=True)

st.subheader("3 — H2→H1 HAREKET YOĞUNLUKLARI")
cols=["T21_birth","T21_death","T21_exact","T21_shift_left","T21_shift_right","T21_grow","T21_shrink","T21_morph"]
prof=pd.DataFrame([
 {"group":"DOGRU","n":len(good),**{c:good[c].mean() for c in cols}},
 {"group":"YANLIS","n":len(bad),**{c:bad[c].mean() for c in cols}}
])
st.dataframe(prof,use_container_width=True,hide_index=True)

st.subheader("4 — KARAKTER × PRE-H GEOMETRİ")
x["geom_key"]=(
 x.H1_blocks.astype(str)+"B|L"+x.H1_maxlen.astype(str)+
 "|BIRTH"+x.T21_birth.astype(str)+"|DEATH"+x.T21_death.astype(str)+
 "|EX"+x.T21_exact.astype(str)+"|SR"+x.T21_shift_right.astype(str)+
 "|SL"+x.T21_shift_left.astype(str))
geo=(x.groupby(["expert_character","geom_key"]).agg(signals=("draw_no","count"),correct=("correct","sum")).reset_index())
geo["wrong"]=geo.signals-geo.correct;geo["accuracy"]=geo.correct/geo.signals
st.dataframe(geo.sort_values(["wrong","signals"],ascending=[False,False]),use_container_width=True,hide_index=True)

st.warning("METODOLOJİ KİLİDİ: Buradaki farklar keşif bulgusudur. H hedefi yalnız 'doğru/yanlış' etiketi olarak kullanılır; mikro-geometri H-3/H-2/H-1'den hesaplanır. Bu 9 hataya bakarak otomatik veto eklenmez.")

bio=io.BytesIO()
with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
    z.writestr("00_MANIFEST.txt","V6.10 MIKRO-GEOMETRI PROFESORU\n161/152/9 gate sabit.\nOzellikler yalniz PRE-H: H3,H2,H1 blok kimlikleri ve iki pre gecis.\nH sonucu ozellik uretiminde kullanilmaz. Yeni veto otomatik uretilmez.\n")
    z.writestr("01_GATE_WITH_PRE_MICRO_GEOMETRY.csv",x.to_csv(index=False).encode("utf-8-sig"))
    z.writestr("02_WRONG_9_PRE_GEOMETRY.csv",bad.to_csv(index=False).encode("utf-8-sig"))
    z.writestr("03_CORRECT_152_PRE_GEOMETRY.csv",good.to_csv(index=False).encode("utf-8-sig"))
    z.writestr("04_GOOD_BAD_FEATURE_COMPARISON.csv",cmp.to_csv(index=False).encode("utf-8-sig"))
    z.writestr("05_T21_EVENT_PROFILE.csv",prof.to_csv(index=False).encode("utf-8-sig"))
    z.writestr("06_CHARACTER_GEOMETRY_MAP.csv",geo.to_csv(index=False).encode("utf-8-sig"))
st.download_button("⬇️ V6.10 MİKRO-GEOMETRİ — TEK ZIP",bio.getvalue(),"HIZLI_ON_V6_10_MIKRO_GEOMETRI_PROFESORU.zip","application/zip",use_container_width=True)
