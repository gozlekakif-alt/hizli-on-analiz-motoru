# V118 — V100B'ye Dönüş: 12, 24, 36 … 672 İç İçe Havuz + 1/0 ve Aileler

**Tarih: 16 Ekim 2026**

**Çalışan kod:** [v118_v100b_56_icice_halqa_01_aile_oncu_test.py](v118_v100b_56_icice_halqa_01_aile_oncu_test.py)

**Doğrulanmış GitHub Actions çalışması (başarılı):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38965118178

**İndirilebilir dokuz dosyalı sonuç arşivi:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38965118178/artifacts/12074607114

## V100B'nin gerçek yöntemi, V115/V116'dan farkı

**Halka 1:** Son 12 çekiliş. **Halka 2:** Son 24 çekiliş. … **Halka 56:** Son 672 çekiliş.

Her biri **80 sayının ilgili uzunluk boyunca toplam 1 adet görünme sayısına göre** hesaplanmış göreli 16 soğuk +16 serin +16 nötr +16 ılık +16 sıcak havuzudur. Tüm 56 pencerenin **bitiş noktası aynıdır (hedef çekiliş öncesi)**. Yeni tek çekilişin sonucuyla birlikte her pencere tek çekiliş kayar, kendi en eski bir çekilişini çıkarır. Bu, V115'in her biri **ayrı 12 çekiliş** tutan 56 gruplu sistemi **değildir**.

Aile sınıflaması dahil **bütün öngörü işaretleri hedef sonucu gelmeden önce** hesaplandı; hedeften sonra oluşan sıcaklık değişimleri geriye doğru yansıtılmadı. `1` çıktı, `0` çıkmadı bilgisi hedef gerçekleştikten sonra etiketlendi.

## Veri ve karşılaştırma

Kaynak `veri.txt`, **15.790** gerçek sonuç, son veri **13 Ekim 2026 #62014**.

69 eksiksiz **23:02–23:57** son saat bulundu. Bu saat başlamadan H22'nin iki çekilişinde **tam 7 ortak sayı** çıkmışsa, son ikili kesişimin belirlediği aile önceden sabitlendi. **68/69 saatte** bir yedili aile bulundu. **68×12=816 hedef çekiliş** aile ve kontrol kuponlarını karşılaştırır. 69×12=**828 hedef çekilişin tamamı**, 80 sayının **12/72/672 sınıf geçişleri** açısından ayrıntılı yazılmıştır.

Saat başlamadan **69×56×80=309.120 sayı-pencere frekans + havuz kaydı**, **69×80=5.520 adet 672-bit 1/0 geçmiş** kaydı ve H23'in 828 çekilişindeki **66.240 sayı/çekiliş önce-sonra 12/72/672 hareket kaydı** kaydedildi.

| Her hedef çekilişte 7 sayı seçen sabit yöntem | Bir çekilişte ortalama isabet | Hedefte 5/7+ |
|---|---:|---:|
| H22'de iki ayrı çekilişte birlikte çıkan 7'li aile | **1,74755** | **5** |
| Rastgele 7 | **1,72794** | **1** |
| 672 havuz kompozisyonu eşlenmiş 7 | **1,74877** | **5** |
| En çok çıkan son72'den 7 | **1,71201** | Çıktı dosyasında |
| En çok çıkan son672'den 7 | **1,68505** | Çıktı dosyasında |
| Teorik adil 7 sayı × 20/80 | **1,75000** | 5+/7 yaklaşık %0,94/kupon |

Seçilen yedili aileye karşı **gün-cluster bootstrap %95 güven aralığı**, çekiliş başına fark olarak:

- Aile − rastgele: +0,01961, %95 [−0,09069, +0,13235].
- Aile − 672 havuz eşli kontrol: **−0,00123**, %95 [−0,12132, +0,11397].
- Aile − sıcak72: +0,03554, %95 [−0,05637, +0,12868].
- Aile − sıcak672: +0,06250, %95 [−0,03431, +0,16299].

**Dört farkın tamamının belirsizlik aralığı sıfırı kapsar. Öngörü üstünlüğü yok.**

## İç içe halkalar içinde ailelerin hareketine yönelik sabit, hedeften önce görülebilen işaretler

**A. Kısa pencerede daha çok aynı havuzda birleşme:** 12–72'lik 6 havuzda yedi aile üyesinin aynı havuz çift sayısı, 612–672'lik 6 uzun pencereden yüksekse:

| Durum | Aile saat | Sonraki hedef çekiliş | Ortalama aile doğru sayısı |
|---|---:|---:|---:|
| Evet | 53 | 636 | 1,731 |
| Hayır | 15 | 180 | 1,806 |

**B. Uzun pencerelerde en fazla 3 üye aynı havuzdayken kısa pencerelerde en az 4 üyenin toplanması:**

| Durum | Aile saat | Hedef çekiliş | Ortalama aile doğru sayısı |
|---|---:|---:|---:|
| Evet | 36 | 432 | 1,725 |
| Hayır | 32 | 384 | 1,773 |

**C. Yedili ailenin en az 4 üyesinin son72'de, önceki72'den daha çok `1` üretmesi:**

| Durum | Aile saat | Hedef çekiliş | Ortalama aile doğru sayısı |
|---|---:|---:|---:|
| Evet | 40 | 480 | 1,746 |
| Hayır | 28 | 336 | 1,750 |

**D. A (yakınlaşma) ve C (1/0 yükselişi) aynı anda:**

| Durum | Aile saat | Hedef çekiliş | Ortalama aile doğru sayısı |
|---|---:|---:|---:|
| Evet | 35 | 420 | 1,740 |
| Hayır | 33 | 396 | 1,755 |

Bu sayılar, daha önce yıllarca araştırılmış **aynı tarihsel veri içindeki** betimsel farklardır. İşaretlerin eşiklerini karşılaştırıp en başarılı gözükene göre rastlantıyı seçmek ciddi hatadır. H22 üzerinden yedili aile seçilmesi, kısa pencerede yüksek son72 `1` toplamını mekanik olarak teşvik eder; bağımsız bulgu değildir. Bu bir RNG çözümü veya garantili 5/7, 6/7 yöntemi olarak sunulmamalıdır.

## Tam arşivdeki raporlar

1. `00_V118_KISA_TURKCE_GERCEK_SONUC.txt`
2. `01_H23_ONCESI_56_ICICE_HALKA_80_SAYI_TAM_KAYIT.csv` — 309.120 satır; her sayı her iç içe halkada görünme sayısı, sınıfı ve önceki dar pencereye göre yönü.
3. `02_H23_ONCESI_80_SAYI_672_BIT_1_0_DIZISI.csv` — saat başlangıcından önce 80 sayının her birine ait 672 bit; ayrıca kronolojik 56×12 bölümü.
4. `03_7LI_AILE_56_PENCEREDE_FREKANS_HAVUZ_BIRLESME.csv` — her ailenin gerçek 56 halkadaki sayıları, havuzları, çift beraberliği, ilgili 12 yeni bit.
5. `04_GUN_GUN_AILE_HEDEF_ONCESI_ISARET_5_KUPON.csv`
6. `05_HEDEF_12_CEKILIS_BIREBIR_5_KUPON_KARSILASTIRMA.csv`
7. `06_HER_HEDEF_80_SAYI_12_72_672_ONCE_SONRA_1_0.csv`
8. `07_12_72_672_HAVUZ_CARPRAZ_GERCEK_HEDEF_ORANLARI.csv`
9. `08_AILE_DONEM_YON_01_RITIM_KOR_KIYAS.csv`
10. `09_ETKI_GUVEN_ARALIKLARI_VE_METOD.json`

**Not:** Arşivde aslında **10 dosya** vardır (00–09). Hedef günün sonuçları geçmiş halka tanımına girmedi. Aynı günün H23 sonraki çekilişlerinde **her yeni çekiliş geldikten sonra bir sonraki hedef için bütün 56 pencere bir çekiliş kaydırılarak** yeniden hesaplandı. H22'de önceden sabit yedili ailenin üyeleri 12 hedef boyunca aynıdır.

**Karar:** V100B, V118 çalışmasıyla 1/0 ve yedili aile hareket kayıtları açısından genişletilmiştir. Bu üç kısa/uzun kümeleşme ve sıklık artışı işareti gerçek isabet üstünlüğü göstermedi. Yeni modelleri paralel çoğaltmak yerine zaman damgalı **yeni ileriye dönük hedef çekilişlerinde** önce işareti sabitlemek ve sonra sonuçla sınamak gerekir.
