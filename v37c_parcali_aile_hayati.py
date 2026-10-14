# -*- coding: utf-8 -*-
"""V37C: fourth member can complete a family ACROSS draws without 4/4 once.

Reads V37A's immutable draw_ledger and ball_step (single shared memory).
A) EXACT counts across all 1,581,580 possible 4-families of first-appearance
   patterns in TWO and THREE adjacent real draws, excluding any 4/4 in the
   observed 2- or 3-draw fragment. Combinatorics, no family enumeration.
B) Lifetimes of a PRE-REGISTERED, outcome-blind 2048-quartet simple random
   sample: 0/1/2/3/4 seen per draw, silent episodes, last-12-draw rolling
   fragmented coverage without any earlier SAME-DRAW 4/4, sample reactivation.
Sample family identities and state are persisted in compressed checkpoints;
no cherry-picked winners, no future leakage, no claims of hidden RNG cloning.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import pickle
import random
import sqlite3
import zlib
import zipfile
from collections import Counter
from itertools import combinations

VERSION=2
SAMPLE=2048
LOOKBACK=12
EVENT_CAP=12
UNIVERSE=math.comb(80,4)
LANE_MASKS=tuple(0xFFF<<(12*k) for k in range(4))
SHIFT_MASK=sum(0xFFE<<(12*k) for k in range(4))
INSERT=tuple(sum(((m>>k)&1)<<(12*k) for k in range(4)) for m in range(16))
FIELDS=("seq","day","pos","draw_no","global_4_family_universe",
        "exact_two_1+3","exact_two_2+2","exact_two_3+1",
        "exact_three_1+1+2","exact_three_1+2+1","exact_three_2+1+1",
        "sample_0_4","sample_1_4","sample_2_4","sample_3_4","sample_4_4",
        "sample_current_no_4ever","sample_current_first_fragment",
        "sample_fragment_reactivation","sample_fragment_cover_now",
        "sample_silence_3plus","sample_12draw_fragment_eligible",
        "sample_heat_up_on_first_fragment",
        "sample_heat_down_on_first_fragment","source_sample_size",
        "bounded_event_examples","warning")
EVENT_FIELDS=("event_id","seq","draw_no","day","pos","family_numbers",
              "event_type","path","silence_before","previous_fragment_seq",
              "four_number_12bit_history","previous_full4_seq","full4_in_last12",
              "heat_directions",
              "linked_heat_event_ids","last_lookback_source_draws")
CSV_OPTS=dict(delimiter=";",lineterminator="\n")


def _choose(n,k):
    return math.comb(n,k) if n>=k>=0 else 0


def _mask(winners):
    return sum(1<<(n-1) for n in winners)


def _counts_two(a,b):
    """Exact new first-cover families over two draws, NO same-draw 4/4
    in either of these draws. First stage elements belong to a and are
    possibly re-seen in b. Second stage elements are b-a and cannot be a."""
    if a is None or b is None:return (0,0,0)
    only_new=b-a
    prior_not_now=a-b
    # Every qualified family must include >=1 exclusive member of a
    # and >=1 exclusive member of b; all families are distinct.
    # Thus 1+3, 2+2, 3+1 with no four in the b draw.
    return (_choose(len(a),1)*_choose(len(only_new),3)
                 - _choose(len(a & b),1)*_choose(len(only_new),3),
            _choose(len(a),2)*_choose(len(only_new),2)
                 - _choose(len(a & b),2)*_choose(len(only_new),2),
            _choose(len(a),3)*_choose(len(only_new),1)
                 - _choose(len(a & b),3)*_choose(len(only_new),1))


def _counts_three(a,b,c):
    """All fourth-ball families first appearing across exactly 3
    adjacent real draws: 1+1+2, 1+2+1, 2+1+1.
    Exclude quartets seen as 4/4 at draw c. A,B cannot have all four
    because at least one fourth-member appears FIRST in c."""
    if a is None or b is None or c is None:return (0,0,0)
    X=a
    Y=b-a
    Z=c-(a|b)
    XC=X&c
    YC=Y&c
    return (
       max(0,len(X)*len(Y)*_choose(len(Z),2)
               -len(XC)*len(YC)*_choose(len(Z),2)),
       max(0,len(X)*_choose(len(Y),2)*len(Z)
               -len(XC)*_choose(len(YC),2)*len(Z)),
       max(0,_choose(len(X),2)*len(Y)*len(Z)
               -_choose(len(XC),2)*len(YC)*len(Z))
    )


def _catalog():
    # Uniformly sample ALL C(80,4) quartet ranks, independent of outcomes.
    # Rank -> lexicographic 4-combination via combinatorial unranking.
    rng=random.Random(37042026)
    picks=sorted(rng.sample(range(UNIVERSE),SAMPLE))
    result=[]
    for original_rank in picks:
        index=original_rank
        previous=0
        family=[]
        for depth in range(4):
            for n in range(previous+1,81):
                rem=_choose(80-n,3-depth)
                if index>=rem:
                    index-=rem
                else:
                    family.append(n)
                    previous=n
                    break
        if len(family)!=4:raise AssertionError("Unranking failed")
        result.append(tuple(family))
    if len(result)!=SAMPLE or len(set(result))!=SAMPLE:
        raise AssertionError("Sample collision")
    return result


CATALOG=tuple(_catalog())
CATALOG_SHA=hashlib.sha256(json.dumps(CATALOG,separators=(",",":")).encode()).hexdigest()
CATALOG_MASKS=tuple(_mask(c) for c in CATALOG)


def _make_catalogue(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS v37c_step(
     draw_no INTEGER PRIMARY KEY, seq INTEGER NOT NULL, day TEXT NOT NULL,
     pos INTEGER NOT NULL, payload TEXT NOT NULL, version INTEGER NOT NULL,
     FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no));
    CREATE TABLE IF NOT EXISTS v37c_family_events(
     event_id TEXT PRIMARY KEY, draw_no INTEGER NOT NULL, seq INTEGER NOT NULL,
     family_index INTEGER NOT NULL, payload TEXT NOT NULL,
     FOREIGN KEY(draw_no) REFERENCES draw_ledger(draw_no));
    CREATE TABLE IF NOT EXISTS v37c_checkpoint(
     id INTEGER PRIMARY KEY CHECK(id=1),last_seq INTEGER NOT NULL,
     last_draw_no INTEGER NOT NULL, catalogue_sha TEXT NOT NULL,
     engine_version INTEGER NOT NULL, state_zlib BLOB NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_v37c_events_seq ON v37c_family_events(seq);
    """)
    con.execute("INSERT OR IGNORE INTO motor_registry VALUES(?,?,?,?)",
                ("FAMILY.FRAGMENT_2_DRAW_EXACT",VERSION,"CALISIYOR_V37_C",
                 "2 adjacent real draws, exact 1+3,2+2,3+1 fragment families without full4"))
    con.execute("INSERT OR IGNORE INTO motor_registry VALUES(?,?,?,?)",
                ("FAMILY.FRAGMENT_3_DRAW_EXACT",VERSION,"CALISIYOR_V37_C",
                 "3 adjacent real draws exact 2+1+1,1+2+1,1+1+2 without full4"))
    con.execute("INSERT OR IGNORE INTO motor_registry VALUES(?,?,?,?)",
                ("FAMILY.FRAGMENT_LIFE_SAMPLE",VERSION,"CALISIYOR_V37_C",
                 "Pre-registered 2048 4-families across 12-draw rolling history"))
    con.execute("INSERT OR IGNORE INTO motor_registry VALUES(?,?,?,?)",
                ("DIALOGUE.FRAGMENT_HEAT",VERSION,"CALISIYOR_V37_C",
                 "Family fragment events linked to real HEAT_SEAT evidence"))
    con.commit()


