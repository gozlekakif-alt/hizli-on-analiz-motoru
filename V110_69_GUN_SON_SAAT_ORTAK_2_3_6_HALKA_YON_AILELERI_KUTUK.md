# V110 — 56 Halka Ortak Yön Aileleri: 69 Günün 23:02–23:57 Son Saati

**16 Ekim 2026.** V104/V105/V108/V109 altyapısındaki **672 çekilişlik FIFO, 56 sabit 12'li halka** değiştirilmedi. Kullanıcı isteği üzerine 80 sayının saat öncesinde **son 2, 3 veya 6 tamamlanmış halka yön dizisi tamamen aynıysa** aynı yön ailesi sayıldı. Saat sonunda birlikte gelme ve 5+/6+ görünüm ayrı raporlandı.

## Kapsam

- **69 son saat** (4 Ağustos–12 Ekim 2026), 5.520 sayı-saat, her saatte 80 sayı ve 3.160 çift.
- İlk **34 gün** sadece davranış tablolarını oluşturmak için kullanıldı; sonraki **35 gün** kronolojik karşılaştırma.
- Aile, saat başlamadan dondurulmuş aynı *Y (ısınma), D (soğuma), = (sabit)* son2, son3 veya son6 yön dizisidir. Hareketli aile: en az bir Y/D var; `===` gibi hiç hareket olmayanlarla karıştırılmıyor.
- Gerçek 23:02–23:57 hedef saatinde her sayının 5+, 6+, 7+, 8+ görünümü; her eşleşen çiftin **H1–H6** ve **H7–H12** içinde aynı çekilişte kaç kez birlikte geldiği ayrı sayıldı.

## Eşleşen aileler tarihsel olarak daha çok birlikte geliyor mu?

**Son 35 gün, H7–H12:** Aynı halka dizisini taşıyan ve taşımayan çiftlerin **bir çekilişte birlikte görünme** oranları:

| Aynı yön dizisi | Farklı çiftler | Aynı aile çiftleri | Hareket içeren aynı-aile çiftleri |
|---|---:|---:|---:|
| Son 2 halka | %5,9986 | %6,1003 (15.278 çift-saat) | %5,9279 (7.670) |
| Son 3 halka | %6,0026 | %6,1843 (6.123) | %6,2893 (3.127) |
| Son 6 halka | %6,0113 | %6,4003 (**388**) | %6,3194 (**240**) |

**Dikkat:** Bu *ham oranlar* yalnız tarihsel benzerliktir, geleceğe yönelik tahmin başarısı değildir. Son altı halkalık tam ortak hareket az bulunuyor; özellikle örnek sayısının düşmesi oranı oynatabilir.

## İlk 6 ve sıcaklık havuzu sabitken katkı

**Karşılaştırma:** Bir çiftin iki üyesinin H1–H6 içinde kaç kez geldiği (0/1/2/3+), ikisinin H1–H6'da **aynı elde beraber görünme sayısı** (0/1/2+) ve saat başlamadan önceki sıcaklık havuzları eşitlendi. İlk 34 günden sabit koşullu frekans tahminleri oluşturulup son 35 günde yalnız **H7–H12 aynı çekilişte birlikte çıkma** olaylarıyla karşılaştırıldı. İkili olay Brier hatası: **düşük iyidir**.

| Kullanılan ek bilgi | Son 35 gün Brier | Basite göre fark |
|---|---:|---:|
| İlk6 iki sayı toplamı + ilk6 aynı-çekiliş eşleşmesi + son havuz çiftleri | **0,056526165** | Referans |
| + Son 2 ortak yön dizisi | 0,056535050 | **+0,000008884** |
| + Son 3 ortak yön dizisi | 0,056532608 | **+0,000006442** |
| + Son 6 ortak yön dizisi | 0,056531893 | **+0,000005727** |
| + Yalnız son 2 hareketli ortak yön | 0,056532540 | +0,000006375 |
| + Yalnız son 3 hareketli ortak yön | 0,056531880 | +0,000005715 |
| + Yalnız son 6 hareketli ortak yön | 0,056532136 | +0,000005971 |

**Sonuç:** Ortak yön aileleri geçmişte mevcut, ancak bu koşullu karşılaştırmada **gelecek son-altı beraber geliş tahminini iyileştirmedi**. Küçük ama pozitif Brier farkları daha kötü anlamına geliyor. Bu, halka yürüyüşünü silmek gerekçesi değildir, sadece bu özel gösterge için ölçülen sonucu dürüstçe kayıt altına alır.

## Son gün (12 Ekim 23:02–23:57) gerçek sayı aileleri

Ortak **son üç yön** ve bir saatte **en az iki üyesi 5+** olan üç aile gözlendi:

| Önceden yön dizisi | Aile sayıları | Hedefte 5+ olanlar | 6+ olanlar |
|---|---|---|---|
| `=D=` | 4, 15, 24, 33, 52, 56, 61 | **15, 33, 52** | 15 |
| `YD=` | 16, 37, 44, 71 | **16, 44** | — |
| `YDY` | 2, 22, 34, 47 | **34, 47** | 47 |

Bu aileler **saat başlamadan önceki** halka hareketleriyle tanımlandı; 5+ olanlar saat **sonlandıktan sonra** etiketlendi. Aile/kupon ile bireysel tekrarı birbirine karıştırmayın.

## Mekanik ve metodoloji

Sıcaklık havuzları her halka sonunda **16+16+16+16+16** sabit kota ile oluşur. Dolayısıyla aynı yönde hareket eden ailelerin oluşması bile bu göreli sıralamanın yapısal özelliği olabilir; ayrıca 20/80 çekilişinde iki sayının tek elde beraber görünmesinin rastgele referansı `(20/80)*(19/79) ≈ %6,0127` değeridir.

Bu sonuç daha önce yoğun incelenmiş 72 günün yeniden sınıflandırılmasıdır, bağımsız yeni saatlere yönelik kesin tahmin değildir. Son 2/3/6 halkanın aynı dizisi üzerinden kupon başarı garantisi veya RNG çözümü iddiası yoktur.

## Dosya arşivi

Konuşmada sağlanan `V110_69GUN_SON_SAAT_2_3_6_HALKA_YON_AILE.zip` içerisinde:
1. 00 — Türkçe kısa gerçek analiz sonucu;
2. 01 — her gün, her ortak yön ailesi, bireysel 5+/6+/7+/8+ ve ilk/son 6 beraber gelişleri;
3. 02 — 69 günlük aile istatistikleri;
4. 03 — son 35 günde 7 modelin eşit-koşullu Brier hesabı;
5. 04 — 35 günlük hata farkları;
6. 05 — aynı yön/ayrı yön ve hareketli aile karşılaştırmaları;
7. 06 — ilk 34 ve son 35 gün hareketli aile sayıları;
8. 07 — son günün birden çok 5+ içeren aileleri;
9. 08 — kesin veri ve karşılaştırma yöntemi.

**Yeniden üretim:** `v110_56_halka_yon_eszamanli_aile_69_son_saat.py` betiği bu konuşmada dosya olarak sunulmuştur; `--source veri.txt` ile V104'ün sabit halka kaynak dizilerini, `--input V108_69_GUN_SON_SAAT_80_SAYI_TAM_HALKA_DNA.csv` ile V108 dökümünü okuyabilir. GitHub'a mevcut V100C–V109 modülleri değiştirilmeden yeni kütük kaydedildi.
