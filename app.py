# -*- coding: utf-8 -*-
"""Hızlı On V8 — Gün içi 3/4 görünüş + günler arası damar araştırması.

Tek Streamlit dosyası; geçmiş sonuçlardan kupon garantisi çıkarmaz.
Veri kalitesi, parça parça araştırma, günler arası imza, kör değerlendirme.
"""
from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import math
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = 'V8.0.1'
DEFAULT_URL = 'https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt'
SIZES = (6, 7, 8, 9, 10)
SCHEMA = '20261012_v8_2'
# Önceden raporlanmış aileler; yine de gün içi keşif tüm diğer aileleri ayrıca tarar.
BUILTIN_SEEDS = ['1-10-19-21-43-79', '1-11-18-26-39-52', '1-17-27-32-35-42-70-72', '1-2-19-22-23-34-48', '1-24-31-40-56-68', '1-26-32-37-50-77', '1-3-5-10-27-31-34-69', '1-3-7-28-32-55-65', '1-4-35-54-67-72', '1-5-7-19-34-47-59-70-74-76', '10-12-17-19-46-55-66-79', '11-20-28-47-79-80', '11-30-48-49-78-79', '12-15-29-38-44-72-74', '12-23-66-70-72-75', '13-14-16-38-41-56-60', '13-16-20-22-39-49-53', '13-27-30-34-59-60-69', '14-21-57-67-74-78', '14-22-27-39-48-70', '14-35-36-54-64-66', '15-17-41-46-47-53-74', '15-35-37-38-64-67', '16-26-43-52-58-69', '17-19-29-48-49-55-60', '17-27-32-35-42-70-72', '18-22-28-38-39-73', '18-35-48-53-66-71', '19-24-51-67-71-72-78', '19-36-37-41-46-77', '2-16-34-58-59-61-67', '2-17-42-43-62-66', '2-27-36-45-53-76-77', '2-29-41-54-55-61-76', '2-3-14-29-34-70', '2-3-16-34-58-59-61', '2-3-16-34-58-59-61-67', '2-3-16-34-58-59-67', '2-3-16-34-58-61-67', '2-3-16-34-59-61-67', '2-3-16-58-59-61-67', '2-3-34-58-59-61-67', '2-59-62-68-73-78', '2-6-17-37-63-71-75', '2-6-8-11-23-25-28-45-51-66', '20-27-30-45-51-52', '20-32-53-57-71-74', '21-22-28-38-39-70-71', '21-22-37-46-54-80', '21-22-49-55-62-63-80', '21-24-37-46-60-66-77', '21-28-37-62-64-71', '21-36-48-52-56-61-73', '22-26-44-58-66-71', '22-28-32-55-56-67-74-80', '23-37-43-48-61-71-72', '23-39-43-48-61-71-72', '23-43-46-51-56-74-75', '24-28-45-68-70-72-80', '24-31-52-66-67-77', '25-28-34-38-42-44-48-54-60-68', '29-43-50-65-69-73-79', '29-50-63-71-74-78-79', '3-10-16-22-36-60-70', '3-10-21-28-48-53', '3-16-34-58-59-61-67', '3-21-24-25-32-78', '3-21-29-51-59-65', '3-22-26-27-35-48', '3-27-55-59-66-76-79', '3-7-11-29-38-71-79', '3-9-13-25-36-46-62', '33-36-55-66-68-71-80', '34-41-44-49-59-78-79', '4-15-18-43-52-63-78', '4-25-38-47-61-64', '4-5-24-52-55-69', '4-6-27-31-32-36', '5-15-16-36-48-50-61', '5-20-43-53-61-69', '5-21-41-57-69-77', '5-23-28-46-53-54-75', '5-34-48-56-63-67', '5-7-14-22-25-70', '5-7-31-40-77-79', '5-8-12-27-74-77', '5-8-9-22-54-55-80', '5-8-9-51-57-59-66', '5-8-9-51-57-66-74', '6-12-20-43-57-74', '6-12-23-50-70-80', '6-16-34-52-57-71-73', '6-17-25-27-50-65-69', '6-21-26-37-40-67', '6-21-35-46-53-63', '7-17-22-28-44-53', '7-21-36-48-59-71', '7-31-34-35-44-66-72', '7-33-34-48-64-72', '8-10-22-26-52-57-79', '8-11-12-23-25-68', '8-12-14-45-60-62-67', '8-12-27-63-74-77', '9-13-25-31-43-68', '9-15-20-34-44-64', '9-18-30-41-57-59-63', '9-22-60-61-65-75', '9-28-44-49-56-57-78', '9-42-52-57-67-68']


@dataclass(frozen=True)
class Draw:
    ident: int
    dt: datetime
    nums: tuple[int, ...]
    mask: int
    pos: int

    @property
    def day(self):
        return self.dt.date()


def actual_pos(dt):
    """Kesin saat yuvası; eksik çekilişler sıralamayı kaydırmaz."""
    minute = dt.hour * 60 + dt.minute
    if 2 <= minute <= 62 and (minute - 2) % 5 == 0:
        return 1 + (minute - 2) // 5
    if 422 <= minute <= 1437 and (minute - 422) % 5 == 0:
        return 14 + (minute - 422) // 5
    return None


def pos_clock(pos):
    pos = int(pos)
    if 1 <= pos <= 13:
        minute = 2 + 5 * (pos - 1)
    elif 14 <= pos <= 217:
        minute = 422 + 5 * (pos - 14)
    else:
        return ''
    return f'{minute // 60:02d}:{minute % 60:02d}'


def make_mask(nums):
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m


