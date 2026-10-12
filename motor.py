# -*- coding: utf-8 -*-
"""Hızlı On V6 research engine — no execution side effects.
All forecasts use historical information available BEFORE the evaluated draw.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from itertools import combinations
from math import comb, sqrt
import hashlib
import io
import json
import re
import zipfile

import numpy as np
import pandas as pd

FULL80 = (1 << 80) - 1
DAY_GAPS = (2, 5, 7, 14)
FAMILY_SIZES = (5, 6, 7, 8, 9, 10)


def canonical_position(dt):
    """Hızlı On schedule: #1–13 00:02–01:02, #14–217 07:02–23:57."""
    m = dt.hour * 60 + dt.minute
    if 2 <= m <= 62 and (m - 2) % 5 == 0:
        return 1 + (m - 2) // 5
    if 422 <= m <= 1437 and (m - 422) % 5 == 0:
        return 14 + (m - 422) // 5
    return None


def position_time(p):
    p = int(p)
    if 1 <= p <= 13:
        m = 2 + (p - 1) * 5
    elif 14 <= p <= 217:
        m = 422 + (p - 14) * 5
    else:
        return ""
    return f"{m//60:02d}:{m%60:02d}"


def nums_mask(nums):
    mask = 0
    for n in nums:
        mask |= 1 << (int(n) - 1)
    return mask


def mask_nums(mask):
    out = []
    while mask:
        lowest = mask & -mask
        out.append(lowest.bit_length())
        mask ^= lowest
    return tuple(out)


@dataclass(frozen=True)
class Draw:
    id: int
    dt: datetime
    nums: tuple
    mask: int
    pos: int

    @property
    def day(self):
        return self.dt.date()


def _valid(draw_id, dt, nums):
    if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
        return None
    p = canonical_position(dt)
    if p is None or not (0 < draw_id < 10000000000):
        return None
    nums = tuple(sorted(nums))
    return Draw(draw_id, dt, nums, nums_mask(nums), p)


def read_draws(text):
    """Supports native id;dd.mm.yyyy hh:mm;1,...,20 and official multi-line paste."""
    text = text.replace('\ufeff', '')
    arr = []
    malformed = 0
    for raw in text.splitlines():
        s = raw.strip()
        if ';' not in s:
            continue
        fields = s.split(';')
        if len(fields) != 3:
            malformed += 1
            continue
        try:
            id_ = int(fields[0])
            dt = datetime.strptime(fields[1].strip(), '%d.%m.%Y %H:%M')
            nums = [int(n) for n in re.split(r'[\s,]+', fields[2].strip()) if n]
            r = _valid(id_, dt, nums)
            if r is None:
                malformed += 1
            else:
                arr.append(r)
        except (ValueError, OverflowError):
            malformed += 1

    # Official paste: "Çekiliş no: 61642 ..." with number-only lines.
    # Avoid accidentally treating standalone numbers from unrelated text as draws.
    block = re.compile(r'(?:Çekiliş\s*no\s*:\s*#*\s*|###\s*)(\d{5,9})', flags=re.I)
    matches = list(block.finditer(text))
    for i, match in enumerate(matches):
        snippet = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        d = re.search(r'(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})', snippet)
        if not d:
            continue
        try:
            dt = datetime.strptime(d.group(1) + ' ' + d.group(2), '%d.%m.%Y %H:%M')
            # Only number-only lines after the date, before Detaylar/link.
            tail = snippet[d.end():].split('Detaylar')[0].split('[Detaylar]')[0]
            nums = [int(s.strip()) for s in tail.splitlines() if re.fullmatch(r'\s*\d{1,2}\s*', s)]
            r = _valid(int(match.group(1)), dt, nums)
            if r is not None:
                arr.append(r)
        except ValueError:
            continue

    arr.sort(key=lambda r: (r.dt, r.id))
    by_id = {}
    by_slot = {}
    conflicts = []
    for r in arr:
        prev = by_id.get(r.id)
        slotprev = by_slot.get((r.day, r.pos))
        if prev and (prev.dt != r.dt or prev.nums != r.nums):
            conflicts.append('Çekiliş no çakışması: ' + str(r.id))
        elif slotprev and (slotprev.id != r.id or slotprev.nums != r.nums):
            conflicts.append('Tarih/saat çakışması: ' + r.dt.isoformat(' '))
        else:
            by_id[r.id] = r
            by_slot[(r.day, r.pos)] = r
    return sorted(by_id.values(), key=lambda r: (r.dt, r.id)), {'geçersiz_satır': malformed, 'çakışmalar': conflicts}


