# V131 — Sıcağa girmeden veya girer girmez tekrar soğuğa yöneliyor mu?

**V131 GERÇEK VERİ ANALİZİ BAŞARIYLA TAMAMLANDI VE SONUÇLAR KALICI GITHUB RELEASE'E YAYIMLANDI.**

- **Kalıcı ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/download/v131-2026-10-13-hot-entry-reversal-224-rings/V131_SICAGA_GIRIS_TERS_YON_224_HALKA_36_TAKIP.zip
- **Raporun çalıştığı GitHub Actions:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/39017306865
- **Kalıcı yayımlama koşusu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/39017418517
- **Tekrar çalıştırılabilir kod:** [v131_sicaga_yonelen_sayilar_geri_soguyor_mu_224_halka.py](v131_sicaga_yonelen_sayilar_geri_soguyor_mu_224_halka.py)

## Hipotez ve kavram

Hızlı On'da her gerçek çekilişte 1–80 arasından 20 sayı geliyor. Her yeni sonuç sonrası **224 iç içe 12,24,…2688 çekilişlik kümülatif referansta**, 80 sayı frekans sırasına göre **SOĞUK 16, SERİN 16, NÖTR 16, ILIK 16, SICAK 16** sınıfına ayrılıyor.

Kullanıcı sorusu: "Havuz içinde sıcağa yönelen sayı, SICAK sınıfına girmeden geri düşüyor mu; girer girmez geri soğuğa düşüyor mu?" Şu ayrım esastır:

1. **Sıcağa yaklaşma** = sayı NÖTR veya daha soğuk sınıftan **ILIK (3)** sınıfına yeni girer. Sonraki ilk sınıf hareketinde **SICAK (4)** sınıfına geçmesi başarı, **NÖTR/SERİN/SOĞUK (0/1/2)** sınıfına geri dönmesi **sıcağa girmeden yön tersine dönüş** sayılır. Sınıf3'te kalanlar bekleyiştir.
2. **Sıcağa yeni giriş** = sayı son yeni çekilişte 0–3 sınıfından **SICAK (4)** sınıfına geçmiş olur. Bir sonraki çekilişte <4 olması hemen sıcaktan çıkmaktır, **mutlaka SOĞUK 0 sınıfına inmesi DEĞİLDİR**. Gerçek SOĞUK0'a ulaşma ayrıca ölçülmüştür.
3. **Sıcakta yerleşik** = bir önceki ve son bilinen çekilişin ikisinde SICAK (4) sınıfında kalmış sayı. Yeni girenlerle eşit zaman pencerelerinde karşılaştırılıyor.
4. **ILIK içinde rank yükselmesi** = sınıf 3'te kalırken en soğuktan en sıcağa doğru 0–79 sıralamadaki konumu artması; seçilmiş örnek halkalarda ayrıca ölçüldü.

## Kaynak ve takip

GitHub `veri.txt`: **15.790 gerçek çekiliş**, son #62014 **13.10.2026 19:57**. İlk 2.688 kaynak çekilişi referans; ardından **13.102 tek tek gerçek çekiliş adımı** için 224×80 havuz durumu yeniden kuruldu. **13.066** adım üzerinde **tam 36 sonraki gerçek çekiliş** bulunabildiği için ters dönüş testine alındı. Son 36 arşiv çekilişi, gelecek 36 kayıt olmadığı için takip oranlarının paydasına sokulmadı.

224 halka boyunca frekans sıralaması, gerçek sayım ve 5×16 sıcaklık sınıflaması her adımda yeniden üretildi. Her bir halkada yeni giren sayının ilk belirleyici hareketi ile 1/3/6/12/24/36 sonraki çekilişte hâlâ sınıfta olup olmadığı ve gerçekten SOĞUK0'a inip inmediği incelendi.

Tam **1.985.775 ILIK'a yeni giriş** olayı ve **1.484.412 SICAK'a yeni giriş** olayı (aynı sayı farklı iç içe halkalarda birçok kez sayılabildiği için bağımsız olay değildir) incelendi.

## Sıcağa yaklaşırken yeniden soğuyanlar: bütün 224 halka olayı

