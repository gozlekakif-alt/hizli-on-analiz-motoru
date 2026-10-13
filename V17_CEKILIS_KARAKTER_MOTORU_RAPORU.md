# V17 — Karakter motoru: Geçmişten geleceğe rakam değil çekiliş yapısı

**İstek:** "Geçmişten geleceğe bakacağımız şey karakter, rakam değil."  
**Tarih:** 13.10.2026  
**Dönem:** 01.08–12.10.2026, 73 gün.  
**Dosyalar:** v17_karakter_motoru.py, v17_selftest.py, v17_karakter_app.py; V10 → 🧬 V17 Karakter Motoru.

## 1. Karakterin anlamı

Çekilişte 80 sayı içinden seçilen 20 sayının **kimliğini** tahmin etmek yerine 20'linin matematiksel oluşum şeklini tanımlıyoruz. Karakter, fiziksel top sırası veya gizli RNG kodu DEĞİLDİR.

Her çekilişin karakter etiketi:

1. **Tekrar karakteri:** Önceki 20'nin kaçı kaldı? Kopuş=0–3, denge=4–6, taşıma=7+.
2. **Tek/çift koltuk dengesi:** Tek sayı oranı 0–7 / 8–9 / 10–11 / 12–13 / 14+.
3. **Alt/üst koltuk dengesi:** 1–40 ile 41–80 arasındaki doluş.
4. **Dört bant:** 1–20, 21–40, 41–60, 61–80 arasındaki dağılım; baskın bant veya yaygın.
5. **Komşuluk/küme karakteri:** Çekilen 20 içinde ardışık komşu bağlantılarının az/orta/çok olması.
6. **2–10 aile geçmiş izi:** Bugünkü 20'nin altındaki büyüklüğü k=2..10 olan ailelerin önceki 12'lik pencerede kaç *görünüş olayı* yaşadığı. Bu sayı benzersiz aile sayısı değildir; aynı aile ayrı önceki çekilişlerde tekrar sayılabilir.
7. **80 sayılık sıcak/ılık/soğuk koltuk doluşu:** Bugünkü 20'nin hangi mevcut havuzları beklenen paydan en çok aşarak doldurduğu; havuzlar bugünkü sonuç GÖRÜLMEDEN tanımlanır.
8. **Bileşik çekiliş karakteri:** Kopuş/denge/taşıma × dağınık/orta/kümeli.

Bir çekilişin karakteri SONUÇ GELDİKTEN SONRA hesaplanır. Bir sonraki çekilişe ait tahmin, sadece önceki çekilişlerin bilinen karakterleriyle yapılır. Testte gelecekteki gerçek 20 sayı öngörüye girmez.

## 2. Günün 217 çekilişinde karakter değişimi

V17 her günün çekilişlerine sıra, saat ve saat yarısı kimliği verir. 01:02→07:02 arasında altı saat bulunduğundan bu ara "normal 5 dakikalık karakter geçişi" sayılmaz. Eksik ardışık çekilişlerde geçiş oluşturulmaz.

Veri genelinde **15.691** beş dakikalık karakter gözlemi çıkarıldı. Modelin önceki karakteri ve en az 12 geçmiş çekilişi bilmesi gereken ayrı hedef sayısı eğitimde **7.302**, testte **7.511**'dir.

## 3. Önce 36 gün öğren, sonraki 37 günde gelecek karakteri sınama

- Eğitim: 01 Ağustos–05 Eylül 2026, 36 gün.
- Ayrı test: 06 Eylül–12 Ekim 2026, 37 gün.
- Tahmin seçenekleri: (a) gün bölümünün önceki sabit karakter frekansı, (b) gün bölümüne ve son bilinen karaktere koşullu geçiş olasılığı.
- Her iki modelin katsayıları yalnız ilk 36 gündeki veriden öğrenilir, test günlerinde değişmez.
- Aynı hedeflerin log-kaybı ve Brier hatası karşılaştırılır. Küçük daha iyidir. En olası sınıf isabeti tek başına önemli değildir; baskın sınıf tahmini yanıltabilir.

