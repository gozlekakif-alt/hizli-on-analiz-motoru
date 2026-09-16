import streamlit as st
import pandas as pd
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations
from math import comb

st.set_page_config(page_title='Saatlik Aile Avcısı V1', layout='wide')
st.title('🧬 Hızlı On — Saatlik Aile Avcısı V1')
st.caption('NO-FUTURE: Her hedef çekiliş için yalnızca o çekilişten ÖNCE görülen sonuçlar kullanılır. Sinyal yoksa PAS.')

DATA=Path('veri.txt')

@st.cache_data
def load_data():
    rows=[]
    for line in DATA.read_text(encoding='utf-8').splitlines():
        p=line.strip().split(';')
        if len(p)!=3: continue
        nums=tuple(sorted(map(int,p[2].split(','))))
        if len(nums)!=20 or len(set(nums))!=20: continue
        dt=pd.to_datetime(p[1], dayfirst=True)
        rows.append((int(p[0]),dt,nums))
    df=pd.DataFrame(rows,columns=['draw_id','dt','nums']).sort_values('draw_id').reset_index(drop=True)
    df['day']=df.dt.dt.strftime('%d.%m.%Y')
    df['hour']=df.dt.dt.strftime('%H')
    return df

def hit(ticket, actual): return len(set(ticket)&set(actual))
def fmt(t): return '-'.join(map(str,sorted(t)))

def pair_strength(history):
    c=Counter()
    for s in history:
        c.update(combinations(sorted(s),2))
    return c

def tri_strength(history):
    c=Counter()
    for s in history:
        c.update(combinations(sorted(s),3))
    return c

def quad_strength(history):
    c=Counter()
    for s in history:
        c.update(combinations(sorted(s),4))
    return c

def burst_quad(history, min_pair=2):
    # 4'lüyü, içindeki 6 ikili bağın yakın pencere desteğiyle kurar.
    pc=pair_strength(history)
    nodes=Counter()
    for s in history: nodes.update(s)
    cand=set()
    strong=[p for p,n in pc.items() if n>=min_pair]
    for p in strong:
        cand.update(p)
    if len(cand)<4: return None,0
    # aday havuzu en canlı 16 sayı ile sınırlı
    pool=[n for n,_ in nodes.most_common(16) if n in cand]
    best=None; bestscore=-1
    for q in combinations(sorted(pool),4):
        links=[pc[tuple(sorted(x))] for x in combinations(q,2)]
        score=sum(links)+0.35*sum(nodes[n] for n in q)
        if min(links)>=1 and score>bestscore:
            best,bestscore=q,score
    return best,bestscore

def completer_quad(history):
    # Güçlü 3'lünün yanına, üçlü üyeleriyle en güçlü ortak bağa sahip 4. üyeyi koyar.
    tc=tri_strength(history); pc=pair_strength(history); singles=Counter()
    for s in history: singles.update(s)
    if not tc: return None,0
    tri,n3=tc.most_common(1)[0]
    bestx=None; bs=-1
    for x in range(1,81):
        if x in tri: continue
        sc=sum(pc[tuple(sorted((x,a)))] for a in tri)+0.25*singles[x]
        if sc>bs: bestx,bs=x,sc
    return tuple(sorted((*tri,bestx))), n3*3+bs

def carry_family_quad(history):
    # Son elden en güçlü iki taşıyıcı + yakın pencerenin en güçlü bağlayıcı iki üyesi.
    if not history: return None,0
    last=set(history[-1]); pc=pair_strength(history); singles=Counter()
    for s in history: singles.update(s)
    lp=[]
    for a,b in combinations(sorted(last),2):
        lp.append((pc[(a,b)]+0.2*(singles[a]+singles[b]),(a,b)))
    if not lp: return None,0
    lp.sort(reverse=True); core=lp[0][1]
    choices=[]
    for x in range(1,81):
        if x in core: continue
        sc=sum(pc[tuple(sorted((x,a)))] for a in core)+0.2*singles[x]
        choices.append((sc,x))
    choices.sort(reverse=True)
    q=tuple(sorted((*core,choices[0][1],choices[1][1])))
    return q,lp[0][0]+choices[0][0]+choices[1][0]

def consensus(history):
    engines=[]
    for name,fn in [('BURST',burst_quad),('3→4',completer_quad),('TAŞIMA+AİLE',carry_family_quad)]:
        q,s=fn(history)
        if q: engines.append((name,q,s))
    votes=Counter()
    for _,q,_ in engines: votes.update(q)
    # önce 3 motorun/2 motorun ortak üyeleri; sonra motor skorlarından tamamla
    ranked=sorted(range(1,81), key=lambda n:(votes[n], sum(s for _,q,s in engines if n in q)), reverse=True)
    q=tuple(sorted(ranked[:4])) if engines else None
    agreement=sum(1 for n in q if votes[n]>=2) if q else 0
    return q,agreement,engines

