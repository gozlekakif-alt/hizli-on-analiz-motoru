# V36 — Her gerçek çekilişte bağımsız motor hazneleriyle RNG davranış klonu

**Tarih:** 14.10.2026. Bu modül, mevcut V36 H6 devir-zinciri araştırmasına dokunmadan **ayrı bir V36 klon laboratuvarı** olarak eklenmiştir. GitHub: gozlekakif-alt/hizli-on-analiz-motoru.

## Asıl araştırma hedefi

Gerçek RNG'nin tohumunu, gizli durumunu veya algoritmasını elde ettiğimizi **iddia etmiyoruz**. Bir dijital ikiz, *gözlenen oyun davranışlarını* her gerçek çekilişte iki ayrı süreçle üretir ve farkları gün gün ölçer. Bu bir **istatistiksel emülatördür**; kazandıran sayı tahmini olduğu kanıtlanmamıştır.

- **GERÇEK:** Resmi 20 sayı gelir, 60 sayı yoktur; her 80 sayının ilgili uzman haznesine girişi, çıkışı ve dönemsel yaşamı kaydedilir.
- **KLON:** 20 benzersiz sayı üreten özerk kol, bir sonraki adımını *kendi çıkardığı* sayılardan türetir. Böylece gerçekleşmiş sayıların kopyasını sonraki adımın girdisi yapmaz.
- **GERÇEK DURUMDAN KLON:** Bir önceki gerçek durumdan, geçmiş çekilişlerden öğrenilmiş hazne oranlarıyla farklı 20'li üretir. Gerçek bir sonraki çekilişle karşılaştırma yaparken gelecek sonucu önceden kullanmaz.
- **RASTGELE KONTROL:** Hiçbir karakter kullanmadan 20 benzersiz sayı seçer. 20 ile 20 karşılaştırmada beklenen ortak sayı 5'tir.
- **AKORT:** Hedef çekilişin sonucu geldikten SONRA 13 ayrı öğrenme dalının sayaçları güncellenir; bir sonraki çekiliş üretimi yeni veriyi kullanır.

## 15 ana uzman hazne grubu

| Grup | Gerçek görevi ve her çekilişteki kolları |
|---|---|
| HAVUZ20 | Çıkan 20 içinde olan sayılar, girenler, çıkanlar |
| HAVUZ60 | O çekilişte görünmeyen 60, girenler, çıkanlar |
| ISI | Soğuk / soğuğa yakın / orta / ılık / sıcağa yakın / sıcak, 13-13-14-14-13-13 koltuk |
| YON | Yükseliş / düşüş / sabit ve altı ısı havuzunun önceki→sonraki 36 olası geçişi |
| BEKLEME | 0 / 1–3 / 4–5 / tam 6 / 7 / 8 / 9 / 10 / 11+ |
| 11LI | Günün ardışık son 11 gerçek çekilişindeki 0..5 / 6+ görünüş yoğunluğu |
| BANT | Sekiz 10'luk sayı aralığı |
| YARIM | 1–40 / 41–80 |
| TEKRAR | Önceki çıkan 20'den devam eden / önceki çıkmayan 60'tan sahneye gelen |
| AYNA | 81−n aynası önceki gerçek 20'de var / yok |
| DONGU | Çıkan20 üzerinden 80/80 tamamlanma, döngü içindeki görülmüş/görülmemiş |
| AILE2 | Son 12 gerçek adımın ikili birlikteliğinin yeniden oluşması |
| AILE3 | Son 12 gerçek adımın üçlü birlikteliğinin yeniden oluşması |
| AILE4 | Aynı dörtlünün arka arkaya iki gerçek çekilişte birlikte olması |
| IMZA11 | Tam 11 çekiliş kayıtlıysa sayı için 11 bit 1/0 geçmişi |

## 13 ayrı kalibrasyon dalı

