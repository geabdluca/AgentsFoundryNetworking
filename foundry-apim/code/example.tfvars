# Example tfvars for Foundry + APIM deployment
# Copy this file to terraform.tfvars and fill in your values.
# Note: subscription_id, location, apim_publisher_name, and apim_publisher_email
# are automatically populated by the launcher from your az account show output.

subscription_id      = ""     # auto-populated by launcher
location             = ""     # auto-populated by launcher (e.g. "eastus")
apim_publisher_name  = ""     # auto-populated by launcher from az account show
apim_publisher_email = ""     # auto-populated by launcher from az account show

resource_group_name  = "rg-aifoundry-apim"
environment          = "lab"
project_name         = "apim-agent-project"
apim_sku             = "Developer"
