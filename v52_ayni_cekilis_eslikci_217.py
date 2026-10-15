#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V52: exact SAME-DRAW 80x80 co-occurrence ledger across 1..217 daily slots.
Never interprets cross-draw adjacency as co-occurrence. No betting prediction.
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import re
import zipfile
from pathlib import Path
from datetime import date

from v45_sinyal_kor_test import SLOTS, RE as DRAW_RE

INDEX = {stamp: i+1 for i, stamp in enumerate(SLOTS)}
PAIR_P = (20/80)*(19/79)
PARTNER_P = 19/79

def normalise_rows(draws):
    """Input (day,id,time,20 numbers) or draw dicts; return day -> slot-indexed rows."""
    buckets = collections.defaultdict(dict)
    issues = []
    for row in draws:
        try:
            if isinstance(row, dict):
                day = str(row["day"])
                ident = int(row.get("id", row.get("no")))
                clock = str(row.get("time", ""))
                slot = int(row["pos"]) if "pos" in row else INDEX[clock]
                ns = tuple(sorted(map(int, row["nums"])))
                if not clock:
                    clock = SLOTS[slot-1]
            else:
                day, ident, clock, ns = row
                day, ident = str(day), int(ident)
                slot = INDEX[clock]
                ns = tuple(sorted(map(int, ns)))
            date.fromisoformat(day)
            if not (1<=slot<=217 and clock==SLOTS[slot-1] and
                    len(ns)==20 and len(set(ns))==20 and
                    ns[0]>=1 and ns[-1]<=80):
                issues.append(f"Invalid draw {day} #{ident}")
                continue
            r = {"day":day,"id":ident,"time":clock,"pos":slot,"nums":ns}
            old = buckets[day].get(slot)
            if old and old != r:
                issues.append(f"Conflicting {day} slot {slot}")
                continue
            buckets[day][slot]=r
        except (ValueError,TypeError,KeyError,IndexError) as e:
            issues.append(f"Invalid input: {str(e)}")
    return {d:[slots[k] for k in sorted(slots)] for d,slots in sorted(buckets.items())},issues

def parse_txt(path):
    records=[]
    malformed=[]
    for lineno,line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(),1):
        if ";" not in line:
            continue
        m=DRAW_RE.fullmatch(line.strip())
        if not m:
            malformed.append(lineno)
            continue
        ident,dd,mm,yyyy,hh,minute,ntext=m.groups()
        try:
            day=date(int(yyyy),int(mm),int(dd)).isoformat()
            nums=tuple(int(x.strip()) for x in ntext.split(","))
            records.append((day,int(ident),f"{hh}:{minute}",nums))
        except ValueError:
            malformed.append(lineno)
    out,issues=normalise_rows(records)
    return out,issues,malformed

def empty_counts():
    return [0]*81,[[0]*81 for _ in range(81)]

def absorb(counts, pair, nums):
    for i,a in enumerate(nums):
        counts[a]+=1
        for b in nums[i+1:]:
            pair[a][b]+=1
            pair[b][a]+=1

def compute(rows, upto=217):
    counts,pair=empty_counts()
    processed=0
    for r in rows:
        if r["pos"]>upto:
            break
        absorb(counts,pair,r["nums"])
        processed+=1
    return processed,counts,pair

def pairs_sorted(pair):
    return sorted(((a,b,pair[a][b]) for a in range(1,81)
                   for b in range(a+1,81)),
                  key=lambda v:(-v[2],v[0],v[1]))

def anchor_partners(anchor, counts, pair):
    return sorted(((b,pair[anchor][b]) for b in range(1,81) if b!=anchor),
                  key=lambda x:(-x[1],x[0]))

def _write(z,name,header,records):
    # Stream CSV directly into ZIP; never materialize the 217 x 3160 rows.
    with z.open(name,"w",force_zip64=True) as raw:
        out=io.TextIOWrapper(raw,encoding="utf-8",newline="",write_through=False)
        w=csv.writer(out)
        w.writerow(header)
        for r in records:
            w.writerow(r)
        out.flush()
        out.detach()

def per_draw_pair_rows(rows):
    ct,mat=empty_counts()
    for draw in rows:
        ns=draw["nums"]
        for i,a in enumerate(ns):
            ct[a]+=1
            for b in ns[i+1:]:
                mat[a][b]+=1
                mat[b][a]+=1
                yield draw["pos"],draw["id"],draw["time"],a,b,mat[a][b]

def progressive_pair_rows(rows):
    counts,pair=empty_counts()
    seen=0
    for draw in rows:
        absorb(counts,pair,draw["nums"])
        seen+=1
        for a in range(1,81):
            for b in range(a+1,81):
                yield draw["pos"],draw["id"],draw["time"],seen,a,b,pair[a][b]

def progressive_partner_rows(rows):
    counts,pair=empty_counts()
    seen=0
    for draw in rows:
        absorb(counts,pair,draw["nums"])
        seen+=1
        for a in range(1,81):
            order=anchor_partners(a,counts,pair)[:5]
            yield (draw["pos"],draw["id"],draw["time"],seen,a,counts[a],
                   "|".join(f"{b}:{cnt}" for b,cnt in order))

