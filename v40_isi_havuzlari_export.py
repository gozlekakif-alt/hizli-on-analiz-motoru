# -*- coding: utf-8 -*-
"""Run V40 with exact veri.txt, 217 real draws per complete day, one ZIP."""
from pathlib import Path
from v11_arastirma import read_draws
from v40_alti_isi_yon_havuzlari import study
import json
import zipfile


def main():
    raw=Path("veri.txt").read_text(encoding="utf-8-sig")
    draws,parse_bad=read_draws(raw)
    output,meta,evalrows,byseat=study(draws,include_partial=False)
    assert meta["draws_read"]==217*meta["source_days"]
    assert meta["number_steps"]==(meta["draws_read"]-1)*80
    tests={x["donem"]:x for x in evalrows}
    assert "EGITIM" in tests and "TEST" in tests
    assert tests["TEST"]["hedef_cekilis"]>0
    assert abs(tests["TEST"]["rng_25_brier"]-0.1875)<1e-8
    name="V40_ALTI_ISI_YON_AILE_BANT_TEK_ZIP.zip"
    Path(name).write_bytes(output)
    with zipfile.ZipFile(name) as z:
        assert z.testzip() is None and len(z.namelist())==7
    heat=[x for x in byseat if x["boyut"]=="ISI" and x["test_donemi"]=="TEST"]
    assert len(heat)==6
    print("V40 FULL REAL DATA PASS:",json.dumps({
       "complete_days":meta["source_days"],"draws":meta["draws_read"],
       "number_steps":meta["number_steps"],
       "train_test_brier":meta["tested_brier"],
       "heat_test":heat,"zip_bytes":Path(name).stat().st_size,
       "parse_warnings":len(parse_bad)
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
