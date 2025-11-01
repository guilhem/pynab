# Support multiple Python versions
ARG PYTHON_VERSION=3.9
FROM python:${PYTHON_VERSION}-bullseye

# Install extras to include (default: none for Docker)
ARG INSTALL_EXTRAS=""

RUN apt-get update && apt-get install -y \
    postgresql-client gettext \
    libmpg123-dev libasound2-dev \
    wireless-tools sudo

COPY Docker/nab/*.sh /usr/local/bin/

# Fake nabd systemd service file used to retrieve the working directory
RUN echo "WorkingDirectory=/opt/pynab" > /lib/systemd/system/nabd.service

# Fake systemd-time-wait-sync.service needed by nabclockd
RUN mkdir -p /run/systemd/timesync/ && touch /run/systemd/timesync/synchronized

# Naively fake systemctl, used to check if the SSH service is active
RUN ln -s /bin/false /bin/systemctl

# Make /var/log/ writable for service log files, /run for PID files
RUN chmod a+w /var/log /run

# Set timezone
RUN echo "Europe/Paris" > /etc/timezone
RUN ln -fs /usr/share/zoneinfo/Europe/Paris /etc/localtime

# Make sure piwheels is available for pip
RUN /bin/echo -e "[global]\nextra-index-url=https://www.piwheels.org/simple\n" > /etc/pip.conf

RUN groupadd -g 1000 pi
RUN useradd -u 1000 -g pi -m -s /bin/bash tagtagtag
RUN echo "tagtagtag ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/010_tagtagtag-nopasswd

RUN mkdir -p /opt/pynab /opt/venv
RUN chown tagtagtag:pi /opt/pynab /opt/venv

USER tagtagtag

WORKDIR /opt/pynab

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv ${VIRTUAL_ENV}
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

# Copy pyproject.toml for modern pip installation
COPY --chown=tagtagtag:pi pyproject.toml /opt/pynab/
COPY --chown=tagtagtag:pi requirements.txt /opt/pynab/

# Install using pip with optional extras
# Default: no ASR/NLU for Docker (use INSTALL_EXTRAS build arg to customize)
RUN ${VIRTUAL_ENV}/bin/pip install --upgrade pip wheel
RUN if [ -n "${INSTALL_EXTRAS}" ]; then \
        ${VIRTUAL_ENV}/bin/pip install -e "/opt/pynab[${INSTALL_EXTRAS}]"; \
    else \
        # Fallback to requirements.txt without ASR/NLU
        grep -v -e py-kaldi-asr -e snips-nlu < /opt/pynab/requirements.txt > /tmp/requirements_docker.txt && \
        ${VIRTUAL_ENV}/bin/pip install -r /tmp/requirements_docker.txt; \
    fi

ENV NABD_HOST=pynab
ENV NABD_PORT_NUMBER=10543

EXPOSE 8000
EXPOSE 10543
EXPOSE 10544
