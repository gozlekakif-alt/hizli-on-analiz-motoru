
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import re
from datetime import datetime

# ============================================================
# HIZLI ON - KARAKTER ANALIZI & OTOMATIK BASARI TAKIP MOTORU
# ============================================================

DB_FILE = "hizli_on_karakter_motoru.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS draws (
            draw_id INTEGER PRIMARY KEY,
            draw_time TEXT,
            numbers TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_draw_id INTEGER,
            coupon_type TEXT,
            numbers TEXT,
            checked INTEGER DEFAULT 0,
            hit_count INTEGER DEFAULT 0,
            matched_numbers TEXT DEFAULT ''
        )
    """)

    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def parse_numbers(text):
    nums = [int(x) for x in re.findall(r"\d+", str(text))]
    return list(dict.fromkeys(nums))

def validate_draw_numbers(nums):
    if len(nums) != 20:
        return False, f"Tam 20 farklı sayı gerekli. Girilen sayı adedi: {len(nums)}"
    if not all(1 <= n <= 80 for n in nums):
        return False, "Tüm sayılar 1–80 arasında olmalı."
    return True, ""

def load_draws():
    conn = get_db_connection()
    df = pd.read_sql_query(
        "SELECT * FROM draws ORDER BY draw_id DESC",
        conn
    )
    conn.close()
    return df

def load_generated_coupons():
    conn = get_db_connection()
    df = pd.read_sql_query(
        "SELECT * FROM generated_coupons ORDER BY id DESC",
        conn
    )
    conn.close()
    return df

def add_draw(draw_id, draw_time, nums):
    ok, msg = validate_draw_numbers(nums)
    if not ok:
        return False, msg

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO draws (draw_id, draw_time, numbers) VALUES (?, ?, ?)",
            (int(draw_id), draw_time, ",".join(map(str, nums)))
        )
        conn.commit()
        return True, f"{draw_id} numaralı çekiliş kaydedildi."
    except sqlite3.IntegrityError:
        return False, f"{draw_id} numaralı çekiliş zaten kayıtlı."
    finally:
        conn.close()

def bulk_import(raw_text):
    conn = get_db_connection()
    cursor = conn.cursor()

    inserted = 0
    skipped = 0
    errors = []

    for line_no, raw in enumerate(raw_text.splitlines(), start=1):
        line = raw.strip().replace("\ufeff", "")
        if not line:
            continue

        parts = line.split(";", 2)
        if len(parts) != 3:
            skipped += 1
            errors.append(f"Satır {line_no}: biçim tanınmadı")
            continue

        try:
            draw_id = int(parts[0].strip())
            draw_time = parts[1].strip()
            nums = parse_numbers(parts[2])

            ok, msg = validate_draw_numbers(nums)
            if not ok:
                skipped += 1
                errors.append(f"Satır {line_no}: {msg}")
                continue

            cursor.execute(
                "INSERT OR IGNORE INTO draws (draw_id, draw_time, numbers) VALUES (?, ?, ?)",
                (draw_id, draw_time, ",".join(map(str, nums)))
            )

            if cursor.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

        except Exception as e:
            skipped += 1
            errors.append(f"Satır {line_no}: {e}")

    conn.commit()
    conn.close()
    return inserted, skipped, errors

def check_pending_coupons():
    """
    Her kuponu yalnız kendi hedef çekiliş sonucu ile kontrol eder.
    Böylece target_draw_id <= last_id gibi yanlış eşleşme olmaz.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT gc.id, gc.target_draw_id, gc.numbers, gc.coupon_type, d.numbers
        FROM generated_coupons gc
        JOIN draws d ON d.draw_id = gc.target_draw_id
        WHERE gc.checked = 0
        ORDER BY gc.target_draw_id ASC, gc.id ASC
    """)
    rows = cursor.fetchall()

    results = []
    for c_id, target_draw_id, coupon_nums_str, coupon_type, real_nums_str in rows:
        c_nums = set(parse_numbers(coupon_nums_str))
        real_nums = set(parse_numbers(real_nums_str))

        hits = sorted(c_nums.intersection(real_nums))
        hit_count = len(hits)

        cursor.execute("""
            UPDATE generated_coupons
            SET checked = 1,
                hit_count = ?,
                matched_numbers = ?
            WHERE id = ?
        """, (hit_count, ",".join(map(str, hits)), c_id))

        results.append({
            "target_draw_id": target_draw_id,
            "type": coupon_type,
            "numbers": sorted(c_nums),
            "hit": hit_count,
            "total": len(c_nums),
            "matched_nums": hits
        })

    conn.commit()
    conn.close()
    return results

def build_character_pools(df_draws):
    """
    Kullanıcının verdiği karakter mantığını korur:
    - H1: son elden gelenler
    - dinlenen: önceki 1-2 ellerde olup son elde olmayanlar
    - uzun uyku: son 15 elde hiç görünmeyenler
    """
    matrix = []
    for nums in df_draws["numbers"]:
        row = parse_numbers(nums)
        if len(row) == 20:
            matrix.append(row)

    last_draw_nums = matrix[0] if len(matrix) > 0 else []
    prev_draw_nums = matrix[1] if len(matrix) > 1 else []
    prev2_draw_nums = matrix[2] if len(matrix) > 2 else []

    elden_ele_havuzu = sorted(set(last_draw_nums))

    dinlenen_havuz = sorted(
        set(prev_draw_nums + prev2_draw_nums) - set(last_draw_nums)
    )

    son_15_cikanlar = set(
        num
        for draw in matrix[:15]
        for num in draw
    )

    uyku_havuzu = sorted(set(range(1, 81)) - son_15_cikanlar)

    if not uyku_havuzu:
        uyku_havuzu = sorted(set(range(1, 81)) - set(last_draw_nums))

    return matrix, elden_ele_havuzu, dinlenen_havuz, uyku_havuzu

def safe_sample(pool, k):
    if k <= 0 or not pool:
        return []
    return random.sample(pool, min(len(pool), k))

def generate_character_coupons(df_draws, target_size, count=5):
    matrix, h1_pool, rest_pool, sleep_pool = build_character_pools(df_draws)

    n_h1 = max(1, int(target_size * 0.4))
    n_rest = max(1, int(target_size * 0.4))
    n_sleep = max(1, target_size - n_h1 - n_rest)

    coupons = []
    attempts = 0

    while len(coupons) < count and attempts < 500:
        attempts += 1

        coupon = set()
        coupon.update(safe_sample(h1_pool, n_h1))
        coupon.update(safe_sample(rest_pool, n_rest))
        coupon.update(safe_sample(sleep_pool, n_sleep))

        # Eksik kaldığında 1-80 arasından tamamla
        while len(coupon) < target_size:
            coupon.add(random.randint(1, 80))

        # Fazlalık varsa, önce karakter havuzundan gelenleri korumaya çalış
        priority = []
        for n in sorted(coupon):
            score = 0
            if n in h1_pool:
                score += 3
            if n in rest_pool:
                score += 2
            if n in sleep_pool:
                score += 1
            priority.append((score, n))

        final_coupon = tuple(
            sorted([n for _, n in sorted(priority, reverse=True)[:target_size]])
        )

        if final_coupon not in coupons:
            coupons.append(final_coupon)

    return coupons, {
        "H1_havuzu": h1_pool,
        "Dinlenen_havuz": rest_pool,
        "Uyku_havuzu": sleep_pool,
        "n_H1": n_h1,
        "n_Dinlenen": n_rest,
        "n_Uyku": n_sleep,
    }

def save_generated_coupons(target_draw_id, coupon_type, coupons):
    conn = get_db_connection()
    cursor = conn.cursor()

    for coupon in coupons:
        cursor.execute("""
            INSERT INTO generated_coupons (
                target_draw_id,
                coupon_type,
                numbers
            )
            VALUES (?, ?, ?)
        """, (
            int(target_draw_id),
            coupon_type,
            ",".join(map(str, coupon))
        ))

    conn.commit()
    conn.close()

init_db()

st.set_page_config(
    page_title="Hızlı On Karakter Analiz Motoru",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 Hızlı On - Karakter Analizi & Otomatik Başarı Takip Motoru")
st.caption(
    "Kalıcı SQLite hafıza • karakter havuzları • kupon kaydı • hedef çekiliş bazında otomatik isabet kontrolü"
)

# ------------------------------------------------------------
# Otomatik başarı kontrolü
# ------------------------------------------------------------
new_reports = check_pending_coupons()

if new_reports:
    st.subheader("📢 Yeni Tahmin Başarı Raporları")

    for target_id in sorted(set(r["target_draw_id"] for r in new_reports)):
        st.markdown(f"### Çekiliş No {target_id}")

        rows = [r for r in new_reports if r["target_draw_id"] == target_id]
        cols = st.columns(min(len(rows), 5))

        for i, rpt in enumerate(rows):
            with cols[i % len(cols)]:
                st.metric(
                    label=rpt["type"],
                    value=f"{rpt['total']}'de {rpt['hit']} İSABET",
                    delta=(
                        f"Tutanlar: {rpt['matched_nums']}"
                        if rpt["hit"] > 0
                        else "İsabet yok"
                    )
                )
        st.markdown("---")

# ------------------------------------------------------------
# Sekmeler
# ------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "🔮 Karakter Bazlı Kupon Üretici",
    "➕ Tek Yeni Çekiliş Ekle",
    "📂 Toplu Geçmiş Yükle",
    "📈 Başarı Geçmişi"
])

with tab3:
    st.subheader("📂 14 Günlük Ana Veriyi Toplu Yükleme")

    st.code(
        "51213;25.08.2026 00:02;2,4,6,9,13,18,19,20,21,24,32,34,40,48,51,55,61,62,63,80"
    )

    uploaded_file = st.file_uploader(
        "veri.txt veya CSV/TXT dosyasını seçin",
        type=["txt", "csv"],
        key="history_upload"
    )

    if uploaded_file is not None:
        raw = uploaded_file.getvalue().decode("utf-8-sig", errors="ignore")

        if st.button("Geçmiş Veriyi Kalıcı Hafızaya Aktar", type="primary"):
            inserted, skipped, errors = bulk_import(raw)

            st.success(f"{inserted} yeni çekiliş kalıcı hafızaya işlendi.")

            if skipped:
                st.warning(f"{skipped} satır atlandı veya zaten kayıtlıydı.")

            if errors:
                with st.expander("Atlanan satır ayrıntıları"):
                    for err in errors[:100]:
                        st.write(err)

            st.rerun()

with tab2:
    st.subheader("➕ Yeni Çekiliş Giriş Formu")

    with st.form("add_draw_form"):
        c_id = st.number_input(
            "Çekiliş No",
            min_value=1,
            step=1
        )

        c_time = st.text_input(
            "Tarih / Saat",
            datetime.now().strftime("%d.%m.%Y %H:%M")
        )

        c_nums = st.text_area(
            "Çıkan 20 sayı (boşluk, virgül veya ; ile ayırabilirsiniz)",
            placeholder="Örn: 1 2 10 18 20 ..."
        )

        save_btn = st.form_submit_button(
            "Çekilişi Havuza Kaydet ve Kuponları Kontrol Et"
        )

        if save_btn:
            nums = parse_numbers(c_nums)

            ok, msg = add_draw(
                c_id,
                c_time,
                nums
            )

            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

with tab1:
    st.subheader("🔮 Oyunun Karakterine Göre Otomatik Kupon Üretimi")

    df_draws = load_draws()

    if df_draws.empty:
        st.warning(
            "Veri tabanında analiz edilecek çekiliş bulunamadı. "
            "Önce toplu veri yükleyin veya yeni çekiliş ekleyin."
        )
    else:
        total_draws_count = len(df_draws)
        latest_id = int(df_draws.iloc[0]["draw_id"])

        c1, c2 = st.columns(2)

        with c1:
            st.metric("Taranan çekiliş", total_draws_count)

        with c2:
            st.metric("Son çekiliş no", latest_id)

        game_style = st.selectbox(
            "Üretilecek Kupon Hücre Yapısı",
            [
                "4'lü İstatistiki Kupon",
                "5'li İstatistiki Kupon",
                "10'lu Klasik Kupon"
            ]
        )

        size_map = {
            "4'lü İstatistiki Kupon": 4,
            "5'li İstatistiki Kupon": 5,
            "10'lu Klasik Kupon": 10
        }

        target_size = size_map[game_style]

        matrix, h1_pool, rest_pool, sleep_pool = build_character_pools(df_draws)

        with st.expander("Karakter Havuzlarını Göster"):
            st.write("**H1 / Elden Ele:**", h1_pool)
            st.write("**Dinlenip Gelen Adaylar:**", rest_pool)
            st.write("**15 El Uzun Uyku Adayları:**", sleep_pool)

        if st.button(
            "🚀 Karakter Kalıplarını Çalıştır ve Yeni Kuponları Ver",
            type="primary"
        ):
            next_target_id = latest_id + 1

            coupons, meta = generate_character_coupons(
                df_draws,
                target_size,
                count=5
            )

            if not coupons:
                st.error("Kupon üretilemedi.")
            else:
                st.write(
                    f"### 🎯 Çekiliş No {next_target_id} İçin "
                    f"Karakteristik Tahmin Kombinasyonları"
                )

                for idx, coupon in enumerate(coupons, start=1):
                    st.markdown(
                        f"**Kolon {idx}:** `{', '.join(map(str, coupon))}`"
                    )

                save_generated_coupons(
                    next_target_id,
                    game_style,
                    coupons
                )

                st.success(
                    f"5 kupon Çekiliş No {next_target_id} için kalıcı hafızaya alındı. "
                    "Sonucu eklediğiniz anda app kendi hedef çekilişiyle otomatik kontrol edecek."
                )

with tab4:
    st.subheader("📈 Üretilen Kuponlar ve Başarı Geçmişi")

    coupons_df = load_generated_coupons()

    if coupons_df.empty:
        st.info("Henüz kaydedilmiş kupon yok.")
    else:
        view = coupons_df.copy()

        view["Durum"] = view["checked"].map({
            0: "Bekliyor",
            1: "Kontrol edildi"
        })

        view = view[
            [
                "id",
                "target_draw_id",
                "coupon_type",
                "numbers",
                "Durum",
                "hit_count",
                "matched_numbers"
            ]
        ]

        st.dataframe(
            view,
            use_container_width=True,
            height=600
        )

        checked = coupons_df[coupons_df["checked"] == 1]

        if not checked.empty:
            st.markdown("### Genel Başarı Özeti")

            summary = (
                checked.groupby("coupon_type")
                .agg(
                    kolon=("id", "count"),
                    ortalama_isabet=("hit_count", "mean"),
                    max_isabet=("hit_count", "max")
                )
                .reset_index()
            )

            st.dataframe(
                summary,
                use_container_width=True,
                hide_index=True
            )
