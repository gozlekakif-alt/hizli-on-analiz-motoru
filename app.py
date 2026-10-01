
import io
import math
import re
import heapq
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import streamlit as st


# ============================================================
# HIZLI ON — 2'LİDEN 13'LÜYE AİLE + ÖN-İZ ARAŞTIRMA MOTORU
# - Gün gün işler.
# - Aileleri eğitim bölümünde keşfeder.
# - Ön-iz kuralını eğitimde seçer, doğrulama/testte dondurur.
# - Her günün raporunu ayrı üretir.
# - En sonda TÜM GÜNLERİ tek TXT içinde birleştirir.
#
# Not:
# 80 sayı içinden 2..13 tüm olası alt kümeleri kelimesi kelimesine
# listelemek astronomik boyuttadır. Bu motor her boyutu tarar ama
# "beam / derin aday araması" ile en güçlü tekrar eden aileleri seçer.
# Böylece Streamlit üzerinde çalışabilir kalır.
# ============================================================

st.set_page_config(
    page_title="Hızlı On — Aile Ön-İz Motoru",
    page_icon="🔬",
    layout="wide",
)

MINUTES = (2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57)


# ----------------------------
# Yardımcı matematik
# ----------------------------

def family_null_p(k: int) -> float:
    """Sabit k'lı grubun 20/80 çekilişinde tamamen bulunma olasılığı."""
    p = 1.0
    for j in range(k):
        p *= (20 - j) / (80 - j)
    return p


def z_score_support(support: int, n_draws: int, k: int) -> float:
    p = family_null_p(k)
    mu = n_draws * p
    var = n_draws * p * (1.0 - p)
    if var <= 0:
        return 0.0
    return (support - mu) / math.sqrt(var)


def mask_of(nums):
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m


def nums_of_mask(mask):
    return tuple(i + 1 for i in range(80) if (mask >> i) & 1)


def family_text(fam):
    return "-".join(f"{n:02d}" for n in fam)


# ----------------------------
# Veri ayrıştırma
# ----------------------------

COMPACT_DATE_RE = re.compile(
    r"HIZLI ON\s+[—-]\s+(\d{4}-\d{2}-\d{2})\s+GÜN"
)
COMPACT_DRAW_RE = re.compile(
    r"^(\d{2}:\d{2})\s+#(\d+)\s+\|\s+çıkan=([0-9,]+)\s*$"
)

F_HOUR_RE = re.compile(
    r"^---\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}):00\s+\|\s+12 ÇEKİLİŞ\s+---$"
)
F_DRAW_RE = re.compile(
    r"^:(02|07|12|17|22|27|32|37|42|47|52|57)\s+#(\d+)\s+\|\s+\+20=([0-9\-]+)$"
)

RAW_DRAW_NO_INLINE = re.compile(
    r"Çekiliş\s*no\s*:\s*(?:###\s*)?(\d+)", re.I
)
RAW_DATE_RE = re.compile(
    r"(\d{2})\.(\d{2})\.(\d{4})\s*[-–]\s*(\d{2}):(\d{2})"
)
STANDALONE_INT_RE = re.compile(r"^\s*(\d{1,2})\s*$")


