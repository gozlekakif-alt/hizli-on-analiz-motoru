# V44 ANA BEYİN — Ortak Hafıza, Gerçek Uzman Elemesi, Mühürlü Test

**Tarih:** 14 Ekim 2026. **Önceden dondurulmuş çalışma tasarımı.**

V29–V43 tarihsel bulgularını birden fazla anlatı olmaktan çıkarıp ortak bir kronolojik test protokolünde karşılaştırmak. Bu V38'in 207 açıklayıcı karakter sütununu 207 bağımsız kupon tahmincisi kabul etmez; aynı veri ve aynı hedefi gözlemleyen betimsel raporlar otomatik olarak ayrı uzman değildir.

## 1. Tam şeffaf uzman kataloğu

1. **V39 8 gerçek 20/80 model:** `ISI_SICAK`, `ISI_SOGUK`, `YON_IVME`, `BEKLEME_DONUS`, `AILE_BAGLANTI`, `BANT_BASKI`, `AYNA_KOMSU`, `ORTAK_KARAKTER`.
2. **V41 5 yön uzmanı:** `YON_HIZ`, `YON_DEVAM`, `YON_IVME`, `YON_AILE`, `YON_BANT`. Yalnız hedef öncesi bilinen kalibrasyon ve karakter hareketlerini kullanır.
3. **V42/V43/V18 kaynaklı 5 yeni açık formüllü yöntem:** 72 gerçek çekilişlik 5 hareketli sıcaklık havuzundan büyüklük kotası; aynı beş havuzdan önceden gözlenen online oran kotası; 8 onluk bant kontenjanı; son gerçek 20'den beklentiye göre 5 taşıma + kalan 60'tan 15; önceki gerçek beşli havuz katkı imzalarından sadece geçmiş geçiş frekansıyla kotayı öğrenen yöntem.
4. **19. ön kayıtlı model**: Yukarıdaki 18 uzmanın 20'li liste oylarından her numara için eşit ağırlıklı konsensüs.

**Sınırlamalar:** V43'ün bütün özgün analitik CSV sütunları, V38'in 207 açıklayıcı metrikleri ve V29–V37'nin tüm bağımsız alt dalları 19 ayrı gerçek sayı tahminine çevrilmedi. Beş kota tahmini ile 20 sayı kimliği ayrı raporlanır. V41/RNG'nin bilinen geçmişte üstünlük kanıtı yoktur.

## 2. Ön kayıtlı kronolojik protokol

72 tam günün takvim sırası:
- **Gün 1–18 — KURULUM:** Tarihsel hafıza; bu dönemin sonucu ile aday motorları ilerletebiliriz ama bu dönemin başarısı karar kanıtı değildir.
- **Gün 19–36 — UZMAN_ELEME:** 19 ayrı adayın hepsi hedef gerçek 20 açılmadan önce 20 farklı sayı belirler. Bir uzman ancak aşağıdaki kapıları aynı anda geçerse kabul edilir.
- **Gün 37–72 — KOR_TEST:** Seçilmiş uzman listesi kilitlidir; başarısız görünse de son test verisi ile tekrar uzman seçilmez.
- **Daha sonraki tam günler** son 36 tarihlerin dışındaki `YENI_GUN` olarak etiketlenir; ilk 36 günün sınırı asla ileri kaymaz. Sonradan gelecek 14 gün böyle eklenebilir; gerçek dünya ileri testinde puan alır.

Kapılar (hepsi **yalnız gün 19–36** üzerinde hesaplanır):
1. Ortalama 20 sayılık isabet **adil teorik 5/20'yi en az +0,10** aşmalıdır.
2. Validasyon günlerini iki eşit 9 günlük bloğa ayırınca her ikisinde 5/20'ye karşı pozitif fark olmalıdır.
3. Saatin **7,8,9,10,11,12** çekilişleri alt kümesinde fark pozitif olmalıdır.
4. **19 uzman arasındaki çoklu karşılaştırmayı düzelten** aynı gün içindeki aday bağımlılığını koruyan işaret değiştirmeli `maxT` sınavında tek yanlı düzeltilmiş `p < 0.025` gereklidir.
5. Aynı sayı listelerinin valide edilmiş sonuçta ortalama 18,5/20 örtüşmesi olan uzmanlar ayrı bağımsız oy sayılmaz.

**Hiç uzman geçmezse:** `ANA_BEYIN_KILITLI` aynı tarih/pozisyon için deterministik **RASTGELE20_KONTROL** listesine eşit 20 sayı çıkarır. Durum `KANIT_YOK_RNG_REFERANSI` olarak raporlanır. Kazandıran kupon değildir. Geçmişten gerçek bir tahmin üstünlüğü uydurmaz.

## 3. Geleceği görmeme sözleşmesi

Her gerçek hedef `t`:
1. V39 8, V41 5, V42/V43 5 kimlik uzmanının durumu, beş havuz sınıfı ve kota **yalnız hedefin öncesinden** üretilir.
2. 19 adet 20'li liste ile eski V39 birleşimi ve rastgele kontrol; kapısı geçilmişse ana beyin 20'si dondurulur.
3. `t` gerçek 20'si görüldükten sonra tüm uzmanların 0..20 isabeti ve beş havuzun ±1 kota hataları ölçülür.
4. **Ancak bundan sonra** hedef `t` sayı hafızasına, geçmiş-oluşum geçişlerine ve online kalibrasyona girer.

Kotalar adil seçim koşullu çok değişkenli hipergeometrik null olasılıkla karşılaştırılır. Aynı numara kombinasyonunun tekrarlanmaması gizli RNG kuralı kanıtı değildir.

## 4. Tek ZIP ve açık denetim

- `00_KULLANIM_NOTU.txt`
- `01_HER_CEKILISTE_DONDURULMUS_20_LISTELER.csv`
- `02_HER_CEKILISTE_BES_HAVUZ_KOTA.csv`
- `03_UZMAN_SECIMI_MAXT_VALIDASYON.csv`
- `04_20_LISTE_ISABET_EGITIM_VALI_TEST.csv`
- `05_KOTA_ISABET_VE_RNG_REFERANS.csv`
- `06_ESLENIK_GUN_BLOK_KARSILASTIRMA.json`
- `07_KAPSAM_ELEME_GUVENLIK.json`
- `08_VERI_SONRASI_LISTE.csv` — sonraki kaynak konumu; gerçek güncel gelecek olduğunu iddia etmez.

`v44_ana_beyin_uzman_elemesi.py`, `v44_ana_beyin_selftest.py`, `v44_ana_beyin_app.py`, `.github/workflows/v44-ana-beyin-check.yml`.
Streamlit: V10 → **🧠 V44 Ana Beyin**.

**Gerçek 72-gün otomatik sonucu, geçmiş veri üzerinde hesaplanıp doğrulandıktan sonra aşağıya eklenecektir.** Test sonucuna göre ön kayıtlı eşikler değiştirilmez. Bu araştırma, 16/20 veya 20/20 kazanma garantisi sunmaz.
