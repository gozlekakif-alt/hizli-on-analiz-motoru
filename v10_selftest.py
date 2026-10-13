"""V10: only stdlib; execute selected pure functions from AST for deterministic smoke tests."""
import ast
import csv
import io
import json
import re
from datetime import datetime, date, time, timedelta
from collections import Counter, defaultdict

src=open("v10_app.py",encoding="utf-8").read()
ast.parse(src)
names={"pos_of","moment","next_slot_after","next_recorded_slot","next_paste_template",
       "normalize_numbers","make_draw","parse_draw_line","parse_pasted_draws","filter_new_draws","parse_history",
       "merge_draws_into_txt","persist_to_github_veri_txt","load_family_csv","train_profiles",
       "gap_rhythm","gap_class","family_rhythm_report","repeat_gap_targets",
       "active_signals","daily_chains","make_ticket","result_rows","day_signal_replay",
       "cross_day_rhythm_report","cross_day_intraday_report","cross_day_repeat_families"}
tree=ast.parse(src)
nodes=[]
for node in tree.body:
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
        node.decorator_list=[]
        nodes.append(node)
module=ast.Module(body=nodes,type_ignores=[])
ast.fix_missing_locations(module)
env={"datetime":datetime,"date":date,"time":time,"timedelta":timedelta,
     "Counter":Counter,"defaultdict":defaultdict,"csv":csv,"io":io,"json":json,"re":re}
exec(compile(module,"v10_pure", "exec"),env,env)

p=env["pos_of"]
m=env["moment"]
assert p(datetime(2026,10,12,0,2))==1
assert p(datetime(2026,10,12,1,2))==13
assert p(datetime(2026,10,12,7,2))==14
assert p(datetime(2026,10,12,23,57))==217
assert p(datetime(2026,10,12,3,2)) is None
for x in range(1,218):
    assert p(m("2026-10-12",x))==x
try:
    env["normalize_numbers"]([1]*20)
    raise AssertionError("duplicate not rejected")
except ValueError:
    pass

def make(day,pos,ident,extras=()):
    nums=list(range(1,21))
    return env["make_draw"](ident,m(day,pos),nums)
d1=make("2026-10-08",10,111)
d2=make("2026-10-08",15,112)
d3=make("2026-10-10",10,113)
d4=make("2026-10-10",15,114)
new=make("2026-10-12",10,115)
past=[d1,d2,d3,d4]
labels=["01-02-03-04-05"]
profile=env["train_profiles"](json.dumps(past),json.dumps(labels))
assert profile[labels[0]]["first"][5]==2, profile
assert profile[labels[0]]["pair"][5]==2
families={labels[0]:{"nums":(1,2,3,4,5),"mask":sum(1 << (x-1) for x in range(1,6)),"k":5}}
targets,hits=env["active_signals"](
    past+[new],families,profile,"2026-10-12",m("2026-10-12",11))
assert len(targets)==1, targets
assert targets[0]["pos"]==15 and targets[0]["level"]==2, targets
coupon=env["make_ticket"](targets[0],past+[new],size=10)
assert len(coupon)==10 and len(set(coupon))==10 and set(range(1,6)).issubset(coupon)
ticket={"day":"2026-10-12","pos":15,"time":"00:??","family":labels[0],
        "numbers":coupon,"kind":"test"}
results=env["result_rows"]([ticket],past+[new])
assert results[0]["Sonuc"]=="Bekleniyor",results
results=env["result_rows"]([ticket],past+[new,make("2026-10-12",15,116)])
assert results[0]["Sonuc"]=="10/10",results

ten="01-02-03-04-05-06-07-08-09-10"
tenprof={ten:{"days":["2026-09-08","2026-09-10","2026-09-12"]}}
tenfam={ten:{"k":10}}
days=env["daily_chains"](tenprof,tenfam,"2026-09-14")
assert any(r["Hedef gun"]=="2026-09-14" and r["Ardisik gun"]>=3 for r in days),days

