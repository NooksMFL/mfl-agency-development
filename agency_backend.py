import os, sqlite3, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

BASE="https://api.playmfl.com"; DB="agency_development.db"
H={"Accept":"*/*","Origin":"https://app.playmfl.com","Referer":"https://app.playmfl.com/","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36"}

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS wallets(wallet TEXT PRIMARY KEY,added_at TEXT);
    CREATE TABLE IF NOT EXISTS ownership(id INTEGER PRIMARY KEY,wallet TEXT,player_id INTEGER,player_name TEXT,started_at TEXT,ended_at TEXT,start_ovr REAL,start_pac REAL,start_sho REAL,start_pas REAL,start_dri REAL,start_def REAL,start_phy REAL);
    CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,wallet TEXT,player_id INTEGER,captured_at TEXT,player_name TEXT,age INTEGER,position TEXT,club TEXT,ovr REAL,pac REAL,sho REAL,pas REAL,dri REAL,def REAL,phy REAL);
    CREATE TABLE IF NOT EXISTS tags(wallet TEXT,player_id INTEGER,tag TEXT,note TEXT,PRIMARY KEY(wallet,player_id));"""); c.commit()

def access_token():
    rt=os.getenv("MFL_REFRESH_TOKEN")
    if not rt: raise RuntimeError("MFL_REFRESH_TOKEN is not configured in Streamlit Secrets.")
    r=requests.post(BASE+"/auth/refresh",headers=H,json={"refreshToken":rt},timeout=20); r.raise_for_status()
    d=r.json(); a=d.get("access")
    if a is None and isinstance(d.get("data"),dict): a=d["data"].get("access")
    if isinstance(a,dict): a=a.get("token")
    if not a: raise RuntimeError("MFL refresh succeeded but no access token was returned.")
    return a

def ah(token):
    h=dict(H); h["Authorization"]="Bearer "+token; return h

def extract_list(d):
    if isinstance(d,list): return d
    if isinstance(d,dict):
        for k in ("players","items","results"):
            if isinstance(d.get(k),list): return d[k]
        x=d.get("data")
        if isinstance(x,list): return x
        if isinstance(x,dict): return extract_list(x)
    return None

def roster_stubs(wallet,token):
    r=requests.get(BASE+"/players",params={"ownerWalletAddress":wallet,"limit":1200},headers=ah(token),timeout=30)
    r.raise_for_status(); xs=extract_list(r.json())
    if xs is None: raise RuntimeError("MFL roster returned no player list.")
    return xs

def pid_of(p):
    for obj in (p, p.get("metadata") or {}, p.get("player") or {}):
        for k in ("id","playerId","playerID"):
            if obj.get(k) is not None: return int(obj[k])
    raise ValueError("No player ID")

def unwrap(d):
    if isinstance(d,dict):
        for k in ("player","data"):
            if isinstance(d.get(k),dict):
                inner=d[k]
                if any(x in inner for x in ("metadata","overall","overallRating","attributes","firstName","name")): return inner
    return d

def detail(player_id,token):
    r=requests.get(f"{BASE}/players/{player_id}",headers=ah(token),timeout=20)
    r.raise_for_status()
    return unwrap(r.json())

def first(*vals):
    return next((v for v in vals if v is not None),None)

def normalize(p, player_id):
    p=unwrap(p) or {}; m=p.get("metadata") or {}; a=p.get("attributes") or p.get("stats") or {}
    # Current MFL player profiles commonly expose nested metadata with first/last name and ratings.
    name=first(p.get("name"),m.get("name"))
    if not name:
        fn=first(p.get("firstName"),m.get("firstName"),""); ln=first(p.get("lastName"),m.get("lastName"),"")
        name=(str(fn)+" "+str(ln)).strip()
    ratings=p.get("ratings") or p.get("rating") or {}
    def stat(*names):
        for src in (p,a,ratings,m):
            for n in names:
                if isinstance(src,dict) and src.get(n) is not None: return src[n]
        return None
    ac=p.get("activeContract") or {}; club=ac.get("club") or p.get("club") or {}
    if isinstance(club,dict): club=first(club.get("name"),club.get("clubName"),"")
    pos=first(p.get("position"),p.get("primaryPosition"),m.get("position"),"")
    if isinstance(pos,dict): pos=first(pos.get("name"),pos.get("code"),"")
    return {"player_id":player_id,"player_name":name or f"Player {player_id}",
      "age":first(p.get("age"),m.get("age")),"position":str(pos),"club":club or "",
      "ovr":stat("overall","overallRating","ovr"),"pac":stat("pace","PAC"),"sho":stat("shooting","SHO"),
      "pas":stat("passing","PAS"),"dri":stat("dribbling","DRI"),"def_":stat("defense","defending","DEF"),
      "phy":stat("physical","physicality","PHY")}

def sync_wallet(wallet):
    wallet=wallet.strip().lower(); token=access_token()
    stubs=roster_stubs(wallet,token); ids=list(dict.fromkeys(pid_of(x) for x in stubs))
    players=[]; errors=[]
    def fetch(pid):
        try: return normalize(detail(pid,token),pid)
        except Exception as e: return (pid,str(e))
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures={ex.submit(fetch,pid):pid for pid in ids}
        for f in as_completed(futures):
            x=f.result()
            if isinstance(x,tuple): errors.append(x)
            else: players.append(x)
    if not players: raise RuntimeError(f"Found {len(ids)} owned IDs but could not load any player profiles.")
    now=datetime.now(timezone.utc).isoformat(); c=db(); init(c)
    c.execute("INSERT OR IGNORE INTO wallets VALUES(?,?)",(wallet,now))
    opens={r["player_id"]:r for r in c.execute("SELECT * FROM ownership WHERE wallet=? AND ended_at IS NULL",(wallet,))}
    current={p["player_id"] for p in players}
    for p in players:
        c.execute("INSERT INTO snapshots(wallet,player_id,captured_at,player_name,age,position,club,ovr,pac,sho,pas,dri,def,phy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (wallet,p["player_id"],now,p["player_name"],p["age"],p["position"],p["club"],p["ovr"],p["pac"],p["sho"],p["pas"],p["dri"],p["def_"],p["phy"]))
        old=opens.get(p["player_id"])
        # Repair the v3 baseline if it was created with blank/None profile fields.
        if old and old["start_ovr"] is None and p["ovr"] is not None:
            c.execute("""UPDATE ownership SET player_name=?,start_ovr=?,start_pac=?,start_sho=?,start_pas=?,start_dri=?,start_def=?,start_phy=?
                         WHERE id=?""",(p["player_name"],p["ovr"],p["pac"],p["sho"],p["pas"],p["dri"],p["def_"],p["phy"],old["id"]))
        elif not old:
            c.execute("INSERT INTO ownership(wallet,player_id,player_name,started_at,start_ovr,start_pac,start_sho,start_pas,start_dri,start_def,start_phy) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (wallet,p["player_id"],p["player_name"],now,p["ovr"],p["pac"],p["sho"],p["pas"],p["dri"],p["def_"],p["phy"]))
    # Only close ownership if the ID disappeared from the authoritative roster, not because a detail call failed.
    roster_ids=set(ids)
    for pid in set(opens)-roster_ids:
        c.execute("UPDATE ownership SET ended_at=? WHERE wallet=? AND player_id=? AND ended_at IS NULL",(now,wallet,pid))
    c.commit(); c.close()
    return len(ids),len(players),errors
