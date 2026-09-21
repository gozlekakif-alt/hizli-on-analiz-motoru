import io,re,hashlib,zipfile
from pathlib import Path
from collections import Counter,defaultdict
import pandas as pd

DAYS=pd.date_range('2026-08-25','2026-09-07').date
COLUMNS=['draw_id','draw_time','numbers']
def parse_data(raw):
    text=raw.decode('utf-8-sig') if isinstance(raw,bytes) else raw
    rows=[]
    for line in text.splitlines():
        m=re.fullmatch(r'\s*(\d+)\s*;\s*(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})\s*;\s*([\d,\s]+)\s*',line)
        if m:rows.append((int(m[1]),pd.to_datetime(m[2],format='%d.%m.%Y %H:%M'),tuple(map(int,m[3].replace(' ','').split(',')))))
    if not rows:
        for block in re.split(r'(?im)(?=^\s*(?:#+\s*)?Çekiliş\s*no\s*:\s*\d+)',text):
            m=re.search(r'(?i)Çekiliş\s*no\s*:\s*(\d+)',block)
            if not m:continue
            dt=re.search(r'(\d{2})[./-](\d{2})[./-](\d{4})\s*[-– ]\s*(\d{2}):(\d{2})',block)
            if not dt:raise ValueError(f'#{m[1]} tarih/saat yok')
            d,mo,y,h,mi=dt.groups()
            nums=[int(s.strip()) for s in block[dt.end():].splitlines() if re.fullmatch(r'\s*\d{1,2}\s*',s)]
            rows.append((int(m[1]),pd.Timestamp(f'{y}-{mo}-{d} {h}:{mi}'),tuple(nums)))
    if not rows:
        try:
            df=pd.read_csv(io.StringIO(text))
            if set(COLUMNS).issubset(df.columns):
                rows=[(int(r.draw_id),pd.Timestamp(r.draw_time),tuple(map(int,str(r.numbers).split(',')))) for r in df.itertuples()]
        except Exception:pass
    if not rows:raise ValueError('veri.txt biçimi tanınmadı: çekiliş no;tarih saat;20 sayı bekleniyor.')
    df=pd.DataFrame(rows,columns=['draw_id','draw_time','nums']).sort_values('draw_time').reset_index(drop=True)
    if df.draw_id.duplicated().any() or df.draw_time.duplicated().any():raise ValueError('Tekrarlanan çekiliş numarası veya zaman')
    for r in df.itertuples():
        if len(r.nums)!=20 or len(set(r.nums))!=20 or any(n<1 or n>80 for n in r.nums):raise ValueError(f'#{r.draw_id}: 20 benzersiz sayı şartı bozuk')
    return df

