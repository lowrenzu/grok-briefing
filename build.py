#!/usr/bin/env python3
"""Indexe des notes Markdown pour la galaxie de JARVIS (bibliothèque standard)."""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_NOTES_DIR = ROOT / "examples" / "demo-notes"
VIEWER_DIR = ROOT / "viewer"


def _read_config() -> dict[str, Any]:
    path = ROOT / "config.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_notes_dir(value: str | Path | None = None) -> Path:
    """Retourne le dossier des notes; un chemin relatif est relatif au projet."""
    if value is None:
        value = os.environ.get("JARVIS_NOTES_DIR") or _read_config().get("notes_dir")
    if not value:
        return DEFAULT_NOTES_DIR
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _clean_excerpt(text: str, limit: int = 700) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", " ", text)
    text = re.sub(r"[*_`>~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


# Fichiers que JARVIS sait lire. Le Markdown d'abord, puis le texte brut, puis
# les documents Word : de quoi brancher les vrais fichiers d'un PC sans rien
# convertir ni installer.
EXTENSIONS_LUES = (".md", ".txt", ".docx")

# Dossiers qui ne contiennent jamais des notes de quelqu'un : quand on pointe
# JARVIS sur un gros dossier (C:\IA), il ne doit pas avaler la documentation
# des programmes installés à côté.
DOSSIERS_IGNORES = {
    "node_modules", "__pycache__", "venv", ".venv", "site-packages", "dist",
    "build", "target", ".git", "windows", "viewer", "examples", "mes-notes",
    "tests", "data", "tools",
}

DOCX_BALISE = re.compile(r"<[^>]+>")
DOCX_PARAGRAPHE = re.compile(r"</w:p>")


def lire_docx(path: Path) -> str:
    """Extrait le texte d'un document Word, sans rien installer.

    Un .docx est une archive : le texte vit dans `word/document.xml`. On retire
    les balises et on garde un paragraphe par ligne.
    """
    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open("word/document.xml") as flux:
                xml = flux.read().decode("utf-8", errors="replace")
    except (OSError, KeyError, zipfile.BadZipFile, ValueError):
        return ""
    xml = DOCX_PARAGRAPHE.sub("\n", xml)
    texte = DOCX_BALISE.sub("", xml)
    texte = texte.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    texte = texte.replace("&quot;", '"').replace("&apos;", "'")
    lignes = [ligne.strip() for ligne in texte.splitlines()]
    return "\n".join(ligne for ligne in lignes if ligne).strip()


def lire_fichier(path: Path) -> str:
    """Texte d'une note, quel que soit son format lisible."""
    if path.suffix.lower() == ".docx":
        return lire_docx(path)
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, ValueError):
        return ""


def read_notes(notes_dir: str | Path) -> list[dict[str, Any]]:
    """Lit les fichiers lisibles (.md, .txt, .docx), texte complet gardé côté serveur."""
    base = Path(notes_dir).expanduser().resolve()
    if not base.is_dir():
        return []

    paths = sorted(
        (path for path in base.rglob("*")
         if path.is_file()
         and path.suffix.lower() in EXTENSIONS_LUES
         and not any(part.startswith(".") for part in path.relative_to(base).parts)
         and not any(part.lower() in DOSSIERS_IGNORES
                     for part in path.relative_to(base).parts[:-1])),
        # Les captures JARVIS sont rangées à la fin : l'ajout d'un souvenir garde les anciens IDs stables.
        key=lambda path: (
            path.relative_to(base).parts[0].casefold() == "captures",
            path.relative_to(base).as_posix().casefold(),
        ),
    )
    notes: list[dict[str, Any]] = []
    for path in paths:
        try:
            content = lire_fichier(path)
            relative_path = path.relative_to(base).as_posix()
        except (OSError, ValueError):
            continue
        if not content:
            continue
        parent = Path(relative_path).parent.as_posix()
        group = "Mes notes" if parent == "." else parent.replace("/", " · ")
        label = re.sub(r"[\s_-]+", " ", path.stem).strip() or path.name
        notes.append(
            {
                "id": len(notes),
                "label": label,
                "group": group,
                "excerpt": _clean_excerpt(content),
                "content": content,
                "path": relative_path,
            }
        )
    return notes