def _init_states():
    # sig: 4 packed 12-bit draw histories; prev_cover and ever_full distinguish
    # 4 members seen across draws from same-draw family reunion.
    return [[0,False,False,False,0,0,0,0,0,0,0,0] for _ in range(SAMPLE)]


def _decode_state(stateblob):
    if not stateblob:return _init_states()
    states=pickle.loads(zlib.decompress(stateblob))
    if len(states)!=SAMPLE or any(len(s)!=12 for s in states):
        raise ValueError("Mismatched family state catalogue")
    return states


def _encode_state(states):
    return zlib.compress(pickle.dumps(states,protocol=4),level=6)


def _shape(members,sig):
    first=[]
    for i,n in enumerate(members):
        block=(sig>>(12*i))&0xFFF
        if not block:raise ValueError("incomplete quartet cannot have first cover")
        # The oldest observed 1 is most significant bit. 11 -> oldest 12;
        # a smaller first-observed pos means older history.
        first.append(block.bit_length()-1)
    counts=Counter(first)
    return "+".join(str(counts[x]) for x in sorted(counts,reverse=True))


def _get_draws(con):
    for seq,no,day,pos,maskhex in con.execute(
        "SELECT seq,draw_no,day,pos,mask_hex FROM draw_ledger ORDER BY seq"):
        yield seq,no,day,pos,int(maskhex,16)


