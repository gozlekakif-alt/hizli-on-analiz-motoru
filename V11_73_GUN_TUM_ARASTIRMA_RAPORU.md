# V11 — 73 Günlük Aile ve 12×20 Sayı Araştırması

13 Ekim 2026, GitHub ana veri.txt üzerinden. Bu belge V11 programının ilk kapsamlı bulgu raporudur. Kod: v11_arastirma.py; uygulama: V10 içindeki 🧠 V11 Araştırma sekmesi; test: v11_selftest.py.

## 1. Girdi ve zaman ayırımı

- GitHub veri.txt: 1 Ağustos–13 Ekim 2026, toplam 74 takvim gününde **15.968** geçerli çekiliş.
- Son gün 13 Ekim henüz tam olmadığı için karşılaştırmalı test **1 Ağustos–12 Ekim**, **73 gün**, **15.839** kayıt üzerinde yapıldı.
- 23 Ağustos'ta iki çekiliş eksik; son 12 gerçek çekilişin tamamı kayıtlı olmayan pencereye tahmin konulmadı.
- Saatteki 7., 8., 9., 10., 11. ve 12. çekilişleri hedefleyen **7.434 ayrı çekiliş** test edildi.
- İlk 36 gün ile izleyen 37 gün ayrı ölçüldü; ikinci gün grubunun sonuçları yöntemlerin skorlarını yeniden eğitmek için kullanılmadı.
- 6'lı: 198, 7'li: 151, 8'li: 279, 9'lu: 9, 10'lu: 194 — toplam **831** mevcut kayıtlı aile.
- ÖNEMLİ: Bu 831 aile geçmiş verilerdeki sonuçlara bakılarak seçildiği için, ikinci 37 günlük bölüm dahi AİLE SEÇİMİ yönünden gerçek bağımsız kör test değildir.

## 2. Hedef öncesindeki 12 çekiliş: her çekilişin 20 sayısı

V11 araştırması her hedefe bakmadan önceki 12 çekilişte **12×20=240 sayı kaydını** kullanır; her hedefin kendi 20 sayısı SADECE SONUÇ değerlendirmesine girer.

Ölçülen başlıklar:
1. Her 1–80 sayının geçmiş 12 çekilişte görülme sayısı.
2. İlk 6 ile son 6 çekiliş sıcaklık/değişim; yükselen, dengeli, düşen.
3. 0 kez (henüz gelmemiş), 1–2 (soğuk), 3–4 (ılık), 5–6 (sıcak), 7+ (çok sıcak).
4. Bir çekilişten diğerine taşınan sayılar ile yeni gelen sayı sayısı.
5. Önceki 12 çekilişte benzersiz kaç sayı görüldü, hangi sayılar hiç gelmedi?
6. Son 6 çekilişte ikili sayı birliktelikleri.
7. Ardışık/komşu sayılar, 1–20, 21–40, 41–60, 61–80 bantları.
8. Her ailenin önceki 12 çekilişte kaç sayısının birlikte çıktığı: 12 adımlık 0/k...k/k izi.
9. Ailenin geçmiş günlerde aynı saat diliminde tam görünüş sayısı.
10. Tam görünüşe hazırlanma / tekrarlama / dalgalanma / sessiz kalma sınıfları.

Uygulamada V11_80_SAYI_AKTIVASYON.csv, V11_20_SAYI_SAAT.csv ve V11_7_12_SIRA_RAPORU.csv raporları ayrıdır.

## 3. Tam görünen ailenin geliş yolu: kategoriler

Aşağıdakiler deneysel ve birbiriyle öncelik sırasına göre ayrı etiketlenmiştir. Hesap, yalnız hedef öncesindeki 12 çekilişi görür.

