# V100 — 672 çekilişlik kaydırmalı 56 halka / sıcaklık havuzları araştırması

**Tarih:** 16 Ekim 2026  
**Çalışma:** [Başarılı GitHub Actions V100 analizi](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38897927768)  
**Araştırma kodu:** [v100_672_56_halka_havuz_yon_kor_test.py](v100_672_56_halka_havuz_yon_kor_test.py)  
**Tam CSV/ZIP sonuçları:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38897927768/artifacts/12045160357

## Hangi halka?

**V100A** için bir hedef çekiliş `t` belirlendiğinde geçmişteki `[t−672,t)` aralığı **56 ardışık ve örtüşmeyen 12 çekilişlik halkaya** ayrılır. Halkalar en eskiden yeniye sıralanır ve hedef birer çekiliş kaydırılır. Her halkanın sonunda 80 sayının son 12 çekilişlik ve son 72 çekilişlik görünme sayıları ayrı hesaplanır. Sıralama frekans, eşitlikte sayı kimliğiyle yapılır; her an **16 soğuk, 16 serin, 16 nötr, 16 ılık, 16 sıcak** havuzu oluşur.

**Teknik not:** İlk halkanın sonunda 72 çekilişlik sınıflandırma yapabilmek için asıl 672 pencerenin öncesinde 60 çekiliş yalnız başlangıç hesabı için kullanıldı. Hedefe giden 56 halkanın her biri yine tam 12 çekiliş, takip edilen ana geçmiş tam 672 çekiliştir. Bu nedenle **732. sıfır bazlı hedef indeksinden** başlar, 72 tam günün **14.892 hedef çekilişi** kapsanır. Günler arası gerçek olmayan 5 dakika varsayılmaz; halka birimi gözlenen çekiliş sayısıdır.

## Sıcak/soğuk havuz hareketinin bulguları

| Gösterge | Gerçek veri |
|---|---:|
| Analiz edilen hedef | **14.892** |
| Bir 672'lik pencerede ortalama beş havuzu tamamlayan sayı | **77,77 / 80** |
| Bir pencerede 80 sayının 80'inin beş havuzu tamamladığı hedef sayısı | **1.378 / 14.892** |
| Aynı 672 pencerede sıcak ve soğuk havuzun ikisine de uğramış ortalama sayı | **77,82 / 80** |
| Son 6 halkada yükselme gösteren ortalama sayı | **31,85** |
| Son 6 halkada düşüş gösteren ortalama sayı | **31,97** |
| Ortalama sayının 55 halka geçişinde havuz değiştirme sayısı | **27,95** |

**Son hedef (#61845, 12 Ekim 2026):** 80 sayının 78'i 5 havuzu ziyaret etti ve 78'i hem soğuk hem sıcak oldu. **27 numara** sıcak havuza, **44 numara** soğuk havuza hiç uğramadı. Son 6 halka yönü: 30 yükselen, 33 düşen, kalan sabit.

Bu havuz statüleri her halkanın *göreli frekans sırası* ile tanımlanır; bunlar sonraki çekilişte mutlak çıkma olasılığı değildir.

## Doğrulama ve geçmişe dönük son test

Önceden tanımlı **14 alternatif yöntem + HOT72 karşılaştırması**, ilk 36 gün araştırma, sonraki 18 gün seçim, son 18 gün tarihsel kontrolle aynı hedeflerde test edildi. Her yöntemde **80 sayıdan 20 sayı seçilir**, yeni çekilişte gerçek 20 sayıyla eşleşenler sayılır.

| Yöntem | Orta 18 gün / 20 | Son 18 gün / 20 |
|---|---:|---:|
| HOT72 sıcak 72 referansı | 5,022529 | **5,023554** |
| ACCEL_12 kısa süreli halka ivmesi | **5,036610** | **4,959293** |
| Rastgele20 tek karşılaştırma dizisi | 5,022785 | 4,969790 |

Doğrulamada HOT72'ye karşı **+0,014081** görünen ACCEL_12, son dönemde **−0,064260** farka düştü. 18 günlük blokların ortalama farkına dayalı yaklaşık %95 aralık **[−0,126283, −0,002237]**. Bu yön seçildiği şekliyle **başarılı değil**. HOT72 son dönemde kendi yönteminden daha kötü/iyi olduğunu kanıtlayamayacak küçük bir 5,0236 ortalaması verir. Fair 20/80 için teorik 20 sayılık ortalama isabet **5,0**.

**Önemli:** Tüm 72 gün V9–V99 sürümlerinde de tekrar tekrar incelendi. Son 18 gün kronolojik kontrol diye ayrılmış olsa da gerçekten yeni ve dokunulmamış çekiliş sayılmaz; bir ileri tarih avantajı çıkarılamaz. Farklı alt gruplar sonradan seçilirse çoklu deneme yanlılığı vardır.

## 9 dosyalı tam ZIP

1. `00_V100_KESIN_RAPOR.txt`
2. `01_15_YONTEM_36_18_18_KOR_TEST.csv`
3. `02_HER_HEDEF_672_56_HALKA_20LI_KONTROL.csv`
4. `03_HEDEF_BASINA_80_HAVUZ_TUR_DOLULUK.csv`
5. `04_SICAKLIK_YON_DAVRANIS_HEDEF_OLASILIGI.csv`
6. `05_80_SAYI_HANGI_HAVUZDAN_HEDEFE_GELDI.csv`
7. `06_SON_HEDEF_80_SAYI_56_HALKA_FILMI.csv`
8. `07_80_SAYI_TUM_HAVUZ_TUR_ZAMANI.csv`
9. `08_METOT_DENETIM.json`

## Alternatif halka yorumu

Kullanıcının çizdiği **672→660→648→636→...→12** iç içe pencereler anlamına da gelebilir. Bu yüzden V100B ayrıca hazırlanmıştır: Her 56 pencere **aynı hedefte biter** ve pencere uzunluğu her halkada 12 azalır. V100A eski tarihten bugüne 12'şer gözlemdeki fiziksel hareketi; V100B aynı hedefe bağlanan **birbirinin içine geçmiş 672/660/.../12 uzunluklu frekans sıralamalarını** gösterir. İkisini karıştırmayınız.