def draw_text(draws):
    return '\n'.join(f"{r.id};{r.dt:%d.%m.%Y %H:%M};{','.join(map(str, r.nums))}" for r in draws) + '\n'


def by_day(draws):
    days = defaultdict(dict)
    for r in draws:
        days[r.day][r.pos] = r
    return dict(days)


def quality_table(draws):
    rows = []
    for day, d in sorted(by_day(draws).items()):
        missing = sorted(set(range(1, 218)) - set(d))
        rows.append({'Tarih': day.isoformat(), 'Çekiliş': len(d), 'Eksik': 217-len(d),
                     'İlk': min(r.dt.strftime('%H:%M') for r in d.values()),
                     'Son': max(r.dt.strftime('%H:%M') for r in d.values()),
                     'Eksik slotlar (ilk 35)': ','.join(str(x) for x in missing[:35])})
    return pd.DataFrame(rows)


def _iter_triples(days, max_within=24, daygaps=DAY_GAPS):
    """Triples aligned by draw gap within a session or by SAME canonical slot on three dates."""
    for d, mp in sorted(days.items()):
        for p, a in mp.items():
            for g in range(1, max_within+1):
                b, c = mp.get(p+g), mp.get(p+2*g)
                if not b or not c:
                    continue
                if (b.dt-a.dt).total_seconds() != 300*g or (c.dt-b.dt).total_seconds() != 300*g:
                    continue
                yield ('çekiliş', g, a, b, c)
        for g in daygaps:
            mid = days.get(d + timedelta(days=g))
            last = days.get(d + timedelta(days=2*g))
            if not mid or not last:
                continue
            for p, a in mp.items():
                b, c = mid.get(p), last.get(p)
                if b and c:
                    yield ('gün', g, a, b, c)


def _reduction_candidates(intersection, max_per_k=8):
    ns = mask_nums(intersection)
    if len(ns) < 5:
        return
    for k in FAMILY_SIZES:
        if k > len(ns):
            break
        it = combinations(ns, k)
        total = comb(len(ns), k)
        if total <= max_per_k:
            for combo in it:
                yield k, combo
        else:
            # Deterministic spread through the combination sequence; stable reproducible.
            indexes = set(np.linspace(0, total-1, max_per_k, dtype=int).tolist())
            for j, combo in enumerate(it):
                if j in indexes:
                    yield k, combo


