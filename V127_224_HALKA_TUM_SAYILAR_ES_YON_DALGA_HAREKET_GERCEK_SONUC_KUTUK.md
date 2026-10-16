# V127 — 224 iç içe halkada tüm sayılar aynı yönde mi gider? Dalga / yön eşzamanlılığı

**17 Ekim 2026. Başarılı sayısal analiz.**

- [Gerçek analiz koşusu](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38976502493)
- [11 dosyalı sonuç ZIP (GitHub Actions 90 gün)](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38976502493/artifacts/12078699559)
- [Yeniden çalıştırılabilir kod](v127_224_halka_sayi_dalga_ayni_yon_mu_analiz.py)
- [V126 kalıcı eksiksiz her adım arşivi](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/tag/v126-2026-10-13-224-rings-lossless)

## Soru ve kesin kavramsal ayrım

Soru: 224 iç içe (son 12,24,36,…2688 çekiliş) halkada 80 sayı bir dalga gibi hep aynı sıcaklık yönüne mi hareket ediyor? Bir *sayıdaki çıkış adedi* hareketi ve *sayıların birbirine göre sırası/sıcaklık sınıfı* aynı şey değildir.

Yeni hedef çekiliş `t`, herhangi bir 12k halkası `L` ve sayı `b` için:

`YeniFrekans−EskiFrekans = X[t,b]−X[t−L,b]`.

Dolayısıyla sayı **yeni çekilişte çıkmışsa** 224 halkanın hiçbirinde görünme adedi düşemez (ya +1 ya 0); **çıkmamışsa** hiçbirinde artamaz (ya −1 ya 0). Bu yüzden bir sayı için 224 halkada hem frekans artışı hem azalışı aynı çekilişte gerçekleşmesi **matematiksel olarak imkânsızdır**. Bu bir rastgele sayı tahmin sinyali değildir; yeni çekilişte hangi sayıların çıktığını bilmek demektir.

Ama **sıcaklık sınıfı / göreli frekans sırası** rakip 79 sayının çıkışına, pencereden çıkışlarına ve sıralamasına bağlı olarak iki yönlü hareket edebilir. **Her halkanın beş sınıfında 16'şar sayı olduğu için**, bir halkadaki 80 sayının **hepsinin** aynı anda daha sıcak veya daha soğuk sınıfa geçmesi de imkânsızdır. Bir halkada sınıf değiştiren varsa ısınan ve soğuyanlar birlikte bulunur.

## Gerçek V127 çalışması

**Kaynak:** 15.790 gerçek çekiliş, 13 Ekim 2026 son kayıt #62014. İlk 2.688 başlangıç hafızasından sonra **13.102 gerçek yeni çekiliş**, her birinde **224 × 80** sayı durumu tarandı. **1.048.160 sayı × çekiliş** vakasında, tek sayının aynı hedefte bütün 224 halkadaki ±1/0 çıkış adedi; sıralama (rank) değişimi; sıcaklık sınıfı (soğuk-serin-nötr-ılık-sıcak) değişimi karşılaştırıldı. 234.787.840 hücredeki gelişmelerin ham kayıtları daha önce V126'da kaydedilmiştir.

### 224 halka boyunca bir sayı tek yönde mi, iki yönde mi?

| Ölçülen yön | Hiç değişmedi | Yalnız yükseldi | Yalnız düştü | Hem yükseldi hem düştü |
|---|---:|---:|---:|---:|
| **Çıkış adedi** | 0 | 262.040 | 786.120 | **0 (%0)** |
| **Göreli rank** | 0 | 638 | 26 | **1.047.496 (%99,9367)** |
| **Beş sınıflı sıcaklık** | **8.331 (%0,795)** | **133.454 (%12,732)** | **112.141 (%10,699)** | **794.234 (%75,7741)** |

Bir sayı çekilişte çıktıysa frekans bazı halkalarda artıp kalanında sabit kaldı; çıkmadıysa bazı halkalarda azalıp diğerlerinde sabit kaldı. Ancak dört vaka türünden **%75,77'sinde** aynı sayının bazı halkalarda sıcaklığa doğru, başka halkalarda soğuğa doğru hareket ettiği doğrudan gözlendi. Sıcaklık sınıfı değişmeyen halkalar izinli olup sınıflandırmada göz ardı edilmedi.

### Birbirine yakın halkalarda hareket aynı yöne mi?

Yalnız **iki halkada da bu sayı için sınıf değişimi olan gözlemler** paydadır. Sıfır hareket edenleri aynı yön gibi saymayız.

| Halka çiftleri | İkisinde de hareket gözlemi | Aynı yön | Zıt yön | İkisinde hareket varsa aynı yön yüzdesi |
|---|---:|---:|---:|---:|
| 12 ve 24 | 126.671 | 112.923 | 13.748 | **%89,1467** |
| 12 ve 36 | 103.410 | 91.724 | 11.686 | %88,6994 |
| 12 ve 72 | 73.196 | 64.177 | 9.019 | **%87,6783** |
| 12 ve 672 | 24.827 | 20.938 | 3.889 | **%84,3356** |
| 12 ve 1.344 | 17.716 | 14.848 | 2.868 | %83,8112 |
| 12 ve 2.016 | 14.852 | 12.391 | 2.461 | %83,4298 |
| 12 ve 2.688 | 13.142 | 10.925 | 2.217 | **%83,1304** |
| 672 ve 1.344 | 3.597 | 2.871 | 726 | %79,8165 |
| 672 ve 2.016 | 2.931 | 2.255 | 676 | %76,9362 |
| **672 ve 2.688** | **2.423** | **1.933** | **490** | **%79,7771** |
| 2.016 ve 2.688 | 1.765 | 1.385 | 380 | %78,4703 |

