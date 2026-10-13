# V13 — 217 Çekilişlik Hareketli 80 Sayı Havuzu, 20 Koltuk ve Aile Motoru

**Tarih:** 13 Ekim 2026  
**Depo:** gozlekakif-alt/hizli-on-analiz-motoru  
**Motor:** v13_havuz_koltuk.py (V12: v12_80_kule.py ile beraber)  
**Uygulama:** v10_app.py içindeki **🌡️ V13 Hareketli Havuz** sekmesi  
**Test:** v13_selftest.py ve GitHub Actions

## 1. Araştırmanın temel sorusu

Günün 1. çekilişinden 217.'ye kadar her 1–80 sayısının kimliği nasıl değişir?

Örnekler: soğuk-durgun, soğuk-uyanıyor, soğuk-dinleniyor, ılık-yükseliyor, ılık-soğuyor, sıcak-yükseliyor, sıcak-tepe, sıcak-yerleşik, sıcak-soğuyor. Bunlar kendi başlarına sonraki çekilişte sayı olasılığını değiştiren kurallar kabul edilmez; ölçülebilir geçmiş özelliklerdir.

Her hedef öncesinde 80 sayı yeniden sınıflandırılır; 20 sayılık gelecekteki hedefin *sıcak / ılık / soğuk* gruplarından kaç sayı içereceği ve bu grup içinden hangi sayıların seçileceği önceden hesaplanır.

**Koltuk** = 20 sayılık sonuçta belirli sıcaklık grubuna düşen sayı adedidir. Kayıtlardaki 20 sayı küçükten büyüğe listelendiğinden koltuklar fiziksel top çıkma pozisyonu DEMEK DEĞİLDİR.

## 2. Teknik mimari

1. Her çekilişin öncesinde, 1..80 için gün başından birikmiş görünüş sayısı.
2. Sayının son 12, son 6 ve önceki 6 çekilişteki frekans değişimi.
3. Kaç çekiliştir görünmediği, günün konumu, beklenenden sapması (z-puanı).
4. Dört ana havuz: soğuk, ılık, sıcak ve ilk beş çekilişte "erken/veri az".
5. Sıcaklık alt evreleri: *soğuk-uyanıyor / dinleniyor*, *sıcak-yükseliyor / tepe / soğuyor* vb.
6. Geçmiş 36 günlük eğitimde her sınıfın, günün başlangıç/orta/son bölümündeki **sonraki hedefte çıkma sıklığı** ölçülür. Yüksek sonuçlara aşırı güvenmemek için olasılıklar %25 başlangıç değerine doğru yumuşatılır.
7. 20 koltuğun kotaları, geçmiş eğitim dönemindeki oranlarla ve hedef öncesindeki havuz büyüklükleriyle hesaplanır. Bir çekilişte 20 sayı seçilir.
8. Üç ayrı sabit deneysel 20 seçimi: **Koltuk-model / Tepeyi azalt / Tepeyi koru**. İkinci/üçüncü yöntemler sıcak-tepe ailesinin aday sıralamasına sabit -/+ puan verir.
9. Kesintisiz geçmiş 12 çekilişi bulunan saatin 7–12. hedeflerinde V12 sayı ağı da kurulup **Koltuk+V12 / V12 ağ-kule** ayrıca değerlendirilir.
10. Kupondaki 20 sayı *sayı büyüklüğüyle değil*, önceden belirlenmiş hareket puanlarıyla sıralanır. İlk 2,3,...,10 sayı iç içe aile tahmini; 2+3+4+5+6 ise ayrık aile bileşenidir.
11. Tamamen soğuk, tamamen ılık, tamamen sıcak, soğuk-uyanıyor, soğuk-dinleniyor, sıcak-yükseliyor, sıcak-tepe ve sıcak-soğuyor kategorilerinde 2–10 aileler için *tek önceden sabit aile adayı* seçilir. Hedefte tam görünüş 0/k..k/k ile yazılır.
12. Gerçek hedefteki 20 sayının grup koltuklarına göre dağılımı, gerçekleşen sonuçtan sonra kontrol edilir. Koltuk sayılarının **tam tutması**, adil hipergeometrik dağılımdaki kesin rastgele beklentiyle ayrıca karşılaştırılır.
13. Bütün 217 çekilişin sonuçları, ayrıca saat 7–12'nin V12 ile bire bir karşılaştırılabilir alt kümesi, hiçbir başarısız deneme saklanmadan raporlanır.
14. Kullanıcı canlı önizlemede 6,7,8,9,10'lu deneysel aile kuponunu seçip mevcut V10 kupon defterine **kendi düğmesine basarak** kaydedebilir. Otomatik satın alma/oynama yapılmaz.

## 3. Gerçek veride tarihsel eğitim/test ayrımı

