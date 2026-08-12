from pathlib import Path
from datetime import datetime, timedelta, time as dtime
import base64
import re

import numpy as np
import pandas as pd
import requests
import streamlit as st

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

st.set_page_config(
    page_title="Hızlı On — FINAL Uzman V2",
    page_icon="🎯",
    layout="wide",
)

BASE_FILE = Path(__file__).with_name("veri.txt")

# ============================================================
# DONDURULMUŞ ÇEKİRDEK
# ============================================================
# BLOK SIKI V3:
#   Dinamik KONUŞ + Sinyal <= 9 + KAYMA olay <= 0.82
#   + Güven >= 91 + DEVAM olay >= 0.80
#
# TEKRAR SIKI V3:
#   V2: streak >= 3 + trans_same 0.247–0.269
#   V3 ek freni: trans_same >= 0.26136
#
# Bu eşikler uygulama içinden değiştirilemez.
TEKRAR_V2_TRANS_MIN = 0.247
TEKRAR_V2_TRANS_MAX = 0.269
TEKRAR_V2_MIN_STREAK = 3
TEKRAR_V3_TRANS_MIN = 0.26136

BLOCK_NEIGHBORS = 70
BLOCK_SELECTOR_MIN_HISTORY = 60
BLOCK_SELECTOR_WINDOW = 120
BLOCK_SELECTOR_MIN_BUCKET = 12


# ============================================================
# VERİ OKUMA / YAZMA
# ============================================================
def parse_line(raw):
    parts = str(raw).strip().split(";")
    if len(parts) != 4:
        return None
    try:
        no = int(parts[0])
        dt = datetime.strptime(f"{parts[1]} {parts[2]}", "%d.%m.%Y %H:%M")
        nums = [int(x) for x in re.findall(r"\d+", parts[3])]
    except Exception:
        return None
    if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
        return None
    return [no, dt, sorted(nums)]


def parse_text(text):
    rows, invalid = [], []
    for i, raw in enumerate(str(text).splitlines(), 1):
        if not raw.strip():
            continue
        row = parse_line(raw)
        if row is None:
            invalid.append(i)
        else:
            rows.append(row)
    df = pd.DataFrame(rows, columns=["Cekilis_No", "DT", "Nums"])
    if not df.empty:
        df = (
            df.drop_duplicates("Cekilis_No", keep="last")
              .sort_values("Cekilis_No")
              .reset_index(drop=True)
        )
    return df, invalid


def to_text(df):
    lines = []
    for _, r in df.sort_values("Cekilis_No").iterrows():
        nums = ",".join(str(int(x)) for x in r["Nums"])
        lines.append(
            f"{int(r['Cekilis_No'])};"
            f"{pd.Timestamp(r['DT']).strftime('%d.%m.%Y')};"
            f"{pd.Timestamp(r['DT']).strftime('%H:%M')};"
            f"{nums}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def parse_20_numbers(text):
    vals = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", str(text))]
    # Eğer başlık/tarih/saat yapıştırılmışsa yalnız tek başına sayı satırlarını da dene.
    if len(vals) != 20:
        cleaned = re.sub(r"(?mi)^\s*Çekiliş\s*no\s*:\s*\d+\s*$", " ", str(text))
        cleaned = re.sub(r"(?mi)^\s*\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}:\d{2}\s*$", " ", cleaned)
        vals = [int(x) for x in re.findall(r"(?m)^\s*(\d{1,2})\s*$", cleaned)]
    vals = [x for x in vals if 1 <= x <= 80]
    if len(vals) == 20 and len(set(vals)) == 20:
        return sorted(vals)
    return None


def parse_bulk_results(text):
    """Hem no;date;time;nums hem de Çekiliş no:/tarih-saat bloklarını kabul eder."""
    text = str(text or "")
    rows = []

    # 1) Kanonik satırlar
    for raw in text.splitlines():
        p = parse_line(raw)
        if p is not None:
            rows.append(p)

    # 2) Web/mesaj blokları: Çekiliş no: X ... DD.MM.YYYY - HH:MM ... 20 sayı
    block_pat = re.compile(
        r"Çekiliş\s*no\s*:\s*(\d+)\s*"
        r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})\s*"
        r"(.*?)(?=Çekiliş\s*no\s*:|\Z)",
        re.I | re.S,
    )
    for m in block_pat.finditer(text):
        try:
            no = int(m.group(1))
            dt = datetime.strptime(m.group(2) + " " + m.group(3), "%d.%m.%Y %H:%M")
            nums = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", m.group(4))]
            if len(nums) == 20 and len(set(nums)) == 20:
                rows.append([no, dt, sorted(nums)])
        except Exception:
            pass

    if not rows:
        return pd.DataFrame(columns=["Cekilis_No", "DT", "Nums"])
    return (
        pd.DataFrame(rows, columns=["Cekilis_No", "DT", "Nums"])
        .drop_duplicates("Cekilis_No", keep="last")
        .sort_values("Cekilis_No")
        .reset_index(drop=True)
    )


def merge_rows(base_df, add_df):
    if add_df is None or add_df.empty:
        return base_df.copy()
    out = pd.concat([base_df, add_df], ignore_index=True)
    out = (
        out.drop_duplicates("Cekilis_No", keep="last")
           .sort_values("Cekilis_No")
           .reset_index(drop=True)
    )
    return out


