# V96 — Beş Havuz Geçişleriyle Bir Sonraki Çekilişi Önceden Tahmin Etme Kör Testi

**Tarih:** 16 Ekim 2026  
**Durum:** GitHub Actions başarıyla tamamlandı.  
**Çalıştırma:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38885774140  
**Kod:** [v96_bes_havuz_gecis_sonraki_cekilis_kor_test.py](v96_bes_havuz_gecis_sonraki_cekilis_kor_test.py)

## Kurgu
- 72 tam gün, **15.624 çekiliş**, 1–80 arası her çekilişte 20 farklı sayı.
- İlk 36 gün model eğitimi; sonraki 18 gün model seçimi; son 18 gün (**3.906 çekiliş**) modelin sabit tutulduğu geçmişe dönük kronolojik kör test.
- Her çekilişten **önce** 10 sayı seçildi; yalnızca önceki çekilişler kullanıldı.
- V95 ile aynı son 72 çekilişin frekansına göre 5 × 16'lık havuz. Geçiş yönü son 12 ve 24 havuz durumundan çıkarıldı.
- Öğrenilen dört seçenek: POOL5, POOL_DIR15, POOL_DIR_AGE45, POOL_DIR_MOMENTUM45. Kazanan yalnız doğrulamada belirlendi: **POOL_DIR15**.
- Basit HOT72/HOT24/COLD72 ve sabit tohumla rastgele 10 sayı karşılaştırmaları yapıldı.

## 18 gün / 3.906 çekiliş son test

| Yöntem | 10'lu kupon isabet ortalaması | 5+ | 6+ | 7+ | 8+ | 9+ | 10/10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| RANDOM10 (tek rastgele örnek) | 2,441372 | 206 | 47 | 4 | 0 | 0 | 0 |
| HOT72 | **2,523554** | 255 | 64 | 5 | 0 | 0 | 0 |
| HOT24 | 2,506656 | 263 | 47 | 8 | 1 | 0 | 0 |
| COLD72 | 2,462110 | 207 | 52 | 6 | 1 | 1 | 0 |
| **POOL_DIR15 — önceden seçilmiş V96 motoru** | **2,520225** | 240 | 61 | 7 | 0 | 0 | 0 |

**Bağımsız adil 20/80 oyunu için 10 sayılık kuponun teorik isabet ortalaması tam 2,5'tir.**
Rastgele tek kupon serisinin 2,441 çıkması kuramsal beklentiyi değiştirmez.

POOL_DIR15'in HOT72'ye karşı günlük bloklar üzerinden yaklaşık %95 güven aralığı **[-0,0500, +0,0434] isabet/çekiliş**; güvenilir bir üstünlük göstermiyor. V96 seçilen kuponlar için en iyi sonuç 7/10; 8+, 9+, 10/10 hiç yok. 
HOT24 ve COLD72 üzerinde bulunan tekil 8+ / 9+ sonuçları **sonradan gözlenen farklı modellerin seçilmesi için kanıt değildir**.

## Karar
**V96 geçiş modeli için gerçek isabet artışı doğrulanmadı.** Beş havuza giriş/çıkış tek başına sonraki çekilişi bildiğimizi göstermiyor; sabit kazanan model zaten HOT72'yi geçemedi. Modelin kupon motorunda doğrulanmış bir avantaj sunduğu iddia edilmemeli.

Sınırlar:
1. Veri seti önceki sürümlerde çok defa incelendiğinden bu kronolojik bölüm dışarıdan bakıldığında tamamen el değmemiş, ileriye dönük prospektif test değildir.
2. Gün bazlı yaklaşık güven aralığı çoklu geçmiş araştırmaları düzeltmez.
3. Havuzlar son 72 çekilişin sıralamasından elde edilir. Hareket etmeleri, RNG'de zorunlu dengeleme döngüsü olduğu anlamına gelmez.

## Devam koşulu
Önümüzdeki **yeni** çekilişler başlamadan tarih-saat damgalı ve değiştirilemez 10 sayı tahminleri kaydedilmeli. En az birkaç hafta toplanan yeni verilerde rastgele teorik 2,5 ve önceden belirlenmiş HOT72 referansını anlamlı ve tekrarlanabilir biçimde geçmedikçe V96 kupon motoruna otomatik eklenmemeli.

**Geçici GitHub Actions ZIP arşivi:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38885774140/artifacts/12038903405  
**Kalıcı olanlar:** bu kütük ve sürüm kodu. ZIP GitHub Actions saklama süresine tabidir.
