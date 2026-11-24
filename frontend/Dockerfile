FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=builder /app ./
EXPOSE 3010
CMD ["npm", "run", "start", "--", "-p", "3010"]
