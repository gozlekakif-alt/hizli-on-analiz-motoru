# -*- coding: utf-8 -*-
"""V34 basic+full no-lookahead intersection, 36/36 and ZIP integrity tests."""
import csv
import io
import sys
import zipfile
from pathlib import Path
from v34_bekleme_isi_v32_kesisim import run_cross,rows_from_v33,groups_of,A,B,UNSEEN
from v33_bekleme_havuzlari import run_study
from v32_80_tamamlama import clock


def draw(p,nums=None,day="2026-10-01"):
    return {'day':day,'pos':p,'no':30000+p,
            'dt':day+'T'+clock(p),'nums':tuple(nums or range(1,21))}


def basic():
    record={'sinif':'8','isi':'SOGUK','v32_havuz':UNSEEN}
    assert A in groups_of(record) and B not in groups_of(record)
    record['isi']='SOGUGA_YAKIN'
    assert B in groups_of(record) and A not in groups_of(record)
    data=[draw(p) for p in range(1,15)]
    raw,stats,compare,summary,ranking=run_cross(data,include_partial=True,reps=50)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        assert len(z.namelist())==21
        assert 'V34_01_ONCEDEN_SECILEN_8_SOGUK_HENUZ_TEST.csv' in z.namelist()
        assert 'V33_TEMEL/07_BEKLEYENDEN_SONRAKI_CEKILIS_GERCEK_HIT.csv' in z.namelist()
    assert stats['gercek_cekilis']==14
    assert stats['8_bekleme_risk_kaydi']>0
    # Change the as-yet-unknown target, but never alter the source class.
    common=[draw(p) for p in range(1,9)]
    left,_1,_2,_3,_4=run_study(common+[draw(9)],include_partial=True)
    right,_1,_2,_3,_4=run_study(common+[draw(9,range(61,81))],include_partial=True)
    rl=[r for r in rows_from_v33(left) if r['kaynak_sira']=='8']
    rr=[r for r in rows_from_v33(right) if r['kaynak_sira']=='8']
    def keyed(a):
        return {int(r['sayi']):(r['sinif'],r['isi'],r['v32_havuz'],
                set(groups_of(r))) for r in a}
    assert keyed(rl)==keyed(rr), 'target leaked into source features'
    print('V34 synthetic class, no target leakage, combined ZIP PASS')
    if '--full' in sys.argv:
        from v11_arastirma import read_draws
        draws,bad=read_draws(Path('veri.txt').read_text(encoding='utf-8-sig'))
        zipped,info,c,s,r=run_cross(draws,reps=500)
        assert info['v33_tam_gun']>=70
        assert info['gercek_cekilis']==info['v33_tam_gun']*217
        item=info['test_birincil_karsilastirma']
        assert item['hedef_gozlem']>0 and item['diger_gozlem']>0
        assert len(c)==12
        with zipfile.ZipFile(io.BytesIO(zipped)) as z:
            assert z.testzip() is None and len(z.namelist())==21
        print('V34 REAL veri.txt PASS',info)
        print('V34 TEST PRIMARY',item)
        print('V34 TEST TOP TRAIN-SELECTED',r)


if __name__=='__main__':
    basic()
