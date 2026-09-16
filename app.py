
import streamlit as st
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import pandas as pd
import io, zipfile

st.set_page_config(page_title="Hızlı On — Aile & Örüntü Kadavrası", layout="wide")
st.title("🧬 Hızlı On — 2'li / 3'lü / 4'lü Aile & Sonraki-El Örüntü Motoru")
st.caption("Her basışta yalnız 1 günü işler. 14/14 tamamlanınca tek MASTER TXT üretir.")

DATA_FILE = Path("veri.txt")

@st.cache_data
def load_data():
    rows=[]
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            p=line.strip().split(";")
            if len(p)!=3: continue
            draw_id=int(p[0]); dt=pd.to_datetime(p[1], dayfirst=True)
            nums=tuple(sorted(map(int,p[2].split(","))))
            if len(nums)==20 and len(set(nums))==20:
                rows.append((draw_id,dt,nums))
    df=pd.DataFrame(rows, columns=["draw_id","dt","nums"])
    df["day"]=df["dt"].dt.strftime("%d.%m.%Y")
    return df

def pct(a,b):
    return 100*a/b if b else 0.0

def top_lines(counter, n=50):
    return counter.most_common(n)

def analyze_day(daydf):
    daydf=daydf.sort_values("draw_id").reset_index(drop=True)
    pair=Counter(); tri=Counter(); quad=Counter()
    trans=Counter(); trans_base=Counter()
    pair_to=Counter(); pair_to_base=Counter()
    tri_to=Counter(); tri_to_base=Counter()
    neigh=Counter()
    return_gap={1:Counter(),2:Counter(),3:Counter()}
    last_digit=Counter()
    carry=Counter()

    sets=[set(x) for x in daydf.nums]
    for s in sets:
        pair.update(combinations(sorted(s),2))
        tri.update(combinations(sorted(s),3))
        quad.update(combinations(sorted(s),4))
        for a,b in combinations(sorted(s),2):
            if a%10==b%10: last_digit[(a,b)] += 1

    for i in range(len(sets)-1):
        cur,nxt=sets[i],sets[i+1]
        carry[len(cur & nxt)] += 1
        for a in cur:
            trans_base[a]+=1
            for b in nxt:
                trans[(a,b)]+=1
            for d in (-2,-1,0,1,2):
                b=a+d
                if 1<=b<=80:
                    neigh[(d, b in nxt)] += 1
        cur_pairs=list(combinations(sorted(cur),2))
        for ab in cur_pairs:
            pair_to_base[ab]+=1
            for c in nxt: pair_to[(ab,c)]+=1
        cur_tris=list(combinations(sorted(cur),3))
        for abc in cur_tris:
            tri_to_base[abc]+=1
            for c in nxt: tri_to[(abc,c)]+=1

    for gap in (1,2,3):
        for i in range(len(sets)-gap):
            a=sets[i]; b=sets[i+gap]
            for n in a:
                return_gap[gap][(n, n in b)] += 1

    # Ranked conditional transitions with support
    trans_rank=[]
    for (a,b),hits in trans.items():
        den=trans_base[a]
        if den>=10:
            trans_rank.append((pct(hits,den),hits,den,a,b))
    trans_rank.sort(reverse=True)

    pair_to_rank=[]
    for (ab,c),hits in pair_to.items():
        den=pair_to_base[ab]
        if den>=8:
            pair_to_rank.append((pct(hits,den),hits,den,ab,c))
    pair_to_rank.sort(reverse=True)

    tri_to_rank=[]
    for (abc,c),hits in tri_to.items():
        den=tri_to_base[abc]
        if den>=5:
            tri_to_rank.append((pct(hits,den),hits,den,abc,c))
    tri_to_rank.sort(reverse=True)

    return {
        "draws":len(daydf), "pair":pair, "tri":tri, "quad":quad,
        "trans_rank":trans_rank, "pair_to_rank":pair_to_rank, "tri_to_rank":tri_to_rank,
        "carry":carry, "last_digit":last_digit, "return_gap":return_gap
    }