def discover_families(train_draws, legacy_seeds=(), max_per_size=350, max_gap=24):
    """Budgeted candidate discovery. Only training rows used, never holdout."""
    days = by_day(train_draws)
    triple = Counter()
    pairs = Counter()
    for mode, gap, a, b, c in _iter_triples(days, max_within=max_gap):
        intersection = a.mask & b.mask & c.mask
        for k, family in _reduction_candidates(intersection, 25):
            triple[(k, family)] += 1
    # Pair mining of overlaps; candidate cap prevents exponential C(20,k) blow-ups.
    for day, mp in days.items():
        for p, a in mp.items():
            for g in (1,2,3,5,7,12,24):
                b = mp.get(p+g)
                if b and (b.dt-a.dt).total_seconds() == 300*g:
                    intersection = a.mask & b.mask
                    if intersection.bit_count() >= 7:
                        for k, family in _reduction_candidates(intersection, 4):
                            pairs[(k, family)] += 1
            for gap in DAY_GAPS:
                dst = days.get(day + timedelta(days=gap), {})
                b = dst.get(p)
                if b:
                    intersection = a.mask & b.mask
                    if intersection.bit_count() >= 7:
                        for k, family in _reduction_candidates(intersection, 4):
                            pairs[(k, family)] += 1

    candidates = defaultdict(dict)
    for x in legacy_seeds:
        ns = tuple(sorted(int(z) for z in str(x).split('-')))
        if len(ns) in FAMILY_SIZES and len(set(ns)) == len(ns):
            candidates[len(ns)][ns] = {'Kaynak':'V5 çekirdeği', 'Üçlü kaynak':0, 'İkili kaynak':0}
    per_size = Counter()
    sorted_keys = sorted(set(triple)|set(pairs), key=lambda f: (
        triple[f]*20 + min(8, pairs[f]), triple[f], pairs[f]), reverse=True)
    for k, ns in sorted_keys:
        if k in candidates and ns in candidates[k]:
            candidates[k][ns]['Üçlü kaynak'] = triple[(k, ns)]
            candidates[k][ns]['İkili kaynak'] = pairs[(k, ns)]
        elif per_size[k] < max_per_size and (triple[(k, ns)] >= 1 or pairs[(k, ns)] >= 2):
            candidates[k][ns] = {'Kaynak':'Otomatik keşif', 'Üçlü kaynak':triple[(k, ns)], 'İkili kaynak':pairs[(k, ns)]}
            per_size[k] += 1
    return candidates, {'üçlü_aday':len(triple), 'ikili_aday':len(pairs), 'boyut_başına_eklenen':dict(per_size)}


def family_profiles(draws, candidates, max_gap=24):
    """Evaluate candidate events; use strictly pretest candidate pool for holdout analysis."""
    days = by_day(draws)
    rows, history_rows = [], []
    dindex = defaultdict(list)
    for k, fams in candidates.items():
        for family, info in fams.items():
            fm = nums_mask(family)
            occ = [r for r in draws if r.mask & fm == fm]
            dates = {r.day for r in occ}
            ev = {(r.day, r.pos):r for r in occ}
            tick_triples = Counter()
            day_triples = Counter()
            for r in occ:
                for g in range(1,max_gap+1):
                    b,c = ev.get((r.day,r.pos+g)),ev.get((r.day,r.pos+2*g))
                    if b and c and (c.dt-b.dt).total_seconds() == 300*g and (b.dt-r.dt).total_seconds() == 300*g:
                        tick_triples[g] += 1
                for g in DAY_GAPS:
                    b,c = ev.get((r.day + timedelta(days=g),r.pos)),ev.get((r.day+timedelta(days=2*g),r.pos))
                    if b and c:
                        day_triples[g] += 1
            same_day = Counter()
            same_gap = Counter()
            for r in occ:
                for g in range(1,max_gap+1):
                    if (r.day,r.pos+g) in ev:
                        same_day[g] += 1
                for g in DAY_GAPS:
                    if (r.day+timedelta(days=g),r.pos) in ev:
                        same_gap[g] += 1
            strongest = max([('çekiliş',g,n) for g,n in tick_triples.items()] +
                            [('gün',g,n) for g,n in day_triples.items()], key=lambda x:x[2], default=None)
            rows.append({'Boyut':k, 'Aile':'-'.join(map(str,family)), **info,
                         'Görünüş':len(occ), 'Aktif gün':len(dates),
                         'Aynı-gün ikili bağ':sum(same_day.values()), 'Günler-arası ikili bağ':sum(same_gap.values()),
                         'Üçlü aynı rakam / çekiliş':sum(tick_triples.values()),
                         'Üçlü aynı rakam / gün':sum(day_triples.values()),
                         'En güçlü üçlü ritim': f'{strongest[0]} +{strongest[1]} ({strongest[2]})' if strongest else 'yok',
                         'Son görünüş':occ[-1].dt.strftime('%d.%m.%Y %H:%M') if occ else '',
                         'Üçlü tekrar toplam':sum(tick_triples.values()) + sum(day_triples.values())})
            for r in occ:
                history_rows.append({'Boyut':k,'Aile':'-'.join(map(str,family)),
                                     'Tarih':r.day.isoformat(),'Saat':r.dt.strftime('%H:%M'),
                                     'Günlük sıra':r.pos,'Çekiliş':r.id})
    profiles=pd.DataFrame(rows)
    if not profiles.empty:
        profiles=profiles.sort_values(['Üçlü tekrar toplam','Görünüş','Boyut'],ascending=[False,False,False]).reset_index(drop=True)
    return profiles,pd.DataFrame(history_rows)


