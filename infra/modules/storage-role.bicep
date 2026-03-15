@description('Name of the storage account')
param storageAccountName string

@description('Principal ID to assign roles to')
param principalId string

@description('Principal type')
param principalType string = 'ServicePrincipal'

@description('Role to assign: reader, contributor, or delegator')
@allowed(['reader', 'contributor', 'delegator'])
param blobRole string = 'reader'

var roles = {
  reader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'      // Storage Blob Data Reader
  contributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'   // Storage Blob Data Contributor
  delegator: 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a'     // Storage Blob Delegator
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, roles[blobRole])
  scope: storageAccount
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles[blobRole])
  }
}
