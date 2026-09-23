import os, sqlite3, requests, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

BASE="https://api.playmfl.com"; DB="agency_development.db"
H={"Accept":"*/*","Origin":"https://app.playmfl.com","Referer":"https://app.playmfl.com/",
"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0"}
STATS=("overall","pace","shooting","passing","dribbling","defense","physical")

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init(c):
 c.executescript("""CREATE TABLE IF NOT EXISTS ownership_v6(
 wallet TEXT,player_id INTEGER,player_name TEXT,source TEXT,acquired_at TEXT,
 start_ovr REAL,start_pac REAL,start_sho REAL,start_pas REAL,start_dri REAL,start_def REAL,start_phy REAL,
 current_ovr REAL,current_pac REAL,current_sho REAL,current_pas REAL,current_dri REAL,current_def REAL,current_phy REAL,
 progression_owned INTEGER DEFAULT 0,last_progression TEXT,updated_at TEXT,PRIMARY KEY(wallet,player_id));
 CREATE TABLE IF NOT EXISTS tags(wallet TEXT,player_id INTEGER,tag TEXT,note TEXT,PRIMARY KEY(wallet,player_id));"""); c.commit()
def token():
 rt=os.getenv("MFL_REFRESH_TOKEN")
 if not rt: raise RuntimeError("MFL_REFRESH_TOKEN missing")
 r=requests.post(BASE+"/auth/refresh",headers=H,json={"refreshToken":rt},timeout=20); r.raise_for_status()
 d=r.json(); a=d.get("access") or ((d.get("data") or {}).get("access") if isinstance(d.get("data"),dict) else None)
 if isinstance(a,dict):a=a.get("token")
 if not a:raise RuntimeError("No access token returned")
 return a
def ah(t):
 h=dict(H);h["Authorization"]="Bearer "+t;return h
def get(path,t,params=None):
 for attempt in range(5):
  r=requests.get(BASE+path,headers=ah(t),params=params,timeout=30)
  if r.status_code==429:
   wait=int(r.headers.get("Retry-After") or min(60,5*(2**attempt)))
   time.sleep(wait)
   continue
  if not r.ok:raise RuntimeError(f"{path} returned {r.status_code}: {r.text[:180]}")
  return r.json()
 raise RuntimeError(f"{path} is still rate-limited after retries. Please wait and try again later.")

def arr(d):
 if isinstance(d,list):return d
 if isinstance(d,dict):
  for k in ("data","items","results","players","listings","history"):
   x=d.get(k)
   if isinstance(x,list):return x
   if isinstance(x,dict):
    y=arr(x)
    if y:return y
 return []
def pid(p):
 for x in (p,p.get("metadata") or {},p.get("player") or {}):
  for k in ("id","playerId","playerID"):
   if x.get(k) is not None:return int(x[k])
 raise ValueError("No player id")
def roster(wallet,t):
 return arr(get("/players",t,{"ownerWalletAddress":wallet,"limit":1200}))
def unwrap(p):
 if isinstance(p,dict):
  for k in ("data","player"):
   if isinstance(p.get(k),dict):p=p[k]
 return p or {}
def stat(p,*names):
 p=unwrap(p);m=p.get("metadata") or {};a=p.get("attributes") or p.get("stats") or {};r=p.get("ratings") or {}
 for src in (p,a,r,m):
  for n in names:
   if isinstance(src,dict) and src.get(n) is not None:return src[n]
def profile(pid,t):
 p=unwrap(get(f"/players/{pid}",t));m=p.get("metadata") or {}
 name=p.get("name") or m.get("name")
 if not name:name=(str(p.get("firstName") or m.get("firstName") or "")+" "+str(p.get("lastName") or m.get("lastName") or "")).strip()
 return {"name":name or f"Player {pid}","overall":stat(p,"overall","overallRating","ovr"),"pace":stat(p,"pace","PAC"),
 "shooting":stat(p,"shooting","SHO"),"passing":stat(p,"passing","PAS"),"dribbling":stat(p,"dribbling","DRI"),
 "defense":stat(p,"defense","defending","DEF"),"physical":stat(p,"physical","physicality","PHY")}
def todt(v):
 if v is None:return None
 try:
  x=float(v)
  if x>1e10:x/=1000
  return datetime.fromtimestamp(x,tz=timezone.utc)
 except:
  try:return datetime.fromisoformat(str(v).replace("Z","+00:00"))
  except:return None
