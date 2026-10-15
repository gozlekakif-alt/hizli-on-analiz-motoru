#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V61 — Geometry of 20-of-80 patterns on an arbitrary fixed 8x10 board.

A shape is a 2..5-cell connected polyomino, invariant to translation, reflection
and quarter-turn rotation. Count ALL distinct absolute board placements of each
shape in a draw; multi-shape overlaps are allowed but each exact placement is
counted only once. Distinct free-polyomino counts: 1,2,5,12 by k=2,3,4,5.

Before six target draws occur, the first six of each block identify the two
most unusually frequent 3..5-cell shapes. Measure: a) the same shape at an
entirely new placement, b) the exact same placement, c) change in total motif
intensity. Conditional fair RNG expected new-position count =
6*(all_valid_placements - previously_seen_positions)*P(k cells all selected).
This exact expectation corrects for unequal shape sizes and scan exposure.

DEV=first half full days, HOLDOUT=second half. A capped/shrunk, fitted
persistence slope uses only DEV to predict HOLDOUT motif abundance, compared to
the exact fair baseline; bootstrap by DAY. Retrospective, not real forward test.
No betting recommendations; board geometry is imposed, not RNG mechanism.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,random,statistics,zipfile
from collections import defaultdict,Counter
from datetime import datetime,timedelta
from itertools import combinations
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v53_saatlik_degisen_aileler import BLOCKS
SEED=611297
GRID_H,GRID_W=8,10
N_BOOT=1500
SHAPE_SIZE_RANGE=(2,3,4,5)
ROTATIONS=(0,1,2,3)
EXPECTED_POLYOMINO_COUNTS={2:1,3:2,4:5,5:12}
MAX_ARTIFACT_DRAW_ROWS=9000

def norm(points):
    minx=min(x for x,y in points);miny=min(y for x,y in points)
    return tuple(sorted((x-minx,y-miny) for x,y in points))

def symmetries(points):
    choices=set()
    for mirrored in (False,True):
        for rot in ROTATIONS:
            out=[]
            for x,y in points:
                if mirrored:x=-x
                for _ in range(rot):x,y=-y,x
                out.append((x,y))
            choices.add(norm(out))
    return sorted(choices)

def polyominoes():
    family={norm(((0,0),))}
    output={}
    for k in range(2,6):
        expanded=set()
        for src in family:
            ss=set(src)
            for x,y in src:
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    z=(x+dx,y+dy)
                    if z not in ss:
                        trial=ss|{z}
                        expanded.add(min(symmetries(trial)))
        family=expanded
        output[k]=sorted(family)
        assert len(family)==EXPECTED_POLYOMINO_COUNTS[k],(k,len(family))
    return output

def bits(nums):
    m=0
    for n in nums:m|=1<<(n-1)
    return m

def k_probability(k):
    return math.prod((20-j)/(80-j) for j in range(k))

def shapes():
    out=[]
    for k,canonical_shapes in polyominoes().items():
        for index,base in enumerate(canonical_shapes,1):
            masks=set()
            for orientation in symmetries(base):
                width=max(x for x,y in orientation)+1
                height=max(y for x,y in orientation)+1
                for ox in range(GRID_W-width+1):
                    for oy in range(GRID_H-height+1):
                        m=0
                        for x,y in orientation:
                            m|=1<<((oy+y)*GRID_W+(ox+x))
                        masks.add(m)
            mask_tuple=tuple(sorted(masks))
            short=f"K{k}_{index:02d}"
            ascii_map=[]
            w=max(x for x,y in base)+1;h=max(y for x,y in base)+1
            for y in range(h):
                ascii_map.append("".join("#" if (x,y) in base else "."
                                         for x in range(w)))
            out.append({"code":short,"k":k,"canonical":base,
                        "footprint":"/".join(ascii_map),
                        "positions":mask_tuple,
                        "position_count":len(mask_tuple),
                        "fair_per_draw":len(mask_tuple)*k_probability(k)})
    assert len(out)==20
    return out

def scan(mask,definitions,positions=False):
    results={}
    for shape in definitions:
        appearing=tuple(p for p in shape["positions"] if mask&p==p)
        results[shape["code"]]=appearing if positions else len(appearing)
    return results

def valid_complete(path):
    days,issues,malformed=parse_txt(Path(path))
    full={d:[dict(day=d,pos=r["pos"],id=r["id"],time=r["time"],
             nums=tuple(r["nums"])) for r in arr]
          for d,arr in days.items() if len(arr)==217 and
          {r["pos"] for r in arr}==set(range(1,218))}
    return full,issues,malformed,{d:len(arr) for d,arr in days.items() if d not in full}

