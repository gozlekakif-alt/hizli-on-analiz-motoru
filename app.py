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



# =========================
# V3 — SAYI EVENT LOG
# =========================
import ast as _ast
from collections import Counter as _Counter, defaultdict as _defaultdict

def _v3_parse_embedded():
    from pathlib import Path as _Path
    import pandas as _pd
    p = _Path(__file__).parent / "veri.txt"
    rows=[]
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts=ln.strip().split(";")
        if len(parts) < 3: continue
        try:
            did=int(parts[0].strip())
            dt=_pd.to_datetime(parts[1].strip(), dayfirst=True)
            nums=sorted({int(x) for x in parts[2].replace(" ",",").split(",") if x.strip().isdigit()})
            if len(nums)==20:
                rows.append((did,dt,nums))
        except Exception:
            pass
    return _pd.DataFrame(rows, columns=["draw_id","dt","numbers"]).sort_values("draw_id").reset_index(drop=True)

def _v3_delta(prev_set, n):
    # Number identity path: exact carry=0; otherwise nearest predecessor displacement.
    # Tie is resolved toward smaller absolute signed displacement deterministically.
    if n in prev_set: return 0
    cand=[n-x for x in prev_set]
    return min(cand, key=lambda d:(abs(d), d))

def _v3_day_events(daydf, max_k=6):
    import pandas as _pd
    sets=[set(x) for x in daydf["numbers"]]
    ids=daydf["draw_id"].tolist()
    dts=daydf["dt"].tolist()
    # For every number currently REAL, record its displacement from prior REAL20.
    histories={n:[] for n in range(1,81)}
    out=[]
    for t in range(1,len(sets)):
        cur=sets[t]; prev=sets[t-1]
        for n in range(1,81):
            # path state is defined only when n is REAL at t; absence breaks the local chain
            if n in cur:
                d=_v3_delta(prev,n)
                histories[n].append((t,d))
            else:
                histories[n].append((t,None))
        # predict t+1 using only history through t
        if t+1 >= len(sets): continue
        nxt=sets[t+1]
        for n in range(1,81):
            hist=histories[n]
            # contiguous non-null tail
            tail=[]
            for _,d in reversed(hist):
                if d is None: break
                tail.append(d)
            tail=list(reversed(tail))
            for k in range(2,min(max_k,len(tail))+1):
                schema=tuple(tail[-k:])
                # empirical next-delta from prior occurrences in this number only, strictly before t
                seq=[d for _,d in hist[:-1]]
                samples=[]
                for j in range(k-1,len(seq)-1):
                    if None in seq[j-k+1:j+1]: continue
                    if tuple(seq[j-k+1:j+1])==schema and seq[j+1] is not None:
                        samples.append(seq[j+1])
                if not samples: continue
                pred=_Counter(samples).most_common(1)[0][0]
                target=n+pred
                if not (1 <= target <= 80): continue
                out.append({
                    "date": dts[t].strftime("%d.%m.%Y"),
                    "source_draw": ids[t],
                    "target_draw": ids[t+1],
                    "number": n,
                    "k": k,
                    "schema": str(schema),
                    "pred_delta": pred,
                    "target_number": target,
                    "real": int(target in nxt),
                    "history_support": len(samples),
                })
    return _pd.DataFrame(out)

st.divider()
st.header("🧬 V3 — Sayı Event Log")
st.caption("Şema → yön → sayı kimliği → hedef sayı → sonraki REAL20. Her olay yalnız geçmiş bilgiyle üretilir.")

_v3df=_v3_parse_embedded()
_v3days=sorted(_v3df["dt"].dt.strftime("%d.%m.%Y").unique(),
               key=lambda x: x)