def result_to_text(day, r):
    L=[]
    L += [f"===== GUN {day} =====", f"CEKILIS={r['draws']}"]
    L += ["", "[AYNI CEKILIS - TOP 100 IKILI]"]
    for k,v in top_lines(r["pair"],100): L.append(f"{k[0]}-{k[1]}|N={v}")
    L += ["", "[AYNI CEKILIS - TOP 100 UCLU]"]
    for k,v in top_lines(r["tri"],100): L.append(f"{'-'.join(map(str,k))}|N={v}")
    L += ["", "[AYNI CEKILIS - TOP 100 DORTLU]"]
    for k,v in top_lines(r["quad"],100): L.append(f"{'-'.join(map(str,k))}|N={v}")
    L += ["", "[A -> SONRAKI EL B | DESTEK>=10 | TOP 200]"]
    for rate,h,d,a,b in r["trans_rank"][:200]:
        L.append(f"{a}->{b}|HIT={h}/{d}|ORAN={rate:.2f}%")
    L += ["", "[A+B -> SONRAKI EL C | DESTEK>=8 | TOP 200]"]
    for rate,h,d,ab,c in r["pair_to_rank"][:200]:
        L.append(f"{ab[0]}+{ab[1]}->{c}|HIT={h}/{d}|ORAN={rate:.2f}%")
    L += ["", "[A+B+C -> SONRAKI EL D | DESTEK>=5 | TOP 200]"]
    for rate,h,d,abc,c in r["tri_to_rank"][:200]:
        L.append(f"{'+'.join(map(str,abc))}->{c}|HIT={h}/{d}|ORAN={rate:.2f}%")
    L += ["", "[AYNI SON HANE AILELERI - TOP 100]"]
    for k,v in top_lines(r["last_digit"],100): L.append(f"{k[0]}-{k[1]}|N={v}")
    L += ["", "[ELDEN ELE TASINAN SAYI ADEDI]"]
    for k,v in sorted(r["carry"].items()): L.append(f"TASINAN={k}|N={v}")
    L += ["", "[1/2/3 EL SONRA SAYI DONUSU]"]
    for gap,c in r["return_gap"].items():
        hit=sum(v for (n,ok),v in c.items() if ok)
        total=sum(c.values())
        L.append(f"GAP={gap}|HIT={hit}/{total}|ORAN={pct(hit,total):.2f}%")
    return "\n".join(L)

def aggregate(all_day_results):
    P=Counter(); T=Counter(); Q=Counter(); LD=Counter(); C=Counter()
    # Rebuild aggregate conditional counts directly from raw full data to avoid averaging daily rates.
    df=load_data().sort_values("draw_id").reset_index(drop=True)
    trans=Counter(); tb=Counter(); p2=Counter(); p2b=Counter(); t2=Counter(); t2b=Counter()
    rg={1:Counter(),2:Counter(),3:Counter()}
    for day,g in df.groupby("day", sort=False):
        sets=[set(x) for x in g.nums]
        for s in sets:
            P.update(combinations(sorted(s),2)); T.update(combinations(sorted(s),3)); Q.update(combinations(sorted(s),4))
            for a,b in combinations(sorted(s),2):
                if a%10==b%10: LD[(a,b)]+=1
        for i in range(len(sets)-1):
            cur,nxt=sets[i],sets[i+1]; C[len(cur&nxt)]+=1
            for a in cur:
                tb[a]+=1
                for b in nxt: trans[(a,b)]+=1
            for ab in combinations(sorted(cur),2):
                p2b[ab]+=1
                for c in nxt: p2[(ab,c)]+=1
            for abc in combinations(sorted(cur),3):
                t2b[abc]+=1
                for c in nxt: t2[(abc,c)]+=1
        for gap in (1,2,3):
            for i in range(len(sets)-gap):
                for n in sets[i]: rg[gap][(n,n in sets[i+gap])] += 1

    def ranks(c,base,minsup):
        z=[]
        for (lhs,b),h in c.items():
            d=base[lhs]
            if d>=minsup: z.append((pct(h,d),h,d,lhs,b))
        return sorted(z, reverse=True)

    tr=[]
    for (a,b),h in trans.items():
        d=tb[a]
        if d>=50: tr.append((pct(h,d),h,d,a,b))
    tr.sort(reverse=True)
    return P,T,Q,LD,C,tr,ranks(p2,p2b,30),ranks(t2,t2b,15),rg

df=load_data()
days=list(df["day"].drop_duplicates())
if "done_days" not in st.session_state: st.session_state.done_days=[]
if "day_texts" not in st.session_state: st.session_state.day_texts={}

