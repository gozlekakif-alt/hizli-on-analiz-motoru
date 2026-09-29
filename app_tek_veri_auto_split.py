# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile, hashlib, math, random
from collections import Counter, defaultdict
from dataclasses import dataclass

st.set_page_config(page_title="Hızlı On Birleşme Kupon Motoru", layout="wide")
st.title("🎯 Hızlı On — 0/3–3/3 Geçiş / Son-6 Birleşme Motoru")
st.caption("Tek veri.txt: 25.08–07.09 öğrenme • 08.09 ve sonrası otomatik kör-test/güncel veri")

FIRST6 = ["02","07","12","17","22","27"]
TARGETS = ["32","37","42","47","52","57"]
ALL_MINS = FIRST6 + TARGETS
TRAIN_START = pd.Timestamp("2026-08-25")
TRAIN_END   = pd.Timestamp("2026-09-07 23:59:59")

# ---------------- PARSER / MODEL ----------------

def parse_draw_text(path_or_text, is_text=False):
    if is_text:
        txt = str(path_or_text)
    else:
        txt = Path(path_or_text).read_text(encoding="utf-8-sig", errors="replace")

    rows = []
    for line in txt.splitlines():
        p = line.strip().split(";")
        if len(p) != 3:
            continue
        try:
            draw_id = int(p[0].strip())
            dt = pd.to_datetime(p[1].strip(), dayfirst=True)
            nums = tuple(sorted({int(x.strip()) for x in p[2].split(",") if x.strip()}))
        except Exception:
            continue
        if len(nums) == 20 and all(1 <= x <= 80 for x in nums):
            rows.append((draw_id, dt, nums))

    if not rows:
        raise ValueError("Geçerli çekiliş satırı bulunamadı. Format: no;tarih saat;20 sayı")

    df = pd.DataFrame(rows, columns=["draw_id","time","numbers"])
    return df.sort_values(["time","draw_id"]).drop_duplicates("draw_id").reset_index(drop=True)

def complete_hour_blocks(df):
    tmp = defaultdict(dict)
    for row in df.itertuples(index=False):
        minute = row.time.strftime("%M")
        if minute not in ALL_MINS:
            continue
        key = (row.time.strftime("%d.%m.%Y"), row.time.strftime("%H"))
        tmp[key][minute] = (int(row.draw_id), set(row.numbers))
    return {k:v for k,v in tmp.items() if all(m in v for m in ALL_MINS)}

def partial_hour_blocks(df):
    """Tam olması gerekmez; canlı saati de taşır."""
    tmp = defaultdict(dict)
    for row in df.itertuples(index=False):
        minute = row.time.strftime("%M")
        if minute not in ALL_MINS:
            continue
        key = (row.time.strftime("%d.%m.%Y"), row.time.strftime("%H"))
        tmp[key][minute] = (int(row.draw_id), set(row.numbers))
    return dict(tmp)

def classify_families(hd):
    if not all(m in hd for m in FIRST6):
        raise ValueError("İlk 6 çekiliş (:02,:07,:12,:17,:22,:27) tamamlanmadan aile sınıflaması yapılamaz.")
    s = [hd[m][1] for m in FIRST6]
    fam = {}
    for n in range(1,81):
        a = int(n in s[0]) + int(n in s[1]) + int(n in s[2])
        b = int(n in s[3]) + int(n in s[4]) + int(n in s[5])
        fam[n] = f"{a}/3→{b}/3"
    return fam

def period_of(date_str):
    d = pd.to_datetime(date_str, dayfirst=True)
    if d <= pd.Timestamp("2026-08-28 23:59:59"):
        return "D"
    if d <= pd.Timestamp("2026-08-31 23:59:59"):
        return "V1"
    return "R"

def wilson_lower(h, n, z):
    if n <= 0:
        return 0.0
    p = h / n
    return (p + z*z/(2*n) - z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)

@dataclass(frozen=True)
class Branch:
    minute: str
    family: str
    prior: str
    n: int
    hits: int
    rate: float
    d_rate: float
    v1_rate: float
    r_rate: float
    lb95: float
    lb80: float
    tier: str

