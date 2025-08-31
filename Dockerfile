FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev
COPY . .
# If TypeScript, uncomment:
# RUN npm run build
ENV NODE_ENV=production
EXPOSE 3001
CMD ["npm","start"]