\`ISI\`, \`YON\`, \`BEKLEME\`, \`11LI\`, \`BANT\`, \`YARIM\`, \`TEKRAR\`, \`AYNA\`, \`DONGU\`, \`AILE2\`, \`AILE3\`, \`AILE4\`, \`ILK6_SON5\`.

Her dal için ilgili hazneye giren sayıların önceki n adet denemede **ertesi gerçek çıkan20'ye giriş sayısı** tutulur. Sayı çıkma olasılıkları, %25 başlangıç varsayımı ve 160 gözlemlik yumuşatma payıyla çevrimiçi öğrenilir. Uzman etkileri sınırlanır; bunlar yüzde yüz kazanma iddiası değildir.

Dallar bağımsız defterler tutar; 80 sayıya ait birden fazla uzman çıktısı, aşırı güven oluşmaması için kısılmış bir ağırlık üzerinden birleşir. 20 sayı geri koymadan ağırlıklı rastgele seçilir; her klon çekilişinde 20 farklı sayı vardır.

## Zaman ve kayıt kuralı

- Günlük gerçek sıra 1..217'dir. 00:02'den 01:02'ye kadar 13 çekiliş, sonra 07:02–23:57 arasında 204 çekiliş. Günlük toplam **217**.
- 01:02→07:02 arası gerçek çekiliş bulunmadığından yapay sıfır eklenmez. Saatler değil, gerçek adımlar sayılır.
- Eksik sıra varsa bekleme, kısa 11'li geçmiş, aile ve 80/80 döngüsünün kesintisiz bölümü kesilir.
- Yeni günde kısa dönem aile, bekleme, 11'li pencere, 80/80 döngüsü yeni başlangıç yapar; üstel sıcaklık hafızası uzun dönemde korunur.
- Her çekilişten sonra GERÇEK ve KLON için bütün motor-hazne sayı listeleri, içeri girenler ve çıkanlar ayrı satırlarda bulunur.
- Bir motorun isabeti hedef çekiliş görülmeden değişmez; bu nedenle yeni çekilişi önceden kullanma hatasının olmaması sentetik regresyon testiyle kontrol edilir.

## Tek ZIP

\`00_KULLANIM_TASARIM_VE_KURALLAR.txt\`
\`01_80_SAYI_HER_ADIM_KARAKTER.csv\`
\`02_HER_MOTOR_HAZNE_GIRIS_CIKIS.csv\`
\`03_HER_CEKILIS_GERCEK_KLON_KARSILASTIRMA.csv\`
\`04_KALIBRASYON_HER_UZMAN_HAZNESI.csv\`
\`05_GUNLUK_KLON_AKORT_KONTROLU.csv\`
\`06_MOTORLAR_ARASI_GECIS_TAM.csv\`
\`07_AILE_2_3_4_ADIM_ADIM.csv\`
\`08_80_80_TAMAMLANMA_KAYITLARI.csv\`
\`09_UZMAN_MOTOR_GIRIS_CIKIS_TOPLAMLARI.csv\`
\`10_OZET.json\`

### Kod bağlantıları

- Motor çekirdeği: \`v36_rng_davranis_klonu.py\`
- Streamlit V10 içindeki V36 sekmesi: \`v36_klon_app.py\`, \`v10_app.py\`
- Sentetik/gerçek verili test: \`v36_selftest.py\`
- Otomatik tam veri ZIP'i: \`v36_export_zip.py\`
- Ayrı GitHub Actions: \`.github/workflows/v36-clone-check.yml\`

**Dikkat:** Streamlit Cloud giriş dosyası **v10_app.py** olmalıdır; eski **app.py** seçiliyse yeni V36 sekmesi görünmez. Streamlit tek düğmeyle kaynak veriden rapor oluşturur; GitHub Actions her veri/kod güncellemesinde otomatik ZIP de üretir. Streamlit oturumu tek başına kalıcı veritabanı değildir; değişmeyen kaynak veri GitHub'daki \`veri.txt\`, indirilebilir sonuç ZIP'tir.

**Değerlendirme:** Eğitim/test etiketleri takvimde ilk yarı / sonraki yarı olarak ayrılır. Klon test döneminde de *her gerçekleşmiş yeni çekilişten sonra* akort olur; bu bir çevrimiçi, ileri tarihli testtir, kapalı sabit model testi değildir. Rastgele baz çizgisi aşılmazsa klonun dağılımlara benzemesi gelecek gerçek 20'yi bildiğini göstermez.
