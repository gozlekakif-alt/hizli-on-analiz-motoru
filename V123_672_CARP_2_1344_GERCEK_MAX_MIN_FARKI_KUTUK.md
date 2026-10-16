# V123 — Son 672 ile iki katı 1.344 çekiliş: 80 sayının gerçek min–max farkı

**Gerçek GitHub Actions koşusu (başarılı):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38974008603

**80 sayılık tam ZIP verisi:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38974008603/artifacts/12078555857

**Çalışan tekrar kullanılabilir analiz kodu:** [v123_672_iki_kat_1344_minmax_80_sayi.py](v123_672_iki_kat_1344_minmax_80_sayi.py)

## Kesin gerçek sayımlar

Kaynak GitHub `veri.txt` 15.790 gözlenen sonuç, son çekiliş **#62014, 13.10.2026 19:57**. Son 1.344 çekiliş #60668 (07.10.2026 16:17) ile #62014 arası gözlenmiş sonuçlardır; aradaki eksik zamanlar uydurulmaz. İkiye bölünmüş son 672 gözlemin ilk çekilişi #61340 (10.10.2026 18:02).

| Gerçek referans | 80 sayı toplam çıkışı | Sayı başına beklenen | En çok çıkan | En az çıkan | Max−min farkı |
|---|---:|---:|---|---|---:|
| İlk/önceki 672 | 13.440 | 168 | 54 numara 190 | 33 numara 139 | **51** |
| İkinci/son 672 | 13.440 | 168 | 64 numara 191 | 37 numara 146 | **45** |
| İkisinin birleşimi 1.344 | 26.880 | 336 | **8 numara 365** | **37 numara 297** | **68** |

Eski son 672 havuzuna göre fark **45→68** oldu; mutlak artış +23, **1,5111 kat**. İkiyle çarpılınca 90 olacağı varsayımı YANLIŞTIR: birleşik pencerenin maksimum ve minimum sayıları farklı olabilir. Sayı başına beklenen ortalama **168→336**. Sıcak uçtaki sayı 64'ten 8'e değişti. 37 numara son672'nin ve birleşik1344'ün en düşüğüdür. Önceki672'nin min 33, max54'tür.

Ek olarak en büyük fark/ortalama oranı son672 için 45/168 ≈ **%26,79**, son1344 için 68/336 ≈ **%20,24** oldu. Bu yalnız dağılım betimlemesidir; 1/0 RNG tahmin avantajı değildir.

### Denetim

- Son 672 gerçek çekilişte **64=191**, **37=146** önceki V117 bilgisiyle doğrulandı.
- 672×20 = 13.440; 1344×20=26.880 gerçek sayım olarak denetlendi.
- Birleşik1344'ün tüm 80 sayısı için görüldüğü sayı, önceki672 + son672'nin aynı sayı değerindeki çıkışlarının toplamıdır.
- Arşivde `01_KARSILASTIRMA_672x2_1344.json` ve `02_80_SAYI_672_672_1344.csv` bulunuyor.

**Yorum:** Mutlak sıcak-soğuk uç farkı pencere büyüdüğünde artabilir; buna karşın ortalamaya oranla daha küçük kalabilir. Sıralamanın değişmesi kendi başına çekilişlerin rastgele olmadığı veya gelecekte şans avantajı olduğu anlamına gelmez.