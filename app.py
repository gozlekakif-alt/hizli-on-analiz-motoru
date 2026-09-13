
import streamlit as st
import pandas as pd
import requests
from io import StringIO, BytesIO
from collections import Counter, defaultdict
from datetime import datetime
import re

st.set_page_config(page_title="Hızlı On - Gerçek Yaşam İzi", layout="wide")

st.title("Hızlı On — 14 Gün Gerçek Yaşam İzi Analiz Motoru")
st.caption("Her günü ayrı işler, kronolojik PRE-H yaşam izini çıkarır ve sonunda tek birleşik TXT rapor üretir.")

# -----------------------------
# Yardımcı fonksiyonlar
# -----------------------------
def parse_txt(text):
    rows = []
    for ln, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) != 3:
            raise ValueError(f"Satır {ln}: beklenen biçim 'çekiliş_no;tarih saat;sayılar'")
        draw_no = parts[0].strip()
        dt = datetime.strptime(parts[1].strip(), "%d.%m.%Y %H:%M")
        nums = [int(x.strip()) for x in parts[2].split(",") if x.strip()]
        if len(nums) != 20:
            raise ValueError(f"Satır {ln}: {draw_no} çekilişinde 20 yerine {len(nums)} sayı var.")
        if len(set(nums)) != 20:
            raise ValueError(f"Satır {ln}: {draw_no} çekilişinde tekrarlı sayı var.")
        if any(n < 1 or n > 80 for n in nums):
            raise ValueError(f"Satır {ln}: 1–80 dışında sayı var.")
        rows.append({
            "draw_no": draw_no,
            "dt": dt,
            "date": dt.date(),
            "time": dt.strftime("%H:%M"),
            "nums": sorted(nums)
        })
    rows.sort(key=lambda r: r["dt"])
    return rows

def raw_github_url(url):
    url = url.strip()
    if "raw.githubusercontent.com" in url:
        return url
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)", url)
    if m:
        owner, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    return url

def load_from_url(url):
    url = raw_github_url(url)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def age_groups_for_day(day_rows):
    """
    Her çekilişte, o an çıkan her sayının aynı gün içindeki en son görünümüne bakar.
    İlk kez görünüyorsa Yeni.
    Gelecek bilgi kullanılmaz.
    """
    last_seen = {}
    result = []
    for idx, row in enumerate(day_rows):
        groups = defaultdict(list)
        for n in row["nums"]:
            if n in last_seen:
                age = idx - last_seen[n]
                groups[f"H-{age}"].append(n)
            else:
                groups["Yeni"].append(n)
        for n in row["nums"]:
            last_seen[n] = idx
        result.append(groups)
    return result

def h_sort_key(k):
    if k == "Yeni":
        return (9999, 0)
    return (int(k.split("-")[1]), 0)

def hour_key(dt):
    return dt.strftime("%H")

def frequency(rows):
    c = Counter()
    for r in rows:
        c.update(r["nums"])
    return c

def top20(c):
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:20]

def life_cards(day_rows):
    """
    Sayı bazında: ilk doğum, toplam görünüm, görünüm sırası, uyku aralıkları,
    en sık dönüş yaşı, max uyku, son görünüm.
    """
    pos = defaultdict(list)
    for i, r in enumerate(day_rows, start=1):
        for n in r["nums"]:
            pos[n].append(i)
    cards = {}
    for n in range(1,81):
        seq = pos.get(n, [])
        if not seq:
            cards[n] = {
                "first": None, "count": 0, "gaps": [],
                "mode_gap": None, "max_gap": None, "last": None
            }
            continue
        gaps = [seq[i]-seq[i-1] for i in range(1, len(seq))]
        mode_gap = None
        if gaps:
            cc = Counter(gaps)
            mode_gap = sorted(cc.items(), key=lambda x: (-x[1], x[0]))[0][0]
        cards[n] = {
            "first": seq[0],
            "count": len(seq),
            "gaps": gaps,
            "mode_gap": mode_gap,
            "max_gap": max(gaps) if gaps else None,
            "last": seq[-1]
        }
    return cards

