#!/usr/bin/env bash
# Install Docker CE on CentOS Stream 10. Tries an in-cloud mirror first and
# falls back to the official repo.
set -euo pipefail

REPO_TENCENT=https://mirrors.tencentyun.com/docker-ce/linux/centos/docker-ce.repo
REPO_OFFICIAL=https://download.docker.com/linux/centos/docker-ce.repo

dnf -y install dnf-plugins-core >/dev/null

pick_repo() {
  for r in "$REPO_TENCENT" "$REPO_OFFICIAL"; do
    if curl -fsS --max-time 8 "$r" -o /etc/yum.repos.d/docker-ce.repo 2>/dev/null; then
      echo "$r"; return 0
    fi
  done
  return 1
}
echo "==> repo: $(pick_repo)"

# The docker-ce repo has a complete centos/10 tree.
dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version --format 'client={{.Client.Version}} server={{.Server.Version}} api={{.Server.APIVersion}}'
docker compose version --short
