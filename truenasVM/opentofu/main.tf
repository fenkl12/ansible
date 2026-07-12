locals {
  zvol_name = "${var.storage_pool}/${lower(replace(var.vm_name, "_", "-"))}-disk0"
  zvol_path = "/dev/zvol/${local.zvol_name}"
}

resource "truenas_dataset" "vm_disk" {
  name        = local.zvol_name
  type        = "VOLUME"
  volsize     = var.disk_size_gb * 1073741824
  compression = "LZ4"
  comments    = "OpenTofu-managed disk for ${var.vm_name}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "truenas_vm" "this" {
  name                  = var.vm_name
  description           = "Managed by OpenTofu from truenasVM"
  vcpus                 = var.vcpus
  cores                 = var.vcpus
  threads               = 1
  memory                = var.memory_mb
  cpu_mode              = "HOST-PASSTHROUGH"
  bootloader            = "UEFI"
  time                  = "UTC"
  autostart             = true
  desired_state         = "RUNNING"
  ensure_display_device = false

  cloud_init = {
    user_data = templatefile("${path.module}/templates/${var.provisioning_phase == "install" ? "user-data" : "bootstrap-data"}.yml.tftpl", {
      hostname       = var.vm_name
      ssh_user       = var.ssh_user
      ssh_public_key      = var.ssh_public_key
      login_password_hash = var.login_password_hash
      ip_address          = var.ip_address
      prefix_length  = var.prefix_length
      gateway        = var.gateway
      dns_servers    = var.dns_servers
    })
    meta_data    = "instance-id: ${var.vm_name}-${var.provisioning_phase}-v3\nlocal-hostname: ${var.vm_name}\n"
    filename     = "cloud-init-${var.vm_name}.iso"
    upload_path  = "/mnt/${var.storage_pool}/ISOs"
    device_order = 10000
  }

  disk_devices = [{
    path  = local.zvol_path
    type  = "VIRTIO"
    order = 1001
  }]

  cdrom_devices = [{
    path  = var.ubuntu_iso_path
    order = 1002
  }]

  nic_devices = [{
    type       = "VIRTIO"
    nic_attach = var.nic_attach
    order      = 1003
  }]

  lifecycle {
    ignore_changes = [display_devices]
  }

  depends_on = [truenas_dataset.vm_disk]
}