def next_draw_dt(dt):
    dt = pd.Timestamp(dt).to_pydatetime()
    if dt.hour == 1 and dt.minute == 2:
        return (dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    cand = dt + timedelta(minutes=5)
    if (cand.hour == 1 and cand.minute > 2) or (2 <= cand.hour < 7):
        return (dt + timedelta(days=1)).replace(hour=7, minute=2, second=0, microsecond=0)
    return cand


# ============================================================
# GITHUB KALICI KAYIT — SECRETS VARSA
# ============================================================
def github_settings():
    try:
        gh = st.secrets["github"]
        return {
            "token": gh["token"],
            "owner": gh.get("owner", "gozlekakif-alt"),
            "repo": gh.get("repo", "hizli-on-analiz-motoru"),
            "branch": gh.get("branch", "main"),
            "path": gh.get("data_path", "veri.txt"),
        }
    except Exception:
        return None


def github_headers(token):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_get(settings):
    url = f"https://api.github.com/repos/{settings['owner']}/{settings['repo']}/contents/{settings['path']}"
    r = requests.get(
        url,
        headers=github_headers(settings["token"]),
        params={"ref": settings["branch"]},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"GitHub veri.txt okunamadı: {r.status_code}")
    payload = r.json()
    content = base64.b64decode(payload["content"]).decode("utf-8", errors="ignore")
    return content, payload["sha"]


def github_save(settings, text, message):
    _, sha = github_get(settings)
    url = f"https://api.github.com/repos/{settings['owner']}/{settings['repo']}/contents/{settings['path']}"
    payload = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": settings["branch"],
    }
    r = requests.put(
        url,
        headers=github_headers(settings["token"]),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub kayıt hatası: {r.status_code} {r.text[:220]}")
    return r.json()


def persist_pool(df, message="Hızlı On veri havuzu güncelleme"):
    text = to_text(df)
    # Çalışan oturumda hemen güncelle.
    st.session_state["pool_text"] = text
    try:
        BASE_FILE.write_text(text, encoding="utf-8")
    except Exception:
        pass

    gh = github_settings()
    if gh:
        try:
            github_save(gh, text, message)
            return True, "Ana havuz GitHub veri.txt dosyasına kalıcı kaydedildi."
        except Exception as e:
            return False, f"Oturum havuzu güncellendi; GitHub kaydı başarısız: {e}"
    return False, "Oturum havuzu güncellendi. GitHub Secrets bağlı olmadığı için kalıcı GitHub kaydı yapılmadı; aşağıdan veri.txt indirip repoya koyabilirsin."


# ============================================================
# ORTAK HAFİF MOTOR
# ============================================================
class UnifiedEngine:
    def __init__(self, df):
        self.df = df.reset_index(drop=True).copy()
        self.N = len(self.df)
        self.draw_nos = self.df["Cekilis_No"].astype(int).to_numpy()
        self.dts = list(pd.to_datetime(self.df["DT"]))
        self.A = np.zeros((self.N, 80), dtype=np.int8)
        for i, nums in enumerate(self.df["Nums"]):
            self.A[i, np.asarray(nums, dtype=int) - 1] = 1

        self.cumT = np.zeros((self.N, 80, 80), dtype=np.uint16)
        self.cumS = np.zeros((self.N, 80), dtype=np.uint16)
        T = np.zeros((80, 80), dtype=np.uint16)
        S = np.zeros(80, dtype=np.uint16)
        for j in range(self.N - 1):
            if self.draw_nos[j + 1] == self.draw_nos[j] + 1:
                src = np.where(self.A[j] == 1)[0]
                dst = np.where(self.A[j + 1] == 1)[0]
                S[src] += 1
                T[np.ix_(src, dst)] += 1
            self.cumT[j + 1] = T
            self.cumS[j + 1] = S


# ============================================================
# BLOK — DONDURULMUŞ V3 ÇEKİRDEĞİ
# ============================================================
def _runs(nums):
    xs = sorted(set(map(int, nums)))
    out, cur = [], []
    for x in xs:
        if not cur or x == cur[-1] + 1:
            cur.append(x)
        else:
            if len(cur) >= 2:
                out.append(cur)
            cur = [x]
    if len(cur) >= 2:
        out.append(cur)
    return out


def _bf(nums):
    ss = set(map(int, nums))
    rr = _runs(ss)
    rn = set(x for r in rr for x in r)
    edges = set()
    for r in rr:
        if r[0] > 1:
            edges.add(r[0] - 1)
        if r[-1] < 80:
            edges.add(r[-1] + 1)
    bands = [sum(10*b + 1 <= x <= 10*b + 10 for x in ss) for b in range(8)]
    return {
        "set": ss,
        "runs": rr,
        "run_nums": rn,
        "edges": edges,
        "pairs": sum(len(r)-1 for r in rr),
        "triples": sum(max(0, len(r)-2) for r in rr),
        "max_run": max([len(r) for r in rr], default=1),
        "bands": bands,
        "dense": sum(c >= 4 for c in bands),
        "run_count": len(rr),
    }


def _bsim(a, b):
    band_dist = sum(abs(x-y) for x,y in zip(a["bands"], b["bands"])) / 20.0
    z = (
        .18 * min(abs(a["pairs"] - b["pairs"]) / 5, 1)
        + .15 * min(abs(a["triples"] - b["triples"]) / 3, 1)
        + .15 * min(abs(a["max_run"] - b["max_run"]) / 3, 1)
        + .10 * min(abs(a["dense"] - b["dense"]) / 3, 1)
        + .10 * min(abs(a["run_count"] - b["run_count"]) / 5, 1)
        + .32 * min(band_dist, 1)
    )
    return max(0.0, 1.0-z)


def _behavior_labels(prev_nums, next_nums):
    pf = _bf(prev_nums)
    nf = _bf(next_nums)
    nxt = nf["set"]

    continuation = nxt & pf["run_nums"]
    growth = nxt & pf["edges"]

    near2 = set()
    for n in pf["run_nums"]:
        for d in (-2,-1,1,2):
            q=n+d
            if 1 <= q <= 80:
                near2.add(q)
    shift = (nxt & near2) - continuation - growth
    birth = set(nf["run_nums"]) - continuation - growth - shift

    return {
        "DEVAM": continuation,
        "BÜYÜME": growth,
        "KAYMA": shift,
        "DOĞUM": birth,
        "next_block_nums": nf["run_nums"],
    }


def block_predict_v2(engine, t, k=10, neighbors=BLOCK_NEIGHBORS):
    if t < 100:
        return list(range(1,k+1)), pd.DataFrame(), {
            "signal":0,"confidence":0.0,"neighbors":0,"runs":[],"avg":0.0,
            "event_rate":{"DEVAM":0,"BÜYÜME":0,"KAYMA":0,"DOĞUM":0},
            "weights":{"DEVAM":0,"BÜYÜME":0,"KAYMA":0,"DOĞUM":0},
        }

    current_nums = (np.where(engine.A[t-1] == 1)[0] + 1).tolist()
    cf = _bf(current_nums)

    cand=[]
    for j in range(max(20,t-900),t-1):
        prev_j=(np.where(engine.A[j]==1)[0]+1).tolist()
        jf=_bf(prev_j)
        sim=_bsim(cf,jf)
        if cf["max_run"]==jf["max_run"]: sim += .05
        if cf["pairs"]==jf["pairs"]: sim += .04
        if cf["run_count"]==jf["run_count"]: sim += .03
        cand.append((sim,j))
    cand.sort(reverse=True)
    chosen=cand[:min(neighbors,len(cand))]

    channel={name:np.zeros(80,dtype=float) for name in ["DEVAM","BÜYÜME","KAYMA","DOĞUM"]}
    event_hits={name:0.0 for name in channel}
    total_w=0.0

    for sim,j in chosen:
        prev_j=(np.where(engine.A[j]==1)[0]+1).tolist()
        next_j=(np.where(engine.A[j+1]==1)[0]+1).tolist()
        pf=_bf(prev_j)
        labels=_behavior_labels(prev_j,next_j)
        w=max(sim,.02)**3

        for name in channel:
            if labels[name]:
                event_hits[name]+=w

        for r in pf["runs"]:
            for pos,n in enumerate(r):
                if n in labels["DEVAM"]:
                    for cr in cf["runs"]:
                        if len(cr)==len(r) and pos < len(cr):
                            channel["DEVAM"][cr[pos]-1]+=w

        hist_left=set(r[0]-1 for r in pf["runs"] if r[0]>1)
        hist_right=set(r[-1]+1 for r in pf["runs"] if r[-1]<80)
        left_hit=len(hist_left & labels["BÜYÜME"])
        right_hit=len(hist_right & labels["BÜYÜME"])
        for cr in cf["runs"]:
            if cr[0]>1:
                channel["BÜYÜME"][cr[0]-2]+=w*(.35+left_hit)
            if cr[-1]<80:
                channel["BÜYÜME"][cr[-1]]+=w*(.35+right_hit)

        for hn in labels["KAYMA"]:
            nearest=min(pf["run_nums"],key=lambda x:abs(x-hn)) if pf["run_nums"] else None
            if nearest is None:
                continue
            delta=hn-nearest
            if delta not in (-2,-1,1,2):
                continue
            for cn in cf["run_nums"]:
                q=cn+delta
                if 1<=q<=80:
                    channel["KAYMA"][q-1]+=w/max(len(cf["run_nums"]),1)

        for n in labels["DOĞUM"]:
            channel["DOĞUM"][n-1]+=w
        total_w+=w

    def norm(a):
        a=np.asarray(a,dtype=float)
        lo,hi=float(a.min()),float(a.max())
        return (a-lo)/(hi-lo) if hi>lo else np.zeros_like(a)

    for name in channel:
        channel[name]=norm(channel[name])

    event_rate={name:float(event_hits[name]/max(total_w,1e-9)) for name in channel}

    recent=engine.A[max(0,t-120):t]
    recent_block=np.zeros(80,dtype=float)
    if len(recent):
        for row in recent:
            b=_bf(np.where(row==1)[0]+1)
            for n in b["run_nums"]:
                recent_block[n-1]+=1
        recent_block=norm(recent_block)
    channel["DOĞUM"]=.68*channel["DOĞUM"]+.32*recent_block

    weights={
        "DEVAM":.18+.32*event_rate["DEVAM"],
        "BÜYÜME":.15+.30*event_rate["BÜYÜME"],
        "KAYMA":.10+.22*event_rate["KAYMA"],
        "DOĞUM":.16+.30*event_rate["DOĞUM"],
    }
    sw=sum(weights.values())
    weights={k0:v/sw for k0,v in weights.items()}

    score=sum(weights[name]*channel[name] for name in channel)
    support_count=np.zeros(80,dtype=float)
    for name in channel:
        support_count+=(channel[name]>=.55).astype(float)
    score=score+.06*np.minimum(support_count,3)/3.0

    order=np.argsort(-score)
    pred=(order[:k]+1).astype(int).tolist()

    avg_sim=float(np.mean([x[0] for x in chosen])) if chosen else 0.0
    event_stability=1.0-float(np.std(list(event_rate.values())))
    top_margin=float(score[order[0]]-score[order[min(k,79)]]) if len(order)>k else 0.0
    conf=np.clip(
        100*(.38*max(0,avg_sim-.35)/.65 + .32*event_stability + .30*min(top_margin/.35,1)),
        0,100
    )

    signal=cf["pairs"]+2*cf["triples"]+max(0,cf["max_run"]-2)
    rows=[]
    for i in range(80):
        rows.append({
            "Sayı":i+1,
            "Final Blok Puanı":round(float(score[i])*100,2),
            "DEVAM":round(float(channel["DEVAM"][i])*100,2),
            "BÜYÜME":round(float(channel["BÜYÜME"][i])*100,2),
            "KAYMA":round(float(channel["KAYMA"][i])*100,2),
            "DOĞUM":round(float(channel["DOĞUM"][i])*100,2),
            "Kanal Desteği":int(support_count[i]),
        })
    table=pd.DataFrame(rows).sort_values(
        ["Final Blok Puanı","Kanal Desteği"],ascending=[False,False]
    ).reset_index(drop=True)

    info={
        "signal":int(signal),
        "confidence":round(float(conf),1),
        "neighbors":len(chosen),
        "runs":cf["runs"],
        "avg":round(avg_sim,3),
        "event_rate":{k0:round(v,3) for k0,v in event_rate.items()},
        "weights":{k0:round(v,3) for k0,v in weights.items()},
    }
    return pred,table,info


def block_compare_history(engine, tests=250, min_train_draws=60):
    """Geçmişten geleceğe BLOK yeniden-sıralama; her hedefte yalnız önceki gerçekler öğrenilir."""
    feat_cols=["DEVAM","BÜYÜME","KAYMA","DOĞUM","Kanal Desteği"]
    history=[]
    rows=[]
    start=max(120,len(engine.A)-int(tests))

    for t in range(start,len(engine.A)):
        _,table,info=block_predict_v2(engine,t,k=15)
        actual=set((np.where(engine.A[t]==1)[0]+1).tolist())
        cur=table.head(15).copy().reset_index(drop=True)
        cur["Gerçek"]=cur["Sayı"].astype(int).isin(actual).astype(int)

        old10=cur.head(10)["Sayı"].astype(int).tolist()
        new10=old10[:]
        trained=False

        if len(history)>=min_train_draws:
            hist=pd.concat(history[-250:],ignore_index=True)
            if hist["Gerçek"].nunique()==2:
                reranker=make_pipeline(
                    StandardScaler(),
                    LogisticRegression(max_iter=500,C=.20,class_weight=None)
                )
                reranker.fit(hist[feat_cols].astype(float),hist["Gerçek"].astype(int))
                p=reranker.predict_proba(cur[feat_cols].astype(float))[:,1]
                cur2=cur.copy()
                cur2["Yeni Olasılık"]=p
                cur2=cur2.sort_values(
                    ["Yeni Olasılık","Final Blok Puanı","Sayı"],
                    ascending=[False,False,True]
                )
                new10=cur2.head(10)["Sayı"].astype(int).tolist()
                trained=True

        rows.append({
            "Index":t,
            "Çekiliş":int(engine.draw_nos[t]),
            "Eğitim aktif":trained,
            "ESKİ Top10":len(set(old10)&actual),
            "YENİ Top10":len(set(new10)&actual),
            "Fark":len(set(new10)&actual)-len(set(old10)&actual),
            "YENİ sayılar":" - ".join(map(str,new10)),
            "Sinyal":int(info["signal"]),
            "Güven":float(info["confidence"]),
            "Ort benzerlik":float(info["avg"]),
            "DEVAM olay":float(info["event_rate"]["DEVAM"]),
            "BÜYÜME olay":float(info["event_rate"]["BÜYÜME"]),
            "KAYMA olay":float(info["event_rate"]["KAYMA"]),
            "DOĞUM olay":float(info["event_rate"]["DOĞUM"]),
        })
        history.append(cur[feat_cols+["Gerçek"]].copy())
    return pd.DataFrame(rows)


def block_selector_for_current(history_cmp, current_info):
    feature_cols=["Sinyal","Güven","Ort benzerlik","DEVAM olay","BÜYÜME olay","KAYMA olay","DOĞUM olay"]
    active=history_cmp[history_cmp["Eğitim aktif"]==True].copy()
    if len(active)<BLOCK_SELECTOR_MIN_HISTORY:
        return False,0,0.0

    hist=active.tail(BLOCK_SELECTOR_WINDOW)
    X=hist[feature_cols].astype(float).to_numpy()
    x=np.array([
        current_info["signal"],
        current_info["confidence"],
        current_info["avg"],
        current_info["event_rate"]["DEVAM"],
        current_info["event_rate"]["BÜYÜME"],
        current_info["event_rate"]["KAYMA"],
        current_info["event_rate"]["DOĞUM"],
    ],dtype=float)
    mu=X.mean(0)
    sd=X.std(0)
    sd[sd<1e-9]=1.0
    dist=np.sqrt(np.mean(((X-x)/sd)**2,axis=1))
    k=min(max(BLOCK_SELECTOR_MIN_BUCKET,int(round(len(hist)*.20))),len(hist))
    nearest=np.argsort(dist)[:k]
    advantage=float(hist.iloc[nearest]["Fark"].mean())
    return bool(k>=BLOCK_SELECTOR_MIN_BUCKET and advantage>0),int(k),advantage


def block_live_v3(engine):
    t=len(engine.A)
    _,table,info=block_predict_v2(engine,t,k=15)
    feat_cols=["DEVAM","BÜYÜME","KAYMA","DOĞUM","Kanal Desteği"]
    cur=table.head(15).copy().reset_index(drop=True)

    # Öğrenme: mevcut hedef için reranker yalnız geçmiş bilinen çekilişlerden eğitilir.
    train_rows=[]
    start=max(120,t-250)
    for h in range(start,t):
        if h<=0 or engine.draw_nos[h] != engine.draw_nos[h-1]+1:
            continue
        _,htab,_=block_predict_v2(engine,h,k=15)
        actual=set((np.where(engine.A[h]==1)[0]+1).tolist())
        z=htab.head(15).copy()
        z["Gerçek"]=z["Sayı"].astype(int).isin(actual).astype(int)
        train_rows.append(z[feat_cols+["Gerçek"]])

    new10=cur.head(10)["Sayı"].astype(int).tolist()
    learned=False
    if len(train_rows)>=60:
        hist=pd.concat(train_rows[-250:],ignore_index=True)
        if hist["Gerçek"].nunique()==2:
            model=make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=500,C=.20,class_weight=None)
            )
            model.fit(hist[feat_cols].astype(float),hist["Gerçek"].astype(int))
            p=model.predict_proba(cur[feat_cols].astype(float))[:,1]
            cur["Yeni Olasılık"]=p
            cur=cur.sort_values(
                ["Yeni Olasılık","Final Blok Puanı","Sayı"],
                ascending=[False,False,True]
            ).reset_index(drop=True)
            new10=cur.head(10)["Sayı"].astype(int).tolist()
            learned=True

    # Dinamik seçici için yalnız geçmiş karşılaştırma sonuçları.
    cmp=block_compare_history(engine,tests=min(250,max(0,t-120)))
    dynamic,k,adv=block_selector_for_current(cmp,info) if len(cmp) else (False,0,0.0)

    strict_v2=(
        dynamic
        and float(info["signal"])<=9.0
        and float(info["event_rate"]["KAYMA"])<=0.82
    )
    strict_v3=(
        strict_v2
        and float(info["confidence"])>=91.0
        and float(info["event_rate"]["DEVAM"])>=0.80
    )
    picks=new10 if strict_v3 else []
    return picks,cur,info,{
        "Öğrenme aktif":learned,
        "Dinamik KONUŞ":dynamic,
        "Geçmiş benzer olay":k,
        "Beklenen avantaj":adv,
        "SIKI V3":strict_v3,
    }


