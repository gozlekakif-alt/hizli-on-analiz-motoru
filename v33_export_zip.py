# -*- coding: utf-8 -*-
"""Automated current veri.txt -> V33 6..10 waiting pool analysis ZIP."""
from pathlib import Path
from v33_bekleme_havuzlari import run_text

if __name__ == '__main__':
    text=Path(__file__).resolve().with_name('veri.txt').read_text(encoding='utf-8-sig')
    payload,meta,matrix,pools,daily=run_text(text,include_partial=False)
    target=Path('V33_6_7_8_9_10_BEKLEYEN_HAVUZLAR_TEK_ZIP.zip')
    target.write_bytes(payload)
    print('V33 ZIP hazır:',target,len(payload),'bayt')
    print('V33 RESULTS',meta)
    print('V33 TEST NEXT-DRAW',[r for r in matrix if r['donem']=='TEST' and r['grup']=='TUMU'])
