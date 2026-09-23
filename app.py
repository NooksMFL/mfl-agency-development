import os, sqlite3
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import agency_backend as ab

st.set_page_config(page_title="MFL Agency Development",page_icon="🌱",layout="wide")
try:
 if "MFL_REFRESH_TOKEN" in st.secrets: os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception: pass

st.title("🌱 MFL Agency Development")
st.caption("Track how players develop while they are in your agency.")

wallet=st.text_input("Dapper wallet address",value="0x65cc0e72dd71ad80").strip().lower()
c=ab.db(); ab.init(c)

def load():
 rows=c.execute("""SELECT o.*,COALESCE(t.tag,'NORMAL') tag,COALESCE(t.note,'') note
 FROM ownership_v65 o LEFT JOIN tags t ON t.wallet=o.wallet AND t.player_id=o.player_id
 WHERE o.wallet=?""",(wallet,)).fetchall()
 if not rows:return pd.DataFrame()
 d=pd.DataFrame([dict(r) for r in rows])
 pairs=[("OVR +","current_ovr","start_ovr"),("PAC +","current_pac","start_pac"),("SHO +","current_sho","start_sho"),
 ("PAS +","current_pas","start_pas"),("DRI +","current_dri","start_dri"),("DEF +","current_def","start_def"),("PHY +","current_phy","start_phy")]
 for label,cur,start in pairs:d[label]=pd.to_numeric(d[cur],errors="coerce")-pd.to_numeric(d[start],errors="coerce")
 d["Acquired"]=pd.to_datetime(d.acquired_at,utc=True,errors="coerce").dt.strftime("%d %b %Y")
 d["History starts"]=pd.to_datetime(d.history_start,utc=True,errors="coerce").dt.strftime("%d %b %Y")
 d["Auto status"]=d.apply(lambda r:"NEW MINT" if r["source"]=="NEW MINT / ORIGINAL" and (r["OVR +"]==0 or pd.isna(r["OVR +"])) else ("DEVELOPING" if pd.notna(r["OVR +"]) and r["OVR +"]>0 else "TRACKED"),axis=1)
 return d

df=load()
analysed=len(df)
st.subheader("Agency import")
st.caption("Historical ownership is cached. Use Finish agency import to work through all remaining uncached players automatically in controlled batches. Completed players are saved as it goes.")
col_import1,col_import2=st.columns([1,1])
with col_import1:
 if st.button("Analyse next 12 players"):
  bar=st.progress(0,text="Preparing batch…")
  def prog(n,total):bar.progress(n/max(total,1),text=f"Analysing {n}/{total}…")
  try:
   total,ok,errors,analysed,planned=ab.sync(wallet,prog,batch_size=12);bar.empty()
   st.success(f"{ok} added · {analysed}/{total} agency players analysed.")
   if errors:st.warning(f"{len(errors)} player(s) could not be analysed.")
   st.rerun()
  except Exception as e:bar.empty();st.error(f"{type(e).__name__}: {e}")
with col_import2:
 if st.button("Finish agency import",type="primary"):
  bar=st.progress(0,text="Starting safe automatic import…")
  status=st.empty()
  def fullprog(done,total,chunk):
   bar.progress(done/max(total,1),text=f"Agency import: {done}/{total}")
   status.caption(f"Completed safe batch {chunk}. Pausing between batches to protect the MFL API.")
  try:
   result=ab.finish_import(wallet,fullprog,chunk_size=12,pause_seconds=8)
   bar.empty();status.empty()
   if result["complete"]:
    st.success(f"Agency import complete: {result['analysed']}/{result['total']} players.")
   elif result["rate_limited"]:
    st.warning(f"MFL rate limit reached safely at {result['analysed']}/{result['total']}. Everything completed so far is saved. Wait a while, then press Finish agency import again.")
   else:
    st.info(f"Import paused at {result['analysed']}/{result['total']}. Completed data is saved; press Finish agency import again to continue.")
   st.rerun()
  except Exception as e:
   bar.empty();status.empty();st.error(f"{type(e).__name__}: {e}")

df=load()
if df.empty:
 st.info("Run the first batch to build your agency dashboard.")
 st.stop()

# headline metrics
newm=int((df["source"]=="NEW MINT / ORIGINAL").sum())
bought=int((df["source"]=="BOUGHT").sum())
developing=int((pd.to_numeric(df["OVR +"],errors="coerce")>0).sum())
priority=int((df.tag=="PRIORITY").sum())
m1,m2,m3,m4,m5=st.columns(5)
m1.metric("Players analysed",len(df))
m2.metric("New / original",newm)
m3.metric("Bought",bought)
m4.metric("OVR improved",developing)
m5.metric("Priority",priority)

