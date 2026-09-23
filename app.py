import os, shutil, tempfile
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import agency_backend as ab



def valid_wallet_address(value):
    v=(value or "").strip()
    return len(v) >= 10 and v.lower().startswith("0x") and all(ch in "0123456789abcdefABCDEF" for ch in v[2:])

st.set_page_config(page_title="MFL Agency Development",page_icon="🌱",layout="wide")
try:
 if "MFL_REFRESH_TOKEN" in st.secrets:os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception:pass

st.title("🌱 MFL Agency Development")
st.caption("Track how your MFL players develop while they are in your agency.")


with st.expander("🔐 MFL authentication diagnostic"):
    st.caption("Read-only test. It does not change your token or agency database, and token values are never displayed.")
    if st.button("Run authentication diagnostic"):
        with st.spinner("Testing MFL authentication safely…"):
            auth_diag=ab.auth_diagnostic()
        if auth_diag.get("refresh_token_present"):
            st.write(f"Refresh token present: **Yes** · shape: **{auth_diag.get('refresh_token_shape')}** · length: **{auth_diag.get('refresh_token_length')}**")
        else:
            st.error("MFL_REFRESH_TOKEN is missing from Streamlit Secrets.")
        for test in auth_diag.get("tests",[]):
            status=test.get("status")
            if status in (200,201):
                st.success(f"{test.get('name')}: HTTP {status} — authentication accepted.")
            elif status in (401,403):
                st.error(f"{test.get('name')}: HTTP {status} — token/authentication rejected.")
            elif status == 429:
                st.warning(f"{test.get('name')}: HTTP 429 — rate limited. Retry-After: {test.get('retry_after')}")
            elif status and status >= 500:
                st.warning(f"{test.get('name')}: HTTP {status} — MFL server failed while processing the request.")
            else:
                st.info(f"{test.get('name')}: no conclusive HTTP result.")
            with st.expander(f"Technical result · {test.get('name')}"):
                st.json(test)

st.subheader("Load your agency")
st.write("Enter your **Dapper wallet address** below. You do not need to sign in or enter an MFL token.")

wallet_input=st.text_input(
    "Dapper wallet address",
    value=st.session_state.get("agency_wallet",""),
    placeholder="0x…",
    help="Use the Dapper wallet address that owns your MFL players.",
).strip()

load_wallet=st.button("🔎 Load my agency",type="primary")

if load_wallet:
    if not wallet_input:
        st.error("Enter your Dapper wallet address first.")
    elif not valid_wallet_address(wallet_input):
        st.error("That doesn't look like a valid wallet address. It should begin with 0x.")
    else:
        st.session_state["agency_wallet"]=wallet_input.lower()
        st.rerun()

wallet=st.session_state.get("agency_wallet","").strip().lower()

if not wallet:
    st.info("Your agency will appear here after you enter your wallet address.")
    st.stop()

left_wallet,right_wallet=st.columns([4,1])
with left_wallet:
    st.caption(f"Loaded wallet: `{wallet}`")
with right_wallet:
    if st.button("Change wallet"):
        st.session_state.pop("agency_wallet",None)
        st.rerun()

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
 st.info("This wallet has not been imported into the tracker yet.")
 st.subheader("Build agency")
 st.caption("Build this agency from its current MFL roster and historical ownership data. Progress is saved after each batch.")
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
scanned=int(ac.get("scanned") or 0); total=len(df); remaining=max(0,total-scanned)
st.progress((scanned/total) if total else 0.0,text=f"{scanned} / {total} players scanned · {remaining} remaining")
st.caption("MATCH means an MFL match-progression event during the current ownership spell, not yet a verified official appearance.")
ca,cb,cc=st.columns([1,1,3])
with ca:
 batch=st.selectbox("Batch size",[5,10,15],index=1,label_visibility="collapsed")
