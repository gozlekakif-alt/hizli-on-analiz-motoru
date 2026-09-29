# -*- coding: utf-8 -*-
from __future__ import annotations
import base64
from datetime import datetime, date
from pathlib import Path
import requests
import pandas as pd
import streamlit as st

from motor_v5 import (
    EXPECTED_MINUTES, STATE_TR, load_txt_text, dataframe_to_txt, append_draw,
    live_analysis, historical_phase_table
)

st.set_page_config(page_title="Hızlı On Canlı Kupon V5", page_icon="🎯", layout="wide")

LOCAL_DATA = Path("veri.txt")

class GitHubStore:
    def __init__(self):
        self.token = st.secrets.get("GITHUB_TOKEN", "") if hasattr(st, "secrets") else ""
        self.repo = st.secrets.get("GITHUB_REPO", "") if hasattr(st, "secrets") else ""
        self.branch = st.secrets.get("GITHUB_BRANCH", "main") if hasattr(st, "secrets") else "main"
        self.path = st.secrets.get("GITHUB_DATA_PATH", "veri.txt") if hasattr(st, "secrets") else "veri.txt"
        self.ok = bool(self.token and self.repo and self.path)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get(self):
        if not self.ok:
            return None, None
        url = f"https://api.github.com/repos/{self.repo}/contents/{self.path}"
        r = requests.get(url, headers=self._headers(), params={"ref": self.branch}, timeout=20)
        if r.status_code == 404:
            return "", None
        r.raise_for_status()
        j = r.json()
        txt = base64.b64decode(j["content"]).decode("utf-8")
        return txt, j.get("sha")

    def put(self, text, message):
        if not self.ok:
            raise RuntimeError("GitHub bağlantısı ayarlı değil.")
        current, sha = self.get()
        payload = {
            "message": message,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        url = f"https://api.github.com/repos/{self.repo}/contents/{self.path}"
        r = requests.put(url, headers=self._headers(), json=payload, timeout=30)
        if not r.ok:
            raise RuntimeError(f"GitHub kayıt hatası: {r.status_code} {r.text[:300]}")
        return r.json()


def load_source(store):
    if store.ok:
        try:
            txt, _ = store.get()
            if txt and txt.strip():
                return txt, "GitHub"
        except Exception as e:
            st.warning(f"GitHub okunamadı; yerel veri açıldı. {e}")
    if LOCAL_DATA.exists():
        return LOCAL_DATA.read_text(encoding="utf-8"), "Yerel"
    return "", "Boş"


def parse_numbers(s):
    s = s.replace("-", " ").replace(",", " ").replace(";", " ")
    vals = [int(x) for x in s.split() if x.strip()]
    return vals


def fmt_coupon(c):
    return "  ".join(f"{int(n):02d}" for n in c)

store = GitHubStore()
if "data_text" not in st.session_state:
    txt, src = load_source(store)
    st.session_state.data_text = txt
    st.session_state.data_source = src

try:
    df = load_txt_text(st.session_state.data_text)
except Exception as e:
    st.error(f"Veri dosyası okunamadı: {e}")
    st.stop()

st.title("🎯 Hızlı On — Canlı Kupon Üretici V5")
st.caption("İlk 3 + ikinci 3 çekilişten sonra canlı havuz; her yeni sonuçla :32 → :37 → :42 → :47 → :52 → :57 yeniden hesaplanır.")

with st.sidebar:
    st.subheader("Durum")
    st.write(f"Veri: **{st.session_state.data_source}**")
    st.write(f"Toplam çekiliş: **{len(df):,}**")
    if not df.empty:
        st.write(f"Son kayıt: **{df['dt'].max().strftime('%d.%m.%Y %H:%M')}**")
    if store.ok:
        st.success("GitHub kalıcı kayıt: AÇIK")
        st.caption(f"{store.repo} / {store.path}")
    else:
        st.warning("GitHub kalıcı kayıt ayarlı değil")
    if st.button("GitHub'dan yeniden yükle", use_container_width=True, disabled=not store.ok):
        try:
            txt, _ = store.get()
            if txt:
                st.session_state.data_text = txt
                st.session_state.data_source = "GitHub"
                st.rerun()
        except Exception as e:
            st.error(str(e))

live_tab, add_tab, hour_tab, setup_tab = st.tabs(["⚡ Canlı Kupon", "➕ Çekiliş Ekle", "🔬 Saat Analizi", "⚙️ GitHub"])

with live_tab:
    if df.empty:
        st.info("Önce veri yükleyin veya çekiliş ekleyin.")
    else:
        dates = sorted(df["date"].unique(), reverse=True)
        c1, c2, c3 = st.columns([1.2, 1, 1])
        selected_date = c1.selectbox("Canlı gün", dates, format_func=lambda x: x.strftime("%d.%m.%Y"))
        day_hours = sorted(df.loc[df["date"] == selected_date, "hour"].unique().astype(int), reverse=True)
        selected_hour = c2.selectbox("Saat", day_hours)
        coupon_size = c3.selectbox("Kupon boyutu", [6, 5, 7, 4], index=0)

        try:
            a = live_analysis(df, selected_date, int(selected_hour), coupon_size=coupon_size, nvar=5)
            obs = a["obs_count"]
            target = a["target_min"]
            m1, m2, m3 = st.columns(3)
            m1.metric("Gelen çekiliş", f"{obs}/12")
            m2.metric("İlk yarı", f"{min(obs,6)}/6")
            m3.metric("Sonraki hedef", "Saat tamam" if target is None else f"{selected_hour:02d}:{target:02d}")

            if obs < 6:
                st.info(f"Kupon üretimi ilk 6 çekiliş tamamlanınca başlar. **{6-obs} çekiliş daha gerekli.**")
            elif obs >= 12:
                st.success("Bu saat tamamlandı. Sonraki saatin ilk 6 çekilişini bekliyoruz.")
            else:
                ranked = a["ranked"]
                st.subheader(f"Hedef {selected_hour:02d}:{target:02d} — Canlı Kuponlar")
                cols = st.columns(5)
                for i, cp in enumerate(a["coupons"]):
                    with cols[i]:
                        st.markdown(f"**Kupon {i+1}**")
                        st.code(fmt_coupon(cp), language=None)
                if coupon_size != 6:
                    st.caption("Not: 6'lı portföy V4.1 kör testinde doğrulanan yapı; diğer boyutlar aynı canlı skordan türetilen deneysel portföydür.")

                st.subheader("Canlı havuz — erken/geç aktivasyon")
                top = ranked.head(20).copy()
                view = top[["Sayi","DurumTR","Ilk3","Ikinci3","Sonrasi","ToplamGorulme","SonBosluk","P_Next","P_KalanSaat","P_Final4","P_Final5","Skor"]].copy()
                for c in ["P_Next","P_KalanSaat","P_Final4","P_Final5"]:
                    view[c] = (view[c] * 100).round(1)
                view["Skor"] = view["Skor"].round(4)
                view.columns = ["Sayı","Durum","İlk3","İkinci3","6 sonrası","Toplam","Boşluk","Sonraki %","Kalan saat %","4+ %","5+ %","Skor"]
                st.dataframe(view, use_container_width=True, hide_index=True)

                st.subheader("Durum havuzları")
                states = ["ERKEN_DEVAM","GEC_YUKSELIS","ERKEN_SONEN","SONRADAN_GIREN","HALA_YOK"]
                scols = st.columns(len(states))
                for col, state in zip(scols, states):
                    nums = ranked.loc[ranked["Durum"] == state].head(10)["Sayi"].astype(int).tolist()
                    with col:
                        st.markdown(f"**{STATE_TR[state]}**")
                        st.write("-".join(map(str, nums)) if nums else "—")
        except Exception as e:
            st.error(str(e))

with add_tab:
    st.subheader("Yeni çekilişi ekle")
    latest_dt = df["dt"].max().to_pydatetime() if not df.empty else datetime.now()
    with st.form("add_draw", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Tarih", value=latest_dt.date())
        h = c2.number_input("Saat", min_value=0, max_value=23, value=int(latest_dt.hour), step=1)
        minute = c3.selectbox("Dakika", EXPECTED_MINUTES)
        draw_id = st.number_input("Çekiliş no", min_value=1, step=1, value=int(df["draw_id"].max()+1) if not df.empty else 1)
        nums_text = st.text_area("20 sayı", placeholder="Örn: 2 7 10 17 ...", height=110)
        auto_push = st.checkbox("Ekleyince GitHub'a kalıcı kaydet", value=True, disabled=not store.ok)
        submitted = st.form_submit_button("Çekilişi ekle", use_container_width=True)
    if submitted:
        try:
            nums = parse_numbers(nums_text)
            dt = datetime(d.year, d.month, d.day, int(h), int(minute))
            new_df = append_draw(df, int(draw_id), dt, nums)
            new_text = dataframe_to_txt(new_df)
            LOCAL_DATA.write_text(new_text, encoding="utf-8")
            if auto_push and store.ok:
                store.put(new_text, f"Canlı çekiliş {int(draw_id)} - {dt.strftime('%d.%m.%Y %H:%M')}")
                src = "GitHub"
            else:
                src = "Yerel"
            st.session_state.data_text = new_text
            st.session_state.data_source = src
            st.success("Çekiliş kaydedildi. Canlı havuz güncellendi.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

with hour_tab:
    if not df.empty:
        dates = sorted(df["date"].unique(), reverse=True)
        c1, c2 = st.columns(2)
        hd = c1.selectbox("Analiz günü", dates, format_func=lambda x: x.strftime("%d.%m.%Y"), key="hd")
        hrs = sorted(df.loc[df["date"] == hd, "hour"].unique().astype(int))
        hh = c2.selectbox("Analiz saati", hrs, key="hh")
        phase = historical_phase_table(df, hd, int(hh))
        st.caption("İlk3 + ikinci3 + ikinci yarı gerçek aktivasyonlarını aynı tabloda gösterir.")
        f1, f2, f3 = st.columns(3)
        f1.metric("İlk 6'da 2+ olan", int((phase["Ilk6"] >= 2).sum()))
        f2.metric("İlk 6'da hiç çıkmayan", int((phase["Ilk6"] == 0).sum()))
        f3.metric("İlk 6'da yokken ikinci yarıda giren", int(((phase["Ilk6"] == 0) & (phase["IkinciYari"] > 0)).sum()))
        phase = phase.rename(columns={"Sayi":"Sayı","Ilk3":"İlk3","Ikinci3":"İkinci3","Ilk6":"İlk6","IkinciYari":"İkinci yarı","SaatToplam":"Saat toplam"})
        st.dataframe(phase.sort_values(["Saat toplam","İkinci yarı"], ascending=False), use_container_width=True, hide_index=True)

with setup_tab:
    st.subheader("GitHub kalıcı kayıt")
    if store.ok:
        st.success("Bağlantı ayarlı. Her canlı çekiliş doğrudan veri dosyasına commit edilebilir.")
    else:
        st.info("Streamlit Cloud → App settings → Secrets bölümüne aşağıdaki 4 anahtarı ekleyin. Token'ı GitHub dosyasına yazmayın.")
    st.code('''GITHUB_TOKEN = "github_pat_..."
GITHUB_REPO = "kullanici/repo"
GITHUB_BRANCH = "main"
GITHUB_DATA_PATH = "veri.txt"''', language="toml")
    st.caption("Token için repository Contents read/write izni gerekir.")
