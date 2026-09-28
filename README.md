# Pynab

Logiciel libre pour les Nabaztag équipés d'une carte **TagTagTag 2019/2021** ou **NFC 2022**, avec Raspberry Pi Zero ou Zero 2.

[![Images](https://github.com/nabaztag2018/pynab/actions/workflows/images.yml/badge.svg)](https://github.com/nabaztag2018/pynab/actions/workflows/images.yml)

Cette génération utilise **Raspberry Pi OS Lite Trixie + RAUC**, avec PipeWire et un bus MQTT 5 local. Le cœur matériel est en Rust ; l'interface, la configuration et les services sont en Go. Les réglages sont enregistrés atomiquement dans un fichier JSON versionné : aucun serveur de base de données n'est nécessaire.

La qualification du démarrage, des pilotes et du rollback sur les deux matériels est requise avant publication. Les constructions de développement et les tests de simulation ne constituent pas cette qualification.

## Installation

1. Télécharger l'image `.img.xz` correspondant au matériel dans une [release qualifiée](https://github.com/nabaztag2018/pynab/releases) : `zero-armv6` pour le Zero original, `zero2-arm64` pour le Zero 2.
2. Vérifier `SHA256SUMS`, puis flasher une carte microSD de **16 Go minimum**.
3. Démarrer le lapin et configurer le Wi-Fi depuis le point d'accès Comitup.
4. Ouvrir l'interface locale et terminer la configuration de l'administration.

L'installation historique nécessite un **reflash** ; les anciens réglages ne sont pas migrés. SSH est désactivé par défaut. DietPi et la carte Maker Faire 2018 ne font pas partie de cette génération.

Les mises à jour sont proposées dans l'interface après une recherche quotidienne sur GitHub Releases. L'installation est déclenchée par l'utilisateur. RAUC vérifie la signature et la compatibilité, écrit le slot inactif, puis valide le nouveau système après contrôle des services locaux. Les données et réglages sont conservés. Firmware Raspberry Pi et U-Boot restent ceux du flash initial.

## Composants

| Composant | Rôle |
|---|---|
| `core/` — `nab-core` | Matériel, états, séquences, chorégraphies, synchronisation avec le son |
| `services/` — `nab-service` | Interface locale, réglages, horloge, météo, ressources, Home Assistant, mises à jour |
| Mosquitto | Transport MQTT 5 local ; [contrat JSON v1](docs/protocol-v1.md) |
| PipeWire + WirePlumber | Lecture et capture ALSA ; compatibilité PulseAudio pour la voix |
| NetworkManager + Comitup | Connexion Wi-Fi et configuration initiale |
| RAUC + U-Boot | Installation signée A/B et retour à la version précédente |

Linux Voice Assistant est préinstallé uniquement sur ARM64 et **désactivé par défaut**. Son activation utilise Home Assistant pour la reconnaissance et la synthèse. Le bouton précède la qualification du mot d'activation et de l'annulation d'écho. L'API de périphériques reste en boucle locale.

Les pilotes existants oreilles, WM8960, CR14 et ST25R391x, la bibliothèque `rpi_ws281x` et les ressources audio/chorégraphiques sont réutilisés. Un seul lecteur RFID est activé selon le matériel détecté. Les répertoires Python historiques sont conservés comme références et sources de ressources ; ils ne sont pas installés dans les nouvelles images.

## Développement

La [documentation de fabrication](docs/build.md) décrit les commandes locales, les runners GitHub standards, les dépendances archivées, les secrets de signature et le partitionnement. La [fiche de qualification](docs/release-checklist.md) accompagne les brouillons de release.

```sh
cargo test --locked --manifest-path core/Cargo.toml
(cd services && go test -race ./...)
python3 -m unittest discover -s image -p 'test_*.py' -v
python3 tools/integration.py
```

Le dernier contrôle requiert Mosquitto et ses clients. Les règles de contribution sont dans [CONTRIBUTING.md](CONTRIBUTING.md).

Les logiciels ajoutés sont libres. Les firmwares binaires nécessaires au Raspberry Pi restent une exception fournie par Raspberry Pi OS.
