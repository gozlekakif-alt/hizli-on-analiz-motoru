# V27 — Eski sıcaklık hafızası ve yeni 6 basamakta 20 koltuğun kaynakları

**Durum:** Başarılı GitHub otomatik çalışması: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38521774261

**Tarih:** 14 Ekim 2026. **Kaynak:** `veri.txt`; 72 tam gün, 15.624 hedef çekiliş. Ek 366 geçerli kayıt (eksik günler) yalnızca geçmiş bağlamı olabilir; tamamlanmamış günler bağımsız 217 çekilişlik test günü değildir. Geçmiş gözlem indeksi toplam 15.990 geçerli kayıttır.

## Gerçek tarihsel modelin kaynağı

GitHub'da bulunan **V13** `v13_havuz_koltuk.py` 3 sıcaklık sınıfı (**Soğuk, Ilık, Sıcak**) ve gün başında **Erken** veri sınıfını kullanır. GitHub kod aramasında `Soğuğa yakın` ve `Sıcağa yakın` isimli önceden tanımlanmış eski **altı basamaklı** motor bulunmadı.

Eski sohbet çalışmasında ayrıca **12 çekiliş yarı ömürlü, günler arasında taşınan, gece sıfırlanmayan, sıralı 4×20 sıcaklık havuzu** (**S / OD / OY / YS**) kullanılmıştı. V27 bunu **ayrı gerçek tarihsel referans** olarak yeniden oluşturur. Altı yeni basamağı 'eski altı modelin aynısı' diye tanıtmak doğru olmaz.

## Yeni deneysel altı basamak tanımı

80 sayıyı yalnız HEDEF ÖNCESİ geçmiş frekans veya 12 çekiliş yarı ömürlü sınırlı frekansla sıralayıp:
- En alt **13**: Soğuk.
- Sonraki **13**: Soğuğa yakın.
- Sonraki **14**: Orta.
- Sonraki **14**: Ilık.
- Sonraki **13**: Sıcağa yakın.
- En üst **13**: Sıcak.

Her grupta 'Düşen' / 'Dengeli' / 'Yükselen' yönü, bilinen son altı çekiliş ile önceki altı çekiliş frekans farkının sırasıyla ≤-2 / -1..+1 / ≥+2 olmasına göre eklenir. Böylece **18 durum hücresi** vardır; ancak bazı düşük sıcaklık-yüksek ivme hücreleri fiilen boş olabilir. Tek çekilişteki 20 'koltuk', hangi kategoriden kaç sayı geldiğidir; yayımlanan sayıların fiziksel çekiliş sırasına dair kanıt değildir.

## Geriye kaç çekiliş? Denenen pencereler

**6, 12, 24, 36, 72, 144, 217, 434, 868, 1519 gerçek çekiliş** × **Frekans / 12 çekiliş yarı ömürlü skor**. Toplam 20 önceden tanımlanmış aday.

- İlk **18 tam gün** yalnızca 18 sıcaklık × yön hücresinin gerçekleşme oranlarını kalibre eder (%25 prior ile yumuşatma).
- Sonraki **18 tam gün** hangi pencere ve skorun daha iyi olduğunu, hedefteki 80 sayı için **Brier hata** ile seçer.
- **Son 36 tam gün** seçim ve katsayı değiştirilmeden kör dönemi test eder. **7812 ayrı hedef 20'li çekiliş**.

**Doğrulama döneminin seçimi:** `12 gerçek çekiliş geçmişi + 12 çekiliş yarı ömrü`.

## Son 36 gün: 20 tahmin koltuğu ve 20 sayı isabeti

| Ölçüt | V27 seçilen altı-ısı motoru | Rastgele/sabit RNG referansı |
|---|---:|---:|
| Ortalama 20 sayılık tahminde bilinen sayı | **5,0168** | **5,0211** rastgele 20 |
| Teorik 20'lik kupon doğru sayısı | — | **5,0000** |
| Olasılık Brier hatası (küçük daha iyi) | **0,187508345** | **0,187500000** |
| Koltuk tahmini ortalama mutlak hata | RNG tam-kota ile **aynı** | RNG 20 tam-koltuk |

Brier avantajı yaklaşık %95 gün-kümeli aralıkta **negatif**. 20'li isabet farkı = -0,00435 sayı/hedef; yaklaşık %95 gün-kümeli aralık **[-0,05975; +0,05105]**; sıfırı kapsıyor. **Kanıtlanmış tahmin avantajı YOK.**

**Kritik adil karşılaştırma:** Koltuk kotası altı kategorinin her biri için tam sayı ve toplam 20 olacak şekilde hem model hem RNG referansında aynı 'largest remainder' ile yuvarlandı. Eski ara sürümün model tam-sayı/RNG kesirli-koltuk karşılaştırması yanlıştı; düzeltildikten sonra V27 ile RNG koltuk bütçesi eşit başarı gösterdi.

## 20 gerçek sayının altı gruptan geldiği ortalama koltuk sayısı

| Altı ısı grubu | Her hedefte 80 havuz içinden grup sayısı | Son 36 gün gerçek ortalama koltuk | RNG beklenen |
|---|---:|---:|---:|
| Soğuk | 13 | 3,2309 | 3,25 |
| Soğuğa yakın | 13 | 3,2606 | 3,25 |
| Orta | 14 | 3,5157 | 3,50 |
| Ilık | 14 | 3,4967 | 3,50 |
| Sıcağa yakın | 13 | 3,2276 | 3,25 |
| Sıcak | 13 | 3,2684 | 3,25 |

Bütün satırlar 20 koltuğu tamamlar. Tüm sıcaklık kategorilerinde oranlar **yaklaşık %25** ve matematiksel rastgele dağılıma yakın.

### Gerçek eski 4×20 hafıza — ayrı test

Tüm geçmiş geçerli çekilişlerden taşınan **yarı ömür 12** sıcaklık sıralaması:

| Eski sıcaklık havuzu | Son 36 gün hedef20 içinde ortalama koltuk | RNG beklenen |
|---|---:|---:|
| S | 4,9974 | 5,0000 |
| OD | 4,9823 | 5,0000 |
| OY | 5,0073 | 5,0000 |
| YS | 5,0129 | 5,0000 |

Eski modelin **koltuk dağılımı** bu veri kümesinde teorik 5+5+5+5'e çok yakın. Bu tek başına 20 sayının kimliğini tahmin etmeyi kolaylaştırmaz. Önceden seçilmiş 20 sayı sonuçları ek sınamalarda şans seviyesine yakındır.

## Dosyalar

- [V27 altı-ısı motoru](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v27_alti_isi_koltuk.py)
- [V27 test dosyası](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v27_selftest.py)
- [V27 Streamlit arayüzü](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v27_heat_app.py) — V10 içinde **🌡️ V27 Koltuk Isı Hafızası** sekmesi.
- [V27 başarılı otomatik çalışma ve ZIP](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38521774261)
- [V27 GitHub arşivi](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38521774261/artifacts/11874192982)

ZIP içinde yedi rapor: `ozet.json`, `tum_pencereler_dogrulama_ve_test.csv`, `son36_20_koltuk_hedef_hedef.csv`, `son36_18_isi_ve_yon_hucresi.csv`, `son36_eski_dort_20li_koltuk.csv`, `son36_gun_gun_performans.csv`, `son36_guven_araligi.csv`.

Önceki motorlara ve `veri.txt` kaynak dosyasına dokunulmadı. **Altı kategori orijinal eşikler keşfedilirse model yeni sürümde ayrıca aslına uygun uygulanmalıdır.**
