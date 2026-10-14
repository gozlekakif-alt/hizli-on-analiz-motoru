# V34 — 8 çekiliş bekleyen + soğuk + V32 döngüsünde henüz görülmemiş

**14 Ekim 2026** · GitHub `veri.txt` · 72 tam gün (15.624 çekiliş). İlk 36 gün keşif, son 36 gün zaman sıralı test. Kaynak: `v34_bekleme_isi_v32_kesisim.py`.

## Önceden belirlenen ana karşılaştırma

**Kural:** Tam 8 gerçek çekiliştir çıkmamış bir sayı; mevcut çekiliş SONRASI V28 altılı ısı sınıfında `SOGUK`, V32 çıkan20 80/80 döngüsünde `DONGUDE_HENUZ_GORULMEDI`. Hedef: bir sonraki gerçek çekilişte çıkması. Karşı grup: 8 çekiliş bekleyen diğer bütün sayılar.

| Son 36 test günü | Riskli sayı-kesit olayı | Sonraki 20'de çıktı | Oran |
|---|---:|---:|---:|
| 8 bekleyen + soğuk + V32 henüz görülmemiş | 3.230 | 804 | %24,8916 |
| Diğer 8 çekiliş bekleyenler | 12.071 | 3.071 | %25,4411 |
| Bağımsız 20/80 RNG | — | — | %25 |

Fark **−0,549 yüzde puanı**. 2.000 tekrarlı, birim olarak tam günleri koruyan bootstrap yaklaşık %95 aralığı **[−2,556; +1,322] yüzde puanı**. Sıfır dahil. Bağımsız 20/80 üzerinden üstünlük görünmüyor. Bu, tanımlayıcı ve tekrarlı geçmiş araştırmasıdır; prospektif bağımsız bir doğrulama değildir.

## Derin havuzlar

V34 veri kaydında 6,7,8,9,10,11+ bekleme × V28 6 sıcaklık sınıfı × V32 80/80 döngüsünde görülmüş/görülmemiş × sekiz onluk bant birleştirildi. Her kombinasyon için gerçek ertesi çekiliş sayısı / toplam uygun gözlem ve temel %25 kaydedildi. 216.733 gelecek-çekiliş risk kaydı; 30.554 tam 8 bekleme kaydı. Günlük tekrar örnekleme seri bağımlılığı kısmen hesaba katar.

## Eğitimde iyi görünen grupların sonraki günlerde değişmesi

- `9_ILIK_GORULDU` ilk yarıda %29,33 (225 olay), testte %25,00 (212).
- `10_ORTA_GORULDU` ilk yarıda %27,67 (318), testte %21,67 (323).
- `9_ORTA_HENUZ` ilk yarıda %22,74 (730), testte %26,43 (700).

Bu farklılıklar sinyal seçimi ve geriye dönük örneklemlerde görünen zirvelerin kalıcı olmayabileceğini gösterir. Geçmiş testte farklar görmek tek başına avantaj kanıtı değildir.

## Kod ve dosyalar

- `v34_bekleme_isi_v32_kesisim.py` — çapraz analiz, eğitim/test, gün-blok yaklaşık aralık.
- `v34_bekleme_app.py` — V10 Streamlit uygulamasındaki yeni V34 sekmesi.
- `v34_selftest.py` — kaynak kesit özelliklerinin gelecek sonuçtan etkilenmediğini test eder.
- `v34_export_zip.py` — tek ZIP oluşturur.
- `.github/workflows/v34-check.yml` — otomatik test/ZIP. Başarılı çalışma: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38555580321

**21 dosyalı tek ZIP:** 12 V33 tablosu + 9 V34 ileri çapraz rapor. GitHub Artifacts bölümünden alınır. Yeni `veri.txt` güncellemelerinde rapor otomatik yeniden oluşur.

**Yorum:** Bu sınıf tahmin motoruna doğrudan “yüksek öncelikli” kural olarak eklenmemeli. Sonraki araştırmada güçlü görünen farklı sinyaller, yalnız önceden belirlenen kuralla ve yeni gelecekteki veriler üzerinde tekrar sınanmalıdır.
