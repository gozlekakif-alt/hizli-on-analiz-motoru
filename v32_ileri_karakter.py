# -*- coding: utf-8 -*-
"""V32 second-stage, no-lookahead 4/8/12 snapshots and future heldout scoring.

Forecast baseline is exact independent sampling 20 of 80 (60 absent). No future
numbers enter any snapshot feature. Future results are read only as score labels.
A gap of missing *draw positions* terminates a segment. The scheduled 01:02
-> 07:02 break does not create fictional positions or change a draw count.
"""
from __future__ import annotations
from collections import defaultdict
from functools import lru_cache
from math import comb, sqrt
import io
import zipfile
from v32_80_tamamlama import FULL_MASK, BALLS, clock, _segments, analyze as v32_analyze, csv_bytes

CHECKS = (4, 8, 12)
HORIZONS = (1, 4, 8, 12)
KINDS = (('CIKAN_20', 20), ('CIKMAYAN_60', 60))


@lru_cache(maxsize=None)
def transitions(m, drawn):
    if m == 0:
        return ((0, 1.0),)
    denominator = comb(80, drawn)
    return tuple((m-j, comb(m,j)*comb(80-m,drawn-j)/denominator)
                 for j in range(max(0,drawn-(80-m)),min(m,drawn)+1))


@lru_cache(maxsize=None)
def chance_finish(m, drawn, horizon):
    if m == 0: return 1.0
    if horizon <= 0: return 0.0
    if horizon * drawn < m: return 0.0
    return max(0.0, min(1.0, sum(p*chance_finish(next_m,drawn,horizon-1)
                       for next_m,p in transitions(m,drawn))))


