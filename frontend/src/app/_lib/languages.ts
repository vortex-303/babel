// Curated TranslateGemma production languages (ISO 639-1 where possible).
// The model officially benchmarks 55 language pairs + supports ~160 pairs
// experimentally. This list is the 40 most-used pairs — safe defaults.
// Native names shown alongside English names so LATAM users aren't forced
// through an English-only selector.

export type Language = {
  code: string;
  name: string;
  native: string;
};

export const LANGUAGES: Language[] = [
  { code: "ar", name: "Arabic", native: "العربية" },
  { code: "bn", name: "Bengali", native: "বাংলা" },
  { code: "bg", name: "Bulgarian", native: "български" },
  { code: "ca", name: "Catalan", native: "Català" },
  { code: "zh", name: "Chinese (Simplified)", native: "中文 (简体)" },
  { code: "zh-Hant", name: "Chinese (Traditional)", native: "中文 (繁體)" },
  { code: "hr", name: "Croatian", native: "Hrvatski" },
  { code: "cs", name: "Czech", native: "Čeština" },
  { code: "da", name: "Danish", native: "Dansk" },
  { code: "nl", name: "Dutch", native: "Nederlands" },
  { code: "en", name: "English", native: "English" },
  { code: "fi", name: "Finnish", native: "Suomi" },
  { code: "fr", name: "French", native: "Français" },
  { code: "de", name: "German", native: "Deutsch" },
  { code: "el", name: "Greek", native: "Ελληνικά" },
  { code: "he", name: "Hebrew", native: "עברית" },
  { code: "hi", name: "Hindi", native: "हिन्दी" },
  { code: "hu", name: "Hungarian", native: "Magyar" },
  { code: "id", name: "Indonesian", native: "Bahasa Indonesia" },
  { code: "it", name: "Italian", native: "Italiano" },
  { code: "ja", name: "Japanese", native: "日本語" },
  { code: "ko", name: "Korean", native: "한국어" },
  { code: "ms", name: "Malay", native: "Bahasa Melayu" },
  { code: "no", name: "Norwegian", native: "Norsk" },
  { code: "fa", name: "Persian", native: "فارسی" },
  { code: "pl", name: "Polish", native: "Polski" },
  { code: "pt", name: "Portuguese", native: "Português" },
  { code: "pt-BR", name: "Portuguese (Brazil)", native: "Português (Brasil)" },
  { code: "ro", name: "Romanian", native: "Română" },
  { code: "ru", name: "Russian", native: "Русский" },
  { code: "sk", name: "Slovak", native: "Slovenčina" },
  { code: "es", name: "Spanish", native: "Español" },
  { code: "sv", name: "Swedish", native: "Svenska" },
  { code: "ta", name: "Tamil", native: "தமிழ்" },
  { code: "th", name: "Thai", native: "ไทย" },
  { code: "tr", name: "Turkish", native: "Türkçe" },
  { code: "uk", name: "Ukrainian", native: "Українська" },
  { code: "ur", name: "Urdu", native: "اردو" },
  { code: "vi", name: "Vietnamese", native: "Tiếng Việt" },
  { code: "cy", name: "Welsh", native: "Cymraeg" },
];

// Spanish regional variants — babel's first LATAM differentiator.
// When target="es", let the user pick a variant. Prompt augmentation
// handles the variant-specific vocabulary/grammar hints.
export type SpanishVariant = {
  code: string;
  label: string;
  hint: string;
};

export const SPANISH_VARIANTS: SpanishVariant[] = [
  {
    code: "es",
    label: "Spanish (neutral)",
    hint: "neutral international Spanish, no regional colloquialisms",
  },
  {
    code: "es-419",
    label: "Spanish (Latin America)",
    hint: "neutral Latin American Spanish, avoids Iberian-specific terms and vosotros",
  },
  {
    code: "es-AR",
    label: "Spanish (Argentina / Uruguay)",
    hint: "rioplatense Spanish: use voseo (vos, tenés), LATAM vocabulary (auto, celular), Argentine idioms where natural",
  },
  {
    code: "es-MX",
    label: "Spanish (Mexico)",
    hint: "Mexican Spanish: tuteo, Mexican vocabulary (carro, celular, padre/chido)",
  },
  {
    code: "es-ES",
    label: "Spanish (Spain)",
    hint: "Peninsular Spanish: tuteo + vosotros, Iberian vocabulary (coche, móvil, ordenador)",
  },
  {
    code: "es-US",
    label: "Spanish (United States)",
    hint: "US Spanish: accessible to bilingual readers, avoid hyper-regional slang",
  },
];

// Portuguese variants — same idea.
export const PORTUGUESE_VARIANTS = [
  { code: "pt", label: "Portuguese (neutral)", hint: "neutral Portuguese" },
  {
    code: "pt-BR",
    label: "Portuguese (Brazil)",
    hint: "Brazilian Portuguese: você/tu usage, Brazilian vocabulary",
  },
  {
    code: "pt-PT",
    label: "Portuguese (Portugal)",
    hint: "European Portuguese: Iberian vocabulary, formal tu",
  },
];

export function findLanguage(code: string): Language | undefined {
  const base = code.split("-")[0];
  return (
    LANGUAGES.find((l) => l.code === code) ??
    LANGUAGES.find((l) => l.code === base)
  );
}
