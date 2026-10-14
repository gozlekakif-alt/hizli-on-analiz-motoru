# -*- coding: utf-8 -*-
"""V37 Actions: common shared life SQLite + bound family/heat specialists."""
import json
import tempfile
import zipfile
from pathlib import Path
from v11_arastirma import read_draws
from v37_ortak_hafiza import replay,export as export_core
from v37_aile_yon_uzmanlari import build as build_specialists,export as export_specialists


def main():
    raw=Path("veri.txt").read_text(encoding="utf-8-sig")
    draws,bad=read_draws(raw)
    with tempfile.TemporaryDirectory(prefix="v37_") as directory:
        db=Path(directory)/"live.sqlite3"
        core_zip=Path("V37_ORTAK_80_SAYI_YASAM_HAFIZASI_TEK_ZIP.zip")
        expert_zip=Path("V37_AILE_VE_ISI_YON_UZMANLARI_TEK_ZIP.zip")
        stats=replay(draws,db)
        assert stats["ball_step_rows"]==80*stats["draw_count"]
        assert stats["draw_count"]==217*stats["full_days_in_source"]
        assert stats["engine_operational_count"]==8
        advanced=build_specialists(db)
        assert advanced["completed_draws"]==stats["draw_count"]
        comparison=export_specialists(db,expert_zip)
        # Include all family/heat expert event tables IN common SQLite artifact.
        export_core(db,core_zip,stats)
        with zipfile.ZipFile(core_zip) as z:
            assert z.testzip() is None and len(z.namelist())==6
        with zipfile.ZipFile(expert_zip) as z:
            assert z.testzip() is None and len(z.namelist())==7
        print("V37 SQLITE REAL DATA PASS:",json.dumps({
            k:v for k,v in stats.items() if k not in ("daily","source_warnings")
        },ensure_ascii=False),flush=True)
        print("V37 FAMILY+HEAT REAL TEST PASS:",json.dumps(
            advanced,ensure_ascii=False),flush=True)
        print("V37 FAMILY+HEAT EVAL:",json.dumps(
            comparison,ensure_ascii=False),flush=True)
        print("V37 CORE ARTIFACT",core_zip.name,"bytes",core_zip.stat().st_size,flush=True)
        print("V37 EXPERT ARTIFACT",expert_zip.name,"bytes",expert_zip.stat().st_size,flush=True)


if __name__=="__main__":main()
