# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict, Counter
import hashlib, re, math
import io, zipfile, base64, json, urllib.request, urllib.error, urllib.parse
from math import comb

st.set_page_config(page_title="Hızlı On — Canlı Kupon V4", layout="wide")
st.title("🔥❄️ Hızlı On — Canlı Havuz + Kontrollü GitHub + Kupon Motoru V4")
st.caption("ham çekiliş yapıştır • doğrula • onayla • GitHub veri.txt’ye kontrollü kaydet • havuzu güncelle • kupon/ABSTAIN")

START = pd.Timestamp("2026-08-25 00:00:00")
HIST_END = pd.Timestamp("2026-09-29 23:59:59")

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

    cfg=github_config()
    if cfg["configured"]:
        try:
            raw,sha,cfg=github_fetch_veri()
            return raw,f"github/{cfg['repo']}/{cfg['path']}@{sha[:10]}"
        except Exception as e:
            st.warning(f"GitHub okunamadı, repo içi veri.txt deneniyor: {e}")

    p=Path("veri.txt")
    if p.exists():
        return p.read_text(encoding="utf-8-sig",errors="replace"),"repo/veri.txt"
    return None,None


# ----------------------------
# GITHUB KONTROLLÜ KAYIT + HAM YAPIŞTIRMA
# ----------------------------
def _secret_value(*names):
    """Hem üst-seviye hem [github] altındaki yaygın secret adlarını destekle."""
    for name in names:
        try:
            if name in st.secrets:
                v=st.secrets[name]
                if v not in (None,""):
                    return str(v)
        except Exception:
            pass
    try:
        gh=st.secrets["github"]
        for name in names:
            short=name.lower().replace("github_","").replace("gh_","")
            for key in (name, name.lower(), short):
                try:
                    if key in gh and gh[key] not in (None,""):
                        return str(gh[key])
                except Exception:
                    pass
    except Exception:
        pass
    return None

def github_config():
    token=_secret_value("GITHUB_TOKEN","GH_TOKEN","github_token","token")
    repo=_secret_value("GITHUB_REPO","GH_REPO","REPO","repo")
    owner=_secret_value("GITHUB_OWNER","GH_OWNER","owner")
    repo_name=_secret_value("GITHUB_REPO_NAME","REPO_NAME","repo_name")
    if repo and "/" not in repo and owner:
        repo=f"{owner}/{repo}"
    if not repo and owner and repo_name:
        repo=f"{owner}/{repo_name}"
    branch=_secret_value("GITHUB_BRANCH","GH_BRANCH","branch")
    path=_secret_value("GITHUB_DATA_PATH","GITHUB_PATH","DATA_PATH","data_path") or "veri.txt"
    return {
        "token":token,
        "repo":repo,
        "branch":branch,
        "path":path,
        "configured":bool(token and repo),
    }

def _github_request(url, token, method="GET", payload=None):
    headers={
        "Accept":"application/vnd.github+json",
        "Authorization":f"Bearer {token}",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"hizli-on-streamlit",
    }
    data=None
    if payload is not None:
        data=json.dumps(payload).encode("utf-8")
        headers["Content-Type"]="application/json"
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as resp:
            raw=resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8",errors="replace")
        try:
            msg=json.loads(body).get("message",body)
        except Exception:
            msg=body
        raise RuntimeError(f"GitHub HTTP {e.code}: {msg}")
    except Exception as e:
        raise RuntimeError(f"GitHub bağlantı hatası: {e}")

def github_fetch_veri():
    cfg=github_config()
    if not cfg["configured"]:
        raise RuntimeError("GitHub Secrets eksik: GITHUB_TOKEN ve GITHUB_REPO gerekli.")
    path_q=urllib.parse.quote(cfg["path"],safe="/")
    url=f"https://api.github.com/repos/{cfg['repo']}/contents/{path_q}"
    if cfg["branch"]:
        url += "?ref=" + urllib.parse.quote(cfg["branch"],safe="")
    obj=_github_request(url,cfg["token"])
    if obj.get("type")!="file":
        raise RuntimeError(f"{cfg['path']} GitHub'da dosya olarak bulunamadı.")
    content=base64.b64decode(obj.get("content","")).decode("utf-8-sig",errors="replace")
    return content,obj.get("sha",""),cfg

def parse_pasted_draws(raw_text):
    """Milli Piyango kopyala-yapıştır bloklarını 1 veya 6 çekiliş olarak okur."""
    txt=(raw_text or "").replace("\r\n","\n").replace("\r","\n").strip()
    if not txt:
        return [],["Giriş boş."]

    starts=list(re.finditer(r"(?im)^\s*(?:#+\s*)?Çekiliş\s*no\s*:",txt))
    recs=[]
    if starts:
        for j,m in enumerate(starts):
            end=starts[j+1].start() if j+1<len(starts) else len(txt)
            block=txt[m.start():end]

            mid=re.search(
                r"(?is)Çekiliş\s*no\s*:\s*(?:\n\s*(?:#+\s*)?)?\s*(\d+)",
                block
            )
            mdt=re.search(
                r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})",
                block
            )
            if not mid or not mdt:
                return [],[f"{j+1}. blokta çekiliş no veya tarih-saat okunamadı."]

            draw_id=int(mid.group(1))
            try:
                dt=pd.to_datetime(
                    mdt.group(1)+" "+mdt.group(2),
                    format="%d.%m.%Y %H:%M",
                    errors="raise"
                )
            except Exception:
                return [],[f"#{draw_id}: tarih-saat geçersiz."]

            tail=block[mdt.end():]
            tail=re.split(r"(?i)\bDetaylar\b",tail,maxsplit=1)[0]
            nums=[int(x) for x in re.findall(r"(?<!\d)\d{1,2}(?!\d)",tail)]
            recs.append((draw_id,dt,tuple(nums)))
    else:
        for line in txt.splitlines():
            x=parse_line(line)
            if x:
                recs.append(x)
        if not recs:
            return [],["'Çekiliş no:' başlığı veya geçerli veri.txt satırı bulunamadı."]

    errors=[]
    seen_ids=set()
    seen_times=set()
    clean=[]
    for draw_id,dt,nums0 in recs:
        nums=list(nums0)
        if draw_id in seen_ids:
            errors.append(f"#{draw_id}: aynı yapıştırmada mükerrer çekiliş no.")
        if pd.Timestamp(dt) in seen_times:
            errors.append(f"{pd.Timestamp(dt).strftime('%d.%m.%Y %H:%M')}: aynı yapıştırmada mükerrer saat.")
        seen_ids.add(draw_id); seen_times.add(pd.Timestamp(dt))

        if len(nums)!=20:
            errors.append(f"#{draw_id}: 20 sayı yerine {len(nums)} sayı bulundu.")
            continue
        if len(set(nums))!=20:
            errors.append(f"#{draw_id}: tekrar eden sayı var.")
            continue
        if not all(1<=n<=80 for n in nums):
            errors.append(f"#{draw_id}: 1–80 dışında sayı var.")
            continue
        mm=pd.Timestamp(dt).strftime("%M")
        if mm not in HOUR12:
            errors.append(f"#{draw_id}: dakika :{mm}; beklenen Hızlı On dakikalarından değil.")
            continue
        clean.append((int(draw_id),pd.Timestamp(dt),tuple(sorted(nums))))

    clean=sorted(clean,key=lambda x:(x[1],x[0]))
    if errors:
        return clean,errors

    if len(clean)==6:
        days={r[1].strftime("%d.%m.%Y") for r in clean}
        hours={r[1].strftime("%H") for r in clean}
        mins=[r[1].strftime("%M") for r in clean]
        if len(days)!=1 or len(hours)!=1 or tuple(mins)!=FIRST6:
            errors.append("6'lı giriş yalnız aynı saatin :02,:07,:12,:17,:22,:27 ilk6 paketi olabilir.")
    elif len(clean)==1:
        pass
    else:
        errors.append("Canlı girişte yalnız 1 çekiliş veya tam 6 çekilişlik ilk6 paketi kabul edilir.")

    return clean,errors

