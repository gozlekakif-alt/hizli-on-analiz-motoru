# V108 — 72 günlük yürüyen 672/56 halka: günün son saati

**16 Ekim 2026 araştırması.** Bu rapor doğrudan V104'ün gerçek yürüyen 672 çekilişlik 56 halka geçmişinden, her tam günün **23:02–23:57 son 12 çekilişini** ayırarak üretildi. Yeni halka mantığı kurulmadı, V104/V105/V106 değişmedi.

**Kaynak:** [V104 kodu](v104_72gun_basindan_672_56_halka_fifo_yon.py) ve onun 72 günlük sonuçları [Başarılı çalışma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38912727917). Oradaki `05_HEDEF_SAAT_80_SAYI_TAM56_YON_VE_GERCEK12.csv` içinden saat=23 olan 80 sayı kayıtları alınmıştır. Dönem: 04.08–12.10.2026, toplam **69 tam son saat** (ilk 672 çekiliş dolmadan önceki günler ve veri kümesinde bulunmayan 23 Ağustos hariç).

Her saat başlamadan önceki 672 çizilmiş sonuçta son altı tamamlanmış halkanın göreli 72-çekiliş sıcaklık sınıfı net artıyorsa **ısınan**, azalıyorsa **soğuyan**, aynıysa **dengeli**. Hedef saatinde kaç kez göründüğü yalnızca sonradan etiketlenir. 69 son saatte 69×80=**5.520 sayı-saat** gözlemi vardır.

## Son saatteki tarihsel tablo

| Önceden yön | Sayı-saat | 5+ | 6+ | 7+ | 8+ |
|---|---:|---:|---:|---:|---:|
| Isınan | 2.211 | 353 | 99 (**%4,48**) | 27 | 3 |
| Soğuyan | 2.205 | 334 | 132 (**%5,99**) | 38 | 11 |
| Dengeli | 1.104 | 170 | 57 (**%5,16**) | 17 | 3 |
| Toplam | 5.520 | 857 | 288 | 82 | 17 |

Günün son saatinde **6+ tekrarlı sayılar soğuyan kadroda daha sık**. Bu, sabit sayıların değil, her saatin başında oluşmuş **değişen yön gruplarının** sonuçlarıdır.

Ayrı dönemler de yön bakımından:
- İlk **34** son saatte ısınan 6+ **48/1083 (%4,43)**, soğuyan **58/1068 (%5,43)**.
- Son **35** son saatte ısınan 6+ **51/1128 (%4,52)**, soğuyan **74/1137 (%6,51)**.
- Gün bazında soğuyanın 6+ sayısı ısınandan fazla **38 gün**, ısınan fazla **15 gün**, **16 gün** eşit.

## 22. saatten 23. saate doğru yön zinciri

Hedef **23:02** başlamadan önce ilgili sayının **22:02 öncesindeki** ve **23:02 öncesindeki** tamamlanmış halka yön sınıfları karşılaştırıldı:

| 22→23 yön değişimi | Sayı-saat | Son saatte 6+ | Oran |
|---|---:|---:|---:|
| Soğuyan→Soğuyan | 1.572 | 91 | %5,79 |
| Isınan→Isınan | 1.528 | 70 | %4,58 |
| Isınan→Soğuyan | 274 | 18 | %6,57 |
| Soğuyan→Isınan | 307 | 7 | %2,28 |

Bu ayrımlar ilk 34 ve son 35 günlük bölümlerde aynı yönü göstermiştir, ancak küçük alt gruplar ve birçok keşif karşılaştırması kesin kurala dönüşmez.

**07:02 → 23:02 yön karşılaştırması** (ilk uygun günün 07 snapshot'ı mevcut olmadığından 68 tam çift): sabah ve gece hâlâ **soğuyan** 843 sayı-saatte **62 adet 6+ (%7,35)**; sabah ve gece hâlâ **ısınan** 856 sayı-saatte **34 adet 6+ (%3,97)**.

## Kritik ayrım: ilk altı mı, ikinci altı mı?

Son 23 saatte bütün 69 günlük gözlemlerde sayı başına ortalama:
- **Soğuyan:** ilk 6 çekilişte **1,531** kez, son 6 çekilişte **1,469** kez.
- **Isınan:** ilk 6 çekilişte **1,464** kez, son 6 çekilişte **1,540** kez.

Dolayısıyla soğuyanın son saatteki 6+ üstünlüğü, **son altı çekilişte daha sık gelmesiyle açıklanamaz**. Saatin başındaki görünüm ve dağılım kuyrukları da ayrılmalıdır. Bu ayrım V107'nin H1–H6 aynı sayıda görünen sayıları karşılaştırma amacını destekler.

## Gerçek gün sonu örnekleri

- **07.08:** 69, dengeli yönde **9** kez; 44, dengeli yönde **8** kez.
- **15.09:** 55, soğuyan yönde **9** kez.
- **11.10:** 63, soğuyan yönde **8** kez.
- **12.10:** 47, soğuyan yönde **8** kez.

**Dosyalar konuşma eki olarak oluşturuldu:** 69 günün bütün saat sonu tablosu, her gün×80 sayının tam 55/56 halka yön DNA'sı, 22→23 yön geçişlerinin dönemlik özeti, okunabilir TXT sonuçları tek ZIP içine alındı.

**Sınır:** Tüm sonuçlar 12 Ekim'e kadar geçmiş veri ile 23:02–23:57 saatlerine aittir; 16 Ekim'in güncel canlı çekilişleri değildir. Bu tarihsel yön farkı gelecekteki numaralar için isabet üstünlüğü kanıtlamaz. **Önümüzdeki araştırmada ilk 6 çekilişte aynı sayıda görünenleri eşleştirerek 7–12'nin farklılaşıp farklılaşmadığına bakılmalıdır.**
