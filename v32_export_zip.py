# -*- coding: utf-8 -*-
"""Build one-click V32 ZIP from the repository's current veri.txt."""
from pathlib import Path
from v32_80_tamamlama import run_text

if __name__ == '__main__':
    source=Path(__file__).resolve().with_name('veri.txt')
    if not source.is_file():
        raise SystemExit('veri.txt bulunamadı.')
    data=source.read_text(encoding='utf-8-sig')
    payload,summary,_,_,_=run_text(data,rng_reps=30)
    path=Path('V32_80_SAYI_TAMAMLANMA_TEK_RAPOR.zip')
    path.write_bytes(payload)
    print(f'Hazır: {path} ({len(payload)} bayt)')
    print('Gerçek çekiliş:',summary['cekilis_sayisi'],
          '| Çıkan 20 döngü:',summary['tamamlanan_cikan20_dongusu'],
          '| Çıkmayan 60 döngü:',summary['tamamlanan_cikmayan60_dongusu'])