- **Tam tekrar**: Geçmiş 12 çekilişte aile bir kez daha tam görünmüştür.
- **Sessiz**: Geçmiş 12 çekilişte aynı anda görünen aile sayısı hiçbir çekilişte floor(k/2)'yi aşmamıştır.
- **Tamamlayarak**: Son 3 çekilişte k−1 düzeyine ulaşmış ve son 6 ortalaması ilk 6'ya göre yükselmiştir.
- **Yükselerek**: Son 6/ilk 6 ortalama farkı en az 0,85 ve son 6 içinde en az k−2 düzeyi vardır.
- **Dalgalanarak**: Görünüş eğimi en az 4 kez tersine dönmüş ve son 6'da k−2'ye ulaşmıştır.
- **Diğer/karma**: Yukarıdakilerin dışında kalan tam görünüşler.

Bunlar ancak olay GERÇEKLEŞTİKTEN sonra geliş yolunu açıklar; önceden tam isabet tahmin etme gücünü kanıtlamaz.

### Son 37 gün — tam görünüş sayıları

| Boyut | Sessiz | Tamamlayarak | Yükselerek | Dalgalanarak | Tam tekrar | Diğer |
|---|---:|---:|---:|---:|---:|---:|
| 6 | 177 | 1 | 6 | 40 | 40 | 30 |
| 7 | 46 | 0 | 0 | 2 | 7 | 43 |
| 8 | 114 | 0 | 1 | 1 | 42 | 28 |
| 9 | 1 | 0 | 0 | 0 | 3 | 2 |
| 10 | 118 | 0 | 0 | 0 | 0 | 23 |

Özellikle 10'lu ailelerde 141 tam görünüşün 118'i bu "sessiz" sınıfında. Kısmi artış arayan motorların bu aileleri geriden açıklamada yetersiz kalabileceği görülüyor, ancak çok sayıda sessiz aday olduğundan bunları ÖNCEDEN seçebilmek farklı ve zor bir problemdir.

## 4. Tahmin yöntemleri

**Her hedeften ÖNCE belirlenen sayılar** şu altı deneysel yolla hesaplanır:
1. **Sıcak-12**: Geçmiş 12 çekilişte en sık görünen k sayı.
2. **Son6 ivme**: Son 6 eksi ilk 6 frekans farkı en yüksek k sayı.
3. **Soğuk-12**: Geçmiş 12 çekilişte en az görünen k sayı.
4. **Birliktelik**: Son altı çekilişteki ortak sayı çiftlerine dayalı seçim.
5. **Son çekiliş**: En son çıkan 20 sayı içinden 12 çekiliş sıklığı yüksek k sayı.
6. **Aile öncü sinyali**: Geçmişte seçilmiş sabit ailelerden kısmi hareket, saat, dalga, birliktelik ve tekrar sinyallerine göre bir aile.

Ayrıca aynı hedef çekiliş için rastgele sayı seçimi kontrol olarak çalışır.

### Son 37 gün: kupon başına ortalama tutan sayı

| k | Rastgele matematik beklenti | Sıcak-12 | Son6 ivme | Soğuk-12 | Birliktelik | Son çekiliş | Rastgele gerçekleşen |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6 | 1,500 | 1,484 | 1,498 | 1,479 | 1,500 | 1,504 | 1,500 |
| 7 | 1,750 | 1,730 | 1,741 | 1,733 | 1,747 | 1,750 | 1,741 |
| 8 | 2,000 | 1,988 | 1,985 | 1,986 | 2,005 | 1,991 | 1,986 |
| 9 | 2,250 | 2,241 | 2,240 | 2,233 | 2,250 | 2,244 | 2,257 |
| 10 | 2,500 | 2,496 | 2,485 | 2,495 | 2,512 | 2,503 | 2,500 |

Her sayı-temelli yöntem, son 37 günde her boyutta 3.774 hedef çekiliş için kupon oluşturdu. Sayı hareketinden seçilen yöntemler rastgele sayıların matematik beklentisine çok yakın çıktı. Bu verilerde kanıtlanmış tahmin üstünlüğü yok.

