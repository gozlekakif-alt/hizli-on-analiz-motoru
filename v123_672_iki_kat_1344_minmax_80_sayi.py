#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V123: compare consecutive 672-draw windows against their 1344 union.
Count actual appearances of all 80 numbers, not a hypothetical 2x.
Last draw and all prior rows originate in repository veri.txt.
"""
import argparse, csv, io, json, zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

def one(title, values):
    x=np.asarray(values,dtype=int)
    ordered=list(range(80))
    ordered.sort(key=lambda i:(-int(x[i]),i))
    cold=sorted(range(80),key=lambda i:(int(x[i]),i))
    high=int(x.max())
    low=int(x.min())
    hotnums=[int(i+1) for i in np.flatnonzero(x==high)]
    coldnums=[int(i+1) for i in np.flatnonzero(x==low)]
    return {"period":title,"draws":int(x.sum()//20),
      "sum_all_80":int(x.sum()),"expect_each":int(x.sum()//80),
      "max":high,"max_numbers":hotnums,"min":low,"min_numbers":coldnums,
      "difference":high-low,"top16":sorted([i+1 for i in ordered[:16]]),
      "bottom16":sorted([i+1 for i in cold[:16]])}

def main(source,out):
    days,rows,X,issues,bad=load(source)
    assert len(X)==len(rows) and len(rows)>=1344
    assert np.all(X.sum(axis=1)==20)
    windows=[
       ("OLDER_672",X[-1344:-672]),
       ("LATEST_672",X[-672:]),
       ("COMBINED_1344",X[-1344:])]
    reports=[one(k,w.sum(axis=0)) for k,w in windows]
    d={r["period"]:r for r in reports}
    assert d["LATEST_672"]["expect_each"]==168
    assert d["COMBINED_1344"]["expect_each"]==336
    assert sum(int(x.sum()) for k,x in windows[:2])==int(windows[2][1].sum())
    b1,b2=windows[0][1].sum(axis=0),windows[1][1].sum(axis=0)
    b3=windows[2][1].sum(axis=0)
    assert (b1+b2==b3).all()
    print("V123 VERIFIED SOURCE total draws:",len(rows))
    print("V123 LAST SOURCE:",rows[-1]["id"],rows[-1]["day"],rows[-1]["time"])
    print("V123 oldest among combined:",rows[-1344]["id"],rows[-1344]["day"],rows[-1344]["time"])
    print("V123 split earliest second half:",rows[-672]["id"],rows[-672]["day"],rows[-672]["time"])
    for r in reports:
        print("V123",r["period"],"draws",r["draws"],"sum",r["sum_all_80"],
            "expected",r["expect_each"],"max",r["max"],
            "maxnums",",".join(map(str,r["max_numbers"])),"min",r["min"],
            "minnums",",".join(map(str,r["min_numbers"])),"GAP",r["difference"])
    latest=d["LATEST_672"];combined=d["COMBINED_1344"]
    print("V123 GAP change by doubling the reference:",combined["difference"]-latest["difference"])
    print("V123 gap ratio:",round(combined["difference"]/latest["difference"],5))
    print("V123 confirmation old max64=191 and min37=146?",
          int(b2[63])==191,int(b2[36])==146,
          "actual64",int(b2[63]),"actual37",int(b2[36]))
    order=sorted(range(80),key=lambda i:(-int(b3[i]),i))
    csvrows=[]
    for rank,i in enumerate(order,1):
        csvrows.append({"rank_1344":rank,"number":i+1,
                        "older672":int(b1[i]),"latest672":int(b2[i]),
                        "combined1344":int(b3[i]),
                        "change_new_minus_old":int(b2[i]-b1[i]),
                        "vs_336_combined":int(b3[i]-336)})
    summary={
       "source":"veri.txt","rows_total":len(rows),
       "latest_draw_id":rows[-1]["id"],
       "latest_draw_date":rows[-1]["day"],
       "oldest_1344_id":rows[-1344]["id"],
       "oldest_latest672_id":rows[-672]["id"],
       "windows":reports,"per_number":csvrows,
       "same_numbers_top16_between_672_and_1344":len(set(latest["top16"])&set(combined["top16"])),
       "same_numbers_bottom16_between_672_and_1344":len(set(latest["bottom16"])&set(combined["bottom16"])),
       "no_future_pred_claim":True}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("01_KARSILASTIRMA_672x2_1344.json",json.dumps(summary,indent=2,ensure_ascii=False))
        f=io.StringIO()
        writer=csv.DictWriter(f,fieldnames=csvrows[0].keys())
        writer.writeheader();writer.writerows(csvrows)
        z.writestr("02_80_SAYI_672_672_1344.csv",f.getvalue())
    print("V123 COMPLETE",out,"bytes",out.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v123_output/V123_672_672_1344_KARSILASTIRMA.zip")
    a=p.parse_args()
    main(a.source,a.out)
