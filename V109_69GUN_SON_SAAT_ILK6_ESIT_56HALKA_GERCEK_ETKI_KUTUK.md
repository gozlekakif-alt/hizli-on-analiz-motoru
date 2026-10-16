# V109 — Günün Son Saati: İlk 6 Aynıysa 56 Halkalık Geçmiş Ek Bilgi Sağlıyor mu?

**Çalışma tarihi:** 16 Ekim 2026.  
**Dayanak:** V104'ün yürüttüğü **672 gözlem / 56 sabit 12'li halka** + V108'in **69 gün × 80 sayılık 23:02–23:57** tam yön zinciri, `V108_69_GUN_SON_SAAT_80_SAYI_TAM_HALKA_DNA.csv`. Kaynak V108 bulguları [V108 kütüğünde](V108_72GUN_GUNUN_SON_SAATI_56_HALKA_YON_KUTUK.md) açıklanmıştır. V104/V105/V106/V108 mevcut motorları değiştirilmedi.

## Soru

Günün **23:02–23:57** son 12 çekilişinde, ilk 6 çekilişte aynı sayıda (örneğin tam 3 ya da 4 kez) gelen ve **son havuz üyeliği aynı olan** sayılardan hangisi **H7–H12'de** daha fazla çıkıyor? 56 halkalık sıcaklık/yön zinciri, son sıcaklık ve son 6 halka yönünün **ötesinde** bilgi veriyor mu?

**İlk altı çekilişte 3 kez gelen iki sayının toplam 5+ yapmasının gerçek şartı ikisinin de son 6'da ilaveten en az 2 kez çıkmasıdır.** Toplam görünümün ilk yarıda birikmiş kısmı halka zinciri başarısı sayılmaz.

## Kullanılan yöntem

- Yalnız **69 tam son saat / 5.520 sayı-saat kaydı**. Veri 4 Ağustos–12 Ekim 2026; 16 Ekim canlı saat verisi **yok**.
- **İlk 34 günün** sonraki altılı sonucu kullanılarak koşullu gözlemler öğrenildi; **son 35 gün (2.800 sayı-saat)** sonradan karşılaştırıldı.
- Hedef saat başlamadan 672 geçmiş çekilişte **55–56 tam halkadan** şu bilgiler sabitlendi: son 72 çekilişin sıcaklık havuzu, son altı halka net yönü, 22:02'den 23:02'ye yön değişimi, eski 49–50 halkada soğukta kalma süresi, eski halka hareket sayısı, son havuz değişiminden beri geçen halka sayısı.
- **H1–H6'dan sonra** sayı başına ilk altıda kaç kez geldiği bilinir. Temel karşılaştırma: **aynı ilk altı görünüm sayısı + son havuz + son altı halka yönü**.
- Sonrasında yalnız H7–H12 **0–6 görünüm sayısının** yedi sınıflı hatası ölçüldü; ayrıca toplamda 5+,6+,7+,8+ olaylarının olasılık hataları ayrı izlendi.
- Küçük koşullu gruplarda erken dönem gözlemleri `BINOM6(.25)` ve büyük üst gruplara doğru yumuşatıldı. Ek faktörler aynı önceki hesaplara karşılaştırıldı. Günlük ortalama hata farklarından yaklaşık %95 belirsizlik aralığı çıkarıldı.
- Eski 72 günlük veriler daha önce birçok defa incelendi; **bu yeni, bağımsız kör test değildir**.

## Son 35 gün — ilk 6 görünüm sayısı eşitken, 56 halka geçmişi işe yarıyor mu?

**H7–H12'de sayı başına 0..6 görünüm sayısının çok sınıflı Brier hatası; küçük daha iyi.**

| Hesaplanan bilgi | Hata | Aynı ilk6 + havuz + yön modelinden fark |
|---|---:|---:|
| İlk 6 görünüm sayısı tek başına | **0,7344441** | **−0,0014102** |
| Basit bağımsız altı çekiliş Binom(6,0.25) | **0,7350767** | **−0,0007776** |
| İlk 6 + son havuz + mevcut 6 halka yönü | 0,7358543 | Referans |
| + **22→23 yön değişimi** | 0,7371265 | **+0,0012722** |
| + **56 halkada eski soğuk bekleme** | 0,7377812 | **+0,0019269** |
| + **56 halkada eski hareket sayısı** | 0,7379725 | **+0,0021182** |
| + **Son havuz değişikliğinin yaşı** | 0,7377712 | **+0,0019169** |

