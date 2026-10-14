# -*- coding: utf-8 -*-
"""Regression: actual V10 draw schema has 20 nums, NO 'mask' field."""
import ast
from pathlib import Path
from v32_35_draw_fingerprint import draw_fingerprint

FILES = ("v32_80_tamamlama_app.py", "v33_bekleme_app.py",
         "v34_bekleme_app.py", "v35_11_karakter_app.py")


def main():
    one = {"no": 61234, "day": "2026-10-14", "pos": 34,
           "nums": list(range(1, 21))}
    two = {"no": 61235, "day": "2026-10-14", "pos": 35,
           "nums": list(range(2, 22))}
    baseline = draw_fingerprint([one, two])
    assert len(baseline) == 64
    assert baseline == draw_fingerprint([dict(one, nums=list(reversed(one["nums"]))), two])
    assert baseline != draw_fingerprint([one, dict(two, nums=list(range(3,23)))])
    assert baseline != draw_fingerprint([two, one])
    assert baseline == draw_fingerprint([dict(one, mask=1234), dict(two, mask=9876)])
    assert draw_fingerprint([]) == draw_fingerprint([])
    for name in FILES:
        source = Path(name).read_text(encoding="utf-8-sig")
        ast.parse(source)
        assert "from v32_35_draw_fingerprint import draw_fingerprint" in source,name
        assert "draw_fingerprint(draws)" in source,name
        assert "['mask']" not in source and '["mask"]' not in source,name
    print("PASS: V32/33/34/35 real Streamlit draw schema no mask, 20 nums normalized, same/different dataset caches",flush=True)


if __name__ == "__main__":
    main()
