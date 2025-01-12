locals {
  //  zip_file_path = "${path.module}/../../dist/lambda.zip"
}

data "aws_s3_bucket" "data_bucket" {
  bucket = var.data_bucket_name
}

data "aws_s3_bucket" "website_bucket" {
  bucket = var.website_bucket_name
}

resource "aws_iam_policy" "lambda_policy" {
  name = "wknc-stats-lambda-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          "${data.aws_s3_bucket.data_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = [
          "${data.aws_s3_bucket.website_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = ["arn:aws:logs:*:*:*"]
      }
    ]
  })
}

resource "aws_iam_role" "lambda_role" {
  name = "wknc-stats-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Effect = "Allow"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_policy_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

resource "aws_cloudwatch_log_group" "log_group" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = 7
}

resource "aws_lambda_function" "update_lambda" {
  function_name = var.lambda_function_name
  filename      = var.zip_file_path
  handler       = var.lambda_function_handler
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.13"
  timeout       = 900

  depends_on = [aws_cloudwatch_log_group.log_group]

  source_code_hash = filebase64sha256(var.zip_file_path)

  environment {
    variables = {
      DATA_BUCKET           = var.data_bucket_name
      DATA_KEY              = var.data_object_key
      WEBSITE_BUCKET        = var.website_bucket_name
      WEBSITE_KEY           = var.index_object_key
      REQUEST_DELAY_SECONDS = 3
      LOG_LEVEL             = "INFO"
    }
  }
}



