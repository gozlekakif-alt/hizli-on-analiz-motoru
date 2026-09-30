# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict, Counter
import hashlib, re, math
from math import comb

st.set_page_config(page_title="Hızlı On — Dinamik Yaşam Havuzları", layout="wide")
st.title("🔥❄️ Hızlı On — Dinamik Sıcak/Soğuk Yaşam Havuzları V2")
st.caption("1–80 her çekilişte güncellenir • yaşam statüsü • 5'li havuzlar • ilk6 karakteri • sonraki 1–6 çekiliş aktivasyonu • gün gün tek TXT")

START = pd.Timestamp("2026-08-25 00:00:00")
END   = pd.Timestamp("2026-09-29 23:59:59")

FIRST3=("02","07","12")
SECOND3=("17","22","27")
FIRST6=FIRST3+SECOND3
LAST6=("32","37","42","47","52","57")
HOUR12=FIRST6+LAST6

STATUSES = ("NEW_HOT","HOT","WAKING_COLD","COOLING","NEUTRAL","COLD","DEEP_COLD")
HOT_THR = 0.85
COLD_THR = -0.65
DEEP_THR = -1.20

# ----------------------------
# VERİ
# ----------------------------
def parse_line(line):
    s=line.strip()
    if not s or s.startswith(("=","#")):
        return None
    m=re.match(r"^\s*(\d+)\s*;\s*([^;]+?)\s*;\s*(.+?)\s*$",s)
    if not m:
        m=re.match(r"^\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$",s)
    if not m:
        return None
    try:
        draw_id=int(m.group(1))
        dt=pd.to_datetime(m.group(2).strip(),dayfirst=True,errors="raise")
        nums=sorted(set(int(x) for x in re.findall(r"\d+",m.group(3))))
    except Exception:
        return None
    if len(nums)!=20 or not all(1<=n<=80 for n in nums):
        return None
    return draw_id,dt,tuple(nums)

@st.cache_data(show_spinner=False)
def parse_text(raw,digest):
    rows=[]; rejected=0
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith(("=","#")):
            continue
        x=parse_line(line)
        if x:
            rows.append(x)
        elif re.search(r"\d",line):
            rejected+=1
    if not rows:
        raise ValueError("Geçerli çekiliş bulunamadı.")
    df=pd.DataFrame(rows,columns=["draw_id","time","numbers"])
    before=len(df)
    df=df.sort_values(["time","draw_id"]).drop_duplicates("draw_id",keep="last").reset_index(drop=True)
    return df,rejected,before-len(df)

def read_source(uploaded):
    if uploaded is not None:
        b=uploaded.getvalue()
        return b.decode("utf-8-sig",errors="replace"),uploaded.name
    p=Path("veri.txt")
    if p.exists():
        return p.read_text(encoding="utf-8-sig",errors="replace"),"repo/veri.txt"
    return None,None

# ----------------------------
# CANLI YAŞAM METRİKLERİ
# ----------------------------
def binom_z(h,n,p=.25):
    if n<=0:
        return 0.0
    mu=n*p
    sd=math.sqrt(n*p*(1-p))
    return (h-mu)/sd if sd else 0.0

def interval_sum(prefix, end_idx, length):
    """0..end_idx dahil son length toplamı, 80 vektörü."""
    if end_idx < 0:
        return np.zeros(80,dtype=float),0
    start=max(0,end_idx-length+1)
    v=prefix[end_idx].astype(float)
    if start>0:
        v=v-prefix[start-1]
    return v,end_idx-start+1

def classify_state(score, prev_score, prev_state, current_hit, delta, gap):
    # Önce sıcak eşiği: soğuktan/normalden yeni giriş ayrı tutulur.
    if score >= HOT_THR:
        if prev_score < HOT_THR:
            return "NEW_HOT"
        return "HOT"

    # Önceki sıcaklığını yeni kaybettiyse.
    if prev_score >= HOT_THR and score < HOT_THR:
        return "COOLING"

    # Soğuk geçmişten yukarı dönmeye başlayan sayı.
    if prev_score <= COLD_THR and current_hit and delta >= 0.18:
        return "WAKING_COLD"
    if prev_state in ("COLD","DEEP_COLD") and current_hit and delta >= 0.28:
        return "WAKING_COLD"

    if score <= DEEP_THR and gap >= 8:
        return "DEEP_COLD"
    if score <= COLD_THR:
        return "COLD"
    return "NEUTRAL"

