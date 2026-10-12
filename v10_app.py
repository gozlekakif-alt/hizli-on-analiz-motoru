# -*- coding: utf-8 -*-
"""Hizli On V10 — canlı aile / ritim / deneysel kupon.
V9 app.py ve veri.txt dosyalarini degistirmez.
Python 3.10+; streamlit, requests.
"""
import base64
import hmac
import csv
import io
import json
import re
from collections import defaultdict, Counter
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests
import streamlit as st

REPO = "gozlekakif-alt/hizli-on-analiz-motoru"
RAW = "https://raw.githubusercontent.com/" + REPO + "/main/"
STATE_PATH = "v10_canli_kayit.json"
TZ = ZoneInfo("Europe/Istanbul")

def now_tr():
    return datetime.now(TZ).replace(tzinfo=None)

def pos_of(dt):
    m = dt.hour * 60 + dt.minute
    if 2 <= m <= 62 and (m - 2) % 5 == 0:
        return 1 + (m - 2)//5
    if 422 <= m <= 1437 and (m - 422) % 5 == 0:
        return 14 + (m - 422)//5
    return None

def moment(day, pos):
    if not 1 <= pos <= 217:
        raise ValueError("Hedef cekilis sirasi 1-217 olmali.")
    m = 2 + 5*(pos - 1) if pos <= 13 else 422 + 5*(pos - 14)
    return datetime.combine(date.fromisoformat(day), time()) + timedelta(minutes=m)

def normalize_numbers(values):
    arr = [int(x) for x in values]
    if len(arr) != 20 or len(set(arr)) != 20 or any(n < 1 or n > 80 for n in arr):
        raise ValueError("1-80 arasinda 20 benzersiz sayi gerekli.")
    return sorted(arr)

def make_draw(num, dt, nums):
    if not isinstance(dt, datetime):
        dt = datetime.fromisoformat(dt)
    pos = pos_of(dt)
    if pos is None:
        raise ValueError("Takvim disi saat. 00:02-01:02 veya 07:02-23:57, 5 dk.")
    return {"no":int(num), "dt":dt.isoformat(timespec="minutes"),
            "day":dt.date().isoformat(), "pos":pos, "nums":normalize_numbers(nums)}

def parse_draw_line(line):
    p = line.strip().split(";")
    if len(p) != 3 or not p[0].strip().isdigit():
        return None
    dt = datetime.strptime(p[1].strip(), "%d.%m.%Y %H:%M")
    return make_draw(p[0], dt, p[2].split(","))


