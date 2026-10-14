# -*- coding: utf-8 -*-
"""V38: 207 distinct, chronologically evaluated V37 micro-expert measurements.

All 207 catalogue IDs emit ONE numeric observed measure per genuine draw,
including zero if its specified pattern is absent.  Measures are not 207
independent RNG decoders.  More complex labelled lifecycle/causal experts
emit limited-screening proxies (clearly registered), not a falsely complete
individual-identity census. Read-only source: V37 shared SQLite draw_ledger
and ball_step. Extra derived data is checkpointed in the SAME database.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import pickle
import random
import sqlite3
import zlib
import zipfile
from collections import Counter, deque
from itertools import combinations
from pathlib import Path
from v38_207_katalog import CATALOGUE,IDS,GROUPS
from v37c_parcali_aile_hayati import _counts_two,_counts_three,CATALOG_MASKS
from v36_rng_davranis_klonu import SIX,on_slot

VERSION=1
DEEP_PENDING={"LIFE.04","HEAT.08","HEAT.09","HEAT.10","RETURN.04",
  "RETURN.05","RETURN.06","RETURN.07","RETURN.08","RETURN.10",
  "BURST.09","BURST.13","BURST.14","STAGE.08","STAGE.09",
  "PAIR.04","PAIR.08","PAIR.10","TRIPLE.03","TRIPLE.08",
  "TRIPLE.09","TRIPLE.10","TRIPLE.12","QUARTET.03",
  "QUARTET.10","QUARTET.12","QUARTET.13","QUARTET.16",
  "LARGE.04","LARGE.05","LARGE.06","LARGE.07","LARGE.08",
  "BAND.13","CYCLE.09","TIME.10","DIALOGUE.08","DIALOGUE.09",
  "DIALOGUE.10","DIALOGUE.11","DIALOGUE.12",
  "TWIN.05","TWIN.06","TWIN.07","TWIN.08","TWIN.09","TWIN.11"}
assert set(DEEP_PENDING)<set(IDS)
LENGTHS=Counter(x.split(".")[0] for x in IDS)
assert len(IDS)==207 and len(GROUPS)==17
VERSION_HASH=hashlib.sha256(("V38"+str(VERSION)+"|"+",".join(IDS)).encode()).hexdigest()
CSV_OPTIONS=dict(delimiter=";",lineterminator="\n")
EXAMPLES=("seq","draw_no","day","pos","expert","metric","value","sample_ids","evidence_draw_no")
COLD_NAMES=SIX[:2]
HALF=list(range(1,41))
BANDS=tuple((n-1)//10 for n in range(1,81))


def c(n,k):
    return math.comb(n,k) if n>=k>=0 else 0


def avg(a):
    return sum(a)/len(a) if a else 0


def mask(s):
    return sum(1<<(n-1) for n in s)


def parse_wins(hex_mask):
    b=int(hex_mask,16)
    return frozenset(n for n in range(1,81) if b&(1<<(n-1)))


def _countlines(db,no):
    rows=db.execute("""SELECT num,hit,day_hits,life_hits,day_wait,life_wait,
         day_run,life_run,history11,last11_count,valid11,heat,heat_seat,
         heat_move,band,half FROM ball_step WHERE draw_no=? ORDER BY num""",
         (no,)).fetchall()
    if len(rows)!=80 or sum(r[1] for r in rows)!=20:
        raise ValueError("80 cards / 20 hits invariant failed")
    fields=("num","hit","day_hits","life_hits","day_wait","life_wait",
            "day_run","life_run","history11","last11_count","valid11","heat",
            "heat_seat","heat_move","band","half")
    return {r[0]:dict(zip(fields,r)) for r in rows}


class History:
    def __init__(self):
        self.recent=deque(maxlen=219)
        self.same_day=deque(maxlen=217)
        self.prev_map=None
        self.last_day=None
        self.last_pos=None
        self.pairs_seen=set()
        self.triples_seen=set()
        self.prev_h6={}
        self.prev_dirs={}
        self.previous_scores=None
        self.clock20=set()
        self.clock60=set()
        self.clock_len20=0
        self.clock_len60=0
        self.cloned_seen20=set()
        self.cloned_seen60=set()
        self.clone_past=deque(maxlen=12)
        self.last_clone=None
        self.last_baseline=None
        self.last_events=deque(maxlen=8)
        self.revisit_heat=Counter()
        self.warming_streak=Counter()
        self.cooling_streak=Counter()
        self.full_streak=Counter()
        self.last_return={}
        self.last_reactivation={}
        self.motifs=Counter()

    def day_transition(self,day,pos):
        adjacent=bool(self.last_day==day and self.last_pos is not None and pos==self.last_pos+1)
        if not adjacent:
            self.same_day.clear()
            self.clock20.clear();self.clock60.clear()
            self.clock_len20=0;self.clock_len60=0
            self.clone_past.clear()
            self.cloned_seen20.clear();self.cloned_seen60.clear()
            self.last_clone=None
            self.full_streak.clear()
        self.last_day=day;self.last_pos=pos
        return adjacent


def _repeats(now,history):
    # Exact UNIQUE families present now and on at least one earlier draw
    # within the previous 11 genuine consecutive day positions.
    repeat={2:set(),3:set(),4:set()}
    frequency4=Counter()
    for former in list(history)[-11:]:
        shared=sorted(now & former)
        for k in (2,3,4):
            for tup in combinations(shared,k):
                repeat[k].add(tup)
                if k==4:frequency4[tup]+=1
    return repeat,frequency4


def _first_time_family(state,now,k):
    past=state.pairs_seen if k==2 else state.triples_seen
    current=set(combinations(sorted(now),k))
    born=len(current-past)
    old=len(current &past)
    past.update(current)
    return born,old


def _weighted(scores,seed):
    rng=random.Random(seed)
    pairs=[(-math.log(max(rng.random(),1e-16))/max(w,1e-8),n)
           for n,w in enumerate(scores,start=1)]
    return frozenset(n for _,n in sorted(pairs)[:20])


def _measure(metrics):
    if len(metrics)!=207 or set(metrics)!=set(IDS):
        raise AssertionError("207 unique experts must each be evaluated")
    for k,v in metrics.items():
        if not isinstance(v,(int,float)) or not math.isfinite(v):
            raise AssertionError("non-numeric expert metric: "+k)
    return metrics


def calculate(s,seq,no,day,pos,now,lookbehind,old_map):
    contiguous=s.day_transition(day,pos)
    prev=s.recent[-1] if s.recent and contiguous else frozenset()
    older=s.recent[-2] if len(s.recent)>=2 and contiguous else frozenset()
    old3=s.recent[-3] if len(s.recent)>=3 and contiguous else frozenset()
    # 'now' holds exactly 80 current cards. Freeze current winners before
    # calculating previous-wait exits; never include the 60 missing balls.
    rows=now
    win=frozenset(n for n,r in rows.items() if r["hit"])
    newcomers=win-set(prev);returners=win&set(prev);stop=set(prev)-win
    wait_exits={n for n in win if old_map and old_map[n]["life_wait"] is not None
                and old_map[n]["life_wait"]>=6}
    old_h={n:old_map[n]["heat_seat"] if old_map else None for n in range(1,81)}
    new_h={n:rows[n]["heat_seat"] for n in range(1,81)}
    heat_ix={n:SIX.index(new_h[n]) for n in range(1,81)}
    old_ix={n:SIX.index(old_h[n]) if old_h[n] in SIX else heat_ix[n]
            for n in range(1,81)}
    asc={n for n in range(1,81) if heat_ix[n]>old_ix[n]}
    desc={n for n in range(1,81) if heat_ix[n]<old_ix[n]}
    still=set(range(1,81))-asc-desc
    h6={n for n,r in rows.items() if r["valid11"] and r["last11_count"]>=6}
    prev_h6={n for n,r in (old_map or {}).items() if r["valid11"] and r["last11_count"]>=6}
    active_day=[r for r in rows.values() if r["day_wait"] is not None]
    active_life=[r for r in rows.values() if r["life_wait"] is not None]
    silence={n for n,r in rows.items() if r["life_wait"] is not None and r["life_wait"]>=6}
    w6={n for n,r in rows.items() if r["day_wait"] is not None and r["day_wait"]>=6}
    counts=Counter((n-1)//10 for n in win)
    old_counts=Counter((n-1)//10 for n in prev)
    heat_counts=Counter(new_h.values())
    exact20=mask(win)
    # Immutable prior-draw source available for experts, and window cut at day start
    recent=list(s.same_day)
    reps,qprior=_repeats(win,recent)
    pair_new,pair_old=_first_time_family(s,win,2)
    triple_new,triple_old=_first_time_family(s,win,3)
    fq={t for t in combinations(sorted(win),4)}
    consecutive_q=sum(1 for t in reps[4] if set(t)<=set(prev))
    fragment2=_counts_two(set(prev),set(win)) if contiguous else (0,0,0)
    fragment3=_counts_three(set(older),set(prev),set(win)) if contiguous and len(recent)>=2 else (0,0,0)
    if len(recent)>=3:
        age1=set(recent[-3])
        age2=set(recent[-2])-age1
        age3=set(recent[-1])-(age1|age2)
        age4=set(win)-(age1|age2|age3)
        piece1111=len(age1)*len(age2)*len(age3)*len(age4)
        exclude=len(age1&win)*len(age2&win)*len(age3&win)*len(age4)
        piece1111=max(0,piece1111-exclude)
    else:piece1111=0
    oldrep=set(older)&set(prev)
    qdirs=sum(any(n in asc for n in t) and any(n in desc for n in t) for t in reps[4])
    up_weak=sum((n in asc and rows[n]["life_wait"] is not None and rows[n]["life_wait"]>0)
                for n in range(1,81))
    # 80/80 renewal counters are independent from a number's absent streak.
    before_cycle=set(s.clock20)
    s.clock20.update(win)
    s.clock60.update(set(range(1,81))-win)
    s.clock_len20+=1;s.clock_len60+=1
    done20=int(len(s.clock20)==80)
    done60=int(len(s.clock60)==80)
    rem20=80-len(s.clock20);rem60=80-len(s.clock60)
    # Clone: independently generated 20 out of 80; conditioned clone's
    # weights derive solely from t-1 cards, never from current t.
    base_seed=int(hashlib.sha256(f"V38|{day}|{pos}|RNG".encode()).hexdigest()[:16],16)
    baseline=frozenset(random.Random(base_seed).sample(range(1,81),20))
    weights=[math.exp(min(0.8,max(-0.8,(old_map[n]["heat"]-.25*4)*.08)))
             if old_map else 1.0 for n in range(1,81)]
    clone=_weighted(weights,base_seed+38)
    sim_aut=frozenset(random.Random(base_seed+307).sample(range(1,81),20))
    sample_q_count=sum(1 for qmask in CATALOG_MASKS if (exact20&qmask).bit_count()==4)
    clone_q_count=sum(1 for qmask in CATALOG_MASKS if (mask(sim_aut)&qmask).bit_count()==4)
    density_recent=sum(len(win&x) for x in recent[-6:]) if recent else 0
    prev_dirs=dict(s.prev_dirs)
    above_temp={n for n in win if new_h[n] in ("SICAK","SICAGA_YAKIN")}
    # cycle id snapshots before reset; closures reset only AFTER measurements
    metrics={}
    def add(g,values):
        ids=[x for x in IDS if x.startswith(g+".")]
        if len(ids)!=len(values):raise ValueError(f"{g} requires {len(ids)} measurements, given {len(values)}")
        metrics.update(zip(ids,[float(x) for x in values]))
    recent_life=[set(a) for a in list(s.recent)[-219:]]
    def hits_over(span):
        return sum(len(win&z) for z in recent_life[-(span-1):])+20
    freq11=sum(r["last11_count"] for r in rows.values() if r["valid11"])
    avg_lw=avg([r["life_wait"] for r in active_life])
    ups_rank=sum(rows[n]["heat"]>old_map[n]["heat"] for n in still if old_map) if old_map else 0
    downs_rank=sum(rows[n]["heat"]<old_map[n]["heat"] for n in still if old_map) if old_map else 0
    seat_return=sum(old_map is not None and old_h[n]!=new_h[n] and
                   s.revisit_heat[(n,new_h[n])]>0 for n in range(1,81))
    boundary=sum(new_h[n]!=old_h[n] and abs(heat_ix[n]-old_ix[n])==1
                 for n in range(1,81) if old_map)
    for n in range(1,81):
        s.revisit_heat[(n,new_h[n])]+=1
    up_twice=sum(n in asc and prev_dirs.get(n)=="YUKSELIS" for n in asc)
    down_twice=sum(n in desc and prev_dirs.get(n)=="DUSUS" for n in desc)
    up_turn=sum(n in asc and prev_dirs.get(n)=="DUSUS" for n in asc)
    down_turn=sum(n in desc and prev_dirs.get(n)=="YUKSELIS" for n in desc)
    missing=len([r for r in rows.values() if r["life_wait"] is None])
    add("LIFE",[
        sum(r["hit"] for r in rows.values()),sum(r["day_hits"] for r in rows.values()),
        sum(r["life_hits"] for r in rows.values()),
        hits_over(3)+hits_over(6)+hits_over(11)+hits_over(219),
        sum(r["day_hits"]==1 and r["hit"] for r in rows.values()),
        sum(r["life_hits"]==1 and r["hit"] for r in rows.values()),
        80-missing,avg([r["day_wait"] for r in active_day]),
        avg_lw,avg([r["day_run"] for r in rows.values()]),
        avg([r["life_run"] for r in rows.values()]),missing])
    heat_flags=[sum(new_h[n]==label for n in win) for label in SIX]
    add("HEAT",heat_flags+[
        sum(rows[n]["heat"] for n in win),
        avg([s.revisit_heat[(n,new_h[n])] for n in range(1,81)]),
        seat_return,boundary,ups_rank,downs_rank,
        sum(new_h[n]==old_h[n] and rows[n]["heat"]>old_map[n]["heat"] for n in range(1,81)) if old_map else 0,
        sum(heat_counts.values())])
    transitions=[("SOGUK","SOGUGA_YAKIN"),("SOGUGA_YAKIN","ORTA"),
         ("ORTA","ILIK"),("ILIK","SICAGA_YAKIN"),("SICAGA_YAKIN","SICAK"),
         ("SICAK","SICAGA_YAKIN"),("SICAGA_YAKIN","ILIK"),
         ("ILIK","ORTA"),("ORTA","SOGUGA_YAKIN"),("SOGUGA_YAKIN","SOGUK")]
    add("DIRECTION",[
        *[sum(old_h[n]==a and new_h[n]==b for n in range(1,81))
          for a,b in transitions],
        sum(abs(heat_ix[n]-old_ix[n])>1 for n in range(1,81)),
        up_twice,down_twice,len(still)+up_turn+down_turn,
        down_turn,up_turn])
    gaps=[sum(r["day_wait"]==k for r in active_day) for k in range(1,11)]
    add("WAIT",[
        gaps[0],sum(gaps[1:3]),sum(gaps[3:5]),
        *gaps[5:10],sum(r["day_wait"] is not None and 11<=r["day_wait"]<=15 for r in active_day),
        sum(r["day_wait"] is not None and 16<=r["day_wait"]<=24 for r in active_day),
        sum(r["day_wait"] is not None and r["day_wait"]>=25 for r in active_day),
        sum((n-1)//10 for n in silence),
        sum(n in asc for n in silence),
        sum(r["day_wait"]!=r["life_wait"] for r in rows.values() if r["day_wait"] is not None and r["life_wait"] is not None),
        len(wait_exits),sum(r["life_wait"]==0 for r in rows.values())])
    # Return branch fine-grain event measurements, not complete episodes.
    return_ages={n:old_map[n]["life_wait"] for n in wait_exits}
    return1={n for n in win if old_map and old_map[n]["life_run"]==0 and old_map[n]["life_wait"]==1}
    add("RETURN",[
        len(wait_exits),sum(x>=8 for x in return_ages.values()),
        sum(x>=10 for x in return_ages.values()),
        len(win&set(s.last_return)),len(return1),
        sum(n in win and old_map and old_map[n]["life_wait"]==2 for n in win),
        sum(rows[n]["life_run"]>=3 for n in win),
        len(stop&set(s.last_return)),
        len(wait_exits&asc),sum(c(len(wait_exits),2)>0 for _ in [0]),
        sum(n not in before_cycle for n in wait_exits),
        avg(list(return_ages.values()))])
    byfreq=Counter(r["last11_count"] for r in rows.values() if r["valid11"])
    h6persist=h6&prev_h6
    h6exit=prev_h6-h6
    add("BURST",[
        sum(byfreq[k] for k in range(4)),byfreq[4],byfreq[5],
        byfreq[6],byfreq[7],byfreq[8],sum(byfreq[k] for k in range(9,12)),
        len(h6persist),sum(s.prev_h6.get(n,0)>=2 for n in h6persist),
        len(h6exit),len(h6)*len(w6),
        sum(r["valid11"] and r["last11_count"]>=6 and
            (int(r["history11"][-5:],2).bit_count()*6 >
             int(r["history11"][:6],2).bit_count()*5)
            for r in rows.values() if r["history11"]),
        len(h6&prev_h6),sum(rows[n]["history11"]!=old_map[n]["history11"] for n in range(1,81)
                            if old_map and rows[n]["valid11"] and old_map[n]["valid11"])])
    add("STAGE",[
        len(returners),len(stop),len(newcomers),60-len(stop),
        len(above_temp&newcomers),sum((n-1)//10 for n in newcomers),
        len(returners),int(len(returners)>=8 or len(returners)<=2),
        sum(set(q)<=newcomers for q in reps[2]),sum(rows[n]["life_run"]>=2 for n in win)])
    add("PAIR",[
        pair_new,c(len(win&prev),2),pair_old,
        sum(1 for p in reps[2] if len(recent)>=3 and sum(set(p)<=v for v in recent)>=3),
        20*60,c(60,2),
        len(reps[2])-c(len(win&prev),2),
        avg([len(recent)-next((j for j,x in enumerate(reversed(recent),1)
                              if set(p)<=x),len(recent)) for p in list(reps[2])[:60]]),
        sum((a in asc and b in desc) or (b in asc and a in desc) for a,b in reps[2]),
        sum(1 for pair in reps[2] if any(set(pair)<=set(t) for t in list(reps[3])[:30]))])
    add("TRIPLE",[
        triple_new,c(len(win&prev),3),triple_old,
        c(len(set(prev)-win),2)*len(win-set(prev)),
        len(set(prev)-win)*c(len(win-set(prev)),2),
        (len(set(older)-set(prev))*len(set(prev)-win)*len(win-set(prev))
         if len(recent)>=2 else 0),
        c(len(win&prev),2)*len(set(range(1,81))-win),
        c(60,3),c(len(win)-len(win&prev),3),
        len(reps[3])-c(len(win&prev),3),
        len(reps[3]),sum(1 for p in list(reps[3])[:100] if any(set(p)<=set(q) for q in list(reps[4])[:30]))])
    add("QUARTET",[
        c(20,4),c(len(win&prev),4),
        sum(1 for fam,count in qprior.items() if count>=2),
        fragment2[2],fragment2[0],fragment2[1],
        fragment3[2],fragment3[1],fragment3[0],
        piece1111,
        c(len(win&prev),1)+c(len(win&prev),2),
        c(20,3)*60,
        c(60,4),sum(fragment2)+sum(fragment3),
        qdirs,sum(1 for q in list(reps[4])[:100] if any(set(q)<=set(t) for t in list(reps[4])[:25]))])
    # Large-family events are candidate-proxy counts; identities are not yet
    # a complete, permanently followed 5..10-member census.
    overlap=len(win&prev)
    add("LARGE",[
        c(overlap,5),c(overlap,6),
        sum(c(overlap,k) for k in range(7,11)),
        len(newcomers),c(60,5),
        c(len(win&prev),3)*c(len(newcomers),2),
        c(overlap,5),
        len(reps[4])])
    rising_bands=[b for b in range(8) if counts[b]>old_counts[b]]
    falling_bands=[b for b in range(8) if counts[b]<old_counts[b]]
    add("BAND",[
        *[counts[i] for i in range(8)],
        sum(abs(counts[i]-2.5) for i in range(8)),
        sum(new_h[n] in ("SICAK","SICAGA_YAKIN") for n in win),
        len({(n-1)//10 for n in w6}),
        sum(counts[b]>old_counts[b] and counts[7-b]<old_counts[7-b] for b in range(8)),
        len(rising_bands)*len(falling_bands),
        sum(n+1 in win for n in win if n%10 and n<80)])
    mirrorpairs=sum((81-n) in win for n in win)//2
    mirrornew=sum((81-n) in prev for n in newcomers)
    add("MIRROR",[
        mirrorpairs,len([n for n in win if n<=40]),len([n for n in win if n>40]),
        sum(counts[b]*counts[7-b] for b in range(4)),
        sum((n-1 in win)+(n+1 in win) for n in win)//2,
        sum({n,n+1}<=win for n in range(1,80)),
        sum({n,n+1,n+2}<=win for n in range(1,79))+
            sum({n,n+1,n+2,n+3}<=win for n in range(1,78)),
        sum({n,n+2,n+4}<=win for n in range(1,77)),
        mirrornew])
    add("CYCLE",[
        len(s.clock20),len(s.clock60),
        len(s.clock20) if s.clock_len20==4 else 0,
        len(s.clock20) if s.clock_len20==8 else 0,
        len(s.clock20) if s.clock_len20==12 else 0,
        int(rem20<=5)+int(rem60<=5),
        int(rem20==1)+int(rem60==1),
        done20+done60,
        s.clock_len20+s.clock_len60,
        sum(n not in s.clock20 and n in silence for n in range(1,81))])
    hr_time=on_slot(pos)
    minute=int(hr_time.split(":")[1])
    hour=(pos-14)//12 if pos>=14 else 0
    phase=pos%12
    add("TIME",[
        int(pos==1),int(pos==13),int(pos==14),
        int((pos-14)%12<6) if pos>=14 else int(1<=pos<=6),
        int((pos-14)%12>=6) if pos>=14 else int(7<=pos<=12),
        len(newcomers),pos%12,
        int(minute in (32,37,42,47,52,57)),
        1 if pos<=72 else 2 if pos<=145 else 3,
        len(win&set(s.recent[-1])) if s.recent else 0])
    wl=wait_exits & asc
    multiple_movements=len(wl)+qdirs
    postpair=sum(1 for p in reps[2] if any(n in desc for n in p))
    scode=counts[0]+counts[7]
    add("DIALOGUE",[
        len(wl),sum(n in wait_exits for t in list(reps[4])[:100] for n in t),
        len(h6persist)*sum(abs(counts[k]-2.5)>2 for k in range(8)),
        postpair,
        sum(fragment2)*sum(fragment3),
        sum(n in newcomers and n not in s.clock20 for n in win),
        abs(counts[0]-counts[7])+abs(counts[1]-counts[6]),
        sum(s.last_events),multiple_movements,
        sum(s.last_events[-3:]),
        qdirs,len(wl)+len(reps[4])])
    # TWIN data are descriptive benchmarks not a cloned random seed.
    auto_overlap=len(win&sim_aut)
    conditional_overlap=len(win&clone)
    baseline_overlap=len(win&baseline)
    add("TWIN",[
        20,20,conditional_overlap,baseline_overlap,
        len(win&frozenset(random.Random(base_seed+404).sample(range(1,81),20))),
        len(win&sim_aut),abs(len(silence)-sum(n not in sim_aut for n in range(1,81))),
        abs(sample_q_count-clone_q_count),
        abs(len(s.clock20)-len(s.cloned_seen20)),
        1 if seq<=7812 else 2,
        abs(conditional_overlap-5),auto_overlap])
    _measure(metrics)
    # Important: only update AFTER generating all 207 values for this draw.
    s.recent.append(win);s.same_day.append(win)
    s.prev_map=rows
    s.prev_dirs={n:"YUKSELIS" if n in asc else "DUSUS" if n in desc else "SABIT" for n in range(1,81)}
    s.prev_h6={n:s.prev_h6.get(n,0)+1 if n in prev_h6 else 1 for n in h6}
    s.last_events.append(len(wait_exits&asc)+len(reps[4]))
    s.cloned_seen20.update(sim_aut);s.cloned_seen60.update(set(range(1,81))-sim_aut)
    s.clone_past.append(sim_aut)
    if done20:s.clock20.clear();s.clock_len20=0
    if done60:s.clock60.clear();s.clock_len60=0
    if len(s.cloned_seen20)==80:s.cloned_seen20.clear()
    if len(s.cloned_seen60)==80:s.cloned_seen60.clear()
    s.last_return={n for n in wait_exits}
    s.last_clone=sim_aut;s.last_baseline=baseline
    return metrics,contiguous


def setup(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS v38_registry(
      expert_id TEXT PRIMARY KEY,label TEXT NOT NULL,
      audit_status TEXT NOT NULL,version INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS v38_draw(
      seq INTEGER PRIMARY KEY, draw_no INTEGER UNIQUE NOT NULL,
      day TEXT NOT NULL,pos INTEGER NOT NULL,
      packed_metrics BLOB NOT NULL,
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no));
    CREATE TABLE IF NOT EXISTS v38_checkpoint(
      id INTEGER PRIMARY KEY CHECK(id=1), last_seq INTEGER NOT NULL,
      last_draw_no INTEGER NOT NULL,version_hash TEXT NOT NULL,
      history_zlib BLOB NOT NULL);
    """)
    con.executemany("INSERT OR IGNORE INTO v38_registry VALUES(?,?,?,?)",
       [(identifier,label,
         "TARAMA_GOSTERGESI" if identifier in DEEP_PENDING else "ADIM_OLCUMU",
         VERSION) for identifier,label in CATALOGUE])
    con.commit()


