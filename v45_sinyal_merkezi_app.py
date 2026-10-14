# -*- coding: utf-8 -*-
"""V45 Streamlit Sinyal Merkezi; historical reads only, no PIN or GitHub writes."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
import csv
import hashlib
import json
import zipfile

import streamlit as st
from v45_sinyal_kor_test import (
    START, TARGET_DAYS, SLOTS, MODELS, candidates, model_stats,
    select_by_counts, hour_first6,
)

WORKFLOW_URL = "https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/workflows/v45-sinyal-ileritest.yml"
NAMES = {
    "LAG9_45DK_CARRY20": "45 dakika / 9 çekiliş tekrar",
    "LAG1_KONTROL20": "Önceki çekiliş",
    "LAG12_KONTROL20": "12 çekiliş önceki",
    "AYNA_ONCEKI20": "Ayna 20",
    "SON6_SICAK10": "Son 6 sıcak 10",
    "SON6_SOGUK10": "Son 6 soğuk 10",
    "SON6_SICAK20": "Son 6 sıcak 20",
    "SON6_SOGUK20": "Son 6 soğuk 20",
    "SON72_SICAK20": "Son 72 sıcak 20",
    "SON72_SOGUK20": "Son 72 soğuk 20",
    "SAAT_ILK6_SICAK10": "Saat ilk 6 sıcak 10",
    "SAAT_ILK6_SOGUK20": "Saat ilk 6 soğuk 20",
    "SAAT_ILK6_BANT_TERS20": "Bant ters hareket",
    "BEKLEYEN_UZUN20": "Bekleyen 20",
    "AILE_IKILI_ESLIK20": "İkili aile eşlik",
    "AILE_UCLU_ESLIK20": "Üçlü aile eşlik",
    "RASTGELE10_KONTROL": "Rastgele 10 kontrol",
    "RASTGELE20_KONTROL": "Rastgele 20 kontrol",
}

def _days(draws):
    """Reject incomplete days; never invent a missing draw."""
    byday = defaultdict(dict)
    conflicts = []
    for r in draws:
        try:
            d = date.fromisoformat(str(r["day"]))
            pos = int(r["pos"])
            numbers = frozenset(int(n) for n in r["nums"])
            if not (1 <= pos <= 217 and len(numbers) == 20
                    and all(1 <= n <= 80 for n in numbers)):
                continue
            item = {"day": d.isoformat(), "id": int(r["no"]),
                    "time": SLOTS[pos - 1], "nums": numbers}
            if pos in byday[d] and byday[d][pos] != item:
                conflicts.append(f"{d.isoformat()} #{pos}")
                continue
            byday[d][pos] = item
        except (KeyError, ValueError, TypeError):
            continue
    full = [(d, [positions[p] for p in range(1, 218)])
            for d,positions in sorted(byday.items())
            if len(positions) == 217 and set(positions) == set(range(1,218))]
    included = [(d,day) for d,day in full if d >= START]
    partial = [(d,n) for d,records in sorted(byday.items())
               if d >= START and len(records) < 217
               for n in [len(records)]]
    return included[:TARGET_DAYS], included[TARGET_DAYS:], partial, conflicts, byday

def _sig(day, idx):
    picks = candidates(day, idx)
    # The 01:02->07:02 break must not count as 45 minutes.
    for lag,name in ((1,"LAG1_KONTROL20"),
                     (9,"LAG9_45DK_CARRY20"),
                     (12,"LAG12_KONTROL20")):
        if name in picks:
            a = datetime.fromisoformat(day[idx]["day"]+"T"+day[idx]["time"])
            b = datetime.fromisoformat(day[idx-lag]["day"]+"T"+day[idx-lag]["time"])
            if a-b != timedelta(minutes=5*lag):
                del picks[name]
    return picks

@st.cache_data(ttl=600,show_spinner=False)
def _run_analysis(source_key, normalized):
    rows=[]
    for daytext,entries in normalized:
        day=[{"day":daytext,"id":no,"time":clock,"nums":frozenset(nums)}
             for no,clock,nums in entries]
        for i,r in enumerate(day):
            selections = _sig(day,i)
            for name,picks in selections.items():
                rows.append({"day":daytext,"time":r["time"],"id":r["id"],
                    "slot":i+1,"H7_12":int(hour_first6(day,i) is not None),
                    "model":name,"size":len(picks),
                    "selected":",".join(str(x) for x in sorted(picks)),
                    "hits":len(r["nums"].intersection(picks)),"fair":len(picks)/4})
    summary=model_stats(rows,normalized)
    return rows,summary

def _csv(rows,keys):
    stream=StringIO()
    w=csv.DictWriter(stream,fieldnames=keys,extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return stream.getvalue()

def _make_zip(rows,summary,selected_days):
    out=BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_DURUM.json",json.dumps({
            "pre_registered_start":START.isoformat(),
            "full_new_days":selected_days,"target":TARGET_DAYS,
            "predictive_edge_proven":False,
            "warning":"Selection across 18 models is NOT multiplicity-adjusted. "
                      "Follow with genuinely new unseen data."
        },ensure_ascii=False,indent=2))
        z.writestr("01_CEKILIS_ONCESI_10_20_LISTELER.csv",
                   _csv(rows,["day","time","id","slot","H7_12","model",
                              "size","selected","hits","fair"]))
        z.writestr("02_ISABET_OZET.csv",
                   _csv(summary,["model","coupon_size","full_days","targets",
                                 "mean_hits","fair_mean","delta_vs_fair",
                                 "positive_days","daily_CI95_descriptive"]))
        z.writestr("03_SINYAL_KATALOGU.csv",
                   _csv([{"model":key,
                          "description":NAMES.get(key,key),
                          "coupon_size":size,
                          "fair_expected_hits":size/4,
                          "status":"Aday; gelecek avantajı kanıtlanmadı"}
                         for key,size in MODELS.items()],
                        ["model","description","coupon_size",
                         "fair_expected_hits","status"]))
        z.writestr("04_72_GUN_GECMIS_BULGULAR.txt",
                   "V45 - 72 GUN GECMISTEN GELEN SINYAL ADAYLARI\n"
                   "Kaynak araligi: 01.08.2026 - 12.10.2026, 72 tam gun / 15.624 cekilis.\n"
                   "Sinyal kesfi bu veri uzerinde yapildigi icin bagimsiz ileri kanit DEGILDIR.\n"
                   "Son 36 gun: 9 cekilis/45 dakika gecikmede ortak sayi 5,0645/20;\n"
                   "adil beklenti 5,0. Ilk 36 gunde yaklasik 4,9949/20 idi.\n"
                   "Bu gecikme 40 farkli gecikme arasindan sonradan secilmistir.\n"
                   "Saatin ilk 6 cekilisinden soguk 20'li: son 36 gun\n"
                   "H7-H12 hedeflerinde ortalama 5,0617/20; adil beklenti 5,0.\n"
                   "Saatin ilk 6 cekilisinden sicak 10'lu: 2,5129/10;\n"
                   "adil beklenti 2,5.\n"
                   "V44 72-gunluk onceden kilitli elemede 19 adaydan 0 kabul.\n"
                   "Eski 72 gunde yuksek gorunen adaylari yeni kanit diye okumayin.\n"
                   "Yeni 14 tam gun tamamlanmadan sinyal onayi verilmeyecek.\n")
        z.writestr("00_TEK_SAYFA_SONUC.txt",
                   "V45 Sinyal Merkezi - YENI TAM GUN testi\n"
                   f"Yeni tam gun sayisi: {len(selected_days)}/{TARGET_DAYS}\n"
                   "10 sayi icin teorik isabet 2,5; 20 sayi icin 5.\n"
                   "Hedefe karsi guvenilir ustunluk dogrulanmadi.\n"
                   + ("Yeni tam gun olmadigi icin henuz isabet tablosu bos.\n"
                      if not selected_days else
                      "Listeler hedef acilmadan once hesaplanmistir.\n")
                   + "Gecmis 72 gun bulgulari ayri dosyadadir, yeni test degildir.\n"
                   + "\n".join(
                       f"{NAMES.get(r['model'],r['model'])}: "
                       f"{r['mean_hits']}/{r['coupon_size']}"
                       for r in summary
                   ))
    return out.getvalue()

def _radar(byday):
    if not byday: return
    latest_day=max(byday)
    positions=byday[latest_day]
    ix=max(positions)
    prev=[positions.get(i) for i in range(ix-5,ix+1)]
    if len(prev)!=6 or any(x is None for x in prev): return
    st.markdown("#### Son kayıtlardaki hareket göstergeleri")
    st.caption(f"Son kaynak: {latest_day.isoformat()} {positions[ix]['time']}. "
               "Bunlar geçmiş gözlemlerdir, kazanma sinyali değildir.")
    a,b=st.columns(2)
    a.markdown("**Son 6 sıcak 10**")
    a.code("-".join(map(str,select_by_counts(prev,10))))
    b.markdown("**Son 6 soğuk 10**")
    b.code("-".join(map(str,select_by_counts(prev,10,True))))
    if ix-9 in positions:
        stamp=datetime.fromisoformat(positions[ix]["day"]+"T"+positions[ix]["time"])
        old=datetime.fromisoformat(positions[ix-9]["day"]+"T"+positions[ix-9]["time"])
        if stamp-old==timedelta(minutes=45):
            overlap=len(positions[ix]["nums"] & positions[ix-9]["nums"])
            st.metric("Son geçmiş 45 dakika tekrarı",f"{overlap}/20")
            st.caption("Adil beklenti 5 ortaktır; tek gerçekleşme geleceği öngörmez.")

def render_v45(draws):
    st.subheader("🔍 V45 — Sinyal Merkezi")
    st.caption("Sinyal ailelerini, bantları, sıcak-soğuk geçişlerini ve "
               "45 dakika tekrarını gerçek yeni veride karşılaştırır.")
    chosen,additional,partials,conflicts,byday=_days(draws)
    c1,c2,c3=st.columns(3)
    c1.metric("Yeni tam gün",f"{len(chosen)}/{TARGET_DAYS}")
    c2.metric("Araştırma yöntemi",len(MODELS))
    c3.metric("Kalan gün",TARGET_DAYS-len(chosen))
    if conflicts:
        st.error(f"Çakışan çekilişler: {len(conflicts)}. Eksik veriler tamamlanmalı.")
    if partials:
        st.caption("Eksik yeni gün: "+", ".join(
            f"{d.isoformat()} ({n}/217)" for d,n in partials[-5:]))
    if additional:
        st.caption(f"14 gün kilitlendi; {len(additional)} sonraki tam gün "
                   "ilave doğrulamaya ayrılabilir.")
    if len(chosen)<TARGET_DAYS:
        st.warning(f"Kor test henüz tamamlanmadı: {len(chosen)}/14. "
                   "Hiçbir sinyal başarılı ilan edilemez.")
    else:
        st.info("14 tam gün tamamlandı; üstünlük iddiası için bağımsız "
                "tekrar ve çoklu deneme düzeltmesi gerekir.")
    st.markdown("#### Sinyal adayları")
    st.dataframe([
        {"Sinyal":"45 dakika / 9 çekiliş tekrar","Durum":"Takip ediliyor",
         "Adil beklenti":"20 sayıda 5"},
        {"Sinyal":"Saat ilk 6 → sonraki 6 soğuk havuz","Durum":"Takip ediliyor",
         "Adil beklenti":"20 sayıda 5"},
        {"Sinyal":"Aile, bant, ayna, bekleme, sıcaklık","Durum":"Deneysel",
         "Adil beklenti":"Sayı başına %25"},
    ],hide_index=True,use_container_width=True)
    _radar(byday)
    st.markdown("#### Gerçek yeni gün testi")
    if not chosen:
        st.info("14 Ekim ve sonrası 217/217 tam gün henüz bulunmuyor. "
                "Şimdilik geçmiş sinyal bulgularını ve 18 yöntem kataloğunu "
                "tek ZIP olarak indirebilirsin. Yeni tam günler geldikçe "
                "ayrıca gerçek isabet tabloları eklenecek.")
        st.download_button("⬇️ V45 TEK RAPOR ZIP İNDİR — BANA GÖNDER",
            data=_make_zip([], [], []),
            file_name="V45_SINYAL_MERKEZI_TEK_RAPOR.zip",
            mime="application/zip",key="v45_download_waiting",
            type="primary",use_container_width=True)
        st.caption("Bu düğme başka bir siteye gitmez; ZIP doğrudan telefonuna iner.")
        return
    normalized=tuple((d.isoformat(),tuple(
        (r["id"],r["time"],tuple(sorted(r["nums"]))) for r in day
    )) for d,day in chosen)
    ident=hashlib.sha256(repr(normalized).encode()).hexdigest()
    if st.button("▶️ V45 TÜM SİNYALLERİ ANALİZ ET",
                 type="primary",use_container_width=True,key="v45_run"):
        try:
            with st.spinner("Hedefleri görmeden dondurulmuş listeler test ediliyor..."):
                rows,summary=_run_analysis(ident,normalized)
            st.session_state["v45_report"]=(ident,rows,summary)
        except Exception as exc:
            st.error("V45 çalıştırılamadı: "+str(exc))
    result=st.session_state.get("v45_report")
    if not result:
        st.caption("Yeni tam günler için yukarıdaki düğmeye bas.")
        return
    if result[0]!=ident:
        st.warning("Çekiliş verisi değişti; güncel sonuç için tekrar analiz et.")
        return
    _,rows,summary=result
    st.dataframe([{
        "Sinyal":NAMES.get(r["model"],r["model"]),
        "Boyut":r["coupon_size"],"Test çekilişi":r["targets"],
        "Ortalama isabet":r["mean_hits"],"Adil":r["fair_mean"],
        "Fark":r["delta_vs_fair"]
    } for r in summary],hide_index=True,use_container_width=True)
    st.download_button("⬇️ V45 TEK RAPOR ZIP İNDİR — BANA GÖNDER",
        _make_zip(rows,summary,[d.isoformat() for d,_ in chosen]),
        file_name="V45_SINYAL_MERKEZI_TEK_RAPOR.zip",
        mime="application/zip",key="v45_download",type="primary",
        use_container_width=True)
    st.caption("Tüm modeller deneysel; çoklu denemelerde rastlantısal "
               "yüksek sonuçlar kanıtlı tahmin başarısı değildir.")
    st.caption("Rapor doğrudan bu sayfadan indirilir; GitHub'a gitmen gerekmez.")
