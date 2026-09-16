
import streamlit as st
import pandas as pd
from pathlib import Path
from collections import Counter
from itertools import combinations

st.set_page_config(page_title="Hızlı On Aile Yaşam Motoru V1.3", layout="wide")
st.title("🧬 Hızlı On — Aile & Örüntü Motoru V1.3")
st.caption("Her basışta 1 gün hesaplanır. 14/14'te yeniden hesaplama YOK; kayıtlı günlük sonuçlar tek MASTER'a yalnızca birleştirilir.")

DATA = Path("veri.txt")

@st.cache_data
def load_data():
    rows=[]
    for line in DATA.read_text(encoding="utf-8").splitlines():
        p=line.strip().split(";")
        if len(p)!=3: continue
        nums=tuple(sorted(map(int,p[2].split(","))))
        if len(nums)!=20 or len(set(nums))!=20: continue
        dt=pd.to_datetime(p[1],dayfirst=True)
        rows.append((int(p[0]),dt,nums))
    df=pd.DataFrame(rows,columns=["draw_id","dt","nums"])
    df["day"]=df.dt.dt.strftime("%d.%m.%Y")
    return df

def pc(a,b): return 100*a/b if b else 0.0

def day_analysis(g):
    g=g.sort_values("draw_id").reset_index(drop=True)
    sets=[set(x) for x in g.nums]
    single=Counter(); pair=Counter(); tri=Counter(); quad=Counter()
    ab=Counter(); abase=Counter()
    abc=Counter(); abbase=Counter()
    abcd=Counter(); abcbase=Counter()
    carry=Counter(); same_digit=Counter()
    gaps={1:Counter(),2:Counter(),3:Counter()}
    # yaşam pencereleri: ailelerin aynı gün içindeki görünme indeksleri
    pair_pos={}; tri_pos={}; quad_pos={}
    for i,s in enumerate(sets):
        so=sorted(s); single.update(so)
        for x in combinations(so,2):
            pair[x]+=1; pair_pos.setdefault(x,[]).append(i)
            if x[0]%10==x[1]%10: same_digit[x]+=1
        for x in combinations(so,3):
            tri[x]+=1; tri_pos.setdefault(x,[]).append(i)
        for x in combinations(so,4):
            quad[x]+=1; quad_pos.setdefault(x,[]).append(i)

    for i in range(len(sets)-1):
        cur,nxt=sets[i],sets[i+1]
        carry[len(cur&nxt)]+=1
        for a in cur:
            abase[a]+=1
            for b in nxt: ab[(a,b)]+=1
        for fam in combinations(sorted(cur),2):
            abbase[fam]+=1
            for c in nxt: abc[(fam,c)]+=1
        for fam in combinations(sorted(cur),3):
            abcbase[fam]+=1
            for d in nxt: abcd[(fam,d)]+=1
    for gap in (1,2,3):
        for i in range(len(sets)-gap):
            for n in sets[i]:
                gaps[gap][(n,n in sets[i+gap])]+=1

    def bursts(posdict, min_hits=3, max_span=12):
        out=[]
        for fam,pos in posdict.items():
            # best number of appearances in any max_span-draw window
            l=0; best=(0,None,None)
            for r in range(len(pos)):
                while pos[r]-pos[l] >= max_span: l+=1
                cnt=r-l+1
                if cnt>best[0]: best=(cnt,pos[l],pos[r])
            if best[0]>=min_hits:
                out.append((best[0],best[2]-best[1]+1,fam,best[1],best[2],len(pos)))
        return sorted(out,key=lambda x:(-x[0],x[1],-x[5],x[2]))

    def ranked(c,base,minsup):
        out=[]
        for (lhs,b),h in c.items():
            d=base[lhs]
            if d>=minsup: out.append((pc(h,d),h,d,lhs,b))
        return sorted(out,reverse=True)

    ar=[]
    for (a,b),h in ab.items():
        d=abase[a]
        if d>=10: ar.append((pc(h,d),h,d,a,b))
    ar.sort(reverse=True)

    return {
      "draws":len(g),"single":single,"pair":pair,"tri":tri,"quad":quad,
      "A_B":ar,"AB_C":ranked(abc,abbase,8),"ABC_D":ranked(abcd,abcbase,5),
      "carry":carry,"same_digit":same_digit,"gaps":gaps,
      "pair_burst":bursts(pair_pos,3,12),
      "tri_burst":bursts(tri_pos,3,12),
      "quad_burst":bursts(quad_pos,3,12)
    }

