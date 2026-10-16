#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V102: 80-ball 56-ring DIRECTION FILM => target-hour H1..H12 appearances.

This is DESCRIPTIVE ONLY. No ticket, model selection, optimization, or
blind-test claims. Reuses precisely the stable 12-draw ring identities and
FIFO 672 observed-draw memory of V100C; no nested V100B windows.

At the beginning of each verified complete 12-draw clock hour, freeze
the prior 672 OBSERVED draws. The global twelve-draw rings keep their
identities across time, with 55/56 completed and up to 2 partial rings.
For completed rings, class each of 80 balls by last72 frequencies at
that ring end into 5 ordered pools (16 members each); separately
record its in-ring frequency and own 12-draw pool ranking.

Make full 80-ball chronological ring temperature path, +/-/= direction
path, turning points, consecutive rise/fall streaks and warm/hold/cool
behavior. THEN attach only the observed target hour 12-draw H1..H12
membership bits and counts to annotate which chains ended in that hour.
All history/trajectory features are source-time BEFORE that target hour.
Direction doesn't imply predictive RNG edge.

CSV outputs include all hours (80 number profiles/hour), per-hour ring
cohort up/down/same and matched target hour balls, last hour detailed
80x56/57 exact ring film, and all drawn numbers of that hour.
"""
from __future__ import annotations
import argparse, collections, csv, io, json, zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import (
    load, temperature, CAPACITY, GROUP, HISTORY_WARMUP)

VERSION="V102.1"
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
CHAR="CSNIH"
STEP_CHAR={-1:"D",0:"=",1:"Y"}
FIRST=CAPACITY+HISTORY_WARMUP
HHMIN=tuple(range(2,60,5))

def expected_hours(rows):
    groups=collections.defaultdict(list)
    for i,r in enumerate(rows):
        day=r["day"]
        hh,mm=map(int,r["time"].split(":"))
        groups[(day,hh)].append((mm,i,r))
    out=[]
    rejected=0
    for (day,hh),chunk in sorted(groups.items()):
        chunk.sort()
        # A target hour has exactly 12 known 5-minute draws.
        if len(chunk)!=12 or tuple(mm for mm,i,r in chunk)!=HHMIN:
            rejected+=1
            continue
        indices=[i for mm,i,r in chunk]
        # Reject incomplete/non-contiguous IDs; no guessed hours.
        if indices != list(range(indices[0],indices[0]+12)):
            rejected+=1
            continue
        ids=[int(r["id"]) for mm,i,r in chunk]
        if ids != list(range(ids[0],ids[0]+12)):
            rejected+=1
            continue
        if indices[0]<FIRST:continue
        out.append((indices[0], day, hh, ids))
    return out,rejected

def pool_cache(prefix):
    """Exactly the V100C last72 pool at every globally completed ring."""
    out={}
    upto=(len(prefix)-1)//GROUP
    for ring_id in range(upto):
        end=(ring_id+1)*GROUP
        if end<72:continue
        out[ring_id]=temperature(prefix[end]-prefix[end-72])
    return out

def history(t,prefix,cache):
    start=t-CAPACITY
    assert start>=HISTORY_WARMUP
    first=start//12
    last=(t-1)//12
    rings=[]
    for r in range(first,last+1):
        a=max(r*12,start)
        b=min((r+1)*12,t)
        length=b-a
        sealed=length==12
        rank72=(cache[r] if sealed else
                temperature(prefix[b]-prefix[b-72]))
        rank12=temperature(prefix[b]-prefix[a])
        ring_count=(prefix[b]-prefix[a]).astype(np.int16)
        rings.append(dict(id=r,begin=a,end=b,size=length,sealed=sealed,
            pool72=rank72,pool12=rank12,count12=ring_count))
    assert sum(x["size"] for x in rings)==672
    assert len(rings) in (56,57)
    full=[r for r in rings if r["sealed"]]
    assert len(full) in (55,56)
    S=np.stack([r["pool72"] for r in full],axis=1).astype(np.int8)
    W=np.stack([r["pool12"] for r in full],axis=1).astype(np.int8)
    D=np.sign(np.diff(S,axis=1)).astype(np.int8)
    assert S.shape[0]==80 and S.shape[1] in (55,56)
    return rings, full, S, W, D

def longest(seq,target):
    best=0;now=0
    for v in seq:
        if v==target:now+=1;best=max(best,now)
        else:now=0
    return best

def trailing(seq,target):
    size=0
    for v in seq[::-1]:
        if v==target:size+=1
        else:break
    return size

def turns(d):
    meaningful=[v for v in d if v!=0]
    return sum(a!=b for a,b in zip(meaningful,meaningful[1:]))

def phase_of_hour(day,days):
    if day>"2026-10-12":return "NEW_DATA"
    i=days.index(day)
    if i<36:return "EARLY36"
    if i<54:return "MIDDLE18"
    return "LAST18"

def csvw(z,path,rows):
    if not rows:return
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
        stream.flush();stream.detach()

def run(src,out):
    days,rows,X,issues,bad=load(src)
    hourset,skip=expected_hours(rows)
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                      np.cumsum(X,axis=0,dtype=np.int32)))
    cache=pool_cache(prefix)
    allprofiles=[]
    everyhour=[]
    hourbyring=[]
    lastfilm=[]
    lasttarget=[]
    total=collections.defaultdict(lambda:collections.Counter())
    final_hour=None
    agg=collections.defaultdict(lambda:[0,0,0,0])
    # agg: [total ball-hours, appeared >=1, total draw occurrences, appeared >=2].
    for hi,(t,day,clock,ids) in enumerate(hourset):
        rings,full,S,W,D=history(t,prefix,cache)
        hourX=X[t:t+12]
        hits=hourX.sum(axis=0).astype(np.int16)
        bits=["".join(str(int(hourX[k,j])) for k in range(12)) for j in range(80)]
        hname=f"{day} {clock:02d}:02-{clock:02d}:57"
        phase=phase_of_hour(day,days)
        assert np.all(hourX.sum(axis=1)==20)
        hour_profile=[]
        sumrows=collections.Counter()
        profiles_for_last=[]
        for j in range(80):
            s=S[j];d=D[j]
            old=s[0];new=s[-1]
            past6=int(s[-1])-int(s[-7])
            past3=int(s[-1])-int(s[-4])
            up=int(np.count_nonzero(d>0))
            down=int(np.count_nonzero(d<0))
            steady=int(np.count_nonzero(d==0))
            last6dir=d[-6:]
            recent_up=int(np.count_nonzero(last6dir>0))
            recent_down=int(np.count_nonzero(last6dir<0))
            # Directional identity: total up/down count and exact chain,
            # plus two separate rising definitions. Avoid ambiguous "hot".
            direction_label=("ISINIYOR" if past6>0 else
                             "SOGUYOR" if past6<0 else "DENGELI")
            row=dict(
                day=day,target_hour=hname,phase=phase,
                hour_first_draw=ids[0],hour_last_draw=ids[-1],
                number=j+1,oldest_record=rows[t-672]["id"],
                latest_known_record=rows[t-1]["id"],
                sealed_rings=len(full),total_physical_rings=len(rings),
                direction_last6=direction_label,
                last3_net_pool_delta=past3,
                last6_net_pool_delta=past6,
                last12_net_pool_delta=int(s[-1])-int(s[-13]),
                oldest_pool72=POOL[int(old)],
                latest_sealed_pool72=POOL[int(new)],
                rising_steps_full=up,falling_steps_full=down,
                steady_steps_full=steady,
                ring_trend_reversals=turns(d),
                longest_consecutive_rise=longest(d,1),
                longest_consecutive_fall=longest(d,-1),
                end_consecutive_rise=trailing(d,1),
                end_consecutive_fall=trailing(d,-1),
                recent6_rising_steps=recent_up,
                recent6_falling_steps=recent_down,
                visited_five_pools=int(set(s)==set(range(5))),
                seen_cold_and_hot=int(0 in s and 4 in s),
                pool72_sequence="".join(CHAR[int(k)] for k in s),
                pool12_sequence="".join(CHAR[int(k)] for k in W[j]),
                direction_chain="".join(STEP_CHAR[int(k)] for k in d),
                target_H1_H12=bits[j],
                target_draw_count=int(hits[j]),
                target_first_hand=(next((k+1 for k,v in enumerate(bits[j]) if v=="1"),0)),
                target_hands="-".join(str(k+1) for k,v in enumerate(bits[j]) if v=="1")
            )
            allprofiles.append(row)
            profiles_for_last.append(row)
            k=(phase,direction_label)
            a=agg[k];a[0]+=1;a[1]+=int(hits[j]>0);a[2]+=int(hits[j]);a[3]+=int(hits[j]>=2)
            sumrows[(direction_label,"total")]+=1
            sumrows[(direction_label,"in_hour")]+=int(hits[j]>0)
            sumrows[(direction_label,"appearances")]+=int(hits[j])
            if hits[j]:
                sumrows[(direction_label,"number_list")]+=1
        everyhour.append(dict(
            day=day,hour=hname,phase=phase,
            H1_draw_id=ids[0],H12_draw_id=ids[-1],
            reference_672_from=rows[t-672]["id"],
            reference_672_to=rows[t-1]["id"],
            n_rings=len(rings),sealed_rings=len(full),
            oldest_partial=(rings[0]["size"] if not rings[0]["sealed"] else 0),
            newest_partial=(rings[-1]["size"] if not rings[-1]["sealed"] else 0),
            warming_count=sumrows[("ISINIYOR","total")],
            warming_target_hour_different_numbers=sumrows[("ISINIYOR","in_hour")],
            warming_target_hour_total_appearances=sumrows[("ISINIYOR","appearances")],
            cooling_count=sumrows[("SOGUYOR","total")],
            cooling_target_hour_different_numbers=sumrows[("SOGUYOR","in_hour")],
            cooling_target_hour_total_appearances=sumrows[("SOGUYOR","appearances")],
            stable_count=sumrows[("DENGELI","total")],
            stable_target_hour_different_numbers=sumrows[("DENGELI","in_hour")],
            stable_target_hour_total_appearances=sumrows[("DENGELI","appearances")],
            distinct_drawn_in_hour=int(np.count_nonzero(hits)),
            total_hits_in_hour=int(hits.sum())))
        # This explicitly answers which numbers were warming IN EACH ring
        # and which of them appeared at least once in the target clock hour.
        for k in range(1,len(full)):
            d0=D[:,k-1]
            # Two consecutive steps have same direction for same ball?
            prior=D[:,k-2] if k>=2 else None
            rise=np.flatnonzero(d0==1);fall=np.flatnonzero(d0==-1)
            stable=np.flatnonzero(d0==0)
            warming_hit=[int(j+1) for j in rise if hits[j]>0]
            cooling_hit=[int(j+1) for j in fall if hits[j]>0]
            unchanged_hit=[int(j+1) for j in stable if hits[j]>0]
            # matched adjacent direction overlap (including equal state)
            same_dir=int(np.sum(d0==prior)) if prior is not None else -1
            same_up=int(np.sum((d0==1)&(prior==1))) if prior is not None else -1
            hourbyring.append(dict(day=day,target_hour=hname,
                ring_step_old=k,ring_step_new=k+1,
                older_global_ring_id=full[k-1]["id"],
                newer_global_ring_id=full[k]["id"],
                older_end_draw=rows[full[k-1]["end"]-1]["id"],
                newer_end_draw=rows[full[k]["end"]-1]["id"],
                warming_count=len(rise),
                warming_numbers="-".join(str(j+1) for j in rise),
                warming_appeared_target_hour_count=len(warming_hit),
                warming_appeared_numbers="-".join(map(str,warming_hit)),
                cooling_count=len(fall),
                cooling_numbers="-".join(str(j+1) for j in fall),
                cooling_appeared_target_hour_count=len(cooling_hit),
                cooling_appeared_numbers="-".join(map(str,cooling_hit)),
                steady_count=len(stable),
                steady_appeared_target_hour_count=len(unchanged_hit),
                stable_appeared_numbers="-".join(map(str,unchanged_hit)),
                same_direction_as_prior_step=same_dir,
                same_warming_as_prior_step=same_up))
        if hi==len(hourset)-1:
            final_hour=(hname,t,ids,rings,full,S,W,D,
                        hits,bits,profiles_for_last)
            # Last hour exact every-ball every-physical-ring heat and direction.
            index={r["id"]:pos for pos,r in enumerate(full)}
            for ordinal,ring in enumerate(rings,1):
                prev=full[index[ring["id"]]-1] if ring["sealed"] and index[ring["id"]]>0 else None
                for j in range(80):
                    temp=int(ring["pool72"][j])
                    prevpool=int(prev["pool72"][j]) if prev is not None else None
                    lastfilm.append(dict(
                        target_hour=hname,H1_id=ids[0],H12_id=ids[-1],
                        ball=j+1,ring_order=ordinal,
                        absolute_ring_id=ring["id"],
                        ring_status=("DOLU" if ring["sealed"] else "ACIK"),
                        ring_12_capacity=ring["size"],
                        from_draw_id=rows[ring["begin"]]["id"],
                        to_draw_id=rows[ring["end"]-1]["id"],
                        seen_in_ring=int(ring["count12"][j]),
                        temp12=POOL[int(ring["pool12"][j])],
                        temp72=POOL[temp],
                        pool72_rank=temp,
                        direction_from_previous_sealed=(
                            "" if prevpool is None else temp-prevpool),
                        direction_symbol=(
                            "." if prevpool is None else
                            STEP_CHAR[int(np.sign(temp-prevpool))]),
                        target_hour_hands=bits[j],
                        target_hour_appearances=int(hits[j])))
            for k in range(12):
                draw=rows[t+k]
                lasttarget.append(dict(hour=hname,hand=k+1,draw_id=draw["id"],
                    time=draw["time"],
                    appeared_numbers="-".join(map(str,draw["nums"])),
                    warming_appeared_numbers="-".join(str(n) for n in draw["nums"]
                     if profiles_for_last[n-1]["direction_last6"]=="ISINIYOR"),
                    cooling_appeared_numbers="-".join(str(n) for n in draw["nums"]
                     if profiles_for_last[n-1]["direction_last6"]=="SOGUYOR"),
                    stable_appeared_numbers="-".join(str(n) for n in draw["nums"]
                     if profiles_for_last[n-1]["direction_last6"]=="DENGELI")))
        if hi%150==0:print("V102 hours",hi,"/",len(hourset),flush=True)

    last_name,t,ids,rings,full,S,W,D,hits,bits,profiles_for_last=final_hour
    lastsum=everyhour[-1]
    bygroup=[]
    for (phase,status),a in sorted(agg.items()):
        bygroup.append(dict(phase=phase,direction=status,
          number_hours=a[0],appeared_at_least_once_in_target_hour=a[1],
          total_appearances_in_hour=a[2],appeared_twice_plus=a[3],
          share_appeared_once_pct=100*a[1]/a[0],
          mean_appearances_per_ball_hour=a[2]/a[0]))
    # Inspect whether a given ball in successive sealed rings moves
    # identically; use all comparable steps across ALL hour anchors.
    comparisons=[x for x in hourbyring if x["same_direction_as_prior_step"]>=0]
    nsteps=len(comparisons)
    ratio=sum(x["same_direction_as_prior_step"] for x in comparisons)/(80*nsteps)
    pu=sum(x["same_warming_as_prior_step"] for x in comparisons)/(80*nsteps)
    # Strict full-chain monotonic warming not possible across 56-ring
    # relative 5-pool states, so show reverse turns, run lengths and
    # last3/6/12 net delta rather than misleading "56 times rising".
    early=bygroup
    warming=[r for r in profiles_for_last if r["direction_last6"]=="ISINIYOR"]
    warming_in=[r for r in warming if r["target_draw_count"]>0]
    cooled=[r for r in profiles_for_last if r["direction_last6"]=="SOGUYOR"]
    cooled_in=[r for r in cooled if r["target_draw_count"]>0]
    selected=[(r["number"],r["latest_sealed_pool72"],r["last6_net_pool_delta"],
               r["target_hands"]) for r in warming_in]
    report=[
      "V102 — SON 56 HALKA / 80 SAYI ISINMA-SOGUMA YON ZINCIRI",
      "KUPON veya KOR TEST DEGIL: gerçek halka yolunu ve hedef saat sonucunu birlestiren rapor.",
      f"Analiz edilen tam 12 cekilisli hedef saat: {len(hourset)}.",
      f"Reddedilen eksik/tutarsiz saat grubu: {skip}.",
      f"En son tam hedef saat: {last_name}, H1 #{ids[0]}, H12 #{ids[-1]}.",
      f"Hedef saat gelmeden bilinen son cekilis #{rows[t-1]['id']}; referans ilk #{rows[t-672]['id']}.",
      f"56-57 fiziki halka; tam 12 cekilisli sabit halka: {len(full)}; acik halkalar ayri.",
      "80 sayinin her birinde onceki 55/56 DOLU halkanin C/S/N/I/H havuz dizisi,",
      "Y(isi)/D(sogu)/=(sabit) tam YON ZINCIRI ve hedef saatin H1..H12 bitleri bulunur.",
      "Her halka gecisinde YUKSELEN sayilar ve bunlarin hedef saatte gelenleri ayri listelenir.",
      "Isinma tanimi: son 6 TAM halkanin 72-cekimlik havuz ranki net yukari.",
      "Hedef saatin gercek 12 sonucu ISINMA etiketleri hesaplandiktan sonra eslestirilir.",
      "",
      "SON HEDEF SAAT GOSTERGELERI:",
      f" Isinan sayi={len(warming)}, bu saatte gorunen farkli isinan={len(warming_in)}.",
      f" Soguyan sayi={len(cooled)}, bu saatte gorunen farkli soguyan={len(cooled_in)}.",
      f" Sabit yonlu sayi={lastsum['stable_count']}, gorunen={lastsum['stable_target_hour_different_numbers']}.",
      f" 12 cekiliste 20x12 = {lastsum['total_hits_in_hour']} toplu gorunum.",
      "Son 6 halkada ISINAN ve hedef saatte gorunenler (numara,son tam havuz,net delta,eller):"]
    for num,pool,delta,hands in selected:
        report.append(f" {num:2d} {pool:6s} {delta:+d} H:{hands}")
    report.extend(["",
      "GENEL HAREKET KARSILASTIRMASI:",
      f" Her sayinin ardarda iki halka ADIMINDA ayni yonu koruma orani (duranlar dahil) = {100*ratio:.3f}%.",
      f" Her sayinin ardarda iki halka ADIMINDA ust uste isinmasi = {100*pu:.3f}%.",
      " Yon zincirinde her sayi icin tam isinma sayisi, soguma sayisi, durağan sayisi,",
      " maksimum ust uste isinma, yon degistirme ve hedef saatteki H1..H12 kayitli.",
      "Halkalar ayni yonle hareket ediyor mu sorusunu ham diziyle gorebilirsiniz.",
      "",
      "Gecmisteki tum hedef saatlerde son 6 halka yonu -> hedef saat gorunum ozeti:"])
    for a in bygroup:
        report.append(f" {a['phase']:10s} {a['direction']:8s} adet={a['number_hours']} "
             f"gorunen={a['appeared_at_least_once_in_target_hour']} "
             f"gorunme%={a['share_appeared_once_pct']:.3f} "
             f"saatte ort.kez={a['mean_appearances_per_ball_hour']:.4f}")
    report.extend(["",
      "DOSYALAR:",
      "01 Tum saatler x 80 sayinin 55-56 halka sicaklik ve yon DNA zinciri.",
      "02 Tum saatler x her halkada ISINAN/SOGUYAN/SABIT sayilar; saatte hangileri geldi.",
      "03 Son saat icin 80 x 56-57 satirlik ayrintili halka filmi.",
      "04 Son saatin 12 cekilisinde gelen ve o anda isinan/soguyan sayilar.",
      "05 Saatlik hareket-kadro ozeti ve 06 tum gunler grup ozeti.",
      "07 Metot ve veri denetimi.",
      "",
      "C/S/N/I/H = Soguk, Serin, Notr, Ilik, Sicak.",
      "Y/D/= = sicakliga dogru, soguga dogru, sabit hareket.",
      "Tum halkalar GECMIS veriye gore belirlenir, hedef saat YALNIZCA etiketlenir.",
      "Bu bir aciklama ve gozlem aracidir; sayilarin gelecekteki isabetini iddia etmez."
    ])
    meta=dict(version=VERSION,source_draws=len(rows),
        date_start=days[0],date_end=days[-1],
        total_hour_targets=len(hourset),rejected_hours=skip,
        target_clock_format="HH:02 through HH:57, twelve draws",
        last_target_hour=last_name,last_hour_first_id=ids[0],
        last_hour_last_id=ids[-1],
        last_hour_lookback_from_id=rows[t-672]["id"],
        last_hour_lookback_to_id=rows[t-1]["id"],
        per_hour_history_draws=672,per_hour_ring_capacity=12,
        per_hour_sealed_rings=[55,56],
        pools=POOL,temperature_basis="last72 observed draws at each sealed ring end",
        pool12_basis="12 observed draws inside ring",
        warming_basis="latest sealed pool72 rank minus rank 6 sealed rings ago",
        directions=STEP_CHAR,
        source_issues=issues[:20],malformed_line_numbers=bad[:20],
        warning="This is description of future hour already observed; NOT a predictive backtest.")
    dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V102_56_HALKA_YON_SONUCLARI.txt","\n".join(report)+"\n")
        csvw(z,"01_TUM_SAATLER_80_SAYI_56_HALKA_ZINCIRI.csv",allprofiles)
        csvw(z,"02_TUM_SAATLER_HALKA_BASINA_ISINAN_VE_HEDEFTE_CIKAN.csv",hourbyring)
        csvw(z,"03_SON_HEDEF_SAAT_80x56_TAM_HAREKET_FILMI.csv",lastfilm)
        csvw(z,"04_SON_HEDEF_SAAT_12_EL_CIKANLAR_YONLER.csv",lasttarget)
        csvw(z,"05_TUM_HEDEF_SAAT_80_SAYI_YON_DAGILIMI.csv",everyhour)
        csvw(z,"06_GECMIS_GUNLER_YON_GRUBU_SAATTE_GORUNUM.csv",bygroup)
        z.writestr("07_VERI_YON_KODU_DENETIM.json",json.dumps(
            meta,indent=2,ensure_ascii=False,default=str))
    print("\n".join(report),flush=True)
    print("V102 SUCCESS",dst,dst.stat().st_size,flush=True)

def selftest():
    assert longest([1,1,0,1,1,1],1)==3
    assert trailing([1,0,1,1],1)==2
    assert turns([1,0,0,-1,-1,0,1])==2
    assert tuple(range(2,60,5))==HHMIN
    # Fixed absolute rings in original V100C were verified separately.
    print("V102 SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--out",default="v102_output/V102_80_SAYI_56_HALKA_YON_ZINCIRI_HEDEF_SAAT.zip")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
