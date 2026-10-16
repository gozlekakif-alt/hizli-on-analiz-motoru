# V114 — 56 gerçek kapalı 12'li halka 0/1, FIFO ve yedili aile ayrılıp birleşmesi

**Doğrudan doğrulanmış çalışma (SUCCESS):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38942116179  
**11 parçalık ZIP artifact:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38942116179/artifacts/12063996152  
**Çalışan kod:** [v114_56_halka_80_sayi_01_kayit_ve_7li_aile_birlesme.py](v114_56_halka_80_sayi_01_kayit_ve_7li_aile_birlesme.py)

## Ne istendi?
1–80 sayıların **1=çekilişte çıktı, 0=çıkmadı** biçimindeki gerçek kayıtları, 56 halka boyunca 12 çekiliş × 80 sayı ve sabit halka kimliğiyle sakla. **56. en yeni tamamlanmış halkada** her sayının toplam kaç kez görüldüğünü ver. Ayrıca önceki araştırmadan farklı olarak yedili ailelerin bütün halka boyunca **aynı 16'lık sıcaklık havuzunda toplanıp dağılması** ile hedef saatin gerçek ortak çıkışı arasındaki ilişkiyi araştır.

## Kaynak ve gerçek fiziksel halka kuralları

- Kaynak `veri.txt` toplam **15.790 kayıt**, en son **13.10.2026 saat 19:57, çekiliş #62014**.
- Sabit 12'li halka kimliği, 1 Ağustos 2026 ilk kaydından itibaren *mutlak*; her yeni çekilişte yeniden bölümleme yok.
- En yeni kapanan fiziksel halka **#61992 – #62004 arasındaki 12 gerçek çekiliş**, mutlak halka ID **1314**. Bu analizde güncel **56. TAM halka**, önceki 55 tam halkayla birlikte en yeni **56 kapanmış halkayı** ifade ediyor.
- Bundan sonra gelen **10 gerçek çekiliş #62005–#62014**, yeni fiziksel halkanın **10/12'lik PARÇASI**. Bu parçayı kullanıcıya tam halka gibi göstermemek gerekiyor.
- Güncel **tam 672 FIFO çekiliş** içinde **57 fiziksel parça** vardır: en eski fiziksel halkanın sadece son **2 çekilişi** + **55 tam 12'li halka** + en yeni halkanın ilk **10 çekilişi** = **2+660+10 = 672**. Bu nedenle *en yeni 56 kapanmış halka* ve *tam kayan 672 çekiliş* **aynı veri aralığı değildir**; ikisinin 0/1 kayıtları ayrı dosyalarda tutuldu.
- **Halkada 12×20=240 toplam görünüm** ve 80 adet 12 bit tutarlılığı kontrol edildi.

## 56. tamamlanan halka 1–80 sayım

| Sayı | Çıkış | Sayı | Çıkış | Sayı | Çıkış | Sayı | Çıkış |
|---:|---:|---:|---:|---:|---:|---:|---:|
|1|4|21|3|41|1|61|2|
|2|6|22|5|42|3|62|4|
|3|2|23|3|43|3|63|0|
|4|1|24|1|44|4|64|2|
|5|3|25|4|45|5|65|3|
|6|4|26|3|46|3|66|3|
|7|1|27|4|47|3|67|4|
|8|4|28|5|48|1|68|4|
|9|2|29|1|49|4|69|1|
|10|3|30|5|50|2|70|2|
|11|2|31|3|51|2|71|3|
|12|4|32|3|52|5|72|1|
|13|2|33|3|53|2|73|3|
|14|2|34|3|54|2|74|5|
|15|2|35|3|55|2|75|4|
|16|5|36|2|56|3|76|2|
|17|4|37|3|57|4|77|5|
|18|4|38|1|58|2|78|5|
|19|5|39|2|59|2|79|2|
|20|4|40|5|60|4|80|2|

**En çok:** #2 altı kez. **Sıfır:** #63 hiç çıkmadı. Tam çıkış vektörü 12 bitlik: **#2 = `000111001110`**, altı adet 1 içerir.

## Yedili ailenin 56 halka boyunca yeniden bir araya gelmesi

- Her günün hedef son saati başlamadan H22'deki iki gerçek çekilişin **tam yedi ortak üyesinden** yedili aile oluşturuldu, aynı V113 kuralı. **69 son saatten 68'inde** önceden aile vardı.
- 56 halka havuz kimliğinde ailenin yedi üyesi **hangi havuzlarda** sayıldı. Son 12 halkada, önceki 6 halkadan birinde en fazla 2 üye aynı havuzdayken son 6 halkadan birinde **en az 4 üyenin aynı havuza toplanması** = `reunion4`. Bu gösterge hedef saatin sonucunu hiç kullanmaz.
- Geçmiş 69 saat, 68 aile, sonraki **816 gerçek hedef çekiliş**. Kronolojik ilk34 ve son35 ayrı.

