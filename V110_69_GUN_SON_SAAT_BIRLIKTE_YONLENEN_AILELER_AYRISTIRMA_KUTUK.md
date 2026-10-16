# V110 — Aynı 56 halkada beraber yön değiştiren sayı aileleri (gün sonu)

**Tarih:** 16 Ekim 2026. **Gerçek analiz yapıldı.** Kaynak: V104'ün 72 gün başlangıcından beri yürüyen **672 çekilişlik FIFO / 56 sabit 12'li halka** verisinin, V108'de dondurulan 69 adet **23:02–23:57 tam hedef saat** için 80 sayılık ısı/yön DNA ve H1–H12 kayıtları. Burada V104/V105/V108/V109 mantığı değiştirilmedi.

**Kaynak CSV:** V108 sonuçları içinde `V108_69_GUN_SON_SAAT_80_SAYI_TAM_HALKA_DNA.csv`. V108 kütüğü: [V108](V108_72GUN_GUNUN_SON_SAATI_56_HALKA_YON_KUTUK.md).

## Nasıl ayrıştırıldı?

**Hedef saat başlamadan**, her sayı için 55/56 tamamlanmış 12 çekilişlik sabit halka dizisinin en son **2, 3, 4, 6 yön adımı** incelendi. Aynı zamanda **aynı son 72 çekilişlik göreli sıcaklık havuzunda** bulunan ve söz konusu yön adımlarında **birebir aynı Y/D/= dizisini** izleyen en az 2 sayı **yön ailesi** kabul edildi. Her yönü eşit/sabit `===` aileleri ayrıca işaretlendi. **H1–H6 gerçekleşene dek** hiçbir hedef saati sonucu bu aileleri oluşturmada kullanılmadı; H7–H12 daha sonra sonuç etiketi.

| Aynı yönde son kaç halka adımı | 69 gün içindeki aile-gün adetleri | Aileye katılan sayı-saat |
|---|---:|---:|
| 2 | **1.516** | 4.886 |
| 3 | **1.238** | 3.226 |
| 4 | **779** | 1.909 |
| 6 | **261** | 574 |

*Aile-gün*: farklı günlerde aynı grup tekrar görülürse her tarih ayrı sayılır; bunlar 1.238 kalıcı, birbirinden bağımsız sayı ailesi demek değildir.

## 12 Ekim son saatindeki örnekler

Aynı havuzda, **son üç tam halka yön adımında aynı** davranışı izleyen sayılardan:

| Havuz | Ortak yön (eskiden yeniye) | Aile | 12 çekilişte tek tek geliş |
|---|---|---|---|
| **SERİN** | Y–D–Y | **2 ve 47** | **2: 2 kez, 47: 8 kez** |
| **ILIK** | =–Y–= | **40 ve 41** | **40: 3 kez, 41: 6 kez** |
| **NÖTR** | =–D–= | **15 ve 56** | **15: 6 kez, 56: 3 kez** |
| **ILIK** | =–D–= | **33, 52 ve 61** | **33: 5, 52: 5, 61: 3 kez** |

Burada **aynı yolun aynı hedef sonucu üretmediği** doğrudan görülüyor: 2 ve 47 birebir aynı son üç yön adımını izlemişken biri iki, öbürü sekiz kez çıktı.

## İlk altı çekiliş etkisini tutunca ne oldu?

İlk **34 tam son saat** frekans öğrenme; sonraki **35 tam son saat** karşılaştırma. H7–H12'de tek bir sayının **0–6 geliş sayısı** tahmininin 7 sınıflı Brier hatası ölçüldü. **Düşük hata daha iyi.** Aynı bilgi havuzları ve ilk altıda gerçek kaç kez geldiği sabitlenerek aile büyüklüğünün ek faydası arandı.

| Bilgi | Son 35 gün H7–H12 hata |
|---|---:|
| **İlk 6 çekilişte kaç kez geldiği** | **0,73446436** |
| Basit binom(6,%25) | 0,73507669 |
| İlk 6 + son sıcaklık havuzu + son altı halka yönü | 0,73569705 |
| Yukarıdakiler + son **2 halka** aynı aile büyüklüğü | 0,73679525 |
| Yukarıdakiler + son **3 halka** aynı aile büyüklüğü | 0,73700471 |
| Yukarıdakiler + son **4 halka** aynı aile büyüklüğü | 0,73744815 |
| Yukarıdakiler + son **6 halka** aynı aile büyüklüğü | 0,73762578 |

