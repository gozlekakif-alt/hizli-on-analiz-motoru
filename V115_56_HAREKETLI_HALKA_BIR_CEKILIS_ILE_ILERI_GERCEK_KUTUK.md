# V115 — 56 Sabit Sayıda, 12'şer Çekilişlik Hareketli Halka (Her Yeni Çekilişte Tek Kayma)

**Kullanıcının düzelttiği yöntem:** Önceki V100C/V104/V114'te tarihsel çekiliş saatlerine göre **sabit mutlak 12'li halka kimliği** taşınır; FIFO belleği 12'nin ortasından kesilirse 55 tam + 2 kısmi, yani 57 fiziksel halka görünür. **V115'te BUNU İSTEMİYORUZ.**

## Yeni tanım

Her anda son **672 gerçek çekiliş** kronolojik sıralanır; en eskiden yenisine doğru **56 adet 12'li grup** olarak bölünür. Bunlar *göreli* halka konumlarıdır; orijinal kalıcı saat halka ID'si değildir.

Yeni çekiliş gelince:
1. 1. halkanın en eski çekilişi 672 penceresinden çıkar ve **silinmez**, dışarı çıkan kayıt defterine yazılır;
2. 2. halkanın en eski çekilişi 1. halkanın sonuna aktarılır, 3. halkanın en eskisi 2.'ye aktarılır, ...;
3. yeni 20 sayılık çekiliş 56. halkanın sonuna girer;
4. toplam 56 halka ve halka başına 12 çekiliş **hiç değişmez**;
5. her halkanın 80 sayı için *12 bitlik 1/0 dizisi*, 12 çekiliş çıkış sayısı ve son 72 çekilişle hesaplanan 16'lık sıcaklık havuzunu yeniden oluştur; havuz sınıfları gelecek tahmini için sadece çekilişten **önce** kullanılabilir.

Örneğin halka56 = son 12 gerçekte gelen çekiliş; halka1 = mevcut 672 bellekteki en eski 12 çekiliş. Çekilişten sonra 20 yeni rakamın gelmesi, 20 eski rakamın çıkması ve her halka için 20 çıkış/20 giriş çizimlerinin yer değiştirmesi aynı şey değildir: halka toplamında hep **12×20=240** tane 1 vardır.

## V114 ile doğrulanmış veri üzerinde ilk yürüyüş

**Son bilinen çekiliş:** #62014, 13 Ekim 2026 19:57. Geçmiş V114 kaydında 56. tamamlanmış sabit halka #62004'e kadar gelmiş, son 10 çekiliş ayrı kısmi halka sayılıyordu. V115'te #62005–#62014 çekilişlerinin **her biri tek adım** ilerletildi. V114'ün son 56 sabit halka 672 çekilişi ile son kayan 672 çekilişinin **662 çekilişlik bire bir örtüşmesi** kontrol edildi; birleşik **682 gerçek çekiliş** yeniden üretildi; tümünün tam 20 sayısı bulundu.

**Hareketli 56. halka sonunda #62014**: son 12 çekiliş #62003–#62014; 80 sayı toplamı yine 240 çıkış.

| Yeni eklenen çekiliş | Bellekten çıkan en eski çekiliş | Yerel 12-çekiliş sayımı değişen halka | Yeni son72 sıcaklık havuzu değiştiren sayı |
|---|---|---:|---:|
| 62005 | 61330 | 56/56 | 16 |
| 62006 | 61331 | 56/56 | 14 |
| 62007 | 61332 | 56/56 | 10 |
| 62008 | 61333 | 56/56 | 12 |
| 62009 | 61334 | 56/56 | 14 |
| 62010 | 61335 | 56/56 | 18 |
| 62011 | 61336 | 56/56 | 16 |
| 62012 | 61337 | 56/56 | 22 |
| 62013 | 61338 | 56/56 | 16 |
| 62014 | 61339 | 56/56 | 12 |

Son 56. hareketli halkada **5 kez görünen** sayılar: **8, 11, 14, 21, 45, 57, 58, 69, 72, 73, 77, 79**. **0 kez görünen:** **78**. Diğer sayıların tam dökümü ve 12 bit dizileri ZIP/CSV içindedir. Bu sonuç eski sabit 56. halka sayı listesinden **farklıdır**, çünkü halka zaman sınırları artık her beş dakikada kayıyor.

## Gerçek kullanıcı çıktısı

- Yerel rapor: `V115_56_HAREKETLI_HALKALAR_BIR_CEKILIS_ILERLEME.zip` — V114'ten alınan **son 10 gerçek yeni çekilişin** kesintisiz ve bire bir örtüşmeli bağımsız denetimi, son 56x80 satırlık hareketli halka ve 56. halka 80 sayılık döküm.
- Depodaki **tam veri yürüyüşü kodu**: [v115_56_halka_kayan_12lik_her_cekilis_giris_cikis.py](v115_56_halka_kayan_12lik_her_cekilis_giris_cikis.py).
- GitHub Actions: [V115 her çekilişte kayan 56 halka](https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/workflows/v115-56-kayan-halka-her-cekilis.yml).
- Program depo `veri.txt` içindeki **bütün 15.790 çekilişi** okur. İlk 672'yi kurduktan sonra **15.118 yeni çekilişi** tek tek yürüterek 56 halkadan her adımda kaç sayının arttığını/azaldığını ve beş havuzda değişimi kaydeder. Çıktı tarihi eklenen veriyle otomatik değişebilir.

## Sınırlar

Bu, kullanıcının istemiş olduğu **konum olarak kayan halka** sistemidir; geçmişteki fiziksel saat sınırına bağlı halka kimlikleri için tek kaynak değildir. Eski V100C/V104 motorunu silmeden **paralel alternatif** olarak tutarız. Yeni modelin geçmişte farklı bir sayım üretmesi bir tahmin avantajı olduğunu **kanıtlamaz**. Aile birlikteliği/havuz dönüşü tekrar araştırılacaksa, hedeften önce dondurulan bütün 56 hareketli halkanın özellikleri kullanılmalı ve sonuç yalnız sonraki çekilişte ölçülmelidir.
