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

variable "backup_parent_dataset" {
  type        = string
  description = "Parent dataset for shared TrueNAS VM backups."
  default     = "tank/backups/truenasVM"
}

variable "backup_networks" {
  type        = list(string)
  description = "Networks authorized to mount the backup NFS export."
  default     = ["10.0.0.0/16"]
}
