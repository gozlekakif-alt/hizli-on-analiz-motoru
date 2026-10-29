# -*- coding: utf-8 -*-
"""V230 - Hızlı On: sabit 22:57 anlık görüntü, canlı 25 gece sonucu, ortak motorlar.
Eski V10/V18/V40/V42/V44/V45/V50/V52 dosyalarına dokunmaz.
Çekilişleri önceden bilmez; kayıtlar girildikçe analiz eder.
"""
from __future__ import annotations

import csv
import gzip
import html
import importlib
import io
import json
import random
import re
import zipfile
from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

st.set_page_config(page_title="Hızlı On | Gece Merkezi V230", page_icon="🌙",
                   layout="wide", initial_sidebar_state="expanded")

NAMES = ("Çok soğuk", "Serin", "Nötr", "Ilık", "Çok sıcak")
COLORS = ("#334e7e", "#4b83b6", "#718f89", "#ce9b52", "#c15c47")
REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
RAW_URL = "https://raw.githubusercontent.com/" + REPO + "/main/veri.txt"
TR_TZ = ZoneInfo("Europe/Istanbul")

st.markdown("""
<style>
.block-container {padding-top:1rem;max-width:1650px}
.pool-grid {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:12px 0}
.pool {border:1px solid #8b8b8b60;border-radius:12px;padding:10px;min-width:0}
.pool-title {font-size:1.02rem;font-weight:750;margin-bottom:8px}
.pool-items {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}
.ball {border:1px solid #77777750;border-radius:8px;padding:5px 3px;text-align:center;
 font-size:.87rem;font-variant-numeric:tabular-nums;white-space:nowrap}
.ball b {font-size:1rem}
.mini {opacity:.85;font-size:.74rem}
.balls-line {line-height:2.35rem;overflow-wrap:anywhere}
.ball-inline {display:inline-block;margin:2px 4px 2px 0;border-radius:7px;border:1px solid #77777750;
 padding:2px 7px;font-size:.89rem;font-variant-numeric:tabular-nums}
@media(max-width:1020px) {.pool-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:550px) {.pool-grid{grid-template-columns:1fr}.pool-items{grid-template-columns:repeat(4,minmax(0,1fr))}}
</style>
""", unsafe_allow_html=True)

def numbers(value):
    vals = [int(v) for v in re.findall(r"\d+", value)]
    if len(vals) != 20 or len(set(vals)) != 20 or any(n < 1 or n > 80 for n in vals):
        raise ValueError("1–80 arasında 20 farklı sayı girilmeli.")
    return sorted(vals)

def parse_stamp(raw):
    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    raise ValueError("Tarih biçimi: GG.AA.YYYY SS:DD")

def pos_of(dt):
    m = dt.hour * 60 + dt.minute
    if 2 <= m <= 62 and (m - 2) % 5 == 0:
        return 1 + (m - 2) // 5
    if 422 <= m <= 1437 and (m - 422) % 5 == 0:
        return 14 + (m - 422) // 5
    raise ValueError("Geçersiz çekiliş saati.")

def record(ident, dt, nums):
    pos = pos_of(dt)
    return {"no":int(ident), "dt":dt.strftime("%Y-%m-%d %H:%M"),
            "day":dt.date().isoformat(), "pos":pos, "nums":numbers(" ".join(map(str,nums)))}

@st.cache_data(show_spinner=False, max_entries=2)
def parse_text(txt):
    result, errors = [], []
    for i, line in enumerate(txt.splitlines(), 1):
        if not re.match(r"^\s*\d+\s*;", line):
            continue
        try:
            ident, moment, nums = line.split(";", 2)
            result.append(record(int(ident), parse_stamp(moment), numbers(nums)))
        except (ValueError, TypeError) as exc:
            errors.append(f"Satır {i}: {exc}")
    return result, errors

def combine(txt, local):
    parsed, errors = parse_text(txt)
    bytime, byid = {}, {}
    all_rows = []
    for r in sorted(parsed + local, key=lambda x: x["dt"]):
        dt, ident = r["dt"], r["no"]
        old = bytime.get(dt) or byid.get(ident)
        if old:
            if old != r:
                errors.append(f"Çakışma: {dt}, #{ident}; ikinci kayıt alınmadı.")
            continue
        bytime[dt] = r
        byid[ident] = r
        all_rows.append(r)
    return all_rows, errors

