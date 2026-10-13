# V25 — Aile DNA, yaşam evreleri, eşlikçiler ve gerçek 10'lu kupon testi

**Durum:** GitHub Actions tam başarılı, 72 gün / 15.624 çekiliş / 1.296 ayrı 12-çekilişlik saat işlendi. [Doğrulanmış çalışma](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38477600266).

## Araştırma yöntemi

- 1 Ağustos–12 Ekim 2026 arasındaki 72 tam gün; `veri.txt` verisinin bu sürümü üzerinden. Eksik/bozuk 23 Ağustos kayıtları ve henüz tamamlanmamış 13 Ekim tam güne alınmaz. 01:02 tek çekilişi geçmişe eklenir; 01:02–07:02 arasında hayali çekiliş oluşturulmaz.
- Saatlik gerçek 12 çekilişin **ilk 6'sı görünürken** 2/3/4'lü ailelerin o güne kadarki `İlk` (bir kez), `İki` (tam iki kez), `Üç+` (üç ve üzeri) durumları hesaplanır. Aile seçmek için **henüz gerçekleşmeyen son 6'nın sonuçları kullanılmaz**.
- Her aile boyutu/evrede `Yakın` (en son görünen), `Sıcak` (geçmişte sıcak üyeler) ve **aynı aday havuzundan rastgele aile** karşılaştırılır. Eşlikçiler, aileyle geçmişte gerçekten birlikte görülen sayılardan seçilir; aynı sayıdaki rastgele eşlikçilerle karşılaştırılır.
- 5–10'lu büyük aileler için mevcut `v10_aileler.csv` içindeki **1.131 katalog ailesi** ayrıca aktif aile sinyali olarak taranır. Bütün olası 5–10'lu kombinasyonların ilk tekli görünüşlerini bellekte tutma iddiası yoktur.
- Aile sinyalinden `AileDNA` 10'lu kuponu; ilk6 sayılarından `Sıcak10`, `Soğuk10`, **80 sayıdan rastgele 10** ve **ilk6 görülen sayı havuzundan rastgele 10** kupon oluşturulur. Beş kupon da **aynı sonraki altı çekilişte** değerlendirilir. Her hedefte 0/10’dan 10/10’a dağılım ve 5+/6+/7+/8+ sayılır.
- İlk 36 gün model seçimi; son 36 gün **model seçiminden ayrılmış test**. 36 günün 648 saati × 6 = **3.888 hedef çekiliş**. İlk36'da seçilen tek kupon yöntemi **Soğuk10**; test dönemi sonuçlarına bakarak bu seçimi değiştirmedik.

## Son 36 günde gerçek 10'lu isabetleri

| Kupon yöntemi | Hedef çekiliş | Ortalama isabet/10 | 5+ çekiliş | 6+ çekiliş | 7+ çekiliş | 8+ çekiliş | 10/10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **AileDNA** | 3.888 | **2,51312** | 257 | 49 | 7 | 0 | 0 |
| Sıcak10 | 3.888 | 2,51286 | 257 | 56 | 7 | 1 | 0 |
| Soğuk10 (**eğitim galibi**) | 3.888 | 2,51235 | 253 | 47 | 7 | 0 | 0 |
| Rastgele10 | 3.888 | 2,50051 | 253 | 54 | 10 | 1 | 0 |
| İlk6Havuz10 | 3.888 | 2,48611 | 258 | 53 | 7 | 0 | 0 |

**İstatistiksel değerlendirme:** 10 sayı çekilişi için teorik ortalama her çekilişte 2,5 isabettir. AileDNA–Rastgele10 farkı +0,01260/10 isabet; **36 gün kümesi üzerinden yaklaşık %95 güven aralığı [-0,04321, +0,06842]**. Eğitimde seçilen Soğuk10–Rastgele10 farkı +0,01183/10; %95 GA **[-0,05535, +0,07901]**. İki aralık da sıfırı içerir: **güvenilir bir RNG tahmin üstünlüğü saptanmadı**. Rastgele10 kuponu, AileDNA'dan daha fazla 6+, 7+ ve 8+ örneği yakaladı; yani tek bir ölçüden zafer çıkarmamalıyız.

### Aile evrelerinin tam devamı — son 36 gün, Yakın seçimi

| Aile | Gün içi evre | Seçilen aile sayısı | Son6 tam aile görünüşü | RNG beklenen | Rastgele eş aile sonucu |
|---|---|---:|---:|---:|---:|
| 2'li | İlk | 361 | 139 | 130,23 | 130 |
| 2'li | İki | 480 | 170 | 173,16 | 176 |
| 2'li | Üç+ | 648 | 243 | 233,77 | 230 |
| 3'lü | İlk | 648 | 58 | 53,95 | 57 |
| 3'lü | İki | 648 | 48 | 53,95 | 40 |
| 3'lü | Üç+ | 646 | 50 | 53,78 | 52 |
| 4'lü | İlk | 648 | 12 | 11,91 | 13 |
| 4'lü | İki | 648 | 12 | 11,91 | 20 |
| 4'lü | Üç+ | 623 | 11 | 11,45 | 11 |

Büyük sayıların ortak çekirdeklere ait iç içe aileler oluşturduğu unutulmamalıdır. Bunlar **bağımsız bahis** ya da kazanma vaatleri değildir. Fazla seçenek taramanın tesadüfen güçlü görünen kombinasyonlar üretmesi mümkündür.

## Doğrulama ve çıktılar

- [V25 algoritması](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v25_aile_dna_kupon.py)
- [V25 doğrulama testleri](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v25_selftest.py) — aile doğum/ikinci/üçüncü, saat 01:02→07:02, **son6'ya bakmadan donmuş seçim**, kupon isabet toplamı.
- [V25 Streamlit kullanıcı ekranı](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/blob/main/v25_family_app.py); `v10_app.py` içindeki **🧬 V25 Aile DNA Kupon** sekmesi.
- [Başarılı otomatik GitHub çalışması](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38477600266) ve [72 gün ZIP artifact](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38477600266/artifacts/11855830433).
- ZIP içerikleri: `ozet.json`, `aile_evre_ilk_ikinci_ucuncu_ilk6_son6.csv`, `kayitli_1131_buyuk_aile_ilk6_son6.csv`, `gercek_10lu_kuponlar_0dan10a_isabet.csv`, `ilk36_model_secimi.csv`, `aile_olay_isabet_ozetleri.csv`, `kupon_0_10_son36_istatistik.csv`, `test36_gunluk_karsilastirma_guven_araliklari.csv`.

**Sonuç:** Aileleri zaman evreleri ve beraberinde değişen eşlikçilerle izleyerek kupon üreten bir sistem kurulmuştur. Ancak **son 36 gün veri üzerinde ne aile evrelerinin ne de 10'lu kupon motorunun güvenilir rastgele üstünlüğü** bulunmamıştır. Veriye göre yeni kural değişiklikleri ayrıca, daha yeni hiç görülmemiş günlerde sınanmalıdır. **`veri.txt` ve V9–V24 geçmiş motorlarına dokunulmadı.**
