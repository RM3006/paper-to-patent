output "bucket_name" {
  value = cloudflare_r2_bucket.lake.name
}

output "bucket_location" {
  value = cloudflare_r2_bucket.lake.location
}
