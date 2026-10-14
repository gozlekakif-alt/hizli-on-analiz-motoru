# -*- coding: utf-8 -*-
"""Hizli On V10 — canlı aile / ritim / deneysel kupon.
V9 app.py ve veri.txt dosyalarini degistirmez.
Python 3.10+; streamlit, requests.
"""
import base64
import hmac
import csv
import io
import json
import re
from collections import defaultdict, Counter
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests
import streamlit as st
from v10_sira import (family_order_events, family_order_patterns,
                      family_order_matches, family_order_targets)
from v10_geliyorum import upcoming_alerts, replay_warning_day, MIN_PARTIAL
from v10_alti_ritim import gap_targets_today, walkforward_six_gap, six_gap_summary
from v11_arastirma import (run_study, live_preview, csv_export as v11_csv,
                           summary_text as v11_text, SIZES as V11_SIZES,
                           NUMBER_METHODS as V11_METHODS)
from v18_cift_havuz_app import render_v18
from v21_family_app import render_v21
from v22_family_app import render_v22
from v23_family_app import render_v23
from v24_family_app import render_v24
from v25_family_app import render_v25
from v26_family_app import render_v26
from v27_heat_app import render_v27
from v28_dijital_kaplan_app import render_v28
from v29_family_app import render_v29
from v30_bant_isi_yon_app import render_v30
from v31_ayna_simetri_app import render_v31
from v32_80_tamamlama_app import render_v32
from v17_karakter_app import render_v17
from v16_rng_salinim import analyze as v16_analyze
from v15_kupon_motoru import (fit_models as v15_fit,
                               build_six as v15_six,
                               retrospective_test as v15_backtest,
                               as_csv as v15_csv,
                               METHODS as V15_METHODS,
                               FAMILY_SIZES as V15_SIZES)
from v14_gecis_agi import (replay as v14_replay, preview as v14_preview,
                           csv_export as v14_csv, clock_slot as v14_clock)
from v13_havuz_koltuk import (trained_model as v13_train,
                             run_study as v13_study,
                             states_for_day as v13_states,
                             next_day_preview as v13_preview,
                             csv_export as v13_csv,
                             TYPES as V13_TYPES)
from v12_80_kule import (run_tower_study, audit_target as v12_audit_target,
                         target_tower_row as v12_target_row,
                         next_draw_tower as v12_next_tower,
                         csv_export as v12_csv, expected_repeat_per_target,
                         make_ready as v12_ready, SIZES as V12_SIZES,
                         METHODS as V12_METHODS)

REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
RAW = "https://raw.githubusercontent.com/" + REPO + "/main/"
STATE_PATH = "v10_canli_kayit.json"
TZ = ZoneInfo("Europe/Istanbul")

def now_tr():
    return datetime.now(TZ).replace(tzinfo=None)

def pos_of(dt):
    m = dt.hour * 60 + dt.minute
    if 2 <= m <= 62 and (m - 2) % 5 == 0:
        return 1 + (m - 2)//5
    if 422 <= m <= 1437 and (m - 422) % 5 == 0:
        return 14 + (m - 422)//5
    return None

def moment(day, pos):
    if not 1 <= pos <= 217:
        raise ValueError("Hedef cekilis sirasi 1-217 olmali.")
    m = 2 + 5*(pos - 1) if pos <= 13 else 422 + 5*(pos - 14)
    return datetime.combine(date.fromisoformat(day), time()) + timedelta(minutes=m)


def next_slot_after(last):
    """Return the next real scheduled slot, not the next wall-clock five minutes."""
    if not last:
        return None
    dt=datetime.fromisoformat(last["dt"])
    p=last["pos"]
    if p==217:
        candidate=moment((dt.date()+timedelta(days=1)).isoformat(),1)
    else:
        candidate=moment(last["day"],p+1)
    return {"no":last["no"]+1, "date":candidate.date().isoformat(),
            "time":candidate.strftime("%H:%M"),"dt":candidate}

def next_recorded_slot(history):
    if not history:
        return None
    return next_slot_after(max(history,key=lambda d:(d["dt"],d["no"])))

def next_paste_template(history):
    nxt=next_recorded_slot(history)
    if not nxt:
        return ""
    return f"Çekiliş no:{nxt['no']}\n{nxt['dt']:%d.%m.%Y-%H:%M}\n"

def normalize_numbers(values):
    arr = [int(x) for x in values]
    if len(arr) != 20 or len(set(arr)) != 20 or any(n < 1 or n > 80 for n in arr):
        raise ValueError("1-80 arasinda 20 benzersiz sayi gerekli.")
    return sorted(arr)

def make_draw(num, dt, nums):
    if not isinstance(dt, datetime):
        dt = datetime.fromisoformat(dt)
    pos = pos_of(dt)
    if pos is None:
        raise ValueError("Takvim disi saat. 00:02-01:02 veya 07:02-23:57, 5 dk.")
    return {"no":int(num), "dt":dt.isoformat(timespec="minutes"),
            "day":dt.date().isoformat(), "pos":pos, "nums":normalize_numbers(nums)}

def parse_draw_line(line):
    p = line.strip().split(";")
    if len(p) != 3 or not p[0].strip().isdigit():
        return None
    dt = datetime.strptime(p[1].strip(), "%d.%m.%Y %H:%M")
    return make_draw(p[0], dt, p[2].split(","))


def parse_pasted_draws(raw):
    """Read official pasted result blocks and semicolon data lines."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    results, problems = [], []
    for line in text.splitlines():
        if re.match(r"^\s*\d+\s*;", line):
            try:
                d = parse_draw_line(line)
                if d:
                    results.append(d)
            except (ValueError, TypeError) as exc:
                problems.append(str(exc))
    pattern = re.compile(r"(?im)^\s*#*\s*Çekiliş\s*no\s*:\s*#*\s*(\d{4,8})\s*$")
    found = list(pattern.finditer(text))
    for i, match in enumerate(found):
        block = text[match.end():found[i + 1].start() if i + 1 < len(found) else len(text)]
        stamp = re.search(r"(?<!\d)(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}:\d{2})\b", block)
        if not stamp:
            problems.append("#" + match.group(1) + ": tarih/saat bulunamadı")
            continue
        rest = block[stamp.end():]
        rest = re.split(r"(?im)^\s*(?:\[\s*)?Detaylar\b|^\s*https?://", rest, maxsplit=1)[0]
        nums = []
        for line in rest.splitlines():
            v = line.strip()
            if re.fullmatch(r"\d{1,2}(?:\s*[,;\s]\s*\d{1,2})*", v):
                nums.extend(int(x) for x in re.findall(r"\d{1,2}", v))
        try:
            dt = datetime.strptime(stamp.group(1) + " " + stamp.group(2), "%d.%m.%Y %H:%M")
            results.append(make_draw(match.group(1), dt, nums))
        except (ValueError, TypeError) as exc:
            problems.append("#" + match.group(1) + ": " + str(exc))
    if not results and not problems:
        problems.append("Çekiliş başlığı bulunamadı: 'Çekiliş no:61629' veya noktalı veri satırı bekleniyor.")
    return results, problems


def filter_new_draws(records, existing):
    """Validate a pasted batch and exclude exact repeats without hiding conflicts."""
    by_id={d["no"]:d for d in existing}
    by_slot={(d["day"],d["pos"]):d for d in existing}
    accepted, repeats, errors=[],0,[]
    for entry in records:
        try:
            d=make_draw(entry["no"],entry["dt"],entry["nums"])
            prior_id=by_id.get(d["no"])
            prior_slot=by_slot.get((d["day"],d["pos"]))
            for prior in (prior_id,prior_slot):
                if prior is None:
                    continue
                if prior["no"]==d["no"] and prior["dt"]==d["dt"] and prior["nums"]==d["nums"]:
                    repeats+=1
                else:
                    errors.append(f"#{d['no']}: numara, tarih/saat veya 20 sayıda çakışma var. Kayıt reddedildi.")
                break
            else:
                accepted.append(d)
                by_id[d["no"]]=d
                by_slot[(d["day"],d["pos"])]=d
        except (ValueError,KeyError,TypeError) as exc:
            errors.append("Geçersiz çekiliş: "+str(exc))
    return accepted,repeats,errors

def parse_history(raw):
    seen_no, seen_time, draws, errors = set(), set(), [], 0
    for line in raw.splitlines():
        if not re.match(r"^\s*\d+\s*;", line):
            continue
        try:
            d = parse_draw_line(line)
            if not d or d["no"] in seen_no or d["dt"] in seen_time:
                raise ValueError("Mukerrer kayit")
            seen_no.add(d["no"])
            seen_time.add(d["dt"])
            draws.append(d)
        except (ValueError, TypeError):
            errors += 1
    draws.sort(key=lambda d:d["dt"])
    return draws, errors


def merge_draws_into_txt(existing_text, additions):
    """Keep every original byte of veri.txt, append only verified, new draw lines.

    Reject conflicting draw number or date/slot, rather than changing history.
    """
    history, _=parse_history(existing_text)
    ids={d["no"]:d for d in history}
    slots={(d["day"],d["pos"]):d for d in history}
    seen_ids={}
    seen_slots={}
    new=[]
    skipped=0
    for d in sorted(additions,key=lambda row:(row["dt"],row["no"])):
        checked=make_draw(d["no"],d["dt"],d["nums"])
        ident=checked["no"]
        key=(checked["day"],checked["pos"])
        current=ids.get(ident) or slots.get(key) or seen_ids.get(ident) or seen_slots.get(key)
        if current:
            if current["no"] != ident or current["dt"] != checked["dt"] or current["nums"] != checked["nums"]:
                raise ValueError(f"Çelişen çekiliş kaydı: #{ident} / {checked['day']} sıra {checked['pos']}. veri.txt değiştirilmedi.")
            skipped+=1
            continue
        seen_ids[ident]=checked
        seen_slots[key]=checked
        new.append(checked)
    if not new:
        return existing_text, 0, skipped
    # Preserve existing headers and ordering; append official semicolon format.
    joiner="" if not existing_text or existing_text.endswith("\n") else "\n"
    lines=[f"{d['no']};{datetime.fromisoformat(d['dt']):%d.%m.%Y %H:%M};{','.join(map(str,d['nums']))}"
           for d in new]
    return existing_text+joiner+"\n".join(lines)+"\n",len(new),skipped

def draw_confirmation_signature(record):
    """Stable signature for a complete persisted draw, not just its number."""
    return record["dt"]+"|"+",".join(map(str,record["nums"]))


def live_record_status(live_records, history_records, confirmed=None):
    """Distinguish unsaved, exact matching and conflicting live records.

    A GitHub successful PUT confirms the pushed content even when subsequent
    raw/API reads return a temporarily stale file revision.
    """
    confirmed = confirmed or {}
    main = {d["no"]: d for d in history_records}
    pending, conflicts = [], []
    for d in live_records:
        previous=main.get(d["no"])
        if previous is not None:
            if draw_confirmation_signature(previous)!=draw_confirmation_signature(d):
                conflicts.append(d)
        elif confirmed.get(str(d["no"]))!=draw_confirmation_signature(d):
            pending.append(d)
    return pending, conflicts


def remember_github_confirmation(records):
    """Keep GitHub's successful write/exists acknowledgment in this session."""
    prior=st.session_state.setdefault("v10_git_confirmed", {})
    for d in records:
        prior[str(d["no"])]=draw_confirmation_signature(d)


def persist_to_github_veri_txt(additions):
    """Optimistic GitHub contents write, including >1 MB source via Git blob API."""
    tok=secret_token()
    if not tok:
        return False,0,"GitHub token tanımlı değil; veri.txt'ye kalıcı kayıt yapılamadı."
    if not secret_admin_pin():
        return False,0,"Streamlit Secrets'te V10_ADMIN_PIN yok; güvenlik nedeniyle yazma kapalı."
    if not st.session_state.get("v10_admin_unlocked",False):
        return False,0,"GitHub kalıcı kayıt kilitli. Yedek & Kayıt sekmesinde yönetici PIN'ini gir."
    if not additions:
        return True,0,"Yeni kayıt yok."
    url=f"https://api.github.com/repos/{REPO}/contents/veri.txt"
    headers={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json",
             "X-GitHub-Api-Version":"2022-11-28"}
    try:
        for attempt in range(3):
            response=requests.get(url,headers=headers,params={"ref":"main"},timeout=40)
            response.raise_for_status()
            meta=response.json()
            sha=meta["sha"]
            if meta.get("encoding")=="base64" and meta.get("content"):
                body=base64.b64decode(meta["content"]).decode("utf-8-sig")
            else:
                # The GitHub Contents endpoint omits file content above 1 MB.
                blob=requests.get(f"https://api.github.com/repos/{REPO}/git/blobs/{sha}",
                                  headers=headers,timeout=60)
                blob.raise_for_status()
                b=blob.json()
                if b.get("encoding")!="base64":
                    raise ValueError("GitHub büyük veri.txt içeriğini okuyamadı.")
                body=base64.b64decode(b["content"]).decode("utf-8-sig")
            merged,added,already=merge_draws_into_txt(body,additions)
            if added==0:
                remember_github_confirmation(additions)
                github_text.clear()
                return True,0,f"Yeni çekiliş yok; {already} tanesi zaten veri.txt içinde."
            payload={"message":f"V10: veri.txt'ye {added} yeni cekilis ekle",
                     "branch":"main","sha":sha,
                     "content":base64.b64encode(merged.encode("utf-8")).decode("ascii")}
            put=requests.put(url,headers=headers,json=payload,timeout=90)
            if put.status_code in (409,422) and attempt<2:
                continue
            put.raise_for_status()
            remember_github_confirmation(additions)
            github_text.clear()
            return True,added,f"GitHub veri.txt kalıcı kayıt: {added} yeni çekiliş; {already} zaten mevcuttu."
        return False,0,"GitHub'da eşzamanlı güncelleme var; tekrar dene."
    except Exception as exc:
        return False,0,f"GitHub veri.txt kaydı başarısız: {exc}"

def load_family_csv(content):
    records = {}
    for row in csv.DictReader(io.StringIO(content), delimiter=";"):
        label = row.get("Aile", "").strip()
        try:
            nums = tuple(int(x) for x in label.split("-"))
            k = int(row.get("Boyut", 0))
            if not (5 <= k <= 10 and len(nums) == k and
                    len(set(nums)) == k and all(1 <= x <= 80 for x in nums)):
                continue
            records[label] = {"nums":nums,"mask":sum(1 << (x-1) for x in nums),
                              "k":k, "day_count":int(row.get("Aktif_Gun", 0)),
                              "source":row.get("Kaynak","V9")}
        except (ValueError, TypeError):
            pass
    return records

@st.cache_data(ttl=300, show_spinner=False)
def github_text(path):
    res = requests.get(RAW+path, timeout=45)
    res.raise_for_status()
    return res.content.decode("utf-8-sig")

def latest_main_history():
    """Fresh read from GitHub REST, bypassing cached raw CDN snapshot.

    Only called if the live session appears to have unsaved records.
    Large veri.txt files require the Git blob endpoint.
    """
    url=f"https://api.github.com/repos/{REPO}/contents/veri.txt"
    headers={"Accept":"application/vnd.github+json",
             "X-GitHub-Api-Version":"2022-11-28"}
    response=requests.get(url,headers=headers,params={"ref":"main"},timeout=40)
    response.raise_for_status()
    meta=response.json()
    if meta.get("encoding")=="base64" and meta.get("content"):
        raw=base64.b64decode(meta["content"]).decode("utf-8-sig")
    else:
        blob=requests.get(
            f"https://api.github.com/repos/{REPO}/git/blobs/{meta['sha']}",
            headers=headers,timeout=60)
        blob.raise_for_status()
        data=blob.json()
        if data.get("encoding")!="base64" or not data.get("content"):
            raise ValueError("GitHub kaydı doğrulanamadı.")
        raw=base64.b64decode(data["content"]).decode("utf-8-sig")
    return parse_history(raw)


@st.cache_data(ttl=600, show_spinner=False)
def train_profiles(history_json, labels_json):
    """Yalniz HEDEF GUNDEN ONCEKI cekilislerden model olusturulur."""
    past = json.loads(history_json)
    labels = json.loads(labels_json)
    bitsets = [0] * 80
    for idx,d in enumerate(past):
        for n in d["nums"]:
            bitsets[n-1] |= 1 << idx
    profiles = {}
    for label in labels:
        try:
            ns = [int(x) for x in label.split("-")]
            indices = bitsets[ns[0]-1]
            for n in ns[1:]:
                indices &= bitsets[n-1]
            byday = defaultdict(list)
            while indices:
                bit = indices & -indices
                i = bit.bit_length() - 1
                d = past[i]
                byday[d["day"]].append(d["pos"])
                indices ^= bit
            pair_days, first_days, triple_days, quad_days = defaultdict(set),defaultdict(set),defaultdict(set),defaultdict(set)
            hourly_days = defaultdict(set)
            for day, ps in byday.items():
                ps.sort()
                for position in ps:
                    hourly_days[moment(day, position).hour].add(day)
                if len(ps) >= 2:
                    first_days[ps[1]-ps[0]].add(day)
                for i in range(len(ps)):
                    for j in range(i+1,len(ps)):
                        pair_days[ps[j]-ps[i]].add(day)
                for i in range(len(ps)-2):
                    triple_days[(ps[i+1]-ps[i],ps[i+2]-ps[i+1])].add(day)
                for i in range(len(ps)-3):
                    quad_days[tuple(ps[i+t+1]-ps[i+t] for t in range(3))].add(day)
            dates = sorted(byday)
            profiles[label] = {
                "days":dates,
                "total_hits":sum(map(len,byday.values())),
                "pair":{gap:len(ds) for gap,ds in pair_days.items()},
                "first":{gap:len(ds) for gap,ds in first_days.items()},
                "triple":{pat:len(ds) for pat,ds in triple_days.items()},
                "quad":{pat:len(ds) for pat,ds in quad_days.items()},
                "hour_days":{hour:len(ds) for hour,ds in hourly_days.items()},
            }
        except (ValueError, IndexError):
            continue
    return profiles


def historical_hour_support(profiles, label, target_pos, minimum_days=2):
    """Prior-day calendar support for the *same clock hour* as a target slot.

    The supplied profiles must be trained only on draws before target day.
    'Supported' is an additional conservative filter, not a forecast.
    """
    target_hour=moment("2026-01-01",target_pos).hour
    count=int(profiles.get(label,{}).get("hour_days",{}).get(target_hour,0))
    return {"hour":target_hour,"days":count,
            "required":minimum_days,"ok":count>=minimum_days}


def rhythm_ticket_gate(profiles, label, target_pos, fire_families, minimum_days=2):
    """Only FIRE-tagged coupons need independent historical hour support."""
    info=historical_hour_support(profiles,label,target_pos,minimum_days)
    info["flame"]=label in fire_families
    info["coupon_ok"]=not info["flame"] or info["ok"]
    return info


def gap_rhythm(gaps):
    """Describe observed chronological appearance gaps, never a prediction."""
    if not gaps:
        return "TEK GÖRÜNÜŞ"
    if len(gaps)==1:
        return f"İKİLİ +{gaps[0]}"
    if len(set(gaps))==1:
        return f"SABİT +{gaps[0]}"
    if all(a<b for a,b in zip(gaps,gaps[1:])):
        return "ARTAN " + "/".join("+"+str(g) for g in gaps)
    if all(a>b for a,b in zip(gaps,gaps[1:])):
        return "AZALAN " + "/".join("+"+str(g) for g in gaps)
    return "DEĞİŞKEN " + "/".join("+"+str(g) for g in gaps)

def gap_class(gaps):
    if not gaps:
        return "Tek"
    if len(gaps)==1:
        return "İkili"
    if len(set(gaps))==1:
        return "Sabit"
    if all(a<b for a,b in zip(gaps,gaps[1:])):
        return "Artan"
    if all(a>b for a,b in zip(gaps,gaps[1:])):
        return "Azalan"
    return "Değişken"

