# V37B — Aile + Isı Yön Uzmanlarının Ortak Hafızaya Bağlanması
**Tarih:** 14.10.2026

## Amaç
V37'nin tek `draw_ledger` + `ball_step` SQLite geçmişinden **çekiliş çekiliş** aile ve yön olaylarını türetmek. Yeni uzmanlar 80 sayının 1/0 geçmişinin yeni bir kopyasını oluşturmaz. Var olan sayı olaylarının ID'leri üzerinden aile–yön bağlantısı kurar.

## Bu sürümde çalışan uzmanlar

1. `FAMILY.PAIR_12`: Önceki 11 gerçek çekilişte birlikte görülen ikilinin mevcut çekilişte tam 2/2 tekrarı.
2. `FAMILY.TRIPLE_12`: Önceki 11 çekilişte görülen üçlünün bu çekilişte tam 3/3 tekrarı.
3. `FAMILY.QUARTET_12`: Dörtlünün önceki 11 çekilişle tam 4/4 tekrarı, art arda gelme veya araya çekiliş girerek yeniden birleşme.
4. `FAMILY.QUARTET_COVER_PATH`: Mevcut gerçek çekilişte 4/4 bir araya gelen dörtlünün üyelerinin önceki 11 + mevcut çekilişte **ilk ne zaman görünmüş olduğunu** 4, 3+1, 2+2, 1+3, 2+1+1 vb. yol sınıflarına tam sayım olarak ayırır.
5. `DIRECTION.HEAT_6X6`: Altı ısı haznesinin 36 olası önceki→sonraki geçişi, 80 sayının tamamı üzerinden.
6. `DIALOGUE.FAMILY_HEAT`: Dörtlü aile üyelerinin yönleri arasındaki ilişki ve kaynak `HEAT_SEAT` olaylarının ID'leri.

Ayrıca her çekilişte tekrar eden farklı ikili/üçlü/dörtlü aile sayıları **tam**, örnek dörtlü ailelerin bireysel delilleri **en fazla 8 çekiliş başına** kayıt olarak tutulur. Dolayısıyla örnek listesi **bütün 4'lü ailelerin tam dökümü değildir**. Bu kaynak/süreç seçiminin sınırı raporda gösterilir.

## Kritik anlam ayrımı

**Parçalı kapsama vs tam geliş:** Bir dörtlünün iki üyesi bir çekilişte, diğer iki üyesi sonraki çekilişte gelmiş ama dördü **asla aynı tek çekilişte birleşmemişse**, bu olay henüz V37B'nin kapsama tablosunda bulunmaz. V37B'nin 3+1/2+2 değerleri yalnızca **gerçek 4/4'ü de mevcut çekilişte bulunan** dörtlülerin 12 adımlık ilk görülme bileşimlerini ifade eder. Dört üyeli aile için yalnızca parçalı gelen, hiç 4/4 yapmayan hayatların tam izlenmesi **V37C'de ayrı bir iş** olacaktır.

**Sessizlik:** Bir ailenin bir çekilişte 4/4 gelmemesi, dört üyenin hiçbirinin gelmediği anlamına gelmez. İkisini ayırmak için kaynak çekilişler ve son tam birleşme olayları ayrı tutulur.

**Motor ilişkisi:** Aynı çekilişte ailenin yeniden birleşmesi ve üyelerin farklı ısı yönlerine geçmesi zaman birlikteliğidir. Nedensellik veya gelecek 20'yi bulma anlamına gelmez.

## Kalıcılık ve işleme

- `v37_ortak_hafiza.py`: değiştirilmeden ana yaşam kaydı. Mevcut SQLite üzerine uzman tabloları eklenir.
- `v37_aile_yon_uzmanlari.py`: uzman olayları ve diyalog tabloları; idempotent işlem.
- `v37_aile_yon_app.py`: Streamlit ana uygulamasındaki **🧩 V37B Aile + Yön Uzmanları** sekmesi, bir tuşla hem ortak hafıza doğrulaması hem uzman ilerletmesi.
- `v37_aile_yon_selftest.py`: küçük örneklerle 3+1/2+2 kombine aile yolları, 80 ısı koltuğu, boşluk, çift işlem engeli ve tarihsel bilgi izolasyonu.
- `v37_aile_yon_export.py`: otomatik ZIP.
- `.github/workflows/v37b-aile-yon-check.yml`: bütün gerçek veri üzerinden otomatik tarihsel denetim ve ZIP.
- Eski `veri.txt` ana kaynaktır, Streamlit Cloud geçici diski kalıcı GitHub veritabanı yerine geçmez.
- Yeni gerçek çekilişler eklenince önce ortak hafıza son ekten devam eder, aile uzmanı da yalnız yeni çekilişlerde olay ekler. Kaynak geçmişi düzeltilmişse yeni bir DB gerekir.

## Mevcut sınır

V37 için tasarlanan **207 alt dalın tamamı çalışıyor değildir**. Bu sürüm yalnızca 6 yeni araştırma uzmanını ortak hafızaya bağlar. RNG algoritması/tohumu çözüldü veya kupon avantajı bulundu iddiası yoktur. Bir sonraki aşamada parçalı gelip tek çekilişte hiçbir zaman 4/4 yapmamış aileler, sessiz bekleme epizotları, daha uzun aile ömrü ve motif–geçiş matrisi tamamlanacaktır.