assert env["parse_history"]("123;12.10.2026 00:02;"+",".join(map(str,range(1,21))))[0][0]["pos"]==1
csv_text="Aile;Boyut;Aktif_Gun\n01-02-03-04-05;5;3\n"
assert len(env["load_family_csv"](csv_text))==1

# Official pasted user example: accept heading + date/time + 20 vertical numbers.
paste="Çekiliş no:61629\n12.10.2026-00:02\n5\n6\n11\n22\n23\n30\n31\n32\n35\n39\n41\n43\n47\n54\n55\n57\n59\n62\n74\n75"
found,issues=env["parse_pasted_draws"](paste)
assert len(found)==1 and not issues,(found,issues)
assert found[0]["no"]==61629 and found[0]["pos"]==1 and len(found[0]["nums"])==20

for k in range(5,11):
    fake_signal={"label":"-".join(f"{n:02d}" for n in range(1,k+1)),
                 "moment":m("2026-10-12",15).isoformat(timespec="minutes")}
    k_ticket=env["make_ticket"](fake_signal,past+[new],size=k)
    assert len(k_ticket)==k and set(range(1,k+1)).issubset(k_ticket),k_ticket
    fake_record={"day":"2026-10-12","pos":15,"time":"00:??","family":fake_signal["label"],
                 "numbers":k_ticket,"kind":"test"}
    record=env["result_rows"]([fake_record],past+[new,make("2026-10-12",15,116)])[0]
    assert record["Sonuc"]==f"{k}/{k}" and record["Boyut"]==k,record


# Calendar: 01:02 leads to 07:02 on the SAME day; 23:57 leads to 00:02 next day.
x=env["next_recorded_slot"]([make("2026-10-11",217,61628)])
assert x["no"]==61629 and x["date"]=="2026-10-12" and x["time"]=="00:02",x
x=env["next_recorded_slot"]([make("2026-10-12",13,61641)])
assert x["date"]=="2026-10-12" and x["time"]=="07:02",x
template=env["next_paste_template"]([make("2026-10-11",217,61628)])
assert "Çekiliş no:61629" in template and "12.10.2026-00:02" in template,template

# Preserve every old line and reject both same-number and same-slot mismatches.
raw=("===== preserved V9 header =====\n"
     +"61628;11.10.2026 23:57;"+",".join(map(str,range(1,21)))+"\n")
new_record=make("2026-10-12",1,61629)
merged,count,duplicates=env["merge_draws_into_txt"](raw,[new_record])
assert merged.startswith(raw) and count==1 and duplicates==0, (count,duplicates)
assert merged.endswith("61629;12.10.2026 00:02;"+",".join(map(str,range(1,21)))+"\n")
again,count,duplicates=env["merge_draws_into_txt"](merged,[new_record])
assert again==merged and count==0 and duplicates==1
different=dict(new_record)
different["nums"]=list(range(2,22))
try:
    env["merge_draws_into_txt"](merged,[different])
    raise AssertionError("conflicting draw not rejected")
except ValueError:
    pass
different_slot=dict(new_record)
different_slot["no"]=61630
try:
    env["merge_draws_into_txt"](merged,[different_slot])
    raise AssertionError("conflicting slot not rejected")
except ValueError:
    pass

# Mock large GitHub contents API: >1MB reports no inline content; the blob endpoint is required.
import base64
from types import SimpleNamespace
class FakeResponse:
    def __init__(self,data,status=200):
        self._data=data
        self.status_code=status
    def json(self):
        return self._data
    def raise_for_status(self):
        if not 200<=self.status_code<300:
            raise AssertionError("HTTP "+str(self.status_code))

class FakeRequests:
    def __init__(self,base_text):
        self.base_text=base_text
        self.last_put=None
        self.blob_called=False
    def get(self,url,**kwargs):
        if "/git/blobs/" in url:
            self.blob_called=True
            return FakeResponse({"encoding":"base64",
                      "content":base64.b64encode(self.base_text.encode("utf-8")).decode("ascii")})
        return FakeResponse({"sha":"example_sha","encoding":"none","content":""})
    def put(self,url,**kwargs):
        self.last_put=kwargs["json"]
        return FakeResponse({"content":{"sha":"new-sha"}})