def family_rhythm_report(draws, families, dayhits, target_day):
    """Exact-family appearances in the loaded historical corpus; no future rows.
    Return a per-family summary and all matching timestamped occurrences.
    """
    labels=sorted(dayhits)
    selected={label:families[label]["mask"] for label in labels}
    index=defaultdict(list)
    details=[]
    for d in draws:
        if d["day"]>target_day:
            continue
        mask=sum(1 << (n-1) for n in d["nums"])
        for label,subset in selected.items():
            if mask & subset == subset:
                index[label].append(d)
                details.append({"Aile":label,"Boyut":families[label]["k"],
                                "Tarih":d["day"],"Çekiliş":d["no"],
                                "Saat":d["dt"][11:16],"Sıra":d["pos"],
                                "Dönem":"Bugün" if d["day"]==target_day else "Geçmiş"})
    summaries=[]
    for label in labels:
        events=index[label]
        prior=[d for d in events if d["day"]<target_day]
        today=sorted([d for d in events if d["day"]==target_day],key=lambda d:d["pos"])
        prior_days=sorted({d["day"] for d in prior})
        all_days=sorted({d["day"] for d in events})
        positions=[d["pos"] for d in today]
        intra=[b-a for a,b in zip(positions,positions[1:])]
        day_diffs=[(date.fromisoformat(b)-date.fromisoformat(a)).days
                   for a,b in zip(all_days,all_days[1:])]
        prior_counts=Counter(d["day"] for d in prior)
        summaries.append({
            "Aile":label,"Boyut":families[label]["k"],
            "Durum":"İLK KEZ (veride)" if not prior else "GEÇMİŞTEN GELDİ",
            "Bugün kaç kez":len(today),
            "Bugün çekilişler":", ".join(f"#{d['no']} {d['dt'][11:16]}" for d in today),
            "Bugün ritim":gap_rhythm(intra),
            "Ritim türü":gap_class(intra),
            "Geçmiş kaç gün":len(prior_days),
            "Geçmiş toplam":len(prior),
            "Geçmişte 3+ gün":sum(v>=3 for v in prior_counts.values()),
            "Geçmişte 4+ gün":sum(v>=4 for v in prior_counts.values()),
            "Günler arası":gap_rhythm(day_diffs),
            "+2 gün":sum(x==2 for x in day_diffs),
            "+5 gün":sum(x==5 for x in day_diffs),
            "En son önce":f"#{prior[-1]['no']} {prior[-1]['day']} {prior[-1]['dt'][11:16]}" if prior else "YOK",
            "Geçmiş görünüşler":", ".join(
                f"#{d['no']} {d['day']} {d['dt'][11:16]}" for d in prior[-30:]),
            "Tüm tarih/gün":", ".join(all_days)})
    summaries.sort(key=lambda x:(-x["Bugün kaç kez"],-x["Geçmişte 3+ gün"],
                                 -x["Boyut"],x["Aile"]))
    return summaries,details

def repeat_gap_targets(dayhits, profiles, families, day, now, observed_positions,
                       minimum_days=2, latest_known=None):
    """Live targets based on *prior-day* first, triple or quad chronological gaps.
    Stage 1->2: historical first gaps; 2->3: exact (gap1,gap2);
    3->4: exact (gap1,gap2,gap3). Never use future day draws.
    """
    targets=[]
    for label,recs in dayhits.items():
        ps=sorted({d["pos"] for d in recs})
        n=len(ps)
        if n not in (1,2,3):
            continue
        profile=profiles.get(label,{})
        if n==1:
            patterns=[(int(g),int(cnt),"1→2") for g,cnt in profile.get("first",{}).items()]
        elif n==2:
            patterns=[(int(pat[1]),int(cnt),"2→3") for pat,cnt in profile.get("triple",{}).items()
                      if pat[0]==ps[1]-ps[0]]
        else:
            patterns=[(int(pat[2]),int(cnt),"3→4") for pat,cnt in profile.get("quad",{}).items()
                      if tuple(pat[:2])==(ps[1]-ps[0],ps[2]-ps[1])]
        for delta,support,stage in patterns:
            if support<minimum_days:
                continue
            target_pos=ps[-1]+delta
            if delta<=0 or target_pos>217 or target_pos in observed_positions:
                continue
            when=moment(day,target_pos)
            if when<=now:
                continue
            seq=[b-a for a,b in zip(ps,ps[1:])]+[delta]
            kind=gap_rhythm(seq)
            estimated_no=None
            if latest_known and target_pos>latest_known["pos"]:
                estimated_no=latest_known["no"]+(target_pos-latest_known["pos"])
            targets.append({
                "label":label,"size":families[label]["k"],"stage":stage,
                "level":n+1,"gap":delta,"support":support,
                "kind":kind,"pattern":"/".join("+"+str(g) for g in seq),
                "pos":target_pos,"day":day,"time":when.strftime("%H:%M"),
                "estimated_no":estimated_no,
                "trigger_no":max(recs,key=lambda d:d["pos"])["no"],
                "moment":when.isoformat(timespec="minutes")
            })
    targets.sort(key=lambda x:(x["pos"],-x["support"],-x["size"],x["label"]))
    unique={}
    for item in targets:
        key=(item["label"],item["pos"],item["stage"])
        if key not in unique:
            unique[key]=item
    return list(unique.values())

def day_signal_replay(dayhits, profiles, families, target_day, day_draws,
                      minimum_days=2):
    """Recreate historical targets only after each observed 1st/2nd/3rd family
    appearance, without using later outcomes to form a candidate.

    The previous-day training profiles are supplied by caller. Results are
    evaluated separately against already recorded target slots, if available.
    """
    actual_by_pos={d["pos"]:d for d in day_draws}
    rows={}
    for label, observed in dayhits.items():
        appearances=sorted(observed,key=lambda d:d["pos"])
        for i in range(min(3,len(appearances))):
            known=appearances[:i+1]
            trigger=known[-1]
            candidates=repeat_gap_targets(
                {label:known}, profiles, families, target_day,
                moment(target_day,trigger["pos"]),
                {d["pos"] for d in known},
                minimum_days=minimum_days,
                latest_known=trigger
            )
            for signal in candidates:
                result=actual_by_pos.get(signal["pos"])
                own=set(families[label]["nums"])
                matched=sorted(own.intersection(result["nums"])) if result else []
                status=("Bekliyor (çekiliş kayıtta yok)" if result is None
                        else "TAM" if len(matched)==families[label]["k"]
                        else "Tam olmadı")
                key=(label,signal["stage"],signal["pos"])
                rows[key]={
                    "Aile":label,"Boyut":families[label]["k"],
                    "Aşama":signal["stage"],"Ritim":signal["pattern"],
                    "Ritim türü":signal["kind"],"Destek gün":signal["support"],
                    "Tetikleyen":f"#{trigger['no']} {trigger['dt'][11:16]}",
                    "Hedef sıra":signal["pos"],"Hedef saat":signal["time"],
                    "Hedef no":f"#{result['no']}" if result else "Kayıt yok",
                    "Sonuç":status,"İsabet":(
                        f"{len(matched)}/{families[label]['k']}" if result else "—"
                    ),
                    "Tutan sayılar":"-".join(map(str,matched)) if result else "—",
                }
    return sorted(rows.values(),
                  key=lambda r:(r["Hedef sıra"],r["Boyut"],r["Aile"],r["Aşama"]))


def all_draws(history, live):
    by_no = {d["no"]:d for d in history}
    for d in live:
        by_no[d["no"]] = d
    output = sorted(by_no.values(),key=lambda d:d["dt"])
    # Ayni takvim yuvasinda farkli numara olmaz.
    return output

def active_signals(draws, families, profiles, target_day, current):
    todays = [d for d in draws if d["day"]==target_day and
              datetime.fromisoformat(d["dt"]) <= current]
    actual_pos = {d["pos"] for d in draws if d["day"]==target_day}
    dayhits = defaultdict(list)
    masks = [(d, sum(1 << (x-1) for x in d["nums"])) for d in todays]
    for d, mask in masks:
        for label, f in families.items():
            if mask & f["mask"] == f["mask"]:
                dayhits[label].append(d)
    found=[]
    for label, recs in dayhits.items():
        p = profiles.get(label, {})
        ps = sorted(d["pos"] for d in recs)
        n = len(ps)
        if n > 3:
            continue
        supported = p.get("first", {}) if n==1 else p.get("pair", {})
        for gap, count in supported.items():
            gap=int(gap)
            target=ps[-1]+gap
            if target>217 or target in actual_pos or count<2:
                continue
            t=moment(target_day,target)
            if t <= current:
                continue
            # 3. ve 4. hedef: onceki aralikla ayni ritme dayanan
            # bir varsayim. Ayrica 3lu/4lu tekrari varsa bunu belirt.
            if n>=2 and ps[-1]-ps[-2]!=gap:
                continue
            confirmed = False
            if n==2:
                confirmed = p.get("triple",{}).get((gap,gap),0)>=2
            elif n==3:
                confirmed = p.get("quad",{}).get((gap,gap,gap),0)>=2
            kind = ("Tekrarli ilk ikili aralik" if n==1
                    else "Uc/dortlu dogrulanmis ritim" if confirmed
                    else "Deneysel ritim uzatmasi")
            found.append({"label":label,"size":families[label]["k"],"support":count,
                          "kind":kind,"level":n+1,"gap":gap,"pos":target,
                          "day":target_day,"time":t.strftime("%H:%M"),
                          "trigger_no":recs[-1]["no"],
                          "trigger_pos":ps[-1],"moment":t.isoformat(timespec="minutes")})
    found.sort(key=lambda x:(x["pos"],-x["size"],-x["support"],x["label"]))
    return found, dayhits

def cross_day_rhythm_report(profiles, families):
    """Earlier-day-only equal calendar-day interval streaks.

    A streak must contain >=3 distinct observed days (two identical gaps).
    This is a descriptive flag, not evidence of predictive superiority.
    """
    rows = []
    for label, profile in profiles.items():
        if label not in families:
            continue
        dates = sorted({date.fromisoformat(d) for d in profile.get("days", [])})
        if len(dates) < 3:
            continue
        gaps = [(b-a).days for a,b in zip(dates, dates[1:])]
        i = 0
        while i < len(gaps):
            j = i+1
            while j < len(gaps) and gaps[j] == gaps[i]:
                j += 1
            if j-i >= 2:
                end = dates[j]
                rows.append({
                    "Aile":label, "Boyut":families[label]["k"],
                    "Ritim":f"+{gaps[i]} gün",
                    "Ritimli gün":j-i+1, "Aynı aralık":j-i,
                    "Başlangıç":dates[i].isoformat(),
                    "Son gün":end.isoformat(),
                    "Devam etse tarih":(end+timedelta(days=gaps[i])).isoformat(),
                    "Tarih örnekleri":", ".join(d.isoformat() for d in dates[i:j+1]),
                })
            i = j
    rows.sort(key=lambda r:(-r["Aynı aralık"],-r["Ritimli gün"],
                            -r["Boyut"],r["Son gün"],r["Aile"]))
    return rows


def cross_day_intraday_report(profiles, families, minimum_days=2):
    """Observed same intra-day full-family gap patterns across past dates."""
    rows=[]
    levels=(("1→2","first"),("2→3","triple"),("3→4","quad"))
    for label,p in profiles.items():
        if label not in families:
            continue
        for stage,key in levels:
            for pattern,days in p.get(key,{}).items():
                if int(days)<minimum_days:
                    continue
                gaps=(pattern,) if isinstance(pattern,int) else pattern
                rows.append({
                    "Aile":label, "Boyut":families[label]["k"],
                    "Aşama":stage,
                    "Çekiliş aralığı":", ".join("+"+str(g) for g in gaps),
                    "Destek ayrı gün":int(days),
                })
    rows.sort(key=lambda r:(-r["Destek ayrı gün"],-r["Boyut"],
                            r["Aşama"],r["Aile"]))
    return rows


def cross_day_repeat_families(profiles, families, minimum_days=2):
    """Families repeating their own intra-day first/3rd/4th pattern
    on >=minimum_days distinct previous days."""
    found=set()
    for label,p in profiles.items():
        if label not in families:
            continue
        if any(int(v)>=minimum_days for key in ("first","triple","quad")
               for v in p.get(key,{}).values()):
            found.add(label)
    return found


def daily_chains(profiles, families, target_day):
    today=date.fromisoformat(target_day)
    result=[]
    for label,p in profiles.items():
        if families.get(label,{}).get("k")!=10:
            continue
        ds=set(date.fromisoformat(d) for d in p["days"])
        if len(ds)<2:
            continue
        for g in (2,5,7,14):
            for last in ds:
                if last - timedelta(days=g) not in ds:
                    continue
                target=last+timedelta(days=g)
                if target < today or target> today+timedelta(days=14):
                    continue
                chain=2
                back=last-timedelta(days=g)
                while back-timedelta(days=g) in ds:
                    back-=timedelta(days=g)
                    chain+=1
                result.append({"Aile":label,"Ritim":f"+{g} gun",
                               "Ardisik gun":chain,"Son tarih":str(last),
                               "Hedef gun":str(target),"Hedef saat":"Bilinmiyor"})
    result.sort(key=lambda d:(d["Hedef_gun"] if "Hedef_gun" in d else d["Hedef gun"],-d["Ardisik gun"]))
    # Uzun aile listelerinde ayni hedefi tekrarlama.
    unique={}
    for r in result:
        key=(r["Aile"],r["Hedef gun"],r["Ritim"])
        if key not in unique or r["Ardisik gun"]>unique[key]["Ardisik gun"]:
            unique[key]=r
    return list(unique.values())

def make_ticket(signal, draws, size=None):
    family = [int(x) for x in signal["label"].split("-")]
    size = len(family) if size is None else int(size)
    if size < len(family) or size > 10:
        raise ValueError("Kupon boyutu aileden küçük veya 10'dan büyük olamaz.")
    # Tamamlama rakamlari HEDEF ANINDAN once bilinen cekilisler.
    before=[d for d in draws if d["dt"]<signal["moment"]][-48:]
    counter=Counter(n for d in before for n in d["nums"] if n not in family)
    result=family[:]
    for n,_ in sorted(counter.items(),key=lambda t:(-t[1],t[0])):
        if len(result)>=size:break
        if n not in result:result.append(n)
    for n in range(1,81):
        if len(result)>=size:break
        if n not in result:result.append(n)
    return sorted(result[:size])

def secret_token():
    try:
        for key in ("GITHUB_TOKEN","GH_TOKEN","github_token"):
            if st.secrets.get(key):
                return str(st.secrets[key])
        if "github" in st.secrets and st.secrets["github"].get("token"):
            return str(st.secrets["github"]["token"])
    except Exception:
        pass
    return None

def api_state(token, write=None):
    url=f"https://api.github.com/repos/{REPO}/contents/{STATE_PATH}"
    headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"}
    res=requests.get(url,headers=headers,params={"ref":"main"},timeout=20)
    if res.status_code not in (200,404):
        res.raise_for_status()
    if write is None:
        if res.status_code==404:return None
        obj=res.json()
        return json.loads(base64.b64decode(obj["content"]))
    payload={"message":"V10: canli cekilis ve kupon kaydi",
             "branch":"main",
             "content":base64.b64encode(json.dumps(write,ensure_ascii=False).encode("utf8")).decode("ascii")}
    if res.status_code==200:
        payload["sha"]=res.json()["sha"]
    update=requests.put(url,headers=headers,json=payload,timeout=35)
    update.raise_for_status()
    return True

def validate_saved(value):
    if not isinstance(value,dict):raise ValueError("Yedek formati hatali")
    live=[]
    for d in value.get("live",[]):
        live.append(make_draw(d["no"],d["dt"],d["nums"]))
    tickets=value.get("tickets",[])
    if not isinstance(tickets,list):raise ValueError("Kuponlar listesi gecersiz")
    return {"live":live,"tickets":tickets}

def secret_admin_pin():
    try:
        return str(st.secrets.get("V10_ADMIN_PIN", ""))
    except Exception:
        return ""

def auto_save():
    tok=secret_token()
    if not tok:
        return "GitHub token ayarli degil; yerel oturum + JSON yedegi kullanin."
    if not secret_admin_pin():
        return "Güvenlik: Streamlit Secrets'e V10_ADMIN_PIN eklenmeden GitHub yazma kapali."
    if not st.session_state.get("v10_admin_unlocked", False):
        return "GitHub yazma kilitli. Yedek & Kayit sekmesinden PIN ile acin."
    try:
        api_state(tok, {"live":st.session_state.v10_live,
                        "tickets":st.session_state.v10_tickets})
        return "GitHub kalici kaydi guncellendi."
    except Exception as exc:
        return "GitHub kaydi basarisiz: "+str(exc)

def result_rows(tickets, draws):
    actual={(d["day"],d["pos"]):d for d in draws}
    rows=[]
    for t in tickets:
        d=actual.get((t["day"],t["pos"]))
        common=sorted(set(t["numbers"])&set(d["nums"])) if d else []
        k = len(t["numbers"])
        rows.append({"Hedef gun":t["day"],"Saat":t["time"],"Aile":t["family"],
                     "Boyut":k,
                     "Kupon":"-".join(map(str,t["numbers"])),
                     "Sonuc":f"{len(common)}/{k}" if d else "Bekleniyor",
                     "Isabet":len(common) if d else None,
                     "Tutan":"-".join(map(str,common)),
                     "Cekilis_no":d["no"] if d else "",
                     "Sinyal":t["kind"]})
    return rows


@st.cache_data(ttl=300, show_spinner=False)
def cached_family_order_report(draws_json, labels_json, target_day, gap, support):
    """Read-only historical chains cached by complete data/label inputs."""
    events = family_order_events(json.loads(draws_json), json.loads(labels_json), target_day)
    pairs, triples = family_order_patterns(events, target_day, gap, support)
    return events, pairs, triples


def family_order_csv(rows):
    if not rows:
        return ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff" + out.getvalue()


st.set_page_config(page_title="Hizli On V10 Canli Kupon Motoru",page_icon="🎯",
                   layout="wide",initial_sidebar_state="collapsed")
st.title("🎯 Hızlı On V10 — Canlı Ritim ve Kupon")
st.caption("5-10'lu aileler • hedef tarih/saat • canlı çekiliş • deneysel kupon • isabet")
st.warning("Geçmişteki tekrarlar gelecekteki sonucu garanti etmez. Kuponlar deneysel izleme içindir.")

if "v10_live" not in st.session_state:
    st.session_state.v10_live=[]
if "v10_tickets" not in st.session_state:
    st.session_state.v10_tickets=[]
if "v10_cloud_init" not in st.session_state:
    token=secret_token()
    if token:
        try:
            backup=api_state(token)
            if backup:
                b=validate_saved(backup)
                st.session_state.v10_live=b["live"]
                st.session_state.v10_tickets=b["tickets"]
        except Exception as exc:
            st.warning("GitHub kaydi alinamadi: "+str(exc))
    st.session_state.v10_cloud_init=True

historical=[];bad=0
try:
    raw=github_text("veri.txt")
    historical,bad=parse_history(raw)
except Exception as exc:
    st.error("GitHub veri.txt okunamadi. Asagidan TXT yukleyebilirsiniz. "+str(exc))

family_text=""
try:
    family_text=github_text("v10_aileler.csv")
except Exception as exc:
    st.warning("V10 aile havuzu GitHub'dan okunamadi: "+str(exc))

with st.expander("⚙️ Veri kaynağı ve aile havuzu",expanded=not historical or not family_text):
    upl=st.file_uploader("veri.txt dosyasi (GitHub erisimi yoksa)",type=["txt"],key="v10_txt")
    if upl:
        historical,bad=parse_history(upl.getvalue().decode("utf-8-sig"))
    upf=st.file_uploader("V9/V10 aile secim CSV (istege bagli)",type=["csv"],key="v10_csv")
    if upf:
        family_text=upf.getvalue().decode("utf-8-sig")
    if st.button("🔄 GitHub verilerini yenile"):
        github_text.clear()
        st.rerun()
    st.caption("Gecmis veri V9'da kalir. Bu sayfa agir aile kesfini yeniden calistirmaz.")
families=load_family_csv(family_text) if family_text else {}
if not families:
    st.error("Aile CSV bulunamadi; hedef tahmini icin v10_aileler.csv gerekli.")
# If the cached historical snapshot is older than this session's live backup,
# recheck the actual GitHub main branch BEFORE warning about missing records.
session_confirmed=st.session_state.get("v10_git_confirmed",{})
pending_draws,conflicted_live=live_record_status(
    st.session_state.v10_live, historical, session_confirmed)
verified_remote=False
if (pending_draws or conflicted_live) and not upl:
    try:
        fresh_history,fresh_bad=latest_main_history()
        verified_remote=True
        if len(fresh_history)>=len(historical):
            historical,bad=fresh_history,fresh_bad
            pending_draws,conflicted_live=live_record_status(
                st.session_state.v10_live,historical,session_confirmed)
    except Exception:
        # No proof of save: keep pending and warn so backups are retained.
        pass
draws=all_draws(historical,st.session_state.v10_live)
today=now_tr().date()
last_day=max([date.fromisoformat(x["day"]) for x in draws],default=today)
min_day=min([date.fromisoformat(x["day"]) for x in draws],default=today)

a,b,c=st.columns(3)
a.metric("Geçmiş çekiliş",len(historical))
b.metric("Aile havuzu",len(families))
c.metric("Canlı eklenen",len(st.session_state.v10_live))
if conflicted_live:
    st.error(f"⛔ {len(conflicted_live)} çekilişin numarası kayıtlı ama "
             "tarih/saat veya 20 sayısı GitHub'dakinden farklı. "
             "Bu kayıtlar otomatik değiştirilmedi; JSON yedeğinizi koruyun.")
if pending_draws:
    extra=(" Güncel GitHub dosyası kontrol edildi." if verified_remote
           else " GitHub'daki en son sürüm doğrulanamadı.")
    st.warning(f"⚠️ {len(pending_draws)} çekiliş için henüz GitHub kayıt onayı yok."
               +extra+" JSON yedeğini saklayıp kalıcı kayıt durumunu denetle.")
else:
    st.success(f"✅ Canlı kayıtlardan {len(st.session_state.v10_live)} çekiliş "
               "GitHub ana dosyasında veya başarılı kayıt onayında mevcut.")
if bad: st.caption(f"{bad} hatali/mukerrer satir gecmise alinmadi.")

