# MCZ Maestro HA

[![Ajouter le dépôt à Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fbouboun59%2Fmcz-maestro-ha)

![aarch64](https://img.shields.io/badge/aarch64-yes-green.svg) ![amd64](https://img.shields.io/badge/amd64-yes-green.svg)

App (add-on) Home Assistant pour poêles à granulés **MCZ Maestro classique** (pas Maestro+) :
connexion **locale** ou **cloud** au choix, entités créées automatiquement via MQTT.

## Installation

1. **Paramètres › Apps › Boutique d'apps** (anciennement *Modules complémentaires › Boutique*) › **⋮** › **Dépôts**
2. Ajouter `https://github.com/bouboun59/mcz-maestro-ha`
3. Installer **MCZ Maestro HA**, régler `connection_mode`, démarrer.

## Mises à jour

Chaque changement de `version` dans `mcz_maestro/config.yaml` poussé sur `main` est proposé par Home Assistant
(activer **Mise à jour automatique** sur la page de l'app pour l'installer sans intervention).
Publier une version : `scripts/release.sh 1.0.1 "description"`.

## Développement

```bash
pip install -r mcz_maestro/requirements.txt pytest
pytest -q tests
# lancement hors HA
MCZ_OPTIONS=./options.json python -m mcz_maestro   # depuis mcz_maestro/rootfs/app
```

Crédits : Anthony-55, Chibald, pipolaq, SebLz.