def forecast_exact_third(draws, candidates, target_date, min_chain=2, horizon=12, max_gap=24):
    """Two historic exact occurrences + proven triple chains => future third event candidates."""
    days = by_day(draws)
    today = days.get(target_date, {})
    if not today:
        return pd.DataFrame()
    latest = max(today)
    rows=[]
    for k, families in candidates.items():
        for family in families:
            fm=nums_mask(family)
            hits=[r for r in draws if r.dt.date()<=target_date and r.mask & fm == fm]
            ev={(r.day,r.pos):r for r in hits}
            historical_trip=Counter()
            for a in hits:
                for g in range(1,max_gap+1):
                    b,c=ev.get((a.day,a.pos+g)),ev.get((a.day,a.pos+2*g))
                    if b and c and (b.dt-a.dt).total_seconds()==300*g:
                        historical_trip[('çekiliş',g)]+=1
                for g in DAY_GAPS:
                    if (a.day+timedelta(days=g),a.pos) in ev and (a.day+timedelta(days=2*g),a.pos) in ev:
                        historical_trip[('gün',g)]+=1
            if not historical_trip:
                continue
            for g in range(1,max_gap+1):
                for p in range(latest+1,min(217,latest+horizon)+1):
                    a,b=ev.get((target_date,p-2*g)),ev.get((target_date,p-g))
                    if a and b and historical_trip[('çekiliş',g)]>=min_chain:
                        rows.append({'Boyut':k,'Aile':'-'.join(map(str,family)),
                                     'Mekanizma':'Aynı rakam / çekiliş','İlk':a.dt.strftime('%H:%M'),
                                     'İkinci':b.dt.strftime('%H:%M'),'Gap':g,
                                     'Üçüncü aday':position_time(p),'Sıra':p,
                                     'Önceki üçlü zincir':historical_trip[('çekiliş',g)]})
            # Predict future DAY when a family appeared on two previous days at same slot.
            for g in DAY_GAPS:
                prior=target_date-timedelta(days=g)
                first=target_date-timedelta(days=2*g)
                if historical_trip[('gün',g)]>=min_chain:
                    for p in range(latest+1,min(217,latest+horizon)+1):
                        a,b=ev.get((first,p)),ev.get((prior,p))
                        if a and b:
                            rows.append({'Boyut':k,'Aile':'-'.join(map(str,family)),
                                         'Mekanizma':'Aynı rakam / gün','İlk':a.dt.strftime('%d.%m %H:%M'),
                                         'İkinci':b.dt.strftime('%d.%m %H:%M'), 'Gap':g,
                                         'Üçüncü aday':position_time(p),'Sıra':p,
                                         'Önceki üçlü zincir':historical_trip[('gün',g)]})
    return pd.DataFrame(rows).sort_values(['Önceki üçlü zincir','Boyut'],ascending=[False,False]) if rows else pd.DataFrame()


class GroupStat:
    __slots__ = ('n','hist','class_seen','class_hit')
    def __init__(self):
        self.n=0
        self.hist=Counter()
        self.class_seen=[0,0,0,0]
        self.class_hit=[0,0,0,0]
    def add(self, a,b,c):
        s12=(a&b).bit_count()
        s23=(b&c).bit_count()
        s123=(a&b&c).bit_count()
        self.n+=1
        self.hist[(s12,s23,s123)] += 1
        masks=(a&b, b &~a, a &~b, FULL80 &~(a|b))
        for i,mask in enumerate(masks):
            self.class_seen[i]+=mask.bit_count()
            self.class_hit[i]+=(mask & c).bit_count()
    def metrics(self,k):
        base_success=sum(n for (s1,s2,s3),n in self.hist.items() if s2>=k)
        active=sum(n for (s1,s2,s3),n in self.hist.items() if s1>=k)
        success=sum(n for (s1,s2,s3),n in self.hist.items() if s1>=k and s2>=k)
        exact=sum(n for (s1,s2,s3),n in self.hist.items() if s1>=k and s3>=k)
        return active,success,base_success,exact
    def probs(self):
        return [(h+75)/(n+300) for h,n in zip(self.class_hit,self.class_seen)]


