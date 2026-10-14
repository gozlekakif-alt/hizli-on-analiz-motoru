# -*- coding: utf-8 -*-
"""GitHub Actions: V35 complete 11-bit 80-number cycle research ZIP."""
from pathlib import Path
from v35_11_cekim_cift_karakter import from_text

if __name__=='__main__':
    raw=Path(__file__).resolve().with_name('veri.txt').read_text(encoding='utf-8-sig')
    zipped,meta,classes,freq,selected=from_text(raw)
    file=Path('V35_11_CEKILIS_80_SAYI_CIFT_KARAKTER_TEK_ZIP.zip')
    file.write_bytes(zipped)
    print('V35 ZIP hazır',file,len(zipped),'bayt')
    print('V35 FULL RESULT:', {k:v for k,v in meta.items() if k!='sinif_test'})
    print('V35 TEST CLASSES:',[r for r in classes if r['donem']=='TEST'])
    print('V35 TRAIN SELECTED IN TEST:',selected[:5])
