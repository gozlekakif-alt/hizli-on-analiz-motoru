# V121 — 56 İç İçe Halka Üzerinde 29 Sayı Yöntemi, 16 Rastgele Kontrol

**17 Ekim 2026 — başarıyla tamamlanan gerçek araştırma.**

**Çalışan uygulama:** [v121_56_icice_45_model_80_sayi_kor_test.py](v121_56_icice_45_model_80_sayi_kor_test.py)

**Doğrulanmış başarılı GitHub Actions koşusu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38967796471

**Yedi dosyalı 21,5 MB sonuç ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38967796471/artifacts/12075222244

## Testin tam kapsamı

- **AİLELER YOK:** hiçbir model aile kimliği kullanmıyor; 1–80 sayıların 1/0 geçmişi, çıkış frekansı, havuz yönü, ritmi ve 56 halkalık sinyalleri inceleniyor.
- V100B ile tam aynı **56 İÇ İÇE kümülatif pencere**: son **12,24,36,…,672 çekiliş**, hedef T gelmeden 80 sayı/16'şarlı 5 sıcaklık havuzu. V115/V116'nın 56 AYRI 12'li fiziksel halka sistemiyle karıştırılmamalı.
- Kaynak: 15.790 gerçek çekiliş, son veri **13 Ekim 2026 #62014**. İlk 672 hafıza; sonraki **15.118** tekil hedef çekiliş sonucu **görülmeden önce** sayı sıralaması çıkarılır.
- **29 farklı skorlama modeli** ve **16 ayrı bağımsız rastgele kontrol** = 45 eşit bütçeli yöntem. Her hedefte 3,4,5,6,7,8,9,10 ve 20 sayılık kuponlar (her yöntem her boy için bir kupon). 45×15.118 = **680.310 hedef-model satırı**.
- Fikirler: sıcak/soğuk 12,24,72,144,672; kısa/uzun 56 halka yön farkı ve tersi; sert sıcak-soğuk dönüşü; yön kırılması; hızlanma; kararlılık ve oynaklık; kısa/uzun 1/0 patlaması; 5/12 çekilişlik ritim yankısı; son çekilişi tekrarlayan/atlayan; gecikme süresi; ilk 36 gündeki geçmişe eğitilmiş düzenlileştirilmiş doğrusal model (RIDGE).
- İlk 36 gün **TRAIN36 7.140 hedef**; sonraki 18 gün **VALIDATE18 3.906 hedef**; son 18 gün **HOLDOUT18 3.906 hedef**; daha sonra eklenen 166 gerçek hedef **EXTRA**.
- RIDGE modeli yalnız TRAIN36'da öğrenildi. **Kazanacak tek yöntemin seçimi yalnız VALIDATE18 dönemindeki 10-sayı ortalama isabetine dayanır**. Son HOLDOUT18 sonuçları seçilen yöntemi değiştirmez. En çok kupon kazandıran nadir 5/5/6/6/8/10 örnekleri sonradan seçilmez.
- **ÖNEMLİ:** Tarihsel 72 gün daha önce V9–V120'de zaten araştırıldığı için 18 günlük HOLDOUT yalnız bu kod açısından zaman sıralı, tamamen yeni/bağımsız kör veri **değildir**.

## VALIDATE18 sonrası dondurulmuş tek seçim

**Seçilen yöntem: HOT12**, çünkü VALIDATE18 10 sayılık ortalama isabette 29 modelin ilk sırası.

| Doğrulama 10 sayılık yöntem | VALIDATE18 ortalaması | HOLDOUT18 ortalaması | HOLDOUT18'de 8+/10 |
|---|---:|---:|---:|
| **HOT12 (kilitlenen)** | **2,5402** | **2,4995** | 1 |
| HOT24 | 2,5325 | 2,5023 | 0 |
| COLD672 | 2,5312 | 2,5020 | 1 |
| RIDGE_TRAIN36 | 2,5297 | 2,5051 | 1 |
| BURST_24_VS_PREV120 | 2,5202 | 2,4959 | 0 |
| COLD72 | 2,5182 | 2,4652 | 2 |

Bu tabloda altıncı sıradaki COLD72'nin **2 kez 8+/10** tutturması bile ortalama başarıyı yükseltmedi. Nadir yüksek isabetler, ileriye dönük tahmin üstünlüğü demek değil.

## HOLDOUT18 gerçek tam k/k olayları: 3.906 hedef, 1 kupon/yöntem/hedef

