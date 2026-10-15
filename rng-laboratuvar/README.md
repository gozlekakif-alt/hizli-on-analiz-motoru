# Hızlı On — RNG Karakter Laboratuvarı

**Bağımsız uygulama:** Eski `v10_app.py`, `app.py` ve `veri.txt` dosyalarına dokunmaz.

## Ayrı Streamlit uygulaması kurma

1. Streamlit Community Cloud'da **New app** seç.
2. Repository: `gozlekakif-alt/hizli-on-analiz-motoru`
3. Branch: `main`
4. Main file path: **`rng-laboratuvar/app.py`**
5. Deploy. Gerekli paketler bu klasördeki `requirements.txt` içinde.

Bu işlem eski Streamlit uygulamasını etkilemez. Yeni uygulama aynı GitHub deposunda ayrı bir giriş dosyası olarak çalışır. Tamamen yeni GitHub deposuna taşımak istersen bu klasör bütünüyle taşınabilir.

## Veri kaynağı

Tek düğmeyle eski projenin `veri.txt` dosyasını **salt okunur** yükler:

`https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt`

Depo özel (private) ise veya raw bağlantı erişilemezse aynı dosyayı uygulamaya yükle. Uygulama GitHub'a hiçbir bilgi YAZMAZ.

## Neyi test ediyor?

- 217 çekilişli tam günlerde son 72 çekiliş + ilk 6 çekilişe göre **sonraki 6 çekilişin** bant, sıcak/soğuk, örtüşme ve seçili üçlü davranışını önceden tahmin eder.
- Yalnız önceki saatleri kullanan karakter tahmini, matematiksel adil RNG ortalamasına karşı sınanır.
- Karakterli 10'lu, karakter kullanmadan oluşturulan 10'lu ve dondurulmuş rastgele 10'lu aynı hedeflerde test edilir.
- Karakter tahmininde ve kupon sonuçlarında önceki saatlerin 180 testinden yeterli sapma olmadan **SİNYAL YOK** kalır.
- 3'lü, 4'lü ve 5'li saatlik ailelerin aynı kalma / tek sayı değişimi / lider listesinden çıkma davranışı, bağımsız 20/80 sanal çekiliş günleriyle karşılaştırılır.
- Sabit 2026-10-16 başlangıcıyla, ilk 14 yeni tam gün ayrıca raporlanır.

**Dürüstlük:** RNG'nin gerçek algoritması, başlangıç tohumu ve gelecekteki sonuçları bu verilerden çözümlenmiş değildir; öngörü başarısı ancak yeni günlerdeki bağımsız testle değerlendirilir.

## Yerel test / rapor

```bash
python rng-laboratuvar/core.py --selftest
python rng-laboratuvar/core.py --data veri.txt --sims 40 \
  --output rng_lab_tek_rapor.zip
```

Bağımsız Streamlit:
```bash
pip install -r rng-laboratuvar/requirements.txt
streamlit run rng-laboratuvar/app.py
```

## Tek ZIP dosyasının içeriği

`00_TEK_RAPOR_OZET.txt`, `01_KARAKTER_TAHMIN_VE_GERCEK.csv`,
`02_KUPON_3_KONTROL_ISABET.csv`, `03_KOR_TEST_OZET.csv`,
`04_AILE_SAATTEN_SAATE_GECIS.csv`,
`05_GERCEK_VE_SANAL_RNG_KARSILASTIR.csv`,
`06_VERI_KONTROL.json`, `07_KILITLI_KURALLAR.txt`.

Tüm sayısal testler açıklayıcıdır; hiçbir finansal kazanç veya gelecek öngörüsü garanti edilmez.
