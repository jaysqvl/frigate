# go2rtc H.264 packet reassembly fix

The image builds go2rtc 1.9.14 from upstream commit
`b5948cfb25404cc5cb37b166ecaa2dca20b11d4b` with the unchanged module graph and
the exact diff from [upstream PR 2491](https://github.com/AlexxIT/go2rtc/pull/2491),
at head `88024bf00912075b49d289573fa84cfda59c1682` and base
`eb75edcb1403c915666e0f3ac014ce6027bad5e8`.

The patch prevents incomplete H.264 FU-A fragments from being emitted as valid
keyframes when a consumer joins mid-frame or packets are lost. After packet loss,
it resumes output at a complete keyframe. It includes five upstream regression
tests. The production change is 49 added lines in two Go files.

The build verifies the vendored patch checksum, runs `go test ./pkg/h264`, and
cross-compiles with a digest-pinned Go compiler and `CGO_ENABLED=0`. The compiler
and source tree remain in the build stage. The runtime includes a build manifest
and license under `/usr/local/share/go2rtc/`. Its version reports
`1.9.14+dev.b5948cf.dirty`, identifying a modified 1.9.14 build.

This is an unmerged upstream backport, not an official go2rtc release. Neither
go2rtc 1.9.15 nor the current upstream Frigate dependency pin includes this fix.
Once an official release includes equivalent handling, return to the official
release binary and remove this patch, compiler stage, and corresponding image
qualification check together. Do not replace it with a newer release based only
on its version number.

No Frigate frontend, camera configuration, or ROCm runtime changes are needed.
