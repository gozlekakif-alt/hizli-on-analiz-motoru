# V99B — Saatlik Mikrokripto H1–H6: İki Önceki Saatin Rakam Geçmişi

**Tarih:** 16 Ekim 2026  
**Çalışma:** [V99B gerçek veri testi](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38894138075) — **SUCCESS**  
**Kod:** [v99b_saatlik_mikro_dna_h4_h6_72gun.py](v99b_saatlik_mikro_dna_h4_h6_72gun.py)  
**Tam ZIP raporu:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38894138075/artifacts/12043595628

## İstek ve tanım

Bu çalışma **aile** ya da **kupon** analizi değil. Her bir rakamın **davranış yolu** analiz edildi.

- **C:** Mevcut saatten iki önceki *tam* saatin son 3 çekilişi (3 bit).
- **B:** Mevcut saatten bir önceki *tam* saatin son 3 çekilişi (3 bit).
- **A:** Mevcut saatin ilk 3 çekilişi (3 bit).
- Sonra bu rakamın **4., 5. ve 6. çekilişte** verdiği üç bitlik cevap (8 desen).
- İlk 3 çekilişteki çıkış sayıları: **0/3, 1/3, 2/3, 3/3**. Çekiliş sırası korunarak 000, 100, 010, 001, 110, 101, 011, 111 desenleri ayrı tutuldu.
- Sayıların 4. ve 5. çekilişten sonraki **0/4–4/4** ve **0/5–5/5** durumları tek tek kontrol edildi; ilk 6 çekilişin 0/6–6/6 yolları tam bit desenlerinden türetilebilir.
- Önceki saatler gerçek takvim saatleriyle kontrol edildi; gece 01:02 ile 07:02 arasındaki uzun boşluk **ardışık saat sayılmadı**.

Veri: 72 tam gün / 15.624 çekiliş / 1.296 tam saat. Tam C-B-A üçlüsü olan 1.150 hedef saat, **92.000 rakam-saat izi**, 4/5/6 için **276.000 geçiş kontrolü**.

## İlk 3 → İkinci 3: Gerçek dağılım

| İlk 3 | Sonraki 3'te 0 | Sonraki 3'te 1 | Sonraki 3'te 2 | Sonraki 3'te 3 |
|---|---:|---:|---:|---:|
| 0/3 | %42,415 | %42,247 | %13,803 | %1,535 |
| 1/3 | %41,904 | %42,276 | %14,268 | %1,552 |
| 2/3 | %41,608 | %42,710 | %14,200 | %1,481 |
| 3/3 | %44,941 | %39,428 | %14,375 | %1,256 |
| Adil teorik beklenti (hangi ilk 3 olursa olsun) | %42,1875 | %42,1875 | %14,0625 | %1,5625 |

Bu oranların yakın olması, geçmişteki tekrar sayısının geleceği güçlü biçimde belirlediğini göstermiyor. **3/3** grubu diğerlerinden biraz farklı, ancak nadir ve çoklu deneme ile görülen fark kanıtlanmış sinyal değil.

## 0/3 olan sayıların ilk aktivasyonu

38.760 başlangıçta 0/3 sayı-saatinin:
- 4. çekilişte ilk görünüşü **9.646 = %24,886** (adil referans %25)
- 5. çekilişte ilk görünüşü **7.301 = %18,836** (adil referans %18,75)
- 6. çekilişte ilk görünüşü **5.373 = %13,862** (adil referans %14,0625)
- 6 çekilişte hiç görünmeyen **16.440 = %42,415** (adil referans %42,1875)

## 4., 5. ve 6. çekilişte önceki görülme sayısına göre aktivasyon

| Sıra | Öncesinde kaç kez görüldü | Bir sonraki çekilişte çıkma |
|---|---:|---:|
| H4 | 0/3 | %24,886 |
| H4 | 1/3 | %25,064 |
| H4 | 2/3 | %25,399 |
| H4 | 3/3 | %22,749 |
| H5 | 0/4 | %25,077 |
| H5 | 1/4 | %24,950 |
| H5 | 2/4 | %25,170 |
| H5 | 3/4 | %23,984 |
| H5 | 4/4 | %27,607 (yalnız 326 örnek) |
| H6 | 0/5 | %24,632 |
| H6 | 1/5 | %25,030 |
| H6 | 2/5 | %25,349 |
| H6 | 3/5 | %24,832 |
| H6 | 4/5 | %25,253 |
| H6 | 5/5 | %20,000 (yalnız 90 örnek) |

Beklenen koşullu olasılık **%25**. Bir rakamın ilk beş elde gelmemesi H6'yı 'borçlu' yapmaz.

## Gerçek geçmişe-göre değerlendirme

İlk 36 gün öğrenme, sonraki 18 gün doğrulama ile **tek** model seçimi, son 18 gün tarihi kontrol. Brier skorunda küçük sayı iyidir; her çekilişte tüm 80 sayıya %25 tahmin vermenin Brier kaybı 0,1875.

| Model | Doğrulama Brier | Son 18 gün Brier |
|---|---:|---:|
| Sabit %25 | **0,187500000** | **0,187500000** |
| A geçmişi: yalnız H1..H5 sayı adedi | **0,187491130** | 0,187502210 |
| A geçmişi: tam bit sırası | 0,187535314 | 0,187534134 |
| A, B, C toplam sayıları | 0,187576288 | 0,187563701 |
| A, B, C tam bit geçmişi | 0,187668911 | 0,187639722 |
| B, C tam bit geçmişi | 0,187671638 | 0,187605988 |

Doğrulama kazananı A-geçmişinin **kaç kez çıktığı** bilgisi. Ancak kontrol döneminde sabit %25 modelini geçemedi: fark **+0,000002210** (daha kötü); 18 gün bazında yaklaşık %95 aralık **[-0,00001223, +0,00001665]**.

**Karar:** İlk altı çekilişte çok ayrıntılı ve gerçek mikro davranış desenleri var; bunlar açıklayıcı istatistikler olarak değerli. Fakat önceki iki saatin geçmişi, gerçek tahmin gücünü henüz kanıtlamadı. Üretim kupon motoruna eklenmemeli.

Önemli sınır: V9–V99 aşamalarında aynı 72 günlük veri defalarca incelendi; 'holdout' tarihen sıralı olsa da gerçekten dokunulmamış ileriye dönük örnek değil. Yeni çizilen çekilişlerde zaman damgalı tahminlerle doğrulama gerekir.

## ZIP rapor dosyaları

1. `00_SONUC_V99B.txt`
2. `01_TAM_8x8_ILK3_SON3_BIT_DIZILIMLERI.csv`
3. `02_ILK3_SON3_DORT_KADEME_GECISLER.csv`
4. `03_H4_H5_H6_TUM_GECIS_DURUMLARI.csv`
5. `04_0_3_SAYILAR_ILK_NE_ZAMAN_UYANDI.csv`
6. `05_GECMIS_2_SAAT_9_BIT_505_KOD.csv`
7. `06_80_SAYI_KIMLIGININ_MIKRO_GECISLERI.csv`
8. `07_5_MODEL_DOGRULAMA_KOR_TEST.csv`
9. `08_YONTEM_DENETIM.json`
