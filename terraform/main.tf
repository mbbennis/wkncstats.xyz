terraform {
  required_version = "~> 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = {
      IsPublicResource = true
    }
  }
}

locals {
  domain_name             = "wkncstats.xyz"
  index_object_key        = "index.html"
  error_object_key        = "404.html"
  cloudflare_zone_id      = "cd0eafcfe99caa4e1e4ec506cb47ec10"
  data_bucket_name        = "wknc-stats-data"
  data_object_key         = "data/spins.csv"
  lambda_function_name    = "wknc-stats-update-lambda"
  lambda_function_handler = "wknc_stats_lambda.lambda_handler"
  static_folder_path      = abspath("${path.module}/../src/static")
  zip_file_path           = abspath("${path.module}/../dist/lambda.zip")
}

module "website" {
  source             = "mbbennis/s3-cloudflare-website/aws"
  version            = "~> 1.0"
  domain_name        = local.domain_name
  bucket_name        = local.domain_name
  cloudflare_zone_id = local.cloudflare_zone_id
  index_object_key   = local.index_object_key
  error_object_key   = local.error_object_key
}

module "s3" {
  source              = "./s3"
  website_bucket_name = module.website.bucket_name
  data_bucket_name    = local.data_bucket_name
  error_object_key    = local.error_object_key
  static_folder_path  = local.static_folder_path
}

module "lambda" {
  source                  = "./lambda"
  website_bucket_name     = module.website.bucket_name
  data_bucket_name        = local.data_bucket_name
  index_object_key        = local.index_object_key
  data_object_key         = local.data_object_key
  lambda_function_name    = local.lambda_function_name
  lambda_function_handler = local.lambda_function_handler
  zip_file_path           = local.zip_file_path
}

module "scheduler" {
  source               = "./scheduler"
  lambda_function_name = local.lambda_function_name
}
