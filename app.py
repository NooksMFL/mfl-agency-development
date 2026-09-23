import os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import agency_backend as ab

st.set_page_config(page_title="MFL Agency Development",page_icon="🌱",layout="wide")
try:
 if "MFL_REFRESH_TOKEN" in st.secrets:os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception:pass

st.title("🌱 MFL Agency Development")
st.caption("Development management for your MFL agency.")
wallet=st.text_input("Dapper wallet",value="0x65cc0e72dd71ad80",label_visibility="collapsed").strip().lower()
c=ab.db();ab.init(c);ab.ensure_v2(c)

def load():
 rows=c.execute("""SELECT o.*,COALESCE(t.tag,'NORMAL') tag,COALESCE(t.note,'') note,
 m.age,m.position,m.club,a.last_event_at,a.match_events,a.training_events,a.total_events
 FROM ownership_v65 o
 LEFT JOIN tags t ON t.wallet=o.wallet AND t.player_id=o.player_id
 LEFT JOIN player_meta m ON m.wallet=o.wallet AND m.player_id=o.player_id
 LEFT JOIN activity a ON a.wallet=o.wallet AND a.player_id=o.player_id
 WHERE o.wallet=?""",(wallet,)).fetchall()
 if not rows:return pd.DataFrame()
 d=pd.DataFrame([dict(r) for r in rows])
 for lab,cur,start in [("OVR +","current_ovr","start_ovr"),("PAC +","current_pac","start_pac"),("SHO +","current_sho","start_sho"),
 ("PAS +","current_pas","start_pas"),("DRI +","current_dri","start_dri"),("DEF +","current_def","start_def"),("PHY +","current_phy","start_phy")]:
  d[lab]=pd.to_numeric(d[cur],errors="coerce")-pd.to_numeric(d[start],errors="coerce")
 d["Acquired"]=pd.to_datetime(d.acquired_at,utc=True,errors="coerce").dt.strftime("%d %b %Y")
 d["Initial date"]=pd.to_datetime(d.history_start,utc=True,errors="coerce").dt.strftime("%d %b %Y")
 last=pd.to_datetime(d.last_event_at,utc=True,errors="coerce")
 now=pd.Timestamp.now(tz="UTC")
 d["Days since activity"]=(now-last).dt.days
 d["Status"]=d.apply(status,axis=1)
 return d

def status(r):
 if r.get("tag")=="PRIORITY":return "⭐ PRIORITY"
 if r.get("tag")=="WATCH":return "👀 WATCH"
 if r.get("tag")=="DEVELOP":return "🌱 DEVELOP"
 if r.get("source")=="NEW MINT / ORIGINAL" and (pd.isna(r.get("OVR +")) or r.get("OVR +")==0):return "🆕 NEW MINT"
 if pd.notna(r.get("OVR +")) and r.get("OVR +")>0:return "🔥 DEVELOPING"
 days=r.get("Days since activity")
 if pd.notna(days) and days>=14:return "💤 DORMANT"
 return "⚪ NORMAL"

df=load()
if df.empty:
 st.warning("No agency data is stored on this Streamlit instance yet.")
 st.subheader("Build agency")
 st.caption("This will rebuild the historical ownership baseline automatically. You do not need the old importer.")
 if st.button("🚀 Build my agency",type="primary"):
  bar=st.progress(0,text="Starting agency import…")
  status=st.empty()
  def importprog(done,total,chunk):
   bar.progress(done/max(total,1),text=f"Building agency: {done}/{total}")
   status.caption(f"Completed batch {chunk}. Progress is saved after every batch.")
  try:
   result=ab.finish_import(wallet,importprog,chunk_size=12,pause_seconds=8,max_chunks=40)
   bar.empty();status.empty()
   if result["complete"]:
    st.success(f"Agency built: {result['analysed']}/{result['total']} players.")
   elif result["rate_limited"]:
    st.warning(f"MFL rate limit reached at {result['analysed']}/{result['total']}. Everything completed is saved. Wait a little, then press Continue agency build.")
   else:
    st.info(f"Build paused at {result['analysed']}/{result['total']}. Everything completed is saved; press the button again to continue.")
   st.rerun()
  except Exception as e:
   bar.empty();status.empty();st.error(f"{type(e).__name__}: {e}")
 st.stop()

# compact controls
# If the cache is only partially rebuilt, show a one-click continuation control.
try:
 live_total=len(ab.roster_ids(wallet,ab.token()))
except Exception:
 live_total=len(df)
if len(df) < live_total:
 st.info(f"Agency rebuild in progress: {len(df)}/{live_total} players stored.")
 if st.button("🚀 Continue agency build",type="primary"):
  bar=st.progress(0,text="Continuing agency import…")
  status=st.empty()
  def importprog(done,total,chunk):
   bar.progress(done/max(total,1),text=f"Building agency: {done}/{total}")
   status.caption(f"Completed batch {chunk}. Progress is saved after every batch.")
  try:
   result=ab.finish_import(wallet,importprog,chunk_size=12,pause_seconds=8,max_chunks=40)
   bar.empty();status.empty()
   if result["complete"]: st.success(f"Agency built: {result['analysed']}/{result['total']} players.")
   elif result["rate_limited"]: st.warning(f"Rate limit reached at {result['analysed']}/{result['total']}. Saved safely; continue later.")
   else: st.info(f"Paused at {result['analysed']}/{result['total']}. Saved safely.")
   st.rerun()
  except Exception as e:
   bar.empty();status.empty();st.error(f"{type(e).__name__}: {e}")

