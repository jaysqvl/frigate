target "frigate-base" {
  context = "."
  dockerfile = "docker/main/Dockerfile"
  target = "frigate"
  platforms = ["linux/amd64"]
}

target "frigate-rocm" {
  context = "."
  dockerfile = "docker/rocm-owned/Dockerfile"
  contexts = {
    frigate-base = "target:frigate-base"
  }
  platforms = ["linux/amd64"]
}
