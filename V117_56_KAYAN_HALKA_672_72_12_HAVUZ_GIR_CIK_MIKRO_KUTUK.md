# V117 — 56 Hareketli Halkanın 672 / 72 / 12 Çekiliş Havuz Sınırları

**16 Ekim 2026.** Son veri: **13 Ekim 2026 #62014**. Kaynak gerçek çekilişlerin son **672×80 adet 1/0 biti**, V114 ZIP'in `03_YURUYEN_SON672_80_SAYI_TAM_0_1_IZ.csv` dosyasından alındı. Bundan önceki son 10 çekiliş, V115 kayıtlarındaki son 10 **içeri gelen 20 + dışarı çıkan 20** ile tersine doğru bire bir yeniden kuruldu. Tüm 11 zaman anında **672 çekiliş ×20 sayı** ve 56×12 eşitliği korundu.

## Kullanıcının asıl sorusu

672 çekilişlik genel birikim, son72'lik sıcaklık, son12'lik hareketli 56. halka neden **farklı hızda havuz değiştiriyor? Bir sayı kaç kez görünürse havuz sınırını geçer?**

Cevap: **Sabit adet eşiği yok**. Havuzlar sayının izafi **80'li sıralamadaki pozisyonuna** göre kurulur; 1–16 soğuk, 17–32 serin, 33–48 nötr, 49–64 ılık, 65–80 sıcak. Her sayının bir yeni çekilişle sayımında olabilecek değişiklik
`yeni bit (1/0) – çıkan en eski bit (1/0)` = yalnız −1, 0, +1. Ama eşikteki başka sayılar değişirse sıralama da değişir; bit toplamı **0** bile olsa havuz değişebilir.

### Son 10 gerçek tek-çekiliş adımında ortalama havuz değiştiren sayı (80 üzerinden)

- Son **672**, 56 hareketli halka bütününün toplamı: **6,4** sayı/çekiliş.
- Son **72**, mevcut sıcaklık skorunun penceresi: **15,0** sayı/çekiliş.
- Son **12**, 56. hareketli halkanın kendi 12 çekilişi: **28,8** sayı/çekiliş.

Bu on adımda gözlenen maksimum bir tek sayının **sınıf sıçraması** 672'de 1, 72'de 1, 12'de 2 havuzdur. Daha fazla hareket matematiksel olarak imkânsız demek değildir.

### #62014 sonrası güncel sınıf adet aralıkları

| Havuz | 672 çekilişte çıkış adedi | Son72 çıkış adedi | 56. halkada son12 çıkış adedi |
|---|---|---|---|
| Soğuk | 146–160 | 10–14 | 0–2 |
| Serin | 160–164 | 14–17 | 2–3 |
| Nötr | 165–172 | 18–19 | 3 |
| Ilık | 172–176 | 19–20 | 3–4 |
| Sıcak | 176–191 | 21–25 | 4–5 |

**Adet aralıkları örtüşebilir!** Örneğin 672'de 176 kez çıkan bir sayı ılık veya sıcak olabilir. Eşit frekanslar sayı kimliği artan sırada çözülür; ayrıca her havuzda daima 16 sayı kalır. Bu tabloda sıcaklığı belirleyen şey mutlak sınır değil, **sıralama**.

### #62014 hedef çekilişinin mekanik etkisi (hemen öncesi/sonrası)

**672 çekilişlik havuz**: dört sayı sınıf değiştirdi:
- **45:** 164 SERİN → 165 NÖTR (**1 kez artış**)
- **61:** 176 ILIK → 176 SICAK (**sayım değişmedi**)
- **33:** 177 SICAK → 176 ILIK (**1 kez azalma**)
- **71:** 164 NÖTR → 164 SERİN (**sayım değişmedi**)

**Son72 havuzu**: toplam 12 sayı değiştirdi, **ısınanlar 27,43,55,58,68,73**, **soğuyanlar 3,6,23,33,56,57**. Bir sayı 0 kez görülmesine rağmen bile başka sayılar sınır geçtiği için havuz değiştirebilir.

**56. halka son12 havuzu**: toplam **29 sayı** değiştirdi: 16 yukarı ve 13 aşağı. Sayının halka-56'da *tek çizimde çıktıktan sonraki* yeni sayımı tek başına +1/0/−1'dir; ancak sınıfı diğer 79 sayının yeni sıralamasına göre değişir.

Örnekler:
- **64:** 672'de **191 kez = SICAK**, son72'de **13 kez = SOĞUK**, son12'de **1 kez = SOĞUK**.
- **78:** 672'de **169 kez = NÖTR**, son72'de **14 kez = SERİN**, son12'de **0 kez = SOĞUK**.

**Mekanik uyarısı**: Hedef çekilişin sonucu havuz durumunu *sonradan* değiştirir. Bu, hedefin öncesinde bilinen bir öngörü değildir. Gelecek çekiliş tahmininde her sinyal mutlak surette hedef çekilişten **önceki** 56×12 FIFO ile tanımlanmalıdır.

## Kanıt ve çalışma çıktıları

Konuşmada doğrulanmış yerel `V117_672_72_12_HAVUZ_ESIKLERI_56_HALKA_HAREKET.zip`:
1. `00_V117_TURKCE_SONUC.txt`
2. `01_80_SAYI_SON_672_72_12_CIKIS_HAVUZ.csv`: her sayı için üç farklı pencere toplamları / sıraları / beş havuz kimliği;
3. `02_ON_CEKILIS_80_SAYI_CEKILIS_ONCESI_SONRASI.csv`: **10×80×3=2.400** adım, 1/0 giriş ve çıkışları, eski/yeni sıklık, eski/yeni sıra/havuz, fark;
4. `03_5_HAVUZ_ICIN_GUNCEL_ARALIKLAR.csv`;
5. `04_10_ADIM_CIKAN_CIKMAYAN_HAVUZ_HAREKETLERI.csv`;
6. `05_DENETIM.json`.

Özellikle önceki araştırmalardaki son72 havuzları ile tam672 ve son12 havuzlarını birbirinin yerine kullanmamalıyız. Kullanıcının keşfini göstermek için üçünü aynı hedefte **ayrı katmanlar** halinde saklamak gerekli. Bunların hepsi geçmiş sonuçların betimsel eşit-kota etkisidir, gelecek isabet üstünlüğü göstermez.