@st.cache_resource(show_spinner=False)
def build_model_fast(train_path):
    raw = parse_draw_text(train_path)
    train = raw[(raw.time >= TRAIN_START) & (raw.time <= TRAIN_END)].copy()
    if train.empty:
        raise ValueError("25.08.2026–07.09.2026 eğitim aralığı veri.txt içinde yok.")

    blocks = complete_hour_blocks(train)
    stats = defaultdict(lambda: [0,0,0,0,0,0,0,0])

    for (date,hour), hd in blocks.items():
        fam = classify_families(hd)
        prior = {n:"" for n in range(1,81)}
        per = period_of(date)

        for minute in TARGETS:
            actual = hd[minute][1]
            for n in range(1,81):
                key = (minute, fam[n], prior[n])
                s = stats[key]
                s[0] += 1
                hit = 1 if n in actual else 0
                s[1] += hit
                if per == "D":
                    s[2] += 1; s[3] += hit
                elif per == "V1":
                    s[4] += 1; s[5] += hit
                else:
                    s[6] += 1; s[7] += hit

            for n in range(1,81):
                prior[n] += "1" if n in actual else "0"

    model = {}
    rows = []

    for (minute,family,prior), s in stats.items():
        n,hits,dn,dh,vn,vh,rn,rh = s
        rate = hits/n
        dr = dh/dn if dn else 0.25
        vr = vh/vn if vn else 0.25
        rr = rh/rn if rn else 0.25
        lb95 = wilson_lower(hits,n,1.96)
        lb80 = wilson_lower(hits,n,1.282)

        tier = "OFF"
        if n >= 30 and lb95 > 0.25 and min(dr,vr,rr) >= 0.25:
            tier = "CORE"
        elif n >= 40 and lb80 > 0.25 and min(dr,vr,rr) >= 0.24:
            tier = "SUPPORT"

        b = Branch(minute,family,prior,n,hits,rate,dr,vr,rr,lb95,lb80,tier)
        model[(minute,family,prior)] = b

        if tier != "OFF":
            rows.append({
                "Hedef":f":{minute}",
                "Aile":family,
                "Canlı yol":prior or "∅",
                "Tier":tier,
                "n":n,
                "Hit":hits,
                "Oran %":round(100*rate,2),
                "D %":round(100*dr,2),
                "V1 %":round(100*vr,2),
                "R %":round(100*rr,2)
            })

    return raw, train, blocks, model, pd.DataFrame(rows)

def _seed(*parts):
    raw="|".join(map(str,parts))
    return int(hashlib.sha256(raw.encode()).hexdigest()[:16],16)

def generate_for_target(hd, date, hour, target_minute, model, variants=5):
    """
    Yalnız hedef ÖNCESİ bilinen çekilişleri kullanarak kolon üretir.
    target_minute sonucu hd içinde olsa bile seçime dahil edilmez.
    """
    fam = classify_families(hd)
    target_idx = TARGETS.index(target_minute)
    prior_minutes = TARGETS[:target_idx]

    # Önceki son-6 çekilişleri eksiksiz olmalı.
    if not all(m in hd for m in prior_minutes):
        return []

    prior = {}
    for n in range(1,81):
        prior[n] = "".join("1" if n in hd[m][1] else "0" for m in prior_minutes)

    groups = defaultdict(list)
    binfo = {}
    for n in range(1,81):
        b = model.get((target_minute, fam[n], prior[n]))
        if b and b.tier != "OFF":
            g = (fam[n], prior[n])
            groups[g].append(n)
            binfo[g] = b

    def rank(g):
        b = binfo[g]
        return (
            2 if b.tier == "CORE" else 1,
            b.lb95 if b.tier == "CORE" else b.lb80,
            b.rate,
            b.n
        )

    ordered = sorted(groups, key=rank, reverse=True)
    cand = sum(len(groups[g]) for g in ordered)
    if cand < 4:
        return []

    out = []
    for v in range(1, variants+1):
        rng = random.Random(_seed("LIVE",date,hour,target_minute,v))
        bags = {g:list(groups[g]) for g in ordered}
        for g in bags:
            rng.shuffle(bags[g])

        chosen=[]; gc=Counter(); fc=Counter()
        while len(chosen) < 6:
            added=False
            for g in ordered:
                family,_=g
                if gc[g] >= 2 or fc[family] >= 3 or not bags[g]:
                    continue
                chosen.append(bags[g].pop())
                gc[g]+=1
                fc[family]+=1
                added=True
                if len(chosen) == 6:
                    break
            if not added:
                break

        if len(chosen) >= 4:
            out.append({
                "Hedef": f"{hour}:{target_minute}",
                "Varyant": v,
                "Boyut": len(chosen),
                "Aday": cand,
                "Kolon": sorted(chosen)
            })
    return out

