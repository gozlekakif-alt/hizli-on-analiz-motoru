# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict
import hashlib, re, math

st.set_page_config(page_title="Hızlı On — Oyun Kimliği", layout="wide")
st.title("🧬 Hızlı On — Profesyonel Oyun Kimliği / Yaşam İzi Motoru")
st.caption("25.08.2026–29.09.2026 • Gün gün işler • Kupon üretmez • Sonda tek TXT rapor")

START = pd.Timestamp("2026-08-25 00:00:00")
END   = pd.Timestamp("2026-09-29 23:59:59")
FIRST3=("02","07","12")
SECOND3=("17","22","27")
FIRST6=FIRST3+SECOND3
LAST6=("32","37","42","47","52","57")
HOUR12=FIRST6+LAST6
CLASSES=(0,1,2,3)
FAMILIES=tuple(f"{a}/3→{b}/3" for a in CLASSES for b in CLASSES)
STATE_ORDER={"COLD":0,"COOL":1,"NEUTRAL":2,"HOT":3,"VERY_HOT":4}

def parse_line(line):
    s=line.strip()
    if not s or s.startswith(("=","#")): return None
    m=re.match(r"^\s*(\d+)\s*;\s*([^;]+?)\s*;\s*(.+?)\s*$",s)
    if not m:
        m=re.match(r"^\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$",s)
    if not m: return None
    try:
        draw_id=int(m.group(1))
        dt=pd.to_datetime(m.group(2).strip(),dayfirst=True,errors="raise")
        nums=sorted(set(int(x) for x in re.findall(r"\d+",m.group(3))))
    except Exception:
        return None
    if len(nums)!=20 or min(nums)<1 or max(nums)>80: return None
    return draw_id,dt,tuple(nums)

@st.cache_data(show_spinner=False)
def parse_text(raw,digest):
    rows=[]; rejected=0
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith(("=","#")): continue
        x=parse_line(line)
        if x: rows.append(x)
        elif re.search(r"\d",line): rejected+=1
    if not rows: raise ValueError("Geçerli çekiliş bulunamadı.")
    df=pd.DataFrame(rows,columns=["draw_id","time","numbers"])
    before=len(df)
    df=df.sort_values(["time","draw_id"]).drop_duplicates("draw_id",keep="last").reset_index(drop=True)
    return df,rejected,before-len(df)

def read_source(uploaded):
    if uploaded is not None:
        b=uploaded.getvalue()
        return b.decode("utf-8-sig",errors="replace"),uploaded.name
    p=Path("veri.txt")
    if p.exists():
        return p.read_text(encoding="utf-8-sig",errors="replace"),"repo/veri.txt"
    return None,None

def band(n): return (n-1)//10+1

def hour_state(c):
    if c<=1:return "COLD"
    if c==2:return "COOL"
    if c==3:return "NEUTRAL"
    if c<=5:return "HOT"
    return "VERY_HOT"

def z_state(c,n):
    if n<=0:return "NEUTRAL",0.0
    mu=n*.25; sd=math.sqrt(n*.25*.75)
    z=(c-mu)/sd if sd else 0
    if z<=-1.5:return "VERY_COLD",z
    if z<=-.5:return "COLD",z
    if z<.5:return "NEUTRAL",z
    if z<1.5:return "WARM",z
    return "HOT",z

def maxrun(arr,val):
    b=c=0
    for x in arr:
        if int(x)==val:c+=1;b=max(b,c)
        else:c=0
    return b

def chain_runs(nums):
    s=sorted(nums); out=[]
    if not s:return out
    cur=[s[0]]
    for x in s[1:]:
        if x==cur[-1]+1:cur.append(x)
        else:
            if len(cur)>=2:out.append(tuple(cur))
            cur=[x]
    if len(cur)>=2:out.append(tuple(cur))
    return out

def fmt_nums(xs): return ",".join(map(str,xs)) if xs else "-"

