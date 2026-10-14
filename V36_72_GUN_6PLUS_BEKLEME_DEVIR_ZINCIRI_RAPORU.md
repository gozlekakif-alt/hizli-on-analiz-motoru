# V36 — 72 Gün / 80 Sayı: 6+ karakterinin iki kez sürmesi ve bekleyen sayıların devir zinciri

**14 Ekim 2026.** Kaynak: GitHub veri.txt, **72 tam gün / 15.624 çekiliş**. Zaman sıralı 36 gün eğitim, 36 gün test; test başlangıcı **7 Eylül 2026**. Tamamı geçmiş kayıtlar kullanılarak **14.184 geçerli kaynak penceresi** tarandı.

## İncelenen sorunun kesin tanımı

- **A — H6:** Bir sayı, son 11 gerçek çekilişin en az 6'sında çıktı.
- **A — H6 iki kez:** Aynı sayı iki ardışık *kayan 11'li pencerede* H6 oldu; üç ve daha fazla sürmeler de ayrıca raporlanır.
- **B — bekleyen:** Başka bir sayı ardışık 6, 7, 8, 9, 10 ya da 11+ gerçek çekilişte görünmedi.
- A'nın H6 durumunun **sürmesi veya düşmesi** ve B'nin **1, 2, 3, 6, 9 çekiliş içinde ilk kez yeniden görünmesi** beraber kayıt altına alındı.
- Ek olarak, **A'nın H6'dan düştüğü çekilişte B'nin geri gelmesi** sayılar düzeyinde tarandı. Bütün A–B ikilileri, olayın gerçekleşmediği durumlar dahil CSV'de var.

**Önemli ayrım:** Ardışık kayan 11'li pencereler 10 çekilişi paylaşır. Aynı sayının iki kez H6 görünmesi kendiliğinden bir tahmin sinyali değildir. H6'nın bir sonraki pencerede devam etmesi, pencereden çıkan en eski 1/0 hane hesaba katılarak adil RNG ile karşılaştırılmalıdır.

## Test dönemi bulguları (son 36 gün)

| Ölçüm | Gerçek | Adil RNG temel beklenti |
|---|---:|---:|
| H6 iki ve daha çok pencere süren sayıların ertesi çekilişte görünmesi | **%25,3846** (3350/13197) | %25 |
| H6 iki ve daha çok pencere süren sayıların H6 olarak devamı | **%70,6448** (9323/13197) | **%70,6126** (11-bit imzaya göre hesaplanan mekanik beklenti) |
| En az 6 çekiliş bekleyen B, A2 mevcutken ertesi çekilişte döndü | **%25,0254** (22179/88626) | %25 |
| Tam 9 çekiliş bekleyen B, A2 mevcutken ertesi çekilişte döndü | **%24,7697** (2312/9334) | %25 |
| A H6'dan düşerken B geri geldi (A2 ile B6+ ikilisi) | **%7,3731** (14121/191520) | **%7,3658** (A'nın o andaki 11-bit imzası ve iadesiz 20/80 çekilişiyle koşullu hesap) |

**B'nin geri geliş zamanı — A en az iki pencere H6 iken:**

| En fazla kaç çekiliş sonra? | B6+ gerçek / beklenen | B9 gerçek / beklenen |
|---|---|---|
| 1 | %25,025 / %25,000 | %24,770 / %25,000 |
| 2 | %43,792 / %43,750 | %43,229 / %43,750 |
| 3 | %57,835 / %57,812 | %57,585 / %57,812 |
| 6 | %82,153 / %82,202 | %81,701 / %82,202 |
| 9 | %92,372 / %92,492 | %92,436 / %92,492 |

Bu testte **belirgin bir kupon üstünlüğü tespit edilmedi**. Gün içinde geçişler gerçekten yaşanıyor; ancak oranlar, adil 20/80 modelinin ürettiği doğal geçişlerle oldukça uyumlu. Tek sayı–pencere ve farklı sayı çifti kayıtları birbirinden bağımsız değildir. Bu tablolardaki büyük olay sayıları tek başına anlamlılık kanıtı sayılamaz.

## İki farklı 6+ sayı aynı anda bulunuyorsa (ayrı kontrol)

Tek bir sayının üst üste iki kayan pencerede H6 olması ile **aynı anda iki farklı sayının H6 olması** ayrı olaylar olarak test edildi.

| Son 36 günlük durum | B6+ ertesi çekilişte çıktı | B9 ertesi çekilişte çıktı |
|---|---:|---:|
| Aynı anda en az iki farklı H6 sayı var | **%25,0153** (20508/81982) | **%24,9158** (2144/8605) |
| Aynı anda tek bir H6 sayı var | **%25,0734** (3760/14996) | **%25,5266** (412/1614) |
| Aynı anda en az iki farklı sayı H6'da iki veya daha fazla pencere kalmış | **%25,1119** (15032/59860) | **%24,6739** (1551/6286) |
| Aynı anda yalnız bir sayı H6'da iki veya daha fazla pencere kalmış | **%24,8453** (7147/28766) | **%24,9672** (761/3048) |
| RNG referansı | **%25** | **%25** |

Bu ayrım da sınama döneminde belirgin bir ileriye dönük isabet üstünlüğü göstermedi. Yüzdeler farkı doğrudan kazanma avantajı olarak yorumlanmamalı; aynı gün ve pencereler arasında bağlılık bulunur.

## Bir sonraki çekilişte H6'dan düşme ne zaman mümkün?

Şimdiki 11-bit pencereye yeni çekilişin sonucu eklendiğinde en eski bit çıkar. A'nın mevcut sayısı 6 ise ve en eski bit **1** ise, en eski 1 düşünce 5 kalır: A sonraki 20'de **çıkmazsa** H6'dan düşer. En eski bit 0 ise ya da o bit çıkarılınca 6 veya daha fazla 1 kalıyorsa A **bir sonraki çekiliş ne olursa olsun H6'da kalır**. Bu, pencerelerin örtüşmesinden gelen matematiksel kuraldır; sonraki 20 sayıyı tahmin etmek değildir.

## Üretilen program ve raporlar

- Kod: [v36_karakter_devir_zinciri.py](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v36_karakter_devir_zinciri.py)
- [GitHub Actions çalışması](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38562435329)
- [Tek ZIP — tüm A/B sayı bazlı devir kayıtları, günlük özet ve 1/2/3/6/9 geri dönüş tabloları](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38562435329/artifacts/11892861968)
- ZIP 8 dosya; tam sayı–sayı geçişleri **05_TUM_SAYI_SAYI_DEVIRLER.csv** içerisinde.

**Araştırmanın sınırı:** Bu V36 tanımı “iki ardışık *kayan 11 çekilişlik pencere* H6” anlamındadır. Eğer kastedilen ardışık iki ayrı 11 çekilişlik blokta 6+ çıkmasıysa bu başka ve daha nadir bir olaydır; ayrı analiz gerektirir. Aynı şekilde sayıya özel zamansal devir ilişkilerinin geleceğe taşınması, yeni günler üzerinde önceden sabitlenmiş kurallarla sınanmalıdır.
