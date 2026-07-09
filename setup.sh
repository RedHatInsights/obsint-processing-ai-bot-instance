#!/bin/bash
set -e

echo "obsint-processing-ai-bot-instance" > /home/botuser/app/.instance-id

# Instance-specific packages go here:
# dnf install -y --nodocs <package>
# pip3.12 install <package>
# npm install -g <package>

# Syft installation
echo "Installing syft..."
ARCH=$(uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/')
curl -fsSL "https://github.com/anchore/syft/releases/download/v1.21.0/syft_1.21.0_linux_${ARCH}.tar.gz" \
    | tar -xz -C /usr/local/bin syft

# Inject custom workflow symlinks into entrypoint (instance/ isn't copied yet
# during setup.sh, so we add a runtime hook that runs before the bot starts).
ENTRYPOINT="/home/botuser/app/entrypoint.sh"
HOOK='# Link custom workflows from instance config into presets/\nfor wf in /home/botuser/app/instance/*/agent/workflows/*/; do\n    [ -d "$wf" ] || continue\n    wf_name=$(basename "$wf")\n    target="/home/botuser/app/presets/workflows/$wf_name"\n    [ -e "$target" ] || ln -s "$wf" "$target"\ndone'
sed -i "/^exec uv run/i\\$HOOK" "$ENTRYPOINT"

echo "Instance setup complete: obsint-processing-ai-bot-instance"
