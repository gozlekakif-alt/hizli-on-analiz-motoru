# -*- coding: utf-8 -*-
"""V32: exact 80-of-80 renewal cycles for observed 20 and absent 60.

Daily reset: 00:02; positions 1..13 are 00:02..01:02; 14..217
are 07:02..23:57. Position 13->14 is one DRAW step but six hours
in wall clock. On an 80/80 closure reset only AFTER processing the
closing draw. Missing positions are UNKNOWN, never treated as absent.

RNG reference is independent uniform sampling of 20/80 per recorded slot;
cycle closure is a descriptive statistic, not evidence of predictability.
"""
from __future__ import annotations
import csv
import io
import json
import random
import statistics
import zipfile
from collections import Counter, defaultdict
from datetime import datetime

BALLS = range(1, 81)
FULL_MASK = (1 << 80) - 1
KINDS = ('CIKAN_20', 'CIKMAYAN_60')


def clock(p):
    if not 1 <= p <= 217:
        raise ValueError('Çekiliş sıra numarası 1..217 dışında')
    minute = 2 + 5 * (p-1) if p <= 13 else 422 + 5 * (p-14)
    return f'{minute//60:02d}:{minute%60:02d}'


def hour_info(p):
    if p == 13:
        return '01:02 tek çekiliş', 'EK'
    if p <= 12:
        return '00:02', 'H'+str(p)
    h = (p-14)//12
    return f'{h+7:02d}:02', 'H'+str(1+(p-14)%12)


def mask_numbers(mask):
    return [i+1 for i in range(80) if mask & (1<<i)]


def csv_bytes(rows):
    if not rows:
        return '\ufeff'.encode('utf-8')
    cols = list(rows[0])
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, cols, delimiter=';', extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


def _cycle(day, segment, kind, num, start, first_id):
    return {'gun':day, 'parca':segment, 'havuz':kind, 'dongu':num,
            'ilk_sira':start, 'ilk_cekilis_no':first_id, 'gorulen':0,
            'adim':0, 'first':[0]*81, 'count':[0]*81,
            'new_path':[], 'ilk_zaman':clock(start)}


def _close(c, end_pos, end_id, reason, cycle_rows, number_rows):
    complete = c['gorulen'] == FULL_MASK
    cy = {key:c[key] for key in ('gun','parca','havuz','dongu','ilk_sira','ilk_cekilis_no')}
    cy.update({'son_sira':end_pos, 'son_cekilis_no':end_id,
        'baslangic_saat':c['ilk_zaman'], 'bitis_saat':clock(end_pos),
        'adim_sayisi':c['adim'], 'gorulen_farkli':c['gorulen'].bit_count(),
        'eksik_sayi':80-c['gorulen'].bit_count(),
        'tamamlandi':int(complete), 'bitis_nedeni':reason,
        'ilk_kez_gelenler_sirasi':','.join(map(str,c['new_path'])),
        'son_adimda_ilk_gelen':','.join(map(str,[n for n in BALLS if c['first'][n]==c['adim']]))})
    cycle_rows.append(cy)
    for n in BALLS:
        number_rows.append({'gun':c['gun'],'parca':c['parca'],'havuz':c['havuz'],
            'dongu':c['dongu'],'sayi':n,'ilk_gorulme_adimi':c['first'][n] or '',
            'ilk_gorulme_sirasi':(c['ilk_sira']+c['first'][n]-1) if c['first'][n] else '',
            'dongu_ici_tekrar':c['count'][n], 'tamamlandi':int(complete)})


def _segments(draws, include_partial):
    byday = defaultdict(dict)
    errors = []
    for d in draws:
        day = str(d['day']); pos = int(d['pos']); ns = tuple(int(n) for n in d['nums'])
        if pos not in range(1,218) or len(ns)!=20 or len(set(ns))!=20 or min(ns)<1 or max(ns)>80:
            errors.append(f"Geçersiz çekiliş: {day} / {pos}")
            continue
        if day in byday and pos in byday[day]:
            errors.append(f"Mükerrer tarih/sıra: {day} / {pos}")
            continue
        byday[day][pos] = dict(d, pos=pos, day=day, nums=ns, mask=sum(1<<(n-1) for n in ns))
    full_days = [day for day, p in sorted(byday.items()) if len(p)==217 and set(p)==set(range(1,218))]
    partial = sorted(set(byday)-set(full_days))
    segments = []
    for day, pmap in sorted(byday.items()):
        if day in partial and not include_partial:
            continue
        part = []
        for p in sorted(pmap):
            if part and p != part[-1]['pos']+1:
                segments.append((day, len(segments)+1, part))
                part=[]
            part.append(pmap[p])
        if part:
            segments.append((day, len(segments)+1, part))
    return segments, full_days, partial, errors


