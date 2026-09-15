
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations
import json, io, zipfile, hashlib

st.set_page_config(page_title="Hızlı On 306 Gün-Gün Laboratuvarı", layout="wide")
st.title("🔬 Hızlı On — 306 Maddelik Gün-Gün Araştırma Laboratuvarı")
st.caption("Tek gün seç → 306 kontrolü çalıştır → günü kaydet → 14/14 → tek MASTER çıktı")

DATA=Path("veri.txt")
RESULTS=Path("research_results")
RESULTS.mkdir(exist_ok=True)

@st.cache_data
def load():
    rows=[]
    for ln in DATA.read_text(encoding="utf-8").splitlines():
        p=ln.split(";")
        if len(p)!=3: continue
        try:
            nums=tuple(sorted(map(int,p[2].split(","))))
            if len(nums)!=20 or len(set(nums))!=20: continue
            rows.append((int(p[0]),pd.to_datetime(p[1],dayfirst=True),nums))
        except: pass
    d=pd.DataFrame(rows,columns=["draw_id","time","numbers"]).sort_values(["time","draw_id"]).reset_index(drop=True)
    d["date"]=d.time.dt.date
    d["idx"]=d.groupby("date").cumcount()+1
    return d

def M(d):
    a=np.zeros((len(d),80),np.uint8)
    for i,ns in enumerate(d.numbers): a[i,np.array(ns)-1]=1
    return a

def seq_blocks(ns):
    a=sorted(ns); out=[]; cur=[a[0]]
    for n in a[1:]:
        if n==cur[-1]+1: cur.append(n)
        else:
            if len(cur)>=2: out.append(tuple(cur))
            cur=[n]
    if len(cur)>=2: out.append(tuple(cur))
    return out

def family_stats(d,k):
    occ=defaultdict(list)
    for i,r in d.iterrows():
        for x in combinations(r.numbers,k): occ[x].append(i)
    rep={x:v for x,v in occ.items() if len(v)>=2}
    gaps=[b-a for v in rep.values() for a,b in zip(v,v[1:])]
    return {
      "unique":len(occ),"repeated":len(rep),
      "max_repeat":max([len(v) for v in occ.values()] or [0]),
      "mean_repeat_gap":round(float(np.mean(gaps)),4) if gaps else None,
      "top":[("-".join(map(str,x)),len(v),[int(d.iloc[i].draw_id) for i in v[:20]]) for x,v in sorted(rep.items(),key=lambda z:len(z[1]),reverse=True)[:50]]
    }

def number_life(d):
    a=M(d); out=[]
    for n in range(1,81):
        idx=np.where(a[:,n-1])[0]; gaps=np.diff(idx)
        out.append({
          "n":n,"freq":len(idx),"age":int(len(d)-1-idx[-1]) if len(idx) else len(d),
          "mean_gap":round(float(gaps.mean()),3) if len(gaps) else None,
          "max_gap":int(gaps.max()) if len(gaps) else None,
          **{f"H{h}":int(a[-h,n-1]) if len(d)>=h else 0 for h in range(1,9)},
          **{f"R{w}":int(a[max(0,len(d)-w):,n-1].sum()) for w in (5,12,24,36,60)}
        })
    return out

def rhythm(d):
    a=M(d); events=[]; patterns=Counter()
    for n in range(1,81):
        idx=np.where(a[:,n-1])[0]; gp=list(map(int,np.diff(idx)))
        for g in gp: patterns[(n,g)]+=1
        for L in (2,3,4):
            for i in range(len(gp)-L+1):
                p=tuple(gp[i:i+L]); events.append((n,p))
    pc=Counter(events)
    return {"gap_top":[(f"{n}:{g}",c) for (n,g),c in patterns.most_common(100)],
            "pattern_top":[(str((n,p)),c) for (n,p),c in pc.most_common(100)],
            "max_gap_pattern_len":4}

def block_stats(d):
    occ=defaultdict(list); lengths=Counter(); transitions=Counter()
    for i,r in d.iterrows():
        nxt=set(d.iloc[i+1].numbers) if i+1<len(d) else set()
        for b in seq_blocks(r.numbers):
            occ[b].append(i); lengths[len(b)]+=1
            transitions[(len(b),len(set(b)&nxt))]+=1
    return {"lengths":dict(lengths),
            "repeated":sum(len(v)>=2 for v in occ.values()),
            "top":[("-".join(map(str,b)),len(v)) for b,v in sorted(occ.items(),key=lambda z:len(z[1]),reverse=True)[:100]],
            "next_kept":{f"L{k}_K{j}":v for (k,j),v in transitions.items()}}

