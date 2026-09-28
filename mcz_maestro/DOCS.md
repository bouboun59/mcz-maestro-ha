# MCZ Maestro HA

Passerelle MQTT entre un poêle **MCZ Maestro « classique »** (pas Maestro+) et Home Assistant,
avec **choix du mode de connexion : `local` ou `cloud`**, et **découverte MQTT automatique**
(les entités apparaissent seules dans HA, regroupées sous un appareil « Poêle MCZ »).

Projet indépendant de l'ancien add-on *Maestro Gateway MC* : slug, topics MQTT et identifiants d'entités différents, les deux peuvent coexister.

> Le Maestro+ (M1+, app « MCZ Maestro+ ») utilise une API différente et n'est pas concerné.

## Modes de connexion

| Mode | Principe | Prérequis |
|---|---|---|
| `local` | Websocket direct sur le module Maestro (`ws://<ip>:81`) — aucune dépendance internet | HA doit joindre le poêle : soit via son point d'accès Wi-Fi (`192.168.120.1`), soit via son IP sur votre réseau s'il y est connecté |
| `cloud` | Serveur socket.io MCZ (`http://app.mcz.it:9000`), comme l'app Maestro | Poêle connecté à internet + n° de série et MAC (app Maestro › Réglages › Info) |

Changer de mode = modifier l'option `connection_mode` puis redémarrer l'add-on. Les entités HA restent
identiques (mêmes `unique_id`), seuls les capteurs de diagnostic indiquent le mode actif.

## Configuration minimale

**Local :**
```yaml
connection_mode: local
local_host: 192.168.120.1
local_port: 81
```

**Cloud :**
```yaml
connection_mode: cloud
cloud_serial: "1234567890123"
cloud_mac: "AABBCCDDEEFF"
```

Le broker MQTT est récupéré automatiquement depuis l'add-on Mosquitto : laissez `mqtt_host` vide.

## Entités créées

- `climate` : marche/arrêt, consigne (pas de 0,5 °C), température ambiante, ventilation ambiance
- `switch` : marche, Eco, Silence, Chronothermostat, Active, effets sonores, mode été, antigel
- `select` : puissance 1–5, régulation auto/manuel, ventilation ambiance (+ canalisées selon `ducted_fans`)
- `number` : consigne ; `button` : acquitter l'alarme, rafraîchir
- `sensor` : état, températures (ambiante, fumées, carte mère), profil, heures de fonctionnement,
  heures avant entretien, nb d'allumages, RPM extracteur / vis sans fin, horloge du poêle…
- `binary_sensor` : en chauffe, alarme, pellets bas, bougie, connexion poêle

Avec `hydro: true` : températures chaudière / puffer / retour et consigne chaudière.

`auto_regulation: true` reproduit le comportement de l'ancien script local : changer la consigne
passe la régulation en **auto**, changer la puissance la passe en **manuel**.

## Topics MQTT

| Topic | Sens | Contenu |
|---|---|---|
| `mcz_maestro/state` | publié | JSON complet (retenu) |
| `mcz_maestro/bridge/status` / `mcz_maestro/stove/status` | publié | `online` / `offline` |
| `mcz_maestro/set/<commande>` | commande | `power`, `setpoint`, `power_level`, `fan_ambient`, `fan_ducted1`, `fan_ducted2`, `regulation`, `eco`, `silent`, `active`, `chrono`, `sound`, `sleep`, `summer`, `antifreeze`, `adaptive`, `pellet_sensor`, `boiler_setpoint`, `reset_alarm`, `refresh` |
| `mcz_maestro/raw_command` | commande | brut `id,valeur` ou multiple `id,valeur;id,valeur` |

### Compatibilité avec l'ancien add-on (`legacy_enabled`, **désactivé par défaut**)

- publication du **JSON historique** (clés françaises : `Etat du poele`, `TEMP - Consigne`…) sur `Maestro/State` ;
- commandes **multiples** acceptées sur `Maestro/Command` : `34,1;42,21` (la consigne 42 reste en °C).

⚠️ N'activez cette option **qu'après avoir arrêté l'ancien add-on**, sinon chaque commande `Maestro/Command` serait envoyée deux fois au poêle.

## Paramètres utiles (`raw_command`)

| id | Rôle | Valeurs |
|---|---|---|
| 34 | Marche / arrêt | 1 / 40 |
| 36 | Puissance | 1–5 |
| 37 / 38 / 39 | Ventilateur ambiance / canalisé 1 / 2 | 0 = off, 1–5, 6 = auto |
| 40 | Régulation | 1 = auto (thermostat), 0 = manuel |
| 41 / 45 / 35 | Eco / Silence / Active | 0 / 1 |
| 42 | Consigne | °C (×2 appliqué automatiquement) |
| 1111 | Chronothermostat | 0 / 1 |
| 1 | Acquittement alarme | 255 |

## Coexistence avec l'ancien add-on

- **Cloud** : les deux peuvent tourner en même temps (comme l'app sur le téléphone).
- **Local** : le module Maestro accepte peu de connexions websocket simultanées ; si l'ancien add-on est aussi en local, arrêtez-le pendant les tests ou testez le nouveau en cloud.

## Crédits

Anthony-55 (script d'origine), Chibald (maestrogateway local), pipolaq (version cloud), SebLz (add-on).
