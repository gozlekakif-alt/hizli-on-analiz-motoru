# V111.2 — 56 Halkalık Tam Yön Zincirinden En Az Kuponla Gerçek İsabet Analizi

**16 Ekim 2026 — GitHub Actions SUCCESS:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38934525783

**Kod:** [v111_56_halka_tam_yon_zinciri_az_kupon_karsilastir.py](v111_56_halka_tam_yon_zinciri_az_kupon_karsilastir.py)  
**9 dosyalı karşılaştırma ZIP'i:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38934525783/artifacts/12060630742

## Neden bunu yaptık?

V100C–V110 boyunca kullanıcının istediği 672 çekilişlik FIFO dev halka, 55/56 tam kapalı 12'li halka, sayı başına soğuk→serin→nötr→ılık→sıcak statüleri ve tüm halkaların yön dizisi korunur. V111 ilk defa **kupon başına 10/10 isabet dahil gerçek sonraki tek çekiliş** ölçüsünü karşılaştırır. **Bir hedef saatin 1.–6. çekilişi gerçekten göründükten sonra**, 7.–12. çekilişlerin her birinin öncesinde **tek 10'lu**, ayrıca aynı sıralamanın ilk 5, 6 ve 8 sayısını içeren daha küçük adaylar üretir. İlk altı bilinir, gelecek çekiliş bilinmez.

## Veri, zaman ve model

- Kaynak: 1 Ağustos–12 Ekim 2026 **72 tam gün** ve 13 Ekim 2026 19:57 #62014'e kadar depo ekleri, toplam **15.790 kayıt**.
- Doğrulanmış **1.246 tam hedef saat** (HH:02–HH:57). İlk36 gün model için **281.760 sayı-çekiliş eğitim örneği**, sonra kronolojik orta18 (**1.944 tek çekiliş**), son18 (**1.944**) ve 13 Ekim ek veri (**66**) çıktı.
- Her çizilen yeni çekiliş 672 FIFO gözleme eklenir, en eskisi çıkar; halka kimliği yeniden kurulmaz. Son **55/56 tam halkadaki** zaman sıralı sıcaklık havuzları ve **54/55 yön adımları** tahmin sürecinde gerçekten kullanılır. Daha önce kullanılan özet son6 ayrı bir taban motordur.
- **Tam56 modeli:** Hedef öncesi kısa yakın frekans ve ilk6 görünümü + 56 halka sıcaklık dizi konumu + 55 önceki yön adımı, sabit güçte Ridge (alpha 1500). Karşısında **son6 kısa modeli**, **son72 sıcak frekans**, **ilk6 tekrarı**, **rastgele kupon**.
- Her yöntemin **aynı gerçek sonraki çekilişte** 5,6,8,10 sayı seçimi ve 0...10 isabet dağılımı raporlandı. Dış kaynak gelecek sonucu kullanarak sayı optimize edilmedi. Geçmiş 72 gün önce de çok araştırıldı, bu tekrar analizi yeni bağımsız kanıt değildir.

## Son 36 gün: Her yönteme 3.888 eşit çekiliş, 1 kupon / çekiliş

### 10 sayılık kupon

| Yöntem | Ortalama 10'lu isabeti | 5+ | 6+ | 7+ | 10/10 |
|---|---:|---:|---:|---:|---:|
| Rastgele kontrol | 2,4897 | 248 | 50 | 4 | 0 |
| Sıcak son72 | **2,5008** | 270 | **61** | **8** | 0 |
| Hedef saatin ilk6 görünümü | 2,5023 | 279 | 54 | 5 | 0 |
| Son6 halka kısaltılmış motor | 2,4761 | 245 | 49 | 9 | 0 |
| **Tam56 sıra+direksiyon motoru** | **2,5008** | **276** | 45 | 1 | 0 |

**Sonuç:** Tam56 yöntemi 10'lu ortalama isabetinde son72 basit yöntemiyle eşit çıktı. 5+ sonuç biraz fazla ama 6+,7+ da belirgin daha az. **Güvenilir 10/10 üstünlüğü gösterilemedi.** Rastgele 10/10 tek kupon şansı modelde **0,0000112212%**; 3.888 örnekte sıfır olması şaşırtıcı değil.

### Aynı 3.888 çekilişte daha kısa kuponlar — tam isabet

| Yöntem | 5/5 | 6/6 | 8/8 |
|---|---:|---:|---:|
| Rastgele | 3 | **3** | 0 |
| Sıcak72 | 2 | 0 | 0 |
| İlk6 saat tekrarı | 2 | 0 | 0 |
| Son6 kısa motor | 3 | 1 | 0 |
| **Tam56 halka** | **7** | 2 | 0 |

