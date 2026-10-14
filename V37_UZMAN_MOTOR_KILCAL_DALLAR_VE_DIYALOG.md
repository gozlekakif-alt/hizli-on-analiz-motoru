# V37 — UZMAN MOTORLARIN KILCAL ALT DALLARI VE DİYALOG HARİTASI

14 Ekim 2026 • **TASARIMDIR, ÇALIŞAN KOD DEĞİLDİR.** Mevcut V36 korunmuştur.

Bu listede her alt dal ayrı motor kimliğine, kanıta, hazne üye listesine, giriş/çıkış olayına ve geçmişin nereden okunduğunu gösteren kaynak bağlarına sahip olacaktır. Bir dal ancak kodlandı, test edildi, tüm gerçek veri işlendi ve rapor üretildi aşamalarının tamamından sonra çalışıyor sayılır.

## 1. LIFE — 80 sayının ömürlük ortak hafızası (12 uzman)

1. **LIFE.01** — Her çekiliş 80 sayılık 1/0 yaşam izi
2. **LIFE.02** — Günlük 217 adım yaşam kronolojisi
3. **LIFE.03** — Ömür boyu 1/0 yaşam kronolojisi
4. **LIFE.04** — 3,6,11,12,24,36,72,217,219 pencere yoğunlukları
5. **LIFE.05** — Gün içi ilk görünme
6. **LIFE.06** — Ömürlük ilk görünme
7. **LIFE.07** — Kayıtlı son görünme
8. **LIFE.08** — Gün içi ardışık yokluk
9. **LIFE.09** — Ömürlük ardışık yokluk
10. **LIFE.10** — Gün içi ardışık görünme
11. **LIFE.11** — Ömürlük ardışık görünme
12. **LIFE.12** — Eksik veriye UNKNOWN işaretleme

## 2. HEAT — Altı ısı sınıfının ayrı koltukları (14 uzman)

1. **HEAT.01** — Soğuk koltuk giriş/kalış/çıkış
2. **HEAT.02** — Soğuğa yakın giriş/kalış/çıkış
3. **HEAT.03** — Orta giriş/kalış/çıkış
4. **HEAT.04** — Ilık giriş/kalış/çıkış
5. **HEAT.05** — Sıcağa yakın giriş/kalış/çıkış
6. **HEAT.06** — Sıcak giriş/kalış/çıkış
7. **HEAT.07** — 12 çekiliş yarı ömürlü ısı puanı
8. **HEAT.08** — Isı koltuğunda kalış ömrü
9. **HEAT.09** — Daha önce bırakılan koltuğa geri dönüş
10. **HEAT.10** — Isı sınırında salınma
11. **HEAT.11** — Koltuk sırası sabitken ham ısının artması
12. **HEAT.12** — Koltuk sırası sabitken ham ısının düşmesi
13. **HEAT.13** — Isı sırası ve mutlak ısı ayrımı
14. **HEAT.14** — Isı koltuğu 80 toplamı kontrolü

## 3. DIRECTION — Sıcaklık hareketinin kılcal alt yönleri (16 uzman)

1. **DIRECTION.01** — Soğuk→soğuğa yakın
2. **DIRECTION.02** — Soğuğa yakın→orta
3. **DIRECTION.03** — Orta→ılık
4. **DIRECTION.04** — Ilık→sıcağa yakın
5. **DIRECTION.05** — Sıcağa yakın→sıcak
6. **DIRECTION.06** — Sıcak→sıcağa yakın
7. **DIRECTION.07** — Sıcağa yakın→ılık
8. **DIRECTION.08** — Ilık→orta
9. **DIRECTION.09** — Orta→soğuğa yakın
10. **DIRECTION.10** — Soğuğa yakın→soğuk
11. **DIRECTION.11** — Birden fazla basamak sıçrama
12. **DIRECTION.12** — Yükselişin iki gerçek adım sürmesi
13. **DIRECTION.13** — Düşüşün iki gerçek adım sürmesi
14. **DIRECTION.14** — Durağanlık ve yön değiştirme
15. **DIRECTION.15** — Yükseliş→düşüş ters dönüş
16. **DIRECTION.16** — Düşüş→yükseliş ters dönüş

