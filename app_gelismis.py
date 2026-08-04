import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Hızlı On Analiz Motoru', layout='wide')
DATA_FILE = Path(__file__).parent / 'veri.txt'
COLS = ['Cekilis_No', 'Tarih', 'Saat'] + [f'Sayi_{i}' for i in range(1, 21)]


def parse_line(line):
    line = re.sub(r'(?<=\d)-(?=\d)', ',', str(line).strip())
    parts = [p.strip() for p in line.split(',') if p.strip()]
    if len(parts) < 23:
        return None
    try:
        no = int(parts[0])
    except ValueError:
        return None
    nums = [int(x) for x in parts[3:] if x.isdigit() and 1 <= int(x) <= 80][:20]
    if len(nums) != 20 or len(set(nums)) != 20:
        return None
    return [no, parts[1], parts[2]] + sorted(nums)


@st.cache_data(show_spinner=False)
def load_data():
    valid, invalid = [], []
    if not DATA_FILE.exists():
        return pd.DataFrame(columns=COLS), ['veri.txt bulunamadı']
    for i, line in enumerate(DATA_FILE.read_text(encoding='utf-8', errors='ignore').splitlines(), 1):
        row = parse_line(line)
        if row:
            valid.append(row)
        elif line.strip():
            invalid.append(f'Satır {i}: {line[:120]}')
    df = pd.DataFrame(valid, columns=COLS)
    if not df.empty:
        df = df.drop_duplicates('Cekilis_No', keep='last').sort_values('Cekilis_No').reset_index(drop=True)
    return df, invalid


def num_cols(df):
    return [c for c in df.columns if c.startswith('Sayi_')]


def row_sets(df):
    return [set(map(int, r)) for r in df[num_cols(df)].to_numpy()]


def frequency(df):
    c = Counter(map(int, df[num_cols(df)].to_numpy().ravel()))
    return pd.DataFrame([{'Sayı': n, 'Frekans': c.get(n, 0)} for n in range(1, 81)])


def gaps(df):
    sets = row_sets(df)
    out = []
    for n in range(1, 81):
        gap = len(sets)
        for i, s in enumerate(reversed(sets)):
            if n in s:
                gap = i
                break
        out.append({'Sayı': n, 'Dinlenme': gap})
    return pd.DataFrame(out)


def combo_table(df, size, top_n):
    c = Counter()
    for s in row_sets(df):
        c.update(combinations(sorted(s), size))
    return pd.DataFrame([{'Grup': ' - '.join(map(str, k)), 'Frekans': v} for k, v in c.most_common(top_n)])


def consecutive_blocks(nums):
    nums = sorted(nums)
    if not nums:
        return []
    blocks, cur = [], [nums[0]]
    for n in nums[1:]:
        if n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2:
                blocks.append(cur)
            cur = [n]
    if len(cur) >= 2:
        blocks.append(cur)
    return blocks


def repeat_table(df):
    sets = row_sets(df)
    out = []
    for i in range(1, len(sets)):
        common = sorted(sets[i] & sets[i - 1])
        out.append({'Çekiliş': int(df.iloc[i].Cekilis_No), 'Tekrar sayısı': len(common), 'Tekrar edenler': ' - '.join(map(str, common))})
    return pd.DataFrame(out).sort_values('Çekiliş', ascending=False)


def block_table(df, last_n):
    prev, out = [], []
    for _, row in df.tail(last_n).iterrows():
        blocks = consecutive_blocks([int(row[c]) for c in num_cols(df)])
        shifts = []
        for b in blocks:
            for p in prev:
                if len(b) == len(p):
                    d = b[0] - p[0]
                    if d in (-2, -1, 1, 2):
                        shifts.append(f"{'-'.join(map(str,p))} → {'-'.join(map(str,b))} ({d:+d})")
        out.append({'Çekiliş': int(row.Cekilis_No), 'Bloklar': ', '.join('-'.join(map(str,b)) for b in blocks) or 'Yok', 'Kayma': '; '.join(shifts) or 'Yok'})
        prev = blocks
    return pd.DataFrame(out).sort_values('Çekiliş', ascending=False)


