# -*- coding: utf-8 -*-
"""V44: leakage, exact 20/80, quota totals, maxT, fixed chronology, ZIP."""
import csv,io,json,math,zipfile
from collections import defaultdict
from v44_ana_beyin_uzman_elemesi import (
 Brain,study,select_experts,maxT_p,random20,
 CANDIDATES,MASTER,OLD,RNG,CONSENSUS,METHODS,quota)

def sample(day,how_many,change_at=None):
    out=[]
    for p in range(1,how_many+1):
        # Twenty different balls; no real RNG claims from synthetic.
        chosen={((n+11*p)%80)+1 for n in range(20)}
        if p==change_at:chosen=set(range(61,81))
        out.append(dict(day=day,pos=p,
                        no=int(day.replace("-",""))*1000+p,nums=chosen))
    return out

def read_csv(data,path):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return list(csv.DictReader(io.StringIO(
               z.read(path).decode("utf-8-sig")),delimiter=";"))

def main():
    assert len(CANDIDATES)==19 and len(METHODS)==22
    assert len(random20("2026-10-14",7))==20
    assert sum(quota((13,17,22,16,12)))==20
    # Change target t without changing observations <t: t's frozen
    # candidate identities and five pool quotas must remain unchanged.
    p=Brain()
    for d in sample("2026-10-01",80):
        snap=p.freeze(d["day"],d["pos"])
        p.observe(d["day"],d["pos"],d["no"],frozenset(d["nums"]),snap)
    before=p.freeze("2026-10-01",81)
    before2=p.freeze("2026-10-01",81)
    assert before["picks"]==before2["picks"]
    assert before["quotas"]==before2["quotas"]
    assert all(len(x)==20 for x in before["picks"].values())
    assert sum(before["sizes"])==80
    assert all(sum(v)==20 for v in before["quotas"].values())

    # Make 8 partial dates, no artificial missing draw inserted.
    days=[f"2026-10-{i:02d}" for i in range(1,9)]
    draws=sum((sample(day,85) for day in days),[])
    future=sum((sample(day,85,change_at=85 if i==8 else None)
                for i,day in enumerate(days,1)),[])
    a,meta,summary,qsum,gates=study(draws,include_partial=True)
    b,other,_,_,_=study(future,include_partial=True)
    assert meta["real_draws"]==680
    assert len(gates)==19
    assert meta["experts"]==19
    assert not meta["accepted"] # only 2 validation days, cannot pass gate.
    assert any(x["donem"]=="KOR_TEST" and x["motor"]==MASTER for x in summary)
    rows=read_csv(a,"01_HER_CEKILISTE_DONDURULMUS_20_LISTELER.csv")
    second=read_csv(b,"01_HER_CEKILISTE_DONDURULMUS_20_LISTELER.csv")
    assert len(rows)==680*22
    t=[x for x in rows if x["gun"]=="2026-10-08" and x["sira"]=="85"]
    u=[x for x in second if x["gun"]=="2026-10-08" and x["sira"]=="85"]
    assert [(r["motor"],r["secilen20"]) for r in t]==[
        (r["motor"],r["secilen20"]) for r in u],"future target leakage detected"
    for row in rows:
        truth={int(n) for n in row["gercek20"].split(",")}
        selected={int(n) for n in row["secilen20"].split(",")}
        assert len(truth)==len(selected)==20
        assert row["onceden_donduruldu"]=="EVET"
        assert len(truth&selected)==int(row["isabet"])
    # master is an explicit same-seed RNG control if nothing passes.
    for r in rows:
        if r["motor"]==MASTER:
            assert r["secilen20"]==next(x["secilen20"] for x in rows
                if x["gun"]==r["gun"] and x["sira"]==r["sira"] and x["motor"]==RNG)
            assert r["karar"]!="ONAYLI_VALIDASYON"
    quota_rows=read_csv(a,"02_HER_CEKILISTE_BES_HAVUZ_KOTA.csv")
    quota_test=read_csv(b,"02_HER_CEKILISTE_BES_HAVUZ_KOTA.csv")
    assert len(quota_rows)==(680-72)*3
    aa=[r for r in quota_rows if r["gun"]=="2026-10-08" and r["sira"]=="85"]
    bb=[r for r in quota_test if r["gun"]=="2026-10-08" and r["sira"]=="85"]
    for x,y in zip(aa,bb):
        # pre-target predictions must NOT change with t's new actual
        assert [x["tahmin_"+n] for n in ("soguk","serin","notr","ilik","sicak")]==[
                y["tahmin_"+n] for n in ("soguk","serin","notr","ilik","sicak")]
    for r in quota_rows:
        cats=("soguk","serin","notr","ilik","sicak")
        s=[int(r["aday_"+x]) for x in cats]
        p=[int(r["tahmin_"+x]) for x in cats]
        a=[int(r["gercek_"+x]) for x in cats]
        assert sum(s)==80 and sum(p)==sum(a)==20
        assert all(0<=pi<=si for pi,si in zip(p,s))
        assert 0<=float(r["rng_tum5_artieksi1_beklenen"])<=1
    # A synthetic strong predeclared expert can qualify; other weak ones
    # should not inherit its significance despite their shared dates.
    records=[]
    for d in range(1,19):
        for p in range(1,13):
            for i,m in enumerate(CANDIDATES):
                hits=(9 if d%2 else 8) if i==0 else (5 if (d+p+i)%2 else 4)
                records.append({"gun":f"2026-09-{d:02d}","7_12":"EVET" if p>=7 else "HAYIR",
                     "motor":m,"isabet":hits,
                     "secilen20":",".join(map(str,range(1,21))) if i==0
                                  else ",".join(map(str,range(21,41)))})
    _,ok,_=select_experts(records)
    assert CANDIDATES[0] in ok
    assert not (set(ok)-{CANDIDATES[0]})
    with zipfile.ZipFile(io.BytesIO(a)) as z:
        assert z.testzip() is None and len(z.namelist())==9
    print("V44 SELFTEST PASS: frozen 19 expert identities, 5 pool quotas, strict t, 18/18/36 selection gate, synthetic strong expert, 22 lists/draw, ZIP",flush=True)

if __name__=="__main__":
    main()
