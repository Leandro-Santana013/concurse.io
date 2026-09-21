#!/usr/bin/env bash
set -Eeuo pipefail

# Monta um Block Volume OCI e prepara os diretórios usados pelo Compose.
# O script não formata um volume que já tenha filesystem: nesse caso ele
# preserva o conteúdo e apenas monta o dispositivo.

DEVICE="${1:-/dev/oracleoci/oraclevdb}"
MOUNT_POINT="${2:-/srv/concurse-data}"
APP_UID="${CONCURSE_APP_UID:-999}"
APP_GID="${CONCURSE_APP_GID:-999}"

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

if [[ ! -b "${DEVICE}" ]]; then
  echo "Dispositivo não encontrado: ${DEVICE}" >&2
  echo "Informe o caminho exibido pela OCI, por exemplo /dev/oracleoci/oraclevdb." >&2
  exit 1
fi

mkdir -p "${MOUNT_POINT}"

if ! blkid "${DEVICE}" >/dev/null 2>&1; then
  echo "O volume não possui filesystem; criando ext4 em ${DEVICE}."
  mkfs.ext4 -m 0 "${DEVICE}"
fi

UUID="$(blkid -s UUID -o value "${DEVICE}")"
if [[ -z "${UUID}" ]]; then
  echo "Não foi possível obter o UUID de ${DEVICE}." >&2
  exit 1
fi

FSTAB_LINE="UUID=${UUID} ${MOUNT_POINT} ext4 defaults,nofail,x-systemd.device-timeout=30 0 2"
if ! grep -Fq "UUID=${UUID} ${MOUNT_POINT} " /etc/fstab; then
  printf '%s\n' "${FSTAB_LINE}" >> /etc/fstab
fi

mountpoint -q "${MOUNT_POINT}" || mount "${MOUNT_POINT}"

mkdir -p \
  "${MOUNT_POINT}/pdfs" \
  "${MOUNT_POINT}/question-images" \
  "${MOUNT_POINT}/parse-cache" \
  "${MOUNT_POINT}/caddy-data" \
  "${MOUNT_POINT}/caddy-config"

# O Dockerfile cria o usuário app como usuário de sistema (UID/GID 999 na
# imagem Debian atual). Permita sobrescrever caso a imagem seja alterada.
chown -R "${APP_UID}:${APP_GID}" \
  "${MOUNT_POINT}/pdfs" \
  "${MOUNT_POINT}/question-images" \
  "${MOUNT_POINT}/parse-cache"

chmod 0750 \
  "${MOUNT_POINT}/pdfs" \
  "${MOUNT_POINT}/question-images" \
  "${MOUNT_POINT}/parse-cache"
chmod 0700 \
  "${MOUNT_POINT}/caddy-data" \
  "${MOUNT_POINT}/caddy-config"

echo "Block Volume montado em ${MOUNT_POINT}."
echo "UUID=${UUID}"
echo "Diretórios preparados para pdfs, imagens, cache e Caddy."
