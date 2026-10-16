#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V97: 80 numbers and their different multi-day lottery families.

Three non-interchangeable definitions:
A) 20-number complete draw roster around a particular ball.
B) V10 frozen list of 1131 exact 5..10-number groups, counted as
   observed only when the ENTIRE group appears in the same draw.
C) Natural 5..10-number roots: exact intersection of one draw with
   any of previous <=12 ID-consecutive draws; a root occurrence can
   arise from more than one parent, deduplicated within target draw.
   Intersection >10 is NOT truncated; instead skipped to avoid bias.
No hindsight group indicates predictive superiority.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,statistics,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

N=80
SIZES=range(5,11)
EXPECTED_DAYS=72
EXPECTED_DRAWS=15624
VERSION="V97.1"

def bitmask(nums):
    return sum(1<<(int(x)-1) for x in nums)

def bits(mask):
    return [j+1 for j in range(80) if mask>>j&1]

def data(path,catalogpath):
    daily,issues,malformed=parse_txt(path)
    dates=sorted(d for d,rs in daily.items() if len(rs)==217
                  and [r["pos"] for r in rs]==list(range(1,218)))
    if len(dates)!=EXPECTED_DAYS or dates[0]!="2026-08-01" or dates[-1]!="2026-10-12":
        raise RuntimeError(f"Expected 72 full days, got {len(dates)}")
    rows=[r for d in dates for r in daily[d]]
    if len(rows)!=EXPECTED_DRAWS:raise AssertionError("Incomplete day records")
    with Path(catalogpath).open(encoding="utf-8-sig",newline="") as f:
        fam=[(tuple(map(int,r["Aile"].split("-"))),int(r["Boyut"]),
              str(r["Kaynak"])) for r in csv.DictReader(f,delimiter=";")]
    assert len(fam)==1131 and all(len(nums)==k and 5<=k<=10 for nums,k,_ in fam)
    return dates,rows,fam,issues,malformed