## 4. WAIT — Sessizlik ve bekleme sınıfları (16 uzman)

1. **WAIT.01** — Bir çekilişlik yokluk
2. **WAIT.02** — 2-3 gerçek çekiliş yokluk
3. **WAIT.03** — 4-5 gerçek çekiliş yokluk
4. **WAIT.04** — Tam 6 yokluk
5. **WAIT.05** — Tam 7 yokluk
6. **WAIT.06** — Tam 8 yokluk
7. **WAIT.07** — Tam 9 yokluk
8. **WAIT.08** — Tam 10 yokluk
9. **WAIT.09** — 11-15 yokluk
10. **WAIT.10** — 16-24 yokluk
11. **WAIT.11** — 25+ yokluk
12. **WAIT.12** — Beklemenin uzunluğu ve o anki bant
13. **WAIT.13** — Bekleme sırasında ısı yönü
14. **WAIT.14** — Günlük bekleme ile ömürlük bekleme farkı
15. **WAIT.15** — Bekleme sınıfından çıkış
16. **WAIT.16** — Bekleme bitince yeni epizod

## 5. RETURN — Geri canlanma ve ikinci yaşam (12 uzman)

1. **RETURN.01** — 6+ sonra ilk geri geliş
2. **RETURN.02** — 8+ sonra ilk geri geliş
3. **RETURN.03** — 10+ sonra ilk geri geliş
4. **RETURN.04** — İlk gelişten hemen sonra ikinci geliş
5. **RETURN.05** — Bir el dinlenip ikinci geliş
6. **RETURN.06** — İki el dinlenip ikinci geliş
7. **RETURN.07** — İkinci gelişten üçüncü geliş
8. **RETURN.08** — Geri dönüp yeniden sessizleşme
9. **RETURN.09** — Bekleme sonunda ısı yükselişi
10. **RETURN.10** — Bekleme sonunda aileyi tamamlama
11. **RETURN.11** — Bekleme sonunda V32 döngüde ilk görülme
12. **RETURN.12** — Geri gelişlerin zaman aralığı dağılımı

## 6. BURST — 11 gerçek çekilişlik imza ve yoğunluk (14 uzman)

1. **BURST.01** — 11'de 0-3 görülme
2. **BURST.02** — 11'de 4 görülme
3. **BURST.03** — 11'de 5 görülme
4. **BURST.04** — 11'de 6 görülme
5. **BURST.05** — 11'de 7 görülme
6. **BURST.06** — 11'de 8 görülme
7. **BURST.07** — 11'de 9-11 görülme
8. **BURST.08** — Ardışık iki pencerede H6 sürdürme
9. **BURST.09** — Ardışık üç ve üzeri pencerede H6
10. **BURST.10** — H6 karakterinden çıkış
11. **BURST.11** — H6 ile başka sayının A6 beklemesi
12. **BURST.12** — İlk 6 ile sonraki 5 yönü
13. **BURST.13** — 11-bit imza tekrarları
14. **BURST.14** — İmza değişim zinciri

## 7. STAGE — 20 çıkan / 60 çıkmayan hareketi (10 uzman)

1. **STAGE.01** — Önceki çıkan20'den tekrar geliş
2. **STAGE.02** — Önceki çıkan20'den ayrılış
3. **STAGE.03** — Önceki çıkmayan60'tan çıkan20'ye giriş
4. **STAGE.04** — Çıkmayan60'ta kalış
5. **STAGE.05** — Değişen 20/60 içinde ısı dağılımı
6. **STAGE.06** — Değişen 20/60 içinde bant dağılımı
7. **STAGE.07** — Tek çekilişte taşınan tekrar sayısı
8. **STAGE.08** — Yüksek/ düşük tekrarın izleyen karakteri
9. **STAGE.09** — Aile üyelerinin beraber 20/60 geçişi
10. **STAGE.10** — Çıkan20'de kalış epizodu

