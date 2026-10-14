# V35 — 11 gerçek çekilişin 1/0 DNA'sı: 80 sayının çift karakteri
**Tarih:** 14.10.2026. **Kaynak:** GitHub veri.txt, 72 tam gün, 15.624 çekiliş, 14.904 geçerli 11'li kesit. Geriye dönük tarama; eksik 2 gün tam-gün raporuna alınmadı.

## Karakter tanımı

- Her sayının her kesitte geçmiş 11 gerçek çekilişi bir 11-bit imzaya dönüştürülür: \`1=çıkan 20\`, \`0=çıkmayan 60\`. Pencere yalnız geçmiş ve mevcut çekilişi içerir. Gelecek çekiliş sonucu sadece test etiketidir.
- \`YOGUN_6PLUS\`: son 11 çekilişte 6 veya daha fazla çıkış.
- \`BEKLEYEN_6PLUS\`: üst üste 6 veya daha fazla çıkmama.
- \`DUZENLI_4_5\`, \`NORMAL_2_3\`, \`AZ_0_1\`: kalan sayıların diğer 11'li görünme durumları.
- **Önemli matematiksel zorunluluk:** Bir sayının aynı 11 gerçek çekilişte 6 kez görünüp son 6 çekilişte görünmemesi mümkün değildir (en az 12 konum gerekir). Ancak farklı iki sayı aynı anda bu zıt karakterleri taşıyabilir.
- 01:02→07:02 arası saat boşluğu çekiliş oluşturmaz, sıra 13→14 ardışıktır. Eksik kayıt, ardışık imzayı sıfırlar. Gün içinde ilk 11 kayıt tamamlanmadan imza çıkarılmaz.

## Gerçek çekilişlerde her 80 sayılık kesitte karakter büyüklüğü

| Karakter | Ortalama sayı | RNG 20/80 beklentisi |
|---|---:|---:|
| 11'de 6+ kez görülen | 2,74047 | 2,74620 (80×Binom(11,.25) P[X>=6]) |
| Ardışık 6+ kez çıkmayan | 14,26704 | 14,23828 (80×(.75)^6) |

Aynı anda en az bir yoğun ve en az bir bekleyen sayı bulunan **14.247/14.904** kesit. Toplam 1.192.320 sayı–kesit kaydı; bunların 1.186.560'ında sonraki gerçek çekiliş hedefi değerlendirilebilir.

## İlk 36 gün / son 36 gün ayrımı: son 36 gündeki 80/20 geri dönüş

| 11 penceresi sonrası sınıf | Test olay | Sonraki 20 sayıda çıktı | Gerçek |
|---|---:|---:|---:|
| Yoğun 6+ | 20.488 | 5.117 | %24,9756 |
| Bekleyen 6+ | 105.736 | 26.407 | %24,9745 |
| Düzenli 4–5 | 147.961 | 36.901 | %24,9397 |
| Normal 2–3 | 268.932 | 67.412 | %25,0666 |
| Az 0–1 | 50.163 | 12.483 | %24,8849 |

Bağımsız çekilişte tek sayının sonraki 20'de yer alma şansı **%25**. Bu gruplar üstündür diyemiyoruz.

## İki farklı karakterden seçilmiş iki sayı bir sonraki 20'de birlikte çıkıyor mu?

| Tarih dönemi | Zıt karakter sayı çifti olayı | İki sayı da çıktı | Oran |
|---|---:|---:|---:|
| Eğitim (ilk 36) | 293.670 | 17.630 | %6,00334 |
| Test (son 36) | 297.673 | 17.791 | %5,97669 |
| Bağımsız 20/80 referansı | — | — | %6,01266 |

**RNG referansı:** \`(20/80)*(19/79)\` (iki farklı sayının aynı gerçek 20 içinde olma olasılığı). Zıt karakterlerden seçilen çiftlerin sonraki çekilişte birlikte görünme sıklığı da beklentiye yakındır.

## 11 haneli imzaların bağımsız testte sönmesi

İlk 36 günde \`10100010110\` imzası sonraki çekilişte %39,806 (41/103) çıkış gösterdi; son 36 günde **%21,818 (24/110)** oldu. \`01001001011\` imzası ilk 36 günde %38,318 (41/107), sonraki 36 günde **%18,478 (17/92)** oldu. Önceki yüksek skor gelecek üstünlüğünü garantilemez; çoklu imza taraması seçim yanlılığı doğurabilir.

## GitHub ve ZIP

- \`v35_11_cekim_cift_karakter.py\` 11 bit, 80 sayının her kesiti, beş karakter, V28 ısı, V32 döngü, alt/üst 40, 8 bant, hareket, birlikte gelme çiftleri.
- \`v35_11_karakter_app.py\` V35 Streamlit tek ZIP sekmesi.
- \`v35_selftest.py\` eksik veri, 13→14, hedef sızıntısı, binom ve gerçek ZIP testleri.
- \`v35_export_zip.py\` otomatik GitHub dışa aktarımı.
- \`.github/workflows/v35-check.yml\` başarılı 72 gün testi ve tek ZIP Artifact.
- **18 dosyalık ZIP (yaklaşık 16,1 MB):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38558994284/artifacts/11891821552

**Sonuç:** Karakterleri tek tek ve birlikte tanımlayan kayıt altyapısı kurulmuştur. Şu verilerde 11'li tekil ve zıt çift karakter, gelecek sayı isabetinde adil 20/80 modelinin güvenilir biçimde üstüne çıkmamıştır. Bundan sonraki çalışma ancak önceden dondurulmuş kuralları yeni günlerde sınayarak yapılmalıdır.
