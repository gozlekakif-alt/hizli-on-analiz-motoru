# -*- coding: utf-8 -*-
"""V37 Stage A — durable, append-only shared 80-ball life ledger.

A reproducible SQLite core for experts; NOT 207 implemented motors, no
forecasting. Every real draw adds 80 life snapshots and changed-reservoir
events with linked evidence. Future specialist engines read the same ledger.

Input must be history in chronological order; on-disk database can resume
only an IDENTICAL PREFIX plus appended draws. Corrections require a new DB.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import zipfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from v36_rng_davranis_klonu import sorted_draws, BALLS, SIX, SIZE, DECAY, on_slot

SCHEMA_VERSION=1
ALL80=(1<<80)-1
OPERATING=("POOL20","HEAT_SEAT","HEAT_DIRECTION","WAIT_DAY","WAIT_LIFE",
           "FREQ11","BAND","HALF")
DAY_BUCKETS=("0","1-3","4-5","6","7","8","9","10","11+")
BRANCH_DOC={
    "POOL20":"GERCEK_20 / CIKMAYAN_60, numbered pool admission and exit",
    "HEAT_SEAT":"Six mutually exclusive EWMA heat seats",
    "HEAT_DIRECTION":"Seat motion YUKSELIS / DUSUS / SABIT",
    "WAIT_DAY":"Within-day verified consecutive nonappearance",
    "WAIT_LIFE":"Cross-day verified consecutive nonappearance",
    "FREQ11":"11 actual adjacent draw 1/0 signature and frequency",
    "BAND":"Eight 10-number bands, static identity",
    "HALF":"1..40 vs 41..80, static identity"}
STEP_COLUMNS=("draw_no","num","seq","hit","day_hits","life_hits",
              "day_wait","life_wait","day_run","life_run","history11",
              "last11_count","valid11","heat","heat_seat","heat_move",
              "band","half","source_hash")
DAILY_COLUMNS=("day","draws","first_no","last_no","life_rows","events","dialogues",
               "all80_20_60_valid","heat6_seats_valid")
CSV_KW=dict(delimiter=";",lineterminator="\n")


def canonical(d):
    # The same source draw always has the same identity across runs.
    return json.dumps([d["day"],int(d["pos"]),int(d["no"]),sorted(int(x) for x in d["nums"])],
                      ensure_ascii=False,separators=(",",":"))


def digest(d):
    return hashlib.sha256(canonical(d).encode("utf-8")).hexdigest()


def wait_class(n):
    if n is None:return "BILINMIYOR"
    if n==0:return "0"
    if n>=11:return "11+"
    if n>=6:return str(n)
    if n>=4:return "4-5"
    return "1-3"


def setup(con):
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS draw_ledger(
      seq INTEGER PRIMARY KEY,draw_no INTEGER UNIQUE NOT NULL,
      day TEXT NOT NULL,pos INTEGER NOT NULL,clock TEXT NOT NULL,
      mask_hex TEXT NOT NULL,source_hash TEXT NOT NULL,
      gap_from_prior INTEGER NOT NULL,
      UNIQUE(day,pos)
    );
    CREATE TABLE IF NOT EXISTS ball_life(
      num INTEGER PRIMARY KEY CHECK(num BETWEEN 1 AND 80),
      life_hits INTEGER NOT NULL DEFAULT 0,
      life_run INTEGER NOT NULL DEFAULT 0,
      life_wait INTEGER,
      last_hit_seq INTEGER,
      last_hit_draw INTEGER,
      last_hit_day TEXT,
      heat REAL NOT NULL DEFAULT 0,
      heat_seat TEXT NOT NULL DEFAULT 'UNKNOWN',
      history11 INTEGER NOT NULL DEFAULT 0,
      history_valid INTEGER NOT NULL DEFAULT 0,
      last_seen_seq INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS ball_step(
      draw_no INTEGER NOT NULL, num INTEGER NOT NULL,
      seq INTEGER NOT NULL, hit INTEGER NOT NULL,
      day_hits INTEGER NOT NULL,life_hits INTEGER NOT NULL,
      day_wait INTEGER,life_wait INTEGER,
      day_run INTEGER NOT NULL,life_run INTEGER NOT NULL,
      history11 TEXT,last11_count INTEGER,valid11 INTEGER NOT NULL,
      heat REAL NOT NULL,heat_seat TEXT NOT NULL,heat_move TEXT NOT NULL,
      band TEXT NOT NULL,half TEXT NOT NULL,source_hash TEXT NOT NULL,
      PRIMARY KEY(draw_no,num),
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no)
    ) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS motor_registry(
      motor_id TEXT PRIMARY KEY,version INTEGER NOT NULL,
      status TEXT NOT NULL,meaning TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reservoir_event(
      event_id TEXT PRIMARY KEY,
      draw_no INTEGER NOT NULL,num INTEGER NOT NULL,
      motor_id TEXT NOT NULL,old_bin TEXT,new_bin TEXT NOT NULL,
      kind TEXT NOT NULL,source_hash TEXT NOT NULL,
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no)
    );
    CREATE TABLE IF NOT EXISTS event_dialogue(
      dialogue_id TEXT PRIMARY KEY,
      draw_no INTEGER NOT NULL,num INTEGER NOT NULL,
      motor_ids TEXT NOT NULL,source_event_ids TEXT NOT NULL,
      relation TEXT NOT NULL,
      FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no)
    );
    CREATE TABLE IF NOT EXISTS checkpoint(
      id INTEGER PRIMARY KEY CHECK(id=1),
      last_seq INTEGER NOT NULL,last_draw INTEGER NOT NULL,
      last_day TEXT NOT NULL,last_pos INTEGER NOT NULL,
      prefix_sha256 TEXT NOT NULL,engine_version INTEGER NOT NULL,
      committed_draws INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_bs_seq ON ball_step(seq);
    CREATE INDEX IF NOT EXISTS idx_bs_num_seq ON ball_step(num,seq);
    CREATE INDEX IF NOT EXISTS idx_event_draw ON reservoir_event(draw_no);
    CREATE INDEX IF NOT EXISTS idx_dialogue_draw ON event_dialogue(draw_no);
    """)
    con.executemany("INSERT OR IGNORE INTO ball_life(num) VALUES(?)",
                    [(n,) for n in BALLS])
    con.executemany("INSERT OR IGNORE INTO motor_registry VALUES(?,?,?,?)",
                    [(m,1,"CALISIYOR_V37_A",BRANCH_DOC[m]) for m in OPERATING])
    con.execute("INSERT OR IGNORE INTO meta VALUES('schema_version',?)",(str(SCHEMA_VERSION),))
    con.commit()