fake=FakeRequests(raw)
env["requests"]=fake
env["base64"]=base64
env["REPO"]="test/example-repo"
env["secret_token"]=lambda:"test-token-never-commit"
env["secret_admin_pin"]=lambda:"test-pin"
env["st"]=SimpleNamespace(session_state={"v10_admin_unlocked":True})
env["github_text"]=SimpleNamespace(clear=lambda:None)
ok,added,message=env["persist_to_github_veri_txt"]([new_record])
assert ok and added==1 and fake.blob_called,(ok,added,message)
assert base64.b64decode(fake.last_put["content"]).decode("utf-8")==merged
assert fake.last_put["sha"]=="example_sha"


# Exact duplicate within pasted batch is skipped; conflicting IDs or slots are rejected.
baseline=make("2026-10-12",1,61629)
new=make("2026-10-12",2,61630)
conflicting_id=dict(baseline,nums=list(range(2,22)))
conflicting_slot=dict(baseline,no=61631)
accepted,repeats,problems=env["filter_new_draws"](
    [baseline,new,new,conflicting_id,conflicting_slot],[baseline])
assert len(accepted)==1 and accepted[0]["no"]==61630,accepted
assert repeats==2,repeats
assert len(problems)==2,problems
# A malformed draw must not silently enter a bulk file.
bad_draw=dict(new,nums=[1]*20)
accepted,repeats,problems=env["filter_new_draws"]([new,bad_draw],[])
assert len(accepted)==1 and len(problems)==1
# End-to-end: merge accepted records into original without replacing old records.
updated,n_new,n_rep=env["merge_draws_into_txt"](raw,[baseline,new])
assert n_new==2 and n_rep==0
repeat_again,n_new,n_rep=env["merge_draws_into_txt"](updated,[baseline,new])
assert repeat_again==updated and n_new==0 and n_rep==2


# Rhythm classifications: same, increasing and decreasing precise observed gaps.
assert env["gap_rhythm"]([3,3])=="SABİT +3"
assert env["gap_class"]([4,5,7])=="Artan"
assert env["gap_class"]([7,5,4])=="Azalan"
assert env["gap_class"]([4,6,4])=="Değişken"

# Historical 3x/4x 5-number family: two older independent days with +5.
family="01-02-03-04-05"
fmeta={family:{"k":5,"nums":tuple(range(1,6)),"mask":sum(1<<(x-1) for x in range(1,6))}}
historic=[]
for day,first_id in [("2026-10-08",10000),("2026-10-10",10500)]:
    historic.extend(make(day,pos,first_id+j) for j,pos in enumerate((10,15,20,25)))
past_profiles=env["train_profiles"](json.dumps(historic),json.dumps([family]))
assert past_profiles[family]["first"][5]==2
assert past_profiles[family]["triple"][(5,5)]==2
assert past_profiles[family]["quad"][(5,5,5)]==2
today_day="2026-10-12"
for n,pos,target,step in [(1,10,15,"1→2"),(2,15,20,"2→3"),(3,20,25,"3→4")]:
    live=[make(today_day,p,61628+p) for p in (10,15,20)[:n]]
    hits={family:live}
    targets=env["repeat_gap_targets"](
        hits,past_profiles,fmeta,today_day,env["moment"](today_day,pos),
        {d["pos"] for d in live},minimum_days=2,latest_known=live[-1])
    assert len(targets)==1 and targets[0]["stage"]==step and targets[0]["pos"]==target,targets
    assert targets[0]["support"]==2
    assert targets[0]["estimated_no"]==live[-1]["no"]+(target-pos),targets



