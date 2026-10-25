# V230 Gece Merkezi — Kurulum

## Streamlit Community Cloud
Yeni uygulama için New app seç.
Repository: gozlekakif-alt/hizli-on-analiz-motoru
Branch: main
Main file path: v230_gece_merkezi.py
Dependencies: Mevcut requirements.txt
Yerel kullanım: streamlit run v230_gece_merkezi.py

Eski v10_app.py ve diğer dosyalara dokunulmadı.

## 22:57 sabit ve gece değişken görünüm
07:02–22:57 arası 192 gerçek çekiliş zorunludur. 80 sayı 16'şarlı beş havuza ayrılır. Frekans parantez içinde, yön son 36 çekiliş hızının önceki 156 ile karşılaştırılmasından elde edilir.
Bu SABİT havuz gece boyunca değişmez. 23:02–23:57 aynı gün, 00:02–01:02 ertesi gün olsa bile aynı operasyonel geceye bağlanır.
Her yeni gerçek 20'li sabit karakteriyle sıralı gösterilir. Hareketli ikinci havuz son 72 çekilişe göre ayrıca güncellenir; bu farklı bir ölçümdür.

## Veri kaynakları ve kalıcılık
veri.txt / .csv / .gz / .zip dosyası yükleyebilir ya da GitHub veri.txt dosyasını okumayı deneyebilirsin.
Satır örneği: 46005;2026-08-01 00:02;4,7,8,11,19,24,26,34,40,42,43,44,48,50,52,54,57,67,72,74
20 farklı sayı ve gerçek çekiliş saati doğrulanır; çelişen girişler reddedilir.
Streamlit oturumu kalıcı değildir. Yeni kayıtlar GitHub'a otomatik yazılmaz. Her giriş sonrası TXT yedeği indir ve sonraki oturumda yeniden yükle.

## Kupon ve eski motorlar
1–3 yön karmalı 10'lu kolon, 5×16 havuz veya 3 sıcak/4 ılık/3 soğuk düzeni, seçenekli kota ve gerçek çekiliş isabet kontrolü sunulur.
V18 gelen20/kalan60, V35 11 karakter, V39 uzman, V40 altı ısı ve yön, V41 ters dönüş, V42 değişken beş havuz, V44 ana beyin, V45 sinyal, V50 aile, V52 eşlikçi, V54 RNG, V55 önce karakter araştırması eski modüllerden isteğe bağlı çalışır.
V42'nin beş havuzu sabit 16'lı değil, değişken hacimlidir. Yeni ekrandaki 5×16 ile sonuçlarını doğrudan aynı sınıflandırma sayma.

## Yorum ve sınırlar
Gerçek 20'linin gelecek sayıları tahmin edilmiş sayılmaz. Adil çekilişte sayı başına sonraki 20'lide görülme olasılığı %25; geçmiş sıcaklık/yön yöntemlerinin güvenilir üstünlüğü kanıtlanmış değildir.