tabs=st.tabs(["📥 Canlı giriş","🎯 Hedef & Kupon","🔁 Aile Sırası","📊 İsabet","💾 Yedek & Kayıt","🔮 Geliyorum","🔥 6’lı Ritim","🧠 V11 Araştırma","🗼 80 Sayı Kulesi","🌡️ V13 Hareketli Havuz","🔄 V14 Geçiş Ağı","🎟️ V15 Kupon Motoru","🎲 V16 RNG Salınımı","🧬 V17 Karakter Motoru","🌓 V18 Çift Havuz","🌳 V21 Aile Yaşam Döngüsü","🌱 V22 Aile Üçüncü Geliş","🔎 V23 Aile İlk İki Tam Çıkış","🌾 V24 Aile İkinci Çıkış Tahmini","🧬 V25 Aile DNA Kupon","🔀 V26 Karma Sıcak Soğuk","🌡️ V27 Koltuk Isı Hafızası","🐅 V28 Dijital Kaplan Döngü","🔍 V29 Kalış ve Hedef 20","🐅 V30 Bant Isı Yön","🪞 V31 Ayna Bant Kardeşliği","🔁 V32 80 Sayı Döngüsü"])

with tabs[0]:
    # PIN is required once per Streamlit session, not per submitted draw.
    # A public Streamlit app must not allow unauthenticated visitors to use its GitHub write token.
    if secret_token() and secret_admin_pin():
        if st.session_state.get("v10_admin_unlocked", False):
            st.success("🔓 GitHub yazma yetkisi açık. Yeni çekilişler kaydedilir; doğrulama durumu yukarıdadır.")
        else:
            st.warning("🔒 Kalıcı kayıt kilitli. Bu oturum için PIN'i bir kez aç; aksi halde çekiliş yalnız geçici eklenir.")
            pin_on_live=st.text_input("V10 yönetici PIN (yalnız bu oturum için)",type="password",key="v10_pin_live")
            if st.button("🔐 Otomatik kalıcı kaydı aç",key="v10_unlock_live"):
                if hmac.compare_digest(pin_on_live,secret_admin_pin()):
                    st.session_state.v10_admin_unlocked=True
                    if st.session_state.v10_live:
                        ok,_,m=persist_to_github_veri_txt(st.session_state.v10_live)
                        st.session_state.v10_last_paste={
                            "added":0,"repeats":0,"issues":[],
                            "saved":m if ok else "Kalıcı kayıt başarısız: "+m
                        }
                        if ok:
                            auto_save()
                    st.rerun()
                else:
                    st.error("PIN yanlış; GitHub'a yazma izni açılmadı.")
    else:
        st.error("GitHub otomatik kayıt etkin değil: Streamlit Secrets'te GITHUB_TOKEN ve V10_ADMIN_PIN gerekli.")
    st.subheader("📋 Çekiliş sonucunu aynen yapıştır")
    st.caption("Başlık, tarih-saat ve alt alta 20 sayı. Birden fazla çekilişi de aynı kutuya yapıştırabilirsin.")
    next_info=next_recorded_slot(draws)
    if next_info:
        st.info(f"📅 Son kayıtlı çekilişten sonraki: #{next_info['no']} • {next_info['dt']:%d.%m.%Y} • saat {next_info['time']}")
        if next_info["dt"] < now_tr()-timedelta(minutes=5):
            st.caption("Bu tarih geçmişte görünüyor: ana veri.txt henüz güncel değil. Sonuçları geriye dönük sırayla yapıştırabilirsin.")
    # Version migration: clear legacy auto-inserted two-line template once.
    # Do not clear a user's partially typed/pasted 20-number result.
    if "v10_blank_input_migrated" not in st.session_state:
        existing=st.session_state.get("v10_pasted_draw", "")
        legacy=next_paste_template(draws)
        if not existing or existing.strip()==legacy.strip() or re.fullmatch(
            r"Çekiliş no:\s*\d+\s*\n\s*\d{2}\.\d{2}\.\d{4}-\d{2}:\d{2}\s*",
            existing.strip()):
            st.session_state["v10_pasted_draw"]=""
        st.session_state["v10_blank_input_migrated"]=True
    if st.session_state.pop("v10_clear_paste", False):
        st.session_state["v10_pasted_draw"] = ""
    pasted=st.text_area("Çekiliş sonuç metni",height=225,key="v10_pasted_draw",
                        placeholder="")
    if st.button("📥 Yapıştırdığım çekilişi ekle",type="primary",key="v10_add_paste"):
        records, issues=parse_pasted_draws(pasted)
        valid,repeats,conflicts=filter_new_draws(records,draws)
        if valid:
            st.session_state.v10_live.extend(valid)
            ok,pushed,push_message=persist_to_github_veri_txt(st.session_state.v10_live)
            if ok:
                backup_msg=auto_save()
                saved=push_message+" "+backup_msg
            else:
                saved=push_message+" Veriler şimdilik oturumda; JSON yedeğini indir."
        else:
            saved="Yeni çekiliş eklenmedi." if records else ""
        st.session_state.v10_last_paste={
            "added":len(valid),"repeats":repeats,
            "issues":(issues+conflicts)[:12],"saved":saved
        }
        if valid and not (issues or conflicts):
            st.session_state["v10_clear_paste"]=True
        st.rerun()
    if st.session_state.get("v10_last_paste"):
        p=st.session_state.v10_last_paste
        if p["added"]:
            st.success(f"{p['added']} çekiliş uygulamaya alındı; {p['repeats']} zaten kayıtlı.")
        else:
            st.info(f"Yeni kayıt eklenmedi; {p['repeats']} çekiliş zaten kayıtlı.")
        if p["issues"]:
            st.error("⚠️ Hatalı/çakışan kayıtlar kaydedilmedi: " + " | ".join(p["issues"]))
        if p["saved"]:
            if "GitHub veri.txt kalıcı kayıt:" in p["saved"] or "zaten veri.txt içinde" in p["saved"]:
                st.success("✅ GitHub ana veri.txt güncellendi. "+p["saved"])
            else:
                st.error("⚠️ Kalıcı kayıt henüz yapılmadı. "+p["saved"])
    st.download_button("⬇️ Çekilişlerimin JSON yedeğini indir",
                       json.dumps({"live":st.session_state.v10_live,
                                   "tickets":st.session_state.v10_tickets},ensure_ascii=False,indent=2),
                       file_name="V10_CANLI_KAYIT.json",mime="application/json",
                       key="v10_quick_backup")
    with st.expander("Tek tek alan doldur (isteğe bağlı)",expanded=False):
        default_no=max([d["no"] for d in draws],default=0)+1
        with st.form("manual_v10",clear_on_submit=False):
            no=st.number_input("Çekiliş numarası",min_value=1,value=default_no,step=1)
            day=st.date_input("Tarih",value=today)
            hr=st.selectbox("Saat",options=[moment("2026-01-01",p).strftime("%H:%M") for p in range(1,218)],
                            index=min(216,max(0,pos_of(now_tr())-1 if pos_of(now_tr()) else 0)))
            nums=st.text_area("Çıkan 20 sayı — virgül/boşlukla ayır",
                              placeholder="3, 8, 12, 18, ...",height=90)
            submit=st.form_submit_button("✅ Çekilişi ekle",type="primary")
        if submit:
            try:
                numbers=[int(x) for x in re.findall(r"\d+",nums)]
                dt=datetime.strptime(f"{day} {hr}","%Y-%m-%d %H:%M")
                new=make_draw(no,dt,numbers)
                if any(d["no"]==new["no"] or
                       (d["day"]==new["day"] and d["pos"]==new["pos"]) for d in draws):
                    raise ValueError("Ayni numara veya saatli cekilis zaten mevcut.")
                st.session_state.v10_live.append(new)
                ok,_,message=persist_to_github_veri_txt(st.session_state.v10_live)
                if ok:
                    st.success(f"✅ #{new['no']} GitHub veri.txt dosyasına kaydedildi. "+message)
                    st.caption(auto_save())
                else:
                    st.error(f"⚠️ #{new['no']} oturuma eklendi ancak GitHub'a kaydedilmedi. "+message)
            except Exception as exc:
                st.error("Eklenemedi: "+str(exc))

    st.write("**Toplu yükleme**")
    st.caption("Tek satır: 61653;12.10.2026 07:57;4,5,16,... şeklinde 20 sayı. Birden çok satır olabilir.")
    up=st.file_uploader("Çekiliş TXT / CSV yükle",type=["txt","csv"],key="batch_v10")
    if up and st.button("📥 Toplu çekilişleri ekle"):
        data=up.getvalue().decode("utf-8-sig")
        idx_no={d["no"] for d in draws}
        idx_pos={(d["day"],d["pos"]) for d in draws}
        added=0;invalid=0;duplicates=0
        records=[]
        for rawline in data.splitlines():
            if not re.match(r"^\s*\d+\s*;",rawline):
                continue
            try:
                records.append(parse_draw_line(rawline))
            except Exception:
                invalid+=1
        valid,duplicates,conflicts=filter_new_draws(records,draws)
        invalid+=len(conflicts)
        st.session_state.v10_live.extend(valid)
        added=len(valid)
        if added:
            ok,_,message=persist_to_github_veri_txt(st.session_state.v10_live)
        else:
            ok,message=False,"Yeni çekiliş yok."
        if ok:
            st.success(f"✅ {added} çekiliş GitHub veri.txt kaydına alındı; {duplicates} tekrar, {invalid} hatalı kayıt. "+message)
            st.caption(auto_save())
        else:
            st.error(f"⚠️ {added} çekiliş geçici oturumda; {duplicates} tekrar, {invalid} hatalı kayıt. "+message)
        if conflicts:
            st.warning("Çakışmalar: "+" | ".join(conflicts[:5]))
    if st.session_state.v10_live:
        st.write("**Son eklenen çekilişler**")
        st.dataframe([{"No":d["no"],"Tarih":d["day"],"Saat":d["dt"][11:16],
                       "Sayılar":"-".join(map(str,d["nums"]))}
                      for d in st.session_state.v10_live[-12:][::-1]],
                     hide_index=True,use_container_width=True)

with tabs[1]:
    st.subheader("Aile aktivasyonu ve hedef çekiliş")
    loaded_dates=Counter(d["day"] for d in draws)
    recent_day=max(loaded_dates,default=today.isoformat())
    preferred=today if loaded_dates.get(today.isoformat(),0) else date.fromisoformat(recent_day)
    if not loaded_dates.get(today.isoformat(),0):
        st.warning(f"Bugün ({today:%d.%m.%Y}) henüz kayıtlı çekiliş yok. Son kayıt günü {recent_day}; inceleme için o gün seçildi.")
    analysis_date=st.date_input("İncelenecek gün",value=preferred,
                                min_value=min_day,max_value=max(today,last_day))
    daystr=analysis_date.isoformat()
    day_draws=[d for d in draws if d["day"]==daystr]
    current=now_tr() if analysis_date==today else moment(daystr,217)+timedelta(minutes=1)
    cutoff=[d for d in draws if d["day"]<daystr]
    if not families or not cutoff:
        st.info("Hedef hesaplamak icin gecmis cekilis ve aile havuzu gerekli.")
        profiles={}
    else:
        profiles=train_profiles(json.dumps(cutoff,separators=(",",":")),
                                json.dumps(sorted(families),separators=(",",":")))
    st.caption("Model yalnız seçilen günden ÖNCEKİ kayıtlarla kurulur. Yeni çekiliş gelince ritim hedefleri tekrar değerlendirilir.")
    support_days=st.selectbox("Ritim hedefi için geçmişte en az kaç ayrı gün destek olsun?",
                              options=[2,1,3],
                              format_func=lambda n:f"{n} gün (erken/deneysel)" if n==1 else
                                                   f"{n} gün ({'temkinli' if n==2 else 'daha seçici'})",
                              index=0,key="v10_repeat_support")
    _,hits=active_signals(draws,families,profiles,daystr,current)
    known_pos={d["pos"] for d in day_draws}
    live_day=[d for d in day_draws if datetime.fromisoformat(d["dt"])<=current]
    latest=max(live_day,key=lambda d:d["pos"]) if live_day else None
    signals=repeat_gap_targets(hits,profiles,families,daystr,current,known_pos,
                               minimum_days=support_days,latest_known=latest)
    family_summaries,family_events=family_rhythm_report(draws,families,hits,daystr)
    cross_day_runs=cross_day_rhythm_report(profiles,families)
    calendar_fire={r["Aile"] for r in cross_day_runs}
    session_fire=cross_day_repeat_families(profiles,families,minimum_days=2)
    intraday_repeats=cross_day_intraday_report(profiles,families,minimum_days=2)
    fire_families=calendar_fire | session_fire
    hour_days_required=max(2,support_days)
    def ticket_gate(label,position):
        return rhythm_ticket_gate(profiles,label,position,fire_families,
                                  minimum_days=hour_days_required)
    st.caption("🔥 = geçmiş günlerde aynı aralık veya aynı aileye ait "
               "gün içi tekrar ritmi gözlendi; kesin isabet anlamına gelmez.")
    if support_days==1:
        st.warning("Deneysel: tek geçmiş gün bir tekrarın öngörülebilir olduğunu göstermez. Kupon hedefleri istatistiksel olarak doğrulanmış değildir.")
    st.markdown("### 📊 Bu tarihte gerçekten neler var?")
    a,b,c=st.columns(3)
    a.metric("Seçili gün çekilişi",len(day_draws))
    b.metric("Tam çıkan farklı aile",len(hits))
    c.metric("Şu an gelecek hedef",len(signals))
    st.caption(f"Aday havuzu: {len(families)} aile; görünüş yalnız tam sayılar tek çekilişte bulunduğunda sayılır.")
    if day_draws:
        first=min(day_draws,key=lambda d:d["dt"])
        last=max(day_draws,key=lambda d:d["dt"])
        st.caption(f"İlk kayıt: #{first['no']} {first['dt'][11:16]} • Son kayıt: #{last['no']} {last['dt'][11:16]}")
    else:
        st.error(f"{daystr} tarihinde henüz çekiliş verisi bulunmuyor. Önce canlı girişten bu tarihin çekilişlerini ekle.")
    by_k=Counter(families[label]["k"] for label in hits)
    sig_by_k=Counter(s["size"] for s in signals)
    summary=[{"Boyut":f"{k}'li","Aday aile":sum(f["k"]==k for f in families.values()),
              "Bu gün tam çıkan":by_k[k],
              "Gelecek saat hedefi":sig_by_k[k]} for k in range(5,11)]
    st.dataframe(summary,hide_index=True,use_container_width=True)
    st.markdown("### 🔥 Farklı günlerde ritim yapan aileler")
    f1,f2,f3=st.columns(3)
    f1.metric("Sabit gün ritmi",len(calendar_fire))
    f2.metric("Aynı gün içi ritim, farklı günlerde",len(session_fire))
    f3.metric("Bugün görülen alevli",len(set(hits)&fire_families))
    st.caption("Sabit gün ritmi: aynı aile en az 3 farklı tarihte art arda "
               "eşit gün aralıklarıyla tam çıktı. Diğer sayaç: "
               "aynı ailenin gün içi tekrar aralığı en az 2 farklı günde görüldü. "
               "İkisi ayrı ölçüdür; aynı aile iki grupta da olabilir.")
    if cross_day_runs:
        flame_sizes=["Hepsi"]+[str(k) for k in range(5,11)]
        filter_size=st.selectbox("🔥 Ritimli aile boyutu",flame_sizes,
                                 key="v10_fire_size")
        visible_runs=[r for r in cross_day_runs if
                      filter_size=="Hepsi" or r["Boyut"]==int(filter_size)]
        st.dataframe(
            [{**r, "Aile":"🔥 "+r["Aile"],
              "Bugün":"✅ tam çıktı" if r["Aile"] in hits else "—"}
             for r in visible_runs[:250]],
            hide_index=True,use_container_width=True)
        st.download_button("⬇️ Tüm farklı gün ritimleri CSV",
            family_order_csv(cross_day_runs),
            file_name=f"V10_GUNLER_ARASI_RITIM_{daystr}.csv",
            mime="text/csv",key="v10_calendar_fire_csv")
    else:
        st.info("Seçilen günden ÖNCE en az 3 farklı günde aynı aralıkla "
                "tekrarlanan sabit aile zinciri bulunamadı.")
    if intraday_repeats:
        with st.expander("🔥 Farklı günlerde aynı çekiliş aralığını tekrar eden aileler",
                         expanded=False):
            st.dataframe(
                [{**r,"Aile":"🔥 "+r["Aile"]} for r in intraday_repeats[:250]],
                hide_index=True,use_container_width=True)
            st.download_button("⬇️ Gün içi ritimlerin farklı gün tekrarları CSV",
                family_order_csv(intraday_repeats),
                file_name=f"V10_GUN_ICI_RITIM_DESTEK_{daystr}.csv",
                mime="text/csv",key="v10_intraday_fire_csv")
    else:
        st.caption("Önceki günlerde en az iki gün destekli aynı tam-aile "
                   "gün içi aralık şablonu henüz bulunamadı.")
    st.caption("🔥 alev bu ailelerden verilen kuponun yanında da gösterilir. "
               "Kayıtlı olmayan yeni günü eğitim verisine katmadan "
               "ritimleri yeniden hesaplarız. Gün ritmi tek başına "
               "kesin bir çekiliş saati vermez.")

    st.markdown("### 📜 Günlük Sinyal Defteri — geçmiş ve sonuçlar")
    replay=day_signal_replay(hits,profiles,families,daystr,day_draws,
                             minimum_days=support_days)
    settled=[r for r in replay if r["Sonuç"]!="Bekliyor (çekiliş kayıtta yok)"]
    successes=[r for r in settled if r["Sonuç"]=="TAM"]
    pending=[r for r in replay if r["Sonuç"]=="Bekliyor (çekiliş kayıtta yok)"]
    b1,b2,b3,b4=st.columns(4)
    b1.metric("Gün içinde doğan",len(replay))
    b2.metric("Sonucu kayıtlı",len(settled))
    b3.metric("Tam tutan",len(successes))
    b4.metric("Sonuç bekleyen",len(pending))
    st.caption("Bu tablo, her ailenin 1., 2. veya 3. görünüşünden sonra o anda "
               "bilinebilecek önceki gün ritimleriyle yeniden hesaplanır. "
               "Sonradan girilen çekiliş sonucu yalnızca isabet kontrolünde kullanılır. "
               "Sinyal oluşması, başarılı tahmin anlamına gelmez.")
    if replay:
        st.dataframe([{**r,"Aile":("🔥 " if r["Aile"] in fire_families else "")+r["Aile"]} for r in replay],hide_index=True,use_container_width=True)
        st.download_button(
            "⬇️ Günün tüm sinyalleri ve sonuçları (CSV)",
            family_order_csv(replay),
            file_name=f"V10_GUNLUK_SINYAL_DEFTERI_{daystr}.csv",
            mime="text/csv",key="v10_day_replay_csv"
        )
    else:
        st.info(f"{daystr} tarihinde kayıtlı çekilişler üzerinden "
                f"{support_days} geçmiş gün desteğiyle 1→2, 2→3 veya 3→4 "
                "tekrar hedefi doğmadı. Bu, başka tür aile aktivasyonu olmadığı "
                "anlamına gelmez.")
    if analysis_date!=today:
        st.caption("Geçmiş gün için 'Şu an gelecek hedef = 0' doğaldır: "
                   "tarihi geçmiş kuponlar canlı hedef olarak önerilmez. "
                   "Gün içinde oluşan sinyaller yukarıdaki defterdedir.")
    if hits:
        st.markdown("### 🔍 İlk kez, geçmişten gelen ve ritimli aileler")
        st.caption("İlk kez = yalnız yüklenmiş veri aralığında ilk tam görünüş; tüm tarih boyunca ilk kez demek değildir.")
        one=sum(r["Durum"].startswith("İLK") for r in family_summaries)
        repeat=sum(r["Bugün kaç kez"]>=2 for r in family_summaries)
        rhythmic=sum(r["Ritim türü"] in ("Sabit","Artan","Azalan") for r in family_summaries)
        a1,a2,a3=st.columns(3)
        a1.metric("Bu veride ilk kez",one)
        a2.metric("Bugün 2+ görünen",repeat)
        a3.metric("Sabit/artan/azalan",rhythmic)
        st.dataframe(
            [{"Aile":("🔥 " if r["Aile"] in fire_families else "")+r["Aile"],"Boyut":r["Boyut"],"Durum":r["Durum"],
              "Bugün":r["Bugün kaç kez"],"Ritim":r["Bugün ritim"],
              "Çekilişler":r["Bugün çekilişler"],
              "Geçmiş gün":r["Geçmiş kaç gün"],"3+ gün":r["Geçmişte 3+ gün"],
              "4+ gün":r["Geçmişte 4+ gün"],
              "Gün aralığı":r["Günler arası"],
              "+2 gün":r["+2 gün"],"+5 gün":r["+5 gün"]}
             for r in family_summaries[:200]],
            hide_index=True,use_container_width=True)
        with st.expander("📚 Aynı ailelerin geçmiş çizgisi (saat ve çekiliş no)",expanded=False):
            st.dataframe(
                [{"Aile":r["Aile"],"Boyut":r["Boyut"],
                  "Önceki son":r["En son önce"],
                  "Geçmiş görünüşler":r["Geçmiş görünüşler"],
                  "Tüm günler":r["Tüm tarih/gün"]}
                 for r in family_summaries[:200]],
                hide_index=True,use_container_width=True)
        if family_summaries:
            report_data=io.StringIO()
            out_fields=list(family_summaries[0].keys())
            writer=csv.DictWriter(report_data,fieldnames=out_fields,delimiter=";")
            writer.writeheader()
            writer.writerows(family_summaries)
            st.download_button("⬇️ Aile ve tüm ritim özeti CSV",
                               report_data.getvalue().encode("utf-8-sig"),
                               file_name=f"V10_AILE_RITIM_{daystr}.csv",mime="text/csv",
                               key="v10_family_summary_csv")
        if family_events:
            events_csv=io.StringIO()
            event_fields=list(family_events[0].keys())
            writer=csv.DictWriter(events_csv,fieldnames=event_fields,delimiter=";")
            writer.writeheader()
            writer.writerows(family_events)
            st.download_button("⬇️ Ailelerin bütün geçmiş çekiliş/saat kayıtları",
                               events_csv.getvalue().encode("utf-8-sig"),
                               file_name=f"V10_AILE_CEKILIS_GECMISI_{daystr}.csv",
                               mime="text/csv",key="v10_family_all_history")
    elif day_draws:
        st.warning("Bu gün çekilişler var, fakat aday havuzundan henüz tam görünen aile yok. Aile havuzu bütün olası kombinasyonlar değildir.")
    if analysis_date!=today:
        st.info("Geçmiş gün seçildi. Görünüşleri inceleyebilirsin; geçmişte kalmış saatler yeni hedef olarak önerilmez.")
    elif hits and not signals:
        st.info("Aile görüldü ama saat hedefi oluşmadı. Neden: geçmişte iki farklı günde aynı aralık desteği yok, ya da bu günün sonraki uygun saatleri henüz hesaplanamıyor.")
    st.markdown("### 5'li – 10'lu hedef kuponları")
    st.caption("🔥 alevli ailelere kupon: hedefin saat diliminde geçmişten "
               f"en az {hour_days_required} ayrı gün tam görünüş desteği gerekli. "
               "Saat desteği olmayan sinyaller izlenir; kupon oluşturulmaz.")
    groups={k:[] for k in range(5,11)}
    for signal in signals:
        signal={**signal, "hour_gate":ticket_gate(signal["label"],signal["pos"])}
        groups[signal["size"]].append(signal)
    for k in range(5,11):
        eligible=sum(x["hour_gate"]["coupon_ok"] for x in groups[k])
        options=sorted(groups[k],
                       key=lambda x:(not x["hour_gate"]["coupon_ok"],
                                     x["pos"],-x["support"],x["label"]))[:30]
        title=(f"{k}'li aileler — {len(groups[k])} sinyal, "
               f"{eligible} kupon uygun") if options else f"{k}'li aileler — Sinyal yok"
        with st.expander(title,expanded=bool(options)):
            if not options:
                st.caption("Bu boyutta ileri hedef yok. Motor 0 kupon öneriyor.")
                continue
            st.dataframe(
                [{"Aile":("🔥 " if x["label"] in fire_families else "")+x["label"],"Hedef":x["stage"],
                  "Saat":x["time"],"Sıra":x["pos"],
                  "Tahmini no":"#"+str(x["estimated_no"]) if x["estimated_no"] else "—",
                  "Ritim":x["pattern"],"Tür":x["kind"],
                  "Geçmiş destek (gün)":x["support"],
                  "Hedef saat geçmiş gün":x["hour_gate"]["days"],
                  "Kupon durumu":("✅ saat destekli" if x["hour_gate"]["coupon_ok"]
                                   else "⏳ 🔥 saat desteği eksik")} for x in options],
                hide_index=True,use_container_width=True)
            pick=st.selectbox(f"{k}'li hedef seç",list(range(len(options))),
                format_func=lambda i:options[i]["time"]+" | "+("🔥 " if options[i]["label"] in fire_families else "")+options[i]["label"],
                key=f"v10_select_{k}")
            x=options[pick]
            if not x["hour_gate"]["coupon_ok"]:
                st.info(f"🔥 {x['label']} geçmişte ritimli, ancak {x['time']} "
                        f"saatinde yalnız {x['hour_gate']['days']} ayrı geçmiş gün desteği var. "
                        f"En az {hour_days_required} gün olmadığı için kupon üretilmiyor.")
                continue
            ticket_nums=make_ticket(x,draws,size=k)
            st.markdown(f"**{'🔥 ' if x['label'] in fire_families else ''}{k}'li kupon: "+", ".join(map(str,ticket_nums))+"**")
            st.caption(f"{x['day']} {x['time']} · {x['stage']} · {x['kind']} · "+
                       f"{x['support']} ritim destek günü · Hedef saat geçmiş gün desteği: "
                       f"{x['hour_gate']['days']} · Çekiliş sıra {x['pos']}. "+
                       ("Çekiliş numarası yalnız tahminidir." if x['estimated_no'] else "Numara henüz bilinmiyor."))
            if st.button(f"🎟️ {k}'li kuponu kaydet",key=f"v10_save_{k}"):
                ticket={"day":x["day"],"pos":x["pos"],"time":x["time"],
                        "family":x["label"],"numbers":ticket_nums,
                        "size":k,"kind":("🔥 " if x["label"] in fire_families else "")+x["kind"],"trigger_no":x["trigger_no"],
                        "created_at":now_tr().isoformat(timespec="seconds")}
                key=(ticket["day"],ticket["pos"],ticket["family"])
                existing={(t["day"],t["pos"],t["family"]) for t in st.session_state.v10_tickets}
                if key in existing:
                    st.warning("Bu aile ve hedef için kupon zaten kayıtlı.")
                else:
                    st.session_state.v10_tickets.append(ticket)
                    st.success(f"{k}'li kupon kaydedildi. "+auto_save())
    if not signals:
        st.info("Şu an bu destek düzeyinde 1→2, 2→3 veya 3→4 için ilerideki uygun saate denk gelen hedef yok. İstersen 1 geçmiş günle deneysel izleme yapabilirsin; ancak isabet güvencesi yok.")

    st.markdown("#### 10'lu ailelerin gün zinciri")
    watch=daily_chains(profiles,families,daystr)
    if watch:
        st.dataframe(watch[:50],hide_index=True,use_container_width=True)
        st.caption("Gun zinciri kesin saat vermez; bu nedenle otomatik kupon olusturulmaz.")
    else:
        st.caption("Bu tarihten sonraya uzanan +2/+5/+7/+14 zincir hedefi yok.")
    st.markdown("#### Seçili günde tam görünen aileler — kısa tekrar")
    if hits:
        top=[{"Aile":("🔥 " if label in fire_families else "")+label,"Boyut":families[label]["k"],
              "Bugunku gorunus":len(recs),
              "Cekilisler":", ".join("#"+str(d["no"])+" "+d["dt"][11:16] for d in recs)}
             for label,recs in hits.items()]
        top.sort(key=lambda x:(-x["Boyut"],-x["Bugunku gorunus"],x["Aile"]))
        st.dataframe(top[:100],hide_index=True,use_container_width=True)

