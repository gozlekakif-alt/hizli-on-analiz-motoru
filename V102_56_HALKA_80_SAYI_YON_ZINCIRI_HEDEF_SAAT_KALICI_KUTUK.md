# V102 — Her sayı için 56 halka yön zinciri → hedef saatin 12 çekilişi

**Tarih:** 16 Ekim 2026

**İstenen:** V100A/V100C'nin gerçek **672 çekiliş sabit hafıza, 12'li FIFO halkalar** mekanizmasını değiştirmeden her sayının halka halka **soğuk → serin → nötr → ılık → sıcak** yön hareketlerini görmek. **Kupon, kör test ve model seçimi yok.** Bilinen hedef saatin 12 çekilişi, saatten önceki 672 çekilişten oluşturulan halka yolculuğuna yalnızca *sonuç etiketi* olarak eklenir.

**GitHub çalışma kodu:** [v102_80sayi_56_halka_yon_zinciri_hedef_saat.py](v102_80sayi_56_halka_yon_zinciri_hedef_saat.py).  
**Başarılı çalışma:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38904158398  
**Tam ZIP (8 rapor):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38904158398/artifacts/12046614986

## Veriler ve mekanizmanın kesin tanımı

- 72 tam geçmiş gün + 13 Ekim ek kayıtları; kaynakta **15.790** gerçek çekiliş.
- H1 02 ve H12 57 dakikasında olmak üzere **1.246 tam, 12'li hedef saat** incelendi. Eksik/uyumsuz **76 saat grubuna** hedef etiketi verilmedi; eksik veriler uydurulmadı.
- Her saat başlamadan önceki **son 672 gözlenen çekiliş** referans. 12 çekilişlik küresel halka ID'si **yeniden bölünmez**. Hedef saat kaydına geçince en eski çekiliş çıkar, yenisi girer.
- Her hedef öncesinde **55 ya da 56 dolmuş tam halka** bulunur; eksik en eski ve yeni halka ayrıca **açık** etiketlenir (toplam 56/57 fiziksel halka).
- Dolu halkanın bitiminde sayının son **72 gözlenen çekilişteki frekansı** ile 80 sayı 16'şarlı sıcaklık havuzlarına ayrılır. Aynı halkanın kendi **12 çekiliş sıklığı** ayrı katman olarak saklanır.
- **Tam yön dizisi:** Dolu halkalardaki her sayının `C/S/N/I/H` havuz kimliği ve bir önceki dolu halkaya göre `Y/D/=` (yükselme/düşüş/sabit). Yön büyüklüğü ayrıntılı son hedef saati halka tablosunda bulunur.
- **Son 6 halka ısınma:** Son dolu halkanın 72 penceresine göre sınıfı, 6 önceki dolu halkanın sınıfından yüksekse sayı ISINIYOR.
- Her sayının hedef saat içinde çıktığı **H1–H12 el sırası, 12 bitlik dizisi, kaç kere çıktığı** ayrıca kaydedilir.
- Her halka geçişinde ısınan tüm sayıların ve bu sayıların hedef saatte görünenlerinin **numaraları** listelenir; her hedef saat için.

## Temel davranış

**İki ardışık halka hareketinin aynı yönü koruma oranı %38,855** (durağan hareketler dahil). Aynı sayının iki ardışık halka hareketinde **her ikisinde de ısınma oranı %5,864**. Bu oranlar gözlemlenen seri hareketleridir; sıra değişimleri doğal olarak fazladır. Sayının hiç durmadan 56 kez yükselmesi, havuz sayısının yalnız beş oluşu nedeniyle zaten mümkün değildir. Dolayısıyla **tekrar eden kısa yön yolları, dönüşler, duruşlar ve geri dönüşler** önemlidir.

## Son tam hedef saatin gerçek örneği

**13.10.2026 19:02–19:57; H1 #62003, H12 #62014.** Öncesindeki son bilinen çekiliş **#62002**, referans penceresindeki en eski çekiliş **#61328**.

Bu saat öncesindeki 6 tamamlanmış halka hareketine göre:

| Yön | 80 sayı içinde | Hedef 12 çekilişte görünen farklı sayı |
|---|---:|---:|
| ISINIYOR | **33** | **33** |
| SOGUYOR | **30** | **30** |
| DENGELI | **17** | **16** |

