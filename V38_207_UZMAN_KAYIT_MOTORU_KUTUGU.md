# V38 — 207 Uzmanlı Ortak Yaşam Hafızası Araştırma Sistemi
**14 Ekim 2026 — ilk çalışan 207-kimlikli gözlem sürümü.**

## Gerçek durum

V37'de tanımlanan **17 ana uzman grubundaki 207 mikro-uzmanın kimliği, adı, sırası ve çekiliş başına ayrı ölçüm görevi** bu sürümde bilgisayarın çalıştırabileceği katalog ve yürütücüye aktarılmıştır.

Katalog eksiksiz: `v38_207_katalog.py`; çekirdek: `v38_207_uzman_yurutucu.py`; Streamlit: `v38_207_uzman_app.py`.

**207 numaralı uzman kimliği = 207 bağımsız RNG algoritması değil.** Aynı geçmişi ve aynı çekilişi kullandıkları için ölçümleri birbirleriyle ilişkili olabilir. 160 uzman, tanımlı konuda bir çekilişlik sayısal durumu doğrudan ölçer. **47 uzmanın ölçümü ise bir tarama göstergesidir**; katalogdaki daha geniş hayat epizodunu/gerçek nedenselliği eksiksiz bitirdiği iddia edilmez. Bu 47 uzman ZIP'de açıkça `TARAMA_GOSTERGESI` olarak işaretlenir. Yaşamın tüm kılcallarını eksiksiz araştırmak için bu dallarda ayrı epizot yapıları ve ileri tarihli kontroller gereklidir.

## Çekiliş başına işleyiş

1. V37 ortak SQLite `draw_ledger` ve `ball_step` dosyasındaki 80 sayının geçerli gerçek durumuna bakılır. Kaynak 20/60 dengesi doğrulanır.
2. LIFE, HEAT, DIRECTION, WAIT, RETURN, BURST, STAGE, PAIR, TRIPLE, QUARTET, LARGE, BAND, MIRROR, CYCLE, TIME, DIALOGUE ve TWIN uzmanları aynı gerçek adıma ait **207 farklı kayıt alanı** üretir.
3. Her kayıt sayısaldır. İlgili olay yoksa `0` kaydedilir. Her çekiliş 207 alan tamamlanmadan ilerlemez.
4. Uzmanların geçmiş hafızası, kaynak hayat kayıtlarını **kopyalamadan**, yalnız ölçüm/checkpoint durumunu ortak SQLite dosyasına `v38_draw`, `v38_registry` ve `v38_checkpoint` tablolarına yazar.
5. Günlük geçerli 1–217 çekiliş sırası korunur. 01:02→07:02 resmi çekiliş adımları ardışıktır. Eksik gerçek kayıt, gerçekleşmiş bir `0` gibi doldurulmaz. Günlük 11'li pencereler ve döngüler doğru yerde yeniden başlar.
6. Dört üyeli ailelerin iki/üç adımlık parçalı tamamlanmasını V37C tam sayımlı formülleriyle üretir. Daha derin aile yaşam kimliklerini yalnız örneklem/tarama düzeyinde ölçtüğü konuları tam nüfus epizod sayımı diye sunmaz.
7. Bağımsız 20/80 kontrolü ve ayrı örnek klon kolu kullanılır; gelecek gerçek çekiliş sonucunu tarihsel durum üretiminde kullanmaz.
8. Eski aynı gerçek çekilişler tekrar geldiğinde ikinci kez yazılmaz. Sonuna çekiliş eklenirse geçmiş doğrulanır ve yalnız eklenen adımlar uzmanlara işlenir. Motor kodu/katalog değişirse eski checkpoint üzerinde sessizce devam edilmez.

## Gerçek teslimat sınırları

- **207/207 kimlik ve çekiliş başına sayısal ölçüm**: evet, kodlanmış.
- **207/207 uzun süreli eksiksiz uzman evre hafızası**: hayır; 47'si açıkça gösterge, ayrıca doğrudan ölçüm uzmanlarının hepsi de ayrıntılı olay epizodu değil.
- **İki/üç çekilişte tamamlanan dörtlüler**: V37C matematiksel tam sayımı kullanılır.
- **17 ana uzman grubunun aynı birincil 80 sayı yaşam kaynağını okuması**: evet.
- **207 ayrı bağımsız modül ve gizli RNG tohumu çözümü**: hayır.
- **Gerçek gelecek 20 sayıyı rastgele tabanın üstünde belirleme başarısı**: kanıtlanmadı; çıktı betimsel araştırma.
- **Kalıcı GitHub veri.txt ve tekrar işlenebilir ZIP**: evet; Streamlit Cloud geçici SQLite oturum diski tek başına kalıcı GitHub checkpoint'i değildir.

## Tek ZIP

`00_OKU_BENI.txt`: Kullanım ve bilimsel sınırlar  
`01_207_UZMAN_KIMLIK_VE_KAPSAM.csv`: Bütün 207 uzman ve 160/47 statüsü  
`02_HER_GERCEK_CEKILISTE_207_UZMAN.csv`: Her gerçek çekiliş için **tek satır / 207 uzman kolonu**  
`03_ILK36_SON36_207_UZMAN_DAGILIM.csv`: Her uzman için ilk/son yarı ölçümleri  
`04_17_GRUP_DETAYI.csv`: Ana dal etkinlikleri  
`05_KAPSAM_VE_METODOLOJI.json`: Hangi uzmanlar derin epizot değil / RNG kıyas sınırları

### Teknik dosyalar

- [207 katalog](v38_207_katalog.py)
- [207 uzman yürütücüsü](v38_207_uzman_yurutucu.py)
- [Streamlit tek tuş sekmesi](v38_207_uzman_app.py)
- [Sentetik ve geriye bakış güvenliği testleri](v38_207_selftest.py)
- [72 gün otomatik ZIP üreticisi](v38_207_export.py)
- [GitHub Actions iş akışı](.github/workflows/v38-207-uzman-check.yml)

**İnşa yaklaşımı:** Önce 207 uzman kimliği, sonra ayrı ölçüm defterleri, sonra kompleks 47 dalın eksik olan gerçek olay epizotlarını tek tek derinleştirerek `TARAMA_GOSTERGESI` statüsünden çıkarma. Bu, motor adlarını çoğaltmak yerine geçerli gözlemleri ilerletir.
