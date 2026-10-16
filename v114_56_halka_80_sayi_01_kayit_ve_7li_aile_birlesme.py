#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V114 | Real 0/1 for every ball in 56 fixed sealed physical rings.

Latest known data can end mid-ring. Never call partial ring "56th full
ring". Report BOTH last 56 closed rings and physical 672 FIFO window
containing 55 whole plus TWO partial rings if current offset !=0.
Analyze pretarget H22 7-number family reunions across previous 56
temperature pool seal states; validate matched H23 draw outcomes.

All outcomes are logged AFTER ring/family definition. No edge claim.
"""
import argparse,csv,io,zipfile,json,math,collections
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature,groups
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import expected_hours
from v104_72gun_basindan_672_56_halka_fifo_yon import stable_paths

POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
VERSION="V114.1"
def csvout(z,name,data):
    if not data:return
    with z.open(name,'w',force_zip64=True) as fp:
        f=io.TextIOWrapper(fp,encoding='utf-8-sig',newline='')
        w=csv.DictWriter(f,fieldnames=list(data[0]))
        w.writeheader();w.writerows(data)
        f.flush();f.detach()

def rangebits(X,first,end):
    return [''.join(str(int(x)) for x in X[first:end,b]) for b in range(80)]
def family_from_h22(t,X):
    # Predetermined rule from V113: latest first exact-seven pair.
    for i in range(11,0,-1):
        for j in range(i-1,-1,-1):
            common=np.flatnonzero((X[t-12+i]>0)&(X[t-12+j]>0))
            if len(common)==7:
                return common,(j+1,i+1)
    return None,None

def compute(source,output):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert len(X)==n and np.all(X.sum(axis=1)==20)
    p=np.vstack((np.zeros((1,80),np.int32),
                  np.cumsum(X,axis=0,dtype=np.int32)))
    nr=n//12
    seals=np.empty((nr,80),dtype=np.int8)
    for rid in range(nr):
        end=(rid+1)*12
        seals[rid]=temperature(p[end]-p[max(0,end-72)])
    assert nr>=56 and n>=672
    maxrid=nr-1
    minrid=maxrid-55
    lastseal_end=(maxrid+1)*12
    newestpartial=n-lastseal_end
    lastseal_start=lastseal_end-12
    latest=rangebits(X,lastseal_start,lastseal_end)
    latest12=rangebits(X,n-12,n)
    latest_count=X[lastseal_start:lastseal_end].sum(axis=0).astype(int)
    moving_count=X[n-12:n].sum(axis=0).astype(int)
    assert int(latest_count.sum())==240 and int(moving_count.sum())==240
    assert all(len(v)==12 for v in latest)
    live=groups(p,n)
    assert len(live) in (56,57) and sum(x['size'] for x in live)==672
    assert sum(x['sealed'] for x in live)==(56 if newestpartial==0 else 55)
    # Reconstruct 0/1 for latest 56 actually CLOSED physical rings.
    whole=[]
    for rid in range(minrid,maxrid+1):
        left=rid*12;right=left+12
        b12=rangebits(X,left,right)
        pool=seals[rid]
        for b,bits in enumerate(b12):
            whole.append(dict(
                chronological_closed_ring=rid-minrid+1,
                absolute_ring_id=rid,
                ring_first_id=rows[left]['id'],
                ring_last_id=rows[right-1]['id'],
                number=b+1,
                bits_12_draws=bits,
                appearances_in_ring=int(bits.count('1')),
                pool_at_ring_end=POOL[int(pool[b])],
                one_positions_1_to12='-'.join(str(j+1) for j,v in enumerate(bits) if v=="1")))
    last80=[]
    for b,bits in enumerate(latest):
        last80.append(dict(number=b+1,occurrences=int(latest_count[b]),
            zero_one_bits=bits,positions_1_to_12=
            '-'.join(str(i+1) for i,v in enumerate(bits) if v=="1"),
            current_sealed_pool=POOL[int(seals[maxrid,b])],
            last_12_moving_occurrences=int(moving_count[b]),
            last_12_moving_bits=latest12[b]))
    # 672 true one-draw FIFO, maintain partial rings and their identities.
    memory_rows=[]
    serial=[]
    for b in range(80):
        nums=[int(X[k,b]) for k in range(n-672,n)]
        assert len(nums)==672
        across=[]
        for ring in live:
            bits=''.join(str(int(X[k,b])) for k in range(ring['first'],ring['end']))
            across.append(bits)
            memory_rows.append(dict(
                number=b+1,absolute_ring_id=int(ring['ring']),
                physical_ring_order_in_FIFO=len(across),
                first_id=rows[ring['first']]['id'],
                last_id=rows[ring['end']-1]['id'],
                size=int(ring['size']),sealed=int(ring['sealed']),
                bits_of_this_physical_ring=bits,
                appearances=int(bits.count('1')),
                is_newest_partial=int(ring['ring']==live[-1]['ring'] and not ring['sealed'])))
        assert ''.join(across)==''.join(map(str,nums))
        serial.append(dict(number=b+1,total_last672=int(sum(nums)),
             fifo_672_bits=''.join(map(str,nums)),
             fifo_bits_physical_rings='|'.join(across),
             segments=len(across),
             counts_per_physical_ring='|'.join(str(x.count('1')) for x in across)))
    # Family reunion study, same pre-hour family definition as V113.
    hours,rejected=expected_hours(rows)
    hrs=[(t,day,h,ids) for t,day,h,ids in hours
         if h==23 and t>=672 and t+12<=n]
    family_summary=[];family_ledger=[];family_member=[];family_stage=[]
    assert len(hrs)>=69-1
    for t,day,h,ids in hrs:
        fam,pair=family_from_h22(t,X)
        if fam is None:
            family_summary.append(dict(day=day,family_found=0))
            continue
        ids0,S,D=stable_paths(t,seals)
        # Seven members' chronological CURRENT ring pool trail.
        states=S[fam,:]
        ringmax=np.array([
            int(max(np.bincount(states[:,r],minlength=5)))
            for r in range(states.shape[1])],dtype=int)
        paircount=np.array([
            int(sum(math.comb(int(v),2) for v in np.bincount(states[:,r],minlength=5)))
            for r in range(states.shape[1])],dtype=int)
        assert len(ringmax) in (55,56)
        # Predefine a reunion without using future target:
        # had a relatively separated state during 6-12 rings ago,
        # has >=4 in a common current pool in latest 6 rings.
        prior=ringmax[-12:-6]
        recent=ringmax[-6:]
        reunion=int((prior<=2).any() and (recent>=4).any())
        reunion3=int((prior<=2).any() and (recent>=3).any())
        lastmax=int(ringmax[-1])
        total_h23=X[t:t+12,fam].sum(axis=1)
        family_summary.append(dict(day=day,family_found=1,
            selected_family='-'.join(map(str,fam+1)),
            h22_pair=f"{pair[0]}-{pair[1]}",
            pretarget_oldest_sealed_absolute_ring=int(ids0[0]),
            pretarget_latest_sealed_absolute_ring=int(ids0[-1]),
            prior6_min_common_pool=int(prior.min()),
            recent6_max_common_pool=int(recent.max()),
            last_ring_max_common_pool=lastmax,
            prehour_family_reunion4=reunion,
            prehour_family_reunion3=reunion3,
            h23_draws12=12,
            total_family_hits_in_12=int(total_h23.sum()),
            mean_family_hits_per_draw=float(total_h23.mean()),
            times_3plus=int((total_h23>=3).sum()),
            times_4plus=int((total_h23>=4).sum()),
            times_5plus=int((total_h23>=5).sum()),
            times_6plus=int((total_h23>=6).sum()),
            times_7of7=int((total_h23==7).sum())))
        for idx,rid in enumerate(ids0):
            c=np.bincount(states[:,idx],minlength=5)
            family_stage.append(dict(day=day,
                selected_family='-'.join(map(str,fam+1)),
                ring_order=idx+1,complete_rings=len(ids0),
                absolute_ring_id=int(rid),
                pre_hour_members_in_cold=int(c[0]),
                members_cool=int(c[1]),members_neutral=int(c[2]),
                members_warm=int(c[3]),members_hot=int(c[4]),
                max_members_in_one_pool=int(c.max()),
                pairs_sharing_pool=int(paircount[idx]),
                members_pool_path="|".join(POOL[int(v)] for v in states[:,idx])))
        for b in fam:
            b=int(b)
            family_member.append(dict(day=day,number=b+1,
                chosen_family='-'.join(map(str,fam+1)),
                first_sealed_pool=POOL[int(S[b,0])],
                last_sealed_pool=POOL[int(S[b,-1])],
                full_sealed_ring_pool_chain=''.join("CSNIH"[int(x)] for x in S[b]),
                pretarget_older57_pool_moves=int((np.diff(S[b])!=0).sum()),
                target_h23_H1_H12_bits=''.join(str(int(v)) for v in X[t:t+12,b]),
                target12_times=int(X[t:t+12,b].sum())))
        for j in range(12):
            y=X[t+j]
            hits=int(y[fam].sum())
            family_ledger.append(dict(day=day,target_id=rows[t+j]['id'],
                target_hand=j+1,family='-'.join(map(str,fam+1)),
                prehour_reunion4=reunion,prehour_reunion3=reunion3,
                last_sealed_max_common_pool=lastmax,
                hits=hits,
                hit_members='-'.join(map(str,(fam[y[fam]>0]+1))),
                reached4=int(hits>=4),reached5=int(hits>=5),reached6=int(hits>=6),
                reached7=int(hits==7)))
    # Split-first 34 / next 35, report conditional descriptive comparison.
    hrs_day_index={day:i for i,(t,day,h,ids) in enumerate(hrs)}
    good=[v for v in family_summary if v["family_found"]]
    rates=[]
    for a in ("FIRST34","LAST35","ALL69"):
        dat=(good if a=="ALL69" else
            [r for r in good if (hrs_day_index[r["day"]]<34 if a=="FIRST34" else hrs_day_index[r["day"]]>=34)])
        for rmode in ("reunion4","reunion3"):
            for wanted in (0,1):
                g=[r for r in dat if r["prehour_family_"+rmode]==wanted]
                ndraws=sum(int(r["h23_draws12"]) for r in g)
                rates.append(dict(phase=a,condition=rmode,
                    pretarget_reunion_happened=wanted,hours=len(g),
                    next_draws=ndraws,
                    mean_seven_hits=(sum(int(r["total_family_hits_in_12"]) for r in g)/ndraws if ndraws else ""),
                    fiveplus_draws=sum(int(r["times_5plus"]) for r in g),
                    sixplus_draws=sum(int(r["times_6plus"]) for r in g),
                    sevenofseven_draws=sum(int(r["times_7of7"]) for r in g)))
    report=[]
    report.append("V114 | 56 SABIT HALKA / 80 SAYI 0-1 KAYIT / 7LI AILE AYRILMA-BIRLESME")
    report.append(f"LAST VERIFIED DRAW {rows[-1]['id']} {rows[-1]['day']} {rows[-1].get('time','')}; total source draws={n}")
    report.append(f"56th NEWEST SEALED RING: absolute rid={maxrid}, "+
        f"first #{rows[lastseal_start]['id']} to last #{rows[lastseal_end-1]['id']}, 12 draws.")
    report.append(f"Active newest physical ring: {newestpartial} of 12, "+
       (f"#{rows[lastseal_end]['id']}..#{rows[-1]['id']}" if newestpartial else "none"))
    report.append(f"TRUE sliding FIFO at last draw: {len(live)} physical rings, "+
      f"{sum(v['sealed'] for v in live)} SEALED complete, first and last partial sizes "+
      f"{live[0]['size'] if not live[0]['sealed'] else 0}/"+
      f"{live[-1]['size'] if not live[-1]['sealed'] else 0}.")
    report.append("Do NOT mistake most recent 12 moving observations for latest completed physical ring.")
    report.append("")
    report.append("LATEST 56th SEALED RING, ALL 80 numbers: (number: appearances [12 bits])")
    for begin in range(0,80,10):
        report.append(" | ".join(f"{r['number']:02d}:{r['occurrences']} [{r['zero_one_bits']}]"
             for r in last80[begin:begin+10]))
    report.append("")
    report.append("Summation across all 80 numbers in any full ring MUST be 12×20=240.")
    report.append("There is also a CSV ledger for every one of 56 sealed rings, "+
        "and exact 672 rolling 0/1 bits including partial ring positions.")
    report.append("")
    report.append(f"Seven-family historical days={len(hrs)}, found={len(good)}.")
    for r in rates:
        if r["phase"]=="LAST35":
            report.append(f" {r['phase']} {r['condition']}={r['pretarget_reunion_happened']}, "+
                f"nDays={r['hours']}, nDraws={r['next_draws']}, "+
                f"meanHits={r['mean_seven_hits']}, "+
                f"5+={r['fiveplus_draws']}, 6+={r['sixplus_draws']}.")
    report.append("CAUTION: reconstructed family is known from H22 only, all H23 outcomes are"+
      " later. 'Reunion' means 7 members in common TEMPERATURE POOL, not necessarily"+
      " appearing together in a DRAW. Previous 72 days are already explored;"+
      " small subgroups are not proof of predictive advantage.")
    meta=dict(version=VERSION,records=n,last_id=rows[-1]['id'],
       newest_completed_ring_id=int(maxrid),
       newest_completed_ring_first_draw=rows[lastseal_start]['id'],
       newest_completed_ring_last_draw=rows[lastseal_end-1]['id'],
       latest_partial_draws=int(newestpartial),
       actual_rolling_fifo_draws=672,
       rolling_physical_ring_segments=len(live),
       rolling_sealed_rings=sum(int(r["sealed"]) for r in live),
       fixed_last56_closed_total_bits=56*80*12,
       last_56th_ring_all_number_sum=int(latest_count.sum()),
       all_ring_counts_integrity=True,
       new_data_cutoff=rows[-1]["id"],hours23=len(hrs),
       family_hours=len(good),method="strict pre-hour 22nd-hour exact-7",
       family_outcomes_never_used_in_defining_family=True,
       future_prediction_not_proven=True,
       reference="physical rings fixed from initial Aug1 draw, not resegmented"+
                 " after every new draw")
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V114_TURKCE_GERCEK_SONUC_VE_80_SAYI_LISTESI.txt","\n".join(report)+"\n")
        csvout(z,"01_56_HALKA_EN_SON_TAM12_1DEN80E_SAYI_SAYIM.csv",last80)
        csvout(z,"02_56_TAMAMLANMIS_HALKA_80_SAYI_0_1_DIZI_4480_SATIR.csv",whole)
        csvout(z,"03_YURUYEN_SON672_80_SAYI_TAM_0_1_IZ.csv",serial)
        csvout(z,"04_SON672_FIZIKSEL_57_PARCA_GIRIS_CIKIS_SAYILARI.csv",memory_rows)
        csvout(z,"05_H22_ONCEDEN_SECILEN_7LI_AILE_56_HALKADA_BIRLESME.csv",family_stage)
        csvout(z,"06_7LI_AILE_H23_816_CEKILIS_GERCEK_BIRLIKTE_CIKIS.csv",family_ledger)
        csvout(z,"07_GUN_GUN_7LI_AILE_ONCEDEN_BIRLESME_ARDINDAN_H23.csv",family_summary)
        csvout(z,"08_ILK34_SON35_BIRLESME_5_7_DURUM_GRUPLARI.csv",rates)
        csvout(z,"09_AILE_UYELERI_ILK_HALKA_SON_HALKA_HEDEF_0_1.csv",family_member)
        z.writestr("10_HAVUZ_FIZIKSEL_HALKA_DOGRULAMA.json",json.dumps(meta,ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V114 SUCCESS",str(output),output.stat().st_size)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v114_output/V114_56_HALKA_80_SAYI_01_KAYIT_VE_7LI_AILE.zip")
    a=ap.parse_args()
    # cache day-index lookup for chronological validation fold
    days_valid=[d for d in []]
    # Set after load inside compute: phase map local in compute.
    compute(a.source,a.out)
