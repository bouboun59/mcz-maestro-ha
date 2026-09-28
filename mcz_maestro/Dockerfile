ARG BUILD_FROM
FROM $BUILD_FROM

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY rootfs /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