## 8. PAIR — İkili aile yaşamı (10 uzman)

1. **PAIR.01** — İlk tam 2/2 beraber doğuş
2. **PAIR.02** — Ardışık iki çekiliş 2/2
3. **PAIR.03** — İkinci kez 2/2 birliktelik
4. **PAIR.04** — Üçüncü ve dördüncü 2/2 birliktelik
5. **PAIR.05** — Bir üye aktif diğeri sessiz
6. **PAIR.06** — İki üye de sessiz
7. **PAIR.07** — Sessizlik sonrası yeniden 2/2
8. **PAIR.08** — Birleşme arası gerçek çekiliş farkı
9. **PAIR.09** — Zıt sıcaklık yönlü eşleşme
10. **PAIR.10** — Eşleşmeden üçlüye genişleme

## 9. TRIPLE — Üçlü aile yaşamı ve tamamlanma (12 uzman)

1. **TRIPLE.01** — 3/3 aynı çekilişte doğuş
2. **TRIPLE.02** — 3/3 ardışık iki çekiliş
3. **TRIPLE.03** — 3/3 üçüncü birleşme
4. **TRIPLE.04** — 2+1 parçalı tamamlama
5. **TRIPLE.05** — 1+2 parçalı tamamlama
6. **TRIPLE.06** — 1+1+1 parçalı tamamlama
7. **TRIPLE.07** — 2/3 ön sinyal ve üçüncü üye beklemesi
8. **TRIPLE.08** — 2/3 sonrası ailenin sessizliği
9. **TRIPLE.09** — Tam gelişten sonra kopma
10. **TRIPLE.10** — Kopan ailenin yeniden birleşmesi
11. **TRIPLE.11** — 3/3 olayı ile 3 çekilişte kaplanan 3/3 ayrımı
12. **TRIPLE.12** — Dörtlüye genişleme

## 10. QUARTET — Dörtlü aile kılcal dalları (16 uzman)

1. **QUARTET.01** — 4/4 aynı gerçek çekilişte tam geliş
2. **QUARTET.02** — 4/4 ardışık iki çekilişte geliş
3. **QUARTET.03** — 4/4 üçüncü ve sonraki geliş
4. **QUARTET.04** — 3+1 parçalı tamamlama
5. **QUARTET.05** — 1+3 parçalı tamamlama
6. **QUARTET.06** — 2+2 parçalı tamamlama
7. **QUARTET.07** — 2+1+1 parçalı tamamlama
8. **QUARTET.08** — 1+2+1 parçalı tamamlama
9. **QUARTET.09** — 1+1+2 parçalı tamamlama
10. **QUARTET.10** — 1+1+1+1 parçalı tamamlama
11. **QUARTET.11** — 1/4 ve 2/4 hareketleri
12. **QUARTET.12** — 3/4 eksik son üyenin beklemesi
13. **QUARTET.13** — Ailenin tam sessiz dönemi
14. **QUARTET.14** — Parçalı tamamlanma ile tek çekilişte tam geliş ayrımı
15. **QUARTET.15** — Aile içi sıcaklık yükselen/düşen eşleşme
16. **QUARTET.16** — Dörtlünün farklı çekirdek aileye bağlanması

## 11. LARGE — 5–10 üyeli büyük aileler (8 uzman)

1. **LARGE.01** — 5'li aileye yeni üye girişi
2. **LARGE.02** — 6'lı ailede iki ayrı üçlü alt aile
3. **LARGE.03** — 7-10'lu ailede etkin alt aileler
4. **LARGE.04** — Üye değişimi ve aile kimliği
5. **LARGE.05** — Uzun aile sessizliği
6. **LARGE.06** — Aktif alt aile ile sessiz alt aile
7. **LARGE.07** — Alt ailenin yeniden birleşmesi
8. **LARGE.08** — Gerçek olaydan seçilen aday aile defteri

## 12. BAND — Sekiz bant baskısı (14 uzman)

