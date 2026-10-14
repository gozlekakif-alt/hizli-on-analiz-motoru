# -*- coding: utf-8 -*-
"""V31 symmetry invariants, H6 frozen features, 72-day synthetic ZIP smoke."""
import io
import random
import sys
from datetime import date,timedelta
from zipfile import ZipFile,ZIP_DEFLATED

from v21_aile_yasam_dongusu import clock
from v29_sicaklik_kalis_hedef import generate_rows
from v31_ayna_simetri import (
    BALLS, MIRROR_BANDS, MODELS, band_of,mirror_number,sibling_band,
    ring_of,sign,preparing,model_key,fit24,choose_model,probabilities,brier,
    coupons,test36,ring_tables,numeric_mirror_null,run_study
)


def draw(day,pos,nums):
    return {"no":70000+int(day[-2:])*217+pos,
            "day":day,"pos":pos,"nums":tuple(sorted(nums)),
            "dt":day+"T"+clock(pos)[0],
            "mask":sum(1<<(n-1) for n in nums)}


assert MIRROR_BANDS==((1,8),(2,7),(3,6),(4,5))
assert len(MODELS)==5
assert all(mirror_number(mirror_number(n))==n for n in BALLS)
assert all(sibling_band(sibling_band(b))==b for b in range(1,9))
assert all(ring_of(n)==ring_of(81-n) for n in BALLS)
assert mirror_number(1)==80 and mirror_number(40)==41
assert sign(0)=="Sıfır" and sign(3)=="Artı" and sign(-3)=="Eksi"
assert clock(13)==("01:02",62) and clock(14)==("07:02",422)

rng=random.Random(73091)
dates=["2026-10-01","2026-10-02","2026-10-03","2026-10-04"]
records=[draw(day,pos,rng.sample(BALLS,20))
         for day in dates for pos in range(1,218)]
phases={dates[0]:"Eğitim24",dates[1]:"Doğrulama12",
        dates[2]:"Sınama36",dates[3]:"Sınama36"}
events,bandrows=preparing(records,phases)
assert len(events)==6+3*18
assert len(bandrows)==len(events)*8
assert all(len(rows)==80 for _,_,rows in events)
assert all(sum(r["H7-H12 gelen sayı"] for r in rows)==120
           for _,_,rows in events)
assert all(r["Ayna sayı"]==81-r["Sayı"] for _,_,rows in events for r in rows)
assert all(r["Bant"]+r["Kardeş bant"]==9 for _,_,rows in events for r in rows)
assert all(r["Kardeş ilk6 +/− zıtlık"] in range(7)
           for _,_,rows in events for r in rows)

f=fit24(events)
chosen,audit=choose_model(events,f)
assert chosen in MODELS and len(audit)==len(MODELS)
for d,start,rows in events:
    q=probabilities(rows,f,chosen)
    assert len(q)==80 and abs(sum(q)-20)<1e-5
    assert abs(brier(rows,[.25]*80)-.1875)<1e-12
    for label,nums in coupons(rows,q,d,start).items():
        assert len(set(nums))==len(nums)==(10 if label.endswith("10") else 20)
score,dist,ci=test36(events,f,chosen)
assert len(score)==2*18*6 and len(dist)==6
hour,halves,number,profile,counts,totals=ring_tables(events,bandrows)
assert len(hour)==2*18*4 and len(halves)==2*18
assert len(number)==40 and len(profile)==4
assert totals["T"]==2*18*6
assert sum(counts.values())==totals["Toplam çift coappearance"]
perm=numeric_mirror_null(events,reps=7)
assert 0<perm[0]["İki kuyruklu sapma p"]<=1
assert 0<perm[0]["Çoklu çift araması için max-istatistik p"]<=1
# Future-only perturbation must NOT change any frozen H6 mirror features.
d,s,old=events[0]
modified=[]
for record in records:
    if record["day"]==d and s+6<=record["pos"]<=s+11:
        modified.append(draw(d,record["pos"],range(61,81)))
    else:
        modified.append(record)
new_events,newbands=preparing(modified,phases)
new=next(rr for dd,ss,rr in new_events if (dd,ss)==(d,s))
for before,after in zip(old,new):
    for field in ("Sayı","Ayna sayı","Isı6","Basınç yönü",
                  "İlk6 çıkma","Ayna sayı ilk6 geldi",
                  "Kardeş ilk6 artı/eksi","Kendi ilk6 artı/eksi",
                  "İki yarı ilk6 fark","Ayna sayı zıt yönler"):
        assert before[field]==after[field],field
print("V31_SMALL_PASS",len(events),len(hour),chosen,flush=True)

if "--full" in sys.argv:
    rand=random.Random(98765)
    begin=date(2026,1,1)
    lines=[]
    for i in range(72):
        stamp=(begin+timedelta(days=i)).strftime("%d.%m.%Y")
        for pos in range(1,218):
            nums=sorted(rand.sample(BALLS,20))
            lines.append(
                f"{30000+i*217+pos};{stamp} {clock(pos)[0]};"+
                ",".join(map(str,nums)))
    raw="\n".join(lines)
    files,meta,distribution,ci,null,pairs=run_study(raw)
    assert meta["Gün"]==72
    assert meta["Hedef çekiliş"]==3888
    assert meta["80 sayı-saat son36"]==51840
    assert len(files)==13 and len(distribution)==6
    assert len(pairs)==36*18*4
    assert len(files["03_40_ayna_sayi_kardesi_birliktelik.csv"])>1000
    assert len(files["06_ayna_bantlar_gecikme_0_6_cekilis.csv"])>1000
    assert all(d["Hedef"]==3888 for d in distribution)
    assert all(d["RNG ortalama"]==(2.5 if d["Boyut"]==10 else 5.)
               for d in distribution)
    b=io.BytesIO()
    with ZipFile(b,"w",compression=ZIP_DEFLATED) as z:
        for n,p in files.items():z.writestr(n,p)
    with ZipFile(io.BytesIO(b.getvalue())) as z:
        assert len(z.namelist())==13
        assert "00_TEK_RAPOR_AYNA_SIMETRI.txt" in z.namelist()
    print("V31_72_FULL_SYNTHETIC_PASS",
          len(files),meta["Hedef çekiliş"],
          meta["Seçilen"],len(b.getvalue()),flush=True)
