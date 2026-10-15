# HIZLI ON — GitHub Ana Araştırma Sayfası

**Son güncelleme:** 15 Ekim 2026 (V77 tamamlandı)

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
| V64 | [v64_gunluk_isi_yon_kademeli.py](v64_gunluk_isi_yon_kademeli.py) | 72 tam gün; 70 gerçek ardışık gün çifti, 68 üçlü gün, 240 adil 20/80 RNG tekrarında 8 önceden tanımlı ölçüm | Göreli kademeli geçiş %51,786 (RNG %52,031); sabit-eşik kademeli %70,554 (RNG %71,594). Düzeltilmiş 8 testte doğrulanan üstünlük yok |
| V65 | [v65_7_8_9_10_aile_tamamlama.py](v65_7_8_9_10_aile_tamamlama.py) | 7,8,9,10 sayılı tam aile olasılığı; önceki 72+ilk6 çekilişten sabit aday, hedef sonraki6; düşük/yüksek yakın görünüm | LOW: 7'li ort.1,7564 ve 0 tam; 8'li 2,0240 ve 1 tam; 9'lu 2,2439 ve 0 tam; 10'lu 2,5364 ve 0 tam. Keşifsel; istatistiksel tahmin üstünlüğü doğrulanmadı |
| V66 | [v66_72gun_ilk20_birliktelik.py](v66_72gun_ilk20_birliktelik.py) | 72. gün ilk çekilişin 20 sayısından 190 ikili ve 2–10 arası 616.645 farklı grubun önceki 71 günde aynı çekilişte bulunma sayısı; sonraki 216 çekiliş kontrolü | En sık ikili 30–62 (991), en seyrek 41–59 (836); geçmişte az/çok ikili gelecekte 257/256 tam olay, adil beklenti her yanda ~260; üstünlük kanıtlanmadı |
| V67 | [v67_217_cekilis_tum_birliktelik.py](v67_217_cekilis_tum_birliktelik.py) | 72. tam günün tüm 217 çekilişi: her 20'linin 2–10'lu 616.645 grubunun geçmişte aynı çekilişte kaç kez bulunduğu (toplam 133.811.965 tam sayım); önceki 71 gün + o günün önceki çekilişleri; tek ZIP | Sonraki çekilişe önceden dondurulan en az/en çok 10 ikili: 134/113; üçlü: 28/39; 7–10'lularda tam 0. Adil RNG dışı üstünlük doğrulanmadı |

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

## V64 tamamlandı — Günlük sıcaklık, yön ve kademeli geçişler

GitHub Actions çalışması: [V64 otomatik test ve ZIP raporu](../../actions/workflows/v64-gunluk-isi-yon-kademeli.yml).

- Veri: 72 tam gün = 15.624 çekiliş; yalnız **70 gerçek ardışık takvim günü çifti** ve **68 tam üç günlük dizi**. Eksik günler atlanıp yan yana sayılmadı.
- Sınıflar: Her gün **80 sayının 16'şarlı beş göreli sıcaklık dilimi** ve ayrıca sabit frekans dilimleri (`≤44, 45–50, 51–57, 58–63, ≥64`).
- **Göreli kademeli geçiş:** gerçek %51,786; 240 adil RNG tekrarının ortalaması %52,031.
- **Sabit sınıf kademeli geçiş:** gerçek %70,554; RNG ortalaması %71,594.
- **Aynı göreli sınıfta kalış:** gerçek %19,607; RNG %20,002.
- **Üç günlük sayısal yön devamı:** gerçek %28,824; RNG %29,058.
- **Dün en sıcak seçilen 10 sayının ertesi gün isabeti:** gerçek 2,489; RNG 2,500 (adil beklenti 2,5).
- **Sonuç:** Önceden kodlanmış sekiz incelemenin hiçbirinde iki taraflı Monte Carlo, aile düzeyi çoklu test düzeltmesi sonrası üstünlük doğrulanmadı. Bunlar tarihsel keşiflerdir; yeni bağımsız gelecek veride doğrulama sayılmaz.

Kaynak kodu ve test yöntemi GitHub'a kalıcı işlendi. Raporun ZIP çıktısı Actions üzerinde **süreli artifact** olarak saklanır. Sonuçlar kupon satın almayı gerekçelendirmez.

### V65 için olası devam (henüz uygulanmadı)

**Yeni veriye dokunmadan kuralı sabitle:** Önceden belirlenen 8 V64 göstergesinden tercihen tek bir yön göstergesini seç, yeni tam günler geldikçe tahminleri önceden kaydet, her 217 çekilişte 10 sayılık sabit bir seçim yapılıyorsa 2,5 adil isabetiyle karşılaştır. Geçmiş 72 gün üzerinde başka parametre aramak bağımsız kanıt değildir.

## V65 tamamlandı — 7–10 kişilik ailelerin birlikte tamamlanması

Kaynak: [V65 script](v65_7_8_9_10_aile_tamamlama.py) ve [V65 Actions tek ZIP raporu](../../actions/workflows/v65-7-8-9-10-aile-tamamlama.yml).

**Adil 20/80 düzeneğinde tek, önceden seçili k grubunun tamamının çıkma olasılığı:**

- 7/7: 0,0000244026 ≈ 40.979'da 1
- 8/8: 0,0000043457 ≈ 230.115'te 1
- 9/9: 0,0000007243 ≈ 1.380.688'de 1
- 10/10: 0,0000001122 ≈ 8.911.711'de 1

**Yeni test** her saatin ilk 6 çekilişine kadar bilinen son 72+6 çekilişin ikili ortak kümelerinden tam 7,8,9,10 büyüklüğünde aile türetti. Her boyutta düşük/geçmişte az, yüksek/çok, uzun ara veren ve rastgele aileleri önceden dondurarak sonraki 6 çekilişe uyguladı.

- Tam 72 gün; düşük hareketli 7'li ortalama **1,7564/7**, tam 0.
- Düşük hareketli 8'li **2,0240/8**, tam **1** (7776 hedeften; adil beklenti 0,0338 tam).
- Düşük hareketli 9'lu **2,2439/9**, tam 0.
- Düşük hareketli 10'lu **2,5364/10**, tam 0.
- **Az hareketli vs çok hareketli** isabet farkı (gün blok bootstrap): 7'li +0,0540; 8'li +0,0319; 9'lu +0,0034; 10'lu +0,0653. 7'li ve 10'lu için keşifsel %95 blok aralıkları pozitif görünse de **geçmiş verinin tekrar kullanılması, grup ve yöntem seçimi, çoklu deneme** nedeniyle yeni testlerde doğrulama gerekir.
- Bu sınıflandırma **grubun tüm üyelerinin nadir görünmesi değildir**: 7'li ailede en az 5, 8'li en az 6, 9'lu en az 7, 10'lu en az 8 üyenin geçmişte aynı çekilişte kaç defa bulunduğuna göre sıralandı.
- Sabit bir aile için bir önceki çekilişte çıkmaması, adil bağımsız sistemde sonraki çekilişte tam çıkma olasılığını artırmaz. **Nadirlikten kupon satın alma önerisi yapılmıyor.**