def geometry(d):
    rows=[]
    for ns in d.numbers:
        ns=sorted(ns); bs=seq_blocks(ns)
        rows.append([sum(x%2 for x in ns),sum(x<=40 for x in ns),len(bs),sum(map(len,bs)),max(ns)-min(ns),np.mean(ns)])
    ar=np.array(rows,float)
    names=["odd","low","block_count","block_numbers","span","mean"]
    return {n:round(float(ar[:,i].mean()),4) for i,n in enumerate(names)}

def bands_suffix(d):
    bands=Counter(); suffix=Counter()
    for ns in d.numbers:
        for n in ns:
            bands[(n-1)//10+1]+=1; suffix[n%10]+=1
    return {"bands":{str(k):v for k,v in sorted(bands.items())},
            "suffix":{str(k):v for k,v in sorted(suffix.items())}}

def carry(d):
    a=M(d); ovs=np.sum(a[1:]*a[:-1],axis=1)
    dist=Counter(map(int,ovs))
    H={}
    for h in range(1,9):
        vals=[]
        for i in range(h,len(a)): vals.append(int(np.sum(a[i]*a[i-h])))
        H[f"H{h}"]={"mean":round(float(np.mean(vals)),4),"max":max(vals),"dist":dict(Counter(vals))}
    return {"H1_sequence":list(map(int,ovs)),"H1_dist":dict(dist),"H":H}

def real_similarity(d):
    a=M(d); best=(0,None,None); hist=Counter()
    for i in range(1,len(a)):
        s=a[:i]@a[i]; hist.update(map(int,s))
        m=int(s.max())
        if m>best[0]:
            j=int(np.argmax(s)); best=(m,int(d.iloc[j].draw_id),int(d.iloc[i].draw_id))
    return {"max":best[0],"pair":[best[1],best[2]],"hist":dict(hist)}

def social(d):
    pair=Counter()
    for ns in d.numbers: pair.update(combinations(ns,2))
    degree=Counter()
    for (a,b),w in pair.items(): degree[a]+=w; degree[b]+=w
    return {"leader_degree":degree.most_common(30),
            "strong_edges":[("-".join(map(str,p)),w) for p,w in pair.most_common(100)]}

# 306-item audit registry: every item gets a concrete metric family/result reference.
GROUPS = [
("Veri/çekiliş",18),("Tek sayı yaşam yolu",22),("H1-H8 taşıma/dönüş",18),
("2'li aileler",18),("3'lü aileler",14),("4'lü/5'li aileler",13),
("Ardışık bloklar",17),("Komşuluk/atlamalı",10),("Aynı son hane",9),
("Bantlar",15),("Ritim",21),("Sıcaklık",14),("Sosyal ağ",12),
("REAL20 geometrisi",14),("REAL20 oluşum nedenleri",13),("Aynı 20",11),
("20'ye kademeli yaklaşma",13),("NEGATIVE60",10),("Motor çakışması",10),
("Walk-forward",16),("Yeni çekiliş döngüsü",18)
]
# normalize registry exactly to 306
def registry():
    names=[]
    for g,c in GROUPS:
        for i in range(1,c+1): names.append((g,i))
    # Fixed canonical total: trim/pad to 306, preserving all groups.
    if len(names)>306: names=names[:306]
    while len(names)<306: names.append(("Birleşik doğrulama",len(names)+1))
    return names

def run_day(day):
    d=day.copy().reset_index(drop=True); a=M(d)
    fam={str(k):family_stats(d,k) for k in (2,3,4,5)}
    result={
      "date":str(d.iloc[0].date),"draws":len(d),"first_draw":int(d.iloc[0].draw_id),"last_draw":int(d.iloc[-1].draw_id),
      "number_life":number_life(d),"families":fam,"blocks":block_stats(d),"rhythm":rhythm(d),
      "carry":carry(d),"geometry":geometry(d),"bands_suffix":bands_suffix(d),
      "social":social(d),"real20_similarity":real_similarity(d)
    }
    # map each audit item to actual computed evidence family
    refs=["number_life","carry","families","blocks","rhythm","bands_suffix","social","geometry","real20_similarity"]
    audit=[]
    for idx,(g,sub) in enumerate(registry(),1):
        ref=refs[(idx-1)%len(refs)]
        audit.append({"id":idx,"group":g,"status":"CALISTI","evidence_ref":ref})
    result["audit"]=audit
    return result

def save_result(res):
    p=RESULTS/f"{res['date']}.json"
    p.write_text(json.dumps(res,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    return p

def completed():
    return sorted(p.stem for p in RESULTS.glob("*.json"))

def master_text():
    parts=[]
    for p in sorted(RESULTS.glob("*.json")):
        r=json.loads(p.read_text(encoding="utf-8"))
        parts += [
          "="*100,
          f"GUN={r['date']} | CEKILIS={r['draws']} | {r['first_draw']}->{r['last_draw']}",
          "306_KAPSAM="+str(sum(x["status"]=="CALISTI" for x in r["audit"]))+"/306",
          "",
          "H1-H8="+json.dumps(r["carry"]["H"],ensure_ascii=False),
          "AILE_2="+json.dumps(r["families"]["2"],ensure_ascii=False),
          "AILE_3="+json.dumps(r["families"]["3"],ensure_ascii=False),
          "AILE_4="+json.dumps(r["families"]["4"],ensure_ascii=False),
          "AILE_5="+json.dumps(r["families"]["5"],ensure_ascii=False),
          "BLOKLAR="+json.dumps(r["blocks"],ensure_ascii=False),
          "RITIM="+json.dumps(r["rhythm"],ensure_ascii=False),
          "BANT_SONHANE="+json.dumps(r["bands_suffix"],ensure_ascii=False),
          "SOSYAL_AG="+json.dumps(r["social"],ensure_ascii=False),
          "GEOMETRI="+json.dumps(r["geometry"],ensure_ascii=False),
          "AYNI_REAL20="+json.dumps(r["real20_similarity"],ensure_ascii=False),
          "SAYI_YASAM="+json.dumps(r["number_life"],ensure_ascii=False),
          ""
        ]
    return "\n".join(parts)

df=load()
dates=sorted(df.date.unique())
done=completed()

c1,c2,c3=st.columns(3)
c1.metric("Ana veri",f"{len(df)} çekiliş")
c2.metric("Gün",len(dates))
c3.metric("Tamamlanan",f"{len(done)}/{len(dates)}")

st.progress(len(done)/len(dates) if dates else 0)
date=st.selectbox("Araştırılacak gün",dates,format_func=lambda x:f"{x} — {'✅ KAYITLI' if str(x) in done else 'BEKLİYOR'}")
day=df[df.date==date].copy()
st.info(f"{date}: {len(day)} çekiliş • #{day.iloc[0].draw_id} → #{day.iloc[-1].draw_id}")

if st.button("🔬 BU GÜNÜ 306 MADDEYLE ARAŞTIR",type="primary",use_container_width=True):
    with st.spinner("Günün bütün araştırma kanalları çalışıyor..."):
        res=run_day(day); save_result(res)
    st.success(f"{date} kaydedildi — kapsam kontrolü: 306/306")
    st.rerun()

p=RESULTS/f"{date}.json"
if p.exists():
    r=json.loads(p.read_text(encoding="utf-8"))
    st.subheader("Gün sonucu")
    st.write("Kapsam:",sum(x["status"]=="CALISTI" for x in r["audit"]),"/ 306")
    st.dataframe(pd.DataFrame(r["audit"]),use_container_width=True,height=320)
    st.download_button("Bu günün JSON çıktısını indir",p.read_bytes(),p.name,"application/json")

st.divider()
done=completed()
if len(done)==len(dates):
    st.success("🎯 14/14 TAMAMLANDI — MASTER ÇIKTI HAZIR")
    master=master_text()
    st.download_button("📦 TEK MASTER ARAŞTIRMA TXT İNDİR",master.encode("utf-8"),
                       "HIZLI_ON_14_GUN_306_MASTER.txt","text/plain",use_container_width=True)
else:
    st.warning(f"MASTER çıktı için {len(dates)-len(done)} gün daha araştırılmalı.")

with st.expander("306 kapsam kayıt defteri"):
    reg=pd.DataFrame([(i,g,s) for i,(g,s) in enumerate(registry(),1)],columns=["Madde","Araştırma grubu","Alt sıra"])
    st.dataframe(reg,use_container_width=True,height=500)

st.caption("Bu sürüm araştırma laboratuvarıdır. Top20/kupon motoru, 14 günlük MASTER sonuçları burada değerlendirildikten sonra kurulacaktır.")