with cb:
 if st.button(f"Scan next {batch}",use_container_width=True,disabled=(remaining==0)):
  try:
   with st.spinner(f"Reading up to {batch} unscanned progression histories…"):
    done,stopped=ab.refresh_unscanned_activity_batch(wallet,batch)
   good=sum(1 for x in done if "error" not in x)
   errors=[x for x in done if "error" in x]
   if stopped:
    st.warning(f"Saved {good} player(s), then MFL rate-limited the scan. Nothing completed was lost.")
   elif errors:
    st.error(f"Saved {good}; {len(errors)} failed. First error: {errors[0].get('error')}")
   elif good:
    st.success(f"Saved activity for {good} new player(s).")
   else:
    st.info("No unscanned players remain.")
   st.rerun()
  except Exception as e: st.error(f"{type(e).__name__}: {e}")
with cc:
 if remaining:
  st.caption("Resumable queue: this now scans only players not already completed. It will not loop back over earlier players.")
 else:
  st.success("Activity scan complete for the current agency.")

if remaining:
 st.markdown("#### Or finish it automatically")
 st.caption("One click works through every remaining unscanned player. If MFL rate-limits the app, it waits for the cooldown and continues. Keep this browser tab open while it runs.")
 if st.button(f"🚀 Finish activity scan ({remaining} remaining)",type="primary",use_container_width=True):
  bar=st.progress(scanned/total if total else 0.0,text=f"Starting from {scanned}/{total}…")
  status=st.empty()
  def _progress(done_run,total_run,name,wait):
   overall=scanned+done_run
   frac=min(1.0,overall/total) if total else 1.0
   if wait and wait>0:
    status.warning(f"MFL rate limit reached at {overall}/{total}. Waiting about {wait} seconds, then continuing automatically…")
    bar.progress(frac,text=f"{overall} / {total} saved · cooling down…")
   elif wait == -1:
    status.warning(f"Skipped an error for {name}; continuing.")
   else:
    status.info(f"Saved {name} · {overall}/{total}")
    bar.progress(frac,text=f"{overall} / {total} players scanned")
  try:
   result=ab.finish_activity_scan(wallet,_progress)
   if result["errors"]:
    st.warning(f"Finished this run with {result['completed']} newly saved and {len(result['errors'])} player error(s).")
   else:
    st.success(f"Activity scan complete — {scanned + result['completed']} / {total}.")
   st.rerun()
  except Exception as e:
   st.error(f"{type(e).__name__}: {e}")
   st.info("Anything completed before the error is already saved. Press Finish activity scan again to resume.")


with st.expander("🔎 Real match-history API diagnostic"):
 st.caption("MFL MATCH progression is not a reliable appearance count. Use this on a player you know has played; it tests first-party MFL routes only and does not alter the database.")
 probe_choices={f"{r.player_name} · {int(r.player_id)}":int(r.player_id) for _,r in df.sort_values("player_name").iterrows()}
 probe_name=st.selectbox("Known player who has played matches",probe_choices,key="match_api_probe")
 st.caption(f"Backend: {getattr(ab, 'APP_BACKEND_VERSION', 'older version loaded')}")
 if st.button("Probe match API"):
  try:
   if not hasattr(ab,"probe_match_endpoints"):
    st.error("Streamlit is still running the older agency_backend.py. Confirm both files were replaced, then reboot the app.")
    st.stop()
   with st.spinner("Testing MFL match-history routes…"):
    probe=ab.probe_match_endpoints(probe_choices[probe_name])
   for result in probe:
    status=result.get("status","error")
    with st.expander(f"{status} · {result.get('path')}",expanded=(status==200)):
     st.json(result,expanded=True)
  except Exception as e:
   st.error(f"{type(e).__name__}: {e}")


with st.expander("🛠️ Advanced API diagnostics — testing only"):
 st.caption("We confirmed /matches/feed is real, but playerId is ignored. This tests likely query parameter names on that known route and shows only compact samples.")
 target_player=st.number_input("Target player ID",min_value=1,value=144031,step=1,key="target_feed_player")
 target_club=st.number_input("Known club ID (optional)",min_value=0,value=0,step=1,key="target_feed_club")
 target_squad=st.number_input("Known squad ID (optional)",min_value=0,value=0,step=1,key="target_feed_squad")
 if st.button("Test feed filters"):
  try:
   with st.spinner("Testing query parameters on /matches/feed…"):
    feed_probe=ab.probe_match_feed_filters(int(target_player),int(target_club) or None,int(target_squad) or None)
   st.json(feed_probe,expanded=True)
  except Exception as e:
   st.error(f"{type(e).__name__}: {e}")


