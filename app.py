# -*- coding: utf-8 -*-
"""Hızlı On V9 — real draw, checkpointed rhythm research.
Single-file app, no imports from old motor.py.  Python 3.10+.
"""
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
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np

RAW_URL = 'https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt'
BAND_40 = (1 << 40) - 1
GAP_DAYS = (2, 5, 7, 14)
SQL_BATCH = 2500

@dataclass(frozen=True)
class Draw:
    ident: int
    dt: datetime
    day: str
    pos: int
    lo: int
    hi: int
    mask: int


def draw_pos(dt):
    minutes = dt.hour * 60 + dt.minute
    if 2 <= minutes <= 62 and (minutes - 2) % 5 == 0:
        return 1 + (minutes - 2) // 5
    if 422 <= minutes <= 1437 and (minutes - 422) % 5 == 0:
        return 14 + (minutes - 422) // 5
    return None


def read_data(txt):
    draws, problems, seen_id, seen_dt = [], [], set(), set()
    for no, raw in enumerate(txt.splitlines(), 1):
        if not re.match(r'^\s*\d+\s*;', raw):
            continue
        fields = raw.strip().split(';')
        if len(fields) != 3:
            problems.append((no, '3 alan bulunamadi', raw[:90])); continue
        try:
            ident = int(fields[0]); dt = datetime.strptime(fields[1].strip(), '%d.%m.%Y %H:%M')
            nums = [int(x) for x in fields[2].split(',')]
            if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= x <= 80 for x in nums):
                raise ValueError('20 benzersiz sayi bulunmuyor')
            pos = draw_pos(dt)
            if pos is None: raise ValueError('takvim disi dakika')
            if ident in seen_id or dt in seen_dt: raise ValueError('cift cekilis numarasi veya zaman')
            seen_id.add(ident); seen_dt.add(dt)
            mask = sum(1 << (n - 1) for n in nums)
            draws.append(Draw(ident, dt, dt.date().isoformat(), pos, mask & BAND_40, mask >> 40, mask))
        except Exception as exc:
            problems.append((no, str(exc), raw[:90]))
    draws.sort(key=lambda x: x.dt)
    days = defaultdict(list)
    for d in draws: days[d.day].append(d)
    missing = []
    for day, recs in days.items():
        observed = {r.pos for r in recs}
        for slot in sorted(set(range(1,218)) - observed):
            missing.append((day, slot))
    return draws, dict(sorted(days.items())), problems, missing


def family_text(combo):
    return '-'.join(f'{x:02d}' for x in combo)


def family_numbers(label):
    return tuple(map(int, label.split('-')))


def mask_nums(mask):
    return tuple(i + 1 for i in range(80) if (mask >> i) & 1)


def discover_same_day(recs):
    """All exact 5..10 families in any three draws on one day (not only consecutive)."""
    if len(recs) < 3: return []
    lo = np.array([r.lo for r in recs], dtype=np.uint64)
    hi = np.array([r.hi for r in recs], dtype=np.uint64)
    found = set()
    for i in range(len(recs) - 2):
        for j in range(i + 1, len(recs) - 1):
            two_lo = int(lo[i]) & int(lo[j]); two_hi = int(hi[i]) & int(hi[j])
            if two_lo.bit_count() + two_hi.bit_count() < 5: continue
            thirds_lo = lo[j+1:] & np.uint64(two_lo)
            thirds_hi = hi[j+1:] & np.uint64(two_hi)
            counts = np.bitwise_count(thirds_lo) + np.bitwise_count(thirds_hi)
            for offset in np.flatnonzero(counts >= 5):
                m = int(thirds_lo[offset]) | (int(thirds_hi[offset]) << 40)
                nums = mask_nums(m)
                for k in range(5, min(10, len(nums)) + 1):
                    for combo in itertools.combinations(nums, k):
                        found.add((k, family_text(combo)))
    return sorted(found)


