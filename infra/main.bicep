targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (used as a prefix for all resources)')
param environmentName string

@minLength(1)
@description('Azure region for all resources')
param location string

@description('Name of the resource group')
param resourceGroupName string = ''

@description('Name of the storage account')
param storageAccountName string = ''

@description('Name of the Azure AI Search service')
param searchServiceName string = ''

@description('Name of the AI Services / Foundry account')
param aiServicesAccountName string = ''

@description('Name of the Application Insights resource')
param appInsightsName string = ''

@description('Name of the Foundry project')
param projectName string = 'mydemos'

@description('ID of the principal to grant access to (e.g. your user objectId)')
param principalId string = ''

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

// Resource group
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

// Storage account
module storage './modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: !empty(storageAccountName) ? storageAccountName : '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
    containerName: 'wh-kb-docs'
  }
}

// Azure AI Search
module search './modules/search.bicep' = {
  name: 'search'
  scope: rg
  params: {
    name: !empty(searchServiceName) ? searchServiceName : '${abbrs.searchSearchServices}${resourceToken}'
    location: location
    tags: tags
  }
}

// Application Insights + Log Analytics (for agent tracing / observability)
module appInsights './modules/app-insights.bicep' = {
  name: 'app-insights'
  scope: rg
  params: {
    appInsightsName: !empty(appInsightsName) ? appInsightsName : '${abbrs.insightsComponents}${resourceToken}'
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    location: location
    tags: tags
  }
}

// AI Services (Foundry) account + project
module aiServices './modules/ai-services.bicep' = {
  name: 'ai-services'
  scope: rg
  params: {
    accountName: !empty(aiServicesAccountName) ? aiServicesAccountName : '${abbrs.cognitiveServicesAccounts}${resourceToken}'
    location: location
    tags: tags
    projectName: projectName
    searchServiceId: search.outputs.id
  }
}

// Model deployments
module modelDeployments './modules/model-deployments.bicep' = {
  name: 'model-deployments'
  scope: rg
  params: {
    aiServicesAccountName: aiServices.outputs.accountName
  }
}

// Role assignments: Search → Storage (Blob Data Reader)
module searchStorageRole './modules/storage-role.bicep' = {
  name: 'search-storage-blob-reader'
  scope: rg
  params: {
    storageAccountName: storage.outputs.name
    principalId: search.outputs.identityPrincipalId
    principalType: 'ServicePrincipal'
    blobRole: 'reader'
  }
}

// Role assignments: Search → AI Services (Cognitive Services User)
module searchAiRole './modules/ai-services-role.bicep' = {
  name: 'search-ai-user'
  scope: rg
  params: {
    aiServicesAccountName: aiServices.outputs.accountName
    principalId: search.outputs.identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Role assignments: Current user → Storage (Blob Data Contributor)
module userStorageRole './modules/storage-role.bicep' = if (!empty(principalId)) {
  name: 'user-storage-blob-contributor'
  scope: rg
  params: {
    storageAccountName: storage.outputs.name
    principalId: principalId
    principalType: 'User'
    blobRole: 'contributor'
  }
}

// Role assignments: Current user → Storage (Blob Delegator — required for SAS URL generation)
module userStorageDelegator './modules/storage-role.bicep' = if (!empty(principalId)) {
  name: 'user-storage-blob-delegator'
  scope: rg
  params: {
    storageAccountName: storage.outputs.name
    principalId: principalId
    principalType: 'User'
    blobRole: 'delegator'
  }
}

// Role assignments: Current user → AI Services (Cognitive Services User)
module userAiRole './modules/ai-services-role.bicep' = if (!empty(principalId)) {
  name: 'user-ai-user'
  scope: rg
  params: {
    aiServicesAccountName: aiServices.outputs.accountName
    principalId: principalId
    principalType: 'User'
  }
}

// Role assignments: AI Services (self) → AI Services (Cognitive Services User)
// Required for the memory store to call the embedding model on the same account
module aiServicesSelfRole './modules/ai-services-role.bicep' = {
  name: 'ai-services-self-cognitive-user'
  scope: rg
  params: {
    aiServicesAccountName: aiServices.outputs.accountName
    principalId: aiServices.outputs.identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Role assignments: Project managed identity → AI Services (Azure AI User)
// Required for memory store to authenticate and call models (chat + embedding)
module projectAiRole './modules/ai-services-role.bicep' = {
  name: 'project-ai-user'
  scope: rg
  params: {
    aiServicesAccountName: aiServices.outputs.accountName
    principalId: aiServices.outputs.projectIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Outputs consumed by azd and post-provisioning scripts
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.name
output AZURE_STORAGE_CONTAINER_NAME string = storage.outputs.containerName
output AZURE_SEARCH_SERVICE_NAME string = search.outputs.name
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_AI_SERVICES_ACCOUNT_NAME string = aiServices.outputs.accountName
output AZURE_AI_SERVICES_ENDPOINT string = aiServices.outputs.endpoint
output AZURE_AI_PROJECT_NAME string = aiServices.outputs.projectName
output AZURE_APP_INSIGHTS_NAME string = appInsights.outputs.id
output AZURE_APP_INSIGHTS_CONNECTION_STRING string = appInsights.outputs.connectionString
