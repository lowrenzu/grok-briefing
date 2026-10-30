#!/usr/bin/env python3
"""JARVIS doit se brancher sur les VRAIS fichiers de l'ordinateur, pas rester
sur les exemples.

Ce test fabrique une fausse « maison » (Documents, Bureau, OneDrive) avec de
vrais documents dedans — Markdown, texte, Word — puis vérifie que :

1. les documents réels sont repris, les exemples écartés ;
2. un document Word est lisible, sans rien installer ;
3. les fichiers d'origine ne sont jamais modifiés ;
4. un second lancement ne réimporte rien et ne touche pas aux notes ;
5. sans aucun document, les exemples restent MAIS sont signalés comme fictifs.

Usage : python3 tests/test_branchement.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTATS: list[tuple[bool, str, str]] = []


def verifier(label: str, ok: bool, detail: str = "") -> None:
    RESULTATS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<52} {detail}")


def copie_neuve() -> Path:
    app = Path(tempfile.mkdtemp(prefix="jarvis-branchement-"))
    for fichier in sorted(ROOT.glob("*.py")):
        shutil.copy2(fichier, app / fichier.name)
    for dossier in ("viewer", "examples"):
        (app / dossier).symlink_to(ROOT / dossier, target_is_directory=True)
    return app


def fausse_maison() -> Path:
    """Une maison crédible : Documents, Bureau, OneDrive."""
    maison = Path(tempfile.mkdtemp(prefix="jarvis-maison-"))
    documents = maison / "Documents"
    bureau = maison / "Bureau"
    one_drive = maison / "OneDrive" / "Documents"
    for dossier in (documents, bureau, one_drive):
        dossier.mkdir(parents=True, exist_ok=True)

    (documents / "Projet de vacances.md").write_text(
        "# Projet de vacances\n\nPartir a Sanguinet en aout, louer un velo.\n", encoding="utf8")
    (documents / "Liste de courses.txt").write_text(
        "Cafe, pain, tomates, huile d'olive.\n", encoding="utf8")
    (bureau / "Idees de cadeaux.md").write_text(
        "# Idees\n\nUn livre sur les oceans pour Anna.\n", encoding="utf8")

    # Un vrai .docx, fabriqué comme Word le fait : une archive avec du XML.
    with zipfile.ZipFile(documents / "Compte rendu reunion.docx", "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>Reunion du 12 octobre : budget valide.</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Prochaine etape : contacter le fournisseur.</w:t></w:r></w:p>"
            "</w:body></w:document>",
        )
        archive.writestr("word/styles.xml", "<styles/>")

    # Pièges à ignorer.
    (documents / "brouillon.docx").mkdir(exist_ok=True)          # un dossier, pas un fichier
    (documents / "~$verrou.docx").write_bytes(b"verrou Word")     # fichier temporaire
    (documents / ".cache.md").write_text("prive", encoding="utf8")  # fichier caché
    return maison


def environnement(app: Path, maison: Path) -> dict[str, str]:
    env = {cle: valeur for cle, valeur in os.environ.items() if not cle.startswith("JARVIS_")}
    env.update(HOME=str(maison), USERPROFILE=str(maison), JARVIS_NO_BROWSER="1", BROWSER="/bin/true")
    env.pop("PYTHONPATH", None)
    return env


def lancer_preparation(app: Path, maison: Path) -> list[str]:
    """Exécute le lanceur juste assez pour qu'il prépare les notes, puis l'arrête."""
    code = (
        "import runpy, sys;"
        f"sys.argv=['lancer_jarvis.py'];"
        "import lancer_jarvis as l;"
        "l.preparer_notes()"
    )
    resultat = subprocess.run([sys.executable, "-u", "-c", code], cwd=str(app),
                             env=environnement(app, maison), capture_output=True,
                             text=True, timeout=120)
    return (resultat.stdout + resultat.stderr).splitlines()


def noms_notes(app: Path) -> set[str]:
    dossier = app / "mes-notes"
    if not dossier.is_dir():
        return set()
    return {f.name for f in dossier.iterdir() if f.is_file() and not f.name.startswith(".")}


# --- 1. avec de vrais documents --------------------------------------------
app = copie_neuve()
maison = fausse_maison()
original = (maison / "Documents" / "Projet de vacances.md").read_bytes()

sortie = lancer_preparation(app, maison)
notes = noms_notes(app)
verifier("les documents réels sont repris", len(notes) >= 4, f"{len(notes)} fichier(s)")
verifier("un fichier Word est repris", "Compte rendu reunion.docx" in notes)
verifier("un fichier texte est repris", "Liste de courses.txt" in notes)
verifier("un fichier du Bureau est repris", "Idees de cadeaux.md" in notes)
verifier("les exemples ont disparu", "Sources à connecter.md" not in notes)
verifier("le fichier temporaire Word est ignoré", "~$verrou.docx" not in notes)
verifier("le fichier caché est ignoré", ".cache.md" not in notes)
verifier("le message dit d'où viennent les fichiers",
         any("copié" in ligne or "branches" in ligne or "branchés" in ligne for ligne in sortie),
         next((l for l in sortie if "copi" in l or "branch" in l), ""))
verifier("les fichiers d'origine sont intacts",
         (maison / "Documents" / "Projet de vacances.md").read_bytes() == original)
verifier("aucun marqueur d'exemples",
         not (app / "mes-notes" / ".jarvis-exemples").exists())

# --- 2. les formats sont réellement lisibles -------------------------------
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(app))
import build  # noqa: E402

lues = build.read_notes(app / "mes-notes")
par_nom = {Path(note["path"]).name: note for note in lues}
verifier("les notes lues sont les vraies", len(lues) >= 4, f"{len(lues)} note(s)")
word = par_nom.get("Compte rendu reunion.docx")
verifier("le texte du Word est extrait", bool(word) and "budget valide" in word["content"],
         (word["content"][:40] + "…") if word else "absent")
verifier("le Word garde ses paragraphes",
         bool(word) and "fournisseur" in word["content"])
verifier("le texte brut est lu", "Cafe" in par_nom.get("Liste de courses.txt", {}).get("content", ""))
verifier("aucune note vide", all(note["content"].strip() for note in lues))

# --- 3. second lancement : rien ne bouge -----------------------------------
avant = {f.name: f.read_bytes() for f in (app / "mes-notes").iterdir() if f.is_file()}
notes_avant = noms_notes(app)
lancer_preparation(app, maison)
apres = {f.name: f.read_bytes() for f in (app / "mes-notes").iterdir() if f.is_file()}
verifier("un second lancement n'ajoute rien", noms_notes(app) == notes_avant,
         f"{len(notes_avant)} → {len(noms_notes(app))}")
verifier("un second lancement ne réécrit rien", avant == apres)

# --- 4. sans document : exemples, mais signalés ----------------------------
app_vide = copie_neuve()
maison_vide = Path(tempfile.mkdtemp(prefix="jarvis-maison-vide-"))
for nom in ("Documents", "Bureau", "OneDrive/Documents"):
    (maison_vide / nom).mkdir(parents=True, exist_ok=True)

sortie_vide = lancer_preparation(app_vide, maison_vide)
notes_vides = noms_notes(app_vide)
verifier("sans document, les exemples sont là", len(notes_vides) == 25, f"{len(notes_vides)} fichier(s)")
verifier("sans document, le marqueur d'exemples est posé",
         (app_vide / "mes-notes" / ".jarvis-exemples").is_file())
verifier("sans document, le message parle d'exemples",
         any("EXEMPLE" in ligne for ligne in sortie_vide),
         next((l for l in sortie_vide if "EXEMPLE" in l), ""))

# --- 5. le serveur annonce lui-même le mode démo ---------------------------
def port_libre() -> int:
    with socket.socket() as prise:
        prise.bind(("127.0.0.1", 0))
        return prise.getsockname()[1]


def statut(app_test: Path) -> dict:
    port = port_libre()
    env = environnement(app_test, maison)
    env.update(PORT=str(port), JARVIS_AUTH="off", JARVIS_HOST="127.0.0.1",
               JARVIS_NOTES_DIR=str(app_test / "mes-notes"),
               JARVIS_DATA_DIR=str(app_test / "data"),
               JARVIS_ACCESS_PATH=str(app_test / "access.json"))
    processus = subprocess.Popen([sys.executable, "-u", "server.py"], cwd=str(app_test),
                                 env=env, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as r:
                    return json.loads(r.read().decode("utf8"))
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.2)
        return {}
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()


etat_vide = statut(app_vide)
verifier("serveur : dossier d'exemples annoncé comme démo", etat_vide.get("isDemo") is True,
         str(etat_vide.get("isDemo")))
etat_reel = statut(app)
verifier("serveur : vraies notes jamais annoncées comme démo", etat_reel.get("isDemo") is False,
         str(etat_reel.get("isDemo")))
verifier("serveur : les vraies notes sont comptées", (etat_reel.get("noteCount") or 0) >= 4,
         str(etat_reel.get("noteCount")))

reussites = sum(1 for ok, _l, _d in RESULTATS if ok)
print(f"\n{reussites}/{len(RESULTATS)} vérifications passées")
raise SystemExit(0 if reussites == len(RESULTATS) else 1)