# Preserve chronological order explicitly from data
_v3days=list(dict.fromkeys(_v3df["dt"].dt.strftime("%d.%m.%Y").tolist()))
_v3sel=st.selectbox("V3 günü", _v3days, key="v3_day")
if st.button("🔬 BU GÜNÜN SAYI EVENT LOG'UNU ÜRET", type="primary", key="v3_run"):
    _mask=_v3df["dt"].dt.strftime("%d.%m.%Y")==_v3sel
    _ev=_v3_day_events(_v3df[_mask].reset_index(drop=True))
    st.session_state["v3_events_"+_v3sel]=_ev

_ev=st.session_state.get("v3_events_"+_v3sel)
if _ev is not None:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Event", len(_ev))
    c2.metric("REAL", int(_ev["real"].sum()) if len(_ev) else 0)
    c3.metric("REAL oranı", f"{(_ev['real'].mean()*100):.2f}%" if len(_ev) else "—")
    c4.metric("Tekil sayı", int(_ev["number"].nunique()) if len(_ev) else 0)
    st.dataframe(_ev.tail(250), use_container_width=True, hide_index=True)
    st.download_button("⬇️ Günlük EVENT LOG CSV",
                       _ev.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"V3_EVENT_{_v3sel.replace('.','_')}.csv",
                       mime="text/csv")
    if len(_ev):
        _num=_ev.groupby("number").agg(SINYAL=("real","size"),REAL=("real","sum"),ORAN=("real","mean")).reset_index()
        _num["ORAN"]=_num["ORAN"]*100
        st.subheader("1–80 sayı özeti")
        st.dataframe(_num.sort_values(["ORAN","SINYAL"],ascending=False), use_container_width=True, hide_index=True)



# =========================
# V3.1 — 14 GÜN TEK MASTER
# =========================
st.divider()
st.header("📦 14 Gün — Tek EVENT MASTER")

if st.button("🚀 14 GÜNÜ TEK SEFERDE ÇALIŞTIR VE BİRLEŞTİR", type="primary", key="v31_all"):
    _all=[]
    _bar=st.progress(0)
    _status=st.empty()
    _days=list(dict.fromkeys(_v3df["dt"].dt.strftime("%d.%m.%Y").tolist()))
    for _i,_day in enumerate(_days):
        _status.write(f"Çalışıyor: {_day}  ({_i+1}/{len(_days)})")
        _mask=_v3df["dt"].dt.strftime("%d.%m.%Y")==_day
        _one=_v3_day_events(_v3df[_mask].reset_index(drop=True))
        if len(_one):
            _all.append(_one)
        _bar.progress((_i+1)/len(_days))
    _master=_pd.concat(_all, ignore_index=True) if _all else _pd.DataFrame()
    st.session_state["v31_master"]=_master
    _status.success(f"Tamamlandı: {len(_days)}/{len(_days)} gün — {len(_master)} event")

_master=st.session_state.get("v31_master")
if _master is not None and len(_master):
    _uniq=_master.drop_duplicates(subset=["date","source_draw","target_draw","target_number"])
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Toplam event", len(_master))
    c2.metric("REAL event", int(_master["real"].sum()))
    c3.metric("Ham REAL %", f"{100*_master['real'].mean():.2f}")
    c4.metric("Tekil aday-event", len(_uniq))

    st.download_button(
        "⬇️ V3 14 GÜN TEK EVENT MASTER CSV",
        _master.to_csv(index=False).encode("utf-8-sig"),
        file_name="V3_14_GUN_EVENT_MASTER.csv",
        mime="text/csv",
        key="v31_master_download"
    )

    _num=_master.groupby("number").agg(
        SINYAL=("real","size"), REAL=("real","sum"), ORAN=("real","mean")
    ).reset_index()
    _num["ORAN"]*=100
    st.download_button(
        "⬇️ 1–80 SAYI ÖZETİ CSV",
        _num.to_csv(index=False).encode("utf-8-sig"),
        file_name="V3_14_GUN_1_80_SAYI_OZETI.csv",
        mime="text/csv",
        key="v31_num_download"
    )
