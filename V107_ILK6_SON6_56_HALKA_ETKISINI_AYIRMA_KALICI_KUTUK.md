# V107 — İlk 6 çekiliş etkisini 56 halka hareket zincirinden ayırma

**16 Ekim 2026 | Başarılı çalıştırma:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38917498023  
**Kod:** [v107_hedef_saat_ilk6_son6_56_halka_ayristir.py](v107_hedef_saat_ilk6_son6_56_halka_ayristir.py)  
**9 dosyalı ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38917498023/artifacts/12053066622

## Soru

Hedef saatte bir numaranın 5, 6, 7 veya 8 görünümle bitirmesi, **ilk altı çekilişte zaten kaç kere göründüğünden** mi, yoksa önceki **672 çekilişin 56 halkalık sıcaklık ve yön geçmişinden** mi kaynaklanıyor? Bunları aynı ilk altı gözlem düzeyinde karşılaştır.

**V100C, V104, V105, V106 omurgası değiştirilmedi**: global 12 çekilişlik halka kimlikleri sabit; geçmiş 672 çekiliş her yeni çekilişte 1 ileri kayıyor. Hedef saat 12 çekiliş. En eski halkadaki kayıt çıkar, yeni çekiliş eklenir.

## Saatin başında / ortasında / sonunda farklı bilgiler

1. **Hedef başlamadan** önceki 672 gerçek çekilişte, 80 sayının son 55–56 tamamlanmış halka sıcaklık ve yön zinciri dondurulur. Son havuz, son 6 halkadaki yön, eski 49/50 halkada soğukta kaldığı halka sayısı, toplam yön/havuz değişimi ve son havuz hareketinden beri kaç halka geçtiği bilinir.
2. İlk 6 gerçek çekiliş bitince aynı sayının `k` kez görülmüş olduğu bilinir (`0..6`). Bu sayı 56 halka geçmişinden **bağımsız bilgi katmanı**dır.
3. Son 6 başlamadan, **aynı k + aynı son havuz + aynı son altı halkadaki yön** koşulu içinde yalnız daha eski 49–50 halkanın soğukta kalma, hareketlilik ve son hareketin yaşı fark ettiriyor mu diye karşılaştırılır.
4. Son 6 sonuçlarından sonra 12 çekilişte tam `>=5,>=6,>=7,>=8` gerçekleşip gerçekleşmediği işaretlenir.
5. Sadece ilk 36 günlük veri ile koşullu dağılımlar hesaplandı, kalan son 36 gün ve 13 Ekim yeni gün ayrı işlendi. 72 gün eski sürümlerde önceden çok incelenmiştir, bu nedenle gerçek dokunulmamış ileri test diye sunulmaz.

**Önemli:** `k=5` veya `k=6` için zaten `>=5` başarısına ulaşılmıştır. O yüzden bunun 56 halkalık öngörü başarısı olarak sayılmaması gerekir.

## 1.246 tam hedef saatin analiz sonuçları

- İlk 36 gün = **46.960 sayı-saat** örneği.
- Son 36 gün = **51.840 sayı-saat** örneği.
- Sonradan eklenmiş 13 Ekim saatleri de ayrı kaydedildi.
- İnceleme boyunca her saatte 80 sayının **tam 55–56 halkalık sıralı ısı dizisi** ve 54–55 yön simgesi tutuldu.

**Son 36 gün — ilk altı görünümü sabitlenmiş, yalnız ısınan sayılar:**

| İlk 6 görülme sayısı | Önceki 49/50 halkada SOĞUK kalma | Gözlem | Hedef saatte 5+ | Hedef saatte 6+ |
|---|---|---:|---:|---:|
| 3 | Az, 0–5 halka | 621 | **%45,73** | **%16,75** |
| 3 | Orta, 6–11 halka | 1.070 | **%49,44** | **%17,48** |
| 3 | Çok, 12+ halka | 1.024 | **%45,21** | **%16,11** |
| 4 | Az, 0–5 halka | 162 | **%80,25** | **%50,62** |
| 4 | Orta, 6–11 halka | 267 | **%80,90** | **%45,32** |
| 4 | Çok, 12+ halka | 257 | **%81,71** | **%43,58** |