def discover_cross_day(a, b, sizes):
    """Exact same 8/9/10 family in any draw from each of two days.
    Only date differences explicitly scheduled by prepare_units are analyzed.
    """
    if not a or not b or not sizes: return []
    min_k = min(sizes)
    blo = np.array([r.lo for r in b], dtype=np.uint64)
    bhi = np.array([r.hi for r in b], dtype=np.uint64)
    found = set()
    for d in a:
        shared_lo = blo & np.uint64(d.lo)
        shared_hi = bhi & np.uint64(d.hi)
        for i in np.flatnonzero(np.bitwise_count(shared_lo) + np.bitwise_count(shared_hi) >= min_k):
            common = int(shared_lo[i]) | (int(shared_hi[i]) << 40)
            nums = mask_nums(common)
            for k in sizes:
                if k <= len(nums):
                    for combo in itertools.combinations(nums, k):
                        found.add((k, family_text(combo)))
    return sorted(found)


def make_units(days, deep=True):
    keys = sorted(days)
    units = [('GUN_ICI', d, '') for d in keys]
    lookup = set(keys)
    for d in keys:
        for gap in GAP_DAYS:
            to_day = (date.fromisoformat(d) + timedelta(days=gap)).isoformat()
            if to_day in lookup:
                units.append(('GUNLER_ARASI', d, str(gap)))
    return units


def open_store(path, fingerprint):
    con = sqlite3.connect(str(path), timeout=60)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    con.execute('PRAGMA temp_store=MEMORY')
    con.execute('PRAGMA cache_size=-14000')
    con.execute('CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS families (family TEXT PRIMARY KEY, k INTEGER NOT NULL, sources INTEGER NOT NULL DEFAULT 0)')
    con.execute('CREATE TABLE IF NOT EXISTS units (phase TEXT, d TEXT, gap TEXT, done INTEGER DEFAULT 0, families_found INTEGER DEFAULT 0, PRIMARY KEY(phase,d,gap))')
    con.execute('CREATE TABLE IF NOT EXISTS summary (family TEXT PRIMARY KEY,k INTEGER,active_days INTEGER,total_hits INTEGER,max_daily INTEGER,three_days INTEGER,four_days INTEGER,day2 INTEGER,day5 INTEGER,day7 INTEGER,day14 INTEGER,longest_chain INTEGER,chain_gap INTEGER,repeated_pair_days INTEGER,repeated_triple_days INTEGER,repeated_quad_days INTEGER,types TEXT,repeat_details TEXT,three_detail TEXT,day_chain TEXT,all_appearances TEXT,source INTEGER)')
    prev = con.execute("SELECT v FROM meta WHERE k='fingerprint'").fetchone()
    if prev is None:
        con.execute("INSERT INTO meta VALUES ('fingerprint',?)",(fingerprint,))
        con.execute("INSERT INTO meta VALUES ('summary_cursor','')")
    elif prev[0] != fingerprint:
        con.close()
        raise ValueError('Bu veritabani farkli veriye ait. Baska bir veri veya ayarla ayni veritabani kullanilamaz.')
    # Upward compatible with an earlier local checkpoint of this app.
    cols={x[1] for x in con.execute('PRAGMA table_info(summary)')}
    if 'repeat_details' not in cols:
        con.execute('ALTER TABLE summary ADD COLUMN repeat_details TEXT')
    con.commit()
    return con


def install_units(con, units):
    con.executemany('INSERT OR IGNORE INTO units(phase,d,gap) VALUES(?,?,?)', units)
    con.commit()


def pending_unit(con):
    return con.execute("SELECT phase,d,gap FROM units WHERE done=0 ORDER BY CASE phase WHEN 'GUN_ICI' THEN 0 ELSE 1 END,d,gap LIMIT 1").fetchone()


