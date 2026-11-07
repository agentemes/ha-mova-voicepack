#!/usr/bin/with-contenv bashio
# Export add-on options for the Python server.
export VACUUM_ENTITY="$(bashio::config 'vacuum_entity')"
export HA_BASE_URL="$(bashio::config 'ha_base_url')"
# SUPERVISOR_TOKEN is injected by the Supervisor automatically.
bashio::log.info "Starting MOVA Voice Pack builder for ${VACUUM_ENTITY}"
cd /app
exec python3 server.py
