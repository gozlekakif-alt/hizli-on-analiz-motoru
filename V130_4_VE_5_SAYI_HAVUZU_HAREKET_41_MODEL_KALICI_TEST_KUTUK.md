# V130 — 80 sayıyı doğrudan seçmek yerine 4 veya 5 tane 16 sayılık havuzdan dengeli seçim

**ÇALIŞMA GERÇEK VERİYLE BAŞARIYLA TAMAMLANDI.**

GitHub Actions doğrulanmış koşu: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/39012401526
Sonuçlar ZIP (GitHub Actions geçici indirme): https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/39012401526/artifacts/12093263097
Tekrar üretilebilir program: [v130_4_5_havuzdan_10_sayi_secimi_grup_kor_test.py](v130_4_5_havuzdan_10_sayi_secimi_grup_kor_test.py)

## Kullanıcı hipotezi

Önceki sürümler V9–V129, 672/1344/2016/2688 geçmiş çekiliş, 224 iç içe halka ve her halkanın 80 sayısını 5 eşit sınıfta izleyerek güçlü öngörü üstünlüğü kanıtlamadı. Yeni hipotez: 80 sayı içinden doğrudan seçmek yerine önce **5 sıcaklık havuzundan 4'ünü veya 5'ini**, sonra havuzların içindeki bireysel sayıları seçmek.

## Gerçek kurulumu

- Gerçek arşiv: GitHub `veri.txt`, **15.790** gerçek 20/80 çekiliş, son #62014 (13.10.2026).
- Her hedefin ÖNCESİNDE yalnız bitmiş çekilişlerle **224 iç içe kümülatif pencere** 12,24,…2688; 80 sayı tarihsel çıkış adetlerine göre sıralanarak 5 adet 16 sayılık havuza ayrıldı. Eşit çıkış adedinde küçük numara ilk sırada.
- 5 havuzun üyeliği üç farklı şekilde oluşturuldu: **72'lik halkanın** rank havuzları, **672'lik halkanın** rank havuzları, veya **224 halkanın ortak konsensüs sıcaklığı** (her sayının 224 havuz etiketinin toplamından 5×16 yeniden gruplanması).
- Her 4-havuz yönteminde **hangi 16 sayılık grubun dışarıda bırakılacağı çekilişten ÖNCE** karar verildi. Sabit soğuk/sıcak çıkarmak, 12 ve 72 geçmiş çekilişte bu grubun daha az/çok sayısının çıkması, veya sabit tohumlu kontrol olarak rastgele 1 grup çıkarmak denendi.
- Her grubun içinden sayı seçimi yalnız **önceden gözlenen son12 sıklığı**, 224 halkalık son bilinen sıcaklık hareket neti, veya aynı sayıda rastgele seçim ile yapıldı.
- 10 sayılık kupon: **5 havuzdan 2+2+2+2+2**, 4 havuzdan **3+3+2+2**. 20'lik kupon için 5 havuzdan 4'er, 4 havuzdan 5'er. 3,4,5,6,8 boyları aynı yuvarlak sıra seçiminin ilk k üyesi olarak test edildi.
- **36 havuz stratejisi + 5 düz sayı seçimi kontrolü = 41 yöntem**. Hepsi hedef başına aynı kupon sayısını (**bir**) kullandı.
- Her birinde hedef sonucundan **önce** seçim yapıldı. 2688 başlangıç gözlemi ve devamındaki **13.101** gerçek bir sonraki çekilişle karşılaştırma. İlk36 gün TRAIN, sonraki18 VALIDATE, son18 LAST18, en son 13 Ekim'in ek hedefleri. Bu tarihlerin V9–V129 tarafından daha önce görülmüş olması nedeniyle LAST18 yalnızca **iç kronolojik doğrulama**; **bakir gelecek testi değildir**.

## 16'lık havuzlar gerçekten hedef20'de kaçar sayı verdi?

**LAST18 = 3906 hedef**. Her 16 sayılık gruptan adil matematiksel beklenti **4 sayı**.

| Grup | 72 halka sınıflaması | 672 halka sınıflaması | 224 halka ortak sınıflaması |
|---|---:|---:|---:|
| SOĞUK | 3,9642 | 3,9923 | 3,9603 |
| SERİN | 4,0064 | 3,9690 | 4,0200 |
| NÖTR | 4,0340 | 4,0486 | 4,0038 |
| ILIK | 3,9793 | 3,9785 | 4,0202 |
| SICAK | 4,0161 | 4,0115 | 3,9956 |

İlk bakışta **hangi sıcaklık grubunu dışarıda bırakacağımızı** sınıftan tahmin etmek zor. Her sınıf 4'ün çevresinde.

## 4 havuz = 64 aday sayıya geçince ne oldu?

Rastgele seçilen 64 sayının hedef20'den teorik ortalama kapsadığı sayı **16**.