def parse_pasted_draws(raw):
    """Read official pasted result blocks and semicolon data lines."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    results, problems = [], []
    for line in text.splitlines():
        if re.match(r"^\s*\d+\s*;", line):
            try:
                d = parse_draw_line(line)
                if d:
                    results.append(d)
            except (ValueError, TypeError) as exc:
                problems.append(str(exc))
    pattern = re.compile(r"(?im)^\s*#*\s*Çekiliş\s*no\s*:\s*#*\s*(\d{4,8})\s*$")
    found = list(pattern.finditer(text))
    for i, match in enumerate(found):
        block = text[match.end():found[i + 1].start() if i + 1 < len(found) else len(text)]
        stamp = re.search(r"(?<!\d)(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}:\d{2})\b", block)
        if not stamp:
            problems.append("#" + match.group(1) + ": tarih/saat bulunamadı")
            continue
        rest = block[stamp.end():]
        rest = re.split(r"(?im)^\s*(?:\[\s*)?Detaylar\b|^\s*https?://", rest, maxsplit=1)[0]
        nums = []
        for line in rest.splitlines():
            v = line.strip()
            if re.fullmatch(r"\d{1,2}(?:\s*[,;\s]\s*\d{1,2})*", v):
                nums.extend(int(x) for x in re.findall(r"\d{1,2}", v))
        try:
            dt = datetime.strptime(stamp.group(1) + " " + stamp.group(2), "%d.%m.%Y %H:%M")
            results.append(make_draw(match.group(1), dt, nums))
        except (ValueError, TypeError) as exc:
            problems.append("#" + match.group(1) + ": " + str(exc))
    if not results and not problems:
        problems.append("Çekiliş başlığı bulunamadı: 'Çekiliş no:61629' veya noktalı veri satırı bekleniyor.")
    return results, problems

def parse_history(raw):
    seen_no, seen_time, draws, errors = set(), set(), [], 0
    for line in raw.splitlines():
        if not re.match(r"^\s*\d+\s*;", line):
            continue
        try:
            d = parse_draw_line(line)
            if not d or d["no"] in seen_no or d["dt"] in seen_time:
                raise ValueError("Mukerrer kayit")
            seen_no.add(d["no"])
            seen_time.add(d["dt"])
            draws.append(d)
        except (ValueError, TypeError):
            errors += 1
    draws.sort(key=lambda d:d["dt"])
    return draws, errors

def load_family_csv(content):
    records = {}
    for row in csv.DictReader(io.StringIO(content), delimiter=";"):
        label = row.get("Aile", "").strip()
        try:
            nums = tuple(int(x) for x in label.split("-"))
            k = int(row.get("Boyut", 0))
            if not (5 <= k <= 10 and len(nums) == k and
                    len(set(nums)) == k and all(1 <= x <= 80 for x in nums)):
                continue
            records[label] = {"nums":nums,"mask":sum(1 << (x-1) for x in nums),
                              "k":k, "day_count":int(row.get("Aktif_Gun", 0)),
                              "source":row.get("Kaynak","V9")}
        except (ValueError, TypeError):
            pass
    return records

@st.cache_data(ttl=300, show_spinner=False)
def github_text(path):
    res = requests.get(RAW+path, timeout=45)
    res.raise_for_status()
    return res.content.decode("utf-8-sig")

@st.cache_data(ttl=600, show_spinner=False)
def train_profiles(history_json, labels_json):
    """Yalniz HEDEF GUNDEN ONCEKI cekilislerden model olusturulur."""
    past = json.loads(history_json)
    labels = json.loads(labels_json)
    bitsets = [0] * 80
    for idx,d in enumerate(past):
        for n in d["nums"]:
            bitsets[n-1] |= 1 << idx
    profiles = {}
    for label in labels:
        try:
            ns = [int(x) for x in label.split("-")]
            indices = bitsets[ns[0]-1]
            for n in ns[1:]:
                indices &= bitsets[n-1]
            byday = defaultdict(list)
            while indices:
                bit = indices & -indices
                i = bit.bit_length() - 1
                d = past[i]
                byday[d["day"]].append(d["pos"])
                indices ^= bit
            pair_days, first_days, triple_days, quad_days = defaultdict(set),defaultdict(set),defaultdict(set),defaultdict(set)
            for day, ps in byday.items():
                ps.sort()
                if len(ps) >= 2:
                    first_days[ps[1]-ps[0]].add(day)
                for i in range(len(ps)):
                    for j in range(i+1,len(ps)):
                        pair_days[ps[j]-ps[i]].add(day)
                for i in range(len(ps)-2):
                    triple_days[(ps[i+1]-ps[i],ps[i+2]-ps[i+1])].add(day)
                for i in range(len(ps)-3):
                    quad_days[tuple(ps[i+t+1]-ps[i+t] for t in range(3))].add(day)
            dates = sorted(byday)
            profiles[label] = {
                "days":dates,
                "total_hits":sum(map(len,byday.values())),
                "pair":{gap:len(ds) for gap,ds in pair_days.items() if len(ds)>=2},
                "first":{gap:len(ds) for gap,ds in first_days.items() if len(ds)>=2},
                "triple":{pat:len(ds) for pat,ds in triple_days.items() if len(ds)>=2},
                "quad":{pat:len(ds) for pat,ds in quad_days.items() if len(ds)>=2},
            }
        except (ValueError, IndexError):
            continue
    return profiles

def all_draws(history, live):
    by_no = {d["no"]:d for d in history}
    for d in live:
        by_no[d["no"]] = d
    output = sorted(by_no.values(),key=lambda d:d["dt"])
    # Ayni takvim yuvasinda farkli numara olmaz.
    return output

def active_signals(draws, families, profiles, target_day, current):
    todays = [d for d in draws if d["day"]==target_day and
              datetime.fromisoformat(d["dt"]) <= current]
    actual_pos = {d["pos"] for d in draws if d["day"]==target_day}
    dayhits = defaultdict(list)
    masks = [(d, sum(1 << (x-1) for x in d["nums"])) for d in todays]
    for d, mask in masks:
        for label, f in families.items():
            if mask & f["mask"] == f["mask"]:
                dayhits[label].append(d)
    found=[]
    for label, recs in dayhits.items():
        p = profiles.get(label, {})
        ps = sorted(d["pos"] for d in recs)
        n = len(ps)
        if n > 3:
            continue
        supported = p.get("first", {}) if n==1 else p.get("pair", {})
        for gap, count in supported.items():
            gap=int(gap)
            target=ps[-1]+gap
            if target>217 or target in actual_pos or count<2:
                continue
            t=moment(target_day,target)
            if t <= current:
                continue
            # 3. ve 4. hedef: onceki aralikla ayni ritme dayanan
            # bir varsayim. Ayrica 3lu/4lu tekrari varsa bunu belirt.
            if n>=2 and ps[-1]-ps[-2]!=gap:
                continue
            confirmed = False
            if n==2:
                confirmed = p.get("triple",{}).get((gap,gap),0)>=2
            elif n==3:
                confirmed = p.get("quad",{}).get((gap,gap,gap),0)>=2
            kind = ("Tekrarli ilk ikili aralik" if n==1
                    else "Uc/dortlu dogrulanmis ritim" if confirmed
                    else "Deneysel ritim uzatmasi")
            found.append({"label":label,"size":families[label]["k"],"support":count,
                          "kind":kind,"level":n+1,"gap":gap,"pos":target,
                          "day":target_day,"time":t.strftime("%H:%M"),
                          "trigger_no":recs[-1]["no"],
                          "trigger_pos":ps[-1],"moment":t.isoformat(timespec="minutes")})
    found.sort(key=lambda x:(x["pos"],-x["size"],-x["support"],x["label"]))
    return found, dayhits

def daily_chains(profiles, families, target_day):
    today=date.fromisoformat(target_day)
    result=[]
    for label,p in profiles.items():
        if families.get(label,{}).get("k")!=10:
            continue
        ds=set(date.fromisoformat(d) for d in p["days"])
        if len(ds)<2:
            continue
        for g in (2,5,7,14):
            for last in ds:
                if last - timedelta(days=g) not in ds:
                    continue
                target=last+timedelta(days=g)
                if target < today or target> today+timedelta(days=14):
                    continue
                chain=2
                back=last-timedelta(days=g)
                while back-timedelta(days=g) in ds:
                    back-=timedelta(days=g)
                    chain+=1
                result.append({"Aile":label,"Ritim":f"+{g} gun",
                               "Ardisik gun":chain,"Son tarih":str(last),
                               "Hedef gun":str(target),"Hedef saat":"Bilinmiyor"})
    result.sort(key=lambda d:(d["Hedef_gun"] if "Hedef_gun" in d else d["Hedef gun"],-d["Ardisik gun"]))
    # Uzun aile listelerinde ayni hedefi tekrarlama.
    unique={}
    for r in result:
        key=(r["Aile"],r["Hedef gun"],r["Ritim"])
        if key not in unique or r["Ardisik gun"]>unique[key]["Ardisik gun"]:
            unique[key]=r
    return list(unique.values())

def make_ticket(signal, draws, size=None):
    family = [int(x) for x in signal["label"].split("-")]
    size = len(family) if size is None else int(size)
    if size < len(family) or size > 10:
        raise ValueError("Kupon boyutu aileden küçük veya 10'dan büyük olamaz.")
    # Tamamlama rakamlari HEDEF ANINDAN once bilinen cekilisler.
    before=[d for d in draws if d["dt"]<signal["moment"]][-48:]
    counter=Counter(n for d in before for n in d["nums"] if n not in family)
    result=family[:]
    for n,_ in sorted(counter.items(),key=lambda t:(-t[1],t[0])):
        if len(result)>=size:break
        if n not in result:result.append(n)
    for n in range(1,81):
        if len(result)>=size:break
        if n not in result:result.append(n)
    return sorted(result[:size])

def secret_token():
    try:
        for key in ("GITHUB_TOKEN","GH_TOKEN","github_token"):
            if st.secrets.get(key):
                return str(st.secrets[key])
        if "github" in st.secrets and st.secrets["github"].get("token"):
            return str(st.secrets["github"]["token"])
    except Exception:
        pass
    return None

def api_state(token, write=None):
    url=f"https://api.github.com/repos/{REPO}/contents/{STATE_PATH}"
    headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"}
    res=requests.get(url,headers=headers,params={"ref":"main"},timeout=20)
    if res.status_code not in (200,404):
        res.raise_for_status()
    if write is None:
        if res.status_code==404:return None
        obj=res.json()
        return json.loads(base64.b64decode(obj["content"]))
    payload={"message":"V10: canli cekilis ve kupon kaydi",
             "branch":"main",
             "content":base64.b64encode(json.dumps(write,ensure_ascii=False).encode("utf8")).decode("ascii")}
    if res.status_code==200:
        payload["sha"]=res.json()["sha"]
    update=requests.put(url,headers=headers,json=payload,timeout=35)
    update.raise_for_status()
    return True

def validate_saved(value):
    if not isinstance(value,dict):raise ValueError("Yedek formati hatali")
    live=[]
    for d in value.get("live",[]):
        live.append(make_draw(d["no"],d["dt"],d["nums"]))
    tickets=value.get("tickets",[])
    if not isinstance(tickets,list):raise ValueError("Kuponlar listesi gecersiz")
    return {"live":live,"tickets":tickets}

def secret_admin_pin():
    try:
        return str(st.secrets.get("V10_ADMIN_PIN", ""))
    except Exception:
        return ""

def auto_save():
    tok=secret_token()
    if not tok:
        return "GitHub token ayarli degil; yerel oturum + JSON yedegi kullanin."
    if not secret_admin_pin():
        return "Güvenlik: Streamlit Secrets'e V10_ADMIN_PIN eklenmeden GitHub yazma kapali."
    if not st.session_state.get("v10_admin_unlocked", False):
        return "GitHub yazma kilitli. Yedek & Kayit sekmesinden PIN ile acin."
    try:
        api_state(tok, {"live":st.session_state.v10_live,
                        "tickets":st.session_state.v10_tickets})
        return "GitHub kalici kaydi guncellendi."
    except Exception as exc:
        return "GitHub kaydi basarisiz: "+str(exc)

def result_rows(tickets, draws):
    actual={(d["day"],d["pos"]):d for d in draws}
    rows=[]
    for t in tickets:
        d=actual.get((t["day"],t["pos"]))
        common=sorted(set(t["numbers"])&set(d["nums"])) if d else []
        k = len(t["numbers"])
        rows.append({"Hedef gun":t["day"],"Saat":t["time"],"Aile":t["family"],
                     "Boyut":k,
                     "Kupon":"-".join(map(str,t["numbers"])),
                     "Sonuc":f"{len(common)}/{k}" if d else "Bekleniyor",
                     "Isabet":len(common) if d else None,
                     "Tutan":"-".join(map(str,common)),
                     "Cekilis_no":d["no"] if d else "",
                     "Sinyal":t["kind"]})
    return rows

st.set_page_config(page_title="Hizli On V10 Canli Kupon Motoru",page_icon="🎯",
                   layout="wide",initial_sidebar_state="collapsed")
st.title("🎯 Hızlı On V10 — Canlı Ritim ve Kupon")
st.caption("5-10'lu aileler • hedef tarih/saat • canlı çekiliş • deneysel kupon • isabet")
st.warning("Geçmişteki tekrarlar gelecekteki sonucu garanti etmez. Kuponlar deneysel izleme içindir.")

if "v10_live" not in st.session_state:
    st.session_state.v10_live=[]
if "v10_tickets" not in st.session_state:
    st.session_state.v10_tickets=[]
if "v10_cloud_init" not in st.session_state:
    token=secret_token()
    if token:
        try:
            backup=api_state(token)
            if backup:
                b=validate_saved(backup)
                st.session_state.v10_live=b["live"]
                st.session_state.v10_tickets=b["tickets"]
        except Exception as exc:
            st.warning("GitHub kaydi alinamadi: "+str(exc))
    st.session_state.v10_cloud_init=True

historical=[];bad=0
try:
    raw=github_text("veri.txt")
    historical,bad=parse_history(raw)
except Exception as exc:
    st.error("GitHub veri.txt okunamadi. Asagidan TXT yukleyebilirsiniz. "+str(exc))

family_text=""
try:
    family_text=github_text("v10_aileler.csv")
except Exception as exc:
    st.warning("V10 aile havuzu GitHub'dan okunamadi: "+str(exc))

with st.expander("⚙️ Veri kaynağı ve aile havuzu",expanded=not historical or not family_text):
    upl=st.file_uploader("veri.txt dosyasi (GitHub erisimi yoksa)",type=["txt"],key="v10_txt")
    if upl:
        historical,bad=parse_history(upl.getvalue().decode("utf-8-sig"))
    upf=st.file_uploader("V9/V10 aile secim CSV (istege bagli)",type=["csv"],key="v10_csv")
    if upf:
        family_text=upf.getvalue().decode("utf-8-sig")
    if st.button("🔄 GitHub verilerini yenile"):
        github_text.clear()
        st.rerun()
    st.caption("Gecmis veri V9'da kalir. Bu sayfa agir aile kesfini yeniden calistirmaz.")
families=load_family_csv(family_text) if family_text else {}
if not families:
    st.error("Aile CSV bulunamadi; hedef tahmini icin v10_aileler.csv gerekli.")
draws=all_draws(historical,st.session_state.v10_live)
today=now_tr().date()
last_day=max([date.fromisoformat(x["day"]) for x in draws],default=today)
min_day=min([date.fromisoformat(x["day"]) for x in draws],default=today)

a,b,c=st.columns(3)
a.metric("Geçmiş çekiliş",len(historical))
b.metric("Aile havuzu",len(families))
c.metric("Canlı eklenen",len(st.session_state.v10_live))
if bad: st.caption(f"{bad} hatali/mukerrer satir gecmise alinmadi.")

tabs=st.tabs(["📥 Canlı giriş","🎯 Hedef & Kupon","📊 İsabet","💾 Yedek & Kayıt"])

with tabs[0]:
    st.subheader("📋 Çekiliş sonucunu aynen yapıştır")
    st.caption("Başlık, tarih-saat ve alt alta 20 sayı. Birden fazla çekilişi de aynı kutuya yapıştırabilirsin.")
    if st.session_state.pop("v10_clear_paste", False):
        st.session_state["v10_pasted_draw"] = ""
    pasted=st.text_area("Çekiliş sonuç metni",height=225,key="v10_pasted_draw",
         placeholder="Çekiliş no:61629\n12.10.2026-00:02\n5\n6\n11\n22\n...\n75")
    if st.button("📥 Yapıştırdığım çekilişi ekle",type="primary",key="v10_add_paste"):
        records, issues=parse_pasted_draws(pasted)
        known_ids={d["no"] for d in draws}
        known_slots={(d["day"],d["pos"]) for d in draws}
        added, repeats = 0, 0
        for d in records:
            if d["no"] in known_ids or (d["day"],d["pos"]) in known_slots:
                repeats+=1
                continue
            st.session_state.v10_live.append(d)
            known_ids.add(d["no"])
            known_slots.add((d["day"],d["pos"]))
            added+=1
        saved=auto_save() if added else ""
        st.session_state.v10_last_paste={"added":added,"repeats":repeats,"issues":issues[:5],"saved":saved}
        if added:
            st.session_state["v10_clear_paste"] = True
        st.rerun()
    if st.session_state.get("v10_last_paste"):
        p=st.session_state.v10_last_paste
        st.success(f"{p['added']} yeni çekiliş eklendi, {p['repeats']} kayıt zaten vardı.")
        if p["issues"]:
            st.warning("Kontrol: " + " | ".join(p["issues"]))
        if p["saved"]:
            st.caption(p["saved"])
    with st.expander("Tek tek alan doldur (isteğe bağlı)",expanded=False):
        default_no=max([d["no"] for d in draws],default=0)+1
        with st.form("manual_v10",clear_on_submit=False):
            no=st.number_input("Çekiliş numarası",min_value=1,value=default_no,step=1)
            day=st.date_input("Tarih",value=today)
            hr=st.selectbox("Saat",options=[moment("2026-01-01",p).strftime("%H:%M") for p in range(1,218)],
                            index=min(216,max(0,pos_of(now_tr())-1 if pos_of(now_tr()) else 0)))
            nums=st.text_area("Çıkan 20 sayı — virgül/boşlukla ayır",
                              placeholder="3, 8, 12, 18, ...",height=90)
            submit=st.form_submit_button("✅ Çekilişi ekle",type="primary")
        if submit:
            try:
                numbers=[int(x) for x in re.findall(r"\d+",nums)]
                dt=datetime.strptime(f"{day} {hr}","%Y-%m-%d %H:%M")
                new=make_draw(no,dt,numbers)
                if any(d["no"]==new["no"] or
                       (d["day"]==new["day"] and d["pos"]==new["pos"]) for d in draws):
                    raise ValueError("Ayni numara veya saatli cekilis zaten mevcut.")
                st.session_state.v10_live.append(new)
                st.success(f"#{new['no']} eklendi. "+auto_save())
            except Exception as exc:
                st.error("Eklenemedi: "+str(exc))

    st.write("**Toplu yükleme**")
    st.caption("Tek satır: 61653;12.10.2026 07:57;4,5,16,... şeklinde 20 sayı. Birden çok satır olabilir.")
    up=st.file_uploader("Çekiliş TXT / CSV yükle",type=["txt","csv"],key="batch_v10")
    if up and st.button("📥 Toplu çekilişleri ekle"):
        data=up.getvalue().decode("utf-8-sig")
        idx_no={d["no"] for d in draws}
        idx_pos={(d["day"],d["pos"]) for d in draws}
        added=0;invalid=0;duplicates=0
        for rawline in data.splitlines():
            if not re.match(r"^\s*\d+\s*;",rawline):continue
            try:
                d=parse_draw_line(rawline)
                if d["no"] in idx_no or (d["day"],d["pos"]) in idx_pos:
                    duplicates+=1;continue
                st.session_state.v10_live.append(d)
                idx_no.add(d["no"]);idx_pos.add((d["day"],d["pos"]))
                added+=1
            except Exception:
                invalid+=1
        st.success(f"{added} cekilis eklendi; {duplicates} tekrar, {invalid} hatali satir. "+auto_save())
    if st.session_state.v10_live:
        st.write("**Son eklenen çekilişler**")
        st.dataframe([{"No":d["no"],"Tarih":d["day"],"Saat":d["dt"][11:16],
                       "Sayılar":"-".join(map(str,d["nums"]))}
                      for d in st.session_state.v10_live[-12:][::-1]],
                     hide_index=True,use_container_width=True)

with tabs[1]:
    st.subheader("Aile aktivasyonu ve hedef çekiliş")
    analysis_date=st.date_input("Takip edilen gün",value=today,
                                min_value=min_day,max_value=max(today,last_day))
    daystr=analysis_date.isoformat()
    current=now_tr() if analysis_date==today else moment(daystr,217)+timedelta(minutes=1)
    cutoff=[d for d in draws if d["day"]<daystr]
    if not families or not cutoff:
        st.info("Hedef hesaplamak icin gecmis cekilis ve aile havuzu gerekli.")
        profiles={}
    else:
        profiles=train_profiles(json.dumps(cutoff,separators=(",",":")),
                                json.dumps(sorted(families),separators=(",",":")))
    signals,hits=active_signals(draws,families,profiles,daystr,current)
    st.caption("Model yalniz secilen gunden ONCEKI kayitlarla kurulur. Gorulmemis hedef saatleri listelenir.")
    st.metric("Günün aktif aileleri",len(hits))
    if analysis_date!=today:
        st.warning("Gecmis gun secili: tam gun verisi gorunebilecegi icin bu canli kor test degildir.")
    st.markdown("### 5'li – 10'lu hedef kuponları")
    groups={k:[] for k in range(5,11)}
    for signal in signals:
        groups[signal["size"]].append(signal)
    for k in range(5,11):
        options=sorted(groups[k],key=lambda x:(x["pos"],-x["support"],x["label"]))[:30]
        title=f"{k}'li aileler — {len(groups[k])} sinyal" if options else f"{k}'li aileler — Sinyal yok"
        with st.expander(title,expanded=bool(options)):
            if not options:
                st.caption("Bu boyutta ileri hedef yok. Motor 0 kupon öneriyor.")
                continue
            st.dataframe(
                [{"Aile":x["label"],"Hedef":str(x["level"])+". geliş",
                  "Saat":x["time"],"Çekiliş sırası":x["pos"],
                  "Aralık":"+"+str(x["gap"]),
                  "Destek günü":x["support"],"Sinyal":x["kind"]} for x in options],
                hide_index=True,use_container_width=True)
            pick=st.selectbox(f"{k}'li hedef seç",list(range(len(options))),
                format_func=lambda i:options[i]["time"]+" | "+options[i]["label"],
                key=f"v10_select_{k}")
            x=options[pick]
            ticket_nums=make_ticket(x,draws,size=k)
            st.markdown(f"**{k}'li kupon: "+", ".join(map(str,ticket_nums))+"**")
            st.caption(f"{x['day']} {x['time']} · {x['level']}. tam görünüş · {x['kind']}")
            if st.button(f"🎟️ {k}'li kuponu kaydet",key=f"v10_save_{k}"):
                ticket={"day":x["day"],"pos":x["pos"],"time":x["time"],
                        "family":x["label"],"numbers":ticket_nums,
                        "size":k,"kind":x["kind"],"trigger_no":x["trigger_no"],
                        "created_at":now_tr().isoformat(timespec="seconds")}
                key=(ticket["day"],ticket["pos"],ticket["family"])
                existing={(t["day"],t["pos"],t["family"]) for t in st.session_state.v10_tickets}
                if key in existing:
                    st.warning("Bu aile ve hedef için kupon zaten kayıtlı.")
                else:
                    st.session_state.v10_tickets.append(ticket)
                    st.success(f"{k}'li kupon kaydedildi. "+auto_save())
    if not signals:
        st.info("Şu an ileri saatli ritim hedefi yok. Yeni çekilişler eklendikçe güncellenir.")

    st.markdown("#### 10'lu ailelerin gün zinciri")
    watch=daily_chains(profiles,families,daystr)
    if watch:
        st.dataframe(watch[:50],hide_index=True,use_container_width=True)
        st.caption("Gun zinciri kesin saat vermez; bu nedenle otomatik kupon olusturulmaz.")
    else:
        st.caption("Bu tarihten sonraya uzanan +2/+5/+7/+14 zincir hedefi yok.")
    st.markdown("#### Bugün tam görünen aileler")
    if hits:
        top=[{"Aile":label,"Boyut":families[label]["k"],
              "Bugunku gorunus":len(recs),
              "Cekilisler":", ".join("#"+str(d["no"])+" "+d["dt"][11:16] for d in recs)}
             for label,recs in hits.items()]
        top.sort(key=lambda x:(-x["Boyut"],-x["Bugunku gorunus"],x["Aile"]))
        st.dataframe(top[:100],hide_index=True,use_container_width=True)

with tabs[2]:
    st.subheader("Kupon isabet raporu")
    results=result_rows(st.session_state.v10_tickets,draws)
    completed=[r for r in results if r["Isabet"] is not None]
    a,b,c=st.columns(3)
    a.metric("Kupon",len(results))
    b.metric("Sonuclanan",len(completed))
    c.metric("En yuksek isabet",max((r["Isabet"] for r in completed),default="-"))
    if results:
        st.dataframe([{k:v for k,v in r.items() if k!="Isabet"} for r in results],
                     hide_index=True,use_container_width=True)
        counts=Counter(r["Isabet"] for r in completed)
        st.write("**5'li–10'lu boyutlara göre isabet dağılımı**")
        by_k=Counter((r["Boyut"],r["Isabet"]) for r in completed)
        st.dataframe([{"Boyut":k,"Isabet":f"{i}/{k}","Kupon":by_k[(k,i)]}
                      for k in range(5,11) for i in range(k+1)],
                     hide_index=True,use_container_width=True)
        mem=io.StringIO()
        writer=csv.DictWriter(mem,fieldnames=results[0].keys(),delimiter=";")
        writer.writeheader();writer.writerows(results)
        st.download_button("⬇️ Isabet raporunu indir","\ufeff"+mem.getvalue(),
                           file_name="V10_ISABET_RAPORU.csv",mime="text/csv")
    else:
        st.info("Kaydedilmis kupon yok. Hedef ekranindan deneysel kupon kaydedebilirsiniz.")

with tabs[3]:
    st.subheader("Kalıcı kayıt ve yedek")
    tok=secret_token()
    pin=secret_admin_pin()
    st.write("GitHub token: "+"✅ Tanımlı" if tok else "GitHub token: ⚠️ Tanımlı değil")
    if tok and pin:
        if st.session_state.get("v10_admin_unlocked", False):
            st.success("Yonetici yetkisi acik. Kayitlar GitHub'a yazilabilir.")
        else:
            secret_entry=st.text_input("GitHub kaydini acmak icin V10 yonetici PIN",type="password")
            if st.button("🔐 Kalici kaydi ac"):
                if hmac.compare_digest(secret_entry,pin):
                    st.session_state.v10_admin_unlocked=True
                    st.success("Yonetici kilidi acildi.")
                else:
                    st.error("PIN yanlis.")
    elif tok:
        st.warning("GitHub'a guvenli yazma kapali. Secrets'e V10_ADMIN_PIN ekleyin.")
    st.caption("ChatGPT'ye GitHub baglamak Streamlit'e token aktarmaz. Streamlit Secrets'te GITHUB_TOKEN ve V10_ADMIN_PIN olmali.")
    payload={"live":st.session_state.v10_live,"tickets":st.session_state.v10_tickets}
    st.download_button("⬇️ Canli cekilis ve kupon JSON yedegi",
                       json.dumps(payload,ensure_ascii=False,indent=2),
                       file_name="V10_CANLI_KAYIT.json",mime="application/json")
    if st.button("☁️ Simdi GitHub'a kaydet"):
        st.info(auto_save())
    restore=st.file_uploader("Onceden indirilmis V10 JSON yedegi",type=["json"],key="restore_v10")
    if restore and st.button("📥 Yedegi geri yukle"):
        try:
            b=validate_saved(json.loads(restore.getvalue().decode("utf-8-sig")))
            st.session_state.v10_live=b["live"]
            st.session_state.v10_tickets=b["tickets"]
            st.success("Yedek geri yuklendi. "+auto_save())
            st.rerun()
        except Exception as exc:
            st.error("Yedek hatasi: "+str(exc))
    st.caption("Bu uygulama gercek cekilis sonuclarini tahmin garantisiyle sunmaz. Veriler acik GitHub deposuna kaydediliyorsa kamuya acik olabilir.")
