#!/bin/bash
# AWS Lambda deployment script for Epicor-HubSpot Integration

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
FUNCTION_NAME="${FUNCTION_NAME:-epicor-hubspot-sync-production}"
REGION="${AWS_REGION:-us-east-1}"
BUILD_DIR="build"
ZIP_FILE="aws/lambda_function.zip"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Epicor-HubSpot Integration Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Step 1: Clean previous build
echo -e "${YELLOW}[1/6]${NC} Cleaning previous build..."
rm -rf "${BUILD_DIR}"
rm -f "${ZIP_FILE}"
echo -e "${GREEN}${NC} Build directory cleaned"
echo ""

# Step 2: Create build directory
echo -e "${YELLOW}[2/6]${NC} Creating build directory..."
mkdir -p "${BUILD_DIR}"
echo -e "${GREEN}${NC} Build directory created"
echo ""

# Step 3: Copy source code
echo -e "${YELLOW}[3/6]${NC} Copying source code..."
cp -r src/ "${BUILD_DIR}/"
echo -e "${GREEN}${NC} Source code copied"
echo ""

# Step 4: Install dependencies
echo -e "${YELLOW}[4/6]${NC} Installing Python dependencies..."
pip install -r requirements.txt -t "${BUILD_DIR}/" --quiet
echo -e "${GREEN}${NC} Dependencies installed"
echo ""

# Step 5: Create deployment package
echo -e "${YELLOW}[5/6]${NC} Creating deployment package..."
cd "${BUILD_DIR}"
zip -r ../${ZIP_FILE} . -q
cd ..
ZIP_SIZE=$(du -h "${ZIP_FILE}" | cut -f1)
echo -e "${GREEN}${NC} Deployment package created (${ZIP_SIZE})"
echo ""

# Step 6: Deploy to AWS Lambda
echo -e "${YELLOW}[6/6]${NC} Deploying to AWS Lambda..."
echo "Function: ${FUNCTION_NAME}"
echo "Region: ${REGION}"

aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${ZIP_FILE}" \
    --region "${REGION}" \
    --output table

echo ""
echo -e "${GREEN}${NC} Deployment completed successfully!"
echo ""

# Optional: Update environment variables
read -p "Do you want to update environment variables? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    echo -e "${YELLOW}Updating environment variables...${NC}"
    aws lambda update-function-configuration \
        --function-name "${FUNCTION_NAME}" \
        --environment "Variables={LOG_LEVEL=INFO,ENVIRONMENT=production}" \
        --region "${REGION}" \
        --output table
    echo -e "${GREEN}${NC} Environment variables updated"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Test the function: aws lambda invoke --function-name ${FUNCTION_NAME} response.json"
echo "  2. View logs: aws logs tail /aws/lambda/${FUNCTION_NAME} --follow"
echo ""
