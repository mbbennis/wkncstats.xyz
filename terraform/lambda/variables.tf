variable "data_bucket_name" {
  type    = string
  default = "wknc-stats-data"
}

variable "website_bucket_name" {
  type    = string
  default = "www.wkncstats.xyz"
}

variable "index_object_key" {
  type    = string
  default = "index.html"
}

variable "data_object_key" {
  type    = string
  default = "data/spins.json"
}

variable "lambda_function_name" {
  type    = string
  default = "wknc-stats-update-lambda"
}

variable "lambda_function_handler" {
  type    = string
  default = "wknc_stats_lambda.lambda_handler"
}

variable "zip_file_path" {
  type = string
}
