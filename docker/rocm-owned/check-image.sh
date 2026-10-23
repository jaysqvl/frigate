#!/bin/bash
# Qualify an image without devices, networking, or production data.
set -euo pipefail
image=${1:?Pass the image ID or immutable digest}
image=$(docker image inspect --format '{{.Id}}' "$image")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
output=${2:?Pass an evidence directory}
mkdir -p "$output"
output=$(cd "$output" && pwd)
checks=$(cd "$(dirname "$0")" && pwd)
owner="frigate-image-check-$$-${RANDOM}"
containers=()
boot_id=
cleanup() {
    local id state label actual_image
    for id in "${containers[@]}"; do
        state=$(docker inspect --format '{{.State.Status}}' "$id")
        label=$(docker inspect --format '{{index .Config.Labels "io.jaysqvl.image-check"}}' "$id")
        actual_image=$(docker inspect --format '{{.Image}}' "$id")
        test "$label" = "$owner"
        test "$actual_image" = "$image"
        if [ "$id" = "$boot_id" ]; then
            if [ "$state" = running ] || [ "$state" = restarting ]; then
                docker stop --time 60 "$id" >> "$output/cleanup.txt"
            fi
            docker logs "$id" > "$output/boot.log" 2>&1
            docker inspect "$id" > "$output/boot-after.json"
            state=$(docker inspect --format '{{.State.Status}}' "$id")
        fi
        if [ "$state" = running ] || [ "$state" = restarting ]; then
            printf 'Cleanup blocked: owned check container %s is still %s\n' "$id" "$state" >&2
            return 1
        fi
        docker rm "$id" >> "$output/cleanup.txt"
    done
}
trap cleanup EXIT
check() {
    local name=$1 id
    shift
    id=$(docker create --network none --read-only --user 1000:1000 \
        --cpus 4 --memory 10g --memory-swap 10g --pids-limit 1024 --no-healthcheck \
        --tmpfs /tmp:rw,exec,size=2g \
        --label "io.jaysqvl.image-check=$owner" \
        --env FRIGATE_OFFLINE_CHECK=1 --env FRIGATE_TEST_SOURCE_ROOT=/opt/frigate \
        --env OMP_NUM_THREADS=2 --env PYTHONDONTWRITEBYTECODE=1 \
        --env AMD_COMGR_CACHE_DIR=/tmp/comgr --env MIOPEN_CUSTOM_CACHE_DIR=/tmp/miopen \
        --env MIOPEN_USER_DB_PATH=/tmp/miopen \
        --mount "type=bind,source=$checks,target=/checks,readonly" \
        --workdir /opt/frigate --entrypoint python3 "$image" "$@")
    [[ "$id" =~ ^[a-f0-9]{64}$ ]]
    containers+=("$id")
    printf '%s\n' "$id" >> "$output/containers.txt"
    docker inspect "$id" > "$output/$name-before.json"
    docker start --attach "$id" > "$output/$name.log" 2>&1 || true
    docker inspect "$id" > "$output/$name-after.json"
    cat "$output/$name.log"
    docker inspect --format '{{json .State}}' "$id" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert state["Status"] == "exited" and state["ExitCode"] == 0 and not state["OOMKilled"], state
'
}
check runtime -u /checks/smoke.py
check adapter -u /checks/test_plugin.py
check config-migrations -u -m unittest frigate.test.test_config_migration

# Start the actual service with volatile, empty appdata. No ports are published.
boot_id=$(docker create --network none --cpus 2 --memory 4g --memory-swap 4g \
    --pids-limit 1024 --shm-size 256m \
    --tmpfs /config:rw,size=256m --tmpfs /media/frigate:rw,size=128m \
    --tmpfs /tmp/cache:rw,size=128m \
    --label "io.jaysqvl.image-check=$owner" \
    --env FRIGATE_OFFLINE_CHECK=1 --env PYTHONDONTWRITEBYTECODE=1 \
    --env OMP_NUM_THREADS=2 \
    --mount "type=bind,source=$checks,target=/checks,readonly" \
    --entrypoint /bin/bash "$image" -c \
    'test ! -e /dev/kfd && test ! -e /dev/dri && cp /checks/empty-config.yml /config/config.yml && exec /init')
[[ "$boot_id" =~ ^[a-f0-9]{64}$ ]]
containers+=("$boot_id")
printf '%s\n' "$boot_id" >> "$output/containers.txt"
docker inspect "$boot_id" > "$output/boot-before.json"
docker start "$boot_id" > /dev/null
ready=false
for attempt in $(seq 1 60); do
    if docker exec --user frigate "$boot_id" python3 -u /checks/smoke.py --boot \
        > "$output/boot.json" 2> "$output/boot-pending.log"; then
        health=$(docker inspect --format '{{.State.Health.Status}}' "$boot_id")
        if [ "$health" = healthy ]; then
            ready=true
            break
        fi
    fi
    if [ "$(docker inspect --format '{{.State.Running}}' "$boot_id")" != true ]; then
        break
    fi
    sleep 2
done
if [ "$ready" != true ]; then
    docker logs "$boot_id" >&2
    cat "$output/boot-pending.log" >&2
    exit 1
fi
docker inspect "$boot_id" > "$output/boot-healthy.json"
cat "$output/boot.json"
docker stop --time 60 "$boot_id" > /dev/null
docker logs "$boot_id" > "$output/boot.log" 2>&1
docker inspect "$boot_id" > "$output/boot-after.json"
python3 "$checks/smoke.py" --shutdown "$output/boot-after.json" "$output/boot.log" \
    > "$output/shutdown.log"
cat "$output/shutdown.log"