| k'lı kupon | Kilitli HOT12 k/k | HOT72 k/k | 16 rasgele serinin ortalama k/k |
|---|---:|---:|---:|
| 3/3 | **57** | 65 | 52,5 |
| 4/4 | **16** | 14 | 11,812 |
| 5/5 | **4** | 2 | 2,562 |
| 6/6 | **1** | 0 | 0,312 |
| 7/7 | **0** | 0 | 0 |
| 8/8 | **0** | 0 | 0 |
| 9/9 | **0** | 0 | 0 |
| 10/10 | **0** | 0 | 0 |

### HOLDOUT18, on sayılık kupon

| Yöntem | 10'luk ortalama isabet | 5+/10 | 6+/10 | 8+/10 | 10/10 |
|---|---:|---:|---:|---:|---:|
| HOT12 (kilitli kazanan) | **2,4995** | **255** | **57** | **1** | 0 |
| HOT72 | **2,5100** | Karşılaştırma CSV | CSV | 0 | 0 |
| RANDOM16 (ortalama) | **2,5011** | CSV | CSV | CSV | 0 |

**Gün bazında eşlenmiş bootstrap belirsizlikleri** (18 gün):

- HOT12 − HOT72: **−0,01050 isabet/çekiliş**, %95 aralık **[−0,04915, +0,02842]**.
- HOT12 − RANDOM16: **−0,00163 isabet/çekiliş**, %95 aralık **[−0,03570, +0,03120]**.
- HOT12 − HOT672: **+0,00486**, %95 aralık **[−0,03584, +0,04327]**.

Tüm aralıklar sıfırı içerir. 5/5 veya 6/6'lık münferit sevindirici sayılar **kalıcı tahmin avantajı** göstermiyor.

## HOLDOUT18, 20 sayılık seçme kontrolü

Kilitli HOT12, 20 sayının tamamında **4,9972 isabet/20**; HOT72 **5,0236**; RANDOM16 **5,0035**. Adil çekilişte herhangi sabit 20 sayının ortalaması **5** olur. Bu da 56 iç içe halka yöntemiyle %80 hedef sayıyı tutturma iddiasını desteklemiyor.

## Doğrulanmış ZIP içeriği

1. `00_V121_TURKCE_KISA_SONUC.txt` — Özet ve bütün kupon boylarında tam isabet.
2. `01_TUM_HEDEFLER_45_MODEL_3_4_5_6_7_8_9_10_20.csv` — **680.310** hedef-yöntem; seçimden önce belirlenmiş ilk 20 sayı ve hedefte 0/1 sonuçları, 9 kupon boyunun isabeti.
3. `02_KILITLI_SECILI_MODEL_VE_KONTROL_BOYUT_SONUCLARI.csv` — 18 gün bazında kilitli seçki.
4. `03_DOGRULAMA_SIRALAMA_SON18_KONTROL.csv` — 29 modelin doğrulamada sıralanması ve değiştirilmeyen son 18 gün sonuçları.
5. `04_KILITLI_KAZANAN_GUN_BAZLI_GUVEN_ARALIKLARI.csv` — eşlenmiş günlük bootstrap belirsizlikleri.
6. `05_SON_HEDEF_ONCESI_80_SAYI_56_HALKA_672BIT.csv` — son hedefin 80 sayısının tam 672 bit 1/0 geçmişi, tüm 56 pencere frekansları ve beş sınıf yolu.
7. `06_DENETIM.json` — kayıtlar, 56 pencere, dönemler, kilitli model ve ileriye dönüklük denetimi.

## Değerlendirme ve önerilen devam

29 yöntem + 16 kontrol kullanarak güçlü bir **tarihsel negatif bulgu** elde ettik: kısa/uzun sıcaklık, ters yön, ritim, yön kırılması, atlama, istikrar ve doğrusal öğrenme kombinasyonları bu veri altında HOT72 ve rastgele kontrolden güvenilir biçimde üstün çıkmadı. Bu durumu 'henüz bulunamadı' demek yeterli; 'hiçbir zaman bulunamaz' matematiksel sonucu çıkarılmaz.

Yeni çekilişlerde V121'in **kodu, kazanan modeli ve kupon sayısı kilitli** tutulup önce kupon yazdırılmalı ve sonra sonuç kaydedilmelidir. Hedef başına kupon sayısı artarsa şansla gelen en iyi kupon sayısı da artar; adil kıyas için sayı ve bütçe aynı kalmalıdır. Geçmişteki birkaç 5/5,6/6 olayına bakarak gerçek para riskine girilmemeli; güvenilir olumlu sonuç için bağımsız, önceden zaman damgalı ileriye dönük kanıt gerekir.
