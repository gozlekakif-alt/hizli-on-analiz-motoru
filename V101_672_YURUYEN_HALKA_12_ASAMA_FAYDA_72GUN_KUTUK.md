# V101 — Yürüyen 672 çekiliş halkası: hangi aşama bize fayda sağlıyor?

**Sonuç:** 16 Ekim 2026. V100A ve V100C algoritmaları değiştirilmedi; yeni V101 yalnızca **yürüyen 672 geçmiş / 12'li sabit halka** sistemine davranış incelemesi ekler.

**GitHub çalışma:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38902136012 — **SUCCESS**  
**Kaynak kodu:** [v101_yuruyen_672_halqa_1_12_fayda_kor_test.py](v101_yuruyen_672_halqa_1_12_fayda_kor_test.py)  
**Kapsamlı ZIP:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38902136012/artifacts/12047061598

## Gerçek halka mekanizması

Her yeni gözlenen çekilişte 672'nin en eskisi çıkar, yeni çekiliş eklenir. 12 gözlemle bir halka mühürlenir. Halka kimlikleri sıfırlanmaz. 12'lik bölüm bitimlerinde 56 tam halka; geçiş anlarında 55 tam + 2 kısmi halka vardır. Hedefe yeni çekilişin kendisi dahil edilmez.

Program 72 tam tarihi günü ve depoya eklenmiş 13 Ekim 2026 tarihli **166 yeni çekilişi** işler. Son kaynak kayıt **#62014**, 13.10.2026 **19:57**. İncelenen hedef çekiliş sayısı **15.058**. Kaynakta daha sonraki günler olmadığından sonrasını **uydurmaz**.

Her hedefin önünde 56 halka FIFO belleği korunurken, yeni halkanın **1–12. gözlemi**, son 72 çekilişin havuzları, son tamamlanmış halka, son altı tamamlanmış halkanın yönü, yeniden toparlanma ve sıcaklık geçmişi izlenir.

## On yöntemin başa baş testi (aynı hedeflerin 20 sayısına karşı)

İlk 36 tam gün araştırma, sonraki 18 gün **doğrulama/seçim**, sonraki 18 gün **tarihsel holdout**. 13 Ekim kayıtları **NEW_DATA**, yalnız bir gün ve 166 gözlemden oluştuğu için ayrıca raporlanır. Ortalama isabetlerin teorik sabit 20'li seçim beklentisi **5**.

| Yöntem | Doğrulama /20 | Son 18 gün /20 | 13 Ekim /20 (166 hedef) |
|---|---:|---:|---:|
| HOT72 (referans) | 5,022529 | **5,023554** | 4,674699 |
| PREVIEW_POOL, dolan yeni halka | 5,041475 | 5,042499 | 4,566265 |
| PREVIEW_COUNT, yeni halka görülme sayısı | 5,047107 | 5,021249 | 4,656626 |
| **PREVIEW_PLUS_72** yeni halka + son 72 | **5,053507** | **5,008961** | **4,662651** |
| RISING_SEALED6, son 6 dolu halkanın yönü | 5,004096 | 5,021249 | 4,909639 |
| LAST_COMPLETED_RING | 5,040963 | 4,973118 | 4,759036 |
| RANDOM20 kontrol | 5,008961 | 4,983871 | 4,903614 |

**Seçim kuralı:** Orta 18 günlük doğrulamada HOT72'ye en çok üstün görünen `PREVIEW_PLUS_72` seçildi; son 18 gün üzerinde *bu seçim değiştirilmeden* kontrol edildi.

- Doğrulama üstünlüğü **+0,030978** isabet/20'li seçim.
- Son 18 gün gerçek üstünlük **−0,014593** (tersine döndü).
- Takvim günü eşleştirmeli yaklaşık %95 aralık **[−0,063899, +0,034713]**, sıfırı içeriyor.
- 13 Ekim yeni kayıtlarında da seçilen yöntem HOT72'den **−0,012048** geride.

**Karar:** Bu önceden tanımlanmış seçme yöntemi, kontrol dönemlerinde güvenilir biçimde kazanmadı. Mekanizma doğru çalışıyor, doğrulanmış tahmin artışı çıkmadı.

## Hangi halka evresi davranış değiştiriyor?

Halkanın **kaç çekilişle dolduğu**na göre `PREVIEW_POOL` yöntemi, son 18 günlük aynı hedeflerde HOT72'ye göre:

