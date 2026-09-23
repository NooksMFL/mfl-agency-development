import os, requests
from datetime import datetime, timezone
BASE="https://api.playmfl.com"
BROWSER_HEADERS={
 "Accept":"*/*","Origin":"https://app.playmfl.com","Referer":"https://app.playmfl.com/",
 "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0"
}
def token():
 rt=os.getenv("MFL_REFRESH_TOKEN")
 if not rt: raise RuntimeError("MFL_REFRESH_TOKEN missing")
 r=requests.post(f"{BASE}/auth/refresh",headers=BROWSER_HEADERS,json={"refreshToken":rt},timeout=20)
 r.raise_for_status(); d=r.json(); a=d.get("access")
 if a is None and isinstance(d.get("data"),dict): a=d["data"].get("access")
 if isinstance(a,dict): a=a.get("token")
 if not a: raise RuntimeError("MFL refresh succeeded but no access token returned")
 return a
def headers(t):
 h=dict(BROWSER_HEADERS);h["Authorization"]=f"Bearer {t}";return h
def get(path,t,params=None):
 r=requests.get(BASE+path,headers=headers(t),params=params,timeout=30)
 if not r.ok: raise RuntimeError(f"{path} returned {r.status_code}: {r.text[:250]}")
 return r.json()
def items(d):
 if isinstance(d,list):return d
 if isinstance(d,dict):
  for k in ("data","items","results","listings","history"):
   x=d.get(k)
   if isinstance(x,list):return x
   if isinstance(x,dict):
    y=items(x)
    if y:return y
 return []
def dt(v):
 if v is None:return None
 try:
  x=float(v)
  if x>1e10:x/=1000
  return datetime.fromtimestamp(x,tz=timezone.utc)
 except:return None
def fmt(x):return x.strftime("%d %b %Y %H:%M UTC") if x else "—"
def diagnose(pid,wallet):
 t=token()
 prof=get(f"/players/{pid}",t)
 sales=items(get("/listings/feed",t,{"limit":25,"playerId":pid}))
 exp=items(get(f"/players/{pid}/experiences/history",t))
 w=wallet.lower(); buys=[]
 for e in sales:
  buyer=str(e.get("buyerAddress") or e.get("buyerWalletAddress") or "").lower()
  when=dt(e.get("purchaseDateTime") or e.get("createdAt") or e.get("date"))
  if buyer==w and when:buys.append((when,e))
 acq,event=max(buys,key=lambda x:x[0]) if buys else (None,None)
 parsed=[]
 for e in exp:
  when=dt(e.get("date") or e.get("createdAt") or e.get("timestamp"))
  if when:parsed.append((when,e))
 parsed.sort(key=lambda x:x[0])
 before=max((x for x in parsed if acq and x[0]<=acq),default=None,key=lambda x:x[0])
 after=min((x for x in parsed if acq and x[0]>acq),default=None,key=lambda x:x[0])
 return {"profile":prof,"sales":sales,"experiences":exp,"acquired":fmt(acq),"event":event,
         "previous":fmt(before[0]) if before else "—","next":fmt(after[0]) if after else "—"}
