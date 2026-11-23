# ==============================================================================
# Google Cloud Run PowerShell Deployment Script
# ==============================================================================
param(
    [string]$ServiceName = "stock-management-backend",
    [string]$Region = "us-central1"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Deploying Stock Management Backend to Google Cloud Run" -ForegroundColor Cyan
Write-Host " Service : $ServiceName" -ForegroundColor White
Write-Host " Region  : $Region" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan

# Deploy directly from source to Cloud Run
gcloud run deploy $ServiceName `
    --source . `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --memory 1Gi `
    --cpu 1 `
    --timeout 120s `
    --set-env-vars FLASK_ENV=production

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDeployment successful! Fetching Service URL..." -ForegroundColor Green
    $ServiceUrl = gcloud run services describe $ServiceName --region $Region --format="value(status.url)"
    Write-Host "Service URL: $ServiceUrl" -ForegroundColor Yellow
    Write-Host "`nNext Step: Set VITE_API_BASE_URL=$ServiceUrl/api in your Vercel Dashboard Environment Variables." -ForegroundColor Cyan
} else {
    Write-Host "`nDeployment failed. Please check error messages above." -ForegroundColor Red
}
