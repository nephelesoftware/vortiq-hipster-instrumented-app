FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder
WORKDIR /app
COPY . .
RUN dotnet restore &&     dotnet publish -c release -o /cartservice

FROM mcr.microsoft.com/dotnet/aspnet:8.0-alpine

RUN apk add --no-cache wget &&     GRPC_HEALTH_PROBE_VERSION=v0.4.25 &&     wget -qO/bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 &&     chmod +x /bin/grpc_health_probe

WORKDIR /app
COPY --from=builder /cartservice .
ENTRYPOINT ["dotnet", "cartservice.dll", "start"]
