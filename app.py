import streamlit as st
import pandas as pd, numpy as np, json
from pathlib import Path
from collections import Counter, defaultdict

st.set_page_config(page_title='Hızlı On Şematik Sıra-Ritim V2',layout='wide')
st.title('Hızlı On — Şematik Sıra / Ritim / Devir Motoru V2')
st.caption('TEK TUŞ = TEK GÜN • 217 çekiliş tamamlanır, kaydedilir ve durur • 14/14 sonunda MASTER oluşur')

@st.cache_data
def load():
    rows=[]
    for line in Path('veri.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        a,b,c=line.split(';')
        rows.append((int(a),pd.to_datetime(b,dayfirst=True),tuple(sorted(map(int,c.split(','))))))
    d=pd.DataFrame(rows,columns=['draw_id','dt','nums']).sort_values('draw_id').reset_index(drop=True)
    d['date']=d.dt.dt.strftime('%d.%m.%Y'); d['pos']=d.groupby('date').cumcount()+1
    return d

def nearest_delta(n,prev):
    if n in prev:return 0
    return min((n-p for p in prev),key=lambda x:(abs(x),x))

def analyze_day(g):
    g=g.sort_values('draw_id').reset_index(drop=True)
    trans=[]; events=[]
    for i in range(1,len(g)):
        prev=set(g.loc[i-1,'nums']); cur=set(g.loc[i,'nums'])
        ds=[]
        for n in sorted(cur):
            de=nearest_delta(n,prev); ds.append(de)
            events.append({'from_id':int(g.loc[i-1,'draw_id']),'draw_id':int(g.loc[i,'draw_id']),'pos':i+1,'num':n,'delta':de,'abs_delta':abs(de)})
        c=Counter(ds)
        trans.append({'pos':i+1,'from_id':int(g.loc[i-1,'draw_id']),'draw_id':int(g.loc[i,'draw_id']),
            'same':c[0],'m1':c[-1],'p1':c[1],'m2':c[-2],'p2':c[2],
            'near2':sum(v for k,v in c.items() if abs(k)<=2),'far':sum(v for k,v in c.items() if abs(k)>=3),
            'mean_delta':float(np.mean(ds))})
    t=pd.DataFrame(trans); e=pd.DataFrame(events)
    # ngrams 2..6, number-specific within this day
    ng=[]
    for n,gg in e.groupby('num'):
        a=gg.sort_values('draw_id').delta.tolist()
        for k in range(2,7):
            for j in range(k,len(a)):
                ng.append((k,tuple(a[j-k:j]),a[j]))
    dd=defaultdict(Counter)
    for k,p,nxt in ng: dd[(k,p)][nxt]+=1
    ngr=[]
    for (k,p),c in dd.items():
        N=sum(c.values()); top,nc=c.most_common(1)[0]
        if N>=5: ngr.append({'k':k,'schema':str(p),'N':N,'next_delta':top,'correct':nc,'rate':nc/N})
    ngr=pd.DataFrame(ngr).sort_values(['rate','N'],ascending=False) if ngr else pd.DataFrame()
    # devir signature
    hand=[]
    for i in range(len(t)-1):
        a=t.iloc[i]; b=t.iloc[i+1]
        end=(int(np.sign(a.mean_delta)),int(a.near2>=15),int(a.same>=5))
        start=(int(np.sign(b.mean_delta)),int(b.near2>=15),int(b.same>=5))
        hand.append(end==start)
    # no-future walk forward, warmup 12
    hits=[]; freqhits=[]; hist=[]
    for i in range(1,len(g)):
        prev=set(g.loc[i-1,'nums']); cur=set(g.loc[i,'nums'])
        if i>=12:
            dc=Counter(de for rr in hist[-30:] for de in rr if abs(de)<=2)
            scores={n:sum(dc.get(n-p,0)+0.1 for p in prev if abs(n-p)<=2) for n in range(1,81)}
            pred=sorted(scores,key=lambda n:(scores[n],-n),reverse=True)[:20]
            hits.append(len(set(pred)&cur))
            past=g.loc[max(0,i-30):i-1,'nums'].tolist(); fc=Counter(n for s in past for n in s)
            fp=[n for n,_ in sorted(fc.items(),key=lambda x:(-x[1],x[0]))[:20]]
            freqhits.append(len(set(fp)&cur))
        hist.append([nearest_delta(n,prev) for n in cur])
    summary={
        'date':str(g.loc[0,'date']),'draws':len(g),'first_id':int(g.draw_id.min()),'last_id':int(g.draw_id.max()),'transitions':len(t),
        'same_avg':float(t.same.mean()),'m1_avg':float(t.m1.mean()),'p1_avg':float(t.p1.mean()),'m2_avg':float(t.m2.mean()),'p2_avg':float(t.p2.mean()),
        'near2_avg':float(t.near2.mean()),'far_avg':float(t.far.mean()),'devir_rate':float(np.mean(hand)) if hand else 0,
        'wf_n':len(hits),'schema_hit_avg':float(np.mean(hits)) if hits else 0,'freq_hit_avg':float(np.mean(freqhits)) if freqhits else 0,
        'schema_max':int(max(hits)) if hits else 0,'freq_max':int(max(freqhits)) if freqhits else 0,
        'top_schemas':ngr.head(40).to_dict('records') if not ngr.empty else []
    }
    return summary,t,e,ngr

def master_text(results):
    lines=['HIZLI ON SEMATIK SIRA RITIM MASTER V2','KURAL=TEK_TUS_TEK_GUN|GUNLER_AYRI|NO_FUTURE=EVET|BASELINE=5/20',f'TAMAMLANAN={len(results)}/14','']
    for r in results:
        lines += [f"=== {r['date']} ===",f"CEKILIS={r['draws']}|ID={r['first_id']}-{r['last_id']}|GECIS={r['transitions']}",
        f"AYNI={r['same_avg']:.4f}|-1={r['m1_avg']:.4f}|+1={r['p1_avg']:.4f}|-2={r['m2_avg']:.4f}|+2={r['p2_avg']:.4f}|YAKIN2={r['near2_avg']:.4f}|UZAK={r['far_avg']:.4f}",
        f"DEVIR={r['devir_rate']:.6f}|WF_N={r['wf_n']}|SEMA_HIT={r['schema_hit_avg']:.4f}|FREQ_HIT={r['freq_hit_avg']:.4f}|SEMA_MAX={r['schema_max']}|FREQ_MAX={r['freq_max']}",
        'TOP_SEMALAR='+json.dumps(r['top_schemas'],ensure_ascii=False),'']
    if len(results)==14:
        df=pd.DataFrame(results)
        lines += ['=== 14 GUN GENEL ===',f"SEMA_HIT_ORT={df.schema_hit_avg.mean():.4f}|FREQ_HIT_ORT={df.freq_hit_avg.mean():.4f}|YAKIN2_ORT={df.near2_avg.mean():.4f}|DEVIR_ORT={df.devir_rate.mean():.6f}"]
    return '\n'.join(lines)

d=load(); days=d.date.drop_duplicates().tolist()
if 'results' not in st.session_state: st.session_state.results=[]
if 'last_detail' not in st.session_state: st.session_state.last_detail=None
completed=len(st.session_state.results)
st.progress(completed/14,text=f'{completed}/14 gün tamamlandı')

if completed<14:
    nextday=days[completed]
    st.info(f'Sıradaki gün: {nextday} • {len(d[d.date==nextday])} çekiliş')
    if st.button(f'▶ {completed+1}. GÜNÜ TAMAMLA — {nextday}',type='primary',use_container_width=True):
        with st.spinner(f'{nextday} şematik sıra/ritim kadavrası çalışıyor...'):
            r,t,e,ng=analyze_day(d[d.date==nextday].copy())
            st.session_state.results.append(r)
            st.session_state.last_detail=(nextday,t,e,ng)
        st.rerun()
else:
    st.success('✅ 14/14 TAMAMLANDI — MASTER hazır.')

if st.session_state.results:
    rdf=pd.DataFrame(st.session_state.results)
    st.subheader('Tamamlanan günler')
    st.dataframe(rdf[['date','draws','same_avg','m1_avg','p1_avg','m2_avg','p2_avg','near2_avg','devir_rate','schema_hit_avg','freq_hit_avg','schema_max']],use_container_width=True,hide_index=True)
    backup=master_text(st.session_state.results)
    st.download_button('💾 İLERLEME / MASTER TXT',backup.encode('utf-8'),'SEMA_SIRA_RITIM_MASTER_V2.txt','text/plain',use_container_width=True)

if st.session_state.last_detail is not None:
    day,t,e,ng=st.session_state.last_detail
    with st.expander(f'Son tamamlanan günün ayrıntısı — {day}'):
        st.dataframe(t,use_container_width=True,height=360)
        if not ng.empty:
            st.markdown('**Tekrarlanan şemalar (2–6 adım)**')
            st.dataframe(ng.head(100),use_container_width=True,height=360)

if len(st.session_state.results)==14:
    st.subheader('14 Gün MASTER')
    st.download_button('⬇️ 14 GÜN MASTER SONUÇ',master_text(st.session_state.results).encode('utf-8'),'HIZLI_ON_SEMATIK_SIRA_RITIM_MASTER_V2_FINAL.txt','text/plain',use_container_width=True)

with st.expander('Kontroller'):
    st.warning('Sıfırla düğmesi 14 günlük ilerlemeyi bu oturumda siler.')
    if st.button('İlerlemeyi sıfırla'):
        st.session_state.results=[]; st.session_state.last_detail=None; st.rerun()