@st.cache_data(show_spinner=False)
def analyze_day(serial,day_key,digest):
    day=pd.DataFrame(serial,columns=["draw_id","time","numbers"]).sort_values(["time","draw_id"]).reset_index(drop=True)
    N=len(day)
    mat=np.zeros((N,80),dtype=np.uint8)
    for i,r in enumerate(day.itertuples(index=False)):
        for n in r.numbers:mat[i,n-1]=1
    csum=np.cumsum(mat,axis=0)

    life=[]
    for n in range(1,81):
        arr=mat[:,n-1]
        pos=(np.where(arr==1)[0]+1).tolist()
        gaps=np.diff(pos).tolist() if len(pos)>=2 else []
        gc=Counter(gaps)
        mode_gap,mode_n=(gc.most_common(1)[0] if gc else (None,0))
        rhythm=mode_n/len(gaps) if gaps else 0.0
        pairc=Counter(zip(gaps[:-1],gaps[1:])) if len(gaps)>=2 else Counter()
        top_pair,pair_n=(pairc.most_common(1)[0] if pairc else (None,0))
        state,z=z_state(int(arr.sum()),N)
        life.append(dict(number=n,freq=int(arr.sum()),state=state,z=z,
                         first=pos[0] if pos else None,last=pos[-1] if pos else None,
                         hitrun=maxrun(arr,1),missrun=maxrun(arr,0),
                         mode_gap=mode_gap,mode_n=mode_n,rhythm=rhythm,
                         top_pair=top_pair,pair_n=pair_n,
                         bits="".join("1" if x else "0" for x in arr.tolist())))

    daily_hot=[x["number"] for x in life if x["state"]=="HOT"]
    daily_warm=[x["number"] for x in life if x["state"]=="WARM"]
    daily_cold=[x["number"] for x in life if x["state"]=="COLD"]
    daily_vcold=[x["number"] for x in life if x["state"]=="VERY_COLD"]

    buckets=defaultdict(dict)
    for i,r in enumerate(day.itertuples(index=False)):
        mm=r.time.strftime("%M")
        if mm in HOUR12:
            buckets[r.time.strftime("%H")][mm]=(i,int(r.draw_id),set(r.numbers),r.time)

    hours=[]; partial=[]; prev_states=None; quota_rows=[]; stageA=[]; stageB=[]
    for hh in sorted(buckets):
        d=buckets[hh]
        missing=[m for m in HOUR12 if m not in d]
        if missing:
            partial.append((hh,missing)); continue
        sets={m:d[m][2] for m in HOUR12}
        c1={n:sum(n in sets[m] for m in FIRST3) for n in range(1,81)}
        c2={n:sum(n in sets[m] for m in SECOND3) for n in range(1,81)}
        c6={n:c1[n]+c2[n] for n in range(1,81)}
        fam={n:f"{c1[n]}/3→{c2[n]}/3" for n in range(1,81)}
        q1=[sum(c1[n]==k for n in range(1,81)) for k in CLASSES]
        q2=[sum(c2[n]==k for n in range(1,81)) for k in CLASSES]
        q6=[sum(c6[n]==k for n in range(1,81)) for k in range(7)]
        trans=np.zeros((4,4),dtype=int)
        for n in range(1,81):trans[c1[n],c2[n]]+=1

        hf={n:sum(n in sets[m] for m in HOUR12) for n in range(1,81)}
        hs={n:hour_state(hf[n]) for n in range(1,81)}
        first_idx=d["02"][0]
        before_n=first_idx
        before_counts=csum[first_idx-1] if first_idx>0 else np.zeros(80,dtype=int)
        start_state={}
        start_z={}
        for n in range(1,81):
            ss,zz=z_state(int(before_counts[n-1]),before_n)
            start_state[n]=ss;start_z[n]=zz

        to_hot=[];to_cold=[];jump_up=[];jump_down=[]
        if prev_states:
            for n in range(1,81):
                a=STATE_ORDER[prev_states[n]];b=STATE_ORDER[hs[n]]
                if hs[n] in ("HOT","VERY_HOT") and prev_states[n] not in ("HOT","VERY_HOT"):to_hot.append(n)
                if hs[n] in ("COLD","COOL") and prev_states[n] not in ("COLD","COOL"):to_cold.append(n)
                if b-a>=2:jump_up.append(n)
                if a-b>=2:jump_down.append(n)

        exact={4:[],5:[],6:[],7:[],8:[]}
        plus=[]
        for n,count in hf.items():
            if count==4:exact[4].append(n)
            elif count==5:exact[5].append(n)
            elif count==6:exact[6].append(n)
            elif count==7:exact[7].append(n)
            elif count>=8:exact[8].append(n)
            if count>=4:
                plus.append(dict(number=n,freq=count,first3=c1[n],second3=c2[n],
                                 family=fam[n],first6=c6[n],hour_state=hs[n],
                                 start_state=start_state[n],start_z=start_z[n],band=band(n)))
        plus=sorted(plus,key=lambda x:(-x["freq"],x["number"]))

        targets={}; seqA=[];seqB=[]
        for t in LAST6:
            real=sets[t]
            A=[sum(1 for n in real if c1[n]==k) for k in CLASSES]
            B=[sum(1 for n in real if c2[n]==k) for k in CLASSES]
            F6=[sum(1 for n in real if c6[n]==k) for k in range(7)]
            Fam={f:sum(1 for n in real if fam[n]==f) for f in FAMILIES}
            expA=[q1[k]/4 for k in CLASSES]
            expB=[q2[k]/4 for k in CLASSES]
            expF6=[q6[k]/4 for k in range(7)]
            expFam={f:trans[int(f[0]),int(f[4])]/4 for f in FAMILIES}
            surA=[A[k]-expA[k] for k in CLASSES]
            surB=[B[k]-expB[k] for k in CLASSES]
            surF=[F6[k]-expF6[k] for k in range(7)]
            surFam={f:Fam[f]-expFam[f] for f in FAMILIES}
            domA=int(np.argmax(surA));domB=int(np.argmax(surB))
            domF=max(FAMILIES,key=lambda f:(surFam[f],Fam[f]))
            seqA.append(domA);seqB.append(domB)
            targets[t]=dict(A=A,B=B,F6=F6,Fam=Fam,expA=expA,expB=expB,expF6=expF6,
                            expFam=expFam,domA=domA,domB=domB,domF=domF)

            for k in CLASSES:
                quota_rows.append((day_key,hh,t,"FIRST3",f"{k}/3",q1[k],expA[k],A[k]))
                quota_rows.append((day_key,hh,t,"SECOND3",f"{k}/3",q2[k],expB[k],B[k]))
            for k in range(7):
                quota_rows.append((day_key,hh,t,"FIRST6",f"{k}/6",q6[k],expF6[k],F6[k]))
            for f in FAMILIES:
                pool=int(trans[int(f[0]),int(f[4])])
                quota_rows.append((day_key,hh,t,"FAMILY",f,pool,expFam[f],Fam[f]))

        chaincount=Counter(); chaintrans=Counter(); runs_by={}
        for m in HOUR12:
            rr=chain_runs(sets[m]);runs_by[m]=rr
            for r in rr:
                chaincount["2" if len(r)==2 else "3" if len(r)==3 else "4+"]+=1
        for i in range(11):
            a,b=HOUR12[i],HOUR12[i+1]
            for r1 in runs_by[a]:
                for r2 in runs_by[b]:
                    if set(r1)&set(r2) or abs(r1[0]-r2[0])<=2:
                        l1="4+" if len(r1)>=4 else str(len(r1))
                        l2="4+" if len(r2)>=4 else str(len(r2))
                        sh=max(-3,min(3,r2[0]-r1[0]))
                        chaintrans[f"{l1}→{l2} shift={sh:+d}"]+=1

        hours.append(dict(hour=hh,q1=q1,q2=q2,q6=q6,trans=trans.tolist(),
                          hour_states=hs,to_hot=to_hot,to_cold=to_cold,
                          jump_up=jump_up,jump_down=jump_down,exact=exact,plus=plus,
                          targets=targets,seqA=seqA,seqB=seqB,
                          chaincount=dict(chaincount),chaintrans=dict(chaintrans)))
        stageA.append(tuple(seqA));stageB.append(tuple(seqB))
        prev_states=hs

    daily_chain=Counter()
    daily_examples=defaultdict(list)
    for r in day.itertuples(index=False):
        for rr in chain_runs(set(r.numbers)):
            k="2" if len(rr)==2 else "3" if len(rr)==3 else "4+"
            daily_chain[k]+=1
            if len(daily_examples[k])<8:daily_examples[k].append((r.time.strftime("%H:%M"),rr))

    rhythm=[x for x in life if x["freq"]>=8 and x["rhythm"]>=.18]
    rhythm=sorted(rhythm,key=lambda x:(-x["rhythm"],-x["mode_n"],x["number"]))[:20]

    return dict(date=day_key,draw_count=N,life=life,
                daily_hot=daily_hot,daily_warm=daily_warm,daily_cold=daily_cold,daily_vcold=daily_vcold,
                hours=hours,partial=partial,quota_rows=quota_rows,stageA=stageA,stageB=stageB,
                daily_chain=dict(daily_chain),daily_examples=dict(daily_examples),rhythm=rhythm)

