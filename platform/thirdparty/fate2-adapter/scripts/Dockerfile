# Build stage
FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download || true

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o fate2-adapter ./cmd/adapter

# Runtime stage
FROM alpine:3.19

RUN apk add --no-cache ca-certificates

WORKDIR /app
COPY --from=builder /app/fate2-adapter /usr/local/bin/fate2-adapter

ENTRYPOINT ["/usr/local/bin/fate2-adapter"]
