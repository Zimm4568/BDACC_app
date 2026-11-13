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

## Deploy to Azure for Students

The Terraform configuration follows the supplied CLI deployment guide, adapted
for this Python Streamlit dashboard. It creates separate Linux App Service
environments: `dev` uses the free `F1` plan and `prod` uses the paid `B1` plan.
Production consumes Azure credit while the plan exists, even when the app is
stopped. No database or storage account is needed: the CSV files travel with
the application.

### Deployment status

The dev and prod Azure environments, including their App Service plans and
resource groups, were removed on November 13, 2026.

### Sign in and check the region

Install Azure CLI and Terraform, then run these commands from this folder:

```powershell
az login
az account list --output table
az account set --subscription "Azure for Students"
$env:ARM_SUBSCRIPTION_ID = az account show --query id --output tsv
az account show --output table
az policy assignment list --scope "/subscriptions/$env:ARM_SUBSCRIPTION_ID" --disable-scope-strict-match --output json
az provider register --namespace Microsoft.Web --wait
```

Use the account that owns the student subscription. If device-code login is
blocked by university policy, use standard `az login` and its account picker.
The region in both `environments/dev.tfvars` and `environments/prod.tfvars`
must appear in the subscription's **Allowed resource deployment regions**
policy. Both environments use `francecentral`, as requested. France Central
is policy-allowed and had quota for one F1 instance and one B1 instance when
checked on November 13, 2026. An actual F1 plan creation test also succeeded.

### Deploy and verify dev

```powershell
terraform init
terraform workspace select -or-create dev
terraform workspace show
terraform plan '-var-file=environments/dev.tfvars' '-out=dev.tfplan'
# Review the saved plan: only the F1 dashboard dev resources should be added.
terraform apply dev.tfplan
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package-app.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy-app.ps1 -Environment dev
$devUrl = terraform output -raw web_app_url
Invoke-RestMethod "$devUrl/_stcore/health"
.\.venv\Scripts\python.exe scripts/verify-app.py $devUrl
Start-Process $devUrl
```

The package script includes only the application, `requirements.txt`,
`startup.sh`, and all six CSVs. Azure installs the Python dependencies during
ZIP deployment. App Service runs `sh startup.sh`, which starts Streamlit on
`0.0.0.0:8000`; browser sessions
use WebSockets. Check that the charts, ranking, and driver comparison load in
the browser; an HTTP response alone does not verify a Streamlit session.
The free environment can take time to wake up after inactivity.

### Promote the same package to prod

After dev works, deploy the existing `artifacts/app.zip` to prod:

```powershell
terraform workspace select -or-create prod
terraform workspace show
terraform plan '-var-file=environments/prod.tfvars' '-out=prod.tfplan'
# Review the saved plan and the B1 plan before applying it.
terraform apply prod.tfplan
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy-app.ps1 -Environment prod
$prodUrl = terraform output -raw web_app_url
Invoke-RestMethod "$prodUrl/_stcore/health"
.\.venv\Scripts\python.exe scripts/verify-app.py $prodUrl
Start-Process $prodUrl
```

If Azure reports a quota shortage in France Central, resolve it with Azure
support or use an authorized subscription with capacity there, then regenerate
the affected plan. Do not apply a plan containing unexpected resource deletions
or changes to other projects.

`scripts/verify-app.py` checks HTTPS health and runs a real Streamlit session
over WebSockets, requiring the dashboard heading, charts, metrics, and no
Python exceptions. It uses the dashboard's existing Python dependencies.

### Keep state and remove environments when finished

Terraform state stays in the local `terraform.tfstate.d/` folder. Preserve it
and back it up securely; it is required to manage or remove these deployments.
State, plans, provider downloads, and deployment packages are ignored by Git.
Commit the `.tf` files, both `.tfvars` files, scripts, and `.terraform.lock.hcl`.

Only run these cleanup commands when you want to remove the dashboard:

```powershell
$env:ARM_SUBSCRIPTION_ID = az account show --query id --output tsv
terraform workspace select prod
terraform destroy '-var-file=environments/prod.tfvars'
terraform workspace select dev
terraform destroy '-var-file=environments/dev.tfvars'
```

See Microsoft's [Python App Service configuration](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)
and [Streamlit deployment guidance](https://azureossd.github.io/2024/04/18/Deploying-a-Python-Streamlit-app-to-App-Service-Linux/)
for runtime and ZIP-build details.

## Push changes

Git tracks files inside folders, so a folder rename is included when you stage
the moved files. From the `BDACC_app` folder:

```powershell
git add -A
git commit -m "Update F1 dashboard and Azure deployment"
git push
```