def analyse(df):
    df=df[df.draw_time.dt.date.isin(DAYS)].copy()
    if df.empty:raise ValueError('25.08–07.09.2026 araştırma verisi yok')
    details=[]; hours=[]; days=[]; transitions=[]; predictions=[]; issues=[]; day_paths=[]; day_thresholds=[]
    for date,g in df.groupby(df.draw_time.dt.date,sort=True):
        dayrows=g.sort_values('draw_time'); daycounter=Counter(); last_seen={}; previous_hour={}; day_hits=0;day_forecasts=0;day_index=0;history_nums=[];day_streak=Counter();day_hit_ids=defaultdict(list);day_hit_times=defaultdict(list);day_first_threshold={}
        for hour,group in dayrows.groupby(dayrows.draw_time.dt.hour,sort=True):
            group=group.sort_values('draw_time'); items=list(group.itertuples()); nrows=len(items)
            if hour==1:
                if nrows!=1:issues.append(f'{date} 01 köprü: {nrows} çekiliş')
            elif nrows!=12:issues.append(f'{date} saat {hour:02d}: {nrows}/12 çekiliş')
            # Each hour analysed independently, prior hour profile available only from preceding completed hour.
            first=Counter(n for r in items[:3] for n in r.nums) if nrows==12 else Counter()
            hc=Counter(); hour_forecasts=0;hour_hits=0
            for pos,r in enumerate(items,1):
                actual=set(r.nums)
                # Frozen, simple chronological benchmark. No current draw leakage; abstain without any earlier draw that day.
                history=history_nums[-12:]
                if history:
                    recent=Counter(n for nums in history for n in nums)
                    picks=sorted(range(1,81),key=lambda n:(-recent[n],n))[:20]
                    hit=len(actual.intersection(picks));hour_forecasts+=1;hour_hits+=hit;day_forecasts+=1;day_hits+=hit
                    predictions.append({'tarih':str(date),'cekilis':r.draw_id,'saat':r.draw_time.strftime('%H:%M'),'tahmin_oncesi_20':','.join(map(str,sorted(picks))),'gercek_20':','.join(map(str,sorted(actual))),'isabet':hit,'model':'Sabit son-12 frekans kıyası'})
                else:
                    predictions.append({'tarih':str(date),'cekilis':r.draw_id,'saat':r.draw_time.strftime('%H:%M'),'tahmin_oncesi_20':'','gercek_20':','.join(map(str,sorted(actual))),'isabet':None,'model':'Gün başlangıcı: tahmin yok'})
                for n in range(1,81):
                    before=hc[n];seen=n in actual;prev_day=daycounter[n];prior_streak=day_streak[n];age=(day_index-last_seen[n]-1) if n in last_seen else None
                    if nrows==12:
                        details.append({'tarih':str(date),'saat':hour,'cekilis':r.draw_id,'el':pos,'sayi':n,'ilk3_grubu':first[n] if pos>=4 else None,'saat_oncesi':before,'gun_oncesi':prev_day,'gun_sonrasi':prev_day+int(seen),'gun_onceki_durum':f'{prev_day}+', 'gun_sonraki_durum':f'{prev_day+int(seen)}+', 'gun_kesintisiz_oncesi':prior_streak,'gun_kesintisiz_sonrasi':prior_streak+1 if seen else 0,'gun_4_esigi_bu_elde':int(seen and prev_day==3),'gun_5_esigi_bu_elde':int(seen and prev_day==4),'gun_6_esigi_bu_elde':int(seen and prev_day==5),'gun_7_esigi_bu_elde':int(seen and prev_day==6),'gun_8_esigi_bu_elde':int(seen and prev_day==7),'onceki_saat_toplam':previous_hour.get(n,None),'uyku_el':age,'cikti':int(seen),'saat_sonrasi':before+int(seen),'4_esigi_bu_elde':int(seen and before==3),'5_esigi_bu_elde':int(seen and before==4),'6_esigi_bu_elde':int(seen and before==5),'7_esigi_bu_elde':int(seen and before==6),'8_esigi_bu_elde':int(seen and before==7)})
                    if seen and nrows==12 and pos>=4:transitions.append({'tarih':str(date),'saat':hour,'cekilis':r.draw_id,'el':pos,'sayi':n,'ilk3_grubu':first[n],'oncesi':before,'sonrasi':before+1,'onceki_saat':previous_hour.get(n,None),'uyku_el':age})
                # Day state advances only after the current draw's pre-state has been recorded.
                for n in range(1,81):
                    if n in actual:
                        day_streak[n]+=1;day_hit_ids[n].append(r.draw_id);day_hit_times[n].append(r.draw_time.strftime('%H:%M'))
                        threshold=prev=daycounter[n]+1
                        if threshold>=1 and (n,threshold) not in day_first_threshold:
                            day_first_threshold[n,threshold]=(r.draw_id,r.draw_time.strftime('%H:%M'),day_index+1)
                            day_thresholds.append({'tarih':str(date),'sayi':n,'esik':threshold,'cekilis':r.draw_id,'saat':r.draw_time.strftime('%H:%M'),'gun_el':day_index+1,'onceki_gun_toplam':threshold-1})
                    else:day_streak[n]=0
                hc.update(actual);daycounter.update(actual)
                for n in actual:last_seen[n]=day_index
                history_nums.append(r.nums);day_index+=1
            if nrows==12:
                for n in range(1,81):
                    hit_els=[i for i,r in enumerate(items,1) if n in r.nums]
                    run=0;longest=0
                    for i in range(1,13):
                        run=run+1 if i in hit_els else 0;longest=max(longest,run)
                    threshold={f'ilk_{k}_el':next((i for i in range(1,13) if sum(x<=i for x in hit_els)>=k),None) for k in range(4,9)}
                    hours.append({'tarih':str(date),'saat':hour,'sayi':n,'ilk3':first[n],'son9':hc[n]-first[n],'saat_toplam':hc[n],'onceki_saat':previous_hour.get(n,None),'kesintisiz_en_uzun':longest,'ciktigi_eller':','.join(map(str,hit_els)),'ciktigi_cekilisler':','.join(str(items[i-1].draw_id) for i in hit_els),**threshold,**{f'{k}_arti':int(hc[n]>=k) for k in range(4,9)}})
            previous_hour=dict(hc)
        for n in range(1,81):
            ids=day_hit_ids[n]; times=day_hit_times[n]
            day_paths.append({'tarih':str(date),'sayi':n,'gun_toplam':daycounter[n],
                              'ciktigi_cekilisler':','.join(map(str,ids)),
                              'ciktigi_saatler':','.join(times),
                              'gun_esik_yolu':'; '.join(f'{k}+:{day_first_threshold[n,k][1]} (#{day_first_threshold[n,k][0]})' for k in range(1,daycounter[n]+1)),
                              'ilk_gorulme':times[0] if times else '',
                              'son_gorulme':times[-1] if times else ''})
        days.append({'tarih':str(date),'cekilis':len(dayrows),'saat_12_el':sum(dayrows.draw_time.dt.hour.value_counts()==12),'tahmin_sayisi':day_forecasts,'toplam_isabet':day_hits,'ortalama_isabet':round(day_hits/day_forecasts,4) if day_forecasts else None})
        if len(dayrows)!=217:issues.append(f'{date}: {len(dayrows)}/217 çekiliş')
    h=pd.DataFrame(hours);d=pd.DataFrame(details);t=pd.DataFrame(transitions);p=pd.DataFrame(predictions);day=pd.DataFrame(days)
    summary=[]
    if not h.empty:
        for group,g in h.groupby('ilk3'):
            rec={'ilk3_grubu':group,'sayi_saat_ornegi':len(g),'ortalama_saat_toplami':round(g.saat_toplam.mean(),4)}
            for k in range(4,9):rec[f'{k}_arti_adet']=int(g[f'{k}_arti'].sum());rec[f'{k}_arti_oran']=round(g[f'{k}_arti'].mean(),6)
            summary.append(rec)
    return {'gun_ozeti':day,'ilk3_esik_ozeti':pd.DataFrame(summary),'saat_80_yasam':h,'cekilis_80_oncesi':d,'esik_gecisleri':t,'gun_80_yasam_yolu':pd.DataFrame(day_paths),'gun_esik_gecisleri':pd.DataFrame(day_thresholds),'kronolojik_kiyas':p,'uyarilar':issues,'veri_sha256':hashlib.sha256(df[['draw_id','draw_time']].to_csv(index=False).encode()).hexdigest()}

def make_zip(result):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,table in result.items():
            if isinstance(table,pd.DataFrame):z.writestr(name+'.csv',table.to_csv(index=False).encode('utf-8-sig'))
        notes='14 GÜNLÜK KRONOLOJİK MOTOR\n25 Ağustos–7 Eylül 2026; saat 01:02 yalnız köprü.\nGünlük +1,+2,+3,... eşikleri 00:02 itibarıyla gün içinde kümülatiftir; hedef çekiliş öncesi gun_oncesi, sonuç sonrası gun_sonrasi alanındadır. 01:02 günlük hesaba dahildir. İlk3 grupları yalnız 4. elden itibaren bilinir. Eşik ve saat sonu sonuçları betimseldir, önceden tahmin değildir.\nKronolojik kıyas: yalnız geçmişteki son 12 çekiliş, eşitlikte küçük sayı; günün ilk elinde tahmin yok.\nBu kıyas araştırma motoru değildir; gerçek ileri dönem 8–21 Eylül ayrıca test edilmelidir.\nVeri kimlik SHA256: '+result['veri_sha256']+'\nUyarılar: '+('; '.join(result['uyarilar']) or 'yok')+'\n'
        z.writestr('OKU.txt',notes.encode('utf-8'))
    return buf.getvalue()
