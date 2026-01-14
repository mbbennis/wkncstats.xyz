terraform {
  required_version = "~> 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

data "aws_lambda_function" "update_lambda" {
  function_name = var.lambda_function_name
}

resource "aws_iam_policy" "scheduler_policy" {
  name = "wknc-stats-scheduler-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        "Action" : [
          "lambda:InvokeFunction"
        ],
        "Effect" : "Allow",
        "Resource" : data.aws_lambda_function.update_lambda.arn
      }
    ]
  })
}

resource "aws_iam_role" "scheduler_role" {
  name = "wknc-stats-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Service" : "scheduler.amazonaws.com"
        },
        "Action" : "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_policy_attach" {
  role       = aws_iam_role.scheduler_role.name
  policy_arn = aws_iam_policy.scheduler_policy.arn
}

resource "aws_scheduler_schedule" "update_scheduler" {
  name       = "wknc-stats-update-schedule"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(6 hours)"

  target {
    arn      = data.aws_lambda_function.update_lambda.arn
    role_arn = aws_iam_role.scheduler_role.arn
  }
}
