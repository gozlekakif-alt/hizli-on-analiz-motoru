#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone Hızlı On RNG Karakter Laboratuvarı (V56).

Strictly read-only ingestion. 80 numbers, 20 distinct per draw, 217 slots/day.
Every hourly forecast and 10-number ticket is frozen after FIRST SIX draws.
Training data includes only fully scored EARLIER hour windows. Historical
score is exploratory; future audit begins 2026-10-16, first 14 full days.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Iterable
import csv
import hashlib
import io
import json
import math
import random
import re
import statistics
import zipfile

SLOTS = (
    [f"00:{2 + 5*i:02d}" for i in range(12)] + ["01:02"] +
    [f"{(422+5*i)//60:02d}:{(422+5*i)%60:02d}" for i in range(204)]
)
assert len(SLOTS) == len(set(SLOTS)) == 217
SLOT_INDEX = {time: pos for pos,time in enumerate(SLOTS,1)}
BLOCKS = [{"hour":"H00","label":"00:02–01:02","positions":list(range(1,14))}]
for h in range(7,24):
    offset=14+(h-7)*12
    BLOCKS.append({"hour":f"H{h:02d}","label":f"{h:02d}:02–{h:02d}:57",
                   "positions":list(range(offset,offset+12))})
assert sum(len(x["positions"]) for x in BLOCKS)==217 and len(BLOCKS)==18

RE = re.compile(r"^(\d+);(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2});([\d,\s]+)$")
FORWARD_START = date(2026,10,16)
FORWARD_DAYS = 14
HIST_MIN_HOURS = 96
VALIDATE_HOURS = 180
MATCH_NEIGHBORS = 48
WEIGHT_REAL = 0.42
BAND_BASE = [2.5]*8
HEAT_BASE = [4.0]*5
LAST_BASE = 5.0
TRIPLE_BASE = (20*19*18)/(80*79*78)
MODEL_IDS = ("KARAKTER10","KARAKTERSIZ10","RASTGELE10")

def read_txt(raw: str):
    """Return complete-day dictionary, partial-day counts and rejected line log."""
    seen_by_day=defaultdict(dict)
    ids=set()
    rejects=[]
    for line_number,line in enumerate(raw.splitlines(),1):
        line=line.strip()
        if not line or ";" not in line:
            continue
        m=RE.fullmatch(line)
        if not m:
            rejects.append(f"satir {line_number}: format")
            continue
        ident,dd,mm,yy,hh,mins,ns=m.groups()
        try:
            day=date(int(yy),int(mm),int(dd)).isoformat()
            clock=f"{hh}:{mins}"
            pos=SLOT_INDEX[clock]
            numbers=tuple(sorted(int(v.strip()) for v in ns.split(",")))
            ident=int(ident)
        except (ValueError,KeyError):
            rejects.append(f"satir {line_number}: tarih veya sayi")
            continue
        if len(numbers)!=20 or len(set(numbers))!=20 or numbers[0]<1 or numbers[-1]>80:
            rejects.append(f"satir {line_number}: gecersiz 20 sayi")
            continue
        if pos in seen_by_day[day] or ident in ids:
            rejects.append(f"satir {line_number}: mukerrer")
            continue
        ids.add(ident)
        seen_by_day[day][pos]={"id":ident,"day":day,"slot":pos,
                               "time":clock,"nums":frozenset(numbers)}
    full={}
    partial={}
    for day,bypos in sorted(seen_by_day.items()):
        if len(bypos)==217 and set(bypos)==set(range(1,218)):
            full[day]=[bypos[i] for i in range(1,218)]
        else:
            partial[day]={"valid":len(bypos),"missing":217-len(bypos)}
    return full,partial,rejects

def counts_for(history):
    return Counter(n for draw in history for n in draw["nums"])