def _draws(full):
    return sorted((r for arr in full.values() for r in arr),
                  key=lambda r:r["day"]+"T"+r["time"])

def clock_pairs(full):
    all_rows=_draws(full)
    by_clock={r["day"]+"T"+r["time"]:r for r in all_rows}
    for r in all_rows:
        next_stamp=(datetime.fromisoformat(r["day"]+"T"+r["time"])+
                    timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
        nxt=by_clock.get(next_stamp)
        if nxt is not None:yield r,nxt

def full_transforms():
    transforms={}
    def add(name,fn):
        cells=[]
        for x in range(GRID_W):
            for y in range(GRID_H):
                xx,yy=fn(x,y)
                if 0<=xx<GRID_W and 0<=yy<GRID_H:
                    cells.append((1<<(y*GRID_W+x),1<<(yy*GRID_W+xx)))
        transforms[name]=cells
    for dx,dy in ((1,0),(-1,0),(2,0),(-2,0),
                  (0,1),(0,-1),(0,2),(0,-2),
                  (1,1),(-1,1),(1,-1),(-1,-1)):
        add(f"DX{dx:+d}_DY{dy:+d}",lambda x,y,dx=dx,dy=dy:(x+dx,y+dy))
    add("MIRROR_LEFT_RIGHT",lambda x,y:(9-x,y))
    add("MIRROR_UP_DOWN",lambda x,y:(x,7-y))
    add("ROTATE_180",lambda x,y:(9-x,7-y))
    return transforms

def shifts(full):
    # Only true 5-minute consecutive pairs. No retroactively choosing best
    # displacement: report each pre-registered transform individually.
    instructions=full_transforms()
    roll=defaultdict(lambda:[0,0,0])
    perday=defaultdict(lambda:defaultdict(lambda:[0.0,0]))
    ex=[]
    for a,b in clock_pairs(full):
        am=binary(a["nums"]);bm=binary(b["nums"])
        for name,transform in instructions.items():
            transformed=0
            for before,after in transform:
                if am&before:transformed|=after
            pool=transformed.bit_count()
            hit=(transformed&bm).bit_count()
            cell=roll[name];cell[0]+=1;cell[1]+=pool;cell[2]+=hit
            dev=hit-pool/4
            daycell=perday[name][a["day"]];daycell[0]+=dev;daycell[1]+=1
    for name in sorted(roll):
        n,pool,hits=roll[name]
        vals=[v[0]/v[1] for _,v in sorted(perday[name].items())]
        lo,hi=day_bootstrap(vals,seed=SEED+len(name),nboot=900)
        ex.append({"transform":name,"transitions":n,
           "source_placement_size_avg":round(pool/n,6),
           "next_overlap_avg":round(hits/n,6),
           "fair_expected_avg":round(pool/n/4,6),
           "difference":round((hits-pool/4)/n,6),
           "day_boot95_lo":round(lo,6),"day_boot95_hi":round(hi,6)})
    return ex

def binary(ns):return bits(ns)

def day_bootstrap(day_values,seed,nboot=N_BOOT):
    if not day_values:return (0.0,0.0)
    rng=random.Random(seed)
    n=len(day_values)
    samples=[]
    for _ in range(nboot):
        samples.append(sum(rng.choice(day_values) for _ in range(n))/n)
    samples.sort()
    return samples[int(.025*(len(samples)-1))],samples[int(.975*(len(samples)-1))]

def _highest_two(first_results,definitions):
    ranked=[]
    for sh in definitions:
        if sh["k"]==2:continue
        code=sh["code"]
        count=sum(len(item[code]) for item in first_results)
        fair=6*sh["fair_per_draw"]
        anomaly=(count-fair)/math.sqrt(1+fair)
        ranked.append((anomaly,code,count))
    ranked.sort(key=lambda x:(-x[0],x[1]))
    return ranked[:2]

def experiments(full,definitions,include_details=True):
    dates=sorted(full)
    split=len(dates)//2
    phases={d:"DEV" if i<split else "HOLDOUT" for i,d in enumerate(dates)}
    visual={}; rows=[]; selected=[]; selected_draws=[]
    for date in dates:
        indexed={r["pos"]:r for r in full[date]}
        for block in BLOCKS:
            six_first=[indexed[x] for x in range(block["start"],block["start"]+6)]
            six_targets=[indexed[x] for x in range(block["start"]+6,block["start"]+12)]
            before=[]
            for r in six_first:
                key=(date,r["pos"])
                if key not in visual:
                    visual[key]=scan(binary(r["nums"]),definitions,True)
                before.append(visual[key])
            # predictions freeze before looking at ANY target draw.
            chosen=_highest_two(before,definitions)
            for sh in definitions:
                code=sh["code"]
                x=sum(len(p[code]) for p in before)/6
                # Parse six later draws only after candidate selection frozen.
                target=[]
                for r in six_targets:
                    key=(date,r["pos"])
                    if key not in visual:
                        visual[key]=scan(binary(r["nums"]),definitions,True)
                    target.append(visual[key])
                y=sum(len(p[code]) for p in target)/6
                rows.append({"day":date,"phase":phases[date],"hour":block["code"],
                    "shape":code,"shape_k":sh["k"],
                    "first6_mean":x,"next6_mean":y,
                    "fair_per_draw":sh["fair_per_draw"],
                    "resid_first6":x-sh["fair_per_draw"],
                    "resid_next6":y-sh["fair_per_draw"]})
            if include_details:
                for rank,(_,code,source_count) in enumerate(chosen,1):
                    shape=next(t for t in definitions if t["code"]==code)
                    seen=set(q for p in before for q in p[code])
                    first_pos=len(seen)
                    old=0;new=0
                    for r in six_targets:
                        positions=visual[(date,r["pos"])][code]
                        new_found=[p for p in positions if p not in seen]
                        prev_found=[p for p in positions if p in seen]
                        new+=len(new_found);old+=len(prev_found)
                        if include_details:
                            selected_draws.append({
                              "day":date,"phase":phases[date],"hour":block["code"],
                              "rank":rank,"shape":code,"shape_k":shape["k"],
                              "draw_id":r["id"],"clock":r["time"],
                              "new_positions":len(new_found),
                              "old_positions":len(prev_found),
                              "new_example_numbers":"-".join(str(i+1)
                               for i in range(80) if new_found and new_found[0]&(1<<i)),
                              "old_example_numbers":"-".join(str(i+1)
                               for i in range(80) if prev_found and prev_found[0]&(1<<i))})
                    new_expected=6*(shape["position_count"]-first_pos)*k_probability(shape["k"])
                    old_expected=6*first_pos*k_probability(shape["k"])
                    selected.append({
                     "day":date,"phase":phases[date],"hour":block["code"],
                     "rank":rank,"shape":code,"shape_k":shape["k"],
                     "first6_start_id":six_first[0]["id"],
                     "first6_last_id":six_first[-1]["id"],
                     "next6_start_id":six_targets[0]["id"],
                     "next6_last_id":six_targets[-1]["id"],
                     "first6_total_appearances":source_count,
                     "first6_distinct_positions":first_pos,
                     "all_possible_positions":shape["position_count"],
                     "new_location_real":new,
                     "new_location_rng_expected":round(new_expected,7),
                     "new_location_residual":new-new_expected,
                     "exact_same_location_real":old,
                     "exact_same_location_rng_expected":round(old_expected,7),
                     "exact_same_location_residual":old-old_expected,
                     "first6_frozen":1})
    return rows,selected,selected_draws,phases

def fit_slopes(hourrows,definitions):
    train=defaultdict(list)
    for row in hourrows:
        if row["phase"]=="DEV":
            train[row["shape"]].append(row)
    params={}
    for shape in definitions:
        source=train[shape["code"]]
        p=shape["fair_per_draw"]
        xx=[r["first6_mean"]-p for r in source]
        yy=[r["next6_mean"]-p for r in source]
        cov=sum(x*y for x,y in zip(xx,yy))
        var=sum(x*x for x in xx)
        # Predeclared ridge prior = 50% empirical signal shrink; hard cap
        # ensures one unusually large sparse shape cannot overfit.
        coefficient=max(-0.5,min(0.5,cov/(var+max(1.0,0.5*var))))
        params[shape["code"]]={"beta":coefficient,
            "dev_hours":len(source),"shape_k":shape["k"],
            "fair_mean":p}
    return params

def evaluate(rows,parameters):
    byphase=defaultdict(list)
    byday=defaultdict(lambda:[0.0,0.0,0])
    byshape=defaultdict(lambda:[0,0.0,0.0])
    for row in rows:
        p=row["fair_per_draw"]
        x=row["first6_mean"]-p
        y=row["next6_mean"]
        forecast=p+parameters[row["shape"]]["beta"]*x
        sq_n=(y-p)**2
        sq_f=(y-forecast)**2
        diff=sq_n-sq_f
        key=(row["phase"],row["day"])
        entry=byday[key];entry[0]+=sq_n;entry[1]+=sq_f;entry[2]+=1
        s=byshape[(row["phase"],row["shape"])]
        s[0]+=1;s[1]+=sq_n;s[2]+=sq_f
    summary=[]
    for phase in ("DEV","HOLDOUT"):
        days=sorted(d for (p,d) in byday if p==phase)
        n=sum(byday[(phase,d)][2] for d in days)
        fair=sum(byday[(phase,d)][0] for d in days)/n
        fit=sum(byday[(phase,d)][1] for d in days)/n
        d_gain=[(byday[(phase,d)][0]-byday[(phase,d)][1])/
                byday[(phase,d)][2] for d in days]
        ci=day_bootstrap(d_gain,SEED+3 if phase=="HOLDOUT" else SEED+2)
        summary.append({"phase":phase,"days":len(days),"shape_hour_evaluations":n,
            "fair_baseline_MSE":round(fair,7),
            "trained_model_MSE":round(fit,7),
            "improvement_pct":round(100*(fair-fit)/fair,4),
            "day_mean_MSE_gain":round(sum(d_gain)/len(d_gain),7),
            "day_boot95_gain_low":round(ci[0],7),
            "day_boot95_gain_high":round(ci[1],7),
            "decision":"SUPERIORITY_NOT_PROVEN" if ci[0]<=0
                       else "EXPLORATORY_POSITIVE_REQUIRE_NEW_FORWARD_TEST"})
    byshape_rows=[]
    for (phase,code),entry in sorted(byshape.items()):
        n,a,b=entry
        byshape_rows.append({"phase":phase,"shape":code,
            "hour_count":n,"fair_MSE":round(a/n,8),
            "trained_MSE":round(b/n,8),
            "gain_MSE":round((a-b)/n,8),
            "beta_dev_fitted":round(parameters[code]["beta"],6)})
    return summary,byshape_rows

def selected_summary(selected):
    output=[]
    bykey=defaultdict(list)
    for row in selected:bykey[(row["phase"],row["rank"])].append(row)
    for (phase,rank),vals in sorted(bykey.items()):
        day_data=defaultdict(list)
        for r in vals:day_data[r["day"]].append(r["new_location_residual"])
        error=[sum(x)/len(x) for x in day_data.values()]
        ci=day_bootstrap(error,SEED+5+rank+(phase=="HOLDOUT")*10)
        output.append({"phase":phase,"rank":rank,"hours":len(vals),
            "real_new_positions":sum(x["new_location_real"] for x in vals),
            "fair_new_positions":round(sum(x["new_location_rng_expected"] for x in vals),5),
            "new_positions_minus_fair":round(sum(x["new_location_residual"] for x in vals),5),
            "new_position_resid_mean":round(sum(x["new_location_residual"] for x in vals)/len(vals),6),
            "day_boot95_lo":round(ci[0],6),"day_boot95_hi":round(ci[1],6),
            "real_exact_old_positions":sum(x["exact_same_location_real"] for x in vals),
            "fair_old_positions":round(sum(x["exact_same_location_rng_expected"] for x in vals),5)})
    return output

def _csv(z,name,rows,columns=()):
    with z.open(name,"w",force_zip64=True) as fd:
        wrapper=io.TextIOWrapper(fd,encoding="utf-8",newline="")
        writer=csv.DictWriter(wrapper,fieldnames=list(rows[0]) if rows else list(columns))
        writer.writeheader()
        if rows:writer.writerows(rows)
        wrapper.flush();wrapper.detach()

def report(full,defs,rows,selected,drawrows,summary,shapes_summary,
           selected_stats,transforms,issues,malformed,partial):
    bio=io.BytesIO()
    hold=[x for x in summary if x["phase"]=="HOLDOUT"][0]
    statements=[
      "V61 — 8x10 GEOMETRIK DNA | AYNI SEKIL FARKLI SAYILAR",
      f"Tam gun={len(full)}, 217 cekilis/gun, saat={len(rows)//len(defs)}",
      f"20 farkli SERBEST polyomino sekli: k2=1 k3=2 k4=5 k5=12.",
      "Bu sekiller transpozisyon (konum degisimi), 90 derece donus",
      "ve ayna yansimasi altinda ayni sinif sayilir.",
      "Bir sekil olusturan sayilar farkli yerde gorunse bile ayni",
      "SEKIL; sabit konumda ortaya cikarsa ayni YER'deki tekrardir.",
      "Kare, L, yatay/dikey cizgi, merdiven vb. 20 sinif birebir kontrol.",
      "Once ilk 6 cekilis: her saat 3-5 sayilik sekiller arasindan",
      "adil beklentiden en fazla sapan iki sekil ONCEDEN SECILIR.",
      "Hedef 7-12 cekilis: secilen sekillerin yeni veya ayni yerde",
      "kac kez gerceklestigi ayrica sayilir.",
      "Adil RNG kosullu beklentisi: ilk6'da gorulmemis her konum",
      "icin sonraki her cekiliste k-hucre olasiligi (20)_k/(80)_k.",
      "Ilk 36 gun sadece hareketin dev-katsayisini ogretir.",
      "Son 36 gun katsayi dondurulmus haliyle test edilir;",
      "model vs adil RNG sabit sekil ortalamasi MSE kiyaslanir.",
      "Bütün k=2..5 şekillerin hataları esit agırlıklı ortalanır.",
      "Gün kümelemeli bootstrap %95 fark belirsizliği hesaplanır.",
      "Global buyuk resim kaymalari solda/sagda/yukarida/asagida",
      "±1,±2, çapraz, ayna ve 180 derece donus; konum disina",
      "tasan hucreler havuzdan silinir, beklenen havuz/4.",
      "8x10 yerlestirme kullanicinin TANIMLADIGI duzlemdir.",
      "Bu durum RNG'nin fiziksel geometri kullandigini GOSTERMEZ.",
      "Cok sayida sekil tarandigi icin tek bir pozitifi ayri",
      "secip isabet motoru yapmak istatistiksel olarak yanilticidir.",
      "Bu tarihsel holdout, gelecekte tamamlanacak gunlerdeki",
      "gercek onceden sabit testin alternatifi DEĞİLDİR.",
      f"Kusurlu veri={len(issues)}; ayrıştırılamayan satir={len(malformed)};",
      f"tamamlanmamis gun={len(partial)}.",
      "",
      "SON 36 GUN DEV-KATSAYISI HOLDOUT SONUC:",
      f"Adil MSE={hold['fair_baseline_MSE']}, model MSE={hold['trained_model_MSE']}; "
      f"iyilesme={hold['improvement_pct']:+.4f}%",
      f"Gun-bootstrap kazanc CI [{hold['day_boot95_gain_low']:+.7f},"
      f"{hold['day_boot95_gain_high']:+.7f}]",
      f"Yorum={hold['decision']}", "", "FROZEN ILK6 SEKILLERIN YENI KONUM SONUCLARI:"
    ]
    for x in selected_stats:
        if x["phase"]=="HOLDOUT":
            statements.append(f"rank{x['rank']}: gerçek={x['real_new_positions']} "
              f"adil={x['fair_new_positions']} "
              f"fark={x['new_position_resid_mean']:+.5f} per hour; "
              f"95% CI=[{x['day_boot95_lo']:+.5f},{x['day_boot95_hi']:+.5f}]")
    with zipfile.ZipFile(bio,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_OZET_GUVENILIRLIK.txt","\n".join(statements)+"\n")
        _csv(z,"01_20_GEOMETRIK_SEKIL_DNA_SOZLUGU.csv",[
          {"shape":s["code"],"k":s["k"],"footprint":s["footprint"],
           "valid_positions":s["position_count"],
           "fair_per_draw":round(s["fair_per_draw"],8)} for s in defs])
        _csv(z,"02_DEV_HOLDOUT_MSE_SONUC.csv",summary)
        _csv(z,"03_SEKIL_BASINA_MSE_VE_OGRENILEN_KATSAYI.csv",shapes_summary)
        _csv(z,"04_SAATLIK_SEKIL_KARAKTERI_ILK6_SON6.csv",rows)
        _csv(z,"05_ONCEDEN_SECILEN_SEKILLER_YENI_YERDE.csv",selected)
        _csv(z,"06_SECILEN_SEKIL_HER_HEDEF_CEKILIS_DETAY.csv",drawrows)
        _csv(z,"07_SECILEN_SEKILLER_RNG_KOSULLU_TEST.csv",selected_stats)
        _csv(z,"08_BUYUK_20LI_GEOMETRI_KAYMA_YANSIMA.csv",transforms)
        z.writestr("09_METOD_VE_KOR_TEST_SINIRLARI.txt",
          "V61: 20/80, 8×10 sabit grid, tum yasal hucreler.\n"
          "Bir k-hucre motifunun olasiligi tam (20)_k/(80)_k;\n"
          "bu olasilik ne sekle ne hucre konumuna baglidir.\n"
          "Ilk6 motifi hedef 7-12 gorulmeden secilir, böylece tahmin",
          " etiketine gelecekten veri sizmaz.\n"
          "Bir onceki hedefte gorulmemis konumlar ile TAM AYNI",
          " konumlar AYRI tespit edilir. Bunlarin beklenen tekrar",
          " sayilari bilinmesi gereken konum havuzuna gore verilir.\n"
          "RNG gerceginin geometrik düzenlilik göstermesi normaldir;",
          " denk gelen duzenlilik bir sonraki cekilis tahminini saglamaz.\n"
          "DEV sonrasi ek model aramak secici yanlilik yaratir;",
          " ilerleme icin dondurulmus V61 algoritmasiyla canli on test lazim.\n")
    return bio.getvalue()

def selftest():
    defs=shapes()
    assert [sum(s["k"]==k for s in defs) for k in range(2,6)]==[1,2,5,12]
    assert all(len(set(s["positions"]))==s["position_count"] for s in defs)
    # Each translated/rotated footprint must map to exactly same shape.
    two=next(s for s in defs if s["k"]==2)
    m=bits((1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20))
    q=scan(m,defs,True)
    assert len(q[two["code"]])>=1
    assert all(x in two["positions"] for x in q[two["code"]])
    assert math.isclose(k_probability(2),20*19/(80*79))
    rng=random.Random(9161)
    from v45_sinyal_kor_test import SLOTS
    def mk(day):
        return [{"day":day,"pos":i+1,"id":53000+i,"time":t,
                 "nums":tuple(sorted(rng.sample(range(1,81),20)))}
                for i,t in enumerate(SLOTS)]
    full={"2026-10-11":mk("2026-10-11"),"2026-10-12":mk("2026-10-12")}
    inputs,pred,details,phases=experiments(full,defs)
    assert len(inputs)==2*18*20
    assert len(pred)==2*18*2
    assert len(details)==2*18*2*6
    pars=fit_slopes(inputs,defs)
    summary,sm=evaluate(inputs,pars)
    selected_stats=selected_summary(pred)
    tf=shifts(full)
    assert len(tf)==15
    assert all(v["transitions"]==2*215+1 for v in tf)
    out=report(full,defs,inputs,pred,details,summary,sm,selected_stats,tf,[],[],{})
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        assert len(z.namelist())==10
        assert z.read("05_ONCEDEN_SECILEN_SEKILLER_YENI_YERDE.csv")
    print("PASS V61: 20 free polyomino shapes, full 8x10 placements, "
          "frozen first6 shape selection, exact conditional RNG new-location "
          "expectation, 36/36 chronological holdout, day-cluster CI, one ZIP")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v61_output/V61_GEOMETRIK_DNA_SEKIL_DONUSUM_TEK_ZIP.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest();return
    full,issues,malformed,partial=valid_complete(args.source)
    if len(full)<2:raise ValueError("At least 2 complete 217-draw days required.")
    defs=shapes()
    r,selected,details,phase=experiments(full,defs)
    learned=fit_slopes(r,defs)
    summary,byshape=evaluate(r,learned)
    selected_stats=selected_summary(selected)
    movements=shifts(full)
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(report(full,defs,r,selected,details,summary,byshape,
                          selected_stats,movements,issues,malformed,partial))
    print(json.dumps({"output":str(dest),"complete_days":len(full),
      "hours":len(r)//len(defs),"shapes":len(defs),
      "source_20_draws":sum(map(len,full.values())),
      "measured_hour_shapes":len(r),
      "frozen_top2_hour_predictions":len(selected),
      "shift_transforms":len(movements),
      "holdout_MSE":[x for x in summary if x["phase"]=="HOLDOUT"],
      "holdout_new_position":[x for x in selected_stats if x["phase"]=="HOLDOUT"],
      "best_shift_differences":sorted(movements,key=lambda x:-abs(x["difference"]))[:5]},
      ensure_ascii=False))
if __name__=="__main__":main()
