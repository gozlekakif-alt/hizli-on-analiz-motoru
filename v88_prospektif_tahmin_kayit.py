#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V88 — prospective family signal ledger; immutable forecast BEFORE target.

Locked candidate rule: V87 validation-chosen SWAP_TWO, horizon=3.
This rule LOST to random in V87 holdout. This script measures it rather
than promoting it as profitable. Future evidence should be genuinely new.

On every *veri.txt* push, GitHub Actions:
  1. Scores ONLY forecasts already sealed in v88_prospektif/forecasts/.
  2. If the most recent drawing is >=-2 and <=7 minutes old in Türkiye,
     and target ID+3 is absent, and the newest draw contains a SWAP_TWO
     natural-root event, writes ONE new immutable forecast record.
  3. Commits the forecast to git before the target draw is reported.
  4. Never overwrites a forecast or its evaluation.

It cannot watch the lottery website. It only reacts to manually supplied
veri.txt updates / workflow dispatch. If archive is old or a chosen
signal does not exist, the honest output is NO_PROSPECTIVE_FORECAST.
"""
from __future__ import annotations
import argparse,collections,datetime,hashlib,json,random
from pathlib import Path
from zoneinfo import ZoneInfo
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v86_72gun_ailelerin_cekilis_cekilis_soyagaci import (
    bm,fs,members,event_roots,relation)
from v87_aile_donusum_sonrasi_1_3_6_12_isabet_kontrol import (
    discover_class,ticket,freq10,rand10)

VERSION="V88.1"
RULE="SWAP_TWO"
HORIZON=3
MAX_AGE_MIN=7
TZ=ZoneInfo("Europe/Istanbul")
FORECAST_SUBDIR="forecasts"
SCORE_SUBDIR="scores"
LOCK_FILE="kural_kilidi.json"
SEAL_PREFIX="v88_frozen_prior"
EXPECTED_FAM_CLASS="SWAP_TWO"

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False).encode("utf-8")

def save_new(path,doc):
    if path.exists():
        old=json.loads(path.read_text(encoding="utf-8"))
        if old==doc:return False
        raise RuntimeError("IMMUTABLE_FORECAST_MISMATCH: "+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as f:
        json.dump(doc,f,ensure_ascii=False,sort_keys=True,indent=2)
        f.write("\n")
    return True

def fixed_rule():
    return dict(version=VERSION,
        lock_name="V87_VALIDATION_WINNER",
        class_name=EXPECTED_FAM_CLASS,horizon_draws=HORIZON,
        min_family_k=5,max_family_k=10,
        candidate_definition="same drawing exact intersection with each of previous up to twelve consecutive draws; size 5..10, >10 capped to first ten members",
        history_family_relation="exact parent root discovered in prior twelve draw frames, SWAP_TWO 2 retained missing and 2 new members",
        family_winner_order="largest k, shortest provenance lag, ascending family bitmask",
        coupon_completion="selected family exact members plus descending count last72 ACTUAL observed previous draws including source draw, ties ascending number",
        control_random="v87 deterministic seed 871016 + source draw id + horizon + family signature",
        control_frequency="10 most often seen in previous72 actual draws including source",
        frozen_rule_validation_period="2026-09-13 through 2026-09-27",
        prefreeze_historical_holdout="2026-09-28 through 2026-10-12",
        historical_holdout_score="10-ball mean 2.493157 versus matched random10 2.513685; not predictive success",
        notebook="Do not alter lock or selection on later results. A signal can be absent. Max one 10-ball ticket per source. This does not claim a profit expectation.",
        lock_date="2026-10-16",
        draw_age_ceiling_minutes=MAX_AGE_MIN,
        activated_only_if_new_data_arrives=True)

def extract_rows(source):
    buckets,issues,malformed=parse_txt(source)
    rows=[r for day in sorted(buckets) for r in buckets[day]]
    if not rows:raise ValueError("No parsed draw rows")
    for i in range(1,len(rows)):
        if rows[i]["id"]<=rows[i-1]["id"]:
            raise ValueError("Draw IDs not strictly increasing at "+
                str(rows[i]["id"]))
    return rows,issues,malformed

def source_event_latest(rows):
    """REPLAY full timeline without seeing any future results."""
    masks=[bm(r["nums"]) for r in rows]
    known={}
    prev=collections.deque(maxlen=12)
    selected=None
    for t,row in enumerate(rows):
        if t and row["id"]!=rows[t-1]["id"]+1:
            prev.clear()
        roots,_=event_roots(t,rows,masks)
        choices=[]
        for family,origin in roots.items():
            cls,parent,first,rel=discover_class(family,origin["lag"],prev,known)
            if t==len(rows)-1 and cls==RULE:
                choices.append((family,origin))
        if t==len(rows)-1 and choices:
            f,src=min(choices,key=lambda pair:(
              -pair[0].bit_count(),pair[1]["lag"],pair[0]))
            counts=[0]*81
            for m in masks[max(0,t-71):t+1]:
                for n in members(m):counts[n]+=1
            chosen=ticket(f,counts)
            counter=freq10(counts)
            random_base=rand10(row["id"],HORIZON,fs(f))
            assert len(set(chosen))==10 and set(members(f)).issubset(chosen)
            selected=dict(family=list(members(f)),
                family_signature=fs(f),
                family_size=f.bit_count(),
                event_type=RULE,
                source_parent_draw_no=rows[src["parent_index"]]["id"],
                source_parent_lag=src["lag"],
                coupon10=list(chosen),
                random10=list(random_base),
                frequency_control10=list(counter))
        # Update registry only AFTER observing draw t.
        for m in roots:
            if m not in known:
                known[m]=dict(mask=m,created_at=t,first_draw=row["id"])
        prev.append((t,tuple(roots)))
    return selected

def qualify_age(row,now):
    stamp=datetime.datetime.fromisoformat(row["day"]+"T"+row["time"])
    local=stamp.replace(tzinfo=TZ)
    difference=(now.astimezone(TZ)-local).total_seconds()/60
    return -2<=difference<=MAX_AGE_MIN,round(difference,3)

def score_existing(base,rows,now):
    forecasts=base/FORECAST_SUBDIR
    scores=base/SCORE_SUBDIR
    scores.mkdir(parents=True,exist_ok=True)
    indexed={r["id"]:(i,r) for i,r in enumerate(rows)}
    new_scored=[]
    status=dict(pending=0,scored_new=0,scored_total=0,invalid=0)
    for path in sorted(forecasts.glob("*.json")):
        seal=json.loads(path.read_text(encoding="utf-8"))
        if seal["rule"]!=RULE or seal["horizon"]!=HORIZON:
            raise RuntimeError("Frozen rule mismatch in "+path.name)
        sid=int(seal["source_draw_id"])
        targetid=int(seal["target_draw_id"])
        assert targetid==sid+HORIZON
        output=scores/(path.stem+".json")
        if output.exists():
            status["scored_total"]+=1
            continue
        if targetid not in indexed:
            status["pending"]+=1
            continue
        if sid not in indexed:
            raise RuntimeError("Source draw unexpectedly missing "+str(sid))
        si,srow=indexed[sid]
        ti,target=indexed[targetid]
        contiguous=(ti-si==HORIZON and all(
          rows[j]["id"]==sid+(j-si) for j in range(si,ti+1)))
        # Registration must occur earlier than official scheduled draw time.
        targetlocal=datetime.datetime.fromisoformat(
          target["day"]+"T"+target["time"]).replace(tzinfo=TZ)
        sealed=datetime.datetime.fromisoformat(seal["sealed_at_utc"])
        earlier=sealed<targetlocal
        actual=set(target["nums"])
        coupon=seal["coupon10"]
        rng=seal["random10"]
        freq=seal["frequency_control10"]
        family=seal["family"]
        valid=(contiguous and earlier and len(set(coupon))==10
               and len(set(rng))==10 and len(set(freq))==10
               and all(1<=n<=80 for n in coupon+rng+freq+family))
        score=dict(source_draw_id=sid,target_draw_id=targetid,
          prediction_sealed_at_utc=seal["sealed_at_utc"],
          evaluated_at_utc=now.isoformat(),
          status="SCORED" if valid else "INVALID_FORECAST",
          invalid_reason=("" if valid else
              "nonconsecutive horizon or seal not before target time"),
          target_day=target["day"],target_clock=target["time"],
          actual_target20=list(target["nums"]),
          forecast10=list(coupon),
          coupon10_hits=len(actual.intersection(coupon)) if valid else None,
          random10_hits=len(actual.intersection(rng)) if valid else None,
          freq10_hits=len(actual.intersection(freq)) if valid else None,
          family_hit=len(actual.intersection(family)) if valid else None,
          family_exact=int(set(family).issubset(actual)) if valid else None)
        save_new(output,score)
        new_scored.append(score)
        status["scored_new"]+=1
        if valid:status["scored_total"]+=1
        else:status["invalid"]+=1
    return status,new_scored

def run(source,base_dir):
    base=Path(base_dir)
    base.mkdir(parents=True,exist_ok=True)
    forecastpath=base/FORECAST_SUBDIR
    forecastpath.mkdir(exist_ok=True)
    lockpath=base/LOCK_FILE
    lock=fixed_rule()
    save_new(lockpath,lock)
    rows,issues,malformed=extract_rows(source)
    now=utc_now()
    scoreboard,newscores=score_existing(base,rows,now)
    last=rows[-1]
    ok,age=qualify_age(last,now)
    knownids={r["id"] for r in rows}
    canissue=(ok and last["id"]+HORIZON not in knownids)
    outcome="NO_FORECAST_STALE_DATA"
    forecast_written=False
    selected=None
    if canissue:
        selected=source_event_latest(rows)
        if selected is None:
            outcome="NO_SWAPTWO_SIGNAL_ON_NEWEST_DRAW"
        else:
            dest=forecastpath/(str(last["id"])+".json")
            if dest.exists():
                outcome="ALREADY_SEALED"
            else:
                seal=dict(rule=RULE,horizon=HORIZON,rule_version=VERSION,
                   lock_sha256=hashlib.sha256(canonical(lock)).hexdigest(),
                   source_day=last["day"],source_time=last["time"],
                   source_draw_id=last["id"],
                   target_draw_id=last["id"]+HORIZON,
                   source_draw_sha256=hashlib.sha256(canonical({
                        "day":last["day"],"id":last["id"],
                        "nums":list(last["nums"]), "time":last["time"]})).hexdigest(),
                   sealed_at_utc=now.isoformat(),
                   **selected)
                save_new(dest,seal)
                forecast_written=True
                outcome="FORECAST_SEALED_BEFORE_TARGET"
    allscores=[]
    for sf in sorted((base/SCORE_SUBDIR).glob("*.json")):
        x=json.loads(sf.read_text(encoding="utf-8"))
        if x["status"]=="SCORED":allscores.append(x)
    good=len(allscores)
    calc=lambda key:round(sum(x[key] for x in allscores)/good,7) if good else None
    status=dict(version=VERSION,updated_at_utc=now.isoformat(),
        frozen_model_rule=RULE,locked_draw_horizon=HORIZON,
        latest_data_draw_id=last["id"],latest_data_date=last["day"],
        latest_data_clock=last["time"],source_age_minutes=age,
        most_recent_draw_is_fresh=ok,action=outcome,
        registered_new_forecast=forecast_written,
        pending_count=scoreboard["pending"],
        scored_forecasts_total=good,
        new_scores_added=scoreboard["scored_new"],
        avg_10_correct=calc("coupon10_hits"),
        avg_random10_correct=calc("random10_hits"),
        avg_frequency10_correct=calc("freq10_hits"),
        ten_out_of_ten_count=sum(x["coupon10_hits"]==10 for x in allscores),
        interpretation="No evidence of predictive advantage on previous V87 holdout; zero confirmed prospective scores until truly new results are supplied.",
        malformed_lines=malformed[:10],issues=issues[:10])
    statuspath=base/"durum.json"
    statuspath.write_text(json.dumps(status,ensure_ascii=False,indent=2,
                        sort_keys=True)+"\n",encoding="utf-8")
    (base/"SONUC_OKU.txt").write_text(
        "V88 — GELECEKTEKI CEKILISLER ICIN GERCEK KAYIT\n"
        f"Son kayitli cekilis: {last['id']} {last['day']} {last['time']}\n"
        f"Yasi: {age:.2f} dakika | Durum: {outcome}\n"
        f"Sabit deney: V87 SWAP_TWO, 3 cekilis sonrasi tek 10lu.\n"
        f"Gercek ileri testte puanlanan tahmin sayisi: {good}\n"
        f"Ortalama10: {status['avg_10_correct']} vs random10 "
        f"{status['avg_random10_correct']}\n"
        "Tahmin DOSYASI GitHub commit ile ONCEDEN kaydedilmeden test tamamlanmis sayilmaz.\n"
        "Guncel veri olmadan bugun icin yeni kupon veya gelecek isabet uydurulmaz.\n",
        encoding="utf-8")
    print(json.dumps(status,ensure_ascii=False,indent=2),flush=True)
    print("V88 completed local registry evaluation",flush=True)

def selftest():
    l=fixed_rule()
    assert l["class_name"]=="SWAP_TWO" and l["horizon_draws"]==3
    t=datetime.datetime(2026,10,16,8,20,tzinfo=TZ)
    ok,age=qualify_age(dict(day="2026-10-16",time="08:18"),t)
    assert ok and abs(age-2)<.01
    ok2,age=qualify_age(dict(day="2026-10-13",time="23:57"),t)
    assert not ok2
    assert len(rand10(61845,3,"1-2-3-4-5"))==10
    assert len(ticket(bm([1,2,3,4,5]),[0]*81))==10
    print("V88 SELFTEST OK",flush=True)

if __name__=="__main__":
    pa=argparse.ArgumentParser()
    pa.add_argument("--source",default="veri.txt")
    pa.add_argument("--registry",default="v88_prospektif")
    pa.add_argument("--selftest",action="store_true")
    args=pa.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.registry)
