# V116 — 56 Kayan Halka, 1/0 Yolculukları ve Yedili Aile Ön İkaz Testi

**16 Ekim 2026.** Kullanıcının V115'te netleştirdiği yürüyen tanım uygulanır: **her anda 56 halka; her halkada 12 gerçek çekiliş; tam 672 adet; her yeni çekilişte en eski bir çekiliş dışarı, yeni bir çekiliş içeri.** Yeni halkaların zamanı göreli olarak yeniden kurulurken, V100C'nin mutlak halka kimliği kullanan eski metodu silinmez; iki yorum karıştırılmamalıdır.

**Tam sonuç GitHub Actions:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38960884322

**İndirilebilir ZIP (8 dosya):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38960884322/artifacts/12072397958

**Program:** [v116_56_kayan_halka_01_7li_aile_oncu_sinyal.py](v116_56_kayan_halka_01_7li_aile_oncu_sinyal.py)

## Kaynak ve kesin zaman çizgisi

- `veri.txt`: **15.790** gerçek kayıt, son **13 Ekim 2026 #62014**. Her çekilişte 1–80'den 20 farklı sayı.
- **69 gün** 23:02–23:57 son saati; 22. saatin geçmiş çekilişlerinde **7 ortak sayı** içeren bir çift varsa bu yedili aile hedef **23:02'den önce** belirlenir. **68 gün** aile bulundu; bir gün bulunmadı.
- **68×12 = 816 hedef çekiliş**, her hedefte aile ile **rastgele 7**, **aynı son 16'lık havuz dağılımı karşılıklarından 7** ve **son72 görünme sıklığı en yüksek 7** eşit kupon sayısıyla karşılaştırılır. Her saatte 1 kupon, 12 ayrı hedef değerlendirme.
- Saat başlamadan dondurulmuş **her 56 halkada ve her 80 sayıda 12 bitlik 1/0 dizi**, toplam **68×56×80=304.640 satır** ve her aile üyesinin **56×12** bit dizisi kayıtlıdır.
- Her halkanın sıcaklık havuzu kendi son sınırına kadar bilinen en güncel **72 gerçek çekilişle** belirlenen sıralı 16+16+16+16+16 havuzudur. Hedef çekiliş sonucu sıralamayı **sonradan** değiştirdiği için *hedefe ait gelecekteki havuz* hiçbir zaman o hedefin tahmin özelliği olmaz.

## 816 hedef çekilişte gerçek sonuçlar

| Aynı sayıda yedili seçen yöntem | Bir çekilişte ortalama doğru sayı | 5/7 veya daha iyisi |
|---|---:|---:|
| Geçmişte tam-7 kesişen aile | **1,748** | **5** |
| Rastgele 7 | 1,708 | **10** |
| Havuzu eşlenmiş 7 | 1,697 | 6 |
| Son72 sıcak 7 | 1,712 | 7 |
| Adil 20/80 teorisi | **1,750** | **beklenen oran yaklaşık %0,94/kupon** |

**İlk bulgu:** Ailenin hedef öncesinde iki defa birlikte görünmesi, hedefte 5/7 üstünlüğünü sağlamadı. Kontrol kuponlarının fiili ortalamaları 1,75'in yakınında rastgele sapma gösterir.

## Hangi öncü hareketi sınadık?

**A. Havuz yeniden toplanması (reunion4):** Önceki 6 halkada aileden en fazla 2 üye aynı bir havuzda bulunmuşken son 6 halkada en az 4 üyenin aynı havuzda olması (eşiklerin ikisi de zaman öncesinden).

| Durum | Aile-saat | Hedef çekiliş | Aile ortalama isabet | Aile 5+/7 |
|---|---:|---:|---:|---:|
| Yeniden toplandı | 35 | 420 | **1,690** | 2 |
| Yeniden toplanmadı | 33 | 396 | **1,808** | 3 |

**B. Havuz yakınlaşmasının sürekliliği:** Son altı halkadaki aynı-havuz aile çiftlerinin ortalaması, bir önceki altı halkadan yükseldiyse:

| Durum | Aile-saat | Hedef çekiliş | Aile ortalama isabet | Aile 5+/7 |
|---|---:|---:|---:|---:|
| Aynı-havuz yoğunluğu arttı | 31 | 372 | **1,672** | 2 |
| Artmadı | 37 | 444 | **1,811** | 3 |

**C. Gerçek 1/0 yükselişi:** Aynı yedi aile üyesinden **en az dördünün son 6 halka içindeki toplam çıkış sayısının, daha önceki 6 halkaya göre artması**:

| Durum | Aile-saat | Hedef çekiliş | Aile ortalama isabet | Aile 5+/7 |
|---|---:|---:|---:|---:|
| En az dört üye görünüm artırdı | 40 | 480 | **1,746** | 4 |
| Bu koşul yok | 28 | 336 | **1,750** | 1 |

Birlikte çıkarılan aile zaten H22'nin iki eski çekilişinde 7/7 görülmüş olduğundan **son 56. halkadaki tüm üyelerin görünmesi seçim kuralının kaçınılmaz özelliğidir**, geleceğe yönelik yeni sinyalmiş gibi sayılmamalıdır.

## Sonuç ve sonraki araştırma

**Bu üç önceden tanımlı 'aile yaklaşması' işaretinden hiçbiri, yeni gelen 20 sayı için anlamlı/kalıcı üstünlük gösteremedi.** Yeniden birleşme göstergelerinin *ham* ortalaması genellikle beklentinin tersi çıktı. Bu bulgu yalnız 69 tarihi son saat ve bu **tek** tam-7 H22 aile seçme kuralına özgüdür; başka aile tanımları için kesin genelleme yapılamaz.

İlk 34 ve sonraki 35 takvim hedefi ayrıca dönem gruplarına ayrılmıştır. Bir günde aile bulunmadığından ikinci dönemde **34 yedili aile** vardır. Veri zaten önceki V9–V115 araştırmalarında defalarca kullanılmıştır; tarihsel tekrarlar yeni ileriye dönük kör deney değildir.

## 8 doğrulanmış ZIP dosyası

- `00_V116_TURKCE_KISA_SONUCLAR.txt`
- `01_HER_23_SAAT_ONCESI_56X80_HALKA_12BIT_DOKUM.csv`: 304.640 satır, 80 sayının 56 halkada 12'şer bitlik 1/0 kaydı ve 5 havuz sınıfı.
- `02_7LI_AILE_56_HALKANIN_TAMAMINDA_01_VE_5HAVUZ.csv`
- `03_23ONCESI_7LI_AILE_GUN_GUN_ONCU_ISARET.csv`
- `04_HEDEF_23_12_CEKILIS_4_KONTROL_KUPON.csv`
- `05_AILE_UYELERI_HEDEF_CEKILISTEN_ONCE_SONRA_HAVUZ.csv`
- `06_DONEM_SINYAL_7LI_ISABET_KARSILASTIRMA.csv`
- `07_GUN_GUN_FARK_AILE_KONTROL.csv`
- `08_VERI_METOD_DENETIM.json` (toplam **9** ZIP dosyası; `00`–`08`).

Sınır: Yanlış öncü sinyal seçilmesin diye sonuç *çıkan 1/çıkmayan 0* olarak kayıtlı **yalnız gerçekleştikten sonra**, sonucu görmedenki 56 halkalık durum ise **önce** kaydedilmiştir. Ortaya çıkan 5/7 örnekleri güçlü değil; bütçeli gerçek kupon üstünlüğü ilan edilmez.