def do_unit(con, days, unit, deep=True):
    phase, d, gapstr = unit
    if phase == 'GUN_ICI':
        fams = discover_same_day(days[d]); source = 1
    else:
        gap = int(gapstr)
        d2 = (date.fromisoformat(d) + timedelta(days=gap)).isoformat()
        # To keep Streamlit Cloud bounded: 8-10 all pairs only for +2/+5;
        # all 10 exact families for +7/+14, including single occurrence each day.
        sizes = (8,9,10) if deep and gap in (2,5) else (9,10) if gap in (2,5) else (10,)
        fams = discover_cross_day(days[d], days[d2], sizes)
        source = 2
    con.execute('BEGIN')
    try:
        con.executemany('INSERT INTO families(family,k,sources) VALUES(?,?,?) ON CONFLICT(family) DO UPDATE SET sources=sources | excluded.sources', ((fam,k,source) for k,fam in fams))
        con.execute('UPDATE units SET done=1, families_found=? WHERE phase=? AND d=? AND gap=?',(len(fams),phase,d,gapstr))
        con.commit()
    except BaseException:
        con.rollback(); raise
    return len(fams)


def vertical_bits(draws):
    masks = [0]*80
    for i,d in enumerate(draws):
        m=d.mask
        while m:
            low=m & -m
            masks[low.bit_length()-1] |= 1 << i
            m ^= low
    return masks


def exact_indices(fam, bits):
    nums = family_numbers(fam)
    if not nums: return []
    v=bits[nums[0]-1]
    for n in nums[1:]:
        v &= bits[n-1]
        if not v: return []
    out=[]
    while v:
        b = v & -v
        out.append(b.bit_length()-1)
        v ^= b
    return out


def analyse_family(fam, k, source, draws, bits):
    indexes=exact_indices(fam, bits)
    dayhits=defaultdict(list)
    for i in indexes: dayhits[draws[i].day].append(draws[i])
    active=sorted(dayhits); actset=set(active)
    daycount={day:len(recs) for day,recs in dayhits.items()}
    days3=sum(v>=3 for v in daycount.values())
    days4=sum(v>=4 for v in daycount.values())
    common_patterns=defaultdict(set)
    pair_pats=defaultdict(set); quad_pats=defaultdict(set)
    shapes=Counter()
    triple_events=[]
    for day,recs in sorted(dayhits.items()):
        pos=[r.pos for r in recs]
        for a,b in itertools.combinations(pos,2):pair_pats[b-a].add(day)
        for a,b,c in itertools.combinations(pos,3):
            g1,g2=b-a,c-b
            common_patterns[(g1,g2)].add(day)
            shapes['SABIT' if g1==g2 else 'ARTAN' if g2>g1 else 'AZALAN']+=1
        for a,b,c,e in itertools.combinations(pos,4):
            g1,g2,g3=b-a,c-b,e-c
            quad_pats[(g1,g2,g3)].add(day)
            if g1==g2==g3:shapes['4LU_SABIT']+=1
            elif g1<g2<g3:shapes['4LU_ARTAN']+=1
            elif g1>g2>g3:shapes['4LU_AZALAN']+=1
            elif (g1<g2>g3) or (g1>g2<g3):shapes['4LU_DONUSLU']+=1
            else:shapes['4LU_KARISIK']+=1
        if len(recs)>=3:
            tt=' / '.join(f'{r.dt:%H:%M}(#{r.ident},s{r.pos})' for r in recs)
            triple_events.append(f'{day}: {tt}')
    rpair={p:ds for p,ds in pair_pats.items() if len(ds)>=2}
    rtriple={p:ds for p,ds in common_patterns.items() if len(ds)>=2}
    rquad={p:ds for p,ds in quad_pats.items() if len(ds)>=2}
    repeated=[]
    for gap,active_dates in sorted(rpair.items()):
        repeated.append('2li +'+str(gap)+':'+','.join(sorted(active_dates)))
    for gaps,active_dates in sorted(rtriple.items()):
        repeated.append('3lu '+ '-'.join(map(str,gaps))+':'+','.join(sorted(active_dates)))
    for gaps,active_dates in sorted(rquad.items()):
        repeated.append('4lu '+ '-'.join(map(str,gaps))+':'+','.join(sorted(active_dates)))
    bestchain=[];bestgap=0; allchains=[]
    for gap in range(1,31):
        for first in active:
            if (date.fromisoformat(first)-timedelta(days=gap)).isoformat() in actset: continue
            chain=[first]
            while True:
                nxt=(date.fromisoformat(chain[-1])+timedelta(days=gap)).isoformat()
                if nxt not in actset: break
                chain.append(nxt)
            if len(chain)>=3:
                allchains.append(f'+{gap}: '+', '.join(chain))
            if len(chain)>len(bestchain):bestchain=chain;bestgap=gap
    def hasgap(g):
        return sum((date.fromisoformat(d)+timedelta(days=g)).isoformat() in actset for d in active)
    appearances=[]
    for day,recs in sorted(dayhits.items()):
        appearances.append(day+': '+', '.join(f'{r.dt:%H:%M}(#{r.ident},s{r.pos})' for r in recs))
    return (fam,k,len(active),len(indexes),max(daycount.values(),default=0),days3,days4,
            hasgap(2),hasgap(5),hasgap(7),hasgap(14),len(bestchain),bestgap,
            len(rpair),len(rtriple),len(rquad),
            '|'.join(f'{nm}:{shapes[nm]}' for nm in ('SABIT','ARTAN','AZALAN','4LU_SABIT','4LU_ARTAN','4LU_AZALAN','4LU_DONUSLU','4LU_KARISIK') if shapes[nm]),
            ' || '.join(repeated),' || '.join(triple_events),
            ' || '.join(allchains), ' || '.join(appearances), source)


