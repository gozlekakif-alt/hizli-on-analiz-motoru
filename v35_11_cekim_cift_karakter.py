# -*- coding: utf-8 -*-
"""V35: Eleven real-draw binary DNA for each of 80 balls.

A 1 = member of REAL_20, 0 = member of NON_60.
Window: exactly 11 consecutive recorded draw positions, within a day.
A 6+ hit window and a 6+ trailing-zero streak cannot describe the same
number within the same 11-window. Both can coexist among DIFFERENT balls.
All source features are frozen before the NEXT real draw is evaluated.
"""
from __future__ import annotations
import csv
import io
import json
import math
import random
import statistics
import zipfile
from collections import Counter, defaultdict
from v33_bekleme_havuzlari import clean_draws, SIX, SIX_SIZES, DECAY
from v32_80_tamamlama import FULL_MASK, clock, csv_bytes

MASK11=(1<<11)-1
MASK22=(1<<22)-1
BALLS=range(1,81)
RNG_JOINT=(20*19)/(80*79)
RNG_HIGH=sum(math.comb(11,k)*(.25**k)*(.75**(11-k)) for k in range(6,12))
CLASSES=('YOGUN_6PLUS','BEKLEYEN_6PLUS','DUZENLI_4_5','AZ_0_1','NORMAL_2_3')
DETAIL_FIELDS=('gun','donem','kaynak_sira','kaynak_saat','hedef_sira','sayi','bant',
 'imza_11','son11_cikan','son11_cikmayan','son6_cikan','son6_cikmayan',
 'ust_uste_cikmama','ust_uste_cikma','son5_cikan','ilk6_cikan',
 'yon','karakter','v28_isi','v32_dongu_goruldu','onceki11_cikan',
 'onceki11_fark','hedef_20_de','hedef_60_da')


def shift_state(patterns, streak0, streak1, appeared):
    for n in BALLS:
        hit=int(n in appeared)
        patterns[n]=((patterns[n]<<1)|hit)&MASK22
        streak0[n]=0 if hit else streak0[n]+1
        streak1[n]=streak1[n]+1 if hit else 0


def get_class(freq, gap):
    if freq >= 6:
        return CLASSES[0]
    if gap >= 6:
        return CLASSES[1]
    if freq>=4:
        return CLASSES[2]
    if freq<=1:
        return CLASSES[3]
    return CLASSES[4]


def signed_direction(pattern):
    # recent five vs earlier six; compare frequencies without unequal-window bias
    recent=(pattern&31).bit_count()
    older=(pattern>>5).bit_count()
    score=6*recent-5*older
    return 'ARTIYOR' if score>0 else 'AZALIYOR' if score<0 else 'DENGELI'


def moment(p):
    if p==13:return '01:02_EK'
    if p<=12:return '00:02_'+str(p)
    return f'{7+(p-14)//12:02d}:02_'+str((p-14)%12+1)


def heat_after(scores, wins):
    for n in BALLS:scores[n]=scores[n]*DECAY+int(n in wins)
    ordering=sorted(BALLS,key=lambda n:(scores[n],n))
    out=['']*81
    offset=0
    for j,size in enumerate(SIX_SIZES):
        for n in ordering[offset:offset+size]:out[n]=SIX[j]
        offset+=size
    return out


def group_report(counts,keys,period=''):
    rows=[]
    for tag,agg in sorted(counts.items(),key=lambda v:str(v[0])):
        count,hits=agg
        if not count:continue
        key=tag if isinstance(tag,tuple) else (tag,)
        row={k:v for k,v in zip(keys,key)}
        if period:row['donem']=period
        row.update({'gozlem':count,'gelecek20_isabet':hits,
                    'isabet_yuzde':round(100*hits/count,4),
                    'rng_yuzde':25,
                    'rng_fark_puan':round(100*(hits/count-.25),4)})
        rows.append(row)
    return rows


def choose_stable(training,tests,minimum=100):
    # Selection is ONLY from first 36 full days. Held-out rows never select.
    ranked=[]
    for signature,(n,hits) in training.items():
        if n>=minimum:
            effect=hits/n-.25
            ranked.append((abs(effect),signature,n,hits,effect))
    chosen=sorted(ranked,reverse=True)[:20]
    return [
        {'imza_11':f'{signature:011b}',
         'egitim_kesit':n,'egitim_isabet':hits,
         'egitim_yuzde':round(100*hits/n,3),
         'test_kesit':tests.get(signature,(0,0))[0],
         'test_isabet':tests.get(signature,(0,0))[1],
         'test_yuzde':(round(100*tests[signature][1]/tests[signature][0],3)
             if signature in tests and tests[signature][0] else ''),
         'test_rng_yuzde':25} for _,signature,n,hits,_ in chosen]