# ============================================================
# TEKRAR — DONDURULMUŞ SIKI V3
# ============================================================
def repeat_features(engine,t):
    if t<40:
        return pd.DataFrame()
    A=engine.A
    prev_idx=np.where(A[t-1]==1)[0]
    rows=[]

    overlaps=[]
    for j in range(1,t):
        if engine.draw_nos[j]==engine.draw_nos[j-1]+1:
            overlaps.append(int(np.sum(A[j]*A[j-1])))
    global_repeat=float(np.mean(overlaps[-200:]))/20.0 if overlaps else .25

    TT=engine.cumT[t-1].astype(float)
    SS=engine.cumS[t-1].astype(float)
    target_hour=engine.dts[t-1].hour
    H=A[max(0,t-160):t].astype(float)
    freq=H.sum(0)

    for idx in prev_idx:
        n=int(idx+1)
        cases=hits=recent_cases=recent_hits=0

        for j in range(max(0,t-350),t-1):
            if engine.draw_nos[j+1]!=engine.draw_nos[j]+1:
                continue
            if A[j,idx]:
                cases+=1
                hits+=int(A[j+1,idx])
                if j>=t-120:
                    recent_cases+=1
                    recent_hits+=int(A[j+1,idx])

        p_long=(hits+5*global_repeat)/max(cases+5,1)
        p_recent=(recent_hits+4*p_long)/max(recent_cases+4,1)

        streak=0
        for j in range(t-1,-1,-1):
            if A[j,idx]:
                streak+=1
            else:
                break

        f5=float(A[max(0,t-5):t,idx].mean())
        f20=float(A[max(0,t-20):t,idx].mean())

        lifts=[]
        if len(H):
            for s in prev_idx:
                if s==idx:
                    continue
                both=float(np.sum(H[:,idx]*H[:,s]))
                expected=max((freq[idx]*freq[s])/max(len(H),1),1e-6)
                lifts.append(min(both/expected,3.0))
        pair_lift=float(np.mean(lifts)) if lifts else 1.0
        trans_same=float(TT[idx,idx]/SS[idx]) if SS[idx]>0 else 0.0

        hour_cases=hour_hits=0
        for j in range(1,t):
            if engine.draw_nos[j]!=engine.draw_nos[j-1]+1:
                continue
            if engine.dts[j].hour!=target_hour:
                continue
            if A[j-1,idx]:
                hour_cases+=1
                hour_hits+=int(A[j,idx])
        p_hour=(hour_hits+3*p_long)/max(hour_cases+3,1)

        rows.append({
            "Sayı":n,"streak":int(streak),"trans_same":float(trans_same),
            "p_recent":float(p_recent),"p_long":float(p_long),"p_hour":float(p_hour),
            "pair_lift":float(pair_lift),"f5":f5,"f20":f20,"cases":int(cases),
            "recent_cases":int(recent_cases),"hour_cases":int(hour_cases),
            "global_repeat":float(global_repeat),
        })
    return pd.DataFrame(rows)