**37 gün / 7.511 hedefte geçiş modelinin sabit geçmişe göre LOG-KAYIP FARKI:**

| Karakter | Geçiş − sabit log-kayıp | Yorum |
|---|---:|---|
| Önceki sayı tekrarı | +0,000741 | Geçiş biraz kötü |
| Tek/çift koltuğu | +0,002931 | Kötü |
| Alt/üst koltuğu | +0,001533 | Kötü |
| Dört bant karakteri | +0,003562 | Kötü |
| Komşuluk karakteri | +0,000133 | Hemen hemen aynı |
| **2–10 aile iz karakteri** | **−0,000377** | Çok küçük iyileşme, kanıt değil |
| Sıcak/ılık/soğuk koltuk | +0,000586 | Hemen hemen aynı |
| Bileşik karakter | +0,004905 | Kötü |

**8 karakterden 7'si sabit karakter dağılımını geçmedi.** Aile izi karakterindeki −0,000377 kazanç küçüktür ve sekiz ayrı seçenek arandığı için gelecekte tekrar edeceği gösterilmedi. Sonuçlar adil RNG'nin kırıldığı anlamına gelmez.

### Yapısal ailelerin son 37 gün iz miktarı

Ayrı 37 gün boyunca, geçmiş 12 çekilişteki aile birlikte-görünme olayı ortalaması (yalnız BETİMSEL; aynı aile her önceki çekilişte yeniden sayılabilir):

| Aile | Ortalama iz olayı / hedef |
|---|---:|
| 2'li | 133,934 |
| 3'lü | 185,642 |
| 4'lü | 174,127 |
| 5'li | 117,034 |
| 6'lı | 58,269 |
| 7'li | 21,906 |
| 8'li | 6,257 |
| 9'lu | 1,339 |
| 10'lu | 0,205 |

Bu tekrar izlerinin bugünkü 20 sayının seçilmesini tahmin etmede avantaj sağladığı kanıtlanmış değildir.

## 4. Bundan sonra nasıl davranacağız?

- V17'yi "karakteri önceden öngörme" için kullan, rakam tahminiymiş gibi değerlendirme.
- Üst katman karakter → alt katman V12 aileler → V13 havuz koltukları → V15 kupon seçimi şeklinde kurulabilir, **ama karakter kapısı geçmişten bağımsız canlı testte rakip sabit modele göre anlamlı üstünlük verirse** kupon üretimini yönlendirsin.
- Şu an karakter geçişi böyle bir üstünlük göstermediğinden V15 kupon katsayıları aynen korunmuştur. Gereksiz yeni kuralla mevcut kuponu tarihsel veriye göre aşırı uyarlama.
- Yeni günlerde olasılıkları sonuç öncesinden zaman damgalı olarak kaydet; sonuç geldikten sonra her karakterin doğruluğunu raporla.
- RNG'nin algoritmasını yalnız sırasız 20'liklerden çıkardığını iddia etme.

## 5. Kullanım

Streamlit uygulamasında **🧬 V17 Karakter Motoru** sekmesi:

- İncelenen günün bütün 217 pozisyonundaki karakterleri tablo/CSV olarak verir.
- Düğmeyle 73 günlük karakter performansını 36/37 ayrımında analiz eder.
- Sekiz karakterin gerçek öngörü log-kayıp ve Brier karşılaştırmasını, saat ilk/son altı farklarını, aile izi boyutlarını ve geçiş tablolarını indirir.
- Bugünün sonucu henüz gelmemiş bir hedefi için son gerçekleşmiş çekiliş karakterini kullanarak sonraki karakterin olasılık dağılımını gösterir.

**Sınır:** Canlı karakter önizlemesi bir rakam kuponu veya kazanma garantisi değildir. Kullanıcının mevcut V9 veri.txt, V10–V16 motorları, aile listesi ve kupon kayıtları korunmuştur.
