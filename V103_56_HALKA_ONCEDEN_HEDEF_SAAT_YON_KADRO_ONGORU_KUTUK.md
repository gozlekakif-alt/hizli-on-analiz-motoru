# V103 — Hedef Saat Başlamadan 56 Halka Yön Kadrosunu Dondur

**16 Ekim 2026 | Çalıştırıldı, başarılı:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38906297727  
**Kaynak kod:** [v103_56_halka_hedef_saat_yon_on_goru.py](v103_56_halka_hedef_saat_yon_on_goru.py)  
**10 dosya / CSV + JSON + rapor:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38906297727/artifacts/12047878193  
**V100C ve V102 dosyaları değiştirilmedi.**

## Talep ve uygulanan yöntem

Bu sistem **kupon motoru değildir**. Yalnız hedef saat **başlamadan önceki 672 çekilişin 56 halka yönüne** bakarak 80 sayının 12 çekilişlik saatte nasıl dağılacağını betimleyen **dondurulmuş öngörü kaydı** oluşturur. 80 sayının son 55/56 tamamlanmış halkasının V102 tanımlı 72'lik göreli sıcaklık havuzu alınır (her havuzda 16 sayı). Son altı tamamlanmış halkada son statü 6 önceki statüden yüksekse **ISINIYOR**, düşükse **SOGUYOR**, aynıysa **DENGELI**.

- **Hedef saatten önce:** 80 sayı yön gruplarına ayrılır; önceden sabitlenmiş ilk 36 günün ampirik frekansıyla her grubun H1–H12 boyunca beklenen **toplam görünüm sayısı** hesaplanır. Bunlar *kaç farklı sayı* değil **12 çekiliş boyunca tekrarlı toplam görünüm** sayısıdır.
- **H1–H6 geldikten sonra:** O ilk altı gözlemde sayı başına 0, 1, 2, 3+ geliş ayrı toplanır, önceden ilk 36 günden öğrenilmiş tablo kullanılarak **yalnız H7–H12** güncellenir.
- **Saat bitince:** Gerçekte H1–H12'de gelen sayıların hangi yön grubundan geldiği ve kaç kere geldiği karşılaştırılır. Hedefin kendi verisi *hedef öncesi* yön sınıfını oluşturmaz.
- **Depoya yeni veri gelirse:** GitHub workflow yeniden çalışır. 1–11 kayıtla eksik gün/saat geldiğinde bile **saat başlangıcındaki yön haritası** sabitlenir, H1–H6 gelmişse sonraki altı çekiliş için güncelleme yapılır. Eksik saat verileri uydurulmaz.
- Yöntemde sayıların bir çekilişte çıkma tahmini sabit %25 referansıyla karşılaştırılır. Bahis stratejisi olarak doğrulanmış üstünlük iddia edilmez.

## Veri ve araştırma sonucu

GitHub'da son doğrulanmış dosya sonu **13.10.2026 19:57, #62014**. Güncel 16 Ekim çekilişlerini gördüğümüz anlamına gelmez.

İlk 36 günün **587 tam hedef saati** öğrenme; sonraki **659 tam saat** değerlendirme: orta 18 gün 324 saat, son 18 gün 324 saat, 13 Ekim ek veri 11 saat. Önceden sabitlenmiş eğitim aşamaları dışında model güncellenmez.

| Dönem | Saat | Önceden H1–H12 Brier | İlk6 sonrası H7–H12 Brier | Sabit %25 referansı |
|---|---:|---:|---:|---:|
| Orta 18 gün | 324 | 0,187503268 | 0,187522634 | **0,187500000** |
| Son 18 gün | 324 | 0,187499281 | 0,187527482 | **0,187500000** |
| 13 Ekim ek veri | 11 | 0,187506437 | 0,187676789 | **0,187500000** |

Bu farklar çok küçük, **ileri gelen tahmin avantajı doğrulanmadı**. Yalnızca basit %25 referansından daha fazlasını öğrenebilmek için kayıt altyapısı tamamlandı.

