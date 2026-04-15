########## AI Foundry (BYO VNet) + API Management ##########
##
## Deploys the full AI Foundry stack into the hub-spoke spoke VNet
## and adds Azure API Management (internal VNet mode) for controlled access.
##
## Prerequisites: hub-spoke-network must be fully deployed first.
## The hub-spoke state file is read via terraform_remote_state (data.tf).

## ============================================
## Resource Group
## ============================================

resource "azurerm_resource_group" "foundry" {
  name     = var.resource_group_name
  location = var.location

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "ai-foundry-apim"
    }
  )
}

## ============================================
## Random suffix for unique naming
## ============================================

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

## ============================================
## Storage Account with Private Endpoint
## ============================================

resource "azurerm_storage_account" "storage_account" {
  name                     = "aifoundry${random_string.suffix.result}stor"
  resource_group_name      = azurerm_resource_group.foundry.name
  location                 = azurerm_resource_group.foundry.location
  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "LRS"  # Use LRS for broader region availability (change to ZRS/GRS for production)

  shared_access_key_enabled       = false
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "ai-foundry-storage"
    }
  )
}

resource "azurerm_private_endpoint" "storage_account" {
  name                = "pe-storage-${random_string.suffix.result}"
  location            = azurerm_resource_group.foundry.location
  resource_group_name = azurerm_resource_group.foundry.name
  subnet_id           = local.subnet_id_private_endpoints

  private_service_connection {
    name                           = "psc-storage"
    private_connection_resource_id = azurerm_storage_account.storage_account.id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }

  private_dns_zone_group {
    name                 = "storage-dns-zone-group"
    private_dns_zone_ids = [local.dns_zone_blob_storage]
  }

  tags = merge(var.tags, { environment = var.environment })
}

## ============================================
## Cosmos DB with Private Endpoint
## ============================================

resource "azurerm_cosmosdb_account" "cosmosdb" {
  name                              = "aifoundry${random_string.suffix.result}cosmos"
  location                          = azurerm_resource_group.foundry.location
  resource_group_name               = azurerm_resource_group.foundry.name
  offer_type                        = "Standard"
  kind                              = "GlobalDocumentDB"
  free_tier_enabled                 = false
  public_network_access_enabled     = false
  is_virtual_network_filter_enabled = true
  local_authentication_disabled     = true
  automatic_failover_enabled        = false
  multiple_write_locations_enabled  = false

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.foundry.location
    failover_priority = 0
    zone_redundant    = false
  }

  tags = merge(var.tags, { environment = var.environment })
}

resource "azurerm_private_endpoint" "cosmosdb" {
  name                = "pe-cosmos-${random_string.suffix.result}"
  location            = azurerm_resource_group.foundry.location
  resource_group_name = azurerm_resource_group.foundry.name
  subnet_id           = local.subnet_id_private_endpoints

  private_service_connection {
    name                           = "psc-cosmos"
    private_connection_resource_id = azurerm_cosmosdb_account.cosmosdb.id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  private_dns_zone_group {
    name                 = "cosmos-dns-zone-group"
    private_dns_zone_ids = [local.dns_zone_cosmos]
  }

  tags = merge(var.tags, { environment = var.environment })
}

## ============================================
## AI Search with Private Endpoint
## ============================================

resource "azapi_resource" "ai_search" {
  type                      = "Microsoft.Search/searchServices@2025-05-01"
  name                      = "aifoundry-${random_string.suffix.result}-search"
  location                  = azurerm_resource_group.foundry.location
  parent_id                 = azurerm_resource_group.foundry.id
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    sku = {
      name = "standard"
    }
    properties = {
      replicaCount     = 1
      partitionCount   = 1
      hostingMode      = "Default"
      publicNetworkAccess = "Disabled"
      disableLocalAuth = false
      authOptions = {
        aadOrApiKey = {
          aadAuthFailureMode = "http401WithBearerChallenge"
        }
      }
      semanticSearch = "free"
      networkRuleSet = {
        bypass = "None"
      }
    }
  }

  response_export_values = ["*"]

  tags = merge(var.tags, { environment = var.environment })
}

