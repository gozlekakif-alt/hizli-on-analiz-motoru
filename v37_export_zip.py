# -*- coding: utf-8 -*-
"""GitHub Actions V37 stage-A full historical source into shared SQLite ZIP."""
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from v37_ortak_hafiza import run_text, replay


def main():
    raw=Path("veri.txt").read_text(encoding="utf-8-sig")
    # The SQLite checkpoint remains separate from source: deterministic replay
    # on Actions each run. Streamlit reuses its own temporary DB within session.
    with tempfile.TemporaryDirectory(prefix="v37_") as directory:
        db=Path(directory)/"live.sqlite3"
        out=Path("V37_ORTAK_80_SAYI_YASAM_HAFIZASI_TEK_ZIP.zip")
        stats=run_text(raw,db,out)
        assert stats["ball_step_rows"]==80*stats["draw_count"]
        assert stats["draw_count"]==217*stats["full_days_in_source"]
        assert stats["engine_operational_count"]==8
        with zipfile.ZipFile(out) as z:
            assert z.testzip() is None and len(z.namelist())==6
        print("V37 SQLITE REAL DATA PASS:",json.dumps({
            k:v for k,v in stats.items() if k not in ("daily","source_warnings")
        },ensure_ascii=False),flush=True)
        print("V37 ARTIFACT",out.name,"bytes",out.stat().st_size,flush=True)


if __name__=="__main__":main()
