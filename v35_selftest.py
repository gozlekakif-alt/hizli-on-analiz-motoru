# -*- coding: utf-8 -*-
"""V35 eleven-draw dual signature: synthetic + real-data ZIP regressions."""
from __future__ import annotations
import csv
import io
import sys
import zipfile
from pathlib import Path
from v35_11_cekim_cift_karakter import (study, get_class, RNG_HIGH,
    RNG_JOINT, signed_direction, CLASSES)
from v32_80_tamamlama import clock


def sample(p, option=None, day='2026-10-01'):
    # 1 has six hits in the first eleven, 2 is absent last six.
    if option is not None:
        n=list(option)
    else:
        flags=([1] if p<=6 else [])+([2] if p<=5 else [])
        n=flags+list(range(3,3+20-len(flags)))
    assert len(n)==20 and len(set(n))==20
    return {'day':day,'pos':p,'no':10000+p,'dt':day+'T'+clock(p),'nums':tuple(n)}


def rows(blob,name):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig')),delimiter=';'))


def main():
    assert get_class(6,0)=='YOGUN_6PLUS'
    assert get_class(5,6)=='BEKLEYEN_6PLUS'
    assert abs(RNG_JOINT-(20/80)*(19/79))<1e-12
    assert 0<RNG_HIGH<1
    assert signed_direction(0b11111000000)=='AZALIYOR'
    assert signed_direction(0b00000011111)=='ARTIYOR'
    prefix=[sample(i) for i in range(1,12)]
    alt=[sample(12,option=list(range(1,21)))]
    base=[sample(12,option=list(range(40,60)))]
    payload,summary,classes,freq,selected=study(prefix+base,include_partial=True)
    assert summary['11li_kesit']==2
    assert summary['11li_pencere_sayi_kaydi']==160
    assert summary['degerlendirilen_gelecek_sayi']==80
    r=rows(payload,'01_80_SAYI_HER_11_IMZA_VE_SONRAKI_CEKILIS.csv')
    one=[x for x in r if x['kaynak_sira']=='11' and x['sayi']=='1'][0]
    two=[x for x in r if x['kaynak_sira']=='11' and x['sayi']=='2'][0]
    assert one['son11_cikan']=='6' and one['karakter']=='YOGUN_6PLUS'
    assert two['ust_uste_cikmama']=='6' and two['karakter']=='BEKLEYEN_6PLUS'
    assert one['hedef_20_de']=='0' and two['hedef_20_de']=='0'
    z2,_,_,_,_=study(prefix+alt,include_partial=True)
    second=rows(z2,'01_80_SAYI_HER_11_IMZA_VE_SONRAKI_CEKILIS.csv')
    one2=[x for x in second if x['kaynak_sira']=='11' and x['sayi']=='1'][0]
    two2=[x for x in second if x['kaynak_sira']=='11' and x['sayi']=='2'][0]
    # Target changes only the outcome, not the source features.
    keys=['imza_11','son11_cikan','son6_cikmayan','ust_uste_cikmama',
         'karakter','v28_isi','v32_dongu_goruldu','yon']
    assert all(one[k]==one2[k] for k in keys)
    assert all(two[k]==two2[k] for k in keys)
    assert one2['hedef_20_de']=='1' and two2['hedef_20_de']=='1'
    # Missing draw cuts source history. 01:02->07:02 is still next real draw.
    part=[sample(i) for i in range(3,14)]+[sample(14)]
    zp,sp,_,_,_=study(part,include_partial=True)
    assert sp['11li_kesit']==2
    broken=[sample(i) for i in range(1,11)]+[sample(12)]
    _,st,_,_,_=study(broken,include_partial=True)
    assert st['11li_kesit']==0
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None
        assert len(z.namelist())==18
        assert '13_TUM_DURUMDAN_SONRAKI_BIRLIKTE_CIKAN_CIFTLER.csv' in z.namelist()
    print('V35 synthetic 11-signature, hot6, absent6, target-holdout and ZIP PASS')
    if '--full' in sys.argv:
        from v11_arastirma import read_draws
        raw=Path('veri.txt').read_text(encoding='utf-8-sig')
        draws,errors=read_draws(raw)
        payload,stats,classes,freq,selected=study(draws)
        assert stats['tam_gun']>=70
        assert stats['11li_kesit']==stats['tam_gun']*(217-10)
        assert stats['11li_pencere_sayi_kaydi']==stats['11li_kesit']*80
        assert len([r for r in classes if r['donem']=='TEST'])==5
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            assert z.testzip() is None and len(z.namelist())==18
        print('V35 REAL veri.txt PASS:',{k:v for k,v in stats.items() if k!='sinif_test'})
        print('V35 TEST CLASSES:',[r for r in classes if r['donem']=='TEST'])
        print('V35 TRAIN TO TEST:',selected[:8])


if __name__=='__main__':
    main()
