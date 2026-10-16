# V113 — 56 Halka / 16'lık Havuz Giriş-Çıkış / Tek Çekiliş Mikro Analizi / Yedili Aile

**Tarih: 16 Ekim 2026.** Bu araştırma V104'ün çekiliş sonuçları ve 56 halka gerçek zaman dilimlerini kullanır. V100C–V112 motorları değiştirilmedi. **Bulgular geçmişteki betimsel mekanik ve karşılaştırmalardır; yeni hedeflere kanıtlanmış tahmin üstünlüğü değildir.**

## Ham veri ve rekonstrüksiyon denetimi

Kaynak: [V104 GitHub Actions](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38912727917), içindeki `05_HEDEF_SAAT_80_SAYI_TAM56_YON_VE_GERCEK12.csv`. Her hedef saat için **80 adet H1–H12 bit dizisi** aynen alınmıştır.

- **1.235 hedef saat, 14.820 gerçek çekiliş** tekrar oluşturuldu; her çekilişte **tam 20 farklı sayı** doğrulandı.
- En yeni tamamlanmış halkanın beş havuzuna karşı, geriye dönük **820 halka zaman noktasında tüm 80 sayının** yeniden hesaplanan havuzu **80/80 aynı çıktı**.
- Sıralama: Her sayı için sadece **son 72 gerçek çekilişteki** görünüm sayısı hesaplanır, eşitlikte küçük numara önce gelir, 80 sıra beş **16'şarlı** göreli havuza bölünür. Bu beş havuz sırasıyla **SOĞUK / SERİN / NÖTR / ILIK / SICAK**.
- 56 halka geçmişi V104'ün **gerçek fiziksel halka** hafızasından alınır. Hafızanın *ilk halkası*, hedef andaki 672 FIFO içindeki **en eski tamamlanmış halka** demektir; takvimdeki 1 Ağustos halkası demek değildir.
- Her hedef **23:02** başlamadan önce havuz hesaplanır. Ardından her 5 dakikada **çıkan 20 sayı havuza eklenir, 72 çekiliş önceki 20 sayı havuzdan çıkarılır**, sıralama yeniden kurulur. Sonucun değiştiği havuz **hedef çekilişten sonra** kaydedilir. Bu bilgiyi *önceki çekilişe tahmin olarak yansıtmak yasaktır*.
- 01:02 tek ek gece çekilişi bu V104 saat raporundan yeniden kurulmadığı için karşılaştırma **72 bilinen ardışık çekilişin mevcut olduğu 14:02–23:57 saatleriyle** sınırlandı. Günün 23:02–23:57 saati **69 günün 69'unda tamdır**.

## Gün sonu mikro veri

**69 × 12 × 80 = 66.240 sayı/çekiliş** olayı. Saat bazında kontrol: Aynı günlerin 14:02–22:57 arası **615 saat / 7.380 çekiliş**, toplam 14:02–23:57 karşılaştırması 8.208 çekiliştir.

**Bir yeni çekiliş 16'lık havuz üyeliklerini ortalamada kaç sayıda değiştirdi?**

| Saat | Her çekiliş sonunda havuz değiştiren sayı ortalaması |
|---|---:|
| Günün son saati 23:02–23:57 | **13,9251** |
| Aynı günlerde 14:02–22:57 | **13,8877** |
| Gün bazında eşlemeli ortalama fark | **+0,0315** |
| Yaklaşık %95 günlük fark aralığı | **−0,3861 ile +0,4491** |

**Yorum:** Gözlemlenen son saat havuz giriş/çıkış hareketinde anlamlı bir fazlalık kanıtlanmadı. Her bir 16'lık havuzdaki giriş ve çıkışlar sayı olarak zorunlu eşittir; çünkü kontenjan her çizimde 16'dır.

### Çekiliş sonucunun havuza mekanik etkisi

Hedef 23 saatlerindeki **16.560 çıkan-sayı olayı** içinde, sonuç *girildikten sonra*:
- **4.690 sayı** daha sıcak havuza geçti; **122** daha soğuk havuza geçti; **11.748** aynı havuzda kaldı.

Aynı hedeflerdeki **49.680 çıkmayan-sayı olayı** içinde:
- **1.075** daha sıcak, **5.643** daha soğuk havuza geçti; **42.962** aynı havuzda kaldı.

**Bu çok güçlü görünen ilişki tahmin değildir:** Havuz sıralaması yeni çekilişin kendisinden hesaplanır; çıkış sonucu yeni sıralamaya sebep olur. Hedef çekilişten *önceki* son bir çekilişte görülen yönü koşul olarak kullanınca, **sonraki çekilişte** görünme oranları **önceden yükselmiş %24,72, düşmüş %25,35, sabit %24,99**; her biri teorik %25'e yakındır. Bu sonuç hedef çekilişi görmeden üretilen bir işaretin tarihsel sınamasıdır.

## Gerçek yedili aile — hedef 23:02 başlamadan belirleme

Bu bir örnek hipotezdir: **22:02–22:57'deki son 12 gerçek çekilişin içinde, en güncel ortak kesişimi tam yedi sayı olan iki geçmiş çekiliş** seçilir. Hedef 23:02 sonuçları seçimde kullanılmaz; önceki günlerdeki bütün olası yedili aileler taranmaz. Böylece her gün en fazla **bir adet yedili aday** oluşur.

