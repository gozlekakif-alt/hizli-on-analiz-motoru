# V26 — Sıcak + Soğuk + Yeni Aktif Karma 10'lu Kupon Motoru

**Tamamlandı, GitHub Actions başarılı:** [V26 başarılı çalışma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38479388576).
**Veri:** GitHub `veri.txt` blob SHA `86458dbe058a322d828b76913868fe29b648a600`. 72 tam gün, 15.624 gerçek çekiliş, 1.296 adet ilk6→son6 saat penceresi. İlk 36 gün öğrenme, sonraki 36 gün ayrılmış test (648 saat, 3.888 ayrı hedef çekiliş, her yöntem için saatte tek 10'lu kupon).

## Başlangıç anında kesin tanımlar

- **Sıcak:** Saatin ilk **6** çekilişinde en az **3 kez** görülen sayı.
- **Soğuk:** Aynı ilk **6** çekilişte **hiç görünmeyen** sayı.
- **Yeni aktive olan:** İlk **3** çekilişte hiç yokken sonraki **3** çekilişte en az bir kez görülen. Çok hızlı aktive olup altı içinde üç görünüme ulaşan sayı varsa sıcak sınıfa ayrılır; havuzlar çakışmaz.
- Üretilen 10'lu kuponlar: `Karma433` (4 sıcak/3 soğuk/3 yeni), `Karma334` (3/3/4), `Karma343` (3/4/3), `AileKarma433` (4/3/3, aile çekirdeklerinin ilk/ikinci/üçüncü+ evresi ve önceki eşlikçilerle sırala). V25 kontrol kuponları: AileDNA, Sıcak10, Soğuk10, Rastgele10, İlk6Havuz10.
- Kuponlar **6. çekiliş tamamlandıktan sonra** dondurulur. 7,8,9,10,11,12. çekilişlerin hiçbir sayısı kurala giriş değildir. 01:02–07:02 altı saatlik duraklama korunur; 01:02 ayrıca gece tek çekilişidir.
- 72 günün **1.296 saatinin tamamında** üç karma kota da doldurulabildi, kategori doldurma açığı sıfır. Ortalama havuz: 13,62 sıcak, 14,25 soğuk, 18,97 yeni aktif sayı; geriye kalan 33,16 başka sayı.

## Son 36 günün 10'lu kupon sonuçları

Her yöntemde **648 kupon × 6 çekiliş = 3.888** gerçek hedef.

| Model | Ortalama isabet/10 | 5+ | 6+ | 7+ | 8+ | 10/10 |
|---|---:|---:|---:|---:|---:|---:|
| Karma433 | 2,5013 | 260 | 50 | 7 | 0 | 0 |
| Karma334 | 2,4985 | 245 | 58 | 5 | 0 | 0 |
| **Karma343** | **2,5139** | **270** | **65** | **10** | 0 | 0 |
| **AileKarma433 (ilk 36 gün eğitim galibi)** | 2,4895 | 245 | 56 | 7 | 0 | 0 |
| V25 AileDNA | 2,5131 | 257 | 49 | 7 | 0 | 0 |
| Sıcak10 | 2,5129 | 257 | 56 | 7 | 1 | 0 |
| Soğuk10 | 2,5123 | 253 | 47 | 7 | 0 | 0 |
| Rastgele10 | 2,5005 | 253 | 54 | 10 | 1 | 0 |
| İlk6Havuz10 | 2,4861 | 258 | 53 | 7 | 0 | 0 |

**Model seçimi gerçek zaman kilidi:** İlk 36 günde karma modellerin toplam isabetleri Karma433 9.687, Karma334 9.706, Karma343 9.745, AileKarma433 **9.768** idi. Bu nedenle **AileKarma433** ilk 36 günden hareketle seçildi. Sonraki 36 günde bu model rastgele 10'lu kupondan ortalama **0,0111 sayı daha kötü** çıktı (2,4895 vs 2,5005). Gün bazında kümelenmiş yaklaşık %95 güven aralığı fark için [-0,0586; +0,0365] sayı/çekiliş. 5+ oran farkı güven aralığı da sıfırı kapsıyor. **Önceden seçilmiş model için üstünlük kanıtı yok.**

**Karma343'ün 65 adet 6+ sonucu dikkat çekiyor**, rastgele kuponda 54 adet. Ancak Karma343 ilk 36 günde seçilmiş birincil model **değildi**; son testte hangi modelin daha iyi çıktığına sonradan bakılarak ayrıca 'kazanan' seçilemez. Karma343 – rastgele 6+ çekiliş oran farkı +0,00283, gün bazında yaklaşık %95 aralık [-0,00248; +0,00813]; fark sıfırı kapsıyor. Ortalama isabet farkı +0,01337, yaklaşık %95 aralık [-0,04488; +0,07163]. Bu yüzden %6+/6+ isabet avantajı **kanıtlanmadı**. Karma343 gelecekte değiştirilmeden sınanmak üzere bir aday olarak korunabilir.

## Bilimsel sınırlar

- Bu çalışma kazanma garantisi veya RNG algoritmasının açığını bulduğunu göstermez. Sıcak/soğuk/yeni aktif sınıflar geçmiş 6 çekilişi tanımlar, bağımsız çekilişte sonra daha yüksek çıkma olasılığı anlamına gelmez.
- Tek hedefte 10 sayılık kuponun teorik ortalama doğru sayısı **2,5**'tir. Sonuçlar bu beklentiye yakındır.
- 6+ ve 7+ isabetler seyrek, birçok kupon ve zaman penceresi birbiriyle ilişkili. Gün-kümeli güven aralığı ve rastgele kontrol zorunlu; son testten sonradan model seçimi ile isabet şişirilmemelidir.
- 36 gün sonuçlarına göre model geliştirildiyse, sonraki gerçek canlı günlerde modeli değiştirmeden ileri test gerekir.

## Dosyalar

- [V26 analiz motoru](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v26_karma_kupon.py)
- [V26 no-leak ve kategori testleri](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v26_selftest.py)
- [V26 Streamlit sekmesi](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v26_family_app.py) — `v10_app.py` içine **🔀 V26 Karma Sıcak Soğuk** sekmesi ekli.
- [V26 başarılı GitHub Actions çalışması](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38479388576)
- [V26 GitHub rapor ZIP'i](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38479388576/artifacts/11856372814)

ZIP içerisinde 7 rapor: `ozet.json`, `72_gun_6li_saat_sicak_soguk_yeni_havuzlar.csv`, `72_gun_kuponlar_ve_tum_0_10_isabetler.csv`, `ilk36_karma_model_secimi.csv`, `son36_0_10_isabet_ozeti.csv`, `son36_gunluk_eslesik_guven_araligi.csv`, `adil_rng_10lu_kupon_isabet_dagilimi.csv`.

Önceki V9–V25 kaynakları ve `veri.txt` değiştirilmemiştir.