Bir saat 12 çekiliş demek olduğundan **20 × 12 = 240 sayı görünümü** vardır. 12 çekiliş boyunca aynı sayının en az bir kez görünme olasılığı çok yüksektir: bu sayılar hedefte göründü diye tek başına öngörü başarısı iddia edilmemeli. El sırası, kaç kere göründüğü ve yön zinciri beraber değerlendirilmeli.

### İz sürme örnekleri

`C`=soğuk, `S`=serin, `N`=nötr, `I`=ılık, `H`=sıcak.

| Sayı | Son 12 dolu halka sıcaklık dizisi | Son altı halka net yön | Hedef 12 el içinde |
|---|---|---:|---|
| **44** | `SCCCCCCSNHHH` | **+4** kademe | **H3, H5, H12** |
| **10** | `HNSSCCCNINNH` | **+4** kademe | **H4, H9** |
| **11** | `CSSCNSINIINH` | **+3** kademe | **H1, H3, H5, H10, H11** |
| **58** | `INCCCCCCCCCI` | **+3** kademe | **H1, H3, H7, H9, H12** |
| **72** | `NINNNNIHIIIH` | **+2** kademe | **H5, H7, H8, H10, H11** |

Örneğin **44**, son 12 tamamlanmış halka boyunca serinden soğuğa indi; soğukta bir süre kaldı, tekrar serin→nötr→sıcak tarafına yükseldi, son halkalarda sıcakta sabitlendi. Son hedef saatte 3., 5. ve 12. çekilişte gözlendi. **Bu zincirin her bir adımı ayrıca 80 × 56/57 tablosunda kayıtlıdır.**

## Neden aynı yönü koruma ve hedefe gelme ayrı şeyler?

- Yön özelliği yalnızca hedeften **önceki** 672 gerçek çekilişin halkalarından hesaplanıyor.
- Sonraki hedef saatin sonuçları, sayının yolunu bulmakta **kullanılmıyor**; sadece saat sonunda hangi elde çıktığını işaretliyor.
- Halka bazında **tüm 80 sayının** ısınma/soğuma/sabit listeleri, bunların hedef saatte görünen **numaraları** ve ardışık iki halka adımında aynı hareketi tekrar yapan sayı sayıları var.
- Böylece bir sayı sadece “sıcak” değil; “56 halka boyunca hangi yollardan geçerek ısındı ve hedef saatin tam hangi ellerinde ortaya çıktı?” sorusuyla okunuyor.
- Veri eski araştırmalarda çok kez incelenmiş olduğundan burada hiç **tahmin avantajı** iddia etmiyoruz; bu katman davranış haritasıdır.

## ZIP içindeki tam araştırma dosyaları

1. `00_V102_56_HALKA_YON_SONUCLARI.txt` — genel sayı örnekleri ve sonuç.
2. `01_TUM_SAATLER_80_SAYI_56_HALKA_ZINCIRI.csv` — 1.246 hedef saatin **80 sayısının tamamı** için 55–56 harflik ısı ve yön DNA dizisi; hangi H1–H12 elinde görüldüğü.
3. `02_TUM_SAATLER_HALKA_BASINA_ISINAN_VE_HEDEFTE_CIKAN.csv` — **her hedef saat ve her halka geçişinde** ısınan/soğuyan/sabit numaralar; hangileri hedef saatte göründü.
4. `03_SON_HEDEF_SAAT_80x56_TAM_HAREKET_FILMI.csv` — en son tam saatte **80 sayının bütün fiziksel halkalardaki** kademe, yön, 12'lik ve 72'lik havuz geçmişi.
5. `04_SON_HEDEF_SAAT_12_EL_CIKANLAR_YONLER.csv` — H1–H12 her elde hangi sıcaklık/yön grubundan hangi sayılar çıktı.
6. `05_TUM_HEDEF_SAAT_80_SAYI_YON_DAGILIMI.csv` — her hedef saat ısınan/soğuyan/dengeli sayılar ile o saatte görünenler.
7. `06_GECMIS_GUNLER_YON_GRUBU_SAATTE_GORUNUM.csv` — dönem dönem grup hareketi ve ortalama saatlik görünüm.
8. `07_VERI_YON_KODU_DENETIM.json`.

**Sonuç:** Kullanıcının istediği *her halkada ne yana gitti; aynı yönde devam etti mi; bu sayı hedef saatin hangi çekilişinde geldi?* zinciri kuruldu. V100C'nin sabit 672 FIFO omurgası ve halkaları korunuyor. İstenirse yeni saatlerin verisi kayda eklendiğinde V102 aynı şekilde tekrar çalışıyor ve zincir kesilmeden güncelleniyor.
