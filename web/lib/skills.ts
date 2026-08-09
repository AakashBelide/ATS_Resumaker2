// Group the flat skill list into readable categories for the Profile page. Deterministic,
// keyword-based; anything unmatched lands in "Other". Order defines display order.
export const SKILL_CATEGORIES = [
  "AI / ML",
  "Data & Analytics",
  "Cloud & DevOps",
  "Languages",
  "Backend & Web",
  "Databases",
  "Other",
] as const;

type Cat = (typeof SKILL_CATEGORIES)[number];

// exact-ish membership (lowercased) — checked before the keyword rules below
const EXACT: Record<string, Cat> = {
  python: "Languages", javascript: "Languages", typescript: "Languages", "html/css": "Languages",
  sql: "Languages", git: "Cloud & DevOps",
  aws: "Cloud & DevOps", azure: "Cloud & DevOps", "azure devops": "Cloud & DevOps",
  "google cloud (gcp)": "Cloud & DevOps", docker: "Cloud & DevOps", "kubernetes (aks)": "Cloud & DevOps",
  "ci/cd": "Cloud & DevOps", terraform: "Cloud & DevOps", prometheus: "Cloud & DevOps",
  opentelemetry: "Cloud & DevOps", linux: "Cloud & DevOps",
  fastapi: "Backend & Web", flask: "Backend & Web", django: "Backend & Web",
  "node/express": "Backend & Web", react: "Backend & Web", angular: "Backend & Web", "rest apis": "Backend & Web",
  postgresql: "Databases", mysql: "Databases", mongodb: "Databases", neo4j: "Databases",
  tigergraph: "Databases", elasticsearch: "Databases", pinecone: "Databases", qdrant: "Databases",
  "vector databases": "Databases",
  airflow: "Data & Analytics", "delta lake": "Data & Analytics", bigquery: "Data & Analytics",
  databricks: "Data & Analytics", snowflake: "Data & Analytics", "pyspark/spark": "Data & Analytics",
  "enterprise data warehouse": "Data & Analytics", "etl pipelines": "Data & Analytics",
  eda: "Data & Analytics", tableau: "Data & Analytics", "power bi": "Data & Analytics",
};

// keyword fallbacks (substring match)
const RULES: [Cat, string[]][] = [
  ["AI / ML", ["ml", "machine learning", "nlp", "llm", "rag", "retrieval", "fine-tun", "computer vision",
    "classification", "decision tree", "scikit", "fraud", "risk model", "prompt", "langchain", "langgraph",
    "crewai", "agent", "openai", "adk", "a2a", "mcp", "tool calling", "human-in-the-loop", "responsible ai",
    "litellm", "gemini", "mlops"]],
  ["Data & Analytics", ["data", "spark", "warehouse", "analytics", "etl", "graph"]],
  ["Cloud & DevOps", ["cloud", "devops", "docker", "kube", "terraform", "aws", "azure", "gcp"]],
  ["Backend & Web", ["api", "react", "angular", "flask", "django", "node", "frontend", "backend"]],
];

export function skillCategory(skill: string): Cat {
  const s = skill.toLowerCase().trim();
  if (EXACT[s]) return EXACT[s];
  for (const [cat, kws] of RULES) if (kws.some((k) => s.includes(k))) return cat;
  return "Other";
}

export function groupSkills(skills: string[]): [Cat, string[]][] {
  const buckets: Record<string, string[]> = {};
  for (const s of skills) (buckets[skillCategory(s)] ??= []).push(s);
  return SKILL_CATEGORIES.map((c) => [c, (buckets[c] ?? []).sort()] as [Cat, string[]]).filter(([, v]) => v.length > 0);
}
