
apt-get update
apt-get install -y docker.io docker-compose git

systemctl start docker
systemctl enable docker

mkdir -p /opt/chatbot
cd /opt/chatbot

git clone https://github.com/a1344git/py03.git .

cat > .env << EOF
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=$(openssl rand -hex 32)
OPENAI_API_KEY=your_openai_api_key_here
EOF

docker-compose up -d