# Thèmes proposés dans l'interface. Un mot-clé présent dans le titre pèse six fois
# plus qu'un mot présent dans l'extrait : « Analyse de sorties » reste ainsi une note
# de pêche, et « Plan d'apprentissage » une note de formation.
THEMES: tuple[dict[str, Any], ...] = (
    {"label": "PÊCHE", "keywords": ("peche", "spot", "leurre", "poisson", "sortie", "tactique",
                                    "lure", "fish", "mouche", "carnassier", "bateau")},
    {"label": "PROJETS", "keywords": ("projet", "agent", "dashboard", "commande", "objectif",
                                      "besoin", "architecture", "roadmap", "outil", "connecter")},
    {"label": "CRÉATIVITÉ", "keywords": ("creativ", "idee", "design", "inspiration", "concept")},
    {"label": "MÉDIAS", "keywords": ("media", "video", "musique", "livre", "news", "contenu",
                                     "photo", "podcast")},
    {"label": "FORMATION", "keywords": ("formation", "apprentissage", "apprendre", "tutoriel",
                                        "progresser", "veille")},
    {"label": "ANALYSE", "keywords": ("analyse", "donnee", "decision", "comparer", "statistique",
                                      "mesure", "indicateur")},
    {"label": "NATURE", "keywords": ("meteo", "condition", "nature", "environnement", "climat",
                                     "temperature", "vent", "lac")},
    {"label": "QUOTIDIEN", "keywords": ("quotidien", "rappel", "tache", "organisation", "securite",
                                        "privee", "routine")},
)
UNCLASSIFIED_THEME = "À CLASSER"


def theme_of(note: dict[str, Any]) -> str:
    """Classe une note dans un thème : le dossier, puis les mots du titre, puis l'extrait."""
    group = normalize(note.get("group", ""))
    for theme in THEMES:
        if normalize(theme["label"]) == group:
            return theme["label"]
    title = normalize(note.get("label", ""))
    excerpt = normalize(note.get("excerpt", ""))
    best_label, best_score = UNCLASSIFIED_THEME, 0
    for theme in THEMES:
        score = 6 * sum(title.count(word) for word in theme["keywords"])
        score += sum(excerpt.count(word) for word in theme["keywords"])
        if score > best_score:
            best_label, best_score = theme["label"], score
    return best_label


def build_links(notes: list[dict[str, Any]]) -> list[dict[str, int]]:
    """Relie les notes qui se citent par titre ou partagent un wikilink."""
    normalized_titles = [normalize(note["label"]) for note in notes]
    normalized_bodies = [normalize(note["content"]) for note in notes]
    wikilinks = [
        {normalize(target) for target in re.findall(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]", note["content"]) if normalize(target)}
        for note in notes
    ]
    links: list[dict[str, int]] = []
    for left in range(len(notes)):
        for right in range(left + 1, len(notes)):
            left_title = normalized_titles[left]
            right_title = normalized_titles[right]
            left_mentions_right = bool(right_title) and f" {right_title} " in f" {normalized_bodies[left]} "
            right_mentions_left = bool(left_title) and f" {left_title} " in f" {normalized_bodies[right]} "
            share_wikilink = bool(wikilinks[left] & wikilinks[right])
            if left_mentions_right or right_mentions_left or share_wikilink:
                links.append({"source": left, "target": right})
    return links


def public_graph(notes: list[dict[str, Any]], links: list[dict[str, int]]) -> dict[str, Any]:
    degrees = [0] * len(notes)
    for link in links:
        degrees[link["source"]] += 1
        degrees[link["target"]] += 1
    public_nodes = [
        {
            "id": note["id"],
            "label": note["label"],
            "group": note["group"],
            "theme": theme_of(note),
            "excerpt": note["excerpt"],
            "connections": degrees[note["id"]],
        }
        for note in notes
    ]
    counts: dict[str, int] = {}
    for node in public_nodes:
        counts[node["theme"]] = counts.get(node["theme"], 0) + 1
    themes = [{"label": theme["label"], "count": counts.get(theme["label"], 0)} for theme in THEMES]
    if counts.get(UNCLASSIFIED_THEME):
        themes.append({"label": UNCLASSIFIED_THEME, "count": counts[UNCLASSIFIED_THEME]})
    return {"nodes": public_nodes, "links": links, "themes": themes}


def write_graph_data(graph: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else VIEWER_DIR / "graph-data.js"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    # Les excerpts sont des données, jamais du code JavaScript exécutable.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(f"window.JARVIS_GRAPH = {payload};\n", encoding="utf-8")
    temporary.replace(path)
    return path


def build(notes_dir: str | Path | None = None, output: str | Path | None = None) -> dict[str, Any]:
    notes = read_notes(resolve_notes_dir(notes_dir))
    graph = public_graph(notes, build_links(notes))
    write_graph_data(graph, output)
    return graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Construit la galaxie de connaissances JARVIS depuis des fichiers Markdown.")
    parser.add_argument("--notes", help="Dossier des notes .md (défaut: config.json ou examples/demo-notes)")
    parser.add_argument("--output", help="Fichier JS à générer (défaut: viewer/graph-data.js)")
    args = parser.parse_args()
    graph = build(args.notes, args.output)
    print(f"{len(graph['nodes'])} note(s), {len(graph['links'])} lien(s) indexés.")


if __name__ == "__main__":
    main()
