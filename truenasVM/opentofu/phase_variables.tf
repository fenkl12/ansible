variable "provisioning_phase" {
  type        = string
  description = "Provisioning seed phase: install or bootstrap."
  default     = "install"

  validation {
    condition     = contains(["install", "bootstrap"], var.provisioning_phase)
    error_message = "provisioning_phase must be install or bootstrap."
  }
}