def validate_against_remote(records, remote_raw):
    digest=hashlib.sha256(remote_raw.encode("utf-8",errors="replace")).hexdigest()
    rdf,rej,dups=parse_text(remote_raw,digest)
    by_id={int(r.draw_id):(pd.Timestamp(r.time),tuple(r.numbers)) for r in rdf.itertuples(index=False)}
    by_time={pd.Timestamp(r.time):int(r.draw_id) for r in rdf.itertuples(index=False)}
    latest_time=pd.Timestamp(rdf.time.max()) if len(rdf) else None

    add=[]; skipped=[]; conflicts=[]
    for draw_id,dt,nums in records:
        if draw_id in by_id:
            old_dt,old_nums=by_id[draw_id]
            if old_dt==dt and tuple(old_nums)==tuple(nums):
                skipped.append(draw_id)
            else:
                conflicts.append(f"#{draw_id}: GitHub'da aynı no farklı veriyle kayıtlı.")
            continue

        if dt in by_time:
            conflicts.append(
                f"{dt.strftime('%d.%m.%Y %H:%M')}: GitHub'da bu saatte #{by_time[dt]} var; yeni kayıt #{draw_id}."
            )
            continue

        if latest_time is not None and dt <= latest_time:
            conflicts.append(
                f"#{draw_id} {dt.strftime('%d.%m.%Y %H:%M')}: repo son kaydından "
                f"({latest_time.strftime('%d.%m.%Y %H:%M')}) eski/aynı. Canlı kayıt engellendi."
            )
            continue
        add.append((draw_id,dt,nums))

    return add,skipped,conflicts,rdf

def canonical_line(rec):
    draw_id,dt,nums=rec
    return f"{draw_id};{pd.Timestamp(dt).strftime('%d.%m.%Y-%H:%M')};" + ",".join(map(str,nums))

def github_commit_records(records):
    remote_raw,sha,cfg=github_fetch_veri()
    add,skipped,conflicts,rdf=validate_against_remote(records,remote_raw)
    if conflicts:
        return {"ok":False,"conflicts":conflicts,"skipped":skipped,"added":[]}
    if not add:
        return {"ok":True,"message":"Yeni kayıt yok; verilenlerin tamamı zaten mevcut.","skipped":skipped,"added":[]}

    new_text=remote_raw.rstrip()+"\n"+"\n".join(canonical_line(x) for x in add)+"\n"
    dates={pd.Timestamp(x[1]).strftime("%d.%m.%Y") for x in add}
    times=[pd.Timestamp(x[1]).strftime("%H:%M") for x in add]
    ids=[x[0] for x in add]

    if len(add)==6:
        commit_msg=f"{next(iter(dates))} {times[0]}–{times[-1]} ilk6 eklendi"
    else:
        commit_msg=f"#{ids[0]} {next(iter(dates))} {times[0]} canlı çekiliş eklendi"

    path_q=urllib.parse.quote(cfg["path"],safe="/")
    url=f"https://api.github.com/repos/{cfg['repo']}/contents/{path_q}"
    payload={
        "message":commit_msg,
        "content":base64.b64encode(new_text.encode("utf-8")).decode("ascii"),
        "sha":sha,
    }
    if cfg["branch"]:
        payload["branch"]=cfg["branch"]

    try:
        result=_github_request(url,cfg["token"],method="PUT",payload=payload)
    except RuntimeError as e:
        return {"ok":False,"conflicts":[str(e)],"skipped":skipped,"added":[]}

    verify_raw,verify_sha,_=github_fetch_veri()
    vd,_,_=parse_text(
        verify_raw,
        hashlib.sha256(verify_raw.encode("utf-8",errors="replace")).hexdigest()
    )
    vmap={int(r.draw_id):(pd.Timestamp(r.time),tuple(r.numbers)) for r in vd.itertuples(index=False)}
    missing=[]
    for rec in add:
        if rec[0] not in vmap or vmap[rec[0]]!=(rec[1],tuple(rec[2])):
            missing.append(rec[0])
    if missing:
        return {
            "ok":False,
            "conflicts":[f"Commit oluştu fakat doğrulamada bulunamayan kayıtlar: {missing}"],
            "skipped":skipped,
            "added":[x[0] for x in add],
        }

    return {
        "ok":True,
        "message":f"{len(add)} çekiliş GitHub'a kaydedildi ve tekrar okunarak doğrulandı.",
        "added":[x[0] for x in add],
        "skipped":skipped,
        "commit":result.get("commit",{}).get("sha","")[:10],
        "file_sha":verify_sha[:10],
    }