def mask_numbers(mask):
    result = []
    while mask:
        lsb = mask & -mask
        result.append(lsb.bit_length())
        mask ^= lsb
    return tuple(result)


def parse_data(text):
    """CSV-benzeri native TXT veya site kopyası. Çelişkili kayıtlar uyarı üretir."""
    text = text.replace('\ufeff', '')
    accepted, rejected = [], 0

    def push(ident, dt, nums):
        nonlocal rejected
        try:
            ident = int(ident)
            nums = tuple(sorted(int(n) for n in nums))
            pos = actual_pos(dt)
            if pos is None or len(nums) != 20 or len(set(nums)) != 20 or nums[0] < 1 or nums[-1] > 80:
                rejected += 1
                return
            accepted.append(Draw(ident, dt, nums, make_mask(nums), pos))
        except (ValueError, TypeError, IndexError):
            rejected += 1

    for line in text.splitlines():
        if ';' not in line:
            continue
        p = line.strip().split(';')
        if len(p) != 3:
            rejected += 1
            continue
        try:
            push(p[0], datetime.strptime(p[1].strip(), '%d.%m.%Y %H:%M'),
                 [v for v in re.split(r'[,\s]+', p[2]) if v])
        except ValueError:
            rejected += 1

    blocks = list(re.finditer(r'(?:Çekiliş\s*no\s*:\s*#*|###\s*)(\d{5,9})', text, re.I))
    for i, block in enumerate(blocks):
        end = blocks[i+1].start() if i+1 < len(blocks) else len(text)
        section = text[block.end():end]
        dtmatch = re.search(r'(\d\d\.\d\d\.\d{4})\s*[- ]\s*(\d\d:\d\d)', section)
        if not dtmatch:
            continue
        tail = section[dtmatch.end():].split('Detaylar')[0].split('[Detaylar]')[0]
        nums = [s for s in tail.splitlines() if re.fullmatch(r'\s*\d{1,2}\s*', s)]
        try:
            push(block.group(1), datetime.strptime(' '.join(dtmatch.groups()), '%d.%m.%Y %H:%M'), nums)
        except ValueError:
            rejected += 1

    by_id, by_slot, conflicts = {}, {}, []
    for draw in sorted(accepted, key=lambda x: (x.dt, x.ident)):
        prev = by_id.get(draw.ident)
        slot = (draw.day, draw.pos)
        other = by_slot.get(slot)
        if prev is not None and prev != draw:
            conflicts.append(f'Aynı çekiliş numarasında çelişki: {draw.ident}')
        elif other is not None and other != draw:
            conflicts.append(f'Aynı tarih-saatte çelişki: {draw.dt}')
        else:
            by_id[draw.ident] = draw
            by_slot[slot] = draw
    draws = sorted(by_id.values(), key=lambda x: (x.dt, x.ident))
    return draws, {'gecersiz': rejected, 'celiski': conflicts, 'mukerrer': len(accepted) - len(draws)}


def group_days(draws):
    result = defaultdict(dict)
    for d in draws:
        result[d.day][d.pos] = d
    return dict(result)


def data_fingerprint(draws, max_gap, include_seeds):
    h = hashlib.sha256(f'{SCHEMA}|{max_gap}|{include_seeds}|'.encode())
    for d in draws:
        h.update(f'{d.ident}|{d.dt:%Y%m%d%H%M}|{d.mask};'.encode())
    return h.hexdigest()[:22]


def gap_type(gaps):
    if len(set(gaps)) == 1:
        return 'SABİT'
    if all(b > a for a, b in zip(gaps, gaps[1:])):
        return 'ARTAN_EŞİT_ADIM' if len(gaps) > 2 and len(set(b-a for a,b in zip(gaps,gaps[1:]))) == 1 else 'ARTAN'
    if all(b < a for a, b in zip(gaps, gaps[1:])):
        return 'AZALAN_EŞİT_ADIM' if len(gaps) > 2 and len(set(a-b for a,b in zip(gaps,gaps[1:]))) == 1 else 'AZALAN'
    if len(gaps) == 3 and gaps[0] == gaps[2]:
        return 'DÖNÜŞLÜ'
    return 'DEĞİŞKEN'


def signature(gaps):
    return '-'.join(str(x) for x in gaps)


def read_family_seeds(text):
    """Optional known exact families, pasted by user as lines or semicolon-separated."""
    result = set()
    for line in text.splitlines():
        vals = re.findall(r'\d+', line)
        if len(vals) in SIZES:
            nums = tuple(sorted(int(v) for v in vals))
            if len(set(nums)) == len(nums) and 1 <= nums[0] <= nums[-1] <= 80:
                result.add((len(nums), '-'.join(map(str, nums))))
    return result


def db_open(path):
    con = sqlite3.connect(path, timeout=30)
    con.execute('PRAGMA busy_timeout=30000')
    con.execute('PRAGMA journal_mode=DELETE')
    con.execute('PRAGMA synchronous=NORMAL')
    return con


