# V37 B — Aile motorları ve sıcaklık yönlerinin ortak hafızaya bağlanması

**Tarih: 14.10.2026.** V37 A'nın SQLite ana hafızası kullanılır. Veri tekrar kopyalanmaz; motorlar gerçek `draw_ledger`, `ball_step` ve `reservoir_event` tablolarını okur. Yeni uzmanların kodu `v37_aile_yon_uzmanlari.py`, testi `v37_aile_yon_selftest.py`.

## Gerçekten çalışan alt uzmanlar

1. `FAMILY.PAIR_12`: Son 11 gerçek çekilişte tam görülmüş bir ikilinin bu çekilişte yeniden 2/2 olması.
2. `FAMILY.TRIPLE_12`: Son 11 gerçek çekilişte tam görülmüş bir üçlünün bu çekilişte yeniden 3/3 olması.
3. `FAMILY.QUARTET_12`: Son 11 gerçek çekilişte tam görülmüş dörtlünün bu çekilişte yeniden 4/4 olması; ardışık ve ara çekilişli sessiz tekrar ayrımı.
4. `FAMILY.QUARTET_COVER_PATH`: Şimdiki gerçek 20 içindeki bütün **4.845 farklı dörtlü** için son 11 + şimdiki çekilişte her üyenin ilk görünme sırası. 4, 3+1, 2+2, 1+3, 2+1+1, 1+2+1, 1+1+2 ve 1+1+1+1 oluşma yollarının exact kombinatorik sayımı; daha önce dört üyesi de görülmüş aileler ayrıca sayılır.
5. `DIRECTION.HEAT_6X6`: Sıcaklık sıralamasının altı koltuğunda önceki çekiliş→şimdi 36 hücre, yükseliş/düşüş/sabit sayıları. 80 sayıyı eksiksiz kapsar.
6. `DIALOGUE.FAMILY_HEAT`: Yeniden tam birleşen dörtlü üyelerinin ısı değişimlerine bağlı ortak olay; kaynak `HEAT_SEAT` olay kimliklerini içerir.

## Bilinmesi gereken sınırlar

**Aile motorunun '3+1, 2+2, 2+1+1' yolları yalnızca dördü de aynı şimdiki çekilişte mevcut olan dörtlülerin 12 gerçek çekilişteki ilk görülme kapsamını açıklar.** Ayrı çekilişlerde dördünün toplamda görülüp hiçbir çekilişte 4/4 oluşmadığı aileler bu ilk sürümde tam izlenmez; gelecek yaşam motorlarında ayrı aday aile ve epizot takibi gerekir. Aile örnekleri çekiliş başına ilk 8 delilli aileyle sınırlandırılır; ikili/üçlü/dörtlü tam tekrar sayıları ve bütün 4/4 kapsama biçimleri ise eksiksiz sayılır. Bu örnek seçimi isabet amaçlı değil, kayıt boyutunu düşürmek içindir.

Bir aile hiç 4/4 değilse ama üç üyesi farklı çekilişlerde çıkmışsa 'tam aile tekrarlandı' denmez. Tam ailenin sessizliği ile bütün üyelerin sessizliği de aynı değildir.

**RNG sınırı:** Geçmiş motiflerin sık sık görülmesi 80'den gelecek 20 sayıyı bildiğimiz anlamına gelmez. Motorların işe yarama ölçütü önce eksiksiz olay geçmişi, hatasız sıralama ve açıklanabilir çapraz bağlar; ancak daha sonra önceden belirlenmiş ileri testle olası sayı avantajıdır.

## Veri ve çıktı

- V37 ortak SQLite dosyasına eklenen tablolar: `v37_family_step`, `v37_heat_transition`, `v37_family_examples`, `v37_family_heat_dialogue`.
- Ayrı küçük ZIP: `V37_AILE_VE_ISI_YON_UZMANLARI_TEK_ZIP.zip`, toplam 7 dosya.
- Asıl V37 ortak SQLite ZIP'i: `V37_ORTAK_80_SAYI_YASAM_HAFIZASI_TEK_ZIP.zip`.
- Streamlit: `v10_app.py` → **V37 Ortak Yaşam Hafızası** → aynı başlat düğmesi iki çalışmayı da yapar.
- GitHub Actions: `.github/workflows/v37-hafiza-check.yml`; tam veri analizinde önce ortak hafıza, sonra bağlı aile/yön uzmanları, sonra iki ayrı ZIP yayımlanır.
- Artımlı çalışma: Tam geçmiş aynı ise aile özeti tekrar yazılmaz, yalnız yeni çekilişler işlenir; işlem her çekiliş sonunda tutarlı SQLite kaydı oluşturur. Eksik pozisyon sahte 'çıkmadı' sayılmaz; 01:02→07:02 gerçek ardışık 13→14 adımıdır.

## Sonraki araştırma

1. Tam 72 günlük olay sayımlarını ölçüp adil 20/80 benzetimiyle kıyasla.
2. Bir aile tam 4/4 olmadan ayrı çekilişlerde parçalı gelişini sürdüren **kalıcı aile epizodu** motoru ekle.
3. Aile–bekleme–ısı–bant zincirlerini tarihsel örneklem ve yeni zaman sıralı testle karşılaştır.
4. Sürekli akort edilen klonun kendi aile olaylarının gerçek dağılımlara ne kadar benzediğini göster; gelecekte sayı kimliği tahmini ayrı denetimdir.
