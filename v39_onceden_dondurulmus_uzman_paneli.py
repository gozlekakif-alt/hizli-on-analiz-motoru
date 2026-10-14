# -*- coding: utf-8 -*-
"""V39 — temporally honest 20/80 research motor and V38 data-quality audit.

Independent specialist-inspired *number-level* strategies derived only from
draws strictly BEFORE the target. Scores each frozen ticket when the target
arrives, THEN updates historical states and ensemble weights. It does not
claim to have converted 207 V38 descriptive columns into 207 predictive
models; this would be a data leakage error.

Python stdlib only. Complete day default excludes any missing/incomplete day.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import random
import statistics
import zipfile
from collections import Counter, defaultdict, deque
from itertools import combinations
from datetime import date,timedelta

from v36_rng_davranis_klonu import sorted_draws,on_slot

VERSION="V39.1"
N=80
FULL=(1<<219)-1
DECAY=0.5**(1/12)
MODEL_NAMES=("ISI_SICAK","ISI_SOGUK","YON_IVME","BEKLEME_DONUS",
             "AILE_BAGLANTI","BANT_BASKI","AYNA_KOMSU",
             "ORTAK_KARAKTER","DİYALOG_AGIRLIKLI","RASTGELE_20")
SIGNALS=MODEL_NAMES[:-2]
ENSEMBLE="DİYALOG_AGIRLIKLI"
BASELINE="RASTGELE_20"
COLS=("day","pos","draw_no","clock","phase","method","frozen_before_target",
      "selected20","actual20","hit_count","hit_numbers",
      "warmup","previous_observed_draw_no","model_version")
CSV_OPTS=dict(delimiter=";",lineterminator="\n")
QC_COLS=("expert_id","quality","duplicate_of","distinct_values",
         "observed_rows","note")
GROUPS=("LIFE","HEAT","DIRECTION","WAIT","RETURN","BURST","STAGE",
        "PAIR","TRIPLE","QUARTET","LARGE","BAND","MIRROR","CYCLE",
        "TIME","DIALOGUE","TWIN")


def stable_rng(day,pos,name):
    tag=f"V39|{day}|{pos}|{name}|stable-v1"
    return random.Random(int(hashlib.sha256(tag.encode()).hexdigest()[:16],16))


def show(nums):
    return ",".join(str(n) for n in sorted(nums))


def select20(scores,day,pos,name):
    # Random tie breaker uses target date/position and method only, never
    # actual target numbers or unknown future draw_id.
    rng=stable_rng(day,pos,name)
    keyed=[(float(scores[n-1]),rng.random(),n) for n in range(1,81)]
    keyed.sort(reverse=True)
    result=frozenset(row[-1] for row in keyed[:20])
    assert len(result)==20
    return result


class Life:
    def __init__(self):
        self.bits=[0]*81
        self.heat=[.25]*81
        self.absence=[0]*81
        self.seen=[False]*81
        self.recent=deque(maxlen=12)  # true draws, never fabricated
        self.day=None
        self.pos=None
        self.count=0
        self.last_no=None
        self.unknown_gap=False

    def before(self,day,pos):
        # Per-day short families reset; lifelong history remains available.
        if self.day !=day or (self.pos is not None and
                             (day!=self.day or pos!=self.pos+1)):
            self.recent.clear()
            self.unknown_gap=(self.day==day and self.pos is not None)
        else:self.unknown_gap=False
        self.day=day
        return self

    def observe(self,day,pos,draw_no,winners):
        self.before(day,pos)
        if len(winners)!=20:raise ValueError("Draw must have 20 balls")
        for n in range(1,81):
            hit=int(n in winners)
            self.bits[n]=((self.bits[n]<<1)|hit)&FULL
            self.heat[n]=DECAY*self.heat[n]+(1-DECAY)*hit
            if hit:self.absence[n]=0;self.seen[n]=True
            else:self.absence[n]+=1
        self.recent.append(frozenset(winners))
        self.count+=1;self.last_no=draw_no;self.pos=pos


def features(state):
    anchors=set(state.recent[-1]) if state.recent else set()
    recent=list(state.recent)
    bands=Counter((n-1)//10 for s in recent[-6:] for n in s)
    # Family partner histories conditioned on the known previous draw.
    family=Counter()
    for s in recent[-11:]:
        shared=len(s&anchors)
        for n in s:
            family[n]+=shared-int(n in anchors)
    output={}
    for n in range(1,81):
        bits=state.bits[n]
        h3=(bits&7).bit_count()
        h6=(bits&63).bit_count()
        h11=(bits&2047).bit_count()
        h24=(bits&((1<<24)-1)).bit_count()
        h72=(bits&((1<<72)-1)).bit_count()
        older=((bits>>6)&((1<<6)-1)).bit_count()
        h219=bits.bit_count()
        heat=state.heat[n]
        wait=state.absence[n]
        band=(n-1)//10
        last=int(n in anchors)
        neigh=sum(int(k in anchors) for k in (n-1,n+1) if 1<=k<=80)
        mirror=int((81-n) in anchors)
        # 0..1 normalizations are bounded and hypothesis-driven, not
        # estimated using the current real draw's hidden outcome.
        rate11=h11/min(11,max(1,state.count))
        rate24=h24/min(24,max(1,state.count))
        rate72=h72/min(72,max(1,state.count))
        rate219=h219/min(219,max(1,state.count))
        pressure=bands[band]/max(1,6*min(6,len(recent))) # occupancy in 10-ball band
        pair=family[n]/max(1,11*min(len(anchors),19))
        rise=h3/3 - older/6
        hot=.4*heat+.35*rate11+.25*rate24
        cold=1-hot
        trend=.55*rise+.25*(rate11-rate72)+.20*(heat-.25)
        waiting=min(wait,20)/20 + .15*(1-last) - .2*rate11
        band_signal=pressure-.125
        symmetry=.6*mirror+.4*(neigh/2)
        family_signal=.8*pair+.2*(1 if n in anchors else 0)
        # Ensemble composition defined a priori, not tuned on test data.
        combo=.24*hot+.21*trend+.14*waiting+.17*family_signal+ .12*band_signal+.12*symmetry
        output[n]=(hot,cold,trend,waiting,family_signal,band_signal,symmetry,combo)
    return output


class OnlinePanel:
    def __init__(self):
        self.life=Life()
        self.performance=deque(maxlen=96)  # (eight individual ticket scores) prior outcomes only
        self.snapshots=[]

    def frozen(self,day,pos):
        self.life.before(day,pos)
        f=features(self.life)
        pools={}
        for i,name in enumerate(SIGNALS):
            pools[name]=select20([f[n][i] for n in range(1,81)],day,pos,name)
        # Shrunk, capped, rolling previous draw score for each independent
        # specialist group. It never reads the real target t.
        past=list(self.performance)
        weight=[]
        for i,name in enumerate(SIGNALS):
            mean=(sum(row[i]-5 for row in past)/max(len(past),1)) if past else 0
            weight.append(max(.55,min(1.45,1+.12*mean)))
        weighted=[sum(weight[i]*(n in pools[name])
                      for i,name in enumerate(SIGNALS)) for n in range(1,81)]
        pools[ENSEMBLE]=select20(weighted,day,pos,ENSEMBLE)
        pools[BASELINE]=frozenset(stable_rng(day,pos,BASELINE).sample(range(1,81),20))
        if any(len(p)!=20 for p in pools.values()):
            raise AssertionError("20 distinct balls for each pre-target list")
        return pools,weight

    def score_and_learn(self,day,pos,no,actual,pools):
        scored={m:len(p&actual) for m,p in pools.items()}
        self.performance.append(tuple(scored[n] for n in SIGNALS))
        self.life.observe(day,pos,no,actual)
        return scored


def perday_rows(draws,include_partial):
    days,full,warnings=sorted_draws(draws,include_partial)
    return days,len(full),warnings


def statistics_for(trials):
    # outcomes contain only deliberately frozen pre-target tickets
    byphase=defaultdict(lambda:defaultdict(list))
    for r in trials:
        byphase[r["phase"]][r["method"]].append(r["hit_count"])
    out=[]
    for phase,models in sorted(byphase.items()):
        for method,vals in sorted(models.items()):
            counts=Counter(vals)
            out.append({"phase":phase,"method":method,"n":len(vals),
                "avg_hit":round(statistics.mean(vals),5),
                "max_hit":max(vals),
                "hits_10plus":sum(x>=10 for x in vals),
                "hits_12plus":sum(x>=12 for x in vals),
                "hits_14plus":sum(x>=14 for x in vals),
                "hits_16plus":sum(x>=16 for x in vals),
                "histogram_0_to_20":json.dumps([counts.get(k,0) for k in range(21)])})
    return out


def block_difference(trials,phase="TEST",iterations=1200):
    byday=defaultdict(dict)
    for r in trials:
        if r["phase"]==phase and r["method"] in (ENSEMBLE,BASELINE):
            byday[r["day"]].setdefault(r["method"],[]).append(r["hit_count"])
    daydiff=[]
    for day,groups in sorted(byday.items()):
        a=groups.get(ENSEMBLE,[]);b=groups.get(BASELINE,[])
        if a and len(a)==len(b):
            daydiff.append((sum(a)-sum(b),len(a)))
    if not daydiff:return {"tested_days":0,"difference":None,"day_bootstrap_95":None}
    net=sum(a for a,n in daydiff)/sum(n for a,n in daydiff)
    rng=random.Random(39012026)
    sample=[]
    for _ in range(iterations):
        chosen=[daydiff[rng.randrange(len(daydiff))] for _ in daydiff]
        sample.append(sum(a for a,n in chosen)/sum(n for a,n in chosen))
    sample.sort()
    return {"tested_days":len(daydiff),
            "mean_hits_ensemble_minus_rng":round(net,5),
            "day_bootstrap_95":[round(sample[int(.025*(len(sample)-1))],5),
                                  round(sample[int(.975*(len(sample)-1))],5)],
            "interpretation":"Difference is descriptive, daily clustered. A 95% interval crossing zero does not establish improvement."}


def make_rows(draws,include_partial=False,progress=None):
    days,full,errors=perday_rows(draws,include_partial)
    cutoff=days[len(days)//2][0]
    panel=OnlinePanel()
    rows=[]
    total=sum(len(g) for _,g in days)
    processed=0
    for day,group in days:
        for d in group:
            pos=d["pos"];actual=d["nums"]
            previous=panel.life.last_no
            pools,weights=panel.frozen(day,pos)  # no actual passed in
            hits=panel.score_and_learn(day,pos,d["no"],actual,pools) # observe AFTER freeze
            phase="EGITIM" if day<cutoff else "TEST"
            for name,selected in pools.items():
                rows.append({"day":day,"pos":pos,"draw_no":d["no"],
                    "clock":on_slot(pos),"phase":phase,
                    "method":name,
                    "frozen_before_target":"EVET",
                    "selected20":show(selected),"actual20":show(actual),
                    "hit_count":hits[name],
                    "hit_numbers":show(selected&actual),
                    "warmup":int(previous is None),
                    "previous_observed_draw_no":previous or "",
                    "model_version":VERSION})
            processed+=1
            if progress and (processed%100==0 or processed==total):
                progress(processed,total,"V39 önceden dondurulan 20 sayılar",day)
    summary=statistics_for(rows)
    comparison=block_difference(rows)
    meta={"version":VERSION,"full_days_in_source":full,
          "studied_days":len(days),"draw_count":processed,
          "individual_models":list(MODEL_NAMES),
          "ticket_count":len(rows),
          "trained_date_before_test":cutoff,
          "historical_source_warnings":errors,
          "same_draw_future_leakage":False,
          "methodology":"Features at t use only draws <t; frozen 20 numbers evaluated against t; after evaluation states update.",
          "v38_quality_status":"207 descriptive fields are not directly used as per-number predictive features; separate QC report identifies duplicates/constant columns.",
          "target_16plus_guarantee":False,"fair_20_overlap_expected":5,
          "test_ensemble_vs_rng":comparison}
    return rows,summary,meta


def audit_v38_zip(blob):
    # Real data-driven quality audit. Assumes externally supplied original V38
    # CSV; does NOT use this CSV's current outcome as predictive features.
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name=next((n for n in z.namelist() if n.startswith("02_HER_GERCEK_CEKILISTE_207")),None)
        if not name:raise ValueError("Expected original V38 207-expert CSV missing")
        file=io.TextIOWrapper(z.open(name),encoding="utf-8-sig",newline="")
        reader=csv.DictReader(file,delimiter=";")
        ids=[c for c in reader.fieldnames if c not in ("seq","draw_no","day","pos")]
        if len(ids)!=207:raise ValueError(f"Expected 207 expert fields, got {len(ids)}")
        hashes={name:hashlib.sha256() for name in ids}
        first={};unique={i:set() for i in ids}
        varied=set()
        size=0
        for row in reader:
            size+=1
            for ident in ids:
                value=row[ident]
                hashes[ident].update(value.encode()+b"\x00")
                if ident not in first:first[ident]=value
                elif value!=first[ident]:varied.add(ident)
                if len(unique[ident])<100:unique[ident].add(value)
        groups=defaultdict(list)
        for name in ids:groups[hashes[name].hexdigest()].append(name)
        orig={}
        for grp in groups.values():
            for name in grp[1:]:orig[name]=grp[0]
        report=[]
        for name in ids:
            isconst=name not in varied
            note="constant zero" if isconst and float(first[name])==0 else (
                "constant" if isconst else "duplicate exact stream" if name in orig else "varies")
            quality="SABIT" if isconst else "TEKRAR" if name in orig else "AYRI_OLCUM"
            report.append({"expert_id":name,"quality":quality,
                "duplicate_of":orig.get(name,""),"distinct_values":len(unique[name]),
                "observed_rows":size,"note":note})
        return report,{"draws":size,"experts":207,
            "constant":len(ids)-len(varied),
            "always_zero":sum(1 for i in ids if i not in varied and float(first[i])==0),
            "duplicate_columns":len(orig),
            "unique_streams":len(groups),
            "variable_unique_streams":sum(any(n in varied for n in group) for group in groups.values()),
            "meaning":"Exact data equality does not prove logical equivalence; correlated but unequal experts may still be redundant."}


def csvout(z,name,fields,records):
    with z.open(name,"w") as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
        wr=csv.DictWriter(stream,fieldnames=fields,extrasaction="ignore",**CSV_OPTS)
        wr.writeheader()
        for row in records:wr.writerow(row)
        stream.flush();stream.detach()


def package(rows,summary,meta,quality=None,quality_stats=None):
    # ZIP is deterministic and reproducible for equal input.
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        csvout(z,"01_CEKILIS_ONCESI_20_SAYILIK_DONDURULMUS_LISTELER.csv",COLS,rows)
        csvout(z,"02_EGITIM_TEST_HER_MOTOR_ISABET.csv",
            ("phase","method","n","avg_hit","max_hit","hits_10plus",
             "hits_12plus","hits_14plus","hits_16plus","histogram_0_to_20"),summary)
        z.writestr("03_GUN_BLOK_KARSILASTIRMA.json",
            json.dumps(meta["test_ensemble_vs_rng"],ensure_ascii=False,indent=2).encode())
        csvout(z,"04_V38_207_UZMAN_KALITE_KONTROLU.csv",
               QC_COLS,quality or [])
        z.writestr("05_KAYNAK_VE_DOGRULAMA.json",
                   json.dumps({**meta,"v38_quality_audit":quality_stats},
                     ensure_ascii=False,indent=2).encode())
        z.writestr("00_NASIL_OKUNUR.txt",(
         "V39 GERCEK GELECEGE BAKMADAN 20/80 FORWARD-REPLAY\n"
         "================================================\n"
         "Her t gercek cekilisini BILMEDEN 8 kayitli 20'li mekanik,\n"
         "uzman agirliklariyla olusturulan 20'li ve bagimsiz RNG 20'li\n"
         "karmasik sayi kimlikleri kullanilarak olusturulur. Hedef t\n"
         "gelince isabetleri 0..20 olarak sayilir, sonra tarihsel\n"
         "sayi/isi/aile/bant/komsuluk hafizasi t ile gunellenir.\n"
         "KAYIT KURALI: randevu/cekilis esnasinda gercek gelecek gorulmez.\n"
         "Bu retrospektif bir replay; gerçek zamanlı dış kayıt değildir.\n"
         "207 V38 kolonunun hepsi 80 sayilik olasilik tahmini DEGILDIR.\n"
         "Gecmis sonuc iceren V38 niteliklerini ayni t'nin tahmini diye\n"
         "kullanmak veri kacagidir. Ayrica V38 kolon tekrari/sabitligi\n"
         "istege bagli kalite raporunda saptanir; etki olarak sayilmaz.\n"
         "8 mekanik onceden sabittir, hedefte gizli isabet tahmini iddiasi\n"
         "yoktur. Ortalama bagimsiz 20/80 referansi 5/20'dir.\n"
         "Ilk 36/son 36 TAM gun etiketi, en erken tarihlerin yarilaridir.\n"
         "Testte online agirliklar sadece gercek t geldikten SONRA yenilenir.\n"
         "Testte coklu model tarama daha fazla gorunebilir: basari iddiasi\n"
         "gelecekte bagimsiz takvim gunlerinde dogrulanmalidir.\n"
        ).encode("utf-8-sig"))
    return output.getvalue()


def study(draws,include_partial=False,quality_zip=None,progress=None):
    quality,stats=(audit_v38_zip(quality_zip) if quality_zip else (None,None))
    rows,summary,meta=make_rows(draws,include_partial,progress)
    return package(rows,summary,meta,quality,stats),meta,summary,stats
