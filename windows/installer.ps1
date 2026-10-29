# JARVIS - installation comme application Windows
#
# Trois choses, une seule fois :
#   1. verifier que Python est utilisable ;
#   2. installer le composant de fenetre (pywebview) si necessaire ;
#   3. creer un raccourci "JARVIS" sur le Bureau et dans le menu Demarrer.
#
# Fichier volontairement sans accents : Windows PowerShell lit les .ps1 en ANSI
# et abimerait les caracteres accentues.
# En cas d'echec, JARVIS reste utilisable avec LANCER-JARVIS.bat.

$ErrorActionPreference = "Continue"

$dossier = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$lanceur = Join-Path $dossier "lancer_jarvis.py"
$icone = Join-Path $dossier "windows\jarvis.ico"

function Etape([string]$texte) { Write-Host ""; Write-Host "  > $texte" -ForegroundColor Cyan }
function Ok([string]$texte) { Write-Host "    [ok] $texte" -ForegroundColor Green }
function Avertir([string]$texte) { Write-Host "    [!] $texte" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  JARVIS - installation comme application"
Write-Host "  ======================================"

if (-not (Test-Path $lanceur)) {
    Write-Host ""
    Write-Host "  Ce dossier ne contient pas lancer_jarvis.py." -ForegroundColor Red
    Write-Host "  Verifiez que l'archive JARVIS a bien ete decompressee en entier."
    Write-Host ""
    Read-Host "  Appuyez sur Entree pour fermer"
    exit 1
}

# ------------------------------------------------------------- 1. Python
Etape "Recherche de Python"

$python = $null
$essais = @(
    @("py", "-3", "-c", "import sys; print(sys.executable)"),
    @("python", "-c", "import sys; print(sys.executable)"),
    @("python3", "-c", "import sys; print(sys.executable)")
)

foreach ($essai in $essais) {
    $exe = $essai[0]
    $arguments = $essai[1..($essai.Length - 1)]
    try {
        $sortie = & $exe @arguments 2>$null
        if ($LASTEXITCODE -eq 0 -and $sortie) {
            $python = ($sortie | Select-Object -First 1).ToString().Trim()
            break
        }
    } catch {
        continue
    }
}

if (-not $python) {
    Write-Host ""
    Write-Host "  Python n'a pas ete trouve." -ForegroundColor Red
    Write-Host ""
    Write-Host "  1. Ouvrez https://www.python.org/downloads/"
    Write-Host "  2. Cliquez sur le bouton jaune 'Download Python'"
    Write-Host "  3. Lancez le fichier telecharge"
    Write-Host "  4. IMPORTANT : cochez 'Add python.exe to PATH' sur le premier ecran"
    Write-Host "  5. Cliquez 'Install Now', puis relancez ce fichier"
    Write-Host ""
    Read-Host "  Appuyez sur Entree pour fermer"
    exit 1
}

Ok "Python : $python"

# Version sans console : la fenetre JARVIS n'aura pas de terminal derriere.
$pythonw = $python -replace 'python\.exe$', 'pythonw.exe'
if (-not (Test-Path $pythonw)) {
    $pythonw = $python
    Avertir "pythonw.exe introuvable : une fenetre noire restera ouverte derriere JARVIS."
}

# ------------------------------------------------------------- 2. pywebview
Etape "Composant de fenetre (pywebview)"

& $python -c "import webview" 2>$null | Out-Null
$present = ($LASTEXITCODE -eq 0)

if ($present) {
    Ok "deja installe"
} else {
    Write-Host "    installation en cours, environ une minute..."
    & $python -m pip install --user --upgrade --quiet pywebview 2>$null | Out-Null
    & $python -c "import webview" 2>$null | Out-Null
    $present = ($LASTEXITCODE -eq 0)
    if ($present) {
        Ok "installe"
    } else {
        Avertir "installation impossible (pas grave)"
        Write-Host ""
        Write-Host "  JARVIS fonctionnera quand meme : il s'ouvrira dans votre navigateur."
        Write-Host "  Double-cliquez sur LANCER-JARVIS.bat."
    }
}

# ------------------------------------------------------------- 3. raccourcis
Etape "Raccourcis"

$shell = New-Object -ComObject WScript.Shell
$cibles = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "JARVIS.lnk"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\JARVIS.lnk")
)

$crees = 0
foreach ($cible in $cibles) {
    try {
        $parent = Split-Path -Parent $cible
        if (-not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        $raccourci = $shell.CreateShortcut($cible)
        $raccourci.TargetPath = $pythonw
        $raccourci.Arguments = '"' + $lanceur + '"'
        $raccourci.WorkingDirectory = $dossier
        $raccourci.Description = "JARVIS"
        if (Test-Path $icone) {
            $raccourci.IconLocation = $icone + ",0"
        }
        $raccourci.Save()
        $nom = Split-Path -Leaf $cible
        $emplacement = Split-Path -Leaf (Split-Path -Parent $cible)
        $texte = $emplacement + " -> " + $nom
        Ok $texte
        $crees = $crees + 1
    } catch {
        Avertir ("raccourci impossible : " + $cible)
    }
}

Write-Host ""
Write-Host "  ------------------------------------------------"
if ($crees -gt 0) {
    Write-Host "  C'est installe." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Une icone JARVIS est sur votre Bureau."
    Write-Host "  Double-cliquez dessus : JARVIS s'ouvre dans sa propre fenetre."
    Write-Host "  La fermer arrete JARVIS."
} else {
    Avertir "les raccourcis n'ont pas pu etre crees."
    Write-Host "  Utilisez LANCER-JARVIS.bat : JARVIS fonctionnera quand meme."
}
Write-Host "  ------------------------------------------------"
Write-Host ""
Read-Host "  Appuyez sur Entree pour fermer"
