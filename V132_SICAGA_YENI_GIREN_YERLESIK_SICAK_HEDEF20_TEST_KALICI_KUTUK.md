# V132 — SICAK16 HAVUZUNA YENİ GİREN vs YERLEŞİK SICAK SAYININ SONRAKİ HEDEF20'YE GİRİŞİ

**13.101 gerçek ardışık hedef çekiliş öncesi test başarıyla tamamlandı.**

- [Başarılı GitHub Actions analiz koşusu](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/39018290177)
- [Kalıcı analiz programı](v132_sicaga_yeni_giren_ve_yerlesik_hedef20_oncu_test.py)
- [11 dosyalı ZIP (GitHub Actions 90 gün)](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/39018290177/artifacts/12095747374)
- **Kalıcı GitHub Release ve indirme bağlantısı yayımlandıktan sonra eklenecek.**

## Soru

V131'de sıcak havuza yeni giren sayıların uzun halkalarda 12 çekiliş içinde sıcaktan hızla çıktığını, aynı havuzda zaten yerleşik sıcakların daha kalıcı olduğunu gördük. Peki bu ayrımın, bir sonraki **20/80 RNG hedef çekilişinde bulunmaya** olumlu veya olumsuz etkisi var mı?

**V131'deki sınıftan çıkma ile hedefte çıkma olasılığı aynı şey DEĞİLDİR.** Bu yüzden V132'de hedef çekilişi henüz gerçekleşmemiş kabul ederek `t` anının 224 halka sıcaklık sınıfını hesapladık, `t+1` sonucuyla koşullu isabet ölçtük.

## Tanım ve yöntem

15.790 gerçek çekilişlik `veri.txt` arşivi, son gözlem 13 Ekim 2026 #62014. İlk 2.688 çekiliş hafıza; sonraki **13.101** ardışık hedef çekilişten önce önceki tamamlanmış `t` sonucu kullanıldı. 224 iç içe son-12,son-24,...,son-2688 çekilişlik halkada 80 sayının frekans sırası azdan çoğa hesaplandı. 5 havuz da tam 16 üyeden oluşur; eşit frekans halinde küçük numara önce gelir.

- **NEW_HOT**: bir önceki çekilişte sıcak olmayan (0,1,2,3), hedef öncesindeki son güncellemede SICAK4'e yeni giren sayı.
- **ESTABLISHED_HOT**: son iki bilinen çekilişte de SICAK4'te bulunan sayı.
- İki kategori her bir halkanın toplam SICAK16 üyesini tam olarak oluşturur, `NEW_HOT_N + ESTABLISHED_HOT_N = 16`.
- Karşılaştırma için her sayının **sonraki, henüz seçime dahil edilmemiş hedef20'de bulunup bulunmadığı** 0/1 olarak ölçülmüştür.
- Aynı kaynak veri üzerinde **224 halkadan** hem 80 sayı için tüm koşullu gerçek hedef oranları, hem 4×56 halka bantları, hem ayrı 12/72/672/1344/2016/2688 örnek referanslar ve 16 sıcak konumunun sınırdan içeri 0..15 sıralaması kaydedildi.
- Hedef başına ve yönteme göre **tek kupon, tam 10 farklı sayı**. Karşılaştırma yöntemleri: YENİ sıcak önceliği, YERLEŞİK sıcak önceliği, SICAK16 en üst rank10, SICAK16 sınırda rank10, SICAK16 içinden 10 rastgele, 80 sayıdan 10 rastgele.
- Yeni sıcak sayıları tek hedefte 10'dan az olduğunda kalan yerler, aynı halkadaki yerleşik SICAK16 üyeleriyle doldurulmuştur. Yerleşik sıcak öncelikli yöntemde tersi yapılır. Bu düzen, iki yöntemin kupon sayısı ve büyüklüğünü adil eşitler.
- TRAIN36 eski dönem, VALIDATE18 sonraki18 ve LAST18 daha sonraki18. **Bunlar daha önce V9–V131'de incelenmiş tarihsel günlerdir; dışarıdan yeni hiç görülmemiş harici kör test değillerdir.** 12 öncelik×halka kombinasyonundan VALIDATE18 üzerinde iyi görünen tek yöntem kilitlenip LAST18'e taşındı.

## Son 18 gün (3906 hedef çekiliş) gerçek koşullu olasılıklar

| Halka | Yeni giren sıcak sayı N | Yeni giren sonraki hedef20 oranı | Yerleşik sıcak sayı N | Yerleşik sonraki hedef20 oranı | Yeni − yerleşik, yüzde puan |
|---|---:|---:|---:|---:|---:|
| 12 | 12.927 | **%25,829659** | 49.569 | **%24,882487** | +0,947172 |
| 72 | 5.863 | %25,089545 | 56.633 | %25,101972 | −0,012428 |
| 672 | 2.054 | %25,413827 | 60.442 | %25,060388 | +0,353438 |
| 1344 | 1.486 | %24,495289 | 61.010 | %25,082773 | −0,587484 |
| 2016 | 1.487 | %24,142569 | 61.009 | %24,917635 | −0,775066 |
| 2688 | 1.212 | %24,587459 | 61.284 | %24,903727 | −0,316268 |

