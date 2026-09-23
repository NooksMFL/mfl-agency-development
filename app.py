import os, shutil, tempfile
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
    updated,counts=ab.fill_metadata_fast(wallet)
   st.success(f"Roster read successfully: {updated} players · Age {counts.get('ages',0)} · Position {counts.get('positions',0)} · Club {counts.get('clubs',0)}")
   st.rerun()
  except Exception as e:
   msg=str(e)
   if msg.startswith("MFL_RATE_LIMITED"):
    retry=msg.split("|",1)[1] if "|" in msg else ""
    st.warning("MFL is rate-limiting the roster request right now. Nothing has been lost. Try this button again later." + (f" Retry-After: {retry}s." if retry else ""))
   elif "timed out" in msg.lower() or "timeout" in msg.lower():
    st.warning("MFL did not answer within 12 seconds. Nothing has been changed; try again later.")
   else: st.error(f"{type(e).__name__}: {e}")
with top2:
 mc=ab.metadata_counts(wallet)
 st.caption(f"Already stored — Age: {mc.get('ages',0)} · Position: {mc.get('positions',0)} · Club: {mc.get('clubs',0)}. Existing metadata stays saved even if MFL rejects a new request.")

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

with st.expander("🛡️ Backup & diagnostics"):
 st.caption("Streamlit Community Cloud does not guarantee local SQLite persistence. Download a backup after major imports/refreshes so the 352-player history can be restored without rebuilding.")
 b1,b2=st.columns(2)
 with b1:
  try:
   with open(ab.DB,"rb") as fh:
    st.download_button("⬇️ Download agency database backup",data=fh.read(),file_name="agency_development_backup.db",mime="application/octet-stream")
  except Exception as e: st.caption(f"Backup unavailable: {e}")
 with b2:
  uploaded=st.file_uploader("Restore database backup",type=["db"],help="Use a backup created by this dashboard.")
  if uploaded is not None and st.button("Restore uploaded backup"):
   try:
    # Validate as SQLite before replacing live DB.
    import sqlite3
    tmp=tempfile.NamedTemporaryFile(delete=False,suffix=".db");tmp.write(uploaded.getvalue());tmp.close()
    test=sqlite3.connect(tmp.name);test.execute("PRAGMA quick_check").fetchone();test.close()
    shutil.copyfile(tmp.name,ab.DB)
    st.success("Database restored. Reloading dashboard…");st.rerun()
   except Exception as e: st.error(f"Backup could not be restored: {e}")

 st.divider()
 st.markdown("**🎮 Inspect MFL activity for one player**")
 st.caption("This lets us verify exactly what MFL labels as MATCH before we use it as 'games played'. It makes one progression-history request.")
 choices={f"{r.player_name} · {int(r.player_id)}":int(r.player_id) for _,r in df.sort_values("player_name").iterrows()}
 inspect_name=st.selectbox("Player to inspect",choices,key="activity_inspect")
 if st.button("Inspect activity"):
  try:
   with st.spinner("Reading progression history…"):
    diag=ab.inspect_activity_events(choices[inspect_name])
   st.write(f"Events: **{diag['event_count']}** · MATCH-labelled: **{diag['match_count']}**")
   st.write("Reason types:",diag["reasons"])
   if diag["sample_match"] is not None:
    st.markdown("**Raw MATCH event sample**")
    st.json(diag["sample_match"],expanded=True)
   else:
    st.info("No MATCH-labelled progression event was returned for this player.")
    st.markdown("**Latest raw progression events**")
    st.json(diag["sample_events"],expanded=True)
  except Exception as e:
   msg=str(e)
   if "429" in msg or "RATE_LIMIT" in msg: st.warning("MFL is rate-limiting this request. Try again after the cooldown.")
   else: st.error(f"{type(e).__name__}: {e}")

ac=ab.activity_counts(wallet)
st.markdown("### 🎮 Ownership match activity")
st.caption(f"Scanned {ac.get('scanned',0)} / {len(df)} players. MATCH means an MFL match-progression event, not yet a verified official appearance.")
ca,cb=st.columns([1,3])
with ca:
 if st.button("Scan next 10 activity"):
  try:
   with st.spinner("Reading 10 progression histories…"):
    done,stopped=ab.refresh_owned_activity_batch(wallet,10)
   good=sum(1 for x in done if "error" not in x)
   errors=[x for x in done if "error" in x]
   if stopped:
    st.warning(f"Saved {good} players, then MFL rate-limited the scan. Wait for the cooldown and press again.")
   elif errors:
    st.error(f"Saved {good} players; {len(errors)} failed. First error: {errors[0].get('error')}")
   else:
    st.success(f"Saved activity for {good} players.")
   st.rerun()
  except Exception as e: st.error(f"{type(e).__name__}: {e}")
with cb:
 st.caption("Safe/resumable: each player is saved immediately. Repeated presses continue with the least-recently scanned players.")

m1,m2,m3,m4,m5=st.columns(5)
activity_df=pd.DataFrame(ab.agency_v28(wallet))
if not df.empty and not activity_df.empty:
 activity_cols=["player_id","match_events_owned","last_match_at","days_since_match","activity_scanned_at"]
 available=[c for c in activity_cols if c in activity_df.columns]
 activity_small=activity_df[available].copy()
 # `load()` is the dashboard's presentation dataframe; find its player-id label safely.
 id_col=next((c for c in ["player_id","Player ID","ID"] if c in df.columns),None)
 if id_col and "player_id" in activity_small.columns:
  activity_small=activity_small.rename(columns={"player_id":id_col})
  df=df.merge(activity_small,on=id_col,how="left")
 else:
  # Rows originate from the same ownership table; index fallback preserves old UI schema.
  for c in ["match_events_owned","last_match_at","days_since_match","activity_scanned_at"]:
   if c in activity_df.columns and len(activity_df)==len(df):
    df[c]=activity_df[c].values
 if "match_events_owned" in df.columns:
  # Existing tabs use lowercase `match_events`; replace the old generic activity value
  # with the new ownership-spell MATCH count.
  df["match_events"]=df["match_events_owned"]
  df["Match events"]=df["match_events_owned"]
 if "days_since_match" in df.columns:
  # Existing `Days since activity` was based on ANY progression event (training etc.).
  # Needs Games must instead use the last ownership-spell MATCH event.
  df["Days since activity"]=df["days_since_match"]
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
 st.caption("Only scanned players have match-activity data. Match events are MFL progression-history events labelled MATCH during the current ownership spell; Days since activity means days since the latest such MATCH event.")
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

st.caption("Ownership development baselines: BOUGHT = verified purchase into this wallet; NEW / ORIGINAL = MFL INITIAL player state. Match activity is counted only from the current ownership baseline onward. MATCH is an MFL progression-history label and is not yet claimed as an official appearance count.")
c.close()
