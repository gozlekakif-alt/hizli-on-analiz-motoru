# V14 — 217 Çekilişin Zaman Kimliği ve 80×80 Sayı Geçiş Ağı

**Araştırma amacı:** Bir çekilişte görülen 20 sayı ile bir sonraki 20 sayı arasında gerçekten tekrarlanabilir bir *sayı geçiş düzeni* var mı? Günde 217 çekilişin saatleri, ilk/son 6 çekilişleri ve 2, 3, 6, 12 çekilişlik gecikmeler aynı RNG davranışından sapıyor mu?

## 1. Sayıların yer değiştirmesi tam olarak ne anlama geliyor?

Resmî sonuçlar, topların makineden çıkış sırasını değil **20 farklı sayıdan oluşan kümesini** verir. Bu nedenle ayrılan 15 sayı ile gelen 15 sayı arasındaki 225 olası A→B ilişkisi herhangi bir fiziksel ya da nedensel bire-bir eşleştirme oluşturmaz.

V14 iki olayı ayrı inceler:

- **A çıktıktan sonra B'nin görünmesi:** Kaynak A geçmiş çekilişte mevcut, B kaynak çekilişte yokken sonraki çekilişte B çıktı mı? Bu olay **önceden** sorgulanabilir. Adil bağımsız çekilişte B'nin sonraki çekilişte görünme olasılığı **%25**.
- **A'nın ayrıldığı kesinleşince B'nin görünmesi:** Kaynak A bir önceki çekilişte mevcut ama yeni çekilişte artık yok; daha önce mevcut olmayan B geldi mi? Bu ilişki **çekilişten sonra** ölçülebilir, önceden A'nın ayrıldığı bilinemez. Adil bağımsız çekilişte A'nın ayrıldığı koşulunda B'nin gelme olasılığı **20/79 ≈ %25,316**.

Bir çekilişten diğerine ortalama **5 sayı aynen kalır, 15 sayı ayrılır ve 15 farklı sayı girer**. Bunların tek bir gözlemlenmiş örnekte değişmesi beklenir.

## 2. Zaman mimarisi

- Bir günün 217 takvim çekiliş pozisyonunun **her biri** ayrı kimliklidir.
- 00:02–01:02 arası 13 çekiliş vardır. 01:02→07:02 geçişi, zaman olarak altı saattir; algoritma bunu ayrı kayıtlı pozisyonlarda inceler, beş dakika aralık olduğunu varsaymaz.
- 07:02–23:57 arası 17 saat × 12 çekiliş.
- Gün dönemleri: Gece / Sabah / Öğlen / Akşam.
- Bir saatin 1–6 ve 7–12. çekilişleri birbirinden ayrı tutulur.
- Her saat ve her pozisyon için ortalama tekrar, ayrılan ve yeni gelen 20 sayı raporlanır.
- O hedefin gün içindeki önceki çekiliş kaydı yoksa A→B ilişkisi uydurulmaz. Bir günün ilk çekilişi için aynı güne ait önceki çekiliş bulunmadığından iki çekiliş arasında geçiş testi yoktur.

## 3. 80 sayılık ağ

80 düğümden oluşan 6.400 hücreli A→B ağında 1, 2, 3, 6 ve 12 çekiliş gecikmesi ayrı ölçülür. A≠B şartıyla +1 için 6.320 olası çift vardır; diğer gecikmelerde kendini tekrar eden A→A ilişkisi de incelenebilir.

**Bütün çiftlere aynı çekiliş öncesi kural uygulanır:** B bir önceki çekilişte yoktur; A geçmiş ilgili gecikmeli çekilişte görünmüştür. Eğitim günlerinde bu koşulun kaç kez yaşandığı ve B'nin sonraki çekilişte kaç kez geldiği sayılır. **Sadece gelen B'leri saymak değil, gelmeyen B'leri de paydaya eklemek zorunludur.**

Tüm tahmini oranlar %25'e doğru ağırlıklı şekilde yakınsatılır. Eğitimde güçlü görünen 35 ilişki ayrılır ve ayrı test günlerinde doğru olup olmadıkları incelenir. Bu 35 çift **6.320 aday içinden seçilmiş olduğundan**, çoklu hipotez araması ve yanlış pozitif uyarısı uygulanır.

## 4. Kupon motoru

Tahmin, gerçek hedef çekilişinin 20 sayısı görülmeden oluşturulur:

- **V14 bir-adım ağ:** Son çekilişteki sayıların +1 ilişkilerinden, önceki 20'den 5 taşıyan + daha önce gelmeyen 15 öneri.
- **V14 çok-adım ağ:** +1/+2/+3/+6/+12 gecikme ilişkileri ağırlıklı.
- **V13 sıcaklık:** İlk 36 günle eğitilen soğuk/ılık/sıcak 80 sayı durumundan 20 öneri.
- **V12 ağ-kule:** Önceki 12 gerçek çekilişi eksiksiz bilinen saat 7–12 hedeflerinde 20 öneri.
- **Rastgele20:** Aynı hedefe deterministik kontrollü 20 rastgele sayı.

5/15 ayrımı **matematiksel ortalamadan** gelir; her çekilişte tam 5 aynı sayı geleceği iddiası değildir. Alternatifleri kıyaslayabilmek için sabit bir başlangıç kuralıdır.

## 5. Ölçüm ve geleceğe bakmama

- İlk 36 takvim günü **eğitim**; izleyen 37 gün **test**.
- Tahminlerde sadece önceki çekilişler ve önceki günlerde dondurulmuş kalibrasyon kullanılır.
- Test günü sonuçları modele geri öğretilmez. Bütün başarısız hedefler raporda kalır.
- 20/20, en yüksek ve ortalama isabet, 0..20 dağılımı, rastgeleye göre aynı günde eşleşen hedeflerin farkları.
- Günlük gruplama bazlı yaklaşık güven aralığı raporlanır; çoklu test farkı nedeniyle **başarı ispatı olarak sunulmaz**.
- 217 pozisyonun her biri, saat grupları ve bir saat içindeki ilk/son altı ayrı CSV.

## 6. Uygulama, veri ve test

- \`v14_gecis_agi.py\`: standart Python ile ağ ve geçmiş-için-ileri test.
- \`v14_selftest.py\`: yapay hedef veri sızması testi ve gerçek 73 günlük sıralı test.
- \`v10_app.py\`: V10'daki **🔄 V14 Geçiş Ağı** sekmesi; tek gerçek iki çekilişi inceleme, test ve canlı önizleme.
- \`.github/workflows/v10-check.yml\`: V14 modül ve arayüz testlerini otomatik doğrular.

V9 \`app.py\`, ana \`veri.txt\`, V10/V11/V12/V13 kodları, mevcut aileler ve kuponlar değiştirilmez. Hedef %25'ten anlamlı ve ileri tarihte tekrarlanabilir bir sapma bulmak; bulunamıyorsa bunu açıkça söylemektir.

**İstatistiksel sınır:** Bir zaman sırası veya geçiş korelasyonunun betimlenebilir olması, adil ve bağımsız RNG'nin tahmin edilebilir olduğu anlamına gelmez.
