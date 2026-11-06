#!/bin/bash

set -euxo pipefail

# Keep the installed release and module graph; apply only the reviewed H.264 fix.
go2rtc_commit="b5948cfb25404cc5cb37b166ecaa2dca20b11d4b"
fix_commit="88024bf00912075b49d289573fa84cfda59c1682"
patch_sha256="442554a4024a2c3fff7b50ec9e33fa7a6b453b57631083137a610117846bde64"
patch_file="/deps/2491-h264-fua.patch"

case "${TARGETARCH:?TARGETARCH is required}" in
    amd64|arm64) ;;
    *) printf 'Unsupported go2rtc architecture: %s\n' "$TARGETARCH" >&2; exit 1 ;;
esac

printf '%s  %s\n' "$patch_sha256" "$patch_file" | sha256sum -c -

source_dir=$(mktemp -d)
trap 'rm -rf "$source_dir"' EXIT
git -C "$source_dir" init
git -C "$source_dir" fetch --depth=1 https://github.com/AlexxIT/go2rtc.git "$go2rtc_commit"
git -C "$source_dir" checkout --detach FETCH_HEAD
cd "$source_dir"
test "$(git rev-parse HEAD)" = "$go2rtc_commit"
git apply --check --whitespace=error "$patch_file"
git apply --whitespace=error "$patch_file"

# Run the upstream regression tests natively, then cross-compile the runtime binary.
go test ./pkg/h264
dest_dir="/rootfs/usr/local/go2rtc/bin"
mkdir -p "$dest_dir" /rootfs/usr/local/share/go2rtc
GOOS=linux GOARCH="$TARGETARCH" GOAMD64=v1 \
    go build -buildvcs=true -trimpath -ldflags "-s -w" -o "$dest_dir/go2rtc" .
chmod 755 "$dest_dir/go2rtc"
install -m 644 LICENSE /rootfs/usr/local/share/go2rtc/LICENSE

# Go embeds the original revision plus .dirty; this manifest identifies the patch.
binary_sha256=$(sha256sum "$dest_dir/go2rtc" | cut -d ' ' -f 1)
cat > /rootfs/usr/local/share/go2rtc/build.json <<EOF
{
  "upstream_version": "1.9.14",
  "upstream_commit": "$go2rtc_commit",
  "fix_pull_request": "https://github.com/AlexxIT/go2rtc/pull/2491",
  "fix_commit": "$fix_commit",
  "patch_sha256": "$patch_sha256",
  "go_version": "$(go env GOVERSION)",
  "os": "linux",
  "arch": "$TARGETARCH",
  "binary_sha256": "$binary_sha256"
}
EOF
chmod 644 /rootfs/usr/local/share/go2rtc/build.json