**Karar:** Son 35 günlük veri üzerinde 56 halkalık ekstra dört geçmiş niteliği H7–H12 görünüm sayısını **daha iyi açıklamadı**; küçük miktarda daha kötü hesap üretti. Bu, "56 halka boşa yürütüldü" demek değildir: yürüyüş kaydı gerçek ve eski yön filminin tanımlayıcı kullanımı sürüyor; mevcut basit koşullu özelliklerle ek öngörü gösterilemedi demektir.

## Aynı ilk altı görünümüne sahip sayıların gerçek son-altı hareketi

**Son 35 gün; her bir satır sayı-saat örnek adedi**

| H1–H6 aynı adet | Hedef öncesi yön | n | H7–H12 ortalama görünüm | H1–H12 toplam 6+ oranı |
|---|---|---:|---:|---:|
| 3 | Isınan | 122 | **1,533** | %17,21 |
| 3 | Soğuyan | 162 | 1,414 | %14,81 |
| 4 | Isınan | 31 | 1,355 | %41,94 |
| 4 | Soğuyan | 43 | **1,674** | **%60,47** |

**Yalnız '6+ saati tamamladı' bilgisinin yön etkisini göstermediği açık:** İlk altıda 4 görünüm zaten birikmişken, son altıda yalnız 2 ilave görünüm yeter. Örnek adetleri özellikle 4 kez görünümlü sayılarda düşüktür.

**Son 35 gündeki ısınan−soğuyan son altı ilave görünüm farkı:** Gün başına **aynı H1–H6 adedi ve aynı son havuzu paylaşan karşılıklı gruplarla eşleştirilince** **+0,14973 görünüm**; yaklaşık %95 gün-eşlemeli belirsizlik aralığı **[−0,00289, +0,30235]**. Aralık sıfırı içeriyor.

## 22→23 yön değişimi; ilk altı ve son havuz düzeltmesi

Son 35 gün:

| Önceki→Son yön | n | İlk 6 ortalama | Son 6 ortalama | İlk 6 + son havuza göre son-altı farkı | 6+ saati tamamlama |
|---|---:|---:|---:|---:|---:|
| Soğuyan→Soğuyan | 808 | 1,510 | 1,496 | −0,0011 | %6,68 |
| Isınan→Soğuyan | 149 | 1,725 | 1,450 | −0,0375 | %6,71 |
| Soğuyan→Isınan | 154 | 1,448 | 1,513 | +0,0145 | %2,60 |
| Isınan→Isınan | 776 | 1,450 | 1,513 | +0,0096 | %4,77 |

Örneğin **Isınan→Soğuyan grubunun %6,71 6+ oranı**, son altı görünüm artışından değil, ilk altıda ortalama **1,725** görünüm birikmesinden etkilenmiş. Bu nedenle önceki V108’de görülen büyük 6+ farkını doğrudan halka yön tahmini olarak kullanamayız.

## Çıkan sonuç ve sonraki araştırma

V109'un cevabı: **ilk altı çekiliş eşitlenince, incelenen 56 halkalık sıcaklık ve yön geçmişi H7–H12 için doğrulanmış ek üstünlük sağlamadı.** 22→23 yön değişiminin geçmiş 6+ farklarının önemli bir kısmı ilk yarıdaki farklı geliş sayısından kaynaklanıyor. 56 halkayı koruyacağız; fakat hedefte gelecek sayı seçmeye geçmeden önce yeni saatler üzerinde **önceden kayıtlı, sayılar gerçek gelmeden kilitlenmiş** zincir sonuçlarını izlemek gerekir.

## 10 çıktı dosyası

1. `00_V109_ILK6_KONTROLLU_SON_SAAT_BULGULARI.txt`
2. `01_69_GUN_80_SAYI_ILK6_SON6_HALKA_ZINCIRI.csv`
3. `02_SON35_7_YONTEM_KARSILASTIRMA.csv`
4. `03_GUNLUK_ESLESMELI_HATA_ARALIKLARI.csv`
5. `04_ILK6_2_3_4_ESIT_YON_GRUPLARI.csv`
6. `05_22_23_GECISI_ILK6_HAVUZ_DUZELTILMIS.csv`
7. `06_UZUN_SOGUKTA_BEKLEME_ILK6_AYNI.csv`
8. `07_SON35_ILK6_3_4_OLANLAR_ZINCIR.csv`
9. `08_GUNLUK_ESLESMELI_ISINAN_SOGUYAN_SON6.csv`
10. `09_YONTEM_ZAMAN_KAYNAK_DENETIM.json`

**Dosya özelliği:** ZIP içinde 5.520 sayı-saatin 55/56 harfli tam halka ısı zinciri, halka yön zinciri ve gerçekleşen H1–H12 sonuçlarıyla ilk/son altı ayrımı vardır.