**Komşu halka genelinde** hem hareket olan toplam **2.252.048** bitişik halka-sayı-çekiliş ikilisinin **1.878.418'i (%83,4093)** aynı yönde, **373.630'u (%16,5907)** zıt yönde hareket etti. Bu, halka indeksinde yönün yerel kümelenmesini gösterir. Aynı hareketlerin pozitif/negatif ve sıfır sayılarını sabit tutup halka indekslerini karıştıran basit karşı-olgusal model, bitişik aynı yön için yaklaşık **791.022** olay beklerdi; gerçek oran yaklaşık **2,3747 kat**. Ancak halkalar ciddi derecede örtüştüğü için bu farkın mekanik nedeni vardır; olasılık/ödül avantajı veya bağımsız RNG yapı kanıtı **değildir**. Bu karşılaştırma şansa karşı çekiliş tahmin testi değil, halka dizisindeki mekânsal kümelenmenin betimlemesidir.

### 224 halkanın dört 56'lık bölümünde yön karmaşıklığı

| Halka grubu | Kapsam | 1 sayının bu grupta her iki yöne hareket ettiği durum |
|---|---|---:|
| 1–56 | 12–672 çekiliş | **494.900 / 1.048.160 = %47,216** |
| 57–112 | 684–1.344 | **308.722 = %29,454** |
| 113–168 | 1.356–2.016 | **242.737 = %23,158** |
| 169–224 | 2.028–2.688 | **209.762 = %20,012** |

Her blok kendi içinde değerlendirilmiştir; aynı vakalar dört blokta tekrarlanabileceği için yüzde toplama yapılmaz. Geniş pencerelerde sınıf değişimi seyrekleşir.

### Son çekilişte çıkan / çıkmayan sayılar farklı mı?

- **Yeni çekilişte çıkan 20 sayı** × 13.102 çekiliş: 262.040 vaka; bunların **130.955'inde (%49,9752)** sayı 224 halkada hem sıcak hem soğuk yönlü sınıf değişimi gösterdi.
- **Yeni çekilişte çıkmayan 60 sayı** × 13.102 çekiliş: 786.120 vaka; bunların **663.279'unda (%84,3738)** 224 halka boyunca hem sıcak hem soğuk sınıf hareketi gerçekleşti.

Bu **sonuç görüldükten sonra hesaplanan** durumdur. Bir sonraki çekilişte çıkacağı önceden bilinmediğinden, bu oranları geriye dönük olmayan tahmin kuralı gibi kullanamayız.

## V127 ZIP dosyaları

- `00_V127_TURKCE_DALGA_SENKRON_GERCEK_SONUC.txt` — elde edilen sonuçların kısa özeti.
- `01_224_RING_SAYI_HAREKET_TIPLERI_TOPLAM.csv` — sayı çıkış adedi/rank/sıcaklık için none/up/down/mixed, bitişik halka yön uyumu, ardışık yeni çekiliş yön tekrar oranı ve halka indeksleri karıştırma kıyası.
- `02_CIKAN_CIKMAYAN_SAYI_AYRI_DALGA_YONLERI.csv` — hedefte çıkan/çıkmayan ayrı karşılaştırma.
- `03_HALKALAR_ARASI_ESZAMANLI_HAREKET_ESLESMESI.csv` — seçilen 16 farklı halka ikilisindeki eşzamanlı yönler.
- `04_DORT_56_HALKA_BANT_ICI_DALGA_SENKRON.csv` — dört büyük halka bandında up/down/mixed.
- `05_HER_80_SAYI_TARIHSEL_224_HALKA_YON_KARISIKLIK.csv` — 1–80 sayının kendi hareket özeti.
- `06_HER_224_HALKA_ILIK_SOGUK_YON_COUNTER.csv` — 224 halka boyunca hareket sıklıkları.
- `07_GUN_GUN_COUNT_RANK_POOL_DALGA_SAYIM.csv` — 61 günlük tarihsel ayrım.
- `08_SON_HEDEF_80_SAYI_224_HALKA_YON_DESENLERI.csv` — son çekiliş #62014 geldiğinde **80 sayının her biri** için 224 sınıflı yön kodu, önceki/yeni sınıf kodu.
- `09_SON_12_CEKILIS_80_SAYI_HALKA_DALGA_DESEN.csv` — son 12 gözlenen çekilişte her 80 sayı için 224 halkada yön kodu.
- `10_DENETIM_VE_SONUC.json` — yöntem, gerçek veri aralığı, tüm 224 halka ve toplam hesaplar.

## Sınır ve takip

V126'dan bağımsız yeniden hesaplamayla V127 aynı 13.102 adımın sınıflarını incelemiştir. Hareketin hangi halkanın hangisine benzer bir yön izlediğini artık ölçüyoruz. **Bu örüntü, her çekiliş sonucu belli olduktan sonra doğan hareket**; sonraki bilinmeyen 20 numaranın önceden tahmin edilebileceği veya aralarında nedensel şifre bulunduğu kanıtı değildir. Öngörü testinde mutlaka `t` anındaki bilgiyle yalnız `t+1` çıktısı kontrol edilir.
