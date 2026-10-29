# V231 · Ortak yazılım laboratuvarı

**Açılış dosyası:** `v230_gece_merkezi.py` (değişmedi). Sol menüden **🧪 Ortak yazılım laboratuvarı**.

## Bileşenler ve görevleri

- **Python:** 22:57'de dondurulmuş, 80 sayının 5×16 havuz kimliğini ve gündüz hareket yönünü tutar. 23:02–23:57 aynı gece, sonraki günün 00:02–01:02 saatleri operasyonel geceye bağlanır. Sabit havuz gece boyunca asla güncellenmez; en alttaki hareketli son72 havuzu ayrıca güncellenir.
- **Z3:** Her havuzdan 2 sayı, 10 benzersiz sayı, mümkün olduğunda en az bir yükselen ve düşen sayı kısıtlarıyla alternatif 10'lular çözer. Bu bir mantık **kısıt çözümü**dür, RNG tahmini değildir.
- **XGBoost:** Son 72 gerçek çekilişten gecikme/ısıl yön/görünme özelliklerini çıkarır; gün bazlı sabit 70/30 kronolojik ayrımda eğitilir ve gelecekte yer alan test hedeflerinde önceden seçtiği 10 sayıyı rastgele kontrol ile aynı gerçek 20'lide karşılaştırır. Testten sonra parametreler değiştirilirse sonuç bağımsız test sayılmaz.
- **NumPy / Numba:** Gerçek 20'li içinde bulunan 3.160 olası ikilinin sayımını iki farklı uygulamayla hesaplar; tam eşitlik doğrulaması içerir.
- **SciPy:** Sabit beş havuzun gerçekleşen gece katılımını %25 basit rastgele referansına göre hesaplar; ham ve 5-test düzeltilmiş p-değerini gösterir. Bir çekilişin 20/80 örneklemi yerine koymasız olduğu için **binom yaklaşımı yaklaşık**dır.
- **Eski V18/V35/V39/V40/V41/V42/V44/V45/V50/V52/V54/V55:** Kendi orijinal koduyla açılan araştırma sekmeleri. V42'nin beş hareketli havuzu sabit 16 adet değildir, V230 ile tanımları farklıdır.
- **GitHub Actions:** Python/Streamlit çalışma, paket uygunluğu, 22:57 sabitliği, 25-slot gece takvimi, 10'lu havuz kısıtları, Z3 çözümü, XGB test ayrımı, NumPy–Numba eşitliği ve 12 eski modülün import testleri.
- **Termux:** Telefonda yerel geliştirme aracıdır; Streamlit Cloud çalıştığı sunucuda Termux çalıştırılmaz. Python/Z3 aynı işlevi bulut Python ortamında sağlar.

## Yayımlama

Streamlit Community Cloud'da `gozlekakif-alt/hizli-on-analiz-motoru` deposu, `main` dalı, **main file path = `v230_gece_merkezi.py`**. Kök `requirements.txt` Z3, XGBoost, NumPy, Numba, SciPy ve scikit-learn'i yükler.

## Veri kalıcılığı ve dürüst kontrol

Gerçek çekiliş dosyasını `veri.txt`, CSV, ZIP veya GZ olarak yükle; analize başlamak için seçilen tarihte 07:02–22:57 arasında **192 tam gündüz çekilişi** gerekir. Elle girilen 20'li için gerçek çekiliş ID'si zorunludur. 80'li sabit havuzdan gerçek gece 20'lileri aşağı doğru gösterilir.

Streamlit oturumu **kalıcı veritabanı değildir**. Yeni girilen kayıtlar GitHub'daki `veri.txt` dosyasına kendiliğinden yazılmaz. TXT yedeklerini indirip sonraki oturuma aktar. Kaynak geçmişi değiştirilince eski XGB raporu geçersiz sayılır.

Adil 20/80 çekilişte herhangi bir 10'lu kolonun beklenen isabeti 2.5'tir. Yukarıdaki yöntemler için gerçek RNG'nin keşfi ya da kazanç üstünlüğü kanıtlanmamıştır.