with tabs[3]:
    st.subheader("Kupon isabet raporu")
    results=result_rows(st.session_state.v10_tickets,draws)
    completed=[r for r in results if r["Isabet"] is not None]
    a,b,c=st.columns(3)
    a.metric("Kupon",len(results))
    b.metric("Sonuclanan",len(completed))
    c.metric("En yuksek isabet",max((r["Isabet"] for r in completed),default="-"))
    if results:
        st.dataframe([{k:v for k,v in r.items() if k!="Isabet"} for r in results],
                     hide_index=True,use_container_width=True)
        counts=Counter(r["Isabet"] for r in completed)
        st.write("**5'li–10'lu boyutlara göre isabet dağılımı**")
        by_k=Counter((r["Boyut"],r["Isabet"]) for r in completed)
        st.dataframe([{"Boyut":k,"Isabet":f"{i}/{k}","Kupon":by_k[(k,i)]}
                      for k in range(5,11) for i in range(k+1)],
                     hide_index=True,use_container_width=True)
        mem=io.StringIO()
        writer=csv.DictWriter(mem,fieldnames=results[0].keys(),delimiter=";")
        writer.writeheader();writer.writerows(results)
        st.download_button("⬇️ Isabet raporunu indir","\ufeff"+mem.getvalue(),
                           file_name="V10_ISABET_RAPORU.csv",mime="text/csv")
    else:
        st.info("Kaydedilmis kupon yok. Hedef ekranindan deneysel kupon kaydedebilirsiniz.")

with tabs[4]:
    st.subheader("Kalıcı kayıt ve yedek")
    tok=secret_token()
    pin=secret_admin_pin()
    st.write("GitHub token: "+"✅ Tanımlı" if tok else "GitHub token: ⚠️ Tanımlı değil")
    if tok and pin:
        if st.session_state.get("v10_admin_unlocked", False):
            st.success("Yonetici yetkisi acik. Kayitlar GitHub'a yazilabilir.")
        else:
            secret_entry=st.text_input("GitHub kaydini acmak icin V10 yonetici PIN",type="password")
            if st.button("🔐 Kalici kaydi ac"):
                if hmac.compare_digest(secret_entry,pin):
                    st.session_state.v10_admin_unlocked=True
                    st.success("Yonetici kilidi acildi.")
                else:
                    st.error("PIN yanlis.")
    elif tok:
        st.warning("GitHub'a guvenli yazma kapali. Secrets'e V10_ADMIN_PIN ekleyin.")
    st.caption("ChatGPT'ye GitHub bağlamak Streamlit'e token aktarmaz. Streamlit Secrets'te GITHUB_TOKEN ve V10_ADMIN_PIN olmalı.")
    st.write("**Ana veri.txt kalıcı kayıt**")
    if pending_draws:
        st.warning(f"{len(pending_draws)} yeni çekiliş henüz veri.txt içinde değil.")
    else:
        st.success("Bu oturumun tüm çekilişleri ana veri.txt içinde veya zaten kayıtlı.")
    if st.button("💾 Eklenmemiş çekilişleri GitHub veri.txt'ye kaydet"):
        ok,pushed,message=persist_to_github_veri_txt(st.session_state.v10_live)
        st.session_state["v10_last_github_push"]=message
        if ok:
            auto_save()
        st.rerun()
    if st.session_state.get("v10_last_github_push"):
        st.info(st.session_state["v10_last_github_push"])
    payload={"live":st.session_state.v10_live,"tickets":st.session_state.v10_tickets}
    st.download_button("⬇️ Canli cekilis ve kupon JSON yedegi",
                       json.dumps(payload,ensure_ascii=False,indent=2),
                       file_name="V10_CANLI_KAYIT.json",mime="application/json")
    if st.button("☁️ Simdi GitHub'a kaydet"):
        st.info(auto_save())
    restore=st.file_uploader("Onceden indirilmis V10 JSON yedegi",type=["json"],key="restore_v10")
    if restore and st.button("📥 Yedegi geri yukle"):
        try:
            b=validate_saved(json.loads(restore.getvalue().decode("utf-8-sig")))
            st.session_state.v10_live=b["live"]
            st.session_state.v10_tickets=b["tickets"]
            st.success("Yedek geri yuklendi. "+auto_save())
            st.rerun()
        except Exception as exc:
            st.error("Yedek hatasi: "+str(exc))
    st.caption("Bu uygulama gercek cekilis sonuclarini tahmin garantisiyle sunmaz. Veriler acik GitHub deposuna kaydediliyorsa kamuya acik olabilir.")


with tabs[2]:
    st.subheader("🔁 Aileler arası sıra ve nöbet değişimi")
    st.caption(
        "A→B ve A→B→C: farklı ailelerin AYRI çekilişlerde aynı gün içinde "
        "belirli aralıklarla görünmesi. Eğitim sadece incelenen günden önceki "
        "çekilişlerden yapılır. Aynı çekilişte birlikte çıkan aileler 'sıra' sayılmaz."
    )
    st.write(f"**İncelenen tarih:** {daystr} • **Geçmiş destek:** en az {support_days} ayrı gün")
    sira_gap=st.slider("Aileden sonraki aileye en fazla kaç çekiliş aransın?",
                       min_value=1, max_value=36, value=12, step=1, key="v10_sira_gap")
    st.caption("Örnek: +3 aralığı, A'dan üç çekiliş sonra B'nin tam görünmesidir.")
    sira_open=st.checkbox("🔍 Aile sıralarını analiz et / güncel verilerle yenile",
                           key="v10_sira_enabled", value=False)
    if not families or not cutoff:
        st.info("Sıra araştırması için aile havuzu ve seçilen tarihten önce çekilişler gerekli.")
    elif not sira_open:
        st.info("Telefonu yavaşlatmamak için ağır analiz kapalıdır. Yukarıdaki kutuyu işaretleyerek açabilirsin.")
    else:
        try:
            with st.spinner("Geçmiş günlerde A→B ve A→B→C sıraları taranıyor..."):
                sira_events, sira_pairs, sira_triples = cached_family_order_report(
                    json.dumps(draws, separators=(",",":")),
                    json.dumps(sorted(families), separators=(",",":")),
                    daystr, sira_gap, support_days
                )
            sira_seen=family_order_matches(sira_events, daystr, sira_pairs, sira_triples)
            s1,s2,s3=st.columns(3)
            s1.metric("A→B ritmi", len(sira_pairs))
            s2.metric("A→B→C zinciri", len(sira_triples))
            s3.metric("Bugün gözlenen", len(sira_seen))
            st.caption("Sayılar, aday havuzunda destek koşulunu sağlayan farklı tam-aile dizilimleridir. "
                       "Bunlar doğrulanmış tahmin başarısı veya kazanma olasılığı değildir.")
            st.markdown("#### ⏭️ Sıradaki aile için canlı hedefler")
            if analysis_date == today:
                sira_targets=family_order_targets(
                    sira_events, daystr, sira_pairs, sira_triples, now_tr(), moment
                )
            else:
                sira_targets=[]
                st.caption("Geçmiş gün seçili: geçmiş saatlere canlı kupon üretilmez.")
            if sira_targets:
                enriched_targets=[
                    {**t,"hour_gate":ticket_gate(t["Aile"],t["Hedef sıra"])}
                    for t in sira_targets
                ]
                st.dataframe(
                    [{**{k:v for k,v in t.items() if k not in ("moment","hour_gate")},
                      "Hedef saat geçmiş gün":t["hour_gate"]["days"],
                      "Kupon durumu":("✅ uygun" if t["hour_gate"]["coupon_ok"]
                                      else "⏳ 🔥 saat desteği eksik")}
                     for t in enriched_targets[:150]],
                    hide_index=True, use_container_width=True
                )
                candidates=sorted(
                    enriched_targets,
                    key=lambda t:(not t["hour_gate"]["coupon_ok"],
                                  t["Hedef sıra"],-t["Destek gün"]))[:50]
                picked=st.selectbox(
                    "Kupon hedefi seç", range(len(candidates)),
                    format_func=lambda i:(
                        f'{candidates[i]["Hedef saat"]} • '
                        f'{candidates[i]["Aşama"]} • {"🔥 " if candidates[i]["Aile"] in fire_families else ""}{candidates[i]["Aile"]}'
                    ),key="v10_sira_ticket_pick"
                )
                chosen=candidates[picked]
                coupon_ok=chosen["hour_gate"]["coupon_ok"]
                if coupon_ok:
                    coupon=make_ticket(
                        {"label":chosen["Aile"],"moment":chosen["moment"]},
                        draws, size=len(chosen["Aile"].split("-"))
                    )
                    st.write(("🔥 " if chosen["Aile"] in fire_families else "")+
                             "**Deneysel aile kuponu:** "+", ".join(map(str,coupon)))
                    st.caption(
                        f'{chosen["Aşama"]} • {chosen["Destek gün"]} ritim destek günü • '
                        f'Hedef saat geçmiş destek: {chosen["hour_gate"]["days"]} gün. '
                        "Bu ritmin sonraki çekilişte süreceğine dair garanti yoktur."
                    )
                else:
                    st.info(f"🔥 {chosen['Aile']} hedef saat {chosen['Hedef saat']} "
                            f"için {chosen['hour_gate']['days']}/{hour_days_required} "
                            "geçmiş gün desteği bulundu. Kupon üretilmedi.")
                if coupon_ok and st.button("🎟️ Sıra kuponunu kaydet", key="v10_sira_save"):
                    ticket={
                        "day":daystr, "pos":chosen["Hedef sıra"],
                        "time":chosen["Hedef saat"], "family":chosen["Aile"],
                        "numbers":coupon,"size":len(coupon),
                        "kind":("🔥 " if chosen["Aile"] in fire_families else "")+"Aile sırası "+chosen["Aşama"],
                        "trigger_no":0,"created_at":now_tr().isoformat(timespec="seconds")
                    }
                    ticket_key=(ticket["day"],ticket["pos"],ticket["family"])
                    existing_keys={(t["day"],t["pos"],t["family"])
                                   for t in st.session_state.v10_tickets}
                    if ticket_key in existing_keys:
                        st.warning("Bu aile ve hedef için kupon zaten kayıtlı.")
                    else:
                        st.session_state.v10_tickets.append(ticket)
                        st.success("Sıra kuponu kaydedildi. "+auto_save())
                st.download_button("⬇️ Canlı sıra hedefleri CSV",
                    family_order_csv([{k:v for k,v in r.items() if k!="moment"}
                                      for r in sira_targets]),
                    file_name=f"V10_SIRA_HEDEF_{daystr}.csv",mime="text/csv",
                    key="v10_sira_target_csv")
            else:
                st.info("Henüz gelecekteki uygun çekilişe denk gelen, geçmiş destekli sıra hedefi yok.")
            st.markdown("#### ✅ Bu tarihte gerçekten gözlenen sıralar")
            if sira_seen:
                st.dataframe(sira_seen,hide_index=True,use_container_width=True)
            else:
                st.caption("Seçilen günde geçmişten destekli bir A→B / A→B→C zinciri tamamlanmadı.")
            st.markdown("#### 📚 Geçmişte desteklenen aile sıraları")
            if sira_triples:
                with st.expander(f"Üç aile zincirleri — {len(sira_triples)}", expanded=True):
                    st.dataframe(sira_triples[:200], hide_index=True,use_container_width=True)
                    st.download_button("⬇️ A→B→C zincirlerini indir",
                        family_order_csv(sira_triples),
                        file_name=f"V10_ABC_ZINCIRLER_{daystr}.csv",mime="text/csv",
                        key="v10_sira_triple_csv")
            if sira_pairs:
                with st.expander(f"İki aile sıraları — {len(sira_pairs)}",expanded=not bool(sira_triples)):
                    st.dataframe(sira_pairs[:200],hide_index=True,use_container_width=True)
                    st.download_button("⬇️ A→B sıralarını indir",
                        family_order_csv(sira_pairs),
                        file_name=f"V10_AB_SIRALAR_{daystr}.csv",mime="text/csv",
                        key="v10_sira_pair_csv")
            if not sira_pairs:
                st.warning("Bu tarih öncesinde seçilen gün desteği ve aralık için tekrarlanan sıra bulunamadı.")
            st.caption("Uyarı: Aynı veri üzerinde birçok sıra aranması tesadüfi tekrar üretir. "
                       "Gerçek üstünlük için ileri tarihli kör test ve rastgele karşılaştırma gerekir.")
        except Exception as exc:
            st.error("Aile sırası analizinde hata: "+str(exc))


