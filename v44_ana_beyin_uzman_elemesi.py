# -*- coding: utf-8 -*-
"""V44: shared, future-blind brain; independently gated specialists.

18 whole dates fit / 18 whole dates select / 36 whole dates sealed test.
19 candidate strategies: eight genuine V39, five V41, five V42/V43,
one predeclared consensus. Descriptive '207 fields' are not 207 predictors.
Only prior draws feed predictions. Validation day-clustered maxT controls
the familywise false-discovery chance. If no expert qualifies, the master
emits RANDOM CONTROL ONLY, not a betting recommendation. Python stdlib.
"""
from __future__ import annotations
import csv,hashlib,io,json,math,random,statistics,zipfile
from collections import Counter,defaultdict,deque
from datetime import date,timedelta
from pathlib import Path
from v36_rng_davranis_klonu import sorted_draws,on_slot
from v11_arastirma import hour_draw_index
from v39_onceden_dondurulmus_uzman_paneli import OnlinePanel,SIGNALS,ENSEMBLE,show
from v40_alti_isi_yon_havuzlari import PreDraw
from v41_derin_yon_gecis_motoru import Calibrator,prepare,STRATEGIES
from v42_bes_hareketli_havuz_kota import histogram72,largest_remainder,hypergeom_all_five

VERSION="V44.1"
V39=tuple("V39_"+m for m in SIGNALS)
V41=tuple("V41_"+m for m in STRATEGIES)
FORMATION=("V42_BES_HAVUZ_KOTA","V42_KALIBRE_5KOTA","V42_8BANT_KOTA",
           "V18_20_60_TASIMA","V43_OLUSUM_GECIS_KOTA")
CONSENSUS="UZMAN_KONSENSUS_ARASTIRMA"
CANDIDATES=V39+V41+FORMATION+(CONSENSUS,)
MASTER="ANA_BEYIN_KILITLI"
OLD="V39_ONCEKI_BIRLESIM"
RNG="RASTGELE20_KONTROL"
METHODS=CANDIDATES+(MASTER,OLD,RNG)
STAGES=("KURULUM","UZMAN_ELEME","KOR_TEST","YENI_GUN")
OPTIONS=dict(delimiter=";",lineterminator="\n")
MIN_GAIN=.10
FAMILYWISE_P=.025
PERMUTATIONS=1400
SC_T=("gun","sira","cekilis_no","saat","donem","7_12","motor","secilen20",
      "gercek20","isabet","isabet_sayilari","onceden_donduruldu","karar","surum")
SC_Q=("gun","sira","cekilis_no","donem","7_12","kota_yontemi","aday_soguk",
      "aday_serin","aday_notr","aday_ilik","aday_sicak",
      "tahmin_soguk","tahmin_serin","tahmin_notr","tahmin_ilik","tahmin_sicak",
      "gercek_soguk","gercek_serin","gercek_notr","gercek_ilik","gercek_sicak",
      "tum5_tam","tum5_artieksi1","havuz_tekil_artieksi1",
      "rng_tum5_artieksi1_beklenen","kota_abs_hata")
SC_G=("motor","validasyon_cekilis","validasyon_gun","ortalama_isabet",
      "artis_5e_gore","7_12_artis","ilk9gun_artis","son9gun_artis",
      "t_istatistigi","coklu_test_duzeltilmis_p","kabul","gerekce")
SC_S=("donem","pencere","motor","cekilis","ortalama_isabet","en_yuksek",
      "8plus","10plus","12plus","14plus","16plus","isabet_0_20")
SC_QS=("donem","pencere","kota_yontemi","cekilis","havuz_artieksi1_pct",
       "tum5_tam_pct","tum5_artieksi1_pct","rng_tum5_artieksi1_beklenen_pct",
       "kota_abs_hata_ort")

def stable_rng(day,pos,label):
    seed=int(hashlib.sha256(f"V44|{day}|{pos}|{label}".encode()).hexdigest()[:16],16)
    return random.Random(seed)