def setup_database(path, fingerprint, n_days, user_seeds):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = db_open(path)
    con.executescript('''
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS candidate (k INTEGER,family TEXT,source TEXT,first_day TEXT,
                                         PRIMARY KEY(k,family));
    CREATE TABLE IF NOT EXISTS sighting (k INTEGER,family TEXT,day TEXT,pos INTEGER,ident INTEGER,
                                        PRIMARY KEY(k,family,day,pos));
    CREATE TABLE IF NOT EXISTS event (k INTEGER,family TEXT,day TEXT,n INTEGER,p1 INTEGER,p2 INTEGER,
          p3 INTEGER,p4 INTEGER,gaps TEXT,signature TEXT,shape TEXT,
          PRIMARY KEY(k,family,day,n,p1,p2,p3,p4));
    CREATE INDEX IF NOT EXISTS ix_event_family ON event(k,family,day);
    CREATE TABLE IF NOT EXISTS done_mine (day TEXT PRIMARY KEY, candidates INTEGER);
    CREATE TABLE IF NOT EXISTS done_profile (day TEXT PRIMARY KEY, events INTEGER);
    ''')
    m = dict(con.execute('SELECT key,value FROM meta'))
    if m.get('fingerprint') != fingerprint:
        for t in ('candidate', 'sighting', 'event', 'done_mine', 'done_profile', 'meta'):
            con.execute(f'DELETE FROM {t}')
        con.executemany('INSERT INTO meta(key,value) VALUES (?,?)', [
            ('fingerprint',fingerprint), ('phase','mine'), ('n_days',str(n_days)),
            ('version',VERSION), ('started_at',datetime.now(timezone.utc).isoformat())])
    con.executemany('INSERT OR IGNORE INTO candidate(k,family,source,first_day) VALUES (?,?,?,?)',
                    [(len(x.split('-')),x,'ÖNCEKİ ÇALIŞMA ÇEKİRDEĞİ','') for x in BUILTIN_SEEDS])
    con.executemany('INSERT OR IGNORE INTO candidate(k,family,source,first_day) VALUES (?,?,?,?)',
                    [(k, family, 'KULLANICI ÇEKİRDEĞİ', '') for k, family in sorted(user_seeds)])
    con.commit()
    con.close()


def candidate_triplets(day_draws, max_gap, min_size=6):
    """Tam kapsam: 1→2 ve 2→3 farkları <=max_gap, farklı hızlar dahil.
    3'lü ortak kesişimden TÜM 6..10 alt aileleri oluşturur; top-N kırpması yok.
    """
    pos = sorted(day_draws)
    mask = {p: day_draws[p].mask for p in pos}
    candidates = set()
    # Pair-first intersection pruning: most triplets eliminated quickly.
    for a in pos:
        am = mask[a]
        for b in range(a + 1, min(217, a + max_gap) + 1):
            bm = mask.get(b)
            if bm is None:
                continue
            ab = am & bm
            if ab.bit_count() < min_size:
                continue
            for c in range(b + 1, min(217, b + max_gap) + 1):
                cm = mask.get(c)
                if cm is None:
                    continue
                shared = ab & cm
                if shared.bit_count() < min_size:
                    continue
                nums = mask_numbers(shared)
                for k in SIZES:
                    if k > len(nums):
                        break
                    for family in itertools.combinations(nums, k):
                        candidates.add((k, '-'.join(map(str,family))))
    return candidates


def mine_batch(path, grouped, max_gap, batch_size):
    con = db_open(path)
    done = {r[0] for r in con.execute('SELECT day FROM done_mine')}
    target = [day for day in sorted(grouped) if str(day) not in done][:batch_size]
    found = 0
    try:
        for day in target:
            new = candidate_triplets(grouped[day], max_gap)
            con.executemany('INSERT OR IGNORE INTO candidate(k,family,source,first_day) VALUES (?,?,?,?)',
                            [(k,fam,'GÜN İÇİ 3 GÖRÜNÜŞ',str(day)) for k,fam in new])
            con.execute('INSERT INTO done_mine(day,candidates) VALUES (?,?)',(str(day),len(new)))
            con.commit()
            found += len(new)
        if con.execute('SELECT COUNT(*) FROM done_mine').fetchone()[0] == len(grouped):
            con.execute("UPDATE meta SET value='profile' WHERE key='phase'")
            con.commit()
    finally:
        con.close()
    return len(target), found


def event_rows_for_day(k, fam, day, hit_positions):
    """Each ordered 3/4 sighting subsequence, not just consecutive; preserves 1-2-3/4 gaps."""
    arr = sorted(hit_positions)
    if len(arr) < 3:
        return []
    result = []
    for n in (3,4):
        if len(arr) < n:
            continue
        for positions in itertools.combinations(arr, n):
            gaps = tuple(b-a for a,b in zip(positions,positions[1:]))
            pos = list(positions) + [0] * (4-n)
            result.append((k,fam,str(day),n,*pos,','.join(map(str,gaps)),signature(gaps),gap_type(gaps)))
    return result


def profile_batch(path, grouped, batch_size):
    con = db_open(path)
    done = {r[0] for r in con.execute('SELECT day FROM done_profile')}
    target = [day for day in sorted(grouped) if str(day) not in done][:batch_size]
    seeds = [(k,fam,tuple(map(int,fam.split('-')))) for k,fam in
             con.execute('SELECT k,family FROM candidate')]
    total_events = 0
    try:
        for day in target:
            bypos = grouped[day]
            number_slots = [0]*81
            for d in bypos.values():
                for number in d.nums:
                    number_slots[number] |= 1 << (d.pos-1)
            daily_events = []
            daily_hits = []
            for k, fam, family_nums in seeds:
                bits = number_slots[family_nums[0]]
                for number in family_nums[1:]:
                    bits &= number_slots[number]
                    if not bits:break
                if not bits:continue
                positions = []
                while bits:
                    bit = bits & -bits
                    p = bit.bit_length()
                    positions.append(p)
                    bits ^= bit
                    daily_hits.append((k,fam,str(day),p,bypos[p].ident))
                if len(positions) >= 3:
                    daily_events.extend(event_rows_for_day(k,fam,day,positions))
            con.executemany('INSERT OR IGNORE INTO sighting VALUES (?,?,?,?,?)', daily_hits)
            con.executemany('INSERT OR IGNORE INTO event VALUES (?,?,?,?,?,?,?,?,?,?,?)',daily_events)
            con.execute('INSERT INTO done_profile(day,events) VALUES (?,?)',(str(day),len(daily_events)))
            con.commit()
            total_events += len(daily_events)
        if con.execute('SELECT COUNT(*) FROM done_profile').fetchone()[0] == len(grouped):
            con.execute("UPDATE meta SET value='done' WHERE key='phase'")
            con.commit()
    finally:
        con.close()
    return len(target), total_events