def crunch(dates,rows,fam):
    masks=[bitmask(r["nums"]) for r in rows]
    drawcounts=np.zeros(80,dtype=np.int32)
    partner=np.zeros((80,80),dtype=np.int32)
    rosters=[set() for _ in range(80)]
    for i,r in enumerate(rows):
        ar=np.asarray(r["nums"],dtype=int)-1
        drawcounts[ar]+=1
        partner[np.ix_(ar,ar)]+=1
        for a in ar:rosters[a].add(masks[i])
    np.fill_diagonal(partner,0)
    # Catalogue observed whole-family co-occurrence and distinct DAY.
    catalogue=[]
    for ns,k,source in fam:
        key=bitmask(ns)
        seen=0
        daybits=0
        for i,m in enumerate(masks):
            if key&m==key:
                seen+=1
                daybits|=1<<(i//217)
        catalogue.append(dict(family="-".join(map(str,ns)),
            numbers=ns,size=k,source=source,
            total_full_draws=seen,distinct_days=daybits.bit_count(),
            daybits=daybits))
    members=[[] for _ in range(80)]
    for f in catalogue:
        for n in f["numbers"]:members[n-1].append(f)
    # Natural rooted families: exact intersections with previous 12 real draws.
    root={}
    skipped_gt10=0
    root_events=0
    for i,mask in enumerate(masks):
        currentroots=set()
        for j in range(i-1,max(i-13,-1),-1):
            if int(rows[j+1]["id"])!=int(rows[j]["id"])+1:
                break
            common=mask&masks[j]
            size=common.bit_count()
            if size>10:
                skipped_gt10+=1
                continue
            if 5<=size<=10: currentroots.add(common)
        for key in currentroots:
            root_events+=1
            if key not in root: root[key]=[0,0,int(rows[i]["id"]),i]
            root[key][0]+=1
            root[key][1]|=1<<(i//217)
    naturals=[dict(family="-".join(map(str,bits(k))),size=k.bit_count(),
          total_root_events=v[0],distinct_days=v[1].bit_count(),
          first_draw_id=v[2],key=k) for k,v in root.items()]
    rootmembers=[[] for _ in range(80)]
    for famitem in naturals:
        for n in bits(famitem["key"]):rootmembers[n-1].append(famitem)
    bynumber=[]
    bypartner=[]
    for n in range(1,81):
        c=members[n-1]
        nr=rootmembers[n-1]
        ordered=sorted(((int(partner[n-1,p-1]),p) for p in range(1,81) if p!=n),
                       key=lambda x:(-x[0],x[1]))
        dominant=max(c,key=lambda x:(x["total_full_draws"],x["distinct_days"]),
                     default=None)
        lead=sorted(nr,key=lambda x:(-x["distinct_days"],-x["total_root_events"],x["family"]))
        rec=dict(number=n,draws_with_number=int(drawcounts[n-1]),
           distinct_20_number_rosters=len(rosters[n-1]),
           distinct_other_number_partners=int((partner[n-1]>0).sum()),
           top_partner=ordered[0][1],top_partner_together=ordered[0][0],
           top_partner_pct_given_number=round(ordered[0][0]/drawcounts[n-1]*100,3),
           registered_catalogue_families=len(c),
           registered_families_ever_fully_seen=sum(x["distinct_days"]>0 for x in c),
           registered_families_seen_2plus_days=sum(x["distinct_days"]>=2 for x in c),
           registered_families_seen_5plus_days=sum(x["distinct_days"]>=5 for x in c),
           registered_families_never_seen=sum(x["distinct_days"]==0 for x in c),
           most_often_completed_registered_family=dominant["family"] if dominant else "",
           most_often_completed_family_draws=dominant["total_full_draws"] if dominant else 0,
           most_often_completed_family_days=dominant["distinct_days"] if dominant else 0,
           natural_roots_5to10_distinct=len(nr),
           natural_roots_reappeared_2plus_days=sum(x["distinct_days"]>=2 for x in nr),
           natural_roots_3plus_days=sum(x["distinct_days"]>=3 for x in nr),
           natural_top_multiday_root=lead[0]["family"] if lead else "",
           natural_top_root_days=lead[0]["distinct_days"] if lead else 0)
        for k in SIZES:
            rec[f"catalogue_{k}"]=sum(x["size"]==k for x in c)
            rec[f"catalogue_observed_{k}"]=sum(x["size"]==k and x["distinct_days"]>0 for x in c)
            rec[f"natural_{k}"]=sum(x["size"]==k for x in nr)
        bynumber.append(rec)
        for value,p in ordered[:10]:
            bypartner.append(dict(number=n,partner=p,draws_together=value,
              pct_condition_number=round(100*value/drawcounts[n-1],4)))
    catalogcsv=[{k:v for k,v in c.items() if k not in ("numbers","daybits")} for c in catalogue]
    # Rank natural roots that occur on multiple distinct days; only highest 300
    multi=sorted((x for x in naturals if x["distinct_days"]>=2),
                 key=lambda x:(-x["distinct_days"],-x["total_root_events"],x["family"]))
    naturalcsv=[{k:v for k,v in x.items() if k!="key"} for x in multi[:500]]
    summary=dict(
      days=len(dates),draws=len(rows),start=dates[0],end=dates[-1],
      catalogue_count=len(catalogue),catalogue_seen=sum(f["distinct_days"]>0 for f in catalogue),
      catalogue_seen_2days=sum(f["distinct_days"]>=2 for f in catalogue),
      catalogue_seen_5days=sum(f["distinct_days"]>=5 for f in catalogue),
      natural_unique_roots=len(root),natural_root_events=root_events,
      natural_roots_2days=len(multi),natural_roots_3days=sum(x["distinct_days"]>=3 for x in naturals),
      intersection_parent_pairs_gt10_skipped=skipped_gt10,
      all_numbers_have_79_partners=all(x["distinct_other_number_partners"]==79 for x in bynumber),
      numbers_have_unique_20roster_each_appearance=sum(
        x["draws_with_number"]==x["distinct_20_number_rosters"] for x in bynumber),
      anchor_catalog_min=min(x["registered_families_ever_fully_seen"] for x in bynumber),
      anchor_catalog_max=max(x["registered_families_ever_fully_seen"] for x in bynumber),
      anchor_catalog_mean=round(statistics.mean(x["registered_families_ever_fully_seen"]
                                                for x in bynumber),3),
      anchor_root_min=min(x["natural_roots_5to10_distinct"] for x in bynumber),
      anchor_root_max=max(x["natural_roots_5to10_distinct"] for x in bynumber),
      anchor_root_mean=round(statistics.mean(x["natural_roots_5to10_distinct"]
                                             for x in bynumber),3),
      anchor_root_multiday_min=min(x["natural_roots_reappeared_2plus_days"] for x in bynumber),
      anchor_root_multiday_max=max(x["natural_roots_reappeared_2plus_days"] for x in bynumber))
    return summary,bynumber,bypartner,catalogcsv,naturalcsv

def write_csv(z,name,records):
    if not records:return
    with z.open(name,"w") as raw:
        t=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(t,fieldnames=list(records[0].keys()))
        w.writeheader();w.writerows(records);t.flush();t.detach()

def run(src,famsrc,out):
    days,rows,fam,issues,malformed=data(src,famsrc)
    summary,bynumber,bypartner,catalogcsv,naturalcsv=crunch(days,rows,fam)
    examples=[bynumber[n-1] for n in (1,5,23,42,50,79,80)]
    report=[
      "V97 — BIR SAYI GUNLER BOYUNCA HEP AYNI AILEYLE MI CIKIYOR?",
      f"Observed {summary['draws']} real draws / {summary['days']} full days.",
      "20-number roster: all 20 drawn numbers together, order irrelevant.",
      "V10 catalogue: 1131 REGISTERED 5..10-number groups, each counts",
      "only if the entire family falls into the SAME observed draw.",
      "Natural root: exact 5..10-number intersection of two draws at",
      "most 12 previous consecutive IDs apart; dedup same-target parents.",
      "IMPORTANT: natural roots are defined AFTER seeing current result.",
      "Intersections >10 deliberately NOT shortened to 10 members.",
      "",
      f"All 80 ball identities have all 79 possible partners at least once: {summary['all_numbers_have_79_partners']}.",
      f"All appearances had different complete 20-number rosters for {summary['numbers_have_unique_20roster_each_appearance']}/80 numbers.",
      f"V10 registered families {summary['catalogue_count']}, ever fully seen {summary['catalogue_seen']},",
      f"2+ distinct days {summary['catalogue_seen_2days']}, 5+ days {summary['catalogue_seen_5days']}.",
      f"Number-by-number V10 fully observed families min/avg/max: {summary['anchor_catalog_min']}/{summary['anchor_catalog_mean']}/{summary['anchor_catalog_max']}.",
      f"Natural unique exact roots 5..10: {summary['natural_unique_roots']};",
      f"root events {summary['natural_root_events']}, roots seen 2+ days {summary['natural_roots_2days']},",
      f"natural unique roots per ball min/avg/max: {summary['anchor_root_min']}/{summary['anchor_root_mean']}/{summary['anchor_root_max']}.",
      f"Natural roots reappeared 2+ days per ball min/max: {summary['anchor_root_multiday_min']}/{summary['anchor_root_multiday_max']}.",
      "",
      "EXAMPLES (number, draw appearances, distinct 20 rosters, distinct V10 fully-seen,",
      "natural 5..10 distinct, natural 2+ day, top partner, partner co-draw count):"]
    for x in examples:
        report.append(f" {x['number']:2d}: {x['draws_with_number']} / {x['distinct_20_number_rosters']}"
           f" / {x['registered_families_ever_fully_seen']}"
           f" / {x['natural_roots_5to10_distinct']}"
           f" / {x['natural_roots_reappeared_2plus_days']}"
           f" / {x['top_partner']} / {x['top_partner_together']}")
    report+=["",
      "Interpretation: every draw contains 19 companions for the anchor.",
      "Any number belongs to MANY overlapping candidate families;",
      "counting overlapping 5..10 subsets as independent would inflate totals.",
      "V10 catalogue was selected retrospectively, not independently pre-registered.",
      "Exact 20-roster and natural-root turnover does not prove RNG clockwork;",
      "independent 20/80 random draws naturally change each anchor's companions.",
      "A family being seen twice does NOT make its next-draw return more likely.",
      "CSV provides full 1..80 per-number results, catalog identities, and",
      "the most repeatedly detected exact natural roots."]
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(p,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_SONUCLAR_VE_YONTEM.txt","\n".join(report)+"\n")
        write_csv(z,"01_80_SAYI_KAC_FARKLI_AILE.csv",bynumber)
        write_csv(z,"02_HER_SAYININ_ILK10_ESLIKCI.csv",bypartner)
        write_csv(z,"03_1131_KAYITLI_AILE_KAC_GUN_TAM_CIKTI.csv",catalogcsv)
        write_csv(z,"04_BASKA_GUNLERDE_YINELENEN_ILK500_DOGAL_AILE.csv",naturalcsv)
        z.writestr("05_DENETIM.json",json.dumps(dict(version=VERSION,summary=summary,
                    source_issues=issues[:30],source_invalid_lines=malformed[:30]),
                    indent=2,ensure_ascii=False))
    print("\n".join(report),flush=True)
    print("V97 DONE",p,p.stat().st_size,flush=True)

def selftest():
    assert bitmask((1,3,80)).bit_count()==3
    assert bits(bitmask((2,11)))==[2,11]
    assert (bitmask((2,3,4))&bitmask((1,2,3,4,5)))==bitmask((2,3,4))
    print("V97 SELFTEST OK",flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--source",default="veri.txt")
    a.add_argument("--catalogue",default="v10_aileler.csv")
    a.add_argument("--out",default="v97_output/V97_HER_SAYI_KAC_FARKLI_AILE.zip")
    a.add_argument("--selftest",action="store_true")
    v=a.parse_args()
    selftest() if v.selftest else run(v.source,v.catalogue,v.out)
