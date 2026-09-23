import os, requests
from datetime import datetime, timezone
BASE="https://api.playmfl.com"
H={"Accept":"*/*","Origin":"https://app.playmfl.com","Referer":"https://app.playmfl.com/","User-Agent":"Mozilla/5.0"}

def token():
    rt=os.getenv("MFL_REFRESH_TOKEN")
    if not rt: raise RuntimeError("MFL_REFRESH_TOKEN missing")
    r=requests.post(BASE+"/auth/refresh",headers=H,json={"refreshToken":rt},timeout=20); r.raise_for_status()
    d=r.json(); a=d.get("access") or (d.get("data") or {}).get("access")
    if isinstance(a,dict): a=a.get("token")
    if not a: raise RuntimeError("No access token returned")
    return a

def ah(t):
    h=dict(H); h["Authorization"]="Bearer "+t; return h

def get_json(path,t,params=None):
    r=requests.get(BASE+path,headers=ah(t),params=params,timeout=30)
    r.raise_for_status(); return r.json()

def arr(d):
    if isinstance(d,list): return d
    if isinstance(d,dict):
        if isinstance(d.get("data"),list): return d["data"]
        for k in ("items","results","players"):
            if isinstance(d.get(k),list): return d[k]
    return []

def profile(pid,t):
    d=get_json(f"/players/{pid}",t)
    if isinstance(d,dict) and isinstance(d.get("data"),dict): d=d["data"]
    if isinstance(d,dict) and isinstance(d.get("player"),dict): d=d["player"]
    return d

def player_name(p,pid):
    m=p.get("metadata") or {}
    name=p.get("name") or m.get("name")
    if name:return name
    return (str(p.get("firstName") or m.get("firstName") or "")+" "+str(p.get("lastName") or m.get("lastName") or "")).strip() or f"Player {pid}"

def sales(pid,t,limit=100):
    return arr(get_json("/listings/feed",t,{"limit":limit,"playerId":pid}))

def experiences(pid,t):
    return arr(get_json(f"/players/{pid}/experiences/history",t))

def ts(v):
    if v is None:return None
    x=float(v)
    if x>10_000_000_000:x/=1000
    return datetime.fromtimestamp(x,tz=timezone.utc)

def fmt(dt):
    return dt.strftime("%d %b %Y %H:%M UTC") if dt else "—"

def latest_purchase_into_wallet(entries,wallet):
    w=wallet.lower()
    matches=[]
    for e in entries:
        buyer=str(e.get("buyerAddress") or "").lower()
        if buyer==w:
            dt=ts(e.get("purchaseDateTime"))
            if dt:matches.append((dt,e))
    return max(matches,key=lambda x:x[0]) if matches else (None,None)

def reconstruct_at(exps,acq_dt):
    """Carry progression values forward chronologically and return state at acquisition.
    This intentionally does not invent values missing before acquisition."""
    state={k:None for k in ("overall","pace","shooting","passing","dribbling","defense","physical")}
    before=None; after=None
    parsed=[]
    for e in exps:
        dt=ts(e.get("date"))
        if dt:parsed.append((dt,e))
    parsed.sort(key=lambda x:x[0])
    for dt,e in parsed:
        vals=e.get("values") or {}
        if acq_dt and dt<=acq_dt:
            for k in state:
                if vals.get(k) is not None:state[k]=vals[k]
            before=(dt,e)
        elif acq_dt and dt>acq_dt and after is None:
            after=(dt,e)
    return state,before,after,len(parsed)

def diagnose(pid,wallet):
    t=token(); p=profile(pid,t); s=sales(pid,t,100); x=experiences(pid,t)
    acq,event=latest_purchase_into_wallet(s,wallet)
    state,before,after,n=reconstruct_at(x,acq)
    return {
      "player_id":pid,"name":player_name(p,pid),"sale_count":len(s),"experience_count":n,
      "acquired":fmt(acq),"acquired_raw":acq,"sale_event":event,
      "state":state,
      "previous_progression":fmt(before[0]) if before else "—",
      "next_progression":fmt(after[0]) if after else "—",
      "sales":s,"experiences":x
    }
