terraform {
  required_version = "~> 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

locals {
  mime_map = {
    css         = "text/css"
    html        = "text/html"
    ico         = "image/x-icon"
    png         = "image/png"
    svg         = "image/svg+xml"
    webmanifest = "application/manifest+json"
    xml         = "application/xml"
  }

  static_keys = fileset(var.static_folder_path, "**")

  static_objects = {
    for key in local.static_keys : key => {
      content_type = lookup(local.mime_map, reverse(split(".", key))[0], "text/plain")
      source       = "${var.static_folder_path}/${key}"
    }
  }
}


resource "aws_s3_object" "static_objects" {
  for_each = local.static_objects

  bucket       = var.website_bucket_name
  key          = each.key
  content_type = each.value.content_type
  source       = each.value.source
  source_hash  = filemd5(each.value.source)
}

resource "aws_s3_bucket" "data" {
  bucket = var.data_bucket_name
}
