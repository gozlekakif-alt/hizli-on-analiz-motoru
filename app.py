
import streamlit as st
import pandas as pd
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Hızlı On - Gerçek Yaşam İzi", layout="wide")

st.title("Hızlı On — 14 Gün Gerçek Yaşam İzi Analiz Motoru")
st.caption("Aynı GitHub reposundaki veri.txt dosyasını otomatik okur; 14 günü gün gün analiz eder ve tek birleşik TXT rapor üretir.")

DATA_FILE = Path(__file__).with_name("veri.txt")

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
            "nums": sorted(nums),
        })
    rows.sort(key=lambda r: r["dt"])
    return rows

def age_groups_for_day(day_rows):
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

def frequency(rows):
    c = Counter()
    for r in rows:
        c.update(r["nums"])
    return c

def top20(c):
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:20]

def life_cards(day_rows):
    pos = defaultdict(list)
    for i, r in enumerate(day_rows, start=1):
        for n in r["nums"]:
            pos[n].append(i)
    cards = {}
    for n in range(1, 81):
        seq = pos.get(n, [])
        if not seq:
            cards[n] = {"first": None, "count": 0, "gaps": [], "mode_gap": None, "max_gap": None, "last": None}
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
            "last": seq[-1],
        }
    return cards

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
            f"{row['draw_no']} | {row['dt'].strftime('%d.%m.%Y %H:%M')} | " + " | ".join(parts)
        )

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

    by_hour = defaultdict(list)
    for r in day_rows:
        by_hour[r["dt"].strftime("%H")].append(r)

    return {
        "groups_by_draw": groups_by_draw,
        "total_age": total_age,
        "band": band,
        "day_freq": frequency(day_rows),
        "hour_hot": {h: top20(frequency(rs)) for h, rs in sorted(by_hour.items())},
        "cards": life_cards(day_rows),
        "draw_lines": draw_lines,
    }

def format_day_report(date_obj, day_rows, a):
    total_slots = len(day_rows) * 20
    lines = []
    lines.append("="*92)
    lines.append(f"GÜN: {date_obj.strftime('%d.%m.%Y')} | ÇEKİLİŞ: {len(day_rows)} | REAL20 HÜCRESİ: {total_slots}")
    lines.append("="*92)
    lines.append("")
    lines.append("1) ÇEKİLİŞ BAZLI GERÇEK YAŞAM İZİ")
    lines.extend(a["draw_lines"])
    lines.append("")
    lines.append("2) H-KATMAN DAĞILIMI")
    for k in sorted(a["total_age"].keys(), key=h_sort_key):
        v = a["total_age"][k]
        pct = 100*v/total_slots if total_slots else 0
        lines.append(f"{k}: {v} ({pct:.2f}%)")
    lines.append("")
    lines.append("3) H-BANT ÖZETİ")
    for k in ["H1-H3","H4-H6","H7-H14","H15+","Yeni"]:
        v = a["band"].get(k, 0)
        pct = 100*v/total_slots if total_slots else 0
        lines.append(f"{k}: {v} ({pct:.2f}%)")
    lines.append("")
    lines.append("4) GÜN SICAK20")
    lines.append(", ".join(f"{n}({c})" for n,c in top20(a["day_freq"])))
    lines.append("")
    lines.append("5) SAATLİK SICAK20")
    for h, arr in a["hour_hot"].items():
        lines.append(f"{h}:00 -> " + ", ".join(f"{n}({c})" for n,c in arr))
    lines.append("")
    lines.append("6) 1–80 YAŞAM KARTLARI")
    for n in range(1,81):
        c = a["cards"][n]
        gaps = ",".join(map(str, c["gaps"])) if c["gaps"] else "-"
        lines.append(
            f"{n:02d} | ilk={c['first'] or '-'} | adet={c['count']} | son={c['last'] or '-'} | "
            f"tipik_donus={'H-'+str(c['mode_gap']) if c['mode_gap'] else '-'} | "
            f"max_uyku={c['max_gap'] or '-'} | araliklar={gaps}"
        )
    lines.append("")
    return "\n".join(lines)