### Araştırma kararı

Aile tamamlamada matematiksel olarak en nadir 10'lu; bunun için **öncelikli hedef olmasını destekleyen güvenilir kanıt yok**. Sonraki yeni günler geldiğinde, aynı önceden sabitlenen LOW_ACTIVITY ölçümüyle 7 ve 10'luların rastgele kontrole göre davranışını ileriye dönük inceleyebiliriz. Diğer yöntemleri ve eşikleri sonuçlara göre yeniden optimize etmek yerine kuralları önce kilitlemeliyiz.

## V66 tamamlandı — 72. günün ilk 20 sayısı için geçmişte aynı çekilişte birlikte görünme

[Kaynak kodu](v66_72gun_ilk20_birliktelik.py) · [GitHub Actions ZIP raporu](../../actions/workflows/v66-72gun-ilk20-birliktelik.yml) — tek ZIP içinde 190 ikili, her grubun matematiksel olasılığı, 2–10 üyeli **616.645 gruba ait tam geçmiş sayım tablosu**, 7–10'lu dahil özet, ve 72. gün kalan 216 çekiliş kontrolü.

- **72. tam gün:** 12 Ekim 2026. İlk çekiliş: **#61629 — 00:02**; çekilen 20: `5, 6, 11, 22, 23, 30, 31, 32, 35, 39, 41, 43, 47, 54, 55, 57, 59, 62, 74, 75`.
- **Geçmiş veri sınırı:** yalnız bundan önceki **71 tam gün = 15.407 çekiliş**, ilk çekilişin kendisi veya 12 Ekim'deki sonraki çekilişler geçmiş ihtimale dahil değil.
- 190 ikiliden en çok **30–62: 991/15407 = %6,432**, en az **41–59: 836/15407 = %5,426**. Bağımsız adil 20/80 için sabit ikili **%6,013**; A çıktıktan sonra B'nin aynı çekilişte çıkması için adil koşullu olasılık **19/79 ≈ %24,05**.
- Bir sabit gruba ait geçmiş beklenen birlikte görünüm: **2'li 926,37; 3'lü 213,78; 4'lü 47,20; 5'li 9,94; 6'lı 1,99; 7'li 0,376; 8'li 0,067; 9'lu 0,011; 10'lu 0,0017**.
- İlk 20 sayıdan kurulu **184.756** adet 10'lu gruptan **184.447'si** önceki 71 günde sıfır kez tam birlikte göründü. Bu durum düşük teorik olasılığın doğal sonucudur, "yakında gelecek" sinyali değildir.
- **72. günün kalan 216 çekilişi**, ilk 20 sayıyla ortalama **5,0185** sayı örtüştü; adil beklenti **5**. Geçmişte 190 ikilinin en seyrek 20'si sonraki 216 çekilişte toplam **257** kez aynı çekilişte tamamlandı; en sık 20'si **256** kez. Her iki grubun rastgele tamamlama beklentisi ~**259,75**. Bunlar bir gündeki korelasyonlu grup olaylarıdır; istatistiksel anlamlılık veya gelecek tahmini kanıtı değildir.
- Bütün geçmiş veri tekrar araştırılmıştır; bu bir **tarihsel keşifsel geri testtir**, yeni bağımsız öngörü kanıtı değildir.

**Yöntem:** Gruplar ilk çekilişteki sabit 20 sayı içinden, önceki 71 günün 20'liklerinde **aynı tek çekilişte tüm üyelerin bulunması** koşuluyla sayıldı. 2^20 bit maskesi üzerinde tam superset sayımı yapıldı, yalnız komşu çekilişlerde toplam görünümler "birlikte" kabul edilmedi.

## V67 tamamlandı — 72. günün tüm 217 çekilişinde eksiksiz birliktelik geçmişi

**Çalışma:** [V67 kodu](v67_217_cekilis_tum_birliktelik.py) · [V67 GitHub Actions sonucu ve tek ZIP](../../actions/workflows/v67-tum217-birliktelik.yml)

- Gün: **12 Ekim 2026**; çekiliş **#61629 00:02** ile **#61845 23:57** arasında, tam **217/217**.
- Her çekilişin kendi 20 sayısı için **190 ikili ve 2–10'lu toplam 616.645 farklı grubun** *daha önceki aynı çekilişte birlikte görünme* tam sayımı yapıldı. 217×616.645 = **133.811.965 grup kaydı**.
- Her (t) çekilişinde geçmiş havuzu **15.407 önceki tam gün çekilişi + o gün tamamlanmış (t−1) çekiliş**. **Hedef çekiliş ve sonraki çekilişler geçmişe dahil değildir**.
- **Tam veri saklama:** Tek ZIP'in `all_groups/` klasöründe 217 adet `slot_001..217_uint16le.bin` frekans vektörü, sabit `subset_masks_k2_to_k10_uint32le.bin` maskeleriyle bire bir eşlenir; her vektör 616.645 gruba karşılık gelir. Bilgi kaybı olmaması için tam dizi ikilik sıkıştırılmıştır; telefonda 133 milyon satır CSV açmak gerekmez.
- **Okunabilir CSV:** `00_217_CEKILIS_ANA_TABLO.csv` (her çekilişin ilk 20 sayısı ve özetleri), `01_217x9_GRUP_BOYUTLARI_MIN_ORT_MAX_SIFIR.csv` (her çekiliş/boyut), `02_TUM_217_CEKILIS_190_IKILI_SAYIMI.csv` (41.230 ikili), `03_HER_CEKILIS_EN_AZ_EN_COK_10_AILE_K2_K10.csv` (her büyüklük için 10 en az ve 10 en çok aile), `04_SONRAKI_CEKILISTE_ILK20_KAC_SAYI_TEKRAR.csv`, `05_EN_AZ_VE_EN_COK_SONRAKI_CEKILIS_TOPLU.csv`.
- Çekiliş #61629 için **190 ikilinin geçmiş ortalama birlikte görünümü 919,9789**. Son çekiliş #61845'e gelindiğinde geçmiş örnek sayısı **15.623**.
- Her çekilişteki 20 sayı ile **hemen bir sonraki çekilişin** ortalama ortak sayısı **4,99074**, adil beklenti **5**.
- Geçmişte en az görülen **10 ikili**, 216 sonraki çekilişte toplam **134** defa birlikte tamamlandı; en çok görülen 10 ikili **113** defa. Her kolun adil beklentisi **129,873**. Üçlülerde aynı karşılaştırma **28'e 39** (beklenti **29,971**). Sonraki 216 çekilişte seçilen 7–10'lu 10'ar aileler için tam tamamlama yok. Bu gruplar aşırı örtüşebilir, tek günde araştırılmıştır; büyüklük farkını test düzeltmesi yapmadan oyun avantajı saymak yanlış.
- Tarihsel 72 gün önceden birçok kez araştırıldığından bu da **keşifsel geri testtir**; rastgele kontrolden bağımsız veya prospektif bir tahmin kanıtı değildir.

