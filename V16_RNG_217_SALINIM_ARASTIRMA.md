# V16 — RNG salınımı: 217 çekiliş ve 80/20 olasılık sınaması

**Tarih:** 13.10.2026 · **Veri:** GitHub `veri.txt` · **Dönem:** 01.08–12.10.2026 · **Uygulama:** 🎲 V16 RNG Salınımı

## Soru

Önceki 20 sayıdan bazen 2, bazen 5, hatta 12 sayının yeniden gelmesi bir RNG sırası mı? Bu salınım bir sonraki çekilişin 20 sayısını veya önceki 20'den taşınacak sayı miktarını önceden tahmin etmemizi sağlayabilir mi?

**Resmî bilgi:** Hızlı On oyun kurallarında, 80 farklı sayıdan 20 sayının bir *rastgele numara oluşturucu* tarafından belirlendiği açıkça yazılıdır (Madde 2.5, 6.2). Kurallarda PRNG/CSPRNG marka, sürüm, algoritma veya gizli tohum yayımlanmıyor. Kaynak: https://www.millipiyangoonline.com/hizli-on-numara/kurallar .

## Matematiksel beklenti

Eşit olasılıklı, birbiriyle bağımsız iki 20/80 çekilişinde ortak sayı adedi `X`:

`P(X=k)=C(20,k)*C(60,20-k)/C(80,20)`

- Ortalama tam **5**.
- Standart sapma **1,687632**.
- Tam **2** tekrar yaklaşık **%4,971426**.
- Tam **5** tekrar yaklaşık **%23,328074**.
- **12 veya üzeri** tekrar yaklaşık **%0,010021**, yaklaşık her 9.979 beş dakikalık geçişte bir. Bunlar bağımsızlık varsayımı altındaki matematiksel ortalamalardır, çekiliş saati için garanti değildir.

## Gerçek 73 günlük veri

15.691 gerçek **beş dakika aralıklı** çekiliş geçişi incelendi. 00:02–01:02 içindeki geçişler dahil; 01:02–07:02 arasındaki altı saatlik ara ve her günün ilk çekilişi beş dakikalık geçiş sayılmadı; eksik kayıtlar da atlandı.

| Ölçüm | Bağımsız RNG beklenen | Gerçekte gözlenen |
|---|---:|---:|
| Ortalama ortak sayı | **5,00000** | **4,99643** |
| Tam 2 tekrar | 780,07 olay | 837 olay |
| Tam 5 tekrar | 3.660,41 olay | 3.624 olay |
| Tam 12 veya üzeri tekrar | 1,572 olay | **2 olay** |

Önceden belirlenmiş 10 dilimdeki Pearson ki-kare uygunluk sonucu **χ²=14,341, serbestlik=9, p≈0,1107**. Bu veriyle adil bağımsız 20/80 çekiliş modelinin beklediğinden güçlü, tekrarlanabilir bir sapma saptanmadı. **Bu test RNG'nin güvenilirliğini kanıtlamaz, algoritmasını da belirleyemez.**

## 36 gün öğren, sonraki 37 günde salınımı önceden tahmin et

İlk 36 gün *eğitim*, sonraki 37 gün *ayrı test* olarak kullanıldı:

- Eğitim döneminde 7.736 gerçek beş dakikalık geçiş.
- Test döneminde 7.955 gerçek geçiş.
- Önceki salınım da bilinmesi gereken üç çekilişlik toplam 7.881 **test hedefi**.
- Önceki tekrar adedi **0–2 / 3–4 / 5–6 / 7–8 / 9+** sınıflarına ayrıldı; sonra gelen tekrar adedinin olasılık dağılımı eğitimde öğrenilip test döneminde sabitlendi.
- Rakip model, çekilişlerin tamamen bağımsız olduğu teorik hipergeometrik dağılım.

| Önceki tekrar adedi | Ayrı testte sonra gelen ortalaması |
|---|---:|
| 0–2 | **5,0532** |
| 3–4 | **4,9848** |
| 5–6 | **4,9896** |
| 7–8 | **4,9187** |
| 9+ | **5,0435** |

| Hata ölçümü (küçük iyi) | Matematiksel RNG modeli | Geçmiş salınımdan öğrenen model |
|---|---:|---:|
| Ortalama log-kayıp | **1,941646** | 1,946500 |
| Brier hata | **0,835339** | 0,836112 |
| Tekrar sayısı mutlak hata | **1,326735** | 1,333780 |
| Tekrar sayısı kare hata | **2,859282** | 2,862030 |
| En olası tam tekrar adedini bulma | 22,3322% | 22,3322% |

**Sonuç:** Önceki salınımdan yeni salınım tahmin eden motor, 37 günlük ayrı bölümde RNG matematiksel beklentisini geçemedi.

## 217 çekiliş ve saat ayrımı

- Tam günlük takvim 217 sıra; gece 00:02–01:02 ve 07:02–23:57 ayrı değerlendirilir.
- Önceki 20'den kalanlar her saat ve ilk/son 6 karşılaştırmasıyla ölçüldü.
- Son 37 günlük bölümde saatlik ortalamalarda çoklu-karşılaştırma düzeltmesi (18 saatlik Benjamini–Hochberg) sonrasında **anlamlı saat bulunmadı**.
- İlk altı ve son altı çekilişte ortalama tekrar sırasıyla **4,9786** ve **4,9802**; ek 01:02 tek çekilişi **5,0811**.

## Mimari / dosyalar

- `v16_rng_salinim.py`: hipergeometrik denetim, saat/217 zaman sınıflandırması, koşullu tekrar geçiş modeli, eğitim-test skorları, çoklu test düzeltmesi.
- `v16_selftest.py`: yapay kontrol, tam olasılık toplamı, gerçek 73 gün veri sınaması.
- `.github/workflows/v16-check.yml`: bağımsız otomatik test.
- `v10_app.py`: **🎲 V16 RNG Salınımı** sekmesi, test düğmesi, dağılım/gelecek tekrar hatası/saat tabloları ve CSV indirme.

Ana çekiliş verisi, V9–V15 kodu ve kuponlar değiştirilmedi.

**Araştırma sınırı:** RNG'nin gizli algoritmasını ve tohumunu yalnız sonuçların sıralanmış 20 sayısından geri çıkarmak güvenilir biçimde mümkün değildir. Gerçek bir teknik teşhis için üretecin uygulama bilgisi, çıktının üretilme sırası, tohumlama/tasarım bilgileri veya doğrulanabilir anormal sapmalar gerekir. Bu çalışma gizli RNG'yi çözdüğünü iddia etmez; veri üzerinde şimdilik bu tip bir açıklık göstermemektedir.
