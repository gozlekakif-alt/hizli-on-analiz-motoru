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
- **Güncel ekleme koruması (son düzeltme):** İlk 72 tam gün sınırları geriye dönük sabitlenmiştir. Kullanıcı 'eksik günleri de işle' seçse bile ilk 72 tam günün **öncesi veya arasındaki eksik günler** eleme penceresine girmez; yalnız bu dönemin *sonrasına* gelen eksik ve yeni kayıtlar `YENI_GUN` olur. Böylece eski eksik saatleri sonradan eklemek eleme tarihlerini oynatmaz.

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

---

## 5. Doğrulanan gerçek test — 14 Ekim 2026

GitHub Actions: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38635465472

9 dosyalı indirilebilir ZIP: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38635465472/artifacts/11926949242

**Sonuç: iş akışı başarılı; 19 adaydan hiçbirinin gerçek öngörü üstünlüğü kanıtlanamadı.**

- 72 tam gün, **15.624** gerçek çekiliş, 19 uzman araştırma adayı.
- Gün 1–18 model hafızası/kurulum.
- Gün 19–36 = **3.906** çekilişli ve **18 günlü** kilitli uzman sınavı.
- Gün 37–72 = **7.812** çekilişli ve **36 günlü** tamamen ayrık değerlendirme.
- Kabul edilen uzman **0**. Ana beyin bundan dolayı açıkça `KANIT_YOK_RNG_REFERANSI` kaydıyla eşlenik rastgele 20 üretir.
- Geriye dönük olarak son 36 gündeki en yüksek isabetli uzmanı seçip üstünlük iddiası yapılmadı.

| Son 36 gün, 7.812 hedef | Ortalama 20 sayı isabeti | Tek çekilişte maksimum | 16/20+ |
|---|---:|---:|---:|
| **V44 ana beyin (kanıt yok → RNG referansı)** | **4,98297** | 12 | 0 |
| V39 eski birleşim | **4,99373** | 11 | 0 |
| 19 uzman ön kayıtlı konsensüs (araştırma) | **4,98438** | 12 | 0 |
| Eşlenik RNG kontrolü | **4,98297** | 12 | 0 |

Günlük korelasyonu koruyan 36 gün bootstrap eşlenik farkları:
- Konsensüs − rastgele20 **+0,001408/20**, %95 **[−0,038914, +0,041731]**. Rastgele farkı içerir; kazanım kanıtı değildir.
- Ana beyin − V39 **−0,010753/20**, %95 **[−0,052739, +0,031362]**.
- Ana beyin − RNG = **0** (tanım gereği birebir aynı 20, çünkü hiçbir aday kabul edilmedi).

**Saatin 7.–12. hedef çekilişleri (3.888 gerçek çekiliş):**
- Ön-kayıtlı 19 uzman konsensüsü **5,03189/20**.
- V39 eski birleşim **5,02058/20**.
- Ana beyin/RNG referansı **4,98560/20**.
- Bu alt grup geçmişte bazen 5 üzeri görünse bile validasyon kapıları geçilmediğinden, **bu rakamdan daha sonra uzman terfisi yapılamaz.** Yeni 14 gerçek günde sınama gerekir.

**Beş hareketli havuz kotası (test 7.812 çekiliş):**

| Kota motoru | Bir havuzda ±1 | Tüm beş havuz aynı anda ±1 | Adil RNG koşullu beklenti | Ortalama toplam mutlak hata |
|---|---:|---:|---:|---:|
| Basit 20/80 (%25 üye payı) | 67,40143% | 18,88121% | 18,73779% | 6,00333 |
| Geçmişe göre online kalibre | 67,30415% | 18,79160% | 18,69262% | 6,00205 |
| Önceki oluşumdan geçiş hafızası | 66,55402% | 17,84434% | 17,76476% | 6,09780 |

Bu bulgular, eski %60–70 havuz başına ±1 başarısının gözlenmesine rağmen **20 sayı kimliğinde güvenilir gelişme sağlanamadığını** doğrular.

**Elemede en iyi görünen aday bile yeterli değildi:** `V39_AILE_BAGLANTI` validasyon ortalaması **5,042499/20**; ikinci dokuz gün farkı negatif (−0,008193), çoklu test düzeltilmiş p ≈ **0,662384**. Bu nedenle açıkça reddedildi.

**Kod ve gerçek veri test durumu:** V44 tüm birim testlerden geçti; gelecekteki `t` sonucunu değiştirmek `t) öncesindeki listeleri değiştirmiyor. 9 dosyalı ZIP, GitHub Actions `success`. Çalışma sonucuna bakarak ön-kayıtlı eleme eşiği değiştirilmedi.

## 6. Bundan sonra yalnızca yeni günlerde yapılacak iş

- Yeni gerçek çekilişleri eklemeden önce 19 uzmanın eleme kuralı ve aday katalogu donduruldu.
- Tarihsel son 36 gün üzerinde yeni bir model seçilmemeli; araştırma protokolü için yeni sürüm açılırsa bağımsız yeni 14 gün gereklidir.
- Yeni 14 tam gün boyunca özellikle 7.–12. gerçek çekilişin **t** sonuçları görülmeden 20'li listeleri dondurup ekle.
- Bütün motorların ve V44 kilitli ana beynin **isabetleri, 0..20 dağılımı, 5+/6+/7+/8+/10+/12+/16+ olayları**, beşli kota ±1 hatası, gün-bazlı bootstrap ve RNG temel referansı birlikte verilmeli.
- Eski 72 günlük kaynak sonrası tarih/saat **güncel canlı gelecek olduğunun kanıtı değil**; uygulama bunu uyarır.
