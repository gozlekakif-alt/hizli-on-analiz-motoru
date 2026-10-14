# V33 — 6 / 7 / 8 / 9 / 10 çekiliş bekleyen 80 sayının havuzları

**14 Ekim 2026** · Hızlı On · Kaynak: `veri.txt` · 72 tam gün · 15.624 çekiliş. Program: `v33_bekleme_havuzlari.py`; Streamlit: `v33_bekleme_app.py`; 12 dosyalı tek ZIP ve GitHub Actions.

## Bekleme sınıfının kesin anlamı

Sayı son kez göründükten sonra arka arkaya kaç GERÇEK çekilişte gelmedi? `6,7,8,9,10,11+`. Her gün 00:02'de bireysel bekleme sayacı sıfırdan başlar; sayı çıktığı anda sıfırlanır. 01:02–07:02 boşluğu fazladan çekiliş sayılmaz. Eksik kayıtlar yokluk varsayılmaz. Döngüde tüm 80 sayı görülmesi bireysel beklemeyi sıfırlamaz; **V32'nin 80/80 sayacı ile bireysel yokluk sayacı ayrı mekanizmalardır.**

## Tam 72 gün ölçümü

| Sınıf | Günlük ayrı sayı ortalaması | Bir çekiliş sonunda ortalama bekleyen sayı | 80 sayının hepsinin sınıfa girdiği gün |
|---|---:|---:|---:|
| 6 | 80,00 | 3,532 | 72 / 72 |
| 7 | 80,00 | 2,640 | 72 / 72 |
| 8 | 79,92 | 1,965 | 68 / 72 |
| 9 | 79,51 | 1,464 | 46 / 72 |
| 10 | 77,93 | 1,098 | 12 / 72 |
| 11+ | 74,06 | 3,240 | 0 / 72 |

Bir çekiliş sonrasında toplam **13,938/80** sayı 6+ beklemede. Bunların hepsi o anda `CIKMAYAN_60` havuzunda (çıkan 20 içinde hiçbiri bulunamaz). Yeni çekilişte ortaya çıktığında çıkan 20 havuzuna geçer.

## 6 sıcaklık havuzu (V28), bekleyen sayı gözlemi içindeki yüzde

| Sınıf | Soğuk | Soğuğa yakın | Orta | Ilık ve üstü |
|---|---:|---:|---:|---:|
| 6 | %29,0 | %28,6 | %22,1 | %20,4 |
| 7 | %36,8 | %30,0 | %19,7 | %13,4 |
| 8 | %45,3 | %30,1 | %16,3 | %8,3 |
| 9 | %54,4 | %28,6 | %12,4 | %4,7 |
| 10 | %63,9 | %25,3 | %8,4 | %2,4 |
| 11+ | %86,1 | %11,2 | %2,3 | %0,3 |

Soğuk havuz olasılığı, kullanılan ısı göstergesi son çekilişlerde görülmemeye göre hesaplandığından mekanik olarak da artar; bağımsız öngörü kanıtı değildir.

## V32 çıkan20 80/80 döngüsündeki iki alt havuz

| Sınıf | Döngüde zaten görülmüş | Döngüde henüz görülmemiş |
|---|---:|---:|
| 6 | %65,9 | %34,1 |
| 7 | %60,1 | %39,9 |
| 8 | %54,5 | %45,5 |
| 9 | %48,6 | %51,4 |
| 10 | %43,1 | %56,9 |
| 11+ | %25,1 | %74,9 |

## Son 36 test gününde, bekleyen sayının bir SONRAKİ gerçek çekilişte yeniden görülmesi

| Bekleme | Gerçek çıkan20'ye geri dönüş | Rastgele 20/80 referansı |
|---|---:|---:|
| 6 | %24,847 | %25 |
| 7 | %25,145 | %25 |
| 8 | %25,325 | %25 |
| 9 | %24,897 | %25 |
| 10 | %24,838 | %25 |
| 11+ | %24,864 | %25 |

Bu küçük farklardan hiçbirine dayanarak kupon üstünlüğü iddia etmiyoruz; dönemin önceki 36 günü eğitim/keşif, sonraki 36 günü ölçüm olarak ayrıdır.

## Araştırmanın devamı

Her gerçek çekilişte sayının bekleme sınıfı, altılı ısı havuzu, 8×10 bant, 1–40/41–80 konumu, V32 80/80 döngüsünde görüldü/görülmedi ve sonraki gerçek çekilişte geri dönme durumu ayrı yazılıyor. Günlük farklı sayı, sınıfa giriş tekrarı, anlık sınıf büyüklüğü, yeniden çıkış ayrı göstergelerdir. Tek ZIP içinde tüm satırlar bulunur.
