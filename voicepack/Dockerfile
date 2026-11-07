ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 PIP_BREAK_SYSTEM_PACKAGES=1

# python + ffmpeg (audio convert) + curl (voice download)
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       python3 python3-pip ffmpeg curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# web server + Piper neural TTS (offline, MIT)
RUN pip3 install --no-cache-dir aiohttp piper-tts

# one English voice for typed-text -> speech
RUN mkdir -p /opt/piper \
  && curl -fL -o /opt/piper/en_US-lessac-medium.onnx \
     "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
  && curl -fL -o /opt/piper/en_US-lessac-medium.onnx.json \
     "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
