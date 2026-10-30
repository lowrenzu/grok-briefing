#!/usr/bin/env python3
"""Lance JARVIS sur cet ordinateur, sans réglage ni compte.

Double-clic sur le fichier correspondant à votre système :
    Windows  : LANCER-JARVIS.bat
    Mac      : Lancer-JARVIS.command

Ce que fait ce script, dans l'ordre :
  1. il crée un dossier « mes-notes » à côté de lui, et y copie une première
     fois les notes d'exemple (une seule fois : ensuite il n'y touche plus) ;
  2. il démarre JARVIS en écoute uniquement sur cet ordinateur (127.0.0.1),
     donc invisible depuis le réseau ou Internet ;
  3. il ouvre votre navigateur sur la page d'accueil.

Vos notes restent dans « mes-notes », sur votre disque. Rien ne part ailleurs.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOTES = BASE / "mes-notes"
EXEMPLES = BASE / "examples" / "demo-notes"
PORT_PREFERE = 4700


def dire(message: str) -> None:
    print(message, flush=True)


def port_libre(depart: int) -> int:
    """Cherche un port disponible, en commençant par le préféré."""
    for port in range(depart, depart + 20):
        with socket.socket() as essai:
            try:
                essai.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Aucun port libre entre 4700 et 4719.")


# Marqueur déposé quand le dossier ne contient QUE des exemples : l'interface
# peut alors prévenir honnêtement « exemples fictifs » au lieu de faire croire
# que ce sont vos notes.
MARQUEUR_DEMO = ".jarvis-exemples"
MARQUEUR_BRANCHE = ".jarvis-branche"
EXTENSIONS = (".md", ".txt", ".docx")
TAILLE_MAXIMALE = 2 * 1024 * 1024
FICHIERS_MAXIMUM = 120


def emplacements_documents() -> list[Path]:
    """Les dossiers où un particulier range réellement ses documents.

    Noms français ET anglais : « Bureau » comme « Desktop », car Windows
    localisé traduit le nom affiché, pas toujours le chemin.
    """
    maison = Path.home()
    candidats = []
    for nom in ("Documents", "Mes documents", "OneDrive/Documents", "OneDrive/Bureau"):
        candidats.append(maison / nom)
    for nom in ("Desktop", "Bureau"):
        candidats.append(maison / nom)
    # Sous-dossiers fréquents, pour trouver quelque chose même bien rangé.
    for parent in list(candidats):
        for nom in ("Notes", "notes", "JARVIS", "Mes notes"):
            candidats.append(parent / nom)

    # Le dossier qui CONTIENT celui de JARVIS, et celui de JARVIS lui-même :
    # quelqu'un qui range tout dans C:\IA doit être pris en compte sans rien
    # configurer. Les sous-dossiers y sont explorés un niveau plus bas.
    # Les dossiers qui CONTIENNENT JARVIS, sur deux niveaux : quelqu'un qui range
    # tout dans C:\IA et pose JARVIS dans C:\IA\projets\Jarvis doit être trouvé
    # sans rien configurer. On ne monte jamais au-dessus de la racine du disque
    # ni du dossier personnel, pour ne pas fouiller tout l'ordinateur.
    interdits = {Path(Path.home().anchor or "/"), Path.home()}
    racine = BASE.parent
    for _niveau in range(2):
        if racine in interdits or racine == BASE or not racine.is_dir():
            break
        if racine not in candidats:
            candidats.append(racine)
        try:
            for enfant in sorted(racine.iterdir()):
                if not enfant.is_dir():
                    continue
                if enfant.resolve() == BASE:
                    continue
                if enfant.name.lower() in DOSSIERS_TECHNIQUES:
                    continue
                if enfant not in candidats:
                    candidats.append(enfant)
        except OSError:
            pass
        racine = racine.parent
    vus: set[Path] = set()
    uniques = []
    for chemin in candidats:
        try:
            resolu = chemin.expanduser()
        except (OSError, RuntimeError):
            continue
        if resolu in vus:
            continue
        vus.add(resolu)
        uniques.append(resolu)
    return uniques


# Dossiers du programme : jamais des notes, même s'ils contiennent des .md.
DOSSIERS_TECHNIQUES = {
    "viewer", "examples", "mes-notes", "windows", "tests", "data", "tools",
    "node_modules", "__pycache__", ".git", ".venv", "venv", "assets", "icons",
}


def documents_trouves() -> list[Path]:
    """Fichiers lisibles trouvés sur cet ordinateur, hors dossiers techniques."""
    trouves: list[Path] = []
    for dossier in emplacements_documents():
        if not dossier.is_dir():
            continue
        try:
            entrees = sorted(dossier.iterdir())
        except OSError:
            continue
        for entree in entrees:
            if len(trouves) >= FICHIERS_MAXIMUM:
                return trouves
            try:
                if not entree.is_file():
                    continue
                if any(part.lower() in DOSSIERS_TECHNIQUES
                       for part in entree.relative_to(dossier).parts):
                    continue
                if entree.suffix.lower() not in EXTENSIONS:
                    continue
                if entree.name.startswith((".", "~$")):
                    continue
                if entree.stat().st_size > TAILLE_MAXIMALE or entree.stat().st_size == 0:
                    continue
            except OSError:
                continue
            trouves.append(entree)
    return trouves


def empreinte(chemin: Path) -> str:
    import hashlib

    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError:
        return ""


def fichiers_de(chemin: Path) -> list[Path]:
    """Les fichiers de notes réellement présents dans un dossier."""
    if not chemin.is_dir():
        return []
    resultat = []
    for fichier in sorted(chemin.rglob("*")):
        try:
            if fichier.is_file() and fichier.suffix.lower() in EXTENSIONS:
                resultat.append(fichier)
        except OSError:
            continue
    return resultat


def seulement_des_exemples() -> bool:
    """Vrai si le dossier ne contient rien d'autre que les exemples livrés."""
    if not EXEMPLES.is_dir():
        return False
    ici = fichiers_de(NOTES)
    if not ici:
        return False
    attendus = {f.name: empreinte(f) for f in EXEMPLES.glob("*.md")}
    for fichier in ici:
        reference = attendus.get(fichier.name)
        if reference is None or empreinte(fichier) != reference:
            return False
    return True


