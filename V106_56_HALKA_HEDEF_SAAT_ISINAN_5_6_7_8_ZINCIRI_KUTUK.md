# V106 — Hedef Saatte 5, 6, 7, 8 Kez Görünecek Isınan Sayıların 56 Halkalık İzleri

**Tarih:** 16 Ekim 2026  
**Program başarıyla çalıştı:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38916094425  
**Kod:** [v106_hedef_saat_isinan_sayilar_5_6_7_8_56_halka.py](v106_hedef_saat_isinan_sayilar_5_6_7_8_56_halka.py)  
**11 dosyalı ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38916094425/artifacts/12052437900

## Buradaki 5–8 ne?

**Bir sayının hedef saatin 12 çekilişi boyunca toplam 5, 6, 7 ya da 8 defa görünmesi.** Kupon isabeti veya bir ailenin 5–8 farklı sayı çıkarması değildir. Kullanıcı başka anlamı kastediyorsa yöntem o hedefe göre değiştirilmelidir.

## Mekanizma: V100C/V104/V105 aynı kaldı

Kaynak veri 72 tam gün + 13 Ekim'deki ek kayıtlar: 15.790 çekiliş. **1.246** adet doğrulanmış, her biri 12 çekilişlik hedef saat. Yaklaşık **99.680 sayı×saat** kaydı.

Hedef başlamadan önceki son **672 çekiliş** yürüyen FIFO'da 12'lik sabit halka kimliğiyle tutuluyor; **55–56 dolu halka** arasındaki sıralı sıcaklık yolu çıkarılıyor. Her sayı için hem son 6 tam halkadaki sıcaklık farkı hem de daha eski yaklaşık 49–50 halkada ne kadar soğuk/sıcak kaldığı, ne kadar havuz değiştirdiği, kaç defa yükselip düştüğü kaydediliyor. `net6>0` ise **ISINIYOR**.

**Gerçek hedef H1–H12 sonuçları**, ancak yön haritası oluşturulduktan sonra 0–12 geliş sayısını ve her çekilişin 1/0 durumunu etiketlemek için kullanılıyor. Böylece **hangi 56 halka yolculuğundan sonra bir sayının 5/6/7/8 kere geldiği** numara numara bulunabiliyor.

## Sayılar: Isınanların sonraki hedef saatte en az 5–8 kere görünmesi

| Önceden ISINIYOR olan sayı×hedef saat | Sayı×saat kaydı | En az 5 | En az 6 | En az 7 | En az 8 |
|---|---:|---:|---:|---:|---:|
| İlk 36 gün | 18.677 | %15,527 | %4,963 | %1,290 | %0,273 |
| Son 36 gün | 20.748 | %15,693 | %5,364 | %1,364 | %0,222 |

20/80 kuralıyla belirli bir sayının 12 çekilişte teorik 5+,6+,7+,8+ oranları sırasıyla **%15,764, %5,440, %1,425, %0,278**. Bu tarihsel tabloda sırf ısınma yönünde olmak, yüksek tekrar olasılığını artırdığına dair istikrarlı bir kanıt göstermiyor.

**Isınan bir sayının 56 halka geçmişi** dört önceden belirlenmiş duruma ayrıldı:
- `SOGUKTAN_UYANAN`: son 6'dan önceki 6 halkada en az 3 kez soğukta olması ve şimdi net6 ısınması.
- `INI_CIKISLI_ISINAN`: son 6 halkada en az 2 yükseliş ve en az 1 düşüşle sonuçta ısınma.
- `ILIK_SICAKTA_YUKSELEN`: şu anda ılık veya sıcak, son 6 net artı.
- `ALT_HAVUZDA_YUKSELEN`: diğer net artı, alt sıcaklık düzeyinde yükselme.

**Örnek:** `SOGUKTAN_UYANAN` 5+ oranı ilk 36 günde **%15,785** (n=6.126), son 36 günde **%15,991** (n=6.929); 6+ **%5,207→%5,845**, 7+ **%1,420→%1,429**, 8+ **%0,327→%0,260**. Farklar küçük veya yön değiştirmiştir; ileri dönem için kesin bir avantaj denemez.

## İlk 6 çekiliş: 5–8 hedefinde en kullanışlı ara sinyal

Son 36 günde, hedef saat başlamadan **ISINIYOR** olarak işaretli sayıların H1–H6 sonuçları geldikten sonra 12 çekilişi tamamlaması:

| H1–H6 görünüm | n sayı×saat | H1–H12 en az 5 | en az 6 | en az 7 | en az 8 |
|---|---:|---:|---:|---:|---:|
| 2 | 6.158 | **%16,68** | %3,67 | %0,47 | %0,02 |
| 3 | 2.715 | **%47,00** | %16,80 | %3,17 | %0,33 |
| 4 | 686 | **%81,05** | **%45,92** | %17,20 | %3,06 |
| 5 | 96 | **%100,0** | **%80,21** | **%47,92** | %13,54 |

