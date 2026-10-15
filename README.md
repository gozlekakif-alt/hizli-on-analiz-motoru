# HIZLI ON — GitHub Ana Araştırma Sayfası

**Son güncelleme:** 15 Ekim 2026 (V67 tamamlandı)

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

### Yeni sohbetten devam etme

Yeni sohbette şu tek adresi paylaşmak yeterli:

**https://github.com/gozlekakif-alt/hizli-on-analiz-motoru**

Yeni asistana: **“Bu depodaki README, veri.txt, V58–V67 programları, V64 RNG, V65 aile tamamlama, V66 ilk20 ve V67 72. günün 217 çekilişi için geçmiş birliktelik sonuçlarıyla Actions ZIP raporlarına bak. Günler arası kademeli geçişler RNG'den istatistiksel ayrışmadı; yalnız yeni, henüz incelenmemiş tam günlerle önceden sabitlenmiş modeli ileriye dönük test et. Gelecek çekilişi önceden görme ve geçmişi tahmin başarısı gibi sunma.”** de.

_Not: Bu README denemelerin kaynak kodlarını ve doğrulanmış kısa sayısal sonuçlarını tek noktada tutar; bütün ayrıntılı raporlar GitHub Actions çıktı ZIP'lerinde olabilir. V64–V67 için ayrı hesaplayıcılar ve Actions raporları vardır._