def _group_keys(mode,gap,band):
    return ((mode,gap,band),(mode,gap,-1))


def _build_triple_events(draws,max_within=24):
    data=defaultdict(list)
    for mode,gap,a,b,c in _iter_triples(by_day(draws),max_within=max_within):
        data[c.day].append((mode,gap,c.dt.hour,c.pos,a.mask,b.mask,c.mask))
    return data


def _add_stats(stats, mode, gap, band, a,b,c):
    for key in _group_keys(mode,gap,band):
        if key not in stats:
            stats[key]=GroupStat()
        stats[key].add(a,b,c)


def base_prob(k):
    return sum(comb(20,x)*comb(60,20-x)/comb(80,20) for x in range(k, min(20,20)+1) if 20-x <=60)


def _binom_tail(n,s,p):
    # scipy is part of the package; fallback normal approximation is conservative-ish.
    from scipy.stats import binomtest
    return float(binomtest(int(s),int(n),float(p),alternative='greater').pvalue) if n else 1.0


def _best_stat(stats,mode,gap,band,k,min_train=45):
    for slot in (band,-1):
        stat=stats.get((mode,gap,slot))
        if stat:
            n,s,bs,ex=stat.metrics(k)
            if n>=min_train:
                return stat,n,s,slot
    return None


def _train_rule(stats,mode,gap,band,k,min_train=45):
    found=_best_stat(stats,mode,gap,band,k,min_train)
    if not found:
        return None
    stat,n,success,slot=found
    p0=base_prob(k)
    actual=success/n
    lift=actual/p0 if p0 else 0
    pvalue=_binom_tail(n,success,p0)
    return {'train_n':n,'train_s':success,'train_rate':actual,'baseline':p0,
            'train_lift':lift,'train_p':pvalue,'stat':stat,'band_used':slot}


def _ticket(a,b,k,st,freq,total_draws):
    props=st.probs()
    # Shrunk probabilistic feature model; every number starts at chance level 0.25.
    a_and_b=a&b
    b_only=b&~a
    a_only=a&~b
    result=[]
    for n in range(1,81):
        mask=1<<(n-1)
        cls=0 if a_and_b&mask else 1 if b_only&mask else 2 if a_only&mask else 3
        p_num=(freq[n]+25)/(total_draws+100) if total_draws else .25
        score=.25 + .85*(props[cls]-.25) + .35*(p_num-.25)
        result.append((score,-n,n))
    result.sort(reverse=True)
    return tuple(sorted(r[2] for r in result[:k]))


