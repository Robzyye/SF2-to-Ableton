# SF2 → Ableton Sampler (autonome, sans extension Live 12 bêta)

Ce petit outil fait exactement ce que faisait l'import natif `.sf2`
qu'Ableton proposait avant Live 11 : il lit un SoundFont et génère des
presets **Sampler** (`.adv`) prêts à l'emploi, avec les échantillons audio
(`.aif`) qui vont avec.

Contrairement à l'extension `soundfont-importer` (qui nécessite la bêta
Live 12 + son SDK d'extensions), ce script ne touche pas du tout à Ableton :
il écrit juste des fichiers standards dans votre **User Library**. Le format
généré est celui d'Ableton Live 10.1, donc compatible avec **Live 10, 11 et
12**, bêta ou pas.

Aucune dépendance à installer : uniquement Python 3 (déjà présent sur macOS,
et facile à installer sur Windows).

## Utilisation la plus simple

Double-cliquez sur `sf2_to_ableton.py` (ou lancez `python3 sf2_to_ableton.py`
sans argument) : une petite fenêtre s'ouvre. Vous pouvez choisir soit :
- **Fichier…** : un seul `.sf2`
- **Dossier…** : un dossier contenant plusieurs `.sf2`, y compris dans des
  sous-dossiers (ex. `MesSoundfonts/Pianos/`, `MesSoundfonts/Drums/Kicks/`,
  etc.) — tout est converti d'un coup, avec une barre de progression et un
  journal affichant le résultat fichier par fichier. Si l'un des fichiers
  est corrompu ou incompatible, il est simplement signalé en échec et le
  traitement continue avec les suivants.

## En ligne de commande

```bash
# Conversion simple (détecte automatiquement votre User Library Ableton)
python3 sf2_to_ableton.py "MonInstrument.sf2"

# En précisant le dossier User Library (utile si détection automatique fausse,
# ou sur Linux où il n'y a pas d'emplacement standard)
python3 sf2_to_ableton.py "MonInstrument.sf2" --user-library "/chemin/vers/User Library"

# Ne convertir que certains presets (ex. tous les noms contenant "Piano")
python3 sf2_to_ableton.py "MonInstrument.sf2" --filter "Piano"

# Juste lister les presets contenus dans le SoundFont, sans convertir
python3 sf2_to_ableton.py --list "MonInstrument.sf2"

# Dossier entier : convertit récursivement TOUS les .sf2 trouvés,
# y compris dans les sous-dossiers
python3 sf2_to_ableton.py "C:\Mes SoundFonts"
python3 sf2_to_ableton.py "C:\Mes SoundFonts" --user-library "D:\Ableton\User Library"
```

En mode dossier, le script affiche une ligne par fichier traité (succès ou
échec) puis un résumé à la fin. Un fichier `.sf2` corrompu n'interrompt pas
le traitement des autres.

Emplacement par défaut de la User Library :
- macOS : `~/Music/Ableton/User Library`
- Windows : `%USERPROFILE%\Documents\Ableton\User Library`

## Après la conversion

Le script crée, dans votre User Library :

```
User Library/
  Samples/<NomDuSoundfont>/*.aif
  SoundFont Imports/<NomDuSoundfont>/*.adv
```

Dans Ableton Live : **Browser > Places** → clic droit → **Add Folder**, puis
choisissez le dossier `SoundFont Imports`. Vous n'avez besoin de le faire
qu'**une seule fois** : les conversions suivantes apparaîtront automatiquement
dedans, dans un sous-dossier par SoundFont.

Chaque preset `.adv` est un Sampler multi-échantillon classique : mapping des
touches, vélocité, root key et boucles sont repris tels quels depuis le SF2.
Vous pouvez ensuite le glisser sur une piste MIDI comme n'importe quel preset.

## Limites connues

- Les échantillons stéréo (paires gauche/droite liées dans le SF2) sont
  exportés comme deux mono séparés plutôt que fusionnés en un vrai stéréo —
  c'est le même comportement que l'extension officielle d'origine.
- Les échantillons ROM (SoundFonts pointant vers une puce audio, très rares
  de nos jours) ne sont pas exportés, faute de données audio dans le fichier.
- Les modulateurs SF2 (LFO, enveloppes avancées, etc.) ne sont pas repris :
  seuls le mapping clavier/vélocité, l'accordage de base et les boucles le
  sont — comme pour l'import natif historique d'Ableton.

## Origine du code

La logique de lecture SF2 et de génération du `.adv` est adaptée du projet
MIT [`soundfont-importer`](https://github.com/norakorra/soundfont-importer)
de Nora Korra, réécrite en Python pur pour fonctionner sans l'extension ni
la bêta d'Ableton.