| Sonraki gerçek çekiliş süresi | ILIK'tan geri daha soğuk sınıfa ilk hareketi | Önce SICAK4'e ulaşması | Hâlâ ILIK3'te kalması |
|---|---:|---:|---:|
| 1 | %27,46822 | %0,94401 | %71,58777 |
| 3 | %49,46960 | %2,53448 | %47,99592 |
| 6 | %62,44494 | %4,11955 | %33,43551 |
| 12 | **%72,46919** | **%5,93577** | %21,59504 |
| 24 | %79,38261 | %7,88045 | %12,73694 |
| 36 | **%82,20377** | **%9,02303** | %8,77320 |

Yani geçmişte, 224 halkaya dağılmış ılık havuza yeni giriş olaylarının büyük çoğunluğu SICAK4'e ulaşmadan daha alt sınıflara dönmüş; özellikle uzun pencerelerde bu sınır hareketleri çok daha fazla.

## SICAK4'e girer girmez geri çıkış: bütün 224 halka olayı

| Sonraki gözlenen çekiliş aralığı | SICAK4'ten en az bir kez çıkış | Hiç çıkmadan SICAK4'te kalış | Gerçek SOĞUK0'a bir kez erişim |
|---|---:|---:|---:|
| 1 | **%28,92620** | %71,07380 | %0 |
| 3 | %51,84228 | %48,15772 | %0,01152 |
| 6 | %65,51934 | %34,48066 | %0,13554 |
| 12 | **%76,60575** | %23,39425 | **%0,91033** |
| 24 | %84,73113 | %15,26887 | %2,77841 |
| 36 | %88,29537 | %11,70463 | %4,58249 |

**Bu yüzdeleri aynı sayının sonraki çekilişte hedef 20'ye girme olasılığıyla ASLA karıştırma.** Bu sonuçlar, hedefler gözlendikten sonra tarihsel SICAK4 sınıfını terk edip etmediğinin yüzdeleridir; SICAK4 sınıfı her adımda 16 üye tutmak zorundadır.

## En önemli karşılaştırma: SICAK'a yeni giren ve SICAK'ta yerleşik

Hesaplama aynı halka, aynı son gözlenen çekiliş ve sonraki sürelerde yapılan şartlı karşılaştırmadır.

| Halkanın referansı | Yeni sıcağa girenin sonraki 1 çekilişte çıkışı | Yerleşik sıcağın sonraki 1 çekilişte çıkışı | Yeni sıcağa girenin sonraki 12 çekilişte çıkışı | Yerleşik sıcağın sonraki 12 çekilişte çıkışı |
|---|---:|---:|---:|---:|
| **12** | **%31,15490** | %18,16269 | **%91,53987** | %90,80258 |
| **72** | **%29,48644** | %7,10686 | **%78,47030** | %43,99231 |
| **672** | **%29,04841** | %2,52640 | **%75,70952** | %16,24329 |
| **1344** | **%27,90698** | %1,63738 | **%74,50474** | %10,78410 |
| **2016** | **%28,22004** | %1,56904 | **%75,55903** | %10,12494 |
| **2688** | **%27,64312** | %1,36711 | **%74,62610** | %9,01364 |

Bu, uzun iç içe halkalarda en net görünen davranıştır: **SICAK sınıfına yeni giren çoğunlukla sınırdadır ve çok hızlı geri çıkabilir; zaten sıcak sınıfta yerleşik olanların çıkışı belirgin daha azdır.** Sabit 16'lık eşit havuz sınırı ve rank sıralaması bu davranışın mekanik nedenlerindendir.

## Sıcağa girmeden dönüş: örnek halkalar, 12 çekiliş

| Halka referansı | ILIK3'e yeni girenlerin SICAK4'ten ÖNCE daha soğuğa geri dönmesi | SICAK4'e önce ulaşan |
|---|---:|---:|
| 12 | %57,41141 | %42,54392 |
| 72 | %71,05546 | %22,48217 |
| 672 | **%73,82572** | **%0,61637** |
| 1344 | %72,79485 | %0,04289 |
| 2016 | %73,05526 | %0,03520 |
| 2688 | **%72,72017** | **%0,00000** |

