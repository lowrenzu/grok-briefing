#!/usr/bin/env python3
"""Une mise à jour ne doit JAMAIS effacer les données de l'utilisateur.

Le script d'installation utilise `rsync --delete` : le programme est remis à
neuf, mais data/ (notes, noms, teintes), access.json, config.json et les
captures doivent survivre. Ce test relit les exclusions réelles de install.sh
et rejoue la suppression telle que rsync la pratique.

Usage : python3 tests/test_install_keep.py
"""
from __future__ import annotations

import fnmatch
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTATS: list[tuple[bool, str, str]] = []


def verifier(label: str, ok: bool, detail: str = "") -> None:
    RESULTATS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<46} {detail}")


def exclusions_du_script() -> list[str]:
    """Lit la liste --exclude de la commande rsync, dans install.sh."""
    texte = (ROOT / "install.sh").read_text(encoding="utf-8")
    bloc = re.search(r"rsync -a --delete(.*?)\./ \"\$APP_DIR\"/", texte, re.S)
    if not bloc:
        raise RuntimeError("commande rsync introuvable dans install.sh")
    return re.findall(r"--exclude '([^']+)'", bloc.group(1))


def est_exclu(relatif: str, motifs: list[str]) -> bool:
    """Reproduit la règle rsync : un motif terminé par / vise un dossier."""
    for motif in motifs:
        motif_propre = motif.rstrip("/")
        if motif.endswith("/"):
            if relatif == motif_propre or relatif.startswith(motif_propre + "/"):
                return True
        if fnmatch.fnmatch(relatif, motif_propre) or fnmatch.fnmatch(relatif, motif):
            return True
    return False


def synchroniser(source: Path, cible: Path, motifs: list[str]) -> None:
    """rsync -a --delete : copie le programme, supprime le reste SAUF les exclus."""
    presents = set()
    for fichier in sorted(source.rglob("*")):
        if not fichier.is_file() or "__pycache__" in fichier.parts:
            continue
        relatif = fichier.relative_to(source).as_posix()
        presents.add(relatif)
        # rsync n'ignore pas seulement la suppression : il ne copie pas non plus
        # ce qui est exclu. Sans ça, un data/ local écraserait les vraies données.
        if est_exclu(relatif, motifs):
            continue
        destination = cible / relatif
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fichier, destination)

    for fichier in sorted(cible.rglob("*")):
        if not fichier.is_file():
            continue
        relatif = fichier.relative_to(cible).as_posix()
        if relatif in presents or est_exclu(relatif, motifs):
            continue
        fichier.unlink()


def main() -> int:
    motifs = exclusions_du_script()
    verifier("install.sh exclut le dossier data/", "data/" in motifs, str(motifs))
    verifier("install.sh exclut access.json", "access.json" in motifs)
    verifier("install.sh exclut config.json", "config.json" in motifs)

    source = ROOT
    cible = Path(tempfile.mkdtemp(prefix="jarvis-install-")) / "opt-jarvis"
    cible.mkdir(parents=True)

    donnees = {
        "data/prefs/local.json": '{"name":"Cortex","accent":"prune"}',
        "data/users/abc/notes/idee.md": "Note d'Anna",
        "examples/demo-notes/captures/20261029-souvenir.md": "Souvenir capturé",
        "access.json": '{"admin":"funk.e.lee@gmail.com"}',
        "config.json": '{"auth":{"google_client_id":"x"}}',
        "server.py": "# ancienne version",
    }
    for relatif, contenu in donnees.items():
        chemin = cible / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")

    synchroniser(source, cible, motifs)

    for relatif in donnees:
        chemin = cible / relatif
        existe = chemin.is_file()
        if relatif == "server.py":
            verifier("le programme est bien mis à jour", existe and chemin.read_text(encoding="utf-8") != "# ancienne version")
        else:
            verifier(f"conservé : {relatif}", existe)

    # Le nom et la teinte doivent rester intacts, pas juste le fichier.
    prefs = cible / "data/prefs/local.json"
    verifier("le nom choisi est intact", "Cortex" in prefs.read_text(encoding="utf-8"))
    verifier("la teinte choisie est intacte", "prune" in prefs.read_text(encoding="utf-8"))

    reussites = sum(1 for ok, _, _ in RESULTATS if ok)
    print(f"\n{reussites}/{len(RESULTATS)} vérifications passées")
    return 0 if reussites == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