SUMMARY_HEADERS = ['Aile','Boyut','Aktif_Gun','Toplam_Gorunus','En_Fazla_Gunluk','3_Artı_Gun','4_Artı_Gun',
                   '+2_Gun_Bag','+5_Gun_Bag','+7_Gun_Bag','+14_Gun_Bag','En_Uzun_Zincir',
                   'Zincir_Gap','Farkli_Gun_Ayni_2li_Aralik','Farkli_Gun_Ayni_3lu_Aralik',
                   'Farkli_Gun_Ayni_4lu_Aralik','Ritim_Turleri','Tekrarlanan_Ritimler_Tarihleri', '3_4_Gorunus_Saat_Cekilis',
                   'Gun_Zincirleri','Tum_Gorunusler_Tarih_Saat_Cekilis','Kaynak_Bayragi']
SUMMARY_COLS = ['family','k','active_days','total_hits','max_daily','three_days','four_days','day2','day5',
                'day7','day14','longest_chain','chain_gap','repeated_pair_days','repeated_triple_days',
                'repeated_quad_days','types','repeat_details','three_detail','day_chain','all_appearances','source']


def do_summaries(con, draws, bits, batch=250):
    cursor = con.execute("SELECT v FROM meta WHERE k='summary_cursor'").fetchone()[0]
    rows=con.execute('SELECT family,k,sources FROM families WHERE family>? ORDER BY family LIMIT ?', (cursor,batch)).fetchall()
    if not rows:return 0
    info=[analyse_family(fam,k,source,draws,bits) for fam,k,source in rows]
    columns=','.join(SUMMARY_COLS)
    ph=','.join('?' for _ in SUMMARY_COLS)
    con.execute('BEGIN')
    try:
        con.executemany(f'INSERT OR REPLACE INTO summary ({columns}) VALUES ({ph})',info)
        con.execute('UPDATE meta SET v=? WHERE k=?',(rows[-1][0],'summary_cursor'))
        con.commit()
    except BaseException:
        con.rollback();raise
    return len(info)


def unit_counts(con):
    done,total=con.execute('SELECT COALESCE(SUM(done),0),COUNT(*) FROM units').fetchone()
    count=con.execute('SELECT COUNT(*) FROM families').fetchone()[0]
    summary=con.execute('SELECT COUNT(*) FROM summary').fetchone()[0]
    return done,total,count,summary


def finish_ready(con):
    done,total,fams,sums=unit_counts(con)
    return total>0 and done==total and fams==sums


def status_summary(con):
    return con.execute('SELECT k, COUNT(*), SUM(three_days>0), SUM(four_days>0), SUM(day2>0), SUM(day5>0), SUM(longest_chain>=3) FROM summary GROUP BY k ORDER BY k').fetchall()