def repeat_v3_candidates(engine,t):
    tab=repeat_features(engine,t)
    if tab.empty:
        return [],tab
    tab=tab.copy()
    tab["V2_sinyal"]=(
        (tab["streak"]>=TEKRAR_V2_MIN_STREAK)
        & (tab["trans_same"]>=TEKRAR_V2_TRANS_MIN)
        & (tab["trans_same"]<=TEKRAR_V2_TRANS_MAX)
    )
    tab["V3_sinyal"]=tab["V2_sinyal"] & (tab["trans_same"]>=TEKRAR_V3_TRANS_MIN)
    picks=sorted(tab.loc[tab["V3_sinyal"],"Sayı"].astype(int).unique().tolist())
    return picks,tab.sort_values(["V3_sinyal","streak","trans_same"],ascending=[False,False,False])



# ============================================================
# UZMAN TAMAMLAMA LAB V1
# Çekirdek uzman sinyalini DEĞİŞTİRMEZ. Yalnız kalan koltukları
# geçmişteki birlikte-çıkış + güncel frekans desteğiyle sıralar.
# ============================================================
def completion_rank(engine, core, window=240):
    core=sorted(set(int(x) for x in core if 1<=int(x)<=80))
    t=len(engine.A)
    H=engine.A[max(0,t-window):t].astype(float)
    if len(H)==0:
        return pd.DataFrame(columns=["Sayı","Tamamlama Puanı","Çekirdekle Birlikte","Son20","Son60"])
    f20=engine.A[max(0,t-20):t].mean(0)
    f60=engine.A[max(0,t-60):t].mean(0)
    base=H.mean(0)
    rows=[]
    for n in range(1,81):
        if n in core: continue
        idx=n-1
        if core:
            cond=[]
            for c in core:
                ci=c-1
                mask=H[:,ci]>0
                cond.append(float(H[mask,idx].mean()) if mask.any() else float(base[idx]))
            joint=float(sum(cond)/len(cond))
        else:
            joint=float(base[idx])
        # Tamamlayıcı skor; çekirdekten ayrı tutulur.
        score=.55*joint+.25*float(f20[idx])+.20*float(f60[idx])
        rows.append({
            "Sayı":n,
            "Tamamlama Puanı":round(score*100,3),
            "Çekirdekle Birlikte":round(joint*100,3),
            "Son20":round(float(f20[idx])*100,3),
            "Son60":round(float(f60[idx])*100,3),
        })
    return pd.DataFrame(rows).sort_values(
        ["Tamamlama Puanı","Çekirdekle Birlikte","Sayı"],
        ascending=[False,False,True]
    ).reset_index(drop=True)