def db_status(path, n_days):
    c = db_open(path)
    try:
        phase = dict(c.execute('SELECT key,value FROM meta')).get('phase', '?')
        mined = c.execute('SELECT COUNT(*) FROM done_mine').fetchone()[0]
        profiled = c.execute('SELECT COUNT(*) FROM done_profile').fetchone()[0]
        fams = c.execute('SELECT COUNT(*) FROM candidate').fetchone()[0]
        events = c.execute('SELECT COUNT(*) FROM event').fetchone()[0]
        return dict(phase=phase,mined=mined,profiled=profiled,n_days=n_days,fams=fams,events=events)
    finally:
        c.close()


def analyze_results(path, grouped, holdout=16, min_days=2):
    """Generate all reports in memory, no future observations in temporal signal creation."""
    c = db_open(path)
    try:
        families = {(int(k), fam): {'source':source,'first_day':first_day} for k,fam,source,first_day in
                    c.execute('SELECT k,family,source,first_day FROM candidate')}
        hit_by_family = defaultdict(lambda: defaultdict(list))
        for k,fam,day,pos,ident in c.execute('SELECT k,family,day,pos,ident FROM sighting ORDER BY day,pos'):
            hit_by_family[(k,fam)][day].append((int(pos),int(ident)))
        event_by_family = defaultdict(list)
        for k,fam,day,n,p1,p2,p3,p4,gaps,sig,shape in c.execute(
                'SELECT k,family,day,n,p1,p2,p3,p4,gaps,signature,shape FROM event ORDER BY day,n,p1,p2,p3,p4'):
            event_by_family[(k,fam)].append({'Gün':day, 'N':n, 'P':(p1,p2,p3,p4),
                                            'Aralık':gaps,'İmza':sig,'Şekil':shape})
    finally:
        c.close()

    all_days = sorted(str(x) for x in grouped)
    if not all_days:
        raise ValueError('Geçerli gün yok')
    cutoff = all_days[max(0,len(all_days)-min(max(1,int(holdout)),max(1,len(all_days)-1)))]
    quality = []
    for day in sorted(grouped):
        slots = grouped[day]
        missing = sorted(set(range(1,218))-set(slots))
        quality.append({'Gün':str(day),'Çekiliş':len(slots),'Eksik yuva':len(missing),
                        'Eksik yuva örneği':','.join(str(p) for p in missing[:50])})

    event_table, fam_table, sig_days, day_rhythms = [], [], defaultdict(set), []
    daily_family=[]
    hour_stats=defaultdict(lambda: {'olay':0,'aileler':set()})
    pattern_families=defaultdict(set)
    pattern_occurrences=Counter()
    by_size = defaultdict(Counter)
    for key in sorted(families):
        k,fam = key
        ds = hit_by_family.get(key,{})
        evs = event_by_family.get(key,[])
        n3days = {e['Gün'] for e in evs if e['N']==3}
        n4days = {e['Gün'] for e in evs if e['N']==4}
        n_all = sum(len(v) for v in ds.values())
        for active_date, observations in sorted(ds.items()):
            positions=[p for p,_ in observations]
            daily_family.append({'Boyut':k,'Aile':fam,'Gün':active_date,'Görünüş sayısı':len(positions),
                  'Çekiliş sıraları':','.join(map(str,positions)),
                  'Saatler':','.join(pos_clock(p) for p in positions),
                  'Çekiliş numaraları':','.join(str(ident) for _,ident in observations)})
        by_size[k]['Aile'] += 1
        by_size[k]['3+ gün'] += len(n3days)
        by_size[k]['4+ gün'] += len(n4days)
        by_size[k]['Toplam görünüş'] += n_all
        by_size[k]['Farklı gün'] += len(ds)
        # same-family signature repeated on DISTINCT dates (never count overlapping triples on one day twice)
        sig2dates = defaultdict(set)
        four2dates = defaultdict(set)
        start_event_index=len(event_table)
        for ev in evs:
            (sig2dates if ev['N']==3 else four2dates)[ev['İmza']].add(ev['Gün'])
            record={'Boyut':k,'Aile':fam,'Gün':ev['Gün'],'Görünüş':ev['N'],
                    '1. sıra':ev['P'][0],'2. sıra':ev['P'][1],'3. sıra':ev['P'][2],
                    '4. sıra':ev['P'][3] or '', '1. saat':pos_clock(ev['P'][0]),
                    '2. saat':pos_clock(ev['P'][1]),'3. saat':pos_clock(ev['P'][2]),
                    '4. saat':pos_clock(ev['P'][3]),'Aralıklar':ev['Aralık'],
                    'Sınıf':ev['Şekil'],'Günler arası aynı imza':0}
            event_table.append(record)
            sig_days[(k,ev['N'],ev['İmza'])].add(ev['Gün'])
            pattern_families[(k,ev['N'],ev['İmza'])].add(fam)
            pattern_occurrences[(k,ev['N'],ev['İmza'])]+=1
            hh=pos_clock(ev['P'][0])[:2]
            hg=(ev['Gün'],k,hh,ev['N'],ev['Şekil'])
            hour_stats[hg]['olay']+=1
            hour_stats[hg]['aileler'].add(fam)
        # Number of distinct days per exact signature; filled after all families.
        for e in event_table[start_event_index:]:
            e['Günler arası aynı imza'] = len((sig2dates if e['Görünüş']==3 else four2dates).get(e['Aralıklar'],set()))
        active_dates=sorted(ds)
        day_gaps=[(date.fromisoformat(b)-date.fromisoformat(a)).days for a,b in zip(active_dates,active_dates[1:])]
        for idx in range(len(active_dates)-2):
            dg=day_gaps[idx:idx+2]
            day_rhythms.append({'Boyut':k,'Aile':fam,'Başlangıç günü':active_dates[idx],
                                '2. gün':active_dates[idx+1],'3. gün':active_dates[idx+2],
                                'Gün aralıkları':signature(dg),'Sınıf':gap_type(dg)})
        fam_table.append({
            'Boyut':k, 'Aile':fam, 'Kaynak':families[key]['source'],
            'İlk gün':min(ds) if ds else '', 'Son gün':max(ds) if ds else '',
            'Toplam çekiliş görünüşü':n_all, 'Aktif gün':len(ds),
            '3+ kez göründüğü gün':len(n3days),'4+ kez göründüğü gün':len(n4days),
            '3lü tüm olay':sum(e['N']==3 for e in evs),'4lü tüm olay':sum(e['N']==4 for e in evs),
            '3lü sabit aralık':sum(e['N']==3 and e['Şekil']=='SABİT' for e in evs),
            '3lü artan aralık':sum(e['N']==3 and e['Şekil'].startswith('ARTAN') for e in evs),
            '3lü azalan aralık':sum(e['N']==3 and e['Şekil'].startswith('AZALAN') for e in evs),
            '3lü başka gün aynı imza':sum(len(a)>1 for a in sig2dates.values()),
            '4lü başka gün aynı imza':sum(len(a)>1 for a in four2dates.values()),
            'En fazla 1 günde görünüş':max(map(len, ds.values()),default=0),
            'En çok tekrarlanan 3lü imza': max(sig2dates, key=lambda x:(len(sig2dates[x]),x)) if sig2dates else '',
            '3lü imza farklı gün':max((len(v) for v in sig2dates.values()),default=0),
            'En çok tekrarlanan 4lü imza': max(four2dates,key=lambda x:(len(four2dates[x]),x)) if four2dates else '',
            '4lü imza farklı gün':max((len(v) for v in four2dates.values()),default=0),
            'Günler arası görünüş farkları':','.join(map(str,day_gaps[:50])),
            'Aktif gün tarihleri':','.join(active_dates),
            'Gün içi 3+ görüldüğü tarihler':','.join(sorted(n3days)),
            'Gün içi 4+ görüldüğü tarihler':','.join(sorted(n4days))
        })

    # Prequential evaluation: patterns only from dates strictly BEFORE tested date.
    # A family must be observed with same signature on >= min_days DISTINCT historical dates.
    # We produce at most one forecast for each family, target day and stage.
    history3, history4 = defaultdict(lambda: defaultdict(set)), defaultdict(lambda: defaultdict(set))
    history2 = defaultdict(lambda: defaultdict(set))
    events_per_date = defaultdict(list)
    for key, evs in event_by_family.items():
        for e in evs:
            events_per_date[e['Gün']].append((key,e))
    predictions=[]
    daily_test = all_days[all_days.index(cutoff):]
    # use history from earlier days and update when day finished, avoiding lookahead
    for d in all_days:
        if d >= cutoff:
            for key, ds in hit_by_family.items():
                sightings = ds.get(d,[])
                if not sightings:
                    continue
                k,fam = key
                positions = [p for p,_ in sightings]
                present = set(positions)
                day_slots = grouped[date.fromisoformat(d)]
                for stage in (2,3,4):
                    if len(positions) < stage-1:
                        continue
                    observed = positions[:stage-1]
                    known_gaps = tuple(b-a for a,b in zip(observed,observed[1:]))
                    options=[]
                    if stage==2:
                        for g, dates in history2[key].items():
                            if len(dates)>=min_days:
                                options.append((len(dates),int(g),str(g)))
                    elif stage==3:
                        for (g1,g2), dates in history3[key].items():
                            if g1==known_gaps[0] and len(dates)>=min_days:
                                options.append((len(dates),int(g2),f'{g1}-{g2}'))
                    else:
                        for (g1,g2,g3), dates in history4[key].items():
                            if (g1,g2)==known_gaps and len(dates)>=min_days:
                                options.append((len(dates),int(g3),f'{g1}-{g2}-{g3}'))
                    if not options:
                        continue
                    n_support, next_gap, sig = sorted(options,key=lambda o:(-o[0],o[1],o[2]))[0]
                    target = observed[-1]+next_gap
                    if not 1<=target<=217:
                        status='HEDEF GÜN DIŞI'
                    elif target in observed:
                        status='GEÇERSİZ'
                    elif target not in day_slots:
                        status='ÇEKİLİŞ EKSİK'
                    elif len(positions)>=stage and target==positions[stage-1]:
                        status='TAM İSABET'
                    else:
                        status='ISKA'
                    # Critically report all predictions, but don't include missing slots in hit-rate denominators.
                    predictions.append({'Boyut':k,'Aile':fam,'Gün':d,'Beklenen görünüş':stage,
                            'Gözlenen başlangıç':','.join(map(str,observed)),
                            'Geçmiş ritim imzası':sig,'Geçmiş destek günü':n_support,
                            'Tahmin edilen sıra':target,'Tahmin saati':pos_clock(target),
                            'Sonuç':'TAM İSABET' if status=='TAM İSABET' else status,
                            'Rastgele tam aile olasılığı':round(math.comb(80-k,20-k)/math.comb(80,20),10)})
        # Update history AFTER the whole day; count a signature once per distinct day.
        for key, hits in hit_by_family.items():
            positions=[p for p,_ in hits.get(d,[])]
            for p1,p2 in itertools.combinations(positions,2):
                history2[key][p2-p1].add(d)
        for key,e in events_per_date.get(d,[]):
            gaps = tuple(int(v) for v in e['Aralık'].split(','))
            if e['N']==3:
                history3[key][gaps].add(d)
            else:
                history4[key][gaps].add(d)

    blind = defaultdict(Counter)
    for p in predictions:
        blind[p['Boyut']][p['Sonuç']]+=1
    size_table = []
    for k in SIZES:
        hits=blind[k]['TAM İSABET']; losses=blind[k]['ISKA']
        size_table.append({'Boyut':k,'Aile sayısı':by_size[k]['Aile'],
            '3+ görünüş günü (aile-gün)':by_size[k]['3+ gün'],
            '4+ görünüş günü (aile-gün)':by_size[k]['4+ gün'],
            'Kör test değerlendirilebilir':hits+losses,'Kör tam isabet':hits,
            'Kör başarısız':losses,
            'Kör oran':round(100*hits/(hits+losses),3) if hits+losses else '',
            'Tesadüfi tek çekiliş aile olasılığı':round(math.comb(80-k,20-k)/math.comb(80,20),10)})
    template=[]
    for (k,n,sig),dates in sig_days.items():
        template.append({'Boyut':k,'3lü/4lü':n,'Aralık imzası':sig,
                         'Farklı aile sayısı':len(pattern_families[(k,n,sig)]),
                         'Görülen farklı gün':len(dates),
                         'Toplam olay':pattern_occurrences[(k,n,sig)]})
    template.sort(key=lambda x:(-x['Görülen farklı gün'],x['Boyut'],x['Aralık imzası']))
    fam_table.sort(key=lambda x:(-max(x['3lü imza farklı gün'],x['4lü imza farklı gün']),
                                  -x['3+ kez göründüğü gün'],-x['Aktif gün'],x['Boyut'],x['Aile']))
    event_table.sort(key=lambda x:(x['Boyut'],x['Aile'],x['Gün'],x['Görünüş'],x['1. sıra']))
    hourly=[{'Gün':day,'Boyut':k,'Başlangıç saati':hh+':00',
             '3lü/4lü':n,'Sınıf':shape,'Olay':v['olay'],'Farklı aile':len(v['aileler'])}
             for (day,k,hh,n,shape),v in sorted(hour_stats.items())]
    return {'size':size_table,'families':fam_table,'events':event_table,'day_rhythms':day_rhythms,
            'templates':template,'blind':predictions,'quality':quality,'daily_family':daily_family,
            'hourly':hourly,'cutoff':cutoff}


