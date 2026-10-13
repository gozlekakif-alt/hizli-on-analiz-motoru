# V24 — İlk Tam Görünüşten İkinci Çıkışın Önceden Seçilmesi

**Durum:** Çalışma ve veri sızıntısı testleri başarılı. [GitHub Actions doğrulaması](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38473569916).

**Veri:** `veri.txt` (SHA `86458dbe058a322d828b76913868fe29b648a600`), 72 tam gün, 15.624 gerçek çekiliş, 1 Ağustos–12 Ekim 2026. İlk 36 gün öğrenme, sonraki 36 gün test.

## Önceden kayıtlı deney kuralı

- Her saat 00:02 veya 07:02–23:02 başlangıcındaki **ilk çekiliş tamamlandıktan hemen sonra**, o 20'li kadronun içinden daha önce aynı gün **hiç tam çıkmamış** 2–10'lu aile seçilir. Böylece seçilen kadronun **birinci tam çıkışı biliniyor**, ikinci henüz bilinmiyor.
- Seçim yalnız o ana kadar görülen çekilişlere dayanır: sıcak geçmiş sayı frekansı, soğuk geçmiş sayı frekansı, küçük sıralı sayılar; eşit boyutta rasgele seçilen yeni aile kontrol olarak hesaplanır. 2–4'lü aday aile listesi eksiksiz taranır. 5–10'luda sıralı bir sezgisel seçim uygulanır.
- Seçim dondurulduktan sonra sırasıyla **+1**, **+2–3**, **+4–6**, **+7–11** çekiliş aralıkları; ayrıca gün sonuna kadar herhangi bir ikinci tam çıkış izlenir. Her aile tipi için bir saatte tek aile seçilir.
- 01:02 ekstra gerçek çekiliş, 01:02→07:02 arasındaki altı saatlik boşluk ve 217 toplam çekiliş korunur. Çekiliş sırası farkı ile gerçek dakika farkı ayrı tutulur.
- İkinci çıkışın beklenen olasılığı, her bağımsız çekiliş için `(20)_k/(80)_k`; sonraki 11 çekilişte en az bir tekrar için `1-(1-p_k)^11`. Bağımsız RNG varsayımı altında geçmiş frekans avantaj yaratmaz.
- Yöntem seçimi için **yalnız ilk 36 günlük** etiketler kullanıldı. Son 36 günün hedefleri, yöntem seçimini ve aile seçimini etkilemedi.

## Son 36 gün (bağımsız dönem / geçmişe dönük kör test)

| Aile boyutu | Tahmin (saat) | Sonraki 11 çekilişte ikinci tam çıktı | Eş boyutta rastgele yeni ailede çıktı | RNG matematik beklentisi |
|---|---:|---:|---:|---:|
| 2'li | 281 | 141 | 140 | 138,94 |
| 3'lü | 648 | 90 | 90 | 92,32 |
| 4'lü | 648 | 26 | 27 | 21,50 |
| 5'li | 648 | 5 | 2 | 4,58 |
| 6'lı | 648 | 0 | 1 | 0,92 |
| 7'li | 648 | 0 | 0 | 0,17 |
| 8'li | 648 | 0 | 0 | 0,031 |
| 9'lu | 648 | 0 | 0 | 0,005 |
| 10'lu | 648 | 0 | 0 | 0,0008 |

**Neden 2'li 281 tahmin?** Gün ilerledikçe 80 sayı içindeki 3160 olası ikilinin tamamı görülmüş olabilir. Saatin ilk çekilişinde o gün ilk kez çıkmış yeni ikili bulunamazsa hayali ilk çıkış sinyali yaratılmaz.

**2'li:** 141/281 = %50,18; rastgele 140/281 = %49,82. **3'lü:** 90/648 = %13,89; rastgele 90/648. **4'lü:** 26/648 = %4,01; rastgele 27/648 = %4,17. Gün bazında yaklaşık %95 güven aralıklarında model–rastgele farklar sıfırı kapsıyor. 5'li +3 görünümlük fark da çok küçük sayılardadır, istatistiksel üstünlük kanıtı değildir. 6–10'lu ailelerin on bir çekilişte ikinci tam görünüşü çok nadirdir; gün sonu profili ZIP'tedir.

## Sonuç

**İlk çıkışı yakalayıp ikinci çıkışını önceden izlemek başarıyla uygulanmıştır.** Ancak mevcut sıcak/soğuk/sıra stratejilerinin geleceği rasgele kontrolden **güvenilir biçimde daha iyi tahmin ettiğine dair kanıt bulunmamıştır**. Bu bir 6/6 veya 10/10 kupon isabet çalışması değil; tek tek seçilen ailelerin ikinci tam çıkış sınamasıdır. Aynı modelin hiç değişmeden **yeni tarihlerde** canlı sınanması ayrıca gereklidir.

## Dosyalar

- [V24 motoru](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v24_aile_ikinci_ongoru.py)
- [V24 doğrulama testleri](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v24_selftest.py)
- [V24 Streamlit sekmesi](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v24_family_app.py) (V10 arayüzünde **🌾 V24 Aile İkinci Çıkış Tahmini**)
- [Başarılı GitHub çalışma ve ZIP](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38473569916)
- [ZIP artifact](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38473569916/artifacts/11853032221)

ZIP beş dosya içerir: `ozet.json`, `ilk36_yontem_egitim.csv`, `son36_basari_ve_rastgele_kontrol.csv`, `son36_gun_bazli_guven_araliklari.csv`, `tum72_gun_saatlik_aile_ilkden_ikinciye.csv`.

Kaynak `veri.txt` ve önceki V9–V23 araştırma/kupon motorları değiştirilmedi.