def band_counts(missing):
    return [sum(1 for n in missing if (n-1)//10 == i) for i in range(8)]


def speed_class(missing, k, drawn):
    expected=80*(1-((80-drawn)/80)**k)
    surplus=(80-missing)-expected
    return ('HIZLI' if surplus>2.5 else 'YAVAS' if surplus< -2.5 else 'ORTA'), surplus


def _cycle_snapshots(items, kind, drawn, phase):
    out, events, number_events = [],[],[]
    seen=0;cycle_no=0;first_pos=None;recent=[]
    for i,d in enumerate(items):
        if first_pos is None:
            cycle_no+=1;first_pos=d['pos'];seen=0;recent=[]
        mask=d['mask'] if drawn==20 else FULL_MASK^d['mask']
        new=(mask&~seen).bit_count()
        seen |= mask
        recent.append(new)
        step=len(recent)
        remaining=80-seen.bit_count()
        if step in CHECKS and remaining>0:
            missing=tuple(n for n in BALLS if not seen & (1<<(n-1)))
            bands=band_counts(missing)
            speed, surplus=speed_class(remaining,step,drawn)
            head={'gun':d['day'],'donem':phase,'havuz':kind,'dongu':cycle_no,
                'ilk_sira':first_pos,'kesit_adimi':step,'kesit_sira':d['pos'],
                'kesit_saati':clock(d['pos']),'cekilis_no':int(d['no']),
                'gorulen':seen.bit_count(),'eksik':remaining,
                'adim_yeni':new,'son_iki_yeni':sum(recent[-2:]),
                'son_dort_yeni':sum(recent[-4:]),
                'ilk_dort_yeni':sum(recent[:4]),
                'beklenen_gorulen':round(80*(1-((80-drawn)/80)**step),4),
                'hiz_farki':round(surplus,4),'hiz_sinifi':speed,
                'eksik_bant_en_yuksek':max(bands),
                'eksik_bant_dagilimi':','.join(map(str,bands)),
                'eksik_sayilar':','.join(map(str,missing))}
            future_seen=seen
            finish_after=None
            next_new=None
            for h in range(1,min(max(HORIZONS),len(items)-i-1)+1):
                next_draw=items[i+h]['mask']
                if drawn==60:next_draw=FULL_MASK^next_draw
                old=future_seen
                future_seen |= next_draw
                if h==1:next_new=(next_draw & ~old).bit_count()
                if future_seen==FULL_MASK:
                    finish_after=h;break
            head['sonraki_cekilis_yeni_sayi']=next_new if next_new is not None else ''
            head['sonraki_yeni_rng_beklenen']=round(remaining*drawn/80,4)
            head['kapanis_kac_adim_sonra']=finish_after if finish_after is not None else ''
            for h in HORIZONS:
                p=chance_finish(remaining,drawn,h)
                # 1: observed closure by h; 0: h observed draws and not closed;
                # blank: censored, never assume a missing future is a miss.
                if finish_after is not None and finish_after<=h:
                    label=1
                elif len(items)-i-1 >= h:
                    label=0
                else:label=''
                head[f'rng_{h}_olasilik']=round(p,9)
                head[f'gercek_{h}_icinde_tamamlama']=label
                if label != '':
                    events.append({**{k:head[k] for k in ('gun','donem','havuz','dongu','kesit_adimi','kesit_sira','eksik','hiz_sinifi','hiz_farki','eksik_bant_en_yuksek')},
                        'ileriki_cekim_adedi':h,'rng_olasilik':p,'tamamlandi':label})
            out.append(head)
            if next_new is not None:
                for n in missing:
                    hit=int(bool(items[i+1]['mask'] & (1<<(n-1))))
                    if drawn==60:hit=1-hit
                    number_events.append({'gun':d['day'],'donem':phase,'havuz':kind,
                       'kesit_adimi':step,'bant':f'{(n-1)//10*10+1:02d}-{((n-1)//10+1)*10:02d}',
                       'eksik_sayi':n,'sonraki_cekimde_geldi':hit,
                       'rng_beklenen':drawn/80})
        if seen==FULL_MASK:
            seen=0;first_pos=None;recent=[]
    return out,events,number_events


def _agg(events, by):
    groups=defaultdict(list)
    for r in events:
        groups[tuple(r[k] for k in by)].append(r)
    rows=[]
    for key,arr in sorted(groups.items()):
        obs=sum(r['tamamlandi'] for r in arr)
        exp=sum(r['rng_olasilik'] for r in arr)
        n=len(arr)
        variance=sum(p['rng_olasilik']*(1-p['rng_olasilik']) for p in arr)
        brier=sum((r['tamamlandi']-r['rng_olasilik'])**2 for r in arr)/n
        rows.append({**dict(zip(by,key)),'degerlendirilen':n,'gercek_tamamlanma':obs,
             'rng_beklenen_tamamlanma':round(exp,4),
             'gercek_oran_yuzde':round(100*obs/n,3),
             'rng_beklenen_oran_yuzde':round(100*exp/n,3),
             'fark_yuzde_puan':round(100*(obs-exp)/n,3),
             'rng_brier_hatasi':round(brier,8),
             'kesifsel_fark_z':round((obs-exp)/sqrt(variance),3) if variance else ''})
    return rows


def _number_agg(items):
    groups=defaultdict(list)
    for r in items:
        groups[(r['donem'],r['havuz'],r['kesit_adimi'],r['bant'])].append(r)
    rows=[]
    for (period,kind,step,band),group in sorted(groups.items()):
        hits=sum(x['sonraki_cekimde_geldi'] for x in group)
        n=len(group)
        p=group[0]['rng_beklenen']
        rows.append({'donem':period,'havuz':kind,'kesit_adimi':step,'bant':band,
          'gelecek_cekimde_sans':n,'gercek_sayi_isabeti':hits,
          'gercek_oran_yuzde':round(100*hits/n,3),
          'rng_beklenen_yuzde':round(p*100,3),
          'fark_yuzde_puan':round(100*(hits/n-p),3)})
    return rows


def _full_cycle_changes(rows):
    buckets=defaultdict(dict)
    for r in rows:
        buckets[(r['gun'],r['havuz'],r['dongu'],r['ilk_sira'])][r['kesit_adimi']]=r
    out=[]
    for (_,kind,cycle,start),segments in sorted(buckets.items()):
        for a,b in ((4,8),(8,12),(4,12)):
            if a in segments and b in segments:
                x,y=segments[a],segments[b]
                out.append({'gun':x['gun'],'havuz':kind,'dongu':cycle,'ilk_sira':start,
                     'ilk_kesit':a,'ikinci_kesit':b,'ilk_gorulen':x['gorulen'],
                     'son_gorulen':y['gorulen'],'arada_yeni_sayi':y['gorulen']-x['gorulen'],
                     'rng_kosullu_beklenen_yeni':round(x['eksik']*(1-(1-(20 if kind=='CIKAN_20' else 60)/80)**(b-a)),4),
                     'ilk_kesit_hiz':x['hiz_sinifi'],'son_kesit_hiz':y['hiz_sinifi']})
    return out


def run_deep(draws, include_partial=False, rng_reps=30, progress=None):
    base_zip,stats,cycles,hist,comparison=v32_analyze(draws,include_partial,rng_reps,progress)
    segments,full,partial,errors=_segments(draws,include_partial)
    full_sorted=sorted(full)
    if full_sorted:
        cutoff=full_sorted[len(full_sorted)//2]
    else:
        cutoff=sorted({d for d,_,_ in segments})[len(segments)//2]
    snapshots=[];events=[];number_events=[]
    for index,(day,_,items) in enumerate(segments):
        phase='EGITIM' if day<cutoff else 'TEST'
        for kind,drawn in KINDS:
            a,b,c=_cycle_snapshots(items,kind,drawn,phase)
            snapshots.extend(a); events.extend(b);number_events.extend(c)
        if progress: progress(index+1,len(segments),'4-8-12 çekilişten geleceğe',day)
    summary=_agg(events,['donem','havuz','kesit_adimi','ileriki_cekim_adedi'])
    variants=_agg(events,['donem','havuz','kesit_adimi','ileriki_cekim_adedi','hiz_sinifi'])
    bands=_number_agg(number_events)
    transitions=_full_cycle_changes(snapshots)
    plain=("V32 - 4/8/12 CIKAN20 + CIKMAYAN60 DONGU KARAKTERLERI\n"
        "================================================================\n"
        "Her gün 00:02'de döngü sıfırlanır, ayrıca 80/80 olduğu çekilişten SONRA tekrar başlar.\n"
        "13->14: saat 01:02->07:02 boşluğu atlanır; iki gerçek çekiliş ardışıktır.\n"
        "Eksik kayıt anında önceki döngü sansürlenir; sahte 'çıkmayan' eklenmez.\n"
        "4/8/12 anlık özellikleri GELECEĞİ bilmeden, yalnız o ana kadarki çekilişlerden hesaplanır.\n"
        "Kapanış hedefi: mevcut döngünün bir sonraki 1,4,8,12 gerçek çekilişte bitmesi.\n"
        "Cevap=1 ise erken bitiş bilinir; cevap=0 için h gerçek çekilişin tamamı gereklidir.\n"
        "Veri biten açık döngüler etiketsizdir, negatif sonuç gibi gösterilmez.\n"
        "RNG olasılıkları 20/80 veya 60/80 HİPERGEOMETRİK geçişlerinden TAM hesaplanır.\n"
        "EGITIM ve TEST ayrımı takvime göredir (ilk yarı/son yarı).\n"
        "RNG gözlemleriyle karşılaştırma, oyuncu öngörü performansı veya RNG kırma kanıtı değildir.\n"
        "Bant tablosu, 80/80 döngüsünde henüz görünmemiş her sayının sonraki gerçek çekilişte çıkma oranıdır.\n"
        "Sonuçların geçmiş veride keşifsel tarandığını unutma; çoklu karşılaştırma uyarısı geçerlidir.\n"
        f"Gün ortası ayırıcı tarih: {cutoff}; Kesit: {len(snapshots)}; Değerlendirilebilir hedef: {len(events)}.\n")
    extras={'11_4_8_12_ANLIK_DURUM_VE_GELECEK.csv':csv_bytes(snapshots),
         '12_EGITIM_TEST_RNG_KARSILASTIRMA.csv':csv_bytes(summary),
         '13_HIZLI_ORTA_YAVAS_AYRI_RNG.csv':csv_bytes(variants),
         '14_4_8_12_GECISLERI.csv':csv_bytes(transitions),
         '15_EKSIK_SAYI_BANT_ERTEKI_CEKILIS.csv':csv_bytes(bands),
         '16_CALISMA_KURALLARI.txt':plain.encode('utf-8-sig')}
    target=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base_zip)) as src, zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as dst:
        for name in src.namelist():dst.writestr(name,src.read(name))
        for name,data in extras.items():dst.writestr(name,data)
    stats={**stats,'4_8_12_kesit':len(snapshots),'degerlendirilen_gelecek_pencere':len(events),
           '4_8_12_test_ayrac_gun':cutoff}
    return target.getvalue(),stats,summary,variants,bands,snapshots


if __name__=='__main__':
    from pathlib import Path
    from v11_arastirma import read_draws
    txt=Path('veri.txt').read_text(encoding='utf-8-sig')
    a,_=read_draws(txt)
    blob,meta,summary,variants,_,_=run_deep(a,rng_reps=4)
    Path('V32_4_8_12_TEK_ZIP.zip').write_bytes(blob)
    print(meta)
    for row in summary:
        if row['donem']=='TEST' and row['havuz']=='CIKAN_20':print(row)