def parse_text(text: str):
    """
    Çok biçimli ayrıştırıcı.
    Destek:
    1) Gün raporu: 'HH:MM #123 | çıkan=...'
    2) [F] haritası: ':02 #123 | +20=...'
    3) Milli Piyango/web kopyası:
       Çekiliş no:
       ### 59024
       29.09.2026-23:57
       1
       3
       ...
    4) Aynı blokta virgül / tire / boşlukla yazılmış 20 sayı.
    """
    rows = []
    seen = set()
    lines = text.replace("\ufeff", "").splitlines()

    # ---------- 0) SENİN veri.txt TEK-SATIR BİÇİMİN ----------
    # Örnek mantık:
    # ===== 25.08.2026 | 217
    # 51213:25.08.2026 00:02:02,04,06,...,80
    #
    # Gün başlığına ihtiyaç yok; her çekiliş satırındaki tarih/saat doğrudan okunur.
    one_line_re = re.compile(
        r"^\s*(\d{4,7})\s*:\s*"
        r"(\d{2})\.(\d{2})\.(\d{4})\s+"
        r"(\d{2}):(\d{2})"
        r"(.*)$"
    )

    for raw in lines:
        s = raw.strip()
        m = one_line_re.match(s)
        if not m:
            continue

        no_s, dd, mo, yy, hh, mm, rest = m.groups()
        no = int(no_s)

        # Saatten sonraki bölüm yalnız çekiliş sayılarını içerir.
        # Ayırıcı :, |, virgül, tire, boşluk vb. ne olursa olsun 1..80 sayıları çek.
        vals = [int(x) for x in re.findall(r"(?<!\d)(?:[1-9]|[1-7]\d|80)(?!\d)", rest)]

        # Sıralamayı bozmadan ilk 20 benzersiz sayıyı al.
        nums = []
        used = set()
        for x in vals:
            if 1 <= x <= 80 and x not in used:
                nums.append(x)
                used.add(x)
            if len(nums) == 20:
                break

        if len(nums) == 20 and no not in seen:
            dt = datetime(int(yy), int(mo), int(dd), int(hh), int(mm))
            rows.append((dt, no, tuple(sorted(nums))))
            seen.add(no)

    # ---------- 1) Kompakt rapor ----------
    current_date = None
    for raw in lines:
        s = raw.strip()
        md = COMPACT_DATE_RE.search(s)
        if md:
            current_date = md.group(1)
            continue
        md = COMPACT_DRAW_RE.match(s)
        if md and current_date:
            tm, no, nums_s = md.groups()
            no = int(no)
            nums = tuple(sorted(int(x) for x in nums_s.split(",")))
            if len(nums) == 20 and len(set(nums)) == 20 and no not in seen:
                dt = datetime.strptime(current_date + " " + tm, "%Y-%m-%d %H:%M")
                rows.append((dt, no, nums))
                seen.add(no)

    # ---------- 2) [F] tam saat haritası ----------
    current_date = None
    current_hour = None
    for raw in lines:
        s = raw.strip()
        mh = F_HOUR_RE.match(s)
        if mh:
            current_date, current_hour = mh.group(1), int(mh.group(2))
            continue
        md = F_DRAW_RE.match(s)
        if md and current_date is not None:
            minute, no, nums_s = md.groups()
            no = int(no)
            nums = tuple(sorted(int(x) for x in nums_s.split("-")))
            if len(nums) == 20 and len(set(nums)) == 20 and no not in seen:
                tm = f"{current_hour:02d}:{int(minute):02d}"
                dt = datetime.strptime(current_date + " " + tm, "%Y-%m-%d %H:%M")
                rows.append((dt, no, nums))
                seen.add(no)

    # ---------- 3) Genel / markdown / web kopyası ----------
    def clean_line(s):
        s = s.strip()
        # Markdown başlık, madde, blockquote ve kod işaretlerini temizle.
        s = re.sub(r"^[#>*`\-\s]+", "", s)
        s = re.sub(r"[`]+$", "", s).strip()
        return s

    # Tarih biçimleri
    date_tr = re.compile(
        r"(?<!\d)(\d{2})[./](\d{2})[./](\d{4})\s*[-–— ]\s*(\d{2}):(\d{2})(?!\d)"
    )
    date_iso = re.compile(
        r"(?<!\d)(\d{4})-(\d{2})-(\d{2})\s*[-–— ]?\s*(\d{2}):(\d{2})(?!\d)"
    )

    # "Çekiliş no: 59024" veya "Çekiliş no #59024"
    no_inline = re.compile(
        r"(?:çekiliş|cekilis)\s*(?:no|numarası|numarasi|numara)?\s*[:#\-]?\s*(\d{4,7})",
        re.I,
    )
    no_label = re.compile(
        r"(?:çekiliş|cekilis)\s*(?:no|numarası|numarasi|numara)?\s*:?\s*$",
        re.I,
    )

    pending_no = None
    pending_dt = None
    pending_nums = []
    wait_no_after_label = False

    def flush_raw():
        nonlocal pending_no, pending_dt, pending_nums
        if pending_no is not None and pending_dt is not None:
            # İlk 20 benzersiz geçerli sayıyı koru.
            uniq = []
            used = set()
            for x in pending_nums:
                if 1 <= x <= 80 and x not in used:
                    uniq.append(x)
                    used.add(x)
                if len(uniq) == 20:
                    break
            if len(uniq) == 20 and pending_no not in seen:
                rows.append((pending_dt, pending_no, tuple(sorted(uniq))))
                seen.add(pending_no)
        pending_no = None
        pending_dt = None
        pending_nums = []

    for raw in lines:
        s0 = raw.strip()
        s = clean_line(s0)
        if not s:
            continue

        # Yeni çekiliş numarası
        mi = no_inline.search(s)
        if mi:
            flush_raw()
            pending_no = int(mi.group(1))
            wait_no_after_label = False
            continue

        if no_label.search(s):
            flush_raw()
            wait_no_after_label = True
            continue

        # "### 59024" gibi etiketin alt satırı
        if wait_no_after_label:
            mm = re.fullmatch(r"#?\s*(\d{4,7})\s*", s)
            if mm:
                pending_no = int(mm.group(1))
                wait_no_after_label = False
                continue

        # Tarih/saat
        md = date_tr.search(s)
        if md and pending_no is not None:
            dd, mo, yy, hh, mm = md.groups()
            pending_dt = datetime(int(yy), int(mo), int(dd), int(hh), int(mm))
            pending_nums = []
            continue

        md = date_iso.search(s)
        if md and pending_no is not None:
            yy, mo, dd, hh, mm = md.groups()
            pending_dt = datetime(int(yy), int(mo), int(dd), int(hh), int(mm))
            pending_nums = []
            continue

        if pending_no is None or pending_dt is None:
            continue

        # Tek sayı satırı: "17", "### 17", "- 17" vb.
        if re.fullmatch(r"\d{1,2}", s):
            x = int(s)
            if 1 <= x <= 80:
                pending_nums.append(x)
                if len(set(pending_nums)) >= 20:
                    flush_raw()
            continue

        # Bir satırda sayı listesi: "1,3,7..." / "01-03-07..." / "1 3 7..."
        if re.fullmatch(r"[0-9,\-;\s]+", s):
            vals = [int(x) for x in re.findall(r"\d{1,2}", s)]
            vals = [x for x in vals if 1 <= x <= 80]
            if len(vals) >= 2:
                pending_nums.extend(vals)
                if len(set(pending_nums)) >= 20:
                    flush_raw()
            continue

    flush_raw()

    # Aynı çekiliş no'lu kayıtları tekilleştir.
    merged = {}
    for dt, no, nums in rows:
        merged[no] = (dt, no, nums)

    return sorted(merged.values(), key=lambda x: (x[0], x[1]))

