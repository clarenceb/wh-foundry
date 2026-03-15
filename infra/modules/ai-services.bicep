@description('Name of the AI Services account')
param accountName string

@description('Azure region')
param location string = resourceGroup().location

@description('Resource tags')
param tags object = {}

@description('Name of the Foundry project')
param projectName string = 'mydemos'

@description('Resource ID of the Azure AI Search service to connect')
param searchServiceId string = ''

resource aiServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiServicesAccount
  name: projectName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    #disable-next-line BCP037
    aiServicesConnections: !empty(searchServiceId) ? {
      search: {
        kind: 'AISearch'
        resourceId: searchServiceId
      }
    } : {}
  }
}

output accountId string = aiServicesAccount.id
output accountName string = aiServicesAccount.name
output endpoint string = 'https://${aiServicesAccount.name}.openai.azure.com'
output projectName string = project.name
output identityPrincipalId string = aiServicesAccount.identity.principalId
output projectIdentityPrincipalId string = project.identity.principalId
