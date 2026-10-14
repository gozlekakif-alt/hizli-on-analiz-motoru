# V44 — Ana Beyin, 19 Uzman, Kapalı Eleme ve 72 Günlük Bağımsız Test

**Durum:** GitHub otomatik 72 gün testi BAŞARILI (14 Ekim 2026). Mevcut `veri.txt` ve eski V3–V43 motorları değişmedi.

**Test:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38635465472

**Tek ZIP (9,1 MB):** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38635465472/artifacts/11926949242

## Tasarım ve dürüst test kuralı

- **15.624 gerçek çekiliş** × 20 sayı = 72 tam gün.
- **İlk 18 gün:** öğrenme / kurulum.
- **Sonraki 18 gün:** 19 uzmanın daha önce belirlenmiş doğrulama filtresinden geçirilmesi.
- **Son 36 gün:** 7.812 hedef çekiliş; **uzman eleme sonucu test başlamadan sabitlenir**.
- Her çekilişte 80 sayı adayının durumu t anından **önceki** sonuçlarla hesaplanır. 20 sayılık listeler t hedefi açılmadan dondurulur, sonra gerçek çıkan20 karşılaştırılır ve ancak bundan sonra çevrimsel güncelleme yapılır.
- **Adaylar:** V39'un gerçekten 20 sayı üreten 8 uzmanı; V41'in 5 yön modeli; V42/V43'ten uyarlanmış 5 kotaya/banta/20–60 geçişine dayalı kimlik yöntemi; 1 önceden sabit konsensüs. V38'in 207 karakter sütunu 207 ayrı tahmin modeli olarak gösterilmez. V3–V43'ün tamamı birebir yeni motor olarak bağlanmış değildir.
- **Eleme:** En az +0,10/20 validasyon kazanımı, validasyonun iki yarısında ve özel 7.–12. çekilişlerde pozitiflik; 19 denemelik grup için güne göre maksimum t-istatistiği çoklu test p < 0,025. Aynı listeleri tekrarlayan geçerli uzmanlar ayrıca elenir. Sinyal geçmezse **ana beyin rastgele kontrol listesi üretir**, başarılı kupon olduğunu iddia etmez.

## Gerçek sonuçlar

**Validasyonun ilk 4 adayı** bile kapıyı geçemedi:
- V39 Aile Bağlantısı: **5,042499/20**; çoklu test düzeltmeli p=0,662384.
- V39 Yön İvme: **5,033538/20**; düzeltilmiş p=0,831549.
- V39 Ortak Karakter: **5,024322/20**; düzeltilmiş p=0,892220.
- V42 Kalibre 5 Kota: **5,024066/20**; düzeltilmiş p=0,950036.

**Kabul edilen uzman sayısı: 0/19.** Bu sonuç, bütün olası sinyallerin faydasızlığının kanıtı değil; mevcut adayların önceden belirlenen güvenilir üstünlük eşiğini karşılayamadığı anlamına gelir.

### Son 36 gün / 7.812 çekiliş

| Önceden dondurulmuş model | Ortalama isabet /20 | En yüksek | 10+ isabet | 16+ |
|---|---:|---:|---:|---:|
| V44 Ana Beyin (uzman geçmediği için RNG kontrolü) | **4,98297** | 12 | 32 | 0 |
| Aynı RNG kontrolü | **4,98297** | 12 | 32 | 0 |
| 19 uzman konsensüsü, deneysel | **4,98438** | 12 | 31 | 0 |
| Önceki V39 birleşimi | **4,99373** | 11 | 45 | 0 |

V44 Ana Beyin ile RNG **aynı 20 sayı listesini üretir** çünkü hiçbir aday uzman geçmemiştir. Bu iki satırın eşitliği, ana beynin öngörü üstünlüğü olduğunu göstermez. Konsensüs − RNG farkı **+0,001408 isabet/çekiliş**, 36 günlük bootstrap %95 aralığı **[−0,038914; +0,041731]**; anlamlı üstünlük kanıtı yok.

### Saatlerin 7.–12. çekilişleri / 3.888 hedef

| Yöntem | Ortalama 20'li isabeti |
|---|---:|
| V44 kontrol ana beyin | 4,98560 |
| Deneysel uzman konsensüsü | 5,03189 |
| Önceki V39 | 5,02058 |
| RNG kontrolü | 4,98560 |

Buradaki 5,03/20 gibi küçük farklılıklar, uzman eleme kuralını geçmediği için gelecek çekiliş avantajı olarak sunulmaz.

### 5 hareketli sıcaklık havuzu kotası, son 36 gün

| Önceden kota yöntemi | Tek havuz ±1 | Beş havuz birlikte ±1 | Matematiksel adil RNG beklentisi |
|---|---:|---:|---:|
| Havuz büyüklüğünün %25'i | %67,40143 | %18,88121 | %18,73779 |
| Tarihsel online kalibre kota | %67,30415 | %18,79160 | %18,69262 |
| Önceki oluşumdan geçiş hafızası | %66,55402 | %17,84434 | %17,76476 |

Tek havuzdaki %60–70 isabeti 20 sayı kimliğinin %60–70'ini bulma olarak okumamak gerekir.

## 9 dosyalı tek ZIP

1. `00_KULLANIM_NOTU.txt`
2. `01_HER_CEKILISTE_DONDURULMUS_20_LISTELER.csv`
3. `02_HER_CEKILISTE_BES_HAVUZ_KOTA.csv`
4. `03_UZMAN_SECIMI_MAXT_VALIDASYON.csv`
5. `04_20_LISTE_ISABET_EGITIM_VALI_TEST.csv`
6. `05_KOTA_ISABET_VE_RNG_REFERANS.csv`
7. `06_ESLENIK_GUN_BLOK_KARSILASTIRMA.json`
8. `07_KAPSAM_ELEME_GUVENLIK.json`
9. `08_VERI_SONRASI_LISTE.csv`

Kaynaklar: `v44_ana_beyin_uzman_elemesi.py`, `v44_ana_beyin_selftest.py`, `v44_ana_beyin_app.py`, Streamlit `v10_app.py` sekmesi **🧠 V44 Ana Beyin**.

## Devam kararı

Mevcut uzmanlar testte rastgele seçime kıyasla güvenilir üstünlük göstermedi. Dolayısıyla V44, bu aşamada bir kazanç motoru değil; **yanlış-pozitifleri önleyen araştırma denetçisi** olarak kullanılmalı. Yeni gelecek bağımsız tam günler eklendiğinde ilk 18+18 gün eşikleri kaydırılmadan eski kararın sonraki sonuçlarla doğruluğu izlenmeli. Çekiliş adil ve bağımsızsa, geçmiş frekans ve kalıp salınımları sonraki tek sayı çıkışının teorik %25 şansını değiştirmez.
