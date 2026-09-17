import streamlit as st
import pandas as pd
import itertools
from collections import Counter, defaultdict
from math import comb

st.set_page_config(page_title="Hızlı On Aile Birleşme Analizi", layout="wide")
st.title("🧬 Hızlı On — Aile Birleşme / Doluluk Analizi V3 MASTER")
st.caption("GitHub verisini otomatik tanır • REAL20 üst aileleri • 6→7→8→9→… birleşme yaşamı")

def parse_txt(text):
    rows=[]
    for line in text.splitlines():
        parts=line.strip().split(";")
        if len(parts)!=3:
            continue
        try:
            draw_id=int(parts[0])
            dt=pd.to_datetime(parts[1], format="%d.%m.%Y %H:%M")
            nums=tuple(sorted(map(int, parts[2].split(","))))
            if len(nums)==20 and len(set(nums))==20:
                rows.append((draw_id,dt,nums))
        except:
            pass
    df=pd.DataFrame(rows, columns=["draw_id","time","numbers"]).drop_duplicates("draw_id").sort_values("draw_id").reset_index(drop=True)
    return df

def pairwise_families(df, overlap_min=14):
    sets=[set(x) for x in df.numbers]
    out=[]
    for i in range(len(df)):
        a=sets[i]
        for j in range(i+1,len(df)):
            inter=a & sets[j]
            if len(inter)>=overlap_min:
                out.append({
                    "i":i,"j":j,
                    "draw1":int(df.at[i,"draw_id"]),
                    "time1":df.at[i,"time"],
                    "draw2":int(df.at[j,"draw_id"]),
                    "time2":df.at[j,"time"],
                    "gap_draws":j-i,
                    "overlap":len(inter),
                    "family":tuple(sorted(inter))
                })
    return pd.DataFrame(out)

def occupancy_trace(df, family):
    fam=set(family)
    rows=[]
    for i,r in df.iterrows():
        active=sorted(fam & set(r.numbers))
        rows.append({
            "idx":i, "draw_id":int(r.draw_id), "time":r.time,
            "occupancy":len(active), "active":",".join(map(str,active))
        })
    return pd.DataFrame(rows)

def rising_events(trace, min_start=5, target=8, window=12):
    occ=trace.occupancy.to_numpy()
    ev=[]
    for end in range(len(occ)):
        if occ[end] < target: continue
        lo=max(0,end-window)
        prev=occ[lo:end]
        if len(prev)==0: continue
        # "birleşerek yükselme": önce daha düşük doluluk, hedef elde target+
        best_before=max(prev)
        if best_before < target and best_before >= min_start:
            start_idx=lo + max(k for k,v in enumerate(prev) if v==best_before)
            ev.append({
                "from_draw":int(trace.at[start_idx,"draw_id"]),
                "from_time":trace.at[start_idx,"time"],
                "from_occ":int(occ[start_idx]),
                "to_draw":int(trace.at[end,"draw_id"]),
                "to_time":trace.at[end,"time"],
                "to_occ":int(occ[end]),
                "gap":end-start_idx
            })
    return pd.DataFrame(ev)

# ------------------------------------------------------------
# GITHUB / STREAMLIT CLOUD OTOMATİK VERİ TANIMA
# Repo içindeki TXT dosyalarını otomatik tarar. Kullanıcının veri
# yüklemesi gerekmez. En fazla geçerli Hızlı On çekilişi içeren
# TXT otomatik seçilir.
# ------------------------------------------------------------
from pathlib import Path

@st.cache_data(show_spinner=False)
def github_verisini_bul():
    kok = Path(__file__).resolve().parent
    adaylar = []

    # Önce en muhtemel dosya adları
    tercih = [
        "veri (6).txt", "veri.txt",
        "HIZLI_ON_14_GUN_306_MASTER.txt",
        "HIZLI_ON_306_ZINCIR_MASTER_V2.txt"
    ]

    gorulen=set()
    yollar=[]
    for ad in tercih:
        p=kok/ad
        if p.exists():
            yollar.append(p)
            gorulen.add(str(p.resolve()))

    # Sonra repo ve alt klasörlerdeki tüm TXT'ler
    for p in kok.rglob("*.txt"):
        try:
            rp=str(p.resolve())
            if rp not in gorulen and ".git" not in p.parts:
                yollar.append(p)
                gorulen.add(rp)
        except:
            pass

    for p in yollar:
        try:
            text=p.read_text(encoding="utf-8", errors="ignore")
            d=parse_txt(text)
            if len(d):
                adaylar.append((len(d), p, d))
        except:
            continue

    if not adaylar:
        return None, None

    # En fazla geçerli çekiliş içeren veri dosyasını seç
    adaylar.sort(key=lambda x:x[0], reverse=True)
    _, p, d=adaylar[0]
    return str(p.relative_to(kok)), d

