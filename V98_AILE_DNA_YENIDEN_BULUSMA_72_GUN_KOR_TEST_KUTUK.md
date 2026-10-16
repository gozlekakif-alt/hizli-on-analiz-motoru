# V98 — Aile DNA'sı ve Yeniden Buluşma Motoru

**Tarih:** 16 Ekim 2026  
**Durum:** GitHub Actions koşusu başarılı.  
**Kod:** [v98_aile_dna_yeniden_bulusma_kor_test.py](v98_aile_dna_yeniden_bulusma_kor_test.py)  
**Çalıştırma:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38889188514  
**Geçici ayrıntılı ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38889188514/artifacts/12040678076

## Araştırma

- 72 tam gün / **15.624** gerçek 20/80 çekilişi.
- Daha önceki 12 kesintisiz çekilişle *tam kesişimden* doğan 6–10 sayılı aile kökleri.
- En son bilinen çekilişte eski aileden **tam 3 veya 4 üye** görüldüğünde, diğer aile üyelerinin sıradaki çekilişe dönüp dönmediği test edildi.
- `STABLE` sürümlerinde aynı çekirdek 6 önceki çekilişte en az bir başka kez de tam görünmeliydi.
- Aile kayıt hafızası 72 ve 217 çekiliş; böylece **8** önceden tanımlanmış yöntem.
- Aile üyelerinden 10'lu kupon oluşturuldu; eksikler yalnızca önceden gözlenen son 72 çekilişin sıklığıyla dolduruldu.
- Hedef çekiliş içeriği tahminden önce hiçbir şekilde kullanılmadı.
- İlk 36 gün model geliştirme, sonraki 18 gün doğrulama/model seçme, son 18 gün sabitlenmiş son test.
- **Sıcak 72** ve **rastgele 10 sayı** kontrolleri aynı hedef çekilişlerde karşılaştırıldı.

## Doğrulama (orta 18 gün)

| Aile yöntemi | Kupon sayısı | Ortalama isabet | Sıcak 72'ye fark |
|---|---:|---:|---:|
| CORE4_ANY_R72 | 3.906 | 2,507169 | **+0,011777** |
| CORE4_ANY_R217 | 3.906 | 2,507169 | +0,011777 |
| CORE4_STABLE_R72 | 2.488 | 2,507235 | +0,006431 |
| CORE4_STABLE_R217 | 2.802 | 2,502498 | +0,002498 |
| CORE3_ANY_R72 | 3.906 | 2,490527 | -0,004864 |
| CORE3_ANY_R217 | 3.906 | 2,490527 | -0,004864 |
| CORE3_STABLE_R72 | 3.855 | 2,490532 | -0,005188 |
| CORE3_STABLE_R217 | 3.901 | 2,486286 | -0,008972 |

Önceden tanımlanmış seçim kuralı doğrultusunda **CORE4_ANY_R72** seçildi. R217 aynı skor nedeniyle bir ayrı başarı gibi sayılmaz.

## Son 18 gün — gerçek kronolojik geçmişe dönük holdout

**3.906 çekiliş / 3.906 kupon (kapsam %100)**

| Karşılaştırma | 10'lu kupon ortalama isabet |
|---|---:|
| CORE4_ANY_R72 | **2,511265** |
| HOT72 | **2,509985** |
| RANDOM10 tek kontrol serisi | **2,483615** |
| Adil 20/80 oyunun matematiksel beklenen değeri | **2,500000** |

- Seçilen V98 yönteminin HOT72'ye farkı: **+0,001280 isabet/çekiliş**.
- Günlük karşılaştırmanın yaklaşık %95 aralığı: **-0,059437 ile +0,061997**.
- Keşif amaçlı günlük işaret değiştirme testi `p≈0,9693`; üstünlük doğrulanmadı.
- 10 sayı kuponunda **5+ = 264, 6+ = 54, 7+ = 12, 8+ = 2, 9+ = 0, 10/10 = 0**.
- Tam 6–10'lu aile yeniden birleşmesi **1 kez**; bağımsız adil çekiliş modelinde seçilen adayların toplam beklenen tam birleşmesi **0,1575**. Tek gözlemden güçlü sinyal iddia edilemez.

## Karar

**V98'in geçmişte aile DNA'sı üzerinden ürettiği kuponların kalıcı isabet üstünlüğü kanıtlanmadı.** Özellikle seçilen yöntemin HOT72'ye karşı ortalama farkı pratik açıdan ihmal edilebilir ve günlük güven aralığı sıfırı içeriyor. Sonraki sürüme *doğrulanmış avantajlı* yöntem olarak taşınmamalı.

- 72 günlük veri V9–V97 arasında çok sayıda geçmiş araştırmada incelendiğinden bu ayrım gerçekten el değmemiş, yeni tarihli ileriye dönük test değildir.
- Aile ve çekirdek örüntüleri sonradan seçilirse aşırı uyum riski yükselir.
- Geçmiş çekilişte bir çekirdeğin görünmesi, adil bağımsız oyunda diğer üyelerin sonraki çekilişte "borçlu" olduğu anlamına gelmez.
- Kanıt için **yeni çekilişlerde** hedef yayınlanmadan önce GitHub'a değiştirilemez tahmin ve karşılaştırma kaydı şart.

ZIP içeriği: `00_V98_SONUC_KARAR.txt`, `01_SEKIZ_MODEL_36_18_18_PERFORMANS.csv`, `02_SECILEN_MODEL_ONCEDEN_10LU_KUPON.csv`, `03_TUM_8_MODELIN_72_GUN_SINYALLERI.csv`, `04_DENETIM.json`.
