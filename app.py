import os, streamlit as st, pandas as pd
import agency_backend as ab
st.set_page_config(page_title="MFL Agency Development",page_icon="🌱",layout="wide")
try:
    if "MFL_REFRESH_TOKEN" in st.secrets: os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception: pass
st.title("🌱 MFL Agency Development")
st.caption("Development during your ownership — not the player's previous managers.")
wallet=st.text_input("Dapper wallet address",placeholder="0x…").strip()
if wallet:
    if st.button("Load / update my agency",type="primary"):
        try:
            with st.spinner("Finding owned players and loading full MFL profiles…"):
                owned,loaded,errors=ab.sync_wallet(wallet)
            st.success(f"Found {owned} owned players · loaded {loaded} full profiles.")
            if errors: st.warning(f"{len(errors)} player profiles could not be refreshed this time.")
        except Exception as e: st.error(f"{type(e).__name__}: {e}")
    c=ab.db();ab.init(c)
    rows=c.execute("""SELECT o.player_id,o.player_name,o.started_at,o.start_ovr,o.start_pac,o.start_sho,o.start_pas,o.start_dri,o.start_def,o.start_phy,
    s.age,s.position,s.club,s.ovr,s.pac,s.sho,s.pas,s.dri,s.def,s.phy,COALESCE(t.tag,'NORMAL') tag,COALESCE(t.note,'') note
    FROM ownership o JOIN snapshots s ON s.id=(SELECT MAX(id) FROM snapshots q WHERE q.wallet=o.wallet AND q.player_id=o.player_id)
    LEFT JOIN tags t ON t.wallet=o.wallet AND t.player_id=o.player_id WHERE o.wallet=? AND o.ended_at IS NULL
    ORDER BY CASE WHEN s.ovr IS NULL OR o.start_ovr IS NULL THEN -999 ELSE s.ovr-o.start_ovr END DESC,s.ovr DESC""",(wallet.lower(),)).fetchall()
    if rows:
        df=pd.DataFrame([dict(x) for x in rows]); df["OVR +"]=df["ovr"]-df["start_ovr"]
        for short,cur,start in [("PAC +","pac","start_pac"),("SHO +","sho","start_sho"),("PAS +","pas","start_pas"),("DRI +","dri","start_dri"),("DEF +","def","start_def"),("PHY +","phy","start_phy")]:
            df[short]=df[cur]-df[start]
        a,b,c1=st.columns(3); a.metric("Players in agency",len(df)); b.metric("With full OVR",int(df.ovr.notna().sum())); c1.metric("Tagged prospects",int((df.tag!="NORMAL").sum()))
        filt=st.segmented_control("View",["ALL","NEW MINT","DEVELOP","PRIORITY","WATCH","NORMAL"],default="ALL")
        v=df if filt=="ALL" else df[df.tag==filt]
        st.dataframe(v[["tag","player_name","age","position","club","start_ovr","ovr","OVR +","PAC +","SHO +","PAS +","DRI +","DEF +","PHY +"]],
          hide_index=True,use_container_width=True,column_config={"player_name":"Player","start_ovr":"Tracking OVR","ovr":"Current OVR","tag":"Tag"})
        st.caption("Tracking OVR is currently the first valid snapshot we capture. Historical acquisition reconstruction comes next.")
        st.subheader("Mark a prospect")
        names={f'{r.player_name} ({r.player_id})':int(r.player_id) for _,r in df.iterrows()}; who=st.selectbox("Player",names)
        existing=df[df.player_id==names[who]].iloc[0]
        tags=["NEW MINT","DEVELOP","PRIORITY","WATCH","NORMAL"]; tag=st.selectbox("Tag",tags,index=tags.index(existing.tag) if existing.tag in tags else 4)
        note=st.text_input("Private note",value=existing.note)
        if st.button("Save tag"):
            c.execute("INSERT INTO tags(wallet,player_id,tag,note) VALUES(?,?,?,?) ON CONFLICT(wallet,player_id) DO UPDATE SET tag=excluded.tag,note=excluded.note",(wallet.lower(),names[who],tag,note));c.commit();st.rerun()
    c.close()
else: st.info("Enter a Dapper wallet to load an MFL agency.")
