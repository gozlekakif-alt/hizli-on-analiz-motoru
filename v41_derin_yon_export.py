# -*- coding: utf-8 -*-
"""V41: all 72 complete days, exact chronological direction panel vs controls."""
from pathlib import Path
import json
import zipfile
from v11_arastirma import read_draws
from v41_derin_yon_gecis_motoru import (study,ENSEMBLE,CONTROL_RNG,CONTROL_V39,
    FROZEN,ALL_METHODS)


def main():
    data=Path("veri.txt").read_text(encoding="utf-8-sig")
    draws,parse_bad=read_draws(data)
    output,meta,results,brier,compare,groups=study(draws)
    assert meta["complete_days"]==72
    assert meta["real_draws_seen"]==72*217
    assert meta["predicted_draws"]==72*217-1
    assert meta["number_character_cards"]==80*meta["predicted_draws"]
    assert meta["individual_tickets"]==len(ALL_METHODS)*meta["predicted_draws"]
    assert len(results)==2*len(ALL_METHODS)
    bymethod={r["motor"]:r for r in results if r["donem"]=="TEST"}
    assert bymethod[ENSEMBLE]["cekilis"]==7812
    assert bymethod[CONTROL_RNG]["cekilis"]==7812
    assert len(brier)==2
    assert abs(next(x for x in brier if x["donem"]=="TEST")["rng_brier"]-.1875)<1e-8
    out=Path("V41_DERIN_YON_HIZ_IVME_AILE_TEK_ZIP.zip")
    out.write_bytes(output)
    with zipfile.ZipFile(out) as zipf:
        assert len(zipf.namelist())==8 and zipf.testzip() is None
    print("V41 REAL 72 DAY PASS:",json.dumps({
        "full_days":meta["complete_days"],
        "actual_draws":meta["real_draws_seen"],
        "pretar_sayi_kartlari":meta["number_character_cards"],
        "frozen_tickets":meta["individual_tickets"],
        "V41_test":bymethod[ENSEMBLE],
        "V39_test":bymethod[CONTROL_V39],
        "rng_test":bymethod[CONTROL_RNG],
        "frozen_train_only":bymethod[FROZEN],
        "comparisons":{k:v for k,v in compare.items() if k.startswith("TEST__")},
        "brier":brier,
        "artifact_bytes":out.stat().st_size,
        "parse_warnings":len(parse_bad)
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
