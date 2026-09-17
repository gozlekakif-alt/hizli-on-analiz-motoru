import streamlit as st
# GeçmişFrekans sıcaklık bölümü kaldırıldı.


st.markdown("## ⚡ CANLI KULLANIM")
st.caption(f"Son kayıt: #{int(df.iloc[-1]["draw"])} · {df.iloc[-1]["dt"].strftime('%d.%m.%Y %H:%M')} · Toplam {N} çekiliş")

st.markdown(f"## 🎯 Sıradaki çekiliş #{int(df.iloc[-1]["draw"])+1}")

st.markdown("### 🧠 OYUN KARAKTERİ → REAL20")
order=character20["sıralama"]
st.markdown("**Yoğunlaşma sırası:** "+" → ".join(
    f"{k} ({character20['koltuk'][k]})" for k in order))
st.markdown("### 🎯 REAL20 aday havuzu")
st.markdown("## "+" · ".join(map(str,real20)))
st.caption("Koltuklar sabit değildir. Her elde geçmiş tecrübe, PRE-H karakteri, aktif motorlar ve aile yapısı kaynakların payını yeniden belirler.")

# Her aday nereden geldi?
trace=real20_df[["Sayı","Ana_neden","Nedenler","Kaynak","H_yaşı","GeçmişFrekans","REAL20_skor"]].copy()
trace["Nereden geldi"]=trace["Nedenler"].apply(lambda x:" + ".join(x))
trace=trace[["Sayı","Ana_neden","Nereden geldi","Kaynak","H_yaşı","GeçmişFrekans","REAL20_skor"]]
st.dataframe(trace,use_container_width=True,hide_index=True)

st.markdown("### 🎟️ Kuponlar")
a,b,c=st.columns(3)
with a:
    st.info("4'LÜ A")
    st.markdown("## "+" — ".join(map(str,coupon4a)))
with b:
    st.warning("4'LÜ B")
    st.markdown("## "+" — ".join(map(str,coupon4b)))
with c:
    st.success("5'Lİ ANA")
    st.markdown("## "+" — ".join(map(str,coupon5)))

# Kupon sayı kaynaklarını kısa göster.
st.caption("4A: "+" | ".join(f"{n}({reason_map.get(n,'?')})" for n in coupon4a))
if diag.get('v8',{}).get('sniper_on'): st.success("🎯 4L-A1 güçlü rejim tetiklendi: 4A Sniper modunda.")
st.caption("4B: "+" | ".join(f"{n}({reason_map.get(n,'?')})" for n in coupon4b))
st.caption("5'li: "+" | ".join(f"{n}({reason_map.get(n,'?')})" for n in coupon5))

target=int(df.iloc[-1]["draw"])+1
if st.button(f"🔒 #{target} KUPONLARINI DONDUR",type="primary",use_container_width=True):
    save_coupon_pack(target,coupon4a,coupon4b,coupon5,diag)
    st.success(f"#{target} için 4A + 4B + 5'li kalıcı donduruldu.")

packs=check_coupon_packs()
if not packs.empty:
    st.markdown("### 📊 Kolon değerlendirmesi")
    q=packs.copy()
    q["4A"]=q.apply(lambda r:"-" if not bool(r["checked"]) else f"{int(r['hit4_a'])}/4",axis=1)
    q["4B"]=q.apply(lambda r:"-" if not bool(r["checked"]) else f"{int(r['hit4_b'])}/4",axis=1)
    q["5L"]=q.apply(lambda r:"-" if not bool(r["checked"]) else f"{int(r['hit5'])}/5",axis=1)

    # En son sonucu telefonda büyük ve doğrudan göster.
    checked=q[q["checked"].astype(bool)].copy()
    if not checked.empty:
        last=checked.iloc[-1]
        st.markdown(f"#### ✅ #{int(last['target_draw'])} sonucu")
        r1,r2,r3=st.columns(3)
        r1.metric("4'LÜ A", f"{int(last['hit4_a'])}/4")
        r2.metric("4'LÜ B", f"{int(last['hit4_b'])}/4")
        r3.metric("5'Lİ ANA", f"{int(last['hit5'])}/5")

    q=q.rename(columns={"target_draw":"Çekiliş","coupon4_a":"4'lü A kolon","coupon4_b":"4'lü B kolon","coupon5":"5'li ANA kolon"})
    st.dataframe(q[["Çekiliş","4'lü A kolon","4A","4'lü B kolon","4B","5'li ANA kolon","5L"]],
                 use_container_width=True,hide_index=True)

# Son 10 sıcak hafıza kullanıcı isteğiyle kaldırıldı.

st.markdown("**Sıcak 20:** "+" · ".join(map(str,hot20["Sayı"].astype(int).tolist())))
with st.expander("Son 10 çekiliş + sıcaklık detayını aç"):
    last10=df.tail(10)[["draw","dt","nums"]].copy()
    last10["dt"]=last10["dt"].dt.strftime("%d.%m.%Y %H:%M")
    last10["nums"]=last10["nums"].apply(lambda x:" - ".join(map(str,x)))
    st.dataframe(last10,use_container_width=True,hide_index=True)
    st.dataframe(hot10.head(30),use_container_width=True,hide_index=True)

with st.expander("🔬 Teknik motor detayları"):
    st.write("Dinamik karakter kararı:",character20)
    st.write("PRE-H kaynak arzı:",diag["supply"])
    st.write("Karakter/rejim:",diag["regime"])
    st.write("H1 modu:",diag["h1_mode"])
    st.write("MID:",diag["mid_types"],"LONG gate:",diag["long_gate"],"DEEP:",diag["deep_exists"])
    st.dataframe(tab.sort_values("Final_skor",ascending=False),use_container_width=True,hide_index=True)

st.caption("Tarihsel örüntü araştırmasıdır; rastgele çekilişlerde kesin kazanç garantisi vermez.")