def context(earlier, first6):
    """Known to first6 completion; never accesses target six draws."""
    rolling=earlier[-72:]
    source=rolling+first6
    cn=counts_for(source)
    # Quantile-by-rank: exactly 16 numbers in each of 5 heat cohorts.
    ranks=sorted(range(1,81),key=lambda n:(cn[n],n))
    heat={number:ix//16 for ix,number in enumerate(ranks)}
    cf=counts_for(first6)
    fb=[0]*8
    fh=[0]*5
    for row in first6:
        for n in row["nums"]:
            fb[(n-1)//10]+=1
            fh[heat[n]]+=1
    # First6 most frequent exact triplet; no post-target family selection.
    freq3=Counter(tri for draw in first6 for tri in combinations(sorted(draw["nums"]),3))
    triplet=min(freq3,key=lambda t:(-freq3[t],t))
    overlaps=[len(first6[i]["nums"]&first6[i-1]["nums"]) for i in range(1,6)]
    feats=tuple([(v/6-2.5)/1.4 for v in fb]+
       [(v/6-4)/1.7 for v in fh]+
       [(sum(overlaps)/5-5)/1.6,
        (freq3[triplet]-1.0)/1.3])
    return {"heat":heat,"counts":cn,"firstcounts":cf,"band":[n/6 for n in fb],
            "temperature":[n/6 for n in fh],
            "last":frozenset(first6[-1]["nums"]),
            "triplet":triplet,"features":feats}

def measure(ctx,second6):
    band=[0]*8
    heat=[0]*5
    triplet=frozenset(ctx["triplet"])
    count_last=0
    count_triplet=0
    for draw in second6:
        nums=draw["nums"]
        for n in nums:
            band[(n-1)//10]+=1
            heat[ctx["heat"][n]]+=1
        count_last+=len(nums&ctx["last"])
        count_triplet+=int(triplet.issubset(nums))
    return {"band":[v/6 for v in band],
            "temperature":[v/6 for v in heat],
            "last":count_last/6,"triplet":count_triplet/6}

def prediction(ctx,history):
    prior={"band":BAND_BASE[:],"temperature":HEAT_BASE[:],
           "last":LAST_BASE,"triplet":TRIPLE_BASE}
    if len(history)<HIST_MIN_HOURS:
        return prior,"ADIL_RNG_BAZ"
    nearest=sorted(history,key=lambda x:
          sum((a-b)**2 for a,b in zip(ctx["features"],x[0])))[:MATCH_NEIGHBORS]
    ws=[1/(1.0+sum((a-b)**2 for a,b in zip(ctx["features"],x[0])))
        for x in nearest]
    total=sum(ws)
    output={}
    for key in prior:
        if isinstance(prior[key],list):
            output[key]=[(1-WEIGHT_REAL)*p+WEIGHT_REAL*sum(
                w*item[1][key][i] for w,item in zip(ws,nearest))/total
                for i,p in enumerate(prior[key])]
        else:
            output[key]=(1-WEIGHT_REAL)*prior[key]+WEIGHT_REAL*sum(
                w*item[1][key] for w,item in zip(ws,nearest))/total
    return output,"GECMIS_SAAT_BENZERLIGI"

def character_loss(forecast,truth):
    band=sum(abs(a-b) for a,b in zip(forecast["band"],truth["band"]))/8
    heat=sum(abs(a-b) for a,b in zip(
        forecast["temperature"],truth["temperature"]))/5
    last=abs(forecast["last"]-truth["last"])
    trio=(forecast["triplet"]-truth["triplet"])**2
    return {"band":band,"temperature":heat,"last":last,"triplet":trio}

def gate(previous_errors):
    recent=previous_errors[-VALIDATE_HOURS:]
    if len(recent)<VALIDATE_HOURS:
        return False,{"band":0.0,"temperature":0.0,"last":0.0,"coupon":0.0}
    delta={}
    for key in ("band","temperature","last"):
        delta[key]=statistics.mean(
            r["baseline_"+key]-r["model_"+key] for r in recent)
    delta["coupon"]=statistics.mean(
        r["character_hit"]-r["simple_hit"] for r in recent)
    # Improvement must persist in at least 2 character dimensions,
    # AND character-based 10-number selection must beat fixed control.
    signal=sum(delta[k]>0.01 for k in ("band","temperature","last"))>=2
    signal=signal and delta["coupon"]>0.05
    return signal,delta

def _quotas(targets,total=10):
    s=sum(targets)
    share=[v*total/s for v in targets]
    items=[int(v) for v in share]
    order=sorted(range(len(items)),key=lambda i:(-(share[i]-items[i]),i))
    for i in order[:total-sum(items)]:
        items[i]+=1
    return items

def ticket(ctx,forecast,day,hour):
    base=lambda n:(ctx["counts"][n]+0.8*ctx["firstcounts"][n])
    sorted_numbers=sorted(range(1,81),key=lambda n:(-base(n),n))
    fixed=tuple(sorted(sorted_numbers[:10]))
    limits_band=_quotas(forecast["band"])
    limits_heat=_quotas(forecast["temperature"])
    chosen=[]; used_band=Counter();used_heat=Counter()
    while len(chosen)<10:
        def value(n):
            b=(n-1)//10;h=ctx["heat"][n]
            ratio=base(n)
            bonus=0.45*(forecast["band"][b]-2.5)+0.38*(forecast["temperature"][h]-4.0)
            family=0.3*int(n in ctx["triplet"] and forecast["triplet"]>TRIPLE_BASE+0.006)
            over=1.5*max(0,used_band[b]+1-limits_band[b])+1.3*max(
                0,used_heat[h]+1-limits_heat[h])
            return ratio+bonus+family-over
        remaining=[n for n in range(1,81) if n not in chosen]
        best=min(remaining,key=lambda n:(-value(n),n))
        chosen.append(best)
        used_band[(best-1)//10]+=1
        used_heat[ctx["heat"][best]]+=1
    seed=int(hashlib.sha256(f"RNG_LAB_V1|{day}|{hour}|rng".encode()
             ).hexdigest()[:24],16)
    rand=tuple(sorted(random.Random(seed).sample(range(1,81),10)))
    return {"KARAKTER10":tuple(sorted(chosen)),
            "KARAKTERSIZ10":fixed,
            "RASTGELE10":rand}

def audit(full):
    """Chronological, frozen-hour predictions, no use of the target in training."""
    ordered=sorted(full)
    allowed_forward=set(d for d in ordered if d>=str(FORWARD_START)) 
    allowed_forward=set(sorted(allowed_forward)[:FORWARD_DAYS])
    history=[];training=[];error_log=[]
    characters=[];coupon_scores=[]
    for day in ordered:
        if day>=str(FORWARD_START) and day not in allowed_forward:
            continue
        phase="ILERI" if day in allowed_forward else "GECMIS"
        rows=full[day]
        for b in BLOCKS:
            hour=[rows[p-1] for p in b["positions"]]
            first6,target6=hour[:6],hour[6:12]
            ctx=context(history,first6)
            forecast,method=prediction(ctx,training)
            emit,delta=gate(error_log)
            if len(training)<HIST_MIN_HOURS:
                emit=False
            coupons=ticket(ctx,forecast,day,b["hour"])
            # All selection above depends ONLY on known prior draws and first6.
            actual=measure(ctx,target6)
            loss=character_loss(forecast,actual)
            ref=character_loss({"band":BAND_BASE[:],
               "temperature":HEAT_BASE[:],"last":LAST_BASE,
               "triplet":TRIPLE_BASE},actual)
            char={
                "day":day,"phase":phase,"hour":b["hour"],
                "train_hours":len(training),"method":method,
                "signal":int(emit),
                "band_pred":"|".join(f"{v:.3f}" for v in forecast["band"]),
                "band_real":"|".join(f"{v:.3f}" for v in actual["band"]),
                "heat_pred":"|".join(f"{v:.3f}" for v in forecast["temperature"]),
                "heat_real":"|".join(f"{v:.3f}" for v in actual["temperature"]),
                "overlap_pred":round(forecast["last"],4),
                "overlap_real":round(actual["last"],4),
                "trio_pred":round(forecast["triplet"],6),
                "trio_real":round(actual["triplet"],6),
                "trio_family":"-".join(map(str,ctx["triplet"])),
                "band_loss":round(loss["band"],5),
                "band_base_loss":round(ref["band"],5),
                "heat_loss":round(loss["temperature"],5),
                "heat_base_loss":round(ref["temperature"],5),
                "overlap_loss":round(loss["last"],5),
                "overlap_base_loss":round(ref["last"],5),
                "trio_loss":round(loss["triplet"],6),
                "trio_base_loss":round(ref["triplet"],6),
                "gate_band":round(delta["band"],5),
                "gate_heat":round(delta["temperature"],5),
                "gate_overlap":round(delta["last"],5),
                "gate_coupon":round(delta["coupon"],5),
            }
            characters.append(char)
            hit_sums=Counter()
            for target in target6:
                for model,nums in coupons.items():
                    count=len(target["nums"].intersection(nums))
                    hit_sums[model]+=count
                    coupon_scores.append({
                        "day":day,"phase":phase,"hour":b["hour"],
                        "target_id":target["id"],"target_time":target["time"],
                        "signal":int(emit),"mode":model,
                        "coupon":"-".join(map(str,nums)),
                        "hits":count,"at_least7":int(count>=7),
                        "at_least8":int(count>=8),"at_least9":int(count>=9),
                        "all10":int(count==10)})
            error_log.append({
                **{"baseline_"+k:ref[k] for k in ("band","temperature","last")},
                **{"model_"+k:loss[k] for k in ("band","temperature","last")},
                "character_hit":hit_sums["KARAKTER10"]/6,
                "simple_hit":hit_sums["KARAKTERSIZ10"]/6,
            })
            training.append((ctx["features"],actual))
            history.extend(hour)
    return characters,coupon_scores

def summary(characters,coupons):
    rows=[]
    for phase in ("GECMIS","ILERI"):
        good=[x for x in characters if x["phase"]==phase and x["train_hours"]>=HIST_MIN_HOURS]
        score=[x for x in coupons if x["phase"]==phase]
        rng_count=[x for x in score if x["mode"]=="RASTGELE10"]
        row={"period":phase,"hours":len(good),
             "signal_hours":sum(x["signal"] for x in good),
             "targets":len(rng_count)}
        for key in ("band","heat","overlap"):
            row[key+"_model"]=round(statistics.mean(x[key+"_loss"] for x in good),5) if good else ""
            row[key+"_base"]=round(statistics.mean(x[key+"_base_loss"] for x in good),5) if good else ""
        for mode in MODEL_IDS:
            group=[x for x in score if x["mode"]==mode]
            row[mode+"_avg"]=round(statistics.mean(x["hits"] for x in group),5) if group else ""
            row[mode+"_7plus"]=sum(x["at_least7"] for x in group)
            row[mode+"_8plus"]=sum(x["at_least8"] for x in group)
            gated=[x for x in group if x["signal"]]
            row[mode+"_when_signal"]=round(statistics.mean(x["hits"] for x in gated),5) if gated else ""
        rows.append(row)
    return rows

def _top_families(hour,k=3,top=8):
    """Only same-20-number draws count. Candidate families from intersection."""
    support=Counter()
    for i,first in enumerate(hour):
        for second in hour[i+1:]:
            common=first["nums"]&second["nums"]
            if len(common)>=k:
                for fam in combinations(sorted(common),k):
                    support[fam]=0
    for fam in support:
        target=set(fam)
        support[fam]=sum(target.issubset(r["nums"]) for r in hour)
    return sorted(support.items(),key=lambda x:(-x[1],x[0]))[:top]

def family_migrations(rows):
    """Exact families from all 18 hours, with change of one member tracked."""
    all_hours=[]
    for b in BLOCKS:
        hour=[rows[p-1] for p in b["positions"]]
        all_hours.append({k:_top_families(hour,k) for k in (3,4,5)})
    event=[]
    stat=Counter()
    for pos in range(17):
        for k in (3,4,5):
            a=all_hours[pos][k];b=all_hours[pos+1][k]
            second=dict(b)
            for fam,frequency in a:
                if fam in second:
                    matched=fam;state="AYNI";after=second[fam]
                else:
                    candidates=[(v,s) for v,s in b if len(set(fam)&set(v))==k-1]
                    if candidates:
                        matched,after=min(candidates,key=lambda x:(-x[1],x[0]))
                        state="BIR_SAYI_DEGISTI"
                    else:
                        matched=();after=0;state="YOK"
                stat[(k,state)]+=1
                event.append({
                    "from_hour":BLOCKS[pos]["hour"],"to_hour":BLOCKS[pos+1]["hour"],
                    "size":k,"previous":"-".join(map(str,fam)),
                    "next":"-".join(map(str,matched)),
                    "prev_support":frequency,"next_support":after,
                    "status":state,"night_gap":int(pos==0)})
    return stat,event

def _hour_range(rows):
    data=[]
    for b in BLOCKS:
        draws=[rows[p-1] for p in b["positions"]]
        counts=[sum(int((n-1)//10==idx) for r in draws for n in r["nums"])
                for idx in range(8)]
        data.append(max(counts)-min(counts))
    return statistics.mean(data)

def fair_simulation(observed_day,n=80):
    if n<1:raise ValueError("Simülasyon sayısı en az 1 olmalı")
    real_stat,events=family_migrations(observed_day)
    real_spread=_hour_range(observed_day)
    labels=[(k,c) for k in (3,4,5) for c in ("AYNI","BIR_SAYI_DEGISTI","YOK")]
    samples={key:[] for key in labels}
    ranges=[]
    for i in range(n):
        rng=random.Random(506_001+i)
        virtual=[{"nums":frozenset(rng.sample(range(1,81),20))}
                 for j in range(217)]
        stat,_=family_migrations(virtual)
        ranges.append(_hour_range(virtual))
        for key in labels:
            samples[key].append(stat[key])
    output=[]
    for key in labels:
        vals=samples[key]
        observed=real_stat[key]
        output.append({
          "measure":f"{key[0]}_{key[1]}","real":observed,
          "rng_mean":round(statistics.mean(vals),4),
          "rng_low":sorted(vals)[max(0,int(n*.05)-1)],
          "rng_high":sorted(vals)[min(n-1,int(n*.95))],
          "exploratory_p_upper":round((1+sum(v>=observed for v in vals))/(n+1),5),
          "sim_days":n})
    output.append({
      "measure":"SAATLIK_BANT_DENGESIZLIGI",
      "real":round(real_spread,4),
      "rng_mean":round(statistics.mean(ranges),4),
      "rng_low":round(sorted(ranges)[max(0,int(n*.05)-1)],4),
      "rng_high":round(sorted(ranges)[min(n-1,int(n*.95))],4),
      "exploratory_p_upper":round((1+sum(v>=real_spread for v in ranges))/(n+1),5),
      "sim_days":n})
    return output,events

def _csv_archive(z,name,rows):
    if not rows:
        z.writestr(name,"(Veri yok)\n");return
    with z.open(name,"w",force_zip64=True) as buf:
        writer=io.TextIOWrapper(buf,encoding="utf-8",newline="")
        fields=list(rows[0])
        wr=csv.DictWriter(writer,fieldnames=fields)
        wr.writeheader();wr.writerows(rows)
        writer.flush();writer.detach()

def build_package(full,partial,invalid,day=None,sims=80):
    if not full:raise ValueError("En az bir tam gün gerekli.")
    chosen=day or sorted(full)[-1]
    if chosen not in full:raise ValueError("Tam olmayan veya bulunmayan gün: "+chosen)
    char,coupons=audit(full)
    stats=summary(char,coupons)
    monte,families=fair_simulation(full[chosen],n=sims)
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        details=[
          "HIZLI ON RNG KARAKTER LABORATUVARI — AYRI PROGRAM",
          f"Secilen gun: {chosen} | {len(full)} tam gun | {sims} sanal adil RNG gunu.",
          f"Yeni kilitli kor sinav: {FORWARD_START.isoformat()} ve sonrasindaki ILK 14 tam gun.",
          f"Mevcut ileri tam gun: {sum(d>=str(FORWARD_START) for d in full)}",
          f"Eksik gün: {len(partial)}; hatalı/mükerrer satır: {len(invalid)}",
          "1. KARAKTER: Son 72 ve ilk6'ya göre sonraki6'nın bant/ısı/tekrar/trio davranışı.",
          "2. SAYI: Karakterli 10'lu, karakter kullanmayan 10'lu ve sabitlenmiş RNG 10'lu.",
          "3. SAATLIK AILE: 3/4/5'li ilk8 aile, saatten saate aynı/bir sayı değişti/yok.",
          "4. ADIL SIMULASYON: 20 benzersiz sayı, 80 havuz, 217 bağımsız çekiliş/gün.",
          "5. ASIL KRITER: Yeni günlerde karakter hatası azalmalı ve KUPON üstünlüğü görülmeli.",
          "Geriye dönük yüksek isabet tek başına gelecek tahmini kanıtı değildir.",
          "Yalnız 217/217 tam günler kullanıldı; canlı veya eksik günler tahmin gibi doldurulmadı.",
          "Bu laboratuvar eski GitHub dosyalarına hiçbir veri YAZMAZ.",
          "",
          "OZET",
        ]
        for r in stats:
            details.append(str(r))
        details.extend(["","SAYISAL ADIL RNG KIYASI"])
        details.extend(str(r) for r in monte)
        z.writestr("00_TEK_RAPOR_OZET.txt","\n".join(details)+"\n")
        _csv_archive(z,"01_KARAKTER_TAHMIN_VE_GERCEK.csv",char)
        _csv_archive(z,"02_KUPON_3_KONTROL_ISABET.csv",coupons)
        _csv_archive(z,"03_KOR_TEST_OZET.csv",stats)
        _csv_archive(z,"04_AILE_SAATTEN_SAATE_GECIS.csv",families)
        _csv_archive(z,"05_GERCEK_VE_SANAL_RNG_KARSILASTIR.csv",monte)
        z.writestr("06_VERI_KONTROL.json",json.dumps({
            "source":"Hizli On veri.txt",
            "full_days":len(full),"selected":chosen,
            "invalid_rows":invalid[:100],"invalid_count":len(invalid),
            "partial_days":partial,
            "future_start":str(FORWARD_START),
            "forward_count":sum(d>=str(FORWARD_START) for d in full),
            "seed_simulation":506001,
            "independence":"20 of 80 without replacement within a draw, independent draws",
        },ensure_ascii=False,indent=2))
        z.writestr("07_KILITLI_KURALLAR.txt",
            "Her saat ilk6 gelmeden hiçbir gelecek sonucu kullanılamaz.\n"
            "İlk6 tamamlanınca 3 adet 10'lu kupon SABİTLENİR.\n"
            "Karakter hata farkları ve kupon doğrulaması birbirinden AYRI tutulur.\n"
            "İlk 96 saat temel RNG modelidir, sonra önceki saatler en yakın 48 örnekle kullanılır.\n"
            "Kapı: son 180 saat bant/ısı/örtüşmeden en az ikisinde MAE iyileşmesi>0.01 "
            "ve aynı saatli karakter kuponu ile karaktersiz kupon ortalama farkı>0.05.\n"
            "Sinyal yoksa gerçek kupon önerilmez; üç kontrol gölgede ölçülür.\n"
            "İlk 14 tam gün için gelecekteki sınav tarihi 2026-10-16'dan başlar.\n"
            "Yeni program bağımsız bir Streamlit giriş dosyasıdır. veri.txt'nin GitHub RAW "
            "bağlantısını salt-okunur kullanır veya dosya yükleme kabul eder.\n")
    return buf.getvalue(),{"chosen":chosen,"sims":monte,"summary":stats,
                            "audit_hours":len(char),"future_days":sum(d>=str(FORWARD_START) for d in full),
                            "family_transitions":len(families)}

def smoke_test():
    rng=random.Random(100)
    def day(name,start_id):
        nums=[tuple(rng.sample(range(1,81),20)) for _ in range(217)]
        return [
            {"id":start_id+i,"day":name,"slot":i+1,"time":SLOTS[i],
             "nums":frozenset(ns)} for i,ns in enumerate(nums)]
    data={"2026-10-10":day("2026-10-10",10000)}
    first=data["2026-10-10"]
    ctx=context([],first[:6])
    assert len(ctx["heat"])==80
    forecast,method=prediction(ctx,[])
    picks=ticket(ctx,forecast,"2026-10-10","H07")
    assert all(len(v)==10 and len(set(v))==10 for v in picks.values())
    freeze=ticket(ctx,forecast,"2026-10-10","H07")
    first[8]["nums"]=frozenset(range(61,81))
    assert freeze==ticket(ctx,forecast,"2026-10-10","H07")
    char,coupon=audit(data)
    assert len(char)==18 and len(coupon)==18*6*3
    assert all(v["signal"]==0 for v in char)
    check=measure(ctx,first[6:12])
    assert abs(sum(check["band"])-20)<1e-9
    assert abs(sum(check["temperature"])-20)<1e-9
    fake,meta=build_package(data,{},[],sims=3)
    with zipfile.ZipFile(io.BytesIO(fake)) as z:
        assert len(z.namelist())==8
        assert z.read("01_KARAKTER_TAHMIN_VE_GERCEK.csv")
    print("PASS: 217 slots, no future leakage, real+fair RNG, 3 tickets, single ZIP")

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="../veri.txt")
    p.add_argument("--output",default="/tmp/rng_laboratuvar_tek_rapor.zip")
    p.add_argument("--sims",type=int,default=80)
    p.add_argument("--day")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        smoke_test()
    else:
        days,partial,invalid=read_txt(Path(args.data).read_text(encoding="utf-8-sig"))
        report,metadata=build_package(days,partial,invalid,day=args.day,sims=args.sims)
        Path(args.output).write_bytes(report)
        print(json.dumps({"output":args.output,**metadata},ensure_ascii=False))