with tabs[5]:
    st.subheader("🔮 Geliyorum — tüm aileler için erken uyarı")
    st.caption(
        "V10'un 5'li, 6'lı, 7'li, 8'li, 9'lu, 10'lu tüm kayıtlı aileleri taranır. "
        "Kısmi eşleşme ve daha önce aynı saat diliminde tam görünme sayısı izlenir. "
        "Bunlar deneysel işaretlerdir; çekilişler bağımsız olduğundan "
        "sonraki çekilişte görünme üstünlüğü kanıtlanmış değildir."
    )
    alert_min_hour=max(2,support_days)
    early_daily_support={
        r["Aile"] for r in cross_day_runs
        if r["Devam etse tarih"]==daystr
    }
    st.caption(
        f"🔥 kupon için hedef saatinde geçmiş en az {alert_min_hour} ayrı gün tam görünüş "
        "gereklidir. Kısmi sinyalin yalnız son 3 bilinen çekilişten gelmesi gerekir. "
        "Öneri sadece bilinen son çekilişin hemen ARDINDAN gelen tek çekiliş içindir."
    )
    if analysis_date==today and families and profiles:
        with st.spinner("Bütün aileler son çekilişler üzerinde taranıyor..."):
            early_rows,early_stats=upcoming_alerts(
                day_draws,families,profiles,daystr,now_tr(),moment,
                minimum_hour_days=alert_min_hour,
                day_rhythm_families=early_daily_support,
                limit=len(families)
            )
        a,b,c,d=st.columns(4)
        a.metric("Taranan aile",early_stats["scanned"])
        b.metric("Kısmi işaret",early_stats["partial"])
        c.metric("Saat destekli",early_stats["hour_supported"])
        d.metric("Kupon koşulu",early_stats["coupon_ready"])
        if early_stats["reason"]=="stale":
            st.warning("⏳ Son kayıtlı çekilişten sonraki hedef saati geçmiş. "
                       "Güncel çekilişi 📥 Canlı giriş bölümünden ekleyince motor yeni "
                       "hedefi hesaplayacak. Geçmiş saate kupon çıkarılmaz.")
        elif early_stats["reason"]=="no_draw":
            st.info("Bugünün ilk çekilişini eklemeden 'Geliyorum' tetiklenmez.")
        elif early_stats["reason"]=="end_of_day":
            st.info("Bugünün son çekilişi tamamlandı. Yeni gün için veri bekleniyor.")
        else:
            st.info(f"🎯 Hedef: #{day_draws[-1]['no']+1} • "
                    f"{moment(daystr,early_stats['target']):%H:%M} • "
                    f"{early_stats['target']}. çekiliş. "
                    "Bu yalnızca bir sonraki çekiliş için oluşturulmuş deneysel aday listesidir.")
        st.markdown("#### 5'li–10'lu erken uyarı dağılımı")
        st.dataframe([
            {"Aile boyutu":k, "Aday havuzu":sum(f["k"]==k for f in families.values()),
             "Kısmi":early_stats["sizes"].get(k,{}).get("partial",0),
             "Saat destekli":early_stats["sizes"].get(k,{}).get("supported",0),
             "Kupon koşulu":early_stats["sizes"].get(k,{}).get("coupon_ready",0)}
            for k in range(5,11)
        ], hide_index=True,use_container_width=True)
        if early_rows:
            only_ready=st.checkbox("Yalnız 🔥 kupon koşulunu geçenleri göster",
                                   value=False,key="v10_early_only_ready")
            visible=[r for r in early_rows if
                     not only_ready or r["Kupon uygun"]]
            st.dataframe(
                [{k:v for k,v in r.items() if k not in ("moment","Hedef tarih")}
                 for r in visible[:200]],
                hide_index=True,use_container_width=True
            )
            st.download_button(
                "⬇️ Tüm Geliyorum sinyalleri CSV",
                family_order_csv([{k:v for k,v in r.items() if k!="moment"}
                                  for r in early_rows]),
                file_name=f"V10_GELIYORUM_{daystr}.csv",
                mime="text/csv",key="v10_geliyorum_csv"
            )
            ready=[r for r in early_rows if r["Kupon uygun"]]
            if ready:
                picked=st.selectbox(
                    "🔥 Hedef çekiliş kupon adayı",list(range(len(ready))),
                    format_func=lambda i:(
                        f'{ready[i]["Hedef saat"]} • {ready[i]["Durum"]} • '
                        f'{ready[i]["Aile"]} • {ready[i]["Kısmi"]}'
                    ),key="v10_early_selected"
                )
                chosen=ready[picked]
                coupon=list(families[chosen["Aile"]]["nums"])
                st.markdown("**"+chosen["Durum"]+" — "+
                            str(chosen["Boyut"])+"'li kupon: "+
                            ", ".join(map(str,coupon))+"**")
                st.caption(f'Hedef #{chosen["Hedef no"]} • {chosen["Hedef saat"]} • '
                           f'Geçmiş aynı saat desteği {chosen["Geçmiş saat günü"]} ayrı gün. '
                           "Bu işaret, tahmin başarısı kanıtı değildir.")
                if st.button("🎟️ Geliyorum kuponunu kaydet",
                             key="v10_early_save"):
                    if datetime.fromisoformat(chosen["moment"])<=now_tr():
                        st.error("Hedef çekilişin saati geçti. Yeni sonuç ekleyip tekrar değerlendir.")
                    else:
                        ticket={
                            "day":daystr,"pos":chosen["Hedef sıra"],
                            "time":chosen["Hedef saat"],"family":chosen["Aile"],
                            "numbers":coupon,"size":chosen["Boyut"],
                            "kind":chosen["Durum"]+" (Geliyorum erken uyarı)",
                            "trigger_no":chosen["İşaret çekilişi"],
                            "created_at":now_tr().isoformat(timespec="seconds")
                        }
                        key=(ticket["day"],ticket["pos"],ticket["family"])
                        existing={
                            (t["day"],t["pos"],t["family"])
                            for t in st.session_state.v10_tickets
                        }
                        if key in existing:
                            st.warning("Bu aile için aynı çekilişe kupon zaten kaydedildi.")
                        else:
                            st.session_state.v10_tickets.append(ticket)
                            st.success("Kupon izleme listesine kaydedildi.")
                            st.info(auto_save())
            else:
                st.info("Bu an için geçmiş saat desteği yeterli Geliyorum kuponu yok. "
                        "🟡 uyarılar izleme amaçlı; kupon verilmez.")
        elif early_stats["reason"]=="ok":
            st.info("Bu çekilişten önce yeterli kısmi görünüşü olan aile tespit edilmedi.")
    elif analysis_date!=today:
        st.info("Geçmiş gün seçili. Canlı kupon yerine aşağıdan gün içi "
                "adım adım testini başlatabilirsin.")
    else:
        st.info("Geliyorum için aile havuzu ve geçmiş günlerin verisi gerekli.")

    st.markdown("#### 🧪 Günlük ileriye dönük adım adım test")
    st.caption(
        "Seçilen günün her çekilişinde sadece o ana kadar bilinen sayılarla "
        "bir sonraki çekiliş için aday üretir. Seçilen günün gelecekteki "
        "sonuçları sinyal hesabına sokulmaz; yalnızca sonradan isabeti ölçülür. "
        "Aile havuzunun geçmiş çekilişlerden seçilmiş olması nedeniyle bu test "
        "tam bağımsız doğrulama sayılmaz."
    )
    if st.button("🧪 Bu günün Geliyorum hedeflerini test et",
                 key="v10_early_backtest_run"):
        if not day_draws or not profiles or not families:
            st.warning("Test için geçmiş ve seçilen güne ait çekiliş gerekli.")
        else:
            with st.spinner("Çekilişler sırayla yeniden oynatılıyor..."):
                early_test=replay_warning_day(
                    day_draws,families,profiles,daystr,moment,
                    minimum_hour_days=alert_min_hour,
                    day_rhythm_families=early_daily_support
                )
            st.session_state["v10_early_backtest"]={
                "day":daystr,"minimum_days":alert_min_hour,
                "last_no":max(d["no"] for d in day_draws),
                "rows":early_test
            }
    saved_test=st.session_state.get("v10_early_backtest",{})
    if (saved_test.get("day")==daystr and
        saved_test.get("minimum_days")==alert_min_hour and
        saved_test.get("last_no")==max((d["no"] for d in day_draws),default=-1)):
        tested=saved_test["rows"]
        full=sum(r["Tam"] for r in tested)
        t1,t2,t3=st.columns(3)
        t1.metric("Test edilen kupon",len(tested))
        t2.metric("Tam aile isabeti",full)
        t3.metric("Yanlış alarm",len(tested)-full)
        if tested:
            st.dataframe([{k:v for k,v in r.items() if k!="Tam"} for r in tested[:150]],
                         hide_index=True,use_container_width=True)
            st.download_button(
                "⬇️ Geliyorum adım adım test CSV",
                family_order_csv([{k:v for k,v in r.items() if k!="Tam"}
                                  for r in tested]),
                file_name=f"V10_GELIYORUM_TEST_{daystr}.csv",
                mime="text/csv",key="v10_early_backtest_download"
            )
        else:
            st.caption("Bu gün hiçbir kupon adayı filtreyi geçmedi.")


@st.cache_data(ttl=300,show_spinner=False)
def cached_six_gap_replay(draws_json, families_json, threshold):
    """Heavy replay only on explicit request; cached by complete inputs."""
    loaded_draws=json.loads(draws_json)
    labels=json.loads(families_json)
    loaded_families={
        label:{"k":6,"nums":tuple(int(n) for n in label.split("-")),
               "mask":sum(1 << (int(n)-1) for n in label.split("-"))}
        for label in labels
    }
    return walkforward_six_gap(loaded_draws,loaded_families,moment,
                               minimum_days=threshold)


with tabs[6]:
    st.subheader("🔥 6'lı aile — aynı çekiliş aralığı farklı günlerde")
    st.caption("Tam senin tarif ettiğin motor: aynı 6 sayı bir günde iki ayrı "
               "çekilişte aralarında +G çekiliş farkıyla tam çıktıysa; geçmişte "
               "aynı ailede aynı +G aralığı başka günde de görülmüşse "
               "ikinci görünüşten +G sonrası ÜÇÜNCÜ hedef çekiliş olur. "
               "Eşit takvim günü aralığı değil, çekiliş sayısı farkı aranır. "
               "Her gün SADECE ilk iki tam görünüşten 3. hedef çıkarılır.")
    st.caption("Mevcut V10 aile listesindeki 198 adet 6'lı aile izlenir. "
               "Tüm olası 6'lı sayı kombinasyonlarını kapsamaz; "
               "bu aileler de eski verilere bakılarak seçilmiş olabilir.")
    six_support=st.selectbox(
        "Daha önce aynı çekiliş aralığı kaç farklı günde görülmüş olsun?",
        options=[1,2,3],index=0,
        format_func=lambda n:("1 gün — bugünkü tekrar ile toplam en az 2 gün "
                              "(deneysel)" if n==1 else
                              f"{n} geçmiş gün — daha seçici"),
        key="v10_alti_gap_support"
    )
    st.caption("🔥 Gerçek kupon oluşturma eşiği: aralığın bugünden ÖNCE en az "
               "2 farklı gün desteği ve hedef saatinde en az 2 farklı "
               "geçmiş gün tam görünüşü. Diğerleri 🟡 izleme sinyalidir.")
    six_profiles={label:p for label,p in profiles.items()
                  if label in families and families[label]["k"]==6}
    cross_gap=[
        {"Aile":label,"Aralık":gap,"Destek geçmiş gün":count}
        for label,p in six_profiles.items()
        for gap,count in p.get("first",{}).items()
        if count>=six_support
    ]
    cross_gap.sort(key=lambda r:(-r["Destek geçmiş gün"],r["Aralık"],r["Aile"]))
    st.markdown("#### 🔁 Geçmişte aynı +G aralığını başka günlerde yapanlar")
    ca,cb,cc=st.columns(3)
    ca.metric("6'lı aile havuzu",sum(f["k"]==6 for f in families.values()))
    cb.metric("Geçmişteki aile-aralık",len(cross_gap))
    cc.metric("Ayrı aile",len({r["Aile"] for r in cross_gap}))
    if cross_gap:
        with st.expander("📚 Aileler, aralıklar ve geçmiş destek günleri",
                         expanded=False):
            st.dataframe(cross_gap[:200],hide_index=True,use_container_width=True)
            st.download_button("⬇️ 6'lı aile geçmiş aralıkları CSV",
                family_order_csv(cross_gap),
                file_name=f"V10_6LI_GECMIS_ARALIK_{daystr}.csv",
                mime="text/csv",key="v10_six_history_export")
    else:
        st.caption("Bu eşikte farklı gün desteğine sahip aile-aralık bulunamadı.")

    st.markdown("#### 🎯 Aynı aile 2 kez çıktı → 3. çekiliş hedefi")
    if analysis_date!=today:
        st.info("Geçmiş gün seçili. Geçmişte kalmış saate canlı kupon "
                "verilmiyor; aşağıdaki adım adım test kullanılabilir.")
        six_live=[]
    else:
        six_live=gap_targets_today(
            hits,families,profiles,daystr,now_tr(),moment,known_pos,
            minimum_days=six_support,minimum_hour_days=2
        )
    sa,sb=st.columns(2)
    sa.metric("Gelecek hedef sinyali",len(six_live))
    sb.metric("🔥 Kupon koşulu geçen",sum(r["Kupon uygun"] for r in six_live))
    if six_live:
        st.dataframe(
            [{k:v for k,v in r.items() if k!="moment"}
             for r in six_live[:150]],
            hide_index=True,use_container_width=True
        )
        st.download_button("⬇️ Canlı 6'lı ritim hedefleri CSV",
            family_order_csv([{k:v for k,v in r.items() if k!="moment"}
                              for r in six_live]),
            file_name=f"V10_6LI_CANLI_HEDEF_{daystr}.csv",
            mime="text/csv",key="v10_six_live_csv"
        )
        six_ready=[r for r in six_live if r["Kupon uygun"]]
        if six_ready:
            chosen_index=st.selectbox(
                "🔥 Altılı kupon için hedef seç",range(len(six_ready)),
                format_func=lambda i:(
                    f'{six_ready[i]["Hedef saat"]} • '
                    f'+{six_ready[i]["Aralık"]} • '
                    f'{six_ready[i]["Aile"]}'
                ),key="v10_six_coupon_select"
            )
            chosen=six_ready[chosen_index]
            coupon=list(families[chosen["Aile"]]["nums"])
            st.markdown("**🔥 6'lı hedef kuponu: "+
                        ", ".join(map(str,coupon))+"**")
            st.caption(f'Hedef #{chosen["Tahmini no"]} • '
                       f'{chosen["Hedef tarih"]} {chosen["Hedef saat"]} • '
                       f'Ritim geçmiş destek: {chosen["Geçmiş ritim gün"]} gün • '
                       f'Saat desteği: {chosen["Hedef saat destek"]} gün. '
                       "Çekiliş numarası, sıra devam ederse geçerli tahmindir.")
            if st.button("🎟️ 6'lı ritim kuponunu kaydet",
                         key="v10_six_save"):
                if datetime.fromisoformat(chosen["moment"])<=now_tr():
                    st.error("Hedef çekilişin saati geçti. Yeni sonuç ekle.")
                else:
                    ticket={
                        "day":chosen["Hedef tarih"],"pos":chosen["Hedef sıra"],
                        "time":chosen["Hedef saat"],"family":chosen["Aile"],
                        "numbers":coupon,"size":6,
                        "kind":f'🔥 6’lı tekrarlanan +{chosen["Aralık"]} ritim',
                        "trigger_no":chosen["Tetik no"],
                        "created_at":now_tr().isoformat(timespec="seconds")
                    }
                    key=(ticket["day"],ticket["pos"],ticket["family"])
                    existing={(x["day"],x["pos"],x["family"])
                              for x in st.session_state.v10_tickets}
                    if key in existing:
                        st.warning("Bu çekiliş ve aile için kupon zaten kayıtlı.")
                    else:
                        st.session_state.v10_tickets.append(ticket)
                        st.success("Hedefli 6'lı kupon kaydedildi. "+auto_save())
        else:
            st.info("Şu anki hedefler 🟡 izleme amaçlı. Henüz "
                    "🔥 kupon koşulu geçen hedef yok.")
    else:
        st.info("Bu anda iki tam görünüşü ve eski gün aralık desteği "
                "eşleşen, gelecekteki çekilişi hedefleyen 6'lı aile yok.")

    st.markdown("#### 🧪 Gerçek test — tarih tarih, çekiliş çekiliş")
    st.caption("Her günün hedefleri o günden ÖNCEKİ ritim kayıtlarıyla "
               "hesaplanır. O günün sonuçları yalnız sonradan isabet "
               "kontrolünde kullanılır. Bugünlük yeni veriler girildikçe "
               "testi yeniden çalıştırabilirsin.")
    if st.button("🧪 6'lı aile motorunu tüm günlerde test et",
                 key="v10_six_start_replay"):
        with st.spinner("Geçmiş günler ileri doğru sırayla test ediliyor..."):
            replay=cached_six_gap_replay(
                json.dumps(draws,separators=(",",":")),
                json.dumps(sorted(label for label,f in families.items()
                                  if f["k"]==6),separators=(",",":")),
                six_support
            )
        st.session_state["v10_six_replay"]={
            "day":daystr,"threshold":six_support,
            "last_no":max((r["no"] for r in draws),default=-1),
            "rows":replay
        }
    saved=st.session_state.get("v10_six_replay",{})
    if (saved.get("day")==daystr and
        saved.get("threshold")==six_support and
        saved.get("last_no")==max((r["no"] for r in draws),default=-1)):
        replay=saved["rows"]
        report=six_gap_summary(replay)
        a,b,c,d=st.columns(4)
        a.metric("Hedef",report["Tahmin"])
        b.metric("Sonuçlanan",report["Sonuçlanan"])
        c.metric("6/6",report["6/6"])
        d.metric("Yanlış alarm",report["Tam olmayan"])
        st.caption(f"Kuponun bütün güvenlik koşullarını geçen: "
                   f'{report["Kupon koşulu geçen"]}. Bu sayı deneysel '
                   "izleme sinyallerinden ayrı tutulur.")
        dist=[{"İsabet":hit,"Hedef":number}
              for hit,number in report["Dağılım"].items()]
        st.dataframe(dist,hide_index=True,use_container_width=True)
        if replay:
            st.dataframe(replay[:150],hide_index=True,use_container_width=True)
            st.download_button("⬇️ 6'lı aile tüm gerçek test CSV",
                family_order_csv(replay),
                file_name=f"V10_6LI_GAP_WALKFORWARD_{six_support}GUN.csv",
                mime="text/csv",key="v10_six_test_csv")
        else:
            st.info("Bu destek ayarında geçmişte hedef doğmamış. "
                    "0 isabet, başarısız tahmin anlamına gelmez.")
        st.warning("Dikkat: Aileler geçmiş sonuçlara göre seçilmiş "
                   "olabileceğinden bu test kör bağımsız örneklem değildir. "
                   "Tekrarlar kazanmayı garanti etmez.")


@st.cache_data(ttl=900,show_spinner=False)
def cached_v11_study(draws_json, family_json, train_days):
    selected=json.loads(family_json)
    f={
        label:{"k":len(label.split("-")),
               "nums":tuple(int(n) for n in label.split("-")),
               "mask":sum(1<<(int(n)-1) for n in label.split("-"))}
        for label in selected
    }
    return run_study(json.loads(draws_json),f,train_days=train_days)