def export_zip(db, draws, issues, missing, destination):
    con=sqlite3.connect(str(db),timeout=30)
    try:
        done,total,fams,sums=unit_counts(con)
        if done<total or fams>sums:raise ValueError('Analiz tamamlanmadan tam rapor uretilemez.')
        overview={"donem":f'{draws[0].day} / {draws[-1].day}' if draws else '',
                  'cekilis':len(draws),'farkli_gun':len(set(d.day for d in draws)),
                  'aile_adedi':fams,'birim':total, 'hatali_satir':len(issues),
                  'eksik_yuva':len(missing),
                  'tanim':'Tum gorunus: ailenin TUM sayilarinin tek cekiliste bulunmasi.',
                  'kapsam':'GUN ICI 3+ bulunan 5-10 tum tam aileler; GUNLER ARASI +2/+5 icin 8-10 (Derin), +7/+14 icin 10; k=5-7 gunler arasi iliskiler gun ici kesfedilen aileler icin izlenir.'}
        with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
            z.writestr('00_OKU_BENI_VE_OZET.json',json.dumps(overview,ensure_ascii=False,indent=2))
            z.writestr('01_VERI_SORUNLARI.csv',csv_csv([('Satir', 'Sorun','Ham')]+list(issues)))
            z.writestr('02_EKSIK_CEKILIS_YUVALARI.csv',csv_csv([('Tarih','Gunluk_Sira')]+list(missing)))
            all_sql='SELECT '+','.join(SUMMARY_COLS)+' FROM summary ORDER BY k, family'
            # Master shortlist stays small and usable on phones; detailed rows stay in separate size CSVs.
            master_fields=['k','family','active_days','total_hits','three_days','four_days','day2','day5','day7','day14','longest_chain','chain_gap','repeated_pair_days','repeated_triple_days','repeated_quad_days','source']
            master_headers=['Boyut','Aile','Aktif_Gun','Gorunus','3plus_Gun','4plus_Gun','+2_Gun','+5_Gun','+7_Gun','+14_Gun','Zincir','Zincir_Gap','Tekrar_2li','Tekrar_3lu','Tekrar_4lu','Kaynak']
            write_query_csv(z, '03_TEK_ANA_AILE_SECIM_LISTESI.csv', con,
                            'SELECT '+','.join(master_fields)+' FROM summary WHERE three_days>0 OR four_days>0 OR longest_chain>=3 OR repeated_pair_days>0 OR repeated_triple_days>0 OR repeated_quad_days>0 ORDER BY longest_chain DESC,three_days DESC,k DESC',master_headers)
            write_query_csv(z, '03B_TUM_KESFEDILEN_AILE_INDEKSI.csv', con,
                            'SELECT '+','.join(master_fields)+' FROM summary ORDER BY k, family',master_headers)
            # Separate reports: independently browse family sizes without requiring Excel to open all.
            for k in range(5,11):
                write_query_csv(z,f'04_{k}LI_AILELER.csv',con,
                                'SELECT '+','.join(SUMMARY_COLS)+' FROM summary WHERE k=? ORDER BY three_days DESC, four_days DESC, longest_chain DESC, active_days DESC, family', SUMMARY_HEADERS,(k,))
            write_query_csv(z,'05_FARKLI_GUNLER_2_5_7_14.csv',con,
                            'SELECT '+','.join(SUMMARY_COLS)+' FROM summary WHERE day2>0 OR day5>0 OR day7>0 OR day14>0 ORDER BY k DESC, longest_chain DESC, day2+day5 DESC', SUMMARY_HEADERS)
            write_query_csv(z,'06_GUN_ICI_3_VE_4_GORUNUS.csv',con,
                            'SELECT '+','.join(SUMMARY_COLS)+' FROM summary WHERE three_days>0 ORDER BY k DESC, four_days DESC, three_days DESC', SUMMARY_HEADERS)
            write_query_csv(z,'07_FARKLI_GUN_AYNI_RITIM.csv',con,
                            'SELECT '+','.join(SUMMARY_COLS)+' FROM summary WHERE repeated_pair_days>0 OR repeated_triple_days>0 OR repeated_quad_days>0 ORDER BY repeated_triple_days DESC, repeated_quad_days DESC, repeated_pair_days DESC', SUMMARY_HEADERS)
            write_query_csv(z,'08_UZUN_GUN_ZINCIRLERI.csv',con,
                            'SELECT '+','.join(SUMMARY_COLS)+' FROM summary WHERE longest_chain>=3 ORDER BY longest_chain DESC,k DESC',SUMMARY_HEADERS)
            write_query_csv(z,'09_10LU_OZEL_2_5_GUN.csv',con,
                            'SELECT '+','.join(SUMMARY_COLS)+' FROM summary WHERE k=10 AND (day2>0 OR day5>0) ORDER BY longest_chain DESC,day2+day5 DESC,family',SUMMARY_HEADERS)
            notes='''YOLDAŞ — ANALIZ BILGI NOTU

KUPON URETILMEZ. Bu program once tum gercek aile gorunuslerini gun, saat ve cekilis numarasiyla raporlar.
Gun ici uc gorunus kesfi: 5-10 lu herhangi bir aile uc AYRI cekiliste butun sayilariyla tam bulunmussa kesfedilir; ardarda olmak zorunda degildir.
Gunler arasi ek kesif: ayni gun uc kez bulunmayan 10 lu aileleri de +2,+5,+7,+14 gun farkli cekilislerden kesfeder.
Derin modda 8 ve 9 lu ailelerin +2 ve +5 gun baglari da kesfedilir. 5,6,7 li gunler arasi tarama, gun ici kesfedilen ailelerle sinirlidir; tum evrensel 5 li ikili gun kombinasyonlarini cikarmak pratik olarak cok buyuktur.
Gunluk sira gercek takvimden hesaplanir; eksik yuvalar bir sonraki cekilisi kaydirmaz.
Ritim_Tekrari_Detay: Gun icindeki ayni +cekilis araligi (2li) veya aralik dizisi (3lu/4lu) ve goruldugu farkli gunler.
03 secim listesi oncelikli aileler; 03B butun kesfedilen adaylarin eksiksiz indeksi.
Tum gorunuslerde aile sayilarinin AYNI CEKILISTE tamami bulunur; bir gunde ayri ayri gorulmeleri yeterli DEGILDIR.
3/4 gorunus saatleri = tarih | saat (#cekilis_no, s=gun icinde sira) ayrintisi.
Farkli gun ritimlerinde gunler arasi baglar, gun icinde sabit/artan/azalan ritimler ayri tutulur.
Zincir = ayni k sayinin gun araligiyla gorunmesi; saatini veya sonraki tam kuponu garantilemez.
Bu veri onceki cekilislerden secilerek bulundu; gercek ileri zaman testinin yerine gecmez.
Cloud makine yeniden kurulursa yerel sqlite ilerlemesi kaybolabilir: ara yedek indiriniz.
'''
            z.writestr('99_METODOLOJI.txt',notes)
    finally:con.close()
    return destination


