# V37 — ORTAK YAŞAM HAFIZALI ÇOK UZMANLI DAVRANIŞ KLONU
## Değiştirilmeyecek mimari şartnamesi · 14 Ekim 2026

**Durum: MİMARİ / UYGULAMA KODU DEĞİL.** Mevcut \`v10_app.py\`, \`v36_rng_davranis_klonu.py\` ve V9–V36 çalışan sürümlerine dokunulmaz. Bu belge bir sonraki mühendislik aşamasının kabul sözleşmesidir.

### 0. Amaç ve sınır

Amaç gelecek 20 sayıyı hemen kuponlaştırmak değildir. Önce Hızlı On'un 1–80 sayılarının her birini çekiliş çekiliş yaşamı olan **tek ortak kronolojik kütükte** saklamak; sıcaklık, yön, bekleme, görünme, aile, bant, ritim ve döngü uzmanlarının aynı ortak yaşam kütüğünden **bağımsız ve ayrıntılı dallarla** durumlarını oluşturmasını sağlamak; uzmanların belirli kanıtlara dayanan **olay mesajlarıyla diyalog** kurmasını; aynı geçmiş üzerinden ayrı bir **davranış emülatörü** çalıştırılıp gerçeğe benzerliğin ölçülmesini sağlamaktır.

**Bilinmeyen RNG tohumu/algoritması çözüldü demek değildir.** Bir simülasyonun bekleme, tekrar, bant ve aile dağılımında gerçeğe benzemesi o simülasyonun gelecek 20 sayıyı bileceği anlamına gelmez. Bu fark ayrı testlerle ölçülecek.

### 1. Hiç kaybolmayan ortak sayı hafızası

- **Gerçek çekiliş defteri**: \`draw_id\` (resmi çekiliş numarası), \`day\`, \`position:1..217\`, \`timestamp_TR\`, 20 benzersiz sayı için 80-bit mask, onun 60 sayılık tam tümleyeni, kaynak/hazne karması. Değişmez; düzeltme varsa ayrı versiyon.
- **Yaşam izi**: Her sayının çekilişte 1/0 görülme durumu. Örnek: \`80 sayı × 15.624 çekiliş=1.249.920 temel gözlem\`; 80 kopya tabloda değil tek kaynaktan üretilebilir.
- **Çoklu saat**: \`global_real_step\`, \`day_position\`, \`hour_draw_index\` (01:02 tek çekiliş ayrıca), \`consecutive_segment\`, \`since_last_hit_global\`, \`since_last_hit_today\`; bu farklı sayaçlar ASLA karıştırılmaz.
- **Tam günlük ilk çizgi**: 00:02 pozisyon 1; 01:02 pozisyon 13; 07:02 pozisyon 14; 23:57 pozisyon 217. 13→14 arasına yokluk çekilişi uydurulmaz.
- **Eksik gerçek sıra**: \`UNKNOWN/NOT_RECORDED\`, asla \`0=çıkmadı\` sayılmaz. Bağlamı tamsa gerçek saat boşluğu \`SCHEDULED_BREAK\` ve kesilmez.
- **İki hafıza seviyesi**: (A) Günlük yeniden başlayan 00:02 hayata özel sayaçlar, (B) günler arası **silinmeyen** sayı ömrü, tekrar sayısı, 1/0 tarihçesi, aile yaşamı ve ısı belleği. Araştırmada iki seviye yan yana gösterilir.
- **Anlık sayı kartı**: \`(day,pos,num,prev_snapshot,new_snapshot,episode_ids,motor_memberships,signals)\`. Önceki kart değiştirilemez; yeni çekilişte yeni kart eklenir.

### 2. Motor ve kılcal uzman sözleşmesi

Her **uzman dal** bu alanlarla tanımlanır:

\`\`\`yaml
motor_id: HEAT.COLD_TO_WARM.PERSISTENT
version: 1
reads: [BALL_LIFE, HEAT_SEATS, DIRECTION, BANDS]
event_inputs: [HEAT_CHANGED, WAIT_ENDED]
state: {type: per_number, storage: append_only}
outputs: [RESERVOIR_ENTER, RESERVOIR_LEAVE, TRANSITION_EPISODE]
parameters: {window: 11, lower_threshold: ..., upper_threshold: ...}
lineage: {last_real_draw_id: ..., source_event_ids: [...]}
quality: {coverage: ..., tested_period: ..., rng_control: ...}
\`\`\`

- Bir uzman yalnız ortak hafızanın **geçerli adımına kadar** okur; başka motorun bulduğu "gelecekteki sonucu" karakter girdisi yapamaz.
- Motorun **kendi haznesi** vardır: \`members(t)\`, \`members(t-1)\`, \`entered\`, \`left\`, \`remained\`, \`episode_birth\`, \`episode_death\`, \`last_transition\`.
- Aynı sayının birden fazla farklı motor haznesinde bulunması normaldir; tek bir uzman motorunun birbirini dışlayan alt sıcaklık koltuklarında sayı **tam birinde** olmalıdır.
- Her dallanma için olayın **sayı üyeleri, aile üyeleri, süre, pencere, geçmiş delil ve olay numarası** korunur.
- Motorun "6'lı" olmasının yorumu parametrik değildir: \`11 çekilişte 6 kez çıkma\` ile \`6 gerçek çekiliştir yokluk\` **farklı uzman olay türleridir**.

### 3. Çekiliş başına deterministik olay işleme sırası

\`\`\`text
D_t resmi çekiliş maskesi alındı ve doğrulandı
    ├─ 0. Kimlik, sıra, boşluk, mükerrer kayıt doğrulaması
    ├─ 1. Ortak 80 sayı kartı (ham yeni 1/0, eski kart ref)
    ├─ 2. Yaşam hafızası: günlük+ömürlük sayaç/pencere güncelle
    ├─ 3. Bağımsız uzman dallar: ısı, yön, bekleme, aile, ... olayları üret
    ├─ 4. Her haznenin önceki/giren/kalan/çıkan üyelerini hesapla
    ├─ 5. Olay diyalog merkezi: kanıt bağlantılarını eşleştir
    ├─ 6. Gerçek dağılım ve klon dağılımının aynı t için farklarını ölç
    ├─ 7. t-1'de önceden dondurulmuş hedefler varsa t gerçek sonucuyla puanla
    ├─ 8. t görüldükten SONRA uzman özetlerini/akordu güncelle
    ├─ 9. Append-only olaylar; snapshot, checkpoint ve rapor yerleşimi yaz
    └─ 10. Sonraki t+1 için bekle
\`\`\`

**Zaman kuralı:** Klon D_t sonucundan önce üretilmeli; D_t bilindikten sonra oluşturulan özel durum analizi \`analysis_at_t\` adıyla saklanır, geçmişte tutulan "dondurulmuş öngörü" diye raporlanamaz. Üretim, gözlem, öğrenme ve denetim izleri farklı tipte tutulur.

### 4. Olay diyalog merkezi: "Motorlar konuşuyor" ne demek?

Uzmanlar serbest metin sohbet etmez, **denetlenebilir olay mesajları** yayımlar:

\`\`\`json
{
  "event_id": "2026-10-14:p036:HEAT.COLD_TO_WARM:n23",
  "version": 1,
  "scope": {"day":"2026-10-14","position":36,"global_step":123456},
  "source_motor":"HEAT.COLD_TO_WARM",
  "type":"HEAT_STAGE_CHANGED",
  "numbers":[23],
  "family_id":null,
  "before":{"heat":"SOGUK","direction":"STABLE"},
  "after":{"heat":"ORTA","direction":"UP"},
  "evidence":{"source_draw_ids":[111,112],"window":12},
  "parent_event_ids":[],
  "observed_at_source_step":36,
  "eligible_for_future_use_after_step":36
}
\`\`\`

Diyalog alt sisteminin görevleri:

1. **Eşzamanlılık**: aynı \`(day,pos,num)\` üzerinde ısı ↑, bekleme sonu, V32 döngüye ilk geliş ve aile parçalı gelişi aynı anda mı?
2. **Sıralama/bağlantı**: \`WAIT.8 -> REACTIVATION.1 -> HEAT.RISING\`; hangi dal önce, kaç gerçek çekiliş arayla, aynı sayı mı?
3. **Aileye yansıma**: beklemesi biten 23, \`19-23-30-48\` ailesinin tamamlanma yolunda kaçıncı üye?
4. **Çapraz hazne**: bir bandın yoğunlaşması, diğer bandın boşalması ile anlık ortak sayı hareketi oluşturdu mu?
5. **Yolculuk zinciri**: \`episode_id\` ve \`parent_event_ids\` ile yolun geçmişi ileriye dönük kopyalanmadan izlenir.
6. **Olay düzeyi karşılaştırma**: klonda da aynı motif hangi hızda, ne zaman ve hangi bant/ısı bileşiminde oluşuyor?

Diyalog **olayları birbirine bağlar, kanıtlanmamış nedensellik ilan etmez**. Bir motorda sayı "çıkacak" mesajı zorunlu değildir; ana çıktı **açıklanabilir ortak olay**dır.

### 5. Klonun iki ayrı defteri ve karşılaştırması

1. \`REAL_OBSERVATION\`: yalnız gözlenmiş resmi çekilişlerden oluşan hat.
2. \`SYNTHETIC_AUTONOMOUS\`: kendi 20/80 çekilişini üretir, kendi 1/0 yaşam, aile ve ısı motorlarını ilerletir; gerçek geleceğe **erişmez**.
3. \`SYNTHETIC_CONDITIONED\`: **t−1 gerçek geçmişi** üzerinden t için üretilmiş ayrı koşullu örnek; arşivde gerçek t sonucu görüldükten sonra puanlanır. Bu bir "aynı t motor durumu" özetinden ayrıdır.
4. \`IID_20_OF_80_BASELINE\`: her çekilişte eşit olasılıkla geri koymasız 20 benzersiz sayı referansı.
5. Aynı ölçüler: 20/60 içeriği, 11/24/217 yoğunluk dağılımı, altı ısı koltuğu, yön/hız, bekleme süresi, geçiş matrisleri, bant sayısı, ikili/üçlü/dörtlü aile motifleri, sessiz dönem ve parçalı tamamlama hızları, V32 döngü ömürleri.
6. Sadece **benzer ortalamalara** bakmak yetmez: dağılım kuyrukları, aynı gün içi otokorelasyon, ardışık istisna örüntüleri, 217'lik günlük yolculuk ve yeni dönemde uyum ayrı ölçülür.
7. Klon sürekli akort olabilir ama ayrı bir \`FROZEN_CONTROL\` kolu tutularak "değişken akort" ve "sabitleyip sonraki günlerde kontrol" etkileri karıştırılmaz.
8. **RNG algoritması çözüldü** veya **20'nin kimliği bulunuyor** iddiası ancak bağımsız gelecekte ölçülen özel üstünlük varsa tartışılır; dağılım klonlaması tek başına bunu göstermez.

### 6. Veri depolama / mobil Streamlit sınırları

**Öneri:** GitHub \`veri.txt\` gerçek kaynağın ana yüzüdür; yanına ayrı \`v37/\` paketinde **SQLite append-only olay veritabanı** ve üretilen parçalı Parquet/CSV ZIP raporları. SQLite tekil kullanıcı/tek işlemli Streamlit/Actions çalışmasında pratik; **çoklu işçi eşzamanlı yazım için** farklı kilit/işlem koordinasyonu gerekir.

Temel tablolar (tam şema ayrı dosyada):

- \`draw_ledger\`, \`ball_life\`, \`ball_step_state\`
- \`motor_registry\`, \`motor_state\`, \`reservoir_membership_events\`
- \`family_identity\`, \`family_step_state\`, \`family_lifecycle_events\`
- \`event_bus\`, \`event_links\`, \`motor_dialogue\`
- \`clone_draws\`, \`clone_motor_state\`, \`comparisons\`
- \`calibration_snapshots\`, \`frozen_forecasts\`, \`forecast_scores\`
- \`ingestion_checkpoint\`, \`data_quality_alerts\`, \`study_runs\`

**İdempotent uygulama**: \`draw_id\` + \`source_checksum\` + \`motor_id/version\` + \`event_type\` + \`event_key\` benzersiz olur. Aynı çekiliş tekrar yüklenirse iki kere olay üretilmez. Çekiliş değişmişse önceki raporlar **sürüm** olarak saklanır, sessizce üstüne yazılmaz.

**Checkpoint**: \`source_prefix_sha256\`, \`last_draw_id\`, \`last_day/pos\`, \`engine_versions\`, \`state_blob_checksum\`, \`SQLite schema version\`; anahtar uyuşuyorsa **yalnız yeni çekilişlerden** devam. Parametre değişirse hangi motorda hangi tarihten yeniden hesap gerektiği otomatik işaretlenir. Böylece 72 gün her seferinde baştan yürütülmez.

**Kalıcılık net sınırı:** GitHub Actions veya Streamlit Cloud diski kalıcı veritabanı gibi varsayılmaz. GitHub’a kalıcı checkpoint yüklemek ayrıca, çakışma kontrolü yapan onaylı yazma hattı gerektirir. İlk etapta repo veri.txt + tekrar üretilebilir tek ZIP güvenlidir.

### 7. "217 çekilişin her biri" rapor bütünlüğü

- Her gün/hafıza için 217 çekiliş satırı; kısmi gün ise yalnız gerçekten bilinen pozisyonlar; eksikler ayrı hata raporu.
- Her \`(çekiliş, sayı)\` için 80 yaşam kartı; 15.624 tam çekiliş varsa **1.249.920** kaynak sayı-adım kaydı.
- \`(çekiliş, motor, hazne)\` giriş-çıkış/tutunma ve önceki durum; hiçbir motor bir önceki adımı kaybetmez.
- \`(çekiliş, aile)\` tam/parçalı/kapanma/sessizlik/yeniden birleşme; aile \`members\` sabit, \`lifecycle\` değişkendir.
- \`(çekiliş, ilişki)\` motorlar arası olay zinciri kaydı; \`source_event_ids\` olmadan bağlantı üretilmez.
- Aynı çekilişte 80 sayılık **GERÇEK** ve **KLON** havuzlarının ikisi de en az 20/60 kontrolünü sağlamalı.

### 8. Tesisin kabul testleri

1. \`D_t\` oku → 80 sayı kartı; 20 tane 1, 60 tane 0; toplam her zaman 80.
2. Aynı veri iki kere uygulandığında çekiliş/olay/üyelik sayısı değişmez.
3. \`D_t\` sonrasındaki bütün girdileri değiştirip tekrar çalıştırınca \`t\` öncesindeki bütün olay ID'leri ve t'de dondurulmuş durum değişmez.
4. Gün 1..217 sıra; pos13→14 gerçek geçiş, sahte çekiliş yok; kayıp pozisyon unknown.
5. Isı koltuklarında 13+13+14+14+13+13=80 (rütbeye dayalı model ise); mutlak sıcaklık ayrı raporlanır.
6. Her motor üyeliğinde \`old - left + entered = new\`; aynı sayı aynı dışlayıcı alt sınıfta iki kez bulunamaz.
7. Her ailede 2+2 parçalı geliş ile aynı çekilişte tam 4/4 geliş farklı olay ve farklı zaman damgasına sahip.
8. Aile 2+1+1 yolculuğu, üyelerin ara çekilişlerde sahnede bulunup bulunmadığı kaydıyla yeniden oynatılabilir.
9. Gerçek geçmişi değişmeden sentetik RNG seed farklıysa yalnız klon kolu değişir; gerçek motor olayları aynen kalır.
10. Eğitim/test dönemi geçmişten geleceğe; raporlar yalnız \`t\` anında mevcut veriyle izlenebilir.
11. Her yeni \`veri.txt\` eklemesinden sonra checkpoint doğrulanır; yeni çekilişlerden devam eden sonuç ile sıfırdan tam yeniden oynatma **aynı** raporu üretir.
12. Streamlit tek düğme bütün uzmanları koşar; büyük veri artımlı işlenir; bellek dolması veya mobil oturum kopması kalıcı kaydı bozmaz.
13. Özerk klonun bekleme/ısı/aile istatistikleri gerçek RNG ve bağımsız 20/80 baz çizgisiyle yan yana raporlanır.
14. **Motor tanımlanmadan, kayıt oluşturulmadan "çalışıyor" yazılmaz.** Başarılı bir GitHub Actions koşusu ve indirilebilir tek ZIP asgari teslim kriteridir.

### 9. İnşa sırası (henüz çalıştırılmadı)

**Aşama A — Kök:** Ham çizelge normalizasyonu, ortak ömür defteri, olay anahtarları, SQLite şema, idempotent replay.  
**Aşama B — Tekil uzmanlar:** 20/60, 6 ısı ve yönün en küçük dalları, 6–11+ bekleme, 11 bit imzalar, bant ve 217 gün saati.  
**Aşama C — Aile dalları:** 2/3/4 tam ve parçalı geliş, 1+3/2+2/3+1, sessiz bekleme, gecikmeli tamamlama; aile epizotları.  
**Aşama D — Diyalog:** Motor olaylarının delilli birleşimi, sıra zincirleri ve örtüşme/ayrışma motifleri.  
**Aşama E — Özerk klon ve karşılaştırma:** Gerçek/klon/iid, dağılım benzerliği, kuyruk, saat, gün karakteri.  
**Aşama F — Tek düğme:** Streamlit yeni sekme, ilerleme ve checkpoint doğrulaması, tek ZIP, kapsam/uyarı/dönem raporu.  

**Bu belge bir çalışır motor veya sonuç raporu değildir; kod uygulanıp test edilene kadar V36 canlı kalır.**
