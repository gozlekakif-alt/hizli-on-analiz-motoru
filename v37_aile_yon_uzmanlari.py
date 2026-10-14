# -*- coding: utf-8 -*-
"""V37 B: pair/triple/quartet life motifs and six-seat direction specialists.

Reuses SQLite V37 shared immutable draw_ledger, ball_step and reservoir_event.
It adds ONLY derived specialist tables; existing evidence is never copied
or modified. Per draw tracks 12 real consecutive slots: exact repeat family
counts, quartets whose rolling member-coverage first completes on this draw,
and linked heat movements. Counts of quartet first-cover paths are exact via
combinatorial dynamic programming; examples are capped transparently.
"""
from __future__ import annotations
import csv
import io
import json
import math
import sqlite3
import zipfile
from collections import Counter, defaultdict, deque
from itertools import combinations
from pathlib import Path

ENGINE_VERSION=1
WINDOW=12
EXAMPLES_PER_DRAW=8
SIX=("SOGUK","SOGUGA_YAKIN","ORTA","ILIK","SICAGA_YAKIN","SICAK")
FAMILY_KINDS=("AILE2","AILE3","AILE4")
PARTIAL_PATHS=("4","1+3","2+2","3+1","1+1+2","1+2+1","2+1+1",
               "1+1+1+1")
OUT_FIELDS=("day","pos","draw_no","seq","phase","pair_repeats",
            "triple_repeats","quartet_repeats","quartet_consecutive",
            "quartet_silent_return","quartet_new_cover","quartet_already_covered",
            "quartet_path_4","quartet_path_1+3","quartet_path_2+2",
            "quartet_path_3+1","quartet_path_1+1+2",
            "quartet_path_1+2+1","quartet_path_2+1+1",
            "quartet_path_1+1+1+1","heat_up","heat_down","heat_still",
            "heat_change_total","directional_repeat_quartets","linked_examples",
            "raw_20","complete_80","warning")
HEAT_FIELDS=("draw_no","seq","old_heat","new_heat","count","direction")
EXAMPLE_FIELDS=("draw_no","seq","family_size","family_numbers","event_type",
 "previous_full_draw_no","previous_full_pos","quiet_real_draws",
 "heat_directions","parent_reservoir_event_ids","source_draws")
DIALOGUE_FIELDS=("draw_no","seq","numbers","relation","heat_up",
                 "heat_down","source_event_ids","event_id")
CSV_OPTS=dict(delimiter=";",lineterminator="\n")


def _memberstring(values):
    return "-".join(f"{n:02d}" for n in values)