def parse_many(texts):
    merged = {}
    for text in texts:
        for dt, no, nums in parse_text(text):
            merged[no] = (dt, no, nums)
    return sorted(merged.values(), key=lambda x: (x[0], x[1]))


# ----------------------------
# Kronolojik bölme
# ----------------------------

def split_by_days(draws):
    days = sorted({d[0].date() for d in draws})
    if len(days) < 5:
        # Çok kısa dosyada basit çekiliş bazlı böl
        n = len(draws)
        a = max(1, int(n * 0.60))
        b = max(a + 1, int(n * 0.80))
        return set(range(0, a)), set(range(a, b)), set(range(b, n)), days

    a = max(1, int(len(days) * 0.60))
    b = max(a + 1, int(len(days) * 0.80))
    train_days = set(days[:a])
    val_days = set(days[a:b])
    test_days = set(days[b:])

    train_idx = {i for i, d in enumerate(draws) if d[0].date() in train_days}
    val_idx = {i for i, d in enumerate(draws) if d[0].date() in val_days}
    test_idx = {i for i, d in enumerate(draws) if d[0].date() in test_days}
    return train_idx, val_idx, test_idx, days


# ----------------------------
# Aile keşfi — beam derin tarama
# ----------------------------

def build_item_tids(draws, indices):
    ordered = sorted(indices)
    pos = {global_i: local_i for local_i, global_i in enumerate(ordered)}
    tids = {n: 0 for n in range(1, 81)}
    for global_i in ordered:
        local_i = pos[global_i]
        nums = draws[global_i][2]
        bit = 1 << local_i
        for n in nums:
            tids[n] |= bit
    return tids, ordered


