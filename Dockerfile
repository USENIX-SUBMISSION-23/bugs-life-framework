FROM python:3.10.1-slim-buster AS base

WORKDIR /app

RUN apt-get update -y
RUN apt install -y curl gconf-service libasound2 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgcc1 libgconf-2-4 libgdk-pixbuf2.0-0 libglib2.0-0 libgtk-3-0 libnspr4 libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 ca-certificates fonts-liberation libappindicator1 libnss3 lsb-release xdg-utils libgbm-dev xvfb dbus-x11 libnss3-tools python3-pip vim multiarch-support wget git procps \
 && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://get.docker.com/ | sh

# Install Java OpenSDK
RUN wget -O /tmp/java.tar https://download.java.net/java/GA/jdk11/9/GPL/openjdk-11.0.2_linux-x64_bin.tar.gz &&\
    tar xvf /tmp/java.tar -C /tmp/ &&\
    mv /tmp/jdk-11.0.2 /usr/local/
ENV PATH="${PATH}:/usr/local/jdk-11.0.2/bin/"

# Stuff needed for chrome versions < 40
RUN wget -O libgcrypt11.deb https://launchpadlibrarian.net/201289896/libgcrypt11_1.5.3-2ubuntu4.2_amd64.deb &&\
    wget -O libudev0.deb https://launchpad.net/ubuntu/+source/udev/175-0ubuntu9/+build/3386050/+files/libudev0_175-0ubuntu9_amd64.deb &&\
    wget -O libpng12.deb http://mirrors.kernel.org/ubuntu/pool/main/libp/libpng/libpng12-0_1.2.54-1ubuntu1_amd64.deb &&\
    dpkg -i libgcrypt11.deb &&\
    dpkg -i libudev0.deb &&\
    dpkg -i libpng12.deb &&\
    rm libgcrypt11.deb &&\
    rm libudev0.deb &&\
    rm libpng12.deb

# Stuff needed for chrome versions < 17
RUN ln -s /usr/lib/x86_64-linux-gnu/libnss3.so /usr/lib/x86_64-linux-gnu/libnss3.so.1d  &&\
    ln -s /usr/lib/x86_64-linux-gnu/libnssutil3.so /usr/lib/x86_64-linux-gnu/libnssutil3.so.1d  &&\
    ln -s /usr/lib/x86_64-linux-gnu/libsmime3.so /usr/lib/x86_64-linux-gnu/libsmime3.so.1d  &&\
    ln -s /usr/lib/x86_64-linux-gnu/libssl3.so /usr/lib/x86_64-linux-gnu/libssl3.so.1d  &&\
    ln -s /usr/lib/x86_64-linux-gnu/libplds4.so /usr/lib/x86_64-linux-gnu/libplds4.so.0d  &&\
    ln -s /usr/lib/x86_64-linux-gnu/libplc4.so /usr/lib/x86_64-linux-gnu/libplc4.so.0d  &&\
    ln -s /usr/lib/x86_64-linux-gnu/libnspr4.so /usr/lib/x86_64-linux-gnu/libnspr4.so.0d

ENV PYTHONPATH /app
ENV DISPLAY :1
# Disable content sandbox (causes trouble with older Firefox revisions) https://wiki.mozilla.org/Security/Sandbox/Seccomp
ENV MOZ_DISABLE_CONTENT_SANDBOX 1

COPY requirements.txt /app/requirements.txt
RUN  python3 -m pip install --user -r requirements.txt
ENV PATH="${PATH}:/root/.local/bin"
COPY profiles/firefox /app/profiles/firefox

#RUN (echo '#!/bin/bash'; echo "/usr/bin/google-chrome-proxy --no-sandbox --disable-gpu --use-fake-ui-for-media-stream \$*;") > /usr/bin/google-chrome &&\
#    chmod a+x /usr/bin/google-chrome

# Install certificates
COPY ./ssl/ /app/ssl/

# Chromium
RUN mkdir -p $HOME/.pki/nssdb &&\
    certutil -d sql:$HOME/.pki/nssdb -A -t TC -n myCA -i /app/ssl/myCA.crt &&\
    certutil -d sql:$HOME/.pki/nssdb -A -t TC -n littleproxy -i /app/ssl/LittleProxy_MITM.cer

# Firefox
RUN cd /app/profiles &&\
    # Legacy security databases (cert8.db and key3.db)
    certutil -A -n littleproxy -t CT,c -i /app/ssl/LittleProxy_MITM.cer -d firefox/default-67/ &&\
    certutil -A -n littleproxy -t CT,c -i /app/ssl/LittleProxy_MITM.cer -d firefox/tp-67/ &&\
    certutil -A -n myCA -t CT,c -i /app/ssl/myCA.crt -d firefox/default-67/ &&\
    certutil -A -n myCA -t CT,c -i /app/ssl/myCA.crt -d firefox/tp-67/ &&\
    # New SQL security databases (cert9.db and key4.db)
    certutil -A -n littleproxy -t CT,c -i /app/ssl/LittleProxy_MITM.cer -d sql:firefox/default-67/ &&\
    certutil -A -n littleproxy -t CT,c -i /app/ssl/LittleProxy_MITM.cer -d sql:firefox/tp-67/ &&\
    certutil -A -n myCA -t CT,c -i /app/ssl/myCA.crt -d sql:firefox/default-67/ &&\
    certutil -A -n myCA -t CT,c -i /app/ssl/myCA.crt -d sql:firefox/tp-67/
# More info: https://support.mozilla.org/en-US/questions/1207165
#cp firefox/cert8.db firefox/default-67/ &&\
#cp firefox/cert8.db firefox/tp-67/

# Copy rest of source code
COPY . /app
RUN mv /app/docker-config.yaml /app/config.yaml &&\
    mkdir -p /app/binaries/chromium/downloaded &&\
    mkdir -p /app/binaries/firefox/downloaded

# Add user which is not root
#RUN useradd -u 8877 notroot
#USER notroot

FROM base AS prod
CMD Xvfb :1 -screen 0 1024x768x16 &\
    python3 /app/bci/web_front/app.py

FROM base AS dev
CMD Xvfb :1 -screen 0 1024x768x16 &\
    python3 -m debugpy --listen 0.0.0.0:5678 /app/bci/web_front/app.py

FROM base AS worker
COPY ./worker/worker.sh /app/
RUN chmod a+x worker.sh
CMD Xvfb :1 -screen 0 1024x768x16