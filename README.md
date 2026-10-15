# HIZLI ON — GitHub Ana Araştırma Sayfası

**Son güncelleme:** 15 Ekim 2026

Bu depo, kullanıcı tarafından sağlanan gerçek çekiliş sonuçlarıyla 1–80 arasından 20 sayı çekilen Hızlı On oyununun betimsel ve ileriye dönük kontrol deneylerini toplar. Araştırmanın amacı **rastgele beklenenden bağımsız olarak üstün olan bir tahmin yöntemi var mı?** sorusunu sınamaktır. Şu ana kadar güvenilir üstünlük doğrulanmamıştır.

## Kaynak ve zaman disiplini

- **Ana ham veri:** [veri.txt](veri.txt), format `ÇEKİLİŞ_NO;GG.AA.YYYY SS:DD;1,2,...,20`.
- **72 tam gün:** 1 Ağustos–12 Ekim 2026 aralığında toplam **15.624 çekiliş**, her tam gün **217 çekiliş**. 23 Ağustos (215 çekiliş) gibi eksik günler tam-gün testlerine katılmamalı; ham veri güncellenirse kapsam yeniden hesaplanmalı.
- Günlük dağılım: `00:02–01:02` 13 çekiliş; `07:02–23:57` 204 çekiliş. **01:02–07:02 arasındaki boşluk, 5 dakikalık ardışık geçiş değildir.**
- Gerçek tahmin testi: Her saatin **ilk 6 çekilişi** görüldükten sonra sonraki **7.–12. çekilişler için** seçimi sabitle, sonra puanla; hedefe ait veriyi tahminde kullanma.
- Adil bağımsız 20/80 başlangıç beklentisi: Tek sayı %25; **10 sayılık önceden seçilmiş listede 2,5**, 20 sayılık listede 5 isabet. Aynı çekilişte seçilen sayıların olasılıkları bağımsız değildir.
- **Geçmiş 36 gün test dönemleri artık tekrar tekrar incelenmiştir**; yeni bağımsız kanıt için yeni tarihlerde yöntem değiştirmeden prospektif değerlendirme yapılmalıdır.

## Programlar ve test sonuçları

| Sürüm | Dosya | Ne ölçülüyor? | Şimdiye kadarki karar |
|---|---|---|---|
| V58 | [v58_family_120_core.py](v58_family_120_core.py) | 120 betimsel aile/zaman metriği, 72 gün ve saatler | Desenler kataloglandı; RNG dışı sinyal kanıtlanmadı |
| V59 | [v59_aile_birlesim_donusum_kor_test.py](v59_aile_birlesim_donusum_kor_test.py) | Aile birleşimi, dönüşüm, 10'lu liste kör geriye dönük test | Aile dönüşümü 2,502/10; rastgele kontrol 2,507/10 |
| V60 | [v60_komsu_salinim_20_80.py](v60_komsu_salinim_20_80.py) | ±1/±2, yön, 10'luk ve 20'lik bant, 5–60 dakika | Komşuların gözlenen sayısı havuz büyüklüğünün rastgele beklentisine çok yakın |
| V61 | [v61_geometrik_dna.py](v61_geometrik_dna.py) | 8×10 düzeninde aynı şeklin kayma, dönme, aynalama ve yeni konumda oluşması | Geometrik model tarihsel testte rastgele beklentiden daha iyi değil |
| V62 | [v62_geometrik_aile_yasam_motoru.py](v62_geometrik_aile_yasam_motoru.py) | Şekillerin doğumu, parçalanması, birleşmesi, aile soy ağacı | 15.550 gerçek ardışık geçiş, 182.510 aile kaydı, 69.270 soy bağı; öngörü doğrulanmadı |
| V63 | [v63_coklu_motor_turnuvasi.py](v63_coklu_motor_turnuvasi.py) | 31 sabit yöntem ve geliştirmede seçilen 2 birleşik kontrol | Son 36 günlük tarihsel testte en iyi sonradan görünen FRESH6 2,554/10; çoklu test düzeltmesi geçilmedi |

İlgili [GitHub Actions geçmişi](../../actions) hesaplamanın başarılı/başarısız yürütmelerini ve süreli ZIP çıktılarını içerir. Programların kaynak kodu depoda kalıcıdır; Actions **artifact** dosyaları saklama süresi bitince kaybolabilir.

