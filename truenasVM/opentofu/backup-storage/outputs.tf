output "backup_dataset" {
  value = truenas_dataset.data_only.name
}

output "backup_export_path" {
  value = truenas_nfs_share.data_only.path
}

output "snapshot_task_id" {
  value = truenas_periodic_snapshot_task.data_only_daily.id
}
