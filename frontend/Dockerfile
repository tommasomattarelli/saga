FROM node:24.22.0-alpine

WORKDIR /app

COPY package.json package-lock.json .node-version .npmrc ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host"]
