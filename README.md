# voiceover

Outil en ligne de commande qui génère des voix off segment par segment avec l'API
**Gemini Text-to-Speech**, pour les vidéos motion design. Chaque segment du script
(V01, V02, …) devient un fichier WAV séparé. Tous utilisent la même voix et les
mêmes consignes de style, ce qui permet de les caler directement au montage.

- Modèle par défaut : `gemini-3.8-flash-tts` (stable). Il est surchargeable avec
  `--model` ou la variable `GEMINI_TTS_MODEL` (par exemple `gemini-3.8-flash-lite-tts`).
- Sortie de l'API : PCM 16 bits signé little-endian, mono, 24 kHz.
- Post-traitement de chaque WAV :
  - conversion en 48 kHz, mono, 16 bits ;
  - suppression des silences au début et à la fin, avec une marge de 0,15 s ;
  - normalisation à -16 LUFS, avec un pic d'échantillon limité à -1 dBFS.

## Installation

Il faut Python 3.11 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Configuration de la clé API

La clé est lue **uniquement** dans la variable d'environnement `GEMINI_API_KEY`.
Elle peut être chargée depuis un fichier `.env`, qui est ignoré par git.

```bash
cp .env.example .env
# puis éditez .env :
# GEMINI_API_KEY=votre_clé
```

Pour obtenir une clé : <https://aistudio.google.com/apikey>.

Si la clé est absente, la commande s'arrête avec un message explicite. Si l'API la
refuse (clé invalide), même chose. En cas d'erreur 429 ou 5xx, l'outil réessaie
automatiquement jusqu'à 5 fois, avec un délai qui double à chaque tentative
(backoff exponentiel).

## Commandes

```bash
# Générer les 9 segments dans output/autokool-promo/
voiceover generate scripts/autokool.yaml

# Régénérer seulement certains segments
voiceover generate scripts/autokool.yaml --only V03,V07

# Ne pas refaire les fichiers déjà présents
voiceover generate scripts/autokool.yaml --skip-existing

# Afficher le texte final envoyé (après remplacements), sans appeler l'API
voiceover generate scripts/autokool.yaml --dry-run

# Lister les voix (via l'API si une clé est configurée, sinon catalogue intégré)
voiceover voices
voiceover voices --offline
voiceover voices --language fr-FR

# Comparer plusieurs voix sur un même segment
voiceover preview scripts/autokool.yaml --voices Charon,Orus,Sadaltager --segment V01
```

Les fichiers de prévisualisation sont écrits dans
`output/<project>/preview/<ID>_<Voix>.wav`.

On peut aussi lancer l'outil avec `python -m voiceover …`.

## Format du script YAML

```yaml
project: autokool-promo   # nom du dossier de sortie : output/<project>/
voice: Charon             # voix préconstruite (voir `voiceover voices`)
language: fr-FR           # code BCP-47
style: >                  # consignes de style communes à tous les segments
  Voix masculine chaleureuse et assurée, débit de publicité radio dynamique
  mais clair, léger sourire dans la voix. Français standard.
pronunciations:           # remplacements appliqués avant l'envoi à l'API
  AutoKool: "Auto Koul"
  FCFA: "francs CFA"
segments:
  - id: V01
    text: "Cahiers perdus, élèves qui ne paient pas, examens oubliés..."
    style: "Ton de frustration compréhensive, pas triste."   # optionnel, s'ajoute au style global
  - id: V02
    text: "Et si tout tenait dans une seule application ? Voici AutoKool."
```

Règles de validation :

- `project` : lettres, chiffres, `.`, `_` et `-` uniquement ;
- `voice` : obligatoire, doit être une voix préconstruite valide (la casse est ignorée) ;
- `segments` : au moins un segment, avec des `id` uniques et des `text` non vides ;
- les champs inconnus sont refusés, pour repérer les fautes de frappe.

Les prononciations remplacent des **mots entiers** : la casse est respectée et les
clés les plus longues sont appliquées en premier. Le style global et le style du
segment sont concaténés, puis envoyés comme consigne de style (`speech_metadata.style`).

## Rapport

Après chaque génération, l'outil écrit `output/<project>/report.json` et affiche un
tableau qui couvre tous les WAV présents dans le dossier. Pour chaque segment, on y
trouve :

- la durée ;
- le nombre de mots (comptés sur le texte original du script) ;
- le débit en mots par seconde ;
- la loudness mesurée.

Les débits inférieurs à 2,2 ou supérieurs à 3,2 mots par seconde sont signalés en
orange. La durée totale est indiquée en bas du tableau.

## Tests

```bash
pytest
```

Les tests n'appellent jamais la vraie API : le client Gemini est remplacé par un mock.