Adil bağımsız gerçek Hızlı On tek sayının hedef20'de bulunma beklentisi her iki sınıfta da **%25**.

## Kronolojik VALIDATE18'de benzer davranış kararlı mı?

| Halka | VALIDATE18 yeni % | VALIDATE18 yerleşik % | Yeni − yerleşik yüzde puan |
|---|---:|---:|---:|
| 12 | %25,162287 | %25,258294 | **−0,096006** |
| 72 | %25,578891 | %25,064559 | +0,514332 |
| 672 | %23,665480 | %24,981742 | −1,316262 |
| 1344 | %23,709239 | %24,860711 | −1,151471 |
| 2016 | %23,464458 | %24,897210 | −1,432752 |
| 2688 | %25,531915 | %25,053774 | +0,478141 |

Dönemden döneme **yön değiştiren halka etkileri mevcut**. Örneğin 12 halkalık yeni sıcak üstünlüğü VALIDATE18'de negatif iken LAST18'de pozitif. Dolayısıyla tek süreyi seçerek kalıcı avantaj iddia edilemez.

## 10 sayılık tek kupon eşit-bütçeli kontrol

VALIDATE18'de 12 halka×yeni/yerleşik 12 aday modelin en iyisi **12'lik halka + NEW_FIRST**: 10 sayıda ortalama **2,517409**. Değişmeden LAST18'e götürülünce:

| Model | LAST18 hedef sayısı | 10 sayı ortalama isabet | 5+/10 | 6+/10 | Tam10 |
|---|---:|---:|---:|---:|---:|
| **12 halka, YENİ SICAK ÖNCELİĞİ** | 3.906 | **2,534306** | 246 | 56 | 0 |
| Aynı halkada YERLEŞİK SICAK ÖNCELİĞİ | 3.906 | 2,506144 | 263 | 62 | 0 |
| Aynı 16 sıcak sayı içinden rastgele 10 | 3.906 | 2,528418 | 261 | 45 | 0 |
| Aynı 80 sayının içinden rastgele 10 | 3.906 | **2,517921** | 274 | 52 | 0 |

Kilitli kazanan − rastgele 80, ortalama **+0,016385 isabet/kupon**; **%95 günlük-blok bootstrap belirsizlik aralığı [−0,032258,+0,057604]**, sıfırı kapsıyor. Aynı SICAK16'dan rastgele 10 karşısında yalnız **+0,005888**, belirsizlik aralığı **[−0,021505,+0,030722]**. Yerleşik sıcak önceliğine göre **+0,028162**, %95 aralık **[−0,006663,+0,061700]**. Hiçbir fark güvenilir gerçek tahmin üstünlüğü kurmuyor.

## Analizin çıkarımı

V131'de SICAK4'e yeni girenlerin daha kolay hemen dışarı çıktığı görüldü; bu V132'de bazı halkalarda hedef20'ye daha sık girme, başka halkalarda daha az girme yönü gösteriyor. **Havuzdan çıkış riski, sayı çekilme riski değildir.** Geçmiş sonuçlardan sınıf konumu tanımlamak matematiksel olarak meşru fakat adil çekiliş geleceğini değiştirmiyor. 224 halkalar çok yüksek derecede örtüşür; üyelik vakaları bağımsız değil. Çalışmayı yeni çekilişlerle, bugünkü seçilmiş yöntemleri **değiştirmeden** doğrulamak gerekir.

## Tam ZIP içeriği

1. `00_V132_OZET_GERCEK_SONUC.txt` — kontrol ve ana bulgular.
2. `01_224_HALKADA_YENI_VS_YERLESIK_SICAK_NEXT20.csv` — tüm 224 halka × koşullar × dönemler.
3. `02_4X56_HALKA_BANDINA_GORE_SICAKLIK_GIRIS_NEXT20.csv`.
4. `03_6_REFERANS_YENI_YERLESIK_KOSULLU_NEXT20.csv`.
5. `04_6_REFERANS_GUN_BOOTSTRAP_GUVEN_ARALIK.csv`.
6. `05_SONRAKI_10_SAYI_ALTILI_MODEL_ESIT_KUPON.csv`.
7. `06_VALIDE_SECILEN_KILITLI_YONTEM_LAST18.csv`.
8. `07_16_SICAK_SINIR_DERINLIGI_YENI_YERLESIK.csv`.
9. `08_SON18_HER_CEKILIS_10_SAYI_GERCEK_KONTROL.csv`.
10. `09_GECMIS_SON_GOZLENEN_HOT_GIRIS_CIKIS.csv`.
11. `10_METOD_DENETIM.json`.

**Kod, tüm sayıları kaynak `veri.txt` dosyasından yeniden üretir.**
