"""V10 independent integration test against the actual repo's entire veri.txt (stdlib only)."""
import ast,csv,io,json,re
from datetime import date,datetime,time,timedelta
from collections import Counter,defaultdict
src=open("v10_app.py",encoding="utf-8").read()
names={"pos_of","moment","normalize_numbers","make_draw","parse_draw_line","parse_history",
       "load_family_csv","gap_rhythm","gap_class","family_rhythm_report","repeat_gap_targets",
       "train_profiles"}
nodes=[]
for node in ast.parse(src).body:
    if isinstance(node,ast.FunctionDef) and node.name in names:
        node.decorator_list=[]
        nodes.append(node)
module=ast.Module(body=nodes,type_ignores=[])
ast.fix_missing_locations(module)
env={"date":date,"datetime":datetime,"time":time,"timedelta":timedelta,
     "Counter":Counter,"defaultdict":defaultdict,"csv":csv,"io":io,"json":json,"re":re}
exec(compile(module,"v10_app.py","exec"),env,env)
raw=open("veri.txt",encoding="utf-8-sig").read()
history,errors=env["parse_history"](raw)
families=env["load_family_csv"](open("v10_aileler.csv",encoding="utf-8-sig").read())
assert len(history)>15000,len(history)
assert len(families)==1131,len(families)
sample_date="2026-10-11"
day=[d for d in history if d["day"]==sample_date]
assert len(day)==217,len(day)
hits=defaultdict(list)
for d in day:
    m=sum(1<<(n-1) for n in d["nums"])
    for label,fam in families.items():
        if m & fam["mask"]==fam["mask"]:
            hits[label].append(d)
assert len(hits)==67,len(hits)
summary,events=env["family_rhythm_report"](history,families,hits,sample_date)
assert len(summary)==len(hits)==67
assert len(events)>=67
assert all(r["Bugün kaç kez"]==len(hits[r["Aile"]]) for r in summary)
assert any(r["Bugün kaç kez"]>=3 for r in summary)
assert all(r["Durum"] in ("İLK KEZ (veride)","GEÇMİŞTEN GELDİ") for r in summary)
assert all(e["Çekiliş"]>0 and e["Saat"] for e in events)
sizes=Counter(r["Boyut"] for r in summary)
print("PASS actual 11 Oct: 217 drawings; 67 distinct exact families")
print("Counts by size: "+str(dict(sorted(sizes.items()))))
print("Triple families on day: "+str(sum(r["Bugün kaç kez"]>=3 for r in summary)))
print("Total historical appearances for selected families: "+str(len(events)))