def aggregate(results):
    rows=[]
    for d in results:rows.extend(d["quota_rows"])
    q=pd.DataFrame(rows,columns=["date","hour","target","source","class","pool","expected","actual"])
    agg=[]
    if not q.empty:
        for (t,s,c),g in q.groupby(["target","source","class"],sort=False):
            pool=g.pool.astype(float); actual=g.actual.astype(float); exp=g.expected.astype(float)
            corr=pool.corr(actual) if pool.std()>0 and actual.std()>0 else np.nan
            me=exp.mean();ma=actual.mean()
            agg.append(dict(target=t,source=s,cls=c,hours=len(g),mean_pool=pool.mean(),
                            mean_expected=me,mean_actual=ma,lift=ma/me if me else np.nan,
                            mean_surge=(actual-exp).mean(),
                            positive_surge_pct=100*(actual>exp).mean(),corr=corr))
    A=[];B=[]
    for d in results:A.extend(d["stageA"]);B.extend(d["stageB"])
    def transitions(seqs):
        out={}
        for i in range(5):
            c=Counter((s[i],s[i+1]) for s in seqs)
            out[f":{LAST6[i]}→:{LAST6[i+1]}"]=c
        return out
    return q,pd.DataFrame(agg),A,transitions(A),B,transitions(B)