def last_state(con):
    draw=con.execute("SELECT seq,draw_no,day,pos FROM draw_ledger ORDER BY seq DESC LIMIT 1").fetchone()
    lifetime={r[0]:list(r[1:]) for r in con.execute(
       "SELECT num,life_hits,life_run,life_wait,last_hit_seq,last_hit_draw,last_hit_day,"
       "heat,heat_seat,history11,history_valid,last_seen_seq FROM ball_life ORDER BY num")}
    return draw,lifetime


def event_id(draw_no,num,motor,new):
    return hashlib.sha256(f"V37A|{draw_no}|{num}|{motor}|{new}".encode()).hexdigest()[:32]


def source_rows(draws,include_partial):
    days,full,warnings=sorted_draws(draws,include_partial)
    seq=[d for day,group in days for d in group]
    return seq,days,full,warnings


def replay(draws,db_path,include_partial=False,progress=None):
    """Insert only new suffix. Prevent corrupted/missing/changed prefix.

    Persistence belongs to the db_path caller, not automatically GitHub.
    Return a public summary; SQLite itself can be zipped separately.
    """
    seq,days,full,warnings=source_rows(draws,include_partial)
    con=sqlite3.connect(str(db_path),timeout=30)
    try:
      setup(con)
      existing=con.execute("SELECT draw_no,day,pos,source_hash FROM draw_ledger ORDER BY seq").fetchall()
      if len(existing)>len(seq):
          raise ValueError("Kaynak geçmiş eskisinden kısa: eski veritabanı değiştirilmedi.")
      for i,(draw_no,day,pos,h) in enumerate(existing):
          d=seq[i]
          if (draw_no,day,pos,h)!=(d["no"],d["day"],d["pos"],digest(d)):
              raise ValueError(f"Geçmiş değişmiş veya eksilmiş: sıra {i+1}. Yeni DB gerekir.")
      previous,life=last_state(con)
      processed=0
      prev_day=previous[2] if previous else None
      prev_pos=previous[3] if previous else None
      prev_seq=previous[0] if previous else 0
      prior_mask=0
      if previous:
          prior_mask=int(con.execute("SELECT mask_hex FROM draw_ledger WHERE draw_no=?",
                                     (previous[1],)).fetchone()[0],16)
      # Resuming a day needs last per-ball day_hits/wait/run. Read only 80 records.
      daily={n:[0,0,0] for n in BALLS}
      if previous:
          for n,hits,wait,run in con.execute(
              "SELECT num,day_hits,day_wait,day_run FROM ball_step WHERE draw_no=?",
              (previous[1],)):
              daily[n]=[hits,wait,run]
      checkpoint=con.execute("SELECT prefix_sha256 FROM checkpoint WHERE id=1").fetchone()
      prefix=checkpoint[0] if checkpoint else ("0"*64)
      with_new=seq[len(existing):]
      if not with_new:
          return summary(con,days,full,warnings,0)
      for j,d in enumerate(with_new):
          day=d["day"];pos=d["pos"];draw_no=d["no"];source=digest(d)
          current_date=date.fromisoformat(day)
          contiguous=(prev_day==day and prev_pos is not None and pos==prev_pos+1) or (
              prev_day is not None and prev_day!=day and
              current_date==date.fromisoformat(prev_day)+timedelta(days=1) and
              prev_pos==217 and pos==1)
          newday=(prev_day!=day)
          gap_flag=int(prev_day is not None and not contiguous)
          if newday:daily={n:[0,0,0] for n in BALLS}
          new_seq=prev_seq+1
          win=set(d["nums"])
          mask=sum(1<<(n-1) for n in win)
          scores={}
          after=dict()
          for n in BALLS:
              v=life[n]
              scores[n]=v[6]*DECAY+int(n in win)
          ranking=sorted(BALLS,key=lambda n:(scores[n],n))
          index=0
          for rank,amount in enumerate(SIZE):
              for n in ranking[index:index+amount]:after[n]=SIX[rank]
              index+=amount
          assert Counter(after.values())==dict(zip(SIX,SIZE)), "Six heat seats mismatch"
          states=[];events=[];dialogues=[];lifelines=[]
          mask_hex=f"{mask:020x}"
          con.execute("BEGIN")
          con.execute("INSERT INTO draw_ledger VALUES(?,?,?,?,?,?,?,?)",
                      (new_seq,draw_no,day,pos,on_slot(pos),mask_hex,source,gap_flag))
          for n in BALLS:
              v=life[n]  # life_hits,life_run,life_wait,last_hit_seq,last_hit_draw,last_hit_day,heat,seat,history11,valid,last_seen_seq
              hit=int(n in win)
              lh=v[0]+hit
              lr=(v[1]+1 if hit and contiguous else int(hit))
              # Unknown is never interpreted as observed nonappearance.
              lw=(0 if hit else (v[2]+1 if contiguous and v[2] is not None else
                                   1 if not gap_flag else None))
              day_hits=daily[n][0]+hit
              day_run=daily[n][2]+1 if hit and not newday and not gap_flag else hit
              if hit:day_wait=0
              elif (newday or gap_flag):day_wait=1 if not gap_flag else None
              else:day_wait=(daily[n][1]+1 if daily[n][1] is not None else None)
              valid=(v[9]+1 if contiguous else 1)
              bits=((v[8]<<1)|hit)&2047
              valid11=int(valid>=11)
              bitstr=f"{bits:011b}" if valid11 else ""
              count=bits.bit_count() if valid11 else None
              old_seat=v[7] if isinstance(v[7],str) else "UNKNOWN"
              new_seat=after[n]
              ixold=SIX.index(old_seat) if old_seat in SIX else SIX.index(new_seat)
              ixnew=SIX.index(new_seat)
              move=("YUKSELIS" if ixnew>ixold else "DUSUS" if ixnew<ixold else "SABIT")
              band=f"{(n-1)//10*10+1:02d}-{(n-1)//10*10+10:02d}"
              half="ALT40" if n<=40 else "UST40"
              states.append((draw_no,n,new_seq,hit,day_hits,lh,day_wait,lw,
                             day_run,lr,bitstr,count,valid11,scores[n],new_seat,
                             move,band,half,source))
              old_hit=(int(prior_mask & (1<<(n-1))) if prev_day is not None else None)
              # New day still compares 20/60, because observation occurred.
              bins={
                "POOL20":("CIKAN20" if old_hit else "CIKMAYAN60") if old_hit is not None else None,
                "HEAT_SEAT":old_seat if old_seat!="UNKNOWN" else None,
                "HEAT_DIRECTION":None,
                "WAIT_DAY":wait_class(daily[n][1]) if not newday else None,
                "WAIT_LIFE":wait_class(v[2]) if prev_day is not None else None,
                "FREQ11":None if v[9]<11 else str(v[8].bit_count()),
                "BAND":None if prev_day is None else band,
                "HALF":None if prev_day is None else half}
              newbins={"POOL20":"CIKAN20" if hit else "CIKMAYAN60",
                       "HEAT_SEAT":new_seat,"HEAT_DIRECTION":move,
                       "WAIT_DAY":wait_class(day_wait),"WAIT_LIFE":wait_class(lw),
                       "FREQ11":str(count) if valid11 else "EKSIK",
                       "BAND":band,"HALF":half}
              linked=[]
              for m in OPERATING:
                  before=bins[m];new=newbins[m]
                  if before!=new:
                      eid=event_id(draw_no,n,m,new)
                      kind="GIRIS" if before is None else "DEGISIM"
                      events.append((eid,draw_no,n,m,before,new,kind,source))
                      linked.append(eid)
              if len(linked)>=2:
                  # A factual co-occurrence link, not a causal statement.
                  d_id=hashlib.sha256(f"V37_DIALOGUE|{draw_no}|{n}".encode()).hexdigest()[:32]
                  related=sorted({item[3] for item in events if item[2]==n})
                  dialogues.append((d_id,draw_no,n,json.dumps(related),
                                    json.dumps(sorted(linked)),"ESZAMANLI_GERCEK_DEGISIM"))
              new_hit_seq=new_seq if hit else v[3]
              new_hit_draw=draw_no if hit else v[4]
              new_hit_day=day if hit else v[5]
              lifelines.append((lh,lr,lw,new_hit_seq,new_hit_draw,new_hit_day,
                                scores[n],new_seat,bits,valid,new_seq,n))
              life[n]=[lh,lr,lw,new_hit_seq,new_hit_draw,new_hit_day,
                       scores[n],new_seat,bits,valid,new_seq]
              daily[n]=[day_hits,day_wait,day_run]
          con.executemany("INSERT INTO ball_step VALUES("+",".join("?"*len(STEP_COLUMNS))+")",states)
          con.executemany("INSERT INTO reservoir_event VALUES(?,?,?,?,?,?,?,?)",events)
          con.executemany("INSERT INTO event_dialogue VALUES(?,?,?,?,?,?)",dialogues)
          con.executemany("""UPDATE ball_life SET life_hits=?,life_run=?,life_wait=?,
              last_hit_seq=?,last_hit_draw=?,last_hit_day=?,heat=?,heat_seat=?,
              history11=?,history_valid=?,last_seen_seq=? WHERE num=?""",lifelines)
          prefix=hashlib.sha256((prefix+"|"+source).encode()).hexdigest()
          con.execute("INSERT OR REPLACE INTO checkpoint VALUES(1,?,?,?,?,?,?,?)",
                      (new_seq,draw_no,day,pos,prefix,SCHEMA_VERSION,new_seq))
          con.commit()
          processed+=1
          prev_day=day;prev_pos=pos;prev_seq=new_seq;prior_mask=mask
          if progress and (j%60==0 or j==len(with_new)-1):
              progress(j+1,len(with_new),"Ortak 80 sayı hayat hafızası",day)
      return summary(con,days,full,warnings,processed)
    finally:
      con.close()