def build_completion_coupons(engine, block_picks, repeat_picks):
    core=sorted(set(block_picks)|set(repeat_picks))
    rank=completion_rank(engine,core)
    coupons={}
    for size in (3,4,5,7,10):
        if len(core)>=size:
            coupons[size]=core[:size]
        else:
            need=size-len(core)
            extra=rank.head(need)["Sayı"].astype(int).tolist()
            coupons[size]=sorted(core+extra)
    return core,rank,coupons


# ============================================================
# WALK-FORWARD TEST
# ============================================================
def run_final_walkforward(engine,test_count=750):
    valid=[
        t for t in range(140,len(engine.A))
        if engine.draw_nos[t]==engine.draw_nos[t-1]+1
    ]
    targets=valid[-min(int(test_count),len(valid)):]
    rows=[]

    # BLOK: bütün dönem üzerinde gerçek sızıntısız compare + seçici.
    block_cmp=block_compare_history(engine,tests=min(test_count,max(0,len(engine.A)-120)))
    if len(block_cmp):
        # Geçmiş satır bazlı dinamik seçiciyi aynen uygula.
        b=block_cmp.copy()
        b["Dinamik"]="PAS"
        b["Sıkı V3"]="PAS"
        active_idx=b.index[b["Eğitim aktif"]==True].tolist()
        feat=["Sinyal","Güven","Ort benzerlik","DEVAM olay","BÜYÜME olay","KAYMA olay","DOĞUM olay"]
        for pos,idx in enumerate(active_idx):
            past_idx=active_idx[max(0,pos-BLOCK_SELECTOR_WINDOW):pos]
            if len(past_idx)<BLOCK_SELECTOR_MIN_HISTORY:
                continue
            hist=b.loc[past_idx]
            cur=b.loc[idx]
            X=hist[feat].astype(float).to_numpy()
            x=cur[feat].astype(float).to_numpy()
            sd=X.std(0); sd[sd<1e-9]=1.0
            dist=np.sqrt(np.mean(((X-x)/sd)**2,axis=1))
            k=min(max(BLOCK_SELECTOR_MIN_BUCKET,int(round(len(hist)*.20))),len(hist))
            local=hist.iloc[np.argsort(dist)[:k]]
            adv=float(local["Fark"].mean())
            dynamic=(k>=BLOCK_SELECTOR_MIN_BUCKET and adv>0)
            if dynamic:
                b.at[idx,"Dinamik"]="KONUŞ"
            if (
                dynamic
                and float(cur["Sinyal"])<=9
                and float(cur["KAYMA olay"])<=.82
                and float(cur["Güven"])>=91
                and float(cur["DEVAM olay"])>=.80
            ):
                b.at[idx,"Sıkı V3"]="KONUŞ"
        block_map={int(r["Çekiliş"]):r for _,r in b.iterrows()}
    else:
        block_map={}

    for t in targets:
        actual=set((np.where(engine.A[t]==1)[0]+1).tolist())
        rpicks,_=repeat_v3_candidates(engine,t)
        rhit=len(set(rpicks)&actual)

        br=block_map.get(int(engine.draw_nos[t]))
        if br is not None and br["Sıkı V3"]=="KONUŞ":
            bpicks=[int(x) for x in re.findall(r"\d+",str(br["YENİ sayılar"]))][:10]
        else:
            bpicks=[]
        bhit=len(set(bpicks)&actual)

        rows.append({
            "Çekiliş":int(engine.draw_nos[t]),
            "Tarih/Saat":engine.dts[t].strftime("%d.%m.%Y %H:%M"),
            "BLOK karar":"KONUŞ" if bpicks else "PAS",
            "BLOK boyu":len(bpicks),
            "BLOK isabet":bhit,
            "BLOK tahmin":" - ".join(map(str,bpicks)),
            "TEKRAR karar":"KONUŞ" if rpicks else "PAS",
            "TEKRAR boyu":len(rpicks),
            "TEKRAR isabet":rhit,
            "TEKRAR tahmin":" - ".join(map(str,rpicks)),
            "Sızıntı":"TEMİZ",
        })
    return pd.DataFrame(rows)


