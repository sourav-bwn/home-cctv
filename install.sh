#!/data/data/com.termux/files/usr/bin/bash
set -e

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
REPO="https://raw.githubusercontent.com/sourav-bwn/home-cctv/main"

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Home CCTV — One-Click Setup${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}[1/7]${NC} Granting storage access..."
termux-setup-storage || true

echo -e "${YELLOW}[2/7]${NC} Updating packages..."
pkg update -y && pkg upgrade -y

echo -e "${YELLOW}[3/7]${NC} Installing Python, ffmpeg, Termux:API..."
pkg install python ffmpeg termux-api -y

echo -e "${YELLOW}[4/7]${NC} Installing Python libraries..."
pip install python-telegram-bot flask --quiet

echo -e "${YELLOW}[5/7]${NC} Downloading bot..."
curl -sL "$REPO/bot.py" -o ~/bot.py

echo -e "${YELLOW}[6/7]${NC} Configuring..."
echo ""
echo -e "${CYAN}── Telegram Bot Setup ──${NC}"
echo -e "1. Open Telegram → search ${GREEN}@BotFather${NC}"
echo -e "2. Send ${GREEN}/newbot${NC} → pick a name → pick a username ending in ${GREEN}_bot${NC}"
echo -e "3. Copy the token BotFather gives you"
echo ""
read -p "Paste your BotFather token: " TOKEN
read -p "Paste your Telegram User ID (get from @userinfobot): " USER_ID
read -p "Set a password for the web dashboard: " WEB_PASS
echo ""

python3 - "$TOKEN" "$USER_ID" "$WEB_PASS" <<'PYEOF'
import json, sys, os
token, uid, pw = sys.argv[1], int(sys.argv[2]), sys.argv[3]
config = {
    "token": token, "allowed_users": [uid],
    "web_password": pw, "stream_port": 8554, "web_port": 5000
}
with open(os.path.expanduser("~/.cctv_config.json"), "w") as f:
    json.dump(config, f, indent=2)
print("Config saved.")
PYEOF

echo -e "${YELLOW}[7/7]${NC} Setting up auto-start..."
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/cctv.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~
nohup python bot.py > ~/cctv.log 2>&1 &
EOF
chmod +x ~/.termux/boot/cctv.sh

echo -e "${YELLOW}Starting bot...${NC}"
termux-wake-lock
nohup python ~/bot.py > ~/cctv.log 2>&1 &
sleep 2

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${CYAN}📱 Telegram:${NC}  Open Telegram → send ${GREEN}/start${NC}"
echo -e "  ${CYAN}🌐 Web:${NC}       http://$IP:5000"
echo -e "  ${CYAN}📺 Stream:${NC}    rtsp://$IP:8554/live"
echo ""
echo -e "  ${YELLOW}Commands:${NC} /photo /torch /stream /lock /battery"
echo -e "           /sensors /reboot /speak /ping"
echo ""
