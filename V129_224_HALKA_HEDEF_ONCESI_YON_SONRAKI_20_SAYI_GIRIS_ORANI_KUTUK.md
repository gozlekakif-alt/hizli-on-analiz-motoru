# V129 — Çekiliş gelmeden ÖNCE 224 halkanın yönü sayıların SONRAKİ hedef20'ye girmesini nasıl etkiliyor?

**Gerçek çalışma:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/39011511126

**Kalıcı ZIP (9 dosya):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/download/v129-2026-10-13-pretarget-ring-direction-vs-next20/V129_HEDEF_ONCESI_224_HALKA_YON_ETKI_KOR_TEST.zip

**Tekrar çalıştırılabilen program:** [v129_hedef_oncesi_224_halka_yon_20_sayi_etki_test.py](v129_hedef_oncesi_224_halka_yon_20_sayi_etki_test.py)

## ÖNEMLİ: Yönler hedef çekilişten ÖNCE hesaplandı

Kaynak 15.790 gerçek çekiliş, son #62014 (13.10.2026). **İlk 2688 çekiliş** öğrenilen tarihsel hafıza. Sonrasında **13101 gerçek HEDEF** için, hedef çekiliş `t+1` sonucu kullanılmadan, sadece en son bilinen `t` çekilişinde oluşan **224 iç içe halka (12,24,…2688) × 80 sayı** eski→yeni havuz yönleri çıkarıldı. Beş havuz her halka içinde eşit 16'şar sayıdır; sayı ID eşitlikte önce gelir. Hedef `t+1` sonucu daha sonra yalnızca 0/1 isabet denetiminde okunur.

Her sayı-çekiliş için hedef ÖNCESİ koşullu P = sonraki çekilişte sayı 20'lide var olduğu vakalar / bu koşula uyan tüm sayı–hedef vakaları. Adil bağımsız 20/80 koşulsuz matematiksel P **%25**. 29 farklı öncü sinyal, 25 eşit kupon bütçeli sayı seçim modeli, k=3,4,5,6,8,10,20 kupon boyları tarandı. İlk36 gün TRAIN, sonraki18 VALIDATE, daha sonraki18 LAST18 kronolojik; ancak **bu tarihler daha eski V9–V128 çalışmalarında çok kez görüldüğü için hiç incelenmemiş gerçek ileriye dönük harici kör test değildir**.

## Gerçek yüzdeler

| Hedef öncesi 224-halkada sayı hareketi | VALIDATE18 hedef20 çıkış yüzdesi | LAST18 hedef20 çıkış yüzdesi | LAST18 sayı–hedef deneme N |
|---|---:|---:|---:|
| Yalnız ısınma (hiç soğuyan halka yok) | **%24,73175** | **%24,40789** | 39.815 |
| Yalnız soğuma (hiç ısınan halka yok) | %25,25441 | %24,73746 | 33.423 |
| Hem ısınma hem soğuma (karışık yön) | **%25,00632** | **%25,14647** | 236.395 |
| Isınma baskın | %24,94966 | %24,91736 | 83.195 |
| Soğuma baskın | %25,00636 | %25,03228 | 219.984 |
| Kısa 56 halkada ısınıp en uzun 56 halkada soğuma baskın | %25,50770 | %25,52204 | 5.603 |
| En uzun 56 halkada soğuma baskın | %25,09131 | %25,22478 | 115.335 |
| En az 40 halkada ısınma | %24,88038 | %26,24113 | 282 |
| Matematiksel adil oyun referansı | **%25** | **%25** | — |

**Gün-kümeli %95 bootstrap** için LAST18'de aynı dönemin koşula UYMAYAN diğer sayı–hedef çiftlerinden farkı (**yüzde puan**, yani 0,60pp = %0,60'lık mutlak çıkış olasılığı değişimi):

