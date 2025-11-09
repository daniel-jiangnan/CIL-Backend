# Deployment Guide - Environment Variables

## Overview

This guide explains how to set up environment variables for deploying the CIL Backend API to cloud platforms.

## Service Accounts Configuration

### For Local Development

Use local files:

- `service_accounts.txt` - List of service account file paths
- `calendars.json` - Calendar configuration
- `*.json` - Actual service account credential files

```bash
# Example service_accounts.txt
center-for-independent-living-95cb120a7f0e.json
other-org-credentials.json
```

### For Cloud Deployment

Use the `SERVICE_ACCOUNTS_JSON` environment variable to provide all service account credentials as a JSON string.

## Setting up SERVICE_ACCOUNTS_JSON

### Step 1: Prepare Your Service Account Files

Gather all Google Cloud service account JSON files you need. You can download these from Google Cloud Console.

Example service account file content:

```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-private-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service@your-project.iam.gserviceaccount.com",
  "client_id": "1234567890",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service%40your-project.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
```

### Step 2: Create the SERVICE_ACCOUNTS_JSON Environment Variable

Format:

```json
[
  {
    "path": "filename1.json",
    "content": { <entire service account JSON object> }
  },
  {
    "path": "filename2.json",
    "content": { <entire service account JSON object> }
  }
]
```

### Step 3: Platform-Specific Instructions

#### Render.com

1. Go to your service dashboard
2. Click "Environment" tab
3. Add a new environment variable:
   - **Key**: `SERVICE_ACCOUNTS_JSON`
   - **Value**: Paste the JSON array from Step 2

**Important**: The value should be a single-line JSON string (no line breaks):

```
[{"path":"org1.json","content":{...}},{"path":"org2.json","content":{...}}]
```

#### Railway.app

1. Go to your project
2. Click "Variables" tab
3. Add new variable:
   - **Key**: `SERVICE_ACCOUNTS_JSON`
   - **Value**: Paste the JSON array

#### Azure App Service

```bash
az webapp config appsettings set \
  --resource-group myResourceGroup \
  --name myAppName \
  --settings SERVICE_ACCOUNTS_JSON='[{"path":"org1.json","content":{...}}]'
```

#### AWS Lambda / EC2

Set environment variable in your deployment configuration:

**SAM template.yaml**:

```yaml
Resources:
  MyFunction:
    Type: AWS::Serverless::Function
    Properties:
      Environment:
        Variables:
          SERVICE_ACCOUNTS_JSON: '[{"path":"org1.json","content":{...}}]'
```

**Docker**:

```dockerfile
ENV SERVICE_ACCOUNTS_JSON='[{"path":"org1.json","content":{...}}]'
```

#### Google Cloud Run

```bash
gcloud run deploy my-service \
  --update-env-vars SERVICE_ACCOUNTS_JSON='[{"path":"org1.json","content":{...}}]'
```

#### Heroku

```bash
heroku config:set SERVICE_ACCOUNTS_JSON='[{"path":"org1.json","content":{...}}]' -a my-app-name
```

## Complete Example

Here's a complete example with 2 service accounts:

```json
[
  {
    "path": "cil-main.json",
    "content": {
      "type": "service_account",
      "project_id": "center-for-independent-living",
      "private_key_id": "YOUR_PRIVATE_KEY_ID",
      "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_CONTENT\n-----END PRIVATE KEY-----\n",
      "client_email": "your-service@center-for-independent-living.iam.gserviceaccount.com",
      "client_id": "YOUR_CLIENT_ID",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service%40center-for-independent-living.iam.gserviceaccount.com",
      "universe_domain": "googleapis.com"
    }
  },
  {
    "path": "partner-org.json",
    "content": {
      "type": "service_account",
      "project_id": "partner-organization",
      "private_key_id": "YOUR_PRIVATE_KEY_ID",
      "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_CONTENT\n-----END PRIVATE KEY-----\n",
      "client_email": "service@partner-organization.iam.gserviceaccount.com",
      "client_id": "YOUR_CLIENT_ID",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/service%40partner-organization.iam.gserviceaccount.com",
      "universe_domain": "googleapis.com"
    }
  }
]
```

**Note**: Replace all `YOUR_*` placeholders with actual values from your Google Cloud service account credentials.

## API Usage After Deployment

Once deployed with the environment variable set, the API will automatically:

1. Read the `SERVICE_ACCOUNTS_JSON` environment variable at startup
2. Extract all service account credentials
3. Create temporary credential files during runtime
4. Use these credentials for Google Calendar API authentication

### Request Examples

**Search by Date**:

```bash
curl -X POST https://your-api.com/api/appointments/by-date \
  -H "Content-Type: application/json" \
  -d '{"target_date": "2025-12-09"}'
```

**Search by Customer**:

```bash
curl -X POST https://your-api.com/api/appointments/by-customer \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "appointment_date": "2025-12-09",
    "service": "housing"
  }'
```

## Security Notes

⚠️ **Important**:

- Private keys in environment variables are temporary and never stored in code or Git
- The service account files are created at runtime in the application's temporary directory
- After the application shuts down, these files are automatically cleaned up
- Never commit `center-for-independent-living-*.json` or any service account files to Git

## Troubleshooting

### Error: "No service accounts found"

**Cause**: `SERVICE_ACCOUNTS_JSON` environment variable not set or invalid format

**Solution**:

1. Verify the environment variable is set: `echo $SERVICE_ACCOUNTS_JSON`
2. Check the JSON format is valid
3. Ensure all fields are present in each account object

### Error: "Failed to parse SERVICE_ACCOUNTS_JSON"

**Cause**: Invalid JSON format

**Solution**:

1. Validate your JSON at https://jsonlint.com/
2. Ensure special characters in the private key are properly escaped
3. Remove all line breaks - keep it as a single-line JSON string

### Error: "Authentication failed"

**Cause**: Invalid service account credentials

**Solution**:

1. Verify the service account JSON file is correct
2. Check that the service account has Calendar API permissions
3. Ensure the private key is complete and not truncated

## Local Development Testing

To test the environment variable setup locally:

```bash
#!/bin/bash
export SERVICE_ACCOUNTS_JSON='[{"path":"cil-main.json","content":{...}}]'
./venv/bin/python main.py
```

Then test the API:

```bash
curl -X POST http://localhost:8000/api/appointments/by-date \
  -H "Content-Type: application/json" \
  -d '{"target_date": "2025-12-09"}'
```

## Additional Configuration

### DEEPSEEK_API_KEY

For AI service classification features:

```bash
export DEEPSEEK_API_KEY='sk-xxxxxxxx...'
```

### Service Account File Paths (Alternative)

If you prefer using file paths instead of embedding credentials:

```bash
export SERVICE_ACCOUNT_FILE="service_accounts.txt"
```

And upload the `service_accounts.txt` file with your deployment.

---

For more information, see:

- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md)
- [TYPESCRIPT_INTEGRATION_GUIDE.md](./TYPESCRIPT_INTEGRATION_GUIDE.md)