Bu güçlü artış **ilk 6 çekilişte sayının zaten kaç defa çıktığını bilmekten** kaynaklanır. Hangi sayının 5–8 kez görüneceğini saat başlamadan bildiğimiz anlamına gelmez.

**Kontrol:** H1–H6 sonucu sabit tutulduğunda, yalnız 56 halkalık geçmişe dayanan `SOGUKTAN_UYANAN`/eski soğukta kalış/önceki 49-50 halka hareket düzeyi eklenmesi, son 36 günde sürekli daha düşük ikili tahmin hatası getirmedi. Örneğin 5+ için sabit `ilk6 + %25` hesabının Brier hatası **0,09264235**, `ilk6 + geçmiş ısınma tipi` **0,09267791** oldu. `ilk6 + eski soğukluk süresi` **0,09263660** gibi çok küçük bir farkla daha iyi görünse de bu ileride kullanılabilir bir etki olarak gösterilmiş değildir.

## Son tamamlanmış hedef saat ve 5 tekrar sayıları

**13 Ekim 2026 19:02–19:57; #62003–#62014.** Bu saatin başlamasından önce 33 sayının son 6 tam halkası net ısınıyordu.

**Tam 5 kez görünen ısınan sayılar: 11, 58, 72, 73, 79**.

| Sayı | 56 halkanın sonundaki havuz | Son 6 halkadaki net yükselme | Hedef saatteki geliş elleri | Eski ~50 halkada soğuk süresi |
|---|---|---:|---|---:|
| 11 | SICAK | +3 | H1,H3,H5,H10,H11 | 5 |
| 58 | ILIK | +3 | H1,H3,H7,H9,H12 | 3 |
| 72 | SICAK | +2 | H5,H7,H8,H10,H11 | 0 |
| 73 | SICAK | +2 | H1,H3,H6,H9,H12 | 6 |
| 79 | SICAK | +1 | H2,H3,H5,H6,H11 | 19 |

Eski soğuk süresi **0'dan 19'a** değişti: bu beş sayı için tek ve aynı 56 halka davranışı söz konusu değil. Saatte tam 6, 7, 8 veya 9+ kere görünen **önceden ısınan** sayı olmadı.

## Pratik yöntem

1. **H1 başlamadan** 56 halka tam yolunu kaydet; son altı halka net pozitif sayıları ve eski 50 halka hareketini raporla. Bu gruptaki sayılar ön izleme listesidir, garanti değildir.
2. **H1–H6 gelince** hangi sayının kaç kez göründüğünü say; 3–4 tekrara ulaşan ısınanları ayrı gözle.
3. **H7–H12 için** toplamda 5, 6, 7, 8'e ulaşmak üzere kaç görünüm daha gerektiğini takip et. Önceki 36 günün oranlarıyla karşılaştır.
4. **Saat bitince** 0–12 tam sonuç ve bütün 56 halka hareket zincirini numara bazında kaydet. Eski tüm halkalarda kalan/hareket eden ailelerin tekrar örüntülerini dönemden döneme karşılaştır.
5. Bu gözlemleri yeni çekilişler veri dosyasına eklendiğinde yeniden üret; güçlü varsayımları geçmişten seçip sonuçları aynı geçmişte puanlamak ile gerçek ön kayıtlı gelecek performansını ayır.

## ZIP: 11 dosya

`00_ISINAN_SAYI_5_6_7_8_HEDEF_SAAT_RAPOR.txt`, `01_TUM_SAATLER_80_SAYI_TAM56_ZINCIR_0_12_CIKIS.csv`, `02_HEDEF_SAAT_EN_AZ5_OLANLAR_ZINCIRLERI.csv`, `03_HER_HEDEF_SAAT_ISINAN_5_6_7_8_SAYILAR.csv`, `04_ISINMA_ILE_5_6_7_8_ORANLARI.csv`, `05_ISINMA_TIPI_5_6_7_8_ORANLARI.csv`, `06_TAM56_ESKI50_SOGUK_BEKLEME_HAREKET.csv`, `07_BASLANGIC36_SON36_AYNI_ZINCIR_KARSILASTIR.csv`, `08_SON_HAVUZ_SON6_GORUNUS_ORANLARI.csv`, `09_TUM_SAYILAR_DONEM_5_6_7_8_ORANLARI.csv`, `10_KESIN_VERI_VE_YON_TANIMI.json`.

**Sonuç:** Artık "hangi sayı, **hedef başlamadan önceki** 56 halka yolculuğundan sonra, H1–H12 boyunca **5, 6, 7, 8 kez** göründü?" sorusu için eksiksiz otomatik kayıt var. "Gelecek saatte hangi numaralar 5–8 kere çıkacak?" sorusuna doğrulanmış kesin seçim mekanizması bulunamadı.
