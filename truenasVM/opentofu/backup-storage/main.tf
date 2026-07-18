locals {
  backup_dataset = "${var.backup_parent_dataset}/dataOnly"
  backup_path    = "/mnt/${local.backup_dataset}"
}

resource "truenas_dataset" "backup_parent" {
  name        = var.backup_parent_dataset
  type        = "FILESYSTEM"
  compression = "LZ4"
  atime       = "OFF"
  comments    = "OpenTofu-managed parent for TrueNAS VM backups"

  lifecycle {
    prevent_destroy = true
  }
}

resource "truenas_dataset" "data_only" {
  name        = local.backup_dataset
  type        = "FILESYSTEM"
  compression = "LZ4"
  atime       = "OFF"
  comments    = "Nightly pcData mirrors for TrueNAS VMs"

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [truenas_dataset.backup_parent]
}

resource "truenas_nfs_share" "data_only" {
  path         = local.backup_path
  comment      = "OpenTofu-managed pcData backup export for TrueNAS VMs"
  networks     = var.backup_networks
  readonly     = false
  enabled      = true
  maproot_user = "root"
  security     = ["SYS"]

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [truenas_dataset.data_only]
}

resource "truenas_periodic_snapshot_task" "data_only_daily" {
  dataset        = truenas_dataset.data_only.name
  recursive      = false
  enabled        = true
  allow_empty    = false
  naming_schema  = "truenas-vm-daily-%Y-%m-%d_%H-%M"
  lifetime_value = 30
  lifetime_unit  = "DAY"
  schedule       = "0 2 * * *"
}