def format_master_report(results):
    lines = []
    lines.append("HIZLI ON — 14 GÜN GERÇEK YAŞAM İZİ ANA RAPORU")
    lines.append("Kural: Her sayı yalnız o çekilişten önceki en son görünümüne göre H yaşı alır. Gelecek bilgi kullanılmaz.")
    lines.append("")
    master_age = Counter()
    master_band = Counter()
    master_freq = Counter()

    for d, day_rows, a in results:
        master_age.update(a["total_age"])
        master_band.update(a["band"])
        master_freq.update(a["day_freq"])
        lines.append(format_day_report(d, day_rows, a))

    total_slots = sum(len(day_rows)*20 for _, day_rows, _ in results)
    lines.append("="*92)
    lines.append("14 GÜN BİRLEŞİK MAKRO ÖZET")
    lines.append("="*92)
    lines.append(f"Toplam gün: {len(results)}")
    lines.append(f"Toplam çekiliş: {sum(len(day_rows) for _, day_rows, _ in results)}")
    lines.append(f"Toplam REAL20 hücresi: {total_slots}")
    lines.append("")
    lines.append("A) TÜM H-KATMANLARI")
    for k in sorted(master_age.keys(), key=h_sort_key):
        v = master_age[k]
        lines.append(f"{k}: {v} ({100*v/total_slots:.2f}%)")
    lines.append("")
    lines.append("B) TÜM H-BANTLARI")
    for k in ["H1-H3","H4-H6","H7-H14","H15+","Yeni"]:
        v = master_band.get(k, 0)
        lines.append(f"{k}: {v} ({100*v/total_slots:.2f}%)")
    lines.append("")
    lines.append("C) 14 GÜN SICAK20")
    lines.append(", ".join(f"{n}({c})" for n,c in top20(master_freq)))
    lines.append("")
    return "\n".join(lines)

if not DATA_FILE.exists():
    st.error("veri.txt bulunamadı. app.py ile veri.txt aynı GitHub klasöründe olmalı.")
    st.stop()

try:
    text = DATA_FILE.read_text(encoding="utf-8")
except UnicodeDecodeError:
    text = DATA_FILE.read_text(encoding="latin-1")

try:
    rows = parse_txt(text)
except Exception as e:
    st.error(f"veri.txt okunamadı: {e}")
    st.stop()

dates = sorted(set(r["date"] for r in rows))

c1, c2, c3 = st.columns(3)
c1.metric("Toplam Gün", len(dates))
c2.metric("Toplam Çekiliş", len(rows))
c3.metric("Beklenen 14 Gün", "TAMAM" if len(dates) == 14 else f"{len(dates)} gün")

if len(dates) != 14:
    st.warning(f"veri.txt içinde 14 yerine {len(dates)} farklı gün bulundu.")

if st.button("14 GÜNÜ GÜN GÜN ANALİZ ET", type="primary", use_container_width=True):
    progress = st.progress(0)
    status = st.empty()
    results = []

    for i, d in enumerate(dates, start=1):
        day_rows = [r for r in rows if r["date"] == d]
        status.write(f"{d.strftime('%d.%m.%Y')} analiz ediliyor... ({i}/{len(dates)})")
        a = analyze_day(day_rows)
        results.append((d, day_rows, a))
        progress.progress(i/len(dates))

    report = format_master_report(results)
    st.session_state["results"] = results
    st.session_state["report"] = report
    status.success("Bitti. Günler ayrı ayrı işlendi ve tek birleşik rapor hazırlandı.")

if "results" in st.session_state:
    results = st.session_state["results"]
    table = []
    for d, day_rows, a in results:
        total = len(day_rows)*20
        table.append({
            "Gün": d.strftime("%d.%m.%Y"),
            "Çekiliş": len(day_rows),
            "H1-H3 %": round(100*a["band"].get("H1-H3",0)/total,2),
            "H4-H6 %": round(100*a["band"].get("H4-H6",0)/total,2),
            "H7-H14 %": round(100*a["band"].get("H7-H14",0)/total,2),
            "H15+ %": round(100*a["band"].get("H15+",0)/total,2),
            "Yeni %": round(100*a["band"].get("Yeni",0)/total,2),
        })
    st.subheader("Gün Gün Makro Özet")
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    report = st.session_state["report"]
    st.download_button(
        "TEK BİRLEŞİK TXT RAPORU İNDİR",
        data=report.encode("utf-8"),
        file_name="HIZLI_ON_14_GUN_GERCEK_YASAM_IZI_RAPORU.txt",
        mime="text/plain",
        use_container_width=True,
    )

    with st.expander("Rapor önizleme"):
        st.text(report[:25000])
