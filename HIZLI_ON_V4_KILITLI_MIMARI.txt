HIZLI ON V4 — KİLİTLİ ARAŞTIRMA MİMARİSİ

AMAÇ
80 sayının her hedef çekiliş ÖNCESİ durumundan, gerçek 20 sayının hangi katmanlardan ve hangi adaylardan oluştuğunu walk-forward biçimde öğrenmek.

KİLİTLİ KURALLAR
1) Ham kaynak yalnız veri.txt gerçek çekilişleridir.
2) Hedef çekiliş sonucu hiçbir özellik/tahmin hesabında kullanılamaz.
3) Her hedef öncesinde 1–80 arasındaki tüm sayılar için snapshot oluşturulur.
4) Her snapshot'ta H3/H6/H12/H24/H48/H72, gün içi adet, gap, son görülme, son çıkış izi, aynı saat/dakika geçmişi, yön, sıcaklık skoru ve katman saklanır.
5) Katmanlar: SOĞUK / SERİN / NÖTR / ILIK / SICAK.
6) Katman kotası sabit değildir; her çekilişte yeniden hesaplanır.
7) Kota hesabı, o anda katmanda bulunan aday sayısını mutlaka hesaba katar.
8) Beş katmanın merkez kotası toplamı her zaman 20'dir.
9) Sonuç açıldıktan sonra 80 adayın tamamı ÇIKTI=1 / ÇIKMADI=0 olarak etiketlenir.
10) Çıkan 20 kadar çıkmayan 60 da öğrenme verisidir.
11) Her yeni çekiliş yalnız geçmişe eklenir; geleceğe sızıntı yasaktır.
12) Walk-forward sırası:
    snapshot -> kota tahmini -> aday sıralaması -> tahmini dondur ->
    gerçek sonucu aç -> puanla -> öğrenme havuzuna ekle -> sonraki hedef.
13) Saat, dakika ve gün karakteri ayrı hafızalarda tutulur; küçük örnekler düşük ağırlık alır.
14) Katman kotası kanıtlanmadan kupon motoru optimize edilmez.
15) Katman içi aday seçimi kanıtlandıktan sonra 20'lik hedef havuzu kurulur.
16) 10'lu kupon en son katmandır.
17) Performans: kota hatası, ±0/±1/±2, 20'lik havuz isabeti, 10'lu isabet,
    4+/5+/6+/7+, maksimum ve rastgele taban karşılaştırması.
18) Ham veri, snapshot, tahmin, gerçek sonuç, aday skorları, kupon ve performans ayrı dosyalarda tutulur.
19) Her kayıtta motor sürümü bulunur.
20) Uygulama kapanıp açıldığında checkpoint'ten devam eder; eski tamamlanmış çekilişleri gereksiz yere yeniden hesaplamaz.

İNŞA SIRASI
AŞAMA 1 — Veri doğrulama + 80-sayı snapshot + kalıcı checkpoint
AŞAMA 2 — Dinamik katman/kota motoru + gerçek/tahmin hata ölçümü
AŞAMA 3 — Saat/dakika/gün hafızası + tolerans kalibrasyonu
AŞAMA 4 — Katman içi aday ayırıcı (20 vs 60)
AŞAMA 5 — Walk-forward 20'lik hedef havuzu
AŞAMA 6 — 10'lu kupon üretimi ve 4+/5+/6+/7+ performansı

DEĞİŞMEZ PRENSİP
Sonucu gördükten sonra güzel görünen kural, hedef öncesi walk-forward testte çalışmıyorsa ana motora giremez.