veri_dosyasi, df = github_verisini_bul()

if df is None or df.empty:
    st.error(
        "GitHub reposunda okunabilir Hızlı On TXT verisi bulunamadı. "
        "TXT satırları şu biçimde olmalı: "
        "51213;25.08.2026 00:02;2,4,...,80"
    )
    st.stop()

st.success(f"✅ GitHub verisi otomatik tanındı: {veri_dosyasi} — {len(df):,} çekiliş")

c1,c2,c3=st.columns(3)
c1.metric("Çekiliş",len(df))
c2.metric("İlk",f"#{df.draw_id.iloc[0]} — {df.time.iloc[0]}")
c3.metric("Son",f"#{df.draw_id.iloc[-1]} — {df.time.iloc[-1]}")

st.divider()
st.subheader("1) İstisnai üst aileleri bul")
overlap_min=st.slider("İki REAL20 arasında en az kaç ortak sayı?", 10, 18, 14)
if st.button("Üst aileleri tara", type="primary"):
    with st.spinner("Tüm çekiliş çiftleri karşılaştırılıyor..."):
        famdf=pairwise_families(df, overlap_min)
    st.session_state["famdf"]=famdf

famdf=st.session_state.get("famdf")
if famdf is not None:
    st.write(f"Bulunan çift: **{len(famdf):,}**")
    if len(famdf):
        show=famdf[["draw1","time1","draw2","time2","gap_draws","overlap"]].copy()
        st.dataframe(show, use_container_width=True, hide_index=True)

        exact=Counter(famdf.overlap)
        st.write("Örtüşme dağılımı:", dict(sorted(exact.items())))

        options=[]
        for k,r in famdf.iterrows():
            label=f"{k} | {r.overlap}/20 | #{r.draw1} ↔ #{r.draw2} | " + "-".join(map(str,r.family))
            options.append((label,k))
        label=st.selectbox("İncelenecek üst aile", [x[0] for x in options])
        idx=dict(options)[label]
        row=famdf.loc[idx]
        family=row.family

        st.subheader("2) Ailenin kronolojik doluluk yaşamı")
        st.write("Üst aile:", "**"+" - ".join(map(str,family))+"**")
        trace=occupancy_trace(df,family)

        a,b,c,d=st.columns(4)
        a.metric("Aile boyu",len(family))
        b.metric("8+ olduğu el",int((trace.occupancy>=8).sum()))
        c.metric("9+ olduğu el",int((trace.occupancy>=9).sum()))
        d.metric(f"{len(family)}/{len(family)} olduğu el",int((trace.occupancy==len(family)).sum()))

        dist=trace.occupancy.value_counts().sort_index().rename_axis("doluluk").reset_index(name="el")
        st.dataframe(dist, use_container_width=True, hide_index=True)

        st.line_chart(trace.set_index("time")["occupancy"])

        st.subheader("3) Birleşerek 8+'e yükselme")
        window=st.slider("Önceki kaç el içinde yükseliş ara?", 2, 50, 12)
        min_start=st.slider("Başlangıç doluluğu en az", 3, 7, 5)
        rises=rising_events(trace,min_start,8,window)
        st.write(f"Bulunan 8+ birleşme olayı: **{len(rises)}**")
        if len(rises):
            st.dataframe(rises, use_container_width=True, hide_index=True)

        st.subheader("4) 8'li alt kadrolar")
        if len(family)>=8:
            drawsets=[set(x) for x in df.numbers]
            records=[]
            for sub in itertools.combinations(family,8):
                s=set(sub)
                hits=[i for i,x in enumerate(drawsets) if s <= x]
                if len(hits)>=2:
                    records.append({
                        "8li":"-".join(map(str,sub)),
                        "kaç_REAL20":len(hits),
                        "ilk":int(df.at[hits[0],"draw_id"]),
                        "son":int(df.at[hits[-1],"draw_id"]),
                        "yayılım_el":hits[-1]-hits[0]
                    })
            subs=pd.DataFrame(records)
            if len(subs):
                subs=subs.sort_values(["kaç_REAL20","yayılım_el"], ascending=[False,True])
                st.dataframe(subs, use_container_width=True, hide_index=True)
                st.write("En yüksek 8/8 tekrar:", int(subs["kaç_REAL20"].max()))
            else:
                st.write("En az iki REAL20'de komple bulunan 8'li yok.")

        st.subheader("5) Patlamadan ÖNCEKİ yaşam")
        first=min(int(row.i),int(row.j))
        before=trace.iloc[:first]
        if len(before):
            counts={k:int((before.occupancy==k).sum()) for k in range(3,len(family)+1)}
            st.write(counts)
            last=before[before.occupancy>=6].tail(30)
            st.dataframe(last[["draw_id","time","occupancy","active"]],use_container_width=True,hide_index=True)

        st.warning("Bu ekran geçmiş örüntüyü keşfeder. Tahmin gücü için ayrıca yalnız geçmiş bilgiyi kullanan dondurulmuş walk-forward testi gerekir.")