Tam isabet sonuçları: Sayı temelli yöntemlerin hiçbirinde 7/7, 8/8, 9/9, 10/10 görülmedi. 6/6, "Son çekiliş" yönteminde 1 kez ve rastgele kontrol yönteminde de 1 kez görüldü.

### Mevcut eski katalog ailelerinin yüksek görünen isabetleri — ÖNEMLİ YANLILIK

| Boyut | Önceden sinyal verilen hedef | Tam isabet |
|---|---:|---:|
| 6 | 3.774 | 7 |
| 7 | 3.728 | 3 |
| 8 | 3.656 | 7 |
| 9 | 189 | 3 |
| 10 | 3.140 | 0 |

**Bunlar güvenilir tahmin başarı oranları değildir.** Çünkü katalog 1.131 aileden, geçmiş günlerde hangi ailelerin tam çıktıĞINA BAKILARAK seçilmiştir. Böyle bir listeyi geçmiş dönemler için test etmek, hedef sayılar algoritmanın girişinde olmasa bile dolaylı olarak hedef sonuçlarını katalog seçimi üzerinden içeri sızdırır. Özellikle 9'lu ailelerin 3/189 görünüşü tahminin olağanüstü başarılı olduğu iddiası olarak kullanılamaz.

Gelecek günler için kullanacağımız aile listesini bugün KİLİTLEYİP yalnız sonraki günlerde gelen yeni hedefleri saymamız gerekir.

## 5. 1–80 sayı aktivasyonunun gerçek ölçümü

İzleyen 37 günlük bölümde, hedef öncesindeki 12 çekilişin TÜM 20 sayılarını kullanarak 1–80 sayısını ayrı ayrı incelediğimizde:

| Önceki 12 çekilişteki durum | Sayı-hedef gözlemi | Sonraki çekilişte görülme |
|---|---:|---:|
| Hiç görünmeyen (0), dengeli | 9.520 | %25,315 |
| 1–2 kez görünen, dengeli | 76.686 | %24,947 |
| 3–4 kez görünen, dengeli | 90.240 | %24,909 |
| 5–6 kez görünen, artışta | 7.277 | %24,090 |
| 7+ kez görünen, dengeli | 3.049 | %26,763 |

Bunlar aynı yöntemin yalnız bazı sıcaklık/ivme kesitleridir; bütün 80 sayı ve tüm kesitler V11_80_SAYI_AKTIVASYON.csv içinde yer alır. Adil bir 20/80 çekilişte tek sayının çıkış ihtimali %25'tir. Tekil kesitlerdeki küçük farklar çok sayıda alt grubun denenmesinden kaynaklanan rastlantısal değişkenlik olabilir. **Özellikle soğuk/sıcak sayı durumlarının bir sonraki çekiliş için kanıtlanmış üstünlüğü yoktur.**

## 6. Denetim ve çıktılar

Program:
- Her boyutun tam görünüş yolunu ve her yöntem için 0/k...k/k dağılımını gösterir.
- 7–12. çekilişi ayrı ayrı test eder; kayıtlı olmayan 12'lik pencerelerden sonuç çıkarmaz.
- Bütün hedefleri, tarih/saat/çekiliş numarasıyla V11_7434_HEDEF_DEFTERI.csv dosyasına hazırlar.
- 80 sayının frekans/ivme sınıfına göre sonraki hedefte çıkma sıklığını ölçer.
- Altı ayrı istatistik dosyası ve TXT özeti verir; canlı önizleme yalnız hâlâ gelecekte olan uygun hedefe yazılır.
- Ana veri.txt, V9 app.py, V10 aile listesi, canlı JSON ve önceki biletleri DEĞİŞTİRMEZ.

V11 araştırmasındaki tüm yöntemler henüz deneysel. İstatistiksel olarak anlamlı bir üstünlük kanıtlanmadan 6/6 veya 10/10 olacağı iddia edilemez.

