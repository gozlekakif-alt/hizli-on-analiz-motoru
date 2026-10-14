# V40 — Altı Sıcaklık Havuzunun Gerçek 20 Sayıya Katkısı
**Tarih:** 14 Ekim 2026 · Durum: kodlandı, 72 tam günlük veri ve sentetik zamansal sızıntı testleri başarıyla geçti.

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

## 72 tam günlük gerçek çalışma sonucu — 14 Ekim 2026

**Başarılı GitHub Actions:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38622763751

**İndirilebilir V40 tek ZIP (28,3 MB):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38622763751/artifacts/11922677826

- Resmi kaynak: 72 tam gün, 15.624 gerçek çekiliş; girdi metninde iki hatalı/mükerrer kaynak satırı ayrıca dışlandı.
- İlk gerçek çekiliş geçmişi kurmak için kullanıldı; `15.623 × 80 = 1.249.840` sayı-çekiliş öncesi özellik ve sonraki çıkan20 karşılaştırma kartı saklandı.
- 6 sıcaklık koltuğu her çekilişte 13+13+14+14+13+13=80 numara olarak kalıyor.
- Son 36 günde (7.812 gerçek çekiliş) havuz başına sonraki gerçek20'ye geliş:

| Havuz | Önceki havuz üyeliği gözlemi | Gerçek çıkan20'ye girdi | %25 RNG beklentisi | Gerçek oran |
|---|---:|---:|---:|---:|
| SOGUK | 101.556 | 25.278 | 25.389 | %24,89070 |
| SOGUGA_YAKIN | 101.556 | 25.555 | 25.389 | %25,16346 |
| ORTA | 109.368 | 27.129 | 27.342 | %24,80524 |
| ILIK | 109.368 | 27.419 | 27.342 | %25,07040 |
| SICAGA_YAKIN | 101.556 | 25.347 | 25.389 | %24,95864 |
| SICAK | 101.556 | 25.512 | 25.389 | %25,12112 |

**Bağımsız 20/80 kontrolü:** Sabit her sayı %25, Brier 0,18750000.

**V40 çevrimiçi ısı×yön kalibrasyonu:**

| Dönem | Gün | Hedef gerçek çekiliş | V40 Brier | Basit RNG Brier | V40 − RNG |
|---|---:|---:|---:|---:|---:|
| İlk yarı | 36 | 7.811 | 0,18752253 | 0,18750000 | +0,00002253 |
| Son yarı | 36 | 7.812 | 0,18750446 | 0,18750000 | +0,00000446 |

Son 36 gün farkının günlük blok bootstrap %95 aralığı **[+0,0000018, +0,0000073]**. Brier daha küçük daha iyi olduğu için bu nokta tahminleri V40'ın %25 referansından **çok az daha kötü** olasılık tahmini verdiğini gösteriyor. Bu, kural tabanlı bu motorun gerçek RNG'deki her türlü yapıyı dışladığı anlamına gelmez; **bu araştırma kolu henüz öngörü avantajını kanıtlamadı**.

Kesişim tablosu `03_SICAKLIK_YON_AILE_BANT_KALIS_SONUCLARI.csv` gerçek çekilişte aynı anda meydana gelen ısı-yön-bant-aile geçişlerini ayrıntılandırır. Bu tarama aşamasındaki çapraz sayımlar birbirinden bağımsız deneme değildir. Daha derin alt motorlar yalnız sonraki bağımsız günlerde tekrarlanan etkiler olursa gerekçeli olarak çoğaltılmalıdır.

**Kaynak doğrulama:** GitHub Actions kontrol testleri 20/60 toplamını, altı havuz kapasitesini, 01:02→07:02 sahte çekiliş üretmeme kuralını ve `hedef t` değişse de `t` öncesi özellik kartının değişmemesini doğruladı. Bu başarı gizli RNG tohumunun çözüldüğü anlamına gelmez.