# ============================================================
# OTURUM HAVUZU
# ============================================================
if "pool_text" not in st.session_state:
    if BASE_FILE.exists():
        st.session_state["pool_text"]=BASE_FILE.read_text(encoding="utf-8",errors="ignore")
    else:
        st.session_state["pool_text"]=""

df,invalid=parse_text(st.session_state["pool_text"])

st.title("🎯 HIZLI ON — FINAL UZMAN V2 + TAMAMLAMA LAB")
st.caption(
    "Dondurulmuş çekirdek: BLOK SIKI V3 + TEKRAR SIKI V3. "
    "Yeni çekiliş kaydedildiğinde geçmiş istatistikleri ve öğrenilen BLOK yeniden-sıralaması güncellenir; "
    "dondurulmuş karar eşikleri değişmez."
)

if df.empty:
    st.error("Ana veri havuzu boş. veri.txt dosyasını bu app.py ile aynı GitHub klasörüne koy.")
    st.stop()

gh=github_settings()
c1,c2,c3,c4=st.columns(4)
c1.metric("Ana havuz",len(df))
c2.metric("İlk çekiliş",int(df["Cekilis_No"].min()))
c3.metric("Son çekiliş",int(df["Cekilis_No"].max()))
c4.metric("Kalıcı GitHub kayıt","AKTİF" if gh else "Secrets yok")

if invalid:
    st.warning(f"veri.txt içinde atlanan bozuk satır: {len(invalid)}")

st.info(
    "🧠 ÖĞRENME AKTİF: Her yeni sonuç ana havuza eklendiğinde BLOK'un geçmiş Top15 yeniden-sıralama eğitimi, "
    "benzer durumları ve TEKRAR'ın kişisel geçiş oranları yeni veriyle tekrar hesaplanır. "
    "SIKI V3 eşikleri otomatik değişmez."
)

tabs=st.tabs([
    "🎯 Güncel Uzman Kararı",
    "✅ Sonucu Kontrol Et → Kaydet",
    "➕ Tekil Sonuç Ekle",
    "📚 Çoklu Sonuç Ekle",
    "🧪 750 Walk-Forward",
    "💾 Ana Havuz",
])

