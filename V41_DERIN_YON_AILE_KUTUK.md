# V41 — Derin Yön, Hız, İvme ve Aile Birleşimi Araştırma Kütüğü

**14 Ekim 2026.** V40'ın sonuçlarını geliştirmek için yazılan ilk V41 araştırma sürümüdür. Mevcut `veri.txt`, V38, V39, V40 kod ve raporları korunur.

## Neden V41?

V40'ta altı sıcaklık grubundaki sayılar, çıkan20'ye yaklaşık %25 oranında girdi. Son 36 günlük %25 referanslı Brier değeri `0.18750000`, V40 ısı×yön online kalibrasyonu `0.18750446` idi. Yalnız **sıcaklık veya tek adımlı yön** yeterli kanıt vermedi.

V41 şu daha ayrıntılı hareketleri birbirinden ayırır:

1. **Havuz basamak hızı**: sıcaklıktaki göreli sıra değişimi `0`, `1` veya `2PLUS`.
2. **İki ardışık yön**: iki yükseliş, iki düşüş; düşüşten yükselişe / yükselişten düşüşe ters dönüş.
3. **Durma/fren**: önceki hareketten sonra aynı sıcaklık koltuğunda kalış.
4. **Isı puanı ivmesi**: yalnız koltuk sırası değil EWMA ısı değerinin son iki farkındaki hızlanma/yavaşlama/ters dönüş.
5. **Sınıfta yaşama süresi**: giriş, 2–3, 4–6, 7+ adım.
6. **Aile yön eşliği**: bir sayının aile sinyali ile geçmiş çıkan20 üyelerindeki yön uyumu (ilk etapta tarama sinyalidir, bütün ikili/üçlü/dörtlü yaşam epizodlarının tam yeniden kuruluşu değildir).
7. **Bant baskısı**: yakın geçmişteki onluk bant yükünün yön hareketiyle kesişimi.

Bütün özellikler `t) çekilişi görülmeden önce `t-1,t-2,...` verisinden çıkarılır. Isı hafızası günler arasında devam eder; gün içi aile ve hareket zamanının hesabı 217 gerçek çekiliş sırasına dayanır. 01:02→07:02 aralığına hayali çekiliş eklenmez.

## 9 ileri test yöntemi

- `YON_HIZ` — sıcaklık yönü × sıçrama hızı
- `YON_DEVAM` — altı havuz × yön epizodu × kalış
- `YON_IVME` — hızlanma / yavaşlama / fren / yön ters dönüş
- `YON_AILE` — yön epizodu × aile gücü × önceki 20'li yön eşliği
- `YON_BANT` — havuz × yön × bant baskısı
- `YON_BIRLESIM_ONLINE` — üstteki beşten **önceden sabitlenmiş** 0,25 / 0,25 / 0,20 / 0,20 / 0,10 ağırlıklı birleşim
- `YON_BIRLESIM_SABIT` — aynı birleşimin yalnız ilk 36 günde öğrenip son 36 gün boyunca parametre güncellemediği kontrolü
- `V39_ESKI_PANEL` — önceki V39 sıcak-soğuk, bant, aile, 20 sayı birleşimi kontrolü
- `RASTGELE_20` — sayı kimliklerinden bağımsız ve tekrar üretilebilir 20/80 kontrolü

**Ön kayıtlı asıl karşılaştırma:** `YON_BIRLESIM_ONLINE` — `RASTGELE_20`, son 36 tam gün. V39 ile karşılaştırma ve sabit-birleşim kontrolü ikincildir. Beş alternatif ayrı motorun en iyi görünenini son test günlerinde seçmek sonuç manipülasyonu olur; araştırma kütüğünde sabit ön kayıtlı birleşim asıl kıstastır.

## Olasılık, öğrenme ve zaman kuralı

- Her uzman `t) öncesi koşullu geçmiş oranını, %25 merkezli 200 gözlem Beta yumuşatmasıyla üretir.
- Sayı başına 5 uzmanın olasılıkları ağırlıklı birleşir; yüksek puanlı 20 farklı sayı **hedef gerçek20 okunmadan** sabitlenir.
- Gerçek çekiliş geldiğinde 0–20 isabet ve 80 sayılık Brier puanı hesaplanır.
- **Sonrasında** geçmiş sayı/ısı/aile motorları ilerler, online deneysel öğrenme güncellenir.
- İlk yarının sonundaki uzman parametreleri `SABIT` koluna alınır. Bu kol son 36 gün boyunca test sonucuna göre güncellenmez.
- Bağımsız yeni gerçek günler olmadan geçmişteki yüksek bir isabet "RNG çözüldü" iddiası değildir.
- Karşılaştırma aynı günün 217 çekilişini bağımlı blok kabul eden bootstrap belirsizliğini içerir.

## Sekiz dosyalı tek ZIP

1. `00_NASIL_OKUNUR.txt`
2. `01_CEKILIS_ONCESI_80_SAYI_YON_KARTLARI.csv`
3. `02_GERCEK_HEDEF_ONCESI_DONDURULMUS_20_LISTELER.csv`
4. `03_ILK36_SON36_YON_MOTORLAR_ISABET.csv`
5. `04_YON_HIZ_IVME_KALIS_AILE_BANT_KESISIM.csv`
6. `05_ILERI_OLASILIK_BRIER_VE_BELIRSIZLIK.csv`
7. `06_MOTOR_KARSILASTIRMA_GUN_BLOK.json`
8. `07_KAPSAM_VERI_VE_ON_KAYIT.json`

## Kod ve kabul testi

- `v41_derin_yon_gecis_motoru.py`: analiz kaynağı.
- `v41_derin_yon_app.py`: V10 Streamlit içindeki **↗️↘️ V41 Derin Yön ve Aile** sekmesi.
- `v41_derin_yon_selftest.py`: hedef sonucu değiştirilince çekiliş öncesi listelerin değişmediğini, 20 farklı sayı şartını, altı sıcaklık haznesini ve eğitim/test ayrımını test eder.
- `v41_derin_yon_export.py`: 72 tam gün otomatik geçmişten geleceğe test.
- `.github/workflows/v41-derin-yon-check.yml`: GitHub Actions ve ZIP.

**Asıl sonuç ve V41 başarı durumu yalnız 72 gün çalışması başarılı olup gerçek rakamlar kontrol edildikten sonra rapora eklenecektir.** Hedef 16/20 araştırılabilir ama bu veya herhangi bir motorla mümkün olduğu henüz gösterilmedi.