**Bu ayrımda yön ailesi büyüklüğünü eklemek H7–H12 geliş sayısını daha iyi belirlemedi.** Hepsi basit ilk-altı sayımından biraz daha kötü. Bu, 56 halkada geçmiş ortak yön ilişkilerini izlemeyi anlamsız yapmaz, fakat güvenilir sayısal isabet üstünlüğü göstermez.

### Aynı çekilişte birlikte gelme

Aynı **son sıcaklık, son altı halka net yönü, ilk altı çekilişte geliş adedi** eşit olan sayı çiftleri seçildi. İki sayının H7–H12'de **aynı çekilişte eşzamanlı gelme sayısı**, ikisinin ayrı ayrı H7–H12'de kaç kez göründüğü sabit tutularak beklenen eşleşmeyle karşılaştırıldı. Son **3 halka** birebir aynı yön hareketine sahip çiftlerle, buna sahip olmayan benzer çiftler arasındaki **son 35 günün 34 karşılaştırılabilir gününde** ortalama eşzamanlı ekstra fark **+0,0508 ortak çekiliş/çift**. Gün bazlı yaklaşık %95 belirsizlik aralığı **−0,0335 ile +0,1351**; **sıfırı içeriyor**. Eşzamanlı görülme üstünlüğü gösterilmiş değil.

### İlk 6'da aynı geliş adedinden örnek alt gruplar (son 35 gün)

| Son 6 halka net yönü | İlk 6'da | Son 3 halka aynı yön ailesi | n | Son altı ort. geliş | Tüm saatte 6+ |
|---|---:|---|---:|---:|---:|
| Isınan | 3 | Tek/ailesiz | 39 | 1,436 | %15,38 |
| Isınan | 3 | 2–3 kişilik | 66 | 1,591 | %15,15 |
| Soğuyan | 3 | Tek/ailesiz | 73 | 1,274 | %9,59 |
| Soğuyan | 3 | 2–3 kişilik | 74 | 1,514 | %18,92 |

Bunlar yalnız **ilk6 ve genel yönü** eşitledi; tüm havuzları satır bazında eşitlememiş alt grup gösterimleri olduğu için bunlardan otomatik bir kural çıkarılmamalı. Havuz ve yön birlikte eşitlenmiş değerlendirmenin sonucu tabloda görünüyor.

## Çalışma dosyaları

`V110_69_GUN_GUNSONU_BIRLIKTE_YON_AILELERI.zip` içindeki **11 rapor**:

1. `00_V110_AYNI_YON_AILELERI_KISA_SONUC.txt`
2. `01_69_GUN_23_SAAT_FAMILIES_2_3_4_6.csv`: her saat ve ortak halka adımında aile üyeleri ve gerçek sonuç
3. `02_69_GUN_3_HALKA_BIRLIKTE_HAREKET_UYELERI.csv`: her sayı adı, 56 ısı halkası, önce/sonra ilk6
4. `03_SON35_H7_H12_YON_AILE_EK_ETKI.csv`: asıl koşullu tahmin hataları
5. `04_SON35_GUNLUK_YON_AILE_HATA_FARKLARI.csv`
6. `05_HER_GUN_YON_AILE_ES_ZAMANLI_CIKIS_CIFTLERI.csv`
7. `06_SON35_AYNI_SAAT_AYNI_K1-6_CIFTLER_KARSILASTIRMA.csv`
8. `07_ILK6_3_4_ESIT_AILE_BUYUKLUKLERI.csv`
9. `08_69_GUN_GUNSONU_BIRLIKTE_YON_GUNLUK_OZET.csv`
10. `09_TUM_5520_SAYI_SAAT_ZINCIR_AILE_BOYUTLARI.csv`
11. `10_METOT_ZAMAN_IZLEME.json`.

## Karar

**56 halka sistemi aynen korunuyor.** Birlikte yönlenen aileleri, en son 2/3/4/6 halkanın tamamında sayılara göre tek tek görebiliyoruz. Fakat **aynı yönde hareket ediyorlar** cümlesi **aynı çekilişte veya aynı saatte birlikte 5–8 kez çıkacaklar** anlamına gelmiyor. V110 bunu ilk altı çekiliş ve havuz etkisinden ayırdı. Eski 69 gün farklı çalışmalarımızda daha önce incelendiği için **gerçek ileri dönem doğrulaması** için bu tanımları değiştirmeden yeni saatlerin gerçekleşen sonuçlarına ihtiyaç vardır.