## YENİ BULGU — 217 çekilişte günlük 80 sayının alt/üst sınırları

Bu bölüm 15 Ekim'de mevcut `veri.txt` üzerindeki **72 tam gün**, **15.624 çekiliş** için hesaplandı. **Betimsel ölçümdür; tek başına ertesi gün tahmini değildir.**

Her tam günde 217×20 = **4.340 sayı görünümü**, 80 sayıya bölünür. Günlük sayı başına ortalama **54,25** daima sabittir. Bu, her sayının gerçekten 54 veya 55 defa çıkması gerektiği anlamına gelmez.

| Günlük ölçü | Gerçek 72 günlük ortalama |
|---|---:|
| Her sayının günlük beklenen ve gerçekleşen genel ortalaması | **54,25** |
| O gün en az çıkan sayının sayısı | **39,3056** |
| O gün en çok çıkan sayının sayısı | **70,4861** |
| Günün en yüksek eksi en düşük çıkış sayısı | **31,1806** |
| Gün içi 80 sayı frekansının standart sapması, günlük ortalama | **6,4007** |

- **Tek gündeki en düşük**: 28 Ağustos 2026'da **34 numara 34 defa**.
- **Tek gündeki en yüksek**: 25 Ağustos 2026'da **55 numara 83 defa**.
- 72 günün tümünde en çok görülen sayı: **52**, toplam **4.041**, günlük ortalama **56,125**.
- 72 günün tümünde en az görülen sayı: **59**, toplam **3.743**, günlük ortalama **51,9861**.
- Herhangi bir **önceden seçilmiş tek sayı** için adil bağımsız çekiliş modeli `X ~ Binomial(n=217,p=0.25)`: E[X]=54,25, standart sapma ≈ **6,379**. **80 sayı içinden gün sonunda minimumu/maksimumu seçmek** bambaşka bir örneklem olayıdır: bu uçları 54,25 ile tek sayıymış gibi sınamayın.

## Takip edilecek V64 araştırması (henüz yazılmadı / çalıştırılmadı)

**217 çekiliş — Günlük uç frekansın ertesi gün hareketi:**

1. Her gerçek tam günde 80 sayı için frekans ve gün sonu alt/üst 5, alt/üst 10, 40 altı / 70 üstü kategorilerini sabitle.
2. **Yalnız gerçekten ardışık takvim günlerindeki** tam günleri eşleştir (eksik gün varsa atlama yok). O gün 34–40'a düşen sayı ertesi gün kaç kez çıkmış? 70–83'e çıkan sayı ertesi gün kaç kez çıkmış?
3. Etiketli gerçek sayıların ertesi gün frekansını tek sayı için **54,25** adil referansıyla, aynı gün en düşük/en yüksek seçilmesiyle oluşan `regression to the mean` etkisini de karşılaştıran **bağımsız sentetik 20/80 günlük dizileriyle** ölç.
4. Yön ve eşik taramalarında 80 sayı / çoklu deneme yanlılığını düzelt; gün birimiyle güven aralığı raporla.
5. Kuralların sonunda seçilecek tek/az sayıda modelin sonraki **yeni ve önceden görülmemiş** günlerdeki isabetini ölç. Tarihsel çıkış sayısı tek başına sonraki çekiliş ihtimalini yükseltmez.
6. **Henüz hiçbir model para karşılığı kupona bağlanmadı.** İstatistiksel üstünlük gösterilmedikçe kupon sayısını artırma.

### Yeni sohbetten devam etme

Yeni sohbette şu tek adresi paylaşmak yeterli:

**https://github.com/gozlekakif-alt/hizli-on-analiz-motoru**

Yeni asistana: **“Bu depodaki README, veri.txt, V58–V63 programları ve Actions sonuçlarına bak. V64'te günlük 217 çekiliş için sayıların alt/üst frekanslarının ertesi gün hareketini, bağımsız RNG kontrolüyle araştırmaya devam et. Gelecek çekilişi önceden görme ve geçmişi tahmin başarısı gibi sunma.”** de.

_Not: Bu README denemelerin kaynak kodlarını ve doğrulanmış kısa sayısal sonuçlarını tek noktada tutar; bütün ayrıntılı raporlar GitHub Actions çıktı ZIP'lerinde olabilir. Son günlük alt/üst istatistik için henüz ayrı V64 hesaplayıcısı yoktur._
