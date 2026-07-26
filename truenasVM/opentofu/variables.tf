variable "truenas_url" {
  type        = string
  description = "TrueNAS base URL."
  default     = "http://10.0.203.171"
}

variable "truenas_api_key" {
  type        = string
  description = "TrueNAS API key; set with TF_VAR_truenas_api_key."
  sensitive   = true
}

variable "vm_name" { type = string }
variable "ip_address" { type = string }
variable "prefix_length" {
  type    = number
  default = 16
}
variable "gateway" {
  type    = string
  default = "10.0.0.1"
}
variable "dns_servers" {
  type    = list(string)
  default = ["64.71.255.204", "64.71.255.198"]
}
variable "ssh_user" {
  type    = string
  default = "fenkil"
}
variable "ssh_public_key" {
  type      = string
  sensitive = true
}
variable "vcpus" {
  type        = number
  description = "Total guest CPU cores, configured as one socket."
  default     = 2

  validation {
    condition     = var.vcpus >= 1 && var.vcpus <= 16 && floor(var.vcpus) == var.vcpus
    error_message = "vcpus must be a whole number between 1 and 16."
  }
}
variable "memory_mb" {
  type    = number
  default = 4096
}
variable "disk_size_gb" {
  type    = number
  default = 40
}
variable "storage_pool" {
  type    = string
  default = "WD1TB"
}
variable "nic_attach" {
  type    = string
  default = "enp3s0"
}
variable "ubuntu_iso_path" {
  type        = string
  description = "Existing Ubuntu autoinstall-capable ISO path on TrueNAS."
  default     = "/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso"
}
