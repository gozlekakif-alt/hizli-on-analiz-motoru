"""Hızlı On: 14 günlük tam yaşam ve nöbet araştırma uygulaması.
Çalıştır: pip install -r requirements.txt && streamlit run app.py
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import pandas as pd
import streamlit as st
from derin_motor import deep_analyze, detail_text, detail_zip

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'hizli_on_yasam.db'
FMT = '%d.%m.%Y %H:%M'
FIELDS = ['draw_id','draw_time','numbers']


def read_source(upload=None, github_url='', local_path='veri.txt'):
    if upload is not None:
        return upload.getvalue(), 'yüklenen dosya'
    if github_url.strip():
        url = github_url.strip()
        if 'github.com/' in url and '/blob/' in url:
            url = url.replace('github.com/', 'raw.githubusercontent.com/').replace('/blob/', '/')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'raw.githubusercontent.com','github.com'}:
            raise ValueError('GitHub adresi https://github.com veya https://raw.githubusercontent.com olmalı.')
        with urlopen(Request(url, headers={'User-Agent':'HizliOnResearch/1.0'}), timeout=25) as r:
            data = r.read(12_000_001)
        if len(data) > 12_000_000:
            raise ValueError('Dosya 12 MB sınırını aşıyor.')
        return data, url
    path = Path(local_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f'Yerel veri dosyası bulunamadı: {path}. Dosyayı yükleyin veya GitHub bağlantısı girin.')
    return path.read_bytes(), str(path)


def parse_data(raw):
    text = raw.decode('utf-8-sig')
    records, errors = [], []
    seen = set()
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(';')
        if len(parts) != 3:
            errors.append(f'Satır {line_no}: 3 noktalı virgül alanı bekleniyor.')
            continue
        try:
            draw_id = int(parts[0].strip())
            when = datetime.strptime(parts[1].strip(), FMT)
            nums = tuple(int(n.strip()) for n in parts[2].split(','))
            if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
                raise ValueError('20 farklı sayı ve 1–80 aralığı şartı bozulmuş')
            if draw_id in seen:
                raise ValueError('tekrarlanan çekiliş numarası')
            seen.add(draw_id)
            records.append({'draw_id':draw_id,'dt':when,'date':when.strftime('%d.%m.%Y'),
                            'hour':when.hour,'time':when.strftime('%H:%M'),'numbers':tuple(sorted(nums))})
        except (ValueError, TypeError) as exc:
            errors.append(f'Satır {line_no}: {exc}')
    records.sort(key=lambda x:(x['dt'],x['draw_id']))
    for a,b in zip(records,records[1:]):
        if a['dt'] == b['dt']:
            errors.append(f'Aynı zamanlı iki çekiliş: {a["draw_id"]}, {b["draw_id"]}')
    return records, errors


def csv_bytes(rows):
    if not rows: return b''
    f = io.StringIO()
    cols = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
    writer.writeheader()
    for row in rows: writer.writerow(row)
    return f.getvalue().encode('utf-8-sig')


def analyze(records):
    """All computations are chronological; future outcomes are attached only after recording pre-state."""
    by_day = defaultdict(list)
    for r in records: by_day[r['date']].append(r)
    output = {key:[] for key in ('daily','draws','transitions','lives','hours','bridges','hour_paths','first3','first3_events','patterns','alerts')}
    for date, day in by_day.items():
        day.sort(key=lambda r:r['dt'])
        hours = defaultdict(list)
        for r in day:
            if r['time']=='01:02': continue
            hours[r['hour']].append(r)
        # The 01:02 draw is a bridge, not the 13th draw of the 00:02–00:57 frequency window.
        bridge = next((r for r in day if r['time']=='01:02'),None)
        midnight = hours.get(0,[])
        morning = hours.get(7,[])
        hour_frequencies = {}
        first3_sets = {}
        for hour in sorted(hours):
            group = sorted(hours[hour], key=lambda r:r['dt'])
            freq = Counter()
            histories = {n:[] for n in range(1,81)}
            last_seen = {n:None for n in range(1,81)}
            active_positions = {n:[] for n in range(1,81)}
            prev_active = set()
            first3 = None
            for index,r in enumerate(group,1):
                active = set(r['numbers'])
                before = Counter(freq)
                transitions = defaultdict(list)
                for n in sorted(active):
                    transitions[f'{before[n]}→{before[n]+1 if before[n]<8 else "8+"}'].append(n)
                    gap = index-last_seen[n]-1 if last_seen[n] is not None else None
                    output['transitions'].append({'date':date,'hour':hour,'draw_index':index,
                       'draw_id':r['draw_id'],'time':r['time'],'number':n,'from_level':before[n],
                       'to_level':before[n]+1,'rest_draws':gap,'return':gap is not None and gap>0,
                       'first_appearance':last_seen[n] is None,'pre_hour_count':before[n],
                       'pre_day_count':sum(1 for old in day if old['dt']<r['dt'] and n in old['numbers'])})
                    freq[n]+=1
                    last_seen[n]=index
                    active_positions[n].append(index)
                for n in range(1,81): histories[n].append('1' if n in active else '0')
                exact = Counter(freq[n] for n in range(1,81))
                row = {'date':date,'hour':hour,'draw_index':index,'draw_id':r['draw_id'],
                       'time':r['time'],'active20':','.join(map(str,sorted(active))),
                       'carried_from_previous_draw':','.join(map(str,sorted(active&prev_active))),
                       'carried_count':len(active&prev_active),
                       'new_from_previous_draw':','.join(map(str,sorted(active-prev_active))),
                       'exact0':exact[0], 'exact1':exact[1], 'exact2':exact[2],
                       'exact3':exact[3], 'exact4':exact[4], 'exact5':exact[5],
                       'exact6':exact[6], 'exact7':exact[7], 'exact8plus':sum(v for k,v in exact.items() if k>=8)}
                for threshold in range(1,9):
                    row[f'level{threshold}plus']=sum(freq[n]>=threshold for n in range(1,81))
                for threshold in range(0,8):
                    row[f'new_{threshold}_to_{threshold+1}']=','.join(map(str,transitions.get(f'{threshold}→{threshold+1}',[])))
                    row[f'new_{threshold}_to_{threshold+1}_count']=len(transitions.get(f'{threshold}→{threshold+1}',[]))
                row['new_8plus']=','.join(str(n) for n in sorted(active) if before[n]>=8)
                output['draws'].append(row)
                if index==3:
                    first3={n:''.join(histories[n][:3]) for n in range(1,81)}
                    first3_sets[hour]=first3
                if first3 is not None and index>=4:
                    for n in range(1,81):
                        if first3[n].count('1')>=2:
                            output['first3_events'].append({'date':date,'hour':hour,'draw_id':r['draw_id'],
                                'time':r['time'],'number':n,'first3_pattern':first3[n],
                                'active':int(n in active),'pre_count':before[n],'post_count':freq[n],
                                'reached_4_now':int(n in active and freq[n]==4)})
                prev_active=active
            if not group: continue
            hour_frequencies[hour]={n:freq[n] for n in range(1,81)}
            for n in range(1,81):
                pos=active_positions[n]
                gaps=[b-a-1 for a,b in zip(pos,pos[1:])]
                level_times={f'level{k}_at':next((group[p-1]['time'] for p in pos if sum(1 for j in pos if j<=p)==k),'') for k in range(1,9)}
                pattern=''.join(histories[n])
                first3_pattern=(first3 or {}).get(n,'')
                output['lives'].append({'date':date,'hour':hour,'number':n,'total':freq[n],
                    'path':pattern,'active_indices':','.join(map(str,pos)),
                    'active_times':','.join(group[p-1]['time'] for p in pos),
                    'active_draw_ids':','.join(str(group[p-1]['draw_id']) for p in pos),
                    'rest_gaps':','.join(map(str,gaps)), 'max_rest_between_appearances':max(gaps,default=0),
                    'initial_wait_draws':pos[0]-1 if pos else len(group),
                    'final_wait_draws':len(group)-pos[-1] if pos else len(group),
                    'first3_pattern':first3_pattern,'first3_group':('3/3' if first3_pattern=='111' else '2/3' if first3_pattern.count('1')==2 else 'other'),
                    **level_times})
            final=Counter(freq[n] for n in range(1,81))
            output['hours'].append({'date':date,'hour':hour,'draw_count':len(group),
                'first_draw':group[0]['draw_id'],'last_draw':group[-1]['draw_id'],
                'active_4plus':','.join(str(n) for n in range(1,81) if freq[n]>=4),
                'active_4plus_count':sum(freq[n]>=4 for n in range(1,81)),
                **{f'exact{k}':final[k] for k in range(8)},
                'exact8plus':sum(v for k,v in final.items() if k>=8),
                **{f'level{k}plus':sum(freq[n]>=k for n in range(1,81)) for k in range(1,9)}})
            if first3 is not None:
                for n,pattern in first3.items():
                    rest=sum(n in r['numbers'] for r in group[3:])
                    output['first3'].append({'date':date,'hour':hour,'number':n,'pattern':pattern,
                        'first3_count':pattern.count('1'),'remaining_count':rest,'final_count':freq[n],
                        'first_return_time':next((r['time'] for r in group[3:] if n in r['numbers']),''),
                        'reached4plus':int(freq[n]>=4),
                        'reached5plus':int(freq[n]>=5),'reached6plus':int(freq[n]>=6)})
            if len(group)!=12:
                output['alerts'].append({'date':date,'scope':f'{hour:02d} saati',
                    'warning':f'{len(group)} çekiliş var; beklenen 12. Kısmi saat ayrıca gösterildi.'})
        sorted_hours=sorted(hour_frequencies)
        for h0,h1 in zip(sorted_hours,sorted_hours[1:]):
            if h0==0 and h1==7 and bridge is None:
                output['alerts'].append({'date':date,'scope':'01:02 köprüsü','warning':'01:02 eksik; gece-sabah geçişi eksik.'})
            a,b=hour_frequencies[h0],hour_frequencies[h1]
            old={n for n in a if a[n]>=4}; new={n for n in b if b[n]>=4}
            output['hour_paths'].append({'date':date,'from_hour':h0,'to_hour':h1,
                'continuing':','.join(map(str,sorted(old&new))), 'continuing_count':len(old&new),
                'exiting':','.join(map(str,sorted(old-new))), 'exiting_count':len(old-new),
                'entering':','.join(map(str,sorted(new-old))), 'entering_count':len(new-old),
                'bridge_0102':int(h0==0 and h1==7)})
        for n in range(1,81):
            path=[hour_frequencies[h][n] for h in sorted_hours]
            if not path: continue
            output['patterns'].append({'date':date,'number':n,'hour_labels':','.join(f'{h:02d}' for h in sorted_hours),
                'hour_path':','.join(map(str,path)), 'nobet_path':''.join('1' if v>=4 else '0' for v in path),
                'hours_4plus':sum(v>=4 for v in path),'max_hour_count':max(path),
                'nobet_entries':sum(v>=4 and (i==0 or path[i-1]<4) for i,v in enumerate(path)),
                'nobet_returns_after_gap':sum(v>=4 and i>0 and path[i-1]<4 and any(p>=4 for p in path[:i-1]) for i,v in enumerate(path))})
        if bridge is not None:
            bset=set(bridge['numbers'])
            night4={n for n in range(1,81) if hour_frequencies.get(0,{}).get(n,0)>=4}
            mset=set(morning[0]['numbers']) if morning else set()
            output['bridges'].append({'date':date,'bridge_draw_id':bridge['draw_id'],
                'bridge_time':bridge['time'],'night4_count':len(night4),
                'night4_to_0102':','.join(map(str,sorted(night4&bset))),
                'night4_to_0102_count':len(night4&bset),
                'bridge_to_0702':','.join(map(str,sorted(bset&mset))) if morning else '',
                'bridge_to_0702_count':len(bset&mset) if morning else '',
                'night4_bridge_morning':','.join(map(str,sorted(night4&bset&mset))) if morning else '',
                'morning_present':int(bool(morning)),
                'note':'01:02 tek köprü çekilişidir; 01:02→07:02 arası çekilişsiz zaman dinlenme sayılmaz.'})
        else:
            output['alerts'].append({'date':date,'scope':'köprü','warning':'01:02 çekilişi bulunamadı.'})
        expected=217
        output['daily'].append({'date':date,'draw_count':len(day),'expected_draw_count':expected,
            'complete':int(len(day)==expected),'hour_count':len(hours),
            'bridge_present':int(bridge is not None),
            'first_draw':day[0]['draw_id'],'last_draw':day[-1]['draw_id'],
            'unique_numbers':len(set(n for r in day for n in r['numbers'])),
            'total_4plus_hour_memberships':sum(row['active_4plus_count'] for row in output['hours'] if row['date']==date)})
        if len(day)!=expected:
            output['alerts'].append({'date':date,'scope':'gün','warning':f'{len(day)} çekiliş var; beklenen {expected}.'})
    return output


def make_report(data, errors, source, digest):
    daily=data['daily']; hours=data['hours']; paths=data['hour_paths']; first=data['first3']
    lines=['HIZLI ON — 14 GÜNLÜK BİRLEŞİK YAŞAM VE NÖBET ARAŞTIRMASI',
           f'Kaynak: {source}',f'SHA256: {digest}',f'Gün: {len(daily)} | Çekiliş: {sum(x["draw_count"] for x in daily)}',
           'NOT: Gelecek gerçekleşmeleri geriye dönük gözlemdir, önceden üretilmiş tahmin değildir.',
           'SAAT: :02–:57 arası 12 çekiliş. 01:02 özel köprü; 01:02→07:02 arası çekilişsiz zaman dinlenme değildir.',
           '1+…8+ en az o kadar kez görünen sayıları ifade eder; tam1…tam7 ayrı frekanslardır.','']
    for d in daily:
        date=d['date']; hh=[h for h in hours if h['date']==date]
        lines.extend(['='*85,f'GÜN {date} | {d["draw_count"]}/217 çekiliş | {len(hh)} saat | köprü={d["bridge_present"]}',
                      'SAATLİK FREKANS VE EŞİK DAĞILIMI'])
        for h in hh:
            lines.append(f'{h["hour"]:02d}: {h["draw_count"]} el | 1+:{h["level1plus"]} 2+:{h["level2plus"]} 3+:{h["level3plus"]} 4+:{h["level4plus"]} 5+:{h["level5plus"]} 6+:{h["level6plus"]} 7+:{h["level7plus"]} 8+:{h["level8plus"]} | 4+ kadro: {h["active_4plus"]}')
        lines.append('NÖBET DEVRİ')
        for p in paths:
            if p['date']==date:
                lines.append(f'{p["from_hour"]:02d}→{p["to_hour"]:02d} | devam {p["continuing_count"]}: {p["continuing"]} | çıkan {p["exiting_count"]}: {p["exiting"]} | giren {p["entering_count"]}: {p["entering"]} | köprü={p["bridge_0102"]}')
        lines.append('İLK ÜÇ ÇEKİLİŞ ADAYLARI')
        for h in hh:
            f=[r for r in first if r['date']==date and r['hour']==h['hour'] and r['first3_count']>=2]
            if f: lines.append(f'{h["hour"]:02d}: aday {len(f)} | 4+ {sum(x["reached4plus"] for x in f)} | 5+ {sum(x["reached5plus"] for x in f)} | 6+ {sum(x["reached6plus"] for x in f)}')
        lines.append('80 SAYININ SAATLER ARASI YAŞAM YOLU')
        for p in data['patterns']:
            if p['date']==date: lines.append(f'{p["number"]:02d}: saatler {p["hour_labels"]} | frekans {p["hour_path"]} | nöbet {p["nobet_path"]} | 4+ saat {p["hours_4plus"]} | geri dönüş {p["nobet_returns_after_gap"]}')
        for b in data['bridges']:
            if b['date']==date: lines.append(f'01:02 KÖPRÜ: gece4→01:02 [{b["night4_to_0102"]}]; 01:02→07:02 [{b["bridge_to_0702"]}]; üçlü [{b["night4_bridge_morning"]}]')
        lines.append('')
    lines.extend(['VERİ HATALARI / UYARILAR',*errors,*[f'{r["date"]} {r["scope"]}: {r["warning"]}' for r in data['alerts']]])
    lines.extend(['','DETAYLAR: ZIP içindeki cekilis_donusumleri.csv, sayi_tam_yasam.csv, esik_gecisleri.csv, ilk3_olaylari.csv ve diğer tablolar tüm kimlik ve zamanları içerir.'])
    return '\n'.join(lines).encode('utf-8-sig')


def build_zip(data, report, errors, raw, source, digest):
    mem=io.BytesIO()
    names={'daily':'gun_ozetleri','draws':'cekilis_donusumleri','transitions':'esik_gecisleri',
           'lives':'sayi_tam_yasam','hours':'saat_ozetleri','bridges':'0102_kopruleri',
           'hour_paths':'nobet_devirleri','first3':'ilk3_aday_sonuclari',
           'first3_events':'ilk3_cekilis_olaylari','patterns':'saatler_arasi_yasam_yollari','alerts':'veri_uyarilari'}
    with zipfile.ZipFile(mem,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('14_GUN_TEK_BIRLESIK_RAPOR.txt',report)
        z.writestr('kaynak_veri.txt',raw)
        z.writestr('manifest.json',json.dumps({'source':source,'sha256':digest,'day_count':len(data['daily']),
           'draw_count':sum(d['draw_count'] for d in data['daily']),'parse_errors':errors,
           'method':'chronological observational research; no future leakage in pre-state'},ensure_ascii=False,indent=2))
        for key,name in names.items(): z.writestr(name+'.csv',csv_bytes(data[key]))
        for d in data['daily']:
            date=d['date'].replace('.','_')
            for key in ('draws','lives','transitions','hours','bridges','hour_paths','first3','patterns'):
                z.writestr(f'gunler/{date}/{names[key]}.csv',csv_bytes([r for r in data[key] if r['date']==d['date']]))
    return mem.getvalue()


def save_sqlite(data,digest):
    with sqlite3.connect(DB) as conn:
        for key,rows in data.items():
            if not rows: continue
            df=pd.DataFrame(rows)
            df['source_sha256']=digest
            df.to_sql(key,conn,if_exists='replace',index=False)
        conn.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT)')
        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('source_sha256',digest))
        conn.commit()

st.set_page_config(page_title='Hızlı On | 14 Günlük Yaşam Motoru',layout='wide')
st.title('Hızlı On — 14 Günlük Tam Yaşam ve Nöbet Araştırma Motoru')
st.caption('0→1→2→3→4→5→6→7→8+ | 80 sayı | gün gün | 01:02 köprüsü | tek ZIP ve birleşik TXT')
with st.sidebar:
    st.header('Veri kaynağı')
    uploaded=st.file_uploader('veri.txt yükle',type=['txt'])
    github=st.text_input('GitHub veri.txt adresi (raw veya blob)',value='',placeholder='https://raw.githubusercontent.com/.../veri.txt')
    local=st.text_input('Yerel dosya yolu',value='veri.txt')
    st.caption('Öncelik: yükleme → GitHub → yerel dosya. GitHub bağlantısı burada saklanmaz; tekrar açışta yeniden girilebilir.')
    run=st.button('14 günü analiz et',type='primary',use_container_width=True)

if run:
    try:
        with st.spinner('Veri okunuyor, kronolojik analiz yapılıyor...'):
            raw,source=read_source(uploaded,github,local)
            digest=hashlib.sha256(raw).hexdigest()
            records,errors=parse_data(raw)
            if not records: raise ValueError('Geçerli çekiliş bulunamadı.')
            result=analyze(records)
            deep=deep_analyze(records)
            deep_report=detail_text(deep,source,digest)
            deep_bundle=detail_zip(deep,deep_report,raw,source,digest)
            report=make_report(result,errors,source,digest)
            bundle=build_zip(result,report,errors,raw,source,digest)
            save_sqlite(result,digest)
            st.session_state['analysis']=(result,report,bundle,errors,source,digest,deep,deep_report,deep_bundle)
    except Exception as exc:
        st.error(f'Analiz tamamlanamadı: {exc}')

if 'analysis' not in st.session_state:
    st.info('veri.txt dosyasını yükle, GitHub bağlantısını gir veya yerel veri.txt dosyasını yerleştir; ardından analizi başlat.')
    st.stop()

data,report,bundle,errors,source,digest,deep,deep_report,deep_bundle=st.session_state['analysis']
st.success(f'{len(data["daily"])} gün, {sum(d["draw_count"] for d in data["daily"])} çekiliş analiz edildi. Kaynak: {source}')
if errors or data['alerts']:
    st.warning(f'{len(errors)} satır hatası, {len(data["alerts"])} kapsam uyarısı var. Veri uyarıları sekmesinden inceleyin.')
col1,col2=st.columns(2)
with col1: st.download_button('14 günün TEK birleşik TXT raporunu indir',report,'HIZLI_ON_14_GUN_BIRLESIK_TAM_ANALIZ.txt','text/plain',use_container_width=True)
with col2: st.download_button('14 günün TÜM detaylarını TEK ZIP indir',bundle,'HIZLI_ON_14_GUN_TUM_ANALIZLER.zip','application/zip',use_container_width=True)

st.subheader('DERİN ANALİZ — 14 GÜN TEK DOSYA')
st.download_button('14 GÜNÜN TÜM YAŞAM KAYITLARINI TEK TXT İNDİR',deep_report,'14_GUN_TUM_DETAYLAR_TEK_DOSYA.txt','text/plain',use_container_width=True)
st.download_button('14 GÜNÜN TÜM DETAYLI CSV + TXT DOSYALARINI TEK ZIP İNDİR',deep_bundle,'HIZLI_ON_14_GUN_DERIN_ANALIZ.zip','application/zip',use_container_width=True)
st.caption('Derin motor: 80 sayı × her çekiliş durum kaydı; 1+–8+ tam kadrolar, eşik doğumları, dinlenme, tam saat/gün yaşam yolu, 8 seviyede saatler arası nöbet ve 01:02 köprüsü.')
dates=[r['date'] for r in data['daily']]
selected=st.selectbox('Gün seç',dates)
tabs=st.tabs(['Gün özeti','Çekiliş dönüşümü','80 sayının yaşamı','Eşik geçişleri','İlk 3 ve kalan 9','Nöbet devri','01:02 köprüsü','14 gün toplu','Veri uyarıları'])
with tabs[0]:
    st.dataframe(pd.DataFrame([r for r in data['hours'] if r['date']==selected]),use_container_width=True,hide_index=True)
with tabs[1]:
    rows=[r for r in data['draws'] if r['date']==selected]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
with tabs[2]:
    number=st.slider('Sayı',1,80,1)
    rows=[r for r in data['lives'] if r['date']==selected and r['number']==number]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.dataframe(pd.DataFrame([r for r in data['lives'] if r['date']==selected]),use_container_width=True,hide_index=True)
with tabs[3]:
    rows=[r for r in data['transitions'] if r['date']==selected]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
with tabs[4]:
    st.dataframe(pd.DataFrame([r for r in data['first3'] if r['date']==selected]),use_container_width=True,hide_index=True)
    st.dataframe(pd.DataFrame([r for r in data['first3_events'] if r['date']==selected]),use_container_width=True,hide_index=True)
with tabs[5]:
    st.dataframe(pd.DataFrame([r for r in data['hour_paths'] if r['date']==selected]),use_container_width=True,hide_index=True)
    st.dataframe(pd.DataFrame([r for r in data['patterns'] if r['date']==selected]),use_container_width=True,hide_index=True)
with tabs[6]:
    st.dataframe(pd.DataFrame([r for r in data['bridges'] if r['date']==selected]),use_container_width=True,hide_index=True)
with tabs[7]:
    st.dataframe(pd.DataFrame(data['daily']),use_container_width=True,hide_index=True)
    st.dataframe(pd.DataFrame(data['hour_paths']),use_container_width=True,hide_index=True)
with tabs[8]:
    for e in errors: st.write(e)
    st.dataframe(pd.DataFrame(data['alerts']),use_container_width=True,hide_index=True)
st.subheader('Derin yaşam incelemesi')
selected_table=st.selectbox('Derin analiz tablosu',list(deep.keys()))
selected_rows=[r for r in deep[selected_table] if r.get('date')==selected or 'date' not in r]
if selected_table in ('number_draw_state','number_hour_life','number_day_life','bridge_number_states'):
    focus=st.number_input('İncelenecek sayı (0 = hepsi)',min_value=0,max_value=80,value=0,key='deep_focus')
    if focus:selected_rows=[r for r in selected_rows if r.get('number')==focus]
st.dataframe(pd.DataFrame(selected_rows),use_container_width=True,hide_index=True)
st.caption('Araştırma gözlemseldir. Sonradan görülen sonuçlar önceden bilinen sinyal olarak değerlendirilmez. Kupon motoru bu sürümde kasıtlı olarak eklenmemiştir.')