resource "azurerm_private_endpoint" "ai_search" {
  name                = "pe-search-${random_string.suffix.result}"
  location            = azurerm_resource_group.foundry.location
  resource_group_name = azurerm_resource_group.foundry.name
  subnet_id           = local.subnet_id_private_endpoints

  private_service_connection {
    name                           = "psc-search"
    private_connection_resource_id = azapi_resource.ai_search.id
    is_manual_connection           = false
    subresource_names              = ["searchService"]
  }

  private_dns_zone_group {
    name                 = "search-dns-zone-group"
    private_dns_zone_ids = [local.dns_zone_search]
  }

  tags = merge(var.tags, { environment = var.environment })
}

## ============================================
## AI Foundry Account with Private Endpoint
## ============================================

resource "azapi_resource" "ai_foundry" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name                      = var.ai_foundry_name != "" ? var.ai_foundry_name : "aifoundry${random_string.suffix.result}"
  location                  = azurerm_resource_group.foundry.location
  parent_id                 = azurerm_resource_group.foundry.id
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = var.ai_foundry_name != "" ? var.ai_foundry_name : "aifoundry${random_string.suffix.result}"
      publicNetworkAccess    = "Disabled"
      disableLocalAuth       = false
      networkAcls = {
        defaultAction = "Allow"
      }
      networkInjections = [
        {
          scenario                   = "agent"
          subnetArmId                = local.subnet_id_agents
          useMicrosoftManagedNetwork = false
        }
      ]
    }
  }

  response_export_values = ["*"]

  tags = merge(var.tags, { environment = var.environment })
}

resource "azurerm_private_endpoint" "ai_foundry_account" {
  name                = "pe-aifoundry-account-${random_string.suffix.result}"
  location            = azurerm_resource_group.foundry.location
  resource_group_name = azurerm_resource_group.foundry.name
  subnet_id           = local.subnet_id_private_endpoints

  private_service_connection {
    name                           = "psc-aifoundry-account"
    private_connection_resource_id = azapi_resource.ai_foundry.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name                 = "aifoundry-account-dns-zone-group"
    private_dns_zone_ids = [local.dns_zone_cognitive, local.dns_zone_openai, local.dns_zone_ai_services]
  }

  tags = merge(var.tags, { environment = var.environment })
}

## ============================================
## RBAC Role Assignments
## ============================================

