
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import re
from datetime import datetime
from pathlib import Path

DB_FILE = "hizli_on_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS draws (
            draw_id INTEGER PRIMARY KEY,
            draw_time TEXT,
            numbers TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_all_draws():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(
        "SELECT * FROM draws ORDER BY draw_time DESC, draw_id DESC",
        conn
    )
    conn.close()
    return df

def parse_numbers(text):
    nums = [int(x) for x in re.findall(r"\d+", str(text))]
    nums = list(dict.fromkeys(nums))
    return nums

def validate_numbers(nums):
    if len(nums) != 20:
        return False, f"Tam 20 farklı sayı gerekli. Girilen sayı adedi: {len(nums)}"
    if not all(1 <= n <= 80 for n in nums):
        return False, "Tüm sayılar 1–80 arasında olmalı."
    return True, ""

def import_bulk_text(raw_text):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    errors = []

    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip().replace("\ufeff", "")
        if not line:
            continue

        parts = line.split(";", 2)
        if len(parts) < 3:
            skipped += 1
            errors.append(f"Satır {line_no}: biçim tanınmadı")
            continue

        try:
            draw_id = int(parts[0].strip())
            draw_time = parts[1].strip()
            nums = parse_numbers(parts[2])

            ok, msg = validate_numbers(nums)
            if not ok:
                skipped += 1
                errors.append(f"Satır {line_no}: {msg}")
                continue

            numbers = ",".join(map(str, nums))
            cursor.execute(
                "INSERT OR IGNORE INTO draws (draw_id, draw_time, numbers) VALUES (?, ?, ?)",
                (draw_id, draw_time, numbers)
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

def add_single_draw(draw_id, draw_time, nums):
    ok, msg = validate_numbers(nums)
    if not ok:
        return False, msg

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO draws (draw_id, draw_time, numbers) VALUES (?, ?, ?)",
            (int(draw_id), draw_time, ",".join(map(str, nums)))
        )
        conn.commit()
        return True, "Çekiliş kaydedildi."
    except sqlite3.IntegrityError:
        return False, f"{draw_id} numaralı çekiliş zaten kayıtlı."
    finally:
        conn.close()

def build_frequency(df):
    all_numbers = []
    for nums in df["numbers"]:
        all_numbers.extend(parse_numbers(nums))
    if not all_numbers:
        return {}
    return pd.Series(all_numbers).value_counts().to_dict()

def generate_tickets(freq, ticket_size, ticket_count, consecutive=True, skip_one=True):
    if not freq:
        return []

    sorted_nums = [int(k) for k, _ in sorted(freq.items(), key=lambda item: item[1], reverse=True)]
    base_pool = sorted_nums[:40] if len(sorted_nums) >= 40 else sorted_nums[:]

    if len(base_pool) < ticket_size:
        return []

    tickets = []
    attempts = 0

    while len(tickets) < ticket_count and attempts < 500:
        attempts += 1
        ticket = set()

        if consecutive:
            candidates = [x for x in base_pool if x <= 78 and x+1 <= 80 and x+2 <= 80]
            if candidates:
                start = random.choice(candidates)
                ticket.update([start, start+1, start+2])

        if skip_one:
            candidates = [x for x in base_pool if x <= 76 and x+2 <= 80 and x+4 <= 80]
            if candidates:
                start = random.choice(candidates)
                ticket.update([start, start+2, start+4])

        while len(ticket) < ticket_size:
            ticket.add(random.choice(base_pool))

        # Eğer yapı kuralları kupon boyutunu aştıysa frekans önceliğine göre koru.
        if len(ticket) > ticket_size:
            ticket = set(sorted(ticket, key=lambda n: freq.get(n, 0), reverse=True)[:ticket_size])

        result = tuple(sorted(ticket))
        if result not in tickets:
            tickets.append(result)

    return tickets

init_db()

st.set_page_config(page_title="Hızlı On Analiz Motoru", page_icon="🎯", layout="wide")
st.title("🎯 Hızlı On - Canlı Takip & Kombinasyon Motoru")
st.caption("SQLite kalıcı hafıza + toplu veri yükleme + tek çekiliş ekleme + yapısal kupon üretimi")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Kupon Üretici",
    "➕ Tek Çekiliş Ekle",
    "📂 14 Günlük Veri Toplu Yükleme",
    "🗃️ Kayıtlı Veriler"
])