def study(draws,include_partial=False,progress=None):
    byday,full,errors=clean_draws(draws)
    eligible=set(byday) if include_partial else set(full)
    if not eligible:raise ValueError('217 çekilişlik tam gün bulunamadı.')
    cutoff=full[len(full)//2] if full else sorted(eligible)[len(eligible)//2]
    summary={'tam_gun':len(set(full)&eligible),'eksik_gun':len(eligible-set(full)),
       'tum_kayitli_gun':len(byday),'egitim_test_ayrac_gun':cutoff,
       'kayit_hatasi':len(errors),'rng_11de_6arti_oran':round(RNG_HIGH,8),
       'rng_6_ustuste_cikmama_oran':round(.75**6,8),
       'rng_sonraki_20_oran':.25,'rng_iki_farkli_sayinin_birlikte_gelme':round(RNG_JOINT,8)}
    pool_stats=defaultdict(lambda:[0,0])
    heat_stats=defaultdict(lambda:[0,0])
    exact_stats=defaultdict(lambda:[0,0])
    pattern_stats=defaultdict(lambda:[0,0])
    day_stats=defaultdict(Counter)
    per_signature={p:defaultdict(lambda:[0,0]) for p in ('EGITIM','TEST')}
    transition=Counter()
    pattern_pair=defaultdict(lambda:[0,0])
    band_pair=defaultdict(lambda:[0,0])
    pool_pair=defaultdict(lambda:[0,0])
    daily_rows=[]
    window_rows=[]
    transitions_rows=[]
    pair_rows=[]
    pair_summary=[]
    out=io.BytesIO()
    scores=[0.]*81
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
      # Write detailed 80-number snapshots directly into the compressed ZIP,
      # avoiding >1M in-memory Python dicts and phone/Streamlit memory issues.
      with z.open('01_80_SAYI_HER_11_IMZA_VE_SONRAKI_CEKILIS.csv','w') as binary:
       with io.TextIOWrapper(binary,encoding='utf-8-sig',newline='',write_through=True) as file:
        writer=csv.DictWriter(file,fieldnames=DETAIL_FIELDS,delimiter=';',lineterminator='\n')
        writer.writeheader()
        evaluated=0
        observed=0
        for index,day in enumerate(sorted(byday)):
          daymap=byday[day]
          active_day=day in eligible
          phase='EGITIM' if day<cutoff else 'TEST'
          patterns=[0]*81;wait=[0]*81;consecutive_hits=[0]*81
          since_gap=0;last_pos=None
          v32_seen=0
          daily_events=Counter()
          for pos in sorted(daymap):
            row=daymap[pos]
            wins=set(row['nums'])
            if last_pos is not None and pos!=last_pos+1:
                patterns=[0]*81;wait=[0]*81;consecutive_hits=[0]*81
                since_gap=0;v32_seen=0
            last_pos=pos
            since_gap+=1
            shift_state(patterns,wait,consecutive_hits,wins)
            v32_seen |= sum(1<<(n-1) for n in wins)
            heats=heat_after(scores,wins)
            if not active_day:
                if v32_seen==FULL_MASK:v32_seen=0
                continue
            if since_gap<11:
                if v32_seen==FULL_MASK:v32_seen=0
                continue
            target=daymap.get(pos+1)
            # Day 217 and interrupted segments have no known subsequent draw.
            next_set=set(target['nums']) if target is not None else None
            high=[];absent=[]
            class_counts=Counter()
            freq_counts=Counter()
            present6=0;absent6=0
            for n in BALLS:
                p11=patterns[n]&MASK11
                freq=p11.bit_count()
                gap=wait[n]
                status=get_class(freq,gap)
                if freq>=6:high.append(n)
                if gap>=6:absent.append(n)
                if freq>=6 and gap>=6:
                    raise AssertionError('11-window cannot include both H6 and A6 for the same number')
                class_counts[status]+=1
                freq_counts[freq]+=1
                hit=(int(n in next_set) if next_set is not None else None)
                earlier=p11>>5
                recent=p11&31
                trend=signed_direction(p11)
                v32_pool='GORULDU' if v32_seen&(1<<(n-1)) else 'HENUZ_GORULMEDI'
                band=f'{(n-1)//10*10+1:02d}-{(n-1)//10*10+10:02d}'
                row_out={'gun':day,'donem':phase,'kaynak_sira':pos,
                    'kaynak_saat':clock(pos),
                    'hedef_sira':pos+1 if target is not None else '',
                    'sayi':n,'bant':band,'imza_11':f'{p11:011b}',
                    'son11_cikan':freq,'son11_cikmayan':11-freq,
                    'son6_cikan':(p11&63).bit_count(),
                    'son6_cikmayan':6-(p11&63).bit_count(),
                    'ust_uste_cikmama':gap,'ust_uste_cikma':consecutive_hits[n],
                    'son5_cikan':recent.bit_count(),'ilk6_cikan':earlier.bit_count(),
                    'yon':trend,'karakter':status,'v28_isi':heats[n],
                    'v32_dongu_goruldu':v32_pool,
                    'onceki11_cikan':(patterns[n]>>11).bit_count() if since_gap>=22 else '',
                    'onceki11_fark':(freq-(patterns[n]>>11).bit_count()) if since_gap>=22 else '',
                    'hedef_20_de':hit if hit is not None else '',
                    'hedef_60_da':1-hit if hit is not None else ''}
                writer.writerow(row_out)
                observed+=1
                if hit is None:continue
                evaluated+=1
                for typ,key in (
                    ('KARAKTER',(phase,status)),
                    ('SAYI_11',(phase,str(freq))),
                    ('IMZA11',(phase,row_out['imza_11'])),
                    ('KARAKTER_ISI_DONGU',(phase,status,heats[n],v32_pool)),
                    ('KARAKTER_BANT',(phase,status,band)),
                    ('KARAKTER_YON',(phase,status,trend))
                ):
                    bucket=(typ,)+key
                    dst=pool_stats[bucket] if typ=='KARAKTER' else (
                        exact_stats[bucket] if typ=='SAYI_11' else
                        pattern_stats[bucket] if typ=='IMZA11' else
                        heat_stats[bucket])
                    dst[0]+=1;dst[1]+=hit
                key=per_signature[phase][p11]
                key[0]+=1;key[1]+=hit
                nmask=((patterns[n]<<1)|hit)&MASK11
                following=get_class(nmask.bit_count(),0 if hit else gap+1)
                transition[(phase,status,following,hit)]+=1
            if len(high)+len(absent)>80:raise AssertionError('impossible overlapping pools')
            todays_key=(phase,day)
            daily_events['kesit']+=1
            daily_events['yogun_6plus']+=len(high)
            daily_events['bekleyen_6plus']+=len(absent)
            daily_events['her_ikisinin_goruldugu_kesit']+=int(bool(high) and bool(absent))
            daily_events['sonraki_tahmin_kesidi']+=int(next_set is not None)
            crow={'gun':day,'donem':phase,'kaynak_sira':pos,
                'kaynak_saat':clock(pos),'saat_durumu':moment(pos),
                'sonraki_sira':pos+1 if next_set is not None else '',
                'yogun_11de6plus':len(high),'enaz6_ustuste_gelmeyen':len(absent),
                'ikisi_birden_mevcut':int(bool(high) and bool(absent)),
                'yogun_sayi_listesi':','.join(map(str,high)),
                'bekleyen_sayi_listesi':','.join(map(str,absent)),
                'simdi_cikan20_ile_yogun_kesisim':len(wins&set(high)),
                'simdi_cikan20_ile_bekleyen_kesisim':len(wins&set(absent))}
            for f in range(12):crow['11de_'+str(f)+'_defa']=freq_counts[f]
            for label in CLASSES:crow[label]=class_counts[label]
            window_rows.append(crow)
            # Same-draw combinations high A and absent B, measured only at the
            # following *observed* draw. Exact 2-distinct-number RNG joint is
            # 20*19/(80*79), not 25%^2.
            if next_set is not None:
                for a in high:
                    for b in absent:
                        if a==b:raise AssertionError('same-number high/absent impossible')
                        joint=int(a in next_set and b in next_set)
                        pair_key=(phase,a,b)
                        v=pattern_pair[pair_key];v[0]+=1;v[1]+=joint
                        aa=f'{(a-1)//10*10+1:02d}-{(a-1)//10*10+10:02d}'
                        bb=f'{(b-1)//10*10+1:02d}-{(b-1)//10*10+10:02d}'
                        for d,mat in ((band_pair,(phase,aa,bb)),(pool_pair,(phase,heats[a],heats[b]))):
                            v=d[mat];v[0]+=1;v[1]+=joint
                        pair_rows.append({'donem':phase,'gun':day,'kaynak_sira':pos,
                             'hedef_sira':pos+1,'yogun_6plus_sayi':a,
                             '6plus_bekleyen_sayi':b,
                             'yogun_isi':heats[a],'bekleyen_isi':heats[b],
                             'yogun_bant':aa,'bekleyen_bant':bb,
                             'sonraki_cekiliste_ikisi_cikti':joint,
                             'rng_ikisi_cikma_yuzdesi':round(100*RNG_JOINT,6)})
            if v32_seen==FULL_MASK:v32_seen=0
          if active_day and daily_events['kesit']:
            daily_rows.append({'gun':day,'donem':phase,
                '11li_kesit':daily_events['kesit'],
                'enaz6_gorulen_toplam':daily_events['yogun_6plus'],
                'enaz6_bekleyen_toplam':daily_events['bekleyen_6plus'],
                'ortalama_11de6plus':round(daily_events['yogun_6plus']/daily_events['kesit'],4),
                'ortalama_6plus_bekleme':round(daily_events['bekleyen_6plus']/daily_events['kesit'],4),
                'ayni_kesitte_iki_grup':daily_events['her_ikisinin_goruldugu_kesit'],
                'sonraki_cekilis_bilinen':daily_events['sonraki_tahmin_kesidi']})
          if progress:progress(index+1,len(byday),'V35 11 çekiliş karakter taraması',day)
    summary.update({'degerlendirilen_gelecek_sayi':evaluated,
             '11li_pencere_sayi_kaydi':observed,
             '11li_kesit':len(window_rows),
             'aktif_gun':len(daily_rows),
             'yogun_artik_ornek':sum(x['enaz6_gorulen_toplam'] for x in daily_rows),
             '6plus_bekleyen_ornek':sum(x['enaz6_bekleyen_toplam'] for x in daily_rows),
             'yogun_ortalama_kesit':round(sum(x['enaz6_gorulen_toplam'] for x in daily_rows)/len(window_rows),5),
             'bekleyen_ortalama_kesit':round(sum(x['enaz6_bekleyen_toplam'] for x in daily_rows)/len(window_rows),5)})
    tables={}
    classes=group_report({k[1:]:v for k,v in pool_stats.items() if k[0]=='KARAKTER'},
                         ['donem','karakter'])
    freq=group_report({k[1:]:v for k,v in exact_stats.items()},['donem','11de_kac'])
    fullcross=group_report({k[1:]:v for k,v in heat_stats.items() if k[0]=='KARAKTER_ISI_DONGU'},
                           ['donem','karakter','v28_isi','v32_gorulme'])
    bands=group_report({k[1:]:v for k,v in heat_stats.items() if k[0]=='KARAKTER_BANT'},
                           ['donem','karakter','bant'])
    trend=group_report({k[1:]:v for k,v in heat_stats.items() if k[0]=='KARAKTER_YON'},
                           ['donem','karakter','yon'])
    signatures=group_report({k[1:]:v for k,v in pattern_stats.items() if k[0]=='IMZA11'},
                           ['donem','imza_11'])
    transitions=[{'donem':phase,'onceki_karakter':old,'sonraki_karakter':new,
                  'sonraki_20_de':hit,'olay':v}
            for (phase,old,new,hit),v in sorted(transition.items())]
    selected=choose_stable(per_signature['EGITIM'],per_signature['TEST'])
    pairnums=group_report(pattern_pair,['donem','yogun_sayi','bekleyen_sayi'])
    pairbands=group_report(band_pair,['donem','yogun_bant','bekleyen_bant'])
    pairheat=group_report(pool_pair,['donem','yogun_isi','bekleyen_isi'])
    for table in (pairnums,pairbands,pairheat):
        for r in table:
            r['rng_iki_sayi_birlikte_yuzde']=round(RNG_JOINT*100,5)
            r['rng_iki_sayi_fark_puan']=round(r['isabet_yuzde']-RNG_JOINT*100,5)
            # The generic 'rng_yuzde' column from group_report was 25%;
            # replace it for two-distinct-ball joint outcomes.
            r['rng_yuzde']=round(RNG_JOINT*100,5)
            r['rng_fark_puan']=round(r['rng_iki_sayi_fark_puan'],5)
    summary['sinif_test']=[r for r in classes if r['donem']=='TEST']
    summary['imza_11_egitimden_secilen']=len(selected)
    guide=("V35 — 80 SAYI ICIN 11 CEKILIS CIFT KARAKTER YOLCULUGU\n"
      "==============================================================\n"
      "Her sayı için son 11 GERCEK cekilişte 1=CIKAN20, 0=CIKMAYAN60 imzası.\n"
      "11de 6+ görünme H6 ve üst üste 6+ görünmeme A6 iki AYRI karakterdir.\n"
      "Aynı sayi AYNI 11 çekilişte H6 ile A6 olamaz: en az 12 pozisyon gerekir.\n"
      "Ancak AYNI çekilişte FARKLI sayılardan H6 ve A6 grupları bulunabilir;\n"
      "bu iki grubun sayıları sonraki gerçek çekilişte birlikte göründü mü ayrı izlendi.\n"
      "Egitim=ilk 36 tam gün, Test=sonraki 36 tam gün; yalnız eğitim verisiyle\n"
      "seçilen 11 haneli imzalar sonradan test dönemi üzerinde ölçüldü.\n"
      "11'li pencere gün içinde ve eksik kayıt aralıklarında kırılır.\n"
      "01:02 ile 07:02 arasında çekiliş yoktur, 13.->14. gerçek çekiliş ardışıktır.\n"
      "Tam 11 kayıt olmayan bir pencereye sahte 0/1 eklenmez.\n"
      "Her durum çekiliş SONRASI kaydedilir; sonraki çekiliş gerçek isabeti\n"
      "yalnız değerlendirme etiketidir, durum üretiminde ASLA kullanılmaz.\n"
      "Bir sayı için gelecek şansı %25; farklı iki sayının aynı 20'de birlikte\n"
      "gelmesi olasılığı (20*19)/(80*79)=~%6,01266'dır.\n"
      "İç içe kayan 11'li pencereler birbirine bağımlıdır; küçük farklara\n"
      "bakıp RNG karakterini çözdüğümüzü veya kupon üstünlüğünü iddia etmeyiz.\n"
      "V32 döngü ve V28 sıcaklık durumları da sadece çekiliş SONRASINDA bilinir.\n"
      "Arşivde milyonun üzerinde sayı-kesit satırı yer alır, ZIP büyük olabilir.\n"
      f"Özet: {json.dumps({k:v for k,v in summary.items() if k!='sinif_test'},ensure_ascii=False,indent=2)}\n")
    files={
      '00_OZET_VE_KURALLAR.txt':guide.encode('utf-8-sig'),
      '02_HER_CEKILIS_80_SAYI_KARAKTER_IMZASI.csv':csv_bytes(window_rows),
      '03_11DE_0DAN11E_GELECEK_ISABET.csv':csv_bytes(freq),
      '04_5_KARAKTER_EGITIM_TEST_GERI_DONUS.csv':csv_bytes(classes),
      '05_KARAKTER_6_ISI_V32_GORULME_KESISIM.csv':csv_bytes(fullcross),
      '06_KARAKTER_8_BANT_DAGILIM.csv':csv_bytes(bands),
      '07_KARAKTER_YON_ARTIS_AZALIS.csv':csv_bytes(trend),
      '08_11_BIT_IMZA_SONRAKI_CEKILIS_ISABET.csv':csv_bytes(signatures),
      '09_KARAKTERLER_ARASI_GECISLER.csv':csv_bytes(transitions),
      '10_YOGUN_VE_BEKLEYEN_SAYI_CIFTLERI.csv':csv_bytes(pairnums),
      '11_YOGUN_BEKLEYEN_8_BANT_CIFTLERI.csv':csv_bytes(pairbands),
      '12_YOGUN_BEKLEYEN_ISI_CIFTLERI.csv':csv_bytes(pairheat),
      '13_TUM_DURUMDAN_SONRAKI_BIRLIKTE_CIKAN_CIFTLER.csv':csv_bytes(pair_rows),
      '14_EGITIMDEN_SECILEN_IMZALAR_TEST.csv':csv_bytes(selected),
      '15_GUNLUK_CIFT_KARAKTER_DAVRANISI.csv':csv_bytes(daily_rows),
      '16_OZET.json':json.dumps(summary,ensure_ascii=False,indent=2).encode('utf-8'),
      '17_VERI_UYARILARI.txt':('\n'.join(errors) or 'Sorun yok').encode('utf-8-sig')}
    for name,data in files.items():z.writestr(name,data)
    return out.getvalue(),summary,classes,freq,selected


def from_text(text,**options):
    from v11_arastirma import read_draws
    draws,bad=read_draws(text)
    out,summary,classes,freq,selected=study(draws,**options)
    summary['ayristirma_uyarilari']=len(bad)
    return out,summary,classes,freq,selected
