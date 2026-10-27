#!/usr/bin/env bash
# Installs only the notification timer. It does not create a payment or refund.
set -euo pipefail

service_name=st8dom-order-notifications.service
timer_name=st8dom-order-notifications.timer
unit_dir=/etc/systemd/system
marker='# Managed by st8dom order automation'
action=${1:-install}
project_dir=${ST8DOM_PROJECT_DIR:-/srv/st8dom}

fail() { printf '%s\n' "$*" >&2; exit 1; }

[[ $(id -u) == 0 ]] || fail 'Run this installer as root (sudo bash …).'
command -v systemctl >/dev/null || fail 'systemctl is required.'
[[ -d /run/systemd/system ]] || fail 'The host must be running systemd.'
[[ $# -le 1 ]] || fail 'Usage: install-order-notifications.sh [install|remove|status]'

check_owned_unit() {
    local path=$1
    if [[ -e "$path" ]] && ! head -n 1 "$path" | grep -Fqx "$marker"; then
        fail "Refusing to replace a unit not managed by this installer: $path"
    fi
}

case "$action" in
    status)
        systemctl is-enabled "$timer_name" || true
        systemctl list-timers --all "$timer_name" --no-pager
        systemctl show "$service_name" \
            --property=ActiveState,SubState,Result,ExecMainStatus --no-pager
        exit 0
        ;;
    remove)
        check_owned_unit "$unit_dir/$service_name"
        check_owned_unit "$unit_dir/$timer_name"
        systemctl disable --now "$timer_name" 2>/dev/null || true
        # Let an already running SMTP job finish; do not interrupt it mid-send.
        rm -f "$unit_dir/$service_name" "$unit_dir/$timer_name"
        systemctl daemon-reload
        printf '%s\n' 'Timer removed. Any running batch may finish; order data and queued notices are preserved.'
        exit 0
        ;;
    install) ;;
    *) fail 'Usage: install-order-notifications.sh [install|remove|status]' ;;
esac

docker_bin=$(command -v docker) || fail 'docker is required.'
[[ "$docker_bin" == /* && "$project_dir" == /* ]] || fail 'Absolute paths are required.'
# Paths go into a systemd ExecStart. Restrict metacharacters/specifiers instead
# of guessing how an arbitrary shell path should be escaped for systemd.
[[ "$docker_bin" =~ ^/[a-zA-Z0-9_./-]+$ && "$project_dir" =~ ^/[a-zA-Z0-9_./-]+$ ]] \
    || fail 'Docker/project paths may contain only letters, digits, /, _, dot and hyphen.'
[[ -d "$project_dir" ]] || fail "Project directory not found: $project_dir"
"$docker_bin" compose version >/dev/null
container_id=$("$docker_bin" compose --project-directory "$project_dir" ps -q app)
[[ -n "$container_id" ]] || fail 'The app service is not running. Deploy the application first.'
[[ $("$docker_bin" inspect -f '{{.State.Running}}' "$container_id") == true ]] \
    || fail 'The app container must be running.'
# Reads readiness/counts only. Does not send mail or print credentials.
"$docker_bin" compose --project-directory "$project_dir" exec -T app flask order-email-status

check_owned_unit "$unit_dir/$service_name"
check_owned_unit "$unit_dir/$timer_name"
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

cat > "$work_dir/$service_name" <<EOF
$marker
[Unit]
Description=st8dom queued order emails (up to five per batch)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
ConditionPathIsDirectory=$project_dir

[Service]
Type=oneshot
WorkingDirectory=$project_dir
ExecStart=$docker_bin compose --project-directory $project_dir exec -T app flask order-notifications --limit 5
TimeoutStartSec=300
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > "$work_dir/$timer_name" <<EOF
$marker
[Unit]
Description=Process queued st8dom order emails every minute

[Timer]
OnBootSec=60s
OnUnitInactiveSec=60s
AccuracySec=5s
Unit=$service_name

[Install]
WantedBy=timers.target
EOF

install -m 0644 "$work_dir/$service_name" "$unit_dir/$service_name"
install -m 0644 "$work_dir/$timer_name" "$unit_dir/$timer_name"
systemctl daemon-reload
systemctl enable --now "$timer_name"
printf '%s\n' 'Timer installed. Sending requires ORDER_EMAIL_ENABLED=1 and valid SMTP settings.'
systemctl list-timers --all "$timer_name" --no-pager
