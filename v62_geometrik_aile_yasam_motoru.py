#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V62: geometric FAMILY life, fragmentation, fusion, structural transitions.

The lottery 1..80 board is an IMPOSED eight-row, ten-column visualization.
A maximal FAMILY is a 4-neighbor connected component in one 20-number
draw. Families are disjoint within a draw and partition the 20 cells.
Between truly consecutive 5-minute draws, parent-child "lineage" means
physical cell intersection in the imposed grid, not causal RNG ancestry.

Separate two important identities:
 - SAME LOCATION: exact old and new cell sets equal
 - SAME SHAPE: after translation, mirror, rotation, two components share
   the same canonical shape signature, even when numbers change.

The first six draw shape spectrum forecasts 7..12 motif intensities using
source-target connections chosen solely from DEV days, with HOLDOUT days
not used for selection. The independent 20/80 theoretical expectation is
the baseline, NOT an adversarially cherry-picked source.

Full geometric shape dictionary is V61's twenty free 2-5 polyominoes.
"""
from __future__ import annotations
import argparse,csv,io,json,math,random,statistics,zipfile
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v53_saatlik_degisen_aileler import BLOCKS
from v61_geometrik_dna import shapes as all_shapes,scan as shape_scan,bits as shape_bits,symmetries,clock_pairs

SEED=620167
BOOT=1200
WIDTH,HEIGHT=10,8
N_NULL_DAYS=48
SHAPE_K_MIN=3
REGULARIZER=1.0
SLOPE_CAP=0.4

def norm_row(r,day):
    return {"day":day,"id":int(r["id"]),"pos":int(r["pos"]),
            "time":str(r["time"]),"nums":tuple(map(int,r["nums"]))}

def cells(nums):
    return {(n-1)%10 for n in nums}

def orthogonal(n):
    x=(n-1)%WIDTH;y=(n-1)//WIDTH
    return [1+nx+WIDTH*ny for nx,ny in
            ((x+1,y),(x-1,y),(x,y+1),(x,y-1))
            if 0<=nx<WIDTH and 0<=ny<HEIGHT]

ADJ={n:set(orthogonal(n)) for n in range(1,81)}

def signature(members):
    coord=tuple(((n-1)%WIDTH,(n-1)//WIDTH) for n in members)
    return min(symmetries(coord))

def describe(nums):
    remaining=set(nums);parts=[]
    while remaining:
        seed=min(remaining);remaining.remove(seed)
        group={seed};stack=[seed]
        while stack:
            curr=stack.pop()
            for neighbor in ADJ[curr]&remaining:
                remaining.remove(neighbor);group.add(neighbor);stack.append(neighbor)
        ordered=tuple(sorted(group))
        xs=[(n-1)%WIDTH for n in ordered];ys=[(n-1)//WIDTH for n in ordered]
        parts.append({"nums":frozenset(ordered),"text":"-".join(map(str,ordered)),
          "k":len(ordered),"sig":signature(ordered),
          "top_left":(min(xs),min(ys))})
    return sorted(parts,key=lambda a:(min(a["nums"]),a["k"]))

def transition(prev,next_):
    """A complete flow network between maximal geometric components.

    An overlap edge exists only when a previous drawn NUMERAL is drawn
    again next draw, and belongs to both connected components. Split and
    fusion are independently tagged, never mutually exclusive.
    """
    left=describe(prev["nums"]);right=describe(next_["nums"])
    links=[];from_degree=Counter();into_degree=Counter()
    for i,a in enumerate(left):
        for j,b in enumerate(right):
            shared=a["nums"]&b["nums"]
            if not shared:continue
            from_degree[i]+=1;into_degree[j]+=1
            same_shape=a["sig"]==b["sig"]
            dx=b["top_left"][0]-a["top_left"][0]
            dy=b["top_left"][1]-a["top_left"][1]
            exact=a["nums"]==b["nums"]
            one_change=a["k"]==b["k"] and len(shared)==a["k"]-1
            links.append({"old_idx":i,"new_idx":j,
              "from_component":a["text"],"to_component":b["text"],
              "from_k":a["k"],"to_k":b["k"],
              "retained":len(shared),
              "lost_cells":a["k"]-len(shared),
              "new_cells":b["k"]-len(shared),
              "shared": "-".join(map(str,sorted(shared))),
              "exact":int(exact),"shape_preserved":int(same_shape),
              "one_cell_swap":int(one_change),
              "grow":int(b["k"]>a["k"]),
              "shrink":int(b["k"]<a["k"]),
              "changed_shape":int(not same_shape),
              "dx":dx,"dy":dy,"is_shift":int(same_shape and (dx or dy) and not exact),
              "old_signature":";".join(f"{x},{y}" for x,y in a["sig"]),
              "new_signature":";".join(f"{x},{y}" for x,y in b["sig"])})
    exact_matching=sum(1 for e in links if e["exact"] and e["from_k"]>=2)
    split_sources={i for i,n in from_degree.items() if n>=2}
    fuse_targets={j for j,n in into_degree.items() if n>=2}
    same_size_mut=sum(1 for x in links if x["one_cell_swap"] and x["from_k"]>=2)
    shifted=sum(1 for x in links if x["is_shift"] and x["from_k"]>=2)
    changed=sum(1 for x in links if x["changed_shape"] and x["from_k"]>=2 and x["to_k"]>=2)
    growth=sum(1 for x in links if x["grow"] and x["from_k"]>=2)
    shrinkage=sum(1 for x in links if x["shrink"] and x["to_k"]>=2)
    reappeared=sum(1 for b in right if not any(b["nums"]&a["nums"] for a in left)
                   and any(b["sig"]==a["sig"] for a in left) and b["k"]>=2)
    metrics={
      "old_roots":len(left),"new_roots":len(right),
      "old_multicell_roots":sum(a["k"]>=2 for a in left),
      "new_multicell_roots":sum(b["k"]>=2 for b in right),
      "old_largest":max((a["k"] for a in left),default=0),
      "new_largest":max((b["k"] for b in right),default=0),
      "retained_numbers":len(set(prev["nums"])&set(next_["nums"])),
      "exact_components":exact_matching,
      "shifted_same_shapes":shifted,
      "one_cell_swaps":same_size_mut,
      "shape_changes":changed,
      "growth_links":growth,"shrink_links":shrinkage,
      "split_roots":len(split_sources),
      "fused_roots":len(fuse_targets),
      "birth_without_old_cells":sum(i not in into_degree for i in range(len(right))),
      "death_without_new_cells":sum(i not in from_degree for i in range(len(left))),
      "new_shape_old_signature_without_overlap":reappeared,
      "active_overlap_links":len(links),
      "full_20_numbers_new":20-len(set(prev["nums"])&set(next_["nums"]))}
    detail=[]
    for e in links:
        detail.append({**{k:v for k,v in e.items() if k not in ("old_idx","new_idx")},
          "split_from_root":int(e["old_idx"] in split_sources),
          "joined_in_new_root":int(e["new_idx"] in fuse_targets)})
    return metrics,detail,left,right

METRICS=("exact_components","shifted_same_shapes","one_cell_swaps",
 "shape_changes","growth_links","shrink_links","split_roots",
 "fused_roots","birth_without_old_cells","death_without_new_cells",
 "new_shape_old_signature_without_overlap","retained_numbers")

def fair_rng_control(simulated_days=N_NULL_DAYS):
    rng=random.Random(SEED)
    perday=[]
    for i in range(simulated_days):
        prev={"nums":tuple(sorted(rng.sample(range(1,81),20)))}
        acc=Counter()
        for j in range(215):
            nxt={"nums":tuple(sorted(rng.sample(range(1,81),20)))}
            met,_,_,_=transition(prev,nxt)
            acc.update({k:met[k] for k in METRICS})
            prev=nxt
        perday.append({"run":i,"transitions":215,**{
          k:acc[k]/215 for k in METRICS}})
    return perday

def day_bootstrap(vals,n=BOOT,seed=SEED):
    if not vals:return 0,0
    randomizer=random.Random(seed)
    boot=sorted(sum(randomizer.choice(vals) for _ in vals)/len(vals)
                for _ in range(n))
    return boot[int((n-1)*.025)],boot[int((n-1)*.975)]

def component_null(real_day,sim_days):
    observed=defaultdict(lambda:defaultdict(list))
    for row in real_day:
        for m in METRICS:observed[m][row["day"]].append(row[m])
    nullrows=[]
    for m in METRICS:
        days=[sum(v)/len(v) for v in observed[m].values()]
        simulated=[r[m] for r in sim_days]
        lo,hi=day_bootstrap(days,seed=SEED+len(m))
        slo,shi=day_bootstrap(simulated,seed=SEED+len(m)+100)
        nullrows.append({"metric":m,"real_days":len(days),
          "real_mean":round(statistics.mean(days),6),
          "real_day_boot95_low":round(lo,6),
          "real_day_boot95_high":round(hi,6),
          "fair_sim_days":len(sim_days),
          "fair_rng_mean":round(statistics.mean(simulated),6),
          "fair_day_boot95_low":round(slo,6),
          "fair_day_boot95_high":round(shi,6),
          "observed_minus_fair":round(statistics.mean(days)-statistics.mean(simulated),6),
          "interpretation":"EXPLORATORY_NOT_PREDICTIVE"})
    return nullrows

def motif_hours(full,definitions):
    """Read completed hours in order; target data is not used for inputs."""
    precache={}
    def abundance(row):
        key=row["day"],row["pos"]
        if key not in precache:
            precache[key]=shape_scan(shape_bits(row["nums"]),definitions,False)
        return precache[key]
    rows=[]
    dates=sorted(full)
    border=len(dates)//2
    for di,day in enumerate(dates):
        ordered={r["pos"]:r for r in full[day]}
        for hour in BLOCKS:
            first=[ordered[p] for p in range(hour["start"],hour["start"]+6)]
            last=[ordered[p] for p in range(hour["start"]+6,hour["start"]+12)]
            a=[abundance(row) for row in first]
            # Next targets are evaluated only once inputs are fixed.
            x={s["code"]:sum(v[s["code"]] for v in a)/6 for s in definitions
               if s["k"]>=SHAPE_K_MIN}
            b=[abundance(row) for row in last]
            y={s["code"]:sum(v[s["code"]] for v in b)/6 for s in definitions
               if s["k"]>=SHAPE_K_MIN}
            rows.append({"day":day,"phase":"DEV" if di<border else "HOLDOUT",
                "hour":hour["code"],"first6_draws":first[0]["id"],"first6_end":first[-1]["id"],
                "target7_draw":last[0]["id"],"target12_draw":last[-1]["id"],
                "x":x,"y":y})
    return rows

def fit_transformation(motif_rows,definitions):
    """Select one source shape for each target based ONLY on DEV hours.

    Compare all shape-link hypotheses on HOLDOUT only AFTER coefficients
    and source-target assignments have been chosen. 19 target shapes,
    fixed ridge penalty and bounded slopes, no post-hoc optimization.
    """
    selected=[s for s in definitions if s["k"]>=SHAPE_K_MIN]
    bases={s["code"]:s["fair_per_draw"] for s in selected}
    training=[x for x in motif_rows if x["phase"]=="DEV"]
    hold=[x for x in motif_rows if x["phase"]=="HOLDOUT"]
    links=[]
    for target in sorted(bases):
        output=[r["y"][target]-bases[target] for r in training]
        candidates=[]
        for source in sorted(bases):
            inp=[r["x"][source]-bases[source] for r in training]
            denom=sum(v*v for v in inp)
            numerator=sum(a*b for a,b in zip(inp,output))
            coef=max(-SLOPE_CAP,min(SLOPE_CAP,numerator/
                                    (denom*(1+REGULARIZER)+1.0)))
            # Total development MSE gain, with fixed shrinkage and penalized
            # source candidate selection. This is in-sample selection only.
            gain=sum(o*o-(o-coef*i)**2 for o,i in zip(output,inp))
            candidates.append((gain,source,coef))
        best=max(candidates,key=lambda x:(x[0],x[1]))
        links.append({"source_shape":best[1],"target_shape":target,
          "learned_beta":best[2],"dev_MSE_gain_sum":best[0],
          "dev_hours":len(training)})
    byphase=defaultdict(list);eval_rows=[]
    for phase in ("DEV","HOLDOUT"):
        for r in motif_rows:
            if r["phase"]!=phase:continue
            for link in links:
                target=link["target_shape"];source=link["source_shape"]
                fair=bases[target]
                prediction=fair+link["learned_beta"]*(r["x"][source]-bases[source])
                y=r["y"][target]
                gain=(y-fair)**2-(y-prediction)**2
                eval_rows.append({"day":r["day"],"hour":r["hour"],
                  "phase":phase,"source_shape":source,"target_shape":target,
                  "actual_next6_shape_avg":round(y,7),
                  "fair_expected":round(fair,7),
                  "model_forecast":round(prediction,7),
                  "mse_gain":round(gain,9),
                  "learned_beta":round(link["learned_beta"],7)})
                byphase[phase].append((r["day"],(y-fair)**2,(y-prediction)**2))
    summary=[]
    for phase in ("DEV","HOLDOUT"):
        target=byphase[phase]
        byday=defaultdict(list)
        for day,a,b in target:byday[day].append(a-b)
        gains=[sum(v)/len(v) for v in byday.values()]
        lo,hi=day_bootstrap(gains,seed=SEED+(1 if phase=="HOLDOUT" else 0))
        fair=statistics.mean(x[1] for x in target)
        model=statistics.mean(x[2] for x in target)
        summary.append({"phase":phase,"days":len(gains),"evaluations":len(target),
            "fair_mse":round(fair,8),"model_mse":round(model,8),
            "model_improvement_percent":round(100*(fair-model)/fair,5),
            "day_boot95_mse_gain_low":round(lo,8),
            "day_boot95_mse_gain_high":round(hi,8),
            "conclusion":"NOT_VALIDATED" if phase=="DEV" or lo<=0
                         else "EXPLORATORY_ONLY_NEED_NEW_FORWARD_TEST"})
    return links,eval_rows,summary

def exact_shape_lifecycle(hourrows,defs):
    """For every target motif count, compare the prior six intensity and
    next-six intensity; one-shape-in-first-six follow-up is not a causal chain.
    """
    result=[]
    baseline={s["code"]:s["fair_per_draw"] for s in defs if s["k"]>=3}
    for row in hourrows:
        anomaly=sorted(baseline,key=lambda name:(
                     -(row["x"][name]-baseline[name]),name))
        chosen=anomaly[:2]
        for k,name in enumerate(chosen,1):
            result.append({"day":row["day"],"hour":row["hour"],
             "phase":row["phase"],"rank":k,"shape":name,
             "first6_mean":round(row["x"][name],6),
             "target6_mean":round(row["y"][name],6),
             "expected_fair":round(baseline[name],6),
             "target_minus_fair":round(row["y"][name]-baseline[name],6)})
    return result

def _csv(z,name,rows,fields=None):
    with z.open(name,"w",force_zip64=True) as fd:
        writer=io.TextIOWrapper(fd,encoding="utf-8",newline="")
        cols=list(rows[0]) if rows else list(fields or ())
        wc=csv.DictWriter(writer,fieldnames=cols)
        wc.writeheader()
        if rows:wc.writerows(rows)
        writer.flush();writer.detach()

def pack(data):
    out=io.BytesIO()
    lines=[
     "V62 — GEOMETRIK AILELERIN DOGUM / DONUSUM / PARCALANMA / BIRLESME",
     f"Tam gunler={data['full_days']}; zaman-komsu gercek gecisler={len(data['timeline'])}",
     f"Gercek gecis iliski kenarlari={len(data['edges'])}",
     f"Tanimli k3-5 sekiller=19; saat sayisi={len(data['motifs'])}.",
     "Duzlem: 8x10 sabit 1..80. AILE = yatay/dikey komsu",
     "sayi hucrelerinden olusan MAKSIMAL BAGLANTILI PARCA.",
     "Her 20'li hedef kadro birbirinden ayrik geometrik ailelere bolunur.",
     "Aile soy baglari yalniz art arda cekilislerde ortak sayi hucreleriyle",
     "kurulur. Nedensel aile birlesimi veya fiziki RNG mekanizmasi DEGIL.",
     "Parcalanma: onceki tek parca yeni cekiliste iki+ parcaya temas eder.",
     "Birlesme: yeni tek parca onceki iki+ farkli parcadan hucre alir.",
     "Iki hareket ayni anda olabilir; bagimsiz bayraklar olarak yazilir.",
     "Yeni dogum: onceki cekilisten hic ortak hucre tasimayan aile.",
     "Yok olma: sonraki cekilise hic ortak hucre tasimayan aile.",
     "Yapısal kimlik: ayni hucreler / ayni sekil fakat yeni konum / yeni sekil.",
     "Rastgele 48 tam gun, 20/80 uniform bagimsiz cekilisler uzerinden",
     "gercek bolunme/birlesme olaylarinin hesaplama bazini saglar.",
     "DEV ilk 36 gun, HOLDOUT son 36 gun: 19 k3-5 hedef sekli",
     "icin en iyi kaynak-sekil bağlantısı DEV'de seçilir; sabit katsayi",
     "son 36 gunde bilinen RNG geometrik ortalama MSE'siyle kiyaslanir.",
     "Geometri 8x10 bir GORSEL secimdir, cekilis fiziginin geometrisi degildir.",
     "Cok sayida ozellik bakilinca rastgele olumlu sinyaller beklenebilir.",
     "Eski günlerden secilen kural yeni prospektif gunde kanitlanmis DEGIL.",
     "", "36 GUNLUK TEST:",
    ]
    for r in data["forecast"]:
        lines.append(f"{r['phase']}: fair_MSE={r['fair_mse']} "
          f"V62_MSE={r['model_mse']} fark={r['model_improvement_percent']:+.5f}% "
          f"bootstrap95=[{r['day_boot95_mse_gain_low']:+.8f},"
          f"{r['day_boot95_mse_gain_high']:+.8f}] {r['conclusion']}")
    lines.append("");lines.append("BAGLANTI VE RNG KARŞILASTIRMASI")
    for r in data["null"]:
        lines.append(f"{r['metric']} gercek={r['real_mean']:.5f} "
                     f"RNG={r['fair_rng_mean']:.5f} "
                     f"fark={r['observed_minus_fair']:+.5f}")
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        z.writestr("00_TEK_SAYFA_BULGULAR.txt","\n".join(lines)+"\n")
        for name,records in [
          ("01_HER_CEKILIS_GEOMETRIK_AILE_KIMLIGI.csv",data["components"]),
          ("02_ARDISIK_CEKILIS_PARCA_BIRLESME_METRIK.csv",data["timeline"]),
          ("03_AILE_SOY_AGACI_HANGI_PARCAYA_GECTI.csv",data["edges"]),
          ("04_RNG_GERCEK_KARSILASTIRMA.csv",data["null"]),
          ("05_DEVDE_OGRENILEN_SEKIL_DONUSUM_ESLESIM.csv",data["links"]),
          ("06_36_GUN_KOR_TEST_SONUC.csv",data["forecast"]),
          ("07_19_SEKIL_HER_SAAT_ILK6_HEDEF6.csv",data["motif_flat"]),
          ("08_36_GUN_HEDEF_GECIS_TAHMIN_KAYIT.csv",data["forecast_log"]),
          ("09_EN_GUCLU_ILK6_SEKIL_AILELERI.csv",data["lifecycle"]),
          ("10_BIRLESIM_AYRILMA_GUNLUK_OZET.csv",data["daily"]),
        ]:_csv(z,name,records)
        z.writestr("11_METOD_VE_KOR_TEST.txt",
          "Bütün 1..80 sayilar ayni 8x10 izgara koordinatlarindadir.\n"
          "Bir çekilişte 20 farklı hücrenin yatay/dikey komsuluk agi"
          " çıkarılır; maksimal bağlı bileşenler birbirinden ayrıdır.\n"
          "Arka arkaya gecis sadece gercek saatte 5 dakika sonraki"
          " cekilişle kurulur. 01:02—07:02 gap'i gecilmez.\n"
          "Ayrilma/birlesme ayri olay tanimlari olup şans oyununa"
          " özgü öngörü yöntemi olarak kabul edilemez.\n"
          "k3-5 sekiller kanonik rotasyon/ayna/konum eşdeğerliği ile"
          " 19 serbest polyomino tipinden olusur.\n"
          "Her tipin adil RNG beklenen yoğunlugu pozisyon sayisi çarpı"
          " tam (20)_k/(80)_k seçilme olasiligidir.\n"
          "Geçmiş iki kısma bölünür; gelişme dönemi sonuçlarıyla"
          " seçilen bağlantılar tutulan 36 günde değiştirilmez.\n"
          "Gözlemsel 72 gün incelediğimiz için kesin ileriye dönük"
          " öngörü doğrulanmamıştır.\n")
    return out.getvalue()

def selftest():
    assert ADJ[10]=={9,20}
    assert ADJ[11]=={1,12,21}
    # 4 connected cells split in a new 20 when the middle bridge is removed
    x=describe((1,2,3,4,20,22,31,42,54,65,76,80,17,28,39,50,61,72,83 if False else 73,67))
    assert sum(c["k"] for c in x)==20
    old={"nums":tuple(range(1,21))}
    new={"nums":tuple(range(41,61))}
    m,edges,left,right=transition(old,new)
    assert m["retained_numbers"]==0 and not edges
    rng=random.Random(6220)
    from v45_sinyal_kor_test import SLOTS
    full={}
    for day in ("2026-10-11","2026-10-12"):
        full[day]=[norm_row({"id":60000+i,"pos":i+1,"time":t,
            "nums":sorted(rng.sample(range(1,81),20))},day)
                     for i,t in enumerate(SLOTS)]
    defs=all_shapes()
    rows=motif_hours(full,defs)
    assert len(rows)==2*18
    links,log,summary=fit_transformation(rows,defs)
    assert len(links)==19 and len(summary)==2
    life=exact_shape_lifecycle(rows,defs)
    assert len(life)==2*18*2
    null=fair_rng_control(2)
    assert len(null)==2
    print("PASS V62: 8x10 connected families, split/fusion graph, same-shape"
          " equivalence, 19 frozen DEV source-target shape transitions,"
          " holdout baseline, iid RNG controls")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--data",default="veri.txt")
    a.add_argument("--output",default="v62_output/V62_GEOMETRIK_AILE_YASAM_DONUSUM_TEK_ZIP.zip")
    a.add_argument("--rng-days",type=int,default=N_NULL_DAYS)
    a.add_argument("--selftest",action="store_true")
    opt=a.parse_args()
    if opt.selftest:selftest();return
    if opt.rng_days<5:raise ValueError("At least 5 random control days")
    raw,issues,malformed=parse_txt(Path(opt.data))
    full={day:[norm_row(r,day) for r in rs] for day,rs in raw.items()
          if len(rs)==217 and {r["pos"] for r in rs}==set(range(1,218))}
    if len(full)<2:raise ValueError("Need at least two complete 217-draw days")
    component_rows=[];computed={}
    for day in sorted(full):
        for r in full[day]:
            c=describe(r["nums"])
            computed[(day,r["pos"])]=c
            for k,family in enumerate(c,1):
                component_rows.append({"day":day,"draw_id":r["id"],
                  "slot":r["pos"],"time":r["time"],"component_no":k,
                  "family":family["text"],"size":family["k"],
                  "shape_class":";".join(f"{x},{y}" for x,y in family["sig"]),
                  "top_left_x":family["top_left"][0],
                  "top_left_y":family["top_left"][1]})
    print(f"V62 components extracted: {len(component_rows)}",flush=True)
    trend=[];edges=[];byday=defaultdict(list)
    for i,(left,right) in enumerate(clock_pairs(full),1):
        met,paths,_,_=transition(left,right)
        data={"day":left["day"],"from_draw":left["id"],
              "from_time":left["time"],"to_draw":right["id"],
              "to_time":right["time"],**met}
        trend.append(data);byday[left["day"]].append(data)
        edges.extend({"day":left["day"],"from_draw":left["id"],
              "to_draw":right["id"],**e} for e in paths)
        if i%2000==0:print(f"V62 checked {i} true 5-minute transitions",flush=True)
    print("V62 simulation of independently random days",flush=True)
    fair=fair_rng_control(opt.rng_days)
    null=component_null(trend,fair)
    print("V62 fit geometric class movement only on DEV days",flush=True)
    defs=all_shapes()
    motif=motif_hours(full,defs)
    links,eval_log,summary=fit_transformation(motif,defs)
    lifecycle=exact_shape_lifecycle(motif,defs)
    daily=[]
    for day,transitions in sorted(byday.items()):
        line={"day":day,"transitions":len(transitions)}
        for met in METRICS:
            line[met+"_mean"]=round(statistics.mean(r[met] for r in transitions),6)
        daily.append(line)
    motif_flat=[]
    for rec in motif:
        for name in sorted(rec["x"]):
            motif_flat.append({"day":rec["day"],"phase":rec["phase"],
              "hour":rec["hour"],"shape":name,
              "first6_draw":rec["first6_draws"],
              "next7_draw":rec["target7_draw"],
              "first6_mean":round(rec["x"][name],6),
              "next6_mean":round(rec["y"][name],6)})
    report={"full_days":len(full),"timeline":trend,"edges":edges,
      "components":component_rows,"null":null,"links":links,"forecast":summary,
      "motifs":motif,"motif_flat":motif_flat,"forecast_log":eval_log,
      "lifecycle":lifecycle,"daily":daily}
    out=Path(opt.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(pack(report))
    print(json.dumps({"output":str(out),"full_days":len(full),
      "5min_true_transitions":len(trend),"component_occurrences":len(component_rows),
      "lineage_edges":len(edges),"frozen_shape_links":len(links),
      "holdout":[r for r in summary if r["phase"]=="HOLDOUT"],
      "top_null_differences":sorted(null,
          key=lambda r:-abs(r["observed_minus_fair"]))[:6],
      "data_errors":len(issues)+len(malformed)},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