| Ölçüm | Adet |
|---|---:|
| Tüm veri dönemi | 1 Ağustos–12 Ekim 2026 |
| Modelin kuralları/olasılıklarının öğrenildiği gün | 36 (1 Ağustos–5 Eylül) |
| Ayrı test günü | **37** (6 Eylül–12 Ekim) |
| Eğitim çekilişi | **7.810** |
| Test çekilişi, bütün 217'lik gün boyunca | **8.029** |
| V12 ile aynı şartları taşıyan saatin 7–12 hedefleri | **3.774** |
| Hedefe çıkacak numara sayısı | 20 (1–80'den) |

Bu geriye dönük, kronolojik ayrılmış bir **zaman bazlı testtir**. V13 fikirleri ve eşikleri 2026-10-13 tarihinde veri incelendikten sonra tasarlandığı için buna tam bağımsız, gelecekte gerçekleştirilmiş *kör test* denemez. Gerçek kör test için kodu/parametreleri 13 Ekim'de kilitleyip sonraki tarihlerdeki sonuçları kullanmak gerekir.

## 4. Yöntemlerin V12 ile eşleştirilmiş 3.774 hedefte ilk sonuçları

| Yöntem | 20 sayıdan ortalama isabet |
|---|---:|
| **Koltuk-model** | **5,0384** |
| Tepeyi azalt | 5,0450 |
| Tepeyi koru | 5,0379 |
| Koltuk+V12 birleşik | 5,0125 |
| V12 ağ-kule | 4,9645 |
| Rastgele20 (aynı hedef) | 5,0400 |
| Adil matematiksel beklenti | 5,0000 |

**Tam 20/20 hiçbirinde olmadı.** V13 koltuk motoru ve tepe varyantları rastgele kontrolden güvenilir biçimde daha iyi performans göstermedi. "Tepeyi azalt" yönteminin 5,0450 ortalaması onu kazanan motor ilan etmek için yeterli değildir.

## 5. Kullanıcının asıl sorusu: Tamamen soğuk 6'lı veya sıcak-tepe 6'lı geliyor mu?

İzleyen 37 gündeki bütün uygun günlük çekiliş hedeflerine, yalnız hedef ÖNCESİ ilgili durumdaki altı sayı seçilerek yazılan ayrı hedefler:

| Aile evresi | Önceden kurulan 6'lı aile hedefi | Tam 6/6 |
|---|---:|---:|
| **Tamamı soğuk** | 7.755 | **1** |
| Tamamı sıcak | 7.797 | 4 |
| Tamamı sıcak-tepe | 106 | 0 |
| Tamamı soğuk-uyanıyor | 40 | 0 |
| Tamamı soğuk-dinleniyor | 1.662 | 0 |
| Tamamı sıcak-soğuyor | 173 | 0 |

Bu sayılar kesinlikle "sıcakta kazanma avantajı var" veya "tepede asla gelmez" anlamına gelmez. Özellikle tepe 6'lı grubunda yalnız 106 deneme var. Adil çekilişte herhangi bir **önceden sabit 6 sayının** 6/6 gelme olasılığı seçilmiş sıcaklık etiketinden bağımsızdır.

Bir gerçek çekilişteki bütün soğuk/sıcak 6'lı alt ailelerin **SONRADAN** sayılması ayrı bir tanımlayıcı istatistiktir; bunlar 6/6 kupon isabeti gibi gösterilmez.

## 6. Soğuk, ılık, sıcak koltuklarının 20 sayıyı doldurması

Son 37 günün orta ve son bölümlerinde, 80 sayının ortalama havuzda ve gerçek 20'de dağılımları:

| Gün bölümü | Grup | Ortalama havuz sayısı | Gerçek 20'deki koltuk |
|---|---|---:|---:|
| Orta | Soğuk | 13,13 | 3,25 |
| Orta | Ilık | 53,62 | 13,40 |
| Orta | Sıcak | 13,25 | 3,35 |
| Son | Soğuk | 12,73 | 3,19 |
| Son | Ilık | 53,87 | 13,47 |
| Son | Sıcak | 13,40 | 3,34 |

Gerçek 20'deki ortalama koltuk sayıları havuzda olan sayıların yaklaşık **dörtte biri** civarındadır. Bu, bağımsız 20/80 çekilişinden beklenen davranıştır; sıcaklık sınıfının özel avantajına kanıt değildir.

Hedefin 20 koltuğunu *tam doğru doldurma* testi ve koltuk mutlak tahmin hatası CSV tablosu V13 sekmesinde ayrıdır.

## 7. Uygulama ve veri güvenliği

- GitHub motor: v13_havuz_koltuk.py
- Test: v13_selftest.py
- Uygulama: v10_app.py, yeni sekme **🌡️ V13 Hareketli Havuz**
- GitHub Actions Python + Streamlit CI testi
- CSV raporları: bütün 217 hedef isabet defteri, 20 sayılık yöntemler, sıcak/soğuk koltuk tahmini, tam koltuk tutma raporu, sıcak tepe/soğuk-uyanma durumu, 2–10 aile içi başarıları, tam soğuk/sıcak aileleri, aile ve kupon örnekleri.
- V9 app.py, veri.txt, v10_aileler.csv, v10_canli_kayit.json **DEĞİŞTİRİLMEDİ**.
- V13 kendi tahmin motoru deneysel olduğu için kesin kazandırma, 6/6 veya 10/10 garanti iddiası yoktur.

## 8. Bundan sonra

Gerçek bağımsız test için bugün motor kodunu, aile sırasını ve sıcaklık eşiklerini dondurup yarından itibaren her hedef öncesinde kupun/koltuk seçimini zaman damgasıyla kaydetmek gerekir. Yeni çekiliş sonuçları geldikçe aile boyutlarına göre k/k, sıcak-tepe grup etkisi, tam koltuk tutma ve rastgeleye karşı karşılaştırma otomatik güncellenmelidir. Eğer avantaj görülmezse eşiği sonuca bakarak değiştirip aynı günleri tekrar kör test gibi göstermemeliyiz.
