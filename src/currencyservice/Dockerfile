FROM node:18-alpine

WORKDIR /usr/src/app

RUN wget -qO/bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.0/grpc_health_probe-linux-amd64 && chmod +x /bin/grpc_health_probe

COPY package*.json ./
RUN npm install --only=production

COPY . .

EXPOSE 7000
CMD ["node", "server.js"]