def transition_0102_0702(day_rows, groups_by_draw):
    by_time = {r["time"]: i for i, r in enumerate(day_rows)}
    out = None
    if "01:02" in by_time and "07:02" in by_time:
        i = by_time["07:02"]
        g = groups_by_draw[i]
        out = {k: sorted(v) for k, v in g.items()}
    return out

def analyze_day(day_rows):
    groups_by_draw = age_groups_for_day(day_rows)
    total_age = Counter()
    draw_lines = []

    for row, g in zip(day_rows, groups_by_draw):
        parts = []
        for k in sorted(g.keys(), key=h_sort_key):
            vals = sorted(g[k])
            total_age[k] += len(vals)
            parts.append(f"{k}={len(vals)}[{','.join(map(str, vals))}]")
        draw_lines.append(
            f"{row['draw_no']} | {row['dt'].strftime('%d.%m.%Y %H:%M')} | "
            + " | ".join(parts)
        )

    day_freq = frequency(day_rows)

    # Saatlik frekanslar
    hours = defaultdict(list)
    for r in day_rows:
        hours[hour_key(r["dt"])].append(r)
    hour_hot = {}
    for h, rs in sorted(hours.items()):
        hour_hot[h] = top20(frequency(rs))

    # H-bant özetleri
    band = Counter()
    for k, v in total_age.items():
        if k == "Yeni":
            band["Yeni"] += v
        else:
            a = int(k.split("-")[1])
            if a <= 3:
                band["H1-H3"] += v
            elif a <= 6:
                band["H4-H6"] += v
            elif a <= 14:
                band["H7-H14"] += v
            else:
                band["H15+"] += v

    cards = life_cards(day_rows)
    transition = transition_0102_0702(day_rows, groups_by_draw)

    return {
        "groups_by_draw": groups_by_draw,
        "total_age": total_age,
        "band": band,
        "day_freq": day_freq,
        "hour_hot": hour_hot,
        "cards": cards,
        "transition": transition,
        "draw_lines": draw_lines
    }

def format_day_report(date_obj, day_rows, a):
    total_slots = len(day_rows) * 20
    lines = []
    lines.append("="*92)
    lines.append(f"GÜN: {date_obj.strftime('%d.%m.%Y')} | ÇEKİLİŞ: {len(day_rows)} | TOPLAM REAL20 HÜCRESİ: {total_slots}")
    lines.append("="*92)
    lines.append("")

    lines.append("1) ÇEKİLİŞ BAZLI GERÇEK YAŞAM İZİ")
    lines.extend(a["draw_lines"])
    lines.append("")

    lines.append("2) GÜN GENEL H-KATMAN DAĞILIMI")
    for k in sorted(a["total_age"].keys(), key=h_sort_key):
        v = a["total_age"][k]
        pct = (100*v/total_slots) if total_slots else 0
        lines.append(f"{k}: {v} ({pct:.2f}%)")
    lines.append("")

    lines.append("3) H-BANT ÖZETİ")
    for k in ["H1-H3","H4-H6","H7-H14","H15+","Yeni"]:
        v = a["band"].get(k,0)
        pct = (100*v/total_slots) if total_slots else 0
        lines.append(f"{k}: {v} ({pct:.2f}%)")
    lines.append("")

    lines.append("4) GÜNÜN SICAK20'Sİ")
    for n,c in top20(a["day_freq"]):
        lines.append(f"{n}: {c}")
    lines.append("")

    lines.append("5) SAATLİK SICAK20")
    for h, arr in sorted(a["hour_hot"].items()):
        lines.append(f"{h}:00 BANDI")
        lines.append("  " + ", ".join([f"{n}({c})" for n,c in arr]))
    lines.append("")

    if a["transition"]:
        lines.append("6) 01:02 → 07:02 YAŞAM DEVAMLILIĞI")
        for k in sorted(a["transition"].keys(), key=h_sort_key):
            vals = a["transition"][k]
            lines.append(f"{k}: {len(vals)} -> {','.join(map(str, vals))}")
        lines.append("")

    lines.append("7) 1–80 YAŞAM KARTLARI")
    for n in range(1,81):
        c = a["cards"][n]
        gaps = ",".join(map(str,c["gaps"])) if c["gaps"] else "-"
        lines.append(
            f"{n:02d} | ilk={c['first'] if c['first'] else '-'} | "
            f"adet={c['count']} | son={c['last'] if c['last'] else '-'} | "
            f"tipik_donus=H-{c['mode_gap']}" if c['mode_gap'] else
            f"{n:02d} | ilk={c['first'] if c['first'] else '-'} | "
            f"adet={c['count']} | son={c['last'] if c['last'] else '-'} | tipik_donus=-"
        )
        # yukarıdaki satıra max uyku ve gap zinciri ekle
        lines[-1] += f" | max_uyku={c['max_gap'] if c['max_gap'] else '-'} | araliklar={gaps}"

    lines.append("")
    return "\n".join(lines)

