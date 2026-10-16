# V122 — 12, 24, 36, 72 Birikimli Havuz Yön Kırılması ve Gerçek 12 Çekilişlik Bloklar

**17 Ekim 2026. Başarıyla tamamlanmış GitHub Actions:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38973241696

**Tüm sonuçları içeren ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38973241696/artifacts/12077683723

**Program:** [v122_56_halqa_12_24_36_72_yon_kirilmasi_hedef_sayi.py](v122_56_halqa_12_24_36_72_yon_kirilmasi_hedef_sayi.py)

## Net ayrım

- 56 halka 12,24,36,...672 çekilişlik birbirine GÖMÜLÜ kümülatif referanstır. Hepsi hedefin hemen öncesinde biter.
- Havuz yön kırılması, aynı andaki farklı uzunluklu 12/24/36/72 sıralamaların V veya ters-V desenidir; gerçek zamandaki yön değişimi DEĞİLDİR.
- Zamandaki gerçek çıkış yön değişimi ayrıca önceki **36 çekilişin üç farklı, bitişik ve ayrı 12'lik bloğundaki** sayı görünme adetlerinde ölçülür.
- Her sayı hep 80'li sıralamadaki frekansına göre 16 soğuk +16 serin +16 nötr +16 ılık +16 sıcak havuzdan birine aittir.
- Aileler kullanılmadı. Hedef çekiliş gelmeden havuz ve blok işaretleri donduruldu; hedefin 1/0 sonucu yalnız etiket olarak işlendi.

## Kapsam

- 15.790 gerçek çekiliş; son veri #62014, 13 Ekim 2026.
- 672 geçmiş ısınmadan sonra **15.118 hedef**, 16 sabit sayı yöntemi ve 8 ayrı rastgele kontrol (24 yöntem).
- İlk 36 gün: 7.140 hedef; orta 18 gün: 3.906; son 18 gün: 3.906; 13 Ekim ek 166.
- Doğrulamada yalnız 10 sayılık ortalamaya göre bir model seçildi; son18 sonuçlarına göre seçim sonradan değiştirilmedi.
- Tarihsel son18 gün, V9–V121 önceki araştırmalarda incelendiği için gerçekten yeni bağımsız kör test değildir.

## Doğrulamanın seçtiği model: TURN24_VALLEY

12'lik penceredeki havuz sınıfı 24'lükten daha sıcak, 36'lıktaki sınıf da 24'lükten daha sıcak. 24'lükte V çukuru bulunan sayılara öncelik verilir; yeterli sayı çıkmazsa kalanlar HOT72 ile tamamlanır.

| Son 18 gündeki 3.906 hedefte | TURN24_VALLEY | HOT72 | 8 rastgele ortalama |
|---|---:|---:|---:|
| 3/3 tam isabet | 54 | 65 | 52,375 |
| 4/4 tam isabet | 11 | 14 | 11,125 |
| 5/5 tam isabet | 2 | 2 | 2,625 |
| 6/6 tam isabet | 0 | 0 | 0,250 |
| 8/8 tam isabet | 0 | 0 | 0 |
| 10/10 tam isabet | 0 | 0 | 0 |
| 10 sayıda ortalama isabet | **2,5023** | **2,5100** | **2,5067** |
| 20 sayıda ortalama isabet | **4,9974** | **5,0236** | **4,9998** |

Önceden seçilmiş TURN24_VALLEY'nin HOT72'ye göre 10 sayıda gün-blok eşlenmiş farkı −0,00768 isabet/çekiliş, %95 aralık [−0,05581,+0,04173]. Rastgele8'e göre fark −0,00435, %95 [−0,04391,+0,03306]. Her iki aralık sıfırı kapsar.

## Sayı-hedef düzeyindeki işaretler: son 18 gün

| Hedef öncesi işaret | Sayı-hedef sayısı | Hedefte çıkan | Gerçek çıkış oranı |
|---|---:|---:|---:|
| 24'lükte V çukuru | 34.169 | 8.558 | **%25,0461** |
| 24'lükte ters V tepesi | 34.234 | 8.490 | %24,7999 |
| 36'lıkta V çukuru | 34.293 | 8.528 | %24,8680 |
| 36'lıkta ters V tepesi | 33.402 | 8.387 | %25,1093 |
| Kısa 12'lik blokta gerçek zamanlı toparlanma | 75.859 | 18.992 | **%25,0359** |
| Kısa 12'lik blokta gerçek zamanlı tepe | 78.093 | 19.490 | %24,9574 |
| Havuz kırılması VE gerçek zamanlı toparlanma | 32.297 | 8.183 | **%25,3367** |
| Havuz kırılması VE gerçek zamanlı tepe | 33.731 | 8.407 | %24,9237 |

Adil tek sayı çekiliş beklenen oranı tam **%25**. Dikkat çeken birleşik hareket işareti %25,3367 olsa bile gün-blok %95 aralığı **%24,8235–25,8681**; %25'i içerir. Önceden seçilen TURN24_VALLEY tek-sayı oranı %25,0461, %95 aralık %24,6326–25,4602.

### V dönüşü dışında seçilmeyen modeller

- COMBO_TURN_REAL_REBOUND doğrulamada ikinci 10-sayı ortalaması: **2,55044**, son18 ortalaması **2,51536**; son18 8+/10 **2 kez**, 10/10 sıfır.
- REAL_12_REBOUND doğrulamada dördüncü: 2,52611; son18: 2,51792.
- TURN36_PEAK doğrulamada sekizinci: 2,50384; son18: 2,51587.

Bu sayılar doğrulamada birinci sırayı almayan **alternatiflerin geçmiş performansıdır**. Son dönemde iyi görünene sonradan yönelmek güvenilir tahmin kanıtı değildir; yüksek isabeti tespit etmek için gelecekte sabit protokolle kontrol edilmelidir.

## ZIP dosyaları

- 00_V122_KISA_GERCEK_SONUC.txt
- 01_24_MODEL_15118_CEKILIS_3_4_5_6_8_10_20_ISABET.csv — hedef öncesi seçilen sayıların ve gerçek isabetin tam izi
- 02_HAVUZ_YON_KIRILMASI_13_ONCU_GRUP_HEDEF_SONUC.csv — her hedefte 13 koşulun sayı sayısı ve çıktığı sayı
- 03_GUN_BAZLI_SINYAL_25YUZDE_GUVEN_ARALIK.csv
- 04_24_MODEL_DONEMLER_7_FARKLI_KUPON.csv
- 05_SON_HEDEF_80_SAYI_56_HALKA_YON_1_0_PROFIL.csv
- 06_SON18_KILITLI_MODEL_ESLENMIS_KONTROL.csv
- 07_TEST_DENETIM.json

**Karar:** V dönüşü ve gerçek kronolojik 12-blok toparlanması gerçekten ölçülmüştür. Tarihsel bireysel çıkış oranları %25'e yakın, model kuponları benzer bütçeli HOT72 ve rastgele kontrollerden güvenilir biçimde üstün değil. Aynı çekiliş başına daha fazla model ve kupon tarandıkça tesadüfi tam isabet de artar; yeni zaman damgalı ileriye dönük test olmadan kazanç avantajı iddia edilemez.