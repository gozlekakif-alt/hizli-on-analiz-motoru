# V22 — İlk İki Görünüşten Sonra Üçüncü Tam Aile Gelişi, Zaman ve Eşlikçiler

**Kaynak:** `veri.txt` (sha `86458dbe058a322d828b76913868fe29b648a600`). **Doğrulama:** [GitHub Actions başarılı](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38468542060).

72 tam gün: 1 Ağustos—12 Ekim 2026, **15.624 gerçek çekiliş**, 1.296 adet 12 çekilişlik saat. 01:02 özel tek çekiliş korunur; 01:02–07:02 arasında çekiliş olmadığı kabul edilir. Bozuk 23 Ağustos satırları (50924 eksik sayı, 50936 mükerrer 79) tahminle düzeltilmez; 23 Ağustos tam gün sayılmaz. 13 Ekim veri çekildiği sırada eksikti.

## Yöntem

Her saat için yalnız ilk altı çekiliş sonucuna bakılır. 2–10 boyutlarında **tam iki kez** ortaya çıkmış ailelerden her boyutta bir aile, **iki görünüşü arasındaki çekiliş farkı en küçük** olan seçilir. Eşitlikte iki kadronun ortak çevresi, sonra leksikografik kural uygulanır. Aile ve üç eşlikçisi ilk6 sonunda dondurulur. Sonraki6 ve gün sonuna kadar **ilk üçüncü tam aile görünüşü**, çekiliş sırası ve gerçek saat/dakika farkıyla raporlanır. İlk iki çıkışla aynı aralık hedef çekilişi ayrıca sınanır; hedef ilk 6 içinde kalıyorsa önceden gerçekleşmiş olay üstünden sahte tahmin yapılmaz.

## Son 36 günün ayrı test sonuçları

**Son 6 çekilişlik hedef:** her uygun saat/aile için 6 ayrı çekiliş.

| Boyut | Seçilen saat | Son6 tam aile görünüşü | Adil RNG beklenen | Sabit rastgele aile |
|---|---:|---:|---:|---:|
| 2 | 648 | 224 | 233,77 | 212 |
| 3 | 648 | 53 | 53,95 | 41 |
| 4 | 648 | 14 | 11,91 | 11 |
| 5 | 648 | 1 | 2,51 | 3 |
| 6 | 647 | 0 | 0,50 | 0 |
| 7 | 621 | 0 | 0,09 | 0 |
| 8 | 428 | 0 | 0,01 | 0 |
| 9 | 167 | 0 | ~0,001 | 0 |
| 10 | 47 | 0 | ~0,00003 | 0 |

**Gün sonuna kadar en az bir üçüncü aile çıkışı:** 2'li 602/648 (RNG ~600,72); 3'lü 454/648 (~444,06); 4'lü 179/648 (~174,29); 5'li 39/648 (~43,15); 6'lı 9/647 (~8,93); 7–10'lu 0 gözlendi (aşırı düşük olasılıklı). Gün sonuna kadar takip, 01:02 tek çekilişini de içerir ve gece boşluğunu gerçek dakika hesabında 6 saat olarak kaydeder.

**Zamanı birebir hedefleme — İlk iki görünüş aynı aralıkla tekrar edecek mi?** Son 36 günde 2'lide uygun 133 saatten 10 tam hedef isabeti (RNG 8,00); 3'lüde 133 saatten 4 (RNG 1,85); 4'lüde 133 saatten 1 (RNG 0,41). Düşük örneklem ve çoklu boyutlar sebebiyle bunlar üstünlük kanıtı değildir.

## Eşlikçi testi (yalnız 2, 3, 4'lü merkez çekirdek)

Üç eşlikçi sadece ilk iki tam görünüşün çevrelerinden, özellikle ikisinde ortak olanlardan seçildi; eşit boyutlu rastgele 3 eşlikçi de kontrol edildi. Değerlendirme sadece son 6 çekilişte çekirdeğin tam çıkması halinde yapıldı.

| Çekirdek | Seçilen eşlikçilerin tam aile yanında görünüş toplamı | Rastgele eşlikçiler | Adil RNG beklenen |
|---|---:|---:|---:|
| 2'li | 170 | 149 | 155,08 |
| 3'lü | 37 | 33 | 35,10 |
| 4'lü | 6 | 10 | 8,84 |

36 günün gün-kümeli fark güven aralıkları **sıfırı içeriyor**. Dolayısıyla istatistiksel üstünlük henüz yok.

## Somut zaman örnekleri (kural ilk6 bitince donduruldu)

**5 Ekim 2026 saat 19:02–19:57:** 14–27 çekirdeği ilk olarak **19:12** ve **19:17** çekilişlerinde birlikte görüldü; aynı saat **19:37** çekilişinde üçüncü kez birlikte çıktı. Önceden seçilen 32–49–57 eşlikçilerin üçü de üçüncü çekilişte görüldü. Bunun 14–27–32 ve 14–27–32–49 gibi daha büyük iç içe ailelere de yol açabileceği için bu sonuçlar birbirinden bağımsız 3 ayrı keşif değildir.

**28 Eylül 2026 saat 00:02–00:57:** 23–24–28 çekirdeği ilk olarak 00:22, ikinci olarak 00:27 ve üçüncü olarak **00:32** çekilişinde birlikte bulundu. İlk iki çıkışın aralığı 5 dakika idi ve üçüncü de 5 dakika sonra geldi. Saat içinde ilk 6 bitiminde 00:27 sonucu biliniyordu, 00:32 sonucu henüz bilinmiyordu.

## Yorumu

- Bazı aileler gerçekten aynı gün üç kez geliyor; zaman ve çevre ilişkileri saniye/sıra kesinliğinde kaydedildi.
- 2/3/4 çekirdeğin üçüncü tam çıkışları sıklık itibarıyla rastgele beklentiye **yakın**.
- 7–10 ailelerde iki güçlü önceki görünüş, aynı saat veya gün içinde üçüncü tam geliş garantisi **değil**.
- Katalogdaki aileler geçmişten seçilmiş olduğu için seçilim yanlılığı bulunabilir; örüntüler geleceğe dönük kupon başarısı olarak sunulmamalıdır.
- Bu kayıtlar V22 raporunda tek ZIP olarak kaydedilmiştir. V9–V21 motorları, `veri.txt` ve kuponlar değiştirilmemiştir.

## Kaynak kodu ve tam çıktı

- [Analiz motoru](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v22_ucuncu_aile_zaman.py)
- [Streamlit ekranı](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v22_family_app.py) — `v10_app.py` içinde yeni **🌱 V22 Aile Üçüncü Geliş** sekmesi.
- [Veri sızıntısı ve saat doğrulama testleri](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v22_selftest.py)
- [Başarılı GitHub Actions çalışma/indirilebilir ZIP](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38468542060).
- [Oluşturulan ZIP artifact](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38468542060/artifacts/11849178161).