# ------------------------------------------------------------
# TAB 1 — GÜNCEL KARAR
# ------------------------------------------------------------
with tabs[0]:
    st.subheader("Bir sonraki çekiliş için dondurulmuş uzmanlar")
    if "current_prediction" not in st.session_state:
        st.session_state["current_prediction"]=None

    if st.button("🧠 ÖĞREN + GÜNCEL KARARI ÜRET",type="primary",use_container_width=True):
        with st.spinner("Dondurulmuş uzmanlar geçmiş havuzdan yeniden hesaplanıyor..."):
            eng=UnifiedEngine(df)
            bpicks,btab,binfo,bmeta=block_live_v3(eng)
            rpicks,rtab=repeat_v3_candidates(eng,len(eng.A))
            target_dt=next_draw_dt(df.iloc[-1]["DT"])
            st.session_state["current_prediction"]={
                "after_no":int(df.iloc[-1]["Cekilis_No"]),
                "target_no":int(df.iloc[-1]["Cekilis_No"])+1,
                "target_dt":target_dt,
                "block":bpicks,
                "repeat":rpicks,
                "block_info":binfo,
                "block_meta":bmeta,
                "block_table":btab,
                "repeat_table":rtab,
            }

    snap=st.session_state.get("current_prediction")
    if snap:
        stale=int(df.iloc[-1]["Cekilis_No"])!=int(snap["after_no"])
        if stale:
            st.warning("Ana havuz değişti. Bu tahmin eski havuza ait; GÜNCEL KARARI ÜRET'e tekrar bas.")
        st.write(
            f"**Hedef:** #{snap['target_no']} — "
            f"{snap['target_dt'].strftime('%d.%m.%Y %H:%M')}"
        )
        a,b=st.columns(2)
        with a:
            st.markdown("### 🧱 BLOK SIKI V3")
            if snap["block"]:
                st.success("KONUŞ — "+" - ".join(map(str,snap["block"])))
            else:
                st.warning("PAS — 0 sayı")
            bi=snap["block_info"]; bm=snap["block_meta"]
            st.write(
                f"Güven %{bi['confidence']} • Sinyal {bi['signal']} • "
                f"DEVAM {bi['event_rate']['DEVAM']:.3f} • KAYMA {bi['event_rate']['KAYMA']:.3f}"
            )
            st.write(
                f"Öğrenme: {'AKTİF' if bm['Öğrenme aktif'] else 'YETERSİZ GEÇMİŞ'} • "
                f"Dinamik seçici: {'KONUŞ' if bm['Dinamik KONUŞ'] else 'PAS'} • "
                f"Beklenen avantaj: {bm['Beklenen avantaj']:+.3f}"
            )
        with b:
            st.markdown("### 🔁 TEKRAR SIKI V3")
            if snap["repeat"]:
                st.success("KONUŞ — "+" - ".join(map(str,snap["repeat"])))
            else:
                st.warning("PAS — 0 sayı")
            st.write("Kural kilitli: streak ≥ 3 ve 0.26136 ≤ trans_same ≤ 0.269")

        union=sorted(set(snap["block"])|set(snap["repeat"]))
        agree=sorted(set(snap["block"])&set(snap["repeat"]))
        st.markdown("### 📌 Şimdilik sadece uzman çıktıları")
        st.write("BLOK ∪ TEKRAR:", " - ".join(map(str,union)) if union else "Yok")
        st.write("İki uzmanın kesişimi:", " - ".join(map(str,agree)) if agree else "Yok")
        st.caption("Kesişim henüz ayrı bir Uzlaşma motoru değildir; sadece bilgi amaçlı gösterilir.")

        st.markdown("### 🧩 Kupon Tamamlama LAB")
        eng2=UnifiedEngine(df)
        core,crank,coupons=build_completion_coupons(eng2,snap["block"],snap["repeat"])
        st.write("**Uzman çekirdeği:**", " - ".join(map(str,core)) if core else "Yok")
        if core:
            st.caption("Aşağıdaki ek sayılar uzman sinyali değildir; yalnız kuponu tamamlayan adaylardır.")
            cc1,cc2,cc3=st.columns(3)
            with cc1:
                st.write("**3'lü:**"," - ".join(map(str,coupons[3])))
                st.write("**4'lü:**"," - ".join(map(str,coupons[4])))
            with cc2:
                st.write("**5'li:**"," - ".join(map(str,coupons[5])))
                st.write("**7'li:**"," - ".join(map(str,coupons[7])))
            with cc3:
                st.write("**10'lu:**"," - ".join(map(str,coupons[10])))
            st.dataframe(crank.head(15),use_container_width=True,hide_index=True)
        else:
            st.warning("İki dondurulmuş uzman da PAS. Uzman çekirdeği olmadığı için tamamlayıcı kupon üretilmedi.")

# ------------------------------------------------------------
# TAB 2 — SONUCU KONTROL ET, SONRA AYNI ÇEKİLİŞİ KAYDET
# ------------------------------------------------------------
with tabs[1]:
    st.subheader("Tahmini gerçek sonuçla kontrol et")
    snap=st.session_state.get("current_prediction")
    default_no=int(df.iloc[-1]["Cekilis_No"])+1
    default_dt=next_draw_dt(df.iloc[-1]["DT"])

    draw_no=st.number_input("Çekiliş no",min_value=1,value=int(snap["target_no"]) if snap else default_no,step=1,key="check_no")
    date_txt=st.text_input("Tarih (GG.AA.YYYY)",value=(snap["target_dt"] if snap else default_dt).strftime("%d.%m.%Y"),key="check_date")
    time_txt=st.text_input("Saat (SS:DD)",value=(snap["target_dt"] if snap else default_dt).strftime("%H:%M"),key="check_time")
    actual_txt=st.text_area("Gerçek 20 sayı",height=160,placeholder="1 5 9 ... toplam 20 benzersiz sayı",key="check_nums")

    if st.button("🔎 SONUCU KONTROL ET",type="primary",use_container_width=True):
        nums=parse_20_numbers(actual_txt)
        try:
            dt=datetime.strptime(f"{date_txt} {time_txt}","%d.%m.%Y %H:%M")
        except Exception:
            dt=None
        if nums is None:
            st.error("Tam 20 benzersiz sayı girmelisin.")
        elif dt is None:
            st.error("Tarih/saat biçimi hatalı.")
        else:
            row_df=pd.DataFrame([[int(draw_no),dt,nums]],columns=["Cekilis_No","DT","Nums"])
            result={"row_df":row_df,"nums":nums}
            if snap and int(snap["after_no"])==int(df.iloc[-1]["Cekilis_No"]):
                aset=set(nums)
                bh=sorted(aset & set(snap["block"]))
                rh=sorted(aset & set(snap["repeat"]))
                result.update({"block_hits":bh,"repeat_hits":rh})
            st.session_state["pending_verified"]=result

    pending=st.session_state.get("pending_verified")
    if pending:
        nums=pending["nums"]
        st.success("Sonuç geçerli: 20/20 benzersiz sayı.")
        if "block_hits" in pending:
            x,y=st.columns(2)
            x.metric("BLOK isabet",f"{len(pending['block_hits'])}/{len(snap['block'])}" if snap and snap["block"] else "PAS")
            y.metric("TEKRAR isabet",f"{len(pending['repeat_hits'])}/{len(snap['repeat'])}" if snap and snap["repeat"] else "PAS")
            st.write("BLOK tutan:",pending["block_hits"] or "Yok")
            st.write("TEKRAR tutan:",pending["repeat_hits"] or "Yok")
        st.warning("Henüz ana havuza kaydedilmedi.")

        if st.button("✅ KONTROL EDİLEN ÇEKİLİŞİ ANA HAVUZA KAYDET",use_container_width=True):
            newdf=merge_rows(df,pending["row_df"])
            ok,msg=persist_pool(newdf,message=f"Kontrol sonrası çekiliş #{int(pending['row_df'].iloc[0]['Cekilis_No'])} eklendi")
            st.session_state["pending_verified"]=None
            st.session_state["current_prediction"]=None
            if ok: st.success(msg)
            else: st.warning(msg)
            st.rerun()