def node_score(support, n_train, depth):
    # Ana sıralama: beklenene göre z; küçük desteklerde lift etkisini de hafif kat.
    z = z_score_support(support, n_train, depth)
    expected = max(n_train * family_null_p(depth), 1e-12)
    lift = support / expected
    return z + 0.10 * math.log1p(max(lift, 0.0))


def min_candidate_support(n_train, k, strength):
    """
    Bu eşik yalnız 'rapora alınacak aday' eşiğidir.
    Beam dallanması support>=2 ile yürür.
    """
    p = family_null_p(k)
    mu = n_train * p
    sd = math.sqrt(max(n_train * p * (1 - p), 0.0))
    sigma = {"Geniş": 0.8, "Dengeli": 1.5, "Sıkı": 2.2}[strength]
    base = math.ceil(mu + sigma * sd)
    if k >= 8:
        base = max(2, base)
    elif k >= 6:
        base = max(3, base)
    else:
        base = max(4, base)
    return int(base)


def keep_top_nodes(generator, width):
    heap = []
    seq = 0
    for score, support, prefix, tids in generator:
        item = (score, support, seq, prefix, tids)
        seq += 1
        if len(heap) < width:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)
    out = [(a, b, p, t) for a, b, _, p, t in heap]
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return out


@st.cache_data(show_spinner=False)
def mine_families_cached(draw_signature, train_indices_tuple, max_k, beam_width, top_per_k, strength):
    """
    draw_signature = tuple((draw_no, tuple(nums)), ...)
    Cache için datetime taşımıyoruz.
    """
    fake_draws = [(None, no, nums) for no, nums in draw_signature]
    train_indices = set(train_indices_tuple)
    item_tids, ordered = build_item_tids(fake_draws, train_indices)
    n_train = len(ordered)

    current = []
    for n in range(1, 81):
        tids = item_tids[n]
        sup = tids.bit_count()
        current.append((node_score(sup, n_train, 1), sup, (n,), tids))

    results = {}
    for depth in range(2, max_k + 1):
        def gen():
            for _, _, prefix, ptids in current:
                start = prefix[-1] + 1
                for n in range(start, 81):
                    ntids = ptids & item_tids[n]
                    sup = ntids.bit_count()
                    if sup < 2:
                        continue
                    pref = prefix + (n,)
                    yield node_score(sup, n_train, depth), sup, pref, ntids

        current = keep_top_nodes(gen(), beam_width)
        threshold = min_candidate_support(n_train, depth, strength)
        eligible = [x for x in current if x[1] >= threshold]
        results[depth] = eligible[:top_per_k]

        if not current:
            # daha büyük aile mümkün değil
            for d in range(depth + 1, max_k + 1):
                results[d] = []
            break

    return results


# ----------------------------
# Aile oluşumları + ön-iz özellikleri
# ----------------------------

def build_masks(draws):
    return [mask_of(d[2]) for d in draws]


def pretrace_features(masks, idx, fam_mask, lookback):
    if idx <= 0:
        return None
    start = max(0, idx - lookback)
    hist = masks[start:idx]
    if not hist:
        return None

    k = fam_mask.bit_count()
    prev1 = (hist[-1] & fam_mask).bit_count()

    last3 = hist[-3:]
    last6 = hist[-6:]
    last12 = hist[-12:]

    max3 = max((m & fam_mask).bit_count() for m in last3)
    max6 = max((m & fam_mask).bit_count() for m in last6)

    u3 = 0
    for m in last3:
        u3 |= m
    u6 = 0
    for m in last6:
        u6 |= m
    u12 = 0
    for m in last12:
        u12 |= m

    union3 = (u3 & fam_mask).bit_count()
    union6 = (u6 & fam_mask).bit_count()
    union12 = (u12 & fam_mask).bit_count()

    return {
        "prev1": prev1,
        "max3": max3,
        "max6": max6,
        "union3": union3,
        "union6": union6,
        "union12": union12,
        "k": k,
    }


def activation_indices(masks, fam_mask, eligible_indices=None):
    if eligible_indices is None:
        iterable = range(len(masks))
    else:
        iterable = sorted(eligible_indices)
    return [i for i in iterable if (masks[i] & fam_mask) == fam_mask]