def summary(con,days,full,warnings,added):
    db=con.execute("SELECT COUNT(*) FROM draw_ledger").fetchone()[0]
    cards=con.execute("SELECT COUNT(*) FROM ball_step").fetchone()[0]
    events=con.execute("SELECT COUNT(*) FROM reservoir_event").fetchone()[0]
    links=con.execute("SELECT COUNT(*) FROM event_dialogue").fetchone()[0]
    ck=con.execute("SELECT last_draw,last_day,last_pos,prefix_sha256 FROM checkpoint WHERE id=1").fetchone()
    daily=[]
    for day,count,first,last in con.execute(
        "SELECT day,COUNT(*),MIN(draw_no),MAX(draw_no) FROM draw_ledger GROUP BY day ORDER BY day"):
        daily.append({"day":day,"draws":count,"first_no":first,"last_no":last,
                      "life_rows":count*80,
                      "events":con.execute("""SELECT COUNT(*) FROM reservoir_event
                           WHERE draw_no IN (SELECT draw_no FROM draw_ledger WHERE day=?)""",(day,)).fetchone()[0],
                      "dialogues":con.execute("""SELECT COUNT(*) FROM event_dialogue
                           WHERE draw_no IN (SELECT draw_no FROM draw_ledger WHERE day=?)""",(day,)).fetchone()[0],
                      "all80_20_60_valid":1,"heat6_seats_valid":1})
    info={"version":"V37_STAGE_A_ORIGINAL_80_LIFE","schema_version":SCHEMA_VERSION,
          "new_draws_added":added,"draw_count":db,"ball_step_rows":cards,
          "reservoir_change_events":events,"same_number_event_dialogues":links,
          "last_draw":ck[0] if ck else None,
          "last_day":ck[1] if ck else None,
          "last_pos":ck[2] if ck else None,
          "prefix_sha256":ck[3] if ck else None,
          "engine_operational":list(OPERATING),
          "engine_operational_count":len(OPERATING),
          "engine_design_remaining":"Diğer V37 207 uzman dalları yalnız tasarım aşamasında",
          "full_days_in_source":len(full),
          "days_in_db":len(daily),
          "source_warnings":warnings,
          "daily":daily}
    assert cards==80*db, "Missing ball steps"
    return info