def activation_index(score, delta, current_hit, h6, n6):
    # "Due" varsayımı YOK. Sadece güncel yükseliş ve yakın dönem aktivitesi.
    short_rate=(h6/n6) if n6 else 0.0
    return score + 0.45*delta + 0.20*float(current_hit) + 0.15*(short_rate-.25)

def random_p_ge(k_pool, need):
    den=comb(80,k_pool)
    s=0
    for j in range(need,min(k_pool,20)+1):
        s += comb(k_pool,j)*comb(80-k_pool,20-j)
    return s/den

def make_hour_chars(day):
    buckets=defaultdict(dict)
    for r in day.itertuples(index=False):
        mm=r.time.strftime("%M")
        if mm in HOUR12:
            buckets[r.time.strftime("%H")][mm]=set(r.numbers)

    chars={}
    for hh,d in buckets.items():
        if any(m not in d for m in FIRST6):
            continue
        c1={n:sum(n in d[m] for m in FIRST3) for n in range(1,81)}
        c2={n:sum(n in d[m] for m in SECOND3) for n in range(1,81)}
        c6={n:c1[n]+c2[n] for n in range(1,81)}
        q1=[sum(c1[n]==k for n in range(1,81)) for k in range(4)]
        q2=[sum(c2[n]==k for n in range(1,81)) for k in range(4)]
        q6=[sum(c6[n]==k for n in range(1,81)) for k in range(7)]
        z6=q6[0]
        if z6<=12:
            band="ZERO6_LOW"
        elif z6<=16:
            band="ZERO6_MID"
        else:
            band="ZERO6_HIGH"
        chars[hh]={"q1":q1,"q2":q2,"q6":q6,"zero6_band":band}
    return chars

