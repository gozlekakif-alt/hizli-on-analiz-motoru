"""V10 Streamlit start smoke test."""
from streamlit.testing.v1 import AppTest

app=AppTest.from_file("v10_app.py",default_timeout=180).run(timeout=180)
for exc in app.exception:
    raise AssertionError(f"Streamlit UI exception: {exc.message}")
assert len(app.title)>0,"Application title missing"
print("PASS: Streamlit V10 renders without exceptions")
