# Usar la imagen base de Go
FROM golang:1.21-alpine

WORKDIR /app

COPY . ./

RUN go mod init go-executor
RUN go mod tidy
RUN go build -o go-executor

EXPOSE 6000

CMD ["./go-executor"]
