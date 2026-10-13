# V18 — 80 sayıyı iki ayrı havuzda biriktirme: Çıkan 20 / Çıkmayan 60

**13 Ekim 2026 — Hızlı On projesi.**

## Kullanıcı isteği

"80 sayı hedef çekilişte çıkan 20 sayı ve çıkmayan 60 sayı 2 ayrı havuz yapıp 217 çekiliş boyunca ayrı havuzlarda biriktirsene."

Bu çalışma ayrı bir tahmin motoru değildir. **1–80 havuzunun her çekilişte nasıl ikiye bölündüğünü, her sayının gün boyunca hangi havuzdan hangi havuza geçtiğini ve hangi havuzda kaç kez kaldığını kayıt altına alır.** V17 çekiliş karakteri araştırmasına temiz geçmiş veri sağlar.

## Çekiliş başına iki zorunlu havuz

- **Çıkan 20:** Tam 20 farklı sayı; resmî çekiliş sonucunun sayı kümesi.
- **Çıkmayan 60:** 1–80 içerisindeki diğer bütün 60 sayı, yani 80'lik kümenin tamamlayıcısı.
- Her çekiliş için **20+60=80**; bir sayı **ya çıkan ya çıkmayan** havuzundadır, asla ikisinde birden bulunmaz.
- Bu havuzlar sabit bir oyuncu grubu değildir; çekilişten çekilişe 80 sayının kimliği DEĞİL, geçici durumu değişir.

## Günün 1. çekilişinden 217. çekilişine kadar birikim

Her çekilişte iki tam sayı listesi ayrı dosya görünümüne eklenir:

| Günlük çekiliş | Çıkan 20 havuzu birikmiş görünüş | Çıkmayan 60 havuzu birikmiş görünüş |
|---|---:|---:|
| 1 | 20 | 60 |
| 12 | 240 | 720 |
| 13 | 260 | 780 |
| 100 | 2.000 | 6.000 |
| 217 | **4.340** | **13.020** |

Bu rakamlar **benzersiz sayı adedi değil, sayı×çekiliş görünüş kaydı** sayısıdır. Bir sayı, farklı çekilişlerde tekrar tekrar görülür veya bekler. Bir günün 80 sayısının tamamının olası toplam görünüşü 217×80=17.360'tır.

### Her sayı için ayrı birikim

Her 1–80 sayısı için:
- Gün içinde kaç defa **çıkan 20** içinde bulundu?
- Kaç defa **çıkmayan 60** içinde kaldı?
- Hangi çekilişte ilk ve son kez çıktı?
- Çıkan 20'nin içinde kaç ardışık çekiliş kaldı?
- Çıkmayan 60'ta kaç ardışık çekiliş bekledi?
- 60→20 geri dönüş sayısı; 20→60 ayrılma sayısı.
- 20→20 koruma ve 60→60 bekleme sayısı.
- Günün son bilinen çekilişindeki havuzu ve ardışık havuz serisi.

**Tam 217 çekilişte her sayı için çıkan20_görünüşü + çıkmayan60_görünüşü = 217.** Her sayının matematiksel eşit şanslı beklentisi, çıkan 20'de 54,25; çıkmayan 60'ta 162,75 görünüş. Bu beklenen değerler gelecekte çıkış garantisi değildir.

### Havuzdan havuza dört olası geçiş

İki çekiliş arasında 80 sayının tamamı aşağıdaki dört ayrı gruba ayrılır:

1. **20→20:** Önceki çekilişte çıktı, sonraki çekilişte de çıktı.
2. **20→60:** Önceki çekilişte çıktı, sonraki çekilişte çıkmadı.
3. **60→20:** Önceki çekilişte çıkmadı, sonraki çekilişte çıktı.
4. **60→60:** Önceki çekilişte çıkmadı, sonraki çekilişte yine çıkmadı.