def copier_exemples() -> int:
    copies = 0
    if EXEMPLES.is_dir():
        for fichier in sorted(EXEMPLES.glob("*.md")):
            try:
                shutil.copy2(fichier, NOTES / fichier.name)
                copies += 1
            except OSError:
                pass
    return copies


def brancher_documents() -> int:
    """Copie les vrais documents trouvés dans « mes-notes ». Zéro si aucun."""
    trouves = documents_trouves()
    if not trouves:
        return 0

    # On retire les exemples : ils ne doivent pas se mêler aux vraies notes.
    if seulement_des_exemples():
        for fichier in fichiers_de(NOTES):
            try:
                fichier.unlink()
            except OSError:
                pass

    copies = 0
    for source in trouves:
        cible = NOTES / source.name
        suffixe = 2
        while cible.exists():
            cible = NOTES / f"{source.stem} ({suffixe}){source.suffix}"
            suffixe += 1
        try:
            shutil.copy2(source, cible)
            copies += 1
        except OSError:
            continue
    if copies:
        try:
            (NOTES / MARQUEUR_DEMO).unlink()
        except OSError:
            pass
        try:
            (NOTES / MARQUEUR_BRANCHE).write_text(
                str(trouves[0].parent) + "\n", encoding="utf-8")
        except OSError:
            pass
    return copies


def preparer_notes() -> None:
    """Branche JARVIS sur les vrais documents de l'ordinateur.

    Trois cas, dans cet ordre :
      1. le dossier contient déjà de vraies notes → on n'y touche pas ;
      2. il ne contient que des exemples (ou n'existe pas) → on cherche les
         vrais documents de l'utilisateur et on les copie ;
      3. rien de trouvé → les exemples restent, mais signalés comme tels.
    """
    NOTES.mkdir(parents=True, exist_ok=True)

    if notes_reelles():
        dire(f"  Vos notes : {NOTES}")
        dire(f"  {len(fichiers_de(NOTES))} fichier(s) déjà en place, laissés tels quels.")
        return

    copies = brancher_documents()
    if copies:
        origine = ""
        marqueur = NOTES / MARQUEUR_BRANCHE
        try:
            origine = marqueur.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        dire(f"  Vos documents branchés : {copies} fichier(s) copié(s) vers {NOTES}")
        if origine:
            dire(f"  Depuis : {origine}")
        dire("  Vos fichiers d'origine n'ont PAS été modifiés.")
        return

    # Rien trouvé : on garde les exemples, mais on le dit clairement.
    if not fichiers_de(NOTES):
        copies = copier_exemples()
    else:
        copies = len(fichiers_de(NOTES))
    try:
        (NOTES / MARQUEUR_DEMO).write_text("exemples\n", encoding="utf-8")
    except OSError:
        pass
    dire(f"  Dossier de notes : {NOTES}")
    if copies:
        dire(f"  {copies} notes d’EXEMPLE (fictives) : aucun document réel trouvé")
        dire("  dans Documents, Bureau ou OneDrive. Déposez vos fichiers dans")
        dire(f"  {NOTES} puis relancez JARVIS.")


def notes_reelles() -> bool:
    """Vrai si le dossier contient autre chose que les exemples livrés."""
    ici = fichiers_de(NOTES)
    if not ici:
        return False
    return not seulement_des_exemples()