def next_ready_target(hd):
    """
    İlk 6 tamamlandıktan sonra sıradaki eksik hedefi bulur.
    :32 için ilk6 yeterli.
    :37 için :32 sonucu gerekli.
    ...
    """
    if not all(m in hd for m in FIRST6):
        return None, "İlk 6 henüz tamamlanmadı."

    for i, m in enumerate(TARGETS):
        if m in hd:
            continue
        prev = TARGETS[:i]
        if all(x in hd for x in prev):
            return m, None

    if all(m in hd for m in TARGETS):
        return None, "Bu saat tamamlanmış."
    return None, "Sıradaki hedef için önceki hedef sonucu eksik."

def save_upload(upload):
    f=tempfile.NamedTemporaryFile(delete=False,suffix=".txt")
    f.write(upload.getbuffer()); f.close()
    return f.name

# ---------------- UI ----------------

repo = Path("veri.txt")
if repo.exists():
    train_path = str(repo)
    st.sidebar.success("✅ veri.txt bulundu")
else:
    up = st.sidebar.file_uploader("14 günlük veri.txt yükle",type=["txt"],key="train")
    train_path = save_upload(up) if up else None

if not train_path:
    st.error("Repo kökünde veri.txt yok.")
    st.stop()

with st.spinner("14 günlük birleşme modeli hazırlanıyor..."):
    raw,train,train_blocks,model,branches = build_model_fast(train_path)

c1,c2,c3,c4 = st.columns(4)
c1.metric("Ham çekiliş",len(raw))
c2.metric("Eğitim çekiliş",len(train))
c3.metric("Tam saat",len(train_blocks))
c4.metric("Aktif dal",len(branches))

post_train = raw[raw.time > TRAIN_END].copy()
if not post_train.empty:
    st.success(
        f"📦 Tek veri.txt algılandı: eğitim 25.08–07.09 sabit; "
        f"08.09 sonrası {post_train['time'].dt.strftime('%d.%m.%Y').nunique()} gün "
        f"({len(post_train)} çekiliş) kör-test/güncel havuzunda."
    )

tabs = st.tabs(["⚡ Güncel Kupon","🧬 Dallar","🧪 Kör Test","📘 Mantık"])

with tabs[0]:
    st.subheader("Yeni güncel çekilişleri yükle → sıradaki kuponu üret")
    st.info("İlk 6 (:02–:27) tamamlanınca :32 kuponu çıkar. Sonra her yeni sonuç geldikçe sıradaki hedef (:37→:42→:47→:52→:57) otomatik hazırlanır.")

    live_up = st.file_uploader("Güncel çekiliş TXT yükle", type=["txt"], key="livefile")
    live_text = st.text_area(
        "veya çekilişleri buraya yapıştır",
        height=160,
        placeholder="54710;10.09.2026 08:02;12,17,21,...\n54711;10.09.2026 08:07;1,2,11,..."
    )

    live_df = None
    try:
        if live_up is not None:
            live_df = parse_draw_text(save_upload(live_up))
        elif live_text.strip():
            live_df = parse_draw_text(live_text, is_text=True)
    except Exception as e:
        st.error(str(e))

    if live_df is not None:
        pblocks = partial_hour_blocks(live_df)
        if not pblocks:
            st.warning("Uygun saat bloğu bulunamadı.")
        else:
            # En son tarih/saat bloğunu otomatik seç.
            latest_key = sorted(
                pblocks.keys(),
                key=lambda k: pd.to_datetime(f"{k[0]} {k[1]}:00", dayfirst=True)
            )[-1]
            date,hour = latest_key
            hd = pblocks[latest_key]

            st.write(f"**Algılanan saat:** {date} {hour}:00")
            st.write("**Yüklenen dakikalar:**", ", ".join(f":{m}" for m in sorted(hd.keys(), key=int)))

            target, msg = next_ready_target(hd)
            if target is None:
                st.warning(msg)
            else:
                st.success(f"🎯 Sıradaki hedef: **{hour}:{target}**")
                generated = generate_for_target(hd,date,hour,target,model,variants=5)

                if not generated:
                    st.warning("Bu hedef için yeterli CORE/SUPPORT sinyali yok → ABSTAIN.")
                else:
                    q = pd.DataFrame([{
                        "Hedef":x["Hedef"],
                        "Varyant":x["Varyant"],
                        "Boyut":x["Boyut"],
                        "Aday":x["Aday"],
                        "Kolon":" - ".join(map(str,x["Kolon"]))
                    } for x in generated])
                    st.dataframe(q,use_container_width=True,hide_index=True)
                    st.download_button(
                        "Güncel kuponları CSV indir",
                        q.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"GUNCEL_KUPON_{date.replace('.','_')}_{hour}_{target}.csv",
                        mime="text/csv"
                    )

