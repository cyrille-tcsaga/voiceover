# voiceover

```
__     _____ ___ ____ _____ _____     _______ ____
\ \   / / _ \_ _/ ___| ____/ _ \ \   / / ____|  _ \
 \ \ / / | | | | |   |  _|| | | \ \ / /|  _| | |_) |
  \ V /| |_| | | |___| |__| |_| |\ V / | |___|  _ <
   \_/  \___/___\____|_____\___/  \_/  |_____|_| \_\
```

**voiceover** est un outil en ligne de commande qui génère des voix off
segment par segment à partir d'un simple fichier YAML, grâce à l'API
**Gemini Text-to-Speech**.

Il est pensé pour les vidéos (motion design, publicités, démos produit) : chaque
phrase du script devient un fichier WAV séparé, prêt à être placé sur la
timeline de votre logiciel de montage. Tous les segments partagent la même voix
et les mêmes consignes de style, pour un rendu homogène d'un bout à l'autre.

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configurer la clé API](#configurer-la-clé-api)
- [Démarrage rapide](#démarrage-rapide)
- [Écrire un script](#écrire-un-script)
- [Référence des commandes](#référence-des-commandes)
- [Fichiers produits](#fichiers-produits)
- [Méthode de travail conseillée](#méthode-de-travail-conseillée)
- [Dépannage](#dépannage)
- [Contribuer](#contribuer)

## Fonctionnalités

- **Un fichier WAV par segment**, nommé d'après son identifiant (`V01.wav`, `V02.wav`, …).
- **Style global et style par segment** : décrivez le ton une fois, puis affinez-le
  segment par segment si besoin.
- **Dictionnaire de prononciation** pour les noms de marque, sigles et mots étrangers.
- **Comparaison de voix** : faites lire le même segment par plusieurs voix pour
  choisir la bonne.
- **Audio prêt pour le montage** : 48 kHz, mono, 16 bits, silences coupés,
  volume normalisé.
- **Rapport de rythme** : durée, mots par seconde et loudness de chaque segment,
  avec une alerte si le débit est trop lent ou trop rapide.
- **Régénération ciblée** : refaites un seul segment sans toucher aux autres.
- **Robuste** : les erreurs temporaires de l'API (429, 5xx) sont réessayées
  automatiquement.

## Prérequis

- **Python 3.11** ou plus récent
- **Git**
- Une **clé API Gemini**, gratuite à obtenir sur <https://aistudio.google.com/apikey>

## Installation

```bash
git clone https://github.com/cyrille-tcsaga/voiceover.git
cd voiceover

python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate

pip install -e .
```

Vérifiez que l'installation fonctionne :

```bash
voiceover --help
```

> Pensez à réactiver l'environnement (`source .venv/bin/activate`) à chaque
> nouvelle session de terminal. La commande `python -m voiceover` est
> équivalente à `voiceover`.

## Configurer la clé API

L'outil lit la clé dans la variable d'environnement `GEMINI_API_KEY`. Le plus
simple est de la placer dans un fichier `.env` à la racine du dépôt :

```bash
cp .env.example .env
```

Puis ouvrez `.env` et renseignez votre clé :

```dotenv
GEMINI_API_KEY=votre_clé_ici
```

Le fichier `.env` est ignoré par git : votre clé ne sera jamais publiée par
erreur. Vous pouvez aussi définir la variable directement dans votre terminal :

```bash
export GEMINI_API_KEY=votre_clé_ici
```

## Démarrage rapide

Le dossier [`scripts/`](scripts/) contient deux scripts d'exemple complets. Pour
un premier essai :

```bash
# 1. Vérifier le texte qui sera envoyé à l'API (aucun appel, aucun coût)
voiceover generate scripts/autokool.yaml --dry-run

# 2. Générer toutes les voix off
voiceover generate scripts/autokool.yaml
```

Les fichiers sont écrits dans `output/autokool-promo/`, et un tableau
récapitulatif s'affiche à la fin :

```
output/autokool-promo/
├── V01.wav
├── V02.wav
├── …
└── report.json
```

## Écrire un script

Un script est un fichier YAML qui décrit le projet, la voix, le ton et la liste
des segments. Créez le vôtre en vous inspirant de cet exemple :

```yaml
project: ma-video             # nom du dossier de sortie : output/ma-video/
voice: Charon                 # voix utilisée (voir `voiceover voices`)
language: fr-FR               # langue, au format BCP-47 (défaut : fr-FR)

style: >                      # ton commun à tous les segments
  Voix masculine chaleureuse et assurée, débit de publicité radio dynamique
  mais clair, léger sourire dans la voix.

pronunciations:               # comment prononcer certains mots
  AutoKool: "Auto Koul"
  FCFA: "francs CFA"

segments:
  - id: V01
    text: "Cahiers perdus, élèves qui ne paient pas, examens oubliés..."
    style: "Ton de frustration compréhensive, pas triste."   # optionnel
  - id: V02
    text: "Et si tout tenait dans une seule application ? Voici AutoKool."
```

### Champs

| Champ | Obligatoire | Description |
|---|---|---|
| `project` | oui | Nom du projet, utilisé comme dossier de sortie. Lettres, chiffres, `.`, `_` et `-` uniquement. |
| `voice` | oui | Une voix Gemini préconstruite, par exemple `Charon`, `Kore` ou `Puck`. La casse est ignorée. |
| `language` | non | Code de langue BCP-47 (`fr-FR`, `en-US`, …). Défaut : `fr-FR`. |
| `style` | non | Consignes de ton, de débit et d'émotion, communes à tous les segments. |
| `pronunciations` | non | Remplacements appliqués au texte avant l'envoi à l'API. |
| `segments` | oui | Liste des segments, au moins un. |
| `segments[].id` | oui | Identifiant unique : lettres, chiffres, `_` et `-`. Il devient le nom du fichier WAV. |
| `segments[].text` | oui | Le texte à lire. |
| `segments[].style` | non | Consigne propre à ce segment, ajoutée après le style global. |

Les champs inconnus sont refusés : une faute de frappe comme `segmnets` est
signalée immédiatement au lieu d'être ignorée.

### Bien utiliser le style

Le style se rédige en langage naturel, comme une consigne donnée à un comédien.
Décrivez le **timbre** (« voix grave et posée »), le **débit** (« rythme
dynamique ») et l'**émotion** (« léger sourire dans la voix »). Le style d'un
segment s'ajoute au style global : utilisez-le pour marquer un changement de
ton ponctuel (une question, une conclusion, une énumération…).

### Corriger une prononciation

Si un mot est mal prononcé, ajoutez-le dans `pronunciations` en l'écrivant tel
qu'il doit être lu :

```yaml
pronunciations:
  HomeFinder: "Home Finder"
  SaaS: "sasse"
```

- Seuls les **mots entiers** sont remplacés : `SaaS` ne touche pas `SaaSify`.
- La **casse est respectée** : `SaaS` et `saas` sont deux entrées distinctes.
- Les entrées les plus longues sont appliquées en premier.
- Le rapport compte les mots sur le texte **original**, pas sur le texte remplacé.

Utilisez `--dry-run` pour voir le texte exact qui sera envoyé à l'API.

## Référence des commandes

### `voiceover generate` : générer les voix off

```bash
voiceover generate SCRIPT.yaml [OPTIONS]
```

| Option | Description |
|---|---|
| `--only V03,V07` | Ne génère que les segments indiqués. |
| `--skip-existing` | Ignore les segments dont le WAV existe déjà. |
| `--dry-run` | Affiche le texte et le style envoyés, sans appeler l'API. |
| `-o, --output-dir DIR` | Dossier racine de sortie (défaut : `output`). |
| `--model NOM` | Modèle TTS à utiliser (voir [Choisir le modèle](#choisir-le-modèle)). |

Exemples :

```bash
voiceover generate scripts/autokool.yaml                     # tout générer
voiceover generate scripts/autokool.yaml --only V03          # refaire un segment
voiceover generate scripts/autokool.yaml --skip-existing     # compléter les manquants
voiceover generate scripts/autokool.yaml -o ~/Videos/vo      # autre dossier de sortie
```

Si un segment échoue, les autres sont tout de même générés. Les erreurs sont
listées à la fin et la commande se termine avec un code de sortie non nul.

### `voiceover preview` : comparer des voix

Fait lire un même segment par plusieurs voix pour vous aider à choisir.

```bash
voiceover preview SCRIPT.yaml --voices Charon,Orus,Sadaltager [--segment V01]
```

| Option | Description |
|---|---|
| `--voices A,B,C` | Voix à comparer (obligatoire). |
| `--segment ID` | Segment à lire. Défaut : le premier du script. |
| `--dry-run` | Affiche ce qui serait envoyé, sans appeler l'API. |
| `-o, --output-dir DIR` | Dossier racine de sortie (défaut : `output`). |
| `--model NOM` | Modèle TTS à utiliser. |

Les extraits sont écrits dans `output/<project>/preview/<ID>_<Voix>.wav`.
Une fois votre choix fait, reportez la voix dans le champ `voice` du script.

### `voiceover voices` : lister les voix

```bash
voiceover voices                     # liste fournie par l'API
voiceover voices --language fr-FR    # filtrée par langue (via l'API)
voiceover voices --offline           # catalogue intégré, sans clé ni réseau
```

Sans clé API, ou si l'API est indisponible, l'outil affiche automatiquement
le catalogue intégré.

### Choisir le modèle

Le modèle par défaut est `gemini-3.8-flash-tts`. Vous pouvez le changer :

- pour une commande : `--model gemini-3.8-flash-lite-tts` ;
- pour toutes les commandes : `GEMINI_TTS_MODEL=gemini-3.8-flash-lite-tts` dans `.env`.

L'option `--model` est prioritaire sur la variable d'environnement.

## Fichiers produits

### Audio

Chaque segment est enregistré dans `output/<project>/<ID>.wav`, déjà traité
pour le montage :

| Traitement | Valeur |
|---|---|
| Format | WAV PCM 16 bits, mono, 48 kHz |
| Silences | Coupés au début et à la fin, avec une marge de 0,15 s |
| Volume | Normalisé à -16 LUFS, pic limité à -1 dBFS |

Comme tous les fichiers sont au même niveau sonore, vous pouvez les enchaîner
sans réajuster le volume de chaque clip.

### Rapport

Après chaque génération, un tableau s'affiche et le fichier
`output/<project>/report.json` est mis à jour. Il couvre **tous** les WAV
présents dans le dossier, y compris ceux des générations précédentes :

| Colonne | Signification |
|---|---|
| Durée | Longueur du clip, en secondes |
| Mots | Nombre de mots du texte original |
| Mots/s | Débit de lecture |
| Loudness | Volume mesuré, en LUFS |

Un débit **inférieur à 2,2** ou **supérieur à 3,2 mots par seconde** est
surligné en orange : le segment risque de sonner trop lent ou trop pressé. La
durée totale s'affiche en bas du tableau, pratique pour vérifier que la voix off
tient dans la durée de la vidéo.

## Méthode de travail conseillée

1. **Écrivez le script** : un segment par plan ou par phrase de la vidéo.
2. **Vérifiez le texte** avec `--dry-run`, surtout les prononciations.
3. **Choisissez la voix** avec `voiceover preview` sur un segment représentatif.
4. **Générez tout** avec `voiceover generate`.
5. **Lisez le rapport** : repérez les segments en orange et la durée totale.
6. **Ajustez** le texte ou le style des segments à revoir, puis régénérez-les
   seuls avec `--only`.
7. **Importez les WAV** dans votre logiciel de montage.

## Dépannage

**`GEMINI_API_KEY is not set`**
La clé n'est pas trouvée. Vérifiez que le fichier `.env` existe à la racine du
dépôt et contient `GEMINI_API_KEY=…`, ou exportez la variable dans votre terminal.

**Clé refusée par l'API**
La clé est invalide ou a été révoquée. Générez-en une nouvelle sur
<https://aistudio.google.com/apikey>.

**`unknown prebuilt voice`**
Le nom de voix n'existe pas. Lancez `voiceover voices --offline` pour voir la
liste des noms valides.

**`Invalid script …`**
Le YAML ne respecte pas le format attendu. Le message indique le champ fautif,
par exemple `segments.0.text: Value error, segment text must not be empty`
(les segments sont numérotés à partir de 0).

**`transient error …, retry 1 in 1.0s`**
Ce n'est pas une erreur bloquante : l'API est momentanément saturée et l'outil
réessaie tout seul, jusqu'à 5 fois, en doublant le délai à chaque tentative.
Si les échecs persistent, relancez plus tard avec `--skip-existing` pour ne
générer que les segments manquants.

**Un mot est mal prononcé**
Ajoutez-le dans `pronunciations` (voir [Corriger une prononciation](#corriger-une-prononciation)).

## Contribuer

Les contributions sont les bienvenues. Pour préparer un environnement de
développement :

```bash
pip install -e '.[dev]'
pytest
```

Les tests n'appellent jamais la vraie API : le client Gemini est remplacé par un
mock. Aucune clé n'est nécessaire pour les lancer.
