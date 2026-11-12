# Shortcuts. Each target is one plain command you can also run by hand.
setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
data:
	.venv/bin/python scripts/generate_samples.py
run:
	.venv/bin/python run.py
ui:
	.venv/bin/streamlit run app.py
eval:
	.venv/bin/python eval.py --scanned
test:
	.venv/bin/python -m pytest -q
