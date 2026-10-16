# V105 — 56 Halkanın Tam Yön Etki Atlası

**Tarih:** 16 Ekim 2026  
**Durum:** Gerçek veri ile başarıyla çalıştırıldı. **V104'ün 72 gün başlangıcından itibaren yürüyen 672/FIFO halka omurgası değiştirilmedi.**  
**Kod:** [v105_tam56_halka_yon_etkisi_sonraki_halke.py](v105_tam56_halka_yon_etkisi_sonraki_halke.py)  
**Başarılı çalışma:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38914611736  
**11 raporlu ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38914611736/artifacts/12051932728

## Kullanıcı sorusu

"56 halkalık uzun yolculuk sayının sonraki halkada hangi yöne hareket edeceğini nasıl etkiliyor? Aynı son 6 halkalık görünüşe sahip sayıların eski 50 halkadaki yolu önemli mi?"

Burada **kupon sayısı, 20 sayılık isabet optimizasyonu ve dışarıdan üretilmiş sayı tahminleri yoktur.** İlişki yalnızca son 72 çekilişlik **göreli 5 sıcaklık havuzu** ve bir sonraki **tam 12 çekilişlik halkada** bu havuz üyeliğinin yükselmesi/düşmesi/sabit kalması arasında incelendi.

## Kesin veri kapsamı

- Başlangıç **1 Ağustos 2026 00:02 #46005**, bitiş **12 Ekim 2026 23:57 #61845**; **72 tam gün, 15.624 çekiliş**.
- İlk 672 gözlem 56 sabit 12'li halka; V104 bütün dönem boyunca **14.952 tek-çekilişlik FIFO kaydırmayı** gerçekleştirdi.
- V105, sonraki tam halkanın başlangıcında **1.246 tam 12'li sınır** inceledi; bu sınırların tamamında 80 sayının 56 halkalık yön geçmişi dondurulup **99.680 sayı×halka geçişinin** bir sonraki gözlenen yönü etiketlendi.
- Ortalama sonraki halka hareketi: **20,372 ısınan, 20,448 soğuyan, 39,180 sabit** sayı.
- Başlangıçta 72 çekiliş birikmeden açılmış ilk beş halkanın sıcaklık sıralaması yalnız mevcut 12/24/36/48/60 çekilişlik veriyle kurulmuş başlangıç referansıdır; 72 dolduktan sonraki halka sıralamaları son 72 gözleme dayanır.

## 55 geçmiş hareketin her birinin sonraki yönle ilişkisi

**Yöntem:** Aynı sayının son havuz etiketi ve son altı halkadaki net hareket yönü sabit tutularak daha eski her yön adımının sonraki yönle korelasyonu hesaplandı. İlk 36 tam gün ve son 36 tam gün ayrı ayrı incelendi. Korelasyonlar **tanımlayıcı ilişkilerdir**, nedensel halka etkisi değildir.

| Kaç halka önceki yön? | İlk 36 gün ilişki | Son 36 gün ilişki |
|---|---:|---:|
| 1 | −0,00779 | −0,00908 |
| 2 | +0,06217 | +0,06411 |
| 3 | +0,06494 | +0,06247 |
| **6** | **−0,26977** | **−0,27183** |
| 12 | +0,00065 | +0,00050 |
| 24 | −0,00979 | −0,00462 |
| 36 | +0,00544 | −0,00480 |
| 48 | −0,00138 | +0,00766 |
| 55 | −0,00371 | +0,00459 |

**Önemli matematiksel uyarı:** 6 halka önceki yön, aynı analizde sabit tuttuğumuz **son altı halkanın net değişiminden türetilir**. Bu nedenle lag 6'daki −0,27 ilişki bir "gizli güçlü sinyal" değildir; değişkenlerin kısmen aynı verilerden oluşmasının sonucudur.

Özellikle 12–55 halka gecikmelerinin **ortalama mutlak koşullu korelasyonu** ilk yarıda **0,00414**, son yarıda **0,00282** gibi küçük değerler verdi. Her bir eski halka aynı kuvvette sonraki yönü etkilemiyor; uzak geçmişte tutarlı yön ilişkisi görülmedi.

## Son altı halka mı, bütün 56 mı?

**Kıyaslanan olay:** Bir sonraki **tamamlanmış halka sonunda** sayının göreli sıcaklık havuzunun **soğuma/sabit/ısınma** durumu. İlk 36 günün koşullu sıklıklarıyla başlayan hesap son 36 günde incelendi. Bu sayıların **lotoda çıkıp çıkmaması** değil, **havuz yönünü sınıflama hatasıdır** (3 sınıflı Brier; küçük değer daha iyi).

