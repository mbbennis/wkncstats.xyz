# wkncstats.xyz

Contains the resources for [wkncstats.xyz](https://www.wkncstats.xyz).
The static site is served from S3 and periodically updated by a Lambda function.

# Deploying a Static Site to S3

This guide outlines the steps to deploy the static site to an S3 bucket using a Python virtual environment, AWS Lambda, and Terraform.

## Prerequisites
- Python 3.13 installed.
- Terraform installed.
- AWS CLI configured with the necessary permissions.

## Steps

### 1. Set Up Python Virtual Environment
1. Create and activate a Python virtual environment:
   ```bash
   python3.13 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

### 2. Build the AWS Lambda Function
1. Run the provided script to create a Lambda function deployment package:
   ```bash
   python scripts/build_zip.py
   ```

### 3. Deploy the Infrastructure with Terraform
1. Navigate to the `terraform` directory:
   ```bash
   cd terraform
   ```
2. Initialize Terraform:
   ```bash
   terraform init
   ```
3. Apply the Terraform configuration to deploy the resources:
   ```bash
   terraform apply
   ```
   Confirm the action when prompted.

### 4. Initialize the Static Site
1. Run the provided script to invoke the Lambda function and initialize the static site:
   ```bash
   python scripts/invoke_lambda.py
   ```
### 5. Configure Cloudflare
1. [Configure Cloudflare](https://miketabor.com/how-to-host-a-static-website-using-aws-s3-and-Cloudflare/) to serve as the CDN.

## Notes
- Ensure your AWS credentials are set up correctly before running these commands.
- Terraform will create and manage the necessary AWS resources, including the S3 bucket and Lambda function.
- The bucket policy only allows access from Cloudflare.

You're all set! The static site should now be deployed to the specified S3 bucket.