def _process(segments, progress=None):
    draw_rows, cycle_rows, number_rows, band_rows = [], [], [], []
    day_counts = Counter()
    for index, (day, segment, items) in enumerate(segments):
        day_counts[day] += len(items)
        active = {kind:None for kind in KINDS}
        cycle_n = Counter()
        previous = None
        for d in items:
            p = d['pos']; no=int(d['no']); active_mask = d['mask']; absent_mask = FULL_MASK ^ active_mask
            hour, local_h = hour_info(p)
            overlap = (active_mask & previous['mask']).bit_count() if previous else ''
            draw = {'gun':day, 'parca':segment, 'sira':p,'saat':clock(p),
                    'saat_baslangic':hour, 'saat_ici_adim':local_h,'cekilis_no':no,
                    'gelen20':','.join(map(str,mask_numbers(active_mask))),
                    'onceki_cekilisten_tekrar_20':overlap,
                    'onceki_cekilisten_yeni_20':(20-overlap if previous else ''),
                    'tek_sayi_adedi':sum((n%2)!=0 for n in mask_numbers(active_mask)),
                    'alt40':(active_mask & ((1<<40)-1)).bit_count()}
            for kind, mask in (('CIKAN_20',active_mask),('CIKMAYAN_60',absent_mask)):
                if active[kind] is None:
                    cycle_n[kind]+=1
                    active[kind]=_cycle(day,segment,kind,cycle_n[kind],p,no)
                c=active[kind]
                before = c['gorulen']
                fresh_mask = mask & ~before
                new = fresh_mask.bit_count()
                c['gorulen'] |= mask
                c['adim'] += 1
                c['new_path'].append(new)
                for n in mask_numbers(mask):
                    c['count'][n] += 1
                    if c['first'][n]==0:
                        c['first'][n]=c['adim']
                base = 'cikan20' if kind=='CIKAN_20' else 'cikmayan60'
                draw[base+'_dongu']=c['dongu']
                draw[base+'_adim']=c['adim']
                draw[base+'_once_gorulen']=before.bit_count()
                draw[base+'_ilk_kez']=new
                draw[base+'_tekrar']=mask.bit_count()-new
                draw[base+'_toplam_farkli']=c['gorulen'].bit_count()
                draw[base+'_kalan']=80-c['gorulen'].bit_count()
                draw[base+'_tamamlandi']=int(c['gorulen']==FULL_MASK)
                for band in range(8):
                    zone=((1<<10)-1) << (10*band)
                    band_rows.append({'gun':day,'parca':segment,'sira':p,'cekilis_no':no,
                        'havuz':kind,'dongu':c['dongu'],'adim':c['adim'],
                        'bant':f'{band*10+1:02d}-{band*10+10:02d}',
                        'bu_cekiliste_gelen':(mask&zone).bit_count(),
                        'ilk_kez_gelen':(fresh_mask&zone).bit_count(),
                        'dongu_bandi_gorulen':(c['gorulen']&zone).bit_count()})
                if c['gorulen']==FULL_MASK:
                    _close(c,p,no,'80_TAMAMLANDI',cycle_rows,number_rows)
                    active[kind]=None  # reset begins at NEXT real draw
            draw_rows.append(draw)
            previous=d
        for kind,c in active.items():
            if c is not None:
                _close(c,items[-1]['pos'],int(items[-1]['no']),'PARCA_SONU_ACIK',cycle_rows,number_rows)
        if progress:
            progress(index+1, len(segments), 'Gerçek döngüler', day)
    return draw_rows,cycle_rows,number_rows,band_rows,day_counts