def top_hour_identity(draws, activation_idxs):
    c = Counter(draws[i][0].hour for i in activation_idxs)
    if not c:
        return None, 0, 0.0
    h, n = c.most_common(1)[0]
    return h, n, n / len(activation_idxs)


def dominant_day_gap(draws, activation_idxs):
    if len(activation_idxs) < 3:
        return None, 0, 0.0
    dates = [draws[i][0].date() for i in activation_idxs]
    # Aynı gün birden çok aktivasyonu tek gün kabul et
    ud = sorted(set(dates))
    if len(ud) < 3:
        return None, 0, 0.0
    gaps = [(b - a).days for a, b in zip(ud, ud[1:])]
    c = Counter(gaps)
    g, n = c.most_common(1)[0]
    return g, n, n / len(gaps)


def condition_value(feat, feature, threshold):
    return feat[feature] >= threshold


def eval_rule_for_family(masks, fam_mask, indices, feature, threshold, lookback):
    triggers = hits = eligible = 0
    base_hits = 0
    idxset = sorted(indices)
    for i in idxset:
        if i <= 0:
            continue
        feat = pretrace_features(masks, i, fam_mask, lookback)
        if feat is None:
            continue
        eligible += 1
        active = (masks[i] & fam_mask) == fam_mask
        if active:
            base_hits += 1
        if condition_value(feat, feature, threshold):
            triggers += 1
            if active:
                hits += 1

    base = base_hits / eligible if eligible else 0.0
    precision = hits / triggers if triggers else 0.0
    lift = precision / base if base > 0 else 0.0
    return {
        "eligible": eligible,
        "base_hits": base_hits,
        "base_rate": base,
        "triggers": triggers,
        "hits": hits,
        "precision": precision,
        "lift": lift,
    }


def choose_train_rule(masks, fam_mask, train_indices, lookback):
    k = fam_mask.bit_count()
    features = ("prev1", "max3", "max6", "union3", "union6", "union12")
    best = None

    for feature in features:
        for threshold in range(1, k + 1):
            r = eval_rule_for_family(
                masks, fam_mask, train_indices, feature, threshold, lookback
            )
            min_triggers = 20 if k <= 4 else 8
            if r["triggers"] < min_triggers or r["hits"] < 2:
                continue

            # Aşırı küçük trigger sayısını cezalandır.
            score = r["lift"] * math.log1p(r["triggers"])
            cand = (score, r["lift"], r["hits"], r["triggers"], feature, threshold, r)
            if best is None or cand[:4] > best[:4]:
                best = cand

    if best is None:
        return None
    _, _, _, _, feature, threshold, stats = best
    return feature, threshold, stats


def avg_activation_trace(masks, fam_mask, act_idxs, lookback):
    vals = defaultdict(list)
    for i in act_idxs:
        feat = pretrace_features(masks, i, fam_mask, lookback)
        if feat:
            for key in ("prev1", "max3", "max6", "union3", "union6", "union12"):
                vals[key].append(feat[key])
    out = {}
    for key in ("prev1", "max3", "max6", "union3", "union6", "union12"):
        arr = vals.get(key, [])
        out[key] = (sum(arr) / len(arr)) if arr else 0.0
    return out


# ----------------------------
# Rapor üretimi
# ----------------------------

