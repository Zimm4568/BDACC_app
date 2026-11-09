locals {
  tags = {
    application = "f1-dashboard"
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "dashboard" {
  name     = "rg-${var.project_name}-${var.environment}"
  location = var.location
  tags     = local.tags

  lifecycle {
    precondition {
      condition     = terraform.workspace == var.environment
      error_message = "Workspace and environment do not match. Select the matching dev/prod workspace and tfvars file."
    }
  }
}

resource "azurerm_service_plan" "dashboard" {
  name                = "asp-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.dashboard.name
  location            = azurerm_resource_group.dashboard.location
  os_type             = "Linux"
  sku_name            = var.sku_name
  tags                = local.tags
}

resource "azurerm_linux_web_app" "dashboard" {
  name                = "app-${var.project_name}-${random_string.suffix.result}-${var.environment}"
  resource_group_name = azurerm_resource_group.dashboard.name
  location            = azurerm_service_plan.dashboard.location
  service_plan_id     = azurerm_service_plan.dashboard.id
  https_only          = true
  # Streamlit keeps a session on one worker using a WebSocket.
  client_affinity_enabled = true
  tags                    = local.tags

  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  site_config {
    always_on               = var.sku_name != "F1"
    app_command_line        = "python -m streamlit run BDACC_proj_1.py --server.address=0.0.0.0 --server.port=8000 --server.headless=true --server.fileWatcherType=none --browser.gatherUsageStats=false"
    ftps_state              = "Disabled"
    minimum_tls_version     = "1.2"
    scm_minimum_tls_version = "1.2"
    websockets_enabled      = true

    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = {
    ENVIRONMENT                    = var.environment
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD              = "true"
  }
}