def walk_forward(draws, holdout_days=7, max_within=24, max_coupons_hour=6,
                 min_train=50, exploration_p=.01):
    """True rolling daily backtest. Every day's predictions precede that day's labels."""
    days=by_day(draws)
    all_days=sorted(days)
    # Only data up to the end of the requested training period should be supplied.
    if len(all_days)<12:
        return pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{}, {'uyarı':'İleri-zaman testi için en az 12 ayrı gün gerekli.'}
    holdout_days=min(holdout_days,len(all_days)-5)
    test_days=set(all_days[-holdout_days:])
    starts=min(test_days)
    events=_build_triple_events(draws,max_within=max_within)
    stats={}
    freq=Counter()
    total=0
    for d in all_days:
        if d>=starts:
            break
        for r in days[d].values():
            freq.update(r.nums);total+=1
        for mode,g,band,pos,a,b,c in events.get(d,[]):
            _add_stats(stats,mode,g,band,a,b,c)

    # Evaluate every conditioned transition, but rank coupons with training-only evidence.
    aggregate=defaultdict(lambda: [0,0,0,0])  # test active, success, exact, background
    baseline_totals=Counter()
    coupons=[]
    rules_used=Counter()
    for d in all_days:
        if d not in test_days:
            continue
        day_events=events.get(d,[])
        eligible=[]
        for mode,g,band,pos,a,b,c in day_events:
            s12=(a&b).bit_count()
            s23=(b&c).bit_count()
            s123=(a&b&c).bit_count()
            for k in FAMILY_SIZES:
                ky=(mode,g,band,k)
                baseline_totals[ky]+=int(s23>=k)
                if s12>=k:
                    rec=aggregate[ky]
                    rec[0]+=1; rec[1]+=int(s23>=k); rec[2]+=int(s123>=k)
                # Only use qualifying training model to recommend tickets.
                if s12<k:
                    continue
                rule=_train_rule(stats,mode,g,band,k,min_train)
                if rule is None or rule['train_lift']<1.15 or rule['train_p']>exploration_p:
                    continue
                ticket=_ticket(a,b,k,rule['stat'],freq,total)
                hit=sum(bool(c&(1<<(n-1))) for n in ticket)
                eligible.append({'Tarih':d.isoformat(),'Saat':position_time(pos),
                                 'Saat grubu':int(position_time(pos)[:2]),'Sıra':pos,
                                 'Boyut':k,'Motor':'Rakam değişebilir' if mode=='çekiliş' else 'Gün-saat tekrar',
                                 'Gap':g,'Aile':'-'.join(map(str,ticket)),
                                 'İsabet':hit,'Çekiliş olayı başarılı':int(s23>=k),
                                 'Train adet':rule['train_n'],'Train lift':round(rule['train_lift'],3),
                                 'Train p':rule['train_p'],'Gerçekleşti':True})
                rules_used[ky]+=1
        # Limits are decided by prior-data scores; never by actual hit.
        eligible.sort(key=lambda x:(x['Saat'], -x['Train lift'], x['Train p'], -x['Train adet']))
        quota=Counter()
        seen_slot=set()
        for entry in eligible:
            hour=entry['Saat grubu']
            if quota[hour]>=max_coupons_hour or entry['Sıra'] in seen_slot:
                continue
            quota[hour]+=1;seen_slot.add(entry['Sıra'])
            coupons.append(entry)
        # Only AFTER prediction is day d incorporated into history.
        for r in days[d].values():
            freq.update(r.nums);total+=1
        for mode,g,band,pos,a,b,c in day_events:
            _add_stats(stats,mode,g,band,a,b,c)

    validations=[]
    # Test counts must be compared to correct hypergeometric random-overlap baseline.
    for key,(n,s,exact,_) in aggregate.items():
        mode,g,band,k=key
        rate=s/n if n else 0
        p0=base_prob(k)
        validations.append({'Mekanizma':mode,'Gap':g,'Saat':band,'Boyut':k,
                            'Holdout tetik':n,'3. olay başarılı':s,'Oran':round(rate,5),
                            'Rastgele baz':round(p0,5),'Kaldıraç':round(rate/p0,4) if p0 else 0,
                            '3 çizimde aynı aile':exact,
                            'Holdout tek yön p': _binom_tail(n,s,p0) if n>=20 else 1.0})
    val=pd.DataFrame(validations)
    if not val.empty:
        tests=max(1,sum(val['Holdout tetik']>=20))
        val['Çoklu test eşiği']=.05/tests
        val['Testten geçti']= (val['Holdout tetik']>=30)&(val['Holdout tek yön p']<.05/tests)&(val['Kaldıraç']>=1.1)
        val=val.sort_values(['Testten geçti','Holdout tek yön p','Holdout tetik'],ascending=[False,True,False])
    ticket_df=pd.DataFrame(coupons)
    by_size=[]
    for k in FAMILY_SIZES:
        dd=ticket_df[ticket_df['Boyut']==k] if not ticket_df.empty else pd.DataFrame()
        n=len(dd)
        group={'Boyut':k,'Kupon':n,'Toplam isabet':int(dd['İsabet'].sum()) if n else 0,
               'Ort. isabet':round(dd['İsabet'].mean(),3) if n else 0,
               'Rastgele beklenen':round(k/4,3),
               'Maks. isabet':int(dd['İsabet'].max()) if n else 0}
        for h in range(k+1):
            group[f'{h}/{k}']=int((dd['İsabet']==h).sum()) if n else 0
        by_size.append(group)
    summary=pd.DataFrame(by_size)
    info={'eğitim_bitiş':(starts-timedelta(days=1)).isoformat(),
          'test_başlangıç':starts.isoformat(),'test_bitiş':max(test_days).isoformat(),
          'test_gün':len(test_days),'toplam_kupon':len(ticket_df),
          'geçerli_test_grubu':int(val['Testten geçti'].sum()) if not val.empty else 0,
          'yorum':'Geliştirme dönemi parametreleri sabittir; test günleri kronolojik olarak, bir günün sonuçları ancak sonraki günün eğitimine katılarak işlendi.'}
    return val,ticket_df,summary,stats,info


