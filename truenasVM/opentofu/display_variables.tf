variable "display_password" {
  type        = string
  description = "Password for the TrueNAS SPICE console."
  sensitive   = true
}

variable "login_password_hash" {
  type        = string
  description = "SHA-512 crypt hash for the guest login password."
  sensitive   = true
}