Bunlar **sınıf3'e yeni giren sayıların** değerlendirmesi; sıcağa yönelmenin daha dar bir biçimi olan sınıf3'te kalırken rank yükselmesi V131 ZIP'te yalnız seçilmiş halkalar için ayrıca vardır. Özellikle son sınıf4 sınırına gerçek mesafe önemlidir: sadece sınıf3'e giriş, sıcak olacağına dair garanti vermez.

## Doğrudan gerçek SOĞUK sınıfına düşme

- Yeni SICAK4'ten çıkış ile gerçek **SOĞUK0 sınıfına iniş farklı olaydır**. Bütün ringlerde yeni girişlerin 12 çekiliş içinde sıcak sınıfı terk etmesi %76,60575, **SOĞUK0'a ulaşması yalnız %0,91033**.
- 12 çekilişlik kısa halkanın yeni sıcağa girenlerinde 12 çekiliş içinde %23,43492'si SOĞUK0'a ulaşmış. Bu kısa pencere daha hareketlidir.
- **672,1344,2016,2688 uzun halkalarda**, yeni SICAK girişinden sonraki 12 çekiliş içinde SOĞUK0'a ulaştığı gözlenmedi. Bu, hem sıcaklık sınıf sınırlarının hareketinin yavaş olması hem de 36 çekilişlik inceleme süresiyle ilgilidir.
- Tam 36 çekilişlik süre için de `01_224_HALKA_HER_GIRIS_TURU_1_3_6_12_24_36_CIKIS.csv` dosyasında kesin sayımlar vardır.

## Analizin kapsam sınırı

1. 224 halka **çok büyük ölçüde aynı geçmiş çekilişleri paylaşır**; olay sayısı, bağımsız rastgele deneme sayısı olarak kullanılamaz. Eşit 16'lık havuzlar özellikle sınıra yeni giren sayılarda yüksek oynaklık ortaya çıkartır. “Yeni girenler sınırda; yerleşikler daha içeride” açıklaması geçmiş sıcaklık kalışını açıklar, sayının bir sonraki rastgele çekilişte hedef20 içinde olmasını değil.
2. Gelecekteki **bilinmeyen** tek çekilişte belirli bir sayı için adil RNG altında teorik 20/80 çıkış ihtimali **%25**. V131'in geçmişte gözlenen dönme yüzdeleri bunu değiştirmez.
3. Repo `veri.txt` en son 13.10.2026 gerçek kaydında biter; 17 Ekim itibarıyla daha yeni gerçek kaynak olmadan “şu anda” havuza girmiş sayılar hakkında canlı iddia yoktur. ZIP'deki son giriş sayı listesi tarihsel bilgi olarak etiketlenmiştir.

## ZIP'deki dosyalar

- `00_V131_SICAGA_GIRIS_TERS_YON_GERCEK_RAPOR.txt`
- `01_224_HALKA_HER_GIRIS_TURU_1_3_6_12_24_36_CIKIS.csv` — 224 halkanın her biri, tüm 6 takip ufku, 4 band, anchor ringler; sıcak girişleri, sıcaktan çıkışlar, doğrudan ve nihai SOĞUK0'a iniş, ILIK3'teyken önce SICAK4'e varış veya aşağı ters dönüş, yerleşik sıcaklar.
- `02_HER_80_SAYI_HALKA_SICAK_GIRIS_TERSINE_DONUS.csv` — her bireysel sayının tarihsel sıcak/ılık giriş ve ters dönüşleri.
- `03_EN_SON_BILINEN_CEKILIS_SICAGA_YENI_GIRENLER.csv` — son **#62014** kaynak çekilişiyle giren tarihsel sayılar.
- `04_V131_KAYNAK_KONTROL.json` — tam metod ve 36 çekilişlik sansür/evren denetimi.

**Çıkarım:** Sıcakta kalıcılık konusunda “yeni giriş” ile “yerleşik sıcak” ayrımı gerçek ve kuvvetlidir; ancak çekilişte 20 numara tahmini için etkisinin olup olmadığı başka, hedef öncesi kurgulanmış bir testte ölçülmelidir. Bu nedenle şu an için bahis/kupon üstünlüğü veya keskin “çıkar” tahmini iddia edilmez.
