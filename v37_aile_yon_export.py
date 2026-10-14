# -*- coding: utf-8 -*-
"""V37B action: regenerate core once, attach experts in same SQLite, zip reports."""
import json
import tempfile
import zipfile
from pathlib import Path
from v11_arastirma import read_draws
from v37_ortak_hafiza import replay
from v37_aile_yon_uzmanlari import build, export


def main():
    draws,errors=read_draws(Path("veri.txt").read_text(encoding="utf-8-sig"))
    with tempfile.TemporaryDirectory(prefix="v37b_") as tmp:
        db=Path(tmp)/"shared.sqlite3"
        base=replay(draws,db)
        extension=build(db)
        if base["draw_count"]!=extension["completed_draws"]:
            raise ValueError("Family specialists missing history steps")
        output=Path("V37B_AILE_ISI_YON_ORTAK_HAFIZA_TEK_ZIP.zip")
        periods=export(db,output)
        with zipfile.ZipFile(output) as z:
            assert len(z.namelist())==7 and z.testzip() is None
        print("V37B TAMAMLANDI",json.dumps({
            "cekilis":base["draw_count"],
            "ball_life_records":base["ball_step_rows"],
            "family_specialist":extension,
            "period_results":periods,
            "archive_bytes":output.stat().st_size,
            "source_parse_warnings":len(errors)
        },ensure_ascii=False),flush=True)


if __name__=="__main__":main()
