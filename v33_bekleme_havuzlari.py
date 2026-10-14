# -*- coding: utf-8 -*-
"""V33 80 number 6..10 consecutive real-draw absence, pools and reactivation.

Each day: absence streak resets at 00:02; gap 01:02->07:02 counts as
one transition; missing recorded slots break a streak, never guessed.
Temperature ranks use V28 six seats (13/13/14/14/13/13), EWMA half life
12 observed draws, computed POST draw and therefore available to the NEXT draw.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
import io, csv, json, math, statistics, zipfile
from v32_80_tamamlama import FULL_MASK, clock, _segments, csv_bytes

CLASSES = (6,7,8,9,10,11)  # 11 means 11+
SIX = ('SOGUK','SOGUGA_YAKIN','ORTA','ILIK','SICAGA_YAKIN','SICAK')
SIX_SIZES = (13,13,14,14,13,13)
DECAY = 0.5 ** (1/12)
BALLS = range(1,81)


def cname(k):
    return '11+' if k==11 else str(k)


def band(n):
    lo=((n-1)//10)*10+1
    return f'{lo:02d}-{lo+9:02d}'


def clockhour(p):
    if p==13:return '01:02_TEK'
    if p<=12:return '00:02'
    return f'{7+(p-14)//12:02d}:02'


def new_heat(scores, active):
    for n in BALLS:
        scores[n]=scores[n]*DECAY+int(n in active)
    ranked=sorted(BALLS,key=lambda n:(scores[n],n))
    out=['']*81
    offset=0
    for i,size in enumerate(SIX_SIZES):
        for n in ranked[offset:offset+size]:out[n]=SIX[i]
        offset+=size
    return out


def clean_draws(draws):
    byday=defaultdict(dict)
    err=[]
    for d in draws:
        try:
            day=str(d['day']);p=int(d['pos']);ns=tuple(int(n) for n in d['nums'])
            if p not in range(1,218) or len(ns)!=20 or len(set(ns))!=20 or any(n<1 or n>80 for n in ns):
                raise ValueError('invalid number or position')
            if p in byday[day]:raise ValueError('duplicate slot')
            byday[day][p]={**d,'day':day,'pos':p,'nums':ns}
        except Exception as exc:err.append(f"{d.get('day','?')} {d.get('pos','?')}: {exc}")
    dates=sorted(byday)
    full=[day for day in dates if set(byday[day])==set(range(1,218))]
    return byday,full,err


def run_study(draws, include_partial=False, progress=None):
    byday,full,errors=clean_draws(draws)
    fullset=set(full)
    dates=sorted(byday)
    selected=[day for day in dates if include_partial or day in fullset]
    if not selected:raise ValueError('İncelenecek tam gün yok. Eksik günü dahil et veya veri yükle.')
    midpoint=full[len(full)//2] if full else selected[len(selected)//2]
    scores=[0.]*81
    details=[];draw_rows=[];daily_rows=[];return_rows=[]
    risk_rows=[];pool_rows=[];heat_rows=[]
    daily_class_rows=[];matrix_rows=[]
    global_occupancy=Counter()
    distinct_daily=defaultdict(list)
    observed_classes=Counter()
    heat_occupancy=Counter()
    band_occupancy=Counter()
    cycle_occupancy=Counter()
    risk=defaultdict(lambda:[0,0])
    for day_i,day in enumerate(dates):
        pmap=byday[day]
        use=day in selected
        streak=[0]*81
        seen_cycle=0
        cycle=1
        previous=None
        inventory_previous=[]
        daily_unique={k:set() for k in CLASSES}
        daily_entry=Counter()
        day_occupancy=Counter()
        day_max=Counter()
        day_reactive=Counter()
        day_count=0
        for p in sorted(pmap):
            d=pmap[p]
            present=set(d['nums'])
            seis=new_heat(scores,present)
            if not use:continue  # excluded records still inform temperature memory
            if previous is not None and p!=previous+1:
                streak=[0]*81
                seen_cycle=0
                cycle+=1
                inventory_previous=[]
            if previous is not None and p==previous+1:
                for item in inventory_previous:
                    k=item['sinif']
                    yes=int(item['sayi'] in present)
                    for typ,val in (('TUMU','TUMU'),('ISI',item['isi']),
                                    ('BANT',item['bant']),('DONGU',item['v32_havuz'])):
                        counts=risk[(item['donem'],k,typ,val)]
                        counts[0]+=1
                        counts[1]+=yes
                    risk_rows.append({'gun':day,'kaynak_sira':previous,'hedef_sira':p,
                        'sayi':item['sayi'],'sinif':cname(k),'isi':item['isi'],
                        'bant':item['bant'],'v32_havuz':item['v32_havuz'],
                        'ertesi_cekiliste_cikti':yes})
            seen_cycle |= sum(1 << (n-1) for n in present)
            arrived_by_class=Counter()
            for n in present:
                old=streak[n]
                if old>=6:
                    k=min(old,11)
                    arrived_by_class[k]+=1
                    day_reactive[k]+=1
                    return_rows.append({'gun':day,'sira':p,'saat':clock(p),'sayi':n,
                        'bekleme_cekilis_sayisi':old,'son_bekleme_sinifi':cname(k),
                        'yeni_havuz':'CIKAN_20','bant':band(n),
                        'cikis_sonrasi_isi':seis[n],'v32_cikan20_dongu':cycle})
                streak[n]=0
            current={k:0 for k in CLASSES}
            inventory=[]
            for n in BALLS:
                if n in present:continue
                streak[n]+=1
                age=streak[n]
                if age<6:continue
                k=min(age,11)
                current[k]+=1
                day_occupancy[k]+=1
                global_occupancy[k]+=1
                daily_unique[k].add(n)
                if age<=11:
                    daily_entry[k]+=1
                    observed_classes[k]+=1
                position='DONGUDE_GORULDU' if seen_cycle & (1<<(n-1)) else 'DONGUDE_HENUZ_GORULMEDI'
                heat=seis[n]
                one={'gun':day,'donem':'EGITIM' if day<midpoint else 'TEST',
                     'sira':p,'saat':clock(p),'saat_baslangici':clockhour(p),
                     'cekilis_no':int(d['no']),'sayi':n,'bekleme':age,
                     'sinif':k,'isin_sinifi':heat,'bant':band(n),
                     'yarim':'1-40' if n<=40 else '41-80','anlik_havuz':'CIKMAYAN_60',
                     'v32_cikan20_dongu':cycle,'v32_havuz':position}
                details.append({**one,'sinif':cname(k)})
                inventory.append({'sayi':n,'donem':one['donem'],'sinif':k,'isi':heat,
                                  'bant':one['bant'],'v32_havuz':position})
                heat_occupancy[(k,heat)]+=1
                band_occupancy[(k,band(n))]+=1
                cycle_occupancy[(k,position)]+=1
            countrow={'gun':day,'sira':p,'saat':clock(p),'donem':'EGITIM' if day<midpoint else 'TEST',
                      'cekilis_no':int(d['no']),'bekleyen_6_uzeri':sum(current.values()),
                      'cikan_20':20,'cikmayan_60':60,'v32_cikan20_dongu':cycle}
            for k in CLASSES:
                countrow['bekleyen_'+cname(k)]=current[k]
                countrow['siniftan_cikan_'+cname(k)]=arrived_by_class[k]
                day_max[k]=max(day_max[k],current[k])
            draw_rows.append(countrow)
            day_count+=1
            previous=p
            inventory_previous=inventory
            if seen_cycle==FULL_MASK:
                seen_cycle=0
                cycle+=1
        if not use:continue
        overall=set().union(*daily_unique.values())
        daily_rows.append({'gun':day,'tam_gun':int(day in fullset),
            'kayit':day_count,'en_az_6_beklemeye_giren_farkli_sayi':len(overall),
            'hic_6_uzeri_olmayan_sayilar':','.join(map(str,sorted(set(BALLS)-overall)))})
        for k in CLASSES:
            dayrow={'gun':day,'sinif':cname(k),
                'farkli_sayi':len(daily_unique[k]), 'sinifa_giris_sayisi':daily_entry[k],
                'cekilis_basi_ortalama_mevcut':round(day_occupancy[k]/day_count,5),
                'ayni_anda_en_fazla':day_max[k],
                'bekleyisten_cikarak_20ye_donen':day_reactive[k]}
            daily_class_rows.append(dayrow)
            distinct_daily[k].append(len(daily_unique[k]))
        if progress:progress(day_i+1,len(dates),'V33 6–10 bekleyen sayı taraması',day)
    checked=len(draw_rows)
    totals=[]
    for k in CLASSES:
        x=distinct_daily[k]
        totals.append({'sinif':cname(k),'incelenen_gun':len(x),
           'gunluk_ortalama_farkli_sayi':round(statistics.mean(x),4),
           'en_az_gunluk_farkli_sayi':min(x),'en_fazla_gunluk_farkli_sayi':max(x),
           'tum_80_gorulen_gun':sum(v==80 for v in x),
           'cekilis_basi_ortalama_mevcut':round(global_occupancy[k]/checked,5),
           'sinifa_giris_tekrar_sayisi':observed_classes[k]})
    for (period,k,typ,val),arr in sorted(risk.items(),key=lambda x:str(x[0])):
        n,hits=arr
        matrix_rows.append({'donem':period,'sinif':cname(k),'grup':typ,'grup_adi':val,
           'ertesi_cekilis_risk_sayisi':n,'gercek_ertesi_20ye_donen':hits,
           'gercek_yuzde':round(100*hits/n,3),
           'rng_yuzde':25.0,'rng_beklenen_adet':round(n*.25,3),
           'yuzde_puan_fark':round(100*(hits/n-.25),3)})
    placement=[]
    for k in CLASSES:
        for n,v in sorted((n,v) for (kk,n),v in heat_occupancy.items() if kk==k):
            placement.append({'sinif':cname(k),'havuz_turu':'SICAKLIK_6','havuz':n,'sayi_cekim_adimi_sayisi':v})
        for n,v in sorted((n,v) for (kk,n),v in band_occupancy.items() if kk==k):
            placement.append({'sinif':cname(k),'havuz_turu':'8_BANT','havuz':n,'sayi_cekim_adimi_sayisi':v})
        for n,v in sorted((n,v) for (kk,n),v in cycle_occupancy.items() if kk==k):
            placement.append({'sinif':cname(k),'havuz_turu':'V32_CIKAN_20_DONGUSU','havuz':n,'sayi_cekim_adimi_sayisi':v})
        placement.append({'sinif':cname(k),'havuz_turu':'ANLIK_CIKAN_20','havuz':'0 (bekleyen sayı o çekilişte çıkmadı)','sayi_cekim_adimi_sayisi':0})
        placement.append({'sinif':cname(k),'havuz_turu':'ANLIK_CIKMAYAN_60','havuz':'EVET','sayi_cekim_adimi_sayisi':global_occupancy[k]})
    summary={'tam_gun':len(set(selected)&fullset),'eksik_gun':len(selected)-len(set(selected)&fullset),
             'cekilis':checked,'siniflar':totals,
             'her_cekiliste_ortalama_6_uzeri':round(sum(global_occupancy.values())/checked,5),
             'test_baslangic':midpoint,
             'detay_sayi_cekilis_kaydi':len(details),'ertesi_cekilis_kontrolu':len(risk_rows),
             'uyari_sayisi':len(errors)}
    guide=("V33 — 6,7,8,9,10 ve 11+ çekiliş üst üste GÖRÜNMEYEN SAYILAR\n"
      "================================================================\n"
      "Her sayının beklemesi, son görüldüğü çekilişten itibaren ardışık gerçek çekilişlerdeki yokluk sayısıdır.\n"
      "Günün 00:02 çekilişinde sayaç sıfırdan başlar (ilk görülmeyen çekiliş yaş=1).\n"
      "01:02 → 07:02 arası altı saat zaman geçse de BİR sonraki gerçek çekiliştir.\n"
      "Eksik çekiliş varsa seri burada kesilir, sayıların çıkmadığı varsayılmaz.\n"
      "6, 7, 8, 9, 10 sınıfları TAM sayıdadır; 11+ kalanları toplar.\n"
      "Aynı sayı bir günde farklı defalarda aynı sınıfa girebilir; farkli_sayi tekrarı saymaz.\n"
      "Bir çekiliş SONRASINDA bekleme>=6 olan sayı zorunlu CIKMAYAN_60 havuzundadır.\n"
      "Sayı yeni çekilişte göründüğünde bekleme biter ve CIKAN_20 havuzuna geçer.\n"
      "V28 altı ısı sınıfı: 12-çekiliş yarı ömürlü üstel ısı, günler arasında hafıza, 13/13/14/14/13/13 koltuk.\n"
      "Isı sınıfı o çekiliş sonucu görüldükten SONRA hesaplandığı için ancak SONRAKİ çekiliş tahmininde kullanılabilir.\n"
      "V32 görüldü/görülmedi: çıkan20 80/80 döngüsü içinde bir sayının daha önce gelip gelmediği.\n"
      "80/80 tamamlandığı çekilişten sonra bu döngü sıfırlanır; bireysel bekleme sayacı sıfırlanmaz.\n"
      "Risk: sınıftaki sayı bir sonraki gerçek çekilişte ÇIKAN_20'ye geçiyor mu? Günde son çekiliş sansürlüdür.\n"
      "RNG referansı: geçmiş ne olursa olsun her sayının bağımsız bir sonraki 20/80 çekilişte gelme şansı %25'tir.\n"
      "36/36 eğitim/test gün ayırımı gözlemseldir. Bant / ısı / bekleme kategorileri geçmişe göre seçildiğinden\n"
      "küçük farklar kupon üstünlüğü veya RNG çözümü sayılmaz. Geleceği test sonucu özelliklere ekleme.\n"
      f"Özet: {json.dumps(summary,ensure_ascii=False,indent=2)}\n")
    files={
     '00_OZET_VE_KURALLAR.txt':guide.encode('utf-8-sig'),
     '01_HER_CEKILISTE_6_7_8_9_10_11PLUS_MEVCUT.csv':csv_bytes(draw_rows),
     '02_HER_GUN_HER_SINIF_FARKLI_SAYI.csv':csv_bytes(daily_class_rows),
     '03_GUNLUK_6_UZERI_80_SAYI_CIZELGESI.csv':csv_bytes(daily_rows),
     '04_HER_BEKLEYEN_SAYI_ISI_BANT_V32_DONGU.csv':csv_bytes(details),
     '05_SINIFLARIN_6_ISI_8_BANT_V32_HAVUZ_DAGILIMI.csv':csv_bytes(placement),
     '06_BEKLEME_BITINCE_CIKAN20_YENIDEN_AKTIF.csv':csv_bytes(return_rows),
     '07_BEKLEYENDEN_SONRAKI_CEKILIS_GERCEK_HIT.csv':csv_bytes(risk_rows),
     '08_EGITIM_TEST_SINIF_ISI_BANT_RNG_KARSILASTIRMA.csv':csv_bytes(matrix_rows),
     '09_GENEL_SINIF_DAGILIMI.csv':csv_bytes(totals),
     '10_OZET.json':json.dumps(summary,ensure_ascii=False,indent=2).encode('utf-8'),
     '11_VERI_UYARILARI.txt':('\n'.join(errors) or 'Veri temiz.').encode('utf-8-sig')}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,value in files.items():z.writestr(name,value)
    return out.getvalue(),summary,matrix_rows,placement,daily_rows


def run_text(txt,**kw):
    from v11_arastirma import read_draws
    draws,bad=read_draws(txt)
    zipdata,summary,matrix,pools,days=run_study(draws,**kw)
    summary['gecersiz_kayit']=len(bad)
    return zipdata,summary,matrix,pools,days