def format_master_report(all_day_results):
    lines = []
    lines.append("HIZLI ON — 14 GÜN GERÇEK YAŞAM İZİ ANA RAPORU")
    lines.append("Kural: Her sayı yalnız çekilişten ÖNCEKİ en son görünümüne göre H yaşı alır. Gelecek bilgi yoktur.")
    lines.append("")

    master_age = Counter()
    master_freq = Counter()
    master_band = Counter()
    per_day_summary = []

    for date_obj, day_rows, a in all_day_results:
        master_age.update(a["total_age"])
        master_freq.update(a["day_freq"])
        master_band.update(a["band"])
        per_day_summary.append((date_obj, len(day_rows), a["band"], top20(a["day_freq"])))
        lines.append(format_day_report(date_obj, day_rows, a))

    lines.append("="*92)
    lines.append("14 GÜN BİRLEŞİK MAKRO ÖZET")
    lines.append("="*92)
    total_slots = sum(len(day_rows)*20 for _,day_rows,_ in all_day_results)
    total_draws = sum(len(day_rows) for _,day_rows,_ in all_day_results)
    lines.append(f"Toplam gün: {len(all_day_results)}")
    lines.append(f"Toplam çekiliş: {total_draws}")
    lines.append(f"Toplam REAL20 hücresi: {total_slots}")
    lines.append("")

    lines.append("A) TÜM 14 GÜN H-KATMAN DAĞILIMI")
    for k in sorted(master_age.keys(), key=h_sort_key):
        v = master_age[k]
        pct = (100*v/total_slots) if total_slots else 0
        lines.append(f"{k}: {v} ({pct:.2f}%)")
    lines.append("")

    lines.append("B) TÜM 14 GÜN H-BANT DAĞILIMI")
    for k in ["H1-H3","H4-H6","H7-H14","H15+","Yeni"]:
        v = master_band.get(k,0)
        pct = (100*v/total_slots) if total_slots else 0
        lines.append(f"{k}: {v} ({pct:.2f}%)")
    lines.append("")

    lines.append("C) TÜM 14 GÜN SICAK20")
    for n,c in top20(master_freq):
        lines.append(f"{n}: {c}")
    lines.append("")

    lines.append("D) GÜN GÜN KISA ÖZET")
    for date_obj, n_draws, band, hot in per_day_summary:
        total = n_draws*20
        btxt = " | ".join(
            f"{k}={band.get(k,0)}({(100*band.get(k,0)/total if total else 0):.1f}%)"
            for k in ["H1-H3","H4-H6","H7-H14","H15+","Yeni"]
        )
        hot_txt = ", ".join(f"{n}({c})" for n,c in hot[:10])
        lines.append(f"{date_obj.strftime('%d.%m.%Y')} | {btxt} | sıcak10: {hot_txt}")

    return "\n".join(lines)