def _heat_directions(con,no,members):
    ids=[];moves=[]
    for n,move in con.execute("SELECT num,heat_move FROM ball_step WHERE draw_no=? AND num IN (?,?,?,?) ORDER BY num",
                              (no,*members)):
        moves.append(move)
        if move!="SABIT":
            ids.extend(x[0] for x in con.execute(
               "SELECT event_id FROM reservoir_event WHERE draw_no=? AND num=? AND motor_id='HEAT_SEAT'",
               (no,n)))
    return moves,sorted(set(ids))


def run(db_path,progress=None):
    con=sqlite3.connect(str(db_path),timeout=60)
    try:
      con.execute("PRAGMA foreign_keys=ON")
      con.execute("PRAGMA cache_size=-60000")
      _make_catalogue(con)
      base_count=con.execute("SELECT COUNT(*) FROM draw_ledger").fetchone()[0]
      ck=con.execute("SELECT last_seq,last_draw_no,catalogue_sha,engine_version,state_zlib FROM v37c_checkpoint WHERE id=1").fetchone()
      if ck and (ck[2]!=CATALOG_SHA or ck[3]!=VERSION):
          raise ValueError("V37C motor version or sample changed; use new SQLite")
      last_seq=ck[0] if ck else 0
      if base_count<last_seq:raise ValueError("V37 common ledger shorter than specialist checkpoint")
      states=_decode_state(ck[4] if ck else None)
      # Need only preceding 2 real draws for exact-composition comparisons.
      prev1=None;prev2=None
      processed=0;old=None
      checkpoints=0
      for seq,no,day,pos,ballmask in _get_draws(con):
        wins={n for n in range(1,81) if ballmask & (1<<(n-1))}
        d={"seq":seq,"draw_no":no,"day":day,"pos":pos,"wins":wins}
        adjacent=bool(old and day==old["day"] and pos==old["pos"]+1)
        if not adjacent:prev1=prev2=None
        if seq<=last_seq:
            # Past two real observations reconstructed; the family state
            # is already restored from exactly the last processed sequence.
            prev2=prev1;prev1=d;old=d
            continue
        if seq!=last_seq+processed+1:raise ValueError("Gap in shared ledger sequence")
        p1=prev1["wins"] if prev1 else None
        p2=prev2["wins"] if prev2 and p1 is not None else None
        exact2=_counts_two(p1,wins)
        exact3=_counts_three(p2,p1,wins)
        # Draw boundaries reset the rolling 12, NOT lifelong ever_full flag.
        initial=not adjacent
        summary=Counter()
        interesting=[]
        heat_moves=None
        fragment_count=0
        sample_cover_count=0
        for idx,family in enumerate(CATALOG):
            state=states[idx]
            sig,coverprev,everfull,fragonce,fragcount,fullcount,quiet,qlong,lastfrag,lastfull,everseen,full_sig=state
            if initial:sig=0;full_sig=0;coverprev=False;quiet=0
            on=tuple(bool(ballmask&(1<<(n-1))) for n in family)
            bits=sum((1<<k) for k,b in enumerate(on) if b)
            hit=bits.bit_count()
            summary[f"sample_{hit}_4"]+=1
            if hit==0:quiet+=1
            else:
                qlong=max(qlong,quiet)
            q_before=quiet if hit==0 else state[6]
            if hit>0:quiet=0
            # Lifelong everfull is retained for historical facts, but does
            # NOT permanently disqualify a family from a later silent episode.
            # A fragment-only window requires no 4/4 IN THE ROLLING 12,
            # not no 4/4 in its entire historical life.
            old_eligible=bool(coverprev and full_sig==0)
            sig=((sig<<1)&SHIFT_MASK)|INSERT[bits]
            full_sig=((full_sig<<1)|int(hit==4))&0xFFF
            cover=all(sig&lane for lane in LANE_MASKS)
            window_fragment=bool(cover and full_sig==0)
            if cover:sample_cover_count+=1
            if window_fragment:summary["sample_12draw_fragment_eligible"]+=1
            first_fragment=bool(window_fragment and not old_eligible)
            if first_fragment:
                if heat_moves is None:
                    heat_moves=dict(con.execute("SELECT num,heat_move FROM ball_step WHERE draw_no=?",(no,)))
                summary["sample_heat_up_on_first_fragment"]+=sum(heat_moves[n]=="YUKSELIS" for n in family)
                summary["sample_heat_down_on_first_fragment"]+=sum(heat_moves[n]=="DUSUS" for n in family)
                path=_shape(family,sig)
                kind="FRAGMENT_FIRST" if not fragonce else "FRAGMENT_REAPPEARED"
                if not fragonce:summary["sample_current_first_fragment"]+=1
                else:summary["sample_fragment_reactivation"]+=1
                fragonce=True;fragcount+=1
                lastfrag=seq
                # Store at most EVENT_CAP per draw, selected by outcome-blind
                # pre-registered catalogue index (no favorable outcome filter).
                if len(interesting)<EVENT_CAP:
                    interesting.append((idx,family,path,kind,qlong,
                         state[8] if state[8] else 0,sig,lastfull))
            if hit==4:
                everfull=True;fullcount+=1;lastfull=seq
            if not everfull:summary["sample_current_no_4ever"]+=1
            if quiet>=3:summary["sample_silence_3plus"]+=1
            states[idx]=[sig,cover,everfull,fragonce,fragcount,fullcount,
                         quiet,qlong,lastfrag,lastfull,everseen|bits,full_sig]
        if sample_cover_count>2048:raise AssertionError("sample overflow")
        day_result={
            "seq":seq,"day":day,"pos":pos,"draw_no":no,
            "global_4_family_universe":UNIVERSE,
            "exact_two_1+3":exact2[0],"exact_two_2+2":exact2[1],
            "exact_two_3+1":exact2[2],
            "exact_three_1+1+2":exact3[0],
            "exact_three_1+2+1":exact3[1],
            "exact_three_2+1+1":exact3[2],
            "sample_current_no_4ever":summary["sample_current_no_4ever"],
            "sample_current_first_fragment":summary["sample_current_first_fragment"],
            "sample_fragment_reactivation":summary["sample_fragment_reactivation"],
            "sample_fragment_cover_now":sample_cover_count,
            "sample_silence_3plus":summary["sample_silence_3plus"],
            "sample_12draw_fragment_eligible":summary["sample_12draw_fragment_eligible"],
            "source_sample_size":SAMPLE,
            "bounded_event_examples":len(interesting),
            "sample_heat_up_on_first_fragment":summary["sample_heat_up_on_first_fragment"],
            "sample_heat_down_on_first_fragment":summary["sample_heat_down_on_first_fragment"],
            "warning":"Two/three step fragment counts exact; 12-step family life SAMPLE only."}
        for k in range(5):day_result[f"sample_{k}_4"]=summary[f"sample_{k}_4"]
        evidence=[]
        for idx,family,path,kind,quiet_before,prev_frag_seq,sig,lastfull in interesting:
            move,parents=_heat_directions(con,no,family)
            prior_draws=[r[0] for r in con.execute(
                "SELECT draw_no FROM draw_ledger WHERE seq BETWEEN ? AND ? AND day=? ORDER BY seq",
                (max(1,seq-LOOKBACK+1),seq,day))]
            family_txt="-".join(f"{n:02d}" for n in family)
            eventid=hashlib.sha256(f"V37C:{seq}:{idx}:{kind}".encode()).hexdigest()[:32]
            item={
                "event_id":eventid,"seq":seq,"draw_no":no,"day":day,"pos":pos,
                "family_numbers":family_txt,"event_type":kind,"path":path,
                "silence_before":quiet_before,"previous_fragment_seq":prev_frag_seq,
                "four_number_12bit_history":format(sig,"048b"),
                "previous_full4_seq":lastfull if lastfull else "",
                "full4_in_last12":0,
                "heat_directions":json.dumps(move,ensure_ascii=False),
                "linked_heat_event_ids":json.dumps(parents),
                "last_lookback_source_draws":json.dumps(prior_draws)
            }
            evidence.append((eventid,no,seq,idx,json.dumps(item,ensure_ascii=False)))
        con.execute("INSERT INTO v37c_step VALUES(?,?,?,?,?,?)",
                    (no,seq,day,pos,json.dumps(day_result,ensure_ascii=False,sort_keys=True),VERSION))
        con.executemany("INSERT INTO v37c_family_events VALUES(?,?,?,?,?)",evidence)
        processed+=1
        prev2=prev1;prev1=d;old=d
        if processed%75==0 or seq==base_count:
            blob=_encode_state(states)
            con.execute("INSERT OR REPLACE INTO v37c_checkpoint VALUES(1,?,?,?,?,?)",
                        (seq,no,CATALOG_SHA,VERSION,blob))
            con.commit()
            checkpoints+=1
            if progress:progress(seq,base_count,"V37C sessiz parçalı dörtlü yaşamı",day)
      info={
        "source_draws":base_count,
        "completed_draws":con.execute("SELECT COUNT(*) FROM v37c_step").fetchone()[0],
        "new_draws":processed,
        "catalogue_sample_size":SAMPLE,
        "catalogue_sha256":CATALOG_SHA,
        "global_4family_count":UNIVERSE,
        "sample_has_both_zero_and_full":True,
        "bounded_evidence_events":con.execute("SELECT COUNT(*) FROM v37c_family_events").fetchone()[0],
        "checkpoint_seq":con.execute("SELECT last_seq FROM v37c_checkpoint WHERE id=1").fetchone(),
        "checkpoints_during_run":checkpoints,
        "quality_warning":"Exact 2/3 draw formation counts; lifelong 2048 quartet random sample. Not exhaustive lifetime census; no future identity claim."
      }
      info["checkpoint_seq"]=info["checkpoint_seq"][0] if info["checkpoint_seq"] else 0
      return info
    finally:
      con.close()