def iso(x):return x.isoformat() if x else None
def sale_history(pid,t):return arr(get("/listings/feed",t,{"limit":25,"playerId":pid}))
def exp_history(pid,t):return arr(get(f"/players/{pid}/experiences/history",t))
def acquire(sales,wallet):
 w=wallet.lower(); buys=[]
 for e in sales:
  buyer=str(e.get("buyerAddress") or e.get("buyerWalletAddress") or "").lower()
  when=todt(e.get("purchaseDateTime") or e.get("createdAt") or e.get("date"))
  if buyer==w and when:buys.append((when,e))
 if buys:return max(buys,key=lambda z:z[0])[0],"BOUGHT"
 return None,"PACKED / ORIGINAL / UNKNOWN"
def event_values(e):
 vals=e.get("values") or e.get("attributes") or {}
 out={}
 aliases={"overall":("overall","overallRating","ovr"),"pace":("pace","PAC"),"shooting":("shooting","SHO"),
 "passing":("passing","PAS"),"dribbling":("dribbling","DRI"),"defense":("defense","defending","DEF"),"physical":("physical","physicality","PHY")}
 for k,names in aliases.items():
  for src in (vals,e):
   for n in names:
    if isinstance(src,dict) and src.get(n) is not None:out[k]=src[n];break
   if k in out:break
 return out
def reconstruct(exps,acq,current):
 parsed=[]
 for e in exps:
  when=todt(e.get("date") or e.get("createdAt") or e.get("timestamp"))
  if when:parsed.append((when,e))
 parsed.sort(key=lambda z:z[0])
 # If no marketplace acquisition exists, use earliest progression state as a conservative historical baseline.
 effective=acq or (parsed[0][0] if parsed else None)
 state={k:None for k in STATS}
 owned=0;last=None
 for when,e in parsed:
  vals=event_values(e)
  if effective and when<=effective:
   for k,v in vals.items():state[k]=v
  if effective and when>=effective:
   owned+=1;last=when
 # If history doesn't expose a complete state, do not invent growth: fill only missing baseline from current.
 for k in STATS:
  if state[k] is None:state[k]=current.get(k)
 return effective,state,owned,last
def analyse(pid,wallet,t):
 cur=profile(pid,t);sales=sale_history(pid,t);exps=exp_history(pid,t);acq,source=acquire(sales,wallet)
 effective,start,owned,last=reconstruct(exps,acq,cur)
 return pid,cur,source,effective,start,owned,last
def sync(wallet,progress=None,batch_size=15):
 wallet=wallet.strip().lower();t=token()
 # Retry-aware roster request happens only once per batch.
 ids=list(dict.fromkeys(pid(x) for x in roster(wallet,t)))
 c=db();init(c)
 cached={r["player_id"]:r for r in c.execute("SELECT * FROM ownership_v6 WHERE wallet=?",(wallet,))}
 # Historical ownership data is immutable enough to cache. Prioritise unseen players.
 todo=[x for x in ids if x not in cached][:batch_size]
 results=[];errors=[]
 for n,x in enumerate(todo,1):
  try:
   results.append(analyse(x,wallet,t))
  except Exception as e:
   errors.append((x,str(e)))
   # If MFL says rate limited, stop this batch instead of hammering further.
   if "rate-limit" in str(e).lower() or "429" in str(e):
    break
  if progress:progress(n,len(todo))
  time.sleep(0.35)
 now=datetime.now(timezone.utc).isoformat()
 for player_id,cur,source,acq,start,owned,last in results:
  c.execute("""INSERT INTO ownership_v6 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
  ON CONFLICT(wallet,player_id) DO UPDATE SET player_name=excluded.player_name,source=excluded.source,acquired_at=excluded.acquired_at,
  start_ovr=excluded.start_ovr,start_pac=excluded.start_pac,start_sho=excluded.start_sho,start_pas=excluded.start_pas,start_dri=excluded.start_dri,start_def=excluded.start_def,start_phy=excluded.start_phy,
  current_ovr=excluded.current_ovr,current_pac=excluded.current_pac,current_sho=excluded.current_sho,current_pas=excluded.current_pas,current_dri=excluded.current_dri,current_def=excluded.current_def,current_phy=excluded.current_phy,
  progression_owned=excluded.progression_owned,last_progression=excluded.last_progression,updated_at=excluded.updated_at""",
  (wallet,player_id,cur["name"],source,iso(acq),start["overall"],start["pace"],start["shooting"],start["passing"],start["dribbling"],start["defense"],start["physical"],
   cur["overall"],cur["pace"],cur["shooting"],cur["passing"],cur["dribbling"],cur["defense"],cur["physical"],owned,iso(last),now))
 c.commit()
 analysed=c.execute("SELECT COUNT(*) FROM ownership_v6 WHERE wallet=?",(wallet,)).fetchone()[0]
 c.close()
 return len(ids),len(results),errors,analysed,len(todo)

