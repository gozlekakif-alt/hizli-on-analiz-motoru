# V58 — Aile Zaman Laboratuvarı: 120 gösterge, adım adım

## Kullanıcıya kısa özet

- Mevcut `veri.txt` otomatik okunur, **değiştirilmez**.
- 217 çekilişli tam günler alınır; H00 (13 çekiliş) ve H07–H23 (12'şer çekiliş) tam saat bloklarına bölünür.
- 2–20 sayılık kök aileler, *aynı saat içinde en az iki farklı 20 sayılık çekilişte birlikte görünme* koşuluyla bulunur.
- Kök/alt aile ayrımı büyük ailenin tekrarını onlarca bağımsız aile gibi saymayı önler.
- Ailelerin **hangi gün / hangi saat / hangi çekilişte** doğduğu, tekrar ettiği, tek/çok sayı değiştirerek başka aileyle benzeştiği ve hangi aileyle aynı 20'li kadroda buluştuğu incelenir.
- **12 analiz grubu × 10 gösterge = 120 sayısal saatlik metrik**. Bunlar 120 bağımsız tahmin testi anlamına gelmez.
- Aile birleşimleri: hedef çekiliş öncesindeki en çok **3 tamamlanmış saatten** tespit edilen aileler kullanılır; hedef saatten sonra aile tanımlanmaz. Aynı 20 sayı içinde iki tam kök aile görülürse buluşma sayılır.
- **Adil RNG koşullu beklentisi** de hesaplanır: birleştirilmiş aile büyüklüğü `k` ise `(20)_k/(80)_k`. Aynı çekilişte çoklu aile buluşmaları bağımsız olay değildir.

## Programın adım adım çalışma düzeni

[GitHub Actions — V58](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/workflows/v58-120-aile-zaman.yml)

1. **Verify:** Python söz dizimini ve 120 metrik + günlük SQLite kontrol noktası testini yapar.
2. **12 bağımsız gün parçası:** Her parça yaklaşık 6 tam gün üzerinde çalışır. Her tamamlanan gün **atomik SQLite commit** ile kaydolur.
3. **Checkpoint/cache:** İlgili parça tekrar çalışırsa son kaydedilen günleri geçer. Veri dosyasının kimliği değişirse eski checkpoint geçersiz sayılır ve doğru sonuçlar yeniden hesaplanır.
4. **Rapor birleştirme:** GitHub bütün parçaları indirir, kaynak kimliğini, 18 saat/gün ve 120 gösterge/saat şartını doğrular.
5. **Tek ZIP:** Tüm parçalar başarılıysa `V58_120_AILE_TAM_ZAMAN_TEK_ZIP` yüklenebilir.

> Önemli: İşlem yarıda kesilirse, o parçanın tamamlanmış günleri önbellekte tutulabilir; GitHub cache ömrü, kota ve temizleme ilkelerine tabidir. Bu nedenle cache **mutlak kalıcılık garantisi değildir**. GitHub Actions altında her işlem sonunda parçaların ayrı artifact dosyaları da saklanır.

### Veriler güncellendiğinde

`veri.txt` GitHub'a kaydedildiğinde analiz otomatik tetiklenir. Güncel, henüz tamamlanmamış günler ana 72 günlük analizden ayrı tutulur. Henüz gelen yeni veri için “başarı” veya “sinyal” iddiasında bulunulmaz.

## Nihai ZIP içerikleri

- `00_OZET_DURUM_KUTUGU.txt` — Sonuçlar ve yöntem.
- `01_120_METRIK_SOZLUGU.csv` — 120 göstergenin adları ve grupları.
- `02_SAAT_SAAT_120_METRIK.csv` — 72×18 saat × 120 metrik.
- `03_1296_SAAT_ZAMAN_CIZELGESI.csv` — Çekiliş aralığı, kimlikler, gece boşlukları.
- `04_KOK_AILELER_TUM_SAATLER.csv` — Tam aile kimlikleri, destek sayısı, ilk/son çekiliş.
- `05_AILE_SOY_PARÇALANMA_BIRLESME.csv` — Önceki saatten yeni saate yakın aile dönüşümleri, kopan/katılan sayılar.
- `06_AILE_CIFTLERI_AYNI_CEKILISTE.csv` — Çekiliş numarası ve saati olan doğrulanmış buluşmalar.
- `07_HANGI_AILE_KIMLE_COK_BULUSTU.csv` — Buluşma çiftlerinin sıralaması.
- `08_ADIL_RNG_SAATLIK_BEKLENTI.csv` — Koşullu rastgele beklenti ve gözlenen buluşma.
- `09_GUN_GUN_72_OZET.csv` — Gün bazında sonuç.
- `10_SQLITE_KONTROL_NOKTASI_KUTUK.csv` — Günleri işleyen parçaların kontrol kaydı.
- `11_METOD_KONTROL_VE_LIMITLER.txt` — Eksik veri, sınırlar, çoklu karşılaştırma uyarıları.

## Gerçeklik sınırı

Aileler sayısal kümelerdir; **ayrılıp birleşme**, sayı kümesi ilişkisidir, RNG'nin fiziksel davranışı veya gelecekteki çekilişin tahmin edilebilir olduğunu kanıtlamaz. İleriye dönük, önceden sabitlenmiş yöntemle üstünlük görülmeden kupon önerisi çıkarılmamalıdır.