# ------------------------------------------------------------
# TAB 3 — TEKİL EKLEME
# ------------------------------------------------------------
with tabs[2]:
    st.subheader("Tek bir çekilişi doğrudan ana havuza ekle")
    single_no=st.number_input("Çekiliş no ",min_value=1,value=int(df.iloc[-1]["Cekilis_No"])+1,step=1,key="single_no")
    ndt=next_draw_dt(df.iloc[-1]["DT"])
    single_date=st.text_input("Tarih ",value=ndt.strftime("%d.%m.%Y"),key="single_date")
    single_time=st.text_input("Saat ",value=ndt.strftime("%H:%M"),key="single_time")
    single_nums=st.text_area("20 sayı ",height=140,key="single_nums")

    if st.button("➕ TEKİL SONUCU ANA HAVUZA EKLE",use_container_width=True):
        nums=parse_20_numbers(single_nums)
        try:
            dt=datetime.strptime(f"{single_date} {single_time}","%d.%m.%Y %H:%M")
        except Exception:
            dt=None
        if nums is None:
            st.error("20 benzersiz sayı gerekli.")
        elif dt is None:
            st.error("Tarih/saat hatalı.")
        else:
            add=pd.DataFrame([[int(single_no),dt,nums]],columns=["Cekilis_No","DT","Nums"])
            newdf=merge_rows(df,add)
            ok,msg=persist_pool(newdf,message=f"Tekil çekiliş #{int(single_no)} eklendi")
            st.session_state["current_prediction"]=None
            if ok: st.success(msg)
            else: st.warning(msg)
            st.rerun()

# ------------------------------------------------------------
# TAB 4 — ÇOKLU EKLEME
# ------------------------------------------------------------
with tabs[3]:
    st.subheader("Birden fazla çekilişi tek seferde ekle")
    st.write("Kabul edilen biçimler: `No;Tarih;Saat;20 sayı` veya peş peşe `Çekiliş no:` blokları.")
    up=st.file_uploader("TXT / CSV yükle",type=["txt","csv"],key="bulk_file")
    bulk_text=st.text_area("Veya sonuçları buraya yapıştır",height=260,key="bulk_text")

    source=bulk_text
    if up is not None:
        try:
            source=up.getvalue().decode("utf-8-sig",errors="ignore")
        except Exception:
            source=""

    preview=parse_bulk_results(source) if source.strip() else pd.DataFrame()
    if len(preview):
        st.success(f"{len(preview)} geçerli çekiliş bulundu.")
        show=preview.copy()
        show["Tarih"]=show["DT"].dt.strftime("%d.%m.%Y")
        show["Saat"]=show["DT"].dt.strftime("%H:%M")
        show["Sayılar"]=show["Nums"].apply(lambda x:" - ".join(map(str,x)))
        st.dataframe(show[["Cekilis_No","Tarih","Saat","Sayılar"]],use_container_width=True,hide_index=True)

        if st.button("📚 BU SONUÇLARIN TAMAMINI ANA HAVUZA EKLE",use_container_width=True):
            newdf=merge_rows(df,preview)
            ok,msg=persist_pool(newdf,message=f"Çoklu sonuç: {len(preview)} çekiliş eklendi/güncellendi")
            st.session_state["current_prediction"]=None
            if ok: st.success(msg)
            else: st.warning(msg)
            st.rerun()
    elif source.strip():
        st.error("Geçerli çekiliş ayrıştırılamadı.")

# ------------------------------------------------------------
# TAB 5 — TEST
# ------------------------------------------------------------
with tabs[4]:
    st.subheader("Dondurulmuş iki uzmanı sızıntısız geçmişte test et")
    st.caption("Test ağırdır; uygulama açılırken çalışmaz.")
    test_n=st.select_slider("Test adedi",options=[250,500,750],value=750)

    if "final_wf" not in st.session_state:
        st.session_state["final_wf"]=None

    if st.button("🧪 WALK-FORWARD TESTİ BAŞLAT",type="primary",use_container_width=True):
        with st.spinner(f"{test_n} çekilişlik FINAL uzman testi çalışıyor..."):
            eng=UnifiedEngine(df)
            wf=run_final_walkforward(eng,test_n)
            st.session_state["final_wf"]=wf

    wf=st.session_state.get("final_wf")
    if isinstance(wf,pd.DataFrame) and len(wf):
        bactive=wf[wf["BLOK boyu"]>0]
        ractive=wf[wf["TEKRAR boyu"]>0]
        a,b,c,d=st.columns(4)
        a.metric("BLOK KONUŞ",len(bactive))
        b.metric("BLOK Top10 ort.",f"{bactive['BLOK isabet'].mean():.3f}" if len(bactive) else "—")
        total_r=int(ractive["TEKRAR boyu"].sum()) if len(ractive) else 0
        hit_r=int(ractive["TEKRAR isabet"].sum()) if len(ractive) else 0
        c.metric("TEKRAR KONUŞ",len(ractive))
        d.metric("TEKRAR sayı doğruluğu",f"%{100*hit_r/max(total_r,1):.2f}" if len(ractive) else "—")
        st.dataframe(wf.sort_values("Çekiliş",ascending=False),use_container_width=True,hide_index=True)
        st.download_button(
            "⬇️ FINAL WALK-FORWARD CSV İNDİR",
            wf.to_csv(index=False).encode("utf-8-sig"),
            file_name="FINAL_UZMAN_WALKFORWARD.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ------------------------------------------------------------
# TAB 6 — HAVUZ / YEDEK
# ------------------------------------------------------------
with tabs[5]:
    st.subheader("Ana veri havuzu")
    st.dataframe(
        pd.DataFrame({
            "Çekiliş":df["Cekilis_No"].astype(int),
            "Tarih/Saat":df["DT"].dt.strftime("%d.%m.%Y %H:%M"),
            "Sayılar":df["Nums"].apply(lambda x:" - ".join(map(str,x))),
        }).tail(100).sort_values("Çekiliş",ascending=False),
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "⬇️ GÜNCEL veri.txt YEDEĞİNİ İNDİR",
        to_text(df).encode("utf-8"),
        file_name="veri.txt",
        mime="text/plain",
        use_container_width=True,
    )

st.divider()
st.caption(
    "FINAL V1 ilkesi: Elenen GEÇİŞ / DİNLENME / KOMŞU / BİRLİKTELİK / BANT bağımsız sayı üretmez. "
    "SAAT/FAZ ileride hakem/filtre olarak ayrı laboratuvarda değerlendirilecektir."
)
