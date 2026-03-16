@description('Name of the Log Analytics workspace')
param logAnalyticsName string

@description('Name of the Application Insights resource')
param appInsightsName string

@description('Azure region')
param location string = resourceGroup().location

@description('Resource tags')
param tags object = {}

// ── Log Analytics workspace (required by Application Insights) ────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 90
  }
}

// ── Application Insights ──────────────────────────────────────────
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    RetentionInDays: 90
  }
}

@description('Application Insights resource ID')
output id string = appInsights.id

@description('Application Insights instrumentation key')
output instrumentationKey string = appInsights.properties.InstrumentationKey

@description('Application Insights connection string')
output connectionString string = appInsights.properties.ConnectionString

@description('Log Analytics workspace ID')
output logAnalyticsId string = logAnalytics.id