1. **BAND.01** — 01-10 ayrı hareket
2. **BAND.02** — 11-20 ayrı hareket
3. **BAND.03** — 21-30 ayrı hareket
4. **BAND.04** — 31-40 ayrı hareket
5. **BAND.05** — 41-50 ayrı hareket
6. **BAND.06** — 51-60 ayrı hareket
7. **BAND.07** — 61-70 ayrı hareket
8. **BAND.08** — 71-80 ayrı hareket
9. **BAND.09** — Bant başına 20 çıkış baskı ve aşırı uç
10. **BAND.10** — Bant içindeki 6 sıcaklık dağılımı
11. **BAND.11** — Bant içindeki bekleme yoğunluğu
12. **BAND.12** — Bir bant artarken kardeş bant azalması
13. **BAND.13** — Bantlar arası karşılıklı devinim
14. **BAND.14** — Bant içinde ardışık blok

## 13. MIRROR — Alt/üst40, ayna ve komşuluk (9 uzman)

1. **MIRROR.01** — n ile 81−n ayna sayıları
2. **MIRROR.02** — 1–40 çıkış yükü
3. **MIRROR.03** — 41–80 çıkış yükü
4. **MIRROR.04** — Ayna bantlar arasında yön hareketi
5. **MIRROR.05** — Komşu +1/-1 sayılar
6. **MIRROR.06** — İkişerli ardışık bloklar
7. **MIRROR.07** — Üçlü ve dörtlü ardışık bloklar
8. **MIRROR.08** — 1-3-5 atlamalı zincir
9. **MIRROR.09** — Ayna eşlikçisi beklemeden dönerken ana sayı

## 14. CYCLE — İki ayrı 80/80 döngü (10 uzman)

1. **CYCLE.01** — Çıkan20 tüm 80 sayı döngüsü
2. **CYCLE.02** — Çıkmayan60 tüm 80 sayı döngüsü
3. **CYCLE.03** — 4. adım ilk farklı sayı seviyesi
4. **CYCLE.04** — 8. adım ilk farklı sayı seviyesi
5. **CYCLE.05** — 12. adım ilk farklı sayı seviyesi
6. **CYCLE.06** — Son 5 eksik sayı durumu
7. **CYCLE.07** — 79/80 son sayı bekleme
8. **CYCLE.08** — 80/80 sonrası bir sonraki gerçek adımda reset
9. **CYCLE.09** — Bir döngüden sonraki döngü hızı
10. **CYCLE.10** — Döngüde görülmemiş ile 6–11+ bekleme kesişimi

## 15. TIME — 217 çekilişlik gün/saat mekaniği (10 uzman)

1. **TIME.01** — 00:02 ilk gerçek çekiliş
2. **TIME.02** — 01:02 13. çekiliş
3. **TIME.03** — 07:02 14. çekiliş
4. **TIME.04** — Her saatin ilk 6 gerçek çekilişi
5. **TIME.05** — Her saatin son 6 gerçek çekilişi
6. **TIME.06** — Saatten saate taşınan sayı kimlikleri
7. **TIME.07** — 12 çekilişlik saat ritmi
8. **TIME.08** — 32/37/42/47/52/57 dakika özel kesitleri
9. **TIME.09** — Günün erken/orta/geç evreleri
10. **TIME.10** — Önceki gün ile sonraki gün epizot sürekliliği

## 16. DIALOGUE — Motorlar arası olay diyalogları (12 uzman)

