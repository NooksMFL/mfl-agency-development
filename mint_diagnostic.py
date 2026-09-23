import json
import streamlit as st
import agency_backend as ab

st.set_page_config(page_title="MFL New Mint Diagnostic",page_icon="🧪",layout="wide")
st.title("🧪 New Mint Diagnostic")
st.caption("Known test case: Leonardo Silvestri (411974). This page shows the raw MFL profile, sale history and experience-history event so we can identify the mint signature without guessing.")

wallet=st.text_input("Wallet",value="0x65cc0e72dd71ad80").strip()
pid=st.number_input("Player ID",min_value=1,value=411974,step=1)

if st.button("Inspect raw MFL data",type="primary"):
    try:
        t=ab.token()
        profile=ab.get(f"/players/{int(pid)}",t)
        sales=ab.sale_history(int(pid),t)
        exp=ab.exp_history(int(pid),t)

        st.success(f"Loaded player {int(pid)} · {len(sales)} sale event(s) · {len(exp)} experience-history event(s)")
        st.subheader("Classification clues")
        w=wallet.lower()
        buys=[]
        for e in sales:
            buyer=str(e.get("buyerAddress") or e.get("buyerWalletAddress") or "").lower()
            if buyer==w:
                buys.append(e)
        c1,c2,c3=st.columns(3)
        c1.metric("Sale events",len(sales))
        c2.metric("Purchases into this wallet",len(buys))
        c3.metric("Experience events",len(exp))

        st.subheader("Raw experience-history event(s)")
        st.json(exp,expanded=True)

        st.subheader("Raw sale history")
        st.json(sales,expanded=False)

        st.subheader("Raw profile")
        st.json(profile,expanded=False)

        st.info("Do not classify NEW MINT from 'one event' alone. We will use the exact fields/type/timestamp exposed above plus absence of a prior marketplace purchase, then encode that signature in the agency tracker.")
    except Exception as e:
        st.error(f"{type(e).__name__}: {e}")
