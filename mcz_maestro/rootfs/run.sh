#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

# Broker MQTT automatique (add-on Mosquitto) si aucun broker n'est saisi dans les options
if bashio::config.is_empty 'mqtt_host' && bashio::services.available "mqtt"; then
    export SUPERVISOR_MQTT_HOST="$(bashio::services mqtt 'host')"
    export SUPERVISOR_MQTT_PORT="$(bashio::services mqtt 'port')"
    export SUPERVISOR_MQTT_USER="$(bashio::services mqtt 'username')"
    export SUPERVISOR_MQTT_PASSWORD="$(bashio::services mqtt 'password')"
    bashio::log.info "Broker MQTT fourni par le Supervisor : ${SUPERVISOR_MQTT_HOST}:${SUPERVISOR_MQTT_PORT}"
fi

bashio::log.info "Démarrage de la passerelle MCZ Maestro HA (mode $(bashio::config 'connection_mode'))"
export APP_VERSION="$(bashio::addon.version)"
cd /app
exec python3 -u -m mcz_maestro
