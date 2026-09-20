"""Detaylı 0–8+ yaşam motoru. Yalnızca standart Python kullanır."""
from collections import Counter, defaultdict
from datetime import datetime
import io, csv, json, zipfile

LEVELS=range(1,9)

def join(xs): return ','.join(map(str,sorted(xs)))

def deep_analyze(records):
    """Çekiliş sırası korunur. Saatlik 01:02 köprüsü ayrı, günlük akışın içindedir."""
    by_day=defaultdict(list)
    for r in records: by_day[r['date']].append(r)
    result={k:[] for k in ('number_draw_state','draw_level_rosters','threshold_events','number_hour_life','number_day_life','hour_cohorts','hour_level_changes','level_hour_shift','bridge_number_states','day_level_summary','aggregate_levels','warnings')}
    for date,day in by_day.items():
        day=sorted(day,key=lambda r:(r['dt'],r['draw_id']))
        day_count=Counter(); day_seen={n:[] for n in range(1,81)}
        hour_groups=defaultdict(list)
        for r in day:
            if r['time']!='01:02': hour_groups[r['hour']].append(r)
        hour_freqs={}; hour_last={}; hour_pos={}
        prev_draw=set()
        for day_index,r in enumerate(day,1):
            active=set(r['numbers'])
            for n in range(1,81):
                before=day_count[n]; prior=day_seen[n]
                gap=(day_index-prior[-1]-1) if prior else None
                if n in active:
                    day_count[n]+=1; day_seen[n].append(day_index)
                result['number_draw_state'].append({'date':date,'day_index':day_index,'draw_id':r['draw_id'],'time':r['time'],
                  'number':n,'active':int(n in active),'pre_day_count':before,'post_day_count':day_count[n],
                  'pre_day_level':min(before,8),'post_day_level':min(day_count[n],8),
                  'pre_last_seen_index':prior[-1] if prior and n not in active else (prior[-2] if len(prior)>1 else '') if n in active else '',
                  'rest_draws_on_return':gap if n in active and gap is not None else '',
                  'first_day_appearance':int(n in active and before==0),'carried_from_previous':int(n in active and n in prev_draw),
                  'bridge_draw':int(r['time']=='01:02')})
            prev_draw=active
        for n in range(1,81):
            positions=day_seen[n]
            result['number_day_life'].append({'date':date,'number':n,'total_day':day_count[n],
              'active_day_indices':join(positions),'active_draw_ids':join(day[i-1]['draw_id'] for i in positions),
              'active_times':','.join(day[i-1]['time'] for i in positions),
              'full_day_binary_path':''.join('1' if i in positions else '0' for i in range(1,len(day)+1)),
              'rest_gaps':','.join(str(b-a-1) for a,b in zip(positions,positions[1:])),
              'first_wait':positions[0]-1 if positions else len(day),'last_wait':len(day)-positions[-1] if positions else len(day),
              'threshold_draws':';'.join(f'{k}:{day[positions[k-1]-1]["draw_id"]}' for k in LEVELS if len(positions)>=k)})
        for hour in sorted(hour_groups):
            group=sorted(hour_groups[hour],key=lambda r:r['dt']); counts=Counter(); pos={n:[] for n in range(1,81)}
            initial_three={}; previous_exact={n:0 for n in range(1,81)}
            for ix,r in enumerate(group,1):
                active=set(r['numbers']); before=counts.copy(); transitions=defaultdict(list)
                for n in active:
                    counts[n]+=1; pos[n].append(ix)
                    transitions[(before[n],counts[n])].append(n)
                    gap=ix-pos[n][-2]-1 if len(pos[n])>=2 else ''
                    result['threshold_events'].append({'date':date,'hour':hour,'draw_index':ix,'draw_id':r['draw_id'],
                      'time':r['time'],'number':n,'from_exact':before[n],'to_exact':counts[n],
                      'to_8plus':int(counts[n]>=8),'rest_draws':gap,'is_return':int(gap!='' and gap>0),
                      'pre_state_only':before[n]})
                exact={k:join(n for n in range(1,81) if counts[n]==k) for k in range(0,9)}
                roster={'date':date,'hour':hour,'draw_index':ix,'draw_id':r['draw_id'],'time':r['time'],
                        'active20':join(active),'active_1plus':join(n for n in active if counts[n]>=1),
                        'active_existing':join(n for n in active if before[n]>=1),
                        'new_first_time':join(n for n in active if before[n]==0)}
                for k in range(9):
                    roster[f'exact{k}_numbers']=exact[k] if k<8 else join(n for n in range(1,81) if counts[n]>=8)
                    roster[f'exact{k}_count']=sum(counts[n]==k for n in range(1,81)) if k<8 else sum(counts[n]>=8 for n in range(1,81))
                for k in LEVELS:
                    roster[f'{k}plus_numbers']=join(n for n in range(1,81) if counts[n]>=k)
                    roster[f'{k}plus_count']=sum(counts[n]>=k for n in range(1,81))
                    roster[f'new_level{k}_numbers']=join(transitions[(k-1,k)])
                    roster[f'new_level{k}_count']=len(transitions[(k-1,k)])
                roster['above8_numbers']=join(n for n in active if before[n]>=8)
                result['draw_level_rosters'].append(roster)
                if ix==3: initial_three={n:sum(n in q['numbers'] for q in group[:3]) for n in range(1,81)}
                if ix>=4:
                    for k in range(0,9):
                        newly=transitions[(k,k+1)]
                        if newly:
                            result['hour_level_changes'].append({'date':date,'hour':hour,'draw_index':ix,'draw_id':r['draw_id'],
                              'time':r['time'],'transition':f'{k}→{k+1}','numbers':join(newly),'count':len(newly)})
            hour_freqs[hour]=dict(counts); hour_last[hour]=group[-1]
            hour_pos[hour]=pos
            for n in range(1,81):
                positions=pos[n]; gaps=[b-a-1 for a,b in zip(positions,positions[1:])]
                row={'date':date,'hour':hour,'number':n,'total':counts[n],
                    'path':''.join('1' if i in positions else '0' for i in range(1,len(group)+1)),
                    'cumulative_path':','.join(str(sum(p<=i for p in positions)) for i in range(1,len(group)+1)),
                    'active_indices':join(positions),'active_draw_ids':join(group[p-1]['draw_id'] for p in positions),
                    'active_times':','.join(group[p-1]['time'] for p in positions),
                    'rest_gaps':','.join(map(str,gaps)),'rest_return_count':sum(g>0 for g in gaps),
                    'max_rest':max(gaps,default=0),'first_wait':positions[0]-1 if positions else len(group),
                    'last_wait':len(group)-positions[-1] if positions else len(group),
                    'first3_count':initial_three.get(n,''),'first3_pattern':''.join(str(n in q['numbers'])*1 for q in group[:3]) if len(group)>=3 else '',
                    'last9_count':sum(n in q['numbers'] for q in group[3:]),
                    'first_return_after_first3':next((q['time'] for q in group[3:] if n in q['numbers']),''),
                    'last9_4plus_reached':int(counts[n]>=4)}
                for k in LEVELS:
                    row[f'level{k}_draw_id']=group[positions[k-1]-1]['draw_id'] if len(positions)>=k else ''
                    row[f'level{k}_time']=group[positions[k-1]-1]['time'] if len(positions)>=k else ''
                    row[f'level{k}_index']=positions[k-1] if len(positions)>=k else ''
                    row[f'level{k}_wait_from_prior']=positions[k-1]-positions[k-2]-1 if len(positions)>=k and k>1 else ''
                result['number_hour_life'].append(row)
            cohorts=defaultdict(list)
            for n in range(1,81): cohorts[counts[n] if counts[n]<8 else 8].append(n)
            cohort={'date':date,'hour':hour,'draw_count':len(group)}
            for k in range(9):
                cohort[f'exact{k}_numbers']=join(cohorts[k]);cohort[f'exact{k}_count']=len(cohorts[k])
            for k in LEVELS:
                cohort[f'{k}plus_numbers']=join(n for n in range(1,81) if counts[n]>=k)
                cohort[f'{k}plus_count']=sum(counts[n]>=k for n in range(1,81))
            result['hour_cohorts'].append(cohort)
            if len(group)!=12:result['warnings'].append({'date':date,'issue':f'{hour:02d} saatinde {len(group)} çekiliş, 12 bekleniyor'})
        hs=sorted(hour_freqs)
        for h0,h1 in zip(hs,hs[1:]):
            for k in LEVELS:
                a={n for n in range(1,81) if hour_freqs[h0].get(n,0)>=k}
                b={n for n in range(1,81) if hour_freqs[h1].get(n,0)>=k}
                result['level_hour_shift'].append({'date':date,'from_hour':h0,'to_hour':h1,'level':k,
                    'continued':join(a&b),'continued_count':len(a&b),'exited':join(a-b),'exited_count':len(a-b),
                    'entered':join(b-a),'entered_count':len(b-a),'bridge_0102':int(h0==0 and h1==7)})
        bridge=next((r for r in day if r['time']=='01:02'),None)
        morning=hour_groups.get(7,[])
        night=hour_freqs.get(0,{})
        if bridge:
            bset=set(bridge['numbers']);mset=set(morning[0]['numbers']) if morning else set()
            for n in range(1,81):
                result['bridge_number_states'].append({'date':date,'number':n,'night_count':night.get(n,''),
                  'night_level':min(night.get(n,0),8),'night_4plus':int(night.get(n,0)>=4),
                  'bridge_0102_active':int(n in bset),'morning_0702_active':int(n in mset) if morning else '',
                  'night4_bridge_morning':int(night.get(n,0)>=4 and n in bset and n in mset) if morning else '',
                  'gap_draws_0102_to_0702':0 if morning else '',
                  'note':'01:02→07:02 arasında çekiliş yok; saat farkı dinlenme değildir.'})
        else:result['warnings'].append({'date':date,'issue':'01:02 köprüsü eksik'})
        summary={'date':date,'draw_count':len(day),'hour_count':len(hs),'bridge_present':int(bool(bridge))}
        for k in LEVELS:
            summary[f'hour_memberships_{k}plus']=sum(sum(hour_freqs[h].get(n,0)>=k for n in range(1,81)) for h in hs)
            summary[f'distinct_numbers_{k}plus']=sum(any(hour_freqs[h].get(n,0)>=k for h in hs) for n in range(1,81))
        result['day_level_summary'].append(summary)
        if len(day)!=217:result['warnings'].append({'date':date,'issue':f'{len(day)} çekiliş, 217 bekleniyor'})
    for k in LEVELS:
        rows=[r for r in result['hour_cohorts']]
        result['aggregate_levels'].append({'level':k,'days':len(by_day),'hours':len(rows),
          'total_hour_memberships':sum(r[f'{k}plus_count'] for r in rows),
          'mean_memberships_per_hour':round(sum(r[f'{k}plus_count'] for r in rows)/len(rows),4) if rows else 0,
          'hours_with_any':sum(r[f'{k}plus_count']>0 for r in rows),
          'transitions_into_level':sum(r['to_exact']==k for r in result['threshold_events'])})
    return result


