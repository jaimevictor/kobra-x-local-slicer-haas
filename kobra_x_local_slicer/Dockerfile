FROM ubuntu:24.04 AS orca
ARG ORCA_VERSION=2.4.2
ARG ORCA_SHA256=d12fb8c8eac1aecd2dfb6377acd48f994f8fa439ed5292fa532dd82880f029fd
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl python3 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL "https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v${ORCA_VERSION}/OrcaSlicer_Linux_AppImage_Ubuntu2404_V${ORCA_VERSION}.AppImage" -o /tmp/orca.AppImage \
 && echo "${ORCA_SHA256}  /tmp/orca.AppImage" | sha256sum -c - \
 && chmod +x /tmp/orca.AppImage \
 && cd /opt \
 && /tmp/orca.AppImage --appimage-extract >/dev/null \
 && mv /opt/squashfs-root /opt/orca \
 && rm /tmp/orca.AppImage
COPY scripts/resolve_profiles.py /tmp/resolve_profiles.py
RUN mkdir -p /profiles/source /profiles/resolved \
 && PROFILE_ROOT="$(find /opt/orca -type d -path '*/resources/profiles/Anycubic' -print -quit)" \
 && test -n "$PROFILE_ROOT" \
 && mkdir -p /profiles/source/Anycubic \
 && cp -a "$PROFILE_ROOT"/. /profiles/source/Anycubic/ \
 && python3 /tmp/resolve_profiles.py \
      --vendor-root /profiles/source/Anycubic \
      --output-root /profiles/resolved \
      --orca-version "${ORCA_VERSION}" \
      --orca-source-ref "v${ORCA_VERSION}" \
      --machine "machine/Anycubic Kobra X 0.4 nozzle.json:kobra_x_04.resolved.json" \
      --process "process/0.20mm Standard @Anycubic Kobra X 0.4 nozzle.json:kobra_x_020_standard.resolved.json" \
      --filament "filament/Anycubic PLA @Anycubic Kobra X 0.4 nozzle.json:anycubic_pla_kobra_x.resolved.json"

FROM node:24-bookworm-slim AS frontend_vendor
WORKDIR /src
RUN npm init -y >/dev/null 2>&1 && npm install --ignore-scripts --save-exact three@0.179.1
RUN mkdir -p /vendor /libs \
 && cp node_modules/three/build/three.module.js /vendor/three.module.js \
 && cp node_modules/three/build/three.core.js /vendor/three.core.js \
 && cp node_modules/three/examples/jsm/loaders/STLLoader.js /vendor/STLLoader.js \
 && cp node_modules/three/examples/jsm/loaders/3MFLoader.js /vendor/3MFLoader.js \
 && cp node_modules/three/examples/jsm/controls/OrbitControls.js /vendor/OrbitControls.js \
 && cp node_modules/three/examples/jsm/libs/fflate.module.js /libs/fflate.module.js

FROM ubuntu:24.04 AS runtime
ARG ORCA_VERSION=2.4.2
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ORCA_VERSION=${ORCA_VERSION} \
    ORCA_APP=/opt/orca/AppRun \
    KOBRA_DATA_DIR=/data \
    KOBRA_PROFILE_DIR=/opt/kobra/profiles/resolved
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv nginx xvfb xauth \
      libgl1 libglu1-mesa libegl1 libgtk-3-0 libwebkit2gtk-4.1-0 libdbus-1-3 libxkbcommon0 \
      libx11-6 libxext6 libxrender1 libxi6 libxrandr2 libxfixes3 libxcursor1 \
      libfontconfig1 libfreetype6 libnss3 libasound2t64 ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/kobra
COPY requirements.txt /opt/kobra/requirements.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r /opt/kobra/requirements.txt
COPY --from=orca /opt/orca /opt/orca
COPY --from=orca /profiles/resolved /opt/kobra/profiles/resolved
COPY --from=frontend_vendor /vendor /opt/kobra/app/static/vendor
COPY --from=frontend_vendor /libs /opt/kobra/app/static/libs
COPY app /opt/kobra/app
COPY run.sh /opt/kobra/run.sh
COPY rootfs/etc/nginx/http.d/kobra.conf /etc/nginx/sites-enabled/default
RUN ln -s /opt/orca/AppRun /usr/local/bin/OrcaSlicer \
 && xvfb-run -a OrcaSlicer --help \
 && chmod +x /opt/kobra/run.sh \
 && mkdir -p /data/jobs /var/lib/nginx /var/log/nginx /run/nginx \
 && chown -R root:root /opt/kobra /data
EXPOSE 8099
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["/opt/kobra/run.sh"]