## Grant AI Foundry account MI Contributor on the resource group
resource "azurerm_role_assignment" "foundry_contributor" {
  scope                = azurerm_resource_group.foundry.id
  role_definition_name = "Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## Grant AI Foundry account MI Storage Blob Data Contributor
resource "azurerm_role_assignment" "storage_blob_data_contributor_ai_foundry" {
  scope                = azurerm_storage_account.storage_account.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## Grant AI Foundry account MI Cosmos DB Operator
resource "azurerm_role_assignment" "cosmosdb_operator_ai_foundry" {
  scope                = azurerm_cosmosdb_account.cosmosdb.id
  role_definition_name = "Cosmos DB Operator"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## Grant AI Foundry account MI Search Index Data Contributor
resource "azurerm_role_assignment" "search_index_data_contributor_ai_foundry" {
  scope                = azapi_resource.ai_search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## Grant AI Foundry account MI Search Service Contributor
resource "azurerm_role_assignment" "search_service_contributor_ai_foundry" {
  scope                = azapi_resource.ai_search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## ============================================
## AI Foundry Project
## ============================================

resource "time_sleep" "wait_foundry_ready" {
  depends_on = [
    azurerm_role_assignment.foundry_contributor,
    azurerm_role_assignment.storage_blob_data_contributor_ai_foundry,
    azurerm_role_assignment.cosmosdb_operator_ai_foundry,
    azurerm_role_assignment.search_index_data_contributor_ai_foundry,
    azurerm_role_assignment.search_service_contributor_ai_foundry,
    azurerm_private_endpoint.ai_foundry_account,
    azurerm_private_endpoint.storage_account,
    azurerm_private_endpoint.ai_search,
    azurerm_private_endpoint.cosmosdb,
    azurerm_api_management.apim,
  ]
  create_duration = "120s"
}

resource "azapi_resource" "ai_foundry_project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name                      = var.project_name
  location                  = azurerm_resource_group.foundry.location
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {}
  }

  response_export_values = ["*"]

  depends_on = [time_sleep.wait_foundry_ready]
}

## ============================================
## AI Foundry Project – Additional RBAC
## (assigned after project is created)
## ============================================

resource "time_sleep" "wait_project_identities" {
  depends_on      = [azapi_resource.ai_foundry_project]
  create_duration = "30s"
}

## Grant project MI Cosmos DB Operator (control plane — allows sqlDatabases/read)
resource "azurerm_role_assignment" "cosmosdb_operator_ai_foundry_project" {
  depends_on = [time_sleep.wait_project_identities]

  name                 = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}${azurerm_resource_group.foundry.name}cosmosdboperator")
  scope                = azurerm_cosmosdb_account.cosmosdb.id
  role_definition_name = "Cosmos DB Operator"
  principal_id         = azapi_resource.ai_foundry_project.output.identity.principalId
}

## Grant project MI Storage Blob Data Contributor on storage account
resource "azurerm_role_assignment" "storage_blob_data_contributor_ai_foundry_project" {
  depends_on = [time_sleep.wait_project_identities]

  name                 = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}${azurerm_storage_account.storage_account.name}storageblobdatacontributor")
  scope                = azurerm_storage_account.storage_account.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.ai_foundry_project.output.identity.principalId
}

## Grant project MI Search Index Data Contributor on AI Search
resource "azurerm_role_assignment" "search_index_data_contributor_ai_foundry_project" {
  depends_on = [time_sleep.wait_project_identities]

  name                 = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}${azapi_resource.ai_search.name}searchindexdatacontributor")
  scope                = azapi_resource.ai_search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.ai_foundry_project.output.identity.principalId
}

## Grant project MI Search Service Contributor on AI Search
resource "azurerm_role_assignment" "search_service_contributor_ai_foundry_project" {
  depends_on = [time_sleep.wait_project_identities]

  name                 = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}${azapi_resource.ai_search.name}searchservicecontributor")
  scope                = azapi_resource.ai_search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.ai_foundry_project.output.identity.principalId
}

## Grant project MI CosmosDB Built-in Data Contributor at account level (data plane)
resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_sql_data_contributor_ai_foundry_project" {
  depends_on = [time_sleep.wait_project_identities]

  name                = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}${azurerm_cosmosdb_account.cosmosdb.name}cosmosdbsqldatacontributor")
  resource_group_name = azurerm_resource_group.foundry.name
  account_name        = azurerm_cosmosdb_account.cosmosdb.name
  scope               = azurerm_cosmosdb_account.cosmosdb.id
  role_definition_id  = "${azurerm_cosmosdb_account.cosmosdb.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.ai_foundry_project.output.identity.principalId
}

## Wait for all RBAC to propagate before creating connections and capability host
resource "time_sleep" "wait_rbac" {
  depends_on = [
    azurerm_role_assignment.cosmosdb_operator_ai_foundry_project,
    azurerm_role_assignment.storage_blob_data_contributor_ai_foundry_project,
    azurerm_role_assignment.search_index_data_contributor_ai_foundry_project,
    azurerm_role_assignment.search_service_contributor_ai_foundry_project,
    azurerm_cosmosdb_sql_role_assignment.cosmosdb_sql_data_contributor_ai_foundry_project,
  ]
  create_duration = "120s"
}

## ============================================
## AI Foundry Project Connections
## ============================================

resource "azapi_resource" "cosmos_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name                      = azurerm_cosmosdb_account.cosmosdb.name
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "CosmosDb"
      target        = azurerm_cosmosdb_account.cosmosdb.endpoint
      authType      = "AAD"
      isSharedToAll = true
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_cosmosdb_account.cosmosdb.id
        location   = azurerm_resource_group.foundry.location
      }
    }
  }

  depends_on = [time_sleep.wait_rbac]
}