def render_day(day,r):
    L=[f"===== GUN {day} =====",f"CEKILIS={r['draws']}",""]
    L+=["[1LI TEK SAYI]"]
    for n,v in sorted(r["single"].items(),key=lambda x:(-x[1],x[0])):
        L.append(f"{n}|N={v}|ORAN={pc(v,r['draws']):.2f}%")
    for title,key,limit in [("2LI AILE","pair",100),("3LU AILE","tri",100),("4LU AILE","quad",100)]:
        L+=["",f"[{title} TOP {limit}]"]
        for fam,v in r[key].most_common(limit):
            L.append(f"{'-'.join(map(str,fam))}|N={v}")
    for title,key in [("2LI KISA YASAM/BURST","pair_burst"),("3LU KISA YASAM/BURST","tri_burst"),("4LU KISA YASAM/BURST","quad_burst")]:
        L+=["",f"[{title} | 12 EL ICINDE >=3 BULUSMA]"]
        for cnt,span,fam,b,e,total in r[key][:150]:
            L.append(f"{'-'.join(map(str,fam))}|BURST={cnt}|SPAN={span}|EL={b+1}-{e+1}|GUN_TOPLAM={total}")
    L+=["","[A -> SONRAKI B | DESTEK>=10]"]
    for rate,h,d,a,b in r["A_B"][:200]: L.append(f"{a}->{b}|{h}/{d}|{rate:.2f}%")
    L+=["","[A+B -> SONRAKI C | DESTEK>=8]"]
    for rate,h,d,f,c in r["AB_C"][:200]: L.append(f"{f[0]}+{f[1]}->{c}|{h}/{d}|{rate:.2f}%")
    L+=["","[A+B+C -> SONRAKI D | DESTEK>=5]"]
    for rate,h,d,f,c in r["ABC_D"][:200]: L.append(f"{'+'.join(map(str,f))}->{c}|{h}/{d}|{rate:.2f}%")
    L+=["","[TASIMA]"]
    for k,v in sorted(r["carry"].items()): L.append(f"TASINAN={k}|N={v}")
    L+=["","[1/2/3 EL DONUS]"]
    for gap,c in r["gaps"].items():
        hit=sum(v for (n,ok),v in c.items() if ok); total=sum(c.values())
        L.append(f"GAP={gap}|{hit}/{total}|{pc(hit,total):.2f}%")
    return "\n".join(L)

df=load_data()
days=list(df.day.drop_duplicates())
if "done" not in st.session_state: st.session_state.done=[]
if "texts" not in st.session_state: st.session_state.texts={}

st.metric("İlerleme",f"{len(st.session_state.done)}/{len(days)}")
st.progress(len(st.session_state.done)/len(days))

next_day=next((d for d in days if d not in st.session_state.done),None)

if next_day:
    st.info(f"Sıradaki gün: {next_day}")
    if st.button("🔬 SIRADAKİ GÜNÜ HESAPLA",type="primary",use_container_width=True):
        r=day_analysis(df[df.day==next_day])
        # Sadece metin saklanır: 14/14'te ağır sayaçlar yeniden hesaplanmaz.
        st.session_state.texts[next_day]=render_day(next_day,r)
        st.session_state.done.append(next_day)
        st.rerun()
else:
    master_head=[
      "HIZLI ON 14 GUN AILE YASAM & ORUNTU MASTER V1.3",
      f"CEKILIS={len(df)}|GUN={len(days)}|BAS={df.draw_id.min()}|SON={df.draw_id.max()}",
      "MIMARI=HER_GUN_BIR_KEZ_HESAPLA|14_14_YENIDEN_HESAP_YOK",
      "KISA_YASAM=12_EL_ICINDE_EN_AZ_3_BULUSMA",
      ""
    ]
    # Burada SADECE önceden oluşmuş 14 metni birleştiriyoruz.
    master="\n".join(master_head+[st.session_state.texts[d] for d in days])
    st.success("✅ 14/14 TAMAMLANDI — TEK MASTER HAZIR")
    st.download_button("⬇️ TEK 14 GÜNLÜK MASTER TXT İNDİR",
        master.encode("utf-8"),
        "HIZLI_ON_14_GUN_AILE_YASAM_MASTER_V1_3.txt",
        "text/plain",type="primary",use_container_width=True)
    st.caption(f"Birleştirme yeniden analiz yapmadan tamamlandı • {len(master):,} karakter")

if st.session_state.done:
    st.write("Tamamlanan: "+" • ".join(st.session_state.done))

if st.button("♻️ SIFIRLA"):
    st.session_state.done=[]; st.session_state.texts={}; st.rerun()
