# V12 — 80 Sayı Kulesi ve 2–10 Ailelerin Zaman Sırası

**Tarih:** 13 Ekim 2026  
**Veri:** GitHub veri.txt, 1 Ağustos–12 Ekim 2026 (73 gün, 15.839 çekiliş)  
**Test hedefi:** 7.434 bağımsız zamanlı hedef çekilişi (her normal saatin 7–12. slotları)  
**Yazılım:** v12_80_kule.py, v12_selftest.py; mevcut v10_app.py içindeki **🗼 80 Sayı Kulesi** sekmesi.

## A. Burada tam olarak neyi "sıra" kabul ediyoruz?

Hızlı On çekiliş sonucu 20 farklı sayıdan oluşan **bir kümedir**. Veride bunların 1–80 arasındaki **fiziksel makineden çıkma sırası** yer almıyorsa, sayıları küçükten büyüğe sıralamak gerçekte çıkış sırası vermez. **V12 fiziksel top sırası bulduğunu iddia etmez.**

Onun yerine iki geçerli sıra tanımlar:

1. **Ailelerin önceki çekilişlerde zaman sırası**: Bugünkü 20 sayı içinde bulunan bir 2'li, 3'lü, ..., 10'lu aile geçmişteki son 12 çekilişte hangi çekilişte ilk ve son kez birlikte görünmüş? Kaç önceki çekilişte görünmüş?
2. **80 sayılık kulenin önceden inşa sırası**: Önceki 12 çekilişin 240 sayılık verisinden en güçlü ikili, ardından üçüncü, dördüncü ve onuncu sayı hangi aşamada eklendi? Sonra kalan 10 sayı seçilerek 20'li kapanıyor. Bu sıra çekilişten **önce** sabitleniyor ve gerçek 20 ile karşılaştırılıyor.

## B. Tüm alt aile büyüklükleri

Her gerçek 20 sayının tam alt aile sayısı:

| Boyut | Matematiksel alt aile sayısı |
|---|---:|
| 2'li | 190 |
| 3'lü | 1.140 |
| 4'lü | 4.845 |
| 5'li | 15.504 |
| 6'lı | 38.760 |
| 7'li | 77.520 |
| 8'li | 125.970 |
| 9'lu | 167.960 |
| 10'lu | 184.756 |

Bu sayıların tamamını kayda dökmek yerine, **bugünkü 20 ile önceki 12'deki 20 sayının kesişimlerinden** daha önce gerçekten tam görünen tüm aileleri KESİN olarak buluyoruz. Böylece 10'luya kadar hiçbir aile boyutunu atlamadan pratik bellek ve hızda analiz ediyoruz.

**ÖNEMLİ:** Her 20 sayı 2+3+4+5+6 biçiminde daima bölünebilir; bu yalnız matematiksel bir ayrıştırmadır ve önceden tahmin başarısı değildir. V12 hem bu sonradan ortaya konan garantili ayrımı hem de **geçmiş çekilişlerde tam görünerek bugünkü 20'nin kaç sayısını açıklayabilen ayrık aileleri** ayrı kaydeder.

## C. 12 çekilişte 20 sayının oluşma yolculuğu

Her hedefte 12 geçmiş çekiliş sırayla taranır:

- Bugünkü 20 sayıdan kaç tanesi geçmişteki 1. çekilişte görünmüş?
- 2. çekilişte kaç yeni sayı ilk defa aktif olmuş?
- ...
- 12. çekilişin sonunda kaç farklı sayı geçmişte görülmüş, kaç sayı sessiz kalmış?
- Aynı sıra boyunca hangi tam 2'li, 3'lü, ..., 10'lu aileler ilk kez birlikte görünmüş?
- Her boyut için gerçek ilk görünüş adedinin **rastgele ve bağımsız 20/80 çekilişindeki beklenen adetten** farkı nedir?

**Bu yolculuk geçmiş çekilişlerdeki aktivasyondur; çekiliş anındaki gizli fiziksel çıkış sırası değildir.**

## D. İki ayrı araştırma: geçmişte aile var mı, geleceği tahmin edebiliyor muyuz?

### D1 — Geçmiş ailelerin bugünkü 20 sayıda taşınma oranı

Son 37 günlük bölüm; bir gerçek hedef 20 içinde mevcut alt ailelerin, önceki 12 çekilişte en az bir kez TAM görünmüş olanlarının ortalama sayısı:

| Boyut | Gözlenen | Matematiksel bağımsız beklenti |
|---|---:|---:|
| 2 | 99,453 | 99,721 |
| 3 | 175,147 | 175,979 |
| 4 | 173,787 | 175,135 |
| 5 | 117,983 | 119,562 |
| 6 | 58,658 | 59,951 |
| 7 | 21,975 | 22,697 |
| 8 | 6,275 | 6,569 |
| 9 | 1,356 | 1,460 |
| 10 | 0,213 | 0,249 |

Bu sonuçlar 2–10 aile tekrarlarının büyük bölümünün bağımsız çekilişlerde tesadüfen görülebilecek sıklıklara yakın olduğunu gösteriyor. Farkların anlamlılığı, çoklu karşılaştırma ve çekilişler arası örtüşme dikkate alınmadan "öngörü sinyali" ilan edilmez.

### D2 — Önceden seçilen 20 sayı vs gerçek 20 sayı

Her hedefte beş ayrı yöntem tam 20 farklı sayı seçer, ardından hedefin gerçek 20'siyle kaçının tuttuğu ölçülür:

| Yöntem | Son 37 günde 3.774 hedefte ortalama |
|---|---:|
| Önceki 12'de sık görülenler | 4,975 |
| Son 6–ilk 6 ivmesi | 5,027 |
| Son çekilişin 20 sayısını taşıma | 4,985 |
| Ağ-kule (ikili başlayıp 20'liye genişleme) | 4,965 |
| Rastgele 20 sayı | 5,006 |

Matematiksel beklenen sonuç her 20 sayılık kupon için 5/20'dir. **Hiçbiri belirgin üstünlük göstermedi; hiç 20/20 olmadı.**

Önemli: 20 sayılık ağ-kule 2'li, 3'lü, ..., 10'lu **iç içe büyüyen alt aileleri** saklar. Bir aile boyutu için k/k tutan sayı ancak çekiliş öncesinde oluşturulmuşsa test başarısı sayılır. Sonradan seçilen milyonlarca alt aileden birini başarı olarak seçmeyiz.

## E. Kontrol ve uygulama

- Dosyalar: v12_80_kule.py (aile ve kulenin motoru), v12_selftest.py (sentetik + tüm gerçek 73 gün); V10'da **🗼 80 Sayı Kulesi**.
- Uygulamada tek gerçek çekiliş seçilir; tam aile boyutu tablosu, geçmiş 12'deki 2–10 ailesi, zaman sırası, 2+3+4+5+6 ayrımı ve çekilişten önceki 20'li kuleden tutanlar görülür.
- V12 tüm test düğmesiyle çalışır ve CSV üretir: 7.434 hedef kayıtları, boyuta göre tekrarlar, aile aktivasyon sırası, 12 adımlık sayı hareketi, 20'li yöntem karşılaştırmaları ve 7–12 hedef sırası.
- Güncel veriler varsa yalnız **gelecekteki** bir hedefte 12 tam geçmiş çekilişi olan 7–12 arası slotlara kule önerisi yapılır.
- V9 app.py, veri.txt, v10_aileler.csv, v10_canli_kayit.json ve kayıtlı kuponlar korunur.

## F. Sıradaki bilimsel doğrulama

1. Bundan sonraki günler için model formülünü ve rastgele kontrolü kesin olarak sabitle.
2. Çekilişten ÖNCE hedef sırasını ve 20 sayılık öneriyi günlük kayıt dosyasına işle.
3. Tam isabet, ortalama isabet ve her 2–10 alt aile boyutunu sadece hedefin gerçek çıktısıyla doğrula.
4. Aynı anda birçok aile ve yol aramanın şans eseri güzel örüntüler doğurabileceğini unutma.
5. Eğer gerçek fiziksel top çıkış sırası araştırılacaksa **o sırayı içeren orijinal kaynak veri** gereklidir; numaraca sıralanmış 20 sayı yeterli değildir.

**Sonuç:** Bugünkü 20 sayı içinde 2–10 aileler ve onların geçmişten gelen zamansal görünüş sıraları hesaplanabiliyor. Ancak şu ana kadar bu düzenin gelecekteki çekilişe istatistiksel avantaj sağladığı kanıtlanmadı.