| Son 35 gün, pretarget 56 halka | Aile günü | H23 gerçek çekilişleri | Aileden çekiliş başına ortalama | 5/7+ | 6/7+ |
|---|---:|---:|---:|---:|---:|
| Son halkalarda önceden **4 üyelik birleşme** oldu | 11 | 132 | 1,7273 | **0** | 0 |
| Birleşme olmadı | 23 | 276 | 1,7935 | **3** | 0 |

İlk 34 günde birleşme olanlarda **0/192**, olmayanlarda **2/216** adet 5/7+ vardır. **Toplam: 4 üyelik pretarget birleşme olduğunda 0/324 adet 5+/7**, birleşme olmadığında **5/492**. Sayılar küçük; ailelerin yeni çekilişte üstün olduğunu kanıtlamak için kullanılamaz.

### 12 Ekim son saat örneği

H22 öncesi görünümden seçilen aile **1,9,27,41,42,44,78**. En eski 56 halka pozisyonları sırasıyla **Nötr, Serin, Serin, Nötr, Nötr, Serin, Nötr**; son kapalı halkada **Sıcak, Soğuk, Nötr, Ilık, Sıcak, Serin, Sıcak**.

Hedef 23:02–23:57, 12 çekilişte bireysel toplamlar:
- 1→2, 9→2, 27→4, 41→6, 42→2, 44→5, 78→4.
- Ailede önceden en az dört üyenin aynı havuza toplandığı halka görülmüş olsa da, sonraki **12 çekilişin hiçbirinde** yedi sayıdan beşi aynı anda görünmedi. *Bir sayının aynı saatte 6 kez çıkması*, *yedili ailenin tek çekilişte 5/7 bulması* değildir.

## Tek ZIP'deki denetlenebilir gerçek kayıtlar

1. `00_V114_TURKCE_GERCEK_SONUC_VE_80_SAYI_LISTESI.txt` — 80 adet sayının halkada çıkış sayısı ve tam 12 basamak 0/1 dizileri.
2. `01_56_HALKA_EN_SON_TAM12_1DEN80E_SAYI_SAYIM.csv` — 80 sayının 56. tamamlanmış halkadaki çıkış sayısı, an, kapalı halka havuzu, en son kayan 12'linin de ayrı kıyası.
3. `02_56_TAMAMLANMIS_HALKA_80_SAYI_0_1_DIZI_4480_SATIR.csv` — **56×80=4.480** ring-sayı kaydı, her kayıtta **12 gerçek 0/1**, toplam **53.760** ikili gözlem.
4. `03_YURUYEN_SON672_80_SAYI_TAM_0_1_IZ.csv` — **80×672** gerçek FIFO 0/1 satırları, 57 gerçek fiziksel ring/parça işaretleri.
5. `04_SON672_FIZIKSEL_57_PARCA_GIRIS_CIKIS_SAYILARI.csv` — her fiziksel bölümün sayısı, ilk-son ID ve tam/eksik etiketi.
6. `05_H22_ONCEDEN_SECILEN_7LI_AILE_56_HALKADA_BIRLESME.csv` — 69 gün boyunca yedili ailelerin 55/56 kapalı halka başına beş havuza dağılımı.
7. `06_7LI_AILE_H23_816_CEKILIS_GERCEK_BIRLIKTE_CIKIS.csv` — önceden birleşmenin ardından gerçek hedefte üye sayısı.
8. `07_GUN_GUN_7LI_AILE_ONCEDEN_BIRLESME_ARDINDAN_H23.csv` — her gün yedi üyenin önceden seçilen aile kimliği ve skorları.
9. `08_ILK34_SON35_BIRLESME_5_7_DURUM_GRUPLARI.csv` — tarihsel dönemleri ayrı tutan kalibrasyon tablosu.
10. `09_AILE_UYELERI_ILK_HALKA_SON_HALKA_HEDEF_0_1.csv` — yedili üyelerin baştan sona sıcaklık filmi, ardından hedef 12-bit çıkışları.
11. `10_HAVUZ_FIZIKSEL_HALKA_DOGRULAMA.json` — veri ve halka bütünlük kontrolü.

**Sınır ve karar:** Havuz dağılımı son 72 çekilişten mekanik olarak hesaplanır; çıkan sayının sonra ısınması gelecek çekilişte öne çıkarır demek değildir. İlgili 72 gün daha önce araştırılmıştı, dolayısıyla bu karşılaştırma yeni, bağımsız kör test değildir. *Şu ana kadar birleştirilen 7'li ailelerin gelecek tek çekilişte üstün oldukları gösterilmedi.*