# ============================================================
# 6) KOMPLE MASTER ANALİZ KÜTÜĞÜ
# ============================================================
st.divider()
st.subheader("6) Komple analiz çıktısı")

@st.cache_data(show_spinner=False)
def komple_master_analiz(df):
    sets=[set(x) for x in df.numbers]

    # Tek geçişte 10+ tüm çiftleri
    overlaps={k:[] for k in range(10,21)}
    for i in range(len(df)):
        ai=sets[i]
        for j in range(i+1,len(df)):
            inter=ai & sets[j]
            n=len(inter)
            if n>=10:
                overlaps[n].append((i,j,tuple(sorted(inter))))

    out=[]
    out.append("HIZLI ON - KOMPLE AILE / ORTUSME MASTER ANALIZ KUTUGU")
    out.append("="*72)
    out.append(f"CEKILIS SAYISI: {len(df)}")
    out.append(f"ILK: #{int(df.iloc[0].draw_id)} | {df.iloc[0].time}")
    out.append(f"SON: #{int(df.iloc[-1].draw_id)} | {df.iloc[-1].time}")
    out.append("")

    out.append("A) 10+ ORTAK REAL20 OZETI")
    out.append("-"*72)
    for k in range(10,21):
        out.append(f"{k}/20 ORTAK CIFTLER: {len(overlaps[k])}")
    out.append("")

    # 10-14 detay
    for k in range(10,15):
        out.append("="*72)
        out.append(f"B{k}) TAM {k}/20 ORTAK OLAYLAR")
        out.append("="*72)
        for no,(i,j,fam) in enumerate(overlaps[k],1):
            t1=df.at[i,"time"]; t2=df.at[j,"time"]
            out.append(
                f"{no}. #{int(df.at[i,'draw_id'])} | {t1}  <->  "
                f"#{int(df.at[j,'draw_id'])} | {t2} | "
                f"EL_ARALIGI={j-i} | ZAMAN={t2-t1} | "
                f"ORTAK={','.join(map(str,fam))}"
            )
        out.append("")

    # 14+ ailelerin ayrıntılı yaşamı
    high=[]
    for k in range(14,21):
        high.extend([(k,i,j,f) for i,j,f in overlaps[k]])

    out.append("="*72)
    out.append("C) 14+ UST AILELERIN TAM YASAM / DOLULUK ANALIZI")
    out.append("="*72)

    for fam_no,(k,i,j,fam) in enumerate(high,1):
        fs=set(fam)
        out.append("")
        out.append(f"[UST_AILE_{fam_no}] BOY={k}")
        out.append(f"ANA_OLAY: #{int(df.at[i,'draw_id'])} {df.at[i,'time']} <-> #{int(df.at[j,'draw_id'])} {df.at[j,'time']}")
        out.append("AILE="+",".join(map(str,fam)))

        occ=[]
        for x,s in enumerate(sets):
            active=sorted(fs&s)
            occ.append(len(active))
        dist=Counter(occ)
        out.append("DOLULUK_DAGILIMI="+", ".join(f"{z}:{dist[z]}" for z in sorted(dist)))

        # 6+ tüm kronoloji
        out.append("6+ KRONOLOJI:")
        for x,n in enumerate(occ):
            if n>=6:
                active=sorted(fs & sets[x])
                out.append(
                    f"  #{int(df.at[x,'draw_id'])} | {df.at[x,'time']} | "
                    f"{n}/{k} | {','.join(map(str,active))}"
                )

        # ilk ana olaydan önceki 6/7/8/9...
        out.append("ILK_ANA_OLAY_ONCESI:")
        for z in range(6,k+1):
            inds=[x for x in range(i) if occ[x]==z]
            out.append(f"  {z}/{k}: {len(inds)} el")
            if inds:
                x=inds[-1]
                out.append(
                    f"    SON: #{int(df.at[x,'draw_id'])} {df.at[x,'time']} | "
                    f"ANA_OLAYA_EL={i-x} | "
                    f"{','.join(map(str,sorted(fs&sets[x])))}"
                )

        # 6/7 -> 8+ kısa pencere birleşmeleri
        out.append("BIRLESEREK_8+ OLAYLARI (onceki 50 el):")
        for end in range(len(df)):
            if occ[end] < 8: continue
            lo=max(0,end-50)
            prev=occ[lo:end]
            if not prev: continue
            best=max(prev)
            if 6 <= best < 8:
                starts=[lo+p for p,v in enumerate(prev) if v==best]
                start=starts[-1]
                out.append(
                    f"  #{int(df.at[start,'draw_id'])} {best}/{k} -> "
                    f"#{int(df.at[end,'draw_id'])} {occ[end]}/{k} | "
                    f"{end-start} el"
                )

        # 8'li alt kadrolar: en az 2 REAL20'de 8/8
        if k>=8:
            out.append("8LI_ALT_KADROLAR (en az 2 kez 8/8):")
            subs=[]
            for sub in itertools.combinations(fam,8):
                ss=set(sub)
                hits=[x for x,s in enumerate(sets) if ss <= s]
                if len(hits)>=2:
                    subs.append((len(hits),hits[-1]-hits[0],sub,hits))
            subs.sort(key=lambda x:(-x[0],x[1],x[2]))
            out.append(f"  TOPLAM={len(subs)}")
            for hitn,spread,sub,hits in subs:
                out.append(
                    f"  8LI={','.join(map(str,sub))} | 8/8={hitn} kez | "
                    f"YAYILIM={spread} el | "
                    f"ELLER="+",".join(f"#{int(df.at[x,'draw_id'])}" for x in hits)
                )

    # 10 ortak olaylardan 9'lu çekirdek aileleri
    out.append("")
    out.append("="*72)
    out.append("D) 10/20 OLAYLARINDAN 9'LU CEKIRDEK / NOBETCI ANALIZI")
    out.append("="*72)

    ten_fams=list(dict.fromkeys(f for _,_,f in overlaps[10]))
    nine_map=defaultdict(list)
    for tf in ten_fams:
        for nine in itertools.combinations(tf,9):
            nine_map[nine].append(tf)

    repeated={n:list(dict.fromkeys(v)) for n,v in nine_map.items()
              if len(set(v))>=2}
    out.append(f"EN_AZ_2_FARKLI_10LUDA_YASAYAN_9LU_CEKIRDEK={len(repeated)}")
    for no,(nine,tens) in enumerate(sorted(repeated.items()),1):
        extras=[]
        for tf in tens:
            extra=sorted(set(tf)-set(nine))
            extras.extend(extra)
        out.append(
            f"{no}. CEKIRDEK={','.join(map(str,nine))} | "
            f"10LU_AILE={len(tens)} | NOBETCILER={','.join(map(str,sorted(set(extras))))}"
        )

    return "\n".join(out)

if st.button("🧠 KOMPLE MASTER ANALİZİ ÜRET", type="primary", use_container_width=True):
    with st.spinner("3.038 çekilişin tüm çiftleri ve alt aileleri hesaplanıyor..."):
        master_text=komple_master_analiz(df)
        st.session_state["master_text"]=master_text

if "master_text" in st.session_state:
    master_text=st.session_state["master_text"]
    st.success(f"MASTER analiz hazır — {len(master_text):,} karakter")
    st.download_button(
        "📥 KOMPLE_ANALIZ_MASTER.txt İNDİR",
        data=master_text.encode("utf-8"),
        file_name="HIZLI_ON_KOMPLE_AILE_ANALIZ_MASTER.txt",
        mime="text/plain",
        use_container_width=True
    )
    with st.expander("Çıktının ilk bölümünü göster"):
        st.text(master_text[:12000])