tab1,tab2,tab3,tab4=st.tabs(["🏆 Development","🆕 New Mints","🎯 Watchlist","👥 Full Agency"])

with tab1:
 st.subheader("Top developers")
 dev=df[pd.to_numeric(df["OVR +"],errors="coerce")>0].sort_values(["OVR +","current_ovr"],ascending=[False,False])
 if dev.empty:st.info("No analysed players have increased OVR yet.")
 else:
  st.dataframe(dev[["player_name","source","start_ovr","current_ovr","OVR +","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +"]],
   hide_index=True,use_container_width=True,column_config={"player_name":"Player","source":"Ownership","start_ovr":"Start OVR","current_ovr":"Current OVR"})
 st.subheader("Attribute movers")
 movers=df.copy()
 movers["Attribute gains"]=movers[["PAC +","SHO +","PAS +","DRI +","DEF +","PHY +"]].fillna(0).sum(axis=1)
 movers=movers[movers["Attribute gains"]>0].sort_values(["Attribute gains","OVR +"],ascending=False)
 if movers.empty:st.caption("No attribute gains in analysed players yet.")
 else:st.dataframe(movers[["player_name","current_ovr","OVR +","Attribute gains","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +"]],hide_index=True,use_container_width=True)

with tab2:
 mint=df[df.source=="NEW MINT / ORIGINAL"].sort_values(["history_start","current_ovr"],ascending=[False,False])
 st.caption("Players with no marketplace purchase into this wallet whose MFL history begins with an INITIAL state.")
 st.dataframe(mint[["player_name","History starts","start_ovr","current_ovr","OVR +","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +","tag"]],
  hide_index=True,use_container_width=True,column_config={"player_name":"Player","start_ovr":"Initial OVR","current_ovr":"Current OVR","tag":"Your tag"})

with tab3:
 st.subheader("Your development list")
 watch=df[df.tag.isin(["DEVELOP","PRIORITY","WATCH"])].copy()
 if watch.empty:st.info("Tag players as DEVELOP, PRIORITY or WATCH below and they'll appear here.")
 else:st.dataframe(watch[["tag","player_name","source","start_ovr","current_ovr","OVR +","note"]],hide_index=True,use_container_width=True)
 st.subheader("Tag / note a player")
 labels={f'{r.player_name} · {int(r.player_id)}':int(r.player_id) for _,r in df.sort_values("player_name").iterrows()}
 choice=st.selectbox("Player",labels)
 ex=df[df.player_id==labels[choice]].iloc[0]
 tags=["NORMAL","DEVELOP","PRIORITY","WATCH"]
 tag=st.selectbox("Status",tags,index=tags.index(ex.tag) if ex.tag in tags else 0)
 note=st.text_input("Note",value=ex.note)
 if st.button("Save player status"):
  c.execute("""INSERT INTO tags(wallet,player_id,tag,note) VALUES(?,?,?,?)
  ON CONFLICT(wallet,player_id) DO UPDATE SET tag=excluded.tag,note=excluded.note""",(wallet,labels[choice],tag,note));c.commit();st.rerun()

with tab4:
 search=st.text_input("Search player")
 view=df.copy()
 if search:view=view[view.player_name.str.contains(search,case=False,na=False)]
 ownership=st.multiselect("Ownership",sorted(view.source.dropna().unique().tolist()))
 if ownership:view=view[view.source.isin(ownership)]
 sort=st.selectbox("Sort by",["OVR gain","Current OVR","Player"],index=0)
 if sort=="OVR gain":view=view.sort_values(["OVR +","current_ovr"],ascending=[False,False],na_position="last")
 elif sort=="Current OVR":view=view.sort_values("current_ovr",ascending=False)
 else:view=view.sort_values("player_name")
 st.dataframe(view[["tag","player_name","source","Acquired","History starts","start_ovr","current_ovr","OVR +","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +"]],
  hide_index=True,use_container_width=True,column_config={"player_name":"Player","source":"Ownership","start_ovr":"Start OVR","current_ovr":"Current OVR"})

st.caption("BOUGHT uses a verified marketplace acquisition into this wallet. NEW / ORIGINAL uses the player's MFL INITIAL state as the development baseline.")
c.close()
