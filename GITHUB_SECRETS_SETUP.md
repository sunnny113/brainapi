# GitHub Secrets Setup

Configure these repository secrets for automation workflows.

## Required for daily email lifecycle workflow

- BRAINAPI_BASE_URL
- BRAINAPI_ADMIN_API_KEY

## Optional

- BRAINAPI_EMAIL_SEND_LIMIT (default workflow fallback is 100)

## How to set in GitHub UI

1. Open your repository on GitHub.
2. Go to Settings → Secrets and variables → Actions.
3. Click New repository secret.
4. Add each secret exactly as listed above.

## Verify workflow

1. Open Actions tab.
2. Run `Email Lifecycle Cron` manually (`workflow_dispatch`).
3. Check step logs for successful HTTP calls.

## Recommended additional secrets for future CI/CD hardening

- PROD_PUBLIC_BASE_URL
- PROD_RAZORPAY_KEY_ID
- PROD_RAZORPAY_KEY_SECRET
- PROD_RAZORPAY_WEBHOOK_SECRET
- PROD_SMTP_HOST
- PROD_SMTP_USERNAME
- PROD_SMTP_PASSWORD
- PROD_EMAIL_FROM_ADDRESS