| Hedeften önce seçilen 4 havuz | LAST18 hedef20'de kapsanan ortalama | Dışarıda kalan havuzun hedefteki ortalama isabeti |
|---|---:|---:|
| 224 ortak sınıflama, son12'de en az sonuç veren 16'lığı çıkar | **16,0105** | 3,9895 |
| 224 ortak sınıflama, son72'de en az sonuç veren 16'lığı çıkar | **16,0476** | 3,9524 |
| 224 ortak sınıflama, 16'lık grubu rastgele çıkar | **15,9931** | 4,0069 |

İyileşmeler büyüklük olarak çok küçük ve kendi başlarına öngörü lehine kanıt sayılmaz. Tek çekilişte 64 adaydan 10'a inmek için de havuz içi sıralamanın gerçek avantaj sağlaması gerekir.

## Asıl 10 sayılık kupon karşılaştırması

Son18 gün, **3906 hedef çekiliş**, **aynı 1 kupon yöntemi bütçesi**:

| Seçim yöntemi | LAST18 10 sayılık ortalama isabet | 5+/10 | 6+/10 | Tam10 |
|---|---:|---:|---:|---:|
| **224 ortak sınıflama, 5 havuzdan 2'şer, önceki12 sıklığı** | **2,484127** | 238 | 47 | 0 |
| **224 ortak sınıflama, 4 havuzdan 3+3+2+2, son12'de en az çıkan grubu çıkar** | **2,500000** | 243 | 45 | 0 |
| 224 ortak sınıflama, 4 havuzdan son72'de en az çıkan grubu çıkar | 2,482335 | 228 | 51 | 0 |
| 224 ortak sınıflama, rastgele 4 grup & rastgele grup içi sayı | 2,502816 | 240 | 51 | 0 |
| 224 ortak sınıflama, 5 grup, her gruptan rastgele 2 sayı | **2,509985** | 257 | 50 | 0 |
| **72 halkasının havuzları, son12'de en az çıkan grup dışarıda, 4 havuz** | **2,509985** | 245 | 54 | 0 |
| Salt HOT12 sayıları | 2,499488 | 255 | 57 | 0 |
| Salt HOT72 sayıları | **2,509985** | 244 | 54 | 0 |
| Salt RANDOM 10 sayı | **2,512801** | 241 | 51 | 0 |

VALIDATE18'de 36 havuz yöntemi arasından sabitlenen en yüksek 10'lu yöntem **H72_4_DROP_LOW12_HOT12** (doğrulama döneminde 2,544035 isabet); LAST18'de 2,509985 ile, salt rastgele 2,512801 seviyesini aşamadı.

Son18 günlük eşlenmiş bootstrap'le **kilitli havuz kazanını − salt rastgele** farkı **−0,002816 isabet/kupon**, %95 aralık **[−0,064516,+0,053251]**. Sıfırı kapsar. Salt HOT72 karşısında fark **+0,000000**, %95 **[−0,049930,+0,049411]**.

## Yorum ve sonraki mantıklı ayrım

**4 veya 5 havuzu kullanmak rastgele seçimin önüne otomatik geçirmedi.** Ama deney şu ayrımı görünür kılıyor:

(a) hedef20'nin grubunu **önceden doğru seçmek** (64 sayıya düşerken ortalama 16 hedef numarası yakalamak yerine 17+ yakalayabiliyor muyuz?) ve

(b) seçtiğimiz havuzun içinden **doğru 10 sayıyı ayıklamak** (10'da rastgele 2,5 yerine kanıtlanmış daha yüksek ortalama) **iki farklı başarı koşuludur**.

Bu testte hiçbiri istikrarlı kanıt vermedi. 36+ model taraması, önceden görülmüş tarihsel tarihler ve büyük ölçüde iç içe 224 halka bağımlılığı özellikle hesaba katılmalıdır.

## ZIP içeriği

- `00_V130_KISA_4_5_HAVUZ_GERCEK_TEST.txt`
- `01_41_MODEL_3_4_5_6_8_10_20_ISABETLER.csv`
- `02_4_HAVUZ_64_SAYI_HEDEF20_KAPSAMA.csv`
- `03_5_HAVUZ_HER_16_SAYI_HEDEF20_GIRIS_ORANI.csv`
- `04_VALIDASYONDA_SECILEN_MODEL_SON18_KONTROL.csv`
- `05_SON18_41_MODEL_10_SAYI_DOGRULAMA_SIRALAMA.csv` (tüm 36 grup yönteminin validasyon sıralaması; dosya ismi önceki tasarımdan gelir)
- `06_SON18_CONSENSUS224_HEDEF_TEK_TEK_KUPON.csv`
- `07_SON_HEDEF_80_SAYI_224_HAVUZ_SINIFI_SABIT.csv`
- `08_KUTUK_DENETIM.json`