def csv_csv(rows):
    mem=io.StringIO(); w=csv.writer(mem,delimiter=';');w.writerows(rows)
    return ('\ufeff'+mem.getvalue()).encode('utf8')


def write_query_csv(z, name, con, query, headers, args=()):
    with z.open(name,'w',force_zip64=True) as out:
        wrapped=io.TextIOWrapper(out,encoding='utf-8-sig',newline='',write_through=True)
        writer=csv.writer(wrapped,delimiter=';',quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        for row in con.execute(query,args):writer.writerow(row)
        wrapped.flush()
        wrapped.detach()


def main():
    import streamlit as st
    import requests
    st.set_page_config(page_title='Hızlı On V9 | Gerçek Derin Ritim',page_icon='🎯',layout='wide',initial_sidebar_state='collapsed')
    st.title('🎯 Hızlı On V9 — Gerçek Aile ve Ritim Taraması')
    st.caption('5–10 aile · saat / çekiliş no · gün içi 3–4 görünüş · farklı gün +2/+5/+7/+14 · tek ZIP')
    st.info('Önce rapor, sonra aile seçimi. Bu program kupon üretmez; geçmişte görülen ritim gelecek isabeti garanti etmez.')
    with st.expander('Kaynak ve çalışma ayarları',expanded=False):
        url=st.text_input('GitHub veri.txt (RAW)',value=RAW_URL)
        uploaded=st.file_uploader('İstersen TXT dosyanı yükle',type=['txt'])
        deep=st.checkbox('DERİN: +2/+5 günlerde 8’li–10’lu ailelerin tamamını keşfet',value=True,
                          help='Daha çok aile ve daha büyük rapor. Kapalıysa +2/+5 için 9 ve 10 keşfi yapılır.')
        st.caption('+7/+14 günlerde 10’lu aile keşfi de yapılır. 5–7’lilerin günler arası tekrarları, gün içi keşfedilen adaylarda izlenir.')
    @st.cache_data(ttl=300,show_spinner=False)
    def get_raw(u):
        res=requests.get(u,timeout=45);res.raise_for_status();return res.content.decode('utf-8-sig')
    st.caption('Yüksek boyutlu tarama saatler sürebilir. Her gün/gün çifti ayrı kaydedilir; ekran açıkken otomatik devam eder.')
    if st.button('📥 Veriyi hazırla / yenile',type='primary'):
        try:
            val=uploaded.getvalue().decode('utf-8-sig') if uploaded else get_raw(url)
            draws, days, issues, missing=read_data(val)
            if not draws: st.error('20 benzersiz sayılı geçerli çekiliş bulunamadı.');st.stop()
            h=hashlib.sha256(val.encode('utf8')).hexdigest()
            fingerprint=h+('_deep' if deep else '_standard')
            folder=Path(tempfile.gettempdir())/'hizli_on_v9_analiz';folder.mkdir(exist_ok=True)
            path=folder/f'{fingerprint[:16]}_{"d" if deep else "s"}.sqlite'
            st.session_state['v9']={'txt':val,'hash':h,'fingerprint':fingerprint,'db':str(path),'deep':deep}
            st.session_state['v9_run']=False
            st.session_state.pop('v9_zip',None)
            st.session_state.pop('v9_backup',None)
        except Exception as exc: st.error('Veri alinamadi: '+str(exc))
    if 'v9' not in st.session_state:
        st.warning('Önce “Veriyi hazırla / yenile” düğmesine bas.');return
    cfg=st.session_state['v9'];draws, days, issues, missing=read_data(cfg['txt'])
    con=open_store(cfg['db'],cfg['fingerprint']);install_units(con,make_units(days))
    done,total,fams,sums=unit_counts(con)
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Çekiliş',f'{len(draws):,}'.replace(',','.'))
    c2.metric('Gün',len(days))
    c3.metric('Bulunan aile',f'{fams:,}'.replace(',','.'))
    c4.metric('Özetlenen aile',f'{sums:,}'.replace(',','.'))
    st.progress(min(1.,done/max(1,total)),text=f'Aile keşfi: {done}/{total} parça tamamlandı')
    if issues:st.warning(f'{len(issues)} sorunlu satır ayrı raporlanacak; sessizce düzeltme yapılmayacak.')
    if missing:st.caption(f'{len(missing)} eksik çekiliş yuvası var; gerçek saat sırası korunuyor.')
    left,right=st.columns(2)
    with left:
        if st.button('▶️ Analizi başlat / sürdür',type='primary'):
            st.session_state['v9_run']=True
    with right:
        if st.button('⏸️ Sonraki parçadan sonra durdur'):
            st.session_state['v9_run']=False
    status=st.empty()
    if st.session_state.get('v9_run'):
        try:
            # A short bounded unit per rerun prevents one long, unresponsive request.
            if done<total:
                last=None; count=0
                for _ in range(4):
                    step=pending_unit(con)
                    if step is None:break
                    count+=do_unit(con,days,step,cfg['deep'])
                    last=step
                status.success(f'Kaydedilen son parça: {last[0]} · {last[1]} · {last[2]} · bu adımda {count:,} aile adayı')
            elif sums<fams:
                bits=vertical_bits(draws)
                processed=0
                for _ in range(10):
                    n=do_summaries(con,draws,bits,batch=2000)
                    processed+=n
                    if n==0:break
                status.info(f'Aile ayrıntıları oluşturuldu: +{processed} aile (kaydedildi)')
            else:
                st.session_state['v9_run']=False
                status.success('Bütün parçalar ve rapor hesaplamaları tamamlandı.')
            con.close()
            st.rerun()  # display completion panel immediately when the last unit finishes
        except Exception as exc:
            st.session_state['v9_run']=False
            st.error('Parça tamamlanamadı; önceki tamamlanan parçalar korunuyor: '+str(exc))
            con.close()
        return
    if done == total and sums < fams:
        st.warning(f'Keşif tamamlandı. Aile özetlerinin {sums:,}/{fams:,} kısmı yazıldı. Sürdür düğmesine bas.')
    if finish_ready(con):
        st.success('✅ Derin analiz tamamlandı. Tek ZIP rapor hazır.')
        st.caption('Ana listede güçlü ritim adayları öne alınır. Ayrı boyut dosyaları tüm keşfedilmiş ailelerin saat ve çekilişlerini içerir.')
        st.dataframe([{'Boyut':t[0],'Aile':t[1],'Gün içinde 3+':t[2],'4+':t[3],'+2 gün':t[4],'+5 gün':t[5],'3+ gün zinciri':t[6]} for t in status_summary(con)],use_container_width=True,hide_index=True)
        if st.button('📦 Tüm sonuçları tek ZIP olarak hazırla'):
            output=Path(tempfile.gettempdir())/f'HIZLI_ON_V9_5_10_TUM_RITIM_RAPORU_{cfg["hash"][:10]}.zip'
            with st.spinner('CSV raporları diske aktarılıyor...'):
                export_zip(cfg['db'],draws,issues,missing,output)
            st.session_state['v9_zip']=str(output)
        zpath=st.session_state.get('v9_zip')
        if zpath and os.path.isfile(zpath):
            with open(zpath,'rb') as inp:st.download_button('⬇️ TEK ZIP RAPORUNU İNDİR',inp,file_name='HIZLI_ON_V9_TUM_AILE_RITIMLERI.zip',mime='application/zip',type='primary')
    with st.expander('Ara yedek — bağlantı kesilirse devam',expanded=False):
        st.caption('Cloud yeniden kurulursa yedek önemlidir. Uygulama açıkken normal ilerleme kaydedilir.')
        if st.button('SQLite güvenli yedek hazırla'):
            target=Path(tempfile.gettempdir())/'hizli_v9_checkpoint.sqlite'
            back=sqlite3.connect(str(target))
            try:con.backup(back)
            finally:back.close()
            st.session_state['v9_backup']=str(target)
        if st.session_state.get('v9_backup') and Path(st.session_state['v9_backup']).exists():
            with open(st.session_state['v9_backup'],'rb') as inp:
                st.download_button('⬇️ İlerleme yedeğini indir',inp,file_name='hizli_v9_checkpoint.sqlite',mime='application/octet-stream')
        u=st.file_uploader('Önceki ilerleme yedeğini geri yükle (.sqlite)',type=['sqlite'],key='restore')
        if u and st.button('Bu yedeği kullan'):
            try:
                # Validate backup's own hash before replacing database.
                t=Path(tempfile.gettempdir())/'hizli_v9_candidate_restore.sqlite';t.write_bytes(u.getvalue())
                cc=sqlite3.connect(str(t));finger=cc.execute("SELECT v FROM meta WHERE k='fingerprint'").fetchone();cc.close()
                if not finger or finger[0]!=cfg['fingerprint']:raise ValueError('Yedek mevcut veri ve tarama profiline ait degil.')
                con.close()
                import shutil
                shutil.copy2(t,cfg['db'])
                st.success('Yedek geri yüklendi.');st.rerun()
            except Exception as exc:st.error(str(exc))
    con.close()

if __name__=='__main__': main()
