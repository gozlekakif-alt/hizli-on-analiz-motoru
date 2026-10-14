# V40 — Altı Sıcaklık Havuzunun Gerçek 20 Sayıya Katkısı
**Tarih:** 14 Ekim 2026 · Durum: kodlandı, küçük regresyon testleri geçti, tam veri otomatik çalıştırma GitHub Actions üzerinde sürüyor.

## Amaç

1–80 sayı havuzundaki **80 sayıyı, hedef çekilişi okumadan hemen önce** altı ısı koltuğunda değerlendirip her grubun bir sonraki **gerçek çıkan20'ye** katkısını ölçmek. Sayının sıcaklığa geçiş yönü, aynı sınıfta kalış sayısı, son6/11 görünme geçmişi, aile geçmişi ve 8 bant hareketi ayrı uzman hazneleri olarak kaydedilir.

Sadece her motorun 20'li kupon üretmesi istenmiyor; **tam 80 sayının bir sonraki 20'ye hangi eski karakterlerden geldiğini** görmek isteniyor.

## Kaynak, gerçek zaman disiplini

- `v11_arastirma.read_draws(veri.txt)` ve `v36_rng_davranis_klonu.sorted_draws` geçmişin tek kaynağı.
- Varsayılan yalnız 217/217 tam gün. Güne göre 00:02–01:02 gerçek 13 çekiliş, 07:02–23:57 204 gerçek çekiliş. 01:02→07:02 hayali 5-dakikalık çekiliş eklenmez.
- (t-1)'den hesaplanan EWMA sıcaklık, (t-2→t-1) sıcaklık yönü, gün içi son6/11 aile-bant görünme geçmişi **hedef t okunmadan** kaydedilir.
- O çekilişin (t) çıkan 20 sayısı yalnızca **ölçüm ve daha sonra hafızayı ilerletmek** için kullanılır. Sonuç değişse bile t'nin çekiliş öncesi karakterleri değişmemelidir; sentetik regresyon testi var.
- Kalıcı ısı hafızası günler arası devam eder; gün içi kısa aile penceresi yeniden başlar.
- Eksik gerçek çekilişler varsayılan test kapsamına alınmaz. İsteğe bağlı eksik gün çalışmasında aradaki bilinmeyen veriler tahminen doldurulmaz; bunun için tam gün araştırması bilimsel ana referanstır.

## Altı ısı koltuğu

| Koltuk | Sayı sayısı | Sonraki gerçek20'den beklenen ortalama |
|---|---:|---:|
| Soğuk | 13 | 3.25 |
| Soğuğa yakın | 13 | 3.25 |
| Orta | 14 | 3.50 |
| Ilık | 14 | 3.50 |
| Sıcağa yakın | 13 | 3.25 |
| Sıcak | 13 | 3.25 |

Her hedef çekilişte altı grubun toplam üye sayısı **80** ve gerçek20'ye giriş sayısı **20** olmalı. Tek sayı için hiçbir geçmiş karakter olmasa da adil bağımsız 20/80 referansı %25'tir. Havuz büyüklüğünden kaynaklı beklenen farklılığı tahmini bilgi sanmayacağız.

## Motor sınıfları

- **Isı kimliği**: SOGUK / SOGUGA_YAKIN / ORTA / ILIK / SICAGA_YAKIN / SICAK.
- **Yön**: Önceki ısı sınıfından yukarı geçiş / aşağı geçiş / aynı kalış / ilk kayıt.
- **Kalış**: Son sınıfa giriş 1; 2–3; 4–6; 7+ gerçek çekiliş.
- **Bant**: 01–10,11–20,21–30,31–40,41–50,51–60,61–70,71–80.
- **Bant baskı**: Son altı geçmiş çekilişte bandın gerçek20 içindeki ortalama yükü. Eşit olasılıkta bant başına beklenti 2.5 sayı.
- **Aile ikili/üçlü/dörtlü bağ**: Hedeften önceki en çok 11 gerçek çekilişte sayının son gerçek20'deki eşlikçilerle birlikte ne kadar ortaya çıktığı. Bunlar *geçmişten oluşan tarama güçleri*dir, daha önce inşa edilen bütün aile ömür kayıtlarının eksiksiz kopyası değildir.

Rapor hem yalnız altı havuzu, hem **ısı×yön**, hem **ısı×yön×aile**, **ısı×yön×bant** ve **ısı×yön×kalış** tabakalarını inceler. Bir sayının birden fazla çapraz tabakada bulunması normaldir; farklı tabakalar bağımsız ek gözlem değildir.

## Bilimsel kontrol

Önceki çekilişlerin **yalnız ısı×yön** gruplarındaki tarihsel sonraki-gerçek20 çıkma oranı, 120 gözlemlik %25 Beta yumuşatması ile hedef görülmeden kalibre edilir. Sonraki gerçek20 geldiğinde sayısal Brier ve logloss kaydedilir; ardından modelin sayaçları güncellenir.

- Adil RNG referans Brier: **0.1875**. Ortalama altı havuz dağılımına yakınlık, RNG'nin iç durumunu çözme kanıtı değildir.
- Sınıflar test döneminde de yalnız *önceki* sonuçlardan öğrenerek devam eder. Eğitim/test kronolojik ilk/son 36 gündür.
- Gün blok bootstrap aralığı ile olasılık kalibrasyonu farkı incelenir. Test örneğinin tüm sayı-adımları bağımsız değildir; aynı çekilişten 80 sayı ve birbirine bağlı günlerden çok sayı geldiği unutulmaz.
- Çok sayıda çapraz alt grupta istatistiksel sapma görülmesi tek başına üstünlük kanıtı değildir; gelecekteki yeni günlerde bağımsız doğrulama gerekir.

## Tek ZIP ve Streamlit

`v40_alti_isi_yon_havuzlari.py` hesap motoru, `v40_isi_havuzlari_app.py` Streamlit tek düğme, `v40_isi_havuzlari_selftest.py` zamansal/doğruluk denetimi, `v40_isi_havuzlari_export.py` tam gerçek veri raporu; `v10_app.py` sekmesi **🌡️ V40 6 Isı Havuzu Yön**.

ZIP dosyaları:
1. `01_80_SAYI_CEKILIS_ONCESI_TUM_KARAKTER.csv` — çekilişten önce bütün 80 sayının karakterleri ve sonraki isabetleri.
2. `02_HER_CEKILIS_6_HAVUZ_YON_DAGILIMI.csv` — havuz ve yön alt dalının mevcut sayı adedi ve gerçek20 katkısı.
3. `03_SICAKLIK_YON_AILE_BANT_KALIS_SONUCLARI.csv` — beş ayrı boyutun eğitim ve test dönemi karşılaştırması.
4. `04_ILK36_SON36_ILERI_OLASILIK_TESTI.csv` — Brier ve logloss, gün bazlı belirsizlik.
5. `05_CALIBRATION_T_ONCESI_SONUCLAR.csv` — her ısı×yön bölmesinin geçmiş eğitim sayaçları ve yumuşatılmış oranı.
6. `06_OZET_VE_KAYNAK.json` — veri kapsamı.
7. `00_KULLANIM_VE_DELIL_KURALLARI.txt` — yöntem ve kapsam.

## Tamamlanma şartı

**GitHub Actions tam gerçek veri testi, hata olmadan ZIP yüklemesi ve sonuçların kontrolü gerçekleşmeden nihai başarı açıklaması yapılmaz.** Mevcut V38/V39 motorları değiştirilmez. V40, ilk aşamada **betimsel ısı yolculuğu ve kalibrasyon** araştırmasıdır; gelecek 20 için 16/20 garantisi değildir.