with st.expander("🛠️ Club-history diagnostic — testing only"):
 st.caption("MFL's public club pages definitely expose Latest Matches, Schedule and History. Enter a real club ID from an MFL club URL; squad ID is optional.")
 hist_club=st.number_input("Club ID from app.playmfl.com/clubs/…",min_value=1,value=8172,step=1,key="hist_club")
 hist_squad=st.number_input("Squad ID (optional)",min_value=0,value=0,step=1,key="hist_squad")
 if st.button("Probe club history"):
  try:
   with st.spinner("Testing club/squad history routes…"):
    hist_probe=ab.probe_club_history(int(hist_club),int(hist_squad) or None)
   for result in hist_probe:
    status=result.get("status","error")
    with st.expander(f"{status} · {result.get('path')} · {result.get('params')}",expanded=(status==200)):
     st.json(result,expanded=True)
  except Exception as e:
   st.error(f"{type(e).__name__}: {e}")

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
 # Friendly activity display values while retaining numeric source columns.
 scanned_mask=df["activity_scanned_at"].notna() if "activity_scanned_at" in df.columns else pd.Series(False,index=df.index)
 if "Match events" in df.columns:
  df["Match activity"]=df["Match events"].apply(lambda x: "—" if pd.isna(x) else str(int(x)))
 if "Days since activity" in df.columns:
  df["Last match"]=df.apply(
   lambda r: ("Not scanned" if not bool(scanned_mask.loc[r.name])
              else ("Never" if pd.isna(r.get("Days since activity"))
                    else ("Today" if int(r.get("Days since activity"))==0
                          else f"{int(r.get('Days since activity'))} days ago"))),axis=1)
m1.metric("Players",len(df));m2.metric("Improved OVR",int((df["OVR +"]>0).sum()))
m3.metric("New / original",int((df.source=="NEW MINT / ORIGINAL").sum()))
m4.metric("Bought",int((df.source=="BOUGHT").sum()))
m5.metric("Priority",int((df.tag=="PRIORITY").sum()))

# Needs-games priority: scanned players with no MATCH activity first, then oldest last MATCH.
if not df.empty:
 df["_needs_scanned"]=df["activity_scanned_at"].notna() if "activity_scanned_at" in df.columns else False
 df["_needs_never"]=df["_needs_scanned"] & df["match_events_owned"].fillna(0).eq(0) if "match_events_owned" in df.columns else False
 df["_needs_days"]=df["days_since_match"].fillna(10**6) if "days_since_match" in df.columns else 0
tabs=st.tabs(["🏆 Development","🎮 Needs Games","🆕 New Mints","⭐ My List","👥 Agency"])
with tabs[0]:
 st.subheader("Top developers")
 v=df[df["OVR +"]>0].sort_values(["OVR +","current_ovr"],ascending=False)
 st.dataframe(v[["Status","player_name","age","position","start_ovr","current_ovr","OVR +","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +"]],
  hide_index=True,use_container_width=True,column_config={"player_name":"Player","age":"Age","position":"Position","start_ovr":"Start","current_ovr":"Current"})
