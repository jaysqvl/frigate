group "default" {
  targets = ["deps", "rootfs", "native-sdk", "migraphx", "rocm"]
}

target deps {
  dockerfile = "docker/main/Dockerfile"
  platforms = ["linux/amd64"]
  target = "deps"
  output = ["type=cacheonly"]
}

target rootfs {
  dockerfile = "docker/main/Dockerfile"
  platforms = ["linux/amd64"]
  target = "rootfs"
  output = ["type=cacheonly"]
}

target native-sdk {
  dockerfile = "docker/rocm/Dockerfile.native-gfx90c"
  platforms = ["linux/amd64"]
  target = "native-sdk"
  output = ["type=cacheonly"]
}

target migraphx {
  dockerfile = "docker/rocm/Dockerfile.native-gfx90c"
  platforms = ["linux/amd64"]
  target = "migraphx-build"
  output = ["type=cacheonly"]
}

target rocm {
  dockerfile = "docker/rocm/Dockerfile.native-gfx90c"
  contexts = {
    deps = "target:deps",
    rootfs = "target:rootfs"
  }
  platforms = ["linux/amd64"]
  target = "rocm-deps"
}
