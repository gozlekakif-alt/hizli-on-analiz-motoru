# -*- coding: utf-8 -*-
"""V37C: execute 72 day V37A shared SQLite source, then fragmented family study."""
import json
import tempfile
import zipfile
from pathlib import Path

from v11_arastirma import read_draws
from v37_ortak_hafiza import replay
from v37c_parcali_aile_hayati import run,export


def main():
    raw=Path("veri.txt").read_text(encoding="utf-8-sig")
    draws,parse_warnings=read_draws(raw)
    with tempfile.TemporaryDirectory(prefix="v37c_") as td:
        db=Path(td)/"ortak_hafiza.sqlite3"
        base=replay(draws,db)
        stats=run(db)
        assert stats["completed_draws"]==base["draw_count"]
        assert stats["source_draws"]==base["draw_count"]
        assert stats["global_4family_count"]==1581580
        archive=Path("V37C_PARCALI_DORTLU_AILE_YASAM_TEK_ZIP.zip")
        results=export(db,archive)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist())==7
        print("V37C FULL DATA PASS",json.dumps({
            "draws":base["draw_count"],
            "lifecards":base["ball_step_rows"],
            "sampled_quartet_catalogue":stats["catalogue_sample_size"],
            "exact_universe":stats["global_4family_count"],
            "fragment_sample_evidence":stats["bounded_evidence_events"],
            "new_draws":stats["new_draws"],
            "period_results":results,
            "archive_bytes":archive.stat().st_size,
            "parse_warnings":len(parse_warnings)
        },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
