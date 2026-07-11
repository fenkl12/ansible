terraform {
  required_version = ">= 1.7.0"

  required_providers {
    truenas = {
      source  = "registry.terraform.io/baladithyab/truenas"
      version = "= 0.2.25"
    }
  }
}

provider "truenas" {
  base_url = var.truenas_url
  api_key  = var.truenas_api_key
}