def day_report(d):
    L=[]
    L.append("="*105)
    L.append(f"GÜN {d['date']} | çekiliş={d['draw_count']} | tam saat={len(d['hours'])} | eksik saat={len(d['partial'])}")
    L.append("="*105)
    L.append("\n[1] GÜNLÜK SICAK/SOĞUK")
    L.append("HOT: "+fmt_nums(d["daily_hot"]))
    L.append("WARM: "+fmt_nums(d["daily_warm"]))
    L.append("COLD: "+fmt_nums(d["daily_cold"]))
    L.append("VERY_COLD: "+fmt_nums(d["daily_vcold"]))

    L.append("\n[2] 1–80 YAŞAM İZİ")
    L.append("sayı|freq|durum|z|ilk|son|hitrun|missrun|modegap|ritim|217-bit yaşam izi")
    for x in d["life"]:
        mg="-" if x["mode_gap"] is None else f"{x['mode_gap']}x{x['mode_n']}"
        L.append(f"{x['number']:02d}|{x['freq']}|{x['state']}|{x['z']:+.2f}|{x['first'] or '-'}|{x['last'] or '-'}|"
                 f"{x['hitrun']}|{x['missrun']}|{mg}|{x['rhythm']:.3f}|{x['bits']}")

    L.append("\n[3] RİTİM ADAYLARI")
    for x in d["rhythm"]:
        pair="-" if x["top_pair"] is None else f"{x['top_pair'][0]}-{x['top_pair'][1]} x{x['pair_n']}"
        L.append(f"{x['number']:02d}: F={x['freq']} modegap={x['mode_gap']} x{x['mode_n']} ritim={x['rhythm']:.3f} pair={pair}")
    if not d["rhythm"]:L.append("-")

    L.append("\n[4] GÜNLÜK ARDIŞIK ZİNCİR")
    L.append(f"2'li={d['daily_chain'].get('2',0)} | 3'lü={d['daily_chain'].get('3',0)} | 4+={d['daily_chain'].get('4+',0)}")
    for k in ("2","3","4+"):
        ex=d["daily_examples"].get(k,[])
        if ex:L.append(f"{k} örnek: "+" ; ".join(f"{t}:{'-'.join(map(str,r))}" for t,r in ex))

    for h in d["hours"]:
        L.append("\n"+"-"*105)
        L.append(f"SAAT {h['hour']}:00")
        L.append("-"*105)
        L.append(f"İlk3 [0/3,1/3,2/3,3/3] = {h['q1']}")
        L.append(f"İkinci3 [0/3,1/3,2/3,3/3] = {h['q2']}")
        L.append(f"İlk6 [0/6..6/6] = {h['q6']}")
        fams=[]
        for a in CLASSES:
            for b in CLASSES:
                n=h["trans"][a][b]
                if n:fams.append(f"{a}/3→{b}/3:{n}")
        L.append("Aile kontenjanı: "+" | ".join(fams))

        hot=[n for n,s in h["hour_states"].items() if s=="HOT"]
        vhot=[n for n,s in h["hour_states"].items() if s=="VERY_HOT"]
        cold=[n for n,s in h["hour_states"].items() if s=="COLD"]
        L.append("Saat HOT(4–5): "+fmt_nums(hot))
        L.append("Saat VERY_HOT(6+): "+fmt_nums(vhot))
        L.append("Saat COLD(0–1): "+fmt_nums(cold))
        L.append("Sıcağa geçen: "+fmt_nums(h["to_hot"]))
        L.append("Soğuğa geçen: "+fmt_nums(h["to_cold"]))
        L.append("2+ katman yukarı: "+fmt_nums(h["jump_up"]))
        L.append("2+ katman aşağı: "+fmt_nums(h["jump_down"]))

        L.append("Saat TAM frekans | "
                 +" | ".join(f"{k}{'+' if k==8 else ''}={fmt_nums(h['exact'][k])}" for k in (4,5,6,7,8)))
        if h["plus"]:
            L.append("+4/+5/+6/+7/+8 KATMAN KİMLİĞİ:")
            for x in h["plus"]:
                L.append(f"  {x['number']:02d} F={x['freq']} | ilk3={x['first3']}/3 ikinci3={x['second3']}/3 "
                         f"| aile={x['family']} ilk6={x['first6']}/6 | saat={x['hour_state']} "
                         f"| saat-başı-gün={x['start_state']} z={x['start_z']:+.2f} | bant={x['band']}")

        L.append("SON6 SAHNE:")
        for t in LAST6:
            p=h["targets"][t]
            L.append(f"  :{t} | İlk3 gerçek={p['A']} bek={[round(x,2) for x in p['expA']]} patlayan={p['domA']}/3 "
                     f"| İkinci3 gerçek={p['B']} bek={[round(x,2) for x in p['expB']]} patlayan={p['domB']}/3 "
                     f"| 0/6 gerçek={p['F6'][0]} bek={p['expF6'][0]:.2f} | aile={p['domF']}")
        L.append("İlk3 sahne zinciri :32→:57 = "+"→".join(f"{x}/3" for x in h["seqA"]))
        L.append("İkinci3 sahne zinciri :32→:57 = "+"→".join(f"{x}/3" for x in h["seqB"]))

        L.append(f"Ardışık blok | 2'li={h['chaincount'].get('2',0)} 3'lü={h['chaincount'].get('3',0)} 4+={h['chaincount'].get('4+',0)}")
        if h["chaintrans"]:
            L.append("Zincir geçiş TOP10: "+" ; ".join(f"{k} x{v}" for k,v in Counter(h["chaintrans"]).most_common(10)))

    if d["partial"]:
        L.append("\nEKSİK SAATLER:")
        for hh,miss in d["partial"]:L.append(f"{hh}:00 eksik "+",".join(":"+m for m in miss))
    return "\n".join(L)