with tab3:
    st.header("📂 14 Günlük Veri Setini Yükle")
    st.write("Beklenen satır biçimi:")
    st.code("51213;25.08.2026 00:02;2,4,6,9,13,18,19,20,21,24,32,34,40,48,51,55,61,62,63,80")

    uploaded_file = st.file_uploader(
        "veri.txt veya CSV/TXT dosyanızı seçin",
        type=["txt", "csv"],
        key="bulk_upload"
    )

    if uploaded_file is not None:
        try:
            raw = uploaded_file.getvalue().decode("utf-8-sig", errors="ignore")
            if st.button("Veriyi Kalıcı Hafızaya Aktar", type="primary"):
                inserted, skipped, errors = import_bulk_text(raw)
                st.success(f"{inserted} yeni çekiliş kalıcı olarak kaydedildi.")
                if skipped:
                    st.warning(f"{skipped} satır atlandı veya zaten kayıtlıydı.")
                if errors:
                    with st.expander("Atlanan satır ayrıntıları"):
                        for e in errors[:100]:
                            st.write(e)
        except Exception as e:
            st.error(f"Hata oluştu: {e}")

with tab2:
    st.header("➕ Anlık Çekiliş Ekle (Kalıcı Hafıza)")
    with st.form("single_draw"):
        new_id = st.number_input(
            "Çekiliş Numarası",
            min_value=1,
            step=1
        )
        new_time = st.text_input(
            "Tarih ve Saat",
            datetime.now().strftime("%d.%m.%Y %H:%M")
        )
        new_nums = st.text_area(
            "Çıkan 20 sayı (virgül, boşluk veya ; ile ayırabilirsiniz)",
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20"
        )
        submit_btn = st.form_submit_button("Çekilişi Hafızaya Kaydet")

        if submit_btn:
            nums = parse_numbers(new_nums)
            ok, msg = add_single_draw(new_id, new_time, nums)
            if ok:
                st.success(f"{new_id} numaralı çekiliş kalıcı veri havuzuna eklendi.")
            else:
                st.error(msg)

with tab1:
    st.header("🔮 İstatistiki Ritmik Kupon Üretici")
    df_draws = get_all_draws()

    if df_draws.empty:
        st.warning("Veri tabanında kayıtlı çekiliş yok. Önce toplu veri yükleyin veya tek çekiliş ekleyin.")
    else:
        st.info(f"Sistemde toplam **{len(df_draws)}** çekiliş kalıcı olarak kayıtlı.")

        freq = build_frequency(df_draws)
        freq_df = pd.DataFrame(
            sorted(freq.items(), key=lambda x: x[1], reverse=True),
            columns=["Sayı", "Frekans"]
        )

        c1, c2 = st.columns([1, 2])
        with c1:
            ticket_size = st.selectbox("Kupon Tipi", [4, 5, 10], index=2)
            ticket_count = st.slider("Kaç kupon?", 1, 10, 5)

        with c2:
            st.write("### En aktif sayılar")
            st.dataframe(freq_df.head(20), use_container_width=True, hide_index=True)

        st.sidebar.header("🎛️ Ritim Parametreleri")
        skip_one = st.sidebar.checkbox("Sıçrama (Skip-One) Filtresi", value=True)
        consecutive = st.sidebar.checkbox("Ardışık Blok Filtresi", value=True)

        if st.button("Ritmik Formülle Kupon Üret", type="primary"):
            tickets = generate_tickets(
                freq,
                ticket_size=ticket_size,
                ticket_count=ticket_count,
                consecutive=consecutive,
                skip_one=skip_one
            )

            if not tickets:
                st.error("Kupon üretmek için yeterli veri yok.")
            else:
                st.write(f"### 🎯 Yapısal {ticket_size}'li Kuponlar")
                for idx, ticket in enumerate(tickets, 1):
                    st.subheader(f"Kolon {idx}: `{', '.join(map(str, ticket))}`")

with tab4:
    st.header("🗃️ Kalıcı Veri Havuzu")
    df_draws = get_all_draws()
    if df_draws.empty:
        st.info("Kayıt yok.")
    else:
        st.metric("Toplam Kayıt", len(df_draws))
        st.dataframe(df_draws, use_container_width=True, height=600)

        csv_data = df_draws.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Kayıtları CSV Olarak İndir",
            data=csv_data,
            file_name="hizli_on_kayitli_veriler.csv",
            mime="text/csv"
        )