1. **DIALOGUE.01** — WAIT_ENDED ∩ HEAT_UP
2. **DIALOGUE.02** — WAIT_ENDED ∩ FAMILY_COMPLETE
3. **DIALOGUE.03** — H6_PERSIST ∩ BAND_PRESSURE
4. **DIALOGUE.04** — PAIR_REUNITED ∩ HEAT_DOWN
5. **DIALOGUE.05** — TRIPLE_2+1 ∩ QUARTET_3+1
6. **DIALOGUE.06** — 20'ye giren sayının V32'de görülmemişliği
7. **DIALOGUE.07** — Kardeş bant hareketlerinin eşzamanlılığı
8. **DIALOGUE.08** — Motor A'dan sonra 1/2/3/6 adımda motor B
9. **DIALOGUE.09** — İki olaylı zincir tekrar sayısı
10. **DIALOGUE.10** — Üç olaylı zincir tekrar sayısı
11. **DIALOGUE.11** — Aileden sayıya ve sayıdan aileye çift yönlü kanıt
12. **DIALOGUE.12** — Olay kanıt kimlikleri, bağımsız tekrar sayısı

## 17. TWIN — Klon ve denetim laboratuvarı (12 uzman)

1. **TWIN.01** — Gerçek 20/60 ayrı yaşam defteri
2. **TWIN.02** — Özerk klon 20/60 ayrı yaşam defteri
3. **TWIN.03** — t-1 gerçek durumundan koşullu klon
4. **TWIN.04** — Eş olasılıklı 20/80 kontrol
5. **TWIN.05** — Dondurulmuş parametre kontrolü
6. **TWIN.06** — Klon ısı geçiş matrisleri karşılaştırması
7. **TWIN.07** — Klon bekleme kuyrukları karşılaştırması
8. **TWIN.08** — Klon aile parçalı geliş karşılaştırması
9. **TWIN.09** — Klon döngü ömürleri karşılaştırması
10. **TWIN.10** — 72 günü ilk/ikinci yarı test
11. **TWIN.11** — Her yeni çekilişten sonra online akort
12. **TWIN.12** — Klonun gerçek sayıları yakalaması ayrı ölçüm

## 17 ana grup ve 207 kılcal motor dalının ortak sözleşmesi

Her olayda çekiliş no, gün, 1–217 sıra, sayı/aile, motor kimliği, eski/yeni hazne, giren/çıkan/kalan, epizot başlangıcı ve süresi, 1/0 geçmiş kaynakları, başka motor olaylarının ID'leri ve gerçek/klon ayrımı saklanır.

Ailelerde aynı gerçek çekilişte 4/4 ve dört gerçek çekilişin birleşiminde kapsanan parçalı 4/4 iki ayrı olaydır. Sessizlik de ikiye ayrılır: hiç üyenin çıkmaması ile tam ailenin birlikte gelmemesi aynı değildir. Örnek 2+1+1 yolu sadece üyelerin geldiği zamanlar kayıtlıysa tamamlandı olarak işaretlenir. Gelecekteki gelişle geçmişte oluşmuş gibi kayıt yazılmaz.

Büyük ailelerin bütün kombinasyonlarını her gün çoğaltmıyoruz. 80 sayıdan 1.581.580 dört üyeli küme ve 24.040.016 beş üyeli küme vardır. Gerçek gerçekleşmeden türetilmiş adaylar, kaynak oluşum kriteri, izleme kapsamı ve karşılaştırma nüfusu birlikte tutulur. Yalnız başarılı aileler seçilip sonra başarı oranı hesaplanmaz.

Diyalog örneği: 23 sayısı WAIT.06'dan çıktığında RETURN.01 olayı doğar; DIRECTION yükselişi varsa HEAT olayıyla, 19-23-30-48 ailesinin 3+1 tamamlanması varsa QUARTET olayıyla ilişkilendirilir. Tek bir ortak olay bunların kaynak ID'lerini ve sıra farklarını saklar; hiçbir motor tek başına gelecek sayı garantisi ilan etmez.

**İnşa sırasi:** Ortak hayat kütüğü → tekil ısı/yön/bekleme/döngü → 2/3/4 aile epizodları → motor diyalog grafiği → ayrı özerk klon → günlük dağılım ve zaman sıralı rapor → Streamlit tek tuş / checkpoint / tek ZIP. Önce çekirdek verinin eksiksiz, tekrar çalıştırılabilir olması şarttır.

[Temel mimari](V37_ORTAK_HAFIZA_UZMAN_MOTOR_KLON_MIMARISI.md)
