FROM node:22-slim

WORKDIR /app

COPY package.json .

RUN npm install --omit=dev

COPY index.js .

EXPOSE 5002
CMD ["node", "index.js"]