def export(db_path,zip_path,summary_data):
    with sqlite3.connect(str(db_path)) as conn:
      result=conn.execute("PRAGMA integrity_check").fetchone()[0]
      if result!="ok":raise ValueError("SQLite integrity check failed: "+str(result))
      checks=conn.execute("""SELECT COUNT(*) FROM (
          SELECT draw_no,SUM(hit) AS cnt,COUNT(*) AS n FROM ball_step
          GROUP BY draw_no HAVING cnt!=20 OR n!=80)""").fetchone()[0]
      if checks:raise ValueError(f"Invalid 20/80 draw states: {checks}")
      seat_checks=0
      for row in conn.execute("""SELECT draw_no,heat_seat,COUNT(*) FROM ball_step
                          GROUP BY draw_no,heat_seat"""):
          if row[2]!=dict(zip(SIX,SIZE)).get(row[1]):
              seat_checks+=1
      if seat_checks:raise ValueError("Six seats constraint not met")
      readme=("V37 Ortak 80 Sayi Yasam Hafizasi — Aşama A\n"
         "=========================================\n"
         "Kaynak: veri.txt; bütün 80 sayı × her GERÇEK çekiliş kayıtlıdır.\n"
         "Çekirdek 8 çalışan uzman motorunu kullanır (207 dal henüz çalışmıyor).\n"
         "SQLite: draw_ledger,ball_life,ball_step,motor_registry,\n"
         "reservoir_event,event_dialogue,checkpoint,meta.\n"
         "draw_ledger: resmi sonuçlar ve her çekilişin SHA-256 kaynak izi.\n"
         "ball_life: günler boyunca silinmeyen sayı yaşamının güncel toplamı.\n"
         "ball_step: her çekilişte 80 sayı için eski veriye dayalı 1/0 + \n"
         "günlük ve ömürlük sayaç + 11'li imza + 6 ısı koltuğu.\n"
         "reservoir_event: motor haznesine girme/değişme delili.\n"
         "event_dialogue: aynı sayıda birden fazla motor olayı eşzamanlıysa\n"
         "kaynak event_id'leriyle ilişkili olay kaydı; bu nedensellik değildir.\n"
         "Aynı prefix tekrar gelirse 0 satır işlenir; gerçek veri değişirse\n"
         "eski DB bozulmaz, yeni veritabanı / yeniden başlatma gerekir.\n"
         "Eksik çekiliş UNKNOWN; 01:02→07:02 sıra 13→14 gerçekte ardışıktır.\n"
         "Streamlit'in geçici DB'si sunucu kapanınca kalıcı olmaz. ZIP saklanmalı.\n"
         "Gizli RNG algoritması, gelecek 20 sayısı veya 207 çalışır motor iddiası yoktur.\n")
    with zipfile.ZipFile(str(zip_path),"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.write(str(db_path),arcname="01_V37_ORTAK_80_SAYI_HAFIZA.sqlite3")
        z.writestr("00_OKU_BENI.txt",readme.encode("utf-8-sig"))
        z.writestr("02_HAFIZA_OZET.json",json.dumps(
            {k:v for k,v in summary_data.items() if k!="daily"},
            ensure_ascii=False,indent=2).encode("utf-8"))
        out=io.StringIO()
        wr=csv.DictWriter(out,fieldnames=DAILY_COLUMNS,**CSV_KW)
        wr.writeheader();wr.writerows(summary_data["daily"])
        z.writestr("03_GUNLUK_217_ADIM_DENETIM.csv",out.getvalue().encode("utf-8-sig"))
        out=io.StringIO()
        wr=csv.writer(out,**CSV_KW)
        wr.writerow(["motor_id","version","status","meaning"])
        for m in OPERATING:wr.writerow([m,1,"CALISIYOR_V37_A",BRANCH_DOC[m]])
        z.writestr("04_CALISAN_UZMAN_DALLARI.csv",out.getvalue().encode("utf-8-sig"))
        z.writestr("05_SQLITE_KULLANIM_ORNEKLERI.sql",
         ("-- Tek sayının gerçek çekilişlerdeki geçmiş yolu:\n"
          "SELECT * FROM ball_step WHERE num=23 ORDER BY seq;\n"
          "-- Bir çekilişte hangi motor haznesi değişti:\n"
          "SELECT * FROM reservoir_event WHERE draw_no=61653;\n"
          "-- Aynı anda değişen motorlar ve kaynak olayları:\n"
          "SELECT * FROM event_dialogue WHERE num=23 ORDER BY draw_no;\n"
          "-- İkili, üçlü, dörtlü aile uzmanları sonraki aşamada bağlanacak.\n"
         ).encode("utf-8"))
    with zipfile.ZipFile(str(zip_path)) as z:
        assert z.testzip() is None
    return str(zip_path)


def run_text(text,db_path,zip_path,include_partial=False,progress=None):
    from v11_arastirma import read_draws
    draws,bad=read_draws(text)
    info=replay(draws,db_path,include_partial,progress)
    info["text_parser_warnings"]=len(bad)
    export(db_path,zip_path,info)
    return info