def live_structural(draws,target_date,stats,max_within=24,horizon=12,
                   min_train=50,max_per_hour=6,validated_keys=None):
    """Target-day future slots from preceding day/draw events only; never use future labels."""
    days=by_day(draws)
    mp=days.get(target_date,{})
    if not mp:
        return pd.DataFrame(),pd.DataFrame()
    last=max(mp)
    history=[r for r in draws if r.day<=target_date]
    freq=Counter(n for r in history for n in r.nums)
    n_hist=len(history)
    rows=[]
    for p in range(last+1,min(217,last+horizon)+1):
        target_hm=position_time(p)
        target_min=int(target_hm[:2])*60+int(target_hm[3:])
        pairs=[]
        # One, two, three instances with constant draw-count gap in same day's session.
        for gap in range(1,max_within+1):
            a,b=mp.get(p-2*gap),mp.get(p-gap)
            if a is None or b is None or (b.dt-a.dt).total_seconds()!=300*gap:
                continue
            b_min=b.dt.hour*60+b.dt.minute
            if target_min-b_min==5*gap:
                pairs.append(('çekiliş',gap,a,b))
        # Same time slot on dates d-2g,d-g,target_date, different numbers possible.
        for gap in DAY_GAPS:
            a=days.get(target_date-timedelta(days=2*gap),{}).get(p)
            b=days.get(target_date-timedelta(days=gap),{}).get(p)
            if a and b:
                pairs.append(('gün',gap,a,b))
        for mode,gap,a,b in pairs:
            shared=(a.mask&b.mask).bit_count()
            for k in FAMILY_SIZES:
                if shared<k:
                    continue
                band=int(target_hm[:2])
                rule=_train_rule(stats,mode,gap,band,k,min_train)
                if rule is None:
                    continue
                ticket=_ticket(a.mask,b.mask,k,rule['stat'],freq,n_hist)
                rows.append({'Tarih':target_date.isoformat(),'Saat':target_hm,'Sıra':p,
                             'Mekanizma':mode,'Boyut':k,'1. Çekiliş':a.id,'2. Çekiliş':b.id,'Gap':gap,
                             'İlk iki örtüşme':shared,'Train örnek':rule['train_n'],
                             'Beklenen 3. örtüşme':round(rule['train_rate'],3),
                             'Rastgele baz':round(rule['baseline'],3),
                             'Train lift':round(rule['train_lift'],3),
                             'Train p':rule['train_p'],
                             'Kupon aile':'-'.join(map(str,ticket)),
                             'Backtest doğrulama': 'EVET' if validated_keys and (mode,gap,band,k) in validated_keys else 'HAYIR'})
    candidates=pd.DataFrame(rows)
    if candidates.empty:
        return candidates,pd.DataFrame()
    eligible=candidates[(candidates['Backtest doğrulama']=='EVET') &
                        (candidates['Train lift']>=1.15)&(candidates['Train p']<=.01)].copy()
    eligible=eligible.sort_values(['Train lift','Train örnek'],ascending=[False,False])
    selected=[]
    quota=Counter()
    seen=set()
    for _,r in eligible.iterrows():
        hr=int(r['Saat'].split(':')[0]);pos=int(r['Sıra'])
        if quota[hr]>=max_per_hour or pos in seen:
            continue
        quota[hr]+=1;seen.add(pos);selected.append(r.to_dict())
    return candidates,pd.DataFrame(selected)


