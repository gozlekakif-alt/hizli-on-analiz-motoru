# V15 — Altı 10'lu Kupon ve 2–10'lu Aile Motoru

**Kurulum:** 13 Ekim 2026  
**Kod:** v15_kupon_motoru.py, v15_selftest.py, v15_coverage_test.py  
**Uygulama:** V10 Streamlit → 🎟️ V15 Kupon Motoru  
**Test:** İlk 36 gün eğitim (01 Ağustos–05 Eylül), sonraki 37 gün kronolojik değerlendirme (06 Eylül–12 Ekim). Bu, gerçek tarihli canlı kör test değil; geriye dönük keşif amaçlı zaman ayrımıdır.

## Neler üretir?

Her normal saatin 7–12. çekilişlerinden biri henüz gelmemişse, günün önceki kayıtlarından ve son 12 çekilişin tamamından **altı farklı 10 sayılık kupon** oluşturur.

1. V12 aile omurgası.
2. V13 sıcak/ılık/soğuk koltukları.
3. V14 +1 çekiliş geçiş ilişkileri.
4. V14 +1/+2/+3/+6/+12 gecikmeli ilişkiler.
5. V12/V13/V14 birleşik aile kulesi.
6. Diğerlerinden daha az ortak sayı tutmaya çalışan dağıtılmış aile kulesi.

Her 10 sayılık kuponun ilk 2, 3, 4, 5, 6, 7, 8, 9 ve 10 sayılık ailesi **hedef çekilişten önce** tanımlanır. Bir onlu kupon kazandıktan sonra içinden altılı seçilip tahmin başarısı diye sayılmaz.

**İki ayrı kupon düzeni** vardır:
- **Aile odaklı:** Motorların özgün sıralarından kupon seçer.
- **Geniş kapsama (sonradan geliştirilmiş):** Birinci kupon hariç her kupon en az 7 daha önce seçilmemiş sayı içermek zorundadır. Bu tasarım Aile odaklı testin sonucunu gördükten sonra geliştirildi; aynı tarihlerdeki performansı yeni bir bağımsız kör test sayılmaz.

Her hedefe ayrıca aynı sayıda **6 rastgele 10'lu kontrol** üretilir; tüm başarısızlıklar sonuç defterinde kalır.

## Test kapsamı ve aile odaklı ilk sürümün bulguları

| Ölçüm | Değer |
|---|---:|
| Test edilen ayrı çekiliş | 3.774 |
| Motor onlu kuponu | 22.644 |
| Rastgele onlu kontrol | 22.644 |
| Karşılaştırılan toplam onlu | 45.288 |

| Kupon başına 10'da ortalama | Sayı |
|---|---:|
| V12 aile omurgası | 2,5074 |
| V13 ısı koltukları | 2,5262 |
| V14 +1 geçiş | 2,4547 |
| V14 çoklu gecikme | 2,4470 |
| Birleşik aile kulesi | 2,4878 |
| Dağıtılmış aile kulesi | 2,5278 |
| 6 rastgele kontrol (her onlu) | 2,4810 |

**Altı onlu kuponun her hedefteki en iyi isabeti:**
- Aile odaklı motor: **3,933/10**.
- Aynı hedefte altı rastgele: **4,1388/10**.
- Motorun önceden belirlenmiş 6 sayılık aileleri: 4 kez 6/6; kontrol: 5 kez 6/6.
- 10/10: Hiçbir yöntemde yok.

**Altı kupon birlikte kaç farklı sayı kapsıyor?**
- Aile odaklı: ortalama **33,223** farklı sayı.
- Rastgele altı: ortalama **44,099** farklı sayı.

Bu fark, kupon motorunun aynı sayıları tekrar tekrar seçtiğini gösteriyor. Geniş kapsama seçeneği bu tekrarı azaltmak için geliştirildi. Sonuçlarına bakarak motoru yeniden ayarlayıp aynı 37 günü yeni kör test diye göstermeyeceğiz.

## Kayıt ve denetim

Uygulamada kullanıcı **V15 Kupon Motoru** sekmesinden test raporunu CSV indirebilir; ayrıca gelecek 7–12 hedefi için altı kupon ve her birinin 2–10 aile merdiveni önceden üretilebilir.

**Kalıcı kayıt** ancak mevcut V10 yönetici PIN kilidi açıldıktan sonra ve hedef saatinden ÖNCE kullanıcı düğmeye basarsa gerçekleşir. Kayıt mevcut V10 canlı kupon dosyasına eklenir, sonuç daha sonra mevcut **📊 İsabet** tablosundan incelenir. Hedef saati geçmiş veya sonucu kayıtlı bir çekilişe sonradan kupon eklemek yasaktır.

Ana veri.txt, önceki aile CSV, V9 app.py, eski kuponlar ve V10–V14 analizi değiştirilmedi.

## İstatistiksel dürüstlük

Adil bağımsız 20/80 çekilişinde belirli bir 10 sayılık kuponun ortalama isabeti **2,5/10** ve önceden seçilmiş 6 sayının tamamının gelme olasılığı comb(20,6)/comb(80,6) oranıdır. Geçmişte sıcaklık, geçiş veya aile sırası gözlenmiş olması tek başına sonraki sonuçların şansını değiştirmez.

V15'in görevi **gerçekten başarısı ölçülebilir, önceden belirlenmiş kuponlar üretmek ve hatalı görünen sinyalleri ayıklamak**; kazandıracağına dair sahte vaat vermek değil.
