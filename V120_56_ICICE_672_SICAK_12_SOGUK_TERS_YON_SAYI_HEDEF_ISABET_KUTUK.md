# V120 — 56 iç içe havuzda ters yönlü sayıların gerçek hedef isabeti

**GitHub Actions (başarıyla tamamlandı):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38966929742

**Tam ZIP, 9 dosya:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38966929742/artifacts/12075360951

**Tekrar çalıştırılabilir Python:** [v120_56_icice_ters_yon_sayi_12_672_tahmin_test.py](v120_56_icice_ters_yon_sayi_12_672_tahmin_test.py)

## Yöntem

15.790 kayıtlı gerçek çekiliş, son #62014 (13 Ekim 2026). İlk 672 hafıza kuruldu. Kalan **15.118 gerçek hedef çekilişi** gerçekleşmeden önce 80 sayının son **12,24,36,...672** çekiliş görünme sayıları sıralandı; her pencerede 16 soğuk, 16 serin, 16 nötr, 16 ılık, 16 sıcak sayı belirlendi. Bunlar V100B'nin **56 iç içe geçmiş** pencereleridir; birbirinden ayrık 12'li halkalar değildir.

İki uç karşılaştırma:
- 672 SICAK → 12 SOĞUK;
- 672 SOĞUK → 12 SICAK.

Ters yön burada kronolojik değişme değil, aynı hedef öncesi anda **farklı büyüklükte geçmiş pencereye bakınca oluşan göreli havuz farkıdır**. Hedef çekilişin çıkış bilgisi hesaplamada kullanılmadı. Tek sayı adil çıkış beklentisi her zaman %25'tir.

## Dönemlere göre gerçek sonraki tek çekiliş isabetleri

| Dönem | 672 sıcak / 12 soğuk | 672 soğuk / 12 sıcak |
|---|---:|---:|
| İlk 36 gün, 7.140 hedef | 4.402 / 17.554 = **%25,0769** | 4.172 / 16.692 = **%24,9940** |
| Orta 18 gün, 3.906 hedef | 2.290 / 9.319 = **%24,5735** | 2.386 / 9.477 = **%25,1767** |
| Son 18 gün, 3.906 hedef | 2.429 / 9.475 = **%25,6359** | 2.138 / 8.491 = **%25,1796** |
| Sonradan eklenen 166 hedef | 133 / 469 = **%28,3582** | 146 / 502 = **%29,0837** |

Son 166 gözlemin uç grupları çok küçük ve tarihsel olarak zaten incelenmiş olduğundan yüksek görünen oranlar kesin avantaj kanıtı değildir.

## Son18 gün, yön kontrolü

| Grup | Sayı-hedef gözlemi | Hedefte çıktı | Oran |
|---|---:|---:|---:|
| 672 sıcak → 12 soğuk | 9.475 | 2.429 | **%25,6359** |
| 672 sıcak → 12 soğuk DIŞINDA | 53.021 | 13.240 | **%24,9712** |
| 672 soğuk → 12 sıcak | 8.491 | 2.138 | **%25,1796** |
| 672 soğuk → 12 sıcak DIŞINDA | 54.005 | 13.456 | **%24,9162** |
| En az 2 havuz soğuma | 67.382 | 16.980 | **%25,1996** |
| En az 2 havuz ısınma | 68.131 | 17.066 | **%25,0488** |
| 1+ havuz soğuma | 119.799 | 30.041 | **%25,0762** |
| 1+ havuz ısınma | 121.134 | 30.274 | **%24,9922** |
| Sınıf değiştirmedi | 71.547 | 17.805 | **%24,8857** |

### %95 gün bazlı bootstrap, son18 gün

- Sıcaktan soğuğa hedef oranı: **%25,6359**, %95 **%24,890–26,414**, teorik %25 bu aralıkta.
- Soğuktan sıcağa hedef oranı: **%25,1796**, %95 **%24,475–25,890**, teorik %25 bu aralıkta.
- Sıcaktan soğuğa EKSİ soğuktan sıcağa: **+0,4563 yüzde puan**, %95 **[-0,248,+1,226] puan**.
- Sıcaktan soğuğa EKSİ aynı 672-sıcak kökenli diğer sayılar: **+0,665 puan**, %95 **[-0,103,+1,455]**.
- Soğuktan sıcağa EKSİ aynı 672-soğuk kökenli diğer sayılar: **+0,263 puan**, %95 **[-0,640,+1,145]**.
- En az 2 sınıf soğuma EKSİ en az 2 sınıf ısınma: **+0,151 puan**, %95 **[-0,381,+0,678]**.

**Hiçbir önceden tanımlı kıyas, bu dönemde istatistiksel olarak güvenilir üstünlük göstermiyor.** Ayrıca sıcaktan soğuğa eğilim orta 18 günde %25'in altında, son 18 günde üstünde — işaret kalıcı değil.

## ZIP içeriği

1. 00_V120_TURKCE_YON_KARSILASTIRMA_KISA.txt — Türkçe sonuç
2. 01_TUM_HEDEFLER_KARSIT_YON_GUNLUK_ISABET.csv — 15.118 hedefte her grubun boyutu ve hedefte kaçının çıktığı
3. 02_DONEM_YON_GRUPLARI_ISABET.csv — dönem sonuçları
4. 03_672X12_BES_HAVUZ_25_HUCRE_GERCEK_ISABET.csv — 25 havuz kombinasyonu
5. 04_TERS_UC_HAREKET_EDEN_SAYILARIN_56_HALKA_IZLERI.csv — uç gruplarda 56 pencerenin 1/0 sonuçları, sıklık ve sınıflar
6. 05_80_SAYI_SON_56_HAVUZ_KAYIT.csv — son hedef öncesi tam 80 sayının 672 bit ve 56 pencere izleri
7. 06_GUN_GUN_YON_ISABET_ORANLARI.csv — günlük ayrıntı
8. 07_DONEM_GUN_BAZLI_GUVEN_ARALIKLARI.csv — küme bootstrap
9. 08_METOD_VE_DENETIM.json — zaman öncesi özellik kanıtı

**Karar:** Ters yönlü sayılar gerçekten çıkıyor, fakat rastgele %25 beklentisi çevresinde; tahmin üstünlüğü yok. Daha önce pek çok kez incelenen geçmiş dönemleri yeni kör test sayamayız. Gerçek ileriye dönük onay olmadan sonuçlar kupon avantajı olarak yorumlanmamalıdır.
