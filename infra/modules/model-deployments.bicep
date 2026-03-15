@description('Name of the AI Services account')
param aiServicesAccountName string

resource aiServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesAccountName
}

// text-embedding-3-small (used by AI Search skillset for embeddings)
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServicesAccount
  name: 'text-embedding-3-small'
  sku: {
    name: 'Standard'
    capacity: 120
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
  }
}

// gpt-4.1
resource gpt41Deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServicesAccount
  name: 'gpt-4.1'
  sku: {
    name: 'GlobalStandard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1'
      version: '2025-04-14'
    }
  }
  dependsOn: [embeddingDeployment]
}

// gpt-5.1
resource gpt51Deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServicesAccount
  name: 'gpt-5.1'
  sku: {
    name: 'GlobalStandard'
    capacity: 120
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.1'
      version: '2025-11-13'
    }
  }
  dependsOn: [gpt41Deployment]
}

// gpt-5.2
resource gpt52Deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServicesAccount
  name: 'gpt-5.2'
  sku: {
    name: 'GlobalStandard'
    capacity: 150
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.2'
      version: '2025-12-11'
    }
  }
  dependsOn: [gpt51Deployment]
}
