# V126 — BÜTÜN 224 İÇ İÇE HALKADA 80 SAYININ HER YENİ ÇEKİLİŞTEKİ TAM YÖN HAREKET KÜTÜĞÜ

**TAM KAYIT BAŞARIYLA OLUŞTURULDU ve KALICI GITHUB RELEASE OLARAK YAYIMLANDI.**

- **Kalıcı GitHub Release:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/tag/v126-2026-10-13-224-rings-lossless
- **Doğrudan 510 MB'lık TAM VERİ ZIP'i:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/releases/download/v126-2026-10-13-224-rings-lossless/V126_224_HALKA_80_SAYI_HER_ADIM_FULL_LOSSLESS.zip
- **Kaydı üreten kalıcı kaynak kod:** [v126_224_halka_tum_sayilar_adim_adim_eksiksiz_kayit.py](v126_224_halka_tum_sayilar_adim_adim_eksiksiz_kayit.py)
- **İstediğin çekilişi/sayıyı/halkayı açıp CSV yazan okuyucu:** [v126_detay_oku.py](v126_detay_oku.py)
- **Başarılı tam analiz koşusu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38975652486
- **Başarılı KALICI release yükleme koşusu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38975841223

## Hangi çekilişler, hangi halkalar?

Kaynak depodaki **veri.txt**, 15.790 gerçek çekiliş, son kayıt 13 Ekim 2026 **#62014**. İlk **2.688 çekiliş** başlangıç hafızasıdır. Ardından **13.102 yeni çekilişin tamamında**, **224 iç içe kümülatif halka × 80 sayı** yeni gözlenen sonuçla tek tek güncellendi. İlk replay çekilişi **#48693**. Takvim bazında **61 güne bölünmüş** eksiksiz, kayıpsız veri arşivi oluşturuldu.

- Halka 1: son 12 çekiliş; halka 2: son 24; ... halka 56: son 672; halka 112: son 1344; halka 168: son 2016; halka 224: son **2688 çekiliş**.
- Halka sayısı 224'tür; **224 farklı ayrık 12 çekilişlik blok değildir**. Aynı anda geçmişe açılan iç içe 224 penceredir.
- Her çekiliş geldiğinde **224 halkanın TAMAMI bir çekiliş ilerler**.
- Her halkada 80 sayı, görünme adedi sırasına göre **16 SOĞUK + 16 SERİN + 16 NÖTR + 16 ILIK + 16 SICAK** ayrımındadır. Eşitlikte küçük sayıya öncelik verilir.
- Aile ilişkisi, kupon seçimi ve hedef sonrası bilgiyle geleceği tahmin karışıklığı yoktur. **Bu kütük yalnız gözlenen her adımın oluşan değişimini kaydeder; tahmin başarısı kanıtı değildir.**

## Gerçekte tamamlanan işlem

| İçerik | Gerçek değer |
|---|---:|
| Tam çekiliş kaynağı | **15.790** |
| İlk hafıza | **2.688** |
| Yeni çekiliş adımları | **13.102** |
| Her adımda iç içe halkalar | **224** |
| Her halkada takip edilen sayılar | **80** |
| Ayrıntılı tam sayı–halka–adım hücresi | **234.787.840** |
| Kaydedilen toplam gerçek sıcaklık sınıfı değişimi | **13.737.622** |
| Günlük kayıpsız NPZ veri dosyası | **61** |
| Bütün ZIP içindeki girişler | **70** |
| Kalıcı GitHub release ZIP boyutu | **509.668.735 byte (~486 MiB)** |

### Her bir (çekiliş, halka, sayı) için saklanan gerçek ayrıntı

1. Sayının o çekilişte **çıktı mı çıkmadı mı**, yeni giriş biti (1/0).
2. Söz konusu halkanın arkasından tam o adımda **hangi eski çekilişin çıktığı**, bu sayı için ayrılma biti (1/0).
3. Halkadaki eski/yeni gerçek görünme sayısı; yön **−1, 0, +1** ve bunun gerekçesi: `X[t,ball] − X[t−L,ball]`.
4. **Eski ve yeni 0–79 sıralaması** (en soğuktan en sıcağa); rank hareketinin işareti ve adım boyu.
5. **Eski ve yeni SOĞUK/SERİN/NÖTR/ILIK/SICAK sınıfı**, ± kaç sınıf geçtiği.
6. Sayının sıklığı değişmese de başka sayılar hareket ettiği için **sıra veya sınıf değişimi** mutlaka ayrı görünür.
7. Her çekilişte her halka için **5×5 eski→yeni havuz geçiş matrisi** (halkada toplam 80 üye korunuyor).
8. Her adımda 80 sayı için, 224 halkanın **kaçında sıklığı, sırası veya havuzu yükseldi/azaldı**, girme/çıkma sayıları.
9. 224 halka için her adımın **+1/−1/0 adetleri, rank ve sıcaklık yönü sayıları**, eski/yeni 1/0 çakışma sayıları.
10. Günler arası devam eden değişimleri takip etmek için **ilk adım öncesi tam başlangıç durumu** + her günün bütün **tam count/rank/pool 224×80 anlık görüntüleri**.

Günler arası tam state geçişi de yeniden kurulabilir. Eksik sayı-halka-adım bırakılmadı. ZIP bütünlük kontrolü GitHub Actions içinde başarıyla geçti.