# -----------------------------
# UI
# -----------------------------
st.sidebar.header("Veri Kaynağı")
source_mode = st.sidebar.radio("Kaynak", ["GitHub RAW bağlantısı", "TXT dosyası yükle"])

text = None
source_name = None

if source_mode == "GitHub RAW bağlantısı":
    gh_url = st.sidebar.text_input(
        "GitHub RAW / blob bağlantısı",
        placeholder="https://github.com/kullanici/repo/blob/main/veri.txt"
    )
    if gh_url:
        try:
            text = load_from_url(gh_url)
            source_name = gh_url
            st.sidebar.success("GitHub verisi alındı.")
        except Exception as e:
            st.sidebar.error(f"GitHub verisi alınamadı: {e}")
else:
    up = st.sidebar.file_uploader("TXT yükle", type=["txt"])
    if up is not None:
        text = up.getvalue().decode("utf-8", errors="replace")
        source_name = up.name

st.sidebar.markdown("---")
st.sidebar.caption("Beklenen satır biçimi:")
st.sidebar.code("51213;25.08.2026 00:02;2,4,6,...,80")

if text:
    try:
        rows = parse_txt(text)
    except Exception as e:
        st.error(str(e))
        st.stop()

    dates = sorted(set(r["date"] for r in rows))
    st.write(f"**Kaynak:** {source_name}")
    st.write(f"**Toplam çekiliş:** {len(rows)}")
    st.write(f"**Bulunan gün:** {len(dates)}")

    if len(dates) != 14:
        st.warning(f"Dosyada 14 yerine {len(dates)} farklı gün bulundu. App yine mevcut günlerin tamamını işler.")

    if st.button("14 GÜNÜ GÜN GÜN ANALİZ ET", type="primary", use_container_width=True):
        progress = st.progress(0)
        status = st.empty()
        results = []

        for i, d in enumerate(dates, start=1):
            status.write(f"{d.strftime('%d.%m.%Y')} analiz ediliyor... ({i}/{len(dates)})")
            day_rows = [r for r in rows if r["date"] == d]
            a = analyze_day(day_rows)
            results.append((d, day_rows, a))
            progress.progress(i/len(dates))

        report = format_master_report(results)
        st.session_state["report"] = report
        st.session_state["results"] = results
        status.success("Tüm günler tamamlandı. Tek birleşik rapor hazır.")

    if "results" in st.session_state:
        results = st.session_state["results"]
        summary_rows = []
        for d, day_rows, a in results:
            total = len(day_rows)*20
            summary_rows.append({
                "Gün": d.strftime("%d.%m.%Y"),
                "Çekiliş": len(day_rows),
                "H1-H3 %": round(100*a["band"].get("H1-H3",0)/total,2) if total else 0,
                "H4-H6 %": round(100*a["band"].get("H4-H6",0)/total,2) if total else 0,
                "H7-H14 %": round(100*a["band"].get("H7-H14",0)/total,2) if total else 0,
                "H15+ %": round(100*a["band"].get("H15+",0)/total,2) if total else 0,
                "Yeni %": round(100*a["band"].get("Yeni",0)/total,2) if total else 0,
            })
        st.subheader("Gün Gün Makro Özet")
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        report = st.session_state["report"]
        st.download_button(
            "TEK BİRLEŞİK TXT RAPORU İNDİR",
            data=report.encode("utf-8"),
            file_name="HIZLI_ON_14_GUN_GERCEK_YASAM_IZI_RAPORU.txt",
            mime="text/plain",
            use_container_width=True
        )

        with st.expander("Rapor önizleme"):
            st.text(report[:25000])
else:
    st.info("Soldan GitHub RAW bağlantısı gir veya TXT dosyası yükle.")