def render_family_global_line(
    draws, masks, fam, train_idx, val_idx, test_idx, lookback
):
    fm = mask_of(fam)
    train_act = activation_indices(masks, fm, train_idx)
    val_act = activation_indices(masks, fm, val_idx)
    test_act = activation_indices(masks, fm, test_idx)
    all_act = sorted(train_act + val_act + test_act)

    h, hn, hr = top_hour_identity(draws, all_act)
    gap, gn, gr = dominant_day_gap(draws, all_act)
    trace = avg_activation_trace(masks, fm, all_act, lookback)

    rule = choose_train_rule(masks, fm, train_idx, lookback)
    if rule:
        feature, threshold, tr = rule
        va = eval_rule_for_family(masks, fm, val_idx, feature, threshold, lookback)
        te = eval_rule_for_family(masks, fm, test_idx, feature, threshold, lookback)
        rule_text = (
            f"{feature}>={threshold} | "
            f"TRAIN {tr['hits']}/{tr['triggers']} lift={tr['lift']:.2f} | "
            f"VAL {va['hits']}/{va['triggers']} lift={va['lift']:.2f} | "
            f"TEST {te['hits']}/{te['triggers']} lift={te['lift']:.2f}"
        )
    else:
        rule_text = "yeterli ön-iz kuralı oluşmadı"

    hour_text = "-" if h is None else f"{h:02d}:00 ({hn}/{len(all_act)}=%{100*hr:.1f})"
    gap_text = "-" if gap is None else f"{gap} gün ({gn} aralık, %{100*gr:.1f})"

    return (
        f"AİLE {family_text(fam)} | "
        f"aktivasyon T/V/Test={len(train_act)}/{len(val_act)}/{len(test_act)} | "
        f"top-saat={hour_text} | gün-ritmi={gap_text} | "
        f"aktif-öncesi ort: prev1={trace['prev1']:.2f}, max3={trace['max3']:.2f}, "
        f"union3={trace['union3']:.2f}, union6={trace['union6']:.2f}, "
        f"union12={trace['union12']:.2f} | ÖN-İZ={rule_text}"
    )


def make_combined_report(
    draws,
    candidates,
    train_idx,
    val_idx,
    test_idx,
    lookback,
    include_daily_details=True,
):
    masks = build_masks(draws)
    lines = []
    lines.append("HIZLI ON — 2'LİDEN 13'LÜYE AİLE + ÖN-AKTİVASYON İZ RAPORU")
    lines.append("=" * 140)
    lines.append(
        f"Çekiliş={len(draws)} | Gün={len(set(d[0].date() for d in draws))} | "
        f"Tarih={draws[0][0].strftime('%Y-%m-%d %H:%M')} → {draws[-1][0].strftime('%Y-%m-%d %H:%M')}"
    )
    lines.append(
        f"Kronolojik bölme: TRAIN={len(train_idx)} | VAL={len(val_idx)} | TEST={len(test_idx)}"
    )
    lines.append(
        "Aile keşfi TRAIN bölümünde yapılır. Ön-iz kuralı TRAIN'de seçilir; VAL ve TEST'te değiştirilmeden ölçülür."
    )
    lines.append(
        "Ön-iz özellikleri: prev1=hemen önceki çekilişte aileden kaç sayı; "
        "max3/max6=son 3/6 çekilişte tek çekilişte görülen en yüksek aile örtüşmesi; "
        "union3/6/12=son 3/6/12 çekilişin birleşiminde ailenin kaç üyesi en az bir kez görüldü."
    )
    lines.append("")

    # Global aile bölümleri
    lines.append("[A] GLOBAL AİLE KİMLİKLERİ VE KÖR ÖN-İZ TESTİ")
    lines.append("=" * 140)
    for k in range(2, 14):
        lines.append("")
        lines.append("#" * 140)
        lines.append(f"{k}'Lİ AİLELER")
        lines.append("#" * 140)
        fams = [x[2] for x in candidates.get(k, [])]
        if not fams:
            lines.append("Bu ayarlarda rapora girecek aday bulunmadı.")
            continue

        for fam in fams:
            lines.append(
                render_family_global_line(
                    draws, masks, fam, train_idx, val_idx, test_idx, lookback
                )
            )

    # Gün gün gerçek aktivasyonlar
    if include_daily_details:
        lines.append("")
        lines.append("[B] GÜN GÜN AİLE AKTİVASYONLARI + AKTİVASYON ÖNCESİ İZ")
        lines.append("=" * 140)

        fam_records = []
        for k in range(2, 14):
            for score, sup, fam, tids in candidates.get(k, []):
                fam_records.append((k, fam, mask_of(fam)))

        by_day = defaultdict(list)
        for i, (dt, no, nums) in enumerate(draws):
            by_day[dt.date()].append(i)

        all_days = sorted(by_day)
        for day in all_days:
            lines.append("")
            lines.append("*" * 140)
            lines.append(f"GÜN {day.isoformat()} | çekiliş={len(by_day[day])}")
            lines.append("*" * 140)

            day_count = Counter()
            day_lines = []

            for i in by_day[day]:
                dm = masks[i]
                hit_here = []
                for k, fam, fm in fam_records:
                    if (dm & fm) == fm:
                        feat = pretrace_features(masks, i, fm, lookback)
                        if feat is None:
                            continue
                        day_count[k] += 1
                        hit_here.append(
                            (
                                k,
                                family_text(fam),
                                feat["prev1"],
                                feat["max3"],
                                feat["union3"],
                                feat["union6"],
                                feat["union12"],
                            )
                        )

                if hit_here:
                    dt, no, _ = draws[i]
                    day_lines.append(f"{dt.strftime('%H:%M')} #{no}")
                    for k, ft, p1, m3, u3, u6, u12 in sorted(
                        hit_here, key=lambda x: (x[0], x[1])
                    ):
                        day_lines.append(
                            f"  {k}'Lİ {ft} | prev1={p1}/{k} | max3={m3}/{k} | "
                            f"union3={u3}/{k} | union6={u6}/{k} | union12={u12}/{k}"
                        )

            lines.append(
                "ÖZET | "
                + " | ".join(f"{k}'li={day_count[k]}" for k in range(2, 14))
            )
            if day_lines:
                lines.extend(day_lines)
            else:
                lines.append("Bu gün seçilmiş aday ailelerde aktivasyon yok.")

    lines.append("")
    lines.append("[C] NOT")
    lines.append("=" * 140)
    lines.append(
        "Bu rapor tarihsel ilişki/örüntü araştırmasıdır. Bir ailede geçmişte tekrar veya ön-iz görülmesi "
        "gelecek çekilişte aynı davranışın kesin tekrarlanacağı anlamına gelmez."
    )
    return "\n".join(lines)


