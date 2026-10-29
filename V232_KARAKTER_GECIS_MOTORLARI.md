# V232 — Karakter geçişine göre 10'lu kolon motorları

## Ana ekran, sabit havuz ve arşiv

Streamlit giriş dosyası **`v230_gece_merkezi.py`**. Eski uygulama ve V231 laboratuvarı korunur.

Sol menüde **🧬 Karakter geçiş motorları** bölümünü aç. Gün seçildiğinde:

- **Üstteki 22:57 sabit havuzu değişmez:** 07:02–22:57 arası 192 gerçek çekilişten 80 sayı, her biri 16 sayılık beş havuza ayrılır.
- Dört hareket fotoğrafı **11:57, 15:57, 19:57, 22:57** anlarının geçmişten gelen son 72 çekiliş penceresinden hesaplanır. Bunlar sabit 192 gündüz havuzuyla **aynı şey değildir**.
- Hedef 23:02, 23:07, …, 23:57 ve ertesi gün 00:02, …, 01:02 arasında **25 gerçek 20'li** olabilir.
- Her gece çekilişinde 22:57 sabit havuz konumu aynen gösterilir. Hareketli havuz yine ayrı alt paneldedir.

## Altı paralel hipotez

| Kod | Girdi ve davranış |
| --- | --- |
| `IVME_DEVAMI` | Önceki 6/12/36/72 sonuçtaki frekans ve havuz yolunun yönü |
| `TERS_DONUS` | Kısa dönem hız tersine dönüşü ve dörtlü gündüz yolunun yön değişimi |
| `HAVUZ_FAZ_GECISI` | Son üç gece çekilişinin **gerçek** havuz dağılımına göre, gerekirse bir koltuk kaydırılan 5×16 kota |
| `AILE_ESLIK` | Geçmiş 24 çekilişte son üç gerçek çekilişin sayılarıyla aynı 20'lide bulunma |
| `KARMA_KARAKTER` | Dört skor listesinin önceden belirlenmiş eşit-ağırlıklı sıra birleşimi |
| `RASTGELE_KONTROL` | Aynı hedef için değişmeyen tohumdan rastgele 10 sayı; adil matematiksel beklenti **2,5/10** |

Beş motor **her hedef için birer 10'lu** üretir. İlk dört ve karma motorun çoğu beş sabit havuzdan **2+2+2+2+2** seçer. `HAVUZ_FAZ_GECISI` yönteminde gözlenen son gece dağılımı yeterince farklıysa iki havuz arasında **bir koltuk** aktarılır. Altıncı rastgele kontrol havuz kısıtına tabi değildir.

Bu yöntemler önceden belirtilmiş **hipotezlerdir**. Geçmişte bir hareket sınıfını gözlemek gelecekte aynı sayının seçileceğini kanıtlamaz.

## Canlı dondurma

Bir gecenin **sonraki henüz gerçekleşmemiş çekilişi** için motorları çalıştır. Kolonlar o hedefin sonucu girilmeden bir defa oluşturulur; değişmez.

- Tarih/slot, önceki son gerçek kayıt saati, sonuçtan önceki kaynak parmak izi ve her motorun 10 sayısı aynı kayıtla tutulur.
- Gerçek 20'liyi yüklediğinde **ana gece ekranında o çekilişin altına** hedef öncesi kolonlar ve her birinin **0–10 isabeti** eklenir.
- Geçmişe ait eksik bir saati sonradan doldurmak **canlı tahmin** sayılmaz. Yalnız tarihsel kör yürütme testinde karşılaştırılır.
- Streamlit oturumu yeniden başladığında geçmişte kilitlenmiş kolonlar kaybolabilir. **JSON yedeğini indir**; bu sürüm GitHub veya veritabanına otomatik yazmaz.

## 70 gece arşiv backtest

**`70 geceyi tek tek sına`** düğmesi, 192 gündüz + 25 gece sonucu tam olan en fazla **70 geceyi** işler. Her gece **25 hedef × 6 motor** değerlendirilir: en fazla **10.500 kolon-hedef kaydı**.

Üç CSV:
1. Her motor için **0/10…10/10** frekansları, ortalama isabet, 6+, 7+, 8+.
2. 70 günün motor başına ortalama isabetleri.
3. Her hedefin **önceden oluşturulmuş 10'lusu, gerçek 20'lisi, kaynak son zamanı ve isabeti**.

Geçmişte motor tanımları zaten üzerinde çalışılan verilerden etkilenmiş olabilir; bu nedenle 70 gece tablosu keşif testidir. **Yeni, hiç kullanılmamış günlerde önceden kilitlenmiş** sonuçlar olmadan üstünlük iddiası yapılmaz.

## Kurulum

GitHub deposu `gozlekakif-alt/hizli-on-analiz-motoru`, dal `main`, Streamlit **Main file path = `v230_gece_merkezi.py`**. Yeni modüller `v232_gecis_motorlari.py` ve `v232_gecis_app.py` giriş dosyasından çağrılır. Eski V18–V55, Z3, XGBoost, NumPy, Numba, SciPy modülleri durur.

Elimizdeki ham arşivde 72 kayıtlı takvim günü, 15.624 gerçek çekiliş, **72 tam gündüz penceresi** ve **70 tam operasyonel gece** var (1 Ağustos – 12 Ekim 2026 kayıtları). Arşiv Streamlit'e TXT/GZ dosyası olarak ayrıca yüklenmelidir.

## Sınırlar

Çekilişin gerçek rastgele üretecini veya tohumlarını çözmüş değiliz; hiçbir motorun rastgele kontrole üstünlüğü doğrulanmış değil. Teknik testlerden başarılı geçmek **kazanma olasılığını artırma kanıtı değildir**.
