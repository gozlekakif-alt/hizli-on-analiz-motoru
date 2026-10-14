# -*- coding: utf-8 -*-
"""GitHub Action: one real V37 life source, all 207 V38 experts, one ZIP."""
import json
import tempfile
import zipfile
from pathlib import Path
from v11_arastirma import read_draws
from v37_ortak_hafiza import replay as replay_root
from v38_207_uzman_yurutucu import replay,export


def main():
    raw=Path("veri.txt").read_text(encoding="utf-8-sig")
    draws,warnings=read_draws(raw)
    with tempfile.TemporaryDirectory(prefix="v38_") as work:
        db=Path(work)/"shared.sqlite3"
        core=replay_root(draws,db)
        stats=replay(db)
        assert stats["draw_count"]==core["draw_count"]
        assert stats["measurement_cells"]==core["draw_count"]*207
        filename=Path("V38_207_UZMAN_HER_CEKILIS_TEK_ZIP.zip")
        out=export(db,filename)
        assert len(out)==207
        with zipfile.ZipFile(filename) as z:
            assert z.testzip() is None and len(z.namelist())==6
        print("V38 FULL DATA PASS:",json.dumps({
          "core_draws":core["draw_count"],
          "80ball_lifecards":core["ball_step_rows"],
          "registry":stats,"zip_size":filename.stat().st_size,
          "parse_warnings":len(warnings)},
          ensure_ascii=False),flush=True)


if __name__=="__main__":main()
