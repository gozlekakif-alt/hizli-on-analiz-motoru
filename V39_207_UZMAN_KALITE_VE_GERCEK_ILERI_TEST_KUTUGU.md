# V39 — 207 Uzman Kalite Denetimi ve Geliştirme Kararı
**14 Ekim 2026 | Denetim kaynağı:** Kullanıcının 15.990 gerçek çekiliş içeren V38 ZIP dosyası.

## Gerçek ölçüm kapsamı

- 207 uzman adı × 15.990 gözlenen çekiliş = **3.309.930 sayısal alan**. Bunlar 3,3 milyon bağımsız tahmin değildir.
- 72 tam gün = 15.624 çekiliş; 2 eksik gün = 366 çekiliş. Eksik sıra "çıkmadı" olarak yorumlanamaz.
- **18 sütun sabit** (6'sı tamamen sıfır); **21 tam aynı akışın tekrar sütunu**; 186 benzersiz sayısal akışın **176'sı değişken**. Bunlar birbirinden bağımsız 176 sinyal değildir.
- **47 sütun eski V38'de yalnız tarama göstergesidir**; bireysel aile kimliği ve epizot geçmişinin tamamını taşımamaktadır.

### Sürekli sıfır üreten uzmanlar

`WAIT.13`, `PAIR.09`, `QUARTET.15`, `DIALOGUE.04`, `DIALOGUE.06`, `DIALOGUE.11`.

### Sabit olan bütün uzmanlar

`LIFE.01`, `HEAT.14`, `WAIT.13`, `WAIT.16`, `PAIR.05`, `PAIR.06`, `PAIR.09`, `TRIPLE.08`, `QUARTET.01`, `QUARTET.12`, `QUARTET.13`, `QUARTET.15`, `LARGE.05`, `DIALOGUE.04`, `DIALOGUE.06`, `DIALOGUE.11`, `TWIN.01`, `TWIN.02`.

### Gerçek veride tamamen eşit uzman akışları

1. `LIFE.01` = `WAIT.16` = `TWIN.01` = `TWIN.02`
2. `HEAT.11` = `HEAT.13`
3. `WAIT.13` = `PAIR.09` = `QUARTET.15` = `DIALOGUE.04` = `DIALOGUE.06` = `DIALOGUE.11`
4. `WAIT.15` = `RETURN.01`
5. `RETURN.09` = `DIALOGUE.01` = `DIALOGUE.09`
6. `BURST.08` = `BURST.13`
7. `STAGE.01` = `STAGE.07`
8. `STAGE.03` = `LARGE.04` = `TIME.06`
9. `TRIPLE.04` = `TRIPLE.05`
10. `LARGE.01` = `LARGE.07`
11. `MIRROR.05` = `MIRROR.06`
12. `TIME.05` = `TIME.08`
13. `TWIN.06` = `TWIN.12`

**Kural:** Bunları birleştirirken farklı isim sayısı kadar ağırlık verilmeyecek; önce hesaplama kök nedeni incelenecek. Eşit sütunlar farklı değişkenleri tasarlıyor olabilir ama kod henüz doğru ölçmüyor olabilir.

## Uygulanan V39 onarımı

- V9–V38 veri, motor ve `veri.txt` kayıtlarını değiştirmeden **V39 ayrı sekme** kuruldu.
- Tek bir V38 sonucu sonradan hesaplanmış 207 sütununun geleceği gören tahminiymiş gibi kullanılmasını engeller.
- Sayı düzeyinde, önceki gözlenmiş çekilişleri kullanan **8 önceden tanımlı strateji**, bir geçmiş-performans diyaloğu ve **bağımsız 20/80 RNG** karşılaştırılır.
- Dönem kesimi tam günlerle yapılır; 72 tam günün ilk 36'sı eğitim, son 36'sı ileri yürütülen test.
- Her hedef t için 20 sayı **önce** seçilir; gerçek t sayılarıyla isabet ölçülür; motor ancak **sonra** geçmişini t ile günceller. Bu sıralama sentetik geleceği değiştirme testinde doğrulandı.
- 0/20–20/20 histogramları, 10+, 12+, 14+, 16+ ve günlük blok yeniden örnekleme ayrı raporlanır.
- Önceki V38 ZIP dosyası Streamlit sekmesine yüklendiğinde gerçek 207 uzman için sabitlik ve tam tekrarlama ayrı CSV olarak oluşturulur. V39 raporu V38 ZIP olmadan da çalışır.

## Gerçek V39 sonuçları: 72 tam gün, 15.624 gerçek çekiliş

GitHub Actions **başarılı**: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38614969350

Dondurulmuş 20'li listeler: **156.240** (10 yöntem × 15.624 gerçek çekiliş).

**Son 36 tam gün, 7.812 çekiliş:**

| Deneme | Ortalama 20'li ortak sayısı | 10+ | 12+ | 14+ | 16+ | En fazla |
|---|---:|---:|---:|---:|---:|---:|
| Uzmanlarla diyaloğa dayalı ağırlıklı 20'li | **4,99373** | 45 | 0 | 0 | 0 | 11 |
| Eş olasılıklı bağımsız 20/80 | **5,01331** | 34 | 0 | 0 | 0 | 11 |

Gün blok ortalama fark **−0,01959 sayı/çekiliş**, yaklaşık %95 aralık **[−0,05952; +0,02471]**. Bu verilerle üstünlük görülmedi; 16/20 yok.

Rapor: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38615430465/artifacts/11920195628

## Sıradaki mühendislik etapları

Aşama 1: Bu 47 tarama uzmanının bağımsız sayı/aile epizotları, giriş/çıkış zamanları ve olay ID'leriyle gerçek çalışır dal olup olmadığını **tek tek yeniden tanımla ve test et**. İsim verip sayısal kopya oluşturarak tamamlandı yazma.

Aşama 2: Aile 2/3/4 tam ve parçalı yaşam olaylarını geçmişten t öncesine kadar güncelleyip sayı düzeyinde yeni sinyaller üret. Aynı t sonuçları bu sinyallerin girdisi olamaz.

Aşama 3: Rastgele kontrolün kendisiyle de çoğul deneme yanlılığını denetle (birden fazla kolonda en iyi görüneni seçme yanlılığı). Sabit modelle hiç dokunulmamış yeni tarihler üzerinde sınama yap.

Aşama 4: Başarı iddiası için birbirinden bağımsız yeni gerçek çekilişlerde tutarlı isabet üstünlüğü göster. **Adil RNG'nin gizli algoritmasının öğrenildiği veya 16/20 düzenli bulunabileceği bugüne kadar kanıtlanmadı.**

## Veri sonrasındaki ilk 20'li listeler (V39 güncellemesi)

GitHub'da doğrulanmış son sürüm, kaynak içindeki **son işlenen gerçek çekilişten sonraki 1. sıranın** her 10 yöntem için önceden seçilmiş 20 sayısını da ZIP'in **06_VERI_SONRASI_ILK_20_SAYI_LISTESI.csv** dosyasına ekler. Streamlit V39 sekmesi bu listeleri doğrudan gösterir. Bu özellik kaynak `veri.txt` eski olduğunda **gerçek şu anki geleceğe ait olamaz**; ekranda kaynağın son gün/sırası ve hesaplanan hedef gün/sıra açıkça yazılır. Sonuç görmeden yeni hedef için seçim yapılır; güncelliğini kullanıcı kontrol etmelidir. Böylece ZIP toplam **7 rapor dosyası** taşır.

Son doğrulanmış workflow: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38615430465