Her geçişte 20→20 + 20→60 = 20 ve 60→20 + 60→60 = 60; ayrıca 20→20 + 60→20 = 20. Aynı sayıdaki ayrılan/gelenler arasında fiziksel birebir eşleşme varsayılmaz.

01:02→07:02 altı saatlik ara **6 saat ara** olarak işaretlenir; kayıt olmayan slotlardan beş dakikalık geçiş üretilmez. Eksik çekiliş, varsayılan 60'lık havuza asla eklenmez.

## V18 uygulamasında nasıl ulaşılır?

Streamlit V10 uygulamasının **🌓 V18 Çift Havuz** sekmesi:

- İncelenecek günü seç; sistem veri.txt kaynak kaydından o güne ait doğru çekilişleri otomatik yükler.
- Çekiliş seçildiğinde karşı karşıya **çıkan 20** ve **çıkmayan 60** listeleri görülür.
- Günün birikmiş aktif / bekleyen sayı kayıt toplamları ve 80 sayının bireysel kimlikleri tabloda gösterilir.
- Belirli 1–80 sayısının bütün gün boyunca hangi havuzda olduğunu çekiliş çekiliş incele.
- Havuzların değişimini, V17 karakter motoru için 20→20/20→60/60→20/60→60 dönüşlerini ayrı görüntüle.
- İki havuzu **ayrı TXT ve CSV** olarak indir; ayrıca **217×80** "Ç"(çıktı) / "B"(bekledi) günlük durum matrisi ve 80 sayının günlük bilançosunu indir.

### Kalıcılık nasıl sağlanıyor?

Halihazırda GitHub'da kalıcı duran **veri.txt** kayıtları temel kaynak olarak korunuyor. V18 iki ayrı havuz arşivini her açılışta bu kalıcı kaynak üzerinden **deterministik yeniden kuruyor**. Bu iki arşiv uygulamada ayrı görüntülenir ve ayrı dosyalar olarak dışa aktarılabilir. **GitHub'a aynı verinin milyonlarca kopyasını oluşturarak yeni, çatışmalı bir kaynak açmıyoruz.** Yeni çekilişler mevcut kayıt akışına eklendikçe ilgili iki havuz güncellenir.

Eksik kayıt olmadan günün 217 çekilişi tamamlandığında "Tam gün" olarak işaretlenir. Kısmi günler gerçekten kısmi tutulur. Bu araştırma kendiliğinden kupon, bahis veya RNG tahmin kuralı üretmez.

## Test

V18 ilk bağımsız GitHub testinde **74 gün** veri bulundu (son gün kısmi):
- **01.08.2026:** 217 çekiliş, 4.340/13.020 havuz görünüşü.
- **11.08.2026:** 217 çekiliş, 4.340/13.020.
- **05.09.2026:** 217 çekiliş, 4.340/13.020.
- **12.10.2026:** 217 çekiliş, 4.340/13.020.
- **13.10.2026:** test anında 151 çekiliş, 3.020/9.060; 66 kayıtlı olmayan pozisyon raporlandı.

Test her çekilişte 20/60 tam ve ayrık olmayı, her sayının görünüş toplamının günlük gerçek çekiliş sayısına eşitliğini, TXT/CSV satır sayısını ve eksik/kesintili kayıtları kontrol etti.

## Dosyalar

- \`v18_cift_havuz.py\`: saf Python 20/60 ayrımı, kronolojik birikim, 80 sayının kimlik/serileri, 4 durumlu geçiş, TXT/CSV.
- \`v18_cift_havuz_app.py\`: Streamlit sekmesinin görsel arayüzü.
- \`v18_selftest.py\`: sentetik ve gerçek kayıt denetimi.
- \`.github/workflows/v18-check.yml\`: bağımsız test.
- \`v10_app.py\`: 15. sekme **🌓 V18 Çift Havuz**.

Mevcut \`app.py\`, \`veri.txt\`, V10–V17 motorları, aile CSV'leri ve kayıtlı kuponlar değiştirilmedi.
