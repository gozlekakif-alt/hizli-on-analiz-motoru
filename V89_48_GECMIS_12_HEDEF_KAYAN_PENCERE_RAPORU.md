# V89 — 48 Çekiliş Hafıza → Sonraki 12 Çekilişte 4+/5+/6+ | Kayan Pencere

**Araştırma tarihi:** 16.10.2026. **Kaynak:** [veri.txt](veri.txt), 1 Ağustos–13 Ekim 2026. Bu bir **geçmişe dönük** testtir, yeni çekilişler için kanıtlanmış tahmin modeli değildir.

## Soru ve önceden tanımlanan ölçüm

- Her hedef için **önceki 48 gerçek, kesintisiz çekiliş** hafıza. Ardından **12 gerçek, kesintisiz çekiliş** (beşinci saat) hedef.
- Hedef: 1–80 arasındaki **tekil sayılardan hangileri, hedef 12 çekilişin içinde en az 4, 5 veya 6 ayrı çekilişte görünür?** Bu ölçüm aynı *tek çekilişte* 4/4 aile tamamlama ölçümü **değildir**.
- Ana değerlendirme: Her yöntem, hedef başlamadan **10 sayı** seçer. Bu 10 sayıdan kaçının sonraki 12 çekilişte 4+, 5+, 6+ olduğu ayrı ayrı sayılır.
- Hafıza her adımda **bir çekiliş** kaydırıldı; saatler arasında gerçek zaman boşluğu varsa pencere o boşluğu aşmadı. Çekiliş numarasında kopukluk olan pencereler de atlandı.
- Hedeflerin birbiriyle örtüşmesine karşı ek **12'şer çekilişlik, örtüşmeyen hedef saatler** kullanıldı. Bu ikinci analizde hafıza yine 48 çekiliştir; her blokta sadece 48'in ardından gelen 12 hedef çekiliş puanlanır.

## Veri kontrolü

- **16.005** geçerli 20/80 çekiliş kaydı; **2** bozuk kayıt analiz dışında: #50924 (19 sayı), #50936 (21 sayı/tekrarlı 79). Bu noktalar kesinti olarak ele alındı.
- Son kayıt: **#62014, 13.10.2026 19:57**. Bu tarihten sonrasına ilişkin canlı sonuç veya kupon isabeti varmış gibi gösterilmemelidir.
- **11.502** adet birer çekiliş kayan, sonraki 12 çekilişi olan hedef; daha muhafazakâr ve örtüşmeyen değerlendirmede **1.021** hedef saat.
- Eğitim dönemi: 01.08–12.09 (596 örtüşmeyen hedef); seçim/doğrulama dönemi 13.09–27.09 (210 hedef); son raporlama 28.09–13.10 (215 hedef). Son dönem de geçmişteki başka V sürümlerinde incelenmiş olduğundan **tam bağımsız, dokunulmamış bir test sayılmamalıdır**.

## Denenen sayı sıralama yöntemleri

Rastgele kontrol, son 48'de en sıcak 10, son 12'de en sıcak 10, son 24'te en sıcak 10, son 48'de en soğuk 10, 12'ye karşı önceki 36 trendi, son 24'e karşı ilk 24 trendi, yakın çekilişlere üstel ağırlık, 48+12 ortak sıcaklık. Tüm seçimler **hedefteki hiçbir sonucu kullanmadan** yapıldı. Sıralama eşitliğinde küçük sayı önce gelir. Rastgele kontrol sabit çekiliş numarası kaynaklı deterministik pseudo-rastgele sıralamadır.

## Matematiksel beklenti

Adil bağımsız 20/80 modelinde belirli bir sayının 12 çekilişte görülme sayısı Binom(12, %25) olur. Tekil sayı için P(4+) **%35,1221**, P(5+) **%15,7644**, P(6+) **%5,4402**. Önceden seçilmiş **10 sayıda** ortalama 4+ **3,512**, 5+ **1,576**, 6+ **0,544**. Tüm **80 sayıda** ortalama sırasıyla **28,10**, **12,61**, **4,35** sayı. Bu ortalamalar gelecekteki sayıların kimliğini söylemez.

## Örtüşmeyen hedef saatlerde gözlem (10 seçili sayı başına ortalama)

Doğrulama döneminde (210 hedef) geçmişe dayalı yöntemler arasında **48'de en soğuk 10 sayı**, 4+ ölçütünde en yüksek sonucu verdi: **3,629** (rastgele karşılaştırma **3,676**). Bu yöntem son döneme taşındı.

| Son test: 28 Eyl–13 Eki, 215 hedef | 4+ | 5+ | 6+ |
|---|---:|---:|---:|
| **Önceki 48'de en soğuk 10 sayı** | **3,405** | **1,642** | **0,633** |
| Aynı hedeflerde rastgele 10 sayı | 3,595 | 1,605 | 0,595 |
| Adil 20/80 teorik beklenti | 3,512 | 1,576 | 0,544 |
| Soğuk yöntem − rastgele fark | **−0,191** | **+0,037** | **+0,037** |
| Gün düzeyinde bootstrap, keşifsel %95 fark aralığı | [−0,423; +0,053] | [−0,170; +0,241] | [−0,058; +0,131] |

Aralıklar 16 hedef gününün ikameli örneklemesinden (5.000 tekrar), aynı hedefte eşleştirilmiş yöntem farklarından hesaplandı. Her üç aralıkta da sıfır vardır. Geçmişte çoklu yöntem ve eşik denenmiş olması nedeniyle bunlar üstünlük kanıtı değildir.

### Örtüşen tüm 11.502 kayan pencerede (yalnız betimleme)

- En soğuk 10: 4+ **3,564**, 5+ **1,611**, 6+ **0,560**.
- Rastgele 10: 4+ **3,499**, 5+ **1,551**, 6+ **0,545**.
- Çok sayıda komşu hedef aynı gerçek çekilişleri paylaştığından **11.502 bağımsız deneme yoktur**. Bu büyük toplamdaki küçük artışı bağımsız tahmin kanıtı saymak hatalıdır.

## Karar

**48 çekiliş hafızası ile beşinci saatte 4+, 5+, 6+ olacak tekil sayıları rastgeleden güvenilir biçimde ayırt edebildiğimiz henüz gösterilmedi.** Özellikle 4+ için son dönem karşılaştırmasında geçmişte en soğuk yöntem rastgele kontrolün gerisinde kaldı. 5+/6+ için görünen küçük olumlu farklar belirsizlik sınırları ve çoklu sınamalar içinde kalıyor.

Sonraki aşama: Yeni çekilişler Streamlit'ten GitHub'a geldikçe, kuralı değiştirmeden **48 çekiliş sonrasında sıralamayı zaman damgalı ve hedef öncesi kaydetmek**, sonraki 12 sonuç tamamlanınca puanlamak. Veri geriden yükleniyorsa bunu 'ileri test' diye etiketlememek. Kupon satın alma kararı bu araştırmayla gerekçelendirilmemelidir.
