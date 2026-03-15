@description('Name of the AI Services account')
param aiServicesAccountName string

@description('Principal ID to assign roles to')
param principalId string

@description('Principal type')
param principalType string = 'ServicePrincipal'

// Cognitive Services User role
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource aiServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesAccountName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServicesAccount.id, principalId, cognitiveServicesUserRoleId)
  scope: aiServicesAccount
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
  }
}