- **69 günün 68'inde bir yedili aday**, kalan bir günde yok.
- Hedef saatlerin **68×12 = 816** tek çekilişine aynı önceden sabit aile uygulanmıştır.
- Bir çekilişte aileden ortalama **1,748/7** sayı görünür. Rastgele yedili kontrol **1,732/7**; 23:02 öncesindeki havuz sınıfları bire bir eşleştirilmiş başka 7 sayı kontrol **1,674/7**.
- **5/7 veya üzeri:** aile **5/816**, rastgele kontrol **10/816**, havuz eşli kontrol **6/816**.
- **6/7 veya üzeri:** aile **0/816**, rastgele **2/816**, eşli **0/816**.
- **7/7:** üç yöntemde de **0**.
- Sabit herhangi yedi sayının adil 20/80 çekilişte **5+/7** yapma olasılığı **%0,93950**; 816 çekilişte beklenen yaklaşık **7,67** olay. Ailenin bulduğu beş olay **üstünlük kanıtlamıyor**.
- Gün bazında yedili aile ile rastgele kontrolün çekiliş başına ortalama isabet farkı **+0,0159**, yaklaşık %95 günlük aralık **−0,0946 ile +0,1265**. Havuz eşli kontrol farkı **+0,0735**, aralık **−0,0426 ile +0,1897**. Her iki aralık da sıfırı içeriyor.
- İlk34 dönem aile ortalama **1,723**, son35 dönem **1,772**; rastgele kontrol ilk34 **1,635**, son35 **1,828**. Aradaki yer değiştirme güçlü öngörü kanıtı değildir.

### Somut 19 Ağustos 2026, 23:02 çekilişi

**Yedili aile:** `17-24-32-38-60-61-68` — 23:02 *öncesinde* 22. saatin iki çekilişindeki yedi ortak sayıdan seçildi.

**23:02 çekilişinde ailenin beş üyesi birden çıktı:** `32-38-60-61-68`. Hedef sonrasında grup üyelerinin **hiçbirinin havuz seviyesi değişmedi**. Dolayısıyla *aynı çekilişte 5/7 çıkma*, mutlaka beş sayının o çizimde havuza girmesi veya havuz değiştirmesi demek değildir.

| Sayı | 672 FIFO içindeki 1. tam halka havuzu | H23 H1 öncesi canlı havuz | 23:02'de çıktı mı? | H23'te 12 çekilişte toplam |
|---:|---|---|---|---:|
| 17 | SICAK | SOGUK | Hayır | 2 |
| 24 | SICAK | NOTR | Hayır | 5 |
| 32 | NOTR | ILIK | **Evet** | 5 |
| 38 | ILIK | SERIN | **Evet** | 5 |
| 60 | SICAK | SICAK | **Evet** | 4 |
| 61 | SERIN | SICAK | **Evet** | 4 |
| 68 | SERIN | SICAK | **Evet** | 6 |

Gördüğümüz gibi **aynı anda çıkan beş aile üyesi başlangıçta beş havuzun farklı yerlerinde bulunabiliyor**. Tek başına sıcak havuzda beş üye şartı 5/7'yi açıklamıyor.

## Yöntem ve dosyalar

Bu araştırmanın kullanıcıya sunulan `V113_56_HALKA_16_HAVUZ_7LI_AILE_ADIM_ADIM_ANALIZ.zip` arşivi:

- `00_V113_TURKCE_KISA_ARA_KUTUK.txt`, `00_V113_KESIN_MIKRO_BULGULAR.json` — sayısal denetim ve Türkçe sonuç.
- `01_69GUN_SON_SAAT_HER_CEKILIS_80_SAYI_16_HAVUZ_GIRIS_CIKIS.csv` — **66.240** sayı/çekiliş giriş-çıkışı, önceki yön, sonraki yön, 1. halka kimliği, H22 yedili aday üyeliği.
- `02_69GUN_14_23_SAAT_KIYAS_GIRIS_CIKIS.csv` — **8.208** ardışık çekilişin havuz değişim ve kontenjan muhasebesi.
- `03_7LI_AILE_1_HALKA_56_HALKA_H23_KIMLIK.csv` — **476 aile-sayı** kaydının ilk halka, son halka ve tam 55/56 havuz dizisi.
- `04_7LI_AILE_HEDEF_SAAT_12_CEKILIS_DEGISIM.csv` — **816 aile/hedef çekiliş** kaydı; gerçekte birlikte çıkanlar ve havuz eşli kontrol.
- `05_69_GUN_H22DEN_7LI_AILE_SECIMI.csv`, `06_23_ONCESI_YON_SONRAKI_CEKILIS_HAVUZ_ESIT.csv`, `07_GUN_GUN_23_VS_14_22_HAVUZ_GIRIS_CIKIS_FARK.csv`, `V113_TEKNIK_TEKRARLANABILIR_ANALIZ_KODU.py`.

**Araştırma sınırı:** Bunlar daha önce defalarca kullanılmış 72 günlük tarihsel verilerden oluşturulmuştur. V97'nin sonradan kurulmuş 7'li aile kataloğu bu testte kullanılmamış; aileler hedef öncesindeki iki geçmiş çizimin kesişiminden oluşturulmuştur. 23:02 hedeflerine gerçek ileriye dönük kupon üstünlüğü gösterilmedi. **V113, gösterdiği eski hareketleri gelecekteki hedef saat sonuçlarının nedeni veya RNG seed çözümü gibi sunmaz.**
