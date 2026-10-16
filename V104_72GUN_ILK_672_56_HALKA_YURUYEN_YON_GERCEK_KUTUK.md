# V104 — 72 günün başından 672 çekilişlik 56 halkanın tek tek yürütülmesi

**Çalışma tamamlandı.** Bu analiz V100C ve V102'yi bozmaz; kullanıcı isteği üzerine mekanizma **72 günlük havuzun ilk çekilişinden itibaren** tekrar kurulmuş ve 672 veri dolduktan sonra **her yeni çekilişle bir adım ilerletilmiştir.**

**Başarılı gerçek-veri GitHub Actions koşusu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38912727917  
**Çalışan kod:** [v104_72gun_basindan_672_56_halka_fifo_yon.py](v104_72gun_basindan_672_56_halka_fifo_yon.py)  
**11 dosyalı ZIP sonuçları:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38912727917/artifacts/12050902791

## Kurulum ve yürüyüş

- Kaynaktan yalnızca **72 tam günlük 15.624 gerçek çekiliş** alındı (1 Ağustos–12 Ekim 2026, eksik günler uydurulmadı).
- İlk çekiliş **#46005, 1 Ağustos 00:02**, son çekiliş **#61845, 12 Ekim 23:57**.
- İlk **672 çekiliş**, ilk 56 sabit **12'li halka** olarak kuruldu. Başlangıçta kümülatif havuzda 72 çekiliş dolmadan gelen 5 halkanın 72'lik göreli sıcaklık değerlendirmesi **geçici başlangıç sınıflaması**dır; 72'den sonra tüm halka uçları geriye dönük son72 ile değerlendirilir.
- İlk hedef çekiliş **#46677 (4 Ağustos 07:42)**.
- **14.952 kez tek çekiliş ileri yürüdü**. Her yeni çekiliş eski hafızadan bir kaydı çıkardı; yeni kaydı ekledi; halka kimlikleri **yeniden bölünmedi**.
- **1.246 yeni tam halka kapanışı**, **1.301 toplam ardışık tarihsel tam halka geçişi**.
- Halka sınırında **56 tam halka**, arada **55 tam halka + en eski ve en yeni iki kısmi halka**, toplam **672 kayıt**.
- **1.235 tam hedef saatin** her birinin ilk çekilişinden **önceki** tüm 80 sayının son 55–56 tam halkalık sıcaklık yolu, hareket yön dizisi, hedef saatin H1–H12 gerçek sonuçları ve sonraki tamamlanacak halkanın gerçek yönü etiketlendi.

## 56 halkada aynı yönde mi gidiyorlar?

**Hayır.** Gerçek 1.301 tam halka geçişinin ortalaması:

| Bir önceki tam halkaya göre hareket | Ortalama 80 sayı içinden |
|---|---:|
| Isınan | **20,369** |
| Soğuyan | **20,430** |
| Havuz değiştirmeyen | **39,201** |

- Bir halkada ısınan sayı sayısı **12–28**, soğuyan sayı sayısı **13–29** aralığında gözlendi.
- Bir sayının ardışık iki halka adımında aynı yön sınıfını tekrar etmesi (**sabit-sabit dahil**) **%38,858**.
- Beş havuz her halka sonunda tam **16+16+16+16+16** sayıya sahip olduğundan 80 sayının sıcaklık sırası toplamı sabittir; tüm 80 sayı birden aynı anda yukarı veya aşağı gidemez.
- Asıl araştırma için her sayının **tam 55 yön adımı (Y: ısınma; D: soğuma; =: sabit)**, yön dönüşleri ve toplam hareket sayısı baştan sona kaydedildi.

## Son altı halkanın gördüğünden fazlası: aynı kısa sinyal, farklı 56'lık geçmiş

Bir sonraki tamamlanmış halkada **ısınma sıklığı**, son sıcaklık havuzu ve son6 hareket yönü sabitken, bütün 56 halkadaki toplam hareket sayısına göre bazen farklılaşıyor.