@st.cache_data(show_spinner=False)
def analyze_day(serial,day_key,digest):
    day=pd.DataFrame(serial,columns=["draw_id","time","numbers"]).sort_values(["time","draw_id"]).reset_index(drop=True)
    N=len(day)

    mat=np.zeros((N,80),dtype=np.uint8)
    draw_sets=[]
    for i,r in enumerate(day.itertuples(index=False)):
        s=set(r.numbers)
        draw_sets.append(s)
        for n in s:
            mat[i,n-1]=1
    prefix=np.cumsum(mat,axis=0)

    hour_chars=make_hour_chars(day)

    last_seen=np.full(80,-1,dtype=int)
    prev_score=np.zeros(80,dtype=float)
    prev_state=np.array(["NEUTRAL"]*80,dtype=object)

    snapshot_rows=[]
    pool_rows=[]
    report_lines=[]
    report_lines.append("="*110)
    report_lines.append(f"GÜN {day_key} | çekiliş={N}")
    report_lines.append("="*110)

    for t,r in enumerate(day.itertuples(index=False)):
        current=mat[t].astype(float)
        cum=prefix[t].astype(float)

        h6,n6=interval_sum(prefix,t,6)
        h12,n12=interval_sum(prefix,t,12)
        h24,n24=interval_sum(prefix,t,24)

        prev6_end=t-6
        ph6,pn6=interval_sum(prefix,prev6_end,6) if prev6_end>=0 else (np.zeros(80),0)

        z6=np.array([binom_z(h6[i],n6) for i in range(80)])
        z12=np.array([binom_z(h12[i],n12) for i in range(80)])
        z24=np.array([binom_z(h24[i],n24) for i in range(80)])
        zday=np.array([binom_z(cum[i],t+1) for i in range(80)])

        rate6=h6/max(1,n6)
        prev_rate6=ph6/max(1,pn6) if pn6 else np.zeros(80)
        trend=(rate6-prev_rate6)

        # Yakın dönem daha ağır; günlük kimlik zemindir.
        score=.38*z6 + .27*z12 + .20*z24 + .15*zday + .30*trend
        delta=score-prev_score

        gaps=np.zeros(80,dtype=int)
        for i in range(80):
            if current[i]:
                gaps[i]=0
            elif last_seen[i]>=0:
                gaps[i]=t-last_seen[i]
            else:
                gaps[i]=t+1

        states=[]
        act_idx=np.zeros(80,dtype=float)
        for i in range(80):
            stt=classify_state(score[i],prev_score[i],prev_state[i],bool(current[i]),delta[i],int(gaps[i]))
            states.append(stt)
            act_idx[i]=activation_index(score[i],delta[i],bool(current[i]),h6[i],n6)

        # Her durum kendi içinde aktivasyon indeksine göre sıralanır ve 5'li havuzlara bölünür.
        pools=[]
        for status in STATUSES:
            ids=[i for i,s in enumerate(states) if s==status]
            ids=sorted(ids,key=lambda i:(-act_idx[i],-score[i],i))
            for g,start in enumerate(range(0,len(ids),5),1):
                chunk=ids[start:start+5]
                if not chunk:
                    continue
                members=[i+1 for i in chunk]
                pools.append((status,g,chunk,members))

        state_counts=Counter(states)
        mm=r.time.strftime("%M")
        hh=r.time.strftime("%H")
        hc=hour_chars.get(hh)
        char_available=hc is not None and mm in ("27","32","37","42","47","52","57")

        snapshot_rows.append({
            "date":day_key,
            "draw_index":t+1,
            "draw_id":int(r.draw_id),
            "time":r.time.strftime("%H:%M"),
            "minute":mm,
            **{f"n_{s}":state_counts.get(s,0) for s in STATUSES},
            "mean_score":float(np.mean(score)),
            "max_score":float(np.max(score)),
            "min_score":float(np.min(score)),
            "zero6_band":hc["zero6_band"] if char_available else "",
            "q6_0":hc["q6"][0] if char_available else np.nan,
            "q6_1":hc["q6"][1] if char_available else np.nan,
            "q6_2":hc["q6"][2] if char_available else np.nan,
            "q6_3":hc["q6"][3] if char_available else np.nan,
        })

        report_lines.append("")
        report_lines.append(f"[{t+1:03d}] Çekiliş #{int(r.draw_id)} {r.time.strftime('%H:%M')}")
        report_lines.append(
            "• Statü kontenjanı: " +
            " | ".join(f"{s}={state_counts.get(s,0)}" for s in STATUSES)
        )
        if char_available:
            report_lines.append(
                f"• İlk6 saat karakteri: {hc['zero6_band']} | "
                f"ilk3={hc['q1']} | ikinci3={hc['q2']} | ilk6(0..6)={hc['q6']}"
            )

        # Grupları ve gelecekteki aktivasyonunu kaydet.
        for status,g,chunk,members in pools:
            exact_hits=[]
            cum_unique=[]
            seen=set()
            future_member_sets=[]
            for h in range(1,7):
                if t+h<N:
                    hit=set(members)&draw_sets[t+h]
                    exact_hits.append(len(hit))
                    seen |= hit
                    cum_unique.append(len(seen))
                    future_member_sets.append(sorted(hit))
                else:
                    exact_hits.append(np.nan)
                    cum_unique.append(np.nan)
                    future_member_sets.append([])

            valid=[x for x in exact_hits if not pd.isna(x)]
            max_same=int(max(valid)) if valid else np.nan
            first_active=next((h+1 for h,x in enumerate(exact_hits) if not pd.isna(x) and x>0),np.nan)

            row={
                "date":day_key,"snapshot_index":t+1,"draw_id":int(r.draw_id),
                "time":r.time.strftime("%H:%M"),"minute":mm,
                "status":status,"group_rank":g,
                "members":"-".join(f"{n:02d}" for n in members),
                "pool_size":len(members),
                "mean_life_score":float(np.mean([score[i] for i in chunk])),
                "mean_activation_index":float(np.mean([act_idx[i] for i in chunk])),
                "mean_gap":float(np.mean([gaps[i] for i in chunk])),
                "current_hits":int(sum(current[i] for i in chunk)),
                "max_same_draw_next6":max_same,
                "first_activation_step":first_active,
                "zero6_band":hc["zero6_band"] if char_available else "",
                "q6_0":hc["q6"][0] if char_available else np.nan,
                "q6_1":hc["q6"][1] if char_available else np.nan,
                "q6_2":hc["q6"][2] if char_available else np.nan,
                "q6_3":hc["q6"][3] if char_available else np.nan,
            }
            for h in range(1,7):
                row[f"hit_h{h}"]=exact_hits[h-1]
                row[f"cum_unique_h{h}"]=cum_unique[h-1]
                row[f"members_h{h}"]=",".join(map(str,future_member_sets[h-1]))
            pool_rows.append(row)

            sc=",".join(f"{i+1}:{score[i]:+.2f}" for i in chunk)
            hit_txt=" ".join(
                f"+{h}:{'-' if pd.isna(exact_hits[h-1]) else int(exact_hits[h-1])}"
                for h in range(1,7)
            )
            report_lines.append(
                f"• {status} G{g} [{'-'.join(f'{n:02d}' for n in members)}] "
                f"| yaşam={np.mean([score[i] for i in chunk]):+.2f} "
                f"| aktivasyon={np.mean([act_idx[i] for i in chunk]):+.2f} "
                f"| gap={np.mean([gaps[i] for i in chunk]):.1f} "
                f"| {hit_txt} | max6={max_same}"
            )

        # Güncelle
        for i in range(80):
            if current[i]:
                last_seen[i]=t
        prev_score=score.copy()
        prev_state=np.array(states,dtype=object)

    pools_df=pd.DataFrame(pool_rows)
    snaps_df=pd.DataFrame(snapshot_rows)

    # Günlük özet: statü + grup sırası
    daily_agg=[]
    if not pools_df.empty:
        for (status,rank),g in pools_df.groupby(["status","group_rank"]):
            gg=g.dropna(subset=["hit_h1"])
            if gg.empty:
                continue
            row={
                "date":day_key,"status":status,"group_rank":int(rank),"events":len(gg),
                "mean_h1":gg.hit_h1.mean(),
                "p_h1_2plus":100*(gg.hit_h1>=2).mean(),
                "mean_max_next6":gg.max_same_draw_next6.mean(),
                "p_max_next6_2plus":100*(gg.max_same_draw_next6>=2).mean(),
                "p_max_next6_3plus":100*(gg.max_same_draw_next6>=3).mean(),
                "mean_cum_unique6":gg.cum_unique_h6.mean(),
            }
            daily_agg.append(row)

    return {
        "date":day_key,
        "draw_count":N,
        "snapshots":snaps_df,
        "pools":pools_df,
        "daily_agg":pd.DataFrame(daily_agg),
        "report":"\n".join(report_lines),
    }

