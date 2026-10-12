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
       "normalize_numbers","make_draw","parse_draw_line","parse_pasted_draws","parse_history",
       "merge_draws_into_txt","persist_to_github_veri_txt","load_family_csv","train_profiles",
       "active_signals","daily_chains","make_ticket","result_rows"}
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
env["secret_token"]=lambda:"test-token-never-commit"
env["secret_admin_pin"]=lambda:"test-pin"
env["st"]=SimpleNamespace(session_state={"v10_admin_unlocked":True})
env["github_text"]=SimpleNamespace(clear=lambda:None)
ok,added,message=env["persist_to_github_veri_txt"]([new_record])
assert ok and added==1 and fake.blob_called,(ok,added,message)
assert base64.b64decode(fake.last_put["content"]).decode("utf-8")==merged
assert fake.last_put["sha"]=="example_sha"

print("PASS: V10 paste, family targets, calendar, safe veri.txt append, >1MB blob GitHub API")