# ----------------------------
# CANLI YAŞAM METRİKLERİ
# ----------------------------
def binom_z(h,n,p=.25,prior_n=12):
    """Küçük örnekleri yumuşatan z-skoru."""
    if n<=0:
        return 0.0
    mu=n*p
    sd=math.sqrt((n+prior_n)*p*(1-p))
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
    """80 sayıdan 20 çekilirken k_pool üyeli havuz için Hypergeometric P(X>=need)."""
    den=comb(80,k_pool)
    s=0
    for j in range(need,min(k_pool,20)+1):
        s += comb(20,j)*comb(60,k_pool-j)
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
                "is_full5":int(len(members)==5),
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

            # 5'linin her üyesinin hedef ÖNCESİ yaşam kimliği.
            # prev1/2/3 = snapshot dahil son 1/2/3 çekilişte kaç kez aktifti.
            for pos, i in enumerate(chunk,1):
                row[f"p{pos}_num"]=i+1
                row[f"p{pos}_prev1"]=int(mat[t,i])
                row[f"p{pos}_prev2"]=int(mat[max(0,t-1):t+1,i].sum())
                row[f"p{pos}_prev3"]=int(mat[max(0,t-2):t+1,i].sum())
                row[f"p{pos}_prev6"]=int(h6[i])
                row[f"p{pos}_score"]=float(score[i])
                row[f"p{pos}_act"]=float(act_idx[i])
                row[f"p{pos}_gap"]=int(gaps[i])
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
            pool_tag = "5LI" if len(members)==5 else f"PARTIAL-{len(members)}"
            report_lines.append(
                f"• {status} G{g} {pool_tag} [{'-'.join(f'{n:02d}' for n in members)}] "
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
        eval_pools=pools_df[pools_df.pool_size==5].copy()
        for (status,rank),g in eval_pools.groupby(["status","group_rank"]):
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
    full=pools[pools.pool_size==5].copy()

    rows=[]
    for (status,rank),g in full.groupby(["status","group_rank"]):
        gg=g.dropna(subset=["hit_h1"])
        if gg.empty: continue
        rows.append({
            "status":status,"group_rank":int(rank),"events":len(gg),
            "mean_h1":gg.hit_h1.mean(),
            "edge_vs_random":gg.hit_h1.mean()-1.25,
            "p_h1_2plus":100*(gg.hit_h1>=2).mean(),
            "edge_2plus_pp":100*((gg.hit_h1>=2).mean()-random_p_ge(5,2)),
            "p_h1_3plus":100*(gg.hit_h1>=3).mean(),
            "mean_max_next6":gg.max_same_draw_next6.mean(),
            "p_max_next6_2plus":100*(gg.max_same_draw_next6>=2).mean(),
            "p_max_next6_3plus":100*(gg.max_same_draw_next6>=3).mean(),
            "mean_cum_unique6":gg.cum_unique_h6.mean(),
        })
    status_agg=pd.DataFrame(rows)

    stage_minutes=("27","32","37","42","47","52")
    stage=full[full.minute.isin(stage_minutes)].copy()
    stage_rows=[]
    for (minute,zband,status,rank),g in stage.groupby(["minute","zero6_band","status","group_rank"]):
        if not zband: continue
        gg=g.dropna(subset=["hit_h1"])
        if len(gg)<20: continue
        stage_rows.append({
            "snapshot_minute":minute,"zero6_band":zband,
            "status":status,"group_rank":int(rank),"events":len(gg),
            "next_draw_mean_hits":gg.hit_h1.mean(),
            "edge_vs_random":gg.hit_h1.mean()-1.25,
            "next_draw_2plus_pct":100*(gg.hit_h1>=2).mean(),
            "edge_2plus_pp":100*((gg.hit_h1>=2).mean()-random_p_ge(5,2)),
            "next_draw_3plus_pct":100*(gg.hit_h1>=3).mean(),
            "next6_max_2plus_pct":100*(gg.max_same_draw_next6>=2).mean(),
            "next6_max_3plus_pct":100*(gg.max_same_draw_next6>=3).mean(),
            "next6_unique_mean":gg.cum_unique_h6.mean(),
        })
    stage_agg=pd.DataFrame(stage_rows)

    # One chronological split used everywhere below.
    dates=sorted(full.date.unique(),key=lambda x:pd.to_datetime(x,dayfirst=True))
    cut=max(1,len(dates)//2)
    first_half=set(dates[:cut])
    second_half=set(dates[cut:])
    stage["half"]=np.where(stage.date.isin(first_half),"H1","H2")

    hrows=[]
    for (minute,zband,status,rank),g in stage.groupby(["minute","zero6_band","status","group_rank"]):
        if not zband: continue
        halves={}
        for half,gh in g.groupby("half"):
            gh=gh.dropna(subset=["hit_h1"])
            halves[half]={
                "n":len(gh),
                "mean":gh.hit_h1.mean() if len(gh) else np.nan,
                "p2":100*(gh.hit_h1>=2).mean() if len(gh) else np.nan,
                "p3":100*(gh.hit_h1>=3).mean() if len(gh) else np.nan,
            }
        if "H1" not in halves or "H2" not in halves: continue
        stable=(halves["H1"]["n"]>=40 and halves["H2"]["n"]>=40 and
                halves["H1"]["mean"]>1.25 and halves["H2"]["mean"]>1.25 and
                halves["H1"]["p2"]>100*random_p_ge(5,2) and halves["H2"]["p2"]>100*random_p_ge(5,2))
        hrows.append({
            "snapshot_minute":minute,"zero6_band":zband,"status":status,"group_rank":int(rank),
            "n_H1":halves["H1"]["n"],"mean_H1":halves["H1"]["mean"],"p2_H1":halves["H1"]["p2"],"p3_H1":halves["H1"]["p3"],
            "n_H2":halves["H2"]["n"],"mean_H2":halves["H2"]["mean"],"p2_H2":halves["H2"]["p2"],"p3_H2":halves["H2"]["p3"],
            "stable_candidate":stable
        })
    validation_agg=pd.DataFrame(hrows)
    if not validation_agg.empty:
        validation_agg=validation_agg.sort_values(["stable_candidate","p2_H2","mean_H2"],ascending=[False,False,False])

    branch_specs = [
        ("B1", "52", "ZERO6_HIGH", "NEUTRAL", 4, "57"),
        ("B2", "42", "ZERO6_LOW",  "COLD",    1, "47"),
        ("B3", "42", "ZERO6_MID",  "COLD",    2, "47"),
        ("B4", "47", "ZERO6_HIGH", "NEUTRAL", 1, "52"),
    ]

    branch_rows=[]
    pair_rows=[]
    triple_rows=[]
    member_rows=[]
    core_rows=[]
    from itertools import combinations

    for bid,minute,zband,status,rank,target in branch_specs:
        g=full[(full.minute==minute)&(full.zero6_band==zband)&(full.status==status)&(full.group_rank==rank)].copy()
        g=g.dropna(subset=["hit_h1"])
        if g.empty: continue

        # Member-level PRE-TARGET records.
        mrecords=[]
        for r in g.itertuples(index=False):
            hits=set(int(x) for x in str(r.members_h1).split(",") if str(x).strip())
            for pos in range(1,6):
                n=int(getattr(r,f"p{pos}_num"))
                rec={
                    "branch":bid,"date":r.date,"snapshot":minute,"target":target,
                    "pos":pos,"number":n,
                    "prev1":int(getattr(r,f"p{pos}_prev1")),
                    "prev2":int(getattr(r,f"p{pos}_prev2")),
                    "prev3":int(getattr(r,f"p{pos}_prev3")),
                    "prev6":int(getattr(r,f"p{pos}_prev6")),
                    "score":float(getattr(r,f"p{pos}_score")),
                    "act":float(getattr(r,f"p{pos}_act")),
                    "gap":int(getattr(r,f"p{pos}_gap")),
                    "hit_next":int(n in hits),
                    "half":"H1" if r.date in first_half else "H2",
                }
                mrecords.append(rec)
                member_rows.append(rec)
        md=pd.DataFrame(mrecords)

        # Position/pair/triple statistics on the full branch (descriptive).
        pair_total=Counter(); pair_hit=Counter()
        tri_total=Counter(); tri_hit=Counter()
        pos_total=Counter(); pos_hit=Counter()
        for r in g.itertuples(index=False):
            members=[int(getattr(r,f"p{p}_num")) for p in range(1,6)]
            hits=set(int(x) for x in str(r.members_h1).split(",") if str(x).strip())
            for p,n in enumerate(members,1):
                pos_total[p]+=1
                if n in hits: pos_hit[p]+=1
            for combi in combinations(range(5),2):
                key=tuple(x+1 for x in combi)
                pair_total[key]+=1
                if members[combi[0]] in hits and members[combi[1]] in hits:
                    pair_hit[key]+=1
            for combi in combinations(range(5),3):
                key=tuple(x+1 for x in combi)
                tri_total[key]+=1
                if all(members[i] in hits for i in combi):
                    tri_hit[key]+=1

        branch_rows.append({
            "branch":bid,"snapshot":minute,"target":target,"zero6_band":zband,
            "status":status,"group_rank":rank,"events":len(g),
            "mean_hits":g.hit_h1.mean(),"p2":100*(g.hit_h1>=2).mean(),"p3":100*(g.hit_h1>=3).mean(),
            "mean_life_score":g.mean_life_score.mean(),
            "mean_activation_index":g.mean_activation_index.mean(),
            "mean_gap":g.mean_gap.mean(),
            "best_pos":"; ".join(
                f"P{p}:{100*pos_hit[p]/pos_total[p]:.1f}%"
                for p in sorted(pos_total, key=lambda p: pos_hit[p]/pos_total[p], reverse=True)
            )
        })
        for key in sorted(pair_total):
            pair_rows.append({
                "branch":bid,"positions":"-".join(map(str,key)),"events":pair_total[key],
                "both_hit":pair_hit[key],"both_hit_pct":100*pair_hit[key]/pair_total[key]
            })
        for key in sorted(tri_total):
            triple_rows.append({
                "branch":bid,"positions":"-".join(map(str,key)),"events":tri_total[key],
                "all3_hit":tri_hit[key],"all3_hit_pct":100*tri_hit[key]/tri_total[key]
            })

        # Why do members activate? prev1/2/3 life states with chronological split.
        for pos in range(1,6):
            for prev3 in range(0,4):
                mm=md[(md.pos==pos)&(md.prev3==prev3)]
                if len(mm)<20: continue
                h1=mm[mm.half=="H1"]; h2=mm[mm.half=="H2"]
                member_rows.append({
                    "branch":bid,"date":"AGG","snapshot":minute,"target":target,
                    "pos":pos,"number":-1,"prev1":-1,"prev2":-1,"prev3":prev3,"prev6":-1,
                    "score":mm.score.mean(),"act":mm.act.mean(),"gap":mm.gap.mean(),
                    "hit_next":mm.hit_next.mean(),
                    "half":f"AGG n={len(mm)} H1={len(h1)} H2={len(h2)}"
                })

        # H1 learns which positions are strongest; H2 tests them unchanged.
        h1m=md[md.half=="H1"]
        h2g=g[g.date.isin(second_half)].copy()
        if len(h1m)>=20 and len(h2g)>=20:
            pos_rates=h1m.groupby("pos").hit_next.mean().sort_values(ascending=False)
            for core_size in (3,4):
                selected=list(pos_rates.head(core_size).index)
                h2_hits=[]
                for rr in h2g.itertuples(index=False):
                    hitset=set(int(x) for x in str(rr.members_h1).split(",") if str(x).strip())
                    nums=[int(getattr(rr,f"p{p}_num")) for p in selected]
                    h2_hits.append(sum(n in hitset for n in nums))
                arr=np.array(h2_hits,dtype=int)
                core_rows.append({
                    "branch":bid,"core_size":core_size,
                    "selected_positions":"-".join(map(str,selected)),
                    "learn_H1_position_rates":"; ".join(f"P{p}:{100*pos_rates[p]:.1f}%" for p in selected),
                    "H2_events":len(arr),
                    "H2_mean":float(arr.mean()),
                    "H2_edge_vs_random":float(arr.mean()-core_size*.25),
                    "H2_p2":100*float(np.mean(arr>=2)),
                    "H2_p3":100*float(np.mean(arr>=3)) if core_size>=3 else np.nan,
                    "random_p2":100*random_p_ge(core_size,2),
                    "random_p3":100*random_p_ge(core_size,3) if core_size>=3 else np.nan,
                })

    branch_agg=pd.DataFrame(branch_rows)
    pair_agg=pd.DataFrame(pair_rows)
    triple_agg=pd.DataFrame(triple_rows)

    # Separate raw member records from aggregate "why" rows.
    member_df=pd.DataFrame([r for r in member_rows if r.get("date")!="AGG"])
    why_rows=[]
    if not member_df.empty:
        for (branch,pos,prev3),gg in member_df.groupby(["branch","pos","prev3"]):
            if len(gg)<20: continue
            h1=gg[gg.half=="H1"]; h2=gg[gg.half=="H2"]
            why_rows.append({
                "branch":branch,"pos":int(pos),"prev3":int(prev3),"events":len(gg),
                "mean_score":gg.score.mean(),"mean_act":gg.act.mean(),"mean_gap":gg.gap.mean(),
                "hit_rate_all":100*gg.hit_next.mean(),
                "H1_n":len(h1),"H1_hit_pct":100*h1.hit_next.mean() if len(h1) else np.nan,
                "H2_n":len(h2),"H2_hit_pct":100*h2.hit_next.mean() if len(h2) else np.nan,
                "stable_above25":bool(len(h1)>=15 and len(h2)>=15 and h1.hit_next.mean()>.25 and h2.hit_next.mean()>.25)
            })
    why_agg=pd.DataFrame(why_rows)
    if not why_agg.empty:
        why_agg=why_agg.sort_values(["stable_above25","H2_hit_pct","events"],ascending=[False,False,False])

    core_agg=pd.DataFrame(core_rows)

    return pools,snaps,status_agg,stage_agg,validation_agg,branch_agg,pair_agg,triple_agg,why_agg,core_agg

def make_master_report(df,rejected,dup,day_results,status_agg,stage_agg,validation_agg,branch_agg,pair_agg,triple_agg,why_agg,core_agg,source,digest):
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
    L.append("Yaşam puanı: son6 + son12 + son24 + gün içi yumuşatılmış binom-z + yakın dönem trendi.")
    L.append("Aktivasyon indeksi: yaşam puanı + puan değişimi + mevcut çekiliş aktivitesi + kısa dönem oran.")
    L.append("ÖNEMLİ: gap/uzun bekleme 'artık çıkmalı' varsayımıyla puanlanmaz; sadece betimleyici olarak raporlanır.")
    L.append("")
    L.append("5'Lİ RASTGELE TEK ÇEKİLİŞ REFERANSI — DÜZELTİLMİŞ HİPERGEOMETRİK")
    L.append(f"E[isabet]=1.250 | P(2+)=%{100*random_p_ge(5,2):.2f} | P(3+)=%{100*random_p_ge(5,3):.2f} | P(4+)=%{100*random_p_ge(5,4):.3f}")
    L.append("")

    L.append("[A] TÜM DÖNEM — YALNIZ TAM 5'Lİ STATÜ HAVUZLARI")
    L.append("-"*115)
    if not status_agg.empty:
        for r in status_agg.sort_values(["status","group_rank"]).itertuples(index=False):
            L.append(
                f"{r.status} G{r.group_rank} | n={r.events} | sonraki1 ort={r.mean_h1:.3f} "
                f"| mean-edge={r.edge_vs_random:+.3f} "
                f"| P1(2+)=%{r.p_h1_2plus:.1f} edge={r.edge_2plus_pp:+.1f}pp | P1(3+)=%{r.p_h1_3plus:.2f} "
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
                    f"| next ort={r.next_draw_mean_hits:.3f} edge={r.edge_vs_random:+.3f} "
                    f"| next 2+%={r.next_draw_2plus_pct:.1f} edge={r.edge_2plus_pp:+.1f}pp "
                    f"| 6-adım max2+%={r.next6_max_2plus_pct:.1f} max3+%={r.next6_max_3plus_pct:.1f} "
                    f"| unique6={r.next6_unique_mean:.2f}"
                )

    L.append("\n[C] KRONOLOJİK İKİ-YARI İSTİKRAR KONTROLÜ")
    L.append("-"*115)
    L.append("Yalnız TAM 5'li havuzlar. STABLE_CANDIDATE için iki yarıda da n>=40,")
    L.append("ortalama isabet >1.25 ve P(2+) > %36.71 şartı aranır.")
    L.append("Bu çoklu tarama nedeniyle kanıt değil; sonraki gün kör doğrulamasına aday üretir.")
    if validation_agg is not None and not validation_agg.empty:
        vg=validation_agg[validation_agg.stable_candidate==True].copy()
        if vg.empty:
            L.append("İki yarıda birden eşiği geçen aday yok.")
        else:
            for r in vg.itertuples(index=False):
                L.append(
                    f":{r.snapshot_minute} {r.zero6_band} {r.status} G{r.group_rank} | "
                    f"H1 n={r.n_H1} mean={r.mean_H1:.3f} 2+%={r.p2_H1:.1f} | "
                    f"H2 n={r.n_H2} mean={r.mean_H2:.3f} 2+%={r.p2_H2:.1f}"
                )

    L.append("\n[D] DÖRT ANA HAT — 5'LİDEN 3/4'LÜ ÇEKİRDEĞE KAZI")
    L.append("="*115)
    L.append("B1=:52 ZERO6_HIGH NEUTRAL G4 → :57")
    L.append("B2=:42 ZERO6_LOW COLD G1 → :47")
    L.append("B3=:42 ZERO6_MID COLD G2 → :47")
    L.append("B4=:47 ZERO6_HIGH NEUTRAL G1 → :52")
    if branch_agg is not None and not branch_agg.empty:
        for r in branch_agg.itertuples(index=False):
            L.append(
                f"{r.branch} | n={r.events} mean={r.mean_hits:.3f} 2+%={r.p2:.1f} 3+%={r.p3:.1f} "
                f"| yaşam={r.mean_life_score:+.3f} aktivasyon={r.mean_activation_index:+.3f} gap={r.mean_gap:.2f} "
                f"| pozisyon-isabet={r.best_pos}"
            )
            pg=pair_agg[pair_agg.branch==r.branch].sort_values("both_hit_pct",ascending=False).head(5)
            if not pg.empty:
                L.append("  En güçlü pozisyon çiftleri: " + " ; ".join(
                    f"{x.positions} %{x.both_hit_pct:.1f}" for x in pg.itertuples(index=False)
                ))
            tg=triple_agg[triple_agg.branch==r.branch].sort_values("all3_hit_pct",ascending=False).head(5)
            if not tg.empty:
                L.append("  En güçlü pozisyon üçlüleri: " + " ; ".join(
                    f"{x.positions} %{x.all3_hit_pct:.1f}" for x in tg.itertuples(index=False)
                ))

    L.append("\n[E] ÖNCEKİ 1–3 ÇEKİLİŞ YAŞAMI — HANGİ ÜYE NEDEN AKTİVE OLUYOR?")
    L.append("="*115)
    if why_agg is not None and not why_agg.empty:
        vg=why_agg[why_agg.stable_above25==True].copy()
        if vg.empty:
            L.append("İki yarıda da tek-sayı rastgele %25 üstünde kalan prev3/pozisyon hücresi yok.")
        else:
            for r in vg.itertuples(index=False):
                L.append(
                    f"{r.branch} P{r.pos} prev3={r.prev3} | n={r.events} "
                    f"| score={r.mean_score:+.3f} act={r.mean_act:+.3f} gap={r.mean_gap:.2f} "
                    f"| H1 {r.H1_n} hit%={r.H1_hit_pct:.1f} | H2 {r.H2_n} hit%={r.H2_hit_pct:.1f}"
                )

    L.append("\n[F] 3'LÜ / 4'LÜ ÇEKİRDEK — H1'DE ÖĞREN, H2'DE DEĞİŞTİRMEDEN TEST")
    L.append("="*115)
    if core_agg is not None and not core_agg.empty:
        for r in core_agg.itertuples(index=False):
            L.append(
                f"{r.branch} {r.core_size}Lİ | pozisyon={r.selected_positions} "
                f"| H1 oranlar={r.learn_H1_position_rates} | H2 n={r.H2_events} "
                f"| mean={r.H2_mean:.3f} edge={r.H2_edge_vs_random:+.3f} "
                f"| 2+%={r.H2_p2:.1f} (rand %{r.random_p2:.1f}) "
                f"| 3+%={r.H2_p3:.1f} (rand %{r.random_p3:.1f})"
            )

    L.append("\n[G] GÜN GÜN / HER ÇEKİLİŞ DETAYI")
    L.append("="*115)
    for d in day_results:
        L.append(d["report"])
    return "\n".join(L)


# ----------------------------
# CANLI KUPON MOTORU
# ----------------------------
# Bu kurallar 25.08–29.09 araştırmasından kilitlendi.
# Yeni veri geldikçe yaşam havuzları güncellenir; kurallar canlıda yeniden optimize edilmez.
LIVE_BRANCHES = [
    # branch, snapshot minute, next target, ZERO6 band, status, group rank, selected positions
    ("B3", "42", "47", "ZERO6_MID",  "COLD",    2, (2,4,5,1)),
    ("B4", "47", "52", "ZERO6_HIGH", "NEUTRAL", 1, (4,3,5,1)),
    ("B1", "52", "57", "ZERO6_HIGH", "NEUTRAL", 4, (3,4,2,5)),
]

NEXT_TARGET = {
    "27":"32",
    "32":"37",
    "37":"42",
    "42":"47",
    "47":"52",
    "52":"57",
}

def build_live_motor(df_live, digest):
    if df_live.empty:
        return {"ready":False, "message":"Canlı veri yok."}

    latest = df_live.sort_values(["time","draw_id"]).iloc[-1]
    latest_day_key = latest.time.strftime("%d.%m.%Y")
    latest_minute = latest.time.strftime("%M")
    latest_hour = latest.time.strftime("%H")

    day = df_live[df_live.time.dt.strftime("%d.%m.%Y")==latest_day_key][["draw_id","time","numbers"]].copy()
    serial=[(int(r.draw_id),r.time,tuple(r.numbers)) for r in day.itertuples(index=False)]
    dres = analyze_day(serial, latest_day_key, digest)

    out = {
        "ready":True,
        "date":latest_day_key,
        "hour":latest_hour,
        "minute":latest_minute,
        "draw_id":int(latest.draw_id),
        "next_target":NEXT_TARGET.get(latest_minute),
        "first6_complete":False,
        "zero6_band":"",
        "q6":None,
        "signals":[],
        "message":"",
    }

    # İlk6 kimliği ancak aynı saatin :02..:27 çekilişlerinin tamamı geldiyse kullanılabilir.
    day_rows = day.copy()
    same_hour = day_rows[day_rows.time.dt.strftime("%H")==latest_hour]
    have_minutes=set(same_hour.time.dt.strftime("%M"))
    out["first6_complete"] = all(m in have_minutes for m in FIRST6)

    if not out["first6_complete"]:
        missing=[m for m in FIRST6 if m not in have_minutes]
        out["message"]="İlk 6 henüz tamamlanmadı. Eksik: " + ",".join(":"+m for m in missing)
        return out

    # İlk6 karakteri
    hchars=make_hour_chars(day)
    hc=hchars.get(latest_hour)
    if hc:
        out["zero6_band"]=hc["zero6_band"]
        out["q6"]=hc["q6"]

    if latest_minute not in NEXT_TARGET:
        if latest_minute=="57":
            out["message"]="Bu saat tamamlandı. Yeni saatin ilk 6 çekilişi bekleniyor."
        else:
            out["message"]="Motor hedef kontrol dakikasında değil."
        return out

    # :27/:32/:37 için henüz 3/4'lü çekirdek kuralı kilitlenmedi.
    if latest_minute in ("27","32","37"):
        out["message"]=(
            f"İlk6 kimliği hazır ({out['zero6_band']}). Sonraki hedef :{NEXT_TARGET[latest_minute]}; "
            "ancak bu erken hedef için kilitli 3/4'lü çekirdek kuralımız henüz yok → ABSTAIN."
        )
        return out

    # Snapshot anındaki 5'li havuzları al.
    pools=dres["pools"]
    snap=pools[(pools.time==latest.time.strftime("%H:%M")) & (pools.pool_size==5)].copy()

    for branch,snapshot,target,zband,status,rank,positions in LIVE_BRANCHES:
        if snapshot != latest_minute:
            continue
        if out["zero6_band"] != zband:
            continue

        g=snap[(snap.status==status)&(snap.group_rank==rank)]
        if g.empty:
            continue

        r=g.iloc[0]
        members=[int(x) for x in str(r.members).split("-") if x]
        if len(members)!=5:
            continue

        coupon=[members[p-1] for p in positions]
        detail=[]
        for p in positions:
            detail.append({
                "pos":p,
                "num":int(r[f"p{p}_num"]),
                "prev1":int(r[f"p{p}_prev1"]),
                "prev2":int(r[f"p{p}_prev2"]),
                "prev3":int(r[f"p{p}_prev3"]),
                "prev6":int(r[f"p{p}_prev6"]),
                "score":float(r[f"p{p}_score"]),
                "act":float(r[f"p{p}_act"]),
                "gap":int(r[f"p{p}_gap"]),
            })

        out["signals"].append({
            "branch":branch,
            "snapshot":snapshot,
            "target":target,
            "zband":zband,
            "status":status,
            "rank":rank,
            "positions":positions,
            "pool5":members,
            "coupon4":coupon,
            "detail":detail,
        })

    if not out["signals"]:
        out["message"]=(
            f"İlk6 kimliği={out['zero6_band']} ve hedef :{NEXT_TARGET[latest_minute]}. "
            "Kilitli B1/B3/B4 koşullarından hiçbiri açılmadı → ABSTAIN."
        )
    return out

# ----------------------------
# UI
# ----------------------------
with st.sidebar:
    st.header("Veri / GitHub")
    uploaded=st.file_uploader("İstersen veri.txt yükle",type=["txt"])
    cfg=github_config()
    if cfg["configured"]:
        st.success(f"GitHub bağlı: {cfg['repo']} / {cfg['path']}")
    else:
        st.warning("GitHub kayıt için Secrets: GITHUB_TOKEN + GITHUB_REPO")
    st.caption("Dosya yükleme yalnız yedek/recovery içindir. Normal kullanımda GitHub veri.txt okunur.")
    if st.button("🔄 GÜNCEL VERİYİ OKU",width="stretch"):
        st.cache_data.clear()
        st.session_state.pop("analysis",None)
        st.rerun()

raw,source=read_source(uploaded)
if raw is None:
    st.error("veri.txt bulunamadı. Repo kökünde veri.txt olmalı.")
    st.stop()

digest=hashlib.sha256(raw.encode("utf-8",errors="replace")).hexdigest()
df0,rejected,dup=parse_text(raw,digest)

# Tüm güncel veri canlı motor içindir.
df_live=df0[df0.time>=START].copy().reset_index(drop=True)

# 25.08–29.09 araştırma tabanı SABİT tutulur; yeni sonuçlar kuralı canlıda değiştirmez.
df=df_live[df_live.time<=HIST_END].copy().reset_index(drop=True)

c1,c2,c3,c4,c5=st.columns(5)
c1.metric("Toplam veri",len(df_live))
c2.metric("Toplam gün",df_live.time.dt.date.nunique() if len(df_live) else 0)
c3.metric("Araştırma tabanı",len(df))
c4.metric("Son güncel",df_live.time.max().strftime("%d.%m.%Y %H:%M") if len(df_live) else "-")
c5.metric("SHA",digest[:10])

st.info(
    "CANLI MOTOR: veri.txt'ye yeni çekiliş geldikçe 1–80 yaşam statüsü ve 5'li havuzlar yeniden hesaplanır. "
    "İlk 6 (:02–:27) saatin kimliğini kurar; son 6'da her yeni çekilişten sonra bir sonraki hedef tekrar değerlendirilir. "
    "Kilitli kural yoksa kupon basılmaz (ABSTAIN)."
)


st.divider()
st.subheader("📥 YENİ ÇEKİLİŞ GİRİŞİ")
st.caption(
    "İlk kullanımda aynı saatin 6 çekilişini (:02–:27) tek seferde yapıştır. "
    "Sonra :32, :37, :42, :47, :52 ve :57 sonuçlarını birer birer ekle. "
    "Hiçbir veri sen onay vermeden GitHub'a yazılmaz."
)

paste_text=st.text_area(
    "Çekilişi/çekilişleri buraya aynen yapıştır",
    height=300,
    placeholder="Çekiliş no:59187\n30.09.2026-19:27\n1\n2\n...\nDetaylar",
    key="live_paste_text"
)

if st.button("🔍 ÖNCE KONTROL ET",type="primary",width="stretch"):
    recs,errs=parse_pasted_draws(paste_text)
    st.session_state["pending_records"]=recs
    st.session_state["pending_errors"]=errs

if "pending_records" in st.session_state:
    precs=st.session_state.get("pending_records",[])
    perrs=st.session_state.get("pending_errors",[])
    if perrs:
        for e in perrs:
            st.error(e)
    elif precs:
        mode="İLK6 PAKETİ" if len(precs)==6 else "TEK CANLI ÇEKİLİŞ"
        st.success(f"✅ {mode} doğru okundu: {len(precs)} çekiliş / {len(precs)*20} sayı hücresi")
        preview=pd.DataFrame([
            {
                "Çekiliş":r[0],
                "Tarih-Saat":r[1].strftime("%d.%m.%Y %H:%M"),
                "20 sayı":" ".join(map(str,r[2]))
            } for r in precs
        ])
        st.dataframe(preview,width="stretch",hide_index=True)

        cfg_now=github_config()
        if not cfg_now["configured"]:
            st.error("GitHub kayıt kapalı: Secrets içinde GITHUB_TOKEN ve GITHUB_REPO bulunamadı.")
        else:
            try:
                remote_raw_check,remote_sha_check,remote_cfg_check=github_fetch_veri()
                add_check,skip_check,conf_check,_=validate_against_remote(precs,remote_raw_check)
                if conf_check:
                    for e in conf_check:
                        st.error("⛔ "+e)
                else:
                    if skip_check:
                        st.info("Zaten kayıtlı, tekrar yazılmayacak: " + ", ".join("#"+str(x) for x in skip_check))
                    st.write(
                        f"GitHub'a eklenecek yeni çekiliş: **{len(add_check)}** "
                        f"| mevcut dosya SHA: **{remote_sha_check[:10]}**"
                    )
                    confirm=st.checkbox(
                        "Gösterilen çekilişlerin doğru olduğunu kontrol ettim.",
                        key="github_confirm_checkbox"
                    )
                    if st.button(
                        "✅ KONTROL EDİLENİ GITHUB'A KAYDET",
                        disabled=not confirm,
                        width="stretch"
                    ):
                        res=github_commit_records(precs)
                        if res.get("ok"):
                            st.session_state["save_notice"]=res
                            st.session_state.pop("pending_records",None)
                            st.session_state.pop("pending_errors",None)
                            st.cache_data.clear()
                            st.session_state.pop("analysis",None)
                            st.rerun()
                        else:
                            for e in res.get("conflicts",["Kayıt başarısız."]):
                                st.error("⛔ "+e)
            except Exception as e:
                st.error(f"GitHub kontrolü yapılamadı: {e}")

if "save_notice" in st.session_state:
    note=st.session_state.pop("save_notice")
    st.success(
        "✅ "+note.get("message","GitHub kaydı tamamlandı.")+
        (f" | commit {note.get('commit')}" if note.get("commit") else "")
    )
    if note.get("skipped"):
        st.info("Tekrar yazılmayan mevcut kayıtlar: "+", ".join("#"+str(x) for x in note["skipped"]))

st.divider()

# Canlı motoru her sayfa açılışında güncel veriyle çalıştır.
live=build_live_motor(df_live,digest)
st.subheader("🎯 CANLI KUPON MOTORU")
if live.get("ready"):
    st.write(
        f"Son veri: **#{live['draw_id']} — {live['date']} {live['hour']}:{live['minute']}** "
        f"| İlk6: **{'HAZIR' if live['first6_complete'] else 'BEKLİYOR'}** "
        f"| ZERO6: **{live.get('zero6_band') or '-'}**"
    )
    if live.get("q6") is not None:
        st.caption("İlk6 kontenjanı [0/6..6/6] = " + str(live["q6"]))
    if live.get("signals"):
        for sig in live["signals"]:
            st.success(
                f"🔥 {sig['branch']} AÇIK → hedef :{sig['target']} | "
                f"5'li havuz: {sig['pool5']} | 4'lü kupon: {sig['coupon4']}"
            )
            det=pd.DataFrame(sig["detail"])
            st.dataframe(det,width="stretch",hide_index=True)
    else:
        st.warning(live.get("message","ABSTAIN"))
else:
    st.warning(live.get("message","Canlı motor hazır değil."))

health=df_live.assign(day=df_live.time.dt.strftime("%d.%m.%Y")).groupby("day").size().reset_index(name="draws")
health["status"]=np.where(health.draws==217,"TAM","EKSİK/FAZLA")
with st.expander("📦 Veri sağlık kontrolü"):
    st.dataframe(health,width="stretch",hide_index=True)
    st.write(f"Mükerrer temizlenen: **{dup}** • Parse reddi: **{rejected}**")

if st.button("🚀 GÜN GÜN / ÇEKİLİŞ ÇEKİLİŞ ANALİZİ BAŞLAT",type="primary",width="stretch"):
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

    pools,snaps,status_agg,stage_agg,validation_agg,branch_agg,pair_agg,triple_agg,why_agg,core_agg=aggregate_all(results)
    report=make_master_report(df,rejected,dup,results,status_agg,stage_agg,validation_agg,branch_agg,pair_agg,triple_agg,why_agg,core_agg,source,digest)

    st.session_state["analysis"]=(results,status_agg,stage_agg,validation_agg,branch_agg,pair_agg,triple_agg,why_agg,core_agg,report)
    msg.success("✅ Bütün günler ve bütün çekiliş güncellemeleri tamamlandı.")
    prog.empty()

if "analysis" in st.session_state:
    results,status_agg,stage_agg,validation_agg,branch_agg,pair_agg,triple_agg,why_agg,core_agg,report=st.session_state["analysis"]

    # Mobilde sekmeler sağa kayabildiği için indirme butonunu doğrudan üste koy.
    st.success("✅ Analiz tamamlandı — dosyan hazır.")
    report_bytes = report.encode("utf-8-sig")

    # 1) Normal TXT indirme
    st.download_button(
        "⬇️ TXT İNDİR",
        data=report_bytes,
        file_name="HIZLI_ON_DINAMIK_YASAM_HAVUZLARI_25AGUSTOS_29EYLUL.txt",
        mime="text/plain; charset=utf-8",
        width="stretch",
        key="download_top_txt",
        on_click="ignore"
    )

    # 2) Mobil tarayıcılar için ZIP yedeği
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "HIZLI_ON_DINAMIK_YASAM_HAVUZLARI_25AGUSTOS_29EYLUL.txt",
            report_bytes
        )
    zip_bytes = zip_buf.getvalue()

    st.download_button(
        "📦 ZIP OLARAK İNDİR — MOBİL YEDEK",
        data=zip_bytes,
        file_name="HIZLI_ON_ANALIZ.zip",
        mime="application/zip",
        width="stretch",
        key="download_top_zip",
        on_click="ignore"
    )

    # 3) Streamlit download_button çalışmazsa tarayıcının doğrudan açacağı klasik link
    zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
    st.markdown(
        f"""
        <a href="data:application/zip;base64,{zip_b64}"
           download="HIZLI_ON_ANALIZ.zip"
           style="display:block;text-align:center;padding:14px;border:2px solid #444;
                  border-radius:10px;text-decoration:none;font-weight:700;margin-top:8px;">
           🔗 DOĞRUDAN ZIP İNDİRME LİNKİ
        </a>
        """,
        unsafe_allow_html=True
    )
    st.caption("TXT düğmesi telefonda çalışmazsa ZIP düğmesine; o da çalışmazsa DOĞRUDAN ZIP İNDİRME LİNKİNE bas.")
    st.caption("Bu dosyada gün gün, çekiliş çekiliş, statüler, ilk6+canlı, istikrar, 4 Hat Kazısı, prev1–3 yaşamı ve 3/4'lü çekirdek testi birlikte bulunur.")

    t1,t2,t3,t4,t5,t6,t7=st.tabs(["🔥 Statüler","⏱️ İlk6 + Canlı","✅ İstikrar","🧬 4 Hat Kazısı","🎯 Çekirdek","📅 Günler","📄 Tek TXT"])

    with t1:
        st.caption("5'li havuzların tüm dönem aktivasyon özeti.")
        st.dataframe(status_agg,width="stretch",hide_index=True)

    with t2:
        st.caption(":27 sonucu sonrası :32, :32 sonrası :37 ... canlı havuz davranışı; ilk6 0/6 karakteriyle birlikte.")
        st.dataframe(stage_agg,width="stretch",hide_index=True)

    with t3:
        st.caption("Kronolojik iki yarıda da rastgele 5'li referansının üstünde kalan adaylar.")
        if validation_agg is not None and not validation_agg.empty:
            st.dataframe(validation_agg[validation_agg.stable_candidate==True],width="stretch",hide_index=True)
        else:
            st.info("İstikrar adayı bulunmadı.")

    with t4:
        st.caption("Dört sabit hatta 5'li havuzun pozisyon bazlı 2'li/3'lü alt aileleri.")
        st.dataframe(branch_agg,width="stretch",hide_index=True)
        st.subheader("Pozisyon çiftleri")
        st.dataframe(pair_agg.sort_values(["branch","both_hit_pct"],ascending=[True,False]),width="stretch",hide_index=True)
        st.subheader("Pozisyon üçlüleri")
        st.dataframe(triple_agg.sort_values(["branch","all3_hit_pct"],ascending=[True,False]),width="stretch",hide_index=True)

    with t5:
        st.subheader("Önceki 1–3 çekiliş yaşamı")
        st.caption("Aynı 5'linin üyesi; snapshot dahil son 3 çekilişte 0/1/2/3 kez aktif olmuşsa sonraki çekilişte ne yapıyor?")
        st.dataframe(why_agg,width="stretch",hide_index=True)
        st.subheader("3'lü / 4'lü çekirdek — kronolojik H2 testi")
        st.caption("Pozisyonlar yalnız ilk 18 günde öğrenilir; son 18 günde değiştirilmeden test edilir.")
        st.dataframe(core_agg,width="stretch",hide_index=True)

    with t6:
        rows=[]
        for d in results:
            rows.append({
                "Gün":d["date"],"Çekiliş":d["draw_count"],
                "Snapshot":len(d["snapshots"]),
                "5'li havuz kaydı":len(d["pools"])
            })
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)

    with t7:
        st.success("Tek ana araştırma TXT'si hazır.")
        with st.expander("Rapor önizleme"):
            st.text(report[:50000])
