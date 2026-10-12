# BDACC_app

A Streamlit app for exploring Formula 1 history and comparing drivers.

## Install dependencies

From the `BDACC_app` folder in PowerShell, with Python 3.12 or newer installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you use `uv`, it can download Python and create the environment:

```powershell
uv venv --python 3.12 --seed .venv
uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt
```

## Run the app

```powershell
.\.venv\Scripts\python.exe -m streamlit run BDACC_proj_1.py
```

Keep the six dataset CSV files in `data/`, next to `BDACC_proj_1.py`.

## Push changes

Git tracks files inside folders, so a folder rename is included when you stage
the moved files. From the `BDACC_app` folder:

```powershell
git add -A
git commit -m "Rename dataset folder to data and document dependency setup"
git push origin main
```
