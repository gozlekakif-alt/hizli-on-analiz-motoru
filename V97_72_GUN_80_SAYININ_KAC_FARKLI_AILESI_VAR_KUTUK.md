# V97 — 80 Sayının Günler Boyunca Girdiği Farklı Aileler

**Tarih:** 16 Ekim 2026  
**Kaynak:** `veri.txt`, 1 Ağustos–12 Ekim arası **72 tam gün, 15.624 geçerli çekiliş**.  
**Kod:** [v97_80_sayi_kac_farkli_aile_72gun.py](v97_80_sayi_kac_farkli_aile_72gun.py)  
**Başarılı GitHub Actions:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38886742424

## Net cevap

**Hayır, bir rakam her gün hep aynı aileyle çıkmıyor.** Her bir rakamın girdiği **tam 20 sayılık kadro, veri boyunca o rakamın tüm çekilişlerinde birbirinden farklı** çıktı. 80 rakamın her biri 79 farklı olası eşlikçisinin hepsiyle en az bir defa aynı 20'li çekilişte bulundu.

“Aile” kelimesi birden fazla şekilde sayılabildiğinden ayrı tutulmalı:

1. **Tam kadro:** O çekilişin tüm 20 sayısı. Bir rakam için çekiliş sayısı kadar ayrı 20'lik kadro var.
2. **V10 kayıtlı aile:** Önceden derlenmiş **1.131 adet 5–10'lu kesin sayı kümesi**. Bir ailenin **tam görünmesi**, tüm aile üyelerinin aynı 20'li sonuçta bulunmasıdır. Bütün 72 günde, bu katalogdaki 1.130 farklı aile en az bir kez tam göründü; **732** aile iki veya daha fazla farklı günde tam göründü; **337** aile 5 veya daha fazla farklı günde tam göründü. Bir rakamın yer aldığı, geçmişte en az bir kez tam görülmüş kayıtlı aile sayısı **61–274** (80 rakam ortalaması **99,875**). Katalog geçmiş verilerden seçilmiştir, dolayısıyla istatistiksel açıdan bağımsız bir sınama değildir.
3. **Doğal aile kökü:** Bir çekilişle önceki 12 kesintisiz çekilişten birinin **tam kesişimi**, 5–10 sayıdan oluşuyorsa kök olarak kaydedilir. Aynı çekilişte aynı kök farklı kaynak çiftlerinden gelirse yalnız bir kez sayılır. 10 sayıdan daha büyük kesişimler yapay biçimde 10'a düşürülmez, kapsam dışıdır. **113.775** farklı doğal kök bulunmuştur. Tek sayı için **7.893–9.189** ayrı kök görülmüş, fakat aynı kökün iki farklı günde tekrarına bakınca toplam yalnız **38** kök bu şartı sağlamıştır. Bu rakamlar **tüm olası alt ailelerin sayısı değildir** ve hiçbir gelecek tahminine kanıt değildir.

## Örnekler

| Rakam | Çıktığı 20'lik kadro adedi | Kayıtlı, tamamen görülen farklı aile | Bunlardan iki farklı günde görülen | 5–10 doğal kök |
|---:|---:|---:|---:|---:|
| 1 | 3.866 | **274** | 136 | 8.404 |
| 5 | 3.934 | 146 | 78 | 8.680 |
| 23 | 3.870 | 110 | 77 | 8.460 |
| 42 | 3.940 | 72 | 50 | 8.769 |
| 50 | 3.927 | 98 | 66 | 8.775 |
| 79 | 4.015 | 96 | 66 | 9.175 |
| 80 | 3.986 | 112 | 68 | 8.951 |

**Somut örnek:** 1 rakamının kayıtlı ve tam görülen 274 farklı 5–10'lu ailesi vardır. En sık tam gördüğümüz kayıtlı ailelerden `1-10-42-69-79` 72 günde **21 çekilişte**, **15 farklı günde** tam çıktı. Bu, 1'in tüm 3.866 çekilişte hep bu aileyle çıktığı anlamına gelmez. Bu grubu izlemek yeni çekilişte daha olası gelmesini sağlamaz.

## Analiz sınırları

- 20'li kadronun her çekilişte farklı olması adil RNG için şaşırtıcı değildir; tam 20'li kümelerin olasılık uzayı çok büyüktür.
- 1131 katalog ailesi kendi başına tüm var olan alt aileleri temsil etmez. 5–10'lu grupları her 20'liden sonradan tek tek çıkarırsak çok sayıda iç içe/korelasyonlu alt grup elde ederiz.
- Doğal kökleri keşfetmek için hedef çekiliş **görüldükten sonra** kesişim hesaplanır, bu yöntemle hedefi önceden bilmek mümkün olduğu iddia edilemez.
- **Aynı aileyi birkaç kez geçmişte görmek** bir sonraki çekilişte tekrar etme olasılığının yükseldiğini kanıtlamaz.

## Denetim ve indirilebilirler

GitHub Actions run: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38886742424/artifacts/12040090615

Tek ZIP içindeki sonuçlar:
- `00_SONUCLAR_VE_YONTEM.txt`: kısa sonuç
- `01_80_SAYI_KAC_FARKLI_AILE.csv`: 80 sayının tek tek 5–10'lu kayıtlı ve doğal kök aile sayıları
- `02_HER_SAYININ_ILK10_ESLIKCI.csv`: rakamların en sık görülen 10 eşlikçisi
- `03_1131_KAYITLI_AILE_KAC_GUN_TAM_CIKTI.csv`: kayıtlı 1131 aile ve tam çıkış günleri
- `04_BASKA_GUNLERDE_YINELENEN_ILK500_DOGAL_AILE.csv`: başka günlerde yinelenen doğal aileler (38 kayıt)
- `05_DENETIM.json`: veri ve yöntem kontrolü