# ----------------------------
# TOPLAM ÖZET
# ----------------------------
def aggregate_all(day_results):
    pools=pd.concat([d["pools"] for d in day_results],ignore_index=True)
    snaps=pd.concat([d["snapshots"] for d in day_results],ignore_index=True)

    rows=[]
    for (status,rank),g in pools.groupby(["status","group_rank"]):
        gg=g.dropna(subset=["hit_h1"])
        if gg.empty:
            continue
        rows.append({
            "status":status,"group_rank":int(rank),"events":len(gg),
            "mean_h1":gg.hit_h1.mean(),
            "p_h1_2plus":100*(gg.hit_h1>=2).mean(),
            "p_h1_3plus":100*(gg.hit_h1>=3).mean(),
            "mean_max_next6":gg.max_same_draw_next6.mean(),
            "p_max_next6_2plus":100*(gg.max_same_draw_next6>=2).mean(),
            "p_max_next6_3plus":100*(gg.max_same_draw_next6>=3).mean(),
            "mean_cum_unique6":gg.cum_unique_h6.mean(),
        })
    status_agg=pd.DataFrame(rows)

    # Saat ikinci yarısı için :27→:52 güncellemeleri, 0/6 bandıyla.
    stage_minutes=("27","32","37","42","47","52")
    stage_rows=[]
    stage=pools[pools.minute.isin(stage_minutes)].copy()
    for (minute,zband,status,rank),g in stage.groupby(["minute","zero6_band","status","group_rank"]):
        if not zband:
            continue
        gg=g.dropna(subset=["hit_h1"])
        if len(gg)<20:
            continue
        stage_rows.append({
            "snapshot_minute":minute,"zero6_band":zband,
            "status":status,"group_rank":int(rank),"events":len(gg),
            "next_draw_mean_hits":gg.hit_h1.mean(),
            "next_draw_2plus_pct":100*(gg.hit_h1>=2).mean(),
            "next6_max_2plus_pct":100*(gg.max_same_draw_next6>=2).mean(),
            "next6_max_3plus_pct":100*(gg.max_same_draw_next6>=3).mean(),
            "next6_unique_mean":gg.cum_unique_h6.mean(),
        })
    stage_agg=pd.DataFrame(stage_rows)

    return pools,snaps,status_agg,stage_agg