def report_zip(tables,notes):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name,frame in tables.items():
            if isinstance(frame,pd.DataFrame):
                z.writestr(name,frame.to_csv(index=False).encode('utf-8-sig'))
        z.writestr('99_METODOLOJI_VE_UYARILAR.txt',notes.encode('utf-8'))
    return b.getvalue()

def validate_exact_third(draws, candidates, test_dates, min_chain=2, max_gap=24):
    """Test 3rd occurrence AFTER 1st/2nd with only previous triple training. Never inspect target before predicting."""
    days=by_day(draws)
    test_dates=sorted(set(test_dates))
    rows=[]
    for k,fams in candidates.items():
        for family in fams:
            fm=nums_mask(family)
            hits=[r for r in draws if r.mask &fm == fm]
            ev={(r.day,r.pos):r for r in hits}
            for day in test_dates:
                today=days.get(day,{})
                if not today:
                    continue
                train_hits=[r for r in hits if r.day <day]
                prior_ev={(r.day,r.pos):r for r in train_hits}
                prev_tick=Counter()
                prev_day=Counter()
                for a in train_hits:
                    for gap in range(1,max_gap+1):
                        b=prior_ev.get((a.day,a.pos+gap))
                        c=prior_ev.get((a.day,a.pos+2*gap))
                        if b and c and (b.dt-a.dt).total_seconds()==300*gap and (c.dt-b.dt).total_seconds()==300*gap:
                            prev_tick[gap]+=1
                    for gap in DAY_GAPS:
                        if (a.day+timedelta(days=gap),a.pos) in prior_ev and (a.day+timedelta(days=2*gap),a.pos) in prior_ev:
                            prev_day[gap]+=1
                hits_today=[r for r in hits if r.day==day]
                tday_hits={r.pos:r for r in hits_today}
                for a in hits_today:
                    for gap in range(1,max_gap+1):
                        b=tday_hits.get(a.pos+gap)
                        target_pos=a.pos+2*gap
                        c=today.get(target_pos)
                        if prev_tick[gap]>=min_chain and b and c and (b.dt-a.dt).total_seconds()==300*gap and (c.dt-b.dt).total_seconds()==300*gap:
                            rows.append({'Tarih':day.isoformat(),'Mekanizma':'Çekiliş farkı','Boyut':k,
                                         'Aile':'-'.join(map(str,family)),'Gap':gap,
                                         '1. çekiliş':a.id,'2. çekiliş':b.id,'3. hedef':c.id,
                                         'Önceki zincir':prev_tick[gap], '3. isabet':int(c.mask&fm==fm)})
                for gap in DAY_GAPS:
                    if prev_day[gap]<min_chain:
                        continue
                    for pos,c in today.items():
                        a=prior_ev.get((day-timedelta(days=2*gap),pos))
                        b=prior_ev.get((day-timedelta(days=gap),pos))
                        if a and b:
                            rows.append({'Tarih':day.isoformat(),'Mekanizma':'Gün farkı','Boyut':k,
                                         'Aile':'-'.join(map(str,family)),'Gap':gap,
                                         '1. çekiliş':a.id,'2. çekiliş':b.id,'3. hedef':c.id,
                                         'Önceki zincir':prev_day[gap], '3. isabet':int(c.mask&fm==fm)})
    out=pd.DataFrame(rows)
    if not out.empty:
        out=out.drop_duplicates(subset=['Mekanizma','Boyut','Aile','3. hedef'])
    return out