def generate_coupon(df, size, strategy, window):
    f = frequency(df.tail(window)).set_index('Sayı').Frekans
    g = gaps(df).set_index('Sayı').Dinlenme
    nums = np.arange(1, 81)
    if strategy == 'Sıcak ağırlıklı':
        w = np.array([(f.get(n, 0) + 1) ** 2 for n in nums], float)
    elif strategy == 'Dinlenmiş dönüş':
        w = np.array([(g.get(n, 0) + 1) ** 1.6 for n in nums], float)
    else:
        fv = np.array([f.get(n, 0) for n in nums], float)
        gv = np.array([g.get(n, 0) for n in nums], float)
        w = 0.6 * fv / max(fv.max(), 1) + 0.4 * gv / max(gv.max(), 1) + 0.05
    w /= w.sum()
    return sorted(np.random.choice(nums, size=size, replace=False, p=w).tolist())


def to_text(df):
    lines = []
    for _, row in df.sort_values('Cekilis_No').iterrows():
        vals = [str(int(row.Cekilis_No)), str(row.Tarih), str(row.Saat)] + [str(int(row[f'Sayi_{i}'])) for i in range(1, 21)]
        lines.append(','.join(vals))
    return '\n'.join(lines) + '\n'


def parse_pasted_draw(text):
    no = re.search(r'Çekiliş\s*no\s*:\s*(\d+)', text, re.I)
    dt = re.search(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})', text)
    nums = [int(x) for x in re.findall(r'(?m)^\s*(\d{1,2})\s*$', text)]
    if not no or not dt:
        return None, 'Çekiliş numarası, tarih veya saat bulunamadı.'
    if len(nums) != 20:
        return None, f'20 sayı bekleniyordu, {len(nums)} sayı bulundu.'
    if len(set(nums)) != 20 or any(n < 1 or n > 80 for n in nums):
        return None, 'Sayılar 1-80 arasında ve farklı olmalı.'
    return [int(no.group(1)), dt.group(1), dt.group(2)] + sorted(nums), None


st.title('🎯 Hızlı On Gelişmiş Analiz ve İstatistik Motoru')
st.caption('Birlikte çıkma, sıcak/soğuk döngüsü, dinlenme, tekrar, blok kayması ve akıllı kupon')

df, invalid = load_data()
if df.empty:
    st.error('Geçerli çekiliş bulunamadı.')
    st.stop()

latest = df.iloc[-1]
a, b, c = st.columns(3)
a.metric('Toplam çekiliş', f'{len(df):,}')
b.metric('Son çekiliş', int(latest.Cekilis_No))
c.metric('Son tarih / saat', f'{latest.Tarih} {latest.Saat}')

with st.sidebar:
    st.header('⚙️ Ayarlar')
    window = st.slider('Son kaç çekiliş?', 50, max(50, len(df)), min(500, len(df)), 50)
    if invalid:
        st.warning(f'{len(invalid)} bozuk/eksik satır atlandı.')

adf = df.tail(window)
tabs = st.tabs(['📈 Frekans', '🔗 2-3-4-5’li', '🔥 Sıcak/Soğuk', '⏳ Dinlenme', '🔄 Tekrar & Blok', '🎯 Akıllı Kupon', '➕ Yeni Çekiliş'])

with tabs[0]:
    f = frequency(adf).sort_values(['Frekans','Sayı'], ascending=[False,True])
    st.dataframe(f, use_container_width=True, hide_index=True)
    st.bar_chart(f.sort_values('Sayı').set_index('Sayı').Frekans)

with tabs[1]:
    subtabs = st.tabs(['2’li','3’lü','4’lü','5’li'])
    for tab, size in zip(subtabs, [2,3,4,5]):
        with tab:
            topn = st.slider(f'İlk kaç {size}’li grup?', 10, 100, 30, key=f'top{size}')
            st.dataframe(combo_table(adf, size, topn), use_container_width=True, hide_index=True)