| Yeni halkanın doluluğu | İncelenen hedef | Ortalama ilave 20'li isabet |
|---|---:|---:|
| 1/12 | 325 | +0,0554 |
| 2/12 | 325 | +0,0523 |
| 3/12 | 325 | −0,0985 |
| **4/12** | 325 | **+0,1446** |
| **5/12** | 325 | **+0,1354** |
| 6/12 | 326 | −0,0399 |
| 7/12 | 326 | +0,0337 |
| 8/12 | 326 | −0,1135 |
| 9/12 | 326 | +0,0798 |
| 10/12 | 326 | −0,1043 |
| 11/12 | 326 | +0,0644 |
| 12/12 | 325 | +0,0185 |

**Dikkat:** Bu tablo keşif amaçlıdır. Örneğin 4/12 son 18 günde artı verse de, 13 Ekim'in yalnız 14 örneğinde **−0,0714** olmuş; 5/12 orta 18 günlük doğrulamada **−0,0184** olmuş. Bu yüzden bu aşamaları 'kanıtlanmış avantajlı saatler' olarak seçmiyoruz. Çoklu alt grup arama hatası olasılığı yüksektir.

## Halkanın 5 havuzunun gerçek hedefteki görülme oranları

Yeni/aktif halkada sayının **içinde bulunduğu göreli havuz** bazında, son 18 günlük tarihsel hedefte çıkış sıklığı:

| Havuz | Son 18 gün | 13 Ekim (166 hedef) |
|---|---:|---:|
| Soğuk | %24,9264 | %26,4684 |
| Serin | %25,1536 | %24,3223 |
| Nötr | %24,8672 | %26,0166 |
| Ilık | %24,7872 | %25,5648 |
| Sıcak | %25,2656 | %22,6280 |

Havuz etiketleri aynı çekilişte 80 sayının **eşit 16'şarlı frekans sıralamasından** oluşturulur; 13 Ekim'de sıcak havuzun %22,63'e inmesi dikkat çekici bir **gözlem** ama çok kısa bir seri. Tek başına gelecek hedefte geri döneceğini veya sıcak havuzdan kaçınmayı kanıtlamaz.

## Buradan kazandığımız araştırma kabiliyeti

1. **Sabit halka kimliği:** Yeni çekilişte eski halkanın hangi kaydı bıraktığı ve yeni halkaya ne eklendiği denetleniyor.
2. **Evrelere ayrılmış analiz:** 1/12 ... 12/12 aşamalarını karıştırmadan, her birinin getirisi gerçek hedeflerde ölçülüyor.
3. **Sıcaklık geçişleri:** Yeni kısmi halkanın soğuk–sıcak sınıfı, önceki 72'lik sınıf ve son altı tamamlanmış halkanın yönüyle birlikte, 80 sayı bazında raporlanıyor.
4. **Gelişen sistem:** Yeni tarih eklendikçe FIFO hafızası kaybolmuyor; GitHub workflow yeniden çalışıyor.
5. **Hedef öncesi kayda alma:** Mevcut veri **#62014'te** duruyor. V101 ZIP içinde **henüz görülmemiş sıradaki çekilişe** ait hedef ID uydurmadan hazırlanmış, tarihsel doğrulamada seçilmiş yöntem ve 80 sayı özellikleri bulunuyor. Bunlar *test edilmemiş araştırma öngörüleridir*; kupon önerisi değildir.

**Sınırlama:** 72 günlük tarihsel veriler V9–V100 sırasında da tekrar tekrar incelendi; sonuçları kesin 'kör test' veya çözümlenmiş RNG gibi sunmuyoruz. 13 Ekim yalnız 166 hedef, farklı modellerin gelecekte kalıcı avantajını belirleyemez. Yeni, gerçekten gözlenmemiş tarihler gelmeden üstünlük iddia edilmemeli.

## Tam ZIP'in 10 dosyası

`00_V101_YURUYEN_HALKA_FAYDA_SONUCLARI.txt`, `01_10_YONTEM_36_18_18_YENI_VERI.csv`, `02_12_ASAMA_AYRI_10_YONTEM_KONTROL.csv`, `03_HER_HEDEF_ONCEKI_672_SABIT_HALKA.csv`, `04_HER_ASAMA_5_HAVUZDA_HEDEFTE_GELME.csv`, `05_72_VE_YENI_HALKA_HAVUZU_25_ESLESME.csv`, `06_ONCEKI_HALKANIN_YONU_ILE_HAVUZ.csv`, `07_SON_GERCEK_CEKILISTEN_SONRA_80_SAYI_DIAGNOSTIK.csv`, `08_ONCEDEN_SABITLENMIS_GORULMEMIS_HEDEF.json`, `09_VERI_VE_GERIYE_SIZMA_DENETIMI.json`.
