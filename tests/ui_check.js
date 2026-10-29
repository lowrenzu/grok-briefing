/* Vérifie l'interface : teintes d'accent et nom personnalisé.
 *
 *   npm install jsdom && node tests/ui_check.js
 *
 * Aucun navigateur requis : la page est chargée dans un DOM simulé, avec les
 * vraies feuilles de style et le vrai script.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "viewer");
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "styles.css"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");

let ok = 0;
let ko = 0;
function check(label, condition, detail = "") {
  console.log(`${condition ? "OK  " : "FAIL"} ${label.padEnd(48)} ${detail}`);
  condition ? ok++ : ko++;
}

function boot(options = {}) {
  const dom = new JSDOM(html, { url: "http://localhost:4700/", runScripts: "outside-only", pretendToBeVisual: true });
  const { window } = dom;
  window.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, {
    get: (_, prop) => {
      if (prop === "measureText") return () => ({ width: 10 });
      if (prop === "createLinearGradient" || prop === "createRadialGradient")
        return () => ({ addColorStop() {} });
      return typeof prop === "string" ? () => {} : undefined;
    },
    set: () => true,
  });
  window.requestAnimationFrame = () => 0;
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  // Synthèse vocale simulée : on enregistre ce que JARVIS demande de dire.
  const paroles = [];
  window.SpeechSynthesisUtterance = function (texte) {
    this.text = texte;
    this.voice = null;
    this.lang = "";
    this.rate = 1;
    this.pitch = 1;
  };
  window.speechSynthesis = {
    speaking: false,
    pending: false,
    getVoices: () => options.voix || [],
    speak(utterance) { paroles.push(utterance); },
    cancel() {},
    addEventListener() {},
    removeEventListener() {},
  };
  if (options.tests) window.__JARVIS_TESTS__ = true;
  const style = window.document.createElement("style");
  style.textContent = css;
  window.document.head.appendChild(style);
  const errors = [];
  window.addEventListener("error", (event) => errors.push(event.message));
  window.eval(app);
  return { window, document: window.document, errors, paroles };
}

const { window, document, errors } = boot();

// --- teintes ---------------------------------------------------------------
const swatches = document.querySelectorAll("[data-accent-choice]");
check("cinq teintes proposées", swatches.length === 5, `${swatches.length}`);
check("la prune existe", !!document.querySelector('[data-accent-choice="prune"]'));
check("le mode auto existe", !!document.querySelector('[data-accent-choice="auto"]'));
check("la pastille auto est un dégradé", css.includes(".accent-dot-auto"));
check("la teinte prune est stylée", css.includes('[data-accent="prune"]'));
check("le cœur est recoloré en prune", /\[data-accent="prune"\] \.jarvis-core img/.test(css));

const prune = document.querySelector('[data-accent-choice="prune"]');
prune.click();
check("prune appliquée", document.documentElement.dataset.accent === "prune");
check("prune mémorisée", window.localStorage.getItem("jarvis-accent") === "prune");
check("une seule pastille cochée",
  document.querySelectorAll('[data-accent-choice][aria-checked="true"]').length === 1);

// --- mode automatique ------------------------------------------------------
const auto = document.querySelector('[data-accent-choice="auto"]');

function withHour(hour, action) {
  const RealDate = window.Date;
  class FakeDate extends RealDate {
    constructor(...args) { super(...(args.length ? args : [2026, 9, 29, hour, 30, 0])); }
    static now() { return new RealDate(2026, 9, 29, hour, 30, 0).getTime(); }
  }
  window.Date = FakeDate;
  try { action(); } finally { window.Date = RealDate; }
}

withHour(9, () => auto.click());
check("9 h : bleu du matin", !document.documentElement.dataset.accent, document.documentElement.dataset.accent || "bleu");

withHour(19, () => auto.click());
check("19 h : ambre du soir", document.documentElement.dataset.accent === "ambre");

withHour(23, () => auto.click());
check("23 h : violet de la nuit", document.documentElement.dataset.accent === "violet");

withHour(4, () => auto.click());
check("4 h : violet aussi", document.documentElement.dataset.accent === "violet");

check("le mode auto est mémorisé", window.localStorage.getItem("jarvis-accent") === "auto");
check("une seule pastille cochée en auto",
  document.querySelectorAll('[data-accent-choice][aria-checked="true"]').length === 1);

// Retour à une teinte fixe : plus de bascule horaire.
prune.click();
check("teinte fixe après le mode auto", document.documentElement.dataset.accent === "prune");
check("teinte fixe mémorisée", window.localStorage.getItem("jarvis-accent") === "prune");

// --- voix : la moins robotique possible ------------------------------------
{
  const VOCABULAIRE = { name: "Microsoft Hortense - French (France)", lang: "fr-FR", localService: true };
  const PAUL = { name: "Microsoft Paul - French (France)", lang: "fr-FR", localService: true };
  const NEURALE = { name: "Microsoft Denise Online (Natural) - French (France)", lang: "fr-FR", localService: false };
  const ANGLAISE = { name: "Microsoft Aria Online (Natural) - English (United States)", lang: "en-US", localService: false };

  const essai = boot({ tests: true, voix: [ANGLAISE, VOCABULAIRE, PAUL, NEURALE] });
  const outils = essai.window.JARVIS_TEST;
  check("accroche de test disponible", !!outils);

  if (outils) {
    check("la voix neuronale est préférée", outils.pickFrenchVoice([ANGLAISE, VOCABULAIRE, PAUL, NEURALE]) === NEURALE);
    check("Hortense est écartée au profit de Paul",
      outils.pickFrenchVoice([VOCABULAIRE, PAUL]) === PAUL);
    check("jamais de voix anglaise pour du français",
      outils.pickFrenchVoice([ANGLAISE]) === null);
    check("aucune voix : pas de plantage", outils.pickFrenchVoice([]) === null);

    const long = "Bonjour. " + "Ceci est une phrase assez longue pour forcer un découpage propre. ".repeat(4) + "Bonne journée.";
    const phrases = outils.decouperEnPhrases(long);
    check("un texte long est découpé", phrases.length > 1, `${phrases.length} phrases`);
    check("aucune phrase trop longue", phrases.every((p) => p.length <= 180),
      `max ${Math.max(...phrases.map((p) => p.length))}`);
    check("le texte est intégralement conservé",
      phrases.join(" ").replace(/\s+/g, " ").trim() === long.replace(/\s+/g, " ").trim());
  }

  // Comportement réel : activer la voix parle avec la meilleure voix disponible.
  essai.document.querySelector("#voiceToggle").click();
  const premiere = essai.paroles[0];
  check("activer la voix déclenche une lecture", !!premiere);
  if (premiere) {
    check("la voix choisie est la neuronale", (premiere.voice || {}).name === NEURALE.name);
    check("débit naturel", premiere.rate === 1, `${premiere.rate}`);
    check("hauteur naturelle", premiere.pitch === 1, `${premiere.pitch}`);
    check("langue française", premiere.lang === "fr-FR");
  }
}

// --- ouverture directe du fichier (file://) --------------------------------
{
  const domFichier = new JSDOM(html, {
    url: "file:///C:/JARVIS/viewer/index.html",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const page = domFichier.window;
  page.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, {
    get: () => () => {},
    set: () => true,
  });
  page.requestAnimationFrame = () => 0;
  page.matchMedia = () => ({ matches: false, addEventListener() {} });
  page.speechSynthesis = { getVoices: () => [], speak() {}, cancel() {} };
  const styleFichier = page.document.createElement("style");
  styleFichier.textContent = css;
  page.document.head.appendChild(styleFichier);
  page.eval(app);

  const texte = page.document.body.textContent || "";
  check("file:// : un message remplace l'interface", texte.includes("ne s’ouvre pas seul"));
  check("file:// : le fichier à lancer est indiqué", texte.includes("LANCER-JARVIS.bat"));
  check("file:// : aucun cockpit inutile", !page.document.querySelector("#questionInput"));
}

// --- nom -------------------------------------------------------------------
check("le nom est présent dans la marque", document.querySelector(".brand-word .js-name") !== null);
check("10 emplacements de nom", document.querySelectorAll(".js-name").length === 10,
  `${document.querySelectorAll(".js-name").length}`);

// applyName n'est pas exporté : on passe par le champ, comme le ferait l'utilisateur.
const field = document.querySelector("#settingsName");
check("champ de nom présent", !!field);
check("24 caractères maximum", field.getAttribute("maxlength") === "24");

// On déclenche l'événement « change », que le code écoute.
window.fetch = () => Promise.resolve({
  ok: true,
  json: () => Promise.resolve({ ok: true, name: "Cortex", customName: true, accent: "prune" }),
});
field.value = "Cortex";
field.dispatchEvent(new window.Event("change"));

setTimeout(() => {
  const names = [...document.querySelectorAll(".js-name")].map((n) => n.textContent);
  check("tous les emplacements renommés", names.every((n) => n === "Cortex"), names[0]);
  check("titre de l'onglet renommé", document.title.startsWith("Cortex"), document.title);
  check("placeholder du chat renommé",
    document.querySelector("#questionInput").placeholder.includes("Cortex"),
    document.querySelector("#questionInput").placeholder);
  check("label d'accessibilité renommé",
    document.querySelector("#brandLink").getAttribute("aria-label").includes("Cortex"));
  check("aucune erreur JavaScript", errors.length === 0, errors[0] || "");

  console.log(`\n${ok}/${ok + ko} vérifications passées`);
  process.exit(ko === 0 ? 0 : 1);
}, 50);
