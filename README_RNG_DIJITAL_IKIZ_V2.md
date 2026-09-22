# Hızlı On RNG Dijital İkiz V2

## Amaç
14 günlük 25.08.2026–07.09.2026 verisini başlangıç hafızası olarak kullanır. 15. gün ilk çekilişten itibaren her el canlı güncellenir. Bir sonraki el için üretim **sonuç gelmeden önce SHA-256 ile mühürlenir**; gerçek sonuç geldikten sonra fark analizi yapılır ve yalnız sonraki el için akort uygulanır.

## V2'de izlenen yapı
- HOT20 / MID40 / COLD20: aynı gün gerçekleşmiş sonuçlarla her el yeniden sıralanır.
- 20/21 ve 60/61 sınır çevresi.
- H1/H2/H3 taşıma.
- Son 3/6/12/17/24/36/72 el frekansı ve kısa ivme.
- Aynı-gün yaş/uyku ve 2–7 el dönüş.
- H1 ile çift yaşamı.
- Komşu ve aynı-son-hane hareketi.
- Ardışık çift ve bir-atlamalı çift yoğunluğu.
- 1–10 ... 71–80 bant yoğunluğu.
- Simüle edilen 20'nin gerçek 20 anatomisine çekiliş-çekiliş farkı.

## Öğrenme / akort
Kupon isabetini kör biçimde ödüllendirmek yerine gerçek sonucun **anatomisini** öğrenir. HOT/MID/COLD, H1, sınır, dönüş, ardışık, bant vb. baseline değerleri düşük hızlı EMA (alpha=0.025) ile güncellenir. Böylece tek çekiliş motoru sert biçimde bozmaz.

## 15. gün akışı
1. Seed yükle + baseline kur.
2. Hedef çekiliş saatini gir.
3. `RNG-SIM 20’liyi üret ve mühürle`.
4. Gerçek 20 sayı geldiğinde `Gerçeği işle`.
5. APP farkı kaydeder ve baseline'ı yalnız sonraki el için akort eder.
6. 217 el sonunda `217-El Otopsi` ekranından gerçek/sim farklarını indir.

## Çalıştırma
```bash
pip install streamlit pandas numpy
streamlit run hizli_on_rng_dijital_ikiz_v2.py
```

APP dosyası ile `HIZLI_ON_25_08_2026_07_09_2026_TAM_14_GUN(1).txt` aynı klasörde olursa seed düğmesi doğrudan çalışır.

## Sınır
Bu yazılım gerçek çekiliş sisteminin gizli RNG algoritmasını veya seed'ini geri çıkardığını iddia etmez. 14 günlük gözlenebilir çıktı yapısını modelleyen ve ileriye dönük mühürlü testle doğrulanan bir dijital ikiz/simülasyon araştırma aracıdır.
