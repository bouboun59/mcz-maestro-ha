# Changelog

## 1.2.0

Protocole revérifié champ par champ sur l'application MCZ Maestro officielle.

Corrections :
- **Effets sonores** : le switch lisait l'unité °C/°F (champ 48) au lieu des effets sonores (champ 49)
- **Sleep** : c'est une minuterie en pas de 10 min, pas un on/off (`sleep ON` programmait une extinction dans 10 min)
- **Sondes WiFi** : valeurs divisées par 2 (°C) et ignorées quand la sonde est absente
- **Cellule 149** : c'est le profil de chauffe (0–4, +10 adaptatif), plus un simple on/off

Nouveautés :
- `select` **Profil de chauffe** (manual / dynamic / overnight / comfort / power) et switch **Mode adaptatif** (désactivé par défaut)
- `number` **Minuterie sleep** (0–490 min) et températures **chrono T1 / T2 / T3**
- `button` **Réinitialiser Active** et **Mettre le poêle à l'heure**
- `sensor` **Dernière alarme** avec historique horodaté (`C|RecuperaAllarmi`), **Programme chrono** du jour + semaine
  en attributs (`C|RecuperoGiornoChrono`), **Firmware carte**, **Active température**, sondes WiFi 1–3
- Commande `set/chrono_day` (`lundi|<24 hex>`) pour écrire la programmation d'un jour
- Recettes, chrono et alarmes relus au démarrage, après écriture, à chaque nouvelle alarme puis toutes les 10 min

## 1.1.2

- Choisir une puissance passe toujours le poêle en régulation manuelle (sinon la commande était ignorée)

## 1.1.1

- Capteurs « Active » (valeur mesurée) et « Active consigne » (valeur réglée) du mode Active

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
