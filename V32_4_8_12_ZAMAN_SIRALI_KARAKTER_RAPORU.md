# V32 — 4., 8. ve 12. çekilişlerde 80/80 döngü karakterinin denetlenmesi

**Tarih:** 14 Ekim 2026. **Kaynak:** GitHub `veri.txt`; 72 tam gün, 15.624 gerçek çekiliş. Eksik 2 gün varsayılan rapora alınmaz. 80/80 tamamlanmış 842 ÇIKAN_20 döngüsü ve 3.743 ÇIKMAYAN_60 döngüsü.

## Yöntem

- Her gün 00:02 yeni döngü; gün içinde ilgili 80 sayı tamamlandıktan sonraki gerçek çekilişte ilgili havuzun sayacı yeniden 0/80.
- 01:02 → 07:02 saat boşluğu sahte çekiliş üretmez.
- Her açık döngü için adım 4/8/12 kesitlerinde yalnızca o anda bilinen farklı sayı sayısı, son 2/4 adımın ilk kez gelenleri, 8 onluk banttaki görülmeyen sayılar, hız farkı ve eksik sayı kimlikleri kullanılır.
- Hedefler mevcut döngünün bir sonraki 1, 4, 8, 12 gerçek çekilişte tamamlanıp tamamlanmamasıdır.
- Sonuçlanmadan veri biterse test sansürlenir; olumsuz sonuç gibi yazılmaz.
- Referans olasılıkları, bağımsız 20/80 örnekleme ve 60/80 tamamlayıcısı için tam hipergeometrik durum geçişleriyle hesaplanır.
- Tam günlerin ilk 36'sı **EGITIM**, sonraki 36'sı **TEST** olarak ayrılır. Bu sürümde `EGITIM`, sadece keşif dönemi etiketidir: rastgele temeli aşan bir modelin öğrenilip kanıtlandığı iddia edilmez.

## İleri tarihteki 36 test gününün çıkan 20 sonuçları

| Bilinen kesit | Önümüzdeki çekiliş | Değerlendirilen durum | Gerçekte 80/80 | RNG beklentisi | Fark (yüzde puanı) |
|---|---:|---:|---:|---:|---:|
| 4 | 12 | 426 | %41,08 | %43,76 | −2,68 |
| 8 | 8 | 426 | %41,08 | %42,95 | −1,87 |
| 12 | 4 | 402 | %37,56 | %39,32 | −1,75 |

Bu farkların hiçbiri gözlenen veride öngörü üstünlüğünü göstermiyor. 4. çekilişte hızlı / orta / yavaş diye sınıflandırılan döngülerde gerçek 12-çekiliş kapanma oranları sırasıyla %43,86 / %41,46 / %37,81; ancak daha fazla farklı sayı görmek RNG altında bile gelecekte daha yüksek kapanma olasılığı üretir. Aynı grupların **RNG beklentileri** %49,87 / %44,06 / %38,43'tür. Ham sıralama tek başına RNG'yi çözme kanıtı değildir.

## Yeni GitHub dosyaları

- `v32_ileri_karakter.py`: geçmişe bakmayan kesitler ve olasılık karşılaştırması.
- `v32_ileri_selftest.py`: aynı 4 çekilişin üzerine iki farklı geleceği koyup **geleceğin kesit özelliklerini değiştirmediğini** doğrulayan test.
- `v32_80_tamamlama_app.py`: Streamlit V32 sekmesinde tek ZIP.
- `v32_export_zip.py`: GitHub Actions otomatik tek ZIP üretimi.
- `.github/workflows/v32-check.yml`: her kaynak/veri değişikliğinde test ve indirilebilir artefakt.

ZIP: 11 önceki V32 dosyası + 6 yeni dosya = **17 dosya**. GitHub Actions kontrolü başarıyla tamamlandı.

**Sonuç:** Döngü tamamlanmasını öngörmek ile hangi sayıların geleceğini tahmin etmek farklı hedeflerdir. Henüz rastgele seçime göre üstün kupon isabeti kanıtlanmadı. Sonraki araştırma, her sayı ve bant için önceden tanımlanmış sinyalleri yeni günlerde ve kupon bazında sınamaktır.