c1,c2,c3=st.columns(3)
c1.metric("Ham çekiliş", len(df))
c2.metric("Gün", len(days))
c3.metric("İlerleme", f"{len(st.session_state.done_days)}/{len(days)}")
st.progress(len(st.session_state.done_days)/max(1,len(days)))

next_day = next((d for d in days if d not in st.session_state.done_days), None)
if next_day:
    st.info(f"Sıradaki gün: {next_day}")
    if st.button("🔬 SIRADAKİ GÜNÜ KADAVRA YAP", type="primary"):
        r=analyze_day(df[df.day==next_day])
        st.session_state.day_texts[next_day]=result_to_text(next_day,r)
        st.session_state.done_days.append(next_day)
        st.rerun()
else:
    st.success("14/14 tamamlandı. Tek MASTER hazır.")

if st.session_state.done_days:
    st.subheader("Tamamlanan günler")
    st.write(" • ".join(st.session_state.done_days))

if len(st.session_state.done_days)==len(days):
    P,T,Q,LD,C,TR,P2,T2,RG=aggregate(st.session_state.day_texts)
    L=[
        "HIZLI ON 14 GUN AILE & ORUNTU MASTER V1",
        f"CEKILIS={len(df)}|GUN={len(days)}|BAS={df.draw_id.min()}|SON={df.draw_id.max()}",
        "NOT=Gun gecisleri A->B analizine dahil edilmez. Her gun kendi icinde kronolojiktir.",
        "BASELINE_TEK_SAYI=25%",
        "",
        "================ 14 GUN GENEL ================",
        "[TOP 300 IKILI AILE]"
    ]
    for k,v in P.most_common(300): L.append(f"{k[0]}-{k[1]}|N={v}")
    L += ["","[TOP 300 UCLU AILE]"]
    for k,v in T.most_common(300): L.append(f"{'-'.join(map(str,k))}|N={v}")
    L += ["","[TOP 300 DORTLU AILE]"]
    for k,v in Q.most_common(300): L.append(f"{'-'.join(map(str,k))}|N={v}")
    L += ["","[A -> SONRAKI EL B | DESTEK>=50 | TOP 500]"]
    for rate,h,d,a,b in TR[:500]: L.append(f"{a}->{b}|HIT={h}/{d}|ORAN={rate:.3f}%")
    L += ["","[A+B -> SONRAKI EL C | DESTEK>=30 | TOP 500]"]
    for rate,h,d,ab,c in P2[:500]: L.append(f"{ab[0]}+{ab[1]}->{c}|HIT={h}/{d}|ORAN={rate:.3f}%")
    L += ["","[A+B+C -> SONRAKI EL D | DESTEK>=15 | TOP 500]"]
    for rate,h,d,abc,c in T2[:500]: L.append(f"{'+'.join(map(str,abc))}->{c}|HIT={h}/{d}|ORAN={rate:.3f}%")
    L += ["","[AYNI SON HANE AILELERI - TOP 200]"]
    for k,v in LD.most_common(200): L.append(f"{k[0]}-{k[1]}|N={v}")
    L += ["","[TASIMA DAGILIMI]"]
    for k,v in sorted(C.items()): L.append(f"TASINAN={k}|N={v}")
    L += ["","[1/2/3 EL SONRA DONUS]"]
    for gap,c in RG.items():
        hit=sum(v for (n,ok),v in c.items() if ok); total=sum(c.values())
        L.append(f"GAP={gap}|HIT={hit}/{total}|ORAN={pct(hit,total):.3f}%")
    L += ["","================ GUNLUK KADAVRALAR ================"]
    for d in days:
        L += ["", st.session_state.day_texts[d]]
    master="\n".join(L)
    st.download_button("⬇️ 14 GÜN TEK MASTER TXT", master.encode("utf-8"),
                       "HIZLI_ON_14_GUN_AILE_ORUNTU_MASTER_V1.txt","text/plain")

    # Also provide machine-readable compact tables in one ZIP.
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("HIZLI_ON_14_GUN_AILE_ORUNTU_MASTER_V1.txt", master)
    st.download_button("📦 MASTER ZIP", bio.getvalue(), "HIZLI_ON_14_GUN_AILE_ORUNTU_MASTER_V1.zip","application/zip")

if st.button("♻️ İLERLEMEYİ SIFIRLA"):
    st.session_state.done_days=[]
    st.session_state.day_texts={}
    st.rerun()