top1,top2=st.columns([1,3])
with top1:
 if st.button("⚡ Fill age / position / club",type="primary"):
  try:
   with st.spinner("Reading current agency roster…"):
    updated=ab.fill_metadata_from_roster(wallet)
   st.success(f"Metadata loaded for {updated} roster players from one MFL roster request.")
   st.rerun()
  except Exception as e:st.error(f"{type(e).__name__}: {e}")
with top2:
 mc=ab.metadata_counts(wallet)
 st.caption(f"Metadata stored — Age: {mc.get('ages',0)} · Position: {mc.get('positions',0)} · Club: {mc.get('clubs',0)}. This uses the bulk roster response instead of opening every player individually.")

with st.expander("Current stats & activity refresh"):
 st.caption("This is the slower per-player job. It is optional for metadata and can be resumed safely in small batches.")
 if st.button("Refresh next 20 current/activity"):
  bar=st.progress(0,text="Refreshing next 20…")
  def prog(n,total):bar.progress(n/max(total,1),text=f"Refreshing {n}/{total}…")
  try:
   done,total,errs=ab.refresh_current_v21(wallet,prog,20);bar.empty()
   if errs:st.warning(f"Updated {done} players; {len(errs)} issue(s). Press again later to continue.")
   else:st.success(f"Updated {done} players. Press again when you want the next least-recently refreshed group.")
   st.rerun()
  except Exception as e:bar.empty();st.error(f"{type(e).__name__}: {e}")

df=load()
m1,m2,m3,m4,m5=st.columns(5)
m1.metric("Players",len(df));m2.metric("Improved OVR",int((df["OVR +"]>0).sum()))
m3.metric("New / original",int((df.source=="NEW MINT / ORIGINAL").sum()))
m4.metric("Bought",int((df.source=="BOUGHT").sum()))
m5.metric("Priority",int((df.tag=="PRIORITY").sum()))

tabs=st.tabs(["🏆 Development","🎮 Needs Games","🆕 New Mints","⭐ My List","👥 Agency"])
with tabs[0]:
 st.subheader("Top developers")
 v=df[df["OVR +"]>0].sort_values(["OVR +","current_ovr"],ascending=False)
 st.dataframe(v[["Status","player_name","age","position","start_ovr","current_ovr","OVR +","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +"]],
  hide_index=True,use_container_width=True,column_config={"player_name":"Player","age":"Age","position":"Position","start_ovr":"Start","current_ovr":"Current"})
with tabs[1]:
 st.subheader("Needs games / attention")
 st.caption("This becomes more accurate as players are refreshed. 'Match events' currently comes directly from MFL progression-history events labelled MATCH.")
 need=df.copy()
 need["match_events"]=pd.to_numeric(need.match_events,errors="coerce")
 need=need[(need.tag.isin(["DEVELOP","PRIORITY","WATCH"])) | (need.source=="NEW MINT / ORIGINAL")]
 need=need.sort_values(["match_events","Days since activity","age"],ascending=[True,False,True],na_position="last")
 st.dataframe(need[["Status","player_name","age","current_ovr","OVR +","match_events","Days since activity","tag","note"]],
  hide_index=True,use_container_width=True,column_config={"player_name":"Player","current_ovr":"OVR","match_events":"Match events"})
with tabs[2]:
 mint=df[df.source=="NEW MINT / ORIGINAL"].sort_values(["OVR +","current_ovr"],ascending=False)
 st.dataframe(mint[["Status","player_name","age","Initial date","start_ovr","current_ovr","OVR +","match_events","Days since activity"]],
  hide_index=True,use_container_width=True,column_config={"player_name":"Player","start_ovr":"Initial","current_ovr":"Current"})
with tabs[3]:
 mine=df[df.tag!="NORMAL"]
 if mine.empty:st.info("No manual development tags yet.")
 else:st.dataframe(mine[["tag","player_name","age","current_ovr","OVR +","match_events","note"]],hide_index=True,use_container_width=True)
 st.subheader("Player status")
 opts={f"{r.player_name} · {int(r.player_id)}":int(r.player_id) for _,r in df.sort_values("player_name").iterrows()}
 who=st.selectbox("Player",opts);ex=df[df.player_id==opts[who]].iloc[0]
 tags=["NORMAL","DEVELOP","PRIORITY","WATCH"];tag=st.selectbox("Tag",tags,index=tags.index(ex.tag) if ex.tag in tags else 0)
 note=st.text_input("Note",value=ex.note)
 if st.button("Save"):
  c.execute("""INSERT INTO tags(wallet,player_id,tag,note) VALUES(?,?,?,?) ON CONFLICT(wallet,player_id)
  DO UPDATE SET tag=excluded.tag,note=excluded.note""",(wallet,opts[who],tag,note));c.commit();st.rerun()
with tabs[4]:
 q=st.text_input("Search")
 v=df if not q else df[df.player_name.str.contains(q,case=False,na=False)]
 sort=st.selectbox("Sort",["OVR gain","OVR","Age","Name"])
 if sort=="OVR gain":v=v.sort_values(["OVR +","current_ovr"],ascending=False,na_position="last")
 elif sort=="OVR":v=v.sort_values("current_ovr",ascending=False)
 elif sort=="Age":v=v.sort_values("age",na_position="last")
 else:v=v.sort_values("player_name")
 st.dataframe(v[["Status","player_name","age","position","club","source","Acquired","start_ovr","current_ovr","OVR +","match_events","Days since activity"]],
  hide_index=True,use_container_width=True,column_config={"player_name":"Player","age":"Age","position":"Position","club":"Club","source":"Ownership","current_ovr":"OVR","start_ovr":"Start","match_events":"Match events"})

st.caption("Ownership development baselines: BOUGHT = verified purchase into this wallet; NEW / ORIGINAL = MFL INITIAL player state. Match-event counts are based on MFL progression history and are not yet restricted to official league fixtures.")
c.close()
