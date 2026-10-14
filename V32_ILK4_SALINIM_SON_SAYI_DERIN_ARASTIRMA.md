# V32 — 80 sayının tamamlanma hızı, ilk 4 adım ve son tek sayı

**Kaynak:** Kullanıcının V32 ZIP çıktısı; 72 tam ve 2 eksik gün, toplam 15.990 çekiliş. Çıkan 20 havuzu: 931 açılmış döngü, 858 tamamlanan ve 73 açık kalan döngü. Açık döngülerin bitiş süresini tamamlanmış varsayma.

## Uçlar ve ilk dört çekilişin ayrı kimliği

- Tamamlanan döngülerin en kısası 10 çekiliş (4 örnek), en uzunu 36 çekiliş (1 örnek); bunlar matematiksel alt/üst sınır değildir.
- 10 çekilişlik 4 döngünün ilk dört yeni sayı dizisi: `20,18,14,8` (60), `20,15,12,7` (54), `20,12,10,8` (50), `20,17,13,8` (58).
- 36 çekilişlik tek örnek: 2 Eylül 2026, 111.–146. günlük sıra. İlk dört: `20,15,6,9` (50). 12. adımda 79/80 tamamlandı; son eksik sayı **7** ancak 36. adımda geldi. İlk dörtte 50 sayıya ulaşan başka bir döngü ise 10. adımda tamamlandı.
- Tüm ilk dört adımı mevcut döngülerde en yüksek 62/80. Bu düzeye ulaşan örnekler 18 ve 22. adımda bitti: ilk dörtte en yüksek sayı sayısı en kısa bitiş demek değildir.
- İlk dört yeni sayı ortalaması: 20; 15,019; 11,326; 8,397. Bağımsız 20/80 RNG beklentisi: 20; 15; 11,25; 8,4375.

## Tamamlanma karakterleri

| Tamamlanma aralığı | Tamamlanan döngü | İlk dörtte ort. farklı sayı | 75/80'e ort. erişim adımı | 79/80'e ort. erişim adımı | 79'dan sonra ort. ilave adım |
|---|---:|---:|---:|---:|---:|
| 10 | 4 | 55,50 | 8,25 | 10,00 | 0,00 |
| 11–15 | 273 | 54,86 | 9,37 | 12,43 | 1,33 |
| 16–19 | 335 | 54,87 | 10,05 | 14,52 | 2,83 |
| 20–23 | 170 | 54,44 | 10,23 | 16,13 | 5,26 |
| 24–29 | 63 | 54,40 | 10,40 | 16,22 | 9,62 |
| 30–36 | 13 | 53,77 | 10,54 | 17,15 | 15,38 |

**Gözlem:** İlk dört adım hızları benzer. Uzun döngülerde asıl fark, 79/80'e ulaştıktan sonra son eksik sayının beklemesinde.

79/80 durumundan sonraki 3.049 gerçek çekilişlik denemede 753 kapanış gözlendi: %24,697. Rastgele 20/80 çekilişinde tek bekleyen sayının bir çekilişte çıkma olasılığı %25'tir.

## Sıra arayışı

Aynı gün ve aynı kesintisiz veri parçasında 782 ardışık tamamlanmış döngü karşılaştırıldı. Ardışık uzunluk korelasyonu -0,00184; hızlı (10–15) / orta (16–19) / yavaş (20+) durumlarının geçiş tablosunda belirgin düzenli sıra görülmedi. Bu bir sonraki döngünün uzunluğu için kanıtlanmış tahmin işareti değildir.

İlk dörtte görülen farklı sayı adedine göre RNG'nin **tamamlanma olasılığı** değişir, fakat bu RNG'nin normal matematiğidir. Örneğin ilk dörtte 50 sayı görüldüğünde 10. adımda tamamlama olasılığı ~%0,155; 60 sayı görüldüğünde ~%1,56'dır. Bu ihtimaller sayılarının kimliğine yönelik ekstra öngörü göstermez.

## İzlenecek sorular

1. İlk dörtteki hız yerine 4→8→12 adımlarındaki **beklenenden fazla/az yeni sayı** artıkları tutarlı mı?
2. 79/80 noktasında bekleyen tek sayının kimliği, sıcaklık, bant veya saat koşuluna bağlı olarak sonraki çekilişte %25'ten anlamlı şekilde ayrılıyor mu?
3. Aynı sorular, gelecek verileri hiç görmeyen zaman sıralı testte rastgele 20/80 modelini aşabiliyor mu?

**Uyarı:** Uçlardaki örneklem sayıları çok az. Açık kalan döngüler sansürlüdür. Bu çalışma RNG algoritmasını çözmüş veya kupon isabeti arttırmış değildir. Zaman 01:02'den 07:02'ye gerçek boşluk içerir; sahte çekiliş eklenmemelidir.
