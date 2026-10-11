# Changelog

## 1.1.0

- Nouveau : réglages de combustion « Recette air » (-2 à +2) et « Recette granulés » (-3 à +3), comme dans l'app MCZ
  (lecture `C|RecuperoParametriExtra|11` au démarrage, après écriture et toutes les 10 min ; écriture `C|WriteBancaDati`)

## 1.0.1

- Fini les « indisponible » intempestifs : suppression du ping/pong websocket (mal géré par le module Maestro, coupures toutes les 1 à 3 min)
- Les entités ne passent indisponibles qu'après `unavailable_after` secondes sans données (180 s par défaut), plus à chaque micro-coupure
- Chien de garde : reconnexion automatique si le poêle ne répond plus, reconnexion plus rapide (2 s → 30 s max)

## 1.0.0

- Première version : choix `connection_mode` local / cloud, découverte MQTT Home Assistant,
  file de commandes avec anti-rebond, reconnexion automatique, broker Mosquitto automatique,
  compatibilité optionnelle avec l'ancien format `Maestro/State` / `Maestro/Command`.
