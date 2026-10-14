# V42 — Beş Hareketli Havuz Kotası ve 20/20 Tekrar Denetimi

**Tarih:** 14 Ekim 2026. **Durum:** gerçek veri ve zamansal sızıntı kontrolü GitHub'da başarılı.

**GitHub Actions:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38629949988

**Tek ZIP (3,75 MB):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38629949988/artifacts/11924963909

## 1) Kullanıcının işaret ettiği ayrım

- 72 tam gün = 15.624 gerçek çekiliş; her çekiliş tam 20 farklı numaradan oluşur.
- **Hiçbir 20 sayılık tam küme diğerinin aynısı olmamıştır:** 15.624 farklı tam 20'li; tekrar çiftleri = **0**.
- Bu durum RNG'de beklenmedik değildir: \(\binom{80}{20}=3.535.316.142.212.174.320\) eşsiz küme. 15.624 çekilişte adil bağımsız çekiliş altında **beklenen aynı-20 çifti 0,0000000000345222**.
- Asıl gözlenebilir tekrarlar 20 kimliğinin aynen tekrarı değil; çıkan 20'nin farklı havuzlara, bantlara, yönlere ve önceki çıkan20/çıkmayan60'a dağılım **oluşum karakterleridir**.
- İlk 72 gerçek çekiliş ısı geçmişini kurduğu için sonrasında 15.552 hedef çekilişte tam öncesi kota sınıflandırması yapılmıştır.
- Beş havuzdan gerçek çıkan20'ye düşen adet vektöründe **2.584 farklı imza**, bunlardan **1.688'i birden çok kez** görülmüş.
- Sekiz onluk bant katkı vektöründe **12.315 farklı imza**, bunlardan **2.207'si birden çok kez** görülmüş.
- Bu geçmiş imza tekrarları tek başına geleceği tahmin etme kanıtı değildir; ileri test şarttır.

## 2) Önceki sıcaklık çalışmasını yeniden kurma

Eski 6→7 araştırması beş **hareketli hacimli** 72-çekiliş sıcaklık sınıfı kullanıyordu:

| Havuz | H72, yalnız hedeften önceki 72 gerçek çekilişte görünme |
|---|---|
| SOĞUK | 0–14 |
| SERİN | 15–16 |
| NÖTR | 17–19 |
| ILIK | 20–21 |
| SICAK | 22 ve üzeri |

Bu V40/V41'deki sabit kapasiteli **altı havuzdan farklıdır**. Her hedef çekilişten önce beş havuzun gerçek üye adetleri yeniden belirlenir; toplam üyeler 80, tahmin edilen beş kota toplamı **tam 20** olur.

İki yöntem karşılaştırılmıştır:
1. **BOYUT_YUZDE25:** Her havuza üye sayısı × %25 beklentisi, kesirler ve kapasite dikkate alınarak tam 20 kişi Hamilton yöntemiyle pay edilir.
2. **KALIBRE_HAREKETLI:** Her havuzun sadece daha önce gerçek hedeflerdeki gelişlerinden güncellenen, %25 merkezli 160 gözlem yumuşatmalı seçilme oranıyla aday sayıları çarpılır; aynı Hamilton yönteminde toplam 20 sabitlenir.

**Hedef t'nin çıkan20 sayıları hiçbir zaman t için sınıflandırma, kota veya sayı listesi hesabına katılmaz; yalnız tahmin donduktan sonra isabet ölçülür, sonrasında öğrenme güncellenir.**

## 3) İlk36/son36 gerçek test

İlk günün ilk 72 çekilişi geçmişi kurar; 72 tam günde 15.552 geçerli hedef vardır. Son 36 gün **7.812** bağımsız olmayan hedef çekilişi içerir.

| Son36 / bütün hedefler | Basit %25 kota | Hareketli kalibre |
|---|---:|---:|
| Tek bir havuzda ±1 tahmin | %67,4014 | %67,3041 |
| Beş havuz aynı anda ±1 | %18,8812 | %18,7916 |
| Beş havuzun tamamında tam kota | %0,4480 | %0,4480 |
| Toplam mutlak kota hatası / hedef | 6,00333 | 6,00205 |
| Adil RNG için her kendi kotanın bütün5 ±1 beklenen başarısı | %18,7378 | %18,6926 |

Son 36 gün özel **saat 7–12** hedeflerinde, 3.888 gerçek çekiliş:
- Basit kota tek havuz ±1 %67,0988; beş havuz aynı anda ±1 %17,8241.
- Hareketli kota tek havuz ±1 %66,9650; beş havuz aynı anda ±1 %17,6698.
- %25 referansına göre 5 havuzun birlikte ±1 şansı basit kotada %18,7129, hareketli kotada %18,6671.

Eşlenik gün-blok farkı testte kalibre − basit kota bütün 5 aynı anda ±1: **−0,00090**; bootstrap %95 **[−0,00448,+0,002816]**. Belirgin üstünlük yok.

## 4) Kota içinden 20 sayı kimliği

Üç ayrı 20 sayılık liste, hedef görülmeden hazırlanıp sonuç görüldüğünde doğru adet sayılmıştır.

| Son36 7.812 hedef | Ortalama 20 kimlik isabeti | Tek çekiliş en yüksek |
|---|---:|---:|
| KOTA_YON_KIMLIK | **4,99027** | 11/20 |
| KOTA_ICI_RASTGELE | 5,01946 | 12/20 |
| SERBEST_RNG20 | 4,99949 | 11/20 |

Hiçbirinde 16/20 yok. İlk raporun %60–70 sayısı **20'linin %60–70 sayı kimliğini bulmak anlamına gelmez**; tek havuzun beklenen kotasının en çok bir sayı yanılması kriteridir.

## 5) 9 dosyalı tek ZIP

- `00_OKU_ONCE.txt`
- `01_CEKILIS_ONCESI_BES_HAVUZ_KOTA.csv`
- `02_HER_HAVUZ_ARTI_EKSI_BIR_DENETIM.csv`
- `03_KOTADAN_20_SAYI_KIMLIGI_ISABET.csv`
- `04_HAVUZ_KOTA_EGITIM_TEST_OZET.csv`
- `05_20_SAYI_KIMLIK_ISABET_OZET.csv`
- `06_TEKRARLAYAN_HAVUZ_VE_BANT_OLUSUM_IMZALARI.csv`
- `07_GUN_GUN_KOTA_DENETIM.csv`
- `08_BUTUN_SONUC_VE_KAYNAK.json`

Kod: `v42_bes_hareketli_havuz_kota.py`, `v42_bes_havuz_kota_app.py`, `v42_bes_havuz_selftest.py`, `v42_bes_havuz_kota_export.py`, `.github/workflows/v42-bes-havuz-kota-check.yml`. Streamlit V10 sekmesi: **🎯 V42 5 Havuz Kota**.

## 6) Sonraki araştırma sorusu

Havuz oluşumlarının, bant dağılımlarının, 20/60 tekrar/yeni hareketlerinin ve yön baskılarının **bir sonraki** oluşum biçimine bilgi verip vermediğini koşullu geçmiş frekanslar ve adil multivariate-hypergeometric temel modele karşı test etmek; sonra havuzun içindeki numara seçimi farkını ayrı kör test etmek.

**Uyarı:** 20/20 tam kümenin hiç tekrar etmemesi adil 20/80 RNG için neredeyse kesindir; bundan RNG'nin bir önceki çekilişle anti-tekrar kuralına sahip olduğu çıkarılamaz. Tek havuzda yüksek ±1 skor da adil RNG şansının dışında kalmayabilir.