def init_db(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS v37_family_step(
      draw_no INTEGER PRIMARY KEY,seq INTEGER NOT NULL,
      day TEXT NOT NULL,pos INTEGER NOT NULL,payload TEXT NOT NULL,
      engine_version INTEGER NOT NULL,
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no));
    CREATE TABLE IF NOT EXISTS v37_heat_transition(
      draw_no INTEGER NOT NULL,old_heat TEXT NOT NULL,new_heat TEXT NOT NULL,
      count INTEGER NOT NULL,
      PRIMARY KEY(draw_no,old_heat,new_heat),
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no));
    CREATE TABLE IF NOT EXISTS v37_family_examples(
      event_id TEXT PRIMARY KEY,draw_no INTEGER NOT NULL,
      seq INTEGER NOT NULL,family_size INTEGER NOT NULL,
      numbers TEXT NOT NULL,event_type TEXT NOT NULL,
      previous_full_draw_no INTEGER,previous_full_pos INTEGER,
      quiet_real_draws INTEGER,
      heat_directions TEXT NOT NULL,parent_reservoir_event_ids TEXT NOT NULL,
      source_draws TEXT NOT NULL,
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no));
    CREATE TABLE IF NOT EXISTS v37_family_heat_dialogue(
      event_id TEXT PRIMARY KEY,draw_no INTEGER NOT NULL,seq INTEGER NOT NULL,
      numbers TEXT NOT NULL,relation TEXT NOT NULL,
      heat_up INTEGER NOT NULL,heat_down INTEGER NOT NULL,
      source_event_ids TEXT NOT NULL,
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no));
    CREATE INDEX IF NOT EXISTS idx_v37_family_seq ON v37_family_step(seq);
    CREATE INDEX IF NOT EXISTS idx_v37_family_examples_draw ON v37_family_examples(draw_no);
    """)
    db.executemany("INSERT OR IGNORE INTO motor_registry VALUES(?,?,?,?)", [
        ("FAMILY.PAIR_12",1,"CALISIYOR_V37_B","12'li kayan pencerede tam ikili aile tekrari"),
        ("FAMILY.TRIPLE_12",1,"CALISIYOR_V37_B","12'li kayan pencerede tam uclu aile tekrari"),
        ("FAMILY.QUARTET_12",1,"CALISIYOR_V37_B","12'li kayan pencerede tam dortlu aile tekrari"),
        ("FAMILY.QUARTET_COVER_PATH",1,"CALISIYOR_V37_B","Dortlunun 12'li ilk gorulme tamamlanma kompozisyonu"),
        ("DIRECTION.HEAT_6X6",1,"CALISIYOR_V37_B","6 isi sinifi 36 hucreli gecis matrisi"),
        ("DIALOGUE.FAMILY_HEAT",1,"CALISIYOR_V37_B","Yeniden birlesen aile ve uyelerinin isi yonu ortak olay delili"),
    ])
    db.commit()


def first_coverage_paths(cur_set, history, pos):
    """All 4-subsets of CURRENT 20, grouped by the chronological FIRST
    appearance of each member within previous <=11 draws or now.
    This measures 4/4 *within-current-draw* families, NOT all fragments
    that are only union-complete across multiple draws.
    """
    first={n:pos for n in cur_set}
    for old in history:
        for n in cur_set & old["wins"]:
            if first[n]==pos:first[n]=old["pos"]
    bin_counts=Counter(first.values())
    # Exact stage compositions with timestamp-aware state:
    staged={((),0):1}
    for t,cnt in sorted(bin_counts.items()):
        new=defaultdict(int)
        for (composition,used_current),number in staged.items():
            can=4-sum(composition)
            for take in range(min(cnt,can)+1):
                next_comp=composition+((take,) if take else ())
                next_cur=int(used_current or (t==pos and take>0))
                new[(next_comp,next_cur)]+=number*math.comb(cnt,take)
        staged=dict(new)
    prior=0
    for (composition,used_current),count in staged.items():
        if sum(composition)!=4:continue
        if used_current:
            new_path["+".join(map(str,composition))]+=count
        else:
            prior+=count
    assert sum(new_path.values())+prior==math.comb(20,4)
    return new_path,prior,first


def _read_draws(db):
    # The V37 core immutable ledger is our only source of real identities.
    cursor=db.execute("SELECT seq,draw_no,day,pos FROM draw_ledger ORDER BY seq")
    for seq,draw,day,pos in cursor:
        rows=db.execute("SELECT num,hit,heat_seat,heat_move,life_wait FROM ball_step WHERE draw_no=? ORDER BY num",(draw,)).fetchall()
        if len(rows)!=80 or sum(r[1] for r in rows)!=20:
            raise ValueError(f"Bad 80/20 row integrity at draw {draw}")
        yield {"seq":seq,"draw_no":draw,"day":day,"pos":pos,
               "wins":frozenset(r[0] for r in rows if r[1]),
               "heat":{r[0]:r[2] for r in rows},
               "move":{r[0]:r[3] for r in rows}}


def _steps(db):
    return db.execute("SELECT COUNT(*) FROM draw_ledger").fetchone()[0]


def build(db_path,progress=None):
    con=sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys=ON")
    try:
        init_db(con)
        steps=_steps(con)
        old=con.execute("SELECT seq,engine_version FROM v37_family_step ORDER BY seq DESC LIMIT 1").fetchone()
        completed=old[0] if old else 0
        if old and old[1]!=ENGINE_VERSION:raise ValueError("Family expert version changed: use new database")
        if completed>steps:raise ValueError("Family expert ahead of shared ledger")
        history=deque(maxlen=WINDOW-1)
        prev=None
        prev_heat={}
        day_count=0
        added=0
        cutoff=con.execute("SELECT day FROM draw_ledger ORDER BY day LIMIT 1 OFFSET ?",
                          (steps//2,)).fetchone()
        midpoint=cutoff[0] if cutoff else ""
        total_summaries=[]
        for d in _read_draws(con):
            pos=d["pos"];day=d["day"];seq=d["seq"];no=d["draw_no"]
            if prev is None or (prev["day"]!=day or pos!=prev["pos"]+1):
                history.clear()
            if seq<=completed:
                # Reconstruct last 11 *real* history draws for append-only new suffix.
                history.append(d)
                prev=d
                prev_heat=d["heat"]
                continue
            wins=d["wins"]
            prior_full={2:{},3:{},4:{}}
            for old_draw in history:
                shared=sorted(wins & old_draw["wins"])
                for size in (2,3,4):
                    if len(shared)>=size:
                        for family in combinations(shared,size):
                            # nearest preceding full family yields exact silent length.
                            prior_full[size][family]=old_draw
            repeat2=len(prior_full[2]);repeat3=len(prior_full[3])
            repeat4=len(prior_full[4])
            consecutive=sum(1 for q in prior_full[4].values() if q["pos"]==pos-1)
            silent=repeat4-consecutive
            paths,already,first=first_coverage_paths(wins,history,pos)
            old_to_new=Counter()
            for n in range(1,81):
                before=prev_heat.get(n) if prev else None
                now=d["heat"][n]
                if before in SIX and now in SIX:
                    old_to_new[(before,now)]+=1
            up=sum(count for (a,b),count in old_to_new.items() if SIX.index(b)>SIX.index(a))
            down=sum(count for (a,b),count in old_to_new.items() if SIX.index(b)<SIX.index(a))
            still=sum(count for (a,b),count in old_to_new.items() if a==b)
            directional=0
            examples=[]
            dialogues=[]
            # This is an exhaustive repeated-quartet count; only up to 8
            # individual quartet evidence records per draw are materialized.
            # The complete eligible repeat count remains in step payload.
            for family,source in sorted(prior_full[4].items()):
                up_f=sum(d["move"][n]=="YUKSELIS" for n in family)
                down_f=sum(d["move"][n]=="DUSUS" for n in family)
                if up_f and down_f:directional+=1
                if len(examples)>=EXAMPLES_PER_DRAW:continue
                old_eid=[]
                for n in family:
                    es=con.execute("""SELECT event_id FROM reservoir_event
                              WHERE draw_no=? AND num=? AND motor_id='HEAT_SEAT'""",
                              (no,n)).fetchall()
                    old_eid.extend(e[0] for e in es)
                relation=("ZIT_YON_AYNI_AILE" if up_f and down_f else
                          "YON_YUKSELISLI_AILE" if up_f else
                          "YON_DUSUSLU_AILE" if down_f else "SABIT_AILE")
                family_str=_memberstring(family)
                episode_id=f"V37B|{no}|AILE4|{family_str}"
                examples.append((episode_id,no,seq,4,family_str,
                   "ARDISIK_4_4" if source["pos"]==pos-1 else "SESSIZLIK_SONRASI_4_4",
                   source["draw_no"],source["pos"],pos-source["pos"]-1,
                   json.dumps([d["move"][n] for n in family],ensure_ascii=False),
                   json.dumps(sorted(old_eid)),json.dumps([source["draw_no"],no])))
                if up_f or down_f:
                    dialogues.append((episode_id+":YON",no,seq,family_str,relation,
                        up_f,down_f,json.dumps(sorted(old_eid))))
            row={"day":day,"pos":pos,"draw_no":no,"seq":seq,
                 "phase":"EGITIM" if day<midpoint else "TEST",
                 "pair_repeats":repeat2,"triple_repeats":repeat3,
                 "quartet_repeats":repeat4,"quartet_consecutive":consecutive,
                 "quartet_silent_return":silent,
                 "quartet_new_cover":sum(paths.values()),
                 "quartet_already_covered":already,
                 "heat_up":up,"heat_down":down,"heat_still":still,
                 "heat_change_total":up+down,
                 "directional_repeat_quartets":directional,
                 "linked_examples":len(examples),
                 "raw_20":20,"complete_80":80,
                 "warning":"KILAVUZ: Parçalı yollar yalnız mevcut 4/4'ün 12 adımlık ilk kapsama izidir"}
            for key in PARTIAL_PATHS:
                row["quartet_path_"+key]=paths.get(key,0)
            con.execute("BEGIN")
            con.execute("INSERT INTO v37_family_step VALUES(?,?,?,?,?,?)",
                        (no,seq,day,pos,json.dumps(row,ensure_ascii=False,sort_keys=True),ENGINE_VERSION))
            con.executemany("INSERT INTO v37_heat_transition VALUES(?,?,?,?)",
                            [(no,a,b,c) for (a,b),c in old_to_new.items()])
            con.executemany("INSERT INTO v37_family_examples VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",examples)
            con.executemany("INSERT INTO v37_family_heat_dialogue VALUES(?,?,?,?,?,?,?,?)",dialogues)
            con.commit()
            total_summaries.append(row)
            added+=1
            history.append(d)
            prev=d
            prev_heat=d["heat"]
            if progress and (added%200==0 or seq==steps):
                progress(seq,steps,"V37 aile + yön uzmanları",day)
        result={"engine_version":ENGINE_VERSION,"source_draws":steps,
                "new_draws":added,
                "completed_draws":con.execute("SELECT COUNT(*) FROM v37_family_step").fetchone()[0],
                "repeated_quartet_evidence_rows":con.execute("SELECT COUNT(*) FROM v37_family_examples").fetchone()[0],
                "linked_direction_events":con.execute("SELECT COUNT(*) FROM v37_family_heat_dialogue").fetchone()[0],
                "direction_transition_rows":con.execute("SELECT COUNT(*) FROM v37_heat_transition").fetchone()[0],
                "window":WINDOW,"examples_per_draw_limit":EXAMPLES_PER_DRAW,
                "note":"Aile tekrar sayıları tam, 4/4 parçalı kapsama sınıfları tam; bireysel aile örnekleri her çekiliş için en fazla 8, seçici gözlemdir. Gizli RNG klonlama iddiası yok."}
        return result
    finally:
        con.close()


def export(db_path,target):
    con=sqlite3.connect(str(db_path))
    try:
        rows=[]
        for (jsonstr,) in con.execute("SELECT payload FROM v37_family_step ORDER BY seq"):
            rows.append(json.loads(jsonstr))
        summary={}
        if rows:
            for phase in ("EGITIM","TEST"):
                subset=[r for r in rows if r["phase"]==phase]
                if not subset:continue
                avg=lambda name:round(sum(r[name] for r in subset)/len(subset),5)
                summary[phase]={"draws":len(subset),
                  "avg_pair_repeats":avg("pair_repeats"),
                  "avg_triple_repeats":avg("triple_repeats"),
                  "avg_quartet_repeats":avg("quartet_repeats"),
                  "avg_silent_quartet_return":avg("quartet_silent_return"),
                  "avg_up":avg("heat_up"),"avg_down":avg("heat_down"),
                  "total_4_cover":sum(r["quartet_new_cover"] for r in subset),
                  "total_4_already":sum(r["quartet_already_covered"] for r in subset)}
        with zipfile.ZipFile(str(target),"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            z.writestr("00_OZET_VE_KURALLAR.txt",
              ("V37 B - Ortak hafizadan aile ve altı sıcaklık yön uzmanları\n"
               "=====================================================\n"
               "Kaynak: V37 80 sayı SQLite draw_ledger ve ball_step. Veri kopyalanmaz.\n"
               "Aile2/3/4 tekrarları önceki 11 GERÇEK aralıksız çekilişte tam\n"
               "birleşmiş farklı ailelerin bu çekilişte yine tam görünmesidir.\n"
               "Dörtlü aynı çekilişte 4/4 ise ardışık veya en az 1 çekiliş sessiz\n"
               "tam birleşme seçilir; sessiz demek TÜM ÜYELER hiç çıkmadı DEĞİL!\n"
               "4/4 bu çekilişteyse geçmiş 11+bu çekilişte her üyenin ilk gelişi\n"
               "ile 3+1, 2+2, 2+1+1 gibi KAPSAMA YOLLARI tam sayılır.\n"
               "Bu yollar farklı çekilişlerde hiçbir zaman 4/4 olmayan bütün\n"
               "parçalı aileleri kapsamaz; onları ileri alt dallar araştıracak.\n"
               "Yön uzmanı gerçek 6 sıcaklık durumlarının 36 olası geçişini\n"
               "önceki çekilişten bu çekilişe aktarır.\n"
               "İki yön farklıysa kayıtlı örnek aileye yön delilleri bağlanır.\n"
               "Kişisel aile örnekleri çekiliş başına ilk 8 ile SINIRLIDIR;\n"
               "dört aile tekrarının TAM SAYISI ana tabloda korunur.\n"
               "Önceki 11 kayıt eksik/gün değişikliği halinde kesilir.\n"
               "Kısa tarihsel benzerlik gelecek 20 sayı bilmek anlamına gelmez.\n"
              ).encode("utf-8-sig"))
            def csvwrite(name,fields,data):
                s=io.StringIO();writer=csv.DictWriter(s,fieldnames=fields,
                      **CSV_OPTS,extrasaction="ignore")
                writer.writeheader()
                writer.writerows(data)
                z.writestr(name,s.getvalue().encode("utf-8-sig"))
            csvwrite("01_HER_CEKILIS_AILE_2_3_4_AYRINTILI.csv",OUT_FIELDS,rows)
            heats=[{"draw_no":a,"seq":b,"old_heat":c,"new_heat":d,"count":e,
                    "direction":"YUKSELIS" if SIX.index(d)>SIX.index(c)
                                else "DUSUS" if SIX.index(d)<SIX.index(c) else "SABIT"}
                for a,b,c,d,e in con.execute("""SELECT ht.draw_no,dl.seq,
                    ht.old_heat,ht.new_heat,ht.count
                    FROM v37_heat_transition ht JOIN draw_ledger dl
                    ON dl.draw_no=ht.draw_no ORDER BY dl.seq,ht.old_heat,ht.new_heat""")]
            csvwrite("02_ALTI_ISI_HAVUZU_YON_GECIS_MATRISI.csv",HEAT_FIELDS,heats)
            families=[{"draw_no":x[1],"seq":x[2],"family_size":x[3],"family_numbers":x[4],
                      "event_type":x[5],"previous_full_draw_no":x[6],
                      "previous_full_pos":x[7],"quiet_real_draws":x[8],
                      "heat_directions":x[9],"parent_reservoir_event_ids":x[10],
                      "source_draws":x[11]} for x in con.execute(
                      "SELECT * FROM v37_family_examples ORDER BY seq,event_id")]
            csvwrite("03_DORTLU_AILE_SOMUT_GECMIS_DELILLERI.csv",EXAMPLE_FIELDS,families)
            links=[{"event_id":e,"draw_no":dn,"seq":seq,"numbers":nos,
                    "relation":rel,"heat_up":u,"heat_down":d,"source_event_ids":src}
                   for e,dn,seq,nos,rel,u,d,src in con.execute(
                      "SELECT * FROM v37_family_heat_dialogue ORDER BY seq,event_id")]
            csvwrite("04_AILE_ILE_YON_MOTORLARI_DIYALOG.csv",DIALOGUE_FIELDS,links)
            z.writestr("05_EGITIM_TEST_OZET.json",json.dumps(summary,ensure_ascii=False,indent=2).encode("utf-8"))
            z.writestr("06_UZMAN_TAM_KAPSAM_VE_SINIRLARI.json",json.dumps({
                    "source":"v37 sqlite","repeated_family_sizes":[2,3,4],
                    "family_repeat_window_prior_real_draws":WINDOW-1,
                    "quartet_first_cover_path_exact":True,
                    "all_4_4_quartet_paths_exact":True,
                    "all_fragment_only_without_same_draw_4_4":"HENUZ_YOK",
                    "family_examples_per_draw_limit":EXAMPLES_PER_DRAW,
                    "heat_transition_cells":36,
                    "no_lookahead":True},ensure_ascii=False,indent=2).encode("utf-8"))
        with zipfile.ZipFile(str(target)) as z:
            assert z.testzip() is None and len(z.namelist())==7
        return summary
    finally:
        con.close()