# Historical fixed day-gap labels and across-day repeated within-day first gaps.
fA="01-02-03-04-05"
fB="06-07-08-09-10"
fake_meta={
    fA:{"k":5},fB:{"k":5}
}
fixture={
    fA:{"days":["2026-10-01","2026-10-03","2026-10-05"],
        "first":{5:2},"triple":{(5,5):2},"quad":{}},
    fB:{"days":["2026-10-01","2026-10-04","2026-10-09"],
        "first":{4:1},"triple":{},"quad":{}}
}
dr=env["cross_day_rhythm_report"](fixture,fake_meta)
assert len(dr)==1 and dr[0]["Aile"]==fA and dr[0]["Ritim"]=="+2 gün",dr
assert dr[0]["Ritimli gün"]==3 and dr[0]["Devam etse tarih"]=="2026-10-07"
assert env["cross_day_repeat_families"](fixture,fake_meta,2)=={fA}
intra=env["cross_day_intraday_report"](fixture,fake_meta,2)
assert len(intra)==2 and {r["Aşama"] for r in intra}=={"1→2","2→3"},intra
# No look-ahead: a second interval completed on the target day does not light up.
pre={"days":["2026-10-01","2026-10-03"],"first":{},"triple":{},"quad":{}}
assert not env["cross_day_rhythm_report"]({fA:pre},fake_meta)
assert not env["cross_day_repeat_families"]({fA:pre},fake_meta,2)

# Historical ledger: earlier-day support and time-frozen targets, evaluated later.
hist_ledger=historic+[make(today_day,10,61651),make(today_day,15,61652)]
ledger=env["day_signal_replay"](
    {family:hist_ledger[-2:]},past_profiles,fmeta,today_day,
    hist_ledger[-2:],minimum_days=2)
assert len(ledger)==2,ledger
l12=[r for r in ledger if r["Aşama"]=="1→2"]
l23=[r for r in ledger if r["Aşama"]=="2→3"]
assert len(l12)==len(l23)==1,ledger
assert l12[0]["Hedef sıra"]==15 and l12[0]["Sonuç"]=="TAM" and l12[0]["İsabet"]=="5/5",ledger
assert l23[0]["Hedef sıra"]==20 and l23[0]["Sonuç"].startswith("Bekliyor"),ledger
assert not env["day_signal_replay"](
    {family:hist_ledger[-2:]},env["train_profiles"](json.dumps(historic[:4]),json.dumps([family])),
    fmeta,today_day,hist_ledger[-2:],minimum_days=2)
ledger2=env["day_signal_replay"](
    {family:hist_ledger[-2:]},past_profiles,fmeta,today_day,
    hist_ledger[-2:]+[make(today_day,20,61653)],minimum_days=2)
assert any(r["Aşama"]=="2→3" and r["Sonuç"]=="TAM" for r in ledger2)

# On prior-day data only, a single historical supporting day is experimental.
one_day=env["train_profiles"](json.dumps(historic[:4]),json.dumps([family]))
live=[make(today_day,10,61700)]
assert not env["repeat_gap_targets"]({family:live},one_day,fmeta,today_day,
                                     env["moment"](today_day,10),{10},minimum_days=2)
experimental=env["repeat_gap_targets"]({family:live},one_day,fmeta,today_day,
                                       env["moment"](today_day,10),{10},minimum_days=1)
assert experimental and experimental[0]["support"]==1
assert not env["repeat_gap_targets"]({family:live},past_profiles,fmeta,today_day,
                                     env["moment"](today_day,16),{10,15},minimum_days=2)

# Increasing 2→3 then 3→4 gap patterns may not be constant.
increase_history=[]
for day,first_id in [("2026-10-08",20000),("2026-10-10",21000)]:
    increase_history.extend(make(day,p,first_id+i) for i,p in enumerate((10,14,19,25)))
increase_profile=env["train_profiles"](json.dumps(increase_history),json.dumps([family]))
inc_live=[make(today_day,10,61000),make(today_day,14,61001)]
inc=env["repeat_gap_targets"]({family:inc_live},increase_profile,fmeta,today_day,
                              env["moment"](today_day,14),{10,14},minimum_days=2)
assert len(inc)==1 and inc[0]["pos"]==19 and inc[0]["kind"].startswith("ARTAN"),inc
inc_live.append(make(today_day,19,61002))
inc4=env["repeat_gap_targets"]({family:inc_live},increase_profile,fmeta,today_day,
                               env["moment"](today_day,19),{10,14,19},minimum_days=2)