with tabs[7]:
    st.subheader("🧠 V11 — Aile davranışları ve 12 çekilişteki 20 sayı")
    st.caption(
        "6, 7, 8, 9 ve 10 sayılık aileleri ayrı inceler. Sessiz, tamamlayarak, "
        "yükselerek, dalgalanarak ve tam tekrar görünüşleri araştırır. "
        "Hedef öncesindeki 12 çekiliş × 20 sayı üzerinde sıcak/soğuk/ivme, "
        "beraber çıkış, yeni gelen sayılar, ardışık komşular ve bant dağılımı "
        "hesaplanır. Her hedef için yalnızca önceden bilinen kayıtlar kullanılır."
    )
    total_by_size={
        k:sum(1 for f in families.values() if f["k"]==k)
        for k in V11_SIZES
    }
    st.write("**Araştırılan aileler:** " +
             " · ".join(f"{k}'lı: {total_by_size[k]}" for k in V11_SIZES))
    st.caption(
        "Hedefler saatin 7, 8, 9, 10, 11 ve 12. çekilişleridir; "
        "ilk altı çekiliş ve önceki kayıtlar 12 çekilişlik geçmiş pencereyi "
        "oluşturur. 01:02 ek çekilişi ayrı tutulur. Eksik 12'lik pencereden "
        "tahmin üretilmez."
    )
    phase_days=st.slider("İlk araştırma dönemi (gün)",
                         min_value=20,max_value=55,value=36,step=1,
                         key="v11_research_train_days")
    if st.button("🚀 V11 — 73 günün tamamını analiz et",
                 key="v11_run_complete",type="primary"):
        with st.spinner("Bütün çekilişler, aileler ve 12×20 sayı hareketi "
                        "sırayla inceleniyor. Telefonu kapatmadan bekle."):
            report=cached_v11_study(
                json.dumps(draws,separators=(",",":")),
                json.dumps(sorted(label for label,f in families.items()
                                  if f["k"] in V11_SIZES),separators=(",",":")),
                phase_days
            )
        st.session_state["v11_analysis"]={
            "last_no":max((x["no"] for x in draws),default=0),
            "phase_days":phase_days,"result":report
        }
    last_draw_no=max((d["no"] for d in draws),default=0)
    v11_saved=st.session_state.get("v11_analysis",{})
    if v11_saved and v11_saved.get("phase_days")==phase_days:
        if v11_saved.get("last_no")!=last_draw_no:
            st.warning("Yeni çekilişler eklendi. Son rapor eski veriyle "
                       "hesaplanmış olabilir. Analizi yeniden başlat.")
        r=v11_saved["result"]
        meta=r["meta"]
        a,b,c,d=st.columns(4)
        a.metric("Takvim günü",meta["tarih_sayısı"])
        b.metric("Geçerli çekiliş",meta["çekiliş_sayısı"])
        c.metric("Test hedefi",meta["hedef_sayısı"])
        d.metric("Aile sayısı",sum(meta["aile_sayısı"].values()))
        st.caption(f'Veri dönemi: {meta["ilk_gün"]} → {meta["son_gün"]}. '
                   "İlk dönem ve sonraki dönem ayrı raporlanır; yöntemlerin "
                   "puanları son dönemin sonucuna bakılarak ayarlanmaz.")
        st.markdown("#### 🔬 Gerçekte tamamlanan aileler nasıl geldi?")
        selected_k=st.selectbox("Aile boyutu",V11_SIZES,
                                key="v11_size_select")
        arrival=[x for x in r["arrival"] if x["Boyut"]==selected_k]
        st.dataframe(arrival,hide_index=True,use_container_width=True)
        st.markdown("#### 🎯 Önceden verilen kupon hedeflerinin sonuçları")
        scores=[x for x in r["methods"] if x["Boyut"]==selected_k]
        st.dataframe(scores,hide_index=True,use_container_width=True)
        st.caption("Tam isabet ve isabet ortalaması, her kuponun tam hedef "
                   "çekilişi üzerinde ölçülür. Rastgele beklenen tek bilet "
                   f"ortalaması {selected_k}/4 = {selected_k/4:.2f} sayıdır. "
                   "Katalog aileleri geçmiş sonuçlarla seçildiğinden tarafsız "
                   "bağımsız veri testi kabul edilmez.")
        st.markdown("#### 🔥 1–80 sayının sıcak / soğuk aktivasyonu")
        st.caption("Her 7–12 hedefi öncesindeki 12 çekilişte, 1–80 "
                   "arasındaki HER sayının sıcaklığı ve son 6 çekilişteki "
                   "ivmesi hesaplandı. 20 gerçek çıkan sayı yalnız sonuç "
                   "sütununda kullanıldı. Bağımsız çekilişte beklenen oran %25.")
        st.dataframe(r["ball_states"],hide_index=True,
                     use_container_width=True)
        st.markdown("#### 7–12. çekilişlerin isabet karşılaştırması")
        slot_rows=[x for x in r["slots"] if x["Boyut"]==selected_k]
        st.dataframe(slot_rows,hide_index=True,use_container_width=True)
        st.markdown("#### 🕘 Saatlik 20 sayının davranışı")
        st.dataframe(r["hour_summary"],hide_index=True,
                     use_container_width=True)
        with st.expander("👁️ Tam görünüşlerin 12 çekilişlik yolculuk örnekleri"):
            st.dataframe(r["examples"],hide_index=True,use_container_width=True)
        with st.expander("🧪 Gerçek hedefe gitmeden önce üretilmiş sinyal örnekleri"):
            st.dataframe(r["signals"],hide_index=True,use_container_width=True)
        st.markdown("#### 📥 Ayrı veri raporları")
        downloadable=(
            ("6–10 ailelerinin geliş yolları","arrival","V11_GELIS_YOLLARI.csv"),
            ("73 gün bütün hedefler ve her yöntem isabeti","target_ledger","V11_7434_HEDEF_DEFTERI.csv"),
            ("7, 8, 9, 10, 11, 12. çekiliş ayrı sonuçları","slots","V11_7_12_SIRA_RAPORU.csv"),
            ("Önceden hedeflenen kuponların isabeti","methods","V11_TUM_ISABETLER.csv"),
            ("1–80 sayı sıcaklık ve aktivasyon oranları","ball_states","V11_80_SAYI_AKTIVASYON.csv"),
            ("12×20 sayı saat özeti","hour_summary","V11_20_SAYI_SAAT.csv"),
            ("Tam aile görünüş örnekleri","examples","V11_AILE_ORNEKLER.csv"),
            ("Sinyal ve hedef örnekleri","signals","V11_HEDEF_SINYALLERI.csv"),
        )
        for display,key,filename in downloadable:
            st.download_button("⬇️ "+display,
                v11_csv(r[key]),file_name=filename,
                mime="text/csv",key="v11_dl_"+key)
        st.download_button(
            "⬇️ V11 73 günlük tam araştırma özeti TXT",
            v11_text(r),file_name="V11_73_GUN_ARASTIRMA_OZETI.txt",
            mime="text/plain",key="v11_download_summary")
        st.warning("⚠️ Geçmişte güzel görünen ritim, sonraki çekilişte "
                   "kazandıracağı anlamına gelmez. Çok sayıda aile ve yöntem "
                   "taranması tesadüfi kalıpları artırır. Bağımsız ileri tarih "
                   "testi yapılmadan tahmin avantajı kanıtlanmış sayılmaz.")
    else:
        st.info("Araştırmayı çalıştırmak için 🚀 düğmesine bas. "
                "Geniş analiz yalnız isteğinle çalışır; diğer V10 "
                "sekmesini yavaşlatmaz.")

    st.markdown("#### 🔭 Yeni çekiliş için V11 ön izleme")
    st.caption("Ön izleme yalnız saatin 7–12. gelecek çekilişi için "
               "ve arkasında kesintisiz 12 kayıt varsa gösterilir.")
    if analysis_date==today and day_draws:
        ready_draws=[d for d in day_draws
                     if datetime.fromisoformat(d["dt"])<=now_tr()]
        last_pos=max((d["pos"] for d in ready_draws),default=0)
        next_pos=last_pos+1
        next_dt=moment(daystr,next_pos) if next_pos<=217 else None
        if (next_dt and next_dt>now_tr() and
            next_pos not in known_pos):
            preview=live_preview(
                ready_draws,
                {label:f for label,f in families.items()
                 if f["k"] in V11_SIZES},
                next_pos,
                {label:p.get("hour_days",{})
                 for label,p in profiles.items()}
            )
        else:
            preview=[]
        if preview:
            st.caption(f"Bir sonraki hedef: {next_dt:%H:%M} "
                       f"(günlük {next_pos}. çekiliş).")
            st.dataframe(preview,hide_index=True,use_container_width=True)
            st.download_button(
                "⬇️ V11 anlık deneysel sayı adayları",
                v11_csv(preview),
                file_name=f"V11_ON_IZLEME_{daystr}.csv",
                mime="text/csv",key="v11_live_csv")
            st.info("Bunlar araştırma adaylarıdır; V11 henüz doğrulanmış "
                    "tam isabet motoru değildir. Bu sekmede otomatik ücretli "
                    "kupon oluşturulmaz.")
        else:
            st.caption("Şu an için yeterli 12 çekilişli geçmişi bulunan "
                       "gelecek 7–12 slotu yok. Yeni çekiliş gelince "
                       "tekrar kontrol et.")
    else:
        st.caption("Ön izleme yalnız bugünün kayıtlarıyla çalışır.")


@st.cache_data(ttl=1200,show_spinner=False)
def cached_v12_tower_study(draws_json,training_days):
    return run_tower_study(json.loads(draws_json),train_days=training_days)


with tabs[8]:
    st.subheader("🗼 V12 — 80 sayılık kule ve 2–10 aile oluşum sırası")
    st.warning(
        "Önemli ayrım: Resmî 20 sayı bir kümedir; küçükten büyüğe yazılan "
        "sonuçlar topların makineden çıkma SIRASINI göstermez. Buradaki sıra, "
        "ailelerin ÖNCEKİ çekilişlerde hangi sırayla göründüğünü ve kulenin "
        "geçmiş sayılardan hangi sırayla kurulduğunu ifade eder."
    )
    st.caption(
        "80 sayılık merkez → her çekilişteki 20 sayı → o yirmilinin bütün "
        "2, 3, 4, 5, 6, 7, 8, 9, 10'lu alt aileleri → geçmiş 12 çekilişte "
        "tam görülmüş ailelerin zaman çizelgesi → önceki verilerle kurulan "
        "tahmin kulesi → rastgele 20 sayılık kontrol."
    )
    st.markdown("#### 📐 Her 20 sayıda teorik olarak kaç farklı aile var?")
    from math import comb as v12_comb
    v12_theoretical=[
        {"Aile boyutu":k,"Her 20 sayıda":v12_comb(20,k),
         "Tanım":"Tam alt aile (sonradan sayılır)"}
        for k in V12_SIZES
    ]
    st.dataframe(v12_theoretical,hide_index=True,use_container_width=True)
    st.caption(
        "Bu tablo 20 sayıyı gördükten sonra çıkarılan ailelerin sayısını gösterir. "
        "Her yirmili matematiksel olarak 2+3+4+5+6 parçalanabilir. "
        "Bunun kendisi gelecek çekilişi tahmin ettiğimiz anlamına gelmez."
    )

    st.markdown("#### 🔎 Tek bir gerçek çekilişi kulede incele")
    v12_day_sorted=v12_ready(day_draws)
    v12_positions=[r for r in v12_day_sorted if r["pos"]>12]
    if not v12_positions:
        st.info("İncelenecek günün en az 13. çekilişine kadar verisi gerekli.")
    else:
        v12_choice=st.selectbox(
            "İncelenecek çekiliş",
            options=list(range(len(v12_positions)))[::-1],
            format_func=lambda i:(
                f'#{v12_positions[i]["no"]} • '
                f'{v12_positions[i]["dt"][11:16]} • '
                f'günlük {v12_positions[i]["pos"]}. çekiliş'
            ),
            key="v12_actual_select")
        chosen_draw=v12_positions[v12_choice]
        v12_bypos={r["pos"]:r for r in v12_day_sorted}
        v12_previous=[v12_bypos.get(n)
                      for n in range(chosen_draw["pos"]-12,chosen_draw["pos"])]
        if any(r is None for r in v12_previous):
            st.info("Bu çekilişten önce 12 kesintisiz kayıt bulunmuyor. "
                    "Eksik veriden sıra çıkarmıyoruz.")
        else:
            with st.spinner("Gerçek 20 sayının alt aileleri taranıyor..."):
                v12_row,v12_data,v12_prior_guesses=v12_target_row(
                    chosen_draw,v12_previous,phase="Tek çekiliş",keep_detail=True
                )
            x,y,z=st.columns(3)
            x.metric("Gerçek sayı",20)
            y.metric("Geçmiş ailelerle kapsanan",
                     v12_data["covered"])
            z.metric("Kulenin önceden doğru sayısı",
                     v12_row["Ağ-kule"])
            st.write("**Gerçek çıkan 20 sayı:** "+
                     " · ".join(f"{n:02d}" for n in chosen_draw["nums"]))
            st.write("**Önceden kurulan ağ kulesindeki 20 sayı:** "+
                     " · ".join(f"{n:02d}"
                                for n in v12_prior_guesses["Ağ-kule"]))
            st.caption("Gerçek 20 sayıyla ortak çıkan sayılar, "
                       "sadece ÖNCEKİ 12 çekilişle oluşturulan kuleden sayıldı.")
            st.markdown("##### Aile boyutlarına göre gerçek geçmiş izleri")
            by_size=[
                {"Boyut":k,
                 "20 sayıda var olan alt aile":v12_comb(20,k),
                 "Önceki 12'de tam görülmüş":v12_data["counts"][k],
                 "Kulede k'lı öncü aile doğru":
                    str(v12_row[str(k)+"'li aile ortak"])+"/"+str(k)}
                for k in V12_SIZES
            ]
            st.dataframe(by_size,hide_index=True,use_container_width=True)
            st.markdown("##### 🧬 Bugünkü 20 sayı geçmiş 12 çekilişte nasıl birikti?")
            st.dataframe(v12_data["activation"],hide_index=True,
                         use_container_width=True)
            st.caption("Bu sıra, aynı 20 sayıyı geçmiş 12 çekilişte ilk "
                       "ne zaman gördüğümüzü ve 2–10'lu ailelerin hangi "
                       "önceki çekilişte ilk tam göründüğünü gösterir. "
                       "Bugünkü topların fiziksel çıkış sırası değildir.")
            st.markdown("##### ⏱️ Geçmişte görünmüş ailelerin sırası")
            if v12_data["witnessed"]:
                display_order=[
                    {"İlk geçmiş konum":r["prior_first"],
                     "Son geçmiş konum":r["prior_last"],
                     "Geçmişte kaç kez":r["prior_count"],
                     "Boyut":r["size"],
                     "Aile":"-".join(f"{n:02d}" for n in r["nums"])}
                    for r in v12_data["witnessed"]
                ]
                st.dataframe(display_order,hide_index=True,
                             use_container_width=True)
                st.caption(
                    "Geçmiş 12 çekilişin 1 numarası en eski, 12 numarası "
                    "en yenidir. Buradaki sıralama TOPLARIN bugünkü çıkma "
                    "sırası değil, ailelerin önceki çekilişlerde görünme sırasıdır."
                )
            else:
                st.info("Gerçek 20 sayının hiçbir ikili veya daha büyük "
                        "ailesi önceki 12 çekilişte tam görünmemiş.")
            if v12_data["uncovered"]:
                st.write("**Geçmiş ailelerden kapsanamayan sayılar:** "+
                         " – ".join(map(str,v12_data["uncovered"])))
            st.markdown("##### 🧩 Sonradan yapılabilen 20 sayı bölünmesi")
            st.dataframe([
                {"Aşama":i+1,"Boyut":len(g),
                 "Aile":"-".join(f"{n:02d}" for n in g)}
                for i,g in enumerate(v12_data["forced"])
            ],hide_index=True,use_container_width=True)
            st.caption(
                "Bu 2+3+4+5+6 bölünmesi bütün gerçek 20 sayıyı kaplar, "
                "ancak sonucu GÖRDÜKTEN SONRA kurulmuştur. "
                "Kupon başarısı olarak sayılmaz."
            )
            st.download_button(
                "⬇️ Seçilen çekilişin aile sırasını CSV indir",
                v12_csv(display_order if v12_data["witnessed"] else [
                    {"Sonuç":"Bu hedefin geçmiş 12'de tam görünen ailesi yok"}
                ]),
                file_name=f'V12_GECMIS_AILE_SIRASI_{chosen_draw["no"]}.csv',
                mime="text/csv",key="v12_download_audit"
            )

    st.markdown("#### 🧪 73 günlük kronolojik kule testi")
    v12_training_days=st.slider("İlk öğrenme / inceleme dönemi (gün)",
                                min_value=20,max_value=55,value=36,step=1,
                                key="v12_first_period")
    st.caption(
        "Bu testte 7–12. hedef çekilişleri için kule SADECE geçmiş 12×20 "
        "sayıdan kuruluyor. Her kule 20 sayı öneriyor. "
        "Öğrenme günlerinden sonra 20'de kaç sayı tuttuğu, 2–10 aile "
        "alt seviyeleri ve rastgele20 kontrolü ölçülüyor. "
        "Ayrıca 20 sayının önceki 12 çekilişte görülmüş kaç gerçek "
        "aileyle kapsandığı ve bunun tesadüfi beklentisi inceleniyor."
    )
    if st.button("🚀 V12 — 80 sayılık kuleyi tüm geçmişte test et",
                 key="v12_run",type="primary"):
        with st.spinner("Bütün 2–10 aileleri, geçmiş 12 çekilişteki kronolojik "
                        "görünüşleri ve 20 sayılık kuleler inceleniyor..."):
            v12_full_report=cached_v12_tower_study(
                json.dumps(draws,separators=(",",":")),v12_training_days
            )
        st.session_state["v12_report"]={
            "last_no":max((r["no"] for r in draws),default=0),
            "days":v12_training_days,"report":v12_full_report
        }
    v12_saved=st.session_state.get("v12_report")
    if v12_saved and v12_saved.get("days")==v12_training_days:
        report=v12_saved["report"]
        if v12_saved.get("last_no")!=max((r["no"] for r in draws),default=0):
            st.warning("Yeni çekiliş eklendi. Bu rapor bir önceki veri "
                       "sürümüne ait; testi tekrar çalıştır.")
        meta=report["meta"]
        a,b,c=st.columns(3)
        a.metric("Taranan gün",meta["days"])
        b.metric("Gerçek hedef çekiliş",meta["targets"])
        c.metric("Aile seviyeleri","2–10")
        st.markdown("##### 🎯 20 sayıyı önceden seçme başarısı")
        st.dataframe(report["methods"],hide_index=True,use_container_width=True)
        st.markdown("##### 🔁 Geçmişten bugüne taşınan aileler")
        st.dataframe(report["recurrent"],hide_index=True,use_container_width=True)
        st.caption(
            "Her aile boyutundaki geçmiş tekrar adedi, "
            "20/80 bağımsız çekilişte matematiksel olarak beklenen adetle "
            "karşılaştırılır. Sadece örüntü bulmak yetmez; "
            "tesadüften anlamlı biçimde ayrışmalıdır."
        )
        st.markdown("##### 🏗️ Ailelerin 12 adımlık ilk aktivasyon sırası")
        st.dataframe(report["number_first_order"],hide_index=True,
                     use_container_width=True)
        with st.expander("🔍 2–10 ailelerin hangi geçmiş adımda ilk tam göründüğü"):
            st.dataframe(report["family_first_order"],hide_index=True,
                         use_container_width=True)
        with st.expander("📍 Ailelerin önceki 12 çekilişteki son görünüş sırası"):
            st.dataframe(report["age_lags"],hide_index=True,
                         use_container_width=True)
        with st.expander("⏱️ Saatin 7–12 hedef sıralarının başarıları"):
            st.dataframe(report["slot_methods"],hide_index=True,
                         use_container_width=True)
        with st.expander("📚 Bütün hedeflerin 2–10 aile denetimi"):
            st.dataframe(report["ledger"][:150],hide_index=True,
                         use_container_width=True)
        downloads=(
            ("20 sayılık tüm önceden hedefler","ledger","V12_20_SAYI_TUM_HEDEFLER.csv"),
            ("2–10 aile geçmiş tekrarları","recurrent","V12_2_10_AILE_TEKRARLARI.csv"),
            ("Aile aktivasyon sırası","age_lags","V12_AILE_ZAMAN_SIRASI.csv"),
            ("2–10 ailelerin 12 adımda ilk görünüş sırası","family_first_order","V12_AILE_12_ADIM_OLUSUM.csv"),
            ("20 sayının 12 adımda ilk hareketi","number_first_order","V12_20_SAYI_12_ADIM_AKTIVASYON.csv"),
            ("Kule ve rastgele 20 isabeti","methods","V12_20_LI_KULE_PERFORMANSI.csv"),
            ("7–12 hedef saat karşılaştırması","slot_methods","V12_7_12_HEDEF_PERFORMANSI.csv")
        )
        for title_name,field,file_name in downloads:
            st.download_button(
                "⬇️ "+title_name,
                v12_csv(report[field]),
                file_name=file_name,mime="text/csv",
                key="v12_export_"+field
            )
    else:
        st.info("Kapsamlı test kullanıcı düğmesine basınca çalışır. "
                "Sonuçlar geldikten sonra bütün CSV'ler gösterilir.")

    st.markdown("#### 🔭 Gelecek çekiliş için 80 sayı kulesi")
    if analysis_date==today and day_draws:
        v12_ready_day=[r for r in day_draws
                       if datetime.fromisoformat(r["dt"])<=now_tr()]
        p=max((r["pos"] for r in v12_ready_day),default=0)+1
        due=moment(daystr,p) if p<=217 else None
        preview=None
        if due is not None and due>now_tr() and p not in known_pos:
            last_draw=max(v12_ready_day,key=lambda r:r["pos"]) if v12_ready_day else None
            forecast_no=last_draw["no"]+1 if last_draw else 0
            preview=v12_next_tower(v12_ready_day,forecast_no,p)
        if preview:
            st.write(f'**Hedef:** {due:%H:%M} — günlük {p}. çekiliş')
            st.write("**80 sayılık kulenin önerdiği 20:** " +
                     " – ".join(str(n) for n in preview["proposals"]["Ağ-kule"]))
            st.caption(
                "Aşağıdaki merdiven, önerilen ailelerin 2'li başlayıp "
                "3,4,5,6,7,8,9,10'luya kadar NASIL GENİŞLEDİĞİNİ gösterir. "
                "Bu bir tahmin KURULUŞ sırasıdır; resmî top sırası değildir."
            )
            st.dataframe(preview["stairs"],hide_index=True,use_container_width=True)
            st.markdown("##### 🧱 20 sayıyı kaplayan ayrık aile katları")
            st.dataframe(preview["composition"],hide_index=True,
                         use_container_width=True)
            st.markdown("##### 🌐 80 sayının 12 çekilişlik durumu")
            st.dataframe(preview["nodes"],hide_index=True,use_container_width=True)
            st.download_button(
                "⬇️ V12 sonraki hedef 80 sayı düğümleri",
                v12_csv(preview["nodes"]),
                file_name=f"V12_80_SAYI_KULE_{daystr}.csv",
                mime="text/csv",key="v12_live_nodes"
            )
            st.info("Bu seçenekler araştırma hedefleridir; kazanma garantisi "
                    "veya istatistiksel üstünlük iddiası yoktur. "
                    "Bu sekme otomatik bahis/kupon satın alma işlemi yapmaz.")
        else:
            st.info("Yeni hedef için henüz kesintisiz 12 çekilişlik geçmiş yok, "
                    "hedef saati geçti veya saatin 7–12 bölümünde değil.")
    else:
        st.caption("Canlı önizleme yalnız seçili gün bugünse çalışır.")


@st.cache_data(ttl=1800,show_spinner=False)
def cached_v13_training(draws_json,train_days):
    return v13_train(json.loads(draws_json),train_days=train_days)


@st.cache_data(ttl=1800,show_spinner=False)
def cached_v13_full_replay(draws_json,train_days):
    return v13_study(json.loads(draws_json),train_days=train_days)