## En hareketli ilk halkaların gerçek günlük değil, ÇEKİLİŞ başına sınıf değişimi

| Halka büyüklüğü | Ortalama her yeni çekilişte sıcaklık sınıfı değiştiren sayı |
|---|---:|
| Son 12 | **26,989849** |
| Son 24 | **21,979392** |
| Son 36 | **18,672874** |
| Son 48 | **16,523203** |
| Son 60 | **14,928713** |
| Son 72 | **13,811708** |
| Son 84 | **12,903145** |
| Son 96 | **12,100824** |
| Son 108 | **11,486567** |
| Son 120 | **10,963746** |
| Son 132 | **10,429705** |
| Son 144 | **10,113341** |

Çok önemli: Burada halkadaki **sıcaklık sınıfı değiştiren SAYI SAYISI** ölçülüyor; yalnız çıkış adedi ±1 değişimi değil. Dolayısıyla sınıfı değişen sayı o çekilişte çıkmamış da olabilir.

## Tam arşivin içindekiler

- `00_INITIAL_CONDITION_BEFORE_FIRST_DRAW.npz`: ilk geçiş öncesi her sayı × 224 halkanın gerçek çıkış adedi/rank/pool.
- `FULL_EACH_STEP_BY_DAY/<tarih>.npz`: 61 günün her birinde her çekiliş için **tam 224×80 sayım ve sıralama ve sınıf durumu**, ayrıca halkanın çıkardığı eski 80'lik 1/0 bitleri, yeni çekilişin 1/0 bitleri, 5×5 havuz geçişleri ve ring/sayı özetleri. NumPy veri tipi ve dizi şekilleri kaynak kodda tanımlıdır.
- `01_TUM_CEKILISLER_224_HALKA_GENEL_ADIM_OZET.csv`: 13.102 çekilişin her birinin toplam hareket ve yeni 20 sayılık sonuç özeti.
- `02_HER_CEKILIS_TARIH_SAAT_NPZ_KAYIT_INDEKSI.csv`: çekiliş numarası–tarih–saat–gün dosyası–satır indeksinin tamamı.
- `03_HER_HALKA_TOPLAM_KAC_YON_HAREKET_EDILDI.csv`: **224 halkanın** tam hareket toplamları, 5×5 sınıf matrisi.
- `04_GUN_GUN_HER_224_HALKA_HAREKET_DOKUMU.csv`: her gün ve her halkada gerçekleşen hareket toplamları.
- `05_HER_224_HALKA_80_SAYI_YON_HAREKET_ATLASI.csv.gz`: **224×80=17.920 sayı-halka ilişkisinin** bütün adımlar boyunca toplam yönleri.
- `06_SON_12_CEKILIS_224x80_EKSIKSIZ_ADIM_DETAY.csv.gz`: **son 12 gerçek çekilişin HER birinde 224×80 eski/yeni sayım/rank/pool/giriş/çıkış** okunabilir CSV biçimi.
- `07_METOD_VE_GUN_BLOK_LISTESI.json`: tüm 61 dosyanın tarihler/numaralar/byte boyları ve veri şeması.
- `00_KISA_TURKCE_KULLANIM_VE_SONUC.txt`: kısa bulgular.

## Herhangi bir olayı CSV olarak açma

Github'daki **[v126_detay_oku.py](v126_detay_oku.py)** şu işlevleri sağlar:

```bash
# Gerçekte saklanan son çekiliş #62014 geldiğinde 37 numaranın
# 224 halkanın her birindeki hareketini çıkar:
python v126_detay_oku.py --zip V126_224_HALKA_80_SAYI_HER_ADIM_FULL_LOSSLESS.zip --draw-id 62014 --number 37 --out SAYI_37_224_HALKA.csv

# Aynı çekiliş geldiğinde halka 224'te 80 sayı ne yaptı?
python v126_detay_oku.py --zip V126_224_HALKA_80_SAYI_HER_ADIM_FULL_LOSSLESS.zip --draw-id 62014 --ring 224 --out HALKA_224_80_SAYI.csv

# Aynı çekiliş ve halkanın tek sayısının tam öncesi/sonrası:
python v126_detay_oku.py --zip V126_224_HALKA_80_SAYI_HER_ADIM_FULL_LOSSLESS.zip --draw-id 62014 --ring 224 --number 37
```

## Kalıcılık ve denetim

**Önceki GitHub Actions 90 günlük artifact bağlantısı ile karıştırma.** Arşivin **kalıcı GitHub Release varlığı** `v126-2026-10-13-224-rings-lossless` etiketi ile resmen yayımlandı, GitHub API varlığın dosya boyutu `509668735` ve durumunu `uploaded` olarak doğruladı. GitHub Release dosyası kullanıcı tarafından silinmediği sürece süre dolduğu için otomatik silinen Actions artifact dosyalarıyla aynı 90 gün kısıtına tabi değildir.

Kod ve veri.txt de repo içinde kaldığından işlemi kaynak veriden yeniden üretmek mümkündür. Bu işin bir sonraki aşamasında, hareket profilinin **önceden bilinen kısmının** sonraki hedefte isabeti artırıp artırmadığı ancak ayrıca bağımsız testle ölçülebilir. İleri hareketleri tahmin ederken hedef çekilişten SONRA oluşmuş V126 durumunun kullanılması bilgi sızıntısı olur.