## V68 — Sıcaklık / yön + 15'lik çekirdek + geçmiş 20'lik örtüşme ile 20'lik aday havuz

**Gerçek çalıştırma:** [V68 kodu](v68_sicaklik_ortusme_havuz_kor_test.py) · [Actions çalıştırması](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38757314417) · [tek ZIP (245818 bayt, 90 gün)](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38757314417/artifacts/11984126536)

- Kullanıcının teorisi: geçmiş çekilişlerde 20/20 ve 15/20 ortaklık olmayışı, gelecekte sıcak/ılık/soğuğun yönüne göre seçilen **15–20 aday sayı havuzunun kurulmasına katkı sağlayabilir mi?** Bir adayın geçmişte 15/20 örtüşmeye sahip olmaması, adil 20/80 mekanizmasında çok yaygın ve **tek başına seçim avantajı değildir**.
- 12 Ekim 2026, **#61629–#61845** hedeflerinin **217/217** tamamında, önceki 71 tam gün 15.407 çekiliş + o günün hedef öncesi çekilişlerinden sıcaklık, yön, tarihsel 20'lik örtüşme hesaplandı. **Hedefin gerçek 20 sayısı seçimden önce kullanılmadı.**
- Sıcaklık: son 72 geçmiş çekiliş sayımına dayalı V42 benzeri beş havuz; **yön skoru** son 24 çekiliş eksi önceki 24 çekiliş sayımı; kombinasyon puanı `f72 + 0,6*(f24son-f24önce)`. Sabit ilk 10 en sıcak/yönlü sayı + sonraki üst sıradaki adaylardan beş sayı ile **14 adet alternatif 15'lik çekirdek**; geçmiş 20'liklerle her geçmiş çekiliş için **tam ortak sayı** sayımı. 15'liklerin örtüşme puanı 8+/9+/10+; 20'liğe tamamlarken 9 aday beşli, 10+/11+/12+ tarihsel ortaklık puanına göre düşük veya yüksek grup seçimi. **Temel sıcaklık, sıcaklık+yön ve rastgele** kontroller aynı hedeflerde.
- **217 hedef çekilişinde 20 sayılık havuz başına ortalama isabet** (adil beklenti 5): `FREQ20=4,78802`; `HEAT_TREND20=4,91705`; `HEAT_LOW20=4,80184`; `HEAT_HIGH20=4,86636`; `LOW15_LOW20=4,94009`; `LOW15_HIGH20=4,89862`; `HIGH15_LOW20=4,91705`; `HIGH15_HIGH20=5,00461`; `RANDOM20=4,91705`. En yüksek tek havuz isabetleri 9–11, hiçbirinde 20/20 yok.
- **10'lu tek kupon/çekiliş** (adil beklenti 2,5): `FREQ20=2,36406`; `HEAT_TREND20=2,61290`; `HEAT_LOW20=2,49770`; `HEAT_HIGH20=2,56221`; `LOW15_LOW20=2,53456`; `LOW15_HIGH20=2,49309`; `HIGH15_LOW20=2,43779`; `HIGH15_HIGH20=2,52535`; `RANDOM20=2,39170`. En yüksek tek kupon 6–7/10; hiçbirinde 10/10 yok.
- **15'lik çekirdek ortalamaları** (adil beklenti 3,75): `HEAT15=3,49770`; `LOW15=3,59908`; `HIGH15=3,67281`. **V68 verisi istatistiksel üstünlük göstermiyor**; küçük dalgalanmalar ve çoklu aday denemeleri bir kazanma kuralı değildir.
- Tek ZIP: `00_ANA_SONUC_V68.txt`, bütün 15/20 ve 5/6/8/10 sonuç CSV'leri, 217×80 sıcaklık/yön/sayı geçmişi CSV, eşleştirmeli sonuç karşılaştırması, çekiliş bazında tüm dondurulmuş havuzlar ve denetim verileri. Test, daha önce defalarca araştırılmış 12 Ekim üzerinde **keşifsel kronolojik geri test**; gerçek geleceğe yönelik bağımsız doğrulama **yok**.

## V69 — RNG sıcaklık/yön ve saat içinde 4–5–6–7 kez çıkacak sayıları önceden belirleme

**Tamamlanan GitHub Actions testi:** [V69 kaynak kodu](v69_rng_isi_yon_saat_4_5_6_7.py) · [başarılı çalıştırma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38762096264) · [tek ZIP (29.065 bayt)](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38762096264/artifacts/11985428805)

