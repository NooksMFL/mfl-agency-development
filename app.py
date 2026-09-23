import os,streamlit as st,pandas as pd
import agency_backend as ab
st.set_page_config(page_title="MFL Agency Development",page_icon="🌱",layout="wide")
try:
 if "MFL_REFRESH_TOKEN" in st.secrets:os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception:pass
st.title("🌱 MFL Agency Development")
st.caption("How much have your players developed while you owned them?")
wallet=st.text_input("Dapper wallet address",value="0x65cc0e72dd71ad80").strip()
st.info("API-safe mode: each click analyses up to 10 new players and saves the result. This avoids hammering MFL's rate limit.")
if wallet and st.button("Analyse next batch",type="primary"):
 bar=st.progress(0,text="Loading a small batch of ownership + progression history…")
 def prog(n,total):bar.progress(n/max(total,1),text=f"Analysing this batch… {n}/{total}")
 try:
  total,ok,errors,analysed,planned=ab.sync(wallet,prog,batch_size=10);bar.empty()
  st.success(f"Batch complete: {ok} added · {analysed}/{total} agency players analysed so far.")
  if planned==0:st.success("Historical analysis is complete for all currently owned players.")
  if errors:st.warning(f"{len(errors)} player(s) could not be analysed this batch. If MFL rate-limited the request, wait a little before the next batch.")
 except Exception as e:bar.empty();st.error(f"{type(e).__name__}: {e}")
if wallet:
 c=ab.db();ab.init(c)
 rows=c.execute("""SELECT o.*,COALESCE(t.tag,'NORMAL') tag,COALESCE(t.note,'') note FROM ownership_v63 o
 LEFT JOIN tags t ON t.wallet=o.wallet AND t.player_id=o.player_id WHERE o.wallet=?""",(wallet.lower(),)).fetchall()
 if rows:
  df=pd.DataFrame([dict(r) for r in rows])
  for label,cur,start in [("OVR +","current_ovr","start_ovr"),("PAC +","current_pac","start_pac"),("SHO +","current_sho","start_sho"),("PAS +","current_pas","start_pas"),("DRI +","current_dri","start_dri"),("DEF +","current_def","start_def"),("PHY +","current_phy","start_phy")]:df[label]=df[cur]-df[start]
  df["Acquired"]=pd.to_datetime(df.acquired_at,utc=True,errors="coerce").dt.strftime("%d %b %Y")
  df["History starts"]=pd.to_datetime(df.history_start,utc=True,errors="coerce").dt.strftime("%d %b %Y")
  a,b,c1,d=st.columns(4);a.metric("Players analysed",len(df));b.metric("Bought",int((df.source=="BOUGHT").sum()));c1.metric("Other / packed",int((df.source!="BOUGHT").sum()));d.metric("Tagged",int((df.tag!="NORMAL").sum()))
  filt=st.segmented_control("View",["ALL","NEW MINT","DEVELOP","PRIORITY","WATCH","NORMAL"],default="ALL")
  v=df if filt=="ALL" else df[df.tag==filt]
  st.dataframe(v[["tag","player_name","source","confidence","Acquired","History starts","start_ovr","current_ovr","OVR +","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +","event_count"]],
   hide_index=True,use_container_width=True,column_config={"player_name":"Player","source":"Ownership","start_ovr":"Acquired OVR","current_ovr":"Current OVR","event_count":"History events","confidence":"Acquisition confidence"})
  st.caption("Acquired is only shown when a marketplace purchase into this wallet is verified. 'History starts' is MFL progression history, not automatically an ownership date. POSSIBLE ORIGINAL / MINT means an INITIAL progression exists but does not prove this wallet minted the player.")
  st.subheader("🌱 Mark a prospect")
  opts={f'{r.player_name} ({r.player_id})':int(r.player_id) for _,r in df.iterrows()};who=st.selectbox("Player",opts)
  ex=df[df.player_id==opts[who]].iloc[0];tags=["NEW MINT","DEVELOP","PRIORITY","WATCH","NORMAL"]
  tag=st.selectbox("Tag",tags,index=tags.index(ex.tag) if ex.tag in tags else 4);note=st.text_input("Private note",value=ex.note)
  if st.button("Save tag"):
   c.execute("INSERT INTO tags(wallet,player_id,tag,note) VALUES(?,?,?,?) ON CONFLICT(wallet,player_id) DO UPDATE SET tag=excluded.tag,note=excluded.note",(wallet.lower(),opts[who],tag,note));c.commit();st.rerun()
 c.close()
