# Hızlı On – Tam İsabet Araştırma Motoru V1

Bu paket kullanıcının 14 günlük 3.038 çekilişlik veri dosyasını ilk açılışta SQLite veritabanına yükler.

Özellikler:
- 14 günlük başlangıç verisini otomatik tanır ve yükler.
- Tek çekiliş ekleme.
- TXT/CSV veya yapıştırma ile toplu çekiliş ekleme.
- Her yeni sonuç geldiğinde yalnız o hedef için daha önce üretilmiş kuponları kontrol eder.
- Sonucu `x/4` ve `x/5` olarak saklar; 4/4 ve 5/5 sayaçlarını gösterir.
- Son sonuçtan sonra bir sonraki çekiliş için yeni kolonları otomatik üretir.
- 20 sayılık REAL20 aday havuzunun tamamını gösterir.
- Her aday için H yaşı, kaynak (H1/SHORT/MID/LONG/DEEP/YENI), R1-R4 ritim, H1 takım desteği, NEG/PROTECT ve seçim nedeni görünür.
- Genel sıcaklık/frekans sayı seçim puanı olarak kullanılmaz.
- SQLite kalıcı hafıza kullanır.

Çalıştırma:
1. `pip install -r requirements.txt`
2. `streamlit run app.py`

Not:
Bu uygulama araştırma/tahmin aracıdır. 4/4 veya 5/5 garanti etmez; gerçek performansı ileri çekilişlerde otomatik ölçer.