def ingest_bytes(payload, filename):
    if len(payload) > 35_000_000:
        raise ValueError("Dosya çok büyük (üst sınır 35 MB).")
    name = filename.lower()
    if name.endswith(".gz"):
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as f:
            payload = f.read(50_000_001)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            candidates = [x for x in z.namelist()
                          if x.lower().endswith((".txt", ".csv")) and not x.endswith("/")]
            if not candidates:
                raise ValueError("ZIP içinde TXT veya CSV bulunamadı.")
            candidates.sort(key=lambda x: ("veri.txt" not in x.lower() and
                                            "ham_veri" not in x.lower(), len(x)))
            with z.open(candidates[0]) as f:
                payload = f.read(50_000_001)
    if len(payload) > 50_000_000:
        raise ValueError("Açılan dosya çok büyük.")
    return payload.decode("utf-8-sig", errors="replace")

def daytime(day, rows):
    d = date.fromisoformat(day)
    relevant = [r for r in rows
                if date.fromisoformat(r["day"]) == d and
                time(7, 2) <= datetime.fromisoformat(r["dt"]).time() <= time(22, 57)]
    slots = {r["pos"]:r for r in relevant}
    if set(slots) != set(range(14, 206)):
        return [], len(slots)
    return [slots[i] for i in range(14, 206)], 192