def analyze_hour(g, warmup=4, min_agree=2):
    g=g.sort_values('draw_id').reset_index(drop=True)
    rows=[]
    for t in range(warmup,len(g)):
        hist=[set(x) for x in g.loc[:t-1,'nums']]
        q,agree,eng=consensus(hist)
        if q is None or agree<min_agree:
            rows.append({'target':g.loc[t,'draw_id'],'time':g.loc[t,'dt'],'ticket':'PAS','hit':None,'agree':agree,'engines':eng})
            continue
        h=hit(q,g.loc[t,'nums'])
        rows.append({'target':g.loc[t,'draw_id'],'time':g.loc[t,'dt'],'ticket':q,'hit':h,'agree':agree,'engines':eng})
    return rows

def backtest(df,warmup,min_agree):
    allr=[]
    # gerçek saat blokları; 00/01 ve 07..23 ayrı saatler
    for (day,hour),g in df.groupby(['day','hour'],sort=False):
        if len(g)<=warmup: continue
        rr=analyze_hour(g,warmup,min_agree)
        for x in rr: x['day']=day; x['hour']=hour
        allr.extend(rr)
    return allr

df=load_data()
st.sidebar.metric('Çekiliş',len(df)); st.sidebar.metric('Gün',df.day.nunique())
warmup=st.sidebar.slider('Saat başında gözlem eli',2,6,4)
min_agree=st.sidebar.slider('Kupon için en az ortak üye',1,4,2)

st.subheader('1) 14 Gün NO-FUTURE Geri Test')
if st.button('🧪 14 GÜNÜ GERİ TEST ET',type='primary',use_container_width=True):
    res=backtest(df,warmup,min_agree)
    bets=[r for r in res if r['ticket']!='PAS']
    st.session_state['bt']=res
    n=len(bets); full=sum(r['hit']==4 for r in bets); h3=sum(r['hit']==3 for r in bets)
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Kupon',n); c2.metric('4/4',full); c3.metric('3/4',h3); c4.metric('PAS',len(res)-n)
    if n:
        p4=comb(20,4)/comb(80,4)
        st.caption(f'Sabit tek 4-lü kuponun tek çekilişte teorik 4/4 olasılığı: {p4:.6%}. Bu değer yalnız benchmarktır.')
        out=pd.DataFrame([{'Tarih':r['day'],'Saat':r['time'].strftime('%H:%M'),'Hedef':r['target'],'Kupon':fmt(r['ticket']),'İsabet':r['hit'],'Ortak':r['agree']} for r in bets])
        st.dataframe(out,use_container_width=True,height=420)
        txt=out.to_csv(index=False).encode('utf-8-sig')
        st.download_button('⬇️ GERİ TEST CSV İNDİR',txt,'SAATLIK_AILE_AVCISI_GERI_TEST.csv','text/csv',use_container_width=True)

st.subheader('2) Gün/Saat İncele — Canlı Mantık')
day=st.selectbox('Gün',list(df.day.drop_duplicates()),index=len(df.day.drop_duplicates())-1)
hours=list(df[df.day==day].hour.drop_duplicates())
hour=st.selectbox('Saat',hours,index=len(hours)-1)
g=df[(df.day==day)&(df.hour==hour)].sort_values('draw_id').reset_index(drop=True)
seen=st.slider('Bu saatte kaç sonuç görüldü?',1,len(g),min(warmup,len(g)))
st.write(f'**{day} / {hour}:xx** • Görülen {seen}/{len(g)} çekiliş')
for i,row in g.iloc[:seen].iterrows():
    st.caption(f"#{row['draw_id']} {row['dt'].strftime('%H:%M')} → {fmt(row['nums'])}")

if seen>=2:
    hist=[set(x) for x in g.iloc[:seen].nums]
    q,agree,eng=consensus(hist)
    cols=st.columns(3)
    for col,(name,t,s) in zip(cols,eng):
        col.info(f'**{name}**\n\n### {fmt(t)}\nSkor: {s:.2f}')
    st.markdown('### 🎯 Hakem')
    if q and agree>=min_agree:
        st.success(f'KUPON: **{fmt(q)}**  • ortak üye={agree}')
    else:
        st.warning(f'PAS — ortak aile sinyali yetersiz (ortak üye={agree}, eşik={min_agree})')
    if seen<len(g) and q and agree>=min_agree:
        nxt=g.iloc[seen]
        st.caption('Aşağıdaki kontrol yalnız geriye dönük inceleme içindir; canlı kullanımda sonucu görmeden kupon kilitlenir.')
        if st.button('🔓 SONRAKİ GERÇEK SONUCU KONTROL ET'):
            h=hit(q,nxt['nums'])
            st.write(f"#{nxt['draw_id']} {nxt['dt'].strftime('%H:%M')} → **{h}/4** • {fmt(nxt['nums'])}")

st.markdown('---')
st.caption('V1.1: Saatlik aile avcısı. Üç uzman motor + ortak-hakem + PAS + no-future geri test. %100 garanti vermez; amaç gerçek ileri-test performansını ölçmektir.')