def _cycle_summary(cycles):
    rows=[]
    for kind in KINDS:
        cs=[c for c in cycles if c['havuz']==kind]
        comp=[c for c in cs if c['tamamlandi']]
        lens=[c['adim_sayisi'] for c in comp]
        dist=Counter(lens)
        at_risk=Counter()
        for c in cs:
            for k in range(1,c['adim_sayisi']+1):
                at_risk[k]+=1
        for length in sorted(set(at_risk)|set(dist)):
            rows.append({'havuz':kind,'adim':length,
                'en_az_bu_adima_ulasan_dongu':at_risk[length],
                'tam_bu_adimda_tamamlanan':dist[length],
                'tamamlanma_olasiligi_riskteki':round(dist[length]/at_risk[length],6) if at_risk[length] else '',
                'tamamlanan_dongu_toplami':len(comp), 'acik_kalan_dongu':len(cs)-len(comp),
                'tamamlanan_ortalama_adim':round(statistics.mean(lens),4) if lens else '',
                'tamamlanan_ortanca_adim':statistics.median(lens) if lens else ''})
    return rows


def _rng_run(segments, reps, rng_seed=32026014, progress=None):
    rng=random.Random(rng_seed)
    sims=[]
    for rep in range(reps):
        lengths=defaultdict(list)
        for day, segment, draws in segments:
            seen={kind:0 for kind in KINDS}
            steps={kind:0 for kind in KINDS}
            for _ in draws:
                mask = sum(1<<(n-1) for n in rng.sample(range(1,81),20))
                for kind,part in (('CIKAN_20',mask),('CIKMAYAN_60',FULL_MASK^mask)):
                    seen[kind] |= part
                    steps[kind] += 1
                    if seen[kind]==FULL_MASK:
                        lengths[kind].append(steps[kind])
                        seen[kind]=0
                        steps[kind]=0
        for kind in KINDS:
            a=lengths[kind]
            sims.append({'tekrar':rep+1,'havuz':kind,'bitmis_dongu':len(a),
                         'ortalama_adim':round(statistics.mean(a),6) if a else '',
                         'ortanca_adim':statistics.median(a) if a else ''})
        if progress:
            progress(rep+1,reps,'Bağımsız RNG karşılaştırması','')
    return sims


def _check_rng(cycles, sims):
    out=[]
    for kind in KINDS:
        empirical=[c['adim_sayisi'] for c in cycles if c['havuz']==kind and c['tamamlandi']]
        simulated=[float(x['ortalama_adim']) for x in sims if x['havuz']==kind and x['ortalama_adim']!='']
        value=statistics.mean(empirical) if empirical else None
        mean=statistics.mean(simulated) if simulated else None
        # A descriptive reference interval, not a formal p-value.
        out.append({'havuz':kind,'gercek_tamamlanan_dongu':len(empirical),
           'gercek_ortalama_adim':round(value,6) if value is not None else '',
           'rng_ortalama_adim':round(mean,6) if mean is not None else '',
           'rng_min_ortalama':min(simulated) if simulated else '',
           'rng_max_ortalama':max(simulated) if simulated else '',
           'rng_tekrar_sayisi':len(simulated),
           'rng_araligi_disinda':int(value<min(simulated) or value>max(simulated)) if simulated and value is not None else ''})
    return out


