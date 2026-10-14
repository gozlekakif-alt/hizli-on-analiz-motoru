# -*- coding: utf-8 -*-
"""Build extended V32 ZIP from the repository's current veri.txt."""
from pathlib import Path
from v11_arastirma import read_draws
from v32_ileri_karakter import run_deep

if __name__ == '__main__':
    source=Path(__file__).resolve().with_name('veri.txt')
    if not source.is_file():
        raise SystemExit('veri.txt bulunamadı.')
    draws,bad=read_draws(source.read_text(encoding='utf-8-sig'))
    payload,summary,_,_,_,_=run_deep(draws,include_partial=False,rng_reps=30)
    path=Path('V32_4_8_12_TEK_ZIP.zip')
    path.write_bytes(payload)
    print(f'Hazır: {path} ({len(payload)} bayt)')
    print('Gerçek çekiliş:',summary['cekilis_sayisi'],
          '| Çıkan 20 döngü:',summary['tamamlanan_cikan20_dongusu'],
          '| Çıkmayan 60 döngü:',summary['tamamlanan_cikmayan60_dongusu'],
          '| 4/8/12 kesit:',summary['4_8_12_kesit'],
          '| geçersiz satır:',len(bad))