- **Veri:** 71 tam gün ×217 = 15.407 geçmiş çekilişten sonra **12 Ekim 2026, 217 çekiliş** (#61629–#61845), her hedef öncesinde yalnız geçmiş biliniyor. Saat hesabı **18 tam saat ×12 çekiliş** üzerinden; 01:02'daki tek çekiliş saat sayılmıyor.
- **%25 hipotezi:** Her çekilişten önce son 72 çekilişteki V42 sıcak/ılık/soğuk sınıfları ve son 24 − önceki 24 yön hesaplandı. Gerçek sonraki-çekiliş çıkış oranları: **soğuk %24,790; serin %24,356; nötr %25,304; ılık %26,340; sıcak %23,999**. **1.000 adil tam-gün RNG simülasyonu** ile hiçbirinde istatistiksel olarak güvenilir %25 sapması görülmedi (ılık p≈0,075; diğerleri daha yüksek).
- **Saatlik rastgele beklenti:** Her bir sayının 12 çekilişte tam 4 kez çıkma olasılığı %19,3578 (80 sayı içinde ortalama 15,486); tam 5 = %10,3241 (8,259); tam 6 = %4,0149 (3,212); tam 7 = %1,1471 (0,918). Günün 18 saatindeki gerçek adetler: 4 kez **285**, 5 kez **163**, 6 kez **45**, 7 kez **14** sayı-saat.
- **Saat öncesi kimlik seçimi:** Her saat hedef tam 4/5/6/7 çıkış için sırasıyla **15/8/3/1 sayı** donduruldu. 18 saat ×27 aday = **486 sayı-adet tahmini/yöntem**. Toplam doğru eşleşmeler: `HOT72=60`, `HEAT_TREND=65`, `COLD72=63`, `RANDOM=70`. Rastgele simülasyonun aynı yöntemlerde beklediği doğru sayısı ≈69,5–69,8; **16 sınama için maksimum istatistiğe dayalı düzeltmeli p=0,73826**, üstünlük kanıtı yok.
- **Saatin ilk 6 çekilişi görüldükten sonra 12 çekilişlik toplamı tahmin:** `H6_MATH=167`, `H6_MATH_HEAT=168` doğru sayı-adet eşleşmesi. Rastgele sistemde bile H6 bilgisiyle ortalama ~154,6/~154,4 başarılı tahmin yapılabiliyor; tek yönlü simülasyon p≈0,083, sıcaklık katkısı 1 isabet, kanıtlanmış fark değil. **Bu saat öncesi tahmin değildir:** H1–H6 zaten gözlendi, yalnız H7–H12 belirsiz.
- **13 CSV/TXT/JSON çıktı** tek ZIP'te; 217 çekilişte beş havuz ve yön, 18 saat bazında 0–12 tam sayım, saat başından ve H6 sonrasından aday sayı listeleri / gerçek isabetler, RNG simülasyonla denetim. Bugüne dek incelenmiş 12 Ekim geçmişi nedeniyle **keşifsel geri test**; bağımsız geleceğe dönük başarı iddiası yapılmaz.

## V70 — 12 Ekim ilk çekilişin 20 sayısı, geçmişte 12–24–36–42–56–72–...–15.407 pencere

**Başarılı gerçek veri denetimi:** [V70 kod](v70_ilk20_coklu_sicaklik_pencere.py) · [Actions çalıştırma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38764633947) · [V70 tek ZIP](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38764633947/artifacts/11987126977)

- **Sabit hedef:** #61629, 12.10.2026 00:02; `5,6,11,22,23,30,31,32,35,39,41,43,47,54,55,57,59,62,74,75`. Hedef çekilişten **önceki 71 tam gün** 15.407 çekiliş, hedef bilgisi yalnız testte.
- Her geçmiş pencere N'de **80 sayı ayrı ayrı geçmiş frekansına göre sıralandı** ve 16'şar sayılık 5 eşit grup (en soğuk→en sıcak) oluşturuldu. Hedefte gruplardan **beklenen sayı 4'er**. 12,24,36,42,56,72 gibi özel uzunluklar ve tüm geçmiş boyunca çoğunlukla 12'şer adımlı **toplam 1.291 pencere** incelendi. Eşit frekanslı sayılar numara sırasıyla ayrıldı, kesim yerlerindeki eşitlik sayısı her satırda yazıldı. Ek olarak matematiksel z-skorlu, değişken büyüklüklü sıcaklık sınıfları raporlandı.
- **Örnek hedef dağılımı** (soğuk/serin/nötr/ılık/sıcak): `N12=5/3/5/4/3`; `N24=3/6/5/4/2`; `N36=5/6/3/5/1`; `N42=5/4/6/3/2`; `N56=4/6/5/3/2`; `N72=2/7/6/4/1`; `N217=3/4/6/7/0`; `N432=7/4/2/5/2`; `N1008=3/4/7/2/4`; `N15407=4/4/4/4/4`.
- **217'lik pencerede sıcak 16 sayıdan hiçbirinin çıkmaması** tek önceden belirlenmiş sınıflamada adil RNG'de p=`0.0055496`. **Tüm 15.407 geçmişte hedef20'nin beş gruba tam 4'er dağılması** tek sınıflamada p=`0.0056484`. Bunları binlerce pencereden sonradan seçmek ise yanıltıcı olabilir.
- **4.000 aynı-hedef ortak Monte Carlo örneğiyle 1.291 pencerelik tarama düzeltmesi:** herhangi bir pencerede sıfır sıcak sayı görülme ihtimali `p=0.27568`; herhangi bir pencerede 4/4/4/4/4 dağılım görülme ihtimali `p=0.78605`; tüm pencerelerde en yüksek mutlak frekans-z sapması gerçek `|z|=2.2802` (`N408`), düzeltilmiş `p=0.29168`. **Rastgelelikten anlamlı sapma gösterilemedi; sayıların sıcaklık kimliği pencere uzunluğuna göre değişir.** Özellikle kısa pencereler frekans eşitliği nedeniyle keyfi numara bağ çözümünden etkilenir.
- ZIP içeriği: kısa TXT; istenen pencere CSV'si; 1.291 pencere tam CSV; hedef 20 sayının her penceredeki sayı/sıcaklık kimliği CSV; ekstrem pencereler ve sıfır sıcak / tam denge satırları; metodoloji ve audit JSON. Bunun kendisi **gelecekte kupon seçme avantajını kanıtlamaz**; tek geçmiş hedefe bakılmaktadır.

## V71 — 12 Ekim'in 217 hedefi, 1.291 geçmiş sıcaklık penceresi, 10/15/20 kupon ve körlük disiplini

**Başarılı rapor:** [V71 kod](v71_217_cekilis_tum_isi_pencere_test.py) · [GitHub Actions](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38765553971) · [Tek ZIP rapor](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38765553971/artifacts/11990155120)

- **İnceleme:** #61629–#61845, 12.10.2026 **217 çekiliş**. Her hedef öncesi geçmiş: 71 tam gün ×217 = 15.407 çekiliş, gün içinde önceki çekilişler aşamalı ekleniyor. Hedef gerçek 20 sayısı seçime sızmıyor.
- **Pencereler:** Son 12,24,36,42,56,72,...,217,...,15.407 çekiliş; 12 adımlı yaklaşık **1.291 farklı geçmiş uzunluğu**. Her pencerede 80 sayı o aralıktaki görünme sıklığına göre sıralanıyor, eşitliklerde küçük numara önce. Sayı sıcaklığının değişen pencereler arasında eşdeğer olmadığı ayrıca raporlanıyor.
- **Kandidatlar:** COLD/MIDDLE/HOT havuzlarından her hedefe 10/15/20 sayı sabitleniyor. **1.291×3×3 = 11.619 yöntem** ile 217 adımlı retrospektif kronolojik tekrar. Tek sabit rastgele kontrol da mevcut.
- **Tüm pencerelerde geçmişe bakınca en yüksek ortalama:** `10'lu, 1.812 MIDDLE = 2,78802/10` (adil 2,50), `15'li, 1.812 MIDDLE = 4,07373/15` (adil 3,75), `20'li, 2.184 MIDDLE = 5,32258/20` (adil 5,00). Ham tek yönlü p değerleri sırasıyla ≈0,000609 / 0,000991 / 0,002681. **11.619 seçenek üzerinden Bonferroni ile düzeltilmiş p=1** (hiçbiri üstünlük kanıtı değil).
- **Tek rastgele kontrol:** 10'lu 2,56682, 15'li 3,84793, 20'li 5,08295 ortalama. **Tam 217×1291 beşli sıcaklık dağılımı** ve her hedefteki gerçek kupon-isabet listeleri ZIP'te.
- **20'lik ana pencereler (sıcak / orta / soğuk):** 12 → 4,83/5,24/5,00; 24 →4,86/4,99/5,01; 36 →4,90/5,06/4,92; 42 →5,04/5,00/4,99; 56 →4,98/5,08/4,85; 72 →4,88/5,09/4,82; 217 →5,02/5,08/5,01. Hepsi 217 çekiliş ortalama isabeti. **Pencere seçilerek sonuçlar geriye dönük şişirilebilir.**
- **İstatistik:** Her sabit 10/15/20 havuzunun 20/80 hedefte isabet sayısı tam hipergeometrik dağılımlı. 217 çekiliş toplamının olasılıkları 217 kat konvolüsyon ile hesaplandı ve 11.619 hipoteze konservatif aile düzeyi çoklu test düzeltmesi uygulandı. Tek gün daha önce çok incelendiği için **bağımsız ileriye dönük doğrulama yoktur**.
- ZIP: ana kısa karar TXT; 11.619 yöntem tam sonuç CSV; 26 seçili pencere test özeti; 217×26×9 önceden dondurulmuş sayı seçimleri ve gerçekleşen isabetler; 26 pencerenin beşli dağılımı ve hedef bazlı sayım; rastgele kontrol; metodoloji; JSON denetim.

## V72 — Gerçek dengeli 20'lik havuz: beş sıcaklık grubundan dörder sayı, sayı kimliği ve havuz geçiş yönü

**Tamamlanan test ve indirme:** [V72 kaynak](v72_dengeli_5_havuz_isi_yon_ref_secimi.py) · [GitHub Actions başarılı](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38767245577) · [V72 tek ZIP](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38767245577/artifacts/11989647018)

**Önemli kullanıcı düzeltmesi:** V71'de her seferinde yalnız sıcak / yalnız soğuk / yalnız orta havuzdan 10, 15 veya 20 sayı seçilmesi kullanıcının istediği şey DEĞİLDİ. Kullanıcı **80 sayıyı sıcaklığa göre beş gruba ayırıp, her birinden 4 sayı olacak şekilde 20 sayılık birleşik bir hedef aday havuzu** istiyor. Dörder sayının seçiminde her sayının **geçmiş havuz yeri, hangi yöne kaç basamak geçtiği, son dönem çıkış hareketi ve numarası** hesaba katılmalı. Asıl sorusu **bu 5×4 kimlik/yön motorunda sıcaklık sınıfı için sabit kaç geçmiş çekiliş kullanılırsa daha iyi olur?**

- **Gerçek motor:** Son `N` çekilişte her sayının frekansı ile 80 sayı sıralanır → sıcaklığa göre `5×16` eşit kimlik havuzu (soğuk/serin/nötr/ılık/sıcak); aynı sınıflama **12 çekiliş öncesi** tekrar hesaplanıp her sayının `havuz_geçişi ∈[-4,4]` ölçülür. Son 12 ile önceki 12 arasındaki çıkış farkı da ikinci yön özelliği olur. Her hedef öncesinde sıcaklık ve yön **dondurularak** her sınıftan tam dört sayı seçilir. 6 seçim politikası: RISING, COOLING, STEADY, FREQ, MIXED (2 yükselen +1 sabit +1 soğuyan, gerekiyorsa tamamlama), RANDOM (beş havuzda yine 4'er rastgele).
- **Sabit N seçenekleri:** `12,24,36,42,56,72,96,120,144,217,288,432`. Toplam 12×6=72 birleşik yöntem.
- **Seçim disiplininin testi:** 12 Ekim'den önceki **10 tam gün, 2.170 çekiliş** üzerinde N ve yöntem seçildi (`ortalama isabet −0,25×günlük isabet ortalamalarının SD`); **12 Ekim 217 hedef çekilişi** dondurulmuş seçimle test edildi. Eski araştırmalarda bu gün de incelendiği için **bağımsız geleceğe dönük tahmin kanıtı değil**.
- **Eğitimde birinci:** `N=432, STEADY`; eğitim ortalaması **5,08203/20**; 12 Ekim gerçek test ortalaması **4,97235/20**; matematiksel 5,000/20; tam hipergeometrik tek taraflı **p≈0,603**; gerçek gün için ayrı rastgele 20 sayı kontrolü **5,11521/20**. Bu modelin avantajı doğrulanmadı.
- **Her N'nin önceki 10 güne göre seçilen yönteminin 12 Ekim ortalaması:** N12=4,8894; N24=4,9954; N36=4,9124; N42=5,0507; N56=5,0507; N72=5,0829; N96=4,8664; N120=4,8295; N144=4,9677; N217=5,0276; N288=5,1014; N432=4,9724.
- **N=72, 5×4 birleşik aday havuzu, her seçim politikasının 12 Ekim ortalaması:** STEADY **5,08295**; FREQ **4,94931**; RANDOM **5,18433**; MIXED **4,97696**; RISING **4,97235**; COOLING **5,15207**. Rastgele 4'er seçmek bile birçok kuralı geçti; **hangi N/yön daha verimli belirlendi denemez**.
- **Eğitim birincisi 20'lik havuzdan 10'lu kupon:** HEAT_FIRST **2,48387/10**, DIRECTION_FIRST **2,52995/10**; beklenti 2,5; 10/10 hiç yok.
- Tek ZIP: kısa karar; 72 yöntemin 10 günlük eğitim / 217 hedef testi; N bazında eğitim birincileri; **217×12×6 = 15.624 birleşik 20'lik havuz + gerçek isabet**; **217×12×80 = 208.320 sayı-havuz/yön/kimlik kaydı**; gerçekleşen hedeflerin beşli dağılımı; 5/6/8/10 alt kupon raporu; metodoloji ve kontrol JSON.
- **Pratik referans:** N=72 **yalnızca makul sabit başlangıç penceresi** olarak kullanılabilir, yön için 12 çekilişlik havuz yer değiştirme ve 12/24 kısa frekans farkı. Ancak herhangi bir N için **rastgeleliğin üzerinde kanıtlanmış tahmin avantajı yok**; yeni, hiç incelenmemiş günlerde önceden kilitlenmiş tek kural test edilmeden “en iyi pencere” ilan edilmez.

## V73 — Beş eşit sıcaklık havuzundan 4'er sayı ile 20'lik: sabit referans seçiminde 45 günlük öğrenme/doğrulama/test

**Başarılı rapor:** [V73 kod](v73_5_havuz_referans_yon_cok_gun_kor_test.py) · [GitHub Actions](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38768727437) · [V73 tek ZIP, 1,38 MB](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38768727437/artifacts/11990138770)

- **Kullanıcının gerçek hedefi:** Hangi sabit **geçmiş çekiliş sayısı N**, beş eşit sıcaklık sınıfına (`5×16`) bölünen 80 sayının her sınıfından **4 kimlik/yön seçilerek kurulan dengeli 20'lik havuzu** en verimli hale getiriyor? Sadece tüm sıcaklardan veya tüm soğuklardan tek havuz seçimiyse kullanıcı amacını karşılamaz.
- **Veri ve üç evre:** 72 tam gün (1 Ağustos–12 Ekim 2026). İlk 27 gün `warmup`. **29 Ağustos–12 Eylül (15 gün=3.255 çekiliş)**: her N için yön seçimi `TRAIN`. **13–27 Eylül (15 gün=3.255)**: train'de sabitlenen yönlerden bir N referansı seçimi `VALIDATE`. **28 Eylül–12 Ekim (15 gün=3.255)**: tek N ve tek yön **değişmeden HOLDOUT**. Bu günler daha önce çok araştırıldığından geçmişe dönük/kronolojik holdout, tam bağımsız gelecekte test değil.
- **21 sabit N:** `12,24,36,42,56,72,96,120,144,168,217,288,432,576,720,864,1008,1440,2160,3024,4340` çekiliş. Havuzlardaki 80 sayı kimliği son N frekansı ile 16'şar sıralanır. Her hedefte 12 çekiliş öncesindeki aynı-N havuz yeriyle farkı ve son12–önceki12 çıkış yönü hesaplanır. Her havuzdan tam 4 sayı seçilir. `RISING, COOLING, STEADY, FREQ, MIXED, RANDOM` yöntemleri karşılaştırılır. `MIXED`: havuz içinde 2 yükselen, 1 sabit, 1 soğuyan (gerektiğinde yön puanı ile tamamlama).
- **Eğitimde her N için kendi yön kuralı seçildi.** Doğrulamada `ortalama − 0,25×günlük ortalama SD` ölçütüne göre referans **N=12, MIXED** seçildi. Önceden dondurulmuş yöntemin sonuçları: TRAIN `5,05776/20`, VALIDATE `5,06790/20`, HOLDOUT `4,94562/20`, adil RNG beklenen `5,00000/20`. HOLDOUT'ta aynı beş havuzdan rastgele dörder `5,03932/20`. **Seçili yöntem −0,09370 sayı/çekiliş geride**; çiftli karşılaştırma z≈−2,238, yönlü p≈0,9874 (üstünlük yönü); adil RNG üst-kuyruk p≈0,9674.
- **Son 15 günde diğer N/yön kombinasyonlarını yalnız karşılaştırmalı olarak raporladık, bunlardan yeniden kazanan seçilmedi.** Bazı örnekler: N24 COOLING `5,00614`; N42 RISING `4,98648`; N56 RISING `4,98648`; N72 MIXED `4,95422`; N96 COOLING `5,01321`; N217 MIXED `4,98710`; N288 RISING `4,98341`; N432 RISING `5,00369`; N576 COOLING `5,00584`; N720 COOLING `5,02089` (bu sonuçlara göre tekrar N seçmek overfitting olur).
- **Son testte kilitli N=12 MIXED 20'lik havuzu:** 3.255 hedefte **7+ isabet: 578; 8+: 219; 9+: 69; 10+: 11**. Matematiksel rastgele kontrol 20/80 seviyesinin üzerinde doğrulanmış kupon avantajı göstermedi.
- **Raporun tek ZIP içeriği:** 21N×6kural tüm üç dönem sonuçları, eğitimden seçili N başına yön kuralı, 3.255 hedef için seçilen tam 20'lik ve her havuzun 4 numarası, **3.255×80=260.400 sayının eski/yeni sıcaklık havuzu, sıralama yönü, son12/önceki12 frekansı, seçildi/çıktı bilgisi**, 15 günlük hedef-bazlı isabet ve rastgele karşılaştırma, beş havuz hedef kotaları, havuz+yön bazlı isabet, metodoloji, audit JSON.
- **Kesin çıkarım:** Sıcaklık yerine göre yükselme/soğuma gibi geçmiş karakterler kaydedilebilir ancak hangi `N` geçmiş penceresinin **rastgele 5/20 üzeri tahmin avantajı** verdiği henüz gösterilemedi. Sonuç iyi çıktı diye N değiştirmeyin. Gerçekten yeni gelecek çekilişlerde önceden dondurulan tek seçimi sınamak gerekir.

## V74 — 5x5 eski→yeni sıcaklık kimlik matrisi + 5x3 hareket sınıfı, 20'likte eşit 5x4 seçimin doğrulama testi

**Başarılı GitHub Actions:** [V74 kaynak](v74_5x5_kimlik_yon_gecis_kalibrasyon.py) · [çalışma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38769792751) · [tek ZIP V74](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38769792751/artifacts/11990219849)

- **Çıkış noktası:** V73'te sıcaklık/yön için N referans aralığını öğrenme+doğrulama ile seçmek HOLDOUT'ta avantaj göstermedi. Bu kez 80 sayının `eski havuz → yeni havuz` kimlik hareketlerini **TRAIN döneminde gerçek hit oranlarıyla** 5×5 (25 kategori) ve 5×3 (15 kategori) olarak ayrıca öğrendik.
- **Veri:** 72 tam gün, ilk 27 gün warmup; **29 Ağustos–12 Eylül 3.255 çekiliş eğitim**, **13–27 Eylül 3.255 validasyon**, **28 Eylül–12 Ekim 3.255 holdout**. Önceki hedefler geleceğe sızmadan, her sayının son N frekansına göre 5×16 havuzu belirleniyor. Her sayının `L=6/12/24` çekiliş önceki havuz konumu bulunuyor. 12 sabit N (`12,24,42,56,72,96,144,217,288,432,720,1008`), iki durum türü (`TRANS25` ve `DIRECTION15`) ve iki %25 öncüllü yumuşatma gücü (`250/2500`) birlikte **144 aday kural**.
- **Her 20'lik:** Mevcut 5 havuzun her birinden **tam 4 sayının kimliğini**, eğitim verisinden öğrenilen ilgili hareket grubunun gelecekte çıkma oranına göre seç. Eşit puanlarda önceden tohumlanan rastgele öncelik. Karşılaştırma: 5 havuzdan yine **4'er rasgele sayı** seçen denetim.
- **Validasyonun kilitlediği V74 model:** `N=42` geçmiş çekiliş, `LAG=12` hareket aralığı, `DIRECTION15` (5 mevcut sınıf×yükseliyor/sabit/soğuyor), `SHRINK=250`. Yani 5×5 matrisi raporladıysak da **seçilen kural 5×3**.
- **VALIDATE:** model **5,08848/20**, aynı kotalı rastgele **5,01598/20**. **HOLDOUT (3.255 hedef)** model **5,05653/20**, aynı kotalı rastgele **4,97358/20**. Fark **+0,08295** doğru sayı/çekiliş; model-vs-denetim eşleştirilmiş z≈2,221, **tek yönlü p≈0,01318**. Adil RNG 5/20 ortalamasıyla kıyaslamada tek yönlü **p≈0,02834**. Brier skorunda fark çok küçük (`+0,000000315` iyi yön), logloss da çok küçük (`+0,000000825`).
- **Bulguyu abartma:** Bu tarihler V68–V73'te zaten araştırıldı; çok sayıda motor denemesi ve tarih seçimi yapıldı. **Bu p değerleri yeni, gerçek ileriye dönük loto üstünlüğünü kanıtlamaz.** Sonuç yalnızca yeni tarihli sabit parametreli doğrulama yapmaya değecek bir hipotez sunar.
- **ZIP:** 144 yöntem validasyon puanı, 3.255 hedefin dörder seçilen gerçek 20'liği ve isabeti, 3.255×80 sayının eski ve yeni havuzu + yer/yön, 5×5 TRAIN/VALIDATE/HOLDOUT geçiş hit oranları, 5×3 sıcaklık/yön hit oranları, 15 günün günlük sonuçları, diğer pencerelerin yalnız açıklayıcı HOLDOUT değerleri, yöntem ve JSON.

## V75 — V74'ün 42/12 hareket kuralı hiç değiştirilmeden 13 Ekim ilk kesintisiz çekilişlerinde

**Başarılı GitHub Actions:** [V75 kaynak](v75_13ekim_sabit_42_12_gecis_kor_test.py) · [çalışma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38770234509) · [tek ZIP V75](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38770234509/artifacts/11990572837)

- **Frozen V74:** `N42/LAG12/DIRECTION15/SHRINK250`, eğitim fit oranları yalnız **29 Ağustos–12 Eylül**; 13 Ekim sonucuna bakarak parametre değiştirilmedi. Dörder sayılık beş havuz, aynı V74 seed'inin devamı olan tie-break dizisi ve aynı kontrol kuralı.
- **13 Ekim veri kalitesi:** `veri.txt` içinde `13.10.2026` tarihli **151** çekiliş kaydı var (`#61846..#61998`), **#61958 ve #61972** kayıtları eksik. Gerçekte ardışık son N ve N+12 penceresi bozulmasın diye yalnız ilk kesintisiz **112** çekiliş (`#61846 00:02..#61957 15:12`) kullanıldı. Eksik çekilişleri tahmin ederek doldurmadık, kalan 39 kayıt atlandı.
- **13 Ekim 112 hedef sonucu:** 20'lik model **582 toplam =5,19643/20**; aynı havuzlardan rastgele **534 toplam=4,76786/20**; fark **+0,42857**; eşleştirilmiş z≈2,146, tek yönlü p≈0,01592. Ama modelin sabit adil RNG beklentisi **5/20** üzerinde olmasının tek yönlü yaklaşık **p≈0,11434**, yani bağımsız RNG'ye karşı bu 112 çekilişte anlamlı üstünlük kanıtı yok. Model 7+ isabet 25, 8+ 13, 9+ 3, 10+ 0. Brier küçük farkla daha iyi `0,187491831 vs 0,1875`.
- **Sınırlama:** 13 Ekim zaten veri dosyasında vardı; model seçimi için kullanılmamış olsa da gerçek zamanlı ileriye dönük deney değil. Yalnız küçük, eksiksiz 112 çekiliş. Kuralı değiştirmeden yeni, tam çekilişler üzerinde tekrar etmek gerek.
- ZIP: 112 hedefin 5×4 tam 20 aday kimlik listeleri ve isabet, 112×80 eski-yeni havuz/yer/yön/tahmini olasılık satırı, 5×3 çıkış oranları, **değiştirilmemiş eğitim olasılıkları**, metodoloji ve denetim JSON.

## V76 — Kullanıcı önerisi: sıcaklık geçmiş referansı 42 yerine 60 çekiliş olursa ne olur?

**Başarılı GitHub Actions:** [V76 kaynak](v76_42_60_ref_sabit_yon_5x4_kor_test.py) · [çalışma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38771328284) · [tek ZIP](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38771328284/artifacts/11991416803)

- **60 geçmiş çekilişin her sayı için beklentisi =15 çıkış.** 80 sayı sıralanarak 5 eşit 16-ball sıcaklık havuzuna ayrılıyor, her havuzdan tam dört sayının kimliği seçilerek **tek 20'lik** oluşturuluyor. Yalnızca **N=42 → N=60** değiştirilerek önceden belirlenmiş V74 kuralı korunuyor: `LAG=12`, `DIRECTION15` (beş ısı havuzu×üç yer/yön), `SHRINK=250` ve her hedef öncesi aynı seçme/bağlayıcı rastgele puan algoritması.
- **Önceki veride oranlar ayrıca eğitildi:** 29 Ağustos–12 Eylül **3.255** çekiliş; 13–27 Eylül doğrulama **3.255**; 28 Eylül–12 Ekim test **3.255**; 13 Ekim'in ilk kesintisiz **112** çekilişinde tekrar. 13 Ekim'de 151 mevcut kayıttan #61958 ve #61972 eksik, geçmiş bozulmasın diye ilk kesintisiz 112 hedeften sonrası kullanılmadı.
- **Tam karşılaştırma, N42 ortalama vs N60 ortalama:** TRAIN `5,06390 vs 5,06114`; VALIDATE `5,08848 vs 5,02304`; HOLDOUT `5,05653 vs 5,00799`; 13 Ekim ilk 112 `5,19643 vs 5,15179`. Adil RNG beklentisi `5,00000/20`. HOLDOUT 60−42 `−0,04854` ve çift taraflı eşleştirilmiş `p≈0,20644`; 13 Ekim `−0,04464`, `p≈0,82599`. **Aralarında güvenilir fark bulunamadı.**
- **5x4 rastgele kontrol ortalaması:** TRAIN N42 `5,06574`, N60 `5,05161`; VALIDATE `5,01598`, `5,03195`; HOLDOUT `4,97358`, `4,99109`; 13 Ekim `4,76786`, `4,88393`. 13 Ekim N60 sonuçları `7+=17`, `8+=9`, `9+=2`, `10+=1` hedef çekiliş (**20 sayılık havuz isabetleri**, 10'lu kuponun 10/10 kazanımı değil). 13 Ekim N60 adil RNG'ye karşı tek yönlü approx `p≈0,17778` — üstünlük kanıtı değil.
- **Dosya:** V76 ZIP 42/60 tüm öğrenme/doğrulama/test özetleri, günlük isabetler, 13 Ekim her çekilişte 42 ve 60 için beş havuzun gerçek dört sayı kimlikleri ve isabetleri, tüm 80 sayının eski/yeni havuz hareketi, 5×3 öğrenilmiş oranları, denetim bilgisi.
- **Bilimsel karar:** 60 çekiliş matematiksel olarak çalışır ama testte 42'nin önüne geçmedi. 42'nin gerçek, uzun vadeli RNG tahmin üstünlüğü de kanıtlanmadı. Özellikle önceki birçok analizde aynı tarihler incelenmiştir, ileriye dönük henüz görülmemiş çekilişler gereklidir.

## V77 — 72 tam gün, 80 sayı, beş 16'lık sıcaklık havuzu ve gerçek hedef 1/0 kayıt sistemi

**Başarılı GitHub Actions:** [V77 kaynak](v77_72gun_80sayi_bes_havuz_giris_cikis_hedef01.py) · [GitHub Actions çalışması](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38773961273) · [Tek ZIP (12,2 MB)](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38773961273/artifacts/11993230666)

- **Kullanıcının fikri:** 72 günlük çekiliş akışında **80 sayı**, eşit **16+16+16+16+16 sıcaklık grubu** olacak. Her sayı için `numara / bulunduğu 16'lık grup / 1–80 sırası / 16'lı gruba son adımda giriş/çıkış / 12 adım eski grup / yukarı-sabit-aşağı yön` kaydedilecek; hedef çekilişte çıkan 20 sayıya `1`, diğer 60 sayıya `0` yazılacak. Bu ikili hedef etiketi yalnız **sonuçtur**, hedefe ilişkin veri tahmin özelliklerine sızmaz.
- **Veri:** 1 Ağustos–12 Ekim arasında **72 TAM günlük 15.624 çekiliş**, tüm hedefler için **15.624×80=1.249.920 adet 1/0**. 23 Ağustos (2 invalid/missing sayı satırı) ve 13 Ekim (kısmi gün) 72 tam güne dâhil değil. Tam günler arasındaki atlama `22 Ağustos #50778→24 Ağustos #50996`, **217 eksik numaralı çekiliş**. Sıcaklık + yön analizleri ve istatistikler için gerekli N+12 geçmişini bu boşluktan geçirmeyen bir `gecmis_kesintisiz_1_0` kalite bayrağı tutulur.
- **Ana referans:** Kullanıcının son önerisi olan `N=60 önceki çekiliş`. Her sayı için 60 çekilişte **ortalama 15** çıkış beklenir. Her hedef öncesi son 60 çekilişte 80 sayı çıkış frekansına göre sıralanır → tam **5×16 kimlik havuzu** (soğuk-serin-nötr-ılık-sıcak). Eşit frekanslar önceki sıralama korunarak çözülür; amaç yapay sınıf salınımını azaltmak. `42,72,217` referans kontrolü de var.
- **Havuz giriş-çıkış tanımı:** Önceki hedefin öncesindeki sınıf ile güncel hedef öncesi sınıfı karşılaştır. 16'lık havuzdan çıkanların numaralarını ve başka havuzlardan yeni girenlerin numaralarını kaydet. Her biri 16 tuttuğundan giren sayısı çıkan sayısına eşittir. Eski sınıf **12 çekiliş önce**, yön = bugünkü havuz − önceki havuz: ısınma/soğuma/sabit. Her satırda hedef `1/0` + önceki hedef `1/0` var.
- **Gerçek hareket sonucu:** N60 için kesintisiz N+12 geçmişi olan **15.480 hedef**; 80 sayı içinde çekiliş başına ortalama **9,72939 farklı havuza geçiş**, tüm uygun hedeflerde **150.611 bireysel havuz girişi**. `N42: 11,48228`, `N72: 8,88011`, `N217: 5,25992` sayı/çekiliş: N uzadıkça göreli havuz etiketi daha yavaş değişiyor.
- **Gerçek hedef 20'nin beş havuza 1/0 dağılımı** (N60, uygun 15.480 hedef): soğuk `3,98908`, serin `4,01370`, nötr `3,98127`, ılık `4,01751`, sıcak `3,99845` (her biri teorik `4/16`). Tam **4+4+4+4+4** gerçek hedef dağılımı **98** kere; adil bağımsız 20/80'dan beklenen **87,44** (≈%0,5648). Havuzların iç 16'lık sınırlarına ±2 sıra yakın hedef `77.371/309.600=%24,99063`; diğer sıra `232.229/928.800=%25,00312`. Keskin belirgin hedef tercih farkı görülmedi.
- **Geçmiş 0/1→yeni hedef 0/1 tablo** (N60 15.480 uygun hedef ×80 sayı): `0→0 696.521`, `0→1 232.279`, `1→0 232.279`, `1→1 77.321`. Önceki çekilişte 1 olanın yeni hedefte tekrar 1 olma oranı ≈%24,975; rastgele beklenti %25.
- **30 durumlu ek model:** `5 güncel havuz ×3 (son12 yön) ×2 (en son havuz değişti mi)`, her durum için önceki **29 Ağustos–12 Eylül (15 gün) gerçek hedef 1/0** ile olasılık öğrenildi; `alpha=250` ve %25 öncülü. Hedef öncesi her havuzdan olasılığı yüksek dört numara seçerek 20'lik oluşturuldu; `13–27 Eylül (15 gün)` doğrulama ve `28 Eylül–12 Ekim (15 gün)` holdout ile aynı havuzdan dörder rastgele kontrol karşılaştırıldı. 42,60,72,217 referansları **başlangıçta sabit**, holdout'tan kural optimizasyonu yok.
- **Son 15 gün HOLDOUT'ta model / eşit havuzlu rastgele 20'lik:** N42 `5,02826 / 5,04547` (avantaj −0,01720); N60 `5,02028 / 5,05253` (−0,03226); N72 `5,01229 / 5,03072` (−0,01843); N217 `4,99447 / 4,99816` (−0,00369). **Geleceğe dönük isabet avantajı doğrulanmadı.** Önceden araştırılmış günler olduğundan tarihsel sonuç ileriye dönük yeni gün doğrulaması yerine geçmez.
- **ZIP 15 dosya:** `01` tüm 15.624 çekilişte 80 sütun gerçek hedef 1/0 (.csv.gz); `02` yaklaşık 1,245 milyon satır, N60 her sayının öncesindeki 16'lık havuzu, giriş/çıkış, yön, sıra, hedef ve eski hedef 1/0 (.csv.gz); `03` her hedefin beş 16'lık gerçek numara listesi, girenlerin/çıkanların adları ve hedefin her havuzdaki gerçek 1'leri (.csv.gz); `04` 72 günlük hareket özeti; `05` eski→yeni havuz 5×5; `06` 5×3×2 havuz+yön+giriş hedef 1/0 tablosu; `07` her 16'lık havuzda pozisyon1–16 hit oranı; `08` eski hedef→yeni hedef 0/1; `09` N42/60/72/217 değişim; `10` 15+15+15 model ve rastgele sonuçları; `11` 30 durumun eğitim oranı; `12` 3.255 kilitli 60 referanslı aday20+isabet; `13` yöntem; `14` denetim JSON; `00` kısa karar. Ana kaynak kodu GitHub'da kalıcıdır, Actions ZIP süreli saklanır.
- **Önemli:** 5×16 havuzda **sayıların yer-yön yolculuğu** ayrıntılı izlenir; hedef `1` ve `0` ile çaprazlanır ama bu, RNG'nin mekanizmasını çözdüğümüz veya kupon başarısı kanıtlandığı anlamına gelmez. Bundan sonraki araştırma için giriş yapan/çıkan sayıların **kimliklerini, aynı 16'lık grup içindeki 1–16 basamaklarını, önceki hedefin 1/0 etiketini** ve hedef outcome ilişkisini uygun testlerde ölç.
 
### Yeni sohbetten devam etme

Yeni sohbette şu tek adresi paylaşmak yeterli:

**https://github.com/gozlekakif-alt/hizli-on-analiz-motoru**

Yeni asistana: **“Bu depodaki README, veri.txt, V58–V77 programları; V74/V75 42/12 havuz yönü, V76 42/60 referans karşılaştırması ve **V77 72 günlük 80 sayı ×5×16 havuz giriş/çıkış/konum/yön + hedef 1/0 tam kayıt ve test sistemi** sonuçlarını Actions ZIP dosyalarında bul. Günler arası kademeli geçişler RNG'den istatistiksel ayrışmadı; yalnız yeni, henüz incelenmemiş tam günlerle önceden sabitlenmiş modeli ileriye dönük test et. Gelecek çekilişi önceden görme ve geçmişi tahmin başarısı gibi sunma.”** de.

_Not: Bu README denemelerin kaynak kodlarını ve doğrulanmış kısa sayısal sonuçlarını tek noktada tutar; bütün ayrıntılı raporlar GitHub Actions çıktı ZIP'lerinde olabilir. V64–V77 için ayrı hesaplayıcılar ve Actions raporları vardır._
