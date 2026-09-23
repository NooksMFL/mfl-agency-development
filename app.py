import streamlit as st,pandas as pd
import agency_backend as ab
st.set_page_config(page_title="MFL Agency Development",page_icon="🌱",layout="wide")
st.title("🌱 MFL Agency Development")
st.caption("See how much your players have developed while they have been in your agency.")
wallet=st.text_input("Dapper wallet address",placeholder="0x…").strip()
if wallet:
 if st.button("Load / update my agency",type="primary"):
  try:
   with st.spinner("Loading agency from MFL…"): n=ab.sync_wallet(wallet)
   st.success(f"Found {n} players.")
  except Exception as e: st.error(f"Could not load this agency yet: {type(e).__name__}: {e}")
 c=ab.db();ab.init(c)
 rows=c.execute("""SELECT o.player_id,o.player_name,o.started_at,o.start_ovr,s.age,s.position,s.club,s.ovr,s.pac,s.sho,s.pas,s.dri,s.def,s.phy,COALESCE(t.tag,'NORMAL') tag,COALESCE(t.note,'') note FROM ownership o JOIN snapshots s ON s.id=(SELECT MAX(id) FROM snapshots q WHERE q.wallet=o.wallet AND q.player_id=o.player_id) LEFT JOIN tags t ON t.wallet=o.wallet AND t.player_id=o.player_id WHERE o.wallet=? AND o.ended_at IS NULL""",(wallet.lower(),)).fetchall()
 if rows:
  df=pd.DataFrame([dict(x) for x in rows]);df["OVR +"]=df.ovr-df.start_ovr
  st.metric("Players in agency",len(df))
  filt=st.segmented_control("View",["ALL","NEW MINT","DEVELOP","PRIORITY","WATCH","NORMAL"],default="ALL")
  v=df if filt=="ALL" else df[df.tag==filt]
  st.dataframe(v[["tag","player_name","age","position","club","start_ovr","ovr","OVR +"]],hide_index=True,use_container_width=True)
  st.subheader("Mark a prospect")
  names={f'{r.player_name} ({r.player_id})':int(r.player_id) for _,r in df.iterrows()}; who=st.selectbox("Player",names)
  tag=st.selectbox("Tag",["NEW MINT","DEVELOP","PRIORITY","WATCH","NORMAL"]);note=st.text_input("Note")
  if st.button("Save"):
   c.execute("INSERT INTO tags(wallet,player_id,tag,note) VALUES(?,?,?,?) ON CONFLICT(wallet,player_id) DO UPDATE SET tag=excluded.tag,note=excluded.note",(wallet.lower(),names[who],tag,note));c.commit();st.rerun()
 c.close()
else:
 st.info("Enter a Dapper wallet to load an MFL agency.")
