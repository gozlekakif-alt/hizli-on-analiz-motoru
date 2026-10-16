# V125 — 672×4 = 2.688 Çekiliş; 224 İç İçe 12'lik Çember

**Başarılı gerçek GitHub Actions analizi:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38974962709

**Tam ZIP (8 dosya, yaklaşık 2,27 MB):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38974962709/artifacts/12078547481

**Kaynak program:** [v125_2688_224_icice_12lik_cember_80_sayi.py](v125_2688_224_icice_12lik_cember_80_sayi.py)

## Kesin tanım

224 İÇ İÇE halka, son **12,24,36,...,2688** gerçek 20/80 çekilişin kümülatif pencereleridir; **224 ayrı 12'lik fiziki blok değil**. Hedef öncesi bütün halkalar aynı son çekiliş noktasında biter; yeni her çekilişte 224 halka bir birim kayar. Her pencerede 80 sayı görünme sıklığına göre beş 16'lık soğuk-serin-nötr-ılık-sıcak havuzundan birine atanır (eşitlikte sayının küçüğü önce).

15.790 geçerli gerçek kaynak çekiliş, en yeni #62014, 13 Ekim 2026. Veri kaynağı GitHub **veri.txt**. Son 2688 gözlenen çekiliş #62014 dâhil hesaplanır. 2.688 çekilişte 53.760 sayı görünmesi ve sayı başına matematiksel ortalama 672.

| Son N çekiliş | Matematiksel sayı ortalaması | Gerçekte maksimum | Gerçekte minimum | Fark | Fark/ortalama |
|---|---:|---|---|---:|---:|
| 672 | 168 | **64 →191** | **37 →146** | **45** | **%26,79** |
| 1344 | 336 | **8 →365** | **37 →297** | **68** | **%20,24** |
| 2016 | 504 | **77 →549** | **40 →458** | **91** | **%18,06** |
| **2688** | **672** | **6 ve 77 →706** | **40 →613** | **93** | **%13,84** |

Farkın büyümesi sıra ile **+23,+23,+2**; ilk iki +23 artışından genel bir oran yasası çıkarmanın hatalı olduğu son 2688 pencerede açıkça görüldü. Mutlak 93'lük fark, referans ortalamasına oranla azaldı.

## 80 sayının havuz istikrarı

| İki referansın karşılaştırması | Aynı sıcaklık havuzunda kalan | Havuzu değişen | Ortak sıcak 16 | Ortak soğuk 16 |
|---|---:|---:|---:|---:|
| 672 vs 1344 | 30 | 50 | 9 | 6 |
| 1344 vs 2016 | 35 | 45 | 10 | 10 |
| **2016 vs 2688** | **38** | **42** | **11** | **11** |
| **672 vs 2688** | **26** | **54** | **6** | **6** |
| 1344 vs 2688 | 31 | 49 | 8 | 9 |

## Yüksek isabet testi

İlk 2688 gözlem geçmiş hafıza; sonrasındaki **13.102 hedef çekiliş** için seçimler hedef çekiliş gerçekleşmeden önce yalnız son 672,1344,2016,2688 görünümlerinden çıkarıldı. Her yöntem hedef başına eşit sayıda kupon kullanır; aileler yok. Yöntemler HOT672, HOT1344, HOT2016, HOT2688, COLD2016, COLD2688 ve rastgele kontrol. 3,4,5,6,8,10,20 sayı boyu test edildi. Son 18 tam gün (3906 çekiliş) daha önce V9–V124 analizlerinde de incelendiğinden gerçek bağımsız gelecek testi değildir.

| Model | Son18 günde 10 sayı ortalama isabet | 5+/10 | 6+/10 | 8+/10 | 10/10 |
|---|---:|---:|---:|---:|---:|
| HOT672 | 2,49462 | 229 | 53 | 0 | 0 |
| HOT1344 | 2,48029 | 243 | 49 | 0 | 0 |
| HOT2016 | 2,48925 | 269 | 54 | 1 | 0 |
| **HOT2688** | **2,48080** | **247** | **51** | **0** | **0** |
| COLD2688 | 2,45622 | 245 | 55 | 0 | 0 |
| Rastgele | **2,49334** | **253** | **64** | **1** | **0** |

Son18 günlük eşlenmiş bootstrap'te HOT2688 − rastgele, çekiliş başına ortalama fark **−0,01255**, %95 belirsizlik aralığı **[−0,05991,+0,03738]**. Sıfırı kapsıyor; daha büyük 224 çemberlik referansın tek başına tahmin avantajı kanıtlanmadı.

## ZIP içeriği

- `00_V125_KISA_RAPOR.txt` — 672/1344/2016/2688 gerçek min-max ve kupon kontrolü
- `01_80_SAYI_672_1344_2016_2688_224_HALKA_2688_1_0.csv` — 80 sayının her birinde 224 halkalık çıkış sayıları, 224 sıcaklık sınıfı, geçmiş 2688 gerçek 1/0 kayıtları
- `02_672_1344_2016_2688_SICAK_SOGUK_REFERANS.csv` — min/max ve fark
- `03_56_112_168_224_HALKA_HAVUZ_DONUSUMLERI.csv` — havuz değişimleri
- `04_HER_HEDEF_672_1344_2016_2688_RASTGELE_ESIT_KUPON.csv` — her hedef/kupon gerçek sonuç
- `05_BOYUT_DONEM_3_4_5_6_8_10_20_SONUC.csv` — kupon büyüklüğü istatistikleri
- `06_SON18_GUN_GUVEN_ARALIKLARI.csv` — test farkı
- `07_METOD_KONTROL.json` — kaynak ve 224 halka denetimi

**Net sonuç:** Kullanıcının 672×4, 224 iç içe çember modeli veriyle çalıştırıldı. Görünme sayısı uç farkı son 2688 çekilişte 93. Salt uzun geçmişte en sık çıkan sayıları seçmek, geçmiş kontrol döneminde adil rastgele stratejiden daha iyi sayı tahmini sağlamadı.