with tabs[2]:
    f = frequency(adf)
    g = gaps(df)
    merged = f.merge(g, on='Sayı')
    x, y = st.columns(2)
    with x:
        st.markdown('### 🔥 Sıcak sayılar')
        st.dataframe(merged.sort_values(['Frekans','Dinlenme'], ascending=[False,True]).head(20), use_container_width=True, hide_index=True)
    with y:
        st.markdown('### ❄️ Soğuk / dinlenmiş')
        st.dataframe(merged.sort_values(['Dinlenme','Frekans'], ascending=[False,True]).head(20), use_container_width=True, hide_index=True)

with tabs[3]:
    st.dataframe(gaps(df).sort_values(['Dinlenme','Sayı'], ascending=[False,True]), use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader('Çekilişler arası tekrar')
    st.dataframe(repeat_table(adf).head(100), use_container_width=True, hide_index=True)
    st.subheader('Ardışık bloklar ve sağa/sola kayma')
    st.dataframe(block_table(df, min(window,300)), use_container_width=True, hide_index=True)

with tabs[5]:
    c1, c2, c3 = st.columns(3)
    with c1: size = st.selectbox('Kolon büyüklüğü', [3,4,5,6,7,8,10], index=4)
    with c2: count = st.slider('Kolon sayısı', 1, 10, 4)
    with c3: strategy = st.selectbox('Strateji', ['Dengeli','Sıcak ağırlıklı','Dinlenmiş dönüş'])
    if st.button('🎯 Kolonları üret', type='primary'):
        made = set()
        while len(made) < count:
            made.add(tuple(generate_coupon(df, size, strategy, window)))
        for i, coupon in enumerate(made, 1):
            st.success(f"Kolon {i}: " + ' - '.join(map(str, coupon)))
        st.caption('İstatistiksel örneklemedir; kesin sonuç garantisi vermez.')

with tabs[6]:
    st.subheader('Yeni çekilişi olduğu gibi yapıştır')
    raw = st.text_area('Çekiliş metni', height=260, placeholder='''Çekiliş no: 46729\n04.08.2026 - 12:02\n2\n15\n18\n20\n38\n40\n44\n49\n51\n52\n54\n57\n58\n59\n63\n64\n65\n76\n78\n80''')
    if raw.strip():
        row, err = parse_pasted_draw(raw)
        if err:
            st.error(err)
        else:
            st.code(','.join(map(str,row)), language='text')
            if row[0] in set(df.Cekilis_No.astype(int)):
                st.warning('Bu çekiliş zaten kayıtlı.')
            else:
                new_df = pd.concat([df, pd.DataFrame([row], columns=COLS)], ignore_index=True).sort_values('Cekilis_No')
                st.success('Yeni çekiliş eklendi. Güncel veri.txt hazır.')
                st.download_button('⬇️ Güncellenmiş veri.txt indir', to_text(new_df).encode('utf-8'), file_name='veri.txt', mime='text/plain', type='primary')
                prev = set(map(int, df.iloc[-1][num_cols(df)].tolist()))
                cur = set(row[3:])
                common = sorted(prev & cur)
                blocks = consecutive_blocks(row[3:])
                st.write(f'Önceki çekilişten tekrar: **{len(common)} sayı**')
                st.write('Tekrar edenler:', ' - '.join(map(str, common)) or 'Yok')
                st.write('Ardışık bloklar:', ', '.join('-'.join(map(str,b)) for b in blocks) or 'Yok')
                st.info('İndirdiğin veri.txt dosyasını GitHub’daki veri.txt üzerine yüklediğinde kayıt kalıcı olur.')

if invalid:
    with st.expander('⚠️ Atlanan bozuk satırlar'):
        st.code('\n'.join(invalid[:200]), language='text')