def replay(db_path,progress=None):
    db=sqlite3.connect(str(db_path),timeout=90)
    try:
        setup(db)
        total=db.execute("SELECT COUNT(*) FROM draw_ledger").fetchone()[0]
        ck=db.execute("SELECT last_seq,last_draw_no,version_hash,history_zlib FROM v38_checkpoint WHERE id=1").fetchone()
        if ck and ck[2]!=VERSION_HASH:raise ValueError("V38 catalogue/engine version changed: new DB required")
        start=ck[0] if ck else 0
        state=pickle.loads(zlib.decompress(ck[3])) if ck else History()
        if start>total:raise ValueError("V38 checkpoint longer than source")
        prev=state.prev_map
        entries=0
        # The checkpoint and row table are append-only in a batch transaction.
        cursor=db.execute("SELECT seq,draw_no,day,pos FROM draw_ledger WHERE seq>? ORDER BY seq",(start,))
        for seq,no,day,pos in cursor:
            rows=_countlines(db,no)
            values,contiguous=calculate(state,seq,no,day,pos,rows,None,prev)
            compact=json.dumps([values[x] for x in IDS],separators=(",",":"),ensure_ascii=False)
            db.execute("INSERT INTO v38_draw VALUES(?,?,?,?,?)",
                       (seq,no,day,pos,zlib.compress(compact.encode(),level=4)))
            prev=rows;entries+=1
            if entries%120==0 or seq==total:
                db.execute("INSERT OR REPLACE INTO v38_checkpoint VALUES(1,?,?,?,?)",
                   (seq,no,VERSION_HASH,zlib.compress(pickle.dumps(state,protocol=4),level=5)))
                db.commit()
                if progress:progress(seq,total,"V38 207 uzman çekiliş kaydı",day)
        scanned=db.execute("SELECT COUNT(*) FROM v38_draw").fetchone()[0]
        if scanned!=total:raise AssertionError("not every draw got 207 expert observations")
        return {"experts":len(IDS),"groups":len(GROUPS),
                "per_step_measurement_experts":len(IDS)-len(DEEP_PENDING),
                "proxy_screening_experts":len(DEEP_PENDING),
                "draw_count":scanned,"measurement_cells":scanned*len(IDS),
                "newly_processed_draws":entries,"version":VERSION,
                "catalogue_sha256":VERSION_HASH,
                "warning":"Each expert makes an identified per-draw measurement. Some use limited proxy screening, NOT complete lifecycle/causal reconstruction; 207 measurements do not prove improved 20/80 prediction."}
    finally:
        db.close()