def make_report(df,rejected,dup,results,agg,A,TA,B,TB,source,digest):
    L=[]
    L.append("HIZLI ON — OYUN KİMLİĞİ / YAŞAM İZİ ANA RAPORU")
    L.append("="*110)
    L.append(f"Kaynak: {source} | SHA={digest}")
    L.append(f"Kapsam: 25.08.2026–29.09.2026 | çekiliş={len(df)} | gün={df.time.dt.date.nunique()} | dup={dup} | parse-red={rejected}")
    L.append("Amaç: KU PON ÜRETMEK DEĞİL; önce oyunun kimliğini tanımak.")
    L.append("Saat sıcaklığı: 0–1 COLD, 2 COOL, 3 NEUTRAL, 4–5 HOT, 6+ VERY_HOT.")
    L.append("Gün sıcaklığı: teorik p=.25 z-skoru. Patlama = gerçek kontenjan - havuz/4 beklentisi en yüksek sınıf.")

    L.append("\n\n[A] İLK6 KONTENJANI SON6 HAKKINDA BİLGİ TAŞIYOR MU?")
    if not agg.empty:
        for t in LAST6:
            L.append(f"\nHEDEF :{t}")
            for src in ("FIRST3","SECOND3","FIRST6"):
                g=agg[(agg.target==t)&(agg.source==src)]
                L.append(f"  {src}")
                for r in g.itertuples(index=False):
                    corr="-" if pd.isna(r.corr) else f"{r.corr:.3f}"
                    L.append(f"    {r.cls} n={r.hours} havuz={r.mean_pool:.2f} bek={r.mean_expected:.2f} "
                             f"gerçek={r.mean_actual:.2f} lift={r.lift:.3f} surge={r.mean_surge:+.3f} "
                             f"surge+%={r.positive_surge_pct:.1f} corr={corr}")
            gf=agg[(agg.target==t)&(agg.source=="FAMILY")].copy()
            if not gf.empty:
                gf["edge"]=(gf.lift-1).abs()
                L.append("  FAMILY en ayrışan 8")
                for r in gf.sort_values(["edge","hours"],ascending=[False,False]).head(8).itertuples(index=False):
                    L.append(f"    {r.cls} n={r.hours} bek={r.mean_expected:.2f} gerçek={r.mean_actual:.2f} lift={r.lift:.3f}")

    L.append("\n\n[B] 7.,8.,9... ÇEKİLİŞ GELDİKÇE SAHNE DEĞİŞİMİ")
    for title,T in [("İLK3 sınıf sahnesi",TA),("İKİNCİ3 sınıf sahnesi",TB)]:
        L.append(f"\n{title}")
        for step,c in T.items():
            total=sum(c.values())
            L.append("  "+step)
            for (a,b),n in c.most_common():
                L.append(f"    {a}/3→{b}/3 = {n}/{total} = %{100*n/total:.1f}")
    L.append("\nEn sık İlk3 tam sahne dizileri:")
    for s,n in Counter(A).most_common(15):L.append("  "+"→".join(f"{x}/3" for x in s)+f" x{n}")
    L.append("En sık İkinci3 tam sahne dizileri:")
    for s,n in Counter(B).most_common(15):L.append("  "+"→".join(f"{x}/3" for x in s)+f" x{n}")

    L.append("\n\n[C] GÜN GÜN / SAAT SAAT DETAY")
    for d in results:L.append(day_report(d))
    return "\n".join(L)

