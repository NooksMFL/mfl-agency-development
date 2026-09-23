import os,json
import streamlit as st
import agency_backend as ab

st.set_page_config(page_title="MFL Metadata Diagnostic",page_icon="🔎",layout="wide")
try:
 if "MFL_REFRESH_TOKEN" in st.secrets:os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception:pass

st.title("🔎 MFL Player Metadata Diagnostic")
st.caption("One-player diagnostic only. This does not change or rebuild your 352-player agency cache.")

pid=st.number_input("Player ID",min_value=1,value=411974,step=1)
wallet=st.text_input("Wallet",value="0x65cc0e72dd71ad80").strip().lower()

if st.button("Inspect player",type="primary"):
 try:
  t=ab.token()
  profile_raw=ab.get(f"/players/{int(pid)}",t)
  roster_raw=ab.get("/players",t,{"ownerWalletAddress":wallet,"limit":1200})
  roster=ab.arr(roster_raw)
  rr=None
  for x in roster:
   p=ab.unwrap(x)
   xid=p.get("id") or p.get("playerId") or p.get("playerID")
   try:xid=int(xid)
   except:continue
   if xid==int(pid):
    rr=x;break

  st.success("API responses received.")
  st.subheader("What our parser currently finds")
  c1,c2=st.columns(2)
  with c1:
   st.write("Profile parser")
   st.json(ab.player_meta_from_payload(profile_raw))
  with c2:
   st.write("Roster parser")
   st.json(ab.player_meta_from_payload(rr) if rr is not None else {"error":"player not found in roster response"})

  st.subheader("Raw /players/{id} response")
  st.json(profile_raw,expanded=True)
  st.subheader("This player's raw roster record")
  st.json(rr if rr is not None else {"error":"player not found"},expanded=True)

  # Flatten paths so field locations are obvious without guessing.
  def flat(x,path="$",out=None):
   out=[] if out is None else out
   if isinstance(x,dict):
    for k,v in x.items():flat(v,f"{path}.{k}",out)
   elif isinstance(x,list):
    for i,v in enumerate(x[:10]):flat(v,f"{path}[{i}]",out)
   else:
    out.append((path,x))
   return out
  st.subheader("Profile field paths")
  st.dataframe([{"Path":p,"Value":str(v)} for p,v in flat(profile_raw)],use_container_width=True,hide_index=True)
  st.subheader("Roster field paths")
  st.dataframe([{"Path":p,"Value":str(v)} for p,v in flat(rr or {})],use_container_width=True,hide_index=True)
 except Exception as e:
  st.error(f"{type(e).__name__}: {e}")