def random20(day,pos):
    return frozenset(stable_rng(day,pos,"MASTER_RANDOM_BASELINE").sample(range(1,81),20))

def top20(scores,day,pos,label):
    rnd=stable_rng(day,pos,label)
    return frozenset(sorted(range(1,81),
        key=lambda n:(scores[n],rnd.random()),reverse=True)[:20])

def grouped20(groups,quotas,scores,day,pos,label):
    rnd=stable_rng(day,pos,label)
    picks=set()
    assert len(groups)==80 and sum(quotas)==20
    for group,k in enumerate(quotas):
        candidates=[n for n,v in enumerate(groups,1) if v==group]
        candidates.sort(key=lambda n:(scores[n],rnd.random()),reverse=True)
        picks.update(candidates[:k])
    assert len(picks)==20
    return frozenset(picks)

def vote20(tickets,day,pos,label):
    votes=[0]*81
    for picks in tickets.values():
        for n in picks:votes[n]+=1
    return top20(votes,day,pos,label)

def quota(sizes,rate=None):
    if rate is None:return largest_remainder(sizes,sizes)
    weights=[sizes[i]*(rate[i][1]+160*.25)/(rate[i][0]+160) for i in range(5)]
    return largest_remainder(weights,sizes)

class Brain:
    def __init__(self):
        self.v39=OnlinePanel()
        self.v41=PreDraw()
        self.v41rates=Calibrator()
        self.prior_q={}
        self.prior_delta={}
        self.h72=deque(maxlen=72)
        self.previous20=None
        self.recent_sig=None
        self.transitions=defaultdict(Counter)
        self.rate=defaultdict(lambda:[0,0])
        self.n=0
        self.last_no=None

    def freeze(self,day,pos):
        pools,_=self.v39.frozen(day,pos)
        cards=self.v41.snapshot(day,pos)
        if cards is not None:
            cards,_=prepare(cards,self.prior_q,self.prior_delta,self.v41.prev)
            p=self.v41rates.probabilities(cards)
        else:p={m:[.25]*80 for m in STRATEGIES}
        h=histogram72(self.h72)
        groups,sizes=h if h else ((2,)*80,(0,0,80,0,0))
        base=quota(sizes)
        adaptive=quota(sizes,self.rate)
        scores=[0.]*81
        for m in SIGNALS:
            for n in pools[m]:scores[n]+=1
        for n in pools[ENSEMBLE]:scores[n]+=.6
        experts={"V39_"+m:pools[m] for m in SIGNALS}
        for m in STRATEGIES:
            experts["V41_"+m]=top20([0]+p[m],day,pos,"V41_"+m)
        experts["V42_BES_HAVUZ_KOTA"]=grouped20(groups,base,scores,day,pos,"five")
        experts["V42_KALIBRE_5KOTA"]=grouped20(groups,adaptive,scores,day,pos,"five_live")
        bands=tuple((n-1)//10 for n in range(1,81))
        bandquota=largest_remainder([10]*8,[10]*8)
        experts["V42_8BANT_KOTA"]=grouped20(bands,bandquota,scores,day,pos,"eight")
        if self.previous20 is None:
            experts["V18_20_60_TASIMA"]=pools[ENSEMBLE]
        else:
            repeat_groups=tuple(0 if n in self.previous20 else 1 for n in range(1,81))
            experts["V18_20_60_TASIMA"]=grouped20(repeat_groups,(5,15),scores,day,pos,"20_60")
        if self.recent_sig is not None and self.recent_sig in self.transitions:
            counts=self.transitions[self.recent_sig]
            weight=24.
            total=sum(counts.values())
            conditional=[(sum(c*prev[i] for prev,c in counts.items())+
                        weight*sizes[i]/4)/(total+weight) for i in range(5)]
            transition_quota=largest_remainder(conditional,sizes)
        else:transition_quota=base
        experts["V43_OLUSUM_GECIS_KOTA"]=grouped20(
            groups,transition_quota,scores,day,pos,"formation")
        experts[CONSENSUS]=vote20(experts,day,pos,"unweighted_consensus")
        assert tuple(experts)==CANDIDATES
        assert all(len(p)==20 for p in experts.values())
        return {"picks":experts,"v39_old":pools[ENSEMBLE],"pools":pools,
                "cards":cards,"groups":groups,"sizes":sizes,
                "quotas":{"BOYUT_YUZDE25":base,
                          "HAREKETLI_KALIBRE":adaptive,
                          "GECIS_OLUSUM":transition_quota}}

    def observe(self,day,pos,no,real,frozen):
        assert len(real)==20
        self.v39.score_and_learn(day,pos,no,real,frozen["pools"])
        cards=frozen["cards"]
        if cards is not None:
            self.v41rates.observe(cards,real)
            self.prior_q={q["sayi"]:q for q in cards}
            self.prior_delta={q["sayi"]:q["egim"] for q in cards}
        self.v41.append(day,pos,no,real)
        if len(self.h72)==72:
            group=frozen["groups"]
            realquota=tuple(sum(group[n-1]==i for n in real) for i in range(5))
            if self.recent_sig is not None:
                self.transitions[self.recent_sig][realquota]+=1
            self.recent_sig=realquota
            for i,size in enumerate(frozen["sizes"]):
                self.rate[i][0]+=size
                self.rate[i][1]+=realquota[i]
        self.h72.append(frozenset(real))
        self.previous20=frozenset(real)
        self.n+=1
        self.last_no=no

def tstat(vals):
    if len(vals)<3:return 0.
    dev=statistics.stdev(vals)
    return statistics.mean(vals)*math.sqrt(len(vals))/dev if dev>1e-9 else 0.

def maxT_p(dayvalues,reps=PERMUTATIONS):
    days=sorted(dayvalues)
    columns={m:[dayvalues[d][m] for d in days] for m in CANDIDATES}
    observed={m:tstat(a) for m,a in columns.items()}
    rng= random.Random(4402026)
    hits=Counter()
    for _ in range(reps):
        signs=[rng.choice((-1,1)) for d in days]
        largest=max(tstat([v*s for v,s in zip(columns[m],signs)])
                    for m in CANDIDATES)
        for m in CANDIDATES:
            if largest>=observed[m]-1e-10:hits[m]+=1
    return {m:(hits[m]+1)/(reps+1) for m in CANDIDATES}

def select_experts(validation):
    by_day=defaultdict(lambda:defaultdict(list))
    full=defaultdict(list)
    for row in validation:
        if row["motor"] not in CANDIDATES:continue
        by_day[row["gun"]][row["motor"]].append(float(row["isabet"])-5)
        full[row["motor"]].append(row)
    days=sorted(by_day)
    matrix={day:{m:statistics.mean(by_day[day][m]) for m in CANDIDATES}
            for day in days}
    prob=maxT_p(matrix) if len(days)>=12 else {m:1. for m in CANDIDATES}
    report=[];chosen=[]
    for m in CANDIDATES:
        values=full[m]
        delta=statistics.mean(float(r["isabet"])-5 for r in values)
        h=[float(r["isabet"])-5 for r in values if r["7_12"]=="EVET"]
        hscore=statistics.mean(h) if h else 0
        first=statistics.mean(matrix[d][m] for d in days[:len(days)//2])
        second=statistics.mean(matrix[d][m] for d in days[len(days)//2:])
        approved=(len(days)>=12 and delta>=.10 and
                  hscore>0 and first>0 and second>0 and prob[m]<.025)
        if approved:chosen.append(m)
        report.append({"motor":m,"validasyon_cekilis":len(values),
             "validasyon_gun":len(days),
             "ortalama_isabet":round(5+delta,6),"artis_5e_gore":round(delta,6),
             "7_12_artis":round(hscore,6),
             "ilk9gun_artis":round(first,6),"son9gun_artis":round(second,6),
             "t_istatistigi":round(tstat([matrix[d][m] for d in days]),5),
             "coklu_test_duzeltilmis_p":round(prob[m],6),
             "kabul":"EVET" if approved else "HAYIR",
             "gerekce":"ON KAYITLI SINIR GECILDI" if approved else
                      "Ustunluk veya dayaniklilik kanitlanmadi"})
    chosen.sort(key=lambda m:-next(r["artis_5e_gore"] for r in report if r["motor"]==m))
    selected=[];redundant={}
    for m in chosen:
        duplicate=None
        for kept in selected:
            overlap=statistics.mean(len(set(a["secilen20"].split(",")) &
                set(b["secilen20"].split(","))) for a,b in zip(full[m],full[kept]))
            if overlap>=18.5:duplicate=kept;break
        if duplicate:redundant[m]=duplicate
        else:selected.append(m)
    if CONSENSUS in selected:selected=[CONSENSUS]
    return report,selected[:4],redundant

def master_pick(frozen,selected,day,pos):
    if not selected:return random20(day,pos),"KANIT_YOK_RNG_REFERANSI"
    if len(selected)==1:return frozen["picks"][selected[0]],"ONAYLI_VALIDASYON"
    return vote20({m:frozen["picks"][m] for m in selected},
                  day,pos,"vetted_consensus"),"ONAYLI_VALIDASYON"

def export_csv(zipf,name,cols,items):
    with zipf.open(name,"w") as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8-sig",
                                newline="",write_through=True)
        writer=csv.DictWriter(stream,fieldnames=cols,extrasaction="ignore",**OPTIONS)
        writer.writeheader()
        for item in items:writer.writerow(item)
        stream.flush();stream.detach()

def summaries(rows,cols,mode):
    grouped=defaultdict(list)
    for x in rows:
        if mode=="tickets":
            grouped[(x["donem"],"TUM",x["motor"])].append(x)
            if x["7_12"]=="EVET":
                grouped[(x["donem"],"7_12",x["motor"])].append(x)
        else:
            grouped[(x["donem"],"TUM",x["kota_yontemi"])].append(x)
            if x["7_12"]=="EVET":
                grouped[(x["donem"],"7_12",x["kota_yontemi"])].append(x)
    out=[]
    for (phase,window,model),group in sorted(grouped.items()):
        cnt=len(group)
        if mode=="tickets":
            n=[int(x["isabet"]) for x in group]
            c=Counter(n)
            out.append({"donem":phase,"pencere":window,"motor":model,
                "cekilis":cnt,"ortalama_isabet":round(statistics.mean(n),5),
                "en_yuksek":max(n),"8plus":sum(x>=8 for x in n),
                "10plus":sum(x>=10 for x in n),"12plus":sum(x>=12 for x in n),
                "14plus":sum(x>=14 for x in n),"16plus":sum(x>=16 for x in n),
                "isabet_0_20":json.dumps([c.get(i,0) for i in range(21)])})
        else:
            out.append({"donem":phase,"pencere":window,"kota_yontemi":model,
                "cekilis":cnt,"havuz_artieksi1_pct":round(20*sum(x["havuz_tekil_artieksi1"] for x in group)/cnt,5),
                "tum5_tam_pct":round(100*sum(x["tum5_tam"] for x in group)/cnt,5),
                "tum5_artieksi1_pct":round(100*sum(x["tum5_artieksi1"] for x in group)/cnt,5),
                "rng_tum5_artieksi1_beklenen_pct":round(100*statistics.mean(
                       x["rng_tum5_artieksi1_beklenen"] for x in group),5),
                "kota_abs_hata_ort":round(statistics.mean(x["kota_abs_hata"] for x in group),5)})
    return out

def paired_days(rows,a,b,phase="KOR_TEST",iterations=1000):
    candidates=defaultdict(dict)
    for x in rows:
        if x["donem"]==phase and x["motor"] in (a,b):
            candidates[(x["gun"],x["sira"])][x["motor"]]=int(x["isabet"])
    sums=defaultdict(lambda:[0,0])
    for (d,p),s in candidates.items():
        if a in s and b in s:
            sums[d][0]+=s[a]-s[b]
            sums[d][1]+=1
    groups=list(sums.values())
    if not groups:return {}
    diff=sum(x for x,n in groups)/sum(n for x,n in groups)
    rnd=random.Random(4402026)
    bvals=[]
    for _ in range(iterations):
        selected=[groups[rnd.randrange(len(groups))] for k in groups]
        bvals.append(sum(x for x,n in selected)/sum(n for x,n in selected))
    bvals.sort()
    return {"model":a,"reference":b,"days":len(groups),
       "draws":sum(n for x,n in groups),
       "average_hit_difference":round(diff,6),
       "day_block_95":[round(bvals[int(.025*(len(bvals)-1))],6),
                       round(bvals[int(.975*(len(bvals)-1))],6)]}

def study(draws,include_partial=False,progress=None):
    days,full,warnings=sorted_draws(draws,include_partial)
    if len(days)<8:raise ValueError("V44 en az 8 gun, ideal 72 tam gun ister")
    fit_end=days[18][0] if len(days)>=36 else days[max(1,len(days)//4)][0]
    validation_end=days[36][0] if len(days)>=37 else days[max(2,len(days)//2)][0]
    beyond=days[72][0] if len(days)>=73 else None
    brain=Brain()
    tickets=[];quota_rows=[];validation=[]
    gates=[];admitted=None;duplicates={}
    total=sum(len(group) for _,group in days)
    processed=0
    for day,group in days:
        phase=("KURULUM" if day<fit_end else
               "UZMAN_ELEME" if day<validation_end else
               "YENI_GUN" if beyond and day>=beyond else "KOR_TEST")
        if phase in ("KOR_TEST","YENI_GUN") and admitted is None:
            gates,admitted,duplicates=select_experts(validation)
        for d in group:
            pos=d["pos"];no=d["no"];actual=frozenset(d["nums"])
            before=brain.freeze(day,pos)  # t numbers are NOT an input
            if admitted is None:master,status=random20(day,pos),"EGITIM_KARARI_YOK"
            else:master,status=master_pick(before,admitted,day,pos)
            candidates=dict(before["picks"])
            candidates[MASTER]=master
            candidates[OLD]=before["v39_old"]
            candidates[RNG]=random20(day,pos)
            assert set(candidates)==set(METHODS) and all(len(x)==20 for x in candidates.values())
            half="EVET" if hour_draw_index(pos) in range(7,13) else "HAYIR"
            for model,picks in candidates.items():
                hit=picks&actual
                row={"gun":day,"sira":pos,"cekilis_no":no,"saat":on_slot(pos),
                     "donem":phase,"7_12":half,"motor":model,
                     "secilen20":show(picks),"gercek20":show(actual),
                     "isabet":len(hit),"isabet_sayilari":show(hit),
                     "onceden_donduruldu":"EVET",
                     "karar":status if model==MASTER else "KARSILASTIRMA",
                     "surum":VERSION}
                tickets.append(row)
                if phase=="UZMAN_ELEME" and model in CANDIDATES:
                    validation.append(row)
            if brain.n>=72:
                classes=before["groups"];size=before["sizes"]
                actual5=tuple(sum(classes[n-1]==i for n in actual) for i in range(5))
                names=("soguk","serin","notr","ilik","sicak")
                for label,q in before["quotas"].items():
                    exact,odds=hypergeom_all_five(tuple(size),tuple(q))
                    quota_rows.append({"gun":day,"sira":pos,"cekilis_no":no,
                         "donem":phase,"7_12":half,"kota_yontemi":label,
                         **{f"aday_{s}":x for s,x in zip(names,size)},
                         **{f"tahmin_{s}":x for s,x in zip(names,q)},
                         **{f"gercek_{s}":x for s,x in zip(names,actual5)},
                         "tum5_tam":int(q==actual5),
                         "tum5_artieksi1":int(all(abs(a-b)<=1 for a,b in zip(q,actual5))),
                         "havuz_tekil_artieksi1":sum(abs(a-b)<=1 for a,b in zip(q,actual5)),
                         "rng_tum5_artieksi1_beklenen":round(odds,10),
                         "kota_abs_hata":sum(abs(a-b) for a,b in zip(q,actual5))})
            brain.observe(day,pos,no,actual,before) # ONLY now target enters memory
            processed+=1
            if progress and (processed%130==0 or processed==total):
                progress(processed,total,"V44 19 uzman/5 havuz/kor test",day)
    if admitted is None:gates,admitted,duplicates=select_experts(validation)
    score=summaries(tickets,SC_S,"tickets")
    quotas=summaries(quota_rows,SC_QS,"quota")
    pair=[paired_days(tickets,MASTER,RNG),paired_days(tickets,MASTER,OLD),
          paired_days(tickets,CONSENSUS,RNG)]
    day,last=days[-1];lastpos=last[-1]["pos"]
    nextday=day if lastpos<217 else (date.fromisoformat(day)+timedelta(days=1)).isoformat()
    nextpos=lastpos+1 if lastpos<217 else 1
    now=brain.freeze(nextday,nextpos)
    tentative,state=master_pick(now,admitted,nextday,nextpos)
    upcoming={"source_last_date":day,"source_last_pos":lastpos,
        "source_last_draw_no":brain.last_no,
        "next_source_slot_date":nextday,"next_source_slot_pos":nextpos,
        "next_source_slot_time":on_slot(nextpos),
        "research_20":show(tentative),
        "status":state,"not_guaranteed_current_future":True}
    meta={"version":VERSION,"complete_days":len(full),"days_studied":len(days),
         "real_draws":processed,"first18_fit":days[0][0]+".."+days[17][0] if len(days)>=36 else None,
         "middle18_validation":days[18][0]+".."+days[35][0] if len(days)>=37 else None,
         "last36_locked_test_from":validation_end,
         "first72_cutoff_never_shifts_with_new_days":True,
         "experts":len(CANDIDATES),"validation_gate_adjusted_maxT":True,
         "fwer_one_sided_alpha":FAMILYWISE_P,
         "validation_min_gain_vs_theoretical5":MIN_GAIN,
         "gate_repeated_on_test":False,
         "accepted":admitted,"count_accepted":len(admitted),
         "duplicate_streams_if_approved":duplicates,
         "fallback_if_none":"20 seeded fair random numbers; NO predictive advantage and NOT a betting recommendation",
         "v38_207":"207 descriptive fields are not 207 independent future-target experts",
         "v29_v43":"Independent pretarget V39(8),V41(5),V42/V43 inspired(5),one untuned consensus; other reports descriptive not all as models",
         "fair_20_over_80_hit_expected":5,"fair_single_number_probability":.25,
         "fair_bucket_reference":"conditional multivariate hypergeometric",
         "quota_learning_uses_current_target":False,
         "draw_labels_prepared_before_actual_target":True,
         "source_warnings":warnings,"paired_36_day_comparisons":pair,
         "source_next_snapshot":upcoming}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        export_csv(z,"01_HER_CEKILISTE_DONDURULMUS_20_LISTELER.csv",SC_T,tickets)
        export_csv(z,"02_HER_CEKILISTE_BES_HAVUZ_KOTA.csv",SC_Q,quota_rows)
        export_csv(z,"03_UZMAN_SECIMI_MAXT_VALIDASYON.csv",SC_G,gates)
        export_csv(z,"04_20_LISTE_ISABET_EGITIM_VALI_TEST.csv",SC_S,score)
        export_csv(z,"05_KOTA_ISABET_VE_RNG_REFERANS.csv",SC_QS,quotas)
        z.writestr("06_ESLENIK_GUN_BLOK_KARSILASTIRMA.json",
                   json.dumps(pair,ensure_ascii=False,indent=2).encode())
        z.writestr("07_KAPSAM_ELEME_GUVENLIK.json",
                   json.dumps(meta,ensure_ascii=False,indent=2).encode())
        z.writestr("08_VERI_SONRASI_LISTE.csv",
                   "son_gun;son_sira;sonraki_gun;sonraki_sira;saat;20_sayi;karar;canli_kesin_degil\n"+
                   f"{day};{lastpos};{nextday};{nextpos};{on_slot(nextpos)};{show(tentative)};{state};EVET\n")
        z.writestr("00_KULLANIM_NOTU.txt",(
          "V44 ANA BEYIN: 18 TAM GUN KURULUM, 18 TAM GUN UZMAN SECIMI, 36 TAM GUN MUHURLU TEST.\n"
          "19 gercek cekilis-oncesi 20-sayi adayi var (V39 8, V41 5, V42/V43 5, konsensus 1).\n"
          "Her hedef ONCESI sayilar ve havuz kotalari donar; gercek20 yalniz SONRA kayda girer.\n"
          "Ilk 36 gun disindaki kayitlar, test sirasinda uzman secimine katilmaz.\n"
          "Kabul icin validasyonda en az +0.10/20 artim, iki yari pozitif,\n"
          "7-12 pozitif, 19 aday icin gun bazli maxT cogul test duzeltme p<.025 lazim.\n"
          "Hicbiri kabul edilmezse tek ANA_BEYIN 20 rakam basar AMA RASTGELE KONTROL DENEYIDIR.\n"
          "Bu ne kupon tavsiyesidir ne 16/20 garanti; kanitsiz sinyal oyuna baglanmaz.\n"
          "V38 207 kolon analitik karakterlerdir, 207 bagimsiz gelcek tahmini degildir.\n"
          "Beş H72 havuzu ve 8 bant + onceki20/60 + V43 gecis olusumu ayri karsilastirilir.\n"
          "Gelecekte eklenecek yeni gercek gunler secim penceresini ileri kaydirmaz.\n"
          "Kaynak dosyasi eskiyse veri-sonrasi gosterilen tarih gecmiste kalmis olabilir.\n"
        ).encode("utf-8-sig"))
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
        assert z.testzip() is None and len(z.namelist())==9
    return buf.getvalue(),meta,score,quotas,gates

if __name__=="__main__":
    from v11_arastirma import read_draws
    data,errors=read_draws(Path("veri.txt").read_text(encoding="utf-8-sig"))
    content,meta,scores,quotas,gates=study(data)
    out=Path("V44_ANA_BEYIN_ELEME_72_GUN_TEK_ZIP.zip")
    out.write_bytes(content)
    print("V44 VERIFIED 72 DAY:",json.dumps({
       "source_days":meta["complete_days"],"draws":meta["real_draws"],
       "candidate_experts":meta["experts"],"admitted":meta["accepted"],
       "holdout":[r for r in scores if r["donem"]=="KOR_TEST" and r["pencere"]=="TUM"
                   and r["motor"] in (MASTER,OLD,RNG,CONSENSUS)],
       "test_7_12":[r for r in scores if r["donem"]=="KOR_TEST" and r["pencere"]=="7_12"
                   and r["motor"] in (MASTER,OLD,RNG,CONSENSUS)],
       "quota_holdout":[r for r in quotas if r["donem"]=="KOR_TEST" and r["pencere"]=="TUM"],
       "paired":meta["paired_36_day_comparisons"],"validation_top":sorted(
            gates,key=lambda r:-r["artis_5e_gore"])[:4],
       "zip_bytes":out.stat().st_size,"warnings":len(errors)
    },ensure_ascii=False),flush=True)
