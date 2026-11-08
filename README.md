# Whisper · Transcripció d'àudios en català

Programa per a **Windows** amb finestra gràfica per transcriure àudios a text amb [Whisper](https://github.com/openai/whisper) (OpenAI), sense haver d'utilitzar la consola.

Tot funciona **en local**, a l'ordinador: els àudios no es pugen a cap servei d'internet.

## Què permet fer

- Triar un o diversos àudios, o una carpeta sencera.
- Triar la carpeta on es desen les transcripcions i el nom del fitxer.
- Escollir l'idioma (català per defecte), el model i el format de sortida: `txt`, `srt`, `vtt`, `json`, `tsv` o tots alhora.
- Veure el progrés i aturar el procés en qualsevol moment.
- No sobreescriu mai fitxers existents: si el nom ja existeix, afegeix `(2)`.

## Requisits

- Windows 10 o 11
- Python 3.11 de 64 bits
- [FFmpeg](https://www.gyan.dev/ffmpeg/builds/) afegit al `PATH`
- `openai-whisper`

## Instal·lació

1. **Instal·la Python 3.11** des de [python.org](https://www.python.org/downloads/release/python-3119/).
2. **Instal·la FFmpeg**: descarrega una compilació per a Windows, descomprimeix-la (per exemple a `C:\ffmpeg`) i afegeix la carpeta `bin` al `PATH` de Windows. Comprova-ho al CMD amb `ffmpeg -version`.
3. **Crea la carpeta de treball** `C:\WhisperClasses` i, dins, l'entorn virtual i Whisper. Al CMD:

   ```
   cd C:\WhisperClasses
   py -3.11 -m venv .venv
   .venv\Scripts\activate.bat
   python -m pip install --upgrade pip
   pip install -U openai-whisper
   ```

4. **Copia** a `C:\WhisperClasses` els fitxers d'aquest repositori: `whisper_gui.py`, `Whisper.bat` i `icona_whisper.ico`.

## Ús

Fes doble clic a **`Whisper.bat`**. S'obre la finestra del programa:

1. Afegeix els àudios.
2. Tria la carpeta de sortida.
3. Ajusta les opcions (idioma, model, format).
4. Prem **Transcriure**.

La primera vegada que fas servir un model, es descarrega automàticament i pot trigar uns minuts.

## Models

| Model | Característiques |
|---|---|
| `tiny` | molt ràpid, precisió limitada |
| `base` | ràpid, precisió bàsica |
| `small` | equilibrat (recomanat per començar) |
| `medium` | més lent, més precís |
| `large` | el més lent i precís; necessita molta memòria |

Si existeix una carpeta `models` al costat del programa, els models es carreguen (i es descarreguen) allà. Això permet repartir el programa amb el model inclòs, sense necessitat d'internet.

## Crear un executable (`.exe`)

Amb `Whisper.bat` no cal cap `.exe`. Si vols un programa que funcioni en ordinadors sense Python:

1. Deixa `Crear_executable.bat`, `whisper_gui.py` i `icona_whisper.ico` a `C:\WhisperClasses`.
2. Fes doble clic a `Crear_executable.bat` (pot trigar entre 5 i 15 minuts).
3. El resultat és la carpeta `dist\Whisper`. Per compartir-lo, comprimeix tota la carpeta (`Whisper.exe` i `_internal` han d'anar sempre junts).

L'executable no està signat, de manera que Windows pot mostrar un avís de seguretat.

## Problemes freqüents

- **«ffmpeg no trobat»**: comprova que la carpeta `bin` de FFmpeg és al `PATH` i que has tancat i tornat a obrir el CMD o l'ordinador.
- **No s'obre la finestra**: assegura't d'haver obert el programa amb `Whisper.bat` i que la carpeta `.venv` és al costat.
- **Avís «Windows ha protegit el seu PC»**: prem *Més informació → Executa igualment*.

## Crèdits i llicència

- [Whisper](https://github.com/openai/whisper), d'OpenAI (llicència MIT).
- [FFmpeg](https://ffmpeg.org/).
- Aquest programa es distribueix sota la llicència MIT (vegeu el fitxer `LICENSE`).