with tabs[9]:
    st.subheader("🌡️ V13 — 217 çekilişlik hareketli sıcak / ılık / soğuk kule")
    st.caption(
        "Merkezde 1–80'in HER sayısı bulunur. Her günün 1. çekilişinden "
        "217. çekilişine kadar toplam görünüş, son 12, son 6, önceki 6, "
        "görünmeme aralığı, yükseliş, soğuma, tepe noktası hesaplanır. "
        "Bu V12'nin 2–10 aile kulesine bağlanır."
    )
    st.warning(
        "20 'koltuk' = sıcak / ılık / soğuk sayı sınıflarından çıkan kaç "
        "gerçek sayı olduğu; fiziksel makine çekiliş sırası değildir. "
        "Bağımsız çekilişte herhangi bir belirli sayının çıkış olasılığı "
        "%25'tir. Geçmiş sıcaklık, bundan sonra çıkacağını veya "
        "çıkmayacağını kanıtlamaz."
    )
    v13_train_days=st.slider(
        "Geçmiş kaç gün öğrenme için ayrı tutulsun?",
        min_value=20,max_value=50,value=36,step=1,
        key="v13_train_days")
    v13_count=Counter(d["day"] for d in draws)
    v13_complete_dates=[
        day for day in sorted(v13_count)
        if v13_count[day]>=215
    ]
    v13_training_dates=set(v13_complete_dates[:v13_train_days])
    v13_training_draws=[
        d for d in draws if d["day"] in v13_training_dates
    ]
    v13_trainee=None
    if len(v13_training_dates)==v13_train_days:
        v13_trainee=cached_v13_training(
            json.dumps(v13_training_draws,separators=(",",":")),
            v13_train_days
        )
    st.caption(
        f"İlk {v13_train_days} günün HEM sayıları hem sonuçları "
        "ile sıcaklık/koltuk eşikleri öğrenilir. Daha sonraki günler "
        "öğrenmeye katılmadan test edilir. Son 217 çekilişin hiçbir "
        "hedef sonucu, o hedefin öncesindeki duruma eklenmez."
    )
    st.markdown("#### 🧭 Gün boyunca 80 sayının kimliği")
    v13_day_known=[
        d for d in day_draws
        if analysis_date!=today or datetime.fromisoformat(d["dt"])<=now_tr()
    ]
    v13_day_known.sort(key=lambda r:r["pos"])
    identity=v13_states(v13_day_known)
    pool_counts=Counter(r["pool"] for r in identity)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Soğuk havuz",pool_counts["Soğuk"])
    c2.metric("Ilık havuz",pool_counts["Ilık"])
    c3.metric("Sıcak havuz",pool_counts["Sıcak"])
    c4.metric("İşlenen çekiliş",len(v13_day_known))
    st.caption("Kimlik tablosu incelenen günün son bilinen çekilişine "
               "kadarki değerlerdir. Sonuçları görmeden oluşmuştur.")
    v13_display=[
        {"Sayı":r["n"],"Havuz":r["pool"],"Hareket":r["label"],
         "Günde kaç kez":r["day"],"12'de":r["recent12"],
         "Son 6":r["recent6"],"Önceki 6":r["prev6"],
         "İvme":r["slope"],"Kaç çekiliştir yok":r["gap"],
         "Standart sıcaklık":r["z"]}
        for r in identity
    ]
    with st.expander("🌐 80 sayının ayrıntılı kimliklerini aç"):
        st.dataframe(v13_display,hide_index=True,use_container_width=True)
        st.download_button(
            "⬇️ 1–80 sayı gün içi kimlikleri",
            v13_csv(v13_display),file_name=f"V13_80_KIMLIK_{daystr}.csv",
            mime="text/csv",key="v13_identity_csv")
    st.markdown("#### 🔭 Gelecek çekilişin 20 koltuğu ve aile kulesi")
    v13_live=None
    if analysis_date==today and v13_day_known and v13_trainee:
        maxpos=max(r["pos"] for r in v13_day_known)
        next_pos=maxpos+1
        due=moment(daystr,next_pos) if next_pos<=217 else None
        future_key=next_pos not in {r["pos"] for r in day_draws}
        if due and due>now_tr() and future_key:
            v13_live=v13_preview(
                v13_day_known,v13_trainee,next_pos,
                max(v13_day_known,key=lambda r:r["pos"])["no"]+1
            )
    if v13_live:
        st.write(f'**Hedef:** {due:%H:%M} — '
                 f'{v13_live["pos"]}. çekiliş.')
        st.write("**Koltuk dağılımı (öngörü):** "+
                 " · ".join(f"{p}: {v13_live['seats'].get(p,0)}"
                            for p in V13_TYPES))
        st.caption(
            "Koltuk dağılımı geçmiş eğitim dönemindeki görünüş oranlarıyla "
            "kalibre edilir. Gerçek hedef 20'si bu seçimde kullanılmaz."
        )
        rows=[
            {"Yöntem":name,"Seçilen 20 sayı":"-".join(f"{n:02d}" for n in nums)}
            for name,nums in v13_live["coupons"].items()
        ]
        st.dataframe(rows,hide_index=True,use_container_width=True)
        st.markdown("##### 🎟️ V13 önceden sıralanmış aile kuponu")
        select_kind=st.selectbox(
            "20 sayıyı hangi yöntemle sıralayalım?",
            options=list(v13_live["coupons"]),
            key="v13_coupon_method"
        )
        select_size=st.selectbox(
            "İşleme alınacak aile boyutu",
            options=[6,7,8,9,10],index=0,
            format_func=lambda k:f"{k}'lı",
            key="v13_coupon_size"
        )
        # The first k are the predicted rank-order, never numeric order.
        v13_ticket_numbers=tuple(
            v13_live["coupons"][select_kind][:select_size]
        )
        v13_family_label="-".join(
            f"{n:02d}" for n in sorted(v13_ticket_numbers)
        )
        st.write("**Seçilen aile:** "+
                 " – ".join(f"{n:02d}" for n in v13_ticket_numbers))
        st.caption(
            f"Hedef çekiliş: {due:%H:%M}; {select_kind} metodunun "
            "çekilişten önceki sıralamasında ilk "
            f"{select_size} sayı kullanıldı. Bu seçimin "
            "kazandıracağı gösterilmiş değildir."
        )
        if st.button("🎟️ V13 deneysel aile kuponunu kaydet",
                     key="v13_save_family"):
            if due<=now_tr():
                st.warning("Hedef saati geçti; artık kupon kaydedilemez.")
            else:
                ticket={
                    "day":daystr,"pos":v13_live["pos"],
                    "time":due.strftime("%H:%M"),
                    "family":v13_family_label,
                    "numbers":list(sorted(v13_ticket_numbers)),
                    "size":select_size,
                    "kind":"🗼 V13 "+select_kind,
                    "trigger_no":max(v13_day_known,
                                     key=lambda r:r["pos"])["no"],
                    "created_at":now_tr().isoformat(timespec="seconds")
                }
                keys={(x["day"],x["pos"],x["family"])
                      for x in st.session_state.v10_tickets}
                if (ticket["day"],ticket["pos"],ticket["family"]) in keys:
                    st.info("Bu hedef ve aile daha önce kaydedilmiş.")
                else:
                    st.session_state.v10_tickets.append(ticket)
                    st.success("Deneysel V13 kuponu kaydedildi. "+auto_save())
        st.markdown("##### 🧱 V12 ile birleşen 2–10 aile merdiveni")
        st.dataframe(v13_live["stairs"],hide_index=True,use_container_width=True)
        st.markdown("##### 20 sayıyı dolduran ayrık aileler (2+3+4+5+6)")
        st.dataframe(v13_live["groups"],hide_index=True,use_container_width=True)
        st.download_button("⬇️ V13 canlı 80 sayı ve eğitim oranı",
                           v13_csv(v13_live["states"]),
                           file_name=f"V13_CANLI_{daystr}.csv",
                           mime="text/csv",key="v13_live_csv")
        st.info(
            "Bu bir araştırma önerisidir; isabet üstünlüğü "
            "kanıtlanmış otomatik bahis motoru değildir."
        )
    else:
        st.info(
            "Güncel hedef için 217 günlük sırada kayıtlı olmayan ve "
            "saati geçmemiş yeni bir çekiliş gerekli. "
            "Canlı veri güncellemesiyle yeniden kontrol et."
        )
    st.markdown("#### 🧪 İlk günlerden öğren → sonraki 37 günde sınama")
    st.caption(
        "Bütün 217 günlük slot izlenir. Ana koltuk motorları bütün hedeflerde, "
        "V12 aile ağı ise kesintisiz önceki 12 çekilişi olan 7–12. "
        "saat slotlarında ayrıca test edilir. "
        "Tam isabet olmayan kuponlar da sonuç defterinde kalır."
    )
    if st.button("🚀 V13 — 217 çekilişli havuz ve aile motorunu test et",
                 key="v13_start_backtest",type="primary"):
        with st.spinner("217 slot × 80 sayı, 2–10 aile, koltuklar ve "
                        "V12 ağ kulesi; geçmişi görmeden test ediliyor..."):
            tested=cached_v13_full_replay(
                json.dumps(draws,separators=(",",":")),
                v13_train_days
            )
        st.session_state["v13_backtest"]={
            "last_no":max((r["no"] for r in draws),default=0),
            "train":v13_train_days,"result":tested
        }
    saved=st.session_state.get("v13_backtest",{})
    if saved.get("train")==v13_train_days:
        report=saved["result"]
        meta=report["meta"]
        if saved.get("last_no")!=max((r["no"] for r in draws),default=0):
            st.warning("Yeni çekiliş eklendi. Yeni veri için testi tekrar çalıştır.")
        a,b,c=st.columns(3)
        a.metric("Eğitim günü",meta["train_days"])
        b.metric("Ayrı test günü",meta["holdout_days"])
        c.metric("Test hedefi",meta["test_targets"])
        st.caption(
            f'Test: {meta["test_first"]} – {meta["test_last"]}. '
            "Kategorilerin öğrenildiği günlerin sonuçları test başarı "
            "oranına eklenmedi. Bütün rapor keşif amaçlıdır; "
            "gerçek ileri tarihli kör kayıt ayrıca gereklidir."
        )
        st.markdown("##### 🎯 Koltuk motoru ve rastgele 20 isabeti")
        st.dataframe(report["methods"],hide_index=True,use_container_width=True)
        st.markdown("##### 🪑 Hedef 20'nin sıcak / ılık / soğuk koltukları")
        st.dataframe(report["seats"],hide_index=True,use_container_width=True)
        st.markdown("##### ✅ 20 sıcak / ılık / soğuk koltuğun TAM dağılımı")
        st.dataframe(report["seat_exact"],hide_index=True,
                     use_container_width=True)
        st.caption("Bir çekilişteki 20 sayının soğuk/ılık/sıcak grup sayıları "
                   "ayrı ayrı tam tutmuşsa başarı olarak yazılır. "
                   "Rastgele beklenen değer, mevcut havuz büyüklüklerine göre "
                   "hesaplanan kesin çok değişkenli hipergeometrik olasılıktır.")
        st.markdown("##### 📈 Tepeye çıkan ve soğuktan uyanan sayılar")
        st.dataframe(report["states"],hide_index=True,use_container_width=True)
        st.markdown("##### 🎯 2–10 aile kulesinin gerçek isabeti")
        st.dataframe(report["nested"],hide_index=True,
                     use_container_width=True)
        st.caption("Ailenin sayıları kupondaki öncelik sırasından, "
                   "hedef sonucundan ÖNCE sabitlenir. Tam isabet ve "
                   "0/k..k/k dağılımı ayrı gösterilir.")
        st.markdown("##### 👨‍👩‍👧‍👦 Tamamen soğuk veya tamamen sıcak aileler")
        st.caption(
            "Aynı havuzdan seçilmiş bir ailenin önceden kurulmuş "
            "tek k'lı adayının kaç hedefte TAM k/k göründüğü yazılır. "
            "Her gruptaki bütün k'lı ailelerin SONRADAN sayılan "
            "tamamlanmaları ayrıdır; kupon isabeti olarak gösterilmez."
        )
        st.dataframe(report["family"],hide_index=True,use_container_width=True)
        cold6=next((r for r in report["family"]
                    if r["Grup"]=="Soğuk" and r["Boyut"]==6),None)
        if cold6:
            x,y=st.columns(2)
            x.metric("Soğuk 6'lı hedef",cold6["Tek aile hedefi"])
            y.metric("Tam 6/6",cold6["Tam k/k"])
        with st.expander("⏱️ Bütün gün boyunca hedef / koltuk / kupon isabeti"):
            st.dataframe(report["ledger"][:200],hide_index=True,
                         use_container_width=True)
        downloadable=(
            ("217 çekiliş boyunca tüm hedefler","ledger","V13_TUM_HEDEFLER.csv"),
            ("Koltuk tahmini ve 20 sayılık isabet","methods","V13_KUPON_PERFORMANSI.csv"),
            ("20 havuz koltuğu ve beklenen sayı","seats","V13_KOLTUK_DAGILIMI.csv"),
            ("20 koltuğun tam doluş isabeti","seat_exact","V13_TAM_KOLTUK_KONTROL.csv"),
            ("Sıcak tepe / soğuk uyanma sonuçları","states","V13_SICAKLIK_DURUMU.csv"),
            ("2–10 iç içe aile öncü başarıları","nested","V13_2_10_AILE_KULE_ISABET.csv"),
            ("2–10 tamamen soğuk/sıcak aile testleri","family","V13_AILE_SOĞUK_SICAK.csv"),
            ("Örnek 20 sayı / aile dağılımı","examples","V13_KULE_ORNEKLER.csv"),
            ("Örnek bireysel aile hedefleri","family_examples","V13_AILE_HEDEF_ORNEKLER.csv")
        )
        for title_name,field,file_name in downloadable:
            st.download_button("⬇️ "+title_name,v13_csv(report[field]),
                               file_name=file_name,mime="text/csv",
                               key="v13_export_"+field)
    else:
        st.caption("Test henüz çalıştırılmadı. Yukarıdaki 🚀 düğmesine bas.")


@st.cache_data(ttl=1800,show_spinner=False)
def v14_cached_history_replay(draws_json,first_days):
    return v14_replay(json.loads(draws_json),train_days=first_days)


with tabs[10]:
    st.subheader("🔄 V14 — 217 çekilişte 80 sayılık zaman ve geçiş ağı")
    st.caption(
        "80×80 sayı ilişkisi; +1/+2/+3/+6/+12 çekiliş gecikmeleri; "
        "önceki 20'den kalan, ayrılan ve yeni giren sayılar. "
        "Günün 217 çekilişi saat ve ilk-altı / son-altı olarak incelenir. "
        "V12 aile kulesi ve V13 sıcaklık koltuklarıyla aynı hedefte kıyaslanır."
    )
    st.warning(
        "Hızlı On sonucundaki 20 sayı sıralı toplar değil, bir kümedir. "
        "23'ün 58'e fiziksel olarak yerini bıraktığı iddia edilemez. "
        "A→B yalnız istatistiksel birlikte-geçiş gözlemidir. "
        "Adil çekilişte tek sayının gelecek çekilişte çıkma olasılığı %25'tir."
    )
    st.markdown("#### 🔎 İki gerçek çekiliş arasındaki ayrılan / yeni gelen sayılar")
    v14_positions={r["pos"]:r for r in day_draws}
    v14_comparisons=[
        r for r in sorted(day_draws,key=lambda x:x["pos"],reverse=True)
        if r["pos"]-1 in v14_positions
    ]
    if v14_comparisons:
        chosen=st.selectbox(
            "Karşılaştırılacak hedef",
            list(range(len(v14_comparisons))),
            format_func=lambda i:(
                f'#{v14_comparisons[i]["no"]} — '
                f'{v14_comparisons[i]["dt"][11:16]} ('
                f'{v14_comparisons[i]["pos"]}. çekiliş)'
            ),
            key="v14_pair_draw_select"
        )
        target=v14_comparisons[chosen]
        prev=v14_positions[target["pos"]-1]
        pset=set(prev["nums"]);tset=set(target["nums"])
        retained=sorted(pset&tset)
        departed=sorted(pset-tset)
        arrived=sorted(tset-pset)
        a,b,c=st.columns(3)
        a.metric("Aynı kalan",len(retained))
        b.metric("Ayrılan",len(departed))
        c.metric("Yeni gelen",len(arrived))
        st.write("**Aynı kalan:** "+", ".join(map(str,retained)))
        st.write("**Ayrılan:** "+", ".join(map(str,departed)))
        st.write("**Yeni gelen:** "+", ".join(map(str,arrived)))
        st.caption(
            "Ayrılan ve yeni gelenler, bire bir fiziksel değişim çifti "
            "değildir. Bu tek çekilişin SONRADAN yapılan betimsel analizidir."
        )
    else:
        st.info("Bu gün kesintisiz en az iki gerçek çekiliş gerekli.")

    firstdays=st.slider(
        "İlk kaç günle geçiş ağı öğrenilsin?",
        min_value=20,max_value=50,value=36,step=1,
        key="v14_train_days"
    )
    st.markdown("#### 🧪 217 hedef sırası ve sonradan görmeden kontrol")
    st.caption(
        "İlk günler yalnız eğitim verisi olur. Sonraki günler öğrenmeye "
        "dahil edilmez. Geçiş ağının sayı seçimi; rastgele20, "
        "V13 sıcaklık ve uygun 7–12 hedeflerinde V12 ile karşılaştırılır. "
        "80×80 ilişkiler arasından geçmişte en güçlü görünenlerin "
        "yeni günlerde de aynı performansı verip vermediği ayrıca ölçülür."
    )
    if st.button("🚀 V14 — 73 günde 217 sıralı geçiş ağını test et",
                 key="v14_run_full",type="primary"):
        with st.spinner(
            "80×80 geçişler ve beş gecikme; 217 günlük sıra; "
            "V12/V13 karşılaştırması. Analiz tamamlanana kadar bekle..."
        ):
            result=v14_cached_history_replay(
                json.dumps(draws,separators=(",",":")),firstdays
            )
        st.session_state["v14_results"]={
            "nmax":max((r["no"] for r in draws),default=0),
            "firstdays":firstdays,"data":result
        }
    saved=st.session_state.get("v14_results",{})
    if saved.get("firstdays")==firstdays:
        r=saved["data"];meta=r["meta"]
        if saved.get("nmax")!=max((z["no"] for z in draws),default=0):
            st.warning("Veri dosyasına yeni çekilişler gelmiş. "
                       "Son rapor eski sürüme ait olabilir.")
        k1,k2,k3=st.columns(3)
        k1.metric("Eğitim günü",meta["train_days"])
        k2.metric("Ayrı test günü",meta["holdout_days"])
        k3.metric("Değişim hedefi",meta["test_transitions"])
        st.caption(
            f'Test dönemi: {meta["first_test"]} – {meta["last_test"]}. '
            "Günün ilk çekilişi için aynı güne ait önceki çekiliş "
            "olmadığından değişim hesabı yapılamaz."
        )
        st.markdown("##### 🎯 Ağ motoru ile rastgele sayı kıyaslaması")
        st.dataframe(r["methods"],hide_index=True,use_container_width=True)
        st.markdown("##### 📏 Rastgele kontrolüne göre gün bazında fark")
        st.dataframe(r["paired"],hide_index=True,use_container_width=True)
        st.caption(
            "Bu güven aralıkları keşif amaçlıdır. Çok sayıda sayı çifti "
            "ve yöntem denendiğinden rastlantısal üstünlükler oluşabilir."
        )
        st.markdown("##### 🕒 217 pozisyon ve saat grupları")
        st.dataframe(r["times"],hide_index=True,use_container_width=True)
        with st.expander("Her saatin ilk 6 / son 6 sayı hareketi"):
            st.dataframe(r["half_hours"],hide_index=True,
                         use_container_width=True)
        with st.expander("217 çekiliş sırası tek tek"):
            st.dataframe(r["positions"],hide_index=True,
                         use_container_width=True)
        st.markdown("##### 🔎 Hangi A'dan sonra hangi B?")
        st.caption(
            "Bu listedeki çiftler İLK eğitim günlerinde seçildi. "
            "Listede her sayı için koşullu çıkış oranı ve SONRAKİ test "
            "günlerindeki gerçek oran ayrı gösterilir. "
            "A ayrılırsa B'nin gelmesi şartlı olarak yaklaşık %25,316 "
            "beklenir; fakat bu koşul hedef öncesinde bilinmez."
        )
        st.dataframe(r["pairs"],hide_index=True,use_container_width=True)
        st.markdown("##### 📥 İndirilebilir araştırma raporları")
        downloads=(
            ("217 sıra — bütün değişimler ve kupon isabetleri",
             "ledger","V14_217_HEDEF_DEFTERI.csv"),
            ("Saatlik 20 sayı değişim dağılımı",
             "times","V14_SAATLIK_GECIS.csv"),
            ("217 pozisyon ayrı ortalama",
             "positions","V14_217_SIRA_ANALIZ.csv"),
            ("Saat ilk 6 / son 6 değişim",
             "half_hours","V14_SAAT_YARIMLARI.csv"),
            ("80x80 arasından eğitimde seçilen ilişki ve kör test",
             "pairs","V14_SAYI_GECIS_ILISKILERI.csv"),
            ("Kupon yöntemleri isabet karşılaştırması",
             "methods","V14_KUPON_PERFORMANSI.csv"),
            ("Rastgeleye karşı günlük eşli karşılaştırma",
             "paired","V14_KARSILASTIRMA.csv")
        )
        for label,key,path in downloads:
            st.download_button(
                "⬇️ "+label,
                v14_csv(r[key]),file_name=path,mime="text/csv",
                key="v14_export_"+key
            )
    else:
        st.info("Geniş V14 analizi henüz çalıştırılmadı. "
                "Önce 🚀 düğmesine bas.")

    st.markdown("#### 🔭 V14 — gelecek çekiliş adayları")
    if saved.get("firstdays")==firstdays and analysis_date==today and day_draws:
        ready=[
            d for d in day_draws
            if datetime.fromisoformat(d["dt"])<=now_tr()
        ]
        next_pos=max((r["pos"] for r in ready),default=0)+1
        due=moment(daystr,next_pos) if 2<=next_pos<=217 else None
        forecast=None
        if (due is not None and due>now_tr()
            and next_pos not in {r["pos"] for r in day_draws}):
            forecast=v14_preview(
                ready,saved["data"]["model"],saved["data"]["v13_model"],
                next_pos,max((r["no"] for r in ready),default=0)+1
            )
        if forecast:
            st.write(f'**Sıradaki hedef:** {due:%H:%M} — '
                     f'{forecast["pos"]}. çekiliş')
            st.dataframe([
                {"Yöntem":name,"20 aday":", ".join(map(str,nums))}
                for name,nums in forecast["predictions"].items()
            ],hide_index=True,use_container_width=True)
            with st.expander("1–80 sayının geçiş ağı puanı"):
                st.dataframe(forecast["nodes"],hide_index=True,
                             use_container_width=True)
            st.download_button(
                "⬇️ Güncel 80 sayı geçiş puanları",
                v14_csv(forecast["nodes"]),
                file_name=f"V14_CANLI_80_{daystr}.csv",
                mime="text/csv",key="v14_live_export"
            )
            st.info("Bu sonuçlar henüz kanıtlanmış kupon üstünlüğü değildir.")
        else:
            st.caption("Şu an geçmiş kayıtları tam ve saati gelmemiş "
                       "bir sonraki hedef yok.")
    else:
        st.caption("Canlı hedefi görmek için V14'ün tarihsel testini "
                   "çalıştır ve bugünün verilerini seç.")