# ----------------------------
# Streamlit arayüzü
# ----------------------------

st.title("🔬 Hızlı On — 2'li → 13'lü Aile Ön-İz Araştırma Motoru")
st.caption(
    "Tek gün tek gün analiz eder; bütün günleri sonunda TEK TXT dosyada birleştirir."
)

with st.sidebar:
    st.header("Ayarlar")
    lookback = st.slider("Aktivasyondan önce kaç çekiliş izlenecek?", 3, 24, 12, 1)
    max_k = st.slider("En büyük aile", 2, 13, 13, 1)
    beam_width = st.select_slider(
        "Derin tarama genişliği",
        options=[1000, 2500, 5000, 10000, 20000],
        value=5000,
        help="Yükseldikçe daha derin tarar ama daha çok RAM/işlem kullanır.",
    )
    top_per_k = st.slider(
        "Her aile boyutundan rapora alınacak en güçlü aday",
        5, 100, 30, 5
    )
    strength = st.selectbox(
        "Aday filtresi", ["Geniş", "Dengeli", "Sıkı"], index=1
    )
    include_daily = st.checkbox("Gün gün aktivasyon detaylarını yaz", value=True)

st.subheader("1) Veri kaynağı")

# GitHub / Streamlit Cloud:
# app.py ile AYNI klasörde bulunan veri.txt otomatik okunur.
APP_DIR = Path(__file__).resolve().parent
repo_veri = APP_DIR / "veri.txt"

uploaded = st.file_uploader(
    "İstersen yeni/güncel TXT ekle (repo veri.txt ile otomatik birleştirilir)",
    type=["txt"],
    accept_multiple_files=True,
)

texts = []
source_labels = []

if repo_veri.exists():
    try:
        repo_text = repo_veri.read_text(encoding="utf-8", errors="replace")
        texts.append(repo_text)
        source_labels.append(f"GitHub/repo: {repo_veri.name}")
        st.success("✅ GitHub veri.txt bulundu ve otomatik yüklendi.")
    except Exception as e:
        st.error(f"veri.txt bulundu ama okunamadı: {e}")
else:
    st.warning("⚠️ app.py ile aynı klasörde veri.txt bulunamadı.")

if uploaded:
    for f in uploaded:
        texts.append(f.getvalue().decode("utf-8", errors="replace"))
        source_labels.append(f"Yüklenen: {f.name}")

if source_labels:
    st.caption("Kaynaklar: " + " | ".join(source_labels))

