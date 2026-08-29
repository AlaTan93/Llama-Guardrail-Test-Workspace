# Frontend build/dev toolchain — pinned for reproducibility.
# The host needs only Docker; node/npm live entirely in this image.
#
# Source is bind-mounted at runtime (see scripts/build_frontend.sh),
# so this image stays generic and cacheable.
FROM node:24.16.0-alpine3.22

# npm cache in /tmp so a non-root user can write it
ENV npm_config_cache=/tmp/.npm

WORKDIR /app

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
