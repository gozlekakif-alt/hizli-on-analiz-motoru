# -*- coding: utf-8 -*-
"""V232 Streamlit: five transition-aware hypothesis tickets, kept separate
from immutable 22:57 baseline. Only pretarget locked tickets are called LIVE.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from v232_gecis_motorlari import (
    ENGINES, VERSION, as_time, backtest_nights, build_tickets, character,
    four_paths, next_target, source_key, to_csv,
)


@st.cache_data(show_spinner=False, max_entries=2)
def _historical_backtest(source_hash, _cleaned_rows):
    return backtest_nights(list(_cleaned_rows),max_nights=70)


def _plain(rows):
    return [dict(no=int(r["no"]),dt=str(r["dt"]),nums=tuple(r["nums"]))
            for r in rows]


def render_v232(day, dayrows, allrows, frozen, arrows, night):
    st.subheader("🧬 V232 — Karakter Geçişine Göre Kupon Motorları")
    st.caption("Sabit 22:57 havuzu (5×16) korunur. Motorlar günün dört sıcaklık "
               "anına ve hedef öncesindeki son 72 gerçek çekilişe bakar. "
               "İleriye dönük tahmin üstünlüğü henüz kanıtlanmadı.")
    rows=sorted(_plain(allrows),key=lambda r:r["dt"])
    try:
        paths=four_paths(rows,day)
    except ValueError as exc:
        st.error("Gündüz dört anlık yol oluşturulamadı: "+str(exc))
        return

    locked=st.session_state.setdefault("v232_locked",{})
    now=datetime.now(ZoneInfo("Europe/Istanbul")).replace(tzinfo=None)
    st.info("**Beş hipotez motoru + bir rastgele kontrol** her hedefe birer 10'lu "
            "üretir. Aynı anda bir kolon kullanmak istersen motor bazında seçebilirsin. "
            "Bunlar kazanma garantisi değildir.")
    tab1,tab2,tab3=st.tabs([
        "🔒 Sonraki çekiliş için dondur", "📉 70 gece gerçek backtest",
        "🧭 80 sayının geçiş karakteri",
    ])

    with tab1:
        nxt=next_target(rows,day)
        st.markdown("#### Yeni 20'li gelmeden ÖNCE kolonları kilitle")
        if nxt is None:
            st.success("Bu operasyonel gece için 25 gerçek çekiliş tamamlanmış.")
        else:
            slot,stamp=nxt
            target=datetime.fromisoformat(stamp)
            key=day+"|"+stamp
            st.write(f"**Hedef #{slot+1} · {target:%d.%m.%Y %H:%M}**")
            if key in locked:
                st.info("Bu hedefin kolonları daha önce donduruldu. Sonuç yüklenene kadar değiştirilemez.")
            elif target<=now or (rows and as_time(rows[-1])>=target):
                st.warning("Bu hedef geçmişte kalmış veya veri dosyasında daha sonraki "
                           "çekilişler var. Geçmişe dönük yeni kuponu canlı tahmin diye "
                           "kilitlemiyoruz. Gerçek sınama için '70 gece backtest' sekmesini aç.")
            else:
                prior=[r for r in rows if as_time(r)<target]
                if len(prior)<72:
                    st.error("Bu hedef için geçmişte 72 çekiliş bulunmuyor.")
                elif st.button("🔒 5 motor + rastgele kontrolü kilitle",
                               type="primary",use_container_width=True,key="v232_lock"):
                    try:
                        choices=build_tickets(prior,frozen,paths,stamp)
                        locked[key]={
                            "gun":day,"hedef":stamp,"hedef_sira":slot+1,
                            "kayit_zamani":now.isoformat(timespec="seconds"),
                            "son_bilinen_cekilis":prior[-1]["dt"],
                            "veri_izi":source_key(prior),
                            "sabit_havuz":{str(k):int(v) for k,v in frozen.items()},
                            "kolonlar":{m:list(nums) for m,nums in choices.items()},
                            "surum":VERSION,
                        }
                        st.rerun()
                    except Exception as exc:
                        st.error("Kolonlar oluşturulamadı: "+str(exc))

        saved={k:v for k,v in locked.items() if v["gun"]==day}
        if not saved:
            st.caption("Henüz bu geceye ait kilitlenmiş bir kolon paketi yok. "
                       "Eski günler için 70 gece backtest yöntemini kullan.")
        for key,v in sorted(saved.items()):
            stamp=v["hedef"]
            record=next((r for r in rows if r["dt"]==stamp),None)
            with st.container(border=True):
                st.markdown(f"**{stamp[11:16]} — Hedef öncesi dondurulmuş kolonlar**")
                st.caption("Son bilinen veri "+v["son_bilinen_cekilis"]+
                           " · Kayıt "+v["kayit_zamani"])
                results=[]
                for name,ticket in v["kolonlar"].items():
                    hits=len(set(ticket).intersection(record["nums"])) if record else None
                    results.append({"Motor":name,"10'lu":" ".join(f"{n:02d}" for n in ticket),
                                    "İsabet":f"{hits}/10" if hits is not None else "Henüz sonuç yok"})
                st.dataframe(results,hide_index=True,use_container_width=True)
        if saved:
            st.download_button("📦 Kilitli gece kolonlarını JSON yedekle",
               data=json.dumps(saved,ensure_ascii=False,indent=2),
               file_name=f"V232_KILITLI_{day}.json",mime="application/json",
               use_container_width=True)
            st.caption("Kilitler Streamlit oturumu boyunca korunur; yedeği indir. "
                       "Uygulama yeniden başladığında kilitlerin otomatik kalıcı veritabanı yoktur.")

    with tab2:
        st.markdown("#### 70 tam gece · 5 motor ve rastgele kontrol")
        st.caption("Her gecenin 22:57 havuzu 192 gerçek gündüz çekilişinden "
                   "dondurulur. 23:02'den sonraki her hedef için yalnız "
                   "o hedeften önce gerçekleşen çekilişler kullanılır. "
                   "Henüz bilinmeyen sonuçların sayıları kupon üretimine girmez.")
        signature=source_key(rows)
        if st.button("▶️ Hedef öncesi 70 geceyi tek tek sına",
                     type="primary",use_container_width=True,key="v232_backtest"):
            try:
                with st.spinner("Her hedefte kolonları dondurup gerçek 20 ile karşılaştırıyor..."):
                    compact=tuple((r["no"],r["dt"],tuple(r["nums"])) for r in rows)
                    result=_historical_backtest(signature,tuple(
                        {"no":no,"dt":dt,"nums":list(nums)}
                        for no,dt,nums in compact))
                st.session_state["v232_backtest_result"]={
                    "source":signature,"report":result}
            except Exception as exc:
                st.error("Gece testi gerçekleştirilemedi: "+str(exc))
        saved=st.session_state.get("v232_backtest_result")
        if saved:
            if saved["source"] != signature:
                st.warning("Veri değişti. Bu sonuç yeni kaynağa ait değil; yeniden test et.")
            else:
                report=saved["report"]
                a,b,c=st.columns(3)
                a.metric("Tam gece",report["test_nights"])
                b.metric("Gerçek hedef",report["test_targets"])
                c.metric("Her hedefte 10'lu",len(ENGINES))
                st.dataframe(report["summary"],hide_index=True,use_container_width=True)
                st.markdown("#### Gün gün ortalama isabet")
                st.dataframe(report["day_summary"],hide_index=True,use_container_width=True)
                for label,data,name in (
                    ("Motorların 0–10 isabet dağılımını indir",report["summary"],"ozet"),
                    ("70 gün tek tek indir",report["day_summary"],"gun"),
                    ("Her gerçek hedef ve dondurulmuş 10'lular",report["detail"],"tum_kolonlar"),
                ):
                    st.download_button(label,data=to_csv(data),
                         file_name=f"V232_{name}_{day}.csv",mime="text/csv",
                         key="v232_"+name)
                st.caption("Bu 72 günlük geçmiş, yöntem geliştirmede kullanılmış "
                           "olabileceği için **keşif testi** sayılır. "
                           "Bağımsız üstünlük iddiası için yeni günlerde kilitli sınav gereklidir.")

    with tab3:
        prior=[r for r in rows if as_time(r).date().isoformat()==day
               and as_time(r).time()<=datetime.strptime("22:57","%H:%M").time()]
        if len(prior)>=72:
            state=character(paths,prior,frozen)
            cols=[]
            for n in range(1,81):
                entry=state[n]
                cols.append({
                    "Sayı":n,"22:57 sabit":f"H{frozen[n]+1}",
                    "11:57 → 15:57 → 19:57 → 22:57":entry["yol"],
                    "Karakter":entry["sinif"],"Son6 değişim":entry["son6_fark"],
                    "Ters dönüş":entry["donus"]})
            st.dataframe(cols,use_container_width=True,hide_index=True,height=450)
            counts={}
            for v in state.values():
                counts[v["sinif"]]=counts.get(v["sinif"],0)+1
            st.write("**Gün içi karakter sayıları:** "+", ".join(
                     f"{name}: {count}" for name,count in sorted(counts.items())))
            st.caption("Dört gündüz noktası son 72 çekilişlik hareketli havuz "
                       "fotoğraflarıdır; en üstteki 192 çekilişlik sabit havuz başka ölçüdür.")
        else:
            st.warning("Gün içi yol karakteri için geçmiş çekilişler eksik.")