with st.sidebar:
    st.header("Veri")
    uploaded=st.file_uploader("İstersen veri.txt yükle",type=["txt"])
    st.caption("Yükleme yoksa repo kökündeki veri.txt okunur.")
    if st.button("🔄 veri.txt yeniden oku",use_container_width=True):
        st.cache_data.clear();st.session_state.pop("analysis",None);st.rerun()

raw,source=read_source(uploaded)
if raw is None:
    st.error("veri.txt bulunamadı.");st.stop()

digest=hashlib.sha256(raw.encode("utf-8",errors="replace")).hexdigest()
df0,rejected,dup=parse_text(raw,digest)
df=df0[(df0.time>=START)&(df0.time<=END)].copy().reset_index(drop=True)

c1,c2,c3,c4,c5=st.columns(5)
c1.metric("Çekiliş",len(df))
c2.metric("Gün",df.time.dt.date.nunique() if len(df) else 0)
c3.metric("İlk",df.time.min().strftime("%d.%m.%Y") if len(df) else "-")
c4.metric("Son",df.time.max().strftime("%d.%m.%Y") if len(df) else "-")
c5.metric("SHA",digest[:10])

st.info("Bu uygulama kupon üretmez. Önce 1–80 yaşam izini, sıcak/soğuk katmanları, +4..+8 kökenini, "
        "ilk3/ikinci3/ilk6 kontenjanını, son6 sahne değişimini, ritim ve ardışık zincir düzenini ölçer.")