resource "azapi_resource" "storage_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name                      = azurerm_storage_account.storage_account.name
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "AzureStorageAccount"
      target        = azurerm_storage_account.storage_account.primary_blob_endpoint
      authType      = "AAD"
      isSharedToAll = true
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_storage_account.storage_account.id
        location   = azurerm_resource_group.foundry.location
      }
    }
  }

  depends_on = [time_sleep.wait_rbac]
}

resource "azapi_resource" "search_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name                      = azapi_resource.ai_search.name
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "CognitiveSearch"
      target        = "https://${azapi_resource.ai_search.name}.search.windows.net"
      authType      = "AAD"
      isSharedToAll = true
      metadata = {
        ApiType    = "Azure"
        ApiVersion = "2025-05-01-preview"
        ResourceId = azapi_resource.ai_search.id
        location   = azurerm_resource_group.foundry.location
      }
    }
  }

  depends_on = [time_sleep.wait_rbac]
}

## ============================================
## AI Foundry Project Capability Host
## ============================================

resource "azapi_resource" "ai_foundry_project_capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "default"
  parent_id                 = azapi_resource.ai_foundry_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind = "Agents"
      vectorStoreConnections = [
        azapi_resource.search_connection.name
      ]
      storageConnections = [
        azapi_resource.storage_connection.name
      ]
      threadStorageConnections = [
        azapi_resource.cosmos_connection.name
      ]
    }
  }

  depends_on = [
    time_sleep.wait_rbac,
    azapi_resource.cosmos_connection,
    azapi_resource.storage_connection,
    azapi_resource.search_connection,
  ]
}

## ============================================
## Additional Storage RBAC (post capability host)
## ============================================

resource "azurerm_role_assignment" "storage_blob_data_owner_ai_foundry_project" {
  scope                = azurerm_storage_account.storage_account.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azapi_resource.ai_foundry_project.output.identity.principalId

  depends_on = [time_sleep.wait_project_identities]
}

## ============================================
## API Management (Internal VNet Mode)
## ============================================
## NOTE: The APIM NSG and subnet association are managed in the
## hub-spoke-network module (network.tf) alongside the snet-apim subnet.

resource "azurerm_api_management" "apim" {
  name                = "apim-foundry-${random_string.suffix.result}"
  location            = azurerm_resource_group.foundry.location
  resource_group_name = azurerm_resource_group.foundry.name
  publisher_name      = var.apim_publisher_name
  publisher_email     = var.apim_publisher_email
  sku_name            = "${var.apim_sku}_1"

  virtual_network_type = "Internal"

  virtual_network_configuration {
    subnet_id = local.subnet_id_apim
  }

  tags = merge(var.tags, { environment = var.environment })
}

## APIM API surfacing the AI Foundry endpoint
resource "azurerm_api_management_api" "ai_foundry_api" {
  name                = "ai-foundry-api"
  resource_group_name = azurerm_resource_group.foundry.name
  api_management_name = azurerm_api_management.apim.name
  revision            = "1"
  display_name        = "AI Foundry API"
  path                = "ai"
  protocols           = ["https"]
  service_url         = azapi_resource.ai_foundry.output.properties.endpoint

  depends_on = [azapi_resource.ai_foundry]
}

## ============================================
## AI Gateway: Token Rate Limiting Policy
## ============================================
## Limits total LLM tokens (prompt + completion) per subscription key
## per rolling time window. Returns HTTP 429 when limit is exceeded.
## Requires APIM stv2 compute (default for all new instances since Sep 2023).
resource "azurerm_api_management_api_policy" "token_limit" {
  api_name            = azurerm_api_management_api.ai_foundry_api.name
  api_management_name = azurerm_api_management.apim.name
  resource_group_name = azurerm_resource_group.foundry.name

  xml_content = templatefile("${path.module}/policies/token-rate-limit.xml", {
    tokens_per_minute = var.apim_token_limit_per_minute
    renewal_period    = var.apim_token_limit_renewal_period
  })

  depends_on = [azurerm_api_management_api.ai_foundry_api]
}
