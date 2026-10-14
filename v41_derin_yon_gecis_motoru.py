# -*- coding: utf-8 -*-
"""V41 — Hız, ivme, dönüş, kalış ve aile yönlerinin ileri yürüyen testi.

One immutable real drawing at a time: features and 20 number tickets are
produced STRICTLY from preceding actual draws. Only after those tickets are
frozen may the current 20-number result score them; states are then updated.
Primary pre-registered comparison: online direction fusion versus random20,
with day-block paired uncertainty. Older V39 composite is a secondary control.
Multiple subgroup results are exploratory, not claimed as causal RNG keys.
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
from collections import Counter, defaultdict
from pathlib import Path

from v36_rng_davranis_klonu import sorted_draws, on_slot
from v40_alti_isi_yon_havuzlari import PreDraw,SIX
from v39_onceden_dondurulmus_uzman_paneli import OnlinePanel

VERSION="V41.1"
N=80
SHRINK=200
STRATEGIES=("YON_HIZ","YON_DEVAM","YON_IVME","YON_AILE","YON_BANT")
ENSEMBLE="YON_BIRLESIM_ONLINE"
FROZEN="YON_BIRLESIM_SABIT"
CONTROL_V39="V39_ESKI_PANEL"
CONTROL_RNG="RASTGELE_20"
ALL_METHODS=STRATEGIES+(ENSEMBLE,FROZEN,CONTROL_V39,CONTROL_RNG)
WEIGHTS=(.25,.25,.20,.20,.10)
assert len(STRATEGIES)==len(WEIGHTS) and abs(sum(WEIGHTS)-1)<1e-10
CSV_KW=dict(delimiter=";",lineterminator="\n")
DRAW_FIELDS=("gun","sira","cekilis_no","saat","donem","motor","onceden_donduruldu",
             "hedef_onceki_cekilis_no","secilen_20","gercek_20","isabet",
             "isabet_sayilari","motor_surumu")
CHAR_FIELDS=("gun","sira","cekilis_no","sayi","havuz","onceki_havuz",
    "yon","onceki_yon","yon_epizodu","hiz","isi_egimi","ivme",
    "kalis","kalis_sinifi","aile_gucu","aile_yon_esligi",
    "bant_baski","bekleme","son6","son11",
    "yon_teknik_p","yon_devam_p","yon_ivme_p","yon_aile_p",
    "yon_bant_p","birlesim_online_p","birlesim_sabit_p","gercek20")
GROUP_FIELDS=("donem","boyut","sinif","gozlenen_sayi_adim","cikan20",
    "oran_yuzde","adil_rng_oran_yuzde","gercek_eksi_beklenen",
    "not")
EVAL_FIELDS=("donem","motor","cekilis","ortalama_isabet","en_yuksek_isabet",
    "isabet_8_ve_ustu","isabet_10_ve_ustu","isabet_12_ve_ustu",
    "isabet_14_ve_ustu","isabet_16_ve_ustu","isabet_0_20_dagilimi")
B_FIELDS=("donem","denenen_cekilis","sayi_adim","model_brier",
    "rng_brier","model_eksi_rng_brier","gun_blok_95_aralik",
    "gun_sayisi")


def class_momentum(now,prior):
    if now=="YENI":return "YENI"
    if now=="SABIT":return "FREN" if prior in ("YUKSELIS","DUSUS") else "DURAGAN"
    if prior==now:return "IKI_KEZ_"+now
    if prior in ("YUKSELIS","DUSUS"):return "TERS_"+now
    return "YENI_"+now


def class_velocity(before,now):
    if before not in SIX:return "YENI"
    delta=abs(SIX.index(now)-SIX.index(before))
    return "0" if delta==0 else "1" if delta==1 else "2PLUS"


def class_acceleration(delta,prior_delta):
    if abs(delta)<1e-8:return "DURAGAN"
    if prior_delta is None:return "ILK_EGIM"
    if delta*prior_delta<0:return "TERS"
    change=abs(delta)-abs(prior_delta)
    if change>0.002:return "HIZLANIYOR"
    if change<-.002:return "YAVASLIYOR"
    return "AYNI_HIZ"


def prepare(qs,previous_q,previous_delta,prior20):
    # q from V40.PreDraw.snapshot(day,pos), derived only from < target.
    prev=previous_q or {}
    anchor=frozenset(prior20 or ())
    group_dirs=Counter(q["yon"] for q in qs if q["sayi"] in anchor)
    result=[]
    for q in qs:
        n=q["sayi"]
        old=prev.get(n)
        prior_dir=old["yon"] if old else "YENI"
        mom=class_momentum(q["yon"],prior_dir)
        speed=class_velocity(q["onceki_havuz"],q["havuz"])
        delta=q["isi"]-old["isi"] if old else 0.
        accel=class_acceleration(delta,previous_delta.get(n))
        linked=max(0,group_dirs[q["yon"]]-int(n in anchor))
        alignment=("ESYON" if linked>=6 else "KISMI" if linked>=3 else "YOK")
        if q["aile"]=="YOK":alignment="AILESIZ"
        result.append({**q,"onceki_yon":prior_dir,
            "epizod":mom,"hiz":speed,"egim":delta,"ivme":accel,
            "eslik":alignment})
    assert len(result)==80 and len({q["sayi"] for q in result})==80
    next_delta={q["sayi"]:q["egim"] for q in result}
    return result,next_delta


def key(q,model):
    if model=="YON_HIZ":
        return (q["yon"],q["hiz"])
    if model=="YON_DEVAM":
        return (q["havuz"],q["epizod"],q["kalis_sinifi"])
    if model=="YON_IVME":
        return (q["yon"],q["ivme"])
    if model=="YON_AILE":
        return (q["epizod"],q["aile"],q["eslik"])
    if model=="YON_BANT":
        return (q["havuz"],q["yon"],q["bant_baski"])
    raise KeyError(model)


class Calibrator:
    def __init__(self):
        self.stats=defaultdict(lambda:[0,0])

    def prob(self,model,part):
        count,hit=self.stats.get((model,part),(0,0))
        return (hit+SHRINK*.25)/(count+SHRINK)

    def probabilities(self,qs):
        return {m:[self.prob(m,key(q,m)) for q in qs] for m in STRATEGIES}

    def observe(self,qs,target):
        for q in qs:
            hit=int(q["sayi"] in target)
            for m in STRATEGIES:
                k=(m,key(q,m))
                values=self.stats[k];values[0]+=1;values[1]+=hit

    def frozen_copy(self):
        other=Calibrator()
        for k,v in self.stats.items():other.stats[k]=list(v)
        return other


def fusion(probabilities):
    return [sum(w*probabilities[m][i] for w,m in zip(WEIGHTS,STRATEGIES))
            for i in range(80)]


def ticket(scores,day,pos,method):
    if len(scores)!=80:raise ValueError("80-score input required")
    rng=random.Random(int(hashlib.sha256(
      f"V41.1|{day}|{pos}|{method}".encode()).hexdigest()[:16],16))
    scores_and_numbers=[(float(score),rng.random(),n)
                         for n,score in enumerate(scores,1)]
    picks=sorted(scores_and_numbers,reverse=True)[:20]
    return frozenset(n for score,tie,n in picks)


def rng_ticket(day,pos):
    rng=random.Random(int(hashlib.sha256(
         f"V41.1|{day}|{pos}|CONTROL".encode()).hexdigest()[:16],16))
    return frozenset(rng.sample(range(1,81),20))


def display20(s):
    return ",".join(str(n) for n in sorted(s))


def write_csv(z,name,headers,rows):
    with z.open(name,"w") as target:
        file=io.TextIOWrapper(target,encoding="utf-8-sig",newline="",write_through=True)
        writer=csv.DictWriter(file,fieldnames=headers,extrasaction="ignore",**CSV_KW)
        writer.writeheader()
        for row in rows:writer.writerow(row)
        file.flush();file.detach()


def boot_days(items,reps=1400,seed=4102026):
    # Items are (paired summed hit differences, draw count); draws in
    # one calendar day are NOT independent bootstrap units.
    if not items:return None
    rng=random.Random(seed)
    values=[]
    for i in range(reps):
        chosen=[items[rng.randrange(len(items))] for _ in items]
        values.append(sum(d for d,n in chosen)/sum(n for d,n in chosen))
    values.sort()
    return [round(values[int(.025*(len(values)-1))],6),
            round(values[int(.975*(len(values)-1))],6)]


def _evaluation(ticket_rows):
    rows=[]
    for phase in ("EGITIM","TEST"):
      for method in ALL_METHODS:
        vals=[int(row["isabet"]) for row in ticket_rows
              if row["donem"]==phase and row["motor"]==method]
        if not vals:continue
        count=Counter(vals)
        rows.append({"donem":phase,"motor":method,"cekilis":len(vals),
          "ortalama_isabet":round(statistics.mean(vals),5),
          "en_yuksek_isabet":max(vals),
          "isabet_8_ve_ustu":sum(v>=8 for v in vals),
          "isabet_10_ve_ustu":sum(v>=10 for v in vals),
          "isabet_12_ve_ustu":sum(v>=12 for v in vals),
          "isabet_14_ve_ustu":sum(v>=14 for v in vals),
          "isabet_16_ve_ustu":sum(v>=16 for v in vals),
          "isabet_0_20_dagilimi":json.dumps([count.get(k,0) for k in range(21)])})
    return rows


def study(draws,include_partial=False,progress=None):
    days,full,errors=sorted_draws(draws,include_partial)
    cutoff=days[len(days)//2][0]
    heat=PreDraw()
    oldpanel=OnlinePanel()
    online=Calibrator()
    freeze=None
    previous_q={}
    prev_slope={}
    grouped=defaultdict(lambda:[0,0])
    perday=defaultdict(dict)
    risk=defaultdict(lambda:[0.,0.,0]) # directional Brier / constant .25 / n
    methods=[]
    observations=0
    all_real_draws=0
    zip_io=io.BytesIO()
    with zipfile.ZipFile(zip_io,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
      with z.open("01_CEKILIS_ONCESI_80_SAYI_YON_KARTLARI.csv","w") as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
        writer=csv.DictWriter(stream,fieldnames=CHAR_FIELDS,
               extrasaction="ignore",**CSV_KW)
        writer.writeheader()
        limit=sum(len(group) for _,group in days)
        for day,group in days:
          phase="EGITIM" if day<cutoff else "TEST"
          if phase=="TEST" and freeze is None:freeze=online.frozen_copy()
          for d in group:
            all_real_draws+=1
            pos=d["pos"];no=d["no"]
            last_draw=heat.last_no
            qs=heat.snapshot(day,pos)
            # The first true draw seeds lifelong heat, never itself predicted.
            if qs is None:
                heat.append(day,pos,no,d["nums"])
                oldpool,_=oldpanel.frozen(day,pos)
                oldpanel.score_and_learn(day,pos,no,d["nums"],oldpool)
                continue
            qs,next_slope=prepare(qs,previous_q,prev_slope,heat.prev)
            # ALL predictions created without reading target d["nums"].
            probs=online.probabilities(qs)
            frozen_probs=freeze.probabilities(qs) if freeze else probs
            fused=fusion(probs)
            fixed=fusion(frozen_probs)
            pools={m:ticket(probs[m],day,pos,m) for m in STRATEGIES}
            pools[ENSEMBLE]=ticket(fused,day,pos,ENSEMBLE)
            pools[FROZEN]=ticket(fixed,day,pos,FROZEN)
            oldpool,_=oldpanel.frozen(day,pos)
            pools[CONTROL_V39]=oldpool["DİYALOG_AGIRLIKLI"]
            pools[CONTROL_RNG]=rng_ticket(day,pos)
            assert len(pools)==len(ALL_METHODS)
            assert all(len(v)==20 for v in pools.values())
            # Now score every frozen method against the unseen until now target.
            target=frozenset(d["nums"])
            assert len(target)==20 and all(1<=n<=80 for n in target)
            scored={}
            for method,picks in pools.items():
                hits=target&picks
                scored[method]=len(hits)
                methods.append({"gun":day,"sira":pos,"cekilis_no":no,
                  "saat":on_slot(pos),"donem":phase,"motor":method,
                  "onceden_donduruldu":"EVET",
                  "hedef_onceki_cekilis_no":last_draw or "",
                  "secilen_20":display20(picks),"gercek_20":display20(target),
                  "isabet":len(hits),"isabet_sayilari":display20(hits),
                  "motor_surumu":VERSION})
            perday[(phase,day)][pos]=scored
            for i,q in enumerate(qs):
                hit=int(q["sayi"] in target)
                for name,category in (
                    ("HAVUZ",q["havuz"]),
                    ("YON",q["yon"]),
                    ("YON_DEVAM",q["epizod"]),
                    ("YON_HIZ",q["yon"]+"|"+q["hiz"]),
                    ("YON_IVME",q["yon"]+"|"+q["ivme"]),
                    ("YON_KALIS",q["yon"]+"|"+q["kalis_sinifi"]),
                    ("YON_AILE",q["epizod"]+"|"+q["aile"]),
                    ("YON_BANT",q["epizod"]+"|"+q["bant_baski"]),
                    ("AILE_ESYON",q["aile"]+"|"+q["eslik"]),
                ):
                    acc=grouped[(phase,name,category)]
                    acc[0]+=1;acc[1]+=hit
                p=fused[i]
                diff=risk[(phase,day)]
                diff[0]+=(p-hit)**2;diff[1]+=(.25-hit)**2;diff[2]+=1
                writer.writerow({"gun":day,"sira":pos,"cekilis_no":no,"sayi":q["sayi"],
                  "havuz":q["havuz"],"onceki_havuz":q["onceki_havuz"],
                  "yon":q["yon"],"onceki_yon":q["onceki_yon"],
                  "yon_epizodu":q["epizod"],"hiz":q["hiz"],
                  "isi_egimi":round(q["egim"],7),"ivme":q["ivme"],
                  "kalis":q["kalis"],"kalis_sinifi":q["kalis_sinifi"],
                  "aile_gucu":q["aile"],"aile_yon_esligi":q["eslik"],
                  "bant_baski":q["bant_baski"],"bekleme":q["bekleme"],
                  "son6":q["son6"],"son11":q["son11"],
                  "yon_teknik_p":round(probs["YON_HIZ"][i],7),
                  "yon_devam_p":round(probs["YON_DEVAM"][i],7),
                  "yon_ivme_p":round(probs["YON_IVME"][i],7),
                  "yon_aile_p":round(probs["YON_AILE"][i],7),
                  "yon_bant_p":round(probs["YON_BANT"][i],7),
                  "birlesim_online_p":round(p,7),
                  "birlesim_sabit_p":round(fixed[i],7),
                  "gercek20":hit})
            observations+=1
            # Only after scoring T do the T facts enter the experts.
            online.observe(qs,target)
            oldpanel.score_and_learn(day,pos,no,target,oldpool)
            heat.append(day,pos,no,target)
            previous_q={q["sayi"]:q for q in qs}
            prev_slope=next_slope
            if progress and (all_real_draws%110==0 or all_real_draws==limit):
                progress(all_real_draws,limit,"V41 çok adımlı yön ve isabet",day)
        stream.flush();stream.detach()
      write_csv(z,"02_GERCEK_HEDEF_ONCESI_DONDURULMUS_20_LISTELER.csv",
        DRAW_FIELDS,methods)
      evalrows=_evaluation(methods)
      write_csv(z,"03_ILK36_SON36_YON_MOTORLAR_ISABET.csv",
        EVAL_FIELDS,evalrows)
      groupdata=[]
      for (phase,section,label),(seen,hit) in sorted(grouped.items()):
        groupdata.append({"donem":phase,"boyut":section,"sinif":label,
          "gozlenen_sayi_adim":seen,"cikan20":hit,
          "oran_yuzde":round(100*hit/seen,5),
          "adil_rng_oran_yuzde":25,
          "gercek_eksi_beklenen":round(hit-.25*seen,4),
          "not":"Alt gruplar eszamanli ve bagimli; coklu tarama sahte bulgu yaratabilir."})
      write_csv(z,"04_YON_HIZ_IVME_KALIS_AILE_BANT_KESISIM.csv",
        GROUP_FIELDS,groupdata)
      brier=[]
      for phase in ("EGITIM","TEST"):
        blocks=[v for (ph,day),v in risk.items() if ph==phase]
        if not blocks:continue
        diff=[(v[0]-v[1],v[2]) for v in blocks]
        riskm=sum(v[0] for v in blocks)/sum(v[2] for v in blocks)
        risk0=sum(v[1] for v in blocks)/sum(v[2] for v in blocks)
        brier.append({"donem":phase,"denenen_cekilis":sum(v[2] for v in blocks)//80,
          "sayi_adim":sum(v[2] for v in blocks),
          "model_brier":round(riskm,8),"rng_brier":round(risk0,8),
          "model_eksi_rng_brier":round(riskm-risk0,8),
          "gun_blok_95_aralik":json.dumps(boot_days(diff)),
          "gun_sayisi":len(blocks)})
      write_csv(z,"05_ILERI_OLASILIK_BRIER_VE_BELIRSIZLIK.csv",
        B_FIELDS,brier)
      compare={}
      for ph in ("EGITIM","TEST"):
        daygroups={day:drawdata for (phase,day),drawdata in perday.items() if phase==ph}
        for benchmark in (CONTROL_RNG,CONTROL_V39,FROZEN):
            pairs=[]
            for day,drawdict in daygroups.items():
                vals=[s[ENSEMBLE]-s[benchmark] for s in drawdict.values()]
                pairs.append((sum(vals),len(vals)))
            if pairs:
                gap=sum(x for x,n in pairs)/sum(n for x,n in pairs)
                compare[f"{ph}__{ENSEMBLE}__eksi__{benchmark}"]={
                   "days":len(pairs),"draws":sum(n for x,n in pairs),
                   "difference_in_average_hits":round(gap,6),
                   "day_bootstrap_95":boot_days(pairs)}
      z.writestr("06_MOTOR_KARSILASTIRMA_GUN_BLOK.json",
           json.dumps(compare,ensure_ascii=False,indent=2).encode())
      metadata={"version":VERSION,
          "complete_days":len(full),"studied_days":len(days),
          "training_last_day":days[len(days)//2-1][0],
          "testing_first_day":cutoff,
          "real_draws_seen":all_real_draws,
          "predicted_draws":observations,
          "number_character_cards":80*observations,
          "method_count":len(ALL_METHODS),
          "individual_tickets":len(methods),
          "feature_windows":("heat seat movement","two-step persistence/reversal",
             "velocity jump","EWMA slope acceleration",
             "residence length","pretarget family peer movement","band pressure"),
          "primary_predeclared_test":ENSEMBLE+" vs "+CONTROL_RNG,
          "secondary_controls":[CONTROL_V39,FROZEN],
          "holdout_design":"First half history sets frozen parameters; online variant updates only after each future target's result. Fixed variant does NOT update on test.",
          "shrinkage_prior_trials":SHRINK,
          "fair_number_probability":.25,
          "fair_expected_hits_in20":5,
          "hidden_rng_recovered":False,
          "guaranteed_16of20":False,
          "source_warnings":errors}
      z.writestr("07_KAPSAM_VERI_VE_ON_KAYIT.json",
                 json.dumps(metadata,ensure_ascii=False,indent=2).encode())
      z.writestr("00_NASIL_OKUNUR.txt",(
        "V41 — SICAKLIK YONU ILE GERCEK 20'YI ARAS TIRMA\n"
        "================================================\n"
        "1) Her gercek t cekilisinden ONCE yalniz t-1 ve onceki\n"
        "   kayitlardan sicaklik yonu/hizi/ivmesi, iki adimli\n"
        "   devam/ters donus, kalis, aile ve bant hazirlanir.\n"
        "2) Her uzman yonteminden 20 farkli sayi dondurulur.\n"
        "3) Gercek hedef t geldiğinde 0..20 isabeti olculur.\n"
        "4) t gosterildikten SONRA online ogrenme ilerletilir.\n"
        "5) Ilk 36 tam gun egitim, sonraki 36 tam gun ayrik\n"
        "   testtir; testte sabit birlesim egitimde donar.\n"
        "6) Asil on kayitli inceleme YON_BIRLESIM_ONLINE - RASTGELE_20.\n"
        "7) V39 onceki birlesimi ikincil kontrol; test sayisina\n"
        "   bakip farkli denemeler arasindan basarili olan secilmez.\n"
        "8) Gun blok bootstrap fark belirsizligini raporlar.\n"
        "9) %25/5/20 RNG referansi; 16/20 hicbir sekilde garanti degil.\n"
        "10) 207 farkli uzman tamamiyla baglandi iddiasi yoktur.\n"
        "11) Aile yon esligi gercek aile epizotunun tam kopyasi degil,\n"
        "    onceki cekilisin uyelerinin yon uyumuna ait bir taramadir.\n"
        "12) Aynı gun icindeki sayi-kartlari bagimli oldugu icin\n"
        "    milyonlarca bagimsiz deney kabul edilmez.\n"
       ).encode("utf-8-sig"))
    with zipfile.ZipFile(io.BytesIO(zip_io.getvalue())) as z:
        assert z.testzip() is None and len(z.namelist())==8
    return zip_io.getvalue(),metadata,evalrows,brier,compare,groupdata


def from_text(txt,include_partial=False,progress=None):
    from v11_arastirma import read_draws
    draws,errors=read_draws(txt)
    blob,meta,results,brier,compare,groups=study(draws,include_partial,progress)
    meta["parsing_errors"]=len(errors)
    return blob,meta,results,brier,compare,groups
