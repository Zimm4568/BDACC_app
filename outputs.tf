output "resource_group_name" {
  description = "Resource group containing this environment."
  value       = azurerm_resource_group.dashboard.name
}

output "web_app_name" {
  description = "App Service name used by az webapp deploy."
  value       = azurerm_linux_web_app.dashboard.name
}

output "web_app_url" {
  description = "Public HTTPS URL of the F1 dashboard."
  value       = "https://${azurerm_linux_web_app.dashboard.default_hostname}"
}

output "environment" {
  value = var.environment
}

output "subscription_id" {
  description = "Subscription owning the deployed web app."
  value       = split("/", azurerm_linux_web_app.dashboard.id)[2]
}