def analyze(draws, include_partial=False, rng_reps=30, progress=None):
    if not isinstance(rng_reps,int) or not 0<=rng_reps<=200:
        raise ValueError('RNG tekrar sayısı 0..200 arasında olmalı')
    segments,full,partial,errors=_segments(draws,include_partial)
    if not segments:
        raise ValueError('İncelenecek tam gün bulunamadı; eksik günleri dahil etmeyi seçebilirsin.')
    draw_rows,cycles,numbers,bands,day_count=_process(segments,progress)
    hist=_cycle_summary(cycles)
    rngs=_rng_run(segments,rng_reps,progress=progress) if rng_reps else []
    comparison=_check_rng(cycles,rngs)
    completed=Counter(c['havuz'] for c in cycles if c['tamamlandi'])
    average={kind:(statistics.mean([c['adim_sayisi'] for c in cycles if c['havuz']==kind and c['tamamlandi']]) if completed[kind] else None) for kind in KINDS}
    stats={'incelenen_tam_gun':len(set(day_count)&set(full)),
          'incelenen_eksik_gun':len(set(day_count)&set(partial)),
          'toplam_tam_gun':len(full), 'disarida_birakilan_eksik_gun':len(partial) if not include_partial else 0,
          'cekilis_sayisi':len(draw_rows),'parca_sayisi':len(segments),
          'tamamlanan_cikan20_dongusu':completed['CIKAN_20'],
          'tamamlanan_cikmayan60_dongusu':completed['CIKMAYAN_60'],
          'cikan20_ortalama_adim':round(average['CIKAN_20'],4) if average['CIKAN_20'] else None,
          'cikmayan60_ortalama_adim':round(average['CIKMAYAN_60'],4) if average['CIKMAYAN_60'] else None,
          'rng_tekrar':rng_reps,'veri_hatalari':len(errors)}
    days=[{'gun':day,'incelenen_cekilis':count,'tam_gun':int(day in full),
           'gunluk_beklenen':217,'eksik_kayit':217-count}
          for day,count in sorted(day_count.items())]
    readme=("V32 - 80 SAYI TAMAMLANMA DONGUSU\n"
        "=================================\n"
        "00:02..01:02 (13 çekiliş), 01:02 sonrası boşluk, 07:02..23:57 (204 çekiliş); günde 217 gerçek çekiliş.\n"
        "Her gün 00:02'de iki ayrı 80-sayı sayacı sıfırdan başlar.\n"
        "ÇIKAN_20: bir sayının gerçek çıkan yirmilide en az bir kez görünmesi;\n"
        "ÇIKMAYAN_60: bir sayının o çekilişte çıkmayan altmışlıda görünmesi.\n"
        "Her çekilişte yeni görülenlerin bitleri eklenir; 80/80 olunca o çekiliş kaydedilir,\n"
        "sıfırlama ancak sonraki çekilişten başlayarak yapılır.\n"
        "Gün sonundaki açık döngüler tamamlandı kabul edilmez; yeni gün sıfırdan başlar.\n"
        "Eksik pozisyonlar üzerinden asla atlama yapılmaz: veri kesildiğinde döngüler açık kapanır.\n"
        "13->14 ardışık GERÇEK çekiliş sayılır ama aralarında 6 saat zaman boşluğu vardır.\n"
        "Varsayılan: sadece 217 eksiksiz çekiliş olan günler.\n"
        "RNG: her kayıtlı anda bağımsız 20/80 simülasyonu; seçilen gün/parça sınırları aynıdır.\n"
        "RNG min/max bir resmi anlamlılık testi değildir; yalnızca referans aralığıdır.\n"
        "Bu rapor gelecek sayı veya 10'da10 tahmini değildir; davranışın geçmiş ölçümüdür.\n\n"
        f"Özet: {json.dumps(stats,ensure_ascii=False,indent=2)}\n")
    files={'00_OZET_VE_KURALLAR.txt':readme.encode('utf-8-sig'),
           '01_HER_CEKILIS_IKI_HAVUZ_DONGU.csv':csv_bytes(draw_rows),
           '02_80_TAMAMLANAN_VE_ACIK_DONGULER.csv':csv_bytes(cycles),
           '03_HER_DONGU_80_SAYI_ILK_GELIS.csv':csv_bytes(numbers),
           '04_1_2_3_4_N_ADIM_TAMAMLANMA.csv':csv_bytes(hist),
           '05_8_BANT_HER_ADIM_YOLCULUGU.csv':csv_bytes(bands),
           '06_INCELENEN_GUNLER.csv':csv_bytes(days),
           '07_RNG_BAGIMSIZ_KONTROL.csv':csv_bytes(rngs),
           '08_RNG_VE_GERCEK_KARSILASTIRMA.csv':csv_bytes(comparison),
           '09_VERI_UYARILARI.txt':('\n'.join(errors) or 'Sorun yok.').encode('utf-8-sig'),
           '10_OZET.json':json.dumps(stats,ensure_ascii=False,indent=2).encode('utf-8')}
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,raw in files.items():z.writestr(name,raw)
    return memory.getvalue(),stats,cycles,hist,comparison


def run_text(text, **kwargs):
    from v11_arastirma import read_draws
    draws,bad=read_draws(text)
    payload,stats,cycles,hist,comparison=analyze(draws,**kwargs)
    stats['ayristirma_hatalari']=len(bad)
    return payload,stats,cycles,hist,comparison
