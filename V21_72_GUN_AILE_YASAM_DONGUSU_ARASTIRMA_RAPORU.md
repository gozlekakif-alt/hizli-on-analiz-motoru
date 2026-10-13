# V21 — 72 Tam Gün / 2–10'lu Aile Yaşam Döngüsü

Tarih: 13.10.2026. Kaynak: `veri.txt`; veri blob SHA `86458dbe058a322d828b76913868fe29b648a600`.

## Doğrulama

- GitHub Actions **başarılı**: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38466827294
- 72 tam gün (2026-08-01—2026-10-12), 15.624 çekiliş ve 1.296 tam 12-çekilişlik saat incelendi.
- 23.08.2026'da iki **bozuk** satır var: 50924'te 19 sayı, 50936'da tekrar eden 79. Bu gün 215 geçerli çekiliş içerdiğinden tam gün testine alınmadı. 13 Ekim kaynağın o anki sürümünde 151 çekilişle tamamlanmamıştı.
- Saat: 00:02–00:57 12 çekiliş, 01:02 tek çekiliş, 01:02→07:02 çekilişsiz gerçek 6 saat, 07:02–23:57 17x12 çekiliş. Aile çıkış sırası yayınlanmadığından fiziksel top çekme sırası **bilinmiyor**.

## Gün içinde en az 2 defa birlikte çıkan **farklı aileler**

| Boyut | 72 gün boyunca gün-aile toplamı | Gün başına ortalama | Herhangi bir günün aynı aile için en yüksek tam çıkışı |
|---|---:|---:|---:|
| 2 | 227.513 | 3.159,9 | 31 |
| 3 | 4.759.970 | 66.110,7 | 15 |
| 4 | 16.337.966 | 226.916,2 | 11 |
| 5 | 15.404.905 | 213.957,0 | 6 |
| 6 | 8.300.145 | 115.279,8 | 5 |
| 7 | 3.193.440 | 44.353,3 | 4 |
| 8 | 928.461 | 12.895,3 | 3 |
| 9 | 206.761 | 2.871,7 | 3 |
| 10 | 35.293 | 490,2 | 2 |

**Dikkat:** Bu toplamlar tüm 72 günde birbirinden farklı ailelerin sayısı değildir. Aynı aile iki farklı günde yinelenmişse iki gün-aile kaydı olarak yer alır. Dahası 20'lik iki çekiliş 14 sayı paylaştığında `C(14,10)=1001` adet **10'lu tekrar eden aile** bir kerede oluşabilir. Büyük sayılar tek başına bir RNG açığı veya kupon avantajı anlamına gelmez.

## Aynı çekirdeğin çevresi değişiyor

- 01–05 çekirdeği V10 katalogundaki 62 farklı 5–10'lu ailede bulunuyor.
- 01–13 çekirdeği 58 ailede, 01–02 çekirdeği 48 ailede bulunuyor.
- 01.08.2026 günü 42–50 çekirdeği 26 kez birlikte çıkıp 26 farklı dış 18'li kadro ile görüldü. Aynı gün 5 sayısı bu çekirdeğe 11 kez eşlik etti. Eşlikçi seçimi gün sonu sonuçlarından yapılmıştır ve tahmin değildir.
- Günlük raporlar 2, 3 ve 4'lü merkez çekirdekler için ilk/son saat, saatlik yoğunluk, çekiliş arası ve **gerçek dakika** farkı, değişen çevreler, en sık 10 eşlikçiyi içerir.

## Kayıtlı V10 katalogundan ayrı sonuçlar

| Boyut | Katalog adedi | 72 günlük tam aile görünüşü |
|---|---:|---:|
| 5 | 300 | 5.490 |
| 6 | 198 | 1.220 |
| 7 | 151 | 523 |
| 8 | 279 | 850 |
| 9 | 9 | 27 |
| 10 | 194 | 576 |

Kayıtlı 194 adet 10'lu ailenin hiçbirinin 72 tam günlük havuzda **aynı gün içerisinde iki tam çıkışı** yoktu. Yukarıdaki tabloda 10'lu aileler için bulunan 35.293 gün-aile **aynı aile kataloğu değildir**; bunlar hedef sonuçlar görüldükten sonra keşfedilmiş, gün içinde yinelenen tüm farklı 10'lu alt kümelerdir. Bu seçilim önemli farktır.

## İlk 6 → son 6 bağımsız dönem testi

İlk 36 gün öğrenme, sonraki 36 gün test ayrıldı. Her tam 12'lik saat, yalnız **ilk altı çekilişte** en sık tam görünen çekirdek ile sabitlendi. Takip eden 6 çekilişte **tam aile isabeti** sayıldı. Her boyut için 648 saat × 6 = 3.888 hedef.

| Boyut | Son 36 günde tam isabet | Matematiksel RNG beklentisi | Aynı boyutta rastgele aile |
|---|---:|---:|---:|
| 2 | 232 | 233,77 | 218 |
| 3 | 48 | 53,95 | 53 |
| 4 | 15 | 11,91 | 14 |

Görülen farklar tek başına güvenilir üstünlük kanıtlamıyor. Bu **kupon 6/6–10/10** testi değil; tek sabit 2'li, 3'lü veya 4'lü ailenin sonraki çekilişte **tam birlikte çıkması** testidir. Modellerin sınama dönemiyle bağımsız sayılabilmesi için kuralın gelecek veri öncesinde değişmeden sabitlenmesi gerekir.

## Kod, arayüz ve tüm dosyalar

- [V21 analiz motoru](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v21_aile_yasam_dongusu.py)
- [V21 Streamlit ekranı](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v21_family_app.py) — `v10_app.py` içindeki yeni **🌳 V21 Aile Yaşam Döngüsü** sekmesinden açılır.
- [V21 doğrulama testleri](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v21_selftest.py)
- [V21 GitHub Actions çalışma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38466827294) — 72 günlük ZIP analiz raporu indirilebilir.
- ZIP içerikleri: `ozet.json`, `gun_boyut_ozetleri.csv`, `gunluk_en_cok_tekrarlanan_aileler.csv`, `cekirdek_ve_degisen_cevreler.csv`, `kayitli_1131_aile_tam_gecmis.csv`, `kayitli_ailelerin_ortak_cekirdekleri.csv`, `ilk6_son6_ongoru_denekleri.csv`, `ilk6_son6_kor_test_ozeti.csv`.

Kaynak `veri.txt`, V9–V18 modülleri, kuponlar ve kalıcı kayıtlar değiştirilmedi.