if texts:
    with st.spinner("Veri okunuyor ve tek kütükte birleştiriliyor..."):
        draws = parse_many(texts)

    if draws:
        days = sorted({d[0].date() for d in draws})
        st.success(
            f"✅ veri.txt TANINDI: {len(draws):,} benzersiz çekiliş | {len(days)} gün | "
            f"{draws[0][0].strftime('%d.%m.%Y %H:%M')} → "
            f"{draws[-1][0].strftime('%d.%m.%Y %H:%M')}"
        )
        if len(draws) == 7812 and len(days) == 36:
            st.info("🎯 Kontrol geçti: 7.812 çekiliş / 36 gün tam olarak okundu.")
        daily_counts = Counter(d[0].date() for d in draws)
        with st.expander("Gün sayımları"):
            st.text(
                "\n".join(
                    f"{day.isoformat()} : {daily_counts[day]} çekiliş"
                    for day in days
                )
            )

        st.subheader("2) Aileleri keşfet + ön-iz testini çalıştır")
        st.info(
            "Motor önce TRAIN günlerinde 2'liden seçtiğin üst sınıra kadar aile adaylarını keşfeder. "
            "Sonra her aile için aktivasyondan önceki izi ölçer. "
            "Ön-iz kuralı TRAIN'de seçilip VAL/TEST'te değiştirilmeden sınanır."
        )

        if st.button("🚀 DERİN TARAMAYI BAŞLAT", type="primary", use_container_width=True):
            train_idx, val_idx, test_idx, all_days = split_by_days(draws)
            sig = tuple((d[1], d[2]) for d in draws)

            p = st.progress(0, text="Aile adayları keşfediliyor...")
            with st.spinner("2'li → 13'lü aile ağı taranıyor..."):
                candidates = mine_families_cached(
                    sig,
                    tuple(sorted(train_idx)),
                    max_k,
                    beam_width,
                    top_per_k,
                    strength,
                )
            p.progress(35, text="Aile keşfi tamamlandı. Ön-iz analizine geçiliyor...")

            # Kullanıcıya hızlı özet
            summary_lines = []
            for k in range(2, max_k + 1):
                n = len(candidates.get(k, []))
                if n:
                    best = candidates[k][0]
                    summary_lines.append(
                        f"{k}'li: {n} aday | en üst {family_text(best[2])} | TRAIN destek={best[1]}"
                    )
                else:
                    summary_lines.append(f"{k}'li: aday yok")

            st.text("\n".join(summary_lines))
            p.progress(55, text="Gün gün aktivasyon ve ön-iz kayıtları hazırlanıyor...")

            report = make_combined_report(
                draws,
                candidates,
                train_idx,
                val_idx,
                test_idx,
                lookback,
                include_daily_details=include_daily,
            )

            p.progress(100, text="Tamamlandı — tüm günler tek dosyada birleşti.")
            st.success("Analiz tamamlandı. Gün gün bölümler + global sonuçlar tek TXT içinde.")

            st.download_button(
                "⬇️ TÜM GÜNLER — TEK TXT İNDİR",
                data=report.encode("utf-8"),
                file_name="HIZLI_ON_2DEN13E_AILE_ONIZ_TUM_GUNLER_TEK_CIKTI.txt",
                mime="text/plain",
                use_container_width=True,
            )

            with st.expander("Raporun ilk kısmını göster"):
                st.text(report[:30000])
    else:
        st.error("TXT bulundu fakat ayrıştırma 0 çekiliş verdi. İlk satırlar aşağıda; bu sürüm özellikle 51213:25.08.2026 00:02... biçimini okur.")
        st.info("Aşağıdaki tanı bilgisi veri.txt biçimini görmemizi sağlar; sayıların kendisini değiştirmez.")
        combined_text = "\n".join(texts)
        nonempty = [x for x in combined_text.splitlines() if x.strip()]
        st.write(f"Dosya metin satırı: {len(combined_text.splitlines()):,} | boş olmayan: {len(nonempty):,}")
        with st.expander("İlk 40 satırı göster — ayrıştırıcı tanısı"):
            st.code("\n".join(nonempty[:40]), language="text")
else:
    st.warning("Repo kökünde app.py ile aynı klasöre veri.txt koy veya ek TXT yükle.")