13 Ekim **19:02–19:57** saatinde (#62003–#62014) hedef başlamadan yön kadrosu ve hedef sonrası görünüm şöyle eşleşti:

| Yön grubu | Sayı adedi | 12 çekilişte beklenen toplam görünüm | 12 çekilişte gerçekleşen toplam görünüm |
|---|---:|---:|---:|
| Isınan | 33 | 98,787 | 101 |
| Soğuyan | 30 | 90,244 | 91 |
| Dengeli | 17 | 50,891 | 48 |
| **Toplam** | **80** | **239,922** | **240** |

Bir sayının 12 çekilişte en az bir kere çıkmasını tahmin saymak yanıltıcıdır; gerçek değerlendirme çekiliş bazında, grup bazında ve sayı başına yapılır.

## Son kaynak kaydı #62014 sonrasında henüz görülmemiş saat için **sabitlenmiş kayıt**

**Bu, 13 Ekim 2026 19:57'den sonraki kayıtsız saatin arşiv öncesi öngörüsüdür; 16 Ekim'in gerçek saatlik tahmini değildir.** Hedef numarası ve gerçek sonuçlar bilinmediği için uydurulmaz. Tam her sayı olasılığı GitHub Actions ZIP içindeki `08_HENUZ_GELMEMIS_SAAT_KILITLI_ONGORU.json` dosyasında.

| Hedef öncesi yön | Sayı adedi | 12 çekilişte beklenen toplam görünüm |
|---|---:|---:|
| **ISINIYOR** | **35** | **104,7480** |
| **SOGUYOR** | **38** | **114,2866** |
| **DENGELI** | **7** | **20,9823** |
| **Toplam** | **80** | **240,0169** |

**ISINIYOR (35):** 1, 2, 4, 10, 15, 16, 17, 18, 19, 20, 25, 28, 30, 31, 32, 33, 36, 40, 42, 43, 44, 47, 52, 53, 56, 58, 60, 61, 62, 65, 66, 68, 71, 78, 79.

**SOGUYOR (38):** 3, 6, 7, 8, 9, 11, 12, 13, 14, 21, 22, 23, 24, 26, 29, 34, 35, 37, 38, 39, 41, 45, 46, 48, 49, 50, 51, 54, 55, 57, 63, 64, 67, 69, 70, 72, 73, 80.

**DENGELI (7):** 5, 27, 59, 74, 75, 76, 77.

Beklenen sayılar **240 toplam çekiliş görünümünün** üç yön grubuna dağılımıdır. Örneğin "ısınan 35 sayı 104,75 görünüm" demek, bu 35 sayının tamamının çıkacağı iddiası değildir. Ampirik tahminlerin referanstan farkı çok azdır; gerçek oyun sonucunu önceden bilme imkânı gösterilmemiştir.

## ZIP dosyaları

1. `00_V103_SAAT_TAHMINI_YON_KADRO_SONUC.txt`
2. `01_DONEMLERE_GORE_ONGORU_KALIBRASYON.csv`
3. `02_TUM_HEDEF_SAATLER_SABIT_ONGORU_KARSI.csv`
4. `03_HEDEF_SAAT_ISINAN_SOGUYAN_KADRO_TAHMIN_GERCEK.csv`
5. `04_HEDEF_SAAT_80_SAYI_YON_ZINCIR_13EKIM.csv`
6. `05_36GUN_EGITIM_YON_HAVUZ_IHTIMALLERI.csv`
7. `06_ILK6_OLDUKTAN_SONRA_7_12_KOSULLU.csv`
8. `07_SON_TAM_SAAT_ONCE_SONRA_DONDURULMUS.json`
9. `08_HENUZ_GELMEMIS_SAAT_KILITLI_ONGORU.json`
10. `09_TAM_METOT_VE_VERI_SIZMA_DENETIMI.json`

**Sınırlama:** 72 eski gün önceki V9–V102 çalışmalarında araştırılmıştır. 13 Ekim yeni veri yalnız 11 tam hedef saat içermektedir; gerçek anlamda bağımsız yeni bir avantaj tespit etmek için tarihlere göre ileriye dönük dondurulmuş kayıtların gerçekleşen sonuçlarla kıyaslanması gerekir.
