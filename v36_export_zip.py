# -*- coding: utf-8 -*-
"""GitHub Actions: replay the current veri.txt using all V36 expert motors."""
import json
import zipfile
from pathlib import Path
from v36_rng_davranis_klonu import run_from_txt


if __name__=="__main__":
    text=Path(__file__).resolve().with_name("veri.txt").read_text(encoding="utf-8-sig")
    payload,meta,daily,calibrations,motors=run_from_txt(text)
    target=Path("V36_80_SAYI_HER_CEKILIS_KLON_TEK_ZIP.zip")
    target.write_bytes(payload)
    with zipfile.ZipFile(target,"r") as z:
        assert z.testzip() is None and len(z.namelist())==11
    assert meta["cekilis"]==217*meta["tam_gun"]
    assert meta["80_sayi_kaydi"]==80*meta["cekilis"]
    print("V36 GERCEK VERI TAMAMLANDI",json.dumps({
        "dosya":str(target),"boyut_bayt":len(payload),
        "motor_grubu":len(meta["motor_gruplari"]),
        "ayri_kalibrasyon":len(meta["kalibrasyon_dallari"]),
        "cekilis":meta["cekilis"],"tam_gun":meta["tam_gun"],
        "motor_alt_haznesi":meta["motor_alt_hazne_sayisi"],
        "test":meta["test"]
    },ensure_ascii=False),flush=True)
