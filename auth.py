import os
import requests
from dotenv import load_dotenv

API_BASE_URL = "https://api.topstepx.com"


def _load_credentials():
    """
    Local:
        Reads config.env

    Streamlit Cloud:
        Reads from st.secrets
    """

    # Local environment first
    load_dotenv("config.env")

    username = os.getenv("TOPSTEPX_USERNAME")
    api_key = os.getenv("PROJECTX_API_KEY")

    # If local env vars are not available, try Streamlit Secrets
    if not username or not api_key:
        try:
            import streamlit as st

            username = st.secrets.get(
                "TOPSTEPX_USERNAME",
                username,
            )

            api_key = st.secrets.get(
                "PROJECTX_API_KEY",
                api_key,
            )

        except Exception:
            pass

    if not username or not api_key:
        raise RuntimeError(
            "Missing TOPSTEPX_USERNAME or PROJECTX_API_KEY. "
            "Use config.env locally or Streamlit Secrets in deployment."
        )

    return username, api_key


def get_token():
    username, api_key = _load_credentials()

    response = requests.post(
        f"{API_BASE_URL}/api/Auth/loginKey",
        json={
            "userName": username,
            "apiKey": api_key,
        },
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("success"):
        raise RuntimeError(
            f"TopstepX authentication failed: "
            f"{data.get('errorMessage')}"
        )

    token = data.get("token")

    if not token:
        raise RuntimeError(
            "Authentication succeeded but no token was returned."
        )

    return token