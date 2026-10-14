# -*- coding: utf-8 -*-
"""V32 deterministic tests. Run: python v32_selftest.py [--full]"""
import csv
import io
import sys
import zipfile
from pathlib import Path
from v32_80_tamamlama import analyze,clock,hour_info


def row(p,nums,day='2026-10-01',no=None):
    return {'day':day,'pos':p,'no':10000+p if no is None else no,
            'dt':day+'T'+clock(p),'nums':tuple(nums)}


def go():
    assert clock(1)=='00:02'
    assert clock(13)=='01:02'
    assert clock(14)=='07:02'
    assert clock(217)=='23:57'
    assert hour_info(13)[1]=='EK'
    draws=[row(p,range(20*(p-1)+1,20*p+1)) for p in range(1,5)]
    payload,stats,cycles,hist,_=analyze(draws,include_partial=True,rng_reps=2)
    present=[c for c in cycles if c['havuz']=='CIKAN_20']
    absent=[c for c in cycles if c['havuz']=='CIKMAYAN_60']
    assert len(present)==1 and present[0]['tamamlandi']==1 and present[0]['adim_sayisi']==4
    assert present[0]['ilk_kez_gelenler_sirasi']=='20,20,20,20'
    assert len(absent)==2 and all(c['adim_sayisi']==2 and c['tamamlandi'] for c in absent)
    assert stats['tamamlanan_cikan20_dongusu']==1
    assert stats['tamamlanan_cikmayan60_dongusu']==2
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert len(z.namelist())==11
        r=list(csv.DictReader(io.StringIO(z.read('01_HER_CEKILIS_IKI_HAVUZ_DONGU.csv').decode('utf-8-sig')),delimiter=';'))
        assert [int(x['cikan20_toplam_farkli']) for x in r]==[20,40,60,80]
        assert [int(x['cikan20_tamamlandi']) for x in r]==[0,0,0,1]
        assert [int(x['cikmayan60_toplam_farkli']) for x in r]==[60,80,60,80]
    repeat=[row(p,range(1,21)) for p in range(1,5)]
    _,st,cy,_,_=analyze(repeat,include_partial=True,rng_reps=0)
    assert st['tamamlanan_cikan20_dongusu']==0
    assert any(c['tamamlandi']==0 for c in cy)
    d=[row(p,range(1,21)) for p in (12,13,14)]
    _,st,cy,_,_=analyze(d,include_partial=True,rng_reps=0)
    assert st['parca_sayisi']==1
    assert [c['adim_sayisi'] for c in cy if c['havuz']=='CIKAN_20']==[3]
    d=[row(p,range(1,21)) for p in (1,3,4)]
    _,st,cy,_,_=analyze(d,include_partial=True,rng_reps=0)
    assert st['parca_sayisi']==2
    assert sorted(c['adim_sayisi'] for c in cy if c['havuz']=='CIKAN_20')==[1,2]
    assert not any(c['adim_sayisi']==0 for c in cy)
    d=[row(1,range(1,21)),row(1,range(21,41),'2026-10-02',20001)]
    _,_,cy,_,_=analyze(d,include_partial=True,rng_reps=0)
    assert len([c for c in cy if c['havuz']=='CIKAN_20'])==2
    d=[row(p,range(1,21)) for p in range(1,218)]
    _,st,cy,hist,_=analyze(d,include_partial=False,rng_reps=0)
    assert st['incelenen_tam_gun']==1 and st['cekilis_sayisi']==217
    assert any(c['adim_sayisi']==217 and c['tamamlandi']==0 for c in cy)
    assert all(int(x['en_az_bu_adima_ulasan_dongu'])>=int(x['tam_bu_adimda_tamamlanan']) for x in hist)
    print('V32 basic tests PASS')
    if '--full' in sys.argv:
        from v32_80_tamamlama import run_text
        text=Path('veri.txt').read_text(encoding='utf-8-sig')
        zipped,summary,cycles,hist,ref=run_text(text,rng_reps=2)
        assert summary['incelenen_tam_gun']>=1
        assert summary['cekilis_sayisi']==summary['incelenen_tam_gun']*217
        with zipfile.ZipFile(io.BytesIO(zipped)) as z:
            assert z.testzip() is None
            assert len(z.namelist())==11
        print('V32 real veri.txt PASS:',summary)


if __name__=='__main__':
    go()