def export(db_path,zip_path):
    con=sqlite3.connect(str(db_path))
    try:
      rows=[json.loads(r[0]) for r in con.execute(
           "SELECT payload FROM v37c_step ORDER BY seq")]
      halfway=len(rows)//2
      periods={}
      for key,records in (("ILK_YARI",rows[:halfway]),("SON_YARI",rows[halfway:])):
          if not records:continue
          totals={k:sum(int(r[k]) for r in records) for k in FIELDS
                  if (k.startswith("exact_") or k.startswith("sample_")) and k not in
                  ("sample_current_no_4ever","source_sample_size")}
          periods[key]={"draws":len(records),
                 "exact_two_three_counts":{k:v for k,v in totals.items() if k.startswith("exact_")},
                 "sample_event_counts":{k:v for k,v in totals.items() if k.startswith("sample_")},
                 "note":"Rolling-window overlapping records are NOT independent trials."}
      with zipfile.ZipFile(str(zip_path),"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        def csvout(name,fields,data):
            output=io.StringIO()
            wr=csv.DictWriter(output,fieldnames=fields,extrasaction="ignore",**CSV_OPTS)
            wr.writeheader();wr.writerows(data)
            z.writestr(name,output.getvalue().encode("utf-8-sig"))
        csvout("01_HER_CEKILIS_2_3_ADIM_PARCALE_FAMILY_TAM_SAYIM.csv",FIELDS,rows)
        events=[json.loads(p) for p, in con.execute(
             "SELECT payload FROM v37c_family_events ORDER BY seq,family_index")]
        csvout("02_2048_KAYITLI_DORTLU_HAYAT_ORNEKLERI.csv",EVENT_FIELDS,events)
        catalog_rows=[{"id":i+1,"family":"-".join(map(str,f)),"sample_sha":CATALOG_SHA}
                  for i,f in enumerate(CATALOG)]
        csvout("03_ONCEDEN_SECILEN_2048_TARAFSIZ_AILE.csv",
               ("id","family","sample_sha"),catalog_rows)
        z.writestr("04_ILK_VE_SON_YARI_CROSS_TEST.json",
                   json.dumps(periods,ensure_ascii=False,indent=2).encode("utf-8"))
        z.writestr("05_HESAP_TANIMLARI_VE_KAPSAM.txt",
         ("V37C PARCALI DORTLU HAYATLARI — ACIK KAPSAM\n"
          "===================================================\n"
          "TAM SAYIM: 20/80 gercek cekilislerden t ve t-1 kombinatorigiyle\n"
          "1+3 / 2+2 / 3+1. t,t-1,t-2 icin 1+1+2 / 1+2+1 / 2+1+1.\n"
          "Aday dortluler AYNI inceleme penceresinin herhangi bir gercek\n"
          "cekilisinde dordu birlikte cikan aileler HARIC. Bu iki/uc adim\n"
          "disindaki daha eski veya ileriki 4/4 olaylari bu tam sayimda\n"
          "ele alınmaz. Farkli pencerelerde ayni aile birden cok sayilabilir.\n"
          "ORN EKLEM: 80'den 4 = 1.581.580 farkli dortluden, resmi sonuclara\n"
          "hic bakilmadan rastgele secilmis 2.048 sabit aile; her cekilis\n"
          "0/1/2/3/4 gorunme, son 12 gercek cekilis birlesimi, 3+ sessizlik,\n"
          "birinci/tekrar parçalı kapama; tarihte henüz ayni cekiliste 4/4\n"
          "olmamış aileleri geleceği okumadan izler.\n"
          "Örnek ailelerin ayirt edici ayrintilari her adim ilk 12 olayla\n"
          "sinirlidir; tam örnek küme üye listesi 03 raporundadır.\n"
          "HIC 4/4 olmayan 1.58 milyon ailenin TAM OMURLUK defteri YOK.\n"
          "Dört sayılık ailenin parcalı gelmesi 4'ünün ayni cekiliste\n"
          "gelmesiyle karıştırılmaz. Bu bir RNG tohum algoritma klonu degil,\n"
          "gercek tarihlerin gözlemsel karakter karşılaştırmasıdır.\n").encode("utf-8-sig"))
        z.writestr("06_KAPSAM_HAZNE_META.json",json.dumps({
            "catalogue_size":SAMPLE,"catalogue_sha":CATALOG_SHA,
            "family_universe":UNIVERSE,"two_step_exact":True,
            "three_step_exact":True,"all_72day_4family_lifetime_exact":False,
            "lookback_draws":LOOKBACK,"sample_evidence_limit_per_draw":EVENT_CAP,
            "on_new_draw_incremental":True,
            "source":"same V37A SQLite shared draw ledger",
            "rng_hidden_state_recovered":False},ensure_ascii=False,indent=2).encode())
        blob_row=con.execute("SELECT state_zlib FROM v37c_checkpoint WHERE id=1").fetchone()
        latest=_decode_state(blob_row[0] if blob_row else None)
        family_lives=[]
        for i,(members,state) in enumerate(zip(CATALOG,latest)):
            sig,cover,everfull,fragonce,fragcount,fullcount,quiet,qlong,lastfrag,lastfull,everseen,full_sig=state
            family_lives.append({
                "sample_id":i+1,
                "family": "-".join(f"{n:02d}" for n in members),
                "fragment_ever":int(fragonce),"still_never_4of4":int(not everfull),
                "fragment_reactivations":max(0,fragcount-1),
                "fragment_events":fragcount,"same_draw_4of4_events":fullcount,
                "longest_all_members_absent":max(qlong,quiet),
                "current_all_members_absent":quiet,
                "last_fragment_seq":lastfrag if lastfrag else "",
                "last_full4_seq":lastfull if lastfull else "",
                "covered_in_latest_12":int(cover),
                "fragment_eligible_latest12":int(cover and full_sig==0),
                "ever_seen_member_count":everseen.bit_count()
            })
        csvout("07_2048_AILENIN_OMURLUK_KARAKTER_KARTI.csv",
            ("sample_id","family","fragment_ever","still_never_4of4",
             "fragment_reactivations","fragment_events","same_draw_4of4_events",
             "longest_all_members_absent","current_all_members_absent",
             "last_fragment_seq","last_full4_seq","covered_in_latest_12",
             "fragment_eligible_latest12",
             "ever_seen_member_count"),family_lives)
      with zipfile.ZipFile(str(zip_path)) as z:
          assert z.testzip() is None and len(z.namelist())==7
      return periods
    finally:
      con.close()