with tabs[1]:
    st.subheader("14 günden öğrenilen birleşme dalları")
    st.dataframe(
        branches.sort_values(["Tier","Oran %"],ascending=[True,False]),
        use_container_width=True,hide_index=True
    )


with tabs[2]:
    st.subheader("🧪 Kör Test — günleri topluca yükle")
    st.warning(
        "Kural kilitli: CORE/SUPPORT eşikleri, dal sıralaması, varyant sayısı ve seçim mantığı "
        "yüklenen test sonuçlarına göre değişmez. Hedef sonucu yalnız isabeti ölçmek için kullanılır."
    )

    auto_blind = raw[raw.time > TRAIN_END].copy()

    blind_ups = st.file_uploader(
        "İstersen ek kör-test günleri de yükle",
        type=["txt"],
        accept_multiple_files=True,
        key="blind_bulk",
        help="veri.txt içindeki 08.09 ve sonrası zaten otomatik alınır. Buradan ek günler ekleyebilirsin."
    )

    frames = []
    if not auto_blind.empty:
        frames.append(auto_blind)
        st.success(
            f"✅ veri.txt içinden otomatik kör-test: "
            f"{auto_blind['time'].dt.strftime('%d.%m.%Y').nunique()} gün / {len(auto_blind)} çekiliş"
        )

    if blind_ups:
        for up in blind_ups:
            frames.append(parse_draw_text(save_upload(up)))

    if frames:
        try:
            bdf = pd.concat(frames, ignore_index=True)
            bdf = (
                bdf.sort_values(["time","draw_id"])
                .drop_duplicates("draw_id")
                .reset_index(drop=True)
            )
            bdf = bdf[bdf.time > TRAIN_END].reset_index(drop=True)

            all_blocks = complete_hour_blocks(bdf)

            if not all_blocks:
                st.error("Yüklenen dosyalarda tam :02–:57 saat bloğu bulunamadı.")
            else:
                rows = []

                # Dondurulmuş motorla, hedef sonucu görmeden kupon üret;
                # gerçek sonuç yalnız üretim SONRASI skorlama için kullanılır.
                for (date,hour), hd in sorted(all_blocks.items()):
                    for target in TARGETS:
                        arr = generate_for_target(
                            hd, date, hour, target, model, variants=5
                        )
                        actual = hd[target][1]

                        for x in arr:
                            hitnums = sorted(set(x["Kolon"]) & actual)
                            rows.append({
                                "Tarih": date,
                                "Saat": x["Hedef"],
                                "HedefDakika": target,
                                "Varyant": x["Varyant"],
                                "Boyut": x["Boyut"],
                                "Aday": x["Aday"],
                                "Kolon": "-".join(map(str, x["Kolon"])),
                                "İsabet": len(hitnums),
                                "Vuranlar": "-".join(map(str, hitnums)),
                            })

                rep = pd.DataFrame(rows)

                if rep.empty:
                    st.warning("Dondurulmuş motor bu günlerde hiç kupon üretmedi (ABSTAIN).")
                else:
                    gun_say = bdf["time"].dt.strftime("%d.%m.%Y").nunique()
                    tam_saat = len(all_blocks)
                    total = len(rep)
                    hit3 = int((rep["İsabet"] >= 3).sum())
                    hit4 = int((rep["İsabet"] >= 4).sum())
                    hit5 = int((rep["İsabet"] >= 5).sum())
                    hit6 = int((rep["İsabet"] >= 6).sum())

                    c1,c2,c3,c4,c5,c6 = st.columns(6)
                    c1.metric("Gün", gun_say)
                    c2.metric("Tam saat", tam_saat)
                    c3.metric("Toplam kolon", total)
                    c4.metric("3+", hit3)
                    c5.metric("4+", hit4)
                    c6.metric("5+/6+", f"{hit5} / {hit6}")

                    st.markdown("### Tam isabet dağılımı")
                    dist = rep["İsabet"].value_counts().sort_index()
                    distdf = pd.DataFrame({
                        "İsabet": [f"{i}/6" for i in range(7)],
                        "Kolon": [int(dist.get(i,0)) for i in range(7)],
                        "Oran %": [round(100*int(dist.get(i,0))/total,2) for i in range(7)]
                    })
                    st.dataframe(distdf, use_container_width=True, hide_index=True)

                    st.markdown("### Gün gün kör test")
                    day_summary = (
                        rep.assign(
                            is3=(rep["İsabet"]>=3).astype(int),
                            is4=(rep["İsabet"]>=4).astype(int),
                            is5=(rep["İsabet"]>=5).astype(int),
                            is6=(rep["İsabet"]>=6).astype(int),
                        )
                        .groupby("Tarih", as_index=False)
                        .agg(
                            Kolon=("İsabet","size"),
                            Ortalama=("İsabet","mean"),
                            Hit3plus=("is3","sum"),
                            Hit4plus=("is4","sum"),
                            Hit5plus=("is5","sum"),
                            Hit6=("is6","sum"),
                            Maks=("İsabet","max"),
                        )
                    )
                    day_summary["Ortalama"] = day_summary["Ortalama"].round(3)
                    st.dataframe(day_summary, use_container_width=True, hide_index=True)

                    st.markdown("### Dakika bazında")
                    minute_summary = (
                        rep.assign(
                            is3=(rep["İsabet"]>=3).astype(int),
                            is4=(rep["İsabet"]>=4).astype(int),
                            is5=(rep["İsabet"]>=5).astype(int),
                        )
                        .groupby("HedefDakika", as_index=False)
                        .agg(
                            Kolon=("İsabet","size"),
                            Ortalama=("İsabet","mean"),
                            Hit3plus=("is3","sum"),
                            Hit4plus=("is4","sum"),
                            Hit5plus=("is5","sum"),
                            Maks=("İsabet","max"),
                        )
                    )
                    minute_summary["Ortalama"] = minute_summary["Ortalama"].round(3)
                    st.dataframe(minute_summary, use_container_width=True, hide_index=True)

                    st.markdown("### 4+ kolonlar")
                    high = rep[rep["İsabet"]>=4].sort_values(
                        ["İsabet","Tarih","Saat"],
                        ascending=[False,True,True]
                    )
                    if high.empty:
                        st.info("Bu kör testte 4+ kolon çıkmadı.")
                    else:
                        st.dataframe(high, use_container_width=True, hide_index=True)

                    st.markdown("### Tüm kör test kolonları")
                    st.dataframe(rep, use_container_width=True, hide_index=True)

                    st.download_button(
                        "Kör test tam raporunu indir",
                        rep.to_csv(index=False).encode("utf-8-sig"),
                        file_name="KOR_TEST_BIRLESME_MOTORU.csv",
                        mime="text/csv"
                    )
        except Exception as e:
            st.exception(e)

