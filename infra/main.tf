terraform {
  required_version = ">= 1.9"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}

# Authentication: set CLOUDFLARE_API_TOKEN in environment
# (different from the R2 S3 access key — see SETUP.md)
provider "cloudflare" {}

resource "cloudflare_r2_bucket" "lake" {
  account_id = var.cloudflare_account_id
  name       = "p2p-lake"
  location   = "WEUR"
}
