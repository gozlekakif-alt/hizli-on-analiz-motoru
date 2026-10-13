# V23 — Ailelerin Gün İçindeki İlk ve İkinci Tam Çıkışı

**Gerçek veri:** GitHub `veri.txt` blob SHA `86458dbe058a322d828b76913868fe29b648a600`.

**Kesinleşmiş test:** [GitHub Actions V23 — success](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38470916607). 72 tam gün, **15.624 çekiliş**, 2–10'lu aileler. `v23_selftest.py` doğrulaması geçti. [İndirilebilir 9 dosyalı tam ZIP](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38470916607/artifacts/11852697017). 

## 72 gün boyunca ilk iki görünüşü bulunan bütün aileler

Bu **gün-aile** sayısıdır. Aynı sayılardan oluşan aile farklı günlerde ayrıca sayılır. Aynı iki çekiliş yüzlerce ya da binlerce iç içe aile doğurabilir.

| Boyut | En az 2 tam çıkışı olan gün-aile | İlk iki aynı saatte | İlk iki farklı saatte | İlk ikiden sonra aynı gün üçüncü tam çıkış |
|---|---:|---:|---:|---:|
| 2'li | 227.513 | 67.255 | 160.258 | 227.483 |
| 3'lü | 4.759.970 | 418.675 | 4.341.295 | 3.433.823 |
| 4'lü | 16.337.966 | 928.461 | 15.409.505 | 3.392.359 |
| 5'li | 15.404.905 | 803.969 | 14.600.936 | 704.555 |
| 6'lı | 8.300.145 | 426.963 | 7.873.182 | 76.379 |
| 7'li | 3.193.440 | 164.431 | 3.029.009 | 5.479 |
| 8'li | 928.461 | 47.824 | 880.637 | 279 |
| 9'lu | 206.761 | 10.432 | 196.329 | 9 |
| 10'lu | 35.293 | 1.631 | 33.662 | 0 |

**Önemli:** Tek tam çıkışlı ailelerin milyonlarca olası alt kümesi topluca saklanmadı. İstenen aile `V23 Aile İlk İki Tam Çıkış` sekmesinden gün gün doğrudan taranır; bir kez geldiyse ikinci yok diye doğru gösterilir. Kayıtlı 1.131 aile **ilk-only** örnekleriyle de ayrı CSV içindedir.

## Gerçek saat ve çevre örnekleri

- **05.10.2026, 19–20–23**: ilk **13:22** #60199, ikinci **18:32** #60261, aralarında **62 gerçek çekiliş / 310 dakika**; üçüncü **23:42** #60323, ikinciye 62 çekiliş mesafede. Bu, geçmişten seçilmiş bir örnektir; ileri tahmin garantisi değildir.
- **01.10.2026, 31–45**: ilk **01:02** #59254, ikinci **07:02** #59255. **1 çekiliş farkı ama 360 dakika**. Aynı şekilde 37–45 ailesi de ilk iki kez bu sıralarda göründü.
- **01.10.2026, 19–20–23**: o gün yalnız **22:12** #59437 çekilişinde tam görüldü; ikinci tam çıkış **yok**.
- **01.08.2026, 42–50**: günlük 26 birlikte çıkış; ilk **00:02**, ikinci **08:12** — 27 çekiliş / 490 dakika; üçüncü **08:17**.
- **01.08.2026, 01–03–10–25–33–56–61–63–69–71 (10'lu)**: ilk **11:57**, ikinci **16:27**, 54 çekiliş / 270 dakika; üçüncü tam çıkış o gün **yok**.

## Neler ölçüldü?

1. Her tekrar eden 2–10'lu ailenin o günkü **gerçek ilk ve ikinci tam birlikte çıkışı**, hangi çekilişte, hangi saatte, kaç çekiliş ve kaç **gerçek dakika** arayla oluştuğu.
2. İlk iki görünüş aynı saat mi farklı saat mi; hangi saatten hangisine geçtiği; saatlik ilk ve ikinci doğum yoğunluğu.
3. 01:02–07:02 çekilişsiz arayı **360 dakika** sayma, fakat çekiliş sırasına **sahte kayıt eklememe**.
4. İlk iki görünüşe kadar çekirdek çevresindeki ortak ve ayrılan sayılar; seçilen ailelerin üçüncü tam çıkışı.
5. Gün-gün ve tüm 72 gün toplu istatistik; kayıtlı **1.131 aile** için tam günlük ilk, ikinci, üçüncü ve 72 gün boyunca kronolojik ilk/ikinci olay.

## Kaynak dosyalar

- [V23 Python motoru](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v23_aile_ilk_iki_tamgun.py)
- [V23 Streamlit arayüzü](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v23_family_app.py) — V10 uygulamasındaki yeni **🔎 V23 Aile İlk İki Tam Çıkış** sekmesi
- [V23 doğrulama testleri](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v23_selftest.py)
- [1.131 kayıtlı ailenin 72 günlük ilk/ikinci olayları CSV](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/V23_1131_KAYITLI_AILE_72_GUN_ILK_IKI_GORUNUS.csv)
- [V23 72 günlük ZIP dosyası GitHub artifact](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38470916607/artifacts/11852697017)

ZIP içindeki 9 dosya: `ozet.json`, `72_gun_boyut_ilk_iki_ozeti.csv`, `72_gun_ilk_ikinci_gap_dagilimi.csv`, `72_gun_saat_saat_birinci_ikinci.csv`, `72_gun_saatten_saate_aile_gecisleri.csv`, `72_gun_aile_ilk_iki_gercek_ornekler.csv`, `1131_katalog_aile_gunluk_ilk_ikinci.csv`, `1131_katalog_aile_72_gun_ilk_ikinci.csv`, `tum_boyutlar_toplam.csv`.

## Dürüst yorum

Bunlar geçmiş çekilişlerden hesaplanan doğru frekans ve zaman izleridir. **İlk iki tam çıkışı bulmak bir gözlem, ikinci veya üçüncü çıkışın gelecekteki zamanını önceden tutturmak farklı ve istatistiksel olarak henüz kanıtlanmamış bir konudur.** Gelecek hedefler yalnızca daha önceki çekilişlerden oluşturulan modellerle, bağımsız rastgele kontrole karşı test edilmelidir.

23.08.2026'da 20 sayıyı sağlamayan iki kayıt (satır 5783, 5797) ve 13.10.2026 kaynağın o andaki sürümünde tam olmayan gün olduğundan tam-gün araştırmasına katılmadı. Hatalı sayı **uydurulmadı**.