with tabs[3]:
    st.markdown("""
### Canlı çalışma şekli

- `veri.txt` yalnız **14 günlük öğrenme tabanı**dır.
- Yeni günün çekilişlerini **Güncel Kupon** sekmesinden ayrıca yüklersin.
- İlk 6 çekiliş tamamlanınca motor `:32` için kupon üretir.
- `:32` sonucu eklenince `:37` için,
- `:37` sonucu eklenince `:42` için,
- sonra sırasıyla `:47`, `:52`, `:57` için kupon üretir.
- Hedef sonucu, o hedef kuponunu seçerken kullanılmaz.
- Yeni sonucu dosyaya ekleyip tekrar yüklemen yeterlidir.

### Tek `veri.txt` kullanımı
- `veri.txt` içinde 25.08.2026–11.09.2026 gibi daha uzun bir aralık olabilir.
- **25.08–07.09** yalnız öğrenme/eğitim için kullanılır.
- **08.09 ve sonrası** otomatik olarak eğitimden ayrılır ve kör-test/güncel havuzuna alınır.
- Böylece sonraki günler modeli geriye dönük değiştirmez.

### Kör test
- Motor eşikleri test günleri yüklenmeden önce kilitlidir.
- Test günlerini topluca yükleyebilirsin.
- Kupon hedef sonucu görülmeden üretilir.
- Gerçek hedef sonucu yalnız kupon üretildikten sonra skorlama için açılır.
- Test sırasında eşik veya seçim kuralı değiştirilmez.
""")
