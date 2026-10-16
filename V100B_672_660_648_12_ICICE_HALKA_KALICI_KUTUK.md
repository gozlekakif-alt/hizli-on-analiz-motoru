# V100B — Fotoğraftaki gibi iç içe 672 → 660 → 648 → ... → 12 halka

**Tarih:** 16 Ekim 2026  
**Durum:** GitHub Actions [başarılı koşu 38898640577](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38898640577).  
**Kod:** [v100b_hedef_merkezli_672_660_648_12_halka.py](v100b_hedef_merkezli_672_660_648_12_halka.py).  
**Tam 10 dosyalı ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38898640577/artifacts/12045540469

## Kullanıcının çizdiği halka yapısının birebir uygulaması

Hedef çekiliş **T**, henüz gözlenmeden önce `T-672:T` (672 geçmiş çekiliş), `T-660:T` (660 geçmiş çekiliş), `T-648:T`... `T-12:T` (12 geçmiş çekiliş) ele alınır. **56 iç içe halka** vardır, tüm halkaların sağ ucu, gözlenmemiş hedefin hemen öncesi olan **T**'dir. Bir sonraki hedef `T+1` olduğunda tüm pencereler bir çekiliş kayar. Bu tanım, V100A'daki örtüşmeyen, eski tarihten yeniye doğru giden 12'li çekiliş bloklarından farklıdır.

Her hedef ve her halkada, geçmiş uzunluğu kadar çekilişte 80 sayının ayrı ayrı frekansı hesaplanıp, (frekans, sayı kimliği) artan düzende sıralanır: **16 soğuk, 16 serin, 16 nötr, 16 ılık, 16 sıcak** havuz. Ardışık iki halkanın havuz sınıfı değişimi yön ve büyüklük olarak kaydedilir. Hedef henüz bilinmeden son halka için hedefe çıkış istatistiği oluşturulur. Havuzlar **göreli** etiketlerdir ve 12/672 gibi farklı uzunlukların ham frekansları doğrudan karşılaştırılmaz; üyelik sıraları karşılaştırılır.

## 72 günlük gerçek veri kapsamı

- **15.624** geçerli gerçek çekiliş (72 eksiksiz gün).
- İlk 672 çekiliş ısınma, sonra **14.952 hedef çekiliş**.
- Hedef başına **56** iç içe halka, 80 sayı, 55 ardışık yön geçişi.
- İlk 36 gün model araştırması, sonraki 18 gün doğrulama/model seçimi, son 18 gün kilitli tarihsel kontrol.

### Havuz yolculuğunun ölçülen boyutu

| İstatistik | Gerçek veri |
|---|---:|
| Bir hedefin 56 iç içe halkasında 5 havuzun tamamını ziyaret etmiş ortalama sayı | **24,25 / 80** |
| Herhangi bir hedefte tüm 80 sayının 5 havuzu tamamladığı durum | **0** |
| Hem sıcak hem soğuk havuzu en az bir kez ziyaret etmiş ortalama sayı | **26,19 / 80** |
| Dış 672 halkasından iç 12 halkasına yükselen ortalama sayı | **31,01** |
| Dış 672 halkasından iç 12 halkasına düşen ortalama sayı | **30,83** |
| Son 6 iç içe halkada yükselen/düşen ortalama sayı | **28,85 / 28,39** |

**En son geçmiş hedefi 12 Ekim 2026 #61845:** 56 iç içe halkada **23** sayı bütün havuzları, **30** sayı soğuk ile sıcağın ikisini de ziyaret etti. **32** sayı dış 672 sınıfından iç 12 sınıfına yükseldi, **35** sayı düştü. Son 6 halka **26 yükselen, 27 düşen**. Beş havuzu bitiren 23 sayı:

`1, 2, 3, 5, 7, 10, 11, 18, 19, 24, 25, 36, 40, 41, 45, 46, 53, 55, 58, 64, 69, 74, 75`.

