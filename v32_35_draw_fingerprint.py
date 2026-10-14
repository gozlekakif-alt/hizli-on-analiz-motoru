# -*- coding: utf-8 -*-
"""Stable Streamlit cache fingerprint from the ACTUAL common draw schema.

v10_app's draw records contain day, pos, no, nums (20 numbers). They do
not guarantee a precomputed 'mask' field. Never rely on that optional key.
"""
import hashlib
import json


def draw_fingerprint(draws):
    records = [
        [str(row["day"]), int(row["pos"]), int(row["no"]),
         sorted(int(n) for n in row["nums"])]
        for row in draws
    ]
    packed = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()