@st.cache_data(ttl=3600,show_spinner=False)
def v15_cached_fit(training_json,n_days):
    return v15_fit(json.loads(training_json),train_days=n_days)


@st.cache_data(ttl=3600,show_spinner=False)
def v15_cached_replay(all_draws_json,n_days,wide):
    return v15_backtest(json.loads(all_draws_json),train_days=n_days,
                        coverage=wide)


with tabs[11]:
    st.subheader("🎟️ V15 — 6 kupon × 10 sayı | 2–10 aile merdiveni")
    st.caption(
        "Her uygun 7–12. hedef çekilişine, 12 önceki çekilişin 240 sayısı "
        "ve 217'lik gün kimliğinden ALTİ farklı 10'lu kupon oluşturur. "
        "V12 aile ağı + V13 sıcaklık koltukları + V14 geçiş sırası birleşir. "
        "Her kuponun 2'li–10'lu ilk aileleri hedef öncesinden sabitlenir."
    )
    st.warning(
        "Daha çok kupon daha çok kazanma garantisi değildir; "
        "altı model kuponu her hedefte altı rastgele 10'lu ile karşılaştırılır. "
        "Motorun doğrulanmış RNG avantajı bulunmamaktadır. "
        "Geçmiş veriye bakarak strateji tasarlanması nedeniyle "
        "37 günlük ayrılmış dönem tam canlı kör test sayılmaz."
    )
    v15_mode=st.radio(
        "Kupon dağıtım biçimi",
        options=["Aile odaklı", "Geniş kapsama"],
        index=1,horizontal=True,key="v15_mode_select"
    )
    v15_wide=v15_mode=="Geniş kapsama"
    st.caption(
        "Geniş kapsama: İlk kupondan sonra her 10'lu kupon en az "
        "7 yeni sayı taşır. Böylece altı kupon daha fazla farklı "
        "sayıyı hedefler. Bu seçenek eski test sonuçları görüldükten "
        "sonra tasarlandığı için geçmiş sınaması keşif amaçlıdır."
    )
    st.markdown("#### 🧪 İlk 36 gün eğitim — sonraki 37 gün kupon testi")
    if st.button("🚀 V15 6×10 aileli kupon performansını test et",
                 type="primary",key="v15_run_test"):
        with st.spinner(
            "73 gün; 7–12. hedeflere altı model + altı rastgele "
            "kupon; 2–10 ailelerin her biri hesaplanıyor..."
        ):
            v15_report=v15_cached_replay(
                json.dumps(draws,separators=(",",":")),36,v15_wide
            )
        st.session_state["v15_test_report"]={
            "nmax":max((r["no"] for r in draws),default=0),
            "mode":v15_mode,
            "result":v15_report
        }
    v15_report_saved=st.session_state.get("v15_test_report")
    if v15_report_saved and v15_report_saved.get("mode")==v15_mode:
        rr=v15_report_saved["result"];mm=rr["summary"]
        if v15_report_saved.get("nmax")!=max((r["no"] for r in draws),default=0):
            st.warning("Yeni çekiliş geldi. Bu sonuç raporu önceki veri "
                       "sürümüne aittir; düğmeyle yeniden test edebilirsin.")
        a,b,c=st.columns(3)
        a.metric("Ayrı test günü",mm["test_days"])
        b.metric("Hedef çekiliş",mm["targets"])
        c.metric("Karşılaştırılan kupon",mm["coupons"])
        st.caption(
            "Her hedefte 6 motor ve 6 rastgele kontrol = 12 kupon. "
            "Hiçbir başarısız kupon atılmaz. "
            "Her k'lı ailenin ilk k sayısı sonuç gelmeden bellidir."
        )
        cover1,cover2=st.columns(2)
        cover1.metric("Motor: altı kupon farklı sayı",
                      mm["model_coverage"])
        cover2.metric("Rastgele: altı kupon farklı sayı",
                      mm["random_coverage"])
        st.markdown("##### 🎯 10'lu kuponlar: 0/10–10/10 gerçek sonuç")
        st.dataframe(rr["methods"],hide_index=True,use_container_width=True)
        st.markdown("##### 🏆 Altı kupondan en iyisi — rastgele kontrol")
        st.dataframe(rr["best6"],hide_index=True,use_container_width=True)
        x,y=st.columns(2)
        x.metric("Önceden seçilmiş 6'lı tam",
                 mm["model_6_full"])
        y.metric("Rastgele 6'lı tam",mm["random_6_full"])
        st.caption(
            "Aile 6/6 için yalnız kupon hazırlanırken belirlenmiş "
            "ilk 6 sayı sayılır. Sonradan tutan bir 10'lunun "
            "içinden 6 sayı seçmek tahmin başarısı değildir."
        )
        with st.expander("🧬 Her motorun 2'li–10'lu aile başarısı"):
            selected_size=st.select_slider(
                "Aile boyutu",options=list(V15_SIZES),value=6,
                key="v15_family_size"
            )
            st.dataframe(
                [x for x in rr["families"]
                 if x["Aile boyutu"]==selected_size],
                hide_index=True,use_container_width=True
            )
        with st.expander("⌚ Her hedefte altı model / altı rastgele sonuç"):
            st.dataframe(rr["differences"][:200],
                         hide_index=True,use_container_width=True)
        for title_name,key,filename in (
            ("Her kupon ve 6'lı aile isabeti","ledger","V15_KUPONLAR_VE_ISABETLER.csv"),
            ("Altı kupondan en iyi sonuçlar","differences","V15_HEDEF_BAZINDA_KIYAS.csv"),
            ("0–10 tam isabet dağılımı","methods","V15_10_LU_ISABET_DAGILIMI.csv"),
            ("2–10 ailelerin tam isabetleri","families","V15_AILELER_2_10.csv"),
            ("6 model / 6 rastgele en iyisi","best6","V15_EN_IYI_ALTI_KUPON.csv"),
        ):
            st.download_button(
                "⬇️ "+title_name,v15_csv(rr[key]),file_name=filename,
                mime="text/csv",key="v15_dl_"+key
            )
    else:
        st.info("Geçmişe yönelik test için yukarıdaki 🚀 düğmesine bas. "
                "Canlı kupon için aşağıdaki ayrı düğmeyi kullan.")

    st.markdown("#### 🔭 Gelecek çekilişin altı 10'lu kuponunu hazırla")
    v15_pending=None
    if analysis_date==today:
        v15_day_known=[
            r for r in day_draws
            if datetime.fromisoformat(r["dt"])<=now_tr()
        ]
        v15_day_known.sort(key=lambda r:r["pos"])
        v15_pos=max((r["pos"] for r in v15_day_known),default=0)+1
        v15_due=moment(daystr,v15_pos) if v15_pos<=217 else None
        v15_target_no=(
            max(v15_day_known,key=lambda r:r["pos"])["no"]+1
            if v15_day_known else None
        )
        v15_pending=(v15_due is not None and v15_due>now_tr()
                     and v15_pos not in {r["pos"] for r in day_draws}
                     and hour_draw_index(v15_pos) in (7,8,9,10,11,12)
                     and v15_target_no is not None
                     and all(v15_pos-i in {r["pos"] for r in v15_day_known}
                             for i in range(1,13)))
    if v15_pending:
        st.write(f"**Hedef:** {v15_due:%H:%M} — "
                 f"{v15_pos}. çekiliş (tahmini #{v15_target_no})")
        if st.button(
            "🎟️ V15 — Bu hedefe altı 10'lu kupon üret",
            type="primary",key="v15_generate_six"
        ):
            earlier_days=sorted({r["day"] for r in draws if r["day"]<daystr})
            if len(earlier_days)<36:
                st.error("İlk 36 eğitim günü henüz yok.")
            else:
                train_days=set(earlier_days[:36])
                first36=[r for r in draws if r["day"] in train_days]
                with st.spinner("Geçmiş günleri öğrenip V12/V13/V14 "
                                "ailelerini hedef gelmeden seçiyorum..."):
                    models=v15_cached_fit(
                        json.dumps(first36,separators=(",",":")),36
                    )
                    tickets=v15_six(
                        v15_day_known,v15_pos,v15_target_no,models,
                        coverage=v15_wide
                    )
                st.session_state["v15_live_tickets"]={
                    "day":daystr,"pos":v15_pos,"mode":v15_mode,
                    "trigger":v15_day_known[-1]["no"],
                    "target_no":v15_target_no,
                    "generated_at":now_tr().isoformat(timespec="seconds"),
                    "tickets":tickets
                }
        v15_frozen=st.session_state.get("v15_live_tickets",{})
        if (v15_frozen.get("day")==daystr
            and v15_frozen.get("mode")==v15_mode
            and v15_frozen.get("pos")==v15_pos
            and v15_frozen.get("trigger")==v15_day_known[-1]["no"]
            and v15_due>now_tr()):
            st.markdown("##### ✅ Çekilişten önce sabitlenen altı kupon")
            st.metric(
                "Altı kuponun kapsadığı farklı sayı",
                len({n for t in v15_frozen["tickets"]
                     for n in t["numbers"]})
            )
            v15_table=[
                {"No":i+1,"Motor":ticket["method"],
                 "10 sayı":" – ".join(
                     f"{n:02d}" for n in sorted(ticket["numbers"])
                 ),"6'lı aile":" – ".join(
                     f"{n:02d}" for n in sorted(ticket["family6"])
                 )}
                for i,ticket in enumerate(v15_frozen["tickets"])
            ]
            st.dataframe(v15_table,hide_index=True,use_container_width=True)
            pick=st.selectbox(
                "2–10 aile merdivenini aç",
                options=list(range(6)),
                format_func=lambda i:(
                    f'{i+1}. kupon — {v15_frozen["tickets"][i]["method"]}'
                ),
                key="v15_pick_family"
            )
            vals=v15_frozen["tickets"][pick]["numbers"]
            st.dataframe([
                {"Boyut":k,
                 "Çekilişten önce seçilmiş aile":
                    " – ".join(f"{n:02d}" for n in sorted(vals[:k]))}
                for k in V15_SIZES
            ],hide_index=True,use_container_width=True)
            st.download_button(
                "⬇️ Altı 10'lu kuponu CSV indir",
                v15_csv(v15_table),
                file_name=f"V15_6_KUPON_{daystr}_{v15_pos}.csv",
                mime="text/csv",key="v15_download_six"
            )
            if not st.session_state.get("v10_admin_unlocked",False):
                st.info(
                    "Kuponları GitHub'a kalıcı kaydetmek için önce "
                    "💾 Yedek & Kayıt bölümündeki yönetici PIN kilidini aç."
                )
            if st.button("💾 Hedef geçmeden altı kuponu kalıcı kaydet",
                         key="v15_save_six",type="primary",
                         disabled=not st.session_state.get(
                             "v10_admin_unlocked",False)):
                if v15_due<=now_tr() or v15_pos in {
                    r["pos"] for r in day_draws
                }:
                    st.error("Hedef çekiliş saati geldi veya geçti. "
                             "Sonuç göründükten sonra kupon kaydetmiyoruz.")
                else:
                    earlier_keys={
                        (x["day"],x["pos"],x["family"])
                        for x in st.session_state.v10_tickets
                    }
                    created=0
                    for ticket in v15_frozen["tickets"]:
                        nums=sorted(ticket["numbers"])
                        family="-".join(f"{n:02d}" for n in nums)
                        ticket_key=(daystr,v15_pos,family)
                        if ticket_key in earlier_keys:
                            continue
                        st.session_state.v10_tickets.append({
                            "day":daystr,"pos":v15_pos,
                            "time":v15_due.strftime("%H:%M"),
                            "family":family,
                            "numbers":nums,
                            "size":10,
                            "kind":"V15 "+v15_mode+" "+ticket["method"],
                            "trigger_no":v15_frozen["trigger"],
                            "created_at":now_tr().isoformat(timespec="seconds")
                        })
                        earlier_keys.add(ticket_key)
                        created+=1
                    response=auto_save()
                    if response.startswith("GitHub kalici kaydi"):
                        st.success(f"{created} adet 10'lu hedef kupon "
                                   "GitHub'a kaydedildi. "
                                   "İsabet bölümünde sonuçları izleyebilirsin.")
                    else:
                        st.warning(
                            f"{created} kupon oturuma eklendi ama kalıcı "
                            "GitHub kaydı doğrulanamadı: "+response
                        )
        else:
            st.caption("Bu hedef için henüz altı kupon üretilmedi. "
                       "Hedef saati geçmeden yukarıdaki düğmeye bas.")
    else:
        st.info("Canlı kupon yalnız bugünkü, henüz gerçekleşmemiş "
                "7–12. hedef çekilişi ve kesintisiz önceki 12 çekiliş "
                "mevcutsa üretilir. Sonuç gelmiş çekiliş için "
                "sonradan kupon yazılmaz.")


@st.cache_data(ttl=1800,show_spinner=False)
def v16_cached_rnd_study(data_json,train_days=36):
    return v16_analyze(json.loads(data_json),train_days=train_days)


with tabs[12]:
    st.subheader("🎲 V16 — RNG Salınımı ve 217 çekilişin gerçek sınaması")
    st.caption(
        "Bir 20'likten sonraki 20'liye kaç sayı taşınıyor? "
        "2, 5, 12 ve diğer bütün salınımların gerçek sıklığı, "
        "teorik 20/80 dağılımıyla ve sonraki 37 günün sonuçlarıyla "
        "karşılaştırılır."
    )
    st.warning(
        "Sayı kümesinin salınımı tek başına gizli RNG algoritmasını veya "
        "tohumunu ortaya çıkarmaz. Bu sekme yalnız adil, bağımsız çekiliş "
        "modelinden sapma ve önceden tahmin gücü olup olmadığını ölçer."
    )
    st.markdown("#### ⚖️ Değişmez matematiksel kontrol")
    st.write(
        "**Bağımsız çekiliş beklentisi:** 5 tekrar; "
        "standart sapma yaklaşık 1,688. "
        "12 veya daha fazla sayının tekrarının yaklaşık "
        "10.000 geçişte bir görülmesi beklenir."
    )
    if st.button("🔬 V16 — 73 gün RNG salınım testini çalıştır",
                 type="primary",key="v16_go"):
        with st.spinner("73 gün × 217 sıra: tekrar sayıları, saat, "
                        "uç salınımlar ve eğitim/test karşılaştırması..."):
            result=v16_cached_rnd_study(
                json.dumps(draws,separators=(",",":")),36
            )
        st.session_state["v16_audit"]={
            "max_no":max((d["no"] for d in draws),default=0),
            "result":result
        }
    saved=st.session_state.get("v16_audit")
    if saved:
        if saved["max_no"]!=max((d["no"] for d in draws),default=0):
            st.info("Yeni çekilişler geldi. V16'yı güncel dosya için yeniden çalıştır.")
        result=saved["result"]
        meta=result["meta"]
        x,y,z=st.columns(3)
        x.metric("Gerçek 5 dakika geçişi",meta["n_transitions"])
        y.metric("Ortalama aynı sayı",meta["mean_overlap"])
        z.metric("12+ tekrar",f'{meta["observed_12plus"]} / ~{meta["expected_12plus"]}')
        st.caption(
            "01:02–07:02 arasındaki altı saatlik ara, beş dakika geçişi "
            "sayılmaz. Eksik kayıtlar atlanır. Günün son eksik "
            "günü tam günlük analizden çıkarılır."
        )
        st.markdown("##### 📊 Bütün tekrar sayılarının gerçek / teorik dağılımı")
        st.dataframe(result["distribution"],hide_index=True,
                     use_container_width=True)
        st.markdown("##### 🧪 Dağılımın RNG modeline uygunluk testi")
        st.metric(
            "Ki-kare p değeri",
            f'{meta["chi_square_p"]:.4f}'
        )
        st.caption(
            f'10 önceden belirlenmiş dilim; {meta["degrees_freedom"]} '
            "serbestlik derecesi. P değerinin büyük olması "
            "RNG'nin algoritmasının bulunduğu anlamına gelmez."
        )
        st.dataframe(result["pooled_distribution"],hide_index=True,
                     use_container_width=True)
        st.markdown("##### 🔮 Sonraki çekilişin tekrar miktarı tahmin edilebiliyor mu?")
        st.caption(
            "İlk 36 günün önceki tekrarına bakarak öğrenilen model, "
            "sonraki 37 gündeki 7.881 üçlü çekiliş dizisinde "
            "kör biçimde sabit teorik RNG beklentisiyle karşılaştırılır. "
            "Log-kayıp ve hata KÜÇÜK olan daha iyidir."
        )
        st.dataframe(result["forecast"],hide_index=True,
                     use_container_width=True)
        st.markdown("##### ↔️ Büyük/küçük salınımdan sonra ne oldu?")
        st.dataframe(result["conditional"],hide_index=True,
                     use_container_width=True)
        st.markdown("##### 🕒 Hangi saat ve yarı farklı?")
        st.dataframe(result["hour"],hide_index=True,
                     use_container_width=True)
        st.dataframe(result["halves"],hide_index=True,
                     use_container_width=True)
        st.caption(
            "18 farklı saat grubunun p-değerleri birlikte kontrol edilir. "
            "Bir saatin küçük fark göstermesi bağımsız çekilişte "
            "gelecek sayıların öngörülebilir olduğunu ispatlamaz."
        )
        st.markdown("##### 📥 V16 araştırma verilerini indir")
        for label,key,filename in (
            ("0–20 tekrar dağılımı","distribution","V16_0_20_SALINIM.csv"),
            ("Gruplanmış teorik/gerçek","pooled_distribution",
             "V16_TEORIK_KIYAS.csv"),
            ("Yüksek/düşük tekrarın sonrasındaki dağılım",
             "conditional","V16_SALINIM_SONRASI.csv"),
            ("36/37 gün öngörü hata kontrolü",
             "forecast","V16_GERCEK_KOR_TEST.csv"),
            ("18 ayrı saat karşılaştırması",
             "hour","V16_SAAT_SALINIM.csv"),
            ("Saat ilk/son altı hareketi",
             "halves","V16_ILK6_SON6.csv")
        ):
            st.download_button(
                "⬇️ "+label,
                v15_csv(result[key]),file_name=filename,
                mime="text/csv",key="v16_dl_"+key
            )
        st.info(
            "Örüntünün görünmesi, gelecekte tam 6/6 veya 10/10 "
            "kupon avantajı göstermez. Motor yalnız bağımsız sonuçlarla "
            "doğrulanmış sapmaları dikkate almalıdır."
        )
    else:
        st.info("Sonuçlar için 🔬 analiz düğmesine bas. V9–V15 "
                "motorları ve kalıcı kayıtlar değiştirilmez.")


with tabs[13]:
    render_v17(draws,day_draws,daystr,analysis_date==today,now_tr,moment)


with tabs[14]:
    render_v18(day_draws,daystr,analysis_date==today,now_tr)


with tabs[15]:
    render_v21(draws,family_text)


with tabs[16]:
    render_v22(draws)


with tabs[17]:
    render_v23(draws)


with tabs[18]:
    render_v24(draws)


with tabs[19]:
    render_v25(draws,family_text)


with tabs[20]:
    render_v26(draws)


with tabs[21]:
    render_v27(draws)


with tabs[22]:
    render_v28(draws)


with tabs[23]:
    render_v29(draws)


with tabs[24]:
    render_v30(draws)


with tabs[25]:
    render_v31(draws)


with tabs[26]:
    render_v32(draws)
