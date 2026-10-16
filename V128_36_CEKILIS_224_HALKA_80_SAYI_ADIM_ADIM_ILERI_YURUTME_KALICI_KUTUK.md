# V128 — 36 gerçek çekilişi 224 iç içe halka × 80 sayıda sırayla hareket ettirme

**GitHub Actions çalışması başarıyla tamamlandı ve her dosya kalıcı GitHub Release olarak yayımlandı.**

- **Çekilişi 1–36 arası ilerleten interaktif bağımsız HTML dosyası (telefonda çevrimdışı da açılır):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/download/v128-2026-10-13-36-step-ring-replay/V128_36_ADIM_224_HALKA_GORSEL_OYNATICI.html
- **645.120 gerçek geçişin tüm eski/yeni detayları, CSV/NPZ ve oynatıcı ZIP'i:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/download/v128-2026-10-13-36-step-ring-replay/V128_36_ADIM_224_HALKA_TAM_OYNATIM.zip
- **Sürüm sayfası:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/tag/v128-2026-10-13-36-step-ring-replay
- **Kalıcı tekrar çalıştırma kodu:** [v128_son_36_cekilis_224_halka_her_adim_oynat.py](v128_son_36_cekilis_224_halka_her_adim_oynat.py)
- **Doğrulanmış tam analiz koşusu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38977196831
- **Doğrulanmış kalıcı dosya yükleme koşusu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38977281937

## Kapsam ve temel ayrım

GitHub'daki `veri.txt` mevcut arşivde **15.790 gerçek çekiliş** içeriyor, son kayıt **13 Ekim 2026 #62014**. Gerçek anlamda 14–17 Ekim tarihli yeni çekiliş sonuçları bu arşivde yok. **Bu test, son 36 KAYITLI çekilişi başlangıçta gizleyip aynı tarihsel veri içinde sırayla birer birer sisteme vermektir**; gelecekte henüz gerçekleşmeyen çekiliş uydurulmadı.

36 tarihsel gözlem **#61978–#62014** aralığında, kayıtların tarihine göre 13 Ekim 2026 16:57–19:57 arasında. Kayıt dosyası çekiliş **#61999'u içermiyor**; asla sonuç uydurulmadı. Kullanıcı önümüzde 24 veya 36 çekilişi ileri oynatmak istedi; 36 kullanıldı. Kaynağa yeni çekiliş eklenirse program o yeni verinin son 24 veya 36 çekilişini yeniden oynatabilir.

İlk adım öncesi tüm sayı×halka durumları yalnız **#61978'den ÖNCEKİ** tarihin son 2688 gerçek çekilişiyle başlatıldı. Yeni gerçek çekiliş bir adım geldikçe **224 iç içe kümülatif halka** (12,24,36,...2688), tam 80 sayının görünme sayısı/rank/sınıf değişimine göre güncellendi. Yeni sonuç 224 halkaya aynı anda girer; her halkanın en eski kaydı ayrı çıkar.

### Gerçek sonuç

- Her hareket adımı: **224 halka × 80 sayı = 17.920** gerçek halka-sayı geçişi.
- 36 adım: **645.120** tamamı saklanmış geçiş.
- 36 adım boyunca toplam **39.863** sıcaklık sınıfı değişimi (soğuktan sıcağa veya ters yönde).
- En yoğun tek hareket: **#62011**, 1208 sınıf değişimi.
- En az yoğun tek hareket: **#61987**, 1021 sınıf değişimi.
- Her halkada **16 SOĞUK, 16 SERİN, 16 NÖTR, 16 ILIK, 16 SICAK** sayılık sınıf korunuyor; frekans eşitliğinde küçük numara önce sıralanıyor.
- Her sayı/halkada **eski/yeni çıkış sayısı**, eski/yeni 0–79 sıra, eski/yeni 0–4 sıcaklık, yeni çekiliş 1/0 ve halkadan çıkan eski çekiliş 1/0 tam kayıtlı.
- Yeni sonuçlar yalnız kendi sırası geldiğinde hesaba dahil edilir; **hedef sonucunun önceden bilindiği iddiası yok**.

## 36 gerçek çekilişin tek tek hareket tablosu

