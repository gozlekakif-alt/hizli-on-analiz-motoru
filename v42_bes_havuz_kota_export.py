# -*- coding: utf-8 -*-
"""V42 full veri.txt: quota success vs exact RNG, ticket identity, formation."""
import json
import zipfile
from pathlib import Path
from v11_arastirma import read_draws
from v42_bes_hareketli_havuz_kota import study,POOL_NAMES


def main():
    raw=Path("veri.txt").read_text(encoding="utf-8-sig")
    draws,warnings=read_draws(raw)
    blob,meta,summaries,ident,formations=study(draws,include_partial=False)
    assert meta["analyzed_days"]==meta["total_full_days"]
    assert meta["all_real_draws"]==meta["analyzed_days"]*217
    assert meta["evaluated_targets"]==meta["all_real_draws"]-72
    assert len([x for x in summaries if x["donem"]=="TEST"])==4
    assert len([x for x in ident if x["donem"]=="TEST"])==6
    assert sum(x["gorunme"] for x in formations
            if x["imza_tipi"]=="5_SICAKLIK_KOTASI")==meta["evaluated_targets"]
    output=Path("V42_BES_HAVUZ_KOTA_OLUSUM_TEK_ZIP.zip")
    output.write_bytes(blob)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None and len(z.namelist())==9
    print("V42 REAL COMPLETE DATA PASS:",json.dumps({
        "days":meta["analyzed_days"],
        "complete_actual_draws":meta["all_real_draws"],
        "evaluated_draws":meta["evaluated_targets"],
        "test_quota_summary":[x for x in summaries if x["donem"]=="TEST"],
        "test_identity_summary":[x for x in ident if x["donem"]=="TEST"],
        "full20_and_formation_audit":meta["full20_identity_duplicate_audit"],
        "test_quotas_paired":meta["paired_quota_comparisons"],
        "archive_bytes":output.stat().st_size,
        "parse_warnings":len(warnings)
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
