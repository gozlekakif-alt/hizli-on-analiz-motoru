#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read ANY actual V126 draw/ring/number movement from lossless archive.

Examples:
python v126_detay_oku.py --zip V126_224_HALKA_80_SAYI_HER_ADIM_FULL_LOSSLESS.zip --draw-id 62014 --number 37
python v126_detay_oku.py --zip ... --draw-id 62014 --ring 224
python v126_detay_oku.py --zip ... --draw-id 62014 --number 37 --ring 224
No target history assumed except the ZIP itself. No current data invented.
"""
import argparse,csv,io,json,zipfile
import numpy as np
NAMES=("SOGUK","SERIN","NOTR","ILIK","SICAK")

def read_cube(z,filename):
    with np.load(io.BytesIO(z.read(filename)),allow_pickle=False) as a:
        return {k:a[k].copy() for k in a.files}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True,help="downloaded full V126 GitHub artifact .zip")
    p.add_argument("--draw-id",type=int,default=None,
                   help="actual draw number; default last in source")
    p.add_argument("--number",type=int,default=None,
                   help="one number 1..80; otherwise all 80")
    p.add_argument("--ring",type=int,default=None,
                   help="one circle 1..224; otherwise all 224")
    p.add_argument("--out",default=None,
                   help="output CSV filename; by default prints first 12 rows")
    args=p.parse_args()
    if args.number is not None and not 1<=args.number<=80:p.error("number must be 1..80")
    if args.ring is not None and not 1<=args.ring<=224:p.error("ring must be 1..224")
    with zipfile.ZipFile(args.zip) as z:
        manifest=json.loads(z.read("07_METOD_VE_GUN_BLOK_LISTESI.json"))
        lookup={}
        for b in manifest["days_npz"]:
            path=b["file"]
            info=read_cube(z,path)
            # Only one block at a time during lookup; avoid reading every
            # block repeatedly for long histories: use ID interval metadata.
            if args.draw_id is None:
                target_id=int(manifest["final_observed_draw_id"])
            else:
                target_id=args.draw_id
            if b["first_draw_id"]<=target_id<=b["last_draw_id"]:
                ids=list(map(int,info["draw_id"]))
                if target_id in ids:
                    pos=ids.index(target_id)
                    lookup=dict(path=path,cube=info,pos=pos,
                                target_id=target_id)
                    break
        if not lookup:
            raise SystemExit(f"Draw id {target_id} not saved in this V126 archive")
        path=lookup["path"]
        state=lookup["cube"]
        pos=lookup["pos"]
        old=None
        if pos>0:
            old=dict(count_state=state["count_state"][pos-1],
                     rank_state=state["rank_state"][pos-1],
                     pool_state=state["pool_state"][pos-1])
        else:
            blocks=manifest["days_npz"]
            id_index=next(i for i,b in enumerate(blocks) if b["file"]==path)
            if id_index==0:
                base=read_cube(z,"00_INITIAL_CONDITION_BEFORE_FIRST_DRAW.npz")
                old=dict(count_state=base["count_state"],
                         rank_state=base["rank_state"],
                         pool_state=base["pool_state"])
            else:
                before=read_cube(z,blocks[id_index-1]["file"])
                old={k:before[k][-1] for k in
                      ("count_state","rank_state","pool_state")}
        new_draw=np.unpackbits(state["incoming_draw_packed"][pos],count=80)
        leaving=np.unpackbits(state["leaving_ring_packed"][pos],axis=1,count=80)
        rids=range(224) if args.ring is None else [args.ring-1]
        bids=range(80) if args.number is None else [args.number-1]
        records=[]
        for r in rids:
            for b in bids:
                oc=int(old["count_state"][r,b])
                nc=int(state["count_state"][pos,r,b])
                orank=int(old["rank_state"][r,b])
                nrank=int(state["rank_state"][pos,r,b])
                op=int(old["pool_state"][r,b])
                npool=int(state["pool_state"][pos,r,b])
                rec=dict(
                   actual_draw_id=target_id,
                   circle=r+1,reference_last_draws=(r+1)*12,
                   number=b+1,
                   new_drew_1_0=int(new_draw[b]),
                   old_exiting_drew_1_0=int(leaving[r,b]),
                   count_before=oc,count_after=nc,count_delta=nc-oc,
                   rank_before_cold0=orank,rank_after_cold0=nrank,
                   rank_delta=nrank-orank,
                   pool_before=NAMES[op],pool_after=NAMES[npool],
                   pool_delta=npool-op)
                assert rec["count_delta"]==rec["new_drew_1_0"]-rec["old_exiting_drew_1_0"]
                records.append(rec)
    if args.out:
        with open(args.out,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]))
            w.writeheader();w.writerows(records)
        print(f"V126 exported {len(records)} fully audited number-ring transitions "
              f"for draw {target_id}: {args.out}")
    else:
        print(f"V126 draw {target_id}, showing {min(12,len(records))} of "
              f"{len(records)} detailed ring-number movements:")
        for rec in records[:12]:
            print(" ".join(f"{key}={val}" for key,val in rec.items()))
        if len(records)>12:print("To save every record, add --out desired.csv")

if __name__=="__main__":main()
