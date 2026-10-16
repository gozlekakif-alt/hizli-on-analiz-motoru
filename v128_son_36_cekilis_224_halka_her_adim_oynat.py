#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V128: explicit FORWARD HISTORICAL REPLAY of 36 observed real Hızlı On draws.

Freeze all 224×80 nested ring states before the first replay draw,
then feed exactly ONE real draw at a time. Store state before & after,
outgoing oldest draw bit per ring, +1/0/-1 count changes, rank and pool,
all 5x5 class flows, 36-step/224 ring summaries, 36-step/80 ball summaries,
full 645,120 draw-ring-ball audit as compressed CSV, and a self-contained
HTML timeline viewer. Only data present in repo veri.txt is used. No
claim of future draw prediction; last 36 known draws are the "future"
relative to the initial replay baseline, not future relative to today.

Can select 24 or 36 (default 36); 36 archive permits filtering to last 24.
Requires numpy, v100c_yuruyen_672_fifo_sabit_12_halka.load.
"""
from __future__ import annotations
import argparse,base64,csv,gzip,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

LENS=np.arange(12,2689,12,dtype=np.int32)
N_RING=224
N_NUM=80
POOL_NAMES=("SOGUK","SERIN","NOTR","ILIK","SICAK")
assert len(LENS)==N_RING
RING_LABELS=(1,2,3,6,12,24,36,48,56,72,96,112,128,144,168,192,224)

def ranks_pools(cnt):
    assert cnt.shape==(224,80)
    order=np.argsort(cnt,axis=1,kind="stable")
    rk=np.empty((224,80),dtype=np.uint8)
    rk[np.arange(224)[:,None],order]=np.arange(80,dtype=np.uint8)
    pool=rk//16
    assert np.all(np.bincount(pool.ravel(),minlength=5)==224*16)
    return rk,pool

def csv_write(z,p,records,gunzip=False):
    if not records:return
    if gunzip:
        b=io.BytesIO()
        with gzip.GzipFile(fileobj=b,mode="wb",mtime=0,compresslevel=8) as gz:
            out=io.TextIOWrapper(gz,encoding="utf-8-sig",newline="")
            w=csv.DictWriter(out,fieldnames=list(records[0]))
            w.writeheader();w.writerows(records)
            out.flush();out.detach()
        z.writestr(p,b.getvalue(),compress_type=zipfile.ZIP_STORED)
    else:
        out=io.StringIO(newline="")
        w=csv.DictWriter(out,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
        z.writestr(p,out.getvalue().encode("utf-8-sig"),compress_type=zipfile.ZIP_DEFLATED)

def html_page(ids,dates,times,drawnums,stats,initial,after):
    # A standalone browser replay player; compressed number/ring class by frame.
    # Viewer contains 37 sequential 224x80 pool states (initial + 36 results)
    # as base64; each frame has exactly 17920 0..4 class codes.
    stack=np.concatenate((initial[None,:,:],after),axis=0).astype(np.uint8)
    assert stack.shape==(len(ids)+1,224,80)
    b64=base64.b64encode(stack.tobytes(order="C")).decode("ascii")
    meta=dict(
      ids=[str(x) for x in ids],dates=dates,times=times,
      drawn=drawnums,
      steps=[dict(draw_id=str(s["draw_id"]),total_changes=s["temp_changed"],
         temp_up=s["temp_up"],temp_down=s["temp_down"],
         ring_12=s["r12_temp_changed"],ring_72=s["r72_temp_changed"],
         ring_672=s["r672_temp_changed"],
         ring_1344=s["r1344_temp_changed"],
         ring_2016=s["r2016_temp_changed"],
         ring_2688=s["r2688_temp_changed"]) for s in stats],
      frames=len(ids)+1,rows=224,cols=80)
    jmeta=json.dumps(meta,ensure_ascii=False,separators=(",",":"))
    # avoid closing script sequence in injected values; metadata from structured ids.
    html=r"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>V128 — 36 çekiliş 224 halka adım adım</title>
<style>
:root{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color-scheme:light}
body{max-width:1020px;margin:auto;padding:18px;background:#f6f7f9;color:#202532}
h1{font-size:1.4rem;margin:0 0 9px}p{line-height:1.45;color:#424955}
.panel{background:#fff;padding:14px;border:1px solid #dce1e8;border-radius:12px;margin:12px 0}
.controls{display:flex;flex-wrap:wrap;align-items:center;gap:9px}
input[type=range]{flex:1;min-width:140px}
select,input[type=number]{padding:8px;border:1px solid #ccd5e2;border-radius:8px;font-size:1rem;max-width:120px}
button{padding:8px 12px;border:1px solid #ccd5e2;border-radius:9px;background:#fff;cursor:pointer}
button:active{background:#eef}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px}
.stat{background:#f3f5f9;border-radius:10px;padding:10px}
.stat b{display:block;font-size:1.35rem}
small,.muted{color:#6b7280}
#plot{display:block;width:100%;image-rendering:pixelated;border:1px solid #e1e3e6;cursor:crosshair}
.legend{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
.sw{display:inline-block;width:13px;height:13px;border-radius:2px;vertical-align:middle;margin-right:3px}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{text-align:left;border-bottom:1px solid #eceff3;padding:7px}
#numberDetail{overflow:auto}
.detailrow{display:grid;grid-template-columns:84px 1fr 55px;align-items:center;gap:6px;margin:3px 0}
.bar{height:11px;border-radius:3px;overflow:hidden}
footer{margin:25px 0;color:#596272;font-size:.87rem}
</style></head><body>
<h1>V128 · 36 gerçek çekilişi birer birer ilerlet</h1>
<p>Başlangıçta son 36 çekilişten <b>önceki</b> durum donduruldu. Her ileri adımda gerçek bir çekiliş eklenir; 224 halkanın 80 sayısının sıcaklık sınıfı yeniden hesaplanır. <b>Bu geleceğin sonucu tahmin değil, kayıtlı sonuçların geriye dönük oynatımıdır.</b></p>
<section class="panel">
<div class="controls">
<button id="prev" title="Bir çekiliş geri">◀ Geri</button><button id="next" title="Bir çekiliş ileri">İleri ▶</button>
<label>Adım <input type="range" id="step" min="0" max="XXXMAXXXX" value="0"></label>
<strong id="stepLabel">0 / 36</strong>
</div>
<p id="drawLabel">Başlangıç durumuna bakıyorsun.</p>
<div class="stats">
<div class="stat">224 halka × 80 sayı<b>17.920</b><small>Her adımın durumu</small></div>
<div class="stat">Sınıf değişimi<b id="numChanges">—</b></div>
<div class="stat">Isınma / soğuma<b id="tempDirs">—</b></div>
<div class="stat">Halka 12 / 72 / 672<b id="ringChanges">—</b></div>
</div>
</section>
<section class="panel">
<div class="controls">
<label>Görüntü: <select id="mode"><option value="pool">Sonraki havuz sınıfı</option><option value="change">Bir önceki adıma göre değişim</option></select></label>
<label>Sayı: <input type="number" id="number" min="1" max="80" value="37"></label>
</div>
<div class="legend" id="legend"></div>
<canvas id="plot" width="800" height="672" role="img" aria-label="224 halka dikey × 80 sayı yatay ısı haritası"></canvas>
<p class="muted">Yatay eksen 1–80 sayılar, dikey eksen 1–224 halkalar (üstte 12, altta 2.688). Hücreye dokunarak sayıyı seç. Yakın komşu halkalardaki hareketleri adım adım izleyebilirsin.</p>
<div id="numberDetail"></div>
</section>
<footer>Kaynak: 15.790 gerçek çekilişlik veri.txt; görünür son 36 çekiliş tarihsel veridir. Sıcak/soğuk etiketleri her halkada tam 16'şar sayı olacak şekilde sıralama temellidir. Hiçbir hedef gelecekten okunarak tahmin yapılmadı.</footer>
<script>
const metadata=XXXMETAXXX;
const encoded="XXXBASE64XXX";
const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
const per=224*80;
const colors=['#263a77','#548fb7','#b9bdc8','#e4af5d','#c45a43'];
const poolNames=['SOĞUK','SERİN','NÖTR','ILIK','SICAK'];
const moveColors=['#416dbe','#e2e8f0','#df7b48'];
const moveNames=['SOĞUMA','AYNI','ISINMA'];
let step=0;
let ball=37;
const $=x=>document.getElementById(x);
const cx=$('plot').getContext('2d');
function pos(frame,ring,number){return frame*per+ring*80+number;}
function label(str){return (str===undefined)?'—':str}
function draw(){
 const m=metadata,rows=m.rows,draw=m.steps[step-1];
 $('step').value=step;
 $('stepLabel').textContent=step+' / '+(m.frames-1);
 $('drawLabel').textContent=step===0?
   'Başlangıç: henüz hiçbir çekiliş eklenmedi. İlk ileri adım son 36 gözlemden ilkini gösterir.':
   'Eklenen gerçek çekiliş #'+m.ids[step-1]+' · '+m.dates[step-1]+' '+m.times[step-1]+
   ' · Sayılar: '+m.drawn[step-1].join(', ');
 $('numChanges').textContent=draw?draw.total_changes.toLocaleString('tr-TR'):'—';
 $('tempDirs').textContent=draw?draw.temp_up+' / '+draw.temp_down:'—';
 $('ringChanges').textContent=draw?
   draw.ring_12+' / '+draw.ring_72+' / '+draw.ring_672:'—';
 const mode=$('mode').value;
 const pixels=cx.createImageData(800,672);
 const rgb=(h)=>[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];
 const rgbPool=colors.map(rgb),rgbMove=moveColors.map(rgb);
 for(let r=0;r<224;r++){
  for(let y=0;y<3;y++){
   for(let c=0;c<80;c++){
    const newer=bytes[pos(step,r,c)];
    const older=bytes[pos(Math.max(0,step-1),r,c)];
    const clr=mode==='pool'?rgbPool[newer]:rgbMove[(newer>older)?2:(newer<older)?0:1];
    const base=((r*3+y)*800+c*10)*4;
    for(let x=0;x<10;x++){
     const k=base+x*4;
     pixels.data[k]=clr[0];pixels.data[k+1]=clr[1];pixels.data[k+2]=clr[2];pixels.data[k+3]=255;
    }
   }
  }
 }
 cx.putImageData(pixels,0,0);
 // highlight selected number's column
 cx.strokeStyle='#000';cx.lineWidth=1;cx.strokeRect((ball-1)*10+0.5,0.5,9,671);
 const names=mode==='pool'?poolNames:moveNames,cs=mode==='pool'?colors:moveColors;
 $('legend').innerHTML=cs.map((c,i)=>'<span><i class="sw" style="background:'+c+'"></i>'+names[i]+'</span>').join('');
 $('numberDetail').innerHTML=numberHtml();
}
function numberHtml(){
 let upper=0,lower=0,stable=0,body='';
 for(let r=0;r<224;r++){
  const newer=bytes[pos(step,r,ball-1)];
  const old=bytes[pos(Math.max(0,step-1),r,ball-1)];
  if(newer>old)upper++;else if(newer<old)lower++;else stable++;
 }
 const selected=[1,2,3,6,12,24,36,56,112,168,224];
 body+='<h3>Sayı '+ball+' · 224 halkadaki yön: '+upper+' ısınma, '+lower+' soğuma, '+stable+' sabit</h3>';
 body+='<table><tr><th>Halka</th><th>Referans</th><th>Önceki</th><th>Yeni</th><th>Yön</th></tr>';
 for(const ring of selected){
  const prev=bytes[pos(Math.max(0,step-1),ring-1,ball-1)];
  const nxt=bytes[pos(step,ring-1,ball-1)];
  const sign=nxt>prev?'↑ Isındı':nxt<prev?'↓ Soğudu':'— Sabit';
  body+='<tr><td>'+ring+'</td><td>'+(ring*12)+'</td><td>'+poolNames[prev]+'</td><td>'+poolNames[nxt]+'</td><td>'+sign+'</td></tr>';
 }
 body+='</table><p class="muted">Tüm 224 halkanın ve 80 sayının görünme adedi ile eski/yeni sıralama detayı ZIP dosyasındaki gerçek CSV/NPZ kayıtlarındadır.</p>';
 return body;
}
$('next').onclick=()=>{step=Math.min(step+1,metadata.frames-1);draw();};
$('prev').onclick=()=>{step=Math.max(step-1,0);draw();};
$('step').oninput=e=>{step=parseInt(e.target.value);draw();};
$('mode').onchange=draw;
$('number').onchange=e=>{ball=Math.min(80,Math.max(1,Number(e.target.value)||1));draw();};
$('plot').onclick=e=>{
 const r=$('plot').getBoundingClientRect();
 ball=Math.min(80,Math.max(1,Math.floor((e.clientX-r.left)/r.width*80)+1));
 $('number').value=ball;draw();
};
draw();
</script></body></html>"""
    return html.replace("XXXMAXXXX",str(len(ids))).replace("XXXMETAXXX",jmeta).replace("XXXBASE64XXX",b64)

