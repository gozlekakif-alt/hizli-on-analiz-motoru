# -*- coding: utf-8 -*-
"""V33 tests: 6..10 absence, 60/20 pools, gaps and one ZIP."""
import csv
import io
import zipfile
import sys
from pathlib import Path
from v33_bekleme_havuzlari import run_study, clock


def draw(p, ns=None, day='2026-10-01'):
    return {'day':day, 'pos':p, 'no':300000+p,
            'dt':day+'T'+clock(p),
            'nums':tuple(ns if ns is not None else range(1,21))}


def unzipcsv(blob,name):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig')),delimiter=';'))


def test():
    data=[draw(p) for p in range(1,9)]+[draw(9,list(range(1,20))+[80])]
    archive,stats,matrix,pools,days=run_study(data,include_partial=True)
    state=unzipcsv(archive,'01_HER_CEKILISTE_6_7_8_9_10_11PLUS_MEVCUT.csv')
    assert [int(r['bekleyen_6']) for r in state[:7]]==[0,0,0,0,0,60,0]
    assert int(state[6]['bekleyen_7'])==60
    assert int(state[7]['bekleyen_8'])==60
    assert int(state[8]['bekleyen_9'])==59
    assert int(state[8]['cikan_20'])==20 and int(state[8]['cikmayan_60'])==60
    exits=unzipcsv(archive,'06_BEKLEME_BITINCE_CIKAN20_YENIDEN_AKTIF.csv')
    assert len(exits)==1 and exits[0]['sayi']=='80'
    assert exits[0]['bekleme_cekilis_sayisi']=='8'
    details=unzipcsv(archive,'04_HER_BEKLEYEN_SAYI_ISI_BANT_V32_DONGU.csv')
    assert all(r['anlik_havuz']=='CIKMAYAN_60' for r in details)
    assert all(r['isin_sinifi'] in ('SOGUK','SOGUGA_YAKIN','ORTA','ILIK','SICAGA_YAKIN','SICAK') for r in details)
    assert stats['cekilis']==9
    assert len(pools)>0 and len(matrix)>0
    # 01:02 -> 07:02 is next draw, not six hours of missing positions
    gap=[draw(p) for p in range(9,15)]
    z,st,_,_,_=run_study(gap,include_partial=True)
    rows=unzipcsv(z,'01_HER_CEKILISTE_6_7_8_9_10_11PLUS_MEVCUT.csv')
    assert int(rows[-1]['bekleyen_6'])==60
    # Missing slot breaks streak; no fake nonappearances
    missing=[draw(p) for p in [1,2,3,4,5,6,9]]
    z,st,_,_,_=run_study(missing,include_partial=True)
    rows=unzipcsv(z,'01_HER_CEKILISTE_6_7_8_9_10_11PLUS_MEVCUT.csv')
    assert int(rows[-1]['bekleyen_6'])==0
    # Next-draw check never crosses end-of-day
    data=[draw(p) for p in range(1,218)]+[draw(1,day='2026-10-02')]
    z,st,_,_,_=run_study(data,include_partial=True)
    rows=unzipcsv(z,'07_BEKLEYENDEN_SONRAKI_CEKILIS_GERCEK_HIT.csv')
    assert all(r['gun']=='2026-10-01' for r in rows)
    assert all(int(r['hedef_sira'])==int(r['kaynak_sira'])+1 for r in rows)
    assert st['tam_gun']==1
    assert st['eksik_gun']==1
    with zipfile.ZipFile(io.BytesIO(z)) as archive:
        assert len(archive.namelist())==12
        assert archive.testzip() is None
    print('V33 synthetic class, pool, six temperature, gaps and ZIP PASS')
    if '--full' in sys.argv:
        from v11_arastirma import read_draws
        from collections import Counter
        draws,bad=read_draws(Path('veri.txt').read_text(encoding='utf-8-sig'))
        z,meta,matrix,pools,daily=run_study(draws,include_partial=False)
        assert meta['tam_gun']>=1
        assert meta['cekilis']==217*meta['tam_gun']
        assert len(meta['siniflar'])==6
        with zipfile.ZipFile(io.BytesIO(z)) as archive:
            assert len(archive.namelist())==12 and archive.testzip() is None
        print('V33 REAL veri.txt PASS:',meta)
        print('V33 TEST NEXT-DRAW CLASSES:',
              [r for r in matrix if r['donem']=='TEST' and r['grup']=='TUMU'])

if __name__=='__main__':test()