def detail_text(data,source,sha):
    out=['HIZLI ON — 14 GÜN TAM DETAYLI 0→1→2→3→4→5→6→7→8+ YAŞAM KÜTÜĞÜ',
         f'KAYNAK: {source}',f'SHA256: {sha}',
         'Yöntem: günler bağımsız; saat :02–:57 12 çekiliş; 01:02 özel köprü; çekilişsiz süre dinlenme değil.',
         'Gelecek yaşam kayıtları gözlenen sonuçtur, önceden tahmin değildir.','']
    keys=('day_level_summary','hour_cohorts','draw_level_rosters','hour_level_changes','threshold_events','number_hour_life','number_day_life','level_hour_shift','bridge_number_states','aggregate_levels','warnings')
    for key in keys:
        out.extend(['\n'+'='*100, f'BÖLÜM: {key} | {len(data[key])} kayıt','='*100])
        for row in data[key]:
            out.append(' | '.join(f'{k}={v}' for k,v in row.items()))
    return '\n'.join(out).encode('utf-8-sig')


def detail_zip(data,full_text,raw,source,sha):
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('14_GUN_TUM_DETAYLAR_TEK_DOSYA.txt',full_text)
        z.writestr('kaynak_veri.txt',raw)
        z.writestr('manifest.json',json.dumps({'source':source,'sha256':sha,'tables':{k:len(v) for k,v in data.items()}},ensure_ascii=False,indent=2))
        for key,rows in data.items():
            if not rows:continue
            buff=io.StringIO();writer=csv.DictWriter(buff,fieldnames=list(dict.fromkeys(c for row in rows for c in row)))
            writer.writeheader();writer.writerows(rows)
            z.writestr(f'analizler/{key}.csv',buff.getvalue().encode('utf-8-sig'))
            if key!='aggregate_levels':
                for date in dict.fromkeys(row['date'] for row in rows if 'date' in row):
                    subset=[r for r in rows if r.get('date')==date]
                    if not subset:continue
                    buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=writer.fieldnames);w.writeheader();w.writerows(subset)
                    z.writestr(f'gunler/{date.replace(".","_")}/{key}.csv',buf.getvalue().encode('utf-8-sig'))
    return mem.getvalue()
