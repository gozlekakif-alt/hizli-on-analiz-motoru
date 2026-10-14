# -*- coding: utf-8 -*-
"""V34 — exact 6..11+ waiting x V28 six heat seats x V32 seen/unseen
cross-tab and next-draw return. Predeclared primary: wait=8 + SOGUK +
DONGUDE_HENUZ_GORULMEDI versus remaining wait=8. Inference by day-block
bootstrap; train/test chronological. The next draw NEVER influences features.
"""
from __future__ import annotations
import csv
import io
import json
import random
import statistics
import zipfile
from collections import Counter, defaultdict
from v33_bekleme_havuzlari import run_study
from v32_80_tamamlama import csv_bytes

WAITS=('6','7','8','9','10','11+')
HEATS=('SOGUK','SOGUGA_YAKIN','ORTA','ILIK','SICAGA_YAKIN','SICAK')
SEEN='DONGUDE_GORULDU'
UNSEEN='DONGUDE_HENUZ_GORULMEDI'
A='8_SOGUK_HENUZ_GORULMEDI'
B='8_DIGERLERI'
SEED=34082026


def groups_of(r):
    w,heat,seen=r['sinif'],r['isi'],r['v32_havuz']
    p=[]
    if w == '8':
        p.append(A if heat=='SOGUK' and seen==UNSEEN else B)
        p.append('8_SOGUK' if heat=='SOGUK' else '8_SOGUK_DEGIL')
        p.append('8_HENUZ_GORULMEDI' if seen==UNSEEN else '8_ZATEN_GORULDU')
        if heat=='SOGUK':
            p.append('8_SOGUK_'+('HENUZ_GORULMEDI' if seen==UNSEEN else 'GORULDU'))
        else:
            p.append('8_SOGUK_OLMAYAN_'+('HENUZ_GORULMEDI' if seen==UNSEEN else 'GORULDU'))
    p.extend(('BEKLEME_'+w, 'BEKLEME_'+w+'_'+heat,
              'BEKLEME_'+w+'_'+('HENUZ' if seen==UNSEEN else 'GORULDU'),
              'KESISIM_'+w+'_'+heat+'_'+('HENUZ' if seen==UNSEEN else 'GORULDU')))
    return set(p)


def rows_from_v33(zipped):
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        data=z.read('07_BEKLEYENDEN_SONRAKI_CEKILIS_GERCEK_HIT.csv')
    return csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter=';')


def row_group(r):
    return 'SOGUK_HENUZ' if r['isi']=='SOGUK' and r['v32_havuz']==UNSEEN else 'DIGER'


def pct(a,b):
    return round(100*a/b,4) if b else ''


def quantile(vals,p):
    if not vals:return None
    x=sorted(vals)
    f=(len(x)-1)*p
    i=int(f)
    j=min(i+1,len(x)-1)
    return x[i]+(x[j]-x[i])*(f-i)


def day_block_ci(daycounts,group_a,group_b=None,reps=2000,seed=SEED):
    """Bootstrap full days to account for within-day serial dependence."""
    days=sorted(daycounts)
    if len(days)<2:return None
    rng=random.Random(seed)
    vals=[]
    for _ in range(reps):
        total=[0,0,0,0]
        for __ in days:
            d=daycounts[days[rng.randrange(len(days))]]
            ac,ah=d.get(group_a,(0,0))
            total[0]+=ac;total[1]+=ah
            if group_b is not None:
                bc,bh=d.get(group_b,(0,0))
                total[2]+=bc;total[3]+=bh
        if total[0]==0 or (group_b is not None and total[2]==0):
            continue
        v=total[1]/total[0]
        if group_b is None:v-=.25
        else:v-=total[3]/total[2]
        vals.append(v*100)
    if len(vals)<reps//2:return None
    return (round(quantile(vals,.025),3),round(quantile(vals,.975),3))


