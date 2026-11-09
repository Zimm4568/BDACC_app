"""Check HTTPS health and execute the deployed dashboard through a Streamlit session.

Run with the same Python environment used for the dashboard:
    python scripts/verify-app.py https://<app>.azurewebsites.net
"""

import argparse
import json
import time
from urllib.parse import urlsplit

import requests
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect


def verify(url):
    url = url.rstrip("/")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("Supply the deployed dashboard's HTTPS URL.")

    session = requests.Session()
    health = session.get(f"{url}/_stcore/health", timeout=120)
    health.raise_for_status()
    if health.text.strip() != "ok":
        raise RuntimeError(f"Unexpected health response: {health.text[:200]}")
    page = session.get(url, timeout=60)
    page.raise_for_status()

    headers = {}
    if session.cookies:
        headers["Cookie"] = "; ".join(
            f"{cookie.name}={cookie.value}" for cookie in session.cookies
        )

    metrics = []
    charts = 0
    text = []
    exceptions = []
    messages = 0
    started = time.monotonic()
    with connect(
        f"wss://{parts.netloc}/_stcore/stream",
        origin=url,
        subprotocols=["streamlit"],
        additional_headers=headers,
        open_timeout=60,
        max_size=20 * 1024 * 1024,
    ) as socket:
        request = BackMsg()
        request.rerun_script.query_string = ""
        socket.send(request.SerializeToString())

        while time.monotonic() - started < 180:
            payload = socket.recv(timeout=60)
            if not isinstance(payload, bytes):
                continue
            message = ForwardMsg()
            message.ParseFromString(payload)
            messages += 1
            if message.HasField("delta") and message.delta.HasField("new_element"):
                element = message.delta.new_element
                if element.HasField("exception"):
                    exceptions.append(element.exception.message)
                if element.HasField("metric"):
                    metrics.append({"label": element.metric.label, "value": element.metric.body})
                if element.HasField("plotly_chart"):
                    charts += 1
                if element.HasField("markdown"):
                    text.append(element.markdown.body)
            if message.HasField("script_finished"):
                break
        else:
            raise RuntimeError("Streamlit did not complete the dashboard run within 180 seconds.")

    if exceptions:
        raise RuntimeError(f"Dashboard raised exceptions: {exceptions}")
    if len(metrics) < 4 or charts < 2:
        raise RuntimeError(f"Dashboard content incomplete: {len(metrics)} metrics, {charts} charts.")
    if not any("THE GREATEST FORMULA 1 DRIVER?" in item for item in text):
        raise RuntimeError("The expected F1 dashboard heading was not rendered.")

    print(json.dumps({
        "url": url,
        "health": health.text.strip(),
        "websocket_session": "passed",
        "metrics": metrics,
        "plotly_charts": charts,
        "exceptions": exceptions,
        "messages_received": messages,
        "session_seconds": round(time.monotonic() - started, 1),
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    verify(parser.parse_args().url)