| Adım | Çekiliş | Saat | Bütün 224 halkada sınıf değişen hücre | Halka 12 | Halka 72 | Halka 672 | Halka 2688 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 61978 | 16:57 | 1082 | 22 | 16 | 2 | 2 |
| 2 | 61979 | 17:02 | 1122 | 28 | 14 | 6 | 2 |
| 3 | 61980 | 17:07 | 1116 | 30 | 16 | 2 | 6 |
| 4 | 61981 | 17:12 | 1077 | 31 | 12 | 4 | 4 |
| 5 | 61982 | 17:17 | 1078 | 22 | 20 | 8 | 8 |
| 6 | 61983 | 17:22 | 1028 | 32 | 16 | 4 | 6 |
| 7 | 61984 | 17:27 | 1089 | 27 | 14 | 4 | 2 |
| 8 | 61985 | 17:32 | 1057 | 25 | 16 | 8 | 2 |
| 9 | 61986 | 17:37 | 1099 | 27 | 14 | 4 | 0 |
| 10 | 61987 | 17:42 | 1021 | 31 | 18 | 6 | 2 |
| 11 | 61988 | 17:47 | 1054 | 21 | 12 | 6 | 2 |
| 12 | 61989 | 17:52 | 1075 | 29 | 12 | 6 | 2 |
| 13 | 61990 | 17:57 | 1131 | 32 | 14 | 8 | 4 |
| 14 | 61991 | 18:02 | 1073 | 28 | 12 | 4 | 2 |
| 15 | 61992 | 18:07 | 1050 | 25 | 18 | 2 | 6 |
| 16 | 61993 | 18:12 | 1152 | 22 | 16 | 4 | 4 |
| 17 | 61994 | 18:17 | 1125 | 24 | 12 | 2 | 4 |
| 18 | 61995 | 18:22 | 1073 | 33 | 22 | 4 | 4 |
| 19 | 61996 | 18:27 | 1089 | 22 | 18 | 2 | 6 |
| 20 | 61997 | 18:32 | 1123 | 27 | 18 | 4 | 4 |
| 21 | 61998 | 18:37 | 1205 | 22 | 16 | 4 | 2 |
| 22 | 62000 | 18:47 | 1117 | 21 | 14 | 2 | 4 |
| 23 | 62001 | 18:52 | 1134 | 35 | 12 | 8 | 2 |
| 24 | 62002 | 18:57 | 1096 | 28 | 8 | 8 | 0 |
| 25 | 62003 | 19:02 | 1077 | 26 | 14 | 4 | 4 |
| 26 | 62004 | 19:07 | 1096 | 25 | 20 | 6 | 0 |
| 27 | 62005 | 19:12 | 1157 | 27 | 16 | 10 | 2 |
| 28 | 62006 | 19:17 | 1093 | 30 | 14 | 6 | 0 |
| 29 | 62007 | 19:22 | 1172 | 32 | 10 | 4 | 4 |
| 30 | 62008 | 19:27 | 1118 | 24 | 12 | 10 | 0 |
| 31 | 62009 | 19:32 | 1107 | 28 | 14 | 6 | 2 |
| 32 | 62010 | 19:37 | 1149 | 27 | 18 | 6 | 2 |
| 33 | 62011 | 19:42 | 1208 | 28 | 16 | 10 | 0 |
| 34 | 62012 | 19:47 | 1151 | 30 | 22 | 6 | 0 |
| 35 | 62013 | 19:52 | 1174 | 33 | 16 | 2 | 0 |
| 36 | 62014 | 19:57 | 1095 | 29 | 12 | 4 | 0 |

Görüldüğü gibi 2688'lik halkada bazı tekil adımlarda **0 sınıf değişimi** yaşanırken 12'lik halkada çok daha fazla sayı sınıf değiştirebilir. Ancak 2688'lik pencerede görünme sayıları ve sıralar sınıf değişmese bile değişebileceğinden tam veri sadece bu tabloda değildir.

## Görsel oynatıcı kullanımı

1. Yukarıdaki **HTML oynatıcı dosyasını indirip telefonda tarayıcıyla aç**.
2. Başlangıç sahnesi **adım 0**: 36 kayıt öncesinin 224×80 sıcaklık matrisi.
3. **İleri ▶** butonuyla #61978, sonra #61979,... sırayla ilerlet; kaydırıcıyla 0–36 arasında gez.
4. **Havuz sınıfı / önceki adıma göre değişim** seçenekleriyle renkli haritayı çevir.
5. **Sayı seç** kutusundan 1–80 seç veya renkli matrise dokun. O sayının tüm 224 halkadaki ısınma/soğuma/sabit sınıf sayılarını ve önemli halka değerlerini gör.
6. Arşivde aynı verinin **eski/yeni sıralama ve adet hesapları** ile 36×224×80 tekil geçişler CSV ve bütün 37 durum NPZ biçiminde de bulunuyor.

### ZIP içerisindeki dosyalar

- `00_TURKCE_KISA_RAPOR.txt`: Özet, 36 çekiliş çizelgesi.
- `01_TEK_TEK_36_CEKILIS_HAREKET_OZET.csv`: 36 adım toplam hareket, 12/24/36/72/672/1344/2016/2688 halkaları.
- `02_HER_CEKILIS_224_HALKA_DEGISIMI.csv`: **36×224=8064** halka-adım yön, frekans, rank ve 5×5 sıcaklık matrisi.
- `03_HER_CEKILIS_80_SAYI_224_HALKA_YON_OZET.csv`: **36×80=2880** sayı-adım yön profili, 224 halkalık C/0/W kodu.
- `04_TUM_ADIM_224_HALKA_80_SAYI_TAM_ESKI_YENI.csv.gz`: **645.120** eskiden yeniye her sayı-halka-çekiliş satırı, tam eski/yeni count/rank/pool ve giriş/çıkış.
- `05_224_HALKA_BES_HAVUZ_TOPLAM_GECIS.json`: 224 halkada beş havuzun gerçek toplam geçiş 5×5 matrisi.
- `06_TUM_37_DURUM_224_HALKA_80_SAYI_FULL_NPZ.npz`: bir başlangıç + 36 çekiliş sonrasındaki sayım, rank ve sıcaklık dizilerinin tamamı.
- `V128_36_ADIM_224_HALKA_GORSEL_OYNATICI.html`: tamamı içinde kayıtlı, ağ gerekmeden çalışan interaktif adım adım görselleştirme.
- `07_METOD_VE_KONTROL.json`: gerçek kaynak kimlikleri, akış denetimleri, tutarlılık.

**Bu analiz, tarihsel gerçek sonuç girildikten sonra hangi hareketin oluştuğunu gözlemler. Yeni bilinmeyen sonuçlara ait gelişmeler önceden ölçülmedikçe bu bir RNG tahmin başarısı veya isabet avantajı göstermez.**