assert len(inc4)==1 and inc4[0]["pos"]==25 and inc4[0]["kind"].startswith("ARTAN"),inc4

# Cross-day chronology, exact draw numbers, first time on selected day.
fake_family_events=historic+[make(today_day,10,61651),make(today_day,15,61652)]
rows,individual=env["family_rhythm_report"](
    fake_family_events,fmeta,{family:fake_family_events[-2:]},today_day)
assert len(rows)==1 and len(individual)==10, (rows,individual)
assert rows[0]["Bugün ritim"]=="İKİLİ +5"
assert rows[0]["Geçmişte 3+ gün"]==2 and rows[0]["Geçmişte 4+ gün"]==2
assert rows[0]["Durum"]=="GEÇMİŞTEN GELDİ"
assert rows[0]["Günler arası"]=="SABİT +2"
assert rows[0]["+2 gün"]==2
assert "#61651 10:??" not in rows[0]["Bugün çekilişler"]
assert "#61651 00:??" not in rows[0]["Bugün çekilişler"]


# Separate A->B / A->B->C evidence tests: strict earlier-day training.
from v10_sira import (family_order_events, family_order_patterns,
                      family_order_matches, family_order_targets)
A="-".join(f"{x:02d}" for x in range(1,6))
B="-".join(f"{x:02d}" for x in range(6,11))
C="-".join(f"{x:02d}" for x in range(11,16))
order_labels=[A,B,C]
def order_draw(day,pos,ident,label):
    prefix=[int(n) for n in label.split("-")]
    # The fillers exclude the other two families.
    return env["make_draw"](ident,m(day,pos),prefix+list(range(30,45)))
training=[]
for day,first_id in (("2026-10-08",1000),("2026-10-10",2000)):
    training.extend([order_draw(day,10,first_id,A),
                     order_draw(day,13,first_id+1,B),
                     order_draw(day,18,first_id+2,C)])
live=[order_draw("2026-10-12",10,3000,A),order_draw("2026-10-12",13,3001,B)]
order_events=family_order_events(training+live,order_labels,"2026-10-12")
pairs,triples=family_order_patterns(order_events,"2026-10-12",max_gap=12,min_days=2)
assert any(r["A"]==A and r["B"]==B and r["Fark"]==3 and r["Destek gün"]==2
           for r in pairs),pairs
assert any(r["A"]==A and r["B"]==B and r["C"]==C
           and r["Fark 1"]==3 and r["Fark 2"]==5
           and r["Destek gün"]==2 for r in triples),triples
assert not family_order_patterns(order_events,"2026-10-12",12,3)[0]
matches=family_order_matches(order_events,"2026-10-12",pairs,triples)
assert any(r["Zincir"]=="A→B" for r in matches)
targets=family_order_targets(order_events,"2026-10-12",pairs,triples,
                             m("2026-10-12",13),m)
assert any(r["Aile"]==C and r["Aşama"]=="A→B→C" and
           r["Hedef sıra"]==18 for r in targets),targets
assert not family_order_targets(order_events,"2026-10-12",pairs,triples,
                                m("2026-10-12",19),m)
order_events_complete=family_order_events(
    training+live+[order_draw("2026-10-12",18,3002,C)],
    order_labels,"2026-10-12")
assert not any(r["Hedef sıra"]==18 for r in family_order_targets(
    order_events_complete,"2026-10-12",pairs,triples,m("2026-10-12",13),m))
matches=family_order_matches(order_events_complete,"2026-10-12",pairs,triples)
assert any(r["Zincir"]=="A→B→C" for r in matches)
# A and B on the same draw is not chronological evidence.
same_only=order_draw("2026-10-08",10,9000,A)
same_only["nums"]=list(range(1,21))
e=family_order_events([same_only],order_labels,"2026-10-09")
assert not family_order_patterns(e,"2026-10-09",12,1)[0]

print("PASS: V10 rhythms, repeat stages, families, and paste, family targets, calendar, safe veri.txt append, >1MB blob GitHub API")
