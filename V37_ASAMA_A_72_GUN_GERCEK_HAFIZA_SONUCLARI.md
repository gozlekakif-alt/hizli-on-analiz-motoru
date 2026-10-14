# V37 — Ortak 80 sayı yaşam hafızası / Aşama A: GERÇEK TEST

**14.10.2026 • Çalışan çekirdek.** Bu sayfa 207 alt uzman tasarımından farklı olarak **fiilen çalışan sekiz temel motorun** sonuçlarıdır.

## Tam veri ve başarı

Kaynak: GitHub veri.txt; 72 eksiksiz gün × 217 çekiliş = **15.624** gerçek çekiliş. Diğer iki kısmi gün tam-gün raporuna alınmadı.

- Her çekilişin 80 sayı kimlik kartı: **1.249.920** SQLite \`ball_step\` kaydı.
- Denetlenebilir motor haznesine giriş ve değişim olayı: **4.218.092** \`reservoir_event\`.
- Aynı sayı ve aynı gerçek çekilişte oluşan, kaynak olay ID'leriyle bağlantılı motor diyalogları: **1.016.565** \`event_dialogue\`.
- Çalışır motorlar: \`POOL20\`, \`HEAT_SEAT\`, \`HEAT_DIRECTION\`, \`WAIT_DAY\`, \`WAIT_LIFE\`, \`FREQ11\`, \`BAND\`, \`HALF\`. **8 çalışır**, diğer **207 tasarımdaki uzman yolları henüz çalışmıyor.**
- SQLite \`integrity_check=ok\`, her çekilişte 80 sayı × 20 gelen / 60 gelmeyen, altı ısı sınıfı toplam 80, mükerrer kayıt kontrolü, 01:02→07:02 ara gerçek bir sonraki çekiliş, eksik kaynak UNKNOWN kuralı doğrulandı.
- \`veri.txt\` ayrıştırıcısı iki sorunlu/tekrarlı kaydı raporladı; tam günü oluşturamayan kaynaklar dışarıda tutuldu.
- Son tam gün: **12.10.2026**, son çekiliş numarası **61845**, pozisyon **217**. Bu rapor 14 Ekim'in canlı sonuçlarını içerdiği iddiasında değildir.

## İndir ve uygulama

- GitHub başarılı 72 günlük çalışma: https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38574564269
- 6 dosyalı ZIP (SQLite ana dosya + denetim + registry + özet): https://github.com/gozlekakif-alt/hizli-on-analiz-motoru/actions/runs/38574564269/artifacts/11899893087
- Paket boyutu yaklaşık **463 MB**. Bu, verinin çoklu olay ağı nedeniyle büyük olduğunu gösterir; mobil indirme ve Streamlit belleğinde yük olabilir.
- Streamlit: \`v10_app.py\` ana dosyası, **🗃️ V37 Ortak Yaşam Hafızası** sekmesindeki tek düğme.
- GitHub Action: \`.github/workflows/v37-hafiza-check.yml\`; canlı veri.txt yeni sürümü yayımlanınca yeni ZIP yeniden üretilir.
- V37 uygulama çekirdeği: \`v37_ortak_hafiza.py\`, \`v37_hafiza_app.py\`, \`v37_hafiza_selftest.py\`, \`v37_export_zip.py\`.

## Kalıcılık ve kaynak güvenliği

Streamlit oturumundaki SQLite geçicidir; **kalıcı GitHub veritabanı yüklenmiş değil**. Resmi geçmişin tekrar oluşturulabilir ana kaynağı GitHub \`veri.txt\` dosyasıdır. İndirilen ZIP veri defterinin kaydedilebilir bir kopyasıdır. Aynı çizelge SQLite'ya ikinci kez okutulunca yeni çekiliş eklenmez; yalnız sona eklenen çekilişleri işlemeye çalışır. Daha önceki bir sonucu değiştirilmiş veya kayıp girişler eski veritabanına sessizce eklenmez: çatışma olur ve yeni DB gerekir.

**Sınırlama:** Burada 'motorlar arası diyalog' yalnız aynı sayı ve aynı çekilişin eşzamanlı olaylarının kaynak ID eşleştirmesidir. Ailelerin çapraz çekiliş epizotları, 2+1+1/2+2 gibi tamamlanma yolları ve 207 uzman dalın tamamı sonraki safhalarda bu temele bağlanacak. Gizli RNG'nin algoritması çözülmüş değildir.