| Açıklayıcı tarih | Son 36 gün hata |
|---|---:|
| Son havuz + son altı halkanın net yönü | 0,57190943 |
| + Bütün 56 halkada toplam havuz değiştirme sayısı | 0,57204245 |
| + Bütün 56 halkada toplam yön dönüş sayısı | 0,57186746 |
| + Son havuz değiştirmeden beri kaç tam halka geçtiği | **0,57013572** |

**Net bulgu:** Son hareketin "kaç halka önce olduğu" bir miktar faydalı ek tanımlayıcı bilgi sağladı; fakat bütün 56 halkada kaç kez yükselip düştüğü tek başına faydayı artırmadı. Hata farkları küçüktür; tekrarlanan tarihsel veride görünüyor ve şimdiden ileri tarih sayı tahmini sağladığı iddia edilemez.

**Önemli metodolojik sınır:** Bütün hareket, son 72 frekansının göreli sırasından çıkıyor. SICAK havuzdaki bir sayı daha yüksek sınıfa çıkamaz; SOĞUK havuzdaki daha aşağı inemez. Sayılar havuz etiketlerini 16'şarlı sınıflarda paylaştığı için tüm sayıların yönleri birbirine bağımlıdır; bunları "RNG çözüldü" şeklinde yorumlamamalıyız.

## Önceki V104'teki bazı büyük grup farklarını kontrol etme

V104'te "SERİN ve son6 SABİT" gibi belirli küçük örneklerde 56 halkalık geçmişe göre %11'e varan farklılık görülmüştü. V105 tüm **1.246** tam halka sınırını kullanıp bu grupları ilk ve son 36 gün ayrı ölçtü.

**Serin, son altıda SABİT:**
- Az hareket: ilk 36 gün **%37,09 (364 durum)** → son 36 gün **%42,94 (340)**.
- Orta hareket: **%35,03 (1.379)** → **%37,23 (1.617)**.
- Çok hareket: **%38,04 (184)** → **%32,24 (152)**.

Farklı dönemlerde sınıfların sıralaması ve büyüklüğü değiştiği için önceki en büyük farkı geleceğe dönük kural ilan edemeyiz.

**Serin, son altıda SOĞUMA:**
- Az hareket: **%36,88 (1.044)** → **%35,54 (996)**.
- Orta hareket: **%36,66 (4.146)** → **%38,20 (4.699)**.
- Çok hareket: **%39,42 (449)** → **%39,18 (485)**.

Bütün 56 halkayı saklamak uzun hareket profilini ve farklı dönemlerdeki oranları görmemizi sağlar. Ama **kalıcı etkisini sayısal olarak göstermediğimiz hiçbir eski halka davranışını kesin yön tahmini olarak kullanmıyoruz**.

## V105 ZIP içindeki 11 dosya

1. `00_56_HALKA_YON_ETKI_KESIN_SONUC.txt`
2. `01_HER_12_TAM_HALKADA_80_SAYI_56_ZINCIR_GELECEK_YON.csv`
3. `02_55_ESKI_HALKANIN_GELECEK_YONLE_ILISKISI.csv`
4. `03_5_HAVUZ_SON_ADIM_GELECEK_YON_MATRISI.csv`
5. `04_56_HALKA_HAREKET_AZ_ORTA_COK_DONEM_KARSILASTIRMA.csv`
6. `05_AYNI_HAVUZ_SON6_56_ZINCIR_IKI_DONEM.csv`
7. `06_SON_TAM_HALKADA_80_SAYI_YON_FILMI.csv`
8. `07_HER_12_TAM_HALKADA_GENEL_YON_KADRO.csv`
9. `08_ILK36_OGREN_SON36_YON_KALIBRASYON.csv`
10. `09_SON36_GUNLUK_YON_KALIBRASYON.csv`
11. `10_METOT_DENETIM.json`

### Bundan sonraki soru

56 halkayı **aynı şekilde korumaya devam ediyoruz.** Ancak yalnızca hareket sayısı yerine eski halkada ne kadar süre soğuk/sıcak kaldığı ve hareketin **hangi uzaklıkta başladığı** gibi daha özgül yol biçimlerinin farklı dönemlerde tekrar edip etmediğine bakabiliriz. Bu, geçmişteki ilişkileri gözlemleme aşamasıdır; tahmin üstünlüğü iddiası değildir.
