# V37C — Hiç aynı çekilişte 4/4 olmadan tamamlanan dörtlü aile yaşamı
**14 Ekim 2026 · V37 ortak hafızanın üçüncü araştırma katmanı**

## Neden yeni motor?

V37B ikili/üçlü/dörtlü birlikteliklerinin tekrarını ve **mevcut çekilişte gerçekten 4/4 görünen** dörtlülerin geçmişte ilk görülme sırasını hesaplıyordu. Kullanıcının sorduğu farklı olay, **bir dörtlünün üyelerinin farklı çekilişlerde tamamlanması, ama o pencerenin hiçbir çekilişinde dördünün aynı anda bulunmaması**dır.

## V37C iki ayrı kapsamı açıkça ayırır

### 1) Tam sayım — bütün 1.581.580 olası dörtlüden
İki **ardışık gerçek çekilişin** sayı birleşimleri:
- `1+3`: bir üye önceki çekilişte, daha önce görülmeyen diğer üç üye sonraki çekilişte; bu iki çekilişin hiçbirinde aynı anda 4/4 yok.
- `2+2`: ilk çekilişte iki üyeye rastlandı, diğer ikisi ilk kez sonraki çekilişte; aynı iki çekilişte tam 4/4 yok.
- `3+1`: ilk çekilişte üç üye, sonraki çekilişte ilk kez dördüncü üye; yine aynı iki çekilişte 4/4 yok.

Üç **ardışık gerçek çekilişin** ilk görünme birleşimleri:
- `1+1+2`
- `1+2+1`
- `2+1+1`

Bu ailelerin kombinasyonları **tam sayılır**, her birini 72 gün boyunca bellekte yaşatmak yerine combinatorik alt havuz hesabı kullanılır. Üç adımlık dizinin son çekilişinde 4/4 birleşmiş olanlar dışlanır. Ancak bir dörtlünün daha önce başka günlerde veya sonrasında 4/4 yaşayıp yaşamadığı **bu iki/üç adımlık tam sayımın kapsamı değildir**.

### 2) Uzun yaşam örneklemi — 2.048 önceden seçilmiş aile
80 sayıdan olası 4'lü ailelerin `C(80,4)=1.581.580` farklı kimliğinden, resmî sonuçları kullanmadan **önceden sabit tohumla** 2.048 farklı dörtlü üniform örneklenir. Örneklem aile kimlikleri ve SHA-256 parmak izi ZIP içinde saklanır.

Her gerçek çekilişte:
- Dörtlünün 0, 1, 2, 3 veya 4 üyesi var mı?
- Son 12 gerçek çekilişin birleşiminde 4 farklı üyenin tamamı görüldü mü?
- Bu sayıların hepsi **son 12 gerçek çekilişlik parçada** aynı tek çekilişte hiç 4/4 yapmamış mı? Önceki dönemlerde 4/4 yapmış olması yeni parçalı yaşamı engellemez.
- Parçalı tamamlanma daha önce oldu mu; sessizlik bitiminde tekrar oldu mu?
- Dörtlünün **bütün üyeleri** kaç gerçek çekiliş üst üste çıkmadı?
- Üyelerin sıcaklık havuzu yönleri ne, aynı çekilişte ne yönde hareket ettiler?
- Sıcaklık uzmanının ortak `reservoir_event` kayıtlarında bunu destekleyen kaynak ID'leri var mı?

Günlük/çekilişlik örneklem sayımları **2.048 ailenin tamamını** kapsar; ayrıntılı olay delilleri her çekiliş için **en fazla 12 sabit ön kayıt sırasındaki olay** ile sınırlandırılır. Sınır ayrı raporlanır. Bu, 1,58 milyon ailenin ömürlük tam sayımı olarak sunulmaz.

## 7 dosyalı çıktı

1. `01_HER_CEKILIS_2_3_ADIM_PARCALE_FAMILY_TAM_SAYIM.csv`: Her gerçek çekilişte tam sayımlar ve örneklem karakterleri.
2. `02_2048_KAYITLI_DORTLU_HAYAT_ORNEKLERI.csv`: Tarih, aile kimliği, 12 gerçek çekilişlik ilk tam parçalı kapsama, sessizlik, yön, kanıt linkleri.
3. `03_ONCEDEN_SECILEN_2048_TARAFSIZ_AILE.csv`: Ön kayıt aileleri ve SHA.
4. `04_ILK_VE_SON_YARI_CROSS_TEST.json`: İlk ve son yarının zaman sıralı betimsel kıyası; kayan pencereler bağımlıdır.
5. `05_HESAP_TANIMLARI_VE_KAPSAM.txt`: Kapsam ve hata payının anlamı.
6. `06_KAPSAM_HAZNE_META.json`: Tam sayım / örneklem ayrımı.
7. `07_2048_AILENIN_OMURLUK_KARAKTER_KARTI.csv`: Her aile için parçalı kapanma sayısı, 4/4 olup olmadığı ve sessizlik ömrü.

