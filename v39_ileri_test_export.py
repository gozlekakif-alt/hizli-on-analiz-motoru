# -*- coding: utf-8 -*-
"""V39 GitHub Actions: genuine chronological source, frozen 20-ticket ZIP."""
from pathlib import Path
from v11_arastirma import read_draws
from v39_onceden_dondurulmus_uzman_paneli import study,ENSEMBLE,BASELINE
import json
import zipfile


def main():
    draws,errors=read_draws(Path("veri.txt").read_text(encoding="utf-8-sig"))
    blob,meta,summary,qc=study(draws,include_partial=False)
    assert meta["draw_count"]==217*meta["studied_days"]
    assert meta["ticket_count"]==10*meta["draw_count"]
    train={r["method"]:r for r in summary if r["phase"]=="EGITIM"}
    test={r["method"]:r for r in summary if r["phase"]=="TEST"}
    assert len(train)==10 and len(test)==10
    assert train[ENSEMBLE]["n"]+test[ENSEMBLE]["n"]==meta["draw_count"]
    assert test[ENSEMBLE]["n"]==test[BASELINE]["n"]
    assert test[ENSEMBLE]["max_hit"]<=20
    dest=Path("V39_20_SAYI_GERCEK_ILERI_TEST_TEK_ZIP.zip")
    dest.write_bytes(blob)
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None and len(z.namelist())==6
    print("V39 REAL DATA PASS:",json.dumps({
       "complete_draws":meta["draw_count"],
       "days":meta["studied_days"],
       "frozen_tickets":meta["ticket_count"],
       "train_days_then_test_cutoff":meta["trained_date_before_test"],
       "test_ensemble":test[ENSEMBLE],
       "test_random":test[BASELINE],
       "day_block_comparison":meta["test_ensemble_vs_rng"],
       "artifact_bytes":dest.stat().st_size,
       "parse_warnings":len(errors)
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
