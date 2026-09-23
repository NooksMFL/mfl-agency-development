import os, sqlite3, requests
from datetime import datetime, timezone

BASE="https://api.playmfl.com"
DB="agency_development.db"
H={"Accept":"application/json","Origin":"https://app.playmfl.com","Referer":"https://app.playmfl.com/","User-Agent":"MFL-Agency-Development/1.0"}

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wallets(wallet TEXT PRIMARY KEY,added_at TEXT);
    CREATE TABLE IF NOT EXISTS ownership(id INTEGER PRIMARY KEY,wallet TEXT,player_id INTEGER,player_name TEXT,started_at TEXT,ended_at TEXT,start_ovr REAL,start_pac REAL,start_sho REAL,start_pas REAL,start_dri REAL,start_def REAL,start_phy REAL);
    CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,wallet TEXT,player_id INTEGER,captured_at TEXT,player_name TEXT,age INTEGER,position TEXT,club TEXT,ovr REAL,pac REAL,sho REAL,pas REAL,dri REAL,def REAL,phy REAL);
    CREATE TABLE IF NOT EXISTS tags(wallet TEXT,player_id INTEGER,tag TEXT,note TEXT,PRIMARY KEY(wallet,player_id));
    """); c.commit()

def access_token():
    rt=os.getenv("MFL_REFRESH_TOKEN")
    if not rt: raise RuntimeError("Site MFL_REFRESH_TOKEN is not configured")
    r=requests.post(BASE+"/auth/refresh",headers=H,json={"refreshToken":rt},timeout=20)
    r.raise_for_status(); d=r.json()
    a=d.get("access")
    if a is None and isinstance(d.get("data"),dict): a=d["data"].get("access")
    if isinstance(a,dict): a=a.get("token")
    if not a: raise RuntimeError("MFL refresh succeeded but no access token was returned")
    return a

def roster(wallet):
    token=access_token()
    h=dict(H); h["Authorization"]="Bearer "+token
    r=requests.get(BASE+"/players",params={"ownerWalletAddress":wallet,"limit":1200},headers=h,timeout=30)
    if not r.ok:
        body=r.text[:300].replace("\n"," ")
        raise RuntimeError(f"MFL roster request returned {r.status_code}: {body}")
    d=r.json()
    if isinstance(d,list): return d
    if isinstance(d,dict):
        for k in ("players","items","results"):
            if isinstance(d.get(k),list): return d[k]
        if isinstance(d.get("data"),list): return d["data"]
        if isinstance(d.get("data"),dict):
            for k in ("players","items","results"):
                if isinstance(d["data"].get(k),list): return d["data"][k]
    raise RuntimeError("MFL returned data, but no player list was found")

def pick(p,*ks):
    for k in ks:
        if p.get(k) is not None:return p[k]

def norm(p):
    m=p.get("metadata") or {}; a=p.get("attributes") or p.get("stats") or m.get("attributes") or {}
    ac=p.get("activeContract") or {}; club=ac.get("club") or p.get("club") or {}
    if isinstance(club,dict): club=club.get("name","")
    pos=pick(p,"position","primaryPosition") or m.get("position","")
    if isinstance(pos,dict): pos=pos.get("name","")
    return dict(player_id=int(pick(p,"id","playerId")),player_name=pick(p,"name","playerName") or m.get("name",""),
      age=pick(p,"age") or m.get("age"),position=str(pos),club=club or "",
      ovr=pick(p,"overall","overallRating") or a.get("overall"),pac=pick(p,"pace") or a.get("pace"),
      sho=pick(p,"shooting") or a.get("shooting"),pas=pick(p,"passing") or a.get("passing"),
      dri=pick(p,"dribbling") or a.get("dribbling"),def_=pick(p,"defense","defending") or a.get("defense") or a.get("defending"),
      phy=pick(p,"physical") or a.get("physical"))

def sync_wallet(wallet):
    wallet=wallet.strip().lower()
    if not wallet.startswith("0x") or len(wallet)<8: raise ValueError("Enter a valid Dapper/Flow wallet address")
    ps=[norm(x) for x in roster(wallet)]
    now=datetime.now(timezone.utc).isoformat()
    c=db(); init(c); c.execute("INSERT OR IGNORE INTO wallets VALUES(?,?)",(wallet,now))
    opens={r["player_id"]:r for r in c.execute("SELECT * FROM ownership WHERE wallet=? AND ended_at IS NULL",(wallet,))}
    ids={p["player_id"] for p in ps}
    for p in ps:
        c.execute("INSERT INTO snapshots(wallet,player_id,captured_at,player_name,age,position,club,ovr,pac,sho,pas,dri,def,phy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (wallet,p["player_id"],now,p["player_name"],p["age"],p["position"],p["club"],p["ovr"],p["pac"],p["sho"],p["pas"],p["dri"],p["def_"],p["phy"]))
        if p["player_id"] not in opens:
            c.execute("INSERT INTO ownership(wallet,player_id,player_name,started_at,start_ovr,start_pac,start_sho,start_pas,start_dri,start_def,start_phy) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (wallet,p["player_id"],p["player_name"],now,p["ovr"],p["pac"],p["sho"],p["pas"],p["dri"],p["def_"],p["phy"]))
    for pid in set(opens)-ids:
        c.execute("UPDATE ownership SET ended_at=? WHERE wallet=? AND player_id=? AND ended_at IS NULL",(now,wallet,pid))
    c.commit(); c.close(); return len(ps)