def daily_pair_rows(days):
    for day,rows in sorted(days.items()):
        n,ct,mat=compute(rows)
        for a in range(1,81):
            for b in range(a+1,81):
                yield day,n,a,b,ct[a],ct[b],mat[a][b],round(n*PAIR_P,5)

def daily_overview_rows(days):
    for day,rows in sorted(days.items()):
        n,ct,mat=compute(rows)
        pairmax=pairs_sorted(mat)[0]
        yield (day,n,max((x["pos"] for x in rows),default=0),
               "EVET" if len(rows)==217 and {x["pos"] for x in rows}==set(range(1,218)) else "HAYIR",
               *pairmax,round(n*PAIR_P,5),
               sum(mat[a][b] for a in range(1,81) for b in range(a+1,81)))

def make_zip(day,days,issues=(),bad_rows=()):
    rows=days[day]
    draws,counts,pair=compute(rows)
    ranked=pairs_sorted(pair)
    iozip=io.BytesIO()
    with zipfile.ZipFile(iozip,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        summary=[
          "V52 — AYNI CEKILISTE BIRLIKTE CIKAN SAYILAR (80x80)",
          f"Secilen gun: {day} | kayitli 20'li cekilis: {draws}/217",
          "Diger cekilisler arasindaki ardışıklık hesaplanmaz: SADECE AYNI 20'LI KADRO icindeki birliktelikler.",
          f"Her 20'li kadro 190 tekil ikiliye ayrilir. Bu gunde {draws*190} ikili gorunumu.",
          "Tum 1..80 sayilarinin 79 farkli eslikcisi, gorunum sayisi SIFIR olsa dahi tabloda var.",
          "Gunde '217' tam dolmuyorsa eksik slotlar sessizce varsayilmaz.",
          f"1 rasgele adil 20/80 cekilisin belirli ikilisi icin P={PAIR_P:.9f}.",
          f"Bu gun belirli ikili icin adil beklenti={draws*PAIR_P:.4f}.",
          f"20/80 sonucunda bir sayinin diger biriyle beraber olma sansi, kendi gorunumune gore={PARTNER_P:.8f}.",
          f"Bu gunde en sık ikili: {ranked[0][0]}-{ranked[0][1]}, {ranked[0][2]} kez.",
          "Bunun gibi 3.160 farklı olası ikilinin en yükseğini geçmişten seçmek rastlantı yanılmasına neden olur.",
          "Bu veriler tanimlayicidir, gelecek cekilis sonucu icin kanitlanmis tahmin avantaji yok.",
          f"Hatali/cakisan kayit: {len(issues)}; ayrica ayrıştırılamayan satir: {len(bad_rows)}.",
          "", "TOP 20",
        ]
        summary += [f"{i+1:02d}. {a}-{b}: {n}" for i,(a,b,n) in enumerate(ranked[:20])]
        z.writestr("00_TEK_SAYFA_OZET.txt","\n".join(summary)+"\n")
        _write(z,"01_CEKILISLERDE_20LI_KADROLAR.csv",
               ("gun","slot","cekilis_no","saat","20_sayi"),
               ((day,r["pos"],r["id"],r["time"],"-".join(map(str,r["nums"]))) for r in rows))
        _write(z,"02_HER_SAYININ_79_ESLIKCI_SAYISI.csv",
               ("gun","sayi","gun_kac_kez_cikti","eslikci","ayni_cekiliste_birlikte_kac_kez",
                "sayi_ciktiginda_eslikci_gelme_orani"),
               ((day,a,counts[a],b,pair[a][b],round(pair[a][b]/counts[a],5) if counts[a] else 0)
                for a in range(1,81) for b in range(1,81) if a!=b))
        _write(z,"03_3160_FARKLI_IKILI_GUN_SONU.csv",
               ("gun","sayi1","sayi2","beraber_kac_kez","rastgele_beklenen",
                "beklenenden_fark"),
               ((day,a,b,n,round(draws*PAIR_P,5),round(n-draws*PAIR_P,5))
                for a,b,n in ranked))
        _write(z,"04_HER_CEKILISTEKI_190_ESLIK.csv",
               ("slot","cekilis_no","saat","sayi1","sayi2","bu_ana_kadar_birlikte_sayisi"),
               per_draw_pair_rows(rows))
        _write(z,"05_CEKILIS_CEKILIS_3160_IKILININ_BIRIKIMI.csv",
               ("slot","cekilis_no","saat","kayitli_hedef_sayisi","sayi1","sayi2","birikimli_ortak_gorunum"),
               progressive_pair_rows(rows))
        _write(z,"06_CEKILIS_CEKILIS_80_SAYI_ILK5_ESLIK.csv",
               ("slot","cekilis_no","saat","kayitli_hedef_sayisi","sayi","sayi_kac_kez_cikti",
                "o_ana_kadar_en_cok_5_eslikci"),
               progressive_partner_rows(rows))
        _write(z,"07_TUM_GUNLER_3160_IKILI_KARSILASTIR.csv",
               ("gun","kayitli_cekilis","sayi1","sayi2","sayi1_frekans","sayi2_frekans",
                "ayni_cekiliste_ortak","adil_beklenen"),
               daily_pair_rows(days))
        _write(z,"08_TUM_GUNLER_TOP_ESLIK_OZET.csv",
               ("gun","kayitli_cekilis","son_slot","217_tam_mi","en_cok_sayi1",
                "en_cok_sayi2","en_cok_es_cikis","adil_beklenen","toplam_190_katkisi"),
               daily_overview_rows(days))
        z.writestr("09_OKUMA_KILAVUZU.txt",
          "Her 20'li kadrodan kombinasyon (20 sec 2)=190 benzersiz ikili cikar.\n"
          "Ornegin 19 ve 57 ayni kadroda ise bu ikilinin sayaci +1 olur.\n"
          "19 onceki / sonraki baska bir kadroda, 57 farkli kadroda olmussa BIRLIKTE sayilmaz.\n"
          "04: yalniz o cekiliste gorulen 190 ikili, o ana dek kacinci defa birlestikleriyle.\n"
          "05: her kayitli cekilisten SONRAKI TAM 3160 ikili tablosu, sifirlar dahil.\n"
          "06: her cekilisten sonra tum 80 sayinin top-5 eslikcisi.\n"
          "02: her sayinin 79 eslikcisinin tam sayilari, sifirlar dahil.\n"
          "07: veri.txt icindeki tum gunler icin gunluk final 3160 ikili.\n"
          "Kotu/eksik gunlerden fazladan 217 sonuc uretilmez. Benzerliklerin zengin gorunmesi "
          "rastgele cekilis icin normal olabilir.\n")
    return iozip.getvalue()

def _selftest():
    a=tuple(range(1,21))
    b=tuple(range(1,11))+tuple(range(21,31))
    c=tuple(range(1,6))+tuple(range(31,46))
    raw=[("2026-10-12",1,SLOTS[0],a),
         ("2026-10-12",2,SLOTS[1],b),
         ("2026-10-12",3,SLOTS[2],c),
         ("2026-10-13",4,SLOTS[0],a)]
    days,errors=normalise_rows(raw)
    assert len(days)==2 and not errors
    n,count,pair=compute(days["2026-10-12"])
    assert n==3 and count[1]==3 and count[20]==1 and count[40]==1
    assert pair[1][2]==3 and pair[2][1]==3 and pair[1][15]==1
    assert pair[21][22]==1 and pair[21][40]==0 and pair[1][1]==0
    assert sum(pair[a][b] for a in range(1,81) for b in range(a+1,81))==570
    assert all(sum(pair[a][b] for b in range(1,81))==19*count[a] for a in range(1,81))
    prog=list(progressive_pair_rows(days["2026-10-12"]))
    assert len(prog)==3*3160
    assert [x[6] for x in prog if (x[4],x[5])==(1,2)]==[1,2,3]
    report=make_zip("2026-10-12",days)
    with zipfile.ZipFile(io.BytesIO(report)) as z:
        assert len(z.namelist())==10
        rows=list(csv.DictReader(io.StringIO(z.read("02_HER_SAYININ_79_ESLIKCI_SAYISI.csv").decode())))
        assert len(rows)==6320
        rows=list(csv.DictReader(io.StringIO(z.read("05_CEKILIS_CEKILIS_3160_IKILININ_BIRIKIMI.csv").decode())))
        assert len(rows)==9480
        assert z.read("00_TEK_SAYFA_OZET.txt")
    print("PASS V52: same-draw only, exact 190 pairs, 80x79, all 3160 progressive pairs, daily comparison, 10-file ZIP")

def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--source",default="veri.txt")
    pa.add_argument("--day",default=None)
    pa.add_argument("--output-dir",default="v52_artifacts")
    pa.add_argument("--selftest",action="store_true")
    args=pa.parse_args()
    if args.selftest:
        _selftest()
        return
    days,errors,malformed=parse_txt(args.source)
    if not days:
        raise ValueError("No valid draw data found.")
    preferred=[d for d,rows in days.items() if len(rows)==217 and {r["pos"] for r in rows}==set(range(1,218))]
    selected=args.day or (preferred[-1] if preferred else sorted(days)[-1])
    if selected not in days:
        raise ValueError("Requested day missing: "+selected)
    outfile=Path(args.output_dir)
    outfile.mkdir(parents=True,exist_ok=True)
    output=outfile/f"V52_ES_CEKILIS_80X80_{selected}_TEK_RAPOR.zip"
    output.write_bytes(make_zip(selected,days,errors,malformed))
    n,ct,mat=compute(days[selected])
    print(json.dumps({"zip":str(output),"day":selected,"draws":n,
                      "top_pairs":pairs_sorted(mat)[:10],"invalid":len(errors)+len(malformed)},
                     ensure_ascii=False))

if __name__=="__main__":
    main()