health=df.assign(day=df.time.dt.strftime("%d.%m.%Y")).groupby("day").size().reset_index(name="draws")
health["status"]=np.where(health.draws==217,"TAM","EKSİK/FAZLA")
with st.expander("📦 Veri sağlık kontrolü"):
    st.dataframe(health,use_container_width=True,hide_index=True)
    st.write(f"Mükerrer temizlenen: {dup} • Parse reddi: {rejected}")

if st.button("🚀 GÜN GÜN ANALİZİ BAŞLAT",type="primary",use_container_width=True):
    results=[]
    days=sorted(df.time.dt.strftime("%d.%m.%Y").unique(),key=lambda x:pd.to_datetime(x,dayfirst=True))
    prog=st.progress(0,text="Başlıyor...")
    status=st.empty()
    for i,day_key in enumerate(days,1):
        day=df[df.time.dt.strftime("%d.%m.%Y")==day_key][["draw_id","time","numbers"]]
        serial=[(int(r.draw_id),r.time,tuple(r.numbers)) for r in day.itertuples(index=False)]
        status.write(f"🔬 {day_key} — {len(day)} çekiliş")
        results.append(analyze_day(serial,day_key,digest))
        prog.progress(i/len(days),text=f"{i}/{len(days)} gün tamamlandı")
    q,agg,A,TA,B,TB=aggregate(results)
    report=make_report(df,rejected,dup,results,agg,A,TA,B,TB,source,digest)
    st.session_state["analysis"]=(results,agg,A,TA,B,TB,report)
    status.success("✅ Tüm günler tamamlandı.");prog.empty()

if "analysis" in st.session_state:
    results,agg,A,TA,B,TB,report=st.session_state["analysis"]
    t1,t2,t3,t4=st.tabs(["📅 Günler","🧬 Kontenjan","🔗 Sahne","📄 Tek dosya"])
    with t1:
        rows=[{"Gün":d["date"],"Çekiliş":d["draw_count"],"Tam saat":len(d["hours"]),
               "Eksik saat":len(d["partial"]),"HOT":len(d["daily_hot"]),"WARM":len(d["daily_warm"]),
               "COLD":len(d["daily_cold"]),"VERY_COLD":len(d["daily_vcold"]),"Ritim":len(d["rhythm"])} for d in results]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with t2:
        src=st.selectbox("Katman",["FIRST3","SECOND3","FIRST6","FAMILY"])
        st.dataframe(agg[agg.source==src],use_container_width=True,hide_index=True)
    with t3:
        for title,T in [("İlk3 patlayan sınıf",TA),("İkinci3 patlayan sınıf",TB)]:
            st.subheader(title)
            for step,c in T.items():
                total=sum(c.values())
                st.write(f"**{step}:** "+" • ".join(f"{a}/3→{b}/3 %{100*n/total:.1f}" for (a,b),n in c.most_common(8)))
    with t4:
        st.success("Tek ana TXT hazır.")
        st.download_button("⬇️ TEK ANA ANALİZ DOSYASINI İNDİR",
                           report.encode("utf-8-sig"),
                           "HIZLI_ON_25AGUSTOS_29EYLUL_OYUN_KIMLIGI_TAM_ANALIZ.txt",
                           "text/plain",use_container_width=True)
        with st.expander("Önizleme"):st.text(report[:50000])