def night_slot(dt, d):
    # 23:02...23:57 on d, then 00:02...01:02 on d+1
    origin = datetime.combine(d, time(23,2))
    delta = int((dt-origin).total_seconds() // 60)
    if dt-origin != timedelta(minutes=delta) or delta % 5 or not 0 <= delta <= 120:
        return None
    return delta // 5

def night_rows(day, rows):
    d = date.fromisoformat(day)
    existing = {}
    for r in rows:
        p = night_slot(datetime.fromisoformat(r["dt"]), d)
        if p is not None:
            existing[p] = r
    return existing

def rank_pools(counts):
    # Strict 16+16+16+16+16. Equal frequency: smaller number first.
    order = sorted(range(1,81), key=lambda n: (counts[n], n))
    return {n: i // 16 for i,n in enumerate(order)}

def delta_arrows(rows):
    # Rate comparison: last 36 vs previous 156, NOT a forecast.
    old = Counter(n for r in rows[:-36] for n in r["nums"])
    new = Counter(n for r in rows[-36:] for n in r["nums"])
    return {n: "→" if new[n]*156 > old[n]*36 else
               "←" if new[n]*156 < old[n]*36 else "=" for n in range(1,81)}

def baseline(dayrows):
    counts = Counter(n for r in dayrows for n in r["nums"])
    return counts, rank_pools(counts), delta_arrows(dayrows)

def moving_state(history):
    # Moving window 72, separate from frozen all-day 192.
    hist = history[-72:]
    counts = Counter(n for r in hist for n in r["nums"])
    pools = rank_pools(counts)
    if len(hist) < 72:
        return counts, pools, {n:"=" for n in range(1,81)}
    return counts, pools, {
        n: "→" if sum(n in r["nums"] for r in hist[-36:]) >
                  sum(n in r["nums"] for r in hist[:36]) else
        "←" if sum(n in r["nums"] for r in hist[-36:]) <
                  sum(n in r["nums"] for r in hist[:36]) else "="
        for n in range(1,81)
    }

def one_chip(n, count, arrow, color, inline=False):
    cls = "ball-inline" if inline else "ball"
    return (f'<span class="{cls}" style="background:{color}20;border-color:{color}80">'
            f'<b>{n:02d}</b> <span class="mini">({count}) {arrow}</span></span>')

def pool_html(counts, pools, arrows):
    parts = ['<div class="pool-grid">']
    for k in range(5):
        items = sorted(n for n in range(1,81) if pools[n] == k)
        parts.append(f'<section class="pool" style="border-top:5px solid {COLORS[k]}">'
                     f'<div class="pool-title">{NAMES[k]} · H{k+1} · {len(items)} sayı</div>'
                     '<div class="pool-items">')
        parts.extend(one_chip(n,counts[n],arrows[n],COLORS[k]) for n in items)
        parts.append('</div></section>')
    return "".join(parts) + "</div>"

def draw_html(nums, counts, pools, arrows):
    out = []
    for k in range(5):
        chosen = [n for n in sorted(nums) if pools[n] == k]
        body = " ".join(one_chip(n,counts[n],arrows[n],COLORS[k],True) for n in chosen)
        out.append(f'<div><b style="color:{COLORS[k]}">{NAMES[k]} ({len(chosen)})</b> {body or "—"}</div>')
    return '<div class="balls-line">' + "".join(out) + "</div>"

def backup_text(rows):
    return "\n".join(f'{r["no"]};{datetime.fromisoformat(r["dt"]):%d.%m.%Y %H:%M};'
                     + ",".join(map(str,r["nums"])) for r in rows) + "\n"

def candidate_groups(mode, fixed, quotas):
    if mode == "3 havuz: 3 sıcak / 4 ılık / 3 soğuk":
        seq = sorted(range(1,81), key=lambda n:(fixed[0][n],n))
        groups = [seq[:20],seq[20:60],seq[60:]]
        return groups, [3,4,3], ["Soğuk","Ilık","Sıcak"]
    groups = [[n for n in range(1,81) if fixed[1][n]==i] for i in range(5)]
    return groups, quotas, list(NAMES)

def ticket_set(groups, quotas, arrows, seed, used):
    rnd = random.Random(seed)
    picked = set()
    for pool,k in zip(groups,quotas):
        # No hottest/coldest preference; low-repeat diversity across columns.
        allnums = list(pool)
        rnd.shuffle(allnums)
        rising = [n for n in allnums if arrows[n] == "→"]
        falling = [n for n in allnums if arrows[n] == "←"]
        target_rise = k // 2 + (k % 2 and rnd.randrange(2))
        chosen = sorted(rising, key=lambda n:(used[n],rnd.random()))[:target_rise]
        chosen += sorted(falling, key=lambda n:(used[n],rnd.random()))[:max(0,k-len(chosen))]
        if len(chosen) < k:
            chosen += [n for n in sorted(allnums,key=lambda n:(used[n],rnd.random()))
                       if n not in chosen][:k-len(chosen)]
        picked.update(chosen)
    if len(picked) != 10:
        raise ValueError("Kolon 10 farklı sayı üretmedi; kotaları kontrol et.")
    return sorted(picked)

ENGINE_SCREENS = {
    "V18 · Gelen 20 / kalan 60": ("v18_cift_havuz_app","render_v18"),
    "V35 · 11 çekiliş karakteri": ("v35_11_karakter_app","render_v35"),
    "V39 · Çekiliş öncesi uzmanlar": ("v39_ileriye_donuk_app","render_v39"),
    "V40 · Isı, yön ve bantlar": ("v40_isi_havuzlari_app","render_v40"),
    "V41 · Derin yön ve ters dönüş": ("v41_derin_yon_app","render_v41"),
    "V42 · Değişken beş havuz": ("v42_bes_havuz_kota_app","render_v42"),
    "V44 · Ana beyin / uzman eleme": ("v44_ana_beyin_app","render_v44"),
    "V45 · Sinyal merkezi": ("v45_sinyal_merkezi_app","render_v45"),
    "V50 · Sekizli aile": ("v50_8li_yakinlik_app","render_v50"),
    "V52 · İkili arkadaşlık": ("v52_ayni_cekilis_eslikci_app","render_v52"),
    "V54 · RNG karakter laboratuvarı": ("v54_rng_karakter_app","render_v54"),
    "V55 · Önce karakter sonra sayı": ("v55_karakter_once_app","render_v55"),
}

for key,default in (("v230_source",""),("v230_manual",[]),("v230_tickets",{})):
    if key not in st.session_state:
        st.session_state[key] = default

st.title("🌙 Hızlı On · V230 Gece Merkezi")
st.caption("22:57 havuzu SABİT • Her yeni gerçek 20'li aşağıya eklenir • Hareketli havuz ayrıca gösterilir")
st.sidebar.markdown("### Veri kaynağı")
uploaded = st.sidebar.file_uploader("veri.txt / CSV / ZIP / GZ yükle",
                                     type=["txt","csv","zip","gz"], key="v230_upload")
if uploaded is not None and st.sidebar.button("Yüklenen dosyayı içeri al"):
    try:
        text = ingest_bytes(uploaded.getvalue(), uploaded.name)
        records, issues = parse_text(text)
        if not records:
            st.sidebar.error("Dosyada geçerli çekiliş kaydı bulunamadı.")
        else:
            st.session_state["v230_source"] = text
            st.sidebar.success(f"{len(records)} kayıt içeri alındı.")
            st.rerun()
    except Exception as exc:
        st.sidebar.error(str(exc))
if st.sidebar.button("GitHub veri.txt dosyasını oku"):
    try:
        import requests
        resp = requests.get(RAW_URL,timeout=20)
        resp.raise_for_status()
        parsed,_ = parse_text(resp.text)
        if not parsed:
            st.sidebar.warning("GitHub veri.txt boş veya erişilebilir geçerli kayıt içermiyor. Dosyanı yükle.")
        else:
            st.session_state["v230_source"] = resp.text
            st.sidebar.success(f"{len(parsed)} kayıt alındı.")
            st.rerun()
    except Exception as exc:
        st.sidebar.warning("GitHub veri.txt okunamadı. Dosya yüklemeyi kullan. " + str(exc))

allrows, errors = combine(st.session_state["v230_source"],st.session_state["v230_manual"])
with st.sidebar.expander("Kaynak ve veri denetimi",expanded=False):
    st.write(f"Toplam gerçek kayıt: {len(allrows)}")
    st.write(f"Uyarı sayısı: {len(errors)}")
    if errors: st.code("\n".join(errors[:12]))
if allrows:
    st.sidebar.download_button("💾 Tüm veriyi TXT yedekle", backup_text(allrows),
                               file_name="hizli_on_v230_yedek.txt",mime="text/plain")
st.sidebar.caption("Oturum verileri bulut yeniden başlatılınca kaybolabilir; TXT yedeği indir.")

available = []
for d in sorted({r["day"] for r in allrows},reverse=True):
    dayrows, count = daytime(d, allrows)
    if count == 192:
        available.append(d)

menu = st.sidebar.radio("Bölüm",["🌙 Canlı gece paneli","🎟️ Kupon üretici",
                                  "🧠 Eski analiz motorları","🧪 Ortak yazılım laboratuvarı",
                                  "📊 Veri kontrolü"])
if not available:
    st.info("Başlamak için 192 gündüz çekilişi bulunan veri.txt dosyanı yükle. "
            "07:02–22:57'nin tamamı olmadan 22:57 havuzu oluşturulmaz.")
    st.stop()

chosen_day = st.sidebar.selectbox("Analiz günü (22:57 kapanışı)",available,index=0)
dayrows, _ = daytime(chosen_day, allrows)
fixed = baseline(dayrows)
daycounts, frozen, arrows = fixed
night = night_rows(chosen_day,allrows)
seen = [night[p] for p in sorted(night)]

# Legacy engines take calendar day/position, not shifted operational date.
legacy = [{"no":r["no"], "day":r["day"],"pos":r["pos"],
           "dt":r["dt"],"nums":tuple(r["nums"])} for r in allrows]

if menu == "🌙 Canlı gece paneli":
    st.subheader(f"📌 {chosen_day} · 22:57'de dondurulmuş 80 sayı")
    a,b,c,d = st.columns(4)
    a.metric("Gündüz", "192 / 192")
    b.metric("Sabit havuz", "5 × 16")
    c.metric("Girilen gece sonucu",f"{len(seen)} / 25")
    d.metric("Sıradaki saat", (datetime.combine(date.fromisoformat(chosen_day),time(23,2))+
                 timedelta(minutes=5*next((p for p in range(25) if p not in night),24))
                ).strftime("%H:%M") if len(seen)<25 else "Tamam")
    st.info("Bu üstteki havuz ve frekanslar 22:57'de sabitlenir; "
            "gece sonuçları eklense de burası DEĞİŞMEZ. "
            "(frekans) = 192 gündüz çekilişinde çıkışı, yön = son36 / önceki156 çıkış hızı.")
    st.markdown(pool_html(daycounts,frozen,arrows),unsafe_allow_html=True)
    st.markdown("### ➕ Yeni gerçek 20'liyi ekle")
    missing = [i for i in range(25) if i not in night]
    if missing:
        with st.form("v230_new_result",clear_on_submit=True):
            selected_pos = st.selectbox(
                "Çekiliş saati",missing,
                format_func=lambda p:(datetime.combine(date.fromisoformat(chosen_day),time(23,2))+
                                       timedelta(minutes=5*p)).strftime("%d.%m %H:%M"))
            draw_id = st.text_input("Resmî çekiliş numarası (zorunlu)",
                        placeholder="Örn. 63329")
            newnums = st.text_area("20 gerçek sayı (boşluk, virgül veya tire ile)",height=92,
                    placeholder="07 11 12 15 19 22 24 26 29 38 42 44 49 54 67 69 73 75 76 77")
            save = st.form_submit_button("✅ Bu gerçek 20'liyi kaydet",type="primary")
        if save:
            try:
                if not draw_id.strip().isdigit() or int(draw_id) <= 0:
                    raise ValueError("Resmî çekiliş numarasını pozitif tam sayı olarak gir.")
                vals = numbers(newnums)
                stamp = datetime.combine(date.fromisoformat(chosen_day),time(23,2)) + timedelta(minutes=5*selected_pos)
                ident = int(draw_id)
                new = record(ident,stamp,vals)
                if any(r["dt"]==new["dt"] for r in allrows):
                    raise ValueError("Bu saatte zaten bir çekiliş kayıtlı.")
                if any(r["no"]==ident for r in allrows):
                    raise ValueError("Bu çekiliş numarası zaten kayıtlı.")
                st.session_state["v230_manual"].append(new)
                st.rerun()
            except Exception as exc:
                st.error(f"Kayıt reddedildi: {exc}")
    else:
        st.success("Bu geceye ait 25 çekilişin tamamı mevcut.")

    st.markdown("### 📋 Gerçek 20'liler — sırayla")
    if not seen:
        st.caption("Henüz gece sonucu yok. İlk sonuç 23:02'den başlayacak.")
    # Frozen group is always used in the per-draw roster.
    for p in range(25):
        if p not in night:
            continue
        r = night[p]
        stamp = datetime.fromisoformat(r["dt"]).strftime("%H:%M")
        with st.container(border=True):
            st.markdown(f"**#{r['no']} · {stamp} · 20 gerçek sayı**")
            mix = Counter(frozen[n] for n in r["nums"])
            st.caption("22:57 SABİT havuz dağılımı: " + " · ".join(
                f"{NAMES[k]} {mix[k]}" for k in range(5)))
            st.markdown(draw_html(r["nums"],daycounts,frozen,arrows),unsafe_allow_html=True)
            tickets = st.session_state["v230_tickets"].get(chosen_day,[])
            if tickets:
                matches = [len(set(x["numbers"]) & set(r["nums"])) for x in tickets]
                st.caption("Kaydedilmiş kolonların isabeti (bu 20'lide): " +
                           ", ".join(f"Kolon {i+1}: {m}/10" for i,m in enumerate(matches)))
    st.divider()
    st.subheader("🔄 Gece sonrası HAREKETLİ havuz (ayrı)")
    history = sorted(dayrows + seen,key=lambda r:r["dt"])
    mcounts, mpools, marrows = moving_state(history)
    changes = sum(frozen[n] != mpools[n] for n in range(1,81))
    st.caption("Bu ALT havuz, son 72 çekilişe göre güncellenir. "
               "Üstteki 22:57 sabit havuzuyla aynı ölçüm değildir. "
               "Yeni gecenin her sonucundan sonra yeniden hesaplanır.")
    st.metric("22:57 sabit havuzuna göre farklı katmandaki sayı",changes)
    st.markdown(pool_html(mcounts,mpools,marrows),unsafe_allow_html=True)
    if seen:
        stat=[]
        for p in sorted(night):
            r=night[p]
            counts=Counter(frozen[n] for n in r["nums"])
            stat.append({"Saat":datetime.fromisoformat(r["dt"]).strftime("%H:%M"),
                         **{NAMES[k]:counts[k] for k in range(5)},
                         "Yükselen →":sum(arrows[n]=="→" for n in r["nums"]),
                         "Düşen ←":sum(arrows[n]=="←" for n in r["nums"]),
                         "Yatay =":sum(arrows[n]=="=" for n in r["nums"])})
        st.dataframe(stat,hide_index=True,use_container_width=True)

elif menu == "🎟️ Kupon üretici":
    st.subheader("🎟️ Az kolon · kontrollü karma kupon")
    st.warning("Geçmiş sıcaklık ve yönler gelecekteki çekilişi garanti etmez. "
               "Bu bölüm rastgele çeşitlendirilmiş kupon üretir; üstünlük kanıtı değildir.")
    strategy = st.selectbox("Havuz mimarisi",[
        "5 havuz: 2+2+2+2+2",
        "3 havuz: 3 sıcak / 4 ılık / 3 soğuk",
        "5 havuz: serbest kota"])
    quotas = [2,2,2,2,2]
    if strategy == "5 havuz: serbest kota":
        cols=st.columns(5)
        quotas = [int(cols[i].number_input(NAMES[i],min_value=0,max_value=10,value=2,
                    key=f"quota_{i}")) for i in range(5)]
        st.caption(f"Toplam: {sum(quotas)} / 10")
    count = st.slider("Kolon adedi",1,3,2)
    seed = st.number_input("Tekrarlanabilir seçim tohumu",min_value=1,value=20261025,step=1)
    if st.button("Kolonları oluştur ve dondur",disabled=sum(quotas)!=10,type="primary"):
        groups, q, names = candidate_groups(strategy,fixed,quotas)
        used=Counter()
        generated=[]
        try:
            for i in range(count):
                picks=ticket_set(groups,q,arrows,int(seed)+7919*i,used)
                generated.append({"numbers":picks,"method":strategy,
                                  "snapshot_day":chosen_day,"created_at":
                                  datetime.now(TR_TZ).isoformat(timespec="seconds")})
                used.update(picks)
            st.session_state["v230_tickets"][chosen_day]=generated
            st.success(f"{len(generated)} kolon kaydedildi. Sonuçlar eklenince isabetler gösterilecek.")
        except Exception as exc:
            st.error(str(exc))
    saved=st.session_state["v230_tickets"].get(chosen_day,[])
    for i,t in enumerate(saved,1):
        with st.container(border=True):
            st.markdown(f"**Kolon {i} — {t['method']}**")
            st.code(" ".join(f"{n:02d}" for n in t["numbers"]))
            a=sum(arrows[n]=="→" for n in t["numbers"])
            b=sum(arrows[n]=="←" for n in t["numbers"])
            st.caption(f"→ {a} yükselen · ← {b} düşen · = {10-a-b} yatay")
            if seen:
                results=[(datetime.fromisoformat(r["dt"]).strftime("%H:%M"),
                           len(set(t["numbers"]) & set(r["nums"]))) for r in seen]
                st.caption("Gece en yüksek isabet: "+str(max(x[1] for x in results))+"/10")
                st.dataframe([{"Saat":s,"İsabet":v} for s,v in results],
                             hide_index=True,use_container_width=True,height=250)
    if saved:
        st.download_button("🎟️ Kolon listesini JSON indir",
                data=json.dumps(saved,ensure_ascii=False,indent=2),
                file_name=f"V230_{chosen_day}_kolon.json",mime="application/json")
    st.caption("Seçimler havuz içinde uç sıcaklıklara zorlanmaz; ↑ ve ↓ birlikte tutulmaya çalışılır. "
               "Havuzda yön adedi yetersizse dengeden sapabilir. Çekiliş sonrası kuponu değiştirmek "
               "tarihsel sonucu önceden bilme anlamına gelmez.")

elif menu == "🧠 Eski analiz motorları":
    st.subheader("🧠 Aynı programdaki GitHub analiz motorları")
    st.caption("V10'da bulunan kaynak motorlar burada doğrudan, isteğe bağlı çalışır. "
               "V42'nin havuzları DEĞİŞKEN boyutludur; yeni ana ekranın 16'lık havuzlarıyla karıştırma.")
    chosen_engine = st.selectbox("Çalıştırılacak motor",list(ENGINE_SCREENS))
    module, function = ENGINE_SCREENS[chosen_engine]
    try:
        handler = getattr(importlib.import_module(module),function)
        if function == "render_v18":
            selected = [r for r in allrows if r["day"] == chosen_day]
            handler(selected, chosen_day, False,
                    lambda: datetime.now(TR_TZ).replace(tzinfo=None))
        else:
            handler(legacy)
    except Exception as exc:
        st.error(f"{chosen_engine} yüklenemedi: {exc}")
        st.info("Eski motor dosyalarının ve bağımlılıkların aynı GitHub deposunda bulunması gerekir.")
    st.markdown(f"Eski V10'un bütün diğer sekmeleri: "
                f"https://github.com/{REPO}/blob/main/v10_app.py")
    st.caption("Eski motorun hesaplama sonucunu incelemek için ilgili motoru seçip "
               "kendi çalıştır düğmesine bas. Ana 22:57 tablosu değişmez.")

elif menu == "🧪 Ortak yazılım laboratuvarı":
    from v231_analiz_koprusu import (versions, pairs_numpy, pairs_numba,
        scipy_pool_null, z3_constraint_tickets, xgb_walkforward, checksum)
    st.subheader("🧪 V231 · Python, Z3, XGBoost, NumPy, SciPy, Numba")
    st.caption("Tek veri kaynağı: V230'da yüklediğin GERÇEK sonuçlar. "
               "Bu motorlar otomatik kazanç tahmini değil, araştırma ve karşılaştırma araçlarıdır.")
    installed=versions()
    st.dataframe([{"Bileşen":name,"Sürüm":value or "YÜKLÜ DEĞİL",
                   "Durum":"Hazır" if value else "Kurulum gerekli"}
                  for name,value in installed.items()],
                 hide_index=True,use_container_width=True)
    st.caption("Termux yalnız Android cihazda çalışır, bulut Streamlit'in içinde koşmaz. "
               "Z3 / XGBoost / Numba gibi motorlar burada bulut Python ortamında çalıştırılır.")
    tool=st.selectbox("Çalıştırılacak araç",[
        "Python · Gece ve sabit havuz doğrulaması",
        "Z3 · Havuz/yön kısıtlı 10'lu kolon",
        "XGBoost · Eğitim ve sonradan gelen günlerde kör test",
        "NumPy + Numba · Gerçek ikili eşlikçiler",
        "SciPy · Sabit beş havuzun rastgelelik karşılaştırması"])
    if tool.startswith("Python"):
        st.metric("Kaynak çekilişleri",len(allrows))
        st.metric("Sabit havuz sayısı",len(frozen))
        st.metric("Kayıtlı gerçek gece sonucu",len(seen))
        st.code(checksum(allrows)[:28],language="text")
        st.caption("Kaynak parmak izi; geçmişi değiştirip aynı test gibi göstermeyi önler.")
        st.dataframe([{"Havuz":NAMES[k],"Mevcut sayı":sum(v==k for v in frozen.values()),
                       "Gündüz toplam":sum(daycounts[n] for n in frozen if frozen[n]==k),
                       "→":sum(arrows[n]=="→" for n in frozen if frozen[n]==k),
                       "←":sum(arrows[n]=="←" for n in frozen if frozen[n]==k),
                       "=":sum(arrows[n]=="=" for n in frozen if frozen[n]==k)}
                     for k in range(5)],hide_index=True,use_container_width=True)
    elif tool.startswith("Z3"):
        st.write("**Beş havuzdan 2'şer sayı, toplam 10 benzersiz sayı.** "
                 "En az bir yükselen ve bir düşen sayı koşulu, varsa etkin.")
        seed=st.number_input("Z3 kısıt çözümü tohumu",min_value=0,value=20261029)
        cols=st.slider("Çözülecek kolon",1,3,2)
        if not installed["z3-solver"]:
            st.error("Z3 kurulu değil: requirements.txt içinde z3-solver gerekli.")
        elif st.button("Z3 kısıt sistemini çöz",type="primary"):
            try:
                output=z3_constraint_tickets(frozen,arrows,cols,int(seed))
                for idx,nums in enumerate(output,1):
                    st.code(f"{idx}. " + " ".join(f"{n:02d}" for n in nums))
                st.info("Bu çözüm yalnız belirtilen kısıtları sağlar; "
                        "gelecek gerçek 20'liyi bildiği veya kazanma ihtimalini "
                        "artırdığı anlamına gelmez.")
            except Exception as exc:
                st.error("Z3 hesaplama sorunu: "+str(exc))
    elif tool.startswith("XGBoost"):
        st.warning("Model yalnız önceki çekilişlerden özellik çıkarır. "
                   "Eğitim ve sınav tarihleri ayrılır; aynı sonraki hedefte "
                   "10'lu XGBoost ve rastgele 10'lu karşılaştırılır.")
        max_targets=st.slider("Farklı günlere yayılan hedef örneği",100,600,240,20)
        if not installed["xgboost"]:
            st.error("XGBoost kurulu değil: requirements.txt içine eklenmeli.")
        elif st.button("XGBoost ile kronolojik kör test çalıştır",type="primary"):
            try:
                with st.spinner("Eğitim ve sonraki gün testleri hesaplanıyor"):
                    report=xgb_walkforward(allrows,max_targets=max_targets)
                st.session_state["v231_xgb_saved"]={
                    "hash":checksum(allrows),"limit":max_targets,"report":report}
            except Exception as exc:
                st.error("XGBoost analiz sorunu: "+str(exc))
        saved=st.session_state.get("v231_xgb_saved")
        if saved:
            if saved["hash"]!=checksum(allrows) or saved["limit"]!=max_targets:
                st.warning("Veri veya hedef sayısı değişti. Rapor güncel değil.")
            else:
                x=saved["report"]
                c1,c2,c3=st.columns(3)
                c1.metric("XGBoost 10'lu ortalaması",f'{x["model_mean"]}/10')
                c2.metric("Aynı hedef rastgele ortalaması",f'{x["random_mean"]}/10')
                c3.metric("Adil teorik ortalama","2,50/10")
                st.caption(f'Gerçek eğitim {x["trained_days"]} gün / {x["train_draws"]} çekiliş; '
                           f'test {x["tested_days"]} gün / {x["test_draws"]} çekiliş. '
                           f'Bölme tarihi: {x["split_through_day"]}.')
                st.dataframe(x["details"][:100],use_container_width=True,
                             hide_index=True)
                import csv as _csv
                import io as _io
                stream=_io.StringIO()
                w=_csv.DictWriter(stream,fieldnames=list(x["details"][0]),delimiter=";")
                w.writeheader()
                w.writerows(x["details"])
                st.download_button("Testin tamamını CSV indir",stream.getvalue(),
                    file_name=f"V231_XGB_{chosen_day}.csv",mime="text/csv")
                st.caption("Bu araştırma sonucu seçim kriterini sonradan değiştirmek "
                           "için kullanılırsa yeni bağımsız günlerle tekrar sınanmalı.")
    elif tool.startswith("NumPy"):
        if not installed["numpy"]:
            st.error("NumPy yüklü değil.")
        elif st.button("Son 217 gerçek çekilişte ikili sayımını hesapla"):
            try:
                a=pairs_numpy(allrows)
                a.sort(key=lambda v:(-v["birlikte"],v["sayı_a"],v["sayı_b"]))
                st.session_state["v231_pairs"]={"hash":checksum(allrows),"table":a}
                if installed["numba"]:
                    b=pairs_numba(allrows)
                    t={(r["sayı_a"],r["sayı_b"]):r["birlikte"] for r in b}
                    assert all(r["birlikte"]==t[r["sayı_a"],r["sayı_b"]] for r in a)
                    st.success("NumPy ve Numba aynı 3.160 ikili için TAM eşleşti.")
                else:
                    st.info("Numba bulunamadı; eşlikçiler NumPy ile hesaplandı.")
            except Exception as exc:
                st.error("İkili analizi hesaplanamadı: "+str(exc))
        saved=st.session_state.get("v231_pairs")
        if saved and saved["hash"]==checksum(allrows):
            st.dataframe(saved["table"][:60],hide_index=True,use_container_width=True)
            st.caption("İkili buluşma geçmişin betimlenmesidir; ileriye dönük kanıt değildir.")
    else:
        if not installed["scipy"]:
            st.error("SciPy kurulu değil.")
        elif not seen:
            st.info("Bu geceye ait en az bir gerçek 20'li yüklenince karşılaştırma çalışır.")
        else:
            table=scipy_pool_null(seen,frozen)
            st.dataframe(table,hide_index=True,use_container_width=True)
            st.caption("Her havuzda 16 sayı var, adil beklenti sayı başına %25. "
                       "Ham ve beş karşılaştırmaya göre düzeltilmiş p-değerleri "
                       "yalnız açıklayıcıdır. Bir çekilişteki seçimler birbiriyle "
                       "bağımlı olduğundan basit binom testi yaklaşık bir denetimdir.")

else:
    st.subheader("📊 Kayıt bütünlüğü ve dışa aktarma")
    st.write(f"Toplam kayıt: **{len(allrows)}** · Tam gündüz: **{len(available)}**")
    st.dataframe([{"Gün":d,"Gündüz çekilişi":daytime(d,allrows)[1],
                   "Gece çekilişi":len(night_rows(d,allrows))}
                  for d in available],hide_index=True,use_container_width=True)
    if errors:
        st.error(f"{len(errors)} veri sorunu bulundu.")
        st.code("\n".join(errors[:60]))
    else:
        st.success("Yüklenen satırlarda tespit edilmiş bir çakışma yok.")
    st.download_button("⬇️ Gündüz + gece kayıtlarının tamamını TXT indir",
                       backup_text(allrows),file_name="HIZLI_ON_V230_VERI_TAM.txt",
                       mime="text/plain")
    st.info("GitHub veri.txt otomatik GÜNCELLENMEZ. Kaybetmemek için TXT yedeğini indir "
            "veya V10'un yetkili kayıt iş akışını kullan. Anlık 22:57 sınıflaması için "
            "192 gündüz sonucu gerekir.")

st.caption("V230 · 80 sayı / 20 gerçek sayı · Yerel Türkiye saati · Sınıflandırma betimseldir; "
           "rastgele çekilişlere karşı kanıtlanmış tahmin avantajı yoktur.")
