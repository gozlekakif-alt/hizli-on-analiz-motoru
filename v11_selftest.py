# -*- coding: utf-8 -*-
"""V11 time separation, 12x20 feature and real-data integration tests."""
from datetime import datetime, timedelta
from collections import Counter
from v11_arastirma import (
    read_draws,read_families,number_window,constructed_tickets,
    family_features,arrival_category,prospective_signal,
    hour_draw_index,complete_preceding_12,run_study,
    live_preview,summary_text,csv_export,SIZES,NUMBER_METHODS,
    CHANCE_P
)
with open("veri.txt",encoding="utf-8-sig") as ff:
    draws,errors=read_draws(ff.read())
with open("v10_aileler.csv",encoding="utf-8-sig") as ff:
    families=read_families(ff.read())
assert len(draws)>15000,len(draws)
assert len(families)==831,len(families)
assert {k:sum(f["k"]==k for f in families.values())
        for k in SIZES}=={6:198,7:151,8:279,9:9,10:194}
assert len({d["no"] for d in draws})==len(draws)
assert len({(d["day"],d["pos"]) for d in draws})==len(draws)
assert hour_draw_index(13)==13
assert hour_draw_index(20)==7
assert hour_draw_index(25)==12
assert hour_draw_index(26)==1
assert round(CHANCE_P[6],8)>0
day="2026-10-11"
rr=[d for d in draws if d["day"]==day]
assert len(rr)==217,len(rr)
bypos={r["pos"]:r for r in rr}
target=bypos[20]
prior=complete_preceding_12(bypos,20)
assert prior is not None and len(prior)==12
ctx=number_window(prior)
assert sum(ctx["count12"].values())==240
assert sum(ctx["count6"].values())==120
assert sum(ctx["first6"].values())==120
assert ctx["new20"]+ctx["old20"]==20
assert ctx["cold"]+sum(ctx["count12"][n]>0 for n in range(1,81))==80
assert sum(ctx["bands"])==20
for k in SIZES:
    constructed=constructed_tickets(ctx,k)
    assert set(constructed)==set(NUMBER_METHODS)
    for label,ns in constructed.items():
        assert len(ns)==k and len(set(ns))==k
        assert all(1<=v<=80 for v in ns)

# Before a target, its twenty result numbers are NEVER in the feature window.
tampered=dict(target)
tampered["nums"]=tuple(range(1,21))
tampered["mask"]=sum(1<<(n-1) for n in tampered["nums"])
altered=dict(bypos)
altered[20]=tampered
assert number_window(complete_preceding_12(altered,20))["count12"]==ctx["count12"]
# But the next draw's 12-window may properly include the just observed draw.
assert complete_preceding_12(altered,21)[-1]["nums"]==tampered["nums"]

fam=next(iter(families.values()))
feat=family_features(fam,prior,ctx)
assert len(feat["overlaps"])==12
assert 0<=feat["max12"]<=fam["k"]
assert arrival_category(fam["k"],feat) in {
    "Sessiz","Tamamlayarak","Yükselerek",
    "Dalgalanarak","Tam tekrar","Diğer / karma"}
assert prospective_signal(fam,feat,0) is None or isinstance(prospective_signal(fam,feat,0)["routes"],list)
assert live_preview(rr[:19],families,20,{})
assert not live_preview(rr[:20],families,20,{})
assert not live_preview(rr[:13],families,14,{})

# Default complete-day study must not evaluate the most recent partial day.
study=run_study(draws,families,train_days=36)
meta=study["meta"]
assert meta["tarih_sayısı"]==73,meta
assert meta["son_gün"]=="2026-10-12",meta
assert meta["çekiliş_sayısı"]==15839,meta
assert meta["hedef_sayısı"]>7200,meta
assert len(study["methods"])==2*5*(len(NUMBER_METHODS)+2)
assert len(study["arrival"])==2*5*6
assert study["ball_states"]
assert sum(x["Sayı-hedef gözlemi"] for x in study["ball_states"])==meta["hedef_sayısı"]*80
assert sum(x["Sonraki çekilişte çıktı"] for x in study["ball_states"])==meta["hedef_sayısı"]*20
assert len(study["target_ledger"])==meta["hedef_sayısı"]*5
assert all(x["Saat içi çekiliş"] in range(7,13) for x in study["target_ledger"])
assert len(study["slots"])>400
assert len(study["hour_summary"])>30
assert study["signals"]
for r in study["methods"]:
    assert 0<=r["Tam isabet"]<=r["Hedef"]
    assert r["Ortalama isabet"]>=0
    assert r["Boyut"] in SIZES
    assert len(r["İsabet dağılımı"].split("/"))==r["Boyut"]+1
all_arrivals=sum(r["Tam görünüş"] for r in study["arrival"])
assert all_arrivals>0
assert len(csv_export(study["methods"]))>100
assert "UYARI:" in summary_text(study)
print("V11_PASS",meta)
print("V11_REPORT_BEGIN")
print(summary_text(study))
print("V11_REPORT_END")
print("V11_ARRIVALS",study["arrival"])
print("V11_80_BALL_STATES",study["ball_states"])
print("V11_HOURS_SAMPLE",study["hour_summary"][:4])