**Bu özet yalnız ilk6 k ve 'ısınan' sınıfını sabitliyor; son sıcaklık havuzları karışık.** GitHub ZIP'deki `02_ISINAN_5_6_7_8_ILK6_ESIT_SON6_TABLO.csv` ayrıca **k, son havuz, son6 yön ve eski halka grubu** aynı tutulmuş tablolardır. Bu örnek oranlar bağımsız sayılar değildir, aynı 72 günlük tarihteki benzer durumlardır.

## Tam56 ekstra bilginin aynı ilk6 görünümüne katkısı

**Son 36 gün, yalnız ısınan sayılar**: H7–H12'de tam kaç kere (0,1,2,3,4,5,6) çıktığını belirlemek için 7 kategorili Brier hatası (düşük daha iyi).

| Bilgi | Son 36 günlük hata |
|---|---:|
| Başlangıçta ilk6 için temel 6-çekiliş sabit referansı | **0,7353843** |
| İlk6 `k` geçmiş koşullu sıklığı | 0,7355519 |
| + Son havuz + son6 halka yönü | 0,7365038 |
| + Eski 49/50 halkanın SOĞUK bekleme sınıfı | 0,7372208 |
| + Son havuz değişikliğinin üzerinden geçen halka | 0,7372598 |
| + Eski 49/50 halkadaki hareket sayısı | 0,7373338 |

**Sonuç:** İlk altı elde kaç kez görüldüğünü ayırdıktan sonra, tam56 halkanın özet hareket özellikleri son 6 eldeki görünüm sayısı üzerinde daha iyi hata oranı sağlamadı. Bu bir “hiçbir geçmiş modeli işe yaramaz” ispatı değildir; mevcut tanımlanmış özetler bu veride öne geçmedi. 5/6/7/8'e ulaşanları geriye dönük zincirleriyle incelemeyi sürdürebiliriz; fakat örneklerin çokluluğu ve tarihsel tekrar kullanım sebebiyle büyük farkları otomatik bir kural saymıyoruz.

## Son tam saat örneği — 13 Ekim 19:02–19:57 (#62003–#62014)

Hedef başlamadan **ısınma yönü** belirlenmiş sayılarda:

| Sayı | H1–H6 | H7–H12 | Toplam | Eski halkada soğuk kalma |
|---|---:|---:|---:|---:|
| 11 | 3 | 2 | **5** | 5 |
| 58 | 2 | 3 | **5** | 3 |
| 73 | 3 | 2 | **5** | 6 |
| 79 | 4 | 1 | **5** | 19 |

72 sayısı bu saatte toplam 5 kez gelmiş olmasına rağmen ilk 6 elde yalnız **1** kez görüldüğü için bu **ilk6=2+** daraltılmış örnek tablosunda listelenmemiştir; tam saatlik 80 sayı dosyasındadır.

## ZIP'de 9 çalışma dosyası

`00_56_HALKA_ILK6_SON6_AYIRMA_RAPORU.txt`, `01_TUM_HEDEF_SAAT_80_SAYI_TAM56_YON_ILK6_SON6.csv`, `02_ISINAN_5_6_7_8_ILK6_ESIT_SON6_TABLO.csv`, `03_ILK6_2_3_4_5_ESIT_ESKI_SOGUK_HALKALAR.csv`, `04_SON36_DONEMINDE_EK_ZINCIR_BILGISI.csv`, `05_SON36_ILK6_HAVUZ_ZINCIR_KOSULLU_OLASILIK.csv`, `06_HER_SAAT_3_4_5_BASLANGIC_SON6_OLAYLAR.csv`, `07_ILK6_DURUMUNA_GORE_GEREKLI_EK_SAYI.csv`, `08_KESIN_METOT_ZAMAN_KONTROL.json`.

**Bir sonraki araştırma:** Sayının **daha az özetlenmiş 56 halkalık dizisindeki belirli yol parçalarının**, ilk6 sabitken son6'nın davranışında tutarlı bir fark üretip üretmediği, yeterli sayı adedi ve tarihsel ayrımla değerlendirilebilir. Bu amaç mevcut yürüyen halkayı değiştirmez.