- Yalnız ısınma: **−0,67857 puan**, %95 gün-blok aralığı **[−0,97826, −0,35316]**; VALIDATE18 farkı da **−0,30708 puan**. İki dönemde de yön negatiftir; ancak bu V129'da yapılan pek çok sinyal karşılaştırmasından biridir ve hiç kullanılmamış bir ileri tarihte yeniden sınanmalı.
- Hem ısınma hem soğuma: LAST18 **+0,60155 puan**, %95 gün-blok aralığı **[+0,25264,+0,95122]**. Fakat bir önceki VALIDATE18'de fark **yalnız +0,02632 puan**; kalıcı, güçlü ve istikrarlı avantaj gibi okunmamalı.
- Yalnız soğuma: LAST18 **−0,29399 puan**, %95 gün-blok **[−0,69871,+0,14671]** ve önceki VALIDATE18 yönü ters (+0,28467 puan).
- Kısa halka sıcak, uzun halka soğuk: LAST18 **+0,53157 puan**, %95 **[−0,54496,+1,67538]**; belirsizlik yüksek.
- 40+ halkada ısınma: LAST18 **+1,24226 puan**, %95 **[−3,21767,+5,70176]**; yalnız **282** sayı–hedef vakası, değişim rastlantı uyumlu.

## Belirli kupon seçiminde işe yaradı mı?

VALIDATE18 10 sayılık ortalamada en yüksek yön modeli `WARM_PERSIST_6`: **2,534306**. Sabit seçilen yöntem LAST18 dönemine bir kere götürüldüğünde:

| 10 sayılık bilet yöntemi | LAST18 3906 hedef ortalama isabet | 5+/10 | 6+/10 | Tam10 |
|---|---:|---:|---:|---:|
| Kilitli WARM_PERSIST_6 | **2,479519** | 271 | 46 | 0 |
| NET_WARM224 | 2,479263 | 241 | 56 | 0 |
| NET_COOL224 | 2,487711 | 265 | 61 | 0 |
| HOT72 | **2,509985** | 244 | 54 | 0 |
| HOT2688 | 2,480799 | 247 | 51 | 0 |
| Rastgele | **2,506656** | 247 | 35 | 0 |

Kilitli yöntem − rastgele 10 sayıda ortalama fark **−0,02714** isabet/çekiliş; %95 gün-blok aralığı **[−0,07245,+0,02330]** sıfırı kapsıyor. Yöntemlerin farklı 5+/10,6+/10 sayıları tek başına genel üstünlük demek değildir.

### Doğru yorum

224 halkanın hareketi, **çekiliş gelmeden ÖNCE hesaplanabilen** karmaşık bir tarihsel özellik. Gerçek ölçümde bazı belirli yön koşullarında hedefe girme frekansı %25'in az altında veya az üstünde. Özellikle YALNIZ ISINMA iki tarihsel evrede de %25'in altında kalmış, ancak sonuç farkı küçüktür, çoklu model tarama riski vardır. KARIŞIK YÖN LAST18'de yüksek görünmüş ancak hemen önceki validasyonda yaklaşık sıfır fark sergilemiş. En iyi valida edilen 10 sayı kupon stratejisi sonraki tarihsel döneminde rastgeleden iyi çıkmamıştır. Bunlar geleceğin rastgele RNG sayılarını öngörebildiğimiz veya hareket yönünün sebep-sonuçla sonucu değiştirdiği anlamına gelmez. İleriye dönük yeni çekilişler üzerinde aynı önceden sabitlenmiş işaretler sınanmadan herhangi bir avantaj iddiası kurulmaz.

### ZIP'deki 9 dosya

- `00_V129_KISA_GERCEK_BULGU.txt`
- `01_ILERIYE_HEDEF20_ONCESI_SINYAL_KOSULLU_OLASILIK.csv`
- `02_SON18_29_ONCU_SINYAL_GUN_GUVEN_ARALIK.csv`
- `03_25_YONTEM_3_4_5_6_8_10_20_BOYUT_SONUC.csv`
- `04_VALIDE_SECILEN_KILITLI_MODEL_KONTROL.csv`
- `05_SON18_HEDEF_4_FARKLI_MODEL_10_SAYI_ESLESME.csv`
- `06_SON_HEDEF_ONCESI_80_SAYI_224_HALKANIN_GERCEK_YONLERI.csv`
- `07_HER_GUN_29_SINYAL_ONCE_VE_HADEF.csv`
- `08_V129_DENETIM.json`

GitHub Actions gerçek koşusu ve ZIP'deki tüm sayılar tekrar hesaplanabilir; öncül sinyallerin 224 halkayı birer çekiliş ilerletme matematiği kaynak programda belirlenmiştir.