def run_cross(draws,include_partial=False,reps=2000,progress=None):
    v33, v33stats,_,_,_=run_study(draws,include_partial=include_partial,progress=progress)
    cutoff=v33stats['test_baslangic']
    by_group=defaultdict(lambda:[0,0])
    daily=defaultdict(lambda:defaultdict(lambda:[0,0]))
    detailed=defaultdict(lambda:[0,0])
    by_number=defaultdict(lambda:[0,0])
    fullrisk=[]
    primary_days=defaultdict(lambda:defaultdict(lambda:[0,0]))
    benchmark=['8_SOGUK', '8_SOGUK_DEGIL','8_HENUZ_GORULMEDI',
               '8_ZATEN_GORULDU','8_SOGUK_GORULDU','8_SOGUK_OLMAYAN_HENUZ_GORULMEDI',
               '8_SOGUK_OLMAYAN_GORULDU']
    for r in rows_from_v33(v33):
        day=r['gun'];period='EGITIM' if day<cutoff else 'TEST'
        observed=int(r['ertesi_cekiliste_cikti'])
        k=r['sinif'];heat=r['isi'];pool=r['v32_havuz'];band=r['bant']
        name=A if k=='8' and heat=='SOGUK' and pool==UNSEEN else B
        for g in groups_of(r):
            row=by_group[(period,g)]
            row[0]+=1;row[1]+=observed
            row=daily[(period,day)][g]
            row[0]+=1;row[1]+=observed
        dkey=(period,k,heat,pool,band)
        detail=detailed[dkey];detail[0]+=1;detail[1]+=observed
        if k=='8':
            bn=by_number[(period,name,int(r['sayi']))]
            bn[0]+=1;bn[1]+=observed
        if k=='8':
            main=primary_days[(period,day)][name]
            main[0]+=1;main[1]+=observed
            fullrisk.append({'donem':period,'gun':day,'sira':r['kaynak_sira'],
              'hedef_sira':r['hedef_sira'],'sayi':r['sayi'],'sinif':k,'isi':heat,
              'v32_havuz':pool,'bant':band,'sinif_kesisim':name,'sonraki_cekiliste_cikti':observed})
    summary=[]
    for (period,g),(n,hits) in sorted(by_group.items()):
        summary.append({'donem':period,'grup':g,'gozlem':n,'ertesi_cekiliste_gelen':hits,
             'gercek_yuzde':pct(hits,n),'rng_yuzde':25.0,
             'rng_beklenen':round(n*.25,2),'rng_fark_yuzde_puan':round(100*(hits/n-.25),3)})
    cross=[]
    for (period,k,heat,pool,band),(n,hits) in sorted(detailed.items()):
        cross.append({'donem':period,'bekleme':k,'isi':heat,'v32_dongu_havuzu':pool,
          'bant':band,'gozlem':n,'sonraki_cekiliste_cikti':hits,
          'gercek_yuzde':pct(hits,n),'rng_yuzde':25.0,
          'rng_fark_yuzde_puan':round(100*(hits/n-.25),3)})
    number=[]
    for (period,g,n),(count,hits) in sorted(by_number.items()):
        number.append({'donem':period,'alt_havuz':g,'sayi':n,
             'gozlem':count,'ertesi_cekiliste_cikti':hits,
             'gercek_yuzde':pct(hits,count),'rng_yuzde':25.0})
    comparisons=[]
    for period in ('EGITIM','TEST'):
        ds={day:groups for (pp,day),groups in daily.items() if pp==period}
        comparisons_to_test=[
            (A,B,'8 çekiliş soğuk + henüz görülmemiş / diğer 8 çekiliş bekleyenler'),
            (A,'8_SOGUK_GORULDU','Soğuk + henüz görülmemiş / soğuk + görülmüş'),
            (A,'8_SOGUK_OLMAYAN_HENUZ_GORULMEDI','Soğuk + henüz görülmemiş / diğer ısı + henüz görülmemiş'),
            (A,None,'Soğuk + henüz görülmemiş / RNG %25'),
            ('8_HENUZ_GORULMEDI','8_ZATEN_GORULDU','8 bekleyen döngüde henüz görülmemiş / zaten görülmüş'),
            ('8_SOGUK','8_SOGUK_DEGIL','8 bekleyen soğuk / diğer ısılar'),
        ]
        for i,(a,b,description) in enumerate(comparisons_to_test):
            an,ah=by_group.get((period,a),(0,0))
            if b is None:bn,bh=0,0;baseline=.25
            else:
                bn,bh=by_group.get((period,b),(0,0))
                baseline=bh/bn if bn else None
            dif=100*(ah/an-baseline) if an and baseline is not None else None
            ci=day_block_ci(ds,a,b,reps=reps,seed=SEED+i)
            comparisons.append({'donem':period,'karsilastirma':description,
                'hedef_sinif':a,'hedef_gozlem':an,'hedef_isabet':ah,
                'hedef_yuzde':pct(ah,an),
                'karsilastirma_sinifi':b or 'RNG_25',
                'diger_gozlem':bn if b else '',
                'diger_isabet':bh if b else '',
                'diger_yuzde':pct(bh,bn) if b else 25.0,
                'fark_yuzde_puan':round(dif,3) if dif is not None else '',
                'gun_blok_bootstrap_alt_95':ci[0] if ci else '',
                'gun_blok_bootstrap_ust_95':ci[1] if ci else '',
                'gun_sayisi':len(ds)})
    # Preselect up to 8 high/low combined signals using ONLY the first 36 days.
    # No test day is considered in candidate selection. This is exploratory.
    ranked=[]
    for (period,g),(n,hits) in by_group.items():
        if period=='EGITIM' and g.startswith('KESISIM_') and n>=200:
            ranked.append((abs(hits/n-.25),g,n,hits))
    ranking=[]
    for _,g,n,hits in sorted(ranked,reverse=True)[:8]:
        tn,th=by_group.get(('TEST',g),(0,0))
        ranking.append({'egitimde_secilen_kesisim':g,
            'egitim_gozlem':n,'egitim_yuzde':pct(hits,n),
            'test_gozlem':tn,'test_yuzde':pct(th,tn),
            'test_rng_fark_yuzde_puan':round(100*(th/tn-.25),3) if tn else '',
            'test_etiket_sadece_degerlendirmede':'EVET'})
    byday=[]
    for (p,day),arr in sorted(primary_days.items()):
        a,ah=arr.get(A,(0,0));b,bh=arr.get(B,(0,0))
        byday.append({'donem':p,'gun':day,'hedef_gozlem':a,'hedef_isabet':ah,
           'diger8_gozlem':b,'diger8_isabet':bh,'hedef_yuzde':pct(ah,a),
           'diger8_yuzde':pct(bh,b),
           'fark_yuzde_puan':round(100*(ah/a-bh/b),3) if a and b else ''})
    primarytest=next((r for r in comparisons if r['donem']=='TEST' and r['hedef_sinif']==A and r['karsilastirma_sinifi']==B),None)
    stats={'v33_tam_gun':v33stats['tam_gun'],
           'gercek_cekilis':v33stats['cekilis'],
           'risk_gozlemi':sum(1 for _ in rows_from_v33(v33)),
           '8_bekleme_risk_kaydi':len(fullrisk),
           'test_baslangic':cutoff,'birincil_kesisim':A,
           'test_birincil_karsilastirma':primarytest,
           'gunluk_bootstrap_tekrar':reps,
           'uc_nokta':'Bekleme 8 + SOGUK + V32 80/80 dongusunde henuz gorulmemis'}
    readme=("V34 — BEKLEME × 6 ISI × V32 GORULDU / GORULMEDI × 8 BANT\n"
      "======================================================\n"
      "Önceden seçilmiş hedef: 8 gerçek çekiliş gelmemiş, SOGUK sınıfında,\n"
      "V32 çıkan20 80/80 döngüsünde HENÜZ GÖRÜLMEMİŞ olan sayı.\n"
      "Karşılaştırma grubu: aynı anda sekiz çekiliştir gelmemiş DİĞER bütün sayılar.\n"
      "Isı: son gözlenen çekiliş SONRASI ölçülür; hedef sonraki gerçek çekiliştir.\n"
      "80/80 döngü görülme sınıfı ile bireysel bekleme sınıfı farklıdır.\n"
      "Saat boşluğu 01:02→07:02 sahte çekiliş üretmez.\n"
      "72 tam günün tarihçe ilk 36'sı EGITIM, sonraki 36'sı TEST.\n"
      "Günleri tam küme olarak tekrar örnekleyen bootstrap 95%% ARALIĞI\n"
      "ölçüm belirsizliğine dair yaklaşık aralıktır; bunlar önceden bağımsız\n"
      "olarak belirlenmiş hipotezlerle yürütülmüş doğrulayıcı testler değildir.\n"
      "Alt gruplar iç içe geçmiş gözlemler içerir. 8 banda, 6 ısıya ve 6 bekleme\n"
      "sınıfına göre çoklu karşılaştırma taraması yanıltıcı zirveler üretebilir.\n"
      "Bütün oranlar gerçekleşmiş hedeflerden gelir; gelecek çekiliş asla giriş\n"
      "özelliği olarak kullanılmaz. Bir sayının RNG altında şansı sabit %%25'tir.\n"
      "Gerçek RNG'nin aşılmış olduğu veya kupon avantajı sağlandığı iddia edilmez.\n"
      "Github veri.txt eksik günleri varsayılan olarak değerlendirme dışıdır.\n"
      f"Kısa sonuç: {json.dumps(stats,ensure_ascii=False,indent=2)}\n")
    files={'V34_00_KURALLAR_VE_SONUC.txt':readme.encode('utf-8-sig'),
        'V34_01_ONCEDEN_SECILEN_8_SOGUK_HENUZ_TEST.csv':csv_bytes(comparisons),
        'V34_02_EGITIM_TEST_6_7_8_9_10_11_ISI_DONGU.csv':csv_bytes(summary),
        'V34_03_BEKLEME_ISI_DONGU_BANT_TUM_KESISIM.csv':csv_bytes(cross),
        'V34_04_8_BEKLEME_HER_SAYI_CIKIS_PERFORMANSI.csv':csv_bytes(number),
        'V34_05_8_BEKLEME_HER_GUN_KARSILASTIRMA.csv':csv_bytes(byday),
        'V34_06_EGITIMDE_SECILEN_8_KESISIM_TESTI.csv':csv_bytes(ranking),
        'V34_07_8_BEKLEYEN_RISK_OLAYLARI.csv':csv_bytes(fullrisk),
        'V34_08_OZET.json':json.dumps(stats,ensure_ascii=False,indent=2).encode('utf-8')}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        with zipfile.ZipFile(io.BytesIO(v33)) as v:
            for name in v.namelist():z.writestr('V33_TEMEL/'+name,v.read(name))
        for name,content in files.items():z.writestr(name,content)
    return out.getvalue(),stats,comparisons,summary,ranking


def run_text(text,**opts):
    from v11_arastirma import read_draws
    a,errors=read_draws(text)
    return run_cross(a,**opts)
