/** API type aliases. Generated from the harness OpenAPI schema
 * (`npm run gen:api`); hand-written only for the two untyped endpoints. */
import type { components } from "./generated/api-schema";

export type Run = components["schemas"]["RunOut"];
export type Objective = components["schemas"]["ObjectiveOut"];
export type Score = components["schemas"]["ScoreOut"];
export type Turn = components["schemas"]["TurnOut"];
export type RunStats = components["schemas"]["RunStats"];
export type JudgeStats = components["schemas"]["JudgeStats"];
export type PairAgreement = components["schemas"]["PairAgreement"];
export type SelfDivergence = components["schemas"]["SelfDivergence"];
export type RunCreate = components["schemas"]["RunCreate"];

// /health and /models return plain dicts on the FastAPI side
export type Health = {
  status: string;
  database: boolean;
  litellm: boolean;
  target_alias: string;
  judges: string[];
  primary_judge: string;
};

export type Models = { aliases: string[] };
