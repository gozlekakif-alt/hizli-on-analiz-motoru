# V36 — 72 tam günlük gerçek veri ile davranış klonu test sonuçları

**Tarih:** 14 Ekim 2026. Otomatik test: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38566449587

**Başarı durumu:** GitHub Actions tam çalıştı; sentetik no-lookahead, hazne dengeleri, eşsiz 20 sayı, eksik çekiliş, deterministik ZIP kontrolü başarılı; gerçek \`veri.txt\` 72 tam gün (15.624 çekiliş) üzerinden tek ZIP üretildi.

## Klonun uzman motorları
- 15 motor grubu: çıkan20, çıkmayan60, 6 sıcaklık, ısı yönü/36 geçiş, 6–11+ bekleme, 11'li çıkma, 8 bant, alt/üst40, tekrar, ayna, çıkan20-80/80 döngüsü, ikili/üçlü/dörtlü aile ve 11-bit imza.
- 13 ayrı çevrimiçi akort dalı; her gerçek çekiliş sonrasında geçmişte bilinen hazne kayıtlarıyla öğrenme.
- Bütün gerçek/klon çizgilerinde 80 sayının tamamı etiketlenir; her motorun giriş/çıkış numaraları raporlanır.
- 2.118 ayrı motor alt-haznesi gözlendi; 1.249.920 gerçek sayı–çekiliş detayı kaydedildi.

## Son 36 tam günün ileri tarihli karşılaştırması

| Ölçü | Gerçek | Özerk klon | Gerçek durumundan klon | Bağımsız RNG kontrol |
|---|---:|---:|---:|---:|
| Gerçek 20 sayıyla ortalama örtüşme | 20,000 | 5,01907 | 5,00435 | 5,00653 |
| Çekiliş sonu 6+ çekiliş bekleyen sayı | 13,93292 | 13,91935 | — | — |
| Çekiliş sonu son 11'de 6+ görünmüş sayı | 2,63441 | 2,62250 | — | — |

**Okuma:** Topluluk/dağılım karakterleri birbirine benziyor, ama gerçek sayı kimliklerinin gelecekte daha iyi tahmin edildiği kanıtlanmadı. %25'lik tek sayı beklentisi ve 20/20 örtüşmede beklenen 5 sayının çok yakınında.

**ZIP:** 80.216.959 bayt, iç içe GitHub artifact arşiviyle 80.217.153 bayt. 11 rapor dosyası; 1,25 milyon 80-sayı satırı, her 15.624 adımın gerçek/klon 15 motor hazne giriş-çıkış defteri, online kalibrasyon, tarihsel aileler, 80/80 döngü, günlük karşılaştırma.

**İndir:** https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38566449587/artifacts/11896690396

**Yeni veride:** GitHub \`veri.txt\` değiştiğinde otomatik workflow yeniden rapor üretir. Streamlit V10 içindeki V36 sekmesi de tek düğmeyle bütün geçmişi deterministik yeniden oynatır. Bu yüzden veri geçmişi GitHub'da korunur; Streamlit oturum durumu kalıcı GitHub checkpoint'i sayılmaz.

**Bilimsel sınır:** Bu bir gizli RNG tohum/algoritma klonu değildir; gözlenen dağılımları yeniden üretmeye ve online akort etmeye çalışan istatistiksel emülatördür. Özerk klonun genel istatistikleri benzemesine rağmen gelecek kazandıran 20 sayının bilindiği sonucu çıkarılamaz.
