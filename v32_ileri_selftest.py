# -*- coding: utf-8 -*-
"""V32 advanced research guardrails: prefix-only predictions and censoring."""
import csv
import io
import sys
import zipfile
from pathlib import Path
from v32_80_tamamlama import clock
from v32_ileri_karakter import chance_finish, run_deep, _cycle_snapshots


def row(p,nums,day='2026-10-01'):
    return {'day':day,'pos':p,'no':10000+p,'nums':tuple(nums),
            'dt':day+'T'+clock(p)}


def check():
    assert abs(chance_finish(1,20,1)-.25)<1e-12
    assert abs(chance_finish(1,60,1)-.75)<1e-12
    assert chance_finish(80,20,3)==0
    assert chance_finish(80,20,4)>0
    # Four known draws reach 60 distinct. The unseen twenty then
    # arrive in the fifth draw. The 4th snapshot predicts from prefix only.
    head=[row(1,range(1,21)),row(2,range(21,41)),
          row(3,range(41,61)),row(4,range(41,61))]
    actual=head+[row(5,range(61,81))]
    altered=head+[row(5,range(1,21))]
    from v32_80_tamamlama import _segments
    a1,_,_,_=_segments(actual,True)
    a2,_,_,_=_segments(altered,True)
    s1,events,_=_cycle_snapshots(a1[0][2],'CIKAN_20',20,'TEST')
    s2,_,_=_cycle_snapshots(a2[0][2],'CIKAN_20',20,'TEST')
    feature_names=('kesit_adimi','gorulen','eksik','adim_yeni','son_dort_yeni',
                   'hiz_farki','hiz_sinifi','eksik_sayilar',
                   'rng_1_olasilik','rng_4_olasilik')
    assert len(s1)==len(s2)==1
    assert {k:s1[0][k] for k in feature_names}=={k:s2[0][k] for k in feature_names}
    assert s1[0]['gercek_1_icinde_tamamlama']==1
    assert s2[0]['gercek_1_icinde_tamamlama']==0
    assert s1[0]['sonraki_cekilis_yeni_sayi']==20
    assert s2[0]['sonraki_cekilis_yeni_sayi']==0
    # Censor on missing future. A positive closure before horizon is known.
    assert s2[0]['gercek_4_icinde_tamamlama']==''
    assert s1[0]['gercek_4_icinde_tamamlama']==1
    # No fabricated draws between 01:02 -> 07:02
    gap=[row(p,range(1,21)) for p in (11,12,13,14,15,16)]
    g,_,_,_=_segments(gap,True)
    assert len(g)==1 and len(g[0][2])==6
    # Extended report retains all original eleven files.
    blob,meta,summary,variants,bands,snapshots=run_deep(
        [row(p,range(1,21)) for p in range(1,218)],rng_reps=0)
    assert meta['incelenen_tam_gun']==1
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None
        assert len(z.namelist())==17
        assert '11_4_8_12_ANLIK_DURUM_VE_GELECEK.csv' in z.namelist()
    print('V32 advanced prefix, censor, RNG, day slots, ZIP PASS')
    if '--full' in sys.argv:
        from v11_arastirma import read_draws
        data,bad=read_draws(Path('veri.txt').read_text(encoding='utf-8-sig'))
        blob,meta,summary,variants,bands,snapshots=run_deep(data,rng_reps=2)
        assert meta['incelenen_tam_gun']>=1
        assert meta['cekilis_sayisi']==meta['incelenen_tam_gun']*217
        assert len(snapshots)>0
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            assert z.testzip() is None and len(z.namelist())==17
        print('V32 4/8/12 real veri.txt PASS:',meta)


if __name__=='__main__':
    check()
