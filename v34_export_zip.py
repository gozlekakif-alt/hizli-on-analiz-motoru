# -*- coding: utf-8 -*-
"""V34 GitHub automatic all-days 8-wait cold V32 cross ZIP."""
from pathlib import Path
from v34_bekleme_isi_v32_kesisim import run_text


if __name__=='__main__':
    text=Path('veri.txt').read_text(encoding='utf-8-sig')
    blob,stats,comparisons,summary,ranking=run_text(text,reps=2000)
    path=Path('V34_8_BEKLEME_SOGUK_V32_KESISIM_TEK_ZIP.zip')
    path.write_bytes(blob)
    print('V34 ZIP saved',str(path),len(blob),'bytes')
    print('V34 SUMMARY',stats)
    print('V34 PRIMARY TEST',stats['test_birincil_karsilastirma'])