def make_master_report(df,rejected,dup,day_results,status_agg,stage_agg,source,digest):
    L=[]
    L.append("HIZLI ON — DİNAMİK SICAK/SOĞUK YAŞAM HAVUZLARI ANA RAPORU")
    L.append("="*115)
    L.append(f"Kaynak: {source}")
    L.append(f"SHA256: {digest}")
    L.append(f"Kapsam: 25.08.2026–29.09.2026 | çekiliş={len(df)} | gün={df.time.dt.date.nunique()} | dup={dup} | parse-red={rejected}")
    L.append("")
    L.append("AMAÇ")
    L.append("Her çekiliş sonrası 1–80 yaşam statüsünü yeniden hesaplamak; aynı yaşam statüsündeki sayıları")
    L.append("aktivasyon indeksine göre 5'erli havuzlara bölmek; bu havuzların sonraki 1–6 çekilişte")
    L.append("kaç üye aktive ettiğini gün/saat/dakika ve ilk6 karakteriyle birlikte ölçmek.")
    L.append("")
    L.append("STATÜLER")
    L.append("NEW_HOT: sıcak eşiğine yeni giren | HOT: sıcaklığı sürdüren | WAKING_COLD: soğuktan yükseliş")
    L.append("COOLING: sıcaktan düşen | NEUTRAL | COLD | DEEP_COLD")
    L.append("Yaşam puanı: son6 + son12 + son24 + gün içi binom-z + yakın dönem trendi.")
    L.append("Aktivasyon indeksi: yaşam puanı + puan değişimi + mevcut çekiliş aktivitesi + kısa dönem oran.")
    L.append("ÖNEMLİ: gap/uzun bekleme 'artık çıkmalı' varsayımıyla puanlanmaz; sadece betimleyici olarak raporlanır.")
    L.append("")
    L.append("5'Lİ RASTGELE TEK ÇEKİLİŞ REFERANSI")
    L.append(f"E[isabet]=1.250 | P(2+)=%{100*random_p_ge(5,2):.2f} | P(3+)=%{100*random_p_ge(5,3):.2f} | P(4+)=%{100*random_p_ge(5,4):.3f}")
    L.append("")

    L.append("[A] TÜM DÖNEM — STATÜ / 5'Lİ GRUP PERFORMANSI")
    L.append("-"*115)
    if not status_agg.empty:
        for r in status_agg.sort_values(["status","group_rank"]).itertuples(index=False):
            L.append(
                f"{r.status} G{r.group_rank} | n={r.events} | sonraki1 ort={r.mean_h1:.3f} "
                f"| P1(2+)=%{r.p_h1_2plus:.1f} P1(3+)=%{r.p_h1_3plus:.2f} "
                f"| sonraki6 max ort={r.mean_max_next6:.3f} "
                f"| max6 2+%={r.p_max_next6_2plus:.1f} 3+%={r.p_max_next6_3plus:.1f} "
                f"| 6 adımda farklı aktive={r.mean_cum_unique6:.2f}/5"
            )

    L.append("\n[B] İLK6 KARAKTERİ + CANLI GÜNCELLEME")
    L.append("-"*115)
    L.append("Snapshot :27 ise sonraki çekiliş :32; :32 ise :37; ... :52 ise :57.")
    L.append("Sadece en az 20 olay bulunan kombinasyonlar listelenir.")
    if not stage_agg.empty:
        for minute in ("27","32","37","42","47","52"):
            L.append(f"\nSNAPSHOT :{minute}")
            g=stage_agg[stage_agg.snapshot_minute==minute].copy()
            # En güçlü 20 kombinasyonu 2+ oranına göre ver
            g=g.sort_values(["next_draw_2plus_pct","events"],ascending=[False,False]).head(20)
            for r in g.itertuples(index=False):
                L.append(
                    f"{r.zero6_band} | {r.status} G{r.group_rank} | n={r.events} "
                    f"| next ort={r.next_draw_mean_hits:.3f} | next 2+%={r.next_draw_2plus_pct:.1f} "
                    f"| 6-adım max2+%={r.next6_max_2plus_pct:.1f} max3+%={r.next6_max_3plus_pct:.1f} "
                    f"| unique6={r.next6_unique_mean:.2f}"
                )

    L.append("\n[C] GÜN GÜN / HER ÇEKİLİŞ DETAYI")
    L.append("="*115)
    for d in day_results:
        L.append(d["report"])
    return "\n".join(L)

# ----------------------------
# UI
# ----------------------------
with st.sidebar:
    st.header("Veri")
    uploaded=st.file_uploader("İstersen veri.txt yükle",type=["txt"])
    st.caption("Yükleme yoksa repo kökündeki veri.txt otomatik okunur.")
    if st.button("🔄 veri.txt yeniden oku",use_container_width=True):
        st.cache_data.clear()
        st.session_state.pop("analysis",None)
        st.rerun()