def export(db_path,output):
    db=sqlite3.connect(str(db_path))
    try:
        done=db.execute("SELECT COUNT(*) FROM v38_draw").fetchone()[0]
        source=db.execute("SELECT COUNT(*) FROM draw_ledger").fetchone()[0]
        if done!=source:raise ValueError("unfinished 207-expert source")
        with zipfile.ZipFile(str(output),"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            z.writestr("00_OKU_BENI.txt",
               ("V38 207 UZMAN DAHILI ORTAK YASAM HAFIZASI\n"
                "========================================\n"
                "17 ana grup, 207 sabit kimlik; 207 x her gercek cekiliste\n"
                "bir sayisal olcum, kayit yoksa 0. HAM VERI YOK.\n"
                "v37_ortak_hafiza.py tarafindan onaylanmis 80 kart/sira\n"
                "tek ortak SQLite kaynagindan OKUNUR; yeni ham veri kopyalanmaz.\n"
                "Kimi dal tam olay sayar, kimi YALNIZ TARAMA GOSTERGESIDIR.\n"
                "TARAMA_GOSTERGESI ayrintili aile oykusunun tamamini cikarmis\n"
                "sayilmaz; bakiniz 01 UZMAN KATALOG ve 05 KAPSAM.\n"
                "207 uzman birbirinden bagimsiz RNG tohum çözücüsü DEGILDIR.\n"
                "Cikan20, bekleyen60, isi, yon, aile, bant, simetri, iki\n"
                "80/80 dongu, zaman, motor baglanti ve rastgele klon kontrolu\n"
                "sinyalleri gercek cekilis sonrasi kaydedilir.\n"
                "Bir sonraki gercek sonucun kimligini bilmek farkli hedeftir.\n"
               ).encode("utf-8-sig"))
            reg=[{"motor":i,"uzmanlik":lab,
                  "durum":"TARAMA_GOSTERGESI" if i in DEEP_PENDING else "ADIM_OLCUMU",
                  "kaynak":"V37 ORTAK HAFIZA",
                  "not":"Tam aile epizodu degil; sayisal sinyal" if i in DEEP_PENDING
                        else "Her gercek cekiliste sayisal gozetim"}
                 for i,lab in CATALOGUE]
            def tocsv(filename,fields,rows):
                with z.open(filename,"w") as raw:
                    wrapper=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
                    w=csv.DictWriter(wrapper,fieldnames=fields,**CSV_OPTIONS)
                    w.writeheader()
                    for row in rows:w.writerow(row)
                    wrapper.flush();wrapper.detach()
            tocsv("01_207_UZMAN_KIMLIK_VE_KAPSAM.csv",
                  ("motor","uzmanlik","durum","kaynak","not"),reg)
            # Compressed per-draw expert vector, 207 columns, exactly 1 row
            # per real draw. This is leaner than 3.2m duplicated long rows.
            summaries={ident:{"nonzero_draws":0,"total_value":0.0,
                              "firsthalf_total":0.0,"secondhalf_total":0.0}
                       for ident in IDS}
            def walk_rows():
                for seq,no,day,pos,payload in db.execute(
                    "SELECT seq,draw_no,day,pos,packed_metrics FROM v38_draw ORDER BY seq"):
                    values=json.loads(zlib.decompress(payload))
                    if len(values)!=207:raise AssertionError("corrupt expert vector")
                    row={"seq":seq,"draw_no":no,"day":day,"pos":pos}
                    for ident,value in zip(IDS,values):
                        row[ident]=round(value,6)
                        acc=summaries[ident]
                        if value:acc["nonzero_draws"]+=1
                        acc["total_value"]+=value
                        acc["firsthalf_total" if seq<=done//2 else "secondhalf_total"]+=value
                    yield row
            tocsv("02_HER_GERCEK_CEKILISTE_207_UZMAN.csv",
                  ("seq","draw_no","day","pos",*IDS),walk_rows())
            totals=[{"motor":name,"uzmanlik":dict(CATALOGUE)[name],
                     "durum":"TARAMA_GOSTERGESI" if name in DEEP_PENDING else "ADIM_OLCUMU",
                     "gozlenen_cekilis":done,
                     "sifirdan_farkli_cekilis":sums["nonzero_draws"],
                     "toplam_olcum":round(sums["total_value"],5),
                     "ilk_yari_toplam":round(sums["firsthalf_total"],5),
                     "son_yari_toplam":round(sums["secondhalf_total"],5)}
                     for name,sums in summaries.items()]
            tocsv("03_ILK36_SON36_207_UZMAN_DAGILIM.csv",
                  ("motor","uzmanlik","durum","gozlenen_cekilis",
                   "sifirdan_farkli_cekilis","toplam_olcum",
                   "ilk_yari_toplam","son_yari_toplam"),totals)
            bygroup=Counter()
            for name,values in summaries.items():
                g=name.split(".")[0]
                bygroup[(g,"expert_count")]+=1
                bygroup[(g,"nonzero_draws")]+=values["nonzero_draws"]
            groupout=[{"ana_grup":g,
                       "uzman":bygroup[(g,"expert_count")],
                       "pozitif_olcum_kesidi":bygroup[(g,"nonzero_draws")]}
                       for g in GROUPS]
            tocsv("04_17_GRUP_DETAYI.csv",
                  ("ana_grup","uzman","pozitif_olcum_kesidi"),groupout)
            z.writestr("05_KAPSAM_VE_METODOLOJI.json",
                json.dumps({"total_experts":207,"measurement_experts":207-len(DEEP_PENDING),
                  "screening_proxies":sorted(DEEP_PENDING),
                  "draws":done,"cells":done*207,
                  "full_207_historical_lifecycles":False,
                  "registered_expert_observational_values":True,
                  "causality_found":False,"prediction_advantage_tested":False,
                  "random_20of80_baseline_overlap":5,
                  "distinct_family_universe":1581580,
                  "source":"V37 SQLite ball_step / draw_ledger",
                  "warnings":"Proxies are NOT whole specialized lifetime reconstructions; rolling windows dependent."},
                  ensure_ascii=False,indent=2).encode())
        with zipfile.ZipFile(str(output)) as z:
            assert z.testzip() is None and len(z.namelist())==6
        return totals
    finally:db.close()