def main(source,out,steps):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert len(X)==n and n>2688+steps
    assert np.all(X.sum(axis=1)==20)
    # Replay only last 24 or 36 ACTUAL historical observations.
    start=n-steps
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                      np.cumsum(X,dtype=np.int32,axis=0)))
    counts=(prefix[start][None,:]-prefix[start-LENS]).astype(np.int32)
    prev_rank,prev_pool=ranks_pools(counts)
    initial_count=counts.astype(np.uint16).copy()
    initial_rank=prev_rank.copy()
    initial_pool=prev_pool.copy()
    initial_target_id=rows[start]["id"]
    # Every transition record, ordered by actual observed time and number.
    detail=[]
    bystep=[]
    byring=[]
    bynumber=[]
    class_flow=np.zeros((224,5,5),dtype=np.uint64)
    after_count=[]
    after_rank=[]
    after_pool=[]
    incoming=[]
    departing=[]
    all_ids=[]
    all_dates=[]
    all_times=[]
    all_draw_numbers=[]
    n_changes=0
    for j,t in enumerate(range(start,n),1):
        entry=X[t].astype(np.int16)
        leave=X[t-LENS].astype(np.int16)
        diff=entry[None,:]-leave
        nc=counts+diff
        assert (nc>=0).all()
        assert (nc.sum(axis=1)==20*LENS).all()
        newrank,newpool=ranks_pools(nc)
        dr=newrank.astype(np.int16)-prev_rank.astype(np.int16)
        dp=newpool.astype(np.int16)-prev_pool.astype(np.int16)
        assert ((diff>=0)|(entry[None,:]==0)).all()
        assert ((diff<=0)|(entry[None,:]==1)).all()
        up=(dp>0).sum(axis=1)
        down=(dp<0).sum(axis=1)
        noch=(dp==0).sum(axis=1)
        assert (up+down+noch==80).all()
        assert ((up==0)==(down==0)).all()
        changed=int(up.sum()+down.sum())
        n_changes+=changed
        timestamp=(rows[t]["day"],rows[t]["time"])
        entry_nums=(np.flatnonzero(entry)+1).tolist()
        assert len(entry_nums)==20
        summary=dict(step=j,date=timestamp[0],time=timestamp[1],
          draw_id=rows[t]["id"],draw_20_nums=" ".join(map(str,entry_nums)),
          total_224_ring_number_states=224*80,
          temp_up=int(up.sum()),temp_down=int(down.sum()),
          temp_changed=changed,
          rank_up=int((dr>0).sum()),rank_down=int((dr<0).sum()),
          count_up=int((diff>0).sum()),count_down=int((diff<0).sum()),
          rings_changed=int(((up+down)>0).sum()),
          r12_temp_changed=int(up[0]+down[0]),
          r24_temp_changed=int(up[1]+down[1]),
          r36_temp_changed=int(up[2]+down[2]),
          r72_temp_changed=int(up[5]+down[5]),
          r672_temp_changed=int(up[55]+down[55]),
          r1344_temp_changed=int(up[111]+down[111]),
          r2016_temp_changed=int(up[167]+down[167]),
          r2688_temp_changed=int(up[223]+down[223]))
        bystep.append(summary)
        all_ids.append(int(rows[t]["id"]))
        all_dates.append(timestamp[0])
        all_times.append(timestamp[1])
        all_draw_numbers.append(entry_nums)
        after_count.append(nc.astype(np.uint16).copy())
        after_rank.append(newrank.copy())
        after_pool.append(newpool.copy())
        incoming.append(np.packbits(entry.astype(np.uint8)))
        departing.append(np.packbits(leave.astype(np.uint8),axis=1))
        for r in range(224):
            transition=np.bincount(
                prev_pool[r].astype(int)*5+newpool[r].astype(int),
                minlength=25).reshape(5,5)
            assert transition.sum()==80 and np.all(transition.sum(axis=0)==16)
            assert np.all(transition.sum(axis=1)==16)
            class_flow[r]+=transition
            byring.append(dict(step=j,draw_id=rows[t]["id"],
              ring=r+1,window_draws=int(LENS[r]),count_up=int((diff[r]>0).sum()),
              count_down=int((diff[r]<0).sum()),count_stable=int((diff[r]==0).sum()),
              rank_up=int((dr[r]>0).sum()),rank_down=int((dr[r]<0).sum()),
              rank_stable=int((dr[r]==0).sum()),
              warm=int(up[r]),cool=int(down[r]),same_pool=int(noch[r]),
              five_by_five_transitions="|".join(map(str,transition.ravel()))))
            for b in range(80):
                detail.append(dict(step=j,date=timestamp[0],time=timestamp[1],
                    draw_id=rows[t]["id"],ring=r+1,window_draws=int(LENS[r]),
                    number=b+1,drawn_1_0=int(entry[b]),leaving_1_0=int(leave[r,b]),
                    count_before=int(counts[r,b]),count_after=int(nc[r,b]),
                    delta_count=int(diff[r,b]),
                    rank_before=int(prev_rank[r,b]),rank_after=int(newrank[r,b]),
                    delta_rank=int(dr[r,b]),
                    pool_before=POOL_NAMES[int(prev_pool[r,b])],
                    pool_after=POOL_NAMES[int(newpool[r,b])],
                    delta_pool=int(dp[r,b])))
        for b in range(80):
            ds=dp[:,b]
            counts_up=int((diff[:,b]>0).sum())
            counts_down=int((diff[:,b]<0).sum())
            assert counts_up==0 or counts_down==0
            bynumber.append(dict(step=j,draw_id=rows[t]["id"],number=b+1,
                drawn_1_0=int(entry[b]),ring_count_up=counts_up,
                ring_count_down=counts_down,ring_rank_up=int((dr[:,b]>0).sum()),
                ring_rank_down=int((dr[:,b]<0).sum()),
                ring_pool_up=int((ds>0).sum()),
                ring_pool_down=int((ds<0).sum()),
                ring_pool_unchanged=int((ds==0).sum()),
                both_pool_directions=int((ds>0).any() and (ds<0).any()),
                ring_pool_direction_code="".join("C0W"[int(v)+1] for v in np.sign(ds))))
        counts=nc
        prev_rank=newrank
        prev_pool=newpool
        print("V128 STEP",j,"/",steps,
            "draw",rows[t]["id"],timestamp[1],
            "changed_pool_memberships",changed,
            "ring12",summary["r12_temp_changed"],
            "ring72",summary["r72_temp_changed"],
            "ring672",summary["r672_temp_changed"],
            "ring2688",summary["r2688_temp_changed"],flush=True)
    assert len(detail)==steps*224*80
    assert len(bynumber)==steps*80
    assert len(byring)==steps*224
    assert len(bystep)==steps
    assert sum(x["temp_changed"] for x in bystep)==n_changes
    assert int(class_flow.sum())==steps*224*80
    frame_count=np.stack([initial_count]+after_count,axis=0)
    frame_rank=np.stack([initial_rank]+after_rank,axis=0)
    frame_pool=np.stack([initial_pool]+after_pool,axis=0)
    assert frame_pool.shape==(steps+1,224,80)
    assert frame_count.shape==(steps+1,224,80)
    archive=Path(out);archive.parent.mkdir(parents=True,exist_ok=True)
    player=archive.parent/("V128_"+str(steps)+"_ADIM_224_HALKA_GORSEL_OYNATICI.html")
    player.write_text(html_page(all_ids,all_dates,all_times,all_draw_numbers,
        bystep,initial_pool,np.stack(after_pool,axis=0)),encoding="utf-8")
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,
                          compresslevel=6,allowZip64=True) as z:
        z.writestr("00_TURKCE_KISA_RAPOR.txt",
          "\n".join([
            f"V128 - {steps} gerçek çekiliş birer birer ilerletildi",
            "Source: repository veri.txt, historical draw results only.",
            f"Starting remembered history before draw #{initial_target_id}: "
              "all 224 rings in state already built.",
            f"First applied actual result #{all_ids[0]}, final #{all_ids[-1]}.",
            f"Total step/ring/number transitions = {steps*224*80:,}.",
            f"Actual temperature class changes = {n_changes:,}.",
            "Each step advances EXACTLY one new observed draw.",
            "New draw enters each ring; oldest separate historical draw leaves.",
            "All count deltas, 0-79 ranks, 0..4 pool classes recorded before and after.",
            "Temperature classes always contain exactly 16 balls each.",
            "Static self-contained HTML lets move through 36 draws one at a time.",
            "The initial 36 outcomes are held out from initialization; each enters only",
            "at its own turn. They are HISTORICAL known draws, not future guesses.",
            "",
            "36 STEP MOVEMENT OVERVIEW:"
          ] + [
            f"{q['step']:02d}. draw #{q['draw_id']} {q['date']} {q['time']} "
            f"224-ring pool changes {q['temp_changed']}, "
            f"R12 {q['r12_temp_changed']} / R72 {q['r72_temp_changed']} "
            f"/ R672 {q['r672_temp_changed']} / R2688 {q['r2688_temp_changed']}"
            for q in bystep])+"\n")
        csv_write(z,"01_TEK_TEK_36_CEKILIS_HAREKET_OZET.csv",bystep)
        csv_write(z,"02_HER_CEKILIS_224_HALKA_DEGISIMI.csv",byring)
        csv_write(z,"03_HER_CEKILIS_80_SAYI_224_HALKA_YON_OZET.csv",bynumber)
        csv_write(z,"04_TUM_ADIM_224_HALKA_80_SAYI_TAM_ESKI_YENI.csv.gz",
                  detail,gunzip=True)
        z.writestr("05_224_HALKA_BES_HAVUZ_TOPLAM_GECIS.json",
                   json.dumps(class_flow.tolist(),ensure_ascii=False))
        buff=io.BytesIO()
        np.savez_compressed(buff,
          actual_ids=np.array(all_ids,dtype=np.int64),
          initial_start_draw_id=np.array(initial_target_id),
          lengths=LENS,
          count_state=frame_count,rank_state=frame_rank,
          pool_state=frame_pool,
          incoming_draw=np.stack(incoming),
          leaving_draw=np.stack(departing))
        z.writestr("06_TUM_37_DURUM_224_HALKA_80_SAYI_FULL_NPZ.npz",
                   buff.getvalue(),compress_type=zipfile.ZIP_STORED)
        z.writestr(player.name,player.read_bytes())
        z.writestr("07_METOD_VE_KONTROL.json",json.dumps(dict(
            version="V128.1",replay_mode="known_historical_draws_sequentially",
            historical_source_total=n,source_last=rows[-1]["id"],
            replay_start_draw=all_ids[0],replay_end_draw=all_ids[-1],
            steps=steps,nested_rings=224,numbers=80,
            all_transition_rows=len(detail),class_change_events=n_changes,
            initial_context_2688_real_draws_only=True,
            no_family_features=True,
            future_draw_predictions_made=False,
            full_36_step_224_ring_states_saved=True,
            all_draws_processed_in_correct_chronological_order=True),
            ensure_ascii=False,indent=2))
    print("V128 COMPLETE",archive,archive.stat().st_size,
        "HTML",player,player.stat().st_size,flush=True)
    print("V128 SUM TOTAL",steps,"STEPS",steps*224*80,
        "STATES",n_changes,"POOL-CLASS SHIFTS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--steps",type=int,choices=(24,36),default=36)
    p.add_argument("--out",default="v128_output/V128_36_ADIM_224_HALKA_TAM_OYNATIM.zip")
    a=p.parse_args()
    main(a.source,a.out,a.steps)
