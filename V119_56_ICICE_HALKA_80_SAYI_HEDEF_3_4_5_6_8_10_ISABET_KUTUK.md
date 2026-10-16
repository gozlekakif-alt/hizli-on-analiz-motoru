# V119 — Aileler Yok: 80 Sayının 56 İç İçe Halkasından Hedef İsabeti

**16 Ekim 2026.** Gerçek GitHub Actions koşusu başarıyla tamamlandı:
https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38965886732

**Eksiksiz ZIP arşivi:**
https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38965886732/artifacts/12074198992

**Tekrar çalıştırılabilir kod:**
[v119_56_icice_sayi_hedef_3_4_5_6_8_10_test.py](v119_56_icice_sayi_hedef_3_4_5_6_8_10_test.py)

## Yöntem

Aile seçimi kullanılmadı. Son 672 gerçekte çekilmiş 20/80 hedeflerinden önce, bütün 80 sayının geçmiş 12,24,36,…,672 pencerelerindeki görünme frekansı, 16'şarlı beş havuzdaki yönü ve 1/0 geçmişi hesaplanır. Yalnız hedef çekilişten önceki veriler model skoruna girer; sonra gerçek sonuçla karşılaştırılır. Model her çizimde 10 sayı sıralar; önden 3,4,5,6,8,10 sayı seçilerek tüm boylarda ayrı ayrı isabet ölçülür. Her yöntem boy başına bir kupon/çekiliştir.

Kaynak 15.790 gerçek çekiliş; ilk 672 hafıza, sonraki **15.118 hedef çekiliş**. Son gözlenen çekiliş 13 Ekim 2026 #62014. Tarihsel 72 tam günün 36/18/18 bölümü ve ek 166 gözlem. Son18 dönemde 3906 hedef çekiliş.

NEST_CONTRAST modeli 56 iç içe halkanın 6 kısa penceresindeki havuz ortalaması eksi 6 uzun penceresindeki havuz ortalamasına göre sayı seçer. Diğer modeller ters yön NEST_REVERSAL, 1/0 kısa artış NEST_01_BURST, HOT12, HOT72, HOT672 ve eşit miktarda RANDOM'dur. Sonuçları görüp sonra en başarılı modeli seçmek test değildir; birincil modeli NEST_CONTRAST olarak sabitledik.

## Son 18 tam gün, 3906 hedefin tam k/k isabet adedi

| Kupon | NEST_CONTRAST | HOT72 | RANDOM |
|---|---:|---:|---:|
| 3/3 | 50 | 65 | 61 |
| 4/4 | 8 | 14 | 9 |
| 5/5 | 1 | 2 | 3 |
| 6/6 | 0 | 0 | 1 |
| 8/8 | 0 | 0 | 0 |
| 10/10 | 0 | 0 | 0 |

## 10 sayılık kupon, son18 gün

| Model | Ortalama isabet | 5+ | 6+ | 8+ | 10/10 |
|---|---:|---:|---:|---:|---:|
| NEST_CONTRAST | 2,4954 | 243 | 63 | 0 | 0 |
| NEST_REVERSAL | 2,5054 | 252 | 54 | 0 | 0 |
| NEST_01_BURST | 2,5097 | 240 | 49 | 1 | 0 |
| HOT12 | 2,4995 | 255 | 57 | 1 | 0 |
| HOT72 | 2,5100 | 244 | 54 | 0 | 0 |
| HOT672 | 2,4946 | 229 | 53 | 0 | 0 |
| RANDOM | 2,5164 | 253 | 61 | 0 | 0 |

NEST_REVERSAL 6/6 iki kez göründü; fakat yedi model ve çeşitli kupon boyları tarandığı için tesadüf olabilir. NEST_REVERSAL'ın 10 sayıda ortalama 2,5054 isabeti rastgele 2,5164'ün altındadır. Tek başına seyrek 6/6 gelecekte avantajı göstermez.

18 günün eşlenmiş bootstrap testinde 10 sayıda NEST_CONTRAST farkı:
- Rastgeleye göre −0,02099 isabet/çekiliş, %95 aralık [−0,07655, +0,02714]
- HOT72'ye göre −0,01459, %95 aralık [−0,05888, +0,02817]

Her iki belirsizlik aralığı sıfırı kapsar: **kanıtlanmış ek tahmin üstünlüğü yok**. Tarihsel son18 gün de bu sohbetin daha önceki araştırmalarında görüldüğünden gerçek anlamda dokunulmamış ileriye dönük test değildir.

## Ek 166 gerçek çekiliş (13 Ekim, geçmişte incelenmiş)

NEST_CONTRAST tam isabetleri 3/3=1, 4/4=0, 5/5=0, 6/6=0, 8/8=0, 10/10=0. Rastgele 3/3=5, 4/4=1, geri kalan tam 0. Küçük örnek üzerinden sonuç çıkarılmamalı.

## GitHub Actions çıktısındaki 6 dosya

- 00_V119_TURKCE_KISA_CEKILIS_SONUC.txt — Özet
- 01_HER_HEDEF_3_4_5_6_8_10_CEKILIS_KUPON_ISABET.csv — 15118×7=105826 sonuç öncesi seçilmiş gerçek kupon ve isabet
- 02_MODELLER_DONEMLER_K_K_ISABET_ORTALAMA.csv — 3/3–10/10 ve dönem
- 03_SON_HEDEF_80_SAYI_56_ICICE_HAVUZ_01_PROFIL.csv — Son hedef öncesi 80 sayının 672 bit geçmişi ve 56 pencere havuz/yön zinciri
- 04_GUN_ESLESMELI_GUVEN_ARALIKLARI.json — Farkların belirsizliği
- 05_DENETIM_KAPSAM.json — Zaman ve veri kontrolü

**Karar:** Ailelerden bağımsız 56 iç içe halkanın sayı karakteri, önceki tarihi veride gerçek tahmin avantajını göstermedi. Kupona para yatırmak için güvenilir yöntem diye sunulmamalıdır.