**Örnek 1: Son havuz SERİN, son6 halkada yön SABİT**
- Bütün 56 halkada **az hareketli** (0–24 değişim): **60 gözlem → sonraki halkada %45,00 ısınma**.
- Bütün 56 halkada **orta hareketli** (25–34 değişim): **259 gözlem → sonraki halkada %33,59 ısınma**.
- Gözlenen fark **11,41 yüzde puan**.

**Örnek 2: Son havuz SERİN, son6 halkada SOĞUMA**
- Bütün 56 halkada **orta hareketli:** **752 gözlem → sonraki halkada %36,04 ısınma**.
- Bütün 56 halkada **çok hareketli** (35+ değişim): **87 gözlem → sonraki halkada %47,13 ısınma**.
- Gözlenen fark **11,09 yüzde puan**.

Bu oranlar **geçmişe dönük koşullu sayımlardır**, *öngörü avantajı* olduğu henüz söylenemez. Özellikle küçük sayıda gözlem ve birçok grup karşılaştırması olası farkları abartabilir. Ayrıca SICAK havuzdaki bir sayının bir sonraki adımda daha da ısınma yüzdesi **%0** olmak zorundadır: 4/4 zaten en üst basamaktır. Mekanik sınırlar ayrıca ayrılmalıdır.

**Ancak artık asıl kullanıcı sorusunu ölçebiliriz:** Son6 yönü aynı görünen iki sayının **56 halkalık önceki ısınma/soğuma yoğunluğu ve dönüş zinciri** değiştiğinde sonraki halka yönünün geçmişte nasıl farklılaştığını tek tek görebiliyoruz.

## ZIP içindeki 11 rapor

1. `00_YURUYEN_672_56_HALKA_YON_KESIN_SONUC.txt`
2. `01_72GUN_BASTAN_SONA_HER_CEKILIS_BIR_ADIM_FIFO.csv` — **14.953** durum kaydı (ilk dolu durum dahil, **14.952 ilerleme**).
3. `02_ILK_672_80_SAYI_56_HALKA_YON_DNA.csv` — ilk 56 halkada 80 sayı.
4. `03_SON_672_80_SAYI_56_HALKA_YON_DNA.csv` — son 56 halkada 80 sayı.
5. `04_HER_TAMAMLANAN_12_HALKA_YON_HAREKETI.csv` — 1.301 tam halka geçişinde ısınan, soğuyan, sabit sayılar ve ardışık hareket tekrarı.
6. `05_HEDEF_SAAT_80_SAYI_TAM56_YON_VE_GERCEK12.csv` — **1.235 hedef saat × 80 sayı**, 55–56 halka dizisi, gerçek 12 el, sonraki tam halkanın yönü.
7. `06_TUM_GELECEK_HALKA_YONLERI_80_SAYI.csv` — tam halkaların bir sonraki tam halkaya geçişindeki yön kadroları.
8. `07_SON6_VE_TAM56_GECIS_DAGILIMI.csv` — son6 yön + son sıcaklık + **tam56 geçmiş hareket seviyesi** sabitlenerek sonraki halka yönleri.
9. `08_YALNIZ_SON6_GECIS_DAGILIMI.csv` — karşılaştırma için yalnız son6 + son sıcaklık yönleri.
10. `09_TAM56_AZ_ORTA_COK_HAREKET_FARKLARI.csv` — tarihsel farklılıklar.
11. `10_YONTEM_VERI_ZAMAN_DENETIM.json`.

**Kritik ayrım:** Kullanıcı artık 56 halkayı ilk günden yürütülmüş görmek istiyor. V104'te kupon veya kör test amaçlanmadı; geçmiş 56 halkalık tam hareket zinciriyle **sonraki halkanın yönü** birlikte kayıtlı. 56 halkalık tarihsel sınıflamaların sonraki yönleri iyileştirip iyileştirmediği için yeni veriyle daha sonra ayrıca test gerekir.
