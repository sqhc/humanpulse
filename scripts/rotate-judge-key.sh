#!/usr/bin/env bash
# 移除云端 Jev API key，回退本地 Laya（10-22 key 到期用）。
# 幂等：重复执行无害；执行前自动备份 .env。
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "没有 .env，无需回退" >&2
  exit 0
fi

stamp=$(date +%Y%m%d%H%M%S)
cp .env ".env.bak-judge-$stamp"
echo "已备份 .env -> .env.bak-judge-$stamp"

# sed -i 在 macOS / GNU 上后缀参数不同，这里做兼容。
sed_del() { sed -i '' "$1" "$2" 2>/dev/null || sed -i "$1" "$2"; }
sed_sub() { sed -i '' "$1" "$2" 2>/dev/null || sed -i "$1" "$2"; }

# 1) 删除 JUDGEMENT_API_KEY 行
sed_del '/^JUDGEMENT_API_KEY=/d' .env

# 2) 回退 provider / base_url / model 到本地 Laya
set_env() {
  key="$1"; val="$2"
  if grep -q "^${key}=" .env; then
    sed_sub "s|^${key}=.*|${key}=${val}|" .env
  else
    printf '%s=%s\n' "$key" "$val" >> .env
  fi
}

set_env JUDGEMENT_PROVIDER laya
set_env JUDGEMENT_BASE_URL "http://127.0.0.1:8077"
set_env JUDGEMENT_MODEL laya-multilingual

echo "已回退：JUDGEMENT_PROVIDER=laya，JUDGEMENT_API_KEY 已移除"
echo "下一步：make doctor 确认判官状态；如需本地服务先 make laya-serve"
