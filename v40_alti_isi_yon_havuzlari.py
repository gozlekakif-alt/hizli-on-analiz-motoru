# -*- coding: utf-8 -*-
"""V40 — six-seat heat life, movement and next-draw provenance laboratory.

Each of the 80 numbers is assigned a seat BEFORE the target draw is read.
Heat is EWMA of previously observed draws; direction uses previous two seat
assignments, never target t; past family links and band pressure likewise.
An unbiased 20/80 next draw gives each number probability 25% regardless of
past heat or direction. Tests report these null rates, day bootstrap and
out-of-period predictive calibration. Observing structure is NOT recovering
the hidden RNG. Uses only stdlib; streams ~1.25m number-step records to ZIP.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import random
import statistics
import tempfile
import zipfile
from collections import Counter, defaultdict, deque
from itertools import combinations
from pathlib import Path

from v36_rng_davranis_klonu import sorted_draws, on_slot

ENGINE="V40.1"
SIX=("SOGUK","SOGUGA_YAKIN","ORTA","ILIK","SICAGA_YAKIN","SICAK")
SIZES=(13,13,14,14,13,13)
DIRECTIONS=("YUKSELIS","DUSUS","SABIT","YENI")
FAMILY=("YOK","ZAYIF","ORTA","GUCLU")
RESIDENCE=("YENI","2_3","4_6","7PLUS")
DECAY=.5**(1/12)
SHRINK=120.0
NUMBER_FIELDS=("gun","sira","cekilis_no","hedef_saati","sayi",
    "onceki_cekilis_no","hedef20","havuz","havuz_yonu",
    "onceki_havuz","havuzda_kalis","kalis_sinifi","sicaklik_puani",
    "son_11_gorulme","son_6_gorulme","onceki20","bekleme","bant",
    "bandin_son6_ortalama_yuku","bant_baski",
    "aile_ikili_bag","aile_uclu_bag","aile_dortlu_bag",
    "aile_kuvvet","rastgele_referans_yuzde",
    "hedef_oncesi_kalibre_olasilik","isabet")
STEP_FIELDS=("gun","sira","cekilis_no","hedef_saati","donem",
    "onceki_cekilis_no","havuz","yon","havuz_mevcudu",
    "havuzdan_hedefe_giren","beklenen_25",
    "sicakliktan_yukselen","sicakliktan_dusen",
    "sicaklikta_kalan","aile_guclu_sayisi",
    "bant_baski_artida","onceden_kalibre_isabet_beklentisi")
AGG_FIELDS=("boyut","havuz","yon","aile","band","kalis_sinifi",
    "test_donemi","sayi_firsati","gercek_sahneye_cikis",
    "cikis_orani_yuzde","rng_referans_yuzde",
    "ortalama_rastgele_beklenen","gozlenen_eksi_rastgele",
    "rastgele_farka_gore_oran")
EVAL_FIELDS=("donem","hedef_cekilis","sayisal_test_firsati",
    "rng_25_brier","model_brier","model_eksi_rng_brier",
    "rng_25_logloss","model_logloss","model_eksi_rng_logloss",
    "gun_blok_bootstrap_95_brier_fark","gun_sayisi",
    "model_rastgeleye_ustunlugu_kanitlandi")
CSV_KW=dict(delimiter=";",lineterminator="\n")


def band(n):
    return (n-1)//10


def residence_label(n):
    if n<=1:return "YENI"
    if n<=3:return "2_3"
    if n<=6:return "4_6"
    return "7PLUS"


def family_level(a,b,c):
    # Count actual *prior* draw co-occurrences with prev-draw companions.
    strength=a+b*1.5+c*2
    if strength>=16:return "GUCLU"
    if strength>=7:return "ORTA"
    if strength>0:return "ZAYIF"
    return "YOK"


def direction(before,after):
    if before is None:return "YENI"
    d=SIX.index(after)-SIX.index(before)
    return "YUKSELIS" if d>0 else "DUSUS" if d<0 else "SABIT"


def _number_csv(z,name,fields,rows):
    with z.open(name,"w") as raw:
        wraw=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
        wr=csv.DictWriter(wraw,fieldnames=fields,extrasaction="ignore",**CSV_KW)
        wr.writeheader()
        for item in rows:wr.writerow(item)
        wraw.flush();wraw.detach()


def _write_rows(z,name,fields,rows):
    _number_csv(z,name,fields,rows)


def _assign(heats):
    # Six fixed seat capacities. Tie-break deterministic by number.
    ranks=sorted(range(1,81),key=lambda n:(heats[n],n))
    out={};start=0
    for seat,num in zip(SIX,SIZES):
        for n in ranks[start:start+num]:out[n]=seat
        start+=num
    assert Counter(out.values())==dict(zip(SIX,SIZES))
    return out


class PreDraw:
    def __init__(self):
        self.heat=[.25]*81
        self.absence=[0]*81
        self.bit11=[0]*81
        self.prev=None
        self.prior_seat=None
        self.current_seat=None
        self.residence=[0]*81
        self.last_day=None
        self.last_pos=None
        self.last_no=None
        self.history=deque(maxlen=11)
        self.valid_steps=0
        self.last_steps=0

    def snapshot(self,day,pos):
        # Chronology must be real. 13→14 overnight gap is not fake draws.
        # Daily family windows reset on new day; heat memory persists.
        if self.last_day!=day or (self.last_pos is not None and pos!=self.last_pos+1):
            self.history.clear()
        if not self.valid_steps:
            return None
        seats=dict(self.current_seat)
        prev=dict(self.prior_seat) if self.prior_seat else {}
        histories=list(self.history)
        anchor=self.prev if self.prev else frozenset()
        links={}
        # Pair/Triple/Quartet companions from the most recent real 20.
        for n in range(1,81):
            a=b=c=0
            for past in histories:
                if n not in past:continue
                mates=len((past & anchor)-{n})
                a+=mates
                b+=math.comb(mates,2) if mates>=2 else 0
                c+=math.comb(mates,3) if mates>=3 else 0
            links[n]=(a,b,c)
        pressure=Counter(band(n) for past in histories[-6:] for n in past)
        sample=[]
        for n in range(1,81):
            a,b,c=links[n]
            label=seats[n]
            move=direction(prev.get(n),label)
            # Historical EWMA computed from t-1 and earlier ONLY.
            in6=sum(n in row for row in histories[-6:])
            in11=sum(n in row for row in histories)
            strength=family_level(a,b,c)
            load=pressure[band(n)]/max(1,len(histories[-6:]))
            sample.append({"sayi":n,"havuz":label,"yon":move,
                "onceki_havuz":prev.get(n,"KAYIT_YOK"),
                "kalis":self.residence[n],"kalis_sinifi":residence_label(self.residence[n]),
                "isi":self.heat[n],"onceki20":int(n in anchor),
                "bekleme":self.absence[n],"son6":in6,"son11":in11,
                "bant":band(n),"bant_yuku":load,"bant_baski":"YUKSEK" if load>2.5 else "DUSUK" if load<2.5 else "NORMAL",
                "ikili":a,"uclu":b,"dortlu":c,"aile":strength})
        return sample

    def append(self,day,pos,no,drawn):
        if len(drawn)!=20 or min(drawn)<1 or max(drawn)>80:raise ValueError("not 20 unique")
        if self.last_day!=day or (self.last_pos is not None and pos!=self.last_pos+1):
            self.history.clear()
        self.prior_seat=dict(self.current_seat) if self.current_seat else None
        # Score is updated only AFTER the pre-target snapshot is captured.
        for n in range(1,81):
            hit=int(n in drawn)
            self.heat[n]=DECAY*self.heat[n]+(1-DECAY)*hit
            self.absence[n]=0 if hit else self.absence[n]+1
            self.bit11[n]=((self.bit11[n]<<1)|hit)&2047
        new_seat=_assign(self.heat)
        for n in range(1,81):
            self.residence[n]=self.residence[n]+1 if self.current_seat and self.current_seat[n]==new_seat[n] else 1
        self.current_seat=new_seat
        self.history.append(frozenset(drawn))
        self.prev=frozenset(drawn)
        self.last_day=day;self.last_pos=pos;self.last_no=no
        self.valid_steps+=1


def segment_key(q,mode):
    if mode=="ISI":return ("ISI",q["havuz"],"","","","")
    if mode=="ISI_YON":return ("ISI_YON",q["havuz"],q["yon"],"","","")
    if mode=="ISI_YON_AILE":return ("ISI_YON_AILE",q["havuz"],q["yon"],q["aile"],"","")
    if mode=="ISI_YON_BANT":return ("ISI_YON_BANT",q["havuz"],q["yon"],"",q["bant"],"")
    if mode=="ISI_YON_KALIS":return ("ISI_YON_KALIS",q["havuz"],q["yon"],"","",q["kalis_sinifi"])
    raise ValueError(mode)


def _quantile(a,p):
    s=sorted(a)
    return round(s[int(p*(len(s)-1))],7) if s else None


def _quality(aggregates,order=("EGITIM","TEST")):
    lines=[]
    for (phase,dim,seat,dirn,family,bandn,stay),(cnt,hit) in sorted(aggregates.items(),key=lambda x:str(x[0])):
        if cnt==0:continue
        lines.append({"boyut":dim,"havuz":seat,"yon":dirn,
            "aile":family,"band":bandn,"kalis_sinifi":stay,
            "test_donemi":phase,"sayi_firsati":cnt,"gercek_sahneye_cikis":hit,
            "cikis_orani_yuzde":round(100*hit/cnt,5),
            "rng_referans_yuzde":25,
            "ortalama_rastgele_beklenen":round(cnt*.25,4),
            "gozlenen_eksi_rastgele":round(hit-cnt*.25,4),
            "rastgele_farka_gore_oran":round(hit/max(1,cnt*.25),5)})
    return lines


def _bootstrap(days,model_diff,reps=1000):
    if not days:return None
    rng=random.Random(402026)
    a=[]
    for _ in range(reps):
        subs=[days[rng.randrange(len(days))] for _ in days]
        total=sum(model_diff[x][0] for x in subs)
        n=sum(model_diff[x][1] for x in subs)
        a.append(total/max(1,n))
    return [_quantile(a,.025),_quantile(a,.975)]


def _day_summary(per_day,phase):
    d=[x for x in per_day if x["donem"]==phase]
    return d


def study(draws,include_partial=False,progress=None):
    days,full,warnings=sorted_draws(draws,include_partial)
    cutoff=days[len(days)//2][0]
    engine=PreDraw()
    # Beta prior centered on 25%, shrink 120 pseudo-trials. Parameters
    # selected *before* seeing test period. Update after target observed.
    learner=defaultdict(lambda:[0,0])
    aggregates=defaultdict(lambda:[0,0])
    daily=defaultdict(lambda:[0.,0.,0.,0.,0]) # (model brier, baseline brier, model loss, base loss, N)
    rows_byday=defaultdict(list)
    progress_denom=sum(len(draws) for _,draws in days)
    n_targets=0;total=0;prev_day=None
    zip_buffer=io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
      with z.open("01_80_SAYI_CEKILIS_ONCESI_TUM_KARAKTER.csv","w") as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
        wr=csv.DictWriter(stream,fieldnames=NUMBER_FIELDS,extrasaction="ignore",**CSV_KW)
        wr.writeheader()
        step_rows=[]
        for day,group in days:
          for d in group:
            total+=1
            pos=d["pos"];no=d["no"];target=d["nums"]
            prior_no=engine.last_no
            snap=engine.snapshot(day,pos)  # computed before inspecting target
            if snap is not None:
                n_targets+=1
                phase="EGITIM" if day<cutoff else "TEST"
                members=defaultdict(lambda:[0,0.,0,0,0,0])  # label,(count, p_sum,up,down,still,family)
                samples_by_seat=defaultdict(list)
                for q in snap:
                    k=segment_key(q,"ISI_YON")
                    trial=learner[k]
                    p=max(.03,min(.97,(trial[1]+.25*SHRINK)/(trial[0]+SHRINK)))
                    hit=int(q["sayi"] in target)
                    p_loss=(p-hit)**2
                    base_loss=(.25-hit)**2
                    model_log=-(hit*math.log(p)+(1-hit)*math.log1p(-p))
                    base_log=-(hit*math.log(.25)+(1-hit)*math.log(.75))
                    arr=daily[(phase,day)]
                    arr[0]+=p_loss;arr[1]+=base_loss
                    arr[2]+=model_log;arr[3]+=base_log;arr[4]+=1
                    out={"gun":day,"sira":pos,"cekilis_no":no,"hedef_saati":on_slot(pos),
                        "sayi":q["sayi"],"onceki_cekilis_no":prior_no or "",
                        "hedef20":int(hit),"havuz":q["havuz"],"havuz_yonu":q["yon"],
                        "onceki_havuz":q["onceki_havuz"],"havuzda_kalis":q["kalis"],
                        "kalis_sinifi":q["kalis_sinifi"],"sicaklik_puani":round(q["isi"],7),
                        "son_11_gorulme":q["son11"],"son_6_gorulme":q["son6"],
                        "onceki20":q["onceki20"],"bekleme":q["bekleme"],
                        "bant":q["bant"]*10+1,"bandin_son6_ortalama_yuku":round(q["bant_yuku"],5),
                        "bant_baski":q["bant_baski"],
                        "aile_ikili_bag":q["ikili"],"aile_uclu_bag":q["uclu"],
                        "aile_dortlu_bag":q["dortlu"],"aile_kuvvet":q["aile"],
                        "rastgele_referans_yuzde":25,
                        "hedef_oncesi_kalibre_olasilik":round(p,7),"isabet":hit}
                    wr.writerow(out)
                    for mode in ("ISI","ISI_YON","ISI_YON_AILE","ISI_YON_BANT","ISI_YON_KALIS"):
                        kk=(phase,*segment_key(q,mode))
                        aggregates[kk][0]+=1;aggregates[kk][1]+=hit
                    m=members[q["havuz"]];m[0]+=1;m[1]+=p
                    m[2]+=int(q["yon"]=="YUKSELIS")
                    m[3]+=int(q["yon"]=="DUSUS")
                    m[4]+=int(q["yon"]=="SABIT")
                    m[5]+=int(q["aile"]=="GUCLU")
                    samples_by_seat[(q["havuz"],q["yon"])].append(q)
                assert sum(m[0] for m in members.values())==80
                for seat in SIX:
                    assert members[seat][0]==SIZES[SIX.index(seat)]
                for (seat,dirn),subset in sorted(samples_by_seat.items()):
                    if not subset:continue
                    st=(members[seat])
                    hits=sum(q["sayi"] in target for q in subset)
                    step_rows.append({"gun":day,"sira":pos,"cekilis_no":no,
                        "hedef_saati":on_slot(pos),"donem":phase,
                        "onceki_cekilis_no":prior_no,"havuz":seat,"yon":dirn,
                        "havuz_mevcudu":len(subset),"havuzdan_hedefe_giren":hits,
                        "beklenen_25":round(len(subset)*.25,4),
                        "sicakliktan_yukselen":sum(q["yon"]=="YUKSELIS" for q in subset),
                        "sicakliktan_dusen":sum(q["yon"]=="DUSUS" for q in subset),
                        "sicaklikta_kalan":sum(q["yon"]=="SABIT" for q in subset),
                        "aile_guclu_sayisi":sum(q["aile"]=="GUCLU" for q in subset),
                        "bant_baski_artida":sum(q["bant_baski"]=="YUKSEK" for q in subset),
                        "onceden_kalibre_isabet_beklentisi":round(sum(
                            max(.03,min(.97,(learner[segment_key(q,"ISI_YON")][1]+.25*SHRINK)/
                                (learner[segment_key(q,"ISI_YON")][0]+SHRINK)))
                            for q in subset),5)})
                # A test target has NOW been scored. Update calibration only
                # after writing every pre-target prediction and result.
                for q in snap:
                    key=segment_key(q,"ISI_YON")
                    learner[key][0]+=1
                    learner[key][1]+=int(q["sayi"] in target)
            # The true target is finally shown to the lifelong heat tracker.
            engine.append(day,pos,no,target)
            if progress and (total%100==0 or total==progress_denom):
                progress(total,progress_denom,"V40 altı ısı havuzu ve geçişleri",day)
        stream.flush();stream.detach()
      _write_rows(z,"02_HER_CEKILIS_6_HAVUZ_YON_DAGILIMI.csv",STEP_FIELDS,step_rows)
      aggr=_quality(aggregates)
      _write_rows(z,"03_SICAKLIK_YON_AILE_BANT_KALIS_SONUCLARI.csv",AGG_FIELDS,aggr)
      evalrows=[]
      comparisons={}
      for phase in ("EGITIM","TEST"):
        blocks={day:vals for (p,day),vals in daily.items() if p==phase}
        t=[sum(v[i] for v in blocks.values()) for i in range(5)]
        if t[4]==0:continue
        perday_diff={day:((v[0]-v[1]),v[4]) for day,v in blocks.items()}
        conf=_bootstrap(list(perday_diff),perday_diff)
        model_b=t[0]/t[4];base_b=t[1]/t[4]
        model_l=t[2]/t[4];base_l=t[3]/t[4]
        evalrows.append({"donem":phase,"hedef_cekilis":t[4]//80,
            "sayisal_test_firsati":t[4],"rng_25_brier":round(base_b,8),
            "model_brier":round(model_b,8),"model_eksi_rng_brier":round(model_b-base_b,8),
            "rng_25_logloss":round(base_l,8),
            "model_logloss":round(model_l,8),
            "model_eksi_rng_logloss":round(model_l-base_l,8),
            "gun_blok_bootstrap_95_brier_fark":json.dumps(conf),
            "gun_sayisi":len(blocks),
            "model_rastgeleye_ustunlugu_kanitlandi":"HAYIR (ayri gelecekte dogrulama gerekir)"})
        comparisons[phase]={"days":len(blocks),"draws":t[4]//80,
            "model_brier":round(model_b,8),"rng_brier":round(base_b,8),
            "difference":round(model_b-base_b,8),"day_bootstrap_95":conf}
      _write_rows(z,"04_ILK36_SON36_ILERI_OLASILIK_TESTI.csv",EVAL_FIELDS,evalrows)
      count_rows=sorted(learner.items(),key=lambda x:str(x[0]))
      _write_rows(z,"05_CALIBRATION_T_ONCESI_SONUCLAR.csv",
         ("motor","havuz","yon","alt_boyut1","alt_boyut2","alt_boyut3",
          "gecmis_gozlem","gecmis_hedef20","kalibre_yuzde"),
         ({"motor":k[0],"havuz":k[1],"yon":k[2],"alt_boyut1":k[3],
           "alt_boyut2":k[4],"alt_boyut3":k[5],"gecmis_gozlem":v[0],
           "gecmis_hedef20":v[1],
           "kalibre_yuzde":round(100*(v[1]+.25*SHRINK)/(v[0]+SHRINK),5)}
          for k,v in count_rows))
      meta={"version":ENGINE,"source_days":len(days),
            "source_full_days":len(full),"draws_read":total,
            "draws_with_prior_character":n_targets,
            "number_steps":n_targets*80,
            "tested_brier":comparisons,
            "seat_capacity":dict(zip(SIX,SIZES)),
            "reference_per_number":.25,
            "pretarget_seat_direction":True,
            "pretarget_family_band":True,
            "no_future_target_as_feature":True,
            "online_calibration_after_target_only":True,
            "data_warnings":warnings,
            "statistical_warning":"No hidden RNG state recovered. Grouping past outcomes cannot itself establish future predictive advantage. Clustering and multiple subgroup selection can produce false positives."}
      z.writestr("06_OZET_VE_KAYNAK.json",json.dumps(meta,ensure_ascii=False,indent=2).encode())
      z.writestr("00_KULLANIM_VE_DELIL_KURALLARI.txt",(
        "V40 ALT I SICAKLIK HAVUZU / 80 SAYI YASAMINA BAGLI ANALIZ\n"
        "========================================================\n"
        "1) Hedef D_t henuz okunmadan, t-1 ve onceki gercek c ekilislerden\n"
        "   her sayinin sicaklik havuzu, yonu, kalis ve aile/bant isaretleri\n"
        "   hesaplanir. Sicak havuz SOGUK..SICAK 13/13/14/14/13/13.\n"
        "2) Bundan sonra gercek hedef 20 ile karsilastirilir; grup isabeti\n"
        "   ve cikan oranlar kaydedilir. HER BIR SAYI icin rastgele oran %25.\n"
        "3) Ancak sonrasinda online havuz olasilik akordu guncellenir.\n"
        "4) Gunun sonundan ertesi gune isi belleği surer; gunluk aile\n"
        "   penceresi sifirlanir. 01:02 -> 07:02 sahte draw eklenmez.\n"
        "5) Deneme gunleri kronolojik ilk/son yarida karsilastirilir.\n"
        "6) Brier kucukse daha iyi; gune gore bootstrap belirsizligi raporda.\n"
        "7) 80 sayinin hicbiri havuz disinda kalmaz. 6 havuz her adim 80.\n"
        "8) Bu tahmin edilen 20 listesinin testinden FARKLIDIR; 6 havuzun\n"
        "   gercek sonraki 20'ye karakter bazli katkisini arastirir.\n"
        "9) Co-occurrence family metrics are historical overlap screening,\n"
        "   not proof of distinct family episodes, hidden RNG or causality.\n"
        "10) 207 dal baglandi veya 16/20 basari saglandi denmiyor.\n"
      ).encode("utf-8-sig"))
    assert zipfile.ZipFile(io.BytesIO(zip_buffer.getvalue())).testzip() is None
    return zip_buffer.getvalue(),meta,evalrows,aggr


def from_text(text,include_partial=False,progress=None):
    from v11_arastirma import read_draws
    draws,parsing=read_draws(text)
    result=study(draws,include_partial,progress)
    result[1]["source_text_warning_count"]=len(parsing)
    return result
