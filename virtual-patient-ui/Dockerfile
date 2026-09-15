# syntax=docker/dockerfile:1

FROM node:20-alpine AS dependencies

WORKDIR /app

COPY package.json yarn.lock .yarnrc.yml ./
COPY .yarn ./.yarn

RUN --mount=type=cache,target=/root/.yarn/berry/cache \
    node .yarn/releases/yarn-4.6.0.cjs install --immutable


FROM dependencies AS development

COPY . .

EXPOSE 5173

CMD ["sh", "-c", "node .yarn/releases/yarn-4.6.0.cjs install --immutable && exec node .yarn/releases/yarn-4.6.0.cjs dev --host 0.0.0.0"]


FROM dependencies AS build

ARG VITE_RECAPTCHA_SITE_KEY
ARG VITE_API_HOST
ARG VITE_API_PORT
ARG VITE_SPEECH_INPUT_PROVIDER

ENV VITE_RECAPTCHA_SITE_KEY=${VITE_RECAPTCHA_SITE_KEY} \
    VITE_API_HOST=${VITE_API_HOST} \
    VITE_API_PORT=${VITE_API_PORT} \
    VITE_SPEECH_INPUT_PROVIDER=${VITE_SPEECH_INPUT_PROVIDER}

COPY . .

RUN node .yarn/releases/yarn-4.6.0.cjs build


FROM nginx:alpine AS production

RUN apk add --no-cache curl

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl --fail --insecure https://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
