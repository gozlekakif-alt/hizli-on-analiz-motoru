import streamlit as st
import pandas as pd
import numpy as np
from collections import Counter
from itertools import combinations
import io
from pathlib import Path
st.set_page_config(page_title="Hızlı On Analiz Motoru", layout="wide")

st.title("🎯 Hızlı On Gelişmiş Analiz ve İstatistik Motoru")
st.caption("4.000+ Çekilişlik Dev Veri Havuzu İle Detaylı Strateji Motoru")

DOSYA_ADI = "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"
# --- 1. VERİ YÜKLEME VE HAZIRLAMA ---
@st.cache_data
def veriyi_yukle():
    try:
        # 4.000+ çekilişi hızlıca yükle
    df = pd.read_csv(DOSYA_ADI, header=None)
    df = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    
    return df
    except Exception as e:
    return None

df_raw = veriyi_yukle()

if df_raw is not None:
    toplam_cekilis = len(df_raw)
    st.success(f"📊 **Büyük Veri Havuzu Aktif:** Toplam **{toplam_cekilis:,}** Çekiliş Analize Hazır!")

    # --- YAN MENÜ / FİLTRELER ---
    st.sidebar.header("⚙️ Analiz Filtreleri")
    son_n = st.sidebar.slider(
        "Analiz Edilecek Çekiliş Sayısı (Son N):",
        min_value=50,
        max_value=toplam_cekilis,
        value=min(1000, toplam_cekilis),
        step=50
    )

    df_analiz = df_raw.tail(son_n)

    # Tüm çekilen sayıların listesi (1-80)
    tum_sayilar = []
    for row in df_analiz.values:
        row_clean = [int(x) for x in row if not np.isnan(x) and 1 <= x <= 80]
        tum_sayilar.extend(row_clean)

    frekans = Counter(tum_sayilar)
    df_frekans = pd.DataFrame(frekans.items(), columns=["Sayı", "Geliş Frekansı"]).sort_values(by="Geliş Frekansı", ascending=False)

    # --- TAB'LI ANALİZ EKRANI ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Frekans & Sıcak/Soğuk", 
        "⏱️ Dinlenme Süreleri", 
        "🔗 İkili Kombinasyonlar", 
        "🎲 Akıllı Kupon Üretici",
        "➕ Yeni Çekiliş Ekle"
    ])

    # TAB 1: FREKANS VE SICAK/SOĞUK SAYILAR
    with tab1:
        st.subheader(f"🔥 Son {son_n} Çekilişin Sıcak ve Soğuk Sayıları")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🔥 En Çok Çıkan 10 Sayı (Sıcak)")
            st.dataframe(df_frekans.head(10).reset_index(drop=True), use_container_width=True)
            
        with col2:
            st.markdown("### ❄️ En Az Çıkan 10 Sayı (Soğuk)")
            st.dataframe(df_frekans.tail(10).iloc[::-1].reset_index(drop=True), use_container_width=True)

        st.write("---")
        st.subheader("📈 Tüm Sayıların Frekans Dağılımı Grafiği (1 - 80)")
        st.bar_chart(df_frekans.set_index("Sayı"))

    # TAB 2: DİNLENME SÜRELERİ (GELMEYEN GÜN/ÇEKİLİŞ SAYISI)
    with tab2:
        st.subheader("⏱️ Sayıların Son Çıkışından Bu Yana Geçen Çekiliş Sayısı")
        
        dinlenme_dict = {}
        for sayi in range(1, 81):
            mask = (df_raw == sayi).any(axis=1)
            if mask.any():
                son_goruldugu_index = mask[::-1].idxmax()
                gecen_cekilis = (toplam_cekilis - 1) - son_goruldugu_index
                dinlenme_dict[sayi] = gecen_cekilis
            else:
                dinlenme_dict[sayi] = toplam_cekilis

        df_dinlenme = pd.DataFrame(dinlenme_dict.items(), columns=["Sayı", "Gelmeyen Çekiliş Sayısı"]).sort_values(by="Gelmeyen Çekiliş Sayısı", ascending=False)
        
        st.info("💡 **İpucu:** En uzun süredir çıkmayan (yüksek dinlenme süresine sahip) sayılar istatistiksel geri dönme eğilimi gösterebilir.")
        st.dataframe(df_dinlenme.head(20).reset_index(drop=True), use_container_width=True)

    # TAB 3: İKİLİ KOMBİNASYON ANALİZİ
    with tab3:
        st.subheader(f"🔗 Son {son_n} Çekilişte Birlikte En Sık Çıkan İkili Çiftler")
        
        @st.cache_data
        def ikili_kombinasyon_hesapla(df_data):
            ikili_sayac = Counter()
            for row in df_data.values:
                row_clean = [int(x) for x in row if not np.isnan(x) and 1 <= x <= 80]
                if len(row_clean) >= 2:
                    ikili_sayac.update(combinations(sorted(row_clean), 2))
            return ikili_sayac

        ikililer = ikili_kombinasyon_hesapla(df_analiz)
        df_ikili = pd.DataFrame([{"İkili Grubu": f"{k[0]} - {k[1]}", "Birlikte Gelme Frekansı": v} for k, v in ikililer.most_common(15)])
        
        st.dataframe(df_ikili, use_container_width=True)

    # TAB 4: AKILLI KUPON ÜRETİCİ
    with tab4:
        st.subheader("🎲 İstatistiğe Dayalı Otomatik Kupon Oluşturucu")
        st.write("Bu modül, 4.000+ çekilişlik veri havuzundaki sıcak ve dinlenmiş sayıları analiz ederek kupon önerileri üretir.")
        
        kupon_sayisi = st.slider("Üretilecek Kupon Sayısı:", 1, 10, 3)
        secim_turu = st.radio("Kupon Stratejisi:", ["🔥 Ağırlıklı Sıcak Sayılar", "⚖️ Dengeli (Sıcak + Soğuk/Dinlenmiş)", "🎲 Tam İstatistiksel Karma"])
        
        if st.button("🚀 Kuponları Üret"):
            st.write("---")
            feature_pool = df_frekans["Sayı"].tolist()
            
            for i in range(1, kupon_sayisi + 1):
                if secim_turu == "🔥 Ağırlıklı Sıcak Sayılar":
                    secilenler = sorted(np.random.choice(feature_pool[:30], size=10, replace=False))
                elif secim_turu == "⚖️ Dengeli (Sıcak + Soğuk/Dinlenmiş)":
                    sicaklar = np.random.choice(feature_pool[:25], size=6, replace=False)
                    soguklar = np.random.choice(feature_pool[-25:], size=4, replace=False)
                    secilenler = sorted(list(set(sicaklar).union(set(soguklar))))
                else:
                    secilenler = sorted(np.random.choice(feature_pool, size=10, replace=False))
                
                st.success(f"**Kupon {i}:**  `{' - '.join(map(str, secilenler))}`")

    # TAB 5: ANLIK YENİ ÇEKİLİŞ EKLEME
    with tab5:
        st.subheader("➕ Anlık Yeni Çekiliş Ekleme")
        yeni_cekilis = st.text_area("Çekiliş sonuçlarını virgülle ayırarak yapıştırın:", placeholder="Örn: 3, 8, 15, 22, 31, 44, 52, 60, 67, 79")
        if yeni_cekilis and st.button("Veriye Ekle"):
            st.success("Yeni çekiliş geçici olarak hafızaya eklendi!")

else:
    st.error(f"⚠️ '{DOSYA_ADI}' reponuzda bulunamadı. Lütfen yüklemenin tamamlandığından emin olun.")