## Veri mimarisi

`v37c_parcali_aile_hayati.py` önceden doğrulanmış `v37_ortak_hafiza.py` içindeki **tek** `draw_ledger` + `ball_step` ve sıcaklık olaylarından beslenir. Yeni `v37c_step`, `v37c_family_events`, `v37c_checkpoint` tabloları aynı SQLite'a eklenir; ham 1/0 geçmişin başka kopyası oluşturulmaz. V37C işaretçisi aynı kaynak geçmiş ve aynı örneklem parametreleri korunduğu sürece yalnız yeni gerçek çekilişlerden devam edebilir. Eksik gerçek çekiliş yeni örüntü oluşturmaz; 01:02→07:02 13→14 kesintisiz gerçek sıra olarak alınır. Günlük 12'lik parçalı hafıza sıfırlanır, ailelerin ömür boyu daha önce 4/4 gösterip göstermediği silinmez.

## Sınırlar

Bütün 207 tasarım dalı tamamlanmadı; bu sürüm iki/üç adımlık parçalı oluşum uzmanlarını ve 12 adımlık **örneklem aile hafızasını** çalıştırır. 72 günlük geçmişteki desenleri açıklamak ile rastgele RNG'nin gizli durumunu çözmek **farklı iddialardır**. Gelecek 20'nin kimliği bilinmiyor. Bu rapor **öncelikle betimsel**, bağımsız gelecekte kupon isabet üstünlüğü kanıtı değildir.

**GitHub Streamlit V10 sekmesi:** `🧩 V37C Sessiz Parçalı Aileler` — tek tuşla aynı ortak SQLite üzerine kayıtlar, tek ZIP.

## Araştırmada bulunan önemli metodolojik düzeltme (V37C v2)

72 gün boyunca hiç **bir kez bile** 4/4 yapmamış sabit dörtlü aileler üzerinden yaşam aramak yanlış bir eşik: 2.048 tarafsız örnek ailenin tamamı ilk 36 günde en az bir defa aynı çekilişte 4/4 görmüştür. Bu nedenle V37C'nin ilk tarihsel denemesinde ikinci 36 gün için yeni parçalı aile olayı kalmamıştı. **V37C v2 bu hatalı sert ömürlük eşiği kaldırır:** Ailelerin *son 12 gerçek çekilişte* tam 4/4 yapmamışken üyelerini parçalı biçimde tamamlamasını, eski yıllarda/çekilişlerde 4/4 yapmış olsa bile yeni bir epizod olarak kaydeder. Geçmişteki toplam 4/4 sayısı ayrıca korunur. Bu değişiklik gizli RNG'ye erişim değildir; doğru yaşam-evre tanımıdır.

## 72 günlük başarılı tam araştırma, V37C v2

GitHub Actions **başarılı**: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38598125256

Tek 7 dosyalı ZIP (yaklaşık 10,1 MB): https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38598125256/artifacts/11913016372

- 72 tam gün, 15.624 gerçek çekiliş, ortak SQLite'dan 1.249.920 sayı kartı.
- 1.581.580 olası dörtlünün iki/üç ardışık çekiliş içindeki *parçalı oluşum olayları* tam sayıldı. Benzersiz aile sayısı değildir.
- İki çekiliş penceresi olayları: 1+3 = **115.286.052**, 2+2 = **298.680.433**, 3+1 = **262.741.377**.
- Üç çekiliş penceresi olayları: 1+1+2 = **260.485.056**, 1+2+1 = **363.034.038**, 2+1+1 = **488.103.316**.
- Sonuçlardan bağımsız 2.048 ön kayıtlı dörtlünün 12 gerçek çekilişlik parçalı yaşamı kaydedildi.
- İlk 36 günde parçalı yeniden oluşum olayları: **527.296**; son 36 günde **524.952**. Bunlar kayan pencere boyunca birden fazla sayılan **olaylardır**, benzersiz aileler değildir.
- Delili bireysel saklanan sınırlı örnek olay: **134.041** (her çekilişte en çok 12 ön sıralı olay; toplam olayların tamamı değildir).
- Önceki katı «ömrü boyunca hiç 4/4 yapmasın» şartı kaldırıldı; son **12 gerçek çekilişte** tam 4/4 yapmamışsa daha önce yaşamış 4/4 olayına rağmen yeni parçalı hayat evresi olarak izlenir.
- Hem ilk hem son 36 günün özel aile ve yön kayıtları üretilir; bu sonuçlar **gerçek gelecek 20'yi daha iyi bilme kanıtı değildir**.
