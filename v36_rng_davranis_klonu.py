# -*- coding: utf-8 -*-
"""V36 draw-by-draw observable RNG behavior emulator and calibration laboratory.

Not a clone of the secret PRNG or its state. A self-updating *statistical*
replica generates 20 unique balls without replacement; all learning is online:
generate from t-1 state, score against draw t, update, then read t states.
Generates a complete per-motor numbered entry/exit audit and one ZIP.
Pure Python 3.10+. No external dependencies.
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
from datetime import datetime

BALLS=tuple(range(1,81))
SIX=("SOGUK","SOGUGA_YAKIN","ORTA","ILIK","SICAGA_YAKIN","SICAK")
SIZE=(13,13,14,14,13,13)
DECAY=0.5**(1/12)
PRIOR=160.0
CLIP=1.3
BRANCHES=("ISI","YON","BEKLEME","11LI","BANT","YARIM","TEKRAR",
          "AYNA","DONGU","AILE2","AILE3","AILE4","ILK6_SON5")
MOTOR_GROUPS=("HAVUZ20","HAVUZ60","ISI","YON","BEKLEME","11LI",
              "BANT","YARIM","TEKRAR","AYNA","DONGU","AILE2","AILE3","AILE4","IMZA11")
NUM_FIELDS=("gun","sira","cekilis_no","sayi","gercek20","klon20",
            "onceki_isi","isi","isi_yonu","bekleme","11de","11li_imza",
            "bant","yarim","onceki20","ayna20","dongude_goruldu",
            "aile2","aile3","aile4","bekleme_sinifi","son6_ilk5_yon")
STEP_FIELDS=("gun","sira","cekilis_no","saat","donem","gercek20",
             "klon20","gercek_durum20","klon_durum20","rastgele20",
             "klon_ortak_sayi","durum_ortak_sayi","rastgele_ortak_sayi",
             "gercek_tekrar","klon_tekrar","gercek_6plus_bekleyen",
             "klon_6plus_bekleyen","gercek_11de6plus","klon_11de6plus",
             "gercek_bantlar","klon_bantlar","bant_mutlak_fark","kalibrasyon_olay",
             "kaynak_eksikligi")
HAZNE_FIELDS=("gun","sira","cekilis_no","kol","motor","hazne","haznede",
              "giren","cikan","doluluk","giren_adet","cikan_adet")
CAL_FIELDS=("motor","hazne","gozlem","sonraki_20de_cikti","sonraki_isabet_yuzde",
            "yumusatilmis_oran","rng_referans_yuzde")
FAMILY_FIELDS=("gun","sira","cekilis_no","ikili_yeniden_birlesen_sayi",
               "uclu_yeniden_birlesen_sayi","dortlu_ustuste_birlesen_sayi",
               "tekrar_2li","tekrar_3lu","tekrar_4lu")
CSV_OPTIONS=dict(delimiter=";",lineterminator="\n")


def pclass(k):
    if k>=11:return "11+"
    if k>=6:return str(k)
    if k>=4:return "4-5"
    if k>=1:return "1-3"
    return "0"


def fclass(x):
    if x>=6:return "6+"
    return str(x)


def parts(x):
    return ",".join(str(n) for n in sorted(x))


def simple_csv(z,filename,rows,fields):
    with z.open(filename,"w") as raw:
        wrapper=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
        w=csv.DictWriter(wrapper,fieldnames=fields,**CSV_OPTIONS,extrasaction="ignore")
        w.writeheader()
        for row in rows:w.writerow(row)
        wrapper.flush()
        wrapper.detach()


def file_writer(z,filename,fields):
    raw=z.open(filename,"w")
    wrapper=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
    writer=csv.DictWriter(wrapper,fieldnames=fields,**CSV_OPTIONS,extrasaction="ignore")
    writer.writeheader()
    return raw,wrapper,writer


def close_writer(raw,wrapper):
    wrapper.flush()
    wrapper.detach()
    raw.close()


def seed_for(day,pos,kind):
    return int(hashlib.sha256(f"V36|{day}|{pos}|{kind}|20261014".encode()).hexdigest()[:16],16)


def weighted20(weights,rng):
    # Efraimidis-Spirakis, no duplicates. weights >0.
    keys=[(-math.log(max(rng.random(),1e-15))/max(w,0.000001),n)
          for n,w in zip(BALLS,weights)]
    keys.sort()
    return set(n for _,n in keys[:20])


def momentum(bits):
    # last 5 / preceding 6, scale properly
    recent=(bits & 31).bit_count()
    older=(bits>>5).bit_count()
    x=recent*6-older*5
    return "ARTIYOR" if x>0 else "AZALIYOR" if x<0 else "DENGELI"


def allowed(m):
    if not (len(m)==20 and len(set(m))==20 and all(n in BALLS for n in m)):
        raise ValueError("Her çekiliş 1..80 arası benzersiz 20 sayı içermeli.")
    return set(m)


def on_slot(p):
    if not 1<=p<=217:raise ValueError("Sıra 1..217 olmalı")
    mins=2+5*(p-1) if p<=13 else 422+5*(p-14)
    return f"{mins//60:02d}:{mins%60:02d}"


def sorted_draws(draws,include_partial=False):
    valid=defaultdict(dict)
    errors=[]
    seen_id=set()
    for d in sorted(draws,key=lambda d:(str(d.get("day","")),int(d.get("pos",0)))):
        try:
            day=str(d["day"]);pos=int(d["pos"]);no=int(d["no"])
            _=datetime.strptime(day,"%Y-%m-%d")
            if not 1<=pos<=217:raise ValueError("geçersiz sıra")
            nums=allowed(d["nums"])
            if (day,pos) in {(day,k) for k in valid[day]}:raise ValueError("çakışan gün/sıra")
            if no in seen_id:raise ValueError("tekrar çekiliş numarası")
            seen_id.add(no)
            valid[day][pos]={"day":day,"pos":pos,"no":no,"nums":nums}
        except Exception as e:errors.append(f"{d.get('day')} / {d.get('pos')}: {e}")
    full={day for day,slots in valid.items() if set(slots)==set(range(1,218))}
    chosen=sorted(valid) if include_partial else sorted(full)
    if not chosen:raise ValueError("Tam gün yok; eksik gün dahil et veya daha fazla çekiliş gir.")
    return [(day,[valid[day][p] for p in sorted(valid[day])]) for day in chosen],full,errors


class State:
    """Independent reservoirs, rolling family memories and V32 cycle for one arm."""
    def __init__(self):
        self.day=None
        self.pos=None
        self.heat=[0.0]*81
        self.heat_label=["SOGUK"]*81
        self.previous_heat=["SOGUK"]*81
        self.wait=[0]*81
        self.bits=[0]*81
        self.consec=[0]*81
        self.family=deque(maxlen=12)
        self.pairs=Counter()
        self.triples=Counter()
        self.last=None
        self.seen_cycle=set()
        self.cycle_id=1
        self.valid_run=0
        self.member2=set()
        self.member3=set()
        self.member4=set()
        self.f2=0
        self.f3=0
        self.f4=0

    def reset(self,day,pos):
        self.day=day
        self.pos=None
        self.wait=[0]*81;self.bits=[0]*81;self.consec=[0]*81
        self.family=deque(maxlen=12);self.pairs=Counter();self.triples=Counter()
        self.last=None;self.seen_cycle=set();self.cycle_id=1
        self.valid_run=0
        self.member2=set();self.member3=set();self.member4=set()
        self.f2=self.f3=self.f4=0

    def ensure_day(self,day,pos):
        if day!=self.day:
            self.reset(day,pos)
        elif self.pos is not None and pos!=self.pos+1:
            self.reset(day,pos)
        # Keep EWMA heat over all days; no fake zeros in 01:02/07:02 break.

    def family_update(self,s):
        # Pair/triple families: exact coappearances in rolling 12 actual draws.
        # Quartet engine: every four in intersection with immediately preceding draw.
        m2=set();m3=set();m4=set()
        num2=num3=num4=0
        for c in combinations(sorted(s),2):
            if self.pairs[c]>=2:
                num2+=1;m2.update(c)
        for c in combinations(sorted(s),3):
            if self.triples[c]>=2:
                num3+=1;m3.update(c)
        if self.last is not None:
            inter=sorted(s & self.last)
            if len(inter)>=4:
                num4=math.comb(len(inter),4)
                m4.update(inter)
        self.member2=m2;self.member3=m3;self.member4=m4
        self.f2=num2;self.f3=num3;self.f4=num4
        if len(self.family)==12:
            old=self.family.popleft()
            for c in combinations(sorted(old),2):
                self.pairs[c]-=1
                if self.pairs[c]==0:del self.pairs[c]
            for c in combinations(sorted(old),3):
                self.triples[c]-=1
                if self.triples[c]==0:del self.triples[c]
        for c in combinations(sorted(s),2):self.pairs[c]+=1
        for c in combinations(sorted(s),3):self.triples[c]+=1
        self.family.append(s)

    def advance(self,day,pos,nums):
        self.ensure_day(day,pos)
        s=allowed(nums)
        self.family_update(s)
        self.previous_heat=self.heat_label[:]
        for n in BALLS:
            hit=int(n in s)
            self.wait[n]=0 if hit else self.wait[n]+1
            self.consec[n]=self.consec[n]+1 if hit else 0
            self.bits[n]=((self.bits[n]<<1)|hit)&2047
            self.heat[n]=self.heat[n]*DECAY+hit
        ranks=sorted(BALLS,key=lambda x:(self.heat[x],x))
        labels=[""]*81
        k=0
        for i,size in enumerate(SIZE):
            for n in ranks[k:k+size]:labels[n]=SIX[i]
            k+=size
        self.heat_label=labels
        self.seen_cycle.update(s)
        self.pos=pos;self.last=s
        self.valid_run+=1
        # At 80/80 cycle closure reset after we saved this draw's state.
        cycle_end=len(self.seen_cycle)==80
        snaps=self.snapshot()
        if cycle_end:
            self.seen_cycle=set();self.cycle_id+=1
        return snaps,cycle_end

    def snapshot(self):
        ans={}
        for n in BALLS:
            bit=self.bits[n]
            after=SIX.index(self.heat_label[n])
            before=SIX.index(self.previous_heat[n])
            direction=("YUKSELIS" if after>before else "DUSUS" if after<before else "SABIT")
            seen=n in self.seen_cycle
            ans[n]={
                "ISI":self.heat_label[n],
                "YON":direction,
                "ISI_GECIS":self.previous_heat[n]+"->"+self.heat_label[n],
                "BEKLEME":pclass(self.wait[n]),
                "11LI":fclass(bit.bit_count()) if self.valid_run>=11 else "EKSIK",
                "IMZA11":format(bit,"011b") if self.valid_run>=11 else "EKSIK",
                "ILK6_SON5":momentum(bit) if self.valid_run>=11 else "EKSIK",
                "BANT":f"{(n-1)//10*10+1:02d}-{(n-1)//10*10+10:02d}",
                "YARIM":"ALT40" if n<=40 else "UST40",
                "TEKRAR":"ONCEKI20" if self.last and n in self.last else "ONCEKI60",
                "AYNA":"AYNA_ONCEKI20" if self.last and (81-n) in self.last else "AYNA_ONCEKI60",
                "DONGU":"DONGUDE_GORULDU" if seen else "DONGUDE_HENUZ",
                "AILE2":"AKTIF" if n in self.member2 else "PASIF",
                "AILE3":"AKTIF" if n in self.member3 else "PASIF",
                "AILE4":"AKTIF" if n in self.member4 else "PASIF",
                "gercek20":int(bool(self.last and n in self.last)),
                "bekleme":self.wait[n],
                "11de":bit.bit_count(),
            }
        return ans


def reservoirs(snap):
    out=defaultdict(set)
    for n,a in snap.items():
        out["HAVUZ20" if a["gercek20"] else "HAVUZ60","ICINDE"].add(n)
        for motor in ("ISI","YON","BEKLEME","11LI","BANT","YARIM","TEKRAR",
                      "AYNA","DONGU","AILE2","AILE3","AILE4"):
            out[motor,a[motor]].add(n)
        out["YON",a["ISI_GECIS"]].add(n)
        if a["IMZA11"]!="EKSIK":
            out["IMZA11",a["IMZA11"]].add(n)
    return out


class Learner:
    def __init__(self):
        self.count=defaultdict(lambda:[0,0])
        self.updates=0
    def learn(self,features,observed):
        for n,row in features.items():
            hit=int(n in observed)
            for branch in BRANCHES:
                key=(branch,row[branch])
                self.count[key][0]+=1;self.count[key][1]+=hit
        self.updates+=1
    def weights(self,features):
        weights=[]
        for n,row in features.items():
            score=0.0
            for branch in BRANCHES:
                cnt,hits=self.count[(branch,row[branch])]
                if cnt<30:continue
                post=(hits+PRIOR*.25)/(cnt+PRIOR)
                # Restrained contribution; 13 motor branches do not
                # independently justify multiplying unbounded likelihoods.
                score+=0.22*(post-.25)/.25
            score=max(-CLIP,min(CLIP,score))
            weights.append(math.exp(score))
        return weights
    def report(self):
        ans=[]
        for (m,lab),(cnt,hits) in sorted(self.count.items()):
            ans.append({"motor":m,"hazne":lab,"gozlem":cnt,
                       "sonraki_20de_cikti":hits,
                       "sonraki_isabet_yuzde":round(100*hits/cnt,4),
                       "yumusatilmis_oran":round(100*(hits+PRIOR*.25)/(cnt+PRIOR),4),
                       "rng_referans_yuzde":25})
        return ans


def run(draws,include_partial=False,progress=None):
    days,full,errors=sorted_draws(draws,include_partial)
    cutoff=days[len(days)//2][0]
    real=State();clone=State();cal=Learner()
    steps=[];hazne_prev={"GERCEK":{},"KLON":{}}
    day_stats=defaultdict(lambda:Counter())
    transitions=Counter()
    motor_global=Counter()
    family_events=[]
    cycle=[]
    num_events=0
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
      raw_n,wrap_n,wn=file_writer(z,"01_80_SAYI_HER_ADIM_KARAKTER.csv",NUM_FIELDS)
      raw_h,wrap_h,wh=file_writer(z,"02_HER_MOTOR_HAZNE_GIRIS_CIKIS.csv",HAZNE_FIELDS)
      raw_s,wrap_s,ws=file_writer(z,"03_HER_CEKILIS_GERCEK_KLON_KARSILASTIRMA.csv",STEP_FIELDS)
      try:
       for day_index,(day,group) in enumerate(days):
        phase="EGITIM" if day<cutoff else "TEST"
        old_s=None;old_m=None
        for d in group:
            pos=d["pos"];winning=d["nums"];no=d["no"]
            # A missing real slot breaks each arm's rolling memory.
            real.ensure_day(day,pos)
            clone.ensure_day(day,pos)
            if old_s is not None and pos!=old_s+1:old_m=None
            before=real.snapshot() if real.pos is not None else None
            # REAL-state conditional replica forecasts; generated BEFORE
            # draw t is read. Distinct from the autonomous clone arm.
            weights=cal.weights(before) if before else [1.]*80
            conditioned=weighted20(weights,random.Random(seed_for(day,pos,"DURUM")))
            # Autonomous digital twin uses its own earlier outputs as state.
            cloned_before=clone.snapshot() if clone.pos is not None else None
            cloned_weights=cal.weights(cloned_before) if cloned_before else [1.]*80
            generated=weighted20(cloned_weights,random.Random(seed_for(day,pos,"KLON")))
            baseline=set(random.Random(seed_for(day,pos,"RNG")).sample(BALLS,20))
            for arm,nums,inst in (("GERCEK",winning,real),("KLON",generated,clone)):
                snap,finished=inst.advance(day,pos,nums)
                h=reservoirs(snap)
                old=hazne_prev[arm] if old_s is not None and pos==old_s+1 else {}
                for motor,key in sorted(set(h)|set(old)):
                    if motor not in MOTOR_GROUPS:continue
                    inside=h.get((motor,key),set())
                    former=old.get((motor,key),set())
                    entering=inside-former;leaving=former-inside
                    wh.writerow({"gun":day,"sira":pos,"cekilis_no":no,
                        "kol":arm,"motor":motor,"hazne":key,"haznede":parts(inside),
                        "giren":parts(entering),"cikan":parts(leaving),
                        "doluluk":len(inside),"giren_adet":len(entering),
                        "cikan_adet":len(leaving)})
                    if arm=="GERCEK":
                        motor_global[("entered",motor,key)]+=len(entering)
                        motor_global[("left",motor,key)]+=len(leaving)
                hazne_prev[arm]=h
                if finished:cycle.append({"gun":day,"sira":pos,"cekilis_no":no,
                    "kol":arm,"80_80_dongu_tamamlandi":1,"dongu_no":inst.cycle_id-1})
                if arm=="GERCEK":real_snap=snap
                else:clone_snap=snap
            for n in BALLS:
                a=real_snap[n]
                before_heat=real.previous_heat[n]
                wn.writerow({"gun":day,"sira":pos,"cekilis_no":no,
                    "sayi":n,"gercek20":int(n in winning),"klon20":int(n in generated),
                    "onceki_isi":before_heat,"isi":a["ISI"],"isi_yonu":a["YON"],
                    "bekleme":a["bekleme"],"11de":a["11de"],"11li_imza":a["IMZA11"],
                    "bant":a["BANT"],"yarim":a["YARIM"],
                    "onceki20":a["TEKRAR"],"ayna20":a["AYNA"],
                    "dongude_goruldu":a["DONGU"],"aile2":a["AILE2"],
                    "aile3":a["AILE3"],"aile4":a["AILE4"],
                    "bekleme_sinifi":a["BEKLEME"],"son6_ilk5_yon":a["ILK6_SON5"]})
                num_events+=1
            if before is not None:
                cal.learn(before,winning)
                for n in BALLS:
                    key=(before[n]["ISI"],real_snap[n]["ISI"])
                    transitions[("ISI",)+key]+=1
                    transitions[("YON",before[n]["YON"],real_snap[n]["YON"])]+=1
                    transitions[("BEKLEME",before[n]["BEKLEME"],real_snap[n]["BEKLEME"])]+=1
            counts=lambda snap:sum(v["BEKLEME"] in ("6","7","8","9","10","11+") for v in snap.values())
            hot=lambda snap:sum(v["11de"]>=6 for v in snap.values() if v["IMZA11"]!="EKSIK")
            bandcount=lambda s:[len([n for n in s if (n-1)//10==b]) for b in range(8)]
            rb=bandcount(winning);cb=bandcount(generated)
            row={"gun":day,"sira":pos,"cekilis_no":no,"saat":on_slot(pos),
                "donem":phase,"gercek20":parts(winning),"klon20":parts(generated),
                "gercek_durum20":parts(conditioned),"klon_durum20":parts(generated),
                "rastgele20":parts(baseline),
                "klon_ortak_sayi":len(winning&generated),
                "durum_ortak_sayi":len(winning&conditioned),
                "rastgele_ortak_sayi":len(winning&baseline),
                "gercek_tekrar":len(winning&old_m) if old_m is not None else "",
                "klon_tekrar":len(generated&clone_previous) if (old_m is not None and clone_previous is not None) else "",
                "gercek_6plus_bekleyen":counts(real_snap),
                "klon_6plus_bekleyen":counts(clone_snap),
                "gercek_11de6plus":hot(real_snap),"klon_11de6plus":hot(clone_snap),
                "gercek_bantlar":",".join(map(str,rb)),
                "klon_bantlar":",".join(map(str,cb)),
                "bant_mutlak_fark":sum(abs(a-b) for a,b in zip(rb,cb)),
                "kalibrasyon_olay":cal.updates,
                "kaynak_eksikligi":int(old_m is None)}
            ws.writerow(row)
            steps.append({k:row[k] for k in ("gun","sira","donem","klon_ortak_sayi",
                       "durum_ortak_sayi","rastgele_ortak_sayi",
                       "bant_mutlak_fark","gercek_6plus_bekleyen",
                       "klon_6plus_bekleyen","gercek_11de6plus","klon_11de6plus")})
            day_stats[day]["cekilis"]+=1
            for metric in ("klon_ortak_sayi","durum_ortak_sayi","rastgele_ortak_sayi",
                           "bant_mutlak_fark","gercek_6plus_bekleyen",
                           "klon_6plus_bekleyen","gercek_11de6plus","klon_11de6plus"):
                day_stats[day][metric]+=row[metric]
            family_events.append({"gun":day,"sira":pos,"cekilis_no":no,
                "ikili_yeniden_birlesen_sayi":parts(real.member2),
                "uclu_yeniden_birlesen_sayi":parts(real.member3),
                "dortlu_ustuste_birlesen_sayi":parts(real.member4),
                "tekrar_2li":real.f2,"tekrar_3lu":real.f3,"tekrar_4lu":real.f4})
            old_s=pos;old_m=winning;clone_previous=generated
        if progress:progress(day_index+1,len(days),"V36 çekiliş çekiliş klon hazneleri",day)
      finally:
        for tup in [(raw_n,wrap_n),(raw_h,wrap_h),(raw_s,wrap_s)]:
            close_writer(*tup)
      calrows=cal.report()
      simple_csv(z,"04_KALIBRASYON_HER_UZMAN_HAZNESI.csv",calrows,CAL_FIELDS)
      dayrows=[]
      for day,v in sorted(day_stats.items()):
        n=v["cekilis"]
        rr={"gun":day,"donem":"EGITIM" if day<cutoff else "TEST",
            "cekilis":n}
        for k in ("klon_ortak_sayi","durum_ortak_sayi","rastgele_ortak_sayi",
                   "bant_mutlak_fark","gercek_6plus_bekleyen","klon_6plus_bekleyen",
                   "gercek_11de6plus","klon_11de6plus"):
            rr["ortalama_"+k]=round(v[k]/n,5)
        dayrows.append(rr)
      simple_csv(z,"05_GUNLUK_KLON_AKORT_KONTROLU.csv",dayrows,list(dayrows[0]))
      changes=[{"motor":m,"eski_hazne":x,"yeni_hazne":y,"sayi_gecisi":count}
               for (m,x,y),count in sorted(transitions.items())]
      simple_csv(z,"06_MOTORLAR_ARASI_GECIS_TAM.csv",changes,
                 ("motor","eski_hazne","yeni_hazne","sayi_gecisi"))
      simple_csv(z,"07_AILE_2_3_4_ADIM_ADIM.csv",family_events,FAMILY_FIELDS)
      simple_csv(z,"08_80_80_TAMAMLANMA_KAYITLARI.csv",cycle,
                 ("gun","sira","cekilis_no","kol","80_80_dongu_tamamlandi","dongu_no"))
      motor_counts=[{"yon":x,"motor":m,"hazne":k,"toplam_sayi_hareketi":v}
                    for (x,m,k),v in sorted(motor_global.items())]
      simple_csv(z,"09_UZMAN_MOTOR_GIRIS_CIKIS_TOPLAMLARI.csv",motor_counts,
                 ("yon","motor","hazne","toplam_sayi_hareketi"))
      def phase_stats(phase):
          x=[v for v in steps if v["donem"]==phase]
          out={"gercek_cekilis":len(x)}
          for metric in ("klon_ortak_sayi","durum_ortak_sayi","rastgele_ortak_sayi",
                         "bant_mutlak_fark","gercek_6plus_bekleyen",
                         "klon_6plus_bekleyen","gercek_11de6plus","klon_11de6plus"):
              out["ortalama_"+metric]=round(statistics.mean(r[metric] for r in x),5) if x else None
          return out
      meta={"versiyon":"V36_DAVRANIS_KLONU","tam_gun":len(set(day for day,_ in days)&full),
          "incelenen_gun":len(days),"cekilis":len(steps),"80_sayi_kaydi":num_events,
          "online_kalibrasyon_olayi":cal.updates,"egitim_test_siniri":cutoff,
          "motor_gruplari":list(MOTOR_GROUPS),"kalibrasyon_dallari":list(BRANCHES),
          "motor_alt_hazne_sayisi":len({(m,k) for (_,m,k) in motor_global}),
          "kalibrasyon_hazneleri":len(cal.count),"kaynak_uyarisi":errors,
          "egitim":phase_stats("EGITIM"),"test":phase_stats("TEST"),
          "beklenen_rastgele_20_ortak_sayi":5,
          "not":"Bu gizli RNG'yi, tohumunu veya algoritmasını klonlamaz. Gerçek veriyle sürekli yeniden ayarlanan istatistiksel davranış emülatörüdür. İleri sonuçlar önceden bilinmez."}
      z.writestr("10_OZET.json",json.dumps(meta,ensure_ascii=False,indent=2).encode())
      readme=("V36 - RNG DAVRANIS KLONU / HER GERCEK CEKILIS\n"
        "==============================================\n"
        "GERCEK KOL: 80 sayinin her cekilisten sonra 20/60, 6 isi, yukselis/dusus,\n"
        "bekleme, 11'li imza, 8 bant, 40/40, tekrar, simetri, V32 80/80 dongu,\n"
        "ikili/uclu/dortlu aile gruplari ayri motorlara girer ve cikar.\n"
        "KLON KOL: kendi urettigi 20 sayiyi bir sonraki kendi durumu yapmak suretiyle\n"
        "GERCEK KOLDAN BAGIMSIZ bir dijital ikiz yapar.\n"
        "DURUMA GORE KLON: gercek son durumundan gecmis online hazne akortlariyla\n"
        "gelecek icin 20 benzersiz sayi uretir; gercek cekiliste kac ortak test edilir.\n"
        "RNG KONTROL: ayni zamanda bagimsiz es olasilikli 20 sayi secimi.\n"
        "Once sonuc bilinmeden klon/olasilik hazirlanir, sonra gercek cekilis\n"
        "gelince once test, sonra 13 ayri uzmanin istatistigi yenilenir.\n"
        "Gun 00:02'de aile, 11'li pencere, bekleme ve V32 yeniden baslar; isi hafizasi\n"
        "uzun vadede korunur. 01:02-07:02 boslugu gercekten cekilis olmadigi icin\n"
        "sahte sayi eklenmez. Eksik pozisyonlar seri pencereleri sifirlar.\n"
        "Tum olasiliklar gecmise gore ogrenilir; farkli bir algoritma kazanma\n"
        "garantisi vermez. Kaynak: repo veri.txt; her yeniden calismada deterministik\n"
        "gecmis tekrar oynatilir. ZIP kalicidir; Streamlit oturumu kalici DB degildir.\n"
        "Ilk ve ikinci 36 gun kesif/test etiketidir. TEST sirasinda da sistem\n"
        "gercek cekilis geldikten SONRA ogrenmeye devam eder: uyarlamali ileri test.\n"
        "Motor sayisi isim degil: bireysel hazne / giren / cikan satirlari gercekten\n"
        "02 nolu dosyada her cekilis icin ayridir. Kupon kazanci iddiasi yoktur.\n"
        f"Kisa ozet: {json.dumps(meta,ensure_ascii=False,indent=2)}")
      z.writestr("00_KULLANIM_TASARIM_VE_KURALLAR.txt",readme.encode("utf-8-sig"))
    return archive.getvalue(),meta,dayrows,calrows,motor_counts


def run_from_txt(txt,include_partial=False,progress=None):
    from v11_arastirma import read_draws
    parsed,bad=read_draws(txt)
    blob,meta,dayrows,calrows,motor_counts=run(parsed,include_partial,progress)
    meta["ham_satir_uyarilari"]=len(bad)
    return blob,meta,dayrows,calrows,motor_counts