with tabs[1]:
 st.subheader("🎮 Match progression activity")
 st.caption("Temporary diagnostic view. We have confirmed that MFL MATCH progression events are not a reliable appearance count, so 0 here does not mean 0 games played.")

 ng=df.copy()
 if ng.empty:
  st.info("No agency data available.")
 else:
  # Resolve presentation-column names once so the view works with the existing dashboard schema.
  player_col=next((c for c in ["Player","player_name","Name"] if c in ng.columns),None)
  age_col=next((c for c in ["Age","age"] if c in ng.columns),None)
  pos_col=next((c for c in ["Position","position"] if c in ng.columns),None)
  club_col=next((c for c in ["Club","club"] if c in ng.columns),None)
  ovr_col=next((c for c in ["Current","OVR","current_ovr"] if c in ng.columns),None)
  gain_col=next((c for c in ["OVR +","ovr_gain"] if c in ng.columns),None)
  own_col=next((c for c in ["Ownership","source"] if c in ng.columns),None)

  for c in [age_col,ovr_col,gain_col,"match_events_owned","days_since_match"]:
   if c and c in ng.columns: ng[c]=pd.to_numeric(ng[c],errors="coerce")

  scanned=ng["activity_scanned_at"].notna() if "activity_scanned_at" in ng.columns else pd.Series(False,index=ng.index)
  matches=ng["match_events_owned"] if "match_events_owned" in ng.columns else pd.Series(float("nan"),index=ng.index)
  days=ng["days_since_match"] if "days_since_match" in ng.columns else pd.Series(float("nan"),index=ng.index)

  def attention_reason(i):
   if not bool(scanned.loc[i]): return "⚪ NOT SCANNED"
   m=matches.loc[i]; d=days.loc[i]
   age=ng.at[i,age_col] if age_col else None
   status=str(ng.at[i,"Status"]) if "Status" in ng.columns else ""
   tag=str(ng.at[i,"tag"]).upper() if "tag" in ng.columns and pd.notna(ng.at[i,"tag"]) else "NORMAL"
   if tag=="PRIORITY": return "⭐ PRIORITY"
   if pd.isna(m) or int(m)==0:
    if "NEW MINT" in status and pd.notna(age) and age<=23: return "🆕 NEW MINT · NO MATCH PROGRESSION"
    return "⚠️ NO MATCH PROGRESSION"
   if pd.notna(d) and d>=30: return "🔴 30+ DAYS"
   if pd.notna(d) and d>=14: return "🟠 14–29 DAYS"
   if tag=="DEVELOP": return "🏷️ DEVELOP"
   if tag=="WATCH": return "👀 WATCH"
   return "🟢 RECENT"

  ng["Attention"]=pd.Series({i:attention_reason(i) for i in ng.index})
  order={"⭐ PRIORITY":0,"🆕 NEW MINT · NO MATCH PROGRESSION":1,"⚠️ NO MATCH PROGRESSION":2,
         "🔴 30+ DAYS":3,"🟠 14–29 DAYS":4,"🏷️ DEVELOP":5,
         "👀 WATCH":6,"🟢 RECENT":7,"⚪ NOT SCANNED":8}
  ng["_attention_order"]=ng["Attention"].map(order).fillna(9)

  # Summary metrics.
  c1,c2,c3,c4,c5=st.columns(5)
  c1.metric("New mints · no match",int((ng["Attention"]=="🆕 NEW MINT · NO MATCH PROGRESSION").sum()))
  c2.metric("Other · no match",int((ng["Attention"]=="⚠️ NO MATCH PROGRESSION").sum()))
  c3.metric("30+ days",int((ng["Attention"]=="🔴 30+ DAYS").sum()))
  c4.metric("14–29 days",int((ng["Attention"]=="🟠 14–29 DAYS").sum()))
  c5.metric("Recent",int((ng["Attention"]=="🟢 RECENT").sum()))

  st.markdown("#### Quick views")
  q1,q2,q3,q4=st.columns(4)
  young_only=q1.toggle("23 & under",value=False)
  developing_only=q2.toggle("Developing only",value=False)
  no_match_only=q3.toggle("No match progression",value=False)
  stale_only=q4.toggle("14+ days / never",value=False)

  with st.expander("More filters",expanded=False):
   f1,f2,f3,f4=st.columns(4)
   with f1:
    att=st.selectbox("Attention",["All"]+[x for x in order if x in set(ng["Attention"])])
   with f2:
    positions=sorted({p.strip() for v in ng[pos_col].dropna().astype(str) for p in v.split("/") if p.strip()}) if pos_col else []
    pos=st.selectbox("Position",["All"]+positions)
   with f3:
    ownership_values=sorted(ng[own_col].dropna().astype(str).unique().tolist()) if own_col else []
    ownership=st.selectbox("Ownership",["All"]+ownership_values)
   with f4:
    clubs=sorted(ng[club_col].dropna().astype(str).unique().tolist()) if club_col else []
    club=st.selectbox("Club",["All"]+clubs)

   f5,f6=st.columns(2)
   with f5:
    tags=["All"]+sorted(ng["tag"].dropna().astype(str).unique().tolist()) if "tag" in ng.columns else ["All"]
    tag_filter=st.selectbox("Tag",tags)
   with f6:
    sort_choice=st.selectbox("Sort by",["Needs attention","Longest since match","Fewest match events","Youngest","OVR gain"])
  # Defaults when expander widgets exist but no special selection.
  view=ng.copy()
  if young_only and age_col: view=view[view[age_col].fillna(999)<=23]
  if developing_only and "Status" in view.columns: view=view[view["Status"].astype(str).str.contains("DEVELOPING",na=False)]
  if no_match_only: view=view[view["match_events_owned"].fillna(0).eq(0) & view["activity_scanned_at"].notna()]
  if stale_only: view=view[(view["activity_scanned_at"].notna()) & (view["match_events_owned"].fillna(0).eq(0) | view["days_since_match"].fillna(-1).ge(14))]

  if att!="All": view=view[view["Attention"]==att]
  if pos!="All" and pos_col:
   view=view[view[pos_col].fillna("").astype(str).apply(lambda x: pos in [p.strip() for p in x.split("/")])]
  if ownership!="All" and own_col: view=view[view[own_col].astype(str)==ownership]
  if club!="All" and club_col: view=view[view[club_col].astype(str)==club]
  if tag_filter!="All" and "tag" in view.columns: view=view[view["tag"].astype(str)==tag_filter]

  if sort_choice=="Needs attention":
   view=view.sort_values(["_attention_order","days_since_match"],ascending=[True,False],na_position="last")
  elif sort_choice=="Longest since match":
   view=view.sort_values("days_since_match",ascending=False,na_position="last")
  elif sort_choice=="Fewest match events":
   view=view.sort_values(["match_events_owned","days_since_match"],ascending=[True,False],na_position="last")
  elif sort_choice=="Youngest" and age_col:
   view=view.sort_values(age_col,ascending=True,na_position="last")
  elif sort_choice=="OVR gain" and gain_col:
   view=view.sort_values(gain_col,ascending=False,na_position="last")

  view["Match activity"]=view.apply(
   lambda r:"Not scanned" if pd.isna(r.get("activity_scanned_at"))
   else ("0 · Never" if pd.isna(r.get("match_events_owned")) or int(r.get("match_events_owned"))==0
         else str(int(r.get("match_events_owned")))),axis=1)
  view["Last match"]=view.apply(
   lambda r:"Not scanned" if pd.isna(r.get("activity_scanned_at"))
   else ("Never" if pd.isna(r.get("days_since_match"))
         else ("Today" if int(r.get("days_since_match"))==0 else f"{int(r.get('days_since_match'))} days ago")),axis=1)

  # Create explicit stable display columns; this fixes the missing Player/Position/Club issue.
  display=pd.DataFrame(index=view.index)
  display["Attention"]=view["Attention"]
  if player_col: display["Player"]=view[player_col]
  if "Status" in view.columns: display["Status"]=view["Status"]
  if age_col: display["Age"]=view[age_col]
  if pos_col: display["Position"]=view[pos_col]
  if club_col: display["Club"]=view[club_col]
  if ovr_col: display["OVR"]=view[ovr_col]
  if gain_col: display["OVR +"]=view[gain_col]
  display["Match activity"]=view["Match activity"]
  display["Last match"]=view["Last match"]
  if own_col: display["Ownership"]=view[own_col]
  if "tag" in view.columns: display["Tag"]=view["tag"]
  if "note" in view.columns: display["Note"]=view["note"]

  st.markdown(f"#### Players shown · {len(display)}")
  st.dataframe(display,use_container_width=True,hide_index=True,height=560)
  st.caption("Attention buckets are workflow flags, not player-quality ratings. 'Never' means no MFL MATCH progression event was found. It does NOT mean the player never played.")

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
