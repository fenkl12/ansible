output "vm_name" { value = truenas_vm.this.name }
output "vm_id" { value = truenas_vm.this.id }
output "ip_address" { value = var.ip_address }
output "ssh_user" { value = var.ssh_user }
output "zvol_path" { value = local.zvol_path }

