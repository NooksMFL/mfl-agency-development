import os,streamlit as st
import diagnostic_backend as d
st.set_page_config(page_title="MFL Ownership Diagnostic",page_icon="🧪",layout="wide")
try:
 if "MFL_REFRESH_TOKEN" in st.secrets:os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception:pass
st.title("🧪 MFL Ownership / Acquisition Diagnostic")
st.caption("v5.2 — acquisition diagnostic with MFL listing-feed limit corrected to 25.")
wallet=st.text_input("Your Dapper wallet",value="0x65cc0e72dd71ad80")
pid=st.number_input("Player ID",min_value=1,step=1,value=374865)
if st.button("Check Arnt / this player",type="primary"):
 try:
  with st.spinner("Checking MFL history…"):r=d.diagnose(int(pid),wallet)
  st.success("MFL authentication and history requests succeeded.")
  a,b,c=st.columns(3);a.metric("Sale events",len(r["sales"]));b.metric("Progression events",len(r["experiences"]));c.metric("Acquired by this wallet",r["acquired"])
  st.write("**Last progression on/before acquisition:**",r["previous"])
  st.write("**First progression after acquisition:**",r["next"])
  st.subheader("Matched purchase event");st.json(r["event"] or {"result":"No matching purchase into this wallet found"})
  with st.expander("Raw sale history"):st.json(r["sales"])
  with st.expander("Raw progression history"):st.json(r["experiences"])
 except Exception as e:st.error(f"{type(e).__name__}: {e}")
