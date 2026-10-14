# -*- coding: utf-8 -*-
"""V36 — 11-cekilis H6 surekliligi, 6..11+ bekleme ve sayilar arasi devirler.

A=H6: son 11 GERCEK cekiliste 6+ gorunme.
A2=H6: ardisik iki kayan 11'li pencerede de H6.
B=6,7,8,9,10,11+ gercek cekilis ust uste yok.
Gelecek h=1/2/3/6/9 yalniz SONUC olarak okunur.
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import io
import json
import zipfile

from v33_bekleme_havuzlari import clean_draws
from v11_arastirma import read_draws
from v32_80_tamamlama import clock

HORIZONS=(1,2,3,6,9)
MASK=(1<<11)-1
RNG_A0_B1=(60/80)*(20/79)

def wc(v):
    return str(v) if 6<=v<=10 else ('11+' if v>=11 else '')

def pct(n,v):
    return round(100*v/n,5) if n else None

def write_csv(z,name,rows,fields):
    buf=io.StringIO()
    w=csv.DictWriter(buf,fieldnames=fields,delimiter=';',extrasaction='ignore',lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    z.writestr(name,buf.getvalue().encode('utf-8-sig'))

def analyze(draws, include_partial=False):
    byday,full,errors=clean_draws(draws)
    days=sorted(byday) if include_partial else sorted(full)
    if not days: raise ValueError('Gecerli cekilis gunu yok')
    divider=days[len(days)//2]
    high=defaultdict(lambda:[0,0,0,0.])
    risk=defaultdict(lambda:[0,0])
    pairs=defaultdict(lambda:[0,0,0,0,0.])
    daily=[]
    examples=[]  # ALL A2+B pair states; no sampling or favorable-outcome filtering
    for day in days:
        phase='EGITIM' if day<divider else 'TEST'
        bypos=byday[day]
        gaps=[0]*81
        sig=[0]*81
        h6_age=[0]*81
        segment=0;previous=None
        found=Counter()
        for t in sorted(bypos):
            present=set(bypos[t]['nums'])
            if previous is not None and t!=previous+1:
                gaps=[0]*81;sig=[0]*81;h6_age=[0]*81;segment=0
            previous=t;segment+=1
            for n in range(1,81):
                hit=int(n in present)
                sig[n]=((sig[n]<<1)|hit)&MASK
                gaps[n]=0 if hit else gaps[n]+1
                h6_age[n]=(h6_age[n]+1 if segment>=11 and sig[n].bit_count()>=6 else 0)
            if segment<12 or any(t+h not in bypos for h in range(1,10)):
                continue
            found['windows']+=1
            future=[set(bypos[t+h]['nums']) for h in range(1,10)]
            next20=future[0]
            persist=[n for n in range(1,81) if h6_age[n]>=2]
            highs=[n for n in range(1,81) if h6_age[n]>=1]
            absent=[n for n in range(1,81) if gaps[n]>=6]
            context='VAR_H6_2PLUS' if persist else 'YOK_H6_2PLUS'
            count_context=('EN_AZ_IKI_H6_2PLUS_SAYI' if len(persist)>=2 else
                ('TEK_H6_2PLUS_SAYI' if len(persist)==1 else 'HIC_H6_2PLUS_SAYI_YOK'))
            simultaneous_context=('EN_AZ_IKI_H6_SAYI' if len(highs)>=2 else
                ('TEK_H6_SAYI' if len(highs)==1 else 'HIC_H6_SAYI_YOK'))
            found['persist_windows']+=bool(persist)
            found['persist_numbers']+=len(persist)
            found['waiting_numbers']+=len(absent)
            for a in highs:
                hit=int(a in next20)
                freq=sig[a].bit_count()
                without_first=freq-((sig[a]>>10)&1)
                stays=int(without_first+hit>=6)
                nullstay=1 if without_first>=6 else .25
                groups=['H6_GENEL', 'H6_YENI' if h6_age[a]==1 else 'H6_2PLUS',
                        'H6_ILK' if h6_age[a]==1 else ('H6_IKINCI' if h6_age[a]==2 else 'H6_UC_PLUS')]
                for group in groups:
                    v=high[(phase,group)]
                    v[0]+=1;v[1]+=hit;v[2]+=stays;v[3]+=nullstay
            for b in absent:
                first_return=next((h for h,drawn in enumerate(future,1) if b in drawn),None)
                for ctx in (context,count_context,simultaneous_context,'TUM_BAGLAMLAR'):
                    for wait in (wc(gaps[b]),'6PLUS_GENEL'):
                        for horizon in HORIZONS:
                            v=risk[(phase,ctx,wait,horizon)]
                            v[0]+=1
                            v[1]+=int(first_return is not None and first_return<=horizon)
            for a in persist:
                # H6 can fall only if removing oldest 1 leaves exactly five hits.
                requires_next_hit=(sig[a].bit_count()-((sig[a]>>10)&1))==5
                a_exits=int(requires_next_hit and a not in next20)
                for b in absent:
                    assert a!=b
                    b_returns=int(b in next20)
                    for wait in (wc(gaps[b]),'6PLUS_GENEL'):
                        v=pairs[(phase,wait)]
                        v[0]+=1
                        v[1]+=b_returns
                        v[2]+=a_exits
                        v[3]+=int(a_exits and b_returns)
                        v[4]+=RNG_A0_B1 if requires_next_hit else 0
                    if True:  # all pairs, including both-negative controls
                        examples.append({'gun':day,'donem':phase,'sira':t,
                          'saat':clock(t),'H6_A':a,'H6_suren_pencere':h6_age[a],
                          'H6_A_11de_kac':sig[a].bit_count(),'bekleyen_B':b,
                          'B_bekleme':gaps[b],'A_H6_dustu':a_exits,
                          'B_ertesi_geldi':b_returns,
                          'B_ilk_donus':next((h for h,d in enumerate(future,1) if b in d),'9dan_sonra')})
        if found['windows']:
            daily.append({'gun':day,'donem':phase,'olculen_pencere':found['windows'],
             'H6_2PLUS_olan_pencere':found['persist_windows'],
             'H6_2PLUS_sayi_olay':found['persist_numbers'],
             'B_6PLUS_sayi_olay':found['waiting_numbers']})
    hrows=[{'donem':p,'A_H6_karakteri':s,'olay':v[0],
        'ertesi_A_cikti':v[1],'ertesi_A_cikis_yuzde':pct(v[0],v[1]),
        'sonraki_pencerede_H6_kaldi':v[2],'H6_kalma_yuzde':pct(v[0],v[2]),
        'mekanik_H6_kalma_RNG_beklentisi':pct(v[0],v[3])}
        for (p,s),v in sorted(high.items())]
    rrows=[{'donem':p,'A_H6_2PLUS_baglam':c,'B_bekleme_sinifi':w,
        'gelecek_cekilis_ufku':h,'B_olay':v[0],'B_geri_geldi':v[1],
        'geri_donus_yuzde':pct(v[0],v[1]),
        'RNG_beklenen_yuzde':round(100*(1-.75**h),5),
        'RNG_fark_puan':round(100*(v[1]/v[0]-(1-.75**h)),5) if v[0] else None}
        for (p,c,w,h),v in sorted(risk.items())]
    prows=[{'donem':p,'B_bekleme_sinifi':w,'H6_A_B_cift_olayi':v[0],
         'B_ertesi_geldi':v[1],'B_ertesi_yuzde':pct(v[0],v[1]),
         'A_ertesi_H6dan_dustu':v[2],'A_dusus_yuzde':pct(v[0],v[2]),
         'A_duserken_B_geldi':v[3],'devir_yuzde':pct(v[0],v[3]),
         'RNG_devir_beklenen_yuzde':pct(v[0],v[4]),
         'RNG_fark_puan':round(100*(v[3]-v[4])/v[0],5) if v[0] else None}
         for (p,w),v in sorted(pairs.items())]
    overview={'tam_gun':len(full),'incelenen_gun':len(days),
      'test_ilk_gun':divider,'incelenen_pencere':sum(x['olculen_pencere'] for x in daily),
      'H6_2PLUS_olan_pencere':sum(x['H6_2PLUS_olan_pencere'] for x in daily),
      'hatali_satir':len(errors),
      'test_H6_2PLUS':next((x for x in hrows if x['donem']=='TEST' and x['A_H6_karakteri']=='H6_2PLUS'),None),
      'test_B_9_H6_2PLUS':next((x for x in rrows if x['donem']=='TEST' and x['A_H6_2PLUS_baglam']=='VAR_H6_2PLUS' and x['B_bekleme_sinifi']=='9' and x['gelecek_cekilis_ufku']==1),None),
      'test_B_6PLUS_H6_2PLUS':next((x for x in rrows if x['donem']=='TEST' and x['A_H6_2PLUS_baglam']=='VAR_H6_2PLUS' and x['B_bekleme_sinifi']=='6PLUS_GENEL' and x['gelecek_cekilis_ufku']==1),None),
      'test_A_B_devir':next((x for x in prows if x['donem']=='TEST' and x['B_bekleme_sinifi']=='6PLUS_GENEL'),None)}
    guide=('V36 A->B KARAKTER DEVIR ZINCIRI\n\n'
      'H6: Bir sayi son 11 cekiliste en az 6 kez gelmis.\n'
      'H6_2PLUS: Ayni sayi ardisik en az iki kayan 11 cekilislilik kesitte H6.\n'
      'Bu pencereler 10 cekilisi paylasir: surme etkisi mekaniktir.\n'
      'B: baska sayi 6,7,8,9,10 veya 11+ cekilis gelmemis.\n'
      'Analiz: H6 surerken B 1/2/3/6/9 cekilis icinde donuyor mu?\n'
      'Ve A H6dan DUSERKEN B ayni gelecek cekiliste geliyor mu?\n'
      'RNG B 1 sonraki cekiliste gelme=%25; h icinde donme=1-(.75)^h.\n'
      'A H6da kalma referansi mevcut 11li imzanin birinci hanesine\n'
      'gore 100% veya 25%: basit 25% referans kullanilamaz.\n'
      'A H6dan duserken B gelme referansi A imzasina gore 0 veya\n'
      'P(A gelmez,B gelir)=(60/80)*(20/79).\n'
      'Ilk yari EGITIM; ikinci yari TEST.\n'
      'Kayan pencereler ve sayi ciftleri bagimsiz degildir.\n'
      'Sonuc kupon ustunlugu veya RNG tahmini garantisi degildir.\n')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('00_OKU.txt',guide.encode('utf-8-sig'))
        write_csv(z,'01_GUNLUK.csv',daily,list(daily[0]) if daily else ['gun'])
        write_csv(z,'02_H6_SURME.csv',hrows,list(hrows[0]) if hrows else ['donem'])
        write_csv(z,'03_B_GERI_DONUS_UFKU.csv',rrows,list(rrows[0]) if rrows else ['donem'])
        write_csv(z,'04_A_DUSERKEN_B_GELME.csv',prows,list(prows[0]) if prows else ['donem'])
        write_csv(z,'05_TUM_SAYI_SAYI_DEVIRLER.csv',examples,list(examples[0]) if examples else ['gun'])
        z.writestr('06_OZET.json',json.dumps(overview,ensure_ascii=False,indent=2))
        z.writestr('07_VERI_HATALARI.txt','\n'.join(errors) or 'Yok')
    return out.getvalue(),overview,hrows,rrows,prows

def selftest():
    nums=[]
    for t in range(1,27):
        row=([1] if t<=6 or t in (12,13) else [])+list(range(3,23))
        nums.append({'day':'2026-10-01','pos':t,'nums':tuple(row[:20])})
    archive,meta,h,r,p=analyze(nums,include_partial=True)
    assert meta['incelenen_pencere']==27-12-9
    assert any(x['B_bekleme_sinifi']=='11+' for x in r)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert len(z.namelist())==8 and z.testzip() is None
    print('V36 synthetic PASS')

if __name__=='__main__':
    import sys
    selftest()
    if '--full' in sys.argv:
        raw=Path('veri.txt').read_text(encoding='utf-8-sig')
        draws,bad=read_draws(raw)
        artifact,meta,h,r,p=analyze(draws)
        assert meta['incelenen_gun']>=70
        filename='V36_KARAKTER_DEVIR_ZINCIRI_72_GUN_TEK_ZIP.zip'
        Path(filename).write_bytes(artifact)
        print('V36 FULL RESULT',json.dumps(meta,ensure_ascii=False))
        print('V36 H6 TEST',json.dumps([x for x in h if x['donem']=='TEST'],ensure_ascii=False))
        print('V36 WAIT TEST NEXT',json.dumps([x for x in r if x['donem']=='TEST' and x['gelecek_cekilis_ufku']==1],ensure_ascii=False))
        print('V36 HANDOVER TEST',json.dumps([x for x in p if x['donem']=='TEST'],ensure_ascii=False))
        print('V36 LAGS TEST',json.dumps([x for x in r if x['donem']=='TEST' and x['A_H6_2PLUS_baglam']=='VAR_H6_2PLUS' and x['B_bekleme_sinifi'] in ('6PLUS_GENEL','9')],ensure_ascii=False))
        print('V36 TWO-NUMBER TEST',json.dumps([x for x in r if x['donem']=='TEST' and x['gelecek_cekilis_ufku']==1 and x['B_bekleme_sinifi'] in ('6PLUS_GENEL','9') and x['A_H6_2PLUS_baglam'] in ('EN_AZ_IKI_H6_SAYI','TEK_H6_SAYI','EN_AZ_IKI_H6_2PLUS_SAYI','TEK_H6_2PLUS_SAYI')],ensure_ascii=False))
        print('V36 FILE',filename,len(artifact),'bytes')
