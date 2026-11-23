#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Run Deployment Script for Stock Management Backend
# ==============================================================================
set -e

SERVICE_NAME="stock-management-backend"
REGION="${GCP_REGION:-us-central1}"
MEMORY="1Gi"
CPU="1"

echo "=========================================================="
echo " Deploying Stock Management Backend to Google Cloud Run"
echo " Service : ${SERVICE_NAME}"
echo " Region  : ${REGION}"
echo " Memory  : ${MEMORY}"
echo " CPU     : ${CPU}"
echo "=========================================================="

# Deploy directly from source via Google Cloud Build & Cloud Run
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --memory "${MEMORY}" \
  --cpu "${CPU}" \
  --timeout 120s \
  --set-env-vars FLASK_ENV=production

echo ""
echo "Deployment successful! Service URL:"
gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format="value(status.url)"
echo ""
echo "Next step: Update your Vercel frontend VITE_API_BASE_URL to point to this URL."