def attendre(port: int, delai: float = 30.0) -> bool:
    fin = time.time() + delai
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.time() < fin:
        try:
            with ouvreur.open(f"http://127.0.0.1:{port}/api/session", timeout=1) as reponse:
                if reponse.status == 200:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.25)
    return False


def voix_naturelle() -> bool:
    """Vrai si le paquet de voix neuronale est installé (aucun import tenté)."""
    try:
        return importlib.util.find_spec("edge_tts") is not None
    except (ImportError, ValueError):
        return False


def fenetre_disponible() -> bool:
    """Vrai si une vraie fenêtre d'application peut être ouverte."""
    if os.environ.get("JARVIS_NAVIGATEUR") == "1":
        return False
    try:
        import webview  # noqa: F401  (présence seulement)
    except Exception:  # noqa: BLE001 - absence ou WebView2 indisponible
        return False
    return True


def chemin_icone() -> str | None:
    """Icône de la fenêtre et de la barre des tâches, si elle existe."""
    for candidat in (BASE / "windows" / "jarvis.ico", BASE / "viewer" / "icons" / "icon-512.png"):
        if candidat.is_file():
            return str(candidat)
    return None


def ouvrir_fenetre(adresse: str) -> bool:
    """Ouvre JARVIS dans sa propre fenêtre, sans navigateur autour.

    Bloque jusqu'à ce que la fenêtre soit fermée : fermer la fenêtre arrête
    JARVIS. Renvoie False si ce n'est pas possible, pour laisser la main au
    navigateur — jamais d'échec bloquant.
    """
    try:
        import webview
    except Exception:  # noqa: BLE001
        return False

    try:
        icone = chemin_icone()
        options = {
            "width": 1360,
            "height": 900,
            "min_size": (960, 640),
            "background_color": "#070b12",
            "text_select": True,
        }
        if icone:
            # `image` sert d'icône de fenêtre sur Windows dès qu'elle est chargée.
            options["image"] = icone
        webview.create_window("JARVIS", adresse, **options)
        webview.start()
        return True
    except Exception as exc:  # noqa: BLE001 - on continue dans le navigateur
        dire(f"  Fenêtre indisponible ({type(exc).__name__}) : ouverture dans le navigateur.")
        return False


def main() -> int:
    if not (BASE / "server.py").is_file():
        dire("  Ce fichier doit rester à côté de server.py, dans le dossier JARVIS.")
        return 1

    dire("")
    dire("  JARVIS — démarrage sur cet ordinateur")
    dire("  ─────────────────────────────────────────────────")

    preparer_notes()
    port = port_libre(PORT_PREFERE)

    environnement = dict(os.environ)
    environnement.update({
        # Écoute locale uniquement : le reste du réseau n'y a pas accès.
        "JARVIS_HOST": "127.0.0.1",
        # Pas de connexion Google : un seul utilisateur, sur son propre PC.
        "JARVIS_AUTH": "off",
        "JARVIS_NOTES_DIR": str(NOTES),
        "PORT": str(port),
    })

    processus = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        cwd=str(BASE), env=environnement,
    )

    adresse = f"http://localhost:{port}"
    try:
        if not attendre(port):
            dire("")
            dire("  Le serveur n’a pas démarré. La fenêtre reste ouverte pour lire l’erreur.")
            return 1
        dire("")
        dire(f"  Adresse : {adresse}")
        dire("  Voix : " + ("naturelle" if voix_naturelle() else "celle de Windows (voix naturelle non installée)"))

        # 1) La vraie fenêtre d'application, si pywebview est disponible.
        if fenetre_disponible() and os.environ.get("JARVIS_NO_BROWSER") != "1":
            dire("  Ouverture de la fenêtre JARVIS. La fermer arrête tout.")
            dire("")
            if ouvrir_fenetre(adresse):
                return 0
        elif os.environ.get("JARVIS_NO_BROWSER") != "1":
            # Sans ce message, on croit que JARVIS « n'est qu'une page web ».
            dire("")
            dire("  Fenêtre d'application indisponible : ouverture dans le navigateur.")
            dire("  Pour l'avoir en vraie fenêtre, lancez une fois :")
            dire("      INSTALLER-APPLICATION.bat")

        # 2) Sinon, le navigateur — et JARVIS reste simple à utiliser.
        dire("")
        dire("  Pour arrêter JARVIS : fermez cette fenêtre, ou Ctrl+C.")
        dire("")
        if os.environ.get("JARVIS_NO_BROWSER") != "1":
            try:
                webbrowser.open(adresse)
            except Exception:  # noqa: BLE001 - un navigateur absent n'est pas une panne
                dire(f"  Ouvrez cette adresse dans votre navigateur : {adresse}")
        return processus.wait()
    except KeyboardInterrupt:
        dire("\n  Arrêt demandé.")
        return 0
    finally:
        if processus.poll() is None:
            processus.terminate()
            try:
                processus.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processus.kill()


if __name__ == "__main__":
    sys.exit(main())
