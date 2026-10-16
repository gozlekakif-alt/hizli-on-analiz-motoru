# V112 — 56 halka: beş havuz turu, son saat ve altılı aile ayrımı

**Tarih:** 16 Ekim 2026. **Durum:** Tarihsel keşif / kupon üstünlüğü doğrulanmadı.

## Kullanıcının hipotezi
Yalnız sıcak sayı seçmek yerine 672 çekilişlik kayan 56 halkada sayıların beş havuzda dolaşmasını, bir çevrimi tamamlamasını, 6'lı aile üyelerinin birlikte yer değiştirmesini ve hedef çekilişte ailenin üyelerinin gelmesini birbirinden ayır.

## Veri ve kesin tanımlar
- Kaynak: bu deponun `veri.txt` dosyası (Git blob SHA `c0fd63c33696622e56fe7c9c427a65ef49954874`).
- 1 Ağustos–12 Ekim 2026: 72 geçerli tam gün = **15.624 çekiliş**; eksik 23 Ağustos dışarıda. Her günün 23:02–23:57 arasındaki son saati; 672 geçmiş çekiliş tamamlandıktan sonra **69 son saat**.
- Her hedef saatin **23:02 öncesindeki** [t−672, t) geçmişinden 56 tane 12 çekilişlik halka çıkarıldı. Halkanın sonunda yalnız o ana kadarki **son 72 çekiliş** sıklığı ile 80 sayı sıralandı (eşitlikte küçük sayı önce). Beş göreli havuzda daima **16 sayı** bulunur: soğuk, serin, nötr, ılık, sıcak.
- **Tur bitirme (araştırma tanımı):** Her sayı için ilk halkadan itibaren görülen farklı havuzlar kaydedildi; beş ayrı havuzu ziyaret edince bir tur sayıldı ve sonraki halkadan itibaren yeni tur için kayıt sıfırlandı. Sıralı soğuk→sıcak rotası veya aynı saat içinde tüm beş havuzu ziyaret etme zorunluluğu **yoktur**. "Son 6 halkada tamamladı" bu tanımla 51.–56. halkalarda tur kapanması demektir.
- **Altılı yön ailesi (dar test tanımı):** Önceden son üç ardışık halka geçişinin sıcaklık yönü (yukarı, aşağı, eşit) tamamen aynı olan **tam altı sayılık** imza grubu. Bu, V10 katalog ailesi/V58 kök aile ile **aynı tanım değildir**.
- Yalnız hedef saatin 7.–12. çekilişi sonuç ölçümüdür (her sayı için altı adet 0/1 sonucu). Gruplar hedef saat başlamadan belirlenir; hedef çekilişlerle sonradan aile kurulmaz.

## 69 günün somut bulgusu

- **5.520 sayı-saat** kayıtlarının **5.369'u** 56 halka boyunca beş havuzun tamamını görmüştür (**%97,26**); **151'i** tüm beş havuzu görmemiştir.
- **69 son saatin 8'inde**, 80 sayının 80'i de 56 halka boyunca bütün beş havuzlara uğramış durumdaydı (**%11,59**).
- Sayı-saat başına turunu son altı halkada bitiren ortalama **21,97 sayı**; toplam **1.516 sayı-saat**.
- Son altı halkada tur tamamlayanların sonraki H7–H12 bir çekilişte görünme oranı **%24,538** (1.516 sayı-saat); diğerlerinin **%25,175** (4.004 sayı-saat). Matematiksel nötr oran, bağımsız ve adil 20/80 için **%25**.
- Son altı tur tamamlayanlar / diğerleri: **ilk 34 gün %23,819 / %25,460**; **son 35 gün %25,265 / %24,902**. Üstünlük yönü dönemlere göre tersine döndü.
- Son havuzu sıcak olan ve turunu son 6 halkada tamamlayanlarda **%26,153** (383 sayı-saat), diğer sıcaklarda **%25,312** (721). Son havuzu soğuk olan yeni tamamlayanlarda **%23,622** (381), diğer soğuklarda **%25,795** (723). Bunlar küçük alt gruplardır; son sıcaklık ve önceki ilk 6 çıktıları kontrollü ileri model karşılaştırması değildir.
- Altılı aynı-yön aileleri: **57 aile/saat olayı**, toplam 342 sayı-saat. Üyelerin H7–H12'de görünme oranı **%25,195**, altılı aile dışındakiler **%24,987**. Dönemler: ilk 34 gün aile üyeleri **%25,926**, son 35 gün **%24,537** (güçlü ve kalıcı fark yok).
- Bu **57 dar tanımlı altılı ailenin hiçbirinde** son halkanın sıcak havuzunda birden **5 veya 6 üye yoktu**. Sıcak üye sayısı dağılımı (0,1,2,3,4,5,6): **37,8,8,3,1,0,0**. Bu **başka aile tanımlarında** 5 sıcak üye bulunmadığı anlamına gelmez.
- Bu 57 altılı aile için her birinin hedef saatinin 7.–12. çekilişindeki altı hedefte sabit altılı kupon kontrolü: **342 aile-kupon**, **2 kez 5/6**, **0 kez 6/6**. Adil bağımsız 20/80 için teorik **5+/6 olasılığı 0,00322462**, dolayısıyla 342 kuponda rastlantısal beklenen 5+ **1,10**; 2 gözlem üstünlük kanıtı değildir.
- Belirtilen aile alt grupları aynı havuz üyeliğini paylaşmak ve tüm 80 sayının beş havuzu dolaşması gibi göreli sıralamalardan da doğabilir.

## Ne öğrendik, neyi öğrenmedik?
1. **Havuz turu gerçekten sayılabilir, ama bitirmek sonraki çekiliş için matematiksel zorunluluk doğurmaz.** Yeni bitirenlerin bütününün isabet oranı adil %25 civarında.
2. **80/80 tur bitirdi** göstergesi, tek başına hangi sayının çıkacağını seçmez; tüm sayılar için aynı bilgi.
3. **Aynı üç yönlü tam altılı** aile, kullanıcının tarif ettiği sıcak havuzda beş üye birikme / eski kayıtlı aile parçalarının yeniden birleşmesi kavramını yeterince temsil etmeyebilir.
4. V109–V111'deki ilk 6 çekiliş ve sıcaklık kontrollü karşılaştırmalarda da halka özetleri / sıra modeli kalıcı kupon avantajı üretmedi; geçmişte 5/5 örneklerinin yüksek görünmesi bir garanti değildir.
5. Geçmiş günler daha önce çok sayıda model için kullanıldı; son 35 gün gerçekten görülmemiş prospektif veriler değildir.

## Sonraki özgül araştırma
**V113 için önerilen hipotez (henüz test edilmedi):** V10/V58'de **hedef öncesinde kayıtlı gerçek 6'lı aileleri** al; her halkanın sonunda altı üyenin beş sıcaklık havuzundaki konumunu ve tur kapatma sırasını izle. Aile içinden 4/6, 5/6, 6/6 üyenin aynı havuz/havuz geçişinde olup olmadığı, hangi üyenin gruptan ayrıldığı, hedef H7–H12'de 4+/5+/6+ ile eşleşmesi ayrı test edilsin. İlk 6 sonuç, son72 sıcaklık ve aile büyüklüğü eşitlenerek yeni veride ileriye dönük kuponları önce dondurup sonra skorla. Rastgele ve HOT72 ile aynı sayıda kupon karşılaştır; önceden belirlenen katı eşikler başarısızsa kupon üretme.

Bu rapor yeni başarı iddiası değil; dar, yeniden üretilebilir bir tarihsel sorgulamanın ara kütüğüdür.
