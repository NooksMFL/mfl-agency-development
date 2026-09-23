import os, json, streamlit as st
import diagnostic_backend as d
st.set_page_config(page_title="MFL Ownership Diagnostic",page_icon="🧪",layout="wide")
try:
    if "MFL_REFRESH_TOKEN" in st.secrets:os.environ["MFL_REFRESH_TOKEN"]=st.secrets["MFL_REFRESH_TOKEN"]
except Exception:pass
st.title("🧪 MFL Ownership / Acquisition Diagnostic")
st.caption("v5 test page — verify acquisition dates and reconstructed starting ratings before applying them to the whole agency.")
wallet=st.text_input("Your Dapper wallet",value="0x65cc0e72dd71ad80")
pid=st.number_input("Player ID",min_value=1,step=1,value=411569)
if st.button("Check this player",type="primary"):
    try:
        with st.spinner("Checking MFL sale + progression history…"):r=d.diagnose(int(pid),wallet)
        st.success(r["name"])
        a,b,c=st.columns(3);a.metric("Sale events returned",r["sale_count"]);b.metric("Progression events",r["experience_count"]);c.metric("Acquired by this wallet",r["acquired"])
        st.subheader("Reconstructed ratings at acquisition")
        st.json(r["state"])
        st.write("**Last progression on/before acquisition:**",r["previous_progression"])
        st.write("**First progression after acquisition:**",r["next_progression"])
        st.subheader("Matched purchase event")
        st.json(r["sale_event"] if r["sale_event"] else {"result":"No BUY event into this wallet found in returned sale history"})
        with st.expander("Raw sale history"):
            st.json(r["sales"])
        with st.expander("Raw progression history"):
            st.json(r["experiences"])
    except Exception as e:st.error(f"{type(e).__name__}: {e}")