raw,source=read_source(uploaded)
if raw is None:
    st.error("veri.txt bulunamadı. Repo kökünde veri.txt olmalı.")
    st.stop()

digest=hashlib.sha256(raw.encode("utf-8",errors="replace")).hexdigest()
df0,rejected,dup=parse_text(raw,digest)
df=df0[(df0.time>=START)&(df0.time<=END)].copy().reset_index(drop=True)

c1,c2,c3,c4,c5=st.columns(5)
c1.metric("Çekiliş",len(df))
c2.metric("Gün",df.time.dt.date.nunique() if len(df) else 0)
c3.metric("İlk",df.time.min().strftime("%d.%m.%Y") if len(df) else "-")
c4.metric("Son",df.time.max().strftime("%d.%m.%Y") if len(df) else "-")
c5.metric("SHA",digest[:10])

st.info(
    "Bu sürümde her çekiliş sonrası 1–80 yeniden sınıflandırılır. "
    "Her statü kendi içinde 5'li havuzlara ayrılır; havuzların sonraki 1–6 çekilişteki aktivasyonu ölçülür. "
    "Kupon üretimi yoktur."
)

health=df.assign(day=df.time.dt.strftime("%d.%m.%Y")).groupby("day").size().reset_index(name="draws")
health["status"]=np.where(health.draws==217,"TAM","EKSİK/FAZLA")
with st.expander("📦 Veri sağlık kontrolü"):
    st.dataframe(health,use_container_width=True,hide_index=True)
    st.write(f"Mükerrer temizlenen: **{dup}** • Parse reddi: **{rejected}**")

if st.button("🚀 GÜN GÜN / ÇEKİLİŞ ÇEKİLİŞ ANALİZİ BAŞLAT",type="primary",use_container_width=True):
    results=[]
    days=sorted(df.time.dt.strftime("%d.%m.%Y").unique(),key=lambda x:pd.to_datetime(x,dayfirst=True))
    prog=st.progress(0,text="Hazırlanıyor...")
    msg=st.empty()

    for i,day_key in enumerate(days,1):
        day=df[df.time.dt.strftime("%d.%m.%Y")==day_key][["draw_id","time","numbers"]]
        serial=[(int(r.draw_id),r.time,tuple(r.numbers)) for r in day.itertuples(index=False)]
        msg.write(f"🔬 {day_key}: {len(day)} çekiliş tek tek güncelleniyor...")
        results.append(analyze_day(serial,day_key,digest))
        prog.progress(i/len(days),text=f"{i}/{len(days)} gün tamamlandı")

    pools,snaps,status_agg,stage_agg=aggregate_all(results)
    report=make_master_report(df,rejected,dup,results,status_agg,stage_agg,source,digest)

    st.session_state["analysis"]=(results,status_agg,stage_agg,report)
    msg.success("✅ Bütün günler ve bütün çekiliş güncellemeleri tamamlandı.")
    prog.empty()

if "analysis" in st.session_state:
    results,status_agg,stage_agg,report=st.session_state["analysis"]
    t1,t2,t3,t4=st.tabs(["🔥 Statüler","⏱️ İlk6 + Canlı","📅 Günler","📄 Tek TXT"])

    with t1:
        st.caption("5'li havuzların tüm dönem aktivasyon özeti.")
        st.dataframe(status_agg,use_container_width=True,hide_index=True)

    with t2:
        st.caption(":27 sonucu sonrası :32, :32 sonrası :37 ... canlı havuz davranışı; ilk6 0/6 karakteriyle birlikte.")
        st.dataframe(stage_agg,use_container_width=True,hide_index=True)

    with t3:
        rows=[]
        for d in results:
            rows.append({
                "Gün":d["date"],"Çekiliş":d["draw_count"],
                "Snapshot":len(d["snapshots"]),
                "5'li havuz kaydı":len(d["pools"])
            })
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

    with t4:
        st.success("Tek ana araştırma TXT'si hazır.")
        st.download_button(
            "⬇️ TEK ANA ANALİZ DOSYASINI İNDİR",
            report.encode("utf-8-sig"),
            file_name="HIZLI_ON_DINAMIK_YASAM_HAVUZLARI_25AGUSTOS_29EYLUL.txt",
            mime="text/plain",
            use_container_width=True
        )
        with st.expander("Rapor önizleme"):
            st.text(report[:50000])