Bütün havuzları 23 sayının tamamlaması **sonraki çekilişte bu sayıların çıkacağı iddiası değildir**.

### Halka küçüldükçe yön hareketleri nasıl değişti?

**Son 18 gün** örneği, her geçişte toplam **3.906 hedef × 80 sayı = 312.480 sayı-değişim durumu**. Seçilmiş halkalarda havuz üyeliği yönleri:

| Dış → iç halka | Düşen | Sabit | Yükselen |
|---|---:|---:|---:|
| 672→660 | 24.080 | 264.288 | 24.112 |
| 360→348 | 31.426 | 249.448 | 31.606 |
| 144→132 | 47.676 | 215.867 | 48.937 |
| 72→60 | 62.623 | 183.991 | 65.866 |
| 24→12 | 90.157 | 126.508 | 95.815 |

**Asıl yapısal bulgu:** Uzun geçmişi 12 çekiliş azaltmak sıralamayı nispeten az oynatıyor; hedefe yakın kısa halkalarda aynı 12 çekilişlik küçültme çok daha fazla sayının göreli sıcaklık sınıfını değiştiriyor. Bu, pencere hassasiyetini ölçüyor; geleceği önceden görme iddiası değil.

## Hedef 20 sayısını bilme açısından kontrol

Önceden tanımlı **14 aday + HOT72** ile 20 sayılık seçimler yapıldı. Hedefin kendi sonucu seçim yapılana kadar kesinlikle kullanılmadı. Referans 20 sayıda beklenen isabet 5,0.

| Model | Doğrulama 18 gün | Son 18 gün |
|---|---:|---:|
| HOT72 | 5,022529 | **5,023554** |
| NEST_LONG_SHORT_RATIO (672 ile 12 karşılaştırması) | **5,036866** | **4,977983** |
| Rastgele20 kontrol | bağlama özel tek seri | **5,020993** |

Doğrulama ilkesiyle seçilen **NEST_LONG_SHORT_RATIO** son 18 günde HOT72'ye **−0,045571** isabet/çekiliş daha kötü oldu. 18 günlük bloklar üzerinden yaklaşık %95 güven aralığı farkı **[−0,091236, +0,000095]**, üstünlük gösterilemedi.

Son 18 günde HOT72'yi hiçbir diğer 14 modelin ortalama isabeti geçmedi (bu, modellerin geçmişe sonradan incelenmiş karşılaştırmasıdır, bir ispat değildir).

**Karar:** 672→660→648→...→12 hedefe bağlı iç içe havuz dönüşleri başarıyla ölçülmüştür. Bu geçmişteki hareketlerin isabet üstünlüğü henüz doğrulanmadı. Kupon motoruna kazanç/öngörü yöntemi olarak eklenmemeli. Önce halka yapısı üzerinden daha anlamlı betimleyici sorular seçilmeli; yeni çekilişlerde zaman damgalı ileriye dönük değerlendirme yapılmalı.

**Tekrar kullanım uyarısı:** V9–V100 birçok çalışma aynı veriyi gördü; ayrılmış son 18 gün gerçek anlamda dokunulmamış test değildir.

## ZIP: 10 tam rapor

`00_NESTED_672_660_12_RAPOR.txt`, `01_15_MODEL_36_18_18_KOR_TEST.csv`, `02_14952_HEDEF_KAYDIRMA_KUPON_KONTROL.csv`, `03_HER_HEDEF_56_HALKA_DOLULUK.csv`, `04_55_ASAMA_YON_HEDEF_GELME_OLASILIGI.csv`, `05_SON72_SON12_YON_TUM_DAVRANISLAR.csv`, `06_80_SAYI_HANGI_IC_HALKA_HAVUZDAN_GELDI.csv`, `07_SON_HEDEF_80_SAYI_672_660_12_FILMI.csv`, `08_80_SAYI_INCE_HALKA_TAM_TUR.csv`, `09_METOT_KOR_DENETIM.json`.