def csv_data(rows):
    if not rows:
        return '\ufeffBilgi\nKayıt bulunamadı\n'.encode('utf-8')
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]),delimiter=';',extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return ('\ufeff'+out.getvalue()).encode('utf-8')


def report_zip(report, settings=None):
    names = [
        ('00_BOYUT_OZETI.csv','size'),
        ('01_TEK_ANA_AILE_LISTESI.csv','families'),
        ('02_GUN_ICI_3_4_GORUNUS_TUM_OLAYLAR.csv','events'),
        ('07_AILE_GUN_GUN_TUM_GORUNUSLER.csv','daily_family'),
        ('08_SAAT_SAAT_GORUNUS_OZETI.csv','hourly'),
        ('03_GUNLER_ARASI_GORUNUS_ZINCIRLERI.csv','day_rhythms'),
        ('04_RAKAM_DEGISIMLI_RITIM_SABLONLARI.csv','templates'),
        ('05_KOR_TEST_2_3_4_HEDEF.csv','blind'),
        ('06_VERI_KALITESI.csv','quality'),
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for filename,key in names:
            z.writestr(filename,csv_data(report[key]))
        z.writestr('99_OKU_ONCE.txt',f'''HIZLI ON V8 — ANALİZ RAPORU\n\nANA DOSYA: 01_TEK_ANA_AILE_LISTESI.csv\nAyrıntılar: 02... ve diğer CSV'ler.\nKör test başlangıcı: {report['cutoff']}\nParametreler: {json.dumps(settings or {},ensure_ascii=False)}\n\nSINIRLAR:\n- Gün içi keşif 1→2 ve 2→3 aralıkları belirlenen üst sınır içinde kalan tüm 6..10 alt aileleri kapsar.\n- Bu pencerenin dışındaki ve gün içi 3 kez hiç görünmeyen aileler, ancak önceki çekirdek listesinde veya kullanıcı çekirdeğinde varsa izlenir.\n- Günler arası karşılaştırma, keşfedilen aynı sayı ailesinin TÜM tarihlerini tekrar tarar.\n- Rakam değişimli şablonlar sadece yapı/tarih araştırmasıdır, tek başına sayısal tahmin değildir.\n- Zaman sıralı testte ritim bilgisi yalnız önceki tarihlerden gelir; gün sonunda günün ritimleri öğrenilir.
- Aday havuzu tam veri üzerinde keşfedildiği için geçmişe dönük seçim yanlılığı olabilir: bu tam bağımsız ileriye dönük canlı test değildir.\n- İlk/ikinci/üçüncü görünüşe göre 2.,3.,4. görünüşler sınanır. Tek çekilişte aynı tam aile aranır.\n- Aynı ailede daha önce 2 ayrı günde tekrarlayan kalıp bulunmadıkça sinyal verilmez (eşik değiştirilebilir).\n- Tam isabet geçmiş başarı olabilir; gelecek için garanti değildir.\n- Streamlit Cloud yerel SQLite kalıcı değildir; mutlaka checkpoint ZIP indirin.\n''')
    return out.getvalue()


def checkpoint_zip(path):
    # database open connection is closed between batches, safe to copy this file
    with open(path,'rb') as f:
        content=f.read()
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('v8_checkpoint.sqlite', content)
    return b.getvalue()


def restore_checkpoint(content,path,fingerprint):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if 'v8_checkpoint.sqlite' not in z.namelist():
            raise ValueError('Yedekte v8_checkpoint.sqlite bulunamadı.')
        content=z.read('v8_checkpoint.sqlite')
    tmp=path+'.restore'
    with open(tmp,'wb') as f:
        f.write(content)
    try:
        c=sqlite3.connect(tmp)
        got=dict(c.execute('SELECT key,value FROM meta')).get('fingerprint')
        c.close()
        if got != fingerprint:
            raise ValueError('Yedek bu veri ve ayarlarla aynı değil. Önce doğru veri / aralık seçilmeli.')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.remove(tmp)


def streamlit_main():
    import streamlit as st
    import pandas as pd
    import requests
    st.set_page_config(page_title='Hızlı On V8 — Ritim Araştırması',page_icon='🔎',layout='wide',initial_sidebar_state='collapsed')
    st.title('🔎 Hızlı On V8 — Ailelerin Ritim Haritası')
    st.caption('6 / 7 / 8 / 9 / 10 aileleri • aynı gün 3–4 geliş • günler arası aynı damar • artan/azalan/sabit ritimler')
    st.info('Bu aşamada **kupon üretmiyoruz**. Önce ritimleri ayrı ayrı ve geçmiş-gün kör testiyle ölçüyoruz. Geçmişte %100 görünen ritim gelecekte kesinlik değildir.')
    mode=st.radio('Araştırma derinliği', ['Dengeli • 48 çekiliş','Derin • 96 çekiliş','Çok derin • 216 çekiliş'],horizontal=True,index=0)
    max_gap={'Dengeli • 48 çekiliş':48,'Derin • 96 çekiliş':96,'Çok derin • 216 çekiliş':216}[mode]
    st.caption('Pencere: 1→2 ve 2→3 aralıklarının ayrı ayrı üst sınırı. Daha büyük pencere çok daha uzun sürebilir.')
    with st.expander('⚙️ İleri ayarlar / dosya / yedek',expanded=False):
        url=st.text_input('GitHub veri.txt RAW adresi',DEFAULT_URL)
        uploaded=st.file_uploader('İsteğe bağlı ek çekiliş TXT',type=['txt'],help='GitHub verisiyle birleştirilir; geçerli aynı çekiliş iki kez eklenmez.')
        seed_text=st.text_area('Ek izlenecek bilinen aileler (satır başına 6–10 rakam, - veya boşlukla)',height=95)
        holdout=st.slider('Kör test: son kaç gün',5,45,16)
        min_days=st.slider('Önceki kaç ayrı günde aynı ritim gözlenmiş olmalı?',2,5,2)
        per_step=st.slider('Bir tıklamada kaç gün işlesin?',1,5,2)
        back=st.file_uploader('Önceki V8 checkpoint ZIP (isteğe bağlı)',type=['zip'])
    if 'url' not in locals():url=DEFAULT_URL
    if 'holdout' not in locals():holdout=16
    if 'min_days' not in locals():min_days=2
    if 'per_step' not in locals():per_step=2
    if 'seed_text' not in locals():seed_text=''
    if 'back' not in locals():back=None
    if 'uploaded' not in locals():uploaded=None

    @st.cache_data(ttl=180,show_spinner=False)
    def fetch(url):
        r=requests.get(url,timeout=35)
        r.raise_for_status()
        return r.content.decode('utf-8-sig',errors='replace')

    if st.button('🔄 GitHub verisini tazele'):
        fetch.clear();st.rerun()
    try:
        source=fetch(url)
        if uploaded is not None:
            source+='\n'+uploaded.getvalue().decode('utf-8-sig',errors='replace')
        draws, warnings=parse_data(source)
    except Exception as e:
        st.error(f'veri.txt okunamadı: {e}. GitHub adresini kontrol et.');st.stop()
    if not draws:
        st.error('Geçerli çekiliş bulunamadı.');st.stop()
    days=group_days(draws)
    custom=read_family_seeds(seed_text)
    fingerprint=data_fingerprint(draws,max_gap,sorted(custom))
    path=os.path.join(tempfile.gettempdir(),f'hizli_on_v8_{fingerprint}.sqlite')
    setup_database(path,fingerprint,len(days),custom)
    if back is not None:
        h=hashlib.sha256(back.getvalue()).hexdigest()
        if st.session_state.get('last_restore') != h:
            try:
                restore_checkpoint(back.getvalue(),path,fingerprint)
                st.session_state['last_restore']=h
                st.success('Yedek geri yüklendi.')
            except Exception as e:st.error(f'Yedek yüklenemedi: {e}')
    stats=db_status(path,len(days))
    c1,c2,c3=st.columns(3)
    c1.metric('Çekiliş',f'{len(draws):,}'.replace(',','.'))
    c2.metric('Gün',len(days))
    c3.metric('Bulunan aile',stats['fams'])
    st.caption(f'Veri: {draws[0].dt:%d.%m.%Y} — {draws[-1].dt:%d.%m.%Y} · 217 sabit saat yuvası; eksik yuvalar kaydırılmaz.')
    if warnings['celiski']:
        st.warning(f'{len(warnings["celiski"])} çelişen çekiliş var. İlk kayıt korundu; veri kalitesini kontrol et.')
    missing=sum(217-len(ds) for ds in days.values())
    if missing:st.caption(f'Eksik çekiliş yuvası toplamı: {missing}. Başlangıç/son gün kısmi olabilir.')
    if stats['phase']=='mine':
        st.subheader('1 / 3 — Bütün günlerde 3 görünüşlü aile keşfi')
        st.progress(stats['mined']/len(days))
        st.write(f'{stats["mined"]} / {len(days)} gün tarandı. Bu bölüm, bilinen ailelerle sınırlı değildir.')
    elif stats['phase']=='profile':
        st.subheader('2 / 3 — Ailelerin TÜM gün/saat/çekiliş görünüşleri')
        st.progress(stats['profiled']/len(days))
        st.write(f'{stats["profiled"]} / {len(days)} gün doğrulandı. {stats["fams"]} aile aranıyor.')
    else:
        st.subheader('3 / 3 — Analiz tamamlandı')
        st.progress(1.0)

    if stats['phase']!='done':
        if st.button('▶️ ANALİZİ BAŞLAT / KALDIĞI YERDEN DEVAM',type='primary',use_container_width=True):
            started=time.monotonic()
            processed=0
            with st.spinner('Günler sırayla işleniyor ve veritabanına kaydediliyor…'):
                running=st.empty()
                while time.monotonic()-started < 17:
                    current=db_status(path,len(days))
                    if current['phase']=='done':break
                    if current['phase']=='mine':
                        n,v=mine_batch(path,days,max_gap,per_step)
                    else:
                        n,v=profile_batch(path,days,per_step)
                    if n==0:break
                    processed+=n
                    fresh=db_status(path,len(days))
                    running.write(f'İlerleme: keşif {fresh["mined"]}/{len(days)} gün, '
                                  f'doğrulama {fresh["profiled"]}/{len(days)} gün. '
                                  f'Bu çalıştırmada {processed} gün işlendi.')
            fresh=db_status(path,len(days))
            st.rerun()
        st.caption('İşlem tek düğmede kendiliğinden ilerler; her küçük grup SQLite’a kaydedilir. '
                   'Uzun taramalarda düğmeye yeniden basınca kaldığı yerden devam eder.')
    if stats['mined'] or stats['profiled']:
        st.download_button('💾 Kaldığım yerden devam için ZIP yedeği indir',
            data=checkpoint_zip(path),file_name=f'HIZLI_ON_V8_CHECKPOINT_{fingerprint}.zip',
            mime='application/zip',use_container_width=True)
    if stats['phase']=='done':
        with st.spinner('Tam analiz raporu hazırlanıyor…'):
            report=analyze_results(path,days,holdout,min_days)
        st.subheader('6’lı–10’lu aile özeti')
        st.dataframe(pd.DataFrame(report['size']),hide_index=True,use_container_width=True)
        st.subheader('Aynı ailenin farklı günlerde aynı aralıkla gelmesi')
        top=[f for f in report['families'] if f['3lü imza farklı gün']>=2 or f['4lü imza farklı gün']>=2]
        if top:st.dataframe(pd.DataFrame(top).head(100),hide_index=True,use_container_width=True)
        else:st.info('Aynı ailenin aynı üçlü/dörtlü aralık imzasını iki ayrı günde tekrar ettiği olay bulunmadı.')
        st.subheader('Zaman sıralı test — 2., 3. ve 4. geliş')
        n=sum(x['Kör test değerlendirilebilir'] for x in report['size'])
        h=sum(x['Kör tam isabet'] for x in report['size'])
        st.write(f'Değerlendirilebilir {n} önceden hedef; tam isabet {h}.')
        st.caption('Ritim geçmişi her günün öncesinden gelir; ancak aday aileler tüm veriyle keşfedildiği için tam bağımsız ileri test değildir. Eksik hedef sayılmaz.')
        st.download_button('⬇️ TEK ANA AİLE LİSTESİ (CSV)',csv_data(report['families']),
            'HIZLI_ON_V8_TEK_ANA_AILE_LISTESI.csv','text/csv',type='primary',use_container_width=True)
        st.download_button('⬇️ TÜM DETAYLI RAPORLAR (TEK ZIP)',
            report_zip(report,dict(max_gap=max_gap,holdout=holdout,min_days=min_days)),
            'HIZLI_ON_V8_TUM_DETAYLI_ANALIZLER.zip','application/zip',use_container_width=True)
        with st.expander('Ayrıntılı 3/4 görünüş örnekleri'):
            st.dataframe(pd.DataFrame(report['events']).head(200),hide_index=True,use_container_width=True)
        with st.expander('Günler arası görünüş zincirleri'):
            st.dataframe(pd.DataFrame(report['day_rhythms']).head(200),hide_index=True,use_container_width=True)
    st.caption(f'{VERSION}: Bu motor tarihsel düzenleri sınıflandırır. Sonraki çekiliş için garantili kupon yoktur. \n'
               'Streamlit Cloud yerel dosyaları uygulama yeniden başlatıldığında kaybolabilir; düzenli ZIP yedeği alın.')


if __name__=='__main__':
    streamlit_main()