5/5 sonucu Tam56 için **ilk 18 günde 3**, son 18 günde **4** olaydır. Ancak yalnız dört hane kadar biletin çok düşük sayılı tam isabet farkında **şans, yöntem çokluğu, model araştırması geçmişi ve örnekler arası bağımlılık** nedeniyle garanti bir avantajdan söz edilemez. Rastgele 5/5 kuponu beklenen oranı `C(20,5)/C(80,5)=0,0006449247`; 3.888 bilet için beklenen ortalama **2,51**. Gözlenen Tam56 **7** sonuç, sonraki yeni ve gerçekten görülmemiş saatlerde önceden dondurulmuş kayıtla tekrarlanmadıkça üstünlük değildir.

**6/6 sonucu** Tam56 için ilk18 günde **2**, son18 günde **0**; rastgele örnekte toplam **3**. Bu da kalıcı avantaj göstermez.

## Çekilişten önce kayıt disiplini

Tahmin satırları `03_TUM_CEKILISLER_SURELI_1_KUPON_ONCE_SONRA.csv` içinde:
- önceki bilinen çekiliş kimliği;
- **hedef çekiliş kimliği**, saat dilimi ve H7–H12 el numarası;
- tahmin edilen sıralı sayı seçiminin alfabetik değil sayısal olarak sıralanmış tek kuponu;
- hedef görüldükten sonra kaç tuttuğu / hangi numaralar tuttu;
- model/kupon boyu.

Bu, geriye dönük simülasyonda hedef bilgisi kullanılıp kullanılmadığını denetlemek içindir. **Gerçek canlı/ileri izleme sistemine dönüşmesi için önce yeni verilerin tahmin kaydından sonra gelmesi şart.** 16 Ekim güncel sonuçları depoda yoktur.

## İstatistiksel belirsizlik

Son18 günlük veri günlük çiftlemeli 10'lu isabet ortalama farkında Tam56−Rastgele **+0,04475** ve yaklaşık %95 gün-gruplu aralık **[−0,05921, +0,14872]**; Tam56−Son6 **+0,02109**, aralık **[−0,04159, +0,08377]**. Sıfır bu aralıklarda yer alır. İlk18 günlük Tam56−Rastgele **−0,02263**, yine üstünlük göstermez.

13 Ekim yalnız **11 tam saat / 66 H7–H12 çekiliş**, bir günlük yeni veri bulunduğu için günlük belirsizlik aralığı hesaplamak anlamlı değil. Kodun tek güne koyduğu sıfır genişlikli biçim **istatistiksel güven aralığı olarak yorumlanmamalıdır.**

## Dosya listesi

1. `00_V111_TAM56_KUPON_KOR_KARSILASTIRMA_SONUC.txt` — ayrıntılı TXT;
2. `01_10LU_MOTORLAR_DONEMLER_0_10_ISABET.csv` — her 10'lu 0..10 sonuç;
3. `02_5_6_8_10LU_TAM56_ISABET_DAGILIMI.csv` — tam56 k boyları;
4. `02B_5_6_8_10LU_TUM_MODELLER_ESIT_CEKILIS.csv` — **her yöntemde aynı 5/6/8/10 boyları**;
5. `03_TUM_CEKILISLER_SURELI_1_KUPON_ONCE_SONRA.csv` — her çekiliş/kupon tahmin kaydı;
6. `04_GUNLUK_10LU_ESLESMELI_FARK.csv`;
7. `05_10LU_KARSILASTIRMA_GUN_BAZLI_BELIRSIZLIK.csv`;
8. `06_EK_13EKIM_80_SAYI_GERCEKLERI_OLASILIK.csv`;
9. `07_METOT_GECMIS_SIZMA_DENETIM.json`.

## Sonraki karar

**V100C/V104 yürüyen 56 halka aynen korunur.** V111 bir araştırma motorudur: şu anda yeni bir çekilişe `10'da10` garanti tahmin üretebilen bir mekanizma gösterilemedi. İleride en doğru yöntem, tüm olasılık ve kuponları yeni çekiliş **öncesinde zaman damgasıyla sabitleyip**, günlerce yeni gelen hedeflere karşı günlük özetleri göstermektir. Kupon bütçesini artırıp geçmişte görünen aşırı isabetleri kovalamak rasyonel bir sonuç değildir.
