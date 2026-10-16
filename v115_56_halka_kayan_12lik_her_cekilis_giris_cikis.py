#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V115B: exactly 56 RELATIVE rolling rings x12 observed draws, NOT
57 absolute physical rings. Shift by ONE DRAW after each real draw.

Newest draw enters ring56; first draw of ring56 shifts to last slot of
ring55, and so forth; first draw of ring1 expires from the 672-draw
FIFO but is preserved in the outgoing ledger.

Recomputing every ring's 12-appearance count and its pre-existing
72-draw 16/16/16/16/16 temperature using ONLY past observations.
The user-requested moving groups are distinct from calendar-fixed
V100C/V104 absolute ring IDs (which stay intact in existing code).
"""
from __future__ import annotations
import argparse,csv,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature

POOLS=('SOGUK','SERIN','NOTR','ILIK','SICAK')
MEM=672
RINGS=56
N=12

def write_rows(z,name,rows):
    if not rows:return
    with z.open(name,"w",force_zip64=True) as f:
        s=io.TextIOWrapper(f,encoding='utf-8-sig',newline='')
        w=csv.DictWriter(s,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        s.flush();s.detach()

def run(src,dest):
    days,rows,X,issues,bad=load(src)
    total=len(rows)
    assert X.shape==(total,80) and (X.sum(axis=1)==20).all()
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                     np.cumsum(X,dtype=np.int32,axis=0)))
    # t means number of observed draws: known X[0:t] only
    t=MEM
    C=X[:t].reshape(RINGS,N,80).sum(axis=1).astype(np.int16)
    assert C.shape==(RINGS,80) and (C.sum(axis=1)==240).all()
    progress=[]
    ten_steps=[]
    for incoming_idx in range(MEM,total):
        # Pre-draw data ends at t=incoming_idx; new draw only arrives
        # AFTER any forecast for draw incoming_idx+1 was frozen.
        assert t==incoming_idx
        removed=X[t-MEM:t:N]
        added=np.concatenate((X[t-MEM+N:t:N],X[t:t+1]),axis=0)
        assert removed.shape==added.shape==(RINGS,80)
        oldfirst=X[t-MEM]
        incoming=X[t]
        newC=C-removed+added
        assert (newC>=0).all() and (newC.sum(axis=1)==240).all()
        before=temperature(prefix[t]-prefix[t-72])
        after=temperature(prefix[t+1]-prefix[t+1-72])
        old_pool_count=[int((before==p).sum()) for p in range(5)]
        new_pool_count=[int((after==p).sum()) for p in range(5)]
        assert old_pool_count==new_pool_count==[16]*5
        changed=(newC!=C)
        progress.append(dict(
            newly_added_draw_id=rows[t]['id'],
            previously_last_known_id=rows[t-1]['id'],
            expired_oldest_draw_id=rows[t-MEM]['id'],
            added_20_nums='-'.join(str(i+1) for i in np.flatnonzero(incoming)),
            removed_20_nums='-'.join(str(i+1) for i in np.flatnonzero(oldfirst)),
            ring_count=RINGS,draws_per_ring=N,rolling_draws=MEM,
            rings_whose_80_counts_change=int(changed.any(axis=1).sum()),
            up_pool72_count=int((after>before).sum()),
            down_pool72_count=int((after<before).sum()),
            unchanged_pool72_count=int((after==before).sum()),
            ring56_total_ones=240,
            per_ring_up_frequency_56='|'.join(map(str,((newC>C).sum(axis=1)).tolist())),
            per_ring_down_frequency_56='|'.join(map(str,((newC<C).sum(axis=1)).tolist())),
            )))
        if incoming_idx>=total-10:
            for ring in range(RINGS):
                old20=removed[ring]
                new20=added[ring]
                ten_steps.append(dict(draw_id=rows[t]['id'],
                    expired_global_id=rows[t-MEM]['id'],
                    relative_ring=ring+1,
                    outgoing_20_from_this_ring='-'.join(map(str,np.flatnonzero(old20)+1)),
                    incoming_20_to_this_ring='-'.join(map(str,np.flatnonzero(new20)+1)),
                    numbers_increasing_local12_count=int((newC[ring]>C[ring]).sum()),
                    numbers_decreasing_local12_count=int((newC[ring]<C[ring]).sum()),
                    counts_unchanged=int((newC[ring]==C[ring]).sum()),
                    original12_count=240,new12_count=240))
        t+=1
        C=newC
        if t%3000==0:
            print('V115B processed known draw count',t,flush=True)
    # Validate newest snapshot 56x12 (not 55+2 partial).
    blocks=X[total-672:total].reshape(RINGS,12,80)
    assert np.array_equal(blocks.sum(axis=1),C)
    assert (C.sum(axis=1)==240).all() and len(progress)==total-672
    latest_pool=temperature(prefix[total]-prefix[total-72])
    rings=[];ring56=[]
    for k in range(RINGS):
        last_draw_idx=total-672+(k+1)*N
        rank=temperature(prefix[last_draw_idx]-
                         prefix[max(0,last_draw_idx-72)])
        if last_draw_idx>=72:
            assert all((rank==v).sum()==16 for v in range(5))
        for b in range(80):
            bits=''.join(str(int(v)) for v in blocks[k,:,b])
            record=dict(relative_ring=k+1,number=b+1,
                start_draw_id=rows[total-672+k*N]['id'],
                end_draw_id=rows[last_draw_idx-1]['id'],
                twelve_bits=bits,
                appearances=int(C[k,b]),
                temperature_at_end_from_72=POOLS[int(rank[b])])
            rings.append(record)
            if k==RINGS-1:
                ring56.append(dict(number=b+1,appearances=int(C[k,b]),
                    bits_12=bits,current_pool72=POOLS[int(latest_pool[b])]))
    assert len(rings)==4480 and len(ring56)==80
    assert sum(x['appearances'] for x in ring56)==240
    k=RINGS-1
    summary=[
       "V115B: 56 groups each with exactly 12 draws at ALL moving steps",
       f"Last observed draw: #{rows[-1]['id']} {rows[-1]['day']}",
       f"Observed draw count: {total}; real one-in-one-out shifts: {len(progress)}",
       f"Newest moving ring56 (12 draws): #{rings[55*80]['start_draw_id']} - #{rings[-1]['end_draw_id']}",
       "Fixed absolute ring boundaries of V100C/V104 are a separate model;",
       "this uses 56 RELATIVE rolling rings and never creates ring57.",
       "Moving ring56, 1..80 count:",
       *[' '.join(f'{r["number"]:02d}:{r["appearances"]}' for r in ring56[i:i+10])
           for i in range(0,80,10)],
       "Ring56 total: 240; each of all 56 rings also totals 240.",
       "Pre-target pool uses last 72 observed draws; post-target pool never read before incoming draw.",
       "An expired 20-number draw is permanently retained in the update ledger.",
       "The whole data history was previously researched; descriptive results are not proof of predictive advantage."
    ]
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V115B_KISA_SONUC.txt","\n".join(summary)+"\n")
        write_rows(z,"01_SON_56_HAREKETLI_HALKA_80_SAYI_12BIT_4480.csv",rings)
        write_rows(z,"02_SON_HAREKETLI_56_HALKA_80_SAYI_SAYIM.csv",ring56)
        write_rows(z,"03_TUM_GECMIS_CEKILISLER_56_HALKA_GIR_CIK.csv",progress)
        write_rows(z,"04_SON10_CEKILISIN_56_HALKA_GIR_CIK_MIKRO.csv",ten_steps)
        z.writestr("05_DOGRULAMA.json",json.dumps(dict(
            version="V115B.1",total_draws=total,
            shifts=len(progress),relative_rolling_rings=56,
            each_ring_size=12,memory=672,
            source_latest_draw_id=rows[-1]['id'],
            latest_ring_total=int(sum(x['appearances'] for x in ring56)),
            oldest_draws_preserved_in_log=True,
            no_57th_ring=True,
            same_source_as_v114=True,independent_predictive_edge=False),
            ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V115B COMPLETED",dest,dest.stat().st_size,flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v115_output/V115B_56_HAREKETLI_KAYAN_672_TAM_CEKILIS.zip")
    a=p.parse_args()
    run(a.source,a.